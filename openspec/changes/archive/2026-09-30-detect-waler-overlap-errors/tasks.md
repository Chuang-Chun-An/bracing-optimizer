# Tasks

## 實作前閱讀

- **第 1 組前**：閱讀 [proposal.md](proposal.md) 的「現況與目標／不變事項」、[design.md](design.md) 的 D1、D2、D6，以及 `dxf-waler-overlap-diagnostics` 的「重大共線重疊」公式與「競爭關係」direct-provenance Requirements。
- **第 2 組前**：閱讀 [design.md](design.md) 的 D1、D2 與 `dxf_import/waler_contact_face.py` 的 `WalerEnvelopeFacts`、`TerminalTopologyIssue`、`WalerContactResolution`；可先跳過 Presentation。
- **第 3 組前**：閱讀 [design.md](design.md) 的 D2、D3、D4，以及 `dxf-waler-contact-face-recognition` 的「Unresolved Waler 不得產生正式接觸面」。
- **第 4 組前**：閱讀 [design.md](design.md) 的 D4、D5，以及 `dxf-review-engineering-data-presentation` 的兩個 Requirements；確認 `DXFReviewWorkflow` 是 live state owner。
- **第 5 組前**：回讀三份 delta specs 的所有 Scenarios、[proposal.md](proposal.md) 的 In／Out of Scope 與 [design.md](design.md) 的 Architecture Alignment；Solver 文件與演算法不在本 change scope。

## 1. 建立測試基線與失敗案例

- [x] 1.1 在 `tests/test_dxf_waler_contact_face_recognition.py` 新增純幾何 overlap qualification tests，明確斷言分子為兩條 source-supported provisional axes 的正有限投影交集、分母為 `min(provisional_axis_length_a, provisional_axis_length_b)`，並涵蓋 exact `50%`、略低於 `50%`、endpoint-only、零長度、不可靠／缺少 source-supported axis、禁止以 finalized face／envelope／外框／bounding box／Project row／無限 supporting line 補算、端點反轉與 input/source 順序交換；以所有負向 cases 不建立 overlap fact 且既有 diagnostics 保留驗證完成。
- [x] 1.2 在 `tests/test_dxf_waler_contact_face_recognition.py` 新增 direct identity provenance tests：A／B overlap + unrelated unresolved 只能 warning、A／B overlap + 實際 A／C competition 不得建立 A／B blocking、A／B overlap + 同一 terminal 或 finalization 明列 A、B 時為 warning+`WALER_OVERLAP_COMPETITION`，以及 input/source/competing-identity 順序互換後結果等價；以 pair、terminal context、severity 與受影響 identities assertions 驗證完成。
- [x] 1.3 在 `tests/test_dxf_waler_contact_face_recognition.py` 固定 Y29 baseline：`69C`／`721` 同時 active 時既有 `AMBIGUOUS_WALER_CONNECTION` 與 `WALER_CONTACT_FACE_UNRESOLVED` 仍存在、direct provenance 支持該 pair 的 competition、兩支都不是正式接觸面；排除任一 handle 時另一支採用支撐側最外表面；以反轉 source/entity 順序後工程結果集合相同驗證完成。
- [x] 1.4 在合適的 `tests/test_dxf_review_*.py` focused test 建立 Preview／Review baseline，斷言 formal 與 provisional Waler 可由 typed staged state 區分、warning-only 不阻擋、competition error 顯示受影響 terminal 並阻擋、其他 unresolved 不改變 A／B 顯示層級，且 Review 只中性說明 rebuild、不推薦 winner。

## 2. 實作重大共線重疊事實與診斷分層

- [x] 2.1 在 `dxf_import/waler_contact_face.py` 新增 immutable `WalerOverlapFact`（或等價 typed fact）與具名 `0.50` threshold，保存 canonical source pair、有限 overlap segment、positive projected length、兩方 provisional-axis finite lengths 與 ratio；以 Task 1.1 驗證 ratio 可追溯且不依端點／輸入順序。
- [x] 2.2 在 `dxf_import/waler_contact_face.py` 實作 reliability gate 與 pairwise qualification，只使用 source-supported `WalerEnvelopeFacts.provisional_axis` 的有限區段及既有 angle／collinearity tolerances，拒絕 shared identity、unreliable／unsupported axis、零長度、endpoint-only、non-collinear 與 `< 50%` cases，且不以任何禁用幾何補算；以 Task 1.1 全部通過且既有 recognition/contact diagnostics 不被吞掉驗證完成。
- [x] 2.3 在 `dxf_import/waler_contact_face.py` 或 recognition 純協調 helper 以完整 Waler source identity 做 exact provenance join：只有同一 `TerminalTopologyIssue` 或同一 contact-finalization outcome 同時明列 overlap pair 兩方為實際 competitors 才產 blocking fact，generic unresolved、只列一方或 A／C competition 不得升級 A／B；以 Task 1.2 全部通過且沒有新增 proximity inference／winner ranking 驗證完成。

## 3. 接入 Recognition、Importer 與正式線狀態

