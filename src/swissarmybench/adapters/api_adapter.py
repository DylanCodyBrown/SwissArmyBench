"""api_adapter: every API call in and out of a project, the same file wherever it runs (the app, a Workbench
kernel, a local sandbox API's process, an exported project). Any payload in, one envelope out; the answer's
shape is found, not configured, so when an API's payload changes the code that reads it does not.

    from api_adapter import actions, run, learn, discover

    found = actions(openapi_document, api="Orders")        # the specification is the front door
    answer = run(found["list_orders"], {"status": "open"}, api=http("https://example.test/v1"))
    answer["kind"], answer["records"], answer["paging"], answer["shape"]["drift"]
    contract = learn(answer["shape"])                       # the fields a widget can pick, with their boxes

It reads top to bottom in the order a call runs:

  1. Actions        an API's actions read from its specification (OpenAPI 3.x, Swagger 2.0): each one's
                    method, path, inputs, body fields and declared answer (a first guess, never trusted)
  2. Inputs         a call's inputs checked first (a missing or wrong one refused, naming it), made a Request
  3. Sending        Request and Response; an Api (its address, its sign-in, its send): http() over
                    urllib with a sign-in from environment variables, from_client() over an
                    API_<name>.py client (its own sign-in); retries on 429 (Retry-After) and passing errors
  4. Detection      the answer's format (JSON, JSON lines, XML without DOCTYPE or entity, CSV or TSV, YAML, a
                    file, text) and its envelope (records wherever they sit, a header-and-rows pair, a
                    record, a value)
  5. Paging         a next link (the body's, a Link header), a cursor or token, offset and limit, page
                    numbers; followed to the end within the call's limits, said in `paging`
  6. Shapes         each field's type read from its values (dates, numbers in text, booleans), records
                    flattened by path (customer.id), the fingerprint
  7. Drift          against the last shape: fields added, missing (null, marked), retyped (coerced where it
                    reads cleanly, else kept as text, marked), moved (the envelope); a rename offered once,
                    never guessed; paths matched in any case and across camelCase, snake_case and spaces
  8. The call       run(action, inputs): the one envelope (ok, status, kind, records / record / value / file,
                    paging, shape, raw, error in the one refusal shape, facts for the statistics)
  9. Learning       keep(): an endpoint's current shape, both ways (sent and returned), as one small
                    byte-stable file (types only, never a value); learn(): that shape as the widgets' contract
  10. Discovery     discover(actions, api): one read-only GET per read endpoint at the smallest page size, its
                    required inputs filled from other answers, at most a set number of calls, never a write;
                    each endpoint mapped by its shape (a table, a detail card, a metric, a download, a form;
                    master and detail pairs)
  11. Tables        table(answer): records as an Arrow table through adapter, the one crossing point

The standard library only (adapter is imported by table() alone): an export copies this file as it is. Its
contract only grows (design principle 12b): a version adds, never breaks a caller.

Version 1.0.0 (2026-11-22). What each version added (Plans/api-adapter.plan.md):
  1.0.0    actions from a specification; inputs checked; http, from_client, retries; detection of format,
           envelope, paging and types; shapes, drift, renames offered; run and its envelope; keep, learn;
           discover and the mapping; table; each call's facts and observe() (the statistics' seam)
"""

from __future__ import annotations

import base64
import csv
import datetime
import email.utils
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree

VERSION = "1.0.0"  # the docstring's change list says what each version added

KINDS = ("records", "record", "value", "file", "empty", "text")
READS = ("GET", "HEAD", "OPTIONS")  # the methods that change nothing; every other method writes
IDEMPOTENT = ("GET", "HEAD", "OPTIONS", "PUT", "DELETE")  # tried again after a passing error
PASSING = (429, 500, 502, 503, 504)  # throttled, or failed on its side for now
MAX_PAGES = 20  # pages a call follows at most
MAX_RECORDS = 10_000  # records a call keeps at most
MAX_WAIT = 30.0  # seconds a Retry-After is waited at most
MAX_FILE = 5_000_000  # bytes of a file answer carried in the envelope (base64)
MAX_FIELDS = 300  # paths a shape keeps
MAX_DEPTH = 6  # levels a record is flattened to
ENVELOPE_KEYS = ("value", "data", "items", "results", "records", "rows", "entries", "list", "content", "hits")
HEADER_KEYS = ("columns", "header", "headers", "fields", "names")
ROWS_KEYS = ("rows", "data", "values", "records")
NEXT_LINKS = (
    "@odata.nextlink",
    "nextlink",
    "next_link",
    "next",
    "nexturl",
    "next_url",
    "nexturi",
    "nextpage",
)
NEXT_TOKENS = ("nexttoken", "nextpagetoken", "nextcursor", "cursor", "continuationtoken", "endcursor")
TOKEN_INPUTS = ("pagetoken", "nexttoken", "cursor", "continuationtoken", "after", "startingafter", "token")
OFFSET_INPUTS = ("offset", "skip", "start")
LIMIT_INPUTS = ("limit", "top", "pagesize", "perpage", "size", "count", "maxresults", "first")
PAGE_INPUTS = ("page", "pagenumber", "pageno")
PAGING_HOLDERS = ("links", "_links", "paging", "pagination", "meta", "@odata", "page_info", "pageinfo")
TOTAL_PAGES = ("totalpages", "pages", "lastpage", "pagecount")
HIDDEN_HEADERS = re.compile(r"authorization|cookie|token|key|secret|signature|password", re.IGNORECASE)
# Words of an envelope's own keys beside its one list of records (count, next, page, links ...)
META_WORDS = (
    "count",
    "total",
    "next",
    "prev",
    "page",
    "size",
    "limit",
    "offset",
    "cursor",
    "token",
    "link",
    "meta",
    "more",
    "took",
    "status",
    "success",
    "odata",
    "skip",
    "version",
    "request",
)
MESSAGE_KEYS = ("message", "error_description", "detail", "error", "title", "msg", "description")


class ActionError(ValueError):
    """An action or its inputs the adapter cannot take, said in one sentence; `where` names the input."""

    def __init__(self, said: str, where: str = "") -> None:
        super().__init__(said)
        self.where = where


def refusal(
    said: str, where: str = "", fixes: Sequence[Mapping[str, Any]] = (), details: str = ""
) -> dict[str, Any]:
    """The app's one refusal shape (design principle 9.5): what happened, where, the fixes, its words."""
    return {"error": said, "where": where, "fixes": [dict(f) for f in fixes], "details": details}


# ===== 1. Actions: from the specification =====


@dataclass(frozen=True)
class Input:
    """One input of an action: its name, where it goes (path, query, header, cookie, body), its declared type
    (string, integer, number, boolean, array, object), whether it is required, its closed set of values."""

    name: str
    place: str = "query"
    type: str = "string"
    required: bool = False
    choices: tuple[Any, ...] = ()
    format: str = ""
    description: str = ""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "in": self.place,
            "type": self.type,
            "required": self.required,
        }
        if self.choices:
            out["choices"] = list(self.choices)
        if self.format:
            out["format"] = self.format
        if self.description:
            out["description"] = self.description
        return out


@dataclass(frozen=True)
class Action:
    """One call of an API, as its specification declares it. `declared` is the declared answer's shape (a
    first guess: every answer's own types win); `body` the request body's fields (path -> Input)."""

    name: str
    method: str = "GET"
    path: str = "/"
    api: str = ""
    summary: str = ""
    inputs: tuple[Input, ...] = ()
    body: tuple[Input, ...] = ()
    body_required: bool = False
    body_media: str = "application/json"
    declared: Mapping[str, Any] = field(default_factory=dict)

    @property
    def writes(self) -> bool:
        """Whether a call changes something outside the app (every method but GET, HEAD and OPTIONS)."""
        return self.method.upper() not in READS

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "api": self.api,
            "method": self.method,
            "path": self.path,
            "summary": self.summary,
            "writes": self.writes,
            "inputs": [i.to_json() for i in self.inputs],
            "body": [i.to_json() for i in self.body],
            "body_required": self.body_required,
            "body_media": self.body_media,
            "declared": dict(self.declared),
        }

    @staticmethod
    def from_json(raw: Mapping[str, Any]) -> Action:
        def inputs(items: Any, place: str) -> tuple[Input, ...]:
            return tuple(
                Input(
                    str(i["name"]),
                    str(i.get("in") or place),
                    str(i.get("type") or "string"),
                    bool(i.get("required")),
                    tuple(i.get("choices") or ()),
                    str(i.get("format") or ""),
                    str(i.get("description") or ""),
                )
                for i in items or ()
            )

        return Action(
            name=str(raw["name"]),
            method=str(raw.get("method") or "GET").upper(),
            path=str(raw.get("path") or "/"),
            api=str(raw.get("api") or ""),
            summary=str(raw.get("summary") or ""),
            inputs=inputs(raw.get("inputs"), "query"),
            body=inputs(raw.get("body"), "body"),
            body_required=bool(raw.get("body_required")),
            body_media=str(raw.get("body_media") or "application/json"),
            declared=dict(raw.get("declared") or {}),
        )


def _ref(doc: Mapping[str, Any], node: Any, seen: frozenset[str] = frozenset()) -> Any:
    """A `$ref` followed inside the document (#/components/schemas/Order, #/definitions/Order), once each."""
    while isinstance(node, Mapping) and isinstance(node.get("$ref"), str):
        ref = str(node["$ref"])
        if ref in seen or not ref.startswith("#/"):
            return {}
        seen = seen | {ref}
        target: Any = doc
        for part in ref[2:].split("/"):
            target = (
                target.get(part.replace("~1", "/").replace("~0", "~"))
                if isinstance(target, Mapping)
                else None
            )
        node = target if isinstance(target, Mapping) else {}
    return node


