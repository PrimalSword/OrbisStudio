from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import shutil
import sys
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .toolchain import DEFAULT_TOOLS, inspect_toolchain


class BootstrapError(RuntimeError):
    """Raised when the managed toolchain cannot be installed safely."""


@dataclass(frozen=True)
class ManagedTool:
    name: str
    filename: str
    url: str
    encoding: str = "base64"
    sha256: str | None = None


@dataclass(frozen=True)
class SetupItem:
    name: str
    status: str
    path: str | None
    sha256: str | None
    detail: str


@dataclass(frozen=True)
class SetupReport:
    platform: str
    architecture: str
    tools_directory: str
    items: tuple[SetupItem, ...]
    scope: str = "full"

    @property
    def ready(self) -> bool:
        required = CORE_TOOLS if self.scope == "core" else DEFAULT_TOOLS
        by_name = {item.name: item for item in self.items}
        return all(
            by_name.get(name) is not None
            and by_name[name].status in {"installed", "present", "imported"}
            for name in required
        )

    def to_json(self) -> str:
        payload = asdict(self)
        payload["ready"] = self.ready
        return json.dumps(payload, ensure_ascii=False, indent=2)


MANAGED_TOOLS: tuple[ManagedTool, ...] = (
    ManagedTool(
        "avbtool",
        "avbtool.py",
        "https://android.googlesource.com/platform/external/avb/+/refs/heads/main/avbtool.py?format=TEXT",
    ),
    ManagedTool(
        "mkbootimg",
        "mkbootimg.py",
        "https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/main/mkbootimg.py?format=TEXT",
    ),
    ManagedTool(
        "unpack_bootimg",
        "unpack_bootimg.py",
        "https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/main/unpack_bootimg.py?format=TEXT",
    ),
    ManagedTool(
        "mkdtimg",
        "mkdtboimg.py",
        "https://android.googlesource.com/platform/system/libufdt/+/refs/heads/main/utils/src/mkdtboimg.py?format=TEXT",
    ),
)

NATIVE_TOOLS = (
    "lpunpack",
    "lpmake",
    "payload_generator",
    "brillo_update_payload",
    "dtc",
)

CORE_TOOLS = (
    "lpunpack",
    "lpmake",
    "avbtool",
    "mkbootimg",
    "unpack_bootimg",
    "dtc",
    "mkdtimg",
)

_NATIVE_FILENAMES: dict[str, tuple[str, ...]] = {
    "lpunpack": ("lpunpack.exe", "lpunpack"),
    "lpmake": ("lpmake.exe", "lpmake"),
    "payload_generator": ("payload_generator.exe", "payload_generator"),
    "brillo_update_payload": ("brillo_update_payload.exe", "brillo_update_payload"),
    "dtc": ("dtc.exe", "dtc"),
}


def default_tools_directory() -> Path:
    configured = os.environ.get("ORBIS_TOOLS")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".orbisstudio" / "tools").resolve()


