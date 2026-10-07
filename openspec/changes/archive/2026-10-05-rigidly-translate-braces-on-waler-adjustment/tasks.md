# Tasks

## 實作前閱讀

| Task group | 開始前必讀 | 目的 |
| --- | --- | --- |
| 1. Baseline 與純幾何 | `proposal.md`「現況與目標」；`design.md` Decision 1～3；spec「一般斜撐 SHALL 以共同平移…」、「斜撐 SHALL 使用兩端最終圍令…」 | 先固定 formal-only source of truth、baseline-WCS override、方程與平行／有限線段邊界 |
| 2. Adjustment plan 整合 | `design.md` Decision 2～4；spec「平行圍令 SHALL…」、「無唯一合法剛體解時 SHALL 原子失敗」 | 以兩端 final Waler 取代單端 station 更新，維持 pure plan／atomic apply |
| 3. Workflow、replay 與 downstream | `design.md` Decision 2、4～6；spec「斜撐 SHALL 使用兩端最終圍令…」、「Preview、downstream geometry 與 Project projection SHALL 使用同一結果」 | 確保 adjusted-view endpoint 先轉回 baseline WCS、replay 不重複位移，且兩端移動傳到所有 consumers |
| 4. 文件與整體驗證 | `proposal.md`「不變事項」；全部 spec Requirements；`design.md` Architecture Alignment／Risks | 確認沒有擴張到 Solver、Strut、CornerBrace 或 Project schema |

可先跳過 `docs/SOLVER.md`、Solver regression 細節與 CornerBrace repair specs；若實作意外碰觸 Solver 檔案或改變角撐規則，應停止並回報 scope 衝突。

## 1. 建立 Brace adjustment baseline 與純幾何解

- [x] 1.1 在 `dxf_import/models.py` 與 Waler contact 初始化路徑加入最小、不可變且可重建的 formal Brace adjustment baseline，保存 source identity、兩端 Waler identities 與 adjustment 前 WCS endpoints；以 `tests/test_dxf_waler_contact_adjustment.py` 驗證 baseline 只為 canonical result 中兩端 identity 唯一且不同、完整 formal connection 已成立的 Brace 建立，side-only／competing evidence、同一 Waler、缺端或 ambiguous Brace 均不得建立 baseline，且重複初始化不把已調整 geometry 當新 baseline、不新增 Project row／Solver 欄位。（對應 baseline Requirement、Design Decision 2／5；與 `enforce-unique-brace-waler-terminals`、`decouple-waler-side-evidence-from-terminal-identity` 一致）
- [x] 1.2 在 `dxf_import/waler_contact_adjustment.py` 建立 pure rigid-translation calculation，使用 baseline 向量與兩端 final Waler lines 求共同 `t`；加入水平／垂直、一般斜交、start／end 反轉與 Waler collection order 反轉測試，驗證兩端 displacement 相同且向量、角度、長度在既有 tolerance 內不變。（對應剛體 Requirement、Design Decision 1）
- [x] 1.3 為 pure calculation 加入平行相容 minimum-norm 解、單邊平行位移不相容、退化 baseline、identity 無效及 infinite-line 解落在 finite segment 外的測試；驗證只使用既有具名 tolerances，失敗不做 nearest snap、endpoint clamp、旋轉或伸縮。（對應平行與原子失敗 Requirements、Design Decision 3）
- [x] 1.4 在既有 `SourceManualOverride`／version 2 `manual_overrides` payload 加入 optional baseline-WCS 語意標記，更新 capture／parse／serialization 並新增 round-trip 與 legacy tests；驗證新 Brace endpoint override 帶 `baseline_wcs`、非 Brace 語意不變、缺標記且 `t = 0` 可安全 replay、缺標記且存在非零 adjustment 時人工 geometry 進入 `needs_review` 但可獨立重驗的尺寸 decision 不丟失，且 `review_state_version` 與 Project schema 均不提升。（對應 baseline Requirement、Design Decision 2／5）

## 2. 將一般 Brace 接入兩端聯立 adjustment plan

- [x] 2.1 在 `plan_waler_contact_adjustment()` 以「target proposed Waler + 另一端目前 final Waler + immutable Brace baseline」取代現有單端 station 更新，並同時更新 Brace 兩端；`test_three_member_types_follow_distinct_geometry_rules` 的 fixture、Brace 預期 endpoints／angle／length 與 assertions 應依本 change 明確改成非平行 Waler 的共同平移結果，這是預期 contract 變更，不得保留舊有單端 station、旋轉／伸縮預期；Strut／CornerBrace assertions 維持既有規則。（對應剛體 Requirement、Design Decision 1／4）
- [x] 2.2 擴充 `BraceAdjustment` 與 plan result，記錄共同 translation、From／To old／new stations、baseline／proposed endpoints；以直接測試驗證資料可同時描述兩端滑移，且合法 plan 的 angle／length before-after 等價。（對應 Preview Requirement、Design Decision 6）
- [x] 2.3 新增同一 Waler 重複編輯、兩端 Waler 依相反順序編輯、preview 後 apply 與直接 apply 的等價測試；驗證所有路徑都從同一 baseline 與兩端 final lines 重算，不累積浮點 drift，結果不依操作順序。（對應 baseline Requirement、Design Decision 2）
- [x] 2.4 新增並註冊可追溯的 rigid-translation blocking diagnostics，涵蓋 parallel incompatible、outside finite segment、identity invalid 與 baseline drift；以多構件案例驗證任一 Brace 失敗時 `apply_waler_contact_adjustment()` 保留 Waler、Brace、Strut、CornerBrace、association 與 CandidatePoint 提交前狀態。（對應原子失敗 Requirement、Design Decision 3／4）

