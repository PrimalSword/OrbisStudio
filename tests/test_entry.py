from __future__ import annotations

from orbisstudio.entry import (
    PUBLIC_BOOTSTRAP_COMMANDS,
    PUBLIC_WORKSPACE_COMMANDS,
    _bootstrap_parser,
    _workspace_parser,
)


def test_public_bootstrap_commands_are_stable() -> None:
    assert PUBLIC_BOOTSTRAP_COMMANDS == (
        "setup",
        "doctor",
        "import-native",
        "verify-tools",
    )


def test_public_workspace_commands_are_stable() -> None:
    assert PUBLIC_WORKSPACE_COMMANDS == (
        "workspace-create",
        "workspace-info",
        "workspace-verify",
    )


def test_doctor_defaults_to_full_scope() -> None:
    args = _bootstrap_parser().parse_args(["doctor"])
    assert args.command == "doctor"
    assert args.scope == "full"


def test_import_native_requires_source() -> None:
    args = _bootstrap_parser().parse_args(["import-native", "--from", "tools"])
    assert args.command == "import-native"
    assert args.source == "tools"


def test_workspace_create_contract() -> None:
    args = _workspace_parser().parse_args(
        ["workspace-create", "--source", "dump", "--project", "HY300"]
    )
    assert args.command == "workspace-create"
    assert args.source == "dump"
    assert args.project == "HY300"
    assert args.copy_to_work is False
