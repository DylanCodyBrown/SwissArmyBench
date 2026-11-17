"""Every Streamlit starter piece runs, filled, under Streamlit's own test runner (AppTest) with a made-up
table, without an error; and the five pieces of the user guide's "Learning Streamlit" page run together
as one page, in the order their names need.

Streamlit is never the app's dependency: these run in a Python that has it, named by
SWISSARMYBENCH_STREAMLIT_PYTHON (a throwaway environment), else this Python if it has it; without one
they are skipped (the reason says so)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from swissarmybench.domain.blades import read_blade
from swissarmybench.domain.snippets import fill
from swissarmybench.renamed import env
from swissarmybench_streamlit.domain.streamlit_cells import Facts, facts, run_order

FOLDER = Path(__file__).resolve().parents[1] / "extensions" / "streamlit" / "src" / "swissarmybench_streamlit"
FOLDER = FOLDER / "starters"  # the Streamlit extension's starters
PIECES = [read_blade(p.read_text(encoding="utf-8")) for p in sorted(FOLDER.glob("streamlit_*.blade.py"))]
# The made-up table's columns, by placeholder.
VALUES = {
    "table": "orders",
    "column": "region",
    "date column": "order_date",
    "value column": "amount",
    "flag column": "shipped",
    "category column": "region",
    "number column": "amount",
    "search column": "product",
    "x column": "region",
    "y column": "amount",
    "colour column": "region",
    "wait seconds": "0",
}
TABLE = """import pandas as pd

orders = pd.DataFrame(
    {
        "region": ["North", "South", "East", "West"] * 10,
        "product": ["Widget", "Gadget", "Gizmo", "Doohickey", "Widget"] * 8,
        "order_date": pd.date_range("2026-01-01", periods=40, freq="3D"),
        "amount": [round(10 + (i * 7.3) % 90, 2) for i in range(40)],
        "quantity": [1 + i % 5 for i in range(40)],
        "shipped": [i % 3 != 0 for i in range(40)],
        "lat": [51.5 + (i % 7) * 0.1 for i in range(40)],
        "lon": [-0.12 + (i % 5) * 0.1 for i in range(40)],
    }
)
"""
RUNNER = """
import json, sys
from streamlit.testing.v1 import AppTest

found = {}
for path in sys.argv[1:]:
    at = AppTest.from_file(path, default_timeout=60).run()
    found[path] = [str(e.value) for e in at.exception] + [f"error box: {e.value}" for e in at.error]
