"""Add API (docs/ideas.md, "Add API", the owner 2026-11-15): an OpenAPI document (2.0 or 3.x) or a short
form, made into `API_<name>.py` (a ready-to-call client) and a "Python (your own code)" connection.

The owner: "if we could create a connection type that literally turns an openapi json into a ready to
call connection type it would be a power feature."

This file is the rules (domain/api_clients.py writes the file itself):

  spec         an OpenAPI document read into operations: method, path, parameters (path, query, header,
               cookie), the body, the answer (a table or not, and where the rows are in it, and their
               columns), its tag; its servers and the security scheme that picks the auth type
  form         a base URL, an auth type and any number of endpoints, read into the same spec
  auth         the auth types, each one's settings and the environment variables it reads (a secret is
               only ever read from one: the file and the connection hold its name, never its value)
  presets      Azure Function App, AWS Lambda, Google (Firebase, Cloud Functions, Cloud Run): the form
               filled in, and where the host keeps its OpenAPI document
  names        the module (API_Orders), the class (OrdersApi), the variables' prefix (ORDERS)
  connection   its three boxes: Connect imports the client, List the tables lists the GET operations
               that return a table, Read a table calls one with the limit
  changes      what re-importing would change in the made file, said before it is written

Standard library only; no I/O.
"""

from __future__ import annotations

import json
import keyword
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

MAX_OPERATIONS: int = 500
MAX_PARAMETERS: int = 60
MAX_SPEC_CHARS: int = 10_000_000
MAX_COLUMNS: int = 500
METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
PLACES: tuple[str, ...] = ("path", "query", "header", "cookie")
# A wrapped table's rows: {"value": [...], "nextLink": ...} (Microsoft's), {"items": [...]}, {"data": [...]}.
ROW_KEYS: tuple[str, ...] = ("value", "items", "data", "results", "records", "rows", "entries", "list")
# A query parameter that takes the next page's token, and one that counts the page or the offset.
TOKEN_PARAMETERS: tuple[str, ...] = (
    "pagetoken",
    "page_token",
    "nexttoken",
    "next_token",
    "cursor",
    "continuationtoken",
    "continuation_token",
    "after",
    "starting_after",
)
PAGE_PARAMETERS: tuple[str, ...] = ("page", "pagenumber", "page_number")
OFFSET_PARAMETERS: tuple[str, ...] = ("offset", "skip", "$skip", "start")
# The client's own names: no operation or argument takes them.
RESERVED: frozenset[str] = frozenset(
    {"self", "body", "max_rows", "tables", "read", "base_url", "timeout", "retries", "backoff", "max_pages"}
)
_WORD = re.compile(r"[A-Za-z0-9]+")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,128}$")


class ApiError(ValueError):
    """The spec, the form or the auth cannot be used as given. The message says why in plain words."""


# ===== the model =====


@dataclass(frozen=True)
class Parameter:
    name: str  # as the API names it
    place: str  # path, query, header or cookie
    required: bool
    type: str  # string, integer, number, boolean, array, object
    description: str = ""
    python: str = ""  # its name as the method's argument (given when the spec is read)
    enum: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "in": self.place,
            "required": self.required,
            "type": self.type,
            "description": self.description,
            "python": self.python,
        }


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    name: str  # the client's method (list_orders)
    summary: str = ""
    description: str = ""
    parameters: tuple[Parameter, ...] = ()
    body: str = ""  # "json", "form" or "" (none)
    body_required: bool = False
    body_description: str = ""
    table: bool = False  # the answer is rows
    rows_at: str = ""  # where the rows are in the answer: "" (the answer is the list) or a key
    columns: tuple[tuple[str, str], ...] = ()  # (column, type) of a row, when the spec says
    tag: str = ""
    deprecated: bool = False
    returns: str = ""  # what a non-table answer is, in a word (object, string, nothing)

    @property
    def readable(self) -> bool:
        """A table the connection lists: a GET that returns rows and needs nothing to be called."""
        needed = any(p.required for p in self.parameters) or self.body_required
        return self.method == "GET" and self.table and not needed

    def paging(self) -> dict[str, str]:
        """How its pages are asked for, by its query parameters: a token, a page number or an offset.
        A next link (in the answer or its Link header) is followed whatever it says."""
        if not self.table:
            return {}
        for p in self.parameters:
            if p.place == "query" and p.name.lower() in TOKEN_PARAMETERS:
                return {"token": p.name}
        for p in self.parameters:
            if p.place == "query" and p.name.lower() in PAGE_PARAMETERS:
                return {"page": p.name}
        for p in self.parameters:
            if p.place == "query" and p.name.lower() in OFFSET_PARAMETERS:
                return {"offset": p.name}
        return {}

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "summary": self.summary,
            "parameters": [p.to_json() for p in self.parameters],
            "body": self.body or None,
            "table": self.table,
            "readable": self.readable,
            "columns": [{"column": c, "type": t} for c, t in self.columns],
            "tag": self.tag,
        }


@dataclass(frozen=True)
class Auth:
    type: str = "none"
    settings: Mapping[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str:
        return str(self.settings.get(name, AUTH_TYPES[self.type].default(name)))

    def to_json(self) -> dict[str, Any]:
        return {"type": self.type, **dict(self.settings)}


@dataclass(frozen=True)
class Spec:
    title: str
    version: str  # the API's own version
    source: str  # "OpenAPI 3.0.3", "Swagger 2.0" or "form"
    base_url: str
    description: str
    operations: tuple[Operation, ...]
    auth: Auth
    # The schemes the document declares, by name, as auths (a form has none): the dialog offers them.
    schemes: tuple[tuple[str, Auth], ...] = ()

    def tables(self) -> dict[str, Operation]:
        """The connection's tables: each readable GET under a short name of its own (its path's words)."""
        found: dict[str, Operation] = {}
        for op in self.operations:
            if op.readable:
                found[_unique(table_name(op), found)] = op
        return found

    def to_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "version": self.version,
            "source": self.source,
            "base_url": self.base_url,
            "operations": [op.to_json() for op in self.operations],
            "tables": [
                {"table": name, "schema": schema_of(op), "operation": op.name}
                for name, op in self.tables().items()
            ],
            "auth": self.auth.to_json(),
            "schemes": [{"name": n, **a.to_json()} for n, a in self.schemes],
        }


