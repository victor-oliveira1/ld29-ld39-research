#!/usr/bin/env python3
"""
Build candidate protocol-v2 Sage MIRR/VDAT messages from an Annex-B H.264 stream.

Reverse-engineered from:
  ClientMessage20.toPacket()
  ClientMessage20$ChannelType
  MirrorCommand.addBuffer()
  MirrorCommand$Type
  MirrorCommand$StreamData.addBuffer()
  PacketBuffer.push(int)

Message layout (all integer fields little-endian):
  0x00  char[4] "RRIM"  (reversed bytes for logical token "MIRR")
  0x04  uint32  magic   (upper 16 bits = session SSID, lower 16 random per message)
  0x08  uint32  value   (defaults to 0 in ClientMessage20)
  0x0c  char[4] "TADV"  (reversed bytes for logical token "VDAT")
  0x10  uint32  timestamp_ms (System.currentTimeMillis() truncated to 32 bits)
  0x14  uint32  angle
  0x18  uint32  payload_length
  0x1c  bytes   H.264 access unit as output by MediaCodec

This tool packetizes only. It does NOT perform the USB/AOA handshake or transmit data.
Input must be raw Annex-B H.264 with Access Unit Delimiter NALs (type 9), so each
AUD starts a new access unit. Re-encode with x264 aud=1 if needed.
"""
from __future__ import annotations

import argparse
import csv
import random
import struct
import sys
import time
from pathlib import Path

START4 = b"\x00\x00\x00\x01"
START3 = b"\x00\x00\x01"
HEADER_SIZE = 28

def split_annexb_nals(data: bytes) -> list[bytes]:
    """Split Annex-B stream into NAL units, retaining each start code."""
    starts: list[tuple[int, int]] = []
    i = 0
    while i < len(data) - 2:
        if data[i:i+4] == START4:
            starts.append((i, 4))
            i += 4
        elif data[i:i+3] == START3:
            starts.append((i, 3))
            i += 3
        else:
            i += 1
    if not starts:
        raise ValueError("No Annex-B start codes found. Convert to raw .h264 first.")
    nals: list[bytes] = []
    for idx, (pos, _sc_len) in enumerate(starts):
        end = starts[idx+1][0] if idx+1 < len(starts) else len(data)
        nal = data[pos:end]
        if nal:
            nals.append(nal)
    return nals

def nal_type(nal: bytes) -> int:
    off = 4 if nal.startswith(START4) else 3 if nal.startswith(START3) else 0
    if len(nal) <= off:
        return -1
    return nal[off] & 0x1f

def group_access_units(nals: list[bytes]) -> list[bytes]:
    """Group NALs by AUD (type 9); AUD belongs to the access unit it starts."""
    if not any(nal_type(n) == 9 for n in nals):
        raise ValueError(
            "No AUD NALs (type 9) found. Re-encode with: "
            "ffmpeg -i input.mp4 -an -c:v libx264 -preset ultrafast "
            "-tune zerolatency -x264-params 'aud=1:keyint=30:repeat-headers=1' "
            "-f h264 input_aud.h264"
        )
    units: list[bytes] = []
    current: list[bytes] = []
    for nal in nals:
        if nal_type(nal) == 9 and current:
            units.append(b"".join(current))
            current = []
        current.append(nal)
    if current:
        units.append(b"".join(current))
    return units

def make_message(access_unit: bytes, *, ssid: int, angle: int,
                 timestamp_ms: int, rng: random.Random) -> tuple[bytes, int]:
    # ClientMessage20 initializes magic = random 32-bit value with upper 16 bits
    # replaced by static SSID; each message therefore shares SSID and random low bits.
    magic = (ssid & 0xffff0000) | rng.randrange(0x10000)
    # ChannelType.toArray() reverses ASCII token bytes; same for MirrorCommand.Type.
    msg = (
        b"RRIM"
        + struct.pack("<II", magic, 0)  # magic, value (default 0)
        + b"TADV"
        + struct.pack("<III", timestamp_ms & 0xffffffff,
                      angle & 0xffffffff, len(access_unit))
        + access_unit
    )
    assert len(msg) == HEADER_SIZE + len(access_unit)
    return msg, magic

def main() -> int:
    ap = argparse.ArgumentParser(description="Packetize H.264 into Sage protocol-v2 MIRR/VDAT messages.")
    ap.add_argument("input", type=Path, help="raw Annex-B .h264 input")
    ap.add_argument("-o", "--output-dir", type=Path, default=Path("sage_v2_packets"),
                    help="directory for one .bin file per VDAT message")
    ap.add_argument("--fps", type=float, default=30.0, help="timestamp increment rate (default: 30)")
    ap.add_argument("--angle", type=int, default=0, help="rotation angle field (default: 0)")
    ap.add_argument("--ssid", type=lambda x: int(x, 0), default=None,
                    help="optional 16-bit session id, e.g. 0x4a20; random if omitted")
    ap.add_argument("--start-timestamp", type=lambda x: int(x, 0), default=None,
                    help="starting timestamp in ms (32-bit; default: current time)")
    ap.add_argument("--seed", type=int, default=None, help="optional RNG seed for repeatable magic values")
    args = ap.parse_args()

    if args.fps <= 0:
        ap.error("--fps must be greater than zero")
    if not 0 <= args.angle <= 0xffffffff:
        ap.error("--angle must fit an unsigned 32-bit integer")
    if args.ssid is not None and not 0 <= args.ssid <= 0xffff:
        ap.error("--ssid must be a 16-bit value (0..65535)")

    try:
        raw = args.input.read_bytes()
        nals = split_annexb_nals(raw)
        access_units = group_access_units(nals)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    ssid = (args.ssid if args.ssid is not None else rng.randrange(0x10000)) << 16
    ts0 = args.start_timestamp if args.start_timestamp is not None else int(time.time() * 1000)
    step = max(1, round(1000.0 / args.fps))

    index_path = args.output_dir / "index.csv"
    with index_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame_index", "filename", "timestamp_ms_u32", "magic_hex",
                    "payload_bytes", "message_bytes", "nal_count", "contains_idr"])
        total_bytes = 0
        for i, au in enumerate(access_units):
            ts = (ts0 + i * step) & 0xffffffff
            msg, magic = make_message(au, ssid=ssid, angle=args.angle,
                                      timestamp_ms=ts, rng=rng)
            filename = f"vdat_{i:06d}.bin"
            (args.output_dir / filename).write_bytes(msg)
            au_nals = split_annexb_nals(au)
            types = [nal_type(n) for n in au_nals]
            w.writerow([i, filename, ts, f"0x{magic:08x}", len(au), len(msg),
                        len(au_nals), int(5 in types)])
            total_bytes += len(msg)

    print(f"NAL units: {len(nals)}")
    print(f"Access units: {len(access_units)}")
    print(f"SSID upper 16 bits: 0x{ssid >> 16:04x}")
    print(f"Output directory: {args.output_dir}")
    print(f"Index: {index_path}")
    print(f"Total serialized message bytes: {total_bytes}")
    print("NOTE: messages are serialized, not sent; start/handshake negotiation is not implemented.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
