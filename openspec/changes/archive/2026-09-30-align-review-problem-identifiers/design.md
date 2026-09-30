# Design

## 閱讀導航

- **現在必讀**：Decision 1「在 `ProblemRecord` 投影邊界統一顯示」、Decision 2「只使用目前正式 source ownership」；兩者共同保證所有問題面板一致且不建立第二份工程 truth。
- **實作前閱讀**：Decision 3「安全替換與去重」及 delta spec「問題說明須使用可在清單定位的代號」。
- **遇到特定風險才讀**：Decision 4「fallback 與相容性」；只有處理無 owner、multi-owner、multi-handle 或既有測試固定 raw handle 時需要。
- **可先跳過**：Waler overlap 幾何、contact-face qualification、Solver 與 persistence 文件；本設計不修改其 contract。

## 方案摘要

`ValidationMessage` 繼續保存辨識層產生的原始診斷；`build_problem_records()` 在建立 Review-facing `ProblemRecord` 時，只取該訊息 `source_handles` 或明確 structured competing identities 作為替換 allowlist，再用同一個 `DXFImportResult` 的正式 source ownership 解析 `正式 ID（來源 handle）`。它不以全 result handles 對 description 全文搜尋。`build_review_items()` 與兩個問題 Treeview 繼續消費同一批 `ProblemRecord`，不各自格式化。

```text
ValidationMessage structured handles ──→ replacement allowlist
                                                 │
DXFImportResult members ──→ owner lookup ──→ build_problem_records()
                                                 │
                                                 └─→ ProblemRecord.description
                                                     ├─ 全體問題清單
                                                     └─ 選取項目問題明細
```

本 change 的「source ownership」只指目前正式 member 的 `source_handles` 對應；「顯示代號」指同一 member 在左側清單使用的 `member.id`。兩者只用於文字投影，不是新的工程 identity。

## 決策對照

| Decision | 對應 spec | 對應 tasks |
|---|---|---|
| 1. 在 `ProblemRecord` 投影邊界統一顯示 | 問題說明須使用可在清單定位的代號 | 1.1、1.2、2.1 |
| 2. 結構化 handle allowlist 加目前正式 ownership | 顯示代號不得取代診斷 identity | 1.1、1.2、2.2 |
| 3. 數值語境保護與 `正式 ID（handle）` 格式 | 數值碰撞／多來源 scenarios | 1.1～1.3、2.1 |
| 4. 自然排序、無 owner 與已排除 fallback | 多 owner／未解析／已排除 scenarios | 1.1、1.3、2.1、2.2 |

## Context

參見 `proposal.md` 的 Why。現況中 `recognition.py`、`importer.py` 等辨識流程會把 source handle 寫入 `ValidationMessage.message`；`validation.py` 的 `build_problem_records()` 已持有完整 `DXFImportResult`，也已建立 source handle 到正式 member ID 的 ownership 資訊，但目前直接複製原始 message 文字。`dialog.py` 的全體問題表與右側問題明細都顯示 `ProblemRecord.description`，因此 projection boundary 是可同時修正兩處且不碰 Tkinter widget 的最小共同點。

## Goals / Non-Goals

**Goals:**

- 對結構化列出 handle 的 Review 診斷採用一套 `正式 ID（來源 handle）` 顯示規則。
- 維持 raw structured identities，僅改變 `ProblemRecord.description`。
- 對工程數值、multi-owner、multi-handle、無 owner 與已排除狀態給出 deterministic、保守結果。
- 讓 focused unit tests 不需開啟 GUI 即可驗證顯示 contract。

**Non-Goals:**

- 不改診斷產生條件、message code、severity 或 blocking。
- 不解析自然語言以推導不存在的 source relationship。
- 不從整個 result 的 ownership index 搜尋未列於該訊息 structured fields 的文字 token。
- 不改 ReviewItem 分組、清單 ID、selection 或 source exclusion。
- 不建立新的持久化欄位或 migration。

## Decisions

### Decision 1：在 `ProblemRecord` 投影邊界統一顯示

顯示轉換放在 `build_problem_records()` 使用的集中式 helper，而不是分散修改每個 `ValidationMessage` 產生點，也不在 `dialog.py` 的兩個 Treeview 各做一次。

理由：

- 此處同時可取得原始診斷與完整目前 result。
- `ProblemRecord` 本來就是 concise、component-oriented UI row，符合 Presentation-facing projection 責任。
- 全體問題表與構件明細自然共用同一文字，不會 drift。

Rejected alternatives：

- 在每個 recognition message 直接寫 W／S／B ID：辨識階段常尚未分配正式 ID，且會把 UI label 帶入 source diagnostic truth。
- 在 `dialog.py` 即時替換：兩個面板與後續消費者容易各自形成不同格式規則。

### Decision 2：結構化 handle allowlist 加目前正式 ownership

每則訊息先從自己的 `ValidationMessage.source_handles` 與明確 structured competing identities（若該 message contract 提供）建立 replacement allowlist。Ownership index 來源仍是 `_result_members(result)` 中每個正式 member 的 `source_handles` 與 `id`，但只能查詢 allowlist 內的 handles；不得遍歷整個 index 對 description 做全文搜尋。文字中出現、但未列於該訊息 structured fields 的 handle 保留原文，並以 characterization test 記錄此類訊息。

