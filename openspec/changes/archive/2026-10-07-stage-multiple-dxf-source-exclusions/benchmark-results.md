# Multi-pending benchmark results

## 閱讀導航

- **現在必讀（P0）**：只讀「結論」與「工作次數」即可確認本 change 是否消除重複全面辨識。
- **實作前閱讀**：需要調整 benchmark 時，再讀 `tools/benchmark_dxf_source_exclusion.py` 的 `benchmark_multi()`。
- **需要時再讀**：觀測秒數僅供本機比較，不是 CI 門檻；不需據此調整 recognition、Solver 或工程規則。

## 結論

2026-10-07 以 `tools/benchmark_dxf_source_exclusion.py --multi Y05 Y29` 執行。兩筆來源由逐筆完整套用改為一次 multi-pending 套用後，Y05 與 Y29 的 convert、manual replay、commit 與 refresh 都由 2 次降為 1 次；final exclusion count 相同。

## 工作次數

| Fixture | Flow | Convert | Replay | Commit | Refresh | Final excluded sources | Revision |
|---|---|---:|---:|---:|---:|---:|---:|
| Y05 | repeated single | 2 | 2 | 2 | 2 | 30 | 3 |
| Y05 | multi-pending | 1 | 1 | 1 | 1 | 30 | 2 |
| Y29 | repeated single | 2 | 2 | 2 | 2 | 12 | 3 |
| Y29 | multi-pending | 1 | 1 | 1 | 1 | 12 | 2 |

## 本機觀測時間

| Fixture | Flow | Plan (s) | Commit (s) | Refresh projection (s) | Wall-clock (s) |
|---|---|---:|---:|---:|---:|
| Y05 | repeated single | 23.285920 | 2.728826 | 0.010508 | 26.033358 |
| Y05 | multi-pending | 10.899711 | 0.987207 | 0.005584 | 11.900604 |
| Y29 | repeated single | 12.719685 | 3.670504 | 0.000915 | 16.392473 |
| Y29 | multi-pending | 6.630489 | 2.480890 | 0.001300 | 9.117412 |

上述秒數受機器、快取及背景負載影響，只是本次觀測值；正確性與 CI assertion 以 deterministic work-count 為準。
