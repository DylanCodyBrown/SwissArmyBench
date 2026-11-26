"""The Desktop shell, really run: Qt WebEngine (Chromium) drawing off screen, the server a real process the
shell starts. Skipped where PySide6's Qt WebEngine is not installed
(the Desktop extension's own dependency, never the base's). Made-up data only.

tests/desktop_drive.py drives the windows themselves; the second test runs the shell as its own process
(`python -m swissarmybench.server app`), as `swissarmybench` does, and talks to it as the server does.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _webengine_starts() -> str:
    """ "" when Qt WebEngine can start here (offscreen); else why not. Installed is not enough: a machine
    without the system libraries it needs (libEGL, NSS, xcb: a bare CI runner) fails at import."""
    try:
        if importlib.util.find_spec("PySide6.QtWebEngineWidgets") is None:
            return "PySide6 with Qt WebEngine is not installed here"
    except (ImportError, ValueError):
        return "PySide6 with Qt WebEngine is not installed here"
    probe = "from PySide6.QtWebEngineWidgets import QWebEngineView"
    env = os.environ | {"QT_QPA_PLATFORM": "offscreen", "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox"}
    try:
        done = subprocess.run(  # noqa: S603 (this Python)
            [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60, env=env, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"Qt WebEngine could not start here: {error}"
    if done.returncode != 0:
        last = (done.stderr.strip().splitlines() or ["(no message)"])[-1]
        return f"Qt WebEngine cannot start here (its system libraries are missing?): {last[:200]}"
    return ""


_WHY_NOT = (
    # A CI runner has no graphics: Qt WebEngine falls back to software rendering and the home page did not
    # load in a minute on GitHub's (release run 57). These real-app tests run on a desktop before tagging, as
    # the browser tests do; SWISSARMYBENCH_DESKTOP_TEST=1 runs them anywhere.
    "on a CI runner (no graphics): run on a desktop, or set SWISSARMYBENCH_DESKTOP_TEST=1"
    if os.environ.get("CI") and not os.environ.get("SWISSARMYBENCH_DESKTOP_TEST")
    else _webengine_starts()
)
pytestmark = pytest.mark.skipif(bool(_WHY_NOT), reason=_WHY_NOT or "runs")


def environment(folder: Path) -> dict[str, str]:
    (folder / "home").mkdir(parents=True, exist_ok=True)
    (folder / "state").mkdir(parents=True, exist_ok=True)
    paths = [str(ROOT / "extensions" / "streamlit" / "src")]
    return os.environ | {
        "HOME": str(folder / "home"),
        "USERPROFILE": str(folder / "home"),
        "SWISSARMYBENCH_STATE": str(folder / "state"),
        "SWISSARMYBENCH_INFO": str(folder / "state" / "server.json"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(folder / "home" / "SwissArmyBench"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(folder / "home" / "Projects"),
        "SWISSARMYBENCH_UPDATE_FEED": "none",
        "SWISSARMYBENCH_EXTENSIONS": "streamlit",
        # The server's life, short: it stops 2 s after the app's last window, 3 s after a client's request.
        "SWISSARMYBENCH_LIFE_GRACE": "2",
        "SWISSARMYBENCH_LIFE_IDLE": "3",
        "SWISSARMYBENCH_LIFE_START_GRACE": "60",
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
    # window.print(): Print to PDF, named for the page; the page's @page size (Letter landscape), its print
    # layout held until the shell's afterprint once the PDF was written (the Save dialog took 2 s).
    assert (
        said["print_dialog"][0] == "Print to PDF" and said["pdf_head"] == "%PDF-" and said["pdf_size"] > 1000
    )
    assert said["page_knows_the_app"] is True
    assert [round(float(n)) for n in said["pdf_mediabox"]] == [0, 0, 792, 612]
    assert said["afterprint"] == "[true]"
    assert said["windows_at_start"] == 1
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
    assert said["status_windows"] == ["home", "notebooks"] and said["status_has_no_token"]
    assert said["channel_opened"] == "scripts" and "error" in said["bad_key"]
    # The Workbench's place remembered and used again (within the screen).
    assert said["remembered"] == {"x": 40, "y": 50, "w": 900, "h": 640, "maximized": False}
    x, y, w, h = said["reopened_at"]
    sw, sh = said["screen"]
    assert ((x, y) == (40, 50) and (w, h) == (min(900, sw), min(640, sh))) or (x, y, w) == (
        40,
        50,
        min(900, sw),
    )
    # Open in browser: the page in the system's browser (stood in), with the token as the launch has it.
    assert said["open_in_browser"].endswith("/scripts") and said["open_in_browser_has_token"]
    assert said["catalog_reused"]
    # Files: handed over the channel and dropped on a window, each read by its real path.
    assert said["file_answer"] == {"ok": True} and said["file_origin"] == "file"
    assert said["drop_accepted"] and said["drop_origin"] == "file"
    assert said["windows_grew_on_drop"] == 0  # into the window it was dropped on, never another
    assert said["opened_files"] == ["regions.csv", "drop_me.csv"]
    # The browser's keys are the app's: Ctrl+Tab, Ctrl+W a tab (the window stays), Ctrl+Shift+T it again;
    # the Workbench's F5 is its own; Ctrl+W with no document closes the window.
    assert said["ctrl_tab_moved"] and said["ctrl_w_closed_tab"] and said["ctrl_w_kept_window"]
    assert said["ctrl_shift_t_reopened"] and said["workbench_f5_kept_page"] is True
    # F11: the window itself full screen with the page's, and back (2026-11-21).
    assert said["f11_window_full"] is True and said["f11_window_back"] is True
    # The Canvas's F11 too (2026-11-26): the board alone and the window full screen; Escape back as it was.
    assert said["canvas_f11_full"] is True and said["canvas_escape_back"] is True
    assert said["ctrl_w_closed_empty_window"]
    # The profile in the state folder: cookies and local storage kept there.
    assert {"Cookies", "Local Storage"} <= set(said["profile_folder"])
    # Every window closed: the app told the server, and the server stopped.
    assert said["told_server_closed"] == 1
    assert said["closing_stopped_server"] and said["windows_after_close"] == 0


def test_the_app_process_one_at_a_time_told_by_the_server_and_its_server_follows_it(tmp_path: Path) -> None:
    env = environment(tmp_path)
    info = tmp_path / "state" / "server.json"
    first = subprocess.Popen(
        [sys.executable, "-m", "swissarmybench.server", "app"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    old = {k: os.environ.get(k) for k in ("SWISSARMYBENCH_INFO", "QT_QPA_PLATFORM")}
    os.environ.update({"SWISSARMYBENCH_INFO": str(info), "QT_QPA_PLATFORM": env["QT_QPA_PLATFORM"]})
    try:
        from swissarmybench.server import desktop as launch
        from swissarmybench.server.lifecycle import page_address, running_server

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
        shell = launch.running_app(info)
        assert shell is not None and shell[0] == first.pid
        # A second start of the app hands its page to the first and ends.
        second = subprocess.run(
            [sys.executable, "-m", "swissarmybench.server", "app", "/catalog"],
            env=env,
            timeout=60,
            check=False,
        )
        assert second.returncode == 0
        wait(lambda: "catalog" in {w["kind"] for w in launch.status(info)["windows"]})
        # The server's "open a page" (the launch, `swissarmybench open`, desktop_open) goes to the app.
        assert launch.open_page(page_address(server, "/scripts"), info)  # the Scripts page (2026-11-21)
        wait(lambda: "scripts" in {w["kind"] for w in launch.status(info)["windows"]})
        assert first.poll() is None
        # `swissarmybench stop`'s quit, over the channel: every window closed (each one's place kept), the
        # server told, the app ended; the server follows.
        # (quit_app's own wait sees this test's child as a zombie until it is reaped: the message, then wait.)
        assert launch.tell({"quit": True}, info) == {"ok": True}
        assert first.wait(30) == 0
        places = json.loads((tmp_path / "state" / "desktop" / "windows.json").read_text(encoding="utf-8"))
        assert {"home", "catalog", "scripts"} <= set(places)
        from swissarmybench.server.lifecycle import read_info as connection

        wait(lambda: connection(info) is None, 60)
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


# ===== White screen after an update, 2026-11-22 =====


def _web_copy(target: Path) -> Path:
    """This checkout's front end (its Blazor build: `python blazor/publish.py`) copied."""
    from swissarmybench.settings import Settings

    built = Settings().blazor_root
    if not (built / "index.html").is_file():
        pytest.skip("The front end is not built here (python blazor/publish.py).")
    shutil.copytree(built, target)
    return target


