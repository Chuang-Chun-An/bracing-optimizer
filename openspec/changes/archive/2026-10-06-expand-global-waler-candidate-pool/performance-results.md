# Global Waler candidate-pool 效能量測

## 閱讀導航

- **現在必讀（P0）**：本頁「結論與人工決策 gate」及「量測結果」。
- **實作前閱讀**：`design.md` 的 Decision 5、`tasks.md` 的 Task 5.3。
- **需要時再讀**：`proposal.md` 的取捨與 `specs/global-waler-candidate-pool/spec.md` 的 diagnostics requirement；其餘 artifact 可先跳過。

## 結論與人工決策 gate

量測已完成，並依 Task 5.3 暫停等待人工決策。使用者於 2026-10-06 明確判定效能結果可接受，授權繼續 Task Group 6／7；本 change 未加入 Top N、beam pruning 或 state truncation。

三個案例均完整進入 Exact DP，且 Expanded profile 都選中 rank 6 以上候選。Y05 的 DP transitions 從 88 增至 4,136,096，max active states 從 12 增至 110,421；Y29 分別從 267 增至 1,934,248、從 77 增至 59,078；Y1A 分別從 19 增至 165,925、從 6 增至 14,413。

Y05 的前後全場比例相同；Y29 與 Y1A 的 Expanded 結果都更接近 20/50/30。這些數據已作為上述人工決策依據；接受不改變候選保留或 Exact DP objective。

## 量測方法

- Y05、Y29：直接載入 `project_cases/Y05車站第一層支撐/project.json` 與 `project_cases/Y29車站第一層支撐/project.json` 的 `input_data`，保留人工修補後的幾何、接點、材料規格與庫存；沒有重新執行 DXF recognition。
- 為使效能測試可完整配置，量測工具只在記憶體內把 gap 大於 200 mm 的 non-RC Waler 修正至最近的 500 mm 整數長度，並沿原軸方向同步調整 endpoint；沒有覆寫 saved project。
- Y05 測試修補：W2/W3/W5/W6 `16,950→17,000`、W8/W10 `44,390→44,500`、W9 `17,400→17,500`。14 支 Waler 中有 4 支 RC 依既有規則排除，10 支進入 Global。
- Y29 測試修補：W4 `22,400→22,500`、W11 `4,865→5,000`、W13 `17,249→17,000`、W14 `24,400→24,500`、W15 `53,317→53,500`。15 支全部進入 Global。
- Y1A：repository 沒有對應 saved project，使用 `tests/sample_dxf_assets.py` 指向的正式 DXF、既有 default layer mapping，並套用 `H400x400`、1,000–10,000 mm 每 500 mm 一種的量測材料；數量 999。
- 三者目標比例皆為 Short/Mid/Long = 20/50/30。
- 修改前：Global orchestration 不變，但 local retention 強制使用 `SINGLE_TOP_5`。
- 修改後：正式 `GLOBAL_FINAL_POPULATION`。
- 兩個 profile 各自完整執行 staged GA 與 Global flow；沒有重播 local 結果、縮小 population／generations、改 seed 或加入截斷。
- 執行命令：`.venv\Scripts\python.exe tools\measure_global_waler_candidate_pool.py <Y05|Y29|Y1A>`。
- 環境：Windows、Python 3.12、單一前景程序；執行時間為單次 wall-clock，未做多次平均。

## 量測結果

| Fixture | Profile | 執行時間（秒） | 送入 DP 候選總數 | transition_count | max_active_state_count | Global 結果 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Y05 repaired saved project | Top 5 | 101.17 | 16 | 88 | 12 | 成功 |
| Y05 repaired saved project | Expanded | 143.57 | 344 | 4,136,096 | 110,421 | 成功 |
| Y29 repaired saved project | Top 5 | 216.06 | 25 | 267 | 77 | 成功 |
| Y29 repaired saved project | Expanded | 301.38 | 228 | 1,934,248 | 59,078 | 成功 |
| Y1A | Top 5 | 142.80 | 8 | 19 | 6 | 成功 |
| Y1A | Expanded | 182.55 | 220 | 165,925 | 14,413 | 成功 |

## 每支 Waler 候選數（material-signature merge 前）

下表是 local 跨 stage 完整 solution merge 後、material-signature merge 前的 raw candidate
counts；「送入 DP 候選總數」則是 material-signature merge 後的代表候選總數。兩個邊界不混用。

### Y05 repaired saved project

| Waler | Top 5 | Expanded | 差值 |
| --- | ---: | ---: | ---: |
| W1 | 5 | 26 | +21 |
| W2 | 5 | 15 | +10 |
| W3 | 5 | 15 | +10 |
| W4 | 5 | 26 | +21 |
| W5 | 5 | 20 | +15 |
| W6 | 5 | 20 | +15 |
| W7 | 5 | 294 | +289 |
| W8 | 5 | 98 | +93 |
| W9 | 5 | 37 | +32 |
| W10 | 5 | 113 | +108 |

Expanded 候選數最多前三支：W7 294、W10 113、W8 98。

### Y29 repaired saved project

