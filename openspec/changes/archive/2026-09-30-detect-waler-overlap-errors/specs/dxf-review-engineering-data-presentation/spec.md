# Spec Delta

## 閱讀導航

- **必讀**：「Preview 必須區分正式接觸面與 provisional axis」Requirement；定義 unresolved Waler 的可見呈現。
- **條件式閱讀**：「Review 必須呈現重疊來源與重建資訊」Requirement；修改 problem list、工程資料或來源定位互動時必讀。
- **可先跳過**：重疊資格與 contact-face finalization 算法；Presentation 只投影既有 staged truth。

## ADDED Requirements

### Requirement: Preview 必須區分正式接觸面與 provisional axis

DXF Review Preview SHALL 使用不會被合理誤認為正式 Waler engineering line 的視覺語意呈現 unresolved／ambiguous Waler provisional axis。正式完成 contact-face finalization 的 Waler SHALL 維持正式工程線呈現；未完成者 SHALL 以不同線型、色彩、標記或等價的明確方式顯示 provisional 狀態。Presentation MUST 只消費目前 staged recognition／contact-face state，不得自行推導重疊、關係或接觸面。

Preview 的 viewport、selection、highlight 或重繪 MUST NOT 改變 Waler 的 formal／provisional truth。若某 Waler 沒有正式接觸面，Preview MUST NOT 因其具有 `closed_outline_axis`、selected candidate 或可畫線段而將它渲染成已完成正式辨識。

#### Scenario: W17 與 W20 的 provisional axes 不偽裝為正式線

- **WHEN** Y29 W17 與 W20 因重疊競爭而維持 unresolved contact-face state
- **THEN** Preview SHALL 將兩支 provisional axes 與正式 Waler engineering lines 明確區分
- **AND** MUST NOT 顯示成兩支已成功完成內側接觸面判定的正式線

#### Scenario: 排除來源後更新為正式線

- **WHEN** 排除 W17 或 W20 後，剩餘 Waler 完成 contact-face finalization
- **THEN** Preview SHALL 依目前 staged truth 將剩餘 Waler 顯示為正式 engineering line
- **AND** SHALL 移除該 pair 的 stale provisional／competition 呈現

#### Scenario: 重繪與選取不改變工程 truth

- **WHEN** 使用者縮放、平移、選取 Waler 或觸發 Preview 重繪
- **THEN** formal／provisional 狀態與 staged `DXFImportResult` SHALL 保持不變

### Requirement: Review 必須呈現重疊來源與重建資訊

對重大共線重疊 warning 或 blocking competition error，DXF Review SHALL 讓使用者定位所有參與的 Waler sources，並顯示重疊原因、重疊比例及目前是否阻擋完成。Blocking competition error SHALL 顯示 direct identity provenance 所指向的受影響 terminal 或 contact-face finalization context。Review SHALL 中性說明 active sources 變更後會重新辨識，但 MUST NOT 推薦、暗示或預選應刪除、排除、保留的 Waler winner。

Presentation MUST NOT 建立第二份 overlap qualification、direct identity join、connection 或 contact-face 規則，也不得將 source handle、Treeview item ID、顯示 ID 或 collection index 當成正式 identity。顯示內容 SHALL 由目前 staged diagnostics 與 source provenance 唯讀投影；Presentation MUST NOT 因附近另有 unresolved outcome 而自行把 warning 升級為 blocking。

#### Scenario: Blocking overlap 可定位兩方來源

- **WHEN** W17（source `69C`）與 W20（source `721`）形成 blocking competition
- **THEN** Review SHALL 顯示並可定位兩方 sources、重大重疊原因與 blocking 狀態
- **AND** SHALL 顯示 direct provenance 所指向的受影響 terminal 或 finalization context
- **AND** SHALL 中性說明 active sources 變更後會重新辨識
- **AND** MUST NOT 推薦排除、刪除或保留 W17、W20 的任一方

#### Scenario: 純 overlap warning 不偽裝成 blocking error

- **WHEN** 重大共線重疊沒有造成 terminal 或 contact-face 多解
- **THEN** Review SHALL 顯示 warning 而非 blocking error
- **AND** SHALL 不因該 warning 單獨阻止完成

#### Scenario: 其他 unresolved 不改變 overlap pair 的顯示層級

- **WHEN** A／B overlap 只有 warning，而 staged diagnostics 的 unresolved outcome 沒有 A、B 同時競爭同一 terminal／finalization 的 direct provenance
- **THEN** Review SHALL 維持 A／B warning-only 呈現
- **AND** MUST NOT 自行建立 A／B blocking 標示或 winner 建議

#### Scenario: Rebuild 後只呈現目前診斷

- **WHEN** source exclusion／restore、Pause／Resume、recovery 或 rebuild 改變目前 overlap／competition outcomes
- **THEN** Review SHALL 只呈現目前 staged diagnostics 與 identities
- **AND** MUST NOT 顯示已不存在 pair 的 stale 問題或先前 UI identity