def _schema_type(schema: Mapping[str, Any]) -> str:
    kind = schema.get("type")
    if isinstance(kind, list):  # OpenAPI 3.1's ["string", "null"]
        kind = next((k for k in kind if k != "null"), "string")
    if not kind:
        kind = "object" if "properties" in schema else "array" if "items" in schema else "string"
    return str(kind)


def _declared_fields(doc: Mapping[str, Any], schema: Any, prefix: str = "", depth: int = 0) -> dict[str, str]:
    """A schema's fields by path, as declared (object properties flattened, a list's items under its path)."""
    schema = _ref(doc, schema)
    if not isinstance(schema, Mapping) or depth > MAX_DEPTH:
        return {}
    for combined in ("allOf", "oneOf", "anyOf"):
        if isinstance(schema.get(combined), list):
            merged: dict[str, str] = {}
            for part in schema[combined]:
                merged |= _declared_fields(doc, part, prefix, depth + 1)
            return merged
    kind = _schema_type(schema)
    if kind == "object" and isinstance(schema.get("properties"), Mapping):
        out: dict[str, str] = {}
        for name, sub in schema["properties"].items():
            out |= _declared_fields(doc, sub, f"{prefix}.{name}" if prefix else str(name), depth + 1)
        return out
    if kind == "array" and prefix == "":
        return _declared_fields(doc, schema.get("items"), "", depth + 1)
    word = {
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "array": "list",
        "object": "object",
    }
    found = word.get(kind, "text")
    if kind == "string" and schema.get("format") in ("date", "date-time"):
        found = "date" if schema["format"] == "date" else "datetime"
    return {prefix or "value": found}


def _declared(doc: Mapping[str, Any], responses: Any) -> dict[str, Any]:
    """The declared answer: its kind (records, record, value) and fields, from the first success's schema."""
    if not isinstance(responses, Mapping):
        return {}
    code = next((c for c in sorted(responses, key=str) if str(c).startswith("2")), None)
    answer = _ref(doc, responses.get(code)) if code is not None else {}
    schema: Any = answer.get("schema") if isinstance(answer, Mapping) else None  # Swagger 2.0
    content = answer.get("content") if isinstance(answer, Mapping) else None
    if isinstance(content, Mapping) and content:
        media = next((m for m in content if "json" in str(m)), next(iter(content)))
        schema = (content.get(media) or {}).get("schema")
    schema = _ref(doc, schema)
    if not isinstance(schema, Mapping) or not schema:
        return {}
    kind = _schema_type(schema)
    envelope = "$"
    if kind == "object" and isinstance(schema.get("properties"), Mapping):
        for key in ENVELOPE_KEYS:
            sub = _ref(doc, schema["properties"].get(key))
            if isinstance(sub, Mapping) and _schema_type(sub) == "array":
                schema, kind, envelope = sub, "array", f"$.{key}"
                break
    if kind == "array":
        return {"kind": "records", "envelope": envelope, "fields": _declared_fields(doc, schema.get("items"))}
    if kind == "object":
        return {"kind": "record", "envelope": "$", "fields": _declared_fields(doc, schema)}
    return {"kind": "value", "envelope": "$", "fields": _declared_fields(doc, schema)}


def _input(doc: Mapping[str, Any], raw: Any) -> Input | None:
    raw = _ref(doc, raw)
    if (
        not isinstance(raw, Mapping)
        or not raw.get("name")
        or raw.get("in") not in ("path", "query", "header", "cookie")
    ):
        return None
    schema = (
        _ref(doc, raw.get("schema")) if "schema" in raw else raw
    )  # Swagger 2.0 keeps the type on the parameter
    schema = schema if isinstance(schema, Mapping) else {}
    return Input(
        name=str(raw["name"]),
        place=str(raw["in"]),
        type=_schema_type(schema),
        required=bool(raw.get("required")) or raw.get("in") == "path",
        choices=tuple(schema.get("enum") or ()),
        format=str(schema.get("format") or ""),
        description=str(raw.get("description") or "")[:300],
    )


def _body_fields(doc: Mapping[str, Any], schema: Any) -> tuple[Input, ...]:
    """A request body's top-level fields as inputs (their type picks a form's box)."""
    schema = _ref(doc, schema)
    if not isinstance(schema, Mapping):
        return ()
    if isinstance(schema.get("allOf"), list):
        merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        for part in schema["allOf"]:
            part = _ref(doc, part)
            if isinstance(part, Mapping):
                merged["properties"] |= dict(part.get("properties") or {})
                merged["required"] += list(part.get("required") or [])
        schema = merged
    required = set(schema.get("required") or ())
    out = []
    for name, sub in (schema.get("properties") or {}).items():
        sub = _ref(doc, sub)
        sub = sub if isinstance(sub, Mapping) else {}
        out.append(
            Input(
                str(name),
                "body",
                _schema_type(sub),
                name in required,
                tuple(sub.get("enum") or ()),
                str(sub.get("format") or ""),
                str(sub.get("description") or "")[:300],
            )
        )
    return tuple(out)


def _name(raw: Mapping[str, Any], method: str, path: str) -> str:
    given = str(raw.get("operationId") or "").strip()
    if given:
        return re.sub(r"[^A-Za-z0-9_]+", "_", given).strip("_") or "call"
    words = [w for w in re.split(r"[^A-Za-z0-9]+", path) if w]
    return "_".join([method.lower(), *words]) or method.lower()


def actions(doc: Mapping[str, Any], api: str = "") -> dict[str, Action]:
    """Every action an OpenAPI 3.x or Swagger 2.0 document declares, by name (its operationId, else its method
    and path). The document is the only way an action comes in: what is learned refines it, never replaces
    it."""
    if not isinstance(doc, Mapping) or not isinstance(doc.get("paths"), Mapping):
        raise ActionError("A specification is an OpenAPI 3.x or Swagger 2.0 document with paths.")
    found: dict[str, Action] = {}
    for path, item in doc["paths"].items():
        item = _ref(doc, item)
        if not isinstance(item, Mapping):
            continue
        shared = [p for p in (_input(doc, raw) for raw in item.get("parameters") or ()) if p]
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            raw = item.get(method)
            if not isinstance(raw, Mapping):
                continue
            own = [p for p in (_input(doc, r) for r in raw.get("parameters") or ()) if p]
            names = {(p.name, p.place) for p in own}
            listed = [p for p in shared if (p.name, p.place) not in names] + own
            declared = {p.name for p in listed if p.place == "path"}
            # A {placeholder} the document forgot to declare is a required path input all the same.
            listed += [
                Input(n, "path", required=True)
                for n in re.findall(r"\{([^}/]+)\}", str(path))
                if n not in declared
            ]
            inputs = tuple(listed)
            body, body_required, media = _request_body(doc, raw)
            name = _name(raw, method, str(path))
            while name in found:
                name += "_"
            found[name] = Action(
                name=name,
                method=method.upper(),
                path=str(path),
                api=api,
                summary=str(raw.get("summary") or raw.get("description") or "")[:300],
                inputs=inputs,
                body=body,
                body_required=body_required,
                body_media=media,
                declared=_declared(doc, raw.get("responses")),
            )
    return found


def _request_body(doc: Mapping[str, Any], raw: Mapping[str, Any]) -> tuple[tuple[Input, ...], bool, str]:
    """OpenAPI 3's requestBody, or Swagger 2.0's `in: body` parameter: its fields, required, media type."""
    for param in raw.get("parameters") or ():
        param = _ref(doc, param)
        if isinstance(param, Mapping) and param.get("in") == "body":
            return _body_fields(doc, param.get("schema")), bool(param.get("required")), "application/json"
    body = _ref(doc, raw.get("requestBody"))
    if not isinstance(body, Mapping) or not isinstance(body.get("content"), Mapping) or not body["content"]:
        return (), False, "application/json"
    content = body["content"]
    media = next((m for m in content if "json" in str(m)), next(iter(content)))
    return _body_fields(doc, (content.get(media) or {}).get("schema")), bool(body.get("required")), str(media)


# ===== 2. Inputs: checked first =====


def _typed(value: Any, kind: str, name: str) -> Any:
    """A value as its input's type, or refused naming it."""
    if kind == "integer":
        if isinstance(value, bool) or not re.fullmatch(r"-?\d+", str(value).strip()):
            raise ActionError(f"{name} is a whole number: {value!r} is not one.", name)
        return int(str(value).strip())
    if kind == "number":
        try:
            return float(value) if not isinstance(value, bool) else _not_number(name, value)
        except (TypeError, ValueError):
            raise ActionError(f"{name} is a number: {value!r} is not one.", name) from None
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if str(value).strip().lower() in ("true", "yes", "1", "false", "no", "0"):
            return str(value).strip().lower() in ("true", "yes", "1")
        raise ActionError(f"{name} is true or false: {value!r} is neither.", name)
    if kind == "array" and isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return value


def _not_number(name: str, value: Any) -> float:
    raise ActionError(f"{name} is a number: {value!r} is not one.", name)


