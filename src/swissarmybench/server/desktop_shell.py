"""The desktop app: Swiss Army Bench's pages in windows of their own (PySide6, Qt WebEngine: Chromium), over
the local server it starts and owns (the owner, 2026-11-18: "It's not an extension it is the app framework
now and it should have been since the start"). server/desktop.py starts it; domain/desktop.py has its rules.

One QApplication; each page a QMainWindow holding a QWebEngineView, every view on one persistent profile in
the state folder's desktop/profile (cookies: the sab_<port> cookie the token buys; localStorage; the cache).

  window.open        QWebEnginePage.createWindow: a new app window (Chromium itself finds a named window
                     that is open, as a browser does; the page's focus() raises it: the shell's small script)
  outside addresses  the system's browser (QDesktopServices.openUrl), never inside the shell
  downloads          the profile's downloadRequested: a Save dialog, the progress, Show in folder
  window.print()     Print to PDF: a Save dialog, then QWebEnginePage.printToPdf
  permissions        the clipboard for the app's own origin; nothing else to anyone
  keys               F12 the developer tools (a window of their own), F11 full screen, Alt+Left/Right back
                     and forward, Ctrl+P print, Ctrl+Shift+B the page in the browser (also on the right-click
                     menu: Open in browser). The page's first (the shell's script, when the page leaves
                     them): F5 and Ctrl+R reload, Ctrl+W closes the window. The pages take the browser's keys
                     in the app (window.sabApp): Ctrl+W a tab, Ctrl+T and Ctrl+N new, Ctrl+Tab, Ctrl+Shift+T
  files              `swissarmybench open <file>` ({"file": path} on the channel), a file dropped from the
                     system (its real path), macOS's Open with (FileOpen): server/desktop.py file_page
  the server's life  no server running: it is started (`swissarmybench start --no-window`, off the window
                     thread; the first window says Starting… meanwhile); the last window closed: the server is
                     told (POST /lifecycle/closed, services/lifecycle.py, from a thread) and the app ends. A
                     window asks its page first (beforeunload: unsaved work says so); the channel's quit
                     does not (`swissarmybench stop`, an update).

Nothing here holds the token but the addresses the windows load (read from the server's connection file
each time a page is opened); the channel's messages and the command line carry pages without it.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
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
    QPushButton,
    QWidget,
)

from swissarmybench.adapters.desktop import JsonState, Listener, RecordFile, new_key
from swissarmybench.domain import desktop as rules
from swissarmybench.server.lifecycle import home_path, post_json, process_alive, read_info, running_server
from swissarmybench.server.updater import detached

APP_NAME = "Swiss Army Bench"
# The pages' console line the shell's script writes: a focus() (raise this window), the window's name, or a
# close (the page's Ctrl+W with no tab left: the window).
MARK = "\u2063sab-shell "
SHELL_SCRIPT = """
(() => {
  if (window.__sabShell) return;
  window.__sabShell = true;
  const say = (m) => console.info("__MARK__" + JSON.stringify(m));
  // The page knows it is in the desktop app: the browser's keys are the app's (Ctrl+W, Ctrl+T, Ctrl+N,
  // Ctrl+Tab, Ctrl+Shift+T), and print waits for the PDF. close(): this window (asking its page first).
  // fullScreen(on): the window itself full screen or back (the pages' F11, 2026-11-21).
  const app = Object.freeze({
    app: true, close: () => say({ close: true }), fullScreen: (on) => say({ full: !!on }),
  });
  Object.defineProperty(window, "sabApp", { value: app, enumerable: false });
  // The keys a page leaves alone: F5 and Ctrl+R reload, Ctrl+W closes the window. A page that takes one
  // (the Workbench's F5 runs, a grid page's Ctrl+W closes its tab) prevents its default first.
  window.addEventListener("keydown", (e) => {
    if (e.defaultPrevented || e.altKey) return;
    const ctrl = e.ctrlKey || e.metaKey;
    const key = e.key.toLowerCase();
    if (e.key === "F5" || (ctrl && !e.shiftKey && key === "r")) { e.preventDefault(); location.reload(); }
    else if (ctrl && !e.shiftKey && key === "w") { e.preventDefault(); say({ close: true }); }
  });
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
CLOSED_TIMEOUT_SECONDS = 2.0
# window.print() returns at once in Qt (the Save dialog and the PDF come after): the page is told when it is
# over, as a browser's afterprint, so it keeps its print layout (and its @page size) until then.
AFTER_PRINT = "window.dispatchEvent(new Event('afterprint')); true"
# The first window while the server comes up (a page of its own: nothing of the app's is there yet).
STARTING_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Swiss Army Bench</title><style>
:root { color-scheme: light dark; }
body { margin: 0; height: 100vh; display: grid; place-items: center; font: 15px system-ui, sans-serif;
  background: Canvas; color: GrayText; }
</style></head><body><p>Starting…</p></body></html>"""

AskSave = Callable[[QWidget | None, str, str, str], str]
OpenOutside = Callable[[QUrl], object]


def draw_mark(size: int = 64, dot: bool = False) -> QPixmap:
    """The app's mark (the pages' icon, the windows', the launcher's): a red rounded square, a white cross;
    `dot`: the update's dot."""
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


class Bridge(QObject):  # type: ignore[misc,unused-ignore]  # Any to mypy without PySide6
    """Calls from other threads (the channel) handed to the window thread."""

    open_page = Signal(str)  # a page of the app, no token
    file_shown = Signal(str)  # a file opened with the app: the page that shows it
    said = Signal(str)  # words for the front window's status line (a file that did not open)
    server_up = Signal(bool)  # the server answered (True), or did not start in time
    quit = Signal()


class Drops(QObject):  # type: ignore[misc,unused-ignore]  # Any to mypy without PySide6
    """Files dropped from the system on a window: their real paths opened with the app (so a table's origin
    is its file and a project reads it again), before Chromium would take them as an upload. Installed on
    each window's view and the view's child that draws the page. The browser keeps its upload."""

    def __init__(self, shell: Shell) -> None:
        super().__init__(shell)
        self.shell = shell

    def eventFilter(self, watched: Any, event: Any) -> bool:
        kind = event.type()
        if kind not in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            return False
        mime = event.mimeData()
        paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()] if mime and mime.hasUrls() else []
        if not paths:
            return False
        event.acceptProposedAction()
        if kind == QEvent.Type.Drop:
            for path in paths[:20]:
                self.shell.open_file(path)
        return True


