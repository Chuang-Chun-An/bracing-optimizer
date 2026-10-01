# Proposal

## 閱讀導航

### P0｜現在必讀

1. 本文件的「快速摘要」、「現況與目標」與「不變事項」。
2. `specs/bim-block-brace-recognition/spec.md` 的「斜切封閉 Brace 外框」Requirement 與 Y29 `71A` scenarios。
3. `design.md` 的「Decision 1：以封閉拓撲取代 rail 等長覆蓋」與「Decision 2：端面交點界定來源軸」。

### P1｜實作前閱讀

1. `openspec/specs/bim-block-brace-recognition/spec.md`：既有 body width、center authority、safe failure requirements。
2. `openspec/specs/brace-axis-waler-extension/spec.md`：可靠來源軸建立後的 direct／outward-ray Waler connection contract。
3. `docs/DOMAIN.md` 的「4.10 Brace 本體寬度與中心 authority」及 `docs/ARCHITECTURE.md` 的 DXF recognition stage order。

### P2｜需要時再讀

1. `tests/test_dxf_bim_block_recognition.py` 的 closed-outline、斜端面與 Y29 characterization tests。
2. `tests/test_dxf_waler_contact_face_recognition.py` 的 Brace terminal／contact-face tests。
3. `docs/WORKFLOW.md` 的 DXF Review lifecycle；只有調整 Review 顯示或重播時才需要。

本次可以先跳過 Solver、材料最佳化、CornerBrace repair、Double Support 與 Joist specs；本 change 不修改這些能力。

## 快速摘要

- Y29 `71A` 是兩端依圍令斜切、但拓撲完整的封閉 Brace 外框；目前因兩條平行 body rails 長度不同、短側只覆蓋整體投影約 `77.36%`，未通過共用的 `0.8` coverage gate。
- 本 change 不把全域門檻降為 `0.7`；完整、無分支、可唯一解讀的封閉外框將以拓撲證明完整性，開放 rail pair 與 fragmented evidence 仍保留既有 `0.8` gate。
- 斜切外框的 source-supported recognition axis 端點將由中心 supporting line 與兩端有限切面求交，不再取所有頂點的最大／最小 longitudinal projection。
- 既有 `> 250 mm` Brace 寬度 hard gate、`<= 600 mm` 最大寬度、Waler identity ambiguity、600 mm 軸向延伸與 formal Brace 原子提交規則全部不變。

## 現況與目標

| | 現況（Before） | 目標（After） |
|---|---|---|
| 完整性 | 封閉斜切外框的兩條 body rails 仍各自必須覆蓋整體 longitudinal extent 至少 80% | 唯一、封閉、無分支的 body topology 可證明 rails 與兩端切面共同形成完整構件 |
| 來源軸端點 | 由所有外框頂點的最小／最大軸向投影決定，斜切時可能超出實體端面 | 由 body midline 與兩個有限 terminal cut segments 的交點決定 |
| 寬度 | 使用兩側 outer supporting lines 的正交距離 | 維持相同規則；不得以斜切端面長度取代寬度 |
| 其他來源 | 降低共用門檻會讓多個原本不可靠來源進入後續流程 | 不改全域門檻；只讓具完整 topology 的斜切 closed outline 使用專屬資格判定 |
| Waler 多解 | 重疊 Waler identities 保持 ambiguous | 維持相同安全行為，不因斜切外框辨識成功而任選 Waler |

「terminal cut」指封閉 Brace 外框在構件起端或終端、連接兩條 longitudinal body rails 的有限邊；它可因圍令接觸方向而斜切，不代表 Brace 本體寬度。

## 主要流程

```text
Brace-role closed outline
  → 驗證單一、封閉、無分支 boundary
  → 唯一找出一對平行 outer body rails
  → 驗證其餘邊形成兩個完整 terminal cuts
  → 以 rail supporting-line separation 量測 body width
  → 以兩 rail 的正中 supporting line 建立方向與橫向中心
  → 以 midline × terminal cuts 的有限交點界定 source axis
  → 進入既有 terminal evidence → Waler contact face → member verdict 流程
```

## 不變事項

