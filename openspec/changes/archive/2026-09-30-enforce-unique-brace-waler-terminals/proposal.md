# Proposal

## 閱讀導航

- **P0 現在必讀**：本文件的「快速摘要」、「現況與目標」、「主要流程」與「In Scope／Out of Scope」，用來確認 B15／W18／W19 的產品決策。
- **P0 現在必讀**：本 change 的 `specs/brace-axis-waler-extension/spec.md`，特別是「延伸結果必須一致更新正式 Brace 連接」及「Terminal evidence 必須單向支援 Waler contact-face 判定」Requirements。
- **P0 現在必讀**：相鄰 change `../detect-waler-overlap-errors/proposal.md` 的「In Scope／Out of Scope」，確認圍令重疊診斷與斜撐端點裁決的責任邊界。
- **P1 實作前閱讀**：本 change 的 `design.md`，以及 `docs/ARCHITECTURE.md` 的「DXF Import」與「Project conversion」段落。
- **P2 需要時再讀**：`openspec/specs/dxf-waler-contact-face-recognition/spec.md` 的 terminal identity 與 finalization 規則；可先跳過 Solver、材料配置及 CornerBrace repair 的其他規格，因為本 change 不修改那些流程。

## 快速摘要

- 現況會在 B15 一端唯一連到 W16、另一端同時命中重疊的 W18／W19 時正確回報歧義，但仍把來源輪廓推得的 P02 留在看似正式的斜撐幾何中。
- 本 change 規定：自動辨識的 Brace（斜撐）兩端都必須各自唯一對應不同的有限 Waler（圍令），且 contact faces、有限交點與提交後長度全數合法，整支 Brace 才能正式成立；任一條件失敗即整支 unresolved，不得靠 Candidate Point、ID 或順序補選。
- 唯一 terminal evidence 會先作為對應 Waler 的接觸側證據；member-level verdict 只在 contact face 完成後決定整支 Brace 是否正式成立，不會反向改寫 Waler 判定。
- 排除重複 Waler 後若只剩唯一合法關係，rebuild 才可依既有軸線與正式 contact face 交點規則完成端點校正；Y29 fixture 預期交點位於 P07，但 P04／P06 中點不是新的計算方法。
- 不改變 250 mm direct tolerance、600 mm 軸向延伸上限、Brace 本體辨識、CornerBrace 規則或 Solver 評分。

## 現況與目標

「source-supported axis」是由斜撐原始 DXF 幾何推得、可供 Review 追溯的暫存軸線；「formal Brace」則是兩端 Waler 關係已完整成立、可轉入 Project 的正式斜撐。

| 項目 | Before | After |
| --- | --- | --- |
| 單端唯一、另一端多解 | 唯一端可被校正；歧義端保留來源端點，整體畫面仍可能像一支已成立的 Brace | 整支 Brace 明確標成 unresolved；兩端結果只作辨識證據，不形成部分正式 Brace |
| B15 對 W18／W19 | 回報 `AMBIGUOUS_WALER_CONNECTION`，但 P02 仍留在 member geometry，P07 只是一個候選 | 問題列出競爭 Waler identities；P02 可作來源證據但不是正式端點，P07 也不得在歧義未解除前被採用 |
| 刪除／排除 W18 | rebuild 後因只剩 W19 而可正確校正 | 保持此行為；兩端皆唯一且 contact faces 已正式完成後，才一次建立完整 B15；此 fixture 的 W19 端交點預期位於 P07 |
| 單端 evidence 與 Waler contact face | Brace 整體未完成時，單端 evidence 是否仍可支援 Waler 接觸側不夠明確 | 唯一端 evidence 仍可支援該 Waler；ambiguous 端不得支援任何競爭 Waler；Brace verdict 不回饋 contact-face 判定 |
| Candidate Points | 初始 start／end 可持續成為建議選擇，即使 Waler identity 未唯一 | 候選點不得繞過 terminal identity 歧義或把 unresolved Brace 升級成 formal Brace |
| 完成匯入 | blocking problem 會阻擋，但 staged member 仍混合部分正式與來源幾何 | unresolved Brace 不得轉成 Project row 或進入 Solver；既有 committed Project／Solver 結果不變 |

## 主要流程

```text
辨識 Brace 來源幾何與可靠軸線
  -> 對 start / end 各自蒐集 direct 候選
  -> 未直接連接端再依既有規則蒐集 <= 600 mm 的 outward extension 候選
  -> 每端以最近合法位置判定 Waler identity 數量
       -> 恰好 1 支：建立唯一 terminal evidence，供該 Waler 判定接觸側
       -> 0 支或 2 支以上：不建立側向 evidence；產生 blocking problem
  -> 由合格 terminal evidence 完成各 Waler contact-face finalization
  -> member-level verdict 檢查兩端唯一、不同 Waler、正式 contact faces、
     合法有限交點與合法提交長度
       -> 全部成立：一次提交完整 formal Brace、兩端點與 FromWaler / ToWaler
       -> 否：整支維持 unresolved，只顯示可追溯的來源／候選證據
  -> exclusion / restore / rebuild 從目前 active sources 重算
```

## 不變事項

- Brace 本體來源辨識、可靠軸線與來源 provenance 的產生方式不變。
- direct connection tolerance `250 mm`、maximum axis extension `600 mm`、有限 Waler segment 與 outward-ray 規則不變。
- 不合併重疊 Waler、不以 Waler ID、DXF handle、entity order、candidate order 或浮點微差選 winner。
- Brace 正式端點仍由 Brace 軸線與 selected formal Waler contact face 的既有有限交點規則取得；不得改成直接計算輪廓端點中點。
- Strut、CornerBrace、Column、Beam 的辨識規則不變；CornerBrace 僅作「多解不提交正式關係」的行為參考。
- Solver scoring、候選數、材料規則、Project schema 與已提交的 Project／Solver transaction boundary 不變。

