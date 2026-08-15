package io.github.romanvht.byedpi.ewenloy.tgws

import android.content.Context
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.cancel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import java.util.concurrent.ConcurrentHashMap
import kotlin.coroutines.coroutineContext

private data class TgProbeResult(
    val route: TgTransportRoute,
    val success: Boolean,
    val latencyMs: Long? = null,
    val endpoint: String? = null,
    val error: String? = null,
)

class TgAutoEngine(
    context: Context,
    private val dpiProcess: TgDpiProcessController,
    private val onRouteChanged: (TgTransportRoute) -> Unit,
) {
    private val appContext = context.applicationContext
    private var scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var selectJob: Job? = null
    private val cache = ConcurrentHashMap<String, TgTransportRoute>()
    private val officialStrategies = loadStrategies()

    @Volatile private var current = TgTransportRoute.PROBING

    fun currentRoute(): TgTransportRoute = current

    fun onNetworkChanged(snapshot: TgNetworkSnapshot) {
        selectJob?.cancel()
        selectJob = scope.launch { selectForNetwork(snapshot) }
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
        TgCleanRuntime.tgProbePhase = "Direct WSS"
        TgCleanRuntime.tgProbeProgress = ""
        TgCleanRuntime.lastError = null

        if (!snapshot.hasInternet) {
            publish(TgTransportRoute.failed("Нет сети"))
            TgCleanRuntime.lastError = "Нет активной сети"
            return
        }

        cache[snapshot.key]?.let { cached ->
            TgCleanRuntime.tgProbePhase = "Проверка кэша"
            val cachedProbe = validateCached(cached)
            if (cachedProbe.success) {
                val restored = cached.copy(latencyMs = cachedProbe.latencyMs)
                publish(restored)
                TgCleanRuntime.probeSummary = "CACHE ${restored.label}: ${cachedProbe.latencyMs} ms"
                return
            }
            cache.remove(snapshot.key)
            dpiProcess.stopStrategy()
        }

        val results = mutableListOf<TgProbeResult>()
        val directTimeout = if (snapshot.type == "Мобильная сеть") 1800 else 2400
        val direct = probeRoute(TgTransportRoute.direct(), directTimeout, dc = 2)
        results += direct
        updateProbeSummary(results)

        if (direct.success) {
            TgCleanRuntime.tgProbePhase = "Проверяем Direct WSS по DC"
            val verified = verifyAcrossDcs(TgTransportRoute.direct(), timeoutMs = 2600)
            if (verified.success) {
                val chosen = TgTransportRoute.direct(verified.latencyMs)
                cache[snapshot.key] = chosen
                publish(chosen)
                updateProbeSummary(results + verified)
                return
            }
            results += verified
            updateProbeSummary(results)
        }

        val fastIndices = FAST_INDICES.filter { it in officialStrategies.indices }
        TgCleanRuntime.tgProbePhase = "Быстрый TG DPI"
        for ((position, index) in fastIndices.withIndex()) {
            coroutineContext.ensureActive()
            TgCleanRuntime.tgProbeProgress = "${position + 1}/${fastIndices.size}"
            val route = routeFor(index)
            val candidate = tryDpiCandidate(route, probeTimeout = 2800, verifyTimeout = 3200)
            results += candidate
            updateProbeSummary(results)
            if (candidate.success) {
                val chosen = route.copy(latencyMs = candidate.latencyMs)
                cache[snapshot.key] = chosen
                publish(chosen)
                return
            }
        }

        val attempted = fastIndices.toSet()
        val deep = officialStrategies.indices.filterNot { it in attempted }
        TgCleanRuntime.tgProbePhase = "Глубокий TG DPI"
        for ((position, index) in deep.withIndex()) {
            coroutineContext.ensureActive()
            TgCleanRuntime.tgProbeProgress = "${position + 1}/${deep.size}"
            val route = routeFor(index)
            val candidate = tryDpiCandidate(route, probeTimeout = 3400, verifyTimeout = 3800)
            results += candidate
            updateProbeSummary(results)
            if (candidate.success) {
                val chosen = route.copy(latencyMs = candidate.latencyMs)
                cache[snapshot.key] = chosen
                publish(chosen)
                return
            }
        }

        dpiProcess.stopStrategy()
        publish(TgTransportRoute.failed("Маршрут не найден"))
        TgCleanRuntime.tgProbePhase = "Не найден"
        TgCleanRuntime.tgProbeProgress = "${officialStrategies.size}/${officialStrategies.size}"
        TgCleanRuntime.lastError = results.takeLast(8).joinToString(" | ") {
            "${it.route.label}: ${it.error ?: "fail"}"
        }
    }

    private suspend fun tryDpiCandidate(
        route: TgTransportRoute,
        probeTimeout: Int,
        verifyTimeout: Int,
    ): TgProbeResult {
        val strategy = route.strategy
            ?: return TgProbeResult(route, false, error = "strategy missing")
        if (!dpiProcess.restartStrategy(strategy)) {
            return TgProbeResult(route, false, error = "TG ByeDPI port did not start")
        }

        val initial = probeRoute(route, timeoutMs = probeTimeout, dc = 2)
        if (!initial.success) {
            dpiProcess.stopStrategy()
            return initial
        }

        val verified = verifyAcrossDcs(route, verifyTimeout)
        if (!verified.success) {
            dpiProcess.stopStrategy()
            return verified
        }

        // Keep the isolated TG ByeDPI process running: this route is now active.
        return verified
    }

    private suspend fun validateCached(route: TgTransportRoute): TgProbeResult {
        if (route.kind == TgRouteKind.BYEDPI_WSS) {
            val strategy = route.strategy ?: return TgProbeResult(route, false, error = "cached strategy missing")
            if (!dpiProcess.restartStrategy(strategy)) {
                return TgProbeResult(route, false, error = "cached TG ByeDPI failed to start")
            }
        } else {
            dpiProcess.stopStrategy()
        }
        val result = verifyAcrossDcs(route, timeoutMs = 2400)
        if (!result.success && route.kind == TgRouteKind.BYEDPI_WSS) dpiProcess.stopStrategy()
        return result
    }

    private suspend fun verifyAcrossDcs(route: TgTransportRoute, timeoutMs: Int): TgProbeResult = coroutineScope {
        val checks = VERIFY_DCS.map { dc ->
            async(Dispatchers.IO) { probeRoute(route, timeoutMs, dc) }
        }.awaitAll()
        val ok = checks.filter { it.success && it.latencyMs != null }
        val required = 2
        if (ok.size >= required) {
            val average = ok.mapNotNull { it.latencyMs }.average().toLong()
            TgProbeResult(route, true, average, endpoint = "DC ${ok.size}/${VERIFY_DCS.size}")
        } else {
            TgProbeResult(
                route,
                false,
                error = "multi-DC ${ok.size}/${VERIFY_DCS.size}; " + checks.filterNot { it.success }.take(2)
                    .joinToString("; ") { it.error ?: "fail" },
            )
        }
    }

    private suspend fun probeRoute(route: TgTransportRoute, timeoutMs: Int, dc: Int): TgProbeResult = coroutineScope {
        val ip = EwenloyTelegramRanges.wsGatewayIp(dc)
            ?: return@coroutineScope TgProbeResult(route, false, error = "DC$dc gateway missing")
        val domains = EwenloyTelegramRanges.wsDomains(dc, false).distinct().take(2)

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
                    TgProbeResult(route, true, elapsed, "DC$dc $domain")
                } catch (e: Exception) {
                    TgProbeResult(route, false, error = "DC$dc ${e.javaClass.simpleName}: ${e.message ?: "error"}")
                }
            }
        }

        val finished = probes.awaitAll()
        finished.filter { it.success }.minByOrNull { it.latencyMs ?: Long.MAX_VALUE }
            ?: finished.firstOrNull()
            ?: TgProbeResult(route, false, error = "DC$dc no endpoints")
    }

    private fun routeFor(index: Int): TgTransportRoute {
        return TgTransportRoute.dpi(
            id = "tg-dpi-${index + 1}",
            label = "TG DPI #${index + 1}",
            strategy = officialStrategies[index],
        )
    }

    private fun loadStrategies(): List<String> {
        return appContext.assets.open("proxytest_strategies.list").bufferedReader().use { it.readText() }
            .replace("{sni}", "\"google.com\"")
            .lines().map { it.trim() }.filter { it.isNotEmpty() }
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
        TgCleanRuntime.probeSummary = results.takeLast(18).joinToString("\n") { result ->
            if (result.success) {
                "${result.route.label}: ${result.latencyMs} ms ${result.endpoint.orEmpty()}"
            } else {
                "${result.route.label}: FAIL ${result.error.orEmpty()}"
            }
        }
    }

    companion object {
        private const val TAG = "TgAutoEngine"
        private val VERIFY_DCS = listOf(2, 4, 5)
        private val FAST_INDICES = listOf(0, 2, 3, 4, 7, 9, 20, 21, 29, 38, 48, 55)
    }
}
