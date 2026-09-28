# dxf-corner-brace-repair-tool Specification

## Purpose
提供 DXF Review 中受 BIM 遮蔽或中心軸誤判之角撐的保守人工修補流程，在不放寬自動辨識的前提下，以目標殘線、既有工程構件與可追溯參考角撐提出可預覽候選，並只在使用者明確採用後更新正式 Review state。

## Requirements

### Requirement: 修補工具只處理明確選取的角撐 subject

系統 SHALL 在 STEP4 修改工具中，對使用者目前選取的正式 CornerBrace 或狀態為 `unresolved`、角色為 `corner_brace` 且具有可識別 source identity 的來源提供角撐修補入口。一次修補 MUST 只針對一個明確 subject；工具不得掃描後自動修改其他角撐。

#### Scenario: 修補已辨識但軸線錯誤的角撐
- **WHEN** 使用者選取一支正式 CornerBrace 並啟動修補工具
- **THEN** 系統以該 CornerBrace 的 exact source identity 與來源幾何建立修補 session
- **AND** 不修改其他正式 CornerBrace

#### Scenario: 修補尚未形成正式角撐的來源
- **WHEN** 使用者選取角色為 `corner_brace`、具有 exact source identity 的 unresolved Review subject 並啟動修補工具
- **THEN** 系統可為該來源規劃建立正式 CornerBrace 的候選
- **AND** 在使用者採用前不得先建立正式工程構件

#### Scenario: 非角撐或缺少安全來源 identity
- **WHEN** 選取項目不是 CornerBrace subject，或無法取得可安全識別的角撐來源
- **THEN** 系統 SHALL 不啟用角撐修補
- **AND** SHALL 說明此項目不符合修補前提

### Requirement: 目標來源幾何是修補必要證據

系統 MUST 從目標 subject 自己的 DXF source geometry 取得可用殘線，作為修補位置與方向的必要證據。附近已成功角撐、Waler 或 Strut 不得在完全沒有目標來源幾何支持時單獨創造 CornerBrace。修補 eligibility 與幾何比較 SHALL 使用既有具名 `GeometryTolerances`；不得加入固定材料寬度或未命名距離門檻。

#### Scenario: 殘線可支持候選方向
- **WHEN** 目標來源保留可與某一候選工程軸一致的局部線段證據
- **THEN** 系統可將該證據納入修補候選的方向、位置與符合度判定

#### Scenario: 參考角撐存在但目標沒有可用殘線
- **WHEN** 附近存在已成功角撐，但目標來源沒有可用幾何可支持其位置或方向
- **THEN** 系統 MUST 拒絕產生可採用的正式修補候選
- **AND** MUST NOT 只複製參考角撐或依對稱位置創造構件

#### Scenario: 多條殘線支持非等價軸
- **WHEN** 目標來源中的殘線在既有容差下支持多條非等價工程軸
- **THEN** 系統 MUST 保留多解狀態
- **AND** MUST NOT 依 entity order、handle 大小或 first match 任意選定工程軸

### Requirement: 參考角撐必須分級並阻止推測鏈

系統 MUST 將 reference CornerBrace 分為 `automatic primary` 與 `manual repaired secondary`。`automatic primary` MUST 來自 automatic recognition、來源目前有效，且具有唯一有效的 CornerBrace-to-Waler／Strut 關聯。`manual repaired secondary` MUST 已由使用者明確採用、具有完整 repair provenance、目前 Review confirmation 仍有效、來源目前有效、不是 `requires_review`，且仍具有唯一有效的 CornerBrace-to-Waler／Strut 關聯。

每一個可採用 repair candidate MUST 至少由一支 `automatic primary` 支持。`manual repaired secondary` 只能補充一致性 evidence，不得單獨使候選成立；系統不得遞迴展開 secondary reference 自己曾使用的 repaired references，也不得讓 repaired CB1 → repaired CB2 → repaired CB3 形成無 automatic primary 的推測鏈。Reference 可來自同一 Strut、另一側或鄰近 Strut，不得限制為同一支 Strut 的另一側。

