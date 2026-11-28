"""data.ts: a code app's data notebook's TypeScript cells as one module the app imports (as data.py is made
from data.ipynb's Python cells), with typed results; Use in app writes it into the code app's src/.

The app runs in the browser (Vite and React), so only what can run there goes in:
- a TypeScript cell's top-level declarations (function, const, let, class, type, interface, enum) are
  exported, in the notebook's order, each under its cell's number and name;
- a cell that uses the notebook's own kernel (`sab.`, `Deno.`, DuckDB's Node package, a jsr: import) stays
  in the notebook: a comment says so, so nothing the app cannot run is written;
- `npm:` specifiers become the package's plain name (`npm:lodash@4` -> `lodash`), the imports gathered at
  the top, each once;
- typed results: a name a cell made that holds a table result when the notebook last ran (its DuckDB
  columns and types, asked of the kernel) gets a row interface (`ByRegionRow`) and its type
  (`ByRegion = ByRegionRow[]`). DuckDB's types as JSON gives them (BIGINT, DECIMAL and dates as strings);
- where each result comes from: `SOURCES`, the tables its query read (each marked when it is one of the app's
  Dataverse sources), so a page's hook knows what to read; the query itself is never translated;
- a small result (at most MAX_ROWS rows and MAX_CHARS of JSON: a lookup table) as a constant
  (`byRegionRows`); a bigger one is said plainly in a comment and in `left`, never embedded.

**Nothing in it imports DuckDB or WebAssembly** (the owner, 2026-11-17: "I can't change the code apps security
policy"): a code app's default Content-Security-Policy has `worker-src 'none'` and `script-src 'self'` plus
the platform's, which DuckDB-Wasm needs past, and DuckDB's Node package does not run in a browser. A cell
importing either stays in the notebook; `no_duckdb` refuses a text that would still name one. An `enum`
stays too: the template builds with `erasableSyntaxOnly`.

SQL cells and markdown stay in the notebook (DuckDB is the notebook's). Pure rules: no I/O.
"""

from __future__ import annotations

import json
import re
from typing import Any

from swissarmybench.domain import sql_guard

HEADER = (
    "// data.ts: made from the data notebook's TypeScript cells (data.ipynb) by Swiss Army Bench.\n"
    "// Use in app writes it again: change the notebook, not this file.\n"
)
_DECLARATION = re.compile(
    r"^(?:export\s+)?(?:declare\s+)?(async\s+function|function|const|let|var|class|type|interface|enum)\b"
)
_NAME_AFTER = re.compile(
    r"^(?:export\s+)?(?:async\s+function\*?|function\*?|const|let|var|class|type|interface|enum)\s+([A-Za-z_$][\w$]*)"
)
_IMPORT = re.compile(r"""^import\s.+?\sfrom\s+(["'])(.+?)\1\s*;?\s*$|^import\s+(["'])(.+?)\3\s*;?\s*$""")
_KERNEL_ONLY = re.compile(
    r"\bsab\.|\bDeno\.|from\s+[\"']jsr:|[\"'][^\"'\n]*(?:duckdb|\.wasm)[^\"'\n]*[\"']", re.IGNORECASE
)
_ENUM = re.compile(r"^(?:export\s+)?(?:const\s+|declare\s+)*enum\s", re.MULTILINE)
MAX_ROWS = 50  # a result embedded as a constant (a lookup table): at most this many rows
MAX_CHARS = 20_000  # and at most this much JSON
_NPM = re.compile(r"""(["'])npm:((?:@[^/"'@]+/)?[^@/"']+)(?:@[^/"']*)?(/[^"']*)?\1""")

_NUMBER = {"TINYINT", "SMALLINT", "INTEGER", "FLOAT", "DOUBLE", "REAL", "UTINYINT", "USMALLINT", "UINTEGER"}
_STRING = {
    "VARCHAR", "BIGINT", "HUGEINT", "UBIGINT", "UHUGEINT", "DATE", "TIME", "TIMESTAMP", "UUID",
    "INTERVAL", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP_S", "TIMESTAMP_MS", "TIMESTAMP_NS", "BLOB", "BIT",
    "TIME WITH TIME ZONE",
}  # fmt: skip


