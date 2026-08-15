package io.github.romanvht.byedpi.ewenloy.tgws

object TgCleanRuntime {
    @Volatile var running: Boolean = false
    @Volatile var route: String = "idle"
    @Volatile var routeLabel: String = "—"
    @Volatile var routeLatencyMs: Long? = null
    @Volatile var networkType: String = "—"
    @Volatile var networkKey: String = ""
    @Volatile var stats: String = ""
    @Volatile var probeSummary: String = ""
    @Volatile var lastError: String? = null
}