def checked(action: Action, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    """The inputs checked against the action (each by its name; a body as `body`, or its fields flat): a
    missing required one, a wrong type, a value outside its choices or a name the action does not take is
    refused naming it. Answers {"path", "query", "header", "cookie": {name: value}, "body": ...}."""
    given = dict(inputs or {})
    out: dict[str, Any] = {"path": {}, "query": {}, "header": {}, "cookie": {}, "body": None}
    for one in action.inputs:
        value = given.pop(one.name, None)
        if value is None or value == "":
            if one.required:
                raise ActionError(f"{one.name} ({one.place}) is required.", one.name)
            continue
        value = _typed(value, one.type, one.name)
        if one.choices and value not in one.choices:
            choices = ", ".join(map(str, one.choices))
            raise ActionError(f"{one.name} is one of {choices}: {value!r} is not.", one.name)
        out[one.place][one.name] = value
    body = given.pop("body", None)
    named = {b.name for b in action.body}
    flat = {k: given.pop(k) for k in list(given) if k in named}
    if given:
        raise ActionError(f"{action.name} takes no input called {sorted(given)[0]}.", sorted(given)[0])
    if body is None and flat:
        body = flat
    elif isinstance(body, dict) and flat:
        body = body | flat
    if isinstance(body, str) and body.strip()[:1] in ("{", "["):
        try:
            body = json.loads(body)
        except ValueError as error:
            raise ActionError(f"The body is not JSON ({error}).", "body") from None
    if body is None and action.body_required:
        raise ActionError(f"{action.name} needs a body.", "body")
    out["body"] = _checked_body(action, body) if isinstance(body, dict) else body
    return out


def _checked_body(action: Action, body: dict[str, Any]) -> dict[str, Any]:
    out = dict(body)
    for one in action.body:
        value = out.get(one.name)
        if value is None:
            if one.required:
                raise ActionError(f"The body's {one.name} is required.", f"body.{one.name}")
            continue
        if one.type in ("integer", "number", "boolean"):
            out[one.name] = _typed(value, one.type, f"The body's {one.name}")
        if one.choices and out[one.name] not in one.choices:
            choices = ", ".join(map(str, one.choices))
            raise ActionError(f"The body's {one.name} is one of {choices}.", f"body.{one.name}")
    return out


def _plain(value: Any) -> str:
    return ("true" if value else "false") if isinstance(value, bool) else str(value)


def url_of(
    base_url: str, action: Action, parts: Mapping[str, Any], extra: Mapping[str, Any] | None = None
) -> str:
    """The call's address: the path's values put in (quoted), the query after it (`extra` over it)."""
    path = action.path
    for name, value in (parts.get("path") or {}).items():
        path = path.replace("{" + name + "}", urllib.parse.quote(_plain(value), safe=""))
    url = path if path.startswith(("http://", "https://")) else base_url.rstrip("/") + path
    query = dict(parts.get("query") or {}) | dict(extra or {})
    pairs = [
        (k, _plain(v))
        for k, values in query.items()
        if values is not None
        for v in (values if isinstance(values, list | tuple) else [values])
    ]
    return url + (("&" if "?" in url else "?") + urllib.parse.urlencode(pairs) if pairs else "")


# ===== 3. Sending =====


@dataclass
class Request:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None

    def parts(self) -> tuple[str, dict[str, str]]:
        """The address's path and its query's values (a send to a process of this computer takes them)."""
        split = urllib.parse.urlsplit(self.url)
        return split.path or "/", dict(urllib.parse.parse_qsl(split.query))


@dataclass
class Response:
    """An answer as it came: its status (0: the API was not reached), headers (lower-case names), body."""

    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


Send = Callable[[Request], Response]


@dataclass
class Api:
    """Where an action is sent: its base address and its send (a sign-in already inside it)."""

    base_url: str
    send: Send
    name: str = ""


def _urllib_send(sign: Callable[[Request], Request] | None, timeout: float) -> Send:
    def send(request: Request) -> Response:
        signed = sign(request) if sign else request
        if not signed.url.startswith(("https://", "http://")):
            return Response(0, {}, b"An API's address starts with https:// or http://.")
        made = urllib.request.Request(  # noqa: S310 (http and https only: checked above)
            signed.url, data=signed.body, method=signed.method, headers=signed.headers
        )
        try:
            with urllib.request.urlopen(made, timeout=timeout) as answer:  # noqa: S310 (http and https only)
                return Response(
                    answer.status, {k.lower(): v for k, v in answer.headers.items()}, answer.read()
                )
        except urllib.error.HTTPError as error:
            got = {k.lower(): v for k, v in (error.headers.items() if error.headers else [])}
            return Response(error.code, got, error.read())
        except (urllib.error.URLError, OSError) as error:
            return Response(0, {}, str(getattr(error, "reason", error)).encode())

    return send


def signed_by(auth: Mapping[str, Any] | None) -> Callable[[Request], Request] | None:
    """A sign-in read from environment variables at each call, never stored: {"type": "bearer", "variable"},
    {"type": "api_key", "name", "in": "header" | "query", "variable"}, {"type": "basic", "user", "password"}
    (the variables' names). None: no sign-in."""
    kind = str((auth or {}).get("type") or "none")
    if kind == "none":
        return None
    given = dict(auth or {})

    def sign(request: Request) -> Request:
        headers = dict(request.headers)
        url = request.url
        if kind == "bearer":
            headers["Authorization"] = "Bearer " + os.environ.get(str(given.get("variable")), "")
        elif kind == "api_key" and given.get("in") == "query":
            pair = urllib.parse.urlencode(
                {str(given.get("name")): os.environ.get(str(given.get("variable")), "")}
            )
            url += ("&" if "?" in url else "?") + pair
        elif kind == "api_key":
            headers[str(given.get("name") or "X-Api-Key")] = os.environ.get(str(given.get("variable")), "")
        elif kind == "basic":
            user = os.environ.get(str(given.get("user")), "")
            pair = f"{user}:{os.environ.get(str(given.get('password')), '')}"
            headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
        return Request(request.method, url, headers, request.body)

    return sign


def http(base_url: str, auth: Mapping[str, Any] | None = None, timeout: float = 30.0, name: str = "") -> Api:
    """An API reached over HTTPS from here, its sign-in from environment variables (signed_by)."""
    return Api(base_url, _urllib_send(signed_by(auth), timeout), name)


def from_client(client: Any, name: str = "") -> Api:
    """An API_<name>.py client (Add API's made file) as an Api: its own sign-in and address; each request one
    `_send` of it (its own retries inside), an answer that is not a success a Response all the same."""
    error_type = getattr(client, "Error", Exception)

    def send(request: Request) -> Response:
        try:
            status, headers, raw = client._send(request.method, request.url, request.headers, request.body)
        except error_type as error:
            status = int(getattr(error, "status", 0) or 0)
            text = str(getattr(error, "text", "") or error)
            return Response(status, {}, text.encode())
        return Response(
            int(status), {str(k).lower(): str(v) for k, v in dict(headers).items()}, bytes(raw or b"")
        )

    return Api(str(getattr(client, "base_url", "")), send, name)


_FOUND: dict[str, Callable[[str], Api]] = {}
_OBSERVERS: list[Callable[[dict[str, Any]], Any]] = []


def observe(hook: Callable[[dict[str, Any]], Any] | None) -> None:
    """A hook handed each call's facts as it ends (the envelope's `facts`: times, sizes, outcome, who; never a
    value): the seam the call statistics plug into (Plans/stats.plan.md). None: no hook, the default."""
    _OBSERVERS.clear()
    if hook is not None:
        _OBSERVERS.append(hook)


def use(find: Callable[[str], Api] | None) -> None:
    """How run() finds an API by its name (an exported project names its APIs; the app gives its own)."""
    _FOUND.clear()
    if find is not None:
        _FOUND["find"] = find


def _api_of(api: Api | str | None, action: Action) -> Api:
    if isinstance(api, Api):
        return api
    named = api or action.api
    if "find" not in _FOUND:
        raise ActionError(f"No API is set up to send {action.name} to: pass api=, or use(find) first.", "api")
    return _FOUND["find"](str(named))


def _wait(headers: Mapping[str, str], attempt: int) -> float:
    """Retry-After's seconds or date (at most MAX_WAIT), else 1, 2, 4 ... seconds."""
    said = str(headers.get("retry-after") or "").strip()
    if said.isdigit():
        return min(float(said), MAX_WAIT)
    if said:
        try:
            when = email.utils.parsedate_to_datetime(said)
            return max(0.0, min((when - datetime.datetime.now(datetime.UTC)).total_seconds(), MAX_WAIT))
        except (TypeError, ValueError):
            pass
    return min(2.0 ** (attempt - 1), MAX_WAIT)


def sent(
    api: Api, request: Request, retries: int = 3, sleep: Callable[[float], Any] = time.sleep
) -> tuple[Response, int]:
    """One request, tried again on 429 (any method) and on a passing error (5xx, unreachable: a method that
    changes nothing twice only), waiting as the API says. Answers the last Response and the retries made."""
    attempt = 0
    while True:
        answer = api.send(request)
        passing = answer.status in PASSING or answer.status == 0
        again = answer.status == 429 or request.method.upper() in IDEMPOTENT
        if not passing or not again or attempt >= retries:
            return answer, attempt
        attempt += 1
        sleep(_wait(answer.headers, attempt))


# ===== 4. Detection: format and envelope =====


def _text_of(raw: bytes) -> str | None:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _xml(text: str) -> Any:
    """XML as plain values (no DOCTYPE, no entity: refused): attributes as @name, text as #text, a repeated
    child a list."""
    if re.search(r"<!DOCTYPE|<!ENTITY", text, re.IGNORECASE):
        raise ActionError("The answer is XML with a DOCTYPE or an entity: refused.")
    root = ElementTree.fromstring(text)  # noqa: S314 (no DOCTYPE, no entity: checked above)
    return {_tag(root.tag): _element(root)}


def _tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element(element: ElementTree.Element) -> Any:
    out: dict[str, Any] = {f"@{_tag(k)}": v for k, v in element.attrib.items()}
    for child in element:
        name, value = _tag(child.tag), _element(child)
        if name in out:
            out[name] = (out[name] if isinstance(out[name], list) else [out[name]]) + [value]
        else:
            out[name] = value
    text = (element.text or "").strip()
    if not out:
        return text
    if text:
        out["#text"] = text
    return out


def _cell(text: str) -> Any:
    """A CSV cell as the value it reads as: empty, a whole number, a number, true or false, else text."""
    value = text.strip()
    if value == "":
        return None
    if re.fullmatch(r"-?\d{1,18}", value) and not (len(value) > 1 and value.lstrip("-").startswith("0")):
        return int(value)
    if re.fullmatch(r"-?\d*\.\d+(e-?\d+)?|-?\d+e-?\d+", value, re.IGNORECASE):
        return float(value)
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return text


def _csv(text: str, delimiter: str) -> list[dict[str, Any]]:
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows:
        return []
    header = [h.strip() or f"column{n + 1}" for n, h in enumerate(rows[0])]
    return [
        {h: _cell(v) for h, v in zip(header, row, strict=False)}
        for row in rows[1:]
        if any(c.strip() for c in row)
    ]


def _delimiter(text: str, kind: str) -> str | None:
    """CSV's or TSV's delimiter when the text reads as one (by its content type, or two lines that agree)."""
    if "tab-separated" in kind or "tsv" in kind:
        return "\t"
    lines = [line for line in text.splitlines()[:5] if line.strip()]
    for mark in ("\t", ",", ";", "|"):
        counts = {line.count(mark) for line in lines}
        if len(lines) >= 2 and len(counts) == 1 and counts != {0}:
            return mark
    return "," if "csv" in kind else None


def _json_lines(text: str) -> list[Any] | None:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    try:
        return [json.loads(line) for line in lines]
    except ValueError:
        return None


def _yaml(text: str) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]  # optional: PyYAML where it is installed
    except ImportError:
        return text
    try:
        return yaml.safe_load(text)
    except Exception:
        return text


