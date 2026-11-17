# ruff: noqa: E501 (the connections' code is text, written as it runs; its lines are its own)
"""Stand-ins on this computer for the lake and SharePoint connections (domain/lakes.py, domain/sharepoint.py):
no real tenant, storage account or site is ever reached, and every value is made up.

One server answers what the connections ask, the way Microsoft documents it:

  POST /{tenant}/oauth2/v2.0/token        the sign-ins: client credentials, and the username and password
                                          (ROPC: a wrong password is AADSTS50126, an MFA account AADSTS50076)
  GET  /msi/token?resource=...            a managed identity's (IDENTITY_ENDPOINT, IDENTITY_HEADER)
  GET  /{account}/{filesystem}?resource=filesystem&recursive=...&directory=...&continuation=...
                                          the ADLS Gen2 listing (paged), over a made-up lake on disk
  GET, HEAD /{account}/{filesystem}/{path}   a file (Range requests too): a bearer token or a SAS signed
                                          with the made-up account key
  /graph/v1.0/...                         Microsoft Graph for a made-up SharePoint site: its lists (typed
                                          columns, lookups, people, paging, $filter on indexed columns),
                                          its document library (its file index, a workbook, a CSV...),
                                          uploads, and $batch (a 429 first, when asked)

The made-up lake (make_lake): a Data Lake account's container with a Delta table (two versions,
partitioned by region), a Parquet file, a CSV file and a hive-partitioned folder; a OneLake workspace's
lakehouse with two Delta tables (one with a checkpoint) and a CSV under Files/. The Delta logs are written
here by hand (no deltalake needed).

    python -m tests.lake_standins 8793        # run it by itself (the screenshots do)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import re
import sys
import threading
import time
import zipfile
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

import pyarrow as pa
import pyarrow.parquet as pq

TENANT = "made-up-tenant-2001"
CLIENT = "made-up-client-2002"
SECRET = "made-up-client-secret-2003"
TOKEN = "made-up-lake-token-2004"
IDENTITY_HEADER = "made-up-identity-header-2005"
USERNAME = "pat@made-up.example"
PASSWORD = "made-up-password-2006"
MFA_USERNAME = "mfa@made-up.example"
ACCOUNT = "madeupstore"
CONTAINER = "sales"
ACCOUNT_KEY = base64.b64encode(b"made-up-account-key-2007").decode()
WORKSPACE = "Made-up Workspace"
SITE_HOST = "madeup.sharepoint.com"
SITE_PATH = "/sites/team"
SITE_ID = "madeup.sharepoint.com,site-1,web-1"
PAGE = 7  # the listing's page (small, so continuation is used)
GRAPH_PAGE = 4  # Graph's page of list items (small, so @odata.nextLink is used)
NOT_TO_BE_SEEN = (SECRET, TOKEN, IDENTITY_HEADER, PASSWORD, ACCOUNT_KEY)

DAY = 86_400_000
FIRST = int(datetime(2026, 11, 1, 9, 0, tzinfo=UTC).timestamp() * 1000)

# ===== the made-up lake, on disk =====

ORDERS_V0 = [(1, 120.0, "North"), (2, 80.5, "North"), (3, 42.0, "South")]
ORDERS_V1 = [(4, 300.0, "South"), (5, 15.25, "West")]


def write_delta(table: Path, versions: list[list[tuple[int, float, str]]], checkpoint: bool = False) -> None:
    """A Delta table written by hand: partitioned by region, one commit per version (a day apart), an
    add per region; with `checkpoint`, a checkpoint at the last version (Parquet, as Delta writes it)."""
    log = table / "_delta_log"
    log.mkdir(parents=True)
    schema = {"type": "struct", "fields": [
        {"name": "order_id", "type": "long", "nullable": True, "metadata": {}},
        {"name": "amount", "type": "double", "nullable": True, "metadata": {}},
        {"name": "region", "type": "string", "nullable": True, "metadata": {}},
    ]}  # fmt: skip
    meta = {"metaData": {"id": "made-up", "format": {"provider": "parquet", "options": {}},
                         "schemaString": json.dumps(schema), "partitionColumns": ["region"],
                         "configuration": {}, "createdTime": FIRST}}  # fmt: skip
    protocol = {"protocol": {"minReaderVersion": 1, "minWriterVersion": 2}}
    adds: list[dict[str, Any]] = []
    for version, rows in enumerate(versions):
        actions: list[dict[str, Any]] = [protocol, meta] if version == 0 else []
        for region in sorted({r[2] for r in rows}):
            folder = table / f"region={region}"
            folder.mkdir(exist_ok=True)
            name = f"part-{version:05d}.parquet"
            mine = [r for r in rows if r[2] == region]
            pq.write_table(
                pa.table({"order_id": [r[0] for r in mine], "amount": [r[1] for r in mine]}), folder / name
            )
            add = {"path": f"region={region}/{name}", "partitionValues": {"region": region},
                   "size": (folder / name).stat().st_size, "modificationTime": FIRST, "dataChange": True}  # fmt: skip
            adds.append(add)
            actions.append({"add": add})
        actions.append({"commitInfo": {"timestamp": FIRST + version * DAY, "operation": "WRITE"}})
        (log / f"{version:020d}.json").write_text("\n".join(json.dumps(a) for a in actions) + "\n")
    if checkpoint:
        last = len(versions) - 1
        actions_at: list[dict[str, Any]] = [{"protocol": protocol["protocol"], "metaData": None, "add": None},
                {"protocol": None, "metaData": _flat(meta["metaData"]), "add": None}]  # fmt: skip
        actions_at += [{"protocol": None, "metaData": None, "add": a} for a in adds]
        pq.write_table(pa.Table.from_pylist(actions_at), log / f"{last:020d}.checkpoint.parquet")
        (log / "_last_checkpoint").write_text(json.dumps({"version": last, "size": len(actions_at)}))
        for v in range(last):  # older commits cleaned away: only the checkpoint says them
            (log / f"{v:020d}.json").unlink()


def _flat(meta: dict[str, Any]) -> dict[str, Any]:
    """metaData as a checkpoint holds it here (Parquet has no empty structs: the empty parts left out)."""
    return {
        "id": meta["id"],
        "format": {"provider": "parquet"},
        "schemaString": meta["schemaString"],
        "partitionColumns": meta["partitionColumns"],
        "createdTime": meta["createdTime"],
    }


def make_lake(root: Path) -> dict[str, Path]:
    """The made-up lake under `root` (the storage's own folder: <account>/<filesystem>/...)."""
    lake = root / ACCOUNT / CONTAINER / "lake"
    write_delta(lake / "orders", [ORDERS_V0, ORDERS_V1])
    pq.write_table(pa.table({"customer_id": [1, 2, 3], "name": ["Avery Made-up", "Blake Made-up", "Casey Made-up"]}),
                   lake / "customers.parquet")  # fmt: skip
    (lake / "returns.csv").write_text("order_id,reason\n2,damaged\n4,late\n", encoding="utf-8")
    for day, rows in (("2026-11-01", [1, 2]), ("2026-11-02", [3])):
        folder = lake / "events" / f"day={day}"
        folder.mkdir(parents=True)
        pq.write_table(pa.table({"event_id": rows}), folder / "part-0.parquet")
    (lake / "_tmp_ignored.csv").write_text("x\n1\n", encoding="utf-8")
    house = root / "onelake" / WORKSPACE / "Sales.Lakehouse"
    write_delta(house / "Tables" / "orders", [ORDERS_V0, ORDERS_V1], checkpoint=True)
    write_delta(house / "Tables" / "products", [[(10, 9.99, "North")]])
    (house / "Files" / "raw").mkdir(parents=True)
    (house / "Files" / "raw" / "regions.csv").write_text(
        "region,manager\nNorth,Avery\nSouth,Blake\n", encoding="utf-8"
    )
    return {"lake": lake, "house": house}


def verify_sas(query: dict[str, str]) -> bool:
    """A SAS signed with the made-up account key (the account SAS the connection signs)."""
    signed = "\n".join([ACCOUNT, query.get("sp", ""), query.get("ss", ""), query.get("srt", ""), "",
                        query.get("se", ""), "", query.get("spr", ""), query.get("sv", ""), "", ""])  # fmt: skip
    digest = hmac.new(base64.b64decode(ACCOUNT_KEY), signed.encode(), hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), query.get("sig", ""))


