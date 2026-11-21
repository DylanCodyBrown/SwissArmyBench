"""The APIs page (the owner, 2026-11-17: "Apis need thier own page so they can be imported managed,
refreshed when the api changes and searchable ... see their descriptions and see thier payloads and input
and outputs"): an API's OpenAPI document read for people, as an explorer. Our own design.

  explore    each operation as the page shows it: its plain name, method, path, tags, description; its
             inputs (parameters: name, where, type, required, default, description; the request body's
             schema as a structure and an example payload) and outputs (per status code: a description,
             the schema as a structure, an example); the named schemas (models) and where each is used
  examples   a payload made from a schema (its own example first, then its default, an enum's first
             value, else a value of its type): made up, never a real response
  search     one box across every API and operation: plain name, method, path, summary, description,
             tags, parameter and field names
  diff       what a re-read document changes: operations added, removed, changed (parameters, body and
             response fields added or removed)
  call       Try it's request from the inputs typed (path, query, header values; a JSON body), checked
             against the operation; the answer's headers with sign-in ones hidden
  form       a form-made API written as an OpenAPI document, so the explorer reads every API one way

Standard library only; no I/O.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from swissarmybench.domain import apis
from swissarmybench.domain.apis import ApiError, Spec

MAX_DEPTH: int = 8
MAX_PROPERTIES: int = 200
MAX_RESULTS: int = 200
_SCHEMA_REF = re.compile(r"^#/(components/schemas|definitions)/(.+)$")
_HIDDEN_HEADERS = re.compile(r"cookie|authorization|token|secret|key|signature|credential", re.IGNORECASE)
_WORDS = re.compile(r"[A-Za-z0-9_]+")
EXAMPLE_FORMATS: dict[str, Any] = {
    "date": "2026-01-31",
    "date-time": "2026-01-31T09:30:00Z",
    "email": "someone@example.com",
    "uuid": "00000000-0000-4000-8000-000000000000",
    "uri": "https://example.com/",
    "url": "https://example.com/",
    "hostname": "example.com",
    "ipv4": "192.0.2.1",
}


def _resolve(
    doc: Mapping[str, Any], node: Any, seen: frozenset[str]
) -> tuple[Any, str | None, frozenset[str]]:
    """A $ref followed (one step at a time): the node, the named schema it is (Order), the refs seen."""
    name: str | None = None
    while isinstance(node, Mapping) and isinstance(node.get("$ref"), str):
        ref = str(node["$ref"])
        found = _SCHEMA_REF.match(ref)
        if found:
            name = found.group(2).replace("~1", "/").replace("~0", "~")
        if ref in seen or not ref.startswith("#/"):
            return {}, name, seen
        seen = seen | {ref}
        target: Any = doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            target = target.get(part) if isinstance(target, Mapping) else None
        node = target if target is not None else {}
    return node, name, seen


def _type_words(schema: Mapping[str, Any]) -> str:
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = " | ".join(str(k) for k in kind)
    if not kind:
        kind = "object" if "properties" in schema else "array" if "items" in schema else "any"
    words = str(kind)
    if schema.get("format"):
        words += f" ({schema['format']})"
    if isinstance(schema.get("enum"), list):
        words += ": " + " | ".join(str(v) for v in schema["enum"][:12])
    if schema.get("nullable"):
        words += ", or null"
    return words


def schema_tree(doc: Mapping[str, Any], schema: Any, uses: set[str] | None = None) -> Any:
    """A schema as a structure to look at: an object's properties as keys (a required one marked *), a
    list as [one item], a value as its type in words ("string (date-time)"); a named schema used inside
    itself stops at "→ Order"."""
    return _tree(doc, schema, frozenset(), uses if uses is not None else set(), 0)


def _tree(doc: Mapping[str, Any], schema: Any, seen: frozenset[str], uses: set[str], depth: int) -> Any:
    node, name, seen = _resolve(doc, schema, seen)
    if name:
        uses.add(name)
    if not isinstance(node, Mapping) or depth > MAX_DEPTH or (name and not node):
        return f"→ {name}" if name else "any"  # a named schema inside itself stops here
    for key in ("allOf",):
        parts = node.get(key)
        if isinstance(parts, list) and parts:
            merged: dict[str, Any] = {}
            for part in parts:
                tree = _tree(doc, part, seen, uses, depth + 1)
                if isinstance(tree, dict):
                    merged |= tree
            return merged
    for key in ("oneOf", "anyOf"):
        parts = node.get(key)
        if isinstance(parts, list) and parts:
            return {
                f"one of ({n + 1})": _tree(doc, p, seen, uses, depth + 1) for n, p in enumerate(parts[:8])
            }
    kind = node.get("type")
    if kind == "array" or (not kind and "items" in node):
        return [_tree(doc, node.get("items", {}), seen, uses, depth + 1)]
    props = node.get("properties")
    if kind == "object" or isinstance(props, Mapping):
        required = set(node.get("required") or []) if isinstance(node.get("required"), list) else set()
        out: dict[str, Any] = {}
        for prop, inner in list((props or {}).items())[:MAX_PROPERTIES]:
            out[f"{prop}*" if prop in required else str(prop)] = _tree(doc, inner, seen, uses, depth + 1)
        extra = node.get("additionalProperties")
        if isinstance(extra, Mapping) and extra:
            out["<any key>"] = _tree(doc, extra, seen, uses, depth + 1)
        return out
    return _type_words(node)


def example(doc: Mapping[str, Any], schema: Any) -> Any:
    """A made-up payload from a schema: its own example, default or first enum value, else by type."""
    return _example(doc, schema, frozenset(), 0)


def _example(doc: Mapping[str, Any], schema: Any, seen: frozenset[str], depth: int) -> Any:
    node, _, seen = _resolve(doc, schema, seen)
    if not isinstance(node, Mapping) or depth > MAX_DEPTH:
        return None
    for key in ("example", "default"):
        if key in node:
            return node[key]
    examples = node.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]
    if isinstance(node.get("enum"), list) and node["enum"]:
        return node["enum"][0]
    for key in ("allOf",):
        if isinstance(node.get(key), list):
            merged: dict[str, Any] = {}
            for part in node[key]:
                found = _example(doc, part, seen, depth + 1)
                if isinstance(found, dict):
                    merged |= found
            return merged
    for key in ("oneOf", "anyOf"):
        if isinstance(node.get(key), list) and node[key]:
            return _example(doc, node[key][0], seen, depth + 1)
    kind = node.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "string")
    if kind == "array" or (not kind and "items" in node):
        item = _example(doc, node.get("items", {}), seen, depth + 1)
        return [] if item is None else [item]
    if kind == "object" or isinstance(node.get("properties"), Mapping):
        props = node.get("properties") or {}
        return {str(k): _example(doc, v, seen, depth + 1) for k, v in list(props.items())[:MAX_PROPERTIES]}
    if kind == "integer":
        return 0
    if kind == "number":
        return 0.0
    if kind == "boolean":
        return True
    if kind == "string":
        return EXAMPLE_FORMATS.get(str(node.get("format") or ""), "string")
    return None


def _media(content: Any) -> tuple[str, Any, Any]:
    """A content map's JSON part (else its first): the media type, its schema, its example."""
    if not isinstance(content, Mapping) or not content:
        return "", None, None
    media = next((m for m in content if "json" in str(m).lower()), next(iter(content)))
    part = content[media] if isinstance(content[media], Mapping) else {}
    given = part.get("example")
    if given is None and isinstance(part.get("examples"), Mapping) and part["examples"]:
        first = next(iter(part["examples"].values()))
        given = first.get("value") if isinstance(first, Mapping) else None
    return str(media), part.get("schema"), given


def _text(value: Any, limit: int = 20_000) -> str:
    return str(value)[:limit] if isinstance(value, str | int | float) else ""


def _parameter(doc: Mapping[str, Any], raw: Any) -> dict[str, Any] | None:
    node, _, _ = _resolve(doc, raw, frozenset())
    if not isinstance(node, Mapping) or not isinstance(node.get("name"), str):
        return None
    place = node.get("in")
    if place not in apis.PLACES:
        return None
    schema, _, _ = _resolve(doc, node.get("schema", node), frozenset())
    schema = schema if isinstance(schema, Mapping) else {}
    default = schema.get("default", node.get("default"))
    return {
        "name": node["name"],
        "in": place,
        "type": _type_words(schema) if schema else "string",
        "required": bool(node.get("required")) or place == "path",
        "default": default,
        "description": _text(node.get("description")),
        "enum": [str(v) for v in schema.get("enum", [])][:40] if isinstance(schema.get("enum"), list) else [],
        "example": node.get("example", schema.get("example")),
    }


def explore(doc: Mapping[str, Any], spec: Spec) -> dict[str, Any]:
    """The document as the explorer shows it (operations by the client's method names, `spec`'s)."""
    names = {(op.method, op.path): op for op in spec.operations}
    operations: list[dict[str, Any]] = []
    used_by: dict[str, list[str]] = {}
    for path, item in (doc.get("paths") or {}).items():
        item, _, _ = _resolve(doc, item, frozenset())
        if not isinstance(item, Mapping) or not isinstance(path, str):
            continue
        shared = [p for p in (_parameter(doc, r) for r in item.get("parameters") or []) if p]
        for verb, raw in item.items():
            method = str(verb).upper()
            op = names.get((method, path[:500]))
            if method not in apis.METHODS or not isinstance(raw, Mapping) or op is None:
                continue
            uses: set[str] = set()
            params = {(p["name"], p["in"]): p for p in shared}
            body: dict[str, Any] | None = None
            for r in raw.get("parameters") or []:
                node, _, _ = _resolve(doc, r, frozenset())
                if isinstance(node, Mapping) and node.get("in") == "body":  # Swagger 2.0
                    schema = node.get("schema")
                    body = {
                        "required": bool(node.get("required")),
                        "description": _text(node.get("description")),
                        "media": "application/json",
                        "schema": schema_tree(doc, schema, uses),
                        "example": example(doc, schema),
                    }
                    continue
                found = _parameter(doc, r)
                if found:
                    params[(found["name"], found["in"])] = found
            for p in op.parameters:  # a {word} in the path the document forgot
                params.setdefault(
                    (p.name, p.place),
                    {
                        "name": p.name,
                        "in": p.place,
                        "type": p.type,
                        "required": True,
                        "default": None,
                        "description": "",
                        "enum": [],
                        "example": None,
                    },
                )
            request, _, _ = _resolve(doc, raw.get("requestBody"), frozenset())
            if isinstance(request, Mapping) and request:
                media, schema, given = _media(request.get("content"))
                body = {
                    "required": bool(request.get("required")),
                    "description": _text(request.get("description")),
                    "media": media,
                    "schema": schema_tree(doc, schema, uses) if schema is not None else None,
                    "example": given if given is not None else example(doc, schema),
                }
            responses = []
            for status, answer in (raw.get("responses") or {}).items():
                answer, _, _ = _resolve(doc, answer, frozenset())
                if not isinstance(answer, Mapping):
                    continue
                if "content" in answer:
                    media, schema, given = _media(answer.get("content"))
                else:  # Swagger 2.0
                    media, schema, given = ("application/json", answer.get("schema"), None)
                    examples = answer.get("examples")
                    if isinstance(examples, Mapping) and examples:
                        given = next(iter(examples.values()))
                responses.append(
                    {
                        "status": str(status),
                        "description": _text(answer.get("description")),
                        "media": media,
                        "schema": schema_tree(doc, schema, uses) if schema is not None else None,
                        "example": given if given is not None else (example(doc, schema) if schema else None),
                    }
                )
            tags = [str(t)[:60] for t in raw.get("tags") or [] if isinstance(t, str | int)]
            operations.append(
                {
                    "id": op.name,
                    "name": op.summary or _plain(op.name),
                    "method": method,
                    "path": path,
                    "summary": op.summary,
                    "description": _text(raw.get("description")),
                    "tags": tags or [""],
                    "deprecated": op.deprecated,
                    "parameters": sorted(
                        params.values(), key=lambda p: (apis.PLACES.index(p["in"]), not p["required"])
                    ),
                    "body": body,
                    "responses": responses,
                    "table": op.table,
                    "schemas": sorted(uses),
                }
            )
            for name in uses:
                used_by.setdefault(name, []).append(op.name)
    found_schemas = (doc.get("components") or {}).get("schemas") or doc.get("definitions") or {}
    schemas = []
    for name, schema in found_schemas.items() if isinstance(found_schemas, Mapping) else []:
        inside: set[str] = set()
        schemas.append(
            {
                "name": str(name),
                "description": _text(schema.get("description")) if isinstance(schema, Mapping) else "",
                "schema": schema_tree(doc, schema, inside),
                "example": example(doc, schema),
                "used_by": used_by.get(str(name), []),
                "uses": sorted(inside - {str(name)}),
            }
        )
    info = doc.get("info") if isinstance(doc.get("info"), Mapping) else {}
    return {
        "title": spec.title,
        "version": spec.version,
        "source": spec.source,
        "description": _text(info.get("description") if isinstance(info, Mapping) else ""),
        "base_url": spec.base_url,
        "auth": spec.auth.type,
        "operations": operations,
        "schemas": schemas,
    }


