# Tasks

## 1. Application Exact-Match Contract

- [x] 1.1 Add the paused Review Relink request, status, exact evaluation plan and commit-result contracts in `bracing_optimizer/application/project_service.py`; verify focused tests represent `EXACT_MATCH`, `SOURCE_CONTENT_MISMATCH` and `VALIDATION_FAILED` without Tkinter or DXF recognition imports.
- [x] 1.2 Implement Review-only candidate evaluation using the saved `dxf_import_state.source_fingerprint` and existing `DxfAssetManager.file_info()` validation; verify `tests/test_project_service.py` covers exact content at a new path, different content, unreadable/invalid DXF, missing saved fingerprint, wrong workflow and caller-state immutability.
- [x] 1.3 Stage Exact Match as a deep copy that changes only the resolved `source_path` and normalized fingerprint representation; verify all other nested Review fields, confirmations, exclusions, decisions, pending messages and manual overrides remain equal to the input state.
- [x] 1.4 Implement commit-time candidate revalidation and base Review state token checks; verify candidate changes and stale Review state both reject commit without returning adoptable state or changing the current asset report.

## 2. Main Review Relink Workflow

- [x] 2.1 Route `main.py::_relink_dxf()` to the paused Review Exact Relink flow only when workflow is `REVIEW`, while preserving the existing non-Review Relink path; verify UI workflow tests cover both branches and presentation source contains no hash comparison or DXF validation logic.
- [x] 2.2 Treat file selection as Exact Match adoption authorization: cancel before calling Application, immediately commit an exact plan, and show retry/cancel for mismatch or validation failure; verify no redundant Exact confirmation dialog is displayed.
- [x] 2.3 Add a single Main adoption helper that snapshots and atomically updates Review state, runtime asset status, compatibility status and dirty state, with rollback on any adoption/UI-refresh error; verify ProjectData, ProjectResult, Solver memory and support candidate cache never change.
- [x] 2.4 Preserve the same-session Review cache on Exact Match and resume through the existing `resume_review=True` path without recognition, association rebuild or import completion; verify workflow remains `REVIEW` and no new requires-review items are introduced.
- [x] 2.5 When `_review_resume_source()` cannot find or validate the saved source, offer the same paused Review Relink flow; verify cancel, repeated mismatch and validation failure all preserve the original source reference, paused state, dirty flag and Review cache.

## 3. Persistence and Regression

- [x] 3.1 Integrate a successful Exact Relink with the existing accepted/pending-save asset report without replacing the managed DXF copy during Relink; verify `tests/test_project_persistence.py` proves Save/Load restores the new source relationship and workflow `REVIEW` without a schema-version change.
- [x] 3.2 Add regression coverage showing existing `COMPLETED`／legacy Relink behavior and normal same-source paused Review resume are unchanged; verify the existing project service, persistence and DXF Review workflow suites pass.
- [x] 3.3 After implementation tests pass, update `docs/WORKFLOW.md` so Phase 1 Exact Match is documented as supported while Phase 2 content-changed compatibility／re-binding／partial recovery remains an explicit future item; verify Architecture, Domain and Solver documents require no truth changes.

## 4. Final Verification

- [x] 4.1 Run the focused suites with `.\.venv\Scripts\python.exe -m unittest tests.test_project_service tests.test_dxf_review_workflow tests.test_project_persistence tests.test_interface_presentation tests.test_app_dependencies -v` and resolve all failures without weakening assertions.
- [x] 4.2 Run the full regression suite with `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` and confirm no DXF import, completed Relink, persistence, Project editing or Solver regressions.
- [x] 4.3 Run OpenSpec implementation verification against this change and `openspec validate relink-paused-dxf-review-source --strict`; resolve any mismatch between implementation, tests, proposal, spec, design and completed task checkboxes before archive.
