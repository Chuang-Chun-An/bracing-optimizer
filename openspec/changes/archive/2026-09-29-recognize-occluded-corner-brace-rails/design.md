# Design

## 閱讀導航

### P0｜現在必讀

1. 「方案摘要」：先掌握完整候選、遮蔽 fallback 與 unresolved problem 的分層。
2. 「決策對照」中的 D1～D6：確認正式材料寬度、完整候選全列舉、terminal occlusion hard gates、Review completion 與 selected rail ownership。
3. `specs/dxf-corner-brace-occluded-rail-recognition/spec.md`：正式行為與邊界案例以該 spec 為準。

### P1｜實作前閱讀

- `proposal.md` 的「In Scope／Out of Scope」與「不變事項」。
- `dxf_import/recognition.py` 的 `_corner_brace_candidates_from_group()`、`_corner_brace_center_axis()`、`_refine_corner_brace_axis_intersections()` 與 `_engineering_line_candidates()`。
- `specs/dxf-corner-brace-centerline-extension/spec.md`：selected rail pair 與有限交點校正的責任分界。
- `specs/dxf-corner-brace-repair-tool/spec.md`：automatic unresolved source 與人工 repair 的銜接。

### P2｜需要時再讀

- `docs/ARCHITECTURE.md` 的 DXF Import 與 Review state ownership；本 change 不改變依賴方向。
- `docs/DOMAIN.md`：實作及測試完成後記錄正式 CornerBrace 材料規則。
- `docs/WORKFLOW.md`：只有 unresolved problem 的 Review projection／completion 或 paused-session regression 時需要。
- 可先跳過 Solver、支撐配置與雙路支撐文件；本 change 不修改這些流程。

## 方案摘要

辨識流程維持在 DXF Infrastructure 中，拆成「列舉 hypothesis」與「建立正式 CornerBrace」兩個層次。每個 hypothesis 都先保存實際 selected rails、rail separation、端板證據、遮蔽證據與拒絕理由，再決定是否可成為正式 `_Candidate`。

```text
exact CornerBrace source group
  → 列舉全部完整 rail-pair hypotheses
      → 近似等長完整 topology；或
      → 雙端板 + 四 terminal connections + 唯一 closed traversal 的完整斜切／梯形 topology
  → 套用 rail separation > 250.0 mm
  → 合併幾何等價候選 + 完成既有可分割性判斷
  → 有可正式建立的完整 body 集合：保存 selected rails，不進入 fallback
  → 完整候選 ambiguity：建立 unresolved problem，不進入 fallback
  → 合法完整候選集合為空：列舉 occluded-rail hypotheses
      → 平行／重疊／>250 mm／短長比 ≥75%
      → 至少一端板 + terminal neighborhood 有限幾何遮蔽 evidence
  → Body recognition 成功後列舉 active Waler／Strut 有限關聯
  → 唯一 active relationship：建立正式 connection 並校正 endpoints
  → 零個或多個 active relationships：保留 body evidence，不建立猜測 connection，建立阻止 Review 完成的 problem
```

正式 candidate 保存的 selected rail pair 是後續中心軸、寬度、有限交點校正與 Review 的唯一來源；後續階段不得從 `boundary_lines` 再推選另一組 rails。

## 決策對照

| 決策 | 設計結論 | 對應規格 | 預定任務 |
|---|---|---|---|
| D1 寬度 truth | selected rails 的正交間距是正式材料寬度，必須嚴格 `> 250.0 mm` | occluded-rail「本體 rail 寬度」 | 1.2、1.3、5.3 |
| D2 分層列舉 | 先全列舉近似等長及完整斜切／梯形候選、等價合併及可分割性；只有合法 body 集合為空才啟動 fallback | occluded-rail「完整候選全部列舉」 | 2.1～2.3 |
| D3 遮蔽證據 | 短長比至少 75%，並要求一端板、截短 terminal neighborhood 的有限幾何 corridor 與唯一有限關聯 | occluded-rail「遮蔽 fallback」 | 2.3～2.5 |
| D4 唯一性 | 只合併 source group 內幾何等價 rail／plate hypotheses；active Waler identities 即使幾何重合也不得合併，零解或多關聯都不猜測 | occluded-rail「無唯一合法解」 | 2.1、2.2、2.5、3.2 |
| D5 單一 truth | `_Candidate` 明確保存 selected rails，中心線校正直接使用，不再重新列舉 | occluded-rail「不得建立第二份 truth」、centerline delta | 1.4、3.1 |
| D6 診斷與 Review | 區分 body 已辨識與 relationship unresolved；保留 exact source、selected rails、寬度及原因，其他辨識可繼續，但 problem 阻止 Review 完成 | occluded-rail「無唯一合法解」 | 1.1、3.2、3.3 |
| D7 相容性 | 不新增 Project schema；既有 repair explicit-adoption contract 不變 | repair-tool delta | 4.1、4.2 |
| D8 驗證 | CB58 focused fixture + Y05／Y1A／Y29 regression + module boundary tests | 全部 | 5.1～5.4 |

