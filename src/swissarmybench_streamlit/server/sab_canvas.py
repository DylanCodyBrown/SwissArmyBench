"""Swiss Army Bench's canvas runtime: each widget run in its own place.

render() runs a widget's code with its properties' values. A widget that fails shows its own error panel in
its place and the rest of the page runs; a table or a variable that is missing is said there; a slow one
shows a spinner while it works. Made-up sample data stands in when no table is picked.

This file is the runtime itself: the builder (domain/canvas_build.py) reads its text and writes it beside
every played, launched and exported app's pages as sab_canvas.py (folded into an export's app.py). It runs
there, in the app's own Python with Streamlit, never in Swiss Army Bench: nothing of the app imports it.
"""

from __future__ import annotations

import contextvars
import hashlib
import html
import importlib
import linecache
import os
import re
import traceback
from pathlib import Path
from typing import Any

import sab_widgets
import streamlit as st

try:  # the Performance Analyzer's helper: beside a launched app's pages only (an export has none)
    import sab_perf as _perf
except Exception:
    _perf = None

# Play's stamp of the tables it reads (beside a played or launched app only, never an export's): rewritten
# when one changes, so Streamlit's own file watcher runs the open pages again by itself.
try:
    import sab_live  # noqa: F401
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_INSTANCE: contextvars.ContextVar[str] = contextvars.ContextVar("sab_instance", default="w")
_COMPILED: dict[tuple[str, str], Any] = {}


class Missing(Exception):
    """A table or a variable a widget needs that is not here: said in its place."""


def key(name: str = "") -> str:
    """A widget key of this instance's own (two instances of one widget never share a key)."""
    instance = _INSTANCE.get()
    return f"{instance}-{name}" if name else instance


SAMPLES = ("sales", "orders", "products", "tickets", "stock")


def sample(rows: int | None = None, kind: str = "sales") -> Any:
    """Made-up data, the same every time, by kind:
    sales     month, region, product, revenue, units, margin, lat, lon (24 rows)
    orders    an export's orders, headers in its own words: Order No, Cust. name, Product, Qty, ... (12)
    products  product_id, sku, product_name, category, unit_price, launched_on, discontinued (8)
    tickets   support tickets: ticket_id, customer_name, subject, priority, status, opened_at, ... (18)
    stock     store, product_id, product_name, on_hand, on_order, reorder_point (24)"""
    if kind == "sales":
        return _sales(24 if rows is None else int(rows))
    made = _SAMPLE.get(kind)
    if made is None:
        raise ValueError(f"sample's kind is one of {', '.join(SAMPLES)}.")
    frame = made()
    return frame if rows is None else frame.head(int(rows))


def _sales(rows: int) -> Any:
    import pandas as pd

    regions = ["North", "South", "East", "West"]
    products = ["Alpha", "Beta", "Gamma"]
    points = {"North": (52.5, 13.4), "South": (48.1, 11.6), "East": (51.3, 12.4), "West": (50.9, 6.9)}
    made = []
    for i in range(rows):
        region = regions[i % 4]
        lat, lon = points[region]
        revenue = 1000 + (i * 137) % 900 + (i % 4) * 150
        made.append(
            {
                "month": f"2026-{(i // 2) % 12 + 1:02d}-01",
                "region": region,
                "product": products[i % 3],
                "revenue": float(revenue),
                "units": 10 + (i * 7) % 40,
                "margin": round(0.1 + ((i * 13) % 20) / 100, 2),
                "lat": lat + (i % 5) * 0.05,
                "lon": lon + (i % 3) * 0.05,
            }
        )
    frame = pd.DataFrame(made)
    frame["month"] = pd.to_datetime(frame["month"])
    return frame


def _orders() -> Any:
    import pandas as pd

    people = ["Ada Ashdown", "Bram Brookfield", "Cleo Calloway", "Dov Dunmore", "Esme Everly"]
    products = ["Desk lamp", "Kettle", "Planter", "Wok", "Notebook"]
    return pd.DataFrame(
        [
            {
                "Order No": 81000 + at,
                "Cust. name": people[at % 5],
                "Product": products[(at * 3) % 5],
                "Qty": [2, 1, 4, 0, 3, 12, 1, 2][at % 8],
                "Unit price": [24.5, 39.0, 12.99, 9.5, 3.25][at % 5],
                "Order date": pd.Timestamp(2026, 11, 1 + at),
                "Status": ["Delivered", "Shipped", "Pending", "Delivred"][at % 4],
            }
            for at in range(12)
        ]
    )


