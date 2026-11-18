"""The Desktop shell: the app's pages in windows of their own (PySide6, Qt WebEngine: Chromium), with the tray
icon's job in the same process (one icon, not two). server/launch.py starts it; domain/windows.py has its
rules.

One QApplication; each page a QMainWindow holding a QWebEngineView, every view on one persistent profile in
the state folder's desktop/profile (cookies: the sab_<port> cookie the token buys; localStorage; the cache).

  window.open        QWebEnginePage.createWindow: a new app window (Chromium itself finds a named window
                     that is open, as a browser does; the page's focus() raises it: the shell's small script)
  outside addresses  the system's browser (QDesktopServices.openUrl), never inside the shell
  downloads          the profile's downloadRequested: a Save dialog, the progress, Show in folder
  window.print()     Print to PDF: a Save dialog, then QWebEnginePage.printToPdf
  permissions        the clipboard for the app's own origin; nothing else to anyone
  keys               F12 the developer tools (a window of their own), F11 full screen, Alt+Left/Right back and
                     forward, F5 and Ctrl+R reload, Ctrl+P print, Ctrl+W close the window
  the tray           the base's Tray (server/tray.py: its menu, the watchdog, Update, Start at sign-in,
                     Quit) drawn by QSystemTrayIcon instead of pystray

Nothing here holds the token but the addresses the windows load (read from the server's connection file
each time a page is opened); the channel's messages and the command line carry pages without it.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QStandardPaths, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QPolygonF,
    QShortcut,
)
from PySide6.QtWebEngineCore import (
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QWidget,
)

from swissarmybench.domain.updates import tooltip
from swissarmybench.server.autostart import Autostart
from swissarmybench.server.lifecycle import read_info
from swissarmybench.server.tray import POLL_SECONDS, Server, Tray, server_command
from swissarmybench.server.updater import detached
from swissarmybench_desktop.adapters.channel import JsonState, Listener, RecordFile, new_key
from swissarmybench_desktop.domain import windows as rules

APP_NAME = "Swiss Army Bench"
# The pages' console line the shell's script writes: a focus() (raise this window) or the window's name.
MARK = "\u2063sab-shell "
SHELL_SCRIPT = """
(() => {
  if (window.__sabShell) return;
  window.__sabShell = true;
  const say = (m) => console.info("__MARK__" + JSON.stringify(m));
  const focus = window.focus;
  window.focus = function () { say({ focus: true }); return focus.call(window); };
  let name = window.name;
  say({ name });
  setInterval(() => { if (window.name !== name) { name = window.name; say({ name }); } }, 500);
})();
""".replace("__MARK__", MARK)
MARK_RED = QColor(0xD5, 0x2B, 0x1E)
DOT_BLUE = QColor(0x25, 0x63, 0xEB)
SERVER_WAIT_MS = 60_000
STATUS_HIDE_MS = 30_000

AskSave = Callable[[QWidget | None, str, str, str], str]
OpenOutside = Callable[[QUrl], object]


def draw_mark(size: int = 64, dot: bool = False) -> QPixmap:
    """The app's mark (the pages' icon, the tray's): a red rounded square, a white cross; the update's dot."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = size / 100
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(MARK_RED)
    painter.drawRoundedRect(QRectF(0, 0, size, size), 20 * scale, 20 * scale)
    cross = [(42, 23), (58, 23), (58, 42), (77, 42), (77, 58), (58, 58), (58, 77), (42, 77), (42, 58)]
    cross += [(23, 58), (23, 42), (42, 42)]
    painter.setBrush(QColor(255, 255, 255))
    painter.drawPolygon(QPolygonF([QPointF(x * scale, y * scale) for x, y in cross]))
    if dot:
        r = size * 0.22
        painter.drawEllipse(QPointF(size - r - 1, r + 1), r + size * 0.04, r + size * 0.04)
        painter.setBrush(DOT_BLUE)
        painter.drawEllipse(QPointF(size - r - 1, r + 1), r, r)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(draw_mark(size))
    return icon


def ask_save(parent: QWidget | None, title: str, start: str, filters: str) -> str:
    """The system's Save dialog (QFileDialog: the native one where the system has one); "" when cancelled."""
    chosen, _ = QFileDialog.getSaveFileName(parent, title, start, filters)
    return str(chosen or "")


def downloads_folder() -> str:
    return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or str(
        Path.home()
    )


