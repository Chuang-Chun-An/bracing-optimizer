"""Application services for validating and recalculating edited Solver plans."""

from __future__ import annotations

import copy
import math
from collections import Counter

from bracing_optimizer.algorithms import support, wales
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.solver_input_builder import InventoryLookup


def _number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _format_number(value) -> str:
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.1f}"
    return str(value)


class SupportPlanEditing:
    """Re-evaluate a manually edited support plan or support group."""

    @staticmethod
    def recalculate_global_solution(solution):
        plans = list(getattr(solution, "plans", []) or [])
        valid = all(
            getattr(plan, "valid", False) and not getattr(plan, "reason", "")
            for plan in plans
        ) and support.shared_layout_groups_valid(plans)
        reasons = []
        if not support.shared_layout_groups_valid(plans):
            reasons.append("雙路支撐群組的材料配置不一致")
        for previous, current in zip(plans, plans[1:]):
            ok, _penalty = support.pair_penalty(previous, current)
            if not ok:
                valid = False
                reasons.append(
                    f"{getattr(previous, 'support_id', '')} 與 "
                    f"{getattr(current, 'support_id', '')} 千斤頂距離不足"
                )
        recalculated = support.make_global_solution(
            plans,
            material_ratio_targets=(
                getattr(solution, "material_ratio_targets", None)
                or support.default_material_ratio_targets()
            ),
            material_ratio_weight=getattr(
                solution,
                "material_ratio_weight",
                support.SUPPORT_MATERIAL_RATIO_WEIGHT,
            ),
            valid=valid,
            reason="；".join(reasons),
        )
        for attribute in (
            "total_score",
            "reason",
            "single_score_total",
            "jack_region_penalty",
            "material_ratio_penalty",
            "material_ratio_analysis",
            "material_ratio_targets",
            "material_ratio_weight",
            "min_jack_distance",
        ):
            setattr(solution, attribute, getattr(recalculated, attribute))
        solution.valid = valid
        solution.group_penalty = (
            recalculated.jack_region_penalty
            + recalculated.material_ratio_penalty
        )
        return solution.group_penalty, reasons

    @staticmethod
    def find_forbidden_zone_hit(plan, config):
        for joint in getattr(plan, "joints", []) or []:
            for zone_start, zone_end, zone_type in support.forbidden_zones(config):
                if zone_start <= joint <= zone_end:
                    return joint, zone_start, zone_end, zone_type
        return None

    @staticmethod
    def neighbor_checks(solution, support_id: str) -> list[dict]:
        plans = list(getattr(solution, "plans", []) or [])
        index = next(
            (
                position
                for position, plan in enumerate(plans)
                if str(getattr(plan, "support_id", "")) == str(support_id)
            ),
            None,
        )
        if index is None:
            return []

        checks = []
        current = plans[index]
        previous_index = next(
            (
                position
                for position in range(index - 1, -1, -1)
                if not support.plans_share_layout_group(
                    plans[position],
                    current,
                )
            ),
            None,
        )
        if previous_index is not None:
            checks.append(
                SupportPlanEditing._neighbor_check(
                    plans[previous_index],
                    current,
                    relation="前一支支撐",
                    current_is_second=True,
                )
            )
        next_index = next(
            (
                position
                for position in range(index + 1, len(plans))
                if not support.plans_share_layout_group(
                    current,
                    plans[position],
                )
            ),
            None,
        )
        if next_index is not None:
            checks.append(
                SupportPlanEditing._neighbor_check(
                    current,
                    plans[next_index],
                    relation="下一支支撐",
                    current_is_second=False,
                )
            )
        return checks

    @staticmethod
    def _neighbor_check(first, second, *, relation: str, current_is_second: bool):
        ok, penalty = support.pair_penalty(first, second)
        current = second if current_is_second else first
        neighbor = first if current_is_second else second
        current_region = getattr(current, "jack_region_id", "無資料")
        neighbor_region = getattr(neighbor, "jack_region_id", "無資料")
        return {
            "relation": relation,
            "support_id": getattr(neighbor, "support_id", ""),
            "distance": abs(
                getattr(neighbor, "jack_center", 0)
                - getattr(current, "jack_center", 0)
            ),
            "ok": ok,
            "penalty": float(penalty),
            "current_region": current_region,
            "neighbor_region": neighbor_region,
            "region_penalty": (
                3000 * abs(neighbor_region - current_region)
                if ok and neighbor_region != current_region
                else 0
            ),
        }


