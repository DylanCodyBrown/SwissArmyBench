"""Web call blades (the owner, 2026-11-17: "APIS and web calls will be built by using blades"; "they are
not really connections, UNLESS they return a table"; "so we need an option on web call blade to return
as table. This is the gate for making it querable from DuckDB"; "alright just let duckdb to the
conversion then").

An API is blades: its API blade (the made client: base address, sign-in, retries, paging; a secret's
source named, never its value) and one web call blade per endpoint: that call alone, through its API
blade, its inputs and body the blade's settings. Return as table, off by default, is the one gate to
DuckDB SQL: on, the call is one of its API's tables (`SELECT * FROM [Orders].list_orders`).

  settings    the [web_call] header: api, operation, method, path; as_table, the shape (records, or
              header and rows), the records or rows path, the header (a path, or the first row), the
              columns and their types, flatten, paging, and the conversion
  shapes      the common answers found in a response, so switching on is one click: a list of records,
              an envelope ({"data" | "value" | "items" | "results" | "records": [...]}, OData's
              @odata.nextLink), and header and rows first of all ({"columns": [...], "rows": [[...]]},
              {"header": [...], "data": [[...]]}, columns as {"name", "type"} as Trino answers, a header
              row as the first row; any of them under data or result)
  conversion  DuckDB's own query over the pages read (a view `response`, one row per page, its JSON in
              `page`): records unnested (nested objects as columns when flattened; a list inside a
              record stays a LIST), header and rows projected by position with the header's types
              (DUCKDB_TYPES) winning over detection. Editable: it is SQL
  code        a web call blade's code (its inputs and body, then the call), the part the app runs after
              the API blade (Send, Try it), and the API blade's two boxes listing and reading its tables
  tables      the contract: an API's tables are exactly its web calls with Return as table on; one with a
              required input and no value names it

Standard library only (the plain client reads blades); no I/O.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
PAGING: tuple[str, ...] = ("all", "first")
SHAPES: tuple[str, ...] = ("records", "header_rows")
ENVELOPES: tuple[str, ...] = (
    "data",
    "value",
    "items",
    "results",
    "records",
    "rows",
    "entries",
    "list",
    "result",
)
HEADER_KEYS: tuple[str, ...] = ("columns", "header", "headers", "fields")
ROW_KEYS: tuple[str, ...] = ("rows", "data", "values", "records")
NEXT_FIELDS: tuple[str, ...] = ("@odata.nextLink", "nextUri", "nextLink", "next_link", "next", "nextUrl")
MAX_COLUMNS: int = 500
TAG: str = "web call"
API_TAG: str = "api"
_PATH = re.compile(r'^\$(\.[A-Za-z_@][A-Za-z0-9_.@-]*|\[\d+\]|\["[^"]+"\])*$')
_TYPE = re.compile(r"^[A-Z][A-Z0-9_ ]*(\(\s*\d+\s*(,\s*\d+\s*)?\))?(\[\])?$")
_PART = re.compile(r'\.([A-Za-z_@][A-Za-z0-9_@-]*)|\[(\d+)\]|\["([^"]+)"\]')

# A header's type words as DuckDB's (they win over DuckDB's own detection).
DUCKDB_TYPES: dict[str, str] = {
    **dict.fromkeys(
        (
            "bigint",
            "int8",
            "long",
            "int64",
            "integer",
            "int",
            "int4",
            "int32",
            "smallint",
            "tinyint",
            "short",
            "number:int",
        ),
        "BIGINT",
    ),
    **dict.fromkeys(("varchar", "string", "text", "char", "nvarchar", "str", "uuid", "json"), "VARCHAR"),
    **dict.fromkeys(
        ("double", "float", "float8", "float64", "real", "float4", "number", "numeric:float"), "DOUBLE"
    ),
    **dict.fromkeys(
        (
            "timestamp",
            "datetime",
            "timestamp with time zone",
            "timestamptz",
            "date-time",
            "datetime2",
            "timestamp(3)",
            "timestamp(6)",
        ),
        "TIMESTAMP",
    ),
    **dict.fromkeys(("decimal", "numeric", "money"), "DECIMAL(38, 10)"),
    **dict.fromkeys(("boolean", "bool", "bit"), "BOOLEAN"),
    **dict.fromkeys(("date",), "DATE"),
}


class WebCallError(ValueError):
    """A web call's settings that cannot be used as given (why, in plain words)."""


