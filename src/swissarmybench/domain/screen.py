"""The screen state: what one window shows, as text the agent reads on demand (the owner, 2026-11-27).

"what if the app always get a version of what is rendered on screen available to the agent at all times
... Instead of a snapshot it's literally just feeding the state back to the agent." / "It shouldn't send the
screen every turn that will kill context. it should just be accessible when needed."

Every window reports what it shows; this module is the ONE shape a report is read into (`clean`): a known key
with a known type is kept, everything else is dropped, so a page cannot send what the shape has no place for.

**Names only, never a value.** The shape has places for names (a table, its columns, a file's path, a
dialog's title), numbers (a row count, a cursor's line, a selected cell's row and column number) and states;
none for a cell's value, a printed output, a line of code or a secret. A step is said by its kind and the
columns it names: a filter's value may be a cell's own, so it is never taken (`step_words`). The agent reads
values through its other commands (row_read, workbench_read...), which are audited.

A window's state is at most MAX_BYTES of JSON; a larger one is trimmed in TRIMS' order and says which ran.
Standard library only; no I/O, no clock.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# One window's state as JSON, at most (the owner's brief: "a size cap per window (say 8 KB)").
MAX_BYTES: int = 8 * 1024
# A page's report as it arrives, at most: a larger one is not read at all.
MAX_REPORT_BYTES: int = 64 * 1024
NAME_LENGTH: int = 160  # a name, a title, a path
TEXT_LENGTH: int = 300  # an error's or a notice's sentence
LIST_LENGTH: int = 200  # any list, before the cap's trims

NOT_REPORTED = "This window has not reported what it shows yet."
NO_WINDOWS = "No window of Swiss Army Bench is open."


@dataclass(frozen=True)
class Text:
    """A string of at most `most` characters, its white space made single spaces."""

    most: int = NAME_LENGTH


@dataclass(frozen=True)
class Number:
    """A whole number (a count, a line, a row); never a number with a fraction, never a bool."""


@dataclass(frozen=True)
class Flag:
    """True or false."""


@dataclass(frozen=True)
class Many:
    """A list of `of`, at most LIST_LENGTH."""

    of: Any


NAME = Text()
SENTENCE = Text(TEXT_LENGTH)
COUNT = Number()
FLAG = Flag()
NAMES = Many(NAME)

# What a step may say of itself: its kind, on or off, the columns it names, a filter's test (a word of
# FILTER_WORDS), a sort's directions. Never its value.
STEP: dict[str, Any] = {
    "kind": NAME,
    "enabled": FLAG,
    "op": NAME,
    "columns": NAMES,
    "directions": NAMES,
}

# A tab's document; `view`: a text document's view (preview, split or source: its tab's Preview toggle);
# `comments`: how many annotations wait on it (the count only, never an annotation's words).
DOCUMENT: dict[str, Any] = {
    "title": NAME,
    "path": NAME,
    "kind": NAME,
    "dirty": FLAG,
    "view": NAME,
    "comments": COUNT,
}

# The page-specific parts, by name: each a page's own hook (blazor: ScreenState.Show).
PARTS: dict[str, dict[str, Any]] = {
    # The Tables page's table in front.
    "table": {
        "grid": NAME,
        "name": NAME,
        "title": NAME,
        "rows": COUNT,
        "columns": Many({"name": NAME, "type": NAME}),
        "steps": Many(STEP),
        "selection": {
            "kind": NAME,  # none, cells, rows, columns, all
            "rows": Many({"first": COUNT, "last": COUNT}),  # row numbers as the grid counts them, from 1
            "columns": NAMES,
            "column_numbers": Many(COUNT),  # from 1, as the columns stand
        },
        "showing": {"first": COUNT, "last": COUNT},  # the rows on screen, from 1
        "split": NAMES,  # two tables side by side: their names
        "tabs": NAMES,
        "panels": NAMES,
    },
    # A notebook: the cell in focus and each cell on screen.
    "notebook": {
        "cells": COUNT,
        "focused": COUNT,  # the cell's number (never changes, never reused)
        "visible": Many({"number": COUNT, "kind": NAME, "name": NAME, "state": NAME}),
    },
    # A script or a .sql file: its language and whether it runs.
    "script": {"language": NAME, "running": FLAG},
    "canvas": {
        "path": NAME,
        "page": NAME,
        "pages": NAMES,
        "layout": NAME,  # desktop or phone
        "selection": Many({"id": NAME, "kind": NAME, "widget": NAME, "title": NAME}),
        "items": COUNT,
        "zoom": COUNT,
        "playing": FLAG,
        "full_screen": FLAG,
    },
    "analyze": {
        "analysis": NAME,
        "table": NAME,
        "form": Many({"slot": NAME, "columns": NAMES}),
        "missing": SENTENCE,
        "dashboard": NAME,
        "cards": Many({"title": NAME, "kind": NAME}),
    },
    # The Connections page (read from its address: `clean`): the cards, a card's detail, a form.
    "connections": {"view": NAME, "selected": NAME},
    "settings": {"section": NAME, "sections": NAMES},
    "home": {"view": NAME},
}

# One window's report: what every page says the same way, then the parts.
WINDOW: dict[str, Any] = {
    "window": NAME,  # the window's own name (sab-home, sab-notebooks...)
    "page": NAME,  # the address's path under /blazor/
    "address": Text(400),
    "title": NAME,
    "project": NAME,  # the open project's name
    "width": COUNT,
    "height": COUNT,
    "focused": FLAG,
    "tab": DOCUMENT,  # the open tab's document
    "tabs": Many(DOCUMENT),
    "cursor": {"line": COUNT, "column": COUNT},
    "selection": {"from_line": COUNT, "to_line": COUNT},
    "panes": NAMES,
    "dialogs": NAMES,
    "menus": NAMES,
    "errors": Many(SENTENCE),
    "notices": Many(SENTENCE),
    "problems": COUNT,
    "session": NAME,  # the Python session's word: Ready, Running…, Not started
    # Pop out (domain/pop_outs.py): the page or table this window holds as its own window; what other
    # windows hold; and the placeholder this window shows where one of those was.
    "pop_out": NAME,
    "popped_out": NAMES,
    "placeholder": SENTENCE,
    **PARTS,
}

# A page's first path part and the kind of window it makes; anything else is its own word.
KINDS: dict[str, str] = {
    "": "home",
    "grids": "tables",
    "tables": "tables",
    "workspace": "tables",
    "widget": "widgets",
    "apps": "canvas",
}

FILTER_WORDS: dict[str, str] = {
    "eq": "is",
    "ne": "is not",
    "gt": "is greater than",
    "ge": "is at least",
    "lt": "is less than",
    "le": "is at most",
    "contains": "contains",
    "not_contains": "does not contain",
    "starts_with": "starts with",
    "ends_with": "ends with",
    "in": "is one of",
    "not_in": "is none of",
    "between": "is between",
    "blank": "is blank",
    "not_blank": "is not blank",
    "before": "is before",
    "after": "is after",
    "date_between": "is between",
    "true": "is true",
    "false": "is false",
}
# A filter's tests that name no value.
_NO_VALUE = ("blank", "not_blank", "true", "false")

STEP_WORDS: dict[str, str] = {
    "columns": "Keep columns",
    "rename": "Rename",
    "group_by": "Group by",
    "distinct": "Keep distinct rows",
    "limit": "Keep the first rows",
    "transform": "Change the text of",
    "bucket": "Bucket",
    "categorize": "Categorize",
    "sql": "SQL",
}

# The cap's trims, in the order they run (each only while the state is still over MAX_BYTES).
TRIMS: tuple[tuple[str, str], ...] = (
    ("lists_30", "every list cut to its first 30"),
    ("texts_120", "every error and notice cut to 120 characters"),
    ("lists_10", "every list cut to its first 10"),
    ("lists_3", "every list cut to its first 3"),
    ("parts", "the page's own parts left out"),
)


def kind_of(page: str) -> str:
    """The kind of window a page makes: its first path part (tables, notebooks, scripts, canvas...)."""
    first = page.strip("/").split("/", 1)[0].split("?", 1)[0].lower()
    return KINDS.get(first, first or "home")


def _text(value: object, most: int) -> str | None:
    if not isinstance(value, str):
        return None
    words = " ".join(value.split())
    return words if len(words) <= most else words[: most - 1] + "…"


def _take(value: object, spec: Any) -> Any:
    """`value` read as `spec`, or None when it is not that."""
    if isinstance(spec, Text):
        return _text(value, spec.most)
    if isinstance(spec, Number):
        return (
            value if isinstance(value, int) and not isinstance(value, bool) and abs(value) < 2**53 else None
        )
    if isinstance(spec, Flag):
        return value if isinstance(value, bool) else None
    if isinstance(spec, Many):
        if not isinstance(value, list):
            return None
        taken = (_take(item, spec.of) for item in value[:LIST_LENGTH])
        return [item for item in taken if item not in (None, {})]
    if not isinstance(value, dict):
        return None
    read = {key: _take(value.get(key), inner) for key, inner in spec.items() if key in value}
    return {key: item for key, item in read.items() if item is not None and item != {}}


def step_words(step: dict[str, Any], number: int) -> str:
    """One step in plain words by its kind and the columns it names: never its value."""
    kind = str(step.get("kind", ""))
    columns = [str(c) for c in step.get("columns", [])]
    named = ", ".join(columns)
    if kind == "filter":
        op = str(step.get("op", ""))
        test = FILTER_WORDS.get(op, "")
        tail = "" if op in _NO_VALUE or not test else " a value (not shown)"
        words = f"Keep rows where {named or 'a column'} {test}{tail}".rstrip()
    elif kind == "sort":
        directions = [str(d) for d in step.get("directions", [])]
        keys = (
            f"{c} {'descending' if at < len(directions) and directions[at] == 'desc' else 'ascending'}"
            for at, c in enumerate(columns)
        )
        words = "Sort by " + ", ".join(keys)
    else:
        words = f"{STEP_WORDS.get(kind, kind or 'A step')} {named}".rstrip()
    return f"{number}. {words}{'' if step.get('enabled', True) else ' (off)'}"


def _table(table: dict[str, Any]) -> dict[str, Any]:
    """The table part as the agent reads it: its steps in words, and the sort and the filtered columns they
    make (the last sort that is on; every filter that is on)."""
    steps = table.pop("steps", [])
    on = [s for s in steps if s.get("enabled", True)]
    sorts = [s for s in on if s.get("kind") == "sort"]
    if sorts:
        last = sorts[-1]
        directions = last.get("directions", [])
        table["sort"] = [
            {"column": c, "direction": "descending" if directions[at : at + 1] == ["desc"] else "ascending"}
            for at, c in enumerate(last.get("columns", []))
        ]
    filtered = [c for s in on if s.get("kind") == "filter" for c in s.get("columns", [])]
    if filtered:
        table["filter"] = list(dict.fromkeys(filtered))
    if steps:
        table["steps"] = [step_words(s, at) for at, s in enumerate(steps, start=1)]
    return table


# The Connections page's views by the address's key (its page keeps each there), the first that is there.
_CONNECTION_VIEWS: tuple[tuple[str, str], ...] = (
    ("queries", "queries"),
    ("edit", "edit"),
    ("kind", "add"),
    ("name", "detail"),
    ("sandboxshown", "sandbox"),
    ("add", "add"),
    ("find", "find"),
)


_ESCAPES = re.compile(rb"%([0-9A-Fa-f]{2})")


def _plain(text: str) -> str:
    """A query's key or value as typed: `+` a space, `%20` its character (the domain reads no urllib)."""
    raw = _ESCAPES.sub(lambda found: bytes.fromhex(found.group(1).decode()), text.replace("+", " ").encode())
    return raw.decode("utf-8", "replace")


