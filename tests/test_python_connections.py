"""A connection from your own Python: three boxes (Connect, List the tables, Read a table) and the
environment variables they read, each mapped to where its value comes from.

Made-up data only: a tiny web service started here on 127.0.0.1, serving made-up tables as JSON,
guarded by a made-up API key."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pyarrow as pa
import pytest
import uvicorn
from starlette.testclient import TestClient

import swissarmygrid as sag
from swissarmygrid.adapters.blade_run import BladeRunError, list_tables, read_table, run_code, set_variables
from swissarmygrid.domain import python_connections as rules
from swissarmygrid.domain.blades import BladeError, parse_blade, read_blade, write_blade
from swissarmygrid.domain.connections import connection_kind, has_catalog, opens_in_code
from swissarmygrid.server.app import create_app
from swissarmygrid.server.blade_runner import read_result
from swissarmygrid.server.blade_templates import PYTHON_CONNECT, PYTHON_READ, PYTHON_TABLES
from swissarmygrid.settings import Settings
from tests.conftest import AGENT, AUTH
from tests.fake_keyring import memory_keyring

API_KEY = "made-up-key-7391"  # made up: the tiny service below answers only to it


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


# ===== the environment variables the code reads =====


def test_every_way_of_reading_a_variable_is_found_by_name() -> None:
    code = """
import os
from os import environ, getenv
import os as system

a = os.environ["ORDERS_API_KEY"]
b = os.environ.get("ORDERS_API_URL", "http://127.0.0.1")
c = os.getenv("REGION")
d = secret("TOKEN")
e = environ["FROM_IMPORT"]
f = getenv("ALSO_IMPORTED")
g = system.environ.get("RENAMED_OS")
"""
    found = rules.env_reads(code)
    assert [(r.name, r.required) for r in found] == [
        ("ORDERS_API_KEY", True),  # os.environ["X"] fails without it
        ("ORDERS_API_URL", False),  # .get and getenv do not
        ("REGION", False),
        ("TOKEN", True),
        ("FROM_IMPORT", True),
        ("ALSO_IMPORTED", False),
        ("RENAMED_OS", False),
    ]
    assert rules.looks_secret("ORDERS_API_KEY") and rules.looks_secret("TOKEN")
    assert not rules.looks_secret("ORDERS_API_URL") and not rules.looks_secret("REGION")


def test_names_built_at_run_time_or_only_mentioned_are_not_variables() -> None:
    code = """
