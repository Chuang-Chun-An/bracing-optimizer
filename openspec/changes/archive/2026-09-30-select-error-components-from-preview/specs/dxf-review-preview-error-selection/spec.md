# Spec Delta

## 閱讀導航

- **必讀**：「圖面可選取未解析錯誤來源」與其唯一命中、viewport 同步、實際繪製可見性 scenarios；定義本 capability 的核心使用者行為。
- **必讀**：「重疊歧義與既有操作優先序」；定義多重命中時不得猜測，以及現有圖面操作不得被搶走。
- **條件式閱讀**：「錯誤來源選取不得改變正式資料」；修改 Review workflow、資料模型、持久化或修正工具時必讀。
- **可先跳過**：DXF recognition、工程關聯、Solver、Project apply 與 persistence specs；本 capability 只定義 Preview 的 Presentation selection。

## Purpose

定義 DXF Review 預覽圖對未解析 error／critical 來源的直接選取、清單與明細同步、重疊歧義處理及無資料副作用邊界，讓使用者能從可見錯誤幾何快速進入既有檢核流程。

## ADDED Requirements

### Requirement: 圖面可選取未解析錯誤來源

DXF Review 預覽圖 SHALL 允許使用者以滑鼠左鍵選取目前可見、最高嚴重度為 `error` 或 `critical`，且尚未形成正式 member 的 ReviewItem 來源幾何。「目前可見」MUST 以該來源是否實際繪製於目前畫面為準：因目前 selection 的 `focus_handles` 而在來源圖層隱藏時仍被強制繪製的幾何 SHALL 視為可見；沒有實際繪製的來源一律 MUST NOT 命中。系統 MUST 以目前 ReviewItem 所保存的 source handles 建立對應；一次點擊所命中的所有線段若只對應同一 ReviewItem，系統 SHALL 將其視為唯一命中，而不得因同一來源具有多段幾何或同一 ReviewItem 具有多個 source handles 而判為歧義。

用於 source selection 的 hit index MUST 對應目前 viewport transform 與目前 render generation。viewport 平移或縮放、source visibility、ReviewItems 或 active result 任一改變後，既有 index MUST 立即視為失效；點擊或 hover 在 index 失效時 MUST 先以目前畫面狀態重建，或不執行命中判斷，且 MUST NOT 使用舊螢幕座標判斷命中。

唯一命中後，系統 SHALL 選取對應 ReviewItem、同步既有構件清單與問題明細，並使用既有來源聚焦效果標示其全部 source handles。該選取 SHALL 清除先前的正式 member selection，但 MUST NOT 建立虛構 member ID、候選點或正式工程線。可點選來源在滑鼠 hover 時 SHALL 提供游標或等價的可互動提示。

此 Requirement 是 Presentation 行為，不是 Engineering Hard Constraint、Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 點選唯一未解析錯誤來源

- **WHEN** 預覽圖顯示一個最高嚴重度為 `error` 或 `critical` 的 unresolved ReviewItem 來源幾何
- **AND** 使用者以左鍵點擊命中該 ReviewItem，且沒有其他不同 ReviewItem 同時命中
- **THEN** 系統 SHALL 選取該 ReviewItem
- **AND** SHALL 同步構件清單、問題明細與其全部 source handles 的來源聚焦效果
- **AND** SHALL 清除先前的正式 member selection

#### Scenario: 同一 ReviewItem 的多段幾何仍為唯一命中

- **WHEN** 一次點擊命中同一 unresolved error／critical ReviewItem 的兩段以上來源幾何，或命中該 ReviewItem 的兩個以上 source handles
- **AND** 沒有命中其他不同 ReviewItem
- **THEN** 系統 SHALL 將命中結果依 ReviewItem identity 去重後選取該 ReviewItem
- **AND** MUST NOT 將同一 ReviewItem 的多個幾何命中視為選取歧義

#### Scenario: 沒有實際繪製的來源不能由圖面選取

- **WHEN** unresolved error／critical ReviewItem 的來源幾何沒有實際繪製於目前畫面
- **THEN** 該來源 MUST NOT 成為本次圖面點擊的命中目標
- **AND** 使用者仍 SHALL 能從既有構件清單或問題清單選取該 ReviewItem

#### Scenario: Focus source 在來源圖層隱藏時仍可命中

- **WHEN** 來源圖層目前隱藏
- **AND** unresolved error／critical ReviewItem 的來源幾何因目前 selection 的 `focus_handles` 而實際強制繪製於畫面
- **THEN** 該來源 SHALL 維持可命中
- **AND** 系統 MUST 使用與畫面實際繪製相同的幾何範圍判斷命中

#### Scenario: Viewport 改變後不得使用舊螢幕座標

- **WHEN** Preview 完成一次 render 後，使用者平移或縮放 viewport
- **AND** 使用者立即點擊移動後畫面中 unresolved error／critical source 的新位置
- **THEN** 命中結果 SHALL 對應目前 viewport 與目前畫面位置
- **AND** 該 source 在變更前的舊螢幕位置 MUST NOT 因 stale hit index 而命中

#### Scenario: 非錯誤來源不因本 capability 成為可點選目標

