# DXF saveas 最小重現 Audit 報告

ezdxf 版本：`1.4.4`

## 案例摘要

| 案例 | 檔案 | bytes | EntityDB | Layer records / table entries | Dictionary pre → post Audit | XRecord pre → post Audit | Audit errors | Audit fixes | 錯誤類型 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01_original_source | C:\Users\ChunAn\support_distribution_uv\project_cases\Y1A站第一層支撐\source\source.dxf | 7388788 | 22646 | 123 / 106 | 279 → 279 | 147 → 147 | 0 | 0 | 無 |
| 02_immediate_saveas | C:\Users\ChunAn\support_distribution_uv\tmp\dxf_minimal_repro\02_immediate_saveas.dxf | 6512094 | 22632 | 106 / 106 | 280 → 268 | 147 → 135 | 0 | 12 | fix:INVALID_OWNER_HANDLE=12 |
| 03_add_one_dimension | C:\Users\ChunAn\support_distribution_uv\tmp\dxf_minimal_repro\03_add_one_dimension.dxf | 6515078 | 22652 | 106 / 106 | 280 → 268 | 147 → 135 | 0 | 12 | fix:INVALID_OWNER_HANDLE=12 |
| 04_add_jack_block | C:\Users\ChunAn\support_distribution_uv\tmp\dxf_minimal_repro\04_add_jack_block.dxf | 6525796 | 22709 | 106 / 106 | 280 → 268 | 147 → 135 | 0 | 12 | fix:INVALID_OWNER_HANDLE=12 |
| 05_full_export | C:\Users\ChunAn\support_distribution_uv\source_配置標註.dxf | 6849061 | 24569 | 106 / 106 | 280 → 268 | 147 → 135 | 0 | 12 | fix:INVALID_OWNER_HANDLE=12 |

## Audit 明細

