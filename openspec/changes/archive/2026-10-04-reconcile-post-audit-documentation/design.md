# Design

## 閱讀導航

- **現在必讀（P0）**：Decision 1 的 source-of-truth 分工，以及 Decision 2～4 的四組校正內容。
- **實作前閱讀（P1）**：proposal.md、MODIFIED delta 與 tasks.md；本 change 只修正規格文字，不改 runtime behavior，也不直接編輯主規格。
- **條件式閱讀（P2）**：校正 CornerBrace 時讀已 archive change 與現行 implementation/tests；校正 Shim 時讀現行 Support validator。
- **可先跳過**：所有不在 proposal 列出的文件與程式模組。

## 方案摘要

以已驗證的 implementation、tests 與已成立 OpenSpec 為證據，逐項校正四個文件漂移：CornerBrace repair 描述、README Qty 說明、SOLVER Shim validation 表格、AGENTS dependency code fence。CornerBrace 採 MODIFIED delta，之後由 archive 合併主規格；只修正文字與格式，不補新 runtime 需求、不更動 code。

## 決策對照

| Decision | 對應 proposal 範圍 | 對應 task |
| --- | --- | --- |
| D1. 每類資訊只由專責文件定義細節 | 全部文件一致性 | 1.1 |
| D2. CornerBrace 使用 MODIFIED delta，不直接改主規格 | CornerBrace template／relationship 描述 | 2.1、2.2 |
| D3. Qty 與 Shim 只描述目前成立行為 | README Qty、SOLVER Shim | 2.3、2.4 |
| D4. AGENTS 只修 Markdown 邊界 | dependency fence | 2.5 |

## Context

health check 發現少量長期文件與現行 specs／tests 不一致。這些差異會讓後續維護者把 overview、workflow 或表格誤認為另一套規則，但尚無證據顯示 runtime 應改成舊文件所述。

## 已確認 evidence baseline

