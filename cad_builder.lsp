;;; Support Distribution UV - progeCAD CAD bridge
;;; Compatibility-first version: ASCII-only source, no vl-load-com,
;;; no Visual LISP file helpers.
;;;
;;; Commands:
;;;   ADDWALER
;;;   ADDSTRUT
;;;   UPDSTRUT
;;;   ADDBRACE
;;;   SUPSTATUS
;;;   SUPCLEAR

(prompt "\n[CAD Bridge] Loading...")

(setq cb:*event-file-name* "support_distribution_uv_cad_builder_temp.json")

(defun cb:event-path (/ temp-dir last-char)
  (setq temp-dir (getenv "TEMP"))
  (if (or (null temp-dir) (= temp-dir "") (= temp-dir " "))
    (setq temp-dir (getvar "TEMPPREFIX"))
  )
  (if (or (null temp-dir) (= temp-dir "") (= temp-dir " "))
    nil
    (progn
      (setq last-char (substr temp-dir (strlen temp-dir) 1))
      (if (or (= last-char "\\") (= last-char "/"))
        (strcat temp-dir cb:*event-file-name*)
        (strcat temp-dir "\\" cb:*event-file-name*)
      )
    )
  )
)

(defun cb:replace-char (text old-char new-char / i ch result)
  (setq i 1)
  (setq result "")
  (while (<= i (strlen text))
    (setq ch (substr text i 1))
    (if (= ch old-char)
      (setq result (strcat result new-char))
      (setq result (strcat result ch))
    )
    (setq i (+ i 1))
  )
  result
)

(defun cb:number-json (value / text)
  (setq text (rtos value 2 12))
  (cb:replace-char text "," ".")
)

(defun cb:json-string (text / escaped)
  (setq escaped (cb:replace-char text "\\" "\\\\"))
  (cb:replace-char escaped "\"" "\\\"")
)

(defun cb:event-id (/ cdate-value)
  ;; progeCAD compatibility:
  ;; avoid MILLISECS because some versions return an incompatible value.
  ;; CDATE alone is sufficient for this one-event-at-a-time bridge.
  (setq cdate-value (getvar "CDATE"))
  (if (numberp cdate-value)
    (rtos cdate-value 2 8)
    "cad-event"
  )
)

(defun cb:planar-length (p1 p2 / dx dy)
  (setq dx (- (car p2) (car p1)))
  (setq dy (- (cadr p2) (cadr p1)))
  (sqrt (+ (* dx dx) (* dy dy)))
)

