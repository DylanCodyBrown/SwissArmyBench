"""Export to delimited text, CSV, Excel and Parquet (plan section 10a).

Exports read the grid's own view, so the file always matches the grid. Rows stream out of
DuckDB in Arrow record batches and each format consumes them batch by batch.

Decisions recorded in docs/verified.md:
- Excel is written by sab_excel (openpyxl only: Plans/excel.plan.md), a batch of rows at a time in
  openpyxl's write-only mode: memory stays flat, and a large export is slower than xlsxwriter's was
  (docs/verified.md has both times). openpyxl passes each sheet through one temporary file of the
  system's, removed as the workbook is saved. The Excel row limit (1,048,576) and the column limit
  (16,384) are refused with a message.
- Parquet is written by pyarrow into memory in row groups; DuckDB's own COPY stays disabled.
- Text that starts with = + - @ tab or carriage return could run as a formula when a CSV is
  opened in Excel. By default such text cells get a leading apostrophe in delimited exports.
  Excel exports write every text cell as a text cell (never a formula: sab_excel's cell_value), so
  nothing needs changing there.
"""

from __future__ import annotations

import csv
import importlib
import io
import json
from collections.abc import Iterator
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from swissarmybench.adapters import adapter
from swissarmybench.domain.datasets import Column
from swissarmybench.domain.export import (
    FORMULA_STARTS,
    ExportError,
    ExportOptions,
    Provenance,
    markdown_table,
    neutralize,
)
from swissarmybench.domain.steps import type_family


class _Later:
    """A module imported on its first use, not with the app (sab_excel with openpyxl, Arrow's compute)."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, attribute: str) -> Any:
        return getattr(importlib.import_module(self._name), attribute)


pc: Any = _Later("pyarrow.compute")
sab_excel: Any = _Later("swissarmybench.sab_excel")


EXCEL_MAX_ROWS: int = 1_048_576
EXCEL_MAX_COLUMNS: int = 16_384
_BATCH_ROWS: int = 50_000


def batches(cursor: duckdb.DuckDBPyConnection, sql: str) -> pa.RecordBatchReader:
    """The rows to export, read through the adapter (Plans/adapter.plan.md, phase 3): its query over the
    app's own DuckDB session, streamed a batch at a time."""
    return adapter.query(adapter.DuckDB.session(cursor, "the open tables"), sql)


def _text_value(value: Any, options: ExportOptions, is_text: bool) -> str:
    if value is None:
        return options.blank
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return neutralize(value) if (is_text and options.neutralize_formulas) else value
    return str(value)


def _column_texts(array: pa.Array, options: ExportOptions, is_text: bool) -> list[Any]:
    """_text_value for every value of one column, with the per-type work chosen once. For the csv
    writer only: where it writes a value just as _text_value would (a whole number, a float, and a
    blank when blanks are written empty), the value is left for it to write."""
    blank = options.blank
    kind = array.type
    if pa.types.is_date32(kind):
        dates = _date_texts(array, blank)
        if dates is not None:
            return dates
    values: list[Any] = array.to_pylist()
    if pa.types.is_string(kind) or pa.types.is_large_string(kind) or pa.types.is_string_view(kind):
        if is_text and options.neutralize_formulas:
            return [blank if v is None else ("'" + v if v.startswith(FORMULA_STARTS) else v) for v in values]
        return values if blank == "" else [blank if v is None else v for v in values]
    if pa.types.is_integer(kind) or pa.types.is_floating(kind):
        # The csv writer writes str() of a number (repr() of a float is the same text) and nothing
        # for None.
        return values if blank == "" else [blank if v is None else v for v in values]
    if pa.types.is_boolean(kind):
        return [blank if v is None else ("true" if v else "false") for v in values]
    return [_text_value(v, options, is_text) for v in values]


# The days from 1970-01-01 of the first and last day a Python date holds (0001-01-01, 9999-12-31).
_FIRST_DAY, _LAST_DAY = -719_162, 2_932_896


def _date_texts(array: pa.Array, blank: str) -> list[Any] | None:
    """A DATE column as ISO text, written by Arrow: the text date.isoformat() gives, without a
    Python date made for every value (1,600,000 dates: 1.4 s -> 0.1 s). None when a day is outside
    what a Python date holds, which is left to fail as it always has."""
    span = pc.min_max(array.cast(pa.int32())).as_py()
    if span["min"] is not None and not (_FIRST_DAY <= span["min"] and span["max"] <= _LAST_DAY):
        return None
    texts: list[Any] = array.cast(pa.string()).to_pylist()
    return texts if blank == "" else [blank if v is None else v for v in texts]


