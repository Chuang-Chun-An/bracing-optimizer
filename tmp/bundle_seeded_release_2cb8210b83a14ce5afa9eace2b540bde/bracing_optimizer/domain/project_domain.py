"""Core engineering entities for one support-distribution project.

These models contain confirmed project meaning only.  DXF recognition
metadata (handles, confidence, candidate points, world/local alternatives)
belongs to the import model and is mapped into these entities at the project
boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.x)) or not math.isfinite(float(self.y)):
            raise ValueError("座標必須是有限數值")

    def as_tuple(self) -> tuple[float, float]:
        return float(self.x), float(self.y)


@dataclass(frozen=True)
class LineSegment:
    start: Point
    end: Point

    @property
    def length(self) -> float:
        return math.hypot(
            self.end.x - self.start.x,
            self.end.y - self.start.y,
        )


@dataclass(frozen=True)
class Waler:
    id: str
    axis: LineSegment | None
    material_spec: str = ""
    remark: str = ""


@dataclass(frozen=True)
class Strut:
    id: str
    axis: LineSegment | None
    shared_layout_group: str = ""
    from_waler_id: str = ""
    to_waler_id: str = ""
    material_spec: str = ""
    target_jack_region: int = 2
    zoning: str = ""
    from_brace_to_waler_start_len: float = 0.0
    from_brace_to_waler_end_len: float = 0.0
    to_brace_to_waler_start_len: float = 0.0
    to_brace_to_waler_end_len: float = 0.0
    column_positions: tuple[float, ...] = ()
    beam_positions: tuple[float, ...] = ()


@dataclass(frozen=True)
class Brace:
    id: str
    axis: LineSegment | None
    from_waler_id: str = ""
    to_waler_id: str = ""


@dataclass(frozen=True)
class SupportGroup:
    """Physical struts that must use one ordered material layout."""

    id: str
    member_ids: tuple[str, ...]
    require_shared_layout: bool = True


@dataclass(frozen=True)
class ProjectDomainModel:
    walers: tuple[Waler, ...] = ()
    struts: tuple[Strut, ...] = ()
    braces: tuple[Brace, ...] = ()
    support_groups: tuple[SupportGroup, ...] = ()

    def validation_issues(self) -> tuple[str, ...]:
        """Return aggregate identity/reference violations without UI wording."""

        issues = []
        collections = (
            ("Waler", self.walers),
            ("Strut", self.struts),
            ("Brace", self.braces),
        )
        for type_name, entities in collections:
            identifiers = [entity.id.strip() for entity in entities]
            if any(not identifier for identifier in identifiers):
                issues.append(f"{type_name} ID 不可空白")
            duplicates = sorted({item for item in identifiers if item and identifiers.count(item) > 1})
            if duplicates:
                issues.append(f"{type_name} ID 重複：{', '.join(duplicates)}")
        for strut in self.struts:
            for label, positions in (
                ("ColumnPositions", strut.column_positions),
                ("BeamPositions", strut.beam_positions),
            ):
                if any(
                    not math.isfinite(float(position)) or float(position) < 0
                    for position in positions
                ):
                    issues.append(f"Strut {strut.id or '<未命名>'} 的 {label} 無效")
        struts_by_id = {strut.id: strut for strut in self.struts if strut.id}
        for group in self.support_groups:
            if len(group.member_ids) != 2:
                issues.append(
                    f"雙路支撐群組 {group.id} 必須剛好包含兩支實體支撐"
                )
                continue
            members = [struts_by_id.get(member_id) for member_id in group.member_ids]
            if any(member is None for member in members):
                issues.append(f"雙路支撐群組 {group.id} 含有不存在的支撐")
                continue
            first, second = members
            if first.zoning != second.zoning:
                issues.append(f"雙路支撐群組 {group.id} 的兩支支撐必須位於相同分區")
            if first.material_spec != second.material_spec:
                issues.append(f"雙路支撐群組 {group.id} 的材料規格必須相同")
            if (
                first.from_waler_id,
                first.to_waler_id,
            ) != (
                second.from_waler_id,
                second.to_waler_id,
            ):
                issues.append(
                    f"雙路支撐群組 {group.id} 的兩支支撐必須使用相同圍令方向"
                )
        return tuple(issues)

    def waler_by_id(self, waler_id: str) -> Waler | None:
        target = str(waler_id or "").strip()
        return next((item for item in self.walers if item.id == target), None)


__all__ = [
    "Brace",
    "LineSegment",
    "Point",
    "ProjectDomainModel",
    "Strut",
    "SupportGroup",
    "Waler",
]
