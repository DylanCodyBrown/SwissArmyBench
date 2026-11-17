"""What every Write starter shares (docs/ideas.md, "Writing data", the owner, 2026-11-17: "writes are
meant to be handled with blades and cells in notebooks"): the rows, the dry run's plan and the write's
counts. Each target's own helper builds on it (client/write_sql.py, write_dataverse.py); the statements
and calls themselves stay written out in each blade's cell.

    rows      the rows to write (a DataFrame of any kind, an Arrow table, a DuckDB relation), staged in a
              DuckDB of their own: their columns and types, counts, keys and batches are DuckDB SQL
    Write     one write's report: what a dry run would do (the target, the rows, the statements, the
              counts it could count cheaply, a 5-row sample) or what the write did (its counts and time;
              a difference from the last dry run of the same write is said)

The same shape in every Write starter: **a dry run first** (dry_run = True changes nothing; an agent
sets it to False only after the user said to write, in their own words, in this conversation), **one
transaction** where the target has them, **counts at the end**, **never a secret** (the connection's
own sign-in, sab.connection) and never a row shown beyond the 5-row sample.

Standard library only: DuckDB and each target's driver are imported when a write runs, so this module
loads in any Python, and a missing package is named by the missing-package prompt.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import json
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from typing import Any

SAMPLE_ROWS: int = 5
# The last dry run of each write (connection, target, what) -> its counts: the write says when it did
# something else. This Python's memory only.
_DRY_RUNS: dict[tuple[str, str, str], dict[str, int | None]] = {}
_VERBS: tuple[tuple[str, str], ...] = (
    ("deleted", "delete"),
    ("updated", "update"),
    ("inserted", "insert"),
    ("written", "write"),
    ("sent", "send"),
)


class WriteError(RuntimeError):
    """The write cannot go ahead, or it failed (and was rolled back where the target can): the message
    says why, and what to do instead."""


class Write:
    """One write's report. A starter says what it would do (`would`), then, with dry_run False, writes
    and says what it did (`done`); shown in a notebook, it is that report in words."""

    def __init__(
        self, connection: str, target: str, what: str, rows: Any = None, dry_run: bool = True
    ) -> None:
        self.connection, self.target, self.what = str(connection), str(target), what
        self.dry_run = bool(dry_run)
        self.rows: Rows | None = None if rows is None else Rows(rows)
        self.facts: list[tuple[str, str]] = [("Target", f"{target} on {connection}")]
        if self.rows is not None:
            self.facts.append(("Rows", f"{self.rows.count:,}: {self.rows.typed()}"))
        self.planned: dict[str, int | None] = {}
        self.statements: list[str] = []
        self.counts: dict[str, int] | None = None
        self.notes: list[str] = []
        self.seconds = 0.0
        self._started = time.monotonic()

    def need_rows(self) -> Rows:
        if self.rows is None:
            raise WriteError(f"A {self.what} writes rows: set rows to a DataFrame or a DuckDB relation.")
        return self.rows

    def fact(self, key: str, value: str) -> None:
        self.facts.append((key, value))

    def would(self, *statements: str, **counts: int | None) -> None:
        """What the write would do: its statements or calls in words, and the counts (None: not counted)."""
        self.statements += [s for s in statements if s]
        self.planned.update(counts)
        if self.dry_run:
            _DRY_RUNS[self._key()] = dict(self.planned)

    def done(self, **counts: int) -> Write:
        """What the write did; a difference from the last dry run of the same write is said."""
        self.counts = dict(counts)
        self.seconds = time.monotonic() - self._started
        planned = _DRY_RUNS.pop(self._key(), None)
        if planned:
            differ = [
                f"{k} {planned[k]:,} -> {counts.get(k, 0):,}"
                for k in planned
                if planned[k] is not None and k in counts and planned[k] != counts[k]
            ]
            if differ:
                self.notes.append(
                    f"The dry run counted otherwise ({'; '.join(differ)}): the target changed in between."
                )
        return self

    def _key(self) -> tuple[str, str, str]:
        return (self.connection, self.target, self.what)

    def words(self) -> str:
        if self.counts is None:
            heading = "Dry run: nothing was written. Set dry_run = False to write."
            if not self.dry_run:
                heading = "Nothing was written."
            facts = [*self.facts, ("Would", counted(self.planned, would=True) or "change nothing")]
        else:
            done = counted(self.counts) or "nothing"
            heading = f"Wrote {self.target} on {self.connection}: {done} in {self.seconds:.1f} s."
            facts = list(self.facts)
        width = max(len(k) for k, _ in facts)
        lines = [heading, *(f"  {k.ljust(width)}  {v}" for k, v in facts)]
        if self.statements:
            lines.append("  " + ("Would run:" if self.counts is None else "Ran:"))
            lines += ["    " + s.strip().replace("\n", "\n    ") for s in self.statements]
        lines += [f"  {note}" for note in self.notes]
        if self.counts is None and self.rows is not None and self.rows.count:
            lines += [f"The first {min(SAMPLE_ROWS, self.rows.count)} rows:", self.rows.sample()]
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.words()

    def __repr__(self) -> str:  # a notebook shows the report, never a wall of fields
        return self.words()


def live(connection: Any) -> tuple[str, Any]:
    """A connection's name (for the words) and its live object: by its name it is sab.connection's,
    signed in its own way (its vault, its keyring, its sign-in), never a copy of a secret."""
    if isinstance(connection, str):
        import swissarmybench as sab

        return connection, sab.connection(connection)
    return type(connection).__name__, connection


def counted(counts: dict[str, int | None] | dict[str, int], would: bool = False) -> str:
    """Counts in words: "update 3 rows, insert 12 rows" (would) or "updated 3 rows, inserted 12 rows"."""
    parts = []
    for done, verb in _VERBS:
        if done in counts:
            value = counts[done]
            amount = "an uncounted number of" if value is None else f"{value:,}"
            parts.append(f"{verb if would else done} {amount} {'row' if value == 1 else 'rows'}")
    return ", ".join(parts)


# ===== the rows: staged in a DuckDB of their own, read back in batches =====


class Rows:
    """The rows to write (a DataFrame of any kind, an Arrow table, or a DuckDB relation), staged in a
    DuckDB of their own so their columns, types, counts, keys and batches are all DuckDB SQL."""

    def __init__(self, data: Any) -> None:
        import duckdb  # the rows are staged in DuckDB: imported when a write runs

        if isinstance(data, duckdb.DuckDBPyRelation):
            data = (getattr(data, "to_arrow_table", None) or data.fetch_arrow_table)()
        self.db = duckdb.connect()
        try:
            self.db.register("sab_given", data)
            # A table of its own (a registered frame is seen by this cursor only; batches read on another)
            self.db.execute("CREATE TABLE sab_rows AS SELECT * FROM sab_given")
            self.db.unregister("sab_given")
            described = self.db.execute("DESCRIBE SELECT * FROM sab_rows").fetchall()
        except Exception as error:
            kind = type(data).__name__
            raise WriteError(
                f"rows is a DataFrame, an Arrow table or a DuckDB relation, not a {kind}."
            ) from (error)
        self.columns: list[tuple[str, str]] = [(str(r[0]), str(r[1])) for r in described]
        self.names: list[str] = [n for n, _ in self.columns]
        self.count: int = self.one("SELECT count(*) FROM sab_rows")

    def one(self, sql: str) -> Any:
        found = self.db.execute(sql).fetchall()
        return found[0][0] if found else None

    def typed(self) -> str:
        return ", ".join(f"{n} ({t})" for n, t in self.columns)

    def sample(self) -> str:
        return str(self.db.sql(f"FROM sab_rows LIMIT {SAMPLE_ROWS}"))

    def widths(self) -> dict[str, int]:
        """Each text column's longest value (characters), for a new table's column widths."""
        texts = [n for n, t in self.columns if t == "VARCHAR"]
        if not texts or not self.count:
            return {}
        found = self.db.execute(
            "SELECT " + ", ".join(f"max(length({quote(n)}))" for n in texts) + " FROM sab_rows"
        ).fetchall()
        return {n: int(w or 0) for n, w in zip(texts, found[0] if found else (), strict=False)}

    def batches(
        self,
        names: Sequence[str],
        size: int,
        value: Callable[[Any], Any] | None = None,
        distinct: bool = False,
    ) -> Iterator[list[tuple[Any, ...]]]:
        """The rows' `names` columns in batches of `size`, each value as `value` makes it."""
        picked = ", ".join(quote(n) for n in names)
        cursor = self.db.cursor().execute(f"SELECT {'DISTINCT ' if distinct else ''}{picked} FROM sab_rows")
        convert = value or (lambda v: v)
        while batch := cursor.fetchmany(size):
            yield [tuple(convert(v) for v in row) for row in batch]

    def records(self, size: int, value: Callable[[Any], Any] | None = None) -> Iterator[list[dict[str, Any]]]:
        for batch in self.batches(self.names, size, value):
            yield [dict(zip(self.names, row, strict=True)) for row in batch]

    def check_keys(self, keys: Sequence[str], unique: bool) -> list[str]:
        """The key columns, checked: columns of the rows, never empty; with `unique`, no two rows share
        one (an upsert would write the second over the first)."""
        wrong = [k for k in keys if k not in self.names]
        if not keys or wrong:
            raise WriteError(
                f"keys names the rows' columns that find a row ({', '.join(self.names)}), "
                f"not {', '.join(wrong) or 'nothing'}."
            )
        empty = self.one(
            "SELECT count(*) FROM sab_rows WHERE " + " OR ".join(f"{quote(k)} IS NULL" for k in keys)
        )
        if empty:
            raise WriteError(f"{empty:,} rows have no value in a key column ({', '.join(keys)}).")
        if unique:
            picked = ", ".join(quote(k) for k in keys)
            shared = self.one(
                f"SELECT count(*) FROM (SELECT {picked} FROM sab_rows GROUP BY ALL HAVING count(*) > 1)"
            )
            if shared:
                raise WriteError(
                    f"{shared:,} keys are shared by more than one row: each row needs a key of its own "
                    f"({', '.join(keys)})."
                )
        return list(keys)

    def distinct(self, keys: Sequence[str]) -> int:
        picked = ", ".join(quote(k) for k in keys)
        return int(self.one(f"SELECT count(*) FROM (SELECT DISTINCT {picked} FROM sab_rows)"))