def _unique(name: str, taken: Iterable[str]) -> str:
    used = set(taken)
    if name not in used:
        return name
    n = 2
    while f"{name}_{n}" in used:
        n += 1
    return f"{name}_{n}"


def snake(text: str, fallback: str = "value") -> str:
    """A Python name from any words: listOrders -> list_orders, "Order ID" -> order_id."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", spaced)
    words = [w.lower() for w in _WORD.findall(spaced)]
    name = "_".join(words) or fallback
    if name[0].isdigit():
        name = f"n{name}"
    if keyword.iskeyword(name) or keyword.issoftkeyword(name):
        name += "_"
    return name


def table_name(op: Operation) -> str:
    """/orders -> orders; /customers/active -> customers_active; /v1/orders -> orders. Path parameters
    are left out (a readable table has none)."""
    words = [
        part
        for part in op.path.strip("/").split("/")
        if part and not part.startswith("{") and not re.fullmatch(r"v\d+|api", part, re.IGNORECASE)
    ]
    return snake("_".join(words), snake(op.name, "table")) if words else snake(op.name, "table")


def schema_of(op: Operation) -> str:
    """A table's schema in the catalog: its first tag, else "api"."""
    return snake(op.tag, "api") if op.tag else "api"


# ===== names =====


@dataclass(frozen=True)
class Names:
    connection: str  # "Orders API": the connection, as the user named it
    module: str  # "API_Orders": the file is API_Orders.py
    cls: str  # "OrdersApi"
    prefix: str  # "ORDERS": its environment variables start with it

    @property
    def file(self) -> str:
        return f"{self.module}.py"

    def to_json(self) -> dict[str, str]:
        return {
            "connection": self.connection,
            "module": self.module,
            "class": self.cls,
            "prefix": self.prefix,
        }


def names_for(title: str) -> Names:
    """The names an API is made under, from its title (or the name the user typed): "Orders API" ->
    API_Orders.py, class OrdersApi, ORDERS_API_KEY."""
    text = " ".join(str(title or "").split())[:64]
    words = _WORD.findall(text)
    if words and words[-1].lower() == "api" and len(words) > 1:
        words = words[:-1]
    if not words:
        raise ApiError("Name the API: letters or digits (Orders).")
    stem = "_".join(words)
    if stem[0].isdigit():
        stem = f"N{stem}"
    camel = "".join(w[:1].upper() + w[1:] for w in words)
    if camel[0].isdigit():
        camel = f"N{camel}"
    return Names(text, f"API_{stem}", f"{camel}Api", re.sub(r"_+", "_", stem.upper()))


# ===== auth types =====


@dataclass(frozen=True)
class Setting:
    id: str
    label: str
    default: str = ""
    choices: tuple[tuple[str, str], ...] = ()  # (value, label)
    when: tuple[str, str] | None = None  # shown only when another setting has this value

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "default": self.default,
            "choices": [{"value": v, "label": label} for v, label in self.choices],
            "when": {"setting": self.when[0], "is": self.when[1]} if self.when else None,
        }


@dataclass(frozen=True)
class Variable:
    """An environment variable the client reads, and the constructor argument it is given as."""

    name: str
    argument: str
    required: bool
    secret: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "argument": self.argument,
            "required": self.required,
            "secret": self.secret,
        }


@dataclass(frozen=True)
class AuthType:
    id: str
    label: str
    settings: tuple[Setting, ...] = ()

    def default(self, name: str) -> str:
        return next((s.default for s in self.settings if s.id == name), "")

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "settings": [s.to_json() for s in self.settings]}


_FLOWS = (
    ("client_credentials", "Client credentials"),
    ("authorization_code", "Authorization code (browser, PKCE)"),
    ("device_code", "Device code"),
)
_JWT_MODES = (("token", "A ready token"), ("login", "A login endpoint"), ("signed", "Signed here"))
FIREBASE_SIGN_IN = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
FIREBASE_REFRESH = "https://securetoken.googleapis.com/v1/token"

AUTH_TYPES: dict[str, AuthType] = {
    t.id: t
    for t in (
        AuthType("none", "None"),
        AuthType(
            "api_key",
            "API key",
            (
                Setting(
                    "in", "In", "header", (("header", "Header"), ("query", "Query"), ("cookie", "Cookie"))
                ),
                Setting("name", "Key name", "X-Api-Key"),
            ),
        ),
        AuthType("bearer", "Bearer token"),
        AuthType("basic", "Basic"),
        AuthType(
            "oauth2",
            "OAuth 2.0",
            (
                Setting("flow", "Flow", "client_credentials", _FLOWS),
                Setting("token_url", "Token URL"),
                Setting("authorize_url", "Authorization URL", when=("flow", "authorization_code")),
                Setting("device_url", "Device authorization URL", when=("flow", "device_code")),
                Setting("scopes", "Scopes"),
                Setting("redirect_port", "Redirect port", "0", when=("flow", "authorization_code")),
            ),
        ),
        AuthType(
            "jwt",
            "JWT",
            (
                Setting("mode", "Token", "token", _JWT_MODES),
                Setting("login_url", "Login URL", "/login", when=("mode", "login")),
                Setting("token_field", "Token field", when=("mode", "login")),
                Setting(
                    "algorithm",
                    "Algorithm",
                    "HS256",
                    (("HS256", "HS256"), ("RS256", "RS256"), ("ES256", "ES256")),
                    when=("mode", "signed"),
                ),
                Setting("issuer", "Issuer", when=("mode", "signed")),
                Setting("subject", "Subject", when=("mode", "signed")),
                Setting("audience", "Audience", when=("mode", "signed")),
                Setting("key_id", "Key id", when=("mode", "signed")),
                Setting("lifetime", "Lifetime (seconds)", "3600", when=("mode", "signed")),
            ),
        ),
        AuthType(
            "sigv4",
            "AWS Signature Version 4",
            (
                Setting("region", "Region", "us-east-1"),
                Setting(
                    "service",
                    "Service",
                    "",
                    (
                        ("", "From the address"),
                        ("lambda", "Lambda function URL"),
                        ("execute-api", "API Gateway"),
                    ),
                ),
            ),
        ),
        AuthType("google", "Google identity token", (Setting("audience", "Audience"),)),
        AuthType(
            "firebase",
            "Firebase ID token",
            (
                Setting(
                    "mode",
                    "Token",
                    "password",
                    (("password", "Email and password"), ("token", "A ready token")),
                ),
                Setting("sign_in_url", "Sign-in URL", FIREBASE_SIGN_IN, when=("mode", "password")),
                Setting("refresh_url", "Refresh URL", FIREBASE_REFRESH, when=("mode", "password")),
            ),
        ),
    )
}