class App(QApplication):  # type: ignore[misc,unused-ignore]  # Any to mypy without PySide6
    """The app's QApplication: macOS's Open with (a QFileOpenEvent) opens the file, as a drop does."""

    file_opened: Callable[[str], None] | None = None

    def event(self, event: Any) -> bool:
        if event.type() == QEvent.Type.FileOpen and self.file_opened is not None and event.file():
            self.file_opened(event.file())
            return True
        return bool(super().event(event))


class Page(QWebEnginePage):  # type: ignore[misc,unused-ignore]  # Any to mypy without PySide6
    """One window's page: what loads inside, new windows, the shell's console lines, print, close."""

    def __init__(self, shell: Shell, window: AppWindow) -> None:
        super().__init__(shell.profile, window)
        self.shell = shell
        self.window = window

    def acceptNavigationRequest(
        self, url: QUrl | str, kind: QWebEnginePage.NavigationType, main_frame: bool
    ) -> bool:
        address = url.toString() if isinstance(url, QUrl) else str(url)
        if self.window.starting and main_frame and address.startswith("data:"):
            return True  # the shell's own Starting… page (setHtml)
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
        return self.shell.new_window().page

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
            if said.get("close") is True:
                QTimer.singleShot(0, self.window.close)  # its page is asked first (beforeunload)
            if isinstance(said.get("name"), str):
                self.window.name = said["name"][:200]
                self.shell.changed()
            if isinstance(said.get("full"), bool):
                self.window.full_screen(said["full"])