# ===== the made-up SharePoint site =====

PEOPLE = {11: "Avery Made-up", 12: "Blake Made-up", 13: "Casey Made-up"}
CUSTOMERS = {
    1: ("Northwind Made-up", "North"),
    2: ("Southside Made-up", "South"),
    3: ("Westway Made-up", "West"),
}


def _task(n: int) -> dict[str, Any]:
    return {
        "Title": f"Made-up task {n:02d}",
        "Status": ["Open", "Done", "Waiting"][n % 3],
        "Due": (datetime(2026, 11, 1, tzinfo=UTC) + timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Hours": float(n * 1.5),
        "Done": n % 3 == 1,
        "CustomerLookupId": str(n % 3 + 1),
        "AssignedToLookupId": str(11 + n % 3),
        "Notes": f"made-up note {n}",
    }


TASKS = {n: _task(n) for n in range(1, 11)}
TASK_COLUMNS = [
    {"name": "Title", "displayName": "Title", "indexed": True, "text": {}},
    {"name": "Status", "displayName": "Status", "indexed": True, "choice": {"choices": ["Open", "Done", "Waiting"]}},
    {"name": "Due", "displayName": "Due", "indexed": False, "dateTime": {}},
    {"name": "Hours", "displayName": "Hours", "indexed": False, "number": {}},
    {"name": "Done", "displayName": "Done", "indexed": False, "boolean": {}},
    {"name": "Customer", "displayName": "Customer", "indexed": False,
     "lookup": {"listId": "list-customers", "columnName": "Title"}},
    {"name": "AssignedTo", "displayName": "Assigned To", "indexed": False, "personOrGroup": {}},
    {"name": "Notes", "displayName": "Notes", "indexed": False, "text": {}},
    {"name": "ContentType", "displayName": "Content Type", "indexed": False, "text": {}},
    {"name": "_Hidden", "displayName": "Hidden", "hidden": True, "text": {}},
]  # fmt: skip
CUSTOMER_COLUMNS = [
    {"name": "Title", "displayName": "Title", "indexed": True, "text": {}},
    {
        "name": "Region",
        "displayName": "Region",
        "indexed": True,
        "choice": {"choices": ["North", "South", "West"]},
    },
]
DOC_COLUMNS = [
    {"name": "Title", "displayName": "Title", "text": {}},
    {
        "name": "Department",
        "displayName": "Department",
        "indexed": True,
        "choice": {"choices": ["Finance", "HR"]},
    },
]


def workbook() -> bytes:
    """A made-up budget: two sheets and a named table (Targets)."""
    from openpyxl import Workbook
    from openpyxl.worksheet.table import Table

    book = Workbook()
    summary = book.active
    assert summary is not None
    summary.title = "Summary"
    for line in (("region", "budget"), ("North", 1000), ("South", 750), ("West", 500)):
        summary.append(line)
    detail = book.create_sheet("Detail")
    for entry in (("month", "region", "amount"), ("2026-01", "North", 80), ("2026-02", "North", 90)):
        detail.append(entry)
    targets = book.create_sheet("Goals")
    for row in (("goal", "value"), ("Growth", 5), ("Margin", 12)):
        targets.append(row)
    targets.add_table(Table(displayName="Targets", ref="A1:B3"))
    sink = io.BytesIO()
    book.save(sink)
    return sink.getvalue()


def word_document() -> bytes:
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w") as book:
        book.writestr(
            "word/document.xml",
            '<w:document xmlns:w="w"><w:body><w:p><w:r><w:t>Made-up travel policy.'
            "</w:t></w:r></w:p><w:p><w:r><w:t>Book trains first.</w:t></w:r></w:p></w:body></w:document>",
        )
    return sink.getvalue()


def documents() -> dict[str, dict[str, Any]]:
    sink = io.BytesIO()
    pq.write_table(pa.table({"quarter": ["Q3"], "revenue": [12345.5]}), sink)
    files = {
        "Finance/Budget 2026.xlsx": (workbook(), "Finance"),
        "Finance/regions.csv": (b"region,manager\nNorth,Avery\nSouth,Blake\n", "Finance"),
        "Reports/q3.parquet": (sink.getvalue(), "Finance"),
        "Policies/Travel.docx": (word_document(), "HR"),
        "Images/logo.png": (b"\x89PNG made-up", "HR"),
    }
    return {
        path: _document(n, path, data, department)
        for n, (path, (data, department)) in enumerate(files.items(), 1)
    }


def _document(n: int, path: str, data: bytes, department: str) -> dict[str, Any]:
    return {"id": f"item-{n}", "path": path, "data": data, "etag": f'"etag-{n}-1"', "Department": department}


# ===== the server =====


class StandIn:
    def __init__(self, root: Path, port: int = 0) -> None:
        self.root = root
        self.requests: list[dict[str, Any]] = []
        self.tasks = {k: dict(v) for k, v in TASKS.items()}
        self.docs = documents()
        self.refuse_once: set[str] = set()  # $batch request ids answered 429 once ("all": every first)
        self.downloads: list[str] = []
        standin = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send(
                self, status: int, body: Any, headers: dict[str, str] | None = None, head: bool = False
            ) -> None:
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                if not isinstance(body, bytes):
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if not head:
                    self.wfile.write(data)

            def _headers(self) -> dict[str, str]:
                return {k.lower(): v for k, v in self.headers.items()}

            def do_GET(self) -> None:
                self._send(*standin.get(self.path, self._headers()))

            def do_HEAD(self) -> None:
                status, body, headers = standin.get(self.path, self._headers())
                self._send(status, body, headers, head=True)

            def _body(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def do_POST(self) -> None:
                self._send(*standin.post(self.path, self._body(), self._headers()))

            def do_PATCH(self) -> None:
                self._send(*standin.change("PATCH", self.path, self._body(), self._headers()))

            def do_PUT(self) -> None:
                self._send(*standin.change("PUT", self.path, self._body(), self._headers()))

            def do_DELETE(self) -> None:
                self._send(*standin.change("DELETE", self.path, b"", self._headers()))

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> StandIn:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def environment(self) -> dict[str, str]:
        """What moves the connections here (a child process gets them too)."""
        return {
            "SWISSARMYBENCH_LOGIN_URL": self.url,
            "SWISSARMYBENCH_STORAGE_URL": self.url,
            "SWISSARMYBENCH_GRAPH_URL": f"{self.url}/graph/v1.0",
            "IDENTITY_ENDPOINT": f"{self.url}/msi/token",
            "IDENTITY_HEADER": IDENTITY_HEADER,
        }

    def seen(self, what: str) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["what"] == what]

    # ===== the sign-ins =====

    def token(self, path: str, body: bytes) -> tuple[int, Any, dict[str, str]]:
        form = {k: v[0] for k, v in parse_qs(body.decode()).items()}
        tenant = path.split("/")[1]
        shown = {k: ("****" if k in ("password", "client_secret") else v) for k, v in form.items()}
        self.requests.append({"what": "token", "tenant": tenant, "form": shown})
        if tenant != TENANT or form.get("client_id") != CLIENT:
            return (
                400,
                {"error": "unauthorized_client", "error_description": "AADSTS700016: Application not found."},
                {},
            )
        if form.get("grant_type") == "client_credentials":
            if form.get("client_secret") != SECRET:
                return (
                    401,
                    {"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret."},
                    {},
                )
        elif form.get("grant_type") == "password":
            if form.get("username") == MFA_USERNAME:
                return (
                    400,
                    {
                        "error": "invalid_grant",
                        "error_description": "AADSTS50076: Due to a configuration "
                        "change made by your administrator, you must use multi-factor authentication.",
                    },
                    {},
                )
            if (form.get("username"), form.get("password")) != (USERNAME, PASSWORD):
                return (
                    400,
                    {
                        "error": "invalid_grant",
                        "error_description": "AADSTS50126: Error validating "
                        "credentials due to invalid username or password.",
                    },
                    {},
                )
            if "client_secret" in form and form["client_secret"] != SECRET:
                return (
                    401,
                    {"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret."},
                    {},
                )
        else:
            return 400, {"error": "unsupported_grant_type"}, {}
        return 200, {"token_type": "Bearer", "expires_in": 3599, "access_token": TOKEN}, {}

    def managed(self, query: dict[str, str], headers: dict[str, str]) -> tuple[int, Any, dict[str, str]]:
        self.requests.append({"what": "managed identity", "query": query})
        if headers.get("x-identity-header") != IDENTITY_HEADER:
            return 400, {"error": "invalid_request"}, {}
        return 200, {"access_token": TOKEN, "expires_on": str(int(time.time()) + 3600)}, {}

    # ===== requests =====

    def get(self, path: str, headers: dict[str, str]) -> tuple[int, Any, dict[str, str]]:
        parts = urlsplit(path)
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        if parts.path == "/msi/token":
            return self.managed(query, headers)
        if parts.path.startswith("/graph/v1.0/"):
            if headers.get("authorization") != f"Bearer {TOKEN}":
                return (
                    401,
                    {"error": {"code": "InvalidAuthenticationToken", "message": "Access token is empty."}},
                    {},
                )
            return self.graph(unquote(parts.path[len("/graph/v1.0/") :]), query, headers)
        return self.storage(parts.path, query, headers)

    def post(self, path: str, body: bytes, headers: dict[str, str]) -> tuple[int, Any, dict[str, str]]:
        if path.endswith("/oauth2/v2.0/token"):
            return self.token(path, body)
        if path.startswith("/graph/v1.0/$batch"):
            return self.batch(json.loads(body))
        return self.change("POST", path, body, headers)

    # ===== storage (ADLS Gen2) =====

    def _allowed(self, query: dict[str, str], headers: dict[str, str]) -> bool:
        if "sig" in query:
            return verify_sas(query)
        return headers.get("authorization") == f"Bearer {TOKEN}"

    def storage(
        self, path: str, query: dict[str, str], headers: dict[str, str]
    ) -> tuple[int, Any, dict[str, str]]:
        parts = [unquote(p) for p in path.strip("/").split("/")]
        self.requests.append({"what": "storage", "path": "/".join(parts), "query": {k: v for k, v in query.items()
                              if k != "sig"}, "range": headers.get("range")})  # fmt: skip
        if not self._allowed(query, headers):
            return 403, b"<Error><Message>Server failed to authenticate the request.</Message></Error>", {
                "x-ms-error-code": "AuthenticationFailed"}  # fmt: skip
        if len(parts) < 2:
            return 400, {"error": {"message": "Name the filesystem."}}, {}
        place = self.root / parts[0] / parts[1]
        if query.get("resource") == "filesystem":
            return self.listing(place, query)
        file = place.joinpath(*parts[2:])
        if not file.is_file():
            return 404, b"<Error><Message>The specified path does not exist.</Message></Error>", {
                "x-ms-error-code": "PathNotFound"}  # fmt: skip
        data = file.read_bytes()
        found = {"Accept-Ranges": "bytes", "ETag": f'"{file.stat().st_mtime_ns}"',
                 "Last-Modified": "Mon, 16 Nov 2026 10:00:00 GMT"}  # fmt: skip
        wanted = headers.get("range")
        if wanted:
            start, _, end = wanted.removeprefix("bytes=").partition("-")
            a, z = int(start), int(end) if end else len(data) - 1
            return 206, data[a : z + 1], found | {"Content-Range": f"bytes {a}-{z}/{len(data)}"}
        return 200, data, found

    def listing(self, place: Path, query: dict[str, str]) -> tuple[int, Any, dict[str, str]]:
        directory = query.get("directory", "")
        start = place.joinpath(*[p for p in directory.split("/") if p])
        if not start.is_dir():
            return (
                404,
                {"error": {"code": "PathNotFound", "message": "The specified path does not exist."}},
                {},
            )
        recursive = query.get("recursive") == "true"
        found = sorted(start.rglob("*") if recursive else start.iterdir())
        rows = [{"name": p.relative_to(place).as_posix(), "isDirectory": "true" if p.is_dir() else "false",
                 "contentLength": "0" if p.is_dir() else str(p.stat().st_size),
                 "lastModified": "Mon, 16 Nov 2026 10:00:00 GMT", "etag": f"0x{p.stat().st_mtime_ns:x}"}
                for p in found]  # fmt: skip
        at = int(query.get("continuation") or 0)
        page = rows[at : at + PAGE]
        more = {"x-ms-continuation": str(at + PAGE)} if at + PAGE < len(rows) else {}
        return 200, {"paths": page}, more

    # ===== Graph =====

    def _lists(self) -> list[dict[str, Any]]:
        return [
            {"id": "list-tasks", "name": "Tasks", "displayName": "Tasks", "list": {"template": "genericList"}},
            {"id": "list-customers", "name": "Customers", "displayName": "Customers",
             "list": {"template": "genericList"}},
            {"id": "list-documents", "name": "Shared Documents", "displayName": "Documents",
             "list": {"template": "documentLibrary"}},
            {"id": "list-users", "name": "users", "displayName": "User Information List",
             "list": {"template": "genericList", "hidden": True}},
        ]  # fmt: skip

    def _items(self, list_id: str) -> dict[int, dict[str, Any]]:
        if list_id == "list-tasks":
            return self.tasks
        if list_id == "list-customers":
            return {k: {"Title": t, "Region": r} for k, (t, r) in CUSTOMERS.items()}
        if list_id == "list-users":
            return {
                k: {"Title": t, "EMail": f"{t.split()[0].lower()}@made-up.example"} for k, t in PEOPLE.items()
            }
        return {}

    def graph(
        self, path: str, query: dict[str, str], headers: dict[str, str]
    ) -> tuple[int, Any, dict[str, str]]:
        self.requests.append({"what": "graph", "path": path, "query": query, "prefer": headers.get("prefer")})
        if path == f"sites/{SITE_HOST}:{SITE_PATH}":
            return 200, {"id": SITE_ID, "webUrl": f"https://{SITE_HOST}{SITE_PATH}"}, {}
        site = f"sites/{SITE_ID}/"
        if path == site + "lists":
            return 200, {"value": self._lists()}, {}
        found = re.fullmatch(re.escape(site) + r"lists/([^/]+)/columns", path)
        if found:
            columns = {"list-tasks": TASK_COLUMNS, "list-customers": CUSTOMER_COLUMNS,
                       "list-documents": DOC_COLUMNS, "list-users": [{"name": "Title", "text": {}}]}  # fmt: skip
            return 200, {"value": columns.get(found.group(1), [])}, {}
        found = re.fullmatch(re.escape(site) + r"lists/([^/]+)/items", path)
        if found:
            return self.list_items(found.group(1), query)
        if path == site + "drives":
            return 200, {"value": [{"id": "drive-docs", "name": "Documents", "driveType": "documentLibrary",
                                    "webUrl": f"https://{SITE_HOST}{SITE_PATH}/Shared Documents"}]}, {}  # fmt: skip
        if path == "drives/drive-docs/list":
            return 200, {"id": "list-documents"}, {}
        if path == "drives/drive-docs/list/items":
            return self.doc_items(query)
        found = re.fullmatch(r"drives/drive-docs/items/([^/]+)/content", path)
        if found:
            doc = next((d for d in self.docs.values() if d["id"] == found.group(1)), None)
            if doc is None:
                return (
                    404,
                    {"error": {"code": "itemNotFound", "message": "The resource could not be found."}},
                    {},
                )
            self.downloads.append(doc["path"])
            return 200, doc["data"], {"Content-Type": "application/octet-stream"}
        return 404, {"error": {"code": "itemNotFound", "message": f"No such path: {path}"}}, {}

    def _page(self, rows: list[dict[str, Any]], query: dict[str, str], path: str) -> dict[str, Any]:
        top = min(int(query.get("$top") or 200), GRAPH_PAGE)
        at = int(query.get("$skiptoken") or 0)
        page = rows[at : at + top]
        answer: dict[str, Any] = {"value": page}
        if at + top < len(rows):
            rest = {k: v for k, v in query.items() if k != "$skiptoken"} | {"$skiptoken": str(at + top)}
            answer["@odata.nextLink"] = f"{self.url}/graph/v1.0/{quote(path)}?" + "&".join(
                f"{k}={quote(v, safe='')}" for k, v in rest.items())  # fmt: skip
        return answer

    def list_items(self, list_id: str, query: dict[str, str]) -> tuple[int, Any, dict[str, str]]:
        items = self._items(list_id)
        selected = re.search(r"fields\(\$select=([^)]*)\)", query.get("$expand", ""))
        names = selected.group(1).split(",") if selected else None
        rows = [{"id": str(k), "fields": {n: v for n, v in f.items() if names is None or n in names}}
                for k, f in sorted(items.items())]  # fmt: skip
        wanted = query.get("$filter")
        if wanted:
            for field in re.findall(r"fields/(\w+)", wanted):
                column = next((c for c in TASK_COLUMNS + CUSTOMER_COLUMNS if c["name"] == field), None)
                if column is None or not column.get("indexed"):
                    return 400, {"error": {"code": "invalidRequest", "message": f"Field '{field}' cannot be "
                                 "referenced in filter or orderby as it is not indexed."}}, {}  # fmt: skip
            rows = [r for r in rows if _matches(wanted, items[int(str(r["id"]))])]
        return 200, self._page(rows, query, f"sites/{SITE_ID}/lists/{list_id}/items"), {}

    def doc_items(self, query: dict[str, str]) -> tuple[int, Any, dict[str, str]]:
        rows = []
        for n, (path, d) in enumerate(sorted(self.docs.items())):
            folder, _, name = path.rpartition("/")
            rows.append({
                "id": str(n + 1),
                "fields": {"FileLeafRef": name, "ContentType": "Document", "Department": d["Department"]},
                "driveItem": {
                    "id": d["id"], "name": name, "size": len(d["data"]), "eTag": d["etag"],
                    "webUrl": f"https://{SITE_HOST}{SITE_PATH}/Shared Documents/{path}",
                    "createdDateTime": "2026-11-02T10:00:00Z", "lastModifiedDateTime": "2026-11-10T15:30:00Z",
                    "createdBy": {"user": {"displayName": "Avery Made-up"}},
                    "lastModifiedBy": {"user": {"displayName": "Blake Made-up"}},
                    "parentReference": {"path": f"/drives/drive-docs/root:/{folder}"},
                    "file": {"mimeType": "application/octet-stream"},
                },
            })  # fmt: skip
        rows.append({"id": "99", "fields": {"FileLeafRef": "Finance"}, "driveItem": {"id": "folder-1", "name": "Finance",
                     "folder": {"childCount": 2}}})  # fmt: skip
        return 200, self._page(rows, query, "drives/drive-docs/list/items"), {}

    # ===== changes =====

    def change(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> tuple[int, Any, dict[str, str]]:
        if headers.get("authorization") != f"Bearer {TOKEN}":
            return (
                401,
                {"error": {"code": "InvalidAuthenticationToken", "message": "Access token is empty."}},
                {},
            )
        inner = unquote(urlsplit(path).path).removeprefix("/graph/v1.0/")
        self.requests.append({"what": "change", "method": method, "path": inner})
        status, answer = self.apply(method, inner, json.loads(body) if body and method != "PUT" else body)
        return status, answer, {}

    def apply(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        base = f"sites/{SITE_ID}/lists/list-tasks/items"
        path = path.lstrip("/")
        if method == "POST" and path == base:
            new = max(self.tasks, default=0) + 1
            self.tasks[new] = dict(body.get("fields") or {})
            return 201, {"id": str(new), "fields": self.tasks[new]}
        found = re.fullmatch(re.escape(base) + r"/(\d+)(/fields)?", path)
        if found and int(found.group(1)) not in self.tasks:
            return 404, {"error": {"code": "itemNotFound", "message": "Item not found"}}
        if found and method == "PATCH":
            self.tasks[int(found.group(1))].update(body or {})
            return 200, self.tasks[int(found.group(1))]
        if found and method == "DELETE":
            del self.tasks[int(found.group(1))]
            return 204, {}
        found = re.fullmatch(r"drives/drive-docs/root:/(.+):/content", path)
        if found and method == "PUT":
            n = len(self.docs) + 1
            self.docs[found.group(1)] = _document(n, found.group(1), bytes(body), "Finance")
            name = found.group(1).rsplit("/", 1)[-1]
            return 201, {
                "id": f"item-{n}",
                "name": name,
                "size": len(body),
                "webUrl": f"https://{SITE_HOST}/x/{name}",
            }
        return 400, {"error": {"code": "invalidRequest", "message": f"Cannot {method} {path}"}}

    def batch(self, sent: dict[str, Any]) -> tuple[int, Any, dict[str, str]]:
        requests = sent.get("requests") or []
        self.requests.append({"what": "batch", "count": len(requests)})
        if len(requests) > 20:
            return (
                400,
                {"error": {"code": "invalidRequest", "message": "A batch holds at most 20 requests."}},
                {},
            )
        answers = []
        for r in requests:
            if r["id"] in self.refuse_once or "all" in self.refuse_once:
                self.refuse_once.discard(r["id"])
                answers.append({"id": r["id"], "status": 429, "headers": {"Retry-After": "0"}, "body": {}})
                continue
            status, body = self.apply(r["method"], r["url"], r.get("body"))
            answers.append({"id": r["id"], "status": status, "body": body})
        self.refuse_once.discard("all")
        return 200, {"responses": answers}, {}


def _matches(where: str, fields: dict[str, Any]) -> bool:
    """A made-up $filter: comparisons joined by and/or (the shapes the connection sends)."""

    def one(text: str) -> bool:
        found = re.fullmatch(
            r"\(?fields/(\w+) (eq|ne|gt|ge|lt|le) ('(?:[^']|'')*'|[\d.]+|true|false)\)?", text.strip()
        )
        if found is None:
            return True
        name, op, raw = found.groups()
        value: Any = (
            raw[1:-1].replace("''", "'")
            if raw.startswith("'")
            else (raw == "true" if raw in ("true", "false") else float(raw))
        )
        have = fields.get(name)
        if have is None:
            return False
        if isinstance(value, float):
            have = float(have)
        compared: dict[str, bool] = {"eq": have == value, "ne": have != value, "gt": have > value,
                                  "ge": have >= value, "lt": have < value, "le": have <= value}  # fmt: skip
        return compared[op]

    for group in re.split(r"\s+and\s+", where):
        options = re.split(r"\s+or\s+", group.strip().strip("()"))
        if not any(one(o) for o in options):
            return False
    return True


if __name__ == "__main__":
    import tempfile

    folder = Path(tempfile.mkdtemp(prefix="sab-lake-"))
    make_lake(folder)
    running = StandIn(folder, int(sys.argv[1]) if len(sys.argv) > 1 else 8793).start()
    print(running.url, json.dumps(running.environment()), flush=True)
    os.environ.update(running.environment())
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        running.stop()
