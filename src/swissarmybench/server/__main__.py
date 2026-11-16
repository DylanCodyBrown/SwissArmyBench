"""The `swissarmybench` command: start, stop or check the local server.

    uv run swissarmybench                 start (reuses the last port when it is free)
    uv run swissarmybench --port 8790     start on exactly this port, or fail clearly
    uv run swissarmybench status          is one running, and where
    uv run swissarmybench open            open the running app's page in the browser
    uv run swissarmybench stop            ask the running one to shut down

Started by hand, it opens the app's page in the default browser once it listens (--no-browser not to),
and prints the page's full address. The token is in the address's fragment (#token=...), which a
browser never sends over the network.

Swiss Army Bench lives in VS Code: its extension runs this command when VS Code opens (with
SWISSARMYBENCH_STARTED_BY=vscode), and a server it started stops once no VS Code window has been
connected for VSCODE_GONE_SECONDS. Starting it by hand is for working on Swiss Army Bench itself.

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
from typing import Any

import uvicorn

from swissarmybench import __version__
from swissarmybench.adapters.live_updates import LiveUpdates
from swissarmybench.adapters.state_files import info_file_path, remove_info_file, write_info_file
from swissarmybench.renamed import env, move_state_folder
from swissarmybench.server.app import create_app
from swissarmybench.server.lifecycle import (
    AlreadyRunningError,
    AlreadyStartingError,
    InstanceLock,
    PortError,
    on_exit,
    open_listener,
    remember_port,
    request_stop,
    running_server,
)
from swissarmybench.server.routes_processes import QuietHeartbeats
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
    parser.add_argument("command", nargs="?", default="start", choices=["start", "stop", "status", "open"])
    parser.add_argument("--port", type=int, default=None, help="Exact port; 0 picks any free one.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the page when it starts.")
    args = parser.parse_args()
    path = info_file_path()

    if args.command == "open":
        if not open_page(path):
            print("Swiss Army Bench is not running. Start it with: swissarmybench start")
            sys.exit(1)
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
        start(args.port, browser=not args.no_browser)
    except AlreadyRunningError as error:
        # Already running: open its page, which is what someone starting it again wants.
        if not args.no_browser and env("SWISSARMYBENCH_NO_BROWSER", "") != "1" and open_page(path):
            print("Swiss Army Bench is already running: its page is open in your browser.")
            return
        print(error, file=sys.stderr)
        sys.exit(1)
    except (AlreadyStartingError, PortError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)


def page_address(info: dict[str, Any]) -> str:
    """The app's page with its token in the fragment (never sent over the network)."""
    return f"http://127.0.0.1:{info['port']}/#token={info['token']}"


def open_page(path: Path | None = None) -> bool:
    """Open the running app's page in the default browser. False when none is running."""
    info = running_server(path or info_file_path())
    if info is None:
        return False
    address = page_address(info)
    print(address)
    webbrowser.open(address)
    return True


def start(port: int | None, browser: bool = True) -> None:
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
