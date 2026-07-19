from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import shutil

from .lp import LinearExtent, linear_extents, load_profile


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_super(
    original_super: Path,
    logical_images: dict[str, Path],
    profile_path: Path,
    output: Path,
) -> dict[str, object]:
    profile = load_profile(profile_path)
    extents = linear_extents(profile)
    missing = sorted(set(logical_images) - set(extents))
    if missing:
        raise ValueError(f"Partições sem extent linear no perfil: {', '.join(missing)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original_super, output)

    injected: dict[str, dict[str, object]] = {}
    with output.open("r+b") as target:
        for name, image in logical_images.items():
            extent: LinearExtent = extents[name]
            actual_size = image.stat().st_size
            if actual_size != extent.size:
                raise ValueError(
                    f"{name}: tamanho {actual_size} difere do perfil {extent.size}"
                )
            target.seek(extent.offset)
            with image.open("rb") as source:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            injected[name] = {
                "extent": asdict(extent),
                "image": str(image),
                "sha256": sha256(image),
            }

    verification = verify_super(output, logical_images, extents)
    manifest = {
        "output": str(output),
        "sha256": sha256(output),
        "injected": injected,
        "verification": verification,
    }
    output.with_suffix(output.suffix + ".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def verify_super(
    super_image: Path,
    logical_images: dict[str, Path],
    extents: dict[str, LinearExtent],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    with super_image.open("rb") as source:
        for name, image in logical_images.items():
            extent = extents[name]
            source.seek(extent.offset)
            digest = hashlib.sha256()
            remaining = extent.size
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise EOFError(f"super.img truncada durante verificação de {name}")
                digest.update(chunk)
                remaining -= len(chunk)
            embedded = digest.hexdigest()
            expected = sha256(image)
            result[name] = {
                "embedded_sha256": embedded,
                "expected_sha256": expected,
                "ok": embedded == expected,
            }
    return result