def check_auth(value: Any) -> Auth:
    """The auth as sent ({"type": "api_key", "in": "header", "name": "x-functions-key"}), checked: a
    known type, only its own settings, each a short text."""
    if value is None or value == "":
        return Auth()
    if isinstance(value, str):
        value = {"type": value}
    if not isinstance(value, Mapping):
        raise ApiError('The auth is {"type": "api_key", "in": "header", "name": "X-Api-Key"}.')
    kind = value.get("type") or "none"
    if kind not in AUTH_TYPES:
        raise ApiError(f"{kind!r} is not an auth type. Use one of: {', '.join(AUTH_TYPES)}.")
    known = {s.id: s for s in AUTH_TYPES[kind].settings}
    settings: dict[str, str] = {}
    for key, raw in value.items():
        if key == "type" or raw is None:
            continue
        if key not in known:
            raise ApiError(
                f"{AUTH_TYPES[kind].label} has no setting {key!r}"
                + (f" (it has: {', '.join(known)})." if known else ".")
            )
        text = str(raw).strip()
        if len(text) > 2_000 or "\x00" in text or "\n" in text:
            raise ApiError(f"{known[key].label} is one line of text.")
        choices = [v for v, _ in known[key].choices]
        if choices and text not in choices:
            raise ApiError(f"{known[key].label} is one of: {', '.join(c or '(empty)' for c in choices)}.")
        settings[key] = text
    auth = Auth(str(kind), settings)
    if kind == "api_key" and not _HEADER_NAME.fullmatch(auth.get("name")):
        raise ApiError("Name the API key's header, query parameter or cookie (X-Api-Key).")
    if kind == "jwt" and auth.get("mode") == "signed" and not auth.get("lifetime").isdigit():
        raise ApiError("A signed JWT's lifetime is a number of seconds.")
    if kind == "oauth2":
        flow = auth.get("flow")
        needed = {
            "client_credentials": ("token_url",),
            "authorization_code": ("authorize_url", "token_url"),
            "device_code": ("device_url", "token_url"),
        }[flow]
        for key in needed:
            if auth.get(key) and not re.match(r"^https?://", auth.get(key)):
                raise ApiError(f"{known[key].label} is an http or https address.")
        if not auth.get("redirect_port").isdigit() or int(auth.get("redirect_port")) > 65535:
            raise ApiError("The redirect port is a number (0: any free port).")
    return auth


def variables(auth: Auth, prefix: str) -> list[Variable]:
    """The environment variables the client reads for its auth, each with the constructor argument it
    comes in as. SigV4 reads AWS's own names (a Lambda and the AWS tools set them)."""

    def v(suffix: str, argument: str, required: bool = True, secret: bool = True) -> Variable:
        return Variable(f"{prefix}_{suffix}", argument, required, secret)

    kind = auth.type
    found: list[Variable] = []
    if kind == "api_key":
        found = [v("API_KEY", "api_key")]
    elif kind == "bearer":
        found = [v("TOKEN", "token")]
    elif kind == "basic":
        found = [v("USERNAME", "username", secret=False), v("PASSWORD", "password")]
    elif kind == "oauth2":
        flow = auth.get("flow")
        words = sorted(
            {
                w
                for key in ("token_url", "authorize_url", "device_url")
                for w in _PLACEHOLDER.findall(auth.get(key))
            }
        )
        found = [Variable(f"{prefix}_{w.upper()}", snake(w), True, False) for w in words]
        found += [
            v("CLIENT_ID", "client_id", secret=False),
            v("CLIENT_SECRET", "client_secret", required=flow == "client_credentials"),
        ]
    elif kind == "jwt":
        mode = auth.get("mode")
        if mode == "token":
            found = [v("TOKEN", "token")]
        elif mode == "login":
            found = [v("USERNAME", "username", secret=False), v("PASSWORD", "password")]
        elif auth.get("algorithm") == "HS256":
            found = [v("JWT_SECRET", "jwt_secret")]
        else:
            found = [v("PRIVATE_KEY", "private_key")]
    elif kind == "sigv4":
        found = [
            Variable("AWS_ACCESS_KEY_ID", "access_key_id", True, False),
            Variable("AWS_SECRET_ACCESS_KEY", "secret_access_key", True, True),
            Variable("AWS_SESSION_TOKEN", "session_token", False, True),
        ]
    elif kind == "google":
        found = [v("SERVICE_ACCOUNT_KEY", "service_account_key")]
    elif kind == "firebase":
        if auth.get("mode") == "token":
            found = [v("ID_TOKEN", "id_token")]
        else:
            found = [
                v("FIREBASE_API_KEY", "firebase_api_key", secret=False),
                v("EMAIL", "email", secret=False),
                v("PASSWORD", "password"),
            ]
    return found


def url_variable(prefix: str) -> str:
    """The variable that moves the client to another address (a test service, a slot): ORDERS_URL."""
    return f"{prefix}_URL"


def placeholders(auth: Auth) -> dict[str, str]:
    """The `{tenant}` words of an OAuth URL, each with the constructor argument that fills it."""
    words = {
        w for key in ("token_url", "authorize_url", "device_url") for w in _PLACEHOLDER.findall(auth.get(key))
    }
    return {w: snake(w) for w in sorted(words)}


