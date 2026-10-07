# 開發歷程

本文件保存專案的長期開發紀錄。Codex／OpenSpec 封存紀錄由 archive workflow
自動維護；GPT、Copilot、LINE、會議及其他來源可由使用者補充。

## Codex／OpenSpec 封存紀錄

<!-- codex-archive-log:start -->

<!-- codex-archive-log:entry-start key="2026-10-07-fix-project-menu-label-and-tab-colors" -->
### 2026-10-07｜`fix-project-menu-label-and-tab-colors`

- Archive：[openspec/changes/archive/2026-10-07-fix-project-menu-label-and-tab-colors](../openspec/changes/archive/2026-10-07-fix-project-menu-label-and-tab-colors)
- 完成內容：將 Project cascade 的動態 label 更新改為穩定識別，不再依賴未驗證的固定數字 index。；保證狀態刷新前後頂層選單仍只有一個 Project cascade，且「檔案」與「說明」名稱不被改寫。；為主 Notebook 與巢狀次 Notebook 定義不同 ttk style，採用低彩度藍灰色；選取狀態使用較深底色與白字，次層使用較淡色階，並保留 disabled／focus 可讀性。
- Capabilities：`main-window-project-controls`
- 驗證：Artifacts 4/4 done; tasks 12/12 complete; implementation verification passed.
- Specs：main-window-project-controls synced; openspec validate --specs: 38 passed, 0 failed.
<!-- codex-archive-log:entry-end key="2026-10-07-fix-project-menu-label-and-tab-colors" -->

<!-- codex-archive-log:entry-start key="2026-10-07-simplify-main-window-project-controls" -->
### 2026-10-07｜`simplify-main-window-project-controls`

- Archive：[openspec/changes/archive/2026-10-07-simplify-main-window-project-controls](../openspec/changes/archive/2026-10-07-simplify-main-window-project-controls)
- 完成內容：移除主視窗頂部 Project toolbar，以及其中的 New、Project Combobox、Open、Save、Save As、完整重新投影按鈕與快速狀態文字。；將「檔案」選單整理為：新建專案、開啟專案…、儲存專案、另存新專案…、結束，並提供 `Ctrl+N`、`Ctrl+O`、`Ctrl+S`、`Ctrl+Shift+S`。；Save與Save As新增共用的active-editor completion gate：合法pending值先提交並納入本次payload；不合法時保留editor並取消儲存，不執行任何persistence。
- Capabilities：`main-window-project-controls`、`unsaved-changes-navigation-guard`
- 驗證：29/29 tasks complete; strict validation passed; 1787 tests passed, 2 skipped
- Specs：Synced and verified: main-window-project-controls created; unsaved-changes-navigation-guard updated; openspec validate --specs passed 38/38
<!-- codex-archive-log:entry-end key="2026-10-07-simplify-main-window-project-controls" -->

<!-- codex-archive-log:entry-start key="2026-10-07-bundle-seeded-project-cases" -->
### 2026-10-07｜`bundle-seeded-project-cases`

- Archive：[openspec/changes/archive/2026-10-07-bundle-seeded-project-cases](../openspec/changes/archive/2026-10-07-bundle-seeded-project-cases)
- 完成內容：將目前 `Y05車站第一層支撐` 與 `Y29車站第一層支撐` 的正式內容建立為 tracked release asset 快照。；修改 `SupportSolver.spec`，把兩個案例的 `project.json` 與 `source/source.dxf` 複製到成品 `project_cases/` 的相同 managed layout。；明確禁止將兩個案例的 `project.json.bak`、其他 Project、`test_cases/` 或 `tests/fixtures/` 帶入正式包。
- Capabilities：`release-package-assets`
- 驗證：all artifacts complete; 11/11 tasks complete; implementation verification passed
- Specs：release-package-assets synced; openspec validate --specs --strict passed
<!-- codex-archive-log:entry-end key="2026-10-07-bundle-seeded-project-cases" -->

<!-- codex-archive-log:entry-start key="2026-10-07-stage-multiple-dxf-source-exclusions" -->
### 2026-10-07｜`stage-multiple-dxf-source-exclusions`

- Archive：[openspec/changes/archive/2026-10-07-stage-multiple-dxf-source-exclusions](../openspec/changes/archive/2026-10-07-stage-multiple-dxf-source-exclusions)
- 完成內容：將既有來源排除入口從「立即建立單筆plan」改為「逐筆加入或取消pending exclusion draft」；即使只有一筆也必須先標記，再由「重新辨識並套用」處理，且不保留或新增立即排除入口。標記操作本身不得呼叫full recognition。；Pending draft以canonical source identity正規化及去重，並綁定建立時的Review revision與source fingerprint；每筆加入時仍執行來源存在性、角色、normalized handles及shared-handle安全檢查。；DXF Review新增「重新辨識並套用」入口；無pending時disabled，有pending時顯示數量，並針對整組candidate exclusions只呼叫一次既有canonical staging路徑。
- Capabilities：`dxf-source-exclusion-workflow`
- 驗證：All artifacts complete; 35/35 tasks complete; strict change validation passed
- Specs：Synced dxf-source-exclusion-workflow main spec; strict main-spec validation passed (37/37)
<!-- codex-archive-log:entry-end key="2026-10-07-stage-multiple-dxf-source-exclusions" -->

<!-- codex-archive-log:entry-start key="2026-10-07-stabilize-corner-brace-repair-reference-identity" -->
### 2026-10-07｜`stabilize-corner-brace-repair-reference-identity`

- Archive：[openspec/changes/archive/2026-10-07-stabilize-corner-brace-repair-reference-identity](../openspec/changes/archive/2026-10-07-stabilize-corner-brace-repair-reference-identity)
- 完成內容：CornerBrace repair reference以stable source identity／subject key作為主要對齊依據；依順序產生的member ID不再是exact match的必要條件。；Stable match必須唯一；零筆或多筆match不得依幾何距離、display ID或first match自行挑選。；Match成功後仍依目前result重驗reference geometry、唯一CornerBrace-to-Waler／Strut connection、primary／secondary eligibility、confirmation、provenance及既有candidate validation。
- Capabilities：`dxf-corner-brace-repair-tool`
- 驗證：All 4 artifacts complete; 27/27 tasks complete; 1722 tests passed, 1 skipped; strict change validation passed
- Specs：Synced dxf-corner-brace-repair-tool MODIFIED requirement; 19/19 scenarios matched; main specs validation 37 passed, 0 failed
<!-- codex-archive-log:entry-end key="2026-10-07-stabilize-corner-brace-repair-reference-identity" -->

<!-- codex-archive-log:entry-start key="2026-10-07-add-software-information-dialog" -->
### 2026-10-07｜`add-software-information-dialog`

- Archive：[openspec/changes/archive/2026-10-07-add-software-information-dialog](../openspec/changes/archive/2026-10-07-add-software-information-dialog)
- 完成內容：在主視窗增加「說明」選單，並提供「軟體資訊」命令。；新增獨立、可重複開啟的軟體資訊視窗，集中顯示產品名稱、版本、作者與開發歷程。；建立不依賴 Tkinter 的產品資訊模型／provider，讓 UI 與測試共用同一份顯示資料。
- Capabilities：`release-package-assets`、`software-information-presentation`
- 驗證：all artifacts done; 18/18 tasks complete; implementation verification passed
- Specs：synced: release-package-assets modified; software-information-presentation created; main specs validation 37 passed
<!-- codex-archive-log:entry-end key="2026-10-07-add-software-information-dialog" -->

<!-- codex-archive-log:entry-start key="2026-10-06-add-waler-tail-adjustment-block" -->
### 2026-10-06｜`add-waler-tail-adjustment-block`

- Archive：[openspec/changes/archive/2026-10-06-add-waler-tail-adjustment-block](../openspec/changes/archive/2026-10-06-add-waler-tail-adjustment-block)
- 完成內容：將 `100／150／200／300 mm` 定義為 Waler 可用的單一尾端調整塊尺寸，`0` 代表不配置。；將 Waler 完成長度契約改為 `steel_length + tail_adjustment + gap = required_length`，Gap 合法閉區間為 `0～150 mm`。；定義 deterministic 選擇順序：短差在 `0～150 mm` 時 `tail_adjustment = 0`、Gap 等於短差；短差大於 `150 mm` 時，選擇能使 `0 <= Gap <= 150 mm` 的最小調整塊。
- Capabilities：`waler-plan-evaluation`
- 驗證：All artifacts complete; 25/25 tasks complete; strict change validation passed.
- Specs：Synced waler-plan-evaluation to main specs; openspec validate --specs passed (36/36).
<!-- codex-archive-log:entry-end key="2026-10-06-add-waler-tail-adjustment-block" -->

<!-- codex-archive-log:entry-start key="2026-10-06-optimize-dxf-source-exclusion-workflow" -->
### 2026-10-06｜`optimize-dxf-source-exclusion-workflow`

