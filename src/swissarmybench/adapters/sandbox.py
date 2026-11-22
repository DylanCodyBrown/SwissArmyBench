"""A project's sandbox on disk (domain/sandbox.py): its DuckDB file, the baseline's and the checkpoints'
copies, and
sandbox.json.

The file is opened by this server only, with external access off (no file, no network, no ATTACH from a query
an
API sends) and no spill folder. Reads and writes share the file (each on a cursor of its own, DuckDB's own
transactions keeping them apart), so callers at once are read at once; a reset, a baseline, a checkpoint and a
table added or dropped hold it alone, so none crosses a read or a write. A baseline
or
a checkpoint is a copy of the whole file, taken after a CHECKPOINT with the file closed, so Reset is one file
copy
and gives back exactly the bytes' tables. Rows reach this disk only on the user's action (Add to sandbox).
"""

from __future__ import annotations

import contextlib
import copy
import shutil
import threading
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.ipc

from swissarmybench.adapters import sab_adapter
from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.domain import sandbox as rules

MAX_BATCH = 50_000  # rows a kept rest is read in at a time


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


class _Gate:
    """Many readers and writers at once (shared), or one holder alone (exclusive: the file closed, copied or
    its tables changed). Re-entrant for the one holding it alone."""

    def __init__(self) -> None:
        self._condition = threading.Condition(threading.Lock())
        self._shared = 0
        self._owner: int | None = None
        self._depth = 0

    @contextlib.contextmanager
    def shared(self) -> Iterator[None]:
        me = threading.get_ident()
        if self._owner == me:  # inside its own exclusive hold
            yield
            return
        with self._condition:
            while self._owner is not None:
                self._condition.wait()
            self._shared += 1
        try:
            yield
        finally:
            with self._condition:
                self._shared -= 1
                if not self._shared:
                    self._condition.notify_all()

    @contextlib.contextmanager
    def exclusive(self) -> Iterator[None]:
        me = threading.get_ident()
        with self._condition:
            if self._owner == me:
                self._depth += 1
            else:
                while self._owner is not None or self._shared:
                    self._condition.wait()
                self._owner, self._depth = me, 1
        try:
            yield
        finally:
            with self._condition:
                self._depth -= 1
                if not self._depth:
                    self._owner = None
                    self._condition.notify_all()


