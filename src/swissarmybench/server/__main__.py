"""The `swissarmybench` command: start, stop or check the local server.

    uv run swissarmybench                 start (reuses the last port when it is free)
    uv run swissarmybench --port 8790     start on exactly this port, or fail clearly
    uv run swissarmybench status          is one running, and where
    uv run swissarmybench open            open the running app's page in the browser
    uv run swissarmybench open sales.sab  open a project (starting the app when it is not running)
    uv run swissarmybench stop            ask the running one to shut down
    uv run swissarmybench tray            the tray icon (`start` starts it too, unless --no-tray)
    uv run swissarmybench autostart on    start at sign-in (the tray, which starts the server); off, status
    uv run swissarmybench start --background   detached, no console, returns at once

Started by hand, it opens the app's page in the default browser once it listens (--no-browser not to),
and prints the page's full address. The token is in the address's fragment (#token=...), which a
browser never sends over the network.

A server started here, by the tray or at sign-in never stops on its own: only Stop and quit,
`swissarmybench stop` or signing out stop it, and the tray starts it again if it dies. VS Code's
extension runs this command with SWISSARMYBENCH_STARTED_BY=vscode; a server it started stops once no
VS Code window has been connected for VSCODE_GONE_SECONDS.

Start-up order matters (server/lifecycle.py): take the instance lock, refuse if a healthy server
is already running, bind and listen, write the connection file, serve, delete the file on every
way out. A fresh token is made on every start, so grid tabs from an earlier run must be reopened
from a push.
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from types import FrameType

import uvicorn

from swissarmybench import __version__
from swissarmybench.adapters.live_updates import LiveUpdates
from swissarmybench.adapters.state_files import info_file_path, remove_info_file, write_info_file
from swissarmybench.renamed import env, move_state_folder
from swissarmybench.server.app import create_app
from swissarmybench.server.autostart import Autostart
from swissarmybench.server.lifecycle import (
    AlreadyRunningError,
    AlreadyStartingError,
    InstanceLock,
    PortError,
    on_exit,
    open_listener,
    post_json,
    remember_port,
    request_stop,
    running_server,
)
from swissarmybench.server.lifecycle import (
    page_address as page_address,
)
from swissarmybench.server.routes_processes import QuietHeartbeats
from swissarmybench.server.tray import server_command, start_tray
from swissarmybench.server.updater import detached
from swissarmybench.settings import Settings

# Long enough to ride out a window reload (the extension reconnects within a few seconds).
VSCODE_GONE_SECONDS: float = 30.0


class _Server(uvicorn.Server):
    """uvicorn's server, but a stop by signal (Ctrl+C, the system shutting down) first lets the waiting
    listeners answer, as `swissarmybench stop` does."""

    def __init__(self, config: uvicorn.Config, on_exit: Callable[[], None]) -> None:
        super().__init__(config)
        self._on_exit = on_exit

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        try:
            self._on_exit()
        except Exception:  # noqa: S110 (never in the way of stopping)
            pass
        super().handle_exit(sig, frame)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Swiss Army Bench server on localhost.")
    parser.add_argument(
        "command",
        nargs="?",
        default="start",
        choices=["start", "stop", "status", "open", "tray", "autostart"],
    )
    parser.add_argument(
        "switch", nargs="?", help="autostart: on, off or status; open: a project's .sab file (or folder)."
    )
    parser.add_argument("--port", type=int, default=None, help="Exact port; 0 picks any free one.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the page when it starts.")
    parser.add_argument("--no-tray", action="store_true", help="Start without the tray icon.")
    parser.add_argument(
        "--background", action="store_true", help="Start detached, with no console, and return at once."
    )
    args = parser.parse_args()
    path = info_file_path()

    if args.command == "autostart" and args.switch not in (None, "on", "off", "status"):
        parser.error("autostart takes on, off or status.")
    if args.command == "open" and args.switch:
        sys.exit(open_project(args.switch, path))
    if args.command == "open":
        if not open_page(path):
            print("Swiss Army Bench is not running. Start it with: swissarmybench start")
            sys.exit(1)
        return
    if args.command == "tray":
        from swissarmybench.server.tray import run_tray

        sys.exit(run_tray(path, Settings().state_dir / "server_events.json"))
    if args.command == "autostart":
        sys.exit(autostart(args.switch or "status"))
    if args.command == "start" and args.background:
        start_in_background(args.port, browser=not args.no_browser, tray=not args.no_tray)
        return

    if args.command == "status":
        info = running_server(path)
        if info is None:
            print("Swiss Army Bench is not running.")
            sys.exit(1)
        print(f"Running on http://127.0.0.1:{info['port']} (process {info.get('pid')}).")
        return
    if args.command == "stop":
        if not request_stop(path):
            print("Swiss Army Bench is not running.")
            return
        for _ in range(50):
            if running_server(path) is None:
                print("Stopped.")
                return
            time.sleep(0.1)
        print("Asked the server to stop; it has not exited yet.")
        sys.exit(1)

    try:
        start(args.port, browser=not args.no_browser, tray=not args.no_tray)
    except AlreadyRunningError as error:
        if not args.no_tray and env("SWISSARMYBENCH_TRAY", "1") != "0":
            start_tray()  # its tray, if it has none (a second one ends at once)
        # Already running: open its page, which is what someone starting it again wants.
        if not args.no_browser and env("SWISSARMYBENCH_NO_BROWSER", "") != "1" and open_page(path):
            print("Swiss Army Bench is already running: its page is open in your browser.")
            return
        print(error, file=sys.stderr)
        sys.exit(1)
    except (AlreadyStartingError, PortError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)


def open_page(path: Path | None = None) -> bool:
    """Open the running app's page in the default browser. False when none is running."""
    info = running_server(path or info_file_path())
    if info is None:
        return False
    address = page_address(info)
    print(address)
    webbrowser.open(address)
    return True


def open_project(target: str, path: Path, wait_seconds: float = 30.0) -> int:
    """`swissarmybench open sales.sab` (a double-click on a .sab runs it): the app started in the background
    when it is not running, the project opened in it (the page asks first when unsaved work would be lost),
    and the home window shown when none is open."""
    file = Path(target).expanduser()
    if not file.exists():
        print(f"{file} is not there.", file=sys.stderr)
        return 1
    info = running_server(path)
    if info is None:
        start_in_background(None, browser=False)
        deadline = time.monotonic() + wait_seconds
        while info is None and time.monotonic() < deadline:
            time.sleep(0.3)
            info = running_server(path)
        if info is None:
            print(
                "Swiss Army Bench did not start: run swissarmybench start, then open the project.",
                file=sys.stderr,
            )
            return 1
    try:
        answer = post_json(info, "/project/open", {"path": str(file.resolve()), "ask": True})
    except OSError as error:
        print(f"{file.name} could not be opened: {error}", file=sys.stderr)
        return 1
    if not (isinstance(answer, dict) and answer.get("page")):
        webbrowser.open(page_address(info))  # no home window is open: one, showing the project
    print(f"Opened {file.name}." if not (isinstance(answer, dict) and answer.get("asked")) else
          f"{file.name}: the app asks about the unsaved work open now.")  # fmt: skip
    return 0


def start_in_background(port: int | None, browser: bool = True, tray: bool = True) -> None:
    """`swissarmybench start --background`: the server detached, with no console window, outliving this
    command, which returns at once. The tray and the sign-in entry start the server this way."""
    detached(server_command(port, browser, tray))
    print("Swiss Army Bench is starting in the background.")


def autostart(switch: str) -> int:
    """`swissarmybench autostart on|off|status`: start at sign-in (server/autostart.py)."""
    entry = Autostart()
    try:
        if switch in ("on", "off"):
            entry.set(switch == "on")
    except OSError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"{entry.label}: {'on' if entry.status() else 'off'}")
    return 0


