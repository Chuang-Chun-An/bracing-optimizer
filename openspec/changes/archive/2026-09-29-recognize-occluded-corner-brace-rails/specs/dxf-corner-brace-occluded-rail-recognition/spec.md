# Spec Delta

## Purpose

定義 CornerBrace 本體 rail 正交間距的正式材料規則，以及 DXF automatic recognition 如何以此排除材料尺度不合理的窄線組合；當一側 rail 因其他斜撐或來源有限幾何在 terminal neighborhood 實際遮蔽而截短時，系統使用保守且可追溯的 fallback 建立唯一候選，若無安全解則保留來源並阻止 DXF Review 完成。

## 閱讀導航

- **必讀**：「本體 rail 寬度是正式材料規則」、「完整候選必須全部列舉」及「無唯一合法解必須阻止 Review 完成」。
- **條件式閱讀**：實作 diagnostics／Review projection 時閱讀「診斷必須保留 exact source identity」；調整中心軸端點時改讀 `dxf-corner-brace-centerline-extension` delta。
- **可先跳過**：人工 reference-template repair、Pause／Resume 與 Solver specs；本 capability 不改變其既有 contract。

## ADDED Requirements

### Requirement: 本體 rail 寬度是正式材料規則與 automatic recognition hard gate

系統 MUST 以 selected 本體 rails 各自所在 supporting line 之間的真正正交間距作為 CornerBrace 本體寬度。對既有平行角度容差內的 rail pair，量測 SHALL 對稱使用兩條無限 supporting lines 的垂直距離，且 MUST NOT 將有限 rail 端部 overhang 納入寬度。正式 CornerBrace 的 rail separation MUST 嚴格大於 250.0 mm；寬度等於或小於 250.0 mm 的 rail pair MUST NOT 成為正式 CornerBrace。本規則是已確認的正式材料／工程規則，並由 DXF automatic recognition 執行；它不是 DXF 搜尋 heuristic、Solver Preference、Solver scoring 或搜尋參數。

系統 MUST NOT 使用連接板線長、兩端板線長平均值、圖塊名稱、最近構件距離或既有 `source_width` 的非 rail 語意代替本體 rail 正交間距。

#### Scenario: 正常約 300 mm rail pair
- **WHEN** 兩條通過既有完整角撐拓撲檢核的本體 rail，其正交間距約為 300 mm 且嚴格大於 250 mm
- **THEN** 系統 SHALL 允許該 rail pair 繼續參與完整 CornerBrace candidate selection

#### Scenario: 250 mm 等號邊界
- **WHEN** 候選 rail pair 的正交間距恰好等於 250 mm
- **THEN** 系統 MUST 拒絕該 pair 成為正式 automatic CornerBrace

#### Scenario: 內部窄線組合
- **WHEN** 圖塊內兩條平行線可形成既有拓撲組合，但其正交間距小於 250 mm
- **THEN** 系統 MUST 排除該組合
- **AND** MUST NOT 因其長度更一致、端板更完整或排列順序較前而使其勝出

#### Scenario: 端板平均長度與 rail 間距不同
- **WHEN** 兩端連接板線長的平均值與本體 rail 正交間距不同
- **THEN** 系統 SHALL 使用 rail 正交間距進行 250 mm hard gate
- **AND** SHALL NOT 將端板平均值呈現或重用為本體寬度 truth

#### Scenario: 斜切 rail 的有限端部不得增加正式寬度
- **WHEN** 兩條合法 selected rails 的 supporting lines 正交間距約為 300 mm，但兩條有限 rail 長度不同，使 generic 有限線段端點平均距離大於 300 mm
- **THEN** 系統 SHALL 將約 300 mm 的 supporting-line 正交間距存為 `source_width`
- **AND** MUST NOT 使用有限端部 overhang 所增加的 segment distance 作為 CornerBrace rail separation

### Requirement: 完整候選必須全部列舉並優先於遮蔽 fallback

系統 SHALL 完成 exact source group 內全部完整 rail-pair hypotheses 的列舉。完整 hypothesis MAY 為近似等長的既有雙 rail／雙端板 topology，或完整斜切／梯形 topology。完整斜切／梯形 hypothesis MUST 具有兩條合法平行 body rails、兩條不同有限端板、四個實際 rail-to-plate terminal connections，以及由該 rail／plate evidence 形成唯一且完整的 closed traversal；它不得只因任意封閉外框或 generic `closed_outline_axis` 成立。

