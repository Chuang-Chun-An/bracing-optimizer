"""Mappings between editable/project JSON rows and core domain entities."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from bracing_optimizer.domain.project_domain import (
    Brace,
    LineSegment,
    Point,
    ProjectDomainModel,
    Strut,
    SupportGroup,
    Waler,
)


class ProjectDomainMappingError(ValueError):
    def __init__(self, issues: Sequence[str]):
        self.issues = tuple(str(issue) for issue in issues if str(issue).strip())
        super().__init__("\n".join(self.issues))


def _number(value: Any) -> float | int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _text(value: Any) -> str:
    return str(value or "").strip()


def _axis(row: Mapping[str, Any]) -> LineSegment | None:
    values = tuple(
        _number(row.get(field))
        for field in ("StartX", "StartY", "EndX", "EndY")
    )
    if any(value is None for value in values):
        return None
    start_x, start_y, end_x, end_y = values
    return LineSegment(Point(start_x, start_y), Point(end_x, end_y))


def _numeric(value: Any, default: float = 0.0) -> float:
    number = _number(value)
    return float(default if number is None else number)


def _position_list(value: Any) -> tuple[list[float], str | None]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        tokens = list(value)
    else:
        text = str(value or "").strip().replace("，", ",")
        if not text:
            return [], None
        tokens = text.split(",")
    positions = []
    for token in tokens:
        number = _number(token)
        if number is None:
            return [], f"{token} 不是有效數字"
        positions.append(float(number))
    return positions, None


class ProjectRowMapper:
    """Translate storage/UI rows without leaking those keys into the domain."""

    @staticmethod
    def waler(row: Mapping[str, Any]) -> Waler:
        return Waler(
            id=_text(row.get("WalerID")),
            axis=_axis(row),
            material_spec=_text(row.get("material_spec")),
            remark=_text(row.get("Remark")),
        )

    @staticmethod
    def strut(row: Mapping[str, Any]) -> Strut:
        target = _number(row.get("TargetJackRegion"))
        column_positions, column_error = _position_list(
            row.get("ColumnPositions")
        )
        beam_positions, beam_error = _position_list(row.get("BeamPositions"))
        issues = []
        if column_error:
            issues.append(f"ColumnPositions：{column_error}")
        if beam_error:
            issues.append(f"BeamPositions：{beam_error}")
        if issues:
            raise ProjectDomainMappingError(issues)
        return Strut(
            id=_text(row.get("StrutID")),
            axis=_axis(row),
            shared_layout_group=_text(row.get("SharedLayoutGroup")),
            from_waler_id=_text(row.get("FromWaler")),
            to_waler_id=_text(row.get("ToWaler")),
            material_spec=_text(row.get("material_spec")),
            target_jack_region=int(target) if target is not None else 2,
            zoning=_text(row.get("Zoning")),
            from_brace_to_waler_start_len=_numeric(
                row.get("FromBraceToWalerStartLen")
            ),
            from_brace_to_waler_end_len=_numeric(
                row.get("FromBraceToWalerEndLen")
            ),
            to_brace_to_waler_start_len=_numeric(
                row.get("ToBraceToWalerStartLen")
            ),
            to_brace_to_waler_end_len=_numeric(
                row.get("ToBraceToWalerEndLen")
            ),
            column_positions=tuple(column_positions),
            beam_positions=tuple(beam_positions),
        )

    @staticmethod
    def brace(row: Mapping[str, Any]) -> Brace:
        return Brace(
            id=_text(row.get("BraceID")),
            axis=_axis(row),
            from_waler_id=_text(row.get("FromWaler")),
            to_waler_id=_text(row.get("ToWaler")),
        )

    @classmethod
    def project(
        cls,
        *,
        walers: Sequence[Mapping[str, Any]],
        struts: Sequence[Mapping[str, Any]],
        braces: Sequence[Mapping[str, Any]],
        strict: bool = True,
    ) -> ProjectDomainModel:
        strut_models = tuple(cls.strut(row) for row in struts)
        grouped_member_ids: dict[str, list[str]] = {}
        for strut in strut_models:
            if strut.shared_layout_group:
                grouped_member_ids.setdefault(strut.shared_layout_group, []).append(
                    strut.id
                )
        project = ProjectDomainModel(
            walers=tuple(cls.waler(row) for row in walers),
            struts=strut_models,
            braces=tuple(cls.brace(row) for row in braces),
            support_groups=tuple(
                SupportGroup(group_id, tuple(member_ids))
                for group_id, member_ids in grouped_member_ids.items()
            ),
        )
        if strict and (issues := project.validation_issues()):
            raise ProjectDomainMappingError(issues)
        return project


__all__ = ["ProjectDomainMappingError", "ProjectRowMapper"]
