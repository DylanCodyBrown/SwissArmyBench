"""Made-up web services on 127.0.0.1 for Add API's tests: an orders API with any one auth type in front of
it, its OpenAPI documents (3.0 and Swagger 2.0), and the sign-in services the auth types talk to (an OAuth
2.0 server with PKCE and device code, a login endpoint, Google's token endpoint, Firebase's). Every key,
password, token and row is made up.

  GET  /openapi.json, /swagger.json      the API's documents (no sign-in)
  GET  /v1/orders?status&pageToken       {"items": [10 a page], "nextToken"}: 25 orders
  GET  /v1/orders/{order_id}             one order          POST /v1/orders   a new one, echoed
  GET  /v1/clients?cursor                a list, 2 a page, the next in a Link header
  GET  /v1/regions?page                  a list, 3 a page (a page number)
  GET  /v1/products                      a list (the form's endpoint: no schema says its columns)
  GET  /v1/flaky                         503 the first time, then a list
  POST /v1/login                         {"username", "password"} -> {"token"} (a JWT login)
  /oauth/{tenant}/token, /oauth/authorize, /oauth/device;  /google/token;  /firebase/signin, /refresh
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlsplit

API_KEY = "made-up-api-key-5521"
BEARER = "made-up-bearer-8812"
USER, PASSWORD = "ada", "made-up-password-3310"
CLIENT_ID, CLIENT_SECRET = "made-up-client", "made-up-client-secret-7740"
TENANT = "made-up-tenant"
JWT_SECRET = "made-up-jwt-secret-1188"
AWS_KEY_ID, AWS_SECRET = "AKIDMADEUP0001", "made-up-aws-secret-4471"
FIREBASE_WEB_KEY = "made-up-web-key-2290"
EMAIL = "ada@example.com"
SECRETS = (API_KEY, BEARER, PASSWORD, CLIENT_SECRET, JWT_SECRET, AWS_SECRET)

ORDERS = [
    {"order_id": n, "amount": round(n * 2.5, 2), "status": "shipped" if n % 3 == 0 else "open"}
    for n in range(1, 26)
]
CLIENTS = [
    {"client": c, "city": t} for c, t in (("Ada", "Springfield"), ("Grace", "Riverton"), ("Alan", "Lakeside"))
]
REGIONS = [{"region": r} for r in ("North", "South", "East", "West", "Centre", "Coast", "Hills")]
PRODUCTS = [{"sku": "A-1", "price": 3.5}, {"sku": "B-2", "price": 9.0}]


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sigv4_signature(
    method: str, raw_path: str, headers: dict[str, str], body: bytes, signed: str, scope: str
) -> str:
    """AWS Signature Version 4, worked out again from the request as the service received it."""
    path, _, query = raw_path.partition("?")
    pairs = sorted(parse_qsl(query, keep_blank_values=True))
    canonical_query = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in pairs)
    names = signed.split(";")
    canonical_headers = "".join(f"{n}:{' '.join(headers[n].split())}\n" for n in names)
    canonical = "\n".join(
        [
            method,
            quote(path, safe="/-_.~"),
            canonical_query,
            canonical_headers,
            signed,
            hashlib.sha256(body).hexdigest(),
        ]
    )
    day, region, service, _ = scope.split("/")
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", headers["x-amz-date"], scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    key = ("AWS4" + AWS_SECRET).encode()
    for part in (day, region, service, "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()


class Service:
    """The API and its sign-in services on a free port of 127.0.0.1. `mode` is the auth it asks for:
    none, api_key_header, api_key_query, api_key_cookie, bearer, basic, oauth2, jwt_token, jwt_login,
    jwt_signed, sigv4, google, firebase."""

    def __init__(self, mode: str = "none") -> None:
        self.mode = mode
        self.key_name = "X-Api-Key"
        self.public_key: Any = None  # a signed JWT's (RS256, ES256) or Google's service account key's
        self.counter = itertools.count(1)
        self.tokens: dict[str, int] = {}  # a token handed out -> the requests it is good for
        self.codes: dict[str, str] = {}  # an authorization code -> its PKCE challenge
        self.device_polls = 0
        self.flaky = 0
        self.seen: list[dict[str, Any]] = []  # each API request: path and headers (the tests look)
        self.logins = 0
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> Service:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)

    def issue(self, prefix: str, uses: int = 1_000) -> str:
        token = f"{prefix}-{next(self.counter)}"
        self.tokens[token] = uses
        return token

    # ===== the documents =====

    def openapi(self) -> dict[str, Any]:
        order = {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer"},
                "amount": {"type": "number"},
                "status": {"type": "string", "enum": ["open", "shipped"]},
            },
        }
        listed = {"type": "array", "items": {"$ref": "#/components/schemas/Order"}}
        return {
            "openapi": "3.0.3",
            "info": {"title": "Orders", "version": "1.0", "description": "A made-up orders service."},
            "servers": [{"url": "/v1"}],
            "components": {
                "schemas": {"Order": order},
                "securitySchemes": {
                    "functionKey": {"type": "apiKey", "in": "header", "name": "x-functions-key"}
                },
            },
            "security": [{"functionKey": []}],
            "paths": {
                "/orders": {
                    "get": {
                        "operationId": "listOrders",
                        "summary": "The orders",
                        "tags": ["sales"],
                        "parameters": [
                            {"name": "status", "in": "query", "schema": {"type": "string"}},
                            {"name": "pageToken", "in": "query", "schema": {"type": "string"}},
                        ],
                        "responses": {
                            "200": {
                                "description": "A page",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {"items": listed, "nextToken": {"type": "string"}},
                                        }
                                    }
                                },
                            }
                        },
                    },
                    "post": {
                        "operationId": "createOrder",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/Order"}}
                            },
                        },
                        "responses": {
                            "201": {"description": "Made", "content": {"application/json": {"schema": order}}}
                        },
                    },
                },
                "/orders/{order_id}": {
                    "get": {
                        "operationId": "getOrder",
                        "parameters": [
                            {
                                "name": "order_id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "integer"},
                            }
                        ],
                        "responses": {
                            "200": {"description": "One", "content": {"application/json": {"schema": order}}}
                        },
                    }
                },
                "/clients": {
                    "get": {
                        "operationId": "listClients",
                        "tags": ["sales"],
                        "parameters": [{"name": "cursor", "in": "query", "schema": {"type": "string"}}],
                        "responses": {
                            "200": {
                                "description": "A page",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "client": {"type": "string"},
                                                    "city": {"type": "string"},
                                                },
                                            },
                                        }
                                    }
                                },
                            }
                        },
                    }
                },
                "/regions": {
                    "get": {
                        "operationId": "listRegions",
                        "parameters": [{"name": "page", "in": "query", "schema": {"type": "integer"}}],
                        "responses": {
                            "200": {
                                "description": "A page",
                                "content": {
                                    "application/json": {
                                        "schema": {"type": "array", "items": {"type": "object"}}
                                    }
                                },
                            }
                        },
                    }
                },
            },
        }

    def swagger(self) -> dict[str, Any]:
        return {
            "swagger": "2.0",
            "info": {"title": "Orders Two", "version": "2.0"},
            "host": self.url.removeprefix("http://"),
            "basePath": "/v1",
            "schemes": ["http"],
            "securityDefinitions": {"basicAuth": {"type": "basic"}},
            "security": [{"basicAuth": []}],
            "definitions": {
                "Order": {
                    "type": "object",
                    "properties": {"order_id": {"type": "integer"}, "amount": {"type": "number"}},
                }
            },
            "paths": {
                "/orders": {
                    "get": {
                        "operationId": "listOrders",
                        "parameters": [{"name": "pageToken", "in": "query", "type": "string"}],
                        "responses": {
                            "200": {
                                "description": "A page",
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "items": {"type": "array", "items": {"$ref": "#/definitions/Order"}},
                                        "nextToken": {"type": "string"},
                                    },
                                },
                            }
                        },
                    },
                    "post": {
                        "operationId": "createOrder",
                        "parameters": [
                            {
                                "name": "order",
                                "in": "body",
                                "required": True,
                                "schema": {"$ref": "#/definitions/Order"},
                            }
                        ],
                        "responses": {
                            "201": {"description": "Made", "schema": {"$ref": "#/definitions/Order"}}
                        },
                    },
                },
                "/orders/{order_id}": {
                    "get": {
                        "operationId": "getOrder",
                        "parameters": [
                            {"name": "order_id", "in": "path", "required": True, "type": "integer"}
                        ],
                        "responses": {
                            "200": {"description": "One", "schema": {"$ref": "#/definitions/Order"}}
                        },
                    }
                },
            },
        }

    # ===== who may ask =====

    def authorized(self, method: str, raw_path: str, headers: dict[str, str], body: bytes) -> bool:
        mode, auth = self.mode, headers.get("authorization", "")
        query = parse_qs(urlsplit(raw_path).query)
        if mode == "none":
            return True
        if mode == "api_key_header":
            return headers.get(self.key_name.lower()) == API_KEY
        if mode == "api_key_query":
            return query.get(self.key_name) == [API_KEY]
        if mode == "api_key_cookie":
            return f"{self.key_name}={API_KEY}" in headers.get("cookie", "")
        if mode == "basic":
            return auth == "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
        if mode in ("bearer", "jwt_token"):
            return auth == f"Bearer {BEARER}"
        if mode in ("oauth2", "jwt_login", "google", "firebase"):
            token = auth.removeprefix("Bearer ")
            if self.tokens.get(token, 0) <= 0:
                return False
            self.tokens[token] -= 1
            return True
        if mode == "jwt_signed":
            return self._jwt_ok(auth.removeprefix("Bearer "))
        if mode == "sigv4":
            parts = dict(p.strip().split("=", 1) for p in auth.removeprefix("AWS4-HMAC-SHA256 ").split(","))
            key_id, _, scope = parts.get("Credential", "").partition("/")
            if key_id != AWS_KEY_ID:
                return False
            expected = sigv4_signature(method, raw_path, headers, body, parts["SignedHeaders"], scope)
            return hmac.compare_digest(expected, parts.get("Signature", ""))
        return False

    def _jwt_ok(self, token: str) -> bool:
        try:
            head, claims, signature = token.split(".")
            header = json.loads(_unb64(head))
            said = json.loads(_unb64(claims))
        except ValueError:
            return False
        signing = f"{head}.{claims}".encode()
        if header["alg"] == "HS256":
            ok = hmac.compare_digest(
                _unb64(signature), hmac.new(JWT_SECRET.encode(), signing, hashlib.sha256).digest()
            )
        else:
            ok = self._verify(header["alg"], signing, _unb64(signature))
        return ok and said.get("exp", 0) > time.time() and said.get("iss") == "made-up-issuer"

    def _verify(self, alg: str, signing: bytes, signature: bytes) -> bool:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, padding, utils

        try:
            if alg == "RS256":
                self.public_key.verify(signature, signing, padding.PKCS1v15(), hashes.SHA256())
            else:
                r, s = int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
                self.public_key.verify(utils.encode_dss_signature(r, s), signing, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature:
            return False
        return True

    # ===== the sign-in services =====

    def oauth_token(self, form: dict[str, str]) -> tuple[int, Any]:
        grant = form.get("grant_type")
        if grant == "client_credentials":
            if (form.get("client_id"), form.get("client_secret")) != (CLIENT_ID, CLIENT_SECRET):
                return 401, {"error": "invalid_client"}
            return 200, {"access_token": self.issue("at"), "expires_in": 3600, "token_type": "Bearer"}
        if grant == "authorization_code":
            challenge = self.codes.pop(form.get("code", ""), None)
            verifier = form.get("code_verifier", "")
            if challenge is None or _b64(hashlib.sha256(verifier.encode()).digest()) != challenge:
                return 400, {"error": "invalid_grant"}
            return 200, {
                "access_token": self.issue("at"),
                "refresh_token": self.issue("rt"),
                "expires_in": 3600,
            }
        if grant == "refresh_token":
            if self.tokens.get(form.get("refresh_token", ""), 0) <= 0:
                return 400, {"error": "invalid_grant"}
            return 200, {"access_token": self.issue("at"), "expires_in": 3600}
        if grant == "urn:ietf:params:oauth:grant-type:device_code":
            self.device_polls += 1
            if self.device_polls < 2:
                return 400, {"error": "authorization_pending"}
            return 200, {
                "access_token": self.issue("at"),
                "refresh_token": self.issue("rt"),
                "expires_in": 3600,
            }
        if grant == "urn:ietf:params:oauth:grant-type:jwt-bearer":  # Google's token endpoint
            head, claims, signature = form.get("assertion", "..").split(".")
            said = json.loads(_unb64(claims))
            if not self._verify("RS256", f"{head}.{claims}".encode(), _unb64(signature)):
                return 400, {"error": "invalid_grant"}
            if said.get("aud") != self.url + "/google/token" or said.get("target_audience") != self.url:
                return 400, {"error": "invalid_audience"}
            return 200, {"id_token": self.issue("gid")}
        return 400, {"error": "unsupported_grant_type"}

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
                raw = json.dumps(body).encode() if body is not None else b""
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

            def _body(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def do_GET(self) -> None:
                self._route("GET", b"")

            def do_POST(self) -> None:
                self._route("POST", self._body())

            def _route(self, method: str, body: bytes) -> None:
                url = urlsplit(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                headers = {k.lower(): v for k, v in self.headers.items()}
                path = url.path
                if path == "/openapi.json":
                    return self._answer(200, service.openapi())
                if path == "/swagger.json":
                    return self._answer(200, service.swagger())
                if (path.startswith("/oauth/") and path.endswith("/token")) or path == "/google/token":
                    status, answer = service.oauth_token(dict(parse_qsl(body.decode())))
                    return self._answer(status, answer)
                if path == "/oauth/authorize":
                    code = f"code-{next(service.counter)}"
                    service.codes[code] = query["code_challenge"]
                    target = query["redirect_uri"] + "?" + urlencode({"code": code, "state": query["state"]})
                    self.send_response(302)
                    self.send_header("Location", target)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                if path == "/oauth/device":
                    return self._answer(
                        200,
                        {
                            "device_code": "dc-1",
                            "user_code": "MADE-UP",
                            "verification_uri": service.url + "/device",
                            "interval": 0,
                            "expires_in": 60,
                        },
                    )
                if path == "/firebase/signin":
                    sent = json.loads(body or b"{}")
                    if query.get("key") != FIREBASE_WEB_KEY or (sent.get("email"), sent.get("password")) != (
                        EMAIL,
                        PASSWORD,
                    ):
                        return self._answer(400, {"error": {"message": "INVALID_PASSWORD"}})
                    service.logins += 1
                    return self._answer(
                        200,
                        {
                            "idToken": service.issue("fid", 2),
                            "refreshToken": service.issue("frt"),
                            "expiresIn": "3600",
                        },
                    )
                if path == "/firebase/refresh":
                    form = dict(parse_qsl(body.decode()))
                    if (
                        query.get("key") != FIREBASE_WEB_KEY
                        or service.tokens.get(form.get("refresh_token", ""), 0) <= 0
                    ):
                        return self._answer(400, {"error": {"message": "INVALID_REFRESH_TOKEN"}})
                    return self._answer(
                        200,
                        {
                            "id_token": service.issue("fid", 2),
                            "refresh_token": form["refresh_token"],
                            "expires_in": "3600",
                        },
                    )
                if path == "/v1/login":
                    sent = json.loads(body or b"{}")
                    if (sent.get("username"), sent.get("password")) != (USER, PASSWORD):
                        return self._answer(401, {"error": "bad login"})
                    service.logins += 1
                    return self._answer(200, {"token": service.issue("jwt", 2)})
                service.seen.append({"method": method, "path": self.path, "headers": headers})
                if not service.authorized(method, self.path, headers, body):
                    return self._answer(401, {"error": "Not signed in"})
                return self._api(method, path, query, body)

            def _api(self, method: str, path: str, query: dict[str, str], body: bytes) -> None:
                if path == "/v1/orders" and method == "GET":
                    rows = [o for o in ORDERS if not query.get("status") or o["status"] == query["status"]]
                    start = int(query.get("pageToken", "p0")[1:]) * 10
                    page = rows[start : start + 10]
                    more = {"nextToken": f"p{start // 10 + 1}"} if start + 10 < len(rows) else {}
                    return self._answer(200, {"items": page, **more})
                if path == "/v1/orders" and method == "POST":
                    return self._answer(201, {"order_id": 1000, **json.loads(body or b"{}")})
                if path.startswith("/v1/orders/"):
                    found = [o for o in ORDERS if str(o["order_id"]) == path.rsplit("/", 1)[1]]
                    return (
                        self._answer(200, found[0])
                        if found
                        else self._answer(404, {"error": "No such order"})
                    )
                if path == "/v1/clients":
                    at = int(query.get("cursor", "0"))
                    clients: Any = CLIENTS[at : at + 2]
                    link = (
                        {"Link": f'</v1/clients?cursor={at + 2}>; rel="next"'}
                        if at + 2 < len(CLIENTS)
                        else {}
                    )
                    return self._answer(200, clients, link)
                if path == "/v1/regions":
                    at = (int(query.get("page", "1")) - 1) * 3
                    return self._answer(200, REGIONS[at : at + 3])
                if path == "/v1/products":
                    return self._answer(200, PRODUCTS)
                if path == "/v1/flaky":
                    service.flaky += 1
                    if service.flaky == 1:
                        return self._answer(503, {"error": "busy"}, {"Retry-After": "0"})
                    return self._answer(200, [{"ok": True}])
                return self._answer(404, {"error": "No such path"})

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler
