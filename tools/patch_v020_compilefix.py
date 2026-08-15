#!/usr/bin/env python3
"""Final transport-test UI/compile guard for the v0.2.0 TG Auto branch."""
from __future__ import annotations
import pathlib, shutil, sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_v020_compilefix.py <ByeByeDPI checkout>')

root = pathlib.Path(sys.argv[1]).resolve()
repo = pathlib.Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


# Keep ViewBinding non-null across portrait/landscape by using the same transport-test layout.
src = repo / 'overlay' / 'v020' / 'activity_main.xml'
dst = root / 'app/src/main/res/layout-land/activity_main.xml'
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(src, dst)
if src.read_text(encoding='utf-8') != dst.read_text(encoding='utf-8'):
    raise RuntimeError('landscape activity_main.xml differs after copy')

# Make the temporary test UI tell the truth about TG Auto and expose useful diagnostics.
main = root / 'app/src/main/java/io/github/romanvht/byedpi/activities/MainActivity.kt'
text = main.read_text(encoding='utf-8')
text = replace_once(
    text,
    '            running && mode == Mode.Proxy -> "Telegram защищён через локальный WSS-транспорт"\n',
    '            running && mode == Mode.Proxy -> "Telegram Auto подбирает лучший маршрут для текущей сети"\n',
    'proxy running subtitle',
)
text = replace_once(
    text,
    '            mode == Mode.Proxy -> "Рекомендуемый режим для Telegram"\n',
    '            mode == Mode.Proxy -> "Telegram Auto: Direct WSS или отдельная TG DPI-стратегия"\n',
    'proxy stopped subtitle',
)
text = replace_once(
    text,
    '            "Только Telegram • стратегии ByeDPI не влияют на 127.0.0.1:1082"\n',
    '            "Только Telegram • TG Auto сам выбирает Direct WSS или внутреннюю DPI-стратегию"\n',
    'proxy mode description',
)
old_runtime = '''    private fun updateRuntimeCard() {
        val running = appStatus.first == AppStatus.Running && TgCleanRuntime.running
        binding.tgProxyStatus.text = if (running) "127.0.0.1:1082  •  готов" else "127.0.0.1:1082  •  остановлен"
        val routeText = when (TgCleanRuntime.route) {
            "ws" -> "Маршрут: WSS"
            "direct" -> "Маршрут: прямой fallback"
            "warming" -> "Маршрут: прогрев соединений…"
            else -> "Маршрут: —"
        }
        binding.routeStatus.text = routeText
    }
'''
new_runtime = '''    private fun updateRuntimeCard() {
        val running = appStatus.first == AppStatus.Running && TgCleanRuntime.running
        val network = TgCleanRuntime.networkType.takeIf { it.isNotBlank() && it != "—" } ?: "сеть не определена"
        binding.tgProxyStatus.text = if (running) {
            "127.0.0.1:1082  •  $network"
        } else {
            "127.0.0.1:1082  •  остановлен"
        }

        val latency = TgCleanRuntime.routeLatencyMs?.let { " • ${it} мс" }.orEmpty()
        binding.routeStatus.text = when {
            !running -> "Маршрут: —"
            TgCleanRuntime.route == "probing" -> "TG Auto: подбираем маршрут…"
            TgCleanRuntime.route == "failed" -> "TG Auto: маршрут не найден"
            else -> "TG Auto: ${TgCleanRuntime.routeLabel}$latency"
        }
    }
'''
text = replace_once(text, old_runtime, new_runtime, 'TG Auto runtime card')
old_diag = '''        val text = buildString {
            appendLine("TG Clean ${BuildConfig.VERSION_NAME}")
            appendLine("Статус: ${appStatus.first}")
            appendLine("Режим: ${if (prefs.mode() == Mode.Proxy) "Telegram-only" else "System VPN"}")
            appendLine("SOCKS5: 127.0.0.1:1082")
            appendLine("TG runtime: ${TgCleanRuntime.running}")
            appendLine("Последний маршрут: ${TgCleanRuntime.route}")
            if (TgCleanRuntime.stats.isNotBlank()) appendLine("Статистика: ${TgCleanRuntime.stats}")
            TgCleanRuntime.lastError?.let { appendLine("Ошибка: $it") }
            if (prefs.mode() == Mode.VPN) appendLine("DPI: ${prefs.getCmdArgs()}")
            appendLine("ABI: ${Build.SUPPORTED_ABIS.joinToString()}")
        }
'''
new_diag = '''        val text = buildString {
            appendLine("TG Clean ${BuildConfig.VERSION_NAME}")
            appendLine("Статус: ${appStatus.first}")
            appendLine("Режим: ${if (prefs.mode() == Mode.Proxy) "Telegram Auto" else "Telegram + System VPN"}")
            appendLine("Сеть: ${TgCleanRuntime.networkType}")
            appendLine("SOCKS5: 127.0.0.1:1082")
            appendLine("TG runtime: ${TgCleanRuntime.running}")
            appendLine("TG route id: ${TgCleanRuntime.route}")
            appendLine("TG route: ${TgCleanRuntime.routeLabel}")
            TgCleanRuntime.routeLatencyMs?.let { appendLine("TG latency: $it ms") }
            if (TgCleanRuntime.probeSummary.isNotBlank()) {
                appendLine()
                appendLine("TG Auto probes:")
                appendLine(TgCleanRuntime.probeSummary)
            }
            if (TgCleanRuntime.stats.isNotBlank()) appendLine("Статистика: ${TgCleanRuntime.stats}")
            TgCleanRuntime.lastError?.let { appendLine("Ошибка: $it") }
            if (prefs.mode() == Mode.VPN) appendLine("System DPI: ${prefs.getCmdArgs()}")
            appendLine("ABI: ${Build.SUPPORTED_ABIS.joinToString()}")
        }
'''
text = replace_once(text, old_diag, new_diag, 'TG Auto diagnostics')
main.write_text(text, encoding='utf-8', newline='\n')

for required in ('TgCleanRuntime.networkType', 'TgCleanRuntime.routeLabel', 'TgCleanRuntime.routeLatencyMs', 'TG Auto probes:'):
    if required not in text:
        raise RuntimeError(f'TG Auto UI diagnostic invariant missing: {required}')

print('TG Clean transport-test UI and activity_main variants finalized')
