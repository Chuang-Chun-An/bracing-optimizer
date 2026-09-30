# Design

## 閱讀導航

### P0：實作者現在必須理解

- D1：確認 selected Waler 與所有正式 connection fields 的 Waler member identity domain，並以既有正式關聯作 single source of truth。
- D2：在工程資料組裝邊界建立純唯讀、分類且 deterministic 的反向摘要。
- D3：三個欄位的顯示位置、空值與非 Waler 相容行為。

### P1：進入特定模組前閱讀

- 修改 `dxf_import/dialog.py` 前閱讀 D2～D4，以及 delta spec 的兩個 Requirements。
- 修改共用中文欄位標籤前閱讀 D3，並核對 `bracing_optimizer/presentation/field_labels.py` 的既有 fallback 行為。
- 實作角撐彙整前閱讀 D1、D5；若 `redesign-corner-brace-occlusion-recognition` 已改變正式 connection contract，先停止並校正整合點。

### P2：需要時再讀

- D6：只有發現需要 persistence、export 或 Project schema 變更時閱讀；依設計應停止而非擴張 scope。
- 可先跳過 Solver、材料配置、Waler contact face 幾何演算法與 CornerBrace body recognition 細節。

## 方案摘要

```text
DXFImportResult（正式關聯 truth）
  +-- Strut.from_waler / to_waler
  +-- Brace.from_waler / to_waler
  +-- formal CornerBrace connections
              |
              v
      pure read-only relation summary
      {struts, braces, corner_braces}
              |
              v
      DXF Review engineering-data rows
```

本設計沿用現有 DXF Review 工程資料組裝流程。選取 Waler 時才從目前 staged result 反查三類正式關聯，完成去重與穩定排序後轉成三列文字；不把摘要保存回任何 model。

## 決策對照

| Decision | 結論 | 對應 Requirement／tasks |
|---|---|---|
| D1 | selected formal Waler 與正式 connection fields 使用同一 Waler member identity domain；UI identity 不參與 | 「圍令工程資料須顯示直接連接構件」之 identity scenarios；tasks 1、2 |
| D2 | 使用 pure read-only helper 建立分類、去重、deterministic 摘要 | 同上之去重與順序 scenarios；tasks 1、2 |
| D3 | Waler 固定顯示三列，空集合為 `—`，非 Waler 不變 | 同上之空集合與非圍令 scenarios；tasks 2、3 |
| D4 | Refresh 時重新投影目前 result，不保存 UI cache truth | 「顯示不得建立第二份關聯資料」；tasks 2、3 |
| D5 | 角撐須為目前正式 member 與 adopted connection 的交集，並忽略 orphan／stale、候選與 unresolved assessment | CornerBrace 完整性 scenarios；tasks 1、2 |
| D6 | 不變更 persistence、Project、export 與 Solver contract | 「顯示不得建立第二份關聯資料」；tasks 3、4 |

## Context

動機見 `proposal.md` 的 Why。現有 `Waler.to_project_row()` 不含反向關聯；`Strut` 與 `Brace` 已持有 `from_waler`／`to_waler`，而 `DXFImportResult` 保存正式 `corner_brace_connections`。`DXFImportDialog._engineering_data_rows()` 目前將 member 的 Project-like row 轉成右側工程資料，並已有對 Strut 與 Column 做 Presentation-only 衍生顯示的先例。

關鍵限制是不能為方便顯示而把反向清單加進 `Waler`，因為 forward relations 才是既有正式 truth；雙向持久化會產生 drift。現行 active CornerBrace redesign 也明定 body／relationship candidates 與正式 connection 的邊界，因此本 change 只能消費完成選擇後的正式 connection。

## 專有名詞

- **直接連接**：正式 member terminal identity 或正式 CornerBrace connection 指向目標 Waler identity。
- **正式 connection**：目前 staged Review result 已採用、可供既有 downstream flow 使用的 connection；不包含候選、assessment、preview 或 unresolved relationship。
- **反向摘要**：從 forward relation 即時計算出的 `{struts, braces, corner_braces}` 顯示集合，不是可保存的 domain state。
- **deterministic 顯示順序**：相同 ID 集合必須產生相同文字，與來源 collection／entity／connection record 順序無關；排序不參與工程判定。

## Goals / Non-Goals

**Goals:**

- 在不複製關聯 truth 的前提下，讓 Waler 工程資料可檢核直接連接拓撲。
- 讓分類、去重、排序與候選排除可由 pure tests 驗證。
- 保持既有 `_engineering_data_rows()`、field-label 與 panel refresh contract。

