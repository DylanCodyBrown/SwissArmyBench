"""Analyze's rules (design principle 8.13): each analysis's contract, the one checker (what fits each slot
and why), the picks, the run sentence, the fixes (each kind, with its count, and the table fitting once its
steps ran) and the ranking. Made-up tables only."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pyarrow as pa
import pytest

from swissarmybench.domain import analysis_contracts as C
from swissarmybench.domain import analyze as Z
from tests.analyze_data import facts_of, orders, run_steps, sample_table

IDS = [c.id for c in C.CONTRACTS]
COLUMN_IDS = [c.id for c in C.CONTRACTS if not c.two_tables]


def plan_of(analysis: str, table: pa.Table, name: str = "orders", **kw: Any) -> Z.Plan:
    rows, facts = facts_of(table)
    return Z.plan(analysis, name, rows, facts, **kw)


def slot_of(p: Z.Plan, key: str) -> dict[str, Any]:
    return next(s for s in p.slots if s["key"] == key)


# ===== the contracts =====


def test_there_is_one_contract_for_every_analysis_on_the_toolbar() -> None:
    assert IDS == [
        "profile",
        "check",
        "benford",
        "fit",
        "together",
        "outliers",
        "odds",
        "predictors",
        "regression",
        "whatif",
        "time_series",
        "forecast",
        "tie_out",
        "key_finder",
    ]
    assert [a["id"] for a in Z.catalog()["analyses"]] == IDS
    assert {c.group for c in C.CONTRACTS} <= set(C.GROUPS)


@pytest.mark.parametrize("analysis", IDS)
def test_a_contract_is_data_in_the_one_format(analysis: str) -> None:
    j = C.contract(analysis).to_json()
    assert j["format"] == C.FORMAT == 1
    assert j["label"] and j["name"] and j["get"]
    assert j["table"]["one_row_per"] and j["table"]["rows_min"] >= 1
    assert j["output"]["cards"]
    for slot in j["slots"]:
        assert slot["words"] and slot["label"]
        assert slot["accepts"] and all(k in C.KINDS for k in slot["accepts"])
        assert slot["count"] in C.COUNTS and slot["count_words"]
        for check in slot["checks"]:
            assert check["check"] in C.CHECKS and check["level"] in ("must", "should")
            assert check["words"] and "{" not in check["words"]
    for option in j["options"]:
        assert option["meaning"] and option["type"] in ("choice", "number", "text", "table", "column")
        if option["type"] == "choice":
            assert option["default"] in [a["value"] for a in option["allowed"]]
    for fix in j["fixes"]:
        assert fix["kind"] in C.FIXES and fix["words"]


def test_every_contract_goes_to_the_agent_with_its_sample() -> None:
    everything = C.every()
    assert everything["format"] == 1 and everything["groups"] == list(C.GROUPS)
    assert [c["id"] for c in everything["contracts"]] == IDS
    assert all(c["sample"]["rows"] for c in everything["contracts"])
    assert set(everything["fixes"]) == set(C.FIXES)


@pytest.mark.parametrize("analysis", IDS)
def test_a_sample_is_the_same_every_time_and_names_its_slots(analysis: str) -> None:
    one, two = C.sample(analysis), C.sample(analysis)
    assert one == two and one["made_up"] is True
    assert all(set(row) == set(one["columns"]) for row in one["rows"])
    contract = C.contract(analysis)
    for slot in contract.slots:
        if slot.table:
            assert one["other"]["rows"]
        else:
            assert one["slots"][slot.key] and set(one["slots"][slot.key]) <= set(one["columns"])
    assert 8 <= len(one["rows"]) <= 24


@pytest.mark.parametrize("analysis", COLUMN_IDS)
def test_every_sample_passes_its_own_checker(analysis: str) -> None:
    sample = C.sample(analysis)
    rows, facts = facts_of(sample_table(sample))
    contract = C.contract(analysis)
    by_name = {f.name: f for f in facts}
    for slot in contract.slots:
        for column in sample["slots"][slot.key]:
            fit = Z.check_column(slot, by_name[column], rows)
            assert fit.fits, f"{analysis}.{slot.key}: {fit.why}"
    # ... and by itself the form picks exactly the sample's columns: the sample shows what the app does.
    p = Z.plan(analysis, sample["name"], rows, facts)
    assert p.ready, p.missing
    for slot in contract.slots:
        want = sample["slots"][slot.key]
        got = p.values[slot.key]
        if slot.count == "any":
            assert got == []
        elif slot.many:
            assert got == want
        elif slot.required:
            assert got == want[0]
    assert not [f for f in p.fixes if f.level == "needed"]
    assert Z.request(p, by_name) or analysis in ("profile", "check")


# ===== what fits each slot, and why =====


def mixed() -> pa.Table:
    """One made-up table with a column of every kind the checker tells apart."""
    n = 40
    return pa.table(
        {
            "invoice_id": [f"INV-{i}" for i in range(n)],
            "amount": [round(12.5 * (1 + i % 9) * 10 ** (i % 3), 2) for i in range(n)],
            "quantity": [1 + i % 6 for i in range(n)],
            "ordered": [dt.date(2025, 1, 1) + dt.timedelta(days=11 * i) for i in range(n)],
            "region": [("West", "East", "North")[i % 3] for i in range(n)],
            "paid": [i % 4 != 0 for i in range(n)],
            "status": [("open", "closed")[i % 2] for i in range(n)],
            "empty": pa.array([None] * n, pa.string()),
            "constant": ["same"] * n,
            "note": [f"note {i}" for i in range(n)],
        }
    )


def test_a_column_is_the_kinds_its_values_make_it() -> None:
    _, facts = facts_of(mixed())
    kinds = {f.name: Z.kinds_of(f) for f in facts}
    assert kinds["amount"] == {"number"}
    assert kinds["quantity"] == {"number", "whole"}
    assert kinds["ordered"] == {"date"}
    assert kinds["region"] == {"category"}
    assert kinds["paid"] == {"category", "yesno"}
    assert kinds["status"] == {"category", "yesno"}  # any column with exactly two values is a yes/no


def test_a_number_slot_offers_only_number_columns_and_says_why_for_the_rest() -> None:
    p = plan_of("benford", mixed(), "invoices")
    slot = slot_of(p, "column")
    assert [o["name"] for o in slot["offered"]] == ["amount", "quantity"]
    assert slot["value"] == "amount" and slot["said"] == "the likeliest, by its name"
    why = {r["name"]: r["why"] for r in slot["rejected"]}
    assert why["region"] == "region is a text column: amounts needs a number column"
    assert why["ordered"] == "ordered is a date column: amounts needs a number column"
    assert why["paid"].startswith("paid is a yes/no column")
    assert why["empty"].startswith("empty is")
    # each offered column carries its type as a word and a tiny preview of its values
    assert slot["offered"][0]["type"] == "number" and len(slot["offered"][0]["preview"]) == 3
    # quantity is offered with its caution: it does not span Benford's range
    assert any("narrow range" in c for c in slot["offered"][1]["cautions"])


def test_a_category_slot_refuses_identifiers_constants_and_blank_columns() -> None:
    p = plan_of("fit", mixed(), "invoices")
    slot = slot_of(p, "column")
    assert [o["name"] for o in slot["offered"]] == ["quantity", "region", "paid", "status"]
    assert slot["value"] == "region"  # named like a group: the likeliest
    why = {r["name"]: r["why"] for r in slot["rejected"]}
    assert why["invoice_id"] == "every row has a different invoice_id: an identifier tells nothing"
    assert why["note"] == "every row has a different note: an identifier tells nothing"
    assert why["constant"] == "constant has only one value"
    assert why["empty"] == "empty is all blank"
    assert why["amount"].startswith("amount is a number column")


def test_an_identifier_by_its_name_is_not_said_to_differ_on_every_row() -> None:
    # Test app one (BI review): customers.region_id, 8 values over 503 rows, was refused as "every row has
    # a different region_id"; its name makes it an identifier, its values repeat.
    from swissarmybench.domain.analysis_facts import Facts, failed

    named = Facts("region_id", "BIGINT", filled=503, distinct=8, identifier=True)
    said = failed(C.Check("not_identifier"), named, 503)
    assert said == "region_id is an identifier by its name: it names things, it does not measure them"
    unique = Facts("order_id", "BIGINT", filled=503, distinct=503, identifier=True)
    assert failed(C.Check("not_identifier"), unique, 503) == (
        "every row has a different order_id: an identifier tells nothing"
    )
    assert failed(C.Check("not_identifier"), Facts("amount", "DOUBLE", 503, 400), 503) is None


def test_the_only_column_that_fits_is_picked_and_said() -> None:
    p = plan_of("time_series", mixed(), "invoices")
    assert slot_of(p, "date")["value"] == "ordered"
    assert slot_of(p, "date")["said"] == "the only date column"
    assert slot_of(p, "metric")["value"] == "amount"  # optional, filled because it is named for it
    assert p.ready


def test_two_slots_never_take_the_same_column() -> None:
    p = plan_of("together", mixed(), "invoices")
    assert p.values["first"] != p.values["second"]
    p = plan_of("regression", mixed(), "invoices")
    assert p.values["target"] == "amount" and "amount" not in p.values["predictors"]
    assert p.values["predictors"] == ["quantity", "region", "paid", "status"]


def test_what_was_given_is_kept_when_it_fits_and_refused_with_the_reason_when_not() -> None:
    p = plan_of("benford", mixed(), "invoices", given={"column": "quantity"})
    assert p.values["column"] == "quantity" and slot_of(p, "column")["said"] == ""
    p = plan_of("benford", mixed(), "invoices", given={"column": "region"})
    assert p.values["column"] == "amount"  # the obvious one instead
    assert p.refused == ["region is a text column: amounts needs a number column"]
    p = plan_of("benford", mixed(), "invoices", given={"column": "amount_usd"})
    assert p.gone == ["amount_usd"] and p.values["column"] == "amount"


def test_an_optional_slot_can_be_left_empty_on_purpose() -> None:
    p = plan_of("time_series", mixed(), "invoices", given={"metric": ""})
    assert p.values["metric"] is None and p.ready
    assert "Count the rows" in Z.sentence(p)


def test_nothing_fits_is_one_sentence_and_never_a_dead_end() -> None:
    table = pa.table({"region": ["West", "East"] * 10, "city": ["A", "B", "C", "D"] * 5})
    p = plan_of("time_series", table, "places")
    assert not p.ready
    assert p.missing == "Nothing in places fits dates: it needs a date column."
    assert p.to_json()["sentence"] is None


def test_few_rows_is_a_caution_and_too_few_is_what_is_missing() -> None:
    table = pa.table({"amount": [10.0, 250.0, 3100.0, 47.0, 12.0, 1900.0]})
    p = plan_of("benford", table, "payments")
    assert p.missing == "payments has only 6 rows: Do the first digits look natural needs at least 10 rows."
    table = pa.table({"amount": [float(10 + i * 37) for i in range(40)]})
    p = plan_of("benford", table, "payments")
    assert p.ready and p.cautions == ["Only 40 rows: the result will be rough (300 is better)."]


def test_options_are_all_defaulted_and_a_wrong_value_falls_back() -> None:
    p = plan_of("outliers", mixed(), "invoices", settings={"method": "nonsense"})
    options = {o["key"]: o for o in p.options}
    assert options["method"]["value"] == "robust"
    assert [c[0] for c in options["by"]["choices"]] == ["", "quantity", "region", "paid", "status"]
    assert all(o["meaning"] for o in p.options)
    p = plan_of("forecast", mixed(), "invoices", settings={"horizon": "soon"})
    assert p.chosen["horizon"] == 6


def test_counts_as_yes_shows_only_for_a_yes_no_target_and_defaults_from_the_values() -> None:
    p = plan_of("regression", orders(), given={"target": "late"})
    assert p.chosen["yes"] == "yes"
    assert Z.request(p, {})["outcome"] == {"column": "late", "values": ["yes"]}
    p = plan_of("regression", orders())
    assert "yes" not in p.chosen and p.values["target"] == "amount"
    p = plan_of("odds", orders())
    assert p.values == {"column": "region", "outcome": "late"} and p.chosen["yes"] == "yes"


# ===== the sentence of what will run =====


def test_the_sentence_says_what_will_run_in_the_forms_words() -> None:
    table = orders()

    def said(analysis: str, **kw: Any) -> str:
        return Z.sentence(plan_of(analysis, table, **kw))

    assert said("benford") == "Test whether amount follows Benford's first-digit law, on 240 rows of orders."
    assert said("benford", settings={"digits": "2"}) == (
        "Test whether amount follows Benford's first-two-digits law, on 240 rows of orders."
    )
    assert said("fit") == "Test whether each region is equally common, on 240 rows of orders."
    assert said("together") == "Test whether region and late go together, on 240 rows of orders."
    assert said("outliers") == "Find the unusual values of amount, on 240 rows of orders."
    assert said("outliers", settings={"by": "region"}) == (
        "Find the unusual values of amount within each region, on 240 rows of orders."
    )
    assert said("odds") == "Count the odds of late = yes for each region, on 240 rows of orders."
    assert (
        said("odds", given={"outcome": ""}) == "Count how often each region shows up, on 240 rows of orders."
    )
    assert said("predictors") == "Rank what explains late among every other column, on 240 rows of orders."
    assert said("regression") == "Predict amount from region, units, late, on 240 rows of orders."
    assert said("time_series") == (
        "Total amount by order_date and spot the trend and seasons, on 240 rows of orders."
    )
    assert said("forecast") == "Forecast amount 6 periods ahead by order_date, on 240 rows of orders."
    assert said("profile") == "Describe every column of orders (240 rows)."
    one = pa.table({"region": ["West"]})
    assert Z.sentence(plan_of("profile", one)) == "Describe every column of orders (1 row)."


def test_two_table_analyses_pick_the_other_table() -> None:
    rows, facts = facts_of(orders())
    others = [{"grid": "g2", "label": "ledger"}, {"grid": "g3", "label": "customers"}]
    p = Z.plan("tie_out", "orders", rows, facts, tables=others[:1])
    assert p.values == {"other": "g2"} and slot_of(p, "other")["said"] == "the only other open table"
    assert Z.request(p, {}) == {"other": "g2"}
    p = Z.plan("tie_out", "orders", rows, facts, given={"other": "g3"}, tables=others)
    assert p.values == {"other": "g3"}
    p = Z.plan("tie_out", "orders", rows, facts)
    assert p.missing == "Do two tables add up the same needs a second open table."
    p = Z.plan("key_finder", "orders", rows, facts)
    assert p.ready and Z.request(p, {})["target"] == "*"


# ===== the request each analysis's route takes =====


def test_the_request_is_the_body_the_analysis_takes() -> None:
    table = orders()
    rows, facts = facts_of(table)
    by_name = {f.name: f for f in facts}

    def body(analysis: str, **kw: Any) -> dict[str, Any]:
        return Z.request(Z.plan(analysis, "orders", rows, facts, **kw), by_name)

    assert body("benford") == {"columns": ["amount"], "expected": "benford"}
    assert body("fit") == {"columns": ["region"], "expected": "even"}
    assert body("together") == {"columns": ["region", "late"], "expected": "together"}
    assert body("outliers") == {"column": "amount", "look": "amount", "method": "robust"}
    assert body("outliers", given={"column": "region"}) == {"column": "region", "look": "frequency"}
    assert body("odds") == {"column": "region", "outcome": {"column": "late", "values": ["yes"]}}
    assert body("predictors") == {"target": "late"}
    assert body("regression") == {"target": "amount", "predictors": ["region", "units", "late"]}
    assert body("time_series") == {
        "date": "order_date",
        "period": "month",
        "total": "sum",
        "metric": "amount",
    }
    assert body("forecast", settings={"horizon": 3})["horizon"] == 3
    assert body("time_series", given={"metric": ""}) == {
        "date": "order_date",
        "period": "month",
        "total": "count",
    }
    with pytest.raises(Z.AnalyzeError, match="needs a second open table"):
        body("tie_out")


def test_an_unknown_analysis_is_refused_with_the_ones_there_are() -> None:
    with pytest.raises(Z.AnalyzeError, match="No analysis 'astrology': one of profile, check, benford"):
        Z.plan("astrology", "orders", 0, [])


# ===== the column-first ways in =====


def test_what_can_i_do_with_a_column_shows_only_what_fits() -> None:
    rows, facts = facts_of(orders())

    def offered(column: str) -> list[str]:
        return [o["analysis"] for o in Z.for_column(column, rows, facts)]

    assert offered("amount") == ["benford", "outliers", "odds", "predictors", "regression"]
    assert offered("order_date") == ["time_series", "forecast"]
    assert offered("region") == ["fit", "together", "outliers", "odds", "predictors"]
    assert offered("late") == ["fit", "together", "outliers", "odds", "predictors", "regression"]
    assert offered("order_id") == []
    assert Z.for_column("amount", rows, facts)[0]["columns"] == {"column": "amount"}
    with pytest.raises(Z.AnalyzeError, match="No column 'nope'"):
        Z.for_column("nope", rows, facts)


# ===== make it fit: each fix, its count, and the table fitting afterwards =====


def needed(p: Z.Plan) -> list[Z.Fix]:
    return [f for f in p.fixes if f.level == "needed"]


def after(table: pa.Table, fix: Z.Fix, analysis: str) -> Z.Plan:
    """The plan once the fix's steps ran on the table, the fix's column given to its slot."""
    fixed = run_steps(table, [dict(s) for s in fix.steps])
    rows, facts = facts_of(fixed)
    return Z.plan(analysis, "t", rows, facts, given={fix.slot: fix.fills} if fix.slot else None)


def test_fix_text_to_number() -> None:
    amounts = [
        "1,240.50",
        "$12",
        " 310 ",
        "4520",
        "17.2",
        "n/a",
        "1210",
        "260.3",
        "31.9",
        "11,050",
        "1.95",
        "",
    ]
    table = pa.table({"invoice": [f"I{i}" for i in range(12)], "amount": amounts})
    p = plan_of("benford", table, "invoices")
    assert p.missing == "Nothing in invoices fits amounts: it needs a number column: the amounts to test."
    (fix,) = needed(p)
    assert (fix.kind, fix.column, fix.count) == ("text_to_number", "amount", 10)
    assert fix.label == "Read amount as numbers"
    assert fix.sentence == "Read amount as numbers: 10 of 12 values are numbers (2 become blank)."
    assert fix.to_json()["fills"] == {"column": "amount"}
    fixed = after(table, fix, "benford")
    assert fixed.ready and fixed.values["column"] == "amount" and not needed(fixed)
    assert run_steps(table, [dict(s) for s in fix.steps])["amount"].to_pylist()[:3] == [1240.5, 12.0, 310.0]


def test_text_that_is_mostly_words_is_not_offered_as_numbers() -> None:
    table = pa.table({"code": ["A1", "B2", "C3", "7", "D4", "E5", "F6", "G7", "H8", "I9", "J1", "K2"]})
    assert plan_of("benford", table).fixes == []


@pytest.mark.parametrize(
    ("values", "style", "words"),
    [
        (
            ["2025-01-05", "2025-02-11", "2025-03-19", "2025-04-02", "soon", "2025-06-30"],
            "iso",
            "year-month-day",
        ),
        (["1/25/2025", "2/11/2025", "3/19/2025", "4/2/2025", "soon", "6/30/2025"], "mdy", "month/day/year"),
        (["25/1/2025", "11/2/2025", "19/3/2025", "2/4/2025", "soon", "30/6/2025"], "dmy", "day/month/year"),
    ],
)
def test_fix_text_to_date(values: list[str], style: str, words: str) -> None:
    table = pa.table({"when": values, "amount": [10.0, 12.0, 9.0, 14.0, 11.0, 13.0]})
    p = plan_of("time_series", table, "sales")
    assert p.missing == "Nothing in sales fits dates: it needs a date column."
    (fix,) = needed(p)
    assert (fix.kind, fix.variant, fix.count) == ("text_to_date", style, 5)
    assert fix.sentence == f"Read when as dates ({words}): 5 of 6 values are dates (1 become blank)."
    fixed = after(table, fix, "time_series")
    assert fixed.ready and fixed.values == {"date": "when", "metric": "amount"}
    assert run_steps(table, [dict(s) for s in fix.steps])["when"].to_pylist()[0] == dt.date(
        2025, 1, 5 if style == "iso" else 25
    )


def test_dates_that_read_both_ways_are_never_guessed_both_are_offered() -> None:
    table = pa.table({"when": ["1/2/2025", "3/4/2025", "5/6/2025", "7/8/2025", "9/10/2025"]})
    fixes = needed(plan_of("time_series", table))
    assert [f.variant for f in fixes] == ["mdy", "dmy"]
    assert "month/day/year" in fixes[0].sentence and "day/month/year" in fixes[1].sentence


def test_fix_group_by_a_period_makes_a_date_a_category() -> None:
    n = 60
    table = pa.table({"ordered": [dt.date(2025, 1, 1) + dt.timedelta(days=5 * i) for i in range(n)]})
    p = plan_of("fit", table, "orders")
    assert not p.ready
    (fix,) = needed(p)
    assert (fix.kind, fix.count, fix.fills) == ("period_column", 10, "ordered_month")
    assert fix.sentence == "Group ordered by month into ordered_month: 10 months."
    fixed = after(table, fix, "fit")
    assert fixed.ready and fixed.values["column"] == "ordered_month"
    made = run_steps(table, [dict(s) for s in fix.steps])
    assert made.column_names == ["ordered", "ordered_month"]  # the dates stay: a column is added
    assert made["ordered_month"].to_pylist()[0] == "2025-01"


def test_fix_top_n_plus_other() -> None:
    n = 900
    table = pa.table({"city": [f"city {i % 250 if i % 3 else i % 4}" for i in range(n)]})
    p = plan_of("fit", table, "visits")
    assert slot_of(p, "column")["rejected"][0]["why"] == "city has 250 different values (at most 200)"
    (fix,) = needed(p)
    assert (fix.kind, fix.fills) == ("top_n_other", "city_top")
    assert fix.count is None and fix.count_sql is not None and "{n}" in fix.sentence  # counted on the table
    made = run_steps(table, [dict(s) for s in fix.steps])
    counts: dict[str, int] = {}
    for value in made["city_top"].to_pylist():
        counts[value] = counts.get(value, 0) + 1
    assert len(counts) == 11 and "Other" in counts
    kept = n - counts["Other"]
    said = fix.counted(kept)
    assert said.sentence == (
        f"Keep the 10 most common city in city_top and call the rest Other: they cover {kept:,} of 900 rows."
    )
    fixed = after(table, fix, "fit")
    assert fixed.ready and fixed.values["column"] == "city_top"


def test_fix_drop_blanks_is_a_suggestion_for_a_picked_column() -> None:
    n = 50
    table = pa.table(
        {
            "region": [("West", "East", "North")[i % 3] if i % 3 != 2 else None for i in range(n)],
            "units": [i % 7 for i in range(n)],
        }
    )
    p = plan_of("fit", table, "orders")
    assert p.ready and p.values["column"] == "region"
    assert slot_of(p, "column")["cautions"] == ["32% of region is blank (left out)"]
    (fix,) = p.fixes
    assert (fix.kind, fix.level, fix.count) == ("drop_blanks", "better", 16)
    assert fix.sentence == "Leave out the 16 rows with no region."
    assert fix.steps == ({"kind": "filter", "params": {"column": "region", "op": "not_blank"}},)
    fixed = after(table, fix, "fit")
    assert fixed.rows == 34 and fixed.fixes == [] and slot_of(fixed, "column")["cautions"] == []


def test_fix_keep_positive_values() -> None:
    amounts = [round(10 ** (1 + (i * 37 % 300) / 100), 2) if i % 10 else -5.0 for i in range(60)]
    table = pa.table({"amount": amounts})
    p = plan_of("benford", table, "payments")
    assert p.ready
    assert "6 of amount's values are zero or negative (left out)" in slot_of(p, "column")["cautions"]
    fix = next(f for f in p.fixes if f.kind == "keep_positive")
    assert (fix.level, fix.count) == ("better", 6)
    assert fix.sentence == "Keep amount above zero: leaves out 6 rows at or below it."
    fixed = after(table, fix, "benford")
    assert fixed.rows == 54 and not [f for f in fixed.fixes if f.kind == "keep_positive"]


def test_fix_yes_no_from_y_n_and_1_0_in_any_spelling() -> None:
    late = ["Y", "n", "yes", "No", "1", "0", "Y", "N", "y", "no", "Y", "N"]
    table = pa.table({"region": ["West", "East", "North"] * 4, "late": late})
    p = plan_of("odds", table, "orders")
    assert p.values == {"column": "region", "outcome": None}  # six spellings: not a yes/no column yet
    fix = next(f for f in p.fixes if f.kind == "yes_no")
    assert (fix.variant, fix.level, fix.count, fix.fills) == ("words", "better", 6, "late_yes_no")
    assert (
        fix.sentence
        == "Make late_yes_no from late: Y, 1, y, yes count as yes (6 rows), N, 0, No, n, no as no."
    )
    made = run_steps(table, [dict(s) for s in fix.steps])
    assert made["late_yes_no"].to_pylist() == ["yes", "no"] * 6
    fixed = after(table, fix, "odds")
    assert fixed.values["outcome"] == "late_yes_no" and fixed.chosen["yes"] == "yes"


def test_fix_yes_no_from_one_value_of_a_text_column() -> None:
    status = ["late", "on time", "early", "on time", "late", "on time", "early", "on time"] * 3
    table = pa.table({"order": [f"O{i}" for i in range(24)], "status": status})
    slot = C.Slot("outcome", "Outcome", "a yes/no column", ("yesno",), checks=(C.Check("two_values"),))
    _, facts = facts_of(table)
    fix = Z.fix_yes_no_value(next(f for f in facts if f.name == "status"), {"order", "status"}, "outcome")
    assert fix is not None
    assert (fix.kind, fix.variant, fix.count, fix.fills) == ("yes_no", "value", 6, "is_late")
    assert fix.sentence == "Make is_late from status: late is yes (6 of 24 rows), every other value no."
    made = run_steps(table, [dict(s) for s in fix.steps])
    assert made["is_late"].to_pylist()[:4] == ["yes", "no", "no", "no"]
    rows, after_facts = facts_of(made)
    assert Z.check_column(slot, next(f for f in after_facts if f.name == "is_late"), rows).fits


def test_fix_group_by_a_period_and_by_a_key_are_the_outliers_contracts_own() -> None:
    n = 240
    table = pa.table(
        {
            "ordered": [dt.date(2024, 1, 1) + dt.timedelta(days=3 * i) for i in range(n)],
            "customer_id": [f"C{i % 30}" for i in range(n)],
            "amount": [100.0 + (i * 37) % 90 for i in range(n)],
        }
    )
    p = plan_of("outliers", table, "orders")
    assert p.ready and p.values["column"] == "amount"
    by_kind = {f.kind: f for f in p.fixes}
    period, key = by_kind["group_by_period"], by_kind["group_by_key"]
    assert period.level == key.level == "better"
    assert period.sentence == "Total amount by month of ordered: 24 rows, one per month."
    assert key.sentence == "Total amount per customer_id: 30 rows, one per customer_id."
    monthly = run_steps(table, [dict(s) for s in period.steps])
    assert monthly.num_rows == 24 and monthly.column_names == ["ordered_month", "amount"]
    per_customer = run_steps(table, [dict(s) for s in key.steps])
    assert per_customer.num_rows == 30 and per_customer.column_names == ["customer_id", "amount"]
    assert after(table, period, "outliers").ready and after(table, key, "outliers").ready


def test_a_fix_never_takes_a_name_the_table_has() -> None:
    n = 60
    table = pa.table(
        {
            "ordered": [dt.date(2025, 1, 1) + dt.timedelta(days=5 * i) for i in range(n)],
            "Ordered_Month": [f"x{i}" for i in range(n)],
        }
    )
    (fix,) = needed(plan_of("fit", table))
    assert fix.fills == "ordered_month_2"


@pytest.mark.parametrize("kind", list(C.FIXES))
def test_every_fix_kind_has_a_test_above(kind: str) -> None:
    import inspect
    import sys

    source = inspect.getsource(sys.modules[__name__])
    assert f'"{kind}"' in source


# ===== Check this table: the ranking =====


def test_the_ranking_puts_what_fits_now_first_with_a_reason() -> None:
    rows, facts = facts_of(orders())
    ranked = Z.rank("orders", rows, facts)
    assert {e["analysis"] for e in ranked} == set(IDS) - {"profile", "check"}
    top = Z.top_three(ranked)
    assert [e["analysis"] for e in top] == ["time_series", "forecast", "predictors"]
    assert top[0]["status"] == "now" and top[0]["button"] == "Run"
    assert top[0]["reason"] == "order_date covers 24 months: enough to show a season"
    assert top[2]["reason"] == "late is a yes/no column and 5 columns might explain it"
    assert top[0]["columns"] == {"date": "order_date", "metric": "amount"}
    scores = [e["score"] for e in ranked]
    assert scores == sorted(scores, reverse=True)
    no = [e for e in ranked if e["status"] == "no"]
    assert {e["analysis"] for e in no} == {"tie_out"}  # no second table open
    assert no[0]["reason"] == "Do two tables add up the same needs a second open table."


def test_the_ranking_says_fits_after_its_fixes_and_names_them_on_the_button() -> None:
    n = 120
    table = pa.table(
        {
            "when": [(dt.date(2023, 1, 1) + dt.timedelta(days=7 * i)).isoformat() for i in range(n)],
            "amount": [f"{100 + (i * 37) % 900}" for i in range(n)],
        }
    )
    rows, facts = facts_of(table)
    ranked = {e["analysis"]: e for e in Z.rank("sales", rows, facts)}
    series = ranked["time_series"]
    assert series["status"] == "fixes"
    assert [f["kind"] for f in series["fixes"]] == ["text_to_date"]
    assert series["button"] == "Read when as dates and run"
    assert series["reason"] == "when holds dates: a trend and seasons can show"
    assert ranked["benford"]["status"] == "fixes"
    assert ranked["benford"]["button"] == "Read amount as numbers and run"
    assert ranked["regression"]["status"] == "no"
    top = Z.top_three(list(ranked.values()))
    assert all(e["status"] != "no" for e in top)


def test_a_table_with_nothing_to_analyse_ranks_nothing() -> None:
    rows, facts = facts_of(pa.table({"id": [f"k{i}" for i in range(30)]}))
    ranked = Z.rank("keys", rows, facts)
    assert Z.top_three(ranked) == [e for e in ranked if e["analysis"] == "key_finder"]


def test_the_shape_notes_say_what_stands_in_the_way() -> None:
    n = 40
    table = pa.table(
        {
            "id": [f"k{i}" for i in range(n)],
            "amount": [f"{(i * 3) % 60}" for i in range(n)],
            "when": [f"2025-01-{1 + i % 28:02d}" for i in range(n)],
            "note": pa.array([None] * n, pa.string()),
            "jan_sales": [1.0] * n,
            "feb_sales": [2.0] * n,
            "mar_sales": [3.0] * n,
        }
    )
    rows, facts = facts_of(table)
    notes = Z.table_notes("wide", rows, facts)
    texts = [n["text"] for n in notes]
    assert any(t.startswith("This table looks wide: 3 number columns") for t in texts)
    assert "40 rows, 7 columns." in texts
    assert "amount is text that reads as numbers (40 of 40 values)." in texts
    assert "when is text that reads as dates (40 of 40 values)." in texts
    assert "note is all blank." in texts
    assert "Identifiers (never analysed): id." in texts
    assert Z.table_notes("none", 0, [])[0] == {"level": "warn", "text": "none has no rows."}


def test_a_year_or_an_identifier_reads_without_separators() -> None:
    # The profile's Lowest and Highest: 2018, never 2,018; an amount keeps its commas.
    from swissarmybench.domain import analysis_cards as K

    assert (
        K.is_label_column("order_year") and K.is_label_column("CustomerKey") and K.is_label_column("cust_id")
    )
    assert K.is_label_column("made", 2015, 2024) and not K.is_label_column("amount", 15, 20240)
    assert not K.is_label_column("amount") and not K.is_label_column("idle_minutes", 0, 90000)
    body = K.profile_cards(
        {
            "rows": 3,
            "duplicate_rows": 0,
            "columns": [
                {
                    "column": "year",
                    "type": "BIGINT",
                    "blanks": 0,
                    "blank_percent": 0,
                    "distinct": 3,
                    "min": 2018,
                    "max": 2024,
                },
                {
                    "column": "amount",
                    "type": "BIGINT",
                    "blanks": 0,
                    "blank_percent": 0,
                    "distinct": 3,
                    "min": 1500,
                    "max": 25000,
                },
            ],
        },
        "orders",
    )[0]["body"]
    assert "| 2018 | 2024 |" in body and "2,018" not in body and "| 1,500 | 25,000 |" in body
