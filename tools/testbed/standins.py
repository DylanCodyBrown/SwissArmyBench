"""Stand-ins for the cloud services, on 127.0.0.1, over the test bed's made-up company.

- **Power BI**: tests/powerbi_standin.py's workspace, with one more dataset, "Company model", read from
  the same rows as the PostgreSQL database. Its last refresh was the day before the last day, so it holds
  every invoice but that day's: a tie-out against the database finds the regions that are off.
- **Azure Key Vault**: the Key Vault REST shape (`GET /secrets`, `GET /secrets/{name}`, api-version 7.4)
  behind a made-up bearer token. A vault connection in the app reads it with the standard library
  (`KEYVAULT_CODE`); Azure's own SDK will not talk to anything but https, so it cannot be pointed here.

Made-up values only.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tests.powerbi_standin import MadeUpModel, StandIn

from tools.testbed.company import Company, line_amount

COMPANY_DATASET = "99999999-1111-4222-8333-444444444444"
VAULT_TOKEN = "made-up-vault-token-0005"  # noqa: S105 (a made-up token for a stand-in)


def _iso(value: Any) -> Any:
    return f"{value.isoformat()}T00:00:00" if isinstance(value, date) else value


def company_model(company: Company) -> MadeUpModel:
    """The company as a Power BI dataset: five tables, two measures, five relationships (one inactive)."""
    last = max(i["invoice_date"] for i in company.invoices)
    refreshed = last - timedelta(days=1)  # the dataset's last refresh: the last day's invoices are not in it
    orders = company.clean_orders()
    tables: dict[str, list[dict[str, Any]]] = {
        "Customers": [
            {k: c[k] for k in ("customer_id", "customer_name", "region", "segment")}
            for c in company.customers
        ],
        "Products": [
            {k: p[k] for k in ("product_id", "product_name", "category", "unit_price")}
            for p in company.products
        ],
        "Orders": [
            {k: _iso(o[k]) for k in ("order_id", "customer_id", "order_date", "status")} for o in orders
        ],
        "Order Lines": [
            {k: v for k, v in line.items() if k in ("order_id", "line_no", "product_id", "quantity")}
            | {"amount": line_amount(line)}
            for line in company.order_lines
        ],
        "Invoices": [
            {
                k: _iso(i[k])
                for k in ("invoice_id", "order_id", "customer_id", "region", "invoice_date", "amount")
            }
            for i in company.invoices
            if i["invoice_date"] <= refreshed
        ],
    }
    kinds = {int: ("Integer", 6), float: ("Decimal", 10), str: ("Text", 2)}
    columns: list[tuple[str, str, str, int]] = []
    for table, rows in tables.items():
        for name, value in rows[0].items():
            if isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT00:00:00", value):
                columns.append((table, name, "DateTime", 9))
            else:
                word, number = kinds[type(value)]
                columns.append((table, name, word, number))
    measures = [("Order Lines", "Total Sales", "Decimal", 10), ("Invoices", "Invoiced", "Decimal", 10)]
    relationships = [
        ("Orders", "customer_id", "Customers", "customer_id", True, False),
        ("Order Lines", "order_id", "Orders", "order_id", True, False),
        ("Order Lines", "product_id", "Products", "product_id", True, False),
        ("Invoices", "order_id", "Orders", "order_id", True, False),
        ("Invoices", "customer_id", "Customers", "customer_id", False, False),
    ]
    return MadeUpModel(COMPANY_DATASET, "Company model", tables, columns, measures, relationships)


def power_bi(company: Company) -> StandIn:
    """The Power BI stand-in with the company's dataset beside its own three, started."""
    running = StandIn()
    running.models.insert(0, company_model(company))
    return running.start()


# ===== Azure Key Vault =====

KEYVAULT_CODE = """import json
import os
import urllib.request

# Azure Key Vault's REST requests (api-version 7.4). The vault's address and the sign-in's token come
# from the environment: a stand-in on this computer in the tests.
vault_url = os.environ["KEYVAULT_URL"]


def _get(path):
    request = urllib.request.Request(
        f"{vault_url}{path}?api-version=7.4",
        headers={"Authorization": "Bearer " + os.environ["KEYVAULT_TOKEN"]},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def names():
    return [item["id"].rsplit("/", 1)[-1] for item in _get("/secrets")["value"]]


def get(name):
    return _get("/secrets/" + name)["value"]
"""


class KeyVault:
    """Azure Key Vault's two reads, over made-up secrets. Every request is kept (`requests`)."""

    def __init__(self, secrets: dict[str, str]) -> None:
        self.secrets = dict(secrets)
        self.requests: list[dict[str, str]] = []
        vault = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                path, _, query = self.path.partition("?")
                vault.requests.append({"path": path, "query": query})
                if self.headers.get("Authorization") != f"Bearer {VAULT_TOKEN}":
                    self._send(401, {"error": {"code": "Unauthorized", "message": "made-up sign-in refused"}})
                elif "api-version=7.4" not in query:
                    self._send(400, {"error": {"code": "MissingApiVersionParameter"}})
                elif path == "/secrets":
                    listed = [
                        {"id": f"{vault.url}/secrets/{n}", "attributes": {"enabled": True}}
                        for n in vault.secrets
                    ]
                    self._send(200, {"value": listed, "nextLink": None})
                elif (found := re.fullmatch(r"/secrets/([A-Za-z0-9-]+)", path)) and found[1] in vault.secrets:
                    name = found[1]
                    self._send(200, {"value": vault.secrets[name], "id": f"{vault.url}/secrets/{name}/1"})
                else:
                    self._send(
                        404, {"error": {"code": "SecretNotFound", "message": "A secret was not found."}}
                    )

            def _send(self, status: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> KeyVault:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def environment(self) -> dict[str, str]:
        """What a vault connection's code reads: the vault's address and the sign-in's token."""
        return {"KEYVAULT_URL": self.url, "KEYVAULT_TOKEN": VAULT_TOKEN}
