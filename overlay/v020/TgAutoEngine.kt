package io.github.romanvht.byedpi.ewenloy.tgws

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.cancel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.ConcurrentHashMap

private data class TgProbeResult(
    val route: TgTransportRoute,
    val success: Boolean,
    val latencyMs: Long? = null,
    val endpoint: String? = null,
    val error: String? = null,
)

class TgAutoEngine(
    private val dpiProcess: TgDpiProcessController,
    private val onRouteChanged: (TgTransportRoute) -> Unit,
) {
    private var scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var selectJob: Job? = null
    private val cache = ConcurrentHashMap<String, TgTransportRoute>()

    @Volatile private var current = TgTransportRoute.PROBING

    private val dpiCandidates = listOf(
        TgTransportRoute.dpi(
            id = "tg-dpi-a",
            label = "TG DPI A",
            strategy = "-o1 -r-5+se -a1",
        ),
        TgTransportRoute.dpi(
            id = "tg-dpi-b",
            label = "TG DPI B",
            strategy = "-o1 -f-1 -r-5+se -a1",
        ),
        TgTransportRoute.dpi(
            id = "tg-dpi-c",
            label = "TG DPI C",
            strategy = "-s1 -d3+s -a1 -At -r1+s -a1",
        ),
        TgTransportRoute.dpi(
            id = "tg-dpi-d",
            label = "TG DPI D",
            strategy = "-d1 -s3+s -a1",
        ),
    )

    fun currentRoute(): TgTransportRoute = current

    fun onNetworkChanged(snapshot: TgNetworkSnapshot) {
        selectJob?.cancel()
        selectJob = scope.launch {
            selectForNetwork(snapshot)
        }
    }

    suspend fun shutdown() {
        selectJob?.cancel()
        dpiProcess.shutdown()
        scope.cancel()
        current = TgTransportRoute.PROBING
    }

    private suspend fun selectForNetwork(snapshot: TgNetworkSnapshot) {
        dpiProcess.stopStrategy()
        publish(TgTransportRoute.PROBING)
        TgCleanRuntime.networkType = snapshot.type
        TgCleanRuntime.networkKey = snapshot.key
        TgCleanRuntime.probeSummary = ""
        TgCleanRuntime.lastError = null

        if (!snapshot.hasInternet) {
            publish(TgTransportRoute.failed("Нет сети"))
            TgCleanRuntime.lastError = "Нет активной сети"
            return
        }

        val cached = cache[snapshot.key]
        if (cached != null) {
            val cachedProbe = validateCached(cached)
            if (cachedProbe.success) {
                val restored = cached.copy(latencyMs = cachedProbe.latencyMs)
                publish(restored)
                TgCleanRuntime.probeSummary = "cache ${restored.label}: ${cachedProbe.latencyMs} ms"
                return
            }
            cache.remove(snapshot.key)
            dpiProcess.stopStrategy()
        }

        val results = mutableListOf<TgProbeResult>()
        val directTimeout = if (snapshot.type == "Мобильная сеть") 1600 else 2200
        val direct = probeRoute(TgTransportRoute.direct(), directTimeout)
        results += direct
        updateProbeSummary(results)

        // Prefer a healthy direct WSS path when it is already quick.
        if (direct.success && (direct.latencyMs ?: Long.MAX_VALUE) <= 1800) {
            val chosen = TgTransportRoute.direct(direct.latencyMs)
            cache[snapshot.key] = chosen
            publish(chosen)
            return
        }

        for (candidate in dpiCandidates) {
            if (!scope.isActive) return
            val started = dpiProcess.restartStrategy(candidate.strategy ?: continue)
            if (!started) {
                results += TgProbeResult(candidate, false, error = "TG ByeDPI port did not start")
                updateProbeSummary(results)
                continue
            }

            val result = probeRoute(candidate, timeoutMs = 2400)
            results += result
            updateProbeSummary(results)
            dpiProcess.stopStrategy()
        }

        val successful = results
            .filter { it.success && it.latencyMs != null }
            .sortedBy { it.latencyMs }

        if (successful.isEmpty()) {
            publish(TgTransportRoute.failed("Маршрут не найден"))
            TgCleanRuntime.lastError = results.joinToString(" | ") {
                "${it.route.label}: ${it.error ?: "fail"}"
            }
            return
        }

        for (candidate in successful) {
            val route = candidate.route
            if (route.kind == TgRouteKind.BYEDPI_WSS) {
                val strategy = route.strategy ?: continue
                if (!dpiProcess.restartStrategy(strategy)) continue
            } else {
                dpiProcess.stopStrategy()
            }

            // Stability check: winner must pass a second handshake before it becomes active.
            val verify = probeRoute(route, timeoutMs = 2600)
            if (verify.success) {
                val stableLatency = listOfNotNull(candidate.latencyMs, verify.latencyMs).average().toLong()
                val chosen = route.copy(latencyMs = stableLatency)
                cache[snapshot.key] = chosen
                publish(chosen)
                updateProbeSummary(results + verify)
                return
            }
            dpiProcess.stopStrategy()
        }

        publish(TgTransportRoute.failed("Маршрут нестабилен"))
        TgCleanRuntime.lastError = "Кандидаты отвечали, но не прошли повторную проверку"
    }

    private suspend fun validateCached(route: TgTransportRoute): TgProbeResult {
        if (route.kind == TgRouteKind.BYEDPI_WSS) {
            val strategy = route.strategy
                ?: return TgProbeResult(route, false, error = "cached strategy missing")
            if (!dpiProcess.restartStrategy(strategy)) {
                return TgProbeResult(route, false, error = "cached TG ByeDPI failed to start")
            }
        }
        return probeRoute(route, timeoutMs = 1800)
    }

    private suspend fun probeRoute(route: TgTransportRoute, timeoutMs: Int): TgProbeResult = coroutineScope {
        val ip = EwenloyTelegramRanges.wsGatewayIp(2)
            ?: return@coroutineScope TgProbeResult(route, false, error = "DC2 gateway missing")
        val domains = EwenloyTelegramRanges.wsDomains(2, false).distinct().take(2)

        val probes = domains.map { domain ->
            async(Dispatchers.IO) {
                val start = System.nanoTime()
                try {
                    val ws = EwenloyRawWebSocket.connect(
                        ip = ip,
                        domain = domain,
                        timeoutMs = timeoutMs,
                        upstreamSocksPort = route.upstreamSocksPort,
                    )
                    ws.close()
                    val elapsed = (System.nanoTime() - start) / 1_000_000
                    TgProbeResult(route, true, elapsed, domain)
                } catch (e: Exception) {
                    TgProbeResult(route, false, error = "${e.javaClass.simpleName}: ${e.message ?: "error"}")
                }
            }
        }

        val finished = probes.awaitAll()
        finished.filter { it.success }.minByOrNull { it.latencyMs ?: Long.MAX_VALUE }
            ?: finished.firstOrNull()
            ?: TgProbeResult(route, false, error = "no endpoints")
    }

    private fun publish(route: TgTransportRoute) {
        current = route
        TgCleanRuntime.route = route.id
        TgCleanRuntime.routeLabel = route.label
        TgCleanRuntime.routeLatencyMs = route.latencyMs
        onRouteChanged(route)
        Log.i(TAG, "TG route=${route.id} label=${route.label} latency=${route.latencyMs}")
    }

    private fun updateProbeSummary(results: List<TgProbeResult>) {
        TgCleanRuntime.probeSummary = results.joinToString("\n") { result ->
            if (result.success) {
                "${result.route.label}: ${result.latencyMs} ms ${result.endpoint.orEmpty()}"
            } else {
                "${result.route.label}: FAIL ${result.error.orEmpty()}"
            }
        }
    }

    companion object {
        private const val TAG = "TgAutoEngine"
    }
}
