#!/usr/bin/env python3
"""Apply TG Clean v0.2.0 TEST3: Cloudflare Worker fallback for Telegram mobile networks."""
from __future__ import annotations
import pathlib, sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_v020_test3.py <ByeByeDPI checkout>')

root = pathlib.Path(sys.argv[1]).resolve()


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


CF_WORKER_DOMAIN = 'odd-cake-197c.omebufufuhekodez.workers.dev'

# Installable upgrade over TEST2.
gradle_rel = 'app/build.gradle.kts'
t = read(gradle_rel)
t = one(t, 'versionCode = 178021', 'versionCode = 178022', 'TEST3 versionCode')
t = one(t, 'versionName = "2.0.0-tgclean-test2"', 'versionName = "2.0.0-tgclean-test3"', 'TEST3 versionName')
write(gradle_rel, t)

# A route may now be an outer WSS connection to a restricted Cloudflare Worker.
route_rel = 'app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/TgTransportRoute.kt'
t = read(route_rel)
t = one(
    t,
    '    BYEDPI_WSS,\n    FAILED,\n',
    '    BYEDPI_WSS,\n    CLOUDFLARE_WORKER,\n    FAILED,\n',
    'Cloudflare route kind',
)
t = one(
    t,
    '    val strategy: String? = null,\n    val latencyMs: Long? = null,\n',
    '    val strategy: String? = null,\n    val workerDomain: String? = null,\n    val latencyMs: Long? = null,\n',
    'Cloudflare route domain',
)
t = one(
    t,
    '''        fun failed(reason: String) = TgTransportRoute(
''',
    '''        fun worker(domain: String, latencyMs: Long? = null) = TgTransportRoute(
            id = "cf-worker",
            label = "Cloudflare Worker",
            kind = TgRouteKind.CLOUDFLARE_WORKER,
            workerDomain = domain,
            latencyMs = latencyMs,
        )

        fun failed(reason: String) = TgTransportRoute(
''',
    'Cloudflare route factory',
)
write(route_rel, t)

# RawWebSocket supports an internal, validated path so the Worker can receive the selected DC.
raw_rel = 'app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/EwenloyRawWebSocket.kt'
t = read(raw_rel)
t = one(
    t,
    '''            timeoutMs: Int = 10000,
            upstreamSocksPort: Int? = null,
        ): EwenloyRawWebSocket {
''',
    '''            timeoutMs: Int = 10000,
            upstreamSocksPort: Int? = null,
            path: String = "/apiws",
        ): EwenloyRawWebSocket {
''',
    'RawWS custom path parameter',
)
t = one(
    t,
    '''                val req = buildString {
                    append("GET /apiws HTTP/1.1\\r\\n")
''',
    '''                require(path.startsWith("/") && '\\r' !in path && '\\n' !in path) {
                    "Invalid WebSocket path"
                }
                val req = buildString {
                    append("GET $path HTTP/1.1\\r\\n")
''',
    'RawWS custom request path',
)
write(raw_rel, t)

# TG Auto: on mobile, try the Worker after the fast set and before another 48-strategy deep scan.
auto_rel = 'app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/TgAutoEngine.kt'
t = read(auto_rel)
t = one(
    t,
    '        val results = mutableListOf<TgProbeResult>()\n',
    '        val results = mutableListOf<TgProbeResult>()\n        var workerAttempted = false\n',
    'TG Worker attempt state',
)
t = one(
    t,
    '''        val attempted = fastIndices.toSet()
        val deep = officialStrategies.indices.filterNot { it in attempted }
''',
    f'''        if (snapshot.type == "Мобильная сеть") {{
            workerAttempted = true
            dpiProcess.stopStrategy()
            TgCleanRuntime.tgProbePhase = "Cloudflare Worker"
            TgCleanRuntime.tgProbeProgress = ""
            val workerRoute = TgTransportRoute.worker(CF_WORKER_DOMAIN)
            val workerProbe = probeWorkerRoute(workerRoute, timeoutMs = 5_000, dc = 2)
            results += workerProbe
            updateProbeSummary(results)
            if (workerProbe.success) {{
                val chosen = workerRoute.copy(latencyMs = workerProbe.latencyMs)
                cache[snapshot.key] = chosen
                publish(chosen)
                return
            }}
        }}

        val attempted = fastIndices.toSet()
        val deep = officialStrategies.indices.filterNot {{ it in attempted }}
''',
    'mobile Worker before deep scan',
)
t = one(
    t,
    '''        dpiProcess.stopStrategy()
        publish(TgTransportRoute.failed("Маршрут не найден"))
''',
    f'''        if (!workerAttempted) {{
            workerAttempted = true
            dpiProcess.stopStrategy()
            TgCleanRuntime.tgProbePhase = "Cloudflare Worker"
            TgCleanRuntime.tgProbeProgress = ""
            val workerRoute = TgTransportRoute.worker(CF_WORKER_DOMAIN)
            val workerProbe = probeWorkerRoute(workerRoute, timeoutMs = 5_000, dc = 2)
            results += workerProbe
            updateProbeSummary(results)
            if (workerProbe.success) {{
                val chosen = workerRoute.copy(latencyMs = workerProbe.latencyMs)
                cache[snapshot.key] = chosen
                publish(chosen)
                return
            }}
        }}

        dpiProcess.stopStrategy()
        publish(TgTransportRoute.failed("Маршрут не найден"))
''',
    'Worker fallback after deep scan',
)
t = one(
    t,
    '''    private suspend fun tryDpiCandidate(
''',
    '''    private fun probeWorkerRoute(
        route: TgTransportRoute,
        timeoutMs: Int,
        dc: Int,
    ): TgProbeResult {
        val worker = route.workerDomain
            ?: return TgProbeResult(route, false, error = "worker domain missing")
        val start = System.nanoTime()
        return try {
            val ws = EwenloyRawWebSocket.connect(
                ip = worker,
                domain = worker,
                timeoutMs = timeoutMs,
                path = "/apiws?dc=$dc",
            )
            ws.close()
            val elapsed = (System.nanoTime() - start) / 1_000_000
            TgProbeResult(route, true, elapsed, endpoint = "$worker DC$dc")
        } catch (e: Exception) {
            TgProbeResult(
                route,
                false,
                error = "${e.javaClass.simpleName}: ${e.message ?: "error"}",
            )
        }
    }

    private suspend fun tryDpiCandidate(
''',
    'Worker probe helper',
)
t = one(
    t,
    '''    private suspend fun validateCached(route: TgTransportRoute): TgProbeResult {
        if (route.kind == TgRouteKind.BYEDPI_WSS) {
''',
    '''    private suspend fun validateCached(route: TgTransportRoute): TgProbeResult {
        if (route.kind == TgRouteKind.CLOUDFLARE_WORKER) {
            dpiProcess.stopStrategy()
            return probeWorkerRoute(route, timeoutMs = 4_000, dc = 2)
        }
        if (route.kind == TgRouteKind.BYEDPI_WSS) {
''',
    'cached Worker validation',
)
t = one(
    t,
    '''        private const val TAG = "TgAutoEngine"
''',
    f'''        private const val TAG = "TgAutoEngine"
        private const val CF_WORKER_DOMAIN = "{CF_WORKER_DOMAIN}"
''',
    'Worker hostname constant',
)
write(auto_rel, t)

