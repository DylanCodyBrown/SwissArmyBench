"""The front end the app opens (the owner, 2026-11-23: the Blazor front end, then "do the swap"): the Blazor
one by default, frontend.json kept on this computer, GET/PUT /app/frontend and the agent's app_frontend, the
launcher's home page (the classic one where Blazor is not built), every classic page's address sent to its
Blazor page, and /blazor/ served from its published files (its pages' addresses answering its index.html),
or one line when it is not built here."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swissarmybench.domain import navigation
from swissarmybench.server import lifecycle
from swissarmybench.server.frontend_pages import blazor_address
from tests.conftest import AGENT, AUTH, make_client


@pytest.fixture(autouse=True)
def no_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests read this computer's own choice (the classic pages' browser tests pin classic)."""
    monkeypatch.delenv("SWISSARMYBENCH_FRONTEND", raising=False)


def test_the_blazor_front_end_unless_the_user_picks_the_classic_one() -> None:
    assert navigation.frontend(None) == "blazor"
    assert navigation.frontend({"frontend": "classic"}) == "classic"
    assert navigation.frontend({"frontend": "react"}) == "blazor"
    assert navigation.home_page(None) == "/blazor/"
    assert navigation.home_page(None, blazor_built=False) == "/workspace"  # a checkout without its build
    assert navigation.home_page({"frontend": "classic"}) == "/workspace"
    assert navigation.frontend_change({"frontend": "classic"}) == "classic"
    bad: object
    for bad in ({}, {"frontend": "new"}, [], None):
        with pytest.raises(navigation.NavigationError, match="frontend"):
            navigation.frontend_change(bad)