class Bridge(QObject):  # type: ignore[misc]  # Qt's classes are Any to mypy (pyproject)
    """Calls from other threads (the channel, the tray's poll) handed to the window thread."""

    open_page = Signal(str)  # a page of the app, no token
    open_address = Signal(str)  # a full address (the tray's)
    tray_changed = Signal()
    say = Signal(str)
    quit = Signal()


class Page(QWebEnginePage):  # type: ignore[misc]  # Qt's classes are Any to mypy (pyproject)
    """One window's page: what loads inside, new windows, the shell's console lines, print, close."""

    def __init__(self, shell: Shell, window: AppWindow) -> None:
        super().__init__(shell.profile, window)
        self.shell = shell
        self.window = window

    def acceptNavigationRequest(
        self, url: QUrl | str, kind: QWebEnginePage.NavigationType, main_frame: bool
    ) -> bool:
        address = url.toString() if isinstance(url, QUrl) else str(url)
        clicked = kind == QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        verdict = rules.decide(address, self.shell.port, main_frame=main_frame, clicked=clicked)
        if verdict == rules.INSIDE:
            return True
        if verdict == rules.OUTSIDE:
            self.shell.outside(QUrl(address))
        if main_frame and self.window.fresh:
            QTimer.singleShot(0, self.window.close)  # a window.open to elsewhere: nothing to show here
        return False

    def createWindow(self, kind: QWebEnginePage.WebWindowType) -> QWebEnginePage:
        popup = kind == QWebEnginePage.WebWindowType.WebDialog
        return self.shell.new_window(popup=popup).page

    def javaScriptConsoleMessage(
        self, level: QWebEnginePage.JavaScriptConsoleMessageLevel, text: str, line: int, source: str
    ) -> None:
        if not text.startswith(MARK):
            return
        try:
            said = json.loads(text[len(MARK) :])
        except ValueError:
            return
        if isinstance(said, dict):
            if said.get("focus") is True:
                self.window.bring_forward()
            if isinstance(said.get("name"), str):
                self.window.name = said["name"][:200]
                self.shell.changed()


