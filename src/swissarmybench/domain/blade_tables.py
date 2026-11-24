"""A blade's table name, and how a connection's tables are listed (the owner, 2026-11-17).

"Shouldnt the table it makes be namable by me with a realtime check for available names": a blade whose
result is a table (a function or code blade that makes a DataFrame) has a table name of its own, kept in
its file's header (`table = "sharepoint_documents"`). Not a connection (its tables are named through the
connection), a vault, a secret, an analysis, a snippet or an API's web call (named through its API).

The name is checked as it is typed, against: a table's name rule (a dataset's: 1 to 64 letters, digits,
'_' or '-'); DuckDB's reserved words; the open tables; every connection's name (its DuckDB SQL name,
`[Sales DB].orders`); and every other blade's table name. DuckDB matches names without case, so these do.

"what the heck does add to catalog do, all blades should be in the catalog already": a connection's tables
are always listed. A connection saved before with no listing query is given its starter's (by its
template, else by its SQL dialect) when it is read: `listing_for`.

What a save may change (the craft review, 2026-11-22): a starter is read-only, a secret blade has no code, a
name is another blade's, and which saved secrets follow a rename (`secrets_after_rename`), one sentence each;
the store's three write paths (adapters/blades.py) ask these.

Standard library only; no I/O.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from swissarmybench.domain.blades import (
    HEADER_TYPE,
    STARTERS,
    TABLE_NAME_RULE,
    Blade,
    BladeCodeError,
    PortableError,
    Template,
    check_table_name,
    header_block,
    header_span,
    read_code,
)
from swissarmybench.domain.blades import BladeError as _BladeError
from swissarmybench.domain.connections import connection_kind

AVAILABLE: str = "available"


def names_table(kind: str, template: str | None, web_call: Mapping[str, object] | None = None) -> bool:
    """Whether a blade's result is a table it names itself: a function or code blade ("other"), not a
    connection and not an API's web call."""
    return kind == "other" and connection_kind(kind, template) is None and not web_call


@dataclass(frozen=True)
class NameCheck:
    """The live check's answer: `available`, and the words shown under the field."""

    name: str
    available: bool
    said: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "available": self.available, "said": self.said}


def check_name(
    name: str,
    *,
    blade: str | None,
    open_tables: Iterable[str],
    connections: Iterable[str],
    blade_tables: Mapping[str, str],
    reserved: Iterable[str],
) -> NameCheck:
    """Whether `name` is free for `blade`'s table (a blade may keep its own). `blade_tables`: each other
    blade's table name, by the blade's name. Answers in plain words: "available", "<name> is already a
    table", "<name> is a connection", "<name> is <blade>'s table", "not a valid name: …"."""
    name = name.strip()
    if not name:
        return NameCheck(name, False, f"not a valid name: {TABLE_NAME_RULE}")
    try:
        check_table_name(name)
    except _BladeError as error:
        return NameCheck(name, False, str(error))
    key = name.casefold()
    if key in {w.casefold() for w in reserved}:
        return NameCheck(name, False, f"not a valid name: {name} is a word DuckDB's SQL keeps for itself")
    mine = (blade or "").casefold()
    for other, table in sorted(blade_tables.items(), key=lambda kv: kv[0].casefold()):
        if other.casefold() != mine and table.casefold() == key:
            return NameCheck(name, False, f"{name} is {other}'s table")
    if key in {c.casefold() for c in connections}:
        return NameCheck(name, False, f"{name} is a connection")
    if key in {t.casefold() for t in open_tables}:
        return NameCheck(name, False, f"{name} is already a table")
    return NameCheck(name, True, AVAILABLE)


def with_header(text: str, blade: Mapping[str, object]) -> str:
    """`text` (a blade's file) with its header written again from `blade` (its JSON): the lines before the
    header and every byte after it (the code, its line ends included) as they were. A blade's code is edited
    in its file, never by the app (the owner, 2026-11-17)."""
    lines = text.splitlines(keepends=True)
    span = header_span([line.rstrip("\r\n") for line in lines])
    if span is None:
        raise PortableError(f"This file has no {HEADER_TYPE} header to change.")
    start, end = span
    newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
    return (
        "".join(lines[:start]) + newline.join(header_block(dict(blade))) + newline + "".join(lines[end + 1 :])
    )


# ===== the blade IDE (the owner, 2026-11-21: "This is an IDE not a save form") =====


def with_code(text: str, code: str) -> str:
    """`text` (a blade's file) with the code after its header replaced by `code`: the lines up to and
    including the header's close as they were, the code in the file's own line ends. A file read and written
    back with its own code is the same bytes (domain/blades.py read_blade reads the code as every line after
    the header's close)."""
    lines = text.splitlines(keepends=True)
    span = header_span([line.rstrip("\r\n") for line in lines])
    if span is None:
        raise PortableError(f"This file has no {HEADER_TYPE} header to keep.")
    start, end = span
    newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
    head = "".join(lines[: end + 1])
    if not head.endswith("\n"):
        head += newline
    body = code.replace("\r\n", "\n")
    return head + (body.replace("\n", "\r\n") if newline == "\r\n" else body)