# ===== presets: the three big function hosts =====


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    urls: tuple[tuple[str, str], ...]  # (what, the address's pattern)
    auths: tuple[tuple[str, Auth], ...]  # (label, the auth it fills in)
    spec_paths: tuple[str, ...] = ()  # where the host keeps its OpenAPI document, from the address's root

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "urls": [{"label": label, "url": url} for label, url in self.urls],
            "auths": [{"label": label, **auth.to_json()} for label, auth in self.auths],
            "spec_paths": list(self.spec_paths),
        }


PRESETS: dict[str, Preset] = {
    p.id: p
    for p in (
        Preset(
            "azure",
            "Azure Function App",
            (("Function app", "https://<app>.azurewebsites.net/api"),),
            (
                ("Function key", Auth("api_key", {"in": "header", "name": "x-functions-key"})),
                (
                    "Entra ID (app registration)",
                    Auth(
                        "oauth2",
                        {
                            "flow": "client_credentials",
                            "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                            "scopes": "api://<application id>/.default",
                        },
                    ),
                ),
            ),
            # The Azure Functions OpenAPI extension's documents.
            ("/api/openapi/v3.json", "/api/swagger.json", "/api/openapi/v2.json"),
        ),
        Preset(
            "aws",
            "AWS Lambda",
            (
                ("Function URL", "https://<url id>.lambda-url.<region>.on.aws"),
                ("API Gateway", "https://<api id>.execute-api.<region>.amazonaws.com/<stage>"),
            ),
            (
                ("None", Auth()),
                ("API key", Auth("api_key", {"in": "header", "name": "x-api-key"})),
                ("Cognito JWT", Auth("jwt", {"mode": "token"})),
                ("IAM (Signature Version 4)", Auth("sigv4", {"region": "us-east-1"})),
            ),
        ),
        Preset(
            "google",
            "Google (Firebase, Cloud Functions, Cloud Run)",
            (
                ("Cloud Functions", "https://<region>-<project>.cloudfunctions.net"),
                ("Cloud Run", "https://<service>-<hash>-<region>.a.run.app"),
            ),
            (
                ("Firebase ID token", Auth("firebase", {"mode": "password"})),
                ("Google identity token (service account)", Auth("google")),
            ),
        ),
    )
}


def spec_urls(preset: str, base_url: str) -> list[str]:
    """Where a preset's host keeps its OpenAPI document, for this address (none: add endpoints by hand)."""
    found = PRESETS.get(preset)
    match = re.match(r"^(https?://[^/]+)", base_url.strip())
    if found is None or match is None or "<" in base_url:
        return []
    return [match.group(1) + path for path in found.spec_paths]


def choices() -> dict[str, Any]:
    """What the Add API dialog offers: the auth types with their settings, and the presets."""
    return {
        "auth_types": [t.to_json() for t in AUTH_TYPES.values()],
        "presets": [p.to_json() for p in PRESETS.values()],
        "methods": list(METHODS),
    }


# ===== reading an OpenAPI document =====


def read_json(text: str) -> dict[str, Any]:
    """An OpenAPI document written as JSON (YAML is read before it reaches here, where it can be)."""
    if len(text) > MAX_SPEC_CHARS:
        raise ApiError("The OpenAPI document is too big (10 MB at most).")
    try:
        found = json.loads(text)
    except json.JSONDecodeError as error:
        raise ApiError(f"The OpenAPI document is not JSON (line {error.lineno}: {error.msg}).") from None
    if not isinstance(found, dict):
        raise ApiError("The OpenAPI document is a JSON object, with openapi (or swagger) and paths.")
    return found


def looks_like_yaml(text: str) -> bool:
    start = text.lstrip()[:200]
    return not start.startswith(("{", "[")) and bool(re.match(r"^\s*(#.*\n\s*)*[\w\"'-]+\s*:", text))


class _Refs:
    """The document's own $refs (#/components/schemas/Order), each followed once on a path (a schema
    that refers to itself stops there)."""

    def __init__(self, doc: Mapping[str, Any]) -> None:
        self.doc = doc

    def follow(self, node: Any, seen: frozenset[str] = frozenset()) -> tuple[Any, frozenset[str]]:
        while isinstance(node, Mapping) and isinstance(node.get("$ref"), str):
            ref = str(node["$ref"])
            if ref in seen or not ref.startswith("#/"):
                return {}, seen
            seen = seen | {ref}
            target: Any = self.doc
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                target = target.get(part) if isinstance(target, Mapping) else None
            node = target if target is not None else {}
        return node, seen


def _text(value: Any, limit: int = 2_000) -> str:
    return " ".join(str(value).split())[:limit] if isinstance(value, str | int | float) else ""


def _schema_type(schema: Any, refs: _Refs, seen: frozenset[str] = frozenset()) -> str:
    schema, seen = refs.follow(schema, seen)
    if not isinstance(schema, Mapping):
        return "string"
    kind = schema.get("type")
    if isinstance(kind, list):  # 3.1: ["string", "null"]
        kind = next((k for k in kind if k != "null"), "string")
    if not kind:
        for key in ("allOf", "oneOf", "anyOf"):
            parts = schema.get(key)
            if isinstance(parts, list) and parts:
                return _schema_type(parts[0], refs, seen)
        kind = "object" if "properties" in schema else "array" if "items" in schema else "string"
    return str(kind) if kind in ("string", "integer", "number", "boolean", "array", "object") else "string"


def _properties(schema: Any, refs: _Refs, seen: frozenset[str] = frozenset()) -> dict[str, Any]:
    """An object schema's properties, allOf's merged."""
    schema, seen = refs.follow(schema, seen)
    if not isinstance(schema, Mapping):
        return {}
    found: dict[str, Any] = {}
    for part in schema.get("allOf") or []:
        found |= _properties(part, refs, seen)
    props = schema.get("properties")
    if isinstance(props, Mapping):
        found |= {str(k): v for k, v in props.items()}
    return found


def _column_type(schema: Any, refs: _Refs) -> str:
    node, _ = refs.follow(schema)
    kind = _schema_type(node, refs)
    form = node.get("format") if isinstance(node, Mapping) else None
    if kind == "string" and form == "date-time":
        return "timestamp"
    if kind == "string" and form == "date":
        return "date"
    return kind


