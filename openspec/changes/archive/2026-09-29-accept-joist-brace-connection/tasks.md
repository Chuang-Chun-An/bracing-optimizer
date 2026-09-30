# Tasks

## 實作前閱讀

- **Task Group 1**：閱讀 `proposal.md` 的「不變事項」、`design.md` Decision 1、2、4，以及 `beam-member-connection-validation` 的唯一 connected predicate、「斜撐接觸不得建立支撐限制」與 coordinate scenarios。
- **Task Group 2**：閱讀 `design.md` Decision 2、`bim-joist-recognition` delta 的兩個 MODIFIED Requirements，以及 main spec 的「Joist contact SHALL preserve source axes...」。
- **Task Group 3**：閱讀 `design.md` Decision 3、5，以及 `beam-member-connection-validation` 的 runtime predicate、`BeamBraceContact` engineering identity 和 rebuild Requirements。
- **Task Group 4**：回讀全部 proposal／design／delta specs，確認實作沒有擴及 Project schema、Solver、材料規則、Brace face／gap snap 或不相關 refactor。

## 1. 建立 Brace contact model 與共用幾何資格

- [x] 1.1 在適當的 DXF pure geometry owner 建立 finite-perpendicular contact helper，沿用具名 `5.0°` inclusive boundary；以 focused tests 驗證 `5.0°` 與真實 finite shared-endpoint contact 通過，而 `> 5.0°`、無限延長線、finite gap、face projection 與 nearest geometry 全部拒絕。
- [x] 1.2 在 `dxf_import/models.py` 新增 immutable `BeamBraceContact` 與 `Beam.brace_contacts` 空 tuple 預設，欄位保留 Beam／Brace identity、WCS／local point、provenance-only Beam segment index 與 recognition method；以 model tests 驗證既有 Beam fixtures 不需新參數仍可建立，且 `Beam.to_project_row()` 不新增 Brace／Project 欄位或第二份 Strut contact collection。
- [x] 1.3 擴充 `apply_coordinate_system` 對 `BeamBraceContact.local_point` 的投影，保留 `world_point` 與 `brace_id`，並在 coordinate／confirmation focused tests 驗證 local origin 改變只更新 local point、contact identity 或 WCS point 改變會使既有 Beam confirmation signature 失效。

## 2. 保存 BIM Joist Brace contact 並共用 direct-contact rule

- [x] 2.1 將 `dxf_import/joist_recognition.py` 的 direct finite contact 改為呼叫 Task 1.1 的共用 helper，保留 Strut `endpoint_face_contact` 為 Strut-only fallback；執行既有與新增 contact boundary tests，確認 pure Strut contacts 仍只依既有 adapter 投影為 `BeamCrossing`，且 BIM single／pair outcome、ambiguity、station 與 source axis 都不變。
- [x] 2.2 在 `dxf_import/importer.py` 將 `JoistContact(member_role="brace")` 映射為對應 runtime `BeamBraceContact`，同時維持只有 `member_role="strut"` 產生 `BeamCrossing`；以 importer test 驗證 Brace-only single Joist 保存 Brace identity／point、沒有 `BeamCrossing`、`BeamPositions`、`AssociatedBeamIDs` 或 `BEAM_NOT_ASSOCIATED`。
- [x] 2.3 在 `tests/test_dxf_bim_joist_recognition.py` 與 `tests/test_dxf_beam_brace_contacts.py` 增加 runtime projection regression：`crossings` 非空／`brace_contacts` 空時 connected 且 Strut projection 不變；`crossings` 空／`brace_contacts` 非空時 connected 且沒有 warning／Strut constraint；mixed contacts 只投影原有 Strut crossings。執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_bim_joist_recognition tests.test_dxf_beam_brace_contacts -v`，確認 Y05 58 支 Joists、136 個 Strut crossings及 paired-axis contracts 維持不變。

## 3. 擴充一般 Beam validation 與所有 rebuild 路徑

- [x] 3.1 在 `dxf_import/candidate_points.py` 以 keyword-only `braces=()` 擴充 `associate_components_to_struts`，由 finalized Beam path 與目前 formal Braces 建立 raw contacts，再以 Beam identity、Brace identity 與 `distance <= beam_crossing_duplicate_tolerance_mm` 的 WCS point identity 去重；以 `tests/test_dxf_beam_brace_contacts.py` 驗證相鄰 segments 共用頂點只產生一筆 contact、segment index 只作 deterministic provenance，而同一 Beam／Brace 的兩個不等價 WCS intersections 保留兩筆。
- [x] 3.2 實作唯一 runtime predicate `bool(beam.crossings) or bool(beam.brace_contacts)`，保留 `BEAM_NOT_ASSOCIATED` code／severity 並更新訊息；以三個 focused tests 分別驗證 crossings-only、brace-contacts-only 與兩者皆空的 connected／warning outcome。
- [x] 3.3 加入 path 反向與 internal segment iteration order regression，驗證 contact engineering identity集合、去重筆數與 warning outcome 等價，且結果不依 Brace collection order、segment iteration order或 first match。
- [x] 3.4 更新初次 importer、`rebuild_component_associations`、`dxf_import/waler_contact_adjustment.py` 及 inventory 發現的其他完整 rebuild callers，傳入各自 staged／proposed formal Braces；以 tests 驗證 formal Brace 未變時 contact 等價，Brace 被排除時 stale contact 消失並依目前 `crossings／brace_contacts` truth 重新產生或抑制 warning。
- [x] 3.5 增加 downstream isolation test，驗證建立或移除 Brace contact 都不增加或修改 `BeamCrossing`、`ComponentAssociation`、`BeamPositions`、`AssociatedBeamIDs` 或 Solver input。
- [x] 3.6 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_input tests.test_dxf_review_confirmation tests.test_dxf_waler_contact_adjustment -v`，確認一般 Beam、confirmation 與 derived rebuild focused regression 全部通過。

## 4. 文件、完整回歸與 OpenSpec 驗證

- [x] 4.1 實作驗證後更新 `docs/DOMAIN.md` 的 Beam contact／Beam station 說明，記錄 Brace contact 可滿足連接狀態但不產生 Strut station；確認未把尚未成立或 Solver 不使用的語意寫入 Domain 文件。
- [x] 4.2 執行受影響 DXF test modules與 boundary tests；再執行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`，確認 Strut crossing 數量、Project rows、Solver input、Y1A／Y29 legacy geometry、Y05 BIM Joist 與 Waler adjustment 無 regression。
- [x] 4.3 對照 proposal 的 In／Out of Scope、兩份 delta specs 與 design Decisions 進行 implementation review，確認沒有 Project schema migration、Brace-to-Strut 偽裝、nearest／gap snap 擴張、Solver 或材料規則修改。
- [x] 4.4 執行 `openspec validate accept-joist-brace-connection --strict` 與 `openspec verify accept-joist-brace-connection`（若目前 CLI 支援），並確認所有 tasks、spec scenarios、focused tests 與 final regression 均有完成證據。当前 CLI 不提供 `verify` command，故以 strict validate、focused tests與 full regression 作為驗證證據。
