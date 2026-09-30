# dxf-corner-brace-occluded-rail-recognition Specification

## Purpose
定義 CornerBrace 本體 rail 正交間距的正式材料規則，以及 DXF automatic recognition 如何以此排除材料尺度不合理的窄線組合；當一側 rail 因其他斜撐或來源有限幾何在 terminal neighborhood 實際遮蔽而截短時，系統使用保守且可追溯的 fallback 建立唯一候選，若無安全解則保留來源並阻止 DXF Review 完成。

## Requirements

### Requirement: 本體 rail 寬度是正式材料規則與 automatic recognition hard gate

系統 MUST 以 selected RailTracks 的 normalized supporting lines 沿 canonical normal 的法向距離作為 CornerBrace rail separation。正式候選的 separation MUST 嚴格大於 `250.0 mm` 且小於或等於 `600.0 mm`；`250.0 mm` 等號不合格，`600.0 mm` 等號合格。

對每一組有限 Waler／Strut relationship，系統 MUST 以 body midline 與兩構件有限工程線交點間的 expected span 計算 `expected span / rail separation`，且比值 MUST 大於或等於 `3.0`。Observed fragment length、端板長度、finite endpoint overhang 或通用 segment separation MUST NOT 取代上述尺度。

#### Scenario: 正常 300 mm 角撐通過材料尺度
- **WHEN** selected supporting lines 的法向間距為 `300 mm`，且某一 relationship 的 expected slenderness 及其他 hard gates 合格
- **THEN** 系統 SHALL 保留該 body 與 relationship assessment

#### Scenario: 250 mm 等號邊界
- **WHEN** rail separation 恰好為 `250.0 mm`
- **THEN** 系統 MUST 拒絕該 body hypothesis

#### Scenario: 600 mm 等號邊界
- **WHEN** rail separation 恰好為 `600.0 mm`，且其他 body geometry gates 合格
- **THEN** 系統 SHALL 允許該 body hypothesis 繼續評估 relationships

#### Scenario: 寬度超過上限
- **WHEN** rail separation 大於 `600.0 mm`
- **THEN** 系統 MUST 拒絕該 body hypothesis

#### Scenario: 長寬比 3 的等號邊界
- **WHEN** 某一 relationship 的 expected span／rail separation 恰好為 `3.0`
- **THEN** 該 relationship SHALL 通過 slenderness gate

#### Scenario: 遮擋殘段不得縮短 expected length
- **WHEN** selected rails 只留下部分 fragments
- **THEN** 系統 MUST 仍以該 relationship 的有限 Waler–Strut expected span 計算 slenderness 與 coverage
- **AND** MUST NOT 以 observed longest fragment 縮短 denominator

#### Scenario: 端板或斜切端不得改寫寬度
- **WHEN** 端板長度、斜切 rail finite endpoints 或通用 segment distance 與 supporting-line separation 不同
- **THEN** 系統 SHALL 只使用 normalized supporting lines 的法向間距作為 rail separation

#### Scenario: 正常約 300 mm rail pair
- **WHEN** normalized supporting lines 的法向間距約為 `300 mm`
- **THEN** 系統 SHALL 以該間距作為 body separation，不得以 finite segment endpoint 平均替代

#### Scenario: 內部窄線組合
- **WHEN** source 內部線形成 separation `<=250 mm` 的 pair
- **THEN** 系統 MUST 依材料 hard gate 拒絕該 body hypothesis

#### Scenario: 端板平均長度與 rail 間距不同
- **WHEN** terminal plates 平均長度與 selected RailTracks separation 不同
- **THEN** source width SHALL 使用 rail separation

#### Scenario: 斜切 rail 的有限端部不得增加正式寬度
- **WHEN** 斜切或梯形 rails 的有限 endpoints 使通用 segment distance 大於 supporting-line separation
- **THEN** 系統 SHALL 保持 supporting-line separation 為正式寬度

### Requirement: 完整候選必須全部列舉並優先於遮蔽 fallback

系統 MUST 先由 exact source finite fragments 建立無方向性的 canonical direction，並由該方向產生 deterministic canonical normal。每個方向差 `<=2°` 的 fragment SHALL 具有 normal offset；同一 RailTrack hypothesis MUST 滿足 `max(normal_offsets)-min(normal_offsets) <=25.0 mm`。至少一條長度 `>=100.0 mm` 的 fragment 才可建立方向，較短 fragment 只能加入已成立的方向 hypothesis。

