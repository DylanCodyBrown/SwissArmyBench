"""The forms and reconciliation app's local sandbox API under load (the owner, 2026-11-21: "Build a large
dataset. Build three app pages and stress test the API against the data").

Skipped unless SWISSARMYBENCH_STRESS=1. A real server in a process of its own, a project made through
its routes, examples/forms_recon/API.py saved into it as the Scripts page saves it, and Larkfield Goods
(the made-up business, tools/testbed/large_company.py) at the medium and large scales: its order lines with
their orders' month, as the copy of a Trino table would arrive, and a ledger of entries made from them with
planted breaks.

Measured with the API running locally (its own port and key, as the app's widgets call it):
- each endpoint's p50, p95 and p99 at 1, 8 and 32 callers at once;
- 100k entries loaded in batches of typed rows;
- the column store's build (the PIVOT over every entry);
- 1M entries against 1M source rows (medium), every status counted against the answer worked out here
  with plain DuckDB from the same files; one month of the large scale's 10M lines the same way;
- an Excel workbook of 100k rows read by the excel widgets' own parsing (excel_upload's _read,
  excel_map_columns' matching), then sent in parts;
- Reset: its time, and every table's rows exactly the baseline's again.

SWISSARMYBENCH_STRESS_SCALES picks the scales (default "medium,large"); SWISSARMYBENCH_STRESS_OUT names a
JSON file for the numbers. Made-up data only.
"""

from __future__ import annotations

import ast
import http.client
import io
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import duckdb
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SWISSARMYBENCH_STRESS") != "1", reason="the stress test: SWISSARMYBENCH_STRESS=1"
)

REPOSITORY = Path(__file__).resolve().parents[2]
API_FILE = REPOSITORY / "examples" / "forms_recon" / "API.py"
WIDGETS = REPOSITORY / "extensions" / "streamlit" / "src" / "swissarmybench_streamlit" / "widgets"
SCALES = [s for s in os.environ.get("SWISSARMYBENCH_STRESS_SCALES", "medium,large").split(",") if s]
RESULTS: dict[str, Any] = {"latency": [], "timings": {}}
CALLERS = (1, 8, 32)

FIELDS: list[dict[str, Any]] = [
    {"name": "line_id", "label": "Line", "type": "number", "required": True},
    {"name": "period", "label": "Month", "type": "text", "required": True},
    {"name": "store_id", "label": "Store", "type": "number"},
    {"name": "amount", "label": "Amount", "type": "money", "required": True},
]


# ===== the server, as the user =====


