# Design：Repository 文件真相來源校準

## 閱讀導航

### 現在必須理解

1. **Decision 1：README 是入口地圖，不是程式符號鏡像**——決定主要刪修方向，對應 Tasks 1、2。
2. **Decision 2：依資訊類型選擇證據來源**——避免用 code 反向改寫未確認的 Domain rule，對應 Tasks 2、3。
3. **Decision 3：現況與歷史分流**——決定哪些內容刪除、改寫或保留，對應 Tasks 2、3。
4. **Decision 4：Normative spec freeze**——本 change 不修改 main specs，對應 Tasks 3、4。

### 遇到特定情況再讀

- 修改 `docs/ARCHITECTURE.md` 時讀「Architecture Alignment」。
- 遇到舊專案、舊欄位或舊工具說明時讀「Backward Compatibility 與 Persistence」。
- 無法判斷文字是歷史紀錄還是現行要求時讀「Risks / Trade-offs」。
- CornerBrace repair 文字互相衝突時停止；該產品決策不屬於本 change。

## 方案摘要

```text
README（入口與導航）
   ├─ Architecture truth → docs/ARCHITECTURE.md
   ├─ Domain truth       → docs/DOMAIN.md
   ├─ Solver truth       → docs/SOLVER.md
   ├─ Workflow truth     → docs/WORKFLOW.md
   ├─ Precise behavior   → openspec/specs/
   └─ Historical record  → docs/DEVELOPMENT_HISTORY.md + archive/
```

實作時先把 README 的陳述依上圖分類，再更新可由既有證據直接判定的現況。容易隨函式增刪而失效的逐符號清單、固定行數、固定測試數與歷史失敗快照不再由 README 手工維護。

## 決策對照

| Decision | 影響範圍 | 對應工作 | 不影響 |
|---|---|---|---|
| 1. README 收斂為入口地圖 | README 結構、函式索引、call graph、快速上手 | Tasks 1.1～2.4 | 程式 module 及 public API |
| 2. 依資訊類型選證據 | 所有被校正的現況敘述 | Tasks 2.2、3.1～3.3 | 已成立 main spec requirement |
| 3. 現況／歷史分流 | 測試快照、舊 UI、legacy migration、技術債清單 | Tasks 2.3～3.2 | `DEVELOPMENT_HISTORY.md` 與 archive 的可追溯性 |
| 4. Normative spec freeze | `openspec/specs/`、CornerBrace 矛盾 | Tasks 3.3、4.3 | Domain、Solver、Workflow observable behavior |
| 5. 文件專用驗證 | link、symbol、OpenSpec、diff | Tasks 4.1～4.4 | 測試 assertion 與 production artifacts |

## 名詞

- **入口地圖**：讓接手者知道系統做什麼、先讀什麼及到哪裡找正式答案；不嘗試列出所有函式。
- **長期真相**：目前已成立且跨單次 change 持續有效的 Architecture、Domain、Solver 或 Workflow 說明。
- **Normative spec**：`openspec/specs/` 中以 SHALL／MUST 與 scenarios 定義的精確行為。
- **歷史紀錄**：已完成 change 的動機、方案與驗證結果；可供追溯，但不覆蓋目前 main spec 與長期文件。

## Context

詳見 `proposal.md` 的 Why。目前 README 超過 2500 行，包含完整函式索引、call graph、行數、方法數、過去測試結果及待重構建議。這些內容在多次架構調整後產生下列已確認 drift：

- `_migrate_strut_position_fields()`、測試案例 UI 與相關方法已不存在，README 仍列為現況。
- UI 已改成 Engineering／Materials／Analysis workspace，README 仍描述八個平行 tabs。
- Project schema 已移除 legacy Strut position normalization 與離線升級工具，README 仍要求舊專案先升級。
- Waler 自動與人工方案已共用 `evaluate_waler_plan()`，README 仍把評分重複列為技術債。
- README 仍把 2026-07-30 的 12 tests／1 failed 與 UCS 說明呈現為目前測試狀態。

長期文件已建立明確分工，因此不需要新增文件系統或工具。本 change 的設計重點是減少 README 與既有 truth sources 的重複維護面。

## Goals / Non-Goals

**Goals:**

- 讓新接手者從 README 能找到目前正確的系統入口與正式文件。
- 移除已確認失效的符號、workflow、測試快照與已解決技術債。
- 保留足以操作、執行、驗證與定位主要模組的資訊。
- 讓本次 1～7 的已成立結果在 README 與長期文件中互相一致。
- 讓後續文件更新只需修改真正擁有該資訊的文件。

**Non-Goals:**

- 建立自動文件生成器或 API reference 工具。
- 全面重寫所有 DXF capability 說明。
- 刪除仍成立的技術債，只因它們看起來負面或陳舊。
- 根據目前 code 猜測未確認的產品或工程規則。
- 修改 main specs、tests 或任何 production source。

## Decisions

### Decision 1：README 維護穩定入口，不維護完整 symbol inventory

README 保留：產品目的、主要功能、架構高階圖、文件地圖、安裝／執行、主要 workflow 入口、資料格式導覽、驗證指令及重要限制。逐函式索引、完整 call graph、固定程式行數、固定方法數及可由 `rg`／IDE 直接取得的資訊予以移除或縮成主要 entry points。

理由：手寫 symbol inventory 在每次 rename、move 或 method extraction 後都會形成第二份 truth，且目前 drift 已證明維護成本高於導覽價值。

Rejected alternatives：

