"""Add API (docs/ideas.md, "Add API"): an OpenAPI document (2.0 or 3.x) or a form, made into API_<name>.py
and a "Python (your own code)" connection. Made-up specs against made-up services on 127.0.0.1
(tests/api_standins.py); the made file is run in a plain Python, without this app."""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from starlette.testclient import TestClient

import swissarmybench as sab
from swissarmybench.client import sql_cell
from swissarmybench.domain import api_clients, apis
from swissarmybench.server.app import create_app
from swissarmybench.services.apis import Apis
from swissarmybench.settings import Settings
from tests import api_standins as standin
from tests.api_standins import Service
from tests.conftest import AGENT, AUTH
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture
def service() -> Iterator[Service]:
    running = Service().start()
    yield running
    running.stop()


HAS_YAML = importlib.util.find_spec("yaml") is not None


def spec_of(service: Service, auth: dict[str, Any] | None = None) -> apis.Spec:
    spec = apis.parse_spec(service.openapi(), service.url + "/openapi.json")
    return dataclasses.replace(spec, auth=apis.check_auth(auth)) if auth is not None else spec


# ===== reading a document =====


def test_an_openapi_3_document_reads_into_operations_tables_and_its_auth(service: Service) -> None:
    spec = spec_of(service)
    assert (spec.title, spec.version, spec.source) == ("Orders", "1.0", "OpenAPI 3.0.3")
    assert spec.base_url == service.url + "/v1"  # a relative server, against where the document came from
    assert [(o.method, o.path, o.name) for o in spec.operations] == [
        ("GET", "/orders", "list_orders"),
        ("POST", "/orders", "create_order"),
        ("GET", "/orders/{order_id}", "get_order"),
        ("GET", "/clients", "list_clients"),
        ("GET", "/regions", "list_regions"),
    ]
    listed = spec.operations[0]
    assert listed.table and listed.rows_at == "items" and listed.readable
    assert listed.columns == (("order_id", "integer"), ("amount", "number"), ("status", "string"))
    assert [(p.name, p.python, p.place, p.required) for p in listed.parameters] == [
        ("status", "status", "query", False),
        ("pageToken", "page_token", "query", False),
    ]
    assert listed.paging() == {"token": "pageToken"}
    assert spec.operations[1].body == "json" and spec.operations[1].body_required
    assert not spec.operations[2].readable  # it needs an order_id
    assert spec.operations[3].paging() == {"token": "cursor"} and spec.operations[4].paging() == {
        "page": "page"
    }
    # The tables: each readable GET under its path's words, in its first tag's schema.
    assert spec.to_json()["tables"] == [
        {"table": "orders", "schema": "sales", "operation": "list_orders"},
        {"table": "clients", "schema": "sales", "operation": "list_clients"},
        {"table": "regions", "schema": "api", "operation": "list_regions"},
    ]
    assert spec.auth == apis.Auth("api_key", {"in": "header", "name": "x-functions-key"})


def test_a_swagger_2_document_reads_the_same_way(service: Service) -> None:
    spec = apis.parse_spec(service.swagger())
    assert spec.source == "Swagger 2.0" and spec.base_url == service.url + "/v1"
    assert spec.auth.type == "basic"
    made = {o.name: o for o in spec.operations}
    assert made["list_orders"].table and made["list_orders"].rows_at == "items"
    assert made["list_orders"].columns == (("order_id", "integer"), ("amount", "number"))
    assert made["create_order"].body == "json" and made["create_order"].body_required
    assert [p.type for p in made["get_order"].parameters] == ["integer"]


@pytest.mark.parametrize(
    ("scheme", "auth"),
    [
        (
            {"type": "apiKey", "in": "cookie", "name": "session"},
            apis.Auth("api_key", {"in": "cookie", "name": "session"}),
        ),
        ({"type": "http", "scheme": "bearer"}, apis.Auth("bearer")),
        ({"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}, apis.Auth("jwt", {"mode": "token"})),
        ({"type": "http", "scheme": "basic"}, apis.Auth("basic")),
        (
            {
                "type": "oauth2",
                "flows": {
                    "clientCredentials": {
                        "tokenUrl": "https://login.example.com/t",
                        "scopes": {"a": "", "b": ""},
                    }
                },
            },
            apis.Auth(
                "oauth2",
                {"flow": "client_credentials", "token_url": "https://login.example.com/t", "scopes": "a b"},
            ),
        ),
        (
            {
                "type": "oauth2",
                "flows": {
                    "authorizationCode": {
                        "authorizationUrl": "https://a.example.com/a",
                        "tokenUrl": "https://a.example.com/t",
                        "scopes": {},
                    }
                },
            },
            apis.Auth(
                "oauth2",
                {
                    "flow": "authorization_code",
                    "token_url": "https://a.example.com/t",
                    "authorize_url": "https://a.example.com/a",
                },
            ),
        ),
        # An AWS API Gateway export: IAM, and a Cognito user pool.
        (
            {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "x-amazon-apigateway-authtype": "awsSigv4",
            },
            apis.Auth("sigv4", {"region": "us-east-1"}),
        ),
        (
            {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "x-amazon-apigateway-authorizer": {"type": "cognito_user_pools"},
            },
            apis.Auth("jwt", {"mode": "token"}),
        ),
        # Google's: a Firebase project's issuer, and a service account's.
        (
            {
                "type": "oauth2",
                "flow": "implicit",
                "authorizationUrl": "",
                "x-google-issuer": "https://securetoken.google.com/made-up",
            },
            apis.Auth("firebase", {"mode": "password"}),
        ),
        (
            {
                "type": "oauth2",
                "flow": "implicit",
                "authorizationUrl": "",
                "x-google-issuer": "robot@made-up.iam.gserviceaccount.com",
            },
            apis.Auth("google"),
        ),
    ],
)
def test_the_documents_security_scheme_picks_the_auth_type(scheme: dict[str, Any], auth: apis.Auth) -> None:
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "Made up"},
        "servers": [{"url": "https://{host}.example.com", "variables": {"host": {"default": "api"}}}],
        "components": {"securitySchemes": {"it": scheme}},
        "paths": {
            "/things": {"get": {"security": [{"it": []}], "responses": {"200": {"description": "ok"}}}}
        },
    }
    spec = apis.parse_spec(doc)
    assert spec.auth == auth and spec.base_url == "https://api.example.com"
    assert spec.operations[0].name == "get_things"