系統 MUST 全列舉所有非等價 RailTrack hypotheses，不得使用 first seed、first-fit、entity order、fragment iteration order、line start／end 或第一條 supporting line 作為隱性 winner。每個 track 將 fragments 投影至自己的 normalized supporting line，合併 overlap 與 `<=50.0 mm` seams；union length MUST NOT 重複計算。Track pair 亦 MUST 全列舉，不得先套用固定 `80%` finite projection overlap、longest-first 或端板必要條件。

系統 MUST 建立 relationship-independent `BodyGeometryEvidence`，且只保存 exact source identity、fragments、RailTracks、selected pair、normalized supporting lines、canonical direction／normal、midline、separation、merged source intervals 與 terminal-plate evidence。Expected span、slenderness、coverage、gaps、occluders、extension、complete／occluded classification 及 hard-valid outcome MUST NOT 保存於 body evidence。

每個 body 對每組 active finite Waler／Strut identities MUST 建立獨立 `BodyRelationshipAssessment`。Complete／occluded classification 只可在 assessment 完成逐軌 coverage、extension 與 gap validation 後產生。端板可作 terminal evidence 或在唯一實際連接某 pair 時協助消歧，但零、一或兩端板均不得單獨改變 eligibility。

#### Scenario: 零端板、單端板與雙端板使用相同 body 類型
- **WHEN** 同等 selected RailTracks 分別具有零、一或兩片 terminal plates
- **THEN** 系統 SHALL 以同一 `BodyGeometryEvidence` 契約表示本體
- **AND** MUST NOT 只因端板數量決定 complete／occluded 或 hard-valid

#### Scenario: 50 mm seam 合併
- **WHEN** 同一 track 上相鄰 intervals 的 gap 恰好為 `50.0 mm`
- **THEN** 系統 SHALL 合併該 seam
- **AND** SHALL NOT 要求 occluder evidence

#### Scenario: 100 mm direction seed 邊界
- **WHEN** fragment 長度恰好為 `100.0 mm`
- **THEN** 該 fragment MAY 建立 direction hypothesis
- **AND** 較短 fragment MUST NOT 單獨建立方向

#### Scenario: Normal offsets 0、20、40 mm
- **WHEN** 同方向 fragments 的 normal offsets 為 `0`、`20`、`40 mm`
- **THEN** 系統 SHALL 保留 `{0,20}` 與 `{20,40}` 等所有合法非等價 hypotheses
- **AND** MUST NOT 將 spread `40 mm` 的 `{0,20,40}` 合併為同一 track

#### Scenario: Fragment permutation 不影響結果
- **WHEN** 相同 fragments 以任意 entity／iteration order 輸入
- **THEN** 系統 SHALL 產生相同 normalized RailTrack hypotheses、body outcomes 與 diagnostics

#### Scenario: Line start end 反轉不影響結果
- **WHEN** 任一 fragment 的 start／end 被反轉
- **THEN** canonical direction、normal、track identity、body 與 diagnostics SHALL 維持幾何等價

#### Scenario: 無法唯一分配 fragment
- **WHEN** shared fragment 支持多個非等價 track／body hypotheses，且後續 evidence 無法唯一消歧
- **THEN** 系統 MUST 保留 competing hypotheses 並回報 body ambiguity
- **AND** MUST NOT 使用 first-fit 或輸入順序選擇

#### Scenario: S7 類低投影重疊仍須評估
- **WHEN** 合法 track pair 的原始有限單段 projection overlap 低於舊 `80%`，但 body 與某 relationship 的正式 hard gates 全部合格
- **THEN** 系統 MUST NOT 因舊 projection gate 提前淘汰

#### Scenario: 完整列舉後存在可建立集合
- **WHEN** 全部 track-pair hypotheses 完成列舉、等價合併與 conflict evaluation，且存在唯一合法 body set
- **THEN** 系統 SHALL 使用該 set 繼續建立 relationship assessments