系統 SHALL 對每個完整 hypothesis 套用 rail separation `> 250.0 mm` hard gate，再合併因方向、端點順序或 exact source group 內重複 primitive 造成的幾何等價 rail／plate candidates，並完成既有可分割性判斷。不共用 rails／plates 且可安全分割的完整候選 SHALL 可建立多個 CornerBrace bodies；若多個候選競爭相同 evidence 或無法形成唯一可分割集合，系統 MUST 將其視為 ambiguity。完整斜切／梯形 body 的 `source_width` MUST 使用 selected rail separation，不得使用端板長度或平均值；遮蔽短長比 `0.75` MUST NOT 套用於具有完整雙端板 traversal 的 body。

完成上述全部程序後，只要仍存在一個或多個可正式建立的完整 CornerBrace，該 exact source group MUST NOT 進入遮蔽 fallback。只有合法完整候選集合為空時，系統才可評估遮蔽 rail fallback；fallback MUST NOT 覆寫或降級完整候選集合。系統 MUST NOT 使用 first valid match、first occurrence、handle ordering、entity order、排序或分數，把未完成列舉或 ambiguity 轉成唯一解。

#### Scenario: 完整列舉後存在可建立集合
- **WHEN** 系統已列舉全部完整 hypotheses、套用 topology 與寬度 hard gate、合併幾何等價候選並完成既有可分割性判斷
- **AND** 結果仍有一個或多個不共用 evidence 且可正式建立的完整 CornerBrace
- **THEN** 系統 SHALL 建立該完整候選集合
- **AND** 該 exact source group MUST NOT 進入遮蔽 fallback

#### Scenario: 完整斜切或梯形 CornerBrace body
- **WHEN** 兩條合法平行 body rails 的正交間距嚴格大於 250.0 mm，且兩條不同有限端板形成四個實際 rail-to-plate terminal connections 與唯一完整 closed traversal
- **THEN** 系統 SHALL 將其視為完整 CornerBrace body candidate，即使兩 rail 的原始有限線長不近似
- **AND** SHALL 使用 rail separation 作為 `source_width`
- **AND** MUST NOT 套用遮蔽 fallback 的 0.75 短長比或 terminal occlusion evidence
- **AND** MUST NOT 退回 generic `closed_outline_axis` 或使用端板平均長度作為本體寬度

#### Scenario: 任意封閉梯形不足以成立
- **WHEN** 一個封閉外框缺少兩條合法平行 body rails、兩條不同有限端板、四個 terminal connections 或唯一完整 rail／plate traversal 中任一條件
- **THEN** 系統 MUST NOT 將該外框視為完整斜切／梯形 CornerBrace body
- **AND** MUST NOT 只因 generic outline 能產生中心軸而建立正式 CornerBrace

#### Scenario: 多個完整候選安全可分割
- **WHEN** 完整列舉後有多個合法 candidates，且它們不共用 rails／plates 並可由既有規則安全分割
- **THEN** 系統 SHALL 允許建立多個正式 CornerBrace
- **AND** MUST NOT 因候選數量大於一而啟動遮蔽 fallback

#### Scenario: 完整候選競爭相同 evidence
- **WHEN** 多個完整 candidates 競爭相同 rail／plate evidence 或無法形成唯一可分割集合
- **THEN** 系統 MUST 將完整候選集合標記為 ambiguity
- **AND** MUST NOT 以 first match、handle／entity order、排序或分數選出其中一個
- **AND** MUST NOT 把該 ambiguity 誤視為合法完整候選集合為空而啟動遮蔽 fallback

#### Scenario: 只有窄線完整候選
- **WHEN** exact source group 的完整拓撲組合全部因 rail 間距小於或等於 250 mm 被拒絕
- **THEN** 系統 SHALL 將該來源視為沒有合法完整候選
- **AND** 只有在其他完整 hypotheses 也完成列舉、合併及可分割性判斷且合法集合為空時，MAY 進入遮蔽 rail fallback 評估

### Requirement: 遮蔽 rail fallback 必須由保守證據共同成立

遮蔽 rail fallback SHALL 只接受一組同時符合以下條件的 pair：兩 rail 通過既有平行角度與投影重疊檢核、正交間距嚴格大於 250.0 mm、較短 rail 長度至少為較長 rail 的 75%、至少一端具有既有 endpoint tolerance 內的連接板證據、缺失或截短端具有其他已辨識斜撐或同一 exact source group 的有限幾何所提供的遮蔽 corridor，且由該 pair 中線可建立唯一有效的有限 Waler 內線與 Strut 中心線交點。

