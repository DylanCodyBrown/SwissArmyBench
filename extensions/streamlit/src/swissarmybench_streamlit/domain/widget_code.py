"""A cell's Streamlit code read and written back (the canvas's property pane, the owner 2026-11-19: "From
here we can edit things in Streamlit like state and cache as well for a widget").

READ (Python's own parser, nothing run):

  widgets     every Streamlit element the cell calls, in the order it is written: its call (`selectbox`), the
              name its value is given, its label, its key (and the key the page gives one that has none), each
              argument as what it is (a plain value, a name, a session state key, a variable of this computer,
              or code), its events' handlers
  functions   the cell's functions: whether st.cache_data or st.cache_resource decorates each, and the
              decorator's arguments (ttl, max_entries, show_spinner, persist)
  variables   the variables of this computer it reads (os.environ, os.getenv, secret(), `${NAME}` in a text)

WRITE: every change finds the exact call or decorator with the parser and changes ONLY those characters: the
cell's comments, spacing and line breaks stay as typed, and nothing is ever written again as a whole
(`Change.edits` are those characters, against the text as it was). A value that is code (`value=load()`) is
never written over: `NotPlain`, said plainly, and the pane shows it read-only with Go to cell.

  set_argument   a property's plain value (a default, a label, options, a key), or taken away (reset)
  bind           a property bound to a name another cell makes, a session state key, a variable of this
                 computer, or a short expression
  add_handler    an event's handler: a function stub above the statement and `on_change=` set
  set_cache      a function's cache decorator: added, its arguments set or taken away, its kind
                 changed, removed

Pure rules, no I/O; standard library only.
"""

from __future__ import annotations

import ast
import datetime
import difflib
import keyword
import math
import re
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain.cell_facts import WIDGETS
from swissarmybench_streamlit.domain import toolbox

MAX_TEXT: int = 2_000
MAX_ITEMS: int = 200
MAX_EXPRESSION: int = 200
EVENTS: tuple[str, ...] = ("on_change", "on_click", "on_submit", "on_select")
CACHES: dict[str, str] = {"data": "cache_data", "resource": "cache_resource"}
CACHE_SETTINGS: tuple[str, ...] = ("ttl", "max_entries", "show_spinner", "persist")
BINDINGS: tuple[str, ...] = ("name", "state", "variable", "expression")
_VARIABLE = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?\}")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CodeError(ValueError):
    """A change that cannot be made (the message says why, in one sentence)."""


class NotPlain(CodeError):
    """The code there is not a plain value: it is shown read-only, and changed in its cell."""


@dataclass(frozen=True)
class Edit:
    """Characters [start, end) of the text as it was, replaced by `text`."""

    start: int
    end: int
    text: str

    def to_json(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "text": self.text}


@dataclass(frozen=True)
class Change:
    code: str  # the cell's code after it
    edits: tuple[Edit, ...]  # only the characters that changed, against the code before
    line: int | None = None  # where to go afterwards (a handler's `def`), in the code after
    handler: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "edits": [e.to_json() for e in self.edits],
            "line": self.line,
            "handler": self.handler,
        }


def apply(code: str, edits: Any) -> str:
    """The text with the edits made (they do not overlap)."""
    for edit in sorted(edits, key=lambda e: (e.start, e.end), reverse=True):
        code = code[: edit.start] + edit.text + code[edit.end :]
    return code


