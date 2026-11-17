"""Connectors in the APIs explorer, and custom connectors from an API's OpenAPI document.

**A connector's shape** (operations, inputs, outputs) is its OpenAPI (Swagger 2.0) definition, read into
the APIs explorer's own model (swissarmybench.domain.api_explorer.explore): the same operations, inputs,
outputs, schemas and made-up examples the APIs page shows. Read-only: a connector is not an API blade (no
Author a call, no Return as table); its action is **Add to app** (`pa app add data-source`). Operations the
connector marks `x-ms-visibility: internal` are left out, as the designers leave them out.

Where a definition comes from: the code app's own `.power/schemas/` (the CLI downloaded it when the
connector was added), else the environment's connectivity service (what the Power Apps CLI itself reads:
`connectivity/connectors/<name>`, its `properties.swagger`).

**A custom connector** from an API in the library: `apiDefinition.swagger.json` (the document as Swagger
2.0, converted from OpenAPI 3 where it is one) and `apiProperties.json` (its connection parameters mapped
from the API's sign-in), then `pac connector create`. Never a secret in either file: an OAuth client's
secret, an API key's value and a password are typed by the user in Power Platform when the connection is
made. Pure rules.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from typing import Any

from swissarmybench.domain import api_explorer, apis

DEFINITION_FILE = "apiDefinition.swagger.json"
PROPERTIES_FILE = "apiProperties.json"
REDIRECT_URL = "https://global.consent.azure-apim.net/redirect"
_REF = re.compile(r"^#/components/schemas/(.+)$")


class ConnectorError(ValueError):
    """A definition that cannot be read, or one that cannot be made into a custom connector."""


def find_swagger(document: Any) -> dict[str, Any] | None:
    """The definition inside what a source holds: the document itself, or the service's
    {properties: {swagger: {...}}} answer."""
    if isinstance(document, Mapping):
        if str(document.get("swagger")) == "2.0" or str(document.get("openapi", "")).startswith("3."):
            return dict(document)
        props = document.get("properties")
        if isinstance(props, Mapping) and isinstance(props.get("swagger"), Mapping):
            return dict(props["swagger"])
        if isinstance(document.get("swagger"), Mapping):
            return dict(document["swagger"])
    return None


def visible(swagger: Mapping[str, Any]) -> dict[str, Any]:
    """The definition without its internal operations (and without a path left empty by that)."""
    doc = copy.deepcopy(dict(swagger))
    paths: dict[str, Any] = {}
    for path, item in (doc.get("paths") or {}).items():
        if not isinstance(item, Mapping):
            continue
        kept = {
            verb: op
            for verb, op in item.items()
            if not (isinstance(op, Mapping) and op.get("x-ms-visibility") == "internal")
        }
        if any(str(v).upper() in apis.METHODS for v in kept):
            paths[path] = kept
    doc["paths"] = paths
    return doc


def explored(name: str, display_name: str, swagger: Mapping[str, Any], where: str) -> dict[str, Any]:
    """The connector as the APIs explorer's model has it (Explored), marked read-only, with its source."""
    doc = visible(swagger)
    try:
        spec = apis.parse_spec(doc, "")
    except apis.ApiError as error:
        raise ConnectorError(f"{display_name}'s definition cannot be read: {error}") from None
    shown = api_explorer.explore(doc, spec)
    ids = {
        (str(verb).upper(), path): str(raw.get("operationId") or "")
        for path, item in (doc.get("paths") or {}).items()
        for verb, raw in (item.items() if isinstance(item, Mapping) else [])
        if isinstance(raw, Mapping)
    }
    for op in shown["operations"]:
        # The generated service's method is named for the operation's id (Office365UsersService.MyProfile_V2).
        op["operation_id"] = ids.get((op["method"], op["path"]), "")
        op.update({"blade": None, "as_table": False, "table": None, "inputs": {}, "body_saved": None})
        op["sql_name"] = None
    return shown | {
        "name": name,
        "display_name": display_name,
        "read_only": True,
        "connector": name,
        "from": where,
    }


