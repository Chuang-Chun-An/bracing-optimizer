# Architecture Guide

本文件提供 SupportOptimizer 的高階架構與依賴邊界。完整實作細節仍以 `README.md` 與程式碼為準。

## 1. High-level Flow

```text
CAD / DXF / Project Files
        |
        v
Infrastructure / dxf_import
        |
        v
Application Use Cases
        |
        +--> Domain Models / Rules
        |
        +--> Algorithms / Solver
        |
        v
Results / Persistence / Export
        |
        v
Presentation / main.py
```

## 2. Main Modules

### `bracing_optimizer/domain/`
純工程 entity、aggregate 與跨流程共用規則。

原則：
- 不依賴 GUI。
- 不依賴外部檔案或 CAD library。
- 不依賴 application orchestration。

### `bracing_optimizer/algorithms/`
最佳化演算法與搜尋政策。

主要包含：
- `support.py`：支撐候選生成與全域最佳化。
- `wales.py`：圍令分段最佳化。
- `solver_search.py`：搜尋政策、階段與診斷。

### `bracing_optimizer/application/`
應用流程與 use cases。

主要責任：
- 將 project data 轉成 solver input。
- 驗證工程資料。
- 呼叫 solver。
- 管理候選快取與 staged search。
- 整理結果與手動編輯流程。

### `bracing_optimizer/infrastructure/`
外部系統與 IO。

例如：
- CAD event。
- DXF result export。
- Excel export。
- Inventory repository。
- Project persistence。

### `bracing_optimizer/presentation/`
Tkinter presentation components。

原則：
- 顯示與互動。
- 不自行實作 solver 規則。
- 不直接承擔 persistence orchestration。

### `main.py`
目前仍是主要桌面應用程式入口與協調層，包含較多歷史 UI 邏輯。

新增功能時，若可放入既有 application / presentation / infrastructure 模組，不應優先繼續擴張 `main.py`。

### `dxf_import/`
DXF 匯入子系統，具有自己的 models、geometry、recognition、validation、controller、preview 與 dialog。

新增 DXF 邏輯時應先判斷它屬於：
- 幾何運算
- 物件辨識
- 候選點
- 驗證
- UI interaction

避免全部放入 `dialog.py`。

## 3. Dependency Direction

期望方向：

```text
Presentation ---> Application ---> Domain
                    |
                    +-----------> Algorithms

Infrastructure ---> Application / Domain contracts
```

重要限制：
- Domain 不認識 Tkinter、Matplotlib、ezdxf、檔案系統。
- Algorithms 不直接操作 UI。
- Presentation 不複製 solver scoring 或 legality rules。

## 4. Where New Code Should Go

新增功能時可用以下判斷：

- 「工程上什麼是合法？」→ Domain。
- 「如何搜尋最佳解？」→ Algorithms。
- 「何時呼叫哪些步驟？」→ Application。
- 「如何讀 DXF / 寫 Excel / 存 JSON？」→ Infrastructure 或 `dxf_import/`。
- 「按鈕、Dialog、顯示文字？」→ Presentation / `main.py`。

## 5. Known Structural Risks

目前需特別留意：

- `main.py` 很大，容易吸收新的 business logic。
- `dxf_import/dialog.py` 很大，新增 DXF 功能時需避免進一步集中責任。
- Solver 模組含大量既有工程假設，不適合順手重構。
- README 已承擔大量詳細文件；新文件應避免複製造成版本漂移。

## 6. Architectural Change Rule

若需求需要跨越既有邊界，先在 spec 中說明：

1. 現有責任在哪裡。
2. 為何現有邊界不足。
3. 新責任應放哪裡。
4. 是否需要 migration / compatibility。
5. 哪些 tests 能防止退化。

不要只因為「Clean Architecture 比較漂亮」而進行無需求驅動的大規模搬移。
