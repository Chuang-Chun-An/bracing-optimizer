# Tasks

## 實作前閱讀

- **Task Group 1｜證據盤點**：先讀 `proposal.md`「現況與目標／In Scope」、`design.md` Decision 2～4；本 change 沒有 delta spec，main specs 只讀。
- **Task Group 2｜README 校準**：先讀 `design.md` Decision 1、3，以及 README 目前第 1～3、10、15、16 節。
- **Task Group 3｜長期文件一致性**：先讀 `design.md` Decision 2、4 與 Architecture Alignment；只讀直接相關的 `docs/*` 章節及 main spec。
- **Task Group 4｜驗證**：先讀 `design.md` Decision 5；若 diff 出現 code、tests、設定或 `openspec/specs/`，停止並恢復 scope，不以文件 change 夾帶行為修改。

## 1. 建立可追溯的文件校準清單

- [x] 1.1 以 `rg` 核對 README 中 `_migrate_strut_position_fields`、test-case UI／methods、`tools/upgrade_project_schema.py`、12 tests／1 failed 與 Waler 評分重複等已知 drift，並確認每項都能由目前 code、tests、main spec 或 archive 證明後再修改。
- [x] 1.2 對照 `main.py::_build_ui()`、Project persistence／schema tests、`evaluate_waler_plan()` callers 及 2026-10-01 archived changes，確認目前 UI、schema、Waler evaluator 與 1～7 行為的現況；驗證結果不得依 README 自己循環證明。
- [x] 1.3 將遇到的文字分類為現況、長期 truth 或歷史紀錄；無法由既有證據判定的規則停止修改並列入 review notes，CornerBrace normative 矛盾不得在本 change 中選邊。

## 2. 將 README 收斂為可維護的 repository 入口

- [x] 2.1 改寫 README 開頭與文件地圖，明確指出 README、`AGENTS.md`、四份 `docs/*`、main specs、active changes、archive 與 development history 的責任；驗證不再宣稱 README 是程式碼完整鏡像。
- [x] 2.2 對齊目前 Engineering／Materials／Analysis workspace、主要子頁籤、Project 與 Material Spec editing owner；搜尋確認 README 不再列出不存在的測試案例頁籤或其 methods。
- [x] 2.3 刪除或縮減逐函式索引、完整 call graph、固定行數／方法數等易漂移內容，只保留主要 entry points 與查找方式；以 `rg` 驗證所有保留的具名 symbol 在 repository 中存在。
- [x] 2.4 對齊 schema 3 compatibility、legacy normalization 移除、空白 Material Spec 的 `99` fallback、Support Shim、result-only DXF 與 Waler shared evaluator；逐項對照相關 main spec 或長期文件，且不得新增 requirement。
- [x] 2.5 重整「待重構／限制／測試」內容，移除已解決的 Waler duplicate、已刪除的離線升級及舊測試失敗快照；保留仍有 repository 證據的健康風險，測試章節只提供可重跑指令與驗證範圍。
- [x] 2.6 保留安裝、執行、打包、常用輸出與新開發者入口資訊，驗證所有命令、路徑及主要檔名在目前 repository 存在或由 `pyproject.toml`／正式設定支持。

## 3. 校準長期文件與歷史邊界

- [x] 3.1 檢查 `docs/ARCHITECTURE.md`、`docs/DOMAIN.md`、`docs/SOLVER.md`、`docs/WORKFLOW.md` 對本次七項既有行為的直接交叉引用；只有發現可證明的過時或錯誤敘述時才修改，並以對應 main spec／test 驗證。
- [x] 3.2 確認歷史內容留在 `docs/DEVELOPMENT_HISTORY.md` 與 archived changes；README 刪除的舊敘述若具有決策價值，必須先確認歷史來源已可追溯，不得改寫 archive 來配合現況。
- [x] 3.3 確認 `openspec/specs/` 沒有任何 diff，且 README 對 CornerBrace repair 只提供中性入口或連結；若需要改 normative wording，停止並另立使用者決策 change。
- [x] 3.4 檢查 README 與四份長期文件的互相引用，驗證相對路徑、章節名稱、module 路徑及 archive links 都能解析至現存目標。

## 4. 文件 regression 與 OpenSpec 驗證

- [x] 4.1 執行 stale-reference 搜尋，確認現況文件不再把 `_migrate_strut_position_fields`、test-case UI、upgrade tool、12 tests／1 failed 或重複 Waler 評分列為目前行為；歷史來源中的命中需明確判定為合理保留。
- [x] 4.2 執行 Markdown path／link 與保留 symbol 檢查，確認 README 導向的文件、設定、entry point 與指令均存在；記錄任何刻意保留但無法自動驗證的外部條件。
- [x] 4.3 執行 `openspec validate --all --strict`，確認本 change 的 `skip_specs: true`、proposal、design、tasks 與現有 main specs 全部通過。
- [x] 4.4 執行 `git diff --check` 並審查 `git diff --name-only`，確認只有 `README.md`、必要的四份長期文件及本 change artifacts 有變更，沒有 code、tests、設定、資料檔或 `openspec/specs/` diff。
- [x] 4.5 依 `proposal.md` In Scope／Out of Scope 與 `design.md` Decisions 完成最終文件 regression review，確認每項已知 drift 已修正、歷史可追溯、未決 Domain／Workflow 問題未被猜測後，再進行 OpenSpec implementation verification。
