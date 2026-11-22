"""sab_api: what a project's API.py imports, the same file wherever it runs.

    from sab_api import connection, endpoint, records

    @endpoint("GET", "/orders/{region}")
    def orders_in(region: str, limit: int = 100) -> list[Order]:
        warehouse = connection("Warehouse")
        with warehouse.cursor() as cursor:
            cursor.execute("SELECT TOP (?) * FROM dbo.orders WHERE region = ?", limit, region)
            return records(cursor)

  endpoint(method, path)  registers the function: a path's {names} are its parameters of those names; a
  parameter
                          typed with a TypedDict, a dataclass, dict or list is the JSON body; the others are
                          the
                          query's (str, int, float, bool, date, datetime; a default makes one optional)
  connection(name)        the connection's client. Here in Swiss Army Bench (the local sandbox API): a mock
  with
                          the real client's shape over the project's sandbox, never the connection itself. In
                          an
                          export: the connection's own portable code (its variables set where it runs)
  records(cursor)         a DB-API cursor's rows as dicts by its description
  ApiError(status, msg)   an answer with that status and {"error": msg}
  The body is checked against its model before the endpoint runs (a TypedDict's or a dataclass's fields,
  nested ones and lists of them): a wrong type, a missing required field or an unknown one is a 422 naming
  the field ({"error": "order.amount is a number, not '12'.", "field": "order.amount"}).
  handle(method, path, query, body)  one request: (status, headers, body bytes): what every target calls

Standard library only: this file is copied as sab_api.py into each exported project.
"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import inspect
import json
import re
import typing
import uuid
from collections.abc import Callable, Mapping
from typing import Any

__all__ = ["ENDPOINTS", "ApiError", "Endpoint", "connection", "endpoint", "handle", "records", "use_clients"]

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
BASE_PATH = ""  # the API's base path (its header's base_path), set by the target that runs it
# Told an endpoint's own failure (a 500) before it is answered: the local host notes its API.py line for
# Try it and the request log. None in an export: the answer is the same either way.
on_failure: Callable[[BaseException], None] | None = None
_KINDS = {
    "int": "a whole number",
    "float": "a number",
    "bool": "true or false",
    "date": "a date (2026-01-15)",
    "datetime": "a date and time (2026-01-15T09:30:00)",
    "Decimal": "a number",
}


class ApiError(Exception):
    """Raise ApiError(404, "No order 7.") for an answer with that status (`field`: the body's field it is
    about, as order.lines[0].quantity)."""

    def __init__(self, status: int, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.status = int(status)
        self.message = message
        self.field = field


@dataclasses.dataclass
class Endpoint:
    method: str
    path: str
    fn: Callable[..., Any]
    name: str
    summary: str
    status: int
    pattern: re.Pattern[str]
    names: tuple[str, ...]


ENDPOINTS: list[Endpoint] = []


def _pattern(path: str) -> tuple[re.Pattern[str], tuple[str, ...]]:
    names = tuple(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", path))
    regex = re.sub(
        r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
        r"(?P<\1>[^/]+)",
        re.escape(path).replace(r"\{", "{").replace(r"\}", "}"),
    )
    return re.compile("^" + regex + "/?$"), names


def endpoint(method: str, path: str, *, summary: str = "", status: int = 200) -> Callable[[Any], Any]:
    verb = str(method).upper()
    if verb not in METHODS:
        raise ValueError(f"An endpoint's method is one of {', '.join(METHODS)}, not {method!r}.")
    if not str(path).startswith("/"):
        raise ValueError(f"An endpoint's path starts with /: {path!r}.")

    def register(fn: Callable[..., Any]) -> Callable[..., Any]:
        pattern, names = _pattern(path)
        said = summary or (inspect.getdoc(fn) or "").split("\n")[0]
        ENDPOINTS.append(Endpoint(verb, path, fn, fn.__name__, said, status, pattern, names))
        return fn

    return register


_clients: Callable[[str], Any] | None = None


def use_clients(make: Callable[[str], Any]) -> None:
    """What connection(name) gives: set once by whatever runs this API (the sandbox's mocks, or an export's
    connections.py)."""
    global _clients
    _clients = make


def connection(name: str) -> Any:
    """The connection's client (see use_clients)."""
    if _clients is None:
        raise RuntimeError(
            f"No client for {name}: run this API with Swiss Army Bench or an exported project."
        )
    return _clients(name)


