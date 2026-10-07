# Spec Delta：DXF 多筆待排除來源一次重新辨識

## 閱讀導航

- **必讀**：「來源排除必須由使用者逐筆明確選取」、「來源排除必須以一次完整 canonical staging 建立結果」與新增的「待排除草稿必須與正式 Review truth 分離」；定義逐筆標記、多筆累積及一次重新辨識的主要行為。
- **必讀**：「人工決策 replay 必須安全且結果等價」與「來源排除提交必須原子且綁定 revision」；多筆合併不得降低既有工程安全或transaction保證。
- **條件式閱讀**：「逐筆入口與 source-atomic assembly 必須維持相容」；修改paired Joist、正式excluded restore、Pause／Complete或close lifecycle時必讀。
- **條件式閱讀**：「排除後畫面必須反映同一份目前結果」；修改pending樣式、Preview、selection、hit index或developer debug時必讀。
- **可先跳過**：recognition幾何門檻、CornerBrace repair eligibility／ranking、Project schema、Solver、成果匯出與changed-content recovery；本change不修改那些規則。

## MODIFIED Requirements

### Requirement: 來源排除必須由使用者逐筆明確選取

DXF Review SHALL 維持每次只由使用者明確選取一個目前 ReviewItem來加入或取消一筆待排除來源，但 SHALL 允許使用者在重新辨識前依序累積多個待排除來源。系統 MUST 對每次標記套用既有的來源存在性、角色、normalized source handles與shared-handle安全檢查，並以canonical source identity正規化、去重待排除集合。

加入或取消待排除標記 MUST NOT 執行full recognition，且 MUST NOT 修改正式recognition result、ReviewItems、`excluded_sources`、manual decisions、confirmations、coordinate state、Project、Solver、persistence或dirty state。系統 MUST NOT 自動加入任何未被使用者逐筆選取的error／critical、紅色來源、同角色來源或推測目標，也 MUST NOT 將Tree多選、框選或顏色視為排除授權。

即使待排除集合只包含一筆來源，系統亦 MUST 先建立待排除標記，再由使用者明確執行「重新辨識並套用」；系統 MUST NOT 提供略過pending draft、於選取後立即重新辨識並排除的入口。

此Requirement是DXF Review workflow與Presentation行為，不新增Engineering Hard Constraint、Solver Preference或Temporary Solver Heuristic。

#### Scenario: 明確排除一個合法來源

- **WHEN** 使用者選取一個目前可安全排除的ReviewItem並執行待排除標記
- **THEN** 系統 SHALL只加入該ReviewItem對應的canonical source identity或其既有source-atomic assembly identity
- **AND** MUST NOT在標記時執行full recognition或修改正式Review state

#### Scenario: 單筆來源也必須先標記後套用

- **WHEN** 使用者只要排除一筆合法來源
- **THEN** 系統 SHALL先將該來源標記為待排除，並等待使用者執行「重新辨識並套用」
- **AND** MUST NOT提供選取後立即重新辨識並排除的入口

#### Scenario: 逐筆標記多個合法來源

- **WHEN** 使用者依序選取三個目前可安全排除的ReviewItems並對每一筆執行待排除標記
- **THEN** 系統 SHALL 以三筆canonical source identities建立去重的待排除集合
- **AND** MUST NOT 在任一次標記時執行full recognition或修改正式Review state

#### Scenario: 取消一筆待排除標記

- **WHEN** 使用者再次操作一筆已在待排除集合中的來源
- **THEN** 系統 SHALL 只移除該筆待排除意圖並保留其他pending項目
- **AND** 正式Review state與dirty state SHALL 維持原值

#### Scenario: 取消單筆影響預覽

- **WHEN** 使用者在來源排除的aggregate impact確認選擇取消
- **THEN** Review result、正式excluded sources、manual decisions、confirmations、Project、Solver、persistence與dirty state SHALL完全維持原值
- **AND** 待排除草稿 SHALL保留供使用者調整或重試

#### Scenario: 不得自動擴張使用者選擇