def _is_file_type(kind: str) -> bool:
    if not kind:
        return False
    texty = ("json", "xml", "yaml", "csv", "tab-separated", "text/", "javascript", "x-www-form-urlencoded")
    return not any(t in kind for t in texty)


def _file(response: Response, kind: str) -> dict[str, Any]:
    disposition = response.headers.get("content-disposition", "")
    named = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition, re.IGNORECASE)
    out: dict[str, Any] = {
        "name": urllib.parse.unquote(named.group(1)) if named else "",
        "type": kind or "application/octet-stream",
        "size": len(response.body),
    }
    if len(response.body) <= MAX_FILE:
        out["base64"] = base64.b64encode(response.body).decode()
    return out


def detected(response: Response) -> tuple[str, Any]:
    """The answer's format and its value: ("json" | "jsonl" | "xml" | "csv" | "tsv" | "yaml" | "file" | "text"
    | "empty", value). The content type is a first guess; the bytes decide."""
    kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if not response.body.strip() or response.status == 204:
        return "empty", None
    text = _text_of(response.body)
    if text is None or (_is_file_type(kind) and text.lstrip()[:1] not in ("{", "[", "<")):
        return "file", _file(response, kind)
    stripped = text.strip()
    if stripped[:1] in ("{", "[") or "json" in kind:
        try:
            return "json", json.loads(stripped)
        except ValueError:
            lines = _json_lines(stripped)
            if lines is not None:
                return "jsonl", lines
    if stripped.startswith("<") and not stripped.lower().startswith(("<!doctype html", "<html")):
        try:
            return "xml", _xml(stripped)
        except (ElementTree.ParseError, ActionError):
            pass
    if "yaml" in kind:
        return "yaml", _yaml(stripped)
    mark = _delimiter(stripped, kind) if "html" not in kind else None
    if mark:
        return ("tsv" if mark == "\t" else "csv"), _csv(stripped, mark)
    return "text", text


def _records_list(value: Any) -> bool:
    return isinstance(value, list) and (not value or all(isinstance(v, Mapping) for v in value[:50]))


def _key(mapping: Mapping[str, Any], names: Iterable[str]) -> str | None:
    """The first of `names` the mapping holds, in any case."""
    lowered = {norm(str(k)): str(k) for k in mapping}
    for name in names:
        if norm(name) in lowered:
            return lowered[norm(name)]
    return None


def _header_rows(value: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]] | None:
    """A header-and-rows pair: {"columns": [...], "rows": [[...]]} (a column a name or {"name": ...})."""
    head, rows = _key(value, HEADER_KEYS), _key(value, ROWS_KEYS)
    if not head or not rows or head == rows:
        return None
    header, body = value[head], value[rows]
    if (
        not isinstance(header, list)
        or not isinstance(body, list)
        or not all(isinstance(r, list) for r in body[:50])
    ):
        return None
    names = [str(h.get("name") if isinstance(h, Mapping) else h) for h in header]
    return f"$.{rows}", [dict(zip(names, row, strict=False)) for row in body]


def envelope(value: Any) -> tuple[str, str, Any]:
    """Where the answer's data sits and what it is: (kind, path, data). Records wherever they sit (a top-level
    list; value, data, items, results ... one or two levels down; a header-and-rows pair; the one list of
    records an object holds), else a record (an object), a value (a scalar or a list of them), or empty."""
    if value is None:
        return "empty", "$", None
    if isinstance(value, str):
        return "text", "$", value
    if _records_list(value):
        return "records", "$", list(value)
    if isinstance(value, list):
        return "value", "$", value
    if not isinstance(value, Mapping):
        return "value", "$", value
    paired = _header_rows(value)
    if paired:
        return "records", paired[0], paired[1]
    found = _envelope_in(value, "$", 0)
    if found:
        return "records", found[0], found[1]
    return "record", "$", dict(value)


def _envelope_in(value: Mapping[str, Any], at: str, depth: int) -> tuple[str, list[Any]] | None:
    key = _key(value, ENVELOPE_KEYS)
    if key and _records_list(value[key]):
        return f"{at}.{key}", list(value[key])
    if not key and len(value) == 1 and isinstance(next(iter(value.values())), Mapping):
        key = next(iter(value))  # a lone wrapper ({"result": {...}}, XML's root element): looked inside
    if key and isinstance(value[key], Mapping) and depth < 2:
        paired = _header_rows(value[key])
        if paired:
            return at + "." + key + paired[0][1:], paired[1]
        inner = _envelope_in(value[key], f"{at}.{key}", depth + 1)
        if inner:
            return inner
    lists = [k for k, v in value.items() if _records_list(v) and v]
    others = [norm(str(k)) for k in value if k not in lists]
    if len(lists) == 1 and all(any(word in k for word in META_WORDS) for k in others):
        return f"{at}.{lists[0]}", list(value[lists[0]])  # {"orders": [...], "count": 2}: the one list
    return None


# ===== 5. Paging =====


def _link_header(headers: Mapping[str, str]) -> str | None:
    for part in str(headers.get("link") or "").split(","):
        match = re.match(r"\s*<([^>]+)>\s*;(.*)", part)
        if match and re.search(r'rel\s*=\s*"?next"?', match.group(2), re.IGNORECASE):
            return match.group(1)
    return None


def _holders(value: Any) -> list[Mapping[str, Any]]:
    """The answer and the objects that hold its paging (links, meta, pagination ...)."""
    if not isinstance(value, Mapping):
        return []
    out = [value]
    for key in value:
        if norm(str(key)) in {norm(h) for h in PAGING_HOLDERS} and isinstance(value[key], Mapping):
            out.append(value[key])
    return out


def _next_link(value: Any) -> str | None:
    for holder in _holders(value):
        for key, found in holder.items():
            if norm(str(key)) not in {norm(n) for n in NEXT_LINKS}:
                continue
            if isinstance(found, Mapping):
                found = found.get("href") or found.get("url")
            if isinstance(found, str) and found.startswith(("http://", "https://", "/")):
                return found
    return None


def _next_token(value: Any) -> str | None:
    for holder in _holders(value):
        for key, found in holder.items():
            if (
                norm(str(key)) in {norm(n) for n in NEXT_TOKENS}
                and isinstance(found, str | int)
                and str(found)
            ):
                return str(found)
            if norm(str(key)) == "next" and isinstance(found, str) and not found.startswith(("http", "/")):
                return found
    return None


def _more_flag(value: Any) -> bool | None:
    for holder in _holders(value):
        key = _key(holder, ("has_more", "hasMore", "has_next", "hasNextPage", "more"))
        if key and isinstance(holder[key], bool):
            return bool(holder[key])
    return None


def _input_named(action: Action, names: Iterable[str]) -> Input | None:
    wanted = {norm(n) for n in names}
    return next((i for i in action.inputs if i.place == "query" and norm(i.name) in wanted), None)


def _total_pages(value: Any) -> int | None:
    for holder in _holders(value):
        key = _key(holder, TOTAL_PAGES)
        if key and isinstance(holder[key], int) and not isinstance(holder[key], bool):
            return int(holder[key])
    return None


