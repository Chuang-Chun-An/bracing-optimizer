# Proposal

## Why

目前自動 Brace-to-Waler 軸向延伸沒有距離上限，Y05 實際資料可出現數公尺至數十公尺的部分延伸，即使另一端仍未連接，仍會使正式 Review geometry 過度拉長。需要保留約 425～503 mm 的有效 Y05 補接能力，同時阻止遠距離自動推測。

## What Changes

- 保留既有 `connection_tolerance_mm = 250 mm` direct snap，作為一般端點繪圖誤差容許值。
- 對 direct snap 後仍未連接、且為 auto selection 的 Brace 端點，繼續只沿可靠中心軸向外尋找有限 Waler 真實交點。
- 將 Brace 自動軸向延伸限制為 `<= 600 mm`；`600 mm` 可接受，`> 600 mm` 不採用。
- 超過 600 mm 時保留 source-supported endpoint，並沿用未連接／單端未連接 blocking validation。
- 600 mm 是 Brace 專用 connection policy，不修改全域 `connection_tolerance_mm`，也不影響 Strut、CornerBrace 或其他 association tolerance。
- 保留最近有限交點、ambiguity、兩端不同 Waler、人工端點優先與 Review lifecycle 契約。

### In Scope

- Brace 自動 outward-axis extension 的 600 mm 上限。
- pure resolution、Candidate Point、diagnostics 與 Review rebuild 對上限採用一致語意。
- Y05 約 425 mm／503 mm 成功案例與超過 600 mm 拒絕案例的 regression coverage。
- 實作完成後同步 `docs/WORKFLOW.md` 的 current behavior。

### Out of Scope

- 將 Brace direct snap tolerance 提高至 600 mm。
- 修改共用 `connection_tolerance_mm = 250 mm`。
- 修改 Strut、CornerBrace、Waler recognition、BIM Brace recognition winner 或 source-supported recognition axis。
- 修改人工 Candidate Point／CAD 工程線規則、Project schema、Solver 或其他 DXF recognition。
- 以 UI 提供可調式距離設定。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `brace-axis-waler-extension`: 將原本沒有固定距離上限的 Brace outward-axis extension 改為最多 600 mm，並明確定義等號邊界及超限失敗行為。

## Impact

- 主要影響 `dxf_import/brace_waler_connection.py` 的 pure endpoint resolution，以及 `dxf_import/candidate_points.py` 的 connection／candidate presentation。
- `GeometryTolerances` 預計新增具名的 Brace 專用 internal connection setting，不改變既有共用 tolerance。
- 需更新 focused geometry、Y05、Review lifecycle 與 regression tests。
- 不新增第三方 dependency，不改變 Architecture、Domain、Solver 或 persistence schema；僅改變 DXF Review Workflow 的 Brace 自動連接範圍。