class WalerPlanEditing:
    """Re-evaluate one edited Waler result against project data."""

    def __init__(self, project_data: ProjectDataModel):
        self.project_data = project_data
        self.inventory = InventoryLookup(project_data.inventory)

    def required_length(self, waler_id: str, result=None) -> int | None:
        result = result or {}
        value = result.get("required_length") if isinstance(result, dict) else None
        if value is not None:
            number = _number(value)
            if number is not None:
                return int(round(number))

        row = next(
            (
                item
                for item in self.project_data.walers
                if str(item.get("WalerID", "")).strip()
                == str(waler_id).strip()
            ),
            None,
        )
        if not row:
            return None
        coordinates = tuple(
            _number(row.get(field))
            for field in ("StartX", "StartY", "EndX", "EndY")
        )
        if any(value is None for value in coordinates):
            return None
        start_x, start_y, end_x, end_y = coordinates
        return int(round(math.hypot(end_x - start_x, end_y - start_y)))

    def recalculate(
        self,
        base_plan,
        segments,
        ratio_targets=None,
        *,
        waler_id=None,
        result_context=None,
    ) -> dict:
        base_plan = base_plan or {}
        result_context = result_context or {}
        material_spec = str(
            result_context.get(
                "material_spec",
                base_plan.get("material_spec", ""),
            )
            or ""
        ).strip()
        segments = [int(round(value)) for value in segments]
        joints = []
        position = 0
        for segment in segments[:-1]:
            position += segment
            joints.append(position)

        targets_source = ratio_targets or base_plan.get("ratio_targets") or {}

        def target_value(key, legacy_key, default):
            try:
                value = targets_source.get(
                    key,
                    targets_source.get(legacy_key, default),
                )
                return float(value)
            except (TypeError, ValueError):
                return default

        targets = {
            "short": target_value(
                "short",
                "short_segment_ratio_target",
                0.2,
            ),
            "mid": target_value("mid", "mid_segment_ratio_target", 0.5),
            "long": target_value("long", "long_segment_ratio_target", 0.3),
        }
        purchasable_lengths = self.inventory.purchasable_lengths(
            material_spec,
            "圍令",
        )
        steel_length = sum(segments)
        required_length = (
            self.required_length(waler_id, result_context)
            if waler_id
            else None
        )
        if required_length is None:
            required_length = int(
                round(float(base_plan.get("required_length", steel_length)))
            )

        completion_error = ""
        try:
            _resolved_steel, tail_adjustment, tail_gap = (
                wales.resolve_tail_adjustment(
                    required_length,
                    steel_length=steel_length,
                )
            )
        except ValueError as exc:
            tail_adjustment = 0
            tail_gap = required_length - steel_length
            completion_error = str(exc)

        config = wales.Config(
            total_length=steel_length,
            support_points=[],
            purchasable_lengths=purchasable_lengths,
            short_segment_ratio_target=targets["short"],
            mid_segment_ratio_target=targets["mid"],
            long_segment_ratio_target=targets["long"],
        )
        segment_counts, segment_ratios = wales.segment_ratio_summary(
            segments,
            config,
        )
        ratio_penalty, segment_ratios = wales.calculate_ratio_penalty(
            segments,
            config,
        )
        allocation = wales.allocate_stock_best_fit(
            segments,
            self.inventory.stock_items(material_spec, "圍令"),
            purchasable_lengths,
        )

        if allocation is None:
            assignments = []
            buy_count = len(segments)
            distinct_groups = len(set(segments))
            length_variation = max(segments) - min(segments) if segments else 0
            under_4000_count = sum(1 for segment in segments if segment < 4000)
            total_waste = 0
            errors = ["部分料長不在庫存可購買長度內，材料配置未完成。"]
        else:
            assignments = allocation["assignments"]
            buy_count = allocation["total_bought"]
            distinct_groups = allocation["distinct_groups"]
            length_variation = allocation["length_variation"]
            under_4000_count = allocation["under_4000_segment_count"]
            total_waste = allocation["total_waste"]
            errors = []
        if completion_error:
            errors.append(completion_error)

        joint_count = len(joints)
        score = (
            buy_count * 100_000
            + ratio_penalty
            + under_4000_count * 100_000
            + distinct_groups * 5_000
            + length_variation
            + joint_count * 1_000
        )
        plan = copy.deepcopy(base_plan)
        plan.update({
            "joints": joints,
            "segments": segments,
            "assignments": assignments,
            "total_waste": total_waste,
            "buy_count": buy_count,
            "distinct_groups": distinct_groups,
            "length_variation": length_variation,
            "under_4000_segment_count": under_4000_count,
            "segment_counts": segment_counts,
            "segment_ratios": segment_ratios,
            "ratio_targets": targets,
            "ratio_penalty": ratio_penalty,
            "joint_count": joint_count,
            "score": score,
            "valid": not errors,
            "errors": errors,
            "required_length": required_length,
            "steel_length": steel_length,
            "tail_adjustment": tail_adjustment,
            "gap": tail_gap,
            "pieces": [
                *[("steel", length) for length in segments],
                *([("shim", tail_adjustment)] if tail_adjustment > 0 else []),
            ],
        })
        if waler_id:
            legality = self.validate(
                waler_id=waler_id,
                segments=segments,
                joints=joints,
                result=result_context,
            )
            plan["legality"] = legality
            plan["valid"] = bool(legality.get("valid")) and not errors
        return plan

    def validate(self, *, waler_id, segments, joints, result=None) -> dict:
        result = result or {}
        required_length = self.required_length(waler_id, result)
        current_length = sum(segments)
        forbidden_points = [
            int(round(point)) for point in (result.get("forbidden_points") or [])
        ]
        joint_clearance = int(
            round(float(result.get("joint_clearance", 300) or 300))
        )
        min_piece_length = int(
            round(float(result.get("min_piece_length", 1000) or 1000))
        )
        max_piece_length = int(
            round(float(result.get("max_piece_length", 10000) or 10000))
        )
        material_spec = str(result.get("material_spec", "") or "").strip()
        purchasable_lengths = self.inventory.purchasable_lengths(
            material_spec,
            "圍令",
        )

        tail_adjustment = 0
        tail_gap = None
        completion_error = ""
        if required_length is not None:
            try:
                _resolved_steel, tail_adjustment, tail_gap = (
                    wales.resolve_tail_adjustment(
                        required_length,
                        steel_length=current_length,
                    )
                )
            except ValueError as exc:
                completion_error = str(exc)

        config = wales.Config(
            total_length=current_length,
            support_points=forbidden_points,
            min_piece_length=min_piece_length,
            max_piece_length=max_piece_length,
            joint_clearance_to_support=joint_clearance,
            purchasable_lengths=purchasable_lengths,
        )
        solver_valid, solver_errors = wales.validate_segments(
            joints,
            segments,
            config,
        )

        violations = []
        details = []
        if completion_error:
            violations.append("尾端調整量不合法")
            details.extend([
                "❌ 無法以一塊調整塊及 0～199 mm 餘量完成圍令",
                f"需求長度：{required_length} mm",
                f"標準鋼材總長：{current_length} mm",
            ])

        forbidden_joint = None
        forbidden_center = None
        for joint in joints:
            for center in forbidden_points:
                if abs(joint - center) < joint_clearance:
                    forbidden_joint = joint
                    forbidden_center = center
                    break
            if forbidden_joint is not None:
                break
        if forbidden_joint is not None:
            violations.append("接頭落入禁止區")
            details.extend([
                "❌ 接頭落入禁止區",
                f"接頭位置：{forbidden_joint} mm",
                (
                    f"禁止區：{forbidden_center - joint_clearance} ~ "
                    f"{forbidden_center + joint_clearance} mm"
                ),
            ])

        allowed_lengths = set(purchasable_lengths)
        missing_length = next(
            (segment for segment in segments if segment not in allowed_lengths),
            None,
        )
        if missing_length is not None:
            violations.append("無此料長")
            details.extend(["❌ 無此料長", f"料長：{missing_length} mm"])

        other_errors = [
            error
            for error in solver_errors
            if "距支撐過近" not in error
            and "不在可用材料長度清單" not in error
        ]
        for error in other_errors:
            violations.append(error)
            details.append(f"❌ {error}")

        warnings = []
        for length, required_quantity in sorted(Counter(segments).items()):
            inventory_quantity = self.inventory.quantity(
                material_spec,
                "圍令",
                length,
            )
            if required_quantity > inventory_quantity and length in allowed_lengths:
                warnings.extend([
                    "庫存不足（會以購買數計入分數）",
                    (
                        f"{length} mm：需要 {required_quantity} 根，庫存 "
                        f"{_format_number(inventory_quantity)} 根，不足 "
                        f"{_format_number(required_quantity - inventory_quantity)} 根"
                    ),
                ])

        valid = (
            required_length is not None
            and not completion_error
            and solver_valid
            and not violations
        )
        if valid:
            summary = "✅ 合法"
            details = [
                "✅ 合法",
                f"需求長度：{required_length} mm",
                f"標準鋼材總長：{current_length} mm",
                f"尾端調整塊：{tail_adjustment} mm",
                f"現場處理餘量：{tail_gap} mm",
                "✅ 所有接頭均符合規範",
            ]
        elif len(violations) == 1:
            summary = f"❌ {violations[0]}"
        else:
            summary = f"❌ 共 {len(violations)} 項違規"
            details = [summary] + [
                f"- {violation}" for violation in violations
            ] + details

        return {
            "valid": valid,
            "summary": summary,
            "violations": violations,
            "details": details,
            "warnings": warnings,
            "required_length": required_length,
            "current_length": current_length,
            "tail_adjustment": tail_adjustment,
            "gap": tail_gap,
        }


__all__ = ["SupportPlanEditing", "WalerPlanEditing"]
