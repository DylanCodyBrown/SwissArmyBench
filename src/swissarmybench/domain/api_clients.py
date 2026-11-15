"""Add API's made file (docs/ideas.md, "Add API"): `API_<name>.py`, the API as a ready-to-call client.

  write      the file's text from a spec (domain/apis.py): one class, standard library only, so the same
             file runs in a plain Python, a notebook and an Azure Function. One typed, documented method
             per operation; retries (429 and 5xx, Retry-After); paging (a next link in the answer or its
             Link header, a page token, a page number or an offset); array answers as DataFrames when
             pandas is there, else lists of dicts; the auth type's own signing; `tables()` and `read()`
             for the connection. Secrets come in as arguments, else from environment variables, and are
             never written in it
  mark       the file's second line says it was made from the spec (and how), so re-import knows it is
             its own to write again, and what changed
  methods    a made file's methods, as re-import compares them (read with ast)
  inline     the file as code pasted into a script or notebook (the exporter: an API_<name>.py beside a
             notebook travels inside it), `import API_<name>` still working

Everything the spec says goes into the file as a Python literal (repr) or a checked name, so a spec can
never write code. Standard library only; no I/O.
"""

from __future__ import annotations

import ast
import json
import re
import textwrap
from collections.abc import Iterable
from typing import Any

from swissarmybench.domain.apis import (
    AUTH_TYPES,
    Auth,
    Names,
    Operation,
    Spec,
    placeholders,
    schema_of,
    url_variable,
    variables,
)

MARK: str = "# swissarmybench-api: "
FIRST_LINE: str = "# Made by Swiss Army Bench's Add API from the API's spec."
MARK_VERSION: int = 1
_PY = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
}


def _doc(text: str) -> str:
    """Spec text safe inside a triple-quoted docstring: no backslash escapes, no closing quotes."""
    clean = "".join(ch for ch in text if ch.isprintable() or ch == " ")
    return clean.replace("\\", "\\\\").replace('"""', '\\"\\"\\"').strip()


def _wrapped(text: str, indent: str, width: int = 100) -> list[str]:
    if not text:
        return []
    return textwrap.wrap(_doc(text), width - len(indent), initial_indent=indent, subsequent_indent=indent)


# ===== the auth types' own code (each a few methods of the class) =====

_IMPORTS_BASE = ("json", "os", "time", "urllib.error", "urllib.parse", "urllib.request")
_AUTH_IMPORTS: dict[str, tuple[str, ...]] = {
    "basic": ("base64",),
    "oauth2": ("base64", "hashlib", "http.server", "secrets", "sys", "webbrowser"),
    "jwt": ("base64", "hashlib", "hmac"),
    "sigv4": ("datetime", "hashlib", "hmac"),
    "google": ("base64", "hashlib", "hmac"),
}

_NONE = """
    def _start(self) -> None:
        pass

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        return url

    def _refresh(self) -> bool:
        return False
"""

_API_KEY = '''
    def _start(self) -> None:
        pass

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        """The API key, in the header, query parameter or cookie the API reads it from."""
        where, name = self._AUTH["in"], self._AUTH["name"]
        if where == "header":
            headers[name] = self._api_key
        elif where == "cookie":
            headers["Cookie"] = "; ".join(filter(None, [headers.get("Cookie"), name + "=" + self._api_key]))
        elif name + "=" not in url:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({name: self._api_key})
        return url

    def _refresh(self) -> bool:
        return False
'''

_BEARER = """
    def _start(self) -> None:
        pass

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        headers["Authorization"] = "Bearer " + self._token
        return url

    def _refresh(self) -> bool:
        return False
"""

_BASIC = """
    def _start(self) -> None:
        pass

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        pair = (self._username + ":" + self._password).encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(pair).decode("ascii")
        return url

    def _refresh(self) -> bool:
        return False
"""

