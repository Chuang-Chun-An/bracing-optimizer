"""Material-spec recognition and review updates for DXF engineering members."""

from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .models import DXFImportError, DXFImportResult, Strut, Waler


_H_SECTION_PATTERN = re.compile(
    r"(?i)\bH\s*[-_]?\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)"
)
_ROLE_USAGE = {"waler": "圍令", "strut": "支撐"}


def section_plan_width_mm(material_spec: Any) -> float | None:
    """Return the plan-view flange width B from an HxB material label."""

    match = _H_SECTION_PATTERN.search(str(material_spec or "").strip())
    if match is None:
        return None
    width = float(match.group(2))
    return width if math.isfinite(width) and width > 0.0 else None


def material_spec_options(
    material_specs: Sequence[Mapping[str, Any]],
    usage: str,
) -> tuple[str, ...]:
    """Return stable, case-insensitively unique Project material options."""

    wanted = str(usage or "").strip().casefold()
    options: list[str] = []
    seen: set[str] = set()
    for row in material_specs:
        if str(row.get("Usage", "") or "").strip().casefold() != wanted:
            continue
        spec = str(row.get("Spec", "") or "").strip()
        key = spec.casefold()
        if not spec or key in seen:
            continue
        seen.add(key)
        options.append(spec)
    return tuple(options)


def recognize_material_spec_from_width(
    source_width: Any,
    usage: str,
    material_specs: Sequence[Mapping[str, Any]],
    *,
    tolerance_mm: float = 1.0,
) -> str:
    """Return a spec only when drawing width identifies exactly one option."""

    try:
        width = float(source_width)
        tolerance = max(0.0, float(tolerance_mm))
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(width) or width <= 0.0:
        return ""
    matches = tuple(
        spec
        for spec in material_spec_options(material_specs, usage)
        if (
            (candidate_width := section_plan_width_mm(spec)) is not None
            and abs(candidate_width - width) <= tolerance
        )
    )
    return matches[0] if len(matches) == 1 else ""


def recognize_result_material_specs(
    result: DXFImportResult,
    material_specs: Sequence[Mapping[str, Any]],
    *,
    tolerance_mm: float = 1.0,
) -> DXFImportResult:
    """Populate Waler/Strut specs from their recognized physical widths."""

    def recognize(member: Waler | Strut, usage: str) -> Waler | Strut:
        spec = recognize_material_spec_from_width(
            member.source_width,
            usage,
            material_specs,
            tolerance_mm=tolerance_mm,
        )
        return replace(
            member,
            material_spec=spec,
            material_spec_source="auto_width" if spec else "",
        )

    return replace(
        result,
        walers=tuple(recognize(member, "圍令") for member in result.walers),
        struts=tuple(recognize(member, "支撐") for member in result.struts),
    )


def set_member_material_spec(
    result: DXFImportResult,
    member_id: str,
    material_spec: Any,
) -> DXFImportResult:
    """Apply one STEP4 material choice without changing member geometry."""

    spec = str(material_spec or "").strip()
    found = False

    def update(member: Waler | Strut) -> Waler | Strut:
        nonlocal found
        if member.id != member_id:
            return member
        found = True
        return replace(
            member,
            material_spec=spec,
            material_spec_source="manual",
        )

    updated = replace(
        result,
        walers=tuple(update(member) for member in result.walers),
        struts=tuple(update(member) for member in result.struts),
    )
    if not found:
        raise DXFImportError(f"{member_id} 不是可設定材料規格的 Waler 或 Strut。")
    return updated


def restore_manual_material_specs_from_debug(
    result: DXFImportResult,
    debug_state: Mapping[str, Any] | None,
    material_specs: Sequence[Mapping[str, Any]],
) -> DXFImportResult:
    """Restore only explicit STEP4 choices from the same DXF source."""

    if not isinstance(debug_state, Mapping):
        return result
    saved_source = str(debug_state.get("source_path", "") or "")
    try:
        same_source = Path(saved_source).resolve() == Path(result.source_path).resolve()
    except (OSError, ValueError):
        same_source = saved_source == result.source_path
    if not same_source:
        return result
    converted = debug_state.get("converted")
    if not isinstance(converted, Mapping):
        return result

    current = result
    for role, key in (("waler", "walers"), ("strut", "struts")):
        allowed = {
            value.casefold()
            for value in material_spec_options(material_specs, _ROLE_USAGE[role])
        }
        raw_members = converted.get(key, ())
        if not isinstance(raw_members, Sequence) or isinstance(
            raw_members, (str, bytes)
        ):
            continue
        current_members = current.walers if role == "waler" else current.struts
        by_handles = {
            tuple(sorted(member.source_handles)): member.id
            for member in current_members
        }
        for raw in raw_members:
            if not isinstance(raw, Mapping):
                continue
            if str(raw.get("material_spec_source", "") or "") != "manual":
                continue
            handles = raw.get("source_handles", ())
            if not isinstance(handles, Sequence) or isinstance(handles, (str, bytes)):
                continue
            member_id = by_handles.get(tuple(sorted(str(value) for value in handles)))
            if member_id is None:
                continue
            spec = str(raw.get("material_spec", "") or "").strip()
            if spec and allowed and spec.casefold() not in allowed:
                continue
            current = set_member_material_spec(current, member_id, spec)
    return current


__all__ = [
    "material_spec_options",
    "recognize_material_spec_from_width",
    "recognize_result_material_specs",
    "restore_manual_material_specs_from_debug",
    "section_plan_width_mm",
    "set_member_material_spec",
]
