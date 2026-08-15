package io.github.romanvht.byedpi.ewenloy.tgws

import android.app.Service
import android.content.Intent
import android.os.Binder
import android.os.IBinder
import android.util.Log
import io.github.romanvht.byedpi.core.ByeDpiProxy
import io.github.romanvht.byedpi.core.ByeDpiProxyCmdPreferences
import io.github.romanvht.byedpi.utility.shellSplit
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.TimeUnit

/** Short-lived ByeDPI instance used only to test system/YouTube strategies. */
class SystemDpiProbeService : Service() {
    private val binder = Binder()
    private val executor = Executors.newSingleThreadExecutor()

    @Volatile private var proxy: ByeDpiProxy? = null
    @Volatile private var worker: Future<*>? = null
    @Volatile private var currentStrategy: String? = null

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                val strategy = intent.getStringExtra(EXTRA_STRATEGY)?.trim().orEmpty()
                if (strategy.isNotEmpty()) startStrategy(strategy)
            }
            ACTION_STOP -> {
                stopProxyInternal()
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    @Synchronized
    private fun startStrategy(strategy: String) {
        if (currentStrategy == strategy && worker?.isDone == false) return
        stopProxyInternal()

        val args = mutableListOf("ciadpi", "--ip", "127.0.0.1", "--port", PORT.toString())
        args += shellSplit(strategy)

        val next = ByeDpiProxy()
        proxy = next
        currentStrategy = strategy
        worker = executor.submit {
            val code = runCatching {
                next.startProxy(ByeDpiProxyCmdPreferences(args.toTypedArray()))
            }.onFailure {
                Log.e(TAG, "System probe ByeDPI crashed", it)
            }.getOrDefault(-1)
            Log.i(TAG, "System probe ByeDPI exited code=$code")
        }
    }

    @Synchronized
    private fun stopProxyInternal() {
        val active = proxy
        proxy = null
        currentStrategy = null
        if (active != null) runCatching { active.stopProxy() }

        worker?.let { activeWorker ->
            runCatching { activeWorker.get(900, TimeUnit.MILLISECONDS) }
            activeWorker.cancel(true)
        }
        worker = null
    }

    override fun onDestroy() {
        stopProxyInternal()
        executor.shutdownNow()
        super.onDestroy()
    }

    companion object {
        const val PORT = 1091
        const val ACTION_START = "io.github.zsanya322maker.byedpitgclean.SYSTEM_DPI_PROBE_START"
        const val ACTION_STOP = "io.github.zsanya322maker.byedpitgclean.SYSTEM_DPI_PROBE_STOP"
        const val EXTRA_STRATEGY = "strategy"
        private const val TAG = "SystemDpiProbeSvc"
    }
}
