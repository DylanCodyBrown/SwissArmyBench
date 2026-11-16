"""Connections: the blades that reach a source of tables or passwords, seen and managed apart from blades.

A connection is a database blade (kind `sql`: its code makes a connection, its dialect says whose SQL),
a file blade (made from a file starter: a CSV, a workbook, a Parquet or JSON file, a folder of them;
its code makes the path) or a key vault (kind `vault`: its code reads a secret by name; each secret it
maps becomes an environment variable in every Workbench kernel, the owner's call, 2026-11-14) or the
user's own Python (kind `other`, the `python` starter: three boxes that connect, list the tables and
read one; domain/python_connections.py). They
live in the blade store (one store: secrets, vaults, catalogs,
folders, packs and the portable file all work the same); what this module decides is which blades are
connections, what kind each is, and how a starter becomes the Add connection form. Pure rules: no I/O.
"""

from __future__ import annotations

import builtins
import re
import unicodedata
from typing import Any

from swissarmybench.domain import python_connections
from swissarmybench.domain.blades import env_name_for_secret

__all__ = ["env_name_for_secret"]  # with the rules below: a vault's secret as a variable

# The file starters (server/blade_templates.py FILES): a blade made from one is a file connection.
FILE_STARTERS: dict[str, str] = {
    "csv": "CSV file",
    "excel": "Workbook",
    "parquet": "Parquet file",
    "json": "JSON file",
    "folder": "Folder of files",
}
# A setting with one of these names holds a path the form offers a picker for.
_FILE_SETTINGS = frozenset({"path", "file", "dbq", "database_file", "certificate file"})
_FOLDER_SETTINGS = frozenset({"folder", "directory"})


def connection_kind(kind: str, template: str | None) -> str | None:
    """The connection a blade is: database, file, vault, python (the user's own code: three boxes), or
    None (a secret, an analysis, other code)."""
    if kind == "other" and template == python_connections.TEMPLATE:
        return "python"
    if kind == "sql":
        return "database"
    if kind == "vault":
        return "vault"
    if kind == "other" and template in FILE_STARTERS:
        return "file"
    return None


def is_connection(kind: str, template: str | None) -> bool:
    return connection_kind(kind, template) is not None


# Code that signs in by asking the person (a browser window, a phone prompt): its catalog is never
# loaded unasked at start-up, only on first use (the owner, 2026-11-14: no sign-in window out of nowhere).
_INTERACTIVE = re.compile(
    r"ActiveDirectoryInteractive|externalbrowser|InteractiveBrowserCredential|DeviceCodeCredential"
    r"|exclude_interactive_browser_credential\s*=\s*False",  # DefaultAzureCredential with a browser
    re.IGNORECASE,
)


def signs_in_interactively(code: str) -> bool:
    """Whether the code's sign-in asks the person (MFA in a browser, a device code)."""
    return bool(_INTERACTIVE.search(code))


def has_catalog(connection: str | None) -> bool:
    """A database, file or own-Python connection lists its tables (a vault has none)."""
    return connection in ("database", "file", "python")


def opens_in_code(connection: str | None) -> bool:
    """Whether the connection is a variable in the Workbench and a SQL cell's source: a database or a
    file, or what the user's own Python makes. A vault is not: its secrets are already environment
    variables there."""
    return connection in ("database", "file", "python")


def picker(setting: dict[str, Any], template: str | None) -> str | None:
    """Which picker the form offers for this setting: file, folder, or None (typed)."""
    name, key = str(setting.get("name", "")).lower(), str(setting.get("key", "")).lower()
    if name in _FOLDER_SETTINGS or (template == "folder" and name in _FILE_SETTINGS):
        return "folder"
    if name in _FILE_SETTINGS or key in _FILE_SETTINGS:
        return "file"
    return None


# ===== a form's order (the owner's decision 14): the same on every database form =====
#
# Where it is (server, port, catalog or database, then anything else the code asks for), then who signs
# in (the user; the form puts the password beside it), then how the connection is secured (encrypt, the
# certificate file and Trust server certificate together). The code's own order differs from starter
# to starter (Trino's begins with the user), so the form does not follow it.