def _plain(name: str) -> str:
    """list_orders -> List orders."""
    words = name.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


# ===== the fields a schema has (search and diff) =====


def fields(tree: Any, prefix: str = "") -> list[str]:
    """A schema tree's field paths: orders[].id, customer.region (a required mark dropped)."""
    out: list[str] = []
    if isinstance(tree, dict):
        for key, inner in tree.items():
            name = f"{prefix}.{key.rstrip('*')}" if prefix else key.rstrip("*")
            out.append(name)
            out += fields(inner, name)
    elif isinstance(tree, list) and tree:
        out += fields(tree[0], f"{prefix}[]")
    return out


def _all_fields(op: Mapping[str, Any]) -> dict[str, set[str]]:
    body = op.get("body") or {}
    found = {"body": set(fields(body.get("schema"))) if body else set()}
    for answer in op.get("responses") or []:
        found[f"response {answer['status']}"] = set(fields(answer.get("schema")))
    return found


# ===== search =====


def _words(text: str) -> list[str]:
    return [w.casefold() for w in _WORDS.findall(text)]


def search(explored: Iterable[tuple[str, Mapping[str, Any]]], query: str) -> list[dict[str, Any]]:
    """Every operation of every API whose words hold all of the query's words: the API, the method, the
    path, its plain name, and where each word matched (name, method, path, summary, description, tags,
    parameter, field)."""
    wanted = [w.casefold() for w in query.split() if w.strip()]
    if not wanted:
        return []
    results: list[dict[str, Any]] = []
    for api_name, doc in explored:
        for op in doc.get("operations") or []:
            places = {
                "api": api_name,
                "name": f"{op['name']} {op['id']}",
                "method": op["method"],
                "path": op["path"],
                "summary": op.get("summary") or "",
                "description": op.get("description") or "",
                "tags": " ".join(op.get("tags") or []),
                "parameter": " ".join(p["name"] for p in op.get("parameters") or []),
                "field": " ".join(f for group in _all_fields(op).values() for f in group),
            }
            hits: dict[str, list[str]] = {}
            for word in wanted:
                where = [k for k, text in places.items() if word in text.casefold()]
                if not where:
                    break
                for k in where:
                    hits.setdefault(k, []).append(word)
            else:
                exact = sum(1 for w in wanted for k in ("name", "path") if w in _words(places[k]))
                results.append(
                    {
                        "api": api_name,
                        "operation": op["id"],
                        "name": op["name"],
                        "method": op["method"],
                        "path": op["path"],
                        "summary": op.get("summary") or "",
                        "matched": {k: sorted(set(v)) for k, v in hits.items()},
                        "score": exact * 10 + len(hits.get("name", [])) * 3 + len(hits.get("path", [])) * 2,
                    }
                )
    results.sort(key=lambda r: (-r["score"], r["api"].casefold(), r["path"], r["method"]))
    return results[:MAX_RESULTS]