- **WHEN** 使用者只標記一個目前顯示為error或critical的ReviewItem
- **THEN** 系統 SHALL 只加入該ReviewItem對應的canonical source identity或其既有source-atomic assembly identity
- **AND** MUST NOT 自動加入其他紅色、相鄰、同角色或相同severity來源

#### Scenario: 來源不再合法

- **WHEN** 選取項目不存在、角色或source identity不一致、已正式排除、或具有不能安全分離的shared-handle conflict
- **THEN** 系統 SHALL 拒絕加入待排除集合並顯示原因
- **AND** MUST NOT 留下部分pending標記或修改正式Review state

### Requirement: 來源排除必須以一次完整 canonical staging 建立結果

當使用者對非空待排除集合執行「重新辨識並套用」時，系統 SHALL 以「目前正式已排除來源」與「全部待排除來源」的canonical聯集建立一份候選exclusion set，並對該完整集合執行一次canonical staging。單次apply attempt MUST 只執行一次full recognition，並從排除後仍active的DXF sources完整重建recognition、formal members、connections、associations、diagnostics、ReviewItems與completion truth，再依既有規則capture、validate及replay全部manual decisions與confirmations。

系統 MUST 將整組待排除來源視為一個候選state transition，只產生一份final staged result、一個base revision與一份對應該result的aggregate impact。系統 MUST NOT 逐筆建立並提交中間recognition results、直接刪除舊result中的構件、複製排除前的derived relationship，或讓temporary staged result在使用者確認前成為live truth。原始DXF entities、檔案內容與source fingerprint MUST維持不變。

此Requirement是workflow correctness與效能工作邊界，不修改recognition或工程eligibility rule。

#### Scenario: 一個來源只建立一份 staged result

- **WHEN** 待排除集合只包含一筆合法canonical source identity且使用者執行一次「重新辨識並套用」
- **THEN** 系統 SHALL以完整candidate exclusion set執行一次full recognition並建立一份final staged result
- **AND** MUST NOT先修改live result再補算connections、associations或diagnostics

#### Scenario: 多筆待排除只執行一次完整辨識

- **WHEN** 待排除集合包含N筆canonical identities且N大於或等於1，使用者執行一次「重新辨識並套用」
- **THEN** 系統 SHALL 對整組candidate exclusion set執行恰好一次full recognition並建立一份final staged result
- **AND** MUST NOT 依pending項目數逐筆重複recognition或先提交中間結果

#### Scenario: 排除影響 derived outcome

- **WHEN** 任一待排除來源會影響Waler terminal、Joist association、CornerBrace repair reference、confirmation或其他derived outcome
- **THEN** staged result SHALL 只使用整組排除後仍active的來源及現行manual replay安全規則重建全部衍生結果
- **AND** MUST NOT 沿用排除前或逐筆中間狀態的relationship、diagnostic、confirmation validity或repair outcome作為新truth

#### Scenario: 顯示整組 aggregate impact

- **WHEN** 整組candidate exclusions的canonical staging成功
- **THEN** 系統 SHALL 以同一份staged result顯示構件、warning、error／critical、manual replay與confirmation invalidation的合併影響
- **AND** 畫面 SHALL註明「以下為所有待排除來源合併後的結果」
- **AND** 畫面 SHALL提示「若結果不如預期，可取消個別待排除後重新套用」
- **AND** 使用者確認前 MUST NOT 修改正式Review state

#### Scenario: 原始 DXF 保持 immutable

- **WHEN** 使用者加入、取消、預覽、確認或提交多筆待排除來源
- **THEN** 原始DXF entities、檔案bytes與source fingerprint SHALL維持不變
- **AND** exclusion SHALL只改變成功提交後的Review active-source decision與由它重建的truth

### Requirement: 人工決策 replay 必須安全且結果等價