import os
prefix = "ORDERS"
a = os.environ[f"{prefix}_KEY"]            # an f-string: no name is written here
b = os.environ[prefix + "_URL"]            # built at run time
c = os.environ.get(name)                   # a variable, not a name
# os.environ["IN_A_COMMENT"]
text = 'os.environ["IN_A_STRING"] and os.getenv("ALSO_TEXT")'
os.environ["WRITTEN_NOT_READ"] = "x"       # set, not read
d = settings.get("NOT_THE_ENVIRONMENT")
e = other.environ["NOT_OS"]
"""
    assert rules.env_names(code) == []
    # A name inside an f-string's braces is still written out, so it is found.
    assert rules.env_names("url = f\"http://{os.environ['HOST']}/api\"") == ["HOST"]


def test_names_come_from_all_three_boxes_once_and_a_half_typed_box_has_none() -> None:
    connect = 'import os\nconn = os.environ["KEY"]'
    tables = 'import os\n[{"table": os.getenv("TABLE"), "column": "id"}]'
    read = 'import os\nos.environ.get("KEY"), os.environ["PAGE_SIZE"]'
    assert rules.env_names(connect, tables, read) == ["KEY", "TABLE", "PAGE_SIZE"]
    assert rules.env_names(connect, "def broken(:", None) == ["KEY"]  # being typed: no names, no error


def test_a_source_is_checked_and_only_names_the_code_reads_are_mapped() -> None:
    names = ["KEY", "URL", "REGION", "TOKEN"]
    sources = rules.parse_sources(
        [
            {"name": "KEY", "from": "vault", "vault": "Team vault", "secret": "orders-api-key"},
            {"name": "URL", "from": "value", "value": "http://127.0.0.1:9"},
            {"name": "REGION", "from": "env"},
            {"name": "TOKEN", "from": "keyring", "value": "never kept here"},
        ],
        names,
    )
    assert sources == {
        "KEY": {"from": "vault", "vault": "Team vault", "secret": "orders-api-key"},
        "URL": {"from": "value", "value": "http://127.0.0.1:9"},
        "REGION": {"from": "env"},
        "TOKEN": {"from": "keyring"},  # its value goes to the keyring, never into the mapping
    }
    assert rules.keyring_names(sources) == ["TOKEN"] and rules.plain_values(sources) == {
        "URL": "http://127.0.0.1:9"
    }
    for bad, why in (
        ([{"name": "OTHER", "from": "env"}], "never reads OTHER"),
        ([{"name": "KEY", "from": "nowhere"}], 'comes "from"'),
        ([{"name": "KEY", "from": "vault", "vault": "Team vault"}], "Name the secret"),
        ([{"name": "KEY", "from": "vault", "secret": "x"}], "Name the key vault"),
        ([{"name": "URL", "from": "value"}], "value is text"),
        ([{"name": "KEY", "from": "env"}, {"name": "KEY", "from": "env"}], "given twice"),
        ([{"name": "not a name", "from": "env"}], "not an environment variable name"),
        ("KEY=env", "are a list"),
    ):
        with pytest.raises(rules.PythonConnectionError, match=why):
            rules.parse_sources(bad, names)


# ===== List the tables: the catalog's shape =====

CONNECT = "conn = {'orders': ['order_id', 'amount'], 'clients': ['client']}"


def listed(command: str) -> tuple[list[str], list[list[Any]]]:
    _, names = run_code(CONNECT, "conn", {}, "Shop")
    return list_tables(names, command, {}, "Shop")


def test_the_catalog_is_a_list_of_dicts_or_a_dataframe_with_optional_columns() -> None:
    rows = "[{'table': t, 'column': c} for t, columns in conn.items() for c in columns]"
    columns, found = listed(rows)  # table and column alone
    assert columns == ["table", "column"] and found == [
        ["orders", "order_id"],
        ["orders", "amount"],
        ["clients", "client"],
    ]
    full = (
        "[{'schema': 'shop', 'table': t, 'column': c, 'type': 'text', 'description': 'made up'}"
        " for t, columns in conn.items() for c in columns]"
    )
    columns, found = listed(full)
    assert columns == ["schema", "table", "column", "type", "description"] and len(found) == 3
    assert rules.first_table(columns, found) == ("shop", "orders")
    assert rules.table_count(columns, found) == 2
    assert rules.tables_json(columns, found)[0] == {
        "schema": "shop",
        "table": "orders",
        "columns": [
            {"column": "order_id", "type": "text", "description": "made up"},
            {"column": "amount", "type": "text", "description": "made up"},
        ],
    }
    frame = f"import pandas as pd\npd.DataFrame({rows})"
    columns, found = listed(frame)  # a DataFrame, the same shape
    assert columns == ["table", "column"] and found[0] == ["orders", "order_id"]
    columns, found = listed(f"catalog = {rows}")  # or a variable named catalog
    assert len(found) == 3


@pytest.mark.parametrize(
    ("command", "why"),
    [
        ("'orders'", "returned a str. Return a list of dicts or a DataFrame: table, column"),
        ("[{'name': 'orders', 'field': 'id'}]", r"no table and no column \(it has: name, field\)"),
        ("[{'table': 'orders'}]", "This has no column"),
        ("[]", "returned no rows: one row for each column"),
        ("[{'table': 'orders', 'column': 'id'}, {'table': '', 'column': 'x'}]", "row 2 has no table"),
        ("[{'table': 'orders', 'column': None}]", "row 1 has no column"),
        ("x = 1", "gave nothing: end it with the tables"),
        ("conn['nowhere']", r"List the tables failed: KeyError: 'nowhere' \(line 1\)"),
    ],
)
def test_a_catalog_in_another_shape_says_what_is_wrong(command: str, why: str) -> None:
    with pytest.raises(BladeRunError, match=why):
        listed(command)


# ===== Read a table: what it returns =====

ORDERS = [{"order_id": n, "amount": n * 1.5} for n in range(1, 8)]  # seven made-up orders


@pytest.mark.parametrize(
    "rows",
    [
        ORDERS,  # a list of dicts
        pd.DataFrame(ORDERS),  # a DataFrame
        pa.Table.from_pylist(ORDERS),  # an Arrow table
        {"order_id": [o["order_id"] for o in ORDERS], "amount": [o["amount"] for o in ORDERS]},  # push's dict
    ],
    ids=["dicts", "dataframe", "arrow", "columns"],
)
def test_read_returns_anything_push_accepts(rows: Any) -> None:
    table, total = read_result(rows, None, None)
    assert table.column_names == ["order_id", "amount"] and table.num_rows == 7 and total is None
    assert table.to_pylist()[0] == {"order_id": 1, "amount": 1.5}


def test_the_limit_and_the_count() -> None:
    # (rows, total): the source's own count, beside the rows it gave.
    assert rules.split_read((ORDERS[:3], 7)) == (ORDERS[:3], 7)
    assert rules.split_read((ORDERS[:3], None)) == (ORDERS[:3], None)
    assert rules.split_read(ORDERS) == (ORDERS, None)
    two_rows = (ORDERS[0], ORDERS[1])  # a tuple of two rows is rows, not (rows, total)
    assert rules.split_read(two_rows) == (two_rows, None)
    table, total = read_result(ORDERS[:3], 7, 3)
    assert table.num_rows == 3 and total == 7
    # Code that ignored the limit returned every row: the first are kept, and the count is known.
    table, total = read_result(ORDERS, None, 3)
    assert table.num_rows == 3 and total == 7 and table.to_pylist()[-1]["order_id"] == 3
    # Fewer rows than the limit: all of them, and no count is needed.
    table, total = read_result(ORDERS, None, 50)
    assert table.num_rows == 7 and total is None
    # No limit (Load all rows): every row.
    assert read_result(ORDERS, 7, None)[0].num_rows == 7
    assert rules.read_total(5, 5, 2) == (5, 5)  # a total below what came is not believed
    with pytest.raises(rules.PythonConnectionError, match="below zero"):
        rules.split_read((ORDERS, -1))


@pytest.mark.parametrize(
    ("rows", "why"),
    [
        ([], "returned no rows"),
        ([1, 2, 3], "a list that is not all dicts"),
        ("orders", "returned a str. Return a DataFrame, an Arrow table or a list of dicts"),
        (42, "returned a int"),
    ],
)
def test_read_in_another_shape_says_what_is_wrong(rows: Any, why: str) -> None:
    with pytest.raises(BladeRunError, match=why):
        read_result(rows, None, 10)


def test_read_is_given_conn_schema_table_and_limit() -> None:
    _, names = run_code(CONNECT, "conn", {}, "Shop")
    command = "[{'schema': schema, 'table': table, 'limit': limit, 'column': c} for c in conn[table]]"
    rows, total = read_table(names, command, "shop", "orders", 5, {}, "Shop")
    assert rows[0] == {"schema": "shop", "table": "orders", "limit": 5, "column": "order_id"}
    assert total is None
    rows, total = read_table(names, "rows = (conn[table], 99)", "", "clients", None, {}, "Shop")
    assert rows == ["client"] and total == 99  # a variable named rows works too
    with pytest.raises(BladeRunError, match=r"Read a table failed: KeyError: 'gone' \(line 1\)"):
        read_table(names, "conn[table]", "", "gone", None, {}, "Shop")
    with pytest.raises(BladeRunError, match="gave nothing: end it with the rows"):
        read_table(names, "x = 1", "", "orders", None, {}, "Shop")


# ===== one connection: saving, and the portable file =====


def python_connection(name: str = "Orders API", **more: Any) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "other",
        "template": "python",
        "variable": "conn",
        "code": PYTHON_CONNECT,
        "catalog": {"language": "python", "command": PYTHON_TABLES},
        "read": {"command": PYTHON_READ},
        "variables": [
            {"name": "ORDERS_API_URL", "from": "value", "value": "http://127.0.0.1:9"},
            {"name": "ORDERS_API_KEY", "from": "vault", "vault": "Team vault", "secret": "orders-api-key"},
        ],
    } | more


def test_it_is_a_connection_with_a_catalog_and_a_name_in_code() -> None:
    assert connection_kind("other", "python") == "python"
    assert has_catalog("python") and opens_in_code("python")
    blade = parse_blade(python_connection())
    assert blade.variable == "conn" and blade.read_command == PYTHON_READ
    assert blade.catalog_language == "python" and blade.catalog_command == PYTHON_TABLES
    assert [r.name for r in blade.env_reads] == ["ORDERS_API_URL", "ORDERS_API_KEY"]
    assert blade.secrets == []  # nothing is saved on this computer: a vault and a plain value
    kept = parse_blade(python_connection(variables=[{"name": "ORDERS_API_KEY", "from": "keyring"}]))
    assert kept.secrets == ["ORDERS_API_KEY"]  # saved on this computer: the keyring keeps it
    with pytest.raises(BladeError, match="never makes 'conn'"):
        parse_blade(python_connection(code="client = 1"))
    with pytest.raises(BladeError, match="Read a table"):
        parse_blade(python_connection(read={"command": "def broken(:"}))
    with pytest.raises(BladeError, match="never reads NOT_READ"):
        parse_blade(python_connection(variables=[{"name": "NOT_READ", "from": "env"}]))
    with pytest.raises(BladeError, match="List the tables is Python"):
        parse_blade(python_connection(catalog={"language": "sql", "command": "SELECT 1"}))
    # Empty boxes: no catalog, no rows; still a connection that makes conn.
    bare = parse_blade(python_connection(catalog=None, read=None, variables=[]))
    assert not bare.has_catalog and bare.read_command is None


def test_the_portable_file_keeps_the_three_boxes_and_the_mapping() -> None:
    blade = parse_blade(python_connection(description="Made-up orders", row_limit=500))
    text = write_blade(blade.to_json())
    assert "[catalog]" in text and "[read]" in text and "[variables]" in text
    assert 'ORDERS_API_KEY = { from = "vault", vault = "Team vault", secret = "orders-api-key" }' in text
    assert 'ORDERS_API_URL = { from = "value", value = "http://127.0.0.1:9" }' in text
    back = parse_blade(read_blade(text))
    assert (back.code, back.catalog_command, back.read_command) == (
        PYTHON_CONNECT,
        PYTHON_TABLES,
        PYTHON_READ,
    )
    assert back.variables == blade.variables and back.row_limit == 500
    assert back.template == "python" and back.variable == "conn" and back.description == "Made-up orders"
    assert write_blade(back.to_json()) == text  # the same file again


def test_a_value_saved_on_this_computer_is_never_in_the_file() -> None:
    data = python_connection(
        variables=[{"name": "ORDERS_API_KEY", "from": "keyring", "value": API_KEY}],
        secrets={"ORDERS_API_KEY": API_KEY},
    )
    text = write_blade(parse_blade(data).to_json())
    assert API_KEY not in text and 'ORDERS_API_KEY = { from = "keyring" }' in text


def test_files_written_before_the_boxes_still_load() -> None:
    old = """# /// swissarmygrid-blade
