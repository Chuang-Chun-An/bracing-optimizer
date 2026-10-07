"""Runtime lifecycle registry for Solver input snapshots and executions."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from bracing_optimizer.algorithms.cancellation import (
    CancellationSource,
    CancellationToken,
)


class SolverKind(str, Enum):
    SUPPORT = "support"
    SINGLE_WALER = "single_waler"
    GLOBAL_WALER = "global_waler"


class SnapshotState(str, Enum):
    OPEN = "open"
    RUNNING = "running"
    STALE = "stale"
    CLOSED = "closed"


class CompletionDisposition(str, Enum):
    ADOPTABLE = "adoptable"
    STALE = "stale"
    IGNORED = "ignored"


class SolverOperationUnavailable(RuntimeError):
    """Raised when a snapshot cannot start another execution."""


@dataclass(frozen=True)
class SolverSnapshotHandle:
    """Opaque identity for one immutable Solver input snapshot."""

    _identity: uuid.UUID


@dataclass(frozen=True)
class SolverExecution:
    """Identity and read-only cancellation token for one worker execution."""

    snapshot_handle: SolverSnapshotHandle
    identity: uuid.UUID
    cancellation_token: CancellationToken


@dataclass(frozen=True)
class SolverSnapshotStatus:
    kind: SolverKind
    state: SnapshotState
    stale_reason: str | None
    has_active_execution: bool


@dataclass(frozen=True)
class InvalidatedSnapshot:
    handle: SolverSnapshotHandle
    kind: SolverKind
    was_running: bool
    reason: str


@dataclass
class _SnapshotRecord:
    kind: SolverKind
    state: SnapshotState = SnapshotState.OPEN
    stale_reason: str | None = None
    execution_id: uuid.UUID | None = None
    cancellation_source: CancellationSource | None = None
    stale_listener: Callable[[str], None] | None = None


class SolverOperationRegistry:
    """Thread-safe source of truth for Solver snapshot operation lifecycles."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[SolverSnapshotHandle, _SnapshotRecord] = {}

    def register_snapshot(self, kind: SolverKind) -> SolverSnapshotHandle:
        handle = SolverSnapshotHandle(uuid.uuid4())
        with self._lock:
            self._records[handle] = _SnapshotRecord(kind=SolverKind(kind))
        return handle

    def set_stale_listener(
        self,
        handle: SolverSnapshotHandle,
        listener: Callable[[str], None] | None,
    ) -> bool:
        stale_reason: str | None = None
        with self._lock:
            record = self._records.get(handle)
            if record is None or record.state is SnapshotState.CLOSED:
                return False
            record.stale_listener = listener
            if record.state is SnapshotState.STALE:
                stale_reason = record.stale_reason or "stale"
        if listener is not None and stale_reason is not None:
            listener(stale_reason)
        return True

    def start_execution(self, handle: SolverSnapshotHandle) -> SolverExecution:
        with self._lock:
            record = self._records.get(handle)
            if record is None or record.state is not SnapshotState.OPEN:
                raise SolverOperationUnavailable(
                    "Solver input snapshot is no longer available"
                )
            execution_id = uuid.uuid4()
            source = CancellationSource()
            record.state = SnapshotState.RUNNING
            record.execution_id = execution_id
            record.cancellation_source = source
            return SolverExecution(handle, execution_id, source.token)

    def invalidate_open_and_running(
        self,
        reason: str,
    ) -> tuple[InvalidatedSnapshot, ...]:
        invalidated: list[InvalidatedSnapshot] = []
        sources: list[CancellationSource] = []
        listeners: list[tuple[Callable[[str], None], str]] = []
        normalized_reason = str(reason or "stale")
        with self._lock:
            for handle, record in self._records.items():
                if record.state not in (SnapshotState.OPEN, SnapshotState.RUNNING):
                    continue
                was_running = record.state is SnapshotState.RUNNING
                record.state = SnapshotState.STALE
                record.stale_reason = normalized_reason
                invalidated.append(
                    InvalidatedSnapshot(
                        handle=handle,
                        kind=record.kind,
                        was_running=was_running,
                        reason=normalized_reason,
                    )
                )
                if was_running and record.cancellation_source is not None:
                    sources.append(record.cancellation_source)
                if record.stale_listener is not None:
                    listeners.append((record.stale_listener, normalized_reason))
        for source in sources:
            source.cancel()
        for listener, stale_reason in listeners:
            listener(stale_reason)
        return tuple(invalidated)

    def can_adopt(
        self,
        handle: SolverSnapshotHandle,
        execution_id: uuid.UUID,
    ) -> bool:
        with self._lock:
            record = self._records.get(handle)
            return bool(
                record is not None
                and record.state is SnapshotState.RUNNING
                and record.execution_id == execution_id
            )

    def complete_execution(
        self,
        handle: SolverSnapshotHandle,
        execution_id: uuid.UUID,
    ) -> CompletionDisposition:
        with self._lock:
            record = self._records.get(handle)
            if record is None or record.execution_id != execution_id:
                return CompletionDisposition.IGNORED
            record.execution_id = None
            record.cancellation_source = None
            if record.state is SnapshotState.STALE:
                return CompletionDisposition.STALE
            if record.state is SnapshotState.RUNNING:
                record.state = SnapshotState.OPEN
                return CompletionDisposition.ADOPTABLE
            return CompletionDisposition.IGNORED

    def abort_execution(
        self,
        handle: SolverSnapshotHandle,
        execution_id: uuid.UUID,
    ) -> bool:
        """Roll back a worker start or terminal path without adopting output."""

        with self._lock:
            record = self._records.get(handle)
            if record is None or record.execution_id != execution_id:
                return False
            record.execution_id = None
            record.cancellation_source = None
            if record.state is SnapshotState.RUNNING:
                record.state = SnapshotState.OPEN
            return True

    def close_snapshot(self, handle: SolverSnapshotHandle) -> bool:
        with self._lock:
            record = self._records.get(handle)
            if record is None:
                return True
            if record.execution_id is not None:
                return False
            record.state = SnapshotState.CLOSED
            record.stale_listener = None
            del self._records[handle]
            return True

    def status(
        self,
        handle: SolverSnapshotHandle,
    ) -> SolverSnapshotStatus | None:
        with self._lock:
            record = self._records.get(handle)
            if record is None:
                return None
            return SolverSnapshotStatus(
                kind=record.kind,
                state=record.state,
                stale_reason=record.stale_reason,
                has_active_execution=record.execution_id is not None,
            )

    def has_stale_running_waler(self) -> bool:
        with self._lock:
            return any(
                record.kind in (SolverKind.SINGLE_WALER, SolverKind.GLOBAL_WALER)
                and record.state is SnapshotState.STALE
                and record.execution_id is not None
                for record in self._records.values()
            )


__all__ = [
    "CompletionDisposition",
    "InvalidatedSnapshot",
    "SnapshotState",
    "SolverExecution",
    "SolverKind",
    "SolverOperationRegistry",
    "SolverOperationUnavailable",
    "SolverSnapshotHandle",
    "SolverSnapshotStatus",
]
