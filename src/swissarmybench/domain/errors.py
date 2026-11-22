"""The error panel's words: what an error means and what to do, in plain language. Pure rules: facts
in (client/kernel_errors.py gathers them in the kernel), an explanation and fixes out.

A fix is something the Workbench can do with one click:
    replace   put `text` where `target` is on the failing line ("Use 'amount'")
    import    add `line` at the top of the cell or script ("Add import pandas as pd")
    install   install `package` into this document's Python (`%pip install`, which uses uv without pip)
    define    run the cell that makes `name` (the page finds it among the cells)
    cell      add a code cell holding `text` below the failing one (a script: copy it)
    table     give the document the read-only cell of `name`, a table open in Grids (a SQL cell named it)
The research behind it: docs/ideas.md (the error panel, 2026-11-14). The explanations are our own,
written for data work; nothing leaves the computer.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain import dataverse
from swissarmybench.domain.packages import missing_packages

# Names people use without importing them, and the line that brings each in.
IMPORTS: dict[str, str] = {
    "pd": "import pandas as pd",
    "np": "import numpy as np",
    "plt": "import matplotlib.pyplot as plt",
    "sns": "import seaborn as sns",
    "px": "import plotly.express as px",
    "go": "import plotly.graph_objects as go",
    "pl": "import polars as pl",
    "pa": "import pyarrow as pa",
    "pq": "import pyarrow.parquet as pq",
    "sab": "import swissarmybench as sab",
    "duckdb": "import duckdb",
    "os": "import os",
    "sys": "import sys",
    "re": "import re",
    "json": "import json",
    "math": "import math",
    "time": "import time",
    "datetime": "import datetime",
    "random": "import random",
    "csv": "import csv",
    "Path": "from pathlib import Path",
    "defaultdict": "from collections import defaultdict",
    "Counter": "from collections import Counter",
    "dataclass": "from dataclasses import dataclass",
    "display": "from IPython.display import display",
}

# A module's name to the package that installs it, where the two differ.
PACKAGES: dict[str, str] = {
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "cv2": "opencv-python",
    "PIL": "pillow",
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "dotenv": "python-dotenv",
    "Crypto": "pycryptodome",
    "MySQLdb": "mysqlclient",
    "psycopg2": "psycopg2-binary",
    "attr": "attrs",
    "jwt": "pyjwt",
    "magic": "python-magic",
    "fitz": "pymupdf",
}


def _quote(text: str) -> str:
    return f"'{text}'"


def _list(names: list[str], most: int = 8) -> str:
    shown = [_quote(n) for n in names[:most]]
    more = len(names) - len(shown)
    if not shown:
        return ""
    if more > 0:
        return ", ".join(shown) + f" and {more} more"
    return shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " and " + shown[-1]


def _replace(target: str, options: list[str]) -> list[dict[str, Any]]:
    return [
        {"kind": "replace", "title": f"Use {_quote(o)}", "target": target, "text": o} for o in options[:3]
    ]


def _bare(text: str) -> str:
    """A key as the error shows it ('amont') without its quotes."""
    return text[1:-1] if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"" else text


# ===== the rules: one entry an error =====
#
# explain() tries RULES in order and the first whose test matches says the explanation and the fixes. A new
# error is a new entry (its test, its words), never another branch: put a narrower rule before a wider one
# (a TypeError that names NoneType before any TypeError), and the rules that read the message rather than
# the type (Dataverse's SQL endpoint, a SQL error) last.


@dataclass(frozen=True)
class Seen:
    """What a rule looks at: the exception's type, its message and the facts the kernel gathered."""

    kind: str
    message: str
    facts: Mapping[str, Any]


Said = tuple[str, list[dict[str, Any]]]  # the explanation, the fixes


def _is(*kinds: str) -> Callable[[Seen], bool]:
    return lambda seen: seen.kind in kinds


def _words(text: str) -> Callable[[Seen], Said]:
    return lambda seen: (text, [])


def _name_error(seen: Seen) -> Said:
    name = str(seen.facts.get("name") or _name_in(seen.message) or "")
    candidates = [c for c in seen.facts.get("candidates", []) if c != name]
    fixes: list[dict[str, Any]] = []
    text = (
        f"Python has no {_quote(name)} here. Either the cell that makes it has not run yet (or ran "
        f"before a restart), or the name is spelled differently."
    )
    if name in IMPORTS:
        text = (
            f"{_quote(name)} is usually brought in with `{IMPORTS[name]}`, which has not run in this kernel."
        )
        fixes.append({"kind": "import", "title": f"Add `{IMPORTS[name]}`", "line": IMPORTS[name]})
    fixes += _replace(name, candidates)
    if name and name not in IMPORTS:
        fixes.append({"kind": "define", "title": f"Run the cell that makes {_quote(name)}", "name": name})
    return text, fixes