- Archive：[openspec/changes/archive/2026-10-06-optimize-dxf-source-exclusion-workflow](../openspec/changes/archive/2026-10-06-optimize-dxf-source-exclusion-workflow)
- 完成內容：維持現有單一 `ReviewItem` 來源排除入口與確認流程，不新增多選或 batch state。；CornerBrace replay 採方案 D：只加速單次 `plan_corner_brace_repair()`。候選 validation 使用相同工程規則，只計算暫時角撐自身的 connection，並以相同 duplicate predicate逐一比較既有角撐；同次呼叫另預建 Waler／Strut lookup、template、relationship frame與方向／anchor索引。；所有方案 D 暫存資料在單次 plan 結束後丟棄，不跨 repair 共用，不建立 dependency footprint或 repair input fingerprint，也不沿用舊 repair outcome。
- Capabilities：`dxf-source-exclusion-workflow`
- 驗證：36/36 tasks complete; OpenSpec strict validation passed; 602 focused tests passed; full suite 1672 tests passed with 1 skipped
- Specs：Synced dxf-source-exclusion-workflow main spec with 6 requirements and 23 scenarios; openspec validate --specs passed 36/36
<!-- codex-archive-log:entry-end key="2026-10-06-optimize-dxf-source-exclusion-workflow" -->

<!-- codex-archive-log:entry-start key="2026-10-06-expand-global-waler-candidate-pool" -->
### 2026-10-06｜`expand-global-waler-candidate-pool`

- Archive：[openspec/changes/archive/2026-10-06-expand-global-waler-candidate-pool](../openspec/changes/archive/2026-10-06-expand-global-waler-candidate-pool)
- 完成內容：為 `OptimizeWaler` 定義明確的 Single／Global candidate retention profile，預設仍是 Single Top 5。；Global profile 收集每個實際執行 stage 最終 population 中所有合法且完整 solution signature 不重複的候選。；跨已執行 stages 合併候選、依既有 deterministic local ordering 排定可能大於 5 的 rank。
- Capabilities：`global-waler-candidate-pool`、`waler-plan-evaluation`
- 驗證：24/24 tasks complete, artifacts complete, strict validation passed
- Specs：synced and verified, openspec validate --specs 35 passed and 0 failed
<!-- codex-archive-log:entry-end key="2026-10-06-expand-global-waler-candidate-pool" -->

<!-- codex-archive-log:entry-start key="2026-10-06-separate-waler-positioning-from-formal-adoption" -->
### 2026-10-06｜`separate-waler-positioning-from-formal-adoption`

- Archive：[openspec/changes/archive/2026-10-06-separate-waler-positioning-from-formal-adoption](../openspec/changes/archive/2026-10-06-separate-waler-positioning-from-formal-adoption)
- 完成內容：候選點區與Preview不新增正式化按鈕；兩處只保留一般幾何選點操作。；在 DXF Review「修改工具」新增「圍令正式化」，顯示／啟用方式比照「中間柱關聯修補」：只依目前選取的唯一 repair-eligible Waler決定入口，不在顯示階段建立plan。；專用視窗提供互斥的「線的來源」單選：預設「點位清單」，並顯示合法起終點、預選目前`selected_start_point_id`／`selected_end_point_id`；只有目標member存在最新CAD pair時才enable「已讀取的CAD線」。
- Capabilities：`dxf-waler-engineering-line-repair`
- 驗證：All artifacts complete; 22/22 tasks complete; strict validation passed
- Specs：Synced to main specs and openspec validate --specs passed
<!-- codex-archive-log:entry-end key="2026-10-06-separate-waler-positioning-from-formal-adoption" -->

<!-- codex-archive-log:entry-start key="2026-10-06-resolve-provisional-waler-manually" -->
### 2026-10-06｜`resolve-provisional-waler-manually`

- Archive：[openspec/changes/archive/2026-10-06-resolve-provisional-waler-manually](../openspec/changes/archive/2026-10-06-resolve-provisional-waler-manually)
- 完成內容：為具有唯一 source identity 的 provisional Waler 提供明確的「採用為正式圍令」修補操作。；允許使用既有候選點配對或 CAD 指定工程線作為人工正式線來源，並使用一致的驗證與原子提交語意。；將已採用人工線設為該 Waler 的正式工程線兼接觸線，記錄人工裁決 provenance，並重建所有依賴正式 Waler geometry 的衍生結果。
- Capabilities：`dxf-waler-contact-face-recognition`、`dxf-waler-engineering-line-repair`、`paused-dxf-review-source-relink`
- 驗證：All artifacts complete; 32/32 tasks complete; full DXF suite 874 passed, 1 skipped; strict change validation passed.
- Specs：Synced: dxf-waler-contact-face-recognition modified; dxf-waler-engineering-line-repair created; paused-dxf-review-source-relink updated; openspec validate --specs passed (34/34).
<!-- codex-archive-log:entry-end key="2026-10-06-resolve-provisional-waler-manually" -->

<!-- codex-archive-log:entry-start key="2026-10-06-clarify-dxf-review-diagnostics" -->
### 2026-10-06｜`clarify-dxf-review-diagnostics`

- Archive：[openspec/changes/archive/2026-10-06-clarify-dxf-review-diagnostics](../openspec/changes/archive/2026-10-06-clarify-dxf-review-diagnostics)
- 完成內容：為 DXF Review 問題建立一致的使用者可見投影：中文類型、白話說明、可執行的處理建議。；主要問題清單與選取項目明細使用同一份投影，不再把原始 diagnostic code 當作主要類型文字。；將內部英文與程式狀態詞改成工程人員可直接理解的繁體中文；保留必要的正式構件 ID、來源 handle、量測值與阻擋狀態。
- Capabilities：`dxf-review-engineering-data-presentation`
- 驗證：All artifacts complete; 16/16 tasks complete; strict change validation and full DXF regression passed.
- Specs：Synced to main spec dxf-review-engineering-data-presentation; openspec validate --specs passed.
<!-- codex-archive-log:entry-end key="2026-10-06-clarify-dxf-review-diagnostics" -->

<!-- codex-archive-log:entry-start key="2026-10-05-calculate-waler-width-orthogonally" -->
### 2026-10-05｜`calculate-waler-width-orthogonally`

- Archive：[openspec/changes/archive/2026-10-05-calculate-waler-width-orthogonally](../openspec/changes/archive/2026-10-05-calculate-waler-width-orthogonally)
- 完成內容：將可靠 Waler envelope 的代表寬度定義為兩條已選外側 supporting lines 的正交間距。；讓縱向端點錯位、斜端長度及有限 segment overhang 不再改變同一外側 rail pair 的寬度。；新增 Y29 W18 source `69F` regression，固定約 `400.000 mm` 的寬度，以及在目前材料規格中改為匹配 `H400x400`、不再匹配 `H414x405` 的結果。
- Capabilities：`dxf-waler-contact-face-recognition`
- 驗證：All artifacts complete; all 11 tasks complete; strict change validation passed.
- Specs：Synced dxf-waler-contact-face-recognition main spec; openspec validate --specs passed.
<!-- codex-archive-log:entry-end key="2026-10-05-calculate-waler-width-orthogonally" -->

<!-- codex-archive-log:entry-start key="2026-10-05-rigidly-translate-braces-on-waler-adjustment" -->
### 2026-10-05｜`rigidly-translate-braces-on-waler-adjustment`

- Archive：[openspec/changes/archive/2026-10-05-rigidly-translate-braces-on-waler-adjustment](../openspec/changes/archive/2026-10-05-rigidly-translate-braces-on-waler-adjustment)
- 完成內容：對每支受影響的一般 Brace，使用兩端最終 Waler 有限線段聯立求解共同平移，而非只更新被編輯端。；將 Brace baseline 方向與長度列為 Engineering Hard Constraint；調整後兩端差向量必須與 baseline 幾何等價。；即使只編輯一端 Waler，也同步更新 Brace 另一端接點及兩端 Waler station。
- Capabilities：`dxf-waler-contact-adjustment`
- 驗證：17/17 tasks complete; OpenSpec strict validation and full test suite passed (1,572 tests, 1 skipped).
- Specs：Synced dxf-waler-contact-adjustment main spec; openspec validate --specs passed.
<!-- codex-archive-log:entry-end key="2026-10-05-rigidly-translate-braces-on-waler-adjustment" -->

<!-- codex-archive-log:entry-start key="2026-10-05-separate-release-and-regression-assets" -->
### 2026-10-05｜`separate-release-and-regression-assets`

- Archive：[openspec/changes/archive/2026-10-05-separate-release-and-regression-assets](../openspec/changes/archive/2026-10-05-separate-release-and-regression-assets)
- 完成內容：從 `SupportSolver.spec` 移除 `project_cases/`、`test_cases/` 及其他 regression-only 資產的發行複製。；將下列三份 DXF 定義為正式使用者素材，統一輸出至成品 `sample_dxf/`：；以明確 allowlist 與 package contract test 保證三份素材完整存在，且不會因來源目錄新增檔案而自動擴大發行內容。
- Capabilities：`release-package-assets`
- 驗證：18/18 tasks complete; OpenSpec strict validation passed
- Specs：Synced release-package-assets main spec (4 requirements, 9 scenarios)
<!-- codex-archive-log:entry-end key="2026-10-05-separate-release-and-regression-assets" -->

