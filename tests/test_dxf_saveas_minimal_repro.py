from __future__ import annotations

import json
import re
import unittest
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import ezdxf
from ezdxf.audit import AuditError


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DXF = ROOT / "project_cases" / "Y1A站第一層支撐" / "source" / "source.dxf"
FULL_EXPORT_DXF = ROOT / "source_配置標註.dxf"
JACK_ASSET_DXF = ROOT / "assets" / "dxf" / "jack_symbol.dxf"
ARTIFACT_DIR = ROOT / "tmp" / "dxf_minimal_repro"

RESAVED_DXF = ARTIFACT_DIR / "02_immediate_saveas.dxf"
DIMENSION_DXF = ARTIFACT_DIR / "03_add_one_dimension.dxf"
BLOCK_DXF = ARTIFACT_DIR / "04_add_jack_block.dxf"
REPORT_JSON = ARTIFACT_DIR / "audit_report.json"
REPORT_MD = ARTIFACT_DIR / "audit_report.md"

HANDLE_RE = re.compile(r"\(#([0-9A-F]+)\)", re.IGNORECASE)
OWNER_RE = re.compile(r"owner handle #([0-9A-F]+)", re.IGNORECASE)


def _alive_entities(document) -> Iterable[Any]:
    return (
        entity
        for entity in document.entitydb.values()
        if entity is not None and entity.is_alive
    )


def _counter_dict(counter: Counter) -> dict[str, int]:
    return dict(sorted((str(key), int(value)) for key, value in counter.items()))


def _count_types(entities: Iterable[Any]) -> dict[str, int]:
    return _counter_dict(Counter(entity.dxftype() for entity in entities))


def _dictionary_key(document, dictionary, child_handle: str) -> str | None:
    if dictionary is None or dictionary.dxftype() != "DICTIONARY":
        return None
    for key, entity in dictionary.items():
        if entity is not None and entity.dxf.get("handle") == child_handle:
            return str(key)
    return None


def _ownership_info(
    document,
    entity,
    source_layer_by_handle: dict[str, str],
) -> dict[str, Any]:
    handle = entity.dxf.get("handle")
    owner = entity.dxf.get("owner")
    parent = document.entitydb.get(owner) if owner else None
    dictionary_handle = (
        parent.dxf.get("handle")
        if parent is not None and parent.dxftype() == "DICTIONARY"
        else None
    )
    dictionary_key = _dictionary_key(document, parent, handle)

    chain: list[dict[str, Any]] = []
    next_handle = owner
    visited: set[str] = set()
    layer_handle = None
    layer_name = None
    layer_status = None
    while next_handle and next_handle not in visited and len(chain) < 16:
        visited.add(next_handle)
        ancestor = document.entitydb.get(next_handle)
        if ancestor is None:
            layer_name = source_layer_by_handle.get(next_handle)
            if layer_name is not None:
                layer_handle = next_handle
                layer_status = "missing_after_saveas"
            chain.append(
                {
                    "handle": next_handle,
                    "type": "MISSING",
                    "owner": None,
                }
            )
            break
        ancestor_type = ancestor.dxftype()
        chain.append(
            {
                "handle": next_handle,
                "type": ancestor_type,
                "owner": ancestor.dxf.get("owner"),
            }
        )
        if ancestor_type == "LAYER":
            layer_handle = next_handle
            layer_name = ancestor.dxf.get("name")
            layer_status = "present"
            break
        next_handle = ancestor.dxf.get("owner")

    return {
        "handle": handle,
        "owner": owner,
        "dictionary_handle": dictionary_handle,
        "dictionary_key": dictionary_key,
        "layer_handle": layer_handle,
        "layer_name": layer_name,
        "layer_status": layer_status,
        "owner_chain": chain,
    }


