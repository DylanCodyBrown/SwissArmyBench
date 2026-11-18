"""The tray icon (`swissarmybench tray`; `swissarmybench start` starts it, unless --no-tray; at sign-in,
server/autostart.py's entry starts it).

A left click opens the app's page. A right click shows the menu (domain/updates.py's tray_menu): an
update first when there is one ("Update to X", "What's new"), what is open (tables, the Workbench's
documents; read fresh as the menu opens), the Workbench, the blades page, Restart, Start with Windows
(Open at login elsewhere), Stop and quit. A newer release puts a dot on the icon and says so in its
tooltip.

It is a client of the running server, over 127.0.0.1 with the token from the connection file, like
`sab`. One tray at a time (the server's instance lock, named for tray.json, which holds the tray's
process id so an update can wait for it). The tray keeps the app running (the owner, 2026-11-16: "start
itself then stay running"): it starts the server when there is none, and starts it again when it dies
(its connection file left behind, its process gone), at most 3 times in 5 minutes; then the menu says
"Swiss Army Bench stopped: Restart". A server stopped on purpose (Stop and quit, `swissarmybench stop`)
removes its connection file, so it is not started again. During an update the tray ends itself, and the
new version starts its own.

pystray draws the icon and Pillow paints it (the plan's decision 6; the [server] extra only). Where no
tray can show (Linux with no desktop), `swissarmybench tray` still starts the server, then ends. An
extension that is on may bring its own icon (its `run_tray` hook: the Desktop extension's shell draws this
same menu with Qt) and its own way to open a page (`open_page`: open_address asks it before the browser).
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

from swissarmybench import extensions
from swissarmybench.domain.updates import MenuItem, TrayState, tooltip, tray_menu, update_question
from swissarmybench.server.autostart import Autostart, run_hidden
from swissarmybench.server.lifecycle import (
    AlreadyStartingError,
    InstanceLock,
    page_address,
    process_alive,
    read_info,
    running_server,
)
from swissarmybench.server.updater import detached

POLL_SECONDS: float = 5.0
# The watchdog: at most this many restarts in this many seconds, then it gives up and says so.
RESTARTS: int = 3
RESTART_WINDOW_SECONDS: float = 300.0
# The app's mark (the pages' icon): a red rounded square with a white cross; the update's dot is blue.
MARK_RED: tuple[int, int, int, int] = (0xD5, 0x2B, 0x1E, 255)
DOT_BLUE: tuple[int, int, int, int] = (0x25, 0x63, 0xEB, 255)


# ===== where a tray can show, and how its processes start =====


def tray_available(
    platform: str = sys.platform, environ: dict[str, str] | None = None, own_tray: bool | None = None
) -> bool:
    """Windows and macOS always have one; Linux only on a desktop (a display) with pystray and Pillow, or an
    extension's own tray (its run_tray hook)."""
    import importlib.util

    if own_tray is None:
        own_tray = extensions.hook("run_tray") is not None
    if not own_tray and any(importlib.util.find_spec(name) is None for name in ("pystray", "PIL")):
        return False
    if platform in ("win32", "darwin"):
        return True
    environ = dict(os.environ) if environ is None else environ
    return bool(environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY"))


def console_python(executable: str = sys.executable) -> str:
    """The console Python beside a pythonw.exe (the sign-in entry's), for a process whose output goes
    somewhere: CREATE_NO_WINDOW keeps it from showing a window, and its children inherit that."""
    path = Path(executable)
    if path.name.lower() == "pythonw.exe" and (path.parent / "python.exe").is_file():
        return str(path.parent / "python.exe")
    return executable


def tray_command(python: str = sys.executable) -> list[str]:
    return [python, "-m", "swissarmybench.server", "tray"]


def server_command(port: int | None = None, browser: bool = False, tray: bool = False) -> list[str]:
    """`swissarmybench start` as a detached process runs it (`start --background` and the tray)."""
    command = [console_python(), "-m", "swissarmybench.server", "start"]
    if port is not None:
        command += ["--port", str(port)]
    if not browser:
        command.append("--no-browser")
    if not tray:
        command.append("--no-tray")
    return command


def start_tray() -> bool:
    """Start the tray as its own process, with no window; False (and nothing said) where none can show."""
    if not tray_available():
        return False
    try:
        detached(tray_command())
    except OSError:
        return False
    return True


def open_address(address: str, browser: Callable[[str], object] | None = None) -> None:
    """A page of the app opened: by an extension that is on and opens pages in its own window (its
    open_page hook says True), else in the default browser."""
    opener = extensions.hook("open_page")
    try:
        if callable(opener) and opener(address):
            return
    except Exception:  # noqa: S110 (the browser, whatever the extension does)
        pass
    (browser or webbrowser.open)(address)


# ===== the icon =====


def draw_icon(size: int = 64, dot: bool = False) -> Any:
    """The mark at `size` pixels, with the update's dot at its top right when `dot`."""
    from PIL import Image, ImageDraw

    scale = size / 100
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=round(20 * scale), fill=MARK_RED)
    cross = [(42, 23), (58, 23), (58, 42), (77, 42), (77, 58), (58, 58), (58, 77), (42, 77), (42, 58)]
    cross += [(23, 58), (23, 42), (42, 42)]
    draw.polygon([(x * scale, y * scale) for x, y in cross], fill=(255, 255, 255, 255))
    if dot:
        r = size * 0.22
        cx, cy = size - r - 1, r + 1
        ring = max(1.0, size * 0.04)
        draw.ellipse((cx - r - ring, cy - r - ring, cx + r + ring, cy + r + ring), fill=(255, 255, 255, 255))
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=DOT_BLUE)
    return image