def edits_between(before: str, after: str) -> tuple[Edit, ...]:
    """The characters that differ, as edits against `before`."""
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    return tuple(
        Edit(i1, i2, after[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"
    )


def _change(
    before: str, after: str, line: int | None = None, handler: str | None = None, edits: Any = None
) -> Change:
    try:
        ast.parse(after)
    except (SyntaxError, ValueError, RecursionError) as error:  # never written: the cell stays as it was
        raise CodeError(f"That change would not leave whole Python ({error}): nothing was changed.") from None
    made = tuple(sorted(edits, key=lambda e: e.start)) if edits is not None else edits_between(before, after)
    return Change(after, made, line, handler)


class _Source:
    """A cell's text, and ast's places (lines from 1, columns in UTF-8 bytes) as places in it."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.lines = code.split("\n")
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line) + 1)

    def at(self, line: int, column: int) -> int:
        text = self.lines[line - 1]
        return self.starts[line - 1] + len(text.encode("utf-8")[:column].decode("utf-8", "ignore"))

    def span(self, node: Any) -> tuple[int, int]:
        return self.at(node.lineno, node.col_offset), self.at(node.end_lineno, node.end_col_offset)

    def text(self, node: Any) -> str:
        start, end = self.span(node)
        return self.code[start:end]

    def line_start(self, offset: int) -> int:
        return self.code.rfind("\n", 0, offset) + 1

    def line_end(self, offset: int) -> int:
        found = self.code.find("\n", offset)
        return len(self.code) if found < 0 else found


def _parse(code: str) -> ast.Module:
    try:
        return ast.parse(code)
    except SyntaxError as error:
        raise CodeError(
            f"The cell is not whole Python yet (line {error.lineno or 1}: {error.msg}): "
            "finish it in its cell."
        ) from None
    except (ValueError, RecursionError):
        raise CodeError("The cell's code cannot be read.") from None


# ===== a value, as what it is =====


@dataclass(frozen=True)
class Value:
    """An argument as written. kind: literal (a plain value: `value`), name (another cell's name or this
    cell's: `target`), state (st.session_state's key), variable (os.environ's or secret()'s name),
    expression (code: read-only)."""

    kind: str
    source: str
    value: Any = None
    target: str | None = None
    form: str = ""  # a literal's: "tuple", "date"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "value": self.value,
            "target": self.target,
            "form": self.form,
        }


def _plain(value: Any, depth: int = 0) -> bool:
    if value is None or isinstance(value, bool | int | str):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if depth > 4:
        return False
    if isinstance(value, list | tuple):
        return len(value) <= MAX_ITEMS and all(_plain(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return len(value) <= MAX_ITEMS and all(
            isinstance(k, str) and _plain(v, depth + 1) for k, v in value.items()
        )
    return False


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple | list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def _is_state(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "session_state"


def _text_of(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _environ_name(node: ast.AST) -> str | None:
    """os.environ["X"], os.environ.get("X"), os.getenv("X"), secret("X"), sab.secret("X")."""
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "environ"
    ):
        return _text_of(node.slice)
    if not isinstance(node, ast.Call) or not node.args:
        return None
    func = node.func
    first = _text_of(node.args[0])
    if isinstance(func, ast.Attribute):
        if func.attr == "get" and isinstance(func.value, ast.Attribute) and func.value.attr == "environ":
            return first
        if func.attr in ("getenv", "secret"):
            return first
    if isinstance(func, ast.Name) and func.id in ("getenv", "secret"):
        return first
    return None


def _date(node: ast.AST) -> str | None:
    """date(2026, 1, 31) or datetime.date(2026, 1, 31) as 2026-01-31."""
    if not isinstance(node, ast.Call) or node.keywords or len(node.args) != 3:
        return None
    func = node.func
    named = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
    if named != "date" or not all(isinstance(a, ast.Constant) and type(a.value) is int for a in node.args):
        return None
    try:
        year, month, day = (a.value for a in node.args)  # type: ignore[attr-defined]
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def read_value(src: _Source, node: ast.AST) -> Value:
    source = src.text(node)
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        value = ...
    if value is not ... and _plain(value):
        return Value("literal", source, _jsonable(value), form="tuple" if isinstance(value, tuple) else "")
    day = _date(node)
    if day is not None:
        return Value("literal", source, day, form="date")
    if isinstance(node, ast.Name):
        return Value("name", source, target=node.id)
    key: str | None = None
    if isinstance(node, ast.Subscript) and _is_state(node.value):
        key = _text_of(node.slice)
    elif isinstance(node, ast.Attribute) and _is_state(node.value):
        key = node.attr
    elif (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and _is_state(node.func.value)
        and node.args
    ):
        key = _text_of(node.args[0])
    if key is not None:
        return Value("state", source, target=key)
    name = _environ_name(node)
    if name is not None:
        return Value("variable", source, target=name)
    return Value("expression", source)


# ===== reading a cell =====


@dataclass(frozen=True)
class Widget:
    index: int  # among the cell's elements, in the order they are written, from 0
    call: str
    line: int
    target: str | None  # region = st.selectbox(...)
    widget: bool  # it gives a value the page's user chose (it has a session state key)
    key: str | None  # its own key, when a plain text
    auto: int | None  # the page keys it "<block>_<auto>" when it has no key of its own
    arguments: dict[str, Value] = field(default_factory=dict)
    by_position: tuple[str, ...] = ()  # the arguments given without a name
    spread: bool = False  # it takes **something: its arguments are not all known
    default: str | None = None  # the parameter that is its default value
    event: str | None = None  # the event it has

    def to_json(self, block: str | None = None) -> dict[str, Any]:
        label = self.arguments.get("label") or self.arguments.get("body")
        events = {
            name: {"handler": value.target if value.kind == "name" else None, "source": value.source}
            for name, value in self.arguments.items()
            if name in EVENTS
        }
        return {
            "index": self.index,
            "call": self.call,
            "line": self.line,
            "target": self.target,
            "widget": self.widget,
            "label": label.value if label is not None and label.kind == "literal" else None,
            "key": self.key,
            # What st.session_state calls it on the page: its own key, else the one the page gives it.
            "state_key": self.key
            or (f"{block}_{self.auto}" if block and self.auto is not None and self.widget else None),
            "arguments": {name: value.to_json() for name, value in self.arguments.items()},
            "by_position": list(self.by_position),
            "spread": self.spread,
            "default": self.default,
            "event": self.event,
            "events": events,
        }


@dataclass(frozen=True)
class Function:
    name: str
    line: int
    cache: str | None  # data, resource, or None: not cached
    settings: dict[str, Value] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "line": self.line,
            "cache": self.cache,
            "settings": {name: value.to_json() for name, value in self.settings.items()},
        }


def aliases(tree: ast.AST) -> set[str]:
    """The names Streamlit goes by in the cell: st (every page has it), and its own imports'."""
    found = {"st"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.asname or a.name for a in node.names if a.name == "streamlit"}
    return found


def _alias(tree: ast.AST) -> str:
    """The name to write Streamlit by: st (every page has it) unless the cell imports it by another."""
    imported = sorted(aliases(tree) - {"st"})
    plain = any(
        isinstance(n, ast.Import) and any(a.name == "streamlit" and a.asname in (None, "st") for a in n.names)
        for n in ast.walk(tree)
    )
    return imported[0] if imported and not plain else "st"


def _root(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _element_calls(tree: ast.Module) -> list[ast.Call]:
    named = aliases(tree)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in toolbox.ELEMENTS
        and (node.func.attr in WIDGETS or _root(node.func.value) in named)
        and node.end_lineno is not None
    ]
    return sorted(calls, key=lambda node: (node.lineno, node.col_offset))


def _targets(tree: ast.Module) -> dict[int, str]:
    """The name each call's value is given directly (`region = st.selectbox(...)`), by the call's id."""
    found: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            found[id(node.value)] = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            found[id(node.value)] = node.target.id
    return found


def _widget(src: _Source, call: ast.Call, index: int, auto: int | None, target: str | None) -> Widget:
    name = call.func.attr  # type: ignore[attr-defined]
    element = toolbox.ELEMENTS[name]
    arguments: dict[str, Value] = {}
    positional: list[str] = []
    spread = any(isinstance(a, ast.Starred) for a in call.args)
    for at, arg in enumerate(call.args):
        if isinstance(arg, ast.Starred):
            break
        named = element.positional[at] if at < len(element.positional) else f"argument {at + 1}"
        arguments[named] = read_value(src, arg)
        positional.append(named)
    for kw in call.keywords:
        if kw.arg is None:
            spread = True
        else:
            arguments[kw.arg] = read_value(src, kw.value)
    key = arguments.get("key")
    return Widget(
        index,
        name,
        call.lineno,
        target,
        name in WIDGETS,
        str(key.value) if key is not None and key.kind == "literal" and isinstance(key.value, str) else None,
        auto,
        arguments,
        tuple(positional),
        spread,
        element.default,
        element.event,
    )


def _cache_of(src: _Source, fn: ast.FunctionDef) -> tuple[ast.expr | None, str | None, dict[str, Value]]:
    for decorator in fn.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr in CACHES.values():
            kind = "data" if target.attr == "cache_data" else "resource"
            settings = (
                {kw.arg: read_value(src, kw.value) for kw in decorator.keywords if kw.arg}
                if isinstance(decorator, ast.Call)
                else {}
            )
            return decorator, kind, settings
    return None, None, {}


@dataclass(frozen=True)
class CellCode:
    widgets: tuple[Widget, ...] = ()
    functions: tuple[Function, ...] = ()
    variables: tuple[str, ...] = ()  # the variables of this computer it reads
    calls: tuple[str, ...] = ()  # the plain names it calls (a function another cell makes)
    problem: str | None = None


def state_reads(code: str) -> list[str]:
    """The session state keys a cell reads by name: st.session_state["k"], st.session_state.k,
    st.session_state.get("k") (a binding to a key reads it so). In order, each once."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    def is_state(node: ast.AST) -> bool:
        return isinstance(node, ast.Attribute) and node.attr == "session_state"

    found: list[str] = []
    for node in ast.walk(tree):
        key: str | None = None
        if isinstance(node, ast.Subscript) and is_state(node.value):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                key = node.slice.value
        elif (
            isinstance(node, ast.Attribute)
            and is_state(node.value)
            and node.attr not in ("get", "keys", "items")
        ):
            key = node.attr
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and is_state(node.func.value)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            key = node.args[0].value
        if key is not None and key not in found:
            found.append(key)
    return found


def read(code: str) -> CellCode:
    """What the property pane shows of a cell's code. A cell that is not whole Python has nothing to show
    but why."""
    try:
        tree = _parse(code)
    except CodeError as error:
        return CellCode(problem=str(error))
    src = _Source(code)
    targets = _targets(tree)
    widgets: list[Widget] = []
    auto = 0
    for index, call in enumerate(_element_calls(tree)):
        number: int | None = None
        keyless = not any(k.arg == "key" or k.arg is None for k in call.keywords)
        if call.func.attr in WIDGETS and keyless:  # type: ignore[attr-defined]
            auto += 1  # as the page numbers them (streamlit_cells.keyed)
            number = auto
        widgets.append(_widget(src, call, index, number, targets.get(id(call))))
    functions = [
        Function(node.name, node.lineno, *_cache_of(src, node)[1:])
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]
    found: list[tuple[int, int, str]] = []
    calls: list[str] = []
    for node in ast.walk(tree):
        place = (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))
        named = _environ_name(node)
        if named:
            found.append((*place, named))
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found += [(*place, name) for name in _VARIABLE.findall(node.value)]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.append(node.func.id)
    variables = [name for _, _, name in sorted(found)]
    return CellCode(
        tuple(widgets), tuple(functions), tuple(dict.fromkeys(variables)), tuple(dict.fromkeys(calls))
    )


# ===== a plain value as Python =====


def _quoted(text: str, quote: str = '"') -> str:
    out = []
    for ch in text:
        if ch == "\\" or ch == quote:
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return quote + "".join(out) + quote


def _quote_of(like: str) -> str:
    """The quote a text already there is written with (so its neighbour looks the same)."""
    found = re.match(r"^[A-Za-z]*(['\"])", like)
    return found.group(1) if found and not like.lstrip("rRbBuUfF").startswith(("'''", '"""')) else '"'


def literal(value: Any, like: Value | None = None, quote: str | None = None) -> str:
    """A plain value (as JSON gives it) as Python. `like`: what stands there now: a text keeps its quotes,
    a tuple stays a tuple, a date stays a date."""
    if not _plain(value):
        raise CodeError(
            "A property takes a plain value: text, a number, true or false, nothing, or a list of those."
        )
    q = quote or (_quote_of(like.source) if like is not None and like.kind == "literal" else '"')
    if isinstance(value, str):
        if len(value) > MAX_TEXT:
            raise CodeError(f"A property's text is at most {MAX_TEXT} characters.")
        if like is not None and like.form == "date" and "(" in like.source:
            try:
                day = datetime.date.fromisoformat(value)
            except ValueError:
                raise CodeError("A date is written 2026-01-31.") from None
            return f"{like.source.split('(', 1)[0]}({day.year}, {day.month}, {day.day})"
        return _quoted(value, q)
    if value is None or isinstance(value, bool | int | float):
        return repr(value)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_quoted(k, q)}: {literal(v, quote=q)}" for k, v in value.items()) + "}"
    items = [literal(v, quote=q) for v in value]
    if like is not None and like.form == "tuple":
        return "(" + ", ".join(items) + ("," if len(items) == 1 else "") + ")"
    return "[" + ", ".join(items) + "]"


