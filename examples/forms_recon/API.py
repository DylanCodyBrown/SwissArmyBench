# /// swissarmybench-api
# name = "Forms and reconciliation"
# description = "Forms people design and fill (typed, from Excel or from a source table), kept long and read as a column store per form; reconciliations of a form's entries against a source table, saved once and run each month."
# target = "fastapi"
# base_path = ""
# ///
"""Larkfield Goods' forms and monthly reconciliations, over the project's sandbox (made-up data).

forms          a form's fields, with versions: a field added later keeps old entries readable
batches        each load (typed, Excel or a source table) with its month, who and when
entries        stored long: form, batch, row, field and its value in the field's type
column store   GET /forms/{form_id}/entries: one typed column per field (DuckDB PIVOT)
reconciliations  a form's entries against a source table: keys, compares and tolerances, totals;
               run for a month, the results paged (matched, differences, only in entries,
               only in source, duplicates)

The endpoints above the last four banners are this project's own logic, written by hand. The ones at the
end were made by New endpoint (the wizard) where one of its patterns fits, each under its marker comment:
a form picker's choices, a reconciliation's runs (a search of recon_runs), a run's counts by status (a
summary of recon_results) and its results as a CSV file.
"""

import datetime
import json
import re
from typing import TypedDict

from sab_api import ApiError, Download, connection, download, endpoint, records

TYPES = ("text", "number", "money", "date", "choice", "yes/no", "file")
NUMBERS = ("number", "money")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
EVERY = "all"  # a reconciliation over every month (a year-end check)
STATUSES = ("matched", "difference", "only_entries", "only_source", "duplicate")
MOST_ROWS = 1000


class Field(TypedDict, total=False):
    name: str
    label: str
    type: str
    required: bool
    choices: list[str]
    default: str
    format: str


class FormIn(TypedDict, total=False):
    title: str
    description: str
    fields: list[Field]


class Form(TypedDict):
    form_id: str
    title: str
    description: str
    version: int
    fields: list[Field]


class BatchIn(TypedDict, total=False):
    period: str
    source: str
    loaded_by: str
    rows: list[dict]


class RowsIn(TypedDict):
    rows: list[dict]


class FromTable(TypedDict, total=False):
    period: str
    table: str
    mapping: dict
    period_column: str
    loaded_by: str


class Batch(TypedDict):
    batch_id: int
    form_id: str
    form_version: int
    period: str
    source: str
    loaded_by: str
    loaded_at: str
    rows: int


class ReconIn(TypedDict, total=False):
    title: str
    form_id: str
    source_table: str
    source_period: str
    keys: list[dict]
    compares: list[dict]
    totals: list[dict]


class RunIn(TypedDict):
    period: str


class SignOff(TypedDict):
    by: str


ENTRY_COLUMNS = ("form_id", "batch_id", "row_no", "field", "value_text", "value_number", "value_date",
                 "value_bool")  # fmt: skip
FIELD_COLUMNS = ("field_id", "form_id", "version", "position", "field", "label", "type", "required", "choices",
                 "format")  # fmt: skip


def _db():
    return connection("Sandbox")


def _rows(sql: str, params: list | None = None) -> list[dict]:
    """The sandbox's own SQL (DuckDB's), its rows as dicts: the adapter's query."""
    return records(_db().query(sql, params or []))


def _first(sql: str, params: list | None = None) -> tuple | None:
    """The first row's values, or None."""
    found = _rows(sql, params)
    return tuple(found[0].values()) if found else None


def _tuples(sql: str, params: list | None = None) -> list[tuple]:
    return [tuple(r.values()) for r in _rows(sql, params)]


def _run(sql: str, params: list | None = None) -> int:
    """A write in the sandbox's own SQL: the rows it changed."""
    return int(_rows(sql, params)[0].get("count") or 0)


def _insert(table: str, columns: tuple, rows: list[tuple]) -> None:
    """Many rows in at once: the adapter's write (one Arrow table, all or none)."""
    if rows:
        _db().write(table, [dict(zip(columns, r)) for r in rows])


def _now() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _period(value: str) -> str:
    if not PERIOD.match(str(value or "")):
        raise ApiError(422, f"A period is a month like 2026-03, not {value!r}.")
    return str(value)


# ===== forms =====