# format = 1
# name = "Weather"
# kind = "other"
# variable = "session"
#
# [catalog]
# language = "python"
# command = '''
# [{"table": "days", "column": "rain"}]
# '''
# ///
session = object()
"""
    blade = parse_blade(read_blade(old))
    assert blade.name == "Weather" and blade.read_command is None and blade.variables == {}
    assert blade.to_json()["read"] is None and connection_kind(blade.kind, blade.template) is None


# ===== the variables reach the code, and no secret leaves =====


def test_variables_are_set_before_the_code_and_a_missing_one_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PC_URL", raising=False)
    monkeypatch.delenv("PC_KEY", raising=False)
    monkeypatch.delenv("PC_OPTIONAL", raising=False)
    code = 'import os\nconn = (os.environ["PC_URL"], os.environ["PC_KEY"], os.getenv("PC_OPTIONAL"))'
    reads = rules.env_reads(code)
    with pytest.raises(BladeRunError, match="Shop reads PC_URL, PC_KEY, which have no value: choose where"):
        set_variables(reads, {}, [], {}, "Shop")
    try:
        set_variables(reads, {"PC_URL": "http://127.0.0.1:9"}, ["PC_KEY"], {"PC_KEY": API_KEY}, "Shop")
        value, _ = run_code(code, "conn", {"PC_KEY": API_KEY}, "Shop")
        assert value == ("http://127.0.0.1:9", API_KEY, None)  # the code reads them as it always would
    finally:
        os.environ.pop("PC_URL", None)
        os.environ.pop("PC_KEY", None)


def test_a_secret_in_an_error_is_starred_out() -> None:
    _, names = run_code("conn = 1", "conn", {}, "Shop")
    secrets = {"ORDERS_API_KEY": API_KEY}
    with pytest.raises(BladeRunError) as failed:
        list_tables(names, f"raise ValueError('refused {API_KEY}')", secrets, "Shop")
    assert API_KEY not in str(failed.value) and "refused ****" in str(failed.value)
    with pytest.raises(BladeRunError) as failed:
        read_table(names, f"raise ValueError('refused {API_KEY}')", "", "orders", 5, secrets, "Shop")
    assert API_KEY not in str(failed.value) and "refused ****" in str(failed.value)


# ===== the whole thing, over a tiny web service, through the real child process =====

TABLES: dict[str, dict[str, list[dict[str, Any]]]] = {
    "orders": {
        "columns": [{"name": "order_id", "type": "integer"}, {"name": "amount", "type": "number"}],
        "rows": [{"order_id": n, "amount": round(n * 2.5, 2)} for n in range(1, 31)],  # thirty, made up
    },
    "clients": {
        "columns": [{"name": "client", "type": "text"}],
        "rows": [{"client": "Ada"}, {"client": "Grace"}],
    },
}


class _Service(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.headers.get("X-Api-Key") != API_KEY:
            self.send_error(401, "Bad API key")
            return
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        if parts == ["tables"]:
            answer: Any = [{"name": name, "columns": t["columns"]} for name, t in TABLES.items()]
        elif len(parts) == 3 and parts[0] == "tables" and parts[2] == "rows" and parts[1] in TABLES:
            rows = TABLES[parts[1]]["rows"]
            limit = parse_qs(url.query).get("limit")
            answer = {"rows": rows[: int(limit[0])] if limit else rows, "total": len(rows)}
        else:
            self.send_error(404)
            return
        body = json.dumps(answer).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # quiet
        pass


@pytest.fixture
def service() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join(5)


TEAM_VAULT = {
    "name": "Team vault",
    "kind": "vault",
    "variable": "get",
    "code": f'values = {{"orders-api-key": "{API_KEY}", "other": "made-up"}}\n\n\n'
    "def names():\n    return list(values)\n\n\ndef get(name):\n    return values[name]\n",
    "vault_mapping": [{"env": "OTHER", "secret": "other"}],
}


def orders_api(url: str, **more: Any) -> dict[str, Any]:
    """The starter's own three boxes, its URL a plain value and its key an entry in the made-up vault."""
    variables = [
        {"name": "ORDERS_API_URL", "from": "value", "value": url},
        {"name": "ORDERS_API_KEY", "from": "vault", "vault": "Team vault", "secret": "orders-api-key"},
    ]
    return python_connection(variables=variables, row_limit=10) | more


