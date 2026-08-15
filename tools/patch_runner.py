#!/usr/bin/env python3
"""Run the v0.1.0 patch with narrowly-scoped compatibility fixes for ByeByeDPI 1.7.8."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_runner.py <ByeByeDPI checkout>")

root = pathlib.Path(sys.argv[1]).resolve()
patch_path = pathlib.Path(__file__).with_name("patch.py")
spec = importlib.util.spec_from_file_location("tgclean_patch", patch_path)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load patch.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT = root
module.TG_DIR = root / "app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws"

strict_replace_once = module.replace_once


def compatible_replace_once(text: str, old: str, new: str, label: str) -> str:
    # ByeDPIVpnService 1.7.8 has two tunFd?.close() sites. The first is onDestroy;
    # only that first site needs our TG listener teardown insertion.
    if label == "VPN onDestroy":
        count = text.count(old)
        if count < 1:
            raise RuntimeError(f"{label}: expected at least one match, found {count}")
        return text.replace(old, new, 1)
    return strict_replace_once(text, old, new, label)


module.replace_once = compatible_replace_once
module.main()

# The upstream NDK Application.mk has its own ABI list, independent of Gradle splits.
app_mk = root / "app/src/main/jni/Application.mk"
text = app_mk.read_text(encoding="utf-8")
old = "APP_ABI := armeabi-v7a arm64-v8a x86 x86_64"
if old in text:
    text = text.replace(old, "APP_ABI := arm64-v8a", 1)
elif "APP_ABI := arm64-v8a" not in text:
    raise RuntimeError("Could not pin Application.mk to arm64-v8a")
app_mk.write_text(text, encoding="utf-8", newline="\n")

print("Compatibility runner completed; JNI ABI pinned to arm64-v8a")
