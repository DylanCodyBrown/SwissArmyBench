"""The Analyze page over HTTP (services/analyze.py): every analysis runs on its contract's own made-up
sample and lands its cards; fixes are grid steps applied on the caller's word; and the edge cases (an empty
table, one row, blank columns, mixed text, uneven dates, a huge table's limit, a table closed mid-form, two
runs at once, a cancelled run, a column renamed after the form filled it). Made-up data only."""

from __future__ import annotations

import datetime as dt
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import analysis_contracts as C
from tests.analyze_data import orders
from tests.conftest import AGENT, AUTH, grid_id, make_client, push

IDS = [c.id for c in C.CONTRACTS]


def post(client: TestClient, path: str, body: Any = None, headers: dict[str, str] | None = None) -> Any:
    return client.post(path, json=body or {}, headers=headers or AUTH)


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def board(client: TestClient) -> list[dict[str, Any]]:
    return list(ok(client.get("/cards", headers=AUTH))["cards"])


def steps_of(client: TestClient, grid: str) -> list[dict[str, Any]]:
    return list(ok(client.get(f"/grids/{grid}", headers=AUTH))["steps"])


@pytest.fixture
def app(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path) as client:
        yield client


@pytest.fixture
def table(app: TestClient) -> str:
    return grid_id(push(app, "orders", orders()))


# ===== the toolbar, the contracts, the tables =====


def test_the_toolbar_lists_every_analysis_in_its_group(app: TestClient, table: str) -> None:
    found = ok(app.get("/analyze", headers=AUTH))
    assert found["groups"] == ["Describe", "Test", "Model", "Time", "Compare", "Yours"]
    assert [a["id"] for a in found["analyses"]] == IDS
    assert found["tables"] == [{"grid": table, "dataset": "orders", "label": "orders", "steps": 0}]
    assert found["current"] == table


def test_the_contracts_are_served_with_their_samples_to_the_agent_too(app: TestClient) -> None:
    everything = ok(app.get("/analyze/contracts", headers=AGENT))
    assert everything["format"] == 1 and [c["id"] for c in everything["contracts"]] == IDS
    one = ok(app.get("/analyze/contracts/benford", headers=AGENT))
    assert one["slots"][0]["accepts"] == ["number"] and one["sample"]["slots"] == {"column": ["amount"]}
    missing = app.get("/analyze/contracts/astrology", headers=AUTH)
    assert missing.status_code == 400 and missing.json()["error"].startswith("No analysis 'astrology'")


def test_a_table_says_its_steps_and_the_front_one_is_where_a_form_starts(app: TestClient, table: str) -> None:
    other = grid_id(push(app, "ledger", pa.table({"region": ["West", "East"], "amount": [1.0, 2.0]})))
    step = {"kind": "filter", "params": {"column": "region", "op": "eq", "value": "West"}}
    ok(post(app, f"/grids/{table}/step-ops", {"op": "add", "step": step}))
    found = ok(app.get(f"/analyze?front={other}", headers=AUTH))
    assert found["current"] == other
    assert found["tables"][0]["label"] == "orders, with 1 step"
    plan = ok(post(app, "/analyze/plan", {"analysis": "benford", "table": table}))
    assert plan["table_label"] == "orders, with 1 step" and plan["rows"] == 96  # its steps applied
    assert plan["sentence"] == "Test whether amount follows Benford's first-digit law, on 96 rows of orders."


# ===== the sweep: every analysis runs on its own sample and lands its cards =====


@pytest.mark.parametrize("analysis", IDS)
def test_every_analysis_runs_on_its_own_sample_and_lands_cards(app: TestClient, analysis: str) -> None:
    ran = ok(post(app, "/analyze/run", {"analysis": analysis, "sample": True}))
    assert ran["analysis"] == analysis and ran["dataset"] == f"sample_{analysis}"
    assert ran["cards"] and ran["sentence"] and isinstance(ran["result"], dict)
    cards = board(app)
    assert [c["id"] for c in cards[: len(ran["cards"])]] == ran["cards"]  # at the top, in the order made
    first = cards[0]
    assert first["analysis"]["run"] == ran["run"] and first["analysis"]["first"] is True
    assert first["analysis"]["columns"] == ran["columns"] and first["grid"] is None
    assert first["kind"] == "note" and first["body"].startswith("# ")
    contract = C.contract(analysis)
    assert {c["kind"] for c in cards[: len(ran["cards"])]} <= set(contract.output.cards) | {"note"}
    # what the contract says it makes is what a result's actions offer
    assert ("grid" in ran["actions"]) == bool(contract.output.table)
    for action in ran["actions"]:
        if action == "math":
            assert ok(app.get(f"/analyze/runs/{ran['run']}/math", headers=AUTH))["markdown"]
        if action == "code":
            assert "stats." in ok(app.get(f"/analyze/runs/{ran['run']}/code", headers=AUTH))["code"]
        if action == "grid":
            opened = ok(post(app, f"/analyze/runs/{ran['run']}/grid"))
            assert opened["rows"] >= 1 and opened["dataset"].startswith(f"sample_{analysis}_{analysis}")
    again = ok(app.get(f"/analyze/runs/{ran['run']}", headers=AUTH))
    assert again["columns"] == ran["columns"] and again["options"] == ran["options"]


def test_a_sample_opens_as_a_table_with_real_dates(app: TestClient) -> None:
    opened = ok(post(app, "/analyze/sample", {"analysis": "forecast"}))
    assert opened["dataset"] == "sample_forecast" and opened["columns"] == {
        "date": "order_month",
        "metric": "amount",
    }
    described = ok(app.get(f"/grids/{opened['grid']}", headers=AUTH))
    types = {c["name"]: c["type"] for c in described["columns"]}
    assert types["order_month"] == "DATE" and described["row_count"] == 24
    two = ok(post(app, "/analyze/sample", {"analysis": "tie_out"}))
    assert two["other"] and two["columns"] == {"other": two["other"]}


# ===== a run: its cards, newest first; the agent's the same =====


def test_run_picks_the_columns_itself_and_newer_runs_land_above_older(app: TestClient, table: str) -> None:
    first = ok(post(app, "/analyze/run", {"analysis": "benford", "table": table}))
    assert first["columns"] == {"column": "amount"} and first["options"] == {"digits": "1"}
    assert first["result"]["results"][0]["column"] == "amount"
    second = ok(post(app, "/analyze/run", {"analysis": "odds", "table": "orders"}))  # by its name too
    assert second["columns"] == {"column": "region", "outcome": "late"}
    ids = [c["id"] for c in board(app)]
    assert ids == second["cards"] + first["cards"]
    runs = ok(app.get("/analyze/runs", headers=AUTH))["runs"]
    assert [r["run"] for r in runs] == [second["run"], first["run"]]
    assert runs[0]["cards"] == second["cards"]


def test_the_agents_run_lands_on_the_board_as_the_users_does(app: TestClient, table: str) -> None:
    ran = ok(post(app, "/analyze/run", {"analysis": "outliers", "table": table}, AGENT))
    cards = board(app)
    assert [c["id"] for c in cards] == ran["cards"]
    assert cards[0]["created_by"] == "agent" and cards[0]["origin"] == "Agent"
    log = ok(app.get("/audit?limit=5", headers=AUTH))
    assert any(e["action"] == "analyze_run" and e["actor"] == "agent" for e in log["entries"])


def test_the_last_columns_and_options_come_back_per_table_and_analysis(app: TestClient, table: str) -> None:
    body = {
        "analysis": "outliers",
        "table": table,
        "columns": {"column": "units"},
        "options": {"method": "iqr"},
    }
    ok(post(app, "/analyze/run", body))
    plan = ok(post(app, "/analyze/plan", {"analysis": "outliers", "table": table}))
    assert plan["remembered"] is True and plan["columns"] == {"column": "units"}
    assert plan["settings"]["method"] == "iqr"
    other = ok(post(app, "/analyze/plan", {"analysis": "benford", "table": table}))
    assert other["remembered"] is False and other["columns"] == {"column": "amount"}
    assert ok(app.get("/analyze", headers=AUTH))["current"] == table  # the last used in Analyze


def test_run_again_with_changed_inputs_is_a_new_run(app: TestClient, table: str) -> None:
    first = ok(post(app, "/analyze/run", {"analysis": "time_series", "table": table}))
    inputs = ok(app.get(f"/analyze/runs/{first['run']}", headers=AUTH))
    changed = inputs | {"options": inputs["options"] | {"period": "quarter"}}
    second = ok(
        post(app, "/analyze/run", {k: changed[k] for k in ("analysis", "table", "columns", "options")})
    )
    assert second["run"] != first["run"] and second["options"]["period"] == "quarter"
    assert len(board(app)) == len(first["cards"]) + len(second["cards"])


def test_the_hand_offs_to_the_next_tool_ride_on_the_card(app: TestClient, table: str) -> None:
    ran = ok(post(app, "/analyze/run", {"analysis": "predictors", "table": table}))
    nexts = board(app)[0]["analysis"]["next"]
    assert ran["columns"]["target"] == "late"
    assert all(n["label"] and ("analysis" in n or "step" in n) for n in nexts)
    series = ok(post(app, "/analyze/run", {"analysis": "time_series", "table": table}))
    labels = [n["label"] for n in board(app)[0]["analysis"]["next"]]
    assert "What comes next?" in labels and series["cards"]


def test_whatif_runs_with_values_to_try(app: TestClient, table: str) -> None:
    plan = ok(post(app, "/analyze/plan", {"analysis": "whatif", "table": table}))
    tries = [o for o in plan["options"] if o.get("what_if")]
    assert [o["label"] for o in tries] == ["region", "units", "late"]
    options = {"value:region": "West", "value:units": 6, "value:late": "no"}
    ran = ok(post(app, "/analyze/run", {"analysis": "whatif", "table": table, "options": options}))
    assert ran["result"]["values"] == {"region": "West", "units": 6.0, "late": "no"}
    assert "estimate" in ran["result"]["prediction"] or ran["result"]["prediction"]


def test_tie_out_picks_two_tables_and_makes_no_compare_on_the_grid_page(app: TestClient, table: str) -> None:
    ledger = pa.table({"region": ["West", "North", "East", "South"], "amount": [1.0, 2.0, 3.0, 4.0]})
    other = grid_id(push(app, "ledger", ledger))
    plan = ok(post(app, "/analyze/plan", {"analysis": "tie_out", "table": table}))
    assert plan["slots"][0]["table"] is True and plan["columns"] == {"other": other}
    ran = ok(post(app, "/analyze/run", {"analysis": "tie_out", "table": table, "columns": {"other": other}}))
    assert ran["result"]["left_name"] == "orders" and ran["result"]["right_name"] == "ledger"
    assert [c["kind"] for c in board(app)[:2]] == ["note", "table"]
    assert ok(app.get("/compares", headers=AUTH))["compares"] == []
    keys = ok(post(app, "/analyze/run", {"analysis": "key_finder", "table": table}))
    assert keys["columns"] == {"other": None} and keys["cards"]


# ===== Yours: an analysis blade through the same form =====

BY_REGION = """import pandas as pd


def analyze(df: pd.DataFrame, columns: list[str]) -> list:
    column = columns[0] if columns else "region"
    counts = df[column].value_counts().rename_axis(column).reset_index(name="rows")
    return [f"## {len(df)} rows by {column}", counts]
"""
DECLARED = """CONTRACT = {
    "label": "Which regions carry the amounts?",
    "one_row_per": "one row per order",
    "slots": [
        {"key": "group", "label": "Group", "accepts": ["category"], "hints": ["region"]},
        {"key": "amount", "label": "Amounts", "accepts": ["number"], "hints": ["amount"]},
    ],
}


def analyze(df, columns):
    group, amount = columns
    totals = df.groupby(group)[amount].sum().reset_index()
    return [f"## {amount} by {group}", totals]
"""


def save_blade(client: TestClient, name: str, code: str) -> None:
    body = {"name": name, "kind": "analysis", "code": code, "variable": "analyze"}
    assert client.post("/blades", json=body, headers=AUTH).status_code == 200


def test_your_own_analysis_is_on_the_toolbar_with_a_contract_read_from_its_code(
    app: TestClient, table: str
) -> None:
    from tests.fake_keyring import memory_keyring

    with memory_keyring():
        save_blade(app, "By region", BY_REGION)
        save_blade(app, "Totals", DECLARED)
        save_blade(app, "Whole table", "def analyze(df):\n    return f'## {len(df)} rows'\n")
        save_blade(app, "Broken", "CONTRACT = {'slots': 'nope'}\ndef analyze(df):\n    return 'x'\n")
        mine = [a for a in ok(app.get("/analyze", headers=AUTH))["analyses"] if a["group"] == "Yours"]
        assert [a["id"] for a in mine] == ["blade:By region", "blade:Totals", "blade:Whole table"]
        derived = ok(app.get("/analyze/contracts/blade:By region", headers=AGENT))
        assert derived["slots"][0]["key"] == "columns" and derived["slots"][0]["count"] == "any"
        assert derived["sample"]["columns"] == ["row_id", "columns"]
        assert ok(app.get("/analyze/contracts/blade:Whole table", headers=AUTH))["slots"] == []
        declared = ok(app.get("/analyze/contracts/blade:Totals", headers=AUTH))
        assert declared["label"] == "Which regions carry the amounts?"
        assert [s["accepts"] for s in declared["slots"]] == [["category"], ["number"]]
        broken = app.get("/analyze/contracts/blade:Broken", headers=AUTH)
        assert broken.status_code == 400
        assert broken.json()["error"] == "Broken's CONTRACT cannot be read: CONTRACT's slots is a list."
        ids = [c["id"] for c in ok(app.get("/analyze/contracts", headers=AUTH))["contracts"]]
        assert ids[-3:] == ["blade:By region", "blade:Totals", "blade:Whole table"]
        # the same form: the declared slots are picked by the same checker, and its cards land
        plan = ok(post(app, "/analyze/plan", {"analysis": "blade:Totals", "table": table}))
        assert plan["columns"] == {"group": "region", "amount": "amount"}
        assert plan["sentence"] == "Run Which regions carry the amounts? on 240 rows of orders."
        ran = ok(post(app, "/analyze/run", {"analysis": "blade:Totals", "table": table}))
        cards = board(app)
        assert [c["id"] for c in cards] == ran["cards"] and [c["kind"] for c in cards] == ["note", "table"]
        assert cards[0]["title"] == "Totals" and cards[0]["body"] == "## amount by region"
        assert cards[0]["analysis"]["actions"] == ["again"] and cards[1]["columns"] == ["region", "amount"]
        chosen = {"analysis": "blade:By region", "table": table, "columns": {"columns": ["late"]}}
        assert ok(post(app, "/analyze/run", chosen))["columns"] == {"columns": ["late"]}
        assert board(app)[0]["body"] == "## 240 rows by late"
        tried = ok(post(app, "/analyze/run", {"analysis": "blade:Totals", "sample": True}))
        assert tried["dataset"] == "sample_totals" and tried["columns"] == {
            "group": "group",
            "amount": "amount",
        }


