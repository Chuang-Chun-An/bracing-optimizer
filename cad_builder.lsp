;;; Support Distribution UV - progeCAD 與 Solver 的 CAD 匯入橋接程式
;;;
;;; 使用 APPLOAD 載入後，可執行：
;;;   ADDWALER - 點選圍令起點與終點
;;;   ADDSTRUT - 點選支撐及選填托梁／中間柱位置
;;;   ADDBRACE - 點選斜撐起點與終點
;;;   SUPSTATUS - 顯示共享事件檔路徑與待匯入狀態

(vl-load-com)

(setq cb:*event-file-name* "support_distribution_uv_cad_builder_temp.json")

(defun cb:event-path (/ temp-dir last-character)
  (setq temp-dir (getenv "TEMP"))
  (if (or (null temp-dir) (= temp-dir "") (= temp-dir " "))
    (setq temp-dir (getvar "TEMPPREFIX"))
  )
  (if (or (null temp-dir) (= temp-dir "") (= temp-dir " "))
    nil
    (progn
      (setq last-character
        (substr temp-dir (strlen temp-dir) 1)
      )
      (if (or (= last-character "\\") (= last-character "/"))
        (strcat temp-dir cb:*event-file-name*)
        (strcat temp-dir "\\" cb:*event-file-name*)
      )
    )
  )
)

(defun cb:temp-path (/ event-path)
  (setq event-path (cb:event-path))
  (if (null event-path)
    nil
    (strcat event-path ".tmp")
  )
)

(defun cb:number-json (value / text)
  (setq text (rtos value 2 12))
  (vl-string-translate "," "." text)
)

(defun cb:event-id ()
  (strcat
    (vl-string-translate "." "-" (rtos (getvar "CDATE") 2 8))
    "-"
    (rtos (getvar "MILLISECS") 2 0)
  )
)

(defun cb:planar-length (start-point end-point / dx dy)
  (setq dx (- (car end-point) (car start-point)))
  (setq dy (- (cadr end-point) (cadr start-point)))
  (sqrt (+ (* dx dx) (* dy dy)))
)

(defun cb:projection-distance
       (start-point end-point selected-point / dx dy length)
  (setq dx (- (car end-point) (car start-point)))
  (setq dy (- (cadr end-point) (cadr start-point)))
  (setq length (cb:planar-length start-point end-point))
  (/ (+ (* (- (car selected-point) (car start-point)) dx)
        (* (- (cadr selected-point) (cadr start-point)) dy))
     length)
)

(defun cb:round-integer (value)
  (if (>= value 0.0)
    (fix (+ value 0.5))
    (fix (- value 0.5))
  )
)

(defun cb:append-station (station-text station)
  (if (= station-text "")
    (itoa station)
    (strcat station-text "," (itoa station))
  )
)

(defun cb:pick-two-points
       (object-name / start-ucs end-ucs)
  (setq start-ucs
    (getpoint (strcat "\n請點選" object-name "起點："))
  )
  (if start-ucs
    (progn
      (setq end-ucs
        (getpoint start-ucs (strcat "\n請點選" object-name "終點："))
      )
      (if end-ucs
        (progn
          (if (> (cb:planar-length start-ucs end-ucs) 0.0)
            (list start-ucs end-ucs)
            (progn
              (prompt "\n起點與終點不可相同。")
              nil
            )
          )
        )
        (progn
          (prompt "\n已取消點位輸入。")
          nil
        )
      )
    )
    (progn
      (prompt "\n已取消點位輸入。")
      nil
    )
  )
)

(defun cb:pick-stations
       (start-point end-point prompt-text
        / selected-ucs station length station-text)
  (setq station-text "")
  (setq length (cb:planar-length start-point end-point))
  (while (setq selected-ucs (getpoint prompt-text))
    (setq station
      (cb:projection-distance start-point end-point selected-ucs)
    )
    (if (or (< station 0.0) (> station length))
      (prompt "\n警告：所選位置超出支撐範圍，仍會保留此測站。")
    )
    (setq station-text
      (cb:append-station station-text (cb:round-integer station))
    )
  )
  station-text
)

(defun cb:ask-for-stations
       (question prompt-text start-point end-point / answer)
  (initget "Yes No")
  (setq answer (getkword question))
  (if (null answer)
    ""
    (if (= answer "Yes")
      (cb:pick-stations start-point end-point prompt-text)
      ""
    )
  )
)

