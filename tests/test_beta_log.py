"""The beta log: what it holds is enough to fix a problem and never the user's data.

A made-up secret, a cell value, a SQL literal and a path go through every kind of event (a server
error, a refusal, a slow request, a process, a page error, a note) and none of them is in the file.
Then: aliases, rotation, beta mode off (nothing written), on again without a restart, the switch kept
across a restart, SWISSARMYBENCH_BETA winning, and the export zip's contents.
"""

from __future__ import annotations

import base64
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters.beta_log import BetaFiles
from swissarmybench.domain import beta_log as rules
from swissarmybench.services.sql import SqlBox

from .conftest import AUTH, grid_id, make_client, push

# Made-up values that must never reach the log.
SECRET = "Zq9-hunter2-SECRET"
VALUE = "Globex-Acme-77"
LITERAL = "east-region-xyz"
PATH = "/home/alice/clients/acme_q3.csv"
FORBIDDEN = (SECRET, VALUE, LITERAL, PATH, "alice", "acme_q3")
NAUGHTY = f"password={SECRET} value '{VALUE}' sql WHERE region = '{LITERAL}' file {PATH} amount 9876543.21"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def log_text(state: Path) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in sorted((state / "logs").glob("*.jsonl")))


def events(client: TestClient, **query: Any) -> list[dict[str, Any]]:
    answer = client.get("/beta/log", params=query, headers=AUTH)
    assert answer.status_code == 200, answer.text
    return list(answer.json()["events"])


def note(client: TestClient, text: str = "The button does nothing", **extra: Any) -> Any:
    body = {
        "text": text,
        "page": "grid",
        "window": "main",
        "element": {"tag": "button", "role": "button", "name": "Filter…", "path": "div.ribbon > button.btn"},
        "actions": ["steps.add", "table.filter"],
    } | extra
    return client.post("/beta/notes", json=body, headers=AUTH)


@pytest.fixture
def opened(tmp_path: Path) -> Any:
    with make_client(tmp_path, beta_slow_seconds=0.0) as client:
        table = pa.table({"client": [VALUE, "Initech"], "region": [LITERAL, "west"]})
        client.grid = grid_id(push(client, "clients", table))  # type: ignore[attr-defined]
        yield client, tmp_path / "state"


# ===== the rules =====


def test_redaction_hides_secrets_values_sql_and_paths() -> None:
    aliases = rules.Aliases()
    aliases.learn({"table": ["clients"], "column": ["balance", "region"]})
    message = (
        f"Binder Error: column \"balance\" of clients: value '{VALUE}' {NAUGHTY}\n"  # noqa: S608 (made-up text, never run)
        f"LINE 1: SELECT * FROM clients WHERE region = '{LITERAL}'\n          ^\n"
        "token=abc123def456 Bearer sk0123456789abcdef and ann@example.com C:\\Users\\alice\\x.xlsx"
    )
    shown = rules.redact(message, aliases, home="/home/alice", secrets=[SECRET])
    for word in (*FORBIDDEN, "abc123def456", "sk0123456789abcdef", "ann@example.com", "9876543", "SELECT"):
        assert word not in shown
    assert '"col#1"' in shown and "table#1" in shown  # a quoted name that is an alias stays readable
    assert "~/" in shown and ".csv" in shown and ".xlsx" in shown  # the home folder is ~, the extension kept
    assert rules.redact("line 12 of 300 rows") == "line 12 of 300 rows"  # short numbers stay


def test_aliases_are_stable_and_whole_words() -> None:
    aliases = rules.Aliases()
    aliases.learn({"table": ["orders", "Order Book"], "column": ["id", "amount"]})
    aliases.learn({"table": ["orders", "items"], "column": ["amount"]})
    assert aliases.replace("ORDERS.amount in Order Book; reorders, items") == (
        "table#1.col#2 in table#2; reorders, table#3"
    )


def test_server_frames_keep_files_and_functions_only() -> None:
    shown = rules.frames(
        [
            ("/home/alice/.venv/lib/python3.12/site-packages/starlette/routing.py", 74, "app"),
            ("/home/alice/code/src/swissarmybench/services/grids.py", 120, "rows"),
            ("/usr/lib/python3.12/asyncio/events.py", 88, "_run"),
            ("/home/alice/acme_q3_blade.py", 4, "load"),
        ]
    )
    assert shown == [
        "starlette/routing.py:74 in app",
        "swissarmybench/services/grids.py:120 in rows",
        "python/asyncio/events.py:88 in _run",
        "\u2039\u2026\u203a.py:4 in load",
    ]


def test_page_frames_keep_the_apps_own_files() -> None:
    stack = (
        "TypeError: x\n    at draw (http://127.0.0.1:8123/static/build/main.js?token=SECRET:1:2345)\n"
        "    at http://127.0.0.1:8123/static/build/workbench.js:3:4\n    at evil (https://elsewhere/a.js:1:1)\n"
        f"    {VALUE}"
    )
    assert rules.page_frames(stack) == [
        "draw @ /static/build/main.js:1:2345",
        "? @ /static/build/workbench.js:3:4",
        "evil @ \u2039\u2026\u203a:1:1",
    ]