| Waler | Top 5 | Expanded | 差值 |
| --- | ---: | ---: | ---: |
| W1 | 1 | 1 | 0 |
| W2 | 1 | 1 | 0 |
| W3 | 1 | 1 | 0 |
| W4 | 5 | 25 | +20 |
| W5 | 5 | 12 | +7 |
| W6 | 1 | 1 | 0 |
| W7 | 5 | 7 | +2 |
| W8 | 1 | 1 | 0 |
| W9 | 5 | 13 | +8 |
| W10 | 5 | 275 | +270 |
| W11 | 1 | 1 | 0 |
| W12 | 5 | 20 | +15 |
| W13 | 5 | 24 | +19 |
| W14 | 5 | 16 | +11 |
| W15 | 5 | 263 | +258 |

Expanded 候選數最多前三支：W10 275、W15 263、W4 25。

### Y1A

| Waler | Top 5 | Expanded | 差值 |
| --- | ---: | ---: | ---: |
| W1 | 5 | 43 | +38 |
| W2 | 5 | 120 | +115 |
| W3 | 5 | 120 | +115 |
| W4 | 5 | 43 | +38 |

Expanded 候選數最多前三支：W2 120、W3 120、W1 43；同數時依既有 `waler_order`。

## Global 選出結果差異

三個案例均以每支 Waler 的完整 selected-plan signature 比較，不只比較 local rank。

### Y05 repaired saved project

- selected-plan signature 不同：W5、W6。
- Expanded 選中 W6 rank 6；其餘最高選中 rank 為 W9 rank 5。
- 兩組方案的 Out count、Out distance、ratio deviation 與 changed-Waler count 都相同：
  `0`、`0.0`、`0.0`、`2`。差異發生在下一個 objective 項目 total local regret。
- Top 5 組合讓 W5 採 rank 4（regret `27,000`）、W6 採 rank 1（regret `0`）；
  Expanded 組合改為 W5 rank 1（regret `0`）、W6 rank 6（regret `21,000`）。W9 在兩者皆為
  rank 5（regret `20,000`），其餘皆為 `0`，因此 total local regret 由 `47,000` 降為
  `41,000`。Exact DP 在比例與前述 objective 項目完全相同時，依既有 lexicographic objective
  選擇 regret 較低的 Expanded 組合；不是因為 rank 6 本身較優先，也沒有改變 DP objective。
- 對應材料 signature：Top 5 為 W5 `(1, 2, 0, 0, 0)`、W6 `(0, 1, 1, 0, 0)`；
  Expanded 將兩者對調為 W5 `(0, 1, 1, 0, 0)`、W6 `(1, 2, 0, 0, 0)`，所以全場
  Short／Mid／Long／Out counts 保持 `8／20／12／0`。

| Profile | Short | Mid | Long | Out |
| --- | ---: | ---: | ---: | ---: |
| Top 5 | 8 / 20.00% | 20 / 50.00% | 12 / 30.00% | 0 / 0.00% |
| Expanded | 8 / 20.00% | 20 / 50.00% | 12 / 30.00% | 0 / 0.00% |

### Y29 repaired saved project

- selected-plan signature 不同：W7、W10、W14、W15。
- Expanded 選中 W10 rank 35、W14 rank 7。

| Profile | Short | Mid | Long | Out |
| --- | ---: | ---: | ---: | ---: |
| Top 5 | 8 / 20.51% | 20 / 51.28% | 11 / 28.21% | 0 / 0.00% |
| Expanded | 8 / 20.00% | 20 / 50.00% | 12 / 30.00% | 0 / 0.00% |

### Y1A

- selected-plan signature 不同：W2、W3、W4。
- Expanded 選中 W2/W3 rank 8、W4 rank 9。

| Profile | Short | Mid | Long | Out |
| --- | ---: | ---: | ---: | ---: |
| Top 5 | 6 / 18.75% | 16 / 50.00% | 10 / 31.25% | 0 / 0.00% |
| Expanded | 7 / 20.59% | 17 / 50.00% | 10 / 29.41% | 0 / 0.00% |

## 原始 DXF「無解」原因覆核（僅回報）

此處只覆核先前以原始 DXF 直接建立 input 時的長度條件，不修改 saved project、DXF、合法性規則或
候選生成。

- **Y05 W2：是。** required length `16,950 mm`，可由 500 mm 標準料組成且不超長的最大 steel
  total 為 `16,500 mm`，短差 `450 mm`，超過允許的 `200 mm` 閉區間，因此沒有合法方案。
- **Y29 W5：否。** required length `12,200 mm`，steel total `12,000 mm`，短差恰為
  `200 mm`，仍在閉區間內。以原始 input 單獨重跑可取得 `120` 個合法候選、`13` 個唯一合法
  signature，第一名 segments 為 `[5,500, 6,500]`。因此 W5 本身可解；先前整場 direct-DXF
  測試把 W5 列為失敗，不能歸因於長度短差超過 200 mm。舊量測沒有保存該次 candidate-building
  exception 的完整內容，無法再把原因縮小到更精確的分支。
