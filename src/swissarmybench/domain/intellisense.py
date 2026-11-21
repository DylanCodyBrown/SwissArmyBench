"""The Workbench editors' intelligence, as rules (the owner, 2026-11-17: "make sure the code completion is
robust to suggest and explain like c# does the function and its inputs", "a basic realtime lint").

Jedi does the Python work (client/kernel_intel.py): the member list, signatures, the active parameter,
hovers. These are the rules around it:

  DOCSTRINGS   Google, NumPy and reST docstrings read for each parameter's words (the bold one's
               description), what it returns and raises (parse_docstring); the documentation panel's
               markdown (markdown_doc); a call's required arguments as tab stops (snippet)
  MAGICS       a notebook cell's IPython lines (%magic, !shell, name?) made Python of the same lines
               (to_python), so they are never syntax errors and the lines stay where they were
  QUOTED       where Jedi cannot see: the app's names inside strings, sab.connection("|"), os.environ["|"],
               secret("|"), sab.blade("|"), sab.structure("|"), a table's columns in orders["|"]
  LINT         Python's compile, then a small ast pass when neither pyflakes nor Ruff is there: undefined
               names (builtins, the kernel's, earlier cells'), unused imports, f-strings without
               placeholders, == None, a bare except; each problem with its fixes (lint)
  IMPORTS      where an import line goes, or the `from m import a` it joins (import_edit); the project's
               modules' public names (module_names)
  SQL          another database's SQL by sqlglot in its dialect; DuckDB's parser error placed
  RANKING      names in scope first, then the project's, the app's, the libraries'; recently used first
               in each group (rank)

Standard library only (and sqlglot for another database's SQL). Lines and columns are 1-based, columns
counted in characters; an end column is the one after the last character.
"""

from __future__ import annotations

import ast
import builtins
import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# ===== docstrings =====

_GOOGLE_PARAMS = (
    "args",
    "arguments",
    "parameters",
    "params",
    "keyword args",
    "keyword arguments",
    "other parameters",
)
_GOOGLE_RETURNS = ("returns", "return", "yields", "yield")
_GOOGLE_RAISES = ("raises", "raise", "exceptions")


@dataclass(frozen=True)
class DocParts:
    """A docstring taken apart: the words before its sections, each parameter's words (by name), its
    parameters' types where the docstring says them, what it returns and what it raises."""

    summary: str
    params: dict[str, str] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)
    returns: str = ""
    raises: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "params": dict(self.params),
            "types": dict(self.types),
            "returns": self.returns,
            "raises": list(self.raises),
        }


def _dedent(lines: list[str]) -> list[str]:
    indents = [len(x) - len(x.lstrip()) for x in lines if x.strip()]
    cut = min(indents) if indents else 0
    return [x[cut:] if x.strip() else "" for x in lines]


def _clean(doc: str) -> list[str]:
    lines = doc.expandtabs(4).splitlines()
    if not lines:
        return []
    # The first line is not indented in a docstring (it follows the quotes): the rest is dedented alone.
    rest = _dedent(lines[1:])
    out = [lines[0].strip(), *rest]
    while out and not out[-1].strip():
        out.pop()
    while out and not out[0].strip():
        out.pop(0)
    return out


def _joined(lines: Iterable[str]) -> str:
    """Lines as one paragraph (blank lines kept as paragraph breaks)."""
    text = "\n".join(x.strip() for x in lines)
    return re.sub(r"(?<!\n)\n(?!\n)", " ", text).strip()


def _numpy_sections(lines: list[str]) -> dict[str, list[str]] | None:
    """NumPy's sections: a title line underlined with dashes."""
    found: dict[str, list[str]] = {}
    current = "summary"
    found[current] = []
    i = 0
    seen = False
    while i < len(lines):
        if i + 1 < len(lines) and lines[i].strip() and re.fullmatch(r"\s*-{3,}\s*", lines[i + 1]):
            current = lines[i].strip().lower()
            found[current] = []
            seen = True
            i += 2
            continue
        found[current].append(lines[i])
        i += 1
    return found if seen else None


def _numpy_entries(lines: list[str]) -> list[tuple[str, str, str]]:
    """`name : type` lines, each with its indented words: (name, type, words)."""
    out: list[tuple[str, str, str]] = []
    name = kind = ""
    words: list[str] = []
    for line in lines:
        if line.strip() and not line.startswith((" ", "\t")):
            if name:
                out.append((name, kind, _joined(words)))
            head, _, kind = line.partition(":")
            name, kind, words = head.strip(), kind.strip(), []
        elif name:
            words.append(line)
    if name:
        out.append((name, kind, _joined(words)))
    return out


def _google_sections(lines: list[str]) -> dict[str, list[str]] | None:
    found: dict[str, list[str]] = {"summary": []}
    current = "summary"
    seen = False
    known = (
        *_GOOGLE_PARAMS,
        *_GOOGLE_RETURNS,
        *_GOOGLE_RAISES,
        "examples",
        "example",
        "note",
        "notes",
        "see also",
        "attributes",
        "todo",
        "warning",
        "warnings",
    )
    for line in lines:
        title = re.fullmatch(r"([A-Za-z][A-Za-z ]*):\s*", line)
        if title and title.group(1).strip().lower() in known and not line.startswith((" ", "\t")):
            current = title.group(1).strip().lower()
            found[current] = []
            seen = True
            continue
        found[current].append(line)
    return found if seen else None


