"""Application services for validating and recalculating edited Solver plans."""

from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Sequence

from bracing_optimizer.algorithms import support, wales
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.solver_input_builder import InventoryLookup


_SUPPORT_JACK_REGION_PENALTY_WEIGHT = 3000


@dataclass(frozen=True)
class SupportEditOptions:
    """Engineering options exposed to the support-plan editor."""

    piece_types: tuple[str, ...]
    steel_lengths: tuple[int, ...]
    shim_lengths: tuple[int, ...]
    jack_length: int
    default_steel_length: int
    default_shim_length: int


@dataclass(frozen=True)
class SupportPieceValidation:
    """Validation outcome for one ordered support-piece layout."""

    valid: bool
    issue_code: str = ""
    message: str = ""


@dataclass(frozen=True)
class SupportPlanAnalysis:
    """Solver-derived facts needed to present one support plan."""

    short_count: int
    short_steel_threshold: int
    short_penalty_weight: float
    joint_count: int
    joint_penalty_weight: float
    target_gap: int
    gap_penalty_weight: float
    quality_score: float
    region_group_penalty: float
    material_ratio_penalty: float
    group_penalty: float
    ranking_score: float
    minimum_jack_distance: float
    jack_region_penalty_weight: float


@dataclass(frozen=True)
class SupportGlobalAnalysis:
    """Solver-derived facts needed to present one global support result."""

    counts: dict[str, object]
    ratios: dict[str, object]
    targets: dict[str, object]
    classified_total: int
    ratio_deviation: float
    material_ratio_weight: float
    material_ratio_penalty: float
    jack_region_penalty: float
    min_jack_distance: float | None
    minimum_jack_distance: float
    jack_distance_ok: bool


@dataclass(frozen=True)
class SupportEditContext:
    """Read-only data required to open the support-plan editor."""

    plan: Any
    config: Any
    options: SupportEditOptions


