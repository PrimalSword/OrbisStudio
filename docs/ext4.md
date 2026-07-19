# EXT4 editing engine

The EXT4 engine creates a modified copy of a logical partition image. It never opens the source image in writable mode.

## Backend

The first production backend uses `debugfs` from e2fsprogs. On Windows, set the executable path explicitly:

```powershell
$env:ORBIS_DEBUGFS = "C:\OrbisStudio\tools\e2fsprogs\debugfs.exe"
```

The backend is intentionally replaceable. A native Python writer can be added later without changing the CLI or build manifests.

## Inspect an image

```powershell
orbis ext4-inspect --image C:\OrbisOS\Backup\Extracted\Logical\system_a.img
```

## Extract a file

```powershell
orbis ext4-extract `
  --image C:\OrbisOS\Backup\Extracted\Logical\system_a.img `
  --source /system/build.prop `
  --output C:\OrbisOS\Room\Extracted\build.prop
```

## Build an edited copy

```powershell
orbis ext4-build `
  --image C:\OrbisOS\Backup\Extracted\Logical\system_a.img `
  --output C:\OrbisOS\Room\Build\system_a.img `
  --replace "C:\OrbisOS\Room\Work\system_a\system\media\bootanimation.zip=/system/media/bootanimation.zip" `
  --replace "C:\OrbisOS\Room\Work\system_a\system\build.prop=/system/build.prop" `
  --manifest C:\OrbisOS\Room\Reports\system_a.ext4.json
```

A replacement is considered successful only when OrbisStudio extracts the written file from the new image and confirms its SHA-256 against the local source file.

## Safety properties

- source and output paths cannot be equal;
- editing happens on a temporary copy;
- the temporary image is deleted on failure;
- the final image appears only after validation;
- every replacement is verified by extraction and SHA-256;
- a JSON manifest records source hash, output hash, backend and changes;
- parent traversal paths are rejected;
- byte-identical output is rejected when changes were requested.

## Current scope

This engine currently supports regular-file replacement and removal. Directory creation, symbolic links, ownership, permissions, SELinux labels and filesystem resizing will be added as explicit operations rather than guessed automatically.