def _google_entries(lines: list[str]) -> list[tuple[str, str, str]]:
    """`name (type): words` entries, continued by deeper-indented lines."""
    body = _dedent(lines)
    out: list[tuple[str, str, str]] = []
    name = kind = ""
    words: list[str] = []
    for line in body:
        entry = re.match(r"^(\*{0,2}[A-Za-z_]\w*)\s*(?:\(([^)]*)\))?\s*:\s*(.*)$", line)
        if entry and not line.startswith((" ", "\t")):
            if name:
                out.append((name, kind, _joined(words)))
            name, kind, words = entry.group(1), (entry.group(2) or "").strip(), [entry.group(3)]
        elif name:
            words.append(line)
    if name:
        out.append((name, kind, _joined(words)))
    return out


def _rest(lines: list[str]) -> DocParts | None:
    fields = [
        i
        for i, x in enumerate(lines)
        if re.match(
            r"\s*:(param|parameter|arg|argument|key|keyword|type|returns?|rtype|raises?|except|exception)\b",
            x,
        )
    ]
    if not fields:
        return None
    summary = _joined(lines[: fields[0]])
    params: dict[str, str] = {}
    types: dict[str, str] = {}
    returns = rtype = ""
    raises: list[str] = []
    entries: list[list[str]] = []
    for line in lines[fields[0] :]:
        if re.match(r"\s*:\w", line):
            entries.append([line.strip()])
        elif entries:
            entries[-1].append(line)
    for entry in entries:
        head = re.match(r":(\w+)\s*([^:]*):\s*(.*)$", entry[0])
        if not head:
            continue
        role, arg, words = head.group(1), head.group(2).strip(), _joined([head.group(3), *entry[1:]])
        if role in ("param", "parameter", "arg", "argument", "key", "keyword"):
            parts = arg.split()
            if len(parts) >= 2:
                types[parts[-1]] = " ".join(parts[:-1])
            if parts:
                params[parts[-1]] = words
        elif role == "type" and arg:
            types[arg] = words
        elif role in ("returns", "return"):
            returns = words
        elif role == "rtype":
            rtype = words
        elif role in ("raises", "raise", "except", "exception"):
            raises.append(f"{arg}: {words}" if arg else words)
    if rtype:
        returns = f"{rtype}: {returns}" if returns else rtype
    return DocParts(summary, params, types, returns, tuple(raises))


def parse_docstring(doc: str | None) -> DocParts:
    """A docstring in any of the three styles (Google's Args:, NumPy's underlined Parameters, reST's
    :param x:), or plain words (all summary)."""
    lines = _clean(doc or "")
    if not lines:
        return DocParts("")
    rest = _rest(lines)
    if rest is not None:
        return rest
    numpy = _numpy_sections(lines)
    if numpy is not None:
        params: dict[str, str] = {}
        types: dict[str, str] = {}
        for title in ("parameters", "other parameters", "keyword arguments"):
            for name, kind, words in _numpy_entries(numpy.get(title, [])):
                for one in name.split(","):
                    params[one.strip()] = words
                    if kind:
                        types[one.strip()] = kind
        returned = _numpy_entries(numpy.get("returns", numpy.get("yields", [])))
        returns = "; ".join(f"{n}: {w}" if w and k else (f"{n}: {w}" if w else n) for n, k, w in returned)
        raises = tuple(f"{n}: {w}" if w else n for n, _, w in _numpy_entries(numpy.get("raises", [])))
        return DocParts(_joined(numpy["summary"]), params, types, returns, raises)
    google = _google_sections(lines)
    if google is not None:
        params, types = {}, {}
        for title in _GOOGLE_PARAMS:
            for name, kind, words in _google_entries(google.get(title, [])):
                params[name.lstrip("*")] = words
                if kind:
                    types[name.lstrip("*")] = kind
        returns = next((_joined(_dedent(google[t])) for t in _GOOGLE_RETURNS if t in google), "")
        raised = next((google[t] for t in _GOOGLE_RAISES if t in google), [])
        raises = tuple(f"{n}: {w}" if w else n for n, _, w in _google_entries(raised))
        return DocParts(_joined(google["summary"]), params, types, returns, raises)
    return DocParts(_joined(lines))


# ===== IPython's lines in a notebook cell =====

_MAGIC = re.compile(r"^(\s*)(%%?\w|!|\?)")
_SHELL_ASSIGN = re.compile(r"^(\s*[A-Za-z_][\w.]*\s*=\s*)(!|%)")
_HELP = re.compile(r"^(\s*)([A-Za-z_][\w.]*)\s*\?\??\s*$")