# Runtime server: Worker WSS itself is the data tunnel. It forwards the same patched
# 64-byte MTProto init and subsequent encrypted bytes to the selected Telegram DC.
server_rel = 'app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/EwenloyTgWsProxyServer.kt'
t = read(server_rel)
t = one(
    t,
    '        val ws = pooled ?: connectRace(targetIp, domains, wsTimeout, activeRoute)\n',
    '        val ws = pooled ?: connectRoute(targetIp, domains, wsTimeout, activeRoute, finalDc)\n',
    'route-aware Worker connect',
)
t = one(
    t,
    '                    val ws = connectRace(ip, domains, WARMUP_CONNECT_TIMEOUT_MS, route) ?: break\n',
    '                    val ws = connectRoute(ip, domains, WARMUP_CONNECT_TIMEOUT_MS, route, dc) ?: break\n',
    'Worker-aware pool refill',
)
t = one(
    t,
    '''    private fun connectRace(
''',
    '''    private fun connectRoute(
        ip: String,
        domains: List<String>,
        timeoutMs: Int,
        route: TgTransportRoute,
        dc: Int,
    ): EwenloyRawWebSocket? {
        if (route.kind == TgRouteKind.CLOUDFLARE_WORKER) {
            val worker = route.workerDomain ?: return null
            return try {
                EwenloyRawWebSocket.connect(
                    ip = worker,
                    domain = worker,
                    timeoutMs = timeoutMs,
                    path = "/apiws?dc=$dc",
                )
            } catch (_: Exception) {
                stats.wsErrors.incrementAndGet()
                null
            }
        }
        return connectRace(ip, domains, timeoutMs, route)
    }

    private fun connectRace(
''',
    'Worker WSS transport helper',
)
write(server_rel, t)

# TEST3 invariants.
gradle = read(gradle_rel)
route = read(route_rel)
raw = read(raw_rel)
auto = read(auto_rel)
server = read(server_rel)

if 'versionName = "2.0.0-tgclean-test3"' not in gradle:
    raise RuntimeError('TEST3 version not applied')
for token in ('CLOUDFLARE_WORKER', 'workerDomain', 'Cloudflare Worker'):
    if token not in route:
        raise RuntimeError(f'TEST3 route invariant missing: {token}')
for token in ('path: String = "/apiws"', 'GET $path HTTP/1.1', 'endpointIdentificationAlgorithm = "HTTPS"'):
    if token not in raw:
        raise RuntimeError(f'TEST3 RawWS invariant missing: {token}')
for token in (CF_WORKER_DOMAIN, 'probeWorkerRoute(', 'Cloudflare Worker'):
    if token not in auto:
        raise RuntimeError(f'TEST3 Auto invariant missing: {token}')
for token in ('connectRoute(', 'TgRouteKind.CLOUDFLARE_WORKER', 'path = "/apiws?dc=$dc"'):
    if token not in server:
        raise RuntimeError(f'TEST3 server invariant missing: {token}')
for token in ('X509TrustManager', 'checkServerTrusted', 'trustAll'):
    if token in raw:
        raise RuntimeError(f'unsafe TLS token returned in TEST3: {token}')
if 'directTcpFallback(c, input, output, addr, port, init)' in server:
    raise RuntimeError('direct TCP fallback remains reachable in TEST3')

print('TG Clean v0.2.0 TEST3 Cloudflare Worker fallback applied successfully')