class App:
    def __init__(self, port: int, token: str) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.token = token

    def call(self, method: str, path: str, body: Any = None, timeout: float = 1800) -> Any:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base + path,
            data,
            {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            raw = answer.read()
        return json.loads(raw) if raw else None


class Api:
    """The project's local sandbox API on its own port, called as the app's widgets call it: one kept-open
    connection per thread."""

    def __init__(self, url: str, key: str) -> None:
        self.host, self.port = url.split("//")[1].split(":")
        self.key = key
        self._local = threading.local()

    def _connection(self) -> http.client.HTTPConnection:
        found = getattr(self._local, "connection", None)
        if found is None:
            found = http.client.HTTPConnection(self.host, int(self.port), timeout=1800)
            self._local.connection = found
        return found

    def send(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        payload = None if body is None else json.dumps(body, default=str).encode()
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        for attempt in range(2):
            connection = self._connection()
            try:
                connection.request(method, path, payload, headers)
                answer = connection.getresponse()
                raw = answer.read()
                return answer.status, (json.loads(raw) if raw else None)
            except (http.client.HTTPException, ConnectionError):
                connection.close()
                self._local.connection = None
                if attempt:
                    raise
        raise AssertionError("unreachable")

    def ok(self, method: str, path: str, body: Any = None) -> Any:
        status, answer = self.send(method, path, body)
        assert status < 300, f"{method} {path}: {status} {answer}"
        return answer


@pytest.fixture(scope="module")
def bench(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("stress")
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
    }
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    for _ in range(200):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    else:
        process.kill()
        raise AssertionError("the server did not start")
    app = App(int(info["port"]), str(info["token"]))
    folder = tmp / "forms_recon"
    app.call("POST", "/project/new", {"path": str(folder), "type": "streamlit"})
    opened = app.call("POST", "/workbench/open", {"path": str(folder / "API.py")})
    app.call(
        "POST",
        "/workbench/save",
        {
            "path": str(folder / "API.py"),
            "text": API_FILE.read_text(encoding="utf-8"),
            "modified": opened["modified"],
        },
    )
    for spec in TABLES:
        app.call("POST", "/sandbox/tables", spec)
    try:
        yield {"app": app, "tmp": tmp, "folder": folder}
    finally:
        out = os.environ.get("SWISSARMYBENCH_STRESS_OUT")
        if out:
            Path(out).write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")
        try:
            app.call("POST", "/local-api/stop", {})
        except Exception:  # noqa: S110 (already stopped)
            pass
        process.terminate()
        process.wait(timeout=30)


def _columns(name: str, *columns: tuple[str, str], key: str | None = None) -> dict[str, Any]:
    return {
        "from": "columns",
        "name": name,
        "columns": [{"name": c, "type": t} | ({"key": True} if c == key else {}) for c, t in columns],
    }


# The app's own tables, empty, by their columns (the sandbox's Add table…).
TABLES = [
    _columns(
        "forms",
        ("form_id", "text"),
        ("title", "text"),
        ("description", "text"),
        ("version", "integer"),
        ("updated_at", "timestamp"),
        key="form_id",
    ),
    _columns(
        "form_fields",
        ("field_id", "text"),
        ("form_id", "text"),
        ("version", "integer"),
        ("position", "integer"),
        ("field", "text"),
        ("label", "text"),
        ("type", "text"),
        ("required", "yes/no"),
        ("choices", "text"),
        ("format", "text"),
        key="field_id",
    ),
    _columns(
        "batches",
        ("batch_id", "integer"),
        ("form_id", "text"),
        ("form_version", "integer"),
        ("period", "text"),
        ("source", "text"),
        ("loaded_by", "text"),
        ("loaded_at", "timestamp"),
        ("rows", "integer"),
        key="batch_id",
    ),
    _columns(
        "entries",
        ("form_id", "text"),
        ("batch_id", "integer"),
        ("row_no", "integer"),
        ("field", "text"),
        ("value_text", "text"),
        ("value_number", "number"),
        ("value_date", "date"),
        ("value_bool", "yes/no"),
    ),
    _columns(
        "recon_defs",
        ("recon_id", "text"),
        ("title", "text"),
        ("form_id", "text"),
        ("source_table", "text"),
        ("source_period", "text"),
        ("keys", "text"),
        ("compares", "text"),
        ("totals", "text"),
        ("updated_at", "timestamp"),
        key="recon_id",
    ),
    _columns(
        "recon_runs",
        ("run_id", "integer"),
        ("recon_id", "text"),
        ("period", "text"),
        ("ran_at", "timestamp"),
        ("matched", "integer"),
        ("differences", "integer"),
        ("only_entries", "integer"),
        ("only_source", "integer"),
        ("duplicates", "integer"),
        ("totals", "text"),
        ("signed_off_by", "text"),
        ("signed_off_at", "timestamp"),
        key="run_id",
    ),
    _columns(
        "recon_results",
        ("run_id", "integer"),
        ("status", "text"),
        ("record_key", "text"),
        ("entry_values", "text"),
        ("source_values", "text"),
        ("difference", "number"),
        ("fields_off", "text"),
    ),
]


def run_api(bench: dict[str, Any]) -> Api:
    app: App = bench["app"]
    state = app.call("POST", "/local-api/run", {})
    assert state["running"], state
    found = app.call("GET", "/local-api/address")
    return Api(found["url"], found["key"])


def timed(name: str, fn: Callable[[], Any]) -> Any:
    started = time.perf_counter()
    out = fn()
    RESULTS["timings"][name] = round(time.perf_counter() - started, 3)
    print(f"{name}: {RESULTS['timings'][name]} s", flush=True)
    return out


# ===== the data: Larkfield Goods, the Trino copy and the ledger with its planted breaks =====


def larkfield(tmp: Path, scale: str) -> Path:
    sys.path.insert(0, str(REPOSITORY))
    from tools.testbed import large_company

    out = tmp / f"larkfield-{scale}"
    if not (out / "order_lines.parquet").exists():
        large_company.build(out, scale=scale)
    return out


def source_files(tmp: Path, scale: str) -> tuple[Path, Path]:
    """trino_sales_lines (the order lines with their order's month, as a Trino table's copy arrives) and
    ledger (the entries people keep, made from it with planted breaks), as Parquet files."""
    folder = larkfield(tmp, scale)
    trino, ledger = tmp / f"trino_sales_lines_{scale}.parquet", tmp / f"ledger_{scale}.parquet"
    if not trino.exists():
        con = duckdb.connect()
        con.execute(
            "COPY (SELECT l.order_line_id, l.order_id, strftime(o.order_date, '%Y-%m') AS period, "
            f"o.store_id, l.quantity, round(l.line_total, 2) AS amount FROM '{folder}/order_lines.parquet' l "
            f"JOIN '{folder}/orders.parquet' o USING (order_id)) TO '{trino}' (FORMAT parquet)"
        )
        # The breaks: one in 997 amounts off by 1.00, one in 991 off by 0.004 (inside the tolerance), one in
        # 1009 left out, one in 1013 kept twice, and 500 lines only the ledger has.
        con.execute(
            f"COPY (SELECT order_line_id AS line_id, period, store_id, CASE WHEN order_line_id % 997 = 0 "
            f"THEN amount + 1 WHEN order_line_id % 991 = 0 THEN amount + 0.004 ELSE amount END AS amount "
            f"FROM '{trino}' WHERE order_line_id % 1009 <> 0 "
            f"UNION ALL SELECT order_line_id, period, store_id, amount FROM '{trino}' "
            f"WHERE order_line_id % 1013 = 0 AND order_line_id % 1009 <> 0 "
            f"UNION ALL SELECT 900000000 + range, '2026-10', 1, 10.0 FROM range(500)) "
            f"TO '{ledger}' (FORMAT parquet)"
        )
    return trino, ledger


def expected(trino: Path, ledger: Path, period: str | None) -> dict[str, int]:
    """The answer, worked out here with plain DuckDB from the same files: by key, a duplicate when either
    side has it more than once, else only on one side, else off by more than 0.01, else matched."""
    where = f"WHERE period = '{period}'" if period else ""
    found = duckdb.execute(
        f"WITH e AS (SELECT CAST(line_id AS VARCHAR) k, count(*) n, first(amount) a FROM '{ledger}' {where} "
        f"GROUP BY 1), s AS (SELECT CAST(order_line_id AS VARCHAR) k, count(*) n, first(amount) a "
        f"FROM '{trino}' {where} GROUP BY 1) SELECT CASE WHEN e.n > 1 OR s.n > 1 THEN 'duplicate' "
        f"WHEN s.k IS NULL THEN 'only_entries' WHEN e.k IS NULL THEN 'only_source' "
        f"WHEN abs(e.a - s.a) > 0.01 THEN 'difference' ELSE 'matched' END st, count(*) "
        f"FROM e FULL OUTER JOIN s ON e.k = s.k GROUP BY 1"
    ).fetchall()
    return {"matched": 0, "difference": 0, "only_entries": 0, "only_source": 0, "duplicate": 0} | {
        str(s): int(n) for s, n in found
    }


# ===== latency =====


def percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)

    def at(p: float) -> float:
        return round(ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))], 1)

    return {"p50": at(0.50), "p95": at(0.95), "p99": at(0.99), "mean": round(statistics.fmean(ordered), 1)}


