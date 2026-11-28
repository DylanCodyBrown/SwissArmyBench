"""Test app one: the BI review (examples/bi_review), built through the agent's commands against a real server,
then each part checked against what the app said and wrote. Made-up data (Larkfield Goods, small).

The build runs once for the module (about a minute); each test reads what it made. The user's one part, the
export's Allow, is answered as the user (no X-Actor), never by the agent's own commands."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import openpyxl
import pyarrow.parquet as pq
import pytest
from examples.bi_review import build as app
from tools.testbed import large_company

from swissarmybench.cli.commands import execute
from swissarmybench.server.app import create_app
from swissarmybench.settings import Settings
from tests.conftest import TOKEN
from tests.fake_keyring import memory_keyring
from tests.live_server import running

YAML = importlib.util.find_spec("yaml") is not None
KEPT = ("SWISSARMYBENCH_INFO", "LARKFIELD_DIR", "TARGET_GROWTH")


def answer(text: str) -> Any:
    if "<untrusted-data" in text:
        text = text[
            text.index(">", text.index("<untrusted-data source=")) + 1 : text.index("</untrusted-data>")
        ]
    return json.loads(text) if text.lstrip().startswith(("{", "[")) else text


class Agent:
    """The agent's commands (the MCP tools' one registry), and the Power BI extension's."""

    def __init__(self) -> None:
        from swissarmybench_powerbi import extension as powerbi

        self.powerbi = powerbi.commands()

    def __call__(self, command: str, /, **args: Any) -> Any:
        if command in self.powerbi:  # the extension's tool: its own command, as the MCP runs it
            return answer(json.dumps(self.powerbi[command].run(args), default=str))
        return answer(execute(command, args))


def user(port: int, method: str, path: str, body: Any = None) -> Any:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.loads(response.read() or b"null")


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[app.Built]:
    tmp = tmp_path_factory.mktemp("bi_review")
    data = tmp / "larkfield"
    large_company.build(data, "small", duckdb_file=True)
    settings = Settings(
        state_dir=tmp / "state",
        export_dir=tmp / "exports",
        projects_dir=tmp / "projects",
        workbench_dir=tmp / "wb",
        auto_load_catalogs=False,
    )
    saved = {k: os.environ.get(k) for k in KEPT}
    try:
        with memory_keyring(), running(lambda port: create_app(port, TOKEN, settings)) as (port, _server):
            info = tmp / "server.json"
            info.write_text(json.dumps({"port": port, "token": TOKEN}), encoding="utf-8")
            os.environ["SWISSARMYBENCH_INFO"] = str(info)

            @contextmanager
            def allow() -> Iterator[None]:
                """The user clicks Allow on what the agent's next step asks (an export, a save with rows)."""
                done = threading.Event()

                def click() -> None:
                    while not done.is_set():
                        for asked in user(port, "GET", "/agent/approvals")["pending"]:
                            user(port, "POST", f"/agent/approvals/{asked['id']}", {"approve": True})
                        time.sleep(0.05)

                helper = threading.Thread(target=click, daemon=True)
                helper.start()
                try:
                    yield
                finally:
                    done.set()
                    helper.join(5)

            made = app.build(Agent(), allow, data, tmp / "projects" / "bi_review", yaml=YAML, powerbi=True)
            (tmp / "facts.json").write_text(json.dumps(made.facts, default=str, indent=1), encoding="utf-8")
            made.facts["export_dir"] = str(tmp / "exports")
            made.facts["data"] = str(data)
            yield made
            try:
                user(port, "POST", "/project/close", {"discard": True})
            except Exception:  # noqa: S110 (closed already)
                pass
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def changes_of(built: app.Built, kind: str) -> list[dict[str, Any]]:
    return [c for c in built.facts["changes"] if c["object"]["kind"] == kind]


# ===== the project and its connections =====


