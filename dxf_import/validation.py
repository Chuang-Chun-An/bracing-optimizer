"""Validation and problem summaries for prepared DXF models."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Sequence

from .geometry import (
    _angle_difference_deg,
    _distance,
    _length,
    _line_distance,
    _segment_distance,
)
from .models import (
    AuxiliaryComponent,
    Beam,
    Brace,
    CandidatePoint,
    Column,
    DXFImportResult,
    GeometryTolerances,
    ProblemRecord,
    ReviewItem,
    Strut,
    ValidationMessage,
    ValidationOverviewItem,
    Waler,
    ERROR_SEVERITIES,
)
from .recognition import _lines_duplicate


PROBLEM_SEVERITY_RANK = {
    "critical": 4,
    "error": 3,
    "warning": 2,
    "info": 1,
}

_RECOGNITION_CODES = {
    "WALER_ENGINEERING_LINE_FAILED",
    "WALER_RECOGNITION_FAILED",
    "STRUT_CENTERLINE_FAILED",
    "STRUT_RECOGNITION_FAILED",
    "BRACE_CENTERLINE_FAILED",
    "BRACE_RECOGNITION_FAILED",
    "COLUMN_CENTERLINE_FAILED",
    "COLUMN_RECOGNITION_FAILED",
    "BEAM_CENTERLINE_FAILED",
    "BEAM_RECOGNITION_FAILED",
    "CORNER_BRACE_CENTERLINE_FAILED",
    "CORNER_BRACE_RECOGNITION_FAILED",
    "AMBIGUOUS_CENTERLINE",
    "AMBIGUOUS_INNER_LINE",
    "COMPONENT_TOO_SHORT",
    "MULTIPLE_MODELS_FROM_ONE_SOURCE",
    "ZERO_LENGTH_COMPONENT",
}
_ENDPOINT_CODES = {
    "BRACE_NOT_CONNECTED",
    "BRACE_ONE_END_NOT_CONNECTED",
    "CANDIDATE_ENDPOINT_NOT_NEAR_WALER",
    "CANDIDATE_LINE_DIRECTION_CHANGED",
    "CANDIDATE_LINE_TOO_SHORT",
    "CANDIDATE_POINT_INVALID",
    "CANDIDATE_POINT_MISSING",
    "STRUT_NOT_CONNECTED",
    "STRUT_ONE_END_NOT_CONNECTED",
    "WALER_CANDIDATE_LINE_UNUSUAL",
    "ZERO_LENGTH_CANDIDATE_LINE",
}
_RELATIONSHIP_CODES = {
    "AMBIGUOUS_COMPONENT_ASSOCIATION",
    "AMBIGUOUS_WALER_CONNECTION",
    "BEAM_CROSSING_SNAPPED",
    "BEAM_NOT_ASSOCIATED",
    "BEAM_OVERLAPS_STRUT",
    "BRACE_STATION_INVALID",
    "COLUMN_NOT_ASSOCIATED",
    "CORNER_BRACE_CONNECTION_INVALID",
    "CORNER_BRACE_CONNECTION_POINT_FAILED",
    "CORNER_BRACE_DERIVED_FIELD_CONFLICT",
    "CORNER_BRACE_INTERSECTION_AMBIGUOUS",
    "CORNER_BRACE_INTERSECTION_FAILED",
    "STRUT_WALER_INTERSECTION_FAILED",
    "WALER_SUPPORT_SIDE_UNKNOWN",
}
_DUPLICATE_CODES = {
    "DUPLICATED_COMPONENT",
    "DUPLICATE_ENGINEERING_COMPONENT",
}
_WALER_CONTACT_CODES = {
    "INVALID_WALER_CONTACT_VALUE",
    "WALER_CONTACT_ADJUSTED",
    "WALER_CONTACT_BASELINE_CHANGED",
}


def problem_severity_rank(severity: str) -> int:
    """Return the review priority without changing import-blocking policy."""

    return PROBLEM_SEVERITY_RANK.get(str(severity).lower(), 0)


def build_problem_records(result: DXFImportResult) -> tuple[ProblemRecord, ...]:
    """Convert validation messages into concise, component-oriented UI rows."""

    members: tuple[Waler | Strut | Brace | AuxiliaryComponent, ...] = (
        *result.walers,
        *result.struts,
        *result.braces,
        *result.columns,
        *result.beams,
        *result.corner_braces,
    )
    member_by_id = {member.id: member for member in members}
    owners_by_handle: dict[str, set[str]] = defaultdict(set)
    for member in members:
        for handle in member.source_handles:
            if str(handle):
                owners_by_handle[str(handle)].add(member.id)

    records = []
    for message in result.messages:
        handles = tuple(dict.fromkeys(str(item) for item in message.source_handles if str(item)))
        member_ids = tuple(
            dict.fromkeys(
                member_id
                for member_id in message.member_ids
                if member_id in member_by_id
            )
        )
        if not member_ids and handles:
            owner_sets = [owners_by_handle.get(handle, set()) for handle in handles]
            if owner_sets and all(len(owners) == 1 for owners in owner_sets):
                common_owners = set.intersection(*owner_sets)
                if len(common_owners) == 1:
                    owner_id = next(iter(common_owners))
                    member_ids = (owner_id,)
        component = ", ".join(member_ids)
        if not component and handles:
            component = ", ".join(handles)
        records.append(
            ProblemRecord(
                message.severity,
                message.code,
                component or "—",
                message.message,
                message.role,
                handles,
                member_ids,
            )
        )
    # Python's sort is stable, so messages at the same severity retain the
    # validation pipeline's original order.
    return tuple(
        sorted(records, key=lambda item: -problem_severity_rank(item.severity))
    )


def _highest_problem_severity(problems: Sequence[ProblemRecord]) -> str:
    if not problems:
        return "success"
    return max(problems, key=lambda item: problem_severity_rank(item.severity)).severity


def _source_metadata(
    result: DXFImportResult,
    role: str,
    handles: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    handle_set = set(handles)
    layers: list[str] = []
    entity_types: list[str] = []
    for item in result.entity_debug:
        if item.handle not in handle_set:
            continue
        if role not in {"", "unknown"} and item.role and item.role != role:
            continue
        if item.layer and item.layer not in layers:
            layers.append(item.layer)
        if (
            item.entity_type
            and item.entity_type != "TEXT_SUMMARY"
            and item.entity_type not in entity_types
        ):
            entity_types.append(item.entity_type)
    for geometry in result.source_geometry:
        if geometry.source_handle not in handle_set:
            continue
        if (
            role not in {"", "unknown"}
            and geometry.role
            and geometry.role != role
        ):
            continue
        if geometry.source_layer and geometry.source_layer not in layers:
            layers.append(geometry.source_layer)
        if geometry.source_entity_type and geometry.source_entity_type not in entity_types:
            entity_types.append(geometry.source_entity_type)
    return tuple(layers), tuple(entity_types)


def build_review_items(
    result: DXFImportResult,
    problem_records: Sequence[ProblemRecord] | None = None,
) -> tuple[ReviewItem, ...]:
    """Project current validation into formal members and unresolved sources."""

    records = tuple(
        build_problem_records(result)
        if problem_records is None
        else problem_records
    )
    members = _result_members(result)
    problems_by_member: dict[str, list[ProblemRecord]] = defaultdict(list)
    owners_by_handle: dict[str, set[str]] = defaultdict(set)
    for member in members:
        for handle in member.source_handles:
            if str(handle):
                owners_by_handle[str(handle)].add(member.id)
    for record in records:
        for member_id in record.member_ids:
            bucket = problems_by_member[member_id]
            if record not in bucket:
                bucket.append(record)

    items: list[ReviewItem] = []
    for member in members:
        role = _member_model_role(member)
        problems = tuple(problems_by_member.get(member.id, ()))
        items.append(
            ReviewItem(
                key=f"member:{role}:{member.id}",
                display_id=member.id,
                role=role,
                status="recognized",
                member_id=member.id,
                source_handles=tuple(member.source_handles),
                source_layers=((member.source_layer,) if member.source_layer else ()),
                source_entity_types=tuple(member.source_entity_types),
                selection_source=member.selection_source,
                problems=problems,
                highest_severity=_highest_problem_severity(problems),
            )
        )

    unresolved: dict[tuple[str, tuple[str, ...]], list[ProblemRecord]] = {}
    for record in records:
        if record.member_ids or record.severity not in {"warning", "error", "critical"}:
            continue
        handles = tuple(sorted(set(record.source_handles)))
        if not handles:
            continue
        # A source already used by any formal member is not presented as a
        # second ghost object when its ownership is ambiguous. The global
        # problem list retains
        # the original ProblemRecord for review.
        if any(owners_by_handle.get(handle) for handle in handles):
            continue
        key = (record.role or "unknown", handles)
        bucket = unresolved.setdefault(key, [])
        if record not in bucket:
            bucket.append(record)

    for (role, handles), problems_list in unresolved.items():
        layers, entity_types = _source_metadata(result, role, handles)
        display_id = f"待修-{handles[0]}"
        if len(handles) > 1:
            display_id += f"（共 {len(handles)} 個圖元）"
        problems = tuple(problems_list)
        items.append(
            ReviewItem(
                key=f"source:{role}:{'|'.join(handles)}",
                display_id=display_id,
                role=role,
                status="unresolved",
                member_id=None,
                source_handles=handles,
                source_layers=layers,
                source_entity_types=entity_types,
                selection_source="",
                problems=problems,
                highest_severity=_highest_problem_severity(problems),
            )
        )

    for excluded in result.excluded_sources:
        previous_display_id = (
            excluded.display_id_when_excluded
            or (excluded.source_handles[0] if excluded.source_handles else "來源")
        )
        display_suffix = (
            previous_display_id[len("待修-"):]
            if previous_display_id.startswith("待修-")
            else previous_display_id
        )
        items.append(
            ReviewItem(
                key=f"excluded:{excluded.identity}",
                display_id=f"已排除-{display_suffix}",
                role=excluded.role,
                status="excluded",
                member_id=None,
                source_handles=excluded.source_handles,
                source_layers=excluded.source_layers,
                source_entity_types=excluded.source_entity_types,
                selection_source="",
                problems=(),
                highest_severity="info",
                exclusion_reason=excluded.reason,
                display_id_before_exclusion=previous_display_id,
            )
        )
    return tuple(items)


def _guidance_for_problem(record: ProblemRecord, item: ReviewItem) -> str:
    code = record.code
    if item.status == "unresolved":
        return (
            "此來源尚未形成正式工程構件。請開啟「圖層 ✓」確認用途並重新辨識，"
            "同時檢查原始 DXF 幾何；目前幾何修正工具不適用。"
        )
    if code in _WALER_CONTACT_CODES:
        return "請在工程資料的圍令接觸位置調整中檢查圖面值與採用值。"
    if "COORDINATE" in code:
        return "請開啟「座標 ✓」檢查座標系統。"
    if code in _RECOGNITION_CODES:
        return "請開啟「圖層 ✓」確認用途後重新辨識，並檢查原始 DXF 幾何。"
    if code in _ENDPOINT_CODES or code in _DUPLICATE_CODES:
        if item.role in {"waler", "strut", "brace"}:
            return (
                "請在候選點區檢查起點與終點；若需依 CAD 圖面重新指定工程線，"
                "可使用修改工具中的「從 CAD 指定工程線」。"
            )
        return "請在候選點區檢查起點與終點。"
    if code in _RELATIONSHIP_CODES:
        if item.role in {"waler", "strut", "brace"}:
            return (
                "請先檢查相關構件的工程線與端點；若位置有誤，可由候選點或 CAD 工程線工具修正。"
            )
        return (
            "請先檢查相關構件的工程線與端點；若此構件端點有誤，可在候選點區修正。"
        )
    return "請依上方問題內容檢查此構件；目前沒有對應的專用人工修正工具。"


def review_item_guidance(item: ReviewItem) -> tuple[str, ...]:
    """Return de-duplicated text that references only existing review tools."""

    if item.status == "excluded":
        return (
            "此 DXF 來源已由使用者排除，不再參與工程辨識。",
            "原始 DXF 圖元仍保留；若要重新辨識，請使用「復原此來源」。",
        )

    guidance: list[str] = []
    for record in item.problems:
        text = _guidance_for_problem(record, item)
        if text not in guidance:
            guidance.append(text)
    return tuple(guidance)


def build_validation_overview(result: DXFImportResult) -> tuple[ValidationOverviewItem, ...]:
    """Build the short checklist an engineer should be able to scan quickly."""

    coordinate = result.coordinate_system
    coordinate_text = (
        f"使用局部座標，原點 ({coordinate.origin_x:g}, {coordinate.origin_y:g})"
        if coordinate.mode == "local"
        else "使用原始 CAD 座標"
    )
    items = [
        ValidationOverviewItem("success", "圖層已讀取"),
        ValidationOverviewItem("success", coordinate_text),
    ]
    role_data = (
        ("strut", "支撐", result.struts),
        ("waler", "圍令", result.walers),
        ("brace", "斜撐", result.braces),
    )
    for role, label, members in role_data:
        engineering_line_code = (
            "WALER_ENGINEERING_LINE_FAILED"
            if role == "waler"
            else f"{role.upper()}_CENTERLINE_FAILED"
        )
        failed = any(
            message.role == role
            and message.severity in ERROR_SEVERITIES
            and message.code
            in {f"{role.upper()}_RECOGNITION_FAILED", engineering_line_code}
            for message in result.messages
        )
        if members and not failed:
            items.append(ValidationOverviewItem("success", f"{label}辨識成功（{len(members)}）"))
        elif not failed and any(
            source.role == role for source in result.excluded_sources
        ):
            excluded_count = sum(
                source.role == role for source in result.excluded_sources
            )
            items.append(
                ValidationOverviewItem(
                    "success",
                    f"{label}來源已全部排除（{excluded_count}）",
                )
            )
        else:
            items.append(ValidationOverviewItem("error", f"{label}辨識失敗或沒有可用構件"))

    for label, members in (
        ("中間柱", result.columns),
        ("托梁", result.beams),
        ("角撐", result.corner_braces),
    ):
        if members:
            items.append(
                ValidationOverviewItem("success", f"{label}辨識成功（{len(members)}）")
            )

    unassociated_columns = sum(not member.associated_strut_id for member in result.columns)
    unassociated_beams = sum(not member.associated_strut_id for member in result.beams)
    if result.columns:
        items.append(
            ValidationOverviewItem(
                "error" if unassociated_columns else "success",
                (
                    f"{unassociated_columns} 根中間柱尚未關聯支撐"
                    if unassociated_columns
                    else "中間柱皆已關聯支撐"
                ),
            )
        )
    if result.beams:
        items.append(
            ValidationOverviewItem(
                "error" if unassociated_beams else "success",
                (
                    f"{unassociated_beams} 根托梁尚未關聯支撐"
                    if unassociated_beams
                    else "托梁皆已關聯支撐"
                ),
            )
        )

    for role, label, members in (("strut", "支撐", result.struts), ("brace", "斜撐", result.braces)):
        incomplete = sum(not (member.from_waler and member.to_waler) for member in members)
        if incomplete:
            items.append(ValidationOverviewItem("error", f"{incomplete} 根{label}未完整連接圍令"))
        elif members:
            items.append(ValidationOverviewItem("success", f"{label}皆已連接圍令"))

    failed_engineering_lines = sum(
        "CENTERLINE_FAILED" in message.code
        or message.code == "WALER_ENGINEERING_LINE_FAILED"
        for message in result.messages
    )
    if failed_engineering_lines:
        items.append(
            ValidationOverviewItem(
                "error", f"{failed_engineering_lines} 個構件工程線建立失敗"
            )
        )
    duplicate_count = sum(message.code == "DUPLICATED_COMPONENT" for message in result.messages)
    if duplicate_count:
        items.append(ValidationOverviewItem("warning", f"{duplicate_count} 組重複幾何已自動合併"))
    manual_count = sum(
        member.selection_source != "auto"
        for member in (
            *result.walers,
            *result.struts,
            *result.braces,
            *result.columns,
            *result.beams,
            *result.corner_braces,
        )
    )
    if manual_count:
        items.append(
            ValidationOverviewItem("info", f"已人工選擇 {manual_count} 個構件工程線")
        )
    if result.can_import:
        items.append(ValidationOverviewItem("success", "工程模型可以匯入求解器"))
    else:
        items.append(ValidationOverviewItem("error", "存在阻擋錯誤，目前不可匯入求解器"))
    return tuple(items)


def validate_duplicate_engineering_members(
    collections: Sequence[
        Sequence[Waler | Strut | Brace | AuxiliaryComponent]
    ],
    tolerances: GeometryTolerances,
) -> tuple[ValidationMessage, ...]:
    """Detect duplicates introduced by manual endpoint combinations."""

    messages: list[ValidationMessage] = []
    for members in collections:
        for index, first in enumerate(members):
            first_line = (
                first.world_start or first.start,
                first.world_end or first.end,
            )
            for second in members[index + 1 :]:
                second_line = (
                    second.world_start or second.start,
                    second.world_end or second.end,
                )
                if not _lines_duplicate(first_line, second_line, tolerances):
                    continue
                messages.append(
                    ValidationMessage(
                        "error",
                        "DUPLICATE_ENGINEERING_COMPONENT",
                        f"{first.id} 與 {second.id} 的工程線重複，請修正候選點。",
                        _member_model_role(first),
                        tuple(
                            sorted(
                                {
                                    *first.source_handles,
                                    *second.source_handles,
                                }
                            )
                        ),
                        member_ids=(first.id, second.id),
                    )
                )
    return tuple(messages)


def _result_members(
    result: DXFImportResult,
) -> tuple[Waler | Strut | Brace | AuxiliaryComponent, ...]:
    return (
        *result.walers,
        *result.struts,
        *result.braces,
        *result.columns,
        *result.beams,
        *result.corner_braces,
    )


def _member_model_role(
    member: Waler | Strut | Brace | AuxiliaryComponent,
) -> str:
    if isinstance(member, Waler):
        return "waler"
    if isinstance(member, Strut):
        return "strut"
    if isinstance(member, Brace):
        return "brace"
    if isinstance(member, Column):
        return "column"
    if isinstance(member, Beam):
        return "beam"
    return "corner_brace"


def candidate_point_by_id(
    member: Waler | Strut | Brace | AuxiliaryComponent,
    point_id: str,
) -> CandidatePoint | None:
    return next(
        (point for point in member.candidate_points if point.id == point_id),
        None,
    )


def validate_candidate_point_pair(
    member: Waler | Strut | Brace | AuxiliaryComponent,
    start_point_id: str,
    end_point_id: str,
    tolerances: GeometryTolerances | None = None,
    walers: Sequence[Waler] = (),
) -> tuple[ValidationMessage, ...]:
    """Validate one pending pair without changing the formal engineering model."""

    tolerances = tolerances or GeometryTolerances()
    start_point = candidate_point_by_id(member, start_point_id)
    end_point = candidate_point_by_id(member, end_point_id)
    role = _member_model_role(member)
    if start_point is None or end_point is None:
        return (
            ValidationMessage(
                "error",
                "CANDIDATE_POINT_MISSING",
                f"{member.id} 的待套用候選點資料遺失。",
                role,
                member.source_handles,
            ),
        )
    coordinates = (*start_point.world_point, *end_point.world_point)
    if not all(math.isfinite(value) for value in coordinates):
        return (
            ValidationMessage(
                "error",
                "CANDIDATE_POINT_INVALID",
                f"{member.id} 的候選點座標不是有效數字。",
                role,
                member.source_handles,
            ),
        )
    selected_length = _distance(start_point.world_point, end_point.world_point)
    if start_point.id == end_point.id or selected_length <= 1e-9:
        return (
            ValidationMessage(
                "error",
                "ZERO_LENGTH_CANDIDATE_LINE",
                f"{member.id} 的起點與終點不可相同。",
                role,
                member.source_handles,
            ),
        )
    if selected_length < tolerances.minimum_component_length_mm:
        return (
            ValidationMessage(
                "error",
                "CANDIDATE_LINE_TOO_SHORT",
                f"{member.id} 的待套用工程線長度 {selected_length:.1f} 小於絕對最小值。",
                role,
                member.source_handles,
            ),
        )

    original_line = (
        (
            member.line_candidates[0].world_start,
            member.line_candidates[0].world_end,
        )
        if member.line_candidates
        else (member.world_start or member.start, member.world_end or member.end)
    )
    selected_line = start_point.world_point, end_point.world_point
    angle = _angle_difference_deg(original_line, selected_line)
    messages: list[ValidationMessage] = []
    if angle > max(10.0, tolerances.parallel_angle_tolerance_deg * 4):
        messages.append(
            ValidationMessage(
                "warning",
                "CANDIDATE_LINE_DIRECTION_CHANGED",
                f"{member.id} 新工程線與自動辨識長軸差異 {angle:.1f}°，請確認方向。",
                role,
                member.source_handles,
            )
        )
    original_length = _length(*original_line)
    if original_length > 0 and selected_length < original_length * 0.35:
        messages.append(
            ValidationMessage(
                "warning",
                "POSSIBLE_COMPONENT_SHORT_SIDE",
                f"{member.id} 新工程線明顯短於自動辨識結果，可能選到構件短邊。",
                role,
                member.source_handles,
            )
        )
    if isinstance(member, Waler) and member.line_candidates:
        best_fit = min(
            max(
                _line_distance(
                    start_point.world_point,
                    candidate.world_start,
                    candidate.world_end,
                ),
                _line_distance(
                    end_point.world_point,
                    candidate.world_start,
                    candidate.world_end,
                ),
            )
            for candidate in member.line_candidates
        )
        if best_fit > tolerances.connection_tolerance_mm:
            messages.append(
                ValidationMessage(
                    "warning",
                    "WALER_CANDIDATE_LINE_UNUSUAL",
                    f"{member.id} 新工程線未落在既有圍令辨識線附近。",
                    role,
                    member.source_handles,
                )
            )
    if isinstance(member, (Strut, Brace)) and walers:
        for endpoint_name, endpoint in (
            ("起點", start_point.world_point),
            ("終點", end_point.world_point),
        ):
            nearest = min(
                _segment_distance(
                    endpoint,
                    waler.world_start or waler.start,
                    waler.world_end or waler.end,
                )
                for waler in walers
            )
            if nearest > tolerances.connection_tolerance_mm:
                messages.append(
                    ValidationMessage(
                        "warning",
                        "CANDIDATE_ENDPOINT_NOT_NEAR_WALER",
                        f"{member.id} {endpoint_name}距圍令內側線 {nearest:.1f}，套用後可能無法連接。",
                        role,
                        member.source_handles,
                    )
                )
    return tuple(messages)
