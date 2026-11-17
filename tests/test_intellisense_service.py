"""The editors' intelligence as a use case (services/intellisense.py) and over HTTP: Jedi's Script and a
kernel's Interpreter, the app's own names, the project's modules with their import, the lint with Ruff or
without, SQL cells, and what the agent reads. Made-up names throughout."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters.intellisense import JediWorld, Linters, ProjectModules
from swissarmybench.client import kernel_intel
from swissarmybench.domain.datasets import Column
from swissarmybench.server.text_process import run_text
from swissarmybench.services.intellisense import Intellisense
from tests.conftest import AGENT, AUTH, make_client

FUNCTIONS = '''"""The project's functions."""


def write_sqlite(connection: str, table: str, rows: list, mode: str = "append") -> int:
    """Write rows to a SQLite table.

    Args:
        connection: The connection's name.
        table: The table to write.
        rows: The rows.
        mode: append or replace.
    """
    return len(rows)


def tidy_names(frame):
    return frame
'''


@pytest.fixture(autouse=True)
def patient(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one-second budget is for typing; under a loaded test run Jedi's first look takes longer."""
    monkeypatch.setattr("swissarmybench.services.intellisense.BUDGET_SECONDS", 20.0)


class NoRuff(Linters):
    def ruff_command(self, python: str | None) -> str | None:
        return None


def service(folder: Path | None = None, linters: Linters | None = None, **extra: Any) -> Intellisense:
    info = SimpleNamespace(
        name="orders", columns=[Column("region", "VARCHAR"), Column("order total", "DOUBLE")]
    )
    ws = SimpleNamespace(store=SimpleNamespace(all=lambda: [info]))
    blades: list[dict[str, Any]] = [
        {
            "name": "Warehouse",
            "kind": "database",
            "connection": "database",
            "code_name": "warehouse",
            "description": "The made-up warehouse.",
        },
        {
            "name": "Tidy columns",
            "kind": "transform",
            "connection": None,
            "env_names": [],
            "description": "Tidies a table's column names.",
        },
    ]
    return Intellisense(
        ws,  # type: ignore[arg-type]
        kernel_intel.answer,
        JediWorld(),
        ProjectModules(),
        linters or NoRuff(),
        kernel_of=extra.get("kernel_of", lambda _id: None),
        project_folder=lambda: str(folder) if folder else None,
        blades=lambda: blades,
        variables=lambda: [
            {"name": "WAREHOUSE_URL", "words": "a plain value"},
            {"name": "WAREHOUSE_PASSWORD", "words": "the keyring"},
        ],
        structures=lambda: ["orders.json"],
        dialect_of=lambda name: {"warehouse": "postgres", "finance": "dax"}.get(name.casefold()),
        read_file=lambda path: Path(path).read_text(encoding="utf-8"),
    )


def labels(answer: dict[str, Any]) -> list[str]:
    return [i["label"] for i in answer["items"]]


def test_the_member_list_explains_a_function_and_tabs_through_its_arguments() -> None:
    intel = service()
    earlier = FUNCTIONS
    answer = asyncio.run(
        intel.complete({"text": "write_", "offset": 6, "notebook": True, "before": [earlier]})
    )
    [item] = [i for i in answer["items"] if i["label"] == "write_sqlite"]
    assert item["kind"] == "function" and item["group"] == "scope"
    assert item["detail"].startswith("write_sqlite(connection: str, table: str, rows: list")
    assert "- `table`: The table to write." in item["documentation"]
    assert item["snippet"] == "write_sqlite(${1:connection}, ${2:table}, ${3:rows})$0"
    assert (answer["start"], answer["end"]) == (0, 6)


def test_sab_offers_its_calls_never_its_layers() -> None:
    answer = asyncio.run(service().complete({"text": "sab.", "offset": 4, "notebook": True}))
    found = labels(answer)
    assert "connection" in found and "sql" in found
    assert not {"adapters", "server", "domain", "bootstrap"} & set(found)
    assert {i["group"] for i in answer["items"]} == {"app"}


def test_the_apps_names_inside_strings() -> None:
    intel = service()

    def inside(text: str) -> dict[str, Any]:
        return asyncio.run(intel.complete({"text": text, "offset": len(text)}))

    assert labels(inside('sab.connection("Wa')) == ["Warehouse"]
    assert labels(inside('sab.blade("')) == ["Tidy columns"]
    assert labels(inside('os.environ["WAREHOUSE_')) == ["WAREHOUSE_URL", "WAREHOUSE_PASSWORD"]
    variable = inside('secret("WAREHOUSE_P')["items"][0]
    assert variable["detail"] == "the keyring" and "value" not in variable
    assert labels(inside('sab.structure("')) == ["orders.json"]
    assert labels(inside('orders["')) == ["region", "order total"]
    assert inside('sab.connection("Wa')["start"] == len('sab.connection("')


def test_an_open_tables_columns_after_its_name_and_the_connections_by_their_code_names() -> None:
    intel = service()
    answer = asyncio.run(intel.complete({"text": "orders.reg", "offset": 10}))
    assert "region" in labels(answer) and "order total" not in labels(answer)  # not an identifier
    answer = asyncio.run(intel.complete({"text": "wareh", "offset": 5}))
    assert answer["items"][0]["label"] == "warehouse" and answer["items"][0]["kind"] == "connection"


def test_a_project_modules_name_completes_with_its_import(tmp_path: Path) -> None:
    (tmp_path / "functions.py").write_text(FUNCTIONS, encoding="utf-8")
    intel = service(tmp_path)
    text = "import json\n\nwrite_sq"
    answer = asyncio.run(intel.complete({"text": text, "offset": len(text)}))
    [item] = [i for i in answer["items"] if i["label"] == "write_sqlite"]
    assert item["group"] == "project" and item["import_line"] == "from functions import write_sqlite"
    assert item["imports"] == [
        {"line": 2, "col": 1, "end_line": 2, "end_col": 1, "text": "from functions import write_sqlite\n"}
    ]
    assert "Write rows to a SQLite table." in item["documentation"]
    # Already imported: no second import.
    text = "from functions import write_sqlite\nwrite_sq"
    answer = asyncio.run(intel.complete({"text": text, "offset": len(text)}))
    assert all("imports" not in i for i in answer["items"])
    # Jedi reads the project's modules too: `from functions import ` lists them.
    text = "from functions import wr"
    answer = asyncio.run(intel.complete({"text": text, "offset": len(text), "path": str(tmp_path / "a.py")}))
    assert "write_sqlite" in labels(answer)


def test_parameter_info_bolds_the_argument_the_cursor_is_on() -> None:
    intel = service()
    text = FUNCTIONS + "\nwrite_sqlite("
    first = asyncio.run(intel.signature({"text": text, "offset": len(text)}))["signatures"][0]
    assert first["label"].startswith("write_sqlite(connection: str, table: str")
    assert first["active"] == 0
    p = first["params"][0]
    assert first["label"][p["span"][0] : p["span"][1]] == "connection: str"
    assert p["words"] == "The connection's name."
    assert first["returns"] == "int" and first["summary"] == "Write rows to a SQLite table."
    second = asyncio.run(intel.signature({"text": text + '"Warehouse", ', "offset": len(text) + 13}))
    assert second["signatures"][0]["active"] == 1
    keyword = asyncio.run(intel.signature({"text": text + "mode=", "offset": len(text) + 5}))
    assert keyword["signatures"][0]["active"] == 3


def test_the_hover_says_the_signature_and_the_docstring() -> None:
    text = FUNCTIONS + "\nwrite_sqlite"
    hover = asyncio.run(service().hover({"text": text, "offset": len(text) - 3}))["hover"]
    assert "write_sqlite(connection: str" in hover and "The table to write." in hover


def test_the_lint_across_cells_in_run_order() -> None:
    intel = service()
    before = ["import pandas as pd\norders = pd.DataFrame()"]
    after = ["print(json.dumps({}))"]
    found = asyncio.run(
        intel.lint(
            {
                "text": "import json\ntotal = len(orders) + len(ordres)",
                "notebook": True,
                "before": before,
                "after": after,
            }
        )
    )
    assert [(p["code"], p["message"]) for p in found["problems"]] == [("F821", "`ordres` is not defined")]
    assert found["problems"][0]["fixes"][0]["title"] == "Use `orders`"
    assert found["ruff"]["used"] is False
    assert found["ruff"]["reason"] == "Ruff is not installed in this document's Python"
    assert found["ruff"]["missing"]["packages"] == ["ruff"]
    magic = asyncio.run(intel.lint({"text": "%time x = 1\n!ls", "notebook": True}))
    assert magic["problems"] == []


def test_a_variable_from_the_variables_page_is_offered_as_its_definition() -> None:
    found = asyncio.run(service().lint({"text": "print(WAREHOUSE_URL)"}))
    titles = [f["title"] for f in found["problems"][0]["fixes"]]
    assert "Define `WAREHOUSE_URL` from the Variables page (a plain value)" in titles


RUFF = shutil.which("ruff")


@pytest.mark.skipif(RUFF is None, reason="Ruff is not installed on this computer")
def test_ruff_in_the_documents_environment_adds_its_rules(tmp_path: Path) -> None:
    env = tmp_path / "env" / "bin"
    env.mkdir(parents=True)
    os.symlink(sys.executable, env / "python")
    os.symlink(RUFF, env / "ruff")  # type: ignore[arg-type]
    (tmp_path / "ruff.toml").write_text('[lint]\nselect = ["E4", "E7", "E9", "F"]\n', encoding="utf-8")
    intel = service(tmp_path, Linters(run_text))
    text = "import os\nx = 1\nif x == None:\n    pass\nimport json\n"
    found = asyncio.run(intel.lint({"text": text, "python": str(env / "python")}))
    assert found["ruff"] == {"used": True} and found["checker"] == "ruff"
    codes = [(p["code"], p["source"]) for p in found["problems"]]
    assert ("F401", "Python") in codes and ("E711", "Python") in codes  # the app's own, with its fixes
    assert ("E402", "Ruff") in codes  # Ruff's own rule: an import below code
    unused = next(p for p in found["problems"] if p["code"] == "F401")
    assert unused["unnecessary"] is True and unused["fixes"]


def test_without_ruff_or_pyflakes_python_and_the_ast_pass_answer() -> None:
    found = asyncio.run(service().lint({"text": "import os\n", "python": "/nowhere/python"}))
    assert found["checker"] in ("python", "pyflakes")
    assert [p["code"] for p in found["problems"]] == ["F401"]


def test_sql_cells_by_duckdb_and_by_the_connections_dialect() -> None:
    intel = service()
    found = asyncio.run(intel.lint({"text": "SELECT a\nFORM [Finance Captive].Sales", "language": "sql"}))
    [p] = found["problems"]
    assert (p["line"], p["source"]) == (2, "DuckDB") and "syntax error" in p["message"].lower()
    assert (
        asyncio.run(intel.lint({"text": "SELECT * FROM [Finance Captive].Sales", "language": "sql"}))[
            "problems"
        ]
        == []
    )
    found = asyncio.run(
        intel.lint({"text": "SELECT a FROM t WHERE", "language": "sql", "connection": "Warehouse"})
    )
    assert found["dialect"] == "postgres" and found["problems"][0]["source"] == "SQL"
    assert (
        asyncio.run(intel.lint({"text": "EVALUATE x", "language": "sql", "connection": "Finance"}))[
            "problems"
        ]
        == []
    )


def test_a_superseded_request_is_not_worked_out() -> None:
    intel = service()
    asyncio.run(intel.complete({"text": "x", "offset": 1, "editor": "e1", "seq": 5}))
    late = asyncio.run(intel.complete({"text": "pri", "offset": 3, "editor": "e1", "seq": 4}))
    assert late["items"] == []


def test_a_notebook_file_checked_for_the_agent(tmp_path: Path) -> None:
    notebook = {
        "cells": [
            {"cell_type": "code", "source": ["import pandas as pd\n", "orders = pd.DataFrame()"]},
            {"cell_type": "code", "source": "print(ordrs)"},
        ]
    }
    path = tmp_path / "a.ipynb"
    path.write_text(json.dumps(notebook), encoding="utf-8")
    found = asyncio.run(service().problems(str(path)))
    [p] = found["documents"][0]["problems"]
    assert (p["cell"], p["code"]) == (2, "F821")


# ===== over HTTP, with a kernel =====


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        yield test_client


def run(client: TestClient, kernel: str, code: str) -> None:
    answer = client.post(f"/workbench/kernels/{kernel}/execute", json={"code": code}, headers=AUTH)
    assert answer.status_code == 200, answer.text


def test_a_kernels_live_names_through_jedis_interpreter(client: TestClient) -> None:
    kernel = client.post("/workbench/kernels", json={}, headers=AUTH).json()["kernel"]
    try:
        run(client, kernel, "import pandas as pd\nrainfall = pd.DataFrame({'rain_mm': [3.5]})")
        body = {"text": "rainfall.rai", "offset": 12, "kernel": kernel, "notebook": True}
        for _ in range(20):  # the kernel's first ask loads Jedi there: the Script answers meanwhile
            answer = client.post("/workbench/intel/complete", json=body, headers=AUTH).json()
            if answer["from"] == "kernel":
                break
        assert "rain_mm" in labels(answer) and answer["from"] == "kernel"
        hover = client.post("/workbench/intel/hover", json=body | {"offset": 3}, headers=AUTH).json()
        assert "rainfall: pandas.DataFrame" in hover["hover"] and "(1 by 1)" in hover["hover"]
        # The kernel's names are known to the lint: nothing undefined.
        lint = client.post(
            "/workbench/intel/lint",
            json={"text": "print(rainfall)", "kernel": kernel, "notebook": True},
            headers=AUTH,
        )
        assert lint.json()["problems"] == []
        signature = client.post(
            "/workbench/intel/signature",
            json={"text": "rainfall.head(", "offset": 14, "kernel": kernel},
            headers=AUTH,
        )
        assert signature.json()["signatures"][0]["params"][0]["name"] == "n"
    finally:
        client.delete(f"/workbench/kernels/{kernel}", headers=AUTH)


def test_the_agent_reads_what_the_editors_show(client: TestClient, tmp_path: Path) -> None:
    problem = {
        "line": 1,
        "col": 1,
        "end_line": 1,
        "end_col": 4,
        "message": "`foo` is not defined",
        "severity": "error",
        "code": "F821",
    }
    assert (
        client.put(
            "/workbench/intel/problems", json={"document": "a.py", "problems": [problem]}, headers=AUTH
        ).status_code
        == 200
    )
    found = client.get("/workbench/intel/problems", headers=AGENT).json()
    assert found["counts"]["error"] == 1 and found["documents"][0]["document"] == "a.py"
    script = tmp_path / "b.py"
    script.write_text("import os\n", encoding="utf-8")
    found = client.get(f"/workbench/intel/problems?path={script}", headers=AGENT).json()
    assert found["documents"][0]["problems"][0]["code"] == "F401"
    client.put("/workbench/intel/problems", json={"document": "a.py", "problems": []}, headers=AUTH)
    assert client.get("/workbench/intel/problems", headers=AGENT).json()["documents"] == []
    agent = client.post(
        "/workbench/intel/complete", json={"text": 'sab.connection("', "offset": 16}, headers=AGENT
    )
    assert agent.status_code == 200