#### Scenario: 完整斜切或梯形 CornerBrace body
- **WHEN** 兩條 selected RailTracks 形成合法斜切或梯形 body geometry
- **THEN** 系統 SHALL 保存相同 `BodyGeometryEvidence` 欄位
- **AND** complete／occluded classification SHALL 留待各 relationship assessment 決定

#### Scenario: 任意封閉梯形不足以成立
- **WHEN** 封閉形狀無法唯一提供合格 RailTracks、separation與midline
- **THEN** 系統 MUST NOT 只因封閉拓撲建立 body

#### Scenario: 多個完整候選安全可分割
- **WHEN** 多個 body hypotheses 不共用 fragments／tracks 且具有唯一可分割集合
- **THEN** 系統 MAY 建立多份獨立 body evidence

#### Scenario: 完整候選競爭相同 evidence
- **WHEN** 多個非等價 bodies 競爭相同 fragments或tracks且無法消歧
- **THEN** 系統 MUST 回報 body ambiguity

#### Scenario: 只有窄線完整候選
- **WHEN** 所有候選 separation 都不大於 `250 mm`
- **THEN** 系統 MUST 保持 body零解，不得進入relationship assessment

### Requirement: 遮蔽 rail fallback 必須由保守證據共同成立

每個 `BodyRelationshipAssessment` MUST 以自己的 expected span 分別計算兩條 selected rails 的 merged interval union coverage。Complete 與 occluded 都要求每條 rail coverage `>=50%`，且 Waler 端與 Strut 端 outward extension 各自 `<=600.0 mm`；coverage 與 extension MUST 同時成立且不得互相替代。

通過共同 hard gates 後：沒有需要遮擋證據的 `>50.0 mm` internal／terminal gap 時，assessment SHALL 分類為 `complete`；存在任一 `>50.0 mm` gap 時，assessment SHALL 分類為 `occluded`，且每個 gap MUST 個別具有 finite occluder evidence。任一軌 coverage 不足、任一端 extension 超限或任一大 gap 無法解釋，該 assessment MUST hard-invalid。

Occluder 只可來自已辨識 Brace／Strut／Waler／Column／Beam 的 finite source geometry，或同一 exact source 的其他 finite lines。正交／斜交 occluder MUST 進入 `25 mm` gap corridor 且有限投影進入 gap interval；方向差 `<=2°` 的 near-parallel occluder另 MUST 覆蓋該 gap 至少 `50%`。文字、尺寸、HATCH pattern、draw metadata、顏色、draw order、無限延長線與只在其他位置相交的線 MUST NOT 成為 evidence。

#### Scenario: Complete 每軌 coverage 恰好 50%
- **WHEN** relationship 沒有 `>50 mm` gap，兩條 rail coverage 都恰好 `50%`，且其他 hard gates 合格
- **THEN** assessment SHALL 可分類為 `complete` 並通過 coverage gate

#### Scenario: Occluded 每軌 coverage 恰好 50%
- **WHEN** relationship 存在已由 finite occluders 個別解釋的大 gap，且兩條 rail coverage 都恰好 `50%`
- **THEN** assessment SHALL 可分類為 `occluded` 並通過 coverage gate

#### Scenario: 任一 rail coverage 低於 50%
- **WHEN** 任一 selected rail 對該 relationship 的 coverage 低於 `50%`
- **THEN** assessment MUST hard-invalid
- **AND** 另一軌較高 coverage、端板或合法 extension MUST NOT 補償

#### Scenario: 同一 body 對不同 relationships 分開計算
- **WHEN** 同一 `BodyGeometryEvidence` 對 relationship A 的每軌 coverage 為 `60%`，對 relationship B 為 `45%`
- **THEN** 系統 SHALL 分別保存兩個 assessments
- **AND** A MAY 通過 coverage，B MUST 因 coverage 不足被拒絕

#### Scenario: 100 mm fragment不足以建立正式角撐
- **WHEN** fragment 足以建立方向但任一 rail 對 expected span 的 coverage 低於 `50%`
- **THEN** 系統 MUST NOT 建立正式 CornerBrace

#### Scenario: 兩端 extension 各 600 但 coverage 約 43.4%
- **WHEN** expected span 為約 `2121.320 mm`，兩端 extension 各為 `600 mm`，但任一 rail coverage 約為 `43.4%`
- **THEN** assessment MUST 因 coverage 不足被拒絕