_OAUTH2 = '''
    def _start(self) -> None:
        self._access: Optional[Tuple[str, float]] = None  # the token, and when it runs out
        self._refresh_token: Optional[str] = None

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        headers["Authorization"] = "Bearer " + self._access_token()
        return url

    def _refresh(self) -> bool:
        """A 401: the cached token is dropped and a new one asked for, once."""
        self._access = None
        return True

    def _endpoint(self, key: str) -> str:
        url = self._AUTH.get(key, "")
        for word, value in self._words.items():
            url = url.replace("{" + word + "}", urllib.parse.quote(value or "", safe=""))
        return url

    def _access_token(self) -> str:
        """The access token, cached until a minute before it runs out."""
        if self._access and self._access[1] > time.time() + 60:
            return self._access[0]
        flow = self._AUTH["flow"]
        if flow == "client_credentials":
            answer = self._token_request({"grant_type": "client_credentials"})
        else:
            answer = None
            kept = self._refresh_token or self._kept()
            if kept:
                try:
                    answer = self._token_request({"grant_type": "refresh_token", "refresh_token": kept})
                except self.Error:
                    answer = None  # expired or revoked: sign in again
            if answer is None:
                answer = self._browser() if flow == "authorization_code" else self._device()
            if answer.get("refresh_token"):
                self._keep(str(answer["refresh_token"]))
        if not answer.get("access_token"):
            raise self.Error(401, "POST", self._endpoint("token_url"), b"The sign-in gave no access token")
        self._access = (str(answer["access_token"]), time.time() + float(answer.get("expires_in") or 3600))
        return self._access[0]

    def _token_request(self, fields: Dict[str, str]) -> Dict[str, Any]:
        sent = dict(fields, client_id=self._client_id or "")
        if self._client_secret:
            sent["client_secret"] = self._client_secret
        if self._AUTH.get("scopes") and fields.get("grant_type") != "refresh_token":
            sent["scope"] = self._AUTH["scopes"]
        return self._auth_post(self._endpoint("token_url"), sent)

    def _kept(self) -> Optional[str]:
        """The refresh token saved in the system keyring by an earlier sign-in (when keyring is here)."""
        try:
            import keyring  # optional: without it the refresh token lasts as long as this Python

            return keyring.get_password("swissarmybench-api", self._keyring_user())
        except Exception:
            return None

    def _keyring_user(self) -> str:
        return self._KEYRING_NAME + ":" + (self._client_id or "")

    def _keep(self, token: str) -> None:
        self._refresh_token = token
        try:
            import keyring

            keyring.set_password("swissarmybench-api", self._keyring_user(), token)
        except Exception:
            pass

    def _open_browser(self, url: str) -> None:
        webbrowser.open(url)

    def _browser(self) -> Dict[str, Any]:
        """Authorization code with PKCE: the sign-in page in the browser, the code back on 127.0.0.1."""
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        got: Dict[str, str] = {}

        class Back(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                got.update({k: v[0] for k, v in query.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<p>Signed in. This window can be closed.</p>")

            def log_message(self, *args: Any) -> None:
                pass

        server = http.server.HTTPServer(("127.0.0.1", int(self._AUTH.get("redirect_port") or 0)), Back)
        server.timeout = 1
        redirect = "http://127.0.0.1:" + str(server.server_address[1]) + "/"
        address = self._endpoint("authorize_url")
        asked = {
            "response_type": "code",
            "client_id": self._client_id or "",
            "redirect_uri": redirect,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if self._AUTH.get("scopes"):
            asked["scope"] = self._AUTH["scopes"]
        try:
            self._open_browser(address + ("&" if "?" in address else "?") + urllib.parse.urlencode(asked))
            deadline = time.time() + 300
            while "code" not in got and "error" not in got and time.time() < deadline:
                server.handle_request()
        finally:
            server.server_close()
        if got.get("state") != state or "code" not in got:
            why = got.get("error_description") or got.get("error") or "The sign-in did not finish"
            raise self.Error(401, "GET", address, why.encode())
        return self._token_request(
            {
                "grant_type": "authorization_code",
                "code": got["code"],
                "redirect_uri": redirect,
                "code_verifier": verifier,
            }
        )

    def _device(self) -> Dict[str, Any]:
        """Device code: a code to enter on another device's browser, then the token when it is done."""
        asked = {"client_id": self._client_id or ""}
        if self._AUTH.get("scopes"):
            asked["scope"] = self._AUTH["scopes"]
        start = self._auth_post(self._endpoint("device_url"), asked)
        where = start.get("verification_uri_complete") or start.get("verification_uri")
        code = str(start.get("user_code"))
        said = start.get("message") or "Sign in at " + str(where) + " with the code " + code
        print(said, file=sys.stderr, flush=True)
        interval = float(start.get("interval") or 5)
        deadline = time.time() + float(start.get("expires_in") or 900)
        while time.time() < deadline:
            time.sleep(interval)
            try:
                grant = "urn:ietf:params:oauth:grant-type:device_code"
                return self._token_request({"grant_type": grant, "device_code": str(start["device_code"])})
            except self.Error as error:
                if "authorization_pending" in error.text:
                    continue
                if "slow_down" in error.text:
                    interval += 5
                    continue
                raise
        raise self.Error(401, "POST", self._endpoint("device_url"), b"The device code ran out")
'''

_JWT_ENCODE = '''
    @staticmethod
    def _jwt_encode(header: Dict[str, Any], claims: Dict[str, Any], key: str) -> str:
        """A JWT: HS256 with the standard library; RS256 and ES256 with the cryptography package."""

        def b64(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        parts = [b64(json.dumps(part, separators=(",", ":")).encode()) for part in (header, claims)]
        signing = parts[0] + "." + parts[1]
        algorithm = header["alg"]
        if algorithm == "HS256":
            return signing + "." + b64(hmac.new(key.encode(), signing.encode(), hashlib.sha256).digest())
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec, padding, utils
        except ImportError:
            needs = " needs the cryptography package in this Python (pip install cryptography)."
            raise RuntimeError(algorithm + needs) from None
        private: Any = serialization.load_pem_private_key(key.replace("\\\\n", "\\n").encode(), password=None)
        if algorithm == "RS256":
            signature = private.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
        else:
            r, s = utils.decode_dss_signature(private.sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
            signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return signing + "." + b64(signature)
'''

_JWT_TOKEN = _BEARER