class AppWindow(QMainWindow):  # type: ignore[misc,unused-ignore]  # Any to mypy without PySide6
    """A page of the app in a window of its own."""

    def full_screen(self, on: bool) -> None:
        """The window full screen (a page's F11 or its full-screen button, 2026-11-21), or back as it was
        (maximized again when it was)."""
        if on == self.isFullScreen():
            return
        if on:
            self.was_maximized = self.isMaximized()
            self.showFullScreen()
        elif getattr(self, "was_maximized", False):
            self.showMaximized()
        else:
            self.showNormal()

    def __init__(self, shell: Shell, ident: int) -> None:
        super().__init__()
        self.shell = shell
        self.ident = ident
        self.starting = False  # showing the shell's Starting… page while the server comes up
        self.name = ""
        self.kind = ""
        self.fresh = True  # nothing of the app shown yet (a window.open's about:blank)
        self.requested: tuple[int, int] | None = None
        self.placed = False
        self.agreed = False  # the page agreed to close (or was never asked: nothing of it shown)
        self.raised = 0  # how often it was brought forward (a page's focus(), a page opened again)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowIcon(shell.icon)
        self.setWindowTitle(APP_NAME)
        self.view = QWebEngineView(self)
        self.page = Page(shell, self)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        self._dropped_on: set[int] = set()
        self.watch_drops()
        # The right-click menu where the page has none of its own: Back, Forward, Reload, ... and Open in
        # browser (the browser stays possible).
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._menu)
        self.devtools: QMainWindow | None = None
        page = self.page
        page.titleChanged.connect(lambda title: self.setWindowTitle(rules.window_title(title)))
        page.urlChanged.connect(self._url_changed)
        page.windowCloseRequested.connect(self._page_agreed)
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
            # F5, Ctrl+R and Ctrl+W are the page's first (the shell's script: a page that does not take one
            # reloads or closes the window), so the Workbench's F5 runs and Ctrl+W closes a tab.
            ("Ctrl+P", lambda: shell.print_page(self)),
            ("Ctrl+Shift+B", lambda: shell.open_in_browser(self)),
        ):
            QShortcut(QKeySequence(keys), self, action)

    def watch_drops(self) -> None:
        """The drop filter on the view and on its child that draws the page (made with the page)."""
        for widget in (self.view, self.view.focusProxy()):
            if widget is not None and id(widget) not in self._dropped_on:
                self._dropped_on.add(id(widget))
                widget.installEventFilter(self.shell.drops)

    # ----- where it goes -----

    def _geometry_asked(self, rect: Any) -> None:
        self.requested = (int(rect.width()), int(rect.height())) if rect.width() and rect.height() else None
        if self.placed and self.requested and not self.shell.saved_for(self.kind):
            self.resize(*self.requested)

    def _url_changed(self, url: QUrl) -> None:
        address = url.toString()
        self.watch_drops()
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

    def _page_agreed(self) -> None:
        self.agreed = True
        self.close()

    def closeEvent(self, event: Any) -> None:
        # The page is asked first (its beforeunload: a Workbench with unsaved work says so); it answers with
        # windowCloseRequested, which closes the window for good.
        if not (self.agreed or self.fresh or self.shell.closing):
            event.ignore()
            self.page.triggerAction(QWebEnginePage.WebAction.RequestClose)
            return
        self.remember()
        if self.devtools is not None:
            self.devtools.close()
        self.shell.closed(self)
        super().closeEvent(event)

    def _menu(self, at: Any) -> None:
        menu = self.view.createStandardContextMenu()
        menu.addSeparator()
        menu.addAction("Open in browser", lambda: self.shell.open_in_browser(self))
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.popup(self.view.mapToGlobal(at))

    # ----- full screen, developer tools, permissions -----

    def toggle_full_screen(self) -> None:
        """F11: a page with a full screen of its own (the Notebooks and Scripts pages: the IDE alone) takes
        it, and asks for the window's through sabApp.fullScreen; any other page, the window alone."""

        def answered(took: Any) -> None:
            if took is True:
                return
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()

        self.page.runJavaScript(
            "typeof window.sabFullScreen === 'function' ? (window.sabFullScreen(), true) : false", 0, answered
        )

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
        self.after_print()
        if ok:
            self.tell(f"Saved {name}", str(Path(path).parent))
            self.shell.printed.append(path)
        else:
            self.tell(f"{name} could not be printed.")

    def after_print(self) -> None:
        """The page's afterprint: its print layout ends now that the PDF is written (or was not wanted)."""
        self.page.runJavaScript(AFTER_PRINT)


