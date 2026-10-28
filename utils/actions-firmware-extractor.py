#!/usr/bin/env python3
"""Extract a SquashFS rootfs from ActionsFirmware packages with gzip chunks.

Requires Python 3 and sasquatch on PATH. Does not modify the input firmware.
The script discovers gzip streams dynamically; it does not use firmware-specific offsets.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

GZIP_MAGIC = b"\x1f\x8b\x08"
ROOTFS_MAGICS = (b"shsq", b"hsqs")
DEFAULT_MAX_GAP = 4096


def gzip_offsets(data: bytes):
    pos = 0
    while True:
        pos = data.find(GZIP_MAGIC, pos)
        if pos < 0:
            return
        yield pos
        pos += 1


def inflate_gzip_at(data: bytes, offset: int):
    dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = dec.decompress(data[offset:])
    out += dec.flush()
    if not dec.eof:
        raise ValueError("incomplete gzip stream")
    consumed = len(data[offset:]) - len(dec.unused_data)
    if consumed <= 0:
        raise ValueError("invalid gzip stream length")
    return out, consumed


def declared_squashfs_size(image: bytes, tool: str) -> int:
    with tempfile.NamedTemporaryFile(prefix="actions-rootfs-probe-", suffix=".bin") as tmp:
        tmp.write(image)
        tmp.flush()
        proc = subprocess.run(
            [tool, "-s", tmp.name], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False
        )
    report = proc.stdout
    match = re.search(r"\((\d+)\s+\[0x[0-9a-fA-F]+\]\s+bytes\)", report)
    if not match:
        raise ValueError("sasquatch did not report a SquashFS filesystem size:\n" + report.strip())
    return int(match.group(1))


def find_rootfs_stream(data: bytes, tool: str):
    for offset in gzip_offsets(data):
        try:
            out, consumed = inflate_gzip_at(data, offset)
        except (zlib.error, ValueError):
            continue
        if not out.startswith(ROOTFS_MAGICS):
            continue
        try:
            size = declared_squashfs_size(out, tool)
        except (ValueError, OSError):
            continue
        # A valid candidate must contain a complete-looking superblock and declare
        # a plausible image larger than this first decompressed chunk.
        if size >= 96 and size > len(out):
            return offset, out, consumed, size
    raise RuntimeError("could not find a gzip stream that begins with a recognized SquashFS rootfs")


def next_gzip_stream(data: bytes, after: int, max_gap: int):
    end = min(len(data), after + max_gap + len(GZIP_MAGIC))
    pos = data.find(GZIP_MAGIC, after, end)
    while pos >= 0:
        try:
            out, consumed = inflate_gzip_at(data, pos)
            return pos, out, consumed
        except (zlib.error, ValueError):
            pos = data.find(GZIP_MAGIC, pos + 1, end)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path, help="input ActionsFirmware package")
    parser.add_argument("-o", "--output", type=Path, help="output rootfs image (default: <firmware>_rootfs.squashfs)")
    parser.add_argument("-d", "--directory", type=Path, help="directory to extract into (default: <firmware>_rootfs)")
    parser.add_argument("--sasquatch", default="sasquatch", help="sasquatch executable (default: sasquatch)")
    parser.add_argument("--max-gap", type=int, default=DEFAULT_MAX_GAP,
                        help=f"maximum padding between gzip chunks in bytes (default: {DEFAULT_MAX_GAP})")
    parser.add_argument("--no-extract", action="store_true", help="only reconstruct and validate the rootfs image")
    args = parser.parse_args()

    if not args.firmware.is_file():
        parser.error(f"input file does not exist: {args.firmware}")
    tool = shutil.which(args.sasquatch)
    if not tool:
        parser.error(f"cannot find sasquatch executable: {args.sasquatch}")
    if args.max_gap < 0:
        parser.error("--max-gap must be >= 0")

    data = args.firmware.read_bytes()
    print(f"[+] Input: {args.firmware} ({len(data):,} bytes)")
    start, first, consumed, expected = find_rootfs_stream(data, tool)
    print(f"[+] Rootfs gzip stream found at 0x{start:X}")
    print(f"[+] First chunk: {len(first):,} decompressed bytes; gzip length {consumed:,} bytes")
    print(f"[+] SquashFS declares {expected:,} bytes")

    combined = bytearray(first)
    next_offset = start + consumed
    chunks = 1

    while len(combined) < expected:
        candidate = next_gzip_stream(data, next_offset, args.max_gap)
        if candidate is None:
            raise RuntimeError(
                f"rootfs is incomplete: reconstructed {len(combined):,}/{expected:,} bytes; "
                f"no valid gzip stream found within {args.max_gap} bytes after offset 0x{next_offset:X}. "
                "Try increasing --max-gap if this firmware inserts larger padding."
            )
        offset, chunk, chunk_len = candidate
        if not chunk:
            raise RuntimeError(f"empty gzip chunk at 0x{offset:X}")
        print(f"[+] Chunk {chunks + 1}: offset 0x{offset:X}, {len(chunk):,} decompressed bytes")
        combined.extend(chunk)
        chunks += 1
        next_offset = offset + chunk_len

    if len(combined) < expected:
        raise RuntimeError(f"incomplete rootfs: {len(combined)} < {expected}")
    image = bytes(combined[:expected])

    output = args.output or args.firmware.with_name(args.firmware.stem + "_rootfs.squashfs")
    output.write_bytes(image)
    print(f"[+] Wrote validated-size image: {output} ({len(image):,} bytes; {chunks} gzip chunk(s))")

    # Ask sasquatch to parse the reconstructed image before extraction.
    probe = subprocess.run([tool, "-s", str(output)], text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if probe.returncode != 0 or "valid little endian SQUASHFS" not in probe.stdout:
        print("[!] Warning: sasquatch did not explicitly confirm a valid SquashFS superblock:")
        print(probe.stdout.strip())
        sys.exit(2)
    print("[+] Sasquatch recognizes the reconstructed SquashFS superblock.")

    if args.no_extract:
        return

    directory = args.directory or args.firmware.with_name(args.firmware.stem + "_rootfs")
    # Sasquatch requires the destination path not to exist at all, even when it is
    # an empty directory. Remove only an empty existing directory; never delete a
    # non-empty directory or its contents automatically.
    if directory.exists():
        if not directory.is_dir():
            raise RuntimeError(f"extraction destination exists and is not a directory: {directory}")
        try:
            directory.rmdir()
            print(f"[+] Removed existing empty destination directory: {directory}")
        except OSError:
            raise RuntimeError(
                f"extraction directory already exists and is not empty: {directory}; "
                "choose another path with -d. Its contents were not changed."
            )

    proc = subprocess.run([tool, "-d", str(directory), str(output)], check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"sasquatch extraction failed with exit code {proc.returncode}; image kept at {output}. "
            f"Check whether the image is complete and whether {directory} was partially created."
        )
    if not directory.is_dir() or not any(directory.iterdir()):
        raise RuntimeError(
            f"sasquatch returned success but the extraction directory is missing or empty: {directory}; "
            f"image kept at {output}"
        )
    print(f"[+] Extracted rootfs to: {directory}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, zlib.error) as exc:
        print(f"[!] Error: {exc}", file=sys.stderr)
        sys.exit(1)
