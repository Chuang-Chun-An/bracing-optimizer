# Spec Delta

## 閱讀導航

- **必讀**：「可靠角撐中心軸的端點校正」與「端點校正只使用唯一且有效的工程關聯」的修改內容。
- **條件式閱讀**：實作遮蔽 candidate enumeration 時改讀 `dxf-corner-brace-occluded-rail-recognition`；人工 repair 維持原 spec。
- **可先跳過**：Waler contact 後續重算與一般構件 regression requirement；本 change 未改變其規則。

## MODIFIED Requirements

### Requirement: 可靠角撐中心軸的端點校正

系統 SHALL 對可取得可靠中心軸且具有唯一 active Waler／Strut relationship 的正式 `corner_brace` 進行端點校正。Automatic recognition 的校正 SHALL 將中心軸延伸並分別與唯一對應圍令的有限內線、唯一對應支撐的中心線求有效交點；系統 MUST 支援由一般完整 body、完整斜切／梯形 body 與通過 `dxf-corner-brace-occluded-rail-recognition` 全部 hard gates 的遮蔽 rail pair 產生的可靠中心軸，不得僅因 recognition method 不同而略過校正。所有新 body candidate 的中心軸 MUST 使用 recognition 已選定且保存的 rail pair，不得在 calibration 階段重新列舉或改選來源線。

使用者明確採用的人工 repair SHALL 使用該候選保存的 target Waler／Strut relationship 與 reference-template transferred endpoints。這兩個 endpoints 必須分別位於 target Waler 有限工程線與 target Strut 有限中心線，並通過 exact target direction／positional-anchor validation；人工 repair 不要求由 target residual axis 與兩構件求交，也不得在採用後重新以 automatic centerline extension 覆寫 transferred endpoints。

#### Scenario: Y1A 連接板型角撐保持辨識並延伸
- **WHEN** automatic CornerBrace 由連接板中點辨識，且可取得唯一有效的圍令與支撐交點
- **THEN** 系統 SHALL 保留連接板辨識結果
- **AND** SHALL 使用角撐中心軸延伸後的交點作為工程端點

#### Scenario: Y29 平行主桿型角撐延伸至中心線
- **WHEN** legacy automatic CornerBrace 由 `parallel_edges_midline` 辨識，且可取得可靠中心軸與唯一有效的 active 圍令及支撐交點
- **THEN** 系統 SHALL 將角撐中心軸延伸至圍令內線與支撐中心線
- **AND** SHALL NOT 因 recognition method 不是 `connection_plate_midpoints` 而略過校正

#### Scenario: Y29 完整斜切角撐延伸至中心線
- **WHEN** automatic CornerBrace 由雙 rail、雙端板、四個 terminal connections 與唯一 closed traversal 辨識為完整斜切 body，且可取得可靠中心軸與唯一有效的 active 圍令及支撐交點
- **THEN** 系統 SHALL 將角撐中心軸延伸至圍令內線與支撐中心線
- **AND** SHALL NOT 因兩 rail 原始有限線長不同而略過校正

#### Scenario: 遮蔽 rail 候選延伸至正式接點
- **WHEN** automatic CornerBrace 由唯一且通過全部遮蔽 rail hard gates 的 selected pair 建立，且該 pair 中線可取得唯一有效的圍令與支撐交點
- **THEN** 系統 SHALL 使用保存的 selected pair 中線延伸至圍令內線與支撐中心線
- **AND** SHALL NOT 在端點校正時重新列舉或替換 rail pair

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

Automatic recognition SHALL 沿 recognition pipeline 先完成全部一般完整與完整斜切／梯形 rail-pair hypotheses 的列舉、hard-gate validation、幾何等價合併及既有可分割性判斷。只要仍有可建立的完整 CornerBrace body，或完整候選仍存在 competing-evidence ambiguity，系統 MUST NOT 進入遮蔽 fallback；只有合法完整 body 集合為空時，才可列舉遮蔽 rail hypotheses。Body recognition 完成後，再依目前 active source facts 列舉 Waler 與 Strut relationships，最後僅在關聯唯一時以選定構件的有限幾何求交。Automatic calibration MUST NOT 自行引入第二套 candidate enumeration、runner-up threshold、50/50 或 51/49 ambiguity policy，也不得只因空間距離最近或有限工程線幾何重合而吸附到構件；新增的 body／遮蔽 rail enumeration 只屬 recognition stage，且其唯一性與 failure behavior 由 `dxf-corner-brace-occluded-rail-recognition` 定義。

每個 active Waler source/member MUST 保持獨立 relationship identity。兩個 active Waler 的有限工程線即使幾何重合，也 MUST 視為兩個有效 relationships；calibration MUST NOT 建立 geometry-equivalent relationship group、canonical Waler ID，或使用 handle、member ID、entity order、first match、nearest distance 選擇其一。

人工 CornerBrace repair 屬於獨立 explicit-selection path。每個可採用 candidate MUST 明確且唯一綁定一組 target Waler／Strut relationship、selected automatic primary template 與 transfer mode；reference 必須先通過工程 compatibility，才能使用 locality ranking。Recognized replace plan 可包含多個分別綁定不同 relationship、各自完整且 hard-valid 的 candidates，並由使用者在 Preview 選定。Unresolved create plan 的所有 hard-eligible candidates MUST 指向同一組 relationship；若出現多組 relationship，create path MUST blocking。採用後，被選 candidate 的 relationship 與 transferred endpoints 才成為本次修補的唯一工程 truth。

#### Scenario: 唯一有效關聯
- **WHEN** automatic CornerBrace 具有 recognition pipeline 唯一選定的完整或遮蔽 rail candidate、Waler 與 Strut，且中心軸分別與兩者有效有限線段相交
- **THEN** 系統 SHALL 使用這兩個交點校正 automatic endpoints

#### Scenario: 多重或競爭關聯
- **WHEN** automatic recognition 存在多個非等價遮蔽 rail candidates，或已辨識 body 同時對應多個 active Waler／Strut identities
- **THEN** automatic calibration SHALL NOT 改變候選勝出或 ambiguity selection policy
- **AND** SHALL NOT 新增 runner-up、比例式門檻、geometry-equivalent member merge、canonical member ID 或 first-match fallback

#### Scenario: 幾何重合的 active Waler 仍是多重關聯
- **WHEN** 已辨識 CornerBrace body 的 center axis 同時與兩個 active Waler sources 的有限工程線建立有效交點，即使兩條工程線幾何重合
- **THEN** automatic calibration MUST NOT 建立正式 CornerBrace connection 或移動 endpoints
- **AND** SHALL 保留 body evidence 並回報 relationship ambiguity

#### Scenario: 排除其中一個 Waler 後依 active facts 重算
- **WHEN** 使用者排除造成 relationship ambiguity 的其中一個 Waler source 並重新辨識
- **THEN** automatic calibration SHALL 只使用重新辨識時仍 active 的 relationships
- **AND** MUST NOT 重播排除前的 ambiguity outcome、暫時選擇或 endpoint calibration

#### Scenario: 完整候選未完成全列舉不得進入 calibration
- **WHEN** exact source group 的完整 hypotheses 尚未完成列舉、幾何等價合併及既有可分割性判斷
- **THEN** automatic calibration MUST NOT 選擇或延伸任何 tentative rail pair
- **AND** MUST NOT 以排序、分數、handle 或 entity order 將 tentative candidate 轉成正式中心軸

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

