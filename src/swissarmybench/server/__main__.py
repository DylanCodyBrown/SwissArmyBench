"""The `swissarmybench` command: the desktop app, and its local server.

    swissarmybench                        open the app (the desktop app; it starts the server it owns)
    swissarmybench open                   the same; with the app open, its home window comes forward
    swissarmybench open ~/sales           open a project folder in the app (starting it when it is not open)
    swissarmybench open orders.csv        a file in the app: a table (CSV, Parquet, Excel, JSON), a notebook,
                                          a blade (Open with and the installers' registrations run this)
    swissarmybench open --browser         the app in the browser instead (a tab; the same server)
    swissarmybench start                  the server in this console, then the app's window (--no-window not)
    swissarmybench start --background     the server detached, no console, returns at once
    swissarmybench --port 8790 start      on exactly this port, or fail clearly
    swissarmybench status                 is one running, and where
    swissarmybench stop                   ask the running one to shut down

Swiss Army Bench is a desktop app (the owner, 2026-11-18: "We should just package this as the desktop app
pyside6"; "It's not an extension it is the app framework now and it should have been since the start"):
PySide6 windows with the pages in Qt WebEngine (server/desktop_shell.py). Where the app cannot run (no
display, no Qt WebEngine) the browser opens instead. The token is in the address's fragment (#token=...),
which is never sent over the network.

The server runs while the app is open (the owner, 2026-11-18: "I wanted the server to simply run while the
app is active and shutdown when it's not"): services/lifecycle.py stops it 30 seconds after the last window
closes (at once when the desktop app closes), or 10 minutes after the last request of the agent, VS Code or
a Python session with still no window open. There is no tray and no start at sign-in any more: `tray` and
`autostart` (and --no-tray) are accepted for one release and say so. VS Code's extension runs this command
with SWISSARMYBENCH_STARTED_BY=vscode: the server only, no window.

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
from typing import TYPE_CHECKING, Any

from swissarmybench import __version__
from swissarmybench.adapters.state_files import info_file_path, remove_info_file, write_info_file
from swissarmybench.server import desktop
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
from swissarmybench.server.updater import detached
from swissarmybench.settings import Settings

if TYPE_CHECKING:
    import uvicorn

GONE_WORDS: str = (
    "There is no tray icon and no start at sign-in any more: Swiss Army Bench runs while it's open "
    "(swissarmybench opens it)."
)


def _server_class() -> Callable[[uvicorn.Config, Callable[[], None]], uvicorn.Server]:
    """uvicorn's server, but a stop by signal (Ctrl+C, the system shutting down) first lets the waiting
    listeners answer, as `swissarmybench stop` does. Made here, not at import: the app's own process (the
    desktop shell) runs this module and never serves, so uvicorn and the app's routes load only in `start`."""
    import uvicorn

    class _Server(uvicorn.Server):
        def __init__(self, config: uvicorn.Config, on_exit: Callable[[], None]) -> None:
            super().__init__(config)
            self._on_exit = on_exit

        def handle_exit(self, sig: int, frame: Any) -> None:
            try:
                self._on_exit()
            except Exception:  # noqa: S110 (never in the way of stopping)
                pass
            super().handle_exit(sig, frame)

    return _Server


