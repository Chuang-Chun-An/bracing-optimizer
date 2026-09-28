# Design

## Context

目前 importer 在各 role 的 candidate recognition 與 Waler inner-line 選擇完成後，呼叫 `_refine_corner_brace_axis_intersections()`，再建立正式 `CornerBrace`。這個階段同時看得到角撐 `_Candidate`、已選 Waler 工程線與 Strut centreline，而且下游 `attach_corner_braces_to_struts()`、candidate point 建立及 `initialize_waler_contact_review()` 尚未執行，因此適合統一角撐工程端點。

現行 refinement 以 `candidate.recognition_method == "connection_plate_midpoints"` 作為入口條件。進入後，`_corner_brace_center_axis()` 可從 `boundary_lines` 的兩條 longitudinal rails 建立 midline，再把該中心軸延伸到 Waler 內線與 Strut 中心線。`parallel_edges_midline` 已具有同類雙平行主桿證據，卻因 method-only gate 完全略過 refinement，所以 Y29 類角撐可能停在支撐外緣或連接板附近。

現行函式同時包含 Waler／Strut 最近構件選擇及 direct／reverse 端點方向判定。本 change 不重做這部分，也不引入新的 ambiguity policy；只泛化「哪些正式角撐可使用可靠中心軸 refinement」，並確保成功後的正式端點流入既有下游流程。

本變更屬 DXF import infrastructure 的 recognition behavior 修正，遵循現有 `recognition → importer orchestration → association/validation → review` 方向，不改變 Core Domain、Application、Algorithms 或 Presentation 的責任。

## Goals / Non-Goals

**Goals:**

- 以可靠中心軸證據而非單一 recognition method 名稱決定是否執行角撐 endpoint refinement。
- 讓 Y1A `connection_plate_midpoints` 與 Y29 類 `parallel_edges_midline` 共用中心軸交點計算。
- 沿用目前已選 Waler／Strut 及 direct／reverse 端點方向，不改變構件 association policy。
- 兩端有限交點與最小長度全部有效後才原子更新角撐工程端點。
- 讓正式 `CornerBrace.start/end` 成為衍生長度、connection 與 Waler contact adjustment 的 single source of truth。
- 保留 Y1A 連接板辨識及既有正確結果。

**Non-Goals:**

- 不處理 Waler／Strut candidate duplication、配對唯一性或 competing association ambiguity。
- 不修改 `ambiguous_connection_delta_mm`，不新增 50/50、51/49、runner-up threshold 或 winner policy。
- 不建立通用 snapping framework，也不修改 geometry tolerance 預設值。
- 不新增人工角撐配對 UI 或新的 persistence 欄位。
- 不修改一般 Brace／Strut recognition、Waler contact 位移公式或角撐固定長度重算公式。
- 不將單一無佐證斜線升級成可自動延伸的可靠中心軸。

## Decisions

### 1. 將 refinement applicability 從 method-only 改為 reliable-axis gate

保留 `_refine_corner_brace_axis_intersections()` 的 pipeline 位置，但先取得 candidate 的可靠中心軸，再決定是否走中心軸交點 refinement。可靠軸沿用 `_corner_brace_center_axis()` 現有雙 longitudinal rail 幾何條件，包括 minimum length、parallel angle、projection overlap 與 component width boundary。

這直接涵蓋：

- `connection_plate_midpoints` 保存的兩條主桿；
- `parallel_edges_midline` 保存的雙平行邊；
- 其他既有 recognition method，僅在它已提供同等 `boundary_lines` 證據且 helper 能建立中心軸時適用。

既有 `_corner_brace_candidates_from_group()` 連接板辨識不移除；它仍負責由 compound INSERT 辨識 Y1A 類角撐。這個 change 只讓它與其他可靠中心軸來源共用後處理。

若非連接板方法沒有可靠中心軸，泛化規則不修改 candidate。Y1A 既有 compatibility behavior 由 characterization tests 鎖定；本 change 不藉機重寫連接板 recognition 或其既有 fallback。

**理由：** 問題是 refinement 的 method gate 過窄，不是需要重建整套角撐辨識或構件配對。

**替代方案：** 只把 `parallel_edges_midline` 加進 method allowlist。拒絕，因為 method 名稱本身不是中心軸證據，未來其他已具雙主桿證據的方法仍會遇到相同問題。

### 2. 沿用現有 Waler／Strut 選擇與端點方向

現行 refinement 會以 candidate 初始兩端與構件距離取得 Waler／Strut，並比較 direct／reverse score 決定哪一端屬於 Waler、哪一端屬於 Strut。這個流程在本 change 保持原樣；泛化後只把可靠中心軸帶入後續交點計算。

本 change 不枚舉所有 Waler／Strut 組合、不比較 runner-up、不新增配對唯一性或 ambiguity diagnostics。若現行 association 對重複 geometry 有問題，留給獨立 upstream workflow 處理。

**理由：** 使用者要修正的是已辨識角撐沒有延伸到支撐中心線，而不是同時改寫構件 association 規則。把兩個問題綁在一起會擴大風險及測試範圍。

