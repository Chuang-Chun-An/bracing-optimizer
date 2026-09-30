# Spec Delta

## 閱讀導航

- **現在必讀**：「可靠角撐中心軸的端點校正」，其中定義每端 `600 mm` extension 與 coverage 的獨立性。
- **實作前閱讀**：「端點校正只使用唯一且有效的工程關聯」，確認 body first、relationship second。
- **需要時再讀**：reference-template repair scenarios；只有修改既有人工修補時閱讀。

## MODIFIED Requirements

### Requirement: 可靠角撐中心軸的端點校正

Automatic CornerBrace MUST 使用唯一 `BodyGeometryEvidence` 中 selected RailTracks 的 normalized supporting-line midline 作為中心軸。每一組 `BodyRelationshipAssessment` MUST 以該中心軸與候選 Waler 有限內線、候選 Strut 有限中心線的真實交點建立 expected span 與 endpoints；不得使用無限延長後落在有限構件之外的點、nearest-point snap、改變中心軸方向或重新選 rails。

從 selected rail evidence 對應可見外端到 Waler 交點的 outward extension MUST `<=600.0 mm`，到 Strut 交點的 outward extension亦 MUST `<=600.0 mm`。兩端分別檢核；`600.0 mm` 等號合格，任一端超過上限即使另一端合格仍須拒絕該 relationship。

Extension gate 與 per-rail coverage gate MUST 獨立且同時通過。合法 extension 不得補償任一 rail coverage `<50%`；合法 coverage 也不得補償任一端 extension `>600 mm`。Complete／occluded classification、coverage、gaps 與 hard-valid outcome SHALL 保存於 `BodyRelationshipAssessment`，不得寫入 `BodyGeometryEvidence`。

使用者明確採用的 `body_relationship_selection` repair SHALL 使用同一 body midline 與所選 assessment 的 finite Waler／Strut identities，並在 Apply 前重驗上述交點、coverage 與 extension。既有 `reference_template` repair SHALL 保留 transferred endpoints authority，不得被 automatic extension 覆寫。

#### Scenario: 完整零端板 body 延伸至正式接點
- **WHEN** unique body 沒有端板，但某一 relationship 的 finite intersections、兩端 extension、逐軌 coverage及其他 gates 全部合格
- **THEN** 系統 SHALL 使用 selected RailTracks 的 midline 與該 relationship endpoints 建立正式中心線

#### Scenario: 遮擋 body 使用同一 selected midline
- **WHEN** assessment 分類為合法 occluded
- **THEN** 系統 SHALL 使用其 `BodyGeometryEvidence` 已選定的 midline
- **AND** MUST NOT 在 calibration 階段重新列舉 rails

#### Scenario: 600 mm outward extension 等號邊界
- **WHEN** Waler 端或 Strut 端所需 outward extension 恰好為 `600.0 mm`，且其他 gates 合格
- **THEN** 該端 SHALL 通過 extension gate

#### Scenario: 任一端延伸超過 600 mm
- **WHEN** 任一端所需 outward extension 大於 `600.0 mm`
- **THEN** 該 relationship MUST hard-invalid
- **AND** MUST NOT 以另一端較短或 coverage 較高補償

#### Scenario: Extension 合格但 coverage 不足
- **WHEN** Waler 與 Strut 端 extension 都不超過 `600 mm`，但任一 selected rail coverage 低於 `50%`
- **THEN** 該 relationship MUST 因 coverage 不足被拒絕

#### Scenario: Coverage 合格但 extension 超限
- **WHEN** 兩條 rail coverage 都不低於 `50%`，但任一端 extension 為 `800 mm`
- **THEN** 該 relationship MUST 因 extension 超限被拒絕

#### Scenario: 無限延長才相交
- **WHEN** body midline 只有與 Waler 或 Strut 的無限延長線相交，交點不位於其有限工程線上
- **THEN** 系統 MUST 拒絕該 relationship

