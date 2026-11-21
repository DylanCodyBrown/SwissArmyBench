"""The Connections page's answers over HTTP (services/connection_usage.py): the cards, one connection's
references, configuration and calls, the kernel's report. No answer holds a password's value: a keyring
password, a vault's entry or an environment variable. Made-up names and values only."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.conftest import AGENT, AUTH
from tests.fake_keyring import memory_keyring

KEYRING_VALUE = "made-up-keyring-pw-4417"
VAULT_VALUE = "made-up-vault-value-9021"
ENV_VALUE = "made-up-env-value-3380"


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def _save(client: TestClient, body: dict[str, Any]) -> None:
    answer = client.post("/connections", json=body, headers=AUTH)
    assert answer.status_code == 200, answer.text


def test_the_usage_answer_names_each_passwords_source_and_never_its_value(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEDGER_PW", ENV_VALUE)
    code = (
        "import psycopg\n"
        'conn = psycopg.connect(host="db.example.test", dbname="sales", password=secret("password"))'
    )
    _save(
        client,
        {"name": "Warehouse", "kind": "sql", "dialect": "postgres", "template": "postgres", "code": code},
    )
    saved = client.put("/blades/Warehouse/secrets", json={"password": KEYRING_VALUE}, headers=AUTH)
    assert saved.status_code == 200, saved.text
    team = {
        "name": "Team vault",
        "kind": "vault",
        "code": f"def get(name):\n    return {VAULT_VALUE!r}",
        "variable": "get",
        "vault_mapping": [{"env": "ARCHIVE_PASSWORD", "secret": "archive-pw"}],
    }
    assert client.post("/blades", json=team, headers=AUTH).status_code == 200
    archive = code.replace('secret("password")', 'secret("ARCHIVE_PASSWORD")')
    _save(
        client,
        {"name": "Archive", "kind": "sql", "dialect": "postgres", "template": "postgres", "code": archive},
    )
    ledger = code.replace('secret("password")', 'secret("LEDGER_PW")')
    _save(
        client,
        {"name": "Ledger", "kind": "sql", "dialect": "postgres", "template": "postgres", "code": ledger},
    )
    lost = code.replace('secret("password")', 'secret("NOWHERE_PW")')
    _save(
        client, {"name": "Lost", "kind": "sql", "dialect": "postgres", "template": "postgres", "code": lost}
    )

    cards = client.get("/connections/usage", headers=AUTH)
    assert cards.status_code == 200, cards.text
    by_name = {c["name"]: c for c in cards.json()["connections"]}
    assert {n: by_name[n]["status"] for n in ("Warehouse", "Archive", "Ledger", "Lost")} == {
        "Warehouse": "ready",
        "Archive": "ready",
        "Ledger": "ready",
        "Lost": "needs",
    }
    assert by_name["Lost"]["missing"] == ["NOWHERE_PW"]
    assert "Team vault" not in by_name or by_name["Team vault"]["connection"] == "vault"

    sources = {}
    for name in ("Warehouse", "Archive", "Ledger", "Lost"):
        answer = client.get(f"/connections/{name}/usage", headers=AGENT)  # the agent too (golden rule)
        assert answer.status_code == 200, answer.text
        text = answer.text
        for value in (KEYRING_VALUE, VAULT_VALUE, ENV_VALUE):
            assert value not in text
        config = answer.json()["configuration"]
        sources[name] = config["passwords"]
        if name == "Warehouse":
            assert {"name": "server", "value": "db.example.test"} in config["settings"]
            assert config["type"] and config["kind"] == "database"
    assert sources == {
        "Warehouse": [{"name": "password", "from": "keyring"}],
        "Archive": [
            {"name": "ARCHIVE_PASSWORD", "from": "vault", "vault": "Team vault", "secret": "archive-pw"}
        ],
        "Ledger": [{"name": "LEDGER_PW", "from": "environment"}],
        "Lost": [{"name": "NOWHERE_PW", "from": "missing"}],
    }
    assert ENV_VALUE not in cards.text and KEYRING_VALUE not in cards.text


def _notebook(cells: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [{"kind": kind, "source": source} for kind, source in cells]


def test_references_calls_and_the_kernels_report(client: TestClient, tmp_path: Path) -> None:
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute("CREATE TABLE orders (order_id INTEGER, region TEXT)")
        made_up.executemany("INSERT INTO orders VALUES (?, ?)", [(i, "North") for i in range(5)])
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{database}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    _save(client, {"name": "Shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code})

    book = tmp_path / "orchard.ipynb"
    cells = [
        {"kind": "sql", "source": "SELECT * FROM orders", "connection": "Shop"},
        {"kind": "code", "source": "# sab.sql('Shop', 'x') is only a comment\nnote = 'Shop'"},
        {"kind": "code", "source": "import swissarmybench as sab\ntotals = sab.sql('Shop', 'SELECT 1')"},
    ]
    saved = client.post("/workbench/save", json={"path": str(book), "cells": cells}, headers=AUTH)
    assert saved.status_code == 200, saved.text
    script = tmp_path / "totals.py"
    text = "import swissarmybench as sab\n\n# %% [1] Load\nrows = sab.read('Shop', 'orders')\n"
    assert (
        client.post("/workbench/save", json={"path": str(script), "text": text}, headers=AUTH).status_code
        == 200
    )
    for path in (book, script):
        client.post("/workbench/open", json={"path": str(path)}, headers=AUTH)

    opened = client.post("/connections/Shop/open", json={"table": "orders"}, headers=AUTH)
    assert opened.status_code == 200, opened.text
    assert client.post("/connections/Shop/used", json={"kind": "query"}, headers=AUTH).status_code == 200
    assert client.post("/connections/Shop/used", json={"kind": "drop"}, headers=AUTH).status_code == 400
    assert client.post("/connections/Nobody/used", json={"kind": "query"}, headers=AUTH).status_code == 404

    usage = client.get("/connections/Shop/usage", headers=AUTH).json()
    found = [(r["kind"], r["title"], r["how"], r.get("cell")) for r in usage["references"]]
    assert ("notebook", "orchard.ipynb", "%%sql", 1) in found
    assert ("notebook", "orchard.ipynb", "sab.sql", 3) in found
    assert not any(r[1] == "orchard.ipynb" and r[3] == 2 for r in found)  # a comment, a string: no use
    assert ("script", "totals.py", "sab.read", 1) in found
    grid = next(r for r in usage["references"] if r["kind"] == "grid")
    assert grid["grid"] == opened.json()["grid"] and grid["title"] == "orders"
    assert usage["calls"]["by_kind"]["read"] >= 1 and usage["calls"]["by_kind"]["query"] == 1
    assert usage["status"] == "works"
    cards = client.get("/connections/usage", headers=AUTH).json()["connections"]
    shop = next(c for c in cards if c["name"] == "Shop")
    assert shop["calls"]["total"] == usage["calls"]["total"] and shop["status"] == "works"
    assert client.get("/connections/Nobody/usage", headers=AUTH).status_code == 404
