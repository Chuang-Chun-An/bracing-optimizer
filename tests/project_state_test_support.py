"""Shared assertions for formal project runtime state boundaries."""

from __future__ import annotations

import copy


def formal_state_snapshot(app, *, recovery_path=None):
    project = app._ensure_project_data()
    results = app._ensure_project_results()
    solver_memory = getattr(app, "solver_memory", {})
    support_cache = getattr(app, "support_candidate_cache", {})
    snapshot = {
        "project_ref": project,
        "project_value": copy.deepcopy(project.to_case_data()),
        "results_ref": results,
        "result_items": copy.deepcopy(results.result_items),
        "result_payload": copy.deepcopy(results.persisted_payload),
        "calculated_time": results.last_calculated_time,
        "solver_memory_ref": solver_memory,
        "solver_memory": copy.deepcopy(solver_memory),
        "support_cache_ref": support_cache,
        "support_cache": copy.deepcopy(support_cache),
        "dxf_workflow": getattr(app, "dxf_workflow_status", None),
        "dxf_review": copy.deepcopy(
            getattr(app, "dxf_review_session", None)
        ),
        "dxf_state": copy.deepcopy(
            getattr(app, "dxf_last_import_debug", None)
        ),
        "dxf_asset": copy.deepcopy(getattr(app, "dxf_asset", None)),
        "dxf_status_ref": getattr(app, "dxf_asset_status_report", None),
        "compatibility_ref": getattr(
            app, "last_dxf_compatibility_report", None
        ),
        "cad_validation_ref": getattr(
            app, "last_cad_validation_report", None
        ),
        "dirty": bool(getattr(app, "project_dirty", False)),
        "dirty_reason": str(getattr(app, "project_dirty_reason", "") or ""),
        "current_path": getattr(app, "current_project_path", None),
        "projection_stale": bool(getattr(app, "projection_stale", False)),
        "cad_ack_event_id": getattr(
            app, "cad_ack_unresolved_event_id", None
        ),
    }
    if recovery_path is not None:
        snapshot["recovery_exists"] = recovery_path.exists()
        snapshot["recovery_bytes"] = (
            recovery_path.read_bytes() if recovery_path.is_file() else None
        )
    return snapshot


def assert_formal_state_unchanged(testcase, before, app, *, recovery_path=None):
    after = formal_state_snapshot(app, recovery_path=recovery_path)
    for key in (
        "project_ref",
        "results_ref",
        "solver_memory_ref",
        "support_cache_ref",
        "dxf_status_ref",
        "compatibility_ref",
        "cad_validation_ref",
    ):
        testcase.assertIs(after[key], before[key], key)
    for key in before.keys() - {
        "project_ref",
        "results_ref",
        "solver_memory_ref",
        "support_cache_ref",
        "dxf_status_ref",
        "compatibility_ref",
        "cad_validation_ref",
    }:
        testcase.assertEqual(after[key], before[key], key)