# ===== diff: what a re-read document changes =====


def diff(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    """Operations added, removed and changed (by method and path), each change in words: parameters,
    body and response fields added or removed, a status code added or removed."""
    before = {(o["method"], o["path"]): o for o in old.get("operations") or []}
    after = {(o["method"], o["path"]): o for o in new.get("operations") or []}

    def label(o: Mapping[str, Any]) -> dict[str, str]:
        return {"method": o["method"], "path": o["path"], "name": o["name"], "id": o["id"]}

    added = [label(after[k]) for k in after if k not in before]
    removed = [label(before[k]) for k in before if k not in after]
    changed = []
    for key in (k for k in after if k in before):
        a, b = before[key], after[key]
        notes: list[str] = []
        old_params = {(p["name"], p["in"]): p for p in a.get("parameters") or []}
        new_params = {(p["name"], p["in"]): p for p in b.get("parameters") or []}
        notes += [f"parameter {n} ({w}) added" for n, w in new_params if (n, w) not in old_params]
        notes += [f"parameter {n} ({w}) removed" for n, w in old_params if (n, w) not in new_params]
        for k in new_params.keys() & old_params.keys():
            if new_params[k]["required"] != old_params[k]["required"]:
                notes.append(
                    f"parameter {k[0]} now {'required' if new_params[k]['required'] else 'optional'}"
                )
            if new_params[k]["type"] != old_params[k]["type"]:
                notes.append(f"parameter {k[0]} is {new_params[k]['type']} (was {old_params[k]['type']})")
        old_fields, new_fields = _all_fields(a), _all_fields(b)
        for group in sorted(old_fields.keys() | new_fields.keys()):
            gained = sorted(new_fields.get(group, set()) - old_fields.get(group, set()))
            lost = sorted(old_fields.get(group, set()) - new_fields.get(group, set()))
            if group not in old_fields:
                notes.append(f"{group} added")
            elif group not in new_fields:
                notes.append(f"{group} removed")
            notes += [f"{group} field {f} added" for f in gained if group in old_fields]
            notes += [f"{group} field {f} removed" for f in lost if group in new_fields]
        if (a.get("summary"), a.get("description")) != (b.get("summary"), b.get("description")) and not notes:
            notes.append("description changed")
        if notes:
            changed.append(label(b) | {"changes": notes})
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "same": len([k for k in after if k in before]) - len(changed),
        "base_url": old.get("base_url") != new.get("base_url"),
        "any": bool(added or removed or changed or old.get("base_url") != new.get("base_url")),
    }


