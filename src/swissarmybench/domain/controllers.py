"""Controllers (docs/ideas.md, "After the beta: controllers", 2026-11-15): a Streamlit cell that drives
others, its contract, the check a canvas page gets, and "Test this page".

A **contract** is the cell's header line that says what it makes, with types and defaults, read by
Python's own parser (the line is Python: annotated names, `;` between them):

    # Region filter
    # Makes: region: str = "All"; by_region: table = orders
    # Role: filter

  makes     each name the cell makes; a type of TYPES (or none), and a default. A default is a plain
            value (a text, a number, True, a list, a date as "2026-01-31"), or for a table the name of
            another table (`orders`: every row). "Makes: nothing" says it makes nothing; the starter
            pieces' plain "Makes: by_region" lines are contracts of names only
  role      filter (it makes what its widgets pick), action (a button with a callback), view (it only
            shows). Said by a `# Role:` line, else read from the code
  default   a block whose name's maker is NOT on the page reads the default (the page writes
            `region = "All"`) and the canvas says so quietly; without a default the page says the maker
            is missing
  check     a page's contracts against its blocks: the defaults used, a contract its code does not
            keep, a name made twice, and the blocks that need each other (a cycle), named

**Test this page** runs the page under Streamlit's own test runner (AppTest), in the app's Python: as it
opens, then each controller's values one at a time (a selectbox's options, a slider's ends, a toggle
both ways, a text that matches nothing, a click), and each query parameter it reads set to nothing and
to a value no option has. Every block records its own error (the page is written with `record`), so a
failure lands on the block that failed. `RUNNER` is the script; `read_results` turns its answer into
each block's failures.

The small API the Properties panel shows (the wb-modes branch): `describe(code).to_json()`, also on each
canvas block as `controller`: {"role", "makes": [{"name", "type", "default", "declared"}], "widgets",
"params", "problems"}.

Standard library only, no I/O.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from swissarmybench.domain import streamlit_cells as cells
from swissarmybench.domain import thin_cells
from swissarmybench.domain.streamlit_cells import Fallback, Key

TYPES: tuple[str, ...] = ("str", "int", "float", "bool", "date", "list", "table", "any")
ROLES: tuple[str, ...] = ("filter", "action", "view")
BUTTONS: frozenset[str] = frozenset({"button", "form_submit_button"})
# The widgets a test tries values on (the others it leaves as they open: a file, a camera, a chat box).
TRIED: frozenset[str] = frozenset(
    {
        "selectbox",
        "radio",
        "select_slider",
        "multiselect",
        "slider",
        "toggle",
        "checkbox",
        "number_input",
        "text_input",
        "text_area",
        "date_input",
        "pills",
        "segmented_control",
        "button",
        "form_submit_button",
    }
)
MAX_VALUES: int = 6  # the values tried for one widget (a selectbox's first options)
MAX_SHOWN: int = 3  # the failures a block shows
TEST_SECONDS: int = 150  # a test's whole budget; what is left untried is said
RUN_SECONDS: int = 30  # one run of the page
RECORD_KEY: str = cells.RECORD  # where a test page's blocks write their errors (st.session_state)
ANSWER: str = "@@swissarmybench-test@@"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEADER_LINE = re.compile(r"^#\s*(makes|role)\s*:\s*(.*?)\s*$", re.IGNORECASE)
NOTHING = "nothing"


# ===== a cell's contract =====


@dataclass(frozen=True)
class Made:
    """A name a cell makes: its type (one of TYPES; "" when none is said) and its default, as Python."""

    name: str
    type: str = ""
    default: str | None = None
    declared: bool = True  # on the Makes line (else only found in the code)

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type, "default": self.default, "declared": self.declared}


@dataclass(frozen=True)
class Widget:
    """A widget call in a cell: its kind (selectbox), key and label when they are plain text, whether it
    sits in a form, and whether it has a callback (on_click, on_change)."""

    kind: str
    key: str | None
    label: str | None
    form: bool = False
    callback: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "label": self.label,
            "form": self.form,
            "callback": self.callback,
        }


@dataclass(frozen=True)
class Controller:
    """What the Properties panel shows of a cell: its role, what it makes (with types and defaults),
    its widgets, the query parameters it reads, and what is wrong with its contract."""

    role: str = ""  # filter, action, view, or "" (it calls no Streamlit: model work)
    makes: tuple[Made, ...] = ()
    widgets: tuple[Widget, ...] = ()
    params: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
    declared: bool = False  # it has a Makes line

    def default(self, name: str) -> Made | None:
        return next((m for m in self.makes if m.name == name and m.default is not None), None)

    def to_json(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "makes": [m.to_json() for m in self.makes],
            "widgets": [w.to_json() for w in self.widgets],
            "params": list(self.params),
            "problems": list(self.problems),
            "declared": self.declared,
        }


def header(code: str) -> list[tuple[int, str]]:
    """The cell's header: its comment lines before the first line of code, as (line, text)."""
    found: list[tuple[int, str]] = []
    for number, line in enumerate(cells.body(code).split("\n"), start=1):
        if not line.strip():
            continue
        if not line.lstrip().startswith("#"):
            break
        found.append((number, line.strip()))
    return found