def test_a_bi_project_with_five_connections_each_tested_and_listing_its_tables(built: app.Built) -> None:
    f = built.facts
    assert f["project"]["type"] == "bi" and (built.folder / "data.ipynb").is_file()
    assert 'os.environ["LARKFIELD_DIR"]' in f["files_code"]  # ${LARKFIELD_DIR} in the box: never the path
    assert all(t["ok"] for t in f["tested"].values()), f["tested"]
    assert f["tested"]["Targets"]["preview"]["columns"] == ["region_id", "month", "target"]
    assert '[Larkfield Files]."order_lines.parquet"' in f["tables"]["Larkfield Files"]
    assert "[Larkfield Warehouse].orders" in f["tables"]["Larkfield Warehouse"]
    assert set(f["tables"]["Larkfield Archive"]) == {
        f"[Larkfield Archive].{t}" for t in ("customers", "products", "regions")
    }
    assert f["tables"]["Store List"] == ["[Store List].stores"]
    assert f["tables"]["Targets"] == ["[Targets].monthly_targets"]
    colours = {c["name"]: c["colour"] for c in f["colour"]["connections"]}
    assert colours["Larkfield Warehouse"] == "#c2410c" and len(set(colours.values())) == len(colours)
    assert (f["limits"]["total"], f["limits"]["agent"], f["limits"]["wait"]) == (4, 2, 60)
    slots = {s["connection"]: s for s in f["slots"]}
    assert slots["Larkfield Warehouse"]["limits"] == {"total": 4, "agent": 2, "wait": 60}
    assert f["queries"]["finished"] and all(q["outcome"] == "ok" for q in f["queries"]["finished"])
    # DuckDB SQL naming three connections' tables: each read once, only the columns the query needs.
    reads = {r["as"]: r for r in f["monthly_reads"]}
    assert reads["[Larkfield Warehouse].orders"]["sent"]["columns"] == ["order_date", "order_id", "store_id"]
    assert reads["[Larkfield Files].order_lines.parquet"]["rows"] == 10042


def test_a_tables_connection_swapped_undone_and_swapped_again_and_a_file_connections_table_keeps_its_own(
    built: app.Built,
) -> None:
    swap = built.facts["swap"]
    assert swap["first"]["swapped"]["to"] == "Larkfield Archive"
    assert (
        swap["undo"]["connection"] == "Larkfield Warehouse"
        and swap["back"]["connection"] == "Larkfield Warehouse"
    )
    assert swap["now"]["connection"] == "Larkfield Archive" and swap["now"]["undo"] is True
    # The folder connection's file is that connection's table (it was a bare path on this disk).
    assert swap["order_lines"]["connection"] == "Larkfield Files" and swap["order_lines"]["exists"]
    assert swap["order_lines"]["place"]["table"] == "order_lines.parquet"


# ===== grids =====


def test_every_kind_of_step_a_profile_a_compare_that_ties_out_and_the_key_finder(built: app.Built) -> None:
    f = built.facts
    assert "needs a type" in f["step_error"]["message"]  # the first try's rule, said plainly
    customers = f["customers"]
    assert customers["step_error"] is None
    assert [s["kind"] for s in customers["steps"]] == [kind for kind, _ in app.STEPS]
    assert customers["view_rows"] == 400
    assert [c["name"] for c in customers["columns"]][-3:] == ["tier_band", "signup", "signup_month"]
    profiled = {c["column"]: c for c in f["profile"]["columns"]}
    assert profiled["signup_month"]["type"] == "DATE" and profiled["customer_id"]["distinct"] == 400
    assert {v["value"] for v in f["column_profile"]["top_values"]} == {"Top", "Other"}
    assert (
        f["by_product"]["columns"] == ["product_id", "revenue", "lines"]
        and f["by_product"]["row_count"] == 240
    )
    assert f["compare"]["counts"] == {"matched": 192, "left_only": 0, "right_only": 0}
    assert f["tie_out_choices"]["suggested"] == {"group": ["region"], "measures": ["orders", "revenue"]}
    groups = f["tie_out"]["groups"]
    assert len(groups) == 8 and all(g["status"] == "ties" for g in groups)
    pairs = {(p["source_column"], p["target_dataset"]) for p in f["key_finder"]["pairs"]}
    assert ("order_id", "order_lines") in pairs and ("customer_id", "customers") in pairs


def test_relationships_found_set_drawn_and_saved_as_a_set(built: app.Built) -> None:
    f = built.facts
    found = {(s["from"], s["to"]) for s in f["found"]}
    assert {
        ("orders", "customers"),
        ("orders", "stores"),
        ("order_lines", "products"),
        ("stores", "regions"),
    } <= found
    erd = f["erd"]["mermaid"]
    assert erd.startswith("erDiagram") and "orders ||--o{ order_lines" in erd
    assert set(f["erd_card"]["tables"]) >= {"orders", "order_lines", "customers"}
    (kept,) = [s for s in f["sets"] if s["name"] == "Larkfield sales"]
    assert kept["relationships"] == 8 and Path(f["set"]["file"]).is_file()


def test_the_monthly_sales_exported_as_csv_parquet_and_excel_on_the_users_allow(built: app.Built) -> None:
    saved = {k: Path(v) for k, v in built.facts["exports"].items()}
    assert {p.name for p in saved.values()} == {
        "monthly_sales.csv",
        "monthly_sales.parquet",
        "monthly_sales.xlsx",
    }
    assert saved["csv"].read_text(encoding="utf-8").splitlines()[0] == "region,month,orders,revenue"
    assert pq.read_table(saved["parquet"]).num_rows == 192
    sheet = openpyxl.load_workbook(saved["xlsx"], read_only=True).worksheets[0]
    assert next(sheet.iter_rows(values_only=True))[:4] == ("region", "month", "orders", "revenue")


