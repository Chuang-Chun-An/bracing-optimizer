"""Application model for persisted Solver results and material usage."""

from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Mapping, Sequence

from bracing_optimizer.algorithms import support


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


@dataclass
class ProjectResultModel:
    """Own the data-only result state stored with one project."""

    result_items: dict[str, dict] = field(default_factory=dict)
    last_calculated_time: str | None = None
    persisted_payload: dict | None = None

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
    "MaterialDetailBuildError",
    "MaterialDetailRow",
    "ProjectResultModel",
]
