"""A stand-in for Power BI on this computer, for tests and screenshots: no real tenant is ever reached.

It answers the three requests the Power BI workspace connection makes, the way Microsoft documents them
(and, below, the REST requests of the starter pack's Power BI blades: refreshes, dataflows, reports,
parameters, take over and the refresh schedule):

  POST /{tenant}/oauth2/v2.0/token                                    the client credentials sign-in
  GET  /v1.0/myorg/groups/{workspace}/datasets                        the workspace's datasets
  POST /v1.0/myorg/groups/{workspace}/datasets/{dataset}/executeQueries   one DAX query, rows as JSON

over a made-up workspace of three datasets:

  Sales model    Sales, Customer, Product and Date, three measures, four relationships (one of them
                 inactive, one filtering both ways) and one of the date tables Power BI makes by itself
  Budget model   Budget, Department and Date (a Date table of its own: the name is shared), one
                 measure, two relationships
  Broken model   answers every query with an error, as a dataset being refreshed does

It knows only the DAX the app sends (the INFO functions, TOPN, COUNTROWS, a table by its name) and one
SUMMARIZECOLUMNS for a notebook cell; anything else is refused in the real service's error shape.

Every request is kept (`requests`), so a test can prove what the sign-in carried. Made-up values only.

    python -m tests.powerbi_standin 8791        # run it by itself (the screenshots do)
"""

from __future__ import annotations

import json
import re
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs

TENANT = "made-up-tenant-0001"
CLIENT = "made-up-client-0002"
SECRET = "made-up-client-secret-0003"
WORKSPACE = "11111111-aaaa-4bbb-8ccc-222222222222"
DATASET = "33333333-dddd-4eee-8fff-444444444444"  # Sales model
BUDGET_DATASET = "55555555-aaaa-4bbb-8ccc-666666666666"
BROKEN_DATASET = "77777777-dddd-4eee-8fff-888888888888"
BROKEN_MESSAGE = "The dataset is being refreshed and cannot be queried now."
SCOPE = "https://analysis.windows.net/powerbi/api/.default"
TOKEN = "made-up-access-token-0004"

_REGIONS = ["North", "South", "East", None]
_START = date(2026, 1, 1)


def _iso(day: date) -> str:
    return f"{day.isoformat()}T00:00:00"


def tables() -> dict[str, list[dict[str, Any]]]:
    """The made-up model's rows, by table. Sales has 40 rows; a few values are missing (null)."""
    customers = [
        {"CustomerKey": i, "Customer Name": f"Customer {i:02d}", "Region": _REGIONS[i % 4]}
        for i in range(1, 9)
    ]
    products = [
        {"ProductKey": i, "Product Name": name, "Unit Price": price}
        for i, (name, price) in enumerate([("Widget", 4.5), ("Gadget", 12.25), ("Gizmo", 30.0)], 1)
    ]
    days = [
        {
            "Date": _iso(_START + timedelta(days=i)),
            "Year": 2026,
            "Month": (_START + timedelta(days=i)).strftime("%B"),
        }
        for i in range(60)
    ]
    sales = [
        {
            "SalesKey": i,
            "CustomerKey": i % 8 + 1,
            "ProductKey": i % 3 + 1,
            "Order Date": _iso(_START + timedelta(days=i)),
            "Ship Date": None if i % 10 == 0 else _iso(_START + timedelta(days=i + 3)),
            "Quantity": i % 5 + 1,
            "Amount": None if i % 13 == 0 else round((i % 5 + 1) * [4.5, 12.25, 30.0][i % 3], 2),
        }
        for i in range(1, 41)
    ]
    return {
        "Sales": sales,
        "Customer": customers,
        "Product": products,
        "Date": days,
        "LocalDateTable_made-up": [{"Date": _iso(_START)}],
    }


