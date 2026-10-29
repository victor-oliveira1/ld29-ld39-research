#!/usr/bin/env python3
"""
Experimental sender for Sage Inc. Mirroring Suit USB protocol v2.

What is implemented from the decompiled app:
- PacketBuffer's 4-byte little-endian total-length prefix.
- ClientMessage20 MIRR channel, magic/value fields.
- MirrorCommand RATS (STAR request / response) and TADV (VDAT).
- StreamData: timestamp_ms, angle, payload_length, Annex-B H.264 access unit.
- UsbHostHelper bulk OUT writes in chunks of at most 0x4000 bytes.
- Responds to a received STAR request, then sends video access units.

This is reverse-engineering test software. The full USB/session negotiation may
still differ from your capture. Use only with your own device.
"""
from __future__ import annotations

import argparse
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    import usb.core
    import usb.util
    import usb.backend.libusb1
except ImportError:
    usb = None  # type: ignore

VID_DEFAULT = 0x18D1
PID_DEFAULT = 0x2D04
USB_CHUNK = 0x4000
USB_WRITE_LOCK = threading.Lock()
START4 = b"\x00\x00\x00\x01"
START3 = b"\x00\x00\x01"


def require_pyusb() -> None:
    if usb is None:
        raise SystemExit(
            "PyUSB não está instalado. Instale com: python3 -m pip install pyusb"
        )


def list_devices() -> int:
    require_pyusb()
    devices = list(usb.core.find(find_all=True) or [])
    if not devices:
        print("Nenhum dispositivo USB encontrado.")
        return 0
    for d in devices:
        try:
            product = usb.util.get_string(d, d.iProduct) if d.iProduct else ""
        except Exception:
            product = ""
        print(
            f"{d.idVendor:04x}:{d.idProduct:04x} "
            f"bus={getattr(d, 'bus', '?')} address={getattr(d, 'address', '?')} "
            f"{product or ''}"
        )
    return 0


def find_bulk_endpoints(dev, interface_number: int | None):
    cfg = dev.get_active_configuration()
    candidates = []
    for intf in cfg:
        if interface_number is not None and intf.bInterfaceNumber != interface_number:
            continue
        ep_in = None
        ep_out = None
        for ep in intf:
            if usb.util.endpoint_type(ep.bmAttributes) != usb.util.ENDPOINT_TYPE_BULK:
                continue
            direction = usb.util.endpoint_direction(ep.bEndpointAddress)
            if direction == usb.util.ENDPOINT_IN and ep_in is None:
                ep_in = ep
            elif direction == usb.util.ENDPOINT_OUT and ep_out is None:
                ep_out = ep
        if ep_in is not None and ep_out is not None:
            candidates.append((intf, ep_in, ep_out))
    if not candidates:
        raise RuntimeError(
            "Não encontrei uma interface com endpoints bulk IN e OUT. "
            "Use --list e confira a interface/endpoints no lsusb -v."
        )
    return candidates[0]


def open_usb(vid: int, pid: int, interface_number: int | None):
    require_pyusb()
    dev = usb.core.find(idVendor=vid, idProduct=pid)
    if dev is None:
        raise RuntimeError(
            f"Dispositivo {vid:04x}:{pid:04x} não encontrado. "
            "Confira o passthrough do emulador e rode --list."
        )
    try:
        dev.set_configuration()
    except usb.core.USBError:
        # It may already have the desired configuration.
        pass
    intf, ep_in, ep_out = find_bulk_endpoints(dev, interface_number)
    number = intf.bInterfaceNumber
    try:
        if dev.is_kernel_driver_active(number):
            dev.detach_kernel_driver(number)
    except (NotImplementedError, usb.core.USBError):
        pass
    usb.util.claim_interface(dev, number)
    print(
        f"USB conectado: {vid:04x}:{pid:04x}, interface {number}, "
        f"IN=0x{ep_in.bEndpointAddress:02x}, OUT=0x{ep_out.bEndpointAddress:02x}"
    )
    return dev, intf, ep_in, ep_out


