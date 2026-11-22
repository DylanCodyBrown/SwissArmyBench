"""A local sandbox API exported for each framework target (domain/api_targets.py, services/api_export.py; the
owner,
2026-11-21: "get API code that is ready to go for that platform ... fast API, azure function app Linux python,
or
lambda Linux python").

The same API.py, built and run against the sandbox's mock of a made-up SQLite connection, is exported three
ways;
each export runs here against the REAL connection (its own code: connections.py), with no app: the Lambda
handler
with made-up API Gateway events (REST and HTTP), the Azure Functions app through a stand-in of
azure.functions'
few names (its worker is not installed here), the FastAPI app through FastAPI when it is installed (else a
stand-in of its few names). The answers match the sandbox's. No secret is in any file; a hand-edited file is
kept; the agent's export with the sandbox's rows waits for Allow. Made-up data only."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import api_targets as targets
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring

KEYRING_SECRET = "made-up-keyring-s3cret"

API_PY = """\
# /// swissarmybench-api
# name = "Shop API"
# description = "Made-up customers"
# target = "aws_lambda"
# base_path = "/v1"
# ///
from typing import TypedDict

from sab_api import ApiError, connection, endpoint, records


class Customer(TypedDict):
    customer_id: int
    city: str


@endpoint("GET", "/customers")
def customers(city: str = "") -> list[Customer]:
    db = connection("Shop")
    if city:
        return records(
            db.query("SELECT customer_id, city FROM customers WHERE city = ? ORDER BY customer_id", [city])
        )
    return records(db.read("customers", columns=["customer_id", "city"], sort=[["customer_id", "asc"]]))


@endpoint("GET", "/customers/{customer_id}")
def customer(customer_id: int) -> Customer:
    found = records(connection("Shop").read("customers", filters=[["customer_id", "=", customer_id]]))
    if not found:
        raise ApiError(404, f"No customer {customer_id}.")
    return found[0]
"""

AZURE_STANDIN = '''
"""azure.functions' few names, stood in for (the worker is not installed here)."""
import enum


class AuthLevel(enum.Enum):
    ANONYMOUS = "anonymous"
    FUNCTION = "function"


class HttpRequest:
    def __init__(self, method, url, params=None, body=b"", route_params=None, headers=None):
        self.method, self.url, self.params, self._body = method, url, params or {}, body
        self.route_params = route_params or {}

    def get_body(self):
        return self._body


class HttpResponse:
    def __init__(self, body=b"", status_code=200, headers=None, mimetype=None):
        self.body, self.status_code, self.headers, self.mimetype = body, status_code, headers or {}, mimetype

    def get_body(self):
        return self.body


class _Function:
    def __init__(self, fn, route, methods):
        self.fn, self.route, self.methods, self.name = fn, route, methods, fn.__name__

    def get_function_name(self):
        return self.name

    def get_user_function(self):
        return self.fn


class FunctionApp:
    def __init__(self, http_auth_level=None):
        self.level, self.made = http_auth_level, []

    def route(self, route, methods):
        def register(fn):
            self.made.append(_Function(fn, route, methods))
            return self.made[-1]
        return register

    def function_name(self, name):
        def named(made):
            made.name = name
            return made
        return named

    def get_functions(self):
        return self.made
'''

FASTAPI_STANDIN = '''
"""FastAPI's few names, stood in for when FastAPI is not installed: routes recorded, Starlette serving."""
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


class FastAPI(Starlette):
    def __init__(self, title="", description=""):
        super().__init__()
        self.title = title

    def _add(self, method, path, endpoint):
        self.router.routes.append(Route(path, endpoint, methods=[method]))

    def get(self, path, **_):
        return lambda fn: (self._add("GET", path, fn), fn)[1]

    def post(self, path, **_):
        return lambda fn: (self._add("POST", path, fn), fn)[1]

    def put(self, path, **_):
        return lambda fn: (self._add("PUT", path, fn), fn)[1]

    def patch(self, path, **_):
        return lambda fn: (self._add("PATCH", path, fn), fn)[1]

    def delete(self, path, **_):
        return lambda fn: (self._add("DELETE", path, fn), fn)[1]