**替代方案：** 重新枚舉兩種端點方向與全場 Waler／Strut 組合，再用 `ambiguous_connection_delta_mm` 選唯一方案。拒絕，因為這正是本 change 明確 deferred 的模糊配對政策。

### 3. 可靠中心軸的兩端交點採原子更新

對已通過 reliable-axis gate 的角撐，使用無限角撐中心軸分別與既有選定 Waler 的有限 inner line、Strut 的有限 centreline 求交。只有下列條件全部成立才提交：

1. Waler 交點存在且位於有限 inner line；
2. Strut 交點存在且位於有限 centreline；
3. 兩交點形成的長度不小於現行 minimum component length。

Refinement 先以 local values 完成計算，成功後才一次更新 `start`、`end`、`recognized_axis`、`reference_point` 與既有成功 method。任一條件失敗時，不得留下單端更新；保留原 candidate 並沿用 `CORNER_BRACE_CONNECTION_POINT_FAILED` 或現有相容診斷，不新增 ambiguity code。

成功端點仍投影回有限 Waler／Strut segment，以消除浮點交點誤差。

**理由：** 中心軸延伸只有在兩端都具工程意義時才完整；單端更新會讓角撐長度與 downstream attachment 使用不一致的基準。

### 4. 下游只消費正式校正後 CornerBrace 幾何

Refinement 保持在正式 model 建立之前。成功後的 `CornerBrace.start/end` 自然流入：

- `attach_corner_braces_to_struts()` 的角撐衍生長度；
- `build_candidate_points()` 的正式端點；
- `initialize_waler_contact_review()` → `build_corner_brace_connections()` 的 Waler/Strut attachment、hole station、fixed length；
- `plan_waler_contact_adjustment()` 的後續固定孔位／固定長度重算。

`waler_contact_adjustment.py` 不重做中心軸延伸，也不保存另一份未校正 attachment。除非 integration test 發現該模組繞過正式 `CornerBrace`，否則不修改其演算法。

### 5. 保持既有架構、association policy 與資料相容性

此變更沿用 DXF import 子系統既有責任分工：

- `recognition.py`：可靠中心軸 applicability 與 endpoint refinement。
- `importer.py`：維持既有呼叫順序及正式 model 組裝。
- `candidate_points.py`／`waler_contact_adjustment.py`：消費正式幾何，不新增 recognition 規則。
- `validation.py`：沿用既有 failure code；本 change 不增加 ambiguity classification。

不新增 Project 欄位或 schema migration，不修改 Waler／Strut candidate selection、association ambiguity、source fingerprint、manual replay 或 Review persistence。

## Data and Control Flow

```text
recognized corner_brace candidate
        │
        ├─ no reliable center axis
        │      └─ keep existing behavior / geometry
        │
        └─ reliable center axis
               │
               ├─ reuse existing Waler / Strut selection
               ├─ reuse existing direct / reverse endpoint direction
               ├─ intersect axis with finite Waler inner line
               ├─ intersect axis with finite Strut centreline
               └─ both valid + legal length?
                       ├─ no  → keep original candidate atomically
                       └─ yes → commit corrected CornerBrace endpoints
                                      │
                                      ▼
                    derived length / candidate points /
                    CornerBraceConnection / Waler contact adjustment
```

## Risks / Trade-offs

- **[Risk] 某些 method 有 boundary lines，但不是可靠主桿雙邊** → 沿用既有 angle／overlap／width／length gate；沒有可靠軸就不套用泛化 refinement。
- **[Risk] 現有 nearest-member association 本身選錯構件** → 本 change 不擴大處理；以 regression 確認 association 行為沒有被悄悄改變，另由後續 workflow 處理重複／模糊 geometry。
- **[Risk] 有中心軸但其中一個有限交點不存在** → 兩端原子拒絕並保留原 candidate，不允許單端成功。
- **[Risk] 泛化 gate 影響 Y1A 連接板結果** → 以現有 Y1A 角撐數量、中心軸、兩端與衍生長度作 regression baseline。
- **[Risk] 校正後端點改變固定長度及支撐衍生長度** → 這是預期工程結果；integration test 驗證 attachment 位於支撐中心線，且後續調整使用同一 baseline。
- **[Risk] DXF 實例檔不適合成為穩定測試依賴** → 使用最小合成 DXF 固定 geometry contract；實例檔僅在 repo 內可穩定取得時做 smoke regression。

## Deferred / Out of Scope

Waler／Strut duplicate geometry、competing association、最佳與 runner-up 差異、`ambiguous_connection_delta_mm` policy，以及任何 50/50／51/49 winner 規則全部 deferred。本 change 不修改、不測試新政策，也不把這些議題設為實作 blocker。

## Migration Plan

1. 先加入現有 Y1A 行為與 Y29 類 `parallel_edges_midline` 的 characterization／failing tests。
2. 將 method-only gate 改成 reliable-axis applicability，保留既有 member selection 與端點方向。
3. 驗證兩端原子交點及下游衍生長度、Waler contact connection 都使用正式校正端點。
4. 執行 focused DXF tests、module boundary tests 及完整 test suite。

回退時只需還原 recognition refinement 與相應 tests；沒有 persistence migration、association migration 或資料回寫需要撤銷。
