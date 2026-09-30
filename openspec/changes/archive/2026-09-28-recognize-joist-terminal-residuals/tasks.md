# Tasks

## 實作前閱讀

- Task Group 1 開始前：閱讀 `proposal.md` 的「現況與目標」、「In Scope／Out of Scope」，`design.md` 的 Decision 2、3、5，以及 delta spec 的 ADDED Requirement「已證明跨越中間柱的托梁可恢復端部殘線」。
- Task Group 2 開始前：閱讀 `design.md` 的 Decision 1、2、3，以及 delta spec 的 700 mm、gap bridging、collective evidence、isolated line 與 ambiguity scenarios。
- Task Group 3 開始前：閱讀 `design.md` 的 Decision 4、6，以及 delta spec 的 MODIFIED Requirement「Joist contact SHALL preserve source axes while supporting finite crossings and qualified Strut-face contacts」。
- Task Group 4 開始前：閱讀 `design.md` 的 Decision 7、Backward Compatibility and Persistence，以及 delta spec 的 MODIFIED Requirement「Y05 characterization SHALL remain a regression contract」。
- Task Group 5 開始前：回讀全部 proposal／design／delta spec，確認實作沒有擴及 Brace-guided recovery、Solver、Project schema 或非 BIM Beam routes。

## 1. 鎖定端部殘線判定契約

- [x] 1.1 在 `tests/test_dxf_bim_joist_recognition.py` 新增 pure synthetic fixtures，表達同 root、既有 paired direction、六條 rail bands、formal Column center 與 occlusion gap；以 fixture 能分別產生完整殘線、Brace-clipped 短片段、孤立短線及互斥候選完成驗證。
- [x] 1.2 在 `tests/test_dxf_bim_joist_recognition.py` 新增 terminal outward signed projection 的 `0.0／700.0 mm` inclusive、`>700.0 mm` 與反方向 boundary tests；以窗內證據可候選、超界與反方向證據不改變 base axes 完成驗證。
- [x] 1.3 在 `tests/test_dxf_bim_joist_recognition.py` 新增 per-sibling rail-band quorum 與 `50.0 mm` terminal-event compatibility tests；以每側各自至少兩個 bands 才能恢復、單一短線被拒絕、兩側端點相差不超過 50 mm 時仍各自停在自身 source-supported endpoint，且不取較外值、不平均、不跨 sibling 外插完成驗證。
- [x] 1.4 在 `tests/test_dxf_bim_joist_recognition.py` 新增衝突候選測試；以多個完整但超出 endpoint tolerance 的 terminal interpretations 產生 blocking ambiguity，且結果不依 ID 或 collection order 完成驗證。
- [x] 1.5 在 `tests/test_dxf_bim_joist_recognition.py` 新增 final identity tests；以 final relation 單純無法證明時回退 base axes、明確改指其他 Strut／Column 或同時形成多個 identities 時 blocking，且兩種情況皆不提交 preliminary truth 完成驗證。

## 2. 實作 Column-qualified terminal recovery

- [x] 2.1 在 `dxf_import/joist_recognition.py` 定義具名常數 `JOIST_COLUMN_TERMINAL_WINDOW_MM = 700.0`，並建立由 `JoistContextSnapshot` 的 finite Strut geometry 與 `JoistColumnStationReference.station` 重建 formal Column WCS center、再依 terminal side 定義 outward signed projection 的 pure helper；以既有與新增 pure tests 驗證座標、方向及 inclusive boundary。
- [x] 2.2 在 `dxf_import/joist_recognition.py` 從 base paired axes 的 canonical direction 與既有 longitudinal offsets 回看同 root 的全部 line primitives，建立 terminal-side rail-band evidence；以測試驗證不重新猜測方向、envelope 或 root，且一般 20% base clustering 門檻未被修改。
- [x] 2.3 在 `dxf_import/joist_recognition.py` 實作每個 sibling 各自至少兩個 rail bands、各自的 band endpoint clustering 與 sibling terminal-event compatibility，並只在唯一完整 interpretation 時讓每支 axis 使用自身 source-supported terminal extent；以 Task 1.2～1.4 測試全部通過，且不取兩者較外值、不平均、不產生跨 sibling 外插完成驗證。
- [x] 2.4 在 `dxf_import/joist_recognition.py` 把 base axis、preliminary Column relation、terminal recovery 與 finalized axis 串成 pure 三段流程；以 gap bridging 測試確認只跨越 formal Column／Strut occlusion corridor，沒有證據時保留 base axes。

