# Spec Delta：DXF 單筆來源排除流程

## 閱讀導航

- **必讀**：「單筆來源排除必須由使用者明確啟動」、「單筆排除必須建立完整 canonical staged result」與「人工決策 replay 必須安全且結果等價」；定義本 capability 的主要行為與效能安全邊界。
- **必讀**：「來源排除提交必須原子且綁定 revision」；定義 preview、cancel、stale 與 failure 的 transaction 語意。
- **條件式閱讀**：「單筆入口與 source-atomic assembly 必須維持相容」；修改 paired Joist、restore 或 persistence 時必讀。
- **條件式閱讀**：「排除後畫面必須反映同一份目前結果」；修改 Preview、hit index、viewport 或 developer debug 時必讀。
- **可先跳過**：recognition 幾何門檻、CornerBrace repair eligibility／ranking、Project schema、Solver、成果匯出與 changed-content recovery；本 capability 不修改那些規則。

## Purpose

定義 DXF Review 如何維持使用者逐筆排除來源的既有操作，同時減少單次完整重建內人工修補 replay 與畫面更新的重複工作，並確保優化結果與既有 canonical 安全流程一致。

## ADDED Requirements

### Requirement: 單筆來源排除必須由使用者明確啟動

DXF Review SHALL 維持一次只處理一個目前 ReviewItem 的來源排除流程。使用者 MUST 明確選取該項目、預覽其影響並確認後，系統才可修改正式 Review state。系統 MUST 對該項目套用既有的來源存在性、角色、normalized source handles 與 shared-handle 安全檢查。

選取、開啟影響預覽或取消確認在 commit 前 MUST NOT 修改 recognition result、ReviewItems、excluded sources、manual decisions、confirmations、coordinate state、Project、Solver、persistence 或 dirty state。系統 MUST NOT 提供或隱含多選來源、批次排除、自動排除全部 error／critical 或依顏色推測排除目標的行為。

此 Requirement 是 DXF Review workflow 與 Presentation 行為，不新增 Engineering Hard Constraint、Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 明確排除一個合法來源

- **WHEN** 使用者選取一個目前可安全排除的 ReviewItem、查看影響並確認
- **THEN** 系統 SHALL 只針對該 ReviewItem 的 canonical source identity 建立一份來源排除 plan
- **AND** MUST NOT 加入任何未被使用者選取的紅色或錯誤來源

#### Scenario: 取消單筆影響預覽

- **WHEN** 使用者開啟單筆來源排除影響後選擇取消
- **THEN** Review result、excluded sources、manual decisions、confirmations、Project、Solver、persistence 與 dirty state SHALL 完全維持原值

#### Scenario: 來源不再合法

- **WHEN** 選取項目在 staging 時已不存在、角色或 source identity 不一致、已排除或具有不能安全分離的 shared-handle conflict
- **THEN** 系統 SHALL 拒絕建立可提交 plan並顯示原因
- **AND** MUST NOT 留下 staged mutation 或部分排除效果

### Requirement: 單筆排除必須建立完整 canonical staged result

系統 SHALL 以「目前已排除來源」與「本次一個 selected source identity」的 canonical 聯集建立一份候選 exclusion set，並對該完整集合執行一次 canonical staging。該 staging MUST 從排除後仍 active 的 DXF sources 完整重建 recognition、formal members、connections、associations、diagnostics、ReviewItems 與 completion truth，並依既有規則 capture、validate 及 replay 全部 manual decisions 與 confirmations。

系統 MUST 將單筆來源排除視為一個候選 state transition，只產生一份 final staged result、一個 base revision 與一份對應該 result 的影響預覽。系統 MUST NOT 直接刪除舊 result 中的構件、複製排除前的 derived relationship，或讓 temporary staged result 在確認前成為 live truth。原始 DXF entities、檔案內容與 source fingerprint MUST 維持不變。

此 Requirement 是 workflow correctness 與效能工作邊界，不修改 recognition 或工程 eligibility rule。

#### Scenario: 一個來源只建立一份 staged result

