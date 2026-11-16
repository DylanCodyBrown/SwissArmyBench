"""Server lifecycle and the push client against a real server process.

Each test points SWISSARMYBENCH_INFO and SWISSARMYBENCH_STATE at a temp folder, so nothing here
touches the real ~/.swissarmybench.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from swissarmybench.client import push_client
from swissarmybench.server import lifecycle


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    variables = {
        "SWISSARMYBENCH_INFO": str(tmp_path / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp_path / "state"),
    }
    for key, value in variables.items():
        monkeypatch.setenv(key, value)
    yield os.environ | variables
    # Stop anything a test started.
    lifecycle.request_stop(Path(variables["SWISSARMYBENCH_INFO"]))
    time.sleep(0.5)


def cli(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "swissarmybench.server", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def start_background(env: dict[str, str], *args: str) -> subprocess.Popen[str]:
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "swissarmybench.server", *args],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    info_path = Path(env["SWISSARMYBENCH_INFO"])
    for _ in range(100):
        if lifecycle.running_server(info_path):
            return process
        time.sleep(0.1)
    process.kill()
    raise AssertionError(process.stdout.read() if process.stdout else "server did not start")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_explicit_busy_port_is_a_plain_error(tmp_path: Path) -> None:
    holder = lifecycle.open_listener(0, tmp_path / "last")
    port = holder.getsockname()[1]
    try:
        with pytest.raises(lifecycle.PortError, match="in use"):
            lifecycle.open_listener(port, tmp_path / "last")
        with pytest.raises(lifecycle.PortError, match="out of range"):
            lifecycle.open_listener(80, tmp_path / "last")
    finally:
        holder.close()


def test_exclusive_bind_blocks_a_second_socket_even_with_reuse(tmp_path: Path) -> None:
    holder = lifecycle.open_listener(0, tmp_path / "last")
    port = holder.getsockname()[1]
    intruder = socket.socket()
    intruder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        with pytest.raises(OSError):
            intruder.bind(("127.0.0.1", port))
    finally:
        intruder.close()
        holder.close()


def test_the_listener_turns_off_nagle_for_every_connection(tmp_path: Path) -> None:
    """asyncio turns Nagle off only on sockets whose proto is IPPROTO_TCP; a socket made with
    socket(AF_INET, SOCK_STREAM) has proto 0, so the server's replies on a kept-alive connection
    (the page fetching grid windows) waited ~40 ms each for the client's delayed ACK."""
    listener = lifecycle.open_listener(0, tmp_path / "last")
    try:
        assert listener.proto == socket.IPPROTO_TCP
        assert listener.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) != 0
    finally:
        listener.close()


def test_kept_alive_requests_answer_without_a_delayed_ack_stall(tmp_path: Path) -> None:
    import http.client
    import statistics
    import threading

    import uvicorn

    from swissarmybench.server.app import create_app
    from swissarmybench.settings import Settings

    listener = lifecycle.open_listener(0, tmp_path / "last")
    port = listener.getsockname()[1]
    settings = Settings(state_dir=tmp_path / "state", export_dir=tmp_path / "exports")
    server = uvicorn.Server(
        uvicorn.Config(create_app(port, "t", settings, audit_log=False), log_level="warning")
    )
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        took: list[float] = []
        for _ in range(12):
            started = time.perf_counter()
            conn.request("GET", "/health", headers={"Authorization": "Bearer t"})
            response = conn.getresponse()
            response.read()
            assert response.status == 200
            took.append(time.perf_counter() - started)
        conn.close()
        # With the stall every request took 40-44 ms; without it about 1 ms.
        assert statistics.median(took) < 0.025, took
    finally:
        server.should_exit = True
        thread.join(10)


def test_last_port_is_reused_when_free_and_skipped_when_busy(tmp_path: Path) -> None:
    last = tmp_path / "last"
    port = free_port()
    lifecycle.remember_port(last, port)
    first = lifecycle.open_listener(None, last)
    assert first.getsockname()[1] == port
    second = lifecycle.open_listener(None, last)  # busy now: falls back to any free port
    assert second.getsockname()[1] != port
    first.close()
    second.close()