| 項目 | 觀察到的漂移 | Authoritative evidence | 目標校正與 owner |
| --- | --- | --- | --- |
| CornerBrace | 主規格「參考角撐必須分級並阻止推測鏈」把每個 repair candidate 都寫成必須有 automatic-primary template；provenance／Pause-Resume 段落也以 selected template 為全稱前提。`docs/WORKFLOW.md` 只摘要 template transfer。 | Archive `2026-09-30-redesign-corner-brace-occlusion-recognition` 的 D7 與 delta spec 明定 `body_relationship_selection` 不需 template；`dxf_import/corner_brace_repair.py` 會建立 `template_reference=None` 的 relationship candidates；`dxf_import/source_exclusion.py` 依 `selection_mode` 分流 replay；`tests/test_dxf_corner_brace_repair.py::CornerBraceRepairPersistenceTests::test_relationship_selection_provenance_round_trips_without_template` 驗證無 template provenance。 | 以 MODIFIED delta 把 template-only 文字限縮到 `reference_template`，並補齊 body mode 已成立的 provenance／replay scenario；主規格只在 archive 時由 OpenSpec 合併。WORKFLOW 只保留兩模式摘要與主規格連結。 |
| Qty | README 7.3 把 Material Spec、Inventory Qty、預設 inventory 的每列 99 根、空白 Material Spec 的 99 根 fallback 與「現行採購／庫存評分」混成同一組通則，容易被讀成 Support／Waler 都已依 Qty 評分。 | `data/inventory.json` 的預設 rows 目前每列 `Qty = 99` 且使用者可修改；`InventoryLookup.stock_items()` 對空白 Material Spec 另依 Usage 料長建立每種 99 根 fallback。`docs/DOMAIN.md`／`docs/SOLVER.md` Gap 1 明定 Support Qty／purchase 尚未進 score；`WalerPlanEditing` 依 Qty 顯示「庫存不足（會以購買數計入分數）」警告。 | README 分開寫「預設資料可編輯的 Qty 99」、「空白規格的暫時 fallback」、「Waler 自動／人工 Qty 評分與警告」及「Support known gap」。 |
| Shim | `docs/SOLVER.md` 分類表把 RC／Steel Shim placement 的 Current Rule 寫成「自動生成階段保證」，弱化完整 evaluation 與人工編輯也必須通過的共用 legality contract。 | `bracing_optimizer/algorithms/support.py:1692` 的 `validate_support_layout()` 檢查 Jack count／600 mm、Shim count／100、150、200、300 mm、placement、gap、forbidden joint 與 Steel length；`evaluate_single_support()` 與 `bracing_optimizer/application/plan_editing.py:244` 共用 verdict。`2026-10-01-align-support-shim-joint-validation` 與 `2026-10-04-align-solver-validation-contracts` 均已 archive，後者已把 size issues 納入正式 verdict。 | 只修正 SOLVER classification table 的 Current Rule，指向候選生成預防及自動完整 evaluation／人工編輯共用 validator；不重寫既有 4.3／4.4。 |
| AGENTS | `AGENTS.md` dependency diagram 只有 opening fence，後續規則會被 Markdown renderer 視為 code block。 | 檔案目前只有一個以 ` ``` ` 開頭的 fence；diagram 後緊接 dependency 規則。 | AGENTS 擁有 agent policy；只在 diagram 後補 closing fence，不改 policy 文字。 |

## Goals / Non-Goals

**Goals:**

- 移除可被誤解為 active rule 的舊敘述。
- 保留 overview 與詳細 spec 之間合理的摘要重複。
- 修復 AGENTS Markdown fence，避免後續規則渲染錯誤。

**Non-Goals:**

- 不重新設計文件架構或大幅重寫歷史。
- 不修改 code、tests、runtime behavior 或未列入 proposal 的 wording。
- 不把其他 active changes 的未實作行為提前寫成現在事實。

## Architecture Alignment

本 change 不修改 Architecture。它恢復既有 source-of-truth 分工：README 是入口；WORKFLOW 描述 runtime 流程；SOLVER 描述現行 solver；OpenSpec main specs 定義精確行為；AGENTS 定義 agent 工作與 layer guardrails。

### 受影響 layer 與依賴方向

- Runtime 的 Presentation、Application、Domain、Algorithms、Infrastructure 均不受影響，也不新增 dependency。
- 文件校正只引用既有方向：CornerBrace Presentation／Workflow 消費 recognition 與 repair evidence；Support 人工編輯透過 Application 呼叫 Algorithms 的共用 validator；README 不成為第二份 Solver 規則。
- 若套用時需要修改 code、test expectation、Project schema 或 layer dependency，表示 evidence baseline 已失效，必須停止並重新評估 change，而不是擴張 scope。

## Decisions

### Decision 1: 先建立 evidence table，再逐句修改

每個差異記錄「舊敘述、authoritative evidence、目標敘述、受影響連結」。沒有 implementation/test/spec 證據的內容不改。這避免以本次 audit 的推論創造新 domain rule。

### Decision 2: CornerBrace 使用 MODIFIED delta，由 archive 合併主規格

本 change 移除 `skip_specs`，以 `dxf-corner-brace-repair-tool` MODIFIED delta 記錄文字校正。Proposal 明確標示「只修正規格文字，runtime 行為不變」。實作階段不得直接編輯 main spec；完成並驗證後由 OpenSpec archive 將 delta 合併到主規格，並把本次校正保留在 archive history。

| 面向 | 採用 MODIFIED delta 的影響 |
| --- | --- |
| Validation | Change strict validation 會要求 delta 存在，並檢查 MODIFIED Requirement 標題、完整內容與 scenarios；另以主規格 strict validation確認現行基線有效。 |
| Archive | Archive 依標準流程把 delta 合併到 main spec；apply 階段不直接改主規格。 |
| 歷史追溯 | Archive 保留本次 requirement 文字差異及其 proposal／design／tasks，可追溯性高於只靠直接編輯與 Git diff。 |

本次只修改下列 Requirement：

| Requirement | 修改類型 | 限定內容 |
| --- | --- | --- |
| `參考角撐必須分級並阻止推測鏈` | 限縮適用範圍 | 「每個 repair candidate 都需 automatic-primary template」只適用 `reference_template`；reference 分級、compatibility gates 與 secondary chain 禁止規則不變。 |
| `修補決策必須可追溯且安全重播` | 限縮適用範圍並補充 scenario | template identity、local transfer 與 template replay 只適用 `reference_template`；補充 `body_relationship_selection` 以 body signature、target identities 與 adopted line 保存及安全重播的既有語意。 |

`每個修補候選必須具有有效的目標工程接點` 已正確定義 body mode 不需 template，不修改。WORKFLOW 只摘要兩種流程並連到主規格，不複製 acceptance details。

### Decision 3: README／SOLVER 描述現況，不預告其他 change

README Qty 段落分開描述：預設 inventory 資料每列 Qty 為 99 且可由使用者修改；空白 Material Spec 依 Usage 料長建立每種 99 根的暫時 fallback；Waler 自動與人工評估使用 Qty，人工編輯在需求超過 Qty 時顯示採購警告；Support Qty／purchase 仍是 known gap。

SOLVER Shim classification table 只寫入目前 `validate_support_layout()` 已成立的正式 verdict：Jack 數量與 `600 mm`、Shim 數量與 `100／150／200／300 mm`、Shim placement、`0～150 mm` gap、forbidden joint 及 Steel purchasable length。候選生成先避免已知錯誤 layout，自動完整 evaluation 與人工 `SupportPlanEditing` 共用此 validator。本 change 不重寫 4.3／4.4，也不寫入尚未實作的行為。

#### 關聯 change 與重疊

- `2026-10-01-align-support-shim-joint-validation` 已 archive 且 tasks 全數完成；它建立 Shim count／placement、RC terminal exception 與 automatic／manual 共用 validator，並更新 SOLVER manual editing／Gap 4。
- `2026-10-04-align-solver-validation-contracts` 已 archive 且 tasks 全數完成；它在上述 contract 加入 Jack／Shim size issues 與完整 priority，並更新 SOLVER 4.3／4.4。
- 兩者與本 change 同屬 `docs/SOLVER.md` Support validation 主題，但本 change 只處理 classification table 殘留的「自動生成階段保證」措辭，沒有 line-level 重寫 4.3／4.4。順序固定為以 2026-10-04 archive 後現況作基線，再套用本次單列校正。

### Decision 4: AGENTS 僅閉合 fence

在 dependency diagram 後正確閉合 Markdown code fence，使後續章節正常渲染；不趁機改 agent policy。

## Rejected Alternatives

- **維持 `skip_specs: true` 並直接改主規格**：未採用；雖可由 change artifacts 與 Git diff 追溯，但 archive 不會保存 MODIFIED delta，且主規格修改不經標準合併流程。使用者選擇以 delta 提高 spec 歷史可追溯性。
- **保留主規格舊全稱文字，只在 WORKFLOW 加註例外**：拒絕；精確 main spec 內部仍會自相矛盾，且會形成兩份 behavior truth。
- **把 Support Qty known gap 寫成即將實作**：拒絕；本 change 沒有 Solver 行為授權，也不得預告其他 active change。
- **順便重排 AGENTS 或全面統一文件措辭**：拒絕；會超出已定位的 Markdown 邊界與四項漂移。

## Source of Truth

- 精確 CornerBrace behavior：active main spec + tests + code。
- Runtime workflow：docs/WORKFLOW.md。
- Solver current mechanics：docs/SOLVER.md。
- Repository entry summary：README.md。
- Agent rules：AGENTS.md。

## Backward Compatibility / Persistence

無 runtime、API、persistence 或 migration 影響。所有改動皆為文件校正。

## Risks / Trade-offs

- [把未實作 change 寫成現況] → 每句以目前 main spec／test／code 驗證，active proposal 只能作未來參考。
- [overview 太詳細形成第二 truth] → README／WORKFLOW 保留摘要並連到精確 spec。
- [純文字 delta 被誤讀為 runtime 行為變更] → Proposal 明記 runtime 不變；delta 只限縮 template-only 全稱並補已實作 scenario，驗證時比對 code／tests 與 archive decision。

## Migration Plan

先以 MODIFIED delta 鎖定主規格的預期文字，再套用 WORKFLOW、README、SOLVER 與 AGENTS 文件校正。Apply 階段不直接改主規格；archive 時才合併 delta。若任一敘述找不到一致 evidence，停止並在 change verification 中回報，不自行猜測。

## Open Questions

無。主規格修改方式已由使用者選定為 MODIFIED delta。若 apply 前 code、tests 或 main spec 已改變，使上述 evidence 不再一致，必須先停止並更新本 change。
