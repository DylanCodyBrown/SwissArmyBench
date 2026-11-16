"""The tray icon (`swissarmybench tray`; `swissarmybench start` starts it, unless --no-tray).

A left click opens the app's page. A right click shows the menu (domain/updates.py's tray_menu): an
update first when there is one ("Update to X", "What's new"), what is open (tables, the Workbench's
documents; read fresh as the menu opens), the Workbench, the blades page, Restart, Start with Windows,
Stop and quit. A newer release puts a dot on the icon and says so in its tooltip.

It is a client of the running server, over 127.0.0.1 with the token from the connection file, like
`sab`; it holds nothing of its own. One tray at a time (the server's instance lock, named for tray.json,
which holds the tray's process id so an update can wait for it). The server can stop and start under it:
the menu then offers Start. During an update the tray ends itself, and the new version starts its own.

pystray draws the icon and Pillow paints it (the plan's decision 6; the [server] extra only).
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

from swissarmybench.domain.updates import MenuItem, TrayState, tooltip, tray_menu, update_question
from swissarmybench.server.lifecycle import AlreadyStartingError, InstanceLock, read_info, running_server
from swissarmybench.server.updater import detached

POLL_SECONDS: float = 5.0
SHORTCUT_NAME: str = "Swiss Army Bench.lnk"
# The app's mark (the pages' icon): a red rounded square with a white cross; the update's dot is blue.
MARK_RED: tuple[int, int, int, int] = (0xD5, 0x2B, 0x1E, 255)
DOT_BLUE: tuple[int, int, int, int] = (0x25, 0x63, 0xEB, 255)


# ===== where a tray can show =====


def tray_available(platform: str = sys.platform, environ: dict[str, str] | None = None) -> bool:
    """Windows and macOS always have one; Linux only on a desktop (a display) with pystray and Pillow."""
    import importlib.util

    if any(importlib.util.find_spec(name) is None for name in ("pystray", "PIL")):
        return False
    if platform in ("win32", "darwin"):
        return True
    environ = dict(os.environ) if environ is None else environ
    return bool(environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY"))


def tray_command(python: str = sys.executable) -> list[str]:
    return [python, "-m", "swissarmybench.server", "tray"]


def start_tray() -> bool:
    """Start the tray as its own process, with no window; False (and nothing said) where none can show."""
    if not tray_available():
        return False
    try:
        detached(tray_command())
    except OSError:
        return False
    return True


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


# ===== Start with Windows: a shortcut in the Startup folder =====


def startup_folder(environ: dict[str, str] | None = None) -> Path | None:
    appdata = (dict(os.environ) if environ is None else environ).get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_target(prefix: Path | None = None) -> Path:
    """The uv tool's own swissarmybench.exe (the same path after an update)."""
    return (prefix or Path(sys.prefix)) / "Scripts" / "swissarmybench.exe"


def shortcut_script(shortcut: Path, target: Path) -> str:
    """PowerShell that writes the shortcut: `swissarmybench.exe start`, minimised."""

    def quoted(text: object) -> str:
        return "'" + str(text).replace("'", "''") + "'"

    return (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + quoted(shortcut) + "); "
        f"$s.TargetPath = {quoted(target)}; $s.Arguments = 'start'; $s.WindowStyle = 7; "
        f"$s.WorkingDirectory = {quoted(Path.home())}; $s.Description = 'Swiss Army Bench'; $s.Save()"
    )


class Startup:
    """Start with Windows: on when the shortcut is there. None on other systems (no menu item)."""

    def __init__(self, folder: Path | None, run: Callable[[list[str]], int] | None = None) -> None:
        self.folder = folder
        self._run = run or _run_hidden

    @property
    def shortcut(self) -> Path | None:
        return self.folder / SHORTCUT_NAME if self.folder else None

    def on(self) -> bool | None:
        return None if self.shortcut is None else self.shortcut.is_file()

    def set(self, on: bool) -> None:
        if self.shortcut is None:
            return
        if not on:
            self.shortcut.unlink(missing_ok=True)
            return
        self.shortcut.parent.mkdir(parents=True, exist_ok=True)
        script = shortcut_script(self.shortcut, startup_target())
        self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])


def _run_hidden(command: list[str]) -> int:
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    try:
        # PowerShell, osascript or zenity, with our own script.
        done = subprocess.run(command, capture_output=True, timeout=30, creationflags=flags, check=False)  # noqa: S603
        return done.returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1


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
        return _run_hidden(["osascript", "-e", script]) == 0
    for tool in ("zenity", "kdialog"):
        found = shutil.which(tool)
        if found:
            command = (
                [found, "--question", "--title", title, "--text", text]
                if tool == "zenity"
                else [found, "--title", title, "--yesno", text]
            )
            return _run_hidden(command) == 0
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

    def page(self, path: str = "/workspace", extra: str = "") -> str | None:
        info = self.info()
        if info is None:
            return None
        return f"http://127.0.0.1:{info['port']}{path}#token={info['token']}{extra}"

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


def state_from(answer: dict[str, Any] | None, startup: bool | None) -> TrayState:
    """The menu's state from GET /updates/tray (None: the server is not running)."""
    if answer is None:
        return TrayState(running=False, startup=startup)
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
        failed=f"Update to {failed.get('version')} failed: {failed.get('reason')}"
        if isinstance(failed, dict)
        else None,
    )


# ===== the tray =====


class Tray:
    """The menu's actions, by the menu item's id; pystray only draws (see `menu_items`)."""

    def __init__(
        self,
        server: Server,
        startup: Startup,
        open_url: Callable[[str], object] = webbrowser.open,
        start_server: Callable[[], object] | None = None,
        confirm: Callable[[str, str], bool] = ask,
    ) -> None:
        self.server = server
        self.startup = startup
        self.open_url = open_url
        self.start_server = start_server or (lambda: detached(server_command()))
        self.confirm = confirm
        self.state = TrayState(running=False, startup=startup.on())
        self.stop_tray: Callable[[], None] = lambda: None
        # How the tray says something (a notification); None until the icon shows.
        self.said: Callable[[str], None] | None = None
        self._told_failure = False

    def refresh(self) -> TrayState:
        try:
            answer = self.server.call("GET", "/updates/tray", timeout=3.0)
        except (OSError, ValueError, urllib.error.URLError):
            answer = None
        self.state = state_from(answer if isinstance(answer, dict) else None, self.startup.on())
        if isinstance(answer, dict) and answer.get("updating"):
            self.stop_tray()  # the update replaces this tray's files: the new version starts its own
        if self.state.failed and not self._told_failure and self.said is not None:
            self._told_failure = True
            self.said(self.state.failed)
        return self.state

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
            self.start_server()
        elif kind == "start":
            self.start_server()
        elif kind == "startup":
            self.startup.set(not self.startup.on())
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


def server_command(python: str = sys.executable) -> list[str]:
    """The tray's own start of the server: no second tray."""
    return [python, "-m", "swissarmybench.server", "start", "--no-tray"]


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


def run_tray(info_file: Path) -> int:
    """`swissarmybench tray`: the icon until Quit (or an update). 0 also when another tray is running."""
    tray_file = info_file.with_name("tray.json")
    try:
        lock = InstanceLock(tray_file)
    except AlreadyStartingError:
        return 0  # one tray at a time: the one already there stays
    try:
        import pystray
    except Exception:  # no desktop to show it on
        lock.release()
        return 0
    tray_file.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    tray = Tray(Server(info_file), Startup(startup_folder() if sys.platform == "win32" else None))
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