def test_stale_file_from_a_crash_is_not_a_running_server(tmp_path: Path) -> None:
    path = tmp_path / "server.json"
    path.write_text(json.dumps({"port": free_port(), "token": "t", "pid": 999_999_999}))
    assert lifecycle.running_server(path) is None
    assert not lifecycle.process_alive(999_999_999)
    assert lifecycle.process_alive(os.getpid())


def test_start_status_second_start_and_stop(env: dict[str, str]) -> None:
    port = free_port()
    process = start_background(env, "--port", str(port))
    info = json.loads(Path(env["SWISSARMYBENCH_INFO"]).read_text())
    # On Windows the venv's python.exe is a launcher, so compare with the server's own pid.
    assert info["port"] == port and info["pid"] == _get(info, "/health")["pid"]
    assert f"127.0.0.1:{port}" in cli(env, "status").stdout
    second = cli(env, "--port", str(free_port()))
    assert second.returncode == 1 and "already running" in second.stderr
    assert "Stopped" in cli(env, "stop").stdout
    process.wait(timeout=20)
    assert not Path(env["SWISSARMYBENCH_INFO"]).exists()
    assert cli(env, "status").returncode == 1
    # The next start reuses the remembered port.
    again = start_background(env)
    assert json.loads(Path(env["SWISSARMYBENCH_INFO"]).read_text())["port"] == port
    cli(env, "stop")
    again.wait(timeout=20)


def test_a_crash_leaves_a_stale_file_that_the_next_start_replaces(env: dict[str, str]) -> None:
    process = start_background(env)
    crashed = json.loads(Path(env["SWISSARMYBENCH_INFO"]).read_text())
    os.kill(crashed["pid"], 9)  # a hard kill: TerminateProcess on Windows, no cleanup runs
    process.wait(timeout=20)
    for _ in range(50):
        if not lifecycle.process_alive(crashed["pid"]):
            break
        time.sleep(0.1)
    assert Path(env["SWISSARMYBENCH_INFO"]).exists()
    assert lifecycle.running_server(Path(env["SWISSARMYBENCH_INFO"])) is None
    replacement = start_background(env)
    info = json.loads(Path(env["SWISSARMYBENCH_INFO"]).read_text())
    assert info["pid"] != crashed["pid"] and info["pid"] == _get(info, "/health")["pid"]
    cli(env, "stop")
    replacement.wait(timeout=20)


def test_push_names_the_dataset_after_the_variable_and_keeps_types(env: dict[str, str]) -> None:
    process = start_background(env)
    try:
        quarterly_sales = pd.DataFrame({"day": [date(2026, 1, 1), date(2026, 2, 1)], "amount": [1.5, None]})
        url = push_client.push(quarterly_sales)
        assert "/g/" in url and "#token=" in url
        info = push_client.ensure_server()
        # Started by hand here, so the status bar in VS Code can tell it from its own server.
        assert info["started_by"] == "cli" and info["executable"] == sys.executable
        listing = _get(info, "/datasets")
        assert [d["name"] for d in listing["datasets"]] == ["quarterly_sales"]
        grid = listing["datasets"][0]["grids"][0]
        described = _get(info, f"/grids/{grid}")
        assert described["title"] == "quarterly_sales"
        assert [c["type"] for c in described["columns"]] == ["DATE", "DOUBLE"]
        assert push_client.push(quarterly_sales, name="explicit").count("/g/") == 1
        with pytest.raises(ValueError, match="not allowed"):
            push_client.push(quarterly_sales, name="bad name")
    finally:
        cli(env, "stop")
        process.wait(timeout=20)


def test_a_push_never_starts_a_server(env: dict[str, str]) -> None:
    """VS Code starts the server; a push with none running says so and starts nothing."""
    with pytest.raises(push_client.ServerNotRunningError, match="VS Code"):
        push_client.push(pd.DataFrame({"a": [1, 2]}), name="auto")
    time.sleep(0.5)
    assert lifecycle.running_server(Path(env["SWISSARMYBENCH_INFO"])) is None


