# Proposal

## 閱讀導航

- **P0 現在必讀**：本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」，先確認本 change 只放寬圍令接觸側所需的證據，不放寬支撐正式連接。
- **P0 現在必讀**：`specs/dxf-waler-contact-face-recognition/spec.md` 的「候選方向證據可獨立於正式連接 identity」Requirement，確認 side evidence 與 connection evidence 的權限邊界。
- **P0 現在必讀**：`specs/brace-axis-waler-extension/spec.md` 的「多解 terminal 不得形成正式連接」Requirement，確認 unresolved 支撐／斜撐仍維持原子式提交。
- **P1 實作前閱讀**：`design.md` 的 Decision 1～4，以及 `dxf_import/waler_contact_face.py` 中 `build_member_terminal_evidence()`、`resolve_waler_contact_faces()`；理解現行證據模型如何把兩種判定綁在一起。
- **P2 需要時再讀**：`specs/dxf-waler-overlap-diagnostics/spec.md` 的 competition 與 lifecycle Requirements；修改重疊診斷或 exclusion／restore regression 時再讀。Solver、材料規則、Project schema、CornerBrace recognition 與其他 DXF capabilities 可先跳過。

## 快速摘要

- 現行流程要求 member terminal 先唯一對應某支 Waler，該 member 才能提供 Waler 接觸側證據；當 terminal 同時可能連到兩支鄰近或重疊 Waler 時，兩支 Waler 即使都能看出 member 從哪一側接近，也會一起失去內外側判定。
- 本 change 將「member 從 Waler 哪一側過來」的候選方向證據，與「member 最終連到哪支 Waler」的正式 identity evidence 分開。
- 接觸側採「唯一證據優先」：只要 Waler 有可靠 unique evidence，就只由 unique evidence 決定；沒有可靠 unique evidence 時，才使用 competing side-only evidence。相反方向的 competing evidence 不得推翻 unique 結果，只產生可追溯 warning。
- 只有 competing evidence 的 Waler 若方向一致可完成支撐側最外接觸面，若同時指向兩側則維持 contact-face ambiguous；terminal identity 仍可維持 ambiguous，Review 仍受既有 connection blocker 阻擋。
- Candidate Point、正式 endpoint、`FromWaler`／`ToWaler`、forbidden point、Project row 與 Solver input 仍只能使用唯一且完整的正式連接，不會因側向證據而提前成立。

## 現況與目標

在本 change 中，**候選方向證據**只表示「從特定 Waler 看，member 本體位於哪一側」；它不是正式連接關係，也不能證明 member 最後採用該 Waler。

| 面向 | Before | After |
| --- | --- | --- |
| 圍令辨識順序 | Waler 先建立 envelope，但接觸側必須等待 terminal identity 唯一 | Waler 仍先建立 envelope；之後可用合法 terminal candidates 的來向完成接觸側，不必先選出唯一連接 identity |
| W17／W18 類多解情境 | 支撐無法唯一歸屬時，競爭 Waler 都拿不到 side evidence | 每個合法候選 Waler 可各自取得只具方向權限的 evidence；若方向一致，可各自完成接觸面 |
| 支撐正式連接 | 多解時 unresolved | 維持多解時 unresolved，不因 Waler 已選出接觸面而自動挑選 Waler |
| Review 狀態 | Waler contact-face 與 member connection 一起 unresolved | 可呈現「Waler 接觸面已解析、member identity 仍多解」；connection blocker 仍禁止完成匯入 |
| 下游工程資料 | 不完整關係不得進入 Project／Solver | 完全不變；side-only evidence 不具有提交權限 |

## 主要流程

```text
Waler source recognition
  -> 建立 provisional axis + reliable envelope

Strut / Brace source recognition
  -> 對每個 terminal 建立合法 Waler candidates
       -> 對每個 candidate 計算 member 來向（side-only evidence）
       -> candidates 若唯一：另建立正式 terminal identity evidence
       -> candidates 若多解：保留 ambiguity，不選 winner

Waler contact-face finalization
  -> 有可靠 unique evidence：只以 unique evidence 選側
       -> opposing competing evidence：保留 unique 結果 + warning
  -> 無可靠 unique evidence：才使用 competing side-only evidence
       -> 同側一致：選支撐側最外實體表面
       -> 兩側衝突：contact-face ambiguous
  -> 無可靠 evidence 或退化：contact-face unresolved

Member connection finalization
  -> 只接受唯一 identity + formal contact faces + 既有合法交點／長度
  -> 多解仍 unresolved，且 Review 保持 blocked
```

## 不變事項

- 不改變 Waler envelope 的來源資格、完整外框、最外實體表面或 provisional axis 規則。
- 不以 Waler ID、handle、entity order、collection order、距離微差或 first match 選擇正式連接。
- 不允許 side-only evidence 建立 member endpoint、連接 identity、Candidate Point adoption、forbidden point、Project row 或 Solver input。
- 同一 Waler 的可靠 unique evidence 若同時指向兩側，或在完全沒有可靠 unique evidence 時 competing evidence 同時指向兩側，仍須回報 contact-face ambiguity；competing evidence 不得推翻一致的 unique 結果，無關或不合格的 nearby member 不得投票。
- 不改 Project persistence schema、Solver scoring、材料政策或既有 committed Project／Solver transaction semantics。

## Why

