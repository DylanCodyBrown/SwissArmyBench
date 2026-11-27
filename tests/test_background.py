"""Work started and not waited for (services/background.py): the task is kept until it ends (the event loop
holds tasks weakly: one nobody keeps may be collected mid-run), and an exception it ends with is logged
instead of vanishing. The services that start such work do it through this one helper."""

from __future__ import annotations

import asyncio
import gc
import logging
from pathlib import Path

import pytest

from swissarmybench.services import background

ROOT = Path(__file__).resolve().parents[1]
STARTERS = (
    "src/swissarmybench/server/api_runs.py",
    "src/swissarmybench/services/debugger.py",
    "src/swissarmybench/services/sharing.py",
    "src/swissarmybench/services/connection_slots.py",
    "extensions/copilot/src/swissarmybench_copilot/services/copilot.py",
)


def test_a_task_is_kept_until_it_ends_and_its_exception_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    asyncio.run(_kept_and_logged(caplog))


async def _kept_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    gate = asyncio.Event()

    async def made_up_failure() -> None:
        await gate.wait()
        raise RuntimeError("made-up failure")

    with caplog.at_level(logging.ERROR, logger=background.LOG_NAME):
        background.keep(made_up_failure(), "a made-up job")
        gc.collect()  # nobody else holds the task
        assert background.running() == 1
        gate.set()
        for _ in range(20):
            await asyncio.sleep(0)
        assert background.running() == 0
    [said] = [r for r in caplog.records if r.name == background.LOG_NAME]
    assert "a made-up job" in said.getMessage() and said.exc_info is not None
    assert isinstance(said.exc_info[1], RuntimeError)


def test_a_cancelled_task_and_one_that_ends_well_say_nothing(caplog: pytest.LogCaptureFixture) -> None:
    asyncio.run(_quiet(caplog))


async def _quiet(caplog: pytest.LogCaptureFixture) -> None:
    async def fine() -> int:
        return 1

    async def waits() -> None:
        await asyncio.sleep(60)

    with caplog.at_level(logging.ERROR, logger=background.LOG_NAME):
        done = background.keep(fine(), "fine")
        stopped = background.keep(waits(), "waits")
        await asyncio.sleep(0)
        stopped.cancel()
        for _ in range(5):
            await asyncio.sleep(0)
        assert done.result() == 1 and stopped.cancelled() and background.running() == 0
    assert [r for r in caplog.records if r.name == background.LOG_NAME] == []


def test_the_services_start_their_background_work_through_the_helper() -> None:
    bare = [path for path in STARTERS if "create_task(" in (ROOT / path).read_text(encoding="utf-8")]
    assert bare == []