class Shell(QObject):  # type: ignore[misc,unused-ignore]  # Any to mypy without PySide6
    """The app's windows and its channel, in one QApplication."""

    def __init__(
        self,
        app: QApplication,
        info_file: Path,
        *,
        save_dialog: AskSave = ask_save,
        open_outside: OpenOutside = QDesktopServices.openUrl,
        start_server: Callable[[], object] | None = None,
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
        self.bridge.server_up.connect(self._server_up)
        self.profile = self._profile()
        self.start_server = start_server or (lambda: detached(server_command()))
        self.bridge.quit.connect(self.quit)
        self.bridge.file_shown.connect(self._file_shown)
        self.bridge.said.connect(self._say)
        self.opened_files: list[str] = []  # files opened with the app (the real run checks them)
        # A file dropped from the system on one of the app's windows (each view and its child: AppWindow).
        self.drops = Drops(self)
        self.closing = False
        # The server that answered once (its process id and token): trusted while that process lives and the
        # connection file still names it, so opening a page never waits on a request (the window thread).
        self._trusted: tuple[int, str] | None = None
        self._watching = False
        self._starting: AppWindow | None = None
        self.told: list[threading.Thread] = []

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
        self._fresh_after_update(profile, storage)
        return profile

    @staticmethod
    def _fresh_after_update(profile: QWebEngineProfile, storage: Path) -> None:
        """A new version clears the saved copies of the pages' files once (cookies and local storage kept),
        so an update never shows the old version's screens (the owner, 2026-11-19)."""
        from swissarmybench import __version__

        mark = storage / "version.txt"
        try:
            last = mark.read_text(encoding="utf-8").strip()
        except OSError:
            last = ""
        if last == __version__:
            return
        profile.clearHttpCache()
        try:
            storage.mkdir(parents=True, exist_ok=True)
            mark.write_text(__version__, encoding="utf-8")
        except OSError:
            pass  # cleared again at the next start: harmless

    # ----- the server -----

    def _server_port(self) -> int:
        info = read_info(self.info_file)
        port = info.get("port") if info else None
        return port if isinstance(port, int) else 0

    def trusted(self, info: dict[str, Any] | None) -> bool:
        """Is `info` (the connection file) the server that already answered, its process still alive? No
        request: the window thread never waits on one."""
        if info is None or self._trusted is None:
            return False
        pid, token = info.get("pid"), info.get("token")
        return (pid, token) == self._trusted and isinstance(pid, int) and process_alive(pid)

    def _watch_server(self) -> None:
        """Off the window thread: the server started when none answers (the app owns its life: it stops once
        the app closes), then waited for; `server_up` says how it went."""
        started = False
        deadline = time.monotonic() + SERVER_WAIT_MS / 1000
        while time.monotonic() < deadline:
            found = running_server(self.info_file)
            if found is not None:
                pid, token = found.get("pid"), found.get("token")
                if isinstance(pid, int) and isinstance(token, str):
                    self._trusted = (pid, token)
                self.bridge.server_up.emit(True)
                return
            if not started:
                started = True
                self.start_server()
            time.sleep(0.3)
        self.bridge.server_up.emit(False)

    def tell_server_closed(self) -> None:
        """The app's last window closed: the server stops as soon as nothing else holds it. Sent off the
        window thread with a short limit (the process waits for it at its end: the thread is no daemon)."""
        info = read_info(self.info_file)
        if info is None:
            return

        def send() -> None:
            try:
                post_json(info, "/lifecycle/closed", {}, timeout=CLOSED_TIMEOUT_SECONDS)
            except (OSError, ValueError):
                pass

        thread = threading.Thread(target=send, name="sab-closed")
        thread.start()
        self.told.append(thread)

    def open_in_browser(self, window: AppWindow) -> None:
        """The window's page in the system's browser (the browser stays possible: Open in browser)."""
        info = read_info(self.info_file)
        if info is None:
            return
        address = window.page.url().toString()
        try:
            page = rules.page_of(address) if rules.is_ours(address, int(info["port"])) else rules.HOME_PAGE
        except rules.ShellError:
            page = rules.HOME_PAGE
        self.open_outside(QUrl(rules.address_of(page, int(info["port"]), str(info["token"]))))

    # ----- opening pages -----

    def open_page(self, page: str) -> None:
        """A page of the app (no token): its address made from the running server's connection file. The
        server not known to answer yet: it is looked for (and started) off the window thread, a first window
        says Starting… meanwhile, and the page opens once the server answers."""
        info = read_info(self.info_file)
        if info is not None and self.trusted(info):
            self.port = int(info["port"])
            self.open_address(rules.address_of(page, self.port, str(info["token"])))
            return
        self._waiting.append(page)
        if not self.windows and self._starting is None:
            self._show_starting(page)
        if not self._watching:
            self._watching = True
            threading.Thread(target=self._watch_server, name="sab-server-wait", daemon=True).start()

    def _show_starting(self, page: str) -> None:
        window = self.new_window()
        window.starting = True
        window.kind = rules.kind_of(page)
        window.page.setHtml(STARTING_HTML)
        window.place()
        self._starting = window

    def _server_up(self, ok: bool) -> None:
        self._watching = False
        waiting, self._waiting = self._waiting, []
        if ok:
            for page in waiting:
                self.open_page(page)
            return
        print("Swiss Army Bench did not start.", file=sys.stderr)
        if self._starting is not None:
            self._starting.page.setHtml(STARTING_HTML.replace("Starting…", "Swiss Army Bench did not start."))

    def open_address(self, address: str) -> AppWindow | None:
        """A full address: the app's page goes to its window (raised, loaded when it says more), or a new
        one; any other address to the system's browser."""
        port = self._server_port() or self.port
        self.port = port
        if rules.decide(address, port) != rules.INSIDE or address.startswith("about:"):
            self.outside(QUrl(address))
            return None
        starting, self._starting = self._starting, None
        if starting is not None and starting.ident in self.windows:
            # The first page goes into the window that said Starting….
            starting.starting = False
            starting.kind = rules.kind_of(address)
            starting.page.load(QUrl(address))
            starting.bring_forward()
            self.changed()
            return starting
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

    def new_window(self) -> AppWindow:
        window = AppWindow(self, self._next)
        self._next += 1
        self.windows[window.ident] = window
        self.changed()
        return window

    def closed(self, window: AppWindow) -> None:
        self.windows.pop(window.ident, None)
        self.changed()
        if window is self._starting:
            # The Starting… window closed before the server answered: nothing more opens; the app ends.
            self._starting = None
            self._waiting.clear()
            if not self.windows and not self.closing:
                QTimer.singleShot(0, self.app.quit)
            return
        if not self.windows and not self.closing and not window.fresh:
            # The app's last window closed: the server stops as soon as nothing else holds it; the app ends.
            self.tell_server_closed()
            QTimer.singleShot(0, self.app.quit)

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
        return {"running": True, "pid": os.getpid(), "windows": windows}

    def heard(self, said: dict[str, Any]) -> dict[str, Any]:
        """The channel's message (on its thread): open a page, quit, or what is open."""
        if "open" in said:
            self.bridge.open_page.emit(str(said["open"]))
            return {"ok": True}
        if said.get("quit") is True:
            self.bridge.quit.emit()
            return {"ok": True}
        if "file" in said:
            self.open_file(str(said["file"]))
            return {"ok": True}
        return self.status()

    # ----- files opened with the app: `swissarmybench open <file>`, Open with, a drop -----

    def open_file(self, path: str) -> None:
        """A file opened with the app, off the window thread: read by its path through the server
        (server/desktop.py file_page: a table, a notebook, a blade, a project), then its page shown."""
        threading.Thread(target=self._open_file, args=(path,), name="sab-open-file", daemon=True).start()

    def _open_file(self, path: str) -> None:
        from swissarmybench.server import desktop as launch

        deadline = time.monotonic() + SERVER_WAIT_MS / 1000
        info = running_server(self.info_file)
        while info is None and time.monotonic() < deadline:
            time.sleep(0.3)  # the app is starting its server (open_page): it answers in a moment
            info = running_server(self.info_file)
        if info is None:
            self.bridge.said.emit(f"{Path(path).name} was not opened: Swiss Army Bench did not start.")
            return
        try:
            page = launch.file_page(path, info)
        except (OSError, ValueError) as error:
            self.bridge.said.emit(str(error)[:300])
            return
        self.opened_files.append(path)
        self.bridge.file_shown.emit(page)

    def _file_shown(self, page: str) -> None:
        # A table's grid: the home window brought forward (its page shows the new tab by itself: the server's
        # grid_shown); with none open, one opens on the grid.
        if page.startswith(rules.HOME_PAGE + "#") and any(w.kind == "home" for w in self.windows.values()):
            page = rules.HOME_PAGE
        self.open_page(page)

    def _say(self, text: str) -> None:
        window = self.front_window()
        if window is not None:
            window.tell(text)
        else:
            print(text, file=sys.stderr)

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
        else:
            window.after_print()

    # ----- the end -----

    def quit(self) -> None:
        """The channel's quit (`swissarmybench stop`, an update's helper): every window closed without asking
        its page (an update warned in the page first; a stop from a terminal is the user's own word), each
        window's place kept (windows.json), the server told, the app ended."""
        had = bool(self.windows)
        self.closing = True
        for window in list(self.windows.values()):
            window.close()
        if had:
            self.tell_server_closed()
        self.app.quit()

    def shutdown(self) -> None:
        """Every window closed and its page gone before the profile (Qt WebEngine asks that order)."""
        self.closing = True
        for window in list(self.windows.values()):
            window.close()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.profile.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def serve(shell: Shell, record: RecordFile) -> Listener:
    """The shell's channel, its port and a fresh key in desktop.json (with the app's process id)."""
    key = new_key()
    listener = Listener(key, shell.heard)
    record.write(rules.record(os.getpid(), listener.port, key))
    return listener


def server_command(python: str = sys.executable) -> list[str]:
    """The server the app starts: `swissarmybench start --no-window` (the app shows the windows itself)."""
    path = Path(python)
    if path.name.lower() == "pythonw.exe" and (path.parent / "python.exe").is_file():
        python = str(path.parent / "python.exe")  # the server writes to a console nobody sees: no window
    return [python, "-m", "swissarmybench.server", "start", "--no-window"]


def run(lock: Any, page: str | None, info_file: Path) -> int:
    """The app, until its last window closes: the channel, the server, the first window."""
    os.environ.setdefault("QTWEBENGINE_DIALOG_SET", "QtWebEngine")
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName("Swiss Army Bench")
    QApplication.setDesktopFileName("swissarmybench")
    found = QApplication.instance()
    app = found if isinstance(found, QApplication) else App(sys.argv[:1])
    record = RecordFile(info_file.with_name(rules.RECORD))
    shell = Shell(app, info_file)
    if isinstance(app, App):
        app.file_opened = shell.open_file  # macOS: Open with, a file dropped on the Dock icon
    listener = serve(shell, record)
    # The last window closed: the server is told (it stops once nothing else holds it), and the app ends
    # (Shell.closed). Not Qt's own last-window rule: the developer tools are windows too.
    app.setQuitOnLastWindowClosed(False)
    shell.open_page(page or home_path())  # the chosen front end's home
    try:
        return int(app.exec())
    finally:
        shell.shutdown()
        listener.close()
        record.remove(os.getpid())
        lock.release()