- [x] 3.1 在 `dxf_import/recognition.py` 的 `_Candidate`／staged contact flow 與 `dxf_import/models.py` 的 `Waler` 加入穩定的 `formal`／`provisional` contact-face state；狀態只能由 successful `WalerContactResolution` 且 selected face 已套用後成為 `formal`，以 unresolved、successful resolution 與 recognition exception focused tests 驗證原子一致性。
- [x] 3.2 在 `dxf_import/recognition.py::_resolve_waler_contact_geometry()` 將 overlap warning 與 competition error 投影為 deterministic `ValidationMessage`，保留雙方完整 Waler identities、overlap ratio／segment、同一 terminal／finalization context 與受影響 member provenance，並保留既有 ambiguity／unresolved messages；以 Task 1.2、Y29 codes、severity、source handles 與不同輸入順序的等價輸出驗證完成。
- [x] 3.3 在 `dxf_import/importer.py::_make_waler()` 將 staged contact-face state 投影到 immutable `Waler`，並在 `DXFImportResult.to_debug_dict()`／相容 hydration 路徑維持穩定字串與舊資料可讀性；以 debug round-trip 或 recovery focused test 驗證缺少新欄位不崩潰，但新 recognition 不依相容 default 判斷正式性。
- [x] 3.4 保持 `Waler.to_project_row()` key set 與 completed import contract 不變，確認 unresolved Y29 仍由 blocking validation 阻止提交且新 Review-only state 不進入 Project／Solver rows；以既有 Project row assertion 加上 key-set regression 驗證完成。

## 4. 接入 Review、Preview 與 lifecycle

- [x] 4.1 在 `dxf_import/validation.py`／既有 problem projection 將 overlap warning 與 competition error 轉為可定位的 problems／review items，顯示兩方來源、原因、比例、blocking status 與 direct provenance 的受影響 terminal／finalization context；只中性說明 active sources 變更後會重新辨識，不推薦刪除、排除或保留任一方，並以 warning-only `can_import` 不變、unrelated unresolved 不誤升級、Y29 blocked 且雙方 handles／terminal 可定位的 focused tests 驗證完成。
- [x] 4.2 在 `dxf_import/dialog.py::_preview_member_styles()` 與 Waler detail projection 只依 typed contact-face state 顯示正式工程線或明確不同的 provisional axis 樣式／標示，不從 `recognition_method`、selected candidate、message code 或 UI selection 反推；以 Preview style helper 測試及 selection／redraw 不修改 `DXFImportResult` 驗證完成。
- [x] 4.3 在 `dxf_import/review_workflow.py` 的既有 exclusion／restore／rebuild 路徑驗證 diagnostics 與 contact-face state 每次都由 active sources 從零重建：排除 `69C` 或 `721` 後 pair diagnostics 消失且剩餘 Waler 為 `formal`，還原後重新成為目前可證明的 overlap／competition／provisional 結果；以 `tests/test_dxf_review_workflow.py` regression 通過驗證完成。
- [x] 4.4 在 `tests/test_dxf_review_recovery.py` 及相關 confirmation/manual replay tests 覆蓋 Pause／Resume、compatible recovery、manual override replay 與 source order permutation，確認沒有 stale overlap pair、舊 formal line 或 UI identity 被重播；以相同 active source facts 產生等價 diagnostics、blocking 與 formal/provisional state 驗證完成。

## 5. Regression、邊界與 OpenSpec 驗證

- [x] 5.1 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_waler_contact_face_recognition tests.test_dxf_review_workflow tests.test_dxf_review_recovery tests.test_dxf_review_items tests.test_dxf_review_confirmation tests.test_dxf_review_layout`，修正本 change 引入的失敗但不降低 assertions，並保存所有 focused suites 通過的結果。
- [x] 5.2 執行既有一般非重疊、Y05／Y1A、HATCH Waler 與 contact adjustment regressions（至少 `tests.test_dxf_hatch_waler_recognition`、`tests.test_dxf_waler_contact_adjustment` 及 `tests.test_dxf_bim_block_recognition` 中相關 cases），確認正式 contact face、ID／source ordering、Project row 與 `can_import` 沒有非預期改變。
- [x] 5.3 執行專案既有 architecture／dependency boundary tests（若 repository 有對應 runner，依 `docs/ARCHITECTURE.md` 指示執行），並以 `rg` 確認 Presentation 未新增 overlap geometry 或 terminal ranking 邏輯、`waler_contact_face.py` 未依賴 GUI／Project／Solver；若長期 Architecture／Workflow truth 未變，不修改長期文件。
- [x] 5.4 對照 [proposal.md](proposal.md)、[design.md](design.md) 與三份 delta specs 完成 implementation review，逐項確認 ratio 僅使用可靠有限 provisional axes、blocking 具有同一 terminal／finalization 的 direct pair provenance、無 winner 推薦、warning/error 分層、provisional 不提交、lifecycle 相容及 Solver／Project schema 未變，再執行 `openspec validate detect-waler-overlap-errors --strict` 並以零錯誤作為完成條件。

