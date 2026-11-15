"""A connection from your own Python (the owner, 2026-11-15: "a connection from raw python. With env
variables mapping, and boxes to supply the python table from the connection to feed the catalog").

Three boxes of the user's Python, saved as one blade (kind `other`, template `python`):

  CONNECT          makes `conn`, any object: an internal web service's client, a vendor library, files
  LIST THE TABLES  returns the catalog for `conn`: a list of dicts or a DataFrame, one row per column,
                   with `table` and `column`, and optionally `schema`, `type` and `description`
                   (the blade's catalog command, in Python)
  READ A TABLE     returns a table's rows, given `conn`, `schema`, `table` and `limit` (None: every
                   row): a DataFrame, an Arrow table, a list of dicts, anything push accepts; or
                   `(rows, total)` when the source holds more than it gave

and the environment variables the three read (`os.environ["X"]`, `os.environ.get("X")`,
`os.getenv("X")`, `secret("X")`), found with ast, each with where its value comes from: this
computer's environment, the keyring, a key vault's secret, or a plain value that is no secret. The
code gets them as environment variables, as a vault's mapping gives them, so the same code runs
unchanged where those names are set some other way (an Azure Function's settings).

This file is the rules: the names found, a source checked, the catalog's shape, what Read returned.
Standard library only (the client runs a connection in the user's Python too). No I/O.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

TEMPLATE: str = "python"
VARIABLE: str = "conn"
# Where a variable's value comes from. "env": this computer's own environment, as the code reads it.
SOURCES: tuple[str, ...] = ("env", "keyring", "vault", "value")
MAX_VARIABLES: int = 100
MAX_CODE_CHARS: int = 200_000
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
_SECRET_WORDS = re.compile(r"pass|pwd|token|secret|credential|api_?key|private|key$", re.IGNORECASE)


class PythonConnectionError(ValueError):
    """The connection's boxes or mapping cannot be used as given. The message says why in plain words."""


# ===== the environment variables the code reads =====


@dataclass(frozen=True)
class EnvRead:
    name: str
    required: bool  # os.environ["X"] and secret("X") fail without it; .get and getenv do not

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "required": self.required, "secret": looks_secret(self.name)}


def looks_secret(name: str) -> bool:
    """A name that reads like a password, token or key: its value is offered as a secret first."""
    return bool(_SECRET_WORDS.search(name))