def ts_type(duckdb_type: str) -> str:
    """A DuckDB column's type as TypeScript sees it in a row object read as JSON."""
    kind = duckdb_type.strip().upper()
    if kind in _NUMBER:
        return "number"
    if kind == "BOOLEAN":
        return "boolean"
    if kind in _STRING or kind.startswith(("DECIMAL", "VARCHAR", "ENUM", "TIMESTAMP")):
        return "string"
    if kind.endswith("[]"):
        return f"{ts_type(kind[:-2])}[]"
    return "unknown"


def interface_name(name: str) -> str:
    """A result's row interface: `by_region` -> ByRegionRow."""
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", name) if p]
    base = "".join(p[:1].upper() + p[1:] for p in parts) or "Result"
    return ("T" + base if base[0].isdigit() else base) + "Row"


def _key(column: str) -> str:
    return column if re.match(r"^[A-Za-z_$][\w$]*$", column) else '"' + column.replace('"', '\\"') + '"'


def row_types(results: dict[str, dict[str, Any]]) -> list[str]:
    """Each named table result's row interface and its array type, in name order."""
    out: list[str] = []
    for name in sorted(results):
        found = results[name]
        columns = [str(c) for c in found.get("columns") or []]
        types = [str(t) for t in found.get("types") or []]
        if not columns:
            continue
        row = interface_name(name)
        fields = "\n".join(
            f"  {_key(c)}: {ts_type(types[i] if i < len(types) else '')};" for i, c in enumerate(columns)
        )
        out.append(f"export interface {row} {{\n{fields}\n}}\nexport type {row[:-3] or 'Result'} = {row}[];")
    return out


class DataTsError(ValueError):
    """A data.ts that would still name DuckDB or WebAssembly (never written)."""


def no_duckdb(text: str) -> str:
    """The text, or DataTsError when an import in it names DuckDB or a .wasm file."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "export ")) and re.search(
            r"duckdb|\.wasm", stripped, re.IGNORECASE
        ):
            raise DataTsError(
                f"data.ts would import DuckDB or WebAssembly ({stripped[:80]}): code apps cannot."
            )
        if re.search(r"\bimport\s*\(|\brequire\s*\(", stripped) and re.search(
            r"duckdb|\.wasm", stripped, re.IGNORECASE
        ):
            raise DataTsError(
                f"data.ts would load DuckDB or WebAssembly ({stripped[:80]}): code apps cannot."
            )
    return text


def _camel(name: str) -> str:
    row = interface_name(name)[:-3]
    return row[:1].lower() + row[1:]


def tables_read(query: str) -> list[str]:
    """The tables a result's query read (sqlglot, DuckDB's dialect; its own CTEs left out), in order."""
    return [t for t in sql_guard.tables_read(query) if not t.startswith("__sab")]


def sources(results: dict[str, dict[str, Any]], dataverse: list[str]) -> str | None:
    """SOURCES: each result's tables, those that are the app's Dataverse sources marked (a page's hook reads
    them through their generated services). None when no result says its query."""
    wanted = {d.lower() for d in dataverse}
    lines = []
    for name in sorted(results):
        query = results[name].get("query")
        if not isinstance(query, str) or not results[name].get("columns"):
            continue
        tables = tables_read(query)
        marked = [t for t in tables if t.lower() in wanted]
        lines.append(f"  {_key(_camel(name))}: {{ tables: {_list(tables)}, dataverse: {_list(marked)} }},")
    if not lines:
        return None
    return (
        "/** Where each result comes from: the tables its notebook query read (the app's Dataverse sources\n"
        " *  marked). A page reads them itself, through its hooks. */\n"
        "export const SOURCES = {\n" + "\n".join(lines) + "\n} as const;"
    )


def _list(items: list[str]) -> str:
    return "[" + ", ".join(json.dumps(i) for i in items) + "]"


def constants(results: dict[str, dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    """Each small result as a constant (its rows as JSON gave them); each too big said plainly."""
    made: list[str] = []
    too_big: list[dict[str, Any]] = []
    for name in sorted(results):
        found = results[name]
        rows = found.get("rows")
        if not isinstance(rows, list) or not found.get("columns"):
            continue
        total = int(found.get("total") or len(rows))
        said = json.dumps(rows[: MAX_ROWS + 1], ensure_ascii=False, indent=2)
        if total > MAX_ROWS or len(rows) > MAX_ROWS or len(said) > MAX_CHARS:
            why = f"{total:,} rows" if total > MAX_ROWS else f"{len(said):,} characters"
            too_big.append(
                {
                    "result": name,
                    "why": f"{why}: more than a constant holds ({MAX_ROWS} rows, {MAX_CHARS:,} characters)",
                }
            )
            made.append(
                f"// {_camel(name)}: {why}, too big to embed here; a page reads it from its source (SOURCES)."
            )
            continue
        row = interface_name(name)
        made.append(f"export const {_camel(name)}Rows: readonly {row}[] = {said};")
    return made, too_big


def declared(code: str) -> list[str]:
    """The names a cell's top-level declarations make (const totals, function byRegion, type Order)."""
    names: list[str] = []
    for line in code.splitlines():
        found = _NAME_AFTER.match(line)
        if found and found.group(1) not in names:
            names.append(found.group(1))
    return names


