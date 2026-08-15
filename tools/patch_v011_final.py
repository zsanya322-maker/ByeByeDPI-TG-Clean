#!/usr/bin/env python3
"""Final least-privilege overlay for ByeByeDPI-TG-Clean v0.1.1."""

from __future__ import annotations

import pathlib
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_v011_final.py <ByeByeDPI checkout>")

root = pathlib.Path(sys.argv[1]).resolve()
manifest = root / "app/src/main/AndroidManifest.xml"
text = manifest.read_text(encoding="utf-8")

query_all = '    <uses-permission android:name="android.permission.QUERY_ALL_PACKAGES" tools:ignore="PackageVisibilityPolicy,QueryAllPackagesPermission" />\n'
if query_all not in text:
    raise RuntimeError("Expected QUERY_ALL_PACKAGES permission not found before final hardening")
text = text.replace(query_all, "", 1)

anchor = '    <uses-feature android:name="android.hardware.touchscreen" android:required="false" />\n\n    <application\n'
queries = '''    <uses-feature android:name="android.hardware.touchscreen" android:required="false" />

    <!-- Least-privilege package visibility for the per-app VPN selector. -->
    <queries>
        <intent>
            <action android:name="android.intent.action.MAIN" />
            <category android:name="android.intent.category.LAUNCHER" />
        </intent>
        <intent>
            <action android:name="android.intent.action.MAIN" />
            <category android:name="android.intent.category.LEANBACK_LAUNCHER" />
        </intent>
    </queries>

    <application
'''
if anchor not in text:
    raise RuntimeError("Manifest application anchor not found")
text = text.replace(anchor, queries, 1)
manifest.write_text(text, encoding="utf-8", newline="\n")

final = manifest.read_text(encoding="utf-8")
for forbidden in (
    "QUERY_ALL_PACKAGES",
    "MANAGE_EXTERNAL_STORAGE",
    "READ_EXTERNAL_STORAGE",
    "WRITE_EXTERNAL_STORAGE",
):
    if forbidden in final:
        raise RuntimeError(f"Least-privilege manifest invariant failed: {forbidden} remains")
for required in (
    "android.intent.category.LAUNCHER",
    "android.intent.category.LEANBACK_LAUNCHER",
    'android:allowBackup="false"',
):
    if required not in final:
        raise RuntimeError(f"Least-privilege manifest invariant missing: {required}")

print("ByeByeDPI-TG-Clean v0.1.1 final least-privilege overlay applied successfully")
