# Design

## 閱讀導航

- **現在必讀**：方案摘要、Decision 1（先驗證版本型別與範圍，再將版本標籤與資料結構分開判斷）、Decision 2（load/save 使用不同入口但共用現行結構驗證）。
- **實作前必讀**：Decision 3（錯誤分類）、Decision 4（不在 load path 正規化 payload）、Architecture Alignment 與測試矩陣。
- **修改 persistence 時條件式閱讀**：Backward Compatibility / Persistence Impact、Migration Plan。
- **處理 UI 或 navigation 測試時條件式閱讀**：Decision 3 與「拒絕時保留目前狀態」的對照。
- **可先跳過**：Solver、DXF recognition、export 與 Domain 工程規則；本設計不接觸這些邏輯。

## 方案摘要

`ProjectSerializer` 繼續作為 Project JSON 格式契約的 single source of truth，但明確區分「load compatibility validation」與既有「current structure validation」。載入先檢查 `schema_version` 欄位是否存在；存在時必須先通過真正整數（排除 bool）與最小值 `1` 的驗證，之後才分類 older／current／future。missing／older／current 再共用同一套 schema 3 結構驗證。只有使用者實際成功 Save 時，save boundary 才會把輸出版本固定為 `3`；單純 load／close 不會就地升級或覆寫來源。

```text
JSON parsed
  → schema_version field exists?
      → no: classify as missing
      → yes: require real integer (not bool) and value >= 1
          → invalid: reject as schema-version-format-error
          → valid: classify as older / current / future
  → future: reject as newer-program-required
  → missing / older / current: validate current schema-3 structure
      → pass: hydrate and adopt through existing Open transaction
      → fail + missing/older: reject with
          「無法以現行格式讀取；若為舊版專案，請先執行升級工具」
          + preserve underlying validation error
      → fail + current: reject as invalid current project
  → later explicit Save: existing save boundary emits schema_version = 3
```

本 change 的「版本標籤」是 `schema_version`；「現行結構」是現有 serializer 已驗證的 schema 3 JSON 與 Domain rows；`old-structure` 只是一個測試分類，表示 missing／older payload 無法通過現行結構驗證，不代表載入流程已辨識或證明其舊格式特徵。

## 決策對照

| Decision | 影響的 Spec Requirement | 對應 Task |
| --- | --- | --- |
| 1. 先驗證版本型別與範圍，再將版本標籤和資料結構分開判斷 | schema_version 必須是有效整數；以版本上限與現行結構共同判斷是否可載入 | 1.1、2.1 |
| 2. Load compatibility 與 save validation 使用不同入口、共用結構驗證 | 以版本上限與現行結構共同判斷是否可載入；成功儲存一律寫入現行版本 | 1.1、1.2、2.1、2.2 |
| 3. 沿用 `ProjectPersistenceError` 的 stage/detail 或固定關鍵字表達拒絕原因 | 拒絕時提供可行的下一步並保留目前狀態 | 1.3、2.1、2.3 |
| 4. Load 不正規化版本、不寫回來源 | 成功儲存一律寫入現行版本 | 1.2、2.2 |
| 5. 非正常版本值與五類相容矩陣作為最小 regression contract | 四項 Requirements 的全部 Scenarios | 2.1、2.2、3.1 |

## Context

動機見 `proposal.md` 的 Why。現有 `ProjectSerializer.validate()` 驗證 schema 3 所需的 `dxf_asset`、Domain tables、row mapping 與 DXF asset contract，但不檢查 `schema_version`；因此 `ProjectService.load_project()` 已能載入版本 `2` 或缺少版本號、但結構等同 schema 3 的 payload，也會接受高於 `3` 的 payload。現有 save path 在寫入與驗證前把 `schema_version` 設為 `PROJECT_SCHEMA_VERSION`，已具備輸出 schema 3 的核心行為。

`tools/upgrade_project_schema.py` 是獨立、明確觸發的舊結構 migration；它會轉換 legacy Strut 欄位並補 `dxf_asset`。本設計不得把該轉換邏輯搬進正常載入。

## Goals / Non-Goals

**Goals:**

- 在 persistence boundary 建立唯一的 load compatibility 判斷。
- 重用既有 schema 3 結構驗證，避免「舊標籤相容驗證」形成第二套 schema 規則。
- 讓 schema-version-format-error、future-version、current-format-unreadable 與 invalid-current 拒絕原因對使用者可辨識。
- 保持 Project Open 的既有 hydrate-then-adopt transaction semantics。

