# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

用法：
    pip install -r requirements.txt pyinstaller
    pyinstaller --noconfirm --clean FileRenamer.spec

产物：dist/FileRenamer.exe（单文件、无控制台窗口）
"""
from PyInstaller.utils.hooks import collect_data_files

# ttkbootstrap 的主题图片位于包内 assets/ 目录，必须显式收集
datas = collect_data_files('ttkbootstrap')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FileRenamer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='tubiaobig.ico',
)