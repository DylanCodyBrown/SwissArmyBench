"""A project's local sandbox API (the owner, 2026-11-21: "So this project now needs a new file in the back
called
API.py" / "Instead of your API just call it local sandbox apis"): API.py at the project's top, the user's own
file.

  [HEADER]     its settings in a `# /// swissarmybench-api` TOML block at its top (as a blade file's): name,
               description, target (fastapi, azure_functions, aws_lambda; extensions add theirs), base_path
  [ENDPOINTS]  read with ast, never run: each function under `@endpoint("GET", "/orders/{region}")`, its
               parameters (the path's, the body: a TypedDict, a dataclass, dict or list; the query's), its
               answer
               (the return annotation), its docstring, its line, the connections it asks for (connection("X"))
               and the SQL strings it sends; the TypedDicts and dataclasses as models
  [OPENAPI]    the OpenAPI 3.0 document of those (the APIs page's explorer reads it as an imported API's)
  [SCAFFOLD]   the file New project writes (a header, one commented example endpoint)

Pure rules: standard library only.
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

FILE = "API.py"
HEADER_TYPE = "swissarmybench-api"
_OPEN = f"# /// {HEADER_TYPE}"
_CLOSE = "# ///"
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def agent_writes_words(first: str) -> str:
    """What the agent's first write through the API asks: Allow covers the rest of this session."""
    return (
        f"{first} on the local sandbox API. Allow lets the agent write through it for the rest of this "
        "session: the project's sandbox only, never live data; Reset undoes it."
    )


DEFAULT_TARGET = "fastapi"
_PATH = re.compile(
    r"^/(?:[A-Za-z0-9._~-]+|\{[A-Za-z_][A-Za-z0-9_]*\})?(?:/(?:[A-Za-z0-9._~-]+|\{[A-Za-z_][A-Za-z0-9_]*\}))*$"
)
_SIMPLE = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "Decimal": "number",
           "date": "string", "datetime": "string"}  # fmt: skip
_FORMATS = {"date": "date", "datetime": "date-time"}


class ApiFileError(ValueError):
    """API.py cannot be read as a local sandbox API, in one sentence with its line."""


@dataclass(frozen=True)
class Settings:
    name: str = "Local sandbox API"
    description: str = ""
    target: str = DEFAULT_TARGET
    base_path: str = ""

    def to_json(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "target": self.target,
            "base_path": self.base_path,
        }


@dataclass
class Param:
    name: str
    where: str  # path, query, body
    type: str  # its annotation as written
    required: bool
    default: Any = None


@dataclass
class Endpoint:
    name: str
    method: str
    path: str
    line: int
    end: int
    summary: str
    description: str
    params: list[Param]
    returns: str
    connections: list[str] = field(default_factory=list)
    sql: list[dict[str, Any]] = field(default_factory=list)  # each SQL string it sends: {text, line}
    streams: bool = False  # DuckDB does part of its work over the stream (it calls duckdb.connect itself)

    @property
    def writes(self) -> bool:
        return self.method != "GET"

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "line": self.line,
            "end": self.end,
            "summary": self.summary,
            "description": self.description,
            "params": [p.__dict__ for p in self.params],
            "returns": self.returns,
            "connections": self.connections,
            "sql": self.sql,
            "streams": self.streams,
            "writes": self.writes,
        }


@dataclass
class Model:
    name: str
    fields: dict[str, tuple[str, bool]]  # name -> (annotation, required)
    line: int


@dataclass
class Api:
    settings: Settings
    endpoints: list[Endpoint]
    models: dict[str, Model]
    problems: list[dict[str, Any]]

    def to_json(self) -> dict[str, Any]:
        return {
            "settings": self.settings.to_json(),
            "endpoints": [e.to_json() for e in self.endpoints],
            "models": {
                m.name: {"fields": {k: v[0] for k, v in m.fields.items()}, "line": m.line}
                for m in self.models.values()
            },
            "problems": self.problems,
        }


# ===== the header =====


def header_span(lines: list[str]) -> tuple[int, int] | None:
    """Where API.py's header opens and closes: at the file's top (only comments and blank lines before)."""
    for i, line in enumerate(lines[:200]):
        if line.strip() == _OPEN:
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == _CLOSE:
                    return i, j
            return None
        if line.strip() and not line.lstrip().startswith("#"):
            return None
    return None


