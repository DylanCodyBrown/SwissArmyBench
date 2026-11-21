"""A blade file's header as the blade tab's Properties, its checks before a save, and New blade's scaffolds.

The owner (2026-11-21): "the blade format requires extra stuff so we should add those properties to the ide
experience along with the option to save the blade. we should scaffold a blank blade for the user".

- **Fields**: every field of the `# /// swissarmybench-blade` header (domain/blades.py `_header_lines`) as a
  Properties field, shown only for the kinds it applies to (`applies`): its key, words, type and value.
  `fields` draws them; `changes` turns a Properties save (or the agent's blades_header_set) into what
  parse_blade reads, refusing a field the kind has not or one that follows from the code (kind, secrets).
- **The required part** (`required_part`): before a Save, beyond compiling (parse_blade): a table blade's
  function returns its table, an analysis's takes the rows, a Python connection has its List the tables and
  Read a table, a vault's reader is a function. A refusal says what and on which line.
- **Scaffolds** (`scaffold`): New blade asks only a name and a kind; the file starts as that kind's blank,
  valid blade, its comments saying what to write and a minimal body over made-up rows, so Run works at once.

Standard library only; no I/O.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain import connection_slots as slot_rules
from swissarmybench.domain.blades import BladeError
from swissarmybench.domain.catalogs import DIALECTS
from swissarmybench.domain.snippets import LANGUAGES


@dataclass(frozen=True)
class Field:
    """One header field: `key` as the file writes it (a table's part as `queries.total`), its words, its
    type (text, textarea, tags, choice, number, bool, names, mapping, code, readonly), its choices."""

    key: str
    label: str
    type: str
    choices: tuple[str, ...] = ()
    hint: str = ""


FIELDS: tuple[Field, ...] = (
    Field("name", "Name", "text"),
    Field("kind", "Kind", "readonly"),
    Field("description", "Description", "textarea"),
    Field("tags", "Tags", "tags"),
    Field("family", "Family", "text"),
    Field("variable", "It hands back", "text", hint="the name its code makes"),
    Field("table", "Its table is called", "text"),
    Field("language", "Language", "choice", LANGUAGES),
    Field("cell_name", "Its cell's name", "text"),
    Field("dialect", "SQL dialect", "choice", DIALECTS),
    Field("row_limit", "Rows to open", "number", hint="0: every row"),
    Field("queries.total", "Queries at once", "number"),
    Field("queries.agent", "The agent's share", "number"),
    Field("queries.wait", "Seconds a query waits", "number"),
    Field("vault_all", "Every secret in the vault", "bool"),
    Field("vault_mapping", "Variables from the vault", "mapping", hint="VARIABLE = secret-name, one a line"),
    Field("env_names", "Its variables", "names", hint="one a line"),
    Field("secrets", "Secrets it asks for", "readonly"),
    Field("catalog.language", "Its tables are listed in", "choice", ("sql", "python")),
    Field("catalog.command", "How its tables are listed", "code"),
    Field("read.command", "Read a table", "code"),
    Field("template", "Made from", "readonly"),
    Field("web_call", "Web call", "readonly"),
    Field("variables", "Where its variables come from", "readonly"),
)
_BY_KEY: dict[str, Field] = {f.key: f for f in FIELDS}
# Fields that follow from the code or the file: shown, never changed by a Properties save.
READ_ONLY: frozenset[str] = frozenset({"kind", "secrets", "template", "web_call", "variables"})
# The keys a Properties save or blades_header_set may send.
KEYS: frozenset[str] = frozenset(_BY_KEY) - READ_ONLY


@dataclass(frozen=True)
class Shape:
    """What a blade is, for which fields apply: its kind, its connection (database, file, vault, python or
    None), whether it names a table of its own, whether it is an API's web call."""

    kind: str
    connection: str | None
    names_table: bool
    web_call: bool = False
    template: str | None = None


def applies(key: str, shape: Shape) -> bool:
    """Whether the header field `key` belongs to a blade of this shape."""
    kind, conn = shape.kind, shape.connection
    if key in ("name", "kind", "description", "tags", "family"):
        return True
    if key in ("language", "cell_name"):
        return kind == "snippet"
    if key == "variable":
        return kind not in ("secret", "snippet")
    if key == "table":
        return shape.names_table
    if key == "dialect":
        return kind == "sql"
    if key == "row_limit":
        return conn in ("database", "python")
    if key.startswith("queries."):
        return kind in ("sql", "other") and conn in ("database", "file", "python")
    if key in ("vault_all", "vault_mapping"):
        return kind == "vault"
    if key == "env_names":
        return kind == "secret"
    if key == "secrets":
        return kind not in ("secret", "snippet")
    if key.startswith("catalog."):
        return conn in ("database", "file", "python")
    if key == "read.command":
        return conn == "python"
    if key == "template":
        return bool(shape.template)
    if key == "web_call":
        return shape.web_call
    if key == "variables":
        return conn == "python"
    return False


def _value(key: str, blade: Mapping[str, Any]) -> Any:
    if key.startswith("queries."):
        limits = slot_rules.check_limits(blade.get("queries") or None)
        return getattr(limits, key.split(".", 1)[1])
    if key.startswith("catalog.") or key == "read.command":
        part, field = key.split(".", 1)
        table = blade.get(part)
        return str(table.get(field) or "") if isinstance(table, Mapping) else ""
    if key == "vault_mapping":
        return "\n".join(f"{row['env']} = {row['secret']}" for row in blade.get("vault_mapping") or [])
    if key == "env_names":
        return "\n".join(blade.get("env_names") or [])
    if key == "web_call":
        call = blade.get("web_call") or {}
        return " ".join(str(call.get(k) or "") for k in ("method", "path")).strip()
    if key == "variables":
        rows = blade.get("variables") or []
        return ", ".join(str(row.get("name")) for row in rows if isinstance(row, Mapping))
    value = blade.get(key)
    if key == "tags":
        return list(value or [])
    if key == "secrets":
        return list(value or []) if isinstance(value, list) else []
    if key in ("vault_all",):
        return bool(value)
    if key == "row_limit":
        return value if isinstance(value, int) else None
    return "" if value is None else value


def fields(blade: Mapping[str, Any], shape: Shape, secrets: list[str] | None = None) -> list[dict[str, Any]]:
    """The Properties fields of this blade, in the header's order, each with its value now."""
    given = dict(blade) | ({"secrets": secrets} if secrets is not None else {})
    out: list[dict[str, Any]] = []
    for f in FIELDS:
        if not applies(f.key, shape):
            continue
        row: dict[str, Any] = {"key": f.key, "label": f.label, "type": f.type, "value": _value(f.key, given)}
        if f.choices:
            row["choices"] = list(f.choices)
        if f.hint:
            row["hint"] = f.hint
        if f.key in READ_ONLY:
            row["read_only"] = True
        out.append(row)
    return out


_MAPPING_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")


def _number(key: str, value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not str(value).strip().lstrip("-").isdigit():
        raise BladeError(f"{_BY_KEY[key].label} is a whole number.")
    return int(str(value).strip())


def changes(blade: Mapping[str, Any], body: Mapping[str, Any], shape: Shape) -> dict[str, Any]:
    """A Properties save's fields (`body`, keyed as `fields` gives them) as the blade's JSON changes that
    parse_blade checks. Refused: a field this kind has not, or one that follows from the code."""
    out: dict[str, Any] = {}
    for key, value in body.items():
        if key not in _BY_KEY:
            raise BladeError(f"A blade's header has no field {key!r}.")
        if key in READ_ONLY:
            raise BladeError(
                f"{_BY_KEY[key].label} follows from the blade's code or file: it is not set here."
            )
        if not applies(key, shape):
            raise BladeError(f"{_BY_KEY[key].label} is not a field of a {shape.kind} blade.")
        if key.startswith("queries."):
            queries = dict(
                out.get("queries") or slot_rules.check_limits(blade.get("queries") or None).header()
            )
            number = _number(key, value)
            part = key.split(".", 1)[1]
            if number is None:
                queries.pop(part, None)
            else:
                queries[part] = number
            out["queries"] = queries
        elif key.startswith("catalog.") or key == "read.command":
            part, field = key.split(".", 1)
            table = dict(
                out.get(part) or (blade.get(part) if isinstance(blade.get(part), Mapping) else {}) or {}
            )
            table[field] = "" if value is None else str(value)
            if part == "catalog":
                table.setdefault("language", "sql")
            out[part] = table
        elif key == "vault_mapping":
            rows = []
            for line in str(value or "").splitlines():
                if not line.strip():
                    continue
                match = _MAPPING_LINE.match(line)
                if not match:
                    raise BladeError(f"Each line reads VARIABLE = secret-name, not {line.strip()[:60]!r}.")
                rows.append({"env": match[1], "secret": match[2]})
            out["vault_mapping"] = rows
        elif key == "env_names":
            names = value if isinstance(value, list) else str(value or "").replace(",", "\n").splitlines()
            out["env_names"] = [str(n).strip() for n in names if str(n).strip()]
        elif key == "row_limit":
            out["row_limit"] = _number(key, value)
        elif key == "vault_all":
            out["vault_all"] = value is True or str(value).lower() in ("true", "1", "yes", "on")
        elif key == "tags":
            out["tags"] = value
        else:
            out[key] = "" if value is None else value
    return out


# ===== the required part, before a save =====


@dataclass(frozen=True)
class Missing:
    """What a blade's code lacks for its kind, and the line it is about (1: the top)."""

    message: str
    line: int = 1

    def to_json(self) -> dict[str, Any]:
        return {"error": self.message, "line": self.line}


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def _returns_value(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Return) and node.value is not None:
            return True
        if isinstance(node, ast.Yield | ast.YieldFrom):
            return True
    return False


def _required_args(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    args = function.args
    positional = len(args.posonlyargs) + len(args.args)
    return positional - len(args.defaults)


def required_part(
    shape: Shape, code: str, variable: str | None, catalog: str = "", read: str = ""
) -> Missing | None:
    """What the code lacks for its kind (None: nothing). Code that does not compile is parse_blade's to
    say; here it is said too, with its line, so a refusal always points somewhere."""
    if shape.kind in ("secret", "snippet"):
        return None
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        return Missing(f"The code is not valid Python: {error.msg}.", error.lineno or 1)
    if not variable:
        return Missing("The code makes nothing to hand back: end it with a function or name = ....")
    function = _function(tree, variable)
    if shape.kind == "analysis":
        if function is None:
            return Missing(f"An analysis blade is a function of the rows: def {variable}(df): ....")
        if not 1 <= len(function.args.posonlyargs) + len(function.args.args) <= 2:
            return Missing(
                f"{variable} takes the rows (df), and optionally the columns: 1 or 2 arguments.",
                function.lineno,
            )
        return None
    if shape.names_table and function is not None:
        if _required_args(function) > 0:
            return Missing(
                f"A table blade's {variable}() is called with nothing: give its arguments defaults.",
                function.lineno,
            )
        if not _returns_value(function):
            return Missing(
                f"A table blade's {variable}() returns its table: end it with return <the DataFrame>.",
                function.lineno,
            )
    if shape.connection == "python":
        if not catalog.strip():
            return Missing("A Python connection lists its tables: fill in How its tables are listed.")
        if not read.strip():
            return Missing("A Python connection reads a table: fill in Read a table.")
    if shape.kind == "vault" and function is None:
        return Missing(f"A vault blade's {variable} is a function: def {variable}(name): returns the secret.")
    return None


# ===== New blade: a name and a kind, and the blank blade it starts as =====

SCAFFOLD_KINDS: tuple[str, ...] = ("table", "code", "analysis", "connection", "snippet", "secret")

_TABLE = '''"""What this table holds, in a sentence."""

# A table blade: the function below is called with nothing and returns a DataFrame. Read your source here
# (a file, an API, a database) and return its rows; sab.blade("{name}") gives the table.
import pandas as pd


def make_table() -> pd.DataFrame:
    # Made-up rows to start from: replace them with your own source's.
    return pd.DataFrame(
        {{
            "order_id": [1001, 1002, 1003],
            "customer": ["Ada Lane", "Bo Reyes", "Cy Ortiz"],
            "amount": [120.5, 89.0, 342.25],
        }}
    )
'''

_CODE = '''"""What this blade gives, in a sentence."""

# Any code: what it makes last (here `regions`) is what sab.blade("{name}") hands back.
regions = ["North", "South", "East", "West"]
'''

_ANALYSIS = '''"""What this analysis answers, in a sentence."""

# An analysis blade: the Analyze page calls it with a table's rows (a pandas DataFrame) and, if it takes
# them, the columns picked. Return markdown text, a table, a figure, or a list of them. Run tries it on
# made-up rows.
import pandas as pd


def analyze(df: pd.DataFrame) -> str:
    return f"{{len(df):,}} rows, {{len(df.columns)}} columns."
'''

_CONNECTION = '''"""What this connection reaches, in a sentence."""

# A connection: `conn` is what the code hands back; SQL cells and [{name}].table read through it, and its
# tables are listed by the query in Properties (How its tables are listed). This one is DuckDB in memory
# with made-up rows: point it at your own database instead.
import duckdb

conn = duckdb.connect()
conn.execute(
    "CREATE TABLE orders AS SELECT * FROM (VALUES "
    "(1001, 'Ada Lane', 120.5), (1002, 'Bo Reyes', 89.0), (1003, 'Cy Ortiz', 342.25)"
    ") AS t(order_id, customer, amount)"
)
'''

_CONNECTION_LISTING = (
    "SELECT table_schema AS schema, table_name AS name FROM information_schema.tables ORDER BY 1, 2"
)


def scaffold(kind: str, name: str) -> dict[str, Any]:
    """The blank blade New blade makes for `kind` (one of SCAFFOLD_KINDS), named `name`: its JSON, which
    parse_blade reads and the file is written from."""
    made: dict[str, Any] = {"name": name, "template": None}
    if kind == "table":
        return made | {"kind": "other", "code": _TABLE.format(name=name), "variable": "make_table"}
    if kind == "code":
        return made | {"kind": "other", "code": _CODE.format(name=name), "variable": "regions"}
    if kind == "analysis":
        return made | {"kind": "analysis", "code": _ANALYSIS.format(name=name), "variable": "analyze"}
    if kind == "connection":
        return made | {
            "kind": "sql",
            "dialect": "duckdb",
            "code": _CONNECTION.format(name=name),
            "variable": "conn",
            "catalog": {"language": "sql", "command": _CONNECTION_LISTING},
        }
    if kind == "snippet":
        return made | {
            "kind": "snippet",
            "language": "markdown",
            "code": "## <<title>>\n\nWhat this part of the notebook says.",
        }
    if kind == "secret":
        return made | {"kind": "secret", "env_names": ["MY_API_TOKEN"]}
    raise BladeError(f"New blade makes one of: {', '.join(SCAFFOLD_KINDS)}.")


def body_line(code: str) -> int:
    """Where the cursor goes in a new scaffold: the first line of its working body (the first line after
    the comments and imports, else 1)."""
    lines = code.split("\n")
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith(("def ", "return ", "conn =", "regions =", "##")):
            return i + 1 if stripped.startswith("def ") else i
    return 1
