# Test Fixture Ownership

本目錄只保存具有直接 automated consumer 的非 Project 測試資料。正式 DXF 使用者素材、Project case、Project JSON、managed `source/source.dxf` 與 manual-only 歷史案例不得放入本目錄。

## 保留的 fixture

| Path | Owner／consumer | 用途 | Release |
| --- | --- | --- | --- |
| `cad/cad_bridge_event_examples.json` | `tests/test_cad_builder_integration.py` | 驗證 CAD bridge event 種類與 payload contract | 不打包 |

## 正式使用者素材（不是 fixture）

下列檔案的 authoritative source 位於 `assets/sample_dxf/`，同時供正式發行包與相關 DXF regression tests 使用；`tests/fixtures/` 不保存副本。

- `Y29_test.dxf`
- `Y1A擋土支撐簡化版.dxf`
- `670-CO-Y05-FW-圖紙 - 005 - Y05站 安全支撐系統 第一層支撐平面圖.dxf`

## Project case 移除對照

| 原路徑 | 既有 consumer／狀態 | 替代方式 |
| --- | --- | --- |
| `project_cases/Y1A站第一層支撐/project.json` | `tests/test_dxf_export_validation.py`、`tests/test_support_shim_fixture_regression.py` | 測試以既有 model／persistence API 程式化建立最小 Project state |
| `project_cases/Y1A站第一層支撐/project.json.bak` | 無直接 consumer | 移除，不保留 fixture |
| `project_cases/Y1A站第一層支撐/source/source.dxf` | `tests/test_dxf_saveas_minimal_repro.py`、DXF export source hash check | 改用正式素材 `assets/sample_dxf/Y1A擋土支撐簡化版.dxf`；兩者原始 SHA-256 相同 |
| `project_cases/Y29車站/project.json` | 無 automated consumer | 移除，不保留 fixture |
| `project_cases/Y29車站/source/source.dxf` | 無直接 consumer | 由正式素材 `assets/sample_dxf/Y29_test.dxf` 取代；兩者原始 SHA-256 相同 |
| `project_cases/123.json` | 無 automated consumer | 移除，不保留 fixture |
| `project_cases/Y1A站第一層支撐.json` | `tmp_compare_manual_h1.py` 透過目錄排序間接選取 | 工具改為要求呼叫者明確傳入外部 Project JSON 路徑；repository 不附案例 |
| `project_cases/Y1A站第二層支撐.json` | 無 automated consumer | 移除，不保留 fixture |
| `project_cases/Y1A第一層支撐1.json` | 無 automated consumer | 移除，不保留 fixture |

Runtime `project_cases/` 由應用程式建立並保存使用者自己的 Project；它不是 repository fixture source。
