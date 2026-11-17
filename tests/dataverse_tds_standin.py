"""Dataverse's read-only SQL endpoint (TDS, port 5558) stood in for at the connection's cursor seam: no
pyodbc and no ODBC driver here, so a Dataverse connection's `conn` is a made-up SQLite file behind a cursor
that reads the T-SQL the app sends it (`SELECT TOP n ...`, INFORMATION_SCHEMA.COLUMNS) as SQLite does.
A real endpoint is not reached (docs/verified.md says so). Made-up accounts and opportunities only."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ACCOUNTS = [(f"a{i}", f"Made-up Account {i:02d}", 1000.0 * i) for i in range(1, 7)]
OPPORTUNITIES = [(f"o{i}", f"a{i % 6 + 1}", 250.0 * i) for i in range(1, 13)]

_CODE = r'''import re
import sqlite3
from pathlib import Path

path = Path(r"{path}")
off = {off}

_COLUMNS = """SELECT 'dbo' AS table_schema, m.name AS table_name, 'BASE TABLE' AS table_type,
       p.name AS column_name, p.type AS data_type, 'YES' AS is_nullable, p.cid + 1 AS ordinal_position
FROM sqlite_master AS m JOIN pragma_table_info(m.name) AS p
WHERE m.type = 'table' ORDER BY m.name, p.cid"""


class Cursor:
    def __init__(self, inner):
        self.inner = inner

    @property
    def description(self):
        return self.inner.description

    @property
    def rowcount(self):
        return self.inner.rowcount

    def execute(self, sql, *parameters):
        if off:
            raise RuntimeError(
                "Dataverse's SQL endpoint (TDS) is off in this environment. The environment's administrator "
                'turns on "Enable TDS endpoint" in the Power Platform admin center.'
            )
        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            sql = _COLUMNS
        top = re.match(r"\s*SELECT\s+TOP\s+(\d+)\s+(.*)$", sql, re.IGNORECASE | re.DOTALL)
        if top:
            sql = f"SELECT {{top.group(2)}} LIMIT {{top.group(1)}}"
        self.inner.execute(sql, *parameters)
        return self

    def fetchall(self):
        return self.inner.fetchall()

    def fetchmany(self, size=1):
        return self.inner.fetchmany(size)

    def close(self):
        self.inner.close()


class Endpoint:
    """The SQL endpoint's connection: only its cursor is stood in for."""

    def __init__(self):
        self.sql = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)

    def cursor(self):
        return Cursor(self.sql.cursor())

    def close(self):
        self.sql.close()


conn = Endpoint()
'''


def made_up_file(folder: Path) -> Path:
    path = folder / "crm_tds.sqlite"
    with sqlite3.connect(path) as made:
        made.execute("CREATE TABLE account (accountid TEXT, name TEXT, revenue REAL)")
        made.executemany("INSERT INTO account VALUES (?, ?, ?)", ACCOUNTS)
        made.execute("CREATE TABLE opportunity (opportunityid TEXT, accountid TEXT, estimatedvalue REAL)")
        made.executemany("INSERT INTO opportunity VALUES (?, ?, ?)", OPPORTUNITIES)
    return path


def code(folder: Path, off: bool = False) -> str:
    """The connection's code: its `conn` the stood-in endpoint over a made-up file (`off`: turned off)."""
    return _CODE.format(path=made_up_file(folder), off=off)