_JWT_LOGIN = '''
    def _start(self) -> None:
        self._jwt: Optional[str] = None

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        headers["Authorization"] = "Bearer " + self._login()
        return url

    def _refresh(self) -> bool:
        """A 401: log in again, once."""
        self._jwt = None
        return True

    def _login(self) -> str:
        """The token the API's own login endpoint gives for the user name and password."""
        if self._jwt is None:
            url = self._AUTH["login_url"]
            url = url if url.startswith(("http://", "https://")) else self.base_url + "/" + url.lstrip("/")
            sent = {"username": self._username, "password": self._password}
            answer = self._auth_post(url, sent, as_json=True)
            named = self._AUTH.get("token_field")
            usual = ["token", "access_token", "id_token", "jwt", "accessToken", "idToken"]
            words = [named] if named else usual
            token = next((answer[w] for w in words if isinstance(answer.get(w), str)), None)
            if not token:
                raise self.Error(401, "POST", url, b"The login answered no token")
            self._jwt = token
        return self._jwt
'''

_JWT_SIGNED = '''
    def _start(self) -> None:
        self._jwt: Optional[Tuple[str, float]] = None

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        headers["Authorization"] = "Bearer " + self._signed()
        return url

    def _refresh(self) -> bool:
        self._jwt = None
        return True

    def _signed(self) -> str:
        """A JWT signed here, made again a minute before it runs out."""
        if self._jwt and self._jwt[1] > time.time() + 60:
            return self._jwt[0]
        now = int(time.time())
        life = int(self._AUTH.get("lifetime") or 3600)
        claims: Dict[str, Any] = {"iat": now, "nbf": now, "exp": now + life}
        for setting, claim in (("issuer", "iss"), ("subject", "sub"), ("audience", "aud")):
            if self._AUTH.get(setting):
                claims[claim] = self._AUTH[setting]
        header = {"alg": self._AUTH.get("algorithm") or "HS256", "typ": "JWT"}
        if self._AUTH.get("key_id"):
            header["kid"] = self._AUTH["key_id"]
        key = self._jwt_secret if header["alg"] == "HS256" else self._private_key
        self._jwt = (self._jwt_encode(header, claims, key), now + life)
        return self._jwt[0]
'''

_SIGV4 = '''
    def _start(self) -> None:
        pass

    def _refresh(self) -> bool:
        return False

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        return self._sigv4(method, url, headers, data)

    def _sigv4(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        data: Optional[bytes],
        now: Optional[datetime.datetime] = None,
        service: Optional[str] = None,
    ) -> str:
        """AWS Signature Version 4, with the standard library: Lambda function URLs and API Gateway."""
        parts = urllib.parse.urlsplit(url)
        host = parts.netloc
        named = "lambda" if ".lambda-url." in host else "execute-api"
        service = service or self._AUTH.get("service") or named
        region = self._AUTH.get("region") or os.environ.get("AWS_REGION") or "us-east-1"
        moment = now or datetime.datetime.now(datetime.timezone.utc)
        stamp, day = moment.strftime("%Y%m%dT%H%M%SZ"), moment.strftime("%Y%m%d")
        headers["Host"] = host
        headers["X-Amz-Date"] = stamp
        if self._session_token:
            headers["X-Amz-Security-Token"] = self._session_token
        signed = {
            k.lower(): " ".join(str(v).split())
            for k, v in headers.items()
            if k.lower() in ("host", "content-type") or k.lower().startswith("x-amz-")
        }
        names = ";".join(sorted(signed))
        pairs = sorted(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
        quoted = [(urllib.parse.quote(k, safe="-_.~"), urllib.parse.quote(v, safe="-_.~")) for k, v in pairs]
        query = "&".join(k + "=" + v for k, v in quoted)
        canonical = "\\n".join(
            [
                method,
                urllib.parse.quote(parts.path or "/", safe="/-_.~"),
                query,
                "".join(k + ":" + signed[k] + "\\n" for k in sorted(signed)),
                names,
                hashlib.sha256(data or b"").hexdigest(),
            ]
        )
        scope = day + "/" + region + "/" + service + "/aws4_request"
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        to_sign = "\\n".join(["AWS4-HMAC-SHA256", stamp, scope, digest])
        key = ("AWS4" + self._secret_access_key).encode()
        for part in (day, region, service, "aws4_request"):
            key = hmac.new(key, part.encode(), hashlib.sha256).digest()
        signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
        credential = self._access_key_id + "/" + scope
        headers["Authorization"] = (
            "AWS4-HMAC-SHA256 Credential=" + credential + ", SignedHeaders=" + names
            + ", Signature=" + signature
        )
        return url
'''

_GOOGLE = '''
    def _start(self) -> None:
        self._identity: Optional[Tuple[str, float]] = None

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        headers["Authorization"] = "Bearer " + self._identity_token()
        return url

    def _refresh(self) -> bool:
        self._identity = None
        return True

    def _identity_token(self) -> str:
        """A Google identity token for this service, minted from the service account's key (RS256)."""
        if self._identity and self._identity[1] > time.time() + 60:
            return self._identity[0]
        account = json.loads(self._service_account_key)
        now = int(time.time())
        token_uri = account.get("token_uri") or "https://oauth2.googleapis.com/token"
        audience = self._AUTH.get("audience") or "/".join(self.base_url.split("/")[:3])
        claims = {
            "iss": account["client_email"],
            "sub": account["client_email"],
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
            "target_audience": audience,
        }
        header = {"alg": "RS256", "typ": "JWT"}
        if account.get("private_key_id"):
            header["kid"] = account["private_key_id"]
        assertion = self._jwt_encode(header, claims, account["private_key"])
        grant = "urn:ietf:params:oauth:grant-type:jwt-bearer"
        answer = self._auth_post(token_uri, {"grant_type": grant, "assertion": assertion})
        if not answer.get("id_token"):
            raise self.Error(401, "POST", token_uri, b"Google answered no identity token")
        self._identity = (str(answer["id_token"]), now + 3300.0)
        return self._identity[0]
'''

