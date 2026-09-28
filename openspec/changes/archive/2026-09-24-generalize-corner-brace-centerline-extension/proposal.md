# Proposal

## Why

DXF 角撐目前只有在以 `connection_plate_midpoints` 辨識時，才會進入既有中心軸端點 refinement，將角撐主桿中心軸延伸到圍令內線與支撐中心線。這使 Y1A 類連接板圖塊能取得正確工程端點，但 Y29 類由雙平行主桿取得可靠中心軸的角撐，仍可能因 recognition-method gate 而停在支撐外緣或連接板附近。

本 change 要修正的是角撐工程端點：只要正式 `corner_brace` 已具有可靠中心軸，就應沿用既有選定的圍令／支撐關係，把該軸延伸到圍令內線與支撐中心線，而不應限定只有連接板辨識方法可以執行。

## What Changes

- 保留既有 `connection_plate_midpoints` 連接板辨識及 Y1A 正確行為。
- 將目前 method-only gate 改為可靠中心軸 gate，使 `parallel_edges_midline` 與其他具有同等中心軸證據的正式角撐可共用既有 endpoint refinement。
- 沿用目前 Waler／Strut 選擇及端點方向判定；本 change 不重新枚舉構件配對，也不新增候選模糊或 winner policy。
- 將可靠角撐中心軸分別延伸到既有選定 Waler 的有限內線與 Strut 的有限中心線；兩個交點及校正後長度全部有效時才一次採用。
- 讓校正後端點成為角撐衍生長度、`CornerBraceConnection` 及背填／圍令寬度調整的共同基準。
- 增加 Y1A 既有行為、Y29 類雙平行主桿、有限交點失敗及 Waler contact 串接的 regression tests。

### In Scope

- DXF `corner_brace` 可靠中心軸資格與 endpoint refinement applicability。
- 以既有選定 Waler／Strut 工程線計算角撐兩端交點。
- 角撐校正結果與既有衍生長度、Waler contact connection／recalculation 流程的整合。
- 相關 DXF recognition 與 Waler contact regression tests。

### Out of Scope

- Waler／Strut candidate duplication、配對唯一性、competing association 或 ambiguity policy。
- 修改 `ambiguous_connection_delta_mm`、新增 runner-up threshold，或以 50/50、51/49 規則選擇構件。
- Solver、材料規則、Project schema 或一般 `brace`／`strut` 辨識行為。
- 對所有斜線、所有角撐圖層圖元或任意最近構件做無條件吸附。
- 新增人工角撐配對 UI、修改既有幾何 tolerance 數值或重新設計 DXF recognition framework。

## Capabilities

### New Capabilities

- `dxf-corner-brace-centerline-extension`: 定義正式角撐具有可靠中心軸時，如何沿用既有 Waler／Strut 選擇安全校正至圍令內線與支撐中心線，以及失敗時的原子保留語意。

### Modified Capabilities

- 無。

## Impact

- 主要影響 `dxf_import/recognition.py` 的角撐後處理；`dxf_import/importer.py` 維持既有 pipeline，`dxf_import/waler_contact_adjustment.py` 應沿用校正後幾何而不建立第二套端點規則。
- 測試主要影響 `tests/test_dxf_input.py` 與 `tests/test_dxf_waler_contact_adjustment.py`。
- 不新增外部依賴，不改 Project persistence schema，不改構件配對／ambiguity policy、Architecture、Core Domain、Solver 或 Workflow 的長期責任邊界。