class AppWindow(QMainWindow):  # type: ignore[misc]  # Qt's classes are Any to mypy (pyproject)
    """A page of the app in a window of its own."""

    def __init__(self, shell: Shell, ident: int, popup: bool = False) -> None:
        super().__init__()
        self.shell = shell
        self.ident = ident
        self.popup = popup
        self.name = ""
        self.kind = ""
        self.fresh = True  # nothing of the app shown yet (a window.open's about:blank)
        self.requested: tuple[int, int] | None = None
        self.placed = False
        self.raised = 0  # how often it was brought forward (a page's focus(), the tray's Open)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowIcon(shell.icon)
        self.setWindowTitle(APP_NAME)
        self.view = QWebEngineView(self)
        self.page = Page(shell, self)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        self.devtools: QMainWindow | None = None
        page = self.page
        page.titleChanged.connect(lambda title: self.setWindowTitle(rules.window_title(title)))
        page.urlChanged.connect(self._url_changed)
        page.windowCloseRequested.connect(self.close)
        page.geometryChangeRequested.connect(self._geometry_asked)
        page.fullScreenRequested.connect(self._full_screen)
        page.permissionRequested.connect(self._permission)
        page.printRequested.connect(lambda: shell.print_page(self))
        page.printRequestedByFrame.connect(lambda _frame: shell.print_page(self))
        page.pdfPrintingFinished.connect(self._printed)
        self._status_label = QLabel()
        self._status_button = QPushButton("Show in folder")
        self._status_button.hide()
        self._status_folder = ""
        self._status_button.clicked.connect(self._show_folder)
        bar = self.statusBar()
        bar.addWidget(self._status_label, 1)
        bar.addPermanentWidget(self._status_button)
        bar.hide()
        self._hide = QTimer(self)
        self._hide.setSingleShot(True)
        self._hide.timeout.connect(bar.hide)
        self._printing = ""
        for keys, action in (
            ("F12", self.toggle_devtools),
            ("Ctrl+Shift+I", self.toggle_devtools),
            ("F11", self.toggle_full_screen),
            ("Alt+Left", lambda: page.triggerAction(QWebEnginePage.WebAction.Back)),
            ("Alt+Right", lambda: page.triggerAction(QWebEnginePage.WebAction.Forward)),
            ("F5", lambda: page.triggerAction(QWebEnginePage.WebAction.Reload)),
            ("Ctrl+R", lambda: page.triggerAction(QWebEnginePage.WebAction.Reload)),
            ("Ctrl+P", lambda: shell.print_page(self)),
            ("Ctrl+W", self.close),
        ):
            QShortcut(QKeySequence(keys), self, activated=action)

    # ----- where it goes -----

    def _geometry_asked(self, rect: Any) -> None:
        self.requested = (int(rect.width()), int(rect.height())) if rect.width() and rect.height() else None
        if self.placed and self.requested and not self.shell.saved_for(self.kind):
            self.resize(*self.requested)

    def _url_changed(self, url: QUrl) -> None:
        address = url.toString()
        if not rules.is_ours(address, self.shell.port):
            return
        self.fresh = False
        self.kind = self.kind or rules.kind_of(address)
        if not self.placed:
            self.place()
        self.shell.changed()

    def place(self) -> None:
        """Its kind's remembered size and place (else the page's asked size, else the default), then shown."""
        self.placed = True
        screens = [
            rules.Rect(g.x(), g.y(), g.width(), g.height())
            for g in (s.availableGeometry() for s in QApplication.screens())
        ]
        spot = rules.place(
            self.kind or "other",
            self.shell.saved_for(self.kind),
            self.requested,
            screens,
            len(self.shell.windows) - 1,
        )
        self.setGeometry(spot.rect.x, spot.rect.y, spot.rect.w, spot.rect.h)
        if spot.maximized:
            self.showMaximized()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def bring_forward(self) -> None:
        self.raised += 1
        if not self.placed:
            self.place()
            return
        if not self.isVisible():
            self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        (self.view.focusProxy() or self.view).setFocus()

    def remember(self) -> None:
        if not self.kind or not self.placed:
            return
        rect = self.normalGeometry() if self.isMaximized() or self.isFullScreen() else self.geometry()
        if rect.width() >= rules.MIN_WIDTH and rect.height() >= rules.MIN_HEIGHT:
            saved = rules.Saved(
                rules.Rect(rect.x(), rect.y(), rect.width(), rect.height()), self.isMaximized()
            )
            self.shell.remember(self.kind, saved)

    def closeEvent(self, event: Any) -> None:
        self.remember()
        if self.devtools is not None:
            self.devtools.close()
        self.shell.closed(self)
        super().closeEvent(event)

    # ----- full screen, developer tools, permissions -----

    def toggle_full_screen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _full_screen(self, request: Any) -> None:
        if rules.is_ours(request.origin().toString(), self.shell.port):
            request.accept()
            if request.toggleOn():
                self.showFullScreen()
            else:
                self.showNormal()
        else:
            request.reject()

    def _permission(self, permission: Any) -> None:
        clipboard = permission.permissionType() == type(permission.permissionType()).ClipboardReadWrite
        if rules.grant(
            "clipboard" if clipboard else "other", permission.origin().toString(), self.shell.port
        ):
            permission.grant()
        else:
            permission.deny()

    def toggle_devtools(self) -> None:
        if self.devtools is not None:
            self.devtools.close()
            return
        tools = QMainWindow()
        tools.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        tools.setWindowTitle(f"Developer tools: {self.windowTitle()}")
        tools.setWindowIcon(self.shell.icon)
        view = QWebEngineView(tools)
        tools.setCentralWidget(view)
        self.page.setDevToolsPage(view.page())
        tools.resize(1000, 700)
        tools.destroyed.connect(lambda *_: setattr(self, "devtools", None))
        self.devtools = tools
        tools.show()

    # ----- the status line: downloads and Print to PDF -----

    def tell(self, text: str, folder: str = "") -> None:
        self._status_label.setText(text)
        self._status_folder = folder
        self._status_button.setVisible(bool(folder))
        self.statusBar().show()
        if text.endswith("…"):
            self._hide.stop()  # under way: shown until it ends
        else:
            self._hide.start(STATUS_HIDE_MS)

    def _show_folder(self) -> None:
        if self._status_folder:
            self.shell.show_folder(self._status_folder)

    def track(self, download: QWebEngineDownloadRequest, path: Path) -> None:
        """A download's progress, then Show in folder (or why it stopped)."""
        state = QWebEngineDownloadRequest.DownloadState

        def progress() -> None:
            total, got = download.totalBytes(), download.receivedBytes()
            share = f" {got * 100 // total}%" if total > 0 else ""
            self.tell(f"Downloading {path.name}{share}…")

        def finished() -> None:
            if download.state() == state.DownloadCompleted:
                self.tell(f"Saved {path.name}", str(path.parent))
                self.shell.downloaded.append(str(path))
            elif download.state() == state.DownloadCancelled:
                self.tell(f"{path.name} was not saved.")
            else:
                self.tell(f"{path.name} was not saved: {download.interruptReasonString()}")

        download.receivedBytesChanged.connect(progress)
        download.isFinishedChanged.connect(finished)
        progress()

    def print_to(self, path: str) -> None:
        self._printing = path
        self.tell(f"Printing {Path(path).name}…")
        self.page.printToPdf(path)

    def _printed(self, path: str, ok: bool) -> None:
        name = Path(path).name
        if ok:
            self.tell(f"Saved {name}", str(Path(path).parent))
            self.shell.printed.append(path)
        else:
            self.tell(f"{name} could not be printed.")