# ===== Try it =====


def _typed(value: Any, kind: str, name: str) -> Any:
    if value is None or value == "":
        return None
    word = kind.split(" ")[0]
    try:
        if word == "integer":
            return int(value)
        if word == "number":
            return float(value)
        if word == "boolean":
            return value if isinstance(value, bool) else str(value).lower() in ("true", "1", "yes")
        if word == "array" and isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
    except ValueError:
        raise ApiError(f"{name} is {word}: {value!r} is not one.") from None
    return value


def call(op: Mapping[str, Any], values: Any) -> dict[str, Any]:
    """Try it's request: {"path": {...}, "query": {...}, "header": {...}, "cookie": {...}, "body": ...}
    (or flat {"name": value}) checked against the operation's inputs (a required one missing says so)."""
    given = values if isinstance(values, Mapping) else {}
    flat = {k: v for k, v in given.items() if k not in (*apis.PLACES, "body")}
    out: dict[str, Any] = {"method": op["method"], "path": op["path"], "params": {}, "query": {}}
    out |= {"headers": {}, "cookies": {}}
    target = {"path": "params", "query": "query", "header": "headers", "cookie": "cookies"}
    for p in op.get("parameters") or []:
        found = given.get(p["in"])
        place: Mapping[str, Any] = found if isinstance(found, Mapping) else {}
        value = place.get(p["name"], flat.get(p["name"]))
        value = _typed(value, str(p["type"]), p["name"])
        if value is None and p["required"]:
            raise ApiError(f"{p['name']} ({p['in']}) is required.")
        if value is not None:
            out[target[p["in"]]][p["name"]] = value
    body = given.get("body")
    if isinstance(body, str) and body.strip():
        try:
            body = json.loads(body)
        except ValueError as error:
            raise ApiError(f"The body is not JSON ({error}).") from None
    if body in (None, "") and (op.get("body") or {}).get("required"):
        raise ApiError("This operation needs a body.")
    if body not in (None, ""):
        out["body"] = body
    return out


