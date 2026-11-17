# ruff: noqa: E501 (the kernel's TypeScript is written as it runs)
"""TypeScript cells in a code app's data notebook (phase 2), run on Deno's Jupyter kernel: the rules.

The owner (2026-11-17): "we can use Dataverse to get the grids and transform the data with typescript ...
Then we just get a data notebook with SQL and typescript cells ... on the back of duck db".

A code app's data notebook (`data.ipynb` in the code app's folder) has TypeScript cells and SQL cells that
run in ONE Deno kernel (`deno jupyter --kernel`), so they share state as Python's cells do, and ONE DuckDB
(DuckDB's Node package, `@duckdb/node-api`, imported by its npm: specifier): a SQL cell is
`await sab.sql("...")` in that kernel, so a TypeScript cell sees what SQL made and the other way round.
A SQL cell that names a connection of its own (`%%sql Warehouse`, the database's own SQL) still runs in
the Python kernel as everywhere else.

Here, as text and rules (no I/O):
  PRELUDE      the kernel's `sab` (run quietly once it starts): `sab.sql` (a query, or a tagged template
               whose values are bound as parameters), `sab.table(name, rows)` (an array of objects as a
               DuckDB table), `sab.tables()`, `sab.db` (the connection itself). A query that names a
               connection's table (`[Finance Captive].orders`) asks this server first, through a
               route of the kernel's own key, which reads the table (the base's connection_tables) into
               Parquet in the notebook's temporary folder and hands back the query pointed at it
  tables       the open tables (a tab in the grid), after their steps, as views over Parquet files in the
               notebook's temporary folder (never in the project), made again when one changes
  outputs      a table result is one MIME bundle (TABLE_MIME: columns, types, the first rows, the total,
               its id, so Open as grid can write it whole); text as text; colour codes taken out
  errors       Deno's error as the error panel's detail (the base's shape: chain, frames, title,
               explanation, fixes; a DuckDB error's place by the base's sql_position)
"""

from __future__ import annotations

import json
import re
from typing import Any

from swissarmybench.domain import errors as base_errors

# DuckDB's Node package, the same DuckDB as the app's Python (2.0.0; docs/verified.md, 2026-11-17).
DUCKDB_PACKAGE = "npm:@duckdb/node-api@2.0.0-r.1"
TABLE_MIME = "application/vnd.swissarmybench.table+json"
SHOWN_ROWS = 200  # a table result's rows drawn in the cell (Open as grid has every row)
PREPARE_VARIABLE = "SWISSARMYBENCH_TS_PREPARE"  # the kernel's own route to read a connection's table
TEMP_VARIABLE = "SWISSARMYBENCH_TS_TEMP"  # the notebook's temporary folder
MAX_CODE = 1_000_000
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_RESULT_ID = re.compile(r"^r[0-9]{1,9}$")
_AT = re.compile(r"at (?:(\S+) \()?<anonymous>:(\d+):(\d+)\)?")
_VIEW_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class TsCellError(ValueError):
    """Code a TypeScript cell cannot run, or a name it cannot have."""