'''


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def shop(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    """A project whose sandbox holds the made-up Shop connection's customers (read once)."""
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute("CREATE TABLE customers (customer_id INTEGER, city TEXT)")
        made_up.executemany(
            "INSERT INTO customers VALUES (?, ?)",
            [(1, "Springfield"), (2, "Shelbyville"), (3, "Springfield")],
        )
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        'assert secret("password")\n'
        f'path = Path(r"{database}")\n'
        "conn = sqlite3.connect(path)\n"
    )
    connection = {
        "name": "Shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code,
        "secrets": {"password": KEYRING_SECRET},
    }  # fmt: skip
    with memory_keyring(), make_client(tmp_path) as client:
        ok(client.post("/connections", json=connection, headers=AUTH))
        folder = tmp_path / "shop"
        ok(client.post("/project/new", json={"path": str(folder)}, headers=AUTH))
        ok(
            client.post(
                "/sandbox/tables",
                json={"from": "connection", "connection": "Shop", "table": "customers"},
                headers=AUTH,
            )
        )
        (folder / "API.py").write_text(API_PY, encoding="utf-8")
        yield client, folder


# A Python with fastapi, azure-functions and duckdb installed (the generated projects' requirements): the
# exports
# run there against the real packages; else this Python with the stand-ins.
EXPORT_PYTHON = os.environ.get("SWISSARMYBENCH_EXPORT_PYTHON")


def _run(folder: Path, script: str, extra: Path | None = None, env: dict[str, str] | None = None) -> Any:
    """A script run in the export's folder by a fresh Python with no app: its printed JSON."""
    if EXPORT_PYTHON:
        extra = None
    head = f"import sys\nsys.path[:0] = [{str(folder)!r}" + (f", {str(extra)!r}" if extra else "") + "]\n"
    done = subprocess.run(  # noqa: S603 (this Python, the test's own script)
        [EXPORT_PYTHON or sys.executable, "-I", "-c", head + textwrap.dedent(script)],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": "/usr/bin:/bin", "SHOP_PASSWORD": "made-up-from-the-platform"} | (env or {}),
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_targets_are_listed_with_an_extensions(shop: tuple[TestClient, Path]) -> None:
    client, _ = shop
    ids = [t["id"] for t in ok(client.get("/local-api/targets", headers=AUTH))["targets"]]
    assert ids == ["fastapi", "azure_functions", "aws_lambda"]
    made = targets.from_extension(
        {"id": "flask", "label": "Flask", "render": lambda b: {"app.py": ""}}, "flask_ext"
    )
    assert made.extension == "flask_ext" and made.to_json()["label"] == "Flask"
    with pytest.raises(ValueError, match="needs an id and a render"):
        targets.from_extension({"id": "x"}, "e")


def test_each_target_runs_with_the_real_connection_and_answers_as_the_mock(
    shop: tuple[TestClient, Path], tmp_path: Path
) -> None:
    client, folder = shop
    # The mock's answer, through the sandbox (the shape the export must give).
    state = ok(client.get("/local-api", headers=AUTH))
    assert state["endpoints"][0]["data"] == ["Mock of Shop (sqlite)"]
    exported: dict[str, Path] = {}
    for target in ("fastapi", "azure_functions", "aws_lambda"):
        done = ok(client.post("/local-api/export", json={"target": target}, headers=AUTH))
        place = Path(done["folder"])
        assert place == folder / "exports" / "api" / target
        # The fewest files (Plans/adapter.plan.md): the core files and the platform's own, sab_api folded into
        # the framework file; api_adapter.py only when API.py calls another API (this one does not).
        framework = {
            "fastapi": {"main.py"},
            "azure_functions": {"function_app.py", "host.json", ".funcignore"},
            "aws_lambda": {"lambda_function.py", "template.yaml"},
        }[target]
        core = {"API.py", "adapter.py", "connections.py", "README.md", "requirements.txt"}
        assert set(done["files"]) == core | framework
        assert sorted(p.name for p in place.iterdir()) == sorted(core | framework)
        wanted = (place / "requirements.txt").read_text(encoding="utf-8").split()
        assert "duckdb>=1.1" in wanted and "pyarrow>=15" in wanted  # the adapter's
        assert (place / "API.py").read_text(encoding="utf-8") == API_PY  # the endpoints never change
        from swissarmybench.adapters import adapter as the_adapter

        made = Path(the_adapter.__file__).read_bytes()
        assert (place / "adapter.py").read_bytes() == made  # the same bytes as the app's (12a)
        sections = (place / "connections.py").read_text(encoding="utf-8")
        assert "# ===== connection: Shop =====" in sections and "# ===== end of Shop =====" in sections
        assert "SHOP_PASSWORD" in done["variables"] and "SHOP_PASSWORD" in (place / "README.md").read_text(
            encoding="utf-8"
        )
        for file in place.rglob("*"):
            if file.is_file():
                assert KEYRING_SECRET not in file.read_text(encoding="utf-8", errors="replace"), file
        compile((place / "connections.py").read_text(encoding="utf-8"), "connections.py", "exec")
        exported[target] = place
    # AWS Lambda: API Gateway's REST (1.0) and HTTP (2.0, a stage) events.
    lam = _run(
        exported["aws_lambda"],
        """
        import json, lambda_function
        rest = {"httpMethod": "GET", "path": "/v1/customers",
                "queryStringParameters": {"city": "Springfield"}}
        http = {"rawPath": "/prod/v1/customers/2",
                "requestContext": {"http": {"method": "GET"}, "stage": "prod"}}
        missing = {"rawPath": "/v1/customers/9",
                   "requestContext": {"http": {"method": "GET"}, "stage": "$default"}}
        out = [lambda_function.handler(e, None) for e in (rest, http, missing)]
        print(json.dumps([[o["statusCode"], json.loads(o["body"])] for o in out]))
        """,
    )
    assert lam == [
        [200, [{"customer_id": 1, "city": "Springfield"}, {"customer_id": 3, "city": "Springfield"}]],
        [200, {"customer_id": 2, "city": "Shelbyville"}],
        [404, {"error": "No customer 9."}],
    ]
    # The copied adapter answers an Arrow endpoint in the export, with no app (Plans/adapter.plan.md).
    arrow = _run(
        exported["aws_lambda"],
        """
        import json, pyarrow as pa, adapter, lambda_function
        sab_api = lambda_function.sab_api
        @sab_api.endpoint("GET", "/arrow")
        def arrow() -> pa.Table:
            return pa.table({"n": [1, 2]})
        status, _, body = sab_api.handle("GET", "/arrow")
        print(json.dumps([status, json.loads(body), adapter.__file__.endswith("adapter.py")]))
        """,
    )
    assert arrow == [200, [{"n": 1}, {"n": 2}], True]
    template = (exported["aws_lambda"] / "template.yaml").read_text(encoding="utf-8")
    assert "Runtime: python3.12" in template and "Handler: lambda_function.handler" in template
    # Azure Functions: each function called through azure.functions' names, stood in for.
    stand = tmp_path / "standins"
    (stand / "azure" / "functions").mkdir(parents=True)
    (stand / "azure" / "__init__.py").write_text("", encoding="utf-8")
    (stand / "azure" / "functions" / "__init__.py").write_text(AZURE_STANDIN, encoding="utf-8")
    az = _run(
        exported["azure_functions"],
        """
        import json, function_app
        import azure.functions as func
        made = function_app.app.get_functions()
        names = [f.get_function_name() for f in made]
        fn = {f.get_function_name(): f.get_user_function() for f in made}
        request = func.HttpRequest(
            method="GET", url="https://x.azurewebsites.net/v1/customers",
            params={"city": "Shelbyville"}, body=b"",
        )
        got = fn["customers"](request)
        print(json.dumps([names, got.status_code, json.loads(got.get_body())]))
        """,
        stand,
    )
    assert az[0] == ["customers", "customer"]
    app_text = (exported["azure_functions"] / "function_app.py").read_text(encoding="utf-8")
    assert "@app.route(route='v1/customers/{customer_id}', methods=['GET'])" in app_text
    assert az[1:] == [200, [{"customer_id": 2, "city": "Shelbyville"}]]
    host = json.loads((exported["azure_functions"] / "host.json").read_text(encoding="utf-8"))
    assert host["extensions"]["http"]["routePrefix"] == ""
    assert not (exported["azure_functions"] / "local.settings.json").exists()  # the user's own
    # FastAPI: its app served (FastAPI itself when installed, else its few names stood in for).
    try:
        import fastapi  # type: ignore[import-not-found]  # noqa: F401

        extra = None
    except ImportError:
        (stand / "fastapi").mkdir()
        (stand / "fastapi" / "__init__.py").write_text(
            FASTAPI_STANDIN + "\n__all__ = ['FastAPI', 'Request', 'Response']\n", encoding="utf-8"
        )
        extra = stand
    fa = _run(
        exported["fastapi"],
        """
        import json
        from starlette.testclient import TestClient
        import main
        with TestClient(main.app) as c:
            a = c.get("/v1/customers/3")
            b = c.get("/v1/customers", params={"city": "Springfield"})
        print(json.dumps([a.status_code, a.json(), b.json()]))
        """,
        extra,
    )
    assert fa == [
        200,
        {"customer_id": 3, "city": "Springfield"},
        [{"customer_id": 1, "city": "Springfield"}, {"customer_id": 3, "city": "Springfield"}],
    ]
    # The sandbox's tables from Shop answer the same SQL alike (tests/test_local_api.py runs the API itself).
    from tests.test_sandbox_query import arrow_rows, query

    sql = "SELECT customer_id, city FROM customers WHERE city = ? ORDER BY customer_id"
    assert arrow_rows(query(client, sql, ["Springfield"], connection="Shop")) == lam[0][1]


def test_a_hand_edited_file_is_kept_and_a_stale_one_goes(shop: tuple[TestClient, Path]) -> None:
    client, folder = shop
    place = folder / "exports" / "api" / "aws_lambda"
    ok(client.post("/local-api/export", json={}, headers=AUTH))
    (place / "old_file.py").write_text("# from an earlier export\n", encoding="utf-8")
    (place / "README.md").write_text("# my own notes\n", encoding="utf-8")
    hand = folder / ".sab" / "hand-edited.json"
    hand.write_text(json.dumps(["exports/api/aws_lambda/README.md"]), encoding="utf-8")
    again = ok(client.post("/local-api/export", json={}, headers=AUTH))
    assert [k["file"] for k in again["kept"]] == ["README.md"] and again["kept"][0][
        "yours"
    ] == "# my own notes\n"
    assert "old_file.py" in again["removed"] and not (place / "old_file.py").exists()
    assert (place / "README.md").read_text(encoding="utf-8") == "# my own notes\n"
    replaced = ok(client.post("/local-api/export", json={"replace": ["README.md"]}, headers=AUTH))
    assert replaced["kept"] == [] and "## Deploy" in (place / "README.md").read_text(encoding="utf-8")
    assert ok(client.post("/local-api/export", json={}, headers=AUTH))["written"] == []  # nothing changed


def test_will_this_work_for_real_reads_only_a_loaded_catalog(shop: tuple[TestClient, Path]) -> None:
    client, folder = shop
    checked = ok(client.post("/local-api/check", json={}, headers=AUTH))
    assert {c["state"] for c in checked["checks"]} == {"no_catalog"} and not checked["ok"]
    assert "load it on the Connections page" in checked["checks"][0]["words"]
    ok(client.post("/blades/Shop/refresh", json={}, headers=AUTH))  # the user's Load: its catalog
    checked = ok(client.post("/local-api/check", json={}, headers=AUTH))
    assert {c["state"] for c in checked["checks"]} == {"works"} and checked["ok"]
    (folder / "API.py").write_text(
        API_PY.replace("customer_id, city FROM", "customer_id, town FROM", 1), encoding="utf-8"
    )
    checked = ok(client.post("/local-api/check", json={}, headers=AUTH))
    differs = [c for c in checked["checks"] if c["state"] == "differs"]
    assert differs and "customers has no column town" in differs[0]["words"]


SANDBOX_API = '''\
# /// swissarmybench-api
# name = "Cities API"
# description = ""
# target = "aws_lambda"
# base_path = ""
# ///
from sab_api import connection, endpoint, records