#### Scenario: 人工選定 relationship 後沿既有 body 求交
- **WHEN** unique body 有多組 hard-valid relationships，且使用者在 Preview 明確選定其中一組
- **THEN** Apply SHALL 使用相同 body midline 與所選 finite identities 的交點
- **AND** MUST NOT 改選 tracks 或套用其他 relationship endpoints

#### Scenario: Reference-template repair 保持 transferred endpoints
- **WHEN** 使用者採用既有 `reference_template` repair candidate
- **THEN** 系統 SHALL 使用該 candidate 已驗證的 transferred endpoints
- **AND** MUST NOT 以 automatic centerline extension 覆寫

#### Scenario: Y1A、Y29 與遮擋 body 共用規則
- **WHEN** Y1A 連接板型、Y29 平行／斜切型或合法遮擋型 CornerBrace 具有可靠 selected rail midline
- **THEN** 系統 SHALL 對各自 relationship 套用相同有限交點、逐軌 coverage 與每端 `600 mm` extension gates

#### Scenario: 沒有可靠中心軸
- **WHEN** automatic candidate 無法取得唯一可靠 body midline
- **THEN** 系統 MUST 保持 unresolved
- **AND** MUST NOT 猜測或移動 endpoints

#### Scenario: Y1A 連接板型角撐保持辨識並延伸
- **WHEN** Y1A型body具有可靠selected rails、唯一hard-valid relationship且所有gates合格
- **THEN** 系統 SHALL 保留連接板evidence並使用midline的finite intersections作為endpoints

#### Scenario: Y29 平行主桿型角撐延伸至中心線
- **WHEN** Y29型平行主桿body具有唯一hard-valid relationship
- **THEN** 系統 SHALL 將selected-track midline校正至finite Waler／Strut intersections

#### Scenario: Y29 完整斜切角撐延伸至中心線
- **WHEN** Y29斜切／梯形body具有唯一hard-valid relationship
- **THEN** 系統 SHALL 使用supporting-line midline，不得因finite rail長度不同而拒絕

#### Scenario: 遮蔽 rail 候選延伸至正式接點
- **WHEN** occluded assessment通過逐軌coverage、逐gap evidence與每端extension gates
- **THEN** 系統 SHALL 使用其body midline與assessment finite endpoints建立正式中心線

#### Scenario: 非 legacy 方法沒有可靠中心軸
- **WHEN** 非legacy recognition無法取得唯一 `BodyGeometryEvidence` midline
- **THEN** 系統 SHALL 保持unresolved，不得使用fallback猜測軸線

#### Scenario: 人工採用 repaired axis
- **WHEN** 使用者明確採用合法repair candidate
- **THEN** 系統 SHALL 依該candidate mode使用已驗證endpoints與relationship provenance

#### Scenario: Reference length 不得改寫 repaired endpoints
- **WHEN** reference-template candidate的result length與reference length不同，但transferred endpoints已通過target validation
- **THEN** 系統 SHALL 將差異只作diagnostic comparison
- **AND** MUST NOT 為符合reference length移動endpoints

#### Scenario: Repaired endpoints 未通過 target validation
- **WHEN** 任一repaired endpoint不在其target finite engineering line或未通過既有target validation
- **THEN** 系統 MUST 拒絕candidate並保留提交前狀態

### Requirement: 端點校正只使用唯一且有效的工程關聯

Automatic recognition MUST 先完成全部 RailTrack hypotheses、track-pair body hypotheses、幾何等價合併與 body ambiguity 判斷，再為每一個 body 列舉 active finite Waler／Strut relationships。每組 relationship MUST 產生自己的 `BodyRelationshipAssessment`；不得把 relationship A 的 expected span、coverage、gaps、classification 或 extension 套到 relationship B。

只有唯一 body 且恰好一組 hard-valid assessment 時，系統 SHALL automatic 建立正式 connection。唯一 body 有多組 hard-valid assessments 時，automatic calibration MUST 保持 unresolved；每組 relationship 保持獨立 source identity，即使有限工程線幾何重合也不得建立 canonical Waler、以 nearest／first-match 選擇或依 collection order 決定。Body 零解或多解時 MUST NOT 進入 relationship-selection repair。

