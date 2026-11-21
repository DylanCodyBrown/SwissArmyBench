"""A project's sandbox on disk (domain/sandbox.py): its DuckDB file, the baseline's and the checkpoints'
copies, and
sandbox.json.

The file is opened by this server only, with external access off (no file, no network, no ATTACH from a query
an
API sends) and no spill folder. Every call holds one lock: a write, a reset and a read never cross. A baseline
or
a checkpoint is a copy of the whole file, taken after a CHECKPOINT with the file closed, so Reset is one file
copy
and gives back exactly the bytes' tables. Rows reach this disk only on the user's action (Add to sandbox).
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.domain import sandbox as rules


def _connect(path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(
        str(path),
        config={
            "enable_external_access": False,
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
            "temp_directory": "",
            "lock_configuration": True,
        },
    )


class SandboxFiles:
    """One project's sandbox: `folder` is the project's top."""

    def __init__(self, project: str) -> None:
        self.root = Path(project) / rules.FOLDER
        self.db = self.root / rules.DB_FILE
        self.baseline = self.root / rules.BASELINE_FILE
        self.points = self.root / rules.CHECKPOINTS
        self.meta_path = self.root / rules.META_FILE
        self._lock = threading.RLock()
        self._con: duckdb.DuckDBPyConnection | None = None

    # ===== the file =====

    def exists(self) -> bool:
        return self.db.exists()

    def _open(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            self.root.mkdir(parents=True, exist_ok=True)
            self._con = _connect(self.db)
        return self._con

    def _shut(self) -> None:
        if self._con is not None:
            try:
                self._con.execute("CHECKPOINT").fetchall()
            finally:
                self._con.close()
                self._con = None

    def close(self) -> None:
        with self._lock:
            self._shut()

    def _all(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        """A statement's whole answer, on a cursor of its own (DuckDB wants each result finished)."""
        cursor = self._open().cursor()
        try:
            return cursor.execute(sql, list(params)).fetchall()
        finally:
            cursor.close()

    def _copy(self, source: Path, target: Path) -> None:
        """The whole file copied with it closed (no write-ahead log left behind)."""
        self._shut()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".copying")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
        Path(str(target) + ".wal").unlink(missing_ok=True)

    # ===== the meta file =====

    def read_meta(self) -> rules.Meta:
        try:
            return rules.read_meta(self.meta_path.read_text(encoding="utf-8"))
        except OSError:
            return rules.Meta()

    def write_meta(self, meta: rules.Meta) -> None:
        write_atomic(self.meta_path, rules.meta_text(meta), if_changed=True)

    # ===== tables =====

    def tables(self) -> list[dict[str, Any]]:
        """Each table: its name, rows and columns (name, type)."""
        with self._lock:
            if not self.exists():
                return []
            names = [
                str(r[0])
                for r in self._all(
                    "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main' ORDER BY table_name"
                )
            ]
            out = []
            for name in names:
                cols = self._columns(name)
                count = self._all(f"SELECT count(*) FROM {rules.quote(name)}")  # noqa: S608
                out.append({"name": name, "rows": int(count[0][0]) if count else 0, "columns": cols})
            return out

    def _columns(self, table: str) -> list[dict[str, Any]]:
        rows = self._all(
            "SELECT column_name, data_type FROM duckdb_columns() "
            "WHERE schema_name = 'main' AND table_name = ? "
            "ORDER BY column_index",
            [table],
        )
        keys = {
            str(c)
            for r in self._all(
                "SELECT constraint_column_names FROM duckdb_constraints() WHERE table_name = ? "
                "AND constraint_type = 'PRIMARY KEY'",
                [table],
            )
            for c in (r[0] or [])
        }
        return [{"name": str(r[0]), "type": str(r[1]), "key": str(r[0]) in keys} for r in rows]

    def columns(self, table: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._columns(table)

    def table_name(self, wanted: str) -> str | None:
        """The table's own name (any case), or None."""
        for t in self.tables():
            if t["name"].casefold() == wanted.casefold():
                return str(t["name"])
        return None

    def put_table(self, name: str, table: pa.Table, replace: bool) -> int:
        with self._lock:
            cursor = self._open().cursor()
            try:
                cursor.register("__sab_incoming", table)
                verb = "CREATE OR REPLACE TABLE" if replace else "CREATE TABLE"
                cursor.execute(f"{verb} {rules.quote(name)} AS SELECT * FROM __sab_incoming")  # noqa: S608
                cursor.unregister("__sab_incoming")
            finally:
                cursor.close()
            return int(table.num_rows)

    def create_empty(self, name: str, columns: Sequence[rules.Column], replace: bool) -> None:
        with self._lock:
            if replace:
                self._all(f"DROP TABLE IF EXISTS {rules.quote(name)}")
            self._all(rules.create_sql(name, columns))

    def drop(self, name: str) -> None:
        with self._lock:
            self._all(f"DROP TABLE IF EXISTS {rules.quote(name)}")

    def arrow(self, name: str) -> pa.Table:
        with self._lock:
            cursor = self._open().cursor()
            try:
                return cursor.sql(f"SELECT * FROM {rules.quote(name)}").to_arrow_table()  # noqa: S608
            finally:
                cursor.close()

    # ===== an API's reads and writes =====

    def query(
        self, statement: rules.Statement, limit: int
    ) -> tuple[list[str], list[str], list[list[Any]], bool]:
        """A read: its columns, their DuckDB types, its rows (at most `limit`), whether more were cut."""
        with self._lock:
            cursor = self._open().cursor()
            try:
                result = cursor.execute(statement.sql, statement.params)
                described = result.description or []
                columns = [str(d[0]) for d in described]
                types = [str(d[1]) for d in described]
                rows = result.fetchmany(limit + 1)
                if len(rows) > limit:
                    result.fetchall()  # finished: DuckDB wants each result done
            finally:
                cursor.close()
        return columns, types, [list(r) for r in rows[:limit]], len(rows) > limit

    def change(self, statement: rules.Statement) -> tuple[list[str], list[str], list[list[Any]]]:
        """One write in its own transaction: what it answers (its RETURNING rows, else its count)."""
        with self._lock:
            con = self._open().cursor()
            con.execute("BEGIN TRANSACTION")
            try:
                result = con.execute(statement.sql, statement.params)
                described = result.description or []
                rows = [list(r) for r in result.fetchall()]
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            finally:
                con.close()
        return [str(d[0]) for d in described], [str(d[1]) for d in described], rows

    def write(self, groups: Sequence[Sequence[rules.Statement]]) -> list[int]:
        """Each group's statements, all in one transaction: the rows each group changed, all or none."""
        with self._lock:
            con = self._open().cursor()
            con.execute("BEGIN TRANSACTION")
            counts: list[int] = []
            try:
                for group in groups:
                    changed = 0
                    for s in group:
                        found = con.execute(s.sql, s.params).fetchall()
                        changed += int(found[0][0]) if found and isinstance(found[0][0], int) else 0
                    counts.append(changed)
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            finally:
                con.close()
            return counts

    # ===== baseline, reset, checkpoints =====

    def set_baseline(self) -> None:
        with self._lock:
            self._open()
            self._copy(self.db, self.baseline)

    def reset(self) -> bool:
        """The file put back to the baseline. False: there is none."""
        with self._lock:
            if not self.baseline.exists():
                return False
            self._shut()
            self._copy(self.baseline, self.db)
            return True

    def save_checkpoint(self, name: str) -> None:
        with self._lock:
            self._open()
            self._copy(self.db, self.points / rules.checkpoint_file(name))

    def restore_checkpoint(self, name: str) -> bool:
        with self._lock:
            source = self.points / rules.checkpoint_file(name)
            if not source.exists():
                return False
            self._shut()
            self._copy(source, self.db)
            return True

    def delete_checkpoint(self, name: str) -> None:
        with self._lock:
            (self.points / rules.checkpoint_file(name)).unlink(missing_ok=True)

    def copy_to(self, target: Path) -> None:
        """The sandbox as it is now, copied whole (an export's bundled data)."""
        with self._lock:
            self._open()
            self._copy(self.db, target)