# ===== a question, in the system's own box =====


def ask(title: str, text: str) -> bool:
    """Yes or no, asked in the system's box (the tray has no window of its own)."""
    if sys.platform == "win32":
        # MB_YESNO | MB_ICONWARNING | MB_SETFOREGROUND | MB_TOPMOST; IDYES is 6.
        return bool(ctypes.windll.user32.MessageBoxW(None, text, title, 0x4 | 0x30 | 0x10000 | 0x40000) == 6)
    if sys.platform == "darwin":
        script = (
            f"display dialog {json.dumps(text)} with title {json.dumps(title)} "
            'buttons {"Cancel", "Update"} default button "Update" with icon caution'
        )
        return run_hidden(["osascript", "-e", script]) == 0
    for tool in ("zenity", "kdialog"):
        found = shutil.which(tool)
        if found:
            command = (
                [found, "--question", "--title", title, "--text", text]
                if tool == "zenity"
                else [found, "--title", title, "--yesno", text]
            )
            return run_hidden(command) == 0
    return False


# ===== the server, as a client =====


class Server:
    """The running server, found through its connection file each time (it may restart under us)."""

    def __init__(self, info_file: Path) -> None:
        self.info_file = info_file

    def info(self) -> dict[str, Any] | None:
        return read_info(self.info_file)

    def running(self) -> bool:
        return running_server(self.info_file) is not None

    def died(self) -> int | None:
        """The process id of a server that ended without stopping (its connection file is still there,
        its process is not); None otherwise. A server that stops on purpose removes the file."""
        info = self.info()
        pid = info.get("pid") if info else None
        return pid if isinstance(pid, int) and not process_alive(pid) else None

    def page(self, path: str = "/workspace", extra: str = "") -> str | None:
        info = self.info()
        if info is None:
            return None
        return page_address(info, path) + extra

    def call(self, method: str, path: str, body: Any = None, timeout: float = 5.0) -> Any:
        info = self.info()
        if info is None:
            raise ConnectionError("not running")
        request = urllib.request.Request(
            f"http://127.0.0.1:{info['port']}{path}",
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"},
        )
        # The server on 127.0.0.1, at the port its connection file names.
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310
            return json.loads(answer.read() or b"null")


def state_from(
    answer: dict[str, Any] | None,
    startup: bool | None,
    label: str = "Start with Windows",
    gave_up: bool = False,
) -> TrayState:
    """The menu's state from GET /updates/tray (None: the server is not running)."""
    if answer is None:
        return TrayState(running=False, startup=startup, startup_label=label, gave_up=gave_up)
    tables = tuple(
        (str(t.get("grid")), str(t.get("name")))
        for t in answer.get("tables", [])
        if isinstance(t, dict) and t.get("grid")
    )
    documents = tuple(
        (str(d.get("key")), str(d.get("title") or "Untitled"), d.get("unsaved") is True)
        for d in answer.get("documents", [])
        if isinstance(d, dict) and d.get("key") is not None
    )
    failed = answer.get("failed")
    return TrayState(
        running=True,
        update=answer.get("version") if answer.get("available") else None,
        tables=tables,
        documents=documents,
        startup=startup,
        startup_label=label,
        failed=f"Update to {failed.get('version')} failed: {failed.get('reason')}"
        if isinstance(failed, dict)
        else None,
    )


# ===== the watchdog =====


