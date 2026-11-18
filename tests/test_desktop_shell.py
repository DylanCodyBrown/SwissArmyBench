"""The Desktop shell, really run: Qt WebEngine (Chromium) drawing off screen, the server a real process the
shell starts. Skipped where PySide6's Qt WebEngine is not installed
(the Desktop extension's own dependency, never the base's). Made-up data only.

tests/desktop_drive.py drives the windows themselves; the second test runs the shell as its own process
(`python -m swissarmybench_desktop`), as `swissarmybench desktop` does, and talks to it as the server does.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _has_webengine() -> bool:
    try:
        return importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None
    except (ImportError, ValueError):
        return False


pytestmark = pytest.mark.skipif(
    not _has_webengine(), reason="PySide6 with Qt WebEngine is not installed here"
)


def environment(folder: Path) -> dict[str, str]:
    (folder / "home").mkdir(parents=True, exist_ok=True)
    (folder / "state").mkdir(parents=True, exist_ok=True)
    paths = [str(ROOT / "extensions" / "desktop" / "src"), str(ROOT / "extensions" / "streamlit" / "src")]
    return os.environ | {
        "HOME": str(folder / "home"),
        "USERPROFILE": str(folder / "home"),
        "SWISSARMYBENCH_STATE": str(folder / "state"),
        "SWISSARMYBENCH_INFO": str(folder / "state" / "server.json"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(folder / "home" / "SwissArmyBench"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(folder / "home" / "Projects"),
        "SWISSARMYBENCH_UPDATE_FEED": "none",
        "SWISSARMYBENCH_EXTENSIONS": "streamlit,desktop",
        "QT_QPA_PLATFORM": os.environ.get("SAB_TEST_QPA", "offscreen"),
        # Chromium's sandbox needs a user that is not root (a container runs tests as root).
        "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox",
        "PYTHONPATH": os.pathsep.join([*paths, str(ROOT), os.environ.get("PYTHONPATH", "")]),
    }


def test_the_shell_does_what_a_browser_did(tmp_path: Path) -> None:
    done = subprocess.run(  # noqa: S603 (this Python, this checkout's driver)
        [sys.executable, str(ROOT / "tests" / "desktop_drive.py"), str(tmp_path)],
        env=environment(tmp_path),
        capture_output=True,
        text=True,
        timeout=400,
        check=False,
    )
    said: dict[str, Any] = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert "error" not in said, said.get("error", "") + done.stderr[-2000:]
    # The shell started the server and showed the home page, its token taken by the page.
    assert said["server_started_by_shell"] and said["home_kind"] == "home"
    assert said["home_name"] == "sab-home" and said["cookie_page_without_token"]
    # window.open: a second window; the same name again: no third; focus() by name raises the home window.
    assert said["window_open_made_window"] == 2 and said["named_window_reused"] == 2
    assert said["home_raised_by_name"] >= 1 and said["windows_after_focus"] == 2
    # The Export's download: the Save dialog (stood in) asked with the suggested name; the file there.
    assert said["download_dialog"] == ["Save", "orders.csv"]
    assert said["download_text"].splitlines()[:2] == ["order_id,region,amount", "1,North,120.5"]
    assert said["download_status"] == "Saved orders.csv" and said["download_show_in_folder"]
    # window.print(): Print to PDF, named for the page.
    assert (
        said["print_dialog"][0] == "Print to PDF" and said["pdf_head"] == "%PDF-" and said["pdf_size"] > 1000
    )
    # Outside addresses: the system's browser (stood in), never a window of the shell's.
    assert said["outside"] == [
        "https://example.com/release-notes",
        "https://example.com/device",
        "https://example.com/elsewhere",
    ]
    assert said["home_still_ours"] and said["windows_after_outside"] == 2
    # The clipboard for the app: off screen no window has the system's focus, which Chromium asks for.
    assert said["clipboard"] == "North,120.50" or "not focused" in said["clipboard"]
    assert said["devtools_window"]
    # The channel: what is open (no token in it); a page opened; another key refused.
    assert said["status_windows"] == ["home", "workbench"] and said["status_has_no_token"]
    assert said["channel_opened"] == "catalog" and "error" in said["bad_key"]
    # The Workbench's place remembered and used again (within the screen).
    assert said["remembered"] == {"x": 40, "y": 50, "w": 900, "h": 640, "maximized": False}
    x, y, w, h = said["reopened_at"]
    sw, sh = said["screen"]
    assert ((x, y) == (40, 50) and (w, h) == (min(900, sw), min(640, sh))) or (x, y, w) == (
        40,
        50,
        min(900, sw),
    )
    # The tray's menu as Qt draws it; its Open the blades page raised the blades window, no new one.
    assert said["tray_menu"][0] == "Open" and "Stop and quit" in said["tray_menu"]
    assert "Open the Workbench" in said["tray_menu"] and said["tray_blades_reused_catalog"]
    # The profile in the state folder: cookies and local storage kept there.
    assert {"Cookies", "Local Storage"} <= set(said["profile_folder"])
    # Quit (the tray's Stop and quit): the server stopped, every window closed.
    assert said["quit_stopped_server"] and said["windows_after_quit"] == 0


def test_the_shell_process_one_at_a_time_and_told_by_the_server(tmp_path: Path) -> None:
    env = environment(tmp_path)
    info = tmp_path / "state" / "server.json"
    first = subprocess.Popen(
        [sys.executable, "-m", "swissarmybench_desktop"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    old = {k: os.environ.get(k) for k in ("SWISSARMYBENCH_INFO", "QT_QPA_PLATFORM")}
    os.environ.update({"SWISSARMYBENCH_INFO": str(info), "QT_QPA_PLATFORM": env["QT_QPA_PLATFORM"]})
    try:
        from swissarmybench.server.lifecycle import page_address, running_server
        from swissarmybench_desktop.server import launch

        def wait(check: Any, seconds: float = 90.0) -> Any:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                got = check()
                if got:
                    return got
                time.sleep(0.2)
            raise AssertionError("waited too long")

        server = wait(lambda: running_server(info))
        windows = wait(
            lambda: [w for w in launch.status(info)["windows"] if w["kind"] == "home" and w["title"]]
        )
        assert "token" not in json.dumps(windows)
        shell = launch.running_shell(info)
        assert shell is not None and shell[0] == first.pid
        # A second shell hands its page to the first and ends.
        second = subprocess.run(
            [sys.executable, "-m", "swissarmybench_desktop", "/catalog"], env=env, timeout=60, check=False
        )
        assert second.returncode == 0
        wait(lambda: "catalog" in {w["kind"] for w in launch.status(info)["windows"]})
        # The server's "open a page" (the launch, `swissarmybench open`, the tray's Open) goes to the shell.
        assert launch.open_page(page_address(server, "/workbench"), info)
        wait(lambda: "workbench" in {w["kind"] for w in launch.status(info)["windows"]})
        assert first.poll() is None
    finally:
        from swissarmybench.server.lifecycle import read_info, request_stop

        if read_info(info) is not None:
            request_stop(info)
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        first.terminate()
        first.wait(30)
