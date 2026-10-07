# Proposal：穩定 CornerBrace repair reference identity

## 閱讀導航

- **P0／現在必讀**：本文件「快速摘要」、「現況與目標」、「主要流程」與「不變事項」；先確認本案只修正 reference identity，不放寬 repair 安全檢查。
- **P0／現在必讀**：`openspec/specs/dxf-corner-brace-repair-tool/spec.md` 的「參考角撐必須分級並阻止推測鏈」與「修補決策必須可追溯且安全重播」；本案將補充 reference replay 的穩定 identity contract。
- **P0／現在必讀**：`openspec/specs/paused-dxf-review-source-relink/spec.md` 的「角撐修補決策不得跨內容靜默轉移」；changed-content recovery 仍維持保守邊界。
- **P1／實作前閱讀**：後續 `design.md` 再定義 stable subject key對齊、零筆／多筆match與geometry／connection revalidation；在 design產生前不要自行選擇fallback細節。
- **P2／需要時再讀**：修改 source exclusion／restore或Pause／Resume測試時，再讀 `optimize-dxf-source-exclusion-workflow` 的 replay contract與 `docs/WORKFLOW.md` 對應段落。可先跳過Solver、材料、Waler最佳化、候選ranking、DXF自動辨識門檻與Project schema；本案不修改那些內容。

## 快速摘要

- 目前保存的 `CornerBraceRepairReference` exact dictionary key包含依辨識順序產生的顯示 member ID；前方角撐增減會讓同一支reference改名，造成安全但錯誤的`needs_review`。
- S14／D1A反例中，排除S14使4支直接相連角撐消失，後方references的source handles、幾何與connection未變，但CB50等顯示ID位移，導致CB66～CB70共5筆repair replay失敗。
- 目標是以穩定source identity／subject key辨識「同一支reference」，顯示member ID只作呈現與診斷，不再作exact identity必要欄位。
- Identity audit確認target Waler／Strut已以canonical source identity保存與重播；S14中只有部分Strut顯示編號位移，target仍能對回同一實體構件。現行confirmation key同樣以source identity索引，但其signature仍間接包含member ID，會在純顯示編號位移時造成安全拒絕。
- 成功對齊後仍須重驗reference來源、角色、幾何、唯一connection、eligibility、confirmation與provenance；任何變更、缺失或歧義仍為`needs_review`或既有安全分類。
- 本案獨立於`optimize-dxf-source-exclusion-workflow`；後者只做planning效能優化，不修正S14 identity問題。

## 現況與目標

本案中的「stable subject key」是由reference自己的角色、source fingerprint／normalized source handles及可穩定重建的subject資料形成的identity；`CB50`這類member ID只是每次recognition後依順序產生的顯示名稱。

| 項目 | Before（現況） | After（目標） |
| --- | --- | --- |
| Reference exact match | stable subject資料與顯示member ID一起成為dictionary key | 先以stable source identity／subject key唯一對齊；member ID只作顯示／診斷 |
| 順序改變 | 前方角撐消失後，後方同一reference改名即match失敗 | 只要stable identity仍唯一且安全輸入未變，可繼續replay |
| Target Waler／Strut | Provenance保存canonical source identity，顯示編號只用於當次結果存取 | 維持source identity唯一對齊；W／S顯示編號位移不得造成reference轉移或誤判 |
| Confirmation | Key不含member ID，但signature包含完整member資料，純顯示編號位移也會失效 | Key與signature都以穩定工程內容判斷；只有display ID改變不得使既有有效confirmation失效 |
| Preferred target ID | 保存修補後CornerBrace顯示ID，衝突或replay結果不同時安全拒絕 | 維持既有安全guard；本案不把preferred ID改成工程identity，也不在衝突時自動改名 |
| 安全重驗 | ID不符時提前`needs_review`，尚未檢查後續工程輸入 | 對齊後仍重驗reference geometry、connection、eligibility、confirmation與provenance |
| 無法證明同一支 | 零筆match即`needs_review` | 零筆、多筆、identity歧義或安全輸入改變仍使用既有`needs_review`／`disabled`語意 |
| Workflow範圍 | Pause／Resume、source exclusion／restore與recovery都可能重新辨識並重編display ID | 各replay入口共用同一stable-reference contract，不各自用member ID推測 |

## 主要流程

```text
讀取已保存的 CornerBrace repair reference
  -> 以stable source identity／subject key尋找目前eligible reference
  -> 要求恰好一筆match
  -> 重驗角色、來源有效性、reference geometry與唯一Waler／Strut connection
  -> 重驗primary／secondary資格、confirmation與repair provenance
  -> 全部相同才reconstruct並依既有candidate validation replay
  -> 任一缺失、歧義或變更：needs_review／disabled，不替換reference
```

## 不變事項

- 不以幾何鄰近、相同顯示ID或排序位置，把repair reference轉移到另一支角撐。
- 不放寬automatic primary／manual repaired secondary資格、target evidence、template compatibility、candidate ranking、duplicate或connection validation。
- Reference geometry、來源角色、Waler／Strut connection、confirmation內容或provenance改變時，仍不得靜默沿用；只有member display ID改變不視為工程內容改變。
- `CornerBraceRepairSubjectKey.base_geometry_key`的recognized形式仍取完成connection-context refinement後的工程線段，unresolved形式仍取來源本體線段；本案不改成geometry-only或connection-ID matching。
- Preferred CornerBrace ID仍是重播結果與命名衝突的安全guard；衝突時維持`needs_review`，不得改套另一支構件。
- `EXACT_MATCH`與same-fingerprint Resume仍應安全保留有效repair；changed-content compatible recovery仍不得把舊repair效果靜默套用到候選內容。
- Source exclusion／restore仍完整重建並逐筆安全replay；本案不新增跨repair cache、batch操作或persistence migration。

