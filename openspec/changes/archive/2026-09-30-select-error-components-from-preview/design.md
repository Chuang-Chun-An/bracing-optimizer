# Design

## 閱讀導航

- **P0｜現在必讀**：Decision 1「從已繪製來源建立 ReviewItem hit index」、Decision 2「重用 unresolved selection path」、Decision 3「維持既有點擊優先序」。這三項共同決定功能正確性與回歸邊界。
- **P1｜實作前閱讀**：Selection flow、State and contract truth、Testing strategy；修改 `dxf_import/dialog.py` 與互動測試時必讀。
- **P1｜遇到 Preview index 或效能問題時閱讀**：Decision 4「純 pixel hit-test 與 ReviewItem 去重」、Risks / Trade-offs。
- **P2｜需要時再讀**：Backward compatibility、Migration Plan；本 change 沒有 persistence migration，也不修改 recognition 或 Solver。
- **可先跳過**：CornerBrace repair、Waler contact adjustment、Project apply、Solver 與其他 recognition design；它們不是本功能的資料來源或提交目標。

## 方案摘要

目前 Preview 已從 `SourceGeometry` 畫出 error／critical unresolved source，但點擊只檢查候選點、pending endpoints 與正式 members。實作時在同一次 source geometry projection 中建立一份 UI-only hit index，索引值指向目前 `ReviewItem.key`；點擊既有目標皆未處理時，再用 pixel tolerance 找出命中的 ReviewItem keys。唯一 key 重用現有 unresolved selection path，多個 keys 則只顯示提示。

```text
visible source geometry
        ↓ project once
draw source line ──＋── build UI-only hit segments keyed by ReviewItem.key
                         ↓
left click: endpoint → candidate/edit guard → formal member → unresolved error
                                                        ↓
                                            1 key: select existing ReviewItem
                                           >1 keys: preserve + ambiguity hint
```

## 決策對照

| Decision | 選擇原因 | 影響的 spec Requirement | 對應 task |
| --- | --- | --- | --- |
| D1：從同一批已投影且實際繪製的來源建立 UI-only error hit index，並記錄 viewport transform／render generation | 避免繪圖與命中範圍使用兩套座標轉換或 stale screen coordinates 而 drift | 圖面可選取未解析錯誤來源 | 1.1、1.2、1.3 |
| D2：命中 identity 使用目前 `ReviewItem.key`，選取重用既有 unresolved path 並抑制 tree event 重入 | 保留 ReviewItem 為唯一正式對應，不製造 member，也不重複更新 detail／render | 圖面可選取未解析錯誤來源；錯誤來源選取不得改變正式資料 | 1.3、2.1 |
| D3：錯誤來源放在既有 endpoint／candidate／edit guard／formal member 之後 | 維持既有操作契約，避免圖面修正工具被紅線攔截 | 重疊歧義與既有操作優先序 | 2.2、3.2 |
| D4：收集容差內全部 keys、依 key 去重；多 key 不選取 | 同一 ReviewItem 多段線不誤判，真正歧義也不依順序猜測 | 圖面可選取未解析錯誤來源；重疊歧義與既有操作優先序 | 1.3、3.1 |
| D5：hover 只提供可互動游標，不新增正式 hover truth | 滿足 discoverability，同時避免新增第二套選取狀態 | 圖面可選取未解析錯誤來源；錯誤來源選取不得改變正式資料 | 2.3、3.3 |

## 專有名詞

- **unresolved ReviewItem**：目前 Review projection 中具有 source handles、但沒有正式 `member_id` 的項目；對應 proposal 的「未解析錯誤來源」。
- **error hit index**：只存在於 Preview Presentation 的 screen-space 線段集合，每段保存 `ReviewItem.key`、source handle 與投影後端點，整體另保存建立時的 viewport transform、render generation 及輸入 signatures；不是 DXF model 或 persisted state。
- **唯一命中**：一次點擊容差內的所有線段在依 `ReviewItem.key` 去重後只剩一個 key；同一項目的多段幾何不是歧義。
- **既有 unresolved selection path**：目前由構件清單選取 unresolved item 時使用的 UI 流程，負責設定 `selected_review_item_key`、`focus_handles`、清除 formal member selection、更新明細與重畫 Preview。

## Context

需求動機見 [proposal.md](./proposal.md)「Why」。目前程式具有以下可重用契約：

