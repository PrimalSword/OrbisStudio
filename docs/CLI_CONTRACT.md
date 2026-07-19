# OrbisStudio CLI contract

This document defines the public command-line surface for the OrbisStudio 0.4 series.

## Stability policy

Commands and flags listed here are considered stable within the current minor release series. They may gain new optional flags, but existing names and meanings must not change without a deprecation period.

Machine-readable commands print JSON to standard output. Diagnostic messages and fatal errors use standard error. A successful and ready operation exits with code `0`; a valid diagnostic that reports an incomplete toolchain exits with code `2`; malformed arguments use the standard argparse exit code.

## Toolchain commands

### `orbis setup`

Installs the managed AOSP Python tools into the Orbis tool directory.

Stable options:

- `--tools-dir PATH`
- `--force`

### `orbis doctor`

Inspects tool availability.

Stable options:

- `--tools-dir PATH`
- `--scope core|full`

The `core` scope covers the firmware workflow required before controlled HY300 image work. The `full` scope also includes OTA-generation tools.

### `orbis import-native`

Imports locally obtained native executables, copies them into the managed directory, calculates SHA-256, and records their provenance.

Stable options:

- `--from PATH`
- `--tools-dir PATH`

### `orbis verify-tools`

Verifies locked files against `toolchain.lock.json`.

Stable options:

- `--tools-dir PATH`

### `orbis --version`

Prints the installed OrbisStudio package version.

## Firmware commands

The following command names are public and remain delegated to the firmware CLI:

- `init`
- `inspect-gpt`
- `diff`
- `preflight`
- `build-super`
- `ext4-inspect`
- `ext4-extract`
- `ext4-build`
- `sparse-inspect`
- `unsparse`
- `sparse`
- `avb-info`
- `avb-verify`
- `build`

## Environment

`ORBIS_TOOLS` selects the managed tool directory when `--tools-dir` is not provided. OrbisStudio does not modify the global Windows `PATH`.