def _new_build(web: Path) -> None:
    """An update's new build, in place: the page's own script changed (what an update's install does: its
    files new, their times and sizes may be the same)."""
    shell = web / "js" / "shell.js"
    shell.write_text(shell.read_text(encoding="utf-8") + "\n// a newer build\n", encoding="utf-8")


def _serve(env: dict[str, str], info: Path) -> subprocess.Popen[bytes]:
    """The server, up before the app (an update's helper starts it, and it starts the app)."""
    from swissarmybench.server.lifecycle import running_server

    server = subprocess.Popen(
        [sys.executable, "-m", "swissarmybench.server", "start", "--no-window"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 90
    while running_server(info) is None:
        assert time.monotonic() < deadline and server.poll() is None, "the server did not start"
        time.sleep(0.2)
    return server


def _stop(server: subprocess.Popen[bytes], info: Path) -> None:
    from swissarmybench.server.lifecycle import request_stop

    request_stop(info)
    try:
        server.wait(30)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(10)


def _app_start(env: dict[str, str], folder: Path, name: str, version: str) -> dict[str, Any]:
    result = folder / f"{name}.json"
    subprocess.run(  # noqa: S603 (this Python, this checkout's driver)
        [sys.executable, str(ROOT / "tests" / "desktop_update_drive.py"), str(result), version],
        env=env,
        capture_output=True,
        timeout=180,
        check=False,
    )
    said: dict[str, Any] = json.loads(result.read_text(encoding="utf-8"))
    assert "error" not in said, said["error"]
    return said


def test_the_first_window_after_an_update_shows_the_app(tmp_path: Path) -> None:
    """The app run once (its profile's cache filled), then an update: a new version with a new build, its
    server up first, the same profile folder. The first window shows the app, and each version has its own
    cache folder (the older one gone). Before the fix the shell cleared the cache in the background as the
    first page loaded, and the window stayed white (it drew on the next start)."""
    from swissarmybench import __version__
    from swissarmybench.domain import desktop as rules

    env = environment(tmp_path)
    info = tmp_path / "state" / "server.json"
    old_web = _web_copy(tmp_path / "web-old")
    server = _serve(env | {"SWISSARMYBENCH_BLAZOR_ROOT": str(old_web)}, info)
    try:
        before = _app_start(env, tmp_path, "before", __version__)
    finally:
        _stop(server, info)
    assert before["drew"], before
    assert rules.cache_folder(__version__) in before["profile"] and before["mark"] == __version__
    new_web = tmp_path / "web-new"
    old_web.rename(new_web)
    _new_build(new_web)
    newer = f"{__version__}.post1"
    server = _serve(env | {"SWISSARMYBENCH_BLAZOR_ROOT": str(new_web)}, info)
    try:
        after = _app_start(env, tmp_path, "after", newer)
    finally:
        _stop(server, info)
    assert after["drew"], after
    assert after["loads"][-1] == "loaded" and after["address"].endswith("/blazor/")
    assert rules.cache_folder(newer) in after["profile"]
    assert rules.cache_folder(__version__) not in after["profile"] and after["mark"] == newer
    assert {"Cookies", "Local Storage"} <= set(after["profile"])  # kept across the update


def test_a_page_that_did_not_load_is_loaded_again(tmp_path: Path) -> None:
    """A load that failed (nothing answered yet) is loaded again until it loads; a page whose process ended
    is loaded again too."""
    env = environment(tmp_path)
    said = _app_start(env, tmp_path, "retry", "retry")
    assert said["drew"], said
    assert said["first"][0] == "failed" and said["first"][-1] == "loaded"
    assert said["page_process"] and said["after_kill"][-2:] == ["page process ended", "loaded"]
