"""Write rows with this call (the owner, 2026-11-17: "Most writes happen via api anyway"): a table's rows
sent through a POST, PUT, PATCH or DELETE operation, a web call blade in mode "write rows".

  mapping   each request field (`body.customer.name`, `path.order_id`, `query.dry_run`, `header.x-tag`)
            from a column or a constant; auto-matched by name (case, `_` and `-` ignored); nested body
            fields from the body schema's tree; a required field unmapped is named and blocks the run
  sending   one call per row, or batched (the body an array of the rows' bodies) where the API takes one;
            one at a time, the API blade's retries pacing 429s by Retry-After
  dry run   the first three request bodies as they will be sent, the row count and the number of calls:
            nothing is sent
  results   one row per input row: its key columns, the status, the answer's id (or a chosen field), the
            error's text and the time; the failed ones sent again with Retry the failed rows
  the blade its [web_call] header carries mode = "write rows", the batching and the mapping (a
            [web_call.mapping] table: field = "column NAME" or "value <JSON>"), readable in Git

Standard library only; no I/O.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

PLACES: tuple[str, ...] = ("body", "path", "query", "header", "cookie")
MAX_ROWS: int = 100_000
DRY_RUN_BODIES: int = 3
_FIELD = re.compile(r"^(body|path|query|header|cookie)(\.[^.]+)*$")


class WriteError(ValueError):
    """A mapping or a setting that cannot be used (why, in words)."""


def norm(name: str) -> str:
    """A name as matching reads it: case, `_`, `-` and spaces ignored (Customer_ID = customerid)."""
    return re.sub(r"[\s_\-]+", "", str(name)).casefold()


def fields(tree: Any, prefix: str = "body") -> list[tuple[str, bool]]:
    """The leaf fields of a body schema's tree (domain/api_explorer.py schema_tree) as (path, required);
    a list's items are not mapped (one row is one object)."""
    out: list[tuple[str, bool]] = []
    if isinstance(tree, dict):
        for key, inner in tree.items():
            name = str(key).rstrip("*")
            required = str(key).endswith("*")
            if isinstance(inner, dict) and inner:
                out += [(p, r and required) for p, r in fields(inner, f"{prefix}.{name}")]
            elif isinstance(inner, list):
                continue
            else:
                out.append((f"{prefix}.{name}", required))
    return out


def targets(body_tree: Any, parameters: Iterable[Mapping[str, Any]]) -> list[tuple[str, bool]]:
    """Every field a row can fill: the parameters (path, query, header) and the body's leaves."""
    found = [(f"{p['in']}.{p['name']}", bool(p.get("required"))) for p in parameters if p.get("in") in PLACES]
    return found + (fields(body_tree) if body_tree else [])