`body_relationship_selection` Preview MAY 呈現 unique body 的多組 hard-valid assessments，但只有使用者明確選定並 Apply 的一組可成為正式工程關係。排除或恢復 source 後 MUST 依 current active facts 重算，不得重播暫時選擇。

#### Scenario: 唯一有效關聯
- **WHEN** unique body 只有一組通過 finite intersections、每軌 coverage、每端 extension與其他 validation 的 assessment
- **THEN** 系統 SHALL automatic 使用該 assessment 校正 endpoints並建立 connection

#### Scenario: 同一 body 對 relationships 結果不同
- **WHEN** relationship A coverage 合格、relationship B coverage 不足
- **THEN** 系統 SHALL 分別保存結果
- **AND** MUST NOT 因共用 body 而把 A 的 hard-valid outcome套到 B

#### Scenario: 多組 hard-valid relationships
- **WHEN** unique body 有兩組以上 hard-valid assessments
- **THEN** automatic calibration MUST 保持 unresolved
- **AND** SHALL 保留所有 competing source identities 供 Preview

#### Scenario: 幾何重合的 active Waler
- **WHEN** 不同 active Waler source identities 具有重合 finite geometry，且各自形成 hard-valid assessment
- **THEN** 系統 MUST 視為不同 relationships
- **AND** MUST NOT 建立 canonical Waler 或自動選擇

#### Scenario: Body 多解不得交給 relationship selection
- **WHEN** source 有多個非等價 body solutions
- **THEN** 系統 MUST 阻止 relationship-selection repair

#### Scenario: 排除其中一個 Waler 後依 active facts 重算
- **WHEN** competing Waler 中一個被排除，重新辨識後只剩一組 hard-valid assessment
- **THEN** 系統 SHALL automatic 建立剩餘 connection
- **AND** MUST NOT 重播排除前 Preview 的選擇

#### Scenario: 未完成 body 全列舉不得校正
- **WHEN** RailTrack／body hypotheses 尚未完成全列舉、等價合併與 ambiguity 判斷
- **THEN** 系統 MUST NOT 提前校正任何 endpoints

#### Scenario: 使用者選定一組 hard-valid relationship
- **WHEN** Preview 顯示 unique body 的多組 hard-valid assessments，且使用者明確 Apply 一組
- **THEN** 系統 SHALL 只使用所選 relationship、finite endpoints與 selection provenance

#### Scenario: 未 Apply 時保持 blocking
- **WHEN** unique body 仍有多組 hard-valid assessments，且使用者尚未 Apply
- **THEN** connection SHALL 保持 unresolved
- **AND** DXF Review completion MUST 維持 blocked

#### Scenario: 多重或競爭關聯
- **WHEN** unique body具有多組hard-valid assessments
- **THEN** automatic calibration MUST 保持unresolved並保留structured candidates

#### Scenario: 幾何重合的 active Waler 仍是多重關聯
- **WHEN** 不同active Waler identities具有重合finite geometry且各自hard-valid
- **THEN** 系統 MUST 視為多重relationships，不得合併

#### Scenario: 完整候選未完成全列舉不得進入 calibration
- **WHEN** body hypotheses尚未完成全列舉、等價合併與ambiguity判定
- **THEN** 系統 MUST NOT 校正tentative endpoints

#### Scenario: 人工修補明確解決多候選
- **WHEN** 使用者在Preview明確選定unique body的一組hard-valid relationship並Apply
- **THEN** 系統 SHALL 只提交所選assessment的finite endpoints與identities

#### Scenario: Unresolved 多 relationship 必須 blocking
- **WHEN** unique body仍有多組hard-valid relationships且未Apply選擇
- **THEN** DXF Review completion MUST 保持blocked

#### Scenario: 最近 reference 不是工程關聯選擇捷徑
- **WHEN** 空間最近的member或reference未通過finite intersection、coverage或extension gates
- **THEN** 系統 MUST NOT 因proximity選擇該relationship
