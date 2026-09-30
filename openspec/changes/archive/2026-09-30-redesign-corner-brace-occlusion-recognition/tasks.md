# Tasks

## 實作前閱讀

- **第 1 組前**：讀 `proposal.md` 的「不變事項」、`design.md` D1、D8及三份 delta specs 的數值邊界。
- **第 2 組前**：讀 `design.md` D2與 occluded spec「完整候選」，確認 canonical normal、全 hypotheses與禁止 first-fit。
- **第 3 組前**：讀 `design.md` D3～D5，確認 body與relationship資料完全分層，以及 complete／occluded都逐軌檢查 coverage。
- **第 4 組前**：讀 `design.md` D6及兩份 recognition／centerline specs，確認 body first、relationship second。
- **第 5 組前**：讀 `design.md` D7、repair delta及 `docs/WORKFLOW.md` 的 Preview／Apply transaction。
- **第 6 組前**：讀 `design.md` D8、Risks與Migration；長期文件只在行為驗證完成後更新。

## 1. 固定現況與具名設定

- [x] 1.1 建立 Y05 `104C`／`1081`／`F9E`／`FB7`、Y29 `4C`及 Y1A baseline characterization，記錄目前 body、relationship、coverage與失敗原因，不修改 production behavior。
- [x] 1.2 加入或確認 CornerBrace 專用具名設定：separation `(250,600]`、expected slenderness `3.0`、direction seed `100 mm`、direction `2°`、normal spread `25 mm`、seam `50 mm`、per-rail coverage `0.5`、parallel occluder overlap `0.5`、每端 extension `600 mm`。
- [x] 1.3 補齊所有等號與 epsilon 邊界 tests，並確認 rail separation `600 mm` 與 per-end extension `600 mm` 是兩項獨立設定／判定。
- [x] 1.4 驗證非 CornerBrace recognizers 的既有 settings與 focused regressions不變。

## 2. 建立順序無關的 RailTrack hypotheses

- [x] 2.1 實作無方向性 canonical rail direction與 deterministic canonical normal；以 line start／end反轉 tests確認 direction、normal與identity不變。
- [x] 2.2 將 eligible fragments轉為 normal offsets與軸向 intervals；同一 hypothesis強制 `max(offsets)-min(offsets) <=25 mm`，不得只比較 first seed。
- [x] 2.3 全列舉非等價 fragment subsets／RailTrack hypotheses，允許 shared fragment支持 competing hypotheses；以 offsets `0,20,40 mm`驗證保留 `{0,20}`、`{20,40}`且拒絕 `{0,20,40}`。
- [x] 2.4 對 offsets `0,20,40 mm` 的所有輸入排列驗證產生相同 hypotheses、body outcomes與 diagnostics；禁止 first-fit、first-match與entity-order authority。
- [x] 2.5 實作 overlap與 `<=50 mm` seam interval union；驗證重疊不重複計數、`50`接受、`50+epsilon`形成 gap。
- [x] 2.6 驗證 `>=100 mm` fragment可建立方向，短 fragment只能加入已成立方向；100 mm本身不代表 coverage合格。
- [x] 2.7 全列舉 separation `(250,600]` 的 track pairs，移除舊 `80%` projection、longest-first與端板必要前置 gate；加入 S7低 overlap及multiple-pair permutation tests。
- [x] 2.8 實作 track／body幾何等價合併與 conflict sets；無法唯一分配 fragments時保留 body ambiguity，不依輸入順序決定。

## 3. 分離 BodyGeometryEvidence 與 BodyRelationshipAssessment

- [x] 3.1 建立 immutable `BodyGeometryEvidence`，只保存 exact source identity、fragments、RailTracks、selected pair、supporting-line identities、canonical direction／normal、midline、separation、merged intervals與terminal-plate evidence。
- [x] 3.2 加入結構／boundary tests，證明 `BodyGeometryEvidence` 不含 expected span、slenderness、coverage、gaps、occluders、extension、classification或hard-valid outcome。
- [x] 3.3 對每個 body全列舉 active finite Waler inner line／Strut centerline identities，為每組建立獨立 `BodyRelationshipAssessment`；不得建立 canonical Waler。
- [x] 3.4 在 assessment保存 finite intersections、expected span、slenderness、每軌 coverage、internal／terminal gaps、occluder assignments、每端 extension、classification、hard-valid outcome與structured rejection reasons。
- [x] 3.5 驗證同一 body對relationship A coverage `60%`、對B `45%`時分開保存與判定，不互相污染 body或另一assessment。

