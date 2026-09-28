# Tasks

## 1. 現況與 Regression Fixtures

- [x] 1.1 在 `tests/test_dxf_bim_block_recognition.py` 加入／確認 Y05 S11 root `D19` characterization，固定 outer rails 約 `X=-5673.5/-5323.5`、正確中心約 `X=-5498.5`，並證明 topology adjacency 已形成四段無分支外框、但 raw exact-value 去重留下 5 個 point samples而產生目前傾斜軸與約 `408.34 mm` 錯誤寬度，再轉為目標 regression。
- [x] 1.2 在同一 focused test module 加入／確認 Y05 roots `B05`／`957` characterization：分別證明 whole-root candidates 約為 `X=±53469.5`、350 mm，local candidates 約為 `X=±53379.0`、204 mm，驗證兩者是鏡像且各候選皆來自自己的同一 root WCS source，並將 `957` 的舊 local expected value 轉為修正 regression。
- [x] 1.3 建立最小 synthetic fixtures，涵蓋無分支完整外框、outer rails 加 internal branch rails、外框接入 detail rail 的 branch／T-junction、可獨立抽出的完整 boundary，以及沒有 topology／whole-root envelope 而只能使用 local fallback；驗證 fixtures 不依 Y05 handle 或固定座標才能成立。
- [x] 1.4 建立 Tier 2 eligibility fixtures，涵蓋外側短 detail／connection line、raw global transverse min/max 會形成錯誤 envelope、以及兩個中心不等價但各自完整的 outer-envelope interpretations；驗證 fixtures 能分別觀察 detail rejection 與 blocking ambiguity。
- [x] 1.5 建立 axis-equivalent／different-width fixtures，涵蓋可由 containment 唯一決定實體外包絡的 nested envelopes，以及 center 唯一但 envelope 無法唯一的案例；驗證預期分別為 unique width 與 recognized axis plus unknown width。

## 2. Topology Envelope Qualification

- [x] 2.1 在 `dxf_import/block_member_recognition.py` 將 Strut topology candidate 的 connected-component 判定與 valid boundary qualification 分離，並以 unit tests 驗證含 branch 的整體 graph 不再直接進入 consolidated center／width 計算。
- [x] 2.2 讓 endpoint clustering 回傳／使用 deterministic canonical topology nodes，並讓 `_topology_member_from_contour()` 或等價 axis／width 計算不再對 raw floating-point endpoints 做 exact-value 去重；以 epsilon-offset corner、entity permutation、line reverse 與 Y05 S11 tests 驗證中心約 `X=-5498.5`、寬度約 350 mm。
- [x] 2.3 實作無分支完整 boundary 的資格判定，允許 branched source 中可獨立且唯一驗證、不使用 branch edges 的完整 boundary 保留；以 synthetic tests 驗證 valid outline 仍是第一順位，無法唯一抽出時不猜測。
- [x] 2.4 將 branch/detail edges 排除於 topology envelope `representative_width` 來源，並以 350、400、500 mm、nested same-axis／different-width 與 axis-known-width-unknown tests 驗證寬度來自唯一有效實體外包絡，而不是固定值、first occurrence 或局部 rail separation。
- [x] 2.5 將新 topology qualification 明確限制在 Strut center authority route，或以等價的 role-aware boundary 保護現有共用 helper；執行既有 Brace focused tests 驗證 Brace recognition winner 未改變。

## 3. Whole-Source Candidate Reconciliation

