from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE_PROJECT_DIR = PROJECT_ROOT / "assets" / "project_cases"

RELEASE_PROJECT_CASE_NAMES = (
    "Y05車站第一層支撐",
    "Y29車站第一層支撐",
)
RELEASE_PROJECT_RELATIVE_FILES = frozenset(
    {
        "project.json",
        "source/source.dxf",
    }
)
RELEASE_PROJECT_CASE_DIRS = tuple(
    RELEASE_PROJECT_DIR / case_name for case_name in RELEASE_PROJECT_CASE_NAMES
)
RELEASE_PROJECT_JSON_PATHS = tuple(
    case_dir / "project.json" for case_dir in RELEASE_PROJECT_CASE_DIRS
)