## 3. 串接 Preview、downstream rebuild 與 Review replay

- [x] 3.1 更新 `format_adjustment_plan()` 與既有 dialog preview projection，顯示共同平移、兩端 station 變化及不變的 angle／length；加入 formatter／dialog focused test，驗證 preview pure、取消不 mutation，且不再顯示「單端 station 不變」的舊語意。（對應 Preview Requirement、Design Decision 6）
- [x] 3.2 驗證成功 apply 將整支 Brace 列為 changed component，並沿既有 rebuild 更新 CandidatePoints、Beam／member contacts、diagnostics、world／local projection 與 Project Brace row；擴充 focused tests，確認所有 consumers 使用同一組 moved endpoints，Project schema 沒有第二組 geometry。（對應 downstream Requirement、Design Decision 4／5）
- [x] 3.3 在 Brace 人工 endpoint 的既有 workflow command／CandidatePoint commit boundary 計算目前共同平移 `t`，將可見 endpoint pair 轉為 `p - t` 後再 staged commit；加入「先改端點再調 Waler」與「先調 Waler 再改端點」測試，驗證前者以人工 geometry 建 baseline，後者重算後回到使用者點選位置且位移恰好套用一次。另加入換算點超出任一 baseline Waler finite segment 的測試，驗證顯示原因、拒絕整次修改，endpoint、CandidatePoint、connection、confirmation、baseline、dimension decision 與完整 Review state 均不變，且不 clamp／snap／硬存。（對應 baseline Requirement 的三個 manual endpoint Scenarios、Design Decision 2／4）
- [x] 3.4 將 same-source recognition、debug restore、source exclusion／restore、Pause／Resume、manual endpoint replay 與 compatible recovery 固定為 `recognition → baseline-WCS manual geometry replay → formal baseline build → Waler dimension replay → downstream rebuild`；在 `tests/test_dxf_waler_contact_adjustment.py`、`tests/test_dxf_source_exclusion.py`、`tests/test_dxf_review_workflow.py`、`tests/test_dxf_review_recovery.py` 驗證「端點後尺寸」、「尺寸後端點」與 Resume／replay 幾何等價、不 double-apply，legacy 未標記非零 adjustment 進入 `needs_review`，identity drift 維持 safe skip，不猜測 baseline。（對應 baseline／Preview Requirements、Design Decision 2／5）
- [x] 3.5 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_waler_contact_adjustment tests.test_dxf_review_workflow tests.test_dxf_source_exclusion tests.test_dxf_review_recovery -v`，修正本 change 造成的 regression，且不得降低既有 Strut、CornerBrace、confirmation invalidation、manual replay report 或 atomic apply assertions。（對應 proposal「不變事項」）

## 4. 長期文件、回歸與 OpenSpec 驗證

- [x] 4.1 行為測試通過後，最小更新 `docs/DOMAIN.md` 與 `docs/WORKFLOW.md`：記錄「一般 Brace 在 Waler contact adjustment 中以兩端 final Waler 聯立剛體平移」、manual endpoint 以 baseline WCS 保存、固定 replay 順序及無解的 atomic blocking semantics；在 `docs/WORKFLOW.md` Pause／Resume 段落明記依新規則重算時 Brace 位置可能不同於舊版曾採用結果。確認既有 `ManualReplayReport` 足以承接 unsafe legacy override，不新增 Resume UI；Architecture responsibility 未變所以不修改 `docs/ARCHITECTURE.md`，Solver truth 未變所以不修改 `docs/SOLVER.md`。（對應 proposal Impact、Design Decision 2／5 與 Architecture Alignment）
- [x] 4.2 執行最接近的 Project conversion、CandidatePoint、DXF Review confirmation 與 coordinate-system regression tests，至少包含 `tests.test_dxf_review_confirmation`、`tests.test_dxf_input` 及實際受影響的 CandidatePoint／Project conversion test modules；驗證 WCS／local 結果一致、Project row 仍只有既有 Brace endpoints、250 mm／600 mm recognition 行為未改變。（對應 downstream Requirement 與 Out of Scope）
- [x] 4.3 執行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` 與 architecture boundary tests，記錄通過、失敗及任何已知既有 failure；不得以刪除測試、降低 assertion 或改動 Solver policy 取得通過。（Final regression）
- [x] 4.4 對照 `proposal.md`、`design.md`、delta spec 與本 tasks 逐項 review 實作，確認一般 Brace 長度／角度不變、兩端共同移動、平行不相容 fail-closed、編輯順序無關、Strut／CornerBrace／Project schema／Solver 不變；執行 `openspec validate rigidly-translate-braces-on-waler-adjustment --strict` 及 OpenSpec verify workflow，確認 artifacts 與 implementation 一致後才可進入 archive。（OpenSpec implementation verification）

