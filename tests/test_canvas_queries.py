"""SQL and DAX cells as canvas blocks (the owner, 2026-11-19: "did we add DAX cells to the canvas?").

A `%%sql <connection>` or `%%dax <connection>/<dataset>` cell goes on a page as a block. Its page code is the
script exporter's own translation of the cell (domain/script_export.py `query_cell`), a call of sab_queries.py
beside the pages: each connection written out as an export writes it, so the page runs under plain Streamlit
with no magic line. A page value the query names (`{{ region }}`) is bound as a parameter (SQL) or written as
a DAX literal; never pasted into the text. The result shows as a table, a chart or a metric (the block's view)
and is cached on the query and its values. Made-up data only."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import textwrap
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks
from swissarmybench.domain import script_export as exporter
from swissarmybench.domain import script_runtime as runtime
from swissarmybench_streamlit.domain import streamlit_cells as rules
from swissarmybench_streamlit.domain.streamlit_cells import Block, Page, PieceCode
from tests import powerbi_standin as made_up
from tests.conftest import AUTH, make_client
from tests.test_connections import sqlite_connection
from tests.test_streamlit_apps import STREAMLIT_PYTHON, FakeRunner, _ok, needs_streamlit

FILTER = '# Region\nregion = st.selectbox("Region", ["East", "West"])'
QUERY = (
    "-- Orders in the region\n"
    "SELECT order_id, amount FROM orders WHERE region = {{ region }} ORDER BY order_id"
)


# ===== the block's code: the exporter's translation =====


def test_a_sql_cell_is_the_exporters_call_with_its_page_values_named() -> None:
    code = rules.query_code("sql", "Shop -> by_region", QUERY, 3)
    assert "%%" not in code
    assert code.startswith("# Orders in the region\nimport sab_queries\n")
    assert "by_region = sab_queries.sql('Shop', " in code and code.count("{'region': region})") == 1
    assert "st.dataframe(by_region)" in code
    # The run order counts the page value as a read, and the result as made.
    found = rules.facts(code)
    assert "region" in found.reads and "by_region" in found.makes
    # The call is read back as the exporter's cell (what sab_queries.py is written for).
    asked = rules.query_calls(code)
    assert [(c.kind, c.connection, c.source) for c in asked] == [("sql", "Shop", QUERY)]
    # The same translation the script exporter makes of that cell.
    cell = exporter.ExportCell("sql", QUERY, "Shop -> by_region", number=3)
    assert exporter.query_cell(cell).query == QUERY and exporter.query_cell(cell).target == "by_region"
    # A DAX cell: its dataset in the name; no result name: query_<n>; a cell's own name titles it.
    dax = rules.query_code("dax", "Finance/Sales model", "EVALUATE 'Customer'", 7, "Customer list")
    assert dax.startswith("# Customer list\n") and "query_7 = sab_queries.dax('Finance/Sales model', " in dax
    # No connection: the block says so on the page.
    assert "st.error('The SQL cell names no connection: pick one in its head.')" in rules.query_code(
        "sql", None, "select 1", 2
    )


def test_page_values_are_read_outside_strings_and_comments_only() -> None:
    sql = "SELECT '{{ a }}' AS t, \"{{ b }}\" FROM x -- {{ c }}\n"
    sql += "/* {{ d }} */ WHERE r = {{ region }} AND y = {{y}}"
    assert exporter.page_names(sql) == ["region", "y"]
    dax = "EVALUATE FILTER('T {{ t }}', 'T'[R] = {{ region }} && \"{{ s }}\" <> \"\" ) // {{ c }}"
    assert exporter.page_names(dax, dax=True) == ["region"]


def _runtime() -> dict[str, Any]:
    """sab_queries.py's own text, run here with a stand-in for Streamlit (its cache_data does nothing)."""
    fake = types.ModuleType("streamlit")
    fake.cache_data = lambda **kept: lambda function: function  # type: ignore[attr-defined]
    held = sys.modules.get("streamlit")
    sys.modules["streamlit"] = fake
    try:
        space: dict[str, Any] = {}
        text = "\n".join(
            [runtime.IMPORTS, "SETTINGS = {}", runtime.SQL_HELPERS, runtime.PAGE_PARTS, runtime.PAGE_QUERIES]
        )
        exec(compile(text, "sab_queries.py", "exec"), space)  # noqa: S102 (our own text)
        return space
    finally:
        if held is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = held


