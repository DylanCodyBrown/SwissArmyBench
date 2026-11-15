"""A notebook's run order and its stale cells (the Workbench's Notebook mode, 2026-11-15).

The window keeps, for each cell, what it last ran (its code then) and when (the kernel's order of
runs). From the names each Python cell makes and reads (found with Python's parser), each cell is:

  notRun      it has not run in this kernel
  edited      its code changed since it ran
  outOfDate   a name it reads was made again after it ran (its maker ran later), or its maker is edited
              or out of date itself; `because` names them
  current     nothing to do (said nowhere: principle 7.9)

The Outline uses the same states. Pure rules, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import table_cells

MAX_CELLS: int = 2_000
MAX_CELL_CHARS: int = 1_000_000


class FlowError(ValueError):
    """Cells that cannot be read as sent (the message says why)."""


@dataclass
class FlowCell:
    number: int
    kind: str
    source: str
    ran: str | None = None  # its code when it last ran (None: it has not run)
    order: int | None = None  # when it ran, among the kernel's runs (bigger: later)
    makes: list[str] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    state: str = "notRun"
    because: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "makes": self.makes,
            "reads": self.reads,
            "state": self.state,
            "because": self.because,
        }


def read_cells(sent: Any) -> list[FlowCell]:
    """The cells as the window sends them: [{"number", "kind", "source", "ran"?, "order"?}]."""
    if not isinstance(sent, list) or len(sent) > MAX_CELLS:
        raise FlowError(
            f'Send {{"cells": [{{"number", "kind", "source", "ran", "order"}}]}} (at most {MAX_CELLS}).'
        )
    cells: list[FlowCell] = []
    for raw in sent:
        if not isinstance(raw, dict) or not isinstance(raw.get("number"), int):
            raise FlowError('Each cell is {"number": 3, "kind": "code", "source": "..."}.')
        source = raw.get("source")
        ran = raw.get("ran")
        order = raw.get("order")
        if not isinstance(source, str) or len(source) > MAX_CELL_CHARS:
            raise FlowError("A cell's source is text.")
        cells.append(
            FlowCell(
                int(raw["number"]),
                str(raw.get("kind") or "code"),
                source,
                ran if isinstance(ran, str) else None,
                order if isinstance(order, int) and not isinstance(order, bool) else None,
            )
        )
    return cells


def flow(cells: Sequence[FlowCell]) -> list[FlowCell]:
    """Each cell's makes, reads and state (the cells are changed in place and given back)."""
    makers: dict[str, list[FlowCell]] = {}
    for cell in cells:
        if cell.kind != "code":
            cell.state = "current" if cell.ran is not None or cell.kind == "markdown" else "notRun"
            continue
        found = table_cells.facts(cell.source)
        cell.makes = list(found.made)
        cell.reads = [name for name in found.needs if name not in cell.makes]
        for name in cell.makes:
            makers.setdefault(name, []).append(cell)
        if cell.ran is None or cell.order is None:
            cell.state = "notRun"
        elif cell.ran != cell.source:
            cell.state = "edited"
        else:
            cell.state = "current"
    # Out of date: a maker of a name it reads ran after it, or is edited or out of date itself. A
    # maker's own staleness passes down, so this settles in at most as many rounds as there are cells.
    for _ in range(len(cells)):
        moved = False
        for cell in cells:
            if cell.kind != "code" or cell.state in ("notRun", "edited"):
                continue
            stale = sorted(
                {
                    name
                    for name in cell.reads
                    for maker in makers.get(name, [])
                    if maker is not cell
                    and (
                        maker.state in ("edited", "outOfDate")
                        or (maker.order is not None and cell.order is not None and maker.order > cell.order)
                    )
                }
            )
            state = "outOfDate" if stale else "current"
            if state != cell.state or stale != cell.because:
                cell.state, cell.because = state, stale
                moved = True
        if not moved:
            break
    return list(cells)


def outline(cells: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The Outline: each Markdown heading (its level and words) and, under it, each named Python cell
    (its number and name), in the notebook's order."""
    out: list[dict[str, Any]] = []
    for cell in cells:
        if cell.get("kind") == "markdown":
            for line in str(cell.get("source") or "").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    level = len(stripped) - len(stripped.lstrip("#"))
                    words = stripped[level:].strip()
                    if words and level <= 6:
                        out.append(
                            {"kind": "heading", "level": level, "text": words, "number": cell.get("number")}
                        )
        elif cell.get("kind") == "code" and cell.get("name"):
            out.append({"kind": "cell", "number": cell.get("number"), "text": str(cell["name"])})
    return out
