"""Deterministic scheduling for tests whose Clock does not advance with host time."""

from concurrent.futures import Future
from typing import Any


class ImmediateExecutor:
    def submit(self, fn: Any, *args: Any) -> Future[Any]:
        future: Future[Any] = Future()
        try:
            future.set_result(fn(*args))
        except BaseException as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, wait: bool = True) -> None:
        del wait  # All submitted tasks have already completed synchronously.


def use_immediate_executor(runner: Any) -> None:
    """Keep real Runner/admission/validation, control only task scheduling."""
    runner._executor.shutdown(wait=True)
    runner._executor = ImmediateExecutor()
