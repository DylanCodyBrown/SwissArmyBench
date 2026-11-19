"""The Desktop shell, really run (tests/test_desktop_shell.py starts this in a process of its own, with Qt
drawing off screen): the shell starts the server, loads the home page, window.open makes a second window
and a named one is reused and raised, an Export's download lands where the Save dialog (stood in) says,
Print to PDF writes a PDF, an outside link goes to the system's browser (stood in), the clipboard works,
the windows' places are remembered, the channel opens a page, and closing every window stops the server.

    python tests/desktop_drive.py <folder> [<screenshots folder>]

Made-up data only. Writes <folder>/result.json: each check's name and what it saw.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from swissarmybench.adapters.desktop import RecordFile, ask
from swissarmybench.domain import desktop as rules
from swissarmybench.server import desktop_shell as shell_module
from swissarmybench.server.lifecycle import read_info, running_server

ORDERS = "order_id\tregion\tamount\n1\tNorth\t120.50\n2\tSouth\t80.00\n3\tEast\t42.25\n4\tWest\t310.75\n"


def main(folder: Path, shots: Path | None) -> int:
    results: dict[str, Any] = {}
    info_file = Path(os.environ["SWISSARMYBENCH_INFO"])
    saved_to = folder / "saved"
    saved_to.mkdir(parents=True, exist_ok=True)
    asked: list[tuple[str, str]] = []
    outside: list[str] = []

    def save_dialog(parent: Any, title: str, start: str, filters: str) -> str:
        asked.append((title, Path(start).name))
        if title == "Print to PDF":
            time.sleep(2.0)  # the user choosing a name: longer than a browser page's own 1.5 s wait
        return str(saved_to / Path(start).name)

    app = QApplication(sys.argv[:1])
    shell = shell_module.Shell(
        app, info_file, save_dialog=save_dialog, open_outside=lambda url: outside.append(url.toString())
    )
    record = RecordFile(info_file.with_name(rules.RECORD))
    closed_told = [0]
    tell = shell.tell_server_closed

    def told() -> None:
        closed_told[0] += 1
        tell()

    shell.tell_server_closed = told  # type: ignore[method-assign]
    listener = shell_module.serve(shell, record)

    def wait(check: Callable[[], Any], seconds: float = 30.0, what: str = "") -> Any:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            got = check()
            if got:
                return got
            time.sleep(0.02)
        raise TimeoutError(what or "waited too long")

    def js(window: Any, code: str, seconds: float = 15.0) -> Any:
        box: list[Any] = []
        window.page.runJavaScript(code, 0, lambda value: box.append(value))
        wait(lambda: box, seconds, f"script: {code[:60]}")
        return box[0]

    def loaded(window: Any) -> bool:
        return bool(js(window, "document.readyState === 'complete' && !!document.querySelector('.nav-rail')"))

    def shot(window: Any, name: str) -> None:
        if shots is not None:
            wait(lambda: True, 0.5)
            window.grab().save(str(shots / name))

    def call(method: str, route: str, body: bytes | None = None) -> Any:
        info = read_info(info_file) or {}
        request = urllib.request.Request(
            f"http://127.0.0.1:{info['port']}{route}",
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "text/csv"},
        )
        with urllib.request.urlopen(request, timeout=30) as answer:  # noqa: S310 (127.0.0.1)
            return json.loads(answer.read() or b"null")

    try:
        # 1. No server yet: the shell starts it, then opens the home page with the token, as the browser.
        assert running_server(info_file) is None
        started = time.monotonic()
        shell.open_page(rules.HOME_PAGE)
        home = wait(lambda: next(iter(shell.windows.values()), None), 60, "the first window")
        wait(lambda: running_server(info_file), 60, "the server")
        results["server_started_by_shell"] = True
        wait(lambda: rules.is_ours(home.page.url().toString(), shell.port) and loaded(home), 60, "home page")
        results["home_loaded_seconds"] = round(time.monotonic() - started, 1)
        # One window from the start: it said Starting… while the server came up, then showed the page.
        results["windows_at_start"] = len(shell.windows)
        results["home_kind"] = home.kind
        results["home_name"] = wait(lambda: home.name, 10, "home window's name")
        results["home_title"] = home.windowTitle()
        results["cookie_page_without_token"] = "token=" not in home.page.url().toString()

        # 2. A made-up table, pasted; its grid shown in the home window.
        pasted = call("POST", "/datasets/orders/paste", ORDERS.encode())
        grid = pasted.get("grid") or pasted.get("grid_id") or pasted.get("id")
        results["grid"] = grid
        wait(lambda: js(home, "document.body.innerText.includes('North')"), 30, "the grid's rows")
        shot(home, "desktop-home-window.png")

        # 3. window.open: a second app window (the Workbench); the same name again reuses it.
        js(home, "window.open('/workbench', 'swissarmybench-workbench'); true")
        wb = wait(lambda: next((w for w in shell.windows.values() if w.kind == "workbench"), None), 30, "wb")
        wait(lambda: loaded(wb), 60, "the Workbench page")
        results["window_open_made_window"] = len(shell.windows)
        results["workbench_title"] = wb.windowTitle()
        js(home, "window.open('/workbench', 'swissarmybench-workbench'); true")
        wait(lambda: True, 1.0)
        results["named_window_reused"] = len(shell.windows)
        # The Workbench brings the home window forward by its name (nav.ts: window.open("", "sab-home"))
        before = home.raised
        js(wb, "(() => { const w = window.open('', 'sab-home'); w.focus(); return w === window; })()")
        wait(lambda: home.raised > before, 10, "the home window raised")
        results["home_raised_by_name"] = home.raised - before
        results["windows_after_focus"] = len(shell.windows)
        shot(wb, "desktop-workbench-window.png")

        # 4. An Export's download (the export dialog's own way: the route's file as a blob, saved by a link).
        js(
            home,
            "fetch('/grids/" + str(grid) + "/export?format=csv').then(r => r.blob()).then(b => {"
            " const a = document.createElement('a'); a.href = URL.createObjectURL(b);"
            " a.download = 'orders.csv';"
            " document.body.append(a); a.click(); a.remove(); }); true",
        )
        path = wait(lambda: shell.downloaded, 30, "the download")[0]
        results["download_dialog"] = asked[-1]
        results["download_path_name"] = Path(path).name
        results["download_text"] = Path(path).read_text(encoding="utf-8-sig")[:200]
        results["download_status"] = home._status_label.text()
        results["download_show_in_folder"] = not home._status_button.isHidden()
        shot(home, "desktop-download-saved.png")

        # 5. Print to PDF: the page's window.print() (Visualizations' Print to PDF calls it, its paper's
        # @page size set and its print layout on until afterprint): the shell fires afterprint once the PDF
        # is written.
        results["page_knows_the_app"] = js(home, "typeof window.sabApp === 'object' && window.sabApp.app")
        js(
            home,
            "window.__after = []; const st = document.createElement('style'); st.id = 'drive-page';"
            " st.textContent = '@page { size: 11in 8.5in; margin: 0; }'; document.head.append(st);"
            " document.body.classList.add('drive-printing');"
            " window.addEventListener('afterprint', () => window.__after.push("
            "document.body.classList.contains('drive-printing')), { once: true });"
            " setTimeout(() => window.print(), 10); true",
        )
        pdf = wait(lambda: shell.printed, 60, "the PDF")[0]
        results["print_dialog"] = asked[-1]
        results["pdf_head"] = Path(pdf).read_bytes()[:5].decode("latin-1")
        results["pdf_size"] = Path(pdf).stat().st_size
        boxes = re.findall(rb"/MediaBox\s*\[([^\]]*)\]", Path(pdf).read_bytes())
        results["pdf_mediabox"] = boxes[0].decode().split() if boxes else []
        results["afterprint"] = wait(
            lambda: (
                js(home, "JSON.stringify(window.__after)") != "[]"
                and js(home, "JSON.stringify(window.__after)")
            ),
            10,
            "afterprint",
        )
        js(home, "document.getElementById('drive-page').remove();"
           " document.body.classList.remove('drive-printing'); true")  # fmt: skip

        # 6. Outside addresses: the system's browser, never inside the shell.
        count = len(shell.windows)
        js(
            home,
            "const a = document.createElement('a'); a.href = 'https://example.com/release-notes';"
            " a.target = '_blank'; document.body.append(a); a.click(); a.remove(); true",
        )
        wait(lambda: "https://example.com/release-notes" in outside, 15, "outside link (new window)")
        wait(lambda: len(shell.windows) == count, 10, "the empty window closed")
        js(home, "window.open('https://example.com/device', '_blank', 'noopener'); true")
        wait(lambda: "https://example.com/device" in outside, 15, "outside window.open")
        js(home, "location.href = 'https://example.com/elsewhere'; true")
        wait(lambda: "https://example.com/elsewhere" in outside, 15, "outside navigation")
        wait(lambda: True, 0.5)
        results["outside"] = list(outside)
        results["home_still_ours"] = rules.is_ours(home.page.url().toString(), shell.port)
        results["windows_after_outside"] = len(shell.windows)

        # 7. The clipboard, granted to the app's own origin (the page needs the focus to use it).
        home.bring_forward()
        proxy = home.view.focusProxy() or home.view
        proxy.clearFocus()
        wait(lambda: True, 0.2)
        proxy.setFocus()
        wait(lambda: True, 0.3)
        results["focus"] = [
            QApplication.activeWindow() is home,
            type(QApplication.focusWidget()).__name__,
            js(home, "document.hasFocus()"),
        ]
        js(
            home,
            "window.__clip = 'pending'; navigator.clipboard.writeText('North,120.50')"
            ".then(() => navigator.clipboard.readText()).then(t => window.__clip = t)"
            ".catch(e => window.__clip = 'error: ' + e); true",
        )
        results["clipboard"] = wait(
            lambda: (lambda v: v if v != "pending" else None)(js(home, "window.__clip"))
        )

        # 8. The developer tools, a window of their own (F12).
        home.toggle_devtools()
        results["devtools_window"] = home.devtools is not None and home.devtools.isVisible()
        home.toggle_devtools()

        # 9. The channel: what is open, and a page opened (as `swissarmybench open` and the server do).
        found = record.shell()
        assert found is not None
        status = ask(found[1], found[2], {"status": True})
        results["status_windows"] = sorted(w["kind"] for w in status["windows"])
        results["status_has_no_token"] = "token" not in json.dumps(status)
        ask(found[1], found[2], {"open": "/catalog"})
        catalog = wait(
            lambda: next((w for w in shell.windows.values() if w.kind == "catalog"), None), 30, "cat"
        )
        results["channel_opened"] = catalog.kind
        results["bad_key"] = ask(found[1], "x" * 43, {"status": True})

        # 10. Places remembered by kind: the Workbench closed somewhere, opened there again.
        wb.setGeometry(40, 50, 900, 640)
        wait(lambda: True, 0.3)
        wb.close()
        wait(lambda: wb.ident not in shell.windows, 10, "the Workbench closed")
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)  # app.exec() does this by itself
        wait(lambda: True, 1.5)  # Chromium lets go of the closed window's name a moment later
        places = json.loads((info_file.parent / "desktop" / "windows.json").read_text(encoding="utf-8"))
        results["remembered"] = places.get("workbench")
        results["reopen_said"] = js(
            home,
            "(() => { const w = window.open('/workbench', 'swissarmybench-workbench');"
            " return w === null ? 'null' : (w.closed ? 'closed' : 'open'); })()",
        )
        again = wait(
            lambda: next((w for w in shell.windows.values() if w.kind == "workbench"), None), 30, "wb2"
        )
        wait(lambda: again.placed, 10, "placed")
        g = again.geometry()
        results["reopened_at"] = [g.x(), g.y(), g.width(), g.height()]
        screen = QApplication.primaryScreen().availableGeometry()
        results["screen"] = [screen.width(), screen.height()]

        # 11. The right-click menu's Open in browser (the browser stays possible), and a page opened again:
        # its window raised, not a new one.
        before = len(shell.windows)
        shell.open_in_browser(catalog)
        results["open_in_browser"] = outside[-1].split("#", 1)[0]
        results["open_in_browser_has_token"] = "#token=" in outside[-1]
        found = record.shell()
        assert found is not None
        ask(found[1], found[2], {"open": "/catalog"})
        wait(lambda: True, 1.0)
        results["catalog_reused"] = len(shell.windows) == before and catalog.raised > 0
        results["profile_folder"] = sorted(
            p.name for p in (info_file.parent / "desktop" / "profile").iterdir()
        )
        shot(catalog, "desktop-catalog-window.png")

        # 11b. Files: one handed over the channel (`swissarmybench open <file>`), one dropped from the system
        # on the home window: each read by its real path (its origin the file).
        def tables() -> dict[str, Any]:
            return {g["dataset"]: g for g in call("GET", "/grids")["grids"]}

        def tab_count() -> int:
            return int(js(home, "document.querySelectorAll('.tab-item[data-grid]').length"))

        regions = folder / "regions.csv"
        regions.write_text("region,manager\nNorth,Avery\nSouth,Blake\n", encoding="utf-8")
        found = record.shell()
        assert found is not None
        results["file_answer"] = ask(found[1], found[2], {"file": str(regions)})
        wait(lambda: "regions" in tables(), 30, "the file handed over the channel")
        wait(lambda: js(home, "!!document.querySelector('.tab-item[title=\"regions\"]')"), 30, "its tab")
        results["file_origin"] = tables()["regions"]["origin"]["kind"]
        dropped = folder / "drop_me.csv"
        dropped.write_text("sku,qty\nA-1,3\nB-2,5\n", encoding="utf-8")
        target = home.view.focusProxy() or home.view
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(dropped))])
        action = Qt.DropAction.CopyAction
        button, none = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
        enter = QDragEnterEvent(QPoint(60, 60), action, mime, button, none)
        QApplication.sendEvent(target, enter)
        results["drop_accepted"] = enter.isAccepted()
        QApplication.sendEvent(target, QDropEvent(QPointF(60, 60), action, mime, button, none))
        wait(lambda: "drop_me" in tables(), 30, "the dropped file")
        results["drop_origin"] = tables()["drop_me"]["origin"]["kind"]
        results["opened_files"] = [Path(p).name for p in shell.opened_files]

        # 11c. The browser's keys are the app's: Ctrl+Tab goes round the tabs, Ctrl+W closes the one in front
        # (not the window), Ctrl+Shift+T brings it back with its steps.
        home.bring_forward()
        target.setFocus()
        wait(lambda: tab_count() >= 3, 15, "three tabs")
        before = tab_count()
        front = js(home, "document.querySelector('.tab-item.active')?.title")
        ctrl, shift = Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier
        QTest.keyClick(target, Qt.Key.Key_Tab, ctrl)
        wait(lambda: js(home, "document.querySelector('.tab-item.active')?.title") != front, 10, "Ctrl+Tab")
        results["ctrl_tab_moved"] = True
        QTest.keyClick(target, Qt.Key.Key_W, ctrl)
        wait(lambda: tab_count() == before - 1, 10, "Ctrl+W closed a tab")
        results["ctrl_w_closed_tab"] = True
        results["ctrl_w_kept_window"] = home.ident in shell.windows and home.isVisible()
        QTest.keyClick(target, Qt.Key.Key_T, ctrl | shift)
        wait(lambda: tab_count() == before, 15, "Ctrl+Shift+T reopened it")
        results["ctrl_shift_t_reopened"] = True
        # The Workbench's F5 is its own (run), never a reload; Ctrl+W with no document closes its window.
        wb_target = again.view.focusProxy() or again.view
        again.bring_forward()
        wb_target.setFocus()
        wait(lambda: loaded(again), 60, "the Workbench again")
        js(again, "window.__kept = 7; true")
        QTest.keyClick(wb_target, Qt.Key.Key_F5)
        wait(lambda: True, 1.5)
        results["workbench_f5_kept_page"] = js(again, "window.__kept === 7")
        QTest.keyClick(wb_target, Qt.Key.Key_W, ctrl)
        wait(lambda: again.ident not in shell.windows, 15, "Ctrl+W closed the Workbench window")
        results["ctrl_w_closed_empty_window"] = True

        # 12. Every window closed (each page asked first): the app tells the server, which stops.
        for window in list(shell.windows.values()):
            window.close()
        wait(lambda: not shell.windows, 30, "the windows closed")
        results["told_server_closed"] = closed_told[0]
        wait(lambda: read_info(info_file) is None, 60, "the server stopped")  # no request: it would count
        results["closing_stopped_server"] = True
        results["windows_after_close"] = len(shell.windows)
    except Exception:
        results["error"] = traceback.format_exc()
        results["windows_then"] = [
            (w.kind, w.page.url().toString()[:60], w.isVisible()) for w in shell.windows.values()
        ]
        results["outside_so_far"] = outside
        with_info = read_info(info_file)
        if with_info:
            try:
                call("POST", "/shutdown")
            except OSError:
                pass
    finally:
        shell.shutdown()
        listener.close()
        record.remove(os.getpid())
        (folder / "result.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if "error" not in results else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None))