作為 corridor evidence 的有限幾何 MUST 在具名幾何容差內實際相交、接觸或通過截短 rail 的 terminal neighborhood，且其位置 MUST 可直接解釋 rail 為何在該 terminal 附近中斷。僅屬於同一 root／block／exact source group、空間鄰近、投影範圍部分重疊、無限延長後可能相交、只在 rail 內部其他位置相交，或依 entity order、顏色、draw order 看似遮蔽，均不足以成為 occlusion corridor evidence。遮蔽 evidence 的幾何比較 MUST 使用具名 recognition tolerances，不得使用未命名 magic number。

#### Scenario: Y05 CB58 類一側 rail 被遮蔽
- **WHEN** exact source group 具有一條完整 rail 與一條因其他斜撐或來源有限幾何在 terminal neighborhood 實際通過而截短的平行 rail，其寬度大於 250.0 mm、短長比至少 75%、投影重疊與至少一端板通過既有容差，且中線可唯一連到有限 Waler／Strut
- **THEN** 系統 SHALL 將該 pair 建立為合法遮蔽 CornerBrace candidate
- **AND** SHALL 保留遮蔽 evidence 與實測 rail 寬度供診斷及 Review 稽核

#### Scenario: 短 rail 比例低於 75%
- **WHEN** 較短 rail 的長度小於較長 rail 的 75%
- **THEN** 系統 MUST 拒絕該遮蔽 hypothesis
- **AND** MUST NOT 只因 rail 寬度大於 250 mm 使其成立

#### Scenario: 缺少遮蔽 corridor evidence
- **WHEN** rail pair 通過寬度、平行與重疊條件，但截短端無法由其他已辨識斜撐或 exact source geometry 的有限線段在 terminal neighborhood 實際相交、接觸或通過來支持為遮蔽
- **THEN** 系統 MUST 拒絕 automatic adoption
- **AND** SHALL 將缺少遮蔽證據列入拒絕診斷

#### Scenario: 同一圖塊內的鄰近線不足以證明遮蔽
- **WHEN** 截短 rail 附近存在同一 exact source group 的其他線段
- **BUT** 該線段未在具名幾何容差內實際相交、接觸或通過截短 rail 的 terminal neighborhood
- **THEN** 系統 MUST NOT 將該線段視為 occlusion corridor evidence
- **AND** MUST NOT 只因同 root、空間鄰近、部分投影重疊或無限延長後可能相交而採用遮蔽候選

#### Scenario: Rail 其他位置的交點不能解釋 terminal 中斷
- **WHEN** 來源有限幾何與截短 rail 在遠離截短 terminal neighborhood 的其他位置相交
- **THEN** 系統 MUST NOT 將該交點視為該 terminal 的 occlusion corridor evidence
- **AND** SHALL 將 terminal 遮蔽證據不足列入拒絕診斷

#### Scenario: 兩端板皆不存在
- **WHEN** 遮蔽 hypothesis 無任何一端可在既有 endpoint tolerance 內找到連接板證據
- **THEN** 系統 MUST 拒絕該 hypothesis

#### Scenario: 中線不能建立有限交點
- **WHEN** 遮蔽 rail pair 的中線無法與唯一 Waler 內線及唯一 Strut 中心線建立有效有限交點
- **THEN** 系統 MUST 拒絕該 hypothesis
- **AND** MUST NOT 以無限延長後最近點吸附使其成立

### Requirement: 無唯一合法解必須阻止 DXF Review 完成

若 exact source group 在完整候選與遮蔽 fallback 後仍沒有合法候選，或存在完整候選 ambiguity／多個非等價合法遮蔽候選而無法唯一決定，系統 MUST NOT 建立猜測的正式 CornerBrace。系統 SHALL 保留 exact source identity、來源幾何、已評估寬度與拒絕原因，並建立可定位來源的 DXF Review problem。

該 problem MUST 至少包含 stable code、來源 Handle、已評估的 rail 寬度及具體拒絕原因；多解時 MUST 列出 ambiguity，而不得依 ID、handle／entity order、排序、分數或 first match 靜默選擇。Operation level SHALL 允許其他來源及構件繼續辨識、顯示與檢核；completion level 則 MUST 在 unresolved source 未被排除、修正或以既有合法流程解決前阻止 DXF Review 完成。系統 MUST NOT 因此自動刪除來源或自動採用 repair candidate。

Body recognition 與 member relationship resolution MUST 分開診斷。若 selected body center axis 同時對應兩個 active Waler sources／members，即使其有限工程線幾何重合，系統 MUST 將其視為多個有效 relationships；MUST NOT 建立 geometry-equivalent Waler relationship group、canonical Waler ID，或依幾何重合、handle、member ID、entity order、first match、nearest distance 選擇其一。系統 SHALL 保留 exact source geometry、selected rails、rail separation 與 relationship ambiguity diagnostics，但 MUST NOT 建立猜測的正式 CornerBrace connection。

