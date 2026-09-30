# Spec Delta

## 閱讀導航

- **必讀**：「自動辨識與非目標系統維持既有行為」修改內容，確認 automatic occluded-rail recognition 與 manual repair 的責任分界。
- **條件式閱讀**：只有調整 unresolved／recognized repair eligibility 時才閱讀主 spec 的 create／replace requirements。
- **可先跳過**：template transfer、provenance replay 與中文 UI requirements；本 change 不修改這些 contract。

## MODIFIED Requirements

### Requirement: 自動辨識與非目標系統維持既有行為

此工具本身 MUST NOT 放寬 CornerBrace automatic recognition、改寫一般 Brace／Strut／Waler recognition，或修改 Solver 與 Project schema。Automatic recognition MAY 依獨立的 `dxf-corner-brace-occluded-rail-recognition` capability 建立通過材料寬度、遮蔽 evidence、唯一性及有限交點 hard gates 的正式 CornerBrace；該行為不屬於 repair tool 的 candidate 或 Apply 路徑。

若 automatic recognition 已建立合法完整或遮蔽 CornerBrace connection，且使用者未啟動修補，系統 SHALL 沿用其 automatic 結果。若 automatic recognition 因 body 無合法解、body 多解，或 body 已成功但 active Waler／Strut relationship 無解／多解而保留 completion-blocking unresolved source，既有 repair tool MAY 依其原有 eligibility 提供 explicit preview／adoption；problem／warning 或已成功的 body evidence 本身不得使 repair candidate 合法。未啟動修補及未採用 repair candidate 時，repair tool MUST 對 automatic result 保持零副作用，且 unresolved source 的 Review completion block SHALL 保持成立。

#### Scenario: 可靠角撐不使用修補工具
- **WHEN** CornerBrace 已由完整或遮蔽 automatic recognition 正確建立，且使用者未啟動修補
- **THEN** 系統 SHALL 維持 automatic 辨識、端點延伸與下游關聯結果
- **AND** repair tool MUST NOT 重新選擇其 rail pair 或 target relationship

#### Scenario: Automatic 無解來源仍需符合 repair eligibility
- **WHEN** automatic recognition 因無合法 rail candidate、body 多解或 active member relationship ambiguity 而保留 warning／unresolved source
- **THEN** repair tool MAY 對該來源評估既有 exact target evidence 與 reference-template eligibility
- **AND** MUST NOT 只因 automatic warning 存在而建立可 Apply repair candidate

#### Scenario: 重複 Waler relationship 不由 repair 自動解決
- **WHEN** CornerBrace body 已辨識，但兩個 active Waler sources 造成 relationship ambiguity
- **THEN** repair tool MUST NOT 合併 Waler identities、選擇 canonical Waler 或自動採用任一 relationship
- **AND** 使用者排除其中一個 Waler source 後，automatic recognition SHALL 依目前 active source facts 重新執行

#### Scenario: Unresolved source 未合法解決前維持 completion block
- **WHEN** automatic unresolved CornerBrace 尚未被排除、修正或由使用者採用通過既有 safety contract 的 repair candidate
- **THEN** DXF Review MUST NOT 完成
- **AND** repair tool MUST NOT 自動採用 candidate、刪除來源或以 warning 本身解除 completion block

#### Scenario: 修補不進入 Project schema
- **WHEN** 修補後的 DXF Review 完成匯入
- **THEN** Project row boundary SHALL 維持既有正式 Waler、Strut 與 Brace contract
- **AND** CornerBrace 詳細資料與修補 provenance SHALL 留在 DXF Review state
