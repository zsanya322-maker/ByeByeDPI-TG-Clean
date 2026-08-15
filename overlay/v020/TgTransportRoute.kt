package io.github.romanvht.byedpi.ewenloy.tgws

enum class TgRouteKind {
    PROBING,
    DIRECT_WSS,
    BYEDPI_WSS,
    FAILED,
}

data class TgTransportRoute(
    val id: String,
    val label: String,
    val kind: TgRouteKind,
    val upstreamSocksPort: Int? = null,
    val strategy: String? = null,
    val latencyMs: Long? = null,
    val ready: Boolean = true,
) {
    companion object {
        val PROBING = TgTransportRoute(
            id = "probing",
            label = "Подбор маршрута",
            kind = TgRouteKind.PROBING,
            ready = false,
        )

        fun direct(latencyMs: Long? = null) = TgTransportRoute(
            id = "direct-wss",
            label = "Direct WSS",
            kind = TgRouteKind.DIRECT_WSS,
            latencyMs = latencyMs,
        )

        fun dpi(id: String, label: String, strategy: String, latencyMs: Long? = null) = TgTransportRoute(
            id = id,
            label = label,
            kind = TgRouteKind.BYEDPI_WSS,
            upstreamSocksPort = TgDpiService.PORT,
            strategy = strategy,
            latencyMs = latencyMs,
        )

        fun failed(reason: String) = TgTransportRoute(
            id = "failed",
            label = reason,
            kind = TgRouteKind.FAILED,
            ready = false,
        )
    }
}
