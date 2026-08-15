package io.github.romanvht.byedpi.ewenloy.tgws

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.net.InetSocketAddress
import java.net.Socket

class TgDpiProcessController(context: Context) {
    private val appContext = context.applicationContext
    @Volatile private var bound = false
    @Volatile private var bindRequested = false

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, service: IBinder?) {
            bound = true
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            bound = false
        }

        override fun onBindingDied(name: ComponentName?) {
            bound = false
            bindRequested = false
        }
    }

    suspend fun startStrategy(strategy: String): Boolean = withContext(Dispatchers.IO) {
        ensureBound()
        val intent = Intent(appContext, TgDpiService::class.java).apply {
            action = TgDpiService.ACTION_START
            putExtra(TgDpiService.EXTRA_STRATEGY, strategy)
        }
        try {
            appContext.startService(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Unable to start TG ByeDPI process", e)
            return@withContext false
        }
        waitForPort(open = true, timeoutMs = 1800)
    }

    suspend fun stopStrategy(): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            appContext.startService(Intent(appContext, TgDpiService::class.java).apply {
                action = TgDpiService.ACTION_STOP
            })
        }
        waitForPort(open = false, timeoutMs = 1400)
    }

    suspend fun restartStrategy(strategy: String): Boolean {
        stopStrategy()
        return startStrategy(strategy)
    }

    suspend fun shutdown() {
        stopStrategy()
        if (bindRequested) {
            runCatching { appContext.unbindService(connection) }
        }
        bound = false
        bindRequested = false
    }

    private fun ensureBound() {
        if (bindRequested) return
        bindRequested = true
        val ok = runCatching {
            appContext.bindService(
                Intent(appContext, TgDpiService::class.java),
                connection,
                Context.BIND_AUTO_CREATE,
            )
        }.getOrDefault(false)
        if (!ok) bindRequested = false
    }

    private suspend fun waitForPort(open: Boolean, timeoutMs: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            val current = isPortOpen()
            if (current == open) return true
            delay(70)
        }
        return isPortOpen() == open
    }

    private fun isPortOpen(): Boolean {
        val socket = Socket()
        return try {
            socket.connect(InetSocketAddress("127.0.0.1", TgDpiService.PORT), 120)
            true
        } catch (_: Exception) {
            false
        } finally {
            runCatching { socket.close() }
        }
    }

    companion object {
        private const val TAG = "TgDpiProcessCtl"
    }
}
