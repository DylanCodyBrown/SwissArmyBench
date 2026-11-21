"""A widget's I/O contract (the owner, 2026-11-21: "Make a way for input and out from widgets to be defined
and clear. Perhaps the app detects a certain format"): what comes in at run time, what goes out, and the
actions it fires, declared at the top level of the widget's code with sab_canvas's markers and read with
Python's own parser (never run). Its plain top-level values stay its properties (the design-time settings,
domain/widget_properties.py); together they are the widget's contract.

    from sab_canvas import Event, In, Out, Table

    # The orders to show
    orders: In[Table] = None          <- data coming in: its source is wired on the Canvas (a table, another
    region: In[str] = "All"              widget's Out, an endpoint's answer, a variable, a typed value); the
                                         value written is what it takes when nothing is wired
    selected_order: Out[int] = None   <- data going out: the widget assigns it; others' Ins read it
    filtered: Out[Table] = None
    saved: Event[dict] = None         <- an action it fires: `saved(payload)` (`= None` may be left out);
                                         the Canvas wires what it does (call an API.py endpoint with the
                                         payload mapped, set a page value, rerun)

TYPES: Table, str, int, float, bool, date, datetime, list (list[...] of one of these), dict. A declaration
whose marker or type is not one of these is still listed, with its problem in one sentence.

Pure rules: no I/O, standard library only.
"""

from __future__ import annotations

import ast
import datetime
import re
from dataclasses import dataclass
from typing import Any

from swissarmybench_streamlit.domain import widget_properties as props_rules

MARKERS: dict[str, str] = {"In": "in", "Out": "out", "Event": "event"}
SCALARS: tuple[str, ...] = ("Table", "str", "int", "float", "bool", "date", "datetime", "dict")
TYPE_WORDS: dict[str, str] = {
    "Table": "a table",
    "str": "text",
    "int": "a whole number",
    "float": "a number",
    "bool": "yes or no",
    "date": "a date",
    "datetime": "a date and time",
    "dict": "a set of names and values",
    "list": "a list",
}
_ALIASES = {"DataFrame": "Table", "Dict": "dict", "List": "list"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$")


class ContractError(ValueError):
    """A contract that cannot be read (its line), or a wire refused (the reason in one sentence)."""

    def __init__(self, message: str, fix: str = "", line: int | None = None) -> None:
        super().__init__(message)
        self.fix = fix
        self.line = line


@dataclass(frozen=True)
class Port:
    """One declaration: an In, an Out or an Event."""

    name: str
    direction: str  # in | out | event
    type: str  # Table, str, ..., list[str], list
    default: Any = None
    help: str = ""
    line: int = 0
    problem: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction,
            "type": self.type,
            "words": words(self.type),
            "default": self.default,
            "help": self.help,
            "line": self.line,
            "problem": self.problem,
        }


def words(kind: str) -> str:
    """A type in words: "a table", "a list of text"."""
    if kind.startswith("list[") and kind.endswith("]"):
        inner = TYPE_WORDS.get(kind[5:-1], kind[5:-1])
        return "a list of " + (
            inner.removeprefix("a ").removeprefix("an ") + "s" if inner[:2] == "a " else inner
        )
    return TYPE_WORDS.get(kind, kind)