_PLACES: dict[str, tuple[str, int]] = {
    "server": ("where", 0),
    "host": ("where", 0),
    "account": ("where", 0),
    "project": ("where", 0),
    "data source": ("where", 0),
    "path": ("where", 0),
    "port": ("where", 1),
    "catalog": ("where", 2),
    "database": ("where", 3),
    "user": ("who", 0),
    "encrypt": ("security", 0),
    "certificate file": ("security", 1),
    "trust server certificate": ("security", 2),
}
_OTHER = ("where", 9)  # a setting the rule does not name: after the database, in the code's order


def field_places() -> dict[str, dict[str, Any]]:
    """Each setting the rule names: its part of the form (where, who or security) and its rank there.
    The form uses it for settings that arrive later (another way to sign in brings a user)."""
    return {name: {"part": part, "rank": rank} for name, (part, rank) in _PLACES.items()}


def form_order(names: list[str]) -> dict[str, list[str]]:
    """A form's settings (in the code's order) as the form shows them: {"where", "who", "security"}."""
    parts: dict[str, list[tuple[int, int, str]]] = {"where": [], "who": [], "security": []}
    for at, name in enumerate(names):
        part, rank = _PLACES.get(name.lower(), _OTHER)
        parts[part].append((rank, at, name))
    return {part: [name for _, _, name in sorted(found)] for part, found in parts.items()}


def form(template: dict[str, Any], inspected: dict[str, Any]) -> dict[str, Any]:
    """A starter as the Add connection form: its fields (the code's settings, a picker where one is a
    path), its passwords (the code's secret names), and the code they are written into."""
    fields = [
        {**setting, "picker": picker(setting, template.get("id"))}
        for setting in inspected.get("settings", [])
    ]
    return {
        "id": template["id"],
        "label": template["label"],
        "group": template["group"],
        "connection": connection_kind(str(template["kind"]), str(template["id"])),
        "kind": template["kind"],
        "dialect": template.get("dialect", "other"),
        "variable": template["variable"],
        "catalog": template.get("catalog"),
        "note": template.get("note", ""),
        "code": template["code"],
        "fields": fields,
        "field_order": form_order([str(f.get("name", "")) for f in fields]),
        "field_places": field_places(),
        "secrets": list(inspected.get("secrets", [])),
        "packages": inspected.get("packages", []),
        "install_here": inspected.get("install_here"),
        "vault_mapping": list(template.get("vault_mapping") or []),
        "vault_all": bool(template.get("vault_all")),
        # Ways to sign in, each its own code (SQL Server, Azure SQL): the form's Sign in.
        "sign_ins": list(template.get("sign_ins") or []),
        # Where a new one's passwords are first offered from ("vault": the Power BI dataset's way).
        "secrets_from": str(template.get("secrets_from") or ""),
        # A saved one's Rows to open (a database, the user's own Python); none: the app's 10,000.
        "row_limit": template.get("row_limit"),
        # The user's own Python: its Read a table box, and where each variable it reads comes from.
        "read": template.get("read"),
        "variables": list(template.get("variables") or []),
    }


# ===== where a password comes from =====

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def check_env_name(name: Any) -> str:
    """An environment variable's name, as a password's source (WAREHOUSE_PASSWORD)."""
    if not isinstance(name, str) or not _ENV_NAME.match(name.strip()):
        raise ValueError(
            "An environment variable's name is letters, digits and _, not starting with a digit."
        )
    return name.strip()


def env_name_for(connection: str, secret: str) -> str:
    """A variable's name for a connection's password: Sales DB, password -> SALES_DB_PASSWORD."""
    words = re.sub(r"[^A-Za-z0-9]+", "_", f"{connection}_{secret}").strip("_").upper()
    return words if words and not words[0].isdigit() else f"_{words}"


MAX_VAULT_NAMES: int = 5_000

# Rows a database table opens with as a grid, unless its connection says otherwise (Rows to open):
# the grid then says how many the source holds and offers the rest.
DEFAULT_OPEN_ROWS: int = 10_000
PREVIEW_ROWS: int = 50  # the catalog page's preview of a table, beside its columns
TEST_ROWS: int = 20  # a file connection's Test: its columns and this many of its first rows


def name_from_path(path: str) -> str:
    """A file connection's name when none was typed: its file's name without the kind, or a folder's
    own name (C:\\data\\Orders 2026.csv -> Orders 2026). Empty for no path."""
    last = next((part for part in reversed(re.split(r"[\\/]", path.strip())) if part), "")
    return re.sub(r"\.[A-Za-z0-9]{1,8}$", "", last)[:64].strip()


