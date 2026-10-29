#!/usr/bin/env python3
"""Analyze Linux usbmon (DLT_USB_LINUX_MMAPPED / linktype 220) PCAPNG captures.

For the Sage Mirroring Suit capture this script:
  * extracts bulk OUT submissions (endpoint 0x01) and bulk IN completions (0x81)
  * reconstructs directional byte streams
  * parses length-prefixed protocol messages (little-endian uint32 length + 4-byte tag)
  * writes CSV/JSON reports and raw message payloads
  * searches message bodies for Annex-B H.264 NAL start codes

Only Python's standard library is required. It does not alter the capture.
"""
from __future__ import annotations
import argparse
import csv
import json
import struct
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PCAPNG_SHB = 0x0A0D0D0A
PCAPNG_IDB = 0x00000001
PCAPNG_EPB = 0x00000006
LINKTYPE_USB_LINUX_MMAPPED = 220
USBMON_HEADER_LEN = 64

@dataclass
class UsbPacket:
    timestamp: float
    event: str
    transfer_type: int
    endpoint: int
    device: int
    bus: int
    status: int
    urb_len: int
    data_len: int
    payload: bytes

@dataclass
class Message:
    direction: str
    index: int
    offset: int
    declared_length: int
    wire_tag: str
    tag: str
    data: bytes
    complete: bool
    note: str = ""


def blocks(path: Path):
    """Yield (block_type, body) for little- or big-endian PCAPNG files."""
    with path.open('rb') as f:
        first = f.read(12)
        if len(first) < 12 or first[:4] != b'\x0a\x0d\x0d\x0a':
            raise ValueError('Not a PCAPNG file (missing Section Header Block)')
        bom = first[8:12]
        if bom == b'\x4d\x3c\x2b\x1a':
            endian = '<'
        elif bom == b'\x1a\x2b\x3c\x4d':
            endian = '>'
        else:
            raise ValueError('Unknown PCAPNG byte-order magic')
        total_len = struct.unpack(endian + 'I', first[4:8])[0]
        rest = f.read(total_len - 12)
        if len(rest) != total_len - 12:
            raise ValueError('Truncated Section Header Block')
        yield PCAPNG_SHB, first[8:] + rest[:-4]
        while True:
            h = f.read(8)
            if not h:
                break
            if len(h) != 8:
                raise ValueError('Truncated PCAPNG block header')
            block_type, block_len = struct.unpack(endian + 'II', h)
            if block_len < 12:
                raise ValueError(f'Invalid PCAPNG block length: {block_len}')
            body_and_trailer = f.read(block_len - 8)
            if len(body_and_trailer) != block_len - 8:
                raise ValueError('Truncated PCAPNG block')
            body = body_and_trailer[:-4]
            yield block_type, body


def read_capture(path: Path):
    interfaces = []
    packets = []
    endian = '<'
    # Determine endian from SHB BOM before interpreting other blocks.
    with path.open('rb') as f:
        shb = f.read(12)
    if shb[8:12] == b'\x1a\x2b\x3c\x4d':
        endian = '>'
    for typ, body in blocks(path):
        if typ == PCAPNG_IDB:
            if len(body) < 8:
                continue
            linktype = struct.unpack(endian + 'H', body[:2])[0]
            snaplen = struct.unpack(endian + 'I', body[4:8])[0]
            # PCAPNG default timestamp resolution is microseconds (10^-6).
            ts_resolution = 1e-6
            pos = 8
            while pos + 4 <= len(body):
                code, olen = struct.unpack(endian + 'HH', body[pos:pos+4])
                pos += 4
                if code == 0:
                    break
                value = body[pos:pos+olen]
                if code == 9 and value:  # if_tsresol
                    v = value[0]
                    ts_resolution = (2.0 ** -(v & 0x7f)) if v & 0x80 else (10.0 ** -v)
                pos += (olen + 3) & ~3
            interfaces.append({'linktype': linktype, 'snaplen': snaplen, 'ts_resolution': ts_resolution})
        elif typ == PCAPNG_EPB:
            if len(body) < 20:
                continue
            iid, tsh, tsl, caplen, origlen = struct.unpack(endian + 'IIIII', body[:20])
            if iid >= len(interfaces):
                continue
            packet_data = body[20:20+caplen]
            info = interfaces[iid]
            if info['linktype'] != LINKTYPE_USB_LINUX_MMAPPED:
                continue
            if len(packet_data) < USBMON_HEADER_LEN:
                continue
            # Linux usbmon mmap header: id, event, xfer, ep, dev, bus, flags,
            # timestamp sec/usec, status, URB len, data len, setup, etc.
            evb = packet_data[8:9]
            try:
                event = evb.decode('ascii')
            except UnicodeDecodeError:
                continue
            if event not in ('S', 'C', 'E'):
                continue
            xfer = packet_data[9]
            ep = packet_data[10]
            dev = packet_data[11]
            bus = struct.unpack(endian + 'H', packet_data[12:14])[0]
            sec = struct.unpack(endian + 'q', packet_data[16:24])[0]
            usec = struct.unpack(endian + 'I', packet_data[24:28])[0]
            status = struct.unpack(endian + 'i', packet_data[28:32])[0]
            urblen = struct.unpack(endian + 'I', packet_data[32:36])[0]
            datalen = struct.unpack(endian + 'I', packet_data[36:40])[0]
            payload = packet_data[USBMON_HEADER_LEN:]
            # usbmon submit for OUT contains outgoing data; completion for IN contains incoming data.
            packets.append(UsbPacket(sec + usec * 1e-6, event, xfer, ep, dev, bus,
                                     status, urblen, datalen, payload))
    if not interfaces:
        raise ValueError('No PCAPNG interface blocks found')
    if not any(i['linktype'] == LINKTYPE_USB_LINUX_MMAPPED for i in interfaces):
        types = ', '.join(str(i['linktype']) for i in interfaces)
        raise ValueError(f'Capture linktype is not Linux usbmon (220); found: {types}')
    return interfaces, packets


