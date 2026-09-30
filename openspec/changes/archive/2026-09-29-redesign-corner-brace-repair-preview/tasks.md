# Tasks

## 實作前閱讀

| Task group | 必讀內容 | 要確認的行為 |
| --- | --- | --- |
| 1. 顯示格式與術語 | `proposal.md`「不變事項」；`design.md` Decision 2、4；spec「定位尺寸使用直觀名稱」「預覽數值統一顯示三位小數」 | 顯示只讀既有 candidate，三位小數不回寫底層值。 |
| 2. 預覽視窗資訊層級 | `proposal.md`「主要流程」；`design.md` Decision 1、2、5；spec「唯一候選仍需確認」「主要資訊與稽核資訊分層」「稽核與診斷區預設收合」「使用者選擇多個候選之一」 | 單一候選直接成為目前方案，仍須明確套用；多候選 selection contract 與稽核區 invariant 不變。 |
| 3. 圖面 overlay | `design.md` Decision 3；spec「以灰色顯示目標來源線段」 | 只畫 plan 提供的 target residual segments，並維持 overlay cleanup。 |
| 4. 整合驗證 | `proposal.md` In Scope／Out of Scope；完整 delta spec；`design.md` Architecture Alignment | 不改 planner、Domain、Solver、workflow commit 或 persistence。 |

## 1. 顯示格式與術語

- [x] 1.1 在 `dxf_import/dialog.py` 新增角撐修補專用的 scalar、point 與 engineering-line 顯示 helper：結果長度、reference fixed length 與兩個定位距離固定三位小數並帶 `mm`，positional anchor 與 candidate world engineering line 的每個座標分量固定三位小數且不帶 `mm`；以 `tests/test_dxf_review_layout.py` focused test 驗證正數、負數、整數補零、四捨五入、點與兩端工程線格式，並驗證 formatter 前後 candidate 原始 numeric values 完全相同。（對應 spec「預覽數值統一顯示三位小數」）
- [x] 1.2 將角撐修補 preview 使用者可見的 `reference_waler_offset_mm`／`reference_strut_station_mm` 名稱改為「圍令端定位距離」／「支撐端定位距離」，並顯示「量測基準：目標圍令與支撐的交會點；支撐端定位距離沿支撐內側方向量測。」；以 layout/source contract test 驗證新名稱出現在主要摘要、量測說明語意正確、被取代名稱不再出現在角撐修補 preview 使用者可見區域，且內部欄位名稱維持原樣。（對應 spec「定位尺寸使用直觀名稱」）

## 2. 預覽視窗資訊層級

- [x] 2.1 重組 `dxf_import/dialog.py` 的角撐修補 Toplevel，建立主要方案摘要，顯示目標 Waler／Strut、模板、移植方式、結果長度、「圍令端定位距離」、「支撐端定位距離」與 valid states；以 focused Presentation test 驗證新名稱出現在摘要、內容皆取自 selected candidate，且工程長度／定位距離為三位小數並帶 `mm`。（對應 spec「主要資訊與稽核資訊分層」）
- [x] 2.2 對單一 candidate 直接設定目前 UI selection、刷新摘要與 overlay、啟用「套用此修補」，但不呼叫 commit；以 dialog test 驗證開窗不改 live Review state、未自動 commit、取消與關閉仍為零副作用，且只有既有 Apply callback 成功後才提交。（對應 spec「唯一候選仍需確認」「使用者取消預覽」）
- [x] 2.3 候選多於一個時保留既有 `Treeview` browse selection 與 candidate ID identity，讓選取事件同步更新摘要、稽核與診斷、overlay 與 Apply state；以 synthetic multi-candidate test 驗證未選取時 disabled、選取後依 candidate ID 只投影該 candidate、表格工程數值顯示三位小數，且不得以格式化字串識別、合併、排序、自動選擇或提交 candidate。（對應 spec「使用者選擇多個候選之一」）
- [x] 2.4 建立預設收合、可透過「顯示稽核與診斷」／「隱藏稽核與診斷」切換的區域，保留 reference fixed length、world engineering line、automatic primary references、manual repaired secondary references、candidate diagnostics 與 plan diagnostics；以 focused test 驗證初始為收合、展開後資料完整、重新收合後仍可再次取得，且 toggle 不改 selected candidate、Apply state、candidate ID、overlay、live Review state 或 persistence。若顯示「有診斷資料」，另驗證它不觸發 Presentation severity 判斷。（對應 spec「稽核與診斷區預設收合」）

## 3. 圖面 overlay

- [x] 3.1 更新 `_draw_corner_brace_repair_overlay`，只將每一條 `plan.residual_segments` 以低干擾灰色細線／虛線顯示，並保留藍色 selected candidate 工程軸線與橘色 positional anchor；以 renderer stub test 驗證 source item 數量、樣式、繪製順序與 target-only input，且 UI 未掃描整張 DXF／鄰近幾何、未把 overlay 當成 eligibility evidence。（對應 spec「以灰色顯示目標來源線段」）
- [x] 3.2 驗證改選 candidate、取消與關閉預覽都會先清除既有 temporary overlay，改選後每個 residual 只重畫一次且不殘留重複 item；以 overlay lifecycle focused test 驗證 `_corner_brace_repair_overlay_items`、canvas items、selected candidate 軸線與 anchor 均回到預期狀態。（對應 spec「改選或離開預覽時清除 temporary overlay」「使用者取消預覽」）

## 4. 整合與完成驗證

- [x] 4.1 執行 `tests/test_dxf_review_layout.py` 與新增的 Presentation／overlay focused tests，確認正式定位名稱、量測基準、長度／定位距離的三位小數與 `mm`、座標三位小數且無單位、原始 numeric values 不變、稽核區預設收合、單一／多候選及 overlay lifecycle contract 全部通過。
- [x] 4.2 執行 `tests/test_dxf_corner_brace_repair.py` regression，確認候選數量、排序、eligibility、explicit adoption、rollback 與 persistence 行為沒有因介面改版而改變。
- [x] 4.3 依影響範圍執行 DXF Review 相關測試或完整 `python -m unittest discover -s tests -v`，回報任何既有失敗與本 change regression；不得藉由降低 assertion 或略過測試完成任務。
- [x] 4.4 執行 `openspec validate redesign-corner-brace-repair-preview --strict`，再使用 `$openspec-verify-change` 對照 proposal、design、delta spec 與 tasks 驗證 implementation；確認沒有超出 Presentation scope，並記錄已知限制。因 long-term Architecture、Domain、Solver、Workflow truth 未改變，本 change 不更新其文件。