def _fields(form_id: str, version: int | None = None) -> tuple[int, list[Field]]:
    if version is None:
        found = _first("SELECT version FROM forms WHERE form_id = ?", [form_id])
        if found is None:
            raise ApiError(404, f"No form {form_id}.")
        version = int(found[0])
    listed = _tuples(
        "SELECT field, label, type, required, choices, format FROM form_fields "
        "WHERE form_id = ? AND version = ? ORDER BY position",
        [form_id, version],
    )
    fields: list[Field] = []
    for name, label, kind, required, choices, fmt in listed:
        field: Field = {"name": name, "label": label or name, "type": kind}
        if required:
            field["required"] = True
        if choices:
            field["choices"] = json.loads(choices)
        if fmt:
            field["format"] = fmt
        fields.append(field)
    return version, fields


def _every_field(form_id: str) -> list[Field]:
    """Every field any version had, the latest version's first: the column store's columns."""
    version, latest = _fields(form_id)
    seen = {f["name"] for f in latest}
    found = _tuples(
        "SELECT field, any_value(type) FROM form_fields WHERE form_id = ? AND version < ? "
        "GROUP BY field ORDER BY min(position)",
        [form_id, version],
    )
    older: list[Field] = [{"name": n, "label": n, "type": t} for n, t in found if n not in seen]
    return latest + older


def _checked(fields: list[Field]) -> list[Field]:
    if not fields:
        raise ApiError(422, "A form needs at least one field.")
    names = set()
    out: list[Field] = []
    for at, field in enumerate(fields, start=1):
        name = str(field.get("name") or "").strip()
        if not NAME.match(name):
            raise ApiError(
                422, f"Field {at}: a name is small letters, digits and _ ({name!r})."
            )
        if name in names:
            raise ApiError(422, f"Two fields are called {name}.")
        names.add(name)
        kind = str(field.get("type") or "text")
        if kind not in TYPES:
            raise ApiError(422, f"{name}: a type is one of {', '.join(TYPES)}.")
        if kind == "choice" and not field.get("choices"):
            raise ApiError(422, f"{name}: a choice needs its choices.")
        out.append({**field, "name": name, "type": kind})
    return out


@endpoint("GET", "/forms")
def list_forms(full: bool = False) -> list[dict]:
    """Every form: its name, title, version and how many fields (?full=true: each one's definition, as
    the form picker takes them)."""
    found = _rows(
        "SELECT f.form_id, f.title, f.version, count(ff.field) AS fields, f.updated_at FROM forms f "
        "LEFT JOIN form_fields ff ON ff.form_id = f.form_id AND ff.version = f.version "
        "GROUP BY ALL ORDER BY f.title"
    )
    if not full:
        return found
    return [{"name": f["form_id"], **get_form(f["form_id"])} for f in found]


@endpoint("GET", "/forms/{form_id}")
def get_form(form_id: str, version: int = 0) -> Form:
    """A form's definition (its latest version, or ?version=)."""
    found = _first("SELECT title, description FROM forms WHERE form_id = ?", [form_id])
    if found is None:
        raise ApiError(404, f"No form {form_id}.")
    number, fields = _fields(form_id, version or None)
    return {"form_id": form_id, "title": found[0], "description": found[1] or "", "version": number,
            "fields": fields}  # fmt: skip


@endpoint("PUT", "/forms/{form_id}")
def save_form(form_id: str, form: FormIn) -> Form:
    """Save a form: a new version when its fields change (older entries stay readable)."""
    if not NAME.match(form_id):
        raise ApiError(422, "A form's name is small letters, digits and _ .")
    fields = _checked(list(form.get("fields") or []))
    title = str(form.get("title") or form_id)
    found = _first("SELECT version FROM forms WHERE form_id = ?", [form_id])
    version = 1
    if found is not None:
        version, before = _fields(form_id)
        if before != fields:
            version += 1
        _run(
            "UPDATE forms SET title = ?, description = ?, version = ?, updated_at = ? WHERE form_id = ?",
            [title, form.get("description") or "", version, _now(), form_id],
        )
    else:
        _run(
            "INSERT INTO forms VALUES (?, ?, ?, ?, ?)",
            [form_id, title, form.get("description") or "", version, _now()],
        )
    _run("DELETE FROM form_fields WHERE form_id = ? AND version = ?", [form_id, version])
    _insert(
        "form_fields",
        FIELD_COLUMNS,
        [
            (
                f"{form_id}:{version}:{f['name']}",
                form_id,
                version,
                at,
                f["name"],
                f.get("label") or f["name"],
                f["type"],
                bool(f.get("required")),
                json.dumps(f["choices"]) if f.get("choices") else None,
                f.get("format") or None,
            )  # fmt: skip
            for at, f in enumerate(fields, start=1)
        ],
    )
    return get_form(form_id)


