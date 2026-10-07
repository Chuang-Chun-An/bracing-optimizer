# Proposal

## 閱讀導航

| 優先級 | 現在要回答的問題 | 文件／段落 | 閱讀目的 |
| --- | --- | --- | --- |
| P0 現在必讀 | 為什麼現行斜撐會變角度與長度？ | 本文件「現況與目標」 | 確認問題與目標行為 |
| P0 現在必讀 | 新行為如何同時保持斜撐角度與長度？ | 本文件「主要流程」 | 理解「剛體平移」與兩端接點聯立重算 |
| P0 現在必讀 | 哪些情況不得自動套用？ | 本文件「In Scope」與「不變事項」 | 確認無解時採原子失敗，不回退成旋轉或伸縮 |
| P1 實作前閱讀 | 精確幾何、基準狀態與相容性如何處理？ | `design.md` 的 Decision 1～5 | 實作聯立解、人工端點 baseline-WCS 保存、replay 與相容性 |
| P1 實作前閱讀 | 可觀察行為與邊界是什麼？ | `specs/dxf-waler-contact-adjustment/spec.md` | 實作與測試的正式依據 |
| P2 需要時再讀 | 現有 Brace 正式連接如何建立？ | `openspec/specs/brace-axis-waler-extension/spec.md` 的「延伸結果必須一致更新正式 Brace 連接」 | 修改 recognition rebuild 或 connection validation 時確認既有完整性契約 |
| P2 需要時再讀 | DXF Review 的 staged／atomic state 如何運作？ | `docs/WORKFLOW.md` 的「DXF Import / Review」與 Waler contact-face canonical finalization | 修改 preview、apply、replay 或 rollback 時確認 state ownership |

本次可以先跳過 `docs/SOLVER.md`、Support／Waler Solver specs、CornerBrace repair specs 與材料最佳化規格；此 change 不修改 Solver、材料政策或角撐修補行為。

## 快速摘要

- 現行 Waler 背填／寬度調整只移動一般斜撐的一端並保留該端圍令站距，因而改變斜撐角度與長度。
- 新行為把一般斜撐視為剛體：兩端使用同一平移向量，斜撐方向與長度保持原設計值。
- 即使只有一端圍令移動，另一端接點也會沿其圍令滑動；兩端必須由最終圍令幾何聯立重算。
- 人工端點一律保存為尚未套用 Waler 尺寸 adjustment 的 baseline WCS；若使用者在已調整畫面上修改，系統先扣除該 Brace 目前的共同平移，再保存並重算。
- 若聯立幾何無唯一合法解、接點超出有限圍令，或平行圍令位移不相容，整次調整停止，不部分套用，也不退回舊有旋轉／伸縮行為。
- Strut、CornerBrace、Waler 位移公式、Project schema 與 Solver 規則維持不變。

## 現況與目標

「剛體平移」在本 change 中表示斜撐兩端套用同一個 WCS 位移向量；因此兩端差向量、角度與長度皆不變。

| 項目 | Before：現況 | After：目標 |
| --- | --- | --- |
| 移動端接點 | 保留原圍令站距，跟著目標圍令平移 | 由兩端最終圍令共同決定，可沿目標圍令滑動 |
| 另一端接點 | 固定不動 | 沿另一端圍令滑動，以滿足同一剛體平移 |
| 斜撐角度 | 可能改變 | 保持原設計角度 |
| 斜撐長度 | 可能加長或縮短 | 保持原設計長度 |
| 無解行為 | 現行流程沒有剛體聯立條件 | 阻止整次 atomic apply，保留提交前狀態並顯示原因 |

## 主要流程

```text
使用者修改某支 Waler 的背填／寬度
  -> 由各 Waler baseline 與採用尺寸建立兩端最終有限接觸線
  -> 取 Brace baseline 向量 v = end - start
  -> 聯立求唯一平移 t，使 start + t、end + t 分別落在兩端最終 Waler
  -> 驗證有限線段、連接 identity、角度與長度不變
  -> 預覽兩端新站距與共同平移
  -> 全部合法才原子套用並重建 downstream Review facts
```

人工端點與 Resume／replay 使用固定順序：

```text
recognition
  -> replay manual endpoints（baseline WCS）
  -> 重新推導正式連接並建立 formal Brace baselines
  -> 套用／replay Waler 尺寸 decisions
  -> 由 baseline 與兩端最終 Waler 重算，每筆位移只套用一次
```

若人工端點是在已調整畫面上選取，系統以目前共同平移 `t` 保存「點選 WCS − t」。換算後的端點必須落在其 baseline Waler 有限線段上；否則阻止此次修改並保留原 Review state，不做 clamp、吸附或硬存。

## 不變事項

- Waler 接觸線位移仍由既有「採用背填差 + 採用圍令寬度差」與已確認支撐側法向決定。
- Strut 仍沿既有中心線與調整後 Waler 求有限交點；本 change 不把 Strut 改成剛體平移。
- CornerBrace 仍使用既有固定長度、支撐孔位與圍令交點規則。
- Brace 的 `FromWaler`／`ToWaler` identity 不因本次尺寸調整改選；identity 不完整或歧義時仍阻止正式結果。
- Project row 欄位、persistence schema、Solver input、評分與材料政策不變。
- 既有 preview-first、atomic apply、confirmation invalidation、CandidatePoint rebuild 與 Pause／Resume lifecycle 不變。