#### Scenario: Automatic recognized CornerBrace 成為 primary reference
- **WHEN** 一支 automatic recognized CornerBrace 的來源有效，且其 CornerBraceConnection 唯一有效
- **THEN** 系統可將它列為 `automatic primary` reference

#### Scenario: 已確認 repaired CornerBrace 成為 secondary reference
- **WHEN** 一支 manual repaired CornerBrace 已明確採用、repair provenance 完整、目前 confirmation 有效、來源有效、不是 `requires_review`，且 connection 仍唯一有效
- **THEN** 系統可將它列為 `manual repaired secondary` reference
- **AND** 它只能補充同一候選已有的 automatic primary evidence

#### Scenario: 只有 repaired references
- **WHEN** 某個 repair hypothesis 只有一支或多支 manual repaired CornerBrace 支持，沒有任何 automatic primary
- **THEN** 該 hypothesis MUST NOT 成為可 Apply candidate
- **AND** 系統 MUST NOT 以 repaired reference chain 補足缺少的 primary evidence

#### Scenario: Repaired reference 不再可信
- **WHEN** manual repaired CornerBrace 尚未確認、repair provenance 不完整、connection 無效、來源失效或狀態為 `requires_review`
- **THEN** 系統 MUST NOT 將它納入 reference evidence

#### Scenario: 鄰近支撐提供有效參考
- **WHEN** 目標同支撐的另一側角撐也被遮蔽，但鄰近支撐存在合格的 automatic primary CornerBrace
- **THEN** 系統可使用該鄰近角撐支持修補候選
- **AND** 正式端點仍須由目標構件幾何求得

#### Scenario: 參考角撐本身關聯無效
- **WHEN** 某一附近 CornerBrace 沒有唯一有效的 Waler／Strut 關聯，或具有阻斷其工程幾何可信度的問題
- **THEN** 系統 MUST NOT 將該 CornerBrace 當作修補參考

#### Scenario: 沒有合格參考角撐
- **WHEN** 目標附近沒有任何合格的 automatic primary CornerBrace 可供參考
- **THEN** 系統 MUST 拒絕產生可採用的修補候選
- **AND** SHALL 保留原正式幾何或 unresolved 狀態

#### Scenario: 多筆參考不一致
- **WHEN** 多支合格參考角撐對目標候選提供互相衝突且無法唯一判定的先驗
- **THEN** 系統 SHALL 將結果保持為多解或證據不足
- **AND** SHALL NOT 只因其中一支距離最近就自動採用

### Requirement: Reference 幾何只能作為一致性檢核

Reference CornerBrace 的 fixed length、side、angle relation 與 topology MUST 只作為 repair hypothesis 的 consistency validation evidence。Repaired CornerBrace 的正式端點 MUST 完全由 candidate axis 與 target finite Waler inner line、target finite Strut centreline 的交點決定。系統 MUST NOT 複製 reference coordinates、以 reference fixed length 改寫或移動目標交點、沿 candidate axis 截短／延長正式端點，或強迫 target 採用 reference length。

#### Scenario: Reference length 與目標交點長度一致
- **WHEN** candidate axis 的兩個 target finite intersections 形成的長度通過 reference fixed-length consistency validation
- **THEN** 系統 SHALL 保留這兩個 target intersections 作為 candidate endpoints
- **AND** SHALL 由兩交點距離計算 target fixed length

#### Scenario: Reference length 與目標交點長度不一致
- **WHEN** candidate axis 的 target finite intersections 所得長度未通過 reference fixed-length consistency validation
- **THEN** 該 hypothesis MUST 被拒絕
- **AND** 系統 MUST NOT 移動任一 target intersection 以配合 reference length

#### Scenario: Reference side 或 topology 不一致
- **WHEN** target hypothesis 與合格 reference 的 side 或 topology evidence 不相容
- **THEN** 系統 SHALL 將該 hypothesis 判為不合格
- **AND** SHALL NOT 以複製 reference absolute geometry 的方式產生另一個 candidate