def delimited(
    reader: pa.RecordBatchReader, columns: tuple[Column, ...], options: ExportOptions
) -> Iterator[bytes]:
    """Delimited text, one encoded chunk per batch. The csv module quotes cells holding the
    delimiter, quotes or line breaks, doubling inner quotes."""
    line_terminator = "\r\n" if options.line_ending == "windows" else "\n"
    text_columns = [type_family(c.type) == "text" for c in columns]
    buffer = io.StringIO()
    writer = csv.writer(
        buffer,
        delimiter=options.delimiter,
        quoting=csv.QUOTE_ALL if options.quote_all else csv.QUOTE_MINIMAL,
        lineterminator=line_terminator,
    )
    first = True

    def flush() -> bytes:
        nonlocal first
        data = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        encoded = data.encode(options.encoding if first else "utf-8")
        first = False
        return encoded

    if options.header:
        # Column names come from the data too, so the header row is neutralized like text cells.
        writer.writerow([neutralize(c.name) if options.neutralize_formulas else c.name for c in columns])
    for batch in reader:
        # Column by column, one type check per column instead of one per cell: on 1,000,000
        # rows x 10 columns this took the export from about 6.2 s to 2.1 s, byte for byte the same.
        texts = [_column_texts(col, options, text_columns[i]) for i, col in enumerate(batch.columns)]
        writer.writerows(zip(*texts, strict=True))
        yield flush()
    tail = flush()
    if tail or first:
        yield tail


def excel(
    reader: pa.RecordBatchReader,
    columns: tuple[Column, ...],
    options: ExportOptions,
    provenance: Provenance | None,
    row_count: int,
) -> bytes:
    """The view as an xlsx workbook: sab_excel's build with no design (Plans/excel.plan.md), the rows
    streamed a batch at a time; the Provenance sheet as its notes."""
    if row_count + 1 > EXCEL_MAX_ROWS:
        raise ExportError(
            f"{row_count:,} rows is more than one Excel sheet holds ({EXCEL_MAX_ROWS - 1:,} "
            "data rows). Filter first, or export CSV or Parquet."
        )
    if len(columns) > EXCEL_MAX_COLUMNS:
        raise ExportError(
            f"{len(columns):,} columns is more than one Excel sheet holds ({EXCEL_MAX_COLUMNS:,}). "
            "Choose fewer columns, or export CSV or Parquet."
        )
    names = [c.name for c in columns]
    rows = pa.RecordBatchReader.from_batches(
        pa.schema([f.with_name(n) for f, n in zip(reader.schema, names, strict=True)]),
        (pa.record_batch(batch.columns, names=names) for batch in reader),
    )
    try:
        made: bytes = sab_excel.build(
            {options.sheet_name: rows},
            notes={"Provenance": provenance.lines()} if provenance is not None else None,
            truncate=options.allow_cell_truncation,
        )
    except sab_excel.WorkbookError as error:
        raise ExportError(str(error)) from error
    return made


def parquet(reader: pa.RecordBatchReader, options: ExportOptions, provenance: Provenance | None) -> bytes:
    """Types survive exactly; provenance goes into the file's key-value metadata."""
    schema = reader.schema
    if provenance is not None:
        schema = schema.with_metadata(
            {
                "swissarmybench.provenance": json.dumps(
                    {
                        "source": provenance.source,
                        "steps": provenance.steps,
                        "settings": provenance.settings,
                        "exported_at": provenance.exported_at,
                        "rows": provenance.rows,
                    }
                )
            }
        )
    output = io.BytesIO()
    with pq.ParquetWriter(output, schema, compression=options.compression) as writer:
        for batch in reader:
            writer.write_batch(batch.replace_schema_metadata(schema.metadata))
    return output.getvalue()


# ===== the service layer's `ExportWriter` port =====


def write(
    cursor: duckdb.DuckDBPyConnection,
    sql: str,
    columns: tuple[Column, ...],
    options: ExportOptions,
    provenance: Provenance | None,
    row_count: int,
) -> bytes:
    """The rows of `sql` as the bytes of one file in the format the options name."""
    reader = batches(cursor, sql)
    if options.format == "xlsx":
        return excel(reader, columns, options, provenance, row_count)
    if options.format == "parquet":
        return parquet(reader, options, provenance)
    if options.format == "md":
        return markdown(reader, columns, options)
    return b"".join(delimited(reader, columns, options))


def markdown(reader: pa.RecordBatchReader, columns: tuple[Column, ...], options: ExportOptions) -> bytes:
    """The rows as a Markdown pipe table (Copy as Markdown): each cell the delimited export's text."""
    text_columns = [type_family(c.type) == "text" for c in columns]
    rows: list[list[str]] = []
    for batch in reader:
        texts = [
            [_text_value(v, options, text_columns[i]) for v in col.to_pylist()]
            for i, col in enumerate(batch.columns)
        ]
        rows += [list(row) for row in zip(*texts, strict=True)]
    numeric = [type_family(c.type) == "number" for c in columns]
    return markdown_table([c.name for c in columns], rows, numeric).encode(options.encoding)


def save(folder: Path, file_name: str, data: bytes, overwrite: bool) -> tuple[str, bool]:
    """Write an export into the export folder. Returns the file's path and whether it was written:
    an existing file is left alone unless `overwrite`."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / file_name
    if target.exists() and not overwrite:
        return str(target), False
    target.write_bytes(data)
    return str(target), True