## Why

目前 B15 在起點唯一連到 W16、終點同時命中 W18／W19 時，雖然已產生 blocking ambiguity，卻仍保留 P02 於看似正式的 member geometry，造成「一端已正確、另一端為何突出」的誤導，也讓 Candidate Point 與正式關係的界線不清楚。現在需要把既有的「單端多解不可任選」提升為完整 Brace lifecycle：任一端不唯一，整支斜撐都不得形成部分正式工程 truth。

## What Changes

- 將 Brace 自動辨識的正式成立條件明確化為：start 與 end 各自恰好一個可識別有限 Waler，且兩端 Waler 不同。
- 補齊正式成立的其餘必要條件：兩端 Waler contact faces 均已正式完成、Brace 軸線與各 selected face 均有合法有限交點，且提交後 Brace 長度合法；任一條件失敗皆使整支 Brace unresolved 並 blocking。
- direct 與 extension 共用同一 terminal uniqueness gate；不能因 direct 候選多解而改走 extension，也不能用 Candidate Point 或來源端點規避歧義。
- 明確建立單向依賴：唯一 terminal evidence 可先參與其 Waler 的接觸側判定；ambiguous terminal 不得提供任一競爭 Waler 的側向 evidence；其後的 member-level verdict 只控制 Brace formalization，不回頭改變 contact-face outcome。
- 任一端零解、多解或兩端指向同一 Waler 時，整支 Brace 維持 unresolved，產生 blocking problem，並保留 Brace、端別及所有競爭 Waler identities 供 Review 說明。
- 把「來源支持的暫存軸線／候選交點」與「正式 Brace geometry／connection」分開呈現；未解析證據不得轉成 Project row 或 Solver input。
- 保留 exclusion／restore／rebuild 行為：競爭來源被排除後若關係變成唯一，才可重新建立完整正式 Brace；復原競爭來源時則回到 unresolved。
- 補上 Y29 B15（source handle `71E`）對 W18（`69F`）／W19（`720`）的回歸驗證；唯一 W19 時仍依既有軸線／正式 contact-face 有限交點規則計算，fixture 預期該交點在具名容差內等價於 P07（P04／P06 在軸線上的中點）。

## In Scope

- 一般 Brace 的 direct／extension terminal candidate cardinality、兩端完整性與 formal commit gate。
- terminal evidence、Waler contact-face finalization 與 member-level verdict 的單向資料依賴。
- ambiguity／not-connected diagnostics 的端別、Brace identity 與競爭 Waler identities。
- staged Review 中 unresolved Brace、來源軸線、Candidate Points、正式 connection 與 Project conversion 的一致性。
- source exclusion、restore、rebuild、manual endpoint replay 與 confirmation invalidation 對此 gate 的既有 lifecycle 整合。
- `dxf_import/waler_contact_face.py`、`dxf_import/recognition.py`、`dxf_import/candidate_points.py`、import finalization／validation 及其聚焦測試。

## Out of Scope

- 自動合併、刪除或挑選重疊 Waler；重疊比例與一般 overlap warning 由 `detect-waler-overlap-errors` change 負責。
- 新增「人工指定競爭 Waler identity」的 UI；只選一個幾何點不足以解除兩支重疊 Waler 的 identity 歧義。
- 修改 Brace 中心線／寬度辨識演算法、P04／P06 的輪廓取法或新增中心線重建公式。
- 將「取 P04／P06 中點」實作成通用端點演算法；P07 僅是 Y29 fixture 對既有交點規則的驗證結果。
- 修改 Strut／CornerBrace recognition、repair、Project schema、Solver input schema、Solver scoring 或材料配置。
- 清理既有 DXF import 技術債或重構整條 recognition pipeline。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `brace-axis-waler-extension`：把既有單端 ambiguity 與 incomplete connection 規則收斂為整支 Brace 的原子式 formal commit；補充 direct 多解、候選點隔離、Review 顯示及 Y29 B15 回歸情境。

## Impact

- **DXF Infrastructure**：Brace terminal evidence、resolution application、candidate point recommendation、formal connection finalization 與 validation projection。
- **Review workflow**：unresolved Brace 的預覽語意、blocking problem 內容、exclusion／restore／rebuild 與完成匯入 gate；不新增新的持久化格式。
- **Project／Solver boundary**：僅強化「不完整 Brace 不得轉入 Project」的既有邊界；不改 schema 或演算法。
- **Tests**：擴充 terminal/contact-face 單向依賴、provisional contact face、無合法交點／長度、production verdict、terminal ambiguity、輸入順序不變性、候選點不可繞過、Review blocking lifecycle 與 Y29 B15 fixture regression。
- **Long-term truth**：預期補充 `docs/DOMAIN.md` 中 formal Brace 的完整且唯一兩端關係，並更新 `docs/WORKFLOW.md` 的 Brace connection lifecycle，明定單端失敗時整支 unresolved；不改 Architecture layer、Solver truth 或材料工程規則。
- **Implementation prerequisite**：開始 apply 前，必須先確認 `detect-waler-overlap-errors` 的 terminal diagnostics／identity provenance 格式已定案或已合併，避免兩個 change 各自建立不相容格式。

## 尚未決定與重新評估條件

- 本 change 預設沿用既有 ambiguity error code 家族，不為 B15 另造專用錯誤碼；若實作時發現現有 code 無法同時承載端別與競爭 identities，才評估新增通用 Brace terminal diagnostic code。
- 本 change 不提供從 UI 直接挑選重疊 Waler identity 的 repair；若使用者未來要求保留兩支重疊 Waler 並人工指定其中一支，應另立 change，定義 identity selection、重播與失效條件。
