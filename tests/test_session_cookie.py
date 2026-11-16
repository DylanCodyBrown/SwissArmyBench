"""The pages' cookie (the owner, 2026-11-16: the user never sees or handles the token, and a bookmark
works): minted only by the token, HttpOnly, SameSite=Strict, named for the port, a secret of this start's
own (never the token); accepted with the Host and Origin checks, our own Origin on an unsafe method; the
websocket takes it; a wrong or old cookie gets the plain page, never data. The agent's Bearer token is
unchanged."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from swissarmybench.server.app import create_app
from swissarmybench.server.security import SIGNED_OUT_PAGE, WEBSOCKET_SUBPROTOCOL
from swissarmybench.settings import Settings

PORT = 8765
TOKEN = "test-token"
BASE = f"http://127.0.0.1:{PORT}"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
OWN = {"Origin": BASE}
NAME = f"sab_{PORT}"


def make(tmp_path: Path) -> TestClient:
    settings = Settings(state_dir=tmp_path / "state", export_dir=tmp_path / "exports", update_feeds=())
    return TestClient(create_app(PORT, TOKEN, settings, audit_log=False), base_url=BASE)


def mint(client: TestClient) -> str:
    """The page's first request: its token, posted to /session; the cookie's value."""
    answer = client.post("/session", headers=AUTH | OWN)
    assert answer.status_code == 200
    said = answer.headers["set-cookie"]
    assert said.startswith(f"{NAME}=")
    parts = {p.strip().lower() for p in said.split(";")}
    assert "httponly" in parts and "samesite=strict" in parts and "path=/" in parts
    assert "secure" not in parts  # plain http on 127.0.0.1
    value = said.split(";")[0].split("=", 1)[1]
    assert value and TOKEN not in value  # a separate secret, never the token
    client.cookies.clear()
    return value


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return make(tmp_path)


def test_only_the_token_mints_the_cookie(client: TestClient) -> None:
    assert client.post("/session", headers=OWN).status_code == 401
    assert client.post("/session", headers={"Authorization": "Bearer wrong"} | OWN).status_code == 401
    mint(client)


def test_the_cookie_reads_data_like_the_token(client: TestClient) -> None:
    value = mint(client)
    cookie = {"Cookie": f"{NAME}={value}"}
    assert client.get("/health", headers=cookie).status_code == 200
    assert client.get("/session", headers=cookie).json() == {"ok": True}
    assert client.get("/datasets", headers=cookie).status_code == 200
    # Another port's cookie, or the token as a cookie, is not it.
    assert client.get("/health", headers={"Cookie": f"sab_9999={value}"}).status_code == 401
    assert client.get("/health", headers={"Cookie": f"{NAME}={TOKEN}"}).status_code == 401


def test_an_unsafe_method_with_the_cookie_needs_our_own_origin(client: TestClient) -> None:
    cookie = {"Cookie": f"{NAME}={mint(client)}"}
    assert client.put("/updates", json={"check": True}, headers=cookie | OWN).status_code == 200
    # No Origin at all (a browser always sends one on these): refused when the cookie is the credential.
    assert client.put("/updates", json={"check": True}, headers=cookie).status_code == 403
    # Another site's page, cookie or not: refused by the Origin check.
    evil = {"Origin": "https://evil.example"}
    assert client.put("/updates", json={"check": True}, headers=cookie | evil).status_code == 403
    assert client.get("/health", headers=cookie | evil).status_code == 403
    # The Bearer token needs no Origin (the agent, the push client).
    assert client.put("/updates", json={"check": True}, headers=AUTH).status_code == 200


def test_a_wrong_or_old_cookie_gets_the_plain_page_not_data(tmp_path: Path) -> None:
    old = make(tmp_path)
    stale = mint(old)
    # A restart: a new server, a new secret. The old cookie reads nothing.
    fresh = make(tmp_path)
    page = {"Accept": "text/html,application/xhtml+xml", "Cookie": f"{NAME}={stale}"}
    answer = fresh.get("/datasets", headers=page)
    assert answer.status_code == 401 and answer.text == SIGNED_OUT_PAGE
    assert "swissarmybench open" in answer.text and "orders" not in answer.text
    assert fresh.get("/datasets", headers={"Cookie": f"{NAME}=wrong"}).status_code == 401
    assert fresh.get("/session", headers={"Cookie": f"{NAME}={stale}"}).status_code == 401
    # The page shell itself is served: its script then shows the same words (api.ts showSignedOut).
    assert fresh.get("/workspace", headers=page).status_code == 200


def test_the_websocket_takes_the_cookie(client: TestClient) -> None:
    cookie = f"{NAME}={mint(client)}"
    host = {"Host": f"127.0.0.1:{PORT}"}
    with client.websocket_connect(
        "/ws?workspace=1", subprotocols=[WEBSOCKET_SUBPROTOCOL], headers=host | OWN | {"Cookie": cookie}
    ) as socket:
        socket.send_text('{"type":"focus"}')
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/ws", subprotocols=[WEBSOCKET_SUBPROTOCOL], headers=host | OWN | {"Cookie": f"{NAME}=wrong"}
        ),
    ):
        pass
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/ws",
            subprotocols=[WEBSOCKET_SUBPROTOCOL],
            headers=host | {"Origin": "https://evil.example", "Cookie": cookie},
        ),
    ):
        pass
