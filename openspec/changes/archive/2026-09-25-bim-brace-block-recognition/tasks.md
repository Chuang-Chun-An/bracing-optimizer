# Tasks

## 1. 前置條件與現況特徵化

- [x] 1.1 確認 `bim-strut-outline-topology` 已完成實作、同步 main specs、通過 strict validation，且其 pure topology contract 已成為 current code truth；affected artifacts 為該 change、`openspec/specs/bim-block-member-recognition/spec.md` 與 `dxf_import/block_member_recognition.py`，以 OpenSpec status／validation 與對應 Strut regression 全數通過驗證，任一條件未成立即停止本 change 的 production implementation。
- [x] 1.2 在 `tests/test_dxf_bim_block_recognition.py` 增加唯讀 Y05 Brace source characterization，按 exact root handle 記錄 general recognition、pure outcome、normalized axis、terminal extent、representative width 與 Waler connection outcome；以同一 DXF 重跑結果一致且輸出不依賴流水 `B<n>` ID 驗證。
- [x] 1.3 依 characterization 選定並固定至少四類 root-handle fixture：局部短軸可改善為唯一完整軸、genuine competing whole axes、whole-axis 成功但 Waler connection 失敗、ordinary non-component fallback；affected module 為 `tests/test_dxf_bim_block_recognition.py` 與既有 DXF test assets，以每個 fixture 的來源證據與預期 outcome 可獨立說明及測試通過驗證。

## 2. 共用 pure recognition core

- [x] 2.1 先在 `tests/test_dxf_bim_block_recognition.py` 補齊 synthetic Brace root fixtures，涵蓋分段輪廓、interior gaps、細部短矩形、不同完整軸、非 component-like block 與跨 root 不得合併；以測試能分別表達 `recognized`、`ambiguous`、`failed`、`not_applicable` 契約驗證。
- [x] 2.2 在 `dxf_import/block_member_recognition.py` 將既有 WCS primitive、fragment、topology 與 whole-axis 分析收斂為 internal role-neutral entry，保留最小 Strut compatibility wrapper／caller 調整；以現有 Strut BIM recognition tests 的 status、diagnostic code、normalized `whole_axis`、`representative_width`、mapped candidate `source_width` 與 material outcome 全數不變驗證，並確認沒有新增 350 mm default、也沒有把 `maximum_component_width_mm = 600` 當成來源或材料寬度。
- [x] 2.3 在 `dxf_import/block_member_recognition.py` 實作 Brace role policy，使用既有具名 credibility／coverage／ambiguity settings 判定一個 root 最多一支完整 Brace，且不得新增 Y05 專用 magic threshold；以 2.1 的 whole-axis、detail contour、genuine ambiguity 與 terminal extent tests 通過驗證。
- [x] 2.4 在 `tests/test_dxf_bim_block_recognition.py` 增加 child entity order、LINE start/end、closed-path traversal 與 candidate enumeration permutation tests；以等價 WCS geometry 產生相同 outcome 與等價 normalized Brace axis 驗證 deterministic contract。
- [x] 2.5 在 `tests/test_dxf_bim_block_recognition.py` 與 `tests/test_dxf_material_recognition.py` 鎖定 role-neutral refactor 的 Strut invariants：當 same-source topology 存在時，geometry-only parallel pairing不得跨 outline或覆寫共同軸／ambiguity；完全沒有 topology evidence時仍保留既有 open parallel-edge／fragmented component fallback；350／400／500 mm有效 envelopes保留實際寬度；nested same-axis outlines只在合格 envelopes中依containment選寬度；D17約12 mm open detail rails不得決定axis或width；axis已知但width不可靠時維持`0.0`且不自動選材料；multiple complete non-equivalent axes維持blocking ambiguous；最外層contour若未通過connected/unbranched topology、whole-axis coverage、length、slenderness與既有width eligibility不得成為component envelope。以每一類都有獨立 assertion且refactor前後結果相同驗證。

## 3. Importer 路由與角色正確的診斷

