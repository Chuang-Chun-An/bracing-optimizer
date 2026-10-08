from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dxf_import.corner_brace_repair as corner_brace_repair
import dxf_import.review_workflow as review_workflow_module
from dxf_import.dialog import DXFImportDialog
from dxf_import.importer import DXFImporter
from dxf_import.preview import PreviewScene, RenderDirty
from dxf_import.review_workflow import DXFReviewWorkflow
from tests.sample_dxf_assets import Y05_DXF_PATH, Y29_DXF_PATH


ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "Y05": (
        Y05_DXF_PATH,
        ROOT / "project_cases" / "Y05車站第一層支撐" / "project.json",
        "BM29",
        "E91",
    ),
    "Y29": (
        Y29_DXF_PATH,
        ROOT / "project_cases" / "Y29車站第一層支撐" / "project.json",
        "W11",
        "58D",
    ),
}
MULTI_CASES = {
    "Y05": (("BM29", "E91"), ("S14", "D1A")),
    "Y29": (("W11", "58D"), ("S1", "D7")),
}


def _load_workflow(name: str):
    dxf_path, project_path, display_id, handle = CASES[name]
    state = json.loads(project_path.read_text(encoding="utf-8"))["dxf_import_state"]
    importer = DXFImporter(dxf_path).read()
    workflow = DXFReviewWorkflow(
        importer,
        dxf_path,
        initial_state=state,
        resume_review=True,
    )
    workflow.recognize(state["layer_classification"])
    item = next(
        value for value in workflow.review_items
        if value.display_id == display_id and handle in value.source_handles
    )
    return workflow, importer, item