def is_cell_magic(text: str) -> bool:
    """A cell whose first line is a cell magic (%%sql, %%html, %%timeit): not Python as a whole."""
    first = next((x for x in text.splitlines() if x.strip()), "")
    return first.lstrip().startswith("%%")


def to_python(text: str) -> str:
    """IPython's own lines made Python of the same lines and length or less: `%time x` and `!pip install`
    become `pass`, `files = !ls` becomes `files = []`, `df?` becomes `df`. A cell magic's body stays as it
    is except its first line (%%time's body is Python)."""
    out: list[str] = []
    for line in text.split("\n"):
        assign = _SHELL_ASSIGN.match(line)
        if assign:
            out.append(f"{assign.group(1)}[]")
            continue
        asked = _HELP.match(line)
        if asked:
            out.append(f"{asked.group(1)}{asked.group(2)}")
            continue
        magic = _MAGIC.match(line)
        if magic:
            out.append(f"{magic.group(1)}pass")
            continue
        out.append(line)
    return "\n".join(out)


# ===== the app's names inside strings =====


@dataclass(frozen=True)
class Quoted:
    """Inside a string the app knows: what it holds (connection, blade, structure, variable, column,
    dataset), the text typed so far and where that text starts (an offset), and for a column the table."""

    kind: str
    typed: str
    start: int
    table: str | None = None
    tables: tuple[str, ...] = ()  # a sandbox column's: the tables its statement names


_QUOTED = (
    (re.compile(r"\bsab\.(?:connection|sql|read)\(\s*(?:connection\s*=\s*)?[\"']([^\"'\n]*)$"), "connection"),
    (re.compile(r"\bsab\.dax\(\s*[\"']([^\"'\n]*)$"), "dataset"),
    (re.compile(r"\bsab\.blade\(\s*(?:name\s*=\s*)?[\"']([^\"'\n]*)$"), "blade"),
    (re.compile(r"\bsab\.(?:structure|structure_table)\(\s*[\"']([^\"'\n]*)$"), "structure"),
    (re.compile(r"\bos\.environ\[\s*[\"']([^\"'\n]*)$"), "variable"),
    (re.compile(r"\bos\.environ\.get\(\s*[\"']([^\"'\n]*)$"), "variable"),
    (re.compile(r"\bos\.getenv\(\s*[\"']([^\"'\n]*)$"), "variable"),
    (re.compile(r"(?<![\w.])secret\(\s*[\"']([^\"'\n]*)$"), "variable"),
    # API.py (the local sandbox API): sab_api's connection("|"), and a table after FROM in its SQL.
    (re.compile(r"(?<![\w.])connection\(\s*[\"']([^\"'\n]*)$"), "mock"),
    (
        re.compile(
            r"\.(?:execute|read_arrow)\(\s*[\"'][^\"'\n]*\b(?:FROM|JOIN|INTO|UPDATE)\s+(?:\w+\.)?(\w*)$", re.I
        ),
        "sandbox_table",
    ),
    (re.compile(r"^\s*%%sql\s+([^\s]*)$", re.M), "connection"),
    (re.compile(r"^\s*%%dax\s+([^\n]*)$", re.M), "dataset"),
)


# API.py: an SQL string a mock sends (one line or three quotes over several): the statement so far.
_SQL_OPEN = re.compile(r"\.(?:execute|executemany|read_arrow)\(\s*[rRfF]?(\"\"\"|\'\'\'|\"|\')")
_SQL_TABLE_AT = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+(?:\w+\.)?(\w*)$", re.I)
_SQL_NAMED = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+(?:\w+\.)?(\w+)", re.I)


def sql_context(text: str, offset: int) -> Quoted | None:
    """Inside an SQL string API.py sends through a mock: a table after FROM, JOIN, INTO or UPDATE
    (sandbox_table), else a column (sandbox_column, with the tables the whole statement names)."""
    before = text[max(0, offset - 4000) : offset]
    opened = None
    for found in _SQL_OPEN.finditer(before):
        opened = found
    if opened is None:
        return None
    quote = opened.group(1)
    sql = before[opened.end() :]
    if quote in sql or (len(quote) == 1 and "\n" in sql):
        return None  # that string closed: the cursor is not in it
    word = re.search(r"(\w*)$", sql)
    typed = word.group(1) if word else ""
    table = _SQL_TABLE_AT.search(sql)
    if table:
        return Quoted("sandbox_table", table.group(1), offset - len(table.group(1)))
    end = text.find(quote, offset)
    whole = sql + (text[offset:end] if end >= 0 else "")
    named = tuple(dict.fromkeys(m.group(1) for m in _SQL_NAMED.finditer(whole)))
    return Quoted("sandbox_column", typed, offset - len(typed), None, named)


def quoted_context(text: str, offset: int) -> Quoted | None:
    """The app's names the cursor's string wants, or None (a plain string, or code)."""
    sql = sql_context(text, offset)
    if sql is not None:
        return sql
    before = text[max(0, offset - 300) : offset]
    line = before[before.rfind("\n") + 1 :]
    for pattern, kind in _QUOTED:
        found = pattern.search(line)
        if found:
            return Quoted(kind, found.group(1), offset - len(found.group(1)))
    column = re.search(r"\b([A-Za-z_]\w*)\[\s*[\"']([^\"'\n]*)$", line)
    if column:
        return Quoted("column", column.group(2), offset - len(column.group(2)), column.group(1))
    return None