def test_your_own_analysis_that_fails_says_why_in_the_one_shape(app: TestClient, table: str) -> None:
    from tests.fake_keyring import memory_keyring

    with memory_keyring():
        save_blade(app, "Breaks", "def analyze(df):\n    return df['nowhere']\n")
        broke = post(app, "/analyze/run", {"analysis": "blade:Breaks", "table": table})
        assert broke.status_code == 422 and "KeyError" in broke.text and broke.json()["error"]
        assert board(app) == []
        missing = post(app, "/analyze/run", {"analysis": "blade:Nobody", "table": table})
        assert missing.status_code in (400, 404)


# ===== refusals: one shape, the form sent back =====


def test_a_table_that_does_not_fit_is_refused_in_the_one_shape_with_the_form(app: TestClient) -> None:
    grid = grid_id(push(app, "places", pa.table({"city": ["A", "B", "C", "D"] * 5})))
    refused = post(app, "/analyze/run", {"analysis": "time_series", "table": grid})
    assert refused.status_code == 409
    said = refused.json()
    assert said["error"] == "Nothing in places fits dates: it needs a date column."
    assert said["where"] == "places" and said["fixes"] == [{"label": "Try again", "action": "try_again"}]
    assert said["plan"]["ready"] is False and said["plan"]["grid"] == grid
    assert board(app) == []


def test_a_column_that_does_not_fit_is_refused_with_why(app: TestClient, table: str) -> None:
    refused = post(
        app, "/analyze/run", {"analysis": "benford", "table": table, "columns": {"column": "region"}}
    )
    assert refused.status_code == 409
    assert refused.json()["error"] == "Region is a text column: amounts needs a number column."
    assert refused.json()["plan"]["columns"] == {"column": "amount"}  # the form, with what does fit


def test_bad_requests_are_said_plainly(app: TestClient, table: str) -> None:
    assert post(app, "/analyze/run", {"analysis": "astrology"}).status_code == 400
    assert post(app, "/analyze/run", {"analysis": "benford", "columns": ["amount"]}).status_code == 400
    assert post(app, "/analyze/plan", []).status_code == 400
    gone = app.get("/analyze/runs/nope/math", headers=AUTH)
    assert gone.status_code == 404
    assert gone.json()["error"] == "That result is from an earlier session: run it again to use it."
    assert app.get("/analyze").status_code in (401, 403)  # the token, as every data route


# ===== make it fit =====


def almost() -> pa.Table:
    n = 120
    return pa.table(
        {
            "when": [(dt.date(2023, 1, 1) + dt.timedelta(days=7 * i)).isoformat() for i in range(n)],
            "amount": [f"{100 + (i * 37) % 900}" for i in range(n)],
            "region": [("West", "East", "North")[i % 3] for i in range(n)],
        }
    )


def test_check_proposes_fixes_and_apply_adds_them_as_steps_the_user_can_undo(app: TestClient) -> None:
    grid = grid_id(push(app, "sales", almost()))
    plan = ok(post(app, "/analyze/check", {"analysis": "time_series", "table": grid}))
    assert (
        plan["ready"] is False and plan["missing"] == "Nothing in sales fits dates: it needs a date column."
    )
    fix = next(f for f in plan["fixes"] if f["level"] == "needed")
    assert fix["sentence"] == "Read when as dates (year-month-day): 120 of 120 values are dates."
    assert fix["steps"][0]["kind"] == "sql" and steps_of(app, grid) == []  # proposed, never applied by itself
    fixed = ok(post(app, "/analyze/fix", {"analysis": "time_series", "table": grid, "fixes": [fix["id"]]}))
    assert fixed["applied"] == [fix["sentence"]] and fixed["ready"] is True
    assert fixed["columns"]["date"] == "when" and fixed["table_label"] == "sales, with 1 step"
    assert len(steps_of(app, grid)) == 1
    ok(post(app, f"/grids/{grid}/step-ops", {"op": "undo"}))  # the steps strip's Undo takes it back
    assert steps_of(app, grid) == []
    assert ok(post(app, "/analyze/plan", {"analysis": "time_series", "table": grid}))["ready"] is False