## Context

現行 `_corner_brace_candidates_from_group()` 將群組內線段兩兩組合，先檢查平行、投影重疊、線間距、細長比與近似等長，再要求兩端都找到連接板。合法選項以長度與端板誤差排序，最後建立 `connection_plate_midpoints` candidate。

這個流程有四個與本次問題直接相關的缺口：

1. 正式 candidate 的 `source_width` 目前取兩端連接板線長平均值，不是 selected rails 的正交間距；因此 CAD 標示 300 mm 時，Review 仍可能顯示約 290 mm。
2. Y05 CB58 的合理 rail pair 真正正交間距約 300.000 mm（generic 有限線段端點平均約 331.86 mm），但其中一側被其他斜撐遮蔽，短長比約 0.7907，且只剩一端板證據；它無法通過「近似等長且雙端板」條件。寬度 155 mm 的內部線組合反而可能符合原條件。
3. `_corner_brace_center_axis()` 會從 `boundary_lines` 重新選最長平行 pair。即使 recognition 選對 rail，calibration 仍可能改選，形成第二份工程 truth。
4. Y29 CB28 是雙端板完整的斜切／梯形 body，兩 selected rail 所在直線的正交間距約 300.000 mm，但原始線長約 1538.473／2138.473 mm。generic `_line_separation` 對有限線段端點取平均會得到約 362.132 mm，舊 generic `closed_outline_axis` 則以約 424.264 mm 端板平均作 `source_width`；兩者皆不是正式正交寬度。若只保留近似等長完整 topology，CB28 又會被誤送至需要 0.75 與遮蔽 evidence 的 fallback。其 center axis 同時命中 W7、W8 兩個 active Waler identities，body 可辨識但 relationship 必須保持 ambiguous。

本 change 必須在不放寬一般構件辨識、不修改 Solver，也不依賴顏色或 draw order 的前提下解決這三項。

## Goals / Non-Goals

### Goals

- 讓 selected rail separation 成為 CornerBrace 的正式材料寬度，並由 automatic recognition 執行嚴格 `> 250.0 mm` hard gate。
- 在 exact source geometry 能提出可稽核遮蔽證據時，辨識 CB58 類「一側 rail 截短、一端板缺失」案例。
- 以完整 rail／plate traversal 辨識 CB28 類雙端板完整斜切／梯形 body，並將 body recognition 與唯一 active member relationship 分層處理。
- 讓辨識、中心線、關聯、diagnostics 與 Review 共用同一 selected rail truth。
- 在無解或多解時提供可追溯、阻止 Review 完成的 problem，而不是產生猜測構件。

### Non-Goals

- 不調整一般 Brace、Strut、Waler、Column、Beam 或 Solver 規則。
- 不把「寬度大於 250 mm」單獨當成遮蔽候選成立條件。
- 不使用影像辨識、顏色、圖層 draw order 或人工選取來完成 automatic adoption。
- 不新增 repair UI、不自動採用 repair candidate，也不改變 Project row schema。
- 不新增 geometry-equivalent Waler relationship group、canonical Waler ID，且不由 CornerBrace recognizer 修改或合併 Waler source identity。

## Decisions

### D1：以 selected rail separation 作為寬度的唯一來源

