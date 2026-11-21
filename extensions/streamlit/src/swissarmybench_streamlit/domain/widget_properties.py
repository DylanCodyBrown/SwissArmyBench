"""A widget's properties (the owner, 2026-11-21: "The properties pane should expose any variables that was
created to configure the widget and should auto detect its type with masks").

DETECT (Python's own parser, never run): every top-level assignment of a plain value is a property

    # The button's words            <- the comment lines just above: its help
    label = "Click me"
    size: int = 3  # 1..10           <- an annotation always wins over the guess; `# a..b` a range
    kind = "primary"  # choices: primary, secondary, tertiary
    colour = "#1f77b4"               <- a colour (the mask: a colour picker)
    start = "2026-01-01"             <- a date
    table = ""                       <- a table (its name: a table property)
    x = "month"  # column of table   <- a column of that table
    key = os.environ["ORDERS_KEY"]   <- a variable of this computer (or "${NAME}")

TYPES and their MASKS: bool (switch), int and float (number; a range), str (text), colour (colour picker),
date, datetime, time (pickers), choice (dropdown: `Literal[...]` or `# choices:`), table (table picker),
column (column picker: of the first table property, or `# column of <property>`), variable (the variables
list), path (a path), list and dict (a small JSON editor). Names starting with _ are not properties.

WRITE: a property's value is written into ONLY its own characters (the value's expression; for a variable,
the name inside os.environ[...]): every other byte stays as typed. CHECK: a value against its type and mask
before it is kept (a bad colour, a column not in the table, a variable not set here), said in one sentence
with the fix.

Pure rules: no I/O, standard library only.
"""

from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

TYPES: dict[str, str] = {
    "bool": "switch",
    "int": "number",
    "float": "number",
    "str": "text",
    "colour": "colour",
    "date": "date",
    "datetime": "datetime",
    "time": "time",
    "choice": "dropdown",
    "table": "table",
    "column": "column",
    "variable": "variable",
    "path": "path",
    "list": "json",
    "dict": "json",
}
_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$")
_TIME = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")
_VARIABLE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_RANGE = re.compile(r"#\s*(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)(?:\s+step\s+(\d+(?:\.\d+)?))?")
_CHOICES = re.compile(r"#\s*choices?\s*:\s*(.+)$", re.IGNORECASE)
_COLUMN_OF = re.compile(r"#\s*column\s+of\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_KIND_WORD = re.compile(r"#\s*(table|column|colour|color|path|date|datetime|time|variable)\b", re.IGNORECASE)
_PATHLIKE = re.compile(r"^([a-zA-Z]:[\\/]|[\\/]|~|\.{1,2}[\\/])|[\\/].*\.[a-zA-Z0-9]{1,8}$")
_ANNOTATIONS: dict[str, str] = {
    "bool": "bool",
    "int": "int",
    "float": "float",
    "str": "str",
    "Colour": "colour",
    "Color": "colour",
    "date": "date",
    "datetime": "datetime",
    "time": "time",
    "Table": "table",
    "Column": "column",
    "Variable": "variable",
    "Path": "path",
    "list": "list",
    "dict": "dict",
}
MAX_TEXT = 5_000
MAX_JSON = 20_000


class PropertyError(ValueError):
    """A property that cannot be read, set or kept (one sentence; `fix`: what to do; `line`: where)."""

    def __init__(self, message: str, fix: str = "", line: int | None = None) -> None:
        super().__init__(message)
        self.fix = fix
        self.line = line


@dataclass(frozen=True)
class Property:
    name: str
    type: str
    default: Any
    help: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple[str, ...] = ()
    of: str | None = None  # a column's table property
    annotated: bool = False
    line: int = 0
    start: int = 0  # the characters a new value replaces
    end: int = 0
    form: str = "literal"  # literal | environ (os.environ["NAME"]) | reference ("${NAME}")
    problem: str | None = None  # the annotation and the value disagree

    @property
    def mask(self) -> str:
        return TYPES[self.type]

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "mask": self.mask,
            "default": self.default,
            "help": self.help,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
            "choices": list(self.choices),
            "of": self.of,
            "annotated": self.annotated,
            "line": self.line,
            "problem": self.problem,
        }


@dataclass(frozen=True)
class Context:
    """What a value is checked against: the tables there are (name -> its columns; None: not known here),
    the variables set on this computer (None: not known), and the instance's other values (a column's
    table)."""

    tables: dict[str, list[str] | None] | None = None
    variables: set[str] | None = None
    values: dict[str, Any] = field(default_factory=dict)