_FIREBASE_EMAIL = '''
    def _start(self) -> None:
        self._identity: Optional[Tuple[str, float]] = None
        self._refresh_token: Optional[str] = None

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        headers["Authorization"] = "Bearer " + self._id_token_now()
        return url

    def _refresh(self) -> bool:
        self._identity = None
        return True

    def _id_token_now(self) -> str:
        """A Firebase ID token: signed in with the email and password, then refreshed as it runs out."""
        if self._identity and self._identity[1] > time.time() + 60:
            return self._identity[0]
        key = "?key=" + urllib.parse.quote(self._firebase_api_key, safe="")
        answer: Dict[str, Any] = {}
        if self._refresh_token:
            try:
                asked = {"grant_type": "refresh_token", "refresh_token": self._refresh_token}
                got = self._auth_post(self._AUTH["refresh_url"] + key, asked)
                answer = {
                    "idToken": got.get("id_token"),
                    "refreshToken": got.get("refresh_token"),
                    "expiresIn": got.get("expires_in"),
                }
            except self.Error:
                answer = {}
        if not answer.get("idToken"):
            sent = {"email": self._email, "password": self._password, "returnSecureToken": True}
            answer = self._auth_post(self._AUTH["sign_in_url"] + key, sent, as_json=True)
        if not answer.get("idToken"):
            raise self.Error(401, "POST", self._AUTH["sign_in_url"], b"Firebase answered no ID token")
        self._refresh_token = answer.get("refreshToken") or self._refresh_token
        self._identity = (str(answer["idToken"]), time.time() + float(answer.get("expiresIn") or 3600))
        return self._identity[0]
'''

_FIREBASE_READY = """
    def _start(self) -> None:
        pass

    def _sign(self, method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> str:
        headers["Authorization"] = "Bearer " + self._id_token
        return url

    def _refresh(self) -> bool:
        return False
"""


def _auth_code(auth: Auth) -> str:
    kind = auth.type
    if kind == "api_key":
        return _API_KEY
    if kind == "bearer":
        return _BEARER
    if kind == "basic":
        return _BASIC
    if kind == "oauth2":
        return _OAUTH2
    if kind == "jwt":
        mode = auth.get("mode")
        body = {"token": _JWT_TOKEN, "login": _JWT_LOGIN}.get(mode, _JWT_SIGNED)
        return body + (_JWT_ENCODE if mode == "signed" else "")
    if kind == "sigv4":
        return _SIGV4
    if kind == "google":
        return _GOOGLE + _JWT_ENCODE
    if kind == "firebase":
        return _FIREBASE_READY if auth.get("mode") == "token" else _FIREBASE_EMAIL
    return _NONE


def _imports(auth: Auth) -> list[str]:
    wanted = set(_IMPORTS_BASE) | set(_AUTH_IMPORTS.get(auth.type, ()))
    if auth.type == "jwt" and auth.get("mode") != "signed":
        wanted -= {"base64", "hashlib", "hmac"}
    return [f"import {m}" for m in sorted(wanted)]


# ===== the runtime every client has: requests, retries, paging, tables =====