def test_documents_that_cannot_be_read_say_why() -> None:
    with pytest.raises(apis.ApiError, match="not an OpenAPI document"):
        apis.parse_spec({"info": {}})
    with pytest.raises(apis.ApiError, match="no paths"):
        apis.parse_spec({"openapi": "3.0.0", "paths": {}})
    with pytest.raises(apis.ApiError, match="not JSON"):
        apis.read_json("{nope")
    assert apis.looks_like_yaml("openapi: 3.0.0\npaths: {}\n") and not apis.looks_like_yaml(
        '{"openapi": "3"}'
    )


def test_the_form_reads_into_the_same_spec() -> None:
    spec = apis.parse_form(
        {
            "title": "Shop",
            "base_url": "https://shop.example.com/api/",
            "auth": {"type": "api_key", "in": "query", "name": "code"},
            "endpoints": [
                {"method": "GET", "path": "/products", "parameters": "category, page", "table": True},
                {"method": "get", "path": "products/{sku}", "parameters": "sku, fields*"},
                {"method": "POST", "path": "/products", "table": False},
            ],
        }
    )
    assert spec.base_url == "https://shop.example.com/api" and spec.source == "form"
    first, one, made = spec.operations
    assert (first.name, first.table, first.readable, first.paging()) == (
        "get_products",
        True,
        True,
        {"page": "page"},
    )
    assert one.path == "/products/{sku}" and one.name == "get_products_by_sku"
    assert [(p.name, p.place, p.required) for p in one.parameters] == [
        ("sku", "path", True),
        ("fields", "query", True),
    ]
    assert made.body == "json" and made.name == "post_products"
    assert spec.auth.get("in") == "query"
    for bad, why in (
        ({"base_url": "ftp://x", "endpoints": [{"path": "/a"}]}, "http or https"),
        ({"base_url": "https://<app>.azurewebsites.net/api", "endpoints": [{"path": "/a"}]}, "Fill in"),
        ({"base_url": "https://x.example.com", "endpoints": []}, "Add an endpoint"),
        ({"base_url": "https://x.example.com", "endpoints": [{"method": "FETCH", "path": "/a"}]}, "method"),
        ({"base_url": "https://x.example.com", "endpoints": [{"path": "/a b"}]}, "one word"),
    ):
        with pytest.raises(apis.ApiError, match=why):
            apis.parse_form(bad)


def test_names_variables_and_auth_settings() -> None:
    names = apis.names_for("Orders API")
    assert (names.connection, names.module, names.cls, names.prefix, names.file) == (
        "Orders API",
        "API_Orders",
        "OrdersApi",
        "ORDERS",
        "API_Orders.py",
    )
    assert apis.names_for("my function app").module == "API_my_function_app"
    assert apis.names_for("2024 sales").cls == "N2024SalesApi"

    def reads(auth: dict[str, Any]) -> list[tuple[str, bool, bool]]:
        return [(v.name, v.required, v.secret) for v in apis.variables(apis.check_auth(auth), "SHOP")]

    assert reads({"type": "none"}) == []
    assert reads({"type": "api_key"}) == [("SHOP_API_KEY", True, True)]
    assert reads({"type": "basic"}) == [("SHOP_USERNAME", True, False), ("SHOP_PASSWORD", True, True)]
    assert reads(
        {"type": "oauth2", "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"}
    ) == [("SHOP_TENANT", True, False), ("SHOP_CLIENT_ID", True, False), ("SHOP_CLIENT_SECRET", True, True)]
    assert reads({"type": "oauth2", "flow": "device_code"})[-1] == ("SHOP_CLIENT_SECRET", False, True)
    assert reads({"type": "jwt", "mode": "signed", "algorithm": "RS256"}) == [
        ("SHOP_PRIVATE_KEY", True, True)
    ]
    assert reads({"type": "sigv4"}) == [
        ("AWS_ACCESS_KEY_ID", True, False),
        ("AWS_SECRET_ACCESS_KEY", True, True),
        ("AWS_SESSION_TOKEN", False, True),
    ]
    assert reads({"type": "google"}) == [("SHOP_SERVICE_ACCOUNT_KEY", True, True)]
    assert [n for n, _, _ in reads({"type": "firebase"})] == [
        "SHOP_FIREBASE_API_KEY",
        "SHOP_EMAIL",
        "SHOP_PASSWORD",
    ]
    for bad, why in (
        ({"type": "magic"}, "not an auth type"),
        ({"type": "api_key", "colour": "red"}, "no setting 'colour'"),
        ({"type": "api_key", "in": "body"}, "is one of"),
        ({"type": "oauth2", "token_url": "login.example.com"}, "http or https"),
        ({"type": "jwt", "mode": "signed", "lifetime": "soon"}, "number of seconds"),
    ):
        with pytest.raises(apis.ApiError, match=why):
            apis.check_auth(bad)


