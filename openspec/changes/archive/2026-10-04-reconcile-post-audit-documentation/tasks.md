# Tasks

## 實作前閱讀

- 第 1 組先讀 proposal 全文、MODIFIED delta 與 design Decision 1～2，確認本 change 只修正規格文字、runtime behavior 不變，且 apply 階段不得直接修改 main spec。
- 第 2 組開始前依項目閱讀 design Decision 2～4、對應現行 main spec、code 與 tests；沒有 evidence 的文字不得改，也不得重寫已由相關 archive 完成的 SOLVER 4.3／4.4。
- 第 3 組只做一致性、Markdown 與 OpenSpec 驗證，不順便整理其他文件。

## 1. 建立校正 evidence

- [x] 1.1 重新核對 `design.md` 的「已確認 evidence baseline」仍符合現行 code、tests、main specs；若任一 evidence 已改變則停止套用並回報，不在本 task 內改寫 behavior。

## 2. 套用限定文件校正

- [x] 2.1 以本 change 的 `dxf-corner-brace-repair-tool` MODIFIED delta 作為唯一主規格修改來源，確認其完整包含「參考角撐必須分級並阻止推測鏈」及「修補決策必須可追溯且安全重播」兩個 Requirement，只限縮 template-only 全稱並補已實作的 body-mode provenance／replay scenarios；apply 階段不得直接編輯 main spec，完成後執行 change strict validation。
- [x] 2.2 更新 docs/WORKFLOW.md 的 CornerBrace repair 摘要與 main spec 連結，驗證 overview 沒有複製另一套 acceptance rules，也沒有把 archive 當 active requirement。
- [x] 2.3 更新 `README.md` Qty 摘要並分開描述：預設 `data/inventory.json` 每列 Qty 為 99 且可由使用者修改；空白 Material Spec 依 Usage 料長建立每種 99 根暫時 fallback；Waler 自動與人工評估使用 Qty，人工編輯在需求超過 Qty 時顯示「庫存不足（會以購買數計入分數）」；Support 目前只使用 purchasable lengths 且 Qty／purchase 尚未進 score。以文件搜尋核對 `docs/DOMAIN.md`／`docs/SOLVER.md` 無矛盾敘述。
- [x] 2.4 只更新 `docs/SOLVER.md` Shim classification table 的 Current Rule，說明候選生成先避免已知錯誤 layout，而 `validate_support_layout()` 已正式檢查 Jack count／600 mm、Shim count／100、150、200、300 mm、placement、gap、forbidden joint 與 Steel length，並由自動完整 evaluation 與人工 `SupportPlanEditing` 共用；不得重寫 4.3／4.4。以 `tests/test_support_waler_type_rules.py` 與 `tests/test_plan_editing.py` 驗證尺寸與 placement 語意不變。
- [x] 2.5 在 `AGENTS.md` dependency diagram 後補 closing Markdown fence，以 fence count／render inspection 驗證後續章節不再落在 code block，並以 diff 確認 policy 文字未變。

## 3. 整體驗證

- [x] 3.1 執行 `tests/test_dxf_corner_brace_repair.py`、`tests/test_support_waler_type_rules.py` 與 `tests/test_plan_editing.py` 的 targeted tests，確認文件敘述仍有現行測試證據且沒有 runtime 修改。
- [x] 3.2 執行 `openspec validate reconcile-post-audit-documentation --strict`，並驗證受影響的 `dxf-corner-brace-repair-tool` 主規格基線；若額外執行 `openspec validate --all --strict`，必須按 item／path 區分失敗是否由本 change 造成，不得把其他 active change、archive 或既有主規格問題歸因於本 change。
- [x] 3.3 依 `$openspec-verify-change` workflow 對照 proposal、delta spec、design 與本 tasks 清單，逐項確認沒有修改程式、測試 expectation、主規格本身或未列入 proposal 的文件內容，且 delta 只修正規格文字、runtime 行為不變。