def measure(
    api: Api,
    label: str,
    method: str,
    path: Callable[[int], str],
    body: Callable[[int], Any] | None,
    requests: int = 0,
) -> None:
    for callers in CALLERS:
        times: list[float] = []
        lock = threading.Lock()
        total = requests or {1: 100, 8: 160, 32: 320}[callers]

        def one(i: int, times: list[float] = times, lock: threading.Lock = lock) -> None:
            started = time.perf_counter()
            status, answer = api.send(method, path(i), body(i) if body else None)
            spent = (time.perf_counter() - started) * 1000
            assert status < 300, f"{label}: {status} {answer}"
            with lock:
                times.append(spent)

        with ThreadPoolExecutor(callers) as pool:
            list(pool.map(one, range(total)))
        row = {"endpoint": label, "callers": callers, "requests": total} | percentiles(times)
        RESULTS["latency"].append(row)
        print(row, flush=True)


# ===== the tests =====


def test_a_endpoint_latency_at_1_8_and_32_callers(bench: dict[str, Any]) -> None:
    app: App = bench["app"]
    trino, ledger = source_files(bench["tmp"], SCALES[0])
    for path, name in ((trino, "trino_sales_lines"), (ledger, "ledger")):
        app.call(
            "POST", "/sandbox/tables", {"from": "file", "path": str(path), "name": name, "replace": True}
        )
    api = run_api(bench)
    api.ok("PUT", "/forms/sales_ledger", {"title": "Sales ledger", "fields": FIELDS})
    batch = api.ok(
        "POST",
        "/forms/sales_ledger/batches/from-table",
        {
            "period": "2026-10",
            "table": "ledger",
            "period_column": "period",
            "mapping": {"line_id": "line_id", "period": "period", "store_id": "store_id", "amount": "amount"},
        },
    )
    api.ok("PUT", "/recons/sales_month", RECON)
    run = api.ok("POST", "/recons/sales_month/runs", {"period": "2026-10"})
    measure(api, "GET /forms", "GET", lambda i: "/forms", None)
    measure(api, "GET /forms/{id}", "GET", lambda i: "/forms/sales_ledger", None)
    measure(
        api,
        "GET /forms/{id}/entries (page of 100)",
        "GET",
        lambda i: f"/forms/sales_ledger/entries?period=2026-10&limit=100&offset={(i * 100) % 20000}",
        None,
    )
    measure(api, "GET /forms/{id}/batches", "GET", lambda i: "/forms/sales_ledger/batches", None)
    measure(api, "GET /recons/{id}", "GET", lambda i: "/recons/sales_month", None)
    measure(
        api,
        "GET /runs/{id}/results (page of 100)",
        "GET",
        lambda i: f"/runs/{run['run_id']}/results?limit=100&offset={(i * 100) % 1000}",
        None,
    )
    measure(
        api,
        "POST /forms/{id}/batches (10 typed rows)",
        "POST",
        lambda i: "/forms/sales_ledger/batches",
        lambda i: {
            "period": "2026-09",
            "source": "typed",
            "loaded_by": "Ada Ashdown",
            "rows": [
                {"line_id": 800000000 + i * 10 + r, "period": "2026-09", "store_id": 3, "amount": 12.5 + r}
                for r in range(10)
            ],
        },
        requests=64,
    )
    assert batch["rows"] > 0


