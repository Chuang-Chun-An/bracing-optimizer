# Tasks

## 實作前閱讀

- **第 1 組開始前**：閱讀 `proposal.md` 的「現況與目標／不變事項／Impact」、`design.md` D1、D5、D6，以及新 capability 的「本體 rail 寬度是正式材料規則」與「無唯一合法解必須阻止 DXF Review 完成」。
- **第 2 組開始前**：閱讀 `design.md` D2～D4，以及新 capability 的「完整候選必須全部列舉並優先於遮蔽 fallback」與「遮蔽 rail fallback」；實作有限交點前再讀 `dxf-corner-brace-centerline-extension` delta。
- **第 3 組開始前**：閱讀 `design.md` D5～D7，以及新 capability 的 unresolved operation-level／completion-level contract。
- **第 4 組開始前**：閱讀 `design.md` D7 與 `dxf-corner-brace-repair-tool` delta；repair 的既有 eligibility／explicit adoption／safety contract 不可放寬。
- **第 5 組開始前**：閱讀 `design.md` D8、Migration and Rollback、Open Questions，以及 `proposal.md` 的 In Scope／Out of Scope；只在實作與測試完成後更新 long-term Domain truth。

## 1. 先確認 Review completion 能力並建立材料寬度 truth

- [x] 1.1 先檢查既有 DXF Review workflow／validation 是否能讓 unresolved CornerBrace 在 operation level 保持其他辨識繼續、同時在 completion level 阻止完成；以現有 completion eligibility 測試或最小 characterization test 證明可承載，若必須改變 completion framework 則停止並回報，不修改程式。
- [x] 1.2 在 DXF recognition 可取用的具名設定責任中加入正式 CornerBrace 最小 rail separation `250.0 mm` 與遮蔽短長比 `0.75`，不得放入 Solver 或 UI；以 focused unit tests 驗證 separation `250.0` 被拒絕、略大於 `250.0` 可繼續，且 ratio `0.75` 通過、略低於 `0.75` 被拒絕。
- [x] 1.3 在 `dxf_import/recognition.py` 建立 internal rail-hypothesis／evidence 資料與小型 helper，保存 ordered rails、separation、overlap、length ratio、端板與 reason codes；以合成幾何測試驗證相反端點順序得到相同量測，且正式 candidate 的 `source_width` 等於 rail separation、不是端板長度或兩端板平均。
- [x] 1.4 擴充 internal `_Candidate` 的 `selected_rail_lines` ownership，讓 `_corner_brace_center_axis()`、`_engineering_line_candidates()` 與後續 calibration 直接重用該 pair；以 regression 建立「boundary 中另有更長的 155 mm 平行 pair」案例，驗證中心軸仍使用 recognition 已選的外側 rails，且公開 line evidence 可識別 selected rails。

## 2. 全列舉完整候選並實作 terminal occlusion fallback

- [x] 2.1 在 `_corner_brace_candidates_from_group()` 列舉全部完整雙 rail／雙端板 hypotheses：一般完整 topology 沿用近似等長；完整斜切／梯形 topology 則要求兩條合法平行 rails、兩條不同有限端板、四個實際 rail-to-plate terminal connections 與唯一完整 closed traversal。逐一套用 rail separation `> 250.0 mm` hard gate，再合併方向、端點順序或 exact source 內重複 primitive 造成的幾何等價項；以 tests 驗證不會在 first valid match 停止、155 mm 組合被排除、任意封閉梯形不足以成立、CB28 類不退回 generic `closed_outline_axis`，且輸入／handle／entity 順序改變不影響 body 結果。
- [x] 2.2 對完整 hypotheses 執行既有可分割性判斷：不共用 rails／plates 且安全可分割者可建立多個 CornerBrace，競爭相同 evidence 或無法形成唯一可分割集合者為 ambiguity；以 tests 驗證多實體合法集合、competing-evidence ambiguity，且排序或分數不能將 ambiguity 轉成唯一解。
- [x] 2.3 僅在完成 2.1～2.2 且合法完整 body 集合確實為空時列舉 occluded-rail hypotheses，要求既有平行／重疊、寬度 `> 250.0 mm`、短長比 `>= 0.75` 與至少一端板；以 tests 驗證一般完整或斜切完整集合存在時不啟動 fallback、完整 ambiguity 也不啟動 fallback，雙端板完整斜切 body 不套用 0.75，零端板與真正遮蔽候選比例不足則保留明確 reason code。
- [x] 2.4 在 `dxf_import` recognition staging 實作 terminal-neighborhood occlusion corridor：只有其他已辨識 brace 或同一 exact source group 的有限幾何在具名容差內實際相交、接觸或通過截短 terminal，且位置能直接解釋中斷時才成立；以 focused tests 分別驗證真實 terminal 穿越可成立、同 root 但只在附近不可成立、只有無限延長相交不可成立、只在 rail 其他位置相交不可成立。若需要新增未定義 tolerance 或現有資料不足，停止並回報。
- [x] 2.5 Body recognition 完成後，依目前 active source/member identities 對完整與遮蔽 hypotheses 套用唯一有限 Waler 內線／Strut 中心線關聯 hard gate，不以無限延長、最近距離或幾何重合補足；不得建立 geometry-equivalent Waler relationship group 或 canonical Waler ID。以合成 tests 驗證兩個有限交點唯一時可成立，缺少有限交點、兩個 active 且幾何重合的 Waler sources、或其他 competing relationship 時保持 unresolved，交換 handle／entity 順序結果不變。