def test_the_choice_is_kept_on_this_computer_and_the_agent_sets_it(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        first = client.get("/app/frontend", headers=AUTH).json()
        assert first == {"frontend": "blazor", "home": "/blazor/"}
        said = client.put("/app/frontend", json={"frontend": "classic"}, headers=AGENT)
        assert said.json() == {"frontend": "classic", "home": "/workspace"}
        assert client.put("/app/frontend", json={"frontend": "x"}, headers=AUTH).status_code == 400
    assert json.loads((tmp_path / "state" / "frontend.json").read_text()) == {"frontend": "classic"}
    with make_client(tmp_path) as client:
        assert client.get("/app/frontend", headers=AUTH).json()["frontend"] == "classic"


def test_the_launcher_opens_the_chosen_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWISSARMYBENCH_STATE", str(tmp_path))
    monkeypatch.setattr("swissarmybench.settings.blazor_built", lambda: True)
    assert lifecycle.home_path() == "/blazor/"
    (tmp_path / "frontend.json").write_text('{"frontend": "classic"}')
    assert lifecycle.home_path() == "/workspace"
    monkeypatch.setenv("SWISSARMYBENCH_FRONTEND", "blazor")  # the pin wins over this computer's choice
    assert lifecycle.home_path() == "/blazor/"
    monkeypatch.delenv("SWISSARMYBENCH_FRONTEND")
    (tmp_path / "frontend.json").write_text("not json")
    info = {"port": 8790, "token": "t"}
    assert lifecycle.page_address(info) == "http://127.0.0.1:8790/blazor/#token=t"
    assert lifecycle.page_address(info, "/workspace") == "http://127.0.0.1:8790/workspace#token=t"
    monkeypatch.setattr("swissarmybench.settings.blazor_built", lambda: False)
    assert lifecycle.home_path() == "/workspace"  # Blazor not built here: the classic pages


def test_blazor_is_served_without_the_token_and_its_pages_answer_its_index(tmp_path: Path) -> None:
    built = tmp_path / "wwwroot"
    (built / "_framework").mkdir(parents=True)
    (built / "index.html").write_text("<!doctype html><base href='/blazor/'>made-up index")
    (built / "_framework" / "app.wasm").write_bytes(b"\0asm")
    with make_client(tmp_path, blazor_root=built) as client:
        assert "made-up index" in client.get("/blazor/").text
        # A page's own address (the app's router draws it): its index.html, also with no token at all.
        assert "made-up index" in client.get("/blazor/connections").text
        assert client.get("/blazor/_framework/app.wasm").headers["content-type"] == "application/wasm"
        assert client.get("/blazor/_framework/missing.wasm").status_code == 404
        assert client.get("/blazor/x", headers={"Origin": "http://evil.example"}).status_code == 403


def test_blazor_not_built_says_so_in_one_line(tmp_path: Path) -> None:
    with make_client(tmp_path, blazor_root=tmp_path / "none") as client:
        answer = client.get("/blazor/")
        assert answer.status_code == 200
        assert "not built here" in answer.text and "/workspace" in answer.text


def test_each_classic_address_has_its_blazor_page() -> None:
    cases = {
        ("/workspace", ()): "/blazor/",
        ("/workspace", (("open", "projects"),)): "/blazor/",
        ("/workspace", (("open", "connections"), ("name", "Shop"))): "/blazor/connections?name=Shop",
        ("/workspace", (("open", "data"),)): "/blazor/catalog",
        ("/workspace", (("open", "environment"), ("at", "libraries"))): "/blazor/environment?at=libraries",
        ("/workspace", (("open", "stockroom"),)): "/blazor/stockroom",  # an extension's area: its own page
        ("/workspace", (("view", "erd"),)): "/blazor/erd",
        ("/workspace", (("view", "analyze"), ("table", "orders"))): "/blazor/analyze?table=orders",
        ("/g/g7", ()): "/blazor/grids?grid=g7",
        ("/g/g7", (("panel", "steps"),)): "/blazor/panel?grid=g7&panel=steps",
        ("/notebooks", (("kind", "notebook"), ("view", "list"))): "/blazor/notebooks",
        ("/scripts", (("path", "etl/load.py"),)): "/blazor/scripts?path=etl%2Fload.py",
        ("/streamlit/canvas", (("path", "app.canvas.json"),)): "/blazor/canvas?path=app.canvas.json",
        ("/streamlit/widget", (("name", "kpi"),)): "/blazor/widgets?name=kpi",
        ("/streamlit/perf", (("canvas", "app"),)): "/blazor/perf?canvas=app",
    }
    for (path, words), blazor in cases.items():
        assert navigation.is_classic_page(path)
        assert blazor_address(path, dict(words)) == blazor, path
    for other in ("/blazor/", "/g/", "/datasets", "/static/build/main.js", "/session"):
        assert not navigation.is_classic_page(other)


def test_a_classic_page_answers_with_its_blazor_page_while_blazor_is_chosen(tmp_path: Path) -> None:
    built = tmp_path / "wwwroot"
    built.mkdir()
    (built / "index.html").write_text("<!doctype html><base href='/blazor/'>made-up index")
    with make_client(tmp_path, blazor_root=built) as client:
        moved = client.get("/workspace?open=connections", headers=AUTH, follow_redirects=False)
        assert moved.status_code == 302 and moved.headers["location"] == "/blazor/connections"
        assert client.get("/notebooks", follow_redirects=False).headers["location"] == "/blazor/notebooks"
        # ?classic=1: the classic page anyway, while it lasts.
        assert client.get("/workspace?classic=1", follow_redirects=False).status_code == 200
        assert client.get("/datasets", headers=AUTH).status_code == 200  # the data routes never move
        client.put("/app/frontend", json={"frontend": "classic"}, headers=AUTH)
        assert client.get("/workspace", follow_redirects=False).status_code == 200  # the choice takes at once


def test_no_page_moves_where_blazor_is_not_built(tmp_path: Path) -> None:
    with make_client(tmp_path, blazor_root=tmp_path / "none") as client:
        assert client.get("/workspace", follow_redirects=False).status_code == 200
