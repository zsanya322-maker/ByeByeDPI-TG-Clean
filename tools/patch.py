#!/usr/bin/env python3
"""Apply ByeByeDPI-TG-Clean v0.1.0 modifications to a pinned ByeByeDPI checkout."""

from __future__ import annotations

import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
UPSTREAM_COMMIT = "f2eb4a06ad918a34df66fc5b104377f21eb74039"
TG_REF_COMMIT = "9e908c0c6c5e8c7fd526ed0877243eb74c7dccfb"
TG_RAW = f"https://raw.githubusercontent.com/EwenLoy/ByeByeDPI-x-tg/{TG_REF_COMMIT}/app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws"
TG_DIR = ROOT / "app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def download(name: str) -> str:
    url = f"{TG_RAW}/{name}"
    print(f"Downloading pinned Telegram source: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "ByeByeDPI-TG-Clean-CI/0.1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


SECURE_RAW_WEBSOCKET = r'''package io.github.romanvht.byedpi.ewenloy.tgws

import android.util.Base64
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.ByteArrayOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.security.MessageDigest
import java.security.SecureRandom
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLSocket

class EwenloyWsHandshakeException(
    val statusCode: Int,
    val statusLine: String,
    val location: String? = null,
) : IllegalStateException(statusLine) {
    val isRedirect: Boolean
        get() = statusCode in setOf(301, 302, 303, 307, 308)
}

class EwenloyRawWebSocket private constructor(
    private val socket: SSLSocket,
    private val input: BufferedInputStream,
    private val output: BufferedOutputStream,
) {
    @Volatile private var closed = false

    fun sendBinary(payload: ByteArray, offset: Int = 0, length: Int = payload.size) {
        val frame = buildFrame(0x2, payload, offset, length, true)
        output.write(frame)
        output.flush()
    }

    fun receive(): ByteArray? {
        val message = ByteArrayOutputStream(65536)
        var fragmentOpen = false

        while (!closed) {
            val hdr1 = input.read()
            if (hdr1 < 0) return null
            val hdr2 = input.read()
            if (hdr2 < 0) return null
            val fin = (hdr1 and 0x80) != 0
            val opcode = hdr1 and 0x0f
            val masked = (hdr2 and 0x80) != 0
            var len = (hdr2 and 0x7f).toLong()
            if (len == 126L) {
                val e = readExact(2)
                len = (((e[0].toInt() and 0xff) shl 8) or (e[1].toInt() and 0xff)).toLong()
            } else if (len == 127L) {
                len = readExact(8).fold(0L) { acc, b -> (acc shl 8) or (b.toLong() and 0xff) }
            }
            if (len < 0 || len > MAX_WS_FRAME_PAYLOAD) {
                close()
                return null
            }
            if (fragmentOpen && message.size().toLong() + len > MAX_WS_MESSAGE_BYTES) {
                close()
                return null
            }
            val mask = if (masked) readExact(4) else null
            val payload = readExact(len.toInt())
            if (masked && mask != null) {
                for (i in payload.indices) {
                    payload[i] = (payload[i].toInt() xor mask[i % 4].toInt()).toByte()
                }
            }
            when (opcode) {
                0x8 -> {
                    runCatching {
                        val closeReply = buildFrame(0x8, payload, 0, minOf(2, payload.size), true)
                        output.write(closeReply)
                        output.flush()
                    }
                    return null
                }
                0x9 -> {
                    val pong = buildFrame(0xA, payload, 0, payload.size, true)
                    output.write(pong)
                    output.flush()
                }
                0xA -> Unit
                0x0 -> {
                    if (!fragmentOpen) continue
                    message.write(payload)
                    if (fin) {
                        fragmentOpen = false
                        return message.toByteArray()
                    }
                }
                0x1, 0x2 -> {
                    if (fragmentOpen) message.reset()
                    fragmentOpen = !fin
                    message.reset()
                    message.write(payload)
                    if (fin) {
                        fragmentOpen = false
                        return message.toByteArray()
                    }
                }
                else -> continue
            }
        }
        return null
    }

    fun sendBatch(parts: List<ByteArray>) {
        for (part in parts) output.write(buildFrame(0x2, part, 0, part.size, true))
        output.flush()
    }

    fun close() {
        if (closed) return
        closed = true
        runCatching { socket.close() }
    }

    private fun readExact(count: Int): ByteArray {
        val buf = ByteArray(count)
        var off = 0
        while (off < count) {
            val n = input.read(buf, off, count - off)
            if (n <= 0) throw IllegalStateException("Unexpected EOF")
            off += n
        }
        return buf
    }

    companion object {
        private const val MAX_WS_FRAME_PAYLOAD = 16L * 1024L * 1024L
        private const val MAX_WS_MESSAGE_BYTES = 64L * 1024L * 1024L
        private const val WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

        fun connect(ip: String, domain: String, timeoutMs: Int = 10000): EwenloyRawWebSocket {
            val plain = Socket()
            try {
                plain.connect(InetSocketAddress(ip, 443), timeoutMs)
                plain.soTimeout = timeoutMs

                val ssl = HttpsURLConnection.getDefaultSSLSocketFactory()
                    .createSocket(plain, domain, 443, true) as SSLSocket
                ssl.soTimeout = timeoutMs
                val params = ssl.sslParameters
                params.endpointIdentificationAlgorithm = "HTTPS"
                ssl.sslParameters = params
                ssl.startHandshake()

                // Endpoint identification above performs normal CA-chain + hostname validation.
                // Keep an explicit hostname check as defense in depth for vendor TLS stacks.
                if (!HttpsURLConnection.getDefaultHostnameVerifier().verify(domain, ssl.session)) {
                    throw IllegalStateException("TLS hostname verification failed for $domain")
                }

                val input = BufferedInputStream(ssl.getInputStream(), 65536)
                val output = BufferedOutputStream(ssl.getOutputStream(), 65536)
                val random = ByteArray(16).also { SecureRandom().nextBytes(it) }
                val wsKey = Base64.encodeToString(random, Base64.NO_WRAP)
                val expectedAccept = websocketAccept(wsKey)

                val req = buildString {
                    append("GET /apiws HTTP/1.1\r\n")
                    append("Host: $domain\r\n")
                    append("Upgrade: websocket\r\n")
                    append("Connection: Upgrade\r\n")
                    append("Sec-WebSocket-Key: $wsKey\r\n")
                    append("Sec-WebSocket-Version: 13\r\n")
                    append("Sec-WebSocket-Protocol: binary\r\n")
                    append("Origin: https://web.telegram.org\r\n")
                    append("User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) ")
                    append("AppleWebKit/537.36 (KHTML, like Gecko) ")
                    append("Chrome/131.0.0.0 Safari/537.36\r\n\r\n")
                }
                output.write(req.toByteArray(Charsets.US_ASCII))
                output.flush()

                val firstLine = readHeaderLine(input)
                val code = firstLine.split(" ").getOrNull(1)?.toIntOrNull() ?: 0
                val headers = linkedMapOf<String, String>()
                while (true) {
                    val line = readHeaderLine(input)
                    if (line.isEmpty()) break
                    val idx = line.indexOf(':')
                    if (idx > 0) {
                        val key = line.substring(0, idx).trim().lowercase()
                        val value = line.substring(idx + 1).trim()
                        headers[key] = value
                    }
                }

                if (code != 101) {
                    throw EwenloyWsHandshakeException(code, firstLine, headers["location"])
                }
                if (!headers["upgrade"].orEmpty().equals("websocket", ignoreCase = true)) {
                    throw IllegalStateException("Invalid WebSocket Upgrade header")
                }
                val connectionTokens = headers["connection"].orEmpty()
                    .split(',').map { it.trim() }
                if (connectionTokens.none { it.equals("upgrade", ignoreCase = true) }) {
                    throw IllegalStateException("Invalid WebSocket Connection header")
                }
                if (headers["sec-websocket-accept"] != expectedAccept) {
                    throw IllegalStateException("Invalid Sec-WebSocket-Accept")
                }

                ssl.soTimeout = 0
                return EwenloyRawWebSocket(ssl, input, output)
            } catch (t: Throwable) {
                runCatching { plain.close() }
                throw t
            }
        }

        private fun websocketAccept(key: String): String {
            val digest = MessageDigest.getInstance("SHA-1")
                .digest((key + WS_GUID).toByteArray(Charsets.US_ASCII))
            return Base64.encodeToString(digest, Base64.NO_WRAP)
        }

        private fun readHeaderLine(input: BufferedInputStream): String {
            val sb = StringBuilder(128)
            var prev = -1
            while (true) {
                val b = input.read()
                if (b < 0) break
                sb.append(b.toChar())
                if (prev == '\r'.code && b == '\n'.code) break
                prev = b
                if (sb.length > 16_384) throw IllegalStateException("HTTP header line too large")
            }
            return sb.toString().trim()
        }

        private fun buildFrame(opcode: Int, payload: ByteArray, offset: Int, length: Int, mask: Boolean): ByteArray {
            val headerSize = 2 + when {
                length < 126 -> 0
                length <= 0xffff -> 2
                else -> 8
            } + if (mask) 4 else 0
            val frame = ByteArray(headerSize + length)
            var pos = 0
            frame[pos++] = (0x80 or opcode).toByte()
            val maskBit = if (mask) 0x80 else 0
            when {
                length < 126 -> frame[pos++] = (maskBit or length).toByte()
                length <= 0xffff -> {
                    frame[pos++] = (maskBit or 126).toByte()
                    frame[pos++] = ((length shr 8) and 0xff).toByte()
                    frame[pos++] = (length and 0xff).toByte()
                }
                else -> {
                    frame[pos++] = (maskBit or 127).toByte()
                    for (i in 7 downTo 0) frame[pos++] = ((length.toLong() shr (i * 8)) and 0xff).toByte()
                }
            }
            if (!mask) {
                System.arraycopy(payload, offset, frame, pos, length)
                return frame
            }
            val maskKey = ByteArray(4).also { SecureRandom().nextBytes(it) }
            System.arraycopy(maskKey, 0, frame, pos, 4)
            pos += 4
            for (i in 0 until length) {
                frame[pos + i] = (payload[offset + i].toInt() xor maskKey[i % 4].toInt()).toByte()
            }
            return frame
        }
    }
}
'''

TG_CONTROLLER = r'''package io.github.romanvht.byedpi.ewenloy.tgws

import android.util.Log

/** Minimal v0.1.0 lifecycle wrapper. The local endpoint is loopback-only. */
class TgCleanController {
    @Volatile private var server: EwenloyTgWsProxyServer? = null

    @Synchronized
    fun start() {
        if (server?.isRunning() == true) return
        val candidate = EwenloyTgWsProxyServer(
            host = "127.0.0.1",
            listenPort = PORT,
            onRouteStatus = { mode -> Log.d(TAG, "Telegram route=$mode") },
            onStats = { stats -> Log.d(TAG, stats) },
        )
        candidate.start()
        if (!candidate.isRunning()) {
            candidate.stop()
            throw IllegalStateException("Unable to bind Telegram SOCKS5 on 127.0.0.1:$PORT")
        }
        server = candidate
        candidate.warmup()
        Log.i(TAG, "Telegram SOCKS5 started on 127.0.0.1:$PORT")
    }

    @Synchronized
    fun stop() {
        val current = server ?: return
        server = null
        runCatching { current.stop() }
            .onFailure { Log.w(TAG, "Telegram SOCKS5 stop failed", it) }
    }

    companion object {
        const val PORT = 1082
        private const val TAG = "TgCleanController"
    }
}
'''


def patch_gradle() -> None:
    path = ROOT / "app/build.gradle.kts"
    text = read(path)
    text = replace_once(
        text,
        'val abis = setOf("armeabi-v7a", "arm64-v8a", "x86", "x86_64")',
        'val abis = setOf("arm64-v8a")',
        "ABI list",
    )
    text = replace_once(
        text,
        'applicationId = "io.github.romanvht.byedpi"',
        'applicationId = "io.github.zsanya322maker.byedpitgclean"',
        "applicationId",
    )
    text = replace_once(text, 'versionCode = 1780', 'versionCode = 178001', "versionCode")
    text = replace_once(text, 'versionName = "1.7.8"', 'versionName = "1.7.8-tgclean-0.1.0"', "versionName")
    write(path, text)


def patch_strings() -> None:
    path = ROOT / "app/src/main/res/values/strings.xml"
    text = read(path)
    text = replace_once(text, '<string name="app_name">ByeByeDPI</string>', '<string name="app_name">ByeByeDPI TG Clean</string>', "app_name")
    text = replace_once(text, '<string name="notification_title">ByeByeDPI</string>', '<string name="notification_title">ByeByeDPI TG Clean</string>', "notification_title")
    write(path, text)


def patch_vpn_service() -> None:
    path = ROOT / "app/src/main/java/io/github/romanvht/byedpi/services/ByeDpiVpnService.kt"
    text = read(path)
    text = replace_once(
        text,
        'import io.github.romanvht.byedpi.data.*\n',
        'import io.github.romanvht.byedpi.data.*\nimport io.github.romanvht.byedpi.ewenloy.tgws.TgCleanController\n',
        "VPN import",
    )
    text = replace_once(
        text,
        '    private val byeDpiProxy = ByeDpiProxy()\n',
        '    private val byeDpiProxy = ByeDpiProxy()\n    private val tgClean = TgCleanController()\n',
        "VPN controller field",
    )
    text = replace_once(
        text,
        '        tunFd?.close()\n',
        '        tgClean.stop()\n        tunFd?.close()\n',
        "VPN onDestroy",
    )
    text = replace_once(
        text,
        '                startProxy()\n                startTun2Socks()\n',
        '                startProxy()\n                tgClean.start()\n                startTun2Socks()\n',
        "VPN start",
    )
    text = replace_once(
        text,
        '                    stopProxy()\n                    stopTun2Socks()\n',
        '                    tgClean.stop()\n                    stopProxy()\n                    stopTun2Socks()\n',
        "VPN stop",
    )
    # If startup fails after TG started, stop() normally cleans it. This catch makes cleanup explicit.
    text = replace_once(
        text,
        '            updateStatus(ServiceStatus.Failed)\n            stop()\n',
        '            tgClean.stop()\n            updateStatus(ServiceStatus.Failed)\n            stop()\n',
        "VPN failed-start cleanup",
    )
    write(path, text)


def patch_proxy_service() -> None:
    path = ROOT / "app/src/main/java/io/github/romanvht/byedpi/services/ByeDpiProxyService.kt"
    text = read(path)
    text = replace_once(
        text,
        'import io.github.romanvht.byedpi.data.*\n',
        'import io.github.romanvht.byedpi.data.*\nimport io.github.romanvht.byedpi.ewenloy.tgws.TgCleanController\n',
        "Proxy import",
    )
    text = replace_once(
        text,
        '    private var proxy = ByeDpiProxy()\n',
        '    private var proxy = ByeDpiProxy()\n    private val tgClean = TgCleanController()\n',
        "Proxy controller field",
    )
    text = replace_once(
        text,
        '                startProxy()\n                updateStatus(ServiceStatus.Connected)\n',
        '                startProxy()\n                tgClean.start()\n                updateStatus(ServiceStatus.Connected)\n',
        "Proxy start",
    )
    text = replace_once(
        text,
        '            updateStatus(ServiceStatus.Failed)\n            stop()\n',
        '            tgClean.stop()\n            updateStatus(ServiceStatus.Failed)\n            stop()\n',
        "Proxy failed-start cleanup",
    )
    text = replace_once(
        text,
        '            withContext(Dispatchers.IO) {\n                stopProxy()\n            }\n',
        '            withContext(Dispatchers.IO) {\n                tgClean.stop()\n                stopProxy()\n            }\n',
        "Proxy stop",
    )
    # Ensure Android destruction also tears down the loopback listener.
    marker = '    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {'
    if marker not in text:
        raise RuntimeError("Proxy onStartCommand marker not found")
    text = text.replace(
        marker,
        '    override fun onDestroy() {\n        tgClean.stop()\n        super.onDestroy()\n    }\n\n' + marker,
        1,
    )
    write(path, text)


def sanity_checks() -> None:
    gradle = read(ROOT / "app/build.gradle.kts")
    if 'applicationId = "io.github.zsanya322maker.byedpitgclean"' not in gradle:
        raise RuntimeError("application ID patch missing")
    raw = read(TG_DIR / "EwenloyRawWebSocket.kt")
    forbidden = ["trustAll", "X509TrustManager", "checkServerTrusted", "java.util.Base64"]
    for token in forbidden:
        if token in raw:
            raise RuntimeError(f"unsafe/incompatible token remains in RawWebSocket: {token}")
    required = ["endpointIdentificationAlgorithm = \"HTTPS\"", "getDefaultHostnameVerifier", "sec-websocket-accept"]
    for token in required:
        if token not in raw:
            raise RuntimeError(f"security invariant missing: {token}")


def main() -> None:
    expected = ROOT / "app/build.gradle.kts"
    if not expected.exists():
        raise SystemExit(f"Not a ByeByeDPI checkout: {ROOT}")

    TG_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("EwenloyTgWsProxyServer.kt", "EwenloyMtProtoParser.kt", "EwenloyTelegramRanges.kt"):
        write(TG_DIR / name, download(name))
    write(TG_DIR / "EwenloyRawWebSocket.kt", SECURE_RAW_WEBSOCKET)
    write(TG_DIR / "TgCleanController.kt", TG_CONTROLLER)

    patch_gradle()
    patch_strings()
    patch_vpn_service()
    patch_proxy_service()
    sanity_checks()
    print("ByeByeDPI-TG-Clean v0.1.0 patch applied successfully")


if __name__ == "__main__":
    main()