- **WHEN** 使用者預覽排除一個合法 source identity
- **THEN** 系統 SHALL 以完整 candidate exclusion set 執行一次 full recognition 並建立一份 final staged result
- **AND** MUST NOT 先修改 live result 再補算 connections、associations 或 diagnostics

#### Scenario: 排除影響 derived outcome

- **WHEN** 被排除來源會影響 Waler terminal、Joist association、CornerBrace repair reference、confirmation 或其他 derived outcome
- **THEN** staged result SHALL 只使用排除後仍 active 的來源及現行 manual replay 安全規則重建全部衍生結果
- **AND** MUST NOT 沿用排除前的 relationship、diagnostic、confirmation validity 或 repair outcome 作為新 truth

#### Scenario: 原始 DXF 保持 immutable

- **WHEN** 使用者建立、取消或提交單筆來源排除
- **THEN** 原始 DXF entities、檔案 bytes 與 source fingerprint SHALL 維持不變
- **AND** exclusion SHALL 只改變 Review active-source decision 與由它重建的 staged truth

### Requirement: 人工決策 replay 必須安全且結果等價

單筆來源排除的 canonical staging SHALL 重新驗證並 replay 全部目前人工輸入，包括 Waler decisions、材料／工程線輸入與 CornerBrace repairs。每一筆 decision MUST 依它執行時的目前 staged result 判定 `preserved`、`needs_review` 或 `disabled`；系統 MUST 保留既有 deterministic ordering、secondary-reference dependency pass、provenance、candidate validation 與 failure semantics。

優化 replay 的最終 members、connections、associations、messages、repair provenance、problem／ReviewItems、completion truth 與 `preserved`／`needs_review`／`disabled` report MUST 與對每筆 decision 使用當下 result 完整重算的 canonical sequential replay 等價。若無法達成等價，系統 SHALL 使用 canonical sequential replay 的結果。

系統 MUST NOT 對可證明未受影響的 repair，無條件重建與該 repair 無關的所有角色完整 problem／ReviewItem。若系統沿用既有 projection、先前規劃結果或先前 repair outcome，MUST 能證明該 repair 正確性所依賴的完整輸入未改變；任何依賴已改變、遺漏、無法正規化或無法可靠比對時，MUST 依目前 staged result 重新驗證並套用該 repair。

若系統以只檢查暫時 CornerBrace 自身 connection、並逐一和既有 CornerBraces 比較 duplicate 的候選局部驗證取代目前全場 validation，該局部驗證對每一個候選的通過／拒絕結果 MUST 與相同輸入下的現行全場 validation 完全相同。此最佳化 MUST 使用相同 connection、duplicate、geometry tolerance與target identity規則，且 MUST NOT 改變候選 eligibility、ranking、集合、順序、ID、provenance、diagnostics或`CornerBraceRepairPlan`輸出。

此 Requirement 是既有人工工程決策的安全 replay contract，不改變任何 Engineering Hard Constraint、repair eligibility 或 candidate ranking。

#### Scenario: 未受影響的 repair 避免不必要的全角色重算

- **WHEN** 單次 staging 需要處理一筆可證明未受排除或先前 decision 影響的 CornerBrace repair
- **THEN** 系統 MUST NOT 僅因需要處理該 repair，就無條件重建所有角色的完整 problem／ReviewItem
- **AND** 系統 MAY 重新 replay、共用安全 projection，或在完整輸入未變時沿用先前 outcome

#### Scenario: 沿用先前 repair outcome

- **WHEN** 系統準備沿用排除前或先前 replay 已產生的 repair outcome
- **THEN** 系統 MUST 先證明該 repair 正確性所依賴的完整輸入未改變
- **AND** 沿用後的最終結果仍 MUST 與 canonical sequential replay 等價

#### Scenario: 依賴改變或無法可靠比對

- **WHEN** repair 的任一依賴已改變，或系統無法完整取得、正規化或可靠比對其依賴輸入
- **THEN** 系統 MUST 依目前 staged result 重新驗證並套用該 repair
- **AND** MUST NOT 以距離、沒有直接相同 source handle 或局部 identity 未變作為充分的沿用證明

#### Scenario: Secondary reference 需要後續 pass

