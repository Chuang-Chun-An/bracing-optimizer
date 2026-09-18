"""Application model for persisted Solver results and material usage."""

from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from bracing_optimizer.algorithms import solver_search, support


QuantityLookup = Callable[[str, str, int | float], int | float]


class MaterialDetailBuildError(ValueError):
    """Raised when one visible result contains invalid material piece data."""


@dataclass(frozen=True)
class MaterialDetailRow:
    """One physical material piece selected by a visible result plan."""

    result_id: str
    usage: str
    member_id: str
    zoning: str
    piece_index: int
    material_type: str
    material_spec: str
    length: int | float
    quantity: int = 1


@dataclass(frozen=True)
class SolverDiagnosticView:
    """Stable Application projection of Solver search diagnostics."""

    legal_solution_found: bool
    search_was_escalated: bool
    result_is_stable: bool
    search_limit_reached: bool
    main_issue_message: str
    affected_component_ids: tuple[str, ...]
    component_candidate_counts: dict[str, object]


@dataclass(frozen=True)
class GlobalWalerApplyPlan:
    """Staged result-state replacement for one global Waler solution."""

    result_items: dict[str, dict]
    selected_candidates: tuple[Any, ...]
    changed_waler_ids: tuple[str, ...]
    solution: Any


@dataclass(frozen=True)
class SingleWalerApplyPlan:
    """Staged result-state replacement for one single-Waler solve."""

    result_items: dict[str, dict]
    waler_id: str
    result_count: int
    preserved_global_result: bool
    search_diagnostics: Any


