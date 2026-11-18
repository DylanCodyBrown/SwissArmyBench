"""Swiss Army Bench as a desktop app (the owner, 2026-11-18): the `swissarmybench` command opens the app (the
browser where it cannot run, or when asked), the agent's desktop_ tools, the update's helper ending the app,
and the tray and start at sign-in gone. No Qt here (tests/test_desktop_shell.py runs the real app)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.cli import commands
from swissarmybench.server import __main__ as command
from swissarmybench.server import desktop
from swissarmybench.services.desktop import Desktop
from tests.conftest import AGENT, AUTH, make_client


class Shell:
    """The app as the service sees it, stood in for."""

    def __init__(self, can: bool = True) -> None:
        self.can = can
        self.opened: list[str] = []

    def status(self) -> dict[str, Any]:
        windows = [{"kind": "home", "title": "Orders", "page": "/workspace", "name": "sab-home"}]
        return {"running": bool(self.opened), "windows": windows if self.opened else []}

    def open(self, page: str) -> bool:
        if self.can:
            self.opened.append(page)
        return self.can


def noted(into: list[Any], value: Any, answer: Any) -> Any:
    into.append(value)
    return answer


def run_main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["swissarmybench", *argv])
    try:
        command.main()
    except SystemExit as stopped:
        return int(stopped.code or 0)
    return 0


def test_swissarmybench_opens_the_app_and_open_browser_opens_a_tab(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SWISSARMYBENCH_INFO", str(tmp_path / "server.json"))
    monkeypatch.delenv("SWISSARMYBENCH_STARTED_BY", raising=False)
    ran: list[Any] = []
    monkeypatch.setattr(desktop, "can_run", lambda: True)
    monkeypatch.setattr(desktop, "main", lambda page=None, info=None: noted(ran, ("app", page), 0))
    monkeypatch.setattr(
        command, "open_in_browser", lambda path, page=None: noted(ran, ("browser", page), True)
    )
    assert run_main(monkeypatch) == 0 and ran == [("app", None)]
    assert run_main(monkeypatch, "open") == 0 and ran[-1] == ("app", None)
    assert run_main(monkeypatch, "open", "--browser") == 0 and ran[-1] == ("browser", None)
    assert run_main(monkeypatch, "app", "/workbench") == 0 and ran[-1] == ("app", "/workbench")
    # Where the app cannot run (no display, no Qt WebEngine): the browser instead.
    monkeypatch.setattr(desktop, "can_run", lambda: False)
    assert run_main(monkeypatch) == 0 and ran[-1] == ("browser", None)


def test_the_server_only_invocations_stay_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """VS Code's extension (no command, SWISSARMYBENCH_STARTED_BY=vscode) and the older `swissarmybench
    --port N` or `--no-browser` start the server, not the app."""
    started: list[Any] = []
    monkeypatch.setattr(command, "start", lambda port, window=True: started.append((port, window)))
    monkeypatch.setenv("SWISSARMYBENCH_STARTED_BY", "vscode")
    assert run_main(monkeypatch) == 0 and started == [(None, True)]
    monkeypatch.delenv("SWISSARMYBENCH_STARTED_BY")
    assert run_main(monkeypatch, "--port", "8790") == 0 and started[-1] == (8790, True)
    assert run_main(monkeypatch, "--no-browser") == 0 and started[-1] == (None, False)
    assert run_main(monkeypatch, "start", "--no-window") == 0 and started[-1] == (None, False)


def test_the_tray_and_start_at_sign_in_are_said_gone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for old in (("tray",), ("autostart", "on"), ("autostart", "off")):
        assert run_main(monkeypatch, *old) == 0
        assert "no tray icon and no start at sign-in" in capsys.readouterr().out
    # --no-tray, from older scripts, is still taken (and does nothing).
    started: list[Any] = []
    monkeypatch.setattr(command, "start", lambda port, window=True: started.append(window))
    assert run_main(monkeypatch, "start", "--no-tray") == 0 and started == [True]
    # The agent's old app_autostart says it went.
    with pytest.raises(commands.CommandError, match="no tray and no start at sign-in"):
        commands.execute_result("app_autostart", {})
    assert "app_autostart" not in commands.REGISTRY and "app_lifecycle" in commands.REGISTRY


def test_open_address_goes_to_the_app_else_the_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    browsed: list[str] = []
    monkeypatch.setattr("webbrowser.open", browsed.append)
    shown: list[str] = []
    monkeypatch.setattr(desktop, "open_page", lambda address, info=None: noted(shown, address, True))
    address = "http://127.0.0.1:8790/workspace#token=t"
    command.open_address(address)
    assert shown == [address] and browsed == []
    command.open_address(address, browser=True)
    assert browsed == [address]
    monkeypatch.setattr(desktop, "open_page", lambda address, info=None: False)
    command.open_address(address)
    assert browsed == [address, address]


def test_the_door_and_the_agents_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    shell = Shell()
    monkeypatch.setattr("swissarmybench.bootstrap.SystemShell", lambda info_file: shell)
    with make_client(tmp_path) as client:
        said = client.get("/desktop", headers=AGENT).json()
        assert said["name"] == "Swiss Army Bench" and said["running"] is False and said["windows"] == []
        opened = client.post("/desktop/open", headers=AGENT, json={"page": "workbench"})
        assert opened.status_code == 200 and opened.json() == {"opened": "workbench"}
        assert shell.opened == ["/workbench"]
        assert client.post("/desktop/open", headers=AUTH, json={}).json() == {"opened": "home"}
        said = client.get("/desktop", headers=AUTH).json()
        assert said["running"] is True
        assert said["windows"] == [{"kind": "home", "title": "Orders", "page": "/workspace"}]
        assert client.post("/desktop/open", headers=AGENT, json={"page": "settings"}).status_code == 400
        assert client.get("/desktop").status_code == 401  # the token, as on every route
    assert {"desktop_status", "desktop_open"} <= set(commands.REGISTRY)


def test_where_the_app_cannot_run_open_says_so(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("swissarmybench.bootstrap.SystemShell", lambda info_file: Shell(can=False))
    with make_client(tmp_path) as client:
        refused = client.post("/desktop/open", headers=AGENT, json={"page": "home"})
        assert refused.status_code == 400 and "Qt WebEngine" in refused.text


def test_the_service_keeps_only_what_the_agent_reads() -> None:
    class Audit:
        def __init__(self) -> None:
            self.said: list[Any] = []

        def write(self, actor: str, action: str, dataset: str | None = None, **details: Any) -> None:
            self.said.append((actor, action, details))

    audit = Audit()
    shell = Shell()
    service = Desktop(shell, audit, "6.12.0")
    assert asyncio.run(service.open({"page": "blades"}, "agent")) == {"opened": "blades"}
    assert shell.opened == ["/catalog"] and audit.said == [("agent", "desktop_open", {"page": "blades"})]
    said = asyncio.run(service.status())
    assert said["qt"] == "6.12.0" and "name" not in said["windows"][0]


def test_the_update_helper_ends_the_app_by_desktop_json(tmp_path: Path) -> None:
    from swissarmybench.domain import desktop as rules
    from swissarmybench.server import updater

    record = tmp_path / rules.RECORD
    record.write_text(json.dumps(rules.record(os.getpid(), 5000, "k" * 43)), encoding="utf-8")
    assert updater._app_pid(record) == os.getpid()
    record.write_text(json.dumps(rules.record(2**22 + 7, 5000, "k" * 43)), encoding="utf-8")
    assert updater._app_pid(record) == 0  # gone: nothing to end


def test_the_pyside6_wheels_are_the_servers_and_pinned() -> None:
    import tomllib

    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    server = project["optional-dependencies"]["server"]
    for pinned in ("PySide6-Essentials==6.12.0", "PySide6-Addons==6.12.0", "PySide6-WebEngine==6.12.0.140"):
        assert pinned in server
    assert not any(d.lower().startswith(("pystray", "pillow")) for d in server)
    assert not any("pyside" in d.lower() for d in project["dependencies"])  # the plain client: none