**Non-Goals:**

- 不把 Presentation 摘要提升為 Domain aggregate 或 Application contract。
- 不新增 navigation、hyperlink、connection station 或 diagnostic UI。
- 不統一或重構所有 DXF member relationship API。

## Decisions

### D1：只以既有正式 forward relations 作 single source of truth

目前 code contract 中，下列值皆使用 `Waler.id` 所代表的同一 **Waler member identity domain**：

- `Strut.from_waler`
- `Strut.to_waler`
- `Brace.from_waler`
- `Brace.to_waler`
- formal `CornerBraceConnection.waler_id`
- 傳入工程資料 row builder 的目前 selected formal `Waler.id`

Treeview selection 只負責經既有 selection flow 找回 formal member；relation-summary helper 必須接收該 `Waler` member 的 `id`，不得直接以 Treeview item ID、Treeview index、畫面 label 或 format 後 row value 作 identity。`CornerBraceConnection.waler_id` 由建立 connection 時使用的正式 `Waler.id` 取得，因此與 Strut／Brace terminal fields 及 selected `Waler.id` 可使用 exact identity equality。

對目標 formal Waler member identity：

- Strut：`from_waler == target` 或 `to_waler == target`。
- Brace：`from_waler == target` 或 `to_waler == target`。
- CornerBrace：目前 result 的正式 adopted connection 之 `waler_id == target`，且 `corner_brace_id` 必須存在於同一 staged result 的正式 `corner_braces` collection，才取其 ID。

比對採 exact identity equality；空字串不成立。Treeview item ID、顯示文字、collection index、source handle、entity order、format 後 field value、Column／Beam association、Waler chain topology、幾何鄰近、交點、diagnostic message、candidate point 或 recognition assessment 都不得成為替代來源。

若未來任一 formal connection field 改為不同 identity domain，helper 不得以字串外觀相同、source handle 或 proximity 自行橋接；只能呼叫當時已存在且屬正式 contract 的 mapping。若不存在此 mapping，實作必須停止並更新 artifacts。

**Rejected alternative：在 `Waler` 新增 `related_member_ids`。** 這會讓 forward 與 reverse data 同時可寫，需新增同步、序列化與 migration contract，且可能在 repair／rebuild 後漂移，因此拒絕。

**Rejected alternative：由 Presentation 重新做幾何連接判定。** 這會建立第二套 recognition rule，並可能把 unresolved 候選誤顯示為正式資料，因此拒絕。

### D2：以小型 pure helper 產生分類摘要

在 DXF Review／Presentation 邊界建立一個不修改輸入的 helper，輸入為目前 `DXFImportResult` 與目標 Waler ID，輸出三個 immutable ID sequences。helper 負責：

1. 從 D1 的正式來源收集 ID。
2. 先建立目前 staged result 的正式 CornerBrace member ID set，再過濾 adopted connections；orphan／stale records 不得輸出。
3. 各類獨立去重。
4. 以共享的 deterministic member-ID sort key 排序，使例如帶數字的 IDs 具有穩定且可理解順序；不得依 collection first occurrence 排序。
5. 不驗證、修復或重新指派關聯，不產生 diagnostics，且不得修改輸入 result 或任何 member／connection model。

若 helper 僅由 dialog 使用且規模維持小型，可放在 `dxf_import/dialog.py` 的 module-level pure function；若現有同層已有適合的 Presentation formatter，則放入該模組。不得為此建立跨層 service 或大型 abstraction。

**Rejected alternative：直接在 `_engineering_data_rows()` 內寫三段 ad-hoc loops。** 行為雖可完成，但分類、候選排除與 permutation invariance 較難獨立驗證，也容易在未來新增旁路時複製邏輯，因此不採用。

### D3：固定三列、固定分類、共用中文標籤

選取 Waler 時，在既有 Waler Project-like fields 之後、計算出的「構件長度（mm）」之前加入：

1. `直接連接支撐`
2. `直接連接斜撐`
3. `直接連接角撐`

每列以 `、` 串接已排序 ID；空集合顯示 `—`。標籤應使用 stable internal field keys，並透過既有 `engineering_field_label()` 中文化，避免把中文 label 回寫 model。非 Waler 不建立這些 internal display fields。

