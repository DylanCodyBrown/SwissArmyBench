"""Work started and not waited for: a pipe read to its end, a notice sent after the answer, a sign-in watched.

The event loop holds its tasks weakly, so a task nobody keeps may be collected while it runs, and one that
ends with an exception says so only when it is collected ("Task exception was never retrieved", if ever).
`keep` is the one way such work starts: the task is held here until it ends, and an exception it ends with
is logged with the job's name (the exception's type and stack; a cancelled task says nothing).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

LOG_NAME: str = "swissarmybench.background"
_log = logging.getLogger(LOG_NAME)
_kept: set[asyncio.Task[Any]] = set()


def keep[T](work: Coroutine[Any, Any, T], name: str) -> asyncio.Task[T]:
    """Start `work` on the running loop as the job `name` and keep it until it ends. The task, for a
    caller that cancels or awaits it."""
    task = asyncio.get_running_loop().create_task(work, name=name)
    _kept.add(task)
    task.add_done_callback(_ended)
    return task


def running() -> int:
    """How many kept jobs have not ended yet."""
    return len(_kept)


def _ended(task: asyncio.Task[Any]) -> None:
    _kept.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        _log.error("The background job %s failed.", task.get_name(), exc_info=error)