class SandboxFiles:
    """One project's sandbox: `folder` is the project's top."""

    def __init__(self, project: str) -> None:
        self.root = Path(project) / rules.FOLDER
        self.db = self.root / rules.DB_FILE
        self.baseline = self.root / rules.BASELINE_FILE
        self.points = self.root / rules.CHECKPOINTS
        self.meta_path = self.root / rules.META_FILE
        self._gate = _Gate()
        self._opening = threading.Lock()
        self._con: duckdb.DuckDBPyConnection | None = None
        self._names: list[str] | None = None  # the tables' names, kept until a table is added or dropped
        self._meta: tuple[tuple[int, int], rules.Meta] | None = (
            None  # sandbox.json as last read, by its stamp
        )

    # ===== the file =====

    def exists(self) -> bool:
        return self.db.exists()

    def _open(self) -> duckdb.DuckDBPyConnection:
        with self._opening:
            if self._con is None:
                self.root.mkdir(parents=True, exist_ok=True)
                self._con = _connect(self.db)
            return self._con

    def _shut(self) -> None:
        self._names = None
        if self._con is not None:
            try:
                self._con.execute("CHECKPOINT").fetchall()
            finally:
                self._con.close()
                self._con = None

    def close(self) -> None:
        with self._gate.exclusive():
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
        """sandbox.json, read again only when the file changed (a copy each time: callers change it)."""
        try:
            found = self.meta_path.stat()
        except OSError:
            return rules.Meta()
        stamp = (found.st_mtime_ns, found.st_size)
        kept = self._meta
        if kept is None or kept[0] != stamp:
            try:
                kept = (stamp, rules.read_meta(self.meta_path.read_text(encoding="utf-8")))
            except OSError:
                return rules.Meta()
            self._meta = kept
        return copy.deepcopy(kept[1])

    def write_meta(self, meta: rules.Meta) -> None:
        write_atomic(self.meta_path, rules.meta_text(meta), if_changed=True)

    # ===== tables =====

    def tables(self) -> list[dict[str, Any]]:
        """Each table: its name, rows and columns (name, type)."""
        with self._gate.shared():
            names = self.table_names()
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
        with self._gate.shared():
            return self._columns(table)

    def table_names(self) -> list[str]:
        """The tables' names, sorted: read once, kept until a table is added, dropped or put back (a mock
        client's every call asks; counting every table's rows for it was the slow part)."""
        with self._gate.shared():
            names = self._names
            if names is None:
                if not self.exists():
                    return []
                names = [
                    str(r[0])
                    for r in self._all(
                        "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main' UNION ALL "
                        "SELECT view_name FROM duckdb_views() WHERE schema_name = 'main' AND NOT internal "
                        "ORDER BY 1"
                    )
                ]
                self._names = names
            return list(names)

    def table_name(self, wanted: str) -> str | None:
        """The table's own name (any case), or None."""
        for name in self.table_names():
            if name.casefold() == wanted.casefold():
                return name
        return None

    def put_table(self, name: str, table: pa.Table, replace: bool) -> int:
        with self._gate.exclusive():
            self._names = None
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
        with self._gate.exclusive():
            self._names = None
            if replace:
                self._all(f"DROP TABLE IF EXISTS {rules.quote(name)}")
            self._all(rules.create_sql(name, columns))

    def drop(self, name: str) -> None:
        with self._gate.exclusive():
            self._names = None
            what = "VIEW" if self._kind_of(name) == "view" else "TABLE"
            self._all(f"DROP {what} IF EXISTS {rules.quote(name)}")

    def _kind_of(self, name: str) -> str | None:
        found = self._all(
            "SELECT 'table' FROM duckdb_tables() WHERE schema_name = 'main' AND table_name = ? UNION ALL "
            "SELECT 'view' FROM duckdb_views() WHERE schema_name = 'main' AND view_name = ? UNION ALL "
            "SELECT 'sequence' FROM duckdb_sequences() WHERE schema_name = 'main' AND sequence_name = ?",
            [name, name, name],
        )
        return str(found[0][0]) if found else None

    def keys(self, name: str) -> list[str]:
        """The table's primary key's columns ([]: none)."""
        if not self.exists():
            return []
        with self._gate.shared():
            return [c["name"] for c in self._columns(name) if c["key"]]

    def set_key(self, name: str, key: Sequence[str]) -> None:
        """The table's primary key made `key`, in the sandbox and in its baseline (Reset keeps it): DuckDB's
        refusal when a row repeats or blanks it. A table with a key already is left as it is."""
        add = (
            f"ALTER TABLE {rules.quote(name)} ADD PRIMARY KEY ("
            + ", ".join(rules.quote(k) for k in key)
            + ")"
        )
        with self._gate.exclusive():
            if not self._key_of(self._open(), name):
                self._all(add)
            if self.baseline.exists():
                other = _connect(self.baseline)
                try:
                    there = other.execute(
                        "SELECT count(*) FROM duckdb_tables() WHERE schema_name = 'main' AND table_name = ?",
                        [name],
                    ).fetchall()[0][0]
                    if there and not self._key_of(other, name):
                        other.execute(add)
                finally:
                    other.close()

    @staticmethod
    def _key_of(con: duckdb.DuckDBPyConnection, name: str) -> bool:
        found = con.execute(
            "SELECT count(*) FROM duckdb_constraints() WHERE table_name = ? "
            "AND constraint_type = 'PRIMARY KEY'",
            [name],
        ).fetchall()
        return bool(found and found[0][0])

    def kind_of(self, name: str) -> str | None:
        """What `name` is in the sandbox's file: "table", "view", "sequence" or None (not there)."""
        if not self.exists():
            return None
        with self._gate.shared():
            return self._kind_of(name)

    def define(self, sql: str, params: Sequence[Any] = ()) -> None:
        """A view, a table made from a query or a sequence, made or dropped by a mock's statement (one DuckDB
        statement the mock checked): under the exclusive gate, the names read again after it."""
        with self._gate.exclusive():
            self._names = None
            self._all(sql, params)

    # ===== through the adapter (Plans/adapter.plan.md): the sandbox is one more DuckDB source =====

    @contextlib.contextmanager
    def _cursor(self, writing: bool) -> Iterator[duckdb.DuckDBPyConnection]:
        """A cursor of its own while the gate is shared: a read keeps it while its batches are read."""
        with self._gate.shared():
            cursor = self._open().cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    def source(self) -> sab_adapter.DuckDB:
        return sab_adapter.DuckDB(self._cursor, f"The {rules.NAME.lower()}")

    def arrow(self, name: str) -> pa.Table:
        """A sandbox table as a grid's Arrow table: read whole through the adapter."""
        return sab_adapter.make_table(sab_adapter.TableSource(self.source(), name))

    def read(self, name: str, plan: Any) -> tuple[pa.RecordBatchReader, tuple[str, ...]]:
        """A table read with a plan (its JSON): the batches as DuckDB makes them, and what was folded."""
        reader, folded = sab_adapter.read(self.source(), name, sab_adapter.plan_from(plan))
        return reader, folded.parts

    def write_arrow(self, name: str, data: bytes, key: Sequence[str], mode: str) -> dict[str, int]:
        """An Arrow IPC stream's rows into a table (insert; update, merge or delete by key; truncate)."""
        reader = pa.ipc.open_stream(pa.BufferReader(data))
        done = sab_adapter.write(self.source(), name, reader, key, mode)
        return {"inserted": done.inserted, "updated": done.updated, "deleted": done.deleted}

    def query_arrow(self, sql: str, params: Any) -> pa.RecordBatchReader:
        """The adapter's query for a read (DuckDB SQL, the source's made so): streamed under the gate."""
        return sab_adapter.query(self.source(), sql, params)

    def change_arrow(self, sql: str, params: Any) -> tuple[pa.Table, int]:
        """A write: its answer (RETURNING rows, else its count) and the rows it changed."""
        answer = sab_adapter.query(self.source(), sql, params).read_all()
        if answer.column_names == [sab_adapter.COUNT]:
            return answer, int(answer.column(0)[0].as_py() or 0) if answer.num_rows else 0
        return answer, answer.num_rows

    @staticmethod
    def counted(rows: int) -> pa.RecordBatchReader:
        return sab_adapter.counted(rows)

    # ===== an API's reads and writes =====

    def query(
        self, statement: rules.Statement, limit: int
    ) -> tuple[list[str], list[str], list[list[Any]], bool]:
        """A read: its columns, their DuckDB types, its rows (at most `limit`), whether more were cut."""
        with self._gate.shared():
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

    def write(self, groups: Sequence[Sequence[rules.Statement]]) -> list[int]:
        """Each group's statements, all in one transaction: the rows each group changed, all or none."""
        with self._gate.shared():
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
        with self._gate.exclusive():
            self._open()
            self._copy(self.db, self.baseline)

    def reset(self) -> bool:
        """The file put back to the baseline. False: there is none."""
        with self._gate.exclusive():
            if not self.baseline.exists():
                return False
            self._shut()
            self._copy(self.baseline, self.db)
            return True

    def reset_table(self, name: str) -> bool:
        """One table back to the baseline (the baseline file read alone, read-only). False: not in it."""
        with self._gate.exclusive():
            if not self.baseline.exists():
                return False
            other = duckdb.connect(
                str(self.baseline), read_only=True, config={"enable_external_access": False}
            )
            try:
                found = other.execute(
                    "SELECT count(*) FROM duckdb_tables() WHERE schema_name = 'main' AND table_name = ?",
                    [name],
                ).fetchall()
                if not found or not found[0][0]:
                    return False
                table = other.sql(f"SELECT * FROM {rules.quote(name)}").to_arrow_table()  # noqa: S608
            finally:
                other.close()
            self.put_table(name, table, True)
            return True

    def save_checkpoint(self, name: str) -> None:
        with self._gate.exclusive():
            self._open()
            self._copy(self.db, self.points / rules.checkpoint_file(name))

    def restore_checkpoint(self, name: str) -> bool:
        with self._gate.exclusive():
            source = self.points / rules.checkpoint_file(name)
            if not source.exists():
                return False
            self._shut()
            self._copy(source, self.db)
            return True

    def delete_checkpoint(self, name: str) -> None:
        with self._gate.exclusive():
            (self.points / rules.checkpoint_file(name)).unlink(missing_ok=True)

    def copy_to(self, target: Path) -> None:
        """The sandbox as it is now, copied whole (an export's bundled data)."""
        with self._gate.exclusive():
            self._open()
            self._copy(self.db, target)