# ===== reading the code =====


class _Source:
    def __init__(self, code: str) -> None:
        self.code = code
        self.lines = code.split("\n")
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line) + 1)

    def at(self, line: int, column: int) -> int:
        text = self.lines[line - 1]
        return self.starts[line - 1] + len(text.encode("utf-8")[:column].decode("utf-8", "ignore"))

    def span(self, node: ast.AST) -> tuple[int, int]:
        return (
            self.at(node.lineno, node.col_offset),  # type: ignore[attr-defined]
            self.at(node.end_lineno, node.end_col_offset),  # type: ignore[attr-defined]
        )


def parse(code: str) -> ast.Module:
    try:
        return ast.parse(code)
    except SyntaxError as error:
        raise PropertyError(
            f"Line {error.lineno or 1}: {error.msg}.",
            "Finish the line; the properties come back.",
            error.lineno,
        ) from None
    except (ValueError, RecursionError):
        raise PropertyError("The widget's code cannot be read.") from None


def _environ_key(node: ast.expr) -> ast.Constant | None:
    """os.environ["NAME"], os.environ.get("NAME"...), os.getenv("NAME"...): the name's string node."""
    if isinstance(node, ast.Subscript) and _dotted(node.value) == "os.environ":
        key = node.slice
        return key if isinstance(key, ast.Constant) and isinstance(key.value, str) else None
    if isinstance(node, ast.Call) and _dotted(node.func) in ("os.environ.get", "os.getenv") and node.args:
        key = node.args[0]
        return key if isinstance(key, ast.Constant) and isinstance(key.value, str) else None
    return None


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        inner = _dotted(node.value)
        return f"{inner}.{node.attr}" if inner else ""
    return ""


def _literal(node: ast.expr) -> tuple[bool, Any]:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False, None
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, (set, frozenset, bytes, complex)):
        return False, None
    if isinstance(value, float) and not math.isfinite(value):
        return False, None
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False, None
    return True, value