def read_settings(text: str) -> Settings:
    lines = text.split("\n")
    span = header_span(lines)
    if span is None:
        return Settings()
    body = "\n".join(
        line[2:] if line.startswith("# ") else line.lstrip("#") for line in lines[span[0] + 1 : span[1]]
    )
    try:
        raw = tomllib.loads(body)
    except tomllib.TOMLDecodeError as error:
        raise ApiFileError(f"Line {span[0] + 1}: API.py's header is not TOML: {error}.") from None
    return Settings(
        str(raw.get("name") or Settings.name),
        str(raw.get("description") or ""),
        str(raw.get("target") or DEFAULT_TARGET),
        check_base(raw.get("base_path") or ""),
    )


def check_base(value: Any) -> str:
    base = str(value or "").strip().rstrip("/")
    if base and not _PATH.match(base):
        raise ApiFileError(f"A base path is like /api, not {value!r}.")
    return base


def _toml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def header_block(settings: Settings) -> list[str]:
    return [
        _OPEN,
        f"# name = {_toml(settings.name)}",
        f"# description = {_toml(settings.description)}",
        f"# target = {_toml(settings.target)}",
        f"# base_path = {_toml(settings.base_path)}",
        _CLOSE,
    ]


def with_settings(text: str, settings: Settings) -> str:
    """API.py with its header written (or added at its top); every other byte as it was."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    span = header_span(lines)
    block = header_block(settings)
    lines = block + lines[span[1] + 1 :] if span else [*block, *lines] if text else [*block, ""]
    if span and span[0] > 0:
        lines = text.replace("\r\n", "\n").split("\n")[: span[0]] + lines
    return newline.join(lines)


# ===== the endpoints =====


def _annotation(node: ast.expr | None) -> str:
    return ast.unparse(node) if node is not None else ""


def _literal(node: ast.expr | None) -> Any:
    try:
        return ast.literal_eval(node) if node is not None else None
    except (ValueError, SyntaxError):
        return ast.unparse(node) if node is not None else None


def _models(tree: ast.Module) -> dict[str, Model]:
    out: dict[str, Model] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {ast.unparse(b) for b in node.bases}
        decorators = {ast.unparse(d).split("(")[0] for d in node.decorator_list}
        typed = any(b.endswith("TypedDict") for b in bases)
        dataclass_ = any(d.endswith("dataclass") for d in decorators)
        if not (typed or dataclass_):
            continue
        total = not any(k.arg == "total" and _literal(k.value) is False for k in node.keywords)
        fields: dict[str, tuple[str, bool]] = {}
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                kind = _annotation(item.annotation)
                required = total and item.value is None and not kind.startswith("NotRequired")
                fields[item.target.id] = (re.sub(r"^NotRequired\[(.*)\]$", r"\1", kind), required)
        out[node.name] = Model(node.name, fields, node.lineno)
    return out


_ROWS_BODY = re.compile(r"^(?:typing\.)?Annotated\[\s*[\w.]*Table\s*,\s*([A-Za-z_]\w*)\s*\]$")


def _as_sent(kind: str) -> str:
    """A body made Arrow by the adapter (`Annotated[pa.Table, Order]`: its rows checked against Order, then an
    Arrow table) is sent as a list of its model: what OpenAPI, Try it and a made-up request see."""
    found = _ROWS_BODY.match(kind.strip())
    return f"list[{found.group(1)}]" if found else kind


def _is_body_type(kind: str, models: Mapping[str, Model]) -> bool:
    bare = re.sub(r"\s*\|\s*None$|^Optional\[(.*)\]$", r"\1", kind).strip()
    return bare in models or bare in ("dict", "list") or bare.startswith(("dict[", "list[", "Mapping["))


def _connections_and_sql(fn: ast.AST) -> tuple[list[str], list[dict[str, Any]]]:
    names: list[str] = []
    sql: list[dict[str, Any]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        callee = ast.unparse(node.func)
        if callee.split(".")[-1] == "connection" and node.args and isinstance(node.args[0], ast.Constant):
            names.append(str(node.args[0].value))
        method = callee.split(".")[-1]
        if method in ("query", "execute", "executemany", "read_arrow", "sql") and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                sql.append({"text": first.value, "line": first.lineno})
            elif isinstance(first, ast.JoinedStr):
                sql.append({"text": ast.unparse(first), "line": first.lineno, "formatted": True})
    return list(dict.fromkeys(names)), sql


def parse(text: str) -> Api:
    """API.py's settings, endpoints and models; what is wrong with an endpoint is a problem with its line."""
    settings = read_settings(text)
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return Api(
            settings,
            [],
            {},
            [{"line": error.lineno or 1, "message": f"Python could not read it: {error.msg}."}],
        )
    models = _models(tree)
    problems: list[dict[str, Any]] = []
    endpoints: list[Endpoint] = []
    seen: dict[tuple[str, str], str] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call) and ast.unparse(decorator.func).split(".")[-1] == "endpoint"
            ):
                continue
            args = [_literal(a) for a in decorator.args]
            if len(args) < 2 or not all(isinstance(a, str) for a in args[:2]):
                problems.append(
                    {
                        "line": decorator.lineno,
                        "message": '@endpoint takes a method and a path: @endpoint("GET", "/orders").',
                    }
                )
                continue
            method, path = str(args[0]).upper(), str(args[1])
            if method not in METHODS:
                problems.append(
                    {
                        "line": decorator.lineno,
                        "message": f"{node.name}'s method is one of {', '.join(METHODS)}, not {args[0]}.",
                    }
                )
                continue
            if not _PATH.match(path):
                problems.append(
                    {
                        "line": decorator.lineno,
                        "message": f"{node.name}'s path {path!r} is not a path like /orders/{{id}}.",
                    }
                )
                continue
            key = (method, re.sub(r"\{[^}]+\}", "{}", path))
            if key in seen:
                problems.append(
                    {
                        "line": decorator.lineno,
                        "message": f"{method} {path} is answered by {seen[key]} already.",
                    }
                )
                continue
            seen[key] = node.name
            in_path = re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", path)
            params: list[Param] = []
            positional = node.args.posonlyargs + node.args.args
            defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
            for arg, default in zip(positional, defaults, strict=True):
                kind = _as_sent(_annotation(arg.annotation))
                where = "path" if arg.arg in in_path else "body" if _is_body_type(kind, models) else "query"
                params.append(Param(arg.arg, where, kind or "str", default is None, _literal(default)))
            missing = [p for p in in_path if p not in {a.arg for a in positional}]
            if missing:
                problems.append(
                    {
                        "line": node.lineno,
                        "message": f"{node.name} has no parameter for the path's {{{missing[0]}}}.",
                    }
                )
            if sum(p.where == "body" for p in params) > 1:
                problems.append(
                    {
                        "line": node.lineno,
                        "message": f"{node.name} takes one body; give it one TypedDict or dataclass.",
                    }
                )
            summary = next(
                (
                    k.value
                    for k in decorator.keywords
                    if k.arg == "summary" and isinstance(k.value, ast.Constant)
                ),
                None,
            )
            doc = ast.get_docstring(node) or ""
            connections, sql = _connections_and_sql(node)
            streams = any(
                isinstance(n, ast.Call) and ast.unparse(n.func) == "duckdb.connect" for n in ast.walk(node)
            )
            endpoints.append(
                Endpoint(
                    node.name,
                    method,
                    path,
                    node.lineno,
                    node.end_lineno or node.lineno,
                    str(summary.value) if summary is not None else doc.split("\n")[0],
                    doc,
                    params,
                    _annotation(node.returns),
                    connections,
                    sql,
                    streams,
                )
            )
    return Api(settings, endpoints, models, problems)