_RUNTIME = '''
    # ===== requests: retries, paging, tables =====

    _RETRY = (429, 500, 502, 503, 504)
    _IDEMPOTENT = ("GET", "HEAD", "PUT", "DELETE", "OPTIONS")
    _NEXT_LINKS = ("@odata.nextLink", "nextLink", "next_link", "next", "nextUrl", "next_url")
    _NEXT_TOKENS = (
        "nextToken",
        "next_token",
        "nextPageToken",
        "next_page_token",
        "nextCursor",
        "next_cursor",
        "cursor",
        "continuationToken",
        "continuation_token",
        "next",
    )
    _ROW_KEYS = ("value", "items", "data", "results", "records", "rows", "entries", "list")

    class Error(Exception):
        """An answer that is not a success: its status (0: the API could not be reached) and its text."""

        def __init__(self, status: int, method: str, url: str, text: bytes) -> None:
            self.status = status
            self.text = text.decode("utf-8", "replace")[:2000]
            where = url.split("?")[0]
            said = " ".join(self.text.split())[:300]
            what = " answered " + str(status) if status else " could not be reached"
            super().__init__(method + " " + where + what + (": " + said if said else ""))

    @staticmethod
    def _plain(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _url(
        self, path: str, params: Optional[Dict[str, Any]] = None, query: Optional[Dict[str, Any]] = None
    ) -> str:
        for name, value in (params or {}).items():
            path = path.replace("{" + name + "}", urllib.parse.quote(self._plain(value), safe=""))
        url = path if path.startswith(("http://", "https://")) else self.base_url + path
        pairs = []
        for name, value in (query or {}).items():
            if value is None:
                continue
            for one in value if isinstance(value, (list, tuple)) else [value]:
                pairs.append((name, self._plain(one)))
        if pairs:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(pairs)
        return url

    def _wait(self, retry_after: Optional[str], attempt: int) -> float:
        if retry_after and retry_after.strip().isdigit():
            return min(float(retry_after), 30.0)
        return min(self.backoff * 2 ** (attempt - 1), 30.0)

    def _send(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, Any]] = None,
        body: Any = None,
        form: bool = False,
        cookies: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """One request, signed, retried on 429 and 5xx (a POST only on 429), once more after a 401
        when the auth can sign in again."""
        data: Optional[bytes] = None
        sent = {"Accept": "application/json", "User-Agent": "swissarmybench-api/1"}
        sent.update({k: self._plain(v) for k, v in (headers or {}).items() if v is not None})
        if cookies:
            sent["Cookie"] = "; ".join(k + "=" + self._plain(v) for k, v in cookies.items() if v is not None)
        if body is not None:
            if form:
                data = urllib.parse.urlencode(body, doseq=True).encode()
                sent["Content-Type"] = "application/x-www-form-urlencoded"
            elif isinstance(body, (bytes, bytearray)):
                data = bytes(body)
            else:
                data = json.dumps(body, default=str).encode()
                sent["Content-Type"] = "application/json"
        attempt, signed_in_again = 0, False
        while True:
            signed = dict(sent)
            address = self._sign(method, url, signed, data)
            request = urllib.request.Request(address, data=data, method=method, headers=signed)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as answer:
                    return answer.status, {k.lower(): v for k, v in answer.headers.items()}, answer.read()
            except urllib.error.HTTPError as error:
                got = {k.lower(): v for k, v in (error.headers.items() if error.headers else [])}
                text = error.read()
                if error.code == 401 and not signed_in_again and self._refresh():
                    signed_in_again = True
                    continue
                again = method in self._IDEMPOTENT or error.code == 429
                if error.code in self._RETRY and attempt < self.retries and again:
                    attempt += 1
                    time.sleep(self._wait(got.get("retry-after"), attempt))
                    continue
                raise self.Error(error.code, method, url, text) from None
            except urllib.error.URLError as error:
                if attempt < self.retries and method in self._IDEMPOTENT:
                    attempt += 1
                    time.sleep(self._wait(None, attempt))
                    continue
                raise self.Error(0, method, url, str(error.reason).encode()) from None

    @staticmethod
    def _decoded(headers: Dict[str, str], raw: bytes) -> Any:
        if not raw:
            return None
        kind = headers.get("content-type", "")
        if "json" in kind or raw[:1] in (b"{", b"["):
            try:
                return json.loads(raw.decode("utf-8"))
            except ValueError:
                pass
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw

    def _call(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        cookies: Optional[Dict[str, Any]] = None,
        body: Any = None,
        form: bool = False,
    ) -> Any:
        status, got, raw = self._send(method, self._url(path, params, query), headers, body, form, cookies)
        return self._decoded(got, raw)

    def _auth_post(self, url: str, fields: Dict[str, Any], as_json: bool = False) -> Dict[str, Any]:
        """A sign-in request (not signed itself): its JSON answer."""
        data = json.dumps(fields).encode() if as_json else urllib.parse.urlencode(fields).encode()
        kind = "application/json" if as_json else "application/x-www-form-urlencoded"
        sent = {"Accept": "application/json", "Content-Type": kind}
        request = urllib.request.Request(url, data=data, method="POST", headers=sent)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:
                found = json.loads(answer.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            raise self.Error(error.code, "POST", url, error.read()) from None
        except urllib.error.URLError as error:
            raise self.Error(0, "POST", url, str(error.reason).encode()) from None
        return found if isinstance(found, dict) else {}

    def _rows_of(self, answer: Any, at: str) -> List[Any]:
        if at and isinstance(answer, dict):
            found = answer.get(at)
            return list(found) if isinstance(found, list) else []
        if isinstance(answer, list):
            return answer
        if isinstance(answer, dict):
            for key in self._ROW_KEYS:
                if isinstance(answer.get(key), list):
                    return list(answer[key])
            return [answer]
        return []

    def _next(
        self,
        url: str,
        headers: Dict[str, str],
        answer: Any,
        found: List[Any],
        first: int,
        path: str,
        params: Optional[Dict[str, Any]],
        query: Dict[str, Any],
        paging: Dict[str, str],
    ) -> Optional[str]:
        """The next page's address: a Link header's rel="next", a next link in the answer, or the
        operation's own page token, page number or offset."""
        for part in headers.get("link", "").split(","):
            if 'rel="next"' in part or "rel=next" in part:
                return urllib.parse.urljoin(url, part.split(";")[0].strip().strip("<>"))
        if isinstance(answer, dict):
            links = answer.get("links") or answer.get("_links") or answer.get("paging") or {}
            nested = links.get("next") if isinstance(links, dict) else None
            nested = nested.get("href") if isinstance(nested, dict) else nested
            for value in [answer.get(k) for k in self._NEXT_LINKS] + [nested]:
                if isinstance(value, str) and value.startswith(("http://", "https://", "/")):
                    return urllib.parse.urljoin(url, value)
        kind, name = next(iter(paging.items()), ("", ""))
        if kind == "token":
            given = answer if isinstance(answer, dict) else {}
            token = next((given[k] for k in self._NEXT_TOKENS if given.get(k)), None)
            if token is None or isinstance(token, (dict, list)):
                return None
            query[name] = token
            return self._url(path, params, query)
        if kind in ("page", "offset") and len(found) >= first:
            if kind == "page":
                query[name] = int(query.get(name) or 1) + 1
            else:
                query[name] = int(query.get(name) or 0) + len(found)
            return self._url(path, params, query)
        return None

    def _table(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        cookies: Optional[Dict[str, Any]] = None,
        at: str = "",
        paging: Optional[Dict[str, str]] = None,
        columns: Tuple[str, ...] = (),
        max_rows: Optional[int] = None,
    ) -> Any:
        """An operation's rows, page after page until there are no more (or `max_rows`)."""
        rows: List[Any] = []
        query = dict(query or {})
        url: Optional[str] = self._url(path, params, query)
        seen = set()
        first, pages = 0, 0
        while url and (max_rows is None or len(rows) < max_rows) and pages < self.max_pages:
            pages += 1
            status, got, raw = self._send("GET", url, headers, None, False, cookies)
            answer = self._decoded(got, raw)
            found = self._rows_of(answer, at)
            mark = json.dumps(found[:1], default=str, sort_keys=True) + "/" + str(len(found))
            if not found or mark in seen:  # the same page again: the API ignores the page asked for
                break
            seen.add(mark)
            first = first or len(found)
            rows.extend(found)
            url = self._next(url, got, answer, found, first, path, params, query, paging or {})
        return self._frame(rows if max_rows is None else rows[:max_rows], columns)

    @staticmethod
    def _frame(rows: List[Any], columns: Tuple[str, ...] = ()) -> Any:
        """Rows as a pandas DataFrame when pandas is installed, else the list of dicts as it came."""
        try:
            import pandas
        except ImportError:
            return rows
        if rows and not all(isinstance(r, dict) for r in rows):
            return pandas.DataFrame({"value": rows})
        if not rows:
            return pandas.DataFrame(columns=list(columns))
        return pandas.DataFrame.from_records(rows)

    @staticmethod
    def _kinds(rows: Any) -> List[Tuple[str, str]]:
        """A table's columns and their types, from rows it returned."""
        if hasattr(rows, "dtypes"):
            words = {"i": "integer", "u": "integer", "f": "number", "b": "boolean", "M": "timestamp"}
            return [(str(c), words.get(t.kind, "string")) for c, t in rows.dtypes.items()]
        first = rows[0] if rows and isinstance(rows[0], dict) else {}

        def kind(v: Any) -> str:
            if isinstance(v, bool):
                return "boolean"
            return "integer" if isinstance(v, int) else "number" if isinstance(v, float) else "string"

        return [(str(k), kind(v)) for k, v in first.items()]
'''