def _text(node: ast.AST | None) -> str | None:
    """A plain string written in the code (never an f-string, never a name built at run time)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and _NAME.fullmatch(node.value):
        return node.value
    return None


def env_reads(*codes: str | None) -> list[EnvRead]:
    """Every environment variable the code reads by a name written in it: `os.environ["X"]`,
    `os.environ.get("X")`, `os.getenv("X")` and `secret("X")` (also `environ` and `getenv` imported
    from os, and os under another name). In the order first read; a name read both ways is required.
    Code that is not Python yet (the user is typing) has no names. Nothing runs."""
    found: dict[str, bool] = {}
    for code in codes:
        if not code or not code.strip():
            continue
        try:
            tree = ast.parse(code)
        except (SyntaxError, ValueError):
            continue
        modules, environs, getenvs = {"os"}, set[str](), set[str]()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(a.asname or a.name for a in node.names if a.name == "os")
            elif isinstance(node, ast.ImportFrom) and node.module == "os":
                for alias in node.names:
                    if alias.name == "environ":
                        environs.add(alias.asname or alias.name)
                    elif alias.name == "getenv":
                        getenvs.add(alias.asname or alias.name)

        def is_environ(node: ast.AST, modules: set[str] = modules, environs: set[str] = environs) -> bool:
            if isinstance(node, ast.Name):
                return node.id in environs
            return (
                isinstance(node, ast.Attribute)
                and node.attr == "environ"
                and isinstance(node.value, ast.Name)
                and node.value.id in modules
            )

        reads: list[tuple[int, int, str, bool]] = []
        for node in ast.walk(tree):
            name: str | None = None
            required = False
            if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and is_environ(node.value):
                name, required = _text(node.slice), True
            elif isinstance(node, ast.Call) and node.args:
                func = node.func
                if isinstance(func, ast.Name) and func.id == "secret":
                    name, required = _text(node.args[0]), True
                elif (isinstance(func, ast.Name) and func.id in getenvs) or (
                    isinstance(func, ast.Attribute)
                    and (
                        (func.attr == "get" and is_environ(func.value))
                        or (
                            func.attr == "getenv"
                            and isinstance(func.value, ast.Name)
                            and func.value.id in modules
                        )
                    )
                ):
                    name = _text(node.args[0])
            if name:
                reads.append((getattr(node, "lineno", 0), getattr(node, "col_offset", 0), name, required))
        for _, _, name, required in sorted(reads):
            found[name] = found.get(name, False) or required
    return [EnvRead(name, required) for name, required in found.items()]


def env_names(*codes: str | None) -> list[str]:
    return [read.name for read in env_reads(*codes)]


# ===== where each value comes from =====


def parse_sources(value: Any, names: Iterable[str]) -> dict[str, dict[str, str]]:
    """The mapping as sent (`[{"name": "ORDERS_API_KEY", "from": "vault", "vault": "Team vault",
    "secret": "orders-api-key"}, {"name": "ORDERS_URL", "from": "value", "value": "http://..."},
    {"name": "REGION", "from": "env"}, {"name": "TOKEN", "from": "keyring"}]`), checked: variable ->
    its source. Only names the code reads. A keyring value is never part of it (it goes to the keyring)."""
    if value is None:
        return {}
    if not isinstance(value, list) or len(value) > MAX_VARIABLES:
        raise PythonConnectionError(
            'The variables are a list: [{"name": "ORDERS_API_KEY", "from": "vault", "vault": "...", '
            '"secret": "..."}].'
        )
    read = set(names)
    sources: dict[str, dict[str, str]] = {}
    for row in value:
        if not isinstance(row, dict):
            raise PythonConnectionError('Each variable is {"name": "ORDERS_API_KEY", "from": "env"}.')
        name, origin = row.get("name"), row.get("from")
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise PythonConnectionError(
                f"{name!r} is not an environment variable name. Use letters, digits and '_', not "
                "starting with a digit (ORDERS_API_KEY)."
            )
        if name not in read:
            raise PythonConnectionError(f"The code never reads {name}.")
        if name in sources:
            raise PythonConnectionError(f"{name} is given twice.")
        if origin not in SOURCES:
            raise PythonConnectionError(
                f'{name} comes "from" env (this computer\'s environment), keyring (saved on this '
                "computer), vault (a key vault's secret) or value (a plain value, not a secret)."
            )
        source = {"from": str(origin)}
        if origin == "vault":
            vault, secret = row.get("vault"), row.get("secret")
            if not isinstance(vault, str) or not vault.strip() or len(vault) > 64:
                raise PythonConnectionError(f"Name the key vault {name} comes from.")
            if not isinstance(secret, str) or not secret.strip() or len(secret) > 500:
                raise PythonConnectionError(f"Name the secret in {vault.strip()} that {name} is.")
            source |= {"vault": vault.strip(), "secret": secret.strip()}
        elif origin == "value":
            plain = row.get("value")
            if not isinstance(plain, str) or len(plain) > 10_000 or "\x00" in plain:
                raise PythonConnectionError(f"{name}'s value is text (at most 10,000 characters).")
            source["value"] = plain
        sources[name] = source
    return sources


def sources_json(sources: Mapping[str, Mapping[str, str]]) -> list[dict[str, str]]:
    return [{"name": name, **source} for name, source in sources.items()]


def keyring_names(sources: Mapping[str, Mapping[str, str]]) -> list[str]:
    return [name for name, source in sources.items() if source.get("from") == "keyring"]


def plain_values(sources: Mapping[str, Mapping[str, str]]) -> dict[str, str]:
    """The variables given a plain value (not secrets): set as they are before the code runs."""
    return {n: s.get("value", "") for n, s in sources.items() if s.get("from") == "value"}


def vault_jobs(
    sources: Mapping[str, Mapping[str, str]],
    vault: Callable[[str], Any],
    saved: Callable[[Any], dict[str, str]],
) -> list[dict[str, Any]]:
    """The vaults to run before the code, each with only the entries this connection maps: variable ->
    the secret's name in that vault. `vault` finds a vault blade by name (KeyError: gone); `saved` gives
    a vault's own saved passwords. The same shape as every vault a run starts with."""
    wanted: dict[str, dict[str, str]] = {}
    for name, source in sources.items():
        if source.get("from") == "vault":
            wanted.setdefault(str(source["vault"]), {})[name] = str(source["secret"])
    jobs = []
    for vault_name, mapping in wanted.items():
        try:
            blade = vault(vault_name)
        except KeyError:
            blade = None
        if blade is None or blade.kind != "vault":
            raise PythonConnectionError(
                f"{', '.join(mapping)} come{'s' if len(mapping) == 1 else ''} from the key vault "
                f"{vault_name}, which is not among the connections. Choose another source."
            )
        jobs.append(
            {
                "label": blade.name,
                "code": blade.code,
                "variable": blade.variable,
                "mapping": mapping,
                "every": False,
                "secrets": saved(blade),
            }
        )
    return jobs


