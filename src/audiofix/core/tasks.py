"""Background task runner that keeps worker-thread ownership out of the GUI."""

from collections.abc import Callable
from threading import Thread
from typing import TypeVar


T = TypeVar("T")


def start_background_task(
    work: Callable[[], T],
    on_success: Callable[[T], None],
    on_error: Callable[[Exception], None],
    schedule: Callable[[Callable[[], None]], None],
) -> Thread:
    thread = Thread(
        target=_run_task,
        args=(work, on_success, on_error, schedule),
        daemon=True,
    )
    thread.start()
    return thread


def _run_task(
    work: Callable[[], T],
    on_success: Callable[[T], None],
    on_error: Callable[[Exception], None],
    schedule: Callable[[Callable[[], None]], None],
) -> None:
    try:
        result = work()
    except Exception as error:
        schedule(lambda error=error: on_error(error))
        return

    schedule(lambda result=result: on_success(result))
