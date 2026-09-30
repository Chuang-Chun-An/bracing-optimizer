# Spec Delta

## MODIFIED Requirements

### Requirement: 可靠角撐中心軸的端點校正

系統 SHALL 對可取得可靠中心軸的正式 `corner_brace` 進行端點校正。Automatic recognition 的校正 SHALL 將中心軸延伸並分別與唯一對應圍令的有限內線、唯一對應支撐的中心線求有效交點；系統 MUST 支援由 `connection_plate_midpoints` 與 `parallel_edges_midline` 產生的可靠中心軸，不得僅因 recognition method 不同而略過校正。

使用者明確採用的人工 repair SHALL 使用該候選保存的 target Waler／Strut relationship 與 reference-template transferred endpoints。這兩個 endpoints 必須分別位於 target Waler 有限工程線與 target Strut 有限中心線，並通過 exact target direction／positional-anchor validation；人工 repair 不要求由 target residual axis 與兩構件求交，也不得在採用後重新以 automatic centerline extension 覆寫 transferred endpoints。

#### Scenario: Y1A 連接板型角撐保持辨識並延伸
- **WHEN** automatic CornerBrace 由連接板中點辨識，且可取得唯一有效的圍令與支撐交點
- **THEN** 系統 SHALL 保留連接板辨識結果
- **AND** SHALL 使用角撐中心軸延伸後的交點作為工程端點

#### Scenario: Y29 平行主桿型角撐延伸至中心線
- **WHEN** automatic CornerBrace 由 `parallel_edges_midline` 辨識，且可取得可靠中心軸與唯一有效的圍令及支撐交點
- **THEN** 系統 SHALL 將角撐中心軸延伸至圍令內線與支撐中心線
- **AND** SHALL NOT 因 recognition method 不是 `connection_plate_midpoints` 而略過校正

#### Scenario: 非 legacy 方法沒有可靠中心軸
- **WHEN** automatic CornerBrace 無法取得可靠中心軸，且使用者沒有採用人工修補候選
- **THEN** 系統 SHALL 保留原辨識幾何
- **AND** SHALL NOT 猜測或移動端點

#### Scenario: 人工採用 repaired axis
- **WHEN** 使用者已在角撐修補預覽中明確採用一組 target Waler／Strut、automatic primary template、transfer mode 與 transferred endpoints
- **THEN** 系統 SHALL 使用該 transferred endpoints 作為正式工程端點
- **AND** SHALL NOT 再以 automatic axis extension 或其他鄰近構件取代使用者採用的 target relationship

#### Scenario: Reference length 不得改寫 repaired endpoints
- **WHEN** reference-template transfer 已依 target local frame、reference Waler offset、reference Strut station 與 transfer mode 產生 endpoints，且重算的 candidate fixed length 與 reference fixed length 不同
- **THEN** 系統 SHALL 將差異只作為 Preview／provenance／diagnostic comparison，且不得因此單獨改變 candidate eligibility
- **AND** MUST NOT 為符合 reference length 而移動 endpoints、強迫等長、使用圓交點／縮放／clamp，或覆寫 target evidence

#### Scenario: Repaired endpoints 未通過 target validation
- **WHEN** transferred endpoints 任一不在 target finite engineering line，或其軸與 exact target direction／positional anchor 不相容
- **THEN** 系統 SHALL 拒絕該 repair candidate
- **AND** SHALL 保留提交前正式幾何或 unresolved state

### Requirement: 端點校正只使用唯一且有效的工程關聯

Automatic recognition SHALL 沿既有 recognition pipeline 選出 Waler 與 Strut，再以選定構件的有限幾何求交；automatic calibration MUST NOT 引入新的 candidate enumeration、runner-up threshold、50/50 或 51/49 ambiguity policy，也不得只因空間距離最近而吸附到構件。

