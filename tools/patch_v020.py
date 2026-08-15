#!/usr/bin/env python3
"""Apply TG Clean v0.2.0 product/UX overlay after v0.1.1 hardening."""
from __future__ import annotations
import pathlib, re, shutil, sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_v020.py <ByeByeDPI checkout>')
root = pathlib.Path(sys.argv[1]).resolve()
repo = pathlib.Path(__file__).resolve().parents[1]
overlay = repo / 'overlay' / 'v020'

def read(rel: str) -> str:
    return (root / rel).read_text(encoding='utf-8')

def write(rel: str, text: str) -> None:
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding='utf-8', newline='\n')

def one(text: str, old: str, new: str, label: str) -> str:
    n=text.count(old)
    if n != 1: raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return text.replace(old,new,1)

def cp(name: str, rel: str) -> None:
    src=overlay/name; dst=root/rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src,dst)

g='app/build.gradle.kts'; t=read(g)
t=one(t,'versionCode = 178011','versionCode = 178020','versionCode')
t=one(t,'versionName = "1.7.8-tgclean-0.1.1"','versionName = "2.0.0-tgclean"','versionName')
write(g,t)

s='app/src/main/res/values/strings.xml'; t=read(s)
t=t.replace('<string name="app_name">ByeByeDPI TG Clean</string>','<string name="app_name">TG Clean</string>',1)
t=t.replace('<string name="notification_title">ByeByeDPI TG Clean</string>','<string name="notification_title">TG Clean</string>',1)
t=re.sub(r'<string name="proxy_notification_content">.*?</string>','<string name="proxy_notification_content">Telegram-транспорт активен</string>',t,count=1)
t=re.sub(r'<string name="vpn_notification_content">.*?</string>','<string name="vpn_notification_content">Telegram + системный VPN активны</string>',t,count=1)
write(s,t)

cp('MainActivity.kt','app/src/main/java/io/github/romanvht/byedpi/activities/MainActivity.kt')
cp('activity_main.xml','app/src/main/res/layout/activity_main.xml')
cp('TgCleanRuntime.kt','app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/TgCleanRuntime.kt')
cp('tgclean_colors.xml','app/src/main/res/values/tgclean_colors.xml')
cp('tgclean_colors_night.xml','app/src/main/res/values-night/tgclean_colors.xml')
cp('tgclean_dot.xml','app/src/main/res/drawable/tgclean_dot.xml')
cp('tgclean_code_bg.xml','app/src/main/res/drawable/tgclean_code_bg.xml')
cp('ic_tgclean.xml','app/src/main/res/drawable/ic_tgclean.xml')

c='app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/TgCleanController.kt'; t=read(c)
t=one(t,'            onRouteStatus = { mode -> Log.d(TAG, "Telegram route=$mode") },\n            onStats = { stats -> Log.d(TAG, stats) },','            onRouteStatus = { mode -> TgCleanRuntime.route = mode; Log.d(TAG, "Telegram route=$mode") },\n            onStats = { stats -> TgCleanRuntime.stats = stats; Log.d(TAG, stats) },','runtime callbacks')
t=one(t,'        if (!candidate.isRunning()) {\n            candidate.stop()\n            throw IllegalStateException("Unable to bind Telegram SOCKS5 on 127.0.0.1:$PORT")\n        }\n        server = candidate\n        candidate.warmup()','        if (!candidate.isRunning()) {\n            candidate.stop()\n            TgCleanRuntime.running = false\n            TgCleanRuntime.lastError = "Не удалось открыть 127.0.0.1:$PORT"\n            throw IllegalStateException("Unable to bind Telegram SOCKS5 on 127.0.0.1:$PORT")\n        }\n        server = candidate\n        TgCleanRuntime.running = true\n        TgCleanRuntime.route = "warming"\n        TgCleanRuntime.lastError = null\n        candidate.warmup()','runtime start')
t=one(t,'        val current = server ?: return\n        server = null\n        runCatching { current.stop() }','        val current = server ?: run { TgCleanRuntime.running = false; TgCleanRuntime.route = "idle"; return }\n        server = null\n        TgCleanRuntime.running = false\n        TgCleanRuntime.route = "idle"\n        runCatching { current.stop() }','runtime stop')
write(c,t)

sv='app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/EwenloyTgWsProxyServer.kt'; t=read(sv)
t=one(t,'            "blocked=${blockedNonTelegram.get()} up=${bytesUp.get()} down=${bytesDown.get()}"','            "blocked=${blockedNonTelegram.get()} wsErr=${wsErrors.get()} httpReject=${httpRejected.get()} up=${bytesUp.get()} down=${bytesDown.get()}"','stats')
write(sv,t)

p='app/src/main/java/io/github/romanvht/byedpi/services/ByeDpiProxyService.kt'; t=read(p)
t=one(t,'            mutex.withLock {\n                startProxy()\n                tgClean.start()\n                updateStatus(ServiceStatus.Connected)\n            }','            mutex.withLock {\n                tgClean.start()\n                updateStatus(ServiceStatus.Connected)\n            }','TG-only start')
t=one(t,'            withContext(Dispatchers.IO) {\n                tgClean.stop()\n                stopProxy()\n            }','            withContext(Dispatchers.IO) {\n                tgClean.stop()\n            }','TG-only stop')
write(p,t)

m='app/src/main/AndroidManifest.xml'; t=read(m)
for permission in ('android.permission.RECEIVE_BOOT_COMPLETED','android.permission.QUICKBOOT_POWERON','android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS','android.permission.FOREGROUND_SERVICE_SPECIAL_USE'):
    t=re.sub(rf'\s*<uses-permission android:name="{re.escape(permission)}"[^>]*/>','',t,count=1)
for activity in ('ToggleActivity','SettingsActivity','FileActivity','TestActivity','TestSettingsActivity'):
    t=re.sub(rf'\n\s*<activity\n\s*android:name="\.activities\.{activity}"[\s\S]*?</activity>\s*', '\n', t, count=1)
    t=re.sub(rf'\n\s*<activity\n\s*android:name="\.activities\.{activity}"[\s\S]*?/>\s*', '\n', t, count=1)
t=re.sub(r'\n\s*<receiver\n\s*android:name="\.receiver\.BootReceiver"[\s\S]*?</receiver>\s*','\n',t,count=1)
t=re.sub(r'android:logo="@[^"]+"','android:logo="@drawable/ic_tgclean"',t,count=1)
t=re.sub(r'android:icon="@[^"]+"','android:icon="@drawable/ic_tgclean"',t,count=1)
t=re.sub(r'android:roundIcon="@[^"]+"','android:roundIcon="@drawable/ic_tgclean"',t,count=1)
write(m,t)

assert 'versionName = "2.0.0-tgclean"' in read(g)
assert 'TG Clean' in read(s)
assert 'startProxy()\n                tgClean.start()' not in read(p)
assert 'directPassthrough(c, input, output, addr, port)' not in read(sv)
assert 'tg://socks?server=127.0.0.1&port=1082' in read('app/src/main/java/io/github/romanvht/byedpi/activities/MainActivity.kt')
for forbidden in ('QUERY_ALL_PACKAGES','MANAGE_EXTERNAL_STORAGE','READ_EXTERNAL_STORAGE','WRITE_EXTERNAL_STORAGE','RECEIVE_BOOT_COMPLETED','REQUEST_IGNORE_BATTERY_OPTIMIZATIONS'):
    if forbidden in read(m): raise RuntimeError(f'forbidden manifest token remains: {forbidden}')
print('TG Clean v0.2.0 overlay applied successfully')