class ExportFolder:
    """A local sandbox API's export folder: its files written only when their bytes change, a stale one
    removed,
    the sandbox's copy (only on the user's tick)."""

    SKIP = ("data/", "__pycache__/", ".venv/", ".aws-sam/")

    def __init__(self, copy_sandbox: Callable[[Path], None]) -> None:
        self._copy = copy_sandbox

    def write(self, folder: str, files: dict[str, str]) -> dict[str, list[str]]:
        root = Path(folder)
        written: list[str] = []
        unchanged: list[str] = []
        for name, text in sorted(files.items()):
            (written if write_atomic(root / name, text, if_changed=True) else unchanged).append(name)
        return {"written": written, "unchanged": unchanged}

    def existing(self, folder: str) -> dict[str, str]:
        root = Path(folder)
        out: dict[str, str] = {}
        if not root.is_dir():
            return out
        for path in root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if not path.is_file() or relative.startswith(self.SKIP):
                continue
            try:
                out[relative] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        return out

    def remove(self, folder: str, names: list[str]) -> None:
        for name in names:
            (Path(folder) / name).unlink(missing_ok=True)

    def copy_sandbox(self, folder: str) -> None:
        self._copy(Path(folder) / "data" / "sandbox.duckdb")


class LocalApiFiles:
    """API.py: read, written atomically (the user's own file: only on their action), its stamp."""

    @staticmethod
    def read(path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    @staticmethod
    def write(path: str, text: str) -> None:
        write_atomic(path, text, if_changed=True)

    @staticmethod
    def stamp(path: str) -> float | None:
        try:
            found = Path(path).stat()
        except OSError:
            return None
        return found.st_mtime_ns / 1e9 + found.st_size

    @staticmethod
    def join(folder: str, name: str) -> str:
        return str(Path(folder) / name)
