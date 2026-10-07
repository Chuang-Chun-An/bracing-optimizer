# Tasks

## 實作前閱讀

- **Group 1 前**：讀 `proposal.md` 的 In Scope／Out of Scope、`design.md` Decision 1～2，以及 `software-information-presentation` 的「顯示可辨識的軟體身分」、「完整顯示起始歷史紀錄」。
- **Group 2 前**：讀 `design.md` Decision 3，以及 spec 的「資源異常時保留基本資訊」。
- **Group 3 前**：讀 `design.md` Decision 5，以及 spec 的「可從主視窗開啟軟體資訊」、「資訊視窗不得修改 Project」。
- **Group 4 前**：讀 `design.md` Decision 4、`release-package-assets` delta，以及既有 main spec 的「正式發行包提供三份 DXF 使用者素材」。
- **Group 5 前**：回讀全部 requirements 與 proposal 的「不變事項」，確認沒有把 Project、DXF、Solver 或完整工程 archive 納入實作。

## 1. 建立產品身分與歷程資料 contract

- [x] 1.1 在 `bracing_optimizer/product_metadata.py` 建立 immutable `ProductIdentity` 與單一 runtime identity（`SupportOptimizer`、`3.0.0`、`莊竣安（Chuang Chun An）`），並以 `tests/test_software_information.py` 驗證三欄為指定值且沒有引用 Project／DXF／Solver version。
- [x] 1.2 在 `bracing_optimizer/application/software_information.py` 建立 immutable `SoftwareHistoryEntry`、`SoftwareHistoryLoadResult`、`SoftwareInformation`，並以單元測試驗證 available 與 unavailable 組合都能保留 `ProductIdentity`。
- [x] 1.3 建立 `assets/software_history.json` 的 `schema_version: 1`、固定 `source_heading` 與起始歷史 entries；在 `tests/test_software_information.py` 解析 `docs/DEVELOPMENT_HISTORY.md` 的起始歷史表格，逐筆驗證 JSON 的 `date_label`、`record` 與原始順序完全相同，且 resource 不含「Codex／OpenSpec 封存紀錄」、「人工補充紀錄」或「AI 對話統計」區段。
- [x] 1.4 在 metadata test 以 `tomllib` 比對 `pyproject.toml [project].version` 與 runtime identity version，執行 `.\.venv\Scripts\python.exe -m unittest tests.test_software_information` 確認一致性失敗會被測試攔截。

## 2. 實作歷程 resource loader 與 fallback

- [x] 2.1 在 `bracing_optimizer/infrastructure/software_history.py` 實作 UTF-8 JSON 讀取、`schema_version`／`source_heading`／entry validation 與原序保留；新增 temporary-file tests 驗證非 ISO 的日期文字不被轉換，entries 不被重新排序。
- [x] 2.2 將 missing file、I/O error、malformed JSON、未知 schema 與無效 entry 收斂為 `available=False` 及固定可理解訊息，同時保留 logger 診斷；測試驗證不拋出 raw exception 且不丟失產品身分。
- [x] 2.3 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_software_information`，確認正常載入、逐筆 parity、原序保留與所有 fallback cases 通過。

## 3. 新增唯讀資訊視窗與主視窗入口

- [x] 3.1 在 `bracing_optimizer/presentation/dialogs/software_information_dialog.py` 實作 modal `Toplevel`：以 labels 顯示身分、disabled `ScrolledText` 依原序顯示全部起始歷史／fallback、提供關閉按鈕與 Escape；新增 Presentation tests 驗證標題、作者 `莊竣安（Chuang Chun An）`、唯讀 state、scrollable history、首末筆內容與 close behavior。
- [x] 3.2 從 `bracing_optimizer.presentation` 公開 dialog，並在 `main.py` 新增 `_show_software_information()`：使用 `RESOURCE_DIR/assets/software_history.json` 載入資訊後開啟 dialog；以 mocked loader／dialog test 驗證 source resource path 與 unavailable result 都能開窗。
- [x] 3.3 在 `_build_project_menu_and_toolbar()` 增加永遠可用的「說明 → 軟體資訊」，保持 `file_menu` 與 `_update_project_action_states()` 原樣；測試驗證沒有 Project selection 仍可呼叫、乾淨與 dirty Project 的 path／dirty state／dirty reason 在開關視窗前後完全相同。
- [x] 3.4 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_software_information tests.test_interface_presentation tests.test_main_project_editing`，確認資訊 UI 行為與既有主視窗互動通過。

## 4. 納入正式封裝並更新使用說明

- [x] 4.1 在 `SupportSolver.spec` 的 `datas` 精確加入 `assets/software_history.json`，擴充 `tests/test_dxf_assets.py` 驗證該檔被 allowlist、完整 `docs/DEVELOPMENT_HISTORY.md`／其他 docs 未被封裝，且既有 Project／fixture／`copytree` 禁止 assertions 仍成立；執行 `tests.test_dxf_assets`。
- [x] 4.2 更新 `README.md` 的正式發行資源與軟體資訊入口說明，但不修改 `docs/ARCHITECTURE.md`、`docs/DOMAIN.md`、`docs/SOLVER.md` 或 `docs/WORKFLOW.md`；以文字搜尋確認 README 只宣告起始歷史紀錄投影，不宣稱完整 `DEVELOPMENT_HISTORY.md` 會被封裝。
- [x] 4.3 使用 `SupportSolver.spec` 建立 onedir，從不含 repository 且斷網的成品手動驗證「說明 → 軟體資訊」能顯示名稱、`3.0.0`、`莊竣安（Chuang Chun An）` 與按文件原序排列的完整起始歷史，且不顯示其他三個區段；暫時移除成品中的 history resource 後驗證 fallback 且主程式／Project 不受影響，再重建乾淨成品。

## 5. 最終驗證與 review

- [x] 5.1 執行 architecture／package boundaries：`.\.venv\Scripts\python.exe -m unittest tests.test_application_domain_boundaries tests.test_package_layout tests.test_app_dependencies`，確認沒有 Presentation／Infrastructure 反向依賴或不必要的 Project dependency。
- [x] 5.2 執行完整回歸 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`，記錄 passed／failed／skipped；不得刪除測試、降低 assertion 或新增 skip 來通過。
- [x] 5.3 逐項對照兩份 delta specs 與本 tasks，執行 OpenSpec implementation verification，確認 Help menu、指定作者、起始歷史逐筆一致性／原序／區段排除、fallback、no-Project-state-change 與 release allowlist 都有實作及證據；若發現 Spec／Design 與 code 衝突，停止並回報，不自行改需求。
- [x] 5.4 執行 `openspec validate add-software-information-dialog --type change --strict`，確認所有 artifacts 與 delta specs 嚴格驗證通過，並回報 package 手動驗證結果與任何已知限制。
