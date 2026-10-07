# Design：穩定 CornerBrace repair reference identity

## 閱讀導航

- **P0／現在必讀**：先讀「方案摘要」、「現行 identity audit」、D1「Stable reference match key」與 D2「集中式唯一對齊」；這些段落定義哪些欄位是工程 identity，以及 display `member_id` 為何不得參與工程 identity。
- **P0／現在必讀**：實作 replay 前讀 D3「以目前 reference 重驗並重建 candidate」與 D4「Workflow 邊界」；不得略過既有 geometry、connection、eligibility、confirmation、provenance 或 candidate validation。
- **P1／實作前閱讀**：修改 `corner_brace_repair.py` 或 `review_confirmation.py` 前讀 D3、D5、D6、「Architecture Alignment」與「驗證策略」；確認不改 `CornerBraceRepairReference` 的全域 equality，也不新增 persistence migration。
- **P1／實作前閱讀**：修改 source exclusion／restore 或 Pause／Resume 測試時，讀 `docs/WORKFLOW.md` 的 CornerBrace repair、單筆 Source Exclusion transaction 與 Resume 段落。
- **P2／需要時再讀**：只有追查 S14 fixture 或效能回歸時，再讀 archived `optimize-dxf-source-exclusion-workflow/design.md` 的「S14／D1A反例根因」及 Y05 fixture 段落。可先跳過 Solver、材料、Waler 最佳化、recognition ranking、Preview UI 與 Project schema。

## 方案摘要

既有 `CornerBraceRepairSubjectKey` 已保存 source fingerprint、normalized source handles、target kind、base geometry key 與固定角色；問題不是缺少穩定資料，而是 replay 以包含 display `member_id` 的整個 `CornerBraceRepairReference` 當 dictionary key。

本方案保留現有 model 與 serialized payload，僅把 saved-reference lookup 改成明確的兩階段流程：

```text
saved CornerBraceRepairReference
  -> (reference_class, CornerBraceRepairSubjectKey) 唯一對齊目前 eligible evidence
  -> 取得目前 reference（含目前 display member_id）
  -> 重驗 template／secondary eligibility、geometry、connection、confirmation、provenance
  -> 重建 transfer 與 current candidate validation
  -> 成功：以目前 references 建立 replay candidate 與新 provenance
  -> 失敗／零筆／多筆：沿用既有 needs_review／disabled／deferred 語意
```

Display `member_id` 保留在 payload、診斷及 UI 中，但不再用來判定 reference 是否為同一工程 subject。Changed-content compatible recovery 不進入此 stable replay 路徑。

Target Waler／Strut已使用canonical source identity，不需重構。另有兩個display-ID-sensitive安全guard：preferred repaired CornerBrace ID與CornerBrace confirmation signature；前者維持安全拒絕，後者需忽略純display-ID重編，否則manual-secondary reference即使是同一工程subject也無法維持有效confirmation。

## 決策對照

| Decision | 解決的問題 | 對應規格 |
| --- | --- | --- |
| D1. 使用 `(reference_class, subject_key)` 作 match key | display ID 重編造成 false negative | `修補決策必須可追溯且安全重播`、`顯示 member ID 重編但 stable reference 未變` |
| D2. 由單一 resolver 執行恰好一筆且一對一匹配 | 防止零筆、多筆、first match 或不同 class 誤配 | `Stable reference 無匹配`、`Stable reference 匹配不唯一` |
| D3. Candidate 與新 provenance 使用目前 result 的 references | 避免成功 replay 後繼續保存過期 display ID，並確保安全重驗使用 current truth | `Stable reference 對齊後工程輸入改變`、`相同來源安全重播` |
| D4. Same-fingerprint rebuild 共用 matcher，changed-content recovery 不使用 | 維持 Pause／Resume、source exclusion／restore、Exact Match 與 recovery 的既有安全邊界 | `Changed-content recovery 不因 stable reference match 恢復 repair` |
| D5. 不改 schema、不改 dataclass equality | 保持舊 payload 可讀並限制影響範圍 | `Legacy version 2 repair payload` |
| D6. CornerBrace confirmation signature忽略純display-ID重編 | 讓已確認的manual-secondary reference在同一工程內容重新編號後仍可安全對齊 | `顯示 member ID 重編但 stable reference 未變`、`Stable reference 對齊後工程輸入改變` |