def follow_variable(code: str, variable: str | None) -> str:
    """The variable a blade hands back once its code is `code`: `variable` while the code still makes it,
    else the last thing the code makes (a function renamed in the editor). Code that does not parse keeps
    `variable` (its run says what is wrong)."""
    try:
        found = read_code(code)
    except BladeCodeError:
        return variable or ""
    if not variable or variable in found.assigned:
        return variable or found.variable or ""
    return found.variable or variable


def stamp(data: bytes) -> str:
    """A file's stamp: its bytes' digest, short. The open editor saves over the file only while its stamp is
    the one it read (an edit made outside, in the user's own editor, is never silently overwritten)."""
    return hashlib.sha256(data).hexdigest()[:16]


def listing_for(
    kind: str, template: str | None, dialect: str, templates: Sequence[Template]
) -> tuple[str, str] | None:
    """The query that lists a connection's tables, from its starter (its template, else the first database
    starter of its dialect): (language, command), or None when it is no connection or has no starter."""
    if connection_kind(kind, template) not in ("database", "file"):
        return None
    by_id = next((t for t in templates if template and t.id == template), None)
    found = by_id if by_id is not None and by_id.catalog_command else None
    if found is None and kind == "sql":
        found = next(
            (t for t in templates if t.kind == "sql" and t.dialect == dialect and t.catalog_command), None
        )
    if found is None or not found.catalog_language or not found.catalog_command:
        return None
    return found.catalog_language, found.catalog_command


def superseded(command: str | None, old: Sequence[str]) -> bool:
    """A saved listing query that is, word for word (line ends and the outer blank space aside), one an
    earlier starter gave: today's starter's lists the tables instead (a Power BI workspace's first 25 datasets
    only: the owner, 2026-11-24). One the user edited is theirs and kept."""
    text = (command or "").replace("\r\n", "\n").strip()
    return bool(text) and any(text == o.replace("\r\n", "\n").strip() for o in old)


def listing_kept(blade: Blade, templates: Sequence[Template], old: Sequence[str]) -> tuple[str, str] | None:
    """The listing query a saved blade is read with instead of its own: its starter's when it has none or its
    own is an earlier starter's word for word (superseded); None keeps its own."""
    if blade.has_catalog and not superseded(blade.catalog_command, old):
        return None
    return listing_for(blade.kind, blade.template, blade.dialect, templates)


# The adapter lists a connection's tables (Plans/adapter.plan.md: "The Catalog lists through the adapter's
# tables()"; a user's edited listing still wins) at its starter's scope, row for row (the same schemas, table
# types, nullability, positions and SQL Server's descriptions and keys: tests/test_catalog_listing.py):
# phase 3 DuckDB, PostgreSQL, SQLite; phase 4 every other dialect the adapter knows (adapter.listed: its
# starter's own listing text in the adapter; a test holds the two the same).
ADAPTER_LISTED: tuple[str, ...] = (
    "duckdb", "postgres", "sqlite", "mysql", "oracle", "snowflake", "sqlserver", "trino", "databricks",
)  # fmt: skip
# A starter whose dialect word is not the adapter's (Databricks' form says "other").
TEMPLATE_DIALECTS: dict[str, str] = {"databricks": "databricks"}


def listed_by_adapter(
    kind: str, template: str | None, dialect: str, language: str | None, command: str | None,
    templates: Sequence[Template],
) -> str:  # fmt: skip
    """The dialect the adapter lists this connection's tables in ("": its own List the tables runs): a
    database the adapter lists as its starter does, whose List the tables the user has not edited (it is its
    starter's, whitespace aside, or empty)."""
    dialect = TEMPLATE_DIALECTS.get(template or "", dialect)
    if dialect not in ADAPTER_LISTED:
        return ""
    starter = listing_for(kind, template, dialect, templates)
    if starter is None:
        return ""
    if command and (language != starter[0] or " ".join(command.split()) != " ".join(starter[1].split())):
        return ""  # the user's own listing: theirs runs
    return dialect


# ===== New blade: the templates the user picks from (the left panel's New blade) =====

# A blade made from one is a file in the library's blades/ folder, edited in the blade IDE (or its file).
NEW_TABLE_CODE: str = '''"""A table: a function that returns a DataFrame."""

import pandas as pd


def make_table() -> pd.DataFrame:
    return pd.DataFrame({"id": [1, 2, 3], "name": ["Ada", "Bea", "Cy"]})
'''


NEW_CODE: str = '"""Any code: what it makes last is what sab.blade gives."""\n\nvalue = 1\n'