def _annotation(node: ast.expr | None) -> tuple[str | None, tuple[str, ...]]:
    """The annotation's type and, for Literal[...], its choices."""
    if node is None:
        return None, ()
    if isinstance(node, ast.Subscript):
        head = _dotted(node.value).split(".")[-1]
        if head == "Literal":
            items = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            choices = tuple(str(i.value) for i in items if isinstance(i, ast.Constant))
            return "choice", choices
        if head in ("list", "List"):
            return "list", ()
        if head in ("dict", "Dict"):
            return "dict", ()
        return None, ()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):  # a string annotation
        try:
            return _annotation(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return None, ()
    name = _dotted(node).split(".")[-1]
    return _ANNOTATIONS.get(name), ()


def _comment(source: _Source, line: int) -> str:
    """The comment at the end of a line (after the code)."""
    text = source.lines[line - 1]
    in_string: str | None = None
    for i, ch in enumerate(text):
        if in_string:
            if ch == in_string and text[i - 1] != "\\":
                in_string = None
        elif ch in "\"'":
            in_string = ch
        elif ch == "#":
            return text[i:]
    return ""


def _help(source: _Source, line: int) -> str:
    """The comment lines just above a statement, as its help."""
    found: list[str] = []
    at = line - 2
    while at >= 0 and source.lines[at].strip().startswith("#") and not source.lines[at].startswith("# ///"):
        found.insert(0, source.lines[at].strip().lstrip("#").strip())
        at -= 1
    return " ".join(f for f in found if f)[:300]


def _guess(name: str, value: Any, comment: str, tables: set[str]) -> str:
    word = _KIND_WORD.search(comment)
    if word:
        kind = word.group(1).lower()
        return "colour" if kind == "color" else kind
    if _CHOICES.search(comment):
        return "choice"
    if _COLUMN_OF.search(comment):
        return "column"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    if value is None:
        return "str"
    text = str(value)
    lowered = name.lower()
    if _VARIABLE.match(text):
        return "variable"
    if _COLOUR.match(text) or lowered.endswith(("colour", "color")):
        return "colour"
    if _DATETIME.match(text):
        return "datetime"
    if _DATE.match(text):
        return "date"
    if _TIME.match(text):
        return "time"
    if lowered == "table" or lowered.endswith("_table") or (text and text in tables):
        return "table"
    if lowered in ("column", "x", "y") or lowered.endswith(("_column", "_col")):
        return "column"
    if lowered.endswith(("path", "file")) or (text and _PATHLIKE.search(text)):
        return "path"
    return "str"


def _fits(kind: str, value: Any) -> bool:
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "list":
        return isinstance(value, list)
    if kind == "dict":
        return isinstance(value, dict)
    return value is None or isinstance(value, str)


def detect(code: str, tables: set[str] | frozenset[str] = frozenset()) -> list[Property]:
    """The widget's properties, in the order they are written. Code that does not parse raises
    PropertyError (its line)."""
    module = parse(code)
    source = _Source(code)
    found: list[Property] = []
    seen: set[str] = set()
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                continue
            target, value, annotation = statement.targets[0].id, statement.value, None
        elif isinstance(statement, ast.AnnAssign):
            if not isinstance(statement.target, ast.Name) or statement.value is None:
                continue
            target, value, annotation = statement.target.id, statement.value, statement.annotation
        else:
            continue
        if target.startswith("_") or target in seen:
            continue
        comment = _comment(source, statement.end_lineno or statement.lineno)
        key = _environ_key(value)
        form = "literal"
        if key is not None:
            kind_guess, default, form = "variable", key.value, "environ"
            start, end = source.span(key)
        else:
            ok, default = _literal(value)
            if not ok:
                continue  # code, not a plain value: not a property
            start, end = source.span(value)
            match = _VARIABLE.match(default) if isinstance(default, str) else None
            if match:
                default, form = match.group(1), "reference"
            kind_guess = _guess(target, default if form == "literal" else "${x}", comment, set(tables))
        annotated_kind, choices = _annotation(annotation)
        kind = annotated_kind or kind_guess
        problem = None
        if annotated_kind and form == "literal" and not _fits_type(annotated_kind, default):
            problem = f"The annotation says {annotated_kind}, the value is {type(default).__name__}."
        if kind == "choice" and not choices:
            said = _CHOICES.search(comment)
            choices = tuple(c.strip() for c in said.group(1).split(",") if c.strip()) if said else ()
            if not choices and isinstance(default, list):
                choices = tuple(str(c) for c in default)
        minimum = maximum = step = None
        ranged = _RANGE.search(comment)
        if ranged and kind in ("int", "float"):
            minimum, maximum = float(ranged.group(1)), float(ranged.group(2))
            step = float(ranged.group(3)) if ranged.group(3) else None
        of = None
        if kind == "column":
            said_of = _COLUMN_OF.search(comment)
            of = said_of.group(1) if said_of else next((p.name for p in found if p.type == "table"), None)
        seen.add(target)
        found.append(
            Property(
                name=target,
                type=kind,
                default=default,
                help=_help(source, statement.lineno),
                minimum=minimum,
                maximum=maximum,
                step=step,
                choices=choices,
                of=of,
                annotated=annotated_kind is not None,
                line=statement.lineno,
                start=start,
                end=end,
                form=form,
                problem=problem,
            )
        )
    return found


def _fits_type(kind: str, value: Any) -> bool:
    if kind in ("bool", "int", "float", "list", "dict"):
        return _fits(kind, value)
    if kind == "choice":
        return isinstance(value, (str, int, float)) and not isinstance(value, bool)
    return isinstance(value, str)


# ===== checking a value =====


def check(prop: Property, value: Any, context: Context | None = None) -> None:
    """A value for this property, checked against its type and mask. Raises PropertyError (what is wrong,
    and the fix) or returns."""
    context = context or Context()
    name, kind = prop.name, prop.type
    if not _fits_type(kind, value) and not (kind == "float" and isinstance(value, int)):
        raise PropertyError(
            f"{name} is {_words(kind)}: {json.dumps(value)[:60]} is not.", f"Give {name} {_words(kind)}."
        )
    if kind in ("int", "float"):
        number = float(value)
        if not math.isfinite(number):
            raise PropertyError(f"{name} is a number.", "Type a number.")
        if prop.minimum is not None and number < prop.minimum:
            raise PropertyError(f"{name} is {_n(prop.minimum)} at least.", f"Use {_n(prop.minimum)} or more.")
        if prop.maximum is not None and number > prop.maximum:
            raise PropertyError(f"{name} is {_n(prop.maximum)} at most.", f"Use {_n(prop.maximum)} or less.")
    elif kind == "colour" and value and not _COLOUR.match(value):
        raise PropertyError(f"{value[:40]} is not a colour.", "Pick a colour, as #1f77b4.")
    elif kind == "date" and value and not (_DATE.match(value) and _real_date(value)):
        raise PropertyError(f"{value[:40]} is not a date.", "Pick a date, as 2026-01-31.")
    elif kind == "datetime" and value and not _DATETIME.match(value):
        raise PropertyError(f"{value[:40]} is not a date and time.", "Pick one, as 2026-01-31 09:30.")
    elif kind == "time" and value and not _TIME.match(value):
        raise PropertyError(f"{value[:40]} is not a time.", "Pick a time, as 09:30.")
    elif kind == "choice" and prop.choices and str(value) not in prop.choices:
        raise PropertyError(
            f"{name} is one of {', '.join(prop.choices)}.", f"Pick one of {', '.join(prop.choices[:6])}."
        )
    elif kind == "table" and value and context.tables is not None and value not in context.tables:
        raise PropertyError(
            f"There is no table called {value[:60]} here.",
            "Pick an open table, or leave it empty for sample data.",
        )
    elif kind == "column" and value:
        table = context.values.get(prop.of or "", None) if prop.of else None
        columns = (context.tables or {}).get(table) if isinstance(table, str) and table else None
        if columns is not None and value not in columns:
            raise PropertyError(
                f"{table} has no column {value[:60]}.", f"Pick one of {', '.join(columns[:6])}."
            )
    elif kind == "variable":
        if not _ENV_NAME.match(value or ""):
            raise PropertyError(f"{value[:40]} is not a variable's name.", "Pick a variable from the list.")
        if context.variables is not None and value not in context.variables:
            raise PropertyError(
                f"{value} is not set on this computer.", f"Set {value} on the Variables page."
            )
    elif kind == "str" and len(value or "") > MAX_TEXT:
        raise PropertyError(f"{name} is {MAX_TEXT} characters at most.", "Shorten it.")
    elif kind in ("list", "dict") and len(json.dumps(value)) > MAX_JSON:
        raise PropertyError(f"{name} is too large to keep here.", "Keep it under 20 KB.")


def _real_date(text: str) -> bool:
    import datetime

    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _n(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else str(number)


def _words(kind: str) -> str:
    return {
        "bool": "on or off",
        "int": "a whole number",
        "float": "a number",
        "list": "a list",
        "dict": "a set of names and values",
        "choice": "one of its choices",
    }.get(kind, "text")


def coerce(prop: Property, value: Any) -> Any:
    """A value as its property keeps it: a whole number for an int, a float for a float."""
    if prop.type == "int" and isinstance(value, float) and value.is_integer():
        return int(value)
    if prop.type == "float" and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


# ===== writing a value back =====


def literal(value: Any) -> str:
    """A value as Python source (a string with double quotes, as most code is written)."""
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{literal(str(k))}: {literal(v)}" for k, v in value.items()) + "}"
    raise PropertyError("That is not a plain value.")


def set_default(code: str, name: str, value: Any, context: Context | None = None) -> str:
    """The code with property `name`'s value written in (checked first). Only the value's characters
    change."""
    props = {p.name: p for p in detect(code)}
    prop = props.get(name)
    if prop is None:
        raise PropertyError(f"The widget has no property {name}.", "Pick one of its properties.")
    check(prop, value, context)
    value = coerce(prop, value)
    if prop.form == "environ":
        text = json.dumps(str(value))
    elif prop.form == "reference" or prop.type == "variable":
        text = json.dumps("${" + str(value) + "}")
    else:
        text = literal(value)
    after = code[: prop.start] + text + code[prop.end :]
    parse(after)
    return after


def values(
    props: list[Property], overrides: dict[str, Any], context: Context | None = None
) -> dict[str, Any]:
    """Each property's value for one instance: its override when that is still good for it, else its
    default."""
    out: dict[str, Any] = {}
    for prop in props:
        if prop.name in overrides:
            try:
                check(prop, overrides[prop.name], context)
            except PropertyError:
                out[prop.name] = prop.default
            else:
                out[prop.name] = coerce(prop, overrides[prop.name])
        else:
            out[prop.name] = prop.default
    return out


def without_properties(code: str, props: list[Property]) -> str:
    """The code with each property's assignment made `pass` (its lines kept, so a traceback's line is the
    widget's own): the page gives the properties their values before it runs."""
    module = parse(code)
    source = _Source(code)
    names = {p.name for p in props}
    spans: list[tuple[int, int, str]] = []
    for statement in module.body:
        target = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
        elif isinstance(statement, ast.AnnAssign):
            target = statement.target
        if isinstance(target, ast.Name) and target.id in names:
            start, end = source.span(statement)
            lines = code[start:end].count("\n")
            spans.append((start, end, "pass" + "\n" * lines))
            names.discard(target.id)
    for start, end, text in sorted(spans, reverse=True):
        code = code[:start] + text + code[end:]
    return code