## Context

問題動機與 scope 見 `proposal.md`。現行資料模型已將穩定 subject 資料放在 `CornerBraceRepairSubjectKey`，並將顯示名稱放在 `CornerBraceRepairReference.member_id`。`eligible_repair_references()` 會從目前 `DXFImportResult` 建立 automatic-primary 與 manual-secondary evidence；這份 current evidence 是 replay 時 reference eligibility 與 connection 的正式來源。

目前 `reconstruct_saved_template_candidate()` 與 `reconstruct_legacy_adopted_candidate()` 以完整 `CornerBraceRepairReference` 建立 dictionary／set，因此 frozen dataclass 的預設 equality 同時比較 `subject_key`、`member_id` 與 `reference_class`。當 recognition 順序改變、同一 source subject 取得不同 CB 編號時，lookup 在進入 template、connection 與 candidate validation 前就失敗。

Source exclusion／restore 與重新 recognition 的 Pause／Resume 都透過 `replay_manual_overrides()` 逐筆重建 CornerBrace repairs；secondary-reference dependency 另有既有 deferred pass。Exact Match Relink 本身只更新 source reference，不重新辨識；之後若 Resume 需要 recognition／replay，仍回到相同 reconstruction path。內容不同的 compatible recovery 則受 `paused-dxf-review-source-relink` 規格限制，不得套用舊 repair。

目前工作樹另有 CornerBrace planning 效能與其他 DXF workflow 修改。本設計不依賴那些優化，也不得改變其 candidate validation、per-call cache 或 transaction 行為。

## 現行 identity audit

下表記錄本change開始實作前的實際比對路徑。程式位置以函式／資料類別作穩定錨點，不依賴會隨修改位移的行號。

| 項目 | 現行資料與程式位置 | Display ID依賴與失敗分類 |
| --- | --- | --- |
| Target Waler／Strut | `dxf_import/corner_brace_repair.py::_identity_for_member()`以`member.source_handles`建立canonical source identity；`apply_corner_brace_repair()`保存`target_waler_identity`／`target_strut_identity`；`dxf_import/source_exclusion.py::replay_manual_overrides()`依canonical identity要求唯一current member | Provenance與replay不使用W／S顯示編號作identity。零筆或多筆source-identity match時安全拒絕，不會改接取得舊編號的另一支構件。 |
| Confirmation key | `dxf_import/review_confirmation.py::review_confirmation_identity()`以role與normalized source handles建立key；`review_item_is_confirmed()`用此key取saved signature | Key不含member ID，不會把另一source member的confirmation錯誤套入。 |
| Confirmation signature | `review_confirmation_signature()`把`asdict(member)`放入payload；CornerBrace的`id`及nested repair reference `member_id`因此進入hash | 同一source subject純重新編號時signature失效，結果是manual secondary不再eligible並安全拒絕；不是錯誤接受。D6將排除這類純display metadata差異。 |
| Preferred repaired ID | `CornerBraceRepairProvenance.preferred_display_id`保存`apply_corner_brace_repair()`實際採用的CornerBrace ID；`_next_corner_brace_id()`只在未占用時沿用，`replay_manual_overrides()`在衝突或最終ID不一致時拒絕staged result | 依賴display ID，但用途是target命名與衝突guard。編號位移或被不同source占用時為`needs_review`，不會提交錯誤構件。 |
| `base_geometry_key` | `dxf_import/corner_brace_repair.py::_base_geometry_key()`：recognized item使用完成recognition後的member工程線；unresolved item使用exact source geometry。recognized工程線在`dxf_import/recognition.py::_refine_corner_brace_axis_intersections()`已由Waler inner line／Strut centreline refinement | Key不含connection record、W／S member ID或display label；recognized key包含connection-context推導後的幾何結果，unresolved key只含來源本體幾何。幾何真的改變時安全拒絕，純display ID位移不影響key。 |
| `evidence_signature` | `apply_corner_brace_repair()`建立的audit signature可能包含selected template member ID；現行replay不把它當lookup identity | 只作保存／稽核，不造成S14 lookup失敗；成功replay後由current candidate重新產生。 |