<!-- codex-archive-log:entry-start key="2026-10-04-reconcile-post-audit-documentation" -->
### 2026-10-04｜`reconcile-post-audit-documentation`

- Archive：[openspec/changes/archive/2026-10-04-reconcile-post-audit-documentation](../openspec/changes/archive/2026-10-04-reconcile-post-audit-documentation)
- 完成內容：新增 `dxf-corner-brace-repair-tool` MODIFIED delta，限縮 template requirement、provenance 與 replay 全稱文字，明確分開兩種 mode；只修正規格文字，runtime 行為不變。；更新 `docs/WORKFLOW.md`，同時描述 reference-template 與 body-relationship repair。；修正 README Qty 摘要，明確指出 Support Qty／purchase 尚未進入 score。
- Capabilities：`dxf-corner-brace-repair-tool`
- 驗證：9/9 tasks complete; change strict validation passed
- Specs：Synced dxf-corner-brace-repair-tool; openspec validate --specs passed
<!-- codex-archive-log:entry-end key="2026-10-04-reconcile-post-audit-documentation" -->

<!-- codex-archive-log:entry-start key="2026-10-04-retire-unused-dxf-legacy-functions" -->
### 2026-10-04｜`retire-unused-dxf-legacy-functions`

- Archive：[openspec/changes/archive/2026-10-04-retire-unused-dxf-legacy-functions](../openspec/changes/archive/2026-10-04-retire-unused-dxf-legacy-functions)
- 完成內容：Audit `_legacy_corner_brace_candidates_from_group`、`_associate_components_to_struts_legacy`、`_select_waler_inner_lines`。；驗證 repository executable code、package exports、dynamic attribute lookup、PyInstaller entry、維護腳本與 tests 均無 consumer。；三者全部通過 gate 後，只移除這三個 private function definitions，並修正 live docstring 的 dangling name reference。
- Capabilities：無 spec-level capability
- 驗證：All artifacts complete; all 15/15 tasks complete; strict validation passed.
- Specs：No delta specs (skip_specs: true).
<!-- codex-archive-log:entry-end key="2026-10-04-retire-unused-dxf-legacy-functions" -->

<!-- codex-archive-log:entry-start key="2026-10-04-cancel-stale-solves-on-cad-update" -->
### 2026-10-04｜`cancel-stale-solves-on-cad-update`

- Archive：[openspec/changes/archive/2026-10-04-cancel-stale-solves-on-cad-update](../openspec/changes/archive/2026-10-04-cancel-stale-solves-on-cad-update)
- 完成內容：新增三種 Solver 共用的 runtime snapshot handle、operation identity、thread-safe cancellation token、stale adoption gate 與 cancelled outcome；handle 從 snapshot 建立起即受 registry 管理，而不是等 worker start 才登記。；在 Support、Single Waler 與 Global Waler 的既有安全搜尋邊界加入 cancellation checkpoint；未取消路徑必須維持相同結果與排序。；讓有效且非 no-op 的 CAD add／update 在 Project mutation 前 invalidate 所有已登記且未關閉的 Solver snapshot handle，並取消其中的 running worker，但不等待 worker 才套用更新。
- Capabilities：`global-waler-result-adoption`、`solver-cad-update-cancellation`
- 驗證：Artifacts complete (4/4); tasks complete (21/21); strict change validation passed
- Specs：Synced to main specs: global-waler-result-adoption modified; solver-cad-update-cancellation created; main-spec validation passed
<!-- codex-archive-log:entry-end key="2026-10-04-cancel-stale-solves-on-cad-update" -->

<!-- codex-archive-log:entry-start key="2026-10-04-mark-invalid-results-in-exports" -->
### 2026-10-04｜`mark-invalid-results-in-exports`

- Archive：[openspec/changes/archive/2026-10-04-mark-invalid-results-in-exports](../openspec/changes/archive/2026-10-04-mark-invalid-results-in-exports)
- 完成內容：建立共用成果匯出 projection，正規化每個 member plan 的 `valid` 與 ordered reasons。；Excel 材料明細加入「是否合法」與「不合法原因」欄位；合法方案原因保持空白。；DXF 新增專用 invalid-result warning layer，以紅色文字在對應構件附近標示構件編號與原因。
- Capabilities：`dxf-result-export`、`excel-result-export`
- 驗證：All artifacts complete; 10/10 tasks complete; change strict validation passed.
- Specs：Synced to main specs; openspec validate --specs --strict passed (30 specs).
<!-- codex-archive-log:entry-end key="2026-10-04-mark-invalid-results-in-exports" -->

<!-- codex-archive-log:entry-start key="2026-10-04-align-solver-validation-contracts" -->
### 2026-10-04｜`align-solver-validation-contracts`

- Archive：[openspec/changes/archive/2026-10-04-align-solver-validation-contracts](../openspec/changes/archive/2026-10-04-align-solver-validation-contracts)
- 完成內容：修改 Waler material context，保留未提供與明確空可購買集合的語意差異。；明確空集合使有 Steel segment 的 Waler plan 產生 non-purchasable issues，且不進行 allocation／score。；明確空集合進入自動求解時仍以既有 invalid-candidate penalty 作為 fitness；Single／Global 無合法方案時回傳既有失敗結果與 diagnostics，不以 exception 表示正常的不可行結果。
- Capabilities：`support-shim-joint-validation`、`waler-plan-evaluation`
- 驗證：11/11 tasks complete; strict change validation, main-spec validation, verification review, targeted tests, and 1500-test full suite passed.
- Specs：Synced support-shim-joint-validation and waler-plan-evaluation delta specs; openspec validate --specs passed (29/29).
<!-- codex-archive-log:entry-end key="2026-10-04-align-solver-validation-contracts" -->

<!-- codex-archive-log:entry-start key="2026-10-04-harden-project-state-transactions" -->
### 2026-10-04｜`harden-project-state-transactions`

- Archive：[openspec/changes/archive/2026-10-04-harden-project-state-transactions](../openspec/changes/archive/2026-10-04-harden-project-state-transactions)
- 完成內容：定義 Project load、Support／Single result adoption、CAD input mutation 與 Material Spec mutation 的一致 transaction outcome，並禁止 commit 呼叫 setter、trace、callback、filesystem 或 collection mutation。；將結果失效、metadata、cache replacement 與 dirty finalization 納入 staged state；projection 失敗後鎖住修改，新增完整重新投影入口。；CAD mutation 已 commit 但 ACK 失敗時停止監聽並阻止 save，直到 pending event 被明確處理；相同 event ID 不得重複套用。
- Capabilities：`project-state-transaction-consistency`
- 驗證：All 4 artifacts complete; all 14 tasks complete; full suite 1488 passed, 1 skipped; strict change validation passed.
- Specs：Synced project-state-transaction-consistency to main specs; openspec validate --specs passed (29 specs).
<!-- codex-archive-log:entry-end key="2026-10-04-harden-project-state-transactions" -->

<!-- codex-archive-log:entry-start key="2026-10-01-reconcile-repository-documentation" -->
### 2026-10-01｜`reconcile-repository-documentation`

- Archive：[openspec/changes/archive/2026-10-01-reconcile-repository-documentation](../openspec/changes/archive/2026-10-01-reconcile-repository-documentation)
- 完成內容：將 README 的定位從「程式碼完整鏡像」收斂為 repository 入口、系統概覽、操作／開發導覽與真相來源索引。；修正已確認的過時內容：測試案例 UI、移除的方法、legacy schema 升級、Waler 評分重複、舊測試失敗、過時 UI 結構及可由程式自動取得而不應手寫維護的數量。；對齊這次已完成的 Support Shim、暫時庫存政策、schema compatibility、manual Project result-only DXF、Material Spec editing ownership、legacy normalization 移除及 Waler evaluator 共用狀態。
- Capabilities：無 spec-level capability
- 驗證：Artifacts complete: proposal/design/tasks done, specs skipped; tasks 18/18 complete; openspec validate --all --strict passed 29/29.
- Specs：No delta specs; skip_specs true; main specs unchanged.
<!-- codex-archive-log:entry-end key="2026-10-01-reconcile-repository-documentation" -->

<!-- codex-archive-log:entry-start key="2026-10-01-recognize-skew-cut-brace-outlines" -->
### 2026-10-01｜`recognize-skew-cut-brace-outlines`

