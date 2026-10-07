# Proposal

## 閱讀導航

- **P0 現在必讀**：本 proposal 的前五節；本 change 的 `dxf-corner-brace-repair-tool` MODIFIED delta；主規格中 template 與 `body_relationship_selection` 相關 Requirements。
- **P1 實作前閱讀**：`design.md` 的決策來源對照與文件修改清單；README 材料政策摘要、`docs/SOLVER.md` Support validation 表格、`AGENTS.md` dependency fence。
- **P2 需要時再讀**：`2026-09-30-redesign-corner-brace-occlusion-recognition` archive design 的兩種 repair mode 決策。
- **可以先跳過**：recognition implementation、Solver 搜尋細節、Project persistence 及所有不在修改清單內的主 specs。

## 快速摘要

- CornerBrace 主規格與 WORKFLOW 仍有「所有 repair 都需 template」的舊全稱文字，但已批准的 body relationship 模式明確不需 template；本 change 以 MODIFIED delta 記錄校正，不直接編輯主規格。
- 本 change 所稱兩種 repair mode，分別是以參考角撐移植局部配置的 `reference_template`，以及沿用已辨識本體、只由使用者選擇工程關係的 `body_relationship_selection`。
- README 的 Inventory Qty 摘要容易讓人誤以為 Support 與 Waler 都已依數量評分。
- SOLVER 表格仍把 Shim placement 寫成只由自動生成保證，與現行共用 validator 不一致。
- 修復 `AGENTS.md` 未閉合 code fence；不改任何產品、Domain 或 implementation 行為。

## 現況與目標

| | Before | After |
| --- | --- | --- |
| CornerBrace repair | template 舊通則與兩模式新規則同時存在 | template 規則只適用 `reference_template`，body 模式有獨立保存／replay 語意 |
| Qty 摘要 | 容易概括成兩 Solver 均參與評分 | 明確區分 Waler 現況與 Support known gap |
| Shim 表格 | 寫成自動生成保證 | 指向自動／人工共用 validator |
| AGENTS 呈現 | 後半部落在未閉合 code block | Markdown 結構正常 |

## 主要流程

1. 以已 archive 的批准決策、現行 code 與 tests 建立逐條文件對照。
2. 以 MODIFIED delta 限縮 CornerBrace 舊全稱 requirement，不直接編輯主規格，也不新增或刪除 repair mode。
3. 修正 README、SOLVER 與 AGENTS 的已知措辭／格式問題。
4. 執行連結、Markdown fence 與 OpenSpec strict validation。

## 不變事項

- 不修改 code、tests、工程規則、Solver 行為或 UI。
- CornerBrace 只修正規格文字，runtime 行為不變；主規格由後續 OpenSpec archive 合併 delta，本 change 實作階段不直接編輯主規格。
- 不刪除 archive；archive 只作追溯證據，不升格為現行 source of truth。
- 不把無呼叫 legacy functions 的移除納入本 change。
- 不重新整理整套文件架構或重寫最近完成的 README。

## Why

第二輪健檢確認少數舊文字在多次改版後仍與已批准、已實作且有測試的現況衝突。這些衝突會讓接手者選錯 source of truth，但不需要重新做產品決策。

## What Changes

- 新增 `dxf-corner-brace-repair-tool` MODIFIED delta，限縮 template requirement、provenance 與 replay 全稱文字，明確分開兩種 mode；只修正規格文字，runtime 行為不變。
- 更新 `docs/WORKFLOW.md`，同時描述 reference-template 與 body-relationship repair。
- 修正 README Qty 摘要，明確指出 Support Qty／purchase 尚未進入 score。
- 修正 `docs/SOLVER.md` Shim placement 表格，使其符合共用 validator 現況。
- 關閉 `AGENTS.md` dependency code fence，恢復後續章節格式。

### In Scope

- 上述精確文件位置與必要交叉引用。

### Out of Scope

- 任何行為修改、直接編輯主規格、legacy code 刪除、架構重整或其他文件的全面編修。

## Capabilities

### New Capabilities

- 無；本 change 不新增行為規格。

### Modified Capabilities

- `dxf-corner-brace-repair-tool`：以 MODIFIED delta 修正「參考角撐必須分級並阻止推測鏈」及「修補決策必須可追溯且安全重播」中的 template-only 全稱文字，並補充 `body_relationship_selection` 已成立的無-template provenance／replay scenario。只修正規格文字，runtime 行為不變。

## Impact

- 規劃階段新增本 change 的 `dxf-corner-brace-repair-tool` delta；套用階段僅影響 `docs/WORKFLOW.md`、README、`docs/SOLVER.md` 與 `AGENTS.md`，不直接修改 `openspec/specs/dxf-corner-brace-repair-tool/spec.md`。
- Architecture、Domain、Solver、Workflow runtime truth 不改變；文件會重新與現況一致。