Audit結論：沒有找到display ID位移後可能對到另一支構件的錯誤接受路徑。現有display-ID依賴均為false negative／安全拒絕；其中reference lookup與CornerBrace confirmation signature屬本change需修正的可恢復性問題，preferred target ID guard則刻意保留。

### S14／D1A target實體核對

以Y05 saved Review state排除Strut `S14`／source identity `strut:D1A`，CB66～CB70前後target如下。前後canonical identity完全相同；只有CB68～CB70的Strut顯示編號各前移一號。

| Repair | Waler排除前 → 排除後 | Waler source identity | Strut排除前 → 排除後 | Strut source identity |
| --- | --- | --- | --- | --- |
| CB66 | W5 → W5 | `waler:B29` | S5 → S5 | `strut:B05` |
| CB67 | W6 → W6 | `waler:B34` | S5 → S5 | `strut:B05` |
| CB68 | W13 → W13 | `waler:1647` | S21 → S20 | `strut:D74` |
| CB69 | W13 → W13 | `waler:1647` | S20 → S19 | `strut:D4B` |
| CB70 | W13 → W13 | `waler:1647` | S19 → S18 | `strut:D34` |

這五筆目前的實際failure point不是target Waler／Strut、confirmation或preferred ID，而是automatic-primary reference仍用完整`CornerBraceRepairReference` equality：CB61→CB57（`11D0`）、CB62→CB58（`1205`）、CB56→CB52（`113F`）、CB53→CB49（`1126`）、CB50→CB46（`110D`）。Fixture的五筆repair均無manual secondary，saved Review state亦無review confirmations，因此D6不是S14五筆失敗的直接原因。

## Goals / Non-Goals

**Goals:**

- 讓 saved primary、selected template 與 secondary references 依穩定 subject identity 唯一對齊目前 eligible references。
- 讓 display ID 重編但工程 reference 未變的 repair 繼續通過完整安全 replay。
- 讓 replay 成功後的 candidate、diagnostics 與新 provenance 使用目前 result 的 display ID，避免保存 stale reference metadata。
- 讓 new-format template replay 與 legacy adopted-line replay 使用同一 match contract。
- 讓CornerBrace confirmation在source identity與工程內容未變時不受display ID重編影響，使已確認的manual secondary仍能通過既有eligibility檢查。
- 保持零筆、多筆、class mismatch、geometry／connection drift 與 secondary dependency 的既有保守結果。

**Non-Goals:**

- 不改 `CornerBraceRepairSubjectKey` 欄位、recognition 編號規則或 CornerBrace candidate ranking。
- 不把 proximity、geometry-only、舊 display ID 或 collection order 當 fallback identity。
- 不改 target subject、target Waler／Strut canonical identity 或 adopted world line 的 replay contract。
- 不移除preferred repaired CornerBrace ID conflict guard，也不在衝突時自動選新ID後接受replay。
- 不改 changed-content compatible recovery、Project schema、Review state version、Solver 或 Presentation。
- 不建立跨 repair cache、dependency graph 或新的 replay summary 類型。

## Decisions

### D1. Stable reference match key 使用既有 subject key 加上 reference class

Reference lookup key 採：

```text
(saved_reference.reference_class, saved_reference.subject_key)
```

`CornerBraceRepairSubjectKey` 已是 frozen、normalized value object，包含：

- `source_fingerprint`
- normalized `source_handles`
- `target_kind`
- `base_geometry_key`
- 固定的 `corner_brace` role