def benchmark(name: str) -> dict[str, object]:
    workflow, importer, selected = _load_workflow(name)
    timings = {
        "convert_seconds": 0.0,
        "manual_replay_seconds": 0.0,
        "final_validation_seconds": 0.0,
    }
    counts = {
        "convert": 0,
        "manual_replay": 0,
        "build_problem_records": 0,
        "build_review_items": 0,
        "candidate_local_validation": 0,
        "candidate_full_validation": 0,
        "candidate_validation_connection_builds": 0,
        "candidate_validation_connection_max_corner_count": 0,
    }
    local_validation_depth = 0

    original_convert = importer.convert
    original_replay = review_workflow_module.replay_manual_overrides
    original_records = review_workflow_module.build_problem_records
    original_items = review_workflow_module.build_review_items
    original_local = corner_brace_repair._candidate_passes_local_validation
    original_full = corner_brace_repair._candidate_passes_full_validation
    original_connections = corner_brace_repair.build_corner_brace_connections

    def timed_convert(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original_convert(*args, **kwargs)
        finally:
            timings["convert_seconds"] += time.perf_counter() - started
            counts["convert"] += 1

    def timed_replay(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original_replay(*args, **kwargs)
        finally:
            timings["manual_replay_seconds"] += time.perf_counter() - started
            counts["manual_replay"] += 1

    def timed_records(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original_records(*args, **kwargs)
        finally:
            timings["final_validation_seconds"] += time.perf_counter() - started
            counts["build_problem_records"] += 1

    def timed_items(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original_items(*args, **kwargs)
        finally:
            timings["final_validation_seconds"] += time.perf_counter() - started
            counts["build_review_items"] += 1

    def counted_local(*args, **kwargs):
        nonlocal local_validation_depth
        counts["candidate_local_validation"] += 1
        local_validation_depth += 1
        try:
            return original_local(*args, **kwargs)
        finally:
            local_validation_depth -= 1

    def counted_full(*args, **kwargs):
        counts["candidate_full_validation"] += 1
        return original_full(*args, **kwargs)

    def counted_connections(result, *args, **kwargs):
        if local_validation_depth:
            counts["candidate_validation_connection_builds"] += 1
            counts["candidate_validation_connection_max_corner_count"] = max(
                counts["candidate_validation_connection_max_corner_count"],
                len(result.corner_braces),
            )
        return original_connections(result, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.object(importer, "convert", side_effect=timed_convert))
        stack.enter_context(
            patch.object(
                review_workflow_module,
                "replay_manual_overrides",
                side_effect=timed_replay,
            )
        )
        stack.enter_context(
            patch.object(
                review_workflow_module,
                "build_problem_records",
                side_effect=timed_records,
            )
        )
        stack.enter_context(
            patch.object(
                review_workflow_module,
                "build_review_items",
                side_effect=timed_items,
            )
        )
        stack.enter_context(
            patch.object(
                corner_brace_repair,
                "_candidate_passes_local_validation",
                side_effect=counted_local,
            )
        )
        stack.enter_context(
            patch.object(
                corner_brace_repair,
                "_candidate_passes_full_validation",
                side_effect=counted_full,
            )
        )
        stack.enter_context(
            patch.object(
                corner_brace_repair,
                "build_corner_brace_connections",
                side_effect=counted_connections,
            )
        )
        started = time.perf_counter()
        plan, restoring, identity = workflow.plan_source_exclusion_for_item(selected)
        plan_seconds = time.perf_counter() - started

    started = time.perf_counter()
    mutation = workflow.commit_source_exclusion_plan(plan)
    commit_seconds = time.perf_counter() - started

    dialog = DXFImportDialog.__new__(DXFImportDialog)
    dialog.result = workflow.result
    dialog.review_workflow = workflow
    dialog.preview_renderer = object()
    dialog.preview_transform = (1.0, 1.0, 0.0, 0.0, 1.0)
    dialog._preview_scene_revision = workflow.revision - 1
    dialog._preview_source_geometry_signature = (
        dialog._dialog_source_geometry_signature(workflow.result)
    )
    dialog.preview_scene = PreviewScene(
        source_handle_items={
            geometry.source_handle: [index]
            for index, geometry in enumerate(workflow.result.source_geometry, start=1)
        }
    )
    dialog._pending_source_style_handles = set()
    dialog._preview_intersects = lambda _points: False
    started = time.perf_counter()
    dirty = dialog._source_exclusion_render_dirty(mutation.effects)
    refresh_seconds = time.perf_counter() - started

    started = time.perf_counter()
    debug_text = json.dumps(
        {
            "review_revision": workflow.revision,
            "result": workflow.result.to_debug_dict(),
            "manual_replay": {
                "preserved": plan.manual_replay.preserved,
                "needs_review": plan.manual_replay.needs_review,
                "disabled": plan.manual_replay.disabled,
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    debug_seconds = time.perf_counter() - started

    return {
        "case": name,
        "selected": selected.display_id,
        "source_identity": identity,
        "restoring": restoring,
        "plan_seconds": round(plan_seconds, 6),
        **{key: round(value, 6) for key, value in timings.items()},
        "commit_seconds": round(commit_seconds, 6),
        "refresh_projection_seconds": round(refresh_seconds, 6),
        "debug_serialization_seconds": round(debug_seconds, 6),
        "debug_payload_bytes": len(debug_text.encode("utf-8")),
        "projection_build_count": (
            counts["build_problem_records"] + counts["build_review_items"]
        ),
        "repair_count": sum(
            label.endswith("CornerBrace repair")
            for label in (
                *plan.manual_replay.preserved,
                *plan.manual_replay.needs_review,
                *plan.manual_replay.disabled,
            )
        ),
        "manual_replay": {
            "preserved": len(plan.manual_replay.preserved),
            "needs_review": len(plan.manual_replay.needs_review),
            "disabled": len(plan.manual_replay.disabled),
        },
        "work_counts": counts,
        "render_dirty": [
            flag.name for flag in RenderDirty
            if flag is not RenderDirty.NONE and dirty & flag
        ],
        "revision": workflow.revision,
    }


def _measure_refresh_projection(workflow, effects) -> float:
    dialog = DXFImportDialog.__new__(DXFImportDialog)
    dialog.result = workflow.result
    dialog.review_workflow = workflow
    dialog.preview_renderer = object()
    dialog.preview_transform = (1.0, 1.0, 0.0, 0.0, 1.0)
    dialog._preview_scene_revision = workflow.revision - 1
    dialog._preview_source_geometry_signature = (
        dialog._dialog_source_geometry_signature(workflow.result)
    )
    dialog.preview_scene = PreviewScene(
        source_handle_items={
            geometry.source_handle: [index]
            for index, geometry in enumerate(
                workflow.result.source_geometry,
                start=1,
            )
        }
    )
    dialog._pending_source_style_handles = set()
    dialog._preview_intersects = lambda _points: False
    started = time.perf_counter()
    dialog._source_exclusion_render_dirty(effects)
    return time.perf_counter() - started


def _benchmark_multi_flow(name: str, *, batched: bool) -> dict[str, object]:
    workflow, importer, _selected = _load_workflow(name)
    targets = MULTI_CASES[name]
    counts = {"convert": 0, "manual_replay": 0, "commit": 0, "refresh": 0}
    timings = {
        "plan_seconds": 0.0,
        "commit_seconds": 0.0,
        "refresh_projection_seconds": 0.0,
    }
    original_convert = importer.convert
    original_replay = review_workflow_module.replay_manual_overrides

    def counted_convert(*args, **kwargs):
        counts["convert"] += 1
        return original_convert(*args, **kwargs)

    def counted_replay(*args, **kwargs):
        counts["manual_replay"] += 1
        return original_replay(*args, **kwargs)

    started_wall = time.perf_counter()
    with patch.object(importer, "convert", side_effect=counted_convert), patch.object(
        review_workflow_module,
        "replay_manual_overrides",
        side_effect=counted_replay,
    ):
        if batched:
            for display_id, handle in targets:
                item = next(
                    value
                    for value in workflow.review_items
                    if value.display_id == display_id
                    and handle in value.source_handles
                )
                workflow.mark_source_exclusion(item)
            started = time.perf_counter()
            plan = workflow.plan_pending_source_exclusions()
            timings["plan_seconds"] += time.perf_counter() - started
            started = time.perf_counter()
            mutation = workflow.commit_source_exclusion_plan(plan)
            timings["commit_seconds"] += time.perf_counter() - started
            counts["commit"] += 1
            timings["refresh_projection_seconds"] += _measure_refresh_projection(
                workflow,
                mutation.effects,
            )
            counts["refresh"] += 1
        else:
            for display_id, handle in targets:
                item = next(
                    value
                    for value in workflow.review_items
                    if value.display_id == display_id
                    and handle in value.source_handles
                )
                started = time.perf_counter()
                plan, _restoring, _identity = (
                    workflow.plan_source_exclusion_for_item(item)
                )
                timings["plan_seconds"] += time.perf_counter() - started
                started = time.perf_counter()
                mutation = workflow.commit_source_exclusion_plan(plan)
                timings["commit_seconds"] += time.perf_counter() - started
                counts["commit"] += 1
                timings["refresh_projection_seconds"] += (
                    _measure_refresh_projection(workflow, mutation.effects)
                )
                counts["refresh"] += 1
    wall_seconds = time.perf_counter() - started_wall
    return {
        "mode": "multi_pending" if batched else "repeated_single",
        "source_count": len(targets),
        "work_counts": counts,
        **{key: round(value, 6) for key, value in timings.items()},
        "wall_seconds": round(wall_seconds, 6),
        "revision": workflow.revision,
        "excluded_source_count": len(workflow.excluded_sources),
    }


def benchmark_multi(name: str) -> dict[str, object]:
    return {
        "case": name,
        "targets": MULTI_CASES[name],
        "repeated_single": _benchmark_multi_flow(name, batched=False),
        "multi_pending": _benchmark_multi_flow(name, batched=True),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--multi",
        action="store_true",
        help="compare repeated single-source commits with one multi-pending commit",
    )
    parser.add_argument("cases", nargs="*", choices=tuple(CASES), default=tuple(CASES))
    args = parser.parse_args()
    runner = benchmark_multi if args.multi else benchmark
    print(json.dumps([runner(name) for name in args.cases], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