def write_all(ep_out, data: bytes, timeout_ms: int = 1000) -> None:
    # UsbHostHelper.ioSend() breaks outgoing buffers into 0x4000-byte chunks.
    # Serialize writes because the heartbeat thread and video thread share EP OUT.
    with USB_WRITE_LOCK:
        for off in range(0, len(data), USB_CHUNK):
            chunk = data[off:off + USB_CHUNK]
            written = ep_out.write(chunk, timeout=timeout_ms)
            if written != len(chunk):
                raise RuntimeError(
                    f"USB write incompleto: {written} de {len(chunk)} bytes "
                    f"(offset {off})"
                )


def heartbeat_worker(ep_in, ep_out, stop_event: threading.Event) -> None:
    """Mirror UsbHostHelper.run(): every 4-byte IN transfer gets 4 zero bytes OUT."""
    print("Heartbeat USB ativo (resposta 00 00 00 00 para leituras de 4 bytes).")
    while not stop_event.is_set():
        try:
            data = bytes(ep_in.read(USB_CHUNK, timeout=500))
        except usb.core.USBTimeoutError:
            continue
        except usb.core.USBError as exc:
            if not stop_event.is_set():
                print(f"Heartbeat: erro de leitura USB: {exc}", file=sys.stderr)
            continue
        if len(data) == 4:
            try:
                write_all(ep_out, b"\x00\x00\x00\x00")
            except Exception as exc:
                if not stop_event.is_set():
                    print(f"Heartbeat: falha enviando resposta: {exc}", file=sys.stderr)
            else:
                print("\nHeartbeat respondido.", flush=True)
        elif data:
            # The original app passes non-4-byte reads to CtrlCenter.dataDeliver().
            # Log these for diagnostics; full inbound command handling is not implemented.
            print(
                f"\nUSB IN durante vídeo: {len(data)} bytes; "
                f"início={data[:16].hex(' ')} (não interpretado)",
                file=sys.stderr,
                flush=True,
            )


def packet_buffer(body: bytes) -> bytes:
    """PacketBuffer.array(): a little-endian total size, including these 4 bytes."""
    return struct.pack("<I", len(body) + 4) + body


def channel_header(ssid_word: int, rng: random.Random) -> bytes:
    # ClientMessage20: magic = static upper 16 bits OR random lower 16 bits.
    magic = ((ssid_word & 0xFFFF) << 16) | rng.randrange(0x10000)
    return b"RRIM" + struct.pack("<II", magic, 0)


def make_vdat(
    access_unit: bytes,
    *,
    ssid_word: int,
    angle: int,
    timestamp_ms: int,
    rng: random.Random,
) -> bytes:
    command = (
        b"TADV"
        + struct.pack(
            "<III",
            timestamp_ms & 0xFFFFFFFF,
            angle & 0xFFFFFFFF,
            len(access_unit),
        )
        + access_unit
    )
    return packet_buffer(channel_header(ssid_word, rng) + command)


def make_sync_response(*, ssid_word: int, peer_magic: int, rng: random.Random) -> bytes:
    # handlerChannelData(SyncChannel): responds with version=2, softVer=0,
    # vid=1, pid=1 and value=the peer's magic.
    body = (
        b"CNYS"
        + struct.pack("<II", ((ssid_word & 0xFFFF) << 16) | rng.randrange(0x10000), peer_magic)
        + struct.pack("<HHHHI", 2, 0, 1, 1, 0)
    )
    return packet_buffer(body)


