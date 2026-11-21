"""Notebooks and Scripts are two pages (the owner, 2026-11-21: "notebooks and scripts should not reuse the
same page they are seperate things"): which page a file opens in, the old /workbench addresses, a
wrong-kind drop refused in one line."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import workbench_pages as pages
from tests.conftest import AGENT, AUTH, make_client


@pytest.mark.parametrize(
    ("path", "page"),
    [
        ("C:\\work\\sales\\data.ipynb", "notebooks"),
        ("/home/u/sales/report.IPYNB", "notebooks"),
        ("/home/u/sales/app.stapp.json", "notebooks"),
        ("/home/u/sales/workbook.design.json", "notebooks"),
        ("/home/u/sales/scripts/etl/load.py", "scripts"),
        ("functions.py", "scripts"),
        ("/home/u/sales/readme.md", None),
        ("", None),
    ],
)
def test_page_of_path(path: str, page: str | None) -> None:
    assert pages.page_of_path(path) == page


def test_page_of_kind() -> None:
    assert pages.page_of_kind("notebook") == "notebooks"
    assert pages.page_of_kind("app") == "notebooks"  # the canvas stays beside the notebooks, as today
    assert pages.page_of_kind("script") == "scripts"
    assert pages.page_of_kind("blade") is None


def test_wrong_page_is_one_line() -> None:
    assert pages.wrong_page("notebook", "notebooks") is None
    said = pages.wrong_page("notebook", "scripts")
    assert said == "A notebook opens on the Notebooks page, not here."
    assert pages.wrong_page("script", "notebooks") == "A script opens on the Scripts page, not here."
    assert pages.wrong_page("explorer", "scripts") is None  # the Data Explorer moves anywhere


def test_old_addresses() -> None:
    assert pages.old_address({"kind": "script", "view": "list"}) == (
        "scripts",
        {"kind": "script", "view": "list"},
    )
    assert pages.old_address({"kind": "notebook"}) == ("notebooks", {"kind": "notebook"})
    assert pages.old_address({"kind": "app", "view": "list"}) == (
        "notebooks",
        {"kind": "app", "view": "list"},
    )
    assert pages.old_address({"file": "/p/load.py"}) == ("scripts", {"file": "/p/load.py"})
    assert pages.old_address({}) == ("notebooks", {})


def test_page_for_command() -> None:
    assert pages.page_for_command("notebooks", {}) == "notebooks"
    assert pages.page_for_command(None, {"path": "/p/x.py"}) == "scripts"
    assert pages.page_for_command(None, {"path": "/p/x.ipynb"}) == "notebooks"
    assert pages.page_for_command(None, {}) is None
    assert pages.page_for_command(None, {}, "file.newScript") == "scripts"
    with pytest.raises(ValueError, match="notebooks or scripts"):
        pages.page_for_command("apps", {})


def test_page_url() -> None:
    assert pages.url_of("scripts") == "/scripts"
    assert pages.WINDOW_NAMES == {"notebooks": "sab-notebooks", "scripts": "sab-scripts"}


# ===== over HTTP =====


def test_the_two_pages_and_the_old_address(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        for path in ("/notebooks", "/scripts"):
            assert "workbench.js" in client.get(path).text
        moved = client.get("/workbench?kind=script&view=list", follow_redirects=False)
        assert moved.status_code == 302
        assert moved.headers["location"] == "/scripts?kind=script&view=list"
        assert client.get("/workbench", follow_redirects=False).headers["location"] == "/notebooks"
        to_file = client.get("/workbench?file=/p/a.py", follow_redirects=False).headers["location"]
        assert to_file.startswith("/scripts?file=")


def test_a_file_says_its_page(tmp_path: Path) -> None:
    (tmp_path / "load.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "data.ipynb").write_text(
        json.dumps({"cells": [], "nbformat": 4, "nbformat_minor": 5, "metadata": {}})
    )
    with make_client(tmp_path) as client:
        script = client.post("/workbench/open", json={"path": str(tmp_path / "load.py")}, headers=AUTH)
        assert script.json()["page"] == "scripts"
        notebook = client.post("/workbench/open", json={"path": str(tmp_path / "data.ipynb")}, headers=AUTH)
        assert notebook.json()["page"] == "notebooks"


def test_a_notebook_is_never_dropped_on_the_scripts_page(tmp_path: Path) -> None:
    document: dict[str, Any] = {
        "kind": "notebook",
        "path": None,
        "title": "Untitled",
        "modified": None,
        "dirty": True,
        "cells": [],
    }
    with make_client(tmp_path) as client:
        made = client.post("/workbench/handoffs", json={"document": document, "to": "main"}, headers=AUTH)
        handoff = made.json()["id"]
        wrong = client.post(
            f"/workbench/handoffs/{handoff}/take", json={"window": "w-s", "page": "scripts"}, headers=AUTH
        )
        assert wrong.status_code == 409
        assert "Notebooks page" in wrong.text
        took = client.post(
            f"/workbench/handoffs/{handoff}/take", json={"window": "w-n", "page": "notebooks"}, headers=AUTH
        )
        assert took.status_code == 200


def test_the_agent_names_a_page_that_is_not_open(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        said = client.post(
            "/workbench/window", json={"command": "documents", "args": {}, "page": "scripts"}, headers=AGENT
        )
        assert said.status_code == 409 and "Scripts page is not open" in said.text
        bad = client.post("/workbench/window", json={"command": "documents", "page": "apps"}, headers=AGENT)
        assert bad.status_code == 400
        nav = client.post("/navigate", json={"window": "scripts", "to": "back"}, headers=AGENT)
        assert nav.status_code == 409 and "Scripts page" in nav.text
