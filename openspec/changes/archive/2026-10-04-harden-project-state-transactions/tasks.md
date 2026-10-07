# Tasks

## 實作前閱讀

- 第 1 組先讀 proposal 的 failure boundaries、design Decision 1 與「main.py commit surface 盤點」、spec 全部 Requirements。
- 第 2 組先讀 design Decision 1、6 與 spec「Projection 失敗後禁止在 stale 畫面修改資料」。
- 第 3 組先讀 design Decision 2～3，以及 `docs/WORKFLOW.md` 的 load、result lifecycle、manual editing、dirty state；Material Spec 另讀 archived `move-material-spec-editing-to-application` Decision 3。
- 第 4 組先讀 design Decision 4 與 CAD ACK／duplicate-event scenarios；第 5 組先讀 Decision 5 與 Project persistence rollback tests。
- 第 6～7 組只在各 transaction targeted tests 通過後執行。

## 1. 建立 fault-injection 與 commit-surface 基準

- [x] 1.1 在 Project load、Support／Single result adoption、Material Spec、CAD ACK 與 managed DXF save rollback 既有 tests 中加入 stage 尾端、commit 邊界與 projection 開頭的 failure injection 基準，驗證 Project model、ProjectResultModel、metadata、cache、DXF status、dirty、current path、projection guard 與 recovery file 的完整狀態。
- [x] 1.2 建立共用 assertion helper 比較正式 state snapshot，並以刻意製造的新舊混合 state 驗證 helper 能抓到 model／results／metadata／cache／DXF status／dirty／current path 不一致。
- [x] 1.3 盤點並鎖定 `main.py` 受影響入口的 property setter、custom `__setattr__`、Tk trace、callback、method call 與 collection mutation；每個入口須在 commit 中仍存在的 callable boundary 注入例外。若實作後沒有可注入點，改以 spy／static inspection test 證明 commit 只含 plain direct assignments、目標欄位無 setter／trace，且所有可能拋錯的工作均位於 stage 或 projection。

## 2. 建立 side-effect-free commit 與 projection recovery

- [x] 2.1 在 Application／Presentation boundary 加入小型 typed mutation outcomes 與 plain-reference commit helper；stage 必須預先建立 Project／Result models、cache replacements、metadata、dirty value／reason 與 DXF state，commit 不得呼叫 property setter、Tk variable、callback、filesystem、`clear()`／`append()` 或其他 collection mutation；以 focused tests 驗證 stage failure 保留舊 state，並執行 Task 1.3 的 fault-injection／不可拋錯證據。
- [x] 2.2 在 `main.py` 加入 `projection_stale` editing guard 與使用者可執行的完整重新投影入口，重建五張輸入表、Results Tree、材料摘要、Preview、Project／DXF／CAD status、selection 與 action state；以 tests 驗證任一步驟失敗都維持鎖定且不修改 committed state，全部成功才解除鎖定，現有「更新圖面」與「重新顯示狀態」不得被誤當完整恢復。

## 3. 收斂 load、result 與 Material Spec transaction

- [x] 3.1 重整 Project load adoption，使解析、驗證、results、DXF report、path、全新 cache objects、`dirty=False` 與空 dirty reason 在 `main.py` swap 前準備完成；測試 pre-commit failure 舊 Project 不變，post-commit projection failure 保留完整新 Project、維持 clean 並啟用 projection guard，完整重新投影成功後解除鎖定。
- [x] 3.2 將 Support 與 Single Waler result adoption 改為先建立完整 result／summary／calculated metadata／dirty outcome 再以 plain references commit；不得使用 `result_items`、`project_result`、`last_calculated_time` setters 或修改既有 `ProjectResultModel`，並測試 projection failure 前後不會留下部分 result 或錯誤 dirty state。
- [x] 3.3 沿用 `material_spec_editing.py` 既有 staged outcome／error-code contract，但將 Main adoption 改成 Project／Result／新 cache references 與 dirty 同次 commit，不得在 commit 呼叫 cache `clear()`；測試 rejected／confirmation／no-op 行為不變，UI projection failure 保留新材料設定與已失效結果、設定 projection guard，且不重開或修改 archived change。

## 4. 固定 CAD ACK 與 duplicate-event 邊界

- [x] 4.1 在 `main.py` `_apply_cad_event` 路徑先 stage 完整 Project／Result／cache／DXF／dirty outcome，再以 plain references commit 後 ACK；測試 stage／commit failure 不 ACK 且舊 state 不變、ACK 成功後 projection failure 保留 mutation 並鎖住編輯、ACK filesystem failure 不 rollback 且停止 polling／阻止 save／回報 unresolved event、相同 event ID 再次被偵測時不得重複套用，pending event 明確處理後才可恢復監聽與 save。

## 5. 保留 managed DXF rollback recovery artifact

- [x] 5.1 在 `bracing_optimizer/infrastructure/project_persistence.py` 只針對 managed DXF 依 rollback outcome 決定 `.rollback` cleanup，typed error 回報 recovery 與 managed DXF 絕對路徑；save 開始前若已有目標 `.rollback`，須在 temp／replace 前拒絕且不修改 JSON、DXF、recovery 或 dirty。測試 rollback 成功可清理、rollback 失敗保留 recovery file，以及連續兩次 save 失敗時第二次不得覆蓋或刪除第一次的 recovery artifact。

## 6. 同步長期文件

- [x] 6.1 在行為驗證完成後更新 `docs/ARCHITECTURE.md` 的 Application transaction responsibility 與 `docs/WORKFLOW.md` 的 side-effect-free commit、projection guard／完整重新投影、CAD ACK unresolved monitor／save guard，以及 managed DXF rollback semantics；明確保留 Project JSON `.tmp`／atomic replace／`.bak` 行為並確認沒有提前描述其他 active changes。

## 7. 整體驗證

- [x] 7.1 執行 Project navigation/load、Project results、Material Spec editing、CAD builder integration、Project persistence 與 Global Waler transaction targeted tests，確認 Global Waler 的 committed／refreshed observable contract 未改，且不把其現行 setter-based commit 當作 D1 合格實作。
- [x] 7.2 執行完整 test suite，確認 Project schema、Solver、DXF recognition、save/load、dirty navigation guard、CAD single-slot transport 與既有 Material Spec error handling 無回歸。
- [x] 7.3 執行 `openspec validate harden-project-state-transactions --strict` 與 `openspec verify`，逐項確認 side-effect-free commit、projection recovery、duplicate-event protection 與 managed DXF recovery collision 契約已實作。
