"""Chinese presentation labels for stable project data field names.

The English keys in this module are persistence/API contracts.  Callers must
translate only at the presentation boundary and must never write these labels
back into Project rows or DXF review state.
"""

from __future__ import annotations

from typing import Mapping


TABLE_COLUMN_LABELS: Mapping[str, Mapping[str, str]] = {
    "walers": {
        "No": "列號",
        "WalerID": "圍令編號",
        "StartX": "起點X",
        "StartY": "起點Y",
        "EndX": "終點X",
        "EndY": "終點Y",
        "material_spec": "材料規格",
        "Remark": "備註",
    },
    "struts": {
        "No": "列號",
        "StrutID": "支撐編號",
        "SharedLayoutGroup": "雙路群組",
        "FromWaler": "起點圍令",
        "ToWaler": "終點圍令",
        "StartX": "起點X",
        "StartY": "起點Y",
        "EndX": "終點X",
        "EndY": "終點Y",
        "material_spec": "材料規格",
        "BeamPositions": "托梁位置(mm)",
        "ColumnPositions": "中間柱位置(mm)",
        "AssociatedColumnIDs": "關聯中間柱",
        "AssociatedBeamIDs": "關聯托梁",
        "FromBraceToWalerStartLen": "起點角撐長度(往圍令起點)",
        "FromBraceToWalerEndLen": "起點角撐長度(往圍令終點)",
        "ToBraceToWalerStartLen": "終點角撐長度(往圍令起點)",
        "ToBraceToWalerEndLen": "終點角撐長度(往圍令終點)",
        "TargetJackRegion": "目標千斤頂區域",
        "Zoning": "分區",
    },
    "braces": {
        "No": "列號",
        "BraceID": "斜撐編號",
        "FromWaler": "起點圍令",
        "ToWaler": "終點圍令",
        "StartX": "起點X",
        "StartY": "起點Y",
        "EndX": "終點X",
        "EndY": "終點Y",
    },
    "inventory": {
        "No": "列號",
        "ItemCode": "機料編號",
        "Spec": "規格",
        "Usage": "用途",
        "Length": "料長(mm)",
        "Qty": "庫存數量",
    },
    "material_specs": {
        "No": "列號",
        "Usage": "用途",
        "Spec": "材料規格",
    },
}


DXF_ENGINEERING_FIELD_LABELS: Mapping[str, str] = {
    "ID": "構件編號",
    "StartX": "起點 X",
    "StartY": "起點 Y",
    "EndX": "終點 X",
    "EndY": "終點 Y",
    "material_spec": "材料規格",
    "Remark": "備註",
    "PrimaryAssociatedStrutID": "主要關聯支撐",
    "AssociatedStrutID": "關聯支撐",
    "AssociatedStrutIDs": "所有關聯支撐",
    "AssociationStation": "關聯位置（mm）",
    "AssociationDistance": "關聯距離（mm）",
    "ReferenceX": "參考點 X",
    "ReferenceY": "參考點 Y",
    "SourceLayer": "來源圖層",
    "Path": "工程路徑",
    "WorldPath": "世界座標路徑",
    "LocalPath": "局部座標路徑",
    "Crossings": "支撐交會資料",
    "Length": "構件長度（mm）",
}


RECOGNITION_METHOD_LABELS: Mapping[str, str] = {
    "existing_centerline": "既有中心線",
    "existing_inner_line": "既有內側線",
    "inner_boundary_line": "內側邊界線",
    "closed_outline_axis": "封閉外框中心軸",
    "parallel_edges_midline": "平行邊線中線",
    "mline_center_path": "多線中心路徑",
    "column_section_centroid": "中間柱截面中心軸",
    "connection_plate_midpoints": "連接板中點",
    "connection_face_midpoints": "接觸面中點",
    "brace_centerline_intersections": "角撐中心線交點",
    "segment_intersection": "線段交點",
    "waler_outer_to_continuous_wall_inner": "圍令外側至連續壁內側量測",
}


DXF_ENTITY_TYPE_LABELS: Mapping[str, str] = {
    "LINE": "LINE（線）",
    "LWPOLYLINE": "LWPOLYLINE（輕量聚合線）",
    "POLYLINE": "POLYLINE（聚合線）",
    "MLINE": "MLINE（多線）",
    "INSERT": "INSERT（圖塊參考）",
    "ARC": "ARC（圓弧）",
    "CIRCLE": "CIRCLE（圓）",
    "SPLINE": "SPLINE（雲形線）",
}


ROLE_TABLE_NAMES = {
    "waler": "walers",
    "strut": "struts",
    "brace": "braces",
}


ROLE_FIELD_OVERRIDES: Mapping[str, Mapping[str, str]] = {
    "column": {"ID": "中間柱編號"},
    "beam": {"ID": "托梁編號"},
    "corner_brace": {"ID": "角撐編號"},
}


def build_table_column_labels() -> dict[str, dict[str, str]]:
    """Return mutable per-window copies of the shared table labels."""

    return {
        table_name: dict(labels)
        for table_name, labels in TABLE_COLUMN_LABELS.items()
    }


def engineering_field_label(role: str, field_name: str) -> str:
    """Return a Chinese DXF engineering label without changing the field key."""

    override = ROLE_FIELD_OVERRIDES.get(role, {}).get(field_name)
    if override:
        return override
    table_name = ROLE_TABLE_NAMES.get(role, "")
    shared = TABLE_COLUMN_LABELS.get(table_name, {}).get(field_name)
    if shared:
        return shared
    return DXF_ENGINEERING_FIELD_LABELS.get(field_name, field_name)


def recognition_method_label(method: str) -> str:
    """Return a user-facing recognition description while retaining unknown IDs."""

    normalized = str(method or "").strip()
    if not normalized:
        return "—"
    return RECOGNITION_METHOD_LABELS.get(
        normalized,
        f"其他辨識方式（{normalized}）",
    )


def dxf_entity_type_label(entity_type: str) -> str:
    """Return a Chinese CAD entity label with its stable DXF name."""

    normalized = str(entity_type or "").strip().upper()
    if not normalized:
        return "—"
    return DXF_ENTITY_TYPE_LABELS.get(normalized, normalized)


__all__ = [
    "DXF_ENGINEERING_FIELD_LABELS",
    "DXF_ENTITY_TYPE_LABELS",
    "RECOGNITION_METHOD_LABELS",
    "TABLE_COLUMN_LABELS",
    "build_table_column_labels",
    "dxf_entity_type_label",
    "engineering_field_label",
    "recognition_method_label",
]