def _attribute_error(seen: Seen) -> Said:
    facts = seen.facts
    name = str(facts.get("name") or "")
    if facts.get("is_none"):
        return (
            f"The value is None, so it has no {_quote(name)}. Something earlier gave back None "
            f"instead of what you expected (a function with no `return`, or a method that changes the "
            f"value in place, like `.sort()`).",
            [],
        )
    fixes: list[dict[str, Any]] = []
    owner = str(facts.get("object_type") or "the value")
    text = f"A {owner} has no attribute {_quote(name)}."
    columns = facts.get("columns") or []
    if columns:
        text += (
            f" Its columns are {_list(columns)}; a column whose name has spaces or capitals is "
            f"read with `df['Column name']`."
        )
        fixes += _replace(name, list(facts.get("column_candidates", [])))
    fixes += _replace(
        name, [c for c in facts.get("candidates", []) if c not in facts.get("column_candidates", [])]
    )
    return text, fixes


def _missing_module(seen: Seen) -> Said:
    module = str(seen.facts["module"])
    top = module.split(".")[0]
    package = PACKAGES.get(top, top)
    text = (
        f"This Python does not have {_quote(top)}. Install it into this document's environment (the "
        f"Environment picker shows which Python runs it)."
    )
    if package != top:
        text += f" Its package is called {_quote(package)}."
    fix = {"kind": "install", "title": f"Install {_quote(package)} here", "package": package, "module": top}
    return text, [fix]


def _key_error(seen: Seen) -> Said:
    facts = seen.facts
    key = _bare(str(facts.get("key", seen.message)))
    keys = list(facts.get("keys") or [])
    if facts.get("table"):
        text = f"The table has no column {_quote(key)}."
        if keys:
            text += f" Its columns are {_list(keys)}."
    elif keys:
        text = f"There is no key {_quote(key)}. The keys are {_list(keys)}."
    elif seen.kind == "IndexError":
        length = facts.get("length")
        text = "The position is past the end." + (
            f" It has {length:,} items, so the last is at {length - 1:,} (counting from 0)."
            if isinstance(length, int) and length > 0
            else ""
        )
    else:
        text = f"There is no key {_quote(key)}."
    return text, _replace(key, list(facts.get("candidates", [])))


def _file_error(seen: Seen) -> Said:
    full = str(seen.facts.get("full_path") or seen.facts.get("path") or "")
    cwd = str(seen.facts.get("cwd") or "")
    if seen.kind == "FileNotFoundError":
        text = f"Nothing is at {full}." if full else "The file is not there."
        if cwd:
            text += f" A path that does not start at a drive or / is read from the kernel's folder, {cwd}."
    elif seen.kind == "PermissionError":
        text = (
            f"This computer does not let Python open {full or 'it'} (it may be open in Excel, or read-only)."
        )
    else:
        text = f"{full or 'The path'} is a folder where a file was expected, or the other way round."
    return text, []


def _decode_error(seen: Seen) -> Said:
    return (
        f"The file is not in {seen.facts.get('encoding') or 'that'} encoding. Files from Excel on Windows "
        f"are often 'cp1252' or 'latin-1': pass `encoding='cp1252'` when reading it.",
        [],
    )


def _tds_off(seen: Seen) -> Said:
    text = (
        "This Dataverse environment's SQL endpoint is off, so SQL cannot reach it. An admin turns on "
        '"Enable TDS endpoint" in the Power Platform admin center; reading the table through the Web '
        "API works now."
    )
    line = re.search(r"(\w+ = )?sab\.read\([^)]*\)", seen.message)
    fixes = [{"kind": "cell", "title": "Read the table instead", "text": line.group(0)}] if line else []
    return text, fixes


def _sql_error(seen: Seen) -> Said:
    absent = missing_table(seen.message)
    text = (
        f"The SQL names a table this query cannot see: {_quote(absent)}. Open it in Grids, read it with "
        "a cell, or check the name's spelling."
        if absent
        else "The SQL did not run: the database's own words are above."
    )
    return text, []