def fill(blade: Any, data: Mapping[str, Any], previous: Any, check_python: Callable[[str, str], Any]) -> None:
    """A blade being saved as a connection from the user's own Python (domain/blades.py parse_blade):
    its Read a table box and where each variable its three boxes read comes from, checked. A save that
    names neither (the blades page's editor, which shows only the code and the catalog) keeps what the
    connection had, and its Rows to open."""
    if blade.catalog_language == "sql":
        raise PythonConnectionError("List the tables is Python: it returns the tables of what Connect made.")
    same = previous is not None and previous.template == blade.template
    if same and "row_limit" not in data:
        blade.row_limit = previous.row_limit
    read = data.get("read", previous.read_command if same else None)
    command = read.get("command") if isinstance(read, Mapping) else read
    if command is not None and not isinstance(command, str):
        raise PythonConnectionError(
            'Read a table is {"command": "..."}: Python that returns a table\'s rows.'
        )
    blade.read_command = None
    if command and command.strip():
        if len(command) > MAX_CODE_CHARS:
            raise PythonConnectionError("Read a table is too long.")
        check_python(command, "Read a table")
        blade.read_command = command
    names = env_names(blade.code, blade.catalog_command, blade.read_command)
    if "variables" in data or not same:
        blade.variables = parse_sources(data.get("variables"), names)
    else:
        blade.variables = {n: dict(source) for n, source in previous.variables.items() if n in names}


def missing(reads: Iterable[EnvRead], present: Callable[[str], bool]) -> list[str]:
    """The variables the code cannot run without (`os.environ["X"]`, `secret("X")`) that have no value."""
    return [read.name for read in reads if read.required and not present(read.name)]


def missing_message(names: list[str], label: str) -> str:
    one = len(names) == 1
    return (
        f"{label} reads {', '.join(names)}, which {'has' if one else 'have'} no value: choose where "
        f"{'it comes' if one else 'they come'} from under Environment variables."
    )


# ===== List the tables: the catalog's shape =====

CATALOG_SHAPE: str = "a list of dicts or a DataFrame: table, column; optionally schema, type, description"
_TABLE_NAMES = ("table", "table_name")
_COLUMN_NAMES = ("column", "column_name")


