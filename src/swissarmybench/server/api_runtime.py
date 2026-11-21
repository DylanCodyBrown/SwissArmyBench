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


class ApiError(Exception):
    """Raise ApiError(404, "No order 7.") for an answer with that status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = int(status)
        self.message = message


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
        if dataclasses.is_dataclass(kind) and isinstance(value, Mapping):
            fields = {f.name for f in dataclasses.fields(kind)}
            extra = [k for k in value if k not in fields]
            if extra:
                raise ApiError(422, f"{name} has no field {extra[0]!r}.")
            return kind(**value)  # type: ignore[operator]
    except ApiError:
        raise
    except (TypeError, ValueError, ArithmeticError):
        raise ApiError(422, f"{name} is not a {getattr(kind, '__name__', kind)}: {value!r}.") from None
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
    given: dict[str, Any] = {}
    for p in inspect.signature(e.fn).parameters.values():
        kind = hints.get(p.name, p.annotation)
        if p.name in path_values:
            given[p.name] = _convert(path_values[p.name], kind, p.name)
        elif _is_body(kind):
            if body is None:
                if p.default is inspect.Parameter.empty:
                    raise ApiError(422, f"{p.name} is the request's JSON body: send one.")
                continue
            given[p.name] = _convert(body, kind, p.name)
        elif p.name in query:
            given[p.name] = _convert(query[p.name], kind, p.name)
        elif p.default is inspect.Parameter.empty:
            raise ApiError(422, f"{p.name} is required (?{p.name}=...).")
    return e.fn(**given)


def handle(
    method: str, path: str, query: Mapping[str, Any] | None = None, body: bytes | str | None = None
) -> tuple[int, dict[str, str], bytes]:
    """One request through the API: its status, headers and JSON body. A refusal is {"error": words}."""
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
        return error.status, headers, json.dumps({"error": error.message}).encode()
    except Exception as error:  # the endpoint's own failure, in its words
        return 500, headers, json.dumps({"error": f"{type(error).__name__}: {error}"}).encode()
    if result is None and e.method == "DELETE":
        return 204, {}, b""
    return e.status, headers, json.dumps(plain(result)).encode()