def records(cursor: Any) -> list[dict[str, Any]]:
    """A DB-API cursor's rows as dicts, by its description's names."""
    names = [d[0] for d in cursor.description or []]
    return [dict(zip(names, row, strict=False)) for row in cursor.fetchall()]


# ===== values in and out =====


def _hints(fn: Callable[..., Any]) -> dict[str, Any]:
    try:
        return typing.get_type_hints(fn)
    except Exception:  # an annotation that does not resolve: read as given
        return dict(getattr(fn, "__annotations__", {}))


def _marked(fn: Callable[..., Any]) -> dict[str, Any]:
    """The function's annotations with their extras (Annotated[pa.Table, Order] kept whole)."""
    try:
        return typing.get_type_hints(fn, include_extras=True)
    except Exception:
        return dict(getattr(fn, "__annotations__", {}))


def _rows_model(kind: Any) -> Any:
    """The model of a body the adapter makes Arrow (`Annotated[pa.Table, Order]`: Order); None for another."""
    if typing.get_origin(kind) is not typing.Annotated:
        return None
    args = typing.get_args(kind)
    table = args[0]
    if getattr(table, "__name__", "") == "Table" and str(getattr(table, "__module__", "")).startswith(
        "pyarrow"
    ):
        return args[1] if len(args) > 1 else None
    return None


_DUCK = {str: "VARCHAR", int: "BIGINT", float: "DOUBLE", bool: "BOOLEAN", datetime.date: "DATE",
         datetime.datetime: "TIMESTAMP", decimal.Decimal: "DOUBLE"}  # fmt: skip


def _adapter() -> Any:
    """sab_adapter, beside this file (the app's host gives it; an export copies it); None without it."""
    import importlib

    try:
        return importlib.import_module("sab_adapter")
    except ImportError:
        return None


def _arrow_body(value: Any, model: Any, at: str) -> Any:
    """A body of records checked against `model` (a 422 naming the field), then made an Arrow table by the
    adapter's from_json with the model's types (strict: a value not of its type is refused)."""
    rows = checked(value, list[model], at)
    adapter = _adapter()
    if adapter is None:
        raise ApiError(500, "A table body needs sab_adapter.py beside sab_api.py.")
    fields, _ = _model_fields(model)
    columns = {}
    for name, kind in fields.items():
        inner = [a for a in typing.get_args(kind) if a is not type(None)] or [kind]
        columns[name] = _DUCK.get(inner[0], "VARCHAR")
    try:
        return adapter.from_json([plain(rows)], columns, strict=True).read_all()
    except ValueError as error:
        raise ApiError(422, f"{at}: {error}") from None


def _is_body(kind: Any) -> bool:
    origin = typing.get_origin(kind)
    if origin is typing.Union or str(origin) == "types.UnionType":
        args = [a for a in typing.get_args(kind) if a is not type(None)]
        return bool(args) and _is_body(args[0])
    if origin in (list, dict) or kind in (list, dict):
        return True
    return dataclasses.is_dataclass(kind) or typing.is_typeddict(kind)