def test_the_original_data_is_never_changed_by_a_fix(app: TestClient) -> None:
    grid = grid_id(push(app, "sales", almost()))
    before = ok(app.get(f"/grids/{grid}/rows?start=0&end=3", headers=AUTH))["rows"]
    ran = ok(post(app, "/analyze/run", {"analysis": "benford", "table": grid, "apply_fixes": True}))
    assert ran["applied"] == ["Read amount as numbers: 120 of 120 values are numbers."]
    steps = steps_of(app, grid)
    assert len(steps) == 1
    ok(post(app, f"/grids/{grid}/step-ops", {"op": "delete", "index": 0}))
    assert ok(app.get(f"/grids/{grid}/rows?start=0&end=3", headers=AUTH))["rows"] == before


def test_check_this_table_ranks_and_one_click_applies_its_fixes_and_runs(app: TestClient) -> None:
    grid = grid_id(push(app, "sales", almost()))
    checked = ok(post(app, "/analyze/check", {"table": grid}))
    assert checked["dataset"] == "sales" and len(checked["top"]) == 3
    assert any(n["text"].startswith("when is text that reads as dates") for n in checked["notes"])
    pick = next(e for e in checked["ranked"] if e["analysis"] == "time_series")
    assert pick["status"] == "fixes" and pick["button"] == "Read when as dates and run"
    refused = post(app, "/analyze/run", {"analysis": "time_series", "table": grid})
    assert refused.status_code == 409  # not without the click that says so
    ran = ok(post(app, "/analyze/run", {"analysis": "time_series", "table": grid, "apply_fixes": True}))
    assert ran["applied"] == ["Read when as dates (year-month-day): 120 of 120 values are dates."]
    assert ran["columns"]["date"] == "when" and ran["cards"] and len(steps_of(app, grid)) == 1


def test_a_fix_that_is_not_one_of_the_tables_is_refused(app: TestClient, table: str) -> None:
    refused = post(
        app, "/analyze/fix", {"analysis": "benford", "table": table, "fixes": ["drop_table:orders"]}
    )
    assert refused.status_code == 409 and refused.json()["error"].startswith("No such fix for orders now")
    assert steps_of(app, table) == []


def test_the_top_n_fixs_count_is_counted_on_the_table(app: TestClient) -> None:
    n = 900
    cities = [f"city {i % 250 if i % 3 else i % 4}" for i in range(n)]
    grid = grid_id(push(app, "visits", pa.table({"city": cities})))
    counts: dict[str, int] = {}
    for city in cities:
        counts[city] = counts.get(city, 0) + 1
    covered = sum(sorted(counts.values(), reverse=True)[:10])
    plan = ok(post(app, "/analyze/plan", {"analysis": "fit", "table": grid}))
    fix = plan["fixes"][0]
    assert fix["kind"] == "top_n_other" and fix["count"] == covered
    assert fix["sentence"].endswith(f"they cover {covered} of 900 rows.")
    fixed = ok(post(app, "/analyze/fix", {"analysis": "fit", "table": grid, "fixes": [fix["id"]]}))
    assert fixed["ready"] and fixed["columns"] == {"column": "city_top"}
    assert ok(post(app, "/analyze/run", {"analysis": "fit", "table": grid, "columns": fixed["columns"]}))[
        "cards"
    ]


def test_what_can_i_do_with_a_column(app: TestClient, table: str) -> None:
    one = ok(post(app, "/analyze/column", {"table": table, "column": "order_date"}))
    assert [a["analysis"] for a in one["analyses"]] == ["time_series", "forecast"]
    every = ok(post(app, "/analyze/column", {"table": table}))
    by_name = {c["name"]: c for c in every["columns"]}
    assert by_name["order_id"]["analyses"] == [] and by_name["amount"]["type"] == "number"
    assert len(by_name["region"]["preview"]) == 3
    assert post(app, "/analyze/column", {"table": table, "column": "nope"}).status_code == 400