@endpoint("DELETE", "/forms/{form_id}")
def delete_form(form_id: str) -> None:
    """Remove a form that has no entries."""
    if _first("SELECT count(*) FROM batches WHERE form_id = ?", [form_id])[0]:
        raise ApiError(409, f"{form_id} has entries: remove its batches first.")
    _run("DELETE FROM form_fields WHERE form_id = ?", [form_id])
    _run("DELETE FROM forms WHERE form_id = ?", [form_id])


# ===== batches and entries: stored long =====


def _value(
    field: Field, raw: object
) -> tuple[str | None, float | None, str | None, bool | None]:
    """A value in its field's type: (text, number, date, yes/no), one of them set."""
    kind = field["type"]
    if kind in NUMBERS:
        if isinstance(raw, str):
            raw = raw.replace(",", "").replace("£", "").strip()
        return None, float(raw), None, None  # type: ignore[arg-type]
    if kind == "date":
        text = raw.isoformat() if hasattr(raw, "isoformat") else str(raw)
        return None, None, datetime.date.fromisoformat(text[:10]).isoformat(), None
    if kind == "yes/no":
        if isinstance(raw, bool):
            return None, None, None, raw
        word = str(raw).strip().lower()
        if word in ("yes", "y", "true", "1"):
            return None, None, None, True
        if word in ("no", "n", "false", "0"):
            return None, None, None, False
        raise ValueError(raw)
    text = str(raw)
    if kind == "choice" and text not in (field.get("choices") or []):
        raise ValueError(raw)
    return text, None, None, None


def _long(
    form_id: str, batch_id: int, first: int, fields: list[Field], rows: list[dict]
) -> list[tuple]:
    """Rows of {field: value} as long entries, or a 422 naming the first problems."""
    out: list[tuple] = []
    problems: list[str] = []
    by_name = {f["name"]: f for f in fields}
    for at, row in enumerate(rows):
        unknown = [k for k in row if k not in by_name]
        if unknown:
            problems.append(f"Row {first + at}: no field {unknown[0]}.")
        for field in fields:
            raw = row.get(field["name"])
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                if field.get("required"):
                    problems.append(f"Row {first + at}: {field['name']} is required.")
                continue
            try:
                text, number, day, yes = _value(field, raw)
            except (TypeError, ValueError):
                problems.append(
                    f"Row {first + at}: {field['name']} is not a {field['type']} ({raw!r})."
                )
                continue
            out.append(
                (form_id, batch_id, first + at, field["name"], text, number, day, yes)
            )
        if len(problems) >= 20:
            break
    if problems:
        raise ApiError(422, " ".join(problems[:20]))
    return out


def _numbered(table: str, column: str, values: list, placeholders: str) -> int:
    """A row inserted with the next number in its first column, in one statement (so two callers at once
    never take the same number): the number."""
    found = _first(
        f"INSERT INTO {table} SELECT coalesce(max({column}), 0) + 1, {placeholders} FROM {table} "  # noqa: S608
        f"RETURNING {column}",
        values,
    )
    return int(found[0])


def _batch(batch_id: int) -> Batch:
    found = _rows("SELECT * FROM batches WHERE batch_id = ?", [batch_id])
    if not found:
        raise ApiError(404, f"No batch {batch_id}.")
    return found[0]  # type: ignore[return-value]


@endpoint("POST", "/forms/{form_id}/batches", status=201)
def new_batch(form_id: str, batch: BatchIn) -> Batch:
    """A new batch of a form's entries for a month: typed rows or an Excel upload's ({field: value})."""
    period = _period(batch.get("period", ""))
    version, fields = _fields(form_id)
    rows = list(batch.get("rows") or [])
    _long(form_id, 0, 1, fields, rows)  # every row checked before the batch is made
    batch_id = _numbered(
        "batches", "batch_id",
        [form_id, version, period, batch.get("source") or "typed", batch.get("loaded_by") or "", _now(), len(rows)],
        "?, ?, ?, ?, ?, ?, ?",
    )  # fmt: skip
    _insert("entries", ENTRY_COLUMNS, _long(form_id, batch_id, 1, fields, rows))
    return _batch(batch_id)


