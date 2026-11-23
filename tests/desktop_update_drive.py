"""One start of the desktop app after an update, really run under Qt off screen (tests/test_desktop_shell.py
starts it in a process of its own, as an update's restart does): the server is up already (the update's
helper starts it, and it starts the app), the profile folder is the one an earlier version used, and the app
runs as `version`. Did the first window show the app?

    python tests/desktop_update_drive.py <result.json> <version>
    python tests/desktop_update_drive.py <result.json> retry

`retry`: a page of the app that did not load is loaded again. The connection file names a port where nothing
answers yet (the load fails), a small stand-in page starts answering there after the first failure, and the
window shows it; then its page's process is killed, and the page is loaded again.

White screen after an update, 2026-11-22: the shell cleared the profile's HTTP cache (clearHttpCache, which
runs in the background) as a new version started, and the first page, loaded while it ran, never drew.
Writes <result.json>: whether the page drew (its rail there), how long it took, each watched load's outcome,
the address, the profile's folders. Made-up data only (none: the home page).
"""

from __future__ import annotations

import http.server
import json
import os
import signal
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication

import swissarmybench


def main(result: Path, version: str) -> int:
    swissarmybench.__version__ = version  # the version the shell reads (its profile's cache, the record)
    from swissarmybench.domain import desktop as rules
    from swissarmybench.server import desktop_shell as shell_module

    said: dict[str, Any] = {"version": version}
    info_file = Path(os.environ["SWISSARMYBENCH_INFO"])
    app = QApplication(sys.argv[:1])
    shell = shell_module.Shell(app, info_file, start_server=lambda: None)
    window: Any = None
    try:
        started = time.monotonic()
        shell.open_page(rules.HOME_PAGE)
        drew = False
        while time.monotonic() - started < float(os.environ.get("SAB_DRAW_SECONDS", "60")):
            app.processEvents()
            time.sleep(0.02)
            window = next(iter(shell.windows.values()), None)
            if window is None or not rules.is_ours(window.page.url().toString(), shell.port):
                continue
            box: list[Any] = []
            window.page.runJavaScript(
                "!!document.querySelector('.nav-rail') && !!document.querySelector('.status-bar')",
                0,
                box.append,
            )
            asked = time.monotonic()
            while not box and time.monotonic() - asked < 5:
                app.processEvents()
                time.sleep(0.01)
            if box and box[0] is True:
                drew = True
                break
        said["drew"] = drew
        said["seconds"] = round(time.monotonic() - started, 2)
        said["address"] = window.page.url().toString().split("#", 1)[0] if window is not None else ""
        said["loads"] = list(getattr(window, "load_results", [])) if window is not None else []
        said["windows"] = len(shell.windows)
        profile = info_file.parent / "desktop" / "profile"
        said["profile"] = sorted(p.name for p in profile.iterdir()) if profile.is_dir() else []
        mark = profile / rules.VERSION_MARK
        said["mark"] = mark.read_text(encoding="utf-8") if mark.is_file() else ""
    except Exception:
        said["error"] = traceback.format_exc()
    finally:
        shell.closing = True  # this start is over: the server is the test's to stop, not told here
        shell.shutdown()
        result.write_text(json.dumps(said, indent=2), encoding="utf-8")
    return 0 if said.get("drew") else 1


STAND_IN = (
    b"<!doctype html><html><head><meta charset='utf-8'><title>Stand-in</title></head>"
    b"<body><nav class='nav-rail'></nav><footer class='status-bar'></footer></body></html>"
)


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(STAND_IN)

    def log_message(self, *args: Any) -> None:
        pass


def retry(result: Path) -> int:
    from swissarmybench.domain import desktop as rules
    from swissarmybench.server import desktop_shell as shell_module

    rules.LOAD_WAIT_SECONDS = 10.0
    rules.LOAD_TRIES = 5  # the stand-in starts as the second load may already have failed
    said: dict[str, Any] = {}
    info_file = Path(os.environ["SWISSARMYBENCH_INFO"])
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    info_file.parent.mkdir(parents=True, exist_ok=True)
    info_file.write_text(json.dumps({"port": port, "token": "t" * 43, "pid": os.getpid()}), encoding="utf-8")
    app = QApplication(sys.argv[:1])
    shell = shell_module.Shell(app, info_file, start_server=lambda: None)
    server: http.server.HTTPServer | None = None

    def wait(check: Any, seconds: float) -> Any:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            got = check()
            if got:
                return got
            time.sleep(0.02)
        raise TimeoutError(str(said))

    def drew(window: Any) -> bool:
        box: list[Any] = []
        window.page.runJavaScript("!!document.querySelector('.nav-rail')", 0, box.append)
        wait(lambda: box, 5)
        return box[0] is True

    try:
        window = shell.open_address(rules.address_of(rules.HOME_PAGE, port, "t" * 43))
        assert window is not None
        wait(lambda: "failed" in window.load_results, 30)  # nothing answers: the load failed
        server = http.server.HTTPServer(("127.0.0.1", port), Page)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        wait(lambda: window.load_results[-1:] == ["loaded"] and drew(window), 30)
        said["first"] = list(window.load_results)
        pid = window.page.renderProcessPid()
        said["page_process"] = pid > 0
        os.kill(pid, signal.SIGKILL)  # the page's process gone: loaded again
        wait(lambda: "page process ended" in window.load_results, 15)
        wait(lambda: window.load_results[-1:] == ["loaded"] and drew(window), 30)
        said["after_kill"] = list(window.load_results)
        said["drew"] = True
    except Exception:
        said["error"] = traceback.format_exc()
    finally:
        shell.closing = True
        shell.shutdown()
        if server is not None:
            server.shutdown()
        result.write_text(json.dumps(said, indent=2), encoding="utf-8")
    return 0 if said.get("drew") else 1


if __name__ == "__main__":
    if sys.argv[2] == "retry":
        sys.exit(retry(Path(sys.argv[1])))
    sys.exit(main(Path(sys.argv[1]), sys.argv[2]))