_CATALOG = '''
    # ===== the connection: the tables this API gives =====

    def tables(self) -> List[Dict[str, str]]:
        """Every table (each GET operation that returns rows and needs no arguments), one row per
        column: a connection's List the tables. A table whose columns the spec does not name is asked
        for one row."""
        found = []
        for table, (schema, method, columns) in self._TABLES.items():
            kinds = list(columns) or self._kinds(getattr(self, method)(max_rows=1))
            found += [{"schema": schema, "table": table, "column": c, "type": t} for c, t in kinds]
        return found

    def read(self, table: str, limit: Optional[int] = None) -> Any:
        """A table's rows (a connection's Read a table): at most `limit` (None: every row)."""
        if table not in self._TABLES:
            has = ", ".join(self._TABLES)
            name = self.__class__.__name__
            raise KeyError(name + " has no table " + repr(table) + ". It has: " + has + ".")
        return getattr(self, self._TABLES[table][1])(max_rows=limit)
'''


# ===== one method per operation =====


def _annotation(kind: str, required: bool) -> str:
    plain = _PY.get(kind, "Any")
    return plain if required else f"Optional[{plain}]"


def _method(op: Operation) -> list[str]:
    required = [p for p in op.parameters if p.required]
    optional = [p for p in op.parameters if not p.required]
    args = ["self"] + [f"{p.python}: {_annotation(p.type, True)}" for p in required]
    if op.body:
        args.append("body: Any" if op.body_required else "body: Any = None")
    args += [f"{p.python}: {_annotation(p.type, False)} = None" for p in optional]
    if op.table:
        args += ["*", "max_rows: Optional[int] = None"]
    one_line = f"    def {op.name}({', '.join(args)}) -> Any:"
    lines = (
        [one_line]
        if len(one_line) <= 110
        else [f"    def {op.name}(", *(f"        {a}," for a in args), "    ) -> Any:"]
    )
    doc = ['        """' + (_doc(op.summary) or f"{op.method} {op.path}")]
    if op.summary:
        doc += ["", f"        {op.method} {_doc(op.path)}"]
    if op.description and op.description != op.summary:
        doc += ["", *_wrapped(op.description, "        ")]
    if op.deprecated:
        doc += ["", "        Deprecated by the API."]
    described = [*required, *optional]
    if described or op.body or op.table:
        doc += ["", "        Args:"]
        for p in described:
            words = p.description or f"The {p.place} parameter {p.name}."
            if p.enum:
                words += " One of: " + ", ".join(p.enum) + "."
            if p.python != p.name:
                words = f"({p.name}) " + words
            lines_of = _wrapped(f"{p.python}: {words}", "            ")
            doc += lines_of
        if op.body:
            doc += _wrapped(
                f"body: {op.body_description or 'The request body'} "
                f"({'JSON' if op.body == 'json' else 'a form'}).",
                "            ",
            )
        if op.table:
            doc += ["            max_rows: At most this many rows, page after page (None: every row)."]
    doc += ["", "        Returns:"]
    doc += [
        "            The rows: a pandas DataFrame when pandas is installed, else a list of dicts."
        if op.table
        else f"            The answer ({op.returns or 'JSON'}), decoded from JSON when it is JSON."
    ]
    doc += ['        """']
    lines += doc

    def mapping(place: str) -> str | None:
        found = [p for p in op.parameters if p.place == place]
        if not found:
            return None
        return "{" + ", ".join(f"{_lit(p.name)}: {p.python}" for p in found) + "}"

    call: list[str] = [_lit(op.path)] if op.table else [_lit(op.method), _lit(op.path)]
    for place, word in (("path", "params"), ("query", "query"), ("header", "headers"), ("cookie", "cookies")):
        found = mapping(place)
        if found:
            call.append(f"{word}={found}")
    if op.table:
        if op.rows_at:
            call.append(f"at={_lit(op.rows_at)}")
        if op.paging():
            call.append(f"paging={_lit(op.paging())}")
        if op.columns:
            call.append(f"columns={_lit(tuple(c for c, _ in op.columns))}")
        call.append("max_rows=max_rows")
    elif op.body:
        call.append("body=body")
        if op.body == "form":
            call.append("form=True")
    function = "self._table" if op.table else "self._call"
    single = f"        return {function}({', '.join(call)})"
    if len(single) <= 110:
        lines.append(single)
    else:
        lines += [f"        return {function}(", *(f"            {c}," for c in call), "        )"]
    return lines


