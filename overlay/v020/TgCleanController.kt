package io.github.romanvht.byedpi.ewenloy.tgws

import android.content.Context
import android.util.Log

class TgCleanController {
    @Volatile private var server: EwenloyTgWsProxyServer? = null
    @Volatile private var networkMonitor: TgNetworkMonitor? = null
    @Volatile private var autoEngine: TgAutoEngine? = null

    @Synchronized
    fun start(context: Context) {
        if (server?.isRunning() == true) return

        val appContext = context.applicationContext
        val dpiProcess = TgDpiProcessController(appContext)
        lateinit var engine: TgAutoEngine

        val candidate = EwenloyTgWsProxyServer(
            host = "127.0.0.1",
            listenPort = PORT,
            routeProvider = { engine.currentRoute() },
            onRouteStatus = { mode ->
                Log.d(TAG, "Telegram route=$mode")
            },
            onStats = { stats ->
                TgCleanRuntime.stats = stats
                Log.d(TAG, stats)
            },
        )

        engine = TgAutoEngine(dpiProcess) { route ->
            TgCleanRuntime.route = route.id
            TgCleanRuntime.routeLabel = route.label
            TgCleanRuntime.routeLatencyMs = route.latencyMs
            candidate.resetTransportState()
            if (route.ready) candidate.warmup()
        }

        candidate.start()
        if (!candidate.isRunning()) {
            TgCleanRuntime.running = false
            TgCleanRuntime.lastError = "Не удалось открыть 127.0.0.1:$PORT"
            throw IllegalStateException("Unable to bind Telegram SOCKS5 on 127.0.0.1:$PORT")
        }

        server = candidate
        autoEngine = engine
        TgCleanRuntime.running = true
        TgCleanRuntime.route = TgTransportRoute.PROBING.id
        TgCleanRuntime.routeLabel = TgTransportRoute.PROBING.label
        TgCleanRuntime.lastError = null

        val monitor = TgNetworkMonitor(appContext) { snapshot ->
            TgCleanRuntime.networkType = snapshot.type
            TgCleanRuntime.networkKey = snapshot.key
            candidate.resetTransportState()
            engine.onNetworkChanged(snapshot)
        }
        networkMonitor = monitor
        monitor.start()

        Log.i(TAG, "Telegram SOCKS5 started on 127.0.0.1:$PORT with TG Auto")
    }

    @Synchronized
    fun stop() {
        networkMonitor?.stop()
        networkMonitor = null

        val engine = autoEngine
        autoEngine = null
        if (engine != null) {
            kotlinx.coroutines.runBlocking {
                runCatching { engine.shutdown() }
            }
        }

        val current = server
        server = null
        runCatching { current?.stop() }
            .onFailure { Log.w(TAG, "Telegram SOCKS5 stop failed", it) }

        TgCleanRuntime.running = false
        TgCleanRuntime.route = "idle"
        TgCleanRuntime.routeLabel = "—"
        TgCleanRuntime.routeLatencyMs = null
        TgCleanRuntime.probeSummary = ""
    }

    companion object {
        const val PORT = 1082
        private const val TAG = "TgCleanController"
    }
}