def test_the_rate_cap_counts_what_it_drops() -> None:
    cap = rules.RateCap(per_minute=3)
    assert [cap.allow(0.0) for _ in range(5)] == [True, True, True, False, False]
    assert cap.take_dropped() == 2 and cap.allow(61.0)


# ===== every kind of event, through the app =====


def test_no_kind_of_event_lets_the_users_data_through(opened: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, state = opened
    grid = client.grid
    ctx = client.app.state.ctx

    # A server error (an exception nobody expected), its message full of data.
    async def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(NAUGHTY)

    monkeypatch.setattr(SqlBox, "run", broken)
    assert (
        client.post(f"/grids/{grid}/sql", json={"sql": f"SELECT '{LITERAL}'"}, headers=AUTH).status_code
        == 500
    )
    monkeypatch.undo()
    # A refusal (a 4xx), its message naming the user's literal and table.
    bad = f"SELECT * FROM clients WHERE region = '{LITERAL}' AND nope = '{SECRET}'"  # noqa: S608 (made-up SQL the app refuses)
    assert client.post(f"/grids/{grid}/sql", json={"sql": bad}, headers=AUTH).status_code == 400
    # A slow request (the mark is 0 seconds here): the URL names the table, the log its route's pattern.
    # (a file that is not there: refused, its message naming the path)
    client.post("/datasets/clients/load", json={"path": PATH}, headers=AUTH)
    # A process that ends badly, with words that hold data.
    ctx.beta.process("kernel", "crash", 137, 1.5, NAUGHTY)
    # A page's error and its stack.
    page = {
        "message": NAUGHTY,
        "stack": f"Error\n    at f (http://127.0.0.1:1/static/build/main.js?x={SECRET}:1:2)",
    }
    assert client.post("/beta/page-errors", json=page, headers=AUTH).status_code == 200
    # A note whose element description (worked out by the page) carries data.
    element = {"name": NAUGHTY, "text": VALUE, "path": f"div.cell[col-id=clients] {PATH}", "role": "gridcell"}
    assert note(client, element=element, actions=["steps.add", NAUGHTY]).status_code == 200
    button = {
        "name": NAUGHTY,
        "text": "Filter…",
        "path": f"div.ribbon > button.btn[title={PATH}]",
        "role": "button",
    }
    assert note(client, element=button).status_code == 200

    text = log_text(state)
    kinds = {e["kind"] for e in events(client)}
    assert {"start", "error", "refused", "slow", "process", "page", "note"} <= kinds
    for word in FORBIDDEN:
        assert word not in text, f"{word!r} reached the log"
    assert "SELECT" not in text and "9876543" not in text
    slow = next(e for e in events(client, kind="slow") if e["route"].endswith("/load"))
    assert slow["route"] == "/datasets/{name}/load" and "ms" in slow
    error = events(client, kind="error")[-1]
    assert error["type"] == "RuntimeError" and any("test_beta_log.py" not in f for f in error["frames"])
    assert any(f.startswith("swissarmybench/server/routes_grids.py:") for f in error["frames"])
    # The note's id list carries that error, so the note and the stack can be read together.
    assert error["id"] in events(client, kind="note")[-1]["server_errors"]


def test_a_notes_own_words_are_kept_and_a_picture_only_when_ticked(opened: Any) -> None:
    client, state = opened
    picture = "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert note(client, "Not ticked", picture=picture).json()["picture"] is False
    assert note(client, "Ticked", picture=picture, attach_picture=True).json()["picture"] is True
    notes = client.get("/beta/notes", headers=AUTH).json()["notes"]
    assert [n["text"] for n in notes] == ["Not ticked", "Ticked"]
    assert "picture" not in notes[0] and notes[1]["picture"].startswith("pictures/")
    assert notes[1]["element"]["path"] == "div.ribbon > button.btn" and notes[1]["actions"] == [
        "steps.add",
        "table.filter",
    ]
    assert len(list((state / "logs" / "pictures").glob("*.png"))) == 1
    assert note(client, " ").status_code == 400


# ===== beta mode: one switch, kept, the variable wins =====


def test_beta_mode_off_writes_nothing_and_on_again_works_at_once(tmp_path: Path) -> None:
    with make_client(tmp_path, beta_slow_seconds=0.0) as client:
        state = tmp_path / "state"
        assert client.put("/beta", json={"on": False}, headers=AUTH).json()["on"] is False
        before = log_text(state)
        client.get("/datasets", headers=AUTH)
        client.post("/beta/page-errors", json={"message": "boom"}, headers=AUTH)
        assert note(client).status_code == 403
        client.app.state.ctx.beta.process("kernel", "crash", 1)  # type: ignore[attr-defined]
        assert log_text(state) == before
        # The files stay until Clear the log, so they can still be exported.
        assert client.get("/beta", headers=AUTH).json()["files"] == 1
        assert client.put("/beta", json={"on": True}, headers=AUTH).json()["on"] is True
        assert note(client).status_code == 200
        assert events(client, kind="note")
        assert client.delete("/beta/log", headers=AUTH).json()["removed"] >= 1
        assert events(client, kind="note") == []  # (the clearing request itself is the slow one now)


def test_beta_mode_survives_a_restart(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        client.put("/beta", json={"on": False}, headers=AUTH)
    assert json.loads((tmp_path / "state" / "beta.json").read_text()) == {"on": False}
    with make_client(tmp_path) as client:
        state = client.get("/beta", headers=AUTH).json()
        assert state["on"] is False and state["set_by"] == "settings"
    # The second start wrote nothing: the one start event is the first server's.
    assert log_text(tmp_path / "state").count('"kind":"start"') == 1


@pytest.mark.parametrize(("value", "on"), [("0", False), ("1", True)])
def test_the_environment_variable_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str, on: bool
) -> None:
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "beta.json").write_text(json.dumps({"on": not on}))
    monkeypatch.setenv("SWISSARMYBENCH_BETA", value)
    with make_client(tmp_path) as client:
        state = client.get("/beta", headers=AUTH).json()
        assert state["on"] is on and state["set_by"] == "environment"
        refused = client.put("/beta", json={"on": not on}, headers=AUTH)
        assert refused.status_code == 403 and "SWISSARMYBENCH_BETA" in refused.text