def test_only_one_server_holds_the_instance_lock(tmp_path: Path) -> None:
    first = lifecycle.InstanceLock(tmp_path / "server.json")
    with pytest.raises(lifecycle.AlreadyStartingError):
        lifecycle.InstanceLock(tmp_path / "server.json")
    lifecycle.InstanceLock(tmp_path / "other.json").release()  # another connection file: its own lock
    first.release()
    lifecycle.InstanceLock(tmp_path / "server.json").release()  # free again once the first is gone


def test_two_servers_started_at_once_leave_one_running(env: dict[str, str]) -> None:
    """VS Code restoring two windows starts the extension in both, and both start a server at the
    same moment, before either has written the connection file. Exactly one keeps running."""
    command = [sys.executable, "-m", "swissarmybench.server"]
    racers = [
        subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)  # noqa: S603
        for _ in range(2)
    ]
    try:
        info_path = Path(env["SWISSARMYBENCH_INFO"])
        for _ in range(150):
            if lifecycle.running_server(info_path) and any(r.poll() is not None for r in racers):
                break
            time.sleep(0.1)
        still_running = [r for r in racers if r.poll() is None]
        assert len(still_running) == 1
        loser = next(r for r in racers if r.poll() is not None)
        assert loser.returncode == 1
        info = lifecycle.running_server(info_path)
        assert info is not None and info["pid"] == _get(info, "/health")["pid"]
    finally:
        cli(env, "stop")
        for racer in racers:
            racer.wait(timeout=20)


def test_variable_name_lookup() -> None:
    import inspect

    orders = object()
    frame = inspect.currentframe()
    assert push_client.caller_variable_name(orders, frame) == "orders"
    alias = orders  # two names for one object: ambiguous
    assert push_client.caller_variable_name(alias, frame) is None


def _get(info: dict[str, object], path: str) -> dict:  # type: ignore[type-arg]
    import urllib.request

    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}",
        headers={"Authorization": f"Bearer {info['token']}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        return json.loads(response.read())  # type: ignore[no-any-return]


def test_start_opens_the_page_with_its_token_and_open_finds_a_running_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner's first run on Windows printed an address with no token and opened nothing: the page
    could not be reached. The address now carries the token in its fragment, and `open` reads it back."""
    from swissarmybench.server import __main__ as command

    assert (
        command.page_address({"port": 58064, "token": "abc"}) == "http://127.0.0.1:58064/workspace#token=abc"
    )
    opened: list[str] = []

    def browse(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("webbrowser.open", browse)
    monkeypatch.setattr(command, "running_server", lambda path: None)
    assert command.open_page(tmp_path / "server.json") is False and opened == []
    monkeypatch.setattr(command, "running_server", lambda path: {"port": 58064, "token": "abc"})
    assert command.open_page(tmp_path / "server.json") is True
    assert opened == ["http://127.0.0.1:58064/workspace#token=abc"]


def test_the_opened_address_is_a_page_the_server_serves_without_the_token(tmp_path: Path) -> None:
    """0.0.2 opened "/", which answers 401 (only the page shells are served without the token): the page
    the browser opens must be one of them, its token in the fragment for the page to read."""
    from urllib.parse import urlsplit

    from swissarmybench.server import __main__ as command
    from tests.conftest import make_client

    address = urlsplit(command.page_address({"port": 8765, "token": "test-token"}))
    with make_client(tmp_path) as client:
        page = client.get(address.path)
        assert page.status_code == 200 and "<html" in page.text.lower()
    assert address.fragment == "token=test-token"


def test_the_bare_address_goes_to_the_apps_page_without_a_token() -> None:
    """0.0.2 opened http://127.0.0.1:<port>/#token=...; the bare address had no page and answered 401.
    It now sends the browser on to /workspace (which keeps the fragment), and holds no data itself."""
    from starlette.testclient import TestClient

    from swissarmybench.server.app import create_app
    from swissarmybench.settings import Settings

    client = TestClient(create_app(8000, "t", Settings()), base_url="http://127.0.0.1:8000")
    answer = client.get("/", follow_redirects=False)
    assert answer.status_code == 307 and answer.headers["location"] == "/workspace"