- Archive：[openspec/changes/archive/2026-10-01-recognize-skew-cut-brace-outlines](../openspec/changes/archive/2026-10-01-recognize-skew-cut-brace-outlines)
- 完成內容：修改一般及 component-like Brace closed-outline eligibility：完整、無分支且只有一個可靠 body interpretation 的封閉外框，可由 topology 證明完整 extent，不要求兩條 rail 各自達到共用 `0.8` coverage。；定義斜切 terminal cuts 的資格：必須各自有限連接兩側 outer rails，並與唯一 body midline 形成合法有限交點。；將 closed skew-cut outline 的 source-supported axis 端點定義為 body midline 與兩個 terminal cuts 的交點；不得以 bounding projection extrema 或為碰觸 Waler 而任意外插。
- Capabilities：`bim-block-brace-recognition`
- 驗證：All artifacts complete; all 18 tasks complete; 232 related unittest cases passed
- Specs：Synced 3 added requirements to bim-block-brace-recognition; openspec validate --specs passed (28 specs); strict change validation passed
<!-- codex-archive-log:entry-end key="2026-10-01-recognize-skew-cut-brace-outlines" -->

<!-- codex-archive-log:entry-start key="2026-10-01-unify-waler-plan-evaluation" -->
### 2026-10-01｜`unify-waler-plan-evaluation`

- Archive：[openspec/changes/archive/2026-10-01-unify-waler-plan-evaluation](../openspec/changes/archive/2026-10-01-unify-waler-plan-evaluation)
- 完成內容：新增可由自動 Solver 與人工編輯共同呼叫的 Waler plan evaluation 契約。；將 segment legality、joint clearance、purchasable length、exact-length allocation、材料比例與 local score 收斂到同一評估結果。；為評估問題定義穩定、具名的 issue code，並讓分類／去重依 code 與結構化內容進行。
- Capabilities：`waler-plan-evaluation`
- 驗證：All 23 artifacts/tasks complete; openspec verify-change checks passed; 247 related tests passed; strict validation passed
- Specs：Synced new waler-plan-evaluation main spec; openspec validate --specs passed
<!-- codex-archive-log:entry-end key="2026-10-01-unify-waler-plan-evaluation" -->

<!-- codex-archive-log:entry-start key="2026-10-01-remove-legacy-strut-position-normalization" -->
### 2026-10-01｜`remove-legacy-strut-position-normalization`

- Archive：[openspec/changes/archive/2026-10-01-remove-legacy-strut-position-normalization](../openspec/changes/archive/2026-10-01-remove-legacy-strut-position-normalization)
- 完成內容：新增 Project input row 的通用現行欄位驗證，依 table contract 回報缺少及不支援欄位，不針對特定 legacy key 寫特例。；**BREAKING**：移除 `Beam1`／`Beam2`、`Column1`／`Column2` 等 legacy Strut position 的 Application normalization、Brace row legacy `Type` cleanup 與 Main lazy migration；不符合現行 row schema 的 persisted Project 不再可藉由載入或顯示流程轉換，runtime row builders也不再包含legacy-specific cleanup。；移除 `tools/upgrade_project_schema.py` 及其 legacy upgrade tests／文件入口；試行期不掃描或轉換既有 Project 檔，舊檔由使用者自行刪除。
- Capabilities：`project-input-row-schema`、`project-schema-compatibility`
- 驗證：19/19 tasks complete; strict validation passed; full test suite 1468 passed with 1 skipped
- Specs：Synced project-input-row-schema and project-schema-compatibility; openspec validate --specs passed
<!-- codex-archive-log:entry-end key="2026-10-01-remove-legacy-strut-position-normalization" -->

<!-- codex-archive-log:entry-start key="2026-10-01-align-support-shim-joint-validation" -->
### 2026-10-01｜`align-support-shim-joint-validation`

- Archive：[openspec/changes/archive/2026-10-01-align-support-shim-joint-validation](../openspec/changes/archive/2026-10-01-align-support-shim-joint-validation)
- 完成內容：將零塊或一塊非零 Shim 定義為唯一合法數量；`shim = 0` 表示沒有 Shim piece。；將 Steel／Steel、RC／Steel、Steel／RC、RC／RC 的 Shim placement 規則集中在共用 validator。；將缺失、空白或無法辨識的 Waler 類型一律視為 Steel。
- Capabilities：`support-shim-joint-validation`
- 驗證：All 18/18 tasks complete; strict change validation passed; implementation verification passed (9 requirements, 32 scenarios).
- Specs：Synced new capability support-shim-joint-validation to main specs; openspec validate --specs passed (26 specs).
<!-- codex-archive-log:entry-end key="2026-10-01-align-support-shim-joint-validation" -->

<!-- codex-archive-log:entry-start key="2026-10-01-export-result-only-dxf-for-manual-projects" -->
### 2026-10-01｜`export-result-only-dxf-for-manual-projects`

- Archive：[openspec/changes/archive/2026-10-01-export-result-only-dxf-for-manual-projects](../openspec/changes/archive/2026-10-01-export-result-only-dxf-for-manual-projects)
- 完成內容：在 DXF 匯出前只依 `dxf_import_state` 是否存在判定模式：欄位不存在或 `None` 為 `result-only`；存在（含 `{}`）則必須以 source-backed 規則解析，資訊不完整即失敗。`dxf_workflow_status` 不參與模式判定。；手動 Project 走 result-only 模式時，將 Project 座標直接視為 WCS，採 identity transform。；Result-only DXF 只建立實際有結果的 Solver 成果圖層與必要結果符號，不輸出背景 DXF 或 `SD_PROJECT_*` geometry 圖層。
- Capabilities：`dxf-result-export`
- 驗證：16/16 tasks complete; strict validation passed; focused and full test suites passed
- Specs：synced: created openspec/specs/dxf-result-export/spec.md; openspec validate --specs passed
<!-- codex-archive-log:entry-end key="2026-10-01-export-result-only-dxf-for-manual-projects" -->

<!-- codex-archive-log:entry-start key="2026-10-01-move-material-spec-editing-to-application" -->
### 2026-10-01｜`move-material-spec-editing-to-application`

- Archive：[openspec/changes/archive/2026-10-01-move-material-spec-editing-to-application](../openspec/changes/archive/2026-10-01-move-material-spec-editing-to-application)
- 完成內容：新增 Application material-spec editing use case，涵蓋 rename、Usage 修改限制、引用查找、刪除保護、跨表同步及 input-change effect planning。；定義明確 request、成功 staged result 與結構化失敗結果；失敗不得改動傳入的 live Project state。；將 Main 縮減為收集 UI 輸入／確認、呼叫 use case、顯示既有錯誤及採用 staged result。
- Capabilities：無 spec-level capability
- 驗證：All artifacts complete; all 18 tasks complete; strict validation passed
- Specs：No delta specs
<!-- codex-archive-log:entry-end key="2026-10-01-move-material-spec-editing-to-application" -->

<!-- codex-archive-log:entry-start key="2026-10-01-define-project-schema-compatibility-policy" -->
### 2026-10-01｜`define-project-schema-compatibility-policy`

- Archive：[openspec/changes/archive/2026-10-01-define-project-schema-compatibility-policy](../openspec/changes/archive/2026-10-01-define-project-schema-compatibility-policy)
- 完成內容：定義 Project 載入的版本分類與結構驗證順序。；`schema_version` 存在時只接受排除 bool、且大於等於 `1` 的真正整數；字串、浮點數、`null`、布林值、`0` 與負數均以格式錯誤拒絕。；允許版本號缺少或低於 3、但資料結構完整符合現行 schema 3 的檔案開啟。
- Capabilities：`project-schema-compatibility`
- 驗證：10/10 tasks complete; openspec validate --strict passed; focused project regression 109 tests passed; presentation boundary 32 tests passed
- Specs：project-schema-compatibility synced to openspec/specs/project-schema-compatibility/spec.md
<!-- codex-archive-log:entry-end key="2026-10-01-define-project-schema-compatibility-policy" -->

<!-- codex-archive-log:entry-start key="2026-09-30-decouple-waler-side-evidence-from-terminal-identity" -->
### 2026-09-30｜`decouple-waler-side-evidence-from-terminal-identity`

- Archive：[openspec/changes/archive/2026-09-30-decouple-waler-side-evidence-from-terminal-identity](../openspec/changes/archive/2026-09-30-decouple-waler-side-evidence-from-terminal-identity)
- 完成內容：把 terminal candidate 的幾何來向保存為只供 Waler contact-face finalization 使用的 side-only evidence；不要求該 terminal 已唯一選定 Waler identity。；對每支候選 Waler 分別判定 member 本體位於 provisional axis 的哪一側；只有合法、非退化且對該 Waler 可追溯的候選才可參與。；採用 unique-first evidence precedence：可靠 unique evidence 是接觸側的 authoritative set；competing side-only evidence 只在沒有可靠 unique evidence 時參與選側，與 authoritative set 相反時只產生不阻擋的可追溯 warning。
- Capabilities：`brace-axis-waler-extension`、`dxf-waler-contact-face-recognition`、`dxf-waler-overlap-diagnostics`
- 驗證：All four artifacts complete; all 22 tasks complete; openspec validate --specs and openspec validate decouple-waler-side-evidence-from-terminal-identity --strict passed; focused and full DXF, review/layout/settings, and architecture boundary tests passed.
- Specs：Synced brace-axis-waler-extension, dxf-waler-contact-face-recognition, and dxf-waler-overlap-diagnostics main specs before archive.
<!-- codex-archive-log:entry-end key="2026-09-30-decouple-waler-side-evidence-from-terminal-identity" -->