def _issue_record(
    issue,
    pre_audit_entities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    message = str(issue.message)
    handle_match = HANDLE_RE.search(message)
    owner_match = OWNER_RE.search(message)
    entity_handle = handle_match.group(1).upper() if handle_match else None
    detail = dict(pre_audit_entities.get(entity_handle, {}))
    code = int(issue.code)
    try:
        error_type = AuditError(code).name
    except ValueError:
        error_type = f"UNKNOWN_{code}"
    detail.update(
        {
            "code": code,
            "error_type": error_type,
            "message": message,
            "handle": entity_handle or detail.get("handle"),
            "reported_owner": (
                owner_match.group(1).upper() if owner_match else None
            ),
        }
    )
    return detail


def _snapshot(
    case_name: str,
    path: Path,
    source_layer_by_handle: dict[str, str],
) -> dict[str, Any]:
    document = ezdxf.readfile(path)
    alive = list(_alive_entities(document))
    objects = list(document.objects)
    modelspace = list(document.modelspace())
    block_content = [entity for block in document.blocks for entity in block]
    dictionaries = [entity for entity in objects if entity.dxftype() == "DICTIONARY"]
    xrecords = [entity for entity in objects if entity.dxftype() == "XRECORD"]

    dictionary_owner_types = Counter()
    dictionary_keys = Counter()
    for dictionary in dictionaries:
        owner = document.entitydb.get(dictionary.dxf.get("owner"))
        dictionary_owner_types[owner.dxftype() if owner is not None else "MISSING"] += 1
        for key, _entity in dictionary.items():
            dictionary_keys[str(key)] += 1

    ownership = {
        entity.dxf.handle: _ownership_info(
            document,
            entity,
            source_layer_by_handle,
        )
        for entity in xrecords
    }
    xrecord_dictionary_keys = Counter(
        detail.get("dictionary_key") or "<no dictionary key>"
        for detail in ownership.values()
    )
    xrecord_layer_resolution = Counter(
        detail.get("layer_status") or "not layer-owned"
        for detail in ownership.values()
    )

    duplicate_layers: dict[str, list[dict[str, str]]] = {}
    layers_by_name: dict[str, list[Any]] = {}
    for entity in alive:
        if entity.dxftype() == "LAYER":
            layers_by_name.setdefault(entity.dxf.name.casefold(), []).append(entity)
    for entities in layers_by_name.values():
        if len(entities) > 1:
            duplicate_layers[entities[0].dxf.name] = [
                {"handle": entity.dxf.handle, "name": entity.dxf.name}
                for entity in entities
            ]

    auditor = document.audit()
    errors = [_issue_record(issue, ownership) for issue in auditor.errors]
    fixes = [_issue_record(issue, ownership) for issue in auditor.fixes]
    post_audit_objects = list(document.objects)
    post_audit_dictionaries = [
        entity
        for entity in post_audit_objects
        if entity.dxftype() == "DICTIONARY"
    ]
    post_audit_xrecords = [
        entity for entity in post_audit_objects if entity.dxftype() == "XRECORD"
    ]
    issue_types = Counter(
        f"error:{issue['error_type']}" for issue in errors
    ) + Counter(f"fix:{issue['error_type']}" for issue in fixes)

    return {
        "case": case_name,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "dxfversion": document.dxfversion,
        "encoding": document.encoding,
        "counts": {
            "entitydb": _count_types(alive),
            "modelspace": _count_types(modelspace),
            "block_content": _count_types(block_content),
            "objects": _count_types(objects),
        },
        "dictionary": {
            "total": len(dictionaries),
            "by_owner_type": _counter_dict(dictionary_owner_types),
            "entry_keys": _counter_dict(dictionary_keys),
        },
        "xrecord": {
            "total": len(xrecords),
            "by_dictionary_key": _counter_dict(xrecord_dictionary_keys),
            "by_layer_resolution": _counter_dict(xrecord_layer_resolution),
        },
        "layer_table_entry_count": len(document.layers),
        "duplicate_layer_records": duplicate_layers,
        "audit": {
            "error_count": len(errors),
            "fix_count": len(fixes),
            "issue_types": _counter_dict(issue_types),
            "errors": errors,
            "fixes": fixes,
            "post_audit_dictionary_total": len(post_audit_dictionaries),
            "post_audit_xrecord_total": len(post_audit_xrecords),
        },
    }


def _delta(current: dict[str, int], base: dict[str, int]) -> dict[str, int]:
    keys = sorted(set(current) | set(base))
    return {
        key: current.get(key, 0) - base.get(key, 0)
        for key in keys
        if current.get(key, 0) != base.get(key, 0)
    }


def _add_one_dimension(source_path: Path, output_path: Path) -> None:
    document = ezdxf.readfile(source_path)
    dimension = document.modelspace().add_aligned_dim(
        p1=(338238.287, -722795.569),
        p2=(340288.287, -722795.569),
        distance=650.0,
        text="<>",
        dimstyle="Standard",
        dxfattribs={"layer": "0"},
    )
    dimension.render()
    document.saveas(output_path)


def _add_jack_block(source_path: Path, output_path: Path) -> None:
    document = ezdxf.readfile(source_path)
    asset_document = ezdxf.readfile(JACK_ASSET_DXF)
    asset_block = asset_document.blocks.get("SUPPORT_JACK")
    block = document.blocks.new("MIN_REPRO_SUPPORT_JACK", base_point=(0, 0, 0))
    attribs = {"layer": "0", "color": 256, "linetype": "BYLAYER"}
    for entity in asset_block:
        if entity.dxftype() == "LINE":
            block.add_line(entity.dxf.start, entity.dxf.end, dxfattribs=attribs)
        elif entity.dxftype() == "CIRCLE":
            block.add_circle(
                entity.dxf.center,
                entity.dxf.radius,
                dxfattribs=attribs,
            )
        else:
            raise AssertionError(f"Unexpected jack entity: {entity.dxftype()}")
    document.modelspace().add_blockref(
        "MIN_REPRO_SUPPORT_JACK",
        (338238.287, -722795.569),
        dxfattribs={"layer": "0"},
    )
    document.saveas(output_path)


def _issue_fingerprint(case: dict[str, Any]) -> set[tuple[Any, ...]]:
    issues = case["audit"]["errors"] + case["audit"]["fixes"]
    return {
        (
            issue.get("code"),
            issue.get("handle"),
            issue.get("owner"),
            issue.get("dictionary_handle"),
            issue.get("dictionary_key"),
            issue.get("layer_handle"),
            issue.get("layer_name"),
        )
        for issue in issues
    }


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return ["（無）"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(value).replace("|", "\\|") for value in row)
            + " |"
        )
    return lines