其中`base_geometry_key`不得誤解為原始source body的統一快照：recognized subject使用完成Waler／Strut context refinement後的工程線段，unresolved subject才使用exact source geometry。兩者都不包含connection record或W／S顯示ID；因此stable match仍須在D3另外重驗current unique connection。

`reference_class` 不放入 subject key，因為它描述該 subject 在 repair evidence 中的資格，而不是 DXF source subject 本身；但 lookup 必須同時核對它，避免 automatic primary 與 manual repaired secondary 互換。`member_id` 不進入 key，只保留為目前畫面名稱與診斷資訊。

實作使用 structured value equality，不以 `_subject_token()` 的 hash 字串作唯一真相。Token 可繼續用於 candidate ID、排序或診斷，但不得讓 hash 或格式化字串取代完整 subject key 比較。

**未採用方案：修改 `CornerBraceRepairReference.__eq__`／`__hash__` 忽略 member ID。** 這會改變所有 set、dictionary、candidate supporting-reference 去重與測試語意，難以區分「工程 identity 比較」和「完整 audit snapshot 比較」，影響面大於本 change。

**未採用方案：刪除或不再保存 `member_id`。** Display ID 對 Preview、diagnostics、audit 與現有 payload 相容性仍有價值；問題只在它被錯用為 match identity。

### D2. 集中式 resolver 執行唯一且一對一的 reference 對齊

`corner_brace_repair.py` 新增 module-private resolver，由 current `eligible_repair_references()` 輸出的 `CornerBraceReferenceEvidence` 建立 index。Index value 保留 list／tuple，不在建表時覆蓋重複 key，才能明確偵測多筆 match。

Resolver 對每一筆 saved reference 執行：

1. 核對 saved `reference_class` 是該集合預期的 primary 或 secondary class。
2. 以 `(reference_class, subject_key)` 查詢 current eligible evidence。
3. 要求恰好一筆 current match；零筆或多筆都回傳安全失敗。
4. 要求整組 saved references 一對一映射；重複 saved key 不得共同指向同一筆 current evidence。
5. 保留 saved tuple 順序回傳 current evidence／references，讓 provenance 與 deterministic output 不受 dictionary order 影響。

Selected template 透過相同 resolver 對齊，且解析結果必須是 resolved primary set 中同一 stable key 的唯一項目。不得先用 display ID lookup 再 fallback；所有 replay 入口只有一套 identity 語意。

New-format 與 legacy reconstruction 共用 resolver。`source_exclusion.py` 繼續只負責 replay orchestration、deferred pass 與結果分類，不複製另一套 reference matcher。

**未採用方案：member ID exact match 優先、stable key 作 fallback。** 兩條 precedence 會讓相同 payload 因入口或資料順序得到不同結果，也無法清楚保證多筆 stable match 時必須拒絕。

**未採用方案：以 source handle 或 geometry 單欄匹配。** Compound INSERT 可能由同一 handle 產生多個 CornerBrace；只用 geometry 又可能跨 source identity 轉移 decision。既有完整 subject key 正是為避免這兩類碰撞。

### D3. 以目前 reference 重驗並重建 candidate

唯一對齊只證明「找到同一個 source subject」，不代表 replay 已合法。`reconstruct_saved_template_candidate()` 仍依既有順序重驗：

1. Current reference 已通過 `eligible_repair_references()` 的來源有效性、唯一 connection、primary／secondary class、confirmation 與 repair provenance 條件。
2. Selected primary 從 current evidence 重新抽取 local template；其 Waler offset、Strut station、topology 與局部幾何仍須符合 saved provenance 及既有 tolerances。
3. Target Waler／Strut canonical identities 必須各自唯一，current relationship frame 與 reference／target angle 必須合法。
4. Transfer 後工程線必須再次通過 target residual evidence、finite endpoints、duplicate、CornerBrace connection 與既有 candidate validation。
5. Replay orchestration 仍核對 reconstructed line 與 saved adopted world line，並維持 unresolved preferred-ID conflict 的既有拒絕行為。

