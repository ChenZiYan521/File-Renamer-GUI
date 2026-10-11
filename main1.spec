# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_submodules

datas = []
binaries = []
hiddenimports = []
datas += collect_data_files('datetime')
datas += collect_data_files('os')
datas += collect_data_files('pathlib')
datas += collect_data_files('queue')
datas += collect_data_files('re')
datas += collect_data_files('threading')
datas += collect_data_files('traceback')
datas += collect_data_files('ttkbootstrap')
datas += collect_data_files('uuid')
binaries += collect_dynamic_libs('datetime')
binaries += collect_dynamic_libs('os')
binaries += collect_dynamic_libs('pathlib')
binaries += collect_dynamic_libs('queue')
binaries += collect_dynamic_libs('re')
binaries += collect_dynamic_libs('threading')
binaries += collect_dynamic_libs('traceback')
binaries += collect_dynamic_libs('uuid')
hiddenimports += collect_submodules('datetime')
hiddenimports += collect_submodules('os')
hiddenimports += collect_submodules('pathlib')
hiddenimports += collect_submodules('queue')
hiddenimports += collect_submodules('re')
hiddenimports += collect_submodules('threading')
hiddenimports += collect_submodules('tkinter')
hiddenimports += collect_submodules('traceback')
hiddenimports += collect_submodules('ttkbootstrap')
hiddenimports += collect_submodules('uuid')


a = Analysis(
    ['D:/code/py-items/File-Renamer-GUI/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
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
    name='main1',
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
    icon=['D:\\code\\py-items\\File-Renamer-GUI\\tubiaobig.ico'],
)
