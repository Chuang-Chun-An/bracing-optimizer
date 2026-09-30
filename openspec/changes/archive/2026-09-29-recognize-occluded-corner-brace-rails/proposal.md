# Proposal

## 閱讀導航

### P0｜現在必讀

1. 本文件「快速摘要」、「現況與目標」與「主要流程」：先確認要解決的辨識問題與不變邊界。
2. `specs/dxf-corner-brace-occluded-rail-recognition/spec.md`：確認正式材料寬度、完整候選列舉、遮蔽候選與 unresolved completion gate。
3. `design.md` 的「Decisions」：實作前確認完整候選與遮蔽 fallback 的分層方式。

### P1｜實作前閱讀

- `openspec/specs/dxf-corner-brace-centerline-extension/spec.md` 的「可靠角撐中心軸的端點校正」與「端點校正只使用唯一且有效的工程關聯」。
- `openspec/specs/dxf-corner-brace-repair-tool/spec.md` 的「自動辨識與非目標系統維持既有行為」。
- `dxf_import/recognition.py` 的 `_corner_brace_candidates_from_group()`、`_corner_brace_center_axis()` 與 `_refine_corner_brace_axis_intersections()`。
- `tests/test_dxf_input.py`、`tests/test_dxf_corner_brace_repair.py` 及 Y05／Y1A／Y29 角撐 regression。

### P2｜需要時再讀

- `docs/ARCHITECTURE.md` 的 DXF 子系統責任與 state ownership；本 change 不改變該架構。
- `docs/DOMAIN.md` 的工程規則分類；本 change 完成後須記錄已確認的 CornerBrace 材料規則。
- `docs/WORKFLOW.md` 的 DXF Review lifecycle；只有在 unresolved problem／Review completion projection 需要釐清時再讀。
- 可先跳過 Solver、支撐最佳化、雙路支撐及 Waler Solver specs；它們不在本次範圍。

## 快速摘要

- 現行 CornerBrace automatic recognition 只接受長度近似且兩端板完整的雙 rail；Y05 CB58 因一側 rail 被斜撐遮蔽而截短，反而選到寬度 155 mm 的錯誤內部線組合。
- 本 change 將 CornerBrace 本體 rail 的正交間距定義為正式材料寬度，正式 CornerBrace 必須嚴格大於 250.0 mm；250.0 mm 等號不合格，且不得使用兩端板平均長度代替本體寬度。此規則是正式材料／工程規則，不是 DXF 搜尋 heuristic 或 Solver Preference。
- 系統必須先完成全部完整 hypotheses 的列舉、幾何等價合併及既有可分割性判斷；只有所得合法完整候選集合為空時，才嘗試受限制的「遮蔽 rail」fallback。
- 完整候選除近似等長矩形本體外，也包含 CB28 類完整斜切／梯形本體：兩條合法平行 rails、兩條不同有限端板、四個實際 rail-to-plate terminal connections，以及唯一完整的 rail／plate closed traversal。此類候選不是遮蔽 fallback，不套用 0.75 短長比。
- 遮蔽 fallback 允許一側截短或一端板缺失，但仍要求材料寬度、至少一端板、截短 terminal neighborhood 的有限幾何遮蔽證據、唯一幾何關聯及有限交點全部成立。
- Body geometry 辨識成功不等於工程關聯已完成；若 center axis 同時對應兩個 active Waler sources，即使兩條有限工程線幾何重合，仍屬 relationship ambiguity，必須保留 body evidence 並阻止 Review 完成，不得自動合併或選 canonical Waler。
- 找不到唯一合法解時，不建立猜測的正式 CornerBrace；系統保留來源並建立可定位 problem。其他來源仍可繼續辨識與檢核，但該來源未被排除、修正或以既有合法流程解決前，DXF Review 不得完成。
- 一般 Brace／Strut／Waler、Solver、Project schema 與既有人工 reference-template repair contract 不變。

## 現況與目標

「Rail」指角撐本體沿長向的邊線；「遮蔽 rail」指因其他斜撐或圖塊幾何覆蓋而只保留部分有限線段的本體邊線。