def _download(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "OrbisStudio/0.4"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _decode(payload: bytes, encoding: str) -> bytes:
    if encoding == "base64":
        try:
            return base64.b64decode(payload, validate=True)
        except ValueError as error:
            raise BootstrapError("AOSP returned invalid base64 content") from error
    if encoding == "raw":
        return payload
    raise BootstrapError(f"unsupported managed-tool encoding: {encoding}")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".orbis.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _write_launcher(directory: Path, tool: ManagedTool) -> Path:
    if os.name == "nt":
        launcher = directory / f"{tool.name}.cmd"
        text = f'@echo off\r\n"{sys.executable}" "%~dp0{tool.filename}" %*\r\n'
    else:
        launcher = directory / tool.name
        text = f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/{tool.filename}" "$@"\n'
    _atomic_write(launcher, text.encode("utf-8"))
    if os.name != "nt":
        launcher.chmod(0o755)
    return launcher


def _read_lock(root: Path) -> dict[str, dict[str, str]]:
    path = root / "toolchain.lock.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BootstrapError("invalid toolchain lock file")
    return {str(name): dict(value) for name, value in data.items() if isinstance(value, dict)}


def _write_lock(root: Path, lock: dict[str, dict[str, str]]) -> None:
    (root / "toolchain.lock.json").write_text(
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def import_native_tools(source: Path, directory: Path | None = None) -> SetupReport:
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise BootstrapError(f"native tool source is not a directory: {source}")
    root = (directory or default_tools_directory()).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = _read_lock(root)
    items: list[SetupItem] = []

    for name in NATIVE_TOOLS:
        candidate = next((source / filename for filename in _NATIVE_FILENAMES[name] if (source / filename).is_file()), None)
        if candidate is None:
            items.append(SetupItem(name, "missing", None, None, "not found in import directory"))
            continue
        payload = candidate.read_bytes()
        if not payload:
            raise BootstrapError(f"refusing to import empty tool: {candidate}")
        target = root / candidate.name
        _atomic_write(target, payload)
        digest = _sha256(payload)
        lock[name] = {
            "path": str(target),
            "sha256": digest,
            "source": str(candidate),
            "kind": "native-import",
        }
        items.append(SetupItem(name, "imported", str(target), digest, "copied and hash-locked"))

    _write_lock(root, lock)
    return doctor(root)


def verify_lock(directory: Path | None = None) -> SetupReport:
    root = (directory or default_tools_directory()).expanduser().resolve()
    lock = _read_lock(root)
    items: list[SetupItem] = []
    for name in DEFAULT_TOOLS:
        entry = lock.get(name)
        if entry is None:
            items.append(SetupItem(name, "unlocked", None, None, "no lock entry"))
            continue
        path = Path(entry.get("path", ""))
        expected = entry.get("sha256")
        if not path.is_file():
            items.append(SetupItem(name, "missing", str(path), expected, "locked file is absent"))
            continue
        actual = _sha256(path.read_bytes())
        status = "present" if expected == actual else "mismatch"
        items.append(SetupItem(name, status, str(path), actual, "hash verified" if status == "present" else f"expected {expected}"))
    return SetupReport(platform.system(), platform.machine(), str(root), tuple(items))


def setup_tools(
    directory: Path | None = None,
    force: bool = False,
    downloader: Callable[[str], bytes] = _download,
) -> SetupReport:
    root = (directory or default_tools_directory()).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    items: list[SetupItem] = []
    lock = _read_lock(root)

    for tool in MANAGED_TOOLS:
        target = root / tool.filename
        if target.is_file() and not force:
            digest = _sha256(target.read_bytes())
            _write_launcher(root, tool)
            items.append(SetupItem(tool.name, "present", str(target), digest, "managed AOSP script"))
            lock[tool.name] = {"path": str(target), "sha256": digest, "source": tool.url, "kind": "aosp-script"}
            continue

        raw = downloader(tool.url)
        payload = _decode(raw, tool.encoding)
        digest = _sha256(payload)
        if tool.sha256 is not None and digest.lower() != tool.sha256.lower():
            raise BootstrapError(
                f"SHA-256 mismatch for {tool.name}: expected {tool.sha256}, received {digest}"
            )
        _atomic_write(target, payload)
        _write_launcher(root, tool)
        items.append(SetupItem(tool.name, "installed", str(target), digest, "downloaded from AOSP"))
        lock[tool.name] = {"path": str(target), "sha256": digest, "source": tool.url, "kind": "aosp-script"}

    _write_lock(root, lock)
    available = {item.name: item for item in inspect_toolchain(DEFAULT_TOOLS, root)}
    for name in NATIVE_TOOLS:
        status = available[name]
        items.append(
            SetupItem(
                name,
                "present" if status.available else "manual",
                status.path,
                None,
                "native executable detected" if status.available else "use 'orbis import-native --from DIR'",
            )
        )

    return SetupReport(platform.system(), platform.machine(), str(root), tuple(items))


def doctor(directory: Path | None = None, scope: str = "full") -> SetupReport:
    if scope not in {"core", "full"}:
        raise BootstrapError(f"invalid doctor scope: {scope}")
    root = (directory or default_tools_directory()).expanduser().resolve()
    tools = inspect_toolchain(DEFAULT_TOOLS, root)
    items = tuple(
        SetupItem(
            item.name,
            "present" if item.available else "missing",
            item.path,
            _sha256(Path(item.path).read_bytes()) if item.path and Path(item.path).is_file() else None,
            "ready" if item.available else "run 'orbis setup' or import a verified native tool",
        )
        for item in tools
    )
    return SetupReport(platform.system(), platform.machine(), str(root), items, scope)