def test_the_form_lists_the_type_its_boxes_and_the_variables_it_reads(client: TestClient) -> None:
    types = {t["id"]: t for t in client.get("/connections/types", headers=AUTH).json()["types"]}
    form = types["python"]
    assert form["connection"] == "python" and form["group"] == "Your own code"
    assert form["label"] == "Python (your own code)" and form["variable"] == "conn"
    assert form["catalog"] == {"language": "python", "command": PYTHON_TABLES}
    assert form["read"] == {"command": PYTHON_READ}
    assert [(r["name"], r["required"], r["secret"]) for r in form["reads"]] == [
        ("ORDERS_API_URL", True, False),
        ("ORDERS_API_KEY", True, True),
    ]
    assert types["postgres"]["reads"] == []  # only the user's own Python has them
    # As the boxes are typed: the names, and whether this computer's environment has each (no value).
    body = {"code": 'import os\nconn = os.environ["PATH"]', "read": 'os.getenv("PC_NOT_SET_ANYWHERE")'}
    found = client.post("/connections/variables", json=body, headers=AGENT).json()["variables"]
    assert found == [
        {"name": "PATH", "required": True, "secret": False, "set": True},
        {"name": "PC_NOT_SET_ANYWHERE", "required": False, "secret": False, "set": False},
    ]


