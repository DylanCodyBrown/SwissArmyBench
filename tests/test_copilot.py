"""The GitHub Copilot extension through its door, with GitHub's Copilot Language Server stood in for by
tests/copilot_standin.py (a stdio server speaking the README's messages; the real one needs a Copilot plan
and is never run here). Made-up code and a made-up account only."""

from __future__ import annotations

import json
import os
import stat
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench import extensions
from swissarmybench.cli import api as cli_api
from swissarmybench.cli import commands as base_commands
from tests.conftest import AGENT, AUTH, make_client

STANDIN = Path(__file__).resolve().parent / "copilot_standin.py"


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def sent(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def methods(log: Path) -> list[str]:
    return [m.get("method", "") for m in sent(log)]


def wait_for(check: Any, seconds: float = 10.0) -> Any:
    end = time.time() + seconds
    while time.time() < end:
        got = check()
        if got:
            return got
        time.sleep(0.05)
    raise AssertionError("never happened")


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    return {"log": tmp_path / "standin.log", "state": tmp_path / "standin-account.json"}


@pytest.fixture
def switched_on(monkeypatch: pytest.MonkeyPatch, files: dict[str, Path]) -> None:
    monkeypatch.setenv(extensions.VARIABLE, "copilot")
    monkeypatch.setenv("SWISSARMYBENCH_COPILOT_STANDIN", str(STANDIN))
    monkeypatch.setenv("COPILOT_STANDIN_LOG", str(files["log"]))
    monkeypatch.setenv("COPILOT_STANDIN_STATE", str(files["state"]))


@pytest.fixture
def client(tmp_path: Path, switched_on: None) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        yield test_client


def sign_in(client: TestClient) -> None:
    panel = ok(client.post("/copilot/panel", json={"action": "sign_in"}, headers=AUTH))
    assert panel["code"]["text"] == "MADE-UP1" and panel["code"]["link"] == "https://github.com/login/device"
    ok(client.post("/copilot/panel", json={"action": "finish"}, headers=AUTH))
    wait_for(lambda: ok(client.get("/copilot", headers=AUTH))["account"]["state"] == "signed_in")


SCRIPT = {"key": "tab-7", "name": "load.py", "kind": "script", "language": "python", "text": "import pan"}


def complete(
    client: TestClient, document: dict[str, Any], line: int, character: int, request: str = "r1"
) -> Any:
    body = {"request": request, "document": document, "position": {"line": line, "character": character}}
    return ok(client.post("/copilot/complete", json=body, headers=AUTH))


# ===== off and on =====


def test_off_nothing_of_it_is_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(extensions.VARIABLE, raising=False)
    with make_client(tmp_path) as client:
        refused = client.get("/copilot", headers=AUTH)
        assert refused.status_code == 404 and refused.json()["extension"] == "copilot"
        mode = ok(client.get("/app/mode", headers=AUTH))["mode"]
        assert mode["inline_completion"] == []
        listed = {e["id"]: e for e in ok(client.get("/extensions", headers=AUTH))["extensions"]}
        assert listed["copilot"]["status"] == "available" and "panel" not in listed["copilot"]
        assert all(not n.startswith("copilot_") for n in base_commands.REGISTRY)


def test_on_its_inline_completion_and_panel_are_declared(client: TestClient) -> None:
    for mode in ok(client.get("/app/modes", headers=AUTH))["modes"]:
        provider = mode["inline_completion"][0]
        assert provider["name"] == "GitHub Copilot" and provider["complete"] == "/copilot/complete"
        assert provider["languages"] == ["python", "sql"] and provider["event"] == "/copilot/event"
    listed = {e["id"]: e for e in ok(client.get("/extensions", headers=AUTH))["extensions"]}
    assert listed["copilot"]["status"] == "installed" and listed["copilot"]["panel"] == "/copilot/panel"


def test_before_sign_in_nothing_is_sent_and_it_is_off(client: TestClient, files: dict[str, Path]) -> None:
    status = ok(client.get("/copilot", headers=AUTH))
    assert status["on"] is False and status["ready"] is False and status["words"] == "off"
    assert status["telemetry"] == "off"
    assert complete(client, SCRIPT, 0, 10) == {"items": [], "off": "off"}
    assert not files["log"].exists()  # the server was never even started
    panel = ok(client.get("/copilot/panel", headers=AUTH))
    assert [a["id"] for a in panel["actions"]] == ["sign_in"]
    assert panel["switches"] == [{"id": "on", "label": "On", "on": False, "disabled": False}]


# ===== signing in: the device flow, the user's own =====


def test_sign_in_is_the_device_flow_and_turns_it_on(client: TestClient, files: dict[str, Path]) -> None:
    sign_in(client)
    status = ok(client.get("/copilot", headers=AUTH))
    assert status["on"] is True and status["ready"] is True
    assert status["account"] == {"state": "signed_in", "user": "made-up-octocat"}
    said = sent(files["log"])
    first = said[0]
    assert first["method"] == "initialize"
    assert first["params"]["initializationOptions"]["editorInfo"]["name"] == "Swiss Army Bench"
    assert [m.get("method") for m in said[1:3]] == ["initialized", "workspace/didChangeConfiguration"]
    assert said[2]["params"]["settings"]["telemetry"]["telemetryLevel"] == "off"
    # The server asked for its settings and was told telemetry is off too.
    asked = [m for m in said if "method" not in m and m.get("result") == [{"telemetryLevel": "off"}]]
    assert asked
    commands = [m["params"]["command"] for m in said if m.get("method") == "workspace/executeCommand"]
    assert commands == ["github.copilot.finishDeviceFlow"]
    # The device page was the page's to open: the client said it was, opening nothing itself.
    assert any(m.get("result") == {"success": True} for m in said if "method" not in m)
    panel = ok(client.get("/copilot/panel", headers=AUTH))
    assert panel["lines"][0] == {"text": "Signed in as made-up-octocat.", "tone": "ok"}
    assert [a["id"] for a in panel["actions"]] == ["sign_out"]


def test_signing_in_and_out_are_the_users_own(client: TestClient) -> None:
    for path in ("/copilot/sign-in", "/copilot/sign-in/finish", "/copilot/sign-out"):
        assert client.post(path, headers=AGENT).status_code == 403
    for action in ("sign_in", "finish", "sign_out", "cancel_sign_in"):
        assert client.post("/copilot/panel", json={"action": action}, headers=AGENT).status_code == 403
    ok(client.post("/copilot/sign-in", headers=AUTH))
    # The agent sees the panel, but not the code.
    assert ok(client.get("/copilot/panel", headers=AGENT))["code"] is None
    assert ok(client.get("/copilot/panel", headers=AUTH))["code"]["text"] == "MADE-UP1"


def test_no_plan_is_said_plainly(client: TestClient, files: dict[str, Path]) -> None:
    files["state"].write_text(json.dumps({"user": "made-up-free", "plan": False}))
    ok(client.post("/copilot/toggle", json={"on": True}, headers=AUTH))
    status = ok(client.get("/copilot", headers=AUTH))
    assert status["account"]["state"] == "no_subscription" and status["words"] == "no plan"
    assert "no GitHub Copilot plan" in ok(client.get("/copilot/panel", headers=AUTH))["lines"][0]["text"]
    assert complete(client, SCRIPT, 0, 10)["off"] == "no plan"


def test_sign_out(client: TestClient, files: dict[str, Path]) -> None:
    sign_in(client)
    ok(client.post("/copilot/sign-out", headers=AUTH))
    assert "signOut" in methods(files["log"])
    status = ok(client.get("/copilot", headers=AUTH))
    assert status["account"]["state"] == "not_signed_in" and not status["ready"]


# ===== completions =====


def test_a_script_is_opened_changed_and_completed(client: TestClient, files: dict[str, Path]) -> None:
    sign_in(client)
    got = complete(client, SCRIPT, 0, 10)
    assert [i["text"] for i in got["items"]] == ["das as pd", "das as pd  # second"]
    assert got["items"][0]["range"] == {
        "start": {"line": 0, "character": 10},
        "end": {"line": 0, "character": 10},
    }
    assert "command" not in got["items"][0]  # the accept command stays on the server's side
    after = dict(SCRIPT, text="def total_by_region(orders):")
    got = complete(client, after, 0, 28, "r2")
    assert got["items"][0]["text"].startswith("\n    return orders.groupby")
    said = sent(files["log"])
    order = [m.get("method") for m in said]
    assert order.count("textDocument/didOpen") == 1 and order.count("textDocument/didChange") == 1
    assert (
        order.index("textDocument/didOpen")
        < order.index("textDocument/didFocus")
        < order.index("textDocument/inlineCompletion")
    )
    inline = next(m for m in said if m.get("method") == "textDocument/inlineCompletion")["params"]
    assert inline["textDocument"] == {"uri": "file:///swissarmybench/tab-7/load.py", "version": 1}
    assert inline["formattingOptions"] == {"tabSize": 4, "insertSpaces": True}
    assert inline["context"] == {"triggerKind": 2}


def test_a_notebook_cell_with_its_other_code_cells(client: TestClient, files: dict[str, Path]) -> None:
    sign_in(client)
    notebook = {
        "key": "nb-1",
        "name": "sales.ipynb",
        "kind": "notebook",
        "cells": [
            {"id": 1, "text": "import duckdb\norders = duckdb.sql('SELECT 1')", "language": "python"},
            {"id": 3, "text": "SELECT region,", "language": "sql"},
        ],
        "cell": 3,
    }
    got = complete(client, notebook, 0, 14)
    assert got["items"][0]["text"] == " sum(amount) AS total FROM orders GROUP BY region"
    opened = next(m for m in sent(files["log"]) if m.get("method") == "notebookDocument/didOpen")["params"]
    assert next(c["text"] for c in opened["cellTextDocuments"]).startswith("import duckdb")
    # Only the cells' text: no outputs, no rows, no values.
    assert set(opened["cellTextDocuments"][0]) == {"uri", "languageId", "version", "text"}


def test_shown_accepted_and_partly_accepted_are_told_back(client: TestClient, files: dict[str, Path]) -> None:
    sign_in(client)
    item = complete(client, SCRIPT, 0, 10)["items"][0]
    assert ok(client.post("/copilot/event", json={"id": item["id"], "kind": "shown"}, headers=AUTH))["sent"]
    ok(client.post("/copilot/event", json={"id": item["id"], "kind": "partial", "length": 3}, headers=AUTH))
    ok(client.post("/copilot/event", json={"id": item["id"], "kind": "accepted"}, headers=AUTH))
    said = sent(files["log"])
    shown = next(m for m in said if m.get("method") == "textDocument/didShowCompletion")["params"]
    assert shown["item"]["insertText"] == "das as pd"
    partial = next(m for m in said if m.get("method") == "textDocument/didPartiallyAcceptCompletion")[
        "params"
    ]
    assert partial["acceptedLength"] == 3
    accepted = [m["params"] for m in said if m.get("method") == "workspace/executeCommand"][-1]
    assert accepted["command"] == "github.copilot.didAcceptCompletionItem"
    assert accepted["arguments"][0].startswith("made-up-")
    assert not ok(client.post("/copilot/event", json={"id": "nope", "kind": "shown"}, headers=AUTH))["sent"]


def test_a_completion_cancelled_on_the_way(
    client: TestClient, files: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPILOT_STANDIN_DELAY", "1.5")
    sign_in(client)
    answers: list[Any] = []
    asking = threading.Thread(target=lambda: answers.append(complete(client, SCRIPT, 0, 10, "slow")))
    asking.start()
    wait_for(lambda: "textDocument/inlineCompletion" in methods(files["log"]))
    assert ok(client.post("/copilot/cancel", json={"request": "slow"}, headers=AUTH))["cancelled"]
    asking.join(10)
    assert answers == [{"items": [], "cancelled": True}]
    assert "$/cancelRequest" in methods(files["log"])


def test_the_off_switch_stops_everything(client: TestClient, files: dict[str, Path]) -> None:
    sign_in(client)
    complete(client, SCRIPT, 0, 10)
    ok(client.post("/copilot/toggle", json={"on": False}, headers=AGENT))  # the agent may switch it
    status = ok(client.get("/copilot", headers=AUTH))
    assert not status["on"] and not status["running"] and status["words"] == "off"
    before = len(sent(files["log"]))
    assert complete(client, dict(SCRIPT, text="import pand"), 0, 11)["off"] == "off"
    assert len(sent(files["log"])) == before
    inline = ok(client.get("/copilot/inline", headers=AUTH))
    assert inline == {"name": "GitHub Copilot", "on": False, "ready": False, "words": "off"}


def test_a_private_project_sends_nothing(client: TestClient, files: dict[str, Path], tmp_path: Path) -> None:
    sign_in(client)
    ok(client.post("/project/new", json={"path": str(tmp_path / "work" / "ledger")}, headers=AUTH))
    complete(client, SCRIPT, 0, 10)  # open before: it is closed once the project is private
    state = ok(client.post("/project/private", json={"on": True}, headers=AUTH))
    assert state["project"]["private"] is True
    manifest = json.loads((tmp_path / "work" / "ledger" / ".sab" / "project.json").read_text())
    assert manifest["private"] is True
    before = methods(files["log"])
    other = {
        "key": "tab-9",
        "name": "secret_plan.py",
        "kind": "script",
        "language": "python",
        "text": "x = 1",
    }
    assert complete(client, other, 0, 5)["off"] == "private"
    after = methods(files["log"])[len(before) :]
    assert "textDocument/didOpen" not in after and "textDocument/inlineCompletion" not in after
    assert after == ["textDocument/didClose"]
    assert not any("secret_plan" in json.dumps(m) for m in sent(files["log"]))
    assert ok(client.get("/copilot", headers=AUTH))["private"] is True
    assert ok(client.get("/copilot/inline", headers=AUTH))["words"] == "private"
    # Not private again: completions come back.
    ok(client.post("/project/private", json={"on": False}, headers=AUTH))
    assert complete(client, other, 0, 0)["items"]


def test_the_agents_private_switch_waits_for_allow(client: TestClient, tmp_path: Path) -> None:
    ok(client.post("/project/new", json={"path": str(tmp_path / "work" / "ledger")}, headers=AUTH))

    def answer() -> None:
        pending = wait_for(lambda: ok(client.get("/agent/approvals", headers=AUTH))["pending"])
        client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": False}, headers=AUTH)

    thread = threading.Thread(target=answer)
    thread.start()
    assert client.post("/project/private", json={"on": True}, headers=AGENT).status_code == 403
    thread.join(10)
    assert ok(client.get("/project", headers=AUTH))["project"]["private"] is False


# ===== the install and Node.js =====


def fake_tool(folder: Path, name: str, script: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(f"#!{sys.executable}\n{script}")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="the fake tools are POSIX scripts")
def test_install_puts_the_pinned_package_in_the_state_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    record = tmp_path / "npm-args.json"
    fake_tool(bin_dir, "node", "print('v22.11.0')\n")
    fake_tool(
        bin_dir,
        "npm",
        "import json, os, sys\n"
        "if sys.argv[1:] == ['--version']: print('10.9.0'); raise SystemExit\n"
        f"json.dump(sys.argv[1:], open({str(record)!r}, 'w'))\n"
        "prefix = sys.argv[sys.argv.index('--prefix') + 1]\n"
        "dist = os.path.join(prefix, 'node_modules', '@github', 'copilot-language-server', 'dist')\n"
        "os.makedirs(dist, exist_ok=True); open(os.path.join(dist, 'language-server.js'), 'w').write('')\n",
    )
    monkeypatch.setenv(extensions.VARIABLE, "copilot")
    monkeypatch.delenv("SWISSARMYBENCH_COPILOT_STANDIN", raising=False)
    monkeypatch.setenv("PATH", str(bin_dir))
    with make_client(tmp_path) as client:
        panel = ok(client.get("/copilot/panel", headers=AUTH))
        assert [a["id"] for a in panel["actions"]] == ["install"] and panel["switches"][0]["disabled"]

        # The agent's install waits for Allow (declined here): nothing ran.
        def answer() -> None:
            pending = wait_for(lambda: ok(client.get("/agent/approvals", headers=AUTH))["pending"])
            client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": False}, headers=AUTH)

        thread = threading.Thread(target=answer)
        thread.start()
        assert client.post("/copilot/install", headers=AGENT).status_code == 403
        thread.join(10)
        assert not record.exists()
        ok(client.post("/copilot/panel", json={"action": "install"}, headers=AUTH))
        argv = json.loads(record.read_text())
        assert argv[:3] == ["install", "--prefix", str(tmp_path / "state" / "copilot")]
        assert argv[-1] == "@github/copilot-language-server@1.572.0"
        assert ok(client.get("/copilot", headers=AUTH))["server_installed"] is True


def test_node_missing_is_the_missing_tool_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv(extensions.VARIABLE, "copilot")
    monkeypatch.delenv("SWISSARMYBENCH_COPILOT_STANDIN", raising=False)
    monkeypatch.setenv("PATH", str(empty))
    with make_client(tmp_path) as client:
        refused = client.post("/copilot/install", headers=AUTH)
        assert refused.status_code == 422, refused.text
        missing = refused.json()["missing"]
        assert (
            missing["packages"] == ["Node.js"] and missing["tool"] == "node" and missing["python"] == "tool"
        )
        assert missing["feature"] == "Installing GitHub's Copilot Language Server"
        panel = ok(client.get("/copilot/panel", headers=AUTH))
        assert any("Node.js 20.8 or later" in line["text"] for line in panel["lines"])


# ===== secrets and the agent =====


def test_no_token_in_any_answer_or_file(client: TestClient, files: dict[str, Path], tmp_path: Path) -> None:
    sign_in(client)
    complete(client, SCRIPT, 0, 10)
    answers = json.dumps(
        [ok(client.get(p, headers=AUTH)) for p in ("/copilot", "/copilot/panel", "/copilot/inline")]
    )
    kept = (tmp_path / "state" / "copilot.json").read_text()
    assert json.loads(kept) == {"on": True, "login": "made-up-octocat"}
    audit = (tmp_path / "state" / "audit.log").read_text()
    assert "copilot_sign_in" in audit
    for text in (answers, kept, audit):
        assert "MADE-UP1" not in text and "token" not in text.lower()
        assert "made-up log" not in text  # the server's own logs are dropped
        assert "import pan" not in text  # nor a document's text


def test_the_agents_commands(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    before_registry = dict(base_commands.REGISTRY)
    before_areas = base_commands.AREAS
    try:
        from swissarmybench_copilot import extension

        base_commands.REGISTRY.update(extension.commands())
        base_commands.AREAS = (*base_commands.AREAS, *extension.AREAS)
        assert {n for n in base_commands.REGISTRY if n.startswith("copilot_")} == {
            "copilot_status",
            "copilot_toggle",
            "copilot_install",
        }
        assert base_commands.area_of("copilot_toggle") == "copilot"

        def through_client(
            method: str, path: str, body: Any = None, params: Any = None, timeout: float = 0
        ) -> Any:
            answer = client.request(method, path, json=body, params=params, headers=AGENT)
            if answer.status_code >= 400:
                raise cli_api.CommandError(answer.text)
            return answer.json()

        monkeypatch.setattr(cli_api, "call", through_client)
        status = json.loads(base_commands.execute("copilot_status"))
        assert status["status"]["on"] is False and status["panel"]["code"] is None
        toggled = json.loads(base_commands.execute("copilot_toggle", {"on": True}))
        assert toggled["on"] is True
        assert "project_private" in base_commands.REGISTRY
    finally:
        base_commands.REGISTRY.clear()
        base_commands.REGISTRY.update(before_registry)
        base_commands.AREAS = before_areas


def test_stopping_the_server_ends_the_language_server(
    tmp_path: Path, switched_on: None, files: dict[str, Path]
) -> None:
    with make_client(tmp_path) as client:
        sign_in(client)
    said = methods(files["log"])
    assert said[-2:] == ["shutdown", "exit"]
    assert os.environ["SWISSARMYBENCH_COPILOT_STANDIN"] == str(STANDIN)
