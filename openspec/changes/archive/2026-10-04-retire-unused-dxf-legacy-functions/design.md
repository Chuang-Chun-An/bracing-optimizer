# Design

## 閱讀導航

- **現在必讀（P0）**：Decision 1 的 consumer gate、Decision 2 的精確候選／replacement matrix，以及 Decision 3 的 behavior-preserving 驗證方式。
- **實作前閱讀（P1）**：`proposal.md`、`tasks.md`、三個候選函式附近的現行 replacement path，以及 baseline regression 結果。
- **條件式閱讀（P2）**：只有 audit 發現 indirect caller 時才閱讀 package export、dynamic lookup 或 PyInstaller entry。
- **可先跳過**：_refine_corner_brace_axis_intersections_legacy；已確認仍有 caller/tests，本 change 禁止移除。

## 方案摘要

先對三個候選建立完整 consumer matrix，再確認 production replacement 與 baseline regression。三個候選必須全部同時滿足 zero-consumer gate，才進入精確刪除；任一項失敗即停止並回報，不藉此改 caller、縮小成部分刪除或重構 DXF pipeline。

## 決策對照

| Decision | 對應 proposal 範圍 | 對應 task |
| --- | --- | --- |
| D1. consumer audit 是整體刪除 gate | repository／package／dynamic／build／tests audit | 1.1、1.3 |
| D2. 只刪除三個明列候選，沿用三個現行 replacement | behavior-preserving cleanup | 1.2、2.1～2.4 |
| D3. 以現行 importer regression 證明不變 | production importer／fixtures regression | 1.3、3.1、3.2 |

## Context

`dxf_import/recognition.py` 與 `dxf_import/candidate_points.py` 留有多次辨識改版產生的 underscore-private legacy functions。規劃階段的 repository 搜尋顯示三個候選在 executable code 中只見 definition，沒有 call、import、export、字串 lookup 或 test reference；`dxf_import/__init__.py` 與 `SupportSolver.spec` 也未暴露它們。使用者另已確認沒有 repository 外部程式直接使用這些 private names。這些是 apply 階段重新執行完整 audit 的 baseline，不取代刪除前 gate。

另一個 `_refine_corner_brace_axis_intersections_legacy` 在 `recognition.py` 的現行 `_refine_corner_brace_axis_intersections()` 中仍有 caller，故明確不屬於刪除候選。

規劃階段的 lint／CI 調查顯示：`pyproject.toml` 只將 `pylint` 列為 dev dependency，repository 沒有 tracked CI workflow、pre-commit／tox／nox 設定或文件化 lint 指令；正式測試入口是 `unittest discover`，現有 AST boundary tests 也不檢查 unused imports。因此目前沒有會因保留孤兒 import 而失敗的必要 gate。Task 4.4 仍須在 apply 時重新確認；若屆時必要檢查已存在或手動 lint 已成為交付條件，必須停止並回報，不得藉機刪除 import。

## Goals / Non-Goals

**Goals:**

- 移除可被證明 unreachable 的三個 private functions。
- 保留現行 recognition output、tolerance、priority、repair 與 Review 行為。
- 留下可重複執行的 consumer audit 證據。

**Non-Goals:**

- 不移除所有名稱含 legacy 的程式。
- 不重寫 current DXF pipeline 或重新命名 public API。
- 不調整 geometry tolerance、dedup、candidate selection 或 fixture expected output。

## Architecture Alignment

本 change 不改 Architecture；只縮減 DXF import 子系統內部 unreachable code。dxf_import 的 models、geometry、recognition、validation、controller 與 dialog boundary 維持不變。

## Decisions

### Decision 1: consumer gate 包含非一般 call syntax

audit 必須涵蓋直接 call/import、module alias 與 function-object registration、`__all__`／re-export、`getattr`／名稱字串、monkeypatch tests、PyInstaller hidden import／entry、維護腳本、live 文件與設定。Archived OpenSpec 中的歷史文字引用需記錄為 non-runtime evidence，不視為 consumer，也不得為了讓搜尋歸零而改寫歷史。使用者確認「沒有外部程式 consumer」是外部邊界證據，不能取代 repository audit。

