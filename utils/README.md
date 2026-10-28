# Firmware utilities

## ActionsFirmware rootfs extractor

[`actions-firmware-extractor.py`](./actions-firmware-extractor.py) reconstructs
the SquashFS root filesystem from an ActionsFirmware package whose rootfs is
stored in gzip chunks. It searches for the rootfs stream and follows subsequent
gzip chunks; it does not rely on firmware-specific offsets. The input firmware
is read but not modified.

### Requirements

- Python 3
- `sasquatch`, available on `PATH` or provided with `--sasquatch`

This directory includes a `sasquatch` executable for Linux x86-64. From the
repository root, pass it explicitly with `--sasquatch utils/sasquatch`. On
other platforms, use a compatible `sasquatch` executable.
You can build sasquatch using this repo: [Sasquatch-Universal-Builder](https://github.com/M-Tarantino/Sasquatch-Universal-Builder)

### Usage

Run from the repository root to reconstruct the rootfs image and extract it:

```sh
python3 utils/actions-firmware-extractor.py \
  --sasquatch utils/sasquatch \
  ~/TG01_1.407.14506_OTA.gz
```

By default, the script writes these files beside the firmware package:

- `<firmware-name>_rootfs.squashfs` — reconstructed SquashFS image
- `<firmware-name>_rootfs/` — extracted filesystem contents

For example, `TG01_1.407.14506_OTA.gz` produces
`TG01_1.407.14506_OTA_rootfs.squashfs` and
`TG01_1.407.14506_OTA_rootfs/`.

To choose different output paths:

```sh
python3 utils/actions-firmware-extractor.py \
  --sasquatch utils/sasquatch \
  --output /tmp/rootfs.squashfs \
  --directory /tmp/rootfs \
  ~/TG01_1.407.14506_OTA.gz
```

To reconstruct and validate the image without extracting its contents, add
`--no-extract`:

```sh
python3 utils/actions-firmware-extractor.py \
  --sasquatch utils/sasquatch \
  --no-extract \
  ~/TG01_1.407.14506_OTA.gz
```

### Options

| Option | Description |
| --- | --- |
| `-o`, `--output PATH` | Output image path. Defaults to `<firmware-name>_rootfs.squashfs` beside the input. |
| `-d`, `--directory PATH` | Extraction destination. Defaults to `<firmware-name>_rootfs` beside the input. |
| `--sasquatch PATH` | `sasquatch` executable to use. Defaults to `sasquatch` on `PATH`. |
| `--max-gap BYTES` | Maximum padding between gzip chunks. Defaults to `4096`; increase this if the firmware has larger gaps. |
| `--no-extract` | Reconstruct and validate the image without extracting it. |
| `-h`, `--help` | Show command-line help. |

### Output and safety notes

The script validates the reconstructed image size against the size declared by
SquashFS and asks `sasquatch` to recognize its superblock before extraction.
The output image is written before that final validation, so an existing file
at the selected output path will be overwritten.

An existing empty extraction directory is removed because `sasquatch` requires
the destination not to exist. A non-empty directory is left untouched and the
script exits with an error; choose another path with `--directory` instead.
Extraction may require elevated privileges to recreate special device files.
If extraction fails, the reconstructed image is kept for inspection.

If the script cannot find a subsequent chunk, it reports how many bytes were
reconstructed and suggests increasing `--max-gap`. Check that the input is a
supported ActionsFirmware package and that `sasquatch` is available when
troubleshooting other errors.
