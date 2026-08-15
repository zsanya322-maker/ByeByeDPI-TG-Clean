package io.github.romanvht.byedpi.ewenloy.tgws

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Build
import android.util.Log

data class TgNetworkSnapshot(
    val key: String,
    val type: String,
    val hasInternet: Boolean,
    val validated: Boolean,
    val metered: Boolean,
)

class TgNetworkMonitor(
    context: Context,
    private val onChanged: (TgNetworkSnapshot) -> Unit,
) {
    private val cm = context.applicationContext.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    @Volatile private var started = false
    @Volatile private var lastKey: String? = null

    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) = dispatch(snapshot(network))
        override fun onLost(network: Network) = dispatch(currentSnapshot())
        override fun onCapabilitiesChanged(network: Network, networkCapabilities: NetworkCapabilities) =
            dispatch(snapshot(network, networkCapabilities))
    }

    fun start() {
        if (started) return
        started = true
        dispatch(currentSnapshot(), force = true)
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                cm.registerDefaultNetworkCallback(callback)
            } else {
                val request = NetworkRequest.Builder()
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .build()
                cm.registerNetworkCallback(request, callback)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Network callback registration failed", e)
        }
    }

    fun stop() {
        if (!started) return
        started = false
        runCatching { cm.unregisterNetworkCallback(callback) }
        lastKey = null
    }

    fun currentSnapshot(): TgNetworkSnapshot {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            return snapshot(cm.activeNetwork)
        }

        @Suppress("DEPRECATION")
        val info = cm.activeNetworkInfo
        if (info == null || !info.isConnected) {
            return TgNetworkSnapshot("none", "Нет сети", false, false, true)
        }
        @Suppress("DEPRECATION")
        val type = when (info.type) {
            ConnectivityManager.TYPE_WIFI -> "Wi-Fi"
            ConnectivityManager.TYPE_MOBILE -> "Мобильная сеть"
            else -> "Другая сеть"
        }
        return TgNetworkSnapshot(
            key = "legacy:${info.type}:${info.subtype}",
            type = type,
            hasInternet = true,
            validated = true,
            metered = cm.isActiveNetworkMetered,
        )
    }

    private fun snapshot(network: Network?, capsOverride: NetworkCapabilities? = null): TgNetworkSnapshot {
        if (network == null) return TgNetworkSnapshot("none", "Нет сети", false, false, true)
        val caps = capsOverride ?: cm.getNetworkCapabilities(network)
            ?: return TgNetworkSnapshot("none", "Нет сети", false, false, true)

        val type = when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "Wi-Fi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "Мобильная сеть"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "Ethernet"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "VPN/другая сеть"
            else -> "Другая сеть"
        }
        val hasInternet = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        val validated = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        } else {
            hasInternet
        }
        val metered = !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
        val key = buildString {
            append(network.toString())
            append(':').append(type)
            append(':').append(if (validated) 'v' else 'u')
        }
        return TgNetworkSnapshot(key, type, hasInternet, validated, metered)
    }

    private fun dispatch(snapshot: TgNetworkSnapshot, force: Boolean = false) {
        if (!started && !force) return
        if (!force && lastKey == snapshot.key) return
        lastKey = snapshot.key
        onChanged(snapshot)
    }

    companion object {
        private const val TAG = "TgNetworkMonitor"
    }
}