@endpoint("POST", "/batches/{batch_id}/rows", status=201)
def add_rows(batch_id: int, more: RowsIn) -> Batch:
    """More rows for a batch (a big upload sent in parts)."""
    found = _batch(batch_id)
    _, fields = _fields(found["form_id"], found["form_version"])
    rows = list(more.get("rows") or [])
    _insert("entries", ENTRY_COLUMNS, _long(found["form_id"], batch_id, int(found["rows"]) + 1, fields, rows))
    _run("UPDATE batches SET rows = rows + ? WHERE batch_id = ?", [len(rows), batch_id])
    return _batch(batch_id)


@endpoint("POST", "/forms/{form_id}/batches/from-table", status=201)
def batch_from_table(form_id: str, load: FromTable) -> Batch:
    """A batch read from a source table in the sandbox (a Trino or Dynamics 365 copy): its columns
    mapped to the form's fields ({field: column}), one month (period_column) or every row."""
    period = _period(load.get("period", ""))
    table = str(load.get("table") or "")
    if not TABLE.match(table):
        raise ApiError(422, f"Name a sandbox table, not {table!r}.")
    version, fields = _fields(form_id)
    mapping = dict(load.get("mapping") or {})
    by_name = {f["name"]: f for f in fields}
    pairs = [
        (f, str(c)) for f, c in mapping.items() if f in by_name and TABLE.match(str(c))
    ]
    if not pairs:
        raise ApiError(
            422, "Map at least one of the form's fields to a column: {field: column}."
        )
    batch_id = _numbered(
        "batches", "batch_id", [form_id, version, period, f"table:{table}", load.get("loaded_by") or "", _now()],
        "?, ?, ?, ?, ?, ?, 0",
    )  # fmt: skip
    where, params = "", [form_id, batch_id]
    if load.get("period_column"):
        if not TABLE.match(str(load["period_column"])):
            raise ApiError(422, "period_column is a column's name.")
        where = f" WHERE CAST({_quote(load['period_column'])} AS VARCHAR) = ?"
        params.append(period)
    parts = []
    for field, column in pairs:
        kind = by_name[field]["type"]
        value = f"CAST({_quote(column)} AS VARCHAR)"
        text = "NULL" if kind in NUMBERS + ("date", "yes/no") else value
        number = f"TRY_CAST({_quote(column)} AS DOUBLE)" if kind in NUMBERS else "NULL"
        day = f"TRY_CAST({_quote(column)} AS DATE)" if kind == "date" else "NULL"
        yes = f"TRY_CAST({_quote(column)} AS BOOLEAN)" if kind == "yes/no" else "NULL"
        parts.append(f"SELECT row_no, '{field}' AS field, {text} AS t, {number} AS n, {day} AS d, {yes} AS b "
                     f"FROM src WHERE {_quote(column)} IS NOT NULL")  # fmt: skip
    _run(
        "INSERT INTO entries SELECT ?, ?, row_no, field, t, n, d, b FROM (WITH src AS (SELECT *, "  # noqa: S608
        f"row_number() OVER () AS row_no FROM {_quote(table)}{where}) "
        + " UNION ALL ".join(parts)
        + ")",
        params,
    )
    counted = _first("SELECT count(DISTINCT row_no) FROM entries WHERE batch_id = ?", [batch_id])
    _run("UPDATE batches SET rows = ? WHERE batch_id = ?", [int(counted[0]), batch_id])
    return _batch(batch_id)


@endpoint("GET", "/forms/{form_id}/batches")
def list_batches(form_id: str, period: str = "") -> list[Batch]:
    """A form's batches, newest first (one month with ?period=)."""
    if period:
        return _rows("SELECT * FROM batches WHERE form_id = ? AND period = ? ORDER BY batch_id DESC",
                     [form_id, _period(period)])  # type: ignore[return-value]  # fmt: skip
    return _rows("SELECT * FROM batches WHERE form_id = ? ORDER BY batch_id DESC", [form_id])  # type: ignore[return-value]


@endpoint("DELETE", "/batches/{batch_id}")
def delete_batch(batch_id: int) -> None:
    """Remove a batch and its entries."""
    _batch(batch_id)
    _run("DELETE FROM entries WHERE batch_id = ?", [batch_id])
    _run("DELETE FROM batches WHERE batch_id = ?", [batch_id])