def test_the_presets_fill_the_form_and_say_where_the_document_is() -> None:
    presets = {p["id"]: p for p in apis.choices()["presets"]}
    azure = presets["azure"]
    assert azure["urls"][0]["url"] == "https://<app>.azurewebsites.net/api"
    assert [a["label"] for a in azure["auths"]] == ["Function key", "Entra ID (app registration)"]
    assert azure["auths"][0] == {
        "label": "Function key",
        "type": "api_key",
        "in": "header",
        "name": "x-functions-key",
    }
    assert "{tenant}" in azure["auths"][1]["token_url"]
    assert apis.spec_urls("azure", "https://made-up.azurewebsites.net/api") == [
        "https://made-up.azurewebsites.net/api/openapi/v3.json",
        "https://made-up.azurewebsites.net/api/swagger.json",
        "https://made-up.azurewebsites.net/api/openapi/v2.json",
    ]
    assert apis.spec_urls("azure", "https://<app>.azurewebsites.net/api") == []  # not filled in yet
    aws = presets["aws"]
    assert [a["type"] for a in aws["auths"]] == ["none", "api_key", "jwt", "sigv4"]
    assert (
        aws["auths"][1]["name"] == "x-api-key"
        and apis.spec_urls("aws", "https://x.lambda-url.us-east-1.on.aws") == []
    )
    google = presets["google"]
    assert [a["type"] for a in google["auths"]] == ["firebase", "google"]
    assert [u["label"] for u in google["urls"]] == ["Cloud Functions", "Cloud Run"]
    # Every preset's auth is one the form takes as it is.
    for preset in presets.values():
        for auth in preset["auths"]:
            apis.check_auth({k: v for k, v in auth.items() if k != "label"})


# ===== the made file =====


def test_the_made_file_is_marked_typed_documented_and_holds_no_secret(service: Service) -> None:
    spec = spec_of(service)
    names = apis.names_for("Orders")
    text = api_clients.write(spec, names)
    compile(text, "API_Orders.py", "exec")
    mark = api_clients.read_mark(text)
    assert mark is not None and mark["class"] == "OrdersApi" and mark["source"] == "OpenAPI 3.0.3"
    assert api_clients.is_made(text) and not api_clients.is_made("print('mine')\n")
    assert "def list_orders(\n" in text and "page_token: Optional[str] = None" in text
    assert "def get_order(self, order_id: int) -> Any:" in text
    assert "def create_order(self, body: Any) -> Any:" in text
    assert '"""The orders\n\n        GET /orders' in text
    assert "(pageToken) The query parameter pageToken." in text
    # Standard library only, and only what its auth needs.
    imported = {n.names[0].name for n in ast.parse(text).body if isinstance(n, ast.Import)}
    assert imported == {"json", "os", "time", "urllib.error", "urllib.parse", "urllib.request"}
    assert 'os.environ.get("ORDERS_API_KEY")' in text
    for secret in standin.SECRETS:
        assert secret not in text