# ===== an endpoint's contract: its body's fields and a made-up request, one definition for every reader =====


def _bare(kind: str) -> str:
    """An annotation without its quotes and its optional wrapping (Optional[X], X | None)."""
    text = kind.strip().strip("'\"")
    text = re.sub(r"\s*\|\s*None$", "", text)
    found = re.match(r"^Optional\[(.*)\]$", text)
    return (found.group(1) if found else text).strip()


def body_of(endpoint: Endpoint) -> Param | None:
    return next((p for p in endpoint.params if p.where == "body"), None)


def body_model(endpoint: Endpoint, models: Mapping[str, Model]) -> Model | None:
    """The model an endpoint's body is (a TypedDict or dataclass of API.py's; a list of one: that one)."""
    body = body_of(endpoint)
    if body is None:
        return None
    kind = _bare(body.type)
    listed = re.match(r"^(?:list|List|Sequence)\[(.*)\]$", kind)
    return models.get(_bare(listed.group(1)) if listed else kind)


def body_fields(endpoint: Endpoint, models: Mapping[str, Model]) -> dict[str, dict[str, Any]] | None:
    """The body's fields in order, each with its type and whether it must be sent; None when the body is not
    one of API.py's models (a plain dict or list, or no body). The Try it form, an Event's body mapping on
    the Canvas, Payload shapes and the OpenAPI document's schema are all this."""
    model = body_model(endpoint, models)
    if model is None:
        return None
    return {name: {"type": kind, "required": required} for name, (kind, required) in model.fields.items()}


