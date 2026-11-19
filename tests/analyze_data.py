"""Made-up tables for the Analyze tests, and a table's facts read with a plain DuckDB (the same queries
the server runs: domain/analyze.py facts_query, values_query, sample_query)."""

from __future__ import annotations

import datetime as dt
from typing import Any

import duckdb
import pyarrow as pa

from swissarmybench.domain import analysis_contracts as C
from swissarmybench.domain import analyze as Z


def facts_of(table: pa.Table) -> tuple[int, list[Z.Facts]]:
    """(rows, facts) of an Arrow table, as the server reads them."""
    con = duckdb.connect()
    con.register("t", table)
    columns = [(str(name), str(kind)) for name, kind, *_ in con.execute("DESCRIBE t").fetchall()]
    row = con.execute(Z.facts_query("t", columns)).fetchone()
    names = [name for name, _ in columns]
    _, first = Z.read_facts(columns, row)
    few = [f.name for f in first if 0 < f.distinct <= Z.VALUES_KEPT]
    values: dict[str, list[tuple[str, int]]] = {}
    if few:
        for i, v, n in con.execute(Z.values_query("t", few)).fetchall():
            values.setdefault(few[i], []).append((str(v), int(n)))
    samples: dict[str, list[str]] = {}
    for i, v in con.execute(Z.sample_query("t", names)).fetchall():
        samples.setdefault(names[i], []).append(str(v))
    return Z.read_facts(columns, row, samples, values)


def run_steps(table: pa.Table, steps: list[dict[str, Any]]) -> pa.Table:
    """A fix's steps run over a table the way the grid would: `grid` is the stage before each step."""
    from swissarmybench.adapters.database import describer, duckdb_grammar
    from swissarmybench.domain.datasets import Column
    from swissarmybench.domain.steps import Step, ViewSettings, compile_view

    con = duckdb.connect()
    con.register("ds", table)
    con.execute('CREATE TABLE "made" AS SELECT * FROM ds')
    describe = describer(con)
    base = tuple(Column(name, kind) for name, kind in describe('SELECT * FROM "made"'))
    compiled = compile_view(
        describe,
        duckdb_grammar(),
        '"made"',
        base,
        [Step.from_json(s, i) for i, s in enumerate(steps)],
        ViewSettings(),
        "made",
    )
    if compiled.error is not None:
        raise AssertionError(f"the step did not compile: {compiled.error}")
    return con.sql(compiled.sql()).to_arrow_table()


def sample_table(sample: dict[str, Any]) -> pa.Table:
    """A contract's made-up sample as an Arrow table (dates typed, as a real table's would be)."""
    columns = sample["columns"]
    data: dict[str, list[Any]] = {name: [row[name] for row in sample["rows"]] for name in columns}
    for name in columns:
        if name in C.SAMPLE_DATES:
            data[name] = [dt.date.fromisoformat(v) for v in data[name]]
    return pa.table(data)


def orders(n: int = 240) -> pa.Table:
    """A made-up orders table that suits most analyses: a date, amounts spanning orders of magnitude,
    a region, a yes/no, a count."""
    regions = ["West", "North", "East", "South"]
    return pa.table(
        {
            "order_id": [f"O-{1000 + i}" for i in range(n)],
            "order_date": [dt.date(2024, 1, 1) + dt.timedelta(days=3 * i) for i in range(n)],
            "region": [regions[(i * 3 + i // 5) % 4] for i in range(n)],
            "units": [1 + (i * 7) % 12 for i in range(n)],
            "amount": [round(10 ** (1 + (i * 37 % 300) / 100) + i % 7, 2) for i in range(n)],
            "late": ["yes" if (i % 4 == 0 or (i % 3 == 0 and i % 5 < 2)) else "no" for i in range(n)],
        }
    )
