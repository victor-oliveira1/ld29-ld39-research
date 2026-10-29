# Sage Mirroring Suit USB Protocol — Reverse Engineering Notes

**Project:** Sage Inc. Mirroring Suit  
**Protocol family:** `ClientMessage20`  
**Transport:** USB bulk transfer  
**Status:** Partially reverse-engineered  
**Implementation language:** Python

## Table of Contents

- [1. Overview](#1-overview)
- [2. Reverse Engineering Sources](#2-reverse-engineering-sources)
- [3. USB Transport](#3-usb-transport)
- [4. Protocol Architecture](#4-protocol-architecture)
- [5. Packet Framing](#5-packet-framing)
- [6. ClientMessage20 Header](#6-clientmessage20-header)
- [7. Channel Identifiers and Commands](#7-channel-identifiers-and-commands)
- [8. Session Initialization](#8-session-initialization)
- [9. Mirror Start Command](#9-mirror-start-command)
- [10. Mirror Start Response](#10-mirror-start-response)
- [11. Video Streaming](#11-video-streaming)
- [12. USB Heartbeat](#12-usb-heartbeat)
- [13. Audio Playback](#13-audio-playback)
- [14. Python Sender Architecture](#14-python-sender-architecture)
- [15. Reverse-Engineered Data Structures](#15-reverse-engineered-data-structures)
- [16. Implementation Considerations](#16-implementation-considerations)
- [17. Known Limitations and Open Questions](#17-known-limitations-and-open-questions)
- [18. Suggested Validation Workflow](#18-suggested-validation-workflow)
- [19. References to Decompiled Classes](#19-references-to-decompiled-classes)

## 1. Overview

This document describes the reverse-engineered USB communication protocol used by the Sage Inc. Mirroring Suit Android application.

The investigation focuses on understanding the Android application's USB transport, command framing, session initialization, mirror-start negotiation, H.264 video transmission, and heartbeat mechanism.

The goal is to implement a Python-based sender capable of transmitting video to a compatible receiver without requiring the original Android application's video-streaming implementation.

The findings are based on decompiled Android Smali code, USB packet captures, and observed application behavior.

> **Important:** This is an incomplete reverse-engineering effort. The structures described below are supported by the available source analysis or observations, but some framing details and protocol behaviors remain unverified.

### Main findings

- The Android application uses USB bulk endpoints for bidirectional communication.
- The analyzed device exposes USB vendor ID `0x18D1` and product ID `0x2D04`.
- The application contains a `ClientMessage20` message format.
- The message format includes a channel identifier, a magic/session-related value, and a command or channel-specific value.
- Video is transported as H.264 data wrapped in a `VDAT` stream command.
- The USB read loop responds to a specific four-byte read with four zero bytes.
- Audio can be played locally on the sending computer while video is transmitted over USB; this is a separate mechanism from USB audio streaming.

## 2. Reverse Engineering Sources

The following evidence was used during the investigation.

| Source | Purpose |
|---|---|
| Decompiled Android APK | Identify message classes, command serialization, and USB I/O |
| Smali source files | Inspect field order, primitive types, serialization, and read-loop behavior |
| USB packet capture (`.pcapng`) | Compare observed traffic with the decompiled implementation |
| Python sender implementation | Validate the proposed packet structures and transmission workflow |

The principal classes identified in the decompiled application are:

- `UsbHostHelper`
- `ClientMessage20`
- `ClientMessage20$SyncChannel`
- `ClientMessage20$MirrorChannel`
- `MirrorCommand$StartMirror`
- `MirrorCommand$RspStartMirror`
- `MirrorCommand$StreamData`
- `MirrorCommand$Type`
- `PacketBuffer`
- `CtrlCenter`

These classes form the basis of the protocol description in this document.

## 3. USB Transport

### 3.1 Device identification

The device observed during the investigation reports the following USB identifiers:

| Property | Value |
|---|---|
| Vendor ID | `0x18D1` |
| Product ID | `0x2D04` |
| Product description | Mirroring Suit |
| Manufacturer | Sage Inc. |

USB identifiers are useful for locating the device, but they do not establish the complete protocol or guarantee that every device with these identifiers behaves identically.

### 3.2 Bulk endpoints

The analyzed application uses the following endpoint addresses:

| Endpoint | Direction | Purpose |
|---|---|---|
| `0x81` | Device to host (IN) | Receive responses and other device-originated data |
| `0x01` | Host to device (OUT) | Send commands, video data, and heartbeat responses |

The Android helper reads endpoint `0x81` using a buffer of `0x4000` bytes (16,384 bytes) and a timeout of 1,000 milliseconds.

The endpoint read size is a buffer limit, not a guarantee that every protocol message occupies exactly 16,384 bytes.

Likewise, a USB bulk transfer boundary must not automatically be treated as an application-message boundary. The precise relationship between USB transfers and complete protocol packets must be verified against the receiver's framing behavior.

## 4. Protocol Architecture

The application uses multiple logical layers.

```text
Python Sender
    |
    +-- H.264 encoder / access-unit extraction
    |
    +-- MirrorCommand
    |       |
    |       +-- StartMirror
    |       +-- StreamData (VDAT)
    |
    +-- ClientMessage20
    |       |
    |       +-- Channel identifier
    |       +-- Magic/session-related field
    |       +-- Channel-specific value
    |
    +-- PacketBuffer
    |       |
    |       +-- Length prefix
    |
    +-- USB bulk OUT endpoint 0x01
                |
                v
        Mirroring Suit receiver

Device responses and heartbeat requests
                |
                v
        USB bulk IN endpoint 0x81
                |
                v
        USB receive loop
```

This diagram represents the logical structure inferred from the source. It does not imply that every layer has been completely reconstructed or that every message follows an identical layout.

## 5. Packet Framing

### 5.1 PacketBuffer

The decompiled `PacketBuffer` implementation prepends a four-byte little-endian length field to the serialized packet.

The length includes the four-byte prefix itself.

For a serialized payload of `N` bytes:

```text
Packet length = N + 4
```

The outer framing can therefore be represented as:

| Offset | Size | Description |
|---|---:|---|
| `0x00` | 4 bytes | Total packet length, little-endian |
| `0x04` | Variable | Serialized message |

For example, if the serialized message is 32 bytes long, the length prefix represents 36 bytes, or `0x24`.

The four-byte prefix would be:

```text
24 00 00 00
```

This is a format example, not a claim that a specific command always has a 32-byte payload.

### 5.2 Important framing caveat

USB packet captures may contain transport-level or protocol-level bytes surrounding the internal `ClientMessage20` header.

The complete relationship between the observed outer framing and the internal message has not yet been conclusively established for every captured packet.

Implementations should therefore distinguish:

1. USB transfer boundaries.
2. The `PacketBuffer` length prefix.
3. The internal `ClientMessage20` structure.
4. The command-specific payload.

Do not assume that a single USB read always returns exactly one complete application message.

## 6. ClientMessage20 Header

The `ClientMessage20` class uses a 12-byte internal header consisting of three four-byte fields.

| Offset | Size | Field | Description |
|---|---:|---|---|
| `0x00` | 4 bytes | Channel identifier | Selects a logical channel |
| `0x04` | 4 bytes | Magic/session-related value | Combines a random lower portion with a static SSID-derived upper portion |
| `0x08` | 4 bytes | Channel-specific value | Carries a channel value or command-related field |

The exact interpretation of the third field depends on the channel implementation and should not be assumed to be identical for all message types.

### 6.1 Magic value

The analyzed implementation constructs the magic value using a random lower 16-bit portion and a static SSID-derived upper 16-bit portion.

Conceptually:

```python
magic = (ssid_value << 16) | random_value
```

The actual Smali operations and masking should be followed when reproducing the implementation. The expression above illustrates the observed composition, not a complete specification of all possible values.

A compatible sender should not hard-code a captured magic value unless testing confirms that the receiver accepts a fixed value across sessions.

### 6.2 Byte order

The command and channel identifiers are serialized through integer-oriented code. Their byte representation can consequently differ from the human-readable identifier.

Examples observed during the investigation:

| Logical identifier | Observed byte representation |
|---|---|
| `MIRR` | `RRIM` |
| `STAR` | `RATS` |
| `VDAT` | `TADV` |

This is consistent with byte reversal when four-character identifiers are represented as integers and serialized little-endian.

**Implementation rule:** use the exact byte representation required by the serialization path. Do not reverse identifiers a second time without checking the actual output bytes.

## 7. Channel Identifiers and Commands

The investigation identified the following logical identifiers:

| Identifier | Observed representation | Interpretation |
|---|---|---|
| `MIRR` | `RRIM` | Mirroring channel |
| `STAR` | `RATS` | Mirror-start command |
| `VDAT` | `TADV` | Video stream data |

These identifiers are based on the decompiled implementation and observed packet bytes.

The full command registry has not been reconstructed. Other commands may exist for synchronization, negotiation, stopping the stream, errors, or device-specific features.

### 7.1 Sync and mirror channels

The decompiled application contains separate channel classes:

- `ClientMessage20$SyncChannel`
- `ClientMessage20$MirrorChannel`

This indicates a distinction between synchronization-related messages and mirroring messages.

The exact state machine, ordering requirements, and complete set of synchronization messages still require further validation.

## 8. Session Initialization

A typical mirroring session involves communication before video streaming begins.

The following sequence is a useful working model:

1. Open the USB device and claim the required interface.
2. Start reading device responses from endpoint `0x81`.
3. Perform the initialization and synchronization exchanges expected by the receiver.
4. Send the mirror-start request.
5. Wait for and parse the corresponding response.
6. Begin sending video stream data.
7. Continue processing device-originated messages and heartbeat requests while streaming.
8. Stop streaming and release USB resources.

This is a conceptual sequence, not a complete, proven specification of every required initialization message.

In particular, the precise initialization state machine and the complete response-handling behavior remain open investigation items.

## 9. Mirror Start Command

The decompiled class `MirrorCommand$StartMirror` parses four configuration fields.

| Field | Type | Meaning |
|---|---|---|
| Width | 16-bit integer (`short`) | Requested video width |
| Height | 16-bit integer (`short`) | Requested video height |
| Bitrate | 32-bit integer (`int`) | Requested video bitrate |
| FPS | 32-bit integer (`int`) | Requested frame rate |

An example configuration observed during the investigation was:

```text
Width:   1024
Height:  576
Bitrate: 10000000
FPS:     60
```

This corresponds to a requested resolution of 1024 × 576, a bitrate of 10,000,000 bits per second, and a frame rate of 60 frames per second.

The exact signedness, byte order, and offsets of these fields within the complete serialized command must follow the relevant serialization implementation. The field types above describe the parsed Java/Smali values.

### 9.1 Configuration considerations

The requested values should be compatible with the encoder output and the receiver's capabilities.

For example, requesting 60 FPS while sending only 30 FPS does not produce a genuine 60 FPS stream. Similarly, a bitrate setting in the start command does not itself encode or re-encode the video.

The sender should configure its encoder consistently with the negotiated mirror parameters.

## 10. Mirror Start Response

The decompiled application includes `MirrorCommand$RspStartMirror`, which parses the response to the mirror-start request.

The analysis also identified fields related to audio format or capabilities, including:

- Audio format
- Number of audio channels
- Audio bit depth
- Audio bitrate

The complete field layout, encoding values, and negotiation semantics have not yet been established sufficiently to document as a definitive wire-format specification.

These fields should not be interpreted as proof that audio must be transmitted over the same USB video channel.

A response may describe supported or negotiated audio parameters without establishing the transport mechanism used by the application in a particular operating mode.

## 11. Video Streaming

### 11.1 H.264 payload

The application uses `MirrorCommand$StreamData` to construct video stream messages.

The payload contains H.264 elementary-stream data. Captured payloads included Annex-B start codes and recognizable H.264 NAL units.

Examples of observed structures include:

```text
00 00 00 01 67 ...
00 00 00 01 68 ...
00 00 00 01 65 ...
```

Common H.264 interpretations are:

| Start-code sequence | NAL unit prefix | Typical meaning |
|---|---|---|
| `00 00 00 01 67` | `0x67` | SPS — Sequence Parameter Set |
| `00 00 00 01 68` | `0x68` | PPS — Picture Parameter Set |
| `00 00 00 01 65` | `0x65` | IDR picture slice |

These examples identify common H.264 NAL types. They do not imply that every video message must contain SPS, PPS, and IDR data together.

### 11.2 StreamData structure

The fields identified in `MirrorCommand$StreamData` are:

| Field | Size | Description |
|---|---:|---|
| Command identifier | 4 bytes | Logical `VDAT` command |
| Timestamp | 4 bytes | Timestamp value |
| Angle | 4 bytes | Video orientation/angle value |
| Payload length | 4 bytes | Length of the H.264 payload |
| H.264 payload | Variable | Encoded video data |

The logical structure is:

```text
+---------------------------+
| VDAT command identifier   | 4 bytes
+---------------------------+
| Timestamp                 | 4 bytes
+---------------------------+
| Angle                     | 4 bytes
+---------------------------+
| H.264 payload length      | 4 bytes
+---------------------------+
| H.264 data                | Variable
+---------------------------+
```

The actual command identifier appears as `TADV` in the observed byte representation.

The payload length describes the H.264 data within this command. It should not automatically be confused with the outer `PacketBuffer` length.

### 11.3 Timestamps

The timestamp is parsed as a 32-bit value. The complete timestamp unit and rollover behavior have not been conclusively established.

A sender should reproduce the units and progression used by the original application wherever possible. Assuming milliseconds based only on a plausible value is not sufficient to establish the protocol specification.

If the original application uses a 32-bit millisecond counter, it will eventually wrap around. A compatible implementation must account for that behavior if confirmed.

### 11.4 Angle

The angle is a 32-bit field associated with video orientation.

The complete set of valid values and their interpretation have not yet been confirmed.

Do not assume that it is always a degree value or that every receiver accepts arbitrary integers.

### 11.5 H.264 access units

A practical sender should preferably transmit complete H.264 access units rather than splitting the stream at arbitrary byte offsets.

The exact relationship between a `StreamData` message and an H.264 access unit should be verified against original application traffic.

The sender must also preserve the data required for decoding, including parameter sets and appropriate keyframes.

### 11.6 Encoding and transmission

A practical implementation may use FFmpeg to encode a source video into H.264, extract the resulting stream, construct `StreamData` messages, wrap them in the appropriate channel and packet framing, and transmit them through USB.

However, correct H.264 encoding alone does not guarantee compatibility. The command framing, packet lengths, session values, timing, and initialization sequence must also match the receiver's expectations.

## 12. USB Heartbeat

### 12.1 Observed behavior

The `UsbHostHelper.run()` method reads endpoint `0x81` into a buffer of `0x4000` bytes with a 1,000 ms timeout.

The analyzed implementation contains a special case:

- If a USB read returns exactly four bytes, the application sends four zero bytes through endpoint `0x01`.
- Otherwise, the received data is passed to `CtrlCenter.dataDeliver()`.

The heartbeat response is:

```text
00 00 00 00
```

### 12.2 Pseudocode

```python
data = usb_read(endpoint_in, size=0x4000, timeout=1000)

if len(data) == 4:
    usb_write(endpoint_out, b"\x00\x00\x00\x00")
else:
    deliver_to_protocol_parser(data)
```

This pseudocode represents the special case observed in the decompiled helper.

It does not establish that every four-byte message is universally a heartbeat in every protocol state. The observed behavior is that the original application treats any read returning exactly four bytes this way.

### 12.3 Concurrent heartbeat handling

Video transmission can occupy the main sending loop. The original application, however, continues reading USB input while mirroring is active.

A Python implementation should therefore ensure that heartbeat requests can be serviced during video transmission.

A separate reader thread is one possible implementation. It should:

- Read endpoint `0x81` continuously.
- Respond to the observed four-byte case with four zero bytes.
- Avoid concurrent writes that corrupt packet ordering.
- Coordinate access to the USB OUT endpoint with the video sender.
- Stop cleanly when the streaming session ends.

A single dedicated USB I/O loop can also work, provided it handles reads and writes without starving heartbeat responses.

### 12.4 USB write synchronization

If multiple threads write to endpoint `0x01`, access should be serialized with a lock or a dedicated writer queue.

This prevents simultaneous writes from interleaving at the application level and makes command ordering easier to reason about.

The lock must cover the complete write operation, including any partial-write handling needed by the USB library.

## 13. Audio Playback

### 13.1 Local audio as an alternative to USB audio

For the current Python sender, the simplest audio implementation is to play the source file's audio on the sending computer while sending its video stream through USB.

In this arrangement:

```text
                  +--------------------------+
Source media ---->| FFmpeg / video extraction|----> H.264 ----> USB OUT
                  |                          |
                  | Audio playback (ffplay)  |----> PulseAudio/PipeWire
                  +--------------------------+
```

This approach does not require reverse-engineering an audio packet format for the USB protocol.

It is a host-side playback strategy, not evidence that the Mirroring Suit receiver is receiving audio through USB.

### 13.2 PulseAudio and PipeWire

On Linux, `ffplay` can normally use the default audio output provided by PulseAudio or PipeWire's PulseAudio-compatible server.

For example:

```bash
ffplay -nodisp -autoexit -vn input.mp4
```

This plays the audio track without displaying the video.

The USB sender can run this process while independently transmitting the H.264 video.

### 13.3 Synchronization limitations

Starting local audio playback and USB video transmission at approximately the same time does not guarantee synchronization.

Potential sources of drift include:

- Encoder startup latency.
- USB transmission latency.
- Receiver buffering.
- Audio-device buffering.
- Different playback clocks.
- Video frame pacing.
- Seeking or variable-frame-rate source media.

For a basic demonstration, simultaneous playback may be sufficient. For accurate synchronization, the sender needs to measure the relative delay and implement an explicit timing strategy.

The current reverse-engineering findings do not establish a mechanism for synchronizing local PC audio with the receiver's displayed video.

### 13.4 When USB audio would be required

If the goal changes to transmitting audio to the receiver itself, rather than playing it locally, further protocol analysis is required.

The available `RspStartMirror` fields are not enough to establish the audio codec, packet framing, timestamps, channel mapping, or transmission command.

## 14. Python Sender Architecture

A robust sender can be organized into the following components:

### USB transport

Responsible for:

- Locating the correct device.
- Opening and claiming the interface.
- Sending complete framed messages.
- Reading device responses.
- Handling USB timeouts and errors.
- Serializing access to the OUT endpoint.

### Protocol serializer

Responsible for:

- Constructing `ClientMessage20` headers.
- Generating the required magic/session-related value.
- Serializing channel identifiers.
- Applying the outer length prefix.
- Encoding command-specific fields.

### Session controller

Responsible for:

- Initialization and synchronization.
- Sending the mirror-start request.
- Parsing the response.
- Starting and stopping video transmission.
- Handling errors and cleanup.

### Video pipeline

Responsible for:

- Reading the input media.
- Encoding or extracting H.264.
- Producing suitable access units.
- Constructing `StreamData` messages.
- Maintaining frame timing and timestamps.

### Heartbeat worker

Responsible for:

- Continuously reading endpoint `0x81`.
- Responding to the observed four-byte case.
- Routing other messages to the protocol parser.
- Coordinating writes with the main sender.

### Audio player

Responsible for:

- Starting local audio playback when enabled.
- Using the system's default audio output.
- Stopping playback when video transmission ends.
- Reporting playback failures.

These components should be separated so that protocol handling, USB transport, and media playback can be tested independently.

## 15. Reverse-Engineered Data Structures

The following diagrams summarize the currently identified structures.

### 15.1 Outer packet

```text
+-----------------------------+
| Total length (uint32 LE)    |
+-----------------------------+
| Serialized message          |
|                             |
+-----------------------------+
```

The total length includes the length prefix itself, according to the analyzed `PacketBuffer` implementation.

### 15.2 ClientMessage20

```text
+-----------------------------+
| Channel identifier (4 bytes)|
+-----------------------------+
| Magic/session value (4 B)   |
+-----------------------------+
| Channel-specific value (4 B)|
+-----------------------------+
| Channel/command payload     |
+-----------------------------+
```

The diagram describes the logical internal message. Exact command nesting and outer framing must be checked against the relevant serializer.

### 15.3 StreamData

```text
+-----------------------------+
| VDAT identifier (4 bytes)   |
+-----------------------------+
| Timestamp (4 bytes)         |
+-----------------------------+
| Angle (4 bytes)             |
+-----------------------------+
| H.264 length (4 bytes)      |
+-----------------------------+
| H.264 payload               |
+-----------------------------+
```

The actual on-wire command identifier observed in the captures is `TADV`.

## 16. Implementation Considerations

### 16.1 Endianness

Do not assume a single byte order for all protocol fields without checking the serializer.

The outer length is little-endian. The four-character command identifiers also exhibit byte reversal consistent with integer serialization.

The exact encoding of every command field must be verified individually.

### 16.2 Length validation

Before parsing a packet:

1. Check that the length prefix is present.
2. Decode the declared length.
3. Validate that the length is within reasonable limits.
4. Wait for or collect enough data to reconstruct the message.
5. Validate command-specific lengths before reading fields.
6. Reject malformed messages rather than reading beyond available bytes.

### 16.3 USB timeouts

A timeout does not necessarily indicate that the session has failed. The implementation should distinguish between normal periods without data, heartbeat behavior, disconnection, and actual USB errors.

### 16.4 Backpressure

If the sender transmits video faster than the receiver can consume it, latency may grow or the receiver may drop data.

Frame pacing should be consistent with the negotiated frame rate. The implementation should avoid treating a USB write timeout as proof that the receiver has decoded the preceding frame.

### 16.5 Cleanup

On normal completion or an exception:

- Stop local audio playback.
- Stop heartbeat and reader threads.
- Release claimed USB interfaces.
- Close the USB device.
- Remove temporary encoded media where appropriate.

## 17. Known Limitations and Open Questions

The following details remain unconfirmed.

| Item | Current status |
|---|---|
| USB device identifiers | Observed |
| IN and OUT endpoint addresses | Identified in the analyzed application |
| Four-byte heartbeat response | Identified in Smali |
| `PacketBuffer` four-byte length prefix | Identified in Smali |
| `ClientMessage20` header fields | Identified in Smali |
| Magic/session value construction | Partially identified |
| `MIRR`, `STAR`, and `VDAT` identifiers | Identified |
| Mirror-start parameter fields | Identified |
| `StreamData` field sequence | Identified |
| H.264 Annex-B payload | Observed |
| Complete outer framing in all states | Not fully verified |
| Complete initialization handshake | Not fully verified |
| All synchronization messages | Not fully verified |
| Timestamp units and rollover semantics | Not fully verified |
| Valid angle values | Not fully verified |
| Full start-response layout | Not fully documented |
| Audio transport protocol | Not established |
| Precise local audio/video synchronization | Not established |
| Device-specific error handling | Not fully documented |

The most important remaining work is to correlate each serialized message in the decompiled code with the exact byte sequence in a USB capture.

## 18. Suggested Validation Workflow

A reproducible validation process should capture and compare each protocol stage independently.

### Stage 1: Device discovery

- Confirm the device's vendor and product IDs.
- Identify the interface and endpoint descriptors.
- Verify that the host can claim the required interface.

### Stage 2: Initialization

- Capture the original application's startup sequence.
- Record each OUT transfer and corresponding IN response.
- Identify synchronization commands and session-related values.
- Verify the order in which commands must be sent.

### Stage 3: Mirror negotiation

- Capture the mirror-start request.
- Decode width, height, bitrate, and frame rate.
- Capture the response.
- Compare all fields with the Smali parser.

### Stage 4: Video stream

- Capture several `StreamData` messages.
- Verify the command identifier, timestamp, angle, payload length, and H.264 bytes.
- Check whether the length field matches the H.264 payload exactly.
- Verify how the outer length prefix relates to the internal message.
- Confirm whether messages contain complete access units or fragments.

### Stage 5: Heartbeat

- Capture device-originated four-byte reads.
- Confirm the original application responds with `00 00 00 00`.
- Verify that the Python implementation behaves the same way during sustained streaming.

### Stage 6: Audio

For local audio playback:

- Verify that the input media contains an audio track.
- Confirm `ffplay` uses the intended Linux audio output.
- Compare audio start time with the first displayed video frame.
- Measure drift over longer playback sessions.

For USB audio, repeat the capture analysis with the original application configured to transmit audio and identify the actual audio packets and transport.

### Stage 7: Robustness

- Test short and long videos.
- Test different resolutions and frame rates.
- Test USB timeouts and device disconnection.
- Verify cleanup after errors.
- Confirm that heartbeat handling continues while the video sender is busy.

## 19. References to Decompiled Classes

Use the following classes as the primary implementation references.

| Class | Investigation target |
|---|---|
| `UsbHostHelper.smali` | USB interface access, bulk reads, heartbeat response |
| `ClientMessage20.smali` | Internal message header and serialization |
| `ClientMessage20$SyncChannel.smali` | Synchronization channel |
| `ClientMessage20$MirrorChannel.smali` | Mirroring channel |
| `MirrorCommand$StartMirror.smali` | Mirror-start parameters |
| `MirrorCommand$RspStartMirror.smali` | Mirror-start response fields |
| `MirrorCommand$StreamData.smali` | Video stream command structure |
| `MirrorCommand$Type.smali` | Command identifiers |
| `PacketBuffer.smali` | Outer packet framing |
| `CtrlCenter.smali` | Message dispatch and video transmission flow |

---

## Disclaimer

This document describes an ongoing reverse-engineering effort based on the analyzed application code and observed USB traffic. It is not an official Sage Inc. protocol specification.

Fields, offsets, command semantics, and transport behavior should be treated as confirmed only to the extent supported by the decompiled implementation or repeatable packet-capture evidence. Unverified assumptions should be tested before being incorporated into a production implementation.