- **WHEN** 圖面來源只對應最高嚴重度為 `warning` 或 `info` 的 unresolved ReviewItem，或只屬於一般背景、已排除來源
- **THEN** 本 capability MUST NOT 將該來源加入錯誤來源圖面選取範圍
- **AND** 其既有顯示與清單操作 SHALL 維持不變

#### Scenario: Hover 提示可選取的錯誤來源

- **WHEN** 滑鼠移至唯一可選取的 unresolved error／critical ReviewItem 來源命中範圍
- **THEN** 預覽圖 SHALL 顯示可互動游標或等價提示
- **AND** hover 本身 MUST NOT 改變目前選取的 ReviewItem 或正式 member

#### Scenario: 圖面選取同步清單不得重複執行

- **WHEN** 一次圖面點擊唯一命中 unresolved error／critical ReviewItem
- **AND** 系統以程式方式同步構件清單的選取狀態
- **THEN** unresolved selection flow SHALL 只執行一次
- **AND** detail panel 與 render request SHALL 各更新一次
- **AND** 清單同步所產生的 selection event MUST NOT 再次執行相同 unresolved selection flow

### Requirement: 重疊歧義與既有操作優先序

若一次點擊命中兩個以上不同 unresolved error／critical ReviewItems，系統 MUST NOT 依來源繪製順序、source handle 字串、ReviewItem collection order、角色、嚴重度或任意最近值自動選擇其一。系統 SHALL 保留點擊前的 selection，並顯示可理解的歧義提示，引導使用者從既有清單選取。

現有候選點、待修改起終點與正式 member 的圖面點選 SHALL 保持目前優先序及結果；只有當這些既有目標都未處理該次點擊時，系統才 SHALL 嘗試 unresolved error／critical source selection。候選點或起終點修改模式中的非法空白點擊 SHALL 維持既有提示行為，不得落入錯誤來源選取。

#### Scenario: 多個不同錯誤項目重疊

- **WHEN** 一次左鍵點擊同時命中兩個以上不同 unresolved error／critical ReviewItems
- **THEN** 系統 MUST NOT 自動選取其中任何一個 ReviewItem
- **AND** SHALL 保留點擊前的 selection
- **AND** SHALL 顯示歧義提示，指引使用者從構件清單或問題清單明確選取
- **AND** 後續由程式化清單同步產生的 selection event MUST NOT 覆蓋該歧義提示

#### Scenario: 候選點命中優先於錯誤來源

- **WHEN** 同一次點擊同時命中既有候選點與 unresolved error／critical 來源
- **THEN** 系統 SHALL 執行既有候選點點選行為
- **AND** MUST NOT 因該次點擊改選 unresolved ReviewItem

#### Scenario: 待修改端點命中優先於錯誤來源

- **WHEN** 系統處於既有端點互動狀態，且同一次點擊由既有端點操作處理
- **THEN** 系統 SHALL 執行既有端點操作
- **AND** MUST NOT 因該次點擊改選 unresolved ReviewItem

#### Scenario: 正式構件命中優先於錯誤來源

- **WHEN** 同一次點擊同時命中既有正式 member 與 unresolved error／critical 來源
- **THEN** 系統 SHALL 執行既有正式 member 選取行為
- **AND** MUST NOT 因該次點擊改選 unresolved ReviewItem

#### Scenario: 端點修改模式的非法點擊不改選錯誤來源

- **WHEN** 系統處於選取新起點或新終點模式
- **AND** 使用者點擊未命中合法候選點的位置，即使該位置命中 unresolved error／critical 來源
- **THEN** 系統 SHALL 維持既有非法候選點提示與 pending edit state
- **AND** MUST NOT 選取 unresolved ReviewItem

### Requirement: 錯誤來源選取不得改變正式資料

從預覽圖選取或 hover unresolved error／critical 來源 MUST 只改變 Presentation 擁有的 selection、focus、cursor 與 render state。系統 MUST NOT 修改 DXF recognition result、validation messages、ReviewItems、formal members、source geometry、confirmation、source exclusion、manual repair、coordinate state、import mode、Project rows、Solver inputs、persisted review state 或 dirty state。

#### Scenario: 圖面選取只有 UI 副作用

- **WHEN** 使用者從預覽圖成功選取一個 unresolved error／critical ReviewItem
- **THEN** 選取前後的 DXF Review result、ReviewItems、工程 members、messages 與 source geometry SHALL 相同
- **AND** confirmation、exclusion、repair、Project、Solver、persistence 與 dirty state SHALL 維持不變

#### Scenario: 歧義點擊沒有資料副作用

- **WHEN** 使用者點擊兩個以上不同 unresolved error／critical ReviewItems 的重疊位置
- **THEN** 除顯示歧義提示外，selection 與所有正式資料 SHALL 維持點擊前狀態

#### Scenario: Hover 沒有資料副作用

- **WHEN** 使用者將滑鼠移入或移出 unresolved error／critical source 的命中範圍但未點擊
- **THEN** 系統 MAY 更新游標或暫時 hover 顯示
- **AND** MUST NOT 改變 ReviewItem selection、正式資料或 dirty state