def test_the_default_is_one_constant() -> None:
    assert rules.BETA_MODE_DEFAULT is True  # the 0.0.1 beta; the release after it flips this


# ===== the files =====


def test_rotation_keeps_the_cap_and_the_days(tmp_path: Path) -> None:
    clock = [time.time()]
    files = BetaFiles(tmp_path / "logs", max_bytes=64 * 1024, days=7, now=lambda: clock[0])
    for i in range(1500):  # (under the queue's size: a full queue drops events rather than wait)
        files.write({"kind": "slow", "i": i, "pad": "x" * 120})
    files.flush()
    parts = sorted((tmp_path / "logs").glob("*.jsonl"))
    assert len(parts) > 1 and sum(p.stat().st_size for p in parts) <= 64 * 1024 + files.part_bytes
    assert files.read()[-1]["i"] == 1499  # the newest are kept, the oldest went
    # Eight days on, a new day's first write removes the old parts.
    clock[0] += 8 * 86400
    for part in parts:
        os.utime(part, (clock[0] - 8 * 86400, clock[0] - 8 * 86400))
    files.write({"kind": "start"})
    files.flush()
    assert [e["kind"] for e in files.read()] == ["start"]


def test_a_folder_of_none_writes_nothing(tmp_path: Path) -> None:
    files = BetaFiles(None, 1 << 20, 7)
    assert files.write({"kind": "start"}) is False and files.read() == []


def test_the_export_zip_holds_the_log_the_notes_and_the_users_pictures(opened: Any) -> None:
    client, state = opened
    picture = "data:image/png;base64," + base64.b64encode(PNG).decode()
    note(client, "With a picture", picture=picture, attach_picture=True)
    target = state.parent / "beta-log.zip"
    made = client.post("/beta/export", json={"path": str(target)}, headers=AUTH).json()
    assert made["notes"] == 1 and made["pictures"] == 1
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        assert "README.txt" in names and "notes.json" in names
        assert any(n.startswith("logs/beta-") for n in names) and any(
            n.startswith("pictures/") for n in names
        )
        assert json.loads(archive.read("notes.json"))[0]["text"] == "With a picture"
    # The agent's export leaves the pictures (which show the user's data) out.
    agent = client.post(
        "/beta/export", json={"path": str(state.parent / "agent.zip")}, headers=AUTH | {"X-Actor": "agent"}
    ).json()
    assert agent["pictures"] == 0
    with zipfile.ZipFile(state.parent / "agent.zip") as archive:
        assert not any(n.startswith("pictures/") for n in archive.namelist())
    assert (
        client.post("/beta/export", json={"path": str(state.parent / "x.txt")}, headers=AUTH).status_code
        == 400
    )


def test_filters_by_kind_and_time(opened: Any) -> None:
    client, _ = opened
    note(client)
    assert {e["kind"] for e in events(client, kind="note")} == {"note"}
    assert events(client, kind="note,start", since="1h", limit=1)[0]["kind"] == "note"
    assert client.get("/beta/log", params={"kind": "nonsense"}, headers=AUTH).status_code == 400
    assert client.get("/beta/log", params={"since": "soon"}, headers=AUTH).status_code == 400