# ===== lint =====

BUILTINS: frozenset[str] = frozenset(dir(builtins)) | {
    "__file__",
    "__name__",
    "__doc__",
    "__builtins__",
    "__spec__",
    "__loader__",
    "__package__",
    "__path__",
    "__annotations__",
}
# Names a Workbench kernel always has (IPython's own, and the app's setup).
KERNEL_NAMES: frozenset[str] = frozenset(
    {"get_ipython", "display", "In", "Out", "exit", "quit", "sab", "sag"}
)


@dataclass(frozen=True)
class Edit:
    line: int
    col: int
    end_line: int
    end_col: int
    text: str

    def to_json(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "text": self.text,
        }


@dataclass(frozen=True)
class Fix:
    title: str
    edits: tuple[Edit, ...] = ()
    # define: a name from the Variables page (its line is the edit); import: an import line added.
    kind: str = "edit"

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "title": self.title, "edits": [e.to_json() for e in self.edits]}


@dataclass(frozen=True)
class Problem:
    line: int
    col: int
    end_line: int
    end_col: int
    message: str
    severity: str  # error, warning, hint (faded: unused), info
    code: str
    source: str = "Python"
    fixes: tuple[Fix, ...] = ()
    unnecessary: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "message": self.message,
            "severity": self.severity,
            "code": self.code,
            "source": self.source,
            "fixes": [f.to_json() for f in self.fixes],
            "unnecessary": self.unnecessary,
        }


def syntax_problem(text: str) -> Problem | None:
    """Python's own compile of the text: its first syntax error, where it points."""
    try:
        ast.parse(text)
    except SyntaxError as error:
        line = error.lineno or 1
        col = max(1, error.offset or 1)
        end_line = error.end_lineno or line
        end_col = error.end_offset or col + 1
        if (end_line, end_col) <= (line, col):
            end_line, end_col = line, col + 1
        message = error.msg[:1].upper() + error.msg[1:] if error.msg else "Invalid syntax"
        return Problem(line, col, end_line, end_col, message, "error", "E999", "Python")
    return None


def _pos(node: ast.AST) -> tuple[int, int, int, int]:
    line = getattr(node, "lineno", 1)
    col = getattr(node, "col_offset", 0) + 1
    end_line = getattr(node, "end_lineno", None) or line
    end_col = (getattr(node, "end_col_offset", None) or col) + 1
    return line, col, end_line, end_col