def auto_map(
    columns: Iterable[str], body_tree: Any, parameters: Iterable[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Each field matched to the column of its name (the last part of its path; case, `_`, `-` ignored)."""
    by_name: dict[str, str] = {}
    for column in columns:
        by_name.setdefault(norm(column), column)
    mapping: dict[str, dict[str, Any]] = {}
    for field, _ in targets(body_tree, parameters):
        last = field.rsplit(".", 1)[-1]
        whole = field.split(".", 1)[1].replace(".", "")
        found = by_name.get(norm(last)) or by_name.get(norm(whole))
        if found is not None:
            mapping[field] = {"column": found}
    return mapping


def check_mapping(raw: Any, columns: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    """A mapping as sent: {field: {"column": name} | {"value": constant}}; a column the table lacks
    says so."""
    if not isinstance(raw, Mapping):
        raise WriteError('A mapping is {"body.name": {"column": "name"}, "query.dry": {"value": true}}.')
    have = set(columns) if columns is not None else None
    out: dict[str, dict[str, Any]] = {}
    for field, source in raw.items():
        field = str(field)
        if not _FIELD.match(field):
            raise WriteError(
                f"{field} is not a request field: body.<name>, path.<name>, query.<name> or header.<name>."
            )
        if isinstance(source, str):
            source = {"column": source}
        if not isinstance(source, Mapping) or not ({"column", "value"} & set(source)):
            raise WriteError(f"{field} comes from a column or a value.")
        if "column" in source:
            column = str(source["column"])
            if have is not None and column not in have:
                raise WriteError(f"{field} names the column {column}: the table has no such column.")
            out[field] = {"column": column}
        else:
            out[field] = {"value": source["value"]}
    return out


def missing(mapping: Mapping[str, Any], body_tree: Any, parameters: Iterable[Mapping[str, Any]]) -> list[str]:
    """The required fields nothing fills: the run is blocked until each is mapped."""
    return [field for field, required in targets(body_tree, parameters) if required and field not in mapping]


def _put(target: dict[str, Any], parts: list[str], value: Any) -> None:
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def request_of(
    row: Mapping[str, Any], mapping: Mapping[str, Mapping[str, Any]]
) -> tuple[dict[str, Any], Any]:
    """One row's inputs (by place) and body, as its call sends them."""
    inputs: dict[str, Any] = {}
    body: dict[str, Any] = {}
    for field, source in mapping.items():
        value = row.get(source["column"]) if "column" in source else source.get("value")
        place, *rest = field.split(".")
        if place == "body":
            if rest:
                _put(body, rest, value)
        else:
            inputs.setdefault(place, {})[".".join(rest)] = value
    return inputs, (body if body else None)


def check_settings(raw: Any) -> dict[str, Any]:
    """The run's settings: batch (one call for every row, the body an array) and its size, the key
    columns the results keep, the answer's field to keep (id by default)."""
    said = raw if isinstance(raw, Mapping) else {}
    size = said.get("batch_size", 100)
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 10_000:
        raise WriteError("batch_size is 1 to 10,000.")
    keys = said.get("key_columns") or []
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
        raise WriteError("key_columns is a list of the table's columns.")
    return {
        "batch": said.get("batch") is True,
        "batch_size": size,
        "key_columns": keys,
        "response_field": str(said.get("response_field") or "id"),
    }


def plan(
    rows: Sequence[Mapping[str, Any]], mapping: Mapping[str, Mapping[str, Any]], settings: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """The calls: one per row ({"rows": [n], "inputs", "body"}), or batches whose body is the rows' bodies."""
    if len(rows) > MAX_ROWS:
        raise WriteError(f"At most {MAX_ROWS:,} rows are written in one run.")
    single = [request_of(row, mapping) for row in rows]
    if not settings.get("batch"):
        return [{"rows": [n], "inputs": inputs, "body": body} for n, (inputs, body) in enumerate(single)]
    size = int(settings.get("batch_size") or 100)
    calls = []
    for start in range(0, len(single), size):
        part = single[start : start + size]
        calls.append(
            {
                "rows": list(range(start, start + len(part))),
                "inputs": part[0][0] if part else {},
                "body": [b for _, b in part],
            }
        )
    return calls


def dry_run(
    rows: Sequence[Mapping[str, Any]], mapping: Mapping[str, Mapping[str, Any]], settings: Mapping[str, Any]
) -> dict[str, Any]:
    """What a run would send, nothing sent: the first three requests, the rows and the calls."""
    calls = plan(rows, mapping, settings)
    return {
        "rows": len(rows),
        "calls": len(calls),
        "first": [{"inputs": c["inputs"], "body": c["body"]} for c in calls[:DRY_RUN_BODIES]],
    }


def results(
    rows: Sequence[Mapping[str, Any]], answers: Sequence[Mapping[str, Any]], settings: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """One row per input row: its number, key columns, status, the answer's field, the error, the time."""
    field = str(settings.get("response_field") or "id")
    keys = list(settings.get("key_columns") or [])
    out: list[dict[str, Any]] = []
    by_row: dict[int, Mapping[str, Any]] = {}
    for answer in answers:
        for n in answer.get("rows") or []:
            by_row[int(n)] = answer
    for n, row in enumerate(rows):
        answer = by_row.get(n, {})
        status = int(answer.get("status") or 0)
        body = answer.get("body")
        if isinstance(body, list) and answer.get("rows"):  # a batch's answer: this row's own, when listed
            at = list(answer["rows"]).index(n)
            body = body[at] if at < len(body) else None
        got = body.get(field) if isinstance(body, dict) else None
        ok = 200 <= status < 300
        out.append(
            {
                "row": n,
                **{k: row.get(k) for k in keys},
                "status": status,
                field: got,
                "error": "" if ok else str(answer.get("error") or body or "not sent")[:500],
                "ms": int(answer.get("ms") or 0),
            }
        )
    return out


def failed(result_rows: Iterable[Mapping[str, Any]]) -> list[int]:
    """The input rows whose call did not succeed (Retry the failed rows)."""
    return [int(r["row"]) for r in result_rows if not 200 <= int(r.get("status") or 0) < 300]


# ===== the blade: its header's mapping, its code =====


def mapping_header(mapping: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """[web_call.mapping]: field = "column NAME" or "value <JSON>" (readable in Git)."""
    return {
        field: f"column {source['column']}"
        if "column" in source
        else f"value {json.dumps(source.get('value'))}"
        for field, source in mapping.items()
    }


def mapping_of_header(header: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for field, said in header.items():
        text = str(said)
        if text.startswith("column "):
            out[str(field)] = {"column": text[len("column ") :]}
        elif text.startswith("value "):
            try:
                out[str(field)] = {"value": json.loads(text[len("value ") :])}
            except ValueError:
                raise WriteError(f"{field}'s value is not JSON: {text}") from None
    return out


def code(
    api: str, method: str, path: str, mapping: Mapping[str, Any], settings: Mapping[str, Any], table: str
) -> str:
    """The blade dropped into a cell: its settings, the table's name, dry_run = True, one call."""
    return "\n".join(
        [
            "import swissarmybench as sab",
            "",
            f"api = sab.blade({json.dumps(api)})",
            f"# Write rows with {method} {path}: one call per row"
            + (", batched" if settings.get("batch") else ""),
            f"mapping = {_py(dict(mapping))}",
            f"settings = {_py(dict(settings))}",
            f"table = {table if table.isidentifier() else 'rows'}  # a DataFrame or a list of dicts",
            "dry_run = True  # the first three requests, the rows and the calls; False sends them",
            f"result = api.write_rows({json.dumps(method)}, {json.dumps(path)}, table, mapping, settings,"
            " dry_run)",
            "",
        ]
    )


def _py(value: Any) -> str:
    if value is None or isinstance(value, bool | int | float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_py(v) for v in value) + "]"
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{json.dumps(str(k))}: {_py(v)}" for k, v in value.items()) + "}"
    return json.dumps(str(value))