def quote(name: str) -> str:
    """A column's name in DuckDB's own SQL."""
    return '"' + name.replace('"', '""') + '"'


def plain_value(value: Any) -> Any:
    """A value as JSON writes it (a web service's body): numbers, text, true/false, dates as ISO text."""
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, _dt.datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, _dt.date | _dt.time):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        return value.total_seconds()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float) and value != value:  # NaN: no value
        return None
    return value


def json_text(value: Any) -> str:
    return json.dumps(value, default=lambda v: plain_value(v) if plain_value(v) is not v else str(v))


def words(error: BaseException) -> str:
    """An error's first line, as the driver or service said it."""
    text = str(error).strip()
    return (text.splitlines() or [type(error).__name__])[0][:400]


class Failed(Exception):
    """A batch that failed: its number, the rows written before it, its size."""

    def __init__(self, number: int, before: int, size: int, error: BaseException) -> None:
        super().__init__(words(error))
        self.number, self.before, self.size, self.error = number, before, size, error

    def where(self) -> str:
        return f"batch {self.number} (rows {self.before + 1:,} to {self.before + self.size:,})"


def each_batch(batches: Iterator[list[Any]], work: Callable[[list[Any]], Any]) -> int:
    """`work(batch)` for each batch; a failure names its batch and its rows. The rows done."""
    done = 0
    for number, batch in enumerate(batches, 1):
        try:
            work(batch)
        except Exception as error:
            raise Failed(number, done, len(batch), error) from error
        done += len(batch)
    return done