新增具名材料 threshold `minimum_corner_brace_rail_separation_mm = 250.0`，語意為「正式 CornerBrace 的 rail separation 必須嚴格大於此值」。此值是已確認的正式材料／工程規則，目前由 DXF automatic recognition 執行；不是搜尋 heuristic、Solver Preference、Solver scoring 或搜尋參數。實作應放在 DXF recognition 可取用的具名設定責任中，不在 UI 或 Solver 重複定義；行為完成後更新 `docs/DOMAIN.md`。

每個 rail-pair hypothesis 在任何排序前先以 CornerBrace 專用量測計算兩條 selected rail 所在無限直線的對稱正交距離。不得使用 generic `_line_separation(first, second)` 的有限線段端點平均，因為斜切 rail 的有限長度不同時，端部 overhang 會把 CB28 的真正 `300.000 mm` 正交間距誤算為約 `362.132 mm`：

- `separation <= 250.0`：直接拒絕，保留 `rail_separation_not_above_minimum` 診斷。
- `separation > 250.0`：才可繼續 topology 或遮蔽檢核。
- 正式 candidate 的 `source_width` 改存該 separation；端板長度可留在 internal evidence／debug，但不得再當本體寬度。

這是既有欄位語意修正，不新增 Project persistence 欄位。因 CornerBrace 不輸出 Solver project row，修改限於 DXF Review model 與辨識診斷；需以 regression 鎖定 UI 顯示與 material recognition 沒有被意外套用到 CornerBrace。

### D2：完整候選與遮蔽 fallback 使用兩階段 pipeline

`_corner_brace_candidates_from_group()` 內部先建立輕量、不可直接輸出的 rail hypothesis 結構，至少包含：

- rail indices 與 ordered finite segments；
- separation、長度比、projection overlap；
- 已匹配的 start／end plate 與誤差；
- occlusion evidence 與拒絕 reason codes；
- 從 selected rails 推導的 center axis；
- 候選 Waler／Strut 有限交點與唯一性結果。

第一階段列舉兩類完整 topology。一般完整 body 沿用近似等長、兩端板為不同線段、最小構件長度、平行與重疊等規則。完整斜切／梯形 body 允許兩 rail 原始有限線長不同，但必須同時具備：兩條合法平行 rails、rail separation 嚴格大於 250.0 mm、兩條不同有限端板、四個實際 rail-to-plate terminal connections，以及由這四條 evidence 形成唯一且完整的 rail／plate closed traversal。端板平均長度不得成為 width truth；0.75 短長比只屬 D3 遮蔽 fallback，不套用於雙端板完整 body。

系統必須列舉全部完整 hypotheses，再合併因方向、端點順序或重複 primitive 造成的幾何等價項，最後執行既有可分割性判斷。不共用 rails／plates 且安全可分割者可建立多個 CornerBrace body；競爭相同 evidence 或無法形成唯一可分割集合者是 ambiguity，不得用 first valid match、first occurrence、handle／entity order、排序或分數選定。完整斜切規則不得退回 generic `closed_outline_axis`，也不得只因看到任意封閉梯形就成立。

完成上述全部程序後，只要仍有一個或多個可正式建立的完整 CornerBrace，就不執行遮蔽 fallback。完整候選 ambiguity 也不得轉入 fallback，而是 unresolved。第二階段只在合法完整候選集合確實為空時列舉遮蔽 hypotheses；它不是對原條件逐項 `or` 放寬，而是一條獨立、證據更多的保守路徑。

### D3：遮蔽 fallback 需要聯合 hard gates

遮蔽 hypothesis 必須全部符合：

1. 既有 `parallel_angle_tolerance_deg` 與 `minimum_projection_overlap_ratio`。
2. D1 的 rail separation 嚴格大於 250 mm，且不超過既有 `maximum_component_width_mm`。
3. `min(rail lengths) / max(rail lengths) >= 0.75`。75% 是本 change 的具名下限；CB58 約 79.07%，保留有限裕度但不接受嚴重殘線。
4. 至少一端能以既有 `endpoint_tolerance_mm` 配對連接板。
5. 其他已辨識 brace 或同一 exact source group 的有限幾何，必須在具名幾何容差內實際相交、接觸或通過截短 rail 的 terminal neighborhood，且該位置可直接解釋 rail 為何在此中斷。只因同 root／block、空間鄰近、投影部分重疊、無限延長後可能相交，或只在 rail 內部其他位置相交，均不成立。Corridor 比較重用 `GeometryTolerances` 中既有 endpoint／connection／collinear tolerances；若實作需要新 tolerance，必須停止並回報，不可自行新增或在條件式寫裸數字。
6. selected rail center axis 對應到唯一 Waler 有限內線與唯一 Strut 有限中心線，且兩個交點都位於各自有限工程線容差範圍內。