def test_sql_values_are_bound_in_the_drivers_own_style_never_pasted() -> None:
    space = _runtime()
    bind = space["bind_sql"]
    query = "SELECT * FROM t WHERE r = {{ region }} AND s LIKE '50%' AND n > {{ low }}"
    assert bind(query, {"region": "West'; DROP TABLE t; --", "low": 3}, "qmark") == (
        "SELECT * FROM t WHERE r = ? AND s LIKE '50%' AND n > ?",
        ["West'; DROP TABLE t; --", 3],
    )
    assert bind(query, {"region": "W", "low": 1}, "pyformat") == (
        "SELECT * FROM t WHERE r = %(p1)s AND s LIKE '50%%' AND n > %(p2)s",
        {"p1": "W", "p2": 1},
    )
    assert bind(query, {"region": "W", "low": 1}, "named")[0].endswith("r = :p1 AND s LIKE '50%' AND n > :p2")
    assert bind("SELECT 1", {}, "format") == ("SELECT 1", None)  # no value: the text as typed
    with pytest.raises(KeyError, match="region"):
        bind(query, {"low": 1}, "qmark")
    # A real driver: the value is data, never SQL.
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE orders (region TEXT, amount INT)")
    con.executemany("INSERT INTO orders VALUES (?, ?)", [("East", 1), ("West", 2), ("x' OR '1'='1", 3)])
    text, params = bind("SELECT amount FROM orders WHERE region = {{ r }}", {"r": "x' OR '1'='1"}, "qmark")
    assert con.execute(text, params).fetchall() == [(3,)]


def test_dax_values_are_written_as_dax_literals() -> None:
    import datetime

    space = _runtime()
    fill = space["fill_dax"]
    assert fill("EVALUATE FILTER('C', 'C'[R] = {{ r }})", {"r": 'Say "hi"'}) == (
        'EVALUATE FILTER(\'C\', \'C\'[R] = "Say ""hi""")'
    )
    value = space["dax_value"]
    assert value(None) == "BLANK()" and value(True) == "TRUE()" and value(2.5) == "2.5"
    assert value(datetime.date(2026, 3, 1)) == "DATE(2026, 3, 1)"
    assert value(["East", 2]) == '{"East", 2}'
    with pytest.raises(ValueError):
        value(float("nan"))
    # Inside a DAX string the name stays as typed.
    assert fill('EVALUATE ROW("x", "{{ r }}")', {}) == 'EVALUATE ROW("x", "{{ r }}")'


def test_the_view_is_a_table_a_chart_or_a_metric_and_the_cache_can_be_turned_off() -> None:
    code = rules.query_code("sql", "Shop -> by_region", QUERY, 3)
    assert rules.shown(code, {}) == code
    bar = rules.shown(code, rules.check_view({"as": "bar", "x": "order_id", "y": "amount"}))
    assert "st.bar_chart(by_region, x='order_id', y='amount')" in bar and "st.dataframe" not in bar
    metric = rules.shown(code, rules.check_view({"as": "metric", "column": "amount", "label": "First"}))
    assert "st.metric('First', sab_queries.one(by_region, 'amount'))" in metric
    off = rules.shown(code, rules.check_view({"as": "table", "cache": False}))
    assert "{'region': region}, cache=False)" in off
    assert rules.check_view({"as": "table"}) == {} and rules.check_view(None) == {}
    for bad in ({"as": "pie"}, {"as": "bar", "x": 3}, {"colour": "red"}, {"cache": "no"}):
        with pytest.raises(rules.StreamlitError):
            rules.check_view(bad)
    # The view is the block's own, written into the app's file and read back identical.
    page = Page("p1", "Orders", [Block("b1", "/w/a.ipynb", 3, view={"as": "line", "y": ["amount"]})])
    text = rules.write_app([page])
    assert '"view": {"as": "line", "y": ["amount"]}' in text and '"version": 2' in text
    again = rules.read_app(text)
    assert again[0].blocks[0].view == {"as": "line", "y": ["amount"]} and rules.write_app(again) == text