- `build_review_items()` 已將沒有正式 member、但具有來源 handles 的 error／critical 訊息投影成 unresolved `ReviewItem`；這是 source identity 與問題內容的既有 truth。
- source geometry renderer 已依 unresolved issue severity 將來源畫成紅色／黃色，並以 `focus_handles` 套用藍色聚焦。
- `_select_unresolved_review_item()` 已能從清單完成正確的 UI selection，但它目前假設觸發來源是 component tree。
- canvas click 目前依序處理 pending endpoint、candidate point、edit-mode guard 與正式 member；source geometry 尚無 hit-test collection。
- `DXFImportDialog` 擁有 viewport、selection、hover 與 temporary UI draft；`DXFReviewWorkflow` 擁有 Review result 與 ReviewItems。這個 ownership 已由 `docs/ARCHITECTURE.md` 定義。

## Goals / Non-Goals

**Goals:**

- 使用畫面上實際可見的 error／critical unresolved source 建立準確、可測試的 pixel hit target。
- 圖面與清單選取共用同一 ReviewItem identity 與 UI adoption path。
- 對重疊歧義採保守且 deterministic 的結果。
- 保持現有互動優先序、render scheduler 與 state ownership。

**Non-Goals:**

- 不新增 recognition、repair 或 guided recognition use case。
- 不把 source handle 轉換成 member identity，也不讓 unresolved item 進入 candidate editing。
- 不建立通用 selection framework 或重構完整 Preview scene graph。
- 不新增重疊候選 popup、click cycling 或持久化 UI selection。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 Architecture 本身**。

| Layer | 責任 | 本 change |
| --- | --- | --- |
| DXF Presentation | Preview projection、screen-space hit-test、cursor、selection synchronization | 唯一受影響 layer |
| DXF Review Workflow | `ReviewItem` 與 active result 的 authoritative owner | 只提供唯讀 snapshot；不新增 command 或 mutation |
| Recognition / Models | 來源幾何、驗證訊息與 member facts | 不變 |
| Project / Solver / Infrastructure | 套用、求解、持久化與外部 I/O | 不變 |

Dependency direction 維持 `DXF Presentation → DXFReviewWorkflow → pure review/recognition → models`。Presentation 只消費 Workflow 已建立的 ReviewItems，不在 UI 重新推導 error ownership 或 recognition 結果。

## Decisions

### Decision 1：由目前 render 的 source projection 建立有 generation stamp 的 UI-only hit index

每次 full scene rebuild 時，先遞增 monotonic `render_generation`，並由目前 unresolved error／critical ReviewItems 建立 normalized source-handle → ReviewItem keys 的唯讀 lookup。source geometry 使用現有 coordinate transform 投影成 screen points時，同步為相鄰點及 closed geometry 的 closing segment 建立 hit records。

hit record 保存足以判定的 `review_key`、`source_handle` 與 screen-space start/end，不保存或複製 `ReviewItem` 內容。整份 index 必須保存建立時的 viewport transform 與 `render_generation`，並保存 source visibility signature、ReviewItems signature 與 active result identity／revision。signature 只用於 freshness 判定，不成為新的 Review truth。

以下任一事件發生時，index 立即 invalid：

- viewport pan、zoom、fit 或其他 transform 變更；
- source visibility 或 `focus_handles` 改變；
- ReviewItems projection 改變；
- active result 被替換或 revision 改變；
- full scene render 尚未完成或開始下一個 generation。

click／hover 在使用 index 前必須比較目前 viewport transform、render generation 與上述 signatures。click 遇到 stale index 時，應以目前 viewport 與目前實際繪製輸入同步重建必要的 hit records後再判斷，使平移或縮放後立即點擊能命中新位置；若當下無法可靠重建則 no-op。hover 可採同一重建路徑或 no-op。兩者都不得讀取 stale screen coordinates。

「可見」只有一個定義：來源是否在目前畫面上實際繪製。一般 source layer 隱藏後不建立可命中的 records；但因目前 selection 的 `focus_handles` 而被強制繪製的 geometry，即使 source layer 隱藏，仍必須納入 index。viewport 外、被 visibility rule 隱藏或沒有 renderer item 的 geometry 不進入當次 index。index 建立與來源顯示必須共用同一份 visible geometry／render decision，不能各自推導。

**Rejected alternatives:**

- 直接掃描所有 world geometry 並在 click 時重做 transform：會與 renderer visibility／closed-segment 行為形成第二套 projection 邏輯。
- 只使用 Canvas `find_closest`：容易受 layer raise order、粗線寬度與透明 overlay 影響，且無法可靠區分同一 ReviewItem 的多段命中與多 ReviewItem 歧義。
- 將 hit index 寫入 `DXFImportResult` 或 `ReviewItem`：screen-space state 屬於 Presentation，寫回會破壞 state ownership。

### Decision 2：以 ReviewItem identity 選取，不以 source handle 假造構件