def _convert(value: Any, kind: Any, name: str) -> Any:
    if value is None or kind in (inspect.Parameter.empty, Any, str):
        return value
    origin = typing.get_origin(kind)
    if origin is typing.Union or str(origin) == "types.UnionType":
        args = [a for a in typing.get_args(kind) if a is not type(None)]
        return _convert(value, args[0], name) if args else value
    try:
        if kind is bool:
            if isinstance(value, bool):
                return value
            low = str(value).strip().lower()
            if low in ("true", "1", "yes", "on"):
                return True
            if low in ("false", "0", "no", "off"):
                return False
            raise ValueError(value)
        if kind is int:
            return int(value)
        if kind is float:
            return float(value)
        if kind is decimal.Decimal:
            return decimal.Decimal(str(value))
        if kind is datetime.date:
            return datetime.date.fromisoformat(str(value)[:10])
        if kind is datetime.datetime:
            return datetime.datetime.fromisoformat(str(value))
    except ApiError:
        raise
    except (TypeError, ValueError, ArithmeticError):
        wanted = getattr(kind, "__name__", str(kind))
        raise ApiError(422, f"{name} is not {_KINDS.get(wanted, 'a ' + wanted)}: {value!r}.") from None
    return value


# ===== the body checked against its model (the owner approved, 2026-11-21) =====

_JSON_WORDS = {
    "str": "text",
    "int": "a whole number",
    "float": "a number",
    "Decimal": "a number",
    "bool": "true or false",
    "date": "a date (2026-01-15)",
    "datetime": "a date and time (2026-01-15T09:30:00)",
}


def _wrong(at: str, kind: Any, value: Any) -> ApiError:
    words = _JSON_WORDS.get(getattr(kind, "__name__", ""), getattr(kind, "__name__", str(kind)))
    return ApiError(422, f"{at} is {words}, not {value!r}.", at)


def _number(value: Any) -> float | None:
    """A JSON number, or text that reads as one (a form's box sends text); None for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            found = float(value.strip())
        except ValueError:
            return None
        return found if found == found and abs(found) != float("inf") else None
    return None


def _model_fields(kind: Any) -> tuple[dict[str, Any], set[str]]:
    """A TypedDict's or a dataclass's fields (name -> type) and the required ones."""
    if typing.is_typeddict(kind):
        try:  # with the extras: NotRequired and Required are read even from postponed annotations
            marked = typing.get_type_hints(kind, include_extras=True)
        except Exception:
            marked = dict(getattr(kind, "__annotations__", {}))
        total = bool(getattr(kind, "__total__", True))
        fields: dict[str, Any] = {}
        required: set[str] = set()
        for name, kind_of in marked.items():
            origin = typing.get_origin(kind_of)
            if origin is typing.Annotated:
                kind_of = typing.get_args(kind_of)[0]
                origin = typing.get_origin(kind_of)
            if origin in (typing.Required, typing.NotRequired):
                if origin is typing.Required:
                    required.add(name)
                kind_of = typing.get_args(kind_of)[0]
            elif total:
                required.add(name)
            fields[name] = kind_of
        return fields, required
    hints = _hints(kind)
    required = {
        f.name
        for f in dataclasses.fields(kind)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    return {f.name: hints.get(f.name, f.type) for f in dataclasses.fields(kind)}, required


def checked(value: Any, kind: Any, at: str) -> Any:
    """`value` (as JSON gave it) checked against `kind`: as sent, a dataclass made from it; ApiError(422)
    naming the field where it does not fit."""
    if kind in (inspect.Parameter.empty, Any, object) or isinstance(kind, (str, typing.TypeVar)):
        return value
    origin = typing.get_origin(kind)
    if origin is typing.Union or str(origin) == "types.UnionType":
        args = [a for a in typing.get_args(kind) if a is not type(None)]
        if value is None and len(args) < len(typing.get_args(kind)):
            return None
        return checked(value, args[0], at) if args else value
    if origin in (typing.Required, typing.NotRequired):  # an annotation get_type_hints kept
        return checked(value, typing.get_args(kind)[0], at)
    if origin is list or kind is list:
        if not isinstance(value, list):
            raise ApiError(422, f"{at} is a list (JSON [...]), not {value!r:.40}.", at)
        inner = typing.get_args(kind)
        return [checked(v, inner[0], f"{at}[{i}]") for i, v in enumerate(value)] if inner else value
    if origin is dict or kind is dict:
        if not isinstance(value, Mapping):
            raise ApiError(422, f"{at} is a JSON object, not {value!r:.40}.", at)
        return value
    if typing.is_typeddict(kind) or dataclasses.is_dataclass(kind):
        fields, required = _model_fields(kind)
        if not isinstance(value, Mapping):
            names = ", ".join(fields)
            raise ApiError(422, f"{at} is a JSON object of {names}, not {value!r:.40}.", at)
        extra = [k for k in value if k not in fields]
        if extra:
            raise ApiError(
                422, f"{at} has no field {extra[0]!r} (it has: {', '.join(fields)}).", f"{at}.{extra[0]}"
            )
        missing = [k for k in fields if k in required and k not in value]
        if missing:
            raise ApiError(422, f"{at}.{missing[0]} is required.", f"{at}.{missing[0]}")
        given = {k: checked(v, fields[k], f"{at}.{k}") for k, v in value.items()}
        if dataclasses.is_dataclass(kind):
            return kind(**given)  # type: ignore[operator]
        return given
    if kind is bool:
        if not isinstance(value, bool):
            raise _wrong(at, kind, value)
        return value
    if kind is int:  # as FastAPI's own takes it: 3, 3.0 and "3", never True or 3.5
        number = _number(value)
        if number is None or number != int(number):
            raise _wrong(at, kind, value)
        return int(number)
    if kind in (float, decimal.Decimal):  # 12, 12.5 and "12.5"
        number = _number(value)
        if number is None:
            raise _wrong(at, kind, value)
        return value if isinstance(value, (int, float)) else float(number)
    if kind is str:
        if not isinstance(value, str):
            raise _wrong(at, kind, value)
        return value
    if kind in (datetime.date, datetime.datetime):
        try:
            if not isinstance(value, str):
                raise ValueError(value)
            kind.fromisoformat(value)
        except ValueError:
            raise _wrong(at, kind, value) from None
        return value
    return value


def plain(value: Any) -> Any:
    """A result as JSON carries it: dataclasses as dicts, dates as ISO text, decimals as numbers, an Arrow
    table or a DataFrame as its records."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return plain(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain(v) for v in value]
    to_pylist = getattr(value, "to_pylist", None)  # an Arrow table
    if callable(to_pylist):
        return plain(to_pylist())
    to_dict = getattr(value, "to_dict", None)  # a DataFrame
    if callable(to_dict):
        try:
            return plain(to_dict(orient="records"))
        except TypeError:
            pass
    return str(value)