同一 allowlisted handle 可對應一個或多個 member IDs；不得使用 proximity、collection position、舊 Review state、message role 或自由文字猜測 owner。已排除來源不在正式 member ownership 中，因此維持 raw handle。

Single source of truth：

- 診斷 truth：`ValidationMessage` 的結構化欄位。
- 正式顯示 ID truth：目前 `DXFImportResult` members 的 `id` 與 `source_handles`。
- `ProblemRecord.description` 只是上述兩者的衍生投影，不回寫任何一方。

這可避免另存 handle→ID 對照表造成 rebuild 後 drift。

### Decision 3：數值語境保護與顯示格式

formatter 只處理 allowlist 中、目前有正式 owner，且在診斷文字中以完整 source-reference token 出現的 handle。使用單次、最長 token 優先的替換，避免 handle 互為前綴時重複處理，也避免替換已產生的 member ID。

即使 `232` 在 allowlist 內，出現位置若緊接 `mm`、`°`、`%`，或屬於小數、座標 token，該次出現也視為工程數值而保留。測試固定「來源 232；長度 232 mm」只轉換前者，後者保持原值。禁止無邊界 `str.replace()`。

輸出規則：

- unique owner：顯示 `member ID（handle）`，例如 `W6（232）`。
- multiple owners：每個 owner 顯示 `member ID（handle）`，以自然排序及固定 `／` 分隔。
- 同一 member 的多個 allowlisted handles 在同一來源列舉中：只顯示一次 ID，括號內列出相關 handles，例如 `W6（232／4E4）`。
- 非完整 token、座標或小數的一部分不得替換。

Rejected alternative：只替換 `WALER_OVERLAP_*`。這只能修正畫面案例，無法涵蓋 BIM span、terminal ambiguity 與同來源多模型等已存在的同類訊息。

### Decision 4：自然排序、無 owner 與已排除 fallback

多 owner IDs 使用與左側清單一致的 numeric-aware 自然排序語意：文字片段不分大小寫比較，數字段以整數比較，因此 `W2` 排在 `W10` 前；member collection order 互換不得改變輸出。固定分隔符為全形 `／`。

formatter 對未列於 allowlist、沒有正式 owner 或已排除的 token 不做變更。這讓 `FB7` 仍可對應 `待修-FB7` 或 `已排除-FB7`，也避免為 unresolved／excluded source 製造 member ID。若一則訊息同時包含正式與未解析來源，只轉換 allowlist 中且能由目前 result 證明的部分。

既有 `ProblemRecord.component`、`source_handles`、`member_ids` 的計算與 ReviewItem ownership 邏輯維持不變；顯示轉換失敗時 fallback 為原始 description，不得丟棄問題或阻止 Review 畫面建立。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 layer responsibility：

- `dxf_import/recognition.py`／`importer.py`：維持 DXF recognition 與 raw diagnostics，不依賴 UI ID formatter。
- `dxf_import/validation.py`：既有 validation-to-review projection boundary 負責建立 UI-oriented `ProblemRecord`；新增純文字顯示投影仍在此責任內。
- `dxf_import/dialog.py`：Presentation widget 繼續只渲染 `ProblemRecord`，不新增 identity 推導。
- Domain、Algorithms、Application、Infrastructure persistence：無變更。

Dependency direction 維持「DXF raw result → validation/review projection → dialog display」，不產生 Presentation 回依賴 recognition 的反向關係。

## Risks / Trade-offs

- **[全數字 handle 被誤認為量測值]** → 僅替換 message allowlist 中的 source-reference occurrence，明定 `mm`／`°`／`%`、小數與座標排除測試。
- **[result 內其他 handle 誤中自由文字]** → ownership index 只作 allowlisted handles 的 lookup，不作全文候選來源。
- **[compound source 顯示重複 member ID]** → 對連續來源列舉做 owner-label 去重，新增 multi-handle regression。
- **[同一 handle 多 owner 造成誤選 winner或字典序錯誤]** → 顯示全部 owners、使用 numeric-aware 自然排序與固定 `／`，不改 structured ownership。
- **[部分舊測試期待 raw handle]** → 只更新屬於正式 member 的顯示 assertions；未解析來源與 structured fields 仍應維持原期待。
- **[自由文字格式新增後未被正確替換]** → focused tests 覆蓋目前已盤點的 handle-bearing diagnostics；fallback 保留原字，不讓問題消失。

## Migration Plan

1. 新增 formatter 與 unit tests，先固定 structured allowlist、數值語境、`ID（handle）`、自然排序、multi-owner、multi-handle、unresolved／excluded fallback。
2. 將 `build_problem_records()` 的 description 接到 formatter，不改其他欄位。
3. 執行 Waler overlap、BIM block 與 Review projection regression。
4. 若需 rollback，只需移除 description projection；資料與 persistence 無需回復或 migration。

## Backward Compatibility 與 Persistence

- `ValidationMessage`、`ProblemRecord` 與 `ReviewItem` 欄位形狀不變。
- serialized Review state、Project schema、export contract 與 solver input 不變。
- 唯一 user-visible 差異是問題說明中符合 structured allowlist 的已辨識來源改顯示 `正式 member ID（來源 handle）`。