Target Waler／Strut lookup繼續只使用saved canonical identities；current顯示ID僅用於當次result內取得relationship與輸出。Preferred repaired CornerBrace ID同樣不升格為source identity：若該ID已由不同source subject占用，或staged replay得到不同ID，整筆staged result不得commit並維持`needs_review`。不得因preferred ID衝突而把repair轉移、選first match或靜默接受新ID。

成功時，candidate 的 `template_reference`、`primary_references` 與 `secondary_references` 全部使用 resolver 回傳的 current references；因此 `apply_corner_brace_repair()` 產生的新 provenance 會保存目前 display IDs。Saved member IDs只可出現在舊 payload 或稽核資料中，不得回填成 current engineering reference。

Legacy adopted-line replay 同樣把 saved references 對齊成 current references後再建立 candidate，但仍維持「不重新 ranking、不改選 nearest template、不重算 adopted line」的既有 contract。

`evidence_signature` 不是 reference identity 的 single source of truth，replay 不得用它或其中可能存在的 display metadata決定 match。現有 payload 不需重寫 signature；成功 replay 後由目前 candidate 重新產生 audit signature。

### D4. Workflow 邊界維持既有 replay 與 recovery 語意

- **Source exclusion／restore**：fresh recognition 後由 `replay_manual_overrides()` 呼叫共用 reconstruction；display ID 漂移不再提前失敗。真正被排除、失去 connection 或 eligibility 的 reference 仍失敗。
- **Same-fingerprint Pause／Resume**：重新 recognition 時使用相同 resolver；same-session cache 未重建時不增加額外工作。
- **Exact Match Relink**：維持只更新 source reference、不額外 recognition 或二次確認。後續 Resume 若需 replay，使用同一 resolver；本 change 不改 Relink transaction。
- **Secondary deferred pass**：第一輪缺少尚未 replay 的 manual secondary 時，維持既有 deterministic later pass。Resolver 不建立跨 repair dependency graph；第二輪仍無唯一 eligible match 才列 `needs_review`。
- **Changed-content compatible recovery**：不得呼叫 stable matcher來恢復舊 repair decision。Fingerprint 不同時仍以 candidate recognition為基底，依既有規格分類 `requires_review`／`disabled`，且不恢復 reference eligibility。

### D5. Backward compatibility 與 persistence impact

不新增欄位、不提高 Review state／Project schema version，也不執行 migration。既有 `CornerBraceRepairReference` payload 的 `subject_key`、`member_id` 與 `reference_class` 照常解析；`member_id` 僅從 match key 移除。

Legacy version 2 payload 若通過現有 parser，繼續使用保存的 adopted world line、target identities 與 references安全 replay。缺欄位、非法 class、無效 subject key 或 partial template fields 仍由現有 parser／reconstruction拒絕，不因本 change 推測補值。

成功 replay 後，current references 會自然寫入新的 runtime provenance；下一次 Pause／Save 才依既有流程持久化。Rollback 不需要資料降版：舊程式仍能讀取相同 payload，只可能再次把 member ID 納入 matching 而恢復原 false-negative 行為。

### D6. CornerBrace confirmation signature只排除純display metadata

Confirmation map key維持`review_confirmation_identity()`的canonical source identity，不新增第二種key。`review_confirmation_signature()`仍必須代表使用者確認時看到的工程與review truth，但對`role == "corner_brace"`的member payload先做targeted canonicalization：

- 移除／替換top-level CornerBrace `id`等只表示當次recognition順序的label。
- Nested `CornerBraceRepairReference.member_id`以其`(reference_class, subject_key)`代表，保留source fingerprint、source handles、target kind、base geometry與class。
- `preferred_display_id`與只為audit呈現的selected-template display metadata不作confirmation工程內容；target Waler／Strut仍由canonical identity表示。
- 幾何、source handles、recognition／selection內容、repair subject、adopted line、transfer參數、primary／secondary stable identities、body／relationship evidence、warnings與problems仍參與signature。