**Non-Goals:**

- 不設計 schema 4，不改 schema 3 欄位，也不加入 migration registry。
- 不改離線 upgrade tool 的轉換能力。
- 不為此功能建立新的跨 layer exception hierarchy 或全域 compatibility framework。
- 不把載入成功本身視為儲存、migration 或 dirty-state mutation。

## Decisions

### Decision 1：先驗證版本型別與範圍，再將版本標籤與資料結構分開判斷

Load compatibility 必須依下列順序判斷：

1. 先檢查 `schema_version` 欄位是否存在；只有欄位不存在才是 missing。
2. 欄位存在時，先確認值是排除 bool 的真正整數，再確認值大於等於 `1`。`"3"`、`3.0`、`true`、`false`、`null`、`0` 與負整數都在此階段以格式錯誤拒絕，不進行轉型。
3. 只有通過型別與範圍驗證的值，才依 `PROJECT_SCHEMA_VERSION` 分類為 older、current 或 future。
4. future 立即拒絕；missing／older／current 執行相同的現行結構驗證。

版本小於 `3` 只代表標籤較舊，不足以證明資料結構過時；反之，即使標籤缺少或較舊，結構驗證失敗仍不得載入。載入流程不偵測舊格式特徵，也不以結構錯誤反推檔案一定是舊格式。

理由是 JSON 的 boolean 在 Python 型別系統中是 `int` 的子類別，若未先明確排除，`true` 可能被誤判成版本 `1`；同樣地，自動把字串、浮點數或 `null` 轉為整數會掩蓋格式錯誤。版本號只能提供 producer 宣告，不能取代 payload 的實際安全性驗證；此順序也避免 future payload 恰巧通過 schema 3 驗證後被錯誤採用。

Rejected alternatives：

- **只接受 version = 3**：會拒絕目前已有測試保障、內容其實完整的相容檔案，與本 change 目標衝突。
- **完全忽略版本號**：無法安全阻止未知 future schema。
- **依每個舊版本選不同 validator**：目前沒有多套受支持的舊 schema contract，會虛構不存在的 compatibility promise。

### Decision 2：Load compatibility 與 save validation 使用不同入口、共用現行結構驗證

在既有 persistence serializer boundary 提供明確的 load-oriented compatibility validation；其內部呼叫既有 current structure validation，而不是複製欄位規則。`ProjectService.load_project()` 改用 load-oriented 入口；save path 繼續以 current structure validation 驗證已固定為 version `3` 的輸出。

這保留責任方向：Application 協調 load use case，Infrastructure 擁有 JSON persistence contract。兩個入口的差異只有 compatibility policy，不存在兩份 schema 3 欄位 truth。

Rejected alternative：在 `ProjectService` 直接比較版本並解讀所有 validation error。這會把 persistence-format policy 洩漏到 Application，且未來其他 load caller 容易繞過版本上限。

### Decision 3：沿用現有錯誤 contract，依 stage/detail 區分拒絕原因

沿用 `ProjectPersistenceError(stage, detail)`：

- future version：stage/detail 明確包含「版本高於目前支援版本」與「請使用較新程式」。
- missing／older 且 current structure validation 失敗：回報「無法以現行格式讀取；若為舊版專案，請先執行升級工具」，detail 同時保留底層結構或 Domain 驗證錯誤；不得偵測舊格式特徵或宣稱檔案一定需要 migration。
- current version 結構失敗：維持目前 JSON／Domain 驗證失敗語意，不誤導成升級可修復。

Main 目前把 exception 字串直接顯示於「載入專案失敗」對話框，因此本 change 不需要新增 presentation 分支或 machine-readable reason code。若後續產品要求錯誤對話框提供不同按鈕，才另行引入 reason code；本 change 不預先建立該 abstraction。

測試以 `ProjectPersistenceError.stage` 或固定關鍵字區分 future、current-format-unreadable 與 invalid-current，不比對完整訊息文字。對 missing／older 的中性錯誤只包裝 load compatibility；原始 current validator 在 save 與直接驗證時仍回報精確結構錯誤。

### Decision 4：Load 不正規化版本，也不寫回來源

成功載入 missing／older payload 時保留讀入 payload 的版本標籤狀態，不在記憶體內假裝已完成 migration，也不修改來源檔。只有後續使用者實際執行且成功完成 Save 時，既有 payload builder 與 persistence save boundary 才輸出 schema 3；僅開啟後關閉、無論 dirty state 為何，都不構成改寫來源的授權。