整組待排除來源的canonical staging SHALL 重新驗證並replay全部目前人工輸入，包括Waler decisions、材料／工程線輸入與CornerBrace repairs。每一筆decision MUST依它執行時的目前staged result判定`preserved`、`needs_review`或`disabled`；系統 MUST保留既有deterministic ordering、secondary-reference dependency pass、stable reference identity、provenance、candidate validation與failure semantics。

優化replay的最終members、connections、associations、messages、repair provenance、problem／ReviewItems、completion truth與`preserved`／`needs_review`／`disabled` report MUST與對整組candidate exclusions執行canonical sequential replay等價。若無法達成等價，系統 SHALL使用canonical sequential replay的結果。

系統 MUST NOT因待排除集合包含多筆來源而省略任何人工decision的validation，也 MUST NOT把逐筆排除的先前plan、outcome或中間result串接成整組最終truth。若系統沿用既有projection、先前規劃結果或先前repair outcome，MUST能證明該repair正確性所依賴的完整輸入未改變；任何依賴已改變、遺漏、無法正規化或無法可靠比對時，MUST依目前staged result重新驗證並套用該repair。

若系統以只檢查暫時CornerBrace自身connection、並逐一和既有CornerBraces比較duplicate的候選局部驗證取代全場validation，該局部驗證對每一個候選的通過／拒絕結果 MUST與相同輸入下的現行全場validation完全相同。此最佳化 MUST使用相同connection、duplicate、geometry tolerance與target identity規則，且 MUST NOT改變候選eligibility、ranking、集合、順序、ID、provenance、diagnostics或`CornerBraceRepairPlan`輸出。

此Requirement是既有人工工程決策的安全replay contract，不改變任何Engineering Hard Constraint、repair eligibility或candidate ranking。

#### Scenario: 未受影響的 repair 避免不必要的全角色重算

- **WHEN** 整組staging需要處理一筆可證明未受排除或先前decision影響的CornerBrace repair
- **THEN** 系統 MUST NOT僅因需要處理該repair，就無條件重建所有角色的完整problem／ReviewItem
- **AND** 系統 MAY重新replay、共用安全projection，或在完整輸入未變時沿用先前outcome

#### Scenario: 沿用先前 repair outcome

- **WHEN** 系統準備沿用排除前或先前replay已產生的repair outcome
- **THEN** 系統 MUST先證明該repair正確性所依賴的完整輸入未改變
- **AND** 沿用後的最終結果仍 MUST與整組candidate exclusions的canonical sequential replay等價

#### Scenario: 多筆排除仍完整replay所有人工輸入

- **WHEN** 整組candidate exclusions進入canonical staging
- **THEN** 系統 SHALL 對全部目前manual decisions執行一次完整、安全且依序的replay
- **AND** MUST NOT因多筆來源合併而略過無直接相同source handle的decision

#### Scenario: 依賴改變或無法可靠比對

- **WHEN** repair的任一依賴因整組排除而改變，或系統無法完整取得、正規化或可靠比對其依賴輸入
- **THEN** 系統 MUST依目前staged result重新驗證並套用該repair
- **AND** MUST NOT以距離、沒有直接相同source handle或局部identity未變作為充分沿用證明

#### Scenario: Secondary reference 需要後續 pass

- **WHEN** repair因manual secondary reference尚未由前置repair建立而需要延後
- **THEN** 系統 SHALL維持既有deterministic dependency pass並在前置repair成功後重新驗證
- **AND** MUST NOT為減少整組replay工作而提早標記preserved、改用其他reference或跳過驗證

#### Scenario: 優化結果與 canonical replay 等價

- **WHEN** 相同整組candidate exclusions與manual decisions分別經optimized replay及canonical sequential replay處理
- **THEN** 兩者的正式構件、connections、associations、messages、repair provenance、problem／ReviewItems、completion truth與replay report SHALL等價
- **AND** 若無法達成等價，系統 SHALL使用canonical sequential replay結果

#### Scenario: 候選局部驗證與全場驗證逐筆等價

