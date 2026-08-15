package io.github.romanvht.byedpi.activities

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.net.Uri
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowManager
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import androidx.lifecycle.lifecycleScope
import io.github.romanvht.byedpi.BuildConfig
import io.github.romanvht.byedpi.R
import io.github.romanvht.byedpi.data.*
import io.github.romanvht.byedpi.databinding.ActivityMainBinding
import io.github.romanvht.byedpi.ewenloy.tgws.SystemAutoEngine
import io.github.romanvht.byedpi.ewenloy.tgws.TgCleanRuntime
import io.github.romanvht.byedpi.ewenloy.tgws.TgNetworkMonitor
import io.github.romanvht.byedpi.services.ServiceManager
import io.github.romanvht.byedpi.services.appStatus
import io.github.romanvht.byedpi.utility.ClipboardUtils
import io.github.romanvht.byedpi.utility.getCmdArgs
import io.github.romanvht.byedpi.utility.getPreferences
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

class MainActivity : BaseActivity() {
    private lateinit var binding: ActivityMainBinding
    private val prefs by lazy { getPreferences() }
    private val handler = Handler(Looper.getMainLooper())
    private var systemAutoJob: Job? = null

    private enum class ProductMode(val key: String) {
        TELEGRAM("telegram_auto"),
        VPN("vpn_strategy"),
        FULL_AUTO("full_auto"),
    }

    private val ticker = object : Runnable {
        override fun run() {
            updateUi()
            handler.postDelayed(this, 800)
        }
    }

