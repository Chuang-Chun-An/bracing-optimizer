from __future__ import annotations

import ast
import re
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace

from bracing_optimizer.presentation.cad_view_interaction import CADViewport

from dxf_import.dialog import DXFImportDialog
from dxf_import.models import (
    DXFImportResult,
    EntityDebugInfo,
    ExcludedSource,
    ProblemRecord,
    ReviewItem,
    SelectionState,
    SourceGeometry,
    Strut,
    ValidationMessage,
)
from dxf_import.preview import RenderDirty, TreeSelectionSynchronizer
from dxf_import.validation import (
    DXF_REVIEW_DIAGNOSTIC_CODES,
    FALLBACK_DESCRIPTION_CODES,
    FORMATTER_DESCRIPTION_CODES,
    PRESERVE_MESSAGE_CODES,
    assert_problem_code_catalog_complete,
    build_problem_records,
    build_review_items,
    review_item_guidance,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DIAGNOSTIC_PRODUCER_PATHS = (
    "dxf_import/candidate_points.py",
    "dxf_import/importer.py",
    "dxf_import/hatch_waler_recognition.py",
    "dxf_import/block_member_recognition.py",
    "dxf_import/joist_recognition.py",
    "dxf_import/recognition.py",
    "dxf_import/waler_contact_face.py",
    "dxf_import/validation.py",
    "dxf_import/waler_contact_adjustment.py",
)
_NON_MESSAGE_UPPERCASE_LITERALS = frozenset(
    {
        "BIM_JOIST_WHOLE_SOURCE_AXIS_FAILED",
        "BRACE_STATION_INVALID",
        "CAD_TEMP",
        "HATCH_WALER_CONFIDENCE",
        "HATCH_WALER_RECOGNIZED",
        "INVALID_WALER_CONTACT_VALUE",
        "JOIST_COLUMN_TERMINAL_WINDOW_MM",
        "JOIST_PAIR_COLUMN_MIDPOINT_TOLERANCE_MM",
        "JOIST_PAIR_NOMINAL_STATION_SPACING_MM",
        "JOIST_PAIR_STATION_SPACING_TOLERANCE_MM",
        "JOIST_STRUT_FACE_CONTACT_TOLERANCE_MM",
        "MANUAL_LINE_SELECTION",
        "NO_HANDLE_",
        "NO_HANDLE_HATCH",
        "NO_HANDLE_TEXT_",
        "NUMERICAL_GEOMETRY_PRECISION_MM",
        "SIGNIFICANT_WALER_OVERLAP_RATIO",
        "TEXT_SUMMARY",
    }
)
_DIAGNOSTIC_LITERAL_PATTERN = re.compile(r"[A-Z][A-Z0-9_]+")


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _literal_validation_message_codes(tree: ast.AST) -> set[str]:
    codes = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) != "ValidationMessage":
            continue
        code_node = node.args[1] if len(node.args) > 1 else next(
            (item.value for item in node.keywords if item.arg == "code"),
            None,
        )
        if isinstance(code_node, ast.Constant) and isinstance(code_node.value, str):
            codes.add(code_node.value)
    return codes


def _importer_engineering_roles(tree: ast.AST) -> tuple[str, ...]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "engineering_roles"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, (ast.Tuple, ast.List)):
            continue
        roles = tuple(
            item.value
            for item in node.value.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        )
        if roles:
            return roles
    raise AssertionError("找不到 importer engineering_roles，請更新 producer inventory")


def _producer_diagnostic_codes() -> set[str]:
    trees = {
        relative_path: ast.parse(
            (_PROJECT_ROOT / relative_path).read_text(encoding="utf-8"),
            filename=relative_path,
        )
        for relative_path in _DIAGNOSTIC_PRODUCER_PATHS
    }
    codes = set()
    for relative_path, tree in trees.items():
        if relative_path == "dxf_import/validation.py":
            # validation.py 同時持有 catalog；只收集實際建構的訊息，避免
            # catalog 自己證明自己完整。
            codes.update(_literal_validation_message_codes(tree))
            continue
        codes.update(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _DIAGNOSTIC_LITERAL_PATTERN.fullmatch(node.value)
            and "_" in node.value
        )

    importer_tree = trees["dxf_import/importer.py"]
    engineering_roles = _importer_engineering_roles(importer_tree)
    codes.update(f"{role.upper()}_RECOGNITION_FAILED" for role in engineering_roles)
    codes.update(
        f"{role.upper()}_CENTERLINE_FAILED"
        for role in engineering_roles
        if role != "waler"
    )
    return codes - _NON_MESSAGE_UPPERCASE_LITERALS


class _Variable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _ReviewTree:
    def __init__(self):
        self.rows = {}
        self._selection = ()
        self.focused = ""
        self.on_selection_set = None

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *iids):
        for iid in iids:
            self.rows.pop(iid, None)

    def insert(
        self,
        parent,
        _position,
        *,
        iid,
        text="",
        values=(),
        tags=(),
        open=False,
    ):
        self.rows[iid] = {
            "parent": parent,
            "text": text,
            "values": tuple(values),
            "tags": tuple(tags),
            "open": open,
        }

    def selection(self):
        return self._selection

    def exists(self, iid):
        return iid in self.rows

    def selection_set(self, iid):
        self._selection = (iid,)
        if self.on_selection_set is not None:
            self.on_selection_set()

    def focus(self, iid):
        self.focused = iid

    def see(self, _iid):
        return None


def _strut(
    identifier: str,
    handle: str,
    *,
    selection_source: str = "auto",
) -> Strut:
    return Strut(
        id=identifier,
        start=(0.0, 0.0),
        end=(1000.0, 0.0),
        source_layer="STRUT",
        source_handles=(handle,),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=0.0,
        from_waler="W1",
        to_waler="W2",
        confidence=1.0,
        selection_source=selection_source,
    )


def _result(
    *,
    struts=(),
    messages=(),
    entity_debug=(),
    source_geometry=(),
    excluded_sources=(),
) -> DXFImportResult:
    return DXFImportResult(
        source_path="review.dxf",
        layer_names=("STRUT", "BEAM"),
        selected_layers={"strut": ("STRUT",), "beam": ("BEAM",)},
        layer_info=(),
        walers=(),
        struts=tuple(struts),
        braces=(),
        columns=(),
        beams=(),
        corner_braces=(),
        entity_debug=tuple(entity_debug),
        messages=tuple(messages),
        source_entity_counts={},
        source_geometry=tuple(source_geometry),
        excluded_sources=tuple(excluded_sources),
    )