## 3. 建立正式結果、unresolved problem 與 Review completion gate

- [x] 3.1 讓唯一合法遮蔽 hypothesis 建立 `occluded_parallel_rails` CornerBrace，沿用 selected rail 中線完成有限交點校正與 `CornerBraceConnection`／candidate points；以 Y05 CB58 focused regression 驗證選到 P20–P27 所屬外側組合、真正正交 rail separation 約 `300.000 mm`，不採用約 `331.86 mm` 的有限線段端點平均，且不再採用 `155 mm` 內部 pair。
- [x] 3.2 對 body 零解、完整候選 ambiguity、多個非等價 fallback 或 body 已成功但 active member relationship 無解／多解建立 `CORNER_BRACE_RAIL_CANDIDATE_UNRESOLVED` problem；diagnostics 必須區分 body geometry 已辨識與 connection unresolved，並保留 exact handle、source geometry、selected rails、rail separation、competing source identities 與拒絕／ambiguity 原因，不建立空殼或猜測 connection。以 validation tests 驗證其他來源仍可辨識、顯示及檢核，但 Review completion eligibility 為 false。
- [x] 3.3 將 unresolved problem 投影至既有 DXF Review debug／validation model，Presentation 只顯示既有 projection、不重算幾何；以 Review workflow tests 驗證可定位來源、查看 body status／寬度／關聯原因，且來源在被合法排除、修正或解決前無法完成 Review。另驗證排除 W7 或 W8 任一重複 Waler source 後會依目前 active facts 完整重跑、只連接剩餘唯一 Waler，且不保存或重播先前暫時選擇／ambiguity outcome；系統不會自動刪除來源或自動採用 repair candidate。

## 4. Repair 與 persistence 相容性

- [x] 4.1 維持 automatic recognition 與 reference-template repair 的責任邊界：成功辨識的完整或 `occluded_parallel_rails` connection 不進入 repair，body 已成功但 relationship ambiguous、unresolved problem／warning 也不能單獨取得 repair eligibility；以 `tests/test_dxf_corner_brace_repair.py` 新增成功 automatic、body 無解與 relationship 多解案例，驗證 repair 不會合併 Waler identities 或選 canonical Waler，且只有通過既有 eligibility 並由使用者明確採用的合法 repair 才能解決來源並解除 completion block。
- [x] 4.2 驗證新增 recognition method、selected rail line source 與 unresolved metadata 對既有 DXF Review save/load／Pause／Resume 向後相容，且不修改 Solver-facing Project schema；以既有 persistence／workflow regression 載入缺少新 evidence 的舊狀態並確認可讀，重新辨識後才產生新 evidence。

## 5. 真實圖面回歸、Domain 文件與完成驗證

- [x] 5.1 執行 Y05 全圖 regression，驗證 CB58 identity、中心線、有限 Waler／Strut 關聯與寬度修正，並鎖定其他正常 CornerBrace 數量及端點沒有非預期變化；保存可重現的 focused assertions，不只依賴人工看圖。
- [x] 5.2 執行 Y1A／Y29 CornerBrace regression：驗證 Y1A 約 `300 mm` rail pairs 維持正式 connection；Y29 CB28／source `4C` 依完整斜切 topology 辨識 body、`source_width ≈ 300.000 mm` 的 selected rail 真正正交間距，不採用約 `362.132 mm` 的有限線段端點平均或 `424.264 mm` 端板平均，但 W7／W8 同時 active 時 connection unresolved 且 Review 不可完成。最低 tests 必須覆蓋：(a) W7/W8 同時 active 不建立任意 connection；(b) 排除 W7 後唯一連 W8；(c) 排除 W8 後唯一連 W7；(d) W7/W8 輸入順序互換 outcome 相同；(e) 單一 Waler relationship 的完整斜切角撐正常完成。確認一般 Brace／Strut／Waler／Column／Beam 結果不變。
- [x] 5.3 在所有行為測試通過後更新 `docs/DOMAIN.md`，記錄 selected rails 正交間距是 CornerBrace 本體寬度、正式 rail separation 必須嚴格 `> 250.0 mm`、端板長度及平均值不得取代本體寬度，且此正式材料規則目前由 DXF automatic recognition 執行、不是 Solver scoring 或搜尋參數；以文件 review 確認未改變其他 member 材料規則、Architecture、Solver 或 Project schema。
- [x] 5.4 執行最接近修改的 CornerBrace／DXF input／repair／Review workflow tests、`tests/test_dxf_module_boundaries.py` 與完整 regression suite，接著執行 `openspec validate recognize-occluded-corner-brace-rails --strict --no-interactive` 及 OpenSpec implementation verification；確認所有測試通過、無不相關修改，並回報任何 fixture、真實圖面或可靠遮蔽證據限制。