### Requirement: 每個修補候選必須具有有效的目標工程接點

每一個可預覽的修補候選 MUST 明確綁定一支目標 Waler 與一支目標 Strut，並由候選軸與該 Waler 有限內線、該 Strut 有限中心線的有效交點產生兩個正式端點。候選 MUST 通過既有最小長度、有限線段與幾何有效性檢核，以及 automatic primary reference 的一致性檢核；不得使用 Waler 或 Strut 的無限延長線接點，也不得修改目標 Waler／Strut 幾何或正式端點以配合 reference。

#### Scenario: 目標 Waler 與 Strut 接點有效
- **WHEN** 一條受目標殘線與參考證據支持的候選軸，能與明確目標 Waler 內線及 Strut 中心線形成有效有限交點
- **THEN** 系統 SHALL 以這兩個交點建立候選正式工程線
- **AND** SHALL 在候選中標示目標 Waler、Strut 與參考角撐

#### Scenario: 任一接點不在有限構件上
- **WHEN** 候選軸只能與 Waler 或 Strut 的無限延長線相交，或其中一端沒有有效有限交點
- **THEN** 該候選 MUST NOT 成為可採用修補

#### Scenario: 多組 Waler 或 Strut 關係皆可成立
- **WHEN** 目標證據可形成多個非等價且各自有效的 Waler／Strut 修補候選
- **THEN** 系統 SHALL 將各候選分開呈現
- **AND** MUST NOT 在使用者選擇前把其中一組當成正式關聯

### Requirement: 修補必須先預覽再明確採用

Repair planner MAY 保留未通過 hard eligibility 的 internal hypotheses 以建立拒絕 diagnostics，但只有同時具備 target source identity、target residual geometry、可靠 residual direction、唯一有效 candidate relationship、至少一支 automatic primary reference、有效 finite intersections，並通過 reference consistency 與既有 CornerBrace validation 的 hypotheses，才可成為 Preview 中可選取、可 Apply 的 candidates。

系統 SHALL 在修改 live Review state 前顯示 eligible candidate 的工程線、目標來源殘線、目標 Waler／Strut、primary／secondary references 及足以區分候選的診斷資訊。即使只有一個 eligible candidate，也 MUST 由使用者明確採用；取消或關閉預覽 MUST 保持零副作用。多個非等價但各自通過全部 hard eligibility 的 candidates 存在時，系統 SHALL 要求使用者明確選擇其中一個，不得以分數自動提交。Proximity 只能排序已合法 candidates 的顯示順序，不得使 hypothesis 合法，也不得自動選 winner。

#### Scenario: 唯一候選仍需確認
- **WHEN** 系統只建立一個合法修補候選
- **THEN** 系統先顯示該候選預覽
- **AND** 只有使用者明確採用後才可修改正式 Review state

#### Scenario: 使用者選擇多個候選之一
- **WHEN** 系統顯示多個合法但非等價的修補候選，且使用者選取其中一個並確認
- **THEN** 系統只採用被選取的候選
- **AND** 不採用其他候選的幾何或關聯

#### Scenario: 使用者取消預覽
- **WHEN** 使用者取消或關閉修補預覽
- **THEN** 正式 CornerBrace、unresolved subject、關聯、validation、confirmation 與 dirty Review state SHALL 維持提交前狀態

#### Scenario: 沒有合法候選
- **WHEN** 目標證據不足、沒有有效工程接點或所有候選均未通過檢核
- **THEN** 系統 SHALL 顯示不可安全修補的原因
- **AND** SHALL 保留原正式幾何或 unresolved 狀態

#### Scenario: 多個 hypotheses 都缺少必要 evidence
- **WHEN** planner 找到多個幾何猜測，但它們缺少 target residual、automatic primary、唯一有限關係或其他 hard eligibility
- **THEN** 系統 SHALL 將 eligible candidate count 視為零並顯示拒絕原因
- **AND** MUST NOT 將這些 hypotheses 包裝成可選取或可 Apply candidates