@dataclass
class ProjectResultModel:
    """Own the data-only result state stored with one project."""

    result_items: dict[str, dict] = field(default_factory=dict)
    last_calculated_time: str | None = None
    persisted_payload: dict | None = None

    @staticmethod
    def waler_result_identity(result_id: str, item: Mapping) -> str:
        """Return the exact Waler ID, including the supported legacy fallback."""

        if not isinstance(item, Mapping) or item.get("type") != "waler":
            return ""
        result = item.get("result")
        if isinstance(result, Mapping):
            explicit_id = str(result.get("waler_id", "") or "").strip()
            if explicit_id:
                return explicit_id
        legacy_id, separator, _suffix = str(result_id or "").partition("-方案")
        return legacy_id.strip() if separator else ""

    @staticmethod
    def serialize_support_plan(plan) -> dict:
        return {
            "support_id": getattr(plan, "support_id", ""),
            "pieces": [
                list(piece) for piece in getattr(plan, "pieces", []) or []
            ],
            "joints": list(getattr(plan, "joints", []) or []),
            "gap": getattr(plan, "gap", 0),
            "jack_center": getattr(plan, "jack_center", 0),
            "jack_region_id": getattr(plan, "jack_region_id", 0),
            "score": getattr(plan, "score", 0),
            "valid": bool(getattr(plan, "valid", False)),
            "pile_centers": list(getattr(plan, "pile_centers", []) or []),
            "waler_centers": list(getattr(plan, "waler_centers", []) or []),
            "reason": getattr(plan, "reason", ""),
            "breakdown": dict(getattr(plan, "breakdown", {}) or {}),
            "material_spec": getattr(plan, "material_spec", ""),
            "shared_layout_group": getattr(plan, "shared_layout_group", ""),
        }

    @staticmethod
    def deserialize_support_plan(data: Mapping) -> support.SupportPlan:
        return support.SupportPlan(
            support_id=str(data.get("support_id", "") or ""),
            pieces=[
                (str(piece[0]), int(piece[1]))
                for piece in list(data.get("pieces", []) or [])
                if isinstance(piece, (list, tuple)) and len(piece) == 2
            ],
            joints=list(data.get("joints", []) or []),
            gap=data.get("gap", 0),
            jack_center=data.get("jack_center", 0),
            jack_region_id=data.get("jack_region_id", 0),
            score=data.get("score", 0),
            valid=bool(data.get("valid", False)),
            pile_centers=list(data.get("pile_centers", []) or []),
            waler_centers=list(data.get("waler_centers", []) or []),
            reason=str(data.get("reason", "") or ""),
            breakdown=dict(data.get("breakdown", {}) or {}),
            material_spec=str(data.get("material_spec", "") or ""),
            shared_layout_group=str(
                data.get("shared_layout_group", "") or ""
            ),
        )

    @classmethod
    def serialize_result_item(cls, result_id: str, item: Mapping) -> dict:
        result_type = item.get("type")
        result = item.get("result")
        if result_type == "support":
            serialized_result = {
                "total_score": getattr(result, "total_score", 0),
                "valid": bool(getattr(result, "valid", False)),
                "reason": getattr(result, "reason", ""),
                "single_score_total": getattr(result, "single_score_total", 0),
                "jack_region_penalty": getattr(result, "jack_region_penalty", 0),
                "material_ratio_penalty": getattr(
                    result,
                    "material_ratio_penalty",
                    0,
                ),
                "material_ratio_analysis": copy.deepcopy(
                    getattr(result, "material_ratio_analysis", {}) or {}
                ),
                "material_ratio_targets": copy.deepcopy(
                    getattr(result, "material_ratio_targets", {}) or {}
                ),
                "material_ratio_weight": getattr(
                    result,
                    "material_ratio_weight",
                    support.SUPPORT_MATERIAL_RATIO_WEIGHT,
                ),
                "min_jack_distance": getattr(result, "min_jack_distance", None),
                "search_diagnostics": copy.deepcopy(
                    getattr(result, "search_diagnostics", {}) or {}
                ),
                "plans": [
                    cls.serialize_support_plan(plan)
                    for plan in list(getattr(result, "plans", []) or [])
                ],
            }
        else:
            serialized_result = copy.deepcopy(result)

        payload = {
            "id": result_id,
            "type": result_type,
            "visible": bool(item.get("visible", True)),
            "result": serialized_result,
        }
        if "support_visibility" in item:
            payload["support_visibility"] = copy.deepcopy(
                item.get("support_visibility") or {}
            )
        return payload

    @classmethod
    def deserialize_result_item(cls, payload: Mapping) -> dict:
        result_type = payload.get("type")
        result = payload.get("result")
        if result_type == "support" and isinstance(result, Mapping):
            result = support.GlobalSolution(
                plans=[
                    cls.deserialize_support_plan(plan_data)
                    for plan_data in list(result.get("plans", []) or [])
                    if isinstance(plan_data, Mapping)
                ],
                total_score=result.get("total_score", 0),
                valid=bool(result.get("valid", False)),
                reason=str(result.get("reason", "") or ""),
                single_score_total=result.get("single_score_total", 0),
                jack_region_penalty=result.get("jack_region_penalty", 0),
                material_ratio_penalty=result.get("material_ratio_penalty", 0),
                material_ratio_analysis=dict(
                    result.get("material_ratio_analysis", {}) or {}
                ),
                material_ratio_targets=dict(
                    result.get("material_ratio_targets", {}) or {}
                ),
                material_ratio_weight=result.get(
                    "material_ratio_weight",
                    support.SUPPORT_MATERIAL_RATIO_WEIGHT,
                ),
                min_jack_distance=result.get("min_jack_distance", None),
                search_diagnostics=dict(
                    result.get("search_diagnostics", {}) or {}
                ),
            )
        else:
            result = copy.deepcopy(result)

        item = {
            "type": result_type,
            "result": result,
            "visible": bool(payload.get("visible", True)),
        }
        if isinstance(payload.get("support_visibility"), Mapping):
            item["support_visibility"] = copy.deepcopy(
                payload["support_visibility"]
            )
        return item

    @classmethod
    def from_payload(cls, payload: Mapping | None) -> "ProjectResultModel":
        if not isinstance(payload, Mapping):
            return cls()
        best_solution = payload.get("best_solution") or {}
        result_items = {}
        if isinstance(best_solution, Mapping):
            for item_payload in list(best_solution.get("result_items", []) or []):
                if not isinstance(item_payload, Mapping):
                    continue
                result_id = str(item_payload.get("id", "") or "").strip()
                if result_id:
                    result_items[result_id] = cls.deserialize_result_item(
                        item_payload
                    )
        return cls(
            result_items=result_items,
            last_calculated_time=payload.get("last_calculated_time"),
            persisted_payload=copy.deepcopy(dict(payload)),
        )

    def to_payload(
        self,
        material_summary: Sequence[Mapping],
        *,
        now: Callable[[], datetime] = datetime.now,
    ) -> dict | None:
        if not self.result_items:
            return None
        calculated_time = self.last_calculated_time or now().isoformat(
            timespec="seconds"
        )
        return {
            "last_calculated_time": calculated_time,
            "material_summary": copy.deepcopy(list(material_summary)),
            "best_solution": {
                "result_items": [
                    self.serialize_result_item(result_id, item)
                    for result_id, item in sorted(self.result_items.items())
                ],
            },
        }

    def clear(self) -> None:
        self.result_items.clear()
        self.last_calculated_time = None
        self.persisted_payload = None

    @staticmethod
    def solver_diagnostic_view(value) -> SolverDiagnosticView | None:
        """Normalize an algorithm diagnostic into a UI-safe result view."""

        diagnostics = solver_search.SolverDiagnostics.from_dict(value)
        if diagnostics is None:
            return None
        return SolverDiagnosticView(
            legal_solution_found=bool(diagnostics.legal_solution_found),
            search_was_escalated=bool(diagnostics.search_was_escalated),
            result_is_stable=bool(diagnostics.result_is_stable),
            search_limit_reached=bool(diagnostics.search_limit_reached),
            main_issue_message=str(diagnostics.main_issue_message or ""),
            affected_component_ids=tuple(
                str(component_id)
                for component_id in (diagnostics.affected_component_ids or ())
            ),
            component_candidate_counts={
                str(component_id): count
                for component_id, count in (
                    diagnostics.component_candidate_counts or {}
                ).items()
            },
        )

    def store_item(self, result_id: str, result_type: str, result) -> bool:
        """Store one visible Solver result under a non-empty identity."""

        result_id = str(result_id).strip()
        if not result_id:
            return False
        self.result_items[result_id] = {
            "type": result_type,
            "result": result,
            "visible": True,
        }
        return True

    def mark_updated(
        self,
        material_summary: Sequence[Mapping],
        *,
        now: Callable[[], datetime] = datetime.now,
    ) -> dict | None:
        """Refresh persisted result metadata after an application mutation."""

        self.last_calculated_time = now().isoformat(timespec="seconds")
        self.persisted_payload = self.to_payload(material_summary, now=now)
        return self.persisted_payload

    def stage_waler_global_result(self, global_result) -> GlobalWalerApplyPlan:
        """Validate and stage all result items selected by a global solve."""

        solution = getattr(global_result, "solution", None)
        diagnostics = getattr(global_result, "diagnostics", None)
        if solution is None or not bool(getattr(solution, "valid", False)):
            raise ValueError("全域圍令結果無效，未套用任何成果。")

        selected_candidates = tuple(
            getattr(solution, "selected_candidates", ()) or ()
        )
        selected_ids = [
            str(candidate.waler_id or "").strip()
            for candidate in selected_candidates
        ]
        if (
            not selected_candidates
            or any(not waler_id for waler_id in selected_ids)
            or len(selected_ids) != len(set(selected_ids))
        ):
            raise ValueError("全域圍令結果未對每支圍令提供唯一候選。")

        targets = dict(getattr(diagnostics, "target_ratio", {}) or {})
        raw_global_diagnostics = (
            diagnostics.to_dict()
            if diagnostics is not None and hasattr(diagnostics, "to_dict")
            else copy.deepcopy(diagnostics)
        )
        global_diagnostics = (
            dict(raw_global_diagnostics)
            if isinstance(raw_global_diagnostics, Mapping)
            else {}
        )
        changed_ids = tuple(
            getattr(solution, "changed_waler_ids", ()) or ()
        )
        global_diagnostics["solution_summary"] = {
            "total_short": solution.total_short,
            "total_mid": solution.total_mid,
            "total_long": solution.total_long,
            "total_out": solution.total_out,
            "short_ratio": solution.short_ratio,
            "mid_ratio": solution.mid_ratio,
            "long_ratio": solution.long_ratio,
            "ratio_deviation": solution.ratio_deviation,
            "total_out_distance_mm": solution.total_out_distance_mm,
            "changed_waler_count": solution.changed_waler_count,
            "changed_waler_ids": list(changed_ids),
        }

        staged_items = copy.deepcopy(self.result_items)
        selected_id_set = set(selected_ids)
        for result_id in list(staged_items):
            if self.waler_result_identity(
                result_id,
                staged_items[result_id],
            ) in selected_id_set:
                staged_items.pop(result_id)

        for candidate in selected_candidates:
            record = global_result.local_result_for(candidate.waler_id)
            if record is None:
                raise ValueError(
                    f"全域結果缺少圍令 {candidate.waler_id} 的單支求解資料。"
                )
            waler_input = record.waler_input
            plan = copy.deepcopy(dict(candidate.payload))
            plan["ratio_targets"] = dict(targets)
            plan["segment_counts"] = {
                "short": candidate.short_count,
                "mid": candidate.mid_count,
                "long": candidate.long_count,
            }
            plan["global_candidate_rank"] = candidate.candidate_rank
            plan["global_local_regret"] = candidate.local_regret
            plan["global_material_counts"] = {
                "short": candidate.short_count,
                "mid": candidate.mid_count,
                "long": candidate.long_count,
                "out": candidate.out_count,
            }
            plan["global_out_distance_mm"] = candidate.out_distance_mm
            local_diagnostics = getattr(record.result, "diagnostics", None)
            result_id = f"{candidate.waler_id}-方案{candidate.candidate_rank}"
            staged_items[result_id] = {
                "type": "waler",
                "result": {
                    "waler_id": candidate.waler_id,
                    "option_index": candidate.candidate_rank,
                    "selected_plan": plan,
                    "ratio_targets": dict(targets),
                    "required_length": int(round(waler_input.total_length)),
                    "forbidden_points": list(waler_input.forbidden_points),
                    "joint_clearance": 300,
                    "min_piece_length": 1000,
                    "max_piece_length": 10000,
                    "material_spec": waler_input.material_spec,
                    "search_diagnostics": (
                        local_diagnostics.to_dict()
                        if local_diagnostics is not None
                        and hasattr(local_diagnostics, "to_dict")
                        else copy.deepcopy(local_diagnostics)
                    ),
                    "global_search_diagnostics": copy.deepcopy(
                        global_diagnostics
                    ),
                    "global_selected": True,
                    "result_series": "global",
                },
                "visible": True,
            }

        return GlobalWalerApplyPlan(
            result_items=staged_items,
            selected_candidates=selected_candidates,
            changed_waler_ids=changed_ids,
            solution=solution,
        )

    def stage_single_waler_result(
        self,
        result: Mapping,
        walers: Sequence[Mapping],
    ) -> SingleWalerApplyPlan:
        """Validate and stage the top plans produced for one Waler."""

        waler_id = str(result.get("waler_id", "") or "").strip()
        if not waler_id:
            raise ValueError("錯誤：圍令結果缺少圍令編號")

        top_results = result.get("top_results")
        if top_results is None:
            selected_plan = result.get("selected_plan")
            top_results = [selected_plan] if selected_plan else []
        top_results = list(top_results or [])[:5]
        if not top_results:
            raise ValueError(f"錯誤：{waler_id} 沒有可儲存的圍令方案")

        ratio_targets = result.get("ratio_targets")
        required_length = result.get("required_length")
        forbidden_points = list(result.get("forbidden_points") or [])
        joint_clearance = result.get("joint_clearance", 300)
        min_piece_length = result.get("min_piece_length", 1000)
        max_piece_length = result.get("max_piece_length", 10000)
        search_diagnostics = copy.deepcopy(result.get("search_diagnostics"))
        material_spec = str(result.get("material_spec", "") or "").strip()
        if not material_spec:
            for row in walers:
                if str(row.get("WalerID", "") or "").strip() == waler_id:
                    material_spec = str(
                        row.get("material_spec", "") or ""
                    ).strip()
                    break

        staged_items = copy.deepcopy(self.result_items)
        existing_waler_results = [
            (result_id, item)
            for result_id, item in staged_items.items()
            if self.waler_result_identity(result_id, item) == waler_id
        ]
        has_global_result = any(
            bool(item["result"].get("global_selected"))
            for _result_id, item in existing_waler_results
        )
        old_result_ids = [
            result_id
            for result_id, item in existing_waler_results
            if not bool(item["result"].get("global_selected"))
        ]
        for result_id in old_result_ids:
            staged_items.pop(result_id, None)

        for index, plan in enumerate(top_results, start=1):
            result_id = (
                f"{waler_id}-單支方案{index}"
                if has_global_result
                else f"{waler_id}-方案{index}"
            )
            staged_items[result_id] = {
                "type": "waler",
                "result": {
                    "waler_id": waler_id,
                    "option_index": index,
                    "selected_plan": plan,
                    "ratio_targets": ratio_targets or plan.get("ratio_targets"),
                    "required_length": required_length,
                    "forbidden_points": forbidden_points,
                    "joint_clearance": joint_clearance,
                    "min_piece_length": min_piece_length,
                    "max_piece_length": max_piece_length,
                    "material_spec": material_spec,
                    "search_diagnostics": search_diagnostics,
                    "result_series": "single" if has_global_result else "",
                },
                "visible": False,
            }

        return SingleWalerApplyPlan(
            result_items=staged_items,
            waler_id=waler_id,
            result_count=len(top_results),
            preserved_global_result=has_global_result,
            search_diagnostics=search_diagnostics,
        )

    @staticmethod
    def material_length_key(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number) or number <= 0:
            return None
        return int(number) if number.is_integer() else number

    @staticmethod
    def support_plan_visible(item: dict, support_id: str) -> bool:
        visibility = item.setdefault("support_visibility", {})
        support_id = str(support_id)
        if support_id not in visibility:
            visibility[support_id] = item.get("visible", True)
        return bool(visibility.get(support_id, True))

    @classmethod
    def _material_detail_row(
        cls,
        *,
        result_id: str,
        usage: str,
        member_id: str,
        zoning: str,
        piece_index: int,
        material_type,
        material_spec: str,
        value,
    ) -> MaterialDetailRow:
        length = cls.material_length_key(value)
        if length is None:
            raise MaterialDetailBuildError(
                f"{usage} {member_id} 的第 {piece_index} 段材料長度無效：{value!r}"
            )
        return MaterialDetailRow(
            result_id=str(result_id),
            usage=usage,
            member_id=member_id,
            zoning=zoning,
            piece_index=piece_index,
            material_type=str(material_type or "").strip().lower() or "other",
            material_spec=material_spec,
            length=length,
        )

    @staticmethod
    def _waler_material_pieces(plan: Mapping) -> list[tuple[object, object]]:
        pieces = list(plan.get("pieces", []) or [])
        if pieces:
            return pieces

        segments = list(plan.get("segments", []) or [])
        if not segments:
            segments = [
                assignment.get("stock_length")
                for assignment in list(plan.get("assignments", []) or [])
                if isinstance(assignment, Mapping)
            ]
        pieces = [("steel", length) for length in segments]
        adjustment = ProjectResultModel.material_length_key(
            plan.get("tail_adjustment", 0)
        )
        if adjustment is not None:
            pieces.append(("shim", adjustment))
        return pieces

    def collect_visible_material_details(self) -> list[MaterialDetailRow]:
        """Return one row per physical piece in the currently visible plans."""

        details = []
        for result_id, item in sorted(self.result_items.items()):
            if not item.get("visible", True):
                continue
            result = item.get("result")
            if item.get("type") == "waler":
                if not isinstance(result, Mapping):
                    continue
                plan = result.get("selected_plan") or {}
                if not isinstance(plan, Mapping):
                    continue
                member_id = str(
                    result.get("waler_id", "") or result_id
                ).strip()
                material_spec = str(
                    result.get("material_spec", "") or ""
                ).strip()
                for piece_index, piece in enumerate(
                    self._waler_material_pieces(plan),
                    start=1,
                ):
                    if not isinstance(piece, (list, tuple)) or len(piece) != 2:
                        raise MaterialDetailBuildError(
                            f"圍令 {member_id} 的第 {piece_index} 段材料格式無效：{piece!r}"
                        )
                    piece_type, value = piece
                    details.append(self._material_detail_row(
                        result_id=result_id,
                        usage="圍令",
                        member_id=member_id,
                        zoning="",
                        piece_index=piece_index,
                        material_type=piece_type,
                        material_spec=(
                            material_spec
                            if str(piece_type).strip().lower() == "steel"
                            else ""
                        ),
                        value=value,
                    ))
                continue

            if item.get("type") != "support" or result is None:
                continue
            for plan in list(getattr(result, "plans", []) or []):
                member_id = str(
                    getattr(plan, "support_id", "") or ""
                ).strip()
                if not member_id or not self.support_plan_visible(
                    item,
                    member_id,
                ):
                    continue
                material_spec = str(
                    getattr(plan, "material_spec", "") or ""
                ).strip()
                for piece_index, piece in enumerate(
                    list(getattr(plan, "pieces", []) or []),
                    start=1,
                ):
                    if not isinstance(piece, (list, tuple)) or len(piece) != 2:
                        raise MaterialDetailBuildError(
                            f"支撐 {member_id} 的第 {piece_index} 段材料格式無效：{piece!r}"
                        )
                    piece_type, value = piece
                    details.append(self._material_detail_row(
                        result_id=result_id,
                        usage="支撐",
                        member_id=member_id,
                        zoning=str(result_id),
                        piece_index=piece_index,
                        material_type=piece_type,
                        material_spec=(
                            material_spec
                            if str(piece_type).strip().lower() == "steel"
                            else ""
                        ),
                        value=value,
                    ))
        return details

    def collect_visible_material_usage(self) -> Counter:
        usage = Counter()
        for item in self.result_items.values():
            if not item.get("visible", True):
                continue
            result = item.get("result")
            if item.get("type") == "waler":
                plan = (
                    (result.get("selected_plan") or {})
                    if isinstance(result, dict)
                    else {}
                )
                material_spec = (
                    str((result or {}).get("material_spec", "") or "").strip()
                    if isinstance(result, dict)
                    else ""
                )
                for piece_type, value in self._waler_material_pieces(plan):
                    if str(piece_type).strip().lower() != "steel":
                        continue
                    length = self.material_length_key(value)
                    if length is not None:
                        usage[("圍令", material_spec, length)] += 1
                continue

            if item.get("type") == "support":
                for plan in getattr(result, "plans", []) or []:
                    support_id = str(
                        getattr(plan, "support_id", "") or ""
                    ).strip()
                    if not self.support_plan_visible(item, support_id):
                        continue
                    material_spec = str(
                        getattr(plan, "material_spec", "") or ""
                    ).strip()
                    for piece_type, value in getattr(plan, "pieces", []) or []:
                        if str(piece_type).lower() != "steel":
                            continue
                        length = self.material_length_key(value)
                        if length is not None:
                            usage[("支撐", material_spec, length)] += 1
        return usage

    @classmethod
    def collect_inventory_quantities(cls, rows: Sequence[Mapping]) -> Counter:
        quantities = Counter()
        for row in rows:
            length = cls.material_length_key(row.get("Length"))
            try:
                quantity = float(row.get("Qty"))
            except (TypeError, ValueError):
                continue
            if (
                length is None
                or not math.isfinite(quantity)
                or quantity < 0
            ):
                continue
            quantity = int(quantity) if quantity.is_integer() else quantity
            usage = str(row.get("Usage", "") or "").strip()
            material_spec = str(row.get("Spec", "") or "").strip()
            quantities[(usage, material_spec, length)] += quantity
        return quantities

    @staticmethod
    def build_material_summary(
        usage: Mapping[tuple[str, str, int | float], int | float],
        quantity_lookup: QuantityLookup,
        *,
        unlimited_quantity: int | float,
    ) -> list[dict]:
        summary = []
        for usage_name, material_spec, length in sorted(usage):
            used_quantity = usage[(usage_name, material_spec, length)]
            inventory_quantity = quantity_lookup(
                material_spec,
                usage_name,
                length,
            )
            remaining_quantity = (
                unlimited_quantity
                if not material_spec
                else inventory_quantity - used_quantity
            )
            summary.append({
                "usage": usage_name,
                "material_spec": material_spec,
                "length": length,
                "used_qty": used_quantity,
                "inventory_qty": inventory_quantity,
                "remaining_qty": remaining_quantity,
            })
        return summary

__all__ = [
    "GlobalWalerApplyPlan",
    "MaterialDetailBuildError",
    "MaterialDetailRow",
    "ProjectResultModel",
    "SingleWalerApplyPlan",
    "SolverDiagnosticView",
]