Canonicalization只套用CornerBrace confirmation member payload，不全域刪除任意名稱為`id`的欄位，也不改Beam assembly或Waler contact confirmation語意。`_member_for_item()`仍可用current ReviewItem的display ID加source identity找到當次member；這是current-result存取，不是persisted confirmation identity。

**未採用方案：維持現行signature，讓manual secondary重新確認。** 這是安全的，但與本change宣告的secondary reference display-ID drift可恢復目標衝突，且把純呈現變更誤當工程變更。

**未採用方案：confirmation只hash source identity。** 這會忽略幾何、repair evidence與review problems等使用者原本確認的內容，可能錯誤沿用confirmation。

**未採用方案：全域移除所有member ID。** 其他role可能把association／contact ID當成有意義的current evidence；本change沒有足夠證據重寫其confirmation contract。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 layer responsibility 或 dependency direction。

```text
DXFReviewWorkflow
  -> source_exclusion.py        replay orchestration／分類／deferred pass
       -> corner_brace_repair.py reference eligibility、stable resolver、reconstruction、validation
       -> review_confirmation.py CornerBrace confirmation payload canonicalization
            -> models.py         immutable subject key／reference／provenance value objects
```

- `models.py` 的 `CornerBraceRepairSubjectKey` 是 persisted stable subject identity 的 single source of truth；本案預期不需改其 shape 或全域 equality。
- `corner_brace_repair.py` 擁有 reference eligibility、stable lookup 與 candidate rebuild，避免 workflow、Presentation 或 persistence parser各自實作工程 matching。
- `source_exclusion.py` 保持 Review decision persistence 與 replay orchestration責任，只消費 reconstruction 成功／失敗，不理解 display-ID fallback。
- `review_confirmation.py`保有confirmation signature責任；只針對CornerBrace payload區分stable engineering truth與volatile display metadata，不把repair matching移入confirmation層。
- `DXFReviewWorkflow` 繼續擁有 live Review state；Dialog 與 Preview 不保存第二份 identity map。
- Domain、Algorithms、主 Application 與 Infrastructure 不受影響；DXF provenance 不進入 Project／Solver rows。

Current eligible evidence 與 saved provenance 是不同時間點的資料，不是兩份同時有效的 truth：saved subject key只提出要找的歷史 subject；current `DXFImportResult` 與 `eligible_repair_references()` 才決定它現在是否存在且仍合法。Resolver 回傳 current evidence後，後續所有工程判斷只使用 current truth，避免 drift。

## 驗證策略

### Focused unit／integration tests

- New-format selected primary 的 `subject_key` 不變但 `member_id` 改變時，reconstruction 成功，candidate與新 provenance 使用 current ID。
- Automatic primary supporting references及manual secondary references發生 ID 重編時，整組依 saved order 唯一 remap；secondary deferred pass仍可在後續輪次成功。
- CornerBrace confirmation key不變且只有top-level／nested display ID重編時signature保持相同；source、geometry、repair evidence、problems或其他工程內容改變時signature必須不同。
- 同一source CornerBrace改名後仍能由current ReviewItem找到member；另一source取得舊display ID時不得命中原confirmation key。
- Stable key 零筆、多筆、saved duplicate、一對多或 `reference_class` 不一致時拒絕，不使用 display ID、proximity 或 first match。
- Reference base geometry、local template尺寸、unique connection、primary／secondary eligibility、confirmation 或 provenance失效時仍拒絕。
- Target Waler／Strut顯示ID改變但canonical identity唯一且工程relationship未變時可繼續；identity缺失、多筆或relationship drift時拒絕。
- Preferred repaired ID被不同source占用或staged replay得到不同ID時不commit且列`needs_review`。
- Legacy adopted-line replay 可容忍 reference display ID 重編，但不重新 ranking、不改 adopted line。
- Changed-content recovery 即使能找到相同／相近 reference，也維持既有 `requires_review`／`disabled`，不套用 repair。

### S14／D1A fixture regression

以 Y05 saved Review state 排除 Strut `S14`／handle `D1A`：