Occlusion evidence 表示「截短 terminal 可由實際有限來源幾何直接解釋」，不是同 group membership 或圖元視覺前後順序。實作不得使用無限延長幾何、entity order、顏色或圖層繪製順序。

### D4：先做幾何等價合併，再要求唯一解

同一 rail pair 可能因方向相反、端點次序或重複 primitive 產生等價 hypotheses。Body 唯一性判定前，應以 ordered rail geometry、既有 collinear／endpoint tolerances、center axis 與 rail／plate traversal 建立 deterministic equivalence key 並合併。此等價合併只處理 exact CornerBrace source group 內重複的 rail／plate evidence；不得跨 active Waler sources 合併 relationship identity。

結果處理如下：

- 全部完整 hypotheses 完成等價合併與既有可分割性判斷後：一個合法候選建立一個 CornerBrace；多個不共用 rail／plate 且安全可分割候選建立多個 CornerBrace。
- 完整 candidates 若競爭相同 evidence 或無法形成唯一可分割集合，視為 ambiguity，不以分數猜測，也不得啟動遮蔽 fallback。
- fallback 恰一個非等價合法候選：採用 `occluded_parallel_rails`。
- fallback 零個或多個非等價合法候選：不建立正式 CornerBrace，建立 completion-blocking unresolved problem。

排序只用於 deterministic presentation，不得用來提前停止列舉或把 ambiguity 變成唯一解；禁止 first valid match、first occurrence、handle／entity order、score 或最近距離決勝。

Body recognition 完成後，每個仍 active 的 Waler／Strut source/member 都是獨立 relationship evidence。即使 W7、W8 的有限工程線在幾何上重合，只要兩者仍 active，就構成兩個有效 Waler relationships；不得建立 geometry-equivalent relationship group、canonical Waler ID，或以重合、handle、member ID、entity order、first match、nearest distance 選擇其中一個。只有來源排除後依目前 active facts 完整重跑 recognition，且剩下唯一 relationship 時，才可完成 connection 與 endpoint calibration。

### D5：selected rails 必須隨 candidate 傳遞

在 internal `_Candidate` 增加明確的 `selected_rail_lines`（恰為兩條 ordered finite segments）與可選 recognition evidence；完整與遮蔽流程建立正式 candidate 時都填入。`boundary_lines` 仍保留全部來源邊界供既有 Review 顯示，不再承擔「哪兩條是正式 rails」的隱含責任。

`_corner_brace_center_axis()` 改為只由 `selected_rail_lines` 計算中線。對歷史上沒有此欄位的非本 change candidate，可保留受測試保護的 legacy fallback；新建立的完整或遮蔽 CornerBrace 不得進入重新列舉路徑。

投影成公開 `CornerBrace` 時：

- `recognition_method` 分別維持既有方法或使用穩定新值 `occluded_parallel_rails`；
- `source_width` 使用 selected rail separation；
- `_engineering_line_candidates()` 將兩條 selected rails 標記為穩定 source（例如 `recognized_corner_brace_rail`），其餘 boundary 維持一般 evidence；
- final axis、connection、candidate points 與 Review 顯示共用相同 `_Candidate` 結果。

此做法只擴充 DXF runtime／Review evidence，不修改 Solver-facing project schema。

### D6：無唯一解建立可定位且阻止 Review 完成的 problem

採用穩定 code `CORNER_BRACE_RAIL_CANDIDATE_UNRESOLVED`。對 body 零解、完整候選 ambiguity、多個非等價 fallback，或 body 已成功但 Waler／Strut relationship 零解／多解，建立可由 Review 定位的 unresolved problem，並包含：