def kernel_only(code: str) -> bool:
    """A cell that needs the notebook's kernel (its DuckDB, Deno's own API): it stays in the notebook."""
    return bool(_KERNEL_ONLY.search(code))


def _exported(line: str) -> str:
    if line.startswith("export ") or not _DECLARATION.match(line):
        return line
    return "export " + line


def build(
    cells: list[dict[str, Any]],
    results: dict[str, dict[str, Any]] | None = None,
    dataverse: list[str] | None = None,
) -> dict[str, Any]:
    """data.ts from the notebook's cells ({kind, source, number, name}): its text, what went in and what
    stayed in the notebook (and why)."""
    imports: list[str] = []
    bodies: list[str] = []
    included: list[dict[str, Any]] = []
    left: list[dict[str, Any]] = []
    for cell in cells:
        if cell.get("kind") != "typescript":
            continue
        code = str(cell.get("source") or "")
        number = cell.get("number")
        label = f"[{number}]" + (f" {cell['name']}" if cell.get("name") else "")
        if not code.strip():
            continue
        if kernel_only(code):
            left.append({"cell": number, "why": "it uses the notebook's kernel (sab, Deno or DuckDB)"})
            bodies.append(f"// {label}: stays in the notebook (it uses the notebook's own kernel).")
            continue
        if _ENUM.search(code):
            left.append({"cell": number, "why": "an enum does not build in the app (erasableSyntaxOnly)"})
            bodies.append(f"// {label}: stays in the notebook (an enum does not build in the app).")
            continue
        own: list[str] = []
        for line in code.splitlines():
            if _IMPORT.match(line.strip()) and not line.startswith((" ", "\t")):
                plain = _NPM.sub(
                    lambda m: f"{m.group(1)}{m.group(2)}{m.group(3) or ''}{m.group(1)}", line.strip()
                )
                if plain not in imports:
                    imports.append(plain)
                continue
            own.append(_exported(line))
        text = "\n".join(own).strip("\n")
        if text:
            bodies.append(f"// {label}\n{text}")
            included.append({"cell": number, "names": declared(code)})
    typed = dict(results or {})
    parts = [HEADER.rstrip("\n")]
    if imports:
        parts.append("\n".join(imports))
    types = row_types(typed)
    if types:
        parts.append("// The notebook's table results, as the app reads them.\n" + "\n\n".join(types))
    where = sources(typed, list(dataverse or []))
    if where:
        parts.append(where)
    fixed, too_big = constants(typed)
    if fixed:
        parts.append("// The small results, fixed (lookup tables).\n" + "\n\n".join(fixed))
    parts.extend(bodies)
    text = no_duckdb("\n\n".join(parts) + "\n")
    return {
        "text": text,
        "cells": included,
        "left": left + too_big,
        "types": [interface_name(n) for n in sorted(typed) if typed[n].get("columns")],
    }
