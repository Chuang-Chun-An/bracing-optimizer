from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bracing_optimizer.application.optimize_waler import OptimizeWaler, SINGLE_TOP_5
from bracing_optimizer.application.optimize_waler_global import (
    OptimizeWalerGlobal,
    OptimizeWalerGlobalRequest,
)
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.solver_input_builder import WalerInputBuilder
from bracing_optimizer.domain.material_rules import MaterialRatioTargets
from dxf_import.dialog import DXFImportDialog
from dxf_import.importer import DXFImporter, default_layer_mapping_for_file
from tests.sample_dxf_assets import Y05_DXF_PATH, Y1A_DXF_PATH, Y29_DXF_PATH


PATHS = {
    "Y05": Y05_DXF_PATH,
    "Y29": Y29_DXF_PATH,
    "Y1A": Y1A_DXF_PATH,
}

PROJECT_PATHS = {
    "Y05": Path("project_cases/Y05車站第一層支撐/project.json"),
    "Y29": Path("project_cases/Y29車站第一層支撐/project.json"),
}


class TopFiveOptimizeWaler(OptimizeWaler):
    def execute(self, request, **kwargs):
        kwargs["retention_profile"] = SINGLE_TOP_5
        return super().execute(request, **kwargs)


def build_inputs(name: str):
    project_path = PROJECT_PATHS.get(name)
    if project_path is not None:
        payload = json.loads(project_path.read_text(encoding="utf-8"))
        project = ProjectDataModel.from_case_data(payload["input_data"])
        return tuple(WalerInputBuilder.build_all(project).values())

    path = PATHS[name]
    importer = DXFImporter(path).read()
    defaults = default_layer_mapping_for_file(path)
    layer_roles = {
        layer: DXFImportDialog.USE_TO_ROLE[defaults.get(layer, "忽略")]
        for layer in importer.layer_names
    }
    result = importer.convert(layer_roles=layer_roles)
    spec = "H400x400"
    project = ProjectDataModel(
        walers=[dict(item.to_project_row(), material_spec=spec) for item in result.walers],
        struts=[item.to_project_row() for item in result.struts],
        braces=[item.to_project_row() for item in result.braces],
        inventory=[
            {
                "ItemCode": f"W-{length}",
                "Spec": spec,
                "Usage": "圍令",
                "Length": length,
                "Qty": 999,
            }
            for length in range(1_000, 10_001, 500)
        ],
    )
    return tuple(WalerInputBuilder.build_all(project).values())


def repair_test_lengths(inputs):
    repaired = []
    records = []
    for item in inputs:
        length = int(item.total_length)
        gap = length - (length // 500) * 500
        if (
            str(item.material_spec or "").strip().casefold() == "rc"
            or gap <= 200
        ):
            repaired.append(item)
            continue
        target = max(500, ((length + 250) // 500) * 500)
        start_x, start_y = item.start_point
        end_x, end_y = item.end_point
        scale = target / length
        repaired_end = (
            start_x + (end_x - start_x) * scale,
            start_y + (end_y - start_y) * scale,
        )
        repaired.append(replace(
            item,
            end_point=repaired_end,
            total_length=target,
        ))
        records.append({
            "waler_id": item.waler_id,
            "original_length": length,
            "repaired_length": target,
            "original_gap": gap,
        })
    return tuple(repaired), records


def summarize(result, elapsed: float):
    solution = result.solution
    diagnostics = result.diagnostics
    total = solution.total_short + solution.total_mid + solution.total_long + solution.total_out
    selected = {
        item.waler_id: {
            "rank": item.candidate_rank,
            "segments": list(item.segments),
            "local_score": item.local_score,
            "local_regret": item.local_regret,
            "material_signature": list(item.material_signature),
        }
        for item in solution.selected_candidates
    }
    counts = dict(diagnostics.raw_candidate_counts_by_waler)
    return {
        "elapsed_seconds": elapsed,
        "valid": solution.valid,
        "reason": solution.reason,
        "per_waler_candidate_counts": counts,
        "per_waler_retained_candidate_counts": dict(
            diagnostics.retained_candidate_counts_by_waler
        ),
        "top_three_candidate_counts": sorted(
            counts.items(), key=lambda item: -item[1]
        )[:3],
        "dp_candidate_total": diagnostics.retained_candidate_count_after_signature_merge,
        "transition_count": diagnostics.transition_count,
        "max_active_state_count": diagnostics.max_active_state_count,
        "selected": selected,
        "changed_waler_ids": list(solution.changed_waler_ids),
        "objective": list(solution.objective_tuple),
        "total_out_distance_mm": solution.total_out_distance_mm,
        "ratio_deviation": solution.ratio_deviation,
        "total_local_regret": solution.total_local_regret,
        "changed_waler_count": solution.changed_waler_count,
        "material_counts": {
            "short": solution.total_short,
            "mid": solution.total_mid,
            "long": solution.total_long,
            "out": solution.total_out,
        },
        "material_percentages": {
            "short": solution.total_short / total if total else 0.0,
            "mid": solution.total_mid / total if total else 0.0,
            "long": solution.total_long / total if total else 0.0,
            "out": solution.total_out / total if total else 0.0,
        },
    }


def run(name: str):
    inputs = build_inputs(name)
    repairs = []
    if name in PROJECT_PATHS:
        inputs, repairs = repair_test_lengths(inputs)
    request = OptimizeWalerGlobalRequest(
        waler_inputs=inputs,
        material_ratio_targets=MaterialRatioTargets.normalized(20, 50, 30),
    )
    outputs = {
        "fixture": name,
        "source": (
            str(PROJECT_PATHS[name])
            if name in PROJECT_PATHS
            else str(PATHS[name])
        ),
        "waler_count": len(inputs),
        "test_length_repairs": repairs,
        "profiles": {},
    }
    for profile, optimizer in (
        ("top_5", OptimizeWalerGlobal(TopFiveOptimizeWaler)),
        ("global_final_population", OptimizeWalerGlobal()),
    ):
        started = time.perf_counter()
        result = optimizer.execute(request, logger=lambda *args: None)
        outputs["profiles"][profile] = summarize(
            result,
            time.perf_counter() - started,
        )
    baseline = outputs["profiles"]["top_5"]
    expanded = outputs["profiles"]["global_final_population"]
    outputs["selection_changed"] = baseline["selected"] != expanded["selected"]
    outputs["changed_selected_waler_ids"] = sorted(
        waler_id
        for waler_id in set(baseline["selected"]) | set(expanded["selected"])
        if baseline["selected"].get(waler_id) != expanded["selected"].get(waler_id)
    )
    return outputs


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1]), ensure_ascii=False, indent=2))