def main() -> None:
    parser = argparse.ArgumentParser(description="Swiss Army Bench: the desktop app and its local server.")
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        choices=["app", "start", "stop", "status", "open", "icon", "tray", "autostart"],
    )
    parser.add_argument(
        "switch",
        nargs="?",
        help="open: a project's folder or a file; app: a page of the app; icon: a .ico or .png file.",
    )
    parser.add_argument("--port", type=int, default=None, help="Exact port; 0 picks any free one.")
    parser.add_argument(
        "--no-window", "--no-browser", dest="no_window", action="store_true", help="No window when it starts."
    )
    parser.add_argument("--browser", action="store_true", help="open: in the browser instead of the app.")
    parser.add_argument("--no-tray", action="store_true", help=argparse.SUPPRESS)  # gone; one release
    parser.add_argument(
        "--background", action="store_true", help="Start detached, with no console, and return at once."
    )
    args = parser.parse_args()
    path = info_file_path()
    # No command: the app. With a server's options (--port, --no-window, --background: the older
    # `swissarmybench --port N`), or from VS Code's extension, the server, as before.
    server_only = args.port is not None or args.no_window or args.background
    vscode = os.environ.get("SWISSARMYBENCH_STARTED_BY", "") == "vscode"
    command = args.command or ("start" if server_only or vscode else "app")

    if command in ("tray", "autostart"):
        print(GONE_WORDS)
        return
    if command == "icon":
        sys.exit(write_icon(args.switch))
    if command == "app":
        if args.browser or not desktop.can_run():
            sys.exit(0 if open_in_browser(path, args.switch) else 1)
        sys.exit(desktop.main(args.switch, path))
    if command == "open" and args.switch:
        sys.exit(open_target(args.switch, path, browser=args.browser))
    if command == "open":
        if args.browser:
            sys.exit(0 if open_in_browser(path) else 1)
        if desktop.can_run():
            sys.exit(desktop.main(None, path))
        sys.exit(0 if open_in_browser(path) else 1)
    if command == "start" and args.background:
        start_in_background(args.port, window=not args.no_window)
        return

    if command == "status":
        info = running_server(path)
        if info is None:
            print("Swiss Army Bench is not running.")
            sys.exit(1)
        print(f"Running on http://127.0.0.1:{info['port']} (process {info.get('pid')}).")
        return
    if command == "stop":
        # The app first (its windows closed, their places kept: the user's own word, from a terminal or an
        # installer), then its server.
        app_quit = desktop.quit_app(path)
        if not request_stop(path):
            if app_quit:
                print("Stopped.")
                return
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
        start(args.port, window=not args.no_window)
    except AlreadyRunningError as error:
        # Already running: show the app, which is what someone starting it again wants.
        if not args.no_window and os.environ.get("SWISSARMYBENCH_NO_BROWSER", "") != "1" and open_page(path):
            print("Swiss Army Bench is already running: its window is in front.")
            return
        print(error, file=sys.stderr)
        sys.exit(1)
    except (AlreadyStartingError, PortError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)


def write_icon(target: str | None) -> int:
    """`swissarmybench icon <file>`: the app's icon for a launcher (the installers': a Windows shortcut's
    .ico, a PNG elsewhere), by the file's suffix."""
    from swissarmybench.domain import desktop as rules

    if not target or not target.lower().endswith((".ico", ".png")):
        print("swissarmybench icon <file.ico | file.png>", file=sys.stderr)
        return 2
    path = Path(target).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rules.icon_ico() if path.suffix.lower() == ".ico" else rules.icon_png(256))
    return 0


def open_address(address: str, browser: bool = False) -> None:
    """A page of the app: in the desktop app (started when it is not open), or the browser where the app
    cannot run or when asked for."""
    if not browser and desktop.open_page(address):
        return
    webbrowser.open(address)


def open_in_browser(path: Path, page: str | None = None) -> bool:
    """`swissarmybench open --browser`: the app in a browser tab, the server started first when needed."""
    info = running_server(path)
    if info is None:
        start_in_background(None, window=False)
        deadline = time.monotonic() + 30
        while info is None and time.monotonic() < deadline:
            time.sleep(0.3)
            info = running_server(path)
    if info is None:
        print("Swiss Army Bench did not start.", file=sys.stderr)
        return False
    address = page_address(info, page or "/workspace")
    print(address)
    webbrowser.open(address)
    return True


def open_page(path: Path | None = None) -> bool:
    """Open the running app's page in the default browser. False when none is running."""
    info = running_server(path or info_file_path())
    if info is None:
        return False
    address = page_address(info)
    print(address)
    open_address(address)
    return True


OLD_SAB_FILE: str = "{name}: this version opens project folders only."


