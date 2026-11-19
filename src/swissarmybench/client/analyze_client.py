"""`sab.analyze`: the Analyze page from Python (the owner, 2026-11-19).

    sab.analyze.benford(invoices)                      # the columns picked as the page picks them
    sab.analyze.odds(orders, column="region", outcome="late")
    sab.analyze.forecast(sales, horizon=3)             # options by their names
    sab.analyze.tie_out("orders", other="ledger")      # an open table by its name: run in the app
    sab.analyze.check(orders)                          # which analyses suit this table, and its fixes
    sab.analyze.contract("benford")                    # the analysis's data contract
    sab.analyze.sample("benford")                      # its made-up sample, as a DataFrame
    sab.analyze(fig, "Sales by month")                 # anything visual as a card on the Analyze board

Each analysis reads the same contract and goes through the same checker as the page's form and the agent's
analyze_run (domain/analysis_contracts.py, domain/analyze.py), and runs the function `swissarmybench.stats`
has (so the numbers are the window's). On a DataFrame it runs here, in this Python; when the app is running
its cards land on the Analyze board too (`board=False` keeps them off). A table that does not fit raises
ValueError with what is missing and how to make it fit. The result is a plain dictionary.

`sab.visualizations` is the old name of the card call (Visualizations became Analyze, 2026-11-19): it warns
once and goes with renamed.py. Importing this module needs only the standard library; an analysis on a
DataFrame needs the app's install (duckdb), as `swissarmybench.stats` does.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from swissarmybench.client.blades_client import _call
from swissarmybench.client.push_client import ServerNotRunningError
from swissarmybench.client.visualizations_client import add_card

# A contract's route to the swissarmybench.stats function that runs it.
_STATS = ("fit_test", "outliers", "odds", "predictors", "regression", "time_series", "forecast")
_SPOKEN = ("name", "board")


class Analyze:
    """`sab.analyze`: callable for a card, with one method per analysis (by the contract's id)."""

    def __call__(
        self,
        thing: object,
        title: str | None = None,
        *,
        key: str | None = None,
        size: tuple[int, int] | None = None,
        kind: str | None = None,
    ) -> str:
        """Add `thing` to the Analyze board (or replace the card named `key`). Returns the card's id."""
        return add_card(thing, title, key=key, size=size, kind=kind)

    # ===== the contracts =====

    def contracts(self) -> dict[str, Any]:
        """Every analysis's data contract, with its made-up sample (what the agent's analyze_contracts
        gives)."""
        from swissarmybench.domain import analysis_contracts as C

        return C.every()

    def contract(self, analysis: str) -> dict[str, Any]:
        """One analysis's data contract: its slots (the kinds of column each takes, how many, the checks),
        the table's shape, the options and their defaults, what it makes."""
        from swissarmybench.domain import analysis_contracts as C

        described: dict[str, Any] = _contract(analysis).to_json()
        return described | {"sample": C.sample(analysis)}

    def sample(self, analysis: str, *, other: bool = False) -> Any:
        """The contract's made-up sample: a pandas DataFrame when pandas is installed (its dates real
        dates), else the rows as a list of dictionaries. `other=True`: a two-table analysis's second table."""
        from swissarmybench.domain import analysis_contracts as C

        _contract(analysis)
        made = C.sample(analysis)
        if other:
            if "other" not in made:
                raise ValueError(f"{analysis} takes one table: it has no second sample.")
            made = made["other"]
        rows = [dict(row) for row in made["rows"]]
        try:
            import pandas as pd
        except ImportError:
            return rows
        frame = pd.DataFrame(rows, columns=list(made["columns"]))
        for column in made["columns"]:
            if column in C.SAMPLE_DATES:
                frame[column] = pd.to_datetime(frame[column])
        return frame

    # ===== the checker =====

    def check(self, data: Any, analysis: str | None = None, **columns: Any) -> dict[str, Any]:
        """Check this table: every analysis ranked for `data` (fits now, fits after its fixes, or not, and
        why). With `analysis`: that one's check: what fits each slot, what is missing, the fixes (each
        with its steps as DuckDB the grid would run). `data`: a DataFrame, or an open table's name."""
        if isinstance(data, str):
            body: dict[str, Any] = {"table": data}
            if analysis:
                body |= {"analysis": analysis, "columns": columns or None}
            return dict(_call("POST", "/analyze/check", _json(body)))
        from swissarmybench.domain import analyze as Z

        rows, facts, _ = _facts(data)
        table = "data"
        if analysis:
            return Z.plan(analysis, table, rows, facts, columns or None).to_json()
        ranked = Z.rank(table, rows, facts)
        return {
            "rows": rows,
            "notes": Z.table_notes(table, rows, facts),
            "ranked": ranked,
            "top": Z.top_three(ranked),
        }

    # ===== every analysis, by its contract's id =====

    def run(self, analysis: str, data: Any, **given: Any) -> dict[str, Any]:
        """Run `analysis` on `data` (a DataFrame, or an open table's name). Slots and options go by their
        contract names (column="amount", digits="2"); `name` is the table's name on its cards; `board`
        False keeps the cards off the Analyze board (by default they land when the app is running)."""
        c = _contract(analysis)
        slots = {s.key for s in c.slots}
        columns = {k: v for k, v in given.items() if k in slots}
        options = {k: v for k, v in given.items() if k not in slots and k not in _SPOKEN}
        known = {o.key for o in c.options}
        unknown = [k for k in options if k not in known and not k.startswith("value:")]
        if unknown:
            takes = ", ".join(sorted(slots | known)) or "nothing but the table"
            raise TypeError(f"sab.analyze.{c.id} has no {unknown[0]!r}: it takes {takes}.")
        if isinstance(data, str):
            body = {"analysis": c.id, "table": data, "columns": columns or None, "options": options or None}
            return dict(_call("POST", "/analyze/run", _json(body))["result"])
        if c.two_tables:
            raise TypeError(
                f"{c.label.rstrip('?…')} runs on two open tables: push both, then "
                f'sab.analyze.{c.id}("orders", other="ledger").'
            )
        return _local(c, data, columns, options, str(given.get("name") or "data"), given.get("board"))

    def __getattr__(self, analysis: str) -> Callable[..., dict[str, Any]]:
        if analysis.startswith("_"):
            raise AttributeError(analysis)
        from swissarmybench.domain import analysis_contracts as C

        if analysis not in C.BY_ID:
            raise AttributeError(f"sab.analyze has no {analysis!r}: its analyses are {', '.join(C.BY_ID)}.")

        def run(data: Any, **given: Any) -> dict[str, Any]:
            return self.run(analysis, data, **given)

        run.__name__ = analysis
        run.__doc__ = f"{C.BY_ID[analysis].label} ({C.BY_ID[analysis].name}): {C.BY_ID[analysis].get}"
        return run

    def __dir__(self) -> list[str]:
        from swissarmybench.domain import analysis_contracts as C

        return sorted({*super().__dir__(), *C.BY_ID})


def _json(body: dict[str, Any]) -> bytes:
    return json.dumps({k: v for k, v in body.items() if v is not None}).encode("utf-8")


def _contract(analysis: str) -> Any:
    from swissarmybench.domain import analyze as Z

    try:
        return Z.contract(analysis)
    except Z.AnalyzeError as error:
        raise ValueError(str(error)) from None


def _facts(data: Any) -> tuple[int, list[Any], Any]:
    """(rows, the columns' facts, the private DuckDB holding `data`): the server's own queries."""
    from swissarmybench import stats
    from swissarmybench.domain import analyze as Z

    con, _, view = stats._open(data)
    columns = [(c.name, c.type) for c in view]
    names = [name for name, _ in columns]
    if not columns:
        return 0, [], con
    row = con.execute(Z.facts_query("data", columns)).fetchone()
    _, first = Z.read_facts(columns, row)
    few = [f.name for f in first if 0 < f.distinct <= Z.VALUES_KEPT]
    values: dict[str, list[tuple[str, int]]] = {}
    if few:
        for i, v, n in con.execute(Z.values_query("data", few)).fetchall():
            values.setdefault(few[int(i)], []).append((str(v), int(n)))
    samples: dict[str, list[str]] = {}
    for i, v in con.execute(Z.sample_query("data", names)).fetchall():
        samples.setdefault(names[int(i)], []).append(str(v)[:60])
    rows, facts = Z.read_facts(columns, row, samples, values)
    return rows, facts, con


def _local(
    c: Any, data: Any, columns: dict[str, Any], options: dict[str, Any], name: str, board: Any
) -> dict[str, Any]:
    from swissarmybench import stats
    from swissarmybench.domain import analyze as Z

    rows, facts, con = _facts(data)
    plan = Z.plan(c.id, name, rows, facts, columns or None, options or None)
    if plan.gone:
        raise ValueError(f"{', '.join(plan.gone)} is not a column of this table.")
    if plan.refused:
        raise ValueError(f"{plan.refused[0][:1].upper()}{plan.refused[0][1:]}.")
    if not plan.ready:
        fixes = " ".join(f.sentence for f in plan.fixes if f.level == "needed")
        raise ValueError(f"{plan.missing}{' Make it fit: ' + fixes if fixes else ''}")
    by_name = {f.name: f for f in facts}
    body = Z.request(plan, by_name)
    result: dict[str, Any]
    if c.id == "profile":
        from swissarmybench.services.profile import profile_table

        result = profile_table(con, "SELECT * FROM data", stats._open(data)[2])
    elif c.id == "check":
        ranked = Z.rank(name, rows, facts)
        result = {
            "notes": Z.table_notes(name, rows, facts),
            "suggested": Z.top_three(ranked),
            "ranked": ranked,
        }
    elif c.id == "whatif":
        fit = stats.regression(data, **body)
        values = Z.what_if_values(plan)
        result = {"fit": fit, "values": values, "prediction": stats.predict(fit["model"], values)}
    elif c.route in _STATS:
        result = dict(getattr(stats, c.route)(data, **body))
    else:
        raise ValueError(f"sab.analyze.{c.id} runs in the app only.")
    if board is not False:
        landed = {
            "analysis": c.id,
            "dataset": name,
            "columns": plan.values,
            "options": plan.chosen,
            "sentence": Z.sentence(plan),
            "request": body,
            "result": result,
        }
        try:
            _call("POST", "/analyze/land", json.dumps(landed, default=str).encode("utf-8"))
        except ServerNotRunningError:
            if board is True:
                raise
    return result


analyze = Analyze()