RECON = {
    "title": "Sales ledger against Trino's order lines",
    "form_id": "sales_ledger",
    "source_table": "trino_sales_lines",
    "source_period": "period",
    "keys": [{"field": "line_id", "column": "order_line_id"}],
    "compares": [{"field": "amount", "column": "amount", "tolerance": 0.01}],
    "totals": [{"field": "amount", "column": "amount"}],
}


def test_b_100k_entries_loaded_in_batches_and_the_column_store_built(bench: dict[str, Any]) -> None:
    api = run_api(bench)
    api.ok("PUT", "/forms/typed_100k", {"title": "Typed entries", "fields": FIELDS})
    rows = [
        {"line_id": n, "period": "2026-08", "store_id": n % 40, "amount": round((n % 997) * 1.25, 2)}
        for n in range(100_000)
    ]

    def load() -> int:
        made = api.ok(
            "POST",
            "/forms/typed_100k/batches",
            {"period": "2026-08", "source": "typed", "loaded_by": "Bram Brookfield", "rows": rows[:5000]},
        )
        for at in range(5000, len(rows), 5000):
            made = api.ok("POST", f"/batches/{made['batch_id']}/rows", {"rows": rows[at : at + 5000]})
        return int(made["rows"])

    assert timed("load 100k typed entries (20 batches of 5,000)", load) == 100_000
    count = timed(
        "column store: count of 100k (PIVOT)", lambda: api.ok("GET", "/forms/typed_100k/entries/count")
    )
    assert count["rows"] == 100_000
    page = timed(
        "column store: one page of 100k",
        lambda: api.ok("GET", "/forms/typed_100k/entries?limit=100&offset=50000"),
    )
    assert len(page) == 100 and page[0]["row_no"] == 50001 and isinstance(page[0]["amount"], float)


