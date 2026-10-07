from __future__ import annotations

import json
import inspect
import tomllib
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, call, patch

from bracing_optimizer.application.software_information import (
    HISTORY_UNAVAILABLE_MESSAGE,
    SoftwareHistoryEntry,
    SoftwareHistoryLoadResult,
    SoftwareInformation,
)
from bracing_optimizer.product_metadata import PRODUCT_IDENTITY
from bracing_optimizer.infrastructure.software_history import (
    SOFTWARE_HISTORY_SOURCE_HEADING,
    SoftwareHistoryRepository,
)
from bracing_optimizer.presentation.dialogs import software_information_dialog
from bracing_optimizer.presentation.dialogs.software_information_dialog import (
    SoftwareInformationDialog,
    format_history_text,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORY_HEADING = "起始歷史紀錄（截至 2026/09/28 早上）"
HISTORY_RESOURCE_PATH = PROJECT_ROOT / "assets" / "software_history.json"
DEVELOPMENT_HISTORY_PATH = PROJECT_ROOT / "docs" / "DEVELOPMENT_HISTORY.md"


def _initial_history_rows() -> list[tuple[str, str]]:
    lines = DEVELOPMENT_HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"## {HISTORY_HEADING}")
    end = next(
        index
        for index in range(start + 1, len(lines))
        if lines[index].startswith("## ")
    )
    rows: list[tuple[str, str]] = []
    for line in lines[start + 1 : end]:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 2 or cells[0] in {"日期", "---"}:
            continue
        rows.append((cells[0], cells[1]))
    return rows


class ProductMetadataTests(unittest.TestCase):
    def test_runtime_identity_has_the_approved_release_values(self):
        self.assertEqual("SupportOptimizer", PRODUCT_IDENTITY.name)
        self.assertEqual("3.0.0", PRODUCT_IDENTITY.version)
        self.assertEqual("莊竣安（Chuang Chun An）", PRODUCT_IDENTITY.author)
        self.assertNotIn("schema", PRODUCT_IDENTITY.version.lower())
        self.assertNotIn("dxf", PRODUCT_IDENTITY.version.lower())
        self.assertNotIn("solver", PRODUCT_IDENTITY.version.lower())

    def test_runtime_identity_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            PRODUCT_IDENTITY.version = "9.9.9"

    def test_runtime_version_matches_pyproject(self):
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)["project"]
        self.assertEqual(project["version"], PRODUCT_IDENTITY.version)


class SoftwareInformationContractTests(unittest.TestCase):
    def test_available_and_unavailable_history_keep_product_identity(self):
        available = SoftwareInformation(
            identity=PRODUCT_IDENTITY,
            history=SoftwareHistoryLoadResult(
                available=True,
                entries=(SoftwareHistoryEntry("日期", "紀錄"),),
            ),
        )
        unavailable = SoftwareInformation(
            identity=PRODUCT_IDENTITY,
            history=SoftwareHistoryLoadResult(
                available=False,
                message=HISTORY_UNAVAILABLE_MESSAGE,
            ),
        )

        self.assertIs(PRODUCT_IDENTITY, available.identity)
        self.assertIs(PRODUCT_IDENTITY, unavailable.identity)
        self.assertTrue(available.history.available)
        self.assertFalse(unavailable.history.available)

    def test_packaged_history_is_an_exact_initial_history_projection(self):
        payload = json.loads(HISTORY_RESOURCE_PATH.read_text(encoding="utf-8"))
        actual_rows = [
            (entry["date_label"], entry["record"])
            for entry in payload["entries"]
        ]

        self.assertEqual(1, payload["schema_version"])
        self.assertEqual(HISTORY_HEADING, payload["source_heading"])
        self.assertEqual(_initial_history_rows(), actual_rows)
        self.assertGreater(len(actual_rows), 0)

    def test_packaged_history_excludes_other_document_sections(self):
        resource_text = HISTORY_RESOURCE_PATH.read_text(encoding="utf-8")
        for excluded_heading in (
            "Codex／OpenSpec 封存紀錄",
            "人工補充紀錄",
            "AI 對話統計（截至 2026/09/28 早上）",
        ):
            with self.subTest(heading=excluded_heading):
                self.assertNotIn(excluded_heading, resource_text)