#### Scenario: Proximity 只排序合法候選
- **WHEN** 多個 candidates 已各自通過全部 hard eligibility
- **THEN** 系統 MAY 依 proximity 排列顯示順序
- **AND** MUST NOT 因 proximity 自動採用或隱藏其他非等價合法候選

### Requirement: Unresolved 來源建立正式 CornerBrace 必須通過額外門檻

系統 MUST 區分「replace existing recognized CornerBrace」與「create formal CornerBrace from unresolved source」。Replace path SHALL 更新已存在且 subject identity 唯一的 CornerBrace。Create path 只有在 unresolved subject 具備 exact `corner_brace` role／source identity、target residual geometry、可靠 residual direction 或有限且可逐一檢核的 hypotheses、全體 hard-eligible hypotheses 指向同一組唯一 finite target Waler／Strut relationship、至少一支有效 automatic primary reference、明確使用者 adoption，且建立後通過全部既有 CornerBrace validation 時才可提交。

只有 layer classification、INSERT identity、附近構件或 references，而沒有 target residual geometry，不足以建立 formal CornerBrace。Create path 若存在多組非等價 target Waler／Strut relationships，MUST 拒絕建立，不得把關係選擇責任移交給 Apply；在唯一 relationship 內若仍有多個各自完整的 axis candidates，則可依 Preview requirement 讓使用者選擇。

#### Scenario: Replace existing recognized CornerBrace
- **WHEN** target 是具有唯一 repair subject identity 的 existing recognized CornerBrace，且使用者採用一個 eligible repair candidate
- **THEN** 系統 SHALL 更新該 CornerBrace，而不是新增第二支 formal CornerBrace

#### Scenario: Unresolved source 通過完整 create eligibility
- **WHEN** unresolved `corner_brace` subject 具有 exact identity、target residual、可靠方向 evidence、唯一 finite Waler／Strut relationship、automatic primary reference，且使用者採用後全部既有 CornerBrace validation 通過
- **THEN** 系統可建立一支 source-traceable formal CornerBrace

#### Scenario: 只有 layer 或 nearby evidence
- **WHEN** unresolved subject 只有正確 layer、INSERT、附近 Waler／Strut 或 reference CornerBrace，但沒有 target residual geometry
- **THEN** 系統 MUST NOT 建立 formal CornerBrace

#### Scenario: Unresolved source 有多組 target relationships
- **WHEN** unresolved source 的 hard-eligible hypotheses 指向多組非等價 target Waler／Strut relationships
- **THEN** 系統 MUST 拒絕 create path並顯示 relationship ambiguity
- **AND** MUST NOT 將這些關係包裝成可 Apply candidates

#### Scenario: 建立後 validation 未全部通過
- **WHEN** selected unresolved repair 在 staged formal CornerBrace 建立後有任一既有 CornerBrace validation 未通過
- **THEN** 系統 MUST 拒絕提交並保留原 unresolved state

### Requirement: 採用修補必須原子重建相關 Review 資料

採用修補 SHALL 是 `DXFReviewWorkflow` 擁有的單一狀態轉換。系統 MUST 更新既有 CornerBrace，或為 unresolved target 建立一支具有唯一顯示 ID 的正式 CornerBrace；同一提交 MUST 保留目標 source handles／layer／entity types，標記人工修補 selection source 與參考 provenance，並重建 CornerBraceConnection、Strut 角撐衍生長度、candidate points、problems、ReviewItems 及 validation。任一步驟失敗 MUST 回復提交前完整 live Review state，不得留下部分更新。

#### Scenario: 更新已辨識 CornerBrace
- **WHEN** 使用者採用已辨識 CornerBrace 的修補候選
- **THEN** 系統 SHALL 以修補工程線更新同一來源的正式 CornerBrace
- **AND** SHALL 重新建立其角撐關聯與相關 Strut 衍生長度