@dataclass(frozen=True)
class SupportPlanEditResult:
    """Staged replacement produced by one support-plan edit."""

    solution: Any
    plan: Any
    updated_support_ids: tuple[str, ...]
    validation: SupportPieceValidation
    neighbor_checks: tuple[dict, ...]
    analysis: SupportPlanAnalysis


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

    def __init__(self, project_data=None, support_input_builder=None):
        self.project_data = project_data
        self.support_input_builder = support_input_builder

    def config_by_id(self, support_id: str):
        if self.project_data is None or self.support_input_builder is None:
            raise RuntimeError("支撐方案編輯服務缺少 ProjectDataModel 或 SupportInputBuilder。")
        return self.support_input_builder.build_one(
            self.project_data,
            support_id,
        )

    @staticmethod
    def edit_options(config) -> SupportEditOptions:
        steel_lengths = tuple(support.configured_steel_lengths(config))
        shim_lengths = tuple(int(value) for value in support.SHIM_LENGTHS)
        default_shim_length = (
            150
            if 150 in shim_lengths
            else next((value for value in shim_lengths if value > 0), 0)
        )
        return SupportEditOptions(
            piece_types=("steel", "shim", "jack"),
            steel_lengths=steel_lengths,
            shim_lengths=shim_lengths,
            jack_length=int(support.JACK_LENGTH),
            default_steel_length=(steel_lengths[0] if steel_lengths else 5000),
            default_shim_length=default_shim_length,
        )

    def edit_context(self, solution, support_id: str) -> SupportEditContext:
        support_id = str(support_id or "")
        plan = next(
            (
                item
                for item in list(getattr(solution, "plans", []) or [])
                if str(getattr(item, "support_id", "")) == support_id
            ),
            None,
        )
        config = self.config_by_id(support_id)
        if plan is None or config is None:
            raise ValueError("找不到支撐方案或支撐設定資料。")
        return SupportEditContext(
            plan=plan,
            config=config,
            options=self.edit_options(config),
        )

    @staticmethod
    def validate_pieces(config, pieces: Sequence[tuple[str, int]]) -> SupportPieceValidation:
        try:
            normalized = [
                (str(kind).strip().lower(), int(round(float(length))))
                for kind, length in pieces
            ]
        except (TypeError, ValueError):
            return SupportPieceValidation(
                valid=False,
                issue_code="invalid_piece_format",
                message="❌ 類型或長度格式錯誤",
            )

        if any(
            kind not in ("steel", "shim", "jack") or length <= 0
            for kind, length in normalized
        ):
            return SupportPieceValidation(
                valid=False,
                issue_code="invalid_piece_format",
                message="❌ 類型或長度格式錯誤",
            )

        jack_count = sum(1 for kind, _length in normalized if kind == "jack")
        if jack_count != 1:
            return SupportPieceValidation(
                valid=False,
                issue_code="invalid_jack_count",
                message="❌ 千斤頂數量不是 1",
            )

        allowed_steel_lengths = support.configured_steel_lengths(config)
        for kind, length in normalized:
            if kind == "steel" and length not in allowed_steel_lengths:
                return SupportPieceValidation(
                    valid=False,
                    issue_code="invalid_steel_length",
                    message=f"❌ 鋼材長度不合法：{length} mm",
                )
            if kind == "shim" and length not in support.SHIM_LENGTHS:
                return SupportPieceValidation(
                    valid=False,
                    issue_code="invalid_shim_length",
                    message=f"❌ 調整塊長度不合法：{length} mm",
                )
            if kind == "jack" and length != support.JACK_LENGTH:
                return SupportPieceValidation(
                    valid=False,
                    issue_code="invalid_jack_length",
                    message=f"❌ 千斤頂長度必須固定為 {support.JACK_LENGTH} mm",
                )
        return SupportPieceValidation(valid=True)

    def stage_edit(
        self,
        solution,
        support_id: str,
        pieces: Sequence[tuple[str, int]],
    ) -> SupportPlanEditResult:
        """Stage one manual edit without mutating the source solution."""

        support_id = str(support_id or "")
        context = self.edit_context(solution, support_id)
        validation = self.validate_pieces(context.config, pieces)
        if validation.issue_code == "invalid_piece_format":
            raise ValueError(validation.message)

        normalized_pieces = [
            (str(kind).strip().lower(), int(round(float(length))))
            for kind, length in pieces
        ]
        source_plans = list(getattr(solution, "plans", []) or [])
        shared_group = str(
            getattr(context.plan, "shared_layout_group", "") or ""
        ).strip()
        target_ids = (
            [
                str(getattr(plan, "support_id", "") or "")
                for plan in source_plans
                if str(
                    getattr(plan, "shared_layout_group", "") or ""
                ).strip() == shared_group
            ]
            if shared_group
            else [support_id]
        )
        configs = {}
        for member_id in target_ids:
            config = self.config_by_id(member_id)
            if config is None:
                raise ValueError(f"找不到支撐 {member_id} 的設定資料。")
            configs[member_id] = config

        staged_solution = copy.deepcopy(solution)
        staged_plans = list(getattr(staged_solution, "plans", []) or [])
        updated_ids = []
        for index, plan in enumerate(staged_plans):
            member_id = str(getattr(plan, "support_id", "") or "")
            if member_id not in configs:
                continue
            staged_plans[index] = support.evaluate_single_support(
                configs[member_id],
                list(normalized_pieces),
            )
            updated_ids.append(member_id)
        if not updated_ids:
            raise ValueError(f"找不到支撐方案 {support_id}。")

        staged_solution.plans = staged_plans
        self.recalculate_global_solution(staged_solution)
        edited_plan = next(
            plan
            for plan in staged_solution.plans
            if str(getattr(plan, "support_id", "")) == support_id
        )
        neighbor_checks = tuple(
            self.neighbor_checks(staged_solution, support_id)
        )
        return SupportPlanEditResult(
            solution=staged_solution,
            plan=edited_plan,
            updated_support_ids=tuple(updated_ids),
            validation=validation,
            neighbor_checks=neighbor_checks,
            analysis=self.analyze_plan(
                edited_plan,
                neighbor_checks,
                staged_solution,
            ),
        )

    @staticmethod
    def analyze_plan(plan, neighbor_checks=None, solution=None) -> SupportPlanAnalysis:
        breakdown = dict(getattr(plan, "breakdown", {}) or {})
        short_penalty = float(breakdown.get("short_penalty", 0.0) or 0.0)
        joint_penalty = float(breakdown.get("joint_penalty", 0.0) or 0.0)
        gap_penalty = float(breakdown.get("gap_penalty", 0.0) or 0.0)
        jack_edge_penalty = float(
            breakdown.get("jack_edge_penalty", 0.0) or 0.0
        )
        invalid_penalty = float(
            breakdown.get("invalid_penalty", 0.0) or 0.0
        )
        short_count = sum(
            1
            for kind, length in list(getattr(plan, "pieces", []) or [])
            if kind == "steel"
            and length < support.SUPPORT_SHORT_STEEL_THRESHOLD
        )
        joint_count = len(getattr(plan, "joints", []) or [])
        quality_score = (
            short_penalty
            + joint_penalty
            + gap_penalty
            + jack_edge_penalty
        )
        region_group_penalty = sum(
            float(item.get("penalty", 0.0) or 0.0)
            for item in neighbor_checks or []
        )
        material_ratio_penalty = (
            float(
                getattr(solution, "material_ratio_penalty", 0.0) or 0.0
            )
            if solution is not None
            else 0.0
        )
        group_penalty = region_group_penalty + material_ratio_penalty
        return SupportPlanAnalysis(
            short_count=short_count,
            short_steel_threshold=int(support.SUPPORT_SHORT_STEEL_THRESHOLD),
            short_penalty_weight=float(
                support.SUPPORT_SHORT_STEEL_PENALTY_WEIGHT
            ),
            joint_count=joint_count,
            joint_penalty_weight=float(support.SUPPORT_JOINT_PENALTY_WEIGHT),
            target_gap=int(support.TARGET_GAP),
            gap_penalty_weight=float(support.SUPPORT_GAP_PENALTY_WEIGHT),
            quality_score=quality_score,
            region_group_penalty=region_group_penalty,
            material_ratio_penalty=material_ratio_penalty,
            group_penalty=group_penalty,
            ranking_score=quality_score + invalid_penalty + group_penalty,
            minimum_jack_distance=float(
                support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS
            ),
            jack_region_penalty_weight=float(
                _SUPPORT_JACK_REGION_PENALTY_WEIGHT
            ),
        )

    @staticmethod
    def global_analysis(solution) -> SupportGlobalAnalysis:
        analysis = dict(
            getattr(solution, "material_ratio_analysis", {}) or {}
        )
        min_distance = getattr(solution, "min_jack_distance", None)
        minimum_distance = float(
            support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS
        )
        return SupportGlobalAnalysis(
            counts=dict(analysis.get("counts", {}) or {}),
            ratios=dict(analysis.get("ratios", {}) or {}),
            targets=dict(analysis.get("targets", {}) or {}),
            classified_total=int(analysis.get("classified_total", 0) or 0),
            ratio_deviation=float(
                analysis.get("ratio_deviation", 0.0) or 0.0
            ),
            material_ratio_weight=float(
                analysis.get(
                    "weight",
                    support.SUPPORT_MATERIAL_RATIO_WEIGHT,
                )
                or 0.0
            ),
            material_ratio_penalty=float(
                analysis.get("penalty", 0.0) or 0.0
            ),
            jack_region_penalty=float(
                getattr(solution, "jack_region_penalty", 0.0) or 0.0
            ),
            min_jack_distance=min_distance,
            minimum_jack_distance=minimum_distance,
            jack_distance_ok=(
                min_distance is None
                or float(min_distance) >= minimum_distance
            ),
        )

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
        region_difference = (
            abs(neighbor_region - current_region)
            if isinstance(current_region, (int, float))
            and isinstance(neighbor_region, (int, float))
            else 0
        )
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
            "minimum_distance": float(
                support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS
            ),
            "region_penalty_weight": float(
                _SUPPORT_JACK_REGION_PENALTY_WEIGHT
            ),
            "region_penalty": (
                _SUPPORT_JACK_REGION_PENALTY_WEIGHT * region_difference
                if ok and region_difference
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


__all__ = [
    "SupportEditContext",
    "SupportEditOptions",
    "SupportGlobalAnalysis",
    "SupportPieceValidation",
    "SupportPlanAnalysis",
    "SupportPlanEditing",
    "SupportPlanEditResult",
    "WalerPlanEditing",
]