def make_start_response(
    *,
    ssid_word: int,
    width: int,
    height: int,
    bitrate: int,
    rng: random.Random,
) -> bytes:
    # RspStartMirror.addBuffer() order, from smali:
    # videoWidth:S, videoHeight:S, videoBitrate:I,
    # screenWidth:S, screenHeight:S, phoneType:I, haveBframe:I,
    # audioFormat:B, audioChannel:B, audioBits:S, audioBitrate:I.
    response = (
        b"RATS"
        + struct.pack(
            "<HHIHHIIBBH I".replace(" ", ""),
            width, height, bitrate,
            width, height,
            0,  # phoneType; isMI9() false
            0,  # haveBframe
            0,  # audioFormat
            2,  # audioChannel
            16, # audioBits
            48000,  # audioBitrate (0xbb80)
        )
    )
    return packet_buffer(channel_header(ssid_word, rng) + response)


def split_annexb_nals(data: bytes) -> list[bytes]:
    starts: list[tuple[int, int]] = []
    i = 0
    while i < len(data) - 2:
        if data[i:i + 4] == START4:
            starts.append((i, 4))
            i += 4
        elif data[i:i + 3] == START3:
            starts.append((i, 3))
            i += 3
        else:
            i += 1
    if not starts:
        raise ValueError("O arquivo não contém start codes H.264 Annex-B.")
    result = []
    for n, (pos, _size) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(data)
        if end > pos:
            result.append(data[pos:end])
    return result


def nal_type(nal: bytes) -> int:
    if nal.startswith(START4):
        off = 4
    elif nal.startswith(START3):
        off = 3
    else:
        return -1
    return (nal[off] & 0x1F) if len(nal) > off else -1


def group_access_units(data: bytes) -> list[bytes]:
    nals = split_annexb_nals(data)
    if not any(nal_type(n) == 9 for n in nals):
        raise ValueError(
            "O H.264 não tem NAL AUD. Converta o vídeo usando este programa "
            "(ffmpeg gera AUD automaticamente) ou reencode com x264 aud=1."
        )
    units: list[bytes] = []
    current: list[bytes] = []
    prefix: list[bytes] = []
    seen_aud = False
    for nal in nals:
        if nal_type(nal) == 9:
            if current:
                units.append(b"".join(current))
                current = []
            if not seen_aud and prefix:
                current.extend(prefix)
                prefix = []
            seen_aud = True
            current.append(nal)
        elif not seen_aud:
            prefix.append(nal)
        else:
            current.append(nal)
    if current:
        units.append(b"".join(current))
    if not units:
        raise ValueError("Não consegui separar access units do H.264.")
    # Prefix NALs before the first AUD (if any) belong with the first access unit.
    if prefix:
        units[0] = b"".join(prefix) + units[0]
    return units


def transcode_to_h264(
    source: Path, width: int, height: int, fps: float, bitrate: int, dest: Path
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg não encontrado. Instale com: sudo apt install ffmpeg"
        )
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    )
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), "-an", "-vf", vf, "-r", str(fps),
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-b:v", str(bitrate), "-maxrate", str(bitrate),
        "-bufsize", str(bitrate * 2),
        "-x264-params", "aud=1:keyint=30:repeat-headers=1",
        "-f", "h264", str(dest),
    ]
    print("Convertendo vídeo para H.264 Annex-B com AUD/SPS/PPS...")
    subprocess.run(cmd, check=True)


def parse_star_request(buffer: bytes):
    """Find the command bytes RATS and parse width/height/bitrate/fps after them."""
    pos = buffer.find(b"RATS")
    if pos < 0 or len(buffer) < pos + 16:
        return None
    try:
        width, height, bitrate, fps = struct.unpack_from("<HHII", buffer, pos + 4)
    except struct.error:
        return None
    if not (1 <= width <= 8192 and 1 <= height <= 8192 and 1 <= bitrate <= 500_000_000):
        return None
    return width, height, bitrate, fps