def describe() -> list[dict[str, Any]]:
    """Each endpoint: its method, path, function, summary, its path's and query's parameters and its body's
    fields (a TypedDict's or a dataclass's, with their types' names): an API form widget's fields."""
    out = []
    for e in ENDPOINTS:
        hints = _hints(e.fn)
        params: list[dict[str, Any]] = []
        body: dict[str, str] = {}
        for p in inspect.signature(e.fn).parameters.values():
            kind = hints.get(p.name, p.annotation)
            model = _rows_model(_marked(e.fn).get(p.name))
            if model is not None:  # a table body: sent as a list of its model
                kind = list[model]  # type: ignore[valid-type]
            if p.name in e.names:
                params.append({"name": p.name, "in": "path"})
            elif _is_body(kind):
                inner = typing.get_args(kind)[0] if typing.get_origin(kind) is list else kind
                if typing.is_typeddict(inner) or dataclasses.is_dataclass(inner):
                    body = {k: getattr(v, "__name__", str(v)) for k, v in _hints(inner).items()}
            else:
                params.append(
                    {
                        "name": p.name,
                        "in": "query",
                        "default": None if p.default is inspect.Parameter.empty else p.default,
                    }
                )
        out.append(
            {
                "method": e.method,
                "path": e.path,
                "name": e.name,
                "summary": e.summary,
                "params": params,
                "body": body,
            }
        )
    return out


# ===== one request =====


