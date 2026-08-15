#!/usr/bin/env python3
"""Apply TG Clean v0.2.0 TG Auto transport v2 after the v0.2.0 UX overlay."""
from __future__ import annotations
import pathlib, shutil, sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_v020_tgauto.py <ByeByeDPI checkout>')

root = pathlib.Path(sys.argv[1]).resolve()
repo = pathlib.Path(__file__).resolve().parents[1]
overlay = repo / 'overlay' / 'v020'


def read(rel: str) -> str:
    return (root / rel).read_text(encoding='utf-8')


def write(rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8', newline='\n')


def one(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)


def cp(name: str, rel: str) -> None:
    src = overlay / name
    dst = root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


# New TG Auto orchestration classes.
for name in (
    'TgCleanRuntime.kt',
    'TgTransportRoute.kt',
    'TgNetworkMonitor.kt',
    'TgDpiService.kt',
    'TgDpiProcessController.kt',
    'TgAutoEngine.kt',
    'TgCleanController.kt',
):
    cp(name, f'app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/{name}')

# Parent services now provide Context to the TG Auto controller.
for rel, owner in (
    ('app/src/main/java/io/github/romanvht/byedpi/services/ByeDpiProxyService.kt', 'ByeDpiProxyService'),
    ('app/src/main/java/io/github/romanvht/byedpi/services/ByeDpiVpnService.kt', 'ByeDpiVpnService'),
):
    t = read(rel)
    old = '                tgClean.start()\n'
    new = f'                tgClean.start(this@{owner})\n'
    t = one(t, old, new, f'{owner} TG Auto context start')
    write(rel, t)

# Secure RawWebSocket can optionally establish its TLS socket through a local SOCKS5 upstream.
raw_rel = 'app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/EwenloyRawWebSocket.kt'
t = read(raw_rel)
t = one(t, 'import java.net.InetSocketAddress\n', 'import java.net.InetAddress\nimport java.net.InetSocketAddress\n', 'RawWS InetAddress import')
t = one(
    t,
    '        fun connect(ip: String, domain: String, timeoutMs: Int = 10000): EwenloyRawWebSocket {\n'
    '            val plain = Socket()\n'
    '            try {\n'
    '                plain.connect(InetSocketAddress(ip, 443), timeoutMs)\n'
    '                plain.soTimeout = timeoutMs\n',
    '        fun connect(\n'
    '            ip: String,\n'
    '            domain: String,\n'
    '            timeoutMs: Int = 10000,\n'
    '            upstreamSocksPort: Int? = null,\n'
    '        ): EwenloyRawWebSocket {\n'
    '            val plain = openTransportSocket(ip, 443, timeoutMs, upstreamSocksPort)\n'
    '            try {\n'
    '                plain.soTimeout = timeoutMs\n',
    'RawWS optional SOCKS transport',
)
helper_anchor = '''        private fun websocketAccept(key: String): String {
'''
helper = '''        private fun openTransportSocket(
            targetIp: String,
            targetPort: Int,
            timeoutMs: Int,
            upstreamSocksPort: Int?,
        ): Socket {
            if (upstreamSocksPort == null) {
                return Socket().apply {
                    connect(InetSocketAddress(targetIp, targetPort), timeoutMs)
                }
            }

            val socket = Socket()
            try {
                socket.connect(InetSocketAddress("127.0.0.1", upstreamSocksPort), timeoutMs)
                socket.soTimeout = timeoutMs
                val input = socket.getInputStream()
                val output = socket.getOutputStream()

                output.write(byteArrayOf(0x05, 0x01, 0x00)); output.flush()
                val hello = readSocksExact(input, 2)
                if (hello[0].toInt() != 0x05 || hello[1].toInt() != 0x00) {
                    throw IllegalStateException("TG ByeDPI SOCKS5 auth negotiation failed")
                }

                val addr = InetAddress.getByName(targetIp).address
                if (addr.size != 4) throw IllegalStateException("TG ByeDPI route requires IPv4 gateway")
                val req = ByteArray(10)
                req[0] = 0x05; req[1] = 0x01; req[2] = 0x00; req[3] = 0x01
                System.arraycopy(addr, 0, req, 4, 4)
                req[8] = ((targetPort ushr 8) and 0xff).toByte()
                req[9] = (targetPort and 0xff).toByte()
                output.write(req); output.flush()

                val reply = readSocksExact(input, 4)
                if (reply[0].toInt() != 0x05 || reply[1].toInt() != 0x00) {
                    throw IllegalStateException("TG ByeDPI SOCKS5 CONNECT failed: ${reply[1].toInt() and 0xff}")
                }
                when (reply[3].toInt() and 0xff) {
                    0x01 -> readSocksExact(input, 4)
                    0x03 -> readSocksExact(input, input.read().also { if (it < 0) throw IllegalStateException("SOCKS EOF") })
                    0x04 -> readSocksExact(input, 16)
                    else -> throw IllegalStateException("TG ByeDPI SOCKS5 invalid ATYP")
                }
                readSocksExact(input, 2)
                return socket
            } catch (t: Throwable) {
                runCatching { socket.close() }
                throw t
            }
        }

        private fun readSocksExact(input: java.io.InputStream, count: Int): ByteArray {
            val data = ByteArray(count)
            var offset = 0
            while (offset < count) {
                val n = input.read(data, offset, count - offset)
                if (n <= 0) throw IllegalStateException("Unexpected SOCKS5 EOF")
                offset += n
            }
            return data
        }

'''
t = one(t, helper_anchor, helper + helper_anchor, 'RawWS SOCKS helper')
write(raw_rel, t)

# Route-aware WSS proxy: no direct TCP fallback, short-lived pools, network reset, endpoint racing.
server_rel = 'app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/EwenloyTgWsProxyServer.kt'
t = read(server_rel)
t = one(t, 'import java.util.concurrent.CopyOnWriteArrayList\n', 'import java.util.concurrent.Callable\nimport java.util.concurrent.CopyOnWriteArrayList\nimport java.util.concurrent.ExecutorCompletionService\n', 'server race imports')
t = one(
    t,
    '    private val listenPort: Int,\n    private val onRouteStatus: (String) -> Unit,\n',
    '    private val listenPort: Int,\n    private val routeProvider: () -> TgTransportRoute,\n    private val onRouteStatus: (String) -> Unit,\n',
    'server route provider constructor',
)

stop_anchor = '''    fun warmup() {
'''
reset_method = '''    fun resetTransportState() {
        wsPool.values.flatten().forEach { runCatching { it.ws.close() } }
        wsPool.clear()
        wsBlacklist.clear()
        lastMode = "idle"
    }

'''
t = one(t, stop_anchor, reset_method + stop_anchor, 'server reset transport')
t = one(t, '        for (dc in listOf(2, 4, 5)) {\n', '        for (dc in listOf(1, 2, 3, 4, 5)) {\n', 'warm all Telegram DCs')

# Capture selected TG Auto route before accepting the SOCKS request.
t = one(
    t,
    '        if (!EwenloyTelegramRanges.isTelegramIp(addr)) {\n'
    '            stats.blockedNonTelegram.incrementAndGet()\n'
    '            sendReply(output, 0x02)\n'
    '            return\n'
    '        }\n\n'
    '        sendReply(output, 0x00)\n',
    '        if (!EwenloyTelegramRanges.isTelegramIp(addr)) {\n'
    '            stats.blockedNonTelegram.incrementAndGet()\n'
    '            sendReply(output, 0x02)\n'
    '            return\n'
    '        }\n\n'
    '        val activeRoute = routeProvider()\n'
    '        if (!activeRoute.ready) {\n'
    '            sendReply(output, 0x01)\n'
    '            return\n'
    '        }\n\n'
    '        sendReply(output, 0x00)\n',
    'active TG Auto route gate',
)

# Fail closed instead of silently returning to blocked direct MTProto TCP.
for label, old in (
    ('no DC fallback', '''        if (finalDc == null) {
            stats.tcpFallback.incrementAndGet()
            lastMode = "direct"; onRouteStatus("direct")
            directTcpFallback(c, input, output, addr, port, init)
            return
        }
'''),
    ('no gateway fallback', '''        if (targetIp == null) {
            stats.tcpFallback.incrementAndGet()
            lastMode = "direct"; onRouteStatus("direct")
            directTcpFallback(c, input, output, addr, port, init)
            return
        }
'''),
):
    if label == 'no DC fallback':
        new = '''        if (finalDc == null) {
            stats.tcpFallback.incrementAndGet()
            lastMode = "no-dc"; onRouteStatus("no-dc")
            return
        }
'''
    else:
        new = '''        if (targetIp == null) {
            stats.tcpFallback.incrementAndGet()
            lastMode = "no-gateway"; onRouteStatus("no-gateway")
            return
        }
'''
    t = one(t, old, new, label)

t = one(
    t,
    '''        if (wsBlacklist.contains(dcKey)) {
            stats.tcpFallback.incrementAndGet()
            lastMode = "direct"; onRouteStatus("direct")
            directTcpFallback(c, input, output, addr, port, init)
            return
        }
''',
    '''        // v0.2.0 uses short retries instead of a long-lived route blacklist.
        wsBlacklist.remove(dcKey)
''',
    'remove long WS blacklist fallback',
)

t = one(
    t,
    '''        val pooled = wsPool[dcKey]?.removeFirstOrNull()?.let {
            if (System.currentTimeMillis() - it.createdAtMs <= WS_POOL_MAX_AGE) it.ws
            else { try { it.ws.close() } catch (_: Exception) {}; null }
        }

        var redirectCount = 0
        var allRedirects = true
        val ws = pooled ?: run {
            var result: EwenloyRawWebSocket? = null
            for (domain in domains) {
                if (!running.get()) break
                try {
                    result = EwenloyRawWebSocket.connect(targetIp, domain, wsTimeout)
                    allRedirects = false
                    break
                } catch (ex: EwenloyWsHandshakeException) {
                    stats.wsErrors.incrementAndGet()
                    if (ex.isRedirect) redirectCount++ else allRedirects = false
                } catch (_: Exception) {
                    stats.wsErrors.incrementAndGet()
                    allRedirects = false
                }
            }
            result
        }

        if (ws == null) {
            if (redirectCount > 0 && allRedirects) {
                wsBlacklist.add(dcKey)
            }
            stats.tcpFallback.incrementAndGet()
            lastMode = "direct"; onRouteStatus("direct")
            directTcpFallback(c, input, output, addr, port, init)
            return
        }

        stats.wsConnections.incrementAndGet()
        lastMode = "ws"; onRouteStatus("ws")
''',
    '''        val pooled = wsPool[dcKey]?.removeFirstOrNull()?.let {
            if (it.routeId == activeRoute.id && System.currentTimeMillis() - it.createdAtMs <= WS_POOL_MAX_AGE) it.ws
            else { try { it.ws.close() } catch (_: Exception) {}; null }
        }

        val ws = pooled ?: connectRace(targetIp, domains, wsTimeout, activeRoute)

        if (ws == null) {
            stats.tcpFallback.incrementAndGet()
            lastMode = "failed:${activeRoute.id}"; onRouteStatus(lastMode)
            return
        }

        stats.wsConnections.incrementAndGet()
        lastMode = "ws:${activeRoute.id}"; onRouteStatus(lastMode)
''',
    'route-aware raced WSS connect',
)

# Route-aware pool with only one warm spare per DC/media class.
t = one(
    t,
    '''    private fun refillPoolAsync(key: Pair<Int, Boolean>, domains: List<String>) {
        safeExecute {
            try {
                val (dc, _) = key
                val ip = EwenloyTelegramRanges.wsGatewayIp(dc) ?: return@safeExecute
                val bucket = wsPool.getOrPut(key) { CopyOnWriteArrayList() }
                while (bucket.size < 4 && running.get()) {
                    val ws = domains.firstNotNullOfOrNull { domain ->
                        try { EwenloyRawWebSocket.connect(ip, domain, WS_CONNECT_TIMEOUT_MS) } catch (_: Exception) { null }
                    } ?: break
                    bucket.add(PooledWs(ws, System.currentTimeMillis()))
                }
            } catch (_: Exception) {}
        }
    }
''',
    '''    private fun refillPoolAsync(key: Pair<Int, Boolean>, domains: List<String>) {
        safeExecute {
            try {
                val route = routeProvider()
                if (!route.ready) return@safeExecute
                val (dc, _) = key
                val ip = EwenloyTelegramRanges.wsGatewayIp(dc) ?: return@safeExecute
                val bucket = wsPool.getOrPut(key) { CopyOnWriteArrayList() }
                while (bucket.size < 1 && running.get()) {
                    val ws = connectRace(ip, domains, WARMUP_CONNECT_TIMEOUT_MS, route) ?: break
                    bucket.add(PooledWs(ws, System.currentTimeMillis(), route.id))
                }
            } catch (_: Exception) {}
        }
    }

    private fun connectRace(
        ip: String,
        domains: List<String>,
        timeoutMs: Int,
        route: TgTransportRoute,
    ): EwenloyRawWebSocket? {
        val completion = ExecutorCompletionService<EwenloyRawWebSocket?>(pool)
        val claimed = AtomicBoolean(false)
        val futures = domains.distinct().take(2).map { domain ->
            completion.submit(Callable {
                try {
                    val ws = EwenloyRawWebSocket.connect(
                        ip = ip,
                        domain = domain,
                        timeoutMs = timeoutMs,
                        upstreamSocksPort = route.upstreamSocksPort,
                    )
                    if (claimed.compareAndSet(false, true)) ws
                    else { runCatching { ws.close() }; null }
                } catch (_: Exception) {
                    stats.wsErrors.incrementAndGet()
                    null
                }
            })
        }
        val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMs.toLong() + 250L)
        var winner: EwenloyRawWebSocket? = null
        for (i in futures.indices) {
            val remain = deadline - System.nanoTime()
            if (remain <= 0L) break
            val completed = completion.poll(remain, TimeUnit.NANOSECONDS) ?: break
            val ws = runCatching { completed.get() }.getOrNull()
            if (ws != null) {
                winner = ws
                break
            }
        }
        futures.forEach { future -> if (!future.isDone) future.cancel(true) }
        return winner
    }
''',
    'route-aware warm pool and domain race',
)

t = one(t, '    private data class PooledWs(val ws: EwenloyRawWebSocket, val createdAtMs: Long)\n', '    private data class PooledWs(val ws: EwenloyRawWebSocket, val createdAtMs: Long, val routeId: String)\n', 'route-tag pooled websocket')
t = one(t, '        private const val WS_POOL_MAX_AGE = 120_000L\n        private const val WS_CONNECT_TIMEOUT_MS = 10_000\n', '        private const val WS_POOL_MAX_AGE = 45_000L\n        private const val WS_CONNECT_TIMEOUT_MS = 3_500\n        private const val WARMUP_CONNECT_TIMEOUT_MS = 2_500\n', 'TG Auto WSS timeouts')
write(server_rel, t)

# Dedicated isolated ByeDPI process + network state permission.
manifest_rel = 'app/src/main/AndroidManifest.xml'
t = read(manifest_rel)
if 'android.permission.ACCESS_NETWORK_STATE' not in t:
    t = one(t, '    <uses-permission android:name="android.permission.INTERNET" />\n', '    <uses-permission android:name="android.permission.INTERNET" />\n    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n', 'ACCESS_NETWORK_STATE')
service_anchor = '''        <service android:name=".services.ByeDpiProxyService"
            android:foregroundServiceType="dataSync"
            android:exported="false">
        </service>
'''
service_block = service_anchor + '''
        <service
            android:name=".ewenloy.tgws.TgDpiService"
            android:process=":tg_dpi"
            android:exported="false" />
'''
t = one(t, service_anchor, service_block, 'isolated TG DPI service')
write(manifest_rel, t)

# Invariants.
raw = read(raw_rel)
server = read(server_rel)
manifest = read(manifest_rel)
for token in ('X509TrustManager', 'checkServerTrusted', 'trustAll'):
    if token in raw:
        raise RuntimeError(f'unsafe TLS token returned: {token}')
for token in ('upstreamSocksPort', 'TG ByeDPI SOCKS5 CONNECT failed', 'endpointIdentificationAlgorithm = "HTTPS"'):
    if token not in raw:
        raise RuntimeError(f'RawWS TG Auto invariant missing: {token}')
for token in ('routeProvider', 'connectRace(', 'resetTransportState()', 'ws:${activeRoute.id}'):
    if token not in server:
        raise RuntimeError(f'server TG Auto invariant missing: {token}')
if 'directTcpFallback(c, input, output, addr, port, init)' in server:
    raise RuntimeError('direct TCP fallback remains reachable')
for token in ('android.permission.ACCESS_NETWORK_STATE', 'android:process=":tg_dpi"', 'android:exported="false"'):
    if token not in manifest:
        raise RuntimeError(f'manifest TG Auto invariant missing: {token}')
print('TG Clean v0.2.0 TG Auto transport v2 applied successfully')
