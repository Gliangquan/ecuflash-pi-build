# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

icon_datas = []
icon_dir = Path('icon')
if icon_dir.exists():
    for item in icon_dir.iterdir():
        if item.is_file():
            icon_datas.append((str(item), 'icon'))
if Path('icon.jpg').exists():
    icon_datas.append(('icon.jpg', '.'))

app_icon = None
if Path('icon.icns').exists():
    app_icon = 'icon.icns'
elif Path('icon.ico').exists():
    app_icon = 'icon.ico'


a = Analysis(
    ['frontend.py'],
    pathex=[],
    binaries=[],
    datas=icon_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ECUFlash',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ECUFlash',
)
app = BUNDLE(
    coll,
    name='ECUFlash.app',
    icon=app_icon,
    bundle_identifier=None,
)
