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
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import io.github.romanvht.byedpi.BuildConfig
import io.github.romanvht.byedpi.R
import io.github.romanvht.byedpi.data.*
import io.github.romanvht.byedpi.databinding.ActivityMainBinding
import io.github.romanvht.byedpi.ewenloy.tgws.TgCleanRuntime
import io.github.romanvht.byedpi.services.ServiceManager
import io.github.romanvht.byedpi.services.appStatus
import io.github.romanvht.byedpi.utility.ClipboardUtils
import io.github.romanvht.byedpi.utility.getCmdArgs
import io.github.romanvht.byedpi.utility.getPreferences
import io.github.romanvht.byedpi.utility.mode

class MainActivity : BaseActivity() {
    private lateinit var binding: ActivityMainBinding
    private val prefs by lazy { getPreferences() }
    private val handler = Handler(Looper.getMainLooper())

    private val ticker = object : Runnable {
        override fun run() {
            updateRuntimeCard()
            handler.postDelayed(this, 1000)
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

        if (!prefs.contains("tgclean_v020_initialized")) {
            prefs.edit(commit = true) {
                putString("byedpi_mode", "proxy")
                putBoolean("tgclean_v020_initialized", true)
            }
        }

        val filter = IntentFilter().apply {
            addAction(STARTED_BROADCAST)
            addAction(STOPPED_BROADCAST)
            addAction(FAILED_BROADCAST)
        }
        ContextCompat.registerReceiver(this, receiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)

        binding.modeToggle.check(if (prefs.mode() == Mode.VPN) R.id.mode_vpn else R.id.mode_telegram)
        binding.modeToggle.addOnButtonCheckedListener { _, checkedId, checked ->
            if (!checked || appStatus.first == AppStatus.Running) return@addOnButtonCheckedListener
            prefs.edit { putString("byedpi_mode", if (checkedId == R.id.mode_vpn) "vpn" else "proxy") }
            updateUi()
        }

        binding.powerButton.setOnClickListener {
            if (appStatus.first == AppStatus.Running) ServiceManager.stop(this) else startWithNotificationPermission()
        }
        binding.setupTelegramButton.setOnClickListener { openTelegramProxySetup() }
        binding.copyProxyButton.setOnClickListener {
            ClipboardUtils.copy(this, "127.0.0.1:1082", "TG Clean SOCKS5")
            Toast.makeText(this, "127.0.0.1:1082 скопирован", Toast.LENGTH_SHORT).show()
        }
        binding.editStrategyButton.setOnClickListener { showStrategyDialog() }
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
        runCatching { unregisterReceiver(receiver) }
        super.onDestroy()
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
        when (prefs.mode()) {
            Mode.Proxy -> ServiceManager.start(this, Mode.Proxy)
            Mode.VPN -> {
                val prepare = VpnService.prepare(this)
                if (prepare != null) vpnPermission.launch(prepare) else ServiceManager.start(this, Mode.VPN)
            }
        }
    }

    private fun updateUi() {
        val running = appStatus.first == AppStatus.Running
        val mode = prefs.mode()

        binding.modeTelegram.isEnabled = !running
        binding.modeVpn.isEnabled = !running
        val wanted = if (mode == Mode.VPN) R.id.mode_vpn else R.id.mode_telegram
        if (binding.modeToggle.checkedButtonId != wanted) binding.modeToggle.check(wanted)

        binding.powerButton.text = if (running) "Остановить" else "Запустить"
        binding.statusTitle.text = if (running) "Работает" else "Остановлено"
        binding.statusSubtitle.text = when {
            running && mode == Mode.Proxy -> "Telegram защищён через локальный WSS-транспорт"
            running && mode == Mode.VPN -> "Telegram + системный обход включены"
            mode == Mode.Proxy -> "Рекомендуемый режим для Telegram"
            else -> "Системный VPN зависит от выбранной DPI-стратегии"
        }
        binding.statusDot.backgroundTintList = ColorStateList.valueOf(
            ContextCompat.getColor(this, if (running) R.color.tgclean_green else R.color.tgclean_muted)
        )
        binding.modeDescription.text = if (mode == Mode.Proxy) {
            "Только Telegram • стратегии ByeDPI не влияют на 127.0.0.1:1082"
        } else {
            "Telegram + весь телефон • сайты вроде YouTube зависят от DPI-стратегии и сети"
        }
        binding.vpnCard.visibility = if (mode == Mode.VPN) android.view.View.VISIBLE else android.view.View.GONE
        binding.strategyValue.text = prefs.getCmdArgs()
        updateRuntimeCard()
    }

    private fun updateRuntimeCard() {
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

    private fun openTelegramProxySetup() {
        val tg = Uri.parse("tg://socks?server=127.0.0.1&port=1082")
        val web = Uri.parse("https://t.me/socks?server=127.0.0.1&port=1082")
        val launched = runCatching { startActivity(Intent(Intent.ACTION_VIEW, tg)); true }.getOrDefault(false)
        if (!launched) runCatching { startActivity(Intent(Intent.ACTION_VIEW, web)) }
    }

    private fun showStrategyDialog() {
        if (appStatus.first == AppStatus.Running) {
            Toast.makeText(this, "Сначала останови сервис", Toast.LENGTH_SHORT).show()
            return
        }
        val input = EditText(this).apply {
            setText(prefs.getCmdArgs())
            setSelectAllOnFocus(false)
            setPadding(48, 24, 48, 24)
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle("DPI-стратегия")
            .setMessage("Нужна только для системного VPN. На Telegram-прокси 1082 не влияет.")
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
            .setTitle("Как подключить Telegram")
            .setMessage(
                "1. Выбери «Только Telegram».\n\n" +
                "2. Нажми «Запустить».\n\n" +
                "3. Нажми «Настроить Telegram» — TG Clean передаст Telegram SOCKS5 127.0.0.1:1082.\n\n" +
                "4. В Telegram включи предложенный прокси. Логин и пароль не нужны.\n\n" +
                "Если нужен обход для других приложений, переключись на «Системный VPN». Telegram-транспорт при этом остаётся отдельным."
            )
            .setPositiveButton("Понятно", null)
            .show()
    }

    private fun showDiagnostics() {
        val text = buildString {
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
        AlertDialog.Builder(this)
            .setTitle("Диагностика")
            .setMessage(text)
            .setPositiveButton("Скопировать") { _, _ -> ClipboardUtils.copy(this, text, "TG Clean diagnostics") }
            .setNegativeButton("Закрыть", null)
            .show()
    }
}