- **WHEN** 系統對同一份目前result、同一個暫時CornerBrace候選、相同target Waler／Strut與相同tolerances，分別執行候選局部驗證及既有全場validation
- **THEN** 兩條路徑對該候選的通過或拒絕結果 MUST完全相同
- **AND** 局部路徑 SHALL保留connection唯一性、target identity匹配、candidate connection messages與duplicate判斷的全部既有語意
- **AND** 任何不等價候選 MUST使用既有全場validation結果

### Requirement: 來源排除提交必須原子且綁定 revision

待排除草稿與其產生的每一份exclusion plan MUST綁定建立時的Review base revision及source fingerprint。Plan另 MUST包含normalized exclusion set、staged world／projected result、problem projection、ReviewItems、manual replay report、revalidated confirmations、candidate projection與aggregate impact。只有使用者確認同一份aggregate impact，且目前Review revision與source fingerprint仍等於plan及pending draft的base時，系統才可提交。

成功提交 SHALL在一個workflow state transition中採用同一份plan的全部資料，只產生一次revision increment，並在提交成功後清空待排除草稿。所有可能失敗且依賴staged result的衍生建立 MUST在修改live state前完成；任一pending draft或plan stale、recognition／replay／projection／commit失敗時，系統 MUST拒絕或rollback整筆，保留提交前的完整Review state與待排除草稿，不得留下部分exclusion、混合新舊result／ReviewItems、遺失manual decision、部分confirmation invalidation或candidate projection。

建立pending、staging、aggregate impact取消或失敗 MUST NOT將Project標為dirty；成功commit的dirty／pause persistence行為 SHALL沿用既有來源排除contract。

#### Scenario: 使用者確認同一份 plan 後提交

- **WHEN** 使用者確認一份base revision與source fingerprint仍有效的aggregate exclusion plan
- **THEN** 系統 SHALL一次採用該plan的exclusions、results、problems、ReviewItems、manual replay、confirmations與candidate projection
- **AND** SHALL只增加一次Review revision並清空全部pending exclusions

#### Scenario: 使用者取消aggregate impact

- **WHEN** canonical staging成功但使用者取消aggregate impact確認
- **THEN** 正式Review state SHALL完全維持原值
- **AND** 待排除草稿 SHALL保留供使用者調整或重試

#### Scenario: Preview 後 revision 改變

- **WHEN** 待排除草稿建立後目前Review revision或source fingerprint與其base不一致
- **THEN** 系統 MUST拒絕重新辨識或提交並把該草稿標示為stale
- **AND** MUST NOT自動rebase、改選來源或套用任何exclusion

#### Scenario: Staging 或 commit 失敗

- **WHEN** 整組plan在recognition、manual replay、validation、problem／ReviewItem、confirmation、candidate projection或state adoption的任一步驟失敗
- **THEN** 系統 MUST保留或恢復提交前的完整Review snapshot
- **AND** 待排除草稿 SHALL保留且 MUST NOT留下任何部分排除效果

### Requirement: 逐筆入口與 source-atomic assembly 必須維持相容

每次pending mark／unmark仍 SHALL由一個目前ReviewItem明確啟動；多筆待排除只合併重新辨識與commit，不得改變單筆來源eligibility、canonical identity或source-atomic assembly規則。不同ReviewItems若共用同一既有source-atomic identity，例如paired BIM Joist的兩個sibling Beam IDs，標記任一sibling SHALL只建立一筆shared-root pending decision，成功提交時一次排除整個assembly。

既有正式excluded source的restore在沒有pending draft時 SHALL維持現行單筆staging、impact、revision與commit行為；pending draft非空時系統 MUST拒絕restore並要求先套用或捨棄pending。本capability MUST NOT新增pending restore、batch restore或persistence schema；保存時仍只使用成功提交後的normalized `excluded_sources`。

既有Pause／Resume、Exact Match Relink、compatible recovery與Project apply工程語意 SHALL維持不變；pending draft不得進入這些durable或recovery contracts。

#### Scenario: Paired Joist sibling 仍排除整個 assembly