# ===== Analyze =====


def test_every_analysis_contract_runs_on_columns_that_fit_and_lands_on_the_board(built: app.Built) -> None:
    f = built.facts
    contracts = {c["id"] for c in f["contracts"]["contracts"]}
    ran = set(f["runs"])
    assert contracts == ran, contracts ^ ran  # every analysis on the toolbar, run once
    assert all(item["status"] == "now" for item in f["ranked"])
    for analysis, result in f["runs"].items():
        assert result["cards"], analysis
    assert f["runs"]["predictors"]["columns"]["target"] == "returned"
    assert f["runs"]["time_series"]["columns"] == {"date": "order_date", "metric": "line_total"}
    # Make it fit: the archive's text dates read as dates by one grid step, then the series runs.
    assert "dates needs a date column" in json.dumps(f["fit_before"]["slots"])
    assert f["fitted"]["columns"]["date"] == "signup_date" and f["fitted"]["cards"]
    assert f["dashboard"]["name"] == "monthly_sales_review" and f["dashboard"]["cards"] >= 2 * len(ran)
    assert [d["name"] for d in f["dashboards"]["dashboards"]] == ["monthly_sales_review"]
    assert (built.folder / ".sab" / "visualizations" / "monthly_sales_review.json").is_file()


# ===== the Workbench =====


def test_data_ipynb_runs_in_one_python_session_with_the_script(built: app.Built) -> None:
    f = built.facts
    cells = f["notebook"]["cells"]
    assert [c["kind"] for c in cells] == ["markdown", "sql", "sql", "code", "html"]
    assert cells[1]["connection"] == "Larkfield Warehouse -> region_orders"
    text = (built.folder / "data.ipynb").read_text(encoding="utf-8")
    assert "%%sql 'Larkfield Warehouse' -> region_orders" in text and "%%sql -> monthly" in text
    assert f["kernel"]["session"]["shared"] and f["same_session"]
    assert f["ran"]["cells_run"] == 4 and all(r["done"]["ok"] for r in f["ran"]["results"])
    assert "<h2>Best region: North Vale</h2>" in json.dumps(f["ran"]["results"][-1]["outputs"])
    assert f["script_ran"]["done"]["ok"] and "'orders': 3337" in f["script_ran"]["outputs"][0]["text"]
    assert f["shared"]["outputs"][0]["text"].startswith("3337 North Vale ")
    assert "<h2>Best region: North Vale</h2>" in f["html"]["html"]
    kinds = [n["kind"] for n in f["lineage"]["nodes"]]
    assert kinds[:2] == ["source", "table"] and kinds.count("cell") == 2


def test_data_py_keeps_the_sql_cells_results_and_both_export_as_one_automation(built: app.Built) -> None:
    f = built.facts
    data_py = (built.folder / "data.py").read_text(encoding="utf-8")
    assert (
        'region_orders = sab.sql("Larkfield Warehouse", """' in data_py and 'monthly = sab.sql("""' in data_py
    )
    assert f["data_py"]["names"][:3] == ["region_orders", "monthly", "by_region"]
    exported = f["exported"]["script"]
    path = Path(exported["path"])
    text = path.read_text(encoding="utf-8")
    assert re.search(r"run_sql\(\s*['\"]Larkfield Warehouse['\"]", text), text[-3000:]
    assert "sab." not in text.split("def run() -> None:")[1]
    assert not exported["problems"] and "connect_larkfield_warehouse" in text.replace(
        "def connect_", "connect_"
    )
    done = subprocess.run(  # noqa: S603 (the exported script, in this Python)
        [sys.executable, str(path)], capture_output=True, text=True, timeout=120, check=False, cwd=path.parent
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "'orders': 3337" in done.stdout
    assert f["exported"]["data"]["problems"] == ["cell 3: the SQL cell names no connection"]


def test_the_excel_deliverable_has_its_table_and_a_total_row(built: app.Built) -> None:
    assert built.facts["workbook_ran"]["done"]["ok"]
    sheet = openpyxl.load_workbook(built.folder / "workbooks" / "monthly_review.xlsx")["Review"]
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0][0] == "Revenue by region" and rows[1] == ("Region", "orders", "revenue")
    assert rows[2][0] == "North Vale" and rows[-1] == ("Total", "=SUM(B3:B10)", "=SUM(C3:C10)")


# ===== Structures =====