def _query(address: str) -> dict[str, str]:
    """The address's query by its keys in lower case, the last of each; a key alone has an empty value."""
    pairs = (pair.partition("=") for pair in address.partition("?")[2].partition("#")[0].split("&") if pair)
    return {_plain(key).lower(): _plain(value) for key, _, value in pairs}


def _from_address(kind: str, address: str) -> dict[str, Any]:
    """The parts a page keeps in its address: the Connections page's view and selected card, Home's view."""
    asked = _query(address)
    if kind == "connections":
        view = next((word for key, word in _CONNECTION_VIEWS if key in asked), "cards")
        selected = _text(asked.get("name") or asked.get("edit") or "", NAME_LENGTH)
        return {"connections": {"view": view} | ({"selected": selected} if selected else {})}
    if kind == "home":
        return {"home": {"view": "projects" if asked.get("view") == "projects" else "home"}}
    return {}


def clean(raw: object) -> dict[str, Any]:
    """A page's report read into the one shape (WINDOW): unknown keys and wrong types dropped, the kind worked
    out from the page, the table's steps as words, then the cap."""
    state: dict[str, Any] = _take(raw, WINDOW) or {}
    state = {"kind": kind_of(state.get("page", "")), **state}
    parts = _from_address(state["kind"], state.get("address", "")) if "page" in state else {}
    for part, read in parts.items():
        state[part] = read | state.get(part, {})
    if "table" in state:
        state["table"] = _table(state["table"])
    return capped(state)


