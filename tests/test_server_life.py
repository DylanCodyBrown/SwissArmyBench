"""The server's life follows the app (the owner, 2026-11-18): it stops 30 seconds after the last window closes
(at once when the desktop app closes), or 10 minutes after the last request of the agent, VS Code or a Python
session with still no window; the open project's unsaved changes are saved first (Autosave's way) or the stop
waits. The tray and start at sign-in are gone, and what an older version left is removed once."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from swissarmybench.domain import lifecycle as rules
from swissarmybench.server import legacy_tray
from swissarmybench.server import lifecycle as server_lifecycle
from swissarmybench.services.lifecycle import Lifecycle
from tests.conftest import AGENT, AUTH, make_client


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def made(
    clock: Clock, windows: list[int], held: str = "", busy: list[str] | None = None
) -> tuple[Lifecycle, list[bool]]:
    stopped: list[bool] = []

    async def before_stop() -> str:
        return held

    life = Lifecycle(
        windows=lambda: windows[0],
        busy=lambda: list(busy or []),
        before_stop=before_stop,
        stop=lambda: stopped.append(True),
        clock=clock,
    )
    return life, stopped


def tick(life: Lifecycle) -> bool:
    return asyncio.run(life.tick())


def test_no_window_yet_waits_the_start_grace_then_stops() -> None:
    clock, windows = Clock(), [0]
    life, stopped = made(clock, windows)
    clock.now += rules.START_GRACE_SECONDS - 1
    assert not tick(life)
    clock.now += 2
    assert tick(life) and stopped == [True]


def test_the_last_window_closed_stops_it_after_the_grace_and_a_reload_does_not() -> None:
    clock, windows = Clock(), [1]
    life, stopped = made(clock, windows)
    assert not tick(life)
    windows[0] = 0  # a reload: the page's socket closes ...
    clock.now += 1
    assert not tick(life)
    clock.now += 2
    windows[0] = 1  # ... and opens again within the grace
    assert not tick(life)
    clock.now += 10 * rules.GRACE_SECONDS
    assert not tick(life)  # a window open: never
    windows[0] = 0  # the last window closed for good
    assert not tick(life)
    clock.now += rules.GRACE_SECONDS - 1
    assert not tick(life) and life.state()["stops_in"] == 1
    clock.now += 2
    assert tick(life) and stopped == [True]


def test_an_agents_request_keeps_it_up_ten_minutes() -> None:
    clock, windows = Clock(), [1]
    life, stopped = made(clock, windows)
    tick(life)
    windows[0] = 0
    tick(life)
    clock.now += 5
    life.request("/grids/x/rows", "the agent", by_token=True, started=True)
    life.request("/grids/x/rows", "the agent", by_token=True, started=False)
    clock.now += rules.GRACE_SECONDS + 5  # past the windows' grace: the agent's ten minutes hold it
    assert not tick(life)
    said = life.state()
    assert said["last_client"]["who"] == "the agent" and "the agent was here" in said["why"]
    clock.now += rules.IDLE_SECONDS
    assert tick(life) and stopped == [True]


def test_the_pages_own_requests_and_cookie_ones_do_not_count() -> None:
    clock, windows = Clock(), [0]
    life, _ = made(clock, windows)
    life.request("/session", "a client", by_token=True, started=True)  # the page trading its token
    life.request("/grids/x/rows", "a client", by_token=False, started=True)  # the page's cookie
    assert life.life.client_at is None


def test_asking_whether_it_runs_or_when_it_stops_is_not_work() -> None:
    """The desktop app checks /health with the token at its start and with each page it opens; counted as
    work, they kept the server up 10 minutes after the app closed (seen on 0.0.22's release check)."""
    clock, windows = Clock(), [0]
    life, _ = made(clock, windows)
    for path in ("/health", "/lifecycle", "/lifecycle/closed"):
        life.request(path, "a client", by_token=True, started=True)
        life.request(path, "a client", by_token=True, started=False)
    assert life.life.client_at is None
    life.request("/datasets", "the agent", by_token=True, started=True)  # real work still counts
    assert life.life.client_at is not None


def test_a_request_under_way_or_vscode_connected_is_busy() -> None:
    clock, windows = Clock(), [0]
    busy: list[str] = []
    life, _ = made(clock, windows, busy=busy)
    life.request("/workbench/scripts/run", "the agent", by_token=True, started=True)
    clock.now += 3 * rules.IDLE_SECONDS
    assert not tick(life) and "a request under way" in life.state()["busy"]
    life.request("/workbench/scripts/run", "the agent", by_token=True, started=False)
    busy.append("a VS Code window")
    clock.now += 3 * rules.IDLE_SECONDS
    assert not tick(life)
    busy.clear()  # VS Code closed: ten minutes from now
    tick(life)
    clock.now += rules.IDLE_SECONDS - 1
    assert not tick(life)
    clock.now += 2
    assert tick(life)
    # A listener that waits by design (a Python session's) is a visit, not work under way.
    life2, _ = made(Clock(), [0])
    life2.request("/processes/p1/requests", "a Python session", by_token=True, started=True)
    assert life2.state()["busy"] == []


def test_the_app_closed_stops_it_at_once_and_unsaved_work_holds_it() -> None:
    clock, windows = Clock(), [2]
    life, stopped = made(clock, windows)
    tick(life)
    windows[0] = 0
    life.closed()
    tick(life)
    clock.now += rules.CLOSE_GRACE_SECONDS + 0.5
    assert tick(life) and stopped == [True]
    # With Autosave off and unsaved changes: held, said, never stopped.
    clock2, windows2 = Clock(), [0]
    held, never = made(clock2, windows2, held="the open project has unsaved changes and Autosave is off")
    clock2.now += rules.START_GRACE_SECONDS + 1
    assert not tick(held) and never == []
    assert held.state()["held"].startswith("the open project has unsaved changes")


def test_the_route_reads_it_and_the_guard_reports_requests(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        said = client.get("/lifecycle", headers=AGENT).json()
        assert {"windows", "last_client", "busy", "held", "stops_in", "why", "rule"} <= set(said)
        assert said["last_client"] is None  # asking when it stops is not work
        client.get("/datasets", headers=AGENT)  # real work, with the token
        said = client.get("/lifecycle", headers=AGENT).json()
        assert said["last_client"]["who"] == "the agent"
        closed = client.post("/lifecycle/closed", headers=AUTH)
        assert closed.status_code == 200
        assert client.get("/lifecycle").status_code == 401


def test_a_pages_fetch_with_the_token_is_not_a_client(tmp_path: Path) -> None:
    """The pages send the token as a Bearer header (web/src/api.ts): without the browser's Sec-Fetch-Site
    mark every click held the server 10 minutes after the app closed (seen on 0.0.22's release check)."""
    assert rules.from_a_page("same-origin") and rules.from_a_page(" Same-Origin ")
    assert not any(rules.from_a_page(value) for value in (None, "cross-site", "none"))
    with make_client(tmp_path) as client:
        client.get("/datasets", headers={**AUTH, "Sec-Fetch-Site": "same-origin"})  # a window's fetch
        assert client.get("/lifecycle", headers=AGENT).json()["last_client"] is None
        client.get("/datasets", headers=AUTH)  # a Python push or VS Code: no such mark
        assert client.get("/lifecycle", headers=AGENT).json()["last_client"] is not None


def test_a_saved_project_is_saved_before_the_stop(tmp_path: Path) -> None:
    """before_stop (bootstrap): a dirty project with Autosave on is saved; with it off, the stop waits."""
    with make_client(tmp_path) as client:
        life = client.app.state.ctx.lifecycle  # type: ignore[attr-defined]
        assert asyncio.run(life._before_stop()) == ""  # nothing open: nothing to keep
        made_project = client.post("/project/new", headers=AUTH, json={"path": str(tmp_path / "proj")})
        assert made_project.status_code == 200, made_project.text
        client.post("/datasets/orders/paste", headers=AUTH, content="id\tregion\n1\tNorth\n2\tSouth\n")
        projects = client.app.state.ctx.sab_projects  # type: ignore[attr-defined]
        projects.current.autosave = False
        assert projects.dirty()
        assert "Autosave is off" in asyncio.run(life._before_stop())
        projects.current.autosave = True
        assert asyncio.run(life._before_stop()) == "" and not projects.dirty()


# ===== the tray and start at sign-in, gone =====


def test_the_old_sign_in_entries_and_tray_are_removed_once(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    state.mkdir()
    linux = home / ".config" / "autostart" / legacy_tray.DESKTOP_NAME
    linux.parent.mkdir(parents=True)
    linux.write_text("[Desktop Entry]\nExec=/x/python -m swissarmybench.server tray\n", encoding="utf-8")
    mac = home / "Library" / "LaunchAgents" / f"{legacy_tray.LABEL}.plist"
    mac.parent.mkdir(parents=True)
    mac.write_text("<plist>swissarmybench.server tray</plist>", encoding="utf-8")
    windows = home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    windows.mkdir(parents=True)
    (windows / legacy_tray.SHORTCUT_NAME).write_bytes(b"made-up shortcut")
    # A stand-in for the old tray: a process of its own, its pid in tray.json.
    standin = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)  # swissarmybench tray stand-in"]
    )
    (state / "tray.json").write_text(json.dumps({"pid": standin.pid}), encoding="utf-8")
    ended: list[int] = []

    def end(pid: int) -> None:
        ended.append(pid)
        standin.terminate()

    try:
        assert legacy_tray.remove_old_tray(state, home, platform="linux", environ={}, end=end)
        assert not linux.exists() and not (state / "tray.json").exists() and ended == [standin.pid]
        assert standin.wait(10) is not None
        assert legacy_tray.remove_old_tray(state, home, platform="darwin", environ={})
        assert not mac.exists()
        assert legacy_tray.remove_old_tray(state, home, platform="win32", environ={})
        assert not (windows / legacy_tray.SHORTCUT_NAME).exists()
        # Once gone, nothing more to say.
        assert not legacy_tray.remove_old_tray(state, home, platform="linux", environ={})
        # An autostart entry that is someone else's (not the tray's command) is left alone.
        linux.write_text("[Desktop Entry]\nExec=other-app\n", encoding="utf-8")
        assert not legacy_tray.remove_old_tray(state, home, platform="linux", environ={})
        assert linux.exists()
    finally:
        if standin.poll() is None:
            standin.kill()


def test_the_page_is_told_once(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "tray.json").write_text(json.dumps({"pid": 2**22 + 7}), encoding="utf-8")
    with make_client(tmp_path) as client:
        notices = client.post("/library/notices", headers=AUTH).json()["notices"]
        assert rules.NOTICE_GONE in [n["text"] for n in notices]
        assert client.post("/library/notices", headers=AUTH).json()["notices"] == []
    assert not (state / "tray.json").exists()


# ===== a real run: a server, a page, the grace =====


def test_a_real_server_stops_after_its_last_page_closes(tmp_path: Path) -> None:
    from websockets.sync.client import connect

    info = tmp_path / "server.json"
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(info),
        "SWISSARMYBENCH_STATE": str(tmp_path / "state"),
        "SWISSARMYBENCH_LIFE_GRACE": "1",
        "SWISSARMYBENCH_LIFE_START_GRACE": "30",
        "SWISSARMYBENCH_LIFE_IDLE": "2",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "swissarmybench.server", "start", "--port", "0", "--no-window"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        server: dict[str, Any] | None = None
        for _ in range(150):
            server = server_lifecycle.running_server(info)
            if server:
                break
            time.sleep(0.1)
        assert server is not None
        address = f"ws://127.0.0.1:{server['port']}/ws?workspace=1"
        page = connect(address, subprotocols=["swissarmybench", server["token"]])  # type: ignore[list-item]
        # A page open: past every grace, the server stays (the agent's request counts 2 s only). The one
        # wait of its kind: the test is that nothing happens for longer than the graces.
        time.sleep(3.5)
        assert process.poll() is None
        page.close()  # the last window closed
        process.wait(timeout=20)  # the grace (1 s) and the agent's last read (2 s) later: stopped
        assert not info.exists()
    finally:
        if process.poll() is None:
            process.kill()
