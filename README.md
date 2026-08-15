# ByeByeDPI-TG-Clean

Android build based on **ByeByeDPI 1.7.8** with a local Telegram MTProto-over-WebSocket SOCKS5 transport.

## Current version: v0.1.1 Security Hardening

- Base: `romanvht/ByeByeDPI` tag `v.1.7.8`, commit `f2eb4a06ad918a34df66fc5b104377f21eb74039`.
- Telegram transport reference: `EwenLoy/ByeByeDPI-x-tg`, commit `9e908c0c6c5e8c7fd526ed0877243eb74c7dccfb` (logic derived from Flowseal `tg-ws-proxy`).
- Application ID: `io.github.zsanya322maker.byedpitgclean`.
- Version name: `1.7.8-tgclean-0.1.1`.
- ARM64-only (`arm64-v8a`).
- Telegram local SOCKS5 endpoint: `127.0.0.1:1082`.
- Telegram transport starts together with ByeByeDPI in VPN or Proxy mode.

### Security hardening in v0.1.1

- Replaces the reference Telegram trust-all TLS implementation with normal Android/system CA-chain validation and HTTPS hostname verification.
- Validates WebSocket `Sec-WebSocket-Accept`.
- Rejects invalid/unsupported WebSocket RSV bits, masked server frames, invalid control frames and invalid fragmentation sequences; response header count is bounded.
- The local `127.0.0.1:1082` SOCKS server is Telegram-only: non-Telegram destinations are rejected instead of acting as a generic local SOCKS proxy.
- SOCKS5 method negotiation verifies that the client actually offered no-auth before selecting it.
- Removes `MANAGE_EXTERNAL_STORAGE`, `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE` and legacy external-storage mode. File import/export uses Android's system document picker (SAF).
- Removes `QUERY_ALL_PACKAGES`. Per-app selection uses least-privilege package visibility for normal launcher and Android TV launcher apps through manifest `<queries>` declarations instead of visibility into every installed package.
- Disables Android app-data backup for this fork (`allowBackup=false`).
- `SettingsActivity` is not exported.
- Exported shortcut control via `ToggleActivity` is guarded by a per-install random token so arbitrary third-party intents cannot start/stop the service or replace the strategy.
- Service status broadcasts are package-local.
- GitHub Actions used by the build are pinned to exact commit SHAs.

## Telegram setup

While ByeByeDPI-TG-Clean is running, configure Telegram proxy as:

- Type: SOCKS5
- Server: `127.0.0.1`
- Port: `1082`
- Username/password: empty

The current version deliberately keeps Telegram UI minimal so transport behavior can be validated independently before adding richer controls.

## Build model

The repository does not vendor a stale full copy of ByeByeDPI. GitHub Actions checks out the exact pinned upstream source and submodules, then applies the project patches. `tools/patch.py` contains the original v0.1.0 integration, `tools/patch_v011.py` applies the main v0.1.1 security overlay, and `tools/patch_v011_final.py` applies the final least-privilege manifest overlay. CI builds and audits the resulting APK.

## Release signing identity

The persistent release private key is **not stored in this public repository**.

Expected release certificate SHA-256 fingerprint:

`0A:E5:E2:CF:5D:0C:08:B2:B1:CA:38:96:10:93:F0:AE:48:30:0D:5A:F1:A1:0F:3D:C1:E8:B2:AF:DD:78:E3:EE`

The v0.1.1 signed APK is verified with APK Signature Scheme v1, v2 and v3. Future release APKs intended as in-place updates must use this same signing identity (or a formally supported signing-key rotation lineage).

## Licenses and attribution

ByeByeDPI and ByeByeDPI-x-tg are GPL-3.0 projects. The Telegram WebSocket reference logic is attributed to Flowseal `tg-ws-proxy` (MIT). See `NOTICE.md`.

This is an experimental third-party modification and is not an official ByeByeDPI or Telegram release.