(defun cb:projection-distance (p1 p2 p / dx dy len)
  (setq dx (- (car p2) (car p1)))
  (setq dy (- (cadr p2) (cadr p1)))
  (setq len (cb:planar-length p1 p2))
  (/ (+ (* (- (car p) (car p1)) dx)
        (* (- (cadr p) (cadr p1)) dy))
     len)
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

(defun cb:ucs-to-wcs (point)
  (trans point 1 0)
)

(defun cb:pick-two-points (obj / p1-ucs p2-ucs p1-wcs p2-wcs)
  (setq p1-ucs (getpoint (strcat "\nPick " obj " start point: ")))
  (if p1-ucs
    (progn
      (setq p2-ucs (getpoint p1-ucs (strcat "\nPick " obj " end point: ")))
      (if p2-ucs
        (progn
          (setq p1-wcs (cb:ucs-to-wcs p1-ucs))
          (setq p2-wcs (cb:ucs-to-wcs p2-ucs))
        )
      )
      (if p2-ucs
        (if (> (cb:planar-length p1-wcs p2-wcs) 0.0)
          (list p1-wcs p2-wcs)
          (progn
            (prompt "\nStart and end points cannot be the same.")
            nil
          )
        )
        (progn
          (prompt "\nPoint input cancelled.")
          nil
        )
      )
    )
    (progn
      (prompt "\nPoint input cancelled.")
      nil
    )
  )
)

(defun cb:pick-stations (p1 p2 prompt-text / p-ucs p-wcs station len station-text)
  (setq station-text "")
  (setq len (cb:planar-length p1 p2))
  (while (setq p-ucs (getpoint prompt-text))
    (setq p-wcs (cb:ucs-to-wcs p-ucs))
    (setq station (cb:projection-distance p1 p2 p-wcs))
    (if (or (< station 0.0) (> station len))
      (prompt "\nWarning: selected point is outside the strut range; station is kept.")
    )
    (setq station-text
      (cb:append-station station-text (cb:round-integer station))
    )
  )
  station-text
)

(defun cb:ask-for-stations (question prompt-text p1 p2 / answer)
  (initget "Yes No")
  (setq answer (getkword question))
  (if (null answer)
    ""
    (if (= answer "Yes")
      (cb:pick-stations p1 p2 prompt-text)
      ""
    )
  )
)

(defun cb:event-json (event-type operation target-id p1 p2 extra-fields)
  (strcat
    "{"
    "\"event_id\":\"" (cb:event-id) "\","
    "\"type\":\"" event-type "\","
    "\"operation\":\"" operation "\","
    "\"coordinate_space\":\"WCS\","
    (if (= target-id "")
      ""
      (strcat "\"target_id\":\"" (cb:json-string target-id) "\",")
    )
    "\"data\":{"
    "\"StartX\":" (cb:number-json (car p1)) ","
    "\"StartY\":" (cb:number-json (cadr p1)) ","
    "\"EndX\":" (cb:number-json (car p2)) ","
    "\"EndY\":" (cb:number-json (cadr p2))
    (if (= extra-fields "") "" (strcat "," extra-fields))
    "}"
    "}"
  )
)

(defun cb:cancel-event-json ()
  (strcat
    "{"
    "\"event_id\":\"cancel-" (cb:event-id) "\","
    "\"type\":\"control\","
    "\"operation\":\"cancel\","
    "\"coordinate_space\":\"WCS\","
    "\"data\":{}"
    "}"
  )
)

(defun cb:write-text-file (file-path content / stream)
  (setq stream (open file-path "w"))
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
  (prompt "\nA previous CAD event is still pending. Wait for Solver, or use SUPCLEAR to discard it.")
)

(defun cb:temp-directory-message ()
  (prompt "\nCannot determine the Windows temporary directory.")
)

(defun cb:write-event (event-type operation target-id p1 p2 extra-fields / event-path content)
  (setq event-path (cb:event-path))
  (if (null event-path)
    (progn
      (cb:temp-directory-message)
      nil
    )
    (if (findfile event-path)
      (progn
        (cb:pending-message)
        nil
      )
      (progn
        (setq content
          (cb:event-json event-type operation target-id p1 p2 extra-fields)
        )
        (if (cb:write-text-file event-path content)
          (progn
            (prompt "\nEvent written. Waiting for Solver import.")
            T
          )
          (progn
            (prompt (strcat "\nCannot write event file: " event-path))
            nil
          )
        )
      )
    )
  )
)

(defun cb:capture-simple (event-type obj / event-path points)
  (setq event-path (cb:event-path))
  (if (null event-path)
    (cb:temp-directory-message)
    (if (findfile event-path)
      (cb:pending-message)
      (progn
        (setq points (cb:pick-two-points obj))
        (if points
          (cb:write-event event-type "add" "" (car points) (cadr points) "")
        )
      )
    )
  )
  (princ)
)

(defun c:ADDWALER ()
  (cb:capture-simple "waler" "Waler")
)

(defun cb:capture-strut (operation / points p1 p2 beam-positions column-positions extra-fields event-path target-id)
  (setq event-path (cb:event-path))
  (if (null event-path)
    (cb:temp-directory-message)
    (if (findfile event-path)
      (cb:pending-message)
      (progn
        (setq target-id "")
        (if (= operation "update")
          (progn
            (setq target-id (getstring T "\nTarget StrutID (example S5): "))
            (if target-id (setq target-id (strcase target-id)))
          )
        )
        (if (and (= operation "update") (= target-id ""))
          (prompt "\nStrut update cancelled: target StrutID is required.")
          (setq points (cb:pick-two-points "Strut"))
        )
        (if points
          (progn
            (setq p1 (car points))
            (setq p2 (cadr points))

            (setq beam-positions
              (cb:ask-for-stations
                "\nPick beam positions? [Yes/No] <No>: "
                "\nPick a beam position, press Enter to finish: "
                p1
                p2
              )
            )

            (setq column-positions
              (cb:ask-for-stations
                "\nPick column positions? [Yes/No] <No>: "
                "\nPick a column position, press Enter to finish: "
                p1
                p2
              )
            )

            (setq extra-fields
              (strcat
                "\"BeamPositions\":\"" beam-positions "\","
                "\"ColumnPositions\":\"" column-positions "\""
                (if (= operation "add") ",\"TargetJackRegion\":2" "")
              )
            )

            (cb:write-event "strut" operation target-id p1 p2 extra-fields)
          )
        )
      )
    )
  )
  (princ)
)

(defun c:ADDSTRUT ()
  (cb:capture-strut "add")
)

(defun c:UPDSTRUT ()
  (cb:capture-strut "update")
)

(defun c:ADDBRACE ()
  (cb:capture-simple "brace" "Brace")
)

(defun c:SUPSTATUS (/ event-path)
  (setq event-path (cb:event-path))
  (if (null event-path)
    (cb:temp-directory-message)
    (progn
      (prompt (strcat "\nSolver CAD event file: " event-path))
      (if (findfile event-path)
        (prompt "\nStatus: one event is waiting for import. Use SUPCLEAR if it was rejected.")
        (prompt "\nStatus: ready for a new event.")
      )
    )
  )
  (princ)
)

(defun c:SUPCLEAR (/ event-path answer content)
  (setq event-path (cb:event-path))
  (if (null event-path)
    (cb:temp-directory-message)
    (if (findfile event-path)
      (progn
        (initget "Yes No")
        (setq answer
          (getkword
            "\nDiscard the pending CAD event? [Yes/No] <No>: "
          )
        )
        (if (= answer "Yes")
          (progn
            (setq content (cb:cancel-event-json))
            (if (cb:write-text-file event-path content)
              (prompt "\nDiscard requested. Wait for Solver, then use SUPSTATUS.")
              (prompt "\nCannot replace the pending CAD event.")
            )
          )
          (prompt "\nPending CAD event was kept.")
        )
      )
      (prompt "\nStatus: ready for a new event. Nothing to discard.")
    )
  )
  (princ)
)

(prompt "\n[CAD Bridge] Loaded successfully.")
(prompt "\nCommands: ADDWALER, ADDSTRUT, UPDSTRUT, ADDBRACE, SUPSTATUS, SUPCLEAR")
(princ)