@endpoint("GET", "/cities")
def cities() -> list[str]:
    """The customers' cities, from the sandbox's own copy."""
    return sorted({row["city"] for row in records(connection("Sandbox").read("customers"))})
'''


def test_an_export_with_rows_reads_its_own_copy_never_an_older_exports(
    shop: tuple[TestClient, Path], tmp_path: Path
) -> None:
    """connection("Sandbox") in an export works on a copy of its bundle in the temporary folder. The copy was
    one fixed name, made only when not there: an export made again (or another project's, on the same
    computer) silently answered an older export's rows (found building the field service test app,
    2026-11-22). Now the working copy is the bundle's own."""
    client, folder = shop
    (folder / "API.py").write_text(SANDBOX_API, encoding="utf-8")
    temp = tmp_path / "platform-tmp"
    temp.mkdir()
    script = """
        import json, lambda_function
        out = lambda_function.handler({"httpMethod": "GET", "path": "/cities"}, None)
        print(json.dumps([out["statusCode"], json.loads(out["body"])]))
    """
    done = ok(client.post("/local-api/export", json={"rows": True}, headers=AUTH))
    place = Path(done["folder"])
    assert done["sandbox"] is True and (place / "data" / "sandbox.duckdb").is_file()
    assert _run(place, script, env={"TMPDIR": str(temp)}) == [200, ["Shelbyville", "Springfield"]]
    assert _run(place, script, env={"TMPDIR": str(temp)}) == [200, ["Shelbyville", "Springfield"]]
    assert len(list(temp.glob("sab_sandbox_*.duckdb"))) == 1  # the same export: the same working copy
    # The sandbox changes and the API is exported again: its run answers the new rows.
    edit = {
        "table": "customers",
        "op": "update",
        "where": {"customer_id": 2},
        "values": {"city": "Ogdenville"},
    }
    ok(client.post("/sandbox/edit", json=edit, headers=AUTH))
    ok(client.post("/local-api/export", json={"rows": True}, headers=AUTH))
    assert _run(place, script, env={"TMPDIR": str(temp)}) == [200, ["Ogdenville", "Springfield"]]
    assert len(list(temp.glob("sab_sandbox_*.duckdb"))) == 2
    # A place of the host's own choosing is still taken as it is.
    own = tmp_path / "own.duckdb"
    assert _run(place, script, env={"SAB_SANDBOX_PATH": str(own), "TMPDIR": str(temp)})[0] == 200
    assert own.is_file()