- exact source handle(s)；
- 已評估的 rail separation；
- 主要拒絕 reason codes，例如寬度不足、短長比不足、端板不足、遮蔽證據不足、有限交點無解或 ambiguity；
- 多解時的非等價候選數量與可區分摘要。
- body status、selected rails、rail separation，以及 competing active Waler／Strut source identities；diagnostics 必須能區分「body geometry 已辨識」與「正式工程關聯無法唯一決定」。

來源不因 problem 被刪除：exact source geometry／debug identity 與已成立的 body evidence 仍可由 Review 定位。Relationship ambiguity 不得建立猜測的正式 CornerBrace connection；operation level 允許其他來源繼續辨識、顯示與檢核，completion level 必須在該 source 未被排除、修正或以既有合法流程解決前阻止 DXF Review 完成。排除 W7 或 W8 後必須依目前 active sources 完整重跑，不得保存或重播排除前的暫時選擇或 ambiguity outcome。若底層仍以 `ValidationMessage(severity="warning")` 承載 operation-level 診斷，Review workflow 仍必須以 unresolved problem／既有 completion eligibility 表達 completion blocking；若現有 framework 無法做到，實作必須停止並回報，不得自行改寫 completion framework。

### D7：repair 與 persistence 維持相容

Automatic occluded recognition 成功時，既有 repair 流程不參與，也不得重選 rail 或 relationship。Automatic 無解或多解時，unresolved source 只有在本來就通過 repair eligibility 時才能出現 repair preview；problem／warning 本身不是 eligibility 證據。只有合法排除、合法 repair adoption 或其他既有合法 resolution 才能解除 completion block。

不新增 Project schema 或 migration。現有 DXF Review session 若持久化的 model 缺少新 internal evidence，讀取仍使用既有預設值；重新執行 recognition 時才依新規則重建。若既有序列化明確保存 `line_candidates`，新增的 source 字串必須保持向後相容。

### D8：測試以行為邊界與真實 regression 雙軌驗證

單元／合成幾何至少覆蓋：

- 250.0 mm 被拒絕、略大於 250.0 mm 可繼續、155 mm 被拒絕；
- 全部完整 candidates 都被列舉，等價合併與可分割性完成後，有可建立集合時不啟動 fallback，完整 ambiguity 也不轉入 fallback；
- 75% 等號可接受、低於 75% 拒絕；
- 單端板 + 有限幾何實際通過 terminal neighborhood 可成立；同 root 但只在附近、只有無限延長相交、或只在 rail 其他位置相交均拒絕；
- 零解／完整 ambiguity／fallback 多解皆建立 completion-blocking problem，不使用 first-match；
- calibration 使用 selected rails，不從 boundary 重選；
- unresolved source 可在 Review 定位、不阻擋其他構件繼續辨識與檢核，但阻止 Review 完成。
- 完整斜切／梯形 body 以雙端板、四 terminal connections 及唯一 closed traversal 成立，`source_width` 使用 rail separation；任意封閉梯形或 generic `closed_outline_axis` 不得繞過此 topology。
- W7／W8 幾何重合且同時 active 時，CB28 body 正交寬度約 300.000 mm 可辨識但 relationship unresolved；交換輸入順序結果相同。分別排除 W7 或 W8 並重跑後，剩餘唯一 Waler 可完成 connection；單一 Waler fixture 直接成功。

真實 regression 至少鎖定：

- Y05 CB58 選到 P20–P27 對應的外側 rail 組合，不再選 155 mm 內部 pair；selected rail supporting lines 的真正正交 separation 約 300.000 mm，不採用約 331.86 mm 的有限線段端點平均，中心線能建立合法有限關聯。
- Y05 正常角撐與 Y1A 約 300 mm 角撐維持既有數量、身份與工程端點；Y29 CB28 body identity 與約 300.000 mm 正交寬度可定位，且不採用約 362.132 mm 的有限線段端點平均，W7／W8 同時 active 時 connection 明確 unresolved，排除任一重複來源後重跑可連至剩餘唯一 Waler。
- Review 所見 `source_width` 為 rail separation，不再是約 290 mm 的端板平均。

## Architecture Alignment

本 change 符合既有依賴方向：

