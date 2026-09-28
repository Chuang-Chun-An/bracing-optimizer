# Tasks

## 1. HATCH 與 Y05 Characterization

- [x] 1.1 在 `tests/test_dxf_hatch_waler_recognition.py` 建立最小 synthetic DXF fixture corpus，涵蓋 patterned／solid HATCH、line-edge `EdgePath`、無 bulge `PolylinePath`、800 mm 直線長條、孔洞、L 形、multi-exterior、相接的水平／垂直 HATCH 與等價外框 LINE；以 fixture 自我檢查確認每個來源的 handle、path topology 與預期 WCS boundary 可重現。
- [x] 1.2 以唯讀 diagnostic test 固定 Y05 `1647`／`1650`、`E65`／`163D` 的實際來源特性（Waler layer、非 associative、單一封閉 line-edge path、約 800 mm 寬及水平／垂直完整 extent），並記錄目前 `待修-1648`／對應 L 形 failure 作為 regression baseline；執行該 focused test 確認 fixture 與實檔假設一致。

## 2. Pure HATCH Waler Recognition

- [x] 2.1 新增 `dxf_import/hatch_waler_recognition.py` 的 immutable WCS boundary DTO、recognized／failed／ambiguous outcome 與 canonical geometry normalization；不得依賴 ezdxf、Presentation、Project 或 Solver，並以 unit tests 驗證 boundary 起點、traversal direction、edge order 與 axis start/end 反轉不改變 outcome。
- [x] 2.2 實作唯一 exterior、closure／continuity、單一主要方向、完整縱向 extent、slenderness、width 及 longitudinal-boundary 推導；明確略過不影響 exterior 的內部 hole，拒絕 L 形、multi-exterior、自交與多個不等價完整軸，並以 focused unit tests 驗證同一 HATCH 只會得到一支 formal axis 或一個 terminal problem。
- [x] 2.3 將 pure service 的所有幾何判斷對應至 Design 表列的 `GeometryTolerances` named settings，確認 HATCH RC route 不使用 `maximum_component_width_mm` 且 production code 沒有新增無命名 heuristic number；執行 800 mm 及一般寬度 boundary tests。

## 3. Importer HATCH Boundary 與 WCS Adapter

- [x] 3.1 在 `dxf_import/importer.py`（或同責任的小型 adapter module）讀取 Waler-role HATCH 的 line-edge `EdgePath` 與無 bulge closed `PolylinePath`，正確套用 OCS、elevation 與既有 transform 至 WCS DTO；對 arc／ellipse／spline／bulge／invalid path 回傳具名 failure，不修改原始 DXF，並以 OCS／旋轉 synthetic tests 驗證座標。
- [x] 3.2 讓每個頂層 Waler HATCH 以自己的 handle 進入 pure service，建立 `EntityDebugInfo`、HATCH boundary `SourceGeometry` 與帶 source handle 的 validation message；確認其他 role／ignored layer 的 HATCH 不進入 RC Waler route，並執行 importer focused tests。
- [x] 3.3 將 recognized outcome 轉成既有 Waler candidate contract，保留完整 `recognized_axis`、實際 `source_width`、兩條 longitudinal boundaries、HATCH provenance 與 RC material hint，再沿用 `_select_waler_inner_lines()`；以水平、垂直、旋轉及接觸側 evidence tests 驗證正式線仍是既有 inner-contact face。

## 4. Boundary Evidence Claim 與一般辨識隔離

- [x] 4.1 在 Waler importer route 於一般 group merge 前建立可重建的 HATCH boundary-evidence claim，只 claim 全部 segments 在既有 angle、collinearity、projection coverage 與 endpoint tolerances 下落於 HATCH exterior 的 LINE／POLYLINE；以 tests 證明單純相交、靠近、部分局部平行或無關 Steel Waler 不會被 claim。
- [x] 4.2 讓 recognized、failed、ambiguous 及 explicitly excluded HATCH 都先重建其可證明的 boundary claims，被 claim 的外框不再進入 `_merge_related_line_groups()`，但仍保留 immutable preview／diagnostic geometry；以 exclusion regression 證明排除 HATCH 後外框 LINE 不會換 identity 重新出現。
- [x] 4.3 驗證兩個相接的水平／垂直 HATCH 維持兩個 source units、不形成 L 形 group；另驗證沒有相關 HATCH 的 LINE／POLYLINE／MLINE Waler 完整沿用既有 recognition behavior。