| 案例 | 類別 | 錯誤類型 | Handle | Owner | Dictionary | Dictionary Key | Layer Handle | Layer | Layer 狀態 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 4704B | 4704A | 4704A | ADSK_XREC_LAYER_RECONCILED | 23D | Defpoints | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 63E76 | 63E75 | 63E75 | ADSK_XREC_LAYER_RECONCILED | 63E74 | ES-中間柱LINE線 | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 6420D | 6420C | 6420C | ADSK_XREC_LAYER_RECONCILED | 6420B | DIM-軸線X | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 6E52A | 6E529 | 6E529 | ADSK_XREC_LAYER_RECONCILED | 6E528 | ES-圍令背填 | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 6FFAC | 6FFAB | 6FFAB | ADSK_XREC_LAYER_RECONCILED | 6FFAA | ES-C380x100 | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 76B3C | 76B3B | 76B3B | ADSK_XREC_LAYER_RECONCILED | 76B3A | ES-支撐DIM | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 77782 | 77781 | 77781 | ADSK_XREC_LAYER_RECONCILED | 77780 | ES-大斜撐_支撐350x350 | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 7A663 | 7A662 | 7A662 | ADSK_XREC_LAYER_RECONCILED | 7A661 | ES-圍令L1H414x405 | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 7A66D | 7A66C | 7A66C | ADSK_XREC_LAYER_RECONCILED | 7A66B | ES-圍令L1H428x407 | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 7CB83 | 7CB82 | 7CB82 | ADSK_XREC_LAYER_RECONCILED | 7CB81 | ES-中間樁NO | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | 7CB92 | 7CB91 | 7CB91 | ADSK_XREC_LAYER_RECONCILED | 7CB90 | ES-C250x90 | missing_after_saveas |
| 02_immediate_saveas | fix | INVALID_OWNER_HANDLE | B42AC | B42AB | B42AB | ADSK_XREC_LAYER_RECONCILED | B42AA | dw | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 4704B | 4704A | 4704A | ADSK_XREC_LAYER_RECONCILED | 23D | Defpoints | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 63E76 | 63E75 | 63E75 | ADSK_XREC_LAYER_RECONCILED | 63E74 | ES-中間柱LINE線 | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 6420D | 6420C | 6420C | ADSK_XREC_LAYER_RECONCILED | 6420B | DIM-軸線X | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 6E52A | 6E529 | 6E529 | ADSK_XREC_LAYER_RECONCILED | 6E528 | ES-圍令背填 | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 6FFAC | 6FFAB | 6FFAB | ADSK_XREC_LAYER_RECONCILED | 6FFAA | ES-C380x100 | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 76B3C | 76B3B | 76B3B | ADSK_XREC_LAYER_RECONCILED | 76B3A | ES-支撐DIM | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 77782 | 77781 | 77781 | ADSK_XREC_LAYER_RECONCILED | 77780 | ES-大斜撐_支撐350x350 | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 7A663 | 7A662 | 7A662 | ADSK_XREC_LAYER_RECONCILED | 7A661 | ES-圍令L1H414x405 | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 7A66D | 7A66C | 7A66C | ADSK_XREC_LAYER_RECONCILED | 7A66B | ES-圍令L1H428x407 | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 7CB83 | 7CB82 | 7CB82 | ADSK_XREC_LAYER_RECONCILED | 7CB81 | ES-中間樁NO | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | 7CB92 | 7CB91 | 7CB91 | ADSK_XREC_LAYER_RECONCILED | 7CB90 | ES-C250x90 | missing_after_saveas |
| 03_add_one_dimension | fix | INVALID_OWNER_HANDLE | B42AC | B42AB | B42AB | ADSK_XREC_LAYER_RECONCILED | B42AA | dw | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 4704B | 4704A | 4704A | ADSK_XREC_LAYER_RECONCILED | 23D | Defpoints | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 63E76 | 63E75 | 63E75 | ADSK_XREC_LAYER_RECONCILED | 63E74 | ES-中間柱LINE線 | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 6420D | 6420C | 6420C | ADSK_XREC_LAYER_RECONCILED | 6420B | DIM-軸線X | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 6E52A | 6E529 | 6E529 | ADSK_XREC_LAYER_RECONCILED | 6E528 | ES-圍令背填 | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 6FFAC | 6FFAB | 6FFAB | ADSK_XREC_LAYER_RECONCILED | 6FFAA | ES-C380x100 | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 76B3C | 76B3B | 76B3B | ADSK_XREC_LAYER_RECONCILED | 76B3A | ES-支撐DIM | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 77782 | 77781 | 77781 | ADSK_XREC_LAYER_RECONCILED | 77780 | ES-大斜撐_支撐350x350 | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 7A663 | 7A662 | 7A662 | ADSK_XREC_LAYER_RECONCILED | 7A661 | ES-圍令L1H414x405 | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 7A66D | 7A66C | 7A66C | ADSK_XREC_LAYER_RECONCILED | 7A66B | ES-圍令L1H428x407 | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 7CB83 | 7CB82 | 7CB82 | ADSK_XREC_LAYER_RECONCILED | 7CB81 | ES-中間樁NO | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | 7CB92 | 7CB91 | 7CB91 | ADSK_XREC_LAYER_RECONCILED | 7CB90 | ES-C250x90 | missing_after_saveas |
| 04_add_jack_block | fix | INVALID_OWNER_HANDLE | B42AC | B42AB | B42AB | ADSK_XREC_LAYER_RECONCILED | B42AA | dw | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 4704B | 4704A | 4704A | ADSK_XREC_LAYER_RECONCILED | 23D | Defpoints | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 63E76 | 63E75 | 63E75 | ADSK_XREC_LAYER_RECONCILED | 63E74 | ES-中間柱LINE線 | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 6420D | 6420C | 6420C | ADSK_XREC_LAYER_RECONCILED | 6420B | DIM-軸線X | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 6E52A | 6E529 | 6E529 | ADSK_XREC_LAYER_RECONCILED | 6E528 | ES-圍令背填 | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 6FFAC | 6FFAB | 6FFAB | ADSK_XREC_LAYER_RECONCILED | 6FFAA | ES-C380x100 | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 76B3C | 76B3B | 76B3B | ADSK_XREC_LAYER_RECONCILED | 76B3A | ES-支撐DIM | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 77782 | 77781 | 77781 | ADSK_XREC_LAYER_RECONCILED | 77780 | ES-大斜撐_支撐350x350 | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 7A663 | 7A662 | 7A662 | ADSK_XREC_LAYER_RECONCILED | 7A661 | ES-圍令L1H414x405 | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 7A66D | 7A66C | 7A66C | ADSK_XREC_LAYER_RECONCILED | 7A66B | ES-圍令L1H428x407 | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 7CB83 | 7CB82 | 7CB82 | ADSK_XREC_LAYER_RECONCILED | 7CB81 | ES-中間樁NO | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | 7CB92 | 7CB91 | 7CB91 | ADSK_XREC_LAYER_RECONCILED | 7CB90 | ES-C250x90 | missing_after_saveas |
| 05_full_export | fix | INVALID_OWNER_HANDLE | B42AC | B42AB | B42AB | ADSK_XREC_LAYER_RECONCILED | B42AA | dw | missing_after_saveas |

