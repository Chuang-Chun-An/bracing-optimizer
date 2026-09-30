# Proposal

## 閱讀導航

### P0｜現在必讀

- 本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」。
- `openspec/specs/bim-joist-recognition/spec.md` 的「Formal BIM Joist axes SHALL be derived from whole-source geometry」。
- 同一 spec 的「Strut and Column context SHALL qualify a unique two-Joist assembly」與 Y05 regression requirements。

### P1｜實作前閱讀

- 本 change 的 `design.md`：Column terminal window、rail qualification、terminal extent 與 failure semantics。
- `docs/ARCHITECTURE.md` 的 DXF recognition stage dependency 與 Joist pure-service ownership。
- `dxf_import/joist_recognition.py` 的 `_cluster_longitudinal_evidence()`、`_source_axes()`、contact 與 pair relation 流程。
- `tests/test_dxf_bim_joist_recognition.py` 的 Y05 whole-source、pair relation、crossing 與 Project projection regression。

### P2｜需要時再讀

- `docs/WORKFLOW.md` 的 DXF Review、confirmation、source exclusion／restore 與 replay lifecycle。
- `dxf_import/recognition.py` 的 BIM Joist router 與 `dxf_import/importer.py` 的 `JoistContextSnapshot` 建立流程。
- 本次可先跳過 Solver、Waler optimization、CornerBrace repair、RC Waler 與一般 BIM Strut 規格；它們不是本 change 的行為範圍。

## 快速摘要

- Y05 的雙 C 托梁 root 在中間柱外側仍有來源支持的短殘線，但現行「至少為最長 fragment 20%」的前置篩選會先排除它們，使正式托梁軸從柱內側主體開始。
- 新規則只對已由既有 Strut／Column context 證明跨越中間柱的 BIM Joist assembly 開放 terminal residual recovery；從中間柱中心沿既有托梁軸、朝該 terminal 外側量測的 signed projection `0～700 mm` 為含邊界候選窗，反方向證據不屬於此窗。
- 距離本身不構成托梁證據；殘線仍須屬於同一 root、方向相容，且可對齊已辨識 Joist envelope 的 longitudinal rail bands，才能跨越柱體遮蔽 gap 延伸 terminal extent。
- Y1A 與 Y29 的 MLINE／closed-outline Beam 保持既有辨識；Brace-contact single Joist、518 mm 配對、Column midpoint、Project schema 與 Solver 都不改變。Y05 原本因軸線截短而使用的 `endpoint_face_contact`，在殘線恢復後若形成真實有限交點，改以 direct crossing 表達。

## 現況與目標

「terminal residual（端部殘線）」指同一 Beam root 內、位於中間柱另一側且仍支持既有托梁長方向／外框，但因長度短或遭柱體、斜撐投影切碎而未進入 whole-source longitudinal evidence 的來源線段。

| | 現況（Before） | 目標（After） |
|---|---|---|
| 初始資格 | 所有 longitudinal fragments 共用 `max(100 mm, 最長 fragment × 20%)`；較短者先被排除 | 一般 fragments 維持原門檻；只有通過 Column contextual terminal eligibility 的殘線可進入端部恢復 |
| 中間柱語意 | Column 只用於驗證兩支 Joist 的 spacing／midpoint，不能協助 terminal extent | 已成立的 same-Strut／opposite-side／spacing／midpoint 關係可界定 terminal residual window |
| 700 mm 範圍 | 無 | 從 formal Column center 沿 Joist 軸向端部量測，來源殘線全段最外投影距離 `<= 700 mm` 才可候選 |
| 短線安全性 | 短線一律不影響軸線，可能漏掉真實尾段 | 距離、root、方向與既有 rail-band 對齊必須同時成立；不把鄰近任意細節線升格為托梁 |
| 正式幾何 | Y05 BM18 類軸線停在柱內側主體，例如 `X=-35323.5` | 可由柱外來源殘線支持完整端部，例如恢復至 `X=-36173.5`，並跨越柱體遮蔽 gap |

Y05 characterization 顯示 20 組 paired assemblies 均有此型端部證據；目前觀測到的 120 條柱外短線全部落在 700 mm 窗內，其中 117 條長 500 mm，最外端距 Column center 675 mm。Y1A 與 Y29 使用 MLINE／closed outline，既有來源路徑已保留，不需要套用此 BIM contextual recovery。

## 主要流程

```text
Beam root 的 whole-source 主體證據
        |
        v
既有 single／paired Joist axis 與 Column pair relation 成立
        |
        v
只在 terminal side 建立 Column center <= 700 mm 候選窗
        |
        v
同 root + 同方向 + 對齊既有 longitudinal rail band？
        | yes
        v
以來源支持的 terminal evidence 跨越柱體遮蔽 gap
        |
        v
兩條 paired axes 各自使用 deterministic、source-supported terminal extent
        |
        v
兩個 terminal stations 相差 <= 50 mm，確認為同一 paired terminal event
```

距離窗只限制「可重新考慮哪些短 fragment」，不授權補出沒有來源支持的方向、橫向中心、paired axis 或任意固定 700 mm 長度。

## 不變事項

- `518 ± 5 mm` paired-axis spacing、Column midpoint `±2 mm`、same-Strut／opposite-side eligibility 不變。
- `endpoint_face_contact` 的資格與 `25 mm` tolerance 不變，仍是來源軸真正停在 Strut 外緣時的 fallback；terminal recovery 必須先完成，恢復後已穿越 Strut 的軸改用 finite crossing，且 crossing station 不得漂移。
- 一個可靠 paired root 仍只建立恰好兩條 Joist axes，且共享 source-atomic confirmation／exclusion lifecycle。
- Brace-contact single Joist 維持既有有限垂直接觸規則；本 change 不新增 Brace-guided residual extension。
- 一般 LINE、MLINE、closed outline Beam、Y1A、Y29、Project schema、Solver 與材料規則不變。