def test_the_export_has_sab_queries_and_no_magic(tmp_path: Path) -> None:
    code = rules.query_code("sql", "Shop -> by_region", QUERY, 2)
    pieces = {
        ("/w/a.ipynb", 1): PieceCode(1, "Region", FILTER),
        ("/w/a.ipynb", 2): PieceCode(2, "Orders", code),
    }
    page = Page("p1", "Orders", [Block("b1", "/w/a.ipynb", 1), Block("b2", "/w/a.ipynb", 2, row=2)])
    made = rules.export("Orders", [page], pieces, [])
    rules.with_queries(made, "# the module\n", ["pandas>=2.0"])
    written = made.files["app_pages/orders.py"]
    assert not any(line.lstrip().startswith("%%") for line in written.split("\n"))
    assert "import sab_queries" in written
    assert written.index("region = st.selectbox") < written.index("by_region = sab_queries.sql")
    assert made.files[rules.QUERY_FILE] == "# the module\n"
    assert "sab_queries" not in made.files["requirements.txt"] and "pandas" in made.files["requirements.txt"]


# ===== the real thing: a SQL block on SQLite, a DAX block on Power BI (stood in for) =====


@pytest.fixture
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, made_up.StandIn]]:
    powerbi = made_up.StandIn().start()
    for name, value in powerbi.environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("POWERBI_CLIENT_SECRET", made_up.SECRET)
    try:
        with make_client(tmp_path) as client:
            client.app.state.ctx.streamlit._runner = FakeRunner()  # type: ignore[attr-defined]
            yield client, powerbi
    finally:
        powerbi.stop()


def _shop(tmp_path: Path) -> Path:
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as made:
        made.execute("CREATE TABLE orders (order_id INTEGER, region TEXT, amount INTEGER)")
        made.executemany(
            "INSERT INTO orders VALUES (?, ?, ?)",
            [(1, "East", 100), (2, "West", 250), (3, "East", 40), (4, "West", 10)],
        )
    return database


def _finance(client: TestClient) -> None:
    from swissarmybench.server.blade_templates import POWERBI_TYPED

    code = POWERBI_TYPED.replace("my-workspace-id", made_up.WORKSPACE)
    code = code.replace('"my-tenant-id"', f'"{made_up.TENANT}"').replace(
        '"my-client-id"', f'"{made_up.CLIENT}"'
    )
    source = {"code": code, "secret": "client secret", "from": "env", "env": "POWERBI_CLIENT_SECRET"}
    code = _ok(client.post("/connections/source", headers=AUTH, json=source))["code"]
    workspace = {"name": "Finance", "kind": "sql", "template": "powerbi", "dialect": "dax", "code": code}
    _ok(client.post("/connections", headers=AUTH, json=workspace | {"variable": "conn"}))


APP_TEST = textwrap.dedent(
    """
    import json, sys
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(sys.argv[1], default_timeout=60).run()
    first = [list(f.value.iloc[:, 0]) if f.value.shape[1] else [] for f in at.dataframe]
    errors = [str(e.value) for e in at.exception] + [e.value for e in at.error]
    at.selectbox[0].set_value(sys.argv[2]).run()
    second = [list(f.value.iloc[:, 0]) if f.value.shape[1] else [] for f in at.dataframe]
    errors += [str(e.value) for e in at.exception] + [e.value for e in at.error]
    print(json.dumps({"first": first, "second": second, "errors": errors}, default=str))
    """
)


