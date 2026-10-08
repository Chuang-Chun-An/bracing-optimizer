"""Thread-safe cooperative cancellation primitives for Solver algorithms."""

from __future__ import annotations

import threading


class SolverCancelled(Exception):
    """Control outcome raised when a Solver reaches a cancellation checkpoint."""


class CancellationToken:
    """Read-only view of a cancellation signal shared with Solver workers."""

    __slots__ = ("__event",)

    def __init__(self, event: threading.Event) -> None:
        self.__event = event

    @property
    def is_cancelled(self) -> bool:
        return self.__event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.__event.is_set():
            raise SolverCancelled()


class CancellationSource:
    """Owner-side cancellation signal; workers receive only its token."""

    __slots__ = ("__event", "__token")

    def __init__(self) -> None:
        self.__event = threading.Event()
        self.__token = CancellationToken(self.__event)

    @property
    def token(self) -> CancellationToken:
        return self.__token

    @property
    def is_cancelled(self) -> bool:
        return self.__event.is_set()

    def cancel(self) -> None:
        self.__event.set()


__all__ = ["CancellationSource", "CancellationToken", "SolverCancelled"]