固定顯示三列而非只顯示非空列，可讓使用者區分「沒有連接」與「功能沒有提供資料」。分類顯示而非單一混合列，可避免只靠 ID prefix 猜測構件類型。

### D4：沿用既有 panel refresh，不保存反向摘要

`_update_engineering_data_panel()` 每次依目前 member 與目前 staged `result` 呼叫 row builder。反向摘要只存在該次計算結果，不加入 dialog 長期 cache。合法 Review mutation 完成後，既有 selection／panel refresh lifecycle 重新呼叫 row builder，即可自然反映新 truth。

Manual editing、diagnostics 與 preview 不新增自己的 Waler relation summary；它們若需要顯示相同資訊，必須重用同一 pure helper，而不是各自推導。

### D5：CornerBrace 只接受正式 adopted connection

目前 contract 下，`DXFImportResult.corner_brace_connections` 是 adopted formal connection 來源，但 connection record 單獨存在仍不足以顯示。helper 必須先以目前 staged `DXFImportResult.corner_braces` 建立正式 member ID set，只有 `corner_brace_id` 存在於該 set，且 connection 的 `waler_id` exact-match selected formal `Waler.id` 時才納入。

Body hypotheses、`BodyRelationshipAssessment`、unresolved body／relationship、repair candidates、Preview temporary selection、已排除 CornerBrace，以及沒有對應正式 member 的 orphan／stale connection 一律排除。Presentation 只做 set membership 過濾與顯示，不得自行建立、修復、重新指派或回寫 connection。

如果 active change 移除或改寫正式 connection contract，實作者不得解析 message 或暫時改讀候選集合，必須停止並更新本 design 的整合點。

### D6：零 persistence 與下游 contract impact

不修改 `to_project_row()`、`DXFImportResult.to_dict()`、Project mapping、Project schema version、save/load、Excel／DXF export 或 Solver input。新增的 stable internal field keys 只服務工程資料 label mapping與 row formatting，不是資料格式欄位。

因此舊有 completed project、paused Review snapshot 與 exported data 不需 migration；Rollback 只需移除 Presentation helper、三個 labels 與 tests，不涉及資料回復。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 Architecture 本身**。

```text
dxf_import models / recognition（正式關聯 ownership）
                    |
                    v  read-only
dxf_import Review Presentation helper
                    |
                    v
DXFImportDialog engineering-data rows
```

- **DXF recognition／models**：繼續擁有正式 member identity 與 connection truth；本 change 不修改。
- **Presentation**：負責反向投影、格式化與空值顯示，不做工程判定。
- **Application／Domain／Algorithms／Infrastructure persistence**：不受影響。

Dependency direction 是 Presentation 單向讀取目前 DXF result。不得讓 model 依賴 UI labels，也不得讓 Presentation 產生可提交的新 connection state。

## Risks / Trade-offs

- **[CornerBrace active change 改變正式 connection 結構]** → 實作前確認 adopted formal connection 的單一 collection；若不存在相容來源則停止並更新 design，不讀候選資料替代。
- **[UI selection identity 被誤當正式 Waler identity]** → helper 只接收 row builder 中 formal `Waler.id`，加入 Treeview／顯示 identity 不同與 rebuild tests。
- **[orphan／stale CornerBrace connection 洩漏到顯示]** → connection IDs 必須與目前 staged formal CornerBrace member set 取交集，加入 orphan／excluded tests。
- **[同一構件有重複 terminal／connection records]** → pure helper 各類以 ID 去重，加入同端重複與雙端同 Waler tests。
- **[輸入順序導致畫面文字變動]** → 使用 deterministic sort key，加入 member 與 connection permutation tests。
- **[UI helper 誤回寫 model]** → tests 保存輸入 snapshot／row 並確認呼叫前後相同；helper 僅回傳 immutable sequences。
- **[關聯數量很多造成換行]** → 沿用現有工程資料 value label 的 `wraplength`；本 change 不新增 scrolling 或截斷規則。

## Migration Plan

1. 先加入 Waler identity-domain、CornerBrace formal-member intersection、pure relation-summary 與 field-label contract tests。
2. 實作唯讀摘要及 Waler engineering-data rows。
3. 執行 DXF Review layout／field-label focused tests，再執行相關 DXF Review regression。
4. 不需資料 migration；若需 rollback，移除新增顯示邏輯與 labels 即可，既有資料完全不變。

## Open Questions

無。helper 的名稱與同層檔案位置可在不改變 D1～D6、spec 或 tasks 的前提下依現有 style 決定。