class Shell(QObject):  # type: ignore[misc]  # Qt's classes are Any to mypy (pyproject)
    """The app's windows, the tray icon and the channel, in one QApplication."""

    def __init__(
        self,
        app: QApplication,
        info_file: Path,
        *,
        save_dialog: AskSave = ask_save,
        open_outside: OpenOutside = QDesktopServices.openUrl,
        tray: Tray | None = None,
        events_file: Path | None = None,
    ) -> None:
        super().__init__()
        self.app = app
        self.info_file = info_file
        self.folder = info_file.parent / "desktop"
        self.save_dialog = save_dialog
        self.open_outside = open_outside
        self.icon = app_icon()
        app.setWindowIcon(self.icon)
        self.windows: dict[int, AppWindow] = {}
        self._next = 1
        self.port = self._server_port()
        self.places = JsonState(self.folder / "windows.json")
        self.outside_opened: list[str] = []  # what went to the system's browser (the real run checks it)
        self.downloaded: list[str] = []
        self.printed: list[str] = []
        self._snapshot: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._waiting: list[str] = []
        self.bridge = Bridge()
        self.bridge.open_page.connect(self.open_page)
        self.bridge.open_address.connect(self.open_address)
        self.profile = self._profile()
        self.tray = tray or Tray(
            Server(info_file),
            Autostart(),
            open_url=lambda address: self.bridge.open_address.emit(str(address)),
            start_server=lambda: detached(server_command()),
            confirm=self._confirm,
            events_file=events_file,
        )
        self.tray.stop_tray = self.bridge.quit.emit
        self.bridge.quit.connect(self.quit)
        self.icon_shown: QSystemTrayIcon | None = None
        self._wait_timer = QTimer(self)
        self._wait_timer.timeout.connect(self._server_up)
        self._waited = 0

    # ----- the profile -----

    def _profile(self) -> QWebEngineProfile:
        profile = QWebEngineProfile("swissarmybench", self)
        storage = self.folder / "profile"
        profile.setPersistentStoragePath(str(storage))
        profile.setCachePath(str(storage / "cache"))
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        # Each permission is asked of the shell every time (it grants the clipboard to the app only).
        profile.setPersistentPermissionsPolicy(QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime)
        profile.setDownloadPath(downloads_folder())
        settings = profile.settings()
        attribute = QWebEngineSettings.WebAttribute
        for name, on in (
            (attribute.JavascriptCanOpenWindows, True),
            (attribute.JavascriptCanAccessClipboard, True),
            (attribute.JavascriptCanPaste, True),
            (attribute.LocalStorageEnabled, True),
            (attribute.FullScreenSupportEnabled, True),
            (attribute.LocalContentCanAccessRemoteUrls, False),
            (attribute.LocalContentCanAccessFileUrls, False),
            (attribute.AllowRunningInsecureContent, False),
            (attribute.PluginsEnabled, False),
        ):
            settings.setAttribute(name, on)
        script = QWebEngineScript()
        script.setName("swissarmybench-shell")
        script.setSourceCode(SHELL_SCRIPT)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        profile.scripts().insert(script)
        profile.downloadRequested.connect(self.download)
        return profile

    # ----- the server -----

    def _server_port(self) -> int:
        info = read_info(self.info_file)
        port = info.get("port") if info else None
        return port if isinstance(port, int) else 0

    def _confirm(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(None, title, text)
        return bool(answer == QMessageBox.StandardButton.Yes)

    # ----- opening pages -----

    def open_page(self, page: str) -> None:
        """A page of the app (no token): its address made from the running server's connection file. The
        server not running yet: it is started (the tray's way), and the page opens once it answers."""
        info = read_info(self.info_file)
        if info is None or not self.tray.server.running():
            self._waiting.append(page)
            if not self._wait_timer.isActive():
                self.tray.ensure_server()
                self._waited = 0
                self._wait_timer.start(300)
            return
        self.port = int(info["port"])
        self.open_address(rules.address_of(page, self.port, str(info["token"])))

    def _server_up(self) -> None:
        self._waited += 300
        if self.tray.server.running():
            self._wait_timer.stop()
            waiting, self._waiting = self._waiting, []
            for page in waiting:
                self.open_page(page)
        elif self._waited >= SERVER_WAIT_MS:
            self._wait_timer.stop()
            self._waiting.clear()
            self.notify("Swiss Army Bench did not start.")

    def open_address(self, address: str) -> AppWindow | None:
        """A full address: the app's page goes to its window (raised, loaded when it says more), or a new
        one; any other address to the system's browser."""
        port = self._server_port() or self.port
        self.port = port
        if rules.decide(address, port) != rules.INSIDE or address.startswith("about:"):
            self.outside(QUrl(address))
            return None
        found = [rules.Open(w.ident, w.name, w.page.url().toString()) for w in self.windows.values()]
        ident, load = rules.target(address, found)
        if ident is not None:
            window = self.windows[ident]
            if load:
                window.page.load(QUrl(address))
            window.bring_forward()
            return window
        window = self.new_window()
        window.kind = rules.kind_of(address)
        window.page.load(QUrl(address))
        window.place()
        self.changed()
        return window

    def new_window(self, popup: bool = False) -> AppWindow:
        window = AppWindow(self, self._next, popup)
        self._next += 1
        self.windows[window.ident] = window
        self.changed()
        return window

    def closed(self, window: AppWindow) -> None:
        self.windows.pop(window.ident, None)
        self.changed()

    def outside(self, url: QUrl) -> None:
        """An address that is not the app's: the system's browser opens it (http, https, mailto only)."""
        address = url.toString()
        if address.split(":", 1)[0].lower() in rules.OUTSIDE_SCHEMES:
            self.outside_opened.append(address)
            self.open_outside(url)

    def show_folder(self, folder: str) -> None:
        self.open_outside_folder(folder)

    def open_outside_folder(self, folder: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ----- what is open (the channel's status, on its own thread) -----

    def changed(self) -> None:
        said = []
        for w in self.windows.values():
            address = w.page.url().toString()
            try:
                page = rules.page_of(address) if rules.is_ours(address, self.port) else ""
            except rules.ShellError:
                page = ""
            said.append({"kind": w.kind or "", "title": w.windowTitle(), "page": page, "name": w.name})
        with self._lock:
            self._snapshot = said

    def status(self) -> dict[str, Any]:
        with self._lock:
            windows = list(self._snapshot)
        return {"running": True, "pid": os.getpid(), "windows": windows, "tray": self.icon_shown is not None}

    def heard(self, said: dict[str, Any]) -> dict[str, Any]:
        """The channel's message (on its thread): open a page, or what is open."""
        if "open" in said:
            self.bridge.open_page.emit(str(said["open"]))
            return {"ok": True}
        return self.status()

    # ----- the windows' places -----

    def saved_for(self, kind: str) -> rules.Saved | None:
        return rules.read_saved(self.places.read()).get(kind) if kind else None

    def remember(self, kind: str, saved: rules.Saved) -> None:
        self.places.write_text(rules.windows_text(rules.remembered(self.places.read(), kind, saved)))

    # ----- downloads and printing -----

    def window_of(self, page: Any) -> AppWindow | None:
        return next((w for w in self.windows.values() if w.page is page), None)

    def front_window(self) -> AppWindow | None:
        active = QApplication.activeWindow()
        if isinstance(active, AppWindow):
            return active
        return next(reversed(self.windows.values()), None) if self.windows else None

    def download(self, download: QWebEngineDownloadRequest) -> None:
        window = self.window_of(download.page()) or self.front_window()
        name = rules.download_name(download.suggestedFileName())
        start = str(Path(self.profile.downloadPath() or downloads_folder()) / name)
        chosen = self.save_dialog(window, "Save", start, "")
        if not chosen:
            download.cancel()
            return
        path = Path(chosen)
        download.setDownloadDirectory(str(path.parent))
        download.setDownloadFileName(path.name)
        download.accept()
        if window is not None:
            window.track(download, path)

    def print_page(self, window: AppWindow) -> None:
        """window.print(), Ctrl+P: Print to PDF, where the Save dialog says."""
        start = str(Path(downloads_folder()) / rules.pdf_name(window.windowTitle()))
        chosen = self.save_dialog(window, "Print to PDF", start, "PDF (*.pdf)")
        if chosen:
            window.print_to(chosen if chosen.lower().endswith(".pdf") else f"{chosen}.pdf")

    # ----- the tray icon -----

    def show_tray(self) -> bool:
        """The tray icon (Tray's menu, drawn by Qt), where the system has a tray."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        icon = QSystemTrayIcon(self.icon, self)
        menu = QMenu()
        menu.aboutToShow.connect(lambda: self._fill(menu))
        icon.setContextMenu(menu)
        icon.activated.connect(self._clicked)
        icon.setToolTip(tooltip(self.tray.state))
        icon.show()
        self.icon_shown = icon
        self._menu = menu
        self.tray.said = self.bridge.say.emit
        self.bridge.say.connect(self.notify)
        self.bridge.tray_changed.connect(self._draw)
        return True

    def _clicked(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.tray.act("open")

    def _fill(self, menu: QMenu) -> None:
        menu.clear()
        for entry in self.tray.menu():
            if entry.separator:
                menu.addSeparator()
                continue
            action = menu.addAction(entry.text)
            action.setEnabled(entry.enabled)
            if entry.checked is not None:
                action.setCheckable(True)
                action.setChecked(entry.checked)
            if entry.default:
                font = action.font()
                font.setBold(True)
                action.setFont(font)
            action.triggered.connect(lambda _=False, which=entry.id: self._act(which))

    def _act(self, which: str) -> None:
        # Stopping, restarting and starting the server wait on it: off the window thread.
        if which.split(":", 1)[0] in ("restart", "start", "quit"):
            threading.Thread(target=self.tray.act, args=(which,), daemon=True).start()
        else:
            self.tray.act(which)

    def _draw(self) -> None:
        if self.icon_shown is not None:
            self.icon_shown.setIcon(QIcon(draw_mark(64, dot=bool(self.tray.state.update))))
            self.icon_shown.setToolTip(tooltip(self.tray.state))

    def notify(self, text: str) -> None:
        if self.icon_shown is not None:
            self.icon_shown.showMessage(APP_NAME, text[:250], self.icon)

    def poll(self) -> None:
        """The tray's look at the server (its menu, the watchdog, an update under way), off the window thread."""

        def look() -> None:
            with contextlib.suppress(Exception):
                self.tray.refresh()
            self.bridge.tray_changed.emit()

        threading.Thread(target=look, daemon=True).start()

    # ----- the end -----

    def quit(self) -> None:
        for window in list(self.windows.values()):
            window.close()
        self.app.quit()

    def shutdown(self) -> None:
        """Every window closed and its page gone before the profile (Qt WebEngine asks that order)."""
        for window in list(self.windows.values()):
            window.close()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.profile.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def serve(shell: Shell, record: RecordFile) -> Listener:
    """The shell's channel, its port and a fresh key in tray.json (with the shell's process id)."""
    key = new_key()
    listener = Listener(key, shell.heard)
    record.write(rules.record(os.getpid(), listener.port, key))
    return listener


def run(lock: Any, tray_mode: bool, page: str | None, info_file: Path, events_file: Path | None) -> int:
    """The shell, until Quit (or an update): the channel, the tray icon, the first window."""
    os.environ.setdefault("QTWEBENGINE_DIALOG_SET", "QtWebEngine")  # the profile's own dialogs, Qt's
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName("Swiss Army Bench")
    QApplication.setDesktopFileName("swissarmybench")
    found = QApplication.instance()
    app = found if isinstance(found, QApplication) else QApplication(sys.argv[:1])
    record = RecordFile(info_file.with_name("tray.json"))
    shell = Shell(app, info_file, events_file=events_file)
    listener = serve(shell, record)
    has_tray = shell.show_tray()
    # Closing the last window leaves the shell in the tray (as closing the browser leaves the server); with
    # no tray to come back from, it ends with its last window.
    app.setQuitOnLastWindowClosed(not has_tray)
    shell.tray.ensure_server()
    timer = QTimer()
    timer.timeout.connect(shell.poll)
    timer.start(int(POLL_SECONDS * 1000))
    shell.poll()
    if not tray_mode or page:
        shell.open_page(page or rules.HOME_PAGE)
    elif not has_tray:
        listener.close()
        record.remove(os.getpid())
        lock.release()
        return 0  # no tray to show and no window asked for: the server is started, nothing else to do
    try:
        return int(app.exec())
    finally:
        shell.shutdown()
        listener.close()
        record.remove(os.getpid())
        lock.release()