def open_target(target: str, path: Path, browser: bool = False) -> int:
    """`swissarmybench open <path>` (and Open with, the installers' registrations): a project's folder, or a
    file: a table (CSV, Parquet, Excel, JSON, Arrow), a notebook, a blade. A file goes to the running app over
    its channel (one app, never a second; started when none runs); where the app cannot run (or --browser),
    the server reads it and the browser shows it."""
    from swissarmybench.domain import desktop as rules

    file = Path(target).expanduser()
    if file.name.lower().endswith(".sab") or not file.exists():
        return open_project(target, path, browser=browser)  # says why, in one line
    from swissarmybench import extensions

    kind = rules.file_kind(file.name, file.is_dir(), (file / ".sab").is_dir(), tuple(extensions.opens()))
    if kind == rules.PROJECT:
        return open_project(target, path, browser=browser)
    if not kind:
        print(rules.CANNOT_OPEN.format(name=file.name), file=sys.stderr)
        return 1
    full = str(file.resolve())
    if not browser and desktop.can_run():
        if desktop.hand_file(full, path):
            print(f"Opening {file.name}.")
            return 0
        print("Swiss Army Bench did not start.", file=sys.stderr)
        return 1
    info = running_server(path)
    if info is None:
        start_in_background(None, window=False)
        deadline = time.monotonic() + 30
        while info is None and time.monotonic() < deadline:
            time.sleep(0.3)
            info = running_server(path)
    if info is None:
        print("Swiss Army Bench did not start.", file=sys.stderr)
        return 1
    try:
        page = desktop.file_page(full, info)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    webbrowser.open(rules.address_of(page, int(info["port"]), str(info["token"])))
    print(f"Opened {file.name}.")
    return 0


def open_project(target: str, path: Path, wait_seconds: float = 30.0, browser: bool = False) -> int:
    """`swissarmybench open <a project's folder>`: the app started in the background when it is not
    running, the project opened in it (the page asks first when unsaved work would be lost), and the home
    window shown when none is open. An old single-file project (.sab) is answered in one line, and nothing
    starts."""
    file = Path(target).expanduser()
    if file.name.lower().endswith(".sab"):
        print(OLD_SAB_FILE.format(name=file.name), file=sys.stderr)
        return 1
    if not file.exists():
        print(f"{file} is not there.", file=sys.stderr)
        return 1
    info = running_server(path)
    if info is None:
        start_in_background(None, window=False)
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
        open_address(page_address(info), browser)  # no home window is open: one, showing the project
    print(f"Opened {file.name}." if not (isinstance(answer, dict) and answer.get("asked")) else
          f"{file.name}: the app asks about the unsaved work open now.")  # fmt: skip
    return 0


def server_command(port: int | None = None, window: bool = False) -> list[str]:
    """`swissarmybench start` as a detached process runs it (`start --background`, `open`)."""
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe" and (python.parent / "python.exe").is_file():
        python = python.parent / "python.exe"
    command = [str(python), "-m", "swissarmybench.server", "start"]
    if port is not None:
        command += ["--port", str(port)]
    if not window:
        command.append("--no-window")
    return command


def start_in_background(port: int | None, window: bool = True) -> None:
    """`swissarmybench start --background`: the server detached, with no console window, outliving this
    command, which returns at once."""
    detached(server_command(port, window))
    print("Swiss Army Bench is starting in the background.")


def start(port: int | None, window: bool = True) -> None:
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
    started_by = os.environ.get("SWISSARMYBENCH_STARTED_BY", "cli")
    import uvicorn

    from swissarmybench.server.app import create_app
    from swissarmybench.server.routes_processes import QuietHeartbeats

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
    if os.environ.get("SWISSARMYBENCH_NO_BROWSER", "") != "1":
        # A push or open_grid with nothing showing it and no VS Code window to ask: the desktop app opens
        # the workspace (the browser where the app cannot run).
        app.state.ctx.live.fallback = lambda address: desktop.show(address, path)
    config = uvicorn.Config(app, log_level="info", timeout_graceful_shutdown=3)
    # uvicorn has set up its loggers by now; keep the sessions' heartbeats out of the access log.
    logging.getLogger("uvicorn.access").addFilter(QuietHeartbeats())
    server = _server_class()(config, release)

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
    if window and started_by != "vscode" and os.environ.get("SWISSARMYBENCH_NO_BROWSER", "") != "1":
        # The socket already listens: the app's window (or a browser) asks now and waits for the answer.
        threading.Timer(0.5, open_address, args=(address,)).start()
    try:
        server.run(sockets=[listener])
    finally:
        remove_info_file(path, token)
        lock.release()


if __name__ == "__main__":
    main()
