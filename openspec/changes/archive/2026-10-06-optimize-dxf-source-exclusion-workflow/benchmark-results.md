# Benchmark：DXF 單筆來源排除

## 閱讀導航

- **現在必讀**：下方結果表與「正確性／工作次數」。這是 2026-10-06 在目前開發機器上的一次非 CI threshold 實測。
- **需要重跑時**：執行 `.\.venv\Scripts\python.exe tools\benchmark_dxf_source_exclusion.py Y05 Y29`。
- **可先跳過**：絕對秒數不是 SLA；不同機器、檔案 cache 與 instrumentation 會改變 wall-clock。

## 結果

| Case／操作 | Plan | Convert | Manual replay | Final problem＋ReviewItem | Commit | Refresh projection | Debug serialization |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Y05／排除 BM29（source identity `beam:E91`） | 8.919105 s | 3.685426 s | 4.130792 s | 0.054584 s | 1.337860 s | 0.003391 s | 0.977978 s |
| Y29／排除 W11（source identity `waler:58D`） | 3.424289 s | 2.465772 s | 0.000075 s | 0.010518 s | 1.310017 s | 0.000913 s | 1.812063 s |

Y05 的 11 筆 CornerBrace repair 全部為 `preserved`，`needs_review=0`、`disabled=0`。Y29 沒有 CornerBrace repair；被排除 Waler 的一筆人工正式工程線正確成為 `disabled`。

Debug payload 分別約 16.62 MB（Y05）與 21.32 MB（Y29）。一般 commit 隱藏 developer panel 時不執行這段序列化；表中數字是明確量測延後工作的成本。

## 正確性／工作次數

| 計數 | Y05 | Y29 |
| --- | ---: | ---: |
| Full importer／recognition | 1 | 1 |
| Manual replay | 1 | 1 |
| `build_problem_records` | 1 | 1 |
| `build_review_items` | 1 | 1 |
| Candidate local validation | 344 | 0 |
| Candidate full validation（production） | 0 | 0 |
| Candidate-local connection build | 344 | 0 |
| 每次 candidate-local connection 的最大 CornerBrace 數 | 1 | 0 |
| Commit revision 增量 | 1 | 1 |

Y05 的 344 個候選仍逐一執行 validation，但每次 connection build 只含 temporary candidate；沒有省略候選、repair 或 final validation。另由 fixture regression 以舊 full-field validator 作 oracle，比較 optimized 與 canonical plan 的 members、connections、messages、provenance、problems、ReviewItems、confirmations、candidate projection、completion truth 與 replay report，結果完全相同。

相較 design Context 記錄的 warm-cache baseline（11 次 planning 約 14.358 秒），本次 manual replay 為 4.131 秒，約少 10.227 秒（約 71%）。這是單次觀測，不作 CI 時間門檻；穩定 gate 是上述工作次數與 differential equivalence。