def test_a_json_and_a_toml_file_with_steps_as_grids_and_saved(built: app.Built) -> None:
    f = built.facts
    assert f["plan_grid"]["rows"] == 2 and f["thresholds_grid"]["rows"] == 2
    saved = json.loads((built.folder / "structures" / "review_plan_open.json").read_text(encoding="utf-8"))
    assert [r["region"] for r in saved["regions"]] == ["North Vale", "Highlands"]
    assert all("monthly_target" in r and "target" not in r for r in saved["regions"])
    thresholds = json.loads((built.folder / "structures" / "thresholds.json").read_text(encoding="utf-8"))
    assert [t["metric"] for t in thresholds["thresholds"]] == ["orders", "revenue"]
    if YAML:
        assert f["yaml"]["format"] == "yaml"


# ===== read back: the outline, the change log, the statistics, the Environment, Power BI =====


def test_the_outline_names_every_connection_and_lists_only_the_users_scripts(built: app.Built) -> None:
    text = (built.folder / "ARCHITECTURE.md").read_text(encoding="utf-8")
    for name in ("Larkfield Files", "Larkfield Warehouse", "Larkfield Archive", "Targets"):
        assert f"- `{name}`:" in text, name
    assert "`order_lines`: from connection `Larkfield Files`" in text
    assert "a file outside the project" not in text
    deliverables = text.split("## 6. Deliverables")[1].split("## 7.")[0]
    assert "`adapter.py`" not in deliverables and "`scripts/monthly_review.py`" in deliverables
    assert str(built.facts["data"]) not in text  # no path of this disk


def test_the_change_log_and_the_statistics_say_what_happened(built: app.Built) -> None:
    tables = {c["object"]["name"] for c in changes_of(built, "table")}
    assert {"orders", "monthly_sales", "sales_lines", "customers"} <= tables
    notebook = changes_of(built, "notebook")
    assert notebook and notebook[0]["who"] == "agent"  # the agent saved data.ipynb
    assert {c["object"]["name"] for c in changes_of(built, "script")} >= {
        "monthly_review.py",
        "review_workbook.py",
    }
    assert not any(
        "0.05" in json.dumps(c) for c in built.facts["changes"] if c["object"]["kind"] == "variable"
    )
    stats = built.facts["stats"]
    assert stats["calls"] > 10 and stats["errors"] == 0
    busiest = {b["object"] for b in stats["busiest"]}
    assert "connection:Larkfield Warehouse" in busiest
    assert built.facts["stats_connection"]["action"] == "connection"


def test_the_environment_shows_each_kind_and_powerbis_plan_takes_the_erds_tables(built: app.Built) -> None:
    env = built.facts["environment"]
    kinds = {row["kind"] for row in app.records(env["list"]) if "kind" in row and "name" in row}
    assert {"table", "variable", "structure", "setting", "library"} <= kinds
    assert env["table"]["name"] == "monthly_sales" and env["setting"]["name"] == "LARKFIELD_DIR"
    assert env["variable"]["name"] == "best_region"  # the project's Python session's
    uses = app.text_of(env["uses"])
    assert "Larkfield Files" in uses
    plan = {t["name"]: t for t in built.facts["powerbi"]["tables"]}
    assert plan["order_lines"]["goes"]  # the folder connection's Parquet file: Power Query reads it
    # Power Query has no reader for a DuckDB or SQLite file: each says so, and how its rows could go instead.
    assert plan["orders"]["why"] == "Power Query has no reader here for a duckdb connection"
    assert plan["customers"]["why"] == "Power Query has no reader here for a sqlite connection"
    assert plan["orders"]["fix"].startswith("Include its rows")


# ===== the project again =====


def test_saved_closed_opened_again_with_every_table_and_its_steps_and_copied(built: app.Built) -> None:
    f = built.facts
    reopened = f["reopened"]["project"]
    assert reopened["problems"] == [], reopened["problems"]
    names = {t["name"] for t in reopened["tables"]}
    assert {"order_lines", "orders", "customers", "monthly_sales", "sales_lines", "monthly_targets"} <= names
    saved = json.loads((built.folder / ".sab" / "project.json").read_text(encoding="utf-8"))
    source = {t["name"]: t["source"] for t in saved["tables"]}
    assert source["order_lines"]["connection"] == "Larkfield Files"
    assert source["customers"]["connection"] == "Larkfield Archive"
    assert f["data"] not in json.dumps(saved)  # no path of this disk in the project
    steps = {t["name"]: [len(g["steps"]) for g in t["grids"]] for t in saved["tables"]}
    assert steps["customers"][0] == len(app.STEPS)
    copied = Path(f["copied"]["copied"])
    assert (copied / ".sab" / "project.json").is_file() and (copied / "data.ipynb").is_file()