## EntityDB 實體數量差異（相對原始檔）

| 案例 | 類型 | 差異 |
| --- | --- | --- |
| 02_immediate_saveas | APPID | +1 |
| 02_immediate_saveas | DICTIONARY | +1 |
| 02_immediate_saveas | DICTIONARYVAR | +1 |
| 02_immediate_saveas | LAYER | -17 |
| 03_add_one_dimension | APPID | +1 |
| 03_add_one_dimension | BLOCK | +2 |
| 03_add_one_dimension | BLOCK_RECORD | +2 |
| 03_add_one_dimension | DICTIONARY | +1 |
| 03_add_one_dimension | DICTIONARYVAR | +1 |
| 03_add_one_dimension | DIMENSION | +1 |
| 03_add_one_dimension | ENDBLK | +2 |
| 03_add_one_dimension | INSERT | +2 |
| 03_add_one_dimension | LAYER | -17 |
| 03_add_one_dimension | LINE | +4 |
| 03_add_one_dimension | MTEXT | +1 |
| 03_add_one_dimension | POINT | +3 |
| 03_add_one_dimension | SEQEND | +2 |
| 03_add_one_dimension | SOLID | +1 |
| 04_add_jack_block | APPID | +1 |
| 04_add_jack_block | BLOCK | +1 |
| 04_add_jack_block | BLOCK_RECORD | +1 |
| 04_add_jack_block | CIRCLE | +1 |
| 04_add_jack_block | DICTIONARY | +1 |
| 04_add_jack_block | DICTIONARYVAR | +1 |
| 04_add_jack_block | ENDBLK | +1 |
| 04_add_jack_block | INSERT | +1 |
| 04_add_jack_block | LAYER | -17 |
| 04_add_jack_block | LINE | +71 |
| 04_add_jack_block | SEQEND | +1 |
| 05_full_export | APPID | +2 |
| 05_full_export | BLOCK | +114 |
| 05_full_export | BLOCK_RECORD | +114 |
| 05_full_export | CIRCLE | +1 |
| 05_full_export | DICTIONARY | +1 |
| 05_full_export | DICTIONARYVAR | +1 |
| 05_full_export | DIMENSION | +112 |
| 05_full_export | DIMSTYLE | +1 |
| 05_full_export | ENDBLK | +114 |
| 05_full_export | INSERT | +239 |
| 05_full_export | LAYER | -17 |
| 05_full_export | LINE | +553 |
| 05_full_export | MTEXT | +112 |
| 05_full_export | POINT | +336 |
| 05_full_export | SEQEND | +239 |
| 05_full_export | SOLID | +1 |

## Modelspace 實體數量差異（相對原始檔）

| 案例 | 類型 | 差異 |
| --- | --- | --- |
| 03_add_one_dimension | DIMENSION | +1 |
| 04_add_jack_block | INSERT | +1 |
| 05_full_export | DIMENSION | +112 |
| 05_full_export | INSERT | +15 |

## Block 內容實體數量差異（相對原始檔）

| 案例 | 類型 | 差異 |
| --- | --- | --- |
| 03_add_one_dimension | DIMENSION | +1 |
| 03_add_one_dimension | INSERT | +2 |
| 03_add_one_dimension | LINE | +4 |
| 03_add_one_dimension | MTEXT | +1 |
| 03_add_one_dimension | POINT | +3 |
| 03_add_one_dimension | SOLID | +1 |
| 04_add_jack_block | CIRCLE | +1 |
| 04_add_jack_block | INSERT | +1 |
| 04_add_jack_block | LINE | +71 |
| 05_full_export | CIRCLE | +1 |
| 05_full_export | DIMENSION | +112 |
| 05_full_export | INSERT | +239 |
| 05_full_export | LINE | +553 |
| 05_full_export | MTEXT | +112 |
| 05_full_export | POINT | +336 |
| 05_full_export | SOLID | +1 |