def made_up_value(kind: str, name: str, models: Mapping[str, Model], depth: int = 0) -> Any:
    """A made-up value for an annotation (never a row's): the same for the same name and type."""
    bare = _bare(kind)
    listed = re.match(r"^(?:list|List|Sequence)\[(.*)\]$", bare)
    if listed:
        return [made_up_value(listed.group(1), name, models, depth + 1)]
    if bare in models and depth < 3:
        return {k: made_up_value(v[0], k, models, depth + 1) for k, v in models[bare].fields.items()}
    simple = bare.split(".")[-1]
    if simple == "int":
        return 101 if name.lower().endswith(("id", "key")) else 3
    if simple in ("float", "Decimal"):
        return 12.5
    if simple == "bool":
        return True
    if simple == "date":
        return "2026-01-15"
    if simple == "datetime":
        return "2026-01-15T09:30:00"
    if bare.startswith(("dict", "Dict", "Mapping")) or bare in models:
        return {}
    if bare in ("list", "List"):
        return []
    return f"made-up {name}"


def made_up(endpoint: Endpoint, models: Mapping[str, Model]) -> dict[str, Any]:
    """A made-up request for an endpoint: {"path": {name: value}, "query": {name: value}, "body": value or
    None}. A query parameter with a default starts from it. Try it starts from this, with what the
    endpoint's learned shape knows over it (domain/api_actions.py tried); the agent reads the same in
    `api(state)`."""
    out: dict[str, Any] = {"path": {}, "query": {}, "body": None}
    for p in endpoint.params:
        if p.where == "body":
            out["body"] = made_up_value(p.type, p.name, models)
        elif p.where == "query" and p.default is not None:
            out["query"][p.name] = p.default
        else:
            out[p.where][p.name] = made_up_value(p.type, p.name, models)
    return out


# ===== the OpenAPI document =====


def schema_of(kind: str, models: Mapping[str, Model]) -> dict[str, Any]:
    """An annotation as a JSON schema (a model as a $ref)."""
    text = kind.strip()
    if not text or text in ("Any", "object", "None"):
        return {} if text != "None" else {"type": "null"}
    optional = re.match(r"^Optional\[(.*)\]$", text) or re.match(r"^(.*?)\s*\|\s*None$", text)
    if optional:
        return schema_of(optional.group(1), models) | {"nullable": True}
    listed = re.match(r"^(?:list|List|Sequence)\[(.*)\]$", text)
    if listed:
        return {"type": "array", "items": schema_of(listed.group(1), models)}
    if text in ("list", "Table"):
        return {"type": "array", "items": {"type": "object"}}
    if text.startswith(("dict", "Dict", "Mapping")):
        return {"type": "object"}
    if text in models:
        return {"$ref": f"#/components/schemas/{text}"}
    bare = text.split(".")[-1]
    if bare in _SIMPLE:
        return {"type": _SIMPLE[bare]} | ({"format": _FORMATS[bare]} if bare in _FORMATS else {})
    return {"type": "object"}