<!-- codex-archive-log:entry-start key="2026-09-30-focus-column-association-repair-on-selection" -->
### 2026-09-30｜`focus-column-association-repair-on-selection`

- Archive：[openspec/changes/archive/2026-09-30-focus-column-association-repair-on-selection](../openspec/changes/archive/2026-09-30-focus-column-association-repair-on-selection)
- 完成內容：「中間柱關聯修補」只在目前唯一選取的 Review 構件角色為 `column` 時可見且可啟動。；開啟工具時只向 Workflow 規劃目前選取的 Column ID；不再掃描所有柱形成 subject list。；修補視窗移除待修／已修中間柱清單，直接呈現該柱狀態、候選支撐、距離、station 與 Preview overlay。
- Capabilities：`dxf-column-association-repair`
- 驗證：13/13 tasks complete; focused and expanded test suites passed; py_compile passed; strict validation passed
- Specs：dxf-column-association-repair delta synced to main spec; openspec validate --specs passed; archived with --yes
<!-- codex-archive-log:entry-end key="2026-09-30-focus-column-association-repair-on-selection" -->

<!-- codex-archive-log:entry-start key="2026-09-30-align-review-problem-identifiers" -->
### 2026-09-30｜`align-review-problem-identifiers`

- Archive：[openspec/changes/archive/2026-09-30-align-review-problem-identifiers](../openspec/changes/archive/2026-09-30-align-review-problem-identifiers)
- 完成內容：問題說明引用已形成正式 Review member 的結構化來源時，改用 `正式 ID（來源 handle）`。；替換候選只來自該則 `ValidationMessage.source_handles` 或該訊息明確保存的 structured competing identities；文字中未被結構化列出的 handle 不替換。；緊接 `mm`、`°`、`%` 的 token，以及小數或座標的一部分不替換，避免全數字 handle 與工程數值碰撞。
- Capabilities：`dxf-review-engineering-data-presentation`
- 驗證：10/10 tasks complete; strict validation passed; focused and workflow regression tests passed
- Specs：Synced to main spec and openspec validate --specs passed
<!-- codex-archive-log:entry-end key="2026-09-30-align-review-problem-identifiers" -->

<!-- codex-archive-log:entry-start key="2026-09-30-enforce-unique-brace-waler-terminals" -->
### 2026-09-30｜`enforce-unique-brace-waler-terminals`

- Archive：[openspec/changes/archive/2026-09-30-enforce-unique-brace-waler-terminals](../openspec/changes/archive/2026-09-30-enforce-unique-brace-waler-terminals)
- 完成內容：將 Brace 自動辨識的正式成立條件明確化為：start 與 end 各自恰好一個可識別有限 Waler，且兩端 Waler 不同。；補齊正式成立的其餘必要條件：兩端 Waler contact faces 均已正式完成、Brace 軸線與各 selected face 均有合法有限交點，且提交後 Brace 長度合法；任一條件失敗皆使整支 Brace unresolved 並 blocking。；direct 與 extension 共用同一 terminal uniqueness gate；不能因 direct 候選多解而改走 extension，也不能用 Candidate Point 或來源端點規避歧義。
- Capabilities：`brace-axis-waler-extension`
- 驗證：All artifacts complete; all 18 tasks complete; openspec strict validation passed.
- Specs：brace-axis-waler-extension synced to main specs; openspec validate --specs passed.
<!-- codex-archive-log:entry-end key="2026-09-30-enforce-unique-brace-waler-terminals" -->

<!-- codex-archive-log:entry-start key="2026-09-30-select-error-components-from-preview" -->
### 2026-09-30｜`select-error-components-from-preview`

- Archive：[openspec/changes/archive/2026-09-30-select-error-components-from-preview](../openspec/changes/archive/2026-09-30-select-error-components-from-preview)
- 完成內容：為 Preview 中可見的 error／critical 未解析來源建立 source-handle hit-test 索引。；Hit index 記錄建立時的 viewport transform 與 render generation，並在 viewport、來源可見性、ReviewItems 或 active result 改變時失效；點擊不得使用 stale index。；唯一命中時，使用既有 unresolved ReviewItem 選取流程同步構件清單、問題明細與來源聚焦。
- Capabilities：`dxf-review-preview-error-selection`
- 驗證：All artifacts complete; 12/12 tasks complete; strict change validation and main-spec validation passed.
- Specs：Synced to main specs: dxf-review-preview-error-selection (new main spec created; 3 requirements, 16 scenarios).
<!-- codex-archive-log:entry-end key="2026-09-30-select-error-components-from-preview" -->

<!-- codex-archive-log:entry-start key="2026-09-30-detect-waler-overlap-errors" -->
### 2026-09-30｜`detect-waler-overlap-errors`

- Archive：[openspec/changes/archive/2026-09-30-detect-waler-overlap-errors](../openspec/changes/archive/2026-09-30-detect-waler-overlap-errors)
- 完成內容：新增跨不同 Waler source identities 的重大共線有限重疊診斷；只使用兩支可靠 source-supported provisional axes 的有限長度，並以「正有限投影重疊長度 ÷ 較短 provisional axis 長度」計算，`>= 50%` 才成立。；對每組符合條件的 Waler 建立可定位 warning；只有既有 terminal topology 或 contact-resolution outcome 直接證明該 pair 的完整 identities 同時競爭同一 terminal／finalization，才建立 blocking Review problem。Generic unresolved 或其他 pair 的競爭不得誤升級。；延伸 Waler contact-face contract：重疊造成 terminal identity 或接觸面不唯一時，provisional axis 只能作為診斷事實，不得成為正式 Waler engineering line、Project 或 Solver truth。
- Capabilities：`dxf-review-engineering-data-presentation`、`dxf-waler-contact-face-recognition`、`dxf-waler-overlap-diagnostics`
- 驗證：All artifacts complete; all 19 tasks complete; focused, regression, boundary and strict OpenSpec validation passed.
- Specs：Three delta specs synced to main specs; openspec validate --specs passed 22/22.
<!-- codex-archive-log:entry-end key="2026-09-30-detect-waler-overlap-errors" -->

<!-- codex-archive-log:entry-start key="2026-09-30-redesign-corner-brace-occlusion-recognition" -->
### 2026-09-30｜`redesign-corner-brace-occlusion-recognition`

- Archive：[openspec/changes/archive/2026-09-30-redesign-corner-brace-occlusion-recognition](../openspec/changes/archive/2026-09-30-redesign-corner-brace-occlusion-recognition)
- 完成內容：**BREAKING**：建立 `BodyGeometryEvidence` 與 `BodyRelationshipAssessment` 兩層契約；complete／occluded classification 只存在於 relationship assessment。；**BREAKING**：完整與遮擋候選都要求兩條 selected rails 各自 `coverage >= 50%`。；正式確認 CornerBrace Waler 端與 Strut 端 outward extension 各自 `<= 600 mm`；此限制與 coverage 必須同時通過。
- Capabilities：`dxf-corner-brace-centerline-extension`、`dxf-corner-brace-occluded-rail-recognition`、`dxf-corner-brace-repair-tool`
- 驗證：All artifacts complete; all 40 tasks complete; full test suite 1313 passed with 1 skipped; OpenSpec strict validation passed
- Specs：3 delta specs synced; 11 requirements modified; main specs updated and validated by archive
<!-- codex-archive-log:entry-end key="2026-09-30-redesign-corner-brace-occlusion-recognition" -->

<!-- codex-archive-log:entry-start key="2026-09-29-accept-joist-brace-connection" -->
### 2026-09-29｜`accept-joist-brace-connection`

- Archive：[openspec/changes/archive/2026-09-29-accept-joist-brace-connection](../openspec/changes/archive/2026-09-29-accept-joist-brace-connection)
- 完成內容：新增共用的托梁連接 validation contract：`beam.crossings` 或 `beam.brace_contacts` 任一非空即滿足 runtime「已連接」。；將 `BEAM_NOT_ASSOCIATED` 的觸發條件改為上述兩個 collections 同時為空；訊息明確區分「未連接」與「沒有 Strut 禁止點」。；將 BIM recognition 已建立的 Brace contact 保留到 runtime Beam／DXF Review state，不在 importer projection 時遺失。
- Capabilities：`beam-member-connection-validation`、`bim-joist-recognition`
- 驗證：OpenSpec artifacts complete; all 16 tasks complete; openspec validate --strict and openspec validate --specs --strict passed; focused 174 tests and full 1305-test suite passed.
- Specs：Synced beam-member-connection-validation (new main spec) and modified bim-joist-recognition; openspec archive reported specsUpdated=true (added 4, modified 2).
<!-- codex-archive-log:entry-end key="2026-09-29-accept-joist-brace-connection" -->

<!-- codex-archive-log:entry-start key="2026-09-29-add-waler-connected-member-engineering-data" -->
### 2026-09-29｜`add-waler-connected-member-engineering-data`