def test_a_spec_can_never_write_code() -> None:
    evil = '"""\nimport os; os.system("echo pwned")\n"""\\'
    doc = {
        "openapi": "3.0.0",
        "info": {"title": f"Evil{evil}", "version": evil, "description": evil},
        "servers": [{"url": f"https://evil.example.com/{evil}"}],
        "paths": {
            f"/x{evil}": {
                "get": {
                    "operationId": f"go{evil}",
                    "summary": evil,
                    "description": evil,
                    "tags": [evil],
                    "parameters": [
                        {"name": f"p{evil}", "in": "query", "description": evil, "schema": {"enum": [evil]}}
                    ],
                    "responses": {
                        "200": {
                            "description": "",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"type": "object", "properties": {evil: {"type": "string"}}},
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }
    spec = apis.parse_spec(doc)
    text = api_clients.write(spec, apis.names_for(spec.title))
    tree = ast.parse(text)
    # Only the docstring, imports and the class at the top; in the class only its docstring, assignments
    # of literals, classes and functions; and no call of os.system anywhere.
    assert all(isinstance(n, ast.Expr | ast.Import | ast.ImportFrom | ast.ClassDef) for n in tree.body)
    assert sum(isinstance(n, ast.Expr) for n in tree.body) == 1
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "system":
            raise AssertionError("the spec wrote code")


def test_re_import_says_what_changes(service: Service) -> None:
    names = apis.names_for("Orders")
    before = api_clients.write(spec_of(service), names)
    doc = service.openapi()
    del doc["paths"]["/regions"]
    doc["paths"]["/orders"]["get"]["parameters"].append(
        {"name": "since", "in": "query", "schema": {"type": "string"}}
    )
    doc["paths"]["/stores"] = {
        "get": {"operationId": "listStores", "responses": {"200": {"description": "ok"}}}
    }
    after_spec = dataclasses.replace(
        apis.parse_spec(doc, service.url + "/openapi.json"), auth=apis.check_auth({"type": "bearer"})
    )
    after = api_clients.write(after_spec, names)
    changes = apis.changes(
        api_clients.methods(before),
        api_clients.methods(after),
        api_clients.read_mark(before) or {},
        api_clients.mark(after_spec, names),
    )
    assert changes.added == ("list_stores",) and changes.removed == ("list_regions",)
    assert changes.changed == ("list_orders",) and changes.same == 3
    assert changes.auth and not changes.base_url and changes.any


def test_the_exporter_pastes_a_made_file_inline(service: Service, tmp_path: Path) -> None:
    """For the exporter (an API_<name>.py beside a notebook travels inside the exported script)."""
    text = api_clients.write(spec_of(service, {"type": "none"}), apis.names_for("Orders"))
    (tmp_path / "API_Orders.py").write_text(text, encoding="utf-8")
    (tmp_path / "API_Mine.py").write_text("x = 1\n", encoding="utf-8")  # not made by Add API: left alone
    from swissarmybench.adapters.apis import ApiFiles, ApiLibrary, SpecSource

    library = ApiLibrary(tmp_path / "library")
    apis_service = Apis(None, ApiFiles(), SpecSource(), None, library, None, lambda: "")  # type: ignore[arg-type]
    cells = ["from API_Orders import OrdersApi\nimport API_Mine", "%time x = 1", "import API_Orders"]
    found = apis_service.inline(str(tmp_path), cells)
    assert [f["module"] for f in found] == ["API_Orders"]
    code = found[0]["code"]
    assert code.startswith("# Made by Swiss Army Bench") and code.rstrip().endswith(
        '_sys.modules["API_Orders"] = API_Orders'
    )
    base = service.url + "/v1"
    script = code + f"\nfrom API_Orders import OrdersApi\nprint(len(OrdersApi({base!r}).list_orders()))\n"
    ran = subprocess.run(  # noqa: S603 (this Python, the made code under test)
        [sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=60, cwd=tmp_path / ".."
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip() == "25"


# ===== the made file in a plain Python, against the stand-in, with each auth type =====


def _keys() -> dict[str, Any]:
    """Made-up key pairs for the signed JWTs and the Google service account (cryptography, in the tests)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa

    def pem(key: Any) -> str:
        return str(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            ).decode()
        )

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ec_key = ec.generate_private_key(ec.SECP256R1())
    return {"rsa": (rsa_key, pem(rsa_key)), "ec": (ec_key, pem(ec_key))}


PLAIN = [sys._base_executable, "-I", "-S"]  # type: ignore[attr-defined]  # no site-packages: no pandas, no keyring

RUN = """
import json, sys, threading, urllib.request
sys.path.insert(0, sys.argv[1])
from API_Orders import OrdersApi
api = OrdersApi(backoff=0.01)
def browse(url):  # the user's browser, stood in for: the sign-in page sends it back at once
    threading.Thread(target=urllib.request.urlopen, args=(url,), daemon=True).start()
api._open_browser = browse
orders = api.list_orders()
rows = orders.to_dict("records") if hasattr(orders, "to_dict") else orders
print(json.dumps({
    "kind": type(orders).__name__,
    "orders": len(rows),
    "first": rows[0],
    "open": len(api.list_orders(status="open")),
    "four": len(api.list_orders(max_rows=4)),
    "one": api.get_order(7),
    "made": api.create_order({"amount": 1.5}),
    "clients": len(api.list_clients()),
    "regions": len(api.read("regions")),
    "tables": sorted({t["table"] for t in api.tables()}),
    "repr": repr(api),
}))
"""

CASES: list[tuple[str, str, dict[str, Any], dict[str, str]]] = [
    ("none", "none", {"type": "none"}, {}),
    (
        "api key header",
        "api_key_header",
        {"type": "api_key", "in": "header", "name": "X-Api-Key"},
        {"ORDERS_API_KEY": standin.API_KEY},
    ),
    (
        "api key query",
        "api_key_query",
        {"type": "api_key", "in": "query", "name": "X-Api-Key"},
        {"ORDERS_API_KEY": standin.API_KEY},
    ),
    (
        "api key cookie",
        "api_key_cookie",
        {"type": "api_key", "in": "cookie", "name": "X-Api-Key"},
        {"ORDERS_API_KEY": standin.API_KEY},
    ),
    ("bearer", "bearer", {"type": "bearer"}, {"ORDERS_TOKEN": standin.BEARER}),
    (
        "basic",
        "basic",
        {"type": "basic"},
        {"ORDERS_USERNAME": standin.USER, "ORDERS_PASSWORD": standin.PASSWORD},
    ),
    (
        "oauth2 client credentials",
        "oauth2",
        {
            "type": "oauth2",
            "flow": "client_credentials",
            "token_url": "{url}/oauth/{tenant}/token",
            "scopes": "api://made-up/.default",
        },
        {
            "ORDERS_TENANT": standin.TENANT,
            "ORDERS_CLIENT_ID": standin.CLIENT_ID,
            "ORDERS_CLIENT_SECRET": standin.CLIENT_SECRET,
        },
    ),
    (
        "oauth2 authorization code (PKCE)",
        "oauth2",
        {
            "type": "oauth2",
            "flow": "authorization_code",
            "authorize_url": "{url}/oauth/authorize",
            "token_url": "{url}/oauth/t/token",
        },
        {"ORDERS_CLIENT_ID": standin.CLIENT_ID},
    ),
    (
        "oauth2 device code",
        "oauth2",
        {
            "type": "oauth2",
            "flow": "device_code",
            "device_url": "{url}/oauth/device",
            "token_url": "{url}/oauth/t/token",
        },
        {"ORDERS_CLIENT_ID": standin.CLIENT_ID},
    ),
    ("jwt ready token", "jwt_token", {"type": "jwt", "mode": "token"}, {"ORDERS_TOKEN": standin.BEARER}),
    (
        "jwt login",
        "jwt_login",
        {"type": "jwt", "mode": "login", "login_url": "/login"},
        {"ORDERS_USERNAME": standin.USER, "ORDERS_PASSWORD": standin.PASSWORD},
    ),
    (
        "jwt HS256",
        "jwt_signed",
        {"type": "jwt", "mode": "signed", "algorithm": "HS256", "issuer": "made-up-issuer"},
        {"ORDERS_JWT_SECRET": standin.JWT_SECRET},
    ),
    (
        "jwt RS256",
        "jwt_signed",
        {"type": "jwt", "mode": "signed", "algorithm": "RS256", "issuer": "made-up-issuer"},
        {"ORDERS_PRIVATE_KEY": "rsa"},
    ),
    (
        "jwt ES256",
        "jwt_signed",
        {"type": "jwt", "mode": "signed", "algorithm": "ES256", "issuer": "made-up-issuer"},
        {"ORDERS_PRIVATE_KEY": "ec"},
    ),
    (
        "aws sigv4",
        "sigv4",
        {"type": "sigv4", "region": "eu-west-2", "service": "execute-api"},
        {"AWS_ACCESS_KEY_ID": standin.AWS_KEY_ID, "AWS_SECRET_ACCESS_KEY": standin.AWS_SECRET},
    ),
    ("google identity token", "google", {"type": "google"}, {"ORDERS_SERVICE_ACCOUNT_KEY": "rsa"}),
    (
        "firebase email and password",
        "firebase",
        {
            "type": "firebase",
            "mode": "password",
            "sign_in_url": "{url}/firebase/signin",
            "refresh_url": "{url}/firebase/refresh",
        },
        {
            "ORDERS_FIREBASE_API_KEY": standin.FIREBASE_WEB_KEY,
            "ORDERS_EMAIL": standin.EMAIL,
            "ORDERS_PASSWORD": standin.PASSWORD,
        },
    ),
    (
        "firebase ready token",
        "firebase",
        {"type": "firebase", "mode": "token"},
        {"ORDERS_ID_TOKEN": "issued"},
    ),
]


@pytest.mark.parametrize(("label", "mode", "auth", "env"), CASES, ids=[c[0] for c in CASES])
def test_the_made_file_runs_in_a_plain_python_with_each_auth_type(
    label: str, mode: str, auth: dict[str, Any], env: dict[str, str], service: Service, tmp_path: Path
) -> None:
    service.mode = mode
    auth = {k: v.replace("{url}", service.url) for k, v in auth.items()}
    environ = {k: v for k, v in os.environ.items() if not k.startswith(("ORDERS_", "AWS_"))}
    environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
    python = PLAIN
    for name, value in env.items():
        if value in ("rsa", "ec"):  # a key pair: the private key to the client, the public one to the service
            key, pem = _keys()[value]
            service.public_key = key.public_key()
            value = pem
            if name == "ORDERS_SERVICE_ACCOUNT_KEY":
                value = json.dumps(
                    {
                        "type": "service_account",
                        "client_email": "robot@made-up.iam.gserviceaccount.com",
                        "private_key_id": "made-up-key-id",
                        "private_key": pem,
                        "token_uri": service.url + "/google/token",
                    }
                )
            python = [sys.executable, "-I"]  # RS256 and ES256: cryptography, in a Python that has it
        elif value == "issued":
            value = service.issue("fid")
        environ[name] = value
    if mode == "none":
        python = [sys.executable, "-I"]  # with pandas: the rows come back as a DataFrame
    spec = spec_of(service, auth)
    (tmp_path / "API_Orders.py").write_text(
        api_clients.write(spec, apis.names_for("Orders")), encoding="utf-8"
    )
    ran = subprocess.run(  # noqa: S603 (a plain Python, the made code under test)
        [*python, "-c", RUN, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=90,
        env=environ,
        cwd=tmp_path,
    )
    assert ran.returncode == 0, ran.stderr[-3000:]
    got = json.loads(ran.stdout.strip().splitlines()[-1])
    assert got["orders"] == 25 and got["open"] == 17 and got["four"] == 4  # three pages by token; cut at 4
    assert got["first"] == {"order_id": 1, "amount": 2.5, "status": "open"}
    assert got["kind"] == ("DataFrame" if python[0] == sys.executable else "list")
    assert got["one"]["order_id"] == 7 and got["made"] == {"order_id": 1000, "amount": 1.5}
    assert got["clients"] == 3 and got["regions"] == 7  # Link header pages; page numbers
    assert got["tables"] == ["clients", "orders", "regions"]
    assert got["repr"] == f"OrdersApi('{service.url}/v1')"
    for secret in standin.SECRETS:
        assert secret not in ran.stdout and secret not in ran.stderr
    if mode in ("jwt_login", "firebase") and "ready" not in label:
        assert service.logins >= 1
    if mode == "jwt_login":
        assert service.logins > 1  # its token ran out (a 401): it logged in again
    if label == "oauth2 device code":
        assert "MADE-UP" in ran.stderr  # the code to enter, said to the user
    if mode == "sigv4":
        assert all(
            s["headers"]["authorization"].startswith("AWS4-HMAC-SHA256 Credential=") for s in service.seen
        )


def test_retries_wait_on_429_and_5xx_and_errors_say_where(service: Service, tmp_path: Path) -> None:
    spec = apis.parse_form(
        {
            "title": "Orders",
            "base_url": service.url + "/v1",
            "endpoints": [
                {"method": "GET", "path": "/flaky", "table": True},
                {"method": "GET", "path": "/orders/{order_id}"},
                {"method": "GET", "path": "/products", "table": True},
            ],
        }
    )
    (tmp_path / "API_Orders.py").write_text(
        api_clients.write(spec, apis.names_for("Orders")), encoding="utf-8"
    )
    script = (
        "import sys, json\nsys.path.insert(0, sys.argv[1])\nfrom API_Orders import OrdersApi\n"
        "api = OrdersApi(backoff=0.01)\nflaky = api.get_flaky()\n"
        "try:\n    api.get_orders_by_order_id(999)\n"
        "except OrdersApi.Error as e:\n    missing = [e.status, str(e)]\n"
        "print(json.dumps({'flaky': flaky, 'missing': missing, 'tables': api.tables()}))"
    )
    command = [*PLAIN, "-c", script, str(tmp_path)]
    ran = subprocess.run(command, capture_output=True, text=True, timeout=60)  # noqa: S603 (a plain Python)
    assert ran.returncode == 0, ran.stderr
    got = json.loads(ran.stdout)
    assert got["flaky"] == [{"ok": True}] and service.flaky == 3  # a 503, waited for, the rows; the probe
    assert got["missing"][0] == 404
    assert got["missing"][1] == f'GET {service.url}/v1/orders/999 answered 404: {{"error": "No such order"}}'
    # The form's tables: columns asked of the API itself (one row), since no schema says them.
    assert {(t["table"], t["column"], t["type"]) for t in got["tables"]} >= {
        ("products", "sku", "string"),
        ("products", "price", "number"),
    }


def test_sigv4_matches_aws_own_example(tmp_path: Path) -> None:
    """AWS's Signature Version 4 test suite, get-vanilla: its published signature, standard library only."""
    spec = apis.parse_form(
        {"base_url": "https://example.amazonaws.com", "auth": {"type": "sigv4"}, "endpoints": [{"path": "/"}]}
    )
    (tmp_path / "API_Vanilla.py").write_text(
        api_clients.write(spec, apis.names_for("Vanilla")), encoding="utf-8"
    )
    sys.path.insert(0, str(tmp_path))
    try:
        import datetime

        import API_Vanilla  # type: ignore[import-not-found]

        client = API_Vanilla.VanillaApi(
            access_key_id="AKIDEXAMPLE", secret_access_key="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
        )
        headers: dict[str, str] = {}
        when = datetime.datetime(2015, 8, 30, 12, 36, 0, tzinfo=datetime.UTC)
        client._sigv4("GET", "https://example.amazonaws.com/", headers, None, when, "service")
        assert headers["Authorization"] == (
            "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31"
        )
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("API_Vanilla", None)


# ===== the app: Add API, its connection, its catalog, Open as grid =====


def test_add_api_writes_the_client_and_its_connection_in_one_step(
    client: TestClient, service: Service, tmp_path: Path
) -> None:
    service.mode = "api_key_header"
    service.key_name = "x-functions-key"
    choices = client.get("/apis/choices", headers=AGENT).json()
    assert [t["id"] for t in choices["auth_types"]] == list(apis.AUTH_TYPES)
    assert [p["id"] for p in choices["presets"]] == ["azure", "aws", "google"]
    # This computer's library, whatever project is open (the owner, 2026-11-17).
    project = tmp_path / "state" / "library" / "apis" / "Orders"
    body = {"spec_url": service.url + "/openapi.json"}

    # Preview: what it would write, written nowhere.
    seen = client.post("/apis/preview", json=body, headers=AGENT)
    assert seen.status_code == 200, seen.text
    plan = seen.json()
    assert (plan["connection"], plan["module"], plan["class"]) == ("Orders", "API_Orders", "OrdersApi")
    assert plan["path"] == str(project / "API_Orders.py") and not plan["exists"] and plan["changes"] is None
    assert [v["name"] for v in plan["variables"]] == ["ORDERS_URL", "ORDERS_API_KEY"]
    assert [t["table"] for t in plan["spec"]["tables"]] == ["orders", "clients", "regions"]
    assert not (project / "API_Orders.py").exists()

    # Add: the file, and the connection with its key saved on this computer.
    keyed = body | {
        "variables": [{"name": "ORDERS_API_KEY", "from": "keyring"}],
        "secrets": {"ORDERS_API_KEY": standin.API_KEY},
        "row_limit": 10,
    }
    added = client.post("/apis", json=keyed, headers=AGENT)
    assert added.status_code == 200, added.text
    assert added.json()["saved"]["connection"] == "python" and added.json()["saved"]["secrets"] == {
        "ORDERS_API_KEY": True
    }
    text = (project / "API_Orders.py").read_text(encoding="utf-8")
    assert api_clients.is_made(text) and standin.API_KEY not in text
    form = client.get("/connections/Orders", headers=AGENT).json()
    assert form["read"] is None and form["catalog"] is None  # no tables until a web call is switched on
    assert (
        f'spec_from_file_location("API_Orders", {json.dumps(str(project / "API_Orders.py"))})' in form["code"]
    )
    assert [r["name"] for r in form["reads"]] == ["ORDERS_URL", "ORDERS_API_KEY"]
    # A web call blade per operation, beside it in the library; not one is a table until switched on.
    operations = ("list_orders", "create_order", "get_order", "list_clients", "list_regions")
    assert set(added.json()["web_calls"]) == {f"Orders.{o}" for o in operations}
    assert (project / "orders_list_orders.blade.py").is_file() and (project / "openapi.json").is_file()
    assert "Orders" not in {c["name"] for c in client.get("/connections", headers=AUTH).json()["connections"]}
    none_yet = client.post("/connections/Orders/tables", json={}, headers=AGENT)
    assert none_yet.status_code == 400 and "no List the tables" in none_yet.text

    # Return as table on list_orders: the one gate to SQL (its records at $.items, every page read).
    on = client.put(
        "/apis/Orders/calls/list_orders", json={"as_table": True, "records": "$.items"}, headers=AGENT
    )
    assert on.status_code == 200, on.text
    assert on.json()["sql_name"] == "[Orders].list_orders"
    form = client.get("/connections/Orders", headers=AGENT).json()
    assert "api.table(" in form["read"]["command"] and "api = conn" in form["catalog"]["command"]
    tables = client.post("/connections/Orders/tables", json={}, headers=AGENT)
    assert tables.status_code == 200, tables.text
    assert [(t["schema"], t["table"], len(t["columns"])) for t in tables.json()["tables"]] == [
        ("", "list_orders", 3)
    ]
    columns = client.get(
        "/catalogs/Orders/columns", params={"schema": "", "table": "list_orders"}, headers=AUTH
    ).json()["columns"]
    assert [(c["column"], c["type"]) for c in columns] == [
        ("order_id", "BIGINT"),
        ("amount", "DOUBLE"),
        ("status", "VARCHAR"),
    ]
    opened = client.post(
        "/connections/Orders/open", json={"schema": "", "table": "list_orders"}, headers=AGENT
    )
    assert opened.status_code == 200, opened.text
    grid = client.get(f"/grids/{opened.json()['grid']}", headers=AUTH).json()
    assert grid["dataset"] == "list_orders" and grid["row_count"] == 10  # its Rows to open
    rows = client.get(
        f"/grids/{opened.json()['grid']}/rows", params={"start": 0, "end": 3}, headers=AUTH
    ).json()
    assert [r[0] for r in rows["rows"]] == [1, 2, 3]

    # No answer, and nothing on disk, holds the key.
    for path in ("/connections", "/connections/Orders", "/blades/Orders", "/blades/Orders/export"):
        assert standin.API_KEY not in client.get(path, headers=AUTH).text
    on_disk = "".join(p.read_text(errors="replace") for p in tmp_path.rglob("*") if p.is_file())
    assert standin.API_KEY not in on_disk and "API_Orders" in on_disk


def test_re_import_shows_the_changes_then_writes_and_keeps_the_mapping(
    client: TestClient, service: Service, tmp_path: Path
) -> None:
    service.mode = "api_key_header"
    service.key_name = "x-functions-key"
    body = {"spec": json.dumps(service.openapi()), "base_url": service.url + "/v1"}
    folder = tmp_path / "state" / "library" / "apis" / "Orders"
    mapping = [{"name": "ORDERS_API_KEY", "from": "keyring"}]
    first = client.post(
        "/apis",
        json=body | {"variables": mapping, "secrets": {"ORDERS_API_KEY": standin.API_KEY}},
        headers=AUTH,
    )
    assert first.status_code == 200, first.text
    doc = service.openapi()
    del doc["paths"]["/regions"]
    again = {**body, "spec": json.dumps(doc)}
    plan = client.post("/apis/preview", json=again, headers=AUTH).json()
    assert plan["exists"] and plan["connection_exists"]
    assert plan["changes"] == {
        "added": [],
        "removed": ["list_regions"],
        "changed": [],
        "same": 4,
        "auth": False,
        "base_url": False,
        "any": True,
    }
    assert "list_regions" in (folder / "API_Orders.py").read_text()  # not written by a preview
    done = client.post("/apis", json=again, headers=AUTH)
    assert done.status_code == 200, done.text
    assert "list_regions" not in (folder / "API_Orders.py").read_text()
    form = client.get("/connections/Orders", headers=AUTH).json()
    assert form["variables"] == mapping  # kept: the same connection, changed
    assert client.get("/blades/Orders.list_regions", headers=AUTH).status_code == 404  # its web call went
    assert client.get("/blades/Orders.list_orders", headers=AUTH).status_code == 200


def test_a_file_or_a_name_that_is_not_add_apis_is_never_taken(client: TestClient, tmp_path: Path) -> None:
    form = {
        "title": "Shop",
        "base_url": "https://shop.example.com",
        "endpoints": [{"path": "/products", "table": True}],
    }
    folder = tmp_path / "state" / "library" / "apis" / "Shop"
    folder.mkdir(parents=True)
    (folder / "API_Shop.py").write_text("# my own code\n", encoding="utf-8")
    taken = client.post("/apis", json={"form": form}, headers=AUTH)
    assert taken.status_code == 409 and "Add API did not make it" in taken.text
    assert (folder / "API_Shop.py").read_text() == "# my own code\n"
    other = {"name": "Shop", "kind": "other", "template": "python", "variable": "conn", "code": "conn = 1"}
    assert client.post("/connections", json=other, headers=AUTH).status_code == 200
    (folder / "API_Shop.py").unlink()
    taken = client.post("/apis", json={"form": form}, headers=AUTH)
    assert taken.status_code == 409 and "A connection is named Shop" in taken.text
    assert not (folder / "API_Shop.py").exists()
    for bad, status, why in (
        ({"folder": str(tmp_path)}, 400, "one way"),
        ({"form": form, "spec_url": "https://x.example.com/o.json"}, 400, "one way"),
        ({"spec_path": str(tmp_path / "missing.json")}, 404, "is not a file"),
        # YAML: read where PyYAML is (no paths: 400); where it is not, the missing-package answer (422, the
        # "Install PyYAML?" prompt's shape).
        ({"spec": "openapi: 3.0.0\npaths: {}\n"}, 400 if HAS_YAML else 422, "no paths|without PyYAML"),
    ):
        answer = client.post("/apis/preview", json=bad, headers=AUTH)
        assert answer.status_code == status and any(w in answer.text for w in why.split("|")), answer.text


def test_the_file_goes_in_this_computers_library(client: TestClient, tmp_path: Path) -> None:
    form = {
        "title": "Shop",
        "base_url": "https://shop.example.com",
        "endpoints": [{"path": "/products", "table": True}],
    }
    plan = client.post("/apis/preview", json={"form": form}, headers=AUTH).json()
    assert plan["path"] == str(tmp_path / "state" / "library" / "apis" / "Shop" / "API_Shop.py")


def test_try_it_reads_an_endpoints_first_rows_before_add_and_writes_nothing(
    client: TestClient, service: Service, tmp_path: Path
) -> None:
    service.mode = "api_key_header"
    service.key_name = "x-api-key"
    form = {
        "title": "Shop",
        "base_url": service.url + "/v1",
        "endpoints": [
            {"path": "/products", "table": True},
            {"path": "/orders/{order_id}", "table": True},
            {"path": "/orders", "method": "POST"},
            {"path": "/regions", "table": False},
        ],
    }
    auth = {"type": "api_key", "in": "header", "name": "x-api-key"}
    project = tmp_path / "shop"
    project.mkdir()
    body = {"form": form, "auth": auth, "folder": str(project)}
    names = [
        o["name"] for o in client.post("/apis/preview", json=body, headers=AUTH).json()["spec"]["operations"]
    ]
    assert names == ["get_products", "get_orders_by_order_id", "post_orders", "get_regions"]

    # The key typed for this try only: the rows come back, the key does not, and nothing is written.
    tried = client.post(
        "/apis/try",
        json=body | {"try": "get_products", "values": {"SHOP_API_KEY": standin.API_KEY}},
        headers=AUTH,
    )
    assert tried.status_code == 200, tried.text
    answer = tried.json()
    assert answer["table"] == "products" and answer["columns"] == ["sku", "price"]
    assert 0 < len(answer["rows"]) <= apis.TRY_ROWS
    assert standin.API_KEY not in tried.text
    assert not list(project.iterdir())
    assert client.get("/connections", headers=AUTH).json()["connections"] == []

    # No key typed, none on this computer: said by its variable's name.
    keyless = client.post("/apis/try", json=body | {"try": "get_products"}, headers=AUTH)
    assert keyless.status_code == 400 and "SHOP_API_KEY" in keyless.text and "under Sign in" in keyless.text
    # A wrong key: the service's own refusal, said.
    wrong = client.post(
        "/apis/try",
        json=body | {"try": "get_products", "values": {"SHOP_API_KEY": "made-up-wrong"}},
        headers=AUTH,
    )
    assert wrong.status_code == 400 and "401" in wrong.text and "made-up-wrong" not in wrong.text
    for operation, why in (
        ("get_orders_by_order_id", "needs a value"),
        ("post_orders", "only a GET"),
        ("get_regions", "Read as a table"),
        ("list_nothing", "There is no list_nothing"),
        ("", "Name the operation"),
    ):
        refused = client.post("/apis/try", json=body | {"try": operation}, headers=AUTH)
        assert refused.status_code == 400 and why in refused.text, refused.text


# ===== in a notebook: the connection is the client; sab.read and a SQL cell =====

TOKEN = "add-api-token"


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
    monkeypatch.setenv("SWISSARMYBENCH_INFO", str(info))
    monkeypatch.setenv("SWISSARMYBENCH_OPEN", "0")
    monkeypatch.setattr(sql_cell, "_connections", {})
    yield port
    server.should_exit = True
    thread.join(10)


def test_in_a_notebook_the_connection_is_the_client_and_a_sql_cell_reads_its_tables(
    live: int, service: Service, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import urllib.request

    service.mode = "bearer"
    monkeypatch.setenv("ORDERS_TOKEN", standin.BEARER)
    body = {"spec_url": service.url + "/openapi.json", "auth": {"type": "bearer"}}

    def send(method: str, path: str, payload: Any) -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{live}{path}",
            data=json.dumps(payload).encode(),
            method=method,
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=60) as answer:  # noqa: S310 (loopback)
            assert answer.status == 200

    send("POST", "/apis", body)
    # Return as table on three web calls: they are the API's tables, and nothing else is.
    send("PUT", "/apis/Orders/calls/list_orders", {"as_table": True, "records": "$.items"})
    send("PUT", "/apis/Orders/calls/list_clients", {"as_table": True, "records": "$"})
    send("PUT", "/apis/Orders/calls/list_regions", {"as_table": True, "records": "$"})
    conn = sab.connection("Orders")
    assert type(conn).__name__ == "OrdersApi" and conn.get_order(3)["amount"] == 7.5
    # A web call blade, run here: through its API blade, its inputs its settings.
    send("PUT", "/apis/Orders/calls/get_order", {"inputs": {"order_id": 3}})
    assert sab.blade("Orders.get_order")["amount"] == 7.5
    rows = sab.read("Orders", "list_orders", limit=4)
    assert list(rows["order_id"]) == [1, 2, 3, 4]
    # A SQL cell on it: DuckDB here, over the tables it names, each read by Read a table.
    counted = sql_cell.sql(
        "Orders", "SELECT status, count(*) AS n FROM list_orders GROUP BY status ORDER BY status"
    )
    assert counted.to_dict("records") == [{"status": "open", "n": 17}, {"status": "shipped", "n": 8}]
    joined = sql_cell.sql("Orders", "SELECT count(*) AS n FROM list_clients, list_regions")
    assert int(joined["n"][0]) == 21
    assert "list_orders" in sql_cell.tables(sql_cell.connection("Orders"))
    assert "create_order" not in sql_cell.tables(sql_cell.connection("Orders"))