def _bound(tree: ast.AST) -> set[str]:
    """Every name the code binds anywhere (assignments, imports, defs, parameters, loops, with, except,
    comprehensions, globals, match captures): a small pass, not pyflakes's scopes."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            out.add(node.id)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            out.add(node.name)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
        elif isinstance(node, ast.alias):
            out.add(node.asname or node.name.split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            out.add(node.name)
        elif isinstance(node, ast.Global | ast.Nonlocal):
            out.update(node.names)
        elif isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
            out.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            out.add(node.rest)
    return out


def _import_fix(lines: list[str], statement: ast.Import | ast.ImportFrom, alias: ast.alias, name: str) -> Fix:
    """Remove an unused import: the whole statement when it imports one name, else the name."""
    if len(statement.names) == 1:
        start, end = statement.lineno, statement.end_lineno or statement.lineno
        return Fix(f"Remove the unused import of `{name}`", (Edit(start, 1, end + 1, 1, ""),))
    line, col, _, end_col = _pos(alias)
    text = lines[line - 1] if line - 1 < len(lines) else ""
    after = re.match(r"\s*,\s*", text[end_col - 1 :])
    if after:
        return Fix(f"Remove `{name}` from the import", (Edit(line, col, line, end_col + after.end(), ""),))
    before = re.search(r",\s*$", text[: col - 1])
    start = before.start() + 1 if before else col
    return Fix(f"Remove `{name}` from the import", (Edit(line, start, line, end_col, ""),))


# Common modules by the name code calls them, for "Add the import" (pd: pandas).
COMMON_IMPORTS: dict[str, str] = {
    "pd": "import pandas as pd",
    "np": "import numpy as np",
    "plt": "import matplotlib.pyplot as plt",
    "px": "import plotly.express as px",
    "alt": "import altair as alt",
    "st": "import streamlit as st",
    "pl": "import polars as pl",
    "pa": "import pyarrow as pa",
    "sab": "import swissarmybench as sab",
    "Path": "from pathlib import Path",
    "date": "from datetime import date",
    "timedelta": "from datetime import timedelta",
    "Any": "from typing import Any",
    "dataclass": "from dataclasses import dataclass",
}
_STDLIB = frozenset(
    {
        "os",
        "re",
        "sys",
        "json",
        "math",
        "csv",
        "time",
        "random",
        "statistics",
        "itertools",
        "functools",
        "collections",
        "pathlib",
        "typing",
        "decimal",
        "logging",
        "shutil",
        "glob",
        "uuid",
        "hashlib",
        "base64",
        "io",
        "textwrap",
        "string",
        "copy",
        "datetime",
        "zipfile",
        "tempfile",
        "urllib",
        "calendar",
        "operator",
        "dataclasses",
        "enum",
        "contextlib",
        "asyncio",
        "sqlite3",
        "secrets",
        "inspect",
        "warnings",
    }
)


def prepare(text: str, notebook: bool) -> str | None:
    """The text Python checks: a notebook cell's IPython lines made Python; None for a cell magic's cell
    (%%sql, %%html: not Python)."""
    if notebook and is_cell_magic(text):
        return None
    return to_python(text) if notebook else text


def lint(
    text: str,
    known: Iterable[str] = (),
    used_later: Iterable[str] = (),
    importable: Mapping[str, str] | None = None,
    variables: Mapping[str, str] | None = None,
    notebook: bool = False,
    names: bool = True,
) -> list[Problem]:
    """Python's compile, then a small ast pass. `known`: names defined elsewhere (the kernel's, earlier
    cells'); `used_later`: names later cells read (an import here for them is used); `importable`: a
    name to the import line that makes it (the project's modules); `variables`: the Variables page's
    names and their source (an undefined one is defined from there); `notebook`: IPython's lines are
    allowed. `names` False: pyflakes or Ruff say the names' problems, so only the rest is checked."""
    source = prepare(text, notebook)
    if source is None:
        return []
    syntax = syntax_problem(source)
    if syntax is not None:
        return [syntax]
    tree = ast.parse(source)
    problems = _patterns(tree)
    if names:
        problems += name_problems(source, tree, known, used_later, importable, variables, notebook)
    return sorted(problems, key=lambda p: (p.line, p.col))


def name_problems(
    source: str,
    tree: ast.Module,
    known: Iterable[str],
    used_later: Iterable[str],
    importable: Mapping[str, str] | None,
    variables: Mapping[str, str] | None,
    notebook: bool,
) -> list[Problem]:
    """Undefined names (a star import makes them unknowable: said once on it) and unused imports."""
    lines = source.split("\n")
    everything = _bound(tree) | frozenset(known) | BUILTINS | (KERNEL_NAMES if notebook else frozenset())
    loaded = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    exported = {
        e.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        and isinstance(node.value, ast.List | ast.Tuple)
        for e in node.value.elts
        if isinstance(e, ast.Constant) and isinstance(e.value, str)
    }
    stars = [
        n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
    ]
    at = import_lines(source)
    out: list[Problem] = []
    for star in stars:
        line, col, end_line, end_col = _pos(star)
        words = f"from {star.module} import *: the names it makes cannot be checked"
        out.append(Problem(line, col, end_line, end_col, words, "info", "F403"))
    for node in ast.walk(tree) if not stars else ():
        if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)) or node.id in everything:
            continue
        line, col, end_line, end_col = _pos(node)
        fixes: list[Fix] = []
        have = (
            (importable or {}).get(node.id)
            or COMMON_IMPORTS.get(node.id)
            or (f"import {node.id}" if node.id in _STDLIB else None)
        )
        if have:
            fixes.append(Fix(f"Add `{have}`", (import_edit(source, have, at),), "import"))
        if variables and node.id in variables:
            fixes.append(define_fix(source, node.id, variables[node.id], at))
        for close in difflib.get_close_matches(node.id, sorted(everything), n=2, cutoff=0.8):
            fixes.append(Fix(f"Use `{close}`", (Edit(line, col, end_line, end_col, close),), "replace"))
        words = f"`{node.id}` is not defined"
        out.append(Problem(line, col, end_line, end_col, words, "error", "F821", fixes=tuple(fixes)))
    used = loaded | frozenset(used_later) | exported | _annotation_names(tree)
    for statement in tree.body:
        if not isinstance(statement, ast.Import | ast.ImportFrom):
            continue
        if isinstance(statement, ast.ImportFrom) and statement.module == "__future__":
            continue
        for alias in statement.names:
            name = alias.asname or alias.name.split(".")[0]
            if alias.name == "*" or name in used:
                continue
            line, col, end_line, end_col = _pos(alias)
            fix = _import_fix(lines, statement, alias, name)
            words = f"`{name}` is imported but not used"
            out.append(
                Problem(line, col, end_line, end_col, words, "hint", "F401", fixes=(fix,), unnecessary=True)
            )
    return out


