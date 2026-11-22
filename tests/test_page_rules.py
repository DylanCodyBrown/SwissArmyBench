"""The page keeps no copy of the rules for where a file opens (the front end / back end rule): it applies the
server's tables (domain/workbench_pages.py rules(), GET /app/rules) with web/src/pageRules.ts. Here the
page's functions, run by Node on those tables, answer exactly as the server's own functions do."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import workbench_pages as pages
from tests.conftest import AUTH
from tests.web_unit import bundled, needs_node

PATHS = [
    "C:\\work\\sales\\data.ipynb",
    "/home/u/sales/report.IPYNB",
    "/home/u/sales/app.stapp.json",
    "/home/u/sales/workbook.design.json",
    "/home/u/sales/scripts/etl/load.py",
    "functions.py",
    "orders.json",
    "config.yaml",
    "config.YML",
    "feed.xml",
    "pyproject.toml",
    r"C:\work\shop\structures\gates.json",
    "sales.canvas.json",
    "old.stapp.json",
    ".sab/project.json",
    "/home/me/shop/.sab/model.json",
    ".hidden.json",
    "orders.jsonl",
    "/home/u/sales/readme.md",
    "",
    "   ",
]
KINDS = ["notebook", "script", "app", "blade", "explorer", "structure", "", None]


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return bundled(tmp_path_factory.mktemp("page-rules"), "pageRules.ts")


def test_the_route_answers_the_domains_tables(client: TestClient) -> None:
    answered = client.get("/app/rules", headers=AUTH)
    assert answered.status_code == 200, answered.text
    assert answered.json() == {"pages": pages.rules()}
    found = pages.rules()
    assert found["structures"]["suffixes"] == list(pages.STRUCTURE_SUFFIXES)
    assert found["wrong_page"].format(kind="A script", page="Scripts") == pages.wrong_page(
        "script", "notebooks"
    )
    for path in PATHS:  # a file's kind and its page agree: a kind's page is its file's
        kind = pages.kind_of_path(path)
        assert kind is None or pages.page_of_kind(kind) == pages.page_of_path(path), path


@needs_node
def test_the_page_answers_as_the_server_does_on_the_servers_tables(run: Any) -> None:
    use = ["usePageRules", pages.rules()]
    said = run(use, *[["pageOfPath", p] for p in PATHS])[1:]
    assert said == [pages.page_of_path(p) for p in PATHS]
    said = run(use, *[["kindOfPath", p] for p in PATHS])[1:]
    assert said == [pages.kind_of_path(p) for p in PATHS]
    said = run(use, *[["isStructurePath", p] for p in PATHS])[1:]
    assert said == [pages.is_structure_path(p) for p in PATHS]
    said = run(use, *[["homeOfPath", p] for p in PATHS])[1:]
    assert said == [pages.home_of_path(p) for p in PATHS]
    said = run(use, *[["pageOfKind", k] for k in KINDS])[1:]
    assert said == [pages.page_of_kind(k) for k in KINDS]
    for page in pages.PAGES:
        said = run(use, *[["wrongPage", k, page] for k in KINDS])[1:]
        assert said == [pages.wrong_page(k, page) for k in KINDS], page
    assert run(use, ["structureSuffixes"])[1] == list(pages.STRUCTURE_SUFFIXES)


@needs_node
def test_the_page_has_no_rule_of_its_own(run: Any) -> None:
    """Before the server's tables arrive every question answers none, and the page's files name no ending."""
    asked = run(
        ["pageOfPath", "load.py"], ["isStructurePath", "a.json"], ["wrongPage", "script", "notebooks"]
    )
    assert asked == [None, False, None]
    assert run(["pageRulesReady"], ["usePageRules", pages.rules()], ["pageRulesReady"]) == [False, None, True]
    source = Path(__file__).resolve().parents[1] / "web" / "src"
    for name in (
        "pageRules.ts",
        "workbenchPages.ts",
        "structurePaths.ts",
        "kindColours.ts",
        "sessionPage.ts",
    ):
        text = (source / name).read_text(encoding="utf-8")
        for ending in (".stapp", 'endsWith(".ipynb")', '[".json", ".yaml"', "A Streamlit app"):
            assert ending not in text, (name, ending)
