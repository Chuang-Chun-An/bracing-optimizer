from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DXF_DIR = PROJECT_ROOT / "assets" / "sample_dxf"

Y29_DXF_PATH = SAMPLE_DXF_DIR / "Y29_test.dxf"
Y1A_DXF_PATH = SAMPLE_DXF_DIR / "Y1A擋土支撐簡化版.dxf"
Y05_DXF_PATH = (
    SAMPLE_DXF_DIR
    / "670-CO-Y05-FW-圖紙 - 005 - Y05站 安全支撐系統 第一層支撐平面圖.dxf"
)

SAMPLE_DXF_PATHS = (
    Y29_DXF_PATH,
    Y1A_DXF_PATH,
    Y05_DXF_PATH,
)
SAMPLE_DXF_FILENAMES = frozenset(path.name for path in SAMPLE_DXF_PATHS)
