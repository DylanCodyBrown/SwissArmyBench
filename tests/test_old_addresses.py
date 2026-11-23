"""One front end (the owner, 2026-11-23: "we can swap over to full Blazer do not keep both in sync in
parallel"): the launcher opens /blazor/, every old page's address (a bookmark, the desktop app, a pushed
grid's address, an agent's window) answers with its Blazor page, /blazor/ is served from its published files
(its pages' addresses answering its index.html) or one line when it is not built here, and nothing is left
to choose: no /app/frontend, no app_frontend, no frontend.json read."""

from __future__ import annotations

from pathlib import Path

import pytest

from swissarmybench.cli.commands import CommandError, execute
from swissarmybench.domain import navigation
from swissarmybench.server import lifecycle
from swissarmybench.server.frontend_pages import blazor_address
from tests.conftest import AUTH, make_client


def built(tmp_path: Path) -> Path:
    root = tmp_path / "wwwroot"
    (root / "_framework").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><base href='/blazor/'>made-up index")
    (root / "_framework" / "app.wasm").write_bytes(b"\0asm")
    return root


def test_the_launcher_opens_the_blazor_home_whatever_an_old_frontend_json_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SWISSARMYBENCH_STATE", str(tmp_path))
    (tmp_path / "frontend.json").write_text('{"frontend": "classic"}')  # an older version's: left alone
    assert lifecycle.home_path() == navigation.HOME == "/blazor/"
    info = {"port": 8790, "token": "t"}
    assert lifecycle.page_address(info) == "http://127.0.0.1:8790/blazor/#token=t"
    assert lifecycle.page_address(info, "/blazor/grids") == "http://127.0.0.1:8790/blazor/grids#token=t"
    assert (tmp_path / "frontend.json").read_text() == '{"frontend": "classic"}'


def test_blazor_is_served_without_the_token_and_its_pages_answer_its_index(tmp_path: Path) -> None:
    with make_client(tmp_path, blazor_root=built(tmp_path)) as client:
        assert "made-up index" in client.get("/blazor/").text
        # A page's own address (the app's router draws it): its index.html, also with no token at all.
        assert "made-up index" in client.get("/blazor/connections").text
        assert client.get("/blazor/_framework/app.wasm").headers["content-type"] == "application/wasm"
        assert client.get("/blazor/_framework/missing.wasm").status_code == 404
        assert client.get("/blazor/x", headers={"Origin": "http://evil.example"}).status_code == 403
        # The bare address goes to the app's home.
        assert client.get("/", follow_redirects=False).headers["location"] == "/blazor/"


def test_blazor_not_built_says_so_in_one_line(tmp_path: Path) -> None:
    with make_client(tmp_path, blazor_root=tmp_path / "none") as client:
        answer = client.get("/blazor/")
        assert answer.status_code == 200
        assert "not built here" in answer.text and "blazor/publish.py" in answer.text
        assert "/workspace" not in answer.text and "classic" not in answer.text


def test_each_old_address_has_its_blazor_page() -> None:
    cases = {
        ("/workspace", ()): "/blazor/",
        ("/workspace", (("open", "projects"),)): "/blazor/",
        ("/workspace", (("open", "connections"), ("name", "Shop"))): "/blazor/connections?name=Shop",
        ("/workspace", (("open", "data"),)): "/blazor/catalog",
        ("/workspace", (("open", "environment"), ("at", "libraries"))): "/blazor/environment?at=libraries",
        ("/workspace", (("open", "stockroom"),)): "/blazor/stockroom",  # an extension's area: its own page
        ("/workspace", (("view", "erd"),)): "/blazor/erd",
        ("/workspace", (("view", "analyze"), ("table", "orders"))): "/blazor/analyze?table=orders",
        ("/workspace", (("classic", "1"),)): "/blazor/",  # an older bookmark's word, dropped
        ("/g/g7", ()): "/blazor/grids?grid=g7",
        ("/g/g7", (("panel", "steps"),)): "/blazor/panel?grid=g7&panel=steps",
        ("/notebooks", (("kind", "notebook"), ("view", "list"))): "/blazor/notebooks",
        ("/scripts", (("path", "etl/load.py"),)): "/blazor/scripts?path=etl%2Fload.py",
        ("/notebooks", (("file", "a.ipynb"),)): "/blazor/notebooks?path=a.ipynb",
        ("/streamlit/canvas", (("path", "app.canvas.json"),)): "/blazor/canvas?path=app.canvas.json",
        ("/streamlit/widget", (("name", "kpi"),)): "/blazor/widgets?name=kpi",
        ("/streamlit/perf", (("canvas", "app"),)): "/blazor/perf?canvas=app",
    }
    for (path, words), blazor in cases.items():
        assert navigation.is_old_page(path)
        assert blazor_address(path, dict(words)) == blazor, path
    for other in ("/blazor/", "/g/", "/datasets", "/static/build/main.js", "/session"):
        assert not navigation.is_old_page(other)


def test_an_old_page_answers_with_its_blazor_page(tmp_path: Path) -> None:
    with make_client(tmp_path, blazor_root=built(tmp_path)) as client:
        moved = client.get("/workspace?open=connections", headers=AUTH, follow_redirects=False)
        assert moved.status_code == 302 and moved.headers["location"] == "/blazor/connections"
        assert client.get("/notebooks", follow_redirects=False).headers["location"] == "/blazor/notebooks"
        assert client.get("/g/g1", follow_redirects=False).headers["location"] == "/blazor/grids?grid=g1"
        assert client.get("/workspace?classic=1", follow_redirects=False).headers["location"] == "/blazor/"
        # The older addresses before those: /catalog and /workbench, then their Blazor pages.
        assert client.get("/catalog", follow_redirects=True).url.path == "/blazor/scripts"
        assert client.get("/datasets", headers=AUTH).status_code == 200  # the data routes never move
        # The classic pages' files are gone: nothing is served at /static/ any more.
        assert client.get("/static/grid.css", headers=AUTH).status_code == 404


def test_an_old_page_moves_even_where_blazor_is_not_built(tmp_path: Path) -> None:
    with make_client(tmp_path, blazor_root=tmp_path / "none") as client:
        moved = client.get("/workspace", follow_redirects=False)
        assert moved.status_code == 302 and moved.headers["location"] == "/blazor/"
        assert "not built here" in client.get("/workspace").text


def test_there_is_no_front_end_to_choose(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/app/frontend", headers=AUTH).status_code == 404
        chosen = client.put("/app/frontend", json={"frontend": "classic"}, headers=AUTH)
        assert chosen.status_code in (404, 405)
    with pytest.raises(CommandError, match="app_frontend went"):
        execute("app_frontend", {})