def _write_report(cases: list[dict[str, Any]]) -> None:
    base = cases[0]
    payload = {
        "ezdxf_version": ezdxf.__version__,
        "cases": cases,
        "deltas_from_original": {
            case["case"]: {
                "entitydb": _delta(
                    case["counts"]["entitydb"], base["counts"]["entitydb"]
                ),
                "modelspace": _delta(
                    case["counts"]["modelspace"], base["counts"]["modelspace"]
                ),
                "block_content": _delta(
                    case["counts"]["block_content"],
                    base["counts"]["block_content"],
                ),
                "objects": _delta(
                    case["counts"]["objects"], base["counts"]["objects"]
                ),
                "dictionary_by_owner_type": _delta(
                    case["dictionary"]["by_owner_type"],
                    base["dictionary"]["by_owner_type"],
                ),
                "dictionary_entry_keys": _delta(
                    case["dictionary"]["entry_keys"],
                    base["dictionary"]["entry_keys"],
                ),
                "xrecord_by_dictionary_key": _delta(
                    case["xrecord"]["by_dictionary_key"],
                    base["xrecord"]["by_dictionary_key"],
                ),
                "xrecord_by_layer_resolution": _delta(
                    case["xrecord"]["by_layer_resolution"],
                    base["xrecord"]["by_layer_resolution"],
                ),
            }
            for case in cases
        },
    }
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# DXF saveas 最小重現 Audit 報告",
        "",
        f"ezdxf 版本：`{ezdxf.__version__}`",
        "",
        "## 案例摘要",
        "",
    ]
    lines.extend(
        _markdown_table(
            [
                "案例",
                "檔案",
                "bytes",
                "EntityDB",
                "Layer records / table entries",
                "Dictionary pre → post Audit",
                "XRecord pre → post Audit",
                "Audit errors",
                "Audit fixes",
                "錯誤類型",
            ],
            [
                [
                    case["case"],
                    case["path"],
                    case["size_bytes"],
                    sum(case["counts"]["entitydb"].values()),
                    (
                        f"{case['counts']['entitydb'].get('LAYER', 0)} / "
                        f"{case['layer_table_entry_count']}"
                    ),
                    (
                        f"{case['dictionary']['total']} → "
                        f"{case['audit']['post_audit_dictionary_total']}"
                    ),
                    (
                        f"{case['xrecord']['total']} → "
                        f"{case['audit']['post_audit_xrecord_total']}"
                    ),
                    case["audit"]["error_count"],
                    case["audit"]["fix_count"],
                    ", ".join(
                        f"{key}={value}"
                        for key, value in case["audit"]["issue_types"].items()
                    )
                    or "無",
                ]
                for case in cases
            ],
        )
    )

    lines.extend(["", "## Audit 明細", ""])
    audit_rows = []
    for case in cases:
        for disposition in ("errors", "fixes"):
            for issue in case["audit"][disposition]:
                audit_rows.append(
                    [
                        case["case"],
                        "error" if disposition == "errors" else "fix",
                        issue.get("error_type"),
                        issue.get("handle"),
                        issue.get("owner"),
                        issue.get("dictionary_handle"),
                        issue.get("dictionary_key"),
                        issue.get("layer_handle"),
                        issue.get("layer_name"),
                        issue.get("layer_status"),
                    ]
                )
    lines.extend(
        _markdown_table(
            [
                "案例",
                "類別",
                "錯誤類型",
                "Handle",
                "Owner",
                "Dictionary",
                "Dictionary Key",
                "Layer Handle",
                "Layer",
                "Layer 狀態",
            ],
            audit_rows,
        )
    )

    count_groups = (
        ("EntityDB 實體數量差異", "entitydb"),
        ("Modelspace 實體數量差異", "modelspace"),
        ("Block 內容實體數量差異", "block_content"),
        ("OBJECTS 實體數量差異", "objects"),
        ("Dictionary owner 類型數量差異", "dictionary_by_owner_type"),
        ("Dictionary entry key 數量差異", "dictionary_entry_keys"),
        ("XRecord Dictionary key 數量差異", "xrecord_by_dictionary_key"),
        ("XRecord Layer 解析數量差異", "xrecord_by_layer_resolution"),
    )
    for title, key in count_groups:
        lines.extend(["", f"## {title}（相對原始檔）", ""])
        rows = []
        for case in cases[1:]:
            for entity_type, delta in payload["deltas_from_original"][case["case"]][
                key
            ].items():
                rows.append([case["case"], entity_type, f"{delta:+d}"])
        lines.extend(_markdown_table(["案例", "類型", "差異"], rows))

    lines.extend(["", "## 原始檔重複 Layer records", ""])
    duplicate_rows = []
    for name, records in base["duplicate_layer_records"].items():
        duplicate_rows.append(
            [name, ", ".join(record["handle"] for record in records)]
        )
    lines.extend(_markdown_table(["Layer", "Handles"], duplicate_rows))

    fingerprints = [_issue_fingerprint(case) for case in cases]
    saveas_matches_complete = fingerprints[1] == fingerprints[4]
    dimension_added_no_issue = fingerprints[2] == fingerprints[1]
    block_added_no_issue = fingerprints[3] == fingerprints[1]
    lines.extend(
        [
            "",
            "## 判斷",
            "",
            f"- 單純 saveas 與完整匯出的 Audit 問題完全相同：`{saveas_matches_complete}`",
            f"- 加入 Dimension 後沒有新增 Audit 問題：`{dimension_added_no_issue}`",
            f"- 加入 Block 後沒有新增 Audit 問題：`{block_added_no_issue}`",
            "- 若上述三項皆為 True，最小重現已證明問題由 ezdxf 對這份來源檔重新儲存所觸發，不是 Dimension、Block 或完整匯出迴圈額外造成。",
            "",
        ]
    )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