# ===== a call's argument: set, added, taken away =====


@dataclass(frozen=True)
class _Item:
    name: str | None
    start: int
    end: int
    value: ast.AST
    positional: bool


def _items(src: _Source, call: ast.Call, positional: tuple[str, ...] = ()) -> list[_Item]:
    found: list[_Item] = []
    for at, arg in enumerate(call.args):
        named = None if isinstance(arg, ast.Starred) or at >= len(positional) else positional[at]
        found.append(_Item(named, *src.span(arg), arg, True))
    for kw in call.keywords:
        start = src.at(kw.lineno, kw.col_offset)
        found.append(_Item(kw.arg, start, src.span(kw.value)[1], kw.value, False))
    return sorted(found, key=lambda item: item.start)


def _quiet(text: str) -> str:
    return re.sub(r"#[^\n]*", "", text)


def _set(
    src: _Source, call: ast.Call, name: str, text: str | None, positional: tuple[str, ...] = ()
) -> list[Edit]:
    """The edits that give a call's argument `text` (None: take the argument away)."""
    code = src.code
    items = _items(src, call, positional)
    close = src.span(call)[1] - 1
    at = next((i for i, item in enumerate(items) if item.name == name), None)
    if at is not None:
        item = items[at]
        if text is not None:
            return [Edit(*src.span(item.value), text)]
        if item.positional:
            raise NotPlain(f"{name} is given by its place in the call: take it out in its cell.")
        line_start, line_end = src.line_start(item.start), src.line_end(item.end)
        tail = code[item.end : line_end]
        opened = src.span(call.func)[1]
        if (
            not code[line_start : item.start].strip()
            and re.fullmatch(r"\s*,?\s*(#.*)?", tail)
            and line_start > opened
            and line_end < close
        ):
            return [Edit(line_start, line_end + 1, "")]  # its own lines, whole
        if at + 1 < len(items):
            return [Edit(item.start, items[at + 1].start, "")]
        if at > 0:
            # The last one: its own comma goes (the space before a trailing comma with it).
            trailing = re.match(r"[ \t]*(?=,)", code[item.end : close])
            return [Edit(items[at - 1].end, item.end + (trailing.end() if trailing else 0), "")]
        comma = re.match(r"\s*,", code[item.end : close])
        return [Edit(item.start, item.end + (comma.end() if comma else 0), "")]
    if text is None:
        return []
    said = f"{name}={text}"
    if not items:
        return [Edit(close, close, said)]
    last = items[-1]
    between = code[last.end : close]
    has_comma = "," in _quiet(between)
    if "\n" in between:
        # The closing bracket is on a line of its own: the argument gets a line of its own above it.
        line = src.line_start(close)
        indent = re.match(r"[ \t]*", code[src.line_start(last.start) :])
        edits = [] if has_comma else [Edit(last.end, last.end, ",")]
        return [*edits, Edit(line, line, f"{indent.group() if indent else ''}{said},\n")]
    if has_comma:
        return [Edit(close, close, ("" if between.endswith(" ") else " ") + said)]
    return [Edit(last.end, last.end, f", {said}")]