| | Before | After |
|---|---|---|
| 本體寬度 | `source_width` 對連接板型候選保存兩端板長度平均，可能顯示約 290 mm，並非兩 rail 間距 | 以兩 rail 的正交間距作為候選本體寬度；Y05 正常 H300 類約為 300.16 mm |
| 完整候選 | 通用流程可能依封閉外框建立中心軸並把端板平均當寬度；專用流程只接受近似等長雙 rail／雙端板 | 列舉近似等長與完整斜切／梯形 hypotheses；後者須有雙 rail、雙端板、四個 terminal connections 與唯一 closed traversal，再套用 `> 250.0 mm` hard gate、幾何等價合併及可分割性判斷 |
| 被遮蔽案例 | 截短 rail 無法通過長度一致與雙端板條件，可能由 155 mm 內部線組合勝出 | 合法完整候選集合為空時，以具名保守條件評估遮蔽 rail pair；只有唯一合法解才可進入正式 automatic 流程 |
| 關聯多解 | 通用流程可能依 first／nearest 結果吸附構件 | Body 可先辨識成功；若對應多個 active Waler sources，保留 selected rails／寬度與 ambiguity diagnostics，不建立猜測 connection，並阻止 Review 完成 |
| 無合適解 | 可能保留不符合材料尺度的形式候選，或只留下不易追查的結果 | 不猜測正式角撐；保留 exact source identity／geometry、寬度與原因，建立阻止 Review 完成的可定位 problem |

## 主要流程

```text
展開 CornerBrace exact source geometry
  → 列舉全部完整雙 rail／雙端板 hypotheses
      → 近似等長完整本體；或
      → 雙端板、四 terminal connections、唯一 closed traversal 的完整斜切／梯形本體
  → 套用 rail 間距 > 250.0 mm 的正式材料 hard gate
  → 合併幾何等價候選並完成既有可分割性判斷
  → 若合法完整候選集合為空，建立遮蔽 rail hypotheses
  → 遮蔽候選驗證截短比例、重疊、至少一端板及 terminal neighborhood 有限幾何遮蔽證據
  → Body recognition 成功後，列舉 active Waler／Strut 有限關聯
  → 唯一合法關聯：建立 automatic CornerBrace connection 並沿用中心軸端點校正
  → 關聯無解或多解：保留 body evidence，不建立猜測 connection，建立阻止 Review 完成的 problem
```

## 不變事項

- 不修改一般 `brace`、`strut`、`waler`、Column 或 Beam 的辨識規則。
- 不修改 CornerBrace 最終端點必須位於有限 Waler 內線與有限 Strut 中心線的既有硬條件。
- 不以距離最近、排序、分數、handle ordering、entity order 或 first-match 解決完整或遮蔽候選 ambiguity。
- 不因兩個 active Waler sources 的有限工程線幾何重合，就合併 relationship identity、建立 canonical Waler ID 或由 CornerBrace recognizer 自行選擇其一。
- 不修改 Solver、Solver scoring／搜尋參數、Project schema、其他 member 材料規則、DXF source entity 或原始圖檔。
- 不取代既有 reference-template repair；仍無法 automatic 唯一辨識的來源可由既有 Review／repair 流程處理。

## Why

Y05 CB58 的一側本體 rail 因斜撐遮蔽而較短，現行「雙 rail 近似等長且兩端板完整」規則無法採用真正正交間距約 300.000 mm 的合理組合，卻可能選到寬度 155 mm 的內部線；generic 有限線段端點平均在此會得到約 331.86 mm，並非正式寬度。另一方面，Y29 CB28 是雙端板完整的斜切／梯形角撐：兩條 selected rail 所在直線的正式正交間距約 300.000 mm，但兩 rail 原始長度不同；既有 generic `_line_separation` 對有限線段端點取平均會得到約 362.132 mm，舊 generic `closed_outline_axis` 又會把約 424.264 mm 的端板平均誤作本體寬度，兩者皆不是正式寬度。系統需要同時保守恢復有證據的遮蔽 rail 與完整斜切 body，並將 body recognition 與唯一 Waler／Strut relationship 分開診斷；若仍無唯一關聯，必須保留 body evidence、阻止 Review 完成，而非猜測。

## What Changes

- 將 CornerBrace rail pair 的正交間距定義為本體寬度，並將嚴格 `> 250.0 mm` 確立為正式材料／工程規則；實作完成後同步更新 `docs/DOMAIN.md`。
- 完整流程必須列舉全部雙 rail／雙端板 hypotheses，完成 hard gates、幾何等價合併及既有可分割性判斷；只要仍有一個或多個可正式建立的完整 CornerBrace，該 group 就不得進入遮蔽 fallback。
- 完整斜切／梯形 body 以雙 rail、雙端板、四個實際 terminal connections 與唯一 closed traversal 成立；它不因 rail 原始長度不同而進入遮蔽 fallback，且 `source_width` 仍使用 rail separation。
- 遮蔽 fallback 允許一側 rail 截短及一端板缺失，但必須有具名長度／重疊門檻、至少一端板，以及其他已辨識斜撐或同一 exact source group 的有限幾何在具名容差內實際相交、接觸或通過截短 rail 的 terminal neighborhood，並具有唯一有效的有限 Waler／Strut 交點。
- 唯一合法遮蔽候選可沿用既有 CornerBrace 中心軸端點校正；多解、證據不足或所有候選失敗時不得建立正式 CornerBrace。
- Body recognition 後必須以 active source facts 列舉 Waler／Strut relationships；幾何重合但 identity 不同的 active Waler sources 仍是多個關聯，不得合併或自動選 canonical ID。排除其中一個來源後必須完整重新辨識，且不得重播先前暫時選擇。
- 新增可追溯 unresolved problem，至少包含 exact source identity、來源幾何、已評估寬度與拒絕原因；它不阻止其他構件繼續辨識與檢核，但在來源未合法解決前必須阻止 DXF Review 完成。
- 釐清既有 `source_width` 對連接板型 CornerBrace 的語意，不再把端板平均長度當成 rail 本體寬度供本規則判斷。