PRELUDE = """\
import { DuckDBInstance as __SabDuckDB } from "__PACKAGE__";
{
  const instance = await __SabDuckDB.create(":memory:");
  const db = await instance.connect();
  const TABLE = "__MIME__";
  const SHOWN = __SHOWN__;
  const results = new Map<string, { query: string; params?: Record<string, unknown> }>();
  const synced = new Set<string>();
  let made = 0;
  const env = (name: string): string => Deno.env.get(name) ?? "";
  const quote = (name: string): string => '"' + String(name).replaceAll('"', '""') + '"';
  const literal = (text: string): string => "'" + String(text).replaceAll("'", "''") + "'";

  class SabTable {
    constructor(
      readonly id: string,
      readonly columns: string[],
      readonly types: string[],
      readonly rows: Record<string, unknown>[],
    ) {}
    get total(): number { return this.rows.length; }
    toJSON(): Record<string, unknown>[] { return this.rows; }
    [Symbol.iterator]() { return this.rows[Symbol.iterator](); }
    [Symbol.for("Jupyter.display")]() {
      const n = this.total, c = this.columns.length;
      const said = `${n} row${n === 1 ? "" : "s"}, ${c} column${c === 1 ? "" : "s"}`;
      return {
        [TABLE]: { id: this.id, columns: this.columns, types: this.types, rows: this.rows.slice(0, SHOWN), total: this.total },
        "text/plain": said,
      };
    }
  }

  async function prepare(text: string): Promise<string> {
    const url = env("__PREPARE__");
    if (!url || !text.includes("[")) return text;
    const answer = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sql: text }) });
    const said = await answer.json();
    if (!answer.ok) throw new Error(String(said?.error ?? `The connection's table could not be read (${answer.status}).`));
    for (const [name, path] of Object.entries(said.tables ?? {})) {
      await db.run(`CREATE OR REPLACE VIEW ${quote(name)} AS SELECT * FROM read_parquet(${literal(String(path))})`);
    }
    return String(said.sql ?? text);
  }

  async function run(query: string, params?: Record<string, unknown>): Promise<SabTable> {
    const id = `r${++made}`;
    const reader = params ? await db.runAndReadAll(query, params as never) : await db.runAndReadAll(query);
    const columns = reader.columnNames();
    const types = reader.columnTypes().map((t) => t.toString());
    const rows = reader.getRowObjectsJson() as Record<string, unknown>[];
    results.set(id, { query, params });
    return new SabTable(id, columns, types, rows);
  }

  async function sql(text: string | TemplateStringsArray, ...values: unknown[]): Promise<SabTable> {
    if (typeof text === "string") return run(await prepare(text));
    let query = text[0] ?? "";
    const params: Record<string, unknown> = {};
    values.forEach((value, i) => {
      params[`p${i + 1}`] = value;
      query += `$p${i + 1}` + (text[i + 1] ?? "");
    });
    return run(await prepare(query), values.length ? params : undefined);
  }

  async function table(name: string, rows: Record<string, unknown>[] | SabTable): Promise<SabTable> {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) throw new Error(`${name} cannot be a table's name: letters, digits and _ only.`);
    const list = rows instanceof SabTable ? rows.rows : rows;
    if (!Array.isArray(list)) throw new Error("sab.table takes an array of objects (one per row).");
    const folder = env("__TEMP__") || Deno.makeTempDirSync();
    const path = `${folder}/${name}.jsonl`;
    Deno.writeTextFileSync(path, list.map((r) => JSON.stringify(r)).join("\\n") + "\\n");
    await db.run(`CREATE OR REPLACE TABLE ${quote(name)} AS SELECT * FROM read_json_auto(${literal(path)})`);
    Deno.removeSync(path);
    return run(`SELECT * FROM ${quote(name)}`);
  }

  async function tables(): Promise<string[]> {
    const reader = await db.runAndReadAll("SELECT table_name FROM information_schema.tables ORDER BY 1");
    return reader.getRowObjectsJson().map((r) => String((r as Record<string, unknown>).table_name));
  }

  async function save(id: string, path: string): Promise<number> {
    const kept = results.get(id);
    if (!kept) throw new Error(`There is no result ${id} in this kernel any more: run its cell again.`);
    const copy = `COPY (${kept.query}) TO ${literal(path)} (FORMAT parquet)`;
    if (kept.params) await db.run(copy, kept.params as never);
    else await db.run(copy);
    return 1;
  }

  async function sync(views: Record<string, string>): Promise<string[]> {
    for (const name of [...synced]) {
      if (!(name in views)) { await db.run(`DROP VIEW IF EXISTS ${quote(name)}`); synced.delete(name); }
    }
    for (const [name, path] of Object.entries(views)) {
      await db.run(`CREATE OR REPLACE VIEW ${quote(name)} AS SELECT * FROM read_parquet(${literal(path)})`);
      synced.add(name);
    }
    return [...synced];
  }

  (globalThis as Record<string, unknown>).sab = { sql, table, tables, db, save, sync, SabTable };
}
"""
for _mark, _value in (
    ("__PACKAGE__", DUCKDB_PACKAGE),
    ("__MIME__", TABLE_MIME),
    ("__SHOWN__", str(SHOWN_ROWS)),
    ("__PREPARE__", PREPARE_VARIABLE),
    ("__TEMP__", TEMP_VARIABLE),
):
    PRELUDE = PRELUDE.replace(_mark, _value)


# The kernel's `sab` for the editor's language service (Monaco's TypeScript), so a cell's member lists and
# parameter info know it.
DECLARATIONS = """\
/** A table result: its columns, DuckDB's types, its rows (as JSON reads them), how many. */
interface SabTable extends Iterable<Record<string, unknown>> {
  readonly id: string;
  readonly columns: string[];
  readonly types: string[];
  readonly rows: Record<string, unknown>[];
  readonly total: number;
}
/** The data notebook's DuckDB (one for the SQL and TypeScript cells): the open tables are views by name. */
declare const sab: {
  /** A query; as a tagged template, its values are bound as parameters. */
  sql(query: string): Promise<SabTable>;
  sql(strings: TemplateStringsArray, ...values: unknown[]): Promise<SabTable>;
  /** An array of objects (or a result) as a DuckDB table of this name. */
  table(name: string, rows: Record<string, unknown>[] | SabTable): Promise<SabTable>;
  /** The tables and views DuckDB holds. */
  tables(): Promise<string[]>;
  /** DuckDB's own connection (@duckdb/node-api). */
  readonly db: unknown;
};
"""


def _js(value: Any) -> str:
    """A value as a JavaScript literal (JSON is one; `</` and the line separators made safe too)."""
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def check_code(code: Any) -> str:
    if not isinstance(code, str):
        raise TsCellError('Send {"code": "..."}: the cell\'s TypeScript.')
    if len(code) > MAX_CODE:
        raise TsCellError(f"A cell holds at most {MAX_CODE:,} characters.")
    return code


