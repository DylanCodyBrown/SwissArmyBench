"""Start at sign-in and stay running (the owner, 2026-11-16: "Swiss Army Bench should start itself then
stay running when it's on the computer"): the sign-in entry's contents on each system, written under a
temporary home; on, off and status (the command, the route, the agent); `start --background` returning
at once with the server answering; the installers turning it on, never on a build machine."""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

import pytest

from swissarmybench.server import autostart
from swissarmybench.server.autostart import Autostart, desktop_text, plist_text, shortcut_script
from swissarmybench.server.lifecycle import process_alive, running_server
from tests.conftest import AGENT, AUTH, make_client

ROOT = Path(__file__).resolve().parents[1]
TOOL = Path("/home/ana/.local/share/uv/tools/swissarmybench")


def test_the_tray_runs_from_the_tools_own_python_and_pythonw_on_windows() -> None:
    assert autostart.tray_command(TOOL, "linux") == [
        str(TOOL / "bin" / "python"),
        "-m",
        "swissarmybench.server",
        "tray",
    ]
    windows = autostart.tray_command(Path("C:/Users/ana/AppData/Roaming/uv/tools/swissarmybench"), "win32")
    assert windows[0].endswith("pythonw.exe") and windows[1:] == ["-m", "swissarmybench.server", "tray"]


def test_linux_gets_an_xdg_autostart_entry(tmp_path: Path) -> None:
    entry = Autostart("linux", home=tmp_path, environ={}, command=autostart.tray_command(TOOL, "linux"))
    assert entry.status() is False and entry.label == "Open at login"
    assert entry.set(True) is True
    path = tmp_path / ".config" / "autostart" / "swissarmybench.desktop"
    text = path.read_text()
    assert "[Desktop Entry]" in text and "Type=Application" in text and "Terminal=false" in text
    assert f"Exec={TOOL}/bin/python -m swissarmybench.server tray" in text
    assert entry.set(False) is False and not path.exists()
    # XDG_CONFIG_HOME wins; a path with a space is quoted.
    spaced = Autostart(
        "linux",
        home=tmp_path,
        environ={"XDG_CONFIG_HOME": str(tmp_path / "cfg")},
        command=["/my tools/python", "-m", "x"],
    )
    spaced.set(True)
    assert (
        'Exec="/my tools/python" -m x'
        in (tmp_path / "cfg" / "autostart" / "swissarmybench.desktop").read_text()
    )


def test_macos_gets_a_launch_agent_that_restarts_only_a_crashed_tray(tmp_path: Path) -> None:
    entry = Autostart("darwin", home=tmp_path, environ={}, command=autostart.tray_command(TOOL, "darwin"))
    entry.set(True)
    path = tmp_path / "Library" / "LaunchAgents" / "com.swissarmybench.tray.plist"
    agent = plistlib.loads(path.read_bytes())
    assert agent["Label"] == "com.swissarmybench.tray" and agent["RunAtLoad"] is True
    assert agent["ProgramArguments"] == [str(TOOL / "bin" / "python"), "-m", "swissarmybench.server", "tray"]
    assert agent["KeepAlive"] == {"SuccessfulExit": False}  # Stop and quit (exit 0) ends it for good
    assert entry.status() and entry.label == "Open at login"
    entry.set(False)
    assert not entry.status()


