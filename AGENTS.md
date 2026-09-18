1. AGENTS.md
# SupportOptimizer Agent Instructions

本檔案定義 AI Agent 在本專案中的工作方式與開發規則。

詳細專案知識請依任務閱讀 `README.md` 與 `docs/` 中的相關文件。

---

## 1. General Rules

- 開發討論與說明優先使用繁體中文。
- 不要收到需求後立即修改程式。
- 除非是極小修改，否則先完成：
  1. Analyze
  2. Spec
  3. Plan
  4. Implement
  5. Verify
- 不修改與目前需求無關的程式。
- 不因為「順便整理」而進行大規模重構。
- 不把尚未驗證的假設描述成既定事實。
- 若需求與既有工程規則衝突，應先指出衝突，不可自行修改 Domain Rule。

---

## 2. Required Context

開始任務前，依工作範圍閱讀相關文件。

### 專案整體
- `README.md`

### 架構
- `docs/ARCHITECTURE.md`

### 工程領域知識
- `docs/DOMAIN.md`

### Solver / 最佳化
- `docs/SOLVER.md`

### 開發流程
- `docs/WORKFLOW.md`

### 特定功能
- `docs/specs/<feature>.md`

不要無差別讀取整個 repository。

只讀取：
- 與需求直接相關的文件
- 受影響模組
- 對應測試

---

## 3. Architecture Rules

專案主要責任如下：

### domain
`bracing_optimizer/domain/`

負責：
- 工程 Entity
- Value Object
- 工程規則
- 材料規則

不得依賴：
- GUI
- Tkinter
- Infrastructure
- Application workflow

---

### algorithms
`bracing_optimizer/algorithms/`

負責：
- Solver
- 搜尋演算法
- 候選方案生成
- 評分與最佳化核心

不得處理：
- UI
- 檔案操作
- 使用者互動

---

### application
`bracing_optimizer/application/`

負責：
- Use Case
- 流程協調
- Solver input 建立
- 驗證
- 結果處理

Application 可以呼叫 Domain 與 Algorithms，
但不要包含 GUI 細節。

---

### infrastructure
`bracing_optimizer/infrastructure/`

負責：
- DXF
- Excel
- JSON
- 檔案
- Repository
- Persistence
- 外部系統

Infrastructure 不應定義核心工程規則。

---

### presentation
`bracing_optimizer/presentation/`
以及 `main.py`

負責：
- UI
- Dialog
- Widget
- 顯示
- 使用者操作

Presentation 不應實作 Solver 演算法或複製工程規則。

---

### DXF import

`dxf_import/`

為獨立 DXF 匯入子系統。

新增功能時，應維持：
- models
- geometry
- recognition
- validation
- controller
- dialog

等責任分離。

---

## 4. Dependency Direction

原則上：

```text
Presentation
     ↓
Application
     ↓
Domain

Application
     ↓
Algorithms

Infrastructure
     ↓
Application / Domain contract

不要形成：

Domain → UI
Algorithms → UI
Domain → Infrastructure

若現有程式存在歷史例外，
不要為了單一功能順手重構整個架構。

5. Coding Rules
Python 版本依 pyproject.toml。
新增或修改公開函式時優先使用 Type Hint。
優先使用小型、單一責任函式。
避免新增大型 God Object。
不在 UI 中複製 Solver 或 Domain 規則。
工程規則不得以無名稱 magic number 隱藏在程式內。
優先使用既有常數或具名設定。
不刪除測試來讓程式通過。
不任意修改資料格式或 contract。
6. Solver Safety

修改下列檔案前：

bracing_optimizer/algorithms/support.py
bracing_optimizer/algorithms/wales.py
bracing_optimizer/algorithms/solver_search.py
bracing_optimizer/application/optimize_support_zone.py
bracing_optimizer/application/optimize_waler.py

必須先閱讀：

docs/SOLVER.md

以及相關測試。

除非需求明確要求，禁止自行修改：

Solver scoring
評分權重
Candidate Count
Beam Width
Random Seed
搜尋階段
合法性判斷
Jack 約束
材料比例政策

Solver 的「比較快」不代表「比較正確」。

工程限制優先於運算速度。

7. Development Workflow

非微小功能預設流程：

需求
↓
Analyze
↓
Spec
↓
Plan
↓
Implement
↓
Verify
↓
Review

詳細規範見：

docs/WORKFLOW.md
8. Testing

修改程式後：

先執行最接近此次修改的測試。
再依影響範圍擴大測試。
新增行為應新增對應測試。
修改架構時需執行 boundary tests。
修改 Solver 時需執行 Solver regression tests。

不得以刪除測試、降低 assertion 或忽略錯誤的方式讓測試通過。

9. Definition of Done

一項任務完成需至少符合：

功能符合 Spec。
工程規則未被破壞。
架構責任合理。
相關測試通過。
無不相關修改。
新增重要工程規則時更新 Domain 文件。
新增架構決策時更新 Architecture 文件。
修改 Solver 規則時更新 Solver 文件。
回報已知限制與尚未解決事項。