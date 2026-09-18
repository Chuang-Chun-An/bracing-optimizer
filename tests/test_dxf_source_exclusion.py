import copy
import hashlib
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
from dxf_import.importer import DXFImporter
from dxf_import.material_recognition import set_member_material_spec
from dxf_import.models import (
    CoordinateSystem,
    ExcludedSource,
    ReviewItem,
    SourceManualOverride,
    apply_coordinate_system,
)
from dxf_import.preview import PreviewRenderer, PreviewScene
from dxf_import.review_workflow import DXFReviewWorkflow, SourceExclusionPlan
from dxf_import.source_exclusion import (
    canonical_source_identity,
    capture_manual_overrides,
    excluded_source_from_review_item,
    exclusions_from_review_state,
    manual_overrides_from_review_state,
    normalize_excluded_sources,
    normalize_source_handles,
    replay_manual_overrides,
    shared_handle_conflicts,
    source_file_fingerprint,
)
from dxf_import.validation import (
    build_problem_records,
    build_review_items,
    build_validation_overview,
)
from dxf_import.waler_contact_adjustment import apply_waler_contact_adjustment


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


class _IdentityViewport:
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
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((500, 0), (500, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((0, 0), (500, 500), dxfattribs={"layer": "CORNER"})
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

    def test_cancelled_confirmation_does_not_commit_staged_result(self):
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
        dialog.review_workflow = Mock()
        dialog.review_workflow.source_exclusion_disabled_reason.return_value = ""
        dialog.review_workflow.plan_source_exclusion_for_item.return_value = (
            Mock(spec=SourceExclusionPlan),
            False,
            "strut:H1",
        )
        dialog._format_source_exclusion_impact = Mock(return_value="impact")
        dialog._commit_source_exclusion_stage = Mock()
        dialog._selected_review_item = Mock(return_value=item)

        with patch("tkinter.messagebox.askyesno", return_value=False):
            dialog._on_source_exclusion_action()

        dialog._commit_source_exclusion_stage.assert_not_called()
        self.assertEqual(dialog.excluded_sources, ())

    def test_staging_exception_does_not_commit_or_change_exclusions(self):
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
        dialog.review_workflow.plan_source_exclusion_for_item = Mock(
            side_effect=RuntimeError("technical failure")
        )
        dialog._commit_source_exclusion_stage = Mock()

        with patch("tkinter.messagebox.showerror"):
            dialog._on_source_exclusion_action()

        dialog._commit_source_exclusion_stage.assert_not_called()
        self.assertEqual(dialog.excluded_sources, original)


class ExplicitReviewOverridePersistenceTests(unittest.TestCase):
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