RULES: tuple[tuple[Callable[[Seen], bool], Callable[[Seen], Said]], ...] = (
    (_is("NameError"), _name_error),
    (
        _is("UnboundLocalError"),
        _words(
            "A function reads a variable before giving it a value. A name assigned anywhere in a function "
            "is that function's own, even on the lines before the assignment: give it a value first, or "
            "mark it `global`."
        ),
    ),
    (_is("AttributeError"), _attribute_error),
    (
        lambda seen: seen.kind in ("ModuleNotFoundError", "ImportError") and bool(seen.facts.get("module")),
        _missing_module,
    ),
    (_is("KeyError", "IndexError"), _key_error),
    (
        _is("ZeroDivisionError"),
        _words(
            "A number was divided by zero. The values below show which part was 0; guard it, or let a "
            "table's division give NaN (pandas does that for columns)."
        ),
    ),
    (
        lambda seen: seen.kind == "TypeError" and "NoneType" in seen.message,
        _words(
            "One of the values is None where a real value was expected. The values below show which; "
            "something earlier gave back None."
        ),
    ),
    (
        _is("TypeError"),
        _words(
            "A value of the wrong kind was used here: the message says which kinds met. The values below "
            "show what each part held."
        ),
    ),
    (
        _is("ValueError"),
        _words(
            "The kind of value was right but not the value itself (a word where a number was expected, a "
            "date in another format, a size that does not match)."
        ),
    ),
    (_is("FileNotFoundError", "IsADirectoryError", "NotADirectoryError", "PermissionError"), _file_error),
    (_is("UnicodeDecodeError"), _decode_error),
    (
        _is("SyntaxError"),
        _words(
            "Python could not read this code: nothing in it ran. The mark shows where it stopped "
            "understanding (the mistake is often just before it: a missing bracket, quote or colon)."
        ),
    ),
    (
        _is("IndentationError", "TabError"),
        _words(
            "The lines' indents do not line up: every line of a block needs the same indent (four "
            "spaces), and tabs and spaces should not be mixed."
        ),
    ),
    (
        _is("RecursionError"),
        _words(
            "A function called itself too many times (it never reached the case that stops). Only the "
            "first and last calls are shown."
        ),
    ),
    (
        _is("MemoryError"),
        _words(
            "This Python ran out of memory. Read fewer rows, fewer columns, or let DuckDB do the work on "
            "the file instead of loading it whole."
        ),
    ),
    (
        _is("KeyboardInterrupt"),
        _words("Interrupt stopped the run. Variables made before that point are still there."),
    ),
    # By the message, whatever the type: after every rule that knows its type.
    (lambda seen: dataverse.tds_off(seen.message), _tds_off),
    (
        lambda seen: seen.kind == "UsageError" or ("Error" in seen.kind and _sql_text(seen.message)),
        _sql_error,
    ),
)
# An error whose title is not its type and message.
TITLES: dict[str, str] = {"KeyboardInterrupt": "Interrupted"}


def explain(entry: dict[str, Any]) -> dict[str, Any]:
    """One exception of the chain: a title, a plain explanation and the fixes (the first of RULES that
    matches; none: no explanation), then what any error may carry: a SQL error's place and close names, a
    "Did you mean" hint as a fix."""
    kind = str(entry.get("type", ""))
    message = str(entry.get("message", ""))
    facts: dict[str, Any] = entry.get("facts") or {}
    seen = Seen(kind, message, facts)
    title = TITLES.get(kind) or (f"{kind}: {message}" if message else kind)
    text, fixes = next((says(seen) for matches, says in RULES if matches(seen)), ("", []))
    sql = sql_position(message)
    if sql:
        candidates = sql.get("candidates", [])
        if sql.get("missing"):
            fixes += _replace(str(sql["missing"]), candidates)
    hint = str(entry.get("hint") or "")
    if hint and not fixes:
        found = re.search(r"Did you mean:? '?([\w.]+)'?\??", hint)
        if found:
            target = str(facts.get("name") or _name_in(message) or "")
            if target:
                fixes += _replace(target, [found.group(1)])
    shown = _without_system_guess(message)
    if shown != message:
        title = f"{kind}: {shown}" if shown else kind
    return {"title": title, "message": shown, "explanation": text, "fixes": _unique(fixes), "sql": sql}


# DuckDB's own tables and views: its "Did you mean" offers one when nothing of the user's is close.
_SYSTEM = re.compile(r"^(pg_|duckdb_|sqlite_|information_schema|pragma_)", re.IGNORECASE)
_GUESS = re.compile(r'\s*Did you mean "([^"]+)"\??')


def _without_system_guess(message: str) -> str:
    """The message without a "Did you mean" that names one of DuckDB's own tables (pg_prepared_statements
    for `orders`): it points away from the user's tables."""
    found = _GUESS.search(message)
    if found and _SYSTEM.match(found.group(1).split(".")[-1]):
        return (message[: found.start()] + message[found.end() :]).rstrip()
    return message


