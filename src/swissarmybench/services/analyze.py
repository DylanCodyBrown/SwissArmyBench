"""The Analyze page's use cases (the owner, 2026-11-19: "This page becomes the place where users can input
columns and tables through guided, exact, very user friendly forms" / "Every analysis should automatically
push to the analysis visualization area" / "make it stupid simple").

One service for every door: the page's forms, the agent's analyze_* tools and `sab.analyze` in Python read
the same contracts (domain/analysis_contracts.py) through the same checker (domain/analyze.py):

  catalog, contracts     the toolbar and each analysis's data contract, with its made-up sample
  tables                 the open tables ("orders, with 2 steps"), and the one Analyze last used
  plan                   one analysis's form for a table: the picks, what is missing, how to make it fit
  check                  Check this table: every analysis ranked (fits now, after its fixes, or not, and why)
  column                 What can I do with a column?
  run                    run it (with its fixes applied first, when asked: grid steps, undoable), and land
                         its cards at the top of the board; a run can be cancelled, and two can run at once
  a run's math, rows as a grid, code and inputs (Run again): kept in memory for this session

Nothing is applied to a table by itself: fixes are steps added on the caller's word, and the original rows
never change. The analyses themselves are the existing run_* functions (services/analysis.py and friends).
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import analysis as A
from swissarmybench.domain import analysis_cards as K
from swissarmybench.domain import analysis_contracts as C
from swissarmybench.domain import analyze as Z
from swissarmybench.domain.datasets import DatasetInfo
from swissarmybench.domain.grids import Grid, view_key
from swissarmybench.domain.proofs import PROOFS as PROVEN
from swissarmybench.domain.proofs import proof as show_the_math
from swissarmybench.domain.relationships import CompareSpec
from swissarmybench.services.analysis import (
    Analysis,
    Columns,
    check_outliers,
    run_fit,
    run_odds,
    run_outliers,
    run_predictors,
)
from swissarmybench.services.blades import BladeService
from swissarmybench.services.charts import Cards
from swissarmybench.services.datasets import DatasetService
from swissarmybench.services.grids import GridService
from swissarmybench.services.ports import AGENT, BACKGROUND, SqlSession
from swissarmybench.services.profile import profile_table
from swissarmybench.services.regression import run_predict, run_regression
from swissarmybench.services.relationships import Compare, KeyFinder
from swissarmybench.services.tieout import TieOut
from swissarmybench.services.timeseries import run_forecast, run_time_series
from swissarmybench.services.workspace import Conflict, NotFound, TimedOut, Workspace

RUNS_KEPT = 60  # results kept in memory for their cards' actions (Show the math, Open as grid, Copy code)
FACTS_KEPT = 64  # tables' column facts kept by view (the same view asked twice is counted once)


class DoesNotFit(Conflict):
    """The table does not fit the analysis as asked: the reason in one sentence, and the form as it stands
    now (`plan`: what fits, what is missing, the fixes) so the page and the agent can go on from it."""

    def __init__(self, what: str, plan: dict[str, Any], where: str | None = None) -> None:
        super().__init__(what, where=where)
        self.plan = plan


@dataclass
class Run:
    id: str
    analysis: str
    grid: str
    dataset: str
    columns: dict[str, Any]
    options: dict[str, Any]
    body: dict[str, Any]
    sentence: str
    result: dict[str, Any] = field(repr=False, default_factory=dict)
    who: str = "user"
    at: float = 0.0

    def inputs(self) -> dict[str, Any]:
        return {
            "run": self.id,
            "analysis": self.analysis,
            "table": self.grid,
            "dataset": self.dataset,
            "columns": self.columns,
            "options": self.options,
            "sentence": self.sentence,
        }


class Analyze:
    def __init__(
        self,
        ws: Workspace,
        grids: GridService,
        datasets: DatasetService,
        analysis: Analysis,
        tie_out: TieOut,
        key_finder: KeyFinder,
        cards: Cards,
        blades: BladeService,
    ) -> None:
        self.ws = ws
        self._grids = grids
        self._datasets = datasets
        self._analysis = analysis
        self._tie_out = tie_out
        self._key_finder = key_finder
        self._cards = cards
        self._blades = blades
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._facts: OrderedDict[str, tuple[int, list[Z.Facts]]] = OrderedDict()
        self._lock = threading.Lock()
        self._memory: dict[tuple[str, str], dict[str, Any]] = {}  # (table, analysis): columns and options
        self._last_table: str | None = None  # the grid Analyze last used
        self._running: dict[str, tuple[Any, list[bool]]] = {}  # token: (its cursor or None, [cancelled])

    # ===== the toolbar, the contracts, the tables =====

    def _mine(self) -> list[C.Contract]:
        """The analysis blades' contracts (the toolbar's Yours): one whose CONTRACT cannot be read is left
        out here and says why when it is asked for by name."""
        found: list[C.Contract] = []
        for listed in self._blades.analysis_blades.analyses()["analyses"]:
            try:
                found.append(self._contract(f"{C.BLADE}{listed['name']}"))
            except (ValueError, LookupError):
                continue
        return found

    def _contract(self, analysis: Any) -> C.Contract:
        """An analysis's contract: a built-in's by its id, an analysis blade's (blade:<name>) read from
        its code (domain/analysis_contracts.py blade_contract: never run)."""
        if isinstance(analysis, str) and analysis.startswith(C.BLADE):
            blade = self._blades.analysis_blades.analysis_blade(analysis.removeprefix(C.BLADE))
            try:
                return C.blade_contract(blade.name, blade.description, blade.code)
            except C.ContractError as error:
                raise Z.AnalyzeError(f"{blade.name}'s CONTRACT cannot be read: {error}") from error
        return Z.contract(analysis)

    def _sample(self, c: C.Contract) -> dict[str, Any]:
        return C.sample(c.id) if c.id in C.BY_ID else C.generic_sample(c)

    def catalog(self) -> dict[str, Any]:
        """The toolbar: the built-in analyses by group, then your own (the analysis blades)."""
        found = Z.catalog()
        found["analyses"] += [
            {
                "id": c.id,
                "group": c.group,
                "label": c.label,
                "name": c.name,
                "get": c.get,
                "two_tables": False,
            }
            for c in self._mine()
        ]
        return found

    def contracts(self, analysis: Any = None) -> dict[str, Any]:
        """Every contract with its made-up sample (your own analyses' too), or one."""
        if analysis in (None, ""):
            every = C.every()
            every["contracts"] += [c.to_json() | {"sample": self._sample(c)} for c in self._mine()]
            return every
        c = self._contract(analysis)
        return c.to_json() | {"sample": self._sample(c)}

    def _label(self, grid: Grid) -> str:
        steps = len([s for s in grid.steps if s.enabled])
        return f"{grid.dataset}" + (f", with {steps} step{'s' if steps != 1 else ''}" if steps else "")

    def tables(self, front: Any = None) -> dict[str, Any]:
        """The open tables, and the one a form starts on: the grid in front (`front`, the page says),
        else the one Analyze last used, else the first."""
        grids = [g for g in self.ws.grids.all() if self.ws.store.get(g.dataset) is not None]
        ids = {g.id for g in grids}
        current = front if front in ids else self._last_table if self._last_table in ids else None
        if current is None and grids:
            current = grids[0].id
        return {
            "tables": [
                {
                    "grid": g.id,
                    "dataset": g.dataset,
                    "label": self._label(g),
                    "steps": len([s for s in g.steps if s.enabled]),
                }
                for g in grids
            ],
            "current": current,
        }

    def _find(self, table: Any, front: Any = None) -> tuple[Grid, DatasetInfo]:
        """A table by its grid id or its name; none named: the one a form starts on."""
        ws = self.ws
        if table in (None, ""):
            table = self.tables(front)["current"]
            if table is None:
                raise NotFound("No table is open: open one first.", fixes=[])
        grid = ws.grids.get(str(table)) or ws.grids.first_for(str(table))
        info = ws.store.get(grid.dataset) if grid else None
        if grid is None or info is None:
            raise NotFound(
                f"The table {str(table)[:80]!r} is not open any more: pick another.", where=str(table)[:80]
            )
        return grid, info

    async def _open(self, body: dict[str, Any], who: str) -> tuple[Grid, DatasetInfo]:
        """The table a request names: an open one (its grid id or name), or a connection's table by its
        DuckDB SQL name (`[Warehouse].orders`), read through the connection-tables contract into a table
        of its own (every row, counted first and refused past the limit in plain words) and kept open."""
        table = body.get("table")
        if not isinstance(table, str) or not table.lstrip().startswith("["):
            return self._find(table, body.get("front"))
        named = table.strip()
        if len(named) > 300 or any(ch in named for ch in ";\n\r") or "--" in named or "/*" in named:
            raise ValueError("Name a connection's table as [Connection].table.")
        name = (
            "_".join(part for part in "".join(ch if ch.isalnum() else " " for ch in named).split()) or "table"
        )
        already = self.ws.grids.first_for(name)
        if already is not None and self.ws.store.get(name) is not None:
            return self._find(already.id)
        # The text is one SELECT for the "+" tab's own guard (domain/sql_guard.py), which refuses the rest.
        select = f"SELECT * FROM {named}"  # noqa: S608
        opened = await self._datasets.build_from_query(self._datasets.free_name(name), select, False, who)
        return self._find(str(opened["grid"]))

    def _others(self, grid: Grid) -> list[dict[str, Any]]:
        return [
            {"grid": g.id, "label": self._label(g)}
            for g in self.ws.grids.all()
            if g.id != grid.id and self.ws.store.get(g.dataset) is not None
        ]

    # ===== a table's facts, on its view =====

    async def _on_view(
        self,
        grid: Grid,
        info: DatasetInfo,
        who: str,
        run: Callable[[SqlSession, str, Columns], Any],
        token: str = "",
    ) -> Any:
        """`run(cursor, relation, columns)` on the grid's view (its steps applied). The query stops at the
        time limit (said in plain words, never a hang) or when its token is cancelled."""
        ws = self.ws
        cursor = ws.store.cursor()
        ticket = grid.admit(None, cursor)
        cancelled = self._running.get(token, (None, [False]))[1] if token else [False]
        if token:
            self._running[token] = (cursor, cancelled)
        seconds = ws.settings.query_timeout_seconds
        timed_out = [False]

        done = threading.Event()

        def stop() -> None:
            # Past its time: interrupted until it has stopped (an interrupt between two of its queries
            # stops nothing, so it is sent again).
            timed_out[0] = True
            while not done.wait(0.05):
                cursor.interrupt()

        def job() -> Any:
            if cancelled[0]:
                raise TimedOut("Cancelled: nothing was added to the board.")
            timer = threading.Timer(seconds, stop)
            timer.daemon = True
            timer.start()
            started = time.monotonic()
            try:
                adapted = ws.views.adapted(cursor)  # its rows only through the adapter
                view = ws.compiled(adapted, grid, info)
                if view.error is not None:
                    raise Conflict(
                        f"A step of {info.name} does not work, so it cannot be analysed: {view.error}",
                        where=info.name,
                    )
                with ws.views.reading(adapted, info, grid.steps, grid.settings) as rows:
                    found = run(adapted, f"({rows}) AS src", view.columns)
                if time.monotonic() - started > seconds:  # past its time as it ended: the limit holds
                    timed_out[0] = True
                    raise ws.interrupted()
                return found
            finally:
                done.set()
                timer.cancel()

        try:
            return await ws.workers.run(AGENT if who == "agent" else BACKGROUND, job)
        except ws.interrupted:
            if cancelled[0]:
                raise TimedOut("Cancelled: nothing was added to the board.") from None
            if timed_out[0]:
                raise TimedOut(
                    f"{info.name} is too big to analyse in {seconds:.0f} seconds: it was stopped. "
                    "Filter it or keep fewer columns first.",
                    where=info.name,
                ) from None
            raise
        finally:
            grid.release(ticket)
            if token and self._running.get(token, (None, None))[0] is cursor:
                self._running[token] = (None, cancelled)

    async def facts(
        self, grid: Grid, info: DatasetInfo, who: str, token: str = ""
    ) -> tuple[int, list[Z.Facts]]:
        """(rows, each column's facts) of the grid's view: one pass, then the few-valued columns' values
        and every column's first values. Kept by view: a form that asks again does not count again."""
        key = view_key(info, grid.steps, grid.settings, None)
        with self._lock:
            if key in self._facts:
                self._facts.move_to_end(key)
                return self._facts[key]

        def read(cur: SqlSession, relation: str, view: Columns) -> tuple[int, list[Z.Facts]]:
            columns = [(c.name, c.type) for c in view]
            names = [name for name, _ in columns]
            if not columns:
                return 0, []
            row = cur.execute(Z.facts_query(relation, columns)).fetchone()
            _, first = Z.read_facts(columns, row)
            few = [f.name for f in first if 0 < f.distinct <= Z.VALUES_KEPT]
            values: dict[str, list[tuple[str, int]]] = {}
            if few:
                for i, v, n in cur.execute(Z.values_query(relation, few)).fetchall():
                    values.setdefault(few[int(i)], []).append((str(v), int(n)))
            samples: dict[str, list[str]] = {}
            for i, v in cur.execute(Z.sample_query(relation, names)).fetchall():
                samples.setdefault(names[int(i)], []).append(str(v)[:60])
            return Z.read_facts(columns, row, samples, values)

        found: tuple[int, list[Z.Facts]] = await self._on_view(grid, info, who, read, token)
        with self._lock:
            self._facts[key] = found
            while len(self._facts) > FACTS_KEPT:
                self._facts.popitem(last=False)
        return found

    async def _counted(self, grid: Grid, info: DatasetInfo, who: str, plan: Z.Plan) -> None:
        """The fixes whose count the facts do not hold (the ten most common values' rows), counted."""
        waiting = [f for f in plan.fixes if f.count_sql]
        if not waiting:
            return

        def count(cur: SqlSession, relation: str, view: Columns) -> list[int]:
            out = []
            for fix in waiting:
                row = cur.execute(str(fix.count_sql).replace("{relation}", relation)).fetchone()
                out.append(int(row[0] or 0) if row else 0)
            return out

        counts = await self._on_view(grid, info, who, count)
        done = {fix.id: fix.counted(n) for fix, n in zip(waiting, counts, strict=True)}
        plan.fixes = [done.get(f.id, f) for f in plan.fixes]

    # ===== a form =====

    def _given(
        self, body: dict[str, Any], dataset: str, analysis: str
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        """(columns, options, remembered): what the caller gave, else what this table and analysis last
        ran with (design principle 8.13: the last columns and options come back)."""
        columns, options = body.get("columns"), body.get("options")
        if columns is not None and not isinstance(columns, dict):
            raise ValueError('"columns" is {slot: column} (or a list for a slot that takes several).')
        if options is not None and not isinstance(options, dict):
            raise ValueError('"options" is {option: value}.')
        kept = self._memory.get((dataset, analysis)) if body.get("remember", True) else None
        if columns is None and options is None and kept:
            return dict(kept["columns"]), dict(kept["options"]), True
        return dict(columns or {}), dict(options or {}), False

    async def plan(self, body: Any, who: str) -> dict[str, Any]:
        """{"analysis", "table"?, "front"?, "columns"?, "options"?}: the form, planned."""
        if not isinstance(body, dict):
            raise ValueError(
                'Send {"analysis": "benford", "table": the id of an open table or a table name}.'
            )
        c = self._contract(body.get("analysis"))
        grid, info = await self._open(body, who)
        rows, facts = await self.facts(grid, info, who)
        columns, options, remembered = self._given(body, info.name, c.id)
        plan = Z.plan(c, info.name, rows, facts, columns, options, self._others(grid))
        if remembered and (plan.gone or plan.refused):  # what was remembered no longer fits: start afresh
            plan = Z.plan(c, info.name, rows, facts, None, None, self._others(grid))
            remembered = False
        await self._counted(grid, info, who, plan)
        return self._planned(plan, grid, info, remembered)

    def _planned(
        self, plan: Z.Plan, grid: Grid, info: DatasetInfo, remembered: bool = False
    ) -> dict[str, Any]:
        return plan.to_json() | {
            "grid": grid.id,
            "dataset": info.name,
            "table_label": self._label(grid),
            "steps": len([s for s in grid.steps if s.enabled]),
            "remembered": remembered,
            "one_row_per": plan.contract.table.one_row_per,
        }

    async def check(self, body: Any, who: str) -> dict[str, Any]:
        """Check this table ({"table"?}): every analysis ranked for it and the three that suit it best;
        with "analysis", that one analysis's check: each slot's fit, what is missing, the fixes."""
        if not isinstance(body, dict):
            raise ValueError(
                'Send {"table": the id of an open table or a table name}, with "analysis" for one analysis.'
            )
        if body.get("analysis") not in (None, ""):
            return await self.plan(body | {"remember": False}, who)
        grid, info = await self._open(body, who)
        rows, facts = await self.facts(grid, info, who)
        ranked = Z.rank(info.name, rows, facts, self._others(grid))
        return {
            "grid": grid.id,
            "dataset": info.name,
            "table_label": self._label(grid),
            "rows": rows,
            "notes": Z.table_notes(info.name, rows, facts),
            "ranked": ranked,
            "top": Z.top_three(ranked),
        }

    async def column(self, body: Any, who: str) -> dict[str, Any]:
        """What can I do with a column? {"table"?, "column"}: the analyses it fits, each one click; with
        no column, every column of the table with what fits it."""
        if not isinstance(body, dict):
            raise ValueError('Send {"table": the id of an open table or a table name, "column": name}.')
        grid, info = await self._open(body, who)
        rows, facts = await self.facts(grid, info, who)
        base = {"grid": grid.id, "dataset": info.name, "table_label": self._label(grid), "rows": rows}
        if body.get("column") in (None, ""):
            return base | {
                "columns": [
                    {
                        "name": f.name,
                        "type": f.word,
                        "preview": list(f.sample),
                        "analyses": Z.for_column(f.name, rows, facts),
                    }
                    for f in facts
                ]
            }
        return base | {"column": body["column"], "analyses": Z.for_column(str(body["column"]), rows, facts)}

    # ===== the made-up sample =====

    async def open_sample(self, analysis: Any, who: str) -> dict[str, Any]:
        """A contract's made-up sample as open tables (Try it on this sample): its grid, the second
        table's for a two-table analysis, and the columns each slot takes."""
        c = self._contract(analysis)
        sample = self._sample(c)
        dates = tuple(sample.get("dates") or ())

        async def store(part: dict[str, Any]) -> str:
            columns = list(part["columns"])
            rows = [[row[name] for name in columns] for row in part["rows"]]
            stored = await self._datasets.store_rows(part["name"], columns, rows, who, dates, "records")
            return str(stored["grid"])

        other = await store(sample["other"]) if sample.get("other") else None
        grid = await store(sample)
        columns: dict[str, Any] = {}
        for slot in c.slots:
            if slot.table:
                columns[slot.key] = other
            elif slot.count != "any":
                picked = sample["slots"][slot.key]
                columns[slot.key] = picked if slot.many else picked[0]
        return {"grid": grid, "dataset": sample["name"], "other": other, "columns": columns}

    # ===== run =====

    def cancel(self, token: Any) -> dict[str, Any]:
        """Stop a run by the token it was started with: its query is interrupted, and nothing of it lands."""
        found = self._running.get(str(token))
        if found is None:
            return {"cancelled": False}
        cursor, cancelled = found
        cancelled[0] = True
        if cursor is not None:
            cursor.interrupt()
        return {"cancelled": True}

    async def _apply(self, grid: Grid, info: DatasetInfo, fixes: list[Z.Fix], who: str) -> list[str]:
        """Fixes added to the grid as its own steps (seen in the steps strip, undone there)."""
        said: list[str] = []
        for fix in fixes:
            for step in fix.steps:
                await self._grids.step_op(grid, info, {"op": "add", "step": dict(step)}, who)
            said.append(fix.sentence)
        return said

    async def apply_fixes(self, body: Any, who: str) -> dict[str, Any]:
        """Make it fit's Apply: {"analysis", "table"?, "columns"?, "fixes": [ids]} adds those fixes' steps
        to the table and plans the form again, each fixed slot taking its new column."""
        if not isinstance(body, dict) or not isinstance(body.get("fixes"), list) or not body["fixes"]:
            raise ValueError(
                'Send {"analysis", "table", "fixes": [a fix\'s id, ...]} (analyze_check lists them).'
            )
        c = self._contract(body.get("analysis"))
        grid, info = await self._open(body, who)
        rows, facts = await self.facts(grid, info, who)
        columns, options, _ = self._given(body | {"remember": False}, info.name, c.id)
        plan = Z.plan(c, info.name, rows, facts, columns, options, self._others(grid))
        by_id = {f.id: f for f in plan.fixes}
        unknown = [str(i)[:60] for i in body["fixes"] if i not in by_id]
        if unknown:
            raise DoesNotFit(
                f"No such fix for {info.name} now: {', '.join(unknown)}.",
                self._planned(plan, grid, info),
                info.name,
            )
        chosen = [by_id[i] for i in dict.fromkeys(body["fixes"])]
        said = await self._apply(grid, info, chosen, who)
        for fix in chosen:
            if fix.slot and fix.fills:
                slot = next(s for s in c.slots if s.key == fix.slot)
                columns[fix.slot] = [fix.fills] if slot.many else fix.fills
        self.ws.audit.write(who, "analyze_fix", info.name, analysis=c.id, fixes=len(chosen), grid=grid.id)
        again = await self.plan(
            {"analysis": c.id, "table": grid.id, "columns": columns, "options": options}, who
        )
        return again | {"applied": said}

    async def run(self, body: Any, who: str) -> dict[str, Any]:
        """{"analysis", "table"?, "columns"?, "options"?, "apply_fixes"?: true, "sample"?: true, "token"?}:
        run one analysis and land its cards on the board. `apply_fixes` first adds the fixes the table
        needs (grid steps); `sample` runs it on the contract's made-up sample (opened as a table)."""
        if not isinstance(body, dict):
            raise ValueError(
                'Send {"analysis": "benford", "table": the id of an open table or a table name}.'
            )
        c = self._contract(body.get("analysis"))
        token = str(body.get("token") or "")[:60]
        if token:
            self._running[token] = (None, [False])
        try:
            return await self._run(c, body, who, token)
        finally:
            self._running.pop(token, None)

    async def _run(self, c: C.Contract, body: dict[str, Any], who: str, token: str) -> dict[str, Any]:
        ws = self.ws
        applied: list[str] = []
        if body.get("sample"):
            sample = await self.open_sample(c.id, who)
            body = body | {"table": sample["grid"], "columns": sample["columns"], "remember": False}
        grid, info = await self._open(body, who)
        rows, facts = await self.facts(grid, info, who, token)
        columns, options, _ = self._given(body, info.name, c.id)
        others = self._others(grid)
        plan = Z.plan(c, info.name, rows, facts, columns, options, others)
        if body.get("apply_fixes") and not plan.ready:
            needed = Z.needed_fixes(plan)
            if needed:
                applied = await self._apply(grid, info, needed, who)
                for fix in needed:
                    slot = next(s for s in c.slots if s.key == fix.slot)
                    columns[fix.slot] = [fix.fills] if slot.many else fix.fills
                rows, facts = await self.facts(grid, info, who, token)
                plan = Z.plan(c, info.name, rows, facts, columns, options, others)
        if plan.gone or plan.refused or not plan.ready:
            await self._counted(grid, info, who, plan)
            if plan.gone:
                names = ", ".join(plan.gone)
                what = (
                    f"{names} is not a column of {info.name} any more (a step renamed or removed it): "
                    "pick again."
                )
            elif plan.refused:
                what = f"{plan.refused[0][:1].upper()}{plan.refused[0][1:]}."
            else:
                what = str(plan.missing)
            raise DoesNotFit(what, self._planned(plan, grid, info), info.name)
        by_name = {f.name: f for f in facts}
        request = Z.request(plan, by_name)
        result = await self._compute(c, grid, info, plan, request, who, token)
        if token and self._running.get(token, (None, [False]))[1][0]:
            raise TimedOut("Cancelled: nothing was added to the board.")
        run = Run(
            secrets.token_hex(5),
            c.id,
            grid.id,
            info.name,
            dict(plan.values),
            dict(plan.chosen),
            request,
            Z.sentence(plan),
            result,
            who,
            time.time(),
        )
        actions = ["again"]
        if c.id.startswith(C.BLADE):  # your own analysis: the cards it returned, as they are
            made = [
                dict(card)
                | {"title": str(card.get("title") or (result.get("title") if at == 0 else "") or "")}
                for at, card in enumerate(result.get("cards") or [])
                if isinstance(card, dict)
            ]
            if not made:
                raise Conflict(f"{c.label} returned nothing to show.", where=c.label)
        else:
            made = K.cards_for(c.id, result, request, info.name)
            if c.route in PROVEN:
                actions.append("math")
            if K.result_rows(c.id, result, request):
                actions.append("grid")
            if c.route in A.CODE_ARGUMENTS:
                actions.append("code")
        landed = await self._cards.land(
            made,
            info.name,
            who,
            run.inputs() | {"label": c.label, "name": c.name, "actions": actions, "next": self._next(run)},
        )
        with self._lock:
            self._runs[run.id] = run
            while len(self._runs) > RUNS_KEPT:
                self._runs.popitem(last=False)
        self._memory[(info.name, c.id)] = {"columns": dict(plan.values), "options": dict(plan.chosen)}
        self._last_table = grid.id
        ws.audit.write(
            who, "analyze_run", info.name, analysis=c.id, cards=len(landed), grid=grid.id, run=run.id
        )
        return run.inputs() | {
            "cards": landed,
            "applied": applied,
            "cautions": plan.cautions,
            "actions": actions,
            "result": result,
        }

    async def land(self, body: Any, who: str) -> dict[str, Any]:
        """A result Python computed itself (sab.analyze.<analysis>(df)) put on the board as a run of its
        own: {"analysis", "dataset", "request", "result", "columns"?, "options"?, "sentence"?}. The cards
        are made here, as every run's are; its code and Run again need a table of that name open."""
        if not isinstance(body, dict) or not isinstance(body.get("result"), dict):
            raise ValueError('Send {"analysis", "dataset", "request": {...}, "result": {...}}.')
        c = self._contract(body.get("analysis"))
        asked = body.get("request")
        request: dict[str, Any] = asked if isinstance(asked, dict) else {}
        dataset = str(body.get("dataset") or "data")[:200]
        result = body["result"]
        try:
            made = K.cards_for(c.id, result, request, dataset)
            rows = K.result_rows(c.id, result, request)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as error:
            raise ValueError(f"That is not a result of {c.name}: {type(error).__name__} {error}.") from error
        open_grid = self.ws.grids.first_for(dataset)
        run = Run(
            secrets.token_hex(5),
            c.id,
            open_grid.id if open_grid else "",
            dataset,
            dict(body.get("columns") or {}) if isinstance(body.get("columns"), dict) else {},
            dict(body.get("options") or {}) if isinstance(body.get("options"), dict) else {},
            request,
            str(body.get("sentence") or "")[:500],
            result,
            who,
            time.time(),
        )
        actions = ["again"] if open_grid else []
        if c.route in PROVEN:
            actions.append("math")
        if rows:
            actions.append("grid")
        if c.route in A.CODE_ARGUMENTS and open_grid:
            actions.append("code")
        landed = await self._cards.land(
            made,
            dataset,
            who,
            run.inputs() | {"label": c.label, "name": c.name, "actions": actions, "next": self._next(run)},
            "python" if who == "user" else who,
        )
        with self._lock:
            self._runs[run.id] = run
            while len(self._runs) > RUNS_KEPT:
                self._runs.popitem(last=False)
        self.ws.audit.write(who, "analyze_run", dataset, analysis=c.id, cards=len(landed), run=run.id)
        return run.inputs() | {"cards": landed, "actions": actions}

    def blade_failure(self, message: str, missing_module: str | None) -> dict[str, Any]:
        """Your own analysis's failed run in the one shape (the install when a module is missing)."""
        return self._blades.run_failure(message, missing_module)

    def _next(self, run: Run) -> list[dict[str, Any]]:
        try:
            return K.next_steps(run.analysis, run.result, run.body)
        except (KeyError, TypeError, ValueError):
            return []

    async def _compute(
        self,
        c: C.Contract,
        grid: Grid,
        info: DatasetInfo,
        plan: Z.Plan,
        request: dict[str, Any],
        who: str,
        token: str,
    ) -> dict[str, Any]:
        """The analysis itself: the same run_* function its own route and swissarmybench.stats call."""
        on = self._on_view
        result: dict[str, Any]
        if c.id.startswith(C.BLADE):
            name = c.id.removeprefix(C.BLADE)
            return dict(
                await self._blades.analysis_blades.analyze(
                    name, grid, info, {"columns": request["columns"]}, who
                )
            )
        if c.id in ("benford", "fit", "together"):
            reference = None
            if request.get("expected") == "grid":
                reference = await self._analysis.reference(request.get("reference"), request["columns"], who)
            result = await on(
                grid, info, who, lambda cur, rel, view: run_fit(cur, rel, view, request, reference), token
            )
            return dict(result)
        if c.id == "outliers":
            check_outliers(request)
            return dict(
                await on(grid, info, who, lambda cur, rel, view: run_outliers(cur, rel, view, request), token)
            )
        if c.id == "odds":
            return dict(
                await on(grid, info, who, lambda cur, rel, view: run_odds(cur, rel, view, request), token)
            )
        if c.id == "predictors":
            return dict(
                await on(
                    grid, info, who, lambda cur, rel, view: run_predictors(cur, rel, view, request), token
                )
            )
        if c.id in ("regression", "whatif"):
            fit = await on(
                grid, info, who, lambda cur, rel, view: run_regression(cur, rel, view, request), token
            )
            if c.id == "regression":
                return dict(fit)
            values = Z.what_if_values(plan)
            return {
                "fit": fit,
                "values": values,
                "prediction": run_predict({"model": fit["model"], "values": values}),
            }
        if c.id == "time_series":
            return dict(
                await on(
                    grid, info, who, lambda cur, rel, view: run_time_series(cur, rel, view, request), token
                )
            )
        if c.id == "forecast":
            return dict(
                await on(grid, info, who, lambda cur, rel, view: run_forecast(cur, rel, view, request), token)
            )
        if c.id == "profile":
            return dict(
                await on(
                    grid,
                    info,
                    who,
                    lambda cur, rel, view: profile_table(cur, f"SELECT * FROM {rel}", view),  # noqa: S608
                    token,
                )
            )
        if c.id == "check":
            checked = await self.check({"table": grid.id}, who)
            suggested = [e | {"label": e["label"], "name": e["name"]} for e in checked["top"]]
            return {"notes": checked["notes"], "suggested": suggested, "ranked": checked["ranked"]}
        if c.id == "tie_out":
            other, other_info = self._find(request["other"])
            cmp = Compare(secrets.token_hex(4), grid.id, other.id, CompareSpec(keys=()))
            suggested = (await self._tie_out.options(cmp))["suggested"]
            asked = {"group": suggested["group"], "measures": suggested["measures"]}
            if "tolerance" in request:
                asked["tolerance"] = request["tolerance"]
            tied = await self._tie_out.run(cmp, asked, who)
            return dict(tied) | {"left_name": info.name, "right_name": other_info.name}
        if c.id == "key_finder":
            return dict(await self._key_finder.run(grid, request, who))
        raise Z.AnalyzeError(f"No analysis {c.id!r}.")

    # ===== a result's actions =====

    def get(self, run_id: Any) -> Run:
        run = self._runs.get(str(run_id))
        if run is None:
            raise NotFound("That result is from an earlier session: run it again to use it.")
        return run

    def runs(self) -> dict[str, Any]:
        """This session's runs, newest first, each with the cards of it still on the board."""
        return {
            "runs": [
                run.inputs() | {"who": run.who, "cards": self._cards.of_run(run.id)}
                for run in reversed(self._runs.values())
            ]
        }

    def inputs(self, run_id: Any) -> dict[str, Any]:
        """Run again: what the run ran with (its form opens filled)."""
        return self.get(run_id).inputs()

    def math(self, run_id: Any) -> dict[str, Any]:
        """Show the math: the result's own numbers worked through (domain/proofs.py)."""
        run = self.get(run_id)
        c = self._contract(run.analysis)
        if c.route not in PROVEN:
            raise NotFound(f"{c.label.rstrip('?…')} has no math to show.")
        result = run.result["fit"] if run.analysis == "whatif" else run.result
        if run.analysis == "together":  # the proof reads a fit test's list of results
            pair = " and ".join(str(name) for name in result.get("columns") or [])
            result = {"expected": "together", "results": [result | {"column": pair}]}
        return dict(show_the_math(c.route, result, run.dataset))

    async def as_grid(self, run_id: Any, who: str) -> dict[str, Any]:
        """Open as grid: the result's table in a tab of its own."""
        run = self.get(run_id)
        rows = K.result_rows(run.analysis, run.result, run.body)
        if not rows:
            raise NotFound("This result has no table to open.")
        columns = list(dict.fromkeys(key for row in rows for key in row))
        data = [[_plain(row.get(name)) for name in columns] for row in rows]
        name = self._datasets.free_name(f"{run.dataset}_{run.analysis}")
        stored = await self._datasets.store_rows(name, columns, data, who, (), "records")
        return {"grid": stored["grid"], "dataset": name, "rows": len(data)}

    async def code(self, run_id: Any) -> dict[str, Any]:
        """Copy code: the analysis as Python for a notebook (the steps as checked SQL, then the
        swissarmybench.stats call that ran)."""
        run = self.get(run_id)
        c = self._contract(run.analysis)
        if c.route not in A.CODE_ARGUMENTS:
            raise NotFound(f"{c.label.rstrip('?…')} has no code to copy.")
        grid, info = self._find(run.grid)
        return await self._analysis.code(c.route, grid, info, run.body)


def _plain(value: Any) -> Any:
    """A result's cell as a table's: text, a number, true/false or blank."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