def file_setting(settings: list[dict[str, Any]], template: str | None) -> str:
    """The path a file connection's form holds (its file or folder setting), once one is filled in."""
    for setting in settings:
        if picker(setting, template) and not setting.get("placeholder"):
            return str(setting.get("value") or "")
    return ""


def dataset_name(text: str) -> str:
    """A table's name as a dataset's: dbo.Order Lines -> Order_Lines (letters, digits, _ and -)."""
    bare = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", text.strip())  # orders.csv -> orders
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", bare).strip("_")[:64]
    return name or "table"


def table_grid_name(name: str, connection: str, open_from: str | None) -> str:
    """A connection's table as a grid: its own name (`name`, already a dataset's), unless a table of
    that name is open from somewhere else (another connection, a file, Python; `open_from` names where,
    "" when not a connection, None when none is open): then the connection's name before it
    (Warehouse_customers), so the open one is not replaced under its grid. A Power BI workspace's
    tables say `Finance/Sales model`: the workspace is the connection."""
    if open_from is None or open_from.partition("/")[0] == connection:
        return name
    return dataset_name(f"{connection} {name}")


def file_to_open(template: str | None, path: str, table: str) -> tuple[str, str | None]:
    """Which file (and sheet) a file connection's catalog table is: a CSV, Parquet or JSON connection is
    its one file; a workbook's tables are its sheets; a folder's are its files."""
    if template == "folder":
        if not table or "/" in table or "\\" in table or table in (".", ".."):
            raise ValueError("Name the file in the folder to open.")
        separator = "\\" if "\\" in path and "/" not in path else "/"
        return path.rstrip("/\\") + separator + table, None
    if template == "excel":
        return path, table or None
    return path, None


def vault_names(found: Any) -> list[dict[str, str]]:
    """What a vault's names() gave, as rows to map: each secret's name and a variable for it. Sorted,
    each once, at most five thousand (a name is not a secret; no value is read)."""
    if not isinstance(found, list):
        return []
    names = sorted({str(n) for n in found if isinstance(n, str | int) and str(n).strip()}, key=str.casefold)
    return [{"secret": n, "env": env_name_for_secret(n)} for n in names[:MAX_VAULT_NAMES]]


def rename_secret(code: str, old: str, new: str) -> str:
    """The code with every secret("old") asking for secret("new") instead: the value then comes from the
    keyring saved under that name, or else the environment variable of that name (a vault sets it)."""
    pattern = re.compile(r"""(\bsecret\(\s*)(["'])""" + re.escape(old) + r"""\2(\s*\))""")
    changed, count = pattern.subn(lambda m: f"{m.group(1)}{m.group(2)}{new}{m.group(2)}{m.group(3)}", code)
    if not count:
        raise ValueError(f'The code does not ask for secret("{old}").')
    return changed


# ===== each connection's name in code (the Workbench: every connection, always there) =====


def code_names(names: list[str]) -> dict[str, str]:
    """Each connection's variable in a Workbench notebook or script: lower case, words joined by _, a
    Python name (Sales DB -> sales_db, 2024 Budget -> c_2024_budget, class -> class_), unique (orders,
    orders_2). In the order given; the first to claim a name keeps it."""
    taken: set[str] = set()
    out: dict[str, str] = {}
    for name in names:
        plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()  # Café -> Cafe
        base = re.sub(r"[^0-9a-zA-Z]+", "_", plain).strip("_").lower() or "connection"
        if base[0].isdigit():
            base = f"c_{base}"
        if base in _PYTHON_WORDS:
            base += "_"
        chosen, n = base, 2
        while chosen in taken:
            chosen, n = f"{base}_{n}", n + 1
        taken.add(chosen)
        out[name] = chosen
    return out


# Never a connection's name in code: Python's words, its built-ins (a connection named Print or List must
# not hide print or list in every kernel), and the names every notebook leans on.
_PYTHON_WORDS = (
    frozenset(
        "False None True and as assert async await break class continue def del elif else except finally for "
        "from global if import in is lambda nonlocal not or pass raise return try while with yield".split()
    )
    | frozenset(name.lower() for name in dir(builtins))
    | frozenset(
        {"sab", "sag", "pd", "np", "plt", "df", "display", "get_ipython", "in", "out"}
    )  # sag: the old alias
)
