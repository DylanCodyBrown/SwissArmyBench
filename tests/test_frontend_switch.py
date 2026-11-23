"""The front end the app opens (the owner, 2026-11-23: the Blazor front end beside the classic one):
frontend.json kept on this computer, GET/PUT /app/frontend and the agent's app_frontend, the launcher's
home page, and /blazor/ served from its published files (its pages' addresses answering its index.html),
or one line when it is not built here."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swissarmybench.domain import navigation
from swissarmybench.server import lifecycle
from tests.conftest import AGENT, AUTH, make_client


def test_the_classic_front_end_until_the_user_picks_the_other() -> None:
    assert navigation.frontend(None) == "classic"
    assert navigation.frontend({"frontend": "blazor"}) == "blazor"
    assert navigation.frontend({"frontend": "react"}) == "classic"
    assert navigation.home_page(None) == "/workspace"
    assert navigation.home_page({"frontend": "blazor"}) == "/blazor/"
    assert navigation.frontend_change({"frontend": "blazor"}) == "blazor"
    bad: object
    for bad in ({}, {"frontend": "new"}, [], None):
        with pytest.raises(navigation.NavigationError, match="frontend"):
            navigation.frontend_change(bad)


def test_the_choice_is_kept_on_this_computer_and_the_agent_sets_it(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        first = client.get("/app/frontend", headers=AUTH).json()
        assert first == {"frontend": "classic", "home": "/workspace"}
        said = client.put("/app/frontend", json={"frontend": "blazor"}, headers=AGENT)
        assert said.json() == {"frontend": "blazor", "home": "/blazor/"}
        assert client.put("/app/frontend", json={"frontend": "x"}, headers=AUTH).status_code == 400
    assert json.loads((tmp_path / "state" / "frontend.json").read_text()) == {"frontend": "blazor"}
    with make_client(tmp_path) as client:
        assert client.get("/app/frontend", headers=AUTH).json()["frontend"] == "blazor"


def test_the_launcher_opens_the_chosen_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWISSARMYBENCH_STATE", str(tmp_path))
    assert lifecycle.home_path() == "/workspace"
    (tmp_path / "frontend.json").write_text('{"frontend": "blazor"}')
    assert lifecycle.home_path() == "/blazor/"
    info = {"port": 8790, "token": "t"}
    assert lifecycle.page_address(info) == "http://127.0.0.1:8790/blazor/#token=t"
    assert lifecycle.page_address(info, "/workspace") == "http://127.0.0.1:8790/workspace#token=t"
    (tmp_path / "frontend.json").write_text("not json")
    assert lifecycle.home_path() == "/workspace"


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
