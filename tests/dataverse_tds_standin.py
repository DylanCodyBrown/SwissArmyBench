"""Dataverse's read-only SQL endpoint (TDS, port 5558) stood in for at its driver's seam: python-tds
(`pytds.connect`, with certifi and pyOpenSSL beside it) is a made-up module here, so a Dataverse
connection's own code (domain/dataverse.py: it signs in at tests/dataverse_standin.py's Web API, then hands
its token to `pytds.connect`) reads a made-up SQLite file through a cursor that reads the T-SQL the app
sends it (`SELECT TOP n ...`, INFORMATION_SCHEMA.COLUMNS, python-tds's %s marks) as SQLite does. What
`pytds.connect` was given is kept in the stood-in module (`seen`). A real endpoint is not reached
(docs/verified.md says so). Made-up accounts and opportunities only."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from swissarmybench.domain import dataverse

ACCOUNTS = [(f"a{i}", f"Made-up Account {i:02d}", 1000.0 * i) for i in range(1, 7)]
OPPORTUNITIES = [(f"o{i}", f"a{i % 6 + 1}", 250.0 * i) for i in range(1, 13)]

_PRELUDE = r'''import re as _re
import sqlite3 as _sqlite3
import sys as _sys
import types as _types
from pathlib import Path as _Path

_path = _Path(r"{path}")
_off = {off}

_COLUMNS = """SELECT 'dbo' AS table_schema, m.name AS table_name, 'BASE TABLE' AS table_type,
       p.name AS column_name, p.type AS data_type, 'YES' AS is_nullable, p.cid + 1 AS ordinal_position
FROM sqlite_master AS m JOIN pragma_table_info(m.name) AS p
WHERE m.type = 'table' ORDER BY m.name, p.cid"""


class _Cursor:
    def __init__(self, inner):
        self.inner = inner

    @property
    def description(self):
        return self.inner.description

    @property
    def rowcount(self):
        return self.inner.rowcount

    def execute(self, sql, params=()):
        if _off:
            raise RuntimeError(
                "Msg 40000: TDS protocol endpoint is disabled for this organization."
            )
        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            sql = _COLUMNS
        top = _re.match(r"\s*SELECT\s+TOP\s+(\d+)\s+(.*)$", sql, _re.IGNORECASE | _re.DOTALL)
        if top:
            sql = f"SELECT {{top.group(2)}} LIMIT {{top.group(1)}}"
        if params:
            sql = sql.replace("%s", "?").replace("%%", "%")
        self.inner.execute(sql, tuple(params))
        return self

    def fetchall(self):
        return self.inner.fetchall()

    def fetchmany(self, size=1):
        return self.inner.fetchmany(size)

    def fetchone(self):
        return self.inner.fetchone()

    def close(self):
        self.inner.close()


class _Endpoint:
    def __init__(self):
        self.sql = _sqlite3.connect(_path.resolve().as_uri() + "?mode=ro", uri=True)

    def cursor(self):
        return _Cursor(self.sql.cursor())

    def close(self):
        self.sql.close()


def _connect(**given):
    token = given.pop("access_token_callable")()
    _pytds.seen.append(dict(given, token=token))
    return _Endpoint()


_pytds = _types.ModuleType("pytds")
_pytds.connect = _connect
_pytds.seen = []
_certifi = _types.ModuleType("certifi")
_certifi.where = lambda: "made-up-authorities.pem"
_sys.modules["pytds"] = _pytds
_sys.modules["certifi"] = _certifi
_sys.modules["OpenSSL"] = _types.ModuleType("OpenSSL")

'''


def made_up_file(folder: Path) -> Path:
    path = folder / "crm_tds.sqlite"
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as made:
        made.execute("CREATE TABLE account (accountid TEXT, name TEXT, revenue REAL)")
        made.executemany("INSERT INTO account VALUES (?, ?, ?)", ACCOUNTS)
        made.execute("CREATE TABLE opportunity (opportunityid TEXT, accountid TEXT, estimatedvalue REAL)")
        made.executemany("INSERT INTO opportunity VALUES (?, ?, ?)", OPPORTUNITIES)
    return path


def code(folder: Path, address: str, off: bool = False) -> str:
    """A Dataverse connection's own code (its managed identity's sign-in, pointed at the Web API stand-in at
    `address`), after the stood-in python-tds over a made-up file (`off`: the endpoint turned off)."""
    prelude = _PRELUDE.format(path=made_up_file(folder), off=off)
    return prelude + dataverse.MANAGED.replace("https://your-org.crm.dynamics.com", address)
