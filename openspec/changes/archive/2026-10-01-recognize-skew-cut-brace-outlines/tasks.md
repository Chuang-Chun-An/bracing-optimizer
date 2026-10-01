# Tasks

## 實作前閱讀

- **第 1 組（基準與量測契約）現在必讀：** `proposal.md` 的「快速摘要／不變事項」、本 change 的三項規格需求、`design.md` 的決策 1～3，以及 `dxf_import/block_member_recognition.py`、`dxf_import/recognition.py` 與其直接測試。其餘文件可先跳過。
- **第 2 組（純幾何辨識）現在必讀：** 規格「完整斜切封閉外框 SHALL 可由拓撲建立 Brace body」與「斜切封閉外框的來源軸 SHALL 由有限端面界定」、設計決策 1～3、5。
- **第 3 組（流程整合）現在必讀：** 規格「斜切外框辨識 SHALL 保留既有安全邊界」、設計決策 4～6，以及既有 `openspec/specs/brace-axis-waler-extension/spec.md` 中與端點接觸、重疊候選及延伸上限相關的需求。
- **第 4 組（回歸驗證）現在必讀：** 本 change 全部規格情境與 `design.md` 的風險／取捨；執行前再閱讀受影響測試檔。Solver 文件與測試不在本 change 範圍，可跳過。
- **第 5 組（文件與完成檢查）現在必讀：** `proposal.md` 的 In Scope／Out of Scope、本 tasks 全文，以及實作後的測試結果。

## 1. 建立基準與共用量測契約

- [x] 1.1 在 Brace 辨識的直接測試中加入 Y29 `71A` 與合成斜切封閉四邊形的特徵測試，固定記錄兩側長邊、覆蓋率、寬度及預期有限端點；驗證測試資料能重現約 `77.36%` 覆蓋率，且在現行 `0.8` 通則下會被拒絕。
- [x] 1.2 在 `dxf_import/block_member_recognition.py` 內定義不可變的共用 `BraceOutlineMeasurement`（包含中心軸、寬度、兩條長邊、兩個有限端面及判定依據），由 `dxf_import/recognition.py` 的既有流程呼叫，且不得建立新的 `dxf_import/recognition/` 套件；保留既有呼叫端所需的相容介面，並以型別檢查或單元測試驗證一般矩形量測結果未改變。

## 2. 實作封閉外框的純幾何辨識

- [x] 2.1 實作封閉輪廓正規化及唯一拓撲分解：將可共線合併的邊整理成兩組平行長邊與兩個連續端面，且結果不受起始頂點與走訪方向影響；以反向走訪、循環位移及多段共線邊測試驗證決定性。
- [x] 2.2 由兩條平行長邊計算 Brace 寬度與中心線，再以中心線和兩個有限端面的交點建立來源軸；以 Y29 `71A` 類型案例驗證端點約為 `(230552.691, -457043.396)`、`(234567.188, -459160.000)`，並驗證不再使用長邊投影極值造成端點外伸。
- [x] 2.3 對缺邊、開口、自交、分支、無法形成唯一兩長邊／兩端面、存在多組合理分解，以及退化外框維持拒絕或待人工確認；負向測試至少涵蓋一條 rail `< minimum_component_length_mm` 的近三角形、terminal cut 在 `parallel_angle_tolerance_deg` 內與 rails 平行、兩 rails 沒有正 longitudinal overlap，並驗證不會建立 closed-topology Brace。只可沿用既有 tolerance；若任何退化案例仍會通過，停止實作並回報，不得自行增加未命名門檻。
- [x] 2.4 保留既有寬度合法性與一般投影覆蓋規則：寬度須嚴格大於 `250 mm` 且不超過設定上限，非完整封閉拓撲仍使用 `minimum_projection_overlap_ratio = 0.8`；以邊界值及開放／碎片輪廓測試驗證未全域降為 `0.7`。

## 3. 整合一般與元件式 Brace 辨識流程

- [x] 3.1 將共用量測接入一般封閉 Brace 候選建立流程，沿用既有 boundary/source provenance 與錯誤分類；以既有矩形、多段封閉輪廓及 `71A` 類型測試驗證候選資料完整且來源 handle 不變。
- [x] 3.2 將相同量測接入元件式辨識的 `TOPOLOGY` 層級，僅在完整且唯一的封閉拓撲成立時取得較高權威；以 INSERT 與一般圖元的等價案例驗證量測一致，並驗證較低層級辨識規則未被放寬。
- [x] 3.3 讓端點接觸與 Waler 延伸流程只消費修正後的 `recognized_axis`，不得以端面直接指定 Waler；以 Y29 驗證 `71A` 可形成幾何候選，但來源 `69F`／`720` 的重疊歸屬仍依既有規則保持歧義。
- [x] 3.4 補強診斷資訊，使完整斜切外框、一般覆蓋不足、拓撲不唯一及 Waler 歧義可被區分；以錯誤碼／診斷內容測試驗證 UI 能沿用既有資料契約呈現原因。

## 4. 回歸與邊界驗證

- [x] 4.1 使用實際 Y29 測試資料驗證 `71A` 被辨識成寬約 `400 mm`、端點受斜切端面限制的 Brace 候選，同時確認不是靠降低全域門檻而連帶接受其他覆蓋不足圖元。
- [x] 4.2 執行並擴充既有 Brace 辨識測試，涵蓋一般矩形、頂點反轉、循環起點、多段共線邊、Y05/Y29 樣本及 `44E`／`45C` 既有觀察結果；既有矩形 closed-outline Brace 經 `BraceOutlineMeasurement` 新量測後，其中心軸與寬度 MUST 在既有 geometry tolerance 內與舊結果完全等價，同時驗證其他舊有合法案例不退步，且跨來源合併／去重行為未改變。
- [x] 4.3 執行端點接觸與 Waler 延伸的直接測試，涵蓋端點容差、共線投影、重疊候選歧義與 `600 mm` 延伸上限；驗證本 change 只修正來源軸，不改變 Waler 選擇政策。
- [x] 4.4 若新增模組或調整依賴，執行 DXF 匯入子系統的 boundary tests；驗證純幾何辨識未依賴 UI、檔案 I/O、Application 或 Solver。
- [x] 4.5 先執行受影響的單元與整合測試，再執行完整 DXF import 相關測試套件；保存測試命令與結果，且不得以刪除測試、降低 assertion 或忽略錯誤方式通過。

## 5. 文件與 OpenSpec 完成檢查

- [x] 5.1 行為驗證通過後更新 `docs/DOMAIN.md` 中的 Brace 外框辨識說明，記錄「完整封閉拓撲」與「投影覆蓋率通則」的適用邊界；若實作未改變架構責任，確認不需修改 `docs/ARCHITECTURE.md`。
- [x] 5.2 對照 `proposal.md`、delta spec 與 `design.md` 逐項審查實作，確認未改動全域 `0.8`、Waler 歧義政策、`600 mm` 上限、Solver 或跨來源去重；以 code review checklist 記錄結論。
- [x] 5.3 執行 `openspec validate recognize-skew-cut-brace-outlines --strict` 與 `openspec status --change recognize-skew-cut-brace-outlines`，確認所有 artifact 可解析、實作任務完成且無未處理的規格落差。
