#!/usr/bin/env python3
"""Apply ByeByeDPI-TG-Clean v0.1.1 security hardening on pinned ByeByeDPI 1.7.8."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_v011.py <ByeByeDPI checkout>")

root = pathlib.Path(sys.argv[1]).resolve()
base_patch_path = pathlib.Path(__file__).with_name("patch.py")

spec = importlib.util.spec_from_file_location("tgclean_base_patch", base_patch_path)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load patch.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

module.ROOT = root
module.TG_DIR = root / "app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws"

strict_replace_once = module.replace_once


def compatible_replace_once(text: str, old: str, new: str, label: str) -> str:
    if label == "VPN onDestroy":
        count = text.count(old)
        if count < 1:
            raise RuntimeError(f"{label}: expected at least one match, found {count}")
        return text.replace(old, new, 1)
    return strict_replace_once(text, old, new, label)


module.replace_once = compatible_replace_once

# Strengthen the secure v0.1.0 WebSocket implementation before base patch writes it.
raw = module.SECURE_RAW_WEBSOCKET
raw = raw.replace(
    '            val fin = (hdr1 and 0x80) != 0\n'
    '            val opcode = hdr1 and 0x0f\n'
    '            val masked = (hdr2 and 0x80) != 0\n',
    '            val fin = (hdr1 and 0x80) != 0\n'
    '            val rsv = hdr1 and 0x70\n'
    '            val opcode = hdr1 and 0x0f\n'
    '            val masked = (hdr2 and 0x80) != 0\n'
    '            if (rsv != 0) throw IllegalStateException("Unexpected WebSocket RSV bits")\n'
    '            if (masked) throw IllegalStateException("Server WebSocket frames must not be masked")\n',
    1,
)
raw = raw.replace(
    '            if (len < 0 || len > MAX_WS_FRAME_PAYLOAD) {\n'
    '                close()\n'
    '                return null\n'
    '            }\n',
    '            if (len < 0 || len > MAX_WS_FRAME_PAYLOAD) {\n'
    '                close()\n'
    '                return null\n'
    '            }\n'
    '            if (opcode >= 0x8 && (!fin || len > 125)) {\n'
    '                throw IllegalStateException("Invalid WebSocket control frame")\n'
    '            }\n'
    '            if (opcode !in setOf(0x0, 0x2, 0x8, 0x9, 0xA)) {\n'
    '                throw IllegalStateException("Unexpected WebSocket opcode: $opcode")\n'
    '            }\n',
    1,
)
raw = raw.replace(
    '                0x0 -> {\n'
    '                    if (!fragmentOpen) continue\n'
    '                    message.write(payload)\n'
    '                    if (fin) {\n'
    '                        fragmentOpen = false\n'
    '                        return message.toByteArray()\n'
    '                    }\n'
    '                }\n'
    '                0x1, 0x2 -> {\n'
    '                    if (fragmentOpen) message.reset()\n'
    '                    fragmentOpen = !fin\n'
    '                    message.reset()\n'
    '                    message.write(payload)\n'
    '                    if (fin) {\n'
    '                        fragmentOpen = false\n'
    '                        return message.toByteArray()\n'
    '                    }\n'
    '                }\n'
    '                else -> continue\n',
    '                0x0 -> {\n'
    '                    if (!fragmentOpen) throw IllegalStateException("Unexpected WebSocket continuation")\n'
    '                    message.write(payload)\n'
    '                    if (fin) {\n'
    '                        fragmentOpen = false\n'
    '                        return message.toByteArray()\n'
    '                    }\n'
    '                }\n'
    '                0x2 -> {\n'
    '                    if (fragmentOpen) throw IllegalStateException("New WebSocket data frame during fragmentation")\n'
    '                    fragmentOpen = !fin\n'
    '                    message.reset()\n'
    '                    message.write(payload)\n'
    '                    if (fin) {\n'
    '                        fragmentOpen = false\n'
    '                        return message.toByteArray()\n'
    '                    }\n'
    '                }\n'
    '                else -> throw IllegalStateException("Unexpected WebSocket opcode: $opcode")\n',
    1,
)
raw = raw.replace(
    '                val headers = linkedMapOf<String, String>()\n'
    '                while (true) {\n',
    '                val headers = linkedMapOf<String, String>()\n'
    '                var headerCount = 0\n'
    '                while (true) {\n',
    1,
)
raw = raw.replace(
    '                    if (line.isEmpty()) break\n'
    '                    val idx = line.indexOf(\':\')\n',
    '                    if (line.isEmpty()) break\n'
    '                    headerCount++\n'
    '                    if (headerCount > 64) throw IllegalStateException("Too many WebSocket response headers")\n'
    '                    val idx = line.indexOf(\':\')\n',
    1,
)
if raw == module.SECURE_RAW_WEBSOCKET:
    raise RuntimeError("WebSocket hardening did not apply")
module.SECURE_RAW_WEBSOCKET = raw
module.TG_CONTROLLER = module.TG_CONTROLLER.replace(
    "/** Minimal v0.1.0 lifecycle wrapper. The local endpoint is loopback-only. */",
    "/** v0.1.1 lifecycle wrapper. The Telegram SOCKS endpoint is loopback-only. */",
    1,
)

module.main()

# Pin JNI ABI independently of Gradle split configuration.
app_mk = root / "app/src/main/jni/Application.mk"
text = app_mk.read_text(encoding="utf-8")
old_abis = "APP_ABI := armeabi-v7a arm64-v8a x86 x86_64"
if old_abis in text:
    text = text.replace(old_abis, "APP_ABI := arm64-v8a", 1)
elif "APP_ABI := arm64-v8a" not in text:
    raise RuntimeError("Could not pin Application.mk to arm64-v8a")
app_mk.write_text(text, encoding="utf-8", newline="\n")

# Bump fork version.
gradle = root / "app/build.gradle.kts"
text = gradle.read_text(encoding="utf-8")
text = strict_replace_once(text, "versionCode = 178001", "versionCode = 178011", "v0.1.1 versionCode")
text = strict_replace_once(
    text,
    'versionName = "1.7.8-tgclean-0.1.0"',
    'versionName = "1.7.8-tgclean-0.1.1"',
    "v0.1.1 versionName",
)
gradle.write_text(text, encoding="utf-8", newline="\n")

# Manifest hardening.
manifest = root / "app/src/main/AndroidManifest.xml"
text = manifest.read_text(encoding="utf-8")
for permission_line in (
    '    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />\n',
    '    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />\n',
    '    <uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE" tools:ignore="AllFilesAccessPolicy,ScopedStorage" />\n',
):
    if permission_line not in text:
        raise RuntimeError(f"Expected storage permission missing before hardening: {permission_line.strip()}")
    text = text.replace(permission_line, "", 1)
text = strict_replace_once(text, '        android:allowBackup="true"\n', '        android:allowBackup="false"\n', "allowBackup")
text = text.replace('        android:dataExtractionRules="@xml/data_extraction_rules"\n', "", 1)
text = text.replace('        android:fullBackupContent="@xml/backup_rules"\n', "", 1)
text = text.replace('        android:requestLegacyExternalStorage="true"\n', "", 1)
text = strict_replace_once(
    text,
    '        <activity\n            android:name=".activities.SettingsActivity"\n            android:label="@string/title_settings"\n            android:exported="true"/>',
    '        <activity\n            android:name=".activities.SettingsActivity"\n            android:label="@string/title_settings"\n            android:exported="false"/>',
    "SettingsActivity exported",
)
manifest.write_text(text, encoding="utf-8", newline="\n")

# SAF-only file import/export: no broad storage privilege on normal Android phones.
file_activity = root / "app/src/main/java/io/github/romanvht/byedpi/activities/FileActivity.kt"
text = file_activity.read_text(encoding="utf-8")
old = '''        if (!externalRequestActive) {
            when {
                PermissionUtils.hasStorageAccess(this) -> showInitialDirectory(savedInstanceState)
                hasSystemFilePicker() -> openSystemFilePicker()
                else -> showStorageAccessDialog()
            }
        }
'''
new = '''        if (!externalRequestActive) {
            if (hasSystemFilePicker()) {
                openSystemFilePicker()
            } else {
                Toast.makeText(this, R.string.file_picker_unavailable, Toast.LENGTH_LONG).show()
                finish()
            }
        }
'''
text = strict_replace_once(text, old, new, "SAF-only FileActivity")
file_activity.write_text(text, encoding="utf-8", newline="\n")

# Hide obsolete broad-storage preference.
main_settings = root / "app/src/main/java/io/github/romanvht/byedpi/fragments/MainSettingsFragment.kt"
text = main_settings.read_text(encoding="utf-8")
listener = '''        findPreferenceNotNull<Preference>("storage_access")
            .setOnPreferenceClickListener {
                PermissionUtils.requestStorageAccess(this)
                true
            }

'''
text = strict_replace_once(text, listener, "", "remove storage permission click handler")
summary = '''        if (PermissionUtils.hasStorageAccess(requireContext())) {
            storageAccess.summary = getString(R.string.storage_access_allowed_summary)
        } else {
            storageAccess.summary = getString(R.string.storage_access_summary)
        }
'''
text = strict_replace_once(text, summary, '        storageAccess.isVisible = false\n', "hide storage access preference")
main_settings.write_text(text, encoding="utf-8", newline="\n")

# Token-gate exported ToggleActivity while preserving dynamic launcher shortcuts.
shortcut_utils = root / "app/src/main/java/io/github/romanvht/byedpi/utility/ShortcutUtils.kt"
text = shortcut_utils.read_text(encoding="utf-8")
text = strict_replace_once(
    text,
    'import android.os.Build\n',
    'import android.os.Build\nimport androidx.core.content.edit\nimport java.util.UUID\n',
    "shortcut imports",
)
text = strict_replace_once(
    text,
    '            val shortcuts = mutableListOf<ShortcutInfo>()\n\n',
    '            val shortcuts = mutableListOf<ShortcutInfo>()\n'
    '            val prefs = context.getPreferences()\n'
    '            val shortcutToken = prefs.getString("tgclean_shortcut_token", null)\n'
    '                ?: UUID.randomUUID().toString().also { token ->\n'
    '                    prefs.edit(commit = true) { putString("tgclean_shortcut_token", token) }\n'
    '                }\n\n',
    "shortcut token creation",
)
text = text.replace(
    '                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK\n',
    '                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK\n'
    '                putExtra("tgclean_shortcut_token", shortcutToken)\n',
)
if text.count('putExtra("tgclean_shortcut_token", shortcutToken)') < 2:
    raise RuntimeError("Shortcut token was not added to all shortcut intents")
shortcut_utils.write_text(text, encoding="utf-8", newline="\n")

toggle_activity = root / "app/src/main/java/io/github/romanvht/byedpi/activities/ToggleActivity.kt"
text = toggle_activity.read_text(encoding="utf-8")
old = '''        prefs = getPreferences()
        val strategy = intent.getStringExtra("strategy")
'''
new = '''        prefs = getPreferences()
        val expectedToken = prefs.getString("tgclean_shortcut_token", null)
        val suppliedToken = intent.getStringExtra("tgclean_shortcut_token")
        if (expectedToken.isNullOrBlank() || suppliedToken != expectedToken) {
            Log.w(TAG, "Rejected external ToggleActivity invocation")
            finish()
            return
        }

        val strategy = intent.getStringExtra("strategy")
'''
text = strict_replace_once(text, old, new, "ToggleActivity token validation")
toggle_activity.write_text(text, encoding="utf-8", newline="\n")

# Telegram SOCKS hardening: negotiate no-auth correctly and block all non-Telegram destinations.
tg_server = module.TG_DIR / "EwenloyTgWsProxyServer.kt"
text = tg_server.read_text(encoding="utf-8")
old = '''        val nMethods = greeting[1].toInt() and 0xff
        if (!readFully(input, ByteArray(nMethods))) return
        output.write(byteArrayOf(0x05, 0x00)); output.flush()
'''
new = '''        val nMethods = greeting[1].toInt() and 0xff
        if (nMethods !in 1..32) return
        val methods = ByteArray(nMethods)
        if (!readFully(input, methods)) return
        if (methods.none { (it.toInt() and 0xff) == 0x00 }) {
            output.write(byteArrayOf(0x05, 0xff.toByte())); output.flush()
            return
        }
        output.write(byteArrayOf(0x05, 0x00)); output.flush()
'''
text = strict_replace_once(text, old, new, "SOCKS method negotiation")
old = '''        if (!EwenloyTelegramRanges.isTelegramIp(addr)) {
            stats.passthrough.incrementAndGet()
            directPassthrough(c, input, output, addr, port)
            return
        }
'''
new = '''        if (!EwenloyTelegramRanges.isTelegramIp(addr)) {
            stats.blockedNonTelegram.incrementAndGet()
            sendReply(output, 0x02)
            return
        }
'''
text = strict_replace_once(text, old, new, "Telegram-only destination policy")
text = strict_replace_once(
    text,
    '        val tcpFallback = AtomicLong(0); val passthrough = AtomicLong(0)\n',
    '        val tcpFallback = AtomicLong(0); val blockedNonTelegram = AtomicLong(0)\n',
    "stats blocked counter",
)
text = strict_replace_once(
    text,
    '            "pass=${passthrough.get()} up=${bytesUp.get()} down=${bytesDown.get()}"\n',
    '            "blocked=${blockedNonTelegram.get()} up=${bytesUp.get()} down=${bytesDown.get()}"\n',
    "stats summary",
)
tg_server.write_text(text, encoding="utf-8", newline="\n")

# Exact DC2 endpoint that sits outside the coarse Telegram prefixes.
tg_ranges = module.TG_DIR / "EwenloyTelegramRanges.kt"
text = tg_ranges.read_text(encoding="utf-8")
needle = '        "91.108.0.0" to "91.108.255.255",\n'
text = strict_replace_once(
    text,
    needle,
    needle + '        "95.161.76.100" to "95.161.76.100",\n',
    "Telegram exact endpoint allowlist",
)
tg_ranges.write_text(text, encoding="utf-8", newline="\n")

# Keep status broadcasts package-local.
for service_name in ("ByeDpiVpnService.kt", "ByeDpiProxyService.kt"):
    service = root / "app/src/main/java/io/github/romanvht/byedpi/services" / service_name
    text = service.read_text(encoding="utf-8")
    marker = '        intent.putExtra(SENDER, Sender.'
    idx = text.find(marker)
    if idx < 0:
        raise RuntimeError(f"{service_name}: status broadcast marker missing")
    text = text[:idx] + '        intent.setPackage(packageName)\n' + text[idx:]
    service.write_text(text, encoding="utf-8", newline="\n")

# Final security invariants.
manifest_text = manifest.read_text(encoding="utf-8")
for forbidden in (
    "MANAGE_EXTERNAL_STORAGE",
    "READ_EXTERNAL_STORAGE",
    "WRITE_EXTERNAL_STORAGE",
    'android:allowBackup="true"',
):
    if forbidden in manifest_text:
        raise RuntimeError(f"manifest hardening failed; forbidden token remains: {forbidden}")
if 'android:allowBackup="false"' not in manifest_text:
    raise RuntimeError("manifest hardening failed: backups not disabled")

server_text = tg_server.read_text(encoding="utf-8")
if "directPassthrough(c, input, output, addr, port)" in server_text:
    raise RuntimeError("generic SOCKS passthrough remains reachable")
if "blockedNonTelegram" not in server_text or "sendReply(output, 0x02)" not in server_text:
    raise RuntimeError("Telegram-only SOCKS policy missing")

raw_text = (module.TG_DIR / "EwenloyRawWebSocket.kt").read_text(encoding="utf-8")
for required in (
    'endpointIdentificationAlgorithm = "HTTPS"',
    "getDefaultHostnameVerifier",
    "Server WebSocket frames must not be masked",
    "Invalid WebSocket control frame",
    "Too many WebSocket response headers",
):
    if required not in raw_text:
        raise RuntimeError(f"WebSocket hardening invariant missing: {required}")
for forbidden in ("X509TrustManager", "checkServerTrusted", "trustAll"):
    if forbidden in raw_text:
        raise RuntimeError(f"unsafe TLS token remains: {forbidden}")

print("ByeByeDPI-TG-Clean v0.1.1 security hardening applied successfully")