## Why

現行 BIM Joist whole-source recognition 會在 Column context 介入前，以相對最長 fragment 的比例排除短線。Y05 證明這會把同一雙 C 托梁位於中間柱外側、且可由既有 paired assembly 與 rail alignment 驗證的真實端部殘線誤當成 detail，造成正式托梁軸被截短。

需要新增一個窄且可稽核的 Column contextual terminal rule，使短線只有在既有托梁與中間柱關係已成立、來源拓撲相容且位於 700 mm 安全窗內時才可恢復；避免直接降低全域 20% 門檻而讓 L-angle、孔洞、端板或其他局部細節污染所有 Joist roots。

## What Changes

- 為 BIM Joist 定義 Column-qualified terminal residual：必須屬於同一 root、位於已驗證 Column relation 的 terminal side、方向相容，並對齊既有 Joist envelope 的 longitudinal rail band。
- 新增具名 `700 mm` inclusive Column terminal window；距離從 formal Column center 沿既有 Joist longitudinal axis 朝 terminal outward direction，以 signed projection 量測到殘線最外來源投影。
- 允許合格殘線跨越中間柱實體寬度或 BIM 投影造成的 interior gap，更新 source-supported terminal extent；不得固定延長 700 mm 或以 Column context 憑空建立幾何。
- paired assembly 的兩個 sibling 必須各自取得足夠 rail-band evidence，並以 `50 mm` tolerance 確認屬於同一 terminal recovery；每支 finalized axis 仍只延伸至自身來源支持的 extent，不以另一支較外端點替它補長。
- preliminary context 只開啟 recovery；finalized axes 必須重新證明相同 Strut／Column identity。證據不足時保留 base axes，只有 identity 矛盾、多重 identity 或多個完整且不相容的 terminal interpretations 才 blocking。
- terminal recovery 在 contact classification 前完成；恢復後與 Strut 真實相交者使用 finite crossing，不再保留同一位置的 `endpoint_face_contact`，但既有 station、association 與 Project constraint 語意保持等價。
- 增加 synthetic boundary、Y05 BM18／E8F、F2A 斜撐切碎殘線，以及 Y1A／Y29 legacy Beam regression。

### In Scope

- Beam-role root `INSERT` 的 BIM Joist whole-source terminal recognition。
- 已由既有 Strut／Column context 證明的 paired-axis assembly。
- Column center `<= 700 mm` 的端部來源殘線資格、rail alignment、gap bridging、terminal extent 與 diagnostics。
- Y05 actual-file characterization 與 Y1A／Y29 backward-compatibility regression。

### Out of Scope

- 以 Brace context 新增另一套 residual extension；Brace-contact single Joist 沿用現況。
- 降低或移除一般 longitudinal evidence 的 20% 門檻。
- 從不同 root 拼接線段、以空間最近線猜測托梁、或把 700 mm 當成固定延長量。
- 修改 Strut、Column、Brace、Waler 的 source recognition truth。
- 修改 Solver、Project schema、材料規則、DXF 原檔或一般非 BIM Beam recognition。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `bim-joist-recognition`：新增由既有 paired Joist／Column relationship 限定的 terminal residual eligibility、700 mm inclusive window、source-supported gap bridging、per-sibling source-supported extent 與 paired terminal-event compatibility，並調整恢復後 direct crossing 與 Y05 regression behavior。

## Impact

- 主要影響 `dxf_import/joist_recognition.py` 的 pure whole-source evidence／axis finalization，以及 `dxf_import/recognition.py` 傳遞 candidate provenance 的窄幅整合。
- 可能需要擴充 DXF-internal immutable DTO／diagnostic metadata，但不新增 Project persistence schema。
- 測試重點為 `tests/test_dxf_bim_joist_recognition.py`，並以既有 Y1A、Y29、Y05 fixtures 執行 importer regression。
- Architecture dependency direction不變，仍為 `Joist source geometry + immutable upstream Strut／Column context → pure recognition outcome`。
- Domain 與 Solver truth 不變；實作完成後需更新 `docs/WORKFLOW.md`，記錄新的 DXF Joist terminal recognition 行為。`docs/ARCHITECTURE.md` 僅在實作導致 ownership 或 contract 改變時才更新。

## 已定案條件與重新評估門檻

- `700 mm` 在本 change 中是 Column contextual recognition safety boundary，不是材料尺寸或通用工程設計限制。若新增 fixture 出現已確認真實殘線最外投影超過 700 mm，必須回到 Spec 重新決定邊界，不得在實作中偷偷放寬。
- paired siblings 各自至少需要兩個 rail bands；兩者 source-supported terminal stations 相差 `<= 50 mm` 只代表可視為同一 terminal recovery，不代表兩條 finalized axes 必須取相同端點。每支 axis 不得超過自身來源證據，單一孤立短線也不得控制 assembly extent。
- recovery 後若無法重新建立 relation，但沒有矛盾證據，視為 recovery 證據不足並保留 base axes；若 finalized 結果改指其他 Strut／Column、同時指向多個 identity，或存在多個完整而不相容的解釋，才回報 blocking。
- 本 change 的 legacy regression 圖面確定為 Y1A 與 Y29，不另外假設存在 Y01 fixture。