def size(state: dict[str, Any]) -> int:
    """The state's size as the JSON the agent reads, in bytes."""
    return len(json.dumps(state, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _cut_lists(value: Any, most: int) -> Any:
    if isinstance(value, list):
        return [_cut_lists(item, most) for item in value[:most]]
    if isinstance(value, dict):
        return {key: _cut_lists(item, most) for key, item in value.items()}
    return value


def _trim(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name.startswith("lists_"):
        cut: dict[str, Any] = _cut_lists(state, int(name.removeprefix("lists_")))
        return cut
    if name == "texts_120":
        short = {k: [_text(t, 120) for t in state[k]] for k in ("errors", "notices") if k in state}
        return state | short
    return {key: item for key, item in state.items() if key not in PARTS}


def capped(state: dict[str, Any], most: int = MAX_BYTES) -> dict[str, Any]:
    """`state` within `most` bytes: TRIMS run in order until it fits; `trimmed` names the ones that ran."""
    ran: list[str] = []
    for name, _words in TRIMS:
        if size(state | ({"trimmed": ran} if ran else {})) <= most:
            break
        state = _trim(state, name)
        ran.append(name)
    return state | {"trimmed": ran} if ran else state


def _plural(count: int, word: str) -> str:
    return f"{count:,} {word}" if count == 1 else f"{count:,} {word}s"


def _table_line(table: dict[str, Any]) -> str:
    parts = [f"table {table.get('name') or table.get('title') or table.get('grid', '')}".rstrip()]
    if "rows" in table:
        parts.append(_plural(table["rows"], "row"))
    if table.get("columns"):
        parts.append(_plural(len(table["columns"]), "column"))
    if table.get("steps"):
        parts.append(_plural(len(table["steps"]), "step"))
    if table.get("sort"):
        parts.append("sorted by " + ", ".join(f"{s['column']} {s['direction']}" for s in table["sort"]))
    selection = table.get("selection", {})
    if selection.get("kind") not in (None, "none"):
        parts.append(f"{selection['kind']} selected")
    return ", ".join(parts)


def shows(state: dict[str, Any]) -> str:
    """One line of what a window shows, for the list of every window."""
    said: list[str] = []
    if state.get("placeholder"):
        said.append(f"{state['placeholder']} (Reattach brings it back)")
    if state.get("pop_out"):
        said.append(f"{state['pop_out']}, popped out in its own window")
    if state.get("table"):
        said.append(_table_line(state["table"]))
    tab = state.get("tab", {})
    if tab.get("path") or tab.get("title"):
        dirty = " (unsaved)" if tab.get("dirty") else ""
        view = f", {tab['view']} view" if tab.get("view") else ""
        said.append(f"{tab.get('kind') or 'document'} {tab.get('path') or tab.get('title')}{dirty}{view}")
        if tab.get("comments"):
            said.append(f"{tab['comments']} annotation{'s' if tab['comments'] != 1 else ''} waiting")
    if "cursor" in state:
        said.append(f"cursor at line {state['cursor'].get('line', 0)}")
    if state.get("notebook", {}).get("focused"):
        said.append(f"cell [{state['notebook']['focused']}] in focus")
    canvas = state.get("canvas", {})
    if canvas:
        said.append(f"canvas {canvas.get('path', '')} page {canvas.get('page', '')}".rstrip())
    analyze = state.get("analyze", {})
    if analyze:
        said.append(
            f"{analyze.get('analysis') or 'the board'}, {_plural(len(analyze.get('cards', [])), 'card')}"
        )
    connections = state.get("connections", {})
    if connections:
        named = f" {connections['selected']}" if connections.get("selected") else "s"
        said.append(f"connection{named} ({connections.get('view', 'cards')})")
    if state.get("settings", {}).get("section"):
        said.append(f"section {state['settings']['section']}")
    if state.get("dialogs"):
        said.append("dialog " + ", ".join(state["dialogs"]))
    if state.get("errors"):
        said.append(_plural(len(state["errors"]), "error") + " showing")
    return "; ".join(said)


def brief(state: dict[str, Any]) -> dict[str, Any]:
    """A window in brief: what it is and one line of what it shows."""
    kept = ("kind", "window", "page", "title", "focused", "dialogs", "problems")
    answer = {key: state[key] for key in kept if key in state}
    if "width" in state and "height" in state:
        answer["size"] = [state["width"], state["height"]]
    return answer | {"shows": shows(state)}
