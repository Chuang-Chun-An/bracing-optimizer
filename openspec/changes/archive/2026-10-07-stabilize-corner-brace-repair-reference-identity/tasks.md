# Tasks

## 實作前閱讀

- **Group 1 開始前（P0）**：讀 `proposal.md` 的「快速摘要／不變事項」、`design.md`「現行 identity audit」與D1／D2，以及delta spec的「Stable reference 無匹配／匹配不唯一」；確認不得修改`CornerBraceRepairReference`全域equality，也不得使用display ID、proximity或first match fallback。
- **Group 2 開始前（P0）**：讀 `design.md` D3與spec「相同來源安全重播／Target顯示編號位移但source identity未變／Preferred repaired ID衝突」；確認stable match後仍執行完整current validation，target canonical identity與preferred-ID guard不得混為同一identity。
- **Group 3 開始前（P0）**：讀 `design.md` D6與spec「CornerBrace confirmation只發生顯示編號位移／工程內容改變」；只canonicalize列舉的CornerBrace display metadata，不可全域刪除任意ID或放寬其他role confirmation。
- **Group 4 開始前（P1）**：讀 `design.md` D4／D5、主規格「參考角撐必須分級並阻止推測鏈」及 `docs/WORKFLOW.md` 的 CornerBrace repair／Source Exclusion／Resume 段落；確認保留 secondary deferred pass、persistence shape 與 Exact Match 行為。
- **Group 5 開始前（P1）**：讀 `design.md`「S14／D1A target實體核對」與「S14／D1A fixture regression」及archived `optimize-dxf-source-exclusion-workflow/design.md` 的「S14／D1A反例根因」；只把display-ID false negative修正，不保留真正依賴S14的角撐。
- **Group 6 開始前（P2）**：回讀 proposal In／Out of Scope、完整delta spec與design Risks；可跳過Solver、材料、Waler最佳化、Preview UI與Project schema migration。

## 1. Stable reference resolver