    private val vpnPermission = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (it.resultCode == RESULT_OK) ServiceManager.start(this, Mode.VPN)
        else Toast.makeText(this, "Разрешение VPN не выдано", Toast.LENGTH_SHORT).show()
        updateUi()
    }

    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        startInternal()
    }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                STARTED_BROADCAST, STOPPED_BROADCAST -> updateUi()
                FAILED_BROADCAST -> {
                    Toast.makeText(this@MainActivity, "Не удалось запустить сервис", Toast.LENGTH_SHORT).show()
                    updateUi()
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        if (!prefs.contains(PREF_PRODUCT_MODE)) {
            prefs.edit(commit = true) {
                putString(PREF_PRODUCT_MODE, ProductMode.TELEGRAM.key)
                putString("byedpi_mode", "proxy")
            }
        }

        val filter = IntentFilter().apply {
            addAction(STARTED_BROADCAST)
            addAction(STOPPED_BROADCAST)
            addAction(FAILED_BROADCAST)
        }
        ContextCompat.registerReceiver(this, receiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)

        binding.modeToggle.addOnButtonCheckedListener { _, checkedId, checked ->
            if (!checked || appStatus.first == AppStatus.Running || TgCleanRuntime.systemAutoRunning) {
                return@addOnButtonCheckedListener
            }
            val mode = when (checkedId) {
                R.id.mode_vpn -> ProductMode.VPN
                R.id.mode_full_auto -> ProductMode.FULL_AUTO
                else -> ProductMode.TELEGRAM
            }
            saveProductMode(mode)
            updateUi()
        }

        binding.powerButton.setOnClickListener {
            if (systemAutoJob?.isActive == true) {
                systemAutoJob?.cancel()
                Toast.makeText(this, "Подбор отменяется…", Toast.LENGTH_SHORT).show()
            } else if (appStatus.first == AppStatus.Running) {
                ServiceManager.stop(this)
            } else {
                startWithNotificationPermission()
            }
        }

        binding.setupTelegramButton.setOnClickListener { openTelegramProxySetup() }
        binding.copyProxyButton.setOnClickListener {
            ClipboardUtils.copy(this, "127.0.0.1:1082", "TG Clean SOCKS5")
            Toast.makeText(this, "127.0.0.1:1082 скопирован", Toast.LENGTH_SHORT).show()
        }
        binding.editStrategyButton.setOnClickListener { showStrategyDialog() }
        binding.systemAutoButton.setOnClickListener {
            if (appStatus.first == AppStatus.Running) {
                Toast.makeText(this, "Сначала останови сервис", Toast.LENGTH_SHORT).show()
            } else {
                runSystemAuto(startVpnAfter = false)
            }
        }
        binding.instructionsButton.setOnClickListener { showInstructions() }
        binding.diagnosticsButton.setOnClickListener { showDiagnostics() }

        updateUi()
    }

    override fun onResume() {
        super.onResume()
        updateUi()
        handler.removeCallbacks(ticker)
        handler.post(ticker)
    }

    override fun onPause() {
        handler.removeCallbacks(ticker)
        super.onPause()
    }

    override fun onDestroy() {
        handler.removeCallbacks(ticker)
        systemAutoJob?.cancel()
        runCatching { unregisterReceiver(receiver) }
        super.onDestroy()
    }

    private fun productMode(): ProductMode {
        return when (prefs.getString(PREF_PRODUCT_MODE, ProductMode.TELEGRAM.key)) {
            ProductMode.VPN.key -> ProductMode.VPN
            ProductMode.FULL_AUTO.key -> ProductMode.FULL_AUTO
            else -> ProductMode.TELEGRAM
        }
    }

    private fun saveProductMode(mode: ProductMode) {
        prefs.edit(commit = true) {
            putString(PREF_PRODUCT_MODE, mode.key)
            putString("byedpi_mode", if (mode == ProductMode.TELEGRAM) "proxy" else "vpn")
        }
    }

    private fun startWithNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            startInternal()
        }
    }

    private fun startInternal() {
        when (productMode()) {
            ProductMode.TELEGRAM -> ServiceManager.start(this, Mode.Proxy)
            ProductMode.VPN -> requestVpnAndStart()
            ProductMode.FULL_AUTO -> runSystemAuto(startVpnAfter = true)
        }
    }

    private fun requestVpnAndStart() {
        val prepare = VpnService.prepare(this)
        if (prepare != null) vpnPermission.launch(prepare) else ServiceManager.start(this, Mode.VPN)
    }

    private fun runSystemAuto(startVpnAfter: Boolean) {
        if (systemAutoJob?.isActive == true) return
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val monitor = TgNetworkMonitor(this) { }
        val snapshot = monitor.currentSnapshot()
        TgCleanRuntime.networkType = snapshot.type
        TgCleanRuntime.systemAutoError = null

        systemAutoJob = lifecycleScope.launch {
            try {
                val selection = SystemAutoEngine(this@MainActivity).select()
                if (selection == null) {
                    Toast.makeText(this@MainActivity, "System Auto не нашёл рабочую стратегию", Toast.LENGTH_LONG).show()
                    return@launch
                }

                prefs.edit(commit = true) {
                    putBoolean("byedpi_enable_cmd_settings", true)
                    putString("byedpi_cmd_args", selection.strategy)
                }
                Toast.makeText(
                    this@MainActivity,
                    "System Auto: стратегия #${selection.index}, ${selection.score}/${selection.total}",
                    Toast.LENGTH_SHORT,
                ).show()

                if (startVpnAfter) requestVpnAndStart()
            } catch (_: kotlinx.coroutines.CancellationException) {
                TgCleanRuntime.systemAutoError = "Подбор отменён"
            } catch (e: Exception) {
                TgCleanRuntime.systemAutoError = "${e.javaClass.simpleName}: ${e.message ?: "error"}"
                Toast.makeText(this@MainActivity, "Ошибка System Auto", Toast.LENGTH_LONG).show()
            } finally {
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                systemAutoJob = null
                updateUi()
            }
        }
    }

    private fun updateUi() {
        val running = appStatus.first == AppStatus.Running
        val scanning = systemAutoJob?.isActive == true || TgCleanRuntime.systemAutoRunning
        val mode = productMode()

        binding.modeTelegram.isEnabled = !running && !scanning
        binding.modeVpn.isEnabled = !running && !scanning
        binding.modeFullAuto.isEnabled = !running && !scanning

        val wanted = when (mode) {
            ProductMode.TELEGRAM -> R.id.mode_telegram
            ProductMode.VPN -> R.id.mode_vpn
            ProductMode.FULL_AUTO -> R.id.mode_full_auto
        }
        if (binding.modeToggle.checkedButtonId != wanted) binding.modeToggle.check(wanted)

        binding.powerButton.text = when {
            scanning -> "Отменить подбор"
            running -> "Остановить"
            else -> "Запустить"
        }
        binding.statusTitle.text = when {
            scanning -> "Подбираем DPI"
            running -> "Работает"
            else -> "Остановлено"
        }
        binding.statusSubtitle.text = when {
            scanning -> "${TgCleanRuntime.systemAutoPhase} ${TgCleanRuntime.systemAutoProgress}".trim()
            running && mode == ProductMode.TELEGRAM -> "Telegram Auto подбирает лучший маршрут для текущей сети"
            running && mode == ProductMode.VPN -> "Telegram Auto + выбранная системная DPI-стратегия"
            running && mode == ProductMode.FULL_AUTO -> "Telegram Auto + System Auto"
            mode == ProductMode.TELEGRAM -> "Только Telegram, без Android VPN"
            mode == ProductMode.VPN -> "Системный VPN с выбранной стратегией + TG Auto"
            else -> "Автоподбор Telegram и системного DPI независимо"
        }
        binding.statusDot.backgroundTintList = ColorStateList.valueOf(
            ContextCompat.getColor(
                this,
                when {
                    running -> R.color.tgclean_green
                    scanning -> R.color.tgclean_primary
                    else -> R.color.tgclean_muted
                },
            ),
        )

        binding.modeDescription.text = when (mode) {
            ProductMode.TELEGRAM -> "TG Auto: Direct WSS → 12 быстрых DPI → полный список стратегий."
            ProductMode.VPN -> "TG Auto работает отдельно; системный VPN использует выбранную ниже стратегию."
            ProductMode.FULL_AUTO -> "TG Auto и System Auto подбирают две независимые стратегии для текущей сети."
        }

        binding.vpnCard.visibility = if (mode == ProductMode.TELEGRAM) View.GONE else View.VISIBLE
        binding.editStrategyButton.visibility = if (mode == ProductMode.VPN) View.VISIBLE else View.GONE
        binding.systemAutoButton.visibility = if (mode == ProductMode.TELEGRAM) View.GONE else View.VISIBLE
        binding.systemAutoButton.isEnabled = !running && !scanning
        binding.strategyValue.text = prefs.getCmdArgs()
        updateSystemAutoUi(mode)
        updateRuntimeCard()
    }

    private fun updateSystemAutoUi(mode: ProductMode) {
        binding.systemAutoStatus.text = when {
            TgCleanRuntime.systemAutoRunning ->
                "${TgCleanRuntime.systemAutoPhase} • ${TgCleanRuntime.systemAutoProgress}".trim()
            TgCleanRuntime.systemStrategyIndex != null ->
                "System Auto #${TgCleanRuntime.systemStrategyIndex} • ${TgCleanRuntime.systemScore}"
            mode == ProductMode.VPN -> "Ручная стратегия. Кнопкой «Подобрать» можно заменить её автоматически."
            else -> "При запуске Full Auto сначала проверит YouTube/API/GoogleVideo и выберет стратегию."
        }
        binding.systemAutoButton.text = if (TgCleanRuntime.systemStrategyIndex == null) "Подобрать" else "Переподобрать"
    }

    private fun updateRuntimeCard() {
        val running = appStatus.first == AppStatus.Running && TgCleanRuntime.running
        binding.tgProxyStatus.text = if (running) "127.0.0.1:1082  •  готов" else "127.0.0.1:1082  •  остановлен"
        binding.routeStatus.text = when {
            !running -> "Маршрут: —"
            TgCleanRuntime.route == "probing" ->
                "TG Auto: ${TgCleanRuntime.tgProbePhase} ${TgCleanRuntime.tgProbeProgress}".trim()
            TgCleanRuntime.route == "failed" -> "TG Auto: маршрут не найден"
            else -> buildString {
                append("TG: ").append(TgCleanRuntime.routeLabel)
                TgCleanRuntime.routeLatencyMs?.let { append(" • ").append(it).append(" мс") }
            }
        }
    }

    private fun openTelegramProxySetup() {
        val tg = Uri.parse("tg://socks?server=127.0.0.1&port=1082")
        val web = Uri.parse("https://t.me/socks?server=127.0.0.1&port=1082")
        val launched = runCatching { startActivity(Intent(Intent.ACTION_VIEW, tg)); true }.getOrDefault(false)
        if (!launched) runCatching { startActivity(Intent(Intent.ACTION_VIEW, web)) }
    }

    private fun showStrategyDialog() {
        if (appStatus.first == AppStatus.Running || systemAutoJob?.isActive == true) {
            Toast.makeText(this, "Сначала останови сервис/подбор", Toast.LENGTH_SHORT).show()
            return
        }
        val input = EditText(this).apply {
            setText(prefs.getCmdArgs())
            setSelectAllOnFocus(false)
            setPadding(48, 24, 48, 24)
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle("Системная DPI-стратегия")
            .setMessage("Используется системным VPN. Telegram Auto подбирается отдельно.")
            .setView(input)
            .setPositiveButton("Сохранить", null)
            .setNeutralButton("По умолчанию", null)
            .setNegativeButton("Отмена", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val value = input.text.toString().trim()
                if (value.isEmpty()) {
                    input.error = "Стратегия не может быть пустой"
                } else {
                    prefs.edit {
                        putBoolean("byedpi_enable_cmd_settings", true)
                        putString("byedpi_cmd_args", value)
                    }
                    binding.strategyValue.text = value
                    dialog.dismiss()
                }
            }
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener {
                input.setText("-o1 -a1 -r-5+se")
            }
        }
        dialog.show()
    }

    private fun showInstructions() {
        AlertDialog.Builder(this)
            .setTitle("Как использовать TG Clean")
            .setMessage(
                "TG Auto — только Telegram через SOCKS5 127.0.0.1:1082, без Android VPN.\n\n" +
                    "VPN — Telegram Auto + системный VPN с выбранной вручную DPI-стратегией.\n\n" +
                    "Full Auto — сначала подбирает системную стратегию по YouTube/API, затем запускает VPN; Telegram подбирает свой маршрут независимо.\n\n" +
                    "Для Telegram нажми «Настроить Telegram» и подтверди SOCKS5 127.0.0.1:1082. Логин и пароль пустые."
            )
            .setPositiveButton("Понятно", null)
            .show()
    }

    private fun showDiagnostics() {
        val mode = productMode()
        val text = buildString {
            appendLine("TG Clean ${BuildConfig.VERSION_NAME}")
            appendLine("Статус: ${appStatus.first}")
            appendLine("Режим: ${mode.key}")
            appendLine("Сеть: ${TgCleanRuntime.networkType}")
            appendLine("SOCKS5: 127.0.0.1:1082")
            appendLine("TG runtime: ${TgCleanRuntime.running}")
            appendLine("TG route id: ${TgCleanRuntime.route}")
            appendLine("TG route: ${TgCleanRuntime.routeLabel}")
            TgCleanRuntime.routeLatencyMs?.let { appendLine("TG latency: $it ms") }
            if (TgCleanRuntime.tgProbePhase.isNotBlank()) {
                appendLine("TG phase: ${TgCleanRuntime.tgProbePhase} ${TgCleanRuntime.tgProbeProgress}".trim())
            }
            if (TgCleanRuntime.probeSummary.isNotBlank()) {
                appendLine()
                appendLine("TG Auto probes:")
                appendLine(TgCleanRuntime.probeSummary)
            }
            TgCleanRuntime.lastError?.let { appendLine("TG error: $it") }

            if (mode != ProductMode.TELEGRAM || TgCleanRuntime.systemStrategyIndex != null) {
                appendLine()
                appendLine("System Auto: ${TgCleanRuntime.systemAutoPhase} ${TgCleanRuntime.systemAutoProgress}".trim())
                TgCleanRuntime.systemStrategyIndex?.let { appendLine("System winner: #$it ${TgCleanRuntime.systemScore}") }
                if (TgCleanRuntime.systemAutoSummary.isNotBlank()) {
                    appendLine("System probes:")
                    appendLine(TgCleanRuntime.systemAutoSummary)
                }
                TgCleanRuntime.systemAutoError?.let { appendLine("System error: $it") }
                appendLine("System DPI: ${prefs.getCmdArgs()}")
            }
            if (TgCleanRuntime.stats.isNotBlank()) appendLine("TG stats: ${TgCleanRuntime.stats}")
            appendLine("Device ABI: ${Build.SUPPORTED_ABIS.joinToString()}")
        }
        AlertDialog.Builder(this)
            .setTitle("Диагностика")
            .setMessage(text)
            .setPositiveButton("Скопировать") { _, _ -> ClipboardUtils.copy(this, text, "TG Clean diagnostics") }
            .setNegativeButton("Закрыть", null)
            .show()
    }

    companion object {
        private const val PREF_PRODUCT_MODE = "tgclean_product_mode"
    }
}