#### Scenario: Coverage 通過但單端 extension 800 mm
- **WHEN** 兩條 rail coverage 都通過，但任一端 outward extension 為 `800 mm`
- **THEN** assessment MUST 因 extension 超限被拒絕

#### Scenario: Coverage 通過且存在大 gap
- **WHEN** 兩條 rail coverage 都通過，但存在任一 `>50 mm` internal／terminal gap
- **THEN** assessment MUST 進入 `occluded` 分類並逐 gap 驗證
- **AND** MUST NOT 分類為 `complete`

#### Scenario: 每個 gap 各自需要 evidence
- **WHEN** assessment 有兩個大 gap，而 finite occluder 只解釋其中一個
- **THEN** assessment MUST hard-invalid

#### Scenario: Near-parallel occluder 等號邊界
- **WHEN** near-parallel finite occluder 進入 corridor 且與 gap overlap 恰好為 `50%`
- **THEN** 該 occluder MAY 解釋該 gap

#### Scenario: 無端板但所有 hard gates 合格
- **WHEN** body 沒有 terminal plate，但兩軌 coverage、extension、slenderness及所有大 gap evidence 均合格
- **THEN** 系統 MUST NOT 只因缺少端板拒絕 assessment

#### Scenario: Y05 CB58 類一側 rail 被遮蔽
- **WHEN** 一側 rail 有大 gap，但兩軌 coverage、兩端 extension與逐gap finite occluder evidence均合格
- **THEN** assessment SHALL 可分類為 `occluded`

#### Scenario: 短 rail 比例低於 75%
- **WHEN** observed單段短長比低於舊 `75%`，但兩軌對expected span的union coverage均達 `50%`且其他gates合格
- **THEN** 系統 MUST NOT 使用舊單段比例拒絕assessment

#### Scenario: 缺少遮蔽 corridor evidence
- **WHEN** 任一大gap沒有finite occluder進入其25 mm corridor
- **THEN** assessment MUST hard-invalid

#### Scenario: 同一圖塊內的鄰近線不足以證明遮蔽
- **WHEN** same-source finite line只在gap附近但未通過corridor與finite projection條件
- **THEN** 該線 MUST NOT 解釋gap

#### Scenario: Rail 其他位置的交點不能解釋 terminal 中斷
- **WHEN** occluder與rail相交的位置不在該terminal gap interval
- **THEN** 系統 MUST NOT 將該交點指派給此gap

#### Scenario: 兩端板皆不存在
- **WHEN** occluded assessment沒有任何terminal plate但全部正式hard gates合格
- **THEN** 系統 SHALL 允許該assessment成立

#### Scenario: 中線不能建立有限交點
- **WHEN** body midline無法同時與候選Waler內線及Strut中心線建立有限交點
- **THEN** 該relationship assessment MUST hard-invalid

### Requirement: 無唯一合法解必須阻止 DXF Review 完成

系統 MUST 先解決 body geometry，再解決 relationships。Body 零解或多解時 MUST 保持 unresolved，且 MUST NOT 建立 `body_relationship_selection` repair candidates。Body 唯一時，系統 SHALL 只計算該 body 的 hard-valid `BodyRelationshipAssessment` 數量：一組時 automatic 建立 connection；零組時 relationship unresolved；多組時 automatic unresolved，並保留所有 competing source identities供 Preview。

幾何重合但 source identity 不同的 active Walers MUST 視為不同 relationships，不得建立 canonical Waler、以 nearest／first-match 選擇，或因輸入順序改變結果。Source exclusion／restore 後 MUST 依 current active facts 完整重算。

#### Scenario: Body 零解或多解
- **WHEN** exact source 無合法 body，或仍有多個非等價 body solutions
- **THEN** 系統 SHALL 建立 completion-blocking unresolved diagnostic
- **AND** MUST NOT 提供 relationship-selection repair

#### Scenario: Body 唯一且一組 hard-valid relationship
- **WHEN** unique body 只有一組 hard-valid assessment
- **THEN** 系統 SHALL automatic 建立該 Waler／Strut connection