# ===== files: written beside the target, then put in its place =====

FILE_KINDS: tuple[str, ...] = ("csv", "parquet", "json", "folder", "xlsx")


class FileWrite(Write):
    """A write to a file (CSV, Parquet, JSON, an Excel sheet) or a folder of partitioned Parquet files:
    written to a new file (or folder) beside the target first, then put in its place, so a failure
    leaves the old one as it was."""

    def __init__(
        self,
        path: Any,
        kind: str,
        rows: Any,
        dry_run: bool = True,
        overwrite: bool = False,
        add: bool = False,
    ) -> None:
        import os
        from pathlib import Path

        if kind not in FILE_KINDS:
            raise WriteError(f"kind is one of {', '.join(FILE_KINDS)}, not {kind!r}.")
        self.file = Path(os.path.expanduser(str(path)))
        super().__init__("this computer", str(self.file), kind, rows, dry_run)
        self.kind, self.overwrite, self.add = kind, bool(overwrite), bool(add)
        self.path = str(self.file)
        self.need_rows()
        there = self.file.exists()
        if there and kind != "folder" and self.file.is_dir():
            raise WriteError(f"{self.file} is a folder: name the file to write.")
        if there and kind == "folder" and not self.file.is_dir():
            raise WriteError(f"{self.file} is a file: name the folder to write the Parquet files into.")
        if there and kind != "xlsx" and not (self.overwrite or self.add):
            raise WriteError(
                f"There is a {'folder' if kind == 'folder' else 'file'} at {self.file} already: set it to be "
                "replaced."
            )
        if not self.file.parent.exists():
            raise WriteError(f"There is no folder {self.file.parent}.")
        self.facts[0] = (
            "Target",
            self.path + (" (there: " + ("added to" if self.add else "replaced") + ")" if there else " (new)"),
        )

    @staticmethod
    def literal(text: str) -> str:
        """Text as a DuckDB string literal."""
        return "'" + str(text).replace("'", "''") + "'"

    def names(self, names: Sequence[str]) -> str:
        return ", ".join(quote(n) for n in names)

    def check_columns(self, names: Sequence[str]) -> None:
        rows = self.need_rows()
        missing = [n for n in names if n not in rows.names]
        if not names or missing:
            raise WriteError(
                f"Name the rows' columns ({', '.join(rows.names)}), not {', '.join(missing) or 'none'}."
            )

    def statement(self, copy: str, file: str | None = None) -> str:
        """A COPY with the file's path in it ({file} in the text)."""
        return copy.replace("{file}", (file or self.path).replace("'", "''"))

    def copy(self, copy: str) -> int:
        """DuckDB's COPY to a new file (or folder) beside the target, then put in its place."""
        import os
        import shutil

        rows = self.need_rows()
        spare = self.file.with_name(f".{self.file.name}.{uuid.uuid4().hex[:8]}.writing")
        try:
            rows.db.execute(self.statement(copy, str(spare)))
            if self.kind != "folder":
                os.replace(spare, self.file)
            elif self.add and self.file.exists():
                for made in spare.rglob("*"):
                    if made.is_file():
                        place = self.file / made.relative_to(spare)
                        place.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(made, place)
                shutil.rmtree(spare, ignore_errors=True)
            else:
                if self.file.exists():
                    shutil.rmtree(self.file)
                os.replace(spare, self.file)
        except Exception as error:
            if spare.is_dir():
                shutil.rmtree(spare, ignore_errors=True)
            elif spare.exists():
                spare.unlink()
            raise WriteError(f"Nothing was written: {words(error)}") from None
        return rows.count

    # ===== an Excel sheet =====

    def sheet_rows(self, sheet: str) -> int | None:
        """The rows a sheet of the workbook holds (its header too); None: no such sheet or workbook."""
        if not self.file.exists():
            return None
        from openpyxl import load_workbook

        book = load_workbook(self.file, read_only=True)
        try:
            return int(book[sheet].max_row or 0) if sheet in book.sheetnames else None
        finally:
            book.close()

    def sheet(self, sheet: str, add: bool = False) -> int:
        """The rows written to `sheet` (its column names on top), or added below its rows (`add`); the
        workbook's other sheets as they were."""
        import os

        from openpyxl import Workbook, load_workbook

        rows = self.need_rows()
        keep_vba = self.file.suffix.lower() == ".xlsm"
        book = load_workbook(self.file, keep_vba=keep_vba) if self.file.exists() else Workbook()
        if not self.file.exists():
            book.remove(book.active)
        if sheet in book.sheetnames and not add:
            at = book.sheetnames.index(sheet)
            book.remove(book[sheet])
            target = book.create_sheet(sheet, at)
        elif sheet in book.sheetnames:
            target = book[sheet]
        else:
            target = book.create_sheet(sheet)
        if not (add and target.max_row > 1):
            target.append(rows.names)
        for batch in rows.batches(rows.names, 5000, _cell_value):
            for row in batch:
                target.append(list(row))
        spare = self.file.with_name(f".{self.file.stem}.{uuid.uuid4().hex[:8]}{self.file.suffix}")
        try:
            book.save(spare)
            os.replace(spare, self.file)
        except Exception as error:
            if spare.exists():
                spare.unlink()
            raise WriteError(
                f"Nothing was written: {words(error)} (is the workbook open in Excel?)"
            ) from None
        return rows.count


def _cell_value(value: Any) -> Any:
    """A value as a sheet's cell holds it: a date and time without its zone, an id as text."""
    if isinstance(value, _dt.datetime) and value.tzinfo is not None:
        return value.astimezone(_dt.UTC).replace(tzinfo=None)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list | dict):
        return json.dumps(value, default=str)
    if isinstance(value, _dt.timedelta):
        return value.total_seconds()
    return value
