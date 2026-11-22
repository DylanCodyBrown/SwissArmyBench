"""What each connection kind can write (docs/ideas.md, "Writing data"; the owner, 2026-11-17: "Write
blades should be geared towards our connection types. Most of our connections don't support it").

Every connection kind the app has is either **writable** (with the operations its Write starters do,
and how) or **read-only** (with the reason in plain words). A kind is the way the connection lists and
reads its tables (domain/connection_tables.py's TABLE_KINDS: a database, Power BI, Dataverse, your own
Python, an API, a file, a folder) and, for a database or a file, its form's template
(server/blade_templates.py): SQL Server writes, Snowflake is read-only here, a CSV file writes.
The Connections page's cards, the agent's connection description and context.md say it: "Writes: <the
starters>" or "Read-only: <why>", so nobody, the agent included, tries to write where it cannot.

A Write starter (the starter pack's Write family) names the kinds it writes to among its tags; the
tests hold the two together: every writable kind has a starter, every starter names a writable kind,
and a read-only kind has none.

Three vocabularies, tied here (the craft review of 2026-11-22): a kind's **operations** are its Write
starters' own words (append, create, replace, upsert...: tests/test_write_vocabulary.py reads each
starter's modes and holds them to this table); its **modes** are the adapter's (insert, update, merge,
delete, truncate: what sab.write and the agent's connections_write take on it); OPERATION_MODES says which
mode does each operation, and STARTER_ONLY the operations no mode does (a starter's own call). The words
say both lists. Standard library only; no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from swissarmybench.domain import connection_kinds
from swissarmybench.domain.connection_kinds import WHOLE_MODES as WHOLE_MODES
from swissarmybench.domain.connection_kinds import WRITE_MODES as WRITE_MODES
from swissarmybench.domain.connection_kinds import Writable as Writable

WRITE_FAMILY: str = "Write"
# sab.write's and the agent's connections_write modes are the adapter's (adapter.MODES; a test holds them):
# WRITE_MODES, and WHOLE_MODES for a file or a sheet (written whole or added to; nothing matched by a key).
KEYED_MODES: tuple[str, ...] = ("update", "merge", "delete")


def write_request(body: Any) -> tuple[str, str, list[str], bool]:
    """A connections_write body checked: its table, mode, key and dry run; ValueError in one sentence."""
    if not isinstance(body, dict) or not isinstance(body.get("table"), str) or not body["table"].strip():
        raise ValueError('Send the table to write: {"table": "orders", "rows": [...], "mode": "insert"}.')
    mode = str(body.get("mode") or "insert")
    if mode not in WRITE_MODES:
        raise ValueError(f"mode is one of {', '.join(WRITE_MODES)}, not {mode!r}.")
    given = body.get("key")
    key = [given] if isinstance(given, str) else [str(k) for k in given or () if k]
    if mode in KEYED_MODES and not key:
        raise ValueError(f'A {mode} names the key its rows are matched by: "key": "order_id".')
    rows, table = body.get("rows"), body.get("from_table")
    if rows is not None and not (isinstance(rows, list) and all(isinstance(r, dict) for r in rows)):
        raise ValueError('rows is a list of records: [{"order_id": 1, "region": "North"}].')
    if rows is None and not isinstance(table, str) and mode != "truncate":
        raise ValueError("Send the rows (a list of records) or from_table (an open table's name).")
    return body["table"].strip(), mode, key, body.get("dry_run") is True


# A Write starter's operation -> the adapter's mode that does it (create: the table or the record made,
# then an insert; replace and overwrite: what is there taken out, then the rows).
OPERATION_MODES: dict[str, str] = {
    "append": "insert",
    "create": "insert",
    "replace": "truncate",
    "overwrite": "truncate",
    "truncate": "truncate",
    "upsert": "merge",
    "merge": "merge",
    "update": "update",
    "delete": "delete",
}
# The operations no adapter mode does: a Delta table's upkeep, the lake's own calls in its starter.
STARTER_ONLY: tuple[str, ...] = ("optimize", "vacuum")

# What each kind writes (Writable: its Write starters' operations, how, a note, the adapter's modes it takes)
# or why it is read-only: each kind's own record says it (domain/connection_kinds.py); these are its views.
WRITABLE: dict[str, Writable] = connection_kinds.writable()
READ_ONLY: dict[str, str] = connection_kinds.read_only()
# The tables kinds whose writes are their template's (a database's engine, a file's format); every other
# tables kind is one kind here. dataverse_web is the same Dataverse (its Web API writes either way).
BY_TEMPLATE: frozenset[str] = connection_kinds.writes_by_template()
_SAME: dict[str, str] = connection_kinds.writes_same()


def kind_of(tables_kind: str | None, template: str | None) -> str:
    """The key a connection's writes are found by: its template for a database or a file (and when the
    tables kind is not known, as for a form), else its tables kind."""
    if tables_kind is None or tables_kind in BY_TEMPLATE:
        return str(template or "")
    return _SAME.get(tables_kind, tables_kind)


def tables_kinds_covered() -> dict[str, str]:
    """Each of connection_tables' kinds and how its writes are decided: "template", "writable",
    "read-only", or "" (not decided: the tests refuse that)."""
    out: dict[str, str] = {}
    for kind in connection_kinds.tables_contract():
        key = kind_of(kind, None)
        if kind in BY_TEMPLATE:
            out[kind] = "template"
        else:
            out[kind] = "writable" if key in WRITABLE else "read-only" if key in READ_ONLY else ""
    return out


def capability(
    template: str | None, starters: Iterable[Mapping[str, Any]] = (), tables_kind: str | None = None
) -> dict[str, Any]:
    """A connection kind's writes: {"writable", "operations" (its Write starters' words), "modes" (the
    adapter's: what sab.write takes on it), "how", "note", "starters" (the Write starters' names for it),
    "reason" (read-only: why), "words"} ("Writes: ..." or "Read-only: ...").
    `tables_kind` is connection_tables.tables_kind's answer (None for a form: its template decides)."""
    key = kind_of(tables_kind, template)
    found = WRITABLE.get(key)
    if found is None:
        reason = READ_ONLY.get(key, "the app has no write starters for this kind of connection")
        return {"writable": False, "operations": [], "modes": [], "how": "", "note": "", "starters": [],
                "reason": reason, "words": f"Read-only: {reason}"}  # fmt: skip
    names = starters_for(key, starters)
    words = (
        f"Writes: {', '.join(found.operations)} with its Write starters; "
        f"{', '.join(found.modes)} with sab.write"
    )
    if found.note:
        words += f" ({found.note})"
    return {
        "writable": True,
        "operations": list(found.operations),
        "modes": list(found.modes),
        "how": found.how,
        "note": found.note,
        "starters": names,
        "reason": "",
        "words": words,
    }


def starters_for(template: str, starters: Iterable[Mapping[str, Any]]) -> list[str]:
    """The Write starters that name this kind among their tags, by name: the calls a cell takes (each
    runs one of the family's functions, `Write to SQLite`, which are not listed here)."""
    return sorted(
        str(s["name"])
        for s in starters
        if s.get("family") == WRITE_FAMILY
        and s.get("kind", "snippet") == "snippet"
        and template in [str(t) for t in s.get("tags") or ()]
    )


def kinds_named(tags: Sequence[str]) -> list[str]:
    """The connection kinds a Write starter's tags name (writable or not)."""
    known = set(WRITABLE) | set(READ_ONLY)
    return [t for t in tags if t in known]
