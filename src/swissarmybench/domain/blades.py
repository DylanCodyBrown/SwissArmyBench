"""Blades: saved Python that reaches outside Python to load something (plan decisions 14-16).

A database connection, an API client, a CSV path, a workbook: any code that loads from outside is a
blade. It is written once, saved by the server, and run wherever it is needed: `sab.blade("name")` runs
it in the caller's Python and returns its variable; the server's Refresh runs it in a child process to
load the blade's catalog.

Everything here is about a blade as text and as a record; nothing is run, read from disk or looked up.
Standard library only, so the plain client can use it. In this order:

  the code       what a blade's code makes, asks for and imports (read with `ast`, never run)
  the packages   the pip packages its imports need (named in domain/packages.py)
  the file       the portable `.blade.py` file: a `# /// swissarmybench-blade` TOML header, and zips
  the settings   the values each person fills in: found with `ast`, placeholders, suggestions, written back
  the blade      the saved record (`Blade`) and the check every save goes through (`parse_blade`)

Running a blade is adapters/blade_run.py; keeping blades and their secrets is adapters/blades.py; the
starter templates are server/blade_templates.py.
"""

from __future__ import annotations

import ast
import io
import json
import re
import tomllib
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from swissarmybench.domain import connection_slots as slot_rules
from swissarmybench.domain import python_connections, snippets, web_calls
from swissarmybench.domain.blade_settings import CONNECTION_KEYS as CONNECTION_KEYS
from swissarmybench.domain.blade_settings import FLAGS as FLAGS
from swissarmybench.domain.blade_settings import KEYWORDS as KEYWORDS
from swissarmybench.domain.blade_settings import BladeCodeError as BladeCodeError
from swissarmybench.domain.blade_settings import FillError as FillError
from swissarmybench.domain.blade_settings import Setting as Setting
from swissarmybench.domain.blade_settings import apply_settings as apply_settings
from swissarmybench.domain.blade_settings import detect_settings as detect_settings
from swissarmybench.domain.blade_settings import env_settings as env_settings
from swissarmybench.domain.blade_settings import is_placeholder as is_placeholder
from swissarmybench.domain.blade_settings import parse_code as parse_code
from swissarmybench.domain.blade_templates import CROSS_LISTED as CROSS_LISTED
from swissarmybench.domain.blade_templates import FAMILIES as FAMILIES
from swissarmybench.domain.blade_templates import STARTERS as STARTERS
from swissarmybench.domain.blade_templates import Template as Template
from swissarmybench.domain.catalogs import CatalogError, check_name, normalize_dialect
from swissarmybench.domain.packages import CALL_NEEDS as CALL_NEEDS
from swissarmybench.domain.packages import PIP_NAMES as PIP_NAMES
from swissarmybench.domain.packages import Package as Package
from swissarmybench.domain.packages import install_command as install_command
from swissarmybench.domain.packages import missing_module_hint as missing_module_hint
from swissarmybench.domain.packages import pip_name as pip_name
from swissarmybench.domain.packages import provided as provided
from swissarmybench.domain.variable_refs import env_name_for_secret as env_name_for_secret
from swissarmybench.domain.variable_refs import every_secret as every_secret

# ===== the code =====
# What a blade's code makes, asks for and imports, read with `ast` and never run.
#
# - The variable: the last name the code assigns at its top level (`conn = pyodbc.connect(...)`), so a
#   highlighted snippet needs no editing to become a blade. The save screen shows it and lets it change.
# - The secrets: every `secret("name")` call with a literal name. Their values live in the operating
#   system's vault, never in the code.
# - The imports: top-level module names, for the package check (below) and for adding imports to
#   a script the blade is dropped into.


@dataclass(frozen=True)
class BladeCode:
    variable: str | None
    assigned: list[str] = field(default_factory=list)  # every top-level name, in order
    secrets: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)  # dotted module names as written
    calls: list[str] = field(default_factory=list)  # attribute and function names called (read_excel, ...)


def _targets(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Tuple | ast.List):
        return [name for element in node.elts for name in _targets(element)]
    if isinstance(node, ast.Starred):
        return _targets(node.value)
    return []