- CB28～CB31 因實際 connection 依賴 S14 而消失，這是合理工程結果。
- 後方 stable references雖由 CB50 等重編為 CB46 等，source handles、subject geometry與connection未變時，CB66～CB70不得只因 display ID 改變成為 `needs_review`。
- 明確assert CB66／CB67 target顯示ID不變，CB68～CB70的Strut分別S21→S20、S20→S19、S19→S18，且五筆Waler／Strut canonical identity均維持「S14／D1A target實體核對」表中的值。
- 原本已 preserved 的 CB71～CB76不得回退；整體 replay report、repair provenance、members、connections、problems、ReviewItems、confirmations與completion truth需符合 current validation。
- Regression 比較工程 truth及stable reference identities，不以硬編碼舊 display ID作安全判斷；display ID只驗證為當次current output。

### Validation scope

先執行 CornerBrace repair與source-exclusion focused tests，再執行Pause／Resume、source relink及Y05 fixture regressions；最後執行OpenSpec strict validation。若 implementation改到architecture imports，再補boundary tests。Solver regression不在本 change範圍。

## Risks / Trade-offs

- **[Risk] Stable subject key碰撞會把不同 current references視為同一組候選。** → Index保留所有values並要求恰好一筆；不得用dictionary overwrite或first match消除歧義。
- **[Risk] 只修 selected template，supporting primary或secondary仍因ID漂移失敗。** → Resolver一次處理provenance中的完整primary／secondary集合，candidate只使用current mapped references。
- **[Risk] Remap成功後略過工程安全檢查，形成false positive。** → Stable match只替換lookup階段；template extraction、saved local尺寸、current connection、target evidence及candidate validation全部保留。
- **[Risk] Secondary尚未replay被誤判永久缺失。** → 保留既有deferred pass；resolver不改replay順序，也不跨repair cache outcome。
- **[Risk] Current display ID回寫provenance使測試或診斷文字改變。** → Identity assertions改比subject key／source handles；UI與audit仍顯示current ID，舊ID不作工程判斷。
- **[Risk] Confirmation canonicalization過度移除欄位而沿用過期確認。** → 只列舉CornerBrace已知volatile display metadata；所有source、geometry、repair、relationship、warning與problem資料保留，並以mutation tests證明每類工程變更都會改signature。
- **[Risk] Target display ID與preferred ID被誤當相同問題一併放寬。** → Waler／Strut以canonical source identity對齊；preferred repaired CornerBrace ID guard維持原拒絕語意，兩者分開測試。
- **[Risk] 與同檔案既有planning優化修改重疊。** → 實作只替換reference lookup與candidate remap，保留per-call indices、canonical validation oracle及其他不相關修改；先跑focused diff與regression。
- **[Trade-off] 每次reconstruction建立小型reference index。** → 成本為current eligible reference數量的線性工作，且只在單次replay call內存活；不建立更高風險的跨repair cache。

## Migration Plan

1. 在`corner_brace_repair.py`加入module-private stable resolver與focused unit tests，不改serialized model shape。
2. 將new-format與legacy reconstruction的完整-dataclass dictionary／set lookup改為resolver，並以current references建立candidate。
3. 在`review_confirmation.py`加入CornerBrace-specific display metadata canonicalization，驗證純ID drift穩定且工程內容drift仍會使signature失效。
4. 執行display-ID drift、零筆／多筆、geometry／connection／eligibility drift、preferred-ID conflict及secondary deferred tests。
5. 執行Y05 S14／D1A source-exclusion fixture與Pause／Resume／relink regressions，確認target identity與changed-content邊界不變。
6. 若所有驗證通過，不需資料migration或使用者操作；既有projects在下一次成功replay與save時自然保存current display metadata。

Rollback只需還原matcher與candidate remap程式變更；因payload格式未變，不需回復或轉換Project資料。若實作發現必須新增schema、修改subject key欄位、放寬changed-content recovery或改變CornerBrace eligibility，應停止並回到proposal／spec重新評估，而不是擴張本Design。
