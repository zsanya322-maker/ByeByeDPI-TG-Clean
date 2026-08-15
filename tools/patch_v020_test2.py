#!/usr/bin/env python3
"""Apply TG Clean v0.2.0 TEST2: 12->60 TG Auto + independent System Auto."""
from __future__ import annotations
import pathlib, shutil, sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_v020_test2.py <ByeByeDPI checkout>')

root = pathlib.Path(sys.argv[1]).resolve()
repo = pathlib.Path(__file__).resolve().parents[1]
overlay = repo / 'overlay' / 'v020'


def read(rel: str) -> str:
    return (root / rel).read_text(encoding='utf-8')


def write(rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8', newline='\n')


def one(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)


def cp(name: str, rel: str) -> None:
    src = overlay / name
    dst = root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


for name in (
    'SystemDpiProbeService.kt',
    'SystemDpiProbeController.kt',
    'SystemAutoEngine.kt',
):
    cp(name, f'app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/{name}')

# Make TEST2 an installable upgrade over TEST1.
gradle_rel = 'app/build.gradle.kts'
t = read(gradle_rel)
t = one(t, 'versionCode = 178020', 'versionCode = 178021', 'TEST2 versionCode')
t = one(t, 'versionName = "2.0.0-tgclean"', 'versionName = "2.0.0-tgclean-test2"', 'TEST2 versionName')
write(gradle_rel, t)

# A third isolated process is used only while probing system/YouTube strategies.
manifest_rel = 'app/src/main/AndroidManifest.xml'
t = read(manifest_rel)
tg_service = '''        <service
            android:name=".ewenloy.tgws.TgDpiService"
            android:process=":tg_dpi"
            android:exported="false" />
'''
probe_service = tg_service + '''
        <service
            android:name=".ewenloy.tgws.SystemDpiProbeService"
            android:process=":system_probe"
            android:exported="false" />
'''
t = one(t, tg_service, probe_service, 'System DPI probe service')
write(manifest_rel, t)

# Invariants for TEST2.
main = read('app/src/main/java/io/github/romanvht/byedpi/activities/MainActivity.kt')
tg_auto = read('app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/TgAutoEngine.kt')
system_auto = read('app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/SystemAutoEngine.kt')
manifest = read(manifest_rel)

for token in ('ProductMode.FULL_AUTO', 'SystemAutoEngine', 'mode_full_auto', 'runSystemAuto'):
    if token not in main:
        raise RuntimeError(f'TEST2 MainActivity invariant missing: {token}')
for token in ('FAST_INDICES', 'Глубокий TG DPI', 'VERIFY_DCS', 'proxytest_strategies.list'):
    if token not in tg_auto:
        raise RuntimeError(f'TEST2 TG Auto invariant missing: {token}')
for token in ('FAST_INDICES', 'Глубокий подбор', 'proxytest_youtube.sites', 'SystemDpiProbeService.PORT'):
    if token not in system_auto:
        raise RuntimeError(f'TEST2 System Auto invariant missing: {token}')
for token in ('android:process=":tg_dpi"', 'android:process=":system_probe"'):
    if token not in manifest:
        raise RuntimeError(f'TEST2 process invariant missing: {token}')
if 'versionName = "2.0.0-tgclean-test2"' not in read(gradle_rel):
    raise RuntimeError('TEST2 version not applied')
print('TG Clean v0.2.0 TEST2 dual-auto overlay applied successfully')
