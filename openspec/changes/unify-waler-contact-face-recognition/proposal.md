# Proposal

## Why

目前 Waler 接觸面以已辨識 Strut／Brace 原始端點到候選邊界的距離選擇；但 BIM Strut 的端點可能已先投影到暫定 Waler 中心線，使兩側距離相同，最後被浮點微差或來源線順序決定。Y05 的 W7 因而選到非支撐側最外實體表面的內部線，並讓鄰近 W12 產生不必要的連接歧義；同一工程語意也會因一般 CAD 或 BIM 的來源畫法不同而得到不同結果。

## What Changes

- 建立一套不依賴 CAD／BIM 畫法的 Waler 接觸面辨識能力：各構件先完成自己的來源辨識，再於 downstream relationship／canonical finalization 判定 Waler 的支撐側與正式接觸面。
- Waler 來源辨識先建立可證明的單一 component scope，再於該 scope 內保留 provisional reference axis、完整構件 envelope 與最外實體表面；不得跨不同 Waler components 取全局 transverse extremes。不在 Waler recognition 階段讀取 Strut／Brace，也不提前選擇接觸面。
- 先以 Waler provisional reference geometry 建立 member endpoint 與 Waler 的來源關係，再由 member 軸線朝構件本體的方向判定支撐側；不得再以已投影端點到兩側邊界的最近距離、全域端點中心或來源順序決定內外側。
- 對有可靠完整 envelope 的 Waler，正式接觸面使用支撐側的最外實體表面；內部平行線、H 型鋼細部線或局部輪廓不得取代該表面。
- 接觸側證據不足、相互衝突或無法得到唯一 deterministic 結果時，產生既有 DXF Review 可處理的 blocking problem，不任意猜測或依 Project／entity order fallback。
- 保持既有 `Waler → Strut → Brace → CornerBrace → Column → Joist` 單向 stage ordering。接觸面 finalization 只能消費已完成的 immutable recognition facts，不得反向改變任何構件的 recognition winner、來源支持軸線、寬度、role 或 provenance。
- 將最終接觸面一致套用至 Waler formal geometry、Strut／Brace endpoint connection、CandidatePoint／association 與 diagnostics；保留既有 Review mutation、confirmation invalidation、Source Exclusion／Restore、Pause／Resume 與 DXF → Project lifecycle。

### In Scope

- 一般 CAD、BIM Block Strut／Brace 與 HATCH RC Waler 共用的 Waler 支撐側／接觸面語意。
- 具有多條平行來源線之 Waler 的單一 component qualification、完整 envelope 與最外實體表面判定；包含防止相接、同方向或同 group 的不同 Walers 被合成假 envelope。
- Waler 與已辨識 Strut／Brace 的 endpoint topology、方向證據與 deterministic ambiguity handling。
- Y05 W7／W12 與既有 Y1A 一般 CAD 的 regression coverage。
- DXF Review 中與接觸面改變直接相關的 validation、problem 與 downstream rebuild。

### Out of Scope

- 改變 Waler、Strut、Brace 各自的 component recognition winner 或來源工程軸。
- 重新設計 BIM Block recognition、Brace extension、HATCH RC classification 或 material recognition。
- 新增 cyclic recognition、iterative recognition feedback 或通用 dependency framework。
- Guided Recognition、人工輔助線、DXF UI 大改、Project schema、Solver、Waler material／section engineering rules。
- 自動合併或刪除 W7／W12 等不同 Waler source identity。

## Capabilities

### New Capabilities

- `dxf-waler-contact-face-recognition`: 定義不同 DXF 來源畫法共用的 Waler 支撐側、最外實體接觸面、下游連接 finalization 與歧義處理行為。

### Modified Capabilities

無。既有 BIM Block、Brace connection 與 HATCH RC Waler capability 保留各自的來源辨識契約，並在辨識完成後使用本次新增的共用接觸面能力。

## Impact

- 預計影響 `dxf_import` 的 Waler candidate geometry、recognition orchestration、contact adjustment／connection finalization、validation／Review problem rebuild 與相關測試。
- 不改變公開 Project row contract、persistence schema、Solver input、第三方 dependency 或 original DXF immutable contract。
- Architecture dependency direction不變；本 change 將既有 Architecture 中「來源辨識」與「post-recognition relationship／canonical finalization」的責任界線落實得更明確。
- Domain 與 Solver truth 預期不變；完成並驗證後，預期更新 `docs/WORKFLOW.md` 的 DXF recognition／finalization 現況說明。若實作未改變既有 Architecture truth，則不修改 `docs/ARCHITECTURE.md`。