- **WHEN** 使用者依序對paired BIM Joist root的兩個sibling Beam ReviewItems執行待排除標記
- **THEN** 系統 SHALL以shared root的同一筆canonical source identity去重pending decision
- **AND** 成功提交時 SHALL一次排除整個assembly而非建立兩筆正式exclusions

#### Scenario: Restore 流程維持既有語意

- **WHEN** 待排除草稿為空且使用者對一筆既有excluded source執行restore
- **THEN** 系統 SHALL沿用現有單筆restore staging、impact、revision與commit行為
- **AND** SHALL NOT建立pending restore或batch restore state

#### Scenario: 有pending時拒絕restore

- **WHEN** 待排除草稿非空且使用者嘗試restore正式excluded source
- **THEN** 系統 SHALL拒絕restore並提示先套用或捨棄pending exclusions
- **AND** 正式Review state與pending draft SHALL維持原值

#### Scenario: Persistence schema 不變

- **WHEN** 多筆待排除成功提交並暫停或保存Review
- **THEN** 系統 SHALL只以既有normalized `excluded_sources`集合持久化正式結果
- **AND** MUST NOT保存pending draft、aggregate impact、temporary plan、render effects或新增Project schema欄位

### Requirement: 排除後畫面必須反映同一份目前結果

待排除草稿非空時，Review清單與Preview SHALL以不同於正式excluded的明確pending樣式標示對應來源，並顯示pending數量及「尚未重新辨識」狀態。Pending樣式 MUST NOT改變正式ReviewItems、problems、engineering members、connections、completion truth、selection eligibility或hit-test identity；這些工程投影仍 SHALL反映上一次committed result。

成功提交整組來源排除後，Review清單、問題投影、Preview engineering members、正式來源排除樣式、selection、focus、hit index、完成狀態與工程資料 SHALL全部反映同一份committed result，且所有pending樣式與計數 SHALL清除。系統 MUST NOT為減少重繪而保留stale member、stale problem、舊excluded／pending style、舊render-generation hit index或排除前的selectable target。

若原始source geometry與目前viewport bounds未因操作改變，系統 SHALL保留使用者提交前viewport。系統 MAY局部更新changed layers，但局部刷新後的可見工程結果、來源樣式、selection priority與hit-test outcome MUST與正確full refresh等價；若無法安全證明，MUST使用full refresh fallback。

開發者debug內容在未顯示時 SHALL可延後建立，且不得成為pending標記或整組commit完成的前置條件。使用者實際開啟或刷新debug內容時，系統 MUST依目前committed revision產生正式資料；未提交pending可另行標示，但 MUST NOT混入或冒充committed recognition payload。

此Requirement是Presentation一致性與互動行為，不新增Engineering Hard Constraint、Solver Preference或Temporary Solver Heuristic。

#### Scenario: Pending樣式不改工程truth

- **WHEN** 使用者標記一筆或多筆待排除來源但尚未執行重新辨識
- **THEN** 畫面 SHALL清楚標示pending來源與數量
- **AND** problems、members、relationships、completion status與hit-test identity SHALL仍來自目前committed result

#### Scenario: 成功提交保留 viewport 並更新目前結果

- **WHEN** 整組exclusion commit成功且原始source geometry與viewport bounds未改變
- **THEN** Preview SHALL保留提交前viewport並清除全部pending樣式
- **AND** 構件、問題、正式excluded style、selection／focus與完成狀態 SHALL反映同一份committed result

#### Scenario: 排除後舊 hit target 不得命中

- **WHEN** 整組exclusion commit使一個unresolved source成為正式excluded，或使ReviewItems／可見來源選取資格改變
- **THEN** 先前render generation的source hit index MUST視為失效
- **AND** 後續點擊 MUST使用目前畫面與目前ReviewItems，或安全地不命中
- **AND** MUST NOT選取stale unresolved ReviewItem

#### Scenario: 局部刷新與完整刷新等價