source handle 只用於從已繪製來源連回目前 unresolved ReviewItem；實際 hit 結果一律轉成 `ReviewItem.key`。同一 key 的多個 handles／segments 先去重，再決定唯一或歧義結果。

唯一命中後擴充既有 unresolved selection helper，使其可接收 `source="canvas"`，並沿用同一組 UI effects：

- 設定 `selected_review_item_key`；
- `focus_handles` 採該 ReviewItem 的完整 source handle set；
- 清除 formal component／candidate selection；
- 更新 unresolved detail panel；
- 以既有 tree synchronizer 將構件清單捲動並選到該 ReviewItem；
- request 足夠的 render dirty regions，確保 tree 與 Preview 同步。

canvas path 必須透過既有 `TreeSelectionSynchronizer` 執行 tree selection，並讓 `<<TreeviewSelect>>` handler 在 synchronizer 的 programmatic-selection guard 有效時立即返回。不得直接繞過 synchronizer 呼叫 `selection_set()`。一次 canvas selection 只能進入 unresolved selection helper 一次、更新 detail 一次並提出一次 render request；tree virtual event 只負責被抑制，不得再進入相同 path。

歧義點擊不執行 tree synchronization，因此不應產生延後的 tree event。若先前仍有 programmatic tree event 排隊，guard 必須避免它重新執行 selection path或覆蓋本次歧義提示。

不新增另一個「selected source handle」truth。`selected_review_item_key` 仍是 review selection identity，`focus_handles` 仍只是 Presentation projection。

**Rejected alternatives:**

- 把 unresolved source 包成 temporary member：會誤開候選點／工程資料工具，並模糊正式 member 邊界。
- canvas click 直接呼叫 problem-list focus：一個 ReviewItem 可包含多個 problems，會把 selection truth 降成單一 problem，且與構件清單不同步。
- 新增 Workflow command 記錄 selection：selection 無需持久化或 transaction，不應擴大 Application responsibility。
- 在 event handler 內用 ReviewItem equality 猜測是否重入：event 排程可能晚於狀態更新，應沿用 synchronizer 明確標示 programmatic selection 的 guard。

### Decision 3：維持現有 selection priority

canvas click 的既有控制流不重排；error source detection 只新增在正式 member detection 之後：

```text
pending endpoint hit
  → candidate point hit
  → active pick-mode invalid-click guard
  → formal member hit
  → unresolved error source hit
  → no-op
```

這確保錯誤來源紅色 overlay 不會攔截 candidate editing 或正式構件選取。正式 member 即使本身帶有 error，仍走既有 member selection，不會被當成 unresolved item。

hover 採同一優先概念：candidate／endpoint／formal member 能提供 hover 時維持既有結果；只在它們都未命中且 unresolved error hit 唯一時顯示 hand cursor。歧義 hit 不顯示成可直接選取，避免游標暗示錯誤承諾。

**Rejected alternatives:**

- error source 優先於正式 member：同一來源常與 formal engineering line 重疊，會破壞現有構件 selection。
- 在 pick mode 中仍允許選 error source：會使一次非法 endpoint click 同時切換 subject，造成 pending edit 語意不明。

### Decision 4：收集全部容差命中後依 ReviewItem key 去重

新增純 screen-space segment hit helper，使用與正式 member selection 一致的固定 pixel tolerance。helper 回傳容差內所有 hit identities，並以 `(distance, identity)` 排序，確保輸入線段順序不影響結果。Dialog 再依 `ReviewItem.key` 去重：

- `0` keys：no-op；
- `1` key：選取；
- `>1` keys：保留 selection 並寫入既有狀態訊息區，提示使用清單。

歧義判定不使用 severity ranking；error 與 critical 重疊仍是兩個不同項目，因為 severity 不足以證明使用者意圖。

**Rejected alternatives:**

- 取最近 source：兩條重疊或近乎重疊的線會受數值誤差影響，且不符合「不猜測」。
- 依 critical 優先：嚴重度是檢核優先度，不是 spatial selection intent。
- click cycling：需要額外 cycle anchor、timeout 與 viewport invalidation state，超出本 change。

### Decision 5：不新增 persistent hover selection

hover 只計算目前游標位置是否有唯一可選的 unresolved error hit，並更新 cursor；離開後恢復既有 cursor 邏輯。不把 unresolved hover key 寫入 `SelectionState`，也不增加 persisted field。

若後續產品需求要求 tooltip 或暫時著色，可另行增加 Presentation-only hover identity；本 change 不預先建立未使用 abstraction。

## State and Contract Truth