def _rows(schema: Any, refs: _Refs) -> tuple[bool, str, tuple[tuple[str, str], ...]]:
    """Whether an answer's schema is rows, where they are, and their columns."""
    node, seen = refs.follow(schema)
    if not isinstance(node, Mapping):
        return False, "", ()
    kind = _schema_type(node, refs)
    at = ""
    if kind == "object":
        props = _properties(node, refs)
        wrapped = next(
            (key for key in props if key.lower() in ROW_KEYS and _schema_type(props[key], refs) == "array"),
            None,
        )
        if wrapped is None:
            return False, "", ()
        at, (node, seen) = wrapped, refs.follow(props[wrapped], seen)
    elif kind != "array":
        return False, "", ()
    items = node.get("items") if isinstance(node, Mapping) else None
    columns = tuple(
        (name, _column_type(prop, refs))
        for name, prop in list(_properties(items, refs, seen).items())[:MAX_COLUMNS]
    )
    if not columns and items is not None and _schema_type(items, refs, seen) not in ("object", "array"):
        columns = (("value", _column_type(items, refs)),)
    return True, at, columns


def _success(responses: Any) -> Any:
    if not isinstance(responses, Mapping):
        return None
    for code in ("200", "201", "202", "203", "2XX", "2xx", "default"):
        if code in responses:
            return responses[code]
    return next((r for c, r in responses.items() if str(c).startswith("2")), None)


def _content_schema(content: Any) -> tuple[str, Any]:
    """The JSON (or form) part of a 3.x content map: its kind and schema."""
    if not isinstance(content, Mapping) or not content:
        return "", None
    for media, part in content.items():
        if "json" in str(media).lower():
            return "json", part.get("schema") if isinstance(part, Mapping) else None
    for media, part in content.items():
        if str(media).lower() in ("application/x-www-form-urlencoded", "multipart/form-data"):
            return "form", part.get("schema") if isinstance(part, Mapping) else None
    media, part = next(iter(content.items()))
    kind = "json" if str(media) == "*/*" else "text"
    return kind, part.get("schema") if isinstance(part, Mapping) else None


def _parameter(raw: Any, refs: _Refs) -> Parameter | None:
    node, _ = refs.follow(raw)
    if not isinstance(node, Mapping):
        return None
    name, place = node.get("name"), node.get("in")
    if not isinstance(name, str) or not name or place not in PLACES:
        return None
    schema = node.get("schema", node)  # 2.0 keeps type on the parameter itself
    resolved, _ = refs.follow(schema)
    enum = resolved.get("enum") if isinstance(resolved, Mapping) else None
    return Parameter(
        name=name[:128],
        place=str(place),
        required=bool(node.get("required")) or place == "path",
        type=_schema_type(schema, refs),
        description=_text(node.get("description")),
        enum=tuple(str(e)[:60] for e in enum[:20]) if isinstance(enum, list) else (),
    )


def _with_python_names(params: list[Parameter]) -> tuple[Parameter, ...]:
    taken: set[str] = set(RESERVED)
    named = []
    for p in params:
        python = _unique(snake(p.name, "value"), taken)
        taken.add(python)
        named.append(replace(p, python=python))
    return tuple(named)


def _operation_name(raw: Any, method: str, path: str) -> str:
    if isinstance(raw, str) and raw.strip():
        return snake(raw)
    words = [p[1:-1] if p.startswith("{") else p for p in path.strip("/").split("/") if p]
    by = [w for p, w in zip(path.strip("/").split("/"), words, strict=False) if p.startswith("{")]
    plain = [w for p, w in zip(path.strip("/").split("/"), words, strict=False) if not p.startswith("{")]
    name = "_".join([method.lower(), *plain] + (["by", *by] if by else []))
    return snake(name)


def _base_from_servers(doc: Mapping[str, Any], source_url: str) -> str:
    servers = doc.get("servers")
    if isinstance(servers, list) and servers and isinstance(servers[0], Mapping):
        url = str(servers[0].get("url") or "")
        given = servers[0].get("variables")
        if isinstance(given, Mapping):
            for key, var in given.items():
                default = var.get("default") if isinstance(var, Mapping) else None
                url = url.replace("{" + str(key) + "}", str(default or ""))
        return _joined(source_url, url)
    host = doc.get("host")
    if isinstance(host, str) and host:
        schemes = doc.get("schemes") if isinstance(doc.get("schemes"), list) else []
        scheme = "https" if not schemes or "https" in schemes else str(schemes[0])
        return f"{scheme}://{host}{doc.get('basePath') or ''}".rstrip("/")
    base = str(doc.get("basePath") or "")
    return _joined(source_url, base) if source_url else base.rstrip("/")


def _joined(source_url: str, url: str) -> str:
    """A server's address that is relative to where the document came from, made whole."""
    if re.match(r"^https?://", url) or not source_url:
        return url.rstrip("/")
    root = re.match(r"^(https?://[^/]+)(/.*)?$", source_url)
    if root is None:
        return url.rstrip("/")
    if url.startswith("/"):
        return (root.group(1) + url).rstrip("/")
    folder = (root.group(2) or "/").rsplit("/", 1)[0]
    return f"{root.group(1)}{folder}/{url}".rstrip("/")