def test_windows_gets_a_startup_folder_shortcut_to_pythonw(tmp_path: Path) -> None:
    ran: list[list[str]] = []

    def run(command: list[str]) -> int:
        ran.append(command)
        Path(entry.path or "").write_text("a shortcut")  # what PowerShell would have made
        return 0

    appdata = tmp_path / "AppData" / "Roaming"
    command = autostart.tray_command(Path("C:/Users/ana/AppData/Roaming/uv/tools/swissarmybench"), "win32")
    entry = Autostart("win32", home=tmp_path, environ={"APPDATA": str(appdata)}, command=command, run=run)
    assert entry.label == "Start with Windows" and entry.status() is False
    assert entry.set(True) is True
    [called] = ran
    assert called[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    script = called[4]
    assert "Startup" in script and "Swiss Army Bench.lnk" in script and "pythonw.exe" in script
    assert "$s.Arguments = '-m swissarmybench.server tray'" in script
    assert (
        entry.path
        == appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Swiss Army Bench.lnk"
    )
    entry.set(False)
    assert not entry.status()
    failing = Autostart(
        "win32", home=tmp_path, environ={"APPDATA": str(appdata)}, command=command, run=lambda c: 1
    )
    with pytest.raises(OSError):
        failing.set(True)
    with pytest.raises(OSError, match="Startup folder"):
        Autostart("win32", home=tmp_path, environ={}).set(True)


def test_the_shortcuts_script_quotes_its_paths() -> None:
    script = shortcut_script(
        Path("C:/Users/o'neil/Startup/Swiss Army Bench.lnk"), ["C:/t/pythonw.exe", "-m", "x"]
    )
    assert "o''neil" in script


def test_the_entries_text_is_stable() -> None:
    assert plist_text(["/p", "-m", "x"]).startswith("<?xml")
    assert desktop_text(["/p", "tray"]).endswith("\n")


def test_the_command_turns_it_on_off_and_says_its_status(tmp_path: Path) -> None:
    home = tmp_path / "home"
    environ = os.environ | {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "APPDATA": str(home / "AppData"),
    }

    def run(*words: str) -> str:
        done = subprocess.run(  # noqa: S603 (this Python, the server's command)
            [sys.executable, "-m", "swissarmybench.server", "autostart", *words],
            capture_output=True,
            text=True,
            timeout=60,
            env=environ,
            check=True,
        )
        return done.stdout.strip()

    if sys.platform == "win32":
        pytest.skip("the Windows shortcut needs PowerShell and WScript: checked on a Windows desktop")
    assert run("status").endswith(": off")
    assert run("on").endswith(": on") and run("status").endswith(": on")
    assert run("off").endswith(": off")


def test_the_route_and_the_agent_switch_it(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        said = client.get("/autostart", headers=AUTH).json()
        assert said["on"] is False and str(tmp_path / "home") in said["entry"]
        assert client.put("/autostart", json={"on": True}, headers=AGENT).json()["on"] is True
        assert Path(client.get("/autostart", headers=AUTH).json()["entry"]).is_file()
        assert client.put("/autostart", json={"on": False}, headers=AUTH).json()["on"] is False
        assert client.put("/autostart", json={"on": "yes"}, headers=AUTH).status_code == 400


def test_start_in_the_background_returns_at_once_and_the_server_answers(tmp_path: Path) -> None:
    environ = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp_path / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp_path / "state"),
        "SWISSARMYBENCH_TRAY": "0",
        "SWISSARMYBENCH_NO_BROWSER": "1",
    }
    began = time.monotonic()
    done = subprocess.run(
        [sys.executable, "-m", "swissarmybench.server", "start", "--background", "--port", "0"],
        capture_output=True,
        text=True,
        timeout=60,
        env=environ,
        check=True,
    )
    returned = time.monotonic() - began
    assert "background" in done.stdout
    info = None
    try:
        for _ in range(300):
            info = running_server(tmp_path / "server.json")
            if info is not None:
                break
            time.sleep(0.1)
        assert info is not None, "the background server never answered"
        assert returned < 10  # it did not wait for the server (which takes a few seconds to start)
        assert info["pid"] != os.getpid() and process_alive(info["pid"])
    finally:
        if info is not None:
            subprocess.run(
                [sys.executable, "-m", "swissarmybench.server", "stop"],
                env=environ,
                timeout=60,
                check=False,
                capture_output=True,
            )


# ===== the installers =====


def test_the_windows_installer_turns_it_on_starts_it_and_never_on_a_build_machine() -> None:
    text = (ROOT / "installer" / "install.ps1").read_text()
    assert "function Quiet" in text  # Windows PowerShell 5.1's safety helper stays
    assert "[switch]$NoAutostart" in text and "[switch]$NoStart" in text
    assert "$env:CI" in text and "SWISSARMYBENCH_NO_AUTOSTART" in text
    assert "autostart on" in text and "start --background" in text


def test_the_unix_installer_does_the_same() -> None:
    text = (ROOT / "installer" / "install.sh").read_text()
    assert "--no-autostart" in text and "--no-start" in text
    assert '"${CI:-}"' in text and "SWISSARMYBENCH_NO_AUTOSTART" in text
    assert "autostart on" in text and "start --background" in text


def test_the_release_workflow_leaves_no_autostart_entry_behind() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "-NoAutostart" in text and "--no-autostart" in text
    assert "autostart status" in text  # and checks there is none


def test_a_status_line_is_on_or_off() -> None:
    assert json.dumps(Autostart("linux", home=Path("/nowhere"), environ={}).to_json())


def test_the_windows_installer_registers_sab_files_for_this_user_only() -> None:
    """A double-click on a .sab opens the project (the owner, 2026-11-16). The registry commands it writes,
    as text: Windows' registry is not here to run them against."""
    text = (ROOT / "installer" / "install.ps1").read_text()
    assert '$Classes = "HKCU:\\Software\\Classes"' in text and "HKLM" not in text  # no administrator
    assert '$ProgId = "SwissArmyBench.Project"' in text
    assert 'SetKey "$Classes\\.sab" $ProgId' in text
    assert 'SetKey "$Classes\\$ProgId\\DefaultIcon" "`"$Icon`",0"' in text
    assert 'SetKey "$Classes\\$ProgId\\shell\\open\\command" "`"$Program`" open `"%1`""' in text
    assert "swissarmybench\\server\\sab-file.ico" in text
    assert text.index("RegisterProjectFiles $Exe") < text.index("start --background")
    # The icon it points at ships in the package (and the Linux desktop's).
    server = ROOT / "src" / "swissarmybench" / "server"
    assert (server / "sab-file.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"
    assert "<svg" in (server / "sab-file.svg").read_text()


def test_the_unix_installer_registers_sab_files_on_a_linux_desktop() -> None:
    text = (ROOT / "installer" / "install.sh").read_text()
    assert '<glob pattern="*.sab"/>' in text and "application/x-swissarmybench-project" in text
    assert 'Exec="$exe" open %f' in text
    assert "xdg-mime default swissarmybench-project.desktop" in text