def _unresolved_review_item(
    key: str = "source:beam:6EF",
    handle: str = "6EF",
    *,
    severity: str = "error",
    status: str = "unresolved",
) -> ReviewItem:
    return ReviewItem(
        key,
        f"來源-{handle}",
        "beam",
        status,
        None,
        (handle,),
        ("BEAM",),
        ("LINE",),
        "",
        (_problem(severity, "FAILED", role="beam", handles=(handle,)),),
        severity,
    )


def _problem(
    severity: str,
    code: str,
    *,
    role="strut",
    handles=(),
    member_ids=(),
) -> ProblemRecord:
    return ProblemRecord(
        severity,
        code,
        ", ".join(member_ids or handles) or "—",
        f"{code} description",
        role,
        tuple(handles),
        tuple(member_ids),
    )


class ReviewProjectionTests(unittest.TestCase):
    def test_problem_record_adds_chinese_display_type_without_changing_identity(self):
        message = ValidationMessage(
            "warning",
            "STRUT_ONE_END_NOT_CONNECTED",
            "S1 只有一端連接圍令。",
            "strut",
            ("H1",),
            ("S1",),
        )

        record = build_problem_records(
            _result(struts=(_strut("S1", "H1"),), messages=(message,))
        )[0]

        self.assertEqual(record.display_type, "端點連接問題")
        self.assertEqual(record.code, message.code)
        self.assertEqual(record.severity, message.severity)
        self.assertEqual(record.role, message.role)
        self.assertEqual(record.source_handles, message.source_handles)
        self.assertEqual(record.member_ids, message.member_ids)

    def test_diagnostic_code_inventory_has_one_explicit_description_source(self):
        categories = (
            PRESERVE_MESSAGE_CODES,
            FORMATTER_DESCRIPTION_CODES,
            FALLBACK_DESCRIPTION_CODES,
        )
        producer_codes = _producer_diagnostic_codes()

        self.assertEqual(producer_codes, DXF_REVIEW_DIAGNOSTIC_CODES)
        self.assertEqual(len(DXF_REVIEW_DIAGNOSTIC_CODES), 88)
        self.assertEqual(set().union(*categories), DXF_REVIEW_DIAGNOSTIC_CODES)
        for index, category in enumerate(categories):
            self.assertTrue(
                category.isdisjoint(set().union(*categories[index + 1 :])),
            )
        assert_problem_code_catalog_complete(producer_codes)
        with self.assertRaisesRegex(ValueError, "NEW_UNCLASSIFIED_DIAGNOSTIC"):
            assert_problem_code_catalog_complete(
                (*DXF_REVIEW_DIAGNOSTIC_CODES, "NEW_UNCLASSIFIED_DIAGNOSTIC")
            )

    def test_special_formatters_hide_internal_terms_and_keep_locations(self):
        fixtures = (
            (
                "WALER_CONTACT_FACE_UNRESOLVED",
                "已選定來源無法建立 provisional 交點。",
                "尚未確認正式接觸面",
            ),
            (
                "AMBIGUOUS_WALER_CONNECTION",
                "terminal identity 無法唯一決定。",
                "無法唯一確認正式連接",
            ),
            (
                "BRACE_RIGID_TRANSLATION_UNRESOLVED",
                "adjustment baseline 遺失（identity_invalid）。",
                "調整基準",
            ),
            (
                "WALER_CONTACT_FINALIZE_FAILED",
                "staged finalization 失敗：RuntimeError('boom')",
                "接觸位置無法確認",
            ),
        )
        forbidden = (
            "provisional",
            "identity",
            "baseline",
            "staged finalization",
            "RuntimeError",
        )

        for code, raw_message, expected in fixtures:
            with self.subTest(code=code):
                record = build_problem_records(
                    _result(
                        struts=(_strut("S1", "H1"),),
                        messages=(
                            ValidationMessage(
                                "error",
                                code,
                                raw_message,
                                "waler" if code.startswith("WALER_") else "brace",
                                ("H1",),
                                ("S1",),
                            ),
                        ),
                    )
                )[0]
                self.assertIn(expected, record.description)
                self.assertIn("S1", record.description)
                self.assertIn("H1", record.description)
                for token in forbidden:
                    self.assertNotIn(token, record.description)

    def test_overlap_formatter_keeps_measurements_and_formal_source_labels(self):
        message = ValidationMessage(
            "warning",
            "WALER_SOURCE_OVERLAP",
            (
                "圍令來源 232 與 4E4 的 source-supported provisional axes "
                "有重大共線重疊：有限重疊長度 1250.500 mm，"
                "占較短 provisional axis 82.5%。"
            ),
            "waler",
            ("232", "4E4"),
        )

        record = build_problem_records(
            _result(
                struts=(_strut("W6", "232"), _strut("W12", "4E4")),
                messages=(message,),
            )
        )[0]

        self.assertIn("W6（232）", record.description)
        self.assertIn("W12（4E4）", record.description)
        self.assertIn("1250.500 mm", record.description)
        self.assertIn("82.5%", record.description)
        self.assertNotIn("provisional", record.description)
        self.assertNotIn("source-supported", record.description)

    def test_known_and_unknown_fallback_hide_raw_diagnostic_details(self):
        messages = (
            ValidationMessage(
                "error",
                "BIM_JOIST_RECOGNITION_FAILED",
                "reason=internal_router_error RuntimeError('secret') traceback",
                "beam",
                ("J01",),
                ("BM2",),
            ),
            ValidationMessage(
                "warning",
                "NEW_DIAGNOSTIC_CODE",
                "reason=secret_token ValueError('secret') traceback",
                "brace",
                ("B01",),
                ("B7",),
            ),
        )

        records = build_problem_records(
            _result(
                struts=(_strut("BM2", "J01"), _strut("B7", "B01")),
                messages=messages,
            )
        )

        self.assertEqual(len(records), 2)
        for record in records:
            self.assertIn("系統無法完成這項", record.description)
            self.assertIn(record.member_ids[0], record.description)
            self.assertIn(record.source_handles[0], record.description)
            self.assertNotIn(record.code, record.description)
            self.assertNotIn("reason=", record.description)
            self.assertNotIn("Error", record.description)
            self.assertNotIn("traceback", record.description)
        self.assertEqual(records[0].display_type, "托梁檢核錯誤")
        self.assertEqual(records[1].display_type, "斜撐檢核警告")

    def test_missing_column_decision_stays_visible_without_repair_subject(self):
        result = _result(
            messages=(
                ValidationMessage(
                    "warning",
                    "COLUMN_ASSOCIATION_REQUIRES_REVIEW",
                    "C25 的來源已不在目前辨識結果，人工關聯需重新檢查。",
                    "column",
                    ("HC25",),
                ),
            ),
        )
        records = build_problem_records(result)
        items = build_review_items(result, records)

        self.assertTrue(any(
            record.code == "COLUMN_ASSOCIATION_REQUIRES_REVIEW"
            for record in records
        ))
        orphan = next(
            item
            for item in items
            if item.role == "column" and item.status == "unresolved"
        )
        self.assertIsNone(orphan.member_id)

        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = SimpleNamespace(world_result=result)
        dialog.review_item_by_key = {orphan.key: orphan}
        dialog.selected_review_item_key = orphan.key
        dialog.selection_state = SelectionState()
        self.assertEqual(dialog._selected_column_repair_subject_id(), "")

    def test_formal_member_without_problem_is_normal(self):
        item = build_review_items(_result(struts=(_strut("S1", "H1"),)))[0]

        self.assertEqual(item.key, "member:strut:S1")
        self.assertEqual(item.status, "recognized")
        self.assertEqual(item.highest_severity, "success")
        self.assertEqual(item.problems, ())

    def test_highest_severity_uses_critical_error_warning_order(self):
        member = _strut("S1", "H1")
        records = (
            _problem("warning", "WARN", handles=("H1",), member_ids=("S1",)),
            _problem("error", "ERROR", handles=("H1",), member_ids=("S1",)),
            _problem("critical", "CRITICAL", handles=("H1",), member_ids=("S1",)),
        )

        item = build_review_items(_result(struts=(member,)), records)[0]

        self.assertEqual(item.highest_severity, "critical")
        self.assertEqual(item.problem_count, 3)

    def test_explicit_shared_problem_is_same_object_on_both_members(self):
        first = _strut("S1", "H1")
        second = _strut("S2", "H2")
        shared = _problem(
            "error",
            "SHARED",
            handles=("H1", "H2"),
            member_ids=("S1", "S2"),
        )

        items = build_review_items(_result(struts=(first, second)), (shared,))

        self.assertIs(items[0].problems[0], shared)
        self.assertIs(items[1].problems[0], shared)

    def test_problem_records_use_explicit_ids_then_strict_unique_fallback(self):
        first = _strut("S1", "H1")
        second = _strut("S2", "H2")
        result = _result(
            struts=(first, second),
            messages=(
                ValidationMessage(
                    "error",
                    "EXPLICIT",
                    "shared",
                    "strut",
                    ("H1", "H2"),
                    ("S1", "S2"),
                ),
                ValidationMessage(
                    "warning",
                    "UNIQUE",
                    "unique",
                    "strut",
                    ("H1",),
                ),
                ValidationMessage(
                    "error",
                    "AMBIGUOUS",
                    "ambiguous",
                    "strut",
                    ("H1", "H2"),
                ),
            ),
        )

        records = {item.code: item for item in build_problem_records(result)}

        self.assertEqual(records["EXPLICIT"].member_ids, ("S1", "S2"))
        self.assertEqual(records["UNIQUE"].member_ids, ("S1",))
        self.assertEqual(records["AMBIGUOUS"].member_ids, ())

    def test_problem_description_replaces_only_structured_source_occurrence(self):
        owner = _strut("W6", "232")
        unrelated_owner = _strut("W12", "4E4")
        message = ValidationMessage(
            "warning",
            "WALER_ENVELOPE_UNRESOLVED",
            (
                "圍令來源 232；長度 232 mm；角度 232°；比例 232%；"
                "小數 232.5；座標 (232, 400)；未列來源 4E4。"
            ),
            "strut",
            ("232",),
        )

        record = build_problem_records(
            _result(struts=(owner, unrelated_owner), messages=(message,))
        )[0]

        self.assertIn("圍令來源 W6（232）", record.description)
        self.assertIn("長度 232 mm", record.description)
        self.assertIn("角度 232°", record.description)
        self.assertIn("比例 232%", record.description)
        self.assertIn("小數 232.5", record.description)
        self.assertIn("座標 (232, 400)", record.description)
        self.assertIn("未列來源 4E4", record.description)
        self.assertNotIn("W12（4E4）", record.description)
        self.assertEqual(record.source_handles, message.source_handles)
        self.assertEqual(record.severity, message.severity)
        self.assertEqual(record.code, message.code)
        self.assertEqual(record.role, message.role)

    def test_problem_description_accepts_explicit_competing_identities(self):
        message = SimpleNamespace(
            severity="error",
            code="WALER_ENVELOPE_AMBIGUOUS",
            message="競爭來源 A 與 B。",
            role="strut",
            source_handles=("ROOT",),
            member_ids=(),
            competing_source_identities=(("A",), ("B",)),
        )
        result = _result(
            struts=(
                _strut("W2", "A"),
                _strut("W10", "B"),
            ),
            messages=(message,),
        )

        record = build_problem_records(result)[0]

        self.assertEqual(
            record.description,
            "競爭來源 W2（A） 與 W10（B）。",
        )
        self.assertEqual(record.source_handles, ("ROOT",))

    def test_problem_description_naturally_sorts_multiple_owners(self):
        message = ValidationMessage(
            "error",
            "DUPLICATE_ENGINEERING_COMPONENT",
            "來源 SHARED。",
            "strut",
            ("SHARED",),
        )
        w10 = _strut("W10", "SHARED")
        w2 = _strut("W2", "SHARED")

        forward = build_problem_records(
            _result(struts=(w10, w2), messages=(message,))
        )[0]
        reverse = build_problem_records(
            _result(struts=(w2, w10), messages=(message,))
        )[0]

        expected = "來源 W2（SHARED）／W10（SHARED）。"
        self.assertEqual(forward.description, expected)
        self.assertEqual(reverse.description, expected)

    def test_problem_description_groups_multiple_handles_for_one_member(self):
        owner = replace(
            _strut("W6", "232"),
            source_handles=("232", "4E4"),
        )
        message = ValidationMessage(
            "warning",
            "WALER_ENVELOPE_UNRESOLVED",
            "圍令來源 232 / 4E4 重疊。",
            "strut",
            ("232", "4E4"),
        )

        record = build_problem_records(
            _result(struts=(owner,), messages=(message,))
        )[0]

        self.assertEqual(record.description, "圍令來源 W6（232／4E4） 重疊。")
        self.assertEqual(record.description.count("W6"), 1)

    def test_unresolved_and_excluded_sources_keep_raw_handle(self):
        message = ValidationMessage(
            "error",
            "BEAM_RECOGNITION_FAILED",
            "來源 FB7 無法辨識。",
            "beam",
            ("FB7",),
        )
        unresolved_result = _result(messages=(message,))
        excluded_result = _result(
            messages=(message,),
            excluded_sources=(
                ExcludedSource(
                    role="beam",
                    source_handles=("FB7",),
                    display_id_when_excluded="待修-FB7",
                ),
            ),
        )

        unresolved_record = build_problem_records(unresolved_result)[0]
        excluded_record = build_problem_records(excluded_result)[0]
        unresolved_items = build_review_items(
            unresolved_result,
            (unresolved_record,),
        )
        excluded_items = build_review_items(
            excluded_result,
            (excluded_record,),
        )

        self.assertIn("來源 FB7", unresolved_record.description)
        self.assertIn("來源 FB7", excluded_record.description)
        self.assertNotIn("BEAM_RECOGNITION_FAILED", unresolved_record.description)
        self.assertIn("待修-FB7", {item.display_id for item in unresolved_items})
        self.assertIn("已排除-FB7", {item.display_id for item in excluded_items})

    def test_multiple_models_diagnostic_uses_its_structured_source_handle(self):
        message = ValidationMessage(
            "critical",
            "MULTIPLE_MODELS_FROM_ONE_SOURCE",
            "來源 ROOT 產生 2 個工程模型；其他文字 MISSING 保持原樣。",
            "strut",
            ("ROOT",),
        )

        record = build_problem_records(
            _result(struts=(_strut("S3", "ROOT"),), messages=(message,))
        )[0]

        self.assertEqual(
            record.description,
            "來源 S3（ROOT） 產生 2 個工程模型；其他文字 MISSING 保持原樣。",
        )

    def test_same_source_problem_set_builds_one_unresolved_item(self):
        messages = (
            ValidationMessage(
                "error",
                "BEAM_CENTERLINE_FAILED",
                "centerline",
                "beam",
                ("6EF",),
            ),
            ValidationMessage(
                "error",
                "BEAM_RECOGNITION_FAILED",
                "recognition",
                "beam",
                ("6EF",),
            ),
        )
        result = _result(
            messages=messages,
            entity_debug=(
                EntityDebugInfo("beam", "BEAM", "LINE", "6EF", "read"),
            ),
            source_geometry=(
                SourceGeometry(
                    "beam",
                    "6EF",
                    ((0.0, 0.0), (100.0, 0.0)),
                    False,
                    "BEAM",
                    "LINE",
                ),
            ),
        )

        items = build_review_items(result)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].display_id, "待修-6EF")
        self.assertEqual(items[0].status, "unresolved")
        self.assertEqual(items[0].problem_count, 2)
        self.assertEqual(items[0].source_layers, ("BEAM",))
        self.assertEqual(items[0].source_entity_types, ("LINE",))

    def test_unresolved_identity_uses_role_and_complete_handle_set(self):
        records = (
            _problem("error", "A", role="beam", handles=("H1", "H2")),
            _problem("warning", "B", role="beam", handles=("H1",)),
            _problem("error", "C", role="column", handles=("H1", "H2")),
        )

        items = build_review_items(_result(), records)

        self.assertEqual(len(items), 3)
        self.assertEqual(len({item.key for item in items}), 3)

    def test_ambiguous_formal_source_stays_only_in_global_problem_list(self):
        first = _strut("S1", "SHARED")
        second = _strut("S2", "SHARED")
        result = _result(
            struts=(first, second),
            messages=(
                ValidationMessage(
                    "error",
                    "AMBIGUOUS",
                    "cannot safely assign",
                    "strut",
                    ("SHARED",),
                ),
            ),
        )

        records = build_problem_records(result)
        items = build_review_items(result, records)

        self.assertEqual(records[0].member_ids, ())
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item.status == "recognized" for item in items))
        self.assertTrue(all(not item.problems for item in items))

    def test_global_problem_does_not_create_fake_review_item(self):
        result = _result(
            messages=(
                ValidationMessage(
                    "critical",
                    "STRUT_RECOGNITION_FAILED",
                    "no struts",
                    "strut",
                ),
            )
        )

        self.assertEqual(build_review_items(result), ())
        self.assertEqual(len(build_problem_records(result)), 1)

    def test_guidance_is_deduplicated_and_respects_item_capability(self):
        formal = ReviewItem(
            "member:strut:S1",
            "S1",
            "strut",
            "recognized",
            "S1",
            ("H1",),
            ("STRUT",),
            ("LINE",),
            "auto",
            (
                _problem("error", "STRUT_NOT_CONNECTED", member_ids=("S1",)),
                _problem(
                    "error",
                    "STRUT_ONE_END_NOT_CONNECTED",
                    member_ids=("S1",),
                ),
            ),
            "error",
        )
        unresolved = ReviewItem(
            "source:beam:6EF",
            "待修-6EF",
            "beam",
            "unresolved",
            None,
            ("6EF",),
            ("BEAM",),
            ("LINE",),
            "",
            (_problem("error", "BEAM_RECOGNITION_FAILED", role="beam"),),
            "error",
        )

        formal_guidance = review_item_guidance(formal)
        unresolved_guidance = review_item_guidance(unresolved)

        self.assertEqual(len(formal_guidance), 1)
        self.assertIn("候選點區", formal_guidance[0])
        self.assertIn("從 CAD 指定工程線", formal_guidance[0])
        self.assertEqual(len(unresolved_guidance), 1)
        self.assertIn("圖層 ✓", unresolved_guidance[0])
        self.assertIn("幾何修正工具不適用", unresolved_guidance[0])

    def test_overlap_guidance_uses_user_facing_source_wording(self):
        item = ReviewItem(
            "member:waler:W1",
            "W1",
            "waler",
            "recognized",
            "W1",
            ("H1",),
            ("WALER",),
            ("LINE",),
            "auto",
            (
                _problem(
                    "error",
                    "WALER_OVERLAP_COMPETITION",
                    role="waler",
                    handles=("H1",),
                    member_ids=("W1",),
                ),
            ),
            "error",
        )

        guidance = review_item_guidance(item)[0]

        self.assertIn("參與辨識的來源", guidance)
        self.assertNotIn("active sources", guidance)
        self.assertNotIn("winner", guidance)

    def test_rebuilding_projection_removes_resolved_source_item(self):
        failed = _result(
            messages=(
                ValidationMessage(
                    "error",
                    "STRUT_RECOGNITION_FAILED",
                    "failed",
                    "strut",
                    ("H1",),
                ),
            )
        )
        resolved = _result(struts=(_strut("S1", "H1"),))

        self.assertEqual(build_review_items(failed)[0].status, "unresolved")
        resolved_items = build_review_items(resolved)
        self.assertEqual(len(resolved_items), 1)
        self.assertEqual(resolved_items[0].display_id, "S1")