@dataclass
class Pager:
    """How a call's next page is asked for, worked out from each answer."""

    action: Action
    base_url: str
    parts: dict[str, Any]
    by: str = ""  # how pages were followed: next link, cursor, offset, page number
    page_size: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def next(self, value: Any, headers: Mapping[str, str], count: int) -> str | None:
        """The next page's address, or None when this was the last."""
        if _more_flag(value) is False or count == 0:
            return None
        link = _next_link(value) or _link_header(headers)
        if link:
            self.by = "next link"
            return link if link.startswith("http") else _joined(self.base_url, link)
        token = _next_token(value)
        token_input = _input_named(self.action, TOKEN_INPUTS)
        if token and token_input:
            self.by = "cursor"
            self.extra[token_input.name] = token
            return url_of(self.base_url, self.action, self.parts, self.extra)
        return self._counted(value, count)

    def _counted(self, value: Any, count: int) -> str | None:
        """Offset and limit, or page numbers: the next while the page came back full."""
        self.page_size = self.page_size or count
        offset, page = _input_named(self.action, OFFSET_INPUTS), _input_named(self.action, PAGE_INPUTS)
        if offset:
            if count < self.page_size:
                return None
            self.by = "offset"
            start = int(self.extra.get(offset.name, self.parts["query"].get(offset.name, 0)) or 0)
            self.extra[offset.name] = start + count
            return url_of(self.base_url, self.action, self.parts, self.extra)
        if page:
            now = int(self.extra.get(page.name, self.parts["query"].get(page.name, 1)) or 1)
            total = _total_pages(value)
            if (total is not None and now >= total) or (total is None and count < self.page_size):
                return None
            self.by = "page number"
            self.extra[page.name] = now + 1
            return url_of(self.base_url, self.action, self.parts, self.extra)
        return None


def _joined(base_url: str, link: str) -> str:
    split = urllib.parse.urlsplit(base_url)
    return f"{split.scheme}://{split.netloc}{link}"


# ===== 6. Shapes: types read from values =====

_DATES = (
    (re.compile(r"\d{4}-\d{2}-\d{2}$"), "iso", "%Y-%m-%d"),
    (re.compile(r"\d{1,2}/\d{1,2}/\d{4}$"), "m/d/y", "%m/%d/%Y"),
    (re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}$"), "d.m.y", "%d.%m.%Y"),
    (re.compile(r"\d{1,2} [A-Za-z]{3} \d{4}$"), "d mon y", "%d %b %Y"),
)
_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")


def norm(name: str) -> str:
    """A name matched forgivingly: any case, and camelCase, snake_case, kebab-case and spaces alike
    (CustomerID = customer_id = Customer Id)."""
    return re.sub(r"[^0-9a-z.@#\[\]]", "", str(name).lower())


def _date_style(text: str) -> tuple[str, str] | None:
    for pattern, style, fmt in _DATES:
        if pattern.match(text):
            try:
                datetime.datetime.strptime(text, fmt)
            except ValueError:
                continue
            return style, fmt
    return None


def type_of(value: Any) -> tuple[str, str]:
    """A value's type and format: ("integer" | "number" | "boolean" | "date" | "datetime" | "text" | "list" |
    "object" | "null", its format: "" as typed, "text" for a number or boolean in text, a date's style)."""
    if value is None:
        return "null", ""
    if isinstance(value, bool):
        return "boolean", ""
    if isinstance(value, int):
        return "integer", ""
    if isinstance(value, float):
        return "number", ""
    if isinstance(value, list):
        return "list", ""
    if isinstance(value, Mapping):
        return "object", ""
    text = str(value).strip()
    if re.fullmatch(r"-?\d{1,15}", text) and not (len(text.lstrip("-")) > 1 and text.lstrip("-")[0] == "0"):
        return "integer", "text"
    if re.fullmatch(r"-?\d*\.\d+|-?\d+\.\d*", text):
        return "number", "text"
    if text.lower() in ("true", "false"):
        return "boolean", "text"
    if _DATETIME.match(text):
        return "datetime", "iso"
    style = _date_style(text)
    if style:
        return "date", style[0]
    return "text", ""


def flat(record: Mapping[str, Any], prefix: str = "", depth: int = 0) -> dict[str, Any]:
    """A record's fields by path (customer.id): nested objects flattened, a list kept whole."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping) and value and depth < MAX_DEPTH:
            out |= flat(value, path, depth + 1)
        else:
            out[path] = value
    return out


def _merged(old: dict[str, Any] | None, kind: str, fmt: str) -> dict[str, Any]:
    """One field's type over several values: a whole number and a number a number, anything and text text."""
    if old is None:
        return {"type": kind if kind != "null" else "null", "format": fmt, "empty": kind == "null"}
    if kind == "null":
        return old | {"empty": True}
    if old["type"] == "null":
        return {"type": kind, "format": fmt, "empty": True}
    if old["type"] == kind:
        return old if old["format"] == fmt else old | {"format": "mixed"}
    if {old["type"], kind} == {"integer", "number"}:
        return old | {"type": "number"}
    return old | {"type": "text", "format": ""}


def fields_of(items: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each path's detected type, format and whether it can be empty, over every record (a field absent from
    some records can be empty)."""
    found: dict[str, dict[str, Any]] = {}
    for record in items:
        for path, value in record.items():
            if path not in found and len(found) >= MAX_FIELDS:
                continue
            found[path] = _merged(found.get(path), *type_of(value))
    for path in found:
        if any(path not in record for record in items):
            found[path]["empty"] = True
    return {p: found[p] for p in sorted(found)}


def fingerprint(shape: Mapping[str, Any]) -> str:
    """A shape's fingerprint: its kind, envelope and each path's type (formats and empties aside)."""
    said = {
        "kind": shape.get("kind"),
        "envelope": shape.get("envelope"),
        "fields": {p: f.get("type") for p, f in (shape.get("fields") or {}).items()},
    }
    return hashlib.sha256(json.dumps(said, sort_keys=True).encode()).hexdigest()[:16]


def shape_of(
    kind: str, data: Any, envelope_at: str = "$", fmt: str = "json", status: int = 200
) -> dict[str, Any]:
    """An answer's shape: its status, kind, format, envelope and each field's type (never a value)."""
    if kind == "records":
        fields = fields_of([flat(r) for r in data])
    elif kind == "record":
        fields = fields_of([flat(data)])
    elif kind in ("value", "text"):
        found = type_of(data)
        fields = {"value": {"type": found[0], "format": found[1], "empty": data is None}}
    else:
        fields = {}
    shape = {"status": status, "kind": kind, "format": fmt, "envelope": envelope_at, "fields": fields}
    return shape | {"fingerprint": fingerprint(shape)}


def sent_shape(parts: Mapping[str, Any]) -> dict[str, Any]:
    """What was sent, as a shape: each query, path and body field's type (never a value)."""
    given: dict[str, Any] = {}
    for place in ("path", "query"):
        given |= {f"{place}.{k}": v for k, v in (parts.get(place) or {}).items()}
    body = parts.get("body")
    if isinstance(body, Mapping):
        given |= {f"body.{k}": v for k, v in flat(body).items()}
    elif body is not None:
        given["body"] = body
    fields = fields_of([given]) if given else {}
    return {"fields": fields, "fingerprint": fingerprint({"fields": fields})}


# ===== 7. Drift: against the last shape =====


def compare(old: Mapping[str, Any] | None, new: Mapping[str, Any]) -> dict[str, Any]:
    """What changed since the last shape: fields added, missing, retyped (a type, or a number now in text, a
    date in another style), the envelope moved, and the renames worth offering (a field gone and a new one of
    the same type, its name alike). Empty lists when nothing changed; nothing at all on a first shape."""
    drift: dict[str, Any] = {"added": [], "missing": [], "retyped": [], "moved": None, "offers": []}
    if not old or not old.get("fields"):
        return drift
    before, now = dict(old.get("fields") or {}), dict(new.get("fields") or {})
    by_norm = {norm(p): p for p in now}
    matched = {p: by_norm.get(norm(p)) for p in before}
    drift["missing"] = sorted(p for p, m in matched.items() if m is None)
    drift["added"] = sorted(set(now) - {m for m in matched.values() if m})
    for path, match in sorted(matched.items()):
        if match and before[path]["type"] != "null" and now[match]["type"] != "null":
            retyped = _retyped(before[path], now[match])
            if retyped:
                drift["retyped"].append({"path": path, "was": retyped[0], "now": retyped[1]})
    if old.get("envelope") and old.get("envelope") != new.get("envelope"):
        drift["moved"] = {"was": old.get("envelope"), "now": new.get("envelope")}
    drift["offers"] = _offers(before, now, drift["missing"], drift["added"])
    return drift


def _words(kind: Mapping[str, Any]) -> str:
    style = kind.get("format") or ""
    return str(kind["type"]) + (
        " in text" if style == "text" else f" ({style})" if style and style != "mixed" else ""
    )


def _retyped(was: Mapping[str, Any], now: Mapping[str, Any]) -> tuple[str, str] | None:
    if was["type"] != now["type"]:
        return _words(was), _words(now)
    if (was.get("format") or "") != (now.get("format") or "") and "mixed" not in (
        was.get("format"),
        now.get("format"),
    ):
        return _words(was), _words(now)
    return None


def _alike(a: str, b: str) -> bool:
    """Two names alike enough to offer one for the other (customer_id, customerNo): a shared stem of four."""
    x, y = norm(a.rsplit(".", 1)[-1]), norm(b.rsplit(".", 1)[-1])
    stem = 0
    while stem < min(len(x), len(y)) and x[stem] == y[stem]:
        stem += 1
    return stem >= 4 or (len(x) >= 3 and (x in y or y in x))


