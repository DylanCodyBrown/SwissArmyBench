"""Lineage (docs/ideas.md, lineage with values and approved outputs, 2026-11-15): from a canvas block or
any cell, back through every cell to the data: what cells make and read, @cell links, the tables'
origins and their grid steps, a project's data.ipynb and the controllers; its Mermaid text; each step's
value, summarised. Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.cli.commands import REGISTRY
from swissarmybench.client import lineage_values as values
from swissarmybench.domain import lineage as rules
from swissarmybench.domain import notebooks
from tests.conftest import AGENT, AUTH, make_client, push

SERVED_ORDERS = pa.table(
    {
        "order_id": [1, 2, 3, 4, 5, 6],
        "region": ["East", "West", "East", "North", "West", "East"],
        "amount": [100, 250, 40, 75, 10, 5],
    }
)
CUSTOMERS = pa.table({"customer": ["Acme", "Globex"], "region": ["East", "West"]})


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, None]]:
    """The server with made-up orders and customers open."""
    with make_client(tmp_path) as client:
        assert push(client, "orders", SERVED_ORDERS).status_code == 200
        assert push(client, "customers", CUSTOMERS).status_code == 200
        yield client, None


BOOK = "/work/sales/analysis.ipynb"
DATA = "/work/sales/data.ipynb"
SCRIPT = "/work/sales/report.py"


def cell(number: int, code: str, **more: Any) -> rules.DocCell:
    return rules.DocCell(number, more.pop("kind", "code"), code, **more)


def book(*cells: rules.DocCell, path: str = BOOK, data: bool = False) -> rules.Document:
    return rules.Document(path, tuple(cells), data=data)


ORDERS = rules.TableFacts(
    "orders",
    "orders",
    origin="file",
    source="orders.csv",
    steps=("Keep rows where amount > 10", "Sort by amount"),
)


def labels(graph: rules.Graph) -> list[str]:
    return [n.label for n in graph.nodes]


def edge_names(graph: rules.Graph) -> set[tuple[str, str, str]]:
    by_id = {n.id: n.label for n in graph.nodes}
    return {(by_id[e.source], by_id[e.target], e.name) for e in graph.edges}


# ===== makes and reads =====


def test_a_cell_is_traced_back_through_the_cells_that_make_what_it_reads() -> None:
    doc = book(
        cell(1, "import pandas as pd"),
        cell(2, 'region = "East"', name="Region"),
        cell(3, "rate = 0.2"),
        cell(4, "unused = 5"),
        cell(5, "total = 100 * rate\nshown = f'{region}: {total}'", name="Total"),
    )
    graph = rules.trace((BOOK, 5), {BOOK: doc}, {})
    assert labels(graph)[-1] == "Total"
    assert set(labels(graph)) == {"Region", "rate = 0.2", "Total"}  # no import, nothing it does not read
    assert labels(graph) == ["Region", "rate = 0.2", "Total"]  # cells that wait on nothing: in file order
    assert ("Region", "Total", "region") in edge_names(graph)
    assert graph.nodes[-1].target and graph.nodes[-1].where == "analysis.ipynb @cell5"


def test_the_nearest_maker_above_is_the_one_read() -> None:
    doc = book(cell(1, "x = 1"), cell(2, "x = 2"), cell(3, "y = x + 1"), cell(4, "x = 9"))
    graph = rules.trace((BOOK, 3), {BOOK: doc}, {})
    assert [n.cell for n in graph.nodes] == [2, 3]


def test_flow_order_puts_every_maker_before_what_reads_it() -> None:
    doc = book(cell(1, "a = 1"), cell(2, "b = a + 1"), cell(3, "c = a + b"), cell(4, "d = c * 2"))
    graph = rules.trace((BOOK, 4), {BOOK: doc}, {})
    order = [n.cell for n in graph.nodes]
    assert order == [1, 2, 3, 4]


def test_a_cell_link_in_a_comment_is_an_edge_too() -> None:
    doc = book(cell(1, "notes = 'made-up'"), cell(2, "# checked against @cell1\nfinal = 3"))
    graph = rules.trace((BOOK, 2), {BOOK: doc}, {})
    [edge] = graph.edges
    assert edge.kind == "link" and [n.cell for n in graph.nodes] == [1, 2]


def test_a_cycle_does_not_walk_forever() -> None:
    doc = book(cell(1, "# see @cell2\na = 1"), cell(2, "# see @cell1\nb = a"))
    graph = rules.trace((BOOK, 2), {BOOK: doc}, {})
    assert sorted(n.cell or 0 for n in graph.nodes) == [1, 2]


# ===== tables: their cells, grid steps and origins =====


def test_a_table_goes_back_through_its_grid_steps_to_its_file() -> None:
    doc = book(
        cell(1, "orders = duckdb.sql('...').df()", role="transformations", table="orders"),
        cell(2, "big = orders[orders.amount > 100]", name="Big orders"),
    )
    graph = rules.trace((BOOK, 2), {BOOK: doc}, {"orders": ORDERS})
    assert [n.kind for n in graph.nodes] == ["source", "step", "step", "table", "cell"]
    assert labels(graph)[:3] == ["orders.csv", "Keep rows where amount > 10", "Sort by amount"]
    table = graph.nodes[3]
    assert table.label == "orders" and table.cell == 1 and table.table == "orders"
    assert graph.nodes[1].step == 1 and graph.nodes[2].step == 2


def test_a_table_with_a_maker_cell_starts_from_that_cell() -> None:
    doc = book(
        cell(1, "orders = pd.read_csv('orders.csv')", role="maker", table="orders"),
        cell(2, "orders = duckdb.sql('...').df()", role="transformations", table="orders"),
        cell(3, "total = orders.amount.sum()"),
    )
    graph = rules.trace((BOOK, 3), {BOOK: doc}, {"orders": ORDERS})
    kinds = [(n.kind, n.label) for n in graph.nodes]
    assert kinds[0] == ("source", "orders.csv")  # read in the maker's own code
    assert kinds[1][0] == "cell" and graph.nodes[1].cell == 1
    assert [k for k, _ in kinds[2:]] == ["step", "step", "table", "cell"]


def test_an_open_table_no_document_holds_is_the_grid_itself() -> None:
    warehouse = rules.TableFacts("customers", "customers", origin="connection", source="Warehouse")
    doc = book(cell(1, "n = len(customers)"))
    graph = rules.trace((BOOK, 1), {BOOK: doc}, {"customers": warehouse})
    assert [(n.kind, n.label) for n in graph.nodes] == [
        ("source", "Warehouse"),
        ("table", "customers"),
        ("cell", "n = len(customers)"),
    ]
    assert graph.nodes[1].where == "the grid"


def test_a_sql_cell_reads_its_connection_and_makes_its_name() -> None:
    doc = book(
        cell(1, "SELECT * FROM orders", kind="sql", connection="Shop -> recent"),
        cell(2, "count = len(recent)"),
    )
    graph = rules.trace((BOOK, 2), {BOOK: doc}, {})
    assert (graph.nodes[0].kind, graph.nodes[0].label) == ("source", "Shop")
    assert graph.nodes[1].cell == 1 and graph.nodes[1].makes == ("recent",)


def test_connections_and_files_named_in_code_are_sources() -> None:
    doc = book(
        cell(1, "shop = sab.sql('Shop', 'SELECT 1')\nrates = pd.read_parquet(r'C:\\data\\rates.parquet')")
    )
    graph = rules.trace((BOOK, 1), {BOOK: doc}, {})
    assert {(n.kind, n.label) for n in graph.nodes if n.kind == "source"} == {
        ("source", "Shop"),
        ("source", "rates.parquet"),
    }


# ===== controllers, text cells, data.ipynb, a canvas page =====


def test_a_widget_cell_is_a_controller() -> None:
    doc = book(
        cell(1, 'region = st.selectbox("Region", ["East", "West"])'),
        cell(2, "# Total\nst.metric('Total', region)"),
    )
    graph = rules.trace((BOOK, 2), {BOOK: doc}, {})
    assert graph.nodes[0].kind == "controller"


def test_a_markdown_cell_reads_its_named_values() -> None:
    doc = book(cell(1, "total = 3"), cell(2, "Total: **{{ total }}**", kind="markdown"))
    graph = rules.trace((BOOK, 2), {BOOK: doc}, {})
    assert [n.kind for n in graph.nodes] == ["cell", "text"]


def test_a_name_imported_from_data_goes_back_into_data_ipynb() -> None:
    data = book(
        cell(1, "orders = duckdb.sql('...').df()", role="transformations", table="orders"),
        cell(2, "by_region = orders.groupby('region').amount.sum()", name="By region"),
        path=DATA,
        data=True,
    )
    doc = book(cell(1, "from data import by_region"), cell(2, "top = by_region.max()"))
    graph = rules.trace((BOOK, 2), {BOOK: doc, DATA: data}, {"orders": ORDERS}, data=DATA)
    by_label = {n.label: n for n in graph.nodes}
    assert by_label["By region"].document == DATA and by_label["By region"].doc_kind == "data"
    assert "orders" in by_label
    assert all(n.cell != 1 or n.document != BOOK for n in graph.nodes)  # the import line is no step


def test_a_block_on_a_page_reads_the_other_blocks_first() -> None:
    doc = book(
        cell(1, 'region = "West"'),
        cell(2, 'region = st.selectbox("Region", ["East", "West"])', name="Region filter"),
        cell(3, "st.metric('Total', region)", name="Total"),
    )
    page = [(BOOK, 3), (BOOK, 2)]
    graph = rules.trace((BOOK, 3), {BOOK: doc}, {}, page=page)
    assert [n.cell for n in graph.nodes] == [2, 3]
    assert graph.nodes[-1].on_page and graph.nodes[0].on_page


def test_a_script_cell_is_green_and_a_notebook_blue() -> None:
    doc = book(cell(1, "a = 1"), cell(2, "b = a"), path=SCRIPT)
    graph = rules.trace((SCRIPT, 2), {SCRIPT: doc}, {})
    assert {n.doc_kind for n in graph.nodes} == {"script"}


def test_an_unknown_target_is_refused() -> None:
    with pytest.raises(rules.LineageError, match="no cell 9"):
        rules.trace((BOOK, 9), {BOOK: book(cell(1, "a = 1"))}, {})


# ===== the Mermaid text =====


def test_the_mermaid_text_is_a_flowchart_with_safe_labels() -> None:
    doc = book(
        cell(1, 'say = "a"', name='Quote " and <b>bold</b> # here'),
        cell(2, "out = say"),
    )
    graph = rules.trace((BOOK, 2), {BOOK: doc}, {})
    text = rules.mermaid(graph, {graph.nodes[0].id: "'a'"})
    assert text.startswith("flowchart TD")
    assert "<b>" not in text and '" and' not in text
    assert "#quot;" in text and "#lt;b#gt;" in text
    assert f"{graph.nodes[0].id} -->|say| {graph.nodes[1].id}" in text
    assert f"class {graph.nodes[1].id} target" in text


def test_the_graph_as_json_has_nodes_edges_and_its_mermaid() -> None:
    doc = book(cell(1, "a = 1"), cell(2, "b = a"))
    said = rules.trace((BOOK, 2), {BOOK: doc}, {}).to_json()
    assert set(said) >= {"nodes", "edges", "mermaid", "target"}
    assert said["nodes"][0] | {} == said["nodes"][0] and said["nodes"][0]["where"] == "analysis.ipynb @cell1"
    json.dumps(said)


# ===== values, summarised (the kernel's side and a live page's) =====


def test_a_table_value_is_its_shape_and_first_rows_only() -> None:
    many = pd.DataFrame({"n": range(1_000), "region": ["East"] * 1_000})
    found = values.summary(many)
    assert found["kind"] == "table" and found["rows"] == 1_000 and found["columns"] == 2
    assert len(found["head"]) == values.HEAD_ROWS and found["names"] == ["n", "region"]


def test_a_single_value_is_itself_and_long_text_is_cut() -> None:
    assert values.summary(390)["text"] == "390"
    assert len(values.summary("x" * 10_000)["text"]) <= values.TEXT_CHARS


def test_summaries_say_what_this_python_does_not_hold() -> None:
    found = json.loads(values.summaries(["total", "nowhere"], {"total": 3}))
    assert found["total"]["text"] == "3" and found["nowhere"]["kind"] == "missing"


def test_a_live_page_notes_each_blocks_values_in_its_folder(tmp_path: Path) -> None:
    here = str(tmp_path / "page_p1_3.py")
    values.start(here, "p1")
    values.note(here, "p1", "b1", {"region": lambda: "West"})

    def unmade() -> Any:
        raise NameError("total")

    values.note(here, "p1", "b2", {"total": unmade}, error=ValueError("made-up"))
    said = json.loads((tmp_path / "lineage-p1.json").read_text(encoding="utf-8"))
    assert said["blocks"]["b1"]["values"]["region"]["text"] == "West"
    assert said["blocks"]["b2"]["error"] == "ValueError: made-up"


# ===== over HTTP: the documents as they are now, the grid's values, a live page's =====

STEP = {"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 50}}


def _ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_a_cells_lineage_from_its_window_with_the_grids_values(served: Any) -> None:
    client, _ = served
    grid = next(
        g["grid"] for g in _ok(client.get("/grids", headers=AUTH))["grids"] if g["dataset"] == "orders"
    )
    _ok(client.post(f"/grids/{grid}/steps", headers=AUTH, json={"steps": [STEP]}))
    cells = [
        {
            "kind": "code",
            "source": "orders = duckdb.sql('...').df()",
            "number": 1,
            "role": "transformations",
            "table": "orders",
        },
        {"kind": "code", "source": "big = orders[orders.amount > 200]", "number": 2, "name": "Big orders"},
    ]
    said = _ok(
        client.post(
            "/workbench/lineage",
            headers=AUTH,
            json={"document": "/made/up/a.ipynb", "cell": 2, "cells": cells},
        )
    )
    kinds = [(n["kind"], n["label"]) for n in said["nodes"]]
    assert kinds == [
        ("step", "Keep rows where amount is greater than 50"),
        ("table", "orders"),
        ("cell", "Big orders"),
    ]
    step, table, mine = said["nodes"]
    # No kernel ran it: the grid says what the step and the table hold, and the row change.
    assert said["values"][step["id"]]["items"][0]["rows"] == 3
    assert said["values"][step["id"]]["items"][0]["change"] == -3  # 6 rows before the step
    held = said["values"][table["id"]]["items"][0]
    assert held["rows"] == 3 and held["names"] == ["order_id", "region", "amount"] and len(held["head"]) == 3
    assert held["change"] == 0
    assert said["values"].get(mine["id"]) is None
    assert said["mermaid"].startswith("flowchart TD") and "3 rows" in said["mermaid"]
    # The graph alone, and a target that is not there.
    bare = _ok(
        client.post(
            "/workbench/lineage",
            headers=AUTH,
            json={"document": "/made/up/a.ipynb", "cell": 2, "cells": cells, "values": False},
        )
    )
    assert "values" not in bare
    refused = client.post(
        "/workbench/lineage", headers=AUTH, json={"document": "/made/up/a.ipynb", "cell": 9, "cells": cells}
    )
    assert refused.status_code == 400 and "no cell 9" in refused.text


def test_a_cells_error_in_its_window_is_where_the_flow_broke(served: Any) -> None:
    client, _ = served
    cells = [
        {"kind": "code", "source": "total = 3", "number": 1},
        {"kind": "code", "source": "half = total / zero", "number": 2},
    ]
    said = _ok(
        client.post(
            "/workbench/lineage",
            headers=AUTH,
            json={
                "document": "/made/up/b.ipynb",
                "cell": 2,
                "cells": cells,
                "errors": {"2": "NameError: name 'zero' is not defined"},
            },
        )
    )
    last = said["nodes"][-1]["id"]
    assert said["values"][last]["error"].startswith("NameError") and "error" in said["mermaid"]


def test_a_project_cell_goes_back_into_data_ipynb(served: Any, tmp_path: Path) -> None:
    client, _ = served
    data = [
        notebooks.Cell(
            "code", "orders = duckdb.sql('...').df()", number=1, role="transformations", table="orders"
        ),
        notebooks.Cell(
            "code", "by_region = orders.groupby('region').amount.sum()", number=2, name="By region"
        ),
    ]
    (tmp_path / "data.ipynb").write_text(notebooks.write_notebook(data), encoding="utf-8")
    cells = [
        notebooks.Cell("code", "from data import by_region", number=1),
        notebooks.Cell("code", "top = by_region.max()", number=2),
    ]
    mine = tmp_path / "analysis.ipynb"
    mine.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    said = _ok(client.post("/workbench/lineage", headers=AUTH, json={"document": str(mine), "cell": 2}))
    by_label = {n["label"]: n for n in said["nodes"]}
    assert (
        by_label["By region"]["doc_kind"] == "data" and by_label["By region"]["where"] == "data.ipynb @cell2"
    )
    assert by_label["orders"]["document"].endswith("data.ipynb")


def _notebook(folder: Path) -> Path:
    """A saved notebook: imports (1), a note, the filter (3), the total (4), plain Python (5)."""
    cells = [
        notebooks.Cell("code", "import pandas as pd"),
        notebooks.Cell("markdown", "# Sales"),
        notebooks.Cell("code", '# Region filter\nregion = "East"'),
        notebooks.Cell("code", '# Total\nprint(int(orders[orders["region"] == region]["amount"].sum()))'),
        notebooks.Cell("code", "threshold = 50"),
    ]
    path = folder / "sales.ipynb"
    path.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    return path


def test_the_agent_reads_a_lineage_as_data(served: Any, tmp_path: Path) -> None:
    client, _ = served
    path = str(_notebook(tmp_path))
    said = _ok(client.post("/workbench/lineage", headers=AGENT, json={"document": path, "cell": 4}))
    assert said["nodes"][-1]["label"] == "Total"
    assert REGISTRY["workbench_lineage"].values is True  # its values come back marked as the user's data
