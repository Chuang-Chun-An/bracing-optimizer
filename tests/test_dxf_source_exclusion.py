import copy
import hashlib
import math
import shutil
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import ezdxf

from dxf_import.candidate_points import (
    add_cad_candidate_points,
    apply_candidate_point_selection,
    set_cad_engineering_line,
)
from dxf_import.dialog import DXFImportDialog
from dxf_import.importer import DXFImporter, Y29_LAYER_MAPPING
from dxf_import.material_recognition import set_member_material_spec
from dxf_import.models import (
    Beam,
    CoordinateSystem,
    DXFImportError,
    DXFImportResult,
    ExcludedSource,
    ReviewItem,
    SelectionState,
    SourceManualOverride,
    Waler,
    apply_coordinate_system,
)
from dxf_import.preview import PreviewRenderer, PreviewScene, RenderDirty
from dxf_import.review_workflow import (
    DXFReviewWorkflow,
    PendingSourceExclusionDraft,
    ReviewMutationEffects,
    SourceExclusionPlan,
)
from dxf_import.source_exclusion import (
    ManualReplayReport,
    canonical_source_identity,
    capture_manual_overrides,
    excluded_source_from_review_item,
    exclusions_from_review_state,
    manual_overrides_from_review_state,
    normalize_excluded_sources,
    normalize_source_handles,
    replay_manual_overrides,
    result_member_counts,
    shared_handle_conflicts,
    source_file_fingerprint,
)
from dxf_import.validation import (
    build_problem_records,
    build_review_items,
    build_validation_overview,
)
from dxf_import.waler_contact_adjustment import apply_waler_contact_adjustment
from dxf_import.waler_engineering_line_repair import formalize_waler_engineering_line
from tests.sample_dxf_assets import Y29_DXF_PATH


def _review_item(
    key,
    display_id,
    role,
    status,
    handles,
    *,
    member_id=None,
):
    return ReviewItem(
        key=key,
        display_id=display_id,
        role=role,
        status=status,
        member_id=member_id,
        source_handles=tuple(handles),
        source_layers=(role.upper(),),
        source_entity_types=("LINE",),
        selection_source="auto" if member_id else "",
        problems=(),
        highest_severity="success",
    )


class _PreviewCanvas:
    def __init__(self):
        self.items = {}
        self.next_id = 1

    def create_line(self, *coordinates, **options):
        item_id = self.next_id
        self.next_id += 1
        self.items[item_id] = {
            "coordinates": tuple(coordinates),
            **options,
        }
        return item_id

    def delete(self, item_id):
        self.items.pop(item_id, None)

    def itemconfigure(self, item_id, **options):
        if item_id in self.items:
            self.items[item_id].update(options)


class _IdentityViewport:
    def __init__(self):
        self.view_bounds = None

    def set_view_bounds(self, bounds):
        self.view_bounds = bounds

    @property
    def legacy_transform(self):
        return (1.0, 1.0, 0.0, 0.0, 1.0)

    @staticmethod
    def data_to_screen(point):
        return point

    @staticmethod
    def intersects(_points):
        return True


class _ReviewTree:
    def __init__(self):
        self.rows = {}

    def get_children(self, parent=""):
        return tuple(
            iid for iid, row in self.rows.items() if row["parent"] == parent
        )

    def delete(self, *_iids):
        self.rows.clear()

    def insert(
        self,
        parent,
        _position,
        *,
        iid,
        text,
        open=False,
        tags=(),
    ):
        self.rows[iid] = {
            "parent": parent,
            "text": text,
            "open": open,
            "tags": tuple(tags),
        }


class SourceExclusionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "source.dxf"
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT", "BEAM"):
            document.layers.add(layer)
        model = document.modelspace()
        self.waler_1 = model.add_line(
            (0, 0), (10000, 0), dxfattribs={"layer": "WALER"}
        )
        self.waler_2 = model.add_line(
            (0, 5000), (10000, 5000), dxfattribs={"layer": "WALER"}
        )
        self.strut = model.add_line(
            (2000, 0), (2000, 5000), dxfattribs={"layer": "STRUT"}
        )
        self.bad_beam = model.add_lwpolyline(
            [(100, 100), (100, 100)],
            dxfattribs={"layer": "BEAM"},
        )
        document.saveas(self.path)
        self.roles = {
            "WALER": "waler",
            "STRUT": "strut",
            "BEAM": "beam",
        }
        self.importer = DXFImporter(self.path).read()
        self.document_counter = 0

    def tearDown(self):
        self.temp_dir.cleanup()

    def convert(self, exclusions=(), material_specs=()):
        return self.importer.convert(
            layer_roles=self.roles,
            coordinate_system=CoordinateSystem(),
            material_specs=material_specs,
            excluded_sources=exclusions,
        )

    @unittest.skipUnless(Y29_DXF_PATH.is_file(), "Y29 DXF test asset unavailable")
    def test_manual_waler_formalization_is_inactive_while_excluded_and_revalidated_on_restore(self):
        importer = DXFImporter(Y29_DXF_PATH).read()
        roles = {
            layer: DXFImportDialog.USE_TO_ROLE[label]
            for layer, label in Y29_LAYER_MAPPING.items()
            if layer in importer.layer_names
        }
        workflow = DXFReviewWorkflow(importer, Y29_DXF_PATH)
        workflow.recognize(roles)
        waler = next(
            item for item in workflow.world_result.walers
            if "58D" in item.source_handles
        )
        start_id = waler.selected_start_point_id or waler.recommended_start_point_id
        end_id = waler.selected_end_point_id or waler.recommended_end_point_id
        repair_plan = workflow.plan_waler_engineering_line_repair(
            waler.id,
            start_id,
            end_id,
            "manual_candidate_points",
            selected_candidate_id="line_1",
        )
        workflow.commit_waler_engineering_line_repair(repair_plan)
        formal_item = workflow.review_item_for_member(waler.id)

        saved_state = workflow.serialize_review_state(layer_roles=roles)
        resumed_importer = DXFImporter(Y29_DXF_PATH).read()
        resumed = DXFReviewWorkflow(
            resumed_importer,
            Y29_DXF_PATH,
            initial_state=saved_state,
            resume_review=True,
        )
        resumed.recognize(roles)
        resumed_w14 = next(
            item for item in resumed.world_result.walers
            if "58D" in item.source_handles
        )
        self.assertEqual(resumed_w14.contact_face_state, "formal")
        self.assertEqual(
            resumed_w14.engineering_line_authority,
            "manual_repair",
        )

        exclude_plan, restoring, _identity = workflow.plan_source_exclusion_for_item(
            formal_item
        )
        self.assertFalse(restoring)
        workflow.commit_source_exclusion_plan(exclude_plan)
        self.assertFalse(
            any("58D" in item.source_handles for item in workflow.world_result.walers)
        )

        excluded_item = next(
            item for item in workflow.review_items
            if item.status == "excluded" and "58D" in item.source_handles
        )
        restore_plan, restoring, _identity = workflow.plan_source_exclusion_for_item(
            excluded_item
        )
        self.assertTrue(restoring)
        workflow.commit_source_exclusion_plan(restore_plan)

        restored = next(
            item for item in workflow.world_result.walers
            if "58D" in item.source_handles
        )
        self.assertEqual(restored.contact_face_state, "formal")
        self.assertEqual(restored.engineering_line_authority, "manual_repair")
        self.assertIn(
            "W14 人工正式工程線",
            workflow.last_manual_replay_report.preserved,
        )

    def convert_document(self, document, roles, exclusions=()):
        self.document_counter += 1
        path = Path(self.temp_dir.name) / f"case_{self.document_counter}.dxf"
        document.saveas(path)
        importer = DXFImporter(path).read()
        return importer.convert(
            layer_roles=roles,
            coordinate_system=CoordinateSystem(),
            excluded_sources=exclusions,
        ), importer

    def test_handle_normalization_and_identity_are_deterministic(self):
        self.assertEqual(
            normalize_source_handles((" 2a8 ", "2A7", "2a7", "")),
            ("2A7", "2A8"),
        )
        self.assertEqual(
            canonical_source_identity(" Strut ", ("2a8", "2A7")),
            "strut:2A7|2A8",
        )
        normalized = normalize_excluded_sources(
            (
                ExcludedSource("STRUT", ("2a8", "2A7", "2a7")),
                {"role": "strut", "source_handles": ["2A7", "2A8"]},
            )
        )
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].identity, "strut:2A7|2A8")

    def test_shared_handle_conflicts_cover_all_review_item_combinations(self):
        formal_1 = _review_item(
            "member:strut:S1", "S1", "strut", "recognized", ("H1", "H2"), member_id="S1"
        )
        formal_2 = _review_item(
            "member:beam:BM1", "BM1", "beam", "recognized", ("H2",), member_id="BM1"
        )
        unresolved_1 = _review_item(
            "source:brace:H1|H3", "待修-H1", "brace", "unresolved", ("H1", "H3")
        )
        unresolved_2 = _review_item(
            "source:waler:H3", "待修-H3", "waler", "unresolved", ("H3",)
        )
        items = (formal_1, formal_2, unresolved_1, unresolved_2)

        formal_conflicts = shared_handle_conflicts(formal_1, items)
        unresolved_conflicts = shared_handle_conflicts(unresolved_1, items)

        self.assertEqual({item.handle for item in formal_conflicts}, {"H1", "H2"})
        self.assertEqual({item.handle for item in unresolved_conflicts}, {"H1", "H3"})
        self.assertIn("BM1 (beam)", formal_conflicts[1].owner_labels)

    def test_exact_same_role_and_handle_set_is_a_conflict(self):
        first = _review_item(
            "member:strut:S1", "S1", "strut", "recognized", ("H1", "H2"), member_id="S1"
        )
        second = _review_item(
            "member:strut:S2", "S2", "strut", "recognized", ("H2", "H1"), member_id="S2"
        )

        conflicts = shared_handle_conflicts(first, (first, second))

        self.assertEqual({item.handle for item in conflicts}, {"H1", "H2"})
        self.assertTrue(all("S2 (strut)" in item.owner_labels for item in conflicts))

    def test_paired_joist_siblings_are_one_source_not_an_ownership_conflict(self):
        first = _review_item(
            "member:beam:BM1",
            "BM1",
            "beam",
            "recognized",
            ("PAIR",),
            member_id="BM1",
        )
        second = _review_item(
            "member:beam:BM2",
            "BM2",
            "beam",
            "recognized",
            ("PAIR",),
            member_id="BM2",
        )

        result = SimpleNamespace(
            beams=(
                SimpleNamespace(id="BM1", joist_assembly_key="PAIR"),
                SimpleNamespace(id="BM2", joist_assembly_key="PAIR"),
            )
        )
        self.assertEqual(
            shared_handle_conflicts(first, (first, second), result),
            (),
        )
        self.assertTrue(shared_handle_conflicts(first, (first, second)))

    def test_paired_joist_manual_replay_is_not_guessed_by_member_order(self):
        common = {
            "source_layer": "BEAM",
            "source_handles": ("PAIR",),
            "source_entity_types": ("INSERT",),
            "recognition_method": "bim_joist_paired_axis",
            "centerline_computed": True,
            "source_width": 90.0,
            "confidence": 1.0,
            "selection_source": "cad_manual",
            "joist_assembly_key": "PAIR",
        }
        first = Beam(
            id="BM1",
            start=(0.0, 0.0),
            end=(1000.0, 0.0),
            joist_axis_slot=0,
            **common,
        )
        second = Beam(
            id="BM2",
            start=(0.0, 518.0),
            end=(1000.0, 518.0),
            joist_axis_slot=1,
            **common,
        )
        result = DXFImportResult(
            source_path="paired.dxf",
            layer_names=("BEAM",),
            selected_layers={"beam": ("BEAM",)},
            layer_info=(),
            walers=(),
            struts=(),
            braces=(),
            entity_debug=(),
            messages=(),
            source_entity_counts={"beam": 1},
            beams=(first, second),
        )

        overrides = capture_manual_overrides(result)
        replayed, report = replay_manual_overrides(result, overrides)

        self.assertEqual(2, len(overrides))
        self.assertEqual(result, replayed)
        self.assertEqual((), report.preserved)
        self.assertEqual(2, len(report.needs_review))

    def test_independent_handle_set_can_be_excluded(self):
        first = _review_item(
            "member:strut:S1", "S1", "strut", "recognized", ("H1",), member_id="S1"
        )
        second = _review_item(
            "source:beam:H2", "待修-H2", "beam", "unresolved", ("H2",)
        )
        self.assertEqual(shared_handle_conflicts(first, (first, second)), ())

    def test_formal_member_exclusion_filters_recognition_but_keeps_source_geometry(self):
        baseline = self.convert()
        item = next(
            item
            for item in build_review_items(baseline, build_problem_records(baseline))
            if item.member_id == "S1"
        )
        exclusion = excluded_source_from_review_item(item, baseline)

        excluded = self.convert((exclusion,))
        review_items = build_review_items(excluded, build_problem_records(excluded))

        self.assertEqual(len(baseline.struts), 1)
        self.assertEqual(excluded.struts, ())
        self.assertEqual(excluded.source_geometry, baseline.source_geometry)
        excluded_item = next(item for item in review_items if item.status == "excluded")
        self.assertEqual(excluded_item.display_id, "已排除-S1")
        self.assertEqual(excluded_item.source_handles, baseline.struts[0].source_handles)
        self.assertFalse(
            any(
                message.role == "strut"
                and message.code == "STRUT_RECOGNITION_FAILED"
                for message in excluded.messages
            )
        )
        overview = build_validation_overview(excluded)
        self.assertTrue(any("支撐來源已全部排除" in item.text for item in overview))

    def test_unresolved_exclusion_removes_only_its_active_problems(self):
        baseline = self.convert()
        unresolved = next(
            item
            for item in build_review_items(baseline, build_problem_records(baseline))
            if item.status == "unresolved" and item.role == "beam"
        )
        exclusion = excluded_source_from_review_item(unresolved, baseline)

        excluded = self.convert((exclusion,))
        review_items = build_review_items(excluded, build_problem_records(excluded))

        self.assertEqual(excluded.source_geometry, baseline.source_geometry)
        self.assertFalse(
            any(
                message.role == "beam"
                and set(message.source_handles).intersection(unresolved.source_handles)
                for message in excluded.messages
            )
        )
        excluded_item = next(item for item in review_items if item.status == "excluded")
        self.assertEqual(excluded_item.display_id, f"已排除-{self.bad_beam.dxf.handle}")
        self.assertEqual(
            excluded_item.display_id_before_exclusion,
            f"待修-{self.bad_beam.dxf.handle}",
        )

    def test_restore_recreates_formal_or_unresolved_source(self):
        baseline = self.convert()
        formal = next(
            item
            for item in build_review_items(baseline, build_problem_records(baseline))
            if item.member_id == "S1"
        )
        exclusion = excluded_source_from_review_item(formal, baseline)

        excluded = self.convert((exclusion,))
        restored = self.convert(())

        self.assertEqual(excluded.struts, ())
        self.assertEqual(restored.struts, baseline.struts)

    def test_waler_exclusion_rebuilds_connections_and_validation(self):
        baseline = self.convert()
        source = baseline.walers[0]
        exclusion = ExcludedSource(
            "waler",
            source.source_handles,
            (source.source_layer,),
            source.source_entity_types,
            source.id,
        )

        excluded = self.convert((exclusion,))

        self.assertEqual(len(excluded.walers), 1)
        self.assertNotEqual(
            (baseline.struts[0].from_waler, baseline.struts[0].to_waler),
            (excluded.struts[0].from_waler, excluded.struts[0].to_waler),
        )
        self.assertTrue(
            any(
                message.code in {"STRUT_NOT_CONNECTED", "STRUT_ONE_END_NOT_CONNECTED"}
                for message in excluded.messages
            )
        )

    def test_strut_exclusion_rebuilds_column_and_beam_associations(self):
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT", "COLUMN", "BEAM"):
            document.layers.add(layer)
        model = document.modelspace()
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((200, 0), (200, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((800, 0), (800, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((700, 400), (820, 400), dxfattribs={"layer": "COLUMN"})
        model.add_lwpolyline(
            [(100, 480), (900, 480), (900, 520), (100, 520)],
            close=True,
            dxfattribs={"layer": "BEAM"},
        )
        roles = {
            "WALER": "waler",
            "STRUT": "strut",
            "COLUMN": "column",
            "BEAM": "beam",
        }
        baseline, importer = self.convert_document(document, roles)
        removed = baseline.struts[1]

        rebuilt = importer.convert(
            layer_roles=roles,
            excluded_sources=(ExcludedSource("strut", removed.source_handles),),
        )

        self.assertEqual(len(rebuilt.struts), 1)
        self.assertEqual(rebuilt.beams[0].associated_strut_ids, ("S1",))
        self.assertEqual(rebuilt.struts[0].associated_beams, ("BM1",))
        self.assertEqual(rebuilt.columns[0].associated_strut_id, "")
        self.assertFalse(
            any(
                association.strut_id == removed.id
                for association in rebuilt.component_associations
            )
        )

    def test_corner_brace_exclusion_clears_rebuilt_derived_lengths(self):
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT", "CORNER"):
            document.layers.add(layer)
        model = document.modelspace()
        model.add_line((0, 0), (2000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 2000), (2000, 2000), dxfattribs={"layer": "WALER"})
        model.add_line((1000, 0), (1000, 2000), dxfattribs={"layer": "STRUT"})
        offset = 150 / math.sqrt(2)
        model.add_lwpolyline(
            [
                (offset, -offset),
                (1000 + offset, 1000 - offset),
                (1000 - offset, 1000 + offset),
                (-offset, offset),
            ],
            close=True,
            dxfattribs={"layer": "CORNER"},
        )
        roles = {
            "WALER": "waler",
            "STRUT": "strut",
            "CORNER": "corner_brace",
        }
        baseline, importer = self.convert_document(document, roles)
        corner = baseline.corner_braces[0]
        self.assertGreater(
            baseline.struts[0].from_brace_to_waler_start_len,
            0.0,
        )

        rebuilt = importer.convert(
            layer_roles=roles,
            excluded_sources=(
                ExcludedSource("corner_brace", corner.source_handles),
            ),
        )

        self.assertEqual(rebuilt.corner_braces, ())
        self.assertEqual(
            (
                rebuilt.struts[0].from_brace_to_waler_start_len,
                rebuilt.struts[0].from_brace_to_waler_end_len,
                rebuilt.struts[0].to_brace_to_waler_start_len,
                rebuilt.struts[0].to_brace_to_waler_end_len,
            ),
            (0.0, 0.0, 0.0, 0.0),
        )

    def test_excluding_one_invalid_source_does_not_suppress_another(self):
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT", "BEAM"):
            document.layers.add(layer)
        model = document.modelspace()
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((500, 0), (500, 1000), dxfattribs={"layer": "STRUT"})
        first = model.add_lwpolyline(
            [(100, 100), (100, 100)], dxfattribs={"layer": "BEAM"}
        )
        second = model.add_lwpolyline(
            [(200, 200), (200, 200)], dxfattribs={"layer": "BEAM"}
        )
        roles = {"WALER": "waler", "STRUT": "strut", "BEAM": "beam"}
        _baseline, importer = self.convert_document(document, roles)

        rebuilt = importer.convert(
            layer_roles=roles,
            excluded_sources=(ExcludedSource("beam", (first.dxf.handle,)),),
        )

        active_problem_handles = {
            handle
            for message in rebuilt.messages
            for handle in message.source_handles
        }
        self.assertNotIn(first.dxf.handle, active_problem_handles)
        self.assertIn(second.dxf.handle, active_problem_handles)
        self.assertTrue(
            any(
                message.role == "beam"
                and message.code == "BEAM_RECOGNITION_FAILED"
                for message in rebuilt.messages
            )
        )

    def test_duplicate_source_validation_is_rebuilt_after_exclusion(self):
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT", "BEAM"):
            document.layers.add(layer)
        model = document.modelspace()
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((200, 0), (200, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((800, 0), (800, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 500), (900, 500), dxfattribs={"layer": "BEAM"})
        roles = {"WALER": "waler", "STRUT": "strut", "BEAM": "beam"}
        baseline, importer = self.convert_document(document, roles)
        manually_duplicated = set_cad_engineering_line(
            baseline,
            "S1",
            baseline.struts[1].world_start,
            baseline.struts[1].world_end,
            importer.tolerances,
        )
        self.assertTrue(
            any(
                message.code == "DUPLICATE_ENGINEERING_COMPONENT"
                for message in manually_duplicated.messages
            )
        )
        overrides = capture_manual_overrides(manually_duplicated)
        beam = baseline.beams[0]

        staged = importer.convert(
            layer_roles=roles,
            excluded_sources=(
                ExcludedSource("beam", beam.source_handles),
            ),
        )
        rebuilt, report = replay_manual_overrides(
            staged,
            overrides,
            tolerances=importer.tolerances,
        )

        self.assertEqual(rebuilt.beams, ())
        self.assertEqual(len(report.preserved), 1)
        self.assertTrue(
            any(
                message.code == "DUPLICATE_ENGINEERING_COMPONENT"
                for message in rebuilt.messages
            )
        )

    def test_exclude_restore_never_writes_original_dxf(self):
        before_bytes = self.path.read_bytes()
        before_hash = hashlib.sha256(before_bytes).hexdigest()
        before_mtime = self.path.stat().st_mtime_ns
        baseline = self.convert()
        source = baseline.struts[0]
        exclusion = ExcludedSource("strut", source.source_handles)

        self.convert((exclusion,))
        self.convert(())

        after_bytes = self.path.read_bytes()
        self.assertEqual(after_bytes, before_bytes)
        self.assertEqual(hashlib.sha256(after_bytes).hexdigest(), before_hash)
        self.assertEqual(self.path.stat().st_mtime_ns, before_mtime)

    def test_same_sha_restores_across_paths_and_different_sha_does_not(self):
        fingerprint = source_file_fingerprint(self.path)
        exclusion = ExcludedSource("beam", (self.bad_beam.dxf.handle,))
        state = {
            "source_path": str(self.path),
            "source_fingerprint": fingerprint,
            "excluded_sources": [asdict(exclusion)],
        }
        copied = Path(self.temp_dir.name) / "moved.dxf"
        shutil.copyfile(self.path, copied)

        restored = exclusions_from_review_state(
            state,
            source_file_fingerprint(copied),
        )
        self.assertEqual(restored.excluded_sources, (exclusion,))
        self.assertFalse(restored.fingerprint_mismatch)

        changed = Path(self.temp_dir.name) / "same-name" / self.path.name
        changed.parent.mkdir()
        changed.write_bytes(self.path.read_bytes() + b"\n999\nchanged\n")
        rejected = exclusions_from_review_state(
            state,
            source_file_fingerprint(changed),
        )
        self.assertEqual(rejected.excluded_sources, ())
        self.assertTrue(rejected.fingerprint_mismatch)

    def test_debug_state_round_trips_fingerprint_exclusions_and_snapshot(self):
        baseline = self.convert()
        manual = set_member_material_spec(baseline, "S1", "H350x350")
        item = next(
            item
            for item in build_review_items(manual, build_problem_records(manual))
            if item.member_id == "S1"
        )
        exclusion = excluded_source_from_review_item(item, manual)
        state = replace(manual, excluded_sources=(exclusion,)).to_debug_dict()

        restored = exclusions_from_review_state(
            copy.deepcopy(state),
            self.importer.source_fingerprint,
        )

        self.assertEqual(restored.excluded_sources, (exclusion,))
        self.assertTrue(restored.excluded_sources[0].manual_override.has_material_spec)
        self.assertEqual(
            restored.excluded_sources[0].manual_override.material_spec,
            "H350x350",
        )

    def test_material_and_cad_geometry_replay_by_exact_source_not_old_id(self):
        specs = ({"Usage": "支撐", "Spec": "H350x350"},)
        baseline = self.convert(material_specs=specs)
        manual = set_member_material_spec(baseline, "S1", "H350x350")
        member = manual.struts[0]
        manual = set_cad_engineering_line(
            manual,
            member.id,
            member.world_start,
            member.world_end,
            self.importer.tolerances,
        )
        overrides = tuple(
            replace(item, display_id="OLD-S99")
            for item in capture_manual_overrides(manual)
        )

        replayed, report = replay_manual_overrides(
            self.convert(material_specs=specs),
            overrides,
            material_specs=specs,
            tolerances=self.importer.tolerances,
        )

        self.assertEqual(replayed.struts[0].id, "S1")
        self.assertEqual(replayed.struts[0].material_spec, "H350x350")
        self.assertEqual(replayed.struts[0].material_spec_source, "manual")
        self.assertEqual(replayed.struts[0].selection_source, "cad_manual")
        self.assertEqual(len(report.preserved), 2)
        self.assertEqual(report.needs_review, ())

    def test_step5_geometry_replays_real_world_points_and_rebuilds_relations(self):
        baseline = self.convert()
        pending, start_id, end_id = add_cad_candidate_points(
            baseline,
            "S1",
            (2500.0, 0.0),
            (2500.0, 5000.0),
            self.importer.tolerances,
        )
        manual = apply_candidate_point_selection(
            pending,
            "S1",
            start_id,
            end_id,
            self.importer.tolerances,
            selection_source="manual_candidate_points",
        )
        overrides = capture_manual_overrides(manual)

        replayed, report = replay_manual_overrides(
            self.convert(),
            overrides,
            tolerances=self.importer.tolerances,
        )

        self.assertEqual(replayed.struts[0].selection_source, "manual_candidate_points")
        self.assertEqual(replayed.struts[0].world_start, (2500.0, 0.0))
        self.assertEqual(replayed.struts[0].world_end, (2500.0, 5000.0))
        self.assertEqual(
            (replayed.struts[0].from_waler, replayed.struts[0].to_waler),
            ("W1", "W2"),
        )
        self.assertEqual(len(report.preserved), 1)
        self.assertEqual(report.needs_review, ())

    def test_waler_contact_replays_input_parameters_not_saved_output_geometry(self):
        baseline = self.importer.convert(
            layer_roles={"WALER": "waler", "STRUT": "strut"},
        )
        adjusted = apply_waler_contact_adjustment(
            baseline,
            "W1",
            original_backfill_mm=100.0,
            adopted_backfill_mm=120.0,
            original_waler_width_mm=300.0,
            adopted_waler_width_mm=350.0,
            tolerances=self.importer.tolerances,
        )
        override = capture_manual_overrides(adjusted)
        fresh = self.importer.convert(
            layer_roles={"WALER": "waler", "STRUT": "strut"},
        )

        replayed, report = replay_manual_overrides(
            fresh,
            override,
            tolerances=self.importer.tolerances,
        )

        review = next(
            item for item in replayed.waler_contact_reviews if item.waler_id == "W1"
        )
        self.assertEqual(
            (
                review.original_backfill_mm,
                review.adopted_backfill_mm,
                review.original_waler_width_mm,
                review.adopted_waler_width_mm,
            ),
            (100.0, 120.0, 300.0, 350.0),
        )
        self.assertEqual(replayed.walers[0].selection_source, "waler_contact_adjustment")
        self.assertEqual(replayed.walers[0].world_start, (0.0, 70.0))
        self.assertEqual(len(report.preserved), 1)
        self.assertEqual(report.needs_review, ())

    def test_replace_and_append_project_rows_follow_existing_import_semantics(self):
        baseline = self.importer.convert(
            layer_roles={"WALER": "waler", "STRUT": "strut"},
        )
        excluded = self.importer.convert(
            layer_roles={"WALER": "waler", "STRUT": "strut"},
            excluded_sources=(
                ExcludedSource("strut", baseline.struts[0].source_handles),
            ),
        )
        existing_strut = {"StrutID": "S9", "StartX": 9, "StartY": 0}

        replacement = excluded.to_project_rows()
        appended = excluded.to_project_rows(
            {
                "walers": ({"WalerID": "W9"},),
                "struts": (existing_strut,),
                "braces": (),
            }
        )

        self.assertEqual(replacement["struts"], [])
        self.assertEqual(appended["struts"], [])
        self.assertEqual([existing_strut, *appended["struts"]], [existing_strut])

    def test_staging_accepts_validation_errors_and_commit_is_atomic(self):
        baseline = self.importer.convert(
            layer_roles={"WALER": "waler", "STRUT": "strut"},
        )
        source = baseline.walers[0]
        exclusion = ExcludedSource(
            "waler",
            source.source_handles,
            (source.source_layer,),
            source.source_entity_types,
            source.id,
        )
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        workflow.set_coordinate_origin((100.0, 200.0))
        local = workflow.result

        stage = workflow.plan_source_exclusion_change((exclusion,))

        self.assertIs(workflow.world_result, baseline)
        self.assertIs(workflow.result, local)
        self.assertEqual(workflow.excluded_sources, ())
        self.assertTrue(
            any(
                message.severity in {"error", "critical"}
                for message in stage.result.messages
            )
        )
        self.assertEqual(stage.result.coordinate_system.mode, "local")

        workflow.commit_source_exclusion_plan(stage)

        self.assertIs(workflow.world_result, stage.world_result)
        self.assertIs(workflow.result, stage.result)
        self.assertEqual(workflow.excluded_sources, (exclusion,))
        self.assertIs(workflow.candidate_point_store, stage.candidate_point_store)
        self.assertEqual(workflow.review_confirmations, stage.review_confirmations)
        self.assertEqual(workflow.revision, stage.effects.committed_revision)

    def test_source_exclusion_plan_prebuild_failure_keeps_live_snapshot(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        source = baseline.struts[0]
        exclusion = ExcludedSource("strut", source.source_handles)
        before = workflow.snapshot
        before_store = workflow.candidate_point_store

        with patch(
            "dxf_import.review_workflow.CandidatePointStore.rebuild",
            side_effect=RuntimeError("candidate projection failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "candidate projection failed"):
                workflow.plan_source_exclusion_change((exclusion,))

        self.assertEqual(workflow.snapshot, before)
        self.assertIs(workflow.candidate_point_store, before_store)

    def test_source_exclusion_commit_rejects_stale_or_invalid_plan_atomically(self):
        baseline = self.convert()
        source = baseline.struts[0]
        exclusion = ExcludedSource("strut", source.source_handles)

        for invalid_kind in ("stale", "fingerprint"):
            with self.subTest(invalid_kind=invalid_kind):
                workflow = DXFReviewWorkflow(
                    self.importer,
                    self.path,
                    initial_world_result=baseline,
                )
                plan = workflow.plan_source_exclusion_change((exclusion,))
                if invalid_kind == "stale":
                    workflow.revision += 1
                else:
                    plan = replace(
                        plan,
                        world_result=replace(
                            plan.world_result,
                            source_fingerprint="B" * 64,
                        ),
                    )
                before = workflow.snapshot
                before_store = workflow.candidate_point_store

                with self.assertRaises(Exception):
                    workflow.commit_source_exclusion_plan(plan)

                self.assertEqual(workflow.snapshot, before)
                self.assertIs(workflow.candidate_point_store, before_store)

    def test_source_exclusion_commit_rolls_back_unexpected_adoption_failure(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        source = baseline.struts[0]
        plan = workflow.plan_source_exclusion_change(
            (ExcludedSource("strut", source.source_handles),)
        )
        before = workflow.snapshot
        before_store = workflow.candidate_point_store

        def fail_after_partial_assignment(staged):
            workflow.excluded_sources = staged.excluded_sources
            workflow.world_result = staged.world_result
            workflow.review_items = staged.review_items
            raise RuntimeError("assignment failed")

        with patch.object(
            workflow,
            "_adopt_source_exclusion_plan",
            side_effect=fail_after_partial_assignment,
        ):
            with self.assertRaisesRegex(RuntimeError, "assignment failed"):
                workflow.commit_source_exclusion_plan(plan)

        self.assertEqual(workflow.snapshot, before)
        self.assertIs(workflow.candidate_point_store, before_store)

    def test_source_exclusion_plan_is_not_persisted_and_commit_uses_existing_schema(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        before = workflow.serialize_review_state(
            layer_roles=baseline.layer_classification,
        )
        source = baseline.struts[0]
        plan = workflow.plan_source_exclusion_change(
            (ExcludedSource("strut", source.source_handles),)
        )

        self.assertEqual(
            workflow.serialize_review_state(
                layer_roles=baseline.layer_classification,
            ),
            before,
        )
        workflow.commit_source_exclusion_plan(plan)
        saved = workflow.serialize_review_state(
            layer_roles=baseline.layer_classification,
        )

        self.assertTrue(saved["excluded_sources"])
        for transient_key in (
            "source_exclusion_plan",
            "mutation_effects",
            "candidate_point_store",
            "debug_payload",
        ):
            self.assertNotIn(transient_key, saved)

    def test_one_exclusion_uses_one_recognition_and_one_revision_increment(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        source = baseline.struts[0]
        before_revision = workflow.revision

        with patch.object(
            self.importer,
            "convert",
            wraps=self.importer.convert,
        ) as convert:
            plan = workflow.plan_source_exclusion_change(
                (ExcludedSource("strut", source.source_handles),)
            )
            workflow.commit_source_exclusion_plan(plan)

        self.assertEqual(convert.call_count, 1)
        self.assertEqual(workflow.revision, before_revision + 1)

    def test_single_item_plan_commit_characterization_stays_canonical(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        item = next(
            value for value in workflow.review_items
            if value.role == "strut" and value.status != "excluded"
        )
        before = workflow.snapshot
        before_revision = workflow.revision

        plan, restoring, identity = workflow.plan_source_exclusion_for_item(item)

        self.assertFalse(restoring)
        self.assertEqual(
            plan.excluded_sources,
            normalize_excluded_sources(plan.excluded_sources),
        )
        self.assertEqual(plan.base_revision, before_revision)
        self.assertEqual(identity, plan.excluded_sources[0].identity)
        self.assertIs(workflow.world_result, before.world_result)
        self.assertEqual(workflow.snapshot, before)
        self.assertIsInstance(plan.manual_replay, ManualReplayReport)

        workflow.commit_source_exclusion_plan(plan)

        self.assertEqual(workflow.revision, before_revision + 1)
        self.assertEqual(workflow.excluded_sources, plan.excluded_sources)
        excluded_item = next(
            value for value in workflow.review_items
            if value.status == "excluded" and workflow.review_item_identity(value) == identity
        )
        restore_plan, restoring, restore_identity = (
            workflow.plan_source_exclusion_for_item(excluded_item)
        )
        self.assertTrue(restoring)
        self.assertEqual(restore_identity, identity)
        self.assertEqual(restore_plan.excluded_sources, ())

    def test_pending_draft_mark_is_immutable_and_does_not_recognize(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        item = next(
            value for value in workflow.review_items
            if value.role == "strut" and value.status != "excluded"
        )
        empty = workflow.pending_source_exclusion_draft
        before_revision = workflow.revision

        with patch.object(self.importer, "convert", wraps=self.importer.convert) as convert:
            active = workflow.mark_source_exclusion(item)

        self.assertIsInstance(active, PendingSourceExclusionDraft)
        self.assertEqual(empty.state, "EMPTY")
        self.assertEqual(empty.sources, ())
        self.assertEqual(active.state, "ACTIVE")
        self.assertEqual(active.base_revision, before_revision)
        self.assertEqual(active.source_fingerprint, baseline.source_fingerprint)
        self.assertEqual(active.generation, empty.generation + 1)
        self.assertEqual(active.identities, (workflow.review_item_identity(item),))
        self.assertEqual(workflow.revision, before_revision)
        self.assertEqual(convert.call_count, 0)
        self.assertIsNot(empty, workflow.snapshot.pending_source_exclusion)

    def test_pending_unmark_discard_and_noop_generation(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        items = tuple(
            value for value in workflow.review_items
            if value.status != "excluded" and value.role in {"waler", "strut"}
        )[:2]
        self.assertEqual(len(items), 2)
        first = workflow.mark_source_exclusion(items[0])
        second = workflow.mark_source_exclusion(items[1])
        self.assertEqual(len(second.sources), 2)
        self.assertEqual(
            workflow.mark_source_exclusion(items[1]).generation,
            second.generation,
        )

        remaining = workflow.unmark_source_exclusion(items[0])
        self.assertEqual(len(remaining.sources), 1)
        self.assertEqual(remaining.generation, second.generation + 1)
        self.assertEqual(
            workflow.unmark_source_exclusion("missing:identity").generation,
            remaining.generation,
        )
        empty = workflow.discard_pending_source_exclusions()
        self.assertEqual(empty.state, "EMPTY")
        self.assertEqual(empty.sources, ())
        self.assertEqual(empty.generation, remaining.generation + 1)
        self.assertEqual(
            workflow.discard_pending_source_exclusions().generation,
            empty.generation,
        )

    def test_pending_paired_joist_siblings_share_one_atomic_identity(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        first = _review_item(
            "member:beam:BM1", "BM1", "beam", "recognized", ("PAIR",),
            member_id="BM1",
        )
        second = _review_item(
            "member:beam:BM2", "BM2", "beam", "recognized", ("PAIR",),
            member_id="BM2",
        )
        workflow.review_items = (first, second)
        workflow.world_result = replace(
            baseline,
            beams=(
                Beam(
                    "BM1", (0.0, 0.0), (100.0, 0.0), "BEAM", ("PAIR",),
                    ("LINE",), "paired_joist", True, 10.0, 1.0,
                    joist_assembly_key="PAIR",
                ),
                Beam(
                    "BM2", (0.0, 10.0), (100.0, 10.0), "BEAM", ("PAIR",),
                    ("LINE",), "paired_joist", True, 10.0, 1.0,
                    joist_assembly_key="PAIR",
                ),
            ),
        )

        first_draft = workflow.mark_source_exclusion(first)
        second_draft = workflow.mark_source_exclusion(second)

        self.assertEqual(len(first_draft.sources), 1)
        self.assertEqual(second_draft, first_draft)
        self.assertEqual(second_draft.identities, ("beam:PAIR",))
        self.assertTrue(workflow.pending_source_exclusion_contains(second))
        self.assertTrue(workflow.unmark_source_exclusion(second).is_empty)

    def test_pending_draft_becomes_stale_and_only_discard_clears_it(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        item = next(
            value for value in workflow.review_items
            if value.role == "strut" and value.status != "excluded"
        )
        workflow.mark_source_exclusion(item)
        before = workflow.snapshot
        workflow.revision += 1

        self.assertEqual(workflow.pending_source_exclusion_draft.state, "STALE")
        with self.assertRaisesRegex(DXFImportError, "已失效"):
            workflow.plan_pending_source_exclusions()
        with self.assertRaisesRegex(DXFImportError, "只能捨棄"):
            workflow.unmark_source_exclusion(item)
        self.assertEqual(workflow.excluded_sources, before.excluded_sources)
        self.assertEqual(workflow.discard_pending_source_exclusions().state, "EMPTY")

    def test_pending_mark_rejects_shared_handle_without_partial_draft(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        first = _review_item(
            "source:strut:H1", "待修-H1", "strut", "unresolved", ("H1",)
        )
        other = _review_item(
            "source:waler:H1", "待修-H1-W", "waler", "unresolved", ("H1",)
        )
        workflow.review_items = (first, other)

        with patch.object(self.importer, "convert", wraps=self.importer.convert) as convert:
            with self.assertRaisesRegex(DXFImportError, "共用 Handle"):
                workflow.mark_source_exclusion(first)

        self.assertTrue(workflow.pending_source_exclusion_draft.is_empty)
        self.assertEqual(convert.call_count, 0)

    def test_pending_mark_rejects_missing_mismatched_or_excluded_item(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        item = next(
            value for value in workflow.review_items
            if value.role == "strut" and value.status != "excluded"
        )
        missing = replace(item, key="missing:item")
        mismatched = replace(item, role="waler")
        excluded = replace(item, status="excluded")

        with patch.object(self.importer, "convert", wraps=self.importer.convert) as convert:
            with self.assertRaisesRegex(DXFImportError, "已變更"):
                workflow.mark_source_exclusion(missing)
            with self.assertRaisesRegex(DXFImportError, "已變更"):
                workflow.mark_source_exclusion(mismatched)
            workflow.review_items = tuple(
                excluded if value.key == item.key else value
                for value in workflow.review_items
            )
            with self.assertRaisesRegex(DXFImportError, "已正式排除"):
                workflow.mark_source_exclusion(excluded)

        self.assertTrue(workflow.pending_source_exclusion_draft.is_empty)
        self.assertEqual(convert.call_count, 0)

    def test_pending_mutation_guard_blocks_workflow_mutation_commands(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        item = next(
            value for value in workflow.review_items
            if value.role == "strut" and value.status != "excluded"
        )
        single_plan, _restoring, _identity = (
            workflow.plan_source_exclusion_for_item(item)
        )
        workflow.mark_source_exclusion(item)
        before = workflow.snapshot
        calls = {
            "recognize_staged": lambda: workflow.recognize_staged((), layer_roles={}),
            "install_recovery": lambda: workflow.install_staged_recovery(
                baseline,
                layer_roles={},
                excluded_sources=(),
                double_support_decisions={},
                review_confirmations={},
                manual_replay_report=ManualReplayReport(),
            ),
            "recognize": lambda: workflow.recognize({}),
            "coordinate": lambda: workflow.set_coordinate_origin((1.0, 2.0)),
            "import_mode": lambda: workflow.set_import_mode("append"),
            "double_support": lambda: workflow.commit_double_support_candidates(()),
            "candidate": lambda: workflow.apply_candidate_change("S1", "A", "B", "manual"),
            "waler_plan": lambda: workflow.plan_waler_engineering_line_repair(
                "W1", "A", "B", "manual"
            ),
            "waler_commit": lambda: workflow.commit_waler_engineering_line_repair(None),
            "cad_line": lambda: workflow.add_cad_candidate_line(
                "S1", (0.0, 0.0), (1.0, 1.0)
            ),
            "material": lambda: workflow.set_material_spec("S1", "H350"),
            "column_plan": lambda: workflow.plan_column_association_repair("C1"),
            "column_commit": lambda: workflow.commit_column_association_repair(None, ()),
            "column_withdraw": lambda: workflow.withdraw_column_association_repair(None),
            "contact_preview": lambda: workflow.preview_waler_contact_adjustment("W1"),
            "contact_apply": lambda: workflow.apply_waler_contact_adjustment("W1"),
            "corner_plan": lambda: workflow.plan_corner_brace_repair(item),
            "corner_commit": lambda: workflow.commit_corner_brace_repair(None, "candidate"),
            "confirm": lambda: workflow.confirm(item),
            "prune_confirmations": workflow.prune_confirmations,
            "single_plan_commit": lambda: workflow.commit_source_exclusion_plan(
                single_plan
            ),
        }

        for name, call in calls.items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    DXFImportError,
                    "請先套用或捨棄待排除來源",
                ):
                    call()

        self.assertEqual(workflow.snapshot, before)

    def test_pending_read_only_queries_and_serialization_keep_draft_ephemeral(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        item = next(
            value for value in workflow.review_items
            if value.role == "strut" and value.status != "excluded"
        )
        active = workflow.mark_source_exclusion(item)
        before_revision = workflow.revision

        self.assertEqual(workflow.review_item_by_key(item.key), item)
        self.assertIsNotNone(workflow.member_by_id(item.member_id or ""))
        self.assertIsNotNone(workflow.completion_status())
        self.assertEqual(workflow.pending_source_exclusion_draft, active)
        saved = workflow.serialize_review_state()

        self.assertEqual(workflow.revision, before_revision)
        self.assertNotIn("pending_source_exclusion", saved)
        self.assertNotIn("pending_exclusions", saved)
        self.assertEqual(saved["excluded_sources"], [])
        resumed = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_state=saved,
            resume_review=True,
            initial_world_result=baseline,
        )
        self.assertTrue(resumed.pending_source_exclusion_draft.is_empty)

    def test_pending_draft_blocks_restore_but_empty_keeps_single_restore(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        items = tuple(
            value for value in workflow.review_items
            if value.status != "excluded" and value.role in {"waler", "strut"}
        )[:2]
        exclude_plan, _restoring, excluded_identity = (
            workflow.plan_source_exclusion_for_item(items[0])
        )
        workflow.commit_source_exclusion_plan(exclude_plan)
        excluded_item = next(
            value for value in workflow.review_items
            if value.status == "excluded"
            and workflow.review_item_identity(value) == excluded_identity
        )
        other = next(
            value for value in workflow.review_items
            if value.status != "excluded"
        )
        workflow.mark_source_exclusion(other)
        before = workflow.snapshot

        with self.assertRaisesRegex(
            DXFImportError,
            "請先套用或捨棄待排除來源",
        ):
            workflow.plan_source_exclusion_for_item(excluded_item)
        self.assertEqual(workflow.snapshot, before)

        workflow.discard_pending_source_exclusions()
        restore_plan, restoring, identity = workflow.plan_source_exclusion_for_item(
            excluded_item
        )
        self.assertTrue(restoring)
        self.assertEqual(identity, excluded_identity)
        self.assertNotIn(excluded_identity, {
            source.identity for source in restore_plan.excluded_sources
        })

    def test_pending_apply_uses_one_recognition_and_one_replay_for_all_sources(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        items = tuple(
            value for value in workflow.review_items
            if value.status != "excluded" and value.role in {"waler", "strut"}
        )[:2]
        self.assertEqual(len(items), 2)
        before_revision = workflow.revision

        with patch.object(self.importer, "convert", wraps=self.importer.convert) as convert, patch(
            "dxf_import.review_workflow.replay_manual_overrides",
            wraps=replay_manual_overrides,
        ) as replay, patch(
            "dxf_import.review_workflow.build_problem_records",
            wraps=build_problem_records,
        ) as records, patch(
            "dxf_import.review_workflow.build_review_items",
            wraps=build_review_items,
        ) as review_items:
            for item in items:
                workflow.mark_source_exclusion(item)
            self.assertEqual(convert.call_count, 0)
            self.assertEqual(replay.call_count, 0)
            self.assertEqual(records.call_count, 0)
            self.assertEqual(review_items.call_count, 0)
            plan = workflow.plan_pending_source_exclusions()

        self.assertEqual(convert.call_count, 1)
        self.assertEqual(replay.call_count, 1)
        self.assertEqual(records.call_count, 1)
        self.assertEqual(review_items.call_count, 1)
        self.assertEqual(
            plan.pending_source_identities,
            workflow.pending_source_exclusion_draft.identities,
        )
        self.assertEqual(
            {source.identity for source in plan.excluded_sources},
            set(plan.pending_source_identities),
        )
        workflow.commit_source_exclusion_plan(plan)
        self.assertEqual(workflow.revision, before_revision + 1)
        self.assertTrue(workflow.pending_source_exclusion_draft.is_empty)

    def test_pending_aggregate_impact_uses_final_plan_and_required_guidance(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        items = tuple(
            value for value in workflow.review_items
            if value.status != "excluded" and value.role in {"waler", "strut"}
        )[:2]
        for item in items:
            workflow.mark_source_exclusion(item)
        draft = workflow.pending_source_exclusion_draft
        plan = workflow.plan_pending_source_exclusions()

        text = DXFImportDialog._format_pending_source_exclusion_impact(
            workflow.result,
            workflow.review_confirmations,
            draft.sources,
            plan,
        )

        self.assertIn("以下為所有待排除來源合併後的結果", text)
        self.assertIn("若結果不如預期，可取消個別待排除後重新套用", text)
        for source in draft.sources:
            self.assertIn(source.display_id_when_excluded, text)
            self.assertIn(source.source_handles[0], text)
        expected_after = sum(result_member_counts(plan.result).values())
        self.assertIn(f"→ {expected_after}", text)
        self.assertIn(f"人工輸入成功保留：{len(plan.manual_replay.preserved)}", text)

    def test_pending_plan_rejects_changed_draft_without_live_mutation(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        items = tuple(
            value for value in workflow.review_items
            if value.status != "excluded" and value.role in {"waler", "strut"}
        )[:2]
        workflow.mark_source_exclusion(items[0])
        plan = workflow.plan_pending_source_exclusions()
        committed_before = workflow.excluded_sources
        result_before = workflow.result
        workflow.mark_source_exclusion(items[1])

        with self.assertRaisesRegex(DXFImportError, "待排除來源已變更"):
            workflow.commit_source_exclusion_plan(plan)

        self.assertEqual(workflow.excluded_sources, committed_before)
        self.assertIs(workflow.result, result_before)
        self.assertEqual(len(workflow.pending_source_exclusion_draft.sources), 2)

    def test_pending_commit_failure_rolls_back_and_keeps_draft(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        item = next(
            value for value in workflow.review_items
            if value.role == "strut" and value.status != "excluded"
        )
        draft = workflow.mark_source_exclusion(item)
        plan = workflow.plan_pending_source_exclusions()
        before = workflow.snapshot

        with patch.object(
            workflow,
            "_adopt_source_exclusion_plan",
            side_effect=RuntimeError("adoption failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "adoption failed"):
                workflow.commit_source_exclusion_plan(plan)

        self.assertEqual(workflow.snapshot, before)
        self.assertEqual(workflow.pending_source_exclusion_draft, draft)

    def test_cancelled_pending_plan_cannot_commit_and_reapply_builds_new_plan(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        item = next(
            value for value in workflow.review_items
            if value.role == "strut" and value.status != "excluded"
        )
        draft = workflow.mark_source_exclusion(item)
        first = workflow.plan_pending_source_exclusions()

        workflow.cancel_pending_source_exclusion_plan(first)

        self.assertEqual(workflow.pending_source_exclusion_draft, draft)
        with self.assertRaisesRegex(DXFImportError, "待排除來源已變更"):
            workflow.commit_source_exclusion_plan(first)
        second = workflow.plan_pending_source_exclusions()
        self.assertNotEqual(first.pending_plan_token, second.pending_plan_token)
        workflow.commit_source_exclusion_plan(second)
        self.assertTrue(workflow.pending_source_exclusion_draft.is_empty)

    def test_pending_plan_build_failures_keep_committed_snapshot_and_draft(self):
        baseline = self.convert()
        failure_targets = (
            "_recognize_staged",
            "build_problem_records",
            "build_review_items",
            "valid_review_confirmations",
        )
        for target in failure_targets:
            with self.subTest(target=target):
                workflow = DXFReviewWorkflow(
                    self.importer,
                    self.path,
                    initial_world_result=baseline,
                )
                item = next(
                    value for value in workflow.review_items
                    if value.role == "strut" and value.status != "excluded"
                )
                workflow.mark_source_exclusion(item)
                before = workflow.snapshot
                patch_target = (
                    patch.object(workflow, target, side_effect=RuntimeError(target))
                    if target.startswith("_")
                    else patch(
                        f"dxf_import.review_workflow.{target}",
                        side_effect=RuntimeError(target),
                    )
                )
                with patch_target:
                    with self.assertRaisesRegex(RuntimeError, target):
                        workflow.plan_pending_source_exclusions()
                self.assertEqual(workflow.snapshot, before)

        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        item = next(
            value for value in workflow.review_items
            if value.role == "strut" and value.status != "excluded"
        )
        workflow.mark_source_exclusion(item)
        before = workflow.snapshot
        with patch(
            "dxf_import.review_workflow.CandidatePointStore.rebuild",
            side_effect=RuntimeError("candidate store"),
        ):
            with self.assertRaisesRegex(RuntimeError, "candidate store"):
                workflow.plan_pending_source_exclusions()
        self.assertEqual(workflow.snapshot, before)

    def test_restore_is_staged_without_changing_current_result(self):
        baseline = self.importer.convert(
            layer_roles={"WALER": "waler", "STRUT": "strut"},
        )
        source = baseline.struts[0]
        exclusion = ExcludedSource("strut", source.source_handles)
        current = self.importer.convert(
            layer_roles={"WALER": "waler", "STRUT": "strut"},
            excluded_sources=(exclusion,),
        )
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_state={
                "source_path": str(self.path),
                "source_fingerprint": self.importer.source_fingerprint,
                "excluded_sources": [asdict(exclusion)],
            },
            initial_world_result=current,
        )

        stage = workflow.plan_source_exclusion_change(())

        self.assertIs(workflow.world_result, current)
        self.assertEqual(workflow.excluded_sources, (exclusion,))
        self.assertEqual(len(stage.world_result.struts), 1)
        self.assertEqual(stage.excluded_sources, ())

    def test_invalid_manual_geometry_is_reported_not_silently_replayed(self):
        baseline = self.convert()
        source = baseline.struts[0]
        override = SourceManualOverride(
            "strut",
            source.source_handles,
            display_id="S1",
            geometry_selection_source="cad_manual",
            world_start=(0.0, 0.0),
            world_end=(0.0, 1.0),
        )

        replayed, report = replay_manual_overrides(
            baseline,
            (override,),
            tolerances=self.importer.tolerances,
        )

        self.assertEqual(replayed.struts[0].selection_source, "auto")
        self.assertEqual(report.preserved, ())
        self.assertEqual(len(report.needs_review), 1)

    def test_override_snapshot_is_disabled_while_source_is_excluded(self):
        baseline = self.convert()
        source = baseline.struts[0]
        override = SourceManualOverride(
            "strut",
            source.source_handles,
            display_id="S1",
            has_material_spec=True,
            material_spec="H350x350",
        )
        exclusion = ExcludedSource(
            "strut",
            source.source_handles,
            manual_override=override,
        )
        excluded = self.convert((exclusion,))

        _result, report = replay_manual_overrides(excluded, (override,))

        self.assertEqual(report.preserved, ())
        self.assertEqual(report.needs_review, ())
        self.assertEqual(report.disabled, ("S1 材料規格",))

    def test_dialog_shared_handle_reason_lists_real_handle_and_owner(self):
        selected = _review_item(
            "member:strut:S1", "S1", "strut", "recognized", ("H1",), member_id="S1"
        )
        other = _review_item(
            "member:beam:BM1", "BM1", "beam", "recognized", ("H1",), member_id="BM1"
        )
        workflow = DXFReviewWorkflow.__new__(DXFReviewWorkflow)
        workflow.review_items = (selected, other)

        reason = workflow.source_exclusion_disabled_reason(selected)

        self.assertIn("Handle H1", reason)
        self.assertIn("BM1 (beam)", reason)

    def test_excluded_review_items_are_projected_into_dedicated_tree_group(self):
        baseline = self.convert()
        source = baseline.struts[0]
        excluded = replace(
            baseline,
            struts=(),
            excluded_sources=(
                ExcludedSource(
                    "strut",
                    source.source_handles,
                    (source.source_layer,),
                    source.source_entity_types,
                    "S1",
                ),
            ),
        )
        review_items = build_review_items(excluded, build_problem_records(excluded))
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.member_tree = _ReviewTree()
        dialog.member_by_tree_iid = {}
        dialog.member_tree_iid_by_member_id = {}
        dialog.review_item_by_tree_iid = {}
        dialog.review_items = review_items
        dialog.selected_review_item_key = ""
        dialog.result = excluded
        dialog.review_workflow = SimpleNamespace(
            is_review_item_confirmed=lambda _item: False,
        )
        dialog._updating_member_tree = False
        dialog.member_tree_selection = Mock()

        dialog._refresh_member_tree()

        self.assertIn("group_excluded", dialog.member_tree.rows)
        self.assertEqual(
            dialog.member_tree.rows["group_excluded"]["text"],
            "已排除來源（1）",
        )
        child = next(
            row
            for row in dialog.member_tree.rows.values()
            if row["parent"] == "group_excluded"
        )
        self.assertIn("已排除-S1", child["text"])
        self.assertEqual(child["tags"], ("excluded",))

    def test_excluded_source_is_muted_drawable_and_focusable_when_source_hidden(self):
        baseline = self.convert()
        source = baseline.struts[0]
        exclusion = ExcludedSource("strut", source.source_handles)
        result = replace(baseline, excluded_sources=(exclusion,))
        handle = source.source_handles[0]
        geometry = next(
            item
            for item in result.source_geometry
            if item.role == "strut" and item.source_handle == handle
        )

        visible = DXFImportDialog._visible_preview_source_geometry(
            result,
            show_source=False,
            show_auxiliary=False,
            focus_handles=(handle,),
        )
        self.assertIn(geometry, visible)

        canvas = _PreviewCanvas()
        scene = PreviewScene()
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = result
        dialog.preview_renderer = PreviewRenderer(canvas, scene)
        dialog.preview_viewport = _IdentityViewport()
        dialog.focus_handles = set()
        dialog.problem_records = ()
        dialog._draw_source_geometry_layer((geometry,))
        muted = canvas.items[scene.source_handle_items[handle][0]]
        self.assertEqual(muted["fill"], "#78909c")
        self.assertEqual(muted["width"], 2)
        self.assertEqual(muted["dash"], (2, 5))

        focused_canvas = _PreviewCanvas()
        focused_scene = PreviewScene()
        dialog.preview_renderer = PreviewRenderer(focused_canvas, focused_scene)
        dialog.focus_handles = {handle}
        dialog._draw_source_geometry_layer((geometry,))
        focused = focused_canvas.items[focused_scene.source_handle_items[handle][0]]
        self.assertEqual(focused["fill"], "#1565c0")
        self.assertEqual(focused["width"], 4)
        self.assertEqual(focused["dash"], (2, 5))

    def test_pending_source_uses_distinct_overlay_without_changing_result(self):
        baseline = self.convert()
        source = baseline.struts[0]
        handle = source.source_handles[0]
        pending_source = ExcludedSource(
            "strut",
            source.source_handles,
            source_layers=(source.source_layer,),
            display_id_when_excluded=source.id,
        )
        draft = PendingSourceExclusionDraft(
            0,
            baseline.source_fingerprint,
            1,
            (pending_source,),
            "ACTIVE",
        )
        geometry = next(
            item
            for item in baseline.source_geometry
            if item.role == "strut" and item.source_handle == handle
        )
        canvas = _PreviewCanvas()
        scene = PreviewScene()
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = baseline
        dialog.review_workflow = SimpleNamespace(
            pending_source_exclusion_draft=draft
        )
        dialog.preview_renderer = PreviewRenderer(canvas, scene)
        dialog.preview_viewport = _IdentityViewport()
        dialog.focus_handles = set()
        dialog.problem_records = ()

        dialog._draw_source_geometry_layer((geometry,))

        overlay = canvas.items[scene.source_handle_items[handle][0]]
        self.assertEqual(overlay["fill"], "#f9a825")
        self.assertEqual(overlay["width"], 3)
        self.assertEqual(overlay["dash"], (8, 4))
        self.assertEqual(baseline.excluded_sources, ())

    def test_source_exclusion_effects_choose_partial_layers_and_preserve_viewport(self):
        baseline = self.convert()
        handle = baseline.struts[0].source_handles[0]
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = baseline
        dialog.review_workflow = SimpleNamespace(revision=8)
        dialog.preview_renderer = object()
        dialog.preview_transform = (1.0, 1.0, 0.0, 0.0, 1.0)
        dialog._preview_scene_revision = 7
        dialog._preview_source_geometry_signature = (
            dialog._dialog_source_geometry_signature(baseline)
        )
        dialog.preview_scene = PreviewScene(
            source_handle_items={handle: [42]},
        )
        dialog._pending_source_style_handles = set()
        dialog.preview_viewport = _IdentityViewport()
        dialog._invalidate_error_source_hit_index = Mock()
        dialog.preview_view_bounds = (10.0, 20.0, 30.0, 40.0)
        dialog._preview_intersects = Mock(return_value=True)
        effects = ReviewMutationEffects(
            committed_revision=8,
            changed_source_handles=(handle,),
            engineering_members_changed=True,
            problems_changed=True,
            candidate_points_changed=True,
            selection_targets_invalidated=True,
            hit_index_invalidated=True,
        )

        dirty = dialog._source_exclusion_render_dirty(effects)

        self.assertFalse(dirty & RenderDirty.FULL_SCENE)
        self.assertTrue(dirty & RenderDirty.SOURCE_STYLE)
        self.assertTrue(dirty & RenderDirty.COMPONENT_LAYER)
        self.assertTrue(dirty & RenderDirty.CANDIDATE_LAYER)
        self.assertEqual(dialog._pending_source_style_handles, {handle})
        self.assertEqual(dialog.preview_view_bounds, (10.0, 20.0, 30.0, 40.0))

    def test_source_style_patch_matches_full_draw_without_rebuilding_other_source(self):
        baseline = self.convert()
        source = baseline.struts[0]
        handle = source.source_handles[0]
        geometries = tuple(
            geometry
            for geometry in baseline.source_geometry
            if geometry.role != "ignore"
        )
        other = next(
            geometry for geometry in geometries
            if geometry.source_handle != handle
        )
        selected = tuple(
            geometry for geometry in geometries
            if geometry.source_handle == handle
        )
        excluded = replace(
            baseline,
            excluded_sources=(ExcludedSource("strut", source.source_handles),),
        )

        canvas = _PreviewCanvas()
        scene = PreviewScene()
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = baseline
        dialog.preview_renderer = PreviewRenderer(canvas, scene)
        dialog.preview_viewport = _IdentityViewport()
        dialog.focus_handles = set()
        dialog.problem_records = ()
        dialog._draw_source_geometry_layer((*selected, other))
        untouched_ids = tuple(scene.source_handle_items[other.source_handle])

        dialog.result = excluded
        dialog.preview_renderer.delete_source_handles((handle,))
        dialog._draw_source_geometry_layer(selected)
        patched = canvas.items[scene.source_handle_items[handle][-1]]

        full_canvas = _PreviewCanvas()
        full_scene = PreviewScene()
        dialog.preview_renderer = PreviewRenderer(full_canvas, full_scene)
        dialog._draw_source_geometry_layer((*selected, other))
        full = full_canvas.items[full_scene.source_handle_items[handle][-1]]

        self.assertEqual(
            {key: patched.get(key) for key in ("fill", "width", "dash")},
            {key: full.get(key) for key in ("fill", "width", "dash")},
        )
        self.assertEqual(tuple(scene.source_handle_items[other.source_handle]), untouched_ids)
        self.assertTrue(all(item_id in canvas.items for item_id in untouched_ids))

    def test_source_partial_refresh_falls_back_when_visible_handle_index_is_missing(self):
        baseline = self.convert()
        handle = baseline.struts[0].source_handles[0]
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = baseline
        dialog.review_workflow = SimpleNamespace(revision=3)
        dialog.preview_renderer = object()
        dialog.preview_transform = (1.0, 1.0, 0.0, 0.0, 1.0)
        dialog._preview_scene_revision = 2
        dialog._preview_source_geometry_signature = (
            dialog._dialog_source_geometry_signature(baseline)
        )
        dialog.preview_scene = PreviewScene()
        dialog._pending_source_style_handles = set()
        dialog._preview_intersects = Mock(return_value=True)

        dirty = dialog._source_exclusion_render_dirty(
            ReviewMutationEffects(
                committed_revision=3,
                changed_source_handles=(handle,),
            )
        )

        self.assertEqual(dirty, RenderDirty.FULL_SCENE)

    def test_excluded_unresolved_source_is_removed_from_click_hit_index(self):
        baseline = self.convert()
        geometry = next(
            value for value in baseline.source_geometry
            if len(value.points) >= 2 and value.role != "ignore"
        )
        item = _review_item(
            "unresolved:test:HIT",
            "待修-HIT",
            geometry.role,
            "unresolved",
            (geometry.source_handle,),
        )
        item = replace(item, highest_severity="error")
        viewport = _IdentityViewport()
        viewport.set_view_bounds((-10000.0, 10000.0, -10000.0, 10000.0))
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = baseline
        dialog.review_items = (item,)
        dialog.review_item_by_key = {item.key: item}
        dialog.preview_viewport = viewport
        dialog._preview_render_generation = 4
        dialog.focus_handles = set()
        dialog.selection_state = SelectionState()
        dialog.canvas_candidate_hit_points = []
        dialog.canvas_member_hit_lines = []
        dialog._pending_endpoint_hits = Mock(return_value=())
        dialog._preview_candidate_hits = Mock(return_value=())
        dialog._nearest_preview_member = Mock(return_value="")
        dialog._select_unresolved_review_item = Mock()
        midpoint = (
            (geometry.points[0][0] + geometry.points[1][0]) / 2.0,
            (geometry.points[0][1] + geometry.points[1][1]) / 2.0,
        )
        event = SimpleNamespace(x=midpoint[0], y=midpoint[1])

        dialog._on_canvas_click(event)
        dialog._select_unresolved_review_item.assert_called_once_with(
            item,
            source="canvas",
        )

        dialog._select_unresolved_review_item.reset_mock()
        excluded_item = replace(item, status="excluded")
        dialog.result = replace(
            baseline,
            excluded_sources=(
                ExcludedSource(geometry.role, (geometry.source_handle,)),
            ),
        )
        dialog.review_items = (excluded_item,)
        dialog.review_item_by_key = {excluded_item.key: excluded_item}
        dialog._on_canvas_click(event)

        dialog._select_unresolved_review_item.assert_not_called()
        self.assertEqual(dialog._error_source_hits(midpoint), ())

    def test_hidden_debug_invalidation_does_not_serialize(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.developer_expanded = False
        dialog._debug_payload_dirty = False
        dialog._refresh_debug_payload = Mock()

        dialog._invalidate_debug_payload()

        self.assertTrue(dialog._debug_payload_dirty)
        dialog._refresh_debug_payload.assert_not_called()

    def test_debug_payload_is_built_for_current_revision_and_cached(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = workflow
        dialog.debug_text = Mock()
        dialog._debug_payload_dirty = True
        dialog._debug_payload_revision = None
        dialog._debug_payload_text = ""

        self.assertTrue(dialog._refresh_debug_payload())
        first_text = dialog._debug_payload_text
        self.assertIn(f'"review_revision": {workflow.revision}', first_text)
        self.assertIn('"manual_replay"', first_text)
        dialog.debug_text.reset_mock()
        self.assertTrue(dialog._refresh_debug_payload())
        dialog.debug_text.insert.assert_not_called()

        source = baseline.struts[0]
        stage = workflow.plan_source_exclusion_change(
            (ExcludedSource("strut", source.source_handles),)
        )
        workflow.commit_source_exclusion_plan(stage)
        dialog._invalidate_debug_payload()
        self.assertTrue(dialog._refresh_debug_payload())
        self.assertEqual(dialog._debug_payload_revision, workflow.revision)
        self.assertIn(source.source_handles[0], dialog._debug_payload_text)

    def test_debug_payload_retries_if_revision_changes_while_serializing(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = workflow
        dialog.debug_text = Mock()
        dialog._debug_payload_dirty = True
        dialog._debug_payload_revision = None
        dialog._debug_payload_text = ""
        original = workflow.result
        assert original is not None
        calls = 0

        def serialize_with_one_concurrent_commit():
            nonlocal calls
            calls += 1
            if calls == 1:
                workflow.revision += 1
            return original.to_debug_dict()

        workflow.result = Mock(wraps=original)
        workflow.result.to_debug_dict.side_effect = serialize_with_one_concurrent_commit

        self.assertTrue(dialog._refresh_debug_payload())

        self.assertEqual(calls, 2)
        self.assertEqual(dialog._debug_payload_revision, workflow.revision)

    def test_debug_failure_does_not_change_committed_workflow_and_stays_dirty(self):
        baseline = self.convert()
        workflow = DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=baseline,
        )
        before = workflow.snapshot
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = workflow
        dialog.debug_text = Mock()
        dialog.debug_text.insert.side_effect = RuntimeError("widget failed")
        dialog.status_var = Mock()
        dialog._debug_payload_dirty = True
        dialog._debug_payload_revision = None
        dialog._debug_payload_text = ""

        self.assertFalse(dialog._refresh_debug_payload())

        self.assertEqual(workflow.snapshot, before)
        self.assertTrue(dialog._debug_payload_dirty)
        self.assertIsNone(dialog._debug_payload_revision)

    def test_fingerprint_mismatch_notice_is_shown_once(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.exclusion_fingerprint_mismatch = True
        dialog._exclusion_fingerprint_notice_shown = False
        dialog.window = None

        with patch("tkinter.messagebox.showwarning") as showwarning:
            dialog._show_exclusion_fingerprint_notice()
            dialog._show_exclusion_fingerprint_notice()

        showwarning.assert_called_once()
        self.assertTrue(dialog._exclusion_fingerprint_notice_shown)

    def test_single_source_action_marks_without_recognition_or_confirmation(self):
        item = _review_item(
            "member:strut:S1", "S1", "strut", "recognized", ("H1",), member_id="S1"
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_item_by_key = {item.key: item}
        dialog.selected_review_item_key = item.key
        dialog.review_items = (item,)
        dialog.excluded_sources = ()
        dialog.world_result = Mock()
        dialog.window = None
        dialog.source_exclusion_status_var = Mock()
        dialog.review_workflow = Mock()
        dialog.review_workflow.source_exclusion_disabled_reason.return_value = ""
        dialog.review_workflow.pending_source_exclusion_contains.return_value = False
        dialog._commit_source_exclusion_stage = Mock()
        dialog._selected_review_item = Mock(return_value=item)
        dialog._sync_review_workflow_state = Mock()
        dialog._refresh_pending_source_visuals = Mock()
        dialog._update_selected_member_panel = Mock()

        with patch("tkinter.messagebox.askyesno") as askyesno:
            dialog._on_source_exclusion_action()

        dialog.review_workflow.mark_source_exclusion.assert_called_once_with(item)
        dialog.review_workflow.plan_source_exclusion_for_item.assert_not_called()
        dialog._commit_source_exclusion_stage.assert_not_called()
        askyesno.assert_not_called()
        self.assertEqual(dialog.excluded_sources, ())

    def test_marking_exception_does_not_commit_or_change_exclusions(self):
        item = _review_item(
            "member:strut:S1", "S1", "strut", "recognized", ("H1",), member_id="S1"
        )
        original = (ExcludedSource("beam", ("H2",)),)
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_items = (item,)
        dialog.excluded_sources = original
        dialog.world_result = Mock()
        dialog.window = None
        dialog._selected_review_item = Mock(return_value=item)
        dialog.review_workflow = Mock()
        dialog.review_workflow.source_exclusion_disabled_reason.return_value = ""
        dialog.review_workflow.pending_source_exclusion_contains.return_value = False
        dialog.review_workflow.mark_source_exclusion = Mock(
            side_effect=RuntimeError("technical failure")
        )
        dialog._commit_source_exclusion_stage = Mock()

        with patch("tkinter.messagebox.showerror"):
            dialog._on_source_exclusion_action()

        dialog._commit_source_exclusion_stage.assert_not_called()
        self.assertEqual(dialog.excluded_sources, original)

    def test_cancelled_aggregate_impact_keeps_draft_and_cancels_plan(self):
        source = ExcludedSource("strut", ("H1",), display_id_when_excluded="S1")
        draft = PendingSourceExclusionDraft(
            3,
            "fingerprint",
            2,
            (source,),
            "ACTIVE",
        )
        plan = Mock(spec=SourceExclusionPlan)
        workflow = Mock()
        workflow.pending_source_exclusion_draft = draft
        workflow.plan_pending_source_exclusions.return_value = plan
        workflow.confirmed_snapshot.return_value = {}
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = workflow
        dialog.result = Mock(spec=DXFImportResult)
        dialog.window = None
        dialog._pending_review_item = Mock(return_value=None)
        dialog._refresh_pending_source_exclusion_controls = Mock()
        dialog._format_pending_source_exclusion_impact = Mock(
            return_value="aggregate impact"
        )
        dialog._commit_source_exclusion_stage = Mock()

        with patch("tkinter.messagebox.askyesno", return_value=False):
            dialog._apply_pending_source_exclusions()

        workflow.cancel_pending_source_exclusion_plan.assert_called_once_with(plan)
        dialog._commit_source_exclusion_stage.assert_not_called()
        self.assertEqual(workflow.pending_source_exclusion_draft, draft)

    def test_aggregate_impact_format_failure_keeps_draft_and_cancels_plan(self):
        source = ExcludedSource("strut", ("H1",), display_id_when_excluded="S1")
        draft = PendingSourceExclusionDraft(
            3,
            "fingerprint",
            2,
            (source,),
            "ACTIVE",
        )
        plan = Mock(spec=SourceExclusionPlan)
        workflow = Mock()
        workflow.pending_source_exclusion_draft = draft
        workflow.plan_pending_source_exclusions.return_value = plan
        workflow.confirmed_snapshot.return_value = {}
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = workflow
        dialog.result = Mock(spec=DXFImportResult)
        dialog.window = None
        dialog._pending_review_item = Mock(return_value=None)
        dialog._refresh_pending_source_exclusion_controls = Mock()
        dialog._format_pending_source_exclusion_impact = Mock(
            side_effect=RuntimeError("format failed")
        )
        dialog._commit_source_exclusion_stage = Mock()

        with patch("tkinter.messagebox.showerror") as showerror:
            dialog._apply_pending_source_exclusions()

        workflow.cancel_pending_source_exclusion_plan.assert_called_once_with(plan)
        dialog._commit_source_exclusion_stage.assert_not_called()
        showerror.assert_called_once()
        self.assertEqual(workflow.pending_source_exclusion_draft, draft)

    def test_confirmed_aggregate_impact_commits_the_same_plan_once(self):
        source = ExcludedSource("strut", ("H1",), display_id_when_excluded="S1")
        draft = PendingSourceExclusionDraft(
            3,
            "fingerprint",
            2,
            (source,),
            "ACTIVE",
        )
        plan = Mock(spec=SourceExclusionPlan)
        workflow = Mock()
        workflow.pending_source_exclusion_draft = draft
        workflow.plan_pending_source_exclusions.return_value = plan
        workflow.confirmed_snapshot.return_value = {}
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = workflow
        dialog.result = Mock(spec=DXFImportResult)
        dialog.window = None
        dialog.source_exclusion_status_var = Mock()
        dialog._pending_review_item = Mock(return_value=None)
        dialog._refresh_pending_source_exclusion_controls = Mock()
        dialog._format_pending_source_exclusion_impact = Mock(
            return_value=(
                "以下為所有待排除來源合併後的結果\n"
                "若結果不如預期，可取消個別待排除後重新套用"
            )
        )
        dialog._stage_review_item_for_identity = Mock(return_value=None)
        dialog._commit_source_exclusion_stage = Mock()

        with patch("tkinter.messagebox.askyesno", return_value=True):
            dialog._apply_pending_source_exclusions()

        workflow.plan_pending_source_exclusions.assert_called_once()
        dialog._commit_source_exclusion_stage.assert_called_once_with(
            plan,
            "",
            initiating_member_ids=(),
        )
        workflow.cancel_pending_source_exclusion_plan.assert_not_called()

    def test_dialog_discard_clears_only_pending_intent(self):
        workflow = Mock()
        workflow.pending_source_exclusion_draft = PendingSourceExclusionDraft(
            3,
            "fingerprint",
            2,
            (ExcludedSource("strut", ("H1",)),),
            "ACTIVE",
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = workflow
        dialog.source_exclusion_status_var = Mock()
        dialog._sync_review_workflow_state = Mock()
        dialog._refresh_pending_source_visuals = Mock()
        dialog._update_selected_member_panel = Mock()

        dialog._discard_pending_source_exclusions()

        workflow.discard_pending_source_exclusions.assert_called_once()
        workflow.plan_pending_source_exclusions.assert_not_called()
        workflow.commit_source_exclusion_plan.assert_not_called()

    def test_pending_draft_blocks_pause_and_complete_actions(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.window = None
        dialog.review_workflow = SimpleNamespace(
            pending_mutation_disabled_reason=lambda: "請先套用或捨棄待排除來源"
        )
        dialog._build_review_state = Mock()

        with patch("tkinter.messagebox.showwarning") as showwarning:
            dialog._pause()
            dialog._apply()

        self.assertEqual(showwarning.call_count, 2)
        dialog._build_review_state.assert_not_called()

    def test_close_requires_explicit_discard_before_pause(self):
        workflow = Mock()
        workflow.pending_mutation_disabled_reason.return_value = (
            "請先套用或捨棄待排除來源"
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.window = None
        dialog.allow_pause = True
        dialog.review_workflow = workflow
        dialog._sync_review_workflow_state = Mock()
        dialog._pause = Mock()

        with patch("tkinter.messagebox.askyesno", return_value=False):
            dialog._close_dialog()
        workflow.discard_pending_source_exclusions.assert_not_called()
        dialog._pause.assert_not_called()

        with patch("tkinter.messagebox.askyesno", return_value=True):
            dialog._close_dialog()
        workflow.discard_pending_source_exclusions.assert_called_once()
        dialog._sync_review_workflow_state.assert_called_once()
        dialog._pause.assert_called_once()


class ExplicitReviewOverridePersistenceTests(unittest.TestCase):
    @staticmethod
    def provisional_waler_result(*, excluded_sources=()):
        waler = Waler(
            "W14",
            (0.0, 0.0),
            (1000.0, 0.0),
            "WALER",
            ("58D",),
            ("LWPOLYLINE",),
            "closed_outline_axis",
            True,
            400.0,
            0.9,
            contact_face_state="provisional",
            source_width_state="unique",
        )
        return DXFImportResult(
            source_path="Y29.dxf",
            layer_names=("WALER",),
            selected_layers={"waler": ("WALER",)},
            layer_info=(),
            walers=(waler,),
            struts=(),
            braces=(),
            entity_debug=(),
            messages=(),
            source_entity_counts={},
            excluded_sources=tuple(excluded_sources),
        )

    def test_waler_formalization_flag_requires_complete_manual_waler_line(self):
        state = {
            "manual_overrides": [
                {
                    "role": "waler",
                    "source_handles": ["58d"],
                    "geometry_selection_source": "cad_manual",
                    "world_start": [10.0, 20.0],
                    "world_end": [30.0, 40.0],
                    "waler_engineering_line_formalized": True,
                },
                {
                    "role": "strut",
                    "source_handles": ["S1"],
                    "geometry_selection_source": "cad_manual",
                    "world_start": [0.0, 0.0],
                    "world_end": [0.0, 100.0],
                    "waler_engineering_line_formalized": True,
                },
                {
                    "role": "waler",
                    "source_handles": ["W2"],
                    "waler_engineering_line_formalized": True,
                },
            ],
        }

        restored = manual_overrides_from_review_state(state)

        self.assertTrue(restored[0].waler_engineering_line_formalized)
        self.assertFalse(restored[1].waler_engineering_line_formalized)
        self.assertFalse(restored[2].waler_engineering_line_formalized)
        self.assertFalse(
            SourceManualOverride("waler", ("58D",)).waler_engineering_line_formalized
        )

    def test_waler_formalization_flag_round_trips_through_mapping(self):
        original = SourceManualOverride(
            role="waler",
            source_handles=("58D",),
            geometry_selection_source="manual_candidate_points",
            world_start=(10.0, 20.0),
            world_end=(30.0, 40.0),
            waler_engineering_line_formalized=True,
        )

        restored = manual_overrides_from_review_state(
            {"manual_overrides": [asdict(original)]}
        )

        self.assertEqual(restored, (original,))

    def test_capture_and_replay_preserve_explicit_waler_formalization(self):
        formal = formalize_waler_engineering_line(
            self.provisional_waler_result(),
            ("58D",),
            (0.0, 50.0),
            (1000.0, 50.0),
            input_kind="cad_manual",
        )

        overrides = capture_manual_overrides(formal)
        replayed, report = replay_manual_overrides(
            self.provisional_waler_result(),
            overrides,
        )

        self.assertEqual(len(overrides), 1)
        self.assertTrue(overrides[0].waler_engineering_line_formalized)
        self.assertEqual(replayed.walers[0].contact_face_state, "formal")
        self.assertEqual(
            replayed.walers[0].engineering_line_authority,
            "manual_repair",
        )
        self.assertEqual(report.preserved, ("W14 人工正式工程線",))

    def test_legacy_geometry_override_does_not_gain_formal_authority(self):
        override = SourceManualOverride(
            role="waler",
            source_handles=("58D",),
            display_id="W14",
            geometry_selection_source="cad_manual",
            world_start=(0.0, 50.0),
            world_end=(1000.0, 50.0),
        )

        replayed, report = replay_manual_overrides(
            self.provisional_waler_result(),
            (override,),
        )

        self.assertEqual(replayed.walers[0].contact_face_state, "provisional")
        self.assertEqual(replayed.walers[0].engineering_line_authority, "automatic")
        self.assertEqual(report.preserved, ("W14 CAD 工程線",))

    def test_excluded_waler_disables_formalization_replay(self):
        override = SourceManualOverride(
            role="waler",
            source_handles=("58D",),
            display_id="W14",
            geometry_selection_source="cad_manual",
            world_start=(0.0, 50.0),
            world_end=(1000.0, 50.0),
            waler_engineering_line_formalized=True,
        )
        excluded = ExcludedSource(
            role="waler",
            source_handles=("58D",),
        )

        replayed, report = replay_manual_overrides(
            self.provisional_waler_result(excluded_sources=(excluded,)),
            (override,),
        )

        self.assertEqual(replayed.walers[0].contact_face_state, "provisional")
        self.assertEqual(report.disabled, ("W14 人工正式工程線",))

    def test_brace_baseline_coordinate_marker_is_optional_in_version_two(self):
        state = {
            "review_state_version": 2,
            "manual_overrides": [
                {
                    "role": "brace",
                    "source_handles": ["B1"],
                    "geometry_selection_source": "cad_manual",
                    "geometry_coordinate_space": "baseline_wcs",
                    "world_start": [10.0, 20.0],
                    "world_end": [30.0, 40.0],
                },
                {
                    "role": "brace",
                    "source_handles": ["B2"],
                    "geometry_selection_source": "cad_manual",
                    "world_start": [50.0, 60.0],
                    "world_end": [70.0, 80.0],
                },
                {
                    "role": "strut",
                    "source_handles": ["S1"],
                    "geometry_selection_source": "cad_manual",
                    "geometry_coordinate_space": "baseline_wcs",
                    "world_start": [0.0, 0.0],
                    "world_end": [0.0, 100.0],
                },
            ],
        }

        restored = manual_overrides_from_review_state(state)

        self.assertEqual(restored[0].geometry_coordinate_space, "baseline_wcs")
        self.assertEqual(restored[1].geometry_coordinate_space, "")
        self.assertEqual(restored[2].geometry_coordinate_space, "")
        self.assertEqual(state["review_state_version"], 2)

    def test_explicit_manual_override_is_preferred_over_derived_snapshot(self):
        state = {
            "manual_overrides": [{
                "role": "strut",
                "source_handles": ["aa", "BB"],
                "display_id": "S9",
                "has_material_spec": True,
                "material_spec": "H350",
                "geometry_selection_source": "cad_manual",
                "world_start": [10.0, 20.0],
                "world_end": [30.0, 40.0],
            }],
            "converted": {"struts": []},
        }

        restored = manual_overrides_from_review_state(state)

        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].source_handles, ("AA", "BB"))
        self.assertEqual(restored[0].geometry_selection_source, "cad_manual")
        self.assertEqual(restored[0].world_start, (10.0, 20.0))
        self.assertEqual(restored[0].material_spec, "H350")


if __name__ == "__main__":
    unittest.main()