def answer(row: Mapping[str, Any]) -> dict[str, Any]:
    """Try it's answer: its status, time, headers (a sign-in one hidden) and body (JSON when it is)."""
    try:
        headers = json.loads(str(row.get("headers") or "{}"))
    except ValueError:
        headers = {}
    shown = {
        str(k): ("(hidden)" if _HIDDEN_HEADERS.search(str(k)) else str(v)[:500]) for k, v in headers.items()
    }
    text = str(row.get("body") or "")
    try:
        body: Any = json.loads(text) if text.strip() else None
        is_json = text.strip() != ""
    except ValueError:
        body, is_json = text, False
    status = int(row.get("status") or 0)
    return {
        "status": status,
        "ok": 200 <= status < 300,
        "ms": int(row.get("ms") or 0),
        "headers": shown,
        "json": is_json,
        "body": body,
        "said": _status_words(status),
    }


def _status_words(status: int) -> str:
    if status == 0:
        return "The API could not be reached."
    if status in (401, 403):
        return f"{status}: the API refused the sign-in (check the connection's key or password source)."
    if status == 404:
        return "404: there is nothing at that address (check the path's values and the base URL)."
    if status == 429:
        return "429: too many requests; wait and try again."
    if status >= 500:
        return f"{status}: the API failed on its side."
    if status >= 400:
        return f"{status}: the API refused the request (check the inputs)."
    return ""


# ===== a form-made API as an OpenAPI document =====


def _schema_of_type(kind: str) -> dict[str, Any]:
    if kind in ("timestamp", "date"):
        return {"type": "string", "format": "date-time" if kind == "timestamp" else "date"}
    return {
        "type": kind if kind in ("string", "integer", "number", "boolean", "array", "object") else "string"
    }


def openapi_of(spec: Spec) -> dict[str, Any]:
    """A form-made API's operations as an OpenAPI 3.0 document (what the form knows: no descriptions
    beyond its own, a table's columns as its rows' schema)."""
    paths: dict[str, Any] = {}
    for op in spec.operations:
        item: dict[str, Any] = {"operationId": op.name}
        if op.summary:
            item["summary"] = op.summary
        if op.tag:
            item["tags"] = [op.tag]
        params = [
            {"name": p.name, "in": p.place, "required": p.required, "schema": _schema_of_type(p.type)}
            | ({"description": p.description} if p.description else {})
            for p in op.parameters
        ]
        if params:
            item["parameters"] = params
        if op.body:
            media = "application/json" if op.body == "json" else "application/x-www-form-urlencoded"
            item["requestBody"] = {
                "required": op.body_required,
                "content": {media: {"schema": {"type": "object"}}},
            }
        if op.table:
            row = {"type": "object", "properties": {c: _schema_of_type(t) for c, t in op.columns}}
            rows: dict[str, Any] = {"type": "array", "items": row}
            schema = {"type": "object", "properties": {op.rows_at: rows}} if op.rows_at else rows
            item["responses"] = {
                "200": {"description": "Rows", "content": {"application/json": {"schema": schema}}}
            }
        else:
            item["responses"] = {"200": {"description": "The answer"}}
        paths.setdefault(op.path, {})[op.method.lower()] = item
    return {
        "openapi": "3.0.3",
        "info": {"title": spec.title, "version": spec.version or "1", "description": spec.description},
        "servers": [{"url": spec.base_url}],
        "paths": paths,
    }


def response_schema(value: Any, depth: int = 0) -> dict[str, Any]:
    """A schema from a real response's shape (types only, never a value): a form-made API's Outputs."""
    if depth > MAX_DEPTH:
        return {}
    if isinstance(value, dict):
        props = {str(k): response_schema(v, depth + 1) for k, v in list(value.items())[:MAX_PROPERTIES]}
        return {"type": "object", "properties": props}
    if isinstance(value, list):
        return {"type": "array", "items": response_schema(value[0], depth + 1) if value else {}}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    return {"type": "string"} if value is not None else {}