## In Scope

- CornerBrace automatic candidate enumeration、正式材料寬度 gate、完整斜切／梯形 body topology、完整候選等價合併／可分割性、遮蔽 rail fallback、唯一 relationship 與 unresolved completion gate。
- 新 recognition method／provenance 所需的 DXF model、debug／Review projection 與 candidate point 支援。
- 遮蔽候選進入既有中心軸有限交點校正及 CornerBraceConnection 重建。
- Y05 CB58 focused regression，以及 Y05、Y1A、Y29 CB28 body／W7-W8 relationship ambiguity／來源排除後重辨識 regression。

## Out of Scope

- 放寬一般 Brace、Strut、Waler 或 BIM member recognition。
- 新增 geometry-equivalent Waler relationship group、canonical Waler ID，或修改 Waler source/member identity contract。
- 以影像、顏色、draw order 或人工標註推斷遮蔽。
- 改寫 reference-template repair、建立新的修補 UI，或自動 Apply 人工候選。
- 修改 Solver、Project schema、材料庫格式或原始 DXF。
- 順帶修正其他 CornerBrace source-width technical debt；僅處理本次候選寬度 contract 所需範圍。

## Capabilities

### New Capabilities

- `dxf-corner-brace-occluded-rail-recognition`: 定義嚴格大於 250.0 mm 的正式 CornerBrace 材料規則、完整候選全列舉與可分割性、受遮蔽 rail fallback、唯一解成立條件及 unresolved Review completion gate。

### Modified Capabilities

- `dxf-corner-brace-centerline-extension`: 讓通過遮蔽 rail hard gates 的可靠中心軸沿用既有有限 Waler／Strut 端點校正，並釐清 candidate enumeration 與 calibration 的責任邊界。
- `dxf-corner-brace-repair-tool`: 釐清新增 automatic 遮蔽辨識後，unresolved source 仍須獨立通過既有 repair eligibility 才可提供人工 preview；problem／warning 本身不是 eligibility evidence，explicit adoption 與 safety contract 不變。

## Impact

- `dxf_import/recognition.py`：完整 rail candidate、遮蔽 fallback、寬度語意、中心軸 refinement 與 diagnostics。
- `dxf_import/models.py`／validation／Review projection：如既有欄位足以承載則沿用；若實作發現必須改變 Review completion framework，應停止並回報，不得自行擴張 scope。
- `tests/test_dxf_input.py` 及相關 DXF regression：新增 CB58 terminal occlusion、CB28 完整斜切 body、W7/W8 同時 active 的 relationship ambiguity、排除任一重複 Waler 後重辨識、同 root 鄰近線反例、窄線排除及無解／多解 completion-blocking problem。
- `docs/DOMAIN.md`：在實作及測試完成後，記錄本體寬度由 selected rail separation 決定、正式 CornerBrace 必須嚴格 `> 250.0 mm`、端板長度不得代替本體寬度，並明訂其不是 Solver scoring 或搜尋參數。
- Architecture、Solver、其他 member 材料規則與 Project persistence truth 不變；Domain truth 會新增上述已確認的 CornerBrace 正式材料規則。

## 已決定事項與停止條件

- 遮蔽 rail 的最小短長比固定為 `0.75`；遮蔽證據必須由有限來源幾何在具名容差內實際相交、接觸或通過截短 rail 的 terminal neighborhood。若需要新增未定義 tolerance，必須停止並回報，不得自行加入 magic number。
- 完整斜切／梯形 body 不套用遮蔽短長比；它必須以兩條不同有限端板、四個 terminal connections 與唯一 closed traversal 證明完整性。active Waler identity 不得因幾何重合而合併。
- 若現有資料無法建立可靠遮蔽證據，automatic adoption 必須維持 unresolved completion-blocking problem，不得僅靠同 root、寬度、空間接近、投影重疊或無限延長交點成立。
- 若必須改變 Review completion framework、Project schema 或已確認 repair safety contract 才能實作，必須停止並回報，不得自行擴張本 change。
