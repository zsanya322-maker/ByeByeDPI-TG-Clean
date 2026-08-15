#!/usr/bin/env python3
"""Keep TEST2 portrait/landscape activity_main layouts identical for ViewBinding."""
from __future__ import annotations
import pathlib, shutil, sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_v020_compilefix.py <ByeByeDPI checkout>')

root = pathlib.Path(sys.argv[1]).resolve()
repo = pathlib.Path(__file__).resolve().parents[1]
src = repo / 'overlay' / 'v020' / 'activity_main.xml'
dst = root / 'app/src/main/res/layout-land/activity_main.xml'
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(src, dst)

if src.read_text(encoding='utf-8') != dst.read_text(encoding='utf-8'):
    raise RuntimeError('landscape activity_main.xml differs after copy')

print('TG Clean TEST2 activity_main layout variants synchronized')