def _said(code: str, word: str) -> str | None:
    for _, line in header(code):
        hit = _HEADER_LINE.match(line)
        if hit and hit.group(1).lower() == word:
            return hit.group(2)
    return None


def _literal_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "date" if _DATE.match(value) else "str"
    if isinstance(value, list | tuple):
        return "list"
    return "any"


_FITS: dict[str, tuple[str, ...]] = {
    "str": ("str", "date"),
    "int": ("int",),
    "float": ("float", "int"),
    "bool": ("bool",),
    "date": ("date",),
    "list": ("list",),
}


def _declaration(node: ast.stmt, said: str) -> tuple[list[Made], str | None]:
    """One part of a Makes line: a name, `name: type`, `name = default` or `name: type = default`."""
    words = ast.get_source_segment(said, node) or ""
    if isinstance(node, ast.Expr):
        value = node.value
        names = value.elts if isinstance(value, ast.Tuple) else [value]
        if all(isinstance(n, ast.Name) for n in names):
            return [Made(n.id) for n in names if isinstance(n, ast.Name)], None
        return [], f"{words} is not a name: the line is `name: type = default`, a `;` between."
    target: ast.expr
    annotation: ast.expr | None = None
    if isinstance(node, ast.AnnAssign):
        target, annotation, value_node = node.target, node.annotation, node.value
    elif isinstance(node, ast.Assign) and len(node.targets) == 1:
        target, value_node = node.targets[0], node.value
    else:
        return [], f"{words}: the line is `name: type = default`, a `;` between."
    if not isinstance(target, ast.Name):
        return [], f'{words}: one name at a time (`a: str = "x"; b: int = 1`).'
    name = target.id
    kind = ""
    if annotation is not None:
        base = annotation.value if isinstance(annotation, ast.Subscript) else annotation
        kind = base.id if isinstance(base, ast.Name) else ""
        if kind not in TYPES:
            return [Made(name)], f"{name}'s type is one of {', '.join(TYPES)}."
    if value_node is None:
        return [Made(name, kind)], None
    if isinstance(value_node, ast.Name):
        if kind not in ("", "table", "any"):
            return [Made(name, kind)], f"{name}'s default is a plain value: only a table's is a name."
        return [Made(name, kind or "table", value_node.id)], None
    try:
        value = ast.literal_eval(value_node)
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return [Made(name, kind)], f"{name}'s default is a plain value (a text, a number, True, a list)."
    found = _literal_type(value)
    if kind == "table":
        return [Made(name, kind)], f"{name} is a table: its default is a table's name (orders)."
    if kind and kind != "any" and found not in _FITS[kind]:
        return [Made(name, kind)], f"{name}'s default {words.split('=', 1)[1].strip()} is not a {kind}."
    return [Made(name, kind or found, _default_code(kind or found, value))], None