- **WHEN** repair 因 manual secondary reference 尚未由前置 repair 建立而需要延後
- **THEN** 系統 SHALL 維持既有 deterministic dependency pass並在前置 repair 成功後重新驗證
- **AND** MUST NOT 為減少重建次數而提早標記 preserved、改用其他 reference 或跳過驗證

#### Scenario: 優化結果與 canonical replay 等價

- **WHEN** 相同 staged input與 manual decisions 分別經 optimized replay及 canonical sequential replay處理
- **THEN** 兩者的正式構件、connections、associations、messages、repair provenance、problem／ReviewItems、completion truth與 replay report SHALL 等價
- **AND** 若無法達成等價，系統 SHALL 使用 canonical sequential replay結果

#### Scenario: 候選局部驗證與全場驗證逐筆等價

- **WHEN** 系統對同一份目前 result、同一個暫時 CornerBrace候選、相同target Waler／Strut與相同tolerances，分別執行候選局部驗證及既有全場validation
- **THEN** 兩條路徑對該候選的通過或拒絕結果 MUST 完全相同
- **AND** 局部路徑 SHALL 保留connection唯一性、target identity匹配、candidate connection messages與duplicate判斷的全部既有語意
- **AND** differential test SHALL 對同一輸入產生的每個候選比較兩條路徑；任何不等價候選 MUST 使用既有全場validation結果

### Requirement: 來源排除提交必須原子且綁定 revision

每一份 exclusion plan MUST 綁定建立時的 Review base revision、normalized exclusion set、staged world／projected result、problem projection、ReviewItems、manual replay report、revalidated confirmations 與 candidate projection。只有使用者確認同一份影響預覽，且目前 Review revision 仍等於 plan 的 base revision 時，系統才可提交。

成功提交 SHALL 在一個 workflow state transition 中採用同一份 plan 的全部資料，並只產生一次 revision increment。所有可能失敗且依賴 staged result 的衍生建立 MUST 在修改 live state 前完成；任一 plan payload stale 或 staging／commit 失敗時，系統 MUST 拒絕或 rollback 整筆，不得留下部分 exclusion、混合新舊 result／ReviewItems、遺失 manual decision、部分 confirmation invalidation 或 candidate projection。

Staging 本身 MUST NOT 將 Project 標為 dirty；成功 commit 的 dirty／pause persistence 行為 SHALL 沿用既有單筆來源排除 contract。

#### Scenario: 使用者確認同一份 plan 後提交

- **WHEN** 使用者確認一份 base revision 仍有效的單筆來源排除 plan
- **THEN** 系統 SHALL 一次採用該 plan 的 exclusions、results、problems、ReviewItems、manual replay、confirmations 與 candidate projection
- **AND** SHALL 只增加一次 Review revision

#### Scenario: Preview 後 revision 改變

- **WHEN** plan 建立後，目前 Review revision 因其他合法操作而改變
- **THEN** 系統 MUST 拒絕提交 stale plan
- **AND** SHALL 保留目前 Review state，不得套用該 plan 的任何 exclusion或 projection

#### Scenario: Staging 或 commit 失敗

- **WHEN** exclusion plan 在 recognition、manual replay、validation、problem／ReviewItem、confirmation、candidate projection 或 state adoption 的任一步驟失敗
- **THEN** 系統 MUST 保留或恢復提交前的完整 Review snapshot
- **AND** MUST NOT 留下任何部分排除效果

### Requirement: 單筆入口與 source-atomic assembly 必須維持相容

既有單筆 exclude／restore 的 eligibility、impact、confirmation invalidation、manual replay、dirty 與 persistence outcome MUST 與本 change 前的安全契約等價。不同 ReviewItems 若共用同一既有 source-atomic identity，例如 paired BIM Joist 的兩個 sibling Beam IDs，排除任一 sibling 仍 SHALL 一次移除整個 shared-root assembly並形成一筆 excluded source decision。

既有 restore、Pause／Resume、Exact Match Relink、compatible recovery 與 Project apply 行為 SHALL 維持不變。本 capability MUST NOT 新增多來源排除、batch restore 或 persistence schema；保存時仍只使用既有 normalized excluded sources。