- Archive：[openspec/changes/archive/2026-09-29-add-waler-connected-member-engineering-data](../openspec/changes/archive/2026-09-29-add-waler-connected-member-engineering-data)
- 完成內容：選取正式 Waler 時，在右側工程資料新增「直接連接支撐」、「直接連接斜撐」及「直接連接角撐」。；使用既有正式關聯反向彙整構件 ID，對重複關聯去重並提供 deterministic 顯示順序。；明定 selected Waler 與各類 formal connection 使用相同 Waler member identity domain 進行 exact equality；若未來 domain 不同，只能使用既有正式 mapping。
- Capabilities：`dxf-review-engineering-data-presentation`
- 驗證：Focused/regression tests passed; full unittest discovery was stopped during long-running real-DXF recognition without observed failure.
- Specs：Delta spec synced to openspec/specs/dxf-review-engineering-data-presentation/spec.md; openspec validate --specs and change strict validation passed.
<!-- codex-archive-log:entry-end key="2026-09-29-add-waler-connected-member-engineering-data" -->

<!-- codex-archive-log:entry-start key="2026-09-29-repair-ambiguous-column-support-associations" -->
### 2026-09-29｜`repair-ambiguous-column-support-associations`

- Archive：[openspec/changes/archive/2026-09-29-repair-ambiguous-column-support-associations](../openspec/changes/archive/2026-09-29-repair-ambiguous-column-support-associations)
- 完成內容：為有明確兩支候選的中間柱歧義警告提供專用修補清單、幾何預覽與人工採用操作。；保存選中的 Column-to-Strut 關係；重建時重新計算各支撐自己的 station 與衍生禁止點。；人工單選不疊加原自動最近關聯；有效採用後移除該柱未解決的距離歧義警告，可保留「已人工判定」資訊。
- Capabilities：`dxf-column-association-repair`
- 驗證：18/18 tasks complete; 366 related tests passed; openspec validate --specs passed 20/20; strict change validation passed
- Specs：Synced new main spec dxf-column-association-repair; main specs validation passed; archive delta now already synced
<!-- codex-archive-log:entry-end key="2026-09-29-repair-ambiguous-column-support-associations" -->

<!-- codex-archive-log:entry-start key="2026-09-29-surface-provisional-double-support-candidates" -->
### 2026-09-29｜`surface-provisional-double-support-candidates`

- Archive：[openspec/changes/archive/2026-09-29-surface-provisional-double-support-candidates](../openspec/changes/archive/2026-09-29-surface-provisional-double-support-candidates)
- 完成內容：只以可靠、source-supported 的 WCS Strut axes套用既有雙路幾何門檻建立 geometry-qualified pair，並另外計算其 Waler topology qualification。；為候選提供可觀察狀態與 reason codes，至少區分可確認、Waler 待處理，以及已明確不相容。；在雙路支撐設定介面顯示 geometry-qualified 暫定候選、警告原因與幾何量測，並禁止暫定候選被接受。
- Capabilities：`dxf-double-support-recognition`
- 驗證：27/27 tasks complete; focused affected tests pass; full suite has 2 unrelated source-exclusion identity failures and 1 skip
- Specs：Delta synced to openspec/specs/dxf-double-support-recognition/spec.md; openspec validate --specs --strict passed
<!-- codex-archive-log:entry-end key="2026-09-29-surface-provisional-double-support-candidates" -->

<!-- codex-archive-log:entry-start key="2026-09-29-strengthen-brace-body-recognition" -->
### 2026-09-29｜`strengthen-brace-body-recognition`

- Archive：[openspec/changes/archive/2026-09-29-strengthen-brace-body-recognition](../openspec/changes/archive/2026-09-29-strengthen-brace-body-recognition)
- 完成內容：新增 Brace 實體寬度 Engineering Hard Constraint：所有可由自動來源幾何量得 body width 的 Brace 候選，寬度 MUST 嚴格 `> 250.0 mm`；`= 250.0 mm` 與 `< 250.0 mm` 均拒絕。；明定 component-like body evidence：同一 Brace-role root `INSERT` 的 whole-source geometry 必須足以支持實體 body／外包絡、主要 longitudinal corridor 與可靠 terminal extent；局部 pair、detail、branch、內部線、孔洞邊或零散 fragments 不得單獨成立分類。；對 component-like Brace root `INSERT` 建立明確 center-authority 順序：完整且可驗證的外框、合格 whole-root outer-envelope、最後才是 local rail-pair fallback。各 tier 必須先列舉全部候選並逐一完成完整性、whole-source support、可靠 extent、寬度量測與 hard gate，才可成為「合法 authority tier」。
- Capabilities：`bim-block-brace-recognition`
- 驗證：17/17 tasks complete; full test suite 1230 passed, 1 skipped; package layout passed; strict OpenSpec validation passed
- Specs：Synced to openspec/specs/bim-block-brace-recognition/spec.md and openspec validate --specs passed
<!-- codex-archive-log:entry-end key="2026-09-29-strengthen-brace-body-recognition" -->

<!-- codex-archive-log:entry-start key="2026-09-29-show-brace-width-in-dxf-engineering-data" -->
### 2026-09-29｜`show-brace-width-in-dxf-engineering-data`

- Archive：[openspec/changes/archive/2026-09-29-show-brace-width-in-dxf-engineering-data](../openspec/changes/archive/2026-09-29-show-brace-width-in-dxf-engineering-data)
- 完成內容：正式斜撐與角撐的右側工程資料新增「構件寬度（mm）」列。；可靠正值寬度固定顯示至小數第 3 位；未知、零值或非可靠值顯示「—」。；顯示列使用既有 DXF member 的 `source_width`，不加入新的工程資料欄位或 persistence contract。
- Capabilities：`dxf-review-engineering-data-presentation`
- 驗證：passed
- Specs：synced
<!-- codex-archive-log:entry-end key="2026-09-29-show-brace-width-in-dxf-engineering-data" -->

<!-- codex-archive-log:entry-start key="2026-09-29-recognize-occluded-corner-brace-rails" -->
### 2026-09-29｜`recognize-occluded-corner-brace-rails`

- Archive：[openspec/changes/archive/2026-09-29-recognize-occluded-corner-brace-rails](../openspec/changes/archive/2026-09-29-recognize-occluded-corner-brace-rails)
- 完成內容：將 CornerBrace rail pair 的正交間距定義為本體寬度，並將嚴格 `> 250.0 mm` 確立為正式材料／工程規則；實作完成後同步更新 `docs/DOMAIN.md`。；完整流程必須列舉全部雙 rail／雙端板 hypotheses，完成 hard gates、幾何等價合併及既有可分割性判斷；只要仍有一個或多個可正式建立的完整 CornerBrace，該 group 就不得進入遮蔽 fallback。；完整斜切／梯形 body 以雙 rail、雙端板、四個實際 terminal connections 與唯一 closed traversal 成立；它不因 rail 原始長度不同而進入遮蔽 fallback，且 `source_width` 仍使用 rail separation。
- Capabilities：`dxf-corner-brace-centerline-extension`、`dxf-corner-brace-occluded-rail-recognition`、`dxf-corner-brace-repair-tool`
- 驗證：All 4 planning artifacts complete; all 18/18 implementation tasks complete; strict change validation and full unittest regression passed (1203 tests, 1 skipped).
- Specs：Synced 5 added and 3 modified requirements to main specs; openspec validate --specs --strict passed.
<!-- codex-archive-log:entry-end key="2026-09-29-recognize-occluded-corner-brace-rails" -->

<!-- codex-archive-log:entry-start key="2026-09-29-redesign-corner-brace-repair-preview" -->
### 2026-09-29｜`redesign-corner-brace-repair-preview`

- Archive：[openspec/changes/archive/2026-09-29-redesign-corner-brace-repair-preview](../openspec/changes/archive/2026-09-29-redesign-corner-brace-repair-preview)
- 完成內容：重整角撐修補預覽的資訊層級，為單一候選提供直接的建議方案摘要。；保留多候選選取能力；選取候選後以相同摘要與明細區呈現。；在預覽圖層以灰色顯示所選角撐 exact source geometry 的全部來源線段，並區分建議軸線與定位錨點。
- Capabilities：`dxf-corner-brace-repair-tool`
- 驗證：All artifacts complete; tasks 12/12 complete; strict validation passed
- Specs：Synced dxf-corner-brace-repair-tool delta to main spec; specs validation passed
<!-- codex-archive-log:entry-end key="2026-09-29-redesign-corner-brace-repair-preview" -->

<!-- codex-archive-log:entry-start key="2026-09-28-recognize-joist-terminal-residuals" -->
### 2026-09-28｜`recognize-joist-terminal-residuals`