def duckdb_type(word: Any) -> str | None:
    """A header's type as DuckDB's (decimal(10,2) and varchar(20) keep their sizes); None: not known."""
    said = " ".join(str(word or "").strip().lower().split())
    if not said:
        return None
    sized = re.fullmatch(r"(decimal|numeric)\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", said)
    if sized:
        return f"DECIMAL({min(int(sized.group(2)), 38)}, {sized.group(3)})"
    base = re.sub(r"\(.*\)$", "", said).strip()
    return DUCKDB_TYPES.get(said) or DUCKDB_TYPES.get(base)


# ===== paths =====


def check_path(path: Any) -> str:
    said = str(path or "$").strip() or "$"
    if not _PATH.match(said):
        raise WebCallError(f'{said} is not a path: $, $.items, $.data.rows or $["odd key"].')
    return said


def parts(path: str) -> list[str | int]:
    found: list[str | int] = []
    for match in _PART.finditer(path):
        name, index, quoted = match.groups()
        found.append(int(index) if index is not None else (name if name is not None else quoted))
    return found


def path_of(found: Sequence[str | int]) -> str:
    out = "$"
    for part in found:
        if isinstance(part, int):
            out += f"[{part}]"
        elif re.fullmatch(r"[A-Za-z_@][A-Za-z0-9_@-]*", part):
            out += f".{part}"
        else:
            out += f'["{part}"]'
    return out


def at(value: Any, path: str) -> Any:
    node = value
    for part in parts(path):
        if isinstance(part, int):
            node = node[part] if isinstance(node, list) and -len(node) <= part < len(node) else None
        else:
            node = node.get(part) if isinstance(node, dict) else None
    return node


def _duck_expr(path: str) -> str:
    """A path inside a page as DuckDB reaches it: page."data"."items" (an index: [n + 1])."""
    out = "page"
    for part in parts(path):
        out += f"[{part + 1}]" if isinstance(part, int) else '."' + part.replace('"', '""') + '"'
    return out


# ===== shapes: what a response looks like =====


def _is_records(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, dict) for v in value[:50])


def _is_rows(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, list) for v in value[:50])


def _header(value: Any) -> list[tuple[str, str | None]] | None:
    """A header: names, or {"name", "type"} objects (Trino's columns)."""
    if not isinstance(value, list) or not value:
        return None
    if all(isinstance(v, str) for v in value):
        return [(v, None) for v in value]
    if all(isinstance(v, dict) and isinstance(v.get("name"), str) for v in value):
        return [
            (v["name"], next((str(v[k]) for k in ("type", "dataType", "data_type") if v.get(k)), None))
            for v in value
        ]
    return None