# ===== the column store: one typed column per field (DuckDB PIVOT) =====

_LETTER = {"number": "n", "money": "n", "date": "d", "yes/no": "b"}


def column_store(
    form_id: str, period: str = "", batch_id: int = 0
) -> tuple[str, list, list[Field]]:
    """The SELECT of a form's entries as one row each, a typed column per field, and its parameters."""
    fields = _every_field(form_id)
    names = ", ".join("'" + f["name"] + "'" for f in fields)
    chosen = ", ".join(f"{_quote(f['name'] + '_' + _LETTER.get(f['type'], 't'))} AS {_quote(f['name'])}"
                       for f in fields)  # fmt: skip
    where, params = "form_id = ?", [form_id]
    if batch_id:
        where += " AND batch_id = ?"
        params.append(batch_id)
    if period and period != EVERY:
        where += " AND batch_id IN (SELECT batch_id FROM batches WHERE form_id = ? AND period = ?)"
        params += [form_id, _period(period)]
    sql = (
        f"SELECT batch_id, row_no, {chosen} FROM (PIVOT (SELECT batch_id, row_no, field, value_text, "  # noqa: S608
        f"value_number, value_date, value_bool FROM entries WHERE {where}) ON field IN ({names}) "
        "USING first(value_text) AS t, first(value_number) AS n, first(value_date) AS d, "
        "first(value_bool) AS b)"
    )
    return sql, params, fields


@endpoint("GET", "/forms/{form_id}/columns")
def store_columns(form_id: str) -> list[dict]:
    """The column store's columns: each field and its type (every version's)."""
    return [{"name": f["name"], "type": f["type"]} for f in _every_field(form_id)]


@endpoint("GET", "/forms/{form_id}/entries")
def entries(
    form_id: str, period: str = "", batch_id: int = 0, limit: int = 100, offset: int = 0
) -> list[dict]:
    """A form's entries from its column store, a page at a time."""
    sql, params, _ = column_store(form_id, period, batch_id)
    return _rows(f"{sql} ORDER BY batch_id, row_no LIMIT ? OFFSET ?",
                 params + [max(1, min(limit, MOST_ROWS)), max(0, offset)])  # fmt: skip


@endpoint("GET", "/forms/{form_id}/entries/count")
def entries_count(form_id: str, period: str = "") -> dict:
    """How many entries a form has (one month with ?period=)."""
    sql, params, _ = column_store(form_id, period)
    found = _first(f"SELECT count(*) AS rows FROM ({sql})", params)  # noqa: S608
    return {"form_id": form_id, "period": period, "rows": int(found[0])}


# ===== reconciliations: saved once, run each month =====


def _recon(recon_id: str) -> dict:
    found = _rows("SELECT * FROM recon_defs WHERE recon_id = ?", [recon_id])
    if not found:
        raise ApiError(404, f"No reconciliation {recon_id}.")
    one = found[0]
    for part in ("keys", "compares", "totals"):
        one[part] = json.loads(one[part] or "[]")
    return one


@endpoint("GET", "/recons")
def list_recons() -> list[dict]:
    """Every reconciliation definition."""
    return _rows("SELECT recon_id, title, form_id, source_table, updated_at FROM recon_defs ORDER BY title")


@endpoint("GET", "/recons/{recon_id}")
def get_recon(recon_id: str) -> dict:
    """A reconciliation's definition: its form, source table, keys, compares with tolerances, totals."""
    return _recon(recon_id)


