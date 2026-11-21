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


def test_a_grid_nothing_shows_opens_in_the_app_else_the_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """The running server's fallback (LiveUpdates.fallback) for a push or open_grid with no VS Code window."""
    browsed: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda address: noted(browsed, address, True))
    shown: list[str] = []
    monkeypatch.setattr(desktop, "open_page", lambda address, info=None: noted(shown, address, True))
    address = "http://127.0.0.1:8790/workspace#token=t&grid=g1"
    assert desktop.show(address) is True and shown == [address] and browsed == []
    monkeypatch.setattr(desktop, "open_page", lambda address, info=None: False)  # the app cannot run here
    assert desktop.show(address) is True and browsed == [address]


def test_stop_quits_the_app_over_its_channel_then_the_server(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from swissarmybench.adapters.desktop import Listener, new_key
    from swissarmybench.domain import desktop as rules

    info = tmp_path / "server.json"
    monkeypatch.setenv("SWISSARMYBENCH_INFO", str(info))
    heard: list[dict[str, Any]] = []
    key = new_key()

    def handle(said: dict[str, Any]) -> dict[str, Any]:
        heard.append(said)
        return {"ok": True}

    listener = Listener(key, handle)
    try:
        # A live process stands in for the app: it "ends" once the quit was heard.
        (tmp_path / "desktop.json").write_text(
            json.dumps(rules.record(os.getpid(), listener.port, key)), encoding="utf-8"
        )
        monkeypatch.setattr(desktop, "process_alive", lambda pid: not heard)
        stopped: list[Path] = []
        monkeypatch.setattr(command, "request_stop", lambda path: noted(stopped, path, False))
        assert run_main(monkeypatch, "stop") == 0
        assert heard == [{"quit": True}] and stopped == [info]
        assert "Stopped." in capsys.readouterr().out
        # No app running: only the server is asked.
        (tmp_path / "desktop.json").unlink()
        assert desktop.quit_app(info) is False
    finally:
        listener.close()


def test_the_door_and_the_agents_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    shell = Shell()
    monkeypatch.setattr("swissarmybench.bootstrap.SystemShell", lambda info_file: shell)
    with make_client(tmp_path) as client:
        said = client.get("/desktop", headers=AGENT).json()
        assert said["name"] == "Swiss Army Bench" and said["running"] is False and said["windows"] == []
        opened = client.post("/desktop/open", headers=AGENT, json={"page": "workbench"})
        assert opened.status_code == 200 and opened.json() == {"opened": "workbench"}
        assert shell.opened == ["/notebooks"]
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
    assert shell.opened == ["/scripts?pane=blades"] and audit.said == [
        ("agent", "desktop_open", {"page": "blades"})
    ]
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


def test_install_sh_adds_the_launcher_and_uninstall_removes_it(tmp_path: Path) -> None:
    """install.sh with a made-up uv on PATH (Linux): the .desktop entry and the icon in ~/.local/share, the
    old tray's sign-in entry taken away, nothing opened on a build machine;
    --uninstall removes the launcher."""
    import subprocess

    root = Path(__file__).resolve().parents[1]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "uv.log"
    (bin_dir / "uv").write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n', encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    script = (root / "installer" / "install.sh").read_text(encoding="utf-8").replace("__VERSION__", "9.9.9")
    (tmp_path / "install.sh").write_text(script, encoding="utf-8")
    wheel = tmp_path / "swissarmybench-9.9.9-py3-none-any.whl"
    wheel.write_bytes(b"made up")
    old = tmp_path / ".config" / "autostart" / "swissarmybench.desktop"
    old.parent.mkdir(parents=True)
    old.write_text("[Desktop Entry]\nExec=/x/python -m swissarmybench.server tray\n", encoding="utf-8")
    env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(tmp_path), "CI": "1"}

    def run(*args: str) -> str:
        done = subprocess.run(  # noqa: S603 (sh, this checkout's installer)
            ["/bin/sh", str(tmp_path / "install.sh"), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout

    said = run(str(wheel), "--no-autostart")  # the gone flag is still taken
    entry = tmp_path / ".local" / "share" / "applications" / "swissarmybench.desktop"
    icon = tmp_path / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps" / "swissarmybench.svg"
    text = entry.read_text(encoding="utf-8")
    assert "Name=Swiss Army Bench" in text and "Icon=swissarmybench" in text and "Exec=" in text
    assert icon.read_text(encoding="utf-8").startswith("<svg") and not old.exists()
    assert "Opening Swiss Army Bench" not in said  # a build machine: nothing opened
    # Open with: `swissarmybench open <file>` for the types it opens; a blade's own type (*.blade.py).
    assert "open %f" in text and "MimeType=text/csv;" in text
    for kind in ("application/vnd.apache.parquet", "spreadsheetml.sheet", "application/x-ipynb+json"):
        assert kind in text
    mime = tmp_path / ".local" / "share" / "mime" / "packages" / "swissarmybench-files.xml"
    assert '<glob pattern="*.blade.py" weight="60"/>' in mime.read_text(encoding="utf-8")
    said = run("--uninstall")
    assert not entry.exists() and not icon.exists() and not mime.exists() and "removed" in said
    assert "tool uninstall swissarmybench" in log.read_text()


def test_the_icon_command_writes_the_launchers_icon(tmp_path: Path) -> None:
    assert command.write_icon(str(tmp_path / "a.ico")) == 0
    data = (tmp_path / "a.ico").read_bytes()
    assert data[:4] == b"\x00\x00\x01\x00" and b"\x89PNG" in data
    assert command.write_icon(str(tmp_path / "a.png")) == 0
    assert (tmp_path / "a.png").read_bytes()[:4] == b"\x89PNG"
    assert command.write_icon(str(tmp_path / "a.gif")) == 2
