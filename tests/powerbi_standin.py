"""A stand-in for Power BI on this computer, for tests and screenshots: no real tenant is ever reached.

It answers the two requests the Power BI dataset connection makes, the way Microsoft documents them:

  POST /{tenant}/oauth2/v2.0/token                                    the client credentials sign-in
  POST /v1.0/myorg/groups/{workspace}/datasets/{dataset}/executeQueries   one DAX query, rows as JSON

over a made-up model: Sales, Customer, Product and Date, three measures, four relationships (one of
them inactive, one filtering both ways) and one of the date tables Power BI makes by itself. It knows
only the DAX the app sends (the INFO functions, TOPN, COUNTROWS, a table by its name) and one
SUMMARIZECOLUMNS for a notebook cell; anything else is refused in the real service's error shape.

Every request is kept (`requests`), so a test can prove what the sign-in carried. Made-up values only.

    python -m tests.powerbi_standin 8791        # run it by itself (the screenshots do)
"""

from __future__ import annotations

import json
import re
import sys
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs

TENANT = "made-up-tenant-0001"
CLIENT = "made-up-client-0002"
SECRET = "made-up-client-secret-0003"
WORKSPACE = "11111111-aaaa-4bbb-8ccc-222222222222"
DATASET = "33333333-dddd-4eee-8fff-444444444444"
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
_TABLE_IDS = {name: 100 + i for i, name in enumerate(dict.fromkeys(c[0] for c in COLUMNS))}
_COLUMN_IDS = {(t, c): 1000 + i for i, (t, c, _, _) in enumerate(COLUMNS)}


def _keyed(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A function's rows as Power BI writes them: each column as [Name]."""
    return [{f"[{k}]": v for k, v in row.items()} for row in rows]


def _info(function: str) -> list[dict[str, Any]] | None:
    """The INFO functions' answers over the made-up model; None for one this stand-in does not know."""
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


def _table_rows(name: str) -> list[dict[str, Any]]:
    found = tables().get(name.replace("''", "'"))
    if found is None:
        raise DaxError(f"Cannot find table '{name}'.")
    return [{f"{name}[{k}]": v for k, v in row.items()} for row in found]


def evaluate(dax: str, view_forms: bool = True, info_forms: bool = True) -> list[dict[str, Any]]:
    """One DAX query's rows, keyed as Power BI keys them (Table[Column], [Name])."""
    text = re.sub(r"(--|//)[^\n]*", "", dax).strip()  # a DAX cell may begin with a comment line
    text = re.sub(r"\s+", " ", text)
    if (found := re.fullmatch(r"EVALUATE ROW\(\s*\"(\w+)\"\s*,\s*1\s*\)", text, re.I)) is not None:
        return [{f"[{found.group(1)}]": 1}]
    if (found := re.fullmatch(r"EVALUATE (INFO(?:\.VIEW)?\.[A-Z]+)\(\)", text, re.I)) is not None:
        function = found.group(1).upper()
        allowed = view_forms if function.startswith("INFO.VIEW.") else info_forms
        rows = _info(function) if allowed else None
        if rows is None:
            raise DaxError(
                f"Failed to resolve name '{found.group(1)}'. It is not a valid table, variable, or "
                "function name."
            )
        return _keyed(rows)
    if re.fullmatch(r"EVALUATE COLUMNSTATISTICS\(\)", text, re.I):
        return _keyed(
            [{"Table Name": t, "Column Name": c, "Cardinality": len(tables()[t])} for t, c, _, _ in COLUMNS]
            + [
                {"Table Name": t, "Column Name": f"RowNumber-made-up-{i}", "Cardinality": 1}
                for t, i in _TABLE_IDS.items()
            ]
        )
    if (
        found := re.fullmatch(r"EVALUATE TOPN\(\s*(\d+)\s*,\s*'((?:[^']|'')+)'\s*\)", text, re.I)
    ) is not None:
        return _table_rows(found.group(2))[: int(found.group(1))]
    if (found := re.fullmatch(r"EVALUATE '((?:[^']|'')+)'", text, re.I)) is not None:
        return _table_rows(found.group(1))
    if (
        found := re.fullmatch(
            r"EVALUATE ROW\(\s*\"(\w+)\"\s*,\s*COUNTROWS\(\s*'((?:[^']|'')+)'\s*\)\s*\)", text, re.I
        )
    ) is not None:
        return [{f"[{found.group(1)}]": len(_table_rows(found.group(2)))}]
    if re.fullmatch(
        r"EVALUATE SUMMARIZECOLUMNS\(\s*'Customer'\[Region\]\s*,\s*"
        r"\"Total Sales\"\s*,\s*\[Total Sales\]\s*\)",
        text,
        re.I,
    ):
        model = tables()
        region = {c["CustomerKey"]: c["Region"] for c in model["Customer"]}
        totals: dict[Any, float] = {}
        for sale in model["Sales"]:
            where = region[sale["CustomerKey"]]
            totals[where] = totals.get(where, 0.0) + (sale["Amount"] or 0.0)
        return [
            {"Customer[Region]": where, "[Total Sales]": round(total, 2)} for where, total in totals.items()
        ]
    raise DaxError("Query (1, 1) The syntax is incorrect, or this stand-in does not know the query.")


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
        standin = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def _send(self, status: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                status, answer = standin.answer(self.path, body, self.headers.get("Authorization") or "")
                self._send(status, answer)

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

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
        if found.groups() != (WORKSPACE, DATASET):
            return 404, _refusal("PowerBIEntityNotFound")
        try:
            rows = evaluate(dax, self.view_forms, self.info_forms)
        except DaxError as error:
            return 400, _refusal("DatasetExecuteQueriesError", str(error))
        if not sent.get("serializerSettings", {}).get("includeNulls"):
            rows = [{k: v for k, v in row.items() if v is not None} for row in rows]  # as the real one does
        return 200, {"results": [{"tables": [{"rows": rows}]}]}

    def queries(self) -> list[str]:
        """Every DAX query received, in order."""
        return [r["dax"] for r in self.requests if r["what"] == "query"]

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