# (table, column, Power BI's word for its type, the numbered form's type)
COLUMNS: list[tuple[str, str, str, int]] = [
    ("Sales", "SalesKey", "Integer", 6),
    ("Sales", "CustomerKey", "Integer", 6),
    ("Sales", "ProductKey", "Integer", 6),
    ("Sales", "Order Date", "DateTime", 9),
    ("Sales", "Ship Date", "DateTime", 9),
    ("Sales", "Quantity", "Integer", 6),
    ("Sales", "Amount", "Decimal", 10),
    ("Customer", "CustomerKey", "Integer", 6),
    ("Customer", "Customer Name", "Text", 2),
    ("Customer", "Region", "Text", 2),
    ("Product", "ProductKey", "Integer", 6),
    ("Product", "Product Name", "Text", 2),
    ("Product", "Unit Price", "Decimal", 10),
    ("Date", "Date", "DateTime", 9),
    ("Date", "Year", "Integer", 6),
    ("Date", "Month", "Text", 2),
    ("LocalDateTable_made-up", "Date", "DateTime", 9),
]
MEASURES: list[tuple[str, str, str, int]] = [
    ("Sales", "Total Sales", "Decimal", 10),
    ("Sales", "Order Count", "Integer", 6),
    ("Customer", "Customer Count", "Integer", 6),
]
# (from table, from column, to table, to column, active, both directions)
RELATIONSHIPS: list[tuple[str, str, str, str, bool, bool]] = [
    ("Sales", "CustomerKey", "Customer", "CustomerKey", True, False),
    ("Sales", "ProductKey", "Product", "ProductKey", True, True),
    ("Sales", "Order Date", "Date", "Date", True, False),
    ("Sales", "Ship Date", "Date", "Date", False, False),
    ("Date", "Date", "LocalDateTable_made-up", "Date", True, False),
]


def budget_tables() -> dict[str, list[dict[str, Any]]]:
    """The second dataset's rows: a budget by department and month, with its own Date table."""
    departments = [
        {"DepartmentKey": i, "Department": name}
        for i, name in enumerate(["Operations", "Marketing", "Research"], 1)
    ]
    months = [{"Date": _iso(date(2026, m, 1)), "Quarter": f"Q{(m - 1) // 3 + 1}"} for m in range(1, 13)]
    budget = [
        {
            "BudgetKey": i,
            "DepartmentKey": i % 3 + 1,
            "Month": _iso(date(2026, i % 12 + 1, 1)),
            "Planned": 1000.0 + 250 * (i % 7),
        }
        for i in range(1, 25)
    ]
    return {"Budget": budget, "Department": departments, "Date": months}


BUDGET_COLUMNS: list[tuple[str, str, str, int]] = [
    ("Budget", "BudgetKey", "Integer", 6),
    ("Budget", "DepartmentKey", "Integer", 6),
    ("Budget", "Month", "DateTime", 9),
    ("Budget", "Planned", "Decimal", 10),
    ("Department", "DepartmentKey", "Integer", 6),
    ("Department", "Department", "Text", 2),
    ("Date", "Date", "DateTime", 9),
    ("Date", "Quarter", "Text", 2),
]
BUDGET_MEASURES: list[tuple[str, str, str, int]] = [("Budget", "Total Planned", "Decimal", 10)]
BUDGET_RELATIONSHIPS: list[tuple[str, str, str, str, bool, bool]] = [
    ("Budget", "DepartmentKey", "Department", "DepartmentKey", True, False),
    ("Budget", "Month", "Date", "Date", True, False),
]


@dataclass(frozen=True)
class MadeUpModel:
    """One dataset of the made-up workspace. `broken`: it answers every query with an error."""

    id: str
    name: str
    rows: dict[str, list[dict[str, Any]]]
    columns: list[tuple[str, str, str, int]]
    measures: list[tuple[str, str, str, int]]
    relationships: list[tuple[str, str, str, str, bool, bool]]
    broken: bool = False

    @property
    def table_ids(self) -> dict[str, int]:
        return {name: 100 + i for i, name in enumerate(dict.fromkeys(c[0] for c in self.columns))}

    @property
    def column_ids(self) -> dict[tuple[str, str], int]:
        return {(t, c): 1000 + i for i, (t, c, _, _) in enumerate(self.columns)}


SALES_MODEL = MadeUpModel(DATASET, "Sales model", tables(), COLUMNS, MEASURES, RELATIONSHIPS)
BUDGET_MODEL = MadeUpModel(
    BUDGET_DATASET, "Budget model", budget_tables(), BUDGET_COLUMNS, BUDGET_MEASURES, BUDGET_RELATIONSHIPS
)
BROKEN_MODEL = MadeUpModel(BROKEN_DATASET, "Broken model", {}, [], [], [], broken=True)
MODELS: list[MadeUpModel] = [SALES_MODEL, BUDGET_MODEL, BROKEN_MODEL]
DATASET_NAMES: list[str] = [m.name for m in MODELS]


