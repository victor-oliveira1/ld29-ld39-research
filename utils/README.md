# Firmware utilities and rootfs research

## ActionsFirmware rootfs extractor

[`actions-firmware-extractor.py`](./actions-firmware-extractor.py) reconstructs
the SquashFS root filesystem from an ActionsFirmware package whose rootfs is
stored in gzip chunks. It locates the rootfs stream and follows subsequent gzip
chunks without relying on firmware-specific offsets. The input firmware is
read but not modified.

### Requirements

- Python 3
- `sasquatch`, either on `PATH` or specified with `--sasquatch`

This directory includes [`sasquatch_v4.3_x86_64`](./sasquatch_v4.3_x86_64), a
Linux x86-64 executable. You can build a compatible `sasquatch` for other
platforms with
[Sasquatch-Universal-Builder](https://github.com/M-Tarantino/Sasquatch-Universal-Builder).

### Usage

From the repository root, reconstruct and extract a firmware rootfs:

```sh
python3 utils/actions-firmware-extractor.py \
  --sasquatch utils/sasquatch_v4.3_x86_64 \
  ~/TG01_1.407.14506_OTA.gz
```

By default, the script writes these files beside the firmware package:

- `<firmware-name>_rootfs.squashfs` — reconstructed SquashFS image
- `<firmware-name>_rootfs/` — extracted filesystem contents

For example, `TG01_1.407.14506_OTA.gz` produces
`TG01_1.407.14506_OTA_rootfs.squashfs` and
`TG01_1.407.14506_OTA_rootfs/`.

Specify alternative output paths with `--output` and `--directory`:

```sh
python3 utils/actions-firmware-extractor.py \
  --sasquatch utils/sasquatch_v4.3_x86_64 \
  --output /tmp/rootfs.squashfs \
  --directory /tmp/rootfs \
  ~/TG01_1.407.14506_OTA.gz
```

To reconstruct and validate the image without extracting its contents, use
`--no-extract`:

```sh
python3 utils/actions-firmware-extractor.py \
  --sasquatch utils/sasquatch_v4.3_x86_64 \
  --no-extract \
  ~/TG01_1.407.14506_OTA.gz
```

### Command-line options

| Option | Description |
| --- | --- |
| `-o`, `--output PATH` | Output image path. Defaults to `<firmware-name>_rootfs.squashfs` beside the input. |
| `-d`, `--directory PATH` | Extraction destination. Defaults to `<firmware-name>_rootfs` beside the input. |
| `--sasquatch PATH` | `sasquatch` executable. Defaults to `sasquatch` on `PATH`. |
| `--max-gap BYTES` | Maximum padding between gzip chunks. Defaults to `4096`; increase this if the firmware has larger gaps. |
| `--no-extract` | Reconstruct and validate the image without extracting it. |
| `-h`, `--help` | Show command-line help. |

### Output and safety notes

The script checks the reconstructed image size against the size declared by
SquashFS and asks `sasquatch` to recognize its superblock before extraction.
The image is written before that final validation; an existing file at the
selected output path will be overwritten.

An existing empty extraction directory is removed because `sasquatch` requires
the destination not to exist. A non-empty directory is left untouched and the
script exits with an error; choose another path with `--directory`. Extraction
may require elevated privileges to recreate special device files. If extraction
fails, the reconstructed image is kept for inspection.

If the script cannot find a subsequent chunk, it reports how many bytes were
reconstructed and suggests increasing `--max-gap`. Check that the input is a
supported ActionsFirmware package and that `sasquatch` is available when
troubleshooting other errors.

## Recovered DM01 rootfs inventory

The inventory below summarizes the `DM01_rootfs_recovered/` tree captured from
a recovered root filesystem. It highlights the main areas and selected files
rather than reproducing every path from the original `find` output. This
summary documents the captured tree; it does not mean the extracted rootfs
files are bundled in this `utils/` directory.

| Path | Contents observed in the inventory |
| --- | --- |
| `bin/`, `sbin/`, `usr/bin/`, `usr/sbin/` | BusyBox-based command-line tools and system utilities. |
| `etc/` | Startup, network, wireless, system, and version configuration; includes `init.d/rcS`, `version.conf`, `dnsmasq.conf`, and hostapd configuration files. |
| `lib/modules/2.6.27.29/` | Kernel modules, including `am7x_*`, `amreg`, `edid_i2c_hw`, `hx170dec`, and USB-related modules. |
| `usr/module/` | Additional modules, including `sg7x_udc.ko`, `sg7x_uoc.ko`, and `sg_mifa.ko`. |
| `am7x/bin/` | Device applications such as `wireUI.app`, `manager.app`, `config.app`, `reset.app`, `pthsystem.app`, and `chpll.app`. |
| `am7x/case/scripts/` | Device startup and service scripts for USB, networking, display, Miracast, and driver setup. |
| `am7x/lib/`, `am7x/sdk/` | Device-specific shared libraries and SDK data. |
| `usr/bin/res/sage/` | UI resources and settings, including `conf.xml`, `firmware.conf`, and `resolution_list.conf`. |
| `mnt/user1/`, `mnt/bak/` | Runtime configuration paths, including hostname and DNS-related files. |
| `boot/`, `proc/`, `sys/`, `dev/`, `tmp/`, `var/` | Boot and runtime filesystem locations. |

The names and locations above reflect the captured inventory; they do not
establish that every listed component is active or used by every firmware
version. The rootfs also contains libraries, firmware data, certificates,
network services, and other system files not individually listed here.
