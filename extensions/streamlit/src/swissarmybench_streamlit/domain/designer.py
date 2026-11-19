"""The designer's arranging (the owner, 2026-11-19: "Snaplines and alignment like WinForms"): several selected
items of one grid aligned, made the same size, or spread evenly. Everything is in the grid's own units (12
columns, rows from 1), so what is arranged here is exactly what the page's `st.columns` then draws.

  left, right, centre      their left edges, right edges or centres on one line (the selection's own)
  top, bottom              all in the selection's first row, or its last (two that would lie on each other:
                           the grid settles one below, as it does for any move)
  same_width, same_height  as wide, or as tall, as the first one selected
  distribute               the items of each row spread so the gaps between them are equal, the row's first
                           and last keeping their outer edges

The outline of a page (Visual Studio's Document Outline) is here too: the page as a tree, in reading order.

Pure rules, no I/O: the items are changed in place and the caller settles the grid.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from swissarmybench_streamlit.domain.streamlit_cells import (
    COLUMNS,
    DEFAULT_WIDTH,
    MIN_WIDTH,
    Container,
    Item,
    Page,
    StreamlitError,
    grouped,
)

HOW: tuple[str, ...] = ("left", "right", "centre", "top", "bottom", "same_width", "same_height", "distribute")


def even_gaps(free: int, gaps: int) -> list[int]:
    """`free` columns shared between `gaps` gaps as evenly as whole columns allow (extra from the left)."""
    if gaps <= 0:
        return []
    each, extra = divmod(max(0, free), gaps)
    return [each + (1 if n < extra else 0) for n in range(gaps)]


def arrange(items: Sequence[Item], how: str) -> list[str]:
    """Arrange the selected items (the first is the one the others follow). The ids of those that changed."""
    if how not in HOW:
        raise StreamlitError(f"Arrange is one of: {', '.join(HOW)}.")
    if len(items) < 2:
        raise StreamlitError("Select two or more blocks to arrange them.")
    if len({(i.parent, i.slot) for i in items}) != 1:
        raise StreamlitError("Arrange blocks that sit in the same container (or all on the page itself).")
    locked = [i.id for i in items if i.locked]
    if locked:
        raise StreamlitError(f"{', '.join(locked)} is locked: unlock it to arrange it.")
    before = {i.id: (i.row, i.column, i.w, i.h) for i in items}
    first = items[0]
    if how == "left":
        edge = min(i.column for i in items)
        for i in items:
            i.column = edge
    elif how == "right":
        edge = max(i.column + i.w for i in items)
        for i in items:
            i.column = edge - i.w
    elif how == "centre":
        # Twice the centre, so a half column stays a whole number.
        middle = min(i.column for i in items) + max(i.column + i.w for i in items)
        for i in items:
            i.column = max(1, min(COLUMNS - i.w + 1, (middle - i.w + 1) // 2))
    elif how == "top":
        row = min(i.row for i in items)
        for i in items:
            i.row = row
    elif how == "bottom":
        row = max(i.row for i in items)
        for i in items:
            i.row = row
    elif how == "same_width":
        for i in items:
            i.w = max(MIN_WIDTH, min(COLUMNS, first.w))
            i.column = max(1, min(COLUMNS - i.w + 1, i.column))
    elif how == "same_height":
        for i in items:
            i.h = first.h
    else:
        by_row: dict[int, list[Item]] = {}
        for i in items:
            by_row.setdefault(i.row, []).append(i)
        if all(len(held) < 3 for held in by_row.values()):
            raise StreamlitError("Distribute spreads three or more blocks of one row.")
        for held in by_row.values():
            if len(held) < 3:
                continue
            held.sort(key=lambda i: i.column)
            left, right = held[0].column, held[-1].column + held[-1].w
            gaps = even_gaps(right - left - sum(i.w for i in held), len(held) - 1)
            cursor = left
            for item, gap in zip(held, [*gaps, 0], strict=True):
                item.column = cursor
                cursor += item.w + gap
    return [i.id for i in items if before[i.id] != (i.row, i.column, i.w, i.h)]


def outline(page: Page, titles: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The page as a tree, in reading order: each block, each container with its slots and what they hold;
    the sidebar last. `titles`: each block's name."""
    groups = grouped(page)
    named = titles or {}

    def node(item: Item) -> dict[str, Any]:
        said: dict[str, Any] = {
            "id": item.id,
            "kind": item.kind if isinstance(item, Container) else "block",
            "title": item.title if isinstance(item, Container) else named.get(item.id, item.id),
            "row": item.row,
            "column": item.column,
            "w": item.w,
            "hidden": item.hidden,
            "locked": item.locked,
        }
        if isinstance(item, Container):
            names = item.slot_names()
            said["slots"] = [
                {
                    "slot": slot,
                    "name": names[slot],
                    "items": [node(i) for i in groups.get((item.id, slot), [])],
                }
                for slot in range(item.slots)
            ]
        return said

    tree = [node(i) for i in groups.get((None, 0), [])]
    return tree + [node(c) for c in page.containers if c.kind == "sidebar"]


def reset_layout(page: Page) -> None:
    """Reset layout: every block back on the page itself in reading order, two a row at the usual width,
    as tall as what it draws; the containers go (one Undo brings it all back)."""
    for index, block in enumerate(page.blocks):
        block.parent, block.slot, block.hidden, block.locked = None, 0, False, False
        block.w, block.h = DEFAULT_WIDTH, None
        block.row, block.column = index // 2 + 1, 1 + (index % 2) * DEFAULT_WIDTH
    page.containers.clear()