def _products() -> Any:
    import datetime

    import pandas as pd

    names = ["Desk lamp", "Storage box", "Cushion", "Planter", "Trowel", "Kettle", "Claw hammer", "Notebook"]
    categories = ["Lighting", "Storage", "Textiles", "Planters", "Garden tools", "Small appliances",
                  "Hand tools", "Paper"]  # fmt: skip
    rows = [
        {
            "product_id": 100 + at,
            "sku": f"LG-{100 + at:06d}",
            "product_name": name,
            "category": categories[at],
            "unit_price": round(4.99 + at * 7.5, 2),
            "launched_on": datetime.date(2024, 1 + at, 10),
            "discontinued": at == 5,
        }
        for at, name in enumerate(names)
    ]
    frame = pd.DataFrame(rows)
    frame["launched_on"] = pd.to_datetime(frame["launched_on"])
    return frame


def _tickets() -> Any:
    import datetime

    import pandas as pd

    subjects = ["Where is my order?", "Item arrived damaged", "Wrong item sent", "Refund not received",
                "Change delivery address", "Invoice copy please", "Product question",
                "Missing part"]  # fmt: skip
    people = ["Ada Ashdown", "Bram Brookfield", "Cleo Calloway", "Dov Dunmore", "Esme Everly",
              "Finn Fairbank"]  # fmt: skip
    statuses = ["New", "Open", "Waiting on customer", "Open", "Resolved", "Closed"]
    priorities = ["Normal", "High", "Low", "Urgent", "Normal", "Normal"]
    hours = {"Urgent": 4, "High": 8, "Normal": 24, "Low": 72}
    start = datetime.datetime(2026, 10, 20, 8, 0)
    rows = []
    for at in range(18):
        priority = priorities[at % 6]
        status = statuses[(at * 5) % 6]
        opened = start + datetime.timedelta(hours=at * 7)
        rows.append(
            {
                "ticket_id": 9100 + at,
                "customer_name": people[at % 6],
                "subject": subjects[at % 8],
                "priority": priority,
                "status": status,
                "channel": ["Email", "Chat", "Phone"][at % 3],
                "opened_at": opened,
                "closed_at": opened + datetime.timedelta(hours=5 + at)
                if status in ("Resolved", "Closed")
                else None,
                "sla_hours": hours[priority],
                "first_response_minutes": (at * 97) % 1500 + 5,
            }
        )
    frame = pd.DataFrame(rows)
    frame["closed_at"] = pd.to_datetime(frame["closed_at"])
    return frame


def _stock() -> Any:
    import pandas as pd

    names = ["Desk lamp", "Storage box", "Cushion", "Planter", "Trowel", "Kettle", "Claw hammer",
             "Screw pack", "Notebook", "Shipping box", "Wok", "Bench"]  # fmt: skip
    rows = []
    for at, name in enumerate(names):
        for store in ("Larkfield Shop", "Marshby Depot"):
            on_hand = (at * 37 + len(store) * 11) % 140 - 15
            rows.append(
                {
                    "store": store,
                    "product_id": 100 + at,
                    "product_name": name,
                    "on_hand": max(on_hand, 0),
                    "on_order": 48 if on_hand < 20 else 0,
                    "reorder_point": 20 + (at % 4) * 5,
                }
            )
    return pd.DataFrame(rows)


_SAMPLE = {"orders": _orders, "products": _products, "tickets": _tickets, "stock": _stock}