@unittest.skipUnless(SOURCE_DXF.is_file(), f"Missing fixture: {SOURCE_DXF}")
@unittest.skipUnless(FULL_EXPORT_DXF.is_file(), f"Missing fixture: {FULL_EXPORT_DXF}")
@unittest.skipUnless(JACK_ASSET_DXF.is_file(), f"Missing fixture: {JACK_ASSET_DXF}")
class DXFSaveasMinimalReproTests(unittest.TestCase):
    def test_compare_source_saveas_dimension_block_and_full_export(self):
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

        document = ezdxf.readfile(SOURCE_DXF)
        document.saveas(RESAVED_DXF)
        _add_one_dimension(SOURCE_DXF, DIMENSION_DXF)
        _add_jack_block(SOURCE_DXF, BLOCK_DXF)

        original = ezdxf.readfile(SOURCE_DXF)
        source_layer_by_handle = {
            entity.dxf.handle: entity.dxf.name
            for entity in _alive_entities(original)
            if entity.dxftype() == "LAYER"
        }
        cases = [
            _snapshot("01_original_source", SOURCE_DXF, source_layer_by_handle),
            _snapshot("02_immediate_saveas", RESAVED_DXF, source_layer_by_handle),
            _snapshot("03_add_one_dimension", DIMENSION_DXF, source_layer_by_handle),
            _snapshot("04_add_jack_block", BLOCK_DXF, source_layer_by_handle),
            _snapshot("05_full_export", FULL_EXPORT_DXF, source_layer_by_handle),
        ]
        _write_report(cases)

        original_issues = _issue_fingerprint(cases[0])
        saveas_issues = _issue_fingerprint(cases[1])
        dimension_issues = _issue_fingerprint(cases[2])
        block_issues = _issue_fingerprint(cases[3])
        full_export_issues = _issue_fingerprint(cases[4])

        self.assertEqual(set(), original_issues)
        self.assertTrue(saveas_issues)
        self.assertEqual(saveas_issues, dimension_issues)
        self.assertEqual(saveas_issues, block_issues)
        self.assertEqual(saveas_issues, full_export_issues)
        self.assertEqual(
            {AuditError.INVALID_OWNER_HANDLE.value},
            {issue[0] for issue in saveas_issues},
        )


if __name__ == "__main__":
    unittest.main()
