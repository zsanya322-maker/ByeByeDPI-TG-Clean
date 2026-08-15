package io.github.romanvht.byedpi.ewenloy.tgws

import android.content.Context
import android.content.Intent
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.net.InetSocketAddress
import java.net.Socket

class SystemDpiProbeController(context: Context) {
    private val appContext = context.applicationContext

    suspend fun startStrategy(strategy: String): Boolean = withContext(Dispatchers.IO) {
        val intent = Intent(appContext, SystemDpiProbeService::class.java).apply {
            action = SystemDpiProbeService.ACTION_START
            putExtra(SystemDpiProbeService.EXTRA_STRATEGY, strategy)
        }
        try {
            appContext.startService(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Unable to start system DPI probe", e)
            return@withContext false
        }
        waitForPort(open = true, timeoutMs = 1400)
    }

    suspend fun stopStrategy(): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            appContext.startService(Intent(appContext, SystemDpiProbeService::class.java).apply {
                action = SystemDpiProbeService.ACTION_STOP
            })
        }
        waitForPort(open = false, timeoutMs = 900)
    }

    suspend fun restartStrategy(strategy: String): Boolean {
        stopStrategy()
        return startStrategy(strategy)
    }

    suspend fun shutdown() {
        stopStrategy()
    }

    private suspend fun waitForPort(open: Boolean, timeoutMs: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            val current = isPortOpen()
            if (current == open) return true
            delay(60)
        }
        return isPortOpen() == open
    }

    private fun isPortOpen(): Boolean {
        val socket = Socket()
        return try {
            socket.connect(InetSocketAddress("127.0.0.1", SystemDpiProbeService.PORT), 100)
            true
        } catch (_: Exception) {
            false
        } finally {
            runCatching { socket.close() }
        }
    }

    companion object {
        private const val TAG = "SystemDpiProbeCtl"
    }
}