class SoftwareHistoryRepositoryTests(unittest.TestCase):
    def _write_payload(self, root: Path, payload: object) -> Path:
        path = root / "software_history.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def _valid_payload(self, entries: list[dict] | None = None) -> dict:
        return {
            "schema_version": 1,
            "source_heading": SOFTWARE_HISTORY_SOURCE_HEADING,
            "entries": entries
            or [
                {"date_label": "2026/10 下旬", "record": "較晚但列在前面"},
                {"date_label": "不是 ISO 日期", "record": "維持來源順序"},
            ],
        }

    def test_loader_preserves_non_iso_labels_and_source_order(self):
        with TemporaryDirectory() as temp_dir:
            path = self._write_payload(Path(temp_dir), self._valid_payload())
            result = SoftwareHistoryRepository(path).load()

        self.assertTrue(result.available)
        self.assertEqual(
            ("2026/10 下旬", "不是 ISO 日期"),
            tuple(entry.date_label for entry in result.entries),
        )
        self.assertIsNone(result.message)

    def test_real_resource_loads_every_projected_entry_in_order(self):
        payload = json.loads(HISTORY_RESOURCE_PATH.read_text(encoding="utf-8"))
        result = SoftwareHistoryRepository(HISTORY_RESOURCE_PATH).load()

        self.assertTrue(result.available)
        self.assertEqual(
            [entry["date_label"] for entry in payload["entries"]],
            [entry.date_label for entry in result.entries],
        )
        self.assertEqual(
            [entry["record"] for entry in payload["entries"]],
            [entry.record for entry in result.entries],
        )

    def test_missing_resource_returns_safe_fallback_and_keeps_identity(self):
        information = SoftwareInformation(
            identity=PRODUCT_IDENTITY,
            history=SoftwareHistoryRepository(PROJECT_ROOT / "missing.json").load(),
        )

        self.assertIs(PRODUCT_IDENTITY, information.identity)
        self.assertFalse(information.history.available)
        self.assertEqual(HISTORY_UNAVAILABLE_MESSAGE, information.history.message)
        self.assertEqual((), information.history.entries)

    def test_io_error_returns_safe_fallback(self):
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            result = SoftwareHistoryRepository("software_history.json").load()

        self.assertFalse(result.available)
        self.assertEqual(HISTORY_UNAVAILABLE_MESSAGE, result.message)

    def test_malformed_json_returns_safe_fallback(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "software_history.json"
            path.write_text("{not-json", encoding="utf-8")
            result = SoftwareHistoryRepository(path).load()

        self.assertFalse(result.available)
        self.assertEqual(HISTORY_UNAVAILABLE_MESSAGE, result.message)

    def test_invalid_utf8_returns_safe_fallback(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "software_history.json"
            path.write_bytes(b"\xff")
            result = SoftwareHistoryRepository(path).load()

        self.assertFalse(result.available)
        self.assertEqual(HISTORY_UNAVAILABLE_MESSAGE, result.message)

    def test_unknown_schema_returns_safe_fallback(self):
        with TemporaryDirectory() as temp_dir:
            payload = self._valid_payload()
            payload["schema_version"] = 2
            path = self._write_payload(Path(temp_dir), payload)
            result = SoftwareHistoryRepository(path).load()

        self.assertFalse(result.available)
        self.assertEqual(HISTORY_UNAVAILABLE_MESSAGE, result.message)

    def test_invalid_entries_return_safe_fallback(self):
        invalid_entries = (
            [],
            ["not-an-object"],
            [{"date_label": "", "record": "紀錄"}],
            [{"date_label": "日期", "record": ""}],
            [{"date_label": "日期", "record": "紀錄", "extra": True}],
        )
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index, entries in enumerate(invalid_entries):
                with self.subTest(entries=entries):
                    payload = self._valid_payload(entries=[{"unused": index}])
                    payload["entries"] = entries
                    path = self._write_payload(root, payload)
                    result = SoftwareHistoryRepository(path).load()
                    self.assertFalse(result.available)
                    self.assertEqual(HISTORY_UNAVAILABLE_MESSAGE, result.message)


class SoftwareInformationDialogTests(unittest.TestCase):
    def _information(self, *, available: bool = True) -> SoftwareInformation:
        history = (
            SoftwareHistoryLoadResult(
                available=True,
                entries=(
                    SoftwareHistoryEntry("第一筆日期", "第一筆紀錄"),
                    SoftwareHistoryEntry("最後一筆日期", "最後一筆紀錄"),
                ),
            )
            if available
            else SoftwareHistoryLoadResult(
                available=False,
                message=HISTORY_UNAVAILABLE_MESSAGE,
            )
        )
        return SoftwareInformation(identity=PRODUCT_IDENTITY, history=history)

    def test_history_text_contains_every_entry_in_source_order(self):
        rendered = format_history_text(self._information())

        self.assertEqual(
            "第一筆日期\n第一筆紀錄\n\n最後一筆日期\n最後一筆紀錄",
            rendered,
        )
        self.assertLess(rendered.index("第一筆日期"), rendered.index("最後一筆日期"))

    def test_history_text_uses_fixed_fallback(self):
        self.assertEqual(
            HISTORY_UNAVAILABLE_MESSAGE,
            format_history_text(self._information(available=False)),
        )

    def test_dialog_is_modal_scrollable_read_only_and_closeable(self):
        parent = object()
        top_level = MagicMock()
        history_widget = MagicMock()
        with (
            patch.object(
                software_information_dialog.tk,
                "Toplevel",
                return_value=top_level,
            ),
            patch.object(software_information_dialog.ttk, "Frame"),
            patch.object(software_information_dialog.ttk, "LabelFrame"),
            patch.object(software_information_dialog.ttk, "Label") as label,
            patch.object(software_information_dialog.ttk, "Button") as button,
            patch.object(
                software_information_dialog.scrolledtext,
                "ScrolledText",
                return_value=history_widget,
            ) as scrolled_text,
        ):
            dialog = SoftwareInformationDialog(parent, self._information())

        top_level.title.assert_called_once_with("軟體資訊")
        top_level.transient.assert_called_once_with(parent)
        top_level.grab_set.assert_called_once_with()
        top_level.bind.assert_called_once_with("<Escape>", dialog._close)
        label.assert_has_calls(
            [
                call(unittest.mock.ANY, text="軟體名稱：SupportOptimizer"),
                call(unittest.mock.ANY, text="版本：3.0.0"),
                call(
                    unittest.mock.ANY,
                    text="作者：莊竣安（Chuang Chun An）",
                ),
                call(unittest.mock.ANY, text="開發歷程"),
            ],
            any_order=True,
        )
        scrolled_text.assert_called_once_with(
            unittest.mock.ANY,
            wrap="word",
            height=22,
        )
        history_widget.insert.assert_called_once_with(
            "1.0",
            "第一筆日期\n第一筆紀錄\n\n最後一筆日期\n最後一筆紀錄",
        )
        history_widget.configure.assert_called_once_with(state="disabled")
        button.assert_called_once_with(
            unittest.mock.ANY,
            text="關閉",
            command=dialog._close,
        )

        dialog.open()
        top_level.wait_window.assert_called_once_with()
        dialog._close()
        top_level.destroy.assert_called_once_with()


class SoftwareInformationMainWiringTests(unittest.TestCase):
    def test_help_menu_is_always_available_and_does_not_join_project_state_updates(self):
        from main import SupportInputApp

        menu_source = inspect.getsource(SupportInputApp._build_project_menu_and_toolbar)
        state_source = inspect.getsource(SupportInputApp._update_project_action_states)

        self.assertIn('label="說明"', menu_source)
        self.assertIn('label="軟體資訊"', menu_source)
        self.assertIn("command=self._show_software_information", menu_source)
        self.assertNotIn("help_menu", state_source)

    def test_handler_opens_available_or_unavailable_information_without_project_changes(self):
        import main

        for dirty, reason, available in (
            (False, "", True),
            (True, "既有未儲存變更", False),
        ):
            with self.subTest(dirty=dirty, available=available):
                app = main.SupportInputApp.__new__(main.SupportInputApp)
                app.root = object()
                app.current_project_path = Path("project_cases/current.json")
                app.project_dirty = dirty
                app.project_dirty_reason = reason
                before = (
                    app.current_project_path,
                    app.project_dirty,
                    app.project_dirty_reason,
                )
                history = SoftwareHistoryLoadResult(
                    available=available,
                    entries=(SoftwareHistoryEntry("日期", "紀錄"),)
                    if available
                    else (),
                    message=None if available else HISTORY_UNAVAILABLE_MESSAGE,
                )

                with (
                    patch.object(main, "SoftwareHistoryRepository") as repository,
                    patch.object(main, "SoftwareInformationDialog") as dialog,
                ):
                    repository.return_value.load.return_value = history
                    app._show_software_information()

                repository.assert_called_once_with(
                    main.RESOURCE_DIR / "assets" / "software_history.json"
                )
                repository.return_value.load.assert_called_once_with()
                passed_information = dialog.call_args.args[1]
                self.assertIs(PRODUCT_IDENTITY, passed_information.identity)
                self.assertIs(history, passed_information.history)
                dialog.return_value.open.assert_called_once_with()
                self.assertEqual(
                    before,
                    (
                        app.current_project_path,
                        app.project_dirty,
                        app.project_dirty_reason,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
