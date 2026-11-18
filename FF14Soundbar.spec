# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, SPECPATH)
from diagnostics import VERSION
from packaging_helpers import without_system_icu
from virtual_cable import CablePackage

root = Path(SPECPATH)
datas = [(str(root/'assets'/'ui'), 'assets/ui')]
optional = {
    'assets/app.ico': 'assets',
    'assets/ff14': 'assets/ff14',
    'assets/ff14-action-types.json': 'assets',
    'assets/ocr': 'assets/ocr',
    'build/release-input/sounds': 'sounds',
}
for name, destination in optional.items():
    path = root / name
    if path.exists():
        datas.append((str(path), destination))
cable = CablePackage(root, root)
if cable.path.exists():
    if not cable.available():
        raise SystemExit('VB-CABLE 安装包校验失败。')
    datas.append((str(cable.path), 'assets/vbcable'))
icon = root / 'assets' / 'app.ico'

a = Analysis(
    ['release_entry.py'], pathex=[], binaries=[],
    datas=datas,
    hiddenimports=['settings_window','sound_import_ui','skillbar_overlay'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['wheel_check','advanced_audio_check','tests','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtPdf','PySide6.QtQml','PySide6.QtQuick'],
    noarchive=False, optimize=0,
)
a.binaries = without_system_icu(a.binaries)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,a.scripts,a.binaries,a.datas,[],name=f'FF14音效技能栏_分享版_{VERSION}',icon=str(icon) if icon.is_file() else None,
    debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
    console=False,disable_windowed_traceback=False,
)