## 3. 以 finalized axes 重建接觸與診斷

- [x] 3.1 在 `dxf_import/joist_recognition.py` 於 terminal recovery 後重新計算 Joist contacts 與 pair relations，並確保真正穿越 finite Strut 的軸線只產生 direct crossing、不重複產生 `endpoint_face_contact`；以新增 contact classification test 驗證 crossing point、Strut station 與 preliminary seed 的 Strut／Column identity 均由 finalized axes 重新證明。
- [x] 3.2 在 `dxf_import/joist_recognition.py` 保留 finalized axis 真正止於 Strut face 時的既有 `25.0 mm` inclusive fallback；以既有 endpoint-face boundary、outside-range、multiple-face ambiguity tests 通過完成驗證。
- [x] 3.3 在 `dxf_import/joist_recognition.py` 區分 final proof 不足與 identity 矛盾：前者放棄 recovery 後從 base axes 重建 final outcome，後者 blocking；在必要的 `dxf_import/recognition.py` 窄幅傳遞 runtime-only incompatible interpretation／context-drift diagnostics，以 Task 1.5 通過且未新增或改動 Project persistence schema完成驗證。

## 4. 實際圖面與相容性回歸

- [x] 4.1 在 `tests/test_dxf_bim_joist_recognition.py` 加強 Y05 E8F／BM18 regression，驗證 paired axes 的 Column-side terminal 由約 `X=-35323.5` 恢復至 `X=-36173.5`、最外端距 Column center 675 mm，且該 Strut 關係改為 direct finite crossing 而 station 與 Column identity 不變。
- [x] 4.2 在 `tests/test_dxf_bim_joist_recognition.py` 新增 Y05 F2A regression，驗證一側完整 500 mm rails 與另一側 156／182／約 2.5 mm fragments 各自達到 quorum 後，可確認為同一 terminal event但分別恢復至不同的 source-supported endpoint；不得取較外值、平均或互相補長，且不產生額外 Joist 或 Beam。
- [x] 4.3 在 `tests/test_dxf_bim_joist_recognition.py` 更新 Y05 全圖 contract，驗證仍為 20 組 paired assemblies、40 條 paired axes、18 條 Brace-contact singles、58 條 formal Joists、68 組 paired relations／136 crossings，且 68 組 relations 均由 finalized finite axes 形成 direct crossings。
- [x] 4.4 執行 Y1A 與 Y29 actual-file regression，驗證 MLINE／closed-outline Beam 的數量、端點與 association outputs 不變，且未進入 BIM Column-qualified recovery route；以相關測試通過及無新增 diagnostic 完成驗證。
- [x] 4.5 執行 `tests/test_dxf_bim_joist_recognition.py` 與受影響的 importer／Project projection tests，確認 finalized axes 能穩定投影且 saved／reloaded Project contract 不變。

## 5. 文件、總回歸與 OpenSpec 驗證

- [x] 5.1 實作驗證完成後更新 `docs/WORKFLOW.md`，記錄 outward signed 700 mm safety boundary、per-sibling source-supported extent、direct-crossing reclassification，以及證據不足 fallback／identity 矛盾 blocking 分界；以文件內容僅描述已通過測試的行為完成驗證，若 ownership／contract 未改變則不修改 `docs/ARCHITECTURE.md`。
- [x] 5.2 執行完整 DXF recognition regression suite，並依實際影響範圍補跑 Project persistence／validation tests；以所有相關測試通過且無 Y1A、Y29 或其他 Beam route regression 完成驗證。
- [x] 5.3 對照 `proposal.md`、`design.md`、delta spec 與本清單進行 implementation review，確認沒有修改 Brace-guided single Joist、Solver、Project schema、材料規則或不相關模組，並以 `openspec verify recognize-joist-terminal-residuals`（或當前 CLI 等價命令）通過完成驗證。