(defun cb:event-json
       (event-type start-point end-point extra-fields)
  (strcat
    "{"
    "\"event_id\":\"" (cb:event-id) "\","
    "\"type\":\"" event-type "\","
    "\"data\":{"
    "\"StartX\":" (cb:number-json (car start-point)) ","
    "\"StartY\":" (cb:number-json (cadr start-point)) ","
    "\"EndX\":" (cb:number-json (car end-point)) ","
    "\"EndY\":" (cb:number-json (cadr end-point))
    (if (= extra-fields "") "" (strcat "," extra-fields))
    "}"
    "}"
  )
)

(defun cb:write-text-file (path content / stream)
  (setq stream (open path "w"))
  (if stream
    (progn
      (write-line content stream)
      (close stream)
      T
    )
    nil
  )
)

(defun cb:pending-message ()
  (prompt
    (strcat
      "\n上一筆 CAD 匯入事件尚未處理完成。"
      "請等待 Solver 匯入後再試一次。"
    )
  )
)

(defun cb:temp-directory-message ()
  (prompt "\n無法取得 Windows 暫存資料夾。")
)

(defun cb:write-event
       (event-type start-point end-point extra-fields
        / event-path temp-path content renamed-path)
  (setq event-path (cb:event-path))
  (setq temp-path (cb:temp-path))
  (if (or (null event-path) (null temp-path))
    (progn
      (cb:temp-directory-message)
      nil
    )
    (progn
      (if (findfile event-path)
        (progn
          (cb:pending-message)
          nil
        )
        (progn
          (if (findfile temp-path)
            (vl-file-delete temp-path)
          )
          (setq content
            (cb:event-json event-type start-point end-point extra-fields)
          )
          (if (not (cb:write-text-file temp-path content))
            (progn
              (prompt
                (strcat "\n無法寫入暫存事件檔：" temp-path)
              )
              nil
            )
            (progn
              (setq renamed-path (vl-file-rename temp-path event-path))
              (if renamed-path
                (progn
                  (prompt "\n事件已寫入，等待 Solver 匯入。")
                  T
                )
                (progn
                  (if (findfile temp-path)
                    (vl-file-delete temp-path)
                  )
                  (prompt
                    (strcat "\n無法發布事件檔：" event-path)
                  )
                  nil
                )
              )
            )
          )
        )
      )
    )
  )
)

(defun cb:capture-simple (event-type object-name / event-path points)
  (setq event-path (cb:event-path))
  (if (null event-path)
    (cb:temp-directory-message)
    (progn
      (if (findfile event-path)
        (cb:pending-message)
        (progn
          (setq points (cb:pick-two-points object-name))
          (if points
            (cb:write-event event-type (car points) (cadr points) "")
          )
        )
      )
    )
  )
  (princ)
)

(defun c:ADDWALER ()
  (cb:capture-simple "waler" "圍令")
)

(defun c:ADDSTRUT
       (/ points start-point end-point beam-positions column-positions
        extra-fields event-path)
  (setq event-path (cb:event-path))
  (if (null event-path)
    (cb:temp-directory-message)
    (progn
      (if (findfile event-path)
        (cb:pending-message)
        (progn
          (setq points (cb:pick-two-points "支撐"))
          (if points
            (progn
              (setq start-point (car points))
              (setq end-point (cadr points))
              (setq beam-positions
                (cb:ask-for-stations
                  "\n是否要點選托梁位置？[Yes/No] <No>："
                  "\n請點選托梁位置，按 Enter 結束："
                  start-point
                  end-point
                )
              )
              (setq column-positions
                (cb:ask-for-stations
                  "\n是否要點選中間柱位置？[Yes/No] <No>："
                  "\n請點選中間柱位置，按 Enter 結束："
                  start-point
                  end-point
                )
              )
              (setq extra-fields
                (strcat
                  "\"BeamPositions\":\"" beam-positions "\","
                  "\"ColumnPositions\":\"" column-positions "\","
                  "\"TargetJackRegion\":\"\""
                )
              )
              (cb:write-event
                "strut"
                start-point
                end-point
                extra-fields
              )
            )
          )
        )
      )
    )
  )
  (princ)
)

(defun c:ADDBRACE ()
  (cb:capture-simple "brace" "斜撐")
)

(defun c:SUPSTATUS (/ path)
  (setq path (cb:event-path))
  (if (null path)
    (cb:temp-directory-message)
    (progn
      (prompt (strcat "\nSolver CAD 匯入事件檔：" path))
      (if (findfile path)
        (prompt "\n狀態：有一筆事件等待匯入。")
        (prompt "\n狀態：可接收新事件。")
      )
    )
  )
  (princ)
)

(prompt
  "\nCAD 匯入橋接程式已載入。指令：ADDWALER、ADDSTRUT、ADDBRACE、SUPSTATUS。"
)
(princ) 
