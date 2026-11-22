"""The server's one refusal shape (design principle 9.5, the owner 2026-11-18: "Errors should be presented to
users in one uniform way as much as possible"): every route's refusal is {"error", "where"?, "fixes"?,
"details"?}, with the fields pages and the agent already read kept beside them. Made-up names only."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pyarrow as pa
import pytest

from swissarmybench.cli.api import refusal_words
from swissarmybench.domain import refusals
from swissarmybench.services.workspace import Conflict, NotFound, Refused
from tests.conftest import AGENT, AUTH, grid_id, make_client, push

SHAPE = {"error", "where", "fixes", "details"}


def _shaped(response: object, status: int) -> dict[str, object]:
    assert response.status_code == status, response.text  # type: ignore[attr-defined]
    assert response.headers["content-type"].startswith("application/json")  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert isinstance(body["error"], str) and body["error"].strip()
    assert "\n" not in body["error"]
    return body  # type: ignore[no-any-return]


# ===== the shape's rules =====


def test_a_long_message_keeps_one_sentence_and_folds_the_rest_into_details() -> None:
    said = refusals.shape("Could not connect to the server.\nTraceback (most recent call last):\n  ...")
    assert said == {
        "error": "Could not connect to the server.",
        "details": "Could not connect to the server.\nTraceback (most recent call last):\n  ...",
    }
    assert refusals.shape("  ") == {"error": "Something went wrong."}
    assert refusals.shape("No grid g9.", where="g9") == {"error": "No grid g9.", "where": "g9"}


def test_a_run_that_failed_says_its_sentence_and_keeps_the_source_s_words() -> None:
    said = "Shop failed: OperationalError: unable to open database file (line 5)"
    assert refusals.run_failure(said) == (
        "Shop failed: unable to open database file.",
        "OperationalError: unable to open database file (line 5)",
    )
    assert refusals.run_failure("SHOP_HOST is not set on this computer.") == (
        "SHOP_HOST is not set on this computer.",
        None,
    )


def test_fixes_name_an_action_the_page_knows() -> None:
    assert refusals.set_variable("SHOP_HOST") == {
        "label": "Set it",
        "action": "set_variable",
        "name": "SHOP_HOST",
        "command": "variables_set",
        "page": "variables",
    }
    assert refusals.sign_in("Warehouse")["action"] == "sign_in"
    assert refusals.open_settings("Warehouse")["label"] == "Open its settings"
    assert refusals.install()["action"] == "install"
    with pytest.raises(ValueError, match="action is one of"):
        refusals.fix("Do it", "dance")


def test_an_outcome_may_say_where_and_how_to_fix_and_a_plain_one_says_its_words() -> None:
    assert refusals.of(NotFound("No grid g9.")) == {"error": "No grid g9."}
    said = refusals.of(
        Refused("Warehouse needs a sign-in.", where="Warehouse", fixes=[refusals.sign_in("Warehouse")])
    )
    assert said["where"] == "Warehouse" and said["fixes"][0]["action"] == "sign_in"
    assert refusals.of(Conflict("Taken.", details="the driver said: 23505"))["details"] == (
        "the driver said: 23505"
    )


def test_the_agent_reads_a_plain_refusal_as_its_words_and_a_fuller_one_as_json() -> None:
    assert refusal_words(b'{"error":"No grid g9."}') == "No grid g9."
    fuller = b'{"error":"A is not set.","fixes":[{"label":"Set it"}]}'
    assert refusal_words(fuller) == fuller.decode()
    assert refusal_words(b"plain words") == "plain words"


# ===== representative routes =====


def test_a_missing_grid_a_bad_body_and_bad_sql_answer_the_shape(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        missing = _shaped(client.get("/grids/nope/rows", headers=AUTH), 404)
        assert set(missing) <= SHAPE
        nowhere = _shaped(client.get("/no/such/address", headers=AUTH), 404)
        assert nowhere == {"error": "No such address.", "where": "/no/such/address"}
        bad = _shaped(
            client.post(
                "/connections/test",
                content=b"{not json",
                headers=AUTH | {"Content-Type": "application/json"},
            ),
            400,
        )
        assert bad["error"] == "The request body is not valid JSON."
        grid = grid_id(push(client, "orders", pa.table({"amount": [1, 2]})))
        said = _shaped(client.post(f"/grids/{grid}/sql", json={"sql": "SELEC 1"}, headers=AUTH), 400)
        assert set(said) <= SHAPE


def test_the_guard_refuses_in_the_shape(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        refused = _shaped(client.get("/connections"), 401)
        assert set(refused) == {"error"}


def test_a_missing_variable_brings_set_it_with_its_action(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        grid = grid_id(push(client, "orders", pa.table({"amount": [1, 2]})))
        sql = {"sql": "SELECT ${MADE_UP_SHOP_FILE}"}
        said = _shaped(client.post(f"/grids/{grid}/sql", json=sql, headers=AUTH), 422)
        assert said["missing_variables"] == ["MADE_UP_SHOP_FILE"]  # kept beside the shape
        fix = said["fixes"][0]  # type: ignore[index]
        assert fix["action"] == "set_variable" and fix["name"] == "MADE_UP_SHOP_FILE"


def test_a_refused_connection_test_says_what_where_and_the_source_s_own_words(tmp_path: Path) -> None:
    database = tmp_path / "shop.db"
    sqlite3.connect(database).close()
    draft = {
        "name": "Warehouse",
        "kind": "sql",
        "dialect": "sqlite",
        "template": "sqlite",
        "code": (
            "import sqlite3\n"
            'raise ConnectionRefusedError("Connection refused by db.example.test:5432.\\n'
            'Is the server running and accepting connections?")\n'
            f'conn = sqlite3.connect(r"{database}")'
        ),
    }
    with make_client(tmp_path) as client:
        for headers in (AUTH, AGENT):  # the agent reads the same answer
            said = _shaped(client.post("/connections/test", json=draft, headers=headers), 422)
            assert "Connection refused" in str(said["error"])
            assert said["where"] == "Warehouse"
            assert "Is the server running" in str(said.get("details", "")) + str(said["error"])


def test_every_route_is_guarded_once_at_the_app() -> None:
    """The simplicity pass (2026-11-21): no route module writes its own guard; the app puts every async
    handler under one (http.guarded), so a crash in any route answers the one shape."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from swissarmybench.server.http import guarded

    async def crashes(request: Request) -> Response:
        raise RuntimeError("made-up failure")

    app = Starlette(routes=guarded([Route("/boom", crashes, methods=["POST"])]))
    body = _shaped(TestClient(app).post("/boom"), 500)
    assert "made-up failure" in str(body)