def wait_for_star(ep_in, ep_out, timeout_s: float, *, ssid_word: int, rng: random.Random,
                  fallback_width: int, fallback_height: int, fallback_bitrate: int,
                  respond: bool):
    print(f"Aguardando solicitação STAR do dispositivo por até {timeout_s:.0f}s...")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            data = bytes(ep_in.read(USB_CHUNK, timeout=500))
        except usb.core.USBTimeoutError:
            continue
        except usb.core.USBError as exc:
            print(f"Leitura USB: {exc}", file=sys.stderr)
            continue
        if not data:
            continue
        # UsbHostHelper answers 4-byte heartbeat reads with four zero bytes.
        if len(data) == 4:
            try:
                write_all(ep_out, b"\x00\x00\x00\x00")
            except Exception as exc:
                print(f"Falha respondendo heartbeat: {exc}", file=sys.stderr)
            continue
        # Protocol-v2 sync channel token is sent byte-reversed as CNYS.
        # Find it even if the USB read includes a transport/padding prefix.
        sync_pos = data.find(b"CNYS")
        if sync_pos >= 0 and len(data) >= sync_pos + 12:
            peer_magic = struct.unpack_from("<I", data, sync_pos + 4)[0]
            sync_reply = make_sync_response(
                ssid_word=ssid_word, peer_magic=peer_magic, rng=rng
            )
            write_all(ep_out, sync_reply)
            print(
                f"SYNC recebido; resposta de protocolo 2 enviada "
                f"({len(sync_reply)} bytes, peer magic=0x{peer_magic:08x})."
            )
            continue
        request = parse_star_request(data)
        if request:
            width, height, bitrate, fps = request
            print(
                f"STAR recebido: {width}x{height}, bitrate={bitrate}, fps={fps}"
            )
            if respond:
                response = make_start_response(
                    ssid_word=ssid_word, width=fallback_width,
                    height=fallback_height, bitrate=fallback_bitrate, rng=rng
                )
                write_all(ep_out, response)
                print(f"Resposta RspStartMirror enviada ({len(response)} bytes).")
            return request
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Teste experimental de envio de vídeo H.264 para Sage Mirroring Suit via USB."
    )
    parser.add_argument("video", nargs="?", type=Path, help="arquivo de vídeo (MP4/MKV/etc.)")
    parser.add_argument("--list", action="store_true", help="listar dispositivos USB e sair")
    parser.add_argument("--vid", type=lambda s: int(s, 0), default=VID_DEFAULT)
    parser.add_argument("--pid", type=lambda s: int(s, 0), default=PID_DEFAULT)
    parser.add_argument("--interface", type=int, default=None)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=576)
    parser.add_argument("--fps", type=float, default=60.0)
    parser.add_argument("--bitrate", type=int, default=10_000_000)
    parser.add_argument("--angle", type=int, default=0)
    parser.add_argument("--ssid", type=lambda s: int(s, 0), default=None,
                        help="palavra alta de 16 bits para magic, ex. 0x6e00")
    parser.add_argument("--wait-start", type=float, default=10.0,
                        help="tempo aguardando STAR; 0 pula a espera")
    parser.add_argument("--no-start-response", action="store_true",
                        help="não enviar RspStartMirror ao receber STAR")
    parser.add_argument("--send-raw-h264", action="store_true",
                        help="tratar entrada como H.264 Annex-B já preparado, sem ffmpeg")
    parser.add_argument("--dry-run", action="store_true",
                        help="gerar e validar pacotes sem enviar por USB")
    parser.add_argument("--limit", type=int, default=0,
                        help="limitar a quantidade de access units enviadas (0=todas)")
    parser.add_argument("--pause", type=float, default=None,
                        help="intervalo entre access units; padrão 1/fps")
    args = parser.parse_args()

    if args.list:
        return list_devices()
    if args.video is None:
        parser.error("informe um arquivo de vídeo ou use --list")
    if args.width <= 0 or args.height <= 0 or args.fps <= 0 or args.bitrate <= 0:
        parser.error("width, height, fps e bitrate devem ser positivos")
    if args.ssid is not None and not 0 <= args.ssid <= 0xFFFF:
        parser.error("--ssid deve ser 0..0xffff, por exemplo 0x6e00")

    rng = random.Random()
    ssid_word = args.ssid if args.ssid is not None else rng.randrange(0x10000)
    pause = args.pause if args.pause is not None else 1.0 / args.fps

    try:
        with tempfile.TemporaryDirectory(prefix="sage_usb_") as td:
            h264_path = Path(td) / "video.h264"
            if args.send_raw_h264:
                h264_path.write_bytes(args.video.read_bytes())
            else:
                transcode_to_h264(
                    args.video, args.width, args.height, args.fps,
                    args.bitrate, h264_path
                )
            access_units = group_access_units(h264_path.read_bytes())
            if args.limit > 0:
                access_units = access_units[:args.limit]
            print(
                f"H.264 preparado: {len(access_units)} access units, "
                f"{sum(map(len, access_units))} bytes de payload; "
                f"magic prefix=0x{ssid_word:04x}"
            )

            if args.dry_run:
                first = make_vdat(
                    access_units[0], ssid_word=ssid_word, angle=args.angle,
                    timestamp_ms=int(time.time() * 1000), rng=rng
                )
                print(
                    f"DRY RUN: primeiro VDAT={len(first)} bytes; "
                    f"length prefix={struct.unpack_from('<I', first)[0]}"
                )
                print("Não foi aberto nem escrito nenhum dispositivo USB.")
                return 0

            dev, intf, ep_in, ep_out = open_usb(args.vid, args.pid, args.interface)
            try:
                if args.wait_start > 0:
                    request = wait_for_star(
                        ep_in, ep_out, args.wait_start,
                        ssid_word=ssid_word, rng=rng,
                        fallback_width=args.width, fallback_height=args.height,
                        fallback_bitrate=args.bitrate,
                        respond=not args.no_start_response
                    )
                    if request is None:
                        print(
                            "Nenhum STAR reconhecido. Não enviei vídeo automaticamente. "
                            "Se o dispositivo já estiver em sessão, tente --wait-start 0.",
                            file=sys.stderr
                        )
                        return 3

                # Keep reading EP IN throughout playback; the original app replies
                # with four zero bytes whenever bulkTransfer(IN) returns exactly 4.
                heartbeat_stop = threading.Event()
                heartbeat_thread = threading.Thread(
                    target=heartbeat_worker,
                    args=(ep_in, ep_out, heartbeat_stop),
                    name="sage-usb-heartbeat",
                    daemon=True,
                )
                heartbeat_thread.start()
                try:
                    ts0 = int(time.time() * 1000) & 0xFFFFFFFF
                    sent_bytes = 0
                    for i, au in enumerate(access_units):
                        timestamp = (ts0 + round(i * 1000.0 / args.fps)) & 0xFFFFFFFF
                        msg = make_vdat(
                            au, ssid_word=ssid_word, angle=args.angle,
                            timestamp_ms=timestamp, rng=rng
                        )
                        write_all(ep_out, msg)
                        sent_bytes += len(msg)
                        if i == 0 or (i + 1) % 30 == 0 or i + 1 == len(access_units):
                            print(
                                f"\rEnviados {i + 1}/{len(access_units)} access units "
                                f"({sent_bytes} bytes de mensagens)", end="", flush=True
                            )
                        time.sleep(max(0.0, pause))
                    print("\nEnvio concluído.")
                finally:
                    heartbeat_stop.set()
                    heartbeat_thread.join(timeout=1.5)
            finally:
                try:
                    usb.util.release_interface(dev, intf.bInterfaceNumber)
                except Exception:
                    pass
                usb.util.dispose_resources(dev)
    except subprocess.CalledProcessError as exc:
        print(f"ffmpeg falhou (código {exc.returncode}).", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError, usb.core.USBError if usb else RuntimeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