def test_the_data_shape_check_is_the_checkers_wide_tables_identifiers_and_benfords_range(
    app: TestClient, table: str
) -> None:
    """The old Data shape rules, folded into the one checker (no second copy)."""
    n = 60
    wide = pa.table(
        {
            "region": ["West", "North", "East"] * 20,
            "jan_sales": [10.0 + i % 7 for i in range(n)],
            "feb_sales": [11.0 + i % 5 for i in range(n)],
            "mar_sales": [12.0 + i % 3 for i in range(n)],
        }
    )
    grid = grid_id(push(app, "wide_sales", wide))
    checked = ok(post(app, "/analyze/check", {"table": grid}))
    assert checked["notes"][0]["level"] == "warn" and "looks wide" in checked["notes"][0]["text"]
    assert "jan_sales" in checked["notes"][0]["text"]
    ran = ok(post(app, "/analyze/run", {"analysis": "check", "table": grid}))
    assert "This table looks wide" in board(app)[0]["body"] and ran["result"]["suggested"]
    benford = ok(post(app, "/analyze/check", {"table": grid, "analysis": "benford"}, AGENT))
    cautions = benford["slots"][0]["cautions"]
    assert any("narrow range: Benford's law needs values from 10s to 1,000s" in c for c in cautions)
    odds = ok(
        post(app, "/analyze/check", {"table": table, "analysis": "odds", "columns": {"column": "order_id"}})
    )
    assert odds["refused"] == ["every row has a different order_id: an identifier tells nothing"]
    assert (
        post(app, f"/grids/{grid}/shape-check", {"analysis": "odds"}).status_code == 404
    )  # the old route went


# ===== the edge cases =====


def test_an_empty_table_says_so_for_every_analysis_and_never_fails(app: TestClient) -> None:
    empty = pa.table({"amount": pa.array([], pa.float64()), "region": pa.array([], pa.string())})
    grid = grid_id(push(app, "nothing", empty))
    for analysis in IDS:
        plan = ok(post(app, "/analyze/plan", {"analysis": analysis, "table": grid}))
        if analysis == "key_finder":
            continue
        assert plan["ready"] is False, analysis
        assert plan["missing"].startswith("nothing has no rows") or "second open table" in plan["missing"], (
            analysis
        )
        assert post(app, "/analyze/run", {"analysis": analysis, "table": grid}).status_code == 409
    checked = ok(post(app, "/analyze/check", {"table": grid}))
    assert checked["notes"][0] == {"level": "warn", "text": "nothing has no rows."}
    assert [e["analysis"] for e in checked["top"]] in ([], ["key_finder"])


def test_one_row_is_too_few_and_says_how_many_it_needs(app: TestClient) -> None:
    grid = grid_id(push(app, "one", pa.table({"amount": [12.5], "region": ["West"]})))
    refused = post(app, "/analyze/run", {"analysis": "outliers", "table": grid})
    assert refused.status_code == 409
    assert refused.json()["error"] == "one has only 1 row: Find unusual values needs at least 5 rows."
    assert ok(post(app, "/analyze/run", {"analysis": "profile", "table": grid}))[
        "cards"
    ]  # a profile still can


def test_every_value_blank_in_a_slot_is_refused_with_why(app: TestClient) -> None:
    n = 30
    table = pa.table({"amount": pa.array([None] * n, pa.float64()), "units": [i % 7 for i in range(n)]})
    grid = grid_id(push(app, "blanks", table))
    plan = ok(post(app, "/analyze/plan", {"analysis": "outliers", "table": grid}))
    rejected = {r["name"]: r["why"] for r in plan["slots"][0]["rejected"]}
    assert rejected["amount"] == "amount is all blank" and plan["columns"] == {"column": "units"}
    refused = post(
        app, "/analyze/run", {"analysis": "outliers", "table": grid, "columns": {"column": "amount"}}
    )
    assert refused.status_code == 409 and refused.json()["error"] == "Amount is all blank."


def test_a_column_of_mixed_text_and_numbers_is_offered_as_numbers_with_its_count(app: TestClient) -> None:
    values = ["120", "95.5", "unknown", "1,300", "88", "n/a", "240", "17", "3,050", "64", "410", "29"]
    grid = grid_id(push(app, "mixed", pa.table({"amount": values})))
    plan = ok(post(app, "/analyze/plan", {"analysis": "outliers", "table": grid}))
    assert plan["columns"] == {"column": "amount"}  # as text it can still be counted: rare values
    plan = ok(post(app, "/analyze/plan", {"analysis": "benford", "table": grid}))
    assert plan["ready"] is False
    assert (
        plan["fixes"][0]["sentence"]
        == "Read amount as numbers: 10 of 12 values are numbers (2 become blank)."
    )
    ran = ok(post(app, "/analyze/run", {"analysis": "benford", "table": grid, "apply_fixes": True}))
    assert ran["result"]["results"][0]["n"] == 10


def test_dates_at_uneven_intervals_run_and_gaps_do_not_break_the_series(app: TestClient) -> None:
    days = [0, 1, 2, 40, 41, 95, 180, 181, 182, 183, 300, 420, 421, 600, 601, 602, 700, 701, 702, 703]
    table = pa.table(
        {
            "seen": [dt.date(2024, 1, 3) + dt.timedelta(days=d) for d in days],
            "amount": [float(10 + d % 9) for d in days],
        }
    )
    grid = grid_id(push(app, "visits", table))
    ran = ok(post(app, "/analyze/run", {"analysis": "time_series", "table": grid}))
    assert ran["result"]["points"] and ran["cards"]
    ahead = ok(post(app, "/analyze/run", {"analysis": "forecast", "table": grid, "options": {"horizon": 3}}))
    assert len(ahead["result"]["forecast"]) == 3


