# Proposal

## 閱讀導航

- **P0 現在必讀**：本文件的「快速摘要」、「現況與目標」與「主要流程」，先確認本 change 處理的是 DXF Review 診斷與呈現，不是自動修正重疊圍令。
- **P0 現在必讀**：[dxf-waler-overlap-diagnostics](specs/dxf-waler-overlap-diagnostics/spec.md) 的「重大共線重疊必須產生來源診斷」與「競爭關係必須升級為 blocking error」Requirements；先確認有限 provisional axis 分母與 direct identity provenance。
- **P0 現在必讀**：`tests/test_dxf_waler_contact_face_recognition.py` 的 Y29 W17／W20 regression 與一般 CAD contact-face baseline；實作前以它們鎖定現有行為。
- **P1 實作前閱讀**：`dxf_import/waler_contact_face.py`、`dxf_import/recognition.py` 的 `_resolve_waler_contact_geometry()`，以及 Preview／Review projection；確認純幾何、staged Review 與 Presentation 的責任邊界。
- **P2 需要時再讀**：[dxf-review-engineering-data-presentation](../../specs/dxf-review-engineering-data-presentation/spec.md) 的唯讀投影與不建立第二份關聯資料 Requirements；修改 Review 細節面板時才需要。
- **可先跳過**：Solver、Project schema、材料規則與 CornerBrace repair specs；它們不在本 change scope。

## 快速摘要

- Y29 的 W17（source handle `69C`）與 W20（`721`）高度重疊，現行 contact-face 流程已保守地保留 terminal-to-Waler ambiguity 與 `WALER_CONTACT_FACE_UNRESOLVED`。
- 問題在於這個重疊沒有獨立、可定位的 Waler 診斷；Preview 又把 provisional `closed_outline_axis` 畫得像正式工程線，容易被誤解為辨識成功。
- 本 change 會對不同 Waler source identities 的重大共線重疊建立 Review warning：分子是兩支 source-supported provisional axes 的正有限投影重疊長度，分母是兩支 provisional axis 有限長度的較小值，比例 `>= 50%` 才成立。
- 只有同一 terminal 或同一 contact-face finalization 的 direct provenance 明確列出 overlap pair 的兩個完整 Waler source identities 時才另建 blocking error；附近另有 generic unresolved outcome 不足以升級。
- Preview／Review 會明確區分正式接觸面與未完成的 provisional axis；若使用者依外部工程判斷變更 active sources，既有流程會重新辨識，不推薦應排除哪一支。
- 不自動合併、刪除、改名或挑選任一重疊 Waler；不改 Solver、Project schema 或既有幾何歧義的保守語意。

## 現況與目標

**Waler overlap** 指不同 source identities 各自具有可靠、非零長度的 source-supported provisional axis，兩條有限軸共線且其有限區段互相覆蓋。本 change 的 overlap ratio 固定為「正有限投影重疊長度 ÷ 兩支 provisional axis 有限長度的較小值」；比例 `>= 50%` 才是重大重疊。Finalized contact face、envelope 周長、外框單邊、bounding box、Project row engineering line 與無限 supporting line 都不是長度來源。

| 面向 | Before | After |
| --- | --- | --- |
| W17／W20 重疊 | 只在後續 terminal/contact-face 語境間接形成 ambiguity | Review 先列出可定位的 overlap warning；只有 direct identity provenance 證明同一 terminal／finalization 的實際競爭時才另列 blocking problem |
| 接觸面 | `WALER_CONTACT_FACE_UNRESOLVED` 正確阻擋，但 provisional axis 在 Preview 看似正式工程線 | unresolved Waler 的 provisional axis 明確標記為未完成，不能偽裝成正式接觸面 |
| Review 行動 | 使用者須從下游構件錯誤反推來源 | 使用者可定位雙方來源與受影響 terminal；Review 只說明 active sources 變更後會 rebuild，不推薦刪除或排除哪一支 |
| 資料安全 | 可能誤以為 Preview 線可提交 | 未完成正式接觸面的 Waler 仍阻擋 Review，不會投影為 Project／Solver 的正式工程線 |

## 主要流程

```text
Waler source recognition
  -> 可靠且非零長度的 source-supported provisional axes
  -> 正有限投影 overlap / min(axis length A, axis length B) >= 50%
  -> overlap warning
  -> direct terminal/finalization identity join
       -> pair 同時為實際競爭 identities：blocking competition error
       -> 沒有 direct provenance：維持 warning-only
  -> terminal-to-Waler / contact-face finalization
       -> 唯一：正式接觸面
       -> ambiguous：維持 provisional axis + blocking state
  -> Preview 僅以不同樣式呈現 provisional 與正式線
  -> exclusion / restore / resume / rebuild 後重新計算
```

## 不變事項