- Archive：[openspec/changes/archive/2026-09-28-recognize-joist-terminal-residuals](../openspec/changes/archive/2026-09-28-recognize-joist-terminal-residuals)
- 完成內容：為 BIM Joist 定義 Column-qualified terminal residual：必須屬於同一 root、位於已驗證 Column relation 的 terminal side、方向相容，並對齊既有 Joist envelope 的 longitudinal rail band。；新增具名 `700 mm` inclusive Column terminal window；距離從 formal Column center 沿既有 Joist longitudinal axis 朝 terminal outward direction，以 signed projection 量測到殘線最外來源投影。；允許合格殘線跨越中間柱實體寬度或 BIM 投影造成的 interior gap，更新 source-supported terminal extent；不得固定延長 700 mm 或以 Column context 憑空建立幾何。
- Capabilities：`bim-joist-recognition`
- 驗證：4/4 artifacts complete; 20/20 tasks complete; strict change validation and full DXF regression passed
- Specs：Synced to main specs; openspec validate --specs passed
<!-- codex-archive-log:entry-end key="2026-09-28-recognize-joist-terminal-residuals" -->

<!-- codex-archive-log:entry-start key="2026-09-28-localize-corner-brace-repair-ui" -->
### 2026-09-28｜`localize-corner-brace-repair-ui`

- Archive：[openspec/changes/archive/2026-09-28-localize-corner-brace-repair-ui](../openspec/changes/archive/2026-09-28-localize-corner-brace-repair-ui)
- 完成內容：將角撐修補視窗的說明、表格欄位、空白提示、候選明細與操作回饋改為繁體中文。；在既有 Presentation label boundary 集中可重複的角色與角撐修補移植方式術語，至少涵蓋 `corner_brace`、`same_side` 與 `mirrored`，並保留未知值的可診斷 fallback。；讓角撐修補介面使用共用術語來源；完整的視窗說明、操作引導與訊息框句子仍留在各自 UI boundary。
- Capabilities：`dxf-corner-brace-repair-tool`
- 驗證：All 4 planning artifacts complete; all 9 implementation tasks complete.
- Specs：Synced dxf-corner-brace-repair-tool main spec; openspec validate --specs passed.
<!-- codex-archive-log:entry-end key="2026-09-28-localize-corner-brace-repair-ui" -->

<!-- codex-archive-log:entry-start key="2026-09-28-reference-template-corner-brace-repair" -->
### 2026-09-28｜`reference-template-corner-brace-repair`

- Archive：[openspec/changes/archive/2026-09-28-reference-template-corner-brace-repair](../openspec/changes/archive/2026-09-28-reference-template-corner-brace-repair)
- 完成內容：將人工 CornerBrace repair 的 candidate generation 改為 reference-template transfer：先辨識目標有限 Waler／Strut 關係，再從相容的已成功角撐擷取相對於 Waler／Strut 交點的局部配置尺寸，移植或鏡射到目標關係。；定義 reference 相容性與優先順序：同一 Waler／Strut 的另一側優先，其次為相同 endpoint topology、相近 Waler／Strut 局部幾何的鄰近 Strut；空間距離只在通過相容性後排序，不得使 reference 合法。；將 exact target residual 的角色改為必要驗證證據：至少須能支持圍令端連接板位置或角撐軸方向，並驗證 transferred candidate 與殘線 corridor 一致；不得再要求殘線自行提供完整角撐長度或兩端交點。
- Capabilities：`dxf-corner-brace-centerline-extension`、`dxf-corner-brace-repair-tool`
- 驗證：All planning artifacts complete; all 28 of 28 tasks complete.
- Specs：Synced to main specs: 1 added, 9 modified, 1 removed requirement.
<!-- codex-archive-log:entry-end key="2026-09-28-reference-template-corner-brace-repair" -->

<!-- codex-archive-log:entry-start key="2026-09-28-add-archive-development-log" -->
### 2026-09-28｜`add-archive-development-log`

- Archive：[openspec/changes/archive/2026-09-28-add-archive-development-log](../openspec/changes/archive/2026-09-28-add-archive-development-log)
- 完成內容：新增 `docs/DEVELOPMENT_HISTORY.md`，以使用者提供、截止於 2026/09/28 早上的歷史時間線與 AI 協作統計作為不可自動回填的起始內容。；新增可從 archived OpenSpec change 產生固定格式紀錄的更新器，至少包含封存日期、change 名稱、archive 路徑、完成摘要、受影響 capability 與驗證狀態。；擴充 Codex 的 OpenSpec archive workflow：archive 成功後必須呼叫更新器，將新條目加在封存紀錄區塊最上方，並在完成回報中說明開發歷程是否已更新。
- Capabilities：`archive-development-history`
- 驗證：All 4 artifacts and 12/12 tasks complete; focused tests passed; OpenSpec strict validation passed
- Specs：Synced to main specs; archive-development-history strict validation passed
<!-- codex-archive-log:entry-end key="2026-09-28-add-archive-development-log" -->

<!-- codex-archive-log:end -->

## 人工補充紀錄

可在此處補充 GPT、Copilot、LINE、會議或其他來源的開發紀錄。Codex 的自動更新器
不會修改此區塊。

## 起始歷史紀錄（截至 2026/09/28 早上）

