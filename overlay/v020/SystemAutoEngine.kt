package io.github.romanvht.byedpi.ewenloy.tgws

import android.content.Context
import io.github.romanvht.byedpi.utility.SiteCheckUtils
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import kotlin.coroutines.coroutineContext

data class SystemAutoSelection(
    val strategy: String,
    val index: Int,
    val score: Int,
    val total: Int,
)

private data class SystemProbeResult(
    val strategy: String,
    val index: Int,
    val score: Int,
    val total: Int,
    val error: String? = null,
)

/**
 * Independent system DPI auto-selector.
 * It runs ByeDPI in :system_probe on 127.0.0.1:1091, so Telegram's :tg_dpi
 * and the final VPN ByeDPI instance remain independent.
 */
class SystemAutoEngine(context: Context) {
    private val appContext = context.applicationContext
    private val process = SystemDpiProbeController(appContext)
    private val strategies = loadStrategies()
    private val testSites = loadSystemSites()

    suspend fun select(): SystemAutoSelection? = withContext(Dispatchers.IO) {
        TgCleanRuntime.systemAutoRunning = true
        TgCleanRuntime.systemAutoPhase = "Быстрый подбор"
        TgCleanRuntime.systemAutoProgress = "0/${FAST_INDICES.size}"
        TgCleanRuntime.systemAutoSummary = ""
        TgCleanRuntime.systemAutoError = null

        val attempted = linkedSetOf<Int>()
        var best: SystemProbeResult? = null

        try {
            for ((position, index) in FAST_INDICES.withIndex()) {
                coroutineContext.ensureActive()
                if (index !in strategies.indices) continue
                attempted += index
                TgCleanRuntime.systemAutoProgress = "${position + 1}/${FAST_INDICES.size}"
                val result = probe(index, strategies[index], timeoutSeconds = 2)
                best = better(best, result)
                appendSummary(result, "FAST")

                if (result.score == result.total && verify(result, timeoutSeconds = 3)) {
                    return@withContext publishSelection(result)
                }
            }

            TgCleanRuntime.systemAutoPhase = "Глубокий подбор"
            val deep = strategies.indices.filterNot { it in attempted }
            for ((position, index) in deep.withIndex()) {
                coroutineContext.ensureActive()
                TgCleanRuntime.systemAutoProgress = "${position + 1}/${deep.size}"
                val result = probe(index, strategies[index], timeoutSeconds = 3)
                best = better(best, result)
                appendSummary(result, "DEEP")

                if (result.score == result.total && verify(result, timeoutSeconds = 3)) {
                    return@withContext publishSelection(result)
                }
            }

            val fallback = best
            if (fallback != null && fallback.score >= MIN_ACCEPTABLE_SCORE.coerceAtMost(fallback.total)) {
                TgCleanRuntime.systemAutoPhase = "Проверка лучшего кандидата"
                if (verify(fallback, timeoutSeconds = 4)) {
                    return@withContext publishSelection(fallback)
                }
            }

            TgCleanRuntime.systemAutoError = "Рабочая системная DPI-стратегия не найдена"
            null
        } finally {
            process.shutdown()
            TgCleanRuntime.systemAutoRunning = false
        }
    }

    private suspend fun probe(index: Int, strategy: String, timeoutSeconds: Long): SystemProbeResult {
        if (!process.restartStrategy(strategy)) {
            return SystemProbeResult(strategy, index, 0, testSites.size, "proxy start failed")
        }

        return try {
            val checker = SiteCheckUtils("127.0.0.1", SystemDpiProbeService.PORT)
            val result = checker.checkSitesAsync(
                sites = testSites,
                requestsCount = 1,
                requestTimeout = timeoutSeconds,
                concurrentRequests = testSites.size.coerceAtMost(6),
                fullLog = false,
            )
            val score = result.sumOf { it.second.coerceAtMost(1) }
            SystemProbeResult(strategy, index, score, testSites.size)
        } catch (e: Exception) {
            SystemProbeResult(strategy, index, 0, testSites.size, "${e.javaClass.simpleName}: ${e.message ?: "error"}")
        } finally {
            process.stopStrategy()
        }
    }

    private suspend fun verify(result: SystemProbeResult, timeoutSeconds: Long): Boolean {
        TgCleanRuntime.systemAutoPhase = "Проверяем #${result.index + 1}"
        val second = probe(result.index, result.strategy, timeoutSeconds)
        appendSummary(second, "VERIFY")
        return second.score >= result.total
    }

    private fun publishSelection(result: SystemProbeResult): SystemAutoSelection {
        TgCleanRuntime.systemAutoPhase = "Готово"
        TgCleanRuntime.systemAutoProgress = "#${result.index + 1}"
        TgCleanRuntime.systemStrategyIndex = result.index + 1
        TgCleanRuntime.systemStrategy = result.strategy
        TgCleanRuntime.systemScore = "${result.score}/${result.total}"
        TgCleanRuntime.systemAutoError = null
        return SystemAutoSelection(result.strategy, result.index + 1, result.score, result.total)
    }

    private fun appendSummary(result: SystemProbeResult, phase: String) {
        val line = buildString {
            append(phase).append(" #").append(result.index + 1)
            append(": ").append(result.score).append('/').append(result.total)
            result.error?.let { append(" ").append(it) }
        }
        val lines = (TgCleanRuntime.systemAutoSummary.lines().filter { it.isNotBlank() } + line).takeLast(14)
        TgCleanRuntime.systemAutoSummary = lines.joinToString("\n")
    }

    private fun better(current: SystemProbeResult?, candidate: SystemProbeResult): SystemProbeResult {
        if (current == null) return candidate
        return if (candidate.score > current.score) candidate else current
    }

    private fun loadStrategies(): List<String> {
        return appContext.assets.open("proxytest_strategies.list").bufferedReader().use { it.readText() }
            .replace("{sni}", "\"google.com\"")
            .lines()
            .map { it.trim() }
            .filter { it.isNotEmpty() }
    }

    private fun loadSystemSites(): List<String> {
        val available = appContext.assets.open("proxytest_youtube.sites").bufferedReader().use { it.readLines() }
            .map { it.trim() }.filter { it.isNotEmpty() }.toSet()
        val preferred = listOf(
            "youtube.com",
            "youtubei.googleapis.com",
            "manifest.googlevideo.com",
            "i.ytimg.com",
            "googleapis.com",
            "yt3.googleusercontent.com",
        )
        return preferred.filter { it in available }.ifEmpty { available.take(6) }
    }

    companion object {
        // Spread across the official 1.7.8 list so the fast pass covers different techniques.
        private val FAST_INDICES = listOf(0, 2, 3, 4, 7, 9, 20, 21, 29, 38, 48, 55)
        private const val MIN_ACCEPTABLE_SCORE = 5
    }
}
