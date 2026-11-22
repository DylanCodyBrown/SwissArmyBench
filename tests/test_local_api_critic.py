"""The local sandbox API builder made to follow the app's own good designs (the critic's fixes, 2026-11-21):

  one definition  an endpoint's body fields and its made-up request are the server's (domain/local_api.py),
                  read by Try it, the Canvas's Event mapping, Payload shapes and the agent (no page's own)
  errors          a refusal through `call` carries its sentence and API.py's line (the error note's parts);
                  the request log says a refusal's words and line and counts rows only for a list; a path no
                  endpoint answers is the API's own 404, never the framework's bare text
  reliability     New endpoint from a table over a date column starts (its import is written); what API.py
                  prints is read (an unread pipe would stop the endpoint) and shown as Output
  words           "a whole number", one "line" in a mock's refusal, an export's warning said in its answer

Made-up data only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swissarmybench.adapters import adapter
from swissarmybench.domain import api_scaffold as scaffold
from swissarmybench.domain import api_targets as targets
from swissarmybench.domain import local_api as rules
from swissarmybench.server import api_runtime
from tests.test_local_api import API_PY, _ask, live  # noqa: F401

VISITS = (
    "visit_id,patient,clinic,visit_date,seen_at,fee\n"
    "1,Ada Fenn,North,2026-01-05,2026-01-05 09:30:00,120.5\n"
    "2,Bo Larch,South,2026-01-06,2026-01-06 14:00:00,80.0\n"
)

MORE = """

@endpoint("GET", "/broken")
def broken() -> dict:
    return {"n": undefined_name}


@endpoint("GET", "/views")
def views() -> list:
    db = connection("Sandbox")
    return records(db.query("SELECT table_name FROM information_schema.tables"))


@endpoint("GET", "/loud")
def loud(lines: int = 3) -> dict:
    for n in range(lines):
        print("made-up line", n, "x" * 100)
    return {"printed": lines}