def test_a_python_connection_over_a_web_service_end_to_end(client: TestClient, service: str) -> None:
    assert client.post("/blades", json=TEAM_VAULT, headers=AUTH).status_code == 200
    draft = orders_api(service)

    # Test (nothing saved): Connect, List the tables, the first table's first rows.
    tested = client.post("/connections/test", json=draft, headers=AUTH)
    assert tested.status_code == 200, tested.text
    answer = tested.json()
    assert answer["ok"] and answer["type"] == "Api" and answer["tables"] == 2 and answer["columns"] == 3
    preview = answer["preview"]
    assert (preview["schema"], preview["table"], preview["total"]) == ("api", "orders", 30)
    assert preview["columns"] == ["order_id", "amount"] and len(preview["rows"]) == 20
    assert preview["rows"][0] == [1, 2.5]
    assert API_KEY not in tested.text
    assert client.get("/connections", headers=AUTH).json()["connections"][0]["name"] == "Team vault"

    # A wrong key: the service's refusal, said plainly; a missing variable is named before the code runs.
    wrong = orders_api(service, variables=[{"name": "ORDERS_API_URL", "from": "value", "value": service}])
    refused = client.post("/connections/test", json=wrong, headers=AUTH)
    assert refused.status_code == 422 and "reads ORDERS_API_KEY, which has no value" in refused.text
    gone = orders_api(service)
    gone["variables"][1]["vault"] = "No such vault"
    missing = client.post("/connections/test", json=gone, headers=AUTH)
    assert missing.status_code == 400 and "No such vault, which is not among the connections" in missing.text

    # Save: one connection, listed as what it is, its mapping shown without a value.
    saved = client.post("/connections", json=draft, headers=AUTH)
    assert saved.status_code == 200, saved.text
    assert saved.json()["connection"] == "python" and saved.json()["has_catalog"]
    listed = {c["name"]: c for c in client.get("/connections", headers=AUTH).json()["connections"]}
    assert listed["Orders API"]["connection"] == "python"
    assert listed["Orders API"]["type"] == "Python (your own code)"
    assert listed["Orders API"]["code_name"] == "orders_api"  # its name in Workbench code
    form = client.get("/connections/Orders%20API", headers=AGENT).json()
    assert form["read"] == {"command": PYTHON_READ} and form["row_limit"] == 10
    assert form["variables"] == draft["variables"]
    assert [r["name"] for r in form["reads"]] == ["ORDERS_API_URL", "ORDERS_API_KEY"]

    # List the tables: the catalog, as any connection's (the tree, completion, the agent's tools).
    tables = client.post("/connections/Orders%20API/tables", json={}, headers=AGENT)
    assert tables.status_code == 200, tables.text
    assert [(t["schema"], t["table"], len(t["columns"])) for t in tables.json()["tables"]] == [
        ("api", "orders", 2),
        ("api", "clients", 1),
    ]
    assert tables.json()["catalog"]["tables"] == 2 and tables.json()["catalog"]["columns"] == 3
    refreshed = client.post("/blades/Orders%20API/refresh", json={}, headers=AUTH)  # Refresh catalog
    assert refreshed.status_code == 200, refreshed.text
    schemas = client.get("/catalogs/Orders%20API/schemas", headers=AUTH).json()["schemas"]
    assert [s["schema"] for s in schemas] == ["api"]
    columns = client.get(
        "/catalogs/Orders%20API/columns", params={"schema": "api", "table": "orders"}, headers=AUTH
    ).json()["columns"]
    assert [(c["column"], c["type"]) for c in columns] == [("order_id", "integer"), ("amount", "number")]

    # The catalog page's preview: the first rows, nothing kept.
    preview = client.post(
        "/connections/Orders%20API/preview", json={"schema": "api", "table": "clients"}, headers=AGENT
    )
    assert preview.status_code == 200, preview.text
    assert preview.json() == {"columns": ["client"], "rows": [["Ada"], ["Grace"]]}

    # Open as grid: the first Rows to open rows, the grid told how many the source holds.
    opened = client.post(
        "/connections/Orders%20API/open", json={"schema": "api", "table": "orders"}, headers=AGENT
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["shown"] == 10 and opened.json()["total"] == 30
    grid = client.get(f"/grids/{opened.json()['grid']}", headers=AUTH).json()
    assert grid["dataset"] == "orders" and grid["row_count"] == 10
    assert grid["opened"] == {
        "connection": "Orders API",
        "database": "",
        "schema": "api",
        "table": "orders",
        "shown": 10,
        "total": 30,
    }
    # Load all rows: the same table again, whole, and the note goes.
    everything = client.post(
        "/connections/Orders%20API/open", json={"schema": "api", "table": "orders", "all": True}, headers=AUTH
    )
    assert everything.status_code == 200, everything.text
    grid = client.get(f"/grids/{everything.json()['grid']}", headers=AUTH).json()
    assert grid["row_count"] == 30 and grid["opened"] is None

    # The connection row's Test: the saved one, with its preview.
    again = client.post("/blades/Orders%20API/test", json={}, headers=AUTH)
    assert again.status_code == 200, again.text
    assert again.json()["tables"] == 2 and len(again.json()["preview"]["rows"]) == 20

    # No answer, and nothing on disk, holds the key; the plain value is not a secret and shows.
    for path in ("/connections", "/connections/Orders%20API", "/blades", "/blades/Orders%20API"):
        assert API_KEY not in client.get(path, headers=AUTH).text
    exported = client.get("/blades/Orders%20API/export", headers=AUTH).text
    assert API_KEY not in exported and service in exported and "[read]" in exported
    # The agent is never given what sag.connection gets (it holds the vault's own code and passwords).
    assert client.get("/blades/Orders%20API/python", headers=AGENT).status_code == 403


def test_a_value_saved_on_this_computer_reaches_the_code_and_no_answer(
    client: TestClient, service: str, tmp_path: Path
) -> None:
    variables = [
        {"name": "ORDERS_API_URL", "from": "value", "value": service},
        {"name": "ORDERS_API_KEY", "from": "keyring"},
    ]
    draft = orders_api(service, variables=variables)
    # Typed into the form for a Test: used, not saved.
    tested = client.post(
        "/connections/test", json=draft | {"secrets": {"ORDERS_API_KEY": API_KEY}}, headers=AUTH
    )
    assert tested.status_code == 200 and tested.json()["tables"] == 2 and API_KEY not in tested.text
    bad = client.post(
        "/connections/test", json=draft | {"secrets": {"ORDERS_API_KEY": "wrong-key-000"}}, headers=AUTH
    )
    assert bad.status_code == 422 and "401" in bad.text and "wrong-key-000" not in bad.text
    saved = client.post("/connections", json=draft | {"secrets": {"ORDERS_API_KEY": API_KEY}}, headers=AUTH)
    assert saved.status_code == 200, saved.text
    assert saved.json()["secrets"] == {"ORDERS_API_KEY": True}  # saved: yes or no, never the value
    preview = client.post(
        "/connections/Orders%20API/preview", json={"schema": "api", "table": "clients"}, headers=AUTH
    )
    assert preview.status_code == 200 and preview.json()["rows"] == [["Ada"], ["Grace"]]
    state = tmp_path / "state"
    on_disk = "".join(
        p.read_text(encoding="utf-8", errors="replace") for p in state.rglob("*") if p.is_file()
    )
    assert "Orders API" in on_disk and API_KEY not in on_disk  # the connection is saved; its key is not
    for path in ("/connections", "/connections/Orders%20API", "/blades/Orders%20API"):
        assert API_KEY not in client.get(path, headers=AGENT).text
    assert API_KEY not in client.get("/blades/Orders%20API/export", headers=AUTH).text


def test_an_environment_variable_is_read_from_this_computer(
    client: TestClient, service: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORDERS_API_KEY", API_KEY)  # the server's own environment: the child inherits it
    monkeypatch.setenv("ORDERS_API_URL", service)
    draft = orders_api(service, variables=[])  # nothing mapped: each comes from the environment
    tested = client.post("/connections/test", json=draft, headers=AUTH)
    assert tested.status_code == 200, tested.text
    assert tested.json()["preview"]["total"] == 30 and API_KEY not in tested.text


def test_a_box_that_fails_says_which_and_only_python_connections_list_this_way(
    client: TestClient, service: str
) -> None:
    assert client.post("/blades", json=TEAM_VAULT, headers=AUTH).status_code == 200
    broken = orders_api(service, read={"command": "conn.get('/nowhere')"})
    failed = client.post("/connections/test", json=broken, headers=AUTH)
    assert failed.status_code == 422 and "Read a table failed" in failed.text and "404" in failed.text
    shape = orders_api(service, catalog={"language": "python", "command": "conn.get('/tables')"})
    failed = client.post("/connections/test", json=shape, headers=AUTH)
    assert (
        failed.status_code == 422 and "This has no table and no column (it has: name, columns)" in failed.text
    )
    # Without Read a table: the tables are listed, and a table says why it cannot open.
    assert client.post("/connections", json=orders_api(service, read=None), headers=AUTH).status_code == 200
    tested = client.post("/blades/Orders%20API/test", json={}, headers=AUTH).json()
    assert tested["tables"] == 2 and "preview" not in tested
    opened = client.post("/connections/Orders%20API/open", json={"table": "orders"}, headers=AUTH)
    assert opened.status_code == 422 and "has no Read a table" in opened.text
    assert client.post("/connections/Team%20vault/tables", json={}, headers=AUTH).status_code == 400


# ===== in a notebook: sag.connection gives conn, sag.read a table =====

TOKEN = "python-connection-token"


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    settings = Settings(
        state_dir=tmp_path / "state", export_dir=tmp_path / "exports", auto_load_catalogs=False
    )
    server = uvicorn.Server(uvicorn.Config(create_app(port, TOKEN, settings), port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    info = tmp_path / "server.json"
    info.write_text(json.dumps({"port": port, "token": TOKEN}))
    monkeypatch.setenv("SWISSARMYGRID_INFO", str(info))
    monkeypatch.setenv("SWISSARMYGRID_OPEN", "0")
    yield port
    server.should_exit = True
    thread.join(10)


def _post(port: int, path: str, body: Any) -> Any:
    import urllib.request

    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (loopback)
        return json.loads(response.read() or b"null")


def test_in_a_notebook_the_connection_is_conn_and_a_table_is_read(
    live: int, service: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ORDERS_API_KEY", raising=False)
    monkeypatch.delenv("ORDERS_API_URL", raising=False)
    _post(live, "/blades", TEAM_VAULT)
    _post(live, "/connections", orders_api(service))
    try:
        conn = sag.connection("Orders API")
        assert type(conn).__name__ == "Api" and [t["name"] for t in conn.get("/tables")] == [
            "orders",
            "clients",
        ]
        # The variables are set here as the code expects them, as a vault's mapping sets its own.
        assert os.environ["ORDERS_API_KEY"] == API_KEY and os.environ["ORDERS_API_URL"] == service
        assert "OTHER" not in os.environ  # only what this connection maps, not the vault's other entries
        rows = sag.read("Orders API", "orders", limit=4)
        assert [r["order_id"] for r in rows] == [1, 2, 3, 4]
        assert len(sag.read("Orders API", "clients", schema="api")) == 2
        with pytest.raises(ValueError, match="has no Read a table box"):
            sag.read("Team vault", "orders")
    finally:
        os.environ.pop("ORDERS_API_KEY", None)
        os.environ.pop("ORDERS_API_URL", None)