## 5. RC Material Precedence 與 Project Contract

- [x] 5.1 在 internal candidate-to-Waler mapping 採用 `material_spec = RC` 與 `material_spec_source = auto_hatch`，並調整 `dxf_import/material_recognition.py` 只對非 auto-hatch member 套用既有 width mapping；以測試確認即使 800 mm 或其他寬度匹配鋼材規格也不覆寫 RC。
- [x] 5.2 驗證 STEP4 `set_member_material_spec()`、manual override replay 與 confirmation invalidation 維持既有行為，rebuild 時先重建 auto-hatch base 再按 exact source identity replay；執行 material／review focused tests。
- [x] 5.3 驗證 completed import 的 Waler Project row 僅透過既有 `material_spec` 欄位帶入 `RC`，不新增 `DXFImportResult`／Project payload schema 欄位，並以 save/load／Project conversion regression 確認相容。

## 6. Review、Source Exclusion 與 Failure Semantics

- [x] 6.1 為 invalid boundary、unsupported nonlinear boundary、ambiguous exterior／axis 與 engineering-line failure 建立穩定的 Waler validation codes；驗證每個 failure 形成包含 HATCH handle、layer、entity type 與可理解原因的 unresolved ReviewItem，且不 fallback 至等價 LINE 建立非 RC formal Waler。
- [x] 6.2 驗證 HATCH recognized／unresolved source 可沿用既有 Source Exclusion／Restore、Review confirmation、pause／resume、fingerprint safety 與 staged mutation；排除／失敗不得修改正式 Project 或 committed Solver result，復原後以原 HATCH identity 重建。
- [x] 6.3 驗證 duplicate-equivalent HATCH 的結果 deterministic 且保留完整 provenance，並補齊 HATCH entity order、boundary start、traversal direction、LINE start/end 及等價外框 entity order permutation tests。

## 7. Y05 與完整 Regression

- [x] 7.1 執行 Y05 regression，確認 `1647`／`1650` 分別建立完整水平與垂直 RC Waler、`E65`／`163D` 同樣分開辨識，且不再出現由其等價外框 LINE 形成的 `待修-1648`／對應 L 形 unresolved item；同時確認 Y05 其他一般 Waler 沒有非預期變更。
- [x] 7.2 執行最接近範圍的測試：`tests/test_dxf_hatch_waler_recognition.py`、`tests/test_dxf_input.py`、`tests/test_dxf_material_recognition.py`、`tests/test_dxf_review_items.py`、`tests/test_dxf_source_exclusion.py`、`tests/test_dxf_review_workflow.py`、`tests/test_dxf_ocs_wcs.py` 與 Waler contact tests，修正本 change 造成的 regression，不弱化既有 assertions。
- [x] 7.3 執行完整 regression suite 與 architecture boundary tests，確認一般 Steel Waler、BIM Strut／Brace、CandidatePoint、Waler contact、Project persistence 與 Solver results 均未改變；記錄通過、失敗與任何既有 failure。
- [x] 7.4 實作驗證完成後，僅在新行為已成為 current truth 時，以最小幅度更新 `docs/WORKFLOW.md` 的 DXF recognition 流程說明；不得修改 `DOMAIN.md`、`SOLVER.md` 或加入未實作 roadmap，並重讀確認 Current／Future 未混寫。
- [x] 7.5 逐項比對 proposal、spec、design 與 tasks 的實際實作，執行 `openspec validate "hatch-rc-waler-recognition" --type change --strict --no-interactive`，確認所有 artifacts valid、沒有未完成 requirement、scope 越界或 persistence schema migration，並回報 OpenSpec implementation verification 結果。