def _scheme_auth(scheme: Any, refs: _Refs) -> Auth | None:
    """A security scheme as the auth type it is (unknown ones: none)."""
    node, _ = refs.follow(scheme)
    if not isinstance(node, Mapping):
        return None
    kind = str(node.get("type") or "")
    if str(node.get("x-amazon-apigateway-authtype") or "").lower() == "awssigv4":
        return Auth("sigv4", {"region": "us-east-1"})
    issuer = str(node.get("x-google-issuer") or "")
    if "securetoken.google.com" in issuer:
        return Auth("firebase", {"mode": "password"})
    if issuer:
        return Auth("google")
    authorizer = node.get("x-amazon-apigateway-authorizer")
    if isinstance(authorizer, Mapping) and str(authorizer.get("type") or "").lower() in (
        "cognito_user_pools",
        "jwt",
    ):
        return Auth("jwt", {"mode": "token"})
    if kind == "apiKey":
        place = str(node.get("in") or "header")
        name = str(node.get("name") or "X-Api-Key")
        return Auth(
            "api_key", {"in": place if place in ("header", "query", "cookie") else "header", "name": name}
        )
    if kind == "basic" or (kind == "http" and str(node.get("scheme") or "").lower() == "basic"):
        return Auth("basic")
    if kind == "http" and str(node.get("scheme") or "").lower() == "bearer":
        if str(node.get("bearerFormat") or "").upper() == "JWT":
            return Auth("jwt", {"mode": "token"})
        return Auth("bearer")
    if kind == "oauth2":
        flows = node.get("flows")
        if isinstance(flows, Mapping):  # 3.x
            if isinstance(flows.get("clientCredentials"), Mapping):
                flow = flows["clientCredentials"]
                return Auth("oauth2", _oauth(flow, "client_credentials"))
            if isinstance(flows.get("authorizationCode"), Mapping):
                return Auth("oauth2", _oauth(flows["authorizationCode"], "authorization_code"))
            return Auth("oauth2", {"flow": "client_credentials"})
        flow2 = str(node.get("flow") or "")  # 2.0
        if flow2 == "accessCode":
            return Auth("oauth2", _oauth(node, "authorization_code"))
        return Auth("oauth2", _oauth(node, "client_credentials"))
    if kind == "openIdConnect":
        return Auth("oauth2", {"flow": "authorization_code"})
    return None


def _oauth(flow: Mapping[str, Any], kind: str) -> dict[str, str]:
    settings = {"flow": kind}
    if isinstance(flow.get("tokenUrl"), str):
        settings["token_url"] = flow["tokenUrl"]
    if isinstance(flow.get("authorizationUrl"), str) and kind == "authorization_code":
        settings["authorize_url"] = flow["authorizationUrl"]
    scopes = flow.get("scopes")
    if isinstance(scopes, Mapping) and scopes:
        settings["scopes"] = " ".join(str(s) for s in scopes)
    return settings


def _schemes(doc: Mapping[str, Any], refs: _Refs) -> tuple[tuple[str, Auth], ...]:
    components = doc.get("components")
    raw = (components.get("securitySchemes") if isinstance(components, Mapping) else None) or doc.get(
        "securityDefinitions"
    )
    if not isinstance(raw, Mapping):
        return ()
    found = []
    for name, scheme in list(raw.items())[:20]:
        auth = _scheme_auth(scheme, refs)
        if auth is not None:
            found.append((str(name), auth))
    return tuple(found)


def _chosen_scheme(doc: Mapping[str, Any], schemes: tuple[tuple[str, Auth], ...]) -> Auth:
    """The auth the API asks for: its own security requirement's first scheme, else the first one an
    operation names, else the first it declares."""
    if not schemes:
        return Auth()
    by_name = dict(schemes)
    requirements: list[Any] = []
    if isinstance(doc.get("security"), list):
        if not doc["security"]:
            return Auth()
        requirements += doc["security"]
    for item in (doc.get("paths") or {}).values() if isinstance(doc.get("paths"), Mapping) else []:
        if isinstance(item, Mapping):
            for op in item.values():
                if isinstance(op, Mapping) and isinstance(op.get("security"), list):
                    requirements += op["security"]
    for requirement in requirements:
        if isinstance(requirement, Mapping):
            for name in requirement:
                if name in by_name:
                    return by_name[name]
    return schemes[0][1]


def parse_spec(doc: Mapping[str, Any], source_url: str = "") -> Spec:
    """An OpenAPI document (3.x, or Swagger 2.0) as the API's spec."""
    openapi, swagger = doc.get("openapi"), doc.get("swagger")
    if isinstance(openapi, str) and openapi.startswith("3."):
        source = f"OpenAPI {openapi}"
    elif str(swagger) == "2.0":
        source = "Swagger 2.0"
    else:
        raise ApiError("This is not an OpenAPI document: it has no openapi: 3.x (or swagger: 2.0).")
    paths = doc.get("paths")
    if not isinstance(paths, Mapping) or not paths:
        raise ApiError("The OpenAPI document has no paths.")
    refs = _Refs(doc)
    found_info = doc.get("info")
    info: Mapping[str, Any] = found_info if isinstance(found_info, Mapping) else {}
    operations: list[Operation] = []
    taken: set[str] = set(RESERVED)
    for path, item in paths.items():
        item, _ = refs.follow(item)
        if not isinstance(item, Mapping) or not isinstance(path, str) or not path.startswith("/"):
            continue
        shared = [p for p in (_parameter(r, refs) for r in item.get("parameters") or []) if p]
        for verb, raw in item.items():
            method = str(verb).upper()
            if method not in METHODS or not isinstance(raw, Mapping):
                continue
            if len(operations) >= MAX_OPERATIONS:
                raise ApiError(f"The OpenAPI document has more than {MAX_OPERATIONS} operations.")
            own = {(p.name, p.place): p for p in shared}
            body, body_required, body_description = "", False, ""
            for r in raw.get("parameters") or []:
                node, _ = refs.follow(r)
                if isinstance(node, Mapping) and node.get("in") in ("body", "formData"):  # 2.0
                    body = "json" if node.get("in") == "body" else "form"
                    body_required = body_required or bool(node.get("required"))
                    body_description = body_description or _text(node.get("description"))
                    continue
                p = _parameter(r, refs)
                if p:
                    own[(p.name, p.place)] = p
            for name in _PLACEHOLDER.findall(path):  # a path's {word} the spec forgot
                if not any(n == name and place == "path" for n, place in own):
                    own[(name, "path")] = Parameter(name, "path", True, "string")
            request, _ = refs.follow(raw.get("requestBody"))
            if isinstance(request, Mapping) and request:
                kind, _schema = _content_schema(request.get("content"))
                body = kind if kind in ("json", "form") else "json"
                body_required = bool(request.get("required"))
                body_description = _text(request.get("description"))
            answer, _ = refs.follow(_success(raw.get("responses")))
            table, at, returns = False, "", "nothing"
            columns: tuple[tuple[str, str], ...] = ()
            if isinstance(answer, Mapping):
                if "content" in answer:
                    kind, schema = _content_schema(answer.get("content"))
                    if schema is not None and kind == "json":
                        table, at, columns = _rows(schema, refs)
                    returns = "text" if kind == "text" else _schema_type(schema, refs) if schema else "object"
                elif "schema" in answer:  # 2.0
                    table, at, columns = _rows(answer["schema"], refs)
                    returns = _schema_type(answer["schema"], refs)
            params = sorted(own.values(), key=lambda p: (not p.required, PLACES.index(p.place)))
            if len(params) > MAX_PARAMETERS:
                raise ApiError(f"{method} {path} has more than {MAX_PARAMETERS} parameters.")
            name = _unique(_operation_name(raw.get("operationId"), method, path), taken)
            taken.add(name)
            tags = raw.get("tags")
            operations.append(
                Operation(
                    method=method,
                    path=path[:500],
                    name=name,
                    summary=_text(raw.get("summary"), 300),
                    description=_text(raw.get("description")),
                    parameters=_with_python_names(params),
                    body=body,
                    body_required=body_required,
                    body_description=body_description,
                    table=table,
                    rows_at=at,
                    columns=columns,
                    tag=_text(tags[0], 60) if isinstance(tags, list) and tags else "",
                    deprecated=bool(raw.get("deprecated")),
                    returns="rows" if table else returns,
                )
            )
    if not operations:
        raise ApiError("The OpenAPI document's paths have no operations (get, post, ...).")
    schemes = _schemes(doc, refs)
    return Spec(
        title=_text(info.get("title"), 64) or "API",
        version=_text(info.get("version"), 60),
        source=source,
        base_url=_base_from_servers(doc, source_url),
        description=_text(info.get("description")),
        operations=tuple(operations),
        auth=_chosen_scheme(doc, schemes),
        schemes=schemes,
    )