"""


# ===== one definition =====


def test_an_endpoints_fields_and_made_up_request_come_from_its_model() -> None:
    api = rules.parse(API_PY)
    by = {e.name: e for e in api.endpoints}
    assert rules.body_fields(by["add_order"], api.models) == {
        "order_id": {"type": "int", "required": True},
        "region": {"type": "str", "required": True},
        "amount": {"type": "float", "required": True},
    }
    assert rules.body_fields(by["orders_in"], api.models) is None
    assert rules.made_up(by["add_order"], api.models) == {
        "path": {},
        "query": {},
        "body": {"order_id": 101, "region": "made-up region", "amount": 12.5},
    }
    # A query parameter starts from its default; a path's from its type.
    assert rules.made_up(by["orders_in"], api.models) == {
        "path": {"region": "made-up region"},
        "query": {"limit": 100},
        "body": None,
    }
    assert rules.made_up(by["one_order"], api.models)["path"] == {"order_id": 101}
    # An optional filter starts empty (the sweep, 2026-11-22: a Summary's ?status= started as "made-up
    # status", so Try it's first Send answered 0 rows and looked broken); one with no default is made up.
    filtered = rules.parse(
        'from sab_api import endpoint\n\n\n@endpoint("GET", "/orders/summary")\n'
        "def summary(year: int, status: str | None = None, limit: int = 1000) -> list[dict]:\n"
        "    return []\n"
    ).endpoints[0]
    assert rules.made_up(filtered, {})["query"] == {"year": 3, "status": None, "limit": 1000}
    # The made-up body fits the OpenAPI schema the same model gives.
    schema = rules.openapi(api)["components"]["schemas"]["Order"]
    assert list(schema["properties"]) == list(rules.made_up(by["add_order"], api.models)["body"])


def test_an_optional_or_listed_body_is_still_its_model() -> None:
    text = API_PY.replace("def add_order(order: Order)", "def add_order(order: list[Order] | None = None)")
    api = rules.parse(text)
    add = next(e for e in api.endpoints if e.name == "add_order")
    assert list(rules.body_fields(add, api.models) or {}) == ["order_id", "region", "amount"]


def test_payload_shapes_check_an_events_call_against_the_endpoint() -> None:
    api = rules.parse(API_PY)

    def use(action: dict[str, object]) -> dict[str, object]:
        return {"canvas": "front.canvas.json", "page": "Home", "instance": "w1", "widget": "de_record_form",
                "event": "saved", "action": {"do": "call"} | action}  # fmt: skip

    whole, mapped, wrong, gone, path = rules.shapes(
        api,
        [
            use({"endpoint": "POST /orders", "body": "values"}),
            use({"endpoint": "POST /orders",
                 "body": {"order_id": "values.id", "region": "values.region", "amount": "values.amount"}}),
            use({"endpoint": "POST /orders", "body": {"order_id": "values.id", "colour": "values.colour"}}),
            use({"endpoint": "POST /nope", "body": "values"}),
            use({"endpoint": "GET /orders/one/{order_id}", "body": "values"}),
        ],
    )  # fmt: skip
    assert whole["problems"] == [] and whole["event"] == "saved"
    assert whole["answers"]["body"] == {"order_id": "int", "region": "str", "amount": "float"}
    assert mapped["problems"] == []
    assert wrong["problems"] == [
        "add_order's body has no field colour.",
        "add_order's body needs region: saved does not send it.",
    ]
    assert gone["problems"] == ["API.py has no endpoint POST /nope."]
    assert path["problems"] == [
        "one_order takes no body: saved sends one.",
        "saved gives no order_id for the path.",
    ]


# ===== New endpoint from a table =====


def test_a_crud_set_with_a_date_column_brings_its_import() -> None:
    columns = [{"name": "visit_id", "type": "BIGINT"}, {"name": "visit_date", "type": "DATE"},
               {"name": "seen_at", "type": "TIMESTAMP"}]  # fmt: skip
    block = scaffold.crud("visits", columns, scaffold.Source("duckdb", "Sandbox"))
    needs = scaffold.imports_missing(rules.scaffold("clinic"), block)
    assert needs == "from datetime import date, datetime  # noqa: E402\n"
    compile(rules.scaffold("clinic") + needs + block, "API.py", "exec")
    # Only what is used, and never twice.
    plain = scaffold.crud("notes", [{"name": "id", "type": "BIGINT"}], scaffold.Source("duckdb", "Sandbox"))
    assert scaffold.imports_missing(rules.scaffold("clinic"), plain) == ""
    assert scaffold.imports_missing(rules.scaffold("clinic") + needs + block, block) == ""
    # Written among API.py's own imports (no lint note), every other line as it was.
    text, rest = scaffold.with_imports(rules.scaffold("clinic"), needs)
    assert rest == "" and text.count("\n") == rules.scaffold("clinic").count("\n") + 1
    at = text.split("\n").index("from datetime import date, datetime")
    assert text.split("\n")[at - 1].startswith("from sab_api import") and "noqa" not in text.split("\n")[at]
    compile(text + block, "API.py", "exec")
    # A file with no import of its own: the lines go before the set, as they are.
    assert scaffold.with_imports("# notes\n", needs) == ("# notes\n", needs)
    assert scaffold.with_imports("x = 1\n", "") == ("x = 1\n", "")


def test_a_table_with_dates_scaffolds_runs_and_answers(live: int, tmp_path: Path) -> None:  # noqa: F811
    port = live
    folder = tmp_path / "clinic"
    _ask(port, "POST", "/project/new", {"path": str(folder)})
    csv = tmp_path / "visits.csv"
    csv.write_text(VISITS, encoding="utf-8")
    _ask(port, "POST", "/sandbox/tables", {"from": "file", "path": str(csv)})
    made = _ask(port, "POST", "/local-api/scaffold", {"table": "visits", "key": "visit_id"})
    assert "list_visits" in made["added"]
    assert "from datetime import date, datetime" in (folder / "API.py").read_text(encoding="utf-8")
    ran = _ask(port, "POST", "/local-api/run", {})
    assert ran["running"] and not ran.get("failed"), ran.get("failed")
    one = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/visits/1"})
    assert one["status"] == 200 and one["body"]["visit_date"] == "2026-01-05"
    # The state's contract: the one definition Try it and the agent read.
    create = next(e for e in ran["endpoints"] if e["name"] == "create_visits")
    assert create["fields"]["visit_date"] == {"type": "date", "required": False}
    assert create["try"]["body"]["visit_date"] == "2026-01-15" and create["try"]["body"]["visit_id"] == 101
    assert [t["id"] for t in ran["targets"]] == ["fastapi", "azure_functions", "aws_lambda"]
    assert ran["targets"][1]["label"] == "Azure Functions (Linux, Python)"
    sent = _ask(
        port, "POST", "/local-api/call", {"method": "POST", "path": "/visits", "body": create["try"]["body"]}
    )
    assert sent["status"] == 201, sent
    _ask(port, "POST", "/local-api/stop", {})


# ===== errors, the log, what it prints =====


def test_a_refusal_says_its_sentence_and_api_pys_line(live: int, tmp_path: Path) -> None:  # noqa: F811
    port = live
    folder = tmp_path / "shop"
    _ask(port, "POST", "/project/new", {"path": str(folder)})
    csv = tmp_path / "orders.csv"
    csv.write_text("order_id,region,amount\n1,West,10.5\n", encoding="utf-8")
    _ask(port, "POST", "/sandbox/tables", {"from": "file", "path": str(csv)})
    text = API_PY + MORE
    (folder / "API.py").write_text(text, encoding="utf-8")
    assert _ask(port, "POST", "/local-api/run", {})["running"]
    lines = text.split("\n")
    # The endpoint's own failure: its words, and the line of API.py it failed on.
    broken = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/broken"})
    assert broken["status"] == 500 and broken["error"] == "NameError: name 'undefined_name' is not defined"
    assert broken["line"] == lines.index('    return {"n": undefined_name}') + 1
    assert broken["where"] == f"API.py line {broken['line']}"
    assert broken["body"] == {"error": broken["error"]}  # the API's own answer is as it was
    # The sandbox's refusal, through the adapter: one "line", said once (in `where`).
    views = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/views"})
    query_line = '    return records(db.query("SELECT table_name FROM information_schema.tables"))'
    assert views["line"] == lines.index(query_line) + 1
    assert (
        views["error"] == "AdapterError: The sandbox's mock has no system views (information_schema.tables)."
    )
    # The API's own refusals: a sentence, no line.
    missing = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/orders/one/99"})
    assert missing["error"] == "No order 99." and "line" not in missing
    typed = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/orders/one/abc"})
    assert typed["status"] == 422 and typed["error"] == "order_id is not a whole number: 'abc'."
    # A path no endpoint answers: the API's own 404, in the log too.
    nowhere = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/nowhere"})
    assert nowhere["status"] == 404 and nowhere["body"] == {"error": "No endpoint answers GET /nowhere."}
    other = _ask(port, "POST", "/local-api/call", {"method": "DELETE", "path": "/broken"})
    assert other["status"] == 405 and other["error"] == "That path takes another method."
    fine = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/orders/West"})
    assert fine["status"] == 200 and "error" not in fine
    log = _ask(port, "GET", "/local-api/log")["log"]
    by = {r["path"]: r for r in reversed(log)}  # each path's first request
    assert by["/broken"]["line"] == broken["line"] and by["/broken"]["error"].startswith("NameError")
    assert by["/broken"]["rows"] is None  # an error is not a row
    assert by["/nowhere"]["status"] == 404 and by["/orders/West"]["rows"] == 1
    assert "error" not in by["/orders/West"]
    _ask(port, "POST", "/local-api/stop", {})


def test_what_api_py_prints_is_read_and_shown(live: int, tmp_path: Path) -> None:  # noqa: F811
    port = live
    folder = tmp_path / "shop"
    _ask(port, "POST", "/project/new", {"path": str(folder)})
    (folder / "API.py").write_text(API_PY + MORE, encoding="utf-8")
    assert _ask(port, "POST", "/local-api/run", {})["running"]
    # Far more than a pipe holds (64 KB): unread, the endpoint would wait for ever.
    done = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/loud", "query": {"lines": 3000}})
    assert done["status"] == 200 and done["body"] == {"printed": 3000}
    again = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/loud"})
    assert again["status"] == 200
    said = []
    for _ in range(40):
        said = _ask(port, "GET", "/local-api/log")["output"]
        if said and said[-1].startswith("made-up line 2 "):
            break
        import time

        time.sleep(0.1)
    assert said[-1].startswith("made-up line 2 ") and len(said) <= 200
    _ask(port, "POST", "/local-api/stop", {})


def test_the_words() -> None:
    with pytest.raises(api_runtime.ApiError, match="paid is not true or false: 'maybe'"):
        api_runtime._convert("maybe", bool, "paid")
    with pytest.raises(api_runtime.ApiError, match=r"fee is not a number: 'lots'"):
        api_runtime._convert("lots", float, "fee")
    assert adapter.sql_line("Line 1: the sandbox's mock has no system views (x).") == (
        "The sandbox's mock has no system views (x)."
    )
    assert adapter.sql_line("Line 3: :id has no value.") == ":id has no value. (line 3 of its SQL)"
    assert adapter.sql_line("Conversion Error: no") == "Conversion Error: no"


def test_an_export_without_rows_warns_in_its_answer() -> None:
    def bundle(rows: bool, uses: bool) -> targets.Bundle:
        return targets.Bundle("Shop", "", API_PY, "", "", {}, (), "", (), (), (), rows, uses)

    assert targets.warnings(bundle(False, True)) == [targets.NO_ROWS]
    assert targets.warnings(bundle(True, True)) == [] and targets.warnings(bundle(False, False)) == []
    module = targets.connections_module("", False, [])
    assert "it uses []" not in module and "has no connection named {name}." in module
    compile(module, "connections.py", "exec")
    assert json.dumps(targets.NO_ROWS)  # one sentence, plain text