@pytest.mark.parametrize("scale", SCALES)
def test_c_reconciliation_against_the_known_answer_then_reset(bench: dict[str, Any], scale: str) -> None:
    app: App = bench["app"]
    trino, ledger = source_files(bench["tmp"], scale)
    period = None if scale == "medium" else "2025-12"  # medium: every month (1M against 1M); large: one month
    timed(
        f"{scale}: add the Trino copy and the ledger to the sandbox",
        lambda: [
            app.call("POST", "/sandbox/tables", {"from": "file", "path": str(p), "name": n, "replace": True})
            for p, n in ((trino, "trino_sales_lines"), (ledger, "ledger"))
        ],
    )
    listed = {t["name"]: t["rows"] for t in app.call("GET", "/sandbox")["tables"]}
    baseline = dict(listed)
    api = run_api(bench)
    form = f"ledger_{scale}"
    api.ok("PUT", f"/forms/{form}", {"title": f"Ledger ({scale})", "fields": FIELDS})
    batch = timed(
        f"{scale}: load the ledger from its table ({'every month' if period is None else period})",
        lambda: api.ok(
            "POST",
            f"/forms/{form}/batches/from-table",
            {
                "period": period or "2026-10",
                "table": "ledger",
                "period_column": "period" if period else "",
                "mapping": {
                    "line_id": "line_id",
                    "period": "period",
                    "store_id": "store_id",
                    "amount": "amount",
                },
            },
        ),
    )
    count = timed(
        f"{scale}: column store count (PIVOT over {batch['rows']:,} entries)",
        lambda: api.ok("GET", f"/forms/{form}/entries/count"),
    )
    assert count["rows"] == batch["rows"]
    api.ok("PUT", f"/recons/{form}", RECON | {"form_id": form})
    run = timed(
        f"{scale}: reconcile {batch['rows']:,} entries against the source",
        lambda: api.ok("POST", f"/recons/{form}/runs", {"period": period or "all"}),
    )
    want = expected(trino, ledger, period)
    got = {
        "matched": run["matched"],
        "difference": run["differences"],
        "only_entries": run["only_entries"],
        "only_source": run["only_source"],
        "duplicate": run["duplicates"],
    }
    RESULTS["timings"][f"{scale}: counts"] = got
    print(scale, got, flush=True)
    assert got == want
    total = run["totals"][0]
    source_sum = duckdb.execute(
        f"SELECT round(sum(amount), 2) FROM '{trino}'" + (f" WHERE period = '{period}'" if period else "")
    ).fetchall()[0][0]
    assert abs(total["source"] - float(source_sum)) < 0.05
    page = timed(
        f"{scale}: a page of differences",
        lambda: api.ok("GET", f"/runs/{run['run_id']}/results?status=difference&limit=100&offset=100"),
    )
    assert len(page) == 100 and all(abs(r["difference"]) > 0.01 for r in page)
    # Reset: every table back to the baseline, exactly.
    changed = {t["name"]: t["rows"] for t in app.call("GET", "/sandbox")["tables"]}
    assert changed["entries"] > baseline["entries"]
    timed(f"{scale}: Reset", lambda: app.call("POST", "/sandbox/reset", {}))
    after = {t["name"]: t["rows"] for t in app.call("GET", "/sandbox")["tables"]}
    assert after == baseline
    assert app.call("GET", "/sandbox")["log"] in ({}, [], None)


