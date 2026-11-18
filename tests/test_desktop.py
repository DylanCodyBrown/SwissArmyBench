"""The Desktop extension in the app: listed, its door and agent commands, and the base's hooks it uses
(the launcher's `swissarmybench desktop`, "open a page", the tray). Off, the base is as it was: the browser
opens the page and pystray draws the tray. No Qt here (tests/test_desktop_shell.py runs the real shell)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from swissarmybench import extensions
from swissarmybench.domain import extensions as catalog
from swissarmybench.server import tray as tray_module
from swissarmybench.server.autostart import Autostart
from swissarmybench_desktop import extension as desktop
from swissarmybench_desktop.services.desktop import Desktop
from tests.conftest import AGENT, AUTH, make_client


def noted(into: list[Any], value: Any, answer: Any) -> Any:
    into.append(value)
    return answer


class Shell:
    """The shell as the service sees it, stood in for."""

    def __init__(self, can: bool = True) -> None:
        self.can = can
        self.opened: list[str] = []

    def status(self) -> dict[str, Any]:
        windows = [{"kind": "home", "title": "Orders", "page": "/workspace", "name": "sab-home"}]
        return {"running": bool(self.opened), "tray": True, "windows": windows if self.opened else []}

    def open(self, page: str) -> bool:
        if self.can:
            self.opened.append(page)
        return self.can


@pytest.fixture
def switched_on(monkeypatch: pytest.MonkeyPatch) -> Shell:
    monkeypatch.setenv(extensions.VARIABLE, "streamlit,desktop")
    shell = Shell()
    monkeypatch.setattr(desktop, "SystemShell", lambda info_file: shell)
    return shell


def test_it_is_in_the_catalog_one_click_away() -> None:
    listed = {e["id"]: e for e in catalog.listed(catalog.CATALOG, {}, "1.2.3")}
    assert listed["desktop"]["status"] == "available"
    assert listed["desktop"]["package"] == "swissarmybench-desktop"
    owner = catalog.owner_of("desktop_open")
    assert owner is not None and owner.id == "desktop"
    assert catalog.launcher_words() == ["desktop"]
    assert "Desktop extension" in catalog.needs_words("desktop")
    found = catalog.describe("desktop", desktop.describe)
    assert found is not None and found.id == "desktop" and found.name == "Desktop" and found.adds


def test_off_swissarmybench_desktop_names_the_extension(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from swissarmybench.server import __main__ as command

    monkeypatch.setenv(extensions.VARIABLE, "streamlit,-desktop")
    monkeypatch.setattr(sys, "argv", ["swissarmybench", "desktop"])
    with pytest.raises(SystemExit) as stopped:
        command.main()
    assert stopped.value.code == 1
    assert "needs the Desktop extension" in capsys.readouterr().err


def test_on_swissarmybench_desktop_runs_the_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    from swissarmybench.server import __main__ as command

    monkeypatch.setenv(extensions.VARIABLE, "streamlit,desktop")
    ran: list[str] = []
    monkeypatch.setattr(desktop, "LAUNCHER", {"desktop": lambda: noted(ran, "shell", 0)})
    monkeypatch.setattr(sys, "argv", ["swissarmybench", "desktop"])
    with pytest.raises(SystemExit) as stopped:
        command.main()
    assert stopped.value.code == 0 and ran == ["shell"]


def test_on_the_tray_command_is_the_shells(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from swissarmybench.server import __main__ as command

    monkeypatch.setenv(extensions.VARIABLE, "streamlit,desktop")
    monkeypatch.setenv("SWISSARMYBENCH_INFO", str(tmp_path / "server.json"))
    asked: list[Any] = []
    monkeypatch.setattr(desktop, "run_tray", lambda info, events=None: noted(asked, info, 0))
    monkeypatch.setattr(sys, "argv", ["swissarmybench", "tray"])
    with pytest.raises(SystemExit) as stopped:
        command.main()
    assert stopped.value.code == 0 and asked == [tmp_path / "server.json"]
    # The base reads the hook by its name, never the extension's.
    assert extensions.hook("run_tray") is not None and extensions.hook("nothing_by_this_name") is None
    assert tray_module.tray_available("linux", {"DISPLAY": ":0"}, own_tray=True)
    assert not tray_module.tray_available("linux", {}, own_tray=True)


def test_on_a_page_opens_in_the_shell_off_in_the_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    browsed: list[str] = []
    monkeypatch.setattr("webbrowser.open", browsed.append)
    shelled: list[str] = []
    monkeypatch.setattr(desktop, "open_page", lambda address: noted(shelled, address, True))
    address = "http://127.0.0.1:8790/workspace#token=t"
    # Off (the base as it was): the default browser.
    monkeypatch.setenv(extensions.VARIABLE, "streamlit,-desktop")
    tray_module.open_address(address)
    assert browsed == [address] and shelled == []
    # On: the shell.
    monkeypatch.setenv(extensions.VARIABLE, "streamlit,desktop")
    tray_module.open_address(address)
    assert shelled == [address] and browsed == [address]
    # On, but the shell cannot run here (no Qt, no display): the browser after all.
    monkeypatch.setattr(desktop, "open_page", lambda address: False)
    tray_module.open_address(address)
    assert browsed == [address, address]
    # The tray's Open goes the same way.
    monkeypatch.setattr(desktop, "open_page", lambda address: noted(shelled, address, True))

    class Server:
        def page(self, path: str = "/workspace", extra: str = "") -> str:
            return address + extra

        def running(self) -> bool:
            return True

    tray = tray_module.Tray(Server(), Autostart(home=Path("/nonexistent")))  # type: ignore[arg-type]
    tray.act("open")
    assert shelled[-1] == address


def test_the_door_and_the_agents_commands(switched_on: Shell, tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        said = client.get("/desktop", headers=AGENT).json()
        assert said["name"] == "Desktop" and said["running"] is False and said["windows"] == []
        opened = client.post("/desktop/open", headers=AGENT, json={"page": "workbench"})
        assert opened.status_code == 200 and opened.json() == {"opened": "workbench"}
        assert switched_on.opened == ["/workbench"]
        assert client.post("/desktop/open", headers=AUTH, json={}).json() == {"opened": "home"}
        said = client.get("/desktop", headers=AUTH).json()
        assert said["running"] is True and said["windows"] == [
            {"kind": "home", "title": "Orders", "page": "/workspace"}
        ]
        assert client.post("/desktop/open", headers=AGENT, json={"page": "settings"}).status_code == 400
        assert client.get("/desktop").status_code == 401  # the token, as on every route
        log = client.get("/session-log", headers=AUTH)
        assert log.status_code == 200 and "Opened workbench in the Desktop app" in log.text


def test_where_the_shell_cannot_run_open_says_so(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(extensions.VARIABLE, "streamlit,desktop")
    monkeypatch.setattr(desktop, "SystemShell", lambda info_file: Shell(can=False))
    with make_client(tmp_path) as client:
        refused = client.post("/desktop/open", headers=AGENT, json={"page": "home"})
        assert refused.status_code == 400 and "Qt WebEngine" in refused.text


def test_off_its_door_names_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(extensions.VARIABLE, "streamlit,-desktop")
    with make_client(tmp_path) as client:
        said = client.get("/desktop/open", headers=AGENT)
        assert said.status_code in (404, 409) and "Desktop" in said.text


def test_the_commands_are_registered_with_its_tool_prefix() -> None:
    names = set(desktop.commands())
    assert names == {"desktop_status", "desktop_open"}
    assert all(catalog.owner_of(n) is not None for n in names)


def test_the_service_reads_windows_without_extra_fields() -> None:
    import asyncio

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


def test_install_and_remove_carry_its_wheel_and_the_helper_ends_the_shell(tmp_path: Path) -> None:
    """Install: the base at this version with its wheel (`--with`); Remove: without it. The update's helper
    ends whatever holds tray.json's pid: the shell writes its own there."""
    import os

    from swissarmybench.server import updater
    from swissarmybench_desktop.domain import windows as rules

    wheels = catalog.kept_wheels(catalog.CATALOG, ["streamlit", "desktop"], "1.2.3")
    assert wheels[-1].endswith("/v1.2.3/swissarmybench_desktop-1.2.3-py3-none-any.whl")
    plan = catalog.plan_change(
        current="1.2.3",
        uv="uv",
        tool_python="py",
        python_version="3.12",
        wheels=wheels,
        before=wheels[:1],
        wait_pids=[1],
        info_file="i",
        note_file="n",
    )
    assert any("swissarmybench_desktop" in part for part in plan.install)
    assert not any("swissarmybench_desktop" in part for part in plan.restore)
    tray_file = tmp_path / "tray.json"
    tray_file.write_text(json.dumps(rules.record(os.getpid(), 5000, "k" * 43)), encoding="utf-8")
    assert updater._tray_pid(tray_file) == os.getpid()