- [x] 3.1 在 `dxf_import/recognition.py` 與必要的 `dxf_import/importer.py` 最小泛化 root `INSERT` router，使 Strut／Brace 在 `_merge_related_line_groups()` 前依各自 role policy 處理；以 `not_applicable` 回到同一未合併 root 的一般 Brace recognition、`recognized` 只產生一支 Brace、其他 role 不進入此路徑的 importer tests 驗證。
- [x] 3.2 在 `dxf_import/recognition.py`、必要的 `dxf_import/models.py`／`validation.py` 建立 role-correct outcome mapping，使 Brace `failed`／`ambiguous` 保留 exact root handle、產生 blocking Brace problem 且不得 local fallback；以 Review item 顯示 Brace role、零支 formal Brace、無 Strut-specific wording 驗證。
- [x] 3.3 在 `tests/test_dxf_bim_block_recognition.py` 與 `tests/test_dxf_ocs_wcs.py` 增加 nested insertion、rotation、scale、OCS-to-WCS 的 Brace regression；以 source geometry 只轉換一次、root handle 不遺失且 normalized world axis 正確驗證。

## 4. Waler-to-Waler 關聯與 Review lifecycle

- [x] 4.1 在 `tests/test_dxf_input.py`／`tests/test_dxf_bim_block_recognition.py` 增加 recognized Brace 進入既有 `candidate_points.py` connection flow 的整合測試，涵蓋兩端成功、單端失敗與零端失敗；以成功時正確建立 `FromWaler`／`ToWaler` 與 snapped endpoints，失敗時保留既有 `BRACE_ONE_END_NOT_CONNECTED`／`BRACE_NOT_CONNECTED` 驗證。
- [x] 4.2 增加 connection boundary regression，證明 pure recognition 不接收 Waler collection、不以 Waler connection 選 geometry winner，且不放寬 `connection_tolerance_mm`、不使用 infinite-axis／無來源外插；affected modules 為 `dxf_import/block_member_recognition.py`、`dxf_import/candidate_points.py` 與相關 tests，以相同 source geometry 在不同 Waler context 下保持相同 recognition outcome 驗證。
- [x] 4.3 在 `tests/test_dxf_source_exclusion.py`、`tests/test_dxf_review_workflow.py`、`tests/test_dxf_review_confirmation.py` 與必要的 review modules 補齊 Brace root exclusion／restore、manual endpoint replay、confirmation invalidation、Pause／Resume 與 completed Project conversion regression；以 role + exact root handle identity 可恢復、blocking problem 未處理不能完成、完成後仍使用既有 Brace row schema且沒有 BIM child metadata 驗證。

## 5. 實際資料回歸、文件與最終驗證

- [x] 5.1 在 `tests/test_dxf_bim_block_recognition.py` 以 1.3 鎖定的 Y05 exact root handles 建立 importer-level regression，明確分開 whole-axis recognition 與 Waler connection assertion；以局部截短案例改善、genuine ambiguity 仍 blocking、連接失敗仍保留既有 diagnostic 驗證。
- [x] 5.2 對 Y1A／Y29 ordinary Brace 與所有既有 BIM Strut fixtures 執行 regression，affected tests 至少包含 `tests/test_dxf_bim_block_recognition.py`、`tests/test_dxf_material_recognition.py` 與 `tests/test_dxf_input.py`；以一般 LINE／LWPOLYLINE／closed-outline Brace 行為不變、不同 root 不合併，且 Strut 的 topology-authoritative boundary、無-topology fallback、normalized axis、350／400／500實際寬度、unknown width與Material Review outcome均不變驗證。
- [x] 5.3 實作與測試成立後更新 `docs/WORKFLOW.md`，將 current truth 由 Strut-only BIM special recognition 改為 Strut／Brace role-aware root paths，並記錄 Brace recognition 與 Waler connection 是兩階段；以文件不宣稱所有 Y05 source 必然成功、且不改寫 Architecture／Domain／Solver truth 驗證。
- [x] 5.4 執行 focused regression：`.\.venv\Scripts\python.exe -m unittest tests.test_dxf_bim_block_recognition tests.test_dxf_material_recognition tests.test_dxf_input tests.test_dxf_ocs_wcs tests.test_dxf_source_exclusion tests.test_dxf_review_workflow tests.test_dxf_review_confirmation`，並修正本 change 造成的失敗，不得降低 assertion 或改動無關工程規則。
- [x] 5.5 執行完整回歸：`.\.venv\Scripts\python.exe -m unittest discover -s tests`，確認無新增失敗且沒有 Project schema、Solver、CornerBrace、Waler recognition 或 persistence 行為漂移。
- [x] 5.6 執行 OpenSpec implementation verification，逐項核對 proposal／spec／design／tasks 與實際 diff，並執行 `openspec validate bim-brace-block-recognition --strict`；以所有 requirement 有對應測試、tasks 可追蹤且 strict validation 通過作為完成條件。