@endpoint("PUT", "/recons/{recon_id}")
def save_recon(recon_id: str, recon: ReconIn) -> dict:
    """Save a reconciliation definition. keys: [{field, column}]; compares: [{field, column, tolerance}];
    totals: [{field, column}]; source_period: the source's month column (text like 2026-03)."""
    if not NAME.match(recon_id):
        raise ApiError(422, "A reconciliation's name is small letters, digits and _ .")
    form_id = str(recon.get("form_id") or "")
    fields = {f["name"]: f for f in _every_field(form_id)}
    table = str(recon.get("source_table") or "")
    if not TABLE.match(table):
        raise ApiError(422, "Name the source table (a sandbox table).")
    keys = list(recon.get("keys") or [])
    if not keys:
        raise ApiError(
            422, "A reconciliation needs at least one key: [{field, column}]."
        )
    for part in ("keys", "compares", "totals"):
        for pair in recon.get(part) or []:
            if pair.get("field") not in fields:
                raise ApiError(
                    422, f"{part}: {form_id} has no field {pair.get('field')!r}."
                )
            if not TABLE.match(str(pair.get("column") or "")):
                raise ApiError(
                    422, f"{part}: {pair.get('column')!r} is not a column's name."
                )
    period = str(recon.get("source_period") or "")
    if period and not TABLE.match(period):
        raise ApiError(422, "source_period is a column's name.")
    row = [recon_id, recon.get("title") or recon_id, form_id, table, period, json.dumps(keys),
           json.dumps(list(recon.get("compares") or [])), json.dumps(list(recon.get("totals") or [])), _now()]  # fmt: skip
    _run("DELETE FROM recon_defs WHERE recon_id = ?", [recon_id])
    _run("INSERT INTO recon_defs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
    return _recon(recon_id)


@endpoint("DELETE", "/recons/{recon_id}")
def delete_recon(recon_id: str) -> None:
    """Remove a reconciliation definition (its runs stay)."""
    _recon(recon_id)
    _run("DELETE FROM recon_defs WHERE recon_id = ?", [recon_id])


def _side(column: str, kind: str) -> str:
    if kind in NUMBERS:
        return f"TRY_CAST({column} AS DOUBLE)"
    if kind == "date":
        return f"TRY_CAST({column} AS DATE)"
    return f"CAST({column} AS VARCHAR)"


def _key(column: str, kind: str) -> str:
    return f"CAST({_side(column, kind)} AS VARCHAR)"


@endpoint("POST", "/recons/{recon_id}/runs", status=201)
def run_recon(recon_id: str, run: RunIn) -> dict:
    """Run a reconciliation for a month (or "all"): every key matched, different, only in the entries,
    only in the source or duplicated; the totals of both sides. The results are kept for paging."""
    period = run.get("period", "")
    period = EVERY if period == EVERY else _period(period)
    recon = _recon(recon_id)
    store, params, fields = column_store(recon["form_id"], period)
    kinds = {f["name"]: f["type"] for f in fields}
    table = _quote(recon["source_table"])
    # A key read the same way on both sides: a number field's as a number (12 and 12.0 are one key).
    e_key = " || '|' || ".join(
        _key(_quote(k["field"]), kinds[k["field"]]) for k in recon["keys"]
    )
    s_key = " || '|' || ".join(
        _key(_quote(k["column"]), kinds[k["field"]]) for k in recon["keys"]
    )
    compares = recon["compares"]
    e_cols = "".join(
        f", first({_side(_quote(c['field']), kinds[c['field']])}) AS e{i}"
        for i, c in enumerate(compares)
    )
    s_cols = "".join(
        f", first({_side(_quote(c['column']), kinds[c['field']])}) AS s{i}"
        for i, c in enumerate(compares)
    )
    off_parts = []
    for i, c in enumerate(compares):
        if kinds[c["field"]] in NUMBERS:
            tolerance = float(c.get("tolerance") or 0)
            off_parts.append(f"CASE WHEN abs(coalesce(e{i}, 0) - coalesce(s{i}, 0)) > {tolerance} "
                             f"THEN '{c['field']}' END")  # fmt: skip
        else:
            off_parts.append(
                f"CASE WHEN e{i} IS DISTINCT FROM s{i} THEN '{c['field']}' END"
            )
    off = f"concat_ws(', ', {', '.join(off_parts)})" if off_parts else "''"
    first_number = next(
        (i for i, c in enumerate(compares) if kinds[c["field"]] in NUMBERS), None
    )
    difference = (
        f"coalesce(e{first_number}, 0) - coalesce(s{first_number}, 0)"
        if first_number is not None
        else "NULL"
    )
    e_json = (
        "json_object("
        + ", ".join(f"'{c['field']}', e{i}" for i, c in enumerate(compares))
        + ")"
        if compares
        else "'{}'"
    )
    s_json = (
        "json_object("
        + ", ".join(f"'{c['field']}', s{i}" for i, c in enumerate(compares))
        + ")"
        if compares
        else "'{}'"
    )
    where, s_params = "", []
    if recon.get("source_period") and period != EVERY:
        where = f" WHERE CAST({_quote(recon['source_period'])} AS VARCHAR) = ?"
        s_params = [period]
    run_id = _numbered("recon_runs", "run_id", [recon_id, period, _now()],
                       "?, ?, ?, 0, 0, 0, 0, 0, '[]', NULL, NULL")  # fmt: skip
    _run(
        "INSERT INTO recon_results SELECT ?, CASE WHEN en > 1 OR sn > 1 THEN 'duplicate' "  # noqa: S608
        "WHEN sn IS NULL THEN 'only_entries' WHEN en IS NULL THEN 'only_source' "
        f"WHEN fields_off <> '' THEN 'difference' ELSE 'matched' END, record_key, "
        f"CASE WHEN en IS NULL THEN NULL ELSE CAST({e_json} AS VARCHAR) END, "
        f"CASE WHEN sn IS NULL THEN NULL ELSE CAST({s_json} AS VARCHAR) END, difference, fields_off FROM ("
        f"SELECT *, CASE WHEN en IS NULL OR sn IS NULL THEN '' ELSE {off} END AS fields_off, "
        f"CASE WHEN en IS NULL OR sn IS NULL THEN NULL ELSE {difference} END AS difference FROM ("
        f"SELECT * FROM (SELECT {e_key} AS record_key, count(*) AS en{e_cols} FROM ({store}) GROUP BY 1) "
        f"FULL OUTER JOIN (SELECT {s_key} AS record_key, count(*) AS sn{s_cols} FROM {table}{where} "
        "GROUP BY 1) USING (record_key)))",
        [run_id] + params + s_params,
    )
    found = _tuples("SELECT status, count(*) FROM recon_results WHERE run_id = ? GROUP BY status", [run_id])
    counts = {s: 0 for s in STATUSES} | {s: int(n) for s, n in found}
    totals = []
    for t in recon["totals"]:
        entries_total = float(
            _first(f"SELECT sum(TRY_CAST({_quote(t['field'])} AS DOUBLE)) FROM ({store})", params)[0] or 0  # noqa: S608
        )
        source_total = float(
            _first(f"SELECT sum(TRY_CAST({_quote(t['column'])} AS DOUBLE)) FROM {table}{where}", s_params)[0]  # noqa: S608
            or 0
        )
        totals.append({"field": t["field"], "entries": round(entries_total, 2), "source": round(source_total, 2),
                       "difference": round(entries_total - source_total, 2)})  # fmt: skip
    _run(
        "UPDATE recon_runs SET matched = ?, differences = ?, only_entries = ?, only_source = ?, duplicates = ?, "
        "totals = ? WHERE run_id = ?",
        [
            counts["matched"],
            counts["difference"],
            counts["only_entries"],
            counts["only_source"],
            counts["duplicate"],
            json.dumps(totals),
            run_id,
        ],  # fmt: skip
    )
    return get_run(run_id)


def _run_out(row: dict) -> dict:
    row["totals"] = json.loads(row.get("totals") or "[]")
    return row


@endpoint("GET", "/runs/{run_id}")
def get_run(run_id: int) -> dict:
    """A run: its month, counts by status, totals and sign-off."""
    found = _rows("SELECT * FROM recon_runs WHERE run_id = ?", [run_id])
    if not found:
        raise ApiError(404, f"No run {run_id}.")
    return _run_out(found[0])


@endpoint("GET", "/runs/{run_id}/results")
def run_results(
    run_id: int, status: str = "", limit: int = 100, offset: int = 0
) -> list[dict]:
    """A run's results a page at a time: one status (matched, difference, only_entries, only_source,
    duplicate) or every one but matched."""
    page = [max(1, min(limit, MOST_ROWS)), max(0, offset)]
    if status:
        if status not in STATUSES:
            raise ApiError(422, f"A status is one of {', '.join(STATUSES)}.")
        return _rows("SELECT status, record_key, entry_values, source_values, difference, fields_off "
                     "FROM recon_results WHERE run_id = ? AND status = ? ORDER BY record_key LIMIT ? OFFSET ?",
                     [run_id, status] + page)  # fmt: skip
    return _rows("SELECT status, record_key, entry_values, source_values, difference, fields_off "
                 "FROM recon_results WHERE run_id = ? AND status <> 'matched' "
                 "ORDER BY status, record_key LIMIT ? OFFSET ?", [run_id] + page)  # fmt: skip


@endpoint("POST", "/runs/{run_id}/signoff")
def sign_off(run_id: int, signed: SignOff) -> dict:
    """Sign a run off: who and when."""
    get_run(run_id)
    if not str(signed.get("by") or "").strip():
        raise ApiError(422, "Say who signs it off.")
    _run("UPDATE recon_runs SET signed_off_by = ?, signed_off_at = ? WHERE run_id = ?",
         [signed["by"], _now(), run_id])  # fmt: skip
    return get_run(run_id)


# ===== forms: Choices (connection("Sandbox") through the adapter) =====
# pattern: choices of forms


class FormsChoice(TypedDict, total=False):
    form_id: str
    title: str


@endpoint("GET", "/forms/choices")
def choices_forms(search: str = "", limit: int = 200) -> list[FormsChoice]:
    """forms: its choices for a dropdown (form_id and title).

    Sorted by title, `limit` at most; ?search= narrows by title."""
    filters = [["title", "like", f"%{search}%"]] if search else []
    plan = {"columns": ["form_id", "title"], "filters": filters, "sort": [["title", "asc"]], "limit": limit}
    return records(connection("Sandbox").read("forms", plan))


# ===== recon_runs: Search (connection("Sandbox") through the adapter) =====
# pattern: search of recon_runs


class ReconRunsFound(TypedDict, total=False):
    run_id: int
    recon_id: str
    period: str
    ran_at: datetime.datetime
    matched: int
    differences: int
    only_entries: int
    only_source: int
    duplicates: int
    totals: str
    signed_off_by: str
    signed_off_at: datetime.datetime


@endpoint("GET", "/recon_runs/search")
def search_recon_runs(
    recon_id: str | None = None,
    period: str | None = None,
    sort: str = "run_id",
    descending: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[ReconRunsFound]:
    """recon_runs: the rows that match, a page at a time.

    recon_id and period narrow it. The filters, the sort and the page go to the source."""
    columns = [
        "run_id",
        "recon_id",
        "period",
        "ran_at",
        "matched",
        "differences",
        "only_entries",
        "only_source",
        "duplicates",
        "totals",
        "signed_off_by",
        "signed_off_at",
    ]
    filters: list[list] = []
    if recon_id is not None:
        filters.append(["recon_id", "=", recon_id])
    if period is not None:
        filters.append(["period", "=", period])
    if sort not in columns:
        raise ApiError(422, "sort is one of the columns it answers.")
    way = "desc" if descending else "asc"
    plan = {"columns": columns, "filters": filters, "sort": [[sort, way]], "limit": limit, "offset": offset}
    return records(connection("Sandbox").read("recon_runs", plan))


# ===== recon_results: Summary (connection("Sandbox") through the adapter) =====
# pattern: summary of recon_results


class ReconResultsRunIdStatusSummary(TypedDict, total=False):
    run_id: int
    status: str
    rows: int


@endpoint("GET", "/recon_results/summary/run_id/status")
def summary_recon_results_by_run_id_status(
    run_id: int | None = None,
    status: str | None = None,
    limit: int = 1000,
) -> list[ReconResultsRunIdStatusSummary]:
    """recon_results: the row count by run_id and status.

    The group and the totals are the read's plan: the source does them where it can."""
    filters: list[list] = []
    if run_id is not None:
        filters.append(["run_id", "=", run_id])
    if status is not None:
        filters.append(["status", "=", status])
    plan = {
        "group": ["run_id", "status"],
        "totals": [{"fn": "count", "name": "rows"}],
        "filters": filters,
        "sort": [["run_id", "asc"], ["status", "asc"]],
        "limit": limit,
    }
    return records(connection("Sandbox").read("recon_results", plan))


# ===== recon_results: Export (connection("Sandbox") through the adapter) =====
# pattern: export of recon_results


@endpoint("GET", "/recon_results/export.csv")
def export_recon_results(limit: int = 100000) -> Download:
    """recon_results as a CSV file to save.

    It carries every column, sorted by record_key: read from the source a batch at a time, `limit` rows at
    most."""
    columns = [
        "run_id",
        "status",
        "record_key",
        "entry_values",
        "source_values",
        "difference",
        "fields_off",
    ]
    plan = {"columns": columns, "sort": [["record_key", "asc"]], "limit": limit}
    return download(connection("Sandbox").read("recon_results", plan), "recon_results.csv")
