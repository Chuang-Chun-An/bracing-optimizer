"""Data-only contracts used by the software information presentation."""

from __future__ import annotations

from dataclasses import dataclass

from bracing_optimizer.product_metadata import ProductIdentity


HISTORY_UNAVAILABLE_MESSAGE = "開發歷程目前無法取得。"


@dataclass(frozen=True)
class SoftwareHistoryEntry:
    """One initial-history row in its authoritative source order."""

    date_label: str
    record: str


@dataclass(frozen=True)
class SoftwareHistoryLoadResult:
    """Validated history entries or a safe user-visible fallback."""

    available: bool
    entries: tuple[SoftwareHistoryEntry, ...] = ()
    message: str | None = None


@dataclass(frozen=True)
class SoftwareInformation:
    """Complete immutable model rendered by the information dialog."""

    identity: ProductIdentity
    history: SoftwareHistoryLoadResult


__all__ = [
    "HISTORY_UNAVAILABLE_MESSAGE",
    "SoftwareHistoryEntry",
    "SoftwareHistoryLoadResult",
    "SoftwareInformation",
]