class Watchdog:
    """Restarts of a server that died: at most RESTARTS in RESTART_WINDOW_SECONDS, then none."""

    def __init__(
        self,
        limit: int = RESTARTS,
        window: float = RESTART_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self.restarts: list[float] = []
        self.gave_up = False

    def may_restart(self) -> bool:
        """A server died: True to start it again (counted), False once the limit is reached."""
        now = self.clock()
        self.restarts = [t for t in self.restarts if now - t < self.window]
        if self.gave_up or len(self.restarts) >= self.limit:
            self.gave_up = True
            return False
        self.restarts.append(now)
        return True

    def reset(self) -> None:
        """The user started it again: count afresh."""
        self.restarts.clear()
        self.gave_up = False


def note_event(path: Path | None, event: str, code: int | None = None, reason: str = "") -> None:
    """What the tray saw while no server could log it, for the next server's beta log (bootstrap.py)."""
    if path is None:
        return
    try:
        events = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    except (OSError, ValueError):
        events = []
    if not isinstance(events, list):
        events = []
    events.append({"time": time.time(), "event": event, "code": code, "reason": reason})
    try:
        path.write_text(json.dumps(events[-50:]), encoding="utf-8")
    except OSError:
        pass


# ===== the tray =====


class Tray:
    """The menu's actions, by the menu item's id; pystray only draws (see `menu_items`)."""

    def __init__(
        self,
        server: Server,
        startup: Autostart,
        open_url: Callable[[str], object] = open_address,
        start_server: Callable[[], object] | None = None,
        confirm: Callable[[str, str], bool] = ask,
        watchdog: Watchdog | None = None,
        events_file: Path | None = None,
    ) -> None:
        self.server = server
        self.startup = startup
        self.open_url = open_url
        self.start_server = start_server or (lambda: detached(server_command()))
        self.confirm = confirm
        self.watchdog = watchdog or Watchdog()
        self.events_file = events_file
        self.state = TrayState(running=False, startup=startup.status(), startup_label=startup.label)
        self.stop_tray: Callable[[], None] = lambda: None
        # How the tray says something (a notification); None until the icon shows.
        self.said: Callable[[str], None] | None = None
        self._told_failure = False
        self._dead: int | None = None  # the process id of the server last seen dead (counted once)

    def refresh(self) -> TrayState:
        try:
            answer = self.server.call("GET", "/updates/tray", timeout=3.0)
        except (OSError, ValueError, urllib.error.URLError):
            answer = None
        if answer is None:
            self._watch()
        self.state = state_from(
            answer if isinstance(answer, dict) else None,
            self.startup.status(),
            self.startup.label,
            self.watchdog.gave_up,
        )
        if isinstance(answer, dict) and answer.get("updating"):
            self.stop_tray()  # the update replaces this tray's files: the new version starts its own
        if self.state.failed and not self._told_failure and self.said is not None:
            self._told_failure = True
            self.said(self.state.failed)
        return self.state

    def _watch(self) -> None:
        """No answer: a server that died is started again (within the watchdog's limit)."""
        dead = self.server.died()
        if dead is None or dead == self._dead:
            return
        self._dead = dead
        note_event(self.events_file, "crash", reason="The server's process ended without stopping.")
        if self.watchdog.may_restart():
            note_event(self.events_file, "restart")
            self.start_server()
        else:
            note_event(
                self.events_file, "failed", reason=f"Stopped {RESTARTS} times in 5 minutes: not restarted."
            )
            self._say("Swiss Army Bench stopped.")

    def ensure_server(self) -> None:
        """At the tray's start (at sign-in): the server, when none is running or starting."""
        if not self.server.running() and (self.server.info() is None or self.server.died() is not None):
            self.start_server()

    def _say(self, text: str) -> None:
        if self.said is not None:
            self.said(text)

    def menu(self) -> list[MenuItem]:
        return tray_menu(self.state)

    def act(self, item_id: str) -> None:
        kind, _, key = item_id.partition(":")
        if kind in ("open", "table", "workbench", "blades", "whats_new"):
            self._open(kind, key)
        elif kind == "document":
            self._show_document(key)
        elif kind == "update":
            self._update()
        elif kind == "restart":
            self._stop_server()
            self.watchdog.reset()
            self.start_server()
        elif kind == "start":
            self.watchdog.reset()
            self.start_server()
        elif kind == "startup":
            try:
                self.startup.set(not self.startup.status())
            except OSError as error:
                self._say(str(error))
        elif kind == "quit":
            if self.state.running:
                self._stop_server()
            self.stop_tray()

    def _open(self, kind: str, key: str) -> None:
        if kind == "whats_new":
            try:
                url = self.server.call("GET", "/updates").get("url")
            except (OSError, ValueError, AttributeError):
                url = None
            if isinstance(url, str) and url.startswith("https://github.com/"):
                self.open_url(url)
            return
        path = {"open": "/workspace", "table": "/workspace", "workbench": "/workbench", "blades": "/catalog"}[
            kind
        ]
        page = self.server.page(path, f"&grid={key}" if kind == "table" and key else "")
        if page:
            self.open_url(page)

    def _show_document(self, key: str) -> None:
        """The document in front of the Workbench window that holds it; the Workbench when none does."""
        try:
            self.server.call(
                "POST", "/workbench/window", {"command": "doc.show", "args": {"index": int(key)}}
            )
        except (OSError, ValueError, urllib.error.URLError):
            self._open("workbench", "")

    def _update(self) -> None:
        version = self.state.update
        if not version:
            return
        try:
            answer = self.server.call("POST", "/updates/install", {"version": version}, timeout=15.0)
            if isinstance(answer, dict) and "confirm" in answer:
                if not self.confirm(f"Update to {version}", update_question(version, answer["confirm"])):
                    return
                answer = self.server.call(
                    "POST", "/updates/install", {"version": version, "confirmed": True}, timeout=15.0
                )
        except urllib.error.HTTPError as error:
            self._say(error.read().decode("utf-8", "replace")[:300] or "The update could not start.")
            return
        except (OSError, ValueError):
            self._say("The server is not answering.")
            return
        if isinstance(answer, dict) and answer.get("updating"):
            self.stop_tray()

    def _stop_server(self) -> None:
        try:
            self.server.call("POST", "/shutdown")
        except (OSError, ValueError):
            return
        for _ in range(100):
            if not self.server.running():
                return
            time.sleep(0.1)


def menu_items(tray: Tray, pystray: Any) -> Any:
    """The pystray menu for the tray's model: one MenuItem per line, its action by id."""

    # pystray counts an action's arguments (icon, item), so each is made with its id closed over.
    def action(which: str) -> Callable[[Any, Any], None]:
        return lambda _icon, _item: tray.act(which)

    def check(on: bool) -> Callable[[Any], bool]:
        return lambda _item: on

    def item(entry: MenuItem) -> Any:
        if entry.separator:
            return pystray.Menu.SEPARATOR
        return pystray.MenuItem(
            entry.text,
            action(entry.id),
            checked=check(entry.checked) if entry.checked is not None else None,
            default=entry.default,
            enabled=entry.enabled,
        )

    return pystray.Menu(lambda: tuple(item(entry) for entry in tray.menu()))


def run_tray(info_file: Path, events_file: Path | None = None) -> int:
    """`swissarmybench tray`: the icon until Quit (or an update). 0 also when another tray is running."""
    tray_file = info_file.with_name("tray.json")
    try:
        lock = InstanceLock(tray_file)
    except AlreadyStartingError:
        return 0  # one tray at a time: the one already there stays
    tray = Tray(Server(info_file), Autostart(), events_file=events_file)
    try:
        import pystray
    except Exception:  # no desktop to show it on: the app still starts, with no icon
        tray.ensure_server()
        lock.release()
        return 0
    tray_file.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    tray.ensure_server()
    tray.refresh()
    plain, dotted = draw_icon(64), draw_icon(64, dot=True)

    class Icon(pystray.Icon):  # type: ignore[misc]
        def _on_notify(self, wparam: Any, lparam: Any) -> Any:
            # Windows: read what is open as the menu opens (WM_RBUTTONUP), not up to five seconds late.
            if lparam == 0x0205:
                tray.refresh()
                self.update_menu()
            return super()._on_notify(wparam, lparam)

    icon = Icon("swissarmybench", plain, tooltip(tray.state), menu_items(tray, pystray))
    stopping = threading.Event()

    def stop() -> None:
        stopping.set()
        icon.stop()

    tray.stop_tray = stop
    tray.said = lambda text: icon.notify(text[:250], "Swiss Army Bench") if icon.HAS_NOTIFICATION else None

    def draw() -> None:
        icon.icon = dotted if tray.state.update else plain
        icon.title = tooltip(tray.state)
        icon.update_menu()

    def poll(_: Any) -> None:
        icon.visible = True
        draw()
        while not stopping.wait(POLL_SECONDS if tray.state.running else 2.0):
            tray.refresh()
            draw()

    try:
        icon.run(setup=poll)
    finally:
        lock.release()
        try:
            tray_file.unlink()
        except OSError:
            pass
    return 0