| 資料／狀態 | Single source of truth | 本 change 的使用方式 |
| --- | --- | --- |
| Validation messages、ReviewItems | `DXFReviewWorkflow` snapshot | 唯讀取得 unresolved error identity 與 handles |
| Source geometry | active `DXFImportResult` | 唯讀投影與建立 screen-space hit records |
| Selected review item | Dialog 的 `selected_review_item_key` | 唯一 UI review selection identity |
| Focused source display | Dialog 的 `focus_handles` | 由 selected ReviewItem 衍生，可隨 selection 重建 |
| Canvas hit segments 與 freshness stamp | Dialog／Preview scene lifecycle | 每次 full rebuild 重建，記錄 viewport transform／render generation／輸入 signatures，不持久化 |
| Formal member selection | 既有 `SelectionState` | unresolved selection 時沿既有流程清空，不建立 member |

避免 drift 的關鍵是 hit index 不保存 problem severity 或 ReviewItem 複本；每次 result／viewport／visibility rebuild 都從目前 ReviewItems 與同次實際繪製決策重建，並以 freshness stamp 阻止 stale coordinates 被使用。選取時再以 key 從目前 lookup 取得 ReviewItem，若 key 已不存在則 index 失效並 no-op 或重建，不得沿用舊 object reference。

## Testing Strategy

- 純 hit-test 測試：pixel tolerance、排序不受輸入順序影響、同 key 多段去重前資料完整。
- Dialog selection 測試：唯一 unresolved error hit 會重用 selection path、同步 tree／detail／focus，且 formal member selection 被清空。
- viewport freshness 測試：pan／zoom 後立即點擊只命中目前畫面新位置，舊 screen position 不命中；stale generation 不得參與 click 或 hover。
- 歧義測試：兩個不同 keys 同時命中時 selection、focus 與 formal state 完全保留，只更新提示。
- priority regression：endpoint、candidate、pick-mode guard、formal member 仍先於 unresolved error。
- visibility／severity 測試：未實際繪製的 source、warning、info、excluded source 不成為 error hit target；`focus_handles` 因 selection 在 source layer hidden 時仍被強制繪製並可命中。
- tree re-entrancy 測試：一次 canvas selection 只執行一次 unresolved selection path，detail 與 render 各更新一次；programmatic tree event 被 guard 忽略，且歧義提示不被延後事件覆蓋。
- state-safety 測試：click／hover 前後 Workflow result、ReviewItems 與 dirty／persistence state 不變。
- 既有 focused tests：`tests/test_dxf_review_items.py`、相關 Preview controller／renderer tests；若修改共用 CAD hit helper，另執行 `tests/test_cad_view_interaction.py`。

## Risks / Trade-offs

- **[Risk] 大型 DXF 產生大量 hit segments，mouse motion 掃描成本增加** → 只索引 error／critical unresolved sources，使用 full-scene rebuild 時預先投影；若量測證明線性掃描不足，再另案引入 spatial index，不預先複雜化。
- **[Risk] viewport 或 source layer 已改變但 hit index 尚存在** → 每份 index 保存 transform／generation／輸入 signatures；pan、zoom、visibility、ReviewItems、active result 變更立即 invalid，click／hover 只使用 freshness check 通過的 index。
- **[Risk] Review refresh 後舊 key 指向不存在項目** → selection 前以目前 `review_item_by_key` resolve；不存在即 no-op，不保留 ReviewItem object reference。
- **[Trade-off] 重疊不同 ReviewItems 無法從圖面直接選其中之一** → 以既有清單作安全 fallback；這是刻意避免任意 selection，必要時再評估候選 popup。
- **[Trade-off] warning／excluded source 仍只能依既有方式選取** → 保持本 change 聚焦「錯誤元件」且避免一般背景變成密集 hit targets。

## Backward Compatibility and Persistence Impact

- 沒有公開 API、DXF model、Project schema、review-state schema 或 serialization 變更。
- 舊專案與 paused review 不需 migration；載入後由目前 ReviewItems 即時建立 hit index。
- 未使用圖面 error selection 的操作路徑完全維持既有行為。
- rollback 只需移除 Presentation hit index 與 click／hover branch，不涉及資料回復。

## Migration Plan

1. 先加入純 hit-test 與 source-handle／ReviewItem lookup 測試。
2. 加入 UI-only index 並串接 unresolved selection helper。
3. 加入 click priority、ambiguity、visibility 與 side-effect regression tests。
4. 手動以含 recognized member error、unresolved source error 及重疊來源的 DXF 驗證游標、tree、detail 與 focus 行為。

此 change 無資料 migration、feature flag 或 staged rollout requirement。