| 日期 | 紀錄 |
| --- | --- |
| **2026/05/19** | 副理提供相關檔案及廠商先前製作的支撐配置試作品影片。 |
| **2026/05/29** | 索取 CAD 圖面並開始確認工程規則；確認千斤頂彼此至少 **600 mm（心到心）**。 |
| **2026/06/11** | 已有新的支撐配置成果，約副理討論程式進度。 |
| **2026/07/14** | 開始思考將圍令材料配置與橫向支撐拼接兩個最佳化問題整合，逐漸形成「全域配置＋單支可行拼接」的分層架構。 |
| **2026/07/15　【Git｜v1.0.0】** | **`11ee6e7` — Initial commit**。第一次將專案正式放入 Git 版本控制。這可以視為 Git 上可追溯的起始版本；實際開發則早於此日期。 |
| **2026/07/20–23** | 持續與副理討論新版支撐程式，並交換最新檔案及 Y01 CAD 資料。 |
| **2026/07/21** | 以 W1、總長 95,500 mm 等實際資料測試圍令最佳化，整理庫存、接頭禁區與評分條件。 |
| **2026/07/27　【Git｜v1.0.0】** | **`61b6d67` —「Solver第一版」**。這是第一個很明確的功能里程碑：支撐／圍令最佳化已經形成可以獨立稱為 Solver 的版本；commit 中也已包含材料庫存資料及打包設定。 |
| **2026/07/29　【Git｜v1.0.0】** | **`3b9b53f` — `CAD_builder update`**。CAD 輸入正式成為重大版本功能；同期開發 progeCAD ↔ Python 的資料橋接。Git 版本與對話紀錄時間吻合。 |
| **2026/07/29–30** | 測試 CAD Bridge 及公司電腦執行環境，遇到 Python 在其他電腦無法正常執行的問題。 |
| **2026/08/05–07** | 開始由「人工點 CAD」往「直接讀 DXF」發展；研究 DXF、`ezdxf`、Layer、Entity 與工程模型辨識。 |
| **2026/08/07–10** | 以 Y1A 人工配置與 Solver 比較，持續調查材料比例、候選池、Jack 位置、Phase 1 Cache、TopN 等問題；DXF 辨識亦逐步加入人工確認、候選點等機制。 |
| **2026/08/12　【Git｜v1.0.0】** | **`8dac57c` —「增加DXF匯入功能」**。這是一個很大的產品版本分界：輸入不再主要依靠手動／CAD Bridge，而開始能直接從 DXF 批次建立工程模型。 |
| **2026/08/12–13** | 繼續處理 DXF 專案管理，包括 `dxf_import_state`、DXF 管理副本、重新連結、相對路徑及來源檔驗證。 |
| **2026/08/14　【Git｜v1.0.0】** | **`ce7b2ed` —「新增DXF匯出功能」**。資料流程從「匯入 DXF → Solver」延伸成「匯入 → 最佳化 → 再輸出 DXF」，開始形成完整的工程資料閉環。 |
| **2026/08/13–16** | 持續處理 DXF 匯出相容性、Audit／XRecord、Clean DXF 等問題，同時開始整理打包方式與給同事測試的執行版本。 |
| **2026/08/17　【Git｜v1.0.0】** | **`5851d43` —「介面小調整」**。功能趨於完整後，開始集中整理使用者操作介面。 |
| **2026/08/17　【Git｜v1.0.0】** | **`6dcfc6a` —「第一版介面定稿」**。可視為第一版產品介面的正式基準點。之後即使功能、架構仍持續修改，整體操作形式已大致確立。 |
| **2026/08 下旬** | 開發重心逐漸轉向專案儲存、材料管理、操作體驗、測試與程式架構整理。 |
| **2026/08/28–30 起** | 開始進行較系統性的 Architecture Review 與漸進式重構，包括 Domain、Application、Presentation、ProjectService、Input Builder、DI 等議題。 |
| **2026/09/02** | 將「支撐最佳化」投入資訊部活動／提案。 |
| **2026/09/04** | 副理提出至 680C 進行程式使用說明，開始進入實際發布準備。 |
| **2026/09/08–09** | 處理公司電腦 Defender／ASR 阻擋打包程式問題，經資訊部協助後解決執行限制。 |
| **2026/09/09–10** | 完成舊版操作文件、LSP 實機測試與第一版發布前準備。 |
| **2026/09/10【v1.0.0】** | **680C 第一版（v1.0.0）發布／使用說明。** |
| 2026/09/12【Git｜v1.0.0】 | b98aa33 —「第一版_架構調整版」。第一版發布後開始進行較正式的架構整理，逐步建立 domain / algorithms / application / infrastructure / presentation 等責任邊界。 |
| 2026/09/15【Git｜v1.0.0】 | 56b74cd —「第一版_waler背填、錯誤辨識」。第一版架構調整後繼續補強 Waler 與 DXF 辨識相關功能。 |
| 2026/09/17【Git｜v2.0.0】 | 0cfbb20 —「第二版_DXF介面調整」。DXF Import / Review 已由單純匯入功能逐漸發展成完整子系統，包含辨識、Review、人工修正、Validation、Preview 等流程。 |
| 2026/09/17 | 參與 Vibe Coding / AI Agent 開發工作流相關學習，開始系統性研究 SDD（Spec Driven Development）、AGENTS.md、Agent 工作規範、Skill 與 Context Engineering；開發方式開始由「直接要求 AI 改 Code」轉向「需求 → 分析 → 規格 → 設計 → 計畫 → 實作 → 驗證」。   AI Agent 工作流整理 |
| 2026/09/17–18 | 重新檢視 AGENTS.md 定位，逐條建立 AI 開發規則：修改前先理解現況、先提出方案、重大技術選擇由使用者確認、Clean Code、分層測試、文件修改需確認、Git 由使用者自行操作等。 |
| 2026/09/17–18 | 進行第二輪 Architecture Audit。不以檔案大小判斷技術債，而是重新繪製 System Architecture、Component、Dependency、DXF Data Flow、Solver Flow、Persistence Flow 等 As-Is 圖，辨識出 DXF Review workflow、main.py workflow、UI → Algorithms 等主要責任問題。 |
| 2026/09/18【Git｜v2.0.0】 | 8d1c218 —「第二版_架構調整」。依 Architecture Audit 逐步處理 UI / Application 邊界，重點不是重寫 Solver，而是把 workflow ownership 從 UI 收回適當層級。 |
| 2026/09/18 後 | Phase 1～4 架構整理完成後進行 Final Architecture Audit；結果判定已無 High architecture debt，當時 663 項測試中 662 通過、1 項因缺外部 fixture 跳過，因此停止繼續重構，轉入 SDD 文件建設。   AI Agent 工作流整理 |
| 2026/09 下旬 | 正式建立長期 SDD 文件體系：AGENTS.md 管 AI 工作方式；ARCHITECTURE.md 管責任與依賴；DOMAIN.md 管工程語意；SOLVER.md 管求解器；WORKFLOW.md 管 runtime 流程。DOMAIN.md 也開始明確區分 Engineering Hard Constraint、Solver Preference、Heuristic 與 Implementation Detail。   AI Agent 工作流整理 |
| 2026/09 下旬 | SOLVER.md 正式建立，開始把 Support Phase 1 / Phase 2、Waler Solver、Global Waler、Search Policy、Diagnostics 等由「存在於程式與對話裡的知識」轉為長期文件。   AI Agent 工作流整理 |
| 2026/09 下旬 | WORKFLOW.md 正式建立並精簡至 710 行，整理 Solver Result lifecycle、Manual Editing immediate commit、DXF/CAD/Persistence transaction boundary，以及 Confirmed Product Gaps / Technical Limitations。   AI Agent 工作流整理 |
| 2026/09 下旬 | 第一次正式以 SDD 規格方式處理 Geometry-based Support Adjacency；建立 836 行 Feature Spec，定義 Zoning、幾何相鄰、SharedLayoutGroup、Jack spacing 等工程語意，進一步從「AI 寫功能」轉向「先固定工程契約」。   AI Agent 工作流整理 |
| 2026/09/22 起 | 開始研究並導入 OpenSpec，將既有手工 SDD 流程接到 proposal → spec → design → tasks → apply → verify → archive；長期的 ARCHITECTURE / DOMAIN / SOLVER / WORKFLOW 不搬家，而是作為跨 capability reference documents。   AI Agent 工作流整理 |
| 2026/09/23 | OpenSpec 正式進入實際開發：完成／封存 Geometry-based Support Adjacency、Global Waler Auto Apply、Paused DXF Review Source Relink、Unsaved Changes Save Option 等 change。 |
| 2026/09/24 | OpenSpec 開發快速擴展至 DXF 與可靠性需求，包括 BIM Block Strut Recognition、BIM Strut Outline Topology、RC Waler 不參與最佳化、Solver 執行中禁止關閉、Support Editor no-op、Paused DXF Review recovery、Corner Brace centerline extension。 |
| 2026/09/25 | 延伸 BIM / DXF 辨識能力：BIM Brace Block Recognition、Brace Axis → Waler Extension、HATCH RC Waler Recognition、Waler-constrained BIM Strut Recognition。 |
| 2026/09/26 | 對 Brace → Waler extension 補上更嚴格範圍限制，開始呈現「先做 capability，再用後續 change 修正邊界」的 OpenSpec 演進方式。 |
| 2026/09/27 | 新增 Corner Brace Repair Tool、Contextual BIM Joist Recognition、BIM Strut Center Selection Repair 等 change；DXF 辨識已由一般幾何辨識逐漸延伸到 BIM 匯出圖面的特殊結構辨識。 |
| 2026/09/28【Git｜v2.0.0】 | 4d5e722 —「第二版_Y05匯入修正」。目前 GitHub 最新 commit。相較 9/18「第二版_架構調整」，這次一次整合大量 SDD/OpenSpec 成果、Y05 DXF/BIM 辨識修正、新 Domain/Application 元件與 regression tests；Git 中已可看到 19 個 archived OpenSpec changes。 |
| 2026/09/29 | 集中補強 DXF／BIM 辨識與 Review 操作：納入托梁與斜撐連接、圍令直接連接構件資料、中間柱歧義關聯修補及暫定雙路支撐候選；同時強化斜撐與角撐本體辨識，建立嚴格大於 250 mm 的寬度規則，並改善構件寬度顯示與角撐修補預覽。 |
| 2026/09/30 | 收斂 DXF Review 的幾何判定與人工修補流程：分離圍令側向證據與端點身分、要求斜撐兩端各自唯一連接不同圍令、加入圍令重疊診斷，並重整角撐遮蔽辨識契約；同步改善中間柱修補入口、問題識別文字及 Preview 錯誤構件點選。 |
| 2026/10/01 | 完成一輪核心契約整理：統一自動 Solver 與人工編輯使用的 Waler plan evaluation，集中 Support Shim／接頭驗證；正式移除舊 Strut 欄位正規化並定義 Project schema 相容政策。另新增手動 Project 的 result-only DXF 匯出、將 Material Spec 編輯移入 Application layer、支援斜切斜撐外框辨識，並全面校正 repository 文件。 |
| 2026/10/04 | 強化執行期可靠性與狀態一致性：建立 Project load、結果採用、CAD 與材料異動的 transaction 契約；CAD 更新會取消過期 Solver 並阻止 stale result 採用。Excel／DXF 匯出開始明確標示不合法成果，Solver 對空材料集合與無合法方案的處理亦完成對齊；同時移除確認無使用者的 DXF legacy functions 並修正文檔。 |
| 2026/10/05 | 修正圍令寬度為外側線的正交間距，避免斜端與端點錯位造成錯誤材料匹配；圍令調整時改以剛體平移同步更新斜撐兩端關係。打包方面將正式發行素材與 regression fixtures 分離，只以 allowlist 納入三份使用者 DXF 範例。 |
| 2026/10/06 | 擴充圍令求解與 DXF Review：Waler 支援 100／150／200／300 mm 尾端調整塊，Global Waler 可保留跨 stage 的完整合法候選池；新增 provisional Waler 的專用正式化流程，可由候選點或 CAD 工程線人工採用。另將 Review 診斷改為一致的繁體中文說明，並在不改變工程規則下加速來源排除與角撐修補規劃。 |
| 2026/10/07 | 完成主視窗與發行內容整理：移除頂部 Project toolbar，將專案操作集中至「檔案」選單並補上快捷鍵與儲存前編輯檢查；修正 Project 狀態誤改「檔案」選單的問題，並以藍灰色區分主、次頁籤。新增軟體資訊視窗，將 Y05／Y29 正式案例納入發行包。DXF Review 同步支援批次暫存來源排除，並以穩定來源身分修正 CornerBrace repair reference 對齊。 |

## AI 對話統計（截至 2026/09/28 早上）

1. **916 次 AI 對話回合**
2. 其中約 **656 次**明顯是在提問、請求分析、修改、檢查或實作
3. 約 **402 次**帶有明顯問句性質，例如「為什麼、怎麼、是否、是什麼、哪個、請問」等
4. 約 **118 次**是超過 1,000 字的長 Prompt
