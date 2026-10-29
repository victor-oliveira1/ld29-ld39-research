#!/usr/bin/env python3
"""
Experimental Sage Mirroring Suit H.264 packetizer.

This creates candidate MIRR/VDAT messages from an Annex-B H.264 stream.
It does NOT send USB data and the private protocol fields are only partially
understood. Use a MIRR frame message captured from your own session as template.
"""
from __future__ import annotations
import argparse
import struct
import sys
from pathlib import Path

START_CODES = (b"\x00\x00\x00\x01", b"\x00\x00\x01")

def split_annexb(data: bytes) -> list[bytes]:
    """Return NAL units without Annex-B start codes."""
    starts = []
    i = 0
    n = len(data)
    while i < n - 2:
        if data[i:i+4] == START_CODES[0]:
            starts.append((i, 4))
            i += 4
        elif data[i:i+3] == START_CODES[1]:
            starts.append((i, 3))
            i += 3
        else:
            i += 1
    if not starts:
        raise ValueError("No Annex-B H.264 start codes found. Convert input to raw .h264 first.")
    nals = []
    for j, (pos, sc_len) in enumerate(starts):
        end = starts[j+1][0] if j+1 < len(starts) else n
        nal = data[pos+sc_len:end].rstrip(b"\x00")
        if nal:
            nals.append(nal)
    return nals

def group_by_aud(nals: list[bytes]) -> list[bytes]:
    """Group NALs by Access Unit Delimiter (NAL type 9). Requires AUDs."""
    groups: list[list[bytes]] = []
    current: list[bytes] = []
    saw_aud = False
    for nal in nals:
        typ = nal[0] & 0x1F
        if typ == 9:
            saw_aud = True
            if current:
                groups.append(current)
            current = [nal]
        else:
            if not current:
                current = [nal]
            else:
                current.append(nal)
    if current:
        groups.append(current)
    if not saw_aud:
        raise ValueError(
            "Input has no AUD NALs (type 9). Re-encode with x264 aud=1; "
            "see the ffmpeg command printed by --help."
        )
    return [b"".join(b"\x00\x00\x00\x01" + nal for nal in group) for group in groups]

def read_template(path: Path) -> tuple[bytes, bytes]:
    """
    Template expected to be a complete captured MIRR message:
      0..3 total length (LE), 4..7 'RRIM', 16..19 'TADV',
      28..31 payload length (LE), payload from byte 32.
    """
    b = path.read_bytes()
    if len(b) < 32 or b[4:8] != b"RRIM" or b[16:20] != b"TADV":
        raise ValueError("Template is not a captured MIRR/VDAT message (expected RRIM at 4 and TADV at 16).")
    return b[:32], b[32:]

def make_message(header: bytes, payload: bytes, timestamp: int) -> bytes:
    # Preserve unknown protocol fields from the captured template.
    h = bytearray(header)
    total = 32 + len(payload)
    struct.pack_into("<I", h, 0, total)
    # Offset 20 is treated as a timestamp based on the capture; this is unverified.
    struct.pack_into("<I", h, 20, timestamp & 0xFFFFFFFF)
    struct.pack_into("<I", h, 28, len(payload))
    return bytes(h) + payload

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create experimental Sage MIRR/VDAT messages from Annex-B H.264.",
        epilog=(
            "Prepare an input with AUD markers, for example:\n"
            "  ffmpeg -i input.mp4 -an -c:v libx264 -preset ultrafast "
            "-tune zerolatency -x264-params aud=1:keyint=30 -f h264 input_aud.h264\n"
            "This script only packetizes; it does not perform the Sage handshake or USB transmission."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input", type=Path, help="raw Annex-B H.264 file")
    ap.add_argument("--template", required=True, type=Path,
                    help="captured MIRR frame message, e.g. out_00019_mirr.bin")
    ap.add_argument("-o", "--output", type=Path, default=Path("sage_candidate_stream.bin"),
                    help="output concatenated candidate messages (default: sage_candidate_stream.bin)")
    ap.add_argument("--timestamp-step", type=int, default=333333,
                    help="increment for the 32-bit timestamp field (default: 333333; unverified units)")
    ap.add_argument("--index", type=Path, default=Path("sage_candidate_index.csv"),
                    help="CSV index output")
    args = ap.parse_args()

    try:
        nals = split_annexb(args.input.read_bytes())
        frames = group_by_aud(nals)
        header, _ = read_template(args.template)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Keep the timestamp from the template and advance it for each access unit.
    base_ts = struct.unpack_from("<I", header, 20)[0]
    out = bytearray()
    rows = ["frame_index,offset,total_length,payload_length,timestamp,nal_count"]
    offset = 0
    for i, frame in enumerate(frames):
        msg = make_message(header, frame, base_ts + i * args.timestamp_step)
        out.extend(msg)
        nal_count = sum(1 for nal in split_annexb(frame))
        rows.append(f"{i},{offset},{len(msg)},{len(frame)},{(base_ts + i * args.timestamp_step) & 0xffffffff},{nal_count}")
        offset += len(msg)

    args.output.write_bytes(out)
    args.index.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"NAL units: {len(nals)}")
    print(f"Access units grouped by AUD: {len(frames)}")
    print(f"Output: {args.output} ({len(out)} bytes)")
    print(f"Index: {args.index}")
    print("WARNING: candidate framing only; handshake, field semantics, timing and device acceptance are not validated.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
