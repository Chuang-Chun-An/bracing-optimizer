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
        ('assets/app_icon', 'assets/app_icon'),
        ('assets/software_history.json', 'assets'),
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
    icon=str(
        Path(SPECPATH)
        / 'assets'
        / 'app_icon'
        / 'support_optimizer_transparent.ico'
    ),
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

sample_dxf_output_dir = output_dir / "sample_dxf"
sample_dxf_output_dir.mkdir(exist_ok=True)

sample_dxf_sources = (
    Path(SPECPATH) / "assets" / "sample_dxf" / "Y29_test.dxf",
    Path(SPECPATH) / "assets" / "sample_dxf" / "Y1A擋土支撐簡化版.dxf",
    Path(SPECPATH)
    / "assets"
    / "sample_dxf"
    / "670-CO-Y05-FW-圖紙 - 005 - Y05站 安全支撐系統 第一層支撐平面圖.dxf",
)
for source_path in sample_dxf_sources:
    shutil.copy2(source_path, sample_dxf_output_dir / source_path.name)

release_project_source_dir = Path(SPECPATH) / "assets" / "project_cases"
release_project_output_dir = output_dir / "project_cases"
release_project_relative_paths = (
    Path("Y05車站第一層支撐") / "project.json",
    Path("Y05車站第一層支撐") / "source" / "source.dxf",
    Path("Y29車站第一層支撐") / "project.json",
    Path("Y29車站第一層支撐") / "source" / "source.dxf",
)
for relative_path in release_project_relative_paths:
    destination_path = release_project_output_dir / relative_path
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(release_project_source_dir / relative_path, destination_path)
