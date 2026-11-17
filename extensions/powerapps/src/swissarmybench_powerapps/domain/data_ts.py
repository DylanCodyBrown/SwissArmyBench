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
  (`ByRegion = ByRegionRow[]`). DuckDB's types as JSON gives them (BIGINT, DECIMAL and dates as strings).

SQL cells and markdown stay in the notebook (DuckDB is the notebook's). Pure rules: no I/O.
"""

from __future__ import annotations

import re
from typing import Any

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
_KERNEL_ONLY = re.compile(r"\bsab\.|\bDeno\.|@duckdb/node-api|from\s+[\"']jsr:")
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


def build(cells: list[dict[str, Any]], results: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
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
    parts.extend(bodies)
    return {
        "text": "\n\n".join(parts) + "\n",
        "cells": included,
        "left": left,
        "types": [interface_name(n) for n in sorted(typed) if typed[n].get("columns")],
    }