def _next_field(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for key in NEXT_FIELDS:
        if isinstance(value.get(key), str):
            return key
    for key in ("cursor", "nextCursor", "next_cursor", "nextToken", "nextPageToken", "continuationToken"):
        if key in value:
            return key
    return ""


def detect(value: Any, where: tuple[str | int, ...] = (), depth: int = 0) -> dict[str, Any] | None:
    """The settings Return as table would start with for this response, or None when it holds no table:
    header and rows first, then a list of records; an envelope (data, value, result ...) looked into."""
    if depth > 3:
        return None
    if isinstance(value, dict):
        for header_key in HEADER_KEYS:
            header = _header(value.get(header_key))
            if header is None:
                continue
            for rows_key in ROW_KEYS:
                if rows_key != header_key and _is_rows(value.get(rows_key)):
                    rows, head = path_of((*where, rows_key)), path_of((*where, header_key))
                    return _settings("header_rows", rows, head, header, value)
        for key in ENVELOPES:
            inner = value.get(key)
            if _is_records(inner):
                return _settings("records", path_of((*where, key)), "", [], value)
            if isinstance(inner, list) and _is_rows(inner) and all(isinstance(c, str) for c in inner[0]):
                header = _header(inner[0]) or []
                return _settings("header_rows", path_of((*where, key)), "first_row", header, value)
        for key in ("data", "result", "response", "body"):
            if isinstance(value.get(key), dict):
                found = detect(value[key], (*where, key), depth + 1)
                if found:
                    found["next"] = found["next"] or _next_field(value)
                    return found
        return None
    if _is_records(value):
        return _settings("records", path_of(where), "", [], value)
    if _is_rows(value) and all(isinstance(c, str) for c in value[0]):
        return _settings("header_rows", path_of(where), "first_row", _header(value[0]) or [], value)
    return None


def _settings(
    shape: str, rows: str, header: str, columns: list[tuple[str, str | None]], page: Any
) -> dict[str, Any]:
    return {
        "shape": shape,
        "records": rows,
        "header": header,
        "columns": {name: (duckdb_type(kind) or "") for name, kind in columns} if columns else {},
        "next": _next_field(page),
    }


# ===== the conversion: DuckDB's query over the pages =====


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def conversion(settings: Mapping[str, Any]) -> str:
    """DuckDB's query that makes the table from `response` (one row per page read, its JSON in `page`)."""
    rows = _duck_expr(check_path(settings.get("records")))
    if settings.get("shape") == "header_rows":
        columns = dict(settings.get("columns") or {})
        if not columns:
            raise WebCallError("Header and rows needs the header's columns: read a response first.")
        source = f"{rows}[2:]" if settings.get("header") == "first_row" else rows
        picks = []
        for n, (name, kind) in enumerate(columns.items(), start=1):
            text = f"json_extract_string(to_json(r[{n}]), '$')"
            picks.append(
                f"TRY_CAST({text} AS {kind}) AS {_ident(name)}" if kind else f"{text} AS {_ident(name)}"
            )
        picked = ",\n  ".join(picks)
        return f"SELECT\n  {picked}\nFROM (SELECT unnest({source}) AS r FROM response)"  # noqa: S608 (names quoted, types checked)
    pick = "unnest(r, recursive := true)" if settings.get("flatten", True) else "r.*"
    return f"SELECT {pick}\nFROM (SELECT unnest({rows}) AS r FROM response)"  # noqa: S608 (a checked path)


# ===== the settings in the blade's header =====


def check_web_call(raw: Any) -> dict[str, Any]:
    """A web call blade's [web_call] settings, checked."""
    if not isinstance(raw, Mapping):
        raise WebCallError('A web call is {"api", "operation", "method", "path", "as_table"?, ...}.')
    out: dict[str, Any] = {}
    for key in ("api", "operation", "path"):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 500:
            raise WebCallError(f"A web call names its {key}.")
        out[key] = value.strip()
    method = str(raw.get("method") or "GET").upper()
    if method not in METHODS:
        raise WebCallError(f"A web call's method is one of {', '.join(METHODS)}.")
    out["method"] = method
    out["as_table"] = raw.get("as_table") is True
    shape = str(raw.get("shape") or "records")
    if shape not in SHAPES:
        raise WebCallError("A web call's table shape is records or header_rows.")
    out["shape"] = shape
    out["records"] = check_path(raw.get("records"))
    header = str(raw.get("header") or "")
    out["header"] = header if header in ("", "first_row") else check_path(header)
    out["flatten"] = raw.get("flatten") is not False
    paging = str(raw.get("paging") or "all")
    if paging not in PAGING:
        raise WebCallError("A web call's paging is all (every page) or first (the first page only).")
    out["paging"] = paging
    columns = raw.get("columns") or {}
    if not isinstance(columns, Mapping) or len(columns) > MAX_COLUMNS:
        raise WebCallError("A web call's columns are {name: its DuckDB type, or empty}.")
    out["columns"] = {str(k)[:200]: str(v or "")[:40].upper() for k, v in columns.items()}
    bad = [t for t in out["columns"].values() if t and not _TYPE.match(t)]
    if bad:
        raise WebCallError(f"{bad[0]} is not a DuckDB type (BIGINT, VARCHAR, DOUBLE, DECIMAL(10, 2) ...).")
    by = raw.get("paging_by") or {}
    out["paging_by"] = {str(k): str(v) for k, v in by.items()} if isinstance(by, Mapping) else {}
    said = raw.get("conversion")
    out["conversion"] = str(said) if isinstance(said, str) and said.strip() else ""
    out["mode"] = str(raw.get("mode") or "call")
    if out["mode"] not in ("call", "write rows"):
        raise WebCallError('A web call\'s mode is "call" or "write rows".')
    if out["mode"] == "write rows":
        from swissarmybench.domain import write_rows

        mapping = raw.get("mapping") or {}
        if (
            isinstance(mapping, Mapping)
            and mapping
            and all(isinstance(v, str) and v.startswith(("column ", "value ")) for v in mapping.values())
        ):
            mapping = write_rows.mapping_of_header(mapping)  # as the blade's header writes it
        try:
            out["mapping"] = write_rows.check_mapping(mapping)
            out |= write_rows.check_settings(raw)
        except write_rows.WriteError as error:
            raise WebCallError(str(error)) from None
        out["as_table"] = False  # a write is never a table
    if out["as_table"] and not out["conversion"]:
        out["conversion"] = conversion(out)
    return out


HEADER_KEYS_WRITTEN: tuple[str, ...] = (
    "api", "operation", "method", "path", "mode", "as_table", "shape", "records", "header", "flatten",
    "paging", "conversion", "batch", "batch_size", "response_field",
)  # fmt: skip


def header_lines(call: Mapping[str, Any]) -> list[str]:
    """A web call blade's [web_call] table for its portable file's TOML header (readable in Git)."""

    def text(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        return json.dumps(str(value), ensure_ascii=False)  # a TOML basic string

    lines = ["", "[web_call]  # an API's one endpoint; as_table: Return as table (its API's table in SQL)"]
    lines += [f"{key} = {text(call[key])}" for key in HEADER_KEYS_WRITTEN if key in call]
    if call.get("paging_by"):
        lines += ["", "[web_call.paging_by]  # how its pages are asked for: token, page or offset"]
        lines += [f"{name} = {text(value)}" for name, value in dict(call["paging_by"]).items()]
    if call.get("key_columns"):
        lines.append("key_columns = [" + ", ".join(text(k) for k in call["key_columns"]) + "]")
    if call.get("mapping"):
        from swissarmybench.domain.write_rows import mapping_header

        lines += ["", "[web_call.mapping]  # request field = column NAME, or value <JSON>"]
        lines += [f"{text(field)} = {text(said)}" for field, said in mapping_header(call["mapping"]).items()]
    if call.get("columns"):
        lines += ["", "[web_call.columns]  # column = its DuckDB type (empty: DuckDB decides)"]
        lines += [f"{text(name)} = {text(kind)}" for name, kind in dict(call["columns"]).items()]
    return lines


def name_of(api: str, operation: str) -> str:
    """A web call blade's name: Orders.list_orders (64 characters at most)."""
    return f"{api}.{operation}"[:64].rstrip(" .")


# ===== the code =====


def _q(text: str) -> str:
    return json.dumps(text)


def py(value: Any) -> str:
    """A JSON value as a Python literal."""
    if value is None or isinstance(value, bool | int | float):
        return repr(value)
    if isinstance(value, str):
        return _q(value)
    if isinstance(value, list):
        return "[" + ", ".join(py(v) for v in value) + "]"
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{_q(str(k))}: {py(v)}" for k, v in value.items()) + "}"
    return _q(str(value))


def code(
    api: str,
    method: str,
    path: str,
    summary: str,
    inputs: Mapping[str, Any],
    body: Any,
    call: Mapping[str, Any] | None = None,
) -> str:
    """A web call blade's code: its API blade, its inputs and body (the settings), then the call; with
    Return as table on, DuckDB's conversion of the pages it reads."""
    lines = [
        "import swissarmybench as sab",
        "",
        f"api = sab.blade({_q(api)})",
        f"# {method} {path}" + (f": {summary}" if summary else ""),
        f"inputs = {py(dict(inputs))}",
        f"body = {py(body)}",
    ]
    if call and call.get("as_table"):
        lines += [
            f"conversion = {_q(str(call.get('conversion') or conversion(call)))}",
            f"result = api.table({_q(method)}, {_q(path)}, inputs, body, conversion, "
            f"{_q(str(call.get('paging') or 'all'))}, {py(dict(call.get('paging_by') or {}))})",
        ]
    else:
        lines.append(f"result = api.request({_q(method)}, {_q(path)}, inputs, body)")
    return "\n".join(lines) + "\n"


def values_of(source: str) -> dict[str, Any]:
    """The `inputs = {...}` and `body = ...` a web call blade's code holds (literals only)."""
    found: dict[str, Any] = {"inputs": {}, "body": None}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return found
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in found:
                try:
                    found[node.targets[0].id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return found


def call_section(source: str) -> str:
    """The code from its inputs on: what the app runs after its API blade's own code."""
    kept = []
    for line in source.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("import swissarmybench", "from swissarmybench")):
            continue
        if re.match(r"^api\s*=\s*sab\.blade\(", stripped):
            continue
        kept.append(line)
    return "\n".join(kept).strip("\n")


def send_command(source: str) -> str:
    """The read box that runs a web call after its API blade's Connect: one row (status, time, headers,
    the answer as JSON); an answer that is not a success is that row too, its text the body."""
    body = "\n".join("    " + line if line.strip() else "" for line in call_section(source).split("\n"))
    return (
        "import json as _json\n"
        "api.last = {}\n"
        "try:\n"
        f"{body}\n"
        "    _value = result\n"
        "except api.Error as _error:\n"
        "    _value = _error.text\n"
        "if hasattr(_value, 'to_pylist'):\n"
        "    _value = _value.to_pylist()\n"
        "elif hasattr(_value, 'to_dict'):\n"
        "    _value = _value.to_dict('records')\n"
        "_last = getattr(api, 'last', None) or {}\n"
        "[{'status': int(_last.get('status') or 0), 'ms': int(_last.get('ms') or 0), "
        "'headers': _json.dumps(dict(_last.get('headers') or {})), 'body': _json.dumps(_value, default=str)}]"
    )


# ===== the tables contract =====


def is_table(blade: Mapping[str, Any]) -> bool:
    """A web call blade with Return as table on (its `[web_call]` header's as_table): the one gate to SQL.
    A write rows call never is (check_web_call turns it off)."""
    call = blade.get("web_call")
    return isinstance(call, Mapping) and call.get("as_table") is True and call.get("mode") != "write rows"


def table_calls(blades: Iterable[Mapping[str, Any]], api: str) -> list[dict[str, Any]]:
    """An API's tables: exactly its web call blades with Return as table on. Each with its call, its
    conversion and `needs`: a required input with no value (unreadable bare until it has one)."""
    found = []
    for blade in blades:
        call = blade.get("web_call") or {}
        if not is_table(blade) or str(call.get("api") or "").casefold() != api.casefold():
            continue
        given = values_of(str(blade.get("code") or ""))
        said = given.get("inputs")
        inputs: dict[str, Any] = said if isinstance(said, dict) else {}
        needs = [
            f"{name} ({place})"
            for place, values in inputs.items()
            if isinstance(values, dict)
            for name, value in values.items()
            if value is None or value == ""
        ]
        found.append(
            {
                "table": str(call["operation"]),
                "blade": str(blade.get("name") or ""),
                "method": call["method"],
                "path": call["path"],
                "inputs": inputs,
                "body": given.get("body"),
                "conversion": call.get("conversion") or conversion(call),
                "paging": call.get("paging", "all"),
                "paging_by": call.get("paging_by") or {},
                "columns": call.get("columns") or {},
                "needs": needs,
            }
        )
    return sorted(found, key=lambda t: t["table"])


def tables_boxes(calls: list[dict[str, Any]]) -> tuple[str, str]:
    """The API blade's List the tables and Read a table boxes for its Return-as-table calls."""
    listed = [{"schema": "", "table": c["table"]} for c in calls]
    keys = ("method", "path", "inputs", "body", "conversion", "paging", "paging_by", "needs")
    entries = {c["table"]: {k: c[k] for k in keys} for c in calls}
    del listed
    catalog = "\n".join(
        [
            "import json as _json",
            f"_calls = _json.loads({_q(json.dumps(entries))})",
            "_found = []",
            "for _table, _call in _calls.items():",
            "    if _call['needs']:",
            "        _said = '(needs ' + ', '.join(_call['needs']) + ')'",
            "        _found.append({'schema': '', 'table': _table, 'column': _said, 'type': ''})",
            "        continue",
            "    _columns = api.table(_call['method'], _call['path'], _call['inputs'], _call['body'],",
            "                         _call['conversion'], 'first', _call['paging_by'], 1, True)",
            "    _found += [{'schema': '', 'table': _table, 'column': c, 'type': t} for c, t in _columns]",
            "_found",
        ]
    )
    read = "\n".join(
        [
            "import json as _json",
            f"_calls = _json.loads({_q(json.dumps(entries))})",
            "if table not in _calls:",
            '    raise ValueError(table + " is not one of this API\'s tables: switch on Return as table.")',
            "_call = _calls[table]",
            "if _call['needs']:",
            "    raise ValueError(table + ' needs ' + ', '.join(_call['needs']) + ': give it a value.')",
            "api.table(_call['method'], _call['path'], _call['inputs'], _call['body'], _call['conversion'],",
            "          _call['paging'], _call['paging_by'], limit)",
        ]
    )
    return catalog, read
