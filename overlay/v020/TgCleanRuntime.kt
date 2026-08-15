package io.github.romanvht.byedpi.ewenloy.tgws

object TgCleanRuntime {
    @Volatile var running: Boolean = false
    @Volatile var route: String = "idle"
    @Volatile var stats: String = ""
    @Volatile var lastError: String? = null
}
