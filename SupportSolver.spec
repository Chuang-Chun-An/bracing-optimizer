# -*- mode: python ; coding: utf-8 -*-

import shutil
from pathlib import Path


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('data', 'data'),
        ('picture', 'picture'),
        ('assets/dxf', 'assets/dxf'),
    ],
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
    name='SupportSolver',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SupportSolver',
)

output_dir = Path(DISTPATH) / "SupportSolver"

shutil.copy2(
    Path(SPECPATH) / "cad_builder.lsp",
    output_dir / "cad_builder.lsp",
)

shutil.copytree(
    Path(SPECPATH) / "test_cases",
    output_dir / "test_cases",
    dirs_exist_ok=True,
)