print(json.dumps(found))
"""


def _streamlit_python() -> str | None:
    for python in (env("SWISSARMYBENCH_STREAMLIT_PYTHON"), sys.executable):
        if not python:
            continue
        probe = subprocess.run(  # noqa: S603 (a Python named by the tester, or this one)
            [python, "-c", "import streamlit.testing.v1, pandas, openpyxl"], capture_output=True, timeout=120
        )
        if probe.returncode == 0:
            return python
    return None


PYTHON = _streamlit_python()
needs_streamlit = pytest.mark.skipif(
    PYTHON is None,
    reason="no Python with Streamlit, pandas and openpyxl here (set SWISSARMYBENCH_STREAMLIT_PYTHON to one)",
)


def _script(code: str) -> str:
    """The piece as a page of its own: the made-up table, each other name it reads as the table (the
    rows another filter would leave), then the piece."""
    found = facts(code)
    more = [f"{name} = orders" for name in found.reads if name != "orders"]
    return TABLE + "\n".join(more) + "\n\n" + code + "\n"


def _run(scripts: dict[str, str], folder: Path) -> dict[str, list[str]]:
    paths = []
    for name, text in scripts.items():
        path = folder / f"{name.replace(' ', '_')}.py"
        path.write_text(text, encoding="utf-8")
        paths.append(str(path))
    environment = os.environ | {"STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
    done = subprocess.run(  # noqa: S603 (the tester's Streamlit Python, on files this test wrote)
        [str(PYTHON), "-I", "-c", RUNNER, *paths],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=folder,
        env=environment,
    )
    assert done.returncode == 0, done.stderr[-3000:]
    answer: dict[str, list[str]] = json.loads(done.stdout.strip().splitlines()[-1])
    return {Path(path).stem: problems for path, problems in answer.items()}


@pytest.mark.parametrize("name", ["Streamlit bar chart", "Streamlit line chart", "Streamlit area chart"])
def test_a_chart_piece_draws_a_databases_decimals_as_numbers(name: str) -> None:
    """The test bed's use case 11: PostgreSQL's numeric amounts arrive as Python Decimals (an object
    column), and the bar chart drew each total as a name on its axis, the bars floating."""
    import types
    from decimal import Decimal

    import pandas as pd

    drawn: dict[str, pd.DataFrame] = {}
    st = types.ModuleType("streamlit")
    for chart in ("bar_chart", "line_chart", "area_chart"):
        setattr(st, chart, lambda data, **_: drawn.setdefault("data", data))
    orders = pd.DataFrame(
        {
            "region": ["North", "South", "North"],
            "order_date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-02-01"]),
            "amount": [Decimal("10.50"), Decimal("7.25"), Decimal("3.00")],
        }
    )
    code = fill(next(p for p in PIECES if p["name"] == name)["code"], "streamlit", VALUES)
    saved = sys.modules.get("streamlit")
    sys.modules["streamlit"] = st
    try:
        exec(code, {"orders": orders})  # noqa: S102 (the starter pack's own code)
    finally:
        if saved is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = saved
    assert pd.api.types.is_float_dtype(drawn["data"]["amount"])


@needs_streamlit
def test_every_piece_runs_under_streamlits_own_test_runner(tmp_path: Path) -> None:
    scripts = {p["name"]: _script(fill(p["code"], "streamlit", VALUES)) for p in PIECES}
    problems = {name: found for name, found in _run(scripts, tmp_path).items() if found}
    assert problems == {}
    assert len(scripts) == 29


# The guide's page: a region filter, a date range, a metric row, a chart and a table, snapped together
# by their names (docs/user-guide.md, "Learning Streamlit with the starter pieces").
GUIDE: list[tuple[str, dict[str, str]]] = [
    ("Streamlit selectbox filter", {"table": "orders", "column": "region", "name": "by_region"}),
    ("Streamlit date range filter", {"table": "by_region", "date column": "order_date", "name": "in_dates"}),
    ("Streamlit metric row", {"table": "in_dates", "value column": "amount"}),
    ("Streamlit bar chart", {"table": "in_dates", "x column": "product", "y column": "amount"}),
    (
        "Streamlit formatted table",
        {"table": "in_dates", "value column": "amount", "date column": "order_date", "title": "Orders"},
    ),
]


def _guide_codes() -> list[tuple[str, str]]:
    by_name = {p["name"]: p for p in PIECES}
    return [(name, fill(by_name[name]["code"], "streamlit", values)) for name, values in GUIDE]


def test_the_guides_five_pieces_snap_together_by_their_names() -> None:
    codes = _guide_codes()
    found: list[tuple[str, Facts]] = [(name, facts(code)) for name, code in codes]
    ordered = run_order(list(reversed(found)))  # placed in any order, they run in the order names need
    assert ordered.cycle == ()
    order = list(ordered.order)
    assert order.index("Streamlit selectbox filter") < order.index("Streamlit date range filter")
    assert order.index("Streamlit date range filter") < order.index("Streamlit metric row")
    assert {(reader, name) for reader, name, _ in ordered.links} == {
        ("Streamlit date range filter", "by_region"),
        ("Streamlit metric row", "in_dates"),
        ("Streamlit bar chart", "in_dates"),
        ("Streamlit formatted table", "in_dates"),
    }


@needs_streamlit
def test_the_guides_page_runs_as_one_page(tmp_path: Path) -> None:
    page = TABLE + "\n\n".join(code for _, code in _guide_codes()) + "\n"
    assert _run({"guide page": page}, tmp_path) == {"guide_page": []}
