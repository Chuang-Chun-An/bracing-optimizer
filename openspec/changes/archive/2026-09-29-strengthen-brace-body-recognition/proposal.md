# Proposal

## 閱讀導航

### P0｜現在必讀

- 本文件「快速摘要」至「不變事項」：先理解問題、目標流程與相容邊界。
- 本文件「In Scope／Out of Scope」：確認本 change 只調整自動 Brace 辨識，不改 Waler 連接、Solver 或人工決策。
- `specs/bim-block-brace-recognition/spec.md`：「component-like body evidence」、「Brace 實體寬度 hard gate」與「Brace 中心 authority」：實作與驗收的正式行為。

### P1｜實作前閱讀

- `design.md`：候選分層、寬度 gate、fallback terminal outcome 與 diagnostics 的技術方案。
- 主規格 `openspec/specs/bim-block-brace-recognition/spec.md`：「Formal Brace axis SHALL represent the whole source-supported member」與「Brace recognition outcome SHALL fail safely and deterministically」。
- `dxf_import/block_member_recognition.py`、`dxf_import/recognition.py` 及 `tests/test_dxf_bim_block_recognition.py` 中的 Brace recognition 路徑與 Y05 fixtures。

### P2｜需要時再讀

- `openspec/specs/bim-block-member-recognition/spec.md` 的 Strut center-authority 規則：只有重用共同幾何方法或確認 Strut 不受影響時再讀。
- `openspec/specs/dxf-corner-brace-occluded-rail-recognition/spec.md`：只在核對既有 CornerBrace `> 250 mm` 規則時閱讀；本 change 不修改 CornerBrace。
- `openspec/specs/brace-axis-waler-extension/spec.md`：只有測試 Brace 端點連接 regression 時再讀；本 change 不修改 600 mm 軸向延伸。
- 其他 Solver、Waler、Joist 與 CornerBrace repair specs 可先跳過。

## 快速摘要

- Y05 B8 顯示現行 Brace 圖塊可能以約 `160.015 mm` 的局部外緣／內部細節線配對取代 `300 mm` 實體外包絡，造成中心軸橫向偏移。
- 自動 Brace 候選若能從來源幾何量得實體寬度，該寬度必須嚴格 `> 250.0 mm`；`= 250.0 mm` 或更小皆不合法。
- component-like 不是只要看見兩條平行線就成立；同一 Brace root 的 whole-source geometry 必須共同支持實體 body、主要 longitudinal corridor、可靠 terminal extent 與 body envelope。
- 系統先列舉各 authority tier 候選並逐一完成來源支持、完整性、可靠寬度與 `> 250.0 mm` gate，再從仍有合法候選的最高 tier 判斷唯一中心；不合法的高 tier 不阻擋合法 lower tier，但最高合法 tier 多解時不得降層。
- 純單 LINE／明確中心線的寬度是未知而非不合格，人工指定工程線也維持既有決策優先權；本 change 不改 Architecture、Project schema、Solver 或 Brace-to-Waler connection contract。

## 現況與目標

| 主題 | Before｜現況 | After｜目標 |
|---|---|---|
| Brace 來源分類 | Brace 圖層上的 root `INSERT` 先嘗試 component-like route；不是事先由 BIM metadata 分類，但 body evidence 的成立條件尚未寫清楚 | 保留相同 role／root source boundary；只有 whole-source geometry 足以支持實體 body、主要 corridor、可靠 extent 與 envelope 時才成立 component-like，局部 pair／detail 不足以單獨成立 |
| 中心候選 | fragment rail pair 可先成功並依 evidence ratio 勝出，未完整套用 Strut 已有的 whole-root center authority | 分別列舉完整外框、whole-root 外包絡、局部 rail pair；每個候選先驗證完整性與寬度，再由最高合法 tier 決定中心 |
| Closed outline 寬度 | 「外框寬度」可能被誤解為 bounding box、最遠點或端板尺寸 | 只使用工程軸相對兩側、共同支持主要 longitudinal corridor 的 outer supporting sides 之正交 separation |
| 實測寬度 | 一般與 component-like Brace 只受既有最小幾何距離及最大 `600 mm` eligibility 約束，約 `160 mm` 也可能成立 | 所有自動 body-derived Brace 候選的實測正交寬度必須嚴格 `> 250.0 mm` |
| 過窄候選 | 可能成為正式 Brace，或特殊 route 不適用後由一般 route 採用 | 必須拒絕；已具 Brace body evidence 的來源不得藉一般 fallback 繞過 hard gate |
| 寬度未知 | 純中心線保存 `source_width = 0` 並可依既有流程成立 | 維持相容；未知不等於 `<= 250 mm`，不因本 change 單獨阻擋 |