這避免 load 產生隱藏磁碟 side effect，也避免 runtime 同時存在「來源已升級」與「其實尚未保存」兩種 truth。Project 的 persisted schema version single source of truth 仍是磁碟上的最後一次成功 save；新 save 的版本 single source of truth 是 `PROJECT_SCHEMA_VERSION`。

Rejected alternative：載入後立即把 payload 的 version 改成 `3`。這會模糊「版本標籤相容」與「已完成持久化 migration」，也可能讓未儲存的狀態被錯誤宣稱為 schema 3 檔案。

### Decision 5：以非正常版本值與五類矩陣鎖定相容邊界

Focused tests 至少覆蓋：

| 類別 | Version | Structure | Expected |
| --- | --- | --- | --- |
| invalid-version | `"3"`、`3.0`、`true`、`false`、`null`、`0`、`-1` | regardless | reject as schema-version-format-error |
| missing | absent | current-valid | load succeeds |
| older | `< 3` | current-valid | load succeeds |
| current | `= 3` | current-valid／invalid | normal validation |
| future | `> 3` | regardless of schema-3 compatibility | reject as newer-program-required |
| old-structure | absent or `< 3` | current-invalid | reject with neutral current-format-unreadable message and underlying error; no detection or conversion |

另以實際呼叫正式 save path 的測試，證明從 missing／older 相容檔案建立的下一次成功輸出為 version `3`，並證明單純 load／close 不改寫來源；此測試不得依賴 dirty state 來替代實際儲存行為。Open transaction test 只需在既有 navigation coverage 不足時補充；不得為測試方便繞過正式 service boundary。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 Architecture 本身**。

- **Infrastructure**：`ProjectSerializer` 擁有版本／結構 persistence contract 與 user-actionable persistence error。
- **Application**：`ProjectService` 選用 load-oriented validation、完成 hydrate 與回傳結果，不複製版本政策。
- **Presentation**：沿用既有 exception 顯示與 hydrate 成功後才採用 state 的流程；不推導 schema compatibility。
- **Domain／Algorithms**：不受影響。Domain row validation 仍由既有 mapper 被 current structure validator 呼叫；Algorithms 不依賴 persistence。

Dependency direction 維持 Presentation → Application，以及 Application 對目前 Infrastructure implementation 的既有 accepted exception。沒有新增反向依賴或第二份 Domain rule。

## Backward Compatibility / Persistence Impact

- schema 3 合法檔案行為不變。
- missing／older version 且 current-valid 的檔案正式成為受支持的讀取相容輸入。
- 非正常 `schema_version` 與 future version 從目前可能誤載，改為明確拒絕；這是保護性 compatibility boundary。
- 真正 legacy structure 仍必須經離線工具明確升級；load 不新增 migration side effect。
- 新存、另存與再存的 JSON 格式不變，持續為 schema 3；不需要批次 migration 或資料庫 deployment。

## Risks / Trade-offs

- **[Risk] 較舊版本號可能隱含未被結構 validator 捕捉的語意差異** → 目前只承諾「完整通過現行結構與 Domain 驗證」；若發現版本特定語意，停止實作並修訂 Spec，不在 code 中加入猜測 heuristic。
- **[Risk] 中性 current-format-unreadable 訊息可能遮蔽具體缺欄原因** → detail 同時保留原始 validation error，讓使用者與維護者都能診斷；載入流程不以特徵偵測猜測舊格式。
- **[Risk] future version rejection 只在某個 load caller 生效** → compatibility 判斷放在 serializer boundary，並測試 `ProjectService` 正式入口。
- **[Trade-off] 沒有 machine-readable reason code** → 現有 UI 只顯示文字，不需要分支；待真正出現 programmatic consumer 再擴充 contract。

## Migration Plan

1. 先加入版本型別／範圍 validation、load compatibility validation，以及指定非正常值與五類 focused tests，確認 save regression 維持 schema 3。
2. 更新 `ProjectService` 正式 load path 使用該入口，不改 hydrate／adopt 順序。
3. 校正 README，將「只接受 schema 3」改為本 Spec 的版本標籤／資料結構政策，保留 upgrade tool 說明。
4. 執行 focused persistence/service tests，再執行 navigation guard 與相關 project regression。

Rollback 可直接回退本 change 的 validator routing、tests 與 README；不需回復任何已遷移資料，因本設計不在 load 時寫檔，而 save 前後皆輸出既有 schema 3。