## 4. 統一 coverage、extension、classification與唯一性

- [x] 4.1 以每個 assessment的 expected span分別計算兩條 selected rails的union coverage；complete與occluded都要求每軌 `>=50%`。
- [x] 4.2 加入 expected span `2121.320 mm`、每軌coverage恰為約 `1060.660 mm`／50%的接受案例。
- [x] 4.3 加入兩端extension各 `600 mm`但coverage約 `43.4%`的拒絕案例，證明extension不能補償coverage。
- [x] 4.4 加入coverage通過但單端extension `800 mm`的拒絕案例，並驗證 `600`接受、`600+epsilon`拒絕。
- [x] 4.5 只在共同hard gates通過後分類：無 `>50 mm` gap為complete；存在大gap為occluded並逐gap驗證；100 mm fragment coverage不足時不得建立正式角撐。
- [x] 4.6 實作逐gap finite occluder assignment：正交／斜交進入25 mm corridor，near-parallel另需gap overlap `>=50%`；加入每種角色、兩gap只解釋一個、infinite-only、nearby-only、HATCH／text／dimension反例。
- [x] 4.7 驗證terminal plates為非必要 evidence：零／一／兩端板在同等rails與assessment下使用同一 eligibility；plate不得挽救coverage、extension或unexplained-gap failure。
- [x] 4.8 先解body再解relationships：body零解／多解unresolved且不可relationship selection；unique body＋一組hard-valid自動建立；unique body＋多組hard-valid保持unresolved。
- [x] 4.9 驗證同一body有兩組hard-valid relationships時automatic unresolved且Preview有兩個候選；排除其中一個重複Waler後依active facts重算並automatic建立唯一connection。
- [x] 4.10 更新structured diagnostics／Review projection，區分body zero、body multiple、relationship zero／multiple，且下游不解析message或重新列舉rails。

## 5. Relationship-selection Preview 與 atomic Apply

- [x] 5.1 擴充repair candidate／plan DTO，以明確 `selection_mode` 區分 `reference_template`與`body_relationship_selection`；後者只從unique body的hard-valid assessments建立。
- [x] 5.2 每個relationship candidate綁定body signature、exact active Waler／Strut identities、finite endpoints、per-rail coverage、extensions、classification、gap evidence與validation；不得要求template或改選tracks。
- [x] 5.3 更新Preview顯示「本體已辨識、工程關係有歧義」、各candidate identities、endpoints、length、coverage、extensions與validation；未選時Apply disabled，取消／關閉／改選零副作用。
- [x] 5.4 Apply前重驗revision、body signature、active identities、finite intersections、coverage、gaps、extensions及既有validation；stale或tampered candidate必須拒絕。
- [x] 5.5 實作atomic commit／rollback：成功一次重建CornerBrace、唯一Connection、candidate points、problems／ReviewItems與derived values；任一步失敗完整rollback。
- [x] 5.6 使用backward-compatible optional selection mode／body signature保存provenance；舊payload預設既有route，若需要Project schema migration則停止並回報。
- [x] 5.7 以Y29 source `4C`驗證W7／W8同時active時顯示兩個hard-valid candidates、不自動選擇；Apply只建立所選connection，source order不影響結果。

## 6. 真實案例、文件與完成驗證

- [x] 6.1 執行Y05 regression：`104C`不再被舊80% gate淘汰；`1081`取得正確tracks／centerline；`F9E`維持合法occluded；`FB7`因coverage不足維持manual。
- [x] 6.2 執行Y29 `4C` body／relationship ambiguity與source exclusion tests，以及Y1A連接板型regressions。
- [x] 6.3 執行既有Y05 60／60、Y29 52／52 expected-slenderness population characterization；數量不得成為掩蓋新合法結果的固定winner policy。
- [x] 6.4 執行一般Brace／Strut／Waler／Column／Beam／Joist focused tests、DXF module boundaries、Review／persistence tests與完整regression suite。
- [x] 6.5 所有行為驗證通過後，最小幅度更新 `docs/DOMAIN.md`：兩層evidence、canonical-normal RailTrack、`(250,600]` separation、`>=3` slenderness、complete／occluded逐軌50%、逐gap evidence與每端600 mm extension；不改Architecture、Solver或Project schema truth。
- [x] 6.6 執行 `openspec validate redesign-corner-brace-occlusion-recognition --strict --no-interactive` 與實作verification；逐項核對proposal、三份delta specs、design與tasks，確認無first-fit、message parsing、canonical Waler或未授權schema change。