def _keyed(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A function's rows as Power BI writes them: each column as [Name]."""
    return [{f"[{k}]": v for k, v in row.items()} for row in rows]


def _info(function: str, model: MadeUpModel = SALES_MODEL) -> list[dict[str, Any]] | None:
    """The INFO functions' answers over a made-up model; None for one this stand-in does not know."""
    _TABLE_IDS, _COLUMN_IDS = model.table_ids, model.column_ids
    COLUMNS, MEASURES, RELATIONSHIPS = model.columns, model.measures, model.relationships
    if function == "INFO.VIEW.TABLES":
        return [
            {"ID": i, "Name": t, "Model": "Model", "IsHidden": t.startswith("Local")}
            for t, i in _TABLE_IDS.items()
        ]
    if function == "INFO.VIEW.COLUMNS":
        return [
            {"ID": _COLUMN_IDS[(t, c)], "Name": c, "Table": t, "DataType": kind, "IsHidden": False}
            for t, c, kind, _ in COLUMNS
        ]
    if function == "INFO.VIEW.MEASURES":
        return [
            {"ID": 5000 + i, "Name": m, "Table": t, "DataType": kind, "Expression": "made up"}
            for i, (t, m, kind, _) in enumerate(MEASURES)
        ]
    if function == "INFO.VIEW.RELATIONSHIPS":
        return [
            {
                "ID": 9000 + i,
                "Name": f"made-up-relationship-{i}",
                "IsActive": active,
                "CrossFilteringBehavior": "BothDirections" if both else "OneDirection",
                "FromTable": ft,
                "FromColumn": fc,
                "FromCardinality": "Many",
                "ToTable": tt,
                "ToColumn": tc,
                "ToCardinality": "One",
            }
            for i, (ft, fc, tt, tc, active, both) in enumerate(RELATIONSHIPS)
        ]
    if function == "INFO.TABLES":
        return [
            {"ID": i, "ModelID": 1, "Name": t, "IsHidden": t.startswith("Local")}
            for t, i in _TABLE_IDS.items()
        ]
    if function == "INFO.COLUMNS":
        listed = [
            {
                "ID": _COLUMN_IDS[(t, c)],
                "TableID": _TABLE_IDS[t],
                "ExplicitName": c,
                "InferredName": None,
                "ExplicitDataType": number,
                "Type": 1,
            }
            for t, c, _, number in COLUMNS
        ]
        hidden = [
            {
                "ID": 3000 + i,
                "TableID": i,
                "ExplicitName": f"RowNumber-made-up-{i}",
                "InferredName": None,
                "ExplicitDataType": 6,
                "Type": 3,
            }
            for i in _TABLE_IDS.values()
        ]
        return hidden + listed
    if function == "INFO.MEASURES":
        return [
            {"ID": 5000 + i, "TableID": _TABLE_IDS[t], "Name": m, "DataType": number, "Expression": "made up"}
            for i, (t, m, _, number) in enumerate(MEASURES)
        ]
    if function == "INFO.RELATIONSHIPS":
        return [
            {
                "ID": 9000 + i,
                "ModelID": 1,
                "IsActive": active,
                "CrossFilteringBehavior": 2 if both else 1,
                "FromTableID": _TABLE_IDS[ft],
                "FromColumnID": _COLUMN_IDS[(ft, fc)],
                "FromCardinality": 2,
                "ToTableID": _TABLE_IDS[tt],
                "ToColumnID": _COLUMN_IDS[(tt, tc)],
                "ToCardinality": 1,
            }
            for i, (ft, fc, tt, tc, active, both) in enumerate(RELATIONSHIPS)
        ]
    return None


class DaxError(Exception):
    """A query the stand-in refuses, in the words the real service would use."""


def _table_rows(name: str, model: MadeUpModel = SALES_MODEL) -> list[dict[str, Any]]:
    found = model.rows.get(name.replace("''", "'"))
    if found is None:
        raise DaxError(f"Cannot find table '{name}'.")
    return [{f"{name}[{k}]": v for k, v in row.items()} for row in found]


def evaluate(
    dax: str, view_forms: bool = True, info_forms: bool = True, model: MadeUpModel = SALES_MODEL
) -> list[dict[str, Any]]:
    """One DAX query's rows, keyed as Power BI keys them (Table[Column], [Name])."""
    if model.broken:
        raise DaxError(BROKEN_MESSAGE)
    text = re.sub(r"(--|//)[^\n]*", "", dax).strip()  # a DAX cell may begin with a comment line
    text = re.sub(r"\s+", " ", text)
    if (found := re.fullmatch(r"EVALUATE ROW\(\s*\"(\w+)\"\s*,\s*1\s*\)", text, re.I)) is not None:
        return [{f"[{found.group(1)}]": 1}]
    if (found := re.fullmatch(r"EVALUATE (INFO(?:\.VIEW)?\.[A-Z]+)\(\)", text, re.I)) is not None:
        function = found.group(1).upper()
        allowed = view_forms if function.startswith("INFO.VIEW.") else info_forms
        rows = _info(function, model) if allowed else None
        if rows is None:
            raise DaxError(
                f"Failed to resolve name '{found.group(1)}'. It is not a valid table, variable, or "
                "function name."
            )
        return _keyed(rows)
    if re.fullmatch(r"EVALUATE COLUMNSTATISTICS\(\)", text, re.I):
        return _keyed(
            [
                {"Table Name": t, "Column Name": c, "Cardinality": len(model.rows[t])}
                for t, c, _, _ in model.columns
            ]
            + [
                {"Table Name": t, "Column Name": f"RowNumber-made-up-{i}", "Cardinality": 1}
                for t, i in model.table_ids.items()
            ]
        )
    if (
        found := re.fullmatch(r"EVALUATE TOPN\(\s*(\d+)\s*,\s*'((?:[^']|'')+)'\s*\)", text, re.I)
    ) is not None:
        return _table_rows(found.group(2), model)[: int(found.group(1))]
    if (found := re.fullmatch(r"EVALUATE '((?:[^']|'')+)'", text, re.I)) is not None:
        return _table_rows(found.group(1), model)
    if (
        found := re.fullmatch(
            r"EVALUATE ROW\(\s*\"(\w+)\"\s*,\s*COUNTROWS\(\s*'((?:[^']|'')+)'\s*\)\s*\)", text, re.I
        )
    ) is not None:
        return [{f"[{found.group(1)}]": len(_table_rows(found.group(2), model))}]
    if (
        re.fullmatch(
            r"EVALUATE SUMMARIZECOLUMNS\(\s*'Customer'\[Region\]\s*,\s*"
            r"\"Total Sales\"\s*,\s*\[Total Sales\]\s*\)",
            text,
            re.I,
        )
        and model is SALES_MODEL
    ):
        region = {c["CustomerKey"]: c["Region"] for c in model.rows["Customer"]}
        totals: dict[Any, float] = {}
        for sale in model.rows["Sales"]:
            where = region[sale["CustomerKey"]]
            totals[where] = totals.get(where, 0.0) + (sale["Amount"] or 0.0)
        return [
            {"Customer[Region]": where, "[Total Sales]": round(total, 2)} for where, total in totals.items()
        ]
    raise DaxError("Query (1, 1) The syntax is incorrect, or this stand-in does not know the query.")


# What an action answers: the status, its JSON (None: an empty answer), and headers.
Acted = tuple[int, dict[str, Any] | None, dict[str, str]]
DATAFLOWS: list[dict[str, Any]] = [
    {"objectId": "99999999-aaaa-4bbb-8ccc-000000000001", "name": "Orders dataflow",
     "description": "Made-up orders, cleaned", "configuredBy": "made.up@example.com"},
]  # fmt: skip
REPORTS: list[dict[str, Any]] = [
    {"id": "aaaaaaaa-1111-4222-8333-000000000001", "name": "Sales overview", "datasetId": DATASET,
     "webUrl": "https://app.powerbi.example/reports/sales-overview"},
    {"id": "aaaaaaaa-1111-4222-8333-000000000002", "name": "Budget review", "datasetId": BUDGET_DATASET,
     "webUrl": "https://app.powerbi.example/reports/budget-review"},
]  # fmt: skip
PARAMETERS: list[dict[str, Any]] = [
    {"name": "Region", "type": "Text", "isRequired": True, "currentValue": "North"},
    {"name": "Rows", "type": "Number", "isRequired": False, "currentValue": "1000"},
]
SCHEDULE: dict[str, Any] = {
    "days": ["Monday", "Wednesday", "Friday"],
    "times": ["07:00", "13:30"],
    "enabled": True,
    "localTimeZoneId": "UTC",
    "notifyOption": "MailOnFailure",
}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _refusal(code: str, message: str | None = None) -> dict[str, Any]:
    """An error as the real service writes it."""
    details = [] if message is None else [
        {"code": "DetailsMessage", "detail": {"type": 1, "value": message}},
        {"code": "AnalysisServicesErrorCode", "detail": {"type": 1, "value": "3241803783"}},
    ]  # fmt: skip
    return {"error": {"code": code, "pbi.error": {"code": code, "parameters": {}, "details": details}}}


class StandIn:
    """The stand-in, listening on 127.0.0.1 (a free port unless one is given). `view_forms` and
    `info_forms` switch off the INFO.VIEW functions, then the INFO ones, as an older model or a
    sign-in with less leave would."""

    def __init__(self, port: int = 0) -> None:
        self.requests: list[dict[str, Any]] = []
        self.view_forms = True
        self.info_forms = True
        self.models: list[MadeUpModel] = list(MODELS)  # a test may leave one dataset, or add many
        # The actions' state: each dataset's refreshes (newest first), a dataflow's, each dataset's
        # parameters and whether the app registration owns it; a refresh runs for this many looks.
        self.refreshes: dict[str, list[dict[str, Any]]] = {}
        self.transactions: dict[str, list[dict[str, Any]]] = {}
        self.parameters: dict[str, list[dict[str, Any]]] = {DATASET: [dict(p) for p in PARAMETERS]}
        self.owners: dict[str, str] = {}
        self.refresh_polls = 2
        self._serial = 0
        standin = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def _send(
                self, status: int, body: dict[str, Any] | None, headers: dict[str, str] | None = None
            ) -> None:
                data = b"" if body is None else json.dumps(body).encode()
                self.send_response(status)
                if body is not None:
                    self.send_header("Content-Type", "application/json")
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                authorization = self.headers.get("Authorization") or ""
                acted = standin.act("GET", self.path, b"", authorization)
                if acted is not None:
                    self._send(*acted)
                    return
                status, answer = standin.listing(self.path, authorization)
                self._send(status, answer)

            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                authorization = self.headers.get("Authorization") or ""
                acted = standin.act("POST", self.path, body, authorization)
                if acted is not None:
                    self._send(*acted)
                    return
                status, answer = standin.answer(self.path, body, authorization)
                self._send(status, answer)

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def listing(self, path: str, authorization: str) -> tuple[int, dict[str, Any]]:
        """GET .../groups/{workspace}/datasets: the workspace's datasets, names and ids."""
        found = re.fullmatch(r"/v1\.0/myorg/groups/([^/]+)/datasets", path)
        self.requests.append({"what": "datasets", "path": path, "authorization": authorization})
        if found is None:
            return 404, _refusal("PowerBIEntityNotFound")
        if authorization != f"Bearer {TOKEN}":
            return 401, _refusal("TokenExpired")
        if found.group(1) != WORKSPACE:
            return 404, _refusal("PowerBIEntityNotFound")
        listed = [
            {"id": m.id, "name": m.name, "isRefreshable": True, "configuredBy": "made.up@example.com"}
            for m in self.models
        ]
        return 200, {"value": listed}

    def answer(self, path: str, body: bytes, authorization: str) -> tuple[int, dict[str, Any]]:
        if path.endswith("/oauth2/v2.0/token"):
            form = {k: v[0] for k, v in parse_qs(body.decode()).items()}
            tenant = path.split("/")[1]
            self.requests.append({"what": "token", "tenant": tenant, "form": form})
            right = (tenant, form.get("client_id"), form.get("client_secret")) == (TENANT, CLIENT, SECRET)
            if not right or form.get("grant_type") != "client_credentials" or form.get("scope") != SCOPE:
                description = (
                    "AADSTS7000215: Invalid client secret provided. Ensure the secret being sent in the "
                    "request is the client secret value, not the client secret ID.\r\nTrace ID: made-up"
                )
                return 401, {
                    "error": "invalid_client",
                    "error_description": description,
                    "error_codes": [7000215],
                }
            return 200, {"token_type": "Bearer", "expires_in": 3599, "access_token": TOKEN}
        found = re.fullmatch(r"/v1\.0/myorg/groups/([^/]+)/datasets/([^/]+)/executeQueries", path)
        if found is None:
            return 404, _refusal("PowerBIEntityNotFound")
        try:
            sent = json.loads(body)
            dax = str(sent["queries"][0]["query"])
        except (ValueError, KeyError, IndexError, TypeError):
            return 400, _refusal("BadRequest", "The request has no query.")
        self.requests.append({"what": "query", "dax": dax, "authorization": authorization, "body": sent})
        if authorization != f"Bearer {TOKEN}":
            return 401, _refusal("TokenExpired")
        model = next((m for m in self.models if m.id == found.group(2)), None)
        if found.group(1) != WORKSPACE or model is None:
            return 404, _refusal("PowerBIEntityNotFound")
        self.requests[-1]["dataset"] = model.name
        try:
            rows = evaluate(dax, self.view_forms, self.info_forms, model)
        except DaxError as error:
            return 400, _refusal("DatasetExecuteQueriesError", str(error))
        if not sent.get("serializerSettings", {}).get("includeNulls"):
            rows = [{k: v for k, v in row.items() if v is not None} for row in rows]  # as the real one does
        return 200, {"results": [{"tables": [{"rows": rows}]}]}

    # ===== the actions: refreshes, dataflows, reports, parameters, take over, the schedule =====

    def act(self, method: str, path: str, body: bytes, authorization: str) -> Acted | None:
        """The REST requests the starter pack's Power BI blades make (None: not one of them), answered
        as Power BI documents them: a refresh is 202 with a RequestId header, then shows in the history
        as Unknown (Power BI's word for running) until it has been asked about `refresh_polls` times."""
        place = r"/v1\.0/myorg/groups/([^/]+)/(datasets|dataflows|reports)(/[^?]*)?(\?.*)?"
        found = re.fullmatch(place, path)
        if found is None or (found.group(2) == "datasets" and not found.group(3)):
            return None  # the datasets list and executeQueries are the connection's own (above)
        what, rest, query = found.group(2), (found.group(3) or ""), (found.group(4) or "")
        if rest.endswith("/executeQueries"):
            return None
        sent: Any = json.loads(body) if body.strip() else None
        self.requests.append({"what": "action", "method": method, "path": path.split("?")[0], "body": sent})
        if authorization != f"Bearer {TOKEN}":
            return 401, _refusal("TokenExpired"), {}
        if found.group(1) != WORKSPACE:
            return 404, _refusal("PowerBIEntityNotFound"), {}
        if what == "reports" and not rest and method == "GET":
            return 200, {"value": [dict(r) for r in REPORTS]}, {}
        if what == "dataflows":
            return self._dataflow(method, rest, sent)
        part = re.fullmatch(r"/([^/]+)(/.*)?", rest)
        model = next((m for m in self.models if part and m.id == part.group(1)), None)
        if part is None or model is None:
            return 404, _refusal("PowerBIEntityNotFound"), {}
        action = part.group(2) or ""
        if action == "/refreshes" and method == "POST":
            notify = (sent or {}).get("notifyOption")
            if notify not in ("NoNotification", "MailOnFailure", "MailOnCompletion"):
                return 400, {"error": {"code": "InvalidRequest", "message": "notifyOption is required."}}, {}
            if notify != "NoNotification":  # a service principal cannot be emailed
                message = "Invalid NotifyOption value 'MailOnFailure' for app only owner requests"
                return 400, {"error": {"code": "InvalidRequest", "message": message}}, {}
            self._serial += 1
            request_id = f"made-up-request-{self._serial:04d}"
            refreshes = self.refreshes.setdefault(model.id, [])
            refreshes.insert(0, {"requestId": request_id, "id": self._serial, "refreshType": "ViaApi",
                                 "startTime": _now(), "status": "Unknown", "polls": 0})  # fmt: skip
            return 202, None, {"RequestId": request_id}
        if action == "/refreshes" and method == "GET":
            top = int((parse_qs(query.lstrip("?")).get("$top") or ["100"])[0])
            listed = []
            for refresh in self.refreshes.get(model.id, [])[:top]:
                refresh["polls"] += 1
                if refresh["status"] == "Unknown" and refresh["polls"] > self.refresh_polls:
                    refresh["endTime"] = _now()
                    refresh["status"] = "Failed" if model.broken else "Completed"
                    if model.broken:
                        error = {"errorCode": "ModelRefreshFailed", "errorDescription": BROKEN_MESSAGE}
                        refresh["serviceExceptionJson"] = json.dumps(error)
                listed.append({k: v for k, v in refresh.items() if k != "polls"})
            return 200, {"value": listed}, {}
        if action == "/parameters" and method == "GET":
            return 200, {"value": [dict(p) for p in self.parameters.get(model.id, [])]}, {}
        if action == "/Default.UpdateParameters" and method == "POST":
            if self.owners.get(model.id) != "app":
                message = "The user is not the owner of the dataset: take it over first."
                return 403, {"error": {"code": "InvalidRequest", "message": message}}, {}
            known = {p["name"]: p for p in self.parameters.get(model.id, [])}
            for detail in (sent or {}).get("updateDetails", []):
                if detail.get("name") not in known:
                    message = f"Parameter {detail.get('name')!r} does not exist in the dataset."
                    return 400, {"error": {"code": "InvalidRequest", "message": message}}, {}
                known[detail["name"]]["currentValue"] = str(detail.get("newValue"))
            return 200, None, {}
        if action == "/Default.TakeOver" and method == "POST":
            self.owners[model.id] = "app"
            return 200, None, {}
        if action == "/refreshSchedule" and method == "GET":
            return 200, dict(SCHEDULE), {}
        return 404, _refusal("PowerBIEntityNotFound"), {}

    def _dataflow(self, method: str, rest: str, sent: Any) -> Acted:
        if not rest and method == "GET":
            return 200, {"value": [dict(d) for d in DATAFLOWS]}, {}
        part = re.fullmatch(r"/([^/]+)/(refreshes|transactions)", rest)
        flow = next((d for d in DATAFLOWS if part and d["objectId"] == part.group(1)), None)
        if part is None or flow is None:
            return 404, _refusal("PowerBIEntityNotFound"), {}
        if part.group(2) == "refreshes" and method == "POST":
            if (sent or {}).get("notifyOption") not in ("NoNotification", "MailOnFailure"):
                return 400, {"error": {"code": "InvalidRequest", "message": "notifyOption is required."}}, {}
            self._serial += 1
            self.transactions.setdefault(flow["objectId"], []).insert(
                0, {"id": f"made-up-transaction-{self._serial:04d}", "refreshType": "ViaApi",
                    "startTime": _now(), "endTime": None, "status": "InProgress"}
            )  # fmt: skip
            return 200, None, {}
        if part.group(2) == "transactions" and method == "GET":
            return 200, {"value": [dict(t) for t in self.transactions.get(flow["objectId"], [])]}, {}
        return 404, _refusal("PowerBIEntityNotFound"), {}

    def actions(self) -> list[dict[str, Any]]:
        """Every action request received, in order: {"method", "path", "body"}."""
        return [r for r in self.requests if r["what"] == "action"]

    def queries(self, dataset: str | None = None) -> list[str]:
        """Every DAX query received, in order (one dataset's, when named)."""
        return [
            r["dax"]
            for r in self.requests
            if r["what"] == "query" and (dataset is None or r.get("dataset") == dataset)
        ]

    def start(self) -> StandIn:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def environment(self) -> dict[str, str]:
        """The two variables that point the connection's code here instead of at Microsoft."""
        return {"POWERBI_API_URL": self.url, "POWERBI_LOGIN_URL": self.url}


if __name__ == "__main__":
    running = StandIn(int(sys.argv[1]) if len(sys.argv) > 1 else 0).start()
    print(running.url, flush=True)
    threading.Event().wait()
