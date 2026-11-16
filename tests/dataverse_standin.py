"""A stand-in for a Dataverse environment on this computer, for tests and screenshots: no real tenant is
ever reached.

It answers the requests the Dataverse connection makes (domain/dataverse.py), the way Microsoft
documents them:

  POST /{tenant}/oauth2/v2.0/token                     the app registration's sign-in (client credentials)
  GET  /msi/token?resource=...                         a managed identity's (IDENTITY_ENDPOINT and
                                                       IDENTITY_HEADER point it here)
  GET  /api/data/v9.2/WhoAmI                           who signed in
  GET  /api/data/v9.2/EntityDefinitions?$select=...&$filter=IsPrivate eq false[&$expand=Attributes(...)]
  GET  /api/data/v9.2/EntityDefinitions(LogicalName='account')/Attributes?$select=...
  GET  /api/data/v9.2/accounts?$select=...&$filter=...&$orderby=...&$top=...&$count=true
       with Prefer: odata.maxpagesize=N (pages joined by @odata.nextLink) and the formatted values
       annotation (a choice column's label, a lookup's name, and, as the real one does, numbers, money
       and dates written out for people: the connection must read those as numbers and dates)
  GET  /api/data/v9.2/accounts?fetchXml=...            a FetchXML query (attributes, conditions, order, top)
  GET  /api/data/v9.2/EntityDefinitions(...)/Attributes(LogicalName='salesstage')/
       Microsoft.Dynamics.CRM.PicklistAttributeMetadata?$expand=OptionSet   a choice column's options
  GET  /api/data/v9.2/RetrieveTotalRecordCount(EntityNames=@p)?@p=["opportunity"]

over a made-up company's sales: accounts, contacts and opportunities (6,200 of them: more than the
5,000 a count and a page stop at), its users (systemuser, shown as User), and a private table that is
never listed. The SQL endpoint (TDS)
cannot be stood in for: tests/test_dataverse.py checks its connection string and token only.

Every request is kept (`requests`), so a test can prove what the sign-in carried. Made-up values only.

    python -m tests.dataverse_standin 8792        # run it by itself (the screenshots do)
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

TENANT = "made-up-tenant-1001"
CLIENT = "made-up-client-1002"
SECRET = "made-up-client-secret-1003"
TOKEN = "made-up-dataverse-token-1004"
IDENTITY_HEADER = "made-up-identity-header-1005"
USER = "aaaaaaaa-1111-4222-8333-444444444444"
ORGANIZATION = "bbbbbbbb-5555-4666-8777-888888888888"
OPPORTUNITIES = 6_200
LABEL = "@OData.Community.Display.V1.FormattedValue"
API = "/api/data/v9.2"

_START = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)


def _id(prefix: int, n: int) -> str:
    return f"{prefix:08x}-0000-4000-8000-{n:012x}"


def _label(text: str) -> dict[str, Any]:
    return {"LocalizedLabels": [{"Label": text, "LanguageCode": 1033}], "UserLocalizedLabel": {"Label": text}}


@dataclass(frozen=True)
class Column:
    name: str
    kind: str  # AttributeType
    title: str
    target: str = ""  # a lookup's table
    options: dict[int, str] = field(default_factory=dict)
    of: str = ""  # AttributeOf
    type_name: str = ""  # AttributeTypeName, when it says more than the type

    def metadata(self) -> dict[str, Any]:
        return {
            "LogicalName": self.name,
            "AttributeType": self.kind,
            "AttributeTypeName": {"Value": self.type_name or f"{self.kind}Type"},
            "DisplayName": _label(self.title) if self.title else {"LocalizedLabels": []},
            "AttributeOf": self.of or None,
            "IsValidForRead": True,
        }

    @property
    def api(self) -> str:
        return f"_{self.name}_value" if self.kind in ("Lookup", "Customer", "Owner") else self.name


INDUSTRY = {1: "Accounting", 7: "Consulting", 19: "Retail", 33: "Transport"}
ACCOUNT_STATE = {0: "Active", 1: "Inactive"}
STAGE = {0: "Qualify", 1: "Develop", 2: "Propose", 3: "Close"}
OPPORTUNITY_STATE = {0: "Open", 1: "Won", 2: "Lost"}
GENDER = {1: "Male", 2: "Female"}

COLUMNS: dict[str, list[Column]] = {
    "account": [
        Column("accountid", "Uniqueidentifier", "Account"),
        Column("name", "String", "Account Name"),
        Column("accountnumber", "String", "Account Number"),
        Column("revenue", "Money", "Annual Revenue"),
        Column("numberofemployees", "Integer", "Number of Employees"),
        Column("industrycode", "Picklist", "Industry", options=INDUSTRY),
        Column("statecode", "State", "Status", options=ACCOUNT_STATE),
        Column("statecodename", "Virtual", "", of="statecode"),
        Column("primarycontactid", "Lookup", "Primary Contact", target="contact"),
        Column("primarycontactidname", "String", "", of="primarycontactid"),
        Column("donotemail", "Boolean", "Do not allow Emails"),
        Column("createdon", "DateTime", "Created On"),
        Column("entityimage", "Virtual", "Default Image", type_name="ImageType"),
    ],
    "contact": [
        Column("contactid", "Uniqueidentifier", "Contact"),
        Column("fullname", "String", "Full Name"),
        Column("emailaddress1", "String", "Email"),
        Column("parentcustomerid", "Customer", "Company Name", target="account"),
        Column("parentcustomeridname", "String", "", of="parentcustomerid"),
        Column("gendercode", "Picklist", "Gender", options=GENDER),
        Column("birthdate", "DateTime", "Birthday"),
    ],
    "opportunity": [
        Column("opportunityid", "Uniqueidentifier", "Opportunity"),
        Column("name", "String", "Topic"),
        Column("parentaccountid", "Lookup", "Account", target="account"),
        Column("parentaccountidname", "String", "", of="parentaccountid"),
        Column("estimatedvalue", "Money", "Est. Revenue"),
        Column("closeprobability", "Integer", "Probability"),
        Column("salesstage", "Picklist", "Sales Stage", options=STAGE),
        Column("statecode", "State", "Status", options=OPPORTUNITY_STATE),
        Column("estimatedclosedate", "DateTime", "Est. Close Date"),
    ],
    "systemuser": [
        Column("systemuserid", "Uniqueidentifier", "User"),
        Column("fullname", "String", "Full Name"),
        Column("internalemailaddress", "String", "Primary Email"),
    ],
    "msdyn_internalcache": [Column("msdyn_internalcacheid", "Uniqueidentifier", "Internal cache")],
}
TABLES: dict[str, tuple[str, str, bool]] = {  # logical name -> (entity set, display name, private)
    "account": ("accounts", "Account", False),
    "contact": ("contacts", "Contact", False),
    "opportunity": ("opportunities", "Opportunity", False),
    "systemuser": ("systemusers", "User", False),  # a display name that says more than its own name
    "msdyn_internalcache": ("msdyn_internalcaches", "Internal cache", True),
}
SETS = {entity_set: logical for logical, (entity_set, _, _) in TABLES.items()}

_ACCOUNT_NAMES = [
    "Bluefin Outfitters", "Copper Kettle Foods", "Driftwood Freight", "Elm Street Books",
    "Foxglove Studio", "Granite Peak Supply", "Harbor Lane Trading", "Ironbark Tools",
    "Juniper Accounting", "Kestrel Couriers", "Lantern Consulting", "Maple Row Grocers",
]  # fmt: skip
_PEOPLE = ["Ada", "Ben", "Cleo", "Dev", "Esme", "Finn", "Gus", "Hana", "Ivo", "Jun"]
_SURNAMES = ["Ashby", "Brook", "Carver", "Dale", "Ellis"]


def records() -> dict[str, list[dict[str, Any]]]:
    """The made-up company's rows, by table, as the Web API's values (lookups as their ids)."""
    accounts = []
    for i, name in enumerate(_ACCOUNT_NAMES, 1):
        accounts.append(
            {
                "accountid": _id(0xA, i),
                "name": name,
                "accountnumber": f"AC-{1000 + i}",
                "revenue": None if i % 5 == 0 else float(120_000 * i + 0.5),
                "numberofemployees": 4 * i + 1,
                "industrycode": list(INDUSTRY)[i % 4],
                "statecode": 1 if i == 12 else 0,
                "primarycontactid": _id(0xC, i * 2),
                "donotemail": i % 3 == 0,
                "createdon": (_START + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "entityimage": None,
            }
        )
    contacts = []
    for i in range(1, 31):
        first, last = _PEOPLE[i % len(_PEOPLE)], _SURNAMES[i % len(_SURNAMES)]
        contacts.append(
            {
                "contactid": _id(0xC, i),
                "fullname": f"{first} {last}",
                "emailaddress1": f"{first.lower()}.{last.lower()}@example.com",
                "parentcustomerid": _id(0xA, (i - 1) % 12 + 1),
                "gendercode": None if i % 7 == 0 else 1 + i % 2,
                "birthdate": None if i % 4 == 0 else f"{1970 + i}-0{1 + i % 9}-15T00:00:00Z",
            }
        )
    opportunities = []
    for i in range(1, OPPORTUNITIES + 1):
        opportunities.append(
            {
                "opportunityid": _id(0x0, i),
                "name": f"Order {i:05d}",
                "parentaccountid": _id(0xA, i % 12 + 1),
                "estimatedvalue": float(500 + (i * 37) % 9_500),
                "closeprobability": (i * 13) % 101,
                "salesstage": i % 4,
                "statecode": i % 3,
                "estimatedclosedate": (_START + timedelta(days=i % 200)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    users = [
        {
            "systemuserid": _id(0x5, i),
            "fullname": name,
            "internalemailaddress": f"{name.split()[0].lower()}@example.com",
        }
        for i, name in enumerate(["Sam Okafor", "Rita Lindqvist", "Tom Achebe"], 1)
    ]
    return {
        "account": accounts,
        "contact": contacts,
        "opportunity": opportunities,
        "systemuser": users,
        "msdyn_internalcache": [],
    }


def _names(rows: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, str], str]:
    """Each row's primary name, by (table, id): a lookup's formatted value."""
    primary = {"account": ("accountid", "name"), "contact": ("contactid", "fullname")}
    return {(table, str(r[key])): str(r[name]) for table, (key, name) in primary.items() for r in rows[table]}


# ===== a tiny OData filter: field op literal [and ...] =====


def _literal(text: str) -> Any:
    text = text.strip()
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1].replace("''", "'")
    if text in ("true", "false"):
        return text == "true"
    if text == "null":
        return None
    return float(text) if "." in text else int(text)


_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and a > b,
    "ge": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b,
    "le": lambda a, b: a is not None and a <= b,
}


class ODataError(ValueError):
    pass


def _matches(row: dict[str, Any], text: str) -> bool:
    for part in re.split(r"\s+and\s+", text.strip()):
        found = re.fullmatch(r"(\w+)\s+(eq|ne|gt|ge|lt|le)\s+(.+)", part.strip())
        if found is None:
            raise ODataError(f"Could not find a property named '{part.strip().split(' ')[0]}'.")
        name, op, value = found.groups()
        key = re.sub(r"^_(\w+)_value$", r"\1", name)
        if key not in row:
            raise ODataError(f"Could not find a property named '{name}' on type 'Microsoft.Dynamics.CRM'.")
        if not _OPS[op](row[key], _literal(value)):
            return False
    return True


class StandIn:
    def __init__(self, port: int = 0) -> None:
        self.requests: list[dict[str, Any]] = []
        self.rows = records()
        self.names = _names(self.rows)
        self.page_cap = 5000  # the most a page holds (Dataverse's own)
        standin = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # quiet
                return

            def _send(self, status: int, body: Any) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; odata.metadata=minimal")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                status, body = standin.get(self.path, {k.lower(): v for k, v in self.headers.items()})
                self._send(status, body)

            def do_POST(self) -> None:
                sent = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                status, body = standin.token(self.path, sent)
                self._send(status, body)

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    # ===== the sign-ins =====

    def token(self, path: str, body: bytes) -> tuple[int, Any]:
        form = {k: v[0] for k, v in parse_qs(body.decode()).items()}
        tenant = path.split("/")[1]
        self.requests.append({"what": "token", "tenant": tenant, "form": form})
        right = (tenant, form.get("client_id"), form.get("client_secret")) == (TENANT, CLIENT, SECRET)
        if (
            not path.endswith("/oauth2/v2.0/token")
            or not right
            or form.get("scope") != f"{self.url}/.default"
        ):
            description = (
                "AADSTS7000215: Invalid client secret provided. Ensure the secret being sent in the request "
                "is the client secret value, not the client secret ID.\r\nTrace ID: made-up"
            )
            return 401, {"error": "invalid_client", "error_description": description}
        return 200, {"token_type": "Bearer", "expires_in": 3599, "access_token": TOKEN}

    def managed(self, query: dict[str, str], headers: dict[str, str]) -> tuple[int, Any]:
        self.requests.append({"what": "managed identity", "query": query})
        if headers.get("x-identity-header") != IDENTITY_HEADER or query.get("resource") != self.url:
            return 400, {"error": "invalid_request", "error_description": "The identity header is not right."}
        expires = str(int(time.time()) + 3600)
        return 200, {
            "access_token": TOKEN,
            "expires_on": expires,
            "resource": self.url,
            "token_type": "Bearer",
        }

    # ===== the Web API =====

    def get(self, path: str, headers: dict[str, str]) -> tuple[int, Any]:
        parts = urlsplit(path)
        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        if parts.path == "/msi/token":
            return self.managed(query, headers)
        authorization = headers.get("authorization", "")
        self.requests.append(
            {
                "what": "get",
                "path": unquote(parts.path),
                "query": query,
                "authorization": authorization,
                "prefer": headers.get("prefer", ""),
            }
        )
        if not parts.path.startswith(API + "/"):
            return 404, _refusal("0x80060888", "Resource not found for the segment.")
        if authorization != f"Bearer {TOKEN}":
            return 401, _refusal("0x80072560", "The user is not a member of the organization.")
        rest = unquote(parts.path[len(API) + 1 :])
        labels = "FormattedValue" in headers.get("prefer", "")
        try:
            if rest == "WhoAmI":
                return 200, {"UserId": USER, "BusinessUnitId": USER, "OrganizationId": ORGANIZATION}
            if rest == "EntityDefinitions":
                return 200, {"value": self.definitions(query)}
            found = re.fullmatch(r"EntityDefinitions\(LogicalName='(\w+)'\)/Attributes", rest)
            if found:
                if found.group(1) not in COLUMNS:
                    return 404, _refusal(
                        "0x80040217", f"Could not find an entity with name {found.group(1)}."
                    )
                return 200, {"value": [c.metadata() for c in COLUMNS[found.group(1)]]}
            found = re.fullmatch(
                r"EntityDefinitions\(LogicalName='(\w+)'\)/Attributes\(LogicalName='(\w+)'\)/"
                r"Microsoft\.Dynamics\.CRM\.(\w+)AttributeMetadata",
                rest,
            )
            if found:
                return self.options(*found.groups())
            if rest == "RetrieveTotalRecordCount(EntityNames=@p)":
                wanted = json.loads(query.get("@p", "[]"))
                values = [len(self.rows[n]) for n in wanted]
                return 200, {"EntityRecordCountCollection": {"Count": len(wanted), "IsReadOnly": False,
                                                             "Keys": wanted, "Values": values}}  # fmt: skip
            if rest in SETS:
                if "fetchXml" in query:
                    return 200, {"value": self.fetch(SETS[rest], query["fetchXml"], labels)}
                return 200, self.read(rest, query, labels, headers.get("prefer", ""))
        except ODataError as error:
            return 400, _refusal("0x80060888", str(error))
        return 404, _refusal("0x80060888", f"Resource not found for the segment '{rest}'.")

    def options(self, table: str, name: str, kind: str) -> tuple[int, Any]:
        """A choice column's options, as its PicklistAttributeMetadata (or State, Status) gives them."""
        column = next((c for c in COLUMNS.get(table, []) if c.name == name), None)
        if column is None or not column.options or column.kind != kind:
            message = f"The attribute {name} is not a {kind}AttributeMetadata."
            return 404, _refusal("0x80040217", message)
        listed = [{"Value": v, "Label": _label(words)} for v, words in column.options.items()]
        return 200, {"LogicalName": name, "OptionSet": {"Options": listed}}

    def definitions(self, query: dict[str, str]) -> list[dict[str, Any]]:
        listed: list[dict[str, Any]] = []
        for logical, (entity_set, title, private) in TABLES.items():
            if private and "IsPrivate eq false" in query.get("$filter", ""):
                continue
            table: dict[str, Any] = {
                "LogicalName": logical,
                "EntitySetName": entity_set,
                "DisplayName": _label(title),
                "PrimaryIdAttribute": f"{logical}id",
                "PrimaryNameAttribute": "fullname" if logical == "contact" else "name",
                "MetadataId": _id(0xE, len(listed) + 1),
            }
            if query.get("$expand", "").startswith("Attributes"):
                table["Attributes"] = [c.metadata() for c in COLUMNS[logical]]
            listed.append(table)
        return listed

    def shaped(self, table: str, row: dict[str, Any], picked: list[Column], labels: bool) -> dict[str, Any]:
        """A row as the Web API writes it: lookups as _x_value, and with the annotations asked for."""
        out: dict[str, Any] = {"@odata.etag": 'W/"1000"'}
        for c in picked:
            value = row.get(c.name)
            out[c.api] = value
            if not labels or value is None:
                continue
            if c.options:
                out[c.api + LABEL] = c.options.get(int(value), str(value))
            elif c.target:
                out[c.api + LABEL] = self.names.get((c.target, str(value)), "")
                out[c.api + "@Microsoft.Dynamics.CRM.lookuplogicalname"] = c.target
            elif c.kind == "Money":
                out[c.api + LABEL] = f"${value:,.2f}"
            elif c.kind == "Integer":
                out[c.api + LABEL] = f"{value:,}"
            elif c.kind == "Boolean":
                out[c.api + LABEL] = "Yes" if value else "No"
            elif c.kind == "DateTime":
                out[c.api + LABEL] = datetime.fromisoformat(value.replace("Z", "+00:00")).strftime(
                    "%m/%d/%Y %I:%M %p"
                )
        return out

    def read(self, entity_set: str, query: dict[str, str], labels: bool, prefer: str) -> dict[str, Any]:
        table = SETS[entity_set]
        readable = [c for c in COLUMNS[table] if not c.of and c.kind != "Virtual"]
        picked = readable
        if query.get("$select"):
            by_api = {c.api: c for c in readable}
            missing = [s for s in query["$select"].split(",") if s not in by_api]
            if missing:
                raise ODataError(
                    f"Could not find a property named '{missing[0]}' on type "
                    f"'Microsoft.Dynamics.CRM.{table}'."
                )
            picked = [by_api[s] for s in query["$select"].split(",")]
        rows = [r for r in self.rows[table] if not query.get("$filter") or _matches(r, query["$filter"])]
        if query.get("$orderby"):
            name, _, way = query["$orderby"].partition(" ")
            key = re.sub(r"^_(\w+)_value$", r"\1", name)
            rows = sorted(rows, key=lambda r: (r.get(key) is None, r.get(key)), reverse=way == "desc")
        matched = len(rows)  # $count counts every match, whatever $top keeps (OData's rule)
        if "$top" in query:
            rows = rows[: int(query["$top"])]
        asked = re.search(r"odata\.maxpagesize=(\d+)", prefer)
        size = min(self.page_cap, int(asked.group(1)) if asked else self.page_cap)
        start = int(query.get("$skiptoken", "0"))
        page = rows[start : start + size]
        answer: dict[str, Any] = {"@odata.context": f"{self.url}{API}/$metadata#{entity_set}"}
        if query.get("$count") == "true":
            answer["@odata.count"] = min(matched, 5000)
            answer["@Microsoft.Dynamics.CRM.totalrecordcount"] = -1
            answer["@Microsoft.Dynamics.CRM.totalrecordcountlimitexceeded"] = matched > 5000
        answer["value"] = [self.shaped(table, r, picked, labels) for r in page]
        if start + size < len(rows):
            kept = "&".join(f"{k}={v}" for k, v in query.items() if k != "$skiptoken")
            answer["@odata.nextLink"] = f"{self.url}{API}/{entity_set}?{kept}&$skiptoken={start + size}"
        return answer

    def fetch(self, table: str, fetch_xml: str, labels: bool) -> list[dict[str, Any]]:
        try:
            root = ElementTree.fromstring(fetch_xml)  # noqa: S314 (the tests' own made-up FetchXML)
        except ElementTree.ParseError as error:
            raise ODataError(f"The FetchXML is not well formed: {error}") from None
        entity = root.find("entity")
        if entity is None or entity.get("name") != table:
            raise ODataError("The FetchXML's entity is not this entity set's.")
        by_name = {c.name: c for c in COLUMNS[table] if not c.of and c.kind != "Virtual"}
        named = [a.get("name", "") for a in entity.findall("attribute")]
        picked = [by_name[n] for n in named if n in by_name] or list(by_name.values())
        rows = list(self.rows[table])
        for condition in entity.iter("condition"):
            name, op, value = (
                condition.get("attribute", ""),
                condition.get("operator", "eq"),
                condition.get("value"),
            )
            wanted = None if value is None else int(value) if value.lstrip("-").isdigit() else value
            rows = [r for r in rows if _OPS.get(op, _OPS["eq"])(r.get(name), wanted)]
        for order in entity.findall("order"):
            name = order.get("attribute", "")
            rows.sort(
                key=lambda r: (r.get(name) is None, r.get(name)), reverse=order.get("descending") == "true"
            )
        top = root.get("top") or root.get("count")
        return [self.shaped(table, r, picked, labels) for r in rows[: int(top) if top else 5000]]

    def gets(self) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["what"] == "get"]

    def start(self) -> StandIn:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def environment(self) -> dict[str, str]:
        """The variables that point the sign-ins here instead of at Microsoft and Azure."""
        return {
            "DATAVERSE_LOGIN_URL": self.url,
            "IDENTITY_ENDPOINT": f"{self.url}/msi/token",
            "IDENTITY_HEADER": IDENTITY_HEADER,
        }


def _refusal(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


if __name__ == "__main__":
    running = StandIn(int(sys.argv[1]) if len(sys.argv) > 1 else 0).start()
    print(running.url, flush=True)
    threading.Event().wait()