def missing_table(message: str) -> str | None:
    """The table a SQL error says is missing: DuckDB's "Table with name orders does not exist!" (any name,
    spaces too) and the "Table "x" does not exist" of others."""
    found = re.search(r'Table with name "?(.+?)"? does not exist', message) or re.search(
        r'[Tt]able "([^"\n]+)" does not exist', message
    )
    return found.group(1).strip() if found else None


def _offer_open_table(entry: dict[str, Any], open_tables: list[str]) -> None:
    """A SQL error's missing table that is open in Grids: its read-only cell, one click away (first)."""
    sql = entry.get("sql") or {}
    absent = str(sql.get("missing") or "")
    if not absent or not missing_table(str(entry.get("message", ""))):
        return
    name = next((t for t in open_tables if t.lower() == absent.lower()), None)
    if name is None:
        return
    entry["explanation"] = (
        f"{_quote(name)} is open in Grids, but this document has no cell for it yet, so the query cannot "
        "see it. Add its table cell (its steps as one DuckDB query) and run this cell again."
    )
    title = f"{name} is open in Grids: add its table cell"
    entry["fixes"] = [{"kind": "table", "title": title, "name": name}] + [
        f for f in entry.get("fixes", []) if f.get("kind") != "replace"
    ]


def _unique(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for f in fixes:
        if f["title"] not in seen:
            seen.add(f["title"])
            out.append(f)
    return out


def _name_in(message: str) -> str | None:
    found = re.search(r"name '([^']+)' is not defined", message)
    return found.group(1) if found else None


def _sql_text(message: str) -> bool:
    return bool(re.search(r"\b(Binder|Parser|Catalog|Conversion) Error\b|LINE \d+:|syntax error", message))


def sql_position(message: str) -> dict[str, Any] | None:
    """Where a SQL error points, from the database's message: DuckDB's and Postgres's `LINE n:` with a
    caret under the place, and DuckDB's "Referenced column ... not found" with its candidates. Lines
    and columns are 1-based, counted in the SQL as the cell holds it."""
    found: dict[str, Any] = {}
    at = re.search(r"LINE (\d+):[ ]?(.*)\n( *)\^", message)
    if at:
        found["line"] = int(at.group(1))
        shown = at.group(2)
        # The message may show the line shortened from the left ("...ROM orders"): count from what it shows.
        prefix = len(f"LINE {at.group(1)}: ")
        found["col"] = max(1, len(at.group(3)) - prefix + 1)
        found["shown"] = shown
    missing = re.search(r'(?:column|Column) "?([\w.]+)"? (?:not found|does not exist)', message)
    if missing:
        found["missing"] = missing.group(1)
    elif table := missing_table(message):
        found["missing"] = table
    message = _without_system_guess(message)
    candidates = re.search(r"Candidate bindings: (.+?)(?:\n|$)", message) or re.search(
        r"Did you mean \"(.+?)\"", message
    )
    if candidates:
        found["candidates"] = [
            c.strip().strip('"').split(".")[-1] for c in candidates.group(1).split(",") if c.strip()
        ]
    return found or None


def explain_detail(
    detail: dict[str, Any], python: str | None = None, open_tables: list[str] | None = None
) -> dict[str, Any]:
    """The kernel's error detail with each exception's words added; `where` names the place in your own
    code the error went through last ("cell [3], line 2" or "report.py, line 7"). A package missing from
    the kernel's Python (`python`) is said in the one missing-package shape too (domain/packages.py). A SQL
    error naming a table that is open in Grids (`open_tables`, any case) offers that table's cell."""
    chain = [entry | explain(entry) for entry in detail.get("chain", []) if isinstance(entry, dict)]
    for entry in chain:
        _offer_open_table(entry, open_tables or [])
    out = dict(detail) | {"chain": chain}
    last = chain[-1] if chain else None
    wanted = [f["package"] for e in chain for f in e.get("fixes", []) if f.get("kind") == "install"]
    if wanted and python:
        out["missing"] = missing_packages("This code", wanted, python, own=False)
    if last:
        frames = last.get("frames") or []
        yours = last.get("your_frame")
        frame = frames[yours] if isinstance(yours, int) and 0 <= yours < len(frames) else None
        if last.get("syntax"):
            frame = last["syntax"]
        if frame:
            if frame.get("cell") is not None:
                out["where"] = f"cell [{frame['cell']}], line {frame.get('line')}"
            elif frame.get("file"):
                out["where"] = (
                    f"{str(frame['file']).replace(chr(92), '/').split('/')[-1]}, line {frame.get('line')}"
                )
    return out