# ===== the form: a base URL, an auth type and endpoints =====


def check_url(value: Any) -> str:
    url = str(value or "").strip()
    if not re.match(r"^https?://[^\s/]+[^\s]*$", url) or len(url) > 2_000:
        raise ApiError("The base URL is an http or https address (https://<app>.azurewebsites.net/api).")
    if "<" in url or ">" in url:
        raise ApiError(f"Fill in the base URL's <...> parts: {url}")
    return url.rstrip("/")


def parse_form(form: Any) -> Spec:
    """The form as a spec: {"title", "base_url", "endpoints": [{"method", "path", "parameters":
    "status, limit" or [{"name", "in", "required", "type"}], "table": true, "columns": "id, amount",
    "summary"}]}. A path's {word} is a path parameter; a parameter named otherwise is in the query."""
    if not isinstance(form, Mapping):
        raise ApiError(
            'The form is {"base_url": "https://...", "endpoints": [{"method": "GET", "path": "/orders"}]}.'
        )
    base = check_url(form.get("base_url"))
    endpoints = form.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise ApiError("Add an endpoint: a method and a path (GET /orders).")
    if len(endpoints) > MAX_OPERATIONS:
        raise ApiError(f"At most {MAX_OPERATIONS} endpoints.")
    operations: list[Operation] = []
    taken: set[str] = set(RESERVED)
    for at, raw in enumerate(endpoints, start=1):
        if not isinstance(raw, Mapping):
            raise ApiError(f'Endpoint {at} is {{"method": "GET", "path": "/orders"}}.')
        method = str(raw.get("method") or "GET").upper()
        if method not in METHODS:
            raise ApiError(f"Endpoint {at}'s method is one of: {', '.join(METHODS)}.")
        path = "/" + str(raw.get("path") or "").strip().lstrip("/")
        if path == "/" and not str(raw.get("path") or "").strip():
            raise ApiError(f"Endpoint {at} has no path (/orders).")
        if len(path) > 500 or re.search(r"\s", path):
            raise ApiError(f"Endpoint {at}'s path is one word of an address (/orders/{{order_id}}).")
        params: dict[tuple[str, str], Parameter] = {
            (w, "path"): Parameter(w, "path", True, "string") for w in _PLACEHOLDER.findall(path)
        }
        given = raw.get("parameters") or []
        if isinstance(given, str):
            given = [{"name": n.strip()} for n in given.split(",") if n.strip()]
        if not isinstance(given, list) or len(given) > MAX_PARAMETERS:
            raise ApiError(f"Endpoint {at}'s parameters are names, separated by commas (status, limit).")
        for g in given:
            entry = {"name": g} if isinstance(g, str) else g
            if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
                raise ApiError(f"Endpoint {at}: a parameter is a name (status).")
            name = entry["name"].strip()
            required = name.endswith("*") or bool(entry.get("required"))
            name = name.rstrip("*").strip()
            if not _HEADER_NAME.fullmatch(name):
                raise ApiError(f"Endpoint {at}: {name!r} is not a parameter's name.")
            place = str(entry.get("in") or ("path" if (name, "path") in params else "query"))
            if place not in PLACES:
                raise ApiError(f"Endpoint {at}: a parameter is in the {', '.join(PLACES)}.")
            kind = str(entry.get("type") or "string")
            if kind not in ("string", "integer", "number", "boolean", "array", "object"):
                kind = "string"
            params[(name, place)] = Parameter(name, place, required or place == "path", kind)
        columns_text = raw.get("columns") or ""
        columns = tuple(
            (c.strip(), "string")
            for c in (columns_text.split(",") if isinstance(columns_text, str) else [])
            if c.strip()
        )[:MAX_COLUMNS]
        name = _unique(_operation_name(raw.get("name"), method, path), taken)
        taken.add(name)
        table = bool(raw.get("table"))
        ordered = sorted(params.values(), key=lambda p: (not p.required, PLACES.index(p.place)))
        operations.append(
            Operation(
                method=method,
                path=path,
                name=name,
                summary=_text(raw.get("summary"), 300),
                parameters=_with_python_names(ordered),
                body="json" if method in ("POST", "PUT", "PATCH") else "",
                table=table,
                rows_at=str(raw.get("rows_at") or "") if table else "",
                columns=columns if table else (),
                returns="rows" if table else "object",
            )
        )
    title = _text(form.get("title"), 64) or "API"
    return Spec(title, "", "form", base, "", tuple(operations), check_auth(form.get("auth")))