def _offers(
    before: Mapping[str, Any], now: Mapping[str, Any], missing: list[str], added: list[str]
) -> list[dict[str, str]]:
    offers = []
    for gone in missing:
        alike = [n for n in added if now[n]["type"] == before[gone]["type"] and _alike(gone, n)]
        if len(alike) == 1:  # one candidate only: two would be a guess
            offers.append({"from": gone, "to": alike[0], "said": f"{alike[0]} looks like {gone}: use it?"})
    return offers


def coerce(value: Any, known: Mapping[str, Any]) -> tuple[Any, bool]:
    """A value as the type it had before, where it reads cleanly (a number in text, a date in another style:
    ISO), else as it came; and whether it read cleanly."""
    kind, fmt = type_of(value)
    want = known.get("type")
    if value is None or (kind == want and (fmt == known.get("format") or fmt == "")):
        return value, True
    text = str(value).strip()
    try:
        if want == "integer" and kind == "integer":
            return int(text), True
        if want == "number" and kind in ("integer", "number"):
            return float(text), True
        if want == "boolean" and kind == "boolean":
            return text.lower() == "true", True
    except ValueError:
        return value, False
    if want == "date" and kind == "date":
        style = _date_style(text)
        if style and known.get("format") == "iso":
            return datetime.datetime.strptime(text, style[1]).date().isoformat(), True
        return value, style is not None
    if want == "datetime" and kind == "datetime":
        return value, True
    if want == "text":
        return (text if not isinstance(value, list | dict) else value), True
    return value, False


def pick(record: Mapping[str, Any], path: str) -> Any:
    """A field of a (flattened or whole) record by its path, matched forgivingly (CustomerID = customer_id;
    customer.id in a nested record too). None when it is not there."""
    if path in record:
        return record[path]
    wanted = norm(path)
    for key, value in record.items():
        if norm(str(key)) == wanted:
            return value
    head, _, rest = path.partition(".")
    for key, value in record.items():
        if rest and norm(str(key)) == norm(head) and isinstance(value, Mapping):
            return pick(value, rest)
    return None


def adapted(
    records: list[dict[str, Any]], known: Mapping[str, Any] | None, renames: Mapping[str, str] | None = None
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Flattened records made to read as before: each known path there (by its known name; matched in any
    case and style; a rename the user took filled from its new name; else null), a retyped value coerced where
    it reads cleanly. Answers the records and the marks: {path: "missing" | "retyped" | "renamed" | "new"}."""
    fields = dict((known or {}).get("fields") or {})
    if not fields:
        return records, {}
    renames = dict(renames or {})
    marks: dict[str, str] = {}
    out = [_adapted_row(record, fields, renames, marks) for record in records]
    known_names = {norm(p) for p in fields} | {norm(n) for n in renames.values()}
    for path in sorted({k for r in records for k in r}):
        if norm(path) not in known_names:
            marks[path] = "new"
    return out, dict(sorted(marks.items()))


def _mark(value: Any, known: Mapping[str, Any], clean: bool) -> str:
    """A value's mark against its known type: "" as before, "retyped" when it came as another type."""
    if value is None:
        return ""
    if not clean:
        return "retyped"
    kind, fmt = type_of(value)
    same = kind == known.get("type") and fmt in (known.get("format"), "")
    return "" if same or known.get("format") == "mixed" else "retyped"


def _adapted_row(
    record: Mapping[str, Any], fields: Mapping[str, Any], renames: Mapping[str, str], marks: dict[str, str]
) -> dict[str, Any]:
    by_norm = {norm(k): k for k in record}
    row = dict(record)
    for path, kind in fields.items():
        source = by_norm.get(norm(path))
        if source is None and path in renames:
            source = by_norm.get(norm(renames[path]))
            if source is not None:
                marks.setdefault(path, "renamed")
        if source is None:
            row[path] = None
            marks.setdefault(path, "missing")
            continue
        value, clean = coerce(record[source], kind)
        if source != path and source not in renames.values():
            row.pop(source, None)  # the same field by its known name (CustomerID read as customer_id)
        row[path] = value if clean else record[source]
        said = _mark(record[source], kind, clean)
        if said:
            marks.setdefault(path, said)
    return row


def drift_words(drift: Mapping[str, Any], since: str = "") -> str:
    """The drift line on an action: "2 fields new, 1 missing since 14 Nov" ("" when nothing changed)."""
    parts: list[str] = []
    for key, word in (("added", "new"), ("missing", "missing"), ("retyped", "retyped")):
        count = len(drift.get(key) or ())
        if count:
            parts.append(
                f"{count} {'field' if count == 1 else 'fields'} {word}" if not parts else f"{count} {word}"
            )
    if drift.get("moved"):
        parts.append("the records moved")
    return (", ".join(parts) + (f" since {since}" if since else "")) if parts else ""


# ===== 8. The call =====


def _message(value: Any) -> str:
    """An error answer's own words (message, error_description, detail, error ...)."""
    if isinstance(value, Mapping):
        key = _key(value, MESSAGE_KEYS)
        if key:
            found = value[key]
            return _message(found) if isinstance(found, Mapping) else str(found)[:500]
    if isinstance(value, str):
        return " ".join(value.split())[:500]
    return ""


def status_words(status: int, action: str) -> str:
    if status == 0:
        return f"{action}: the API could not be reached."
    if status in (401, 403):
        return f"{action} answered {status}: the API refused the sign-in."
    if status == 404:
        return f"{action} answered 404: there is nothing at that address."
    if status == 429:
        return f"{action} answered 429: too many requests, even after waiting."
    if status >= 500:
        return f"{action} answered {status}: the API failed on its side."
    return f"{action} answered {status}: the API refused the request."


def _shown_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: ("(hidden)" if HIDDEN_HEADERS.search(k) else str(v)[:500]) for k, v in sorted(headers.items())}


def _request(action: Action, base_url: str, parts: Mapping[str, Any], url: str | None = None) -> Request:
    headers = {"Accept": "application/json, */*;q=0.5", "User-Agent": "swissarmybench-api-adapter/" + VERSION}
    headers |= {k: _plain(v) for k, v in (parts.get("header") or {}).items()}
    if parts.get("cookie"):
        headers["Cookie"] = "; ".join(f"{k}={_plain(v)}" for k, v in parts["cookie"].items())
    body = parts.get("body")
    data: bytes | None = None
    if body is not None:
        if "x-www-form-urlencoded" in action.body_media and isinstance(body, Mapping):
            data = urllib.parse.urlencode({k: _plain(v) for k, v in body.items()}).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
            headers["Content-Type"] = "application/json"
    return Request(action.method.upper(), url or url_of(base_url, action, parts), headers, data)


def _failed(action: Action, response: Response, fmt: str, value: Any) -> dict[str, Any]:
    fixes = (
        [{"label": "Try again", "action": "try_again"}]
        if response.status in PASSING or not response.status
        else []
    )
    return refusal(status_words(response.status, action.name), action.name, fixes, _message(value))


def run(
    action: Action,
    inputs: Mapping[str, Any] | None = None,
    *,
    api: Api | str | None = None,
    known: Mapping[str, Any] | None = None,
    renames: Mapping[str, str] | None = None,
    required: Sequence[str] = (),
    max_pages: int = MAX_PAGES,
    max_records: int = MAX_RECORDS,
    retries: int = 3,
    sleep: Callable[[float], Any] = time.sleep,
    who: str = "",
) -> dict[str, Any]:
    """One call, any payload, one envelope:

    {"ok", "status", "action", "kind": records | record | value | file | empty | text,
     "records" | "record" | "value" | "file" | "text": the answer in that shape (records flattened by path),
     "paging": {"pages", "by", "more", "stopped"}, "shape": {... "drift", "marks", "words"},
     "sent": its shape,
     "raw": the answer as it came (its first page; sign-in headers hidden), "error": the one refusal shape}

    `known`: the endpoint's last shape (keep() kept it): the records read as before (fields matched
    forgivingly, a missing one null, a retyped one coerced), and what changed in `shape.drift`. `renames`: the
    renames the user took ({old: new}). `required`: paths that must be there: only these fail a call on drift.
    `who`: who made the call (the user, the agent, a widget), for its facts only.

    Each envelope carries `facts` (times in parts, sizes, outcome, who; never a value), and observe()'s hook
    is handed them: the seam the call statistics plug into."""
    tally: dict[str, Any] = {"wait": 0.0, "first": None, "bytes": 0, "started": time.perf_counter()}

    def paused(seconds: float) -> Any:
        tally["wait"] += seconds
        return sleep(seconds)

    answer = _call(
        action, inputs, api, known, renames, required, max_pages, max_records, retries, paused, tally
    )
    answer["facts"] = _facts(answer, tally, who)
    for hook in list(_OBSERVERS):
        try:
            hook(dict(answer["facts"]))
        except Exception:  # noqa: S110 (a statistics hook never fails a call)
            pass
    return answer