class ReviewPresentationTests(unittest.TestCase):
    @staticmethod
    def _error_hit_dialog(
        review_items,
        source_geometry,
        *,
        show_source=True,
        focus_handles=(),
    ):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = _result(source_geometry=source_geometry)
        dialog.review_items = tuple(review_items)
        dialog.preview_viewport = CADViewport(
            view_bounds=(-10.0, 10.0, -10.0, 10.0),
            canvas_width=100.0,
            canvas_height=100.0,
        )
        dialog.show_source_var = _Variable(show_source)
        dialog.show_auxiliary_var = _Variable(True)
        dialog.focus_handles = set(focus_handles)
        dialog._preview_render_generation = 3
        dialog.canvas_error_source_hit_lines = []
        dialog._error_source_hit_index_stamp = None
        return dialog

    def test_error_hit_index_tracks_immediate_pan_and_zoom(self):
        item = _unresolved_review_item()
        geometry = SourceGeometry(
            "beam",
            "6EF",
            ((5.0, 0.0), (5.5, 0.0)),
            False,
            "BEAM",
            "LINE",
        )
        dialog = self._error_hit_dialog((item,), (geometry,))

        self.assertEqual(dialog._error_source_hits((77.0, 50.0)), (item.key,))
        initial_stamp = dialog._error_source_hit_index_stamp

        dialog.preview_view_bounds = (0.0, 20.0, -10.0, 10.0)

        self.assertEqual(dialog._error_source_hits((26.0, 50.0)), (item.key,))
        self.assertEqual(dialog._error_source_hits((77.0, 50.0)), ())
        self.assertNotEqual(dialog._error_source_hit_index_stamp, initial_stamp)

        dialog.preview_view_bounds = (-10.0, 10.0, -10.0, 10.0)
        self.assertEqual(dialog._error_source_hits((77.0, 50.0)), (item.key,))
        dialog.preview_viewport.zoom_at_screen((100.0, 50.0), 0.5)

        self.assertEqual(dialog._error_source_hits((52.0, 50.0)), (item.key,))
        self.assertEqual(dialog._error_source_hits((77.0, 50.0)), ())

    def test_error_hit_index_uses_actual_render_visibility(self):
        item = _unresolved_review_item()
        geometry = SourceGeometry(
            "beam",
            "6EF",
            ((0.0, 0.0), (10.0, 0.0)),
            False,
            "BEAM",
            "LINE",
        )
        dialog = self._error_hit_dialog(
            (item,),
            (geometry,),
            show_source=False,
            focus_handles=("6EF",),
        )

        self.assertEqual(dialog._error_source_hits((75.0, 50.0)), (item.key,))

        dialog.focus_handles.clear()
        self.assertEqual(dialog._error_source_hits((75.0, 50.0)), ())

        dialog.show_source_var.set(True)
        self.assertEqual(dialog._error_source_hits((75.0, 50.0)), (item.key,))

    def test_error_hit_index_refreshes_for_review_result_and_render_generation(self):
        item = _unresolved_review_item()
        geometry = SourceGeometry(
            "beam",
            "6EF",
            ((0.0, 0.0), (10.0, 0.0)),
            False,
        )
        dialog = self._error_hit_dialog((item,), (geometry,))
        self.assertEqual(dialog._error_source_hits((75.0, 50.0)), (item.key,))
        self.assertEqual(
            dialog._error_source_hit_index_stamp.render_generation,
            3,
        )
        initial_stamp = dialog._error_source_hit_index_stamp

        dialog.review_items = (
            _unresolved_review_item(severity="warning"),
        )
        self.assertEqual(dialog._error_source_hits((75.0, 50.0)), ())

        dialog.review_items = (item,)
        dialog.result = _result(
            source_geometry=(
                SourceGeometry(
                    "beam",
                    "6EF",
                    ((0.0, 5.0), (10.0, 5.0)),
                    False,
                ),
            )
        )
        self.assertEqual(dialog._error_source_hits((75.0, 50.0)), ())
        self.assertEqual(dialog._error_source_hits((75.0, 25.0)), (item.key,))

        dialog._preview_render_generation += 1
        self.assertEqual(dialog._error_source_hits((75.0, 25.0)), (item.key,))
        self.assertNotEqual(dialog._error_source_hit_index_stamp, initial_stamp)

    def test_error_hit_index_filters_review_state_and_deduplicates_keys(self):
        first = ReviewItem(
            "source:beam:first",
            "first",
            "beam",
            "unresolved",
            None,
            ("H1", "H2"),
            ("BEAM",),
            ("LINE",),
            "",
            (_problem("error", "FAILED", role="beam"),),
            "error",
        )
        second = _unresolved_review_item("source:beam:second", "H1")
        ignored = (
            _unresolved_review_item(
                "source:beam:warning", "H1", severity="warning"
            ),
            _unresolved_review_item(
                "source:beam:info", "H1", severity="info"
            ),
            _unresolved_review_item(
                "source:beam:excluded", "H1", status="excluded"
            ),
            _unresolved_review_item(
                "source:beam:recognized", "H1", status="recognized"
            ),
        )
        geometries = tuple(
            SourceGeometry(
                "beam",
                handle,
                ((0.0, 0.0), (10.0, 0.0)),
                False,
                "BEAM",
                "LINE",
            )
            for handle in ("H1", "H2")
        )
        dialog = self._error_hit_dialog(
            (first, second, *ignored),
            geometries,
        )

        self.assertEqual(
            dialog._error_source_hits((75.0, 50.0)),
            (first.key, second.key),
        )

    def test_step3_text_keeps_severity_manual_marker_and_problem_count(self):
        item = ReviewItem(
            "member:strut:S1",
            "S1",
            "strut",
            "recognized",
            "S1",
            ("H1",),
            ("STRUT",),
            ("LINE",),
            "manual_candidate_points",
            (_problem("error", "ERROR", member_ids=("S1",)),),
            "error",
        )

        self.assertEqual(DXFImportDialog._review_item_text(item), "✗ S1 ＊ (1)")

    def test_group_summary_counts_affected_items_not_problem_records(self):
        error = ReviewItem(
            "member:strut:S1",
            "S1",
            "strut",
            "recognized",
            "S1",
            (),
            (),
            (),
            "auto",
            (_problem("error", "E1"), _problem("error", "E2")),
            "error",
        )
        warning = ReviewItem(
            "member:strut:S2",
            "S2",
            "strut",
            "recognized",
            "S2",
            (),
            (),
            (),
            "auto",
            (_problem("warning", "W1"),),
            "warning",
        )

        text = DXFImportDialog._review_group_text("支撐", (error, warning))

        self.assertEqual(text, "支撐（2）｜✗1 ⚠1")

    def test_member_tree_contains_formal_and_unresolved_review_items(self):
        formal = build_review_items(
            _result(struts=(_strut("S1", "H1", selection_source="manual_candidate_points"),))
        )[0]
        unresolved = ReviewItem(
            "source:beam:6EF",
            "待修-6EF",
            "beam",
            "unresolved",
            None,
            ("6EF",),
            ("BEAM",),
            ("LINE",),
            "",
            (_problem("error", "FAILED", role="beam", handles=("6EF",)),),
            "error",
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.member_tree = _ReviewTree()
        dialog.member_by_tree_iid = {}
        dialog.review_item_by_tree_iid = {}
        dialog.review_items = (formal, unresolved)
        dialog.selected_review_item_key = ""
        dialog.result = object()
        dialog.review_workflow = SimpleNamespace(
            is_review_item_confirmed=lambda _item: False,
        )
        dialog._updating_member_tree = False
        dialog.member_tree_selection = SimpleNamespace(select=lambda _iid: None)

        dialog._refresh_member_tree()

        texts = {row["text"] for row in dialog.member_tree.rows.values()}
        self.assertIn("支撐（1）", texts)
        self.assertIn("S1 ＊", texts)
        self.assertIn("托梁（1）｜✗1", texts)
        self.assertIn("✗ 待修-6EF (1)", texts)

    def test_unresolved_selection_focuses_handles_without_fake_member(self):
        item = ReviewItem(
            "source:beam:6EF",
            "待修-6EF",
            "beam",
            "unresolved",
            None,
            ("6EF",),
            ("BEAM",),
            ("LINE",),
            "",
            (_problem("error", "FAILED", role="beam", handles=("6EF",)),),
            "error",
        )
        render_requests = []
        panel_updates = []
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.selected_problem = object()
        dialog.selected_review_item_key = ""
        dialog.focus_member_ids = {"S1"}
        dialog.focus_handles = set()
        dialog.selection_state = SelectionState(selected_component_id="S1")
        dialog.selection_controller = SimpleNamespace(state=dialog.selection_state)
        dialog.selected_only_var = _Variable(False)
        dialog.candidate_action_status_var = _Variable("")
        dialog._update_selected_member_panel = lambda: panel_updates.append(True)
        dialog.preview_viewport = CADViewport()
        dialog.preview_fit_all = True
        dialog._open_preview_window = lambda: None
        dialog.render_scheduler = SimpleNamespace(request=render_requests.append)

        dialog._select_unresolved_review_item(item)

        self.assertEqual(dialog.selected_member_id, "")
        self.assertEqual(dialog.selected_review_item_key, item.key)
        self.assertEqual(dialog.focus_member_ids, set())
        self.assertEqual(dialog.focus_handles, {"6EF"})
        self.assertEqual(panel_updates, [True])
        self.assertEqual(render_requests, [RenderDirty.FULL_SCENE])

    def test_canvas_error_selection_runs_once_and_tree_event_is_guarded(self):
        item = _unresolved_review_item()
        render_requests = []
        panel_updates = []
        idle_callbacks = []
        tree = _ReviewTree()
        tree.rows["review_0"] = {}
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog._updating_member_tree = False
        dialog.member_tree = tree
        dialog.member_tree_selection = TreeSelectionSynchronizer(
            tree,
            idle_callbacks.append,
        )
        dialog.review_item_by_tree_iid = {"review_0": item.key}
        dialog.review_item_by_key = {item.key: item}
        dialog.member_by_tree_iid = {}
        dialog.selected_problem = object()
        dialog.selected_review_item_key = ""
        dialog.focus_member_ids = {"S1"}
        dialog.focus_handles = set()
        dialog.selection_state = SelectionState()
        dialog.selection_controller = SimpleNamespace(
            state=dialog.selection_state,
        )
        dialog.selected_only_var = _Variable(False)
        dialog.candidate_action_status_var = _Variable("")
        dialog._update_selected_member_panel = lambda: panel_updates.append(True)
        dialog.preview_viewport = CADViewport()
        dialog.preview_fit_all = True
        dialog._open_preview_window = lambda: None
        dialog.render_scheduler = SimpleNamespace(request=render_requests.append)
        dialog.canvas_candidate_hit_points = []
        dialog.canvas_member_hit_lines = []
        dialog._pending_endpoint_hits = lambda _point: ()
        dialog._error_source_hits = lambda _point: (item.key,)
        dialog.result = _result(
            struts=(_strut("S1", "H1"),),
            messages=(
                ValidationMessage(
                    "error",
                    "FAILED",
                    "kept",
                    "beam",
                    ("6EF",),
                ),
            ),
            source_geometry=(
                SourceGeometry(
                    "beam",
                    "6EF",
                    ((0.0, 0.0), (10.0, 0.0)),
                    False,
                ),
            ),
        )
        dialog.review_items = (item,)
        workflow_state = SimpleNamespace(
            confirmations=("kept",),
            exclusions=("kept",),
            repairs=("kept",),
            persisted_review_state={"kept": True},
            dirty=False,
        )
        dialog.review_workflow = workflow_state
        dialog.project_rows = ({"kept": True},)
        dialog.solver_projection = ("kept",)
        protected_state = {
            "result": dialog.result,
            "review_items": dialog.review_items,
            "workflow": vars(workflow_state).copy(),
            "project_rows": dialog.project_rows,
            "solver_projection": dialog.solver_projection,
        }
        tree.on_selection_set = lambda: dialog._on_member_selected()

        dialog._on_canvas_click(SimpleNamespace(x=10, y=20))

        self.assertEqual(dialog.selected_review_item_key, item.key)
        self.assertEqual(dialog.selection_state.selection_source, "canvas")
        self.assertEqual(panel_updates, [True])
        self.assertEqual(render_requests, [RenderDirty.FULL_SCENE])
        self.assertEqual(tree.selection(), ("review_0",))
        self.assertTrue(dialog.member_tree_selection.syncing)
        self.assertIs(dialog.result, protected_state["result"])
        self.assertIs(dialog.review_items, protected_state["review_items"])
        self.assertEqual(vars(workflow_state), protected_state["workflow"])
        self.assertIs(dialog.project_rows, protected_state["project_rows"])
        self.assertIs(
            dialog.solver_projection,
            protected_state["solver_projection"],
        )

    def test_synthetic_preview_geometry_selects_unresolved_error_end_to_end(self):
        item = _unresolved_review_item()
        geometry = SourceGeometry(
            "beam",
            "6EF",
            ((0.0, 0.0), (10.0, 0.0)),
            False,
            "BEAM",
            "LINE",
        )
        dialog = self._error_hit_dialog((item,), (geometry,))
        tree = _ReviewTree()
        tree.rows["review_0"] = {}
        render_requests = []
        detail_updates = []
        dialog._updating_member_tree = False
        dialog.member_tree = tree
        dialog.member_tree_selection = TreeSelectionSynchronizer(
            tree,
            lambda _callback: None,
        )
        dialog.review_item_by_tree_iid = {"review_0": item.key}
        dialog.review_item_by_key = {item.key: item}
        dialog.member_by_tree_iid = {}
        dialog.selected_problem = None
        dialog.selected_review_item_key = ""
        dialog.focus_member_ids = set()
        dialog.selection_state = SelectionState()
        dialog.selection_controller = SimpleNamespace(
            state=dialog.selection_state,
        )
        dialog.selected_only_var = _Variable(False)
        dialog.candidate_action_status_var = _Variable("")
        dialog._update_selected_member_panel = (
            lambda: detail_updates.append(item.key)
        )
        dialog.preview_fit_all = False
        dialog._open_preview_window = lambda: None
        dialog.render_scheduler = SimpleNamespace(request=render_requests.append)
        dialog.canvas_candidate_hit_points = []
        dialog.canvas_member_hit_lines = []
        dialog._pending_endpoint_hits = lambda _point: ()

        dialog._on_canvas_click(SimpleNamespace(x=75, y=50))

        self.assertEqual(dialog.selected_review_item_key, item.key)
        self.assertEqual(dialog.focus_handles, {"6EF"})
        self.assertEqual(tree.selection(), ("review_0",))
        self.assertEqual(detail_updates, [item.key])
        self.assertEqual(render_requests, [RenderDirty.FULL_SCENE])

    def test_ambiguous_canvas_error_hit_preserves_selection_and_prompt(self):
        status = _Variable("")
        protected_result = _result(
            struts=(_strut("S1", "H1"),),
            messages=(ValidationMessage("error", "KEPT", "kept"),),
        )
        protected_items = (_unresolved_review_item(),)
        workflow_state = SimpleNamespace(
            confirmations=("kept",),
            exclusions=("kept",),
            repairs=("kept",),
            persisted_review_state={"kept": True},
            dirty=False,
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = protected_result
        dialog.review_items = protected_items
        dialog.review_workflow = workflow_state
        dialog.selection_state = SelectionState()
        dialog.selected_review_item_key = "previous"
        dialog.candidate_action_status_var = status
        dialog.canvas_candidate_hit_points = []
        dialog.canvas_member_hit_lines = []
        dialog._updating_member_tree = False
        dialog.member_tree_selection = SimpleNamespace(syncing=True)
        dialog._pending_endpoint_hits = lambda _point: ()
        dialog._error_source_hits = lambda _point: ("first", "second")

        dialog._on_canvas_click(SimpleNamespace(x=10, y=20))
        dialog._on_member_selected()

        self.assertEqual(dialog.selected_review_item_key, "previous")
        self.assertIn("重疊多個錯誤元件", status.get())
        self.assertIs(dialog.result, protected_result)
        self.assertIs(dialog.review_items, protected_items)
        self.assertEqual(workflow_state.dirty, False)
        self.assertEqual(workflow_state.confirmations, ("kept",))
        self.assertEqual(workflow_state.exclusions, ("kept",))
        self.assertEqual(workflow_state.repairs, ("kept",))

    def test_canvas_error_selection_follows_existing_hit_priority(self):
        canvas_event = SimpleNamespace(x=10, y=20)

        endpoint_dialog = DXFImportDialog.__new__(DXFImportDialog)
        endpoint_dialog.selection_state = SelectionState()
        endpoint_dialog._pending_endpoint_hits = lambda _point: ("start",)
        endpoint_dialog._begin_candidate_pick = Mock()
        endpoint_dialog._error_source_hits = Mock(
            side_effect=AssertionError("error hit must not run")
        )
        endpoint_dialog._on_canvas_click(canvas_event)
        endpoint_dialog._begin_candidate_pick.assert_called_once_with(
            "pick_start"
        )

        candidate_dialog = DXFImportDialog.__new__(DXFImportDialog)
        candidate_dialog.selection_state = SelectionState()
        candidate_dialog._pending_endpoint_hits = lambda _point: ()
        candidate_dialog.canvas_candidate_hit_points = [
            ("P1", (10.0, 20.0))
        ]
        candidate_dialog._select_candidate_point = Mock()
        candidate_dialog._error_source_hits = Mock(
            side_effect=AssertionError("error hit must not run")
        )
        candidate_dialog._on_canvas_click(canvas_event)
        candidate_dialog._select_candidate_point.assert_called_once_with(
            "P1",
            source="canvas",
        )

        member_dialog = DXFImportDialog.__new__(DXFImportDialog)
        member_dialog.selection_state = SelectionState()
        member_dialog._pending_endpoint_hits = lambda _point: ()
        member_dialog.canvas_candidate_hit_points = []
        member_dialog.canvas_member_hit_lines = [
            ("S1", (0.0, 20.0), (20.0, 20.0))
        ]
        member_dialog._select_member = Mock()
        member_dialog._error_source_hits = Mock(
            side_effect=AssertionError("error hit must not run")
        )
        member_dialog._on_canvas_click(canvas_event)
        member_dialog._select_member.assert_called_once_with(
            "S1",
            refit=False,
            clear_problem=True,
            source="canvas",
        )

        edit_dialog = DXFImportDialog.__new__(DXFImportDialog)
        edit_dialog.selection_state = SelectionState(mode="pick_start")
        edit_dialog.canvas_candidate_hit_points = []
        edit_dialog.canvas_member_hit_lines = []
        edit_dialog.candidate_action_status_var = _Variable("")
        edit_dialog._error_source_hits = Mock(
            side_effect=AssertionError("error hit must not run")
        )
        edit_dialog._on_canvas_click(canvas_event)
        self.assertTrue(edit_dialog.candidate_action_status_var.get())

    def test_error_hover_uses_hand_cursor_without_selecting_review_item(self):
        configured = []
        hover_calls = []
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.preview_viewport = CADViewport(
            view_bounds=(-10.0, 10.0, -10.0, 10.0),
            canvas_width=100.0,
            canvas_height=100.0,
        )
        dialog.preview_cursor_var = _Variable("")
        dialog.canvas_candidate_hit_points = []
        dialog.canvas_member_hit_lines = []
        dialog.selection_state = SelectionState()
        dialog.selected_review_item_key = "previous"
        protected_result = _result(
            messages=(ValidationMessage("error", "KEPT", "kept"),),
        )
        protected_items = (_unresolved_review_item(),)
        workflow_state = SimpleNamespace(dirty=False, confirmations=("kept",))
        dialog.result = protected_result
        dialog.review_items = protected_items
        dialog.review_workflow = workflow_state
        dialog._pending_endpoint_hits = lambda _point: ()
        dialog._error_source_hits = lambda _point: ("source:beam:6EF",)
        dialog.canvas = SimpleNamespace(
            configure=lambda **options: configured.append(options)
        )
        dialog.tk = SimpleNamespace(TclError=Exception)
        dialog.selection_controller = SimpleNamespace(
            set_hovered_candidate=lambda value: hover_calls.append(
                ("candidate", value)
            ),
            set_hovered_component=lambda value: hover_calls.append(
                ("component", value)
            ),
        )

        dialog._on_canvas_motion(SimpleNamespace(x=50, y=50))

        self.assertEqual(configured[-1]["cursor"], "hand2")
        self.assertEqual(dialog.selected_review_item_key, "previous")
        self.assertEqual(dialog.selection_state, SelectionState())
        self.assertEqual(
            hover_calls,
            [("candidate", ""), ("component", "")],
        )

        dialog._error_source_hits = lambda _point: (
            "source:beam:first",
            "source:beam:second",
        )
        dialog._on_canvas_motion(SimpleNamespace(x=50, y=50))

        self.assertEqual(configured[-1]["cursor"], "crosshair")
        self.assertEqual(dialog.selected_review_item_key, "previous")
        self.assertIs(dialog.result, protected_result)
        self.assertIs(dialog.review_items, protected_items)
        self.assertEqual(vars(workflow_state), {
            "dirty": False,
            "confirmations": ("kept",),
        })

    def test_step4_and_step7_use_shared_problem_focus_helper(self):
        record = _problem("error", "FAILED", handles=("6EF",))
        focused = []
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.problem_tree = _ReviewTree()
        dialog.problem_tree._selection = ("problem_0",)
        dialog.problem_record_by_iid = {"problem_0": record}
        dialog.detail_problem_tree = _ReviewTree()
        dialog.detail_problem_tree._selection = ("detail_0",)
        dialog.detail_problem_record_by_iid = {"detail_0": record}
        dialog.selected_only_var = _Variable(False)
        dialog._focus_problem_record = focused.append

        dialog._on_problem_selected()
        dialog._on_detail_problem_activated()

        self.assertEqual(focused, [record, record])

    def test_step4_and_step7_render_the_same_problem_record_description(self):
        description = "圍令來源 W6（232） 與 W12（4E4） 重疊。"
        record = ProblemRecord(
            "error",
            "WALER_OVERLAP_COMPETITION",
            "W6, W12",
            description,
            "waler",
            ("232", "4E4"),
            ("W6", "W12"),
            "圍令來源重疊",
        )
        item = ReviewItem(
            "member:waler:W6",
            "W6",
            "waler",
            "recognized",
            "W6",
            ("232",),
            ("WALER",),
            ("LINE",),
            "auto",
            (record,),
            "error",
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.problem_tree = _ReviewTree()
        dialog.problem_records = (record,)
        dialog.problem_record_by_iid = {}
        dialog.problem_filter_var = _Variable("all")
        dialog.selected_only_var = _Variable(False)
        dialog.selected_problem = None
        dialog._update_all_problems_header = lambda: None
        dialog.detail_problem_tree = _ReviewTree()
        dialog.detail_problem_record_by_iid = {}
        dialog.detail_problem_empty_var = _Variable("")
        dialog.detail_guidance_var = _Variable("")
        dialog._update_review_confirmation_action_state = lambda _item: None
        dialog._update_source_exclusion_action_state = lambda _item: None

        dialog._refresh_problem_tree()
        dialog._update_review_issue_panel(item)

        self.assertEqual(
            dialog.problem_tree.rows["problem_0"]["values"][-1],
            description,
        )
        self.assertEqual(
            dialog.detail_problem_tree.rows["detail_problem_0"]["values"][-1],
            description,
        )
        self.assertEqual(
            dialog.problem_tree.rows["problem_0"]["values"][1],
            "圍令來源重疊",
        )
        self.assertEqual(
            dialog.detail_problem_tree.rows["detail_problem_0"]["values"][1],
            "圍令來源重疊",
        )
        self.assertNotIn(
            "WALER_OVERLAP_COMPETITION",
            dialog.problem_tree.rows["problem_0"]["values"],
        )

    def test_unresolved_issue_level_is_available_for_preview_overlay(self):
        item = ReviewItem(
            "source:beam:6EF",
            "待修-6EF",
            "beam",
            "unresolved",
            None,
            ("6EF",),
            (),
            (),
            "",
            (_problem("warning", "WARN", handles=("6EF",)),),
            "warning",
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_items = (item,)

        self.assertEqual(
            dialog._unresolved_source_issue_levels(),
            {"6EF": "warning"},
        )

    def test_step4_normal_item_explicitly_reports_validation_pass(self):
        item = ReviewItem(
            "member:strut:S1",
            "S1",
            "strut",
            "recognized",
            "S1",
            ("H1",),
            ("STRUT",),
            ("LINE",),
            "auto",
            (),
            "success",
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.detail_problem_tree = _ReviewTree()
        dialog.detail_problem_record_by_iid = {}
        dialog.detail_problem_empty_var = _Variable("")
        dialog.detail_guidance_var = _Variable("")

        dialog._update_review_issue_panel(item)

        self.assertEqual(dialog.detail_problem_tree.rows, {})
        self.assertEqual(
            dialog.detail_problem_empty_var.get(),
            "✓ 此構件目前沒有檢核問題",
        )
        self.assertEqual(
            dialog.detail_guidance_var.get(),
            "目前不需要額外處理。",
        )


if __name__ == "__main__":
    unittest.main()
