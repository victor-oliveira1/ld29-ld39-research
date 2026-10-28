# Video modes

This document records the video options exposed by the app and encoder
configuration samples collected from Android devices. Values are observations
from the tested devices and may vary with app, firmware, phone, or Android
version.

## App options

| Option | Available values | Effect |
| --- | --- | --- |
| Mirroring mode | Theatre Mode, Game Mode, Smooth Mode | Selects a streaming profile. |
| Picture quality | Smooth, SD, HD, UHD | Selects a bitrate profile. |
| Output resolution | 1280x720@60p, 1920x1080@60p, self-adaptation | Sets or adapts the display output resolution. |

## Recorded profile values

The following values were recorded for LD29 and LD39 profiles. Bitrate values
are shown in megabits per second (Mbps).

| Mirroring mode | Picture quality | Resolution | Frame rate (fps) | Bitrate (Mbps) |
| --- | --- | --- | --- | --- |
| Smooth Mode | Smooth | 1024x576 | 60 | 3 |
| Smooth Mode | SD | 1024x576 | 60 | 5 |
| Smooth Mode | HD | 1024x576 | 60 | 7 |
| Smooth Mode | UHD | 1024x576 | 60 | 10 |
| Game Mode | Smooth | 1280x736 | 55 | 8 |
| Game Mode | SD | 1280x736 | 55 | 15 |
| Game Mode | HD | 1280x736 | 55 | 20 |
| Game Mode | UHD | 1280x736 | 55 | 20 |
| Theatre Mode | Smooth | 1600x928 | 35 | 4 |
| Theatre Mode | SD | 1600x928 | 35 | 6 |
| Theatre Mode | HD | 1600x928 | 35 | 8 |
| Theatre Mode | UHD | 1600x928 | 35 | 12 |

## Behavior notes

| Topic | Information |
| --- | --- |
| Device compatibility | The LD29 and LD39 were observed using the same profile values listed above. |
| Mode or quality change | In the tested setup, changing the mirroring mode or picture quality required disconnecting and reconnecting the cable. |
| Output resolution change | In the tested setup, changing output resolution did not require reconnecting the cable. |

Encoder logs below are examples, not guaranteed output dimensions for every
device. Their reported width and height can differ from the profile table
because the encoder configuration depends on the phone and Android version.

## Encoder log samples

### Smooth Mode / UHD — Lenovo Vibe K6 Note, Android 7
```
[OMX.qcom.video.encoder.avc] configure, AMessage : AMessage(what = 'conf', target = 34) = {
  string mime = "video/avc"
  int32_t frame-rate = 60
  int32_t capture-rate = 60
  int32_t latency = 0
  int32_t color-format = 2130708361
  int32_t height = 1024
  int32_t width = 576
  int32_t bitrate = 10000000
  float max-fps-to-encoder = 60.000000
  int32_t priority = 0
  int32_t i-frame-interval = 30
  int32_t encoder = 1
}
```

### Game Mode / HD — Lenovo Vibe K6 Note, Android 7
```
[OMX.qcom.video.encoder.avc] configure, AMessage : AMessage(what = 'conf', target = 7) = {
  string mime = "video/avc"
  int32_t frame-rate = 55
  int32_t capture-rate = 55
  int32_t latency = 0
  int32_t color-format = 2130708361
  int32_t height = 1280
  int32_t width = 736
  int32_t bitrate = 20000000
  float max-fps-to-encoder = 55.000000
  int32_t priority = 0
  int32_t i-frame-interval = 30
  int32_t encoder = 1
}
```

### Theatre Mode / UHD — Poco X8 Pro Max, Android 16
```
[mId: 0] [video-debug-enc] configure: ClientFormat: AMessage(what = 0x00000000) = {
  int32_t capture-rate = 35
  float max-fps-to-encoder = 35.000000
  int32_t color-format = 2130708361
  int32_t i-frame-interval = 30
  string mime = "video/avc"
  int32_t latency = 0
  int32_t width = 768
  int32_t bitrate = 12000000
  int32_t priority = 0
  int32_t frame-rate = 35
  int32_t height = 1600
}
```

### Game Mode / UHD — Poco X8 Pro Max, Android 16
```
[mId: 1] [video-debug-enc] configure: ClientFormat: AMessage(what = 0x00000000) = {
  int32_t capture-rate = 55
  float max-fps-to-encoder = 55.000000
  int32_t color-format = 2130708361
  int32_t i-frame-interval = 30
  string mime = "video/avc"
  int32_t latency = 0
  int32_t width = 608
  int32_t bitrate = 30000000
  int32_t priority = 0
  int32_t frame-rate = 55
  int32_t height = 1280
}
```