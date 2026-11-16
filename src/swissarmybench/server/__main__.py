"""The `swissarmybench` command: start, stop or check the local server.

    uv run swissarmybench                 start (reuses the last port when it is free)
    uv run swissarmybench --port 8790     start on exactly this port, or fail clearly
    uv run swissarmybench status          is one running, and where
    uv run swissarmybench stop            ask the running one to shut down
    uv run swissarmybench tray            the tray icon (`start` starts it too, unless --no-tray)

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
from collections.abc import Callable
from types import FrameType

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
from swissarmybench.server.tray import start_tray
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
    parser.add_argument("command", nargs="?", default="start", choices=["start", "stop", "status", "tray"])
    parser.add_argument("--port", type=int, default=None, help="Exact port; 0 picks any free one.")
    parser.add_argument("--no-tray", action="store_true", help="Start without the tray icon.")
    args = parser.parse_args()
    path = info_file_path()

    if args.command == "tray":
        from swissarmybench.server.tray import run_tray

        sys.exit(run_tray(path))

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
        start(args.port, tray=not args.no_tray)
    except (AlreadyRunningError, AlreadyStartingError, PortError) as error:
        if (
            isinstance(error, AlreadyRunningError)
            and not args.no_tray
            and env("SWISSARMYBENCH_TRAY", "1") != "0"
        ):
            start_tray()  # its tray, if it has none (a second one ends at once)
        print(error, file=sys.stderr)
        sys.exit(1)


def start(port: int | None, tray: bool = True) -> None:
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