@dataclass(frozen=True)
class NewBlade:
    """One choice under New blade: its id, its words, and what the file starts as."""

    id: str
    label: str
    group: str
    kind: str
    code: str = ""
    variable: str = ""
    language: str = ""
    env_names: tuple[str, ...] = ()
    named: str = ""  # its first name (a blade's name rule: no parentheses or colons)

    def to_json(self) -> dict[str, object]:
        return {"id": self.id, "label": self.label, "group": self.group, "kind": self.kind}

    def data(self, name: str, table: str = "") -> dict[str, object]:
        """The new blade's JSON (domain/blades.py parse_blade reads it)."""
        made: dict[str, object] = {"name": name, "kind": self.kind, "template": None}
        if self.kind == "secret":
            return made | {"env_names": list(self.env_names)}
        if self.kind == "snippet":
            return made | {"code": self.code, "language": self.language}
        made |= {"code": self.code, "variable": self.variable}
        return made | ({"table": table} if table and self.kind == "other" else {})


NEW_BLADES: tuple[NewBlade, ...] = (
    NewBlade(
        "table", "A table (a DataFrame)", "Blades", "other", NEW_TABLE_CODE, "make_table", named="New table"
    ),
    NewBlade("code", "Any code", "Blades", "other", NEW_CODE, "value", named="New blade"),
    NewBlade("secret", "Secret blade", "Blades", "secret", env_names=("MY_VARIABLE",), named="New secret"),
    NewBlade(
        "snippet",
        "Snippet (Markdown)",
        "Blades",
        "snippet",
        "## <<title>>\n",
        language="markdown",
        named="New snippet",
    ),
)


def new_blade(choice: str, templates: Sequence[Template]) -> NewBlade:
    """The New blade choice `choice`: one of NEW_BLADES, or an analysis starter (its id)."""
    for made in NEW_BLADES:
        if made.id == choice:
            return made
    for t in templates:
        if t.id == choice and t.kind == "analysis":
            return NewBlade(t.id, t.label, t.group, "analysis", t.code, t.variable, named=_safe(t.label))
    offered = ", ".join([*(m.id for m in NEW_BLADES), *(t.id for t in templates if t.kind == "analysis")])
    raise _BladeError(f"New blade makes one of: {offered}. A connection is added on the Connections page.")


def _safe(label: str) -> str:
    """A label as a blade's name: what a name may not hold left out ("Pareto: which values make 80%")."""
    return " ".join(re.sub(r"[^A-Za-z0-9 _.-]+", " ", label).split())[:64] or "New blade"


def new_blades(templates: Sequence[Template]) -> list[dict[str, object]]:
    """What New blade offers: NEW_BLADES, then the analysis starters."""
    analyses = [NewBlade(t.id, t.label, t.group, "analysis") for t in templates if t.kind == "analysis"]
    return [m.to_json() for m in [*NEW_BLADES, *analyses]]


# What a blade's code is given before it runs (adapters/blade_run.py's secret()), told to the lint so it is
# never an undefined name.
SECRET_STUB: str = "def secret(name: str) -> str: ...\n"  # noqa: S105 (a stub, no value)


# ===== what a save may change (adapters/blades.py's write paths: Properties, the IDE's Save, save) =====
#
# One rule, one sentence each (the craft review, 2026-11-22: the store wrote "a starter is read-only" three
# ways and moved a renamed blade's secrets two ways).


def starter_read_only(name: str) -> str:
    """A starter comes with the app: never changed in place."""
    return f"{name} is a starter (read-only): Copy as your own (blades_copy) to change it."


def secret_blade_no_code(name: str) -> str:
    """A secret blade holds its variables' names only."""
    return f"{name} is a secret blade: it has no code, only its variables' names."


def name_taken(name: str) -> str:
    """Another blade answers to the name already (a saved one, a blade folder's, a starter's)."""
    return f"A blade named {name!r} already exists. Pick another name."


def may_change(name: str, pack: str | None, kind: str, code: bool = False) -> None:
    """Whether the blade `name` may be written: never a starter's; never code into a secret blade.
    Raises BladeError with the rule's one sentence."""
    if pack == STARTERS:
        raise _BladeError(starter_read_only(name))
    if code and kind == "secret":
        raise _BladeError(secret_blade_no_code(name))


def may_take(name: str, taken: str | None) -> None:
    """A new blade, or a rename, takes a name only no other blade answers to (`taken`: the one that does,
    as it is written, or None). Raises BladeError."""
    if taken is not None:
        raise _BladeError(name_taken(taken))


@dataclass(frozen=True)
class SecretsMove:
    """What a rename does to the blade's saved secrets (the keyring's `blade/<name>/<secret>`): `follow`
    copied to the new name, then `drop` removed from the old one. Whatever another blade still reads under
    the old name stays there."""

    follow: tuple[str, ...]
    drop: tuple[str, ...]


def secrets_after_rename(
    had: Iterable[str], names: Iterable[str], still_read: Iterable[str] = ()
) -> SecretsMove:
    """A blade renamed: of the secrets it `had` under its old name, those its code still `names` follow it
    to the new name; each is removed from the old name unless a blade that still answers to the old name (a
    blade folder's, once a saved one of the same name is renamed) reads it (`still_read`). Never a secret a
    blade still needs: one followed is copied before the old is removed, one still read is kept."""
    kept, read = set(names), set(still_read)
    had = list(dict.fromkeys(had))
    return SecretsMove(follow=tuple(s for s in had if s in kept), drop=tuple(s for s in had if s not in read))
