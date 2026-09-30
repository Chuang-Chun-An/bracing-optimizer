import tempfile
import unittest
from pathlib import Path

from tools.development_history import (
    MANAGED_END,
    MANAGED_START,
    PENDING_FILENAME,
    update_history_from_archive,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _history_document(*, managed: str = "目前尚無自動封存紀錄。") -> str:
    return (
        "# 開發歷程\n\n"
        "## Codex／OpenSpec 封存紀錄\n\n"
        f"{MANAGED_START}\n\n{managed}\n\n{MANAGED_END}\n\n"
        "## 人工補充紀錄\n\n人工內容不得修改。\n\n"
        "## 起始歷史紀錄（截至 2026/09/28 早上）\n\n基準內容不得修改。\n"
    )


class DevelopmentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temporary_directory.name)
        self.history_path = self.repo_root / "docs" / "DEVELOPMENT_HISTORY.md"
        self.history_path.parent.mkdir(parents=True)
        self.history_path.write_text(_history_document(), encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _archive(self, name: str, *, change_text: str) -> Path:
        archive = self.repo_root / "openspec" / "changes" / "archive" / name
        capability = archive / "specs" / "sample-capability"
        capability.mkdir(parents=True)
        (archive / "proposal.md").write_text(
            "# Proposal\n\n## What Changes\n\n"
            f"- {change_text}\n"
            "- 保留既有行為。\n\n## Capabilities\n",
            encoding="utf-8",
        )
        (capability / "spec.md").write_text("# Spec Delta\n", encoding="utf-8")
        return archive

    def _update(self, archive: Path):
        return update_history_from_archive(
            archive,
            self.history_path,
            repo_root=self.repo_root,
            verification_status="focused tests passed",
            spec_status="synced",
        )

    def test_new_archives_are_inserted_first_and_preserve_manual_content(self):
        older = self._archive(
            "2026-09-28-older-change", change_text="完成較早的變更。"
        )
        newer = self._archive(
            "2026-09-29-newer-change", change_text="完成較新的變更。"
        )

        self.assertEqual(self._update(older).status, "updated")
        self.assertEqual(self._update(newer).status, "updated")

        content = self.history_path.read_text(encoding="utf-8")
        self.assertLess(content.index("newer-change"), content.index("older-change"))
        self.assertIn(
            "[openspec/changes/archive/2026-09-29-newer-change]", content
        )
        self.assertIn("完成較新的變更。；保留既有行為。", content)
        self.assertIn("`sample-capability`", content)
        self.assertIn("focused tests passed", content)
        self.assertIn("- Specs：synced", content)
        self.assertIn("人工內容不得修改。", content)
        self.assertIn("基準內容不得修改。", content)

    def test_rerun_does_not_duplicate_archive_entry(self):
        archive = self._archive(
            "2026-09-28-idempotent-change", change_text="完成可重跑的變更。"
        )

        first = self._update(archive)
        second = self._update(archive)

        self.assertEqual(first.status, "updated")
        self.assertEqual(second.status, "already-recorded")
        content = self.history_path.read_text(encoding="utf-8")
        self.assertEqual(content.count('key="2026-09-28-idempotent-change"'), 2)

    def test_malformed_managed_markers_leave_history_unchanged_and_mark_pending(self):
        archive = self._archive(
            "2026-09-28-malformed-history", change_text="完成待補寫變更。"
        )
        malformed = self.history_path.read_text(encoding="utf-8").replace(
            MANAGED_END, ""
        )
        self.history_path.write_text(malformed, encoding="utf-8")

        result = self._update(archive)

        self.assertEqual(result.status, "pending")
        self.assertIn("managed markers", result.error or "")
        self.assertEqual(self.history_path.read_text(encoding="utf-8"), malformed)
        self.assertTrue(archive.is_dir())
        self.assertEqual(
            result.archive_path,
            "openspec/changes/archive/2026-09-28-malformed-history",
        )
        self.assertTrue((archive / PENDING_FILENAME).is_file())

    def test_pending_archive_can_be_retried_after_history_is_repaired(self):
        archive = self._archive(
            "2026-09-28-retry-change", change_text="完成重試變更。"
        )
        self.history_path.unlink()
        self.history_path.mkdir()

        pending = self._update(archive)

        self.assertEqual(pending.status, "pending")
        self.assertTrue((archive / PENDING_FILENAME).is_file())

        self.history_path.rmdir()
        self.history_path.write_text(_history_document(), encoding="utf-8")
        repaired = self._update(archive)

        self.assertEqual(repaired.status, "updated")
        self.assertFalse((archive / PENDING_FILENAME).exists())
        self.assertIn("retry-change", self.history_path.read_text(encoding="utf-8"))

    def test_incomplete_existing_entry_is_not_overwritten(self):
        archive = self._archive(
            "2026-09-28-incomplete-entry", change_text="完成不完整條目測試。"
        )
        incomplete = (
            '<!-- codex-archive-log:entry-start key="2026-09-28-incomplete-entry" -->'
            "\n不完整內容"
        )
        original = _history_document(managed=incomplete)
        self.history_path.write_text(original, encoding="utf-8")

        result = self._update(archive)

        self.assertEqual(result.status, "pending")
        self.assertEqual(self.history_path.read_text(encoding="utf-8"), original)

    def test_repository_baseline_contains_supplied_history_and_statistics(self):
        history = (PROJECT_ROOT / "docs" / "DEVELOPMENT_HISTORY.md").read_text(
            encoding="utf-8"
        )

        self.assertLess(history.index(MANAGED_START), history.index("2026/05/19"))
        self.assertIn("2026/09/28【Git】", history)
        self.assertIn("916 次 AI 對話回合", history)
        self.assertIn("118 次", history)


if __name__ == "__main__":
    unittest.main()