def openapi(api: Api) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for e in api.endpoints:
        op: dict[str, Any] = {"operationId": e.name, "summary": e.summary, "responses": {}}
        if e.description:
            op["description"] = e.description
        params = [
            {
                "name": p.name,
                "in": p.where,
                "required": p.where == "path" or p.required,
                "schema": schema_of(p.type, api.models),
            }
            | ({"default": p.default} if p.default is not None and p.where == "query" else {})
            for p in e.params
            if p.where in ("path", "query")
        ]
        if params:
            op["parameters"] = params
        body = next((p for p in e.params if p.where == "body"), None)
        if body is not None:
            op["requestBody"] = {
                "required": body.required,
                "content": {"application/json": {"schema": schema_of(body.type, api.models)}},
            }
        answer = schema_of(e.returns, api.models)
        status = "204" if e.method == "DELETE" and e.returns in ("", "None") else "200"
        op["responses"][status] = {"description": "OK"} | (
            {"content": {"application/json": {"schema": answer}}} if status == "200" else {}
        )
        op["responses"]["4XX"] = {
            "description": "Refused",
            "content": {
                "application/json": {
                    "schema": {"type": "object", "properties": {"error": {"type": "string"}}}
                }
            },
        }
        paths.setdefault(api.settings.base_path + e.path, {})[e.method.lower()] = op
    schemas = {
        m.name: {
            "type": "object",
            "properties": {k: schema_of(v[0], api.models) for k, v in m.fields.items()},
        }
        | (
            {"required": [k for k, v in m.fields.items() if v[1]]}
            if any(v[1] for v in m.fields.values())
            else {}
        )
        for m in api.models.values()
    }
    return {
        "openapi": "3.0.3",
        "info": {"title": api.settings.name, "version": "1.0.0", "description": api.settings.description},
        "servers": [{"url": "/"}],
        "paths": paths,
        "components": {"schemas": schemas},
    }


# ===== the scaffold =====


def scaffold(name: str) -> str:
    """API.py as New project writes it: the header, and one example endpoint left commented."""
    settings = Settings(name=f"{name} API" if name else Settings.name)
    return (
        "\n".join(header_block(settings))
        + '''
"""The project's local sandbox API: endpoints over the project's sandbox, for its app and anything
else on this computer. Run it from the APIs page (Local sandbox APIs); Export makes it a FastAPI,
Azure Functions or AWS Lambda project that uses the real connections.

connection("<name>") is the adapter's calls on that connection: read(table, columns=, filters=,
sort=, limit=), query(sql, params) in its own SQL, write(table, rows, key, mode), tables(). Here
they read and write the sandbox's tables read from it (Add to sandbox first: a grid's Table row),
never the real connection; an export runs the same code against the real one.
"""

from typing import TypedDict

from sab_api import ApiError, connection, endpoint, records

# ===== an example (uncomment it once the sandbox has an orders table) =====
#
# class Order(TypedDict):
#     order_id: int
#     region: str
#     amount: float
#
#
# @endpoint("GET", "/orders/{region}")
# def orders_in(region: str, limit: int = 100) -> list[Order]:
#     """The orders of one region."""
#     db = connection("Sandbox")
#     return records(db.read("orders", filters=[["region", "=", region]], limit=limit))

__all__ = ["ApiError", "TypedDict", "connection", "endpoint", "records"]
'''
    )


_INTEGERS = frozenset(
    ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT")
)