def fourcc(raw: bytes) -> str:
    """Display protocol FourCC in the order used by the app's little-endian tags."""
    s = raw.decode('ascii', errors='replace')
    # Wire strings in this protocol appear byte-reversed: EVIL -> LIVE, RRIM -> MIRR.
    return s[::-1] if len(s) == 4 and all(32 <= ord(c) <= 126 for c in s) else s


def parse_stream(data: bytes, direction: str, max_message: int = 64 * 1024 * 1024):
    """Parse [uint32 LE length][4-byte tag] framed messages, preserving unknown frames.

    A zero-length 4-byte word is treated as a standalone zero/keepalive marker.
    If a length is implausible, scan forward for a plausible frame boundary instead
    of silently discarding the rest of the stream.
    """
    out = []
    pos = 0
    idx = 0
    known_wire_tags = {b'EVIL', b'CNYS', b'RRIM', b'_PPA', b'RATS', b'TADV'}
    while pos + 4 <= len(data):
        start = pos
        length = struct.unpack_from('<I', data, pos)[0]
        if length == 0:
            out.append(Message(direction, idx, pos, 0, '', 'ZERO/KEEPALIVE', data[pos:pos+4], True,
                               'four zero bytes; framing interpretation is heuristic'))
            pos += 4; idx += 1
            continue
        plausible = 8 <= length <= max_message
        if plausible and pos + length <= len(data):
            tagbytes = data[pos+4:pos+8]
            # Accept known tags or a printable tag; the length prefix is primary evidence.
            printable = len(tagbytes) == 4 and all(32 <= c <= 126 for c in tagbytes)
            if printable:
                wire = tagbytes.decode('ascii', errors='replace')
                out.append(Message(direction, idx, pos, length, wire, fourcc(tagbytes), data[pos:pos+length], True))
                pos += length; idx += 1
                continue
        # Resync: find next plausible length + printable FourCC. Bound search for speed.
        found = None
        scan_end = min(len(data) - 8, pos + 1024 * 1024)
        for candidate in range(pos + 1, scan_end + 1):
            if candidate + 8 > len(data): break
            n = struct.unpack_from('<I', data, candidate)[0]
            if n < 8 or n > max_message or candidate + n > len(data):
                continue
            tag = data[candidate+4:candidate+8]
            if tag in known_wire_tags or all(32 <= c <= 126 for c in tag):
                found = candidate
                break
        if found is not None:
            out.append(Message(direction, idx, start, found-start, '', 'UNFRAMED', data[start:found], True,
                               'bytes skipped while resynchronizing; inspect manually'))
            pos = found; idx += 1
        else:
            remaining = data[pos:]
            out.append(Message(direction, idx, pos, len(remaining), '', 'TRAILING/UNPARSED', remaining, False,
                               'no plausible frame boundary found'))
            break
    if pos < len(data) and len(data) - pos < 4:
        out.append(Message(direction, idx, pos, len(data)-pos, '', 'TRAILING/UNPARSED', data[pos:], False,
                           'fewer than four trailing bytes'))
    return out


def find_h264_nals(blob: bytes):
    """Return basic Annex-B NAL offsets/types; this is a heuristic, not full H.264 parsing."""
    hits = []
    i = 0
    while i < len(blob) - 4:
        if blob[i:i+4] == b'\x00\x00\x00\x01':
            off = i + 4
        elif blob[i:i+3] == b'\x00\x00\x01':
            off = i + 3
        else:
            i += 1; continue
        if off < len(blob):
            b = blob[off]
            nal_type = b & 0x1f
            names = {1:'non-IDR slice', 5:'IDR/keyframe slice', 6:'SEI', 7:'SPS', 8:'PPS', 9:'AUD'}
            hits.append({'offset': i, 'nal_type': nal_type, 'nal_name': names.get(nal_type, 'other')})
            i = off + 1
        else:
            i += 1
    return hits