def _app_test(page: Path, pick: str, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    assert STREAMLIT_PYTHON is not None
    done = subprocess.run(  # noqa: S603 (a Python with Streamlit, our own test)
        [STREAMLIT_PYTHON, "-c", APP_TEST, str(page), pick],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
        cwd=cwd,
        env=env,
    )
    assert done.returncode == 0, done.stderr[-3000:]
    return dict(json.loads(done.stdout.strip().splitlines()[-1]))


def _place(client: TestClient, notebook: Path, cells: list[int]) -> str:
    app = _ok(
        client.post("/streamlit/apps", headers=AUTH, json={"canvas": True, "title": "q", "window": "w1"})
    )
    base = f"/streamlit/apps/{app['app']}"
    _ok(
        client.post(
            f"{base}/pages",
            headers=AUTH,
            json={"name": "Orders", "document": str(notebook), "cell": cells[0]},
        )
    )
    for row, cell in enumerate(cells[1:], start=2):
        _ok(
            client.post(
                f"{base}/pages/p1/blocks",
                headers=AUTH,
                json={"document": str(notebook), "cell": cell, "row": row},
            )
        )
    return base


@needs_streamlit
def test_a_sql_block_on_sqlite_plays_exports_and_runs_with_a_select_feeding_where(
    served: tuple[TestClient, made_up.StandIn], tmp_path: Path
) -> None:
    import os

    client, _ = served
    database = _shop(tmp_path)
    _ok(client.post("/connections", headers=AUTH, json=sqlite_connection(database)))
    notebook = tmp_path / "app.ipynb"
    cells = [notebooks.Cell("code", FILTER), notebooks.Cell("sql", QUERY, "Shop -> by_region")]
    notebook.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    base = _place(client, notebook, [1, 2])
    # Play writes sab_queries.py beside the pages.
    _ok(client.post(f"{base}/run", headers=AUTH, json={}))
    played = Path(client.app.state.ctx.streamlit._runner.started[-1][1])  # type: ignore[attr-defined]
    assert (played / rules.QUERY_FILE).is_file()
    out = tmp_path / "out"
    done = _ok(client.post(f"{base}/export", headers=AUTH, json={"folder": str(out)}))
    assert "sab_queries.py" in done["files"] and not done["problems"], done
    page = (out / "app_pages" / "orders.py").read_text(encoding="utf-8")
    module = (out / "sab_queries.py").read_text(encoding="utf-8")
    assert not any(line.lstrip().startswith(("%%", "%sql")) for line in (page + module).split("\n"))
    assert "def connect_shop" in module
    assert "{'region': region}" in page
    seen = _app_test(out / "app_pages" / "orders.py", "West", out, dict(os.environ))
    assert seen["errors"] == []
    assert seen["first"] == [[1, 3]] and seen["second"] == [[2, 4]]  # the select fed WHERE region = ?


@needs_streamlit
def test_a_dax_block_on_power_bi_plays_exports_and_runs_with_a_select_feeding_its_filter(
    served: tuple[TestClient, made_up.StandIn], tmp_path: Path
) -> None:
    import os

    client, powerbi = served
    _finance(client)
    notebook = tmp_path / "app.ipynb"
    dax = "EVALUATE FILTER('Customer', 'Customer'[Region] = {{ region }})"
    cells = [notebooks.Cell("code", FILTER), notebooks.Cell("dax", dax, "Finance/Sales model -> customers")]
    notebook.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    base = _place(client, notebook, [1, 2])
    out = tmp_path / "out"
    done = _ok(client.post(f"{base}/export", headers=AUTH, json={"folder": str(out)}))
    assert not done["problems"], done
    module = (out / "sab_queries.py").read_text(encoding="utf-8")
    assert made_up.SECRET not in module and "POWERBI_CLIENT_SECRET" in module
    env = dict(os.environ) | powerbi.environment() | {"POWERBI_CLIENT_SECRET": made_up.SECRET}
    seen = _app_test(out / "app_pages" / "orders.py", "West", out, env)
    assert seen["errors"] == [], seen
    east = [c["CustomerKey"] for c in made_up.tables()["Customer"] if c["Region"] == "East"]
    west = [c["CustomerKey"] for c in made_up.tables()["Customer"] if c["Region"] == "West"]
    assert seen["first"] == [east] and seen["second"] == [west]
    asked = [r for r in powerbi.requests if r.get("what") == "query"]
    assert any('= \\"West\\"' in json.dumps(r) or '= "West"' in json.dumps(r) for r in asked)