- [x] 1.1 在 `dxf_import/corner_brace_repair.py` 實作 module-private reference match key與current-evidence index，以 `(reference_class, CornerBraceRepairSubjectKey)` 保留全部候選而非dictionary overwrite；新增focused tests驗證相同subject／不同`member_id`可匹配，執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_corner_brace_repair -v` 通過。
- [x] 1.2 實作整組saved references的恰好一筆、一對一且保持saved order的resolver，安全拒絕零筆、多筆、duplicate saved key與class mismatch；新增對應negative tests並以同一focused unittest確認不使用display ID、collection order或first match。
- [x] 1.3 保持`CornerBraceRepairReference`既有dataclass equality／hash與`CornerBraceRepairSubjectKey`serialized shape不變，新增assertion或round-trip test證明`member_id`仍可保存作diagnostic但不參與resolver key，並執行CornerBrace persistence tests通過。

## 2. Template 與 legacy reconstruction

- [x] 2.1 修改`reconstruct_saved_template_candidate()`，以共用resolver取得selected template與完整current primary集合，並讓candidate的`template_reference`／`primary_references`使用current references；新增selected／supporting primary display-ID drift tests，驗證replay成功且新provenance保存current IDs。
- [x] 2.2 將manual secondary references接入同一resolver並保留`replay_manual_overrides()`既有deferred pass；新增secondary ID drift、producer晚一輪成功及confirmation／provenance失效仍`needs_review`的測試，執行`tests.test_dxf_corner_brace_repair`通過。
- [x] 2.3 確認stable match後仍重驗current template geometry、saved local dimensions、unique connection、target relationship、target residual evidence與candidate validation；補齊geometry／connection／eligibility drift regressions並驗證既有changed-primary與connection-drift tests持續通過。
- [x] 2.4 修改`reconstruct_legacy_adopted_candidate()`使用相同resolver及current references，但不重新ranking、不改nearest template或saved adopted world line；新增legacy reference ID drift與unsafe substitution tests，執行CornerBrace legacy／persistence tests通過。
- [x] 2.5 新增target Waler／Strut identity tests：顯示ID改變但canonical source identity唯一且relationship未變時成功；零筆、多筆、另一source取得舊display ID或relationship drift時安全拒絕，不使用W／S display ID作fallback。
- [x] 2.6 新增`CornerBraceRepairSubjectKey.base_geometry_key`契約測試，分別證明recognized key使用完成connection-context refinement後的工程線、unresolved key使用exact source body geometry，且兩者皆不包含W／S display ID；保留current unique connection的獨立revalidation。
- [x] 2.7 新增preferred repaired ID conflict tests，驗證ID被不同source占用或staged replay得到不同ID時不commit任何partial result、不得改套占用者或靜默接受新ID，並維持既有`needs_review`分類。

## 3. CornerBrace confirmation穩定化

- [x] 3.1 在`dxf_import/review_confirmation.py`加入CornerBrace-specific confirmation payload canonicalizer，只排除top-level CornerBrace ID、nested `CornerBraceRepairReference.member_id`、`preferred_display_id`及design列舉的純display metadata；不得改變persisted confirmation key、其他role signature或Project schema。
- [x] 3.2 新增focused signature tests，證明同一source CornerBrace只改top-level／nested display IDs時signature不變；source、geometry、repair subject、adopted line、transfer evidence、stable reference identities、relationship、warnings或problems任一改變時signature必須改變。
- [x] 3.3 新增confirmation identity isolation tests：同一source CornerBrace改名後仍以current ReviewItem取得current member；不同source取得舊display ID不得命中原confirmation；Beam assembly與Waler contact confirmation既有tests必須維持通過。
- [x] 3.4 串接manual repaired secondary replay test，驗證producer完成後、secondary stable identity唯一且只有display metadata重編時既有confirmation仍有效並可在deferred pass成功；confirmation工程內容失效時仍為`needs_review`。

## 4. Replay lifecycle 與相容性邊界

- [x] 4.1 驗證source exclusion／restore與same-fingerprint Pause／Resume都只透過共用reconstruction取得stable matching，`dxf_import/source_exclusion.py`不新增第二套matcher；執行`tests.test_dxf_corner_brace_repair`及相關`tests.test_dxf_review_workflow` replay tests通過。
- [x] 4.2 驗證Exact Match Relink仍只更新source reference、不增加recognition或第二次確認，後續Resume rebuild才走共用matcher；執行`tests.test_project_service`與`tests.test_dxf_review_workflow`中的paused-review exact-relink tests通過。
- [x] 4.3 驗證fingerprint不同的compatible recovery不因stable reference可對齊而套用repair或恢復reference eligibility，保留`requires_review`／`disabled`分類；執行既有changed-content recovery tests並新增必要的stable-reference反例。
- [x] 4.4 以既有mapping round-trip測試確認不新增欄位、不提高Review state／Project schema version、舊payload仍可讀且非法／partial payload仍安全拒絕；執行CornerBrace persistence與Project persistence相關focused tests通過。

## 5. S14／D1A工程回歸

- [x] 5.1 在`tests/test_dxf_source_exclusion_fixture_regression.py`加入Y05排除Strut `S14`／handle `D1A`的regression，驗證真正依賴S14的CB28～CB31消失，而CB66～CB70不再只因reference display ID重編成為`needs_review`；單獨執行該test method通過。
- [x] 5.2 Assert CB66／CB67 target Waler／Strut顯示ID不變；CB68～CB70 target Strut分別`S21→S20`／`strut:D74`、`S20→S19`／`strut:D4B`、`S19→S18`／`strut:D34`，Waler皆維持`W13`／`waler:1647`，證明前後為同一實體構件而非display-ID fallback。
- [x] 5.3 Assert五筆automatic-primary remap為CB61→CB57（`11D0`）、CB62→CB58（`1205`）、CB56→CB52（`113F`）、CB53→CB49（`1126`）、CB50→CB46（`110D`），並記錄fixture無manual secondary與review confirmations，避免把D6誤認為S14直接根因。
- [x] 5.4 擴充S14 fixture assertion，核對CB66～CB76的replay report、stable reference subject keys、current display IDs、repair provenance、members、connections、problems、ReviewItems、confirmations與completion truth；執行`.\.venv\Scripts\python.exe -m unittest tests.test_dxf_source_exclusion_fixture_regression -v`通過。
- [x] 5.5 重新執行既有Y05 BM29與Y29 source-exclusion regressions，確認本change沒有改變paired Joist、legacy Waler、local candidate validation、atomic commit或lazy debug行為；以整個`tests.test_dxf_source_exclusion_fixture_regression`通過為完成條件。

## 6. 文件與最終驗證

- [x] 6.1 在implementation驗證通過後更新`docs/WORKFLOW.md`的CornerBrace replay摘要，記錄stable subject identity唯一匹配、CornerBrace confirmation display canonicalization、preferred-ID安全guard與changed-content recovery邊界不變；以文件敘述與delta spec／design一致且未宣稱schema或architecture改變為完成條件。
- [x] 6.2 執行focused regression：`.\.venv\Scripts\python.exe -m unittest tests.test_dxf_corner_brace_repair tests.test_dxf_source_exclusion_fixture_regression tests.test_dxf_review_workflow tests.test_project_service -v`，修正本change造成的失敗且不得刪除測試或降低assertion。
- [x] 6.3 執行`.\.venv\Scripts\python.exe -m unittest discover -s tests -v`及受影響時的`tests.test_application_domain_boundaries`，確認無DXF lifecycle或architecture boundary regression；回報任何與本change無關的既有失敗，不擴張scope修理。
- [x] 6.4 執行`openspec validate stabilize-corner-brace-repair-reference-identity --strict`與`$openspec-verify-change stabilize-corner-brace-repair-reference-identity`，逐項對照proposal scope、delta scenarios、design decisions與本tasks checklist，確認implementation完整後才建議archive。