def _annotation_names(tree: ast.AST) -> set[str]:
    """Names read in a string annotation ("pd.DataFrame"): used."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.fullmatch(r"[A-Za-z_][\w.\[\], |]*", node.value):
                out.update(re.findall(r"(?<![\w.])([A-Za-z_]\w*)", node.value))
    return out


def _patterns(tree: ast.Module) -> list[Problem]:
    """An f-string without placeholders, == None, a bare except."""
    out: list[Problem] = []
    # A placeholder's format part ({x:.1%}) is parsed as an f-string of its own: never a finding.
    specs = {id(n.format_spec) for n in ast.walk(tree) if isinstance(n, ast.FormattedValue) and n.format_spec}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.JoinedStr)
            and id(node) not in specs
            and not any(isinstance(v, ast.FormattedValue) for v in node.values)
        ):
            line, col, end_line, end_col = _pos(node)
            words = "An f-string without placeholders: the f does nothing"
            out.append(Problem(line, col, end_line, end_col, words, "warning", "F541"))
        elif isinstance(node, ast.Compare) and len(node.ops) == 1:
            op, right = node.ops[0], node.comparators[0]
            if isinstance(op, ast.Eq | ast.NotEq) and isinstance(right, ast.Constant) and right.value is None:
                line, col, end_line, end_col = _pos(node)
                word = "is None" if isinstance(op, ast.Eq) else "is not None"
                better = f"{ast.unparse(node.left)} {word}"
                edit = Edit(line, col, end_line, end_col, better)
                fixes = (Fix(f"Use `{better}`", (edit,), "replace"),) if line == end_line else ()
                words = f"Compare with None by `{word}`"
                out.append(Problem(line, col, end_line, end_col, words, "warning", "E711", fixes=fixes))
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            line, col = node.lineno, node.col_offset + 1
            fix = Fix("Catch `Exception`", (Edit(line, col, line, col + 6, "except Exception"),), "replace")
            words = "A bare `except:` catches everything, Ctrl+C too: name the error"
            out.append(Problem(line, col, line, col + 6, words, "warning", "E722", fixes=(fix,)))
    return out


def names_made(text: str, notebook: bool = True) -> set[str]:
    """The names a cell binds (for the cells after it); a %%sql cell's `-> name`."""
    source = prepare(text, notebook)
    if source is None:
        first = next((x for x in text.splitlines() if x.strip()), "")
        return set(re.findall(r"->\s*([A-Za-z_]\w*)", first)[:1])
    try:
        return _bound(ast.parse(source))
    except SyntaxError:
        return set(re.findall(r"^([A-Za-z_]\w*)\s*=", source, re.M))


def names_used(text: str, notebook: bool = True) -> set[str]:
    """Every name a cell reads (for the cells before it: their imports are used)."""
    source = prepare(text, notebook)
    if source is None:
        return set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set(re.findall(r"[A-Za-z_]\w*", source))
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


# ===== imports =====