- **WHEN** Presentation判定source geometry未變並使用局部刷新
- **THEN** 使用者可見的正式來源樣式、formal members、problems、selection priority與hit-test outcome SHALL與同一committed result的正確full refresh等價
- **AND** 若等價條件不成立，系統 SHALL使用full refresh fallback

#### Scenario: 開啟 debug 顯示目前 revision

- **WHEN** 使用者在pending存在或整組commit後開啟或刷新developer debug
- **THEN** 正式recognition payload SHALL由目前committed Review revision產生
- **AND** MUST NOT把未提交pending exclusions呈現為已辨識或已正式排除的工程truth

#### Scenario: 隱藏的 developer debug 不阻擋提交

- **WHEN** developer debug目前未顯示且使用者mark／unmark pending或提交整組來源排除
- **THEN** 系統 SHALL完成pending投影或正式Review commit，而不要求先建立完整debug payload
- **AND** hidden debug state MUST NOT改變pending、staging或commit outcome

## RENAMED Requirements

- FROM: `### Requirement: 單筆來源排除必須由使用者明確啟動`
- TO: `### Requirement: 來源排除必須由使用者逐筆明確選取`
- FROM: `### Requirement: 單筆排除必須建立完整 canonical staged result`
- TO: `### Requirement: 來源排除必須以一次完整 canonical staging 建立結果`
- FROM: `### Requirement: 單筆入口與 source-atomic assembly 必須維持相容`
- TO: `### Requirement: 逐筆入口與 source-atomic assembly 必須維持相容`

## ADDED Requirements

### Requirement: 待排除草稿必須與正式 Review truth 分離

系統 SHALL將待排除草稿視為目前live DXF Review session中的暫時操作意圖，並以其建立時的Review revision、source fingerprint及canonical source identities識別。待排除草稿 MUST有單一workflow owner；Presentation只能顯示snapshot與發出mark、unmark、apply或discard命令，不得另存第二份可獨立修改的pending集合。

待排除草稿非空時，系統 SHALL允許不修改Review truth的selection、inspection、filter、zoom、pan及pending mark／unmark操作，但 MUST拒絕manual repair、confirmation、圖層用途、座標、正式restore、Pause、Complete及其他會修改Review truth或其revision的操作，並提示先套用或捨棄pending。

Pending draft MUST NOT寫入Review state、Project payload或dirty state。使用者關閉DXF Review時若pending非空，系統 MUST要求明確捨棄pending或取消關閉；不得靜默保存、提交或遺失pending後繼續Pause／Complete。

此Requirement是workflow transaction與Presentation action-state行為，不修改任何工程或Solver規則。

#### Scenario: Pending期間允許唯讀操作

- **WHEN** 待排除草稿非空且使用者執行selection、inspection、filter、zoom或pan
- **THEN** 系統 SHALL允許該操作並維持pending draft
- **AND** MUST NOT改變Review revision或正式工程truth

#### Scenario: Pending期間拒絕工程mutation

- **WHEN** 待排除草稿非空且使用者嘗試manual repair、confirmation、圖層用途、座標、正式restore、Pause或Complete
- **THEN** 系統 SHALL拒絕該操作並提示先套用或捨棄pending
- **AND** 正式Review state與pending draft SHALL維持原值

#### Scenario: 明確捨棄pending

- **WHEN** 使用者選擇捨棄全部待排除來源
- **THEN** 系統 SHALL清空pending draft及其視覺標記
- **AND** 正式Review state、persistence與dirty state SHALL維持原值

#### Scenario: 關閉時不得靜默遺失pending

- **WHEN** 待排除草稿非空且使用者要求關閉DXF Review
- **THEN** 系統 SHALL提供捨棄pending或取消關閉的明確選擇
- **AND** MUST NOT把pending寫入Project、靜默套用或在未取得捨棄確認時關閉

#### Scenario: 無pending時重新辨識入口不執行工作

- **WHEN** 待排除草稿為空
- **THEN** 「重新辨識並套用」入口 SHALL不可執行或回傳no-op
- **AND** MUST NOT執行recognition、增加revision或修改dirty state