# ===== the file =====


def mark(spec: Spec, names: Names) -> dict[str, Any]:
    """What the made file's mark says: what it was made from and how (no secret: names and settings)."""
    return {
        "version": MARK_VERSION,
        "name": names.connection,
        "module": names.module,
        "class": names.cls,
        "source": spec.source,
        "api_version": spec.version,
        "base_url": spec.base_url,
        "auth": spec.auth.to_json(),
    }


def _lit(value: Any) -> str:
    """A value as a Python literal in the made file (strings in double quotes, every character escaped
    that could end one)."""
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, tuple):
        inner = ", ".join(_lit(v) for v in value)
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    if isinstance(value, list):
        return "[" + ", ".join(_lit(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_lit(k)}: {_lit(v)}" for k, v in value.items()) + "}"
    return repr(value)


def write(spec: Spec, names: Names) -> str:
    """API_<name>.py's text."""
    auth = spec.auth
    needs = variables(auth, names.prefix)
    words = placeholders(auth)
    secrets = ", ".join(v.name for v in needs) or "none"
    title = f"{spec.title}: its API as a Python client ({spec.source}"
    title += f", version {spec.version})." if spec.version else ")."
    head = [
        FIRST_LINE + " Do not edit it: Add API writes it",
        "# again when the spec changes, and your own code goes in your notebooks.",
        MARK + json.dumps(mark(spec, names), ensure_ascii=True, separators=(",", ":")),
        '"""' + _doc(title),
        "",
        *_wrapped(spec.description, ""),
        *([""] if spec.description else []),
        f"    from {names.module} import {names.cls}",
        "",
        f"    api = {names.cls}()  # its secrets from the environment",
    ]
    first = next((op for op in spec.operations if op.readable), None)
    if first is not None:
        head.append(f"    api.{first.name}()  # {first.method} {_doc(first.path)}: the rows")
    head += [
        "",
        "Standard library only. pandas, when it is installed, makes array answers DataFrames.",
        *(["RS256 and ES256 need the cryptography package."] if _signs_rsa(auth) else []),
        '"""',
        "",
        *_imports(auth),
        "from typing import Any, Dict, List, Optional, Tuple",
        "",
        "",
        f"class {names.cls}:",
        '    """'
        + _doc(spec.title)
        + (f" ({_doc(spec.version)})" if spec.version else "")
        + ": one method per operation.",
        "",
        *_wrapped(
            f"Secrets are arguments, else environment variables ({secrets}); "
            "they are never written in this file.",
            "    ",
        ),
        '    """',
        "",
        f"    BASE_URL = {_lit(spec.base_url)}",
        *_auth_lines(auth),
    ]
    if auth.type == "oauth2":
        head.append(f"    _KEYRING_NAME = {_lit(names.module)}")
    head.append("")
    # The constructor.
    args = ["self", "base_url: Optional[str] = None", "*"]
    args += [f"{v.argument}: Optional[str] = None" for v in needs]
    args += ["timeout: float = 30.0", "retries: int = 3", "backoff: float = 0.5"]
    url = _lit(url_variable(names.prefix))
    body = [
        "    def __init__(",
        *(f"        {a}," for a in args),
        "    ) -> None:",
        f'        """`base_url` (else {url_variable(names.prefix)}, else BASE_URL); each secret not given',
        "        is read from its environment variable. A request that fails with 429 or 5xx is tried",
        '        `retries` times more."""',
        f'        self.base_url = (base_url or os.environ.get({url}) or self.BASE_URL).rstrip("/")',
        "        self.timeout, self.retries, self.backoff, self.max_pages = timeout, retries, backoff, 1000",
    ]
    for v in needs:
        body.append(f"        self._{v.argument} = {v.argument} or os.environ.get({_lit(v.name)})")
    for v in needs:
        if v.required:
            body += [
                f"        if not self._{v.argument}:",
                f"            raise ValueError({_lit(f'Set {v.name}, or give {v.argument}=...')})",
            ]
    if auth.type == "oauth2":
        body.append(
            "        self._words = {"
            + ", ".join(f'{_lit(w)}: self._{arg} or ""' for w, arg in words.items())
            + "}"
        )
    body += [
        "        self._start()",
        "",
        "    def __repr__(self) -> str:",
        '        return self.__class__.__name__ + "(" + repr(self.base_url) + ")"',
        "",
        "    # ===== the operations =====",
    ]
    methods: list[str] = []
    for op in spec.operations:
        methods += ["", *_method(op)]
    catalog = ["", "    _TABLES: Dict[str, Tuple[str, str, Tuple[Tuple[str, str], ...]]] = {"]
    for name, op in spec.tables().items():
        entry = f"        {_lit(name)}: ({_lit(schema_of(op))}, {_lit(op.name)}, {_lit(tuple(op.columns))}),"
        if len(entry) > 110:
            entry = "\n".join(
                [
                    f"        {_lit(name)}: (",
                    f"            {_lit(schema_of(op))},",
                    f"            {_lit(op.name)},",
                    f"            {_lit(tuple(op.columns))},",
                    "        ),",
                ]
            )
        catalog.append(entry)
    catalog.append("    }")
    code = "\n".join([*head, *body, *methods, *catalog])
    signing = f"\n    # ===== signing in: {AUTH_TYPES[auth.type].label} =====\n"
    return (code + "\n" + _CATALOG + _RUNTIME + signing + _auth_code(auth)).rstrip() + "\n"