def test_a_category_with_one_value_fits_nothing_and_says_why(app: TestClient) -> None:
    n = 40
    grid = grid_id(push(app, "same", pa.table({"region": ["West"] * n, "units": [i % 6 for i in range(n)]})))
    plan = ok(post(app, "/analyze/plan", {"analysis": "fit", "table": grid}))
    rejected = {r["name"]: r["why"] for r in plan["slots"][0]["rejected"]}
    assert rejected["region"] == "region has only one value" and plan["columns"] == {"column": "units"}
    refused = post(app, "/analyze/run", {"analysis": "fit", "table": grid, "columns": {"column": "region"}})
    assert refused.status_code == 409 and refused.json()["error"] == "Region has only one value."


def test_a_connections_table_is_analysed_through_the_connection_tables_contract(tmp_path: Path) -> None:
    from tests.fake_keyring import memory_keyring
    from tests.test_connection_tables import sqlite_connection

    made = [(i, ("North", "South", "East")[i % 3], float(10 + (i * 37) % 900)) for i in range(1, 601)]
    with memory_keyring(), make_client(tmp_path) as client:
        sqlite_connection(
            client, tmp_path, "Shop", {"orders": ("order_id INTEGER, region TEXT, amount REAL", made)}
        )
        plan = ok(post(client, "/analyze/plan", {"analysis": "outliers", "table": "[Shop].orders"}))
        assert plan["dataset"] == "Shop_orders" and plan["rows"] == 600  # every row, not a first-rows cut
        assert plan["columns"] == {"column": "amount"}
        ran = ok(post(client, "/analyze/run", {"analysis": "outliers", "table": "[Shop].orders"}, AGENT))
        assert ran["dataset"] == "Shop_orders" and ran["cards"]
        assert len(ok(client.get("/grids", headers=AUTH))["grids"]) == 1  # read once, then the open table
        refused = post(
            client, "/analyze/run", {"analysis": "outliers", "table": "[Shop].orders; DROP TABLE x"}
        )
        assert refused.status_code == 400
        missing = post(client, "/analyze/plan", {"analysis": "outliers", "table": "[Shop].nothing"})
        assert missing.status_code in (400, 404) and missing.json()["error"]


def test_a_huge_connection_table_is_refused_at_the_read_limit_in_plain_words(tmp_path: Path) -> None:
    from tests.fake_keyring import memory_keyring
    from tests.test_connection_tables import sqlite_connection

    made = [(i, "North" if i % 3 else "South", 1.0) for i in range(1, 15_001)]
    with memory_keyring(), make_client(tmp_path, max_connection_query_rows=10_000) as client:
        sqlite_connection(
            client, tmp_path, "Big", {"orders": ("order_id INTEGER, region TEXT, amount REAL", made)}
        )
        started = time.monotonic()
        refused = post(client, "/analyze/run", {"analysis": "fit", "table": "[Big].orders"})
        assert time.monotonic() - started < 30 and refused.status_code == 400
        assert (
            "[Big].orders has 15,000 rows" in refused.text and "Add a WHERE that narrows it" in refused.text
        )
        assert board(client) == [] and ok(client.get("/grids", headers=AUTH))["grids"] == []


def test_a_huge_table_is_stopped_at_the_time_limit_in_plain_words_not_a_hang(tmp_path: Path) -> None:
    with make_client(tmp_path, query_timeout_seconds=0.0) as client:
        grid = grid_id(push(client, "orders", orders()))
        started = time.monotonic()
        stopped = post(client, "/analyze/run", {"analysis": "benford", "table": grid})
        assert time.monotonic() - started < 20
        assert stopped.status_code == 408
        assert stopped.json()["error"] == (
            "orders is too big to analyse in 0 seconds: it was stopped. Filter it or keep fewer "
            "columns first."
        )
        assert stopped.json()["where"] == "orders" and board(client) == []