def _call(code: str, index: int) -> tuple[_Source, ast.Module, ast.Call, Widget]:
    tree = _parse(code)
    calls = _element_calls(tree)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(calls):
        raise CodeError(
            f"The cell has no Streamlit element {index}: it has {len(calls)}, numbered from 0."
            if calls
            else "The cell calls no Streamlit element."
        )
    src = _Source(code)
    return src, tree, calls[index], _widget(src, calls[index], index, None, None)


def _made(code: str, edits: list[Edit], line: int | None = None, handler: str | None = None) -> Change:
    """The change these edits make: exactly them, nothing else."""
    return _change(code, apply(code, edits), line, handler, edits)


def _check_name(name: Any) -> str:
    if not isinstance(name, str) or not _NAME.match(name) or keyword.iskeyword(name):
        raise CodeError("A property is named as Streamlit names it: label, value, options, key...")
    return name


def set_argument(code: str, index: int, name: str, value: Any) -> Change:
    """A widget's property given a plain value: only its value's characters change (or `, name=value` is
    added before the call's closing bracket). A property that is code now is not written over."""
    name = _check_name(name)
    src, _, call, widget = _call(code, index)
    now = widget.arguments.get(name)
    if now is not None and now.kind != "literal":
        raise NotPlain(_not_plain(name, now))
    text = literal(value, now)
    if now is not None and now.source == text:
        return Change(code, ())
    return _made(code, _set(src, call, name, text, widget.by_position))