#### Scenario: Paired Joist sibling 仍排除整個 assembly

- **WHEN** 使用者對 paired BIM Joist root 的任一 sibling Beam ReviewItem執行單筆來源排除
- **THEN** 系統 SHALL 以 shared root 的一筆 canonical source identity 排除整個 assembly
- **AND** MUST NOT 將 siblings 拆成獨立 exclusion decisions

#### Scenario: Restore 流程維持既有語意

- **WHEN** 使用者對一筆既有 excluded source 執行 restore
- **THEN** 系統 SHALL 沿用現有單筆 restore staging、impact、revision與commit行為
- **AND** SHALL NOT 建立多來源或 batch restore state

#### Scenario: Persistence schema 不變

- **WHEN** 單筆來源排除成功並暫停或保存 Review
- **THEN** 系統 SHALL 以既有 normalized excluded sources集合持久化結果
- **AND** MUST NOT 保存 replay projection、temporary plan、render effects、debug cache 或新增 Project schema欄位

### Requirement: 排除後畫面必須反映同一份目前結果

成功提交單筆來源排除後，Review 清單、問題投影、Preview engineering members、來源排除樣式、selection、focus、hit index、完成狀態與工程資料 SHALL 全部反映同一份 committed result。系統 MUST NOT 為減少重繪而保留 stale member、stale problem、舊 excluded style、舊 render-generation hit index 或排除前的 selectable target。

若原始 source geometry 與目前 viewport bounds 未因操作改變，系統 SHALL 保留使用者提交前的 viewport，不得只因 exclusion commit 自動縮放至全圖。系統 MAY 局部更新 changed layers，但局部刷新後的可見工程結果、來源樣式、selection priority 與 hit-test outcome MUST 與正確 full refresh 等價；若無法安全證明，MUST 使用 full refresh fallback。

開發者 debug 內容在未顯示時 SHALL 可延後建立，且不得成為一般 exclusion commit 完成的前置條件。使用者實際開啟或刷新 debug 內容時，系統 MUST 依目前 committed revision 產生資料，不得顯示先前 revision payload。Partial refresh、fallback 與 lazy debug MUST NOT 修改 staged engineering truth、diagnostic identity、completion condition 或 persistence state。

此 Requirement 是 Presentation 一致性與互動行為，不新增 Engineering Hard Constraint、Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 成功提交保留 viewport 並更新目前結果

- **WHEN** 單筆 exclusion commit成功，且原始 source geometry與目前 viewport bounds未改變
- **THEN** Preview SHALL 保留提交前 viewport
- **AND** 構件、問題、excluded style、selection／focus與完成狀態 SHALL 反映同一份 committed result

#### Scenario: 排除後舊 hit target 不得命中

- **WHEN** exclusion commit使一個 unresolved source成為 excluded，或使 ReviewItems／可見來源選取資格改變
- **THEN** 先前 render generation 的 source hit index MUST 視為失效
- **AND** 後續點擊 MUST 使用目前畫面與目前 ReviewItems，或安全地不命中
- **AND** MUST NOT 選取 stale unresolved ReviewItem

#### Scenario: 局部刷新與完整刷新等價

- **WHEN** Presentation 判定 source geometry未變並使用局部刷新
- **THEN** 使用者可見的來源樣式、正式構件、問題、selection priority與 hit-test outcome SHALL 與同一 committed result的正確 full refresh等價
- **AND** 若等價條件不成立，系統 SHALL 使用 full refresh fallback

#### Scenario: 隱藏的 developer debug 不阻擋提交

- **WHEN** developer debug目前未顯示且使用者提交單筆來源排除
- **THEN** 系統 SHALL 完成 Review commit與一般畫面更新，而不要求先建立完整 debug payload
- **AND** hidden debug state MUST NOT 改變 commit outcome

#### Scenario: 開啟 debug 顯示目前 revision

- **WHEN** 使用者在一個或多個 exclusion commits後開啟或刷新 developer debug
- **THEN** 顯示資料 SHALL 由目前 committed Review revision產生
- **AND** MUST NOT 顯示先前 revision的 exclusions、members、diagnostics或 manual replay outcome
