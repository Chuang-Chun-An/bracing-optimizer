"""Thread-safe execution guard shared by interactive Waler workflows."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


class WalerSolverBusyGuard:
    """Allow at most one active Waler Solver execution per application."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_token: object | None = None
        self._active_owner = ""

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._active_token is not None

    @property
    def active_owner(self) -> str:
        with self._lock:
            return self._active_owner

    def try_acquire(self, owner: str = "") -> WalerSolverLease | None:
        """Return an idempotent lease, or ``None`` when already busy."""

        with self._lock:
            if self._active_token is not None:
                return None
            token = object()
            self._active_token = token
            self._active_owner = str(owner or "").strip()
        return WalerSolverLease(self, token)

    def _release(self, token: object) -> None:
        with self._lock:
            if self._active_token is not token:
                return
            self._active_token = None
            self._active_owner = ""


@dataclass
class WalerSolverLease:
    """One acquired guard lease; releasing it more than once is safe."""

    _guard: WalerSolverBusyGuard = field(repr=False)
    _token: object = field(repr=False)
    _released: bool = field(default=False, init=False, repr=False)
    _release_lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    @property
    def released(self) -> bool:
        with self._release_lock:
            return self._released

    def release(self) -> None:
        with self._release_lock:
            if self._released:
                return
            self._released = True
        self._guard._release(self._token)

    def __enter__(self) -> WalerSolverLease:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> bool:
        self.release()
        return False


__all__ = ["WalerSolverBusyGuard", "WalerSolverLease"]