def _default_code(kind: str, value: Any) -> str:
    """A default as the page writes it: Python's own text for the value; a date as a date."""
    if kind == "date" and isinstance(value, str):
        year, month, day = (int(part) for part in value.split("-"))
        return f"_sab_date({year}, {month}, {day})"
    if kind == "float" and isinstance(value, int) and not isinstance(value, bool):
        return repr(float(value))
    return repr(value)


def _makes_line(said: str) -> tuple[list[Made], list[str]]:
    text = said.strip()
    if not text or text.lower().startswith(NOTHING):
        return [], []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # A plain line with words after it: "Makes: by_region (the rows its pick leaves)".
        plain = re.sub(r"\s+\(.*\)$", "", text)
        try:
            tree = ast.parse(plain)
            text = plain
        except SyntaxError:
            return [], [f"The Makes line is `name: type = default`, a `;` between: {said.strip()}"]
    made: list[Made] = []
    problems: list[str] = []
    for node in tree.body:
        found, problem = _declaration(node, text)
        made += [m for m in found if m.name not in {d.name for d in made}]
        if problem:
            problems.append(problem)
    return made, problems


def _chain(node: ast.expr) -> list[str]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.insert(0, node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.insert(0, node.id)
    return parts


def _text(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def widgets(code: str) -> list[Widget]:
    """The widget calls in the code, in the order they are written (`keyed` code: each has its key)."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return []
    in_form: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With | ast.AsyncWith):
            opens = [i.context_expr for i in node.items]
            if any(isinstance(c, ast.Call) and _chain(c.func)[-1:] == ["form"] for c in opens):
                for inner in node.body:
                    in_form.update(id(n) for n in ast.walk(inner))
    found: list[tuple[int, int, Widget]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        kind = node.func.attr
        if kind not in cells.WIDGETS and kind != "form_submit_button":
            continue
        keywords = {k.arg: k.value for k in node.keywords if k.arg}
        label = _text(keywords.get("label") or (node.args[0] if node.args else None))
        callback = any(k in keywords for k in ("on_click", "on_change", "on_submit"))
        widget = Widget(kind, _text(keywords.get("key")), label, id(node) in in_form, callback)
        found.append((node.lineno, node.col_offset, widget))
    return [w for _, _, w in sorted(found, key=lambda item: (item[0], item[1]))]


def params(code: str) -> list[str]:
    """The query parameters the code reads by name: `st.query_params.get("region")`,
    `st.query_params["region"]`, `"region" in st.query_params`."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return []
    found: list[str] = []

    def is_params(node: ast.expr) -> bool:
        return _chain(node)[-1:] == ["query_params"]

    for node in ast.walk(tree):
        name: str | None = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and is_params(node.func.value):
            if node.func.attr in ("get", "get_all") and node.args:
                name = _text(node.args[0])
        elif isinstance(node, ast.Subscript) and is_params(node.value) and isinstance(node.ctx, ast.Load):
            name = _text(node.slice)
        elif isinstance(node, ast.Compare) and any(is_params(c) for c in node.comparators):
            name = _text(node.left)
        if name and name not in found:
            found.append(name)
    return found


@lru_cache(maxsize=2048)
def describe(code: str) -> Controller:
    """A cell as a controller: its contract (the header's Makes and Role lines), what it makes, its
    widgets and query parameters, and its role."""
    text = cells.body(code)
    found = cells.facts(code)
    shown = cells.shown_makes(found)
    said = _said(code, "makes")
    declared, problems = _makes_line(said) if said is not None else ([], [])
    for made in declared:
        if made.name not in found.makes and not found.problem:
            problems.append(f"The Makes line names {made.name}, which the cell never makes.")
    listed = {m.name for m in declared}
    makes = [*declared, *(Made(name, declared=False) for name in shown if name not in listed)]
    seen = widgets(text)
    role = (_said(code, "role") or "").strip().lower()
    if role and role not in ROLES:
        problems.append(f"The Role line is one of {', '.join(ROLES)}.")
        role = ""
    if not role:
        if any(w.kind in BUTTONS and w.callback for w in seen):
            role = "action"
        elif shown and any(w.kind not in BUTTONS for w in seen):
            role = "filter"
        elif cells.uses_streamlit(text) or seen:
            role = "view"
    return Controller(role, tuple(makes), tuple(seen), tuple(params(text)), tuple(problems), said is not None)


# ===== a page's check: its defaults, a name made twice, the blocks that need each other =====


def fallbacks(
    here: Iterable[Key], codes: Mapping[Key, str], titles: Mapping[Key, str], where: Mapping[Key, str]
) -> dict[str, Fallback]:
    """The defaults a page can use: each name a linked cell that is NOT on the page declares with a
    default, and the words for that cell ("Region filter, sales.ipynb @cell3"). The first such cell in
    the files' order gives it; a name a block on the page makes is the page's own."""
    on_page = set(here)
    made_here = {n for key in on_page if key in codes for n in cells.facts(codes[key]).makes}
    out: dict[str, Fallback] = {}
    for key, code in codes.items():
        if key in on_page:
            continue
        for made in describe(code).makes:
            if made.default is None or made.name in made_here or made.name in out:
                continue
            table = made.default if made.type in ("table", "any") and made.default.isidentifier() else None
            maker = titles.get(key) or f"cell {key[1]}"
            out[made.name] = Fallback(made.default, f"{maker}, {where.get(key, f'cell {key[1]}')}", table)
    return out


@dataclass(frozen=True)
class BlockCheck:
    id: str
    defaults: tuple[tuple[str, str, str], ...] = ()  # (name, its default, the maker that is not here)
    problems: tuple[str, ...] = ()  # its contract against its code

    def to_json(self) -> dict[str, Any]:
        return {
            "block": self.id,
            "defaults": [{"name": n, "value": v, "maker": m} for n, v, m in self.defaults],
            "problems": list(self.problems),
        }


@dataclass(frozen=True)
class PageCheck:
    blocks: tuple[BlockCheck, ...] = ()
    cycles: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = ()  # (the blocks, the names)
    twice: tuple[tuple[str, tuple[str, ...]], ...] = ()  # a name two blocks make, and the blocks

    def block(self, block_id: str) -> BlockCheck:
        return next((b for b in self.blocks if b.id == block_id), BlockCheck(block_id))

    def to_json(self) -> dict[str, Any]:
        return {
            "blocks": [b.to_json() for b in self.blocks if b.defaults or b.problems],
            "cycles": [{"blocks": list(b), "names": list(n)} for b, n in self.cycles],
            "twice": [{"name": n, "blocks": list(b)} for n, b in self.twice],
        }


def check_page(
    placed: Sequence[tuple[str, str]], made: cells.PageCode, fallen: Mapping[str, Fallback]
) -> PageCheck:
    """A page's check. `placed`: each block's id and its cell's code as the page runs it (a block whose
    cell is gone is left out); `made`: the page as written (its defaults and its order); `fallen`: the
    defaults it could use (`fallbacks`)."""
    found = {block_id: cells.facts(code) for block_id, code in placed}
    ordered = cells.run_order(list(found.items()))
    blocks: list[BlockCheck] = []
    used = {(block_id, name) for block_id, name in made.defaulted}
    for block_id, code in placed:
        defaults = tuple(
            (name, fallen[name].code, fallen[name].maker)
            for b, name in sorted(used)
            if b == block_id and name in fallen
        )
        blocks.append(BlockCheck(block_id, defaults, describe(code).problems))
    cycles: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    if ordered.cycle:
        names = tuple(sorted({n for key, n, _ in ordered.links if key in ordered.cycle}))
        cycles.append((ordered.cycle, names))
    makers: dict[str, list[str]] = {}
    for block_id, facts in found.items():
        for name in cells.shown_makes(facts):
            makers.setdefault(name, []).append(block_id)
    twice = tuple((name, tuple(ids)) for name, ids in makers.items() if len(ids) > 1)
    return PageCheck(tuple(blocks), tuple(cycles), twice)


@dataclass(frozen=True)
class Placed:
    """A block as the canvas's notes read it: its id, its cell's code as the page runs it (None: the
    cell is gone), its kind (code, markdown, html), the words for its cell ("Sales chart, sales.ipynb
    @cell4"), and whether the cell is in data.ipynb (the model itself: no thin-cell hint)."""

    id: str
    code: str | None
    kind: str = "code"
    words: str = ""
    model: bool = False


def test_mark(placed: Sequence[Placed], made: cells.PageCode) -> str:
    """What a test's result stands for: the blocks' code, the tables and the defaults the page reads
    (not where the blocks sit: moving one leaves the result as it was)."""
    said = json.dumps([[(p.id, p.code) for p in placed], made.tables, made.defaulted])
    return hashlib.sha256(said.encode("utf-8", "replace")).hexdigest()[:16]


def page_notes(
    placed: Sequence[Placed],
    made: cells.PageCode,
    fallen: Mapping[str, Fallback],
    inputs: Iterable[str],
    tested: Mapping[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """What a canvas shows of its controllers, by block and for the page: each block's controller (the
    Properties panel's), the defaults it reads, its contract's problems, a thin-cell hint (model work
    to move to data.ipynb), and the failures its last test found (`tested`: a TestResult's JSON, when
    the page is still the one tested); the page's check and its test's counts."""
    check = check_page([(p.id, p.code) for p in placed if p.code is not None], made, fallen)
    held = list(inputs)
    failures = (tested or {}).get("failures") or {}
    notes: dict[str, dict[str, Any]] = {}
    for p in placed:
        mine = check.block(p.id)
        thin = None
        if p.code is not None and p.kind == "code" and not p.model:
            thin = thin_cells.model_work(p.code, held, p.words)
        notes[p.id] = {
            "controller": describe(p.code).to_json() if p.code is not None and p.kind == "code" else None,
            "defaults": [{"name": n, "value": v, "maker": m} for n, v, m in mine.defaults],
            "contract": list(mine.problems),
            "thin": None if thin is None else {"words": thin.words, "names": list(thin.names)},
            "failures": list(failures.get(p.id, [])),
        }
    summary = None
    if tested is not None:
        keep = ("runs", "tries", "failed", "page", "untried", "stopped", "problem")
        summary = {k: tested.get(k) for k in keep}
    return notes, {"check": check.to_json(), "tested": summary}


# ===== Test this page: the plan, the runner, its answer =====


@dataclass(frozen=True)
class Tried:
    block: str  # the block whose widget it is
    name: str  # the block's name, for the words
    widget: Widget


def test_plan(blocks: Sequence[tuple[str, str, str]], page: str = "page.py") -> dict[str, Any]:
    """What the runner tries, from the page's wiring. `blocks`: each block's id, its name, and its code
    as the page writes it (keyed: each widget has its key). Widgets whose key is worked out as the page
    runs cannot be found by the runner: they are said, untried."""
    tried: list[dict[str, Any]] = []
    untried: list[str] = []
    asked: list[dict[str, Any]] = []
    for block_id, name, code in blocks:
        for widget in widgets(code):
            if widget.kind not in TRIED:
                continue
            if widget.key is None:
                untried.append(f"{name}: {widget.label or widget.kind} (its key is worked out as it runs)")
                continue
            tried.append(
                {"block": block_id, "name": name, "label": widget.label or widget.kind} | widget.to_json()
            )
        for param in params(code):
            asked.append({"block": block_id, "name": name, "param": param})
    return {
        "page": page,
        "timeout": RUN_SECONDS,
        "budget": TEST_SECONDS,
        "values": MAX_VALUES,
        "record": RECORD_KEY,
        "answer": ANSWER,
        "widgets": tried,
        "params": asked,
        "untried": untried,
    }


@dataclass
class TestResult:
    """What a test found: how many runs and tries, each block's failures (the value tried, the error),
    an error outside every block, and what was not tried."""

    runs: int = 0
    tries: int = 0
    failures: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    page: list[dict[str, str]] = field(default_factory=list)
    untried: list[str] = field(default_factory=list)
    stopped: bool = False  # the budget ran out before every value was tried
    problem: str | None = None  # the runner itself could not run

    @property
    def failed(self) -> int:
        return sum(len(v) for v in self.failures.values()) + len(self.page)

    def to_json(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "tries": self.tries,
            "failed": self.failed,
            "failures": {b: list(f) for b, f in self.failures.items()},
            "page": list(self.page),
            "untried": list(self.untried),
            "stopped": self.stopped,
            "problem": self.problem,
        }


def _short(error: Any) -> str:
    text = " ".join(str(error).split())
    return text if len(text) <= 300 else text[:299] + "…"


def read_results(output: str, plan: Mapping[str, Any], blocks: Iterable[str]) -> TestResult:
    """The runner's answer (its last line after ANSWER) as each block's failures: the first errors of
    each block (a block that fails the same way for every value says it once)."""
    known = set(blocks)
    result = TestResult(untried=list(plan.get("untried", [])))
    line = next((ln for ln in reversed(output.splitlines()) if ln.startswith(ANSWER)), None)
    if line is None:
        result.problem = "The test did not finish: " + _short(output[-600:] or "it said nothing.")
        return result
    try:
        said = json.loads(line[len(ANSWER) :])
    except ValueError:
        result.problem = "The test's answer could not be read."
        return result
    result.runs = int(said.get("runs") or 0)
    result.tries = int(said.get("tries") or 0)
    result.stopped = bool(said.get("stopped"))
    result.untried += [_short(s) for s in said.get("skipped") or []]
    for case in said.get("cases") or []:
        words = _short(case.get("case") or "")
        for block_id, error in (case.get("failures") or {}).items():
            if block_id not in known:
                continue
            held = result.failures.setdefault(block_id, [])
            if all(f["error"] != _short(error) for f in held) and len(held) < MAX_SHOWN:
                held.append({"case": words, "error": _short(error)})
        for error in case.get("page") or []:
            if len(result.page) < MAX_SHOWN and all(f["error"] != _short(error) for f in result.page):
                result.page.append({"case": words, "error": _short(error)})
    return result


# The runner, run in the app's Python as `python -I -c RUNNER <folder>`: the folder holds the page and
# plan.json. Its answer is one line: ANSWER and JSON. Streamlit's AppTest runs the page in this process,
# without a browser or a server.
RUNNER: str = r'''
import json, sys, time
from pathlib import Path

from streamlit.testing.v1 import AppTest

folder = Path(sys.argv[1])
plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
deadline = time.monotonic() + plan["budget"]
out = {"runs": 0, "tries": 0, "cases": [], "skipped": [], "stopped": False}
PICKS = {"selectbox", "radio", "select_slider", "pills", "segmented_control"}


def page():
    return AppTest.from_file(str(folder / plan["page"]), default_timeout=plan["timeout"])


def run(at, words, block=None):
    out["runs"] += 1
    try:
        at.run()
    except Exception as error:  # the run itself (a timeout)
        out["cases"].append({"case": words, "block": block, "failures": {}, "page": [repr(error)]})
        return
    found = {}
    try:
        if plan["record"] in at.session_state:
            found = dict(at.session_state[plan["record"]])
    except Exception:
        found = {}
    shown = [str(e.value) for e in at.exception]
    outside = shown[len(found):] if len(shown) > len(found) else []
    if found or outside:
        out["cases"].append({"case": words, "block": block, "failures": found, "page": outside})


def element(at, w):
    kind = "button" if w["kind"] == "form_submit_button" else w["kind"]
    return getattr(at, kind)(key=w["key"])


def options(el):
    held = getattr(el, "options", None)
    if held is None and hasattr(el, "proto"):
        held = [o.content for o in getattr(el.proto, "options", [])]
    return list(held or [])


def tries(el, w):
    """(words, how) for each value to try; `how` sets it on a fresh copy of the element."""
    kind, n = w["kind"], plan["values"]
    found = []
    if kind in PICKS:
        for i, option in enumerate(options(el)[:n]):
            if kind == "selectbox":
                found.append((repr(option), lambda e, i=i: e.select_index(i)))
            else:
                found.append((repr(option), lambda e, o=option: e.set_value(o)))
    elif kind == "multiselect":
        every = options(el)
        found = [("none", lambda e: e.set_value([]))]
        if every:
            found.append(("all", lambda e, v=every: e.set_value(list(v))))
            found.append((repr(every[0]), lambda e, v=every[0]: e.set_value([v])))
    elif kind == "slider":
        low, high, value = el.min, el.max, el.value
        if isinstance(value, (tuple, list)):
            found = [
                ("the whole range", lambda e: e.set_value((low, high))),
                ("its lowest end", lambda e: e.set_value((low, low))),
                ("its highest end", lambda e: e.set_value((high, high))),
            ]
        else:
            found = [("its lowest", lambda e: e.set_value(low)), ("its highest", lambda e: e.set_value(high))]
    elif kind in ("toggle", "checkbox"):
        found = [(repr(not el.value), lambda e, v=not el.value: e.set_value(v))]
    elif kind == "number_input":
        proto = getattr(el, "proto", None)
        ends = []
        if proto is not None and getattr(proto, "has_min", False):
            ends.append(("its lowest", proto.min))
        if proto is not None and getattr(proto, "has_max", False):
            ends.append(("its highest", proto.max))
        if not ends:
            ends = [("0", 0), ("-1", -1)]
        found = [(words, lambda e, v=v: e.set_value(v)) for words, v in ends]
    elif kind in ("text_input", "text_area"):
        found = [
            ("empty", lambda e: e.set_value("")),
            ("a text nothing matches", lambda e: e.set_value("zzzq")),
        ]
    elif kind == "date_input":
        value = el.value
        if isinstance(value, (tuple, list)) and value:
            found = [("one day", lambda e, d=value[0]: e.set_value((d, d)))]
    elif kind in ("button", "form_submit_button"):
        found = [("clicked", lambda e: e.click()), ("clicked again", lambda e: e.click())]
    return found


def submit(at, w):
    """A widget in a form takes effect with its form's submit button."""
    if not w["form"]:
        return
    for button in at.button:
        if getattr(button, "form_id", "") and button.form_id == getattr(element(at, w), "form_id", None):
            button.click()


at = page()
run(at, "As the page opens")
for w in plan["widgets"]:
    if time.monotonic() > deadline:
        out["stopped"] = True
        break
    try:
        start = element(at, w)
    except Exception:
        out["skipped"].append(f"{w['name']}: {w['label']} (not on the page as it opens)")
        continue
    kept = None if w["kind"] in ("button", "form_submit_button") else start.value
    for words, how in tries(start, w):
        if time.monotonic() > deadline:
            out["stopped"] = True
            break
        try:
            how(element(at, w))
            if w["kind"] != "form_submit_button":
                submit(at, w)
        except Exception as error:
            out["skipped"].append(f"{w['name']}: {w['label']} = {words} could not be set ({error})")
            continue
        out["tries"] += 1
        run(at, f"{w['name']}: {w['label']} = {words}", w["block"])
    if kept is not None:
        try:
            element(at, w).set_value(kept)
            submit(at, w)
            out["runs"] += 1
            at.run()
        except Exception:
            at = page()
            out["runs"] += 1
            at.run()
for p in plan["params"]:
    for words, value in (("empty", ""), ("a value no option has", "zzzq")):
        if time.monotonic() > deadline:
            out["stopped"] = True
            break
        fresh = page()
        fresh.query_params[p["param"]] = value
        out["tries"] += 1
        run(fresh, f"{p['name']}: ?{p['param']}= {words}", p["block"])
print(plan["answer"] + json.dumps(out, default=str))
'''
