"""Maintain the Codex/OpenSpec section in docs/DEVELOPMENT_HISTORY.md."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence


MANAGED_START = "<!-- codex-archive-log:start -->"
MANAGED_END = "<!-- codex-archive-log:end -->"
EMPTY_PLACEHOLDER = "目前尚無自動封存紀錄。"
PENDING_FILENAME = ".development-history-pending.json"
_ARCHIVE_DATE_PATTERN = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<name>.+)$")


class DevelopmentHistoryError(ValueError):
    """The history document cannot be updated without risking manual content."""


@dataclass(frozen=True)
class ArchiveRecord:
    """Traceable information rendered as one managed Markdown entry."""

    key: str
    archive_date: str
    change_name: str
    archive_path: str
    archive_link: str
    summary: str
    capabilities: tuple[str, ...]
    verification_status: str
    spec_status: str


@dataclass(frozen=True)
class UpdateResult:
    """Machine-readable outcome consumed by the archive workflow."""

    status: str
    archive_path: str
    history_path: str
    key: str
    error: str | None = None
    pending_marker: str | None = None


def _section(markdown: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(markdown)
    return match.group("body").strip() if match else ""


def _proposal_summary(proposal: str) -> str:
    changes = _section(proposal, "What Changes")
    bullets = [
        line[2:].strip()
        for line in changes.splitlines()
        if line.startswith("- ")
    ]
    if bullets:
        return "；".join(bullets[:3])

    why = _section(proposal, "Why")
    paragraphs = [part.strip().replace("\n", " ") for part in why.split("\n\n")]
    return next((part for part in paragraphs if part), "未提供 proposal 摘要。")


def _capabilities(archive_dir: Path) -> tuple[str, ...]:
    specs_dir = archive_dir / "specs"
    if not specs_dir.is_dir():
        return ()
    return tuple(
        sorted(
            spec_path.parent.relative_to(specs_dir).as_posix()
            for spec_path in specs_dir.rglob("spec.md")
        )
    )


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def build_archive_record(
    archive_dir: str | Path,
    history_path: str | Path,
    *,
    repo_root: str | Path,
    verification_status: str,
    spec_status: str,
) -> ArchiveRecord:
    """Build a record only from the archived change and archive workflow facts."""

    archive = Path(archive_dir).resolve()
    history = Path(history_path).resolve()
    root = Path(repo_root).resolve()
    if not archive.is_dir():
        raise DevelopmentHistoryError(f"archived change 不存在：{archive}")

    match = _ARCHIVE_DATE_PATTERN.match(archive.name)
    archive_date = match.group("date") if match else date.today().isoformat()
    change_name = match.group("name") if match else archive.name
    archive_path = _relative_path(archive, root)
    archive_link = Path(
        os.path.relpath(archive, start=history.parent)
    ).as_posix()
    proposal_path = archive / "proposal.md"
    proposal = (
        proposal_path.read_text(encoding="utf-8")
        if proposal_path.is_file()
        else ""
    )
    return ArchiveRecord(
        key=archive.name,
        archive_date=archive_date,
        change_name=change_name,
        archive_path=archive_path,
        archive_link=archive_link,
        summary=_proposal_summary(proposal),
        capabilities=_capabilities(archive),
        verification_status=verification_status.strip(),
        spec_status=spec_status.strip(),
    )


def render_archive_record(record: ArchiveRecord) -> str:
    """Render one self-delimiting Markdown entry."""

    capability_text = (
        "、".join(f"`{name}`" for name in record.capabilities)
        if record.capabilities
        else "無 spec-level capability"
    )
    start = f'<!-- codex-archive-log:entry-start key="{record.key}" -->'
    end = f'<!-- codex-archive-log:entry-end key="{record.key}" -->'
    return "\n".join(
        (
            start,
            f"### {record.archive_date}｜`{record.change_name}`",
            "",
            f"- Archive：[{record.archive_path}]({record.archive_link})",
            f"- 完成內容：{record.summary}",
            f"- Capabilities：{capability_text}",
            f"- 驗證：{record.verification_status}",
            f"- Specs：{record.spec_status}",
            end,
        )
    )


def update_managed_section(markdown: str, record: ArchiveRecord) -> tuple[str, bool]:
    """Insert or refresh one entry without touching text outside managed markers."""

    if markdown.count(MANAGED_START) != 1 or markdown.count(MANAGED_END) != 1:
        raise DevelopmentHistoryError("開發歷程的 managed markers 缺失或重複")
    before, remainder = markdown.split(MANAGED_START, 1)
    managed, after = remainder.split(MANAGED_END, 1)
    if markdown.index(MANAGED_START) > markdown.index(MANAGED_END):
        raise DevelopmentHistoryError("開發歷程的 managed markers 順序錯誤")

    start_marker = f'<!-- codex-archive-log:entry-start key="{record.key}" -->'
    end_marker = f'<!-- codex-archive-log:entry-end key="{record.key}" -->'
    has_start = start_marker in managed
    has_end = end_marker in managed
    if has_start != has_end:
        raise DevelopmentHistoryError(
            f"archive 條目 {record.key} 不完整，無法安全自動修復"
        )

    rendered = render_archive_record(record)
    if has_start:
        prefix, entry_remainder = managed.split(start_marker, 1)
        _, suffix = entry_remainder.split(end_marker, 1)
        replacement = f"{prefix}{rendered}{suffix}"
    else:
        existing = managed.strip()
        if existing == EMPTY_PLACEHOLDER:
            existing = ""
        replacement = f"\n\n{rendered}"
        if existing:
            replacement += f"\n\n{existing}"
        replacement += "\n\n"

    updated = f"{before}{MANAGED_START}{replacement}{MANAGED_END}{after}"
    return updated, updated != markdown


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_pending_marker(archive_dir: Path, result: UpdateResult) -> str | None:
    marker_path = archive_dir / PENDING_FILENAME
    payload = asdict(result)
    payload["recorded_at"] = datetime.now(timezone.utc).isoformat()
    try:
        _atomic_write(
            marker_path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )
    except OSError:
        return None
    return marker_path.as_posix()


def update_history_from_archive(
    archive_dir: str | Path,
    history_path: str | Path,
    *,
    repo_root: str | Path,
    verification_status: str,
    spec_status: str,
) -> UpdateResult:
    """Update history, preserving a retry marker when the write cannot complete."""

    archive = Path(archive_dir).resolve()
    history = Path(history_path).resolve()
    key = archive.name
    archive_display = _relative_path(archive, Path(repo_root))
    try:
        record = build_archive_record(
            archive,
            history,
            repo_root=repo_root,
            verification_status=verification_status,
            spec_status=spec_status,
        )
        current = history.read_text(encoding="utf-8")
        updated, changed = update_managed_section(current, record)
        if changed:
            _atomic_write(history, updated)
        (archive / PENDING_FILENAME).unlink(missing_ok=True)
        return UpdateResult(
            status="updated" if changed else "already-recorded",
            archive_path=archive_display,
            history_path=_relative_path(history, Path(repo_root)),
            key=record.key,
        )
    except (OSError, UnicodeError, DevelopmentHistoryError) as exc:
        result = UpdateResult(
            status="pending",
            archive_path=archive_display,
            history_path=_relative_path(history, Path(repo_root)),
            key=key,
            error=str(exc),
        )
        marker = _write_pending_marker(archive, result) if archive.is_dir() else None
        return UpdateResult(**{**asdict(result), "pending_marker": marker})


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_dir", type=Path, help="已封存 change 的目錄")
    parser.add_argument(
        "--history",
        type=Path,
        default=Path("docs/DEVELOPMENT_HISTORY.md"),
        help="開發歷程 Markdown 路徑",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--verification-status",
        default="OpenSpec archive checks completed",
    )
    parser.add_argument("--spec-status", default="Not reported")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    result = update_history_from_archive(
        args.archive_dir,
        args.history,
        repo_root=args.repo_root,
        verification_status=args.verification_status,
        spec_status=args.spec_status,
    )
    print(json.dumps(asdict(result), ensure_ascii=False))
    return 0 if result.status != "pending" else 2


if __name__ == "__main__":
    raise SystemExit(main())
