"""The Desktop extension's rules (extensions/desktop: domain/windows.py), its channel and its launcher: what
loads inside the shell and what goes to the system's browser, named-window reuse, the remembered places, the
shell's command line and messages. No Qt here (tests/test_desktop_shell.py runs the real shell)."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from swissarmybench_desktop.adapters import channel
from swissarmybench_desktop.domain import windows as rules
from swissarmybench_desktop.server import launch

PORT = 8790
OURS = f"http://127.0.0.1:{PORT}"


# ===== inside, outside, refused =====


@pytest.mark.parametrize(
    ("url", "main", "clicked", "verdict"),
    [
        (f"{OURS}/workspace#token=x", True, False, rules.INSIDE),
        (f"{OURS}/g/3", False, False, rules.INSIDE),
        ("about:blank", True, False, rules.INSIDE),
        ("about:srcdoc", False, False, rules.INSIDE),
        (f"blob:{OURS}/0f1e", True, False, rules.INSIDE),
        ("blob:https://example.com/0f1e", True, False, rules.REFUSE),
        ("https://github.com/x/y/releases", True, False, rules.OUTSIDE),
        ("http://127.0.0.1:9999/workspace", True, False, rules.OUTSIDE),  # another port: not this app
        ("http://localhost:8790/workspace", True, False, rules.OUTSIDE),  # the server answers 127.0.0.1 only
        ("mailto:someone@example.com", True, False, rules.OUTSIDE),
        ("https://example.com/embed", False, False, rules.REFUSE),  # a frame loading by itself
        ("https://example.com/page", False, True, rules.OUTSIDE),  # a click in a frame
        ("data:text/html,<p>x</p>", True, False, rules.REFUSE),
        ("data:text/html,<p>x</p>", False, False, rules.INSIDE),
        ("file:///etc/passwd", True, False, rules.REFUSE),
        ("javascript:alert(1)", True, True, rules.REFUSE),
        ("ftp://example.com/x", True, False, rules.REFUSE),
    ],
)
def test_only_the_apps_own_origin_loads_inside(url: str, main: bool, clicked: bool, verdict: str) -> None:
    assert rules.decide(url, PORT, main_frame=main, clicked=clicked) == verdict


def test_the_clipboard_is_granted_to_the_app_only_and_nothing_else_to_anyone() -> None:
    assert rules.grant("clipboard", OURS, PORT)
    assert not rules.grant("clipboard", "https://example.com", PORT)
    assert not rules.grant("clipboard", "http://127.0.0.1:1", PORT)
    for other in ("notifications", "geolocation", "camera", "other"):
        assert not rules.grant(other, OURS, PORT)


# ===== pages, named without the token =====


def test_a_page_is_named_without_its_token_and_given_the_running_servers() -> None:
    assert rules.page_of(f"{OURS}/workspace#token=secret") == "/workspace"
    assert rules.page_of(f"{OURS}/workspace#token=secret&grid=3") == "/workspace#grid=3"
    assert rules.page_of("/workbench?kind=notebook") == "/workbench?kind=notebook"
    for bad in ("https://example.com/workspace", "//evil.example/x", "", "x" * 5000, 3):
        with pytest.raises(rules.ShellError):
            rules.page_of(bad)  # type: ignore[arg-type]
    full = rules.address_of("/workspace#grid=3", 8800, "tok")
    assert full == "http://127.0.0.1:8800/workspace#token=tok&grid=3"
    # The same shape as the browser launch's (server/lifecycle.py's page_address).
    from swissarmybench.server.lifecycle import page_address

    assert rules.address_of("/workspace", 8800, "tok") == page_address({"port": 8800, "token": "tok"})
    assert rules.page_for("blades") == "/catalog"
    with pytest.raises(rules.ShellError):
        rules.page_for("settings")


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        (f"{OURS}/workspace#token=x", "home"),
        (f"{OURS}/", "home"),
        (f"{OURS}/g/7", "home"),
        (f"{OURS}/workbench?kind=notebook", "workbench"),
        (f"{OURS}/catalog", "catalog"),
        (f"{OURS}/workspace?panel=steps", "home-panel-steps"),
        (f"{OURS}/g/2?panel=connsql", "home-panel-connsql"),
        ("/workbench", "workbench"),
        (f"{OURS}/{'x' * 90}", "other"),
    ],
)
def test_a_windows_kind_is_what_its_place_is_remembered_by(url: str, kind: str) -> None:
    assert rules.kind_of(url) == kind


def test_the_home_page_reuses_the_window_named_sab_home_and_a_page_reuses_its_window() -> None:
    windows = [
        rules.Open(1, "", f"{OURS}/workbench"),
        rules.Open(2, rules.HOME_WINDOW, f"{OURS}/g/4"),
        rules.Open(3, "", f"{OURS}/catalog"),
    ]
    # The home page: the window named sab-home (the pages find it by that name), loaded: it shows a grid.
    assert rules.target(f"{OURS}/workspace#token=t", windows) == (2, True)
    # The same page already open: raised, not loaded again; loaded when the fragment says more.
    assert rules.target(f"{OURS}/catalog#token=t", windows) == (3, False)
    assert rules.target(f"{OURS}/workbench#token=t&doc=2", windows) == (1, True)
    # Nothing like it: a new window.
    assert rules.target(f"{OURS}/workbench?kind=script#token=t", windows) == (None, True)
    # The home window showing the home page already: raised only.
    home = [rules.Open(5, rules.HOME_WINDOW, f"{OURS}/workspace")]
    assert rules.target(f"{OURS}/workspace#token=t", home) == (5, False)
    assert rules.target(f"{OURS}/workspace#token=t&grid=2", home) == (5, True)


# ===== the remembered places =====


def test_a_remembered_place_is_used_while_enough_of_it_is_on_a_screen() -> None:
    screen = rules.Rect(0, 0, 1920, 1040)
    saved = rules.Saved(rules.Rect(100, 80, 1000, 700), maximized=True)
    assert rules.place("home", saved, None, [screen]) == saved
    # A second screen gone (the window was on it): the default size, centred on the first.
    gone = rules.Saved(rules.Rect(2500, 100, 900, 600))
    placed = rules.place("home", gone, None, [screen])
    assert placed.rect == rules.Rect((1920 - 1360) // 2, (1040 - 860) // 2, 1360, 860)
    assert not placed.maximized
    # Larger than the screen it is on: made to fit.
    big = rules.Saved(rules.Rect(0, 0, 4000, 3000))
    assert rules.place("home", big, None, [screen]).rect == rules.Rect(0, 0, 1920, 1040)
    # The page asked for a size (window.open's width and height): used when nothing is remembered.
    asked = rules.place("home-panel-steps", None, (460, 820), [screen])
    assert (asked.rect.w, asked.rect.h) == (460, 820)
    # Too small to use: the least size; cascaded by the windows open.
    tiny = rules.place("x", None, (10, 10), [screen], open_count=2)
    assert (tiny.rect.w, tiny.rect.h) == (rules.MIN_WIDTH, rules.MIN_HEIGHT)
    assert tiny.rect.x == (1920 - rules.MIN_WIDTH) // 2 + 2 * rules.CASCADE
    assert rules.place("x", None, None, []).rect.w == rules.DEFAULT_SIZE[0]


def test_windows_json_is_read_loosely_and_written_sorted() -> None:
    data: Any = {
        "home": {"x": 1, "y": 2, "w": 900, "h": 600, "maximized": True},
        "bad kind!": {"x": 1, "y": 2, "w": 900, "h": 600},
        "catalog": {"x": "1", "y": 2, "w": 900, "h": 600},
        "tiny": {"x": 1, "y": 2, "w": 10, "h": 10},
        "workbench": [],
    }
    assert list(rules.read_saved(data)) == ["home"]
    assert rules.read_saved(None) == {} and rules.read_saved([1]) == {}
    after = rules.remembered(data, "catalog", rules.Saved(rules.Rect(5, 6, 800, 500)))
    assert list(after) == ["catalog", "home"]
    assert after["catalog"] == {"x": 5, "y": 6, "w": 800, "h": 500, "maximized": False}
    text = rules.windows_text(after)
    assert text == rules.windows_text(json.loads(text))  # the same text for the same places
    many = {f"k{i}": {"x": 0, "y": 0, "w": 400, "h": 300} for i in range(rules.MAX_KINDS + 5)}
    kept = rules.remembered(many, "newest", rules.Saved(rules.Rect(0, 0, 400, 300)))
    assert len(kept) == rules.MAX_KINDS and "newest" in kept


# ===== the command line, the record and the messages =====


def test_the_shells_command_line_never_carries_the_token() -> None:
    assert rules.shell_command("py") == ["py", "-m", "swissarmybench_desktop"]
    assert rules.shell_command("py", f"{OURS}/workspace#token=secret&grid=2", tray=False) == [
        "py",
        "-m",
        "swissarmybench_desktop",
        "/workspace#grid=2",
    ]
    assert rules.shell_command("py", tray=True) == ["py", "-m", "swissarmybench_desktop", "--tray"]
    assert rules.read_arguments([]) == (False, None)
    assert rules.read_arguments(["--tray"]) == (True, None)
    assert rules.read_arguments(["/workbench"]) == (False, "/workbench")
    for bad in (["--port", "1"], ["/a", "/b"], ["https://example.com"]):
        with pytest.raises(rules.ShellError):
            rules.read_arguments(bad)


def test_the_record_and_the_messages() -> None:
    said = rules.record(42, 5000, "k" * 43)
    assert said["pid"] == 42 and rules.read_record(said) == (42, 5000, "k" * 43)
    assert rules.read_record({"pid": 42}) is None  # the pystray tray's record
    assert rules.read_record({"pid": 42, "shell": {"port": 0, "key": "k" * 43}}) is None
    assert rules.read_record({"pid": 42, "shell": {"port": 5000, "key": "short"}}) is None
    key = "k" * 43
    line = rules.message(key, {"open": f"{OURS}/workspace#token=secret"})
    assert rules.read_message(line, key) == {"open": "/workspace"}
    assert rules.read_message(rules.message(key, {"status": True}), key) == {"status": True}
    for bad in (
        rules.message("x" * 43, {"status": True}),  # another key
        rules.message(key, {"quit": True}),
        b"not json\n",
        b"[1]\n",
        b"x" * (rules.MAX_MESSAGE + 1),
        rules.message(key, {"open": "https://example.com"}),
    ):
        with pytest.raises(rules.ShellError):
            rules.read_message(bad, key)


def test_download_and_pdf_names() -> None:
    assert rules.download_name("orders.csv") == "orders.csv"
    assert rules.download_name("../../etc/passwd") == "passwd"
    assert rules.download_name("a\\b\\c:d.xlsx") == "cd.xlsx"
    assert rules.download_name("") == "download" and rules.download_name("\x00\x01") == "download"
    assert rules.pdf_name("Q3 sales dashboard") == "Q3 sales dashboard.pdf"
    assert rules.pdf_name("") == "Swiss Army Bench.pdf"
    assert rules.pdf_name("report.pdf") == "report.pdf"


# ===== the channel (real sockets on 127.0.0.1) =====


def test_the_channel_answers_only_its_key_on_127_0_0_1() -> None:
    heard: list[dict[str, Any]] = []
    key = channel.new_key()

    def answer(said: dict[str, Any]) -> dict[str, Any]:
        heard.append(said)
        return {"ok": True}

    listener = channel.Listener(key, answer)
    try:
        assert listener._server.server_address[0] == "127.0.0.1"
        assert channel.ask(listener.port, key, {"open": "/workbench"}) == {"ok": True}
        assert heard == [{"open": "/workbench"}]
        assert "error" in channel.ask(listener.port, "w" * 43, {"open": "/workbench"})
        assert "error" in channel.ask(listener.port, key, {"open": "https://example.com"})
        assert len(heard) == 1
    finally:
        listener.close()
    with pytest.raises(OSError):
        channel.ask(listener.port, key, {"status": True}, timeout=1.0)


def test_the_record_file_is_the_owners_only_and_removed_only_by_its_shell(tmp_path: Path) -> None:
    record = channel.RecordFile(tmp_path / "tray.json")
    record.write(rules.record(42, 5000, "k" * 43))
    assert record.shell() == (42, 5000, "k" * 43)
    if sys.platform != "win32":
        assert (record.path.stat().st_mode & 0o777) == 0o600
    record.remove(41)
    assert record.path.is_file()
    record.remove(42)
    assert not record.path.exists()
    state = channel.JsonState(tmp_path / "desktop" / "windows.json")
    state.write_text("{}\n")
    stamp = state.path.stat().st_mtime_ns
    state.write_text("{}\n")  # the same text: not written again
    assert state.path.stat().st_mtime_ns == stamp and state.read() == {}


# ===== the launcher: open a page, start the shell =====


def test_open_page_sends_to_the_running_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    info = tmp_path / "server.json"
    heard: list[dict[str, Any]] = []
    key = channel.new_key()

    def answer(said: dict[str, Any]) -> dict[str, Any]:
        heard.append(said)
        return {"ok": True} if "open" in said else {"running": True, "windows": [{"kind": "home"}]}

    listener = channel.Listener(key, answer)
    monkeypatch.setattr(launch, "can_run", lambda: True)
    started: list[Any] = []
    monkeypatch.setattr(launch, "start_shell", lambda page, tray=False: started.append(page))
    try:
        channel.RecordFile(tmp_path / "tray.json").write(rules.record(os.getpid(), listener.port, key))
        assert launch.open_page(f"{OURS}/workspace#token=secret&grid=2", info)
        assert heard == [{"open": "/workspace#grid=2"}] and started == []
        assert launch.status(info) == {"running": True, "windows": [{"kind": "home"}]}
    finally:
        listener.close()


def test_open_page_starts_the_shell_when_none_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    info = tmp_path / "server.json"
    monkeypatch.setattr(launch, "can_run", lambda: True)
    started: list[Any] = []
    monkeypatch.setattr(launch, "start_shell", lambda page, tray=False: started.append(page))
    assert launch.open_page(f"{OURS}/workspace#token=secret", info)
    assert started == ["/workspace"]
    # A stale record (its process gone): started all the same.
    channel.RecordFile(tmp_path / "tray.json").write(rules.record(2**22 + 7, 1, "k" * 43))
    assert launch.open_page(f"{OURS}/catalog#token=secret", info)
    assert started == ["/workspace", "/catalog"]
    assert launch.status(info) == {"running": False, "windows": []}


def test_open_page_says_no_where_the_shell_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launch, "can_run", lambda: False)
    assert not launch.open_page(f"{OURS}/workspace#token=s", tmp_path / "server.json")
    monkeypatch.setattr(launch, "can_run", lambda: True)
    assert not launch.open_page("https://example.com", tmp_path / "server.json")


def test_a_pystray_tray_holding_the_lock_gives_way_to_the_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the lock held by the old tray (tray.json: its pid, no shell), open_page starts the shell, which
    ends that tray and takes its place (one icon)."""
    from swissarmybench.server.lifecycle import InstanceLock

    info = tmp_path / "server.json"
    held = InstanceLock(tmp_path / "tray.json")
    try:
        (tmp_path / "tray.json").write_text(json.dumps({"pid": os.getppid()}), encoding="utf-8")
        monkeypatch.setattr(launch, "can_run", lambda: True)
        started: list[Any] = []
        monkeypatch.setattr(launch, "start_shell", lambda page, tray=False: started.append(page))
        assert launch.old_tray(info) == os.getppid()
        assert launch.open_page(f"{OURS}/workspace#token=s", info)
        assert started == ["/workspace"]
    finally:
        held.release()


