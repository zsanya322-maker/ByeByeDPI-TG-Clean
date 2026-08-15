# ByeByeDPI-TG-Clean

Experimental Android build based on **ByeByeDPI 1.7.8** with a local Telegram MTProto-over-WebSocket SOCKS5 transport.

## v0.1.0 scope

- Base: `romanvht/ByeByeDPI` tag `v.1.7.8`, commit `f2eb4a06ad918a34df66fc5b104377f21eb74039`.
- Telegram transport reference: `EwenLoy/ByeByeDPI-x-tg`, commit `9e908c0c6c5e8c7fd526ed0877243eb74c7dccfb` (logic derived from Flowseal `tg-ws-proxy`).
- Telegram local SOCKS5 endpoint: `127.0.0.1:1082`.
- Telegram transport starts together with ByeByeDPI in VPN or Proxy mode.
- TLS is changed from the reference implementation: platform CA validation + HTTPS hostname verification are enabled.
- WebSocket `Sec-WebSocket-Accept` is validated.
- No Telegram-specific Android permissions are added.
- First test build targets `arm64-v8a`.
- Separate application ID: `io.github.zsanya322maker.byedpitgclean`, so it can coexist with the official ByeByeDPI app.

## Telegram setup for v0.1.0

While ByeByeDPI-TG-Clean is running, configure Telegram proxy as:

- Type: SOCKS5
- Server: `127.0.0.1`
- Port: `1082`
- Username/password: empty

The first version deliberately has no extra Telegram UI switch: the goal is to verify the transport on the current ByeByeDPI 1.7.8 base before adding UI and automation.

## Build model

The repository does not vendor a stale copy of ByeByeDPI. GitHub Actions checks out the exact pinned upstream commits, applies `tools/patch.py`, and builds the APK. This keeps the modifications small and auditable.

## Signing

The first CI artifact is a test/debug-signed APK. A private persistent release key must not be committed to this public repository. After the transport is verified, release signing should use a private keystore stored outside the repository / in GitHub Actions secrets.

## Licenses and attribution

ByeByeDPI and ByeByeDPI-x-tg are GPL-3.0 projects. The Telegram WebSocket reference logic is attributed to Flowseal `tg-ws-proxy` (MIT). See `NOTICE.md`.

This is an experimental third-party modification and is not an official ByeByeDPI or Telegram release.