def _not_plain(name: str, now: Value) -> str:
    what = {
        "name": f"is bound to {now.target}",
        "state": f"is bound to the session state key {now.target}",
        "variable": f"is bound to the variable {now.target}",
    }.get(now.kind, "is code, not a plain value")
    fix = "unbind it first" if now.kind != "expression" else "change it in its cell"
    return f"{name}={now.source} {what}: {fix}."


def reset_argument(code: str, index: int, name: str) -> Change:
    """A property taken out of the call (Streamlit's own default again), its comma with it."""
    name = _check_name(name)
    src, _, call, widget = _call(code, index)
    if name not in widget.arguments:
        return Change(code, ())
    return _made(code, _set(src, call, name, None, widget.by_position))


def _import_edit(src: _Source, tree: ast.Module, module: str) -> list[Edit]:
    """`import os` before the cell's first statement, when the cell does not import it."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any((a.asname or a.name) == module for a in node.names):
            return []
    at = src.at(tree.body[0].lineno, 0) if tree.body else len(src.code)
    return [Edit(at, at, f"import {module}\n")]


def bind(code: str, index: int, name: str, kind: str, target: Any) -> Change:
    """A widget's property bound (WPF's bindings): to a name (another cell's, another widget's value), a
    session state key, a variable of this computer, or a short expression. What is there may be a plain
    value or another binding; code that is neither stays."""
    name = _check_name(name)
    if kind not in BINDINGS:
        raise CodeError(f"A property binds to one of: {', '.join(BINDINGS)}.")
    if not isinstance(target, str) or not target.strip() or len(target) > MAX_EXPRESSION or "\n" in target:
        raise CodeError(f"A binding names what it reads, in one line of at most {MAX_EXPRESSION} characters.")
    target = target.strip()
    src, tree, call, widget = _call(code, index)
    now = widget.arguments.get(name)
    if now is not None and now.kind == "expression" and kind != "expression":
        raise NotPlain(_not_plain(name, now))
    extra: list[Edit] = []
    if kind == "name":
        if not _NAME.match(target) or keyword.iskeyword(target):
            raise CodeError("A name is one word of letters, digits and underscores.")
        text = target
    elif kind == "state":
        text = f"{_alias(tree)}.session_state[{_quoted(target)}]"
    elif kind == "variable":
        if not _NAME.match(target):
            raise CodeError("A variable's name is one word of letters, digits and underscores.")
        text = f"os.environ[{_quoted(target)}]"
        extra = _import_edit(src, tree, "os")
    else:
        try:
            parsed = ast.parse(target, mode="eval")
        except (SyntaxError, ValueError, RecursionError):
            raise CodeError("That is not one whole Python expression.") from None
        if isinstance(parsed.body, ast.NamedExpr | ast.Yield | ast.YieldFrom | ast.Await | ast.Lambda):
            raise CodeError("A property's expression reads values: it does not assign, wait or define.")
        text = target
    if now is not None and now.source == text:
        return Change(code, ())
    return _made(code, [*_set(src, call, name, text, widget.by_position), *extra])


# ===== events: a handler's stub =====


def _names(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
    return found


def _statement(tree: ast.Module, call: ast.Call) -> ast.stmt:
    for statement in tree.body:
        if any(node is call for node in ast.walk(statement)):
            return statement
    raise CodeError("The element is not in the cell's code.")


def add_handler(code: str, index: int, event: str | None = None, name: str | None = None) -> Change:
    """An event's handler, as Visual Studio writes one: `def on_region_change():` with nothing in it yet,
    above the statement that draws the widget, and `on_change=on_region_change` in its call. A handler
    already set is not written again: `line` is where its function is."""
    src, tree, call, widget = _call(code, index)
    event = event or widget.event
    if event not in EVENTS:
        raise CodeError(f"{widget.call} has no event to handle.")
    now = widget.arguments.get(event)
    if now is not None:
        if now.kind != "name":
            raise NotPlain(f"{event}={now.source} is code: change it in its cell.")
        found = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == now.target), None)
        return Change(code, (), found.lineno if found else None, now.target)
    base = widget.key or _targets(tree).get(id(call)) or widget.call
    base = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_").lower() or widget.call
    wanted = name or f"on_{base}_{event[3:]}"
    if not _NAME.match(wanted) or keyword.iskeyword(wanted):
        raise CodeError("A handler's name is one word of letters, digits and underscores.")
    taken = _names(tree)
    handler, n = wanted, 2
    while handler in taken:
        handler = f"{wanted}_{n}"
        n += 1
    statement = _statement(tree, call)
    first = min([statement.lineno, *(d.lineno for d in getattr(statement, "decorator_list", []))])
    at = src.at(first, 0)
    stub = Edit(at, at, f"def {handler}():\n    pass\n\n\n")
    return _made(code, [stub, *_set(src, call, event, handler, widget.by_position)], first, handler)


# ===== cache: a function's decorator =====


def _cache_value(name: str, value: Any, kind: str) -> Any:
    if name == "ttl":
        ok = (isinstance(value, int | float) and not isinstance(value, bool) and value >= 0) or (
            isinstance(value, str) and 0 < len(value) <= 40
        )
        if not ok:
            raise CodeError('ttl is a number of seconds, or words like "1h" or "30m".')
    elif name == "max_entries":
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise CodeError("max_entries is a whole number from 1.")
    elif name == "show_spinner":
        if not isinstance(value, bool | str):
            raise CodeError("show_spinner is true, false, or the words to show.")
    elif name == "persist":
        if kind != "data":
            raise CodeError("Only st.cache_data can persist to disk.")
        if value not in ("disk", True, False):
            raise CodeError('persist is "disk" (or true), or false.')
    else:
        raise CodeError(f"A cache has no setting called {name!r}. Its settings: {', '.join(CACHE_SETTINGS)}.")
    return value


def set_cache(code: str, function: str, kind: Any, settings: Any = None) -> Change:
    """A function's cache. `kind`: "data" (st.cache_data), "resource" (st.cache_resource) or None (not
    cached: the decorator's line goes). `settings`: {"ttl", "max_entries", "show_spinner", "persist"}, each a
    plain value, or None to take it out. Only the decorator's characters change."""
    if kind is not None and kind not in CACHES:
        raise CodeError('A cache is "data" (st.cache_data), "resource" (st.cache_resource), or null (none).')
    if settings is not None and not isinstance(settings, dict):
        raise CodeError('The cache\'s settings are {"ttl": 600, "max_entries": 100, "show_spinner": false}.')
    wanted = dict(settings or {})
    after = code
    # One step at a time, each against the text as it then stands: the kind first, then each setting.
    for step in ("kind", *wanted):
        tree = _parse(after)
        src = _Source(after)
        fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function), None)
        if fn is None:
            raise CodeError(f"The cell has no function called {function}.")
        decorator, now, held = _cache_of(src, fn)
        if step == "kind":
            if kind is None:
                if decorator is not None:
                    start = src.line_start(src.span(decorator)[0])
                    after = apply(after, [Edit(start, src.line_end(src.span(decorator)[1]) + 1, "")])
                break
            if decorator is None:
                first = min([fn.lineno, *(d.lineno for d in fn.decorator_list)])
                at = src.at(first, 0)
                indent = re.match(r"[ \t]*", after[at:])
                line = f"{indent.group() if indent else ''}@{_alias(tree)}.{CACHES[kind]}\n"
                after = apply(after, [Edit(at, at, line)])
            elif now != kind:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                end = src.span(target)[1]
                edits = [Edit(end - len(CACHES[now or "data"]), end, CACHES[kind])]
                if kind == "resource" and "persist" in held and isinstance(decorator, ast.Call):
                    edits += _set(src, decorator, "persist", None)
                after = apply(after, edits)
            continue
        if decorator is None or now is None:
            break
        existing = held.get(step)
        if existing is not None and existing.kind != "literal":
            raise NotPlain(f"{step}={existing.source} is code, not a plain value: change it in its cell.")
        value = wanted[step]
        text = None if value is None else literal(_cache_value(step, value, now), existing)
        if step not in CACHE_SETTINGS:
            _cache_value(step, value, now)
        if isinstance(decorator, ast.Call):
            edits = _set(src, decorator, step, text)
            after = apply(after, edits)
            # `@st.cache_data()` with nothing left in it is `@st.cache_data`.
            again = _Source(after)
            fn2 = next(n for n in _parse(after).body if isinstance(n, ast.FunctionDef) and n.name == function)
            dec2 = _cache_of(again, fn2)[0]
            if isinstance(dec2, ast.Call) and not dec2.args and not dec2.keywords:
                after = apply(after, [Edit(again.span(dec2.func)[1], again.span(dec2)[1], "")])
        elif text is not None:
            end = src.span(decorator)[1]
            after = apply(after, [Edit(end, end, f"({step}={text})")])
    return _change(code, after) if after != code else Change(code, ())