- **逐項更新所有函式名稱**：短期看似完整，但下一次重構會再次過期。
- **本次新增自動 API 文件生成**：引入新 tooling 與維護流程，超出純文件校準範圍。
- **把 README 只留三行連結**：會失去安裝、產品概覽及常用入口的實用價值。

### Decision 2：依資訊類型選擇 single source of truth

| 資訊類型 | 主要 truth | 輔助證據 |
|---|---|---|
| Agent 工作方式 | `AGENTS.md` | 無 |
| Architecture responsibility／dependency | `docs/ARCHITECTURE.md` | imports、boundary tests |
| Domain rule | `docs/DOMAIN.md` + 已成立 main spec | tests、implementation |
| Solver policy／scoring／search | `docs/SOLVER.md` + 已成立 main spec | algorithms、regression tests |
| Runtime workflow／state lifecycle | `docs/WORKFLOW.md` + 已成立 main spec | Application／Infrastructure tests |
| 精確 observable behavior | `openspec/specs/` | tests、implementation |
| 目前 UI／module entry | 實際程式 | presentation tests |
| 歷史決策 | `docs/DEVELOPMENT_HISTORY.md` + archived change | Git history |

若 Domain／Workflow 文件與 main spec 矛盾，不以 code 自行選邊；停止該項修改並列為待澄清。若只是 README 的 symbol 或 UI 結構過期，則以目前程式與測試校正。

### Decision 3：歷史資訊保留在歷史來源，README 只陳述現況

早期測試數量、舊失敗原因、已刪除 UI、已完成的 migration 方案及已解決技術債不留在 README 的現況章節。若具追溯價值，確認它已存在於 `DEVELOPMENT_HISTORY.md` 或 archive；本 change 不搬移或重寫 archive。

仍成立的限制與技術債可以保留，但必須有目前 repository 證據，且不使用容易過期的行數或測試數作為核心描述。

### Decision 4：本 change 不修改 normative specs

`.openspec.yaml` 設定 `skip_specs: true`。實作期間不得修改 `openspec/specs/`，也不得把目前 implementation 行為提升成新的 requirement。

CornerBrace 的「每個 candidate 皆需 template」與 `body_relationship_selection` path 之間的矛盾已確認會影響正式產品規則，因此刻意排除。README 若提及該流程，只能連結現有 spec 或中性描述，不得替任一解讀背書。

### Decision 5：用文件證據檢查取代不必要的完整 regression rerun

本 change 不改 production code 或 tests。驗證包含：

1. 搜尋已移除符號、test-case workflow、upgrade tool、過時 test snapshot 與已解決 Waler duplicate 描述。
2. 檢查 README 與四份長期文件的相對連結、路徑及主要 entry point。
3. 執行 `openspec validate --all --strict`。
4. 以 `git diff --check` 及 diff path 檢查確認只有本 change artifacts 與允許的文件變更。

完整測試已在前一個功能 commit 驗證；純文字 change 不重跑 1475 項 regression。若 apply 階段意外修改 code、設定或 tests，則此假設失效，必須停止並恢復 scope 或重新決定驗證範圍。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 layer 或 dependency direction。

| Layer／區域 | 影響 |
|---|---|
| Presentation | 只讀確認目前 workspace 與 entry points；不修改 UI |
| Application／Domain／Algorithms／Infrastructure | 只讀確認 owner 與已成立行為；不修改 code |
| DXF subsystem | 不展開全面整理；只修正 README 中直接且可證明的入口描述 |
| Documentation | README 負責導覽；四份 `docs/*` 依既有分工保存長期 truth |
| OpenSpec | change artifacts 規劃文件工作；main specs 保持不變 |

依賴方向沒有改變。文件引用方向為 README 指向專責文件與 main specs；專責文件不需要反向複製 README 的完整內容。

## Backward Compatibility 與 Persistence

- 不修改 Project JSON schema、serializer、loader 或 migration 行為。
- README 只描述已成立的 schema 3 compatibility policy：missing／older label 仍須符合現行結構，legacy row shape 不轉換，future version 拒絕。
- 舊歷史紀錄可繼續提及當時的 compatibility 行為，但需清楚位於歷史來源。
- 不重新加入 `tools/upgrade_project_schema.py`，也不提出新的 migration。

## Risks / Trade-offs

- **[Risk] README 縮減後，讀者找不到細部函式** → 保留主要 entry points，並提供 `rg` 搜尋範例與專責文件連結。
- **[Risk] 移除歷史文字造成決策脈絡遺失** → 先確認相同歷史已在 `DEVELOPMENT_HISTORY.md` 或 archive；不刪除歷史來源。
- **[Risk] 以 code 校正文案時誤改 Domain 意義** → 只在 UI／symbol／module 現況使用 code authority；Domain／Solver／Workflow 以專責文件與 main specs 為主。
- **[Risk] 文件整理範圍膨脹成全面 rewrite** → 只處理已列證據及其直接交叉引用；新發現若不影響本次一致性，記錄而不順便修改。
- **[Trade-off] README 不再提供完整 API catalog** → 降低一次閱讀的完整度，換取較低 drift 與更清楚的 truth ownership。

## Migration Plan

這是文件變更，不需要 runtime deployment 或資料 migration。

1. 先調整 README 結構與過時內容。
2. 再檢查四份長期文件的直接交叉引用，只做必要修正。
3. 執行文件與 OpenSpec 驗證。
4. 若需要 rollback，可單獨 revert 文件 commit；Project 與使用者資料不受影響。

## Open Questions

無會改變本 change 方案或 task breakdown 的未決問題。CornerBrace requirement 矛盾屬於另一個需使用者決策的 spec change，不在此處延後決定。