#### Scenario: 所有候選皆不合法
- **WHEN** 完整候選都未通過寬度 hard gate，且遮蔽 hypotheses 都缺少必要 evidence 或有限交點
- **THEN** 系統 SHALL 不建立正式 CornerBrace
- **AND** SHALL 建立可追溯 problem 並列出各主要拒絕原因

#### Scenario: 多個非等價遮蔽候選
- **WHEN** 同一 exact source group 有多個非等價遮蔽 hypotheses 同時通過 hard gates
- **THEN** 系統 MUST 不自動選擇其中一個
- **AND** SHALL 保留來源並建立 completion-blocking ambiguity problem

#### Scenario: Unresolved CornerBrace 不阻止其他構件繼續處理
- **WHEN** 一個 CornerBrace source 因無唯一合法解產生 unresolved problem，而其他來源構件均合法
- **THEN** 系統 SHALL 繼續建立及檢核其他構件
- **AND** SHALL 讓使用者可在 DXF Review 定位該 unresolved source

#### Scenario: Unresolved CornerBrace blocks Review completion
- **WHEN** CornerBrace exact source 在完整候選與遮蔽 fallback 後仍無唯一合法解
- **THEN** 系統 SHALL 保留來源並允許其他來源繼續辨識與檢核
- **AND** 系統 SHALL 建立可定位的 DXF Review problem
- **AND** 在該來源未被排除、修正或以既有合法流程解決前，DXF Review MUST NOT 完成
- **AND** 系統 MUST NOT 建立猜測 CornerBrace 或自動採用人工 repair

#### Scenario: 重複重合圍令使角撐關聯保持 unresolved
- **WHEN** 一個已完成 body recognition 的 CornerBrace center axis 同時對應兩個 active Waler sources
- **THEN** 系統 SHALL 將 CornerBrace connection 視為 ambiguous
- **AND** SHALL NOT 依幾何重合、handle、member ID、entity order、first match 或 nearest distance 選擇其中一個
- **AND** SHALL 保留 CornerBrace source geometry、selected rails、rail separation 與 ambiguity diagnostics
- **AND** SHALL 建立可定位的 DXF Review problem
- **AND** 在重複來源未被排除或關聯未以既有合法流程解決前，DXF Review MUST NOT 完成

#### Scenario: 排除重複圍令後重新辨識
- **WHEN** 使用者排除造成 ambiguity 的其中一個重複 Waler source
- **AND** recognition 依目前 active source facts 重新執行
- **THEN** 若 CornerBrace center axis 只剩一個合法有限 Waler relationship，系統 SHALL 使用該唯一關聯完成 CornerBrace connection
- **AND** SHALL NOT 沿用排除前的 ambiguity outcome 或任何暫時選擇

#### Scenario: 重複圍令輸入順序不影響 ambiguity
- **WHEN** 兩個 active Waler sources 都與同一已辨識 CornerBrace body 建立有效有限關聯，且輸入／handle／entity 順序互換
- **THEN** 系統 SHALL 產生相同 relationship ambiguity outcome
- **AND** MUST NOT 因順序不同而讓任一 Waler 自動勝出

#### Scenario: 單一圍令關聯可完成 connection
- **WHEN** 完整斜切／梯形 CornerBrace body 只有一個合法有限 Waler relationship 與一個合法有限 Strut relationship
- **THEN** 系統 SHALL 使用該唯一關聯完成 endpoint calibration 與 CornerBrace connection
- **AND** SHALL NOT 產生重複來源 relationship problem

### Requirement: 遮蔽辨識不得建立第二份工程 truth

合法完整或遮蔽 candidate 一旦完成 body recognition，其 selected rail pair、實測 rail 寬度、中心軸、topology／遮蔽 evidence 與 exact source identity MUST 共同構成同一份 body recognition truth，供關聯列舉、中心軸端點校正、CornerBraceConnection、candidate points、diagnostics 與 Review projection 重用。Presentation、repair 或 validation MUST NOT 各自重新推導另一組 rail pair。Body truth 不得預先綁定未唯一決定的 Waler identity。

#### Scenario: 下游重用同一 selected pair
- **WHEN** 遮蔽 candidate 已通過 automatic recognition 並進入端點校正
- **THEN** 中心軸、關聯、診斷及 Review SHALL 使用該 candidate 保存的同一組 selected rails 與寬度
- **AND** MUST NOT 再從全部來源線段另選不同 rail pair