現行 contract 把「判斷 Waler 哪一側面向支撐」與「唯一決定 member 連到哪支 Waler」視為同一項證據資格，導致 Y29 等鄰近／重疊 Waler 情境只能解決連接安全，卻不必要地阻止圍令先完成可由幾何方向判斷的內外側。將兩種權限分開，能符合既定的 `Waler -> Strut / Brace -> relationship` 辨識順序，同時保留正式連接的 fail-safe 行為。

## What Changes

- 把 terminal candidate 的幾何來向保存為只供 Waler contact-face finalization 使用的 side-only evidence；不要求該 terminal 已唯一選定 Waler identity。
- 對每支候選 Waler 分別判定 member 本體位於 provisional axis 的哪一側；只有合法、非退化且對該 Waler 可追溯的候選才可參與。
- 採用 unique-first evidence precedence：可靠 unique evidence 是接觸側的 authoritative set；competing side-only evidence 只在沒有可靠 unique evidence 時參與選側，與 authoritative set 相反時只產生不阻擋的可追溯 warning。
- 允許存在 member identity ambiguity 時，競爭 Waler 各自依一致的候選方向證據完成接觸面；connection ambiguity 與 overlap competition diagnostics 仍維持 blocking。
- 維持唯一 terminal identity 才能建立正式 member connection 的既有 hard constraint，並明定 side-only evidence 不得被任何 downstream path 升級成正式關係。
- 調整 Review／diagnostics，使 contact-face resolution 與 terminal identity resolution 可分別呈現及重建，不把「member 多解」自動等同於「Waler 接觸側無解」。
- 新增一般幾何與 Y29 regression，涵蓋 unique／competing 衝突優先級、只有 competing 的同側與兩側衝突、退化方向、無關 member、輸入順序、source exclusion／restore，以及 Y05／Y1A／一般 CAD formal Waler 相容性與 Project／Solver 邊界。

## In Scope

- `dxf_import` 中 member terminal candidates、Waler side evidence、contact-face finalization 與 member connection finalization 的證據分權。
- Strut 與一般 Brace terminal 的 direct／既有合法 extension candidates；不改變 candidate 的幾何資格與距離／延伸邊界。
- Waler overlap／competition diagnostic 與 Review lifecycle 對「接觸面已解析但 identity 仍多解」狀態的相容性。
- Preview／Review 對 formal Waler contact face、unresolved member connection 與 blocking problem 的一致投影。

## Out of Scope

- 自動合併、刪除、排除、改名或選擇重疊／鄰近 Waler。
- 新增讓使用者在 UI 直接指定 Waler identity 的 repair 工具。
- 修改 Waler envelope extraction、component qualification、overlap `50%` 門檻、Brace `600 mm` 延伸上限或其他既有幾何 tolerance。
- 修改 CornerBrace recognition、Project schema、Solver input contract、Solver scoring 或材料規則。
- 藉此 change 整理其他 recognition technical debt 或重構整個 DXF pipeline。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-waler-contact-face-recognition`：允許合法 terminal candidates 在 identity 尚未唯一時提供只具方向權限的 Waler side evidence，並將 contact-face resolution 與 connection resolution 分開判定。
- `brace-axis-waler-extension`：把既有「ambiguous 端不得提供任何競爭 Waler side evidence」改為「不得建立正式 identity，但可提供不具連接權限的候選方向證據」，並維持整支 Brace 原子式 formal commit。
- `dxf-waler-overlap-diagnostics`：重疊競爭仍是 blocking identity problem，但不再一律要求兩支 Waler 的 contact-face outcome 同時 unresolved；contact-face state 改由各自 side evidence 決定。

## Impact

- **DXF recognition／geometry**：`dxf_import/waler_contact_face.py` 的 terminal candidate、evidence type、contact-face resolution 與 Brace verdict；`dxf_import/recognition.py` 的 orchestration、diagnostic projection 與 staged geometry apply。
- **Review／Presentation**：既有 problem records 與 Preview 樣式須能同時表達 formal Waler contact face 和 unresolved member connection，不建立第二套幾何判定。
- **Tests**：`tests/test_dxf_waler_contact_face_recognition.py` 為主要 regression；視實際投影影響補充 Review workflow／layout focused tests。
- **Architecture**：沿用既有 `dxf_import` recognition -> Review -> Project boundary，不改 layer 或 dependency direction；single source of truth 仍在 pure recognition outcome。
- **Domain／Workflow**：會改變 DXF recognition 的長期 evidence contract，完成實作後預期更新 `docs/DOMAIN.md` 中 Waler contact-side／formal connection 的區分；若 Review lifecycle 描述受影響，再最小更新 `docs/WORKFLOW.md`。不影響 Solver truth。

## 尚未決定與重新評估條件

- 預設 side-only evidence 沿用既有 terminal candidate 資格，不新增較寬鬆的 proximity 搜尋；若 Y29 fixture 顯示現有 candidate builder 在 W17／W18 情境根本不會產生雙方候選，需先回報並另行決定是否擴張 candidate eligibility。
- 預設 direct 與目前已合法的 Brace axis-extension candidates 都可產生 side-only evidence；若 regression 證明 extension candidate 的來向不足以可靠判定 Waler 側別，則限縮為 direct candidates，且須先回修 spec／design。
- 本 change 不決定 UI 如何讓使用者人工選定最終 identity；若仍需保留兩支 Waler 並完成匯入，應另立 repair change。