def check_catalog(columns: list[str], rows: list[list[Any]]) -> tuple[list[str], list[list[Any]]]:
    """What List the tables returned, as a catalog's rows: one row per column of the source, with a
    table and a column on every row. The loader reads the rest (schema, type, description; an
    INFORMATION_SCHEMA result's names work too)."""
    if not columns and not rows:
        raise PythonConnectionError(
            "List the tables returned no rows: one row for each column of each table."
        )
    lowered = [str(c).strip().lower() for c in columns]
    lacking = [
        word
        for word, names in (("table", _TABLE_NAMES), ("column", _COLUMN_NAMES))
        if not any(n in lowered for n in names)
    ]
    if lacking:
        raise PythonConnectionError(
            f"List the tables returns {CATALOG_SHAPE}. This has no {' and no '.join(lacking)}"
            f" (it has: {', '.join(map(str, columns)) or 'no columns'})."
        )
    if not rows:
        raise PythonConnectionError(
            "List the tables returned no rows: one row for each column of each table."
        )
    table_at = next(i for i, c in enumerate(lowered) if c in _TABLE_NAMES)
    column_at = next(i for i, c in enumerate(lowered) if c in _COLUMN_NAMES)
    for at, row in enumerate(rows, start=1):
        for index, word in ((table_at, "table"), (column_at, "column")):
            cell = row[index] if index < len(row) else None
            if cell is None or not str(cell).strip():
                raise PythonConnectionError(f"List the tables: row {at} has no {word}.")
    return [str(c) for c in columns], rows


def first_table(columns: list[str], rows: list[list[Any]]) -> tuple[str, str]:
    """The first table the catalog names, as (schema, table): what Test reads."""
    lowered = [str(c).strip().lower() for c in columns]
    table_at = next(i for i, c in enumerate(lowered) if c in _TABLE_NAMES)
    schema_at = next((i for i, c in enumerate(lowered) if c in ("schema", "table_schema")), None)
    row = rows[0]
    schema = row[schema_at] if schema_at is not None and schema_at < len(row) else None
    return ("" if schema is None else str(schema), str(row[table_at]))


def table_count(columns: list[str], rows: list[list[Any]]) -> int:
    lowered = [str(c).strip().lower() for c in columns]
    table_at = next(i for i, c in enumerate(lowered) if c in _TABLE_NAMES)
    schema_at = next((i for i, c in enumerate(lowered) if c in ("schema", "table_schema")), None)
    return len({(row[schema_at] if schema_at is not None else None, row[table_at]) for row in rows})


# ===== Read a table: what it returned =====

READ_SHAPE: str = "a DataFrame, an Arrow table or a list of dicts; or (rows, total)"


def split_read(result: Any) -> tuple[Any, int | None]:
    """What Read a table returned, as (the rows, how many the source holds or None): `(rows, total)`
    is told from rows by its second part, a whole number (or None)."""
    if (
        isinstance(result, tuple)
        and len(result) == 2
        and (result[1] is None or (isinstance(result[1], int) and not isinstance(result[1], bool)))
    ):
        total = result[1]
        if total is not None and total < 0:
            raise PythonConnectionError("Read a table returned a total below zero.")
        return result[0], total
    return result, None


def read_total(returned: int, limit: int | None, total: int | None) -> tuple[int, int | None]:
    """How many rows to keep and how many the source holds. Code that ignored the limit returned every
    row: the first `limit` are kept and the count is known. A total smaller than the rows is theirs."""
    kept = returned if limit is None else min(returned, limit)
    if total is None and limit is not None and returned > limit:
        total = returned
    if total is not None and total < kept:
        total = kept
    return kept, total


def read_call(connection: str, schema: str, table: str) -> str:
    """The Python that reads the table again in a notebook: sab.read('Orders API', 'orders')."""
    where = f", schema={schema!r}" if schema else ""
    return f"sab.read({connection!r}, {table!r}{where})"


def tables_json(columns: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    """What List the tables returned, table by table: [{"schema", "table", "columns": [{"column",
    "type", "description"}]}], in the order it named them (the agent's answer; the tree reads the
    loaded catalog)."""
    at = {str(c).strip().lower(): i for i, c in reversed(list(enumerate(columns)))}

    def cell(row: list[Any], *names: str) -> str:
        index = next((at[n] for n in names if n in at), None)
        value = row[index] if index is not None and index < len(row) else None
        return "" if value is None else str(value)

    tables: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        schema, table = cell(row, "schema", "table_schema"), cell(row, *_TABLE_NAMES)
        entry = tables.setdefault((schema, table), {"schema": schema, "table": table, "columns": []})
        entry["columns"].append(
            {
                "column": cell(row, *_COLUMN_NAMES),
                "type": cell(row, "type", "data_type"),
                "description": cell(row, "description", "comment"),
            }
        )
    return list(tables.values())