def test_has_display() -> None:
    assert launch.has_display("win32", {}) and launch.has_display("darwin", {})
    assert not launch.has_display("linux", {})
    assert launch.has_display("linux", {"DISPLAY": ":0"})
    assert launch.has_display("linux", {"WAYLAND_DISPLAY": "wayland-0"})
    assert launch.has_display("linux", {"QT_QPA_PLATFORM": "offscreen"})


def test_the_listener_answers_while_a_handler_runs() -> None:
    """Each message on its own thread: a slow open does not hold up a status."""
    release = threading.Event()
    key = channel.new_key()

    def handle(said: dict[str, Any]) -> dict[str, Any]:
        if "open" in said:
            release.wait(5)
        return {"ok": True}

    listener = channel.Listener(key, handle)
    try:
        slow = threading.Thread(target=channel.ask, args=(listener.port, key, {"open": "/workspace"}))
        slow.start()
        assert channel.ask(listener.port, key, {"status": True}, timeout=3.0) == {"ok": True}
        release.set()
        slow.join(5)
    finally:
        listener.close()


def test_a_windows_title_never_shows_an_address() -> None:
    assert rules.window_title("Workbench") == "Workbench"
    assert rules.window_title(f"{OURS}/workspace#token=secret") == "Swiss Army Bench"
    assert (
        rules.window_title("") == "Swiss Army Bench"
        and rules.window_title("about:blank") == "Swiss Army Bench"
    )