## 主要流程

```text
Brace-role root source
    |
    +-- whole-source geometry 不足以支持 component-like body
    |       `-- not_applicable；依既有規則交回 general Brace recognition
    |
    `-- whole-source geometry 已支持 component-like body
            |
            +-- 分別列舉 TOPOLOGY／WHOLE_ROOT_ENVELOPE／LOCAL_RAIL_PAIR
            +-- 每個候選先驗證：完整性、whole-source support、可靠 extent、
            |                    supporting-side width、width > 250.0 mm
            +-- 移除不合法候選，再找仍有合法候選的最高 authority tier
                    |
                    +-- 唯一 normalized axis --> recognized
                    +-- 多個不等價完整 axes --> blocking ambiguous，不降層
                    `-- 全部 tiers 無合法候選 --> blocking failed，不回 general route

純中心線、無實體 body envelope --> width unknown，維持既有中心線辨識
```

## 不變事項

- Brace role 仍由使用者指定圖層與最外層 root source identity 決定，不使用圖塊名稱或 BIM metadata 猜測 role。
- 單一局部平行線組、短 detail、branch、flange／web 內部線、孔洞邊或零散 fragments，不足以單獨把 root 分類成 component-like。
- 純單 LINE／明確中心線、人工指定工程線與既有 manual endpoint replay 不因未知寬度被拒絕。
- Strut、CornerBrace、Waler、Beam／Joist、Column 的辨識規則不變。
- Brace direct connection 的 `250 mm` tolerance 與 axis extension 的 `600 mm` 上限不變；它們與本 change 的實體寬度 hard gate 是不同語意。
- Project row、persistence schema、Solver input、scoring 與搜尋參數不變。

## Why

現行 Brace component-like recognition 可能把外緣與 H 型鋼內部細節線配成局部窄 rail pair，再以局部 evidence 分數選成正式中心。Y05 B8 因此以約 `160.015 mm` 候選取代來源幾何支持的 `300 mm` 實體外包絡，造成約 `77.5 mm` 的中心偏移；系統需要以完整來源幾何與已確認的最小材料寬度排除這類假中心。

## What Changes

- 新增 Brace 實體寬度 Engineering Hard Constraint：所有可由自動來源幾何量得 body width 的 Brace 候選，寬度 MUST 嚴格 `> 250.0 mm`；`= 250.0 mm` 與 `< 250.0 mm` 均拒絕。
- 明定 component-like body evidence：同一 Brace-role root `INSERT` 的 whole-source geometry 必須足以支持實體 body／外包絡、主要 longitudinal corridor 與可靠 terminal extent；局部 pair、detail、branch、內部線、孔洞邊或零散 fragments 不得單獨成立分類。
- 對 component-like Brace root `INSERT` 建立明確 center-authority 順序：完整且可驗證的外框、合格 whole-root outer-envelope、最後才是 local rail-pair fallback。各 tier 必須先列舉全部候選並逐一完成完整性、whole-source support、可靠 extent、寬度量測與 hard gate，才可成為「合法 authority tier」。
- 系統從仍有合法候選的最高 tier 進行等價合併與唯一性判斷：高 tier 只有不合法候選時繼續評估 lower tier；最高合法 tier 多解時回報 ambiguity，不得降層；唯一合法候選成立後，lower tier 不得以分數、長度或 evidence ratio 覆寫。
- Closed body outline 的寬度只可取自工程軸兩側、共同支持主要 longitudinal corridor 的 outer supporting sides 之正交 separation；不得使用 bounding box、最遠頂點、斜端板、突出 detail、內部線或 axial gap 補足。
- 已具 Brace body evidence但全部候選過窄、寬度無法可靠決定或中心不唯一時，保留 exact source identity 並產生 blocking failure／ambiguity；不得退回一般 outline／parallel-pair route 繞過限制。
- 一般自動 MLINE、closed outline 與 parallel edges 若提供可量測 body width，同樣適用 `> 250.0 mm`；純單 LINE／明確中心線因寬度未知而保持既有相容行為。
- 增加 Y05 B8／root `DD9` regression：拒絕約 `160.015 mm` 局部 pair，採用約 `300 mm` whole-root 外包絡中心，並保護其他 Y05 Brace、一般 Y1A／Y29 Brace 與 Strut behavior。
- **BREAKING**：過去可由自動外框、MLINE 或平行邊辨識成功、但實測 body width `<= 250.0 mm` 的 Brace 將改為不合法；這是刻意的工程 hard-gate 修正。

## In Scope

- Brace component-like body evidence 的分類邊界，以及自動 body geometry 的 supporting-side 寬度量測、hard gate、center authority、ambiguity 與 failure diagnostics。
- root `INSERT` component-like route 與一般 MLINE／closed outline／parallel-pair route 的一致 gate 行為。
- Y05 B8 真實案例、component-like classification 正反例、tier 先 gate 後 selection、closed-outline supporting-side 量測、`250.0 mm` 等號邊界、`>250 mm` 合法邊界與相容性 regression。
- 實作完成後更新 `docs/DOMAIN.md`，將 Brace `> 250.0 mm` 記為 Engineering Hard Constraint。

## Out of Scope

- 以圖塊名稱、BIM family 名稱、庫存或材料規格反推 Brace 寬度。
- 要求純中心線／單 LINE 證明材料寬度，或為其自動猜測寬度。
- 修改人工指定工程線、manual endpoint、source exclusion／restore、Pause／Resume 或 Review commit semantics。
- 修改 Strut center authority、CornerBrace `>250 mm` 規則、Waler contact face、Brace-to-Waler direct tolerance 或 600 mm extension。
- 修改 Solver、Project schema、persistence 或 export contract。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `bim-block-brace-recognition`：補充所有可量得實體寬度的自動 Brace 候選之 `> 250.0 mm` hard gate，並把 component-like Brace 的 center authority 明確改為完整外框、whole-root 外包絡、局部 rail pair 的分層程序與安全 failure semantics。

## Impact

- **Infrastructure／DXF recognition**：`dxf_import/block_member_recognition.py`、`dxf_import/recognition.py`、`dxf_import/models.py` 的具名 Brace width boundary、候選列舉與 route terminal outcome。
- **Diagnostics／Review projection**：沿用既有 `ValidationMessage`、`ProblemRecord` 與 Review lifecycle，新增或細化可定位的過窄／寬度不可靠診斷；不建立第二份幾何 truth。
- **Tests**：`tests/test_dxf_bim_block_recognition.py` 與最接近一般 Brace import 的 focused tests，包含 Y05 `DD9`、250 mm 邊界、fallback bypass 與一般資產 regression。
- **Long-term truth**：`docs/DOMAIN.md` 需在實作完成後新增 Brace body width hard constraint；Architecture、Solver 與 Workflow truth 預期不變。
- **Dependencies／schema**：不新增第三方依賴，不修改 Project 或 persistence schema。

## 尚未決定事項

無。若未來確認存在合法正式 Brace 的實體寬度 `<= 250.0 mm`，必須另立需求重新評估 hard gate；不得在實作中自行放寬本 change 已確認的等號邊界。