# ===== the connection: its three boxes =====


def _q(text: str) -> str:
    """A string as a Python literal in double quotes (JSON's escapes are Python's)."""
    return json.dumps(text)


def connect_code(names: Names, path: str, auth: Auth) -> str:
    """Connect: the made file loaded from where it was written, and the client made with its secrets
    read from the environment (the connection maps each to the vault, the keyring or a value)."""
    lines = [
        "import importlib.util",
        "import os",
        "import sys",
        "",
        f"# {names.file}, made by Add API: the client, loaded from where it was written.",
        f"spec = importlib.util.spec_from_file_location({_q(names.module)}, {_q(path)})",
        f"{names.module} = importlib.util.module_from_spec(spec)",
        f"sys.modules[{_q(names.module)}] = {names.module}",
        f"spec.loader.exec_module({names.module})",
        "",
        *_client_lines(names, auth),
    ]
    return "\n".join(lines)


def _client_lines(names: Names, auth: Auth) -> list[str]:
    """`conn = API_Orders.OrdersApi(...)`, each argument read from its environment variable."""
    lines = [
        f"conn = {names.module}.{names.cls}(",
        f"    os.environ.get({_q(url_variable(names.prefix))}),",
    ]
    for v in variables(auth, names.prefix):
        read = f"os.environ[{_q(v.name)}]" if v.required else f"os.environ.get({_q(v.name)})"
        lines.append(f"    {v.argument}={read},")
    lines.append(")")
    return lines


# ===== Try it: one table's first rows before Add (nothing written) =====

TRY_ROWS: int = 5


def tried_table(spec: Spec, operation: str) -> tuple[str, str]:
    """The table an operation reads as (schema, table); an ApiError says why one cannot be tried."""
    for table, op in spec.tables().items():
        if op.name == operation:
            return schema_of(op), table
    found = next((op for op in spec.operations if op.name == operation), None)
    if found is None:
        raise ApiError(f"There is no {operation}: name an operation the preview lists.")
    if found.method != "GET":
        raise ApiError(f"{found.method} {found.path} changes data: only a GET is tried.")
    if not found.table:
        raise ApiError(f"{found.path} does not answer rows: tick Read as a table to try it.")
    raise ApiError(f"{found.path} needs a value for each of its parameters: it cannot be tried alone.")


def try_connection(names: Names, inlined: str, auth: Auth, typed: Any) -> dict[str, Any]:
    """A draft connection for Try it: the made file pasted in (written nowhere), the client made as
    the saved connection makes it. A value typed for a variable is used for this run only (a secret's
    as a typed password, never kept); any other variable is read from this computer's environment."""
    given = typed if isinstance(typed, Mapping) else {}
    sources: list[dict[str, str]] = []
    secrets: dict[str, str] = {}
    for v in variables(auth, names.prefix):
        value = given.get(v.name)
        if not isinstance(value, str) or not value:
            sources.append({"name": v.name, "from": "env"})
        elif v.secret:
            sources.append({"name": v.name, "from": "keyring"})
            secrets[v.name] = value
        else:
            sources.append({"name": v.name, "from": "value", "value": value})
    code = "\n".join([inlined.rstrip(), "", "import os", "", *_client_lines(names, auth)])
    return {
        "name": names.connection,
        "kind": "other",
        "template": "python",
        "variable": "conn",
        "code": code,
        "read": {"command": READ_CODE},
        "variables": sources,
        "secrets": secrets,
    }


TABLES_CODE: str = "conn.tables()"
READ_CODE: str = "conn.read(table, limit)"


def connection_body(
    names: Names,
    path: str,
    auth: Auth,
    description: str,
    sources: Any = None,
    secrets: Any = None,
    row_limit: Any = None,
) -> dict[str, Any]:
    """The "Python (your own code)" connection, as the Connections form saves it."""
    body: dict[str, Any] = {
        "name": names.connection,
        "kind": "other",
        "template": "python",
        "variable": "conn",
        "code": connect_code(names, path, auth),
        "catalog": {"language": "python", "command": TABLES_CODE},
        "read": {"command": READ_CODE},
        "description": description[:300],
        "tags": ["api"],
    }
    if sources is not None:
        body["variables"] = sources
    if secrets:
        body["secrets"] = secrets
    if row_limit is not None:
        body["row_limit"] = row_limit
    return body


def is_connection_for(code: str, module: str) -> bool:
    """A saved connection's Connect that loads this made file (re-import changes it; another is left)."""
    return f"spec_from_file_location({_q(module)}," in code


# ===== re-import: what changes =====


@dataclass(frozen=True)
class Changes:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    same: int
    auth: bool  # the auth type or its settings
    base_url: bool

    @property
    def any(self) -> bool:
        return bool(self.added or self.removed or self.changed or self.auth or self.base_url)

    def to_json(self) -> dict[str, Any]:
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": list(self.changed),
            "same": self.same,
            "auth": self.auth,
            "base_url": self.base_url,
            "any": self.any,
        }


def changes(
    old: Mapping[str, str], new: Mapping[str, str], old_head: Mapping[str, Any], new_head: Mapping[str, Any]
) -> Changes:
    """What re-importing changes: methods (name -> its signature and documentation, as
    domain/api_clients.py reads them from a made file) added, removed and changed; and the auth and
    base URL in the files' marks."""
    added = tuple(sorted(n for n in new if n not in old))
    removed = tuple(sorted(n for n in old if n not in new))
    changed = tuple(sorted(n for n in new if n in old and old[n] != new[n]))
    same = sum(1 for n in new if n in old and old[n] == new[n])
    return Changes(
        added,
        removed,
        changed,
        same,
        auth=old_head.get("auth") != new_head.get("auth"),
        base_url=old_head.get("base_url") != new_head.get("base_url"),
    )