def _auth_lines(auth: Auth) -> list[str]:
    settings = _auth_settings(auth)
    one = f"    _AUTH: Dict[str, str] = {_lit(settings)}"
    if len(one) <= 110:
        return [one]
    return [
        "    _AUTH: Dict[str, str] = {",
        *(f"        {_lit(k)}: {_lit(v)}," for k, v in settings.items()),
        "    }",
    ]


def _signs_rsa(auth: Auth) -> bool:
    return auth.type == "google" or (
        auth.type == "jwt" and auth.get("mode") == "signed" and auth.get("algorithm") != "HS256"
    )


def _auth_settings(auth: Auth) -> dict[str, str]:
    """The auth's settings as the file keeps them: the ones its choices use, defaults filled in."""
    return {
        s.id: auth.get(s.id)
        for s in AUTH_TYPES[auth.type].settings
        if s.when is None or auth.get(s.when[0]) == s.when[1]
    }


# ===== reading a made file back: its mark, its methods =====


def read_mark(text: str) -> dict[str, Any] | None:
    """A made file's mark (None: not a file Add API made, so it is never written over)."""
    lines = text.splitlines()[:5]
    if not lines or not lines[0].startswith(FIRST_LINE):
        return None
    for line in lines[1:]:
        if line.startswith(MARK):
            try:
                found = json.loads(line[len(MARK) :])
            except ValueError:
                return None
            return found if isinstance(found, dict) else None
    return None


def methods(text: str) -> dict[str, str]:
    """A made file's operations: method name -> its signature and its METHOD path line, as re-import
    compares them. Code that does not parse has none."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    found: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if (
                isinstance(item, ast.FunctionDef)
                and not item.name.startswith("_")
                and item.name
                not in (
                    "tables",
                    "read",
                )
            ):
                doc = ast.get_docstring(item) or ""
                where = next((line for line in doc.splitlines() if re.match(r"^[A-Z]+ /", line)), doc[:80])
                found[item.name] = f"{ast.unparse(item.args)} | {where}"
        break
    return found


# ===== the exporter: a made file pasted inline =====


def is_made(text: str) -> bool:
    return read_mark(text) is not None


def imported(code: str) -> list[str]:
    """The API_ modules a notebook's or script's code imports (import API_Orders, from API_Orders
    import OrdersApi), in the order first imported. Code that does not parse has none."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        names: Iterable[str] = ()
        if isinstance(node, ast.Import):
            names = (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = (node.module,)
        for name in names:
            if name.startswith("API_") and name not in found:
                found.append(name)
    return found


def inline(module: str, text: str) -> str:
    """The made file as code inside an exported script or notebook: its own text (the docstring left
    out), then the lines that make `import API_Orders` and `from API_Orders import OrdersApi` find it
    without the file."""
    found = read_mark(text) or {}
    cls = str(found.get("class") or "")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    lines = text.splitlines()
    if tree is not None and tree.body and isinstance(tree.body[0], ast.Expr):
        doc = tree.body[0]
        end = doc.end_lineno or doc.lineno
        lines = [*lines[: doc.lineno - 1], *lines[end:]]
    if tree is not None and not cls:
        cls = next((n.name for n in tree.body if isinstance(n, ast.ClassDef)), "")
    shim = [
        "",
        "",
        f"# {module}.py travels inside this file: `import {module}` finds it here.",
        "import sys as _sys",
        "import types as _types",
        "",
        f"{module} = _types.ModuleType({_lit(module)})",
    ]
    if cls:
        shim.append(f"{module}.{cls} = {cls}")
    shim.append(f"_sys.modules[{_lit(module)}] = {module}")
    return "\n".join(line.rstrip() for line in [*lines, *shim]).strip() + "\n"