人工 CornerBrace repair 屬於獨立 explicit-selection path。每個可採用 candidate MUST 明確且唯一綁定一組 target Waler／Strut relationship、selected automatic primary template 與 transfer mode；reference 必須先通過工程 compatibility，才能使用 locality ranking。Recognized replace plan 可包含多個分別綁定不同 relationship、各自完整且 hard-valid 的 candidates，並由使用者在 Preview 選定。Unresolved create plan 的所有 hard-eligible candidates MUST 指向同一組 relationship；若出現多組 relationship，create path MUST blocking。採用後，被選 candidate 的 relationship 與 transferred endpoints 才成為本次修補的唯一工程 truth。

#### Scenario: 唯一有效關聯
- **WHEN** automatic CornerBrace 具有既有 pipeline 選定的 Waler 與 Strut，且中心軸分別與兩者有效有限線段相交
- **THEN** 系統 SHALL 使用這兩個交點校正 automatic endpoints

#### Scenario: 多重或競爭關聯
- **WHEN** automatic recognition 存在 competing-axis association
- **THEN** automatic calibration SHALL NOT 改變候選勝出或 ambiguity selection policy
- **AND** SHALL NOT 新增 runner-up 或比例式門檻

#### Scenario: 人工修補明確解決多候選
- **WHEN** recognized replace 的角撐修補工具提出多個分別唯一綁定 target relationship 與 template 的合法 candidates
- **THEN** 系統 SHALL 在採用前呈現每個 candidate 的 relationship、template 與 transfer mode
- **AND** 只有使用者明確選定的 candidate 可成為正式修補結果

#### Scenario: Unresolved 多 relationship 必須 blocking
- **WHEN** unresolved create 的 hard-eligible candidates 指向多組 target Waler／Strut relationships
- **THEN** 系統 MUST 拒絕 create path
- **AND** MUST NOT 讓使用者在 Preview 決定構件歸屬

#### Scenario: 最近 reference 不是工程關聯選擇捷徑
- **WHEN** 空間最近的 CornerBrace 不符合 target endpoint topology、local-frame compatibility 或 target residual validation
- **THEN** 人工修補 MUST 排除該 reference
- **AND** MUST NOT 只因 proximity 將其 target relationship 或 endpoints 設為正式 truth

### Requirement: 校正失敗必須保持候選幾何的原子性

Automatic calibration MUST 先以 local values 完成 Waler intersection、Strut intersection、finite-segment projection 與 minimum-length validation；全部通過後才可寫入 automatic candidate geometry。人工 repair MUST 先以 local values 完成 template extraction、target-frame transfer、finite endpoint checks、target evidence validation 與既有 CornerBrace validation；全部通過後才可形成可 Apply candidate。任一路徑前提不成立時 MUST 保留提交前幾何，並產生可追溯 diagnostic。

#### Scenario: 缺少有效圍令或支撐交點
- **WHEN** automatic centerline 無法與選定 Waler 或 Strut 產生有效 finite intersection，或人工 repair 無法在 target finite geometry 上產生完整的兩個 endpoints
- **THEN** 系統 SHALL NOT 變更 automatic candidate endpoints，也不得建立可 Apply repair candidate
- **AND** SHALL 產生可追溯 diagnostic

#### Scenario: 校正後長度不合法
- **WHEN** automatic calibration 或人工 repair 的完整 local result 非有限值、短於既有最小長度，或未通過既有長度 validation
- **THEN** 系統 SHALL NOT 寫入任何部分校正結果
- **AND** SHALL 保留提交前幾何並產生可追溯 diagnostic

#### Scenario: 人工 template transfer 只有部分成功
- **WHEN** template 可抽取但 target transfer、finite endpoint、target evidence 或 staged validation 任一步失敗
- **THEN** 系統 SHALL NOT 建立可 Apply candidate 或部分更新正式 CornerBrace
- **AND** SHALL 顯示失敗階段與原因

#### Scenario: Apply 前 state 已改變
- **WHEN** Preview 後 target subject、target relationship、selected template 或其 connection 發生改變
- **THEN** 系統 MUST 將 plan 視為 stale 並拒絕提交
- **AND** SHALL 要求使用者重新建立 Preview