- [x] 3.1 為既有 topology、whole-root outer-envelope、local fragmented rail-pair candidates 保留可判定的內部 provenance／tier，且不改公開 input/output schema；以 unit tests 驗證三類候選可依來源分組。
- [x] 3.2 收緊 `_whole_root_envelope_candidates()` 或等價 Tier 2 boundary qualification：每個 outer face 先通過既有 direction、coverage、length、slenderness、same-root 與 whole-corridor completeness，成對 faces 再通過 width compatibility；以 tests 驗證不得直接使用所有 parallel rails 的 raw transverse min/max。
- [x] 3.3 將短 detail、branch rail、connection detail 與局部 rail 限制為 completeness／conflict diagnostics evidence，不得成為 Tier 2 outer face；以 outer-detail fixtures 驗證它們不偏移 center 或擴大 `source_width`。
- [x] 3.4 調整 `_recognize_contextual_strut()`，使所有候選先通過既有 Waler span 與 whole-root completeness eligibility，再依 topology → whole-root envelope → local fallback 選擇第一個合格 center tier；以 S20 regression 驗證 Tier 2 成功後 local source-only／Tier 3 不再具有 authority。
- [x] 3.5 在每個 authority tier 先依 axis equivalence 合併 center evidence groups，再套用既有 center ambiguity semantics；以 tests 驗證同層兩個不等價完整 Tier 2 interpretations 回傳 blocking ambiguity，且不依 score、距離、handle、entity order 或 candidate order 任選或降級。
- [x] 3.6 對 winner center group 獨立 reconcile 有效 envelopes：以 topology、whole extent、containment 與 component-envelope credibility 尋找唯一物理外包絡；以 tests 驗證 nested unique outer envelope 得到正確 width，而 center 唯一但 envelope 不唯一時保留 axis、使用既有 unknown-width 表示且不回報 center ambiguity。
- [x] 3.7 保留 local rail-pair 作為前兩層均無 winner 時的 compatibility fallback，並驗證無 Waler context 的 public compatibility entry、non-component `not_applicable`、`failed` 與既有 terminal diagnostic contracts 不回歸。
- [x] 3.8 驗證 Waler context 只改變 longitudinal terminal span：建立相同 source geometry 配不同有效 Waler span 的測試，確認 transverse center／source width 不被 Waler 中點、接觸面或最近距離改寫。

## 4. Y05 與相容性整合驗證

- [x] 4.1 執行 Y05 S11 importer-level regression，驗證 tolerance-normalized valid Tier 1 outline 產生約 `X=-5498.5`／350 mm，且不再因重複 raw corner sample 輸出傾斜軸、約 408.34 mm 寬度或非預期 ambiguity。
- [x] 4.2 執行 Y05 S20 importer-level regression，驗證 Tier 2 產生約 `X=53469.5`／350 mm 後 Tier 3 不再具有 authority，且不再採用約 `X=53379.0`／204 mm 的 local outcome。
- [x] 4.3 執行並補強 Y05 S2 root `957`、S10、S19 regression：確認 `957` 與 `B05` 對稱採用約 `X=±53469.5`／350 mm 的 whole-root outer-envelope 並維持完整 span；S10 clean connected outline 與 S19 既有 whole-root correction 維持已規範結果；同時確認其餘 Y05 Strut 數量、root provenance 與 terminal Waler associations 無非預期變化。
- [x] 4.4 對 synthetic candidates 執行 entity permutation、segment reverse、block rotation／translation tests，驗證 center grouping、獨立 width reconciliation、unknown-width outcome、status 與 diagnostic deterministic，且不受 first occurrence 或 recognition method 影響。
- [x] 4.5 執行 DXF import／Review focused lifecycle tests，確認 source exclusion／restore、fingerprint replay、pause／resume 與 persisted review contracts 未因內部 candidate tier 改變而回歸。

## 5. 文件與最終驗證

- [x] 5.1 實作驗證完成後，僅在本 change 確實形成新的 long-term recognition truth 時更新 `docs/DOMAIN.md` 或 `docs/ARCHITECTURE.md` 的直接相關段落；以文件 review 確認未寫入 Solver、Waler contact-face 或其他 member 規則。
- [x] 5.2 執行最接近修改的 BIM block／DXF import test modules，再執行完整 test suite；確認不得以 skip、刪除測試或降低 assertion 排除失敗。
- [x] 5.3 執行 `openspec validate repair-bim-strut-center-selection --strict` 與 OpenSpec implementation verification，確認 production behavior、delta spec、design 與 tasks 一致，且 `unify-waler-contact-face-recognition` 仍為獨立 scope。