def search(connectors: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """The environment's connectors whose name, display name or description holds every word."""
    words = [w for w in re.split(r"\s+", query.lower().strip()) if w]
    if not words:
        return connectors
    found = []
    for c in connectors:
        text = f"{c['name']} {c['display_name']} {c.get('description', '')}".lower()
        if all(w in text for w in words):
            found.append(c)
    return found


# ===== custom connectors =====


def _ref_2(value: Any) -> Any:
    """OpenAPI 3's references, as Swagger 2.0's (#/components/schemas/X -> #/definitions/X), everywhere."""
    if isinstance(value, Mapping):
        out = {}
        for k, v in value.items():
            if k == "$ref" and isinstance(v, str) and _REF.match(v):
                out[k] = "#/definitions/" + _REF.match(v).group(1)  # type: ignore[union-attr]
            elif k == "nullable":
                out["x-nullable"] = v
            else:
                out[k] = _ref_2(v)
        return out
    if isinstance(value, list):
        return [_ref_2(v) for v in value]
    return value


def _json_schema(content: Any) -> tuple[str, Any]:
    if not isinstance(content, Mapping) or not content:
        return "", None
    media = next((m for m in content if "json" in str(m)), next(iter(content)))
    entry = content.get(media)
    return str(media), (entry or {}).get("schema") if isinstance(entry, Mapping) else None


def to_swagger(doc: Mapping[str, Any]) -> dict[str, Any]:
    """The document as Swagger 2.0, the form custom connectors take (a 2.0 document is kept as it is)."""
    if str(doc.get("swagger")) == "2.0":
        return copy.deepcopy(dict(doc))
    if not str(doc.get("openapi", "")).startswith("3."):
        raise ConnectorError("A custom connector is made from an OpenAPI document (3.x or Swagger 2.0).")
    info = dict(doc.get("info") or {"title": "API", "version": "1.0"})
    servers = doc.get("servers") or []
    url = str(servers[0].get("url")) if servers and isinstance(servers[0], Mapping) else ""
    found = re.match(r"^(https?)://([^/]+)(/.*)?$", url)
    if not found:
        raise ConnectorError(
            "The API needs a full server address (https://host/path) for a custom connector."
        )
    out: dict[str, Any] = {
        "swagger": "2.0",
        "info": {"title": str(info.get("title") or "API")[:30], "version": str(info.get("version") or "1.0")},
        "host": found.group(2),
        "basePath": (found.group(3) or "/").rstrip("/") or "/",
        "schemes": [found.group(1)],
        "consumes": ["application/json"],
        "produces": ["application/json"],
        "paths": {},
        "definitions": _ref_2((doc.get("components") or {}).get("schemas") or {}),
    }
    if info.get("description"):
        out["info"]["description"] = str(info["description"])[:1000]
    for path, item in (doc.get("paths") or {}).items():
        if not isinstance(item, Mapping):
            continue
        shared = [_ref_2(p) for p in item.get("parameters") or []]
        new_item: dict[str, Any] = {}
        for verb, op in item.items():
            if str(verb).upper() not in apis.METHODS or not isinstance(op, Mapping):
                continue
            params = []
            for p in [*shared, *[_ref_2(x) for x in op.get("parameters") or []]]:
                if not isinstance(p, Mapping) or "$ref" in p:
                    continue
                given = p.get("schema")
                schema: Mapping[str, Any] = given if isinstance(given, Mapping) else {}
                param: dict[str, Any] = {k: p[k] for k in ("name", "in", "required", "description") if k in p}
                param["type"] = schema.get("type", "string")
                for key in ("format", "enum", "default", "items"):
                    if key in schema:
                        param[key] = schema[key]
                if param.get("in") == "path":
                    param["required"] = True
                params.append(param)
            body = op.get("requestBody") if isinstance(op.get("requestBody"), Mapping) else None
            if body:
                _, schema = _json_schema(body.get("content"))
                params.append(
                    {
                        "name": "body",
                        "in": "body",
                        "required": bool(body.get("required")),
                        "schema": _ref_2(schema or {"type": "object"}),
                    }
                )
            responses: dict[str, Any] = {}
            for status, answer in (op.get("responses") or {"200": {"description": "OK"}}).items():
                answer = answer if isinstance(answer, Mapping) else {}
                entry: dict[str, Any] = {"description": str(answer.get("description") or "OK")}
                _, schema = _json_schema(answer.get("content"))
                if schema is not None:
                    entry["schema"] = _ref_2(schema)
                responses[str(status)] = entry
            made: dict[str, Any] = {
                "operationId": str(op.get("operationId") or f"{verb}_{path}")[:80],
                "parameters": params,
                "responses": responses,
            }
            for key in ("summary", "description", "tags", "deprecated"):
                if key in op:
                    made[key] = op[key]
            new_item[str(verb).lower()] = made
        if new_item:
            out["paths"][path] = new_item
    if not out["paths"]:
        raise ConnectorError("The document has no operations to make a connector of.")
    return out


def _ui(display: str, description: str, secure: bool = False, tab: int = 2) -> dict[str, Any]:
    return {
        "displayName": display,
        "description": description,
        "tooltip": description,
        "constraints": {"tabIndex": tab, "clearText": not secure, "required": "true"},
    }


def connection_parameters(auth: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    """The API's sign-in as a custom connector's connection parameters, the Swagger security it needs,
    and a plain note of what the user fills in Power Platform. No secret value goes in."""
    kind = str(auth.get("type") or "none")
    if kind == "none":
        return {}, {}, "No sign-in."
    if kind == "api_key":
        where = str(auth.get("in") or "header")
        name = str(auth.get("name") or "X-Api-Key")
        if where == "cookie":
            raise ConnectorError("A key sent in a cookie cannot be a custom connector's sign-in.")
        params = {
            "api_key": {
                "type": "securestring",
                "uiDefinition": _ui("API key", f"The key sent as {name}", True),
            }
        }
        security: dict[str, Any] = {
            "securityDefinitions": {"API Key": {"type": "apiKey", "in": where, "name": name}}
        }
        return params, security, f"The key is typed when the connection is made (sent as {name})."
    if kind == "basic":
        params = {
            "username": {"type": "securestring", "uiDefinition": _ui("User name", "The user name", True, 2)},
            "password": {"type": "securestring", "uiDefinition": _ui("Password", "The password", True, 3)},
        }
        security = {"securityDefinitions": {"basic_auth": {"type": "basic"}}}
        return params, security, "The user name and password are typed when the connection is made."
    if kind == "bearer":
        params = {"api_key": {"type": "securestring", "uiDefinition": _ui("Token", "Bearer <token>", True)}}
        security = {
            "securityDefinitions": {"API Key": {"type": "apiKey", "in": "header", "name": "Authorization"}}
        }
        return params, security, "The token is typed when the connection is made, as Bearer <token>."
    if kind == "oauth2":
        flow = str(auth.get("flow") or "client_credentials")
        if flow != "authorization_code":
            raise ConnectorError(
                "Custom connectors sign people in with OAuth's authorization code flow; this API uses "
                f"{flow}. Change its sign-in to the authorization code flow first."
            )
        scopes = [s for s in re.split(r"[\s,]+", str(auth.get("scopes") or "")) if s]
        token_url = str(auth.get("token_url") or "")
        authorize_url = str(auth.get("authorize_url") or "")
        if not token_url or not authorize_url:
            raise ConnectorError("The API's OAuth sign-in needs its authorization and token addresses.")
        params = {
            "token": {
                "type": "oAuthSetting",
                "oAuthSettings": {
                    "identityProvider": "oauth2",
                    "clientId": "",
                    "scopes": scopes,
                    "redirectMode": "Global",
                    "redirectUrl": REDIRECT_URL,
                    "properties": {"IsFirstParty": "False"},
                    "customParameters": {
                        "authorizationUrl": {"value": authorize_url},
                        "tokenUrl": {"value": token_url},
                        "refreshUrl": {"value": token_url},
                    },
                },
            }
        }
        security = {
            "securityDefinitions": {
                "oauth2_auth": {
                    "type": "oauth2",
                    "flow": "accessCode",
                    "authorizationUrl": authorize_url,
                    "tokenUrl": token_url,
                    "scopes": {s: s for s in scopes},
                }
            }
        }
        return params, security, "The OAuth client's id and secret are filled in Power Platform, never here."
    raise ConnectorError(
        f"A custom connector cannot sign in the way this API does ({apis.AUTH_TYPES[kind].label}): "
        "custom connectors take no sign-in, an API key, Basic or OAuth 2.0."
        if kind in apis.AUTH_TYPES
        else f"{kind} is not a sign-in type."
    )


def custom_connector_files(
    doc: Mapping[str, Any], auth: Mapping[str, Any], publisher: str = "", brand_color: str = "#007ee5"
) -> dict[str, Any]:
    """The two files `pac connector create` reads, as text, and what the user fills in later."""
    swagger = to_swagger(doc)
    params, security, note = connection_parameters(auth)
    swagger.update(security)
    if security:
        name = next(iter(security["securityDefinitions"]))
        swagger["security"] = [{name: []}]
    if not re.match(r"^#[0-9a-fA-F]{6}$", brand_color):
        raise ConnectorError("The brand colour is #rrggbb.")
    properties: dict[str, Any] = {
        "properties": {
            "connectionParameters": params,
            "iconBrandColor": brand_color,
            "capabilities": [],
            "publisher": publisher[:60] or str(swagger["info"]["title"]),
            "stackOwner": publisher[:60] or str(swagger["info"]["title"]),
        }
    }
    text = json.dumps(swagger, indent=2) + "\n"
    props = json.dumps(properties, indent=2) + "\n"
    return {
        "files": {DEFINITION_FILE: text, PROPERTIES_FILE: props},
        "operations": sum(len(v) for v in swagger["paths"].values()),
        "title": swagger["info"]["title"],
        "host": swagger["host"],
        "sign_in": note,
    }
