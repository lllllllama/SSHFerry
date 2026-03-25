# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import copy_metadata

hiddenimports = [
    'src.ui.main_window',
    'src.ui.panels.local_panel',
    'src.ui.panels.remote_panel',
    'src.ui.panels.task_center',
    'src.ui.widgets.site_editor',
]


a = Analysis(
    ['src\\app\\main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('src\\ui\\assets\\app_icon.png', 'src\\ui\\assets'),
        ('src\\ui\\assets\\app_icon.ico', 'src\\ui\\assets'),
    ] + copy_metadata('paramiko'),
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.datas,
    [],
    name='SSHFerry',
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
    icon='src\\ui\\assets\\app_icon.ico',
)
