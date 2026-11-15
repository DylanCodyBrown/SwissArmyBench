"""Thin cells (docs/ideas.md, "After the beta: controllers", thin cells, 2026-11-15): a page's view cells
show; the model (a table filtered, grouped or joined) belongs in data.ipynb, where every page and
notebook reads it from data.py.

  hint   a block's cell does model work: a top-level assignment that filters, groups or joins a table
         and reads only tables and data.py's names (not a widget's value: that is a controller's
         work, and stays). The canvas says so quietly, with Move to data.ipynb
  move   those lines go into a named cell of data.ipynb (with the imports they use); the view cell
         keeps one line in their place that reads them back: `from data import sales_by_product`

By Python's own parser, standard library only, no I/O.
"""

from __future__ import annotations

import ast
import builtins
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain import streamlit_cells as cells
from swissarmybench.domain import table_cells

JOINS: frozenset[str] = frozenset({"merge", "join", "concat"})
GROUPS: frozenset[str] = frozenset(
    {"groupby", "pivot_table", "pivot", "value_counts", "resample", "crosstab", "agg", "aggregate"}
)
FILTERS: frozenset[str] = frozenset({"query", "isin", "between", "where", "mask", "nlargest", "nsmallest"})
WORDS: dict[str, str] = {"filter": "filters", "group": "groups", "join": "joins"}
_BUILTINS: frozenset[str] = frozenset(dir(builtins))


@dataclass(frozen=True)
class Move:
    """The model work a view cell does, and the move: the names it makes, the work it does (filter,
    group, join), the data.ipynb cell's code and name, and the view cell's code after the move."""

    names: tuple[str, ...]
    work: tuple[str, ...]
    data: str
    cell: str
    title: str

    @property
    def words(self) -> str:
        """`Groups and joins a table: sales_by_product`."""
        said = [WORDS[w] for w in self.work]
        head = said[0] if len(said) == 1 else ", ".join(said[:-1]) + " and " + said[-1]
        return f"{head[:1].upper()}{head[1:]} a table: {', '.join(self.names)}"

    def to_json(self) -> dict[str, Any]:
        return {
            "names": list(self.names),
            "work": list(self.work),
            "words": self.words,
            "data_code": self.data,
            "cell_code": self.cell,
            "title": self.title,
        }


def _attrs(node: ast.AST) -> set[str]:
    return {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def _work(value: ast.AST) -> list[str]:
    """What an expression does to a table: filter, group, join (in that order)."""
    names = _attrs(value)
    calls = {
        n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        for n in ast.walk(value)
        if isinstance(n, ast.Call)
    }
    found: list[str] = []
    picked = any(
        isinstance(n, ast.Subscript)
        and any(isinstance(m, ast.Compare | ast.BoolOp) for m in ast.walk(n.slice))
        for n in ast.walk(value)
    )
    if picked or calls & FILTERS or ("str" in names and "contains" in calls):
        found.append("filter")
    if calls & GROUPS:
        found.append("group")
    if calls & JOINS:
        found.append("join")
    return found


def _whole_lines(statement: ast.stmt, others: list[ast.stmt]) -> bool:
    first, last = statement.lineno, statement.end_lineno or statement.lineno
    return not any(
        o is not statement and o.lineno <= last and (o.end_lineno or o.lineno) >= first for o in others
    )


def _comments_above(lines: list[str], start: int, floor: int) -> int:
    """The first line (1-based) of the comment lines just above line `start`, not above `floor`."""
    at = start
    while at - 1 > floor and lines[at - 2].lstrip().startswith("#"):
        at -= 1
    return at


def model_work(code: str, inputs: Iterable[str], where: str = "") -> Move | None:
    """The model work of a view cell (None: there is none). `inputs`: what a moved line may read: the
    open tables and data.py's names (as Python variables). `where`: the cell's words for the moved
    cell's first line ("Sales by product, sales.ipynb @cell4")."""
    uses, text = table_cells.split_uses(code)
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None
    if not cells.uses_streamlit(text):
        return None  # a cell that shows nothing is the model already
    allowed = set(inputs)
    imported: dict[str, ast.stmt] = {}
    for statement in tree.body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            module = statement.module if isinstance(statement, ast.ImportFrom) else statement.names[0].name
            if (module or "").split(".")[0] == "streamlit":
                continue
            for alias in statement.names:
                imported[alias.asname or alias.name.split(".")[0]] = statement
    moved: list[ast.Assign] = []
    made: list[str] = []
    work: list[str] = []
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or not _whole_lines(statement, tree.body):
            continue
        targets = [n for t in statement.targets for n in table_cells._targets(t)]
        if not targets or not all(isinstance(t, ast.Name) for t in statement.targets):
            continue
        if cells.uses_streamlit(ast.get_source_segment(text, statement) or ""):
            continue
        reads = {n for n in table_cells._reads(statement.value) if n not in _BUILTINS}
        if not reads or not reads <= allowed | set(made) | set(imported):
            continue
        if not reads & (allowed | set(made)):
            continue  # it reads no table
        found = _work(statement.value)
        if not found and not reads & set(made):
            continue
        if any(t.startswith("_") for t in targets):
            continue  # a cell's own helper stays with it
        moved.append(statement)
        made += [t for t in targets if t not in made]
        work += [w for w in found if w not in work]
    if not work:
        return None
    # A name the cell gives again in a line that stays would be read wrongly after the move.
    kept = [s for s in tree.body if s not in moved]
    if any(name in table_cells._made(s) for s in kept for name in made):
        return None
    lines = text.split("\n")
    header = max([n for n, _ in _header_lines(text)], default=0)
    spans: list[tuple[int, int]] = []
    for statement in moved:
        start = _comments_above(lines, statement.lineno, header)
        spans.append((start, statement.end_lineno or statement.lineno))
    needed = [
        s
        for s in tree.body
        if isinstance(s, ast.Import | ast.ImportFrom)
        and s in imported.values()
        and any(name in {n for m in moved for n in table_cells._reads(m.value)} for name in _bound(s))
    ]
    data = [f"# From {where}" if where else f"# From the cell that shows {made[0]}"]
    data += [line for s in needed for line in lines[s.lineno - 1 : (s.end_lineno or s.lineno)]]
    for start, end in spans:
        data += lines[start - 1 : end]
    dropped = {n for start, end in spans for n in range(start, end + 1)}
    first = spans[0][0]
    after: list[str] = []
    for number, line in enumerate(lines, start=1):
        if number == first:
            after.append(f"from data import {', '.join(made)}")
        if number not in dropped:
            after.append(line)
    cell = "\n".join(after)
    if uses is not None:
        cell = f"{uses}\n{cell}"
    order = [w for w in ("filter", "group", "join") if w in work]
    return Move(tuple(made), tuple(order), "\n".join(data).rstrip("\n") + "\n", cell, made[0])


def _bound(statement: ast.Import | ast.ImportFrom) -> list[str]:
    return [alias.asname or alias.name.split(".")[0] for alias in statement.names]


def _header_lines(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        if not line.lstrip().startswith("#"):
            break
        found.append((number, line))
    return found
