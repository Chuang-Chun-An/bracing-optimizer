# SupportOptimizer Agent Instructions

本檔案定義 AI Agent 在本專案中的開發規則。詳細專案知識以 `README.md` 與 `docs/` 內文件為準。

## 1. 回應與工作方式

- 開發討論與說明優先使用繁體中文。
- 不要收到需求後立即大範圍修改程式。
- 新功能或跨模組修改，先完成「理解 → 設計 → 計畫 → 實作 → 驗證」。
- 修改前先指出受影響模組與風險；避免修改與任務無關的檔案。
- 若需求與現有工程規則衝突，先說明衝突，不可自行改變 Domain Rule。

## 2. 必讀文件

依任務閱讀相關文件：

- 專案全貌：`README.md`
- 架構與依賴邊界：`docs/ARCHITECTURE.md`
- 工程領域知識：`docs/DOMAIN.md`
- Solver 與最佳化流程：`docs/SOLVER.md`
- 圍令細節：`docs/wales/README.md`

不要為了完成單一任務一次讀完整個 repository；先讀與任務直接相關的文件與程式。

## 3. Architecture Rules

- `bracing_optimizer/domain/` 不可依賴 GUI、Application 或外部資源。
- `bracing_optimizer/algorithms/` 負責純最佳化與搜尋邏輯，不處理 GUI。
- `bracing_optimizer/application/` 負責 use case、流程協調、驗證與輸入轉換。
- `bracing_optimizer/infrastructure/` 負責 DXF、Excel、檔案、持久化等外部資源。
- `bracing_optimizer/presentation/` 與 `main.py` 負責 UI 與互動，不應自行實作 Solver 演算法。
- `dxf_import/` 為獨立 DXF 匯入子系統；新增辨識或幾何功能時維持既有模組責任。

依賴方向原則：

```text
Presentation -> Application -> Domain
Infrastructure -> Application/Domain contracts
Application -> Algorithms/Domain
Algorithms -> Domain-level rules only when required
```

若現有程式有歷史例外，不要為了「看起來更乾淨」順手做大規模重構。

## 4. Coding Rules

- Python 版本依 `pyproject.toml`，目前為 Python >= 3.12。
- 新增或修改公開函式時，優先補上 Type Hint。
- 優先使用小而明確的函式與 dataclass，避免新增大型 god object。
- 不在 UI layer 複製 Domain / Solver 規則。
- 不使用 magic number 表達工程規則；優先引用既有常數或建立具名常數。
- 不刪除或弱化測試只為了讓變更通過。
- 不任意改變 JSON schema、DXF contract、材料規格或 Solver scoring。

## 5. Solver Safety Rules

修改下列區域前必須先閱讀 `docs/SOLVER.md` 與相關測試：

- `bracing_optimizer/algorithms/support.py`
- `bracing_optimizer/algorithms/wales.py`
- `bracing_optimizer/algorithms/solver_search.py`
- `bracing_optimizer/application/optimize_support_zone.py`
- `bracing_optimizer/application/optimize_waler.py`

除非需求明確要求，否則不要：

- 改變評分權重。
- 改變候選數、Beam Width、Random Seed 或搜尋階段政策。
- 改變合法性判斷。
- 以「速度較快」為理由犧牲既有工程限制。

## 6. Feature Workflow

新增功能時預設遵循：

1. **Analyze**：說明需求、現況、受影響模組、未知事項。
2. **Spec**：對非微小功能建立 `docs/specs/<feature>.md`，寫 Problem、Scope、Rules、Acceptance Criteria。
3. **Plan**：拆成可獨立驗證的 Tasks，列出修改檔案與測試方式。
4. **Implement**：一次處理一個 Task，避免混合無關重構。
5. **Verify**：執行最相關測試；必要時再擴大測試範圍。
6. **Report**：說明變更、測試結果、未解風險。

## 7. Testing

- 使用既有 `tests/` 作為回歸保護。
- 修改某模組時，先跑最接近的測試，再視影響範圍擴大。
- 新增行為應優先新增對應測試。
- 架構邊界變更需特別檢查 module-boundary / application-domain boundary 測試。

## 8. Definition of Done

任務完成至少需符合：

- 行為符合需求與工程規則。
- 修改範圍可解釋且無無關重構。
- 相關測試通過。
- 若新增重要 Domain Rule、Architecture Decision 或 Solver Rule，同步更新對應 `docs/`。
- 回報已知限制與後續事項，不把未驗證假設描述成完成。
