# App archive

This directory contains archived app packages for the Mirroring devices:

- `android/` — Android APKs and an XAPK from multiple versions.
- `ios/` — archived iOS IPA packages.

These are historical copies, not necessarily the latest releases. Check the
package and version before installing.

## Download sources

| Source | URL | Notes |
| --- | --- | --- |
| App website | <https://app2.mirror.sageres.com/> | Website recorded during research. |
| Latest Android package | <https://svc2.onebitplay.com/mirror_app/product_files/androids/latest> | A moving endpoint; it may redirect to a different file. |
| Android download path | <http://mirror.onebitplay.com/mirror.dl/android/Mirror/Mirror-release-v1.1.15497.apk> | Previously observed redirect target for version 1.1.15497. |
| Object storage | <https://mirror-cn.oss-cn-shenzhen.aliyuncs.com/mirror.dl/android/Mirror/Mirror-release-v1.1.15497.apk> | Direct URL recorded for the same version. |
| Product specification | <https://gamestore.fr.sageres.com:8342/onebit/specification.html> | Specification page referenced by the app website. |

On 2026-10-28, the `latest` endpoint returned an HTTP 302 redirect to the
version 1.1.15497 download path above. This observation may no longer be
current.

## Package observations

- Archived iOS filenames use the bundle identifier
  `com.sagetech.mirror`. The original notes also report a different identifier,
  `com.sagete.mirrors`, for a later package; verify the package metadata before
  relying on that observation.
- The original notes report that version 1.1.15498 does not use static
  libraries. Treat this as an observation about that archived build, not a
  guarantee about other releases.

## Capture note

The original download capture used verbose `curl` output. The material finding
is the redirect recorded above; the full TLS and transfer trace is omitted
because it is transient and does not describe the archived packages.