def import_lines(text: str) -> tuple[int, int]:
    """Where the imports are: the line after the module's docstring and `from __future__` lines (the
    first place an import may go), and the last import line at the top (0 when there is none)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 1, 0
    first = 1
    last = 0
    for statement in tree.body:
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
            and first == 1
            and last == 0
        ):
            first = (statement.end_lineno or statement.lineno) + 1
            continue
        if isinstance(statement, ast.ImportFrom) and statement.module == "__future__":
            first = (statement.end_lineno or statement.lineno) + 1
            continue
        if isinstance(statement, ast.Import | ast.ImportFrom):
            last = statement.end_lineno or statement.lineno
            continue
        break
    return first, last


def import_edit(text: str, line_text: str, at: tuple[int, int] | None = None) -> Edit:
    """The edit that adds an import: a name joins an existing `from m import a, b` line of the same
    module; else the line goes after the last import at the top (or where the first may go)."""
    first, last = at or import_lines(text)
    lines = text.split("\n")
    wanted = re.match(r"^from\s+(\S+)\s+import\s+(\w+)$", line_text)
    if wanted:
        for i, line in enumerate(lines[: max(last, 0)]):
            existing = re.match(rf"^from\s+{re.escape(wanted.group(1))}\s+import\s+([\w ,]+?)\s*$", line)
            if existing:
                names = [n.strip() for n in existing.group(1).split(",")]
                if wanted.group(2) in names:
                    return Edit(i + 1, len(line) + 1, i + 1, len(line) + 1, "")
                return Edit(i + 1, len(line) + 1, i + 1, len(line) + 1, f", {wanted.group(2)}")
    where = last + 1 if last else first
    # The first import above code: a blank line between them, as isort and Ruff want it.
    apart = "\n" if not last and where - 1 < len(lines) and lines[where - 1].strip() else ""
    return Edit(where, 1, where, 1, f"{line_text}\n{apart}")


def define_fix(text: str, name: str, source: str, at: tuple[int, int] | None = None) -> Fix:
    """An undefined name that is a variable on the Variables page: read from the environment (where the
    app puts every variable's value while it runs), `import os` added when it is missing."""
    first, last = at or import_lines(text)
    has_os = re.search(r"^\s*import\s+os\b|^\s*import\s+.*,\s*os\b", text, re.M) is not None
    where = last + 1 if last else first
    line = f'{name} = os.environ["{name}"]\n'
    edits = (Edit(where, 1, where, 1, ("" if has_os else "import os\n") + line),)
    return Fix(f"Define `{name}` from the Variables page ({source})", edits, "define")


# ===== another database's SQL =====


def sql_problems(text: str, dialect: str | None) -> list[Problem]:
    """A query's syntax by sqlglot in the connection's dialect: the first error, where it points.
    `[Connection].table` (DuckDB SQL naming a connection) reads as a quoted name."""
    import sqlglot
    from sqlglot.errors import ParseError, TokenError

    if not text.strip():
        return []
    cleaned = re.sub(r"\[([^\]\n]*)\]", lambda m: '"' + m.group(1).replace('"', "'") + '"', text)
    read = {"tsql": "tsql", "mssql": "tsql", "postgresql": "postgres", "pg": "postgres"}.get(
        (dialect or "").lower(), (dialect or "duckdb").lower()
    )
    if read == "tsql":
        cleaned = text  # brackets are T-SQL's own quotes
    try:
        sqlglot.parse(cleaned, read=read)
    except ParseError as error:
        info = error.errors[0] if error.errors else {}
        line = int(info.get("line") or 1)
        col = int(info.get("col") or 1)
        highlight = str(info.get("highlight") or "")
        start = max(1, col - len(highlight) + 1) if highlight else col
        message = str(info.get("description") or str(error).split("\n")[0])
        return [Problem(line, start, line, max(start + 1, col + 1), message, "error", "SQL", "SQL")]
    except TokenError as error:
        return [Problem(1, 1, 1, 2, str(error).split("\n")[0], "error", "SQL", "SQL")]
    except Exception:  # a dialect sqlglot does not know: nothing said
        return []
    return []


def duckdb_error(message: str, text: str) -> Problem:
    """DuckDB's parser error ("syntax error at or near "t"\\n\\nLINE 2: FORM t\\n ^") at its place."""
    first = message.split("\n")[0].removeprefix("Parser Error: ")
    line = 1
    col = 1
    found = re.search(r"LINE (\d+):( ?)(.*)\n(\s*)\^", message)
    if found:
        line = int(found.group(1))
        col = len(found.group(4)) - len(f"LINE {found.group(1)}:{found.group(2)}") + 1
    lines = text.split("\n")
    if line - 1 < len(lines):
        col = max(1, min(col, len(lines[line - 1]) + 1))
    near = re.search(r'at or near "([^"]*)"', first)
    width = len(near.group(1)) if near else 1
    if near and line - 1 < len(lines):
        at = lines[line - 1].find(near.group(1), max(0, col - 1 - len(near.group(1))))
        if at >= 0:
            col = at + 1
    return Problem(
        line, col, line, col + max(1, width), first[:1].upper() + first[1:], "error", "SQL", "DuckDB"
    )


# ===== the project's own modules =====

# The project's scaffold files whose names complete with an import (the owner's list, 2026-11-17).
PROJECT_MODULES: tuple[str, ...] = ("functions", "data", "structures", "variables", "connections")


def module_names(source: str) -> list[dict[str, str]]:
    """The public names a project module makes at its top, each with its kind, a signature line for a
    function and its docstring (its `__all__` when it has one). Nothing when it does not parse."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[dict[str, str]] = []
    exported: set[str] | None = None
    for s in tree.body:
        if (
            isinstance(s, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in s.targets)
            and isinstance(s.value, ast.List | ast.Tuple)
        ):
            exported = {
                e.value for e in s.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
    for s in tree.body:
        if isinstance(s, ast.FunctionDef | ast.AsyncFunctionDef):
            returns = f" -> {ast.unparse(s.returns)}" if s.returns is not None else ""
            line = f"{s.name}({ast.unparse(s.args)}){returns}"
            out.append(
                {"name": s.name, "kind": "function", "signature": line, "doc": ast.get_docstring(s) or ""}
            )
        elif isinstance(s, ast.ClassDef):
            out.append({"name": s.name, "kind": "class", "signature": "", "doc": ast.get_docstring(s) or ""})
        elif isinstance(s, ast.Assign | ast.AnnAssign):
            for t in s.targets if isinstance(s, ast.Assign) else [s.target]:
                if isinstance(t, ast.Name):
                    out.append({"name": t.id, "kind": "variable", "signature": "", "doc": ""})
    if exported is not None:
        return [n for n in out if n["name"] in exported]
    return [n for n in out if not n["name"].startswith("_")]


def imported_names(text: str) -> set[str]:
    """The names a text's import lines bind (so a completion does not import twice)."""
    out: set[str] = set()
    for line in text.split("\n"):
        found = re.match(r"^\s*from\s+\S+\s+import\s+\(?([\w ,]+)\)?", line)
        if found:
            out.update(n.split(" as ")[-1].strip() for n in found.group(1).split(",") if n.strip())
        found = re.match(r"^\s*import\s+([\w., ]+)", line)
        if found:
            out.update(
                n.split(" as ")[-1].strip().split(".")[0] for n in found.group(1).split(",") if n.strip()
            )
    return out


# ===== ranking =====

# The groups, in the order the list shows them.
GROUPS: tuple[str, ...] = ("scope", "project", "app", "library", "keyword")


def rank(items: Sequence[Mapping[str, Any]], recent: Sequence[str] = ()) -> list[dict[str, Any]]:
    """Completions in their groups' order (scope, project, app, libraries, keywords); in each group the
    recently used first (the most recent first), then names as given (not _private ones before public
    ones). Each label once: the first group that offers it keeps it, the others' details join it."""
    order = {g: i for i, g in enumerate(GROUPS)}
    used = {name: i for i, name in enumerate(recent)}
    seen: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        label = str(item["label"])
        if label in seen:
            kept = seen[label]
            for field_name in ("documentation", "signature", "detail"):
                if not kept.get(field_name) and item.get(field_name):
                    kept[field_name] = item[field_name]
            continue
        seen[label] = dict(item) | {"_i": index}

    def order_of(item: dict[str, Any]) -> tuple[int, int, int, int]:
        label = str(item["label"])
        return (
            order.get(str(item.get("group") or "library"), len(GROUPS)),
            used.get(label, len(used) + 1),
            1 if label.startswith("_") else 0,
            int(item["_i"]),
        )

    ranked = sorted(seen.values(), key=order_of)
    for i, item in enumerate(ranked):
        item.pop("_i", None)
        item["sort"] = f"{i:05d}"
    return ranked


def snippet(name: str, params: Sequence[tuple[str, bool, bool]]) -> str:
    """A call with its required arguments as tab stops: `write_sqlite(${1:connection}, ${2:table})`.
    `params`: (name, required, keyword only), as Jedi gives them."""
    stops: list[str] = []
    for param, required, keyword_only in params:
        if not required or param in ("self", "cls") or param.startswith("*"):
            continue
        holder = re.sub(r"[$}\\]", "", param)
        n = len(stops) + 1
        stops.append(f"{holder}=${{{n}}}" if keyword_only else f"${{{n}:{holder}}}")
    return f"{name}({', '.join(stops)})$0" if stops else f"{name}($0)"


def markdown_doc(signature: str, doc: str, origin: str = "") -> str:
    """The documentation panel's words: the full signature as code, the summary, each parameter's
    words, what it returns and raises, where it comes from."""
    d = parse_docstring(doc)
    parts = [f"```python\n{signature}\n```"] if signature else []
    if d.summary:
        parts.append(_escape(d.summary))
    rows = [f"- `{n}`: {_escape(w)}" for n, w in d.params.items() if w]
    if rows:
        parts.append("**Parameters**\n" + "\n".join(rows))
    if d.returns:
        parts.append(f"**Returns** {_escape(d.returns)}")
    if d.raises:
        parts.append("**Raises** " + "; ".join(_escape(r) for r in d.raises))
    if origin:
        parts.append(f"_From {_escape(origin)}_")
    return "\n\n".join(parts)


def _escape(text: str) -> str:
    """Words for markdown: no HTML (the page renders markdown without it)."""
    return text.replace("<", "&lt;").replace(">", "&gt;")


# ===== sab_api, what API.py imports (server/api_runtime.py, copied as sab_api.py into each export) =====

SAB_API_IMPORT = re.compile(r"^\s*from\s+sab_api\s+import\s+(?:\(?\s*)?(?:\w+\s*,\s*)*(\w*)$", re.M)
SAB_API_MODULE = "swissarmybench.server.api_runtime"
_SAB_API: tuple[tuple[str, str, str, str], ...] = (
    (
        "endpoint",
        "function",
        'endpoint(method, path, *, summary="", status=200)',
        "Registers the function as an endpoint: a path's {names} are its parameters; a TypedDict or "
        "dataclass "
        "parameter is the JSON body (checked against it: 422 naming the field); the rest are the query's.",
    ),
    (
        "connection",
        "function",
        "connection(name)",
        "The connection's client: here a mock with the real client's shape over the project's sandbox; in an "
        "export, the connection's own portable code.",
    ),
    (
        "records",
        "function",
        "records(cursor)",
        "A DB-API cursor's rows as dicts, by its description's names.",
    ),
    (
        "ApiError",
        "class",
        "ApiError(status, message, field=None)",
        'Raise it for an answer with that status and {"error": message}.',
    ),
)


def sab_api_names() -> list[dict[str, Any]]:
    """The completions after `from sab_api import`: sab_api's own names, with their words."""
    return [
        {
            "label": n,
            "kind": k,
            "detail": sig,
            "documentation": markdown_doc(sig, doc, "sab_api"),
            "group": "app",
        }
        for n, k, sig, doc in _SAB_API
    ]


def sab_api_for_jedi(code: str, cursor_line: int) -> str:
    """API.py as Jedi reads it: `sab_api` (a copy of the app's runtime) imported from where it lives, so its
    names complete and hover. The cursor's line (0-based) is left as typed, so the positions hold."""
    lines = code.split("\n")
    for at, line in enumerate(lines):
        if at == cursor_line:
            continue
        lines[at] = re.sub(r"^(\s*from\s+)sab_api(\s+import\b)", rf"\g<1>{SAB_API_MODULE}\g<2>", line)
        lines[at] = re.sub(
            r"^(\s*)import\s+sab_api\s*$", rf"\g<1>import {SAB_API_MODULE} as sab_api", lines[at]
        )
    return "\n".join(lines)