- Brace body width 仍必須嚴格 `> 250.0 mm` 且不大於既有最大 component width。
- 開放平行線、fragmented root、whole-root envelope 與 local rail-pair fallback 的 `minimum_projection_overlap_ratio = 0.8` 不變。
- 不跨 root handle 或獨立 source scope 拼接 Brace；不同來源是否為重複構件仍由既有 deduplication 與 source identity 規則處理。
- Brace 必須兩端唯一連接不同有限 Waler；重疊 Waler identities 不得依 ID、handle、輸入順序或微小浮點差任選。
- 既有 direct connection tolerance、最大 600 mm outward extension、Waler contact-face finalization、Review lifecycle、Project schema 與 Solver behavior 不變。
- CornerBrace 使用獨立 body-rail 與 relationship rules，不納入本 change。

## Why

目前 closed-outline Brace 將 rail 對整體投影的 `0.8` coverage 同時用作 body 完整性判定，導致像 Y29 `71A` 這種兩側 rails 平行、寬度可靠且兩端完整封閉，但因圍令接觸面而斜切的合法構件被標記為 `BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE`。直接降低共用門檻會使其他不可靠來源進入辨識，且仍會以錯誤的 projection extrema 建立斜切端點，因此需要以封閉拓撲與有限端面交點表達這類幾何。

## What Changes

- 修改一般及 component-like Brace closed-outline eligibility：完整、無分支且只有一個可靠 body interpretation 的封閉外框，可由 topology 證明完整 extent，不要求兩條 rail 各自達到共用 `0.8` coverage。
- 定義斜切 terminal cuts 的資格：必須各自有限連接兩側 outer rails，並與唯一 body midline 形成合法有限交點。
- 將 closed skew-cut outline 的 source-supported axis 端點定義為 body midline 與兩個 terminal cuts 的交點；不得以 bounding projection extrema 或為碰觸 Waler 而任意外插。
- 保留 outer supporting-line separation 作為 body width 唯一量測來源，端面長度與斜率不得改變寬度 hard gate。
- 對開放、破損、自交、分支、具有多組不等價 rail interpretations 或無法唯一建立兩端切面的來源維持 blocking failure／ambiguity。
- 加入 Y29 `71A`、一般矩形、反轉 traversal、不完整輪廓、多解外框與既有 Y29／Y05 Brace regression coverage。
- 在實作驗證後更新 `docs/DOMAIN.md`，記錄斜切 closed outline 的長期工程語意；不提前改寫現行 truth。

### In Scope

- Brace-role `LWPOLYLINE`／`POLYLINE` closed outline，以及 root `INSERT` 內可驗證的單一 closed body topology。
- Body rail、terminal cut、source-supported center axis、width measurement、deterministic failure／ambiguity。
- 既有 terminal-to-Waler 流程對新來源軸的相容性與 Y29 回歸驗證。

### Out of Scope

- 降低全域 `minimum_projection_overlap_ratio`。
- 自動消解重疊 Waler identity，例如 Y29 `69F` 與 `720`。
- 改變 Waler contact-face 選擇、Brace 600 mm outward extension 或 Project／Solver contract。
- CornerBrace、Strut、Waler、Column、Beam、材料辨識與 Solver 演算法。
- 無關的 DXF recognition 重構、命名整理或效能最佳化。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `bim-block-brace-recognition`：修改 closed body outline 的完整性與 source-supported extent requirements，使唯一且完整的斜切外框以 topology／terminal cuts 建立可靠 body axis，同時保留既有寬度 hard gate、authority、safe-failure 與 connection boundary。

## Impact

- 主要受影響程式：`dxf_import/block_member_recognition.py`、`dxf_import/recognition.py`；只有在既有 terminal facts 缺少必要 provenance 時，才擴充 `dxf_import/waler_contact_face.py` 的資料傳遞，不改其 identity selection 規則。
- 主要受影響測試：`tests/test_dxf_bim_block_recognition.py`、`tests/test_dxf_waler_contact_face_recognition.py`，以及 Y29 fixture regression。
- 長期文件：完成實作與驗證後更新 `docs/DOMAIN.md`；預期不改變 architecture、Solver 或 Project schema truth。
- 外部 API、持久化格式、第三方相依套件與 GUI 操作不變。

## 已決定的範圍邊界與重新評估條件

- 本 change 不重新定義 `44E`／`45C` 的工程 identity，也不修改既有 deduplication contract；實作只驗證新增 closed-topology 路徑不會因共用門檻放寬而意外改變 source-scope 行為。若日後確認既有 deduplication 本身不符合工程 identity，應另立 change 處理。
- 單一 closed primitive 與可由既有 endpoint tolerance 唯一重建的無分支 closed LINE traversal 均可使用同一 topology contract；不得跨 gap、遮蔽或不同 source scope 推導 terminal cuts。若實際資料需要這類推導，必須另行提案，不得在實作時擴張本 change。