def _top_level_names(statements: list[ast.stmt]) -> list[str]:
    names: list[str] = []
    for statement in statements:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                names.extend(_targets(target))
        elif isinstance(statement, ast.AnnAssign | ast.AugAssign) and statement.value is not None:
            names.extend(_targets(statement.target))
        elif isinstance(statement, ast.With | ast.AsyncWith):
            for item in statement.items:
                if item.optional_vars is not None:
                    names.extend(_targets(item.optional_vars))
            names.extend(_top_level_names(statement.body))
        elif isinstance(statement, ast.If | ast.Try):
            # A blade may pick a driver or a path in an if or try; what it assigns there still counts.
            for block in (
                statement.body,
                getattr(statement, "orelse", []),
                getattr(statement, "finalbody", []),
            ):
                names.extend(_top_level_names(block))
            for handler in getattr(statement, "handlers", []):
                names.extend(_top_level_names(handler.body))
        elif isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.append(statement.name)
    return names


def read_code(code: str, label: str = "the blade") -> BladeCode:
    """What the code makes, asks for and imports. Kept by the text (a listing reads every blade's code each
    time, ast's walk the most of its cost); each call gets lists of its own."""
    found = _read_code(code, label)
    return BladeCode(
        found.variable, list(found.assigned), list(found.secrets), list(found.imports), list(found.calls)
    )


