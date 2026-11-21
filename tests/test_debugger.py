"""The Scripts page's debugger (2026-11-21): a script run under its kernel's own debugger (ipykernel's
debugpy, the Jupyter debug protocol), stopped at a breakpoint, a conditional one and a log point; the call
stack, a frame's variables, the debug console, steps, continue and stop; the agent does all of it. Made-up
code only."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import debugger as rules
from tests.conftest import AGENT, AUTH, make_client

SCRIPT = (
    "loaves = 0\n"  # 1
    "def bake(n):\n"  # 2
    "    total = n * 2\n"  # 3
    "    return total\n"  # 4
    "for day in range(1, 4):\n"  # 5
    "    loaves += bake(day)\n"  # 6
    "print('baked', loaves)\n"  # 7
)


def test_the_rules() -> None:
    marks = rules.breakpoints_of([6, {"line": 3, "condition": "n > 1"}, {"line": 6, "log": "day {day}"}])
    assert [b.to_json() for b in marks] == [
        {"line": 3, "condition": "n > 1"},
        {"line": 6, "log": "day {day}"},
    ]
    assert marks[1].protocol() == {"line": 6, "logMessage": "day {day}"}
    with pytest.raises(rules.DebugError):
        rules.breakpoints_of([{"line": 0}])
    assert rules.step_command("over") == "next" and rules.step_command("out") == "stepOut"
    frames = rules.frames_of(
        [
            {"id": 1, "name": "bake", "line": 3, "source": {"path": "/k/1.py"}},
            {"id": 2, "name": "x", "line": 9, "source": {"path": "/lib/a.py"}},
        ],
        "/k/1.py",
        "/p/bake.py",
    )
    assert frames[0] == {"id": 1, "name": "bake", "line": 3, "yours": True, "path": "/p/bake.py"}
    assert frames[1]["yours"] is False and frames[1]["path"] == "/lib/a.py"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        yield test_client


def until(check: Callable[[], Any], seconds: float = 30.0) -> Any:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        found = check()
        if found:
            return found
        time.sleep(0.1)
    raise AssertionError("not in time")


def test_a_script_paused_at_its_breakpoints_stepped_and_read(client: TestClient, tmp_path: Path) -> None:
    script = str(tmp_path / "bake.py")
    kernel = client.post("/workbench/kernels", json={"path": script}, headers=AUTH).json()["kernel"]
    try:

        def state() -> dict[str, Any]:
            found: dict[str, Any] = client.get(
                "/workbench/debug", params={"kernel": kernel}, headers=AGENT
            ).json()
            return found

        marks = [{"line": 3, "condition": "n == 2"}, {"line": 6, "log": "day {day}"}]
        started = client.post(
            "/workbench/debug/start",
            json={"document": script, "code": SCRIPT, "breakpoints": marks},
            headers=AGENT,
        )
        assert started.status_code == 200, started.text
        paused = until(lambda: (s := state())["state"] == "paused" and s)
        assert paused["line"] == 3 and paused["frames"][0]["name"] == "bake" and paused["frames"][0]["yours"]
        assert "day 1" in paused["output"]  # the log point printed; the condition skipped n == 1
        found = client.post("/workbench/debug/variables", json={"kernel": kernel}, headers=AGENT).json()
        local = {v["name"]: v["value"] for v in found["scopes"][0]["variables"]}
        assert local["n"] == "2"
        said = client.post(
            "/workbench/debug/evaluate", json={"kernel": kernel, "expression": "n * 100"}, headers=AUTH
        ).json()
        assert said["value"] == "200"
        client.post("/workbench/debug/step", json={"kernel": kernel, "action": "over"}, headers=AGENT)
        stepped = until(lambda: (s := state())["state"] == "paused" and s)
        assert stepped["line"] == 4
        # No more breakpoints: continue to the end.
        client.post("/workbench/debug/breakpoints", json={"kernel": kernel, "breakpoints": []}, headers=AUTH)
        client.post("/workbench/debug/step", json={"kernel": kernel, "action": "continue"}, headers=AUTH)
        ended = until(lambda: (s := state())["state"] == "ended" and s)
        assert ended["ok"] is True and "baked 12" in ended["output"]
        # Again, then stopped while paused.
        client.post(
            "/workbench/debug/start",
            json={"kernel": kernel, "code": SCRIPT, "breakpoints": [4]},
            headers=AUTH,
        )
        until(lambda: state()["state"] == "paused")
        stopped = client.post("/workbench/debug/stop", json={"kernel": kernel}, headers=AUTH).json()
        assert stopped["state"] == "ended"
        refused = client.post(
            "/workbench/debug/step", json={"kernel": kernel, "action": "over"}, headers=AUTH
        )
        assert refused.status_code == 409
    finally:
        client.delete(f"/workbench/kernels/{kernel}", headers=AUTH)
