# First SDD Trial — Result Formatter Type Hints

## Goal

用一個低風險的小修改驗證新的 Agent / SDD 工作流程是否可用。

## Scope

只修改：

- `bracing_optimizer/presentation/result_formatters.py`
- 必要時補對應測試。

不修改：

- Solver。
- Domain rule。
- DXF 流程。
- UI layout。
- scoring。

## Current Observation

`result_formatters.py` 為純文字 formatter，部分公開函式目前沒有 Type Hint，例如：

- `format_result_value`
- `format_result_list`

這些函式屬於 Presentation，適合做為第一個低風險修改。

## Design

- 為 formatter 的輸入與輸出補上明確 Type Hint。
- 保持目前所有輸出字串完全相同。
- 不加入新的 formatting rule。
- 不改變 `N/A`、數字、小數與空 list 的現行行為。

## Tasks

1. 為 `format_result_value` 加入輸入 / 回傳型別。
2. 為 `format_result_list` 加入輸入 / 回傳型別。
3. 若型別需要，新增最小必要的 `typing` import。
4. 檢查既有 formatter tests / presentation tests 是否依賴相同行為。

## Verification

至少執行：

```bash
uv run python -m unittest tests.test_interface_presentation
```

若本機環境適合，再執行：

```bash
uv run python -m unittest discover -s tests
```

## Acceptance Criteria

- formatter 輸出行為不變。
- 沒有修改 Solver / Domain / Infrastructure。
- 相關測試通過。
- diff 小且容易 review。