def _facts(answer: Mapping[str, Any], tally: Mapping[str, Any], who: str) -> dict[str, Any]:
    """A call's facts for the statistics: times (wait, first byte, total, in ms), sizes (records, bytes,
    pages,
    columns returned), outcome (status, retries, its error's kind), who and which action. Never a value."""
    ms = round((time.perf_counter() - tally["started"]) * 1000, 1)
    first = tally["first"]
    error = answer.get("error") or {}
    status = int(answer.get("status") or 0)
    kind = (
        ""
        if not error
        else "input"
        if status == 0 and error.get("where") != "api"
        else "status"
        if status
        else "unreachable"
    )
    return {
        "api": answer.get("api") or "",
        "action": answer.get("action") or "",
        "who": who,
        "ms": {"wait": round(tally["wait"] * 1000, 1), "first_byte": first, "total": ms},
        "size": {
            "records": len(answer.get("records") or ()),
            "bytes": int(tally["bytes"]),
            "pages": int((answer.get("paging") or {}).get("pages") or 0),
            "columns": len((answer.get("shape") or {}).get("fields") or {}),
        },
        "outcome": {
            "status": status,
            "ok": bool(answer.get("ok")),
            "retries": int((answer.get("paging") or {}).get("retried") or 0),
            "error": kind,
        },
    }


def _call(
    action: Action,
    inputs: Mapping[str, Any] | None,
    api: Api | str | None,
    known: Mapping[str, Any] | None,
    renames: Mapping[str, str] | None,
    required: Sequence[str],
    max_pages: int,
    max_records: int,
    retries: int,
    sleep: Callable[[float], Any],
    tally: dict[str, Any],
) -> dict[str, Any]:
    name = f"{action.method} {action.path}"
    try:
        parts = checked(action, inputs)
    except ActionError as error:
        return _envelope(action, 0, "empty", error=refusal(str(error), error.where or action.name))
    try:
        target = _api_of(api, action)
    except ActionError as error:
        return _envelope(action, 0, "empty", error=refusal(str(error), "api"))
    request = _request(action, target.base_url, parts)
    pager = Pager(action, target.base_url, parts)
    pages, records, raw, first_fmt, value, kind, at = 0, [], None, "empty", None, "empty", "$"
    response = Response(0)
    retried, stopped, more = 0, "", False
    seen: set[str] = set()
    url: str | None = request.url
    while url:
        response, tries = sent(
            target, Request(request.method, url, request.headers, request.body), retries, sleep
        )
        retried += tries
        if tally["first"] is None:
            tally["first"] = round((time.perf_counter() - tally["started"]) * 1000, 1)
        tally["bytes"] += len(response.body)
        fmt, value = detected(response)
        if pages == 0:
            first_fmt, raw = (
                fmt,
                {"status": response.status, "headers": _shown_headers(response.headers), "body": value},
            )
        if not 200 <= response.status < 300:
            if pages == 0:
                return _envelope(
                    action,
                    response.status,
                    "empty",
                    raw=raw,
                    fmt=fmt,
                    error=_failed(action, response, fmt, value),
                    parts=parts,
                )
            stopped, more = f"page {pages + 1} answered {response.status}", True
            break
        pages += 1
        page_kind, page_at, data = (fmt, "$", value) if fmt in ("file", "empty") else envelope(value)
        if pages == 1:
            kind, at = page_kind, page_at
        if page_kind != "records" or kind != "records":
            break
        mark = hashlib.sha256(json.dumps(data, default=str, sort_keys=True).encode()).hexdigest()
        if mark in seen:
            stopped = "the same page came back"
            break
        seen.add(mark)
        records.extend(data)
        if len(records) >= max_records:
            records, more, stopped = (
                records[:max_records],
                True,
                f"the call's limit of {max_records:,} records",
            )
            break
        url = pager.next(value, response.headers, len(data))
        if url and pages >= max_pages:
            more, stopped, url = True, f"the call's limit of {max_pages} pages", None
    paging = {"pages": pages, "by": pager.by, "more": more, "stopped": stopped, "retried": retried}
    if kind == "records":
        return _records_envelope(
            action, response.status, records, at, first_fmt, raw, paging, known, renames, required, parts
        )
    data = value if kind != "records" else None
    if kind == "record":
        data = dict(envelope(value)[2])
    return _single_envelope(
        action, response.status, kind, data, at, first_fmt, raw, paging, known, required, parts, name
    )


def _records_envelope(
    action: Action,
    status: int,
    records: list[Any],
    at: str,
    fmt: str,
    raw: Any,
    paging: dict[str, Any],
    known: Mapping[str, Any] | None,
    renames: Mapping[str, str] | None,
    required: Sequence[str],
    parts: Mapping[str, Any],
) -> dict[str, Any]:
    rows = [flat(r) for r in records]
    shape = shape_of("records", records, at, fmt, status)
    rows, marks = adapted(rows, known, renames)
    return _envelope(
        action,
        status,
        "records",
        records=rows,
        raw=raw,
        fmt=fmt,
        paging=paging,
        shape=_with_drift(shape, known, marks),
        required=required,
        parts=parts,
    )


def _single_envelope(
    action: Action,
    status: int,
    kind: str,
    data: Any,
    at: str,
    fmt: str,
    raw: Any,
    paging: dict[str, Any],
    known: Mapping[str, Any] | None,
    required: Sequence[str],
    parts: Mapping[str, Any],
    name: str,
) -> dict[str, Any]:
    shape = shape_of(kind, data, at, fmt, status)
    more: dict[str, Any] = {}
    marks: dict[str, str] = {}
    if kind == "record":
        rows, marks = adapted([flat(data)], known)
        more["record"] = data
        more["flat"] = rows[0]
    elif kind == "file":
        more["file"] = data
    elif kind == "text":
        more["text"] = data
    elif kind == "value":
        more["value"] = data
    return _envelope(
        action,
        status,
        kind,
        raw=raw,
        fmt=fmt,
        paging=paging,
        shape=_with_drift(shape, known, marks),
        required=required,
        parts=parts,
        **more,
    )


def _with_drift(
    shape: dict[str, Any], known: Mapping[str, Any] | None, marks: dict[str, str]
) -> dict[str, Any]:
    drift = compare(known, shape)
    changed = bool(known and known.get("fingerprint") and known.get("fingerprint") != shape["fingerprint"])
    return shape | {"drift": drift, "marks": marks, "changed": changed, "words": drift_words(drift)}


def _envelope(
    action: Action,
    status: int,
    kind: str,
    *,
    raw: Any = None,
    fmt: str = "empty",
    paging: Mapping[str, Any] | None = None,
    shape: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
    required: Sequence[str] = (),
    parts: Mapping[str, Any] | None = None,
    **answer: Any,
) -> dict[str, Any]:
    shape = dict(
        shape
        or shape_of(kind, None, "$", fmt, status) | {"drift": compare(None, {}), "marks": {}, "words": ""}
    )
    if error is None and required:
        present = {norm(p) for p in (shape.get("fields") or {})}
        lacking = [
            p for p in required if norm(p) not in present or (shape.get("marks") or {}).get(p) == "missing"
        ]
        if lacking:
            error = refusal(
                f"{lacking[0]} is required and the answer no longer has it.",
                lacking[0],
                details=drift_words(shape.get("drift") or {}),
            )
    out: dict[str, Any] = {
        "ok": error is None,
        "status": status,
        "action": action.name,
        "api": action.api,
        "kind": kind,
        "format": fmt,
        "paging": dict(paging or {"pages": 0, "by": "", "more": False, "stopped": "", "retried": 0}),
        "shape": shape,
        "sent": sent_shape(parts or {}),
        "raw": raw,
        "error": dict(error) if error else None,
    }
    return out | answer


# ===== 9. Learning: the current shape, kept; the widgets' contract =====


def shape_file(name: str) -> str:
    """An endpoint's shape file's name: shapes/<name>.json (a name safe on every disk)."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._") + ".json"


def keep(
    old: Mapping[str, Any] | None, answer: Mapping[str, Any], today: str
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The endpoint's current shape after an answer (types only, never a value), and the change to say once
    (None: the same shape, only `seen` moved on). A failed call keeps the old shape. Byte-stable: text() of
    the
    same shape is the same bytes."""
    current = dict(old or {})
    if not answer.get("ok") or (answer.get("kind") == "empty" and answer.get("status") != 204):
        return current, None
    shape = dict(answer.get("shape") or {})
    returned = {k: shape.get(k) for k in ("status", "kind", "format", "envelope", "fields", "fingerprint")}
    sent_now = dict(answer.get("sent") or {})
    changed = (current.get("returned") or {}).get("fingerprint") != returned["fingerprint"]
    sent_changed = bool(sent_now.get("fields")) and (current.get("sent") or {}).get(
        "fingerprint"
    ) != sent_now.get("fingerprint")
    current |= {"action": answer.get("action"), "api": answer.get("api"), "seen": today}
    if sent_changed:
        current["sent"] = {"fields": sent_now["fields"], "fingerprint": sent_now["fingerprint"]}
    if not changed:
        return current, None
    drift = compare(current.get("returned"), returned) if current.get("returned") else None
    current["returned"] = returned
    current["changed"] = today
    current["change"] = {k: drift[k] for k in ("added", "missing", "retyped", "moved")} if drift else None
    current["offers"] = [
        o
        for o in (drift or {}).get("offers", [])
        if o["from"] not in (current.get("renames") or {})
        and o["from"] not in (current.get("declined") or [])
    ]
    return current, (current["change"] if drift else None)


def answered(shape: Mapping[str, Any], offer_from: str, to: str, take: bool) -> dict[str, Any]:
    """A rename offer answered and remembered for the endpoint: taken ({old: new} in `renames`) or declined
    (never offered again)."""
    out = dict(shape)
    if take:
        out["renames"] = dict(out.get("renames") or {}) | {offer_from: to}
    else:
        out["declined"] = sorted({*(out.get("declined") or []), offer_from})
    out["offers"] = [o for o in out.get("offers") or [] if o.get("from") != offer_from]
    return out


