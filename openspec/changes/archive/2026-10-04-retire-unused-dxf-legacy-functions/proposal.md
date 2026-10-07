# Proposal

## 閱讀導航

- **P0 現在必讀**：本 proposal 的前五節；`design.md` 的 Decision 1（consumer audit gate）與 Decision 2（精確刪除清單）；`docs/ARCHITECTURE.md` 的「3.6 DXF Subsystem」。
- **P1 實作前閱讀**：`dxf_import/recognition.py`、`dxf_import/candidate_points.py` 的三個候選與正式 replacement；`tasks.md` 第 1 組的 audit matrix。
- **P2 需要時再讀**：修改 CornerBrace、Waler contact 或 component association 驗證時，分別閱讀 `dxf-corner-brace-occluded-rail-recognition`、`dxf-waler-contact-face-recognition`、`dxf-column-association-repair` 與 `beam-member-connection-validation` 的相關 Requirement。
- **可以先跳過**：Project persistence、Solver、export、Presentation 與其他 DXF recognition capability；本 change 不改它們。

## 快速摘要

- Repository 仍保留三個只見 definition、未見 executable consumer 的舊 DXF 實作，增加閱讀與誤改成本。
- 使用者確認沒有 repository 外部程式直接 import `dxf_import` 的底線私有函式。
- 只有三個候選全部通過靜態、runtime entry point、package/export、dynamic lookup、build 與測試 audit，才可移除；任一項不成立就停止實作並回報。
- 仍有正式呼叫、tests 或 compatibility contract 的 legacy helper 一律保留。

## 現況與目標

| | Before | After |
| --- | --- | --- |
| 私有 legacy functions | 舊新實作並存，部分只剩 definition | 無 consumer 的舊實作移除 |
| 相容性判斷 | 容易因名稱含 legacy 一概而論 | 三個候選各自有 zero-consumer、replacement 與 regression 證據 |
| 辨識結果 | 由現行 production path 產生 | 行為與 regression fixtures 完全不變 |

## 主要流程

1. 對三個候選逐項建立 definitions、direct/indirect imports、function-object alias、dynamic lookup、package exports、tests、build hooks、維護腳本與 production entry points 的 consumer matrix。
2. 確認每個 replacement 已由 production path 使用，並在刪除前以真實 DXF fixtures 保存 member 數量、identity、幾何與 diagnostics 快照。
3. 只有整個 gate 通過才刪除三個函式 definition；若 audit 與「三個皆無 consumer」的前提衝突，停止而不是縮小或擴張刪除清單。
4. 修正 live code 中直接指向已刪名稱的 stale docstring，再重跑 targeted DXF tests、boundary tests 與完整回歸，並逐項比對刪除前快照。

## 不變事項

- 不刪除仍有 caller 或 tests 的 `_refine_corner_brace_axis_intersections_legacy` 等 compatibility path。
- 不調整 geometry tolerance、recognition priority、dedup、repair 或 Review 行為。
- 不將私有函式轉成新的 public API，也不進行整個 recognition module 重構。
- 發現動態或外部 package consumer 證據時，該項停止移除並記錄原因。

## Why

部分早期 DXF migration 實作在新路徑完成並封存後仍留在 production modules，搜尋結果看起來像現行第二套規則。既然底線私有函式沒有外部相容承諾，應在有充分 consumer audit 與 regression 證據的前提下移除確定無用的殘留。

## What Changes

- Audit `_legacy_corner_brace_candidates_from_group`、`_associate_components_to_struts_legacy`、`_select_waler_inner_lines`。
- 驗證 repository executable code、package exports、dynamic attribute lookup、PyInstaller entry、維護腳本與 tests 均無 consumer。
- 三者全部通過 gate 後，只移除這三個 private function definitions，並修正 live docstring 的 dangling name reference。
- 以目前 production importer 與實際 DXF fixtures 保存刪除前快照，並在刪除後逐項比對行為不變。

### In Scope

- `_legacy_corner_brace_candidates_from_group`、`_associate_components_to_struts_legacy`、`_select_waler_inner_lines` 三個明列候選。
- Live docstring 中因上述刪除而形成的 dangling reference 修正。

### Out of Scope

- `DXFImporter.convert()`、`_Candidate` 或 recognition pipeline 的架構重構。
- 任何行為、規格、tolerance、命名或 public API 變更。
- 因名稱含 `legacy` 而未經 audit 的批次刪除。
- 連帶刪除其他 helper、constant、setting、import 或 archived OpenSpec 歷史；即使它們看似可再清理，也需另案處理。

## Capabilities

### New Capabilities

- 無；本 change 是 behavior-preserving internal cleanup。

### Modified Capabilities

- 無；`.openspec.yaml` 使用 `skip_specs: true`。

## Impact

- 主要影響 `dxf_import/recognition.py`、`dxf_import/candidate_points.py` 與直接提及被移除名稱的 live docstring；測試只用來驗證既有行為，不改 expected output。
- Architecture、Domain 與 Workflow truth 不變；預期降低 DXF 辨識維護成本。