#### Scenario: unresolved 來源成為正式 CornerBrace
- **WHEN** unresolved 角撐來源通過 create eligibility，且使用者採用合法修補候選
- **THEN** 系統 SHALL 建立一支來源可追溯的正式 CornerBrace
- **AND** 原 unresolved subject SHALL 由重新建立的 ReviewItems 取代，而不是與正式構件形成兩份 active truth

#### Scenario: 修補會使既有確認失效
- **WHEN** 修補改變被確認 subject 或其相關工程狀態的 current-state signature
- **THEN** 系統 MUST 依既有 confirmation validation 移除失效確認
- **AND** SHALL 回報被連帶失效的確認

#### Scenario: 重建中發生錯誤
- **WHEN** 正式角撐建立、關聯、衍生長度或 validation 重建任一步驟失敗
- **THEN** 系統 MUST 回復修補前的完整 world result、projected result、ReviewItems、confirmations、candidate store 與 revision 狀態

### Requirement: 修補決策必須可追溯且安全重播

已採用修補 MUST 記錄 exact target source identity、採用的 world engineering line、目標 Waler／Strut、selection source、automatic primary reference identities，以及選用的 manual repaired secondary identities。相同 DXF fingerprint 的 Pause／Resume 重新辨識只有在 exact target source identity 仍唯一存在、至少一支記錄的 automatic primary 仍符合 primary eligibility、所有被採用的 secondary 仍符合 secondary eligibility，且修補結果仍通過現行檢核時才可重播；否則 MUST 保留 candidate-based state 並要求重新修補，不得套用到其他來源或改找新的 references。

#### Scenario: 相同來源安全重播
- **WHEN** paused Review 以相同 source fingerprint 恢復，exact target source identity 唯一存在，且保存的修補工程線與目標關係仍有效
- **THEN** 系統 SHALL 恢復修補後的正式 CornerBrace 與重新推導的衍生資料

#### Scenario: exact target source identity 不再唯一
- **WHEN** 恢復 Review 時找不到 exact target source identity，或同一 identity 無法唯一定位修補 subject
- **THEN** 系統 MUST NOT 把修補套用到其他 CornerBrace
- **AND** SHALL 將該修補標示為需要重新處理或已停用

#### Scenario: 參考角撐後續改變
- **WHEN** exact target source identity 仍有效，但保存修補所記錄的參考角撐已改變或不存在
- **THEN** 系統 SHALL 以保存的人工採用工程線及目前目標工程關係重新驗證，不得重新猜測另一支參考角撐
- **AND** 驗證失敗時 SHALL 要求重新修補

#### Scenario: Resume 後只剩 repaired references
- **WHEN** 保存修補的 secondary references 仍有效，但所有記錄的 automatic primary references 已失效或不存在
- **THEN** 系統 MUST NOT replay 該修補
- **AND** SHALL 要求使用者重新檢查，不得以 secondary reference chain 取代 primary evidence

### Requirement: 自動辨識與非目標系統維持既有行為

此工具 MUST NOT 放寬 CornerBrace automatic recognition、改變既有可靠中心軸辨識結果、改寫一般 Brace／Strut／Waler recognition，或修改 Solver 與 Project schema。未啟動修補及未採用候選時，現行 DXF Import 結果 MUST 保持不變。

#### Scenario: 可靠角撐不使用修補工具
- **WHEN** CornerBrace 已由現行 automatic recognition 正確建立，且使用者未啟動修補
- **THEN** 系統 SHALL 維持現行辨識、端點延伸與下游關聯結果

#### Scenario: 修補不進入 Project schema
- **WHEN** 修補後的 DXF Review 完成匯入
- **THEN** Project row boundary SHALL 維持既有正式 Waler、Strut 與 Brace contract
- **AND** CornerBrace 詳細資料與修補 provenance SHALL 留在 DXF Review state