def model_types(columns: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """A table's columns' DuckDB types as Python annotations (a model's fields)."""
    out = {}
    for c in columns:
        t = str(c.get("type") or "").upper()
        py = (
            "int" if t in _INTEGERS
            else "float" if t in ("DOUBLE", "FLOAT", "REAL") or t.startswith("DECIMAL")
            else "bool" if t == "BOOLEAN"
            else "date" if t == "DATE"
            else "datetime" if t.startswith("TIMESTAMP")
            else "str"
        )  # fmt: skip
        out[str(c["name"])] = py
    return out


# ===== the hosting process's environment =====

# What a local sandbox API's process keeps of the server's environment: the system's own, nothing else.
KEPT_VARIABLES = (
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL", "TZ", "SYSTEMDRIVE",
)  # fmt: skip


def runner_env(server: Mapping[str, str], values: Mapping[str, str], home: str) -> dict[str, str]:
    """The process's environment made from nothing: the system's few, an empty home and state folder of its
    own (no library, keyring folder or connection file to find), and its SAB_ values. Never a connection's
    variable, a secret or the server's token."""
    env = {k: server[k] for k in KEPT_VARIABLES if k in server}
    env |= {
        "HOME": home,
        "USERPROFILE": home,
        "TEMP": home,
        "TMP": home,
        "TMPDIR": home,
        "SWISSARMYBENCH_STATE": home,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return env | {str(k): str(v) for k, v in values.items()}


# ===== Payload shapes: what a widget using an endpoint expects, beside what the endpoint answers =====

# Each API widget's expectation: the methods it calls, and what it needs of the answer or the body.
WIDGET_NEEDS: dict[str, dict[str, Any]] = {
    "api_table": {
        "methods": ("GET",),
        "answer": "list",
        "words": "a list of rows (limit and offset pages it)",
    },
    "api_metric": {"methods": ("GET",), "answer": "field", "words": "an object (or rows) with its field"},
    "api_form": {
        "methods": ("POST", "PUT", "PATCH"),
        "answer": "body",
        "words": "a body of the form's fields",
    },
    "api_button": {"methods": METHODS, "answer": "any", "words": "any answer"},
}


def _model_of(kind: str, models: Mapping[str, Model]) -> Model | None:
    bare = re.sub(r"^(?:list|List|Sequence|Optional)\[(.*)\]$", r"\1", kind.strip()).replace(" | None", "")
    return models.get(bare)


def shapes(api: Api, uses: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each use (a canvas widget instance naming an endpoint): what its widget expects, what the endpoint
    answers (its schema, its model's fields and types), and each mismatch in one sentence, before Play."""
    by = {f"{e.method} {e.path}": e for e in api.endpoints}
    out = []
    for use in uses:
        if use.get("action") is not None:
            out.append(_event_shape(api, by, use))
            continue
        values = dict(use.get("values") or {})
        wanted = str(values.get("endpoint") or "")
        widget = str(use.get("widget") or "")
        needs = WIDGET_NEEDS.get(widget, {"methods": METHODS, "answer": "any", "words": "an answer"})
        found = by.get(wanted)
        problems: list[str] = []
        answers: dict[str, Any] = {}
        if found is None:
            problems.append(f"API.py has no endpoint {wanted}.")
        else:
            schema = schema_of(found.returns, api.models)
            model = _model_of(found.returns, api.models)
            answers = {
                "schema": schema,
                "fields": {k: v[0] for k, v in model.fields.items()} if model else {},
            }
            if found.method not in needs["methods"]:
                problems.append(f"{widget} calls {'/'.join(needs['methods'])}; {wanted} is a {found.method}.")
            if needs["answer"] == "list" and schema.get("type") != "array":
                problems.append(
                    f"{widget} shows a list of rows; {found.name} answers {found.returns or 'nothing typed'}."
                )
            if needs["answer"] == "list" and not {"limit", "offset"} <= {p.name for p in found.params}:
                problems.append(
                    f"{found.name} takes no limit and offset: {widget} shows its first page only."
                )
            field = str(values.get("field") or "")
            if needs["answer"] == "field" and field and model is not None and field not in model.fields:
                problems.append(
                    f"{found.name}'s answer has no field {field} (it has {', '.join(model.fields)})."
                )
            if needs["answer"] == "body":
                body = body_of(found)
                body_model_ = body_model(found, api.models)
                asked = [str(f) for f in values.get("fields") or []]
                if body is None:
                    problems.append(f"{found.name} takes no body for {widget} to send.")
                elif body_model_ is not None:
                    answers["body"] = {k: v[0] for k, v in body_model_.fields.items()}
                    extra = [f for f in asked if f not in body_model_.fields]
                    if extra:
                        problems.append(f"{found.name}'s body has no field {extra[0]}.")
            missing = [
                n for n in re.findall(r"\{(\w+)\}", wanted) if n not in (values.get("path_values") or {})
            ]
            if missing:
                problems.append(f"{widget} gives no {missing[0]} for the path (path_values).")
        out.append(
            {"canvas": use.get("canvas"), "page": use.get("page"), "instance": use.get("instance"),
             "widget": widget,
             "endpoint": wanted, "expects": needs["words"], "answers": answers, "problems": problems}
        )  # fmt: skip
    return out


def _event_shape(api: Api, by: Mapping[str, Endpoint], use: Mapping[str, Any]) -> dict[str, Any]:
    """A widget's Event wired to call an endpoint (the Canvas's Events): the call beside the endpoint's own
    definition: the endpoint is API.py's, each mapped field is one of its body's, each required field and
    each {name} of its path is given."""
    action = dict(use.get("action") or {})
    wanted = str(action.get("endpoint") or "")
    widget = str(use.get("widget") or "")
    event = str(use.get("event") or "")
    found = by.get(wanted)
    problems: list[str] = []
    answers: dict[str, Any] = {}
    sent = action.get("body") or ""
    if found is None:
        problems.append(f"API.py has no endpoint {wanted}.")
    else:
        fields = body_fields(found, api.models)
        if fields is not None:
            answers["body"] = {k: v["type"] for k, v in fields.items()}
        if body_of(found) is None and sent:
            problems.append(f"{found.name} takes no body: {event} sends one.")
        elif isinstance(sent, dict) and fields is not None:
            extra = [f for f in sent if f not in fields]
            if extra:
                problems.append(f"{found.name}'s body has no field {extra[0]}.")
            unsent = [f for f, v in fields.items() if v["required"] and f not in sent]
            if unsent:
                problems.append(f"{found.name}'s body needs {unsent[0]}: {event} does not send it.")
        given = action.get("params") or {}
        missing = [n for n in re.findall(r"\{(\w+)\}", wanted) if n not in given]
        if missing:
            problems.append(f"{event} gives no {missing[0]} for the path.")
    return {
        "canvas": use.get("canvas"),
        "page": use.get("page"),
        "instance": use.get("instance"),
        "widget": widget,
        "event": event,
        "endpoint": wanted,
        "expects": f"on {event}: "
        + ("the whole payload as the body" if isinstance(sent, str) else "a field each"),
        "answers": answers,
        "problems": problems,
    }


# ===== API.py's own problems in its editor (the owner approved the critic's proposal 8, 2026-11-21) =====


def is_api_file(path: Any) -> bool:
    """A document is a project's API.py (its name, any folder)."""
    return isinstance(path, str) and re.split(r"[\\/]", path)[-1] == FILE


def editor_problems(
    text: str, mocks: Mapping[str, tuple[str, list[str]]] | None = None
) -> list[dict[str, Any]]:
    """What the APIs page says of API.py, as the editor's squiggles: {line, message}. Its own rules (a path
    with no parameter, two endpoints on one path, ...); with the sandbox's mocks ({name: (dialect, tables)}):
    a connection with no table in the sandbox yet, and each SQL string the mock would refuse (checked by the
    mock's own rule, never run). Python's own syntax errors are the editor's lint's, not repeated here."""
    from swissarmybench.domain import sandbox_dialects as dialects  # the mock's rule, imported when asked
    from swissarmybench.domain.sandbox import SandboxError

    api = parse(text)
    if not api.endpoints and any(p["message"].startswith("Python could not read it") for p in api.problems):
        return []
    out = [{"line": int(p.get("line") or 1), "message": str(p["message"])} for p in api.problems]
    if mocks is None:
        return out
    known = {k.casefold(): v for k, v in mocks.items()}
    lines = text.splitlines()
    for e in api.endpoints:
        for name in e.connections:
            if name.casefold() in known:
                continue
            at = next(
                (
                    i + 1
                    for i in range(e.line - 1, min(e.end, len(lines)))
                    if f"connection({name!r}" in lines[i].replace('"', "'")
                ),
                e.line,
            )
            out.append(
                {
                    "line": at,
                    "message": f"The sandbox has no table read from {name} yet: Add to sandbox one of its "
                    "tables.",
                }
            )
        mine = [known[n.casefold()] for n in e.connections if n.casefold() in known]
        if len(mine) != 1:
            continue  # which mock sends it is not known here
        dialect, tables = mine[0]
        for sql in e.sql:
            try:
                dialects.to_duckdb(sql.get("text"), dialect, None, tables)
            except SandboxError as error:
                said = str(error)
                if "has no value" in said:
                    continue  # its values come at run time
                found = re.match(r"Line (\d+): (.*)$", said, re.S)
                line = int(sql.get("line") or e.line) + (int(found.group(1)) - 1 if found else 0)
                words = found.group(2) if found else said
                out.append({"line": line, "message": words[:1].upper() + words[1:]})
    return sorted(out, key=lambda p: p["line"])
