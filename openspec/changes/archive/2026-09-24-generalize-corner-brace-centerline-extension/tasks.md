# Tasks

## 1. 建立角撐端點行為測試基線

- [x] 1.1 在 `tests/test_dxf_input.py` 保留並補強 Y1A 類 `connection_plate_midpoints` regression，驗證角撐數量、現有成功 recognition method、Waler 內線端點、Strut 中心線端點及衍生長度，並鎖定既有連接板辨識／fallback 行為不回歸。
- [x] 1.2 在 `tests/test_dxf_input.py` 新增 Y29 類 `parallel_edges_midline` 合成 DXF 案例，證明雙主桿中心軸應進入共用 refinement，延伸至現行流程已選定 Waler 的有限內線及 Strut 的有限中心線。
- [x] 1.3 新增沒有可靠中心軸的正式角撐案例，驗證泛化規則不會把單一斜線或暫定端點無條件延伸，且保留既有 recognition／validation 行為。
- [x] 1.4 新增有限交點與 atomicity 測試，涵蓋缺少 Waler 交點、缺少 Strut 交點及校正後過短；逐案驗證原 candidate 不會留下單端或部分欄位更新。
- [x] 1.5 Characterize 現有 Waler／Strut selection 與 direct／reverse 端點方向，確認本 change 前後結果一致；測試不新增 competing-candidate、runner-up 或 ambiguity policy assertion。

## 2. 泛化可靠中心軸 endpoint refinement

- [x] 2.1 在 `dxf_import/recognition.py` 將 `_refine_corner_brace_axis_intersections()` 的 `connection_plate_midpoints` method-only gate 改為 reliable-axis gate，重用 `_corner_brace_center_axis()` 與現行 angle／overlap／width／length tolerances。
- [x] 2.2 保留 `_corner_brace_candidates_from_group()` 的連接板辨識及 Y1A compatibility；驗證 `connection_plate_midpoints` 與具有可靠雙主桿證據的 `parallel_edges_midline` 共用中心軸交點 refinement，而一般 `brace`／`strut` 不受影響。
- [x] 2.3 保留現有 nearest Waler／Strut selection 與 direct／reverse score 決策；不得在此 task 枚舉全場配對、修改 `ambiguous_connection_delta_mm`、新增 runner-up threshold 或建立新的 ambiguity diagnostic。
- [x] 2.4 對可靠中心軸先在 local values 中計算 Waler 有限內線交點、Strut 有限中心線交點及校正後長度；全部有效後才一次更新 `start/end/recognized_axis/reference_point`，失敗時保留原 candidate 並沿用既有 failure classification。
- [x] 2.5 執行 focused recognition tests，確認 Y29 類角撐不再因 method gate 略過支撐中心線延伸，且 Y1A 結果與無可靠中心軸案例維持預期。

## 3. 驗證正式幾何的下游一致性

- [x] 3.1 補充 importer integration test，驗證 `attach_corner_braces_to_struts()` 與 candidate points 皆使用校正後的 Strut 中心線端點，且不再從支撐外緣建立第二套角撐位置。
- [x] 3.2 在 `tests/test_dxf_waler_contact_adjustment.py` 驗證 `build_corner_brace_connections()` 以校正後工程線建立 Waler attachment、Strut attachment、hole station 與 fixed length，並確認背填／圍令寬度預覽及套用使用這組 baseline。
- [x] 3.3 執行角撐 source exclusion、candidate rebuild 與 Review validation 的相關測試，確認校正失敗仍可定位來源，且未引入新的 association、ambiguity、persistence 或 UI contract。

Task 3 不受 Waler／Strut candidate duplication 或 ambiguity policy 阻擋；這些議題已 deferred，不得在本 change 順帶實作。

## 4. Regression 與 OpenSpec 驗證

- [x] 4.1 執行 `tests/test_dxf_input.py`、`tests/test_dxf_waler_contact_adjustment.py`、`tests/test_dxf_source_exclusion.py` 的 focused suite，確認所有新增與既有角撐案例通過。
- [x] 4.2 執行 DXF module boundary、Review workflow 及 OCS/WCS regression tests，確認新 gate 維持 DXF import 責任邊界與 world-coordinate recognition 語意。
- [x] 4.3 執行完整 test suite，確認無失敗、未降低 assertion、未以 skip 排除既有案例，並記錄測試總數與結果。
- [x] 4.4 執行 `openspec validate generalize-corner-brace-centerline-extension --strict --no-interactive` 與 OpenSpec implementation verification；確認 proposal、spec、design、tasks 一致聚焦角撐中心軸延伸，且未納入新的 ambiguity policy。