def _widget_functions(file: str, *names: str) -> dict[str, Any]:
    """A prebuilt widget's own functions, as its page runs them (its file read with ast, never imported:
    its top level draws Streamlit)."""
    import difflib
    import re

    import pandas as pd

    source = (WIDGETS / file).read_text(encoding="utf-8")
    tree = ast.parse(source)

    def wanted(node: ast.stmt) -> bool:
        if isinstance(node, ast.FunctionDef):
            return node.name in names
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        return any(isinstance(t, ast.Name) and t.id in ("_SAME", "match_cutoff") for t in targets)

    picked = [n for n in tree.body if wanted(n)]

    class Quiet:
        def warning(self, *a: Any) -> None:
            raise AssertionError(a)

    space: dict[str, Any] = {"pd": pd, "io": io, "re": re, "difflib": difflib, "st": Quiet()}
    exec(compile(ast.Module(picked, []), file, "exec"), space)  # noqa: S102 (the repository's own widget)
    return space


def test_d_an_excel_workbook_of_100k_rows_through_the_excel_widgets(bench: dict[str, Any]) -> None:
    import openpyxl

    api = run_api(bench)
    api.ok("PUT", "/forms/excel_100k", {"title": "Excel upload", "fields": FIELDS})
    book = openpyxl.Workbook(write_only=True)
    sheet = book.create_sheet("Ledger")
    sheet.append(["Line No", "Month", "Store", "Amt"])
    for n in range(100_000):
        sheet.append([n + 1, "2026-07", n % 40, round((n % 991) * 0.75, 2)])
    data = io.BytesIO()
    timed("excel: write 100k rows (openpyxl)", lambda: book.save(data))
    upload = _widget_functions("excel_upload.widget.py", "_read", "_guess")
    mapper = _widget_functions("excel_map_columns.widget.py", "_plain", "_guess_for")
    frame, names = timed(
        "excel: read 100k rows (excel_upload's _read)",
        lambda: upload["_read"](data.getvalue(), "ledger.xlsx", "", 1, "", openpyxl),
    )
    assert names == ["Ledger"] and len(frame) == 100_000
    columns = list(frame.columns)
    mapping = {f["name"]: mapper["_guess_for"](f["name"], columns) for f in FIELDS}
    # The widget matches three by their names; Month is picked by hand for period, as a user would.
    assert mapping == {"line_id": "Line No", "period": None, "store_id": "Store", "amount": "Amt"}, mapping
    mapping["period"] = "Month"
    rows = [
        {field: row[column] for field, column in mapping.items()} for row in frame.to_dict(orient="records")
    ]

    def send() -> int:
        made = api.ok(
            "POST",
            "/forms/excel_100k/batches",
            {"period": "2026-07", "source": "excel", "loaded_by": "Cleo Calloway", "rows": rows[:10000]},
        )
        for at in range(10000, len(rows), 10000):
            made = api.ok("POST", f"/batches/{made['batch_id']}/rows", {"rows": rows[at : at + 10000]})
        return int(made["rows"])

    assert timed("excel: send 100k rows to the API (10 parts)", send) == 100_000
    assert api.ok("GET", "/forms/excel_100k/entries/count")["rows"] == 100_000
