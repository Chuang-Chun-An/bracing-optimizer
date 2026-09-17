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
    name='SupportOptimizer',
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
    name='SupportOptimizer',
)

output_dir = Path(DISTPATH) / "SupportOptimizer"

shutil.copy2(
    Path(SPECPATH) / "cad_builder.lsp",
    output_dir / "cad_builder.lsp",
)

# Keep the Y29 regression drawing beside the executable so it can be selected
# directly from the packaged application during solver/import testing.
shutil.copy2(
    Path(SPECPATH) / "Y29_test.dxf",
    output_dir / "Y29_test.dxf",
)

shutil.copytree(
    Path(SPECPATH) / "test_cases",
    output_dir / "test_cases",
    dirs_exist_ok=True,
)

# Project cases are writable user/project files, so keep their initial content
# beside the executable instead of placing it under PyInstaller's _internal.
shutil.copytree(
    Path(SPECPATH) / "project_cases",
    output_dir / "project_cases",
    dirs_exist_ok=True,
)