- Waler source identities 維持獨立；不得因幾何重疊而自動合併、刪除、改名或挑選 winner。
- 不得用 Waler ID、handle、DXF entity order、距離微差、first match 或 Preview 狀態解除歧義。
- `WALER_CONTACT_FACE_UNRESOLVED` 的 blocking 語意、既有 manual override replay、source exclusion／restore、Pause／Resume 與 rebuild lifecycle 必須保持。
- 不改 Project schema、Project row、Solver input、Solver scoring 或任何 Solver 規則。

## Why

高度重疊的 Waler 可能讓 member terminal 無法唯一連到來源 identity，現有流程雖然安全地拒絕選擇接觸面，卻沒有將根因直接呈現，並讓 provisional axis 在 Preview 中看似正式成果。Review 需要呈現可核對的來源與受影響 terminal，但不能替使用者決定刪除、排除或保留哪一支。

## What Changes

- 新增跨不同 Waler source identities 的重大共線有限重疊診斷；只使用兩支可靠 source-supported provisional axes 的有限長度，並以「正有限投影重疊長度 ÷ 較短 provisional axis 長度」計算，`>= 50%` 才成立。
- 對每組符合條件的 Waler 建立可定位 warning；只有既有 terminal topology 或 contact-resolution outcome 直接證明該 pair 的完整 identities 同時競爭同一 terminal／finalization，才建立 blocking Review problem。Generic unresolved 或其他 pair 的競爭不得誤升級。
- 延伸 Waler contact-face contract：重疊造成 terminal identity 或接觸面不唯一時，provisional axis 只能作為診斷事實，不得成為正式 Waler engineering line、Project 或 Solver truth。
- 延伸 DXF Review Preview：以明確且不同於正式接觸面的視覺語意顯示 unresolved／ambiguous Waler provisional axis，並讓重疊來源與原因可被檢視。
- 新增有限長度與 unreliable-axis boundary tests、A／B／C identity provenance tests，以及 Y29 W17／W20 regression；涵蓋同時存在、active source 變更、輸入順序不變性與一般非重疊 Waler regression。

## In Scope

- DXF Import Waler overlap qualification、direct-provenance competition join、diagnostics、Review problem projection 與 Preview distinction。
- W17／W20 的 source-specific regression、source exclusion／restore、Pause／Resume、rebuild 與 manual override replay 相容性驗證。
- `dxf_import/waler_contact_face.py`、recognition/import orchestration 與 Review/Preview 的最小必要調整。

## Out of Scope

- 自動移除、合併、重命名或自動選擇重疊 Waler。
- 放寬 terminal-to-Waler 或 contact-face ambiguity 規則。
- Solver、Project schema、Project conversion、持久化格式、材料規則與 CornerBrace recognition 改動。
- 將所有平行或近距 Waler 一概判為錯誤；必須符合本 change 的有限共線與 50% 覆蓋資格。

## Capabilities

### New Capabilities

- `dxf-waler-overlap-diagnostics`: 定義不同 Waler source identities 的 provisional-axis 有限重疊資格、direct-provenance blocking diagnostics、定位資訊與重建一致性。

### Modified Capabilities

- `dxf-waler-contact-face-recognition`: 擴充重疊 Waler 導致 identity／接觸面歧義時的正式工程線與 provisional truth 邊界。
- `dxf-review-engineering-data-presentation`: 擴充 DXF Review 對正式 Waler engineering line、unresolved provisional axis 與重疊原因的唯讀呈現規則。

## Impact

- **Infrastructure／DXF recognition**：`dxf_import/waler_contact_face.py`、`dxf_import/recognition.py` 與 `dxf_import/importer.py` 的 staged geometry／diagnostic flow。
- **Review／Presentation**：Problem records、Review items、Preview rendering 與 Waler detail projection；Presentation 僅消費 staged truth，不自行判斷重疊。
- **Tests**：擴充 `tests/test_dxf_waler_contact_face_recognition.py` 的 exact-50%、低於門檻、endpoint-only、零長度、unreliable-axis、A／B／C provenance 與順序不變性 cases，並補 Review/Preview focused tests；保留現有一般 CAD、Y05 與非重疊 regression。
- **Architecture／Domain／Solver／Workflow truth**：不改 Architecture dependency direction、Domain 或 Solver；Workflow 只沿用既有 staged Review、exclusion、rebuild、Pause／Resume 與 confirmation invalidation contract。

## 已確認的診斷層級

- 任何以可靠、非零長度 source-supported provisional axes 計算且符合 `>= 50%` 門檻的重大共線重疊都產生可定位 warning；只有 direct provenance 明確列出 overlap pair 的兩個完整 source identities 同時競爭同一 terminal 或同一 contact-face finalization 時，才同時產生 blocking error 並阻止 Review 完成。
- Review SHALL 定位雙方來源、受影響 terminal 與 rebuild 行為，但不推薦 winner，也不暗示應刪除、排除或保留哪一支 Waler。
- Preview 的確切顏色、線型與 tooltip 文案屬 Presentation implementation detail；Spec 只要求與正式工程線視覺可區分、可定位來源與原因。