def _head(node: ast.expr) -> str:
    """The marker's name: In, sab_canvas.In, sab.In."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _type(node: ast.expr) -> tuple[str, str | None]:
    """A type annotation's name and its problem (None: it is one of TYPES)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):  # In["list[str]"]
        try:
            return _type(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return node.value, f"{node.value[:40]} is not a type here."
    if isinstance(node, ast.Constant) and node.value is None:
        return "None", "None is not a type: give one of " + ", ".join(SCALARS) + " or list[...]."
    if isinstance(node, ast.Subscript):
        head = _ALIASES.get(_head(node.value), _head(node.value))
        if head == "list":
            inner, problem = _type(node.slice)
            if problem or inner.startswith("list"):
                return f"list[{inner}]", problem or "A list of lists is not a type here: list[str] is."
            return f"list[{inner}]", None
        if head == "dict":
            return "dict", None
        return head or "?", f"{head or 'That'} is not a type here: one of {', '.join(SCALARS)} or list[...]."
    name = _ALIASES.get(_head(node), _head(node))
    if name in SCALARS or name == "list":
        return name, None
    return name or "?", f"{name or 'That'} is not a type here: one of {', '.join(SCALARS)} or list[...]."


def _marker(annotation: ast.expr) -> tuple[str, ast.expr | None] | None:
    """(direction, its type's node) when the annotation is In[...], Out[...] or Event[...] (a bare marker:
    no type; a string annotation is read too); None for any other annotation."""
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            annotation = ast.parse(annotation.value, mode="eval").body
        except SyntaxError:
            return None
    if isinstance(annotation, ast.Subscript) and _head(annotation.value) in MARKERS:
        return MARKERS[_head(annotation.value)], annotation.slice
    if _head(annotation) in MARKERS and isinstance(annotation, (ast.Name, ast.Attribute)):
        return MARKERS[_head(annotation)], None
    return None


def _declaration(statement: ast.stmt) -> tuple[ast.AnnAssign, str, str, ast.expr | None] | None:
    """(the statement, its name, its direction, its type's node) for a top-level In/Out/Event declaration."""
    if not isinstance(statement, ast.AnnAssign) or not isinstance(statement.target, ast.Name):
        return None
    marked = _marker(statement.annotation)
    return None if marked is None else (statement, statement.target.id, marked[0], marked[1])


def is_declaration(statement: ast.stmt) -> bool:
    """A top-level In/Out/Event declaration (never a property)."""
    return _declaration(statement) is not None


def detect(code: str) -> list[Port]:
    """The widget's Ins, Outs and Events, in the order written. Code that does not parse raises
    PropertyError (its line, the properties' own)."""
    module = props_rules.parse(code)
    lines = code.split("\n")
    found: list[Port] = []
    seen: set[str] = set()
    for one in module.body:
        found_one = _declaration(one)
        if found_one is None:
            continue
        statement, name, direction, type_node = found_one
        problem: str | None = None
        if type_node is None and direction == "event":
            kind = "dict"  # an Event's payload is a dict unless it says otherwise
        elif type_node is None:
            kind, problem = "?", f"{name}'s {direction.title()} needs a type: {direction.title()}[str]."
        else:
            kind, problem = _type(type_node)
        default: Any = None
        if statement.value is not None:
            ok, default = props_rules._literal(statement.value)
            if not ok:
                default, problem = (
                    None,
                    problem or f"{name}'s starting value is code: give a plain value or None.",
                )
        if name in seen:  # declared twice: the first one counts
            continue
        if name.startswith("_"):
            continue  # a private name is the widget's own, never part of the contract
        if problem is None and direction == "in" and default is not None and not fits_value(kind, default):
            problem = f"{name}'s starting value is not {words(kind)}."
        if problem is None and direction == "event" and default is not None:
            problem = f"{name} is an Event: it has no value (saved: Event[dict], or = None)."
        seen.add(name)
        found.append(
            Port(
                name=name,
                direction=direction,
                type=kind,
                default=default,
                help=_help(lines, statement.lineno),
                line=statement.lineno,
                problem=problem,
            )
        )
    return found


def _help(lines: list[str], line: int) -> str:
    found: list[str] = []
    at = line - 2
    while at >= 0 and lines[at].strip().startswith("#") and not lines[at].startswith("# ///"):
        found.insert(0, lines[at].strip().lstrip("#").strip())
        at -= 1
    return " ".join(f for f in found if f)[:300]


def without_declarations(code: str, ports: list[Port]) -> str:
    """The code with each declaration made `pass` (its lines kept, so a traceback's line is the widget's
    own): the runtime gives the Ins their values, the Outs their last ones, the Events their callables."""
    module = props_rules.parse(code)
    source = props_rules._Source(code)
    names = {p.name for p in ports}
    spans: list[tuple[int, int, str]] = []
    for statement in module.body:
        found = _declaration(statement)
        if found is not None and found[1] in names:
            start, end = source.span(statement)
            spans.append((start, end, "pass" + "\n" * code[start:end].count("\n")))
            names.discard(found[1])
    for start, end, text in sorted(spans, reverse=True):
        code = code[:start] + text + code[end:]
    return code


# ===== types =====


def fits(given: str, wanted: str) -> bool:
    """Whether a value of type `given` (an Out's, a source's) can feed an In of type `wanted`."""
    if given == wanted:
        return True
    if wanted == "float" and given == "int":
        return True
    if wanted == "Table" and given in ("list[dict]", "list"):
        return True  # records are a table
    if wanted == "list" and given.startswith("list"):
        return True
    if wanted.startswith("list[") and given == "list":
        return True
    if wanted == "list[float]" and given == "list[int]":
        return True
    if wanted == "dict" and given == "Table":
        return False
    return False


def fits_value(kind: str, value: Any) -> bool:
    """Whether a typed constant is of the type (a date as 2026-01-31, a list's items each of its type)."""
    if value is None:
        return True
    if kind == "Table":
        return isinstance(value, list) and all(isinstance(r, dict) for r in value)
    if kind == "str":
        return isinstance(value, str)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "date":
        return isinstance(value, str) and bool(_DATE.match(value)) and _real(value)
    if kind == "datetime":
        return isinstance(value, str) and bool(_DATETIME.match(value))
    if kind == "dict":
        return isinstance(value, dict)
    if kind == "list":
        return isinstance(value, list)
    if kind.startswith("list[") and kind.endswith("]"):
        return isinstance(value, list) and all(fits_value(kind[5:-1], v) for v in value)
    return False


def _real(text: str) -> bool:
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def contract(code: str) -> dict[str, Any]:
    """The whole contract as data: properties (the design-time settings), ins, outs, events."""
    ports = detect(code)
    found = props_rules.detect(code)
    return {
        "properties": [p.to_json() for p in found],
        "ins": [p.to_json() for p in ports if p.direction == "in"],
        "outs": [p.to_json() for p in ports if p.direction == "out"],
        "events": [p.to_json() for p in ports if p.direction == "event"],
    }