def test_a_table_closed_while_its_form_is_open_is_said_and_the_board_keeps_its_results(
    app: TestClient, table: str
) -> None:
    ran = ok(post(app, "/analyze/run", {"analysis": "benford", "table": table}))
    assert app.delete(f"/grids/{table}", headers=AUTH).status_code == 200
    gone = post(app, "/analyze/run", {"analysis": "benford", "table": table, "columns": {"column": "amount"}})
    assert gone.status_code == 404
    assert gone.json()["error"] == f"The table '{table}' is not open any more: pick another."
    assert post(app, "/analyze/plan", {"analysis": "benford", "table": table}).status_code == 404
    assert [c["id"] for c in board(app)] == ran["cards"]  # what it found stays on the board
    assert ok(app.get(f"/analyze/runs/{ran['run']}/math", headers=AUTH))["markdown"]
    code = app.get(f"/analyze/runs/{ran['run']}/code", headers=AUTH)
    assert code.status_code == 404  # its code needs the table's steps: it says the table is closed
    toolbar = ok(app.get("/analyze", headers=AUTH))
    assert toolbar["tables"] == [] and toolbar["current"] is None
    nothing = post(app, "/analyze/plan", {"analysis": "benford"})
    assert nothing.status_code == 404 and nothing.json()["error"] == "No table is open: open one first."


def test_two_runs_at_once_both_land_whole(app: TestClient, table: str) -> None:
    results: dict[str, Any] = {}

    def go(analysis: str) -> None:
        results[analysis] = post(
            app, "/analyze/run", {"analysis": analysis, "table": table, "token": analysis}
        )

    threads = [threading.Thread(target=go, args=(a,)) for a in ("benford", "predictors", "time_series")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    ran = {a: ok(r) for a, r in results.items()}
    cards = board(app)
    assert len(cards) == sum(len(r["cards"]) for r in ran.values())
    assert len({c["order"] for c in cards}) == len(cards)  # no two cards in one place
    for r in ran.values():  # each run's cards sit together, in the order made
        ids = [c["id"] for c in cards]
        at = ids.index(r["cards"][0])
        assert ids[at : at + len(r["cards"])] == r["cards"]


def test_a_cancelled_run_lands_nothing_and_says_cancelled(app: TestClient, table: str) -> None:
    analyze = app.app.state.ctx.analyze  # type: ignore[attr-defined]
    real = analyze._compute

    async def slow(*args: Any, **kwargs: Any) -> Any:
        assert analyze.cancel("t1") == {"cancelled": True}  # the page's Cancel, while it runs
        return await real(*args, **kwargs)

    analyze._compute = slow
    try:
        stopped = post(app, "/analyze/run", {"analysis": "benford", "table": table, "token": "t1"})
    finally:
        analyze._compute = real
    assert stopped.status_code == 408
    assert stopped.json()["error"] == "Cancelled: nothing was added to the board."
    assert board(app) == [] and ok(app.get("/analyze/runs", headers=AUTH))["runs"] == []
    assert ok(post(app, "/analyze/cancel", {"token": "t1"})) == {"cancelled": False}  # it is over
    assert ok(post(app, "/analyze/run", {"analysis": "benford", "table": table, "token": "t1"}))["cards"]


def test_a_column_renamed_by_a_step_after_the_form_filled_it_is_said_and_the_form_refilled(
    app: TestClient, table: str
) -> None:
    plan = ok(post(app, "/analyze/plan", {"analysis": "benford", "table": table}))
    assert plan["columns"] == {"column": "amount"}
    step = {"kind": "rename", "params": {"mapping": {"amount": "amount_usd"}}}
    ok(post(app, f"/grids/{table}/step-ops", {"op": "add", "step": step}))
    refused = post(app, "/analyze/run", {"analysis": "benford", "table": table, "columns": plan["columns"]})
    assert refused.status_code == 409
    said = refused.json()
    assert said["error"] == (
        "amount is not a column of orders any more (a step renamed or removed it): pick again."
    )
    assert said["plan"]["gone"] == ["amount"] and said["plan"]["columns"] == {"column": "amount_usd"}
    assert ok(
        post(app, "/analyze/run", {"analysis": "benford", "table": table, "columns": said["plan"]["columns"]})
    )


def test_what_was_remembered_is_dropped_quietly_when_it_no_longer_fits(app: TestClient, table: str) -> None:
    ok(post(app, "/analyze/run", {"analysis": "benford", "table": table}))
    step = {"kind": "rename", "params": {"mapping": {"amount": "amount_usd"}}}
    ok(post(app, f"/grids/{table}/step-ops", {"op": "add", "step": step}))
    plan = ok(post(app, "/analyze/plan", {"analysis": "benford", "table": table}))
    assert plan["remembered"] is False and plan["gone"] == [] and plan["columns"] == {"column": "amount_usd"}


def test_a_table_with_a_broken_step_is_said_not_crashed(app: TestClient, table: str) -> None:
    bad = {"kind": "filter", "params": {"column": "no_such_column", "op": "eq", "value": 1}}
    app.post(f"/grids/{table}/steps", json={"steps": [bad]}, headers=AUTH)
    refused = post(app, "/analyze/plan", {"analysis": "benford", "table": table})
    assert refused.status_code == 409
    assert refused.json()["error"].startswith("A step of orders does not work, so it cannot be analysed")