## Why

目前 Waler 背填或寬度改變時，一般斜撐只更新連到該 Waler 的單一端點，造成原設計斜撐旋轉並改變長度。工程上斜撐應保持原設計方向與長度，兩端圍令接點則依兩端最終圍令位置共同滑移，因此需要以剛體平移取代單端站距保留。

## What Changes

- 對每支受影響的一般 Brace，使用兩端最終 Waler 有限線段聯立求解共同平移，而非只更新被編輯端。
- 將 Brace baseline 方向與長度列為 Engineering Hard Constraint；調整後兩端差向量必須與 baseline 幾何等價。
- 即使只編輯一端 Waler，也同步更新 Brace 另一端接點及兩端 Waler station。
- 所有重複編輯與 replay 均從保存的 baseline 及目前兩端採用尺寸重算，避免累積誤差與編輯順序差異。
- 將 Brace 人工端點 override 明定為 baseline WCS；在已調整畫面編輯時扣除目前共同平移，並在 baseline 有限 Waler 線段上驗證後才保存。
- 固定 recognition、人工端點 replay、formal baseline 建立、Waler 尺寸 decision 套用的先後順序，防止 adjustment 重複套用。
- 新增無解、非唯一解、有限線段外接點及不相容平行 Waler 的 blocking diagnostics；失敗時維持原子零副作用。
- 更新預覽摘要，使使用者看到兩端接點／站距、共同平移，以及角度與長度保持不變。

### In Scope

- DXF Review 的 Waler 背填／寬度調整對一般 `Brace` 的幾何重算。
- 非平行兩端 Waler 的唯一剛體平移解。
- 平行 Waler 的相容、多解與不相容、無解判定。
- 有限線段、baseline drift、重複編輯、debug replay、CandidatePoint 與 validation rebuild。
- 人工端點在 adjustment 前後的 baseline-WCS 保存、舊 override 相容分類，以及 Pause／Resume／replay 順序無關性。
- 對應 focused tests、workflow regression 與 Domain／Workflow 長期文件更新。

### Out of Scope

- 修改 Waler 位移公式或支撐側判定。
- 修改 Strut 或 CornerBrace 的調整規則。
- 自動改選 Brace 的 `FromWaler`／`ToWaler`。
- 在無剛體解時允許斜撐旋轉、伸縮、脫離圍令、吸附圍令端點或要求 Solver 補償。
- 修改 DXF recognition 的 250 mm direct／600 mm extension 邊界。
- 升級 Project schema 或 DXF Review `review_state_version`、修改 Solver／材料規則，或新增 Resume UI 提示；既有 `manual_overrides` item 可增加 optional coordinate-space 標記以辨識新舊語意。

## Capabilities

### New Capabilities

- `dxf-waler-contact-adjustment`: 定義 Waler 背填／寬度調整時，一般 Brace 必須以兩端 Waler 聯立剛體平移、維持角度與長度，以及無合法解時的原子失敗行為。

### Modified Capabilities

- 無。既有 `brace-axis-waler-extension` 負責 recognition 階段的正式端點與 Waler identity；本 change 在既有正式連接完成後調整幾何，不修改其 direct／extension eligibility 或 ambiguity 規則。

## Impact

- 主要受影響程式：`dxf_import/waler_contact_adjustment.py` 的 Brace planning、preview 與 apply 路徑。
- 可能需最小擴充 `dxf_import/models.py` 的 DXF Review runtime baseline／adjustment metadata，以及在既有 `manual_overrides` item 增加 optional `baseline_wcs` 語意標記；不提升 Review state version，也不新增 Project schema migration。
- `dxf_import/source_exclusion.py` 的 capture／parse／replay 順序需配合 baseline-WCS override，舊未標記 Brace override 在非零 Waler adjustment 下保守進入 `needs_review`。
- 受影響測試以 `tests/test_dxf_waler_contact_adjustment.py` 為主，並擴及 Review replay、source exclusion／restore、Project conversion 與 CandidatePoint regression。
- Architecture 維持現有 DXF Import subsystem 與 Review transaction boundary；不新增跨 layer dependency。
- Domain／Workflow truth 會新增「Waler contact adjustment 中一般 Brace 為剛體、兩端接點聯立」規則；實作驗證通過後應最小更新 `docs/DOMAIN.md` 與 `docs/WORKFLOW.md`。Solver truth 不變。

## 尚未決定事項與重新評估條件

- 沒有未關閉的產品行為問題。平行 Waler 只有在兩端位移約束相容時才可採用共同平移；不相容時必須 blocking。
- 實作可選擇以二維法向聯立方程或「一端最終 Waler 與另一端反向平移 baseline Brace 向量」求交；兩者必須產生相同可觀察結果。若現有 geometry tolerance 無法可靠區分平行／唯一解，應停止實作並回報，不得自行增加未命名數值門檻。