## Why

目前reference exact key把不穩定的顯示member ID當成identity的一部分，使同一支工程reference只因recognition順序改變而被誤判為消失。S14已提供可重現反例，並會影響來源排除／還原、Pause／Resume及recovery中的repair可恢復性，因此需要把顯示名稱與工程identity分離。

## What Changes

- CornerBrace repair reference以stable source identity／subject key作為主要對齊依據；依順序產生的member ID不再是exact match的必要條件。
- Stable match必須唯一；零筆或多筆match不得依幾何距離、display ID或first match自行挑選。
- Match成功後仍依目前result重驗reference geometry、唯一CornerBrace-to-Waler／Strut connection、primary／secondary eligibility、confirmation、provenance及既有candidate validation。
- CornerBrace confirmation維持以source identity作key，並使signature忽略純display member ID重編；若來源、幾何、repair evidence、選擇內容或其他安全輸入改變，confirmation仍必須失效。
- Target Waler／Strut繼續以canonical source identity保存與比對；preferred repaired CornerBrace ID繼續作安全guard，不作reference identity或衝突時的fallback依據。
- Pause／Resume、source exclusion／restore、`EXACT_MATCH` relink與相關repair replay入口共用同一identity語意，避免相同資料在不同workflow得到不同結果。
- Changed-content compatible recovery維持現行安全邊界：不因stable reference可對齊就自動套用舊repair；`requires_review`／`disabled`分類與使用者重新確認要求不變。
- 以S14 fixture補回歸：CB50→CB46等display ID位移但stable identity／geometry／connection未變時，不應僅因member ID不同讓CB66～CB70變成`needs_review`；真正依賴S14而消失或安全輸入改變的reference仍須被拒絕。

## In Scope

- `CornerBraceRepairReference`的identity語意與saved-reference lookup。
- Repair template／primary／secondary reference在replay、Pause／Resume、source exclusion／restore與exact-match relink中的一致對齊。
- 對齊後的reference geometry、connection、eligibility、confirmation與provenance安全重驗。
- CornerBrace confirmation signature對純display member ID重編的穩定化；不改變confirmation的使用者意圖、有效內容與失效邊界。
- S14／D1A與display ID重編、零筆／多筆match、幾何或connection改變的regression tests。

## Out of Scope

- `optimize-dxf-source-exclusion-workflow` 的候選局部validation、per-call planning context、atomic commit、局部刷新與lazy debug；該change不處理本問題。
- 改變CornerBrace自動辨識順序、display member ID編號規則或讓member ID永久化。
- 以geometry-only或proximity把reference轉移到不同source identity。
- 放寬repair eligibility、reference priority、candidate ranking、tolerances、confirmation內容有效性或connection規則；本案只排除confirmation signature中的純display-ID差異。
- 移除preferred repaired CornerBrace ID conflict guard，或在preferred ID衝突時自動重新命名並接受重播。
- 改變changed-content compatible recovery不得靜默套用舊repair的既有contract。
- Project schema migration、Solver、Domain工程規則、Waler或其他構件identity重構。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-corner-brace-repair-tool`：明確規定saved repair reference須以穩定source identity／subject key唯一對齊，顯示member ID不得單獨決定reference是否仍存在；同時保留完整geometry、connection、eligibility、confirmation與provenance重驗。

`paused-dxf-review-source-relink`作為相容性邊界，不修改其changed-content recovery安全語意；後續delta spec不得讓stable matching成為跨內容靜默轉移repair的理由。

## Impact

- **Models／persistence contract**：`dxf_import/models.py` 的`CornerBraceRepairReference` identity／equality使用方式可能調整；優先維持既有serialized payload可讀，不預設schema migration。
- **Repair replay**：`dxf_import/corner_brace_repair.py` 的saved template reconstruction與reference lookup改用stable key後再執行既有安全重驗。
- **Review confirmation**：`dxf_import/review_confirmation.py` 的CornerBrace confirmation signature須canonicalize純display-ID差異；confirmation key仍採source identity，非CornerBrace的既有confirmation語意不在本案中重構。
- **Source lifecycle**：`dxf_import/source_exclusion.py`、Pause／Resume與recovery路徑須共用一致reference matching，不複製不同判斷。
- **Tests**：CornerBrace repair、source exclusion／restore、Pause／Resume、exact-match relink、compatible recovery及S14 fixture regressions。
- **Architecture／Domain／Solver**：預期不改layer responsibility、工程規則或Solver；若後續發現必須修改persistence schema或changed-content recovery contract，應停止並重新評估scope。

## 尚未決定與重新評估條件

- Stable key的最小canonical欄位與legacy payload轉換留待Design依現有serialization與lookup路徑決定；member ID可保留作secondary diagnostic，但不得參與reference exact identity或CornerBrace confirmation的純重編判斷。
- 若source identity無法唯一對齊、同一subject key出現多筆、reference geometry／connection無法可靠比較，必須維持安全拒絕；不得為提高preserved數量擴張成geometry-only matching。
- 若實作需要改變Project schema、changed-content recovery或CornerBrace eligibility，超出本proposal，必須先回報並更新artifacts，不得順帶修改。