def text(shape: Mapping[str, Any]) -> str:
    """A shape file's text: sorted, two-space indented, one newline at the end (same shape, same bytes)."""
    return json.dumps(shape, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


_BOXES = {
    "integer": "number",
    "number": "number",
    "boolean": "switch",
    "date": "date",
    "datetime": "datetime",
    "list": "json",
    "object": "json",
    "text": "text",
    "null": "text",
}


def box(kind: str, choices: Sequence[Any] = (), fmt: str = "") -> str:
    """A field's box in a form by its type: a closed set a dropdown, a date a date picker, a switch."""
    if choices:
        return "dropdown"
    if fmt in ("date", "date-time"):
        return "date" if fmt == "date" else "datetime"
    return _BOXES.get({"string": "text", "array": "list"}.get(kind, kind), "text")


def learn(shape: Mapping[str, Any] | None, action: Action | None = None) -> dict[str, Any]:
    """The learned contract an endpoint gives the widgets (the canvas's field pickers, an Event's payload
    fields, the drift marks): what it answers (kind and each path's type) as last seen, else as declared; what
    it takes (each input and body field with its box); the drift line; the renames on offer."""
    kept = dict(shape or {})
    returned = kept.get("returned") or {}
    declared = dict((action.declared if action else {}) or {})
    learned = bool(returned.get("fields") or returned.get("kind"))
    fields = (
        returned.get("fields")
        if learned
        else {p: {"type": t, "format": "", "empty": True} for p, t in (declared.get("fields") or {}).items()}
    )
    change = kept.get("change") or {}
    marks = {p: "new" for p in change.get("added") or []} | {
        p: "retyped" for p in (r["path"] for r in change.get("retyped") or [])
    }
    takes = [
        i.to_json() | {"box": box(i.type, i.choices, i.format)} for i in (action.inputs if action else ())
    ]
    body = [i.to_json() | {"box": box(i.type, i.choices, i.format)} for i in (action.body if action else ())]
    return {
        "action": kept.get("action") or (action.name if action else ""),
        "learned": learned,
        "kind": returned.get("kind") or declared.get("kind") or "",
        "envelope": returned.get("envelope") or declared.get("envelope") or "$",
        "fields": [
            {
                "path": p,
                "type": f["type"],
                "format": f.get("format", ""),
                "empty": f.get("empty", False),
                "mark": marks.get(p, ""),
            }
            for p, f in sorted((fields or {}).items())
        ],
        "inputs": takes,
        "body": body,
        "drift": drift_words(change, kept.get("changed", "")) if change else "",
        "missing": list(change.get("missing") or []),
        "offers": list(kept.get("offers") or []),
        "renames": dict(kept.get("renames") or {}),
        "seen": kept.get("seen", ""),
        "maps_to": mapped(returned.get("kind") or declared.get("kind") or "", action),
    }


# ===== 10. Discovery =====


def mapped(kind: str, action: Action | None = None) -> list[str]:
    """What an endpoint's answer maps to, by its shape: records a table (an API table widget, a grid), a
    record
    a detail card or an edit form, a value a metric, a file a download; a write a form of its body."""
    if action is not None and action.writes:
        return ["form"]
    return {
        "records": ["table", "grid"],
        "record": ["detail", "form"],
        "value": ["metric"],
        "file": ["download"],
        "text": ["text"],
    }.get(kind, [])


def _probe_order(found: Mapping[str, Action]) -> list[Action]:
    """The read endpoints a probe calls: no required input first (lists), then those whose required path
    inputs
    another answer may give (an id from GET /orders for GET /orders/{id}); a write never."""
    reads = [a for a in found.values() if a.method == "GET"]
    plain = [a for a in reads if not any(i.required for i in a.inputs)]
    rest = [a for a in reads if a not in plain and all(i.place == "path" for i in a.inputs if i.required)]
    return plain + rest


def _smallest(action: Action) -> dict[str, Any]:
    """The smallest page an action takes: 1 in its limit-like input, when it has one."""
    limit = _input_named(action, LIMIT_INPUTS)
    return {limit.name: 1} if limit and limit.type in ("integer", "number", "string") else {}


def _filled(action: Action, ids: Mapping[str, list[Any]]) -> dict[str, Any] | None:
    """Required inputs filled from other answers (an input order_id from an answer's order_id, or id from the
    list whose path its own extends). None when one cannot be filled."""
    out: dict[str, Any] = {}
    for one in action.inputs:
        if not one.required:
            continue
        stem = action.path.split("{")[0].rstrip("/")
        found = ids.get(norm(one.name)) or ids.get(f"{stem}|id") or ids.get(f"{stem}|{norm(one.name)}")
        if not found:
            return None
        out[one.name] = found[0]
    return out


def _ids_from(action: Action, answer: Mapping[str, Any], ids: dict[str, list[Any]]) -> None:
    """The id-like values an answer offers to other endpoints' required inputs: kept in memory for this
    discovery only, never in a shape."""
    rows = answer.get("records") or ([answer.get("flat")] if answer.get("flat") else [])
    for row in rows[:1]:
        for path, value in row.items():
            if value is None or isinstance(value, list | dict):
                continue
            leaf = norm(path.rsplit(".", 1)[-1])
            if leaf == "id" or leaf.endswith("id") or leaf.endswith("key") or leaf.endswith("code"):
                ids.setdefault(leaf, []).append(value)
                ids.setdefault(f"{action.path.rstrip('/')}|{leaf}", []).append(value)


def pairs(found: Mapping[str, Action], shapes: Mapping[str, Mapping[str, Any]]) -> list[dict[str, str]]:
    """Master and detail pairs: a list endpoint and the one-record endpoint under its path (GET /orders and
    GET
    /orders/{id}), or a list whose field names another endpoint's required input (customer_id)."""
    out = []
    for master in found.values():
        kind = ((shapes.get(master.name) or {}).get("returned") or {}).get("kind") or master.declared.get(
            "kind"
        )
        if master.method != "GET" or kind != "records":
            continue
        fields = {
            norm(p.rsplit(".", 1)[-1])
            for p in (
                ((shapes.get(master.name) or {}).get("returned") or {}).get("fields")
                or master.declared.get("fields")
                or {}
            )
        }
        for detail in found.values():
            needed = [i for i in detail.inputs if i.required and i.place == "path"]
            if detail is master or detail.method != "GET" or len(needed) != 1:
                continue
            under = detail.path.startswith(master.path.rstrip("/") + "/{")
            if under or norm(needed[0].name) in fields:
                key = "id" if under and norm(needed[0].name) not in fields else needed[0].name
                out.append({"master": master.name, "detail": detail.name, "by": key, "input": needed[0].name})
    return out


def discover(
    found: Mapping[str, Action],
    api: Api | str | None = None,
    known: Mapping[str, Mapping[str, Any]] | None = None,
    max_calls: int = 20,
    retries: int = 1,
    sleep: Callable[[float], Any] = time.sleep,
) -> dict[str, Any]:
    """Learn an API (the caller has the user's Allow): one GET per read endpoint at the smallest page size
    (one page each), required inputs filled from other endpoints' answers, at most `max_calls` calls, never an
    endpoint that writes (those are learned from the specification). Answers each endpoint's envelope without
    its values (its shape, status and error only), what each maps to, the master and detail pairs, and what
    was not called and why. The caller keeps the shapes; no value leaves this call."""
    known = dict(known or {})
    ids: dict[str, list[Any]] = {}
    answers: dict[str, dict[str, Any]] = {}
    skipped: dict[str, str] = {
        a.name: "it writes: learned from the specification" for a in found.values() if a.writes
    }
    calls = 0
    for action in _probe_order(found):
        filled = _filled(action, ids)
        if filled is None:
            skipped[action.name] = "its required inputs: no other answer gave them"
            continue
        if calls >= max_calls:
            skipped[action.name] = f"the discovery's limit of {max_calls} calls"
            continue
        calls += 1
        answer = run(
            action,
            filled | _smallest(action),
            api=api,
            known=known.get(action.name, {}).get("returned"),
            max_pages=1,
            retries=retries,
            sleep=sleep,
        )
        _ids_from(action, answer, ids)
        answers[action.name] = {
            k: answer[k]
            for k in ("ok", "status", "kind", "format", "shape", "sent", "error", "action", "api")
        }
    for action in found.values():
        if action.name not in answers and action.name not in skipped:
            skipped[action.name] = "its required inputs are not ids another answer gives"
    shapes = {n: {"returned": a["shape"]} for n, a in answers.items() if a["ok"]}
    return {
        "calls": calls,
        "answers": answers,
        "skipped": skipped,
        "maps": {
            n: mapped(
                ((shapes.get(n) or {}).get("returned") or {}).get("kind") or a.declared.get("kind", ""), a
            )
            for n, a in found.items()
        },
        "pairs": pairs(found, shapes),
    }


# ===== 11. Tables: records through adapter =====


def table(answer: Mapping[str, Any], adapter: Any = None) -> Any:
    """A records answer as an Arrow table, through adapter (the one crossing point): the module beside this
    file, or the one given (the app's own)."""
    if adapter is None:
        import adapter  # type: ignore[import-not-found, no-redef]  # beside this file in the scaffold

    rows = answer.get("records")
    if rows is None and answer.get("flat") is not None:
        rows = [answer["flat"]]
    return adapter.arrow_of(list(rows or []))