def find(method: str, path: str) -> tuple[Endpoint | None, dict[str, str], bool]:
    """The endpoint for a request (and its path's values), and whether the path is known for another
    method."""
    path = path or "/"
    if BASE_PATH and path.startswith(BASE_PATH.rstrip("/") + "/"):
        path = path[len(BASE_PATH.rstrip("/")) :]
    other = False
    for e in ENDPOINTS:
        m = e.pattern.match(path)
        if m:
            if e.method == method.upper():
                return e, m.groupdict(), False
            other = True
    return None, {}, other


def call(e: Endpoint, path_values: Mapping[str, str], query: Mapping[str, Any], body: Any) -> Any:
    """The endpoint's function called with its parameters from the path, the query and the body."""
    hints = _hints(e.fn)
    marked = _marked(e.fn)
    given: dict[str, Any] = {}
    for p in inspect.signature(e.fn).parameters.values():
        kind = hints.get(p.name, p.annotation)
        model = _rows_model(marked.get(p.name))
        if p.name in path_values:
            given[p.name] = _convert(path_values[p.name], kind, p.name)
        elif model is not None:
            if body is None:
                if p.default is inspect.Parameter.empty:
                    raise ApiError(422, f"{p.name} is the request's JSON body: send one.")
                continue
            given[p.name] = _arrow_body(body, model, p.name)
        elif _is_body(kind):
            if body is None:
                if p.default is inspect.Parameter.empty:
                    raise ApiError(422, f"{p.name} is the request's JSON body: send one.")
                continue
            given[p.name] = checked(body, kind, p.name)
        elif p.name in query:
            given[p.name] = _convert(query[p.name], kind, p.name)
        elif p.default is inspect.Parameter.empty:
            raise ApiError(422, f"{p.name} is required (?{p.name}=...).")
    return e.fn(**given)


ARROW = "application/vnd.apache.arrow.stream"


def answered(status: int, result: Any, accept: str = "") -> tuple[int, dict[str, str], bytes]:
    """An endpoint's result as its answer: Arrow (a table or a reader) through the adapter, as JSON records
    or, when the caller accepts it (a widget), an Arrow IPC stream; anything else as JSON (plain)."""
    adapter = _adapter()
    if adapter is not None and adapter.is_arrow(result):
        if ARROW in accept:
            return status, {"Content-Type": ARROW}, adapter.to_ipc(result)
        return status, {"Content-Type": "application/json"}, b"".join(adapter.to_json(result))
    return status, {"Content-Type": "application/json"}, json.dumps(plain(result)).encode()


def handle(
    method: str,
    path: str,
    query: Mapping[str, Any] | None = None,
    body: bytes | str | None = None,
    accept: str = "",
) -> tuple[int, dict[str, str], bytes]:
    """One request through the API: its status, headers and JSON body (an Arrow table's rows through the
    adapter; an Arrow IPC stream when `accept` asks for one). A refusal is {"error": words}."""
    headers = {"Content-Type": "application/json"}
    e, values, other = find(method, path)
    if e is None:
        status = 405 if other else 404
        said = "That path takes another method." if other else f"No endpoint answers {method} {path}."
        return status, headers, json.dumps({"error": said}).encode()
    parsed: Any = None
    if body:
        try:
            parsed = json.loads(body)
        except ValueError:
            return 400, headers, json.dumps({"error": "The body is not JSON."}).encode()
    try:
        result = call(e, values, dict(query or {}), parsed)
    except ApiError as error:
        refused: dict[str, Any] = {"error": error.message}
        if error.field:
            refused["field"] = error.field
        return error.status, headers, json.dumps(refused).encode()
    except Exception as error:  # the endpoint's own failure, in its words
        if on_failure is not None:
            on_failure(error)
        return 500, headers, json.dumps({"error": f"{type(error).__name__}: {error}"}).encode()
    if result is None and e.method == "DELETE":
        return 204, {}, b""
    return answered(e.status, result, accept)