def _stem(name: str) -> str:
    """A table's file name in data/ (canvas_build.table_stem's twin): its own name, or made safe."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,80}", name):
        return name
    base = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")[:60] or "table"
    return f"{base}_{hashlib.sha256(name.encode('utf-8')).hexdigest()[:8]}"


def as_table(found: Any, name: str = "") -> Any:
    """A value as a table: a DataFrame as it is, records (a list of dicts) or columns (a dict of lists) made
    one; None stays None."""
    import pandas as pd

    if found is None or isinstance(found, pd.DataFrame):
        return found
    if isinstance(found, (list, dict)):
        try:
            return pd.DataFrame(found)
        except (ValueError, TypeError):
            pass
    raise Missing(f"{name or 'The value'} is not a table: wire it to a table, or an Out that holds one.")


_READ: dict[str, tuple[tuple[int, int], Any]] = {}


def _parquet(path: Path) -> Any:
    """A table's Parquet as a DataFrame of the caller's own: read again only when its file changed (Play
    writes it again when the table changes), else the frame read before, copied (a widget may change it)."""
    import pandas as pd

    try:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        kept = _READ.get(str(path))
        if kept is None or kept[0] != stamp:
            import io

            # Its bytes in one read: a file written again meanwhile (a whole new file put in its place)
            # is never read half from the one and half from the other.
            kept = (stamp, pd.read_parquet(io.BytesIO(path.read_bytes())))
            _READ[str(path)] = kept
    except OSError:
        return None
    return kept[1].copy()


def table(name: str = "") -> Any:
    """A table by its name: the canvas's own copy (data/<name>.parquet; in Play an open table, a sandbox
    table or a connection's `[Conn].table` as it is now: written again when it changes), else data.py's,
    else none: said. No name: the made-up sample."""
    if not name:
        return sample()
    found = _parquet(_HERE / "data" / f"{_stem(name)}.parquet")
    if found is not None:
        return found
    if name.startswith("["):
        if (_HERE / "connections.py").is_file() and (_HERE / "adapter.py").is_file():
            return _connection_table(name).to_pandas()  # an export: through the project's adapter
        raise Missing(
            f"The table {name[:80]} was not read: its connection did not answer, or it is past the query "
            "limit. Check the connection on the Connections page."
        )
    try:
        import data as _data  # the project's data.py, when it is beside the app
    except Exception:
        _data = None
    found = getattr(_data, name, None) if _data is not None else None
    if found is not None:
        return found
    raise Missing(f"The table {name} is not here: open it in Swiss Army Bench, or pick another table.")


def _kept(fn: Any) -> Any:
    """Kept across reruns (Streamlit's cache_resource; a stand-in Streamlit without it: as it is)."""
    cache = getattr(st, "cache_resource", None)
    return cache(show_spinner=False)(fn) if cache is not None else fn


@_kept
def _connection_table(name: str) -> Any:
    """`[Conn].table` read once through adapter.py and connections.py beside the app (an exported project:
    each connection's own code, its variables set where it runs), kept until the app restarts."""
    import adapter
    import connections  # noqa: F401  (adapter.use: each connection's name to its own client)

    found = re.match(r"^\[([^\[\]]+)\]\.(.+)$", name)
    if found is None:
        raise Missing(f"{name[:80]} is not a connection's table: write it as [Connection].table.")
    reader, _ = adapter.read(found.group(1), found.group(2).strip('"'))
    return reader.read_all()


LIMIT = 1000


def choices(options: Any, frame: Any = None, column: str = "", limit: int = LIMIT) -> list[Any]:
    """A select's choices: a table's column's distinct values, sorted (the first `limit`, with a note), or the
    typed options when no table is wired (or no column picked)."""
    if frame is None or not column:
        return list(options or [])
    frame = as_table(frame, "options_table")
    if column not in frame.columns:
        raise Missing(f"The choices' table has no column {column}: pick another in Properties.")
    values = frame[column].dropna().unique().tolist()
    try:
        values.sort()
    except TypeError:  # mixed kinds: as text
        values.sort(key=str)
    if len(values) > limit:
        st.caption(f"The first {limit:,} of {len(values):,} choices from {column}.")
        values = values[:limit]
    return [v.item() if hasattr(v, "item") else v for v in values]


def marked(text: str, needed: bool) -> str:
    """The inputs' one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def problem(message: str) -> None:
    """The inputs' one error look, under the input."""
    st.markdown(f":red[{message}]")


def pick(payload: Any, path: str = "") -> Any:
    """A part of an event's payload by its dotted path ("values.store"; empty: the whole payload)."""
    found = payload
    for part in [p for p in (path or "").split(".") if p]:
        found = found.get(part) if isinstance(found, dict) else None
    return found


# ===== API actions: every call through api_adapter (the file beside this one), one envelope =====

_ACTION = re.compile(r"^(?:\[([^\[\]]{1,120})\] )?(GET|POST|PUT|PATCH|DELETE) (/\S*)$")
_KEPT: dict[str, Any] = {}


def _actions() -> dict[str, Any]:
    """sab_actions.json beside the app: each API's actions as they were when the app was built (their inputs,
    their body's fields, the last learned shape: types only, never a value)."""
    if "apis" not in _KEPT:
        try:
            import json

            _KEPT["apis"] = json.loads((_HERE / "sab_actions.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _KEPT["apis"] = {}
    kept: dict[str, Any] = _KEPT["apis"]
    return kept


def _unsent(said: str, where: str = "api") -> dict[str, Any]:
    """The envelope of a call that could not be made here (no API to send it to): api_adapter's own shape."""
    return {
        "ok": False, "status": 0, "action": "", "api": "", "kind": "empty", "format": "empty",
        "paging": {"pages": 0, "by": "", "more": False, "stopped": "", "retried": 0},
        "shape": {}, "sent": {}, "raw": None,
        "error": {"error": said, "where": where, "fixes": [], "details": ""},
    }  # fmt: skip


def _api(aa: Any, name: str, root: bool, timeout: float) -> Any:
    """Where an API's actions are sent from this app: the local sandbox API at SAB_API_URL (its key
    SAB_API_KEY, its base path SAB_API_BASE: Play and Launch give the running sandbox's, a host the deployed
    API's); another API through its own client file beside the app (API_<name>.py: its sign-in from the
    variables set where the app runs)."""
    if name == "local":
        base = os.environ.get("SAB_API_URL", "")
        if not base:
            raise aa.ActionError("Run the local sandbox API (the APIs page), then Play again.", "api")
        base = base.rstrip("/") + ("" if root else os.environ.get("SAB_API_BASE", ""))
        return aa.http(base, {"type": "bearer", "variable": "SAB_API_KEY"}, timeout, "local")
    module = (_actions().get(name) or {}).get("module")
    if not module:
        raise aa.ActionError(f"{name} is not an API of this app: pick its action again on the canvas.", "api")
    try:
        made = importlib.import_module(str(module))
        client = next(
            v
            for v in vars(made).values()
            if isinstance(v, type) and hasattr(v, "_send") and v.__module__ == made.__name__
        )()
    except Exception as error:
        raise aa.ActionError(f"{name} could not be set up here: {error}", "api") from None
    return aa.from_client(client, name)


def takes(endpoint: str) -> dict[str, Any]:
    """What an action takes, as the app knew it when it was built: {"inputs": [...], "body": [...]}, each
    {"name", "type", "required", "box": text | number | switch | date | datetime | dropdown | json,
    "choices"?}; {"kind"}: what it answers (records, record, value ...), once learned."""
    found = _ACTION.match(str(endpoint or ""))
    kept: dict[str, Any] = {}
    if found:
        apis = _actions().get(found.group(1) or "local") or {}
        kept = (apis.get("actions") or {}).get(f"{found.group(2)} {found.group(3)}") or {}
    return {
        "inputs": list(kept.get("inputs") or []),
        "body": list(kept.get("body") or []),
        "kind": str(kept.get("kind") or ""),
    }


def action(
    endpoint: str,
    inputs: Any = None,
    *,
    query: Any = None,
    body: Any = None,
    pages: int = 1,
    timeout: float = 30.0,
    root: bool = False,
) -> dict[str, Any]:
    """One call of any API's action through api_adapter, its one envelope. `endpoint`: "GET /orders/{id}" (the
    project's local sandbox API) or "[Orders] GET /orders/{id}" (another API). `inputs`: its inputs by name
    (a path's, a query's, the body's fields), checked first; `query`: more query values, sent as given;
    `body`: the whole body. `pages`: the pages followed at most (1: one request).

    The envelope: answer["ok"]; answer["kind"] (records, record, value, file, empty, text) and the answer in
    that shape (answer["records"]: rows by field path; answer["record"]; answer["value"]); answer["paging"]
    (more: there are more pages); answer["raw"]["body"] (as it came); answer["error"] (said(answer): one
    line for the widget's own place). data(answer) is the answer in its shape."""
    found = _ACTION.match(str(endpoint or ""))
    if not found:
        return _unsent(f"{str(endpoint)[:80]!r} is not an action: as GET /orders, or [Orders] GET /orders.")
    try:
        import api_adapter as aa  # beside the app's pages: Play, Launch and Export write it
    except ImportError:
        return _unsent("api_adapter.py is not beside this app: Play it again (or export it again).")
    import dataclasses

    name, method, path = found.group(1) or "local", found.group(2), found.group(3)
    kept = ((_actions().get(name) or {}).get("actions") or {}).get(f"{method} {path}") or {}
    if kept.get("action"):
        one = dataclasses.replace(aa.Action.from_json(kept["action"]), api=name)
    else:  # an action the app did not know when it was built: its path's {names} are its inputs
        names = list(dict.fromkeys(re.findall(r"\{(\w+)\}", path)))
        needed = tuple(aa.Input(n, "path", required=True) for n in names)
        one = aa.Action(f"{method} {path}", method, path, name, inputs=needed)
    given = dict(inputs or {})
    asked = {k: v for k, v in dict(query or {}).items() if v is not None}
    known = {i.name for i in one.inputs} | {b.name for b in one.body} | {"body"}
    free = [k for k in given if k not in known]
    if free and one.writes and not one.body and body is None:  # an undeclared body: the inputs are its fields
        body = {k: given.pop(k) for k in free}
        free = []
    extra = [k for k in [*free, *asked] if k not in {i.name for i in one.inputs}]
    if extra:  # query values the specification does not name are sent all the same
        one = dataclasses.replace(
            one, inputs=one.inputs + tuple(aa.Input(k, "query") for k in dict.fromkeys(extra))
        )
    sent = given | asked | ({"body": body} if body is not None else {})
    try:
        target = _api(aa, name, root, timeout)
    except aa.ActionError as error:
        return _unsent(str(error), error.where or "api")
    answer: dict[str, Any] = aa.run(
        one, sent, api=target, known=kept.get("known"), renames=kept.get("renames") or {},
        max_pages=max(1, int(pages)), retries=1, who="widget",
    )  # fmt: skip
    return answer


def said(answer: Any) -> str:
    """A failed call's words in one line, for the widget's own place (empty: it worked)."""
    error = (answer or {}).get("error") or {}
    words, details = str(error.get("error") or ""), str(error.get("details") or "")
    return f"{words} {details}".strip() if details and details not in words else words


def data(answer: Any) -> Any:
    """An answer in its shape: its records (a list of rows, fields by path: customer.id), its one record
    (whole), its value, its file or its text; None when it failed or answered nothing."""
    if not answer or not answer.get("ok"):
        return None
    kind = str(answer.get("kind"))
    return answer.get(kind) if kind in ("records", "record", "value", "file", "text") else None


def _for_in(answer: dict[str, Any], kind: str) -> Any:
    """An answer as an In of `kind` takes it: a table its records (one record a table of one row), a dict
    the record or the answer as it came, anything else the answer in its shape."""
    raw = (answer.get("raw") or {}).get("body")
    if kind.startswith(("Table", "list")):
        if answer.get("kind") == "records":
            return answer.get("records") or []
        return [answer["flat"]] if answer.get("kind") == "record" and kind.startswith("Table") else raw
    if kind == "dict":
        return answer["record"] if answer.get("kind") == "record" else raw
    found = data(answer)
    return raw if found is None else found


def api_call(
    method: str, path: str, body: Any = None, query: Any = None, root: bool = False
) -> tuple[Any, Any]:
    """One request to the project's local sandbox API, through api_adapter: (the answer as it came, the
    problem). The older form of action(), kept for the widgets written on it."""
    answer = action(f"{method} {path}", None, query=query, body=body, root=root)
    if answer["ok"]:
        return (answer.get("raw") or {}).get("body"), None
    return None, said(answer)


# ===== the contract: In, Out, Event =====


class _Marker:
    """In[...], Out[...], Event[...]: what a widget declares (read by the app from its code, never run)."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getitem__(self, kind: Any) -> Any:
        return Any

    def __repr__(self) -> str:
        return self._name


In = _Marker("In")
Out = _Marker("Out")
Event = _Marker("Event")
Table = _Marker("Table")  # a table: a pandas DataFrame (Table[Row]: its columns are Row's fields)


class File:
    """A file a viewer gave (an upload, a picture, a recording): its name, size in bytes, type (as
    text/csv) and its bytes. An input widget's `file: Out[File]`; a reader's `file: In[File]`."""

    def __init__(self, name: str, data: bytes, type: str = "") -> None:
        self.name, self.bytes, self.type = str(name), bytes(data), str(type or "")
        self.size = len(self.bytes)

    def getvalue(self) -> bytes:  # read like Streamlit's own UploadedFile
        return self.bytes

    def __repr__(self) -> str:
        return f"File({self.name!r}, {self.size} bytes)"


def as_file(found: Any) -> Any:
    """An upload (Streamlit's UploadedFile), a picture or a recording as a File; a list: its first; None
    stays None."""
    if isinstance(found, list):
        found = found[0] if found else None
    if found is None or isinstance(found, File):
        return found
    if isinstance(found, dict) and "bytes" in found:
        return File(found.get("name") or "file", found["bytes"], found.get("type") or "")
    data = found.getvalue() if hasattr(found, "getvalue") else bytes(found)
    return File(getattr(found, "name", "") or "file", data, getattr(found, "type", "") or "")


# ===== who is viewing =====

UNKNOWN = "unknown"


_EMAIL_CLAIMS = (
    "email",
    "emails",
    "preferred_username",
    "upn",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
)
_ID_CLAIMS = ("oid", "http://schemas.microsoft.com/identity/claims/objectidentifier", "sub")
_ROLE_CLAIMS = ("roles", "role", "http://schemas.microsoft.com/ws/2008/06/identity/claims/role")


def principal_claims(encoded: str) -> dict[str, Any]:
    """App Service's X-MS-CLIENT-PRINCIPAL (base64 JSON: auth_typ, claims [{typ, val}], name_typ, role_typ)
    read for the viewer: {name, email, id, roles}; {} when it cannot be read."""
    import base64
    import json

    try:
        data = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4)))
        claims = [(str(c.get("typ") or ""), str(c.get("val") or "")) for c in data.get("claims") or []]
    except Exception:
        return {}
    role_typ = str(data.get("role_typ") or "")
    name_typ = str(data.get("name_typ") or "")

    def first(kinds: tuple[str, ...]) -> str:
        return next((v for t, v in claims for k in kinds if t == k and v), "")

    return {
        "name": first((name_typ, "name")) if name_typ else first(("name",)),
        "email": first(_EMAIL_CLAIMS),
        "id": first(_ID_CLAIMS),
        "roles": [v for t, v in claims if v and (t in _ROLE_CLAIMS or (role_typ and t == role_typ))],
    }


def viewer_info() -> dict[str, Any]:
    """Who is viewing, and how it is known, never invented: {name, email, id, roles, via}. A sign-in the host
    vouches for (Azure App Service's authentication headers, read only on App Service: its name, and from its
    X-MS-CLIENT-PRINCIPAL the email, account (object) id and roles; Streamlit's own st.user when the app signs
    people in: its name and email), else this computer's user name in Swiss Army Bench's Play and Launch
    (SAB_LOCAL_VIEWER: the name only), else "unknown" (a shared app through Dev Tunnels passes no viewer to
    the app). Whatever the sign-in does not give is empty."""
    blank: dict[str, Any] = {"email": "", "id": "", "roles": []}
    try:
        headers = st.context.headers
    except Exception:
        headers = {}

    def header(name: str) -> str:
        if not headers:
            return ""
        found = headers.get(name)
        if found is None:
            found = next((v for k, v in dict(headers).items() if str(k).lower() == name.lower()), None)
        return str(found or "")

    if os.environ.get("WEBSITE_SITE_NAME"):  # App Service sets these headers; outside it anyone could
        name = header("X-MS-CLIENT-PRINCIPAL-NAME")
        claims = principal_claims(header("X-MS-CLIENT-PRINCIPAL")) if header("X-MS-CLIENT-PRINCIPAL") else {}
        if name or claims:
            return {
                "name": name or claims.get("name") or claims.get("email") or UNKNOWN,
                "email": claims.get("email", ""),
                "id": header("X-MS-CLIENT-PRINCIPAL-ID") or claims.get("id", ""),
                "roles": list(claims.get("roles") or []),
                "via": "app service",
            }
    try:
        user = st.user
        if getattr(user, "is_logged_in", False):
            email = str(user.get("email") or "")
            found = email or user.get("name") or user.get("preferred_username")
            if found:
                return blank | {"name": str(found), "email": email, "via": "streamlit"}
    except Exception:
        pass
    local = os.environ.get("SAB_LOCAL_VIEWER", "")
    if local:
        return blank | {"name": local, "via": "this computer"}
    return blank | {"name": UNKNOWN, "via": UNKNOWN}


def viewer() -> dict[str, Any]:
    """Who is viewing: {name ("unknown" when it is not known), email, id, roles, via}, as viewer_info."""
    return viewer_info()


def _out_key(ref: str) -> str:
    return "sab:" + ref


def _coerce(value: Any, kind: str, name: str) -> Any:
    """A value as an In's type takes it (a table made from records, a number from text, a date from
    2026-01-31); one that cannot be is said in the widget's place."""
    import datetime as _dt

    if value is None:
        return None
    try:
        if kind == "Table":
            return as_table(value, name)
        if kind == "File":
            return as_file(value)
        if kind == "str" and isinstance(value, (int, float, _dt.date)):
            # A page value an Event set from a number (an id) read by a text In: its text (st.text_input
            # refused the number: "bad argument type"; test app two, 2026-11-22).
            return value.isoformat() if isinstance(value, _dt.date) else str(value)
        if kind in ("int", "float") and isinstance(value, str):
            return int(value) if kind == "int" else float(value)
        if kind == "bool" and isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        if kind == "date" and isinstance(value, str):
            return _dt.date.fromisoformat(value[:10])
        if kind == "datetime" and isinstance(value, str):
            return _dt.datetime.fromisoformat(value)
        if kind.startswith("list[Table") and isinstance(value, list):
            return [as_table(v, name) for v in value]
    except (ValueError, TypeError):
        raise Missing(f"{name} takes {kind}: {str(value)[:40]!r} is not.") from None
    return value


def _source(wire: Any, kind: str, default: Any, name: str) -> Any:
    """An In's value from its wire (the canvas's wiring): a table, an Out, a page value, an endpoint's answer,
    a variable, a value; none: its starting value."""
    if not isinstance(wire, dict) or not wire:
        return _coerce(default, kind, name)
    if "broken" in wire:
        st.warning(f"{name}: {wire['broken']} It takes its starting value until it is wired again.")
        return _coerce(default, kind, name)
    if "table" in wire:
        return table(str(wire["table"]))
    if "out" in wire:
        return _coerce(st.session_state.get(_out_key(str(wire["out"])), default), kind, name)
    if "page" in wire:
        return _coerce(st.session_state.get(str(wire["page"]), default), kind, name)
    if "endpoint" in wire:
        answer = action(str(wire["endpoint"]))
        if not answer["ok"]:
            raise Missing(f"{name}: {said(answer)}")
        return _coerce(_for_in(answer, kind), kind, name)
    if "variable" in wire:
        return _coerce(var(str(wire["variable"])), kind, name)
    if "value" in wire:
        return _coerce(wire["value"], kind, name)
    if "tables" in wire:
        return [_source(item, "Table", None, name) for item in wire["tables"]]
    return _coerce(default, kind, name)


class _Fire:
    """An Event as the widget calls it: `saved(payload)`. Its payload is kept (another widget's In can read
    it, as an Out), then its actions run in order: call an endpoint of the local sandbox API with the payload
    mapped to its body, set a page value, rerun. A failure is said in the widget's place. Returns {"ok",
    "answers", "errors"}."""

    def __init__(self, instance: str, name: str, actions: list[Any]) -> None:
        self.instance, self.name, self.actions = instance, name, actions

    def __call__(self, payload: Any = None) -> dict[str, Any]:
        st.session_state[_out_key(f"{self.instance}.{self.name}")] = payload
        answers: list[Any] = []
        errors: list[str] = []
        rerun = False
        for step in self.actions:
            do = step.get("do") if isinstance(step, dict) else None
            if do == "set":
                st.session_state[str(step.get("key"))] = pick(payload, str(step.get("value") or ""))
            elif do == "rerun":
                rerun = True
            elif do == "call":
                ref = str(step.get("endpoint") or "")
                found = _ACTION.match(ref)
                method, path = (found.group(2), found.group(3)) if found else ("", ref)
                given = step.get("body", "")
                if isinstance(given, dict):
                    body = {field: pick(payload, at) for field, at in given.items()}
                else:
                    body = pick(payload, given)
                params = step.get("params") or {}
                missing = None
                filled: dict[str, Any] = {}
                for part in re.findall(r"\{(\w+)\}", path):
                    value = (
                        pick(payload, params[part])
                        if part in params
                        else (body.get(part) if isinstance(body, dict) else None)
                    )
                    if value is None:
                        missing = part
                        break
                    filled[part] = value
                if missing:
                    errors.append(f"{self.name} needs {missing} for {path}: map it in the widget's Events.")
                    continue
                answer = action(ref, filled, body=None if method == "GET" else body)
                if answer["ok"]:
                    shaped = data(answer)
                    answers.append((answer.get("raw") or {}).get("body") if shaped is None else shaped)
                else:
                    errors.append(said(answer))
        for words in errors:
            st.error(words)
        if rerun and not errors:
            st.rerun()
        return {"ok": not errors, "answers": answers, "errors": errors}


def var(name: str) -> str:
    """A variable of this computer (its value from the environment, set by the app or the host)."""
    value = os.environ.get(name)
    if value is None:
        raise Missing(
            f"{name} is not set on this computer: set it on the Environment's Settings and secrets tab "
            "(or the host's settings)."
        )
    return value


def begin(page: str) -> None:
    """A page's run begins: the app's own Out app.viewer set (who is viewing), the Performance Analyzer's
    clock started when it is beside the app."""
    try:
        who = viewer_info()
        st.session_state[_out_key("app.viewer")] = who["name"]
        st.session_state[_out_key("app.viewer_email")] = who["email"]
        st.session_state[_out_key("app.viewer_id")] = who["id"]
        st.session_state[_out_key("app.viewer_roles")] = list(who["roles"])
    except Exception:
        pass
    if _perf is not None:
        try:
            _perf.start(str(_HERE), page)
        except Exception:
            pass


def finish() -> None:
    """A page's run ended (its record, when the analyzer is beside the app; else nothing)."""
    if _perf is not None:
        try:
            _perf.end()
        except Exception:
            pass


def style(css: str) -> None:
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def heading(text: str) -> None:
    """A container's title: one line of 28 px on the canvas's design (a longer one wraps, pushing the
    container's widgets down by its extra lines)."""
    st.markdown(
        f"<div class='sab-title' style='font-weight:600;line-height:20px;padding:4px 0;margin:0'>"
        f"{html.escape(text)}</div>",
        unsafe_allow_html=True,
    )


def space(pixels: int) -> None:
    st.markdown(f"<div style='height:{int(pixels)}px'></div>", unsafe_allow_html=True)


def empty() -> None:
    st.caption("This page is empty: draw a container on the canvas and insert a widget.")


def missing(name: str, instance: str) -> None:
    st.warning(
        f"The widget {name} is not in the library any more: Replace or Remove {instance} on the canvas."
    )


def _widgets() -> Any:
    """sab_widgets as its file is now: read again when the file changed since it was imported (a run that
    rewrote it can rerun the page before Streamlit's own watcher has looked)."""
    global sab_widgets
    path = Path(sab_widgets.__file__)
    stamp = path.stat().st_mtime_ns if path.is_file() else 0
    if getattr(sab_widgets, "_sab_stamp", None) != stamp:
        sab_widgets = importlib.reload(sab_widgets)
        vars(sab_widgets)["_sab_stamp"] = stamp
    return sab_widgets


_SEEN: dict[str, list[str]] = {}


def _seen(ref: str, value: Any) -> None:
    """An Out[Table]'s columns as it last ran, written beside the app for the Canvas's column pickers: only in
    Swiss Army Bench's Play and Launch (SAB_RECORD_COLUMNS; never a shared run), only when they change;
    never rows."""
    if os.environ.get("SAB_RECORD_COLUMNS") != "1" or value is None or not hasattr(value, "columns"):
        return
    columns = [str(c) for c in list(value.columns)[:500]]
    if _SEEN.get(ref) == columns:
        return
    _SEEN[ref] = columns
    try:
        import json
        import tempfile

        made = tempfile.NamedTemporaryFile("w", dir=_HERE, suffix=".tmp", delete=False, encoding="utf-8")
        with made:
            json.dump(_SEEN, made)
        os.replace(made.name, _HERE / ".sab_columns.json")
    except OSError:
        pass


def _code(name: str) -> Any:
    text = _widgets().CODE[name]
    key = (name, text)
    if key not in _COMPILED:
        where = f"<widget {name}>"
        linecache.cache[where] = (len(text), None, text.splitlines(keepends=True), where)
        _COMPILED[key] = compile(text, where, "exec")
    return _COMPILED[key]


def render(name: str, values: dict[str, Any], instance: str, wires: dict[str, Any] | None = None) -> None:
    """One widget in its place, with its properties' values and its contract wired: each In its source's
    value, each Out its last value (kept for the page once it has run), each Event a callable that carries out
    its actions. Whatever it does wrong stays in its place."""
    token = _INSTANCE.set(instance)
    if _perf is not None:
        _perf.before(instance)
    wires = wires or {}
    ports = getattr(_widgets(), "PORTS", {}).get(name, {})
    namespace: dict[str, Any] = {}
    try:
        namespace.update({"__name__": f"sab_widget_{name}", **values})
        for variable in _widgets().VARIABLES.get(name, []):
            namespace[variable] = var(str(values.get(variable) or ""))
        for port, (_kind, default) in ports.get("outs", {}).items():
            namespace[port] = st.session_state.get(_out_key(f"{instance}.{port}"), default)
        for port, _kind in ports.get("events", {}).items():
            namespace[port] = _Fire(instance, port, list((wires.get(port) or {}).get("actions") or []))
        for port, (kind, default) in ports.get("ins", {}).items():
            namespace[port] = _source(wires.get(port), kind, default, port)
        with st.spinner(f"Loading {name}…"):
            exec(_code(name), namespace)  # noqa: S102 (the user's own widget, from their library)
    except Missing as said:
        st.warning(str(said))
    except Exception as error:  # a widget's own failure: shown in its place, the page goes on
        if type(error).__name__ in ("RerunException", "StopException", "RerunData"):
            raise
        where = f"<widget {name}>"
        lines = [f.lineno for f in traceback.extract_tb(error.__traceback__) if f.filename == where]
        at = f" (line {lines[-1]})" if lines else ""
        st.error(f"{name} ({instance}) failed: {type(error).__name__}: {error}{at}")
        with st.expander("Details"):
            st.code(traceback.format_exc(), language="text")
    finally:
        for port, (kind, _default) in ports.get("outs", {}).items():  # kept for the app (every page reads it)
            if port in namespace:
                value = namespace[port]
                if kind == "File":
                    value = as_file(value)
                st.session_state[_out_key(f"{instance}.{port}")] = value
                if kind == "Table":
                    _seen(f"{instance}.{port}", value)
        _INSTANCE.reset(token)
        if _perf is not None:
            _perf.mark(instance)