## OBJECTS 實體數量差異（相對原始檔）

| 案例 | 類型 | 差異 |
| --- | --- | --- |
| 02_immediate_saveas | DICTIONARY | +1 |
| 02_immediate_saveas | DICTIONARYVAR | +1 |
| 03_add_one_dimension | DICTIONARY | +1 |
| 03_add_one_dimension | DICTIONARYVAR | +1 |
| 04_add_jack_block | DICTIONARY | +1 |
| 04_add_jack_block | DICTIONARYVAR | +1 |
| 05_full_export | DICTIONARY | +1 |
| 05_full_export | DICTIONARYVAR | +1 |

## Dictionary owner 類型數量差異（相對原始檔）

| 案例 | 類型 | 差異 |
| --- | --- | --- |
| 02_immediate_saveas | DICTIONARY | +1 |
| 02_immediate_saveas | LAYER | -12 |
| 02_immediate_saveas | MISSING | +12 |
| 03_add_one_dimension | DICTIONARY | +1 |
| 03_add_one_dimension | LAYER | -12 |
| 03_add_one_dimension | MISSING | +12 |
| 04_add_jack_block | DICTIONARY | +1 |
| 04_add_jack_block | LAYER | -12 |
| 04_add_jack_block | MISSING | +12 |
| 05_full_export | DICTIONARY | +1 |
| 05_full_export | LAYER | -12 |
| 05_full_export | MISSING | +12 |

## Dictionary entry key 數量差異（相對原始檔）

| 案例 | 類型 | 差異 |
| --- | --- | --- |
| 02_immediate_saveas | EZDXF_META | +1 |
| 02_immediate_saveas | WRITTEN_BY_EZDXF | +1 |
| 03_add_one_dimension | EZDXF_META | +1 |
| 03_add_one_dimension | WRITTEN_BY_EZDXF | +1 |
| 04_add_jack_block | EZDXF_META | +1 |
| 04_add_jack_block | WRITTEN_BY_EZDXF | +1 |
| 05_full_export | EZDXF_META | +1 |
| 05_full_export | WRITTEN_BY_EZDXF | +1 |

## XRecord Dictionary key 數量差異（相對原始檔）

（無）

## XRecord Layer 解析數量差異（相對原始檔）

| 案例 | 類型 | 差異 |
| --- | --- | --- |
| 02_immediate_saveas | missing_after_saveas | +12 |
| 02_immediate_saveas | present | -12 |
| 03_add_one_dimension | missing_after_saveas | +12 |
| 03_add_one_dimension | present | -12 |
| 04_add_jack_block | missing_after_saveas | +12 |
| 04_add_jack_block | present | -12 |
| 05_full_export | missing_after_saveas | +12 |
| 05_full_export | present | -12 |

## 原始檔重複 Layer records

| Layer | Handles |
| --- | --- |
| Defpoints | 23D, CD2E4 |
| A-WALL-PATT | 5D3B0, CD94C |
| S-GRID-IDEN | 5D3B7, CD3CB |
| ES-中間柱LINE線 | 63E74, CD57A |
| DIM-軸線X | 6420B, CD2F1 |
| ES-圍令背填 | 6E528, CD51F |
| ES-C380x100 | 6FFAA, CD909 |
| ES-支撐DIM | 76B3A, CD904 |
| ES-大斜撐_支撐350x350 | 77780, CDA18 |
| ES-圍令L1H414x405 | 7A661, CF1A8 |
| ES-圍令L1H428x407 | 7A66B, CF1AC |
| ES-中間樁NO | 7CB81, CD56F |
| ES-C250x90 | 7CB90, CD565 |
| S | 98AA0, CEA6C |
| ES-圍令RC | A0E70, CE845 |
| dw | B42AA, CF0E4 |
| A-ANNO-NOTE | BD3ED, CF66E |

## 判斷

- 單純 saveas 與完整匯出的 Audit 問題完全相同：`True`
- 加入 Dimension 後沒有新增 Audit 問題：`True`
- 加入 Block 後沒有新增 Audit 問題：`True`
- 若上述三項皆為 True，最小重現已證明問題由 ezdxf 對這份來源檔重新儲存所觸發，不是 Dimension、Block 或完整匯出迴圈額外造成。
