# Notices and attribution

This repository builds a modified Android application based on **ByeByeDPI**.

## ByeByeDPI

- Upstream: `romanvht/ByeByeDPI`
- Pinned base for v0.1.0: `f2eb4a06ad918a34df66fc5b104377f21eb74039` (v1.7.8)
- License: GNU General Public License v3.0

The resulting modified work remains subject to GPL-3.0. The build workflow retrieves the exact upstream source and applies the modifications in this repository.

## Telegram WebSocket transport reference

The Android/Kotlin Telegram transport is derived from the implementation in `EwenLoy/ByeByeDPI-x-tg`, pinned at commit `9e908c0c6c5e8c7fd526ed0877243eb74c7dccfb`.

That implementation states that its Telegram WebSocket logic is aligned with Flowseal `tg-ws-proxy`.

## Flowseal tg-ws-proxy

MIT License

Copyright (c) 2026 Flowseal

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Source repository: `Flowseal/tg-ws-proxy`.

## Local modifications in ByeByeDPI-TG-Clean

For v0.1.0 the Telegram WebSocket transport is modified to:

- use the Android platform trust store instead of trusting every TLS certificate;
- verify the TLS hostname;
- verify the RFC 6455 `Sec-WebSocket-Accept` response;
- use Android-compatible Base64 APIs for minSdk 21;
- start a local SOCKS5 endpoint on `127.0.0.1:1082` together with the ByeByeDPI service;
- use a separate Android application ID so the test build can coexist with official ByeByeDPI.
