"""Find connections on this computer over HTTP: the scan of a made-up home folder, the list (merged, Already
added, kinds we have no connection for), the import (connections from their starters, each password a
variable not set here), the agent's on the user's Allow; no made-up password in any answer, log or file."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests import found_fixtures as fx
from tests.conftest import AGENT, AUTH, make_client


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    home = fx.windows_home(tmp_path / "fakehome")
    with make_client(tmp_path, find_home=home, find_system="windows") as test_client:
        yield test_client


def no_password_anywhere(tmp_path: Path, *answers: Any) -> None:
    for answer in answers:
        assert [p for p in fx.PASSWORDS if p in repr(answer)] == []
    for path in tmp_path.rglob("*"):
        if path.is_file() and "fakehome" not in path.parts:
            data = path.read_bytes()
            assert [p for p in fx.PASSWORDS if p.encode() in data] == [], path


def scan(client: TestClient, headers: dict[str, str] = AUTH) -> dict[str, Any]:
    answer = client.post("/connections/found", headers=headers)
    assert answer.status_code == 200, answer.text
    return dict(answer.json())


def row(found: dict[str, Any], name: str) -> dict[str, Any]:
    return next(r for r in found["connections"] if r["name"] == name)


def test_find_then_import_two(client: TestClient, tmp_path: Path) -> None:
    found = scan(client)
    shop = row(found, "Shop (dev)")
    assert (shop["kind"], shop["server"], shop["database"], shop["user"]) == (
        "postgres",
        "pg.shop.internal",
        "shop",
        "analyst",
    )
    assert [s["tool"] for s in shop["from"]] == ["DBeaver", "pgAdmin 4"]  # merged: both sources shown
    finance = row(found, "Finance ledger")
    assert finance["sign_in"] == "windows"
    assert [n["key"] for n in finance["local"]] == ["windows"]  # the amber note, before it is imported
    events = row(found, "Events")
    assert events["supported"] is False and "MongoDB" in events["why"]
    hint = row(found, "Orders on orders-sql07.corp.internal")
    assert hint["searched"] is True and hint["from"][0]["where"] == "AppData\\Roaming\\OrdersTool"
    assert any("SqlStudio.bin" in n for n in found["notes"])

    done = client.post("/connections/found/import", json={"ids": [shop["id"], finance["id"]]}, headers=AUTH)
    assert done.status_code == 200, done.text
    made = {m["name"]: m for m in done.json()["imported"]}
    assert set(made) == {"Shop dev", "Finance ledger"}  # a connection's name: letters, digits, spaces
    assert made["Shop dev"]["variable"] == "SHOP_DEV_PASSWORD" and made["Finance ledger"]["variable"] is None
    assert done.json()["variables"] == ["SHOP_DEV_PASSWORD"]

    listed = {c["name"]: c for c in client.get("/connections", headers=AUTH).json()["connections"]}
    assert listed["Shop dev"]["template"] == "postgres"
    detail = client.get("/connections/Shop dev", headers=AUTH).json()
    assert 'secret("SHOP_DEV_PASSWORD")' in detail["code"] and 'host="pg.shop.internal"' in detail["code"]
    variables = {v["name"]: v for v in client.get("/variables", headers=AUTH).json()["variables"]}
    assert "SHOP_DEV_PASSWORD" in variables

    again = scan(client)
    assert row(again, "Shop (dev)")["already"] == "Shop dev"
    assert row(again, "Finance ledger")["already"] == "Finance ledger"
    skipped = client.post(
        "/connections/found/import", json={"ids": [row(again, "Shop (dev)")["id"]]}, headers=AUTH
    )
    assert skipped.json()["imported"] == [] and "Already added" in skipped.json()["skipped"][0]["why"]
    unsupported = client.post(
        "/connections/found/import", json={"ids": [row(again, "Events")["id"]]}, headers=AUTH
    )
    assert "no MongoDB connection" in unsupported.json()["skipped"][0]["why"]
    no_password_anywhere(tmp_path, found, again, done.json(), listed, detail, variables)


def test_import_needs_a_search_first(client: TestClient) -> None:
    answer = client.post("/connections/found/import", json={"ids": ["abc"]}, headers=AUTH)
    assert answer.status_code == 409


def test_cancel_with_nothing_running(client: TestClient) -> None:
    assert client.post("/connections/found/cancel", headers=AUTH).json() == {"cancelled": False}


def answer_next(client: TestClient, approve: bool) -> threading.Thread:
    def run() -> None:
        for _ in range(200):
            pending = client.get("/agent/approvals", headers=AUTH).json()["pending"]
            if pending:
                client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": approve}, headers=AUTH)
                return
            time.sleep(0.05)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_the_agents_search_and_import_wait_for_the_users_allow(client: TestClient, tmp_path: Path) -> None:
    thread = answer_next(client, False)
    refused = client.post("/connections/found", headers=AGENT)
    thread.join()
    assert refused.status_code == 403
    thread = answer_next(client, True)
    found = scan(client, AGENT)
    thread.join()
    ids = [row(found, "Sales warehouse")["id"]]
    thread = answer_next(client, True)
    done = client.post("/connections/found/import", json={"ids": ids}, headers=AGENT)
    thread.join()
    assert done.status_code == 200, done.text
    assert [m["name"] for m in done.json()["imported"]] == ["Sales warehouse"]
    detail = client.get("/connections/Sales warehouse", headers=AUTH).json()
    assert 'server="sales-sql02.corp.internal"' in detail["code"] and 'instance="WAREHOUSE"' in detail["code"]
    no_password_anywhere(tmp_path, found, done.json(), detail)