def main():
    ap = argparse.ArgumentParser(description='Reconstruct Sage Mirroring Suit USB protocol messages from a Linux usbmon PCAPNG.')
    ap.add_argument('capture', type=Path, help='input .pcapng captured on usbmon')
    ap.add_argument('-o', '--outdir', type=Path, default=Path('sage_usb_analysis'), help='output directory (default: sage_usb_analysis)')
    ap.add_argument('--bus', type=int, default=None, help='USB bus number (default: auto-select busiest bus/device)')
    ap.add_argument('--device', type=int, default=None, help='USB device address (default: auto-select busiest bus/device)')
    ap.add_argument('--endpoint-out', type=lambda x: int(x, 0), default=0x01, help='bulk OUT endpoint (default 0x01)')
    ap.add_argument('--endpoint-in', type=lambda x: int(x, 0), default=0x81, help='bulk IN endpoint (default 0x81)')
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    interfaces, packets = read_capture(args.capture)
    usb = [p for p in packets if p.transfer_type == 3]
    if args.bus is None or args.device is None:
        counts = Counter((p.bus, p.device) for p in usb)
        if not counts:
            raise SystemExit('No bulk USB events found in this capture.')
        auto_bus, auto_dev = counts.most_common(1)[0][0]
        bus = auto_bus if args.bus is None else args.bus
        dev = auto_dev if args.device is None else args.device
    else:
        bus, dev = args.bus, args.device
    selected = [p for p in usb if p.bus == bus and p.device == dev]

    # Linux usbmon event S = submission, C = completion. OUT payload appears on S;
    # IN payload appears on C. Keep packet order from the capture.
    out_parts = [p.payload for p in selected if p.event == 'S' and p.endpoint == args.endpoint_out and p.payload]
    in_parts = [p.payload for p in selected if p.event == 'C' and p.endpoint == args.endpoint_in and p.payload]
    out_stream = b''.join(out_parts)
    in_stream = b''.join(in_parts)
    (args.outdir / 'bulk_out_stream.bin').write_bytes(out_stream)
    (args.outdir / 'bulk_in_stream.bin').write_bytes(in_stream)
    out_msgs = parse_stream(out_stream, 'OUT')
    in_msgs = parse_stream(in_stream, 'IN')
    messages = out_msgs + in_msgs
    messages.sort(key=lambda m: (m.direction, m.index))

    msg_dir = args.outdir / 'messages'
    msg_dir.mkdir(exist_ok=True)
    rows = []
    for m in messages:
        filename = f'{m.direction.lower()}_{m.index:05d}_{m.tag.lower().replace("/", "_")}.bin'
        (msg_dir / filename).write_bytes(m.data)
        h264 = find_h264_nals(m.data)
        rows.append({
            'direction': m.direction, 'index': m.index, 'offset': m.offset,
            'declared_length': m.declared_length, 'actual_length': len(m.data),
            'wire_tag': m.wire_tag, 'tag_interpreted': m.tag,
            'complete': m.complete, 'note': m.note, 'h264_nal_count': len(h264),
            'h264_nal_types': ','.join(str(x['nal_type']) for x in h264[:30]),
            'file': f'messages/{filename}'
        })
    with (args.outdir / 'messages.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ['direction'])
        w.writeheader(); w.writerows(rows)
    (args.outdir / 'messages.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')

    tag_counts = Counter((m.direction, m.tag) for m in messages)
    report = {
        'capture': str(args.capture), 'interfaces': interfaces,
        'usbmon_packets': len(packets), 'bulk_events': len(usb),
        'selected_bus': bus, 'selected_device_address': dev,
        'selected_bulk_events': len(selected),
        'out_endpoint': hex(args.endpoint_out), 'in_endpoint': hex(args.endpoint_in),
        'out_stream_bytes': len(out_stream), 'in_stream_bytes': len(in_stream),
        'out_message_count': len(out_msgs), 'in_message_count': len(in_msgs),
        'tag_counts': {f'{direction}:{tag}': count for (direction, tag), count in sorted(tag_counts.items())},
        'notes': [
            'Tag interpretation reverses the four printable wire bytes (e.g. EVIL -> LIVE); validate against APK code.',
            'Message framing is heuristic: little-endian 32-bit total length followed by a four-byte tag.',
            'USB audio isochronous endpoint 0x03 is intentionally not reconstructed by this script.',
            'H.264 start-code detection is heuristic and does not decode video.'
        ]
    }
    (args.outdir / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

    print(f'Capture: {args.capture}')
    print(f'USB bus/device selected: {bus}/{dev}')
    print(f'Bulk events for selected device: {len(selected)}')
    print(f'Bulk OUT stream: {len(out_stream):,} bytes; parsed messages: {len(out_msgs)}')
    print(f'Bulk IN stream:  {len(in_stream):,} bytes; parsed messages: {len(in_msgs)}')
    print('Message tags:')
    for (direction, tag), count in sorted(tag_counts.items()):
        print(f'  {direction:>3} {tag:<20} {count}')
    print(f'\nWrote analysis to: {args.outdir.resolve()}')
    print('Start with report.json and messages.csv. Inspect individual binary messages under messages/.')

if __name__ == '__main__':
    main()
