"""Validation and problem summaries for prepared DXF models."""

from __future__ import annotations

import math
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
    Strut,
    ValidationMessage,
    ValidationOverviewItem,
    Waler,
    ERROR_SEVERITIES,
)
from .recognition import _lines_duplicate


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
    records = []
    for message in result.messages:
        handles = set(message.source_handles)
        member_ids = tuple(
            member.id
            for member in members
            if handles.intersection(member.source_handles)
        )
        component = ", ".join(member_ids)
        if not component and message.source_handles:
            component = ", ".join(message.source_handles)
        records.append(
            ProblemRecord(
                message.severity,
                message.code,
                component or "—",
                message.message,
                message.role,
                message.source_handles,
                member_ids,
            )
        )
    severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    return tuple(
        sorted(records, key=lambda item: (severity_order.get(item.severity, 4), item.code, item.component))
    )


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
        items.append(ValidationOverviewItem("success", "工程模型可以匯入 Solver"))
    else:
        items.append(ValidationOverviewItem("error", "存在阻擋錯誤，目前不可匯入 Solver"))
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
