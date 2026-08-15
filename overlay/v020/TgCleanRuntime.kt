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
    @Volatile var tgProbePhase: String = ""
    @Volatile var tgProbeProgress: String = ""
    @Volatile var lastError: String? = null

    @Volatile var systemAutoRunning: Boolean = false
    @Volatile var systemAutoPhase: String = ""
    @Volatile var systemAutoProgress: String = ""
    @Volatile var systemAutoSummary: String = ""
    @Volatile var systemAutoError: String? = null
    @Volatile var systemStrategyIndex: Int? = null
    @Volatile var systemStrategy: String = ""
    @Volatile var systemScore: String = ""
}
