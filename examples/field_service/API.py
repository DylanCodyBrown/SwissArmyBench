# /// swissarmybench-api
# name = "field_service API"
# description = ""
# target = "fastapi"
# base_path = ""
# ///
"""The project's local sandbox API: endpoints over the project's sandbox, for its app and anything
else on this computer. Run it from the APIs page (Local sandbox APIs); Export makes it a FastAPI,
Azure Functions or AWS Lambda project that uses the real connections.

connection("<name>") is the adapter's calls on that connection: read(table, columns=, filters=,
sort=, limit=), query(sql, params) in its own SQL, write(table, rows, key, mode), tables(). Here
they read and write the sandbox's tables read from it (Add to sandbox first: a grid's Table row),
never the real connection; an export runs the same code against the real one.
"""

from datetime import date, datetime
from typing import TypedDict

from sab_api import ApiError, Download, connection, download, endpoint, records

# ===== an example (uncomment it once the sandbox has an orders table) =====
#
# class Order(TypedDict):
#     order_id: int
#     region: str
#     amount: float
#
#
# @endpoint("GET", "/orders/{region}")
# def orders_in(region: str, limit: int = 100) -> list[Order]:
#     """The orders of one region."""
#     db = connection("Sandbox")
#     return records(db.read("orders", filters=[["region", "=", region]], limit=limit))

__all__ = ["ApiError", "TypedDict", "connection", "endpoint", "records"]


# ===== work_orders: Table (connection("Sandbox") through the adapter) =====
# pattern: table of work_orders


class WorkOrdersRow(TypedDict, total=False):
    work_order_id: int
    customer_id: int
    technician_id: int
    region: str
    status: str
    priority: str
    opened_on: date
    closed_on: date
    hours: float
    amount: float
    summary: str

@endpoint("GET", "/work_orders")
def list_work_orders(limit: int = 50, offset: int = 0) -> list[WorkOrdersRow]:
    """work_orders: a page of its rows."""
    return records(connection("Sandbox").read("work_orders", sort=[["work_order_id", "asc"]], limit=limit, offset=offset))


@endpoint("GET", "/work_orders/{key}")
def get_work_orders(key: int) -> WorkOrdersRow:
    """work_orders: one row by work_order_id."""
    found = records(connection("Sandbox").read("work_orders", filters=[["work_order_id", "=", key]], limit=1))
    if not found:
        raise ApiError(404, f"No work_orders row has work_order_id {key}.")
    return found[0]


@endpoint("POST", "/work_orders", status=201)
def create_work_orders(row: WorkOrdersRow) -> WorkOrdersRow:
    """work_orders: a new row from the body."""
    connection("Sandbox").write("work_orders", [{c: v for c, v in row.items() if c in ["work_order_id", "customer_id", "technician_id", "region", "status", "priority", "opened_on", "closed_on", "hours", "amount", "summary"]}])
    return row


@endpoint("PUT", "/work_orders/{key}")
def update_work_orders(key: int, row: WorkOrdersRow) -> WorkOrdersRow:
    """work_orders: the body's columns set on one row."""
    changes = {c: v for c, v in row.items() if c in ["work_order_id", "customer_id", "technician_id", "region", "status", "priority", "opened_on", "closed_on", "hours", "amount", "summary"] and c != "work_order_id"}
    if not changes:
        raise ApiError(422, "Send at least one column to change.")
    done = connection("Sandbox").write("work_orders", [changes | {"work_order_id": key}], key=["work_order_id"], mode="update")
    if not done.updated:
        raise ApiError(404, f"No work_orders row has work_order_id {key}.")
    return get_work_orders(key)


@endpoint("DELETE", "/work_orders/{key}")
def delete_work_orders(key: int) -> None:
    """work_orders: one row gone."""
    done = connection("Sandbox").write("work_orders", [{"work_order_id": key}], key=["work_order_id"], mode="delete")
    if not done.deleted:
        raise ApiError(404, f"No work_orders row has work_order_id {key}.")


# ===== technicians: Choices (connection("Sandbox") through the adapter) =====
# pattern: choices of technicians


class TechniciansChoice(TypedDict, total=False):
    technician_id: int
    name: str


