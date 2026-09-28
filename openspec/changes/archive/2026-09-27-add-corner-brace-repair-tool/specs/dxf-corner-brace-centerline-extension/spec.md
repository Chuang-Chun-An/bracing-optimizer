# Spec Delta

## MODIFIED Requirements

### Requirement: 可靠角撐中心軸的端點校正

系統 SHALL 對可取得可靠中心軸的正式 `corner_brace` 進行端點校正。自動辨識的校正 SHALL 將中心軸延伸並分別與唯一對應圍令的有限內線、唯一對應支撐的中心線求有效交點。系統 MUST 支援由 `connection_plate_midpoints` 與 `parallel_edges_midline` 產生的可靠中心軸；不得僅因 recognition method 不同而略過校正。使用者在角撐修補流程中明確採用的 repaired axis SHALL 視為人工確認的可靠軸，並以該修補候選明確綁定的 Waler 與 Strut 有限幾何完成同一工程端點語意。Reference CornerBrace 的 fixed length、side 與 topology 只能驗證 repaired axis，不得覆寫有限交點、複製 reference coordinates 或強迫 repaired target 採用 reference length。

#### Scenario: Y1A 連接板型角撐保持辨識並延伸
- **WHEN** 角撐由連接板中點辨識，且可取得唯一有效的圍令與支撐交點
- **THEN** 系統 SHALL 保留連接板辨識結果
- **AND** SHALL 使用角撐中心軸延伸後的交點作為工程端點

#### Scenario: Y29 平行主桿型角撐延伸至中心線
- **WHEN** 角撐由 `parallel_edges_midline` 辨識，且可取得可靠中心軸與唯一有效的圍令及支撐交點
- **THEN** 系統 SHALL 將角撐中心軸延伸至圍令內線與支撐中心線
- **AND** SHALL NOT 因 recognition method 不是 `connection_plate_midpoints` 而略過校正

#### Scenario: 非 legacy 方法沒有可靠中心軸
- **WHEN** 正式角撐的辨識方法不是連接板中點，且無法取得可靠中心軸，且使用者沒有採用修補候選
- **THEN** 系統 SHALL 保留原辨識幾何
- **AND** SHALL NOT 猜測或移動端點

#### Scenario: 人工採用 repaired axis
- **WHEN** 使用者已在角撐修補預覽中明確採用一條 repaired axis 及其目標 Waler／Strut
- **THEN** 系統 SHALL 使用該軸與目標 Waler 有限內線、Strut 有限中心線的交點作為正式工程端點
- **AND** SHALL NOT 再以其他鄰近構件取代使用者採用的目標關係

#### Scenario: Reference length 不得改寫 repaired endpoints
- **WHEN** repaired axis 的兩個 target finite intersections 已建立，但其長度與 reference fixed length 不一致
- **THEN** 系統 SHALL 拒絕該 repair hypothesis 或 candidate
- **AND** SHALL NOT 沿軸移動任一交點以符合 reference length

### Requirement: 端點校正只使用唯一且有效的工程關聯

自動辨識流程 SHALL 沿既有 recognition pipeline 選出圍令與支撐，再以選定構件的有限幾何求交；自動校正 MUST NOT 引入新的候選列舉、runner-up 門檻、50/50 或 51/49 ambiguity policy，也不得只因空間距離最近而吸附到構件。人工角撐修補屬於獨立的 explicit-selection path：每個可採用候選 MUST 明確綁定一支 Waler 與一支 Strut，存在多個非等價候選時 MUST 由使用者在預覽中選定一組，採用後該組關係才成為本次修補的唯一工程關聯。

#### Scenario: 唯一有效關聯
- **WHEN** 一支正式角撐具有既有 pipeline 選定的圍令與支撐，且中心軸分別與兩者有效有限線段相交
- **THEN** 系統 SHALL 使用這兩個交點校正端點

#### Scenario: 多重或競爭關聯
- **WHEN** 自動辨識資料存在重複 Waler 或 Strut 幾何，造成 competing-axis association
- **THEN** 自動校正 SHALL NOT 改變候選勝出或 ambiguity selection policy
- **AND** SHALL NOT 新增 runner-up 或比例式門檻

#### Scenario: 人工修補明確解決多候選
- **WHEN** 角撐修補工具提出多個各自具有有效有限交點的非等價候選
- **THEN** 系統 SHALL 在採用前呈現各候選綁定的 Waler／Strut
- **AND** 只有使用者明確選定的關係可成為正式修補結果

### Requirement: 校正後端點是角撐後續工程調整的基準

系統 MUST 將自動校正或已採用人工修補後的角撐端點，作為 corner-brace-to-waler 與 corner-brace-to-strut 關聯、固定孔位站距、固定角撐長度及後續 Waler contact／背填調整的基準。後續調整 SHALL 從該正式支撐中心線端點重算，不得回退至支撐外緣、連接板附近的原始端點或修補前的錯誤軸線。

#### Scenario: 建立角撐關聯
- **WHEN** 角撐端點已完成自動中心線校正或使用者已採用人工修補
- **THEN** 儲存的 Waler attachment、Strut attachment、hole station 與 fixed length SHALL 以目前正式端點計算

#### Scenario: 移動圍令接觸線後重算
- **WHEN** 系統對已校正或已修補角撐套用 Waler contact、背填或圍令寬度調整
- **THEN** 系統 SHALL 從目前正式的支撐中心線端點與既有固定基準重算
- **AND** SHALL NOT 回退至原始未校正或修補前的角撐端點