#### Scenario: Body 唯一且多組 hard-valid relationships
- **WHEN** unique body 有兩組以上 hard-valid assessments
- **THEN** automatic recognition MUST 保持 unresolved
- **AND** Review SHALL 保存每組 structured relationship candidate 供使用者 Preview

#### Scenario: 幾何重合 Waler identities
- **WHEN** 兩個 active Waler sources 的有限工程線幾何重合，且各自形成 hard-valid assessment
- **THEN** 系統 MUST 視為兩組 relationships
- **AND** MUST NOT 合併 identity 或自動選擇

#### Scenario: 排除其中一個 Waler 後重算
- **WHEN** 使用者排除 competing Waler 中的一個並重新辨識，只剩一組 hard-valid assessment
- **THEN** 系統 SHALL 依 current active facts automatic 建立唯一 connection
- **AND** MUST NOT 重播先前 Preview 暫時選擇

#### Scenario: Unresolved 不阻止其他來源處理但阻止完成
- **WHEN** 一個 CornerBrace source unresolved
- **THEN** 系統 MAY 繼續辨識與檢核其他來源
- **AND** DXF Review MUST 在該來源未排除或合法解決前禁止完成

#### Scenario: 所有候選皆不合法
- **WHEN** source的所有body或relationship hypotheses均未通過hard gates
- **THEN** 系統 SHALL 保留structured rejection reasons並保持unresolved

#### Scenario: 多個非等價遮蔽候選
- **WHEN** 多個非等價occluded body hypotheses競爭相同evidence且無法唯一消歧
- **THEN** 系統 MUST 回報body ambiguity，不得依分數或順序選擇

#### Scenario: Unresolved CornerBrace 不阻止其他構件繼續處理
- **WHEN** CornerBrace unresolved
- **THEN** operation SHALL 繼續處理其他獨立來源

#### Scenario: Unresolved CornerBrace blocks Review completion
- **WHEN** unresolved source尚未被排除或合法修正
- **THEN** DXF Review MUST NOT 完成

#### Scenario: 重複重合圍令使角撐關聯保持 unresolved
- **WHEN** unique body對兩個幾何重合但identity不同的Walers均有hard-valid assessment
- **THEN** automatic connection SHALL 保持unresolved

#### Scenario: 排除重複圍令後重新辨識
- **WHEN** 使用者排除其中一個重複Waler並重新辨識
- **THEN** 系統 SHALL 只依剩餘active facts建立assessment

#### Scenario: 重複圍令輸入順序不影響 ambiguity
- **WHEN** competing Waler sources的輸入順序互換
- **THEN** relationship ambiguity與candidate identities SHALL 維持等價

#### Scenario: 單一圍令關聯可完成 connection
- **WHEN** unique body只剩一組hard-valid finite Waler／Strut assessment
- **THEN** 系統 SHALL automatic建立該connection

### Requirement: 遮蔽辨識不得建立第二份工程 truth

Recognition、diagnostics、repair、candidate points 與 Presentation MUST 共用同一 `BodyGeometryEvidence` 與其 `BodyRelationshipAssessment` records。下游 MUST NOT 重新列舉 rails、改選 tracks、重算另一份 body、把 assessment classification 寫回 body，或解析格式化 message 取得工程資料。

#### Scenario: 下游重用同一 body geometry
- **WHEN** recognition 已選出唯一 body geometry
- **THEN** centerline、width、diagnostics 與 repair SHALL 使用同一 selected pair、midline 與 source intervals

#### Scenario: Relationship 結果不污染 body
- **WHEN** 同一 body 的不同 assessments 具有不同 coverage、gaps、classification 或 hard-valid outcome
- **THEN** `BodyGeometryEvidence` SHALL 維持不變
- **AND** 各 assessment SHALL 保存自己的結果

#### Scenario: 下游不得解析 message
- **WHEN** Review 或 repair 需要 body／relationship evidence
- **THEN** 系統 SHALL 使用 structured data
- **AND** MUST NOT 解析 diagnostic message 文字

#### Scenario: 下游重用同一 selected pair
- **WHEN** centerline、diagnostics、repair或candidate points需要本體軸線
- **THEN** 下游 SHALL 重用 `BodyGeometryEvidence` 的selected pair與midline
- **AND** MUST NOT 重新選擇finite LINE pair