def start(port: int | None, browser: bool = True, tray: bool = True) -> None:
    # Swiss Army Bench was SwissArmyGrid: its state folder moves on the first start (renamed.py).
    moved = move_state_folder(in_use=lambda old_info: running_server(old_info) is not None)
    if moved:
        print(moved, file=sys.stderr)
    settings = Settings()
    path = info_file_path()
    try:
        lock = InstanceLock(path)  # held until this process ends
    except AlreadyStartingError:
        running = running_server(path)
        if running is not None:
            raise AlreadyRunningError(running) from None  # say where, when it's up already
        raise
    existing = running_server(path)  # a server from before the lock existed (an older version)
    if existing is not None:
        raise AlreadyRunningError(existing)
    started_by = env("SWISSARMYBENCH_STARTED_BY", "cli")

    listener = open_listener(port, settings.state_dir / "last_port")
    actual_port: int = listener.getsockname()[1]
    token: str = secrets.token_urlsafe(32)

    server: uvicorn.Server | None = None

    def release() -> None:
        # Every waiting listener (each Workbench kernel and Python session has one) answers now, so
        # the stop never waits on them.
        app.state.ctx.sessions.release_waiters()

    def stop_soon() -> None:
        release()
        if server is not None:
            server.should_exit = True

    app = create_app(actual_port, token, settings, on_shutdown=stop_soon)
    config = uvicorn.Config(app, log_level="info", timeout_graceful_shutdown=3)
    # uvicorn has set up its loggers by now; keep the sessions' heartbeats out of the access log.
    logging.getLogger("uvicorn.access").addFilter(QuietHeartbeats())
    server = _Server(config, release)

    on_exit(lambda: remove_info_file(path, token))
    remember_port(settings.state_dir / "last_port", actual_port)
    write_info_file(
        path,
        {
            "port": actual_port,
            "token": token,
            "max_dataset_bytes": settings.max_dataset_bytes,
            "pid": os.getpid(),
            "version": __version__,
            "started": time.time(),
            # Who started it, and from which install: VS Code's status bar item tells its own
            # server from one started by hand or from another install (another version).
            "started_by": started_by,
            "executable": sys.executable,
        },
    )
    print(f"Swiss Army Bench {__version__} on http://127.0.0.1:{actual_port}  (connection file: {path})")
    address = page_address({"port": actual_port, "token": token})
    print(f"Open it: {address}")
    if browser and started_by != "vscode" and env("SWISSARMYBENCH_NO_BROWSER", "") != "1":
        # The socket already listens: a browser that asks now waits for the server's first answer.
        threading.Timer(0.5, webbrowser.open, args=(address,)).start()
    # The tray, as its own process (Windows and macOS; Linux on a desktop), unless --no-tray or VS Code
    # started this server (it has its own status bar item); SWISSARMYBENCH_TRAY=0 for tests.
    if tray and started_by != "vscode" and env("SWISSARMYBENCH_TRAY", "1") != "0":
        start_tray()
    if started_by == "vscode":
        live: LiveUpdates = app.state.ctx.live
        threading.Thread(
            target=end_with_vscode, args=(live, stop_soon), name="sab-vscode", daemon=True
        ).start()
    try:
        server.run(sockets=[listener])
    finally:
        remove_info_file(path, token)
        lock.release()


def end_with_vscode(live: LiveUpdates, stop: Callable[[], None]) -> None:
    """A server VS Code started ends with VS Code: once no window has been connected for
    VSCODE_GONE_SECONDS (from the start, too, should the extension never connect)."""
    while live.openers_gone_for() < VSCODE_GONE_SECONDS:
        time.sleep(2)
    print(f"No VS Code window for {VSCODE_GONE_SECONDS:.0f} seconds; stopping.")
    stop()


if __name__ == "__main__":
    main()
