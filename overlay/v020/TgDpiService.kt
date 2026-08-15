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

/**
 * Runs a second ByeDPI instance in the dedicated :tg_dpi Android process.
 * The upstream ByeDPI JNI bridge is intentionally single-instance per process,
 * so process isolation keeps the Telegram strategy independent from system VPN ByeDPI.
 */
class TgDpiService : Service() {
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

        val args = mutableListOf(
            "ciadpi",
            "--ip", "127.0.0.1",
            "--port", PORT.toString(),
        )
        args += shellSplit(strategy)

        val next = ByeDpiProxy()
        proxy = next
        currentStrategy = strategy
        worker = executor.submit {
            val code = runCatching {
                next.startProxy(ByeDpiProxyCmdPreferences(args.toTypedArray()))
            }.onFailure {
                Log.e(TAG, "TG ByeDPI crashed", it)
            }.getOrDefault(-1)
            Log.i(TAG, "TG ByeDPI exited code=$code strategy=$strategy")
        }
    }

    @Synchronized
    private fun stopProxyInternal() {
        val active = proxy
        proxy = null
        currentStrategy = null
        if (active != null) runCatching { active.stopProxy() }

        val activeWorker = worker
        if (activeWorker != null) {
            runCatching { activeWorker.get(1200, TimeUnit.MILLISECONDS) }
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
        const val PORT = 1090
        const val ACTION_START = "io.github.zsanya322maker.byedpitgclean.TG_DPI_START"
        const val ACTION_STOP = "io.github.zsanya322maker.byedpitgclean.TG_DPI_STOP"
        const val EXTRA_STRATEGY = "strategy"
        private const val TAG = "TgDpiService"
    }
}