@lru_cache(maxsize=2048)
def _read_code(code: str, label: str) -> BladeCode:
    tree = parse_code(code, label)
    assigned = _top_level_names(tree.body)
    imported_names: set[str] = set()
    imports: list[str] = []
    secrets: list[str] = []
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
                imported_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.append(node.module)
            imported_names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name:
                calls.append(name)
            if (
                isinstance(func, ast.Name)
                and func.id == "secret"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                secrets.append(node.args[0].value)
    # The variable is the last thing the code made, a value or a function (a vault's `get`), never a
    # module it imported.
    values = [n for n in assigned if n not in imported_names and not n.startswith("_")]
    return BladeCode(
        variable=values[-1] if values else None,
        assigned=list(dict.fromkeys(assigned)),
        secrets=list(dict.fromkeys(secrets)),
        imports=list(dict.fromkeys(imports)),
        calls=list(dict.fromkeys(calls)),
    )


def _function_params(code: str, name: str) -> int | None:
    """How many positional arguments the top-level function `name` takes; None when it is not one."""
    for statement in parse_code(code).body:
        if isinstance(statement, ast.FunctionDef) and statement.name == name:
            args = statement.args
            return len(args.posonlyargs) + len(args.args)
    return None


def import_lines(code: str) -> list[str]:
    """The code's top-level import statements, as written (for adding to a script's top)."""
    return list(_import_lines(code))


@lru_cache(maxsize=1024)
def _import_lines(code: str) -> tuple[str, ...]:
    tree = parse_code(code)
    lines = code.splitlines()
    found: list[str] = []
    for statement in tree.body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            end = statement.end_lineno or statement.lineno
            found.append("\n".join(lines[statement.lineno - 1 : end]))
    return tuple(found)


def needed(code: str, installed: Callable[[str], bool]) -> list[Package]:
    """Every package the blade needs, whether installed or not (`installed` answers for one module:
    adapters/blade_run.py asks this Python), in the order the code uses them."""
    found = read_code(code)
    packages: dict[str, Package] = {}
    for dotted in found.imports:
        if provided(dotted):
            continue
        pip, guessed = pip_name(dotted)
        if pip not in packages:
            packages[pip] = Package(dotted, pip, guessed, installed(dotted))
    for call in found.calls:
        extra = CALL_NEEDS.get(call)
        if extra and extra not in packages:
            packages[extra] = Package(extra, extra, False, installed(extra))
    return list(packages.values())


# ===== the file =====
# Portable blades: a blade as one plain Python file, `<name>.blade.py`, to share, keep in Git, or import.
#
# The file is the blade's own code under a header comment block, written the way Python's inline script
# metadata is (`# /// <type>` ... `# ///`, each line starting `# `), holding TOML:
#
#     # /// swissarmybench-blade
#     # format = 1
#     # name = "Warehouse"
#     # kind = "sql"
#     # description = "The sales warehouse, read only"
#     # tags = ["sales", "orders-function-app"]
#     # dialect = "sqlserver"
#     # variable = "conn"
#     # secrets = ["password"]
#     #
#     # [catalog]
#     # language = "sql"
#     # command = '''
#     # SELECT ...
#     # '''
#     # ///
#     import pyodbc
#     conn = pyodbc.connect(...)
#
# A vault blade adds `[vault]` (environment variable = secret name); a secret blade lists `env_names` and
# has no code. A connection from your own Python (template "python") keeps its three boxes apart: the
# code is Connect, `[catalog]` is List the tables, `[read]` is Read a table, and `[variables]` says where
# each environment variable comes from (`ORDERS_API_KEY = { from = "vault", vault = "Team vault",
# secret = "orders-api-key" }`; a plain value is written, a secret's never). A file without them loads
# as it always did. Secret values are never written: `secrets` lists only the names the code asks for, which
# the person importing types into their own vault. Several blades travel as a zip of these files.
#
# Reading never runs anything: it parses the header (tomllib) and checks the code is Python (ast).
# Standard library only, so the client can use it too.

FORMAT: int = 1
HEADER_TYPE: str = "swissarmybench-blade"
SUFFIX: str = ".blade.py"
# An analysis blade is the user's own analysis: a function of the grid's rows (a pandas DataFrame, and
# optionally the selected columns) that returns markdown, a table, a figure, or a list or dict of them.
# It shows in the Analyze menu and runs in a child process, like Refresh.
# A snippet is text for a cell, with <<name>> placeholders (domain/snippets.py).
KINDS: tuple[str, ...] = ("sql", "other", "vault", "secret", "analysis", "snippet")
_OPEN = re.compile(r"^# /// (?P<type>[a-zA-Z0-9-]+)$")
_CLOSE: str = "# ///"
_MAX_FILE_BYTES: int = 1_000_000
_MAX_ZIP_ENTRIES: int = 500
_MAX_ZIP_BYTES: int = 50_000_000


class PortableError(ValueError):
    """The file is not a blade, or not one this version reads. The message says why in plain words."""


@dataclass(frozen=True)
class Found:
    """One file offered for import: the blade it holds, or why it holds none."""

    file: str
    blade: dict[str, Any] | None
    error: str | None


# ===== writing =====


def _toml_string(value: str, multiline: bool = False) -> str:
    """A TOML string that reads back exactly. Multi-line text as a literal string ('''...''') when it can
    be (no ''' inside, no control characters but newlines and tabs, no line that would close the
    header); anything else as a basic string, escaped."""
    safe_literal = (
        "'''" not in value
        and not value.endswith("'")
        and all(c in "\n\t" or ord(c) >= 32 for c in value)
        and "\x7f" not in value
        and not any(line.strip() == "///" for line in value.split("\n"))
    )
    if multiline and safe_literal:
        return "'''\n" + value + "'''"
    return json.dumps(value, ensure_ascii=False)


def _header_lines(blade: dict[str, Any]) -> list[str]:
    kind = blade.get("kind", "other")
    lines = [
        f"format = {FORMAT}",
        f"name = {_toml_string(str(blade['name']))}",
        f"kind = {_toml_string(kind)}",
    ]
    if blade.get("description"):
        lines.append(f"description = {_toml_string(str(blade['description']))}")
    if blade.get("tags"):
        lines.append("tags = [" + ", ".join(_toml_string(str(t)) for t in blade["tags"]) + "]")
    if blade.get("family"):
        lines.append(f"family = {_toml_string(str(blade['family']))}")
    if kind == "snippet":
        lines.append(f"language = {_toml_string(str(blade.get('language') or ''))}")
        if blade.get("cell_name"):
            lines.append(f"cell_name = {_toml_string(str(blade['cell_name']))}")
        return lines
    if kind == "sql":
        lines.append(f"dialect = {_toml_string(str(blade.get('dialect') or 'other'))}")
    connection = kind == "sql" or blade.get("template") == python_connections.TEMPLATE
    if blade.get("row_limit") is not None and connection:
        lines.append(f"row_limit = {int(blade['row_limit'])}")
    if kind == "vault" and blade.get("vault_all"):
        lines.append("vault_all = true  # every secret in the vault, each under its own name")
    if kind != "secret":
        lines.append(f"variable = {_toml_string(str(blade.get('variable') or ''))}")
        if kind == "other" and blade.get("table"):
            lines.append(
                f"table = {_toml_string(str(blade['table']))}  # its table's name, wherever it lands"
            )
        try:
            secrets = read_code(str(blade.get("code", ""))).secrets
        except BladeCodeError:
            secrets = []
        if secrets:
            names = ", ".join(_toml_string(s) for s in secrets)
            lines.append(
                f"secrets = [{names}]  # names only: each person types the values into their own vault"
            )
    else:
        names = ", ".join(_toml_string(str(n)) for n in blade.get("env_names", []))
        lines.append(f"env_names = [{names}]  # typed each session, never kept")
    if blade.get("template"):
        lines.append(f"template = {_toml_string(str(blade['template']))}")
    catalog = blade.get("catalog")
    if kind in ("sql", "other") and isinstance(catalog, dict) and catalog.get("command"):
        lines += [
            "",
            "[catalog]",
            f"language = {_toml_string(str(catalog.get('language', 'sql')))}",
            f"command = {_toml_string(str(catalog['command']), multiline=True)}",
        ]
    if kind == "vault" and blade.get("vault_mapping"):
        lines += ["", "[vault]  # environment variable = the secret's name in the vault"]
        for row in blade.get("vault_mapping", []):
            lines.append(f"{row['env']} = {_toml_string(str(row['secret']))}")
    read = blade.get("read")
    if kind == "other" and isinstance(read, dict) and read.get("command"):
        lines += [
            "",
            "[read]  # Read a table: conn, schema, table, limit (None: every row) -> its rows",
            f"command = {_toml_string(str(read['command']), multiline=True)}",
        ]
    if kind == "other" and isinstance(blade.get("web_call"), dict) and blade["web_call"]:
        lines += web_calls.header_lines(blade["web_call"])  # an API's one endpoint, Return as table
    lines += slot_rules.header_lines(blade.get("queries")) if kind in ("sql", "other") else []
    if kind == "other" and blade.get("variables"):
        lines += ["", "[variables]  # environment variable = where its value comes from (no secret's value)"]
        for row in blade["variables"]:
            parts = ", ".join(f"{key} = {_toml_string(str(row[key]))}" for key in row if key != "name")
            lines.append(f"{row['name']} = {{ {parts} }}")
    return lines


def header_block(blade: dict[str, Any]) -> list[str]:
    """The blade's header as its file's lines, from its opening line to its closing one."""
    lines = "\n".join(_header_lines(blade)).split("\n")
    return ["# /// " + HEADER_TYPE, *("# " + line if line else "#" for line in lines), _CLOSE]


def header_span(lines: list[str]) -> tuple[int, int] | None:
    """Where a file's header opens and closes (its lines without their line ends), or None."""
    start = _header_start(lines)
    end = (
        None if start is None else next((i for i in range(start + 1, len(lines)) if lines[i] == _CLOSE), None)
    )
    return None if start is None or end is None else (start, end)


def write_blade(blade: dict[str, Any]) -> str:
    """The blade as its portable file. `blade` is a saved blade's JSON (its `to_json()`)."""
    if blade.get("secrets") and isinstance(blade["secrets"], dict):
        raise PortableError("A portable blade never holds secret values, only their names.")
    header = header_block(blade)
    code = "" if blade.get("kind") == "secret" else str(blade.get("code", ""))
    if blade.get("kind") == "snippet":
        code = snippets.file_body(code)
    return "\n".join(header) + "\n" + code


def file_name(name: str) -> str:
    """A file name for the blade: its name, made safe for every file system."""
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_").lower() or "blade"
    return stem + SUFFIX


# ===== reading =====


def _header_start(lines: list[str]) -> int | None:
    """Where the blade header opens, when it is the file's frontmatter: only blank lines and comments
    (a shebang, an encoding line, a licence) may come before it. A header further down, after code, does
    not count, so an ordinary script that mentions the marker is never taken for a blade."""
    for i, line in enumerate(lines[:200]):
        match = _OPEN.match(line)
        if match and match["type"] == HEADER_TYPE:
            return i
        if line.strip() and not line.lstrip().startswith("#"):
            return None
    return None


def is_blade(text: str) -> bool:
    """True when the text opens with a blade header (the test a blade folder's files must pass)."""
    return _header_start(text.split("\n")) is not None


def read_blade(text: str) -> dict[str, Any]:
    """The blade a portable file holds, ready for the save screen (or BladeStore.save). Nothing runs."""
    lines = text.split("\n")
    start = _header_start(lines)
    if start is None:
        raise PortableError(
            f"This file has no {HEADER_TYPE} header: it is not a blade (export one to see the form)."
        )
    end = next((i for i in range(start + 1, len(lines)) if lines[i] == _CLOSE), None)
    if end is None:
        raise PortableError(
            f"The {HEADER_TYPE} header is never closed: it needs a line that reads '{_CLOSE}'."
        )
    body: list[str] = []
    for line in lines[start + 1 : end]:
        if line == "#":
            body.append("")
        elif line.startswith("# "):
            body.append(line[2:])
        else:
            raise PortableError(f"Every header line starts with '# '; this one does not: {line[:60]!r}")
    try:
        header = tomllib.loads("\n".join(body))
    except tomllib.TOMLDecodeError as error:
        raise PortableError(f"The header is not valid TOML: {error}.") from None
    if header.get("format") != FORMAT:
        raise PortableError(
            f"This blade is in format {header.get('format')!r}; this version reads format {FORMAT}. "
            "Update the grid server to import it."
        )
    name, kind = header.get("name"), header.get("kind")
    if not isinstance(name, str) or not name.strip():
        raise PortableError('The header names no blade: it needs name = "...".')
    if kind not in KINDS:
        raise PortableError(f"The header's kind must be one of {', '.join(KINDS)}, not {kind!r}.")
    code = "\n".join(lines[end + 1 :])
    blade: dict[str, Any] = {"name": name, "kind": kind}
    if kind == "secret":
        names = header.get("env_names")
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise PortableError('A secret blade\'s header lists env_names = ["..."].')
        blade |= {"env_names": names, "code": ""}
    elif kind == "snippet":
        try:
            blade |= snippets.read_file(code, header)
        except snippets.SnippetError as error:
            raise PortableError(str(error)) from None
    else:
        try:
            ast.parse(code, filename=f"{name} (imported)")
        except SyntaxError as error:
            where = f" on line {error.lineno}" if error.lineno else ""
            raise PortableError(f"The blade's code is not valid Python{where}: {error.msg}.") from None
        blade |= {"code": code, "variable": str(header.get("variable") or "")}
        if kind == "other" and isinstance(header.get("table"), str) and header["table"]:
            blade["table"] = header["table"]
        if kind == "sql":
            blade["dialect"] = str(header.get("dialect") or "other")
        if isinstance(header.get("row_limit"), int):
            blade["row_limit"] = header["row_limit"]
        blade |= slot_rules.from_header(header)
        catalog = header.get("catalog")
        if isinstance(catalog, dict) and isinstance(catalog.get("command"), str):
            blade["catalog"] = {
                "language": str(catalog.get("language", "sql")),
                "command": catalog["command"],
            }
        read = header.get("read")
        if isinstance(read, dict) and isinstance(read.get("command"), str):
            blade["read"] = {"command": read["command"]}
        variables = header.get("variables")
        if isinstance(variables, dict):
            if not all(
                isinstance(v, dict) and all(isinstance(part, str) for part in v.values())
                for v in variables.values()
            ):
                raise PortableError(
                    'The [variables] table reads NAME = { from = "vault", vault = "...", secret = "..." }.'
                )
            blade["variables"] = [{"name": name, **source} for name, source in variables.items()]
        blade |= {"web_call": header["web_call"]} if isinstance(header.get("web_call"), dict) else {}
        vault = header.get("vault", {} if header.get("vault_all") is True else None)
        if kind == "vault":
            if not isinstance(vault, dict) or not all(isinstance(v, str) for v in vault.values()):
                raise PortableError('A vault blade\'s header has a [vault] table: VARIABLE = "secret name".')
            blade["vault_mapping"] = [{"env": env, "secret": secret} for env, secret in vault.items()]
            blade["vault_all"] = header.get("vault_all") is True
    template = header.get("template")
    blade["template"] = template if isinstance(template, str) else None
    description = header.get("description")
    if isinstance(description, str) and description:
        blade["description"] = description
    tags = header.get("tags")
    if isinstance(tags, list) and tags:
        blade["tags"] = [str(t) for t in tags if isinstance(t, str)]
    if isinstance(header.get("family"), str) and header["family"]:
        blade["family"] = header["family"]
    return blade


# A blade's table name: a dataset's name (domain/datasets.py), so it opens as a grid as it is.
_TABLE_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
TABLE_NAME_RULE: str = "use 1 to 64 letters, digits, '_' or '-'"


def check_table_name(name: str) -> str:
    """A blade's table name as written, or "" for none; BladeError when no table can have it."""
    if name and not _TABLE_NAME.fullmatch(name):
        raise BladeError(f"not a valid name: {TABLE_NAME_RULE}")
    return name


def _found(file: str, data: bytes) -> Found:
    if len(data) > _MAX_FILE_BYTES:
        return Found(
            file, None, f"{file} is over {_MAX_FILE_BYTES // 1_000_000} MB; a blade is a short file."
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return Found(file, None, f"{file} is not text (UTF-8).")
    try:
        return Found(file, read_blade(text.replace("\r\n", "\n")), None)
    except PortableError as error:
        return Found(file, None, str(error))


def read_blades(files: list[tuple[str, bytes]]) -> list[Found]:
    """Every blade in the files offered: `.blade.py` (or `.py`) files, and zips of them. Zip entries are
    read in memory, never extracted, so a path inside one is only a label."""
    found: list[Found] = []
    for file, data in files:
        if file.lower().endswith(".zip") or data[:4] == b"PK\x03\x04":
            try:
                archive = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                found.append(Found(file, None, f"{file} is not a zip file."))
                continue
            entries = [e for e in archive.infolist() if not e.is_dir() and e.filename.lower().endswith(".py")]
            if len(entries) > _MAX_ZIP_ENTRIES or sum(e.file_size for e in entries) > _MAX_ZIP_BYTES:
                found.append(Found(file, None, f"{file} holds too much to be a set of blades."))
                continue
            for entry in entries:
                if entry.file_size > _MAX_FILE_BYTES:
                    found.append(Found(entry.filename, None, f"{entry.filename} is too large to be a blade."))
                    continue
                found.append(_found(entry.filename, archive.read(entry)))
        else:
            found.append(_found(file, data))
    return found


def write_zip(blades: list[dict[str, Any]]) -> bytes:
    """Several blades as one zip of portable files (names made unique)."""
    buffer = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for blade in blades:
            name = file_name(str(blade["name"]))
            stem, n = name[: -len(SUFFIX)], 2
            while name in used:
                name, n = f"{stem}_{n}{SUFFIX}", n + 1
            used.add(name)
            archive.writestr(name, write_blade(blade))
    return buffer.getvalue()


# ===== suggestions (domain/blade_suggestions.py) =====


def suggest_settings(
    settings: list[Setting],
    others: Iterable[tuple[str, str, str]],
    environ: Mapping[str, str] | None = None,
) -> list[Setting]:
    """Each setting's suggestions: domain/blade_suggestions.py (read when asked: it reads these settings)."""
    from swissarmybench.domain.blade_suggestions import suggest_settings as suggest

    return suggest(settings, others, environ)


# ===== the blade =====

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


_MAX_CODE_CHARS: int = 200_000


class VaultUnavailableError(RuntimeError):
    """This computer has no operating system vault to keep a blade's secrets in."""


class BladeError(ValueError):
    """The blade cannot be saved or used as asked. The message says why in plain words."""


@dataclass
class Blade:
    name: str
    kind: str
    code: str = ""
    variable: str | None = None
    dialect: str = "other"
    catalog_language: str | None = None
    catalog_command: str | None = None
    vault_mapping: dict[str, str] = field(default_factory=dict)  # environment variable -> vault secret name
    # A vault: every secret it holds (read each time), each under its own name; the mapping only renames.
    vault_all: bool = False
    # Rows to open (None: the default); queries at once, the agent's share, the wait (connection_slots.py).
    row_limit: int | None = None
    queries: dict[str, int] = field(default_factory=dict)
    # A connection from the user's own Python (domain/python_connections.py): the Read a table box, and
    # where each environment variable its boxes read comes from (variable -> {"from", ...}).
    read_command: str | None = None
    variables: dict[str, dict[str, str]] = field(default_factory=dict)
    env_names: list[str] = field(default_factory=list)  # a secret blade's variables
    template: str | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    # A snippet's language (dax, html, markdown or streamlit), and the name a Streamlit piece gives its cell.
    language: str = ""
    cell_name: str = ""
    # Its family in the starter pack (Power BI, Excel, Files, DAX, HTML, Streamlit...), kept on a copy.
    family: str = ""
    web_call: dict[str, Any] = field(default_factory=dict)  # a web call blade's (domain/web_calls.py)
    table: str = ""  # its result's table name (domain/blade_tables.py); "": the name its code makes
    path: str | None = None  # a blade folder's file; None for a blade saved in the app
    pack: str | None = None  # STARTERS for the built-in starter pack's (read-only), else None
    created_at: float = 0.0
    updated_at: float = 0.0

    @property
    def secrets(self) -> list[str]:
        """The names its code asks for with secret("..."). A connection from the user's own Python:
        the variables saved on this computer too, and none of those that come from somewhere else."""
        if not self.code or self.kind == "snippet":
            return []
        try:
            found = read_code(self.code, self.name).secrets
        except BladeCodeError:
            found = []
        if not self.variables:
            return found
        kept = python_connections.keyring_names(self.variables)
        return [s for s in found if s not in self.variables] + kept

    @property
    def env_reads(self) -> list[python_connections.EnvRead]:
        """The environment variables a connection from the user's own Python reads, in its three boxes."""
        if self.template != python_connections.TEMPLATE:
            return []
        return python_connections.env_reads(self.code, self.catalog_command, self.read_command)

    @property
    def has_catalog(self) -> bool:
        return bool(self.catalog_language and self.catalog_command)

    @property
    def source(self) -> str:
        """Where it lives: "starter" (the built-in pack), "folder" or "saved"."""
        if self.pack == STARTERS:
            return "starter"
        return "folder" if self.path else "saved"

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "code": self.code,
            "variable": self.variable,
            "dialect": self.dialect,
            "catalog": (
                {"language": self.catalog_language, "command": self.catalog_command}
                if self.has_catalog
                else None
            ),
            "vault_mapping": [{"env": e, "secret": s} for e, s in self.vault_mapping.items()],
            "vault_all": self.vault_all,
            "row_limit": self.row_limit,
            "queries": dict(self.queries) or None,
            "read": {"command": self.read_command} if self.read_command else None,
            "variables": python_connections.sources_json(self.variables),
            "env_names": list(self.env_names),
            "template": self.template,
            "description": self.description,
            "tags": list(self.tags),
            "language": self.language,
            "cell_name": self.cell_name,
            "family": self.family,
            "web_call": dict(self.web_call) or None,
            "table": self.table,
            "path": self.path,
            "pack": self.pack,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _text(data: dict[str, Any], key: str, limit: int = 1_000) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise BladeError(f"{key} must be text.")
    if len(value) > limit:
        raise BladeError(f"{key} is too long ({len(value):,} characters; at most {limit:,}).")
    return value


def _env_name(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _ENV_NAME.fullmatch(value):
        raise BladeError(
            f"{where}: {value!r} is not an environment variable name. Use letters, digits and '_', "
            "not starting with a digit (WAREHOUSE_PASSWORD)."
        )
    return value


_TAG = re.compile(r"[\w][\w .+#-]{0,39}")


def _tags(value: Any) -> list[str]:
    """Tags as typed (trimmed), each 1 to 40 letters, digits, spaces or . + # - _, at most 20, without
    repeats (ignoring case)."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [part for part in value.split(",")]
    if not isinstance(value, list):
        raise BladeError("Tags are a list of words, such as warehouse, finance.")
    tags: dict[str, str] = {}
    for raw in value:
        if not isinstance(raw, str):
            raise BladeError("Each tag is text.")
        tag = " ".join(raw.split())
        if not tag:
            continue
        if not _TAG.fullmatch(tag):
            raise BladeError(f"Tag {tag!r}: use 1 to 40 letters, digits, spaces or . + # - _.")
        tags.setdefault(tag.casefold(), tag)
    if len(tags) > 20:
        raise BladeError("A blade has at most 20 tags.")
    return list(tags.values())


def parse_blade(data: Any, previous: Blade | None = None, now: float = 0.0) -> Blade:
    """A blade from the save screen's JSON, checked. Raises BladeError with a plain message. `now` is
    the time it is saved at (the caller's clock; nothing here reads one)."""
    if not isinstance(data, dict):
        raise BladeError("Send the blade as a JSON object.")
    try:
        name = check_name(_text(data, "name", 64))
    except CatalogError as error:
        raise BladeError(str(error).replace("Catalog name", "Blade name")) from None
    kind = _text(data, "kind", 10)
    if kind not in KINDS:
        raise BladeError(f"A blade's kind is one of {', '.join(KINDS)}, not {kind!r}.")
    blade = Blade(
        name=name,
        kind=kind,
        template=_text(data, "template", 64) or None,
        description=_text(data, "description", 2_000).strip(),
        tags=_tags(data.get("tags")),
        family=_text(data, "family", 40).strip(),
        path=previous.path if previous else None,
        created_at=previous.created_at if previous else now,
        updated_at=now,
    )
    blade.queries = slot_rules.queries_of(data, previous.queries if previous else None, BladeError)
    if kind == "snippet":
        # Text for a cell, with <<name>> placeholders: nothing to run, no variable, no secrets.
        blade.code = _text(data, "code", _MAX_CODE_CHARS).rstrip("\n")
        blade.language = _text(data, "language", 16)
        blade.cell_name = " ".join(_text(data, "cell_name", 120).split())
        try:
            snippets.check(blade.code, blade.language)
        except snippets.SnippetError as error:
            raise BladeError(str(error)) from None
        return blade
    if kind == "secret":
        names = data.get("env_names")
        if not isinstance(names, list) or not names:
            raise BladeError("A secret blade lists at least one environment variable name.")
        blade.env_names = list(dict.fromkeys(_env_name(n, "A secret blade's variable") for n in names))
        if len(blade.env_names) > 100:
            raise BladeError("A secret blade holds at most 100 variables.")
        return blade

    blade.code = _text(data, "code", _MAX_CODE_CHARS)
    if not blade.code.strip():
        raise BladeError(
            "The blade has no code. Paste or write the Python that reaches outside to load something."
        )
    try:
        found = read_code(blade.code, f"Blade {name!r}")
    except BladeCodeError as error:
        raise BladeError(str(error)) from None
    variable = _text(data, "variable", 128).strip() or found.variable
    if not variable:
        raise BladeError(
            "The code makes no variable to hand back. End it with an assignment, such as conn = ..., "
            "or name the variable."
        )
    if variable not in found.assigned:
        raise BladeError(
            f"The code never makes {variable!r}. It makes: {', '.join(found.assigned) or 'nothing'}."
        )
    blade.variable = variable

    if kind == "analysis":
        params = _function_params(blade.code, variable)
        if params is None:
            raise BladeError(
                f"An analysis blade's {variable!r} is a function of the rows: def {variable}(df): ... "
                "(and, if you want them, the selected columns: def analyze(df, columns): ...)."
            )
        if not 1 <= params <= 2:
            raise BladeError(
                f"{variable} takes the rows (df), and optionally the selected columns: 1 or 2 arguments."
            )
        return blade

    if kind == "sql":
        try:
            blade.dialect = normalize_dialect(_text(data, "dialect", 32) or None)
        except CatalogError as error:
            raise BladeError(str(error)) from None
        blade.row_limit = _row_limit(data)

    if kind == "vault":
        mapping = data.get("vault_mapping") or []
        blade.vault_all = data.get("vault_all") is True
        if not isinstance(mapping, list) or not (mapping or blade.vault_all):
            raise BladeError(
                "A vault blade maps at least one secret in the vault to an environment variable, "
                "or loads every secret (vault_all)."
            )
        for row in mapping:
            if not isinstance(row, dict):
                raise BladeError(
                    'Each vault mapping is {"env": "WAREHOUSE_PASSWORD", "secret": "warehouse-pwd"}.'
                )
            env = _env_name(row.get("env"), "A vault mapping's variable")
            secret = row.get("secret")
            if not isinstance(secret, str) or not secret.strip() or len(secret) > 500:
                raise BladeError(f"Name the secret in the vault for {env}.")
            if env in blade.vault_mapping:
                raise BladeError(f"{env} is mapped twice.")
            blade.vault_mapping[env] = secret.strip()
        return blade

    catalog = data.get("catalog")
    if catalog:
        if not isinstance(catalog, dict):
            raise BladeError('The catalog is {"language": "sql" or "python", "command": "..."}.')
        language = _text(catalog, "language", 10)
        command = _text(catalog, "command", _MAX_CODE_CHARS)
        if language not in ("sql", "python"):
            raise BladeError("A catalog command is sql or python.")
        if command.strip():
            if language == "python":
                try:
                    own = blade.template == python_connections.TEMPLATE
                    parse_code(command, "List the tables" if own else "The catalog command")
                except BladeCodeError as error:
                    raise BladeError(str(error)) from None
            blade.catalog_language, blade.catalog_command = language, command
    if kind == "other" and data.get("web_call"):  # a WebCallError is a ValueError: said as one
        blade.web_call = web_calls.check_web_call(data["web_call"])
    if kind == "other" and not blade.web_call:
        blade.table = check_table_name(_text(data, "table", 200).strip())
    if kind == "other" and blade.template == python_connections.TEMPLATE:
        blade.row_limit = _row_limit(data)
        try:  # its Read a table box, and where each variable its three boxes read comes from
            python_connections.fill(blade, data, previous, parse_code)
        except (python_connections.PythonConnectionError, BladeCodeError) as error:
            raise BladeError(str(error)) from None
    return blade


EVERY_ROW = 0  # Rows to open: every row (Load all rows)


def _row_limit(data: dict[str, Any]) -> int | None:
    """Rows to open: rows a table opens with as a grid (None: the default; 0: every row, 2026-11-16)."""
    limit = data.get("row_limit")
    if limit in (None, ""):
        return None
    if isinstance(limit, bool) or not isinstance(limit, int | str) or not str(limit).strip().isdigit():
        raise BladeError("Rows to open is a whole number of rows.")
    if int(limit) != EVERY_ROW and not 1 <= int(limit) <= 50_000_000:
        raise BladeError("Rows to open is between 1 and 50,000,000, or 0 for every row.")
    return int(limit)