@endpoint("GET", "/technicians/choices")
def choices_technicians(search: str = "", limit: int = 200) -> list[TechniciansChoice]:
    """technicians: its choices for a dropdown (technician_id and name).

    Sorted by name, `limit` at most; ?search= narrows by name, in any case."""
    filters = [["name", "contains", search]] if search else []
    plan = {"columns": ["technician_id", "name"], "filters": filters, "sort": [["name", "asc"]], "limit": limit}
    return records(connection("Sandbox").read("technicians", plan))


# ===== work_orders: Search (connection("Sandbox") through the adapter) =====
# pattern: search of work_orders


class WorkOrdersFound(TypedDict, total=False):
    work_order_id: int
    customer_id: int
    technician_id: int
    region: str
    status: str
    priority: str
    opened_on: date
    closed_on: date
    hours: float
    amount: float
    summary: str


@endpoint("GET", "/work_orders/search")
def search_work_orders(
    q: str = "",
    status: str | None = None,
    priority: str | None = None,
    region: str | None = None,
    from_opened_on: date | None = None,
    to_opened_on: date | None = None,
    sort: str = "work_order_id",
    descending: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[WorkOrdersFound]:
    """work_orders: the rows that match, a page at a time.

    ?q= looks in summary, in any case; status, priority, region and opened_on narrow it. The filters, the sort and the page go to the source."""
    columns = [
        "work_order_id",
        "customer_id",
        "technician_id",
        "region",
        "status",
        "priority",
        "opened_on",
        "closed_on",
        "hours",
        "amount",
        "summary",
    ]
    filters: list[list] = []
    if q:
        filters.append(["summary", "contains", q])
    if status is not None:
        filters.append(["status", "=", status])
    if priority is not None:
        filters.append(["priority", "=", priority])
    if region is not None:
        filters.append(["region", "=", region])
    if from_opened_on is not None:
        filters.append(["opened_on", ">=", from_opened_on])
    if to_opened_on is not None:
        filters.append(["opened_on", "<=", to_opened_on])
    if sort not in columns:
        raise ApiError(422, "sort is one of the columns it answers.")
    way = "desc" if descending else "asc"
    plan = {"columns": columns, "filters": filters, "sort": [[sort, way]], "limit": limit, "offset": offset}
    return records(connection("Sandbox").read("work_orders", plan))


# ===== work_orders: Summary (connection("Sandbox") through the adapter) =====
# pattern: summary of work_orders


class WorkOrdersStatusSummary(TypedDict, total=False):
    status: str
    sum_amount: float
    rows: int


@endpoint("GET", "/work_orders/summary/status")
def summary_work_orders_by_status(
    status: str | None = None,
    limit: int = 1000,
) -> list[WorkOrdersStatusSummary]:
    """work_orders: sum of amount and the row count by status.

    The group and the totals are the read's plan: the source does them where it can."""
    filters: list[list] = []
    if status is not None:
        filters.append(["status", "=", status])
    plan = {
        "group": ["status"],
        "totals": [{"fn": "sum", "name": "sum_amount", "column": "amount"}, {"fn": "count", "name": "rows"}],
        "filters": filters,
        "sort": [["status", "asc"]],
        "limit": limit,
    }
    return records(connection("Sandbox").read("work_orders", plan))


# ===== work_orders: Summary (connection("Sandbox") through the adapter) =====
# pattern: summary of work_orders


class WorkOrdersMonthSummary(TypedDict, total=False):
    period: date
    sum_hours: float


@endpoint("GET", "/work_orders/summary/month")
def summary_work_orders_by_month(
    since: date | None = None,
    limit: int = 1000,
) -> list[WorkOrdersMonthSummary]:
    """work_orders: sum of hours by month of opened_on.

    The period, the group and the totals are the read's plan: the source does them where it can."""
    filters: list[list] = []
    if since is not None:
        filters.append(["opened_on", ">=", since])
    plan = {
        "periods": [{"column": "opened_on", "unit": "month", "name": "period"}],
        "group": [],
        "totals": [{"fn": "sum", "name": "sum_hours", "column": "hours"}],
        "filters": filters,
        "sort": [["period", "asc"]],
        "limit": limit,
    }
    return records(connection("Sandbox").read("work_orders", plan))


# ===== parts_used: Bulk upload (connection("Sandbox") through the adapter) =====
# pattern: bulk of parts_used


PARTS_USED_COLUMNS = {"line_id": "int", "work_order_id": "int", "part_sku": "str", "quantity": "int", "unit_cost": "float"}  # each column and what it holds
PARTS_USED_REQUIRED = ["line_id"]


class PartsUsedBulkAnswer(TypedDict):
    rows: int
    inserted: int
    updated: int
    written: bool
    problems: list[dict]


def _problem_parts_used(value: object, kind: str) -> str:
    """Why a value does not fit its column ("" when it does); a date arrives as 2026-01-15."""
    if kind == "int" and (isinstance(value, bool) or not isinstance(value, int)):
        return "is not a whole number"
    if kind == "float" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return "is not a number"
    if kind == "bool" and not isinstance(value, bool):
        return "is not true or false"
    if kind == "str" and not isinstance(value, str):
        return "is not text"
    if kind in ("date", "datetime"):
        try:
            (date if kind == "date" else datetime).fromisoformat(str(value))
        except ValueError:
            return "is not a date (2026-01-15)" if kind == "date" else "is not a date and time"
    return ""


@endpoint("POST", "/parts_used/bulk")
def bulk_parts_used(rows: list[dict], dry_run: bool = False) -> PartsUsedBulkAnswer:
    """parts_used: many rows at once, checked first, then all written or none.

    Every row is checked (its columns, the required ones, each value's type, a line_id sent
    twice); ?dry_run=true answers the problems and what would be written, and writes nothing. With
    no problem, one write: all of it or none. A column a row leaves out is written blank."""
    problems: list[dict] = []
    seen: dict[object, int] = {}
    clean: list[dict] = []
    for at, row in enumerate(rows, 1):
        for name in row:
            if name not in PARTS_USED_COLUMNS:
                problems.append({"row": at, "column": name, "problem": "is not a column of parts_used"})
        for name in PARTS_USED_REQUIRED:
            if row.get(name) in (None, ""):
                problems.append({"row": at, "column": name, "problem": "is required"})
        kept: dict[str, object] = {}
        for name, kind in PARTS_USED_COLUMNS.items():
            value = row.get(name)
            said = "" if value is None else _problem_parts_used(value, kind)
            if said:
                problems.append({"row": at, "column": name, "problem": said})
            elif value is not None and kind in ("date", "datetime"):
                value = (date if kind == "date" else datetime).fromisoformat(str(value))
            kept[name] = value
        key = row.get("line_id")
        if key is not None and key in seen:
            problems.append({"row": at, "column": "line_id", "problem": f"repeats row {seen[key]}'s"})
        seen.setdefault(key, at)
        clean.append(kept)
    keys = [k for k in seen if k is not None]
    inserted = updated = 0
    if keys:  # the write's own dry run, by the keys alone: those there are updated, the rest added
        counted = connection("Sandbox").planned("parts_used", [{"line_id": k} for k in keys], key=["line_id"], mode="merge")
        inserted, updated = counted.inserted, counted.updated
    answer: PartsUsedBulkAnswer = {
        "rows": len(rows),
        "inserted": inserted,
        "updated": updated,
        "written": False,
        "problems": problems[:200],
    }
    if dry_run or not rows:
        return answer
    if problems:
        first = problems[0]
        raise ApiError(
            422,
            f"Nothing was written: {len(problems)} problems, the first: row {first['row']} {first['column']} "
            f"{first['problem']}. Send dry_run=true for the list.",
        )
    done = connection("Sandbox").write("parts_used", clean, key=["line_id"], mode="merge")  # one write: all of it or none
    return answer | {"inserted": done.inserted, "updated": done.updated, "written": True}


# ===== work_orders: Action (connection("Sandbox") through the adapter) =====
# pattern: action of work_orders


class CompleteWorkOrders(TypedDict):
    keys: list[int]


class CompleteWorkOrdersDone(TypedDict):
    changed: int
    keys: list[int]


@endpoint("POST", "/work_orders/complete")
def complete_work_orders(sent: CompleteWorkOrders) -> CompleteWorkOrdersDone:
    """work_orders: complete the rows whose work_order_id is sent: status set to "done".

    Every key is checked first; then one write, all of the rows or none."""
    keys = list(dict.fromkeys(sent["keys"]))
    if not keys:
        raise ApiError(422, "Send at least one key.")
    if len(keys) > 1000:
        raise ApiError(422, "Send 1,000 keys at most in one call.")
    found = records(connection("Sandbox").read("work_orders", columns=["work_order_id"], filters=[["work_order_id", "in", keys]]))
    have = {row["work_order_id"] for row in found}
    missing = [k for k in keys if k not in have]
    if missing:
        gone = f"{len(missing)} of {len(keys)} are not there"
        raise ApiError(404, f"No work_orders row has work_order_id {missing[0]} ({gone}).")
    changes = [{"work_order_id": k, "status": "done"} for k in keys]
    done = connection("Sandbox").write("work_orders", changes, key=["work_order_id"], mode="update")  # one write: all or none
    return {"changed": done.updated, "keys": keys}


# ===== price_lists: Versions (connection("Sandbox") through the adapter) =====
# pattern: versions of price_lists


class PriceListsVersion(TypedDict, total=False):
    price_id: str
    part_sku: str
    part_name: str
    version: int
    is_current: bool
    price: float


@endpoint("GET", "/price_lists/{key}/versions")
def versions_price_lists(key: str, limit: int = 50, offset: int = 0) -> list[PriceListsVersion]:
    """price_lists: every version of one part_sku, the newest first."""
    return records(
        connection("Sandbox").read(
            "price_lists", filters=[["part_sku", "=", key]], sort=[["version", "desc"]], limit=limit, offset=offset
        )
    )


@endpoint("GET", "/price_lists/{key}/current")
def current_price_lists(key: str) -> PriceListsVersion:
    """price_lists: the current version of one part_sku (its highest version)."""
    latest = {"filters": [["part_sku", "=", key]], "sort": [["version", "desc"]], "limit": 1}
    found = records(connection("Sandbox").read("price_lists", latest))
    if not found:
        raise ApiError(404, f"No price_lists row has part_sku {key}.")
    return found[0]


@endpoint("POST", "/price_lists/{key}/versions", status=201)
def new_version_price_lists(key: str, row: PriceListsVersion) -> PriceListsVersion:
    """price_lists: a new version of one part_sku from the body, numbered after its latest.

    Earlier versions are never changed."""
    newest = {"filters": [["part_sku", "=", key]], "sort": [["version", "desc"]], "limit": 1}
    latest = records(connection("Sandbox").read("price_lists", newest | {"columns": ["version"]}))
    made = {name: value for name, value in row.items() if name in ["price_id", "part_sku", "part_name", "version", "is_current", "price"]}
    made |= {"part_sku": key, "version": (latest[0]["version"] if latest else 0) + 1}
    connection("Sandbox").write("price_lists", [made])
    return made


# ===== invoices and work_orders: Reconcile (connection("Sandbox") through the adapter) =====
# pattern: reconcile of invoices and work_orders


RECONCILE_INVOICES_WORK_ORDERS_SHOWS = {
    "differences": ["differing", "missing in invoices", "missing in work_orders"],
    "all": ["matched", "differing", "missing in invoices", "missing in work_orders"],
    "matched": ["matched"],
    "differing": ["differing"],
    "missing_in_invoices": ["missing in invoices"],
    "missing_in_work_orders": ["missing in work_orders"],
}
# Each compared row: the key, its result, both sides' values, in Sandbox's own SQL.
RECONCILE_INVOICES_WORK_ORDERS_COMPARED = """
SELECT
  COALESCE("l"."work_order_id", "r"."work_order_id") AS "work_order_id",
  CASE
    WHEN "r"."work_order_id" IS NULL
    THEN 'missing in work_orders'
    WHEN "l"."work_order_id" IS NULL
    THEN 'missing in invoices'
    WHEN "l"."amount" <> "r"."amount"
    OR (
      "l"."amount" IS NULL AND NOT "r"."amount" IS NULL
    )
    OR (
      NOT "l"."amount" IS NULL AND "r"."amount" IS NULL
    )
    THEN 'differing'
    ELSE 'matched'
  END AS "result",
  "l"."amount" AS "amount_invoices",
  "r"."amount" AS "amount_work_orders"
FROM "invoices" AS l
FULL OUTER JOIN "work_orders" AS r
  ON "l"."work_order_id" = "r"."work_order_id"
"""


class ReconcileInvoicesWorkOrders(TypedDict):
    matched: int
    differing: int
    missing_in_invoices: int
    missing_in_work_orders: int


class ReconcileInvoicesWorkOrdersRow(TypedDict, total=False):
    work_order_id: int
    result: str
    amount_invoices: float
    amount_work_orders: float


@endpoint("GET", "/reconcile/invoices-work_orders")
def reconcile_invoices_work_orders() -> ReconcileInvoicesWorkOrders:
    """invoices and work_orders by work_order_id: how many rows match, differ or are missing on each side.

    Compared: amount. One statement in Sandbox's own SQL: the source joins the two tables."""
    found = connection("Sandbox").query(
        f"""
            WITH compared AS (
              {RECONCILE_INVOICES_WORK_ORDERS_COMPARED}
            )
            SELECT
              "result",
              COUNT(*) AS "rows"
            FROM compared
            GROUP BY
              "result"
        """
    )
    counts = {"matched": 0, "differing": 0, "missing in invoices": 0, "missing in work_orders": 0}
    for row in records(found):
        counts[row["result"]] = row["rows"]
    return {
        "matched": counts["matched"],
        "differing": counts["differing"],
        "missing_in_invoices": counts["missing in invoices"],
        "missing_in_work_orders": counts["missing in work_orders"],
    }


@endpoint("GET", "/reconcile/invoices-work_orders/rows")
def reconcile_invoices_work_orders_rows(show: str = "differences", limit: int = 50, offset: int = 0) -> list[ReconcileInvoicesWorkOrdersRow]:
    """invoices and work_orders by work_order_id: the compared rows, a page at a time.

    Each row has its result and both sides' values. ?show= is one of differences, all, matched, differing,
    missing_in_invoices, missing_in_work_orders. One statement in Sandbox's own SQL: the source joins the two tables."""
    if show not in RECONCILE_INVOICES_WORK_ORDERS_SHOWS:
        raise ApiError(422, f"show is one of: {', '.join(RECONCILE_INVOICES_WORK_ORDERS_SHOWS)}.")
    shown = ", ".join(f"'{word}'" for word in RECONCILE_INVOICES_WORK_ORDERS_SHOWS[show])
    found = connection("Sandbox").query(
        f"""
            WITH compared AS (
              {RECONCILE_INVOICES_WORK_ORDERS_COMPARED}
            )
            SELECT
              *
            FROM compared
            WHERE
              "result" IN ({shown})
            ORDER BY
              "work_order_id"
            LIMIT {int(limit)}
            OFFSET {int(offset)}
        """
    )
    return records(found)


# ===== work_orders: Export (connection("Sandbox") through the adapter) =====
# pattern: export of work_orders


@endpoint("GET", "/work_orders/export.csv")
def export_work_orders(limit: int = 100000) -> Download:
    """work_orders as a CSV file to save.

    It carries every column, sorted by work_order_id: read from the source a batch at a time, `limit` rows at
    most."""
    columns = [
        "work_order_id",
        "customer_id",
        "technician_id",
        "region",
        "status",
        "priority",
        "opened_on",
        "closed_on",
        "hours",
        "amount",
        "summary",
    ]
    plan = {"columns": columns, "sort": [["work_order_id", "asc"]], "limit": limit}
    return download(connection("Sandbox").read("work_orders", plan), "work_orders.csv")


# ===== the app's own endpoints (written by hand, after the wizard's) =====


class VisitDone(TypedDict):
    work_order_id: int
    technician: str
    note: str


@endpoint("POST", "/visits/done")
def visit_done(visit: VisitDone) -> WorkOrdersRow:
    """A visit marked done: its work order's status set to done, its note added to the summary."""
    db = connection("Sandbox")
    key = visit["work_order_id"]
    found = records(db.read("work_orders", filters=[["work_order_id", "=", key]], limit=1))
    if not found:
        raise ApiError(404, f"No work order {key}.")
    change = {"work_order_id": key, "status": "done"}
    if visit["note"]:
        change["summary"] = f"{found[0]['summary']} ({visit['note']})"
    db.write("work_orders", [change], key=["work_order_id"], mode="update")
    return get_work_orders(key)


class LowStock(TypedDict):
    part_sku: str
    part_name: str
    on_hand: int
    reorder_point: int


@endpoint("GET", "/stock/low")
def low_stock() -> list[LowStock]:
    """The parts at or under their reorder point, in Depot's own SQL."""
    return records(
        connection("Depot").query(
            "SELECT part_sku, part_name, on_hand, reorder_point FROM stock "
            "WHERE on_hand <= reorder_point ORDER BY part_sku"
        )
    )