每個候選的 pass condition 為：只有一個預期 definition；repository executable code、tests、exports、dynamic registration 與 build hooks 都沒有 consumer；正式 replacement 有 production caller 與 focused tests；刪除前 baseline 通過。若任何候選不符合，三函式刪除整體停止並回報，不在本 change 搬移 caller、增加 wrapper 或只刪其餘兩個。

### Decision 2: 刪除範圍固定為三個候選

候選與現行 replacement 固定如下：

| 待移除 private function | 現行 replacement／production consumer | 主要 regression |
| --- | --- | --- |
| `_legacy_corner_brace_candidates_from_group` | `_corner_brace_candidates_from_group`，由 `dxf_import/importer.py` import 並呼叫 | `test_dxf_corner_brace_occluded_recognition.py`、`test_dxf_input.py` |
| `_select_waler_inner_lines` | `_resolve_waler_contact_geometry`，由 `dxf_import/importer.py` import 並在 conversion/finalization 呼叫 | `test_dxf_waler_contact_face_recognition.py`、`test_dxf_input.py` |
| `_associate_components_to_struts_legacy` | `associate_components_to_struts`，由 `dxf_import/importer.py`、rebuild paths 與 compatibility wrapper 呼叫 | `test_dxf_waler_contact_adjustment.py`、`test_dxf_beam_brace_contacts.py`、`test_double_support.py`、`test_dxf_input.py` |

實作只刪除上述三個 function definitions，並修正 live docstring 中直接提及 `_select_waler_inner_lines` 的 dangling reference。即使刪除後看見其他疑似 dead helper、constant、setting 或 import，也不連帶移除；`_refine_corner_brace_axis_intersections_legacy` 明確保留。

### Decision 3: behavior preservation 以 current entry points 驗證

不為 dead function 本身保留鏡像測試。刪除前以目前 production importer 執行真實 DXF fixtures，保存 deterministic snapshot，至少包含各 member collection 的數量、engineering identity、幾何與 diagnostics；刪除後以相同 entry point 與 fixtures 逐項比對該快照。另執行 CornerBrace、candidate points、Waler recognition 與 module boundary regression。刪除前後 observable output 必須完全相同，不得修改 expected output 來容納差異。

### Rejected Alternatives

- **依 `_legacy` 命名批次刪除**：名稱不是 consumer 證據，且 `_refine_corner_brace_axis_intersections_legacy` 仍在 production path。
- **保留 wrapper 並標 deprecated**：三個候選是 private 且確認沒有 external contract；wrapper 只會延續第二套路徑的誤導。
- **順便刪除其餘疑似 dead helpers/settings**：缺少本 change 的逐項 consumer 與 behavior audit，會擴張使用者指定範圍。
- **只刪除通過 audit 的其中一部分**：本 change 的前提是三者皆已確認無 consumer；若前提不成立，應停止並重新規劃，而不是靜默改變交付內容。

## Source of Truth

- 是否有 consumer：repository audit 結果 + 使用者的外部 consumer 確認。
- Production behavior：current importer entry points 與 regression tests。
- Public surface：package exports 與現行文件；underscore 名稱本身不足以證明可刪。

## Backward Compatibility / Persistence

沒有 Project schema 或 persistence impact。三個候選為 private 且確認無外部 consumer；如 audit 發現相反證據則不刪除。Runtime DXF output 必須完全相容。

## Risks / Trade-offs

- [動態 caller 搜尋不到] → 搜尋名稱字串、exports、monkeypatch 與 build entry，並跑全套 DXF tests。
- [刪除後出現孤兒程式] → 若有 helper、constant、setting 或 import 變成無人使用，一律保留並記錄，供日後另案處理。
- [真實 fixture 未覆蓋少見路徑] → 使用現有多類 DXF regression，不修改 expected output 來通過。

## Migration Plan

本 change 沒有 persistence 或部署 migration。先完成並回報 audit matrix，並保存真實 DXF fixtures 的 baseline snapshot；再刪除三個 definitions、修正 live dangling docstring，最後跑 focused、DXF boundary、snapshot comparison 與 full suite。任何 audit contradiction、snapshot 差異或 regression 都停止交付並保留原函式；不得修改 expected output 來容納差異。