def sql_cell(text: Any) -> str:
    """A SQL cell of the code app's data notebook, as the kernel runs it: DuckDB's, in the kernel's DuckDB
    (the TypeScript cells' too). Its last line is the result, drawn as a table."""
    query = check_code(text).strip().rstrip(";").strip()
    if not query:
        raise TsCellError("The SQL cell is empty.")
    return f"await sab.sql({_js(query)})"


def sync_code(views: dict[str, str]) -> str:
    """The open tables as the kernel's views: {name: a Parquet file}. Names are checked: a view's name is a
    TypeScript and SQL name of letters, digits and _."""
    for name in views:
        if not _VIEW_NAME.match(name):
            raise TsCellError(f"{name} cannot be a view's name.")
    return f"await sab.sync({_js(dict(sorted(views.items())))});"


def save_code(result_id: Any, path: str) -> str:
    """A table result written whole as Parquet (Open as grid): by its id, never by code the caller sent."""
    ident = str(result_id or "")
    if not _RESULT_ID.match(ident):
        raise TsCellError("A table result's id is r and a number (its cell's output says it).")
    return f"await sab.save({_js(ident)}, {_js(path)});"


def plain(text: str) -> str:
    return _ANSI.sub("", text)


def clean(record: dict[str, Any]) -> dict[str, Any]:
    """A kernel output as the page draws it: Deno's colour codes out of plain text and tracebacks."""
    out = dict(record)
    data = out.get("data")
    if isinstance(data, dict) and isinstance(data.get("text/plain"), str):
        out["data"] = data | {"text/plain": plain(data["text/plain"])}
    if isinstance(out.get("text"), str):
        out["text"] = plain(out["text"])
    if isinstance(out.get("traceback"), list):
        out["traceback"] = [plain(str(line)) for line in out["traceback"]]
    for key in ("ename", "evalue"):
        if isinstance(out.get(key), str):
            out[key] = plain(out[key])
    return out


def table_of(record: dict[str, Any]) -> dict[str, Any] | None:
    """A table result's bundle (columns, types, rows, total, id), or None when the record is not one."""
    data = record.get("data")
    found = data.get(TABLE_MIME) if isinstance(data, dict) else None
    return found if isinstance(found, dict) else None


_TITLES: dict[str, tuple[str, str]] = {
    "ReferenceError": (
        "A name that is not defined",
        "TypeScript has no {name} here: the cell that makes it has not run yet in this kernel (or ran "
        "before a restart), or the name is spelled differently.",
    ),
    "TypeError": ("A value of the wrong kind", "The code used a value in a way its kind does not allow."),
    "SyntaxError": ("The code does not parse", "The cell is not valid TypeScript at the place shown."),
}


def error_detail(record: dict[str, Any], cell: int | None, code: str, sql: bool = False) -> dict[str, Any]:
    """A kernel error as the error panel's detail (workbenchErrors.ts: the base's shape). The cell's own
    frames come from Deno's `<anonymous>:line:col` (the line counted in the cell); a DuckDB error is
    placed in the SQL by the base's rule."""
    kind = plain(str(record.get("ename") or "Error"))
    message = plain(str(record.get("evalue") or ""))
    lines = code.splitlines()
    frames: list[dict[str, Any]] = []
    for raw in record.get("traceback") or []:
        at = _AT.search(plain(str(raw)))
        if not at or sql:
            continue
        line, col = int(at.group(2)), int(at.group(3))
        frames.append(
            {
                "where": "cell",
                "cell": cell,
                "file": None,
                "module": "",
                "function": at.group(1) or "",
                "line": line,
                "end_line": None,
                "col": col,
                "end_col": None,
                "code": lines[line - 1] if 0 < line <= len(lines) else "",
                "values": [],
                "locals": [],
            }
        )
    position = base_errors.sql_position(message) if (sql or "Error:" in message) else None
    named = re.search(r"Table with name (\S+) does not exist", message)  # DuckDB 2.0's own words
    if position is not None and named and "missing" not in position:
        position["missing"] = named.group(1)
    name_match = re.match(r"(\S+) is not defined", message)
    title, explanation = _TITLES.get(kind, (f"{kind}: {message}" if message else kind, ""))
    explanation = explanation.replace("{name}", f"`{name_match.group(1)}`" if name_match else "the name")
    fixes: list[dict[str, Any]] = []
    if kind == "ReferenceError" and name_match:
        name = name_match.group(1)
        fixes.append({"kind": "define", "title": f"Run the cell that makes `{name}`", "name": name})
    if position:
        title, explanation = "DuckDB could not run the query", message
    entry = {
        "type": kind,
        "module": "",
        "message": message,
        "hint": "",
        "relation": None,
        "notes": [],
        "facts": {},
        "syntax": None,
        "frames": frames,
        "group": [],
        "your_frame": len(frames) - 1 if frames else None,
        "title": title,
        "explanation": explanation,
        "fixes": fixes,
        "sql": position,
    }
    where = (
        f"cell [{cell}], line {frames[0]['line']}"
        if frames and cell is not None
        else (f"cell [{cell}]" if cell is not None else "")
    )
    return {"chain": [entry], "where": where, "language": "typescript"}