```text
DXF exact source geometry
  → dxf_import recognition / geometry helpers
  → recognized models + ValidationMessage
  → review workflow projection
  → presentation rendering
```

- 幾何 hard gates 與 evidence 建立留在 `dxf_import/recognition.py` 或同層小型 recognition helper。
- `models.py` 只承載穩定資料，不實作選擇演算法。
- Review workflow 投影 unresolved problem／source identity 並執行 completion eligibility；Presentation 只顯示結果。
- Domain code、Algorithms、Application Solver 與 Project schema 不新增依賴，也不在 Solver 複製 250 mm 規則；`docs/DOMAIN.md` 會新增此正式材料／工程規則的長期文件 truth。

如果實作使 `_corner_brace_candidates_from_group()` 過大，可抽出單一責任的 private geometry／hypothesis helper，但不得為此重構其他 member recognizers。

## Risks / Trade-offs

### 遮蔽 evidence 過寬造成誤認

只用 rail 寬度與長度比會讓一般殘線也可能成立。因而 D3 把至少一端板、terminal neighborhood 的實際有限幾何遮蔽、唯一有限 Waler／Strut 關聯全部設為 hard gates；任一缺失即 unresolved completion block。

### 250 mm 可能排除其他合法材料

本次需求明確指定「大於 250 mm」，因此採 strict hard gate，不做可由 UI 調整的 preference。若未來需支援 250 mm 或更窄材料，必須另行修改 capability／材料規則，不可暗中放寬。

### `source_width` 語意修正影響既有顯示

修正後 Y05 某些角撐會從約 290 mm 改顯示約 300 mm。這是預期行為，但需要檢查任何依賴 `source_width` 的自動材料辨識或 UI 文案，確保 CornerBrace 不因欄位修正意外進入非預期流程。

### 同一 block 可包含多個 CornerBrace

不能把「同群組多候選」一律當 ambiguity。完整候選仍需允許由不共用 rails／plates 的可分割集合建立多個實體；只有競爭相同 evidence 或 fallback 出現非等價多解時才 unresolved。

### Body 成功但 member relationship 多解

不能以 body geometry 已唯一辨識推論 connection 也唯一。active Waler source identity 是工程關聯的一部分；W7、W8 即使有限線重合仍須保留為兩個 relationships。代價是 CB28 在重複來源未排除前保持 completion-blocking，但避免 CornerBrace recognizer 暗中改變 Waler ownership。

### 真實 CAD 浮點誤差

所有幾何比較重用具名 tolerance，只有材料寬度使用需求指定的 strict `> 250.0`。測試同時包含精確邊界與接近實圖的小數值，避免把顯示四捨五入與工程判斷混為一談。

## Migration and Rollback

1. 先確認既有 Review completion eligibility 能承載 unresolved source；若需要改變 completion framework，停止並回報。
2. 加入具名材料 threshold、hypothesis evidence 與 selected rail ownership，不改 UI。
3. 將一般完整與完整斜切／梯形候選接到全列舉、等價合併、可分割性與新 width truth，先驗證 CB28 body evidence，再獨立驗證 active Waler relationship ambiguity。
4. 加入 terminal-neighborhood 遮蔽 fallback 與 completion-blocking problem projection，再啟用 `occluded_parallel_rails`。
5. 最後移除新候選對 `_corner_brace_center_axis()` re-enumeration 的依賴，驗證 connections／candidate points、排除 W7／W8 後完整重跑不重播舊選擇，並在行為測試通過後更新 `docs/DOMAIN.md`。

若真實 regression 出現無法區分的誤認，rollback 應只停用遮蔽 fallback，保留 D1 正式材料 hard gate、correct `source_width` 與 unresolved evidence；不得退回 first-match 或 155 mm 窄線候選。

## Open Questions

本提案階段沒有會改變既定行為的未決規格。短 rail 比例已定為 75%；遮蔽 corridor 必須使用現有具名 `GeometryTolerances` 判斷有限幾何是否實際通過 terminal neighborhood。若實作需要新增未定義 tolerance、改變 Review completion framework、修改 Project schema，或現有資料無法建立可靠遮蔽證據，必須停止並回報，不得自行加入 magic number 或放寬規則。
