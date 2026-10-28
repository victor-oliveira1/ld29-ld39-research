# Server assets

This directory contains JSON responses and request notes captured while
observing network activity from the Mirroring app. The captures include app
and device update metadata; they are snapshots, not live service data or a
complete protocol specification.

## Captured files

| File | Description |
| --- | --- |
| [`android_Mirror.json`](./android_Mirror.json) | Android app update metadata. |
| [`ios_Mirror.json`](./ios_Mirror.json) | iOS app update metadata. |
| [`dev-history.json`](./dev-history.json) | Device firmware history data. |
| [`dev-update.json`](./dev-update.json) | Device update catalog with model, version, download path, and hash fields. |

Firmware packages referenced by some metadata are archived separately in
[`../firmwares/`](../firmwares/).

## Observed service requests

The following endpoints were noted during app use:

| Purpose | Endpoint |
| --- | --- |
| Device firmware package | <http://mirror.onebitplay.com/mirror.dl/device/DM01/DM01_1.392.14012.gz> |
| Firmware history | <http://svc2.onebitplay.com/mirror_oss/mirror.fr/update/dev-history.json> |
| Device update catalog | <http://svc2.onebitplay.com/mirror_oss/mirror.fr/update/dev-update.json> |
| Android app metadata | <http://svc2.onebitplay.com/mirror_oss/mirror.fr/update/android_Mirror.json> |
| iOS app metadata | <http://svc2.onebitplay.com/mirror_oss/mirror.fr/update/ios_Mirror.json> |
| Device suitability check | <http://svc2.onebitplay.com/mirror_admin/product_files/devices/suitable> |

An example request recorded for the suitability check was:

```sh
curl -X POST \
  'http://svc2.onebitplay.com/mirror_admin/product_files/devices/suitable?vid=1&pid=1281&productVersion=1.407.14506&phoneIMIE=0123456789&platform=android&appName=Mirror&appVersion=62'
```

`0123456789` is a placeholder from the capture, not a real device identifier.
Replace it only with an identifier you are authorized to use. Endpoint
availability, parameters, and responses may change.
