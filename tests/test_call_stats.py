"""The statistics' rules (domain/call_stats.py; Plans/stats.plan.md): each call's record from the adapter's
facts, a finished slot ticket and api_adapter's envelope; the running figures per table and endpoint; the
hints in plain words; the agent's views; .sab/stats.json byte-stable. Never a value. Made-up data only."""

from __future__ import annotations

import json
from typing import Any

import pytest

from swissarmybench.domain import call_stats as rules


def _adapter_facts(**more: Any) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "call": "read",
        "source": "Warehouse",
        "kind": "Sql",
        "table": "orders",
        "mode": "",
        "ms": {"connect": 12.0, "first_row": 40.0, "total": 220.0},
        "size": {"rows": 1000, "bytes": 64000, "batches": 1, "columns": 4, "asked": 4},
        "folded": ["filters", "columns"],
        "by_duckdb": [],
        "outcome": {"ok": True, "error": ""},
        "fingerprint": "abc123abc123",
    }
    for key, value in more.items():
        if isinstance(value, dict) and isinstance(facts.get(key), dict):
            facts[key] = facts[key] | value
        else:
            facts[key] = value
    return facts


def _ticket(**more: Any) -> dict[str, Any]:
    done = {
        "id": "t1",
        "connection": "Warehouse",
        "caller": "user",
        "who": "Notebook sales.ipynb",
        "kind": "read",
        "targets": ["orders"],
        "outcome": "ok",
        "reason": "Login failed for user 'sam'",
        "ended_at": 1000.0,
        "seconds": 0.8,
        "waited": 1.5,
        "source": {"document": "/p/sales.ipynb", "cell": 3},
        "rows": 1000,
    }
    return done | more


def test_a_slot_ticket_and_its_childs_facts_are_one_record() -> None:
    made = rules.from_ticket(_ticket(), [_adapter_facts()], at="2026-11-22T10:00:00")
    assert made["object"] == {"kind": "table", "name": "Warehouse.orders"}
    assert made["ms"]["wait"] == 1500.0 and made["ms"]["total"] == 800.0
    assert made["ms"]["connect"] == 12.0 and made["ms"]["first"] == 40.0
    assert made["size"]["rows"] == 1000 and made["size"]["bytes"] == 64000
    assert made["folded"] == ["filters", "columns"]
    assert made["who"] == "user" and made["where"] == {"notebook": "sales.ipynb", "cell": 3}
    assert "sam" not in json.dumps(made)  # a failure's words never come along


def test_a_failed_ticket_says_its_kind_not_its_words() -> None:
    made = rules.from_ticket(_ticket(outcome="failed"), [], at="t")
    assert made["outcome"]["ok"] is False and made["outcome"]["error"] == "failed"
    assert "Login" not in json.dumps(made)


def test_an_api_envelope_is_an_endpoint_record() -> None:
    facts = {
        "api": "Shop",
        "action": "list_orders",
        "who": "agent",
        "ms": {"wait": 0.0, "first_byte": 30.0, "total": 410.0},
        "size": {"records": 120, "bytes": 9000, "pages": 12, "columns": 6},
        "outcome": {"status": 200, "ok": True, "retries": 1, "error": ""},
    }
    made = rules.from_api(facts, "fp00fp00fp00", {"widget": "orders_table", "page": "Overview"}, at="t")
    assert made["object"] == {"kind": "endpoint", "name": "Shop list_orders"}
    assert (
        made["size"]["pages"] == 12 and made["outcome"]["retries"] == 1 and made["outcome"]["status"] == 200
    )
    assert made["where"] == {"widget": "orders_table", "page": "Overview"} and made["who"] == "agent"


def test_running_figures_are_percentiles_and_typical_sizes() -> None:
    figures: dict[str, Any] = {}
    for ms in range(1, 101):
        call = rules.from_adapter(
            _adapter_facts(ms={"total": float(ms)}), {}, "user", at=f"2026-11-22T10:{ms % 60:02d}"
        )
        rules.fold(figures, call)
    failed = rules.from_adapter(
        _adapter_facts(outcome={"ok": False, "error": "OperationalError"}), {}, "user", "z"
    )
    rules.fold(figures, failed)
    one = rules.figure(figures["table:Warehouse.orders"])
    assert one["count"] == 101 and one["errors"] == 1
    assert one["p50"] == pytest.approx(51, abs=2) and one["p95"] == pytest.approx(96, abs=2)
    assert one["rows"] == 1000 and one["last"] == "z"
    assert round(one["error_rate"], 3) == round(1 / 101, 3)


def test_the_kept_file_is_byte_stable_and_holds_no_value() -> None:
    figures: dict[str, Any] = {}
    for at in ("a", "b"):
        rules.fold(figures, rules.from_adapter(_adapter_facts(), {}, "user", at=at))
    text = rules.text(figures)
    assert text == rules.text(rules.read(text))
    assert text.endswith("\n") and json.loads(text)["format"] == rules.FORMAT
    assert rules.read("not json") == {} and rules.read('{"format": 99, "figures": {}}') == {}


def test_hints_in_plain_words() -> None:
    calls = [
        rules.from_adapter(
            _adapter_facts(
                size={"rows": 3_200_000, "columns": 40, "asked": 0}, folded=[], by_duckdb=["filters"]
            ),
            {"widget": "sales_chart", "page": "Overview"},
            "user",
            at="t",
        )
    ]
    paged = {
        "api": "Shop",
        "action": "list_orders",
        "who": "user",
        "ms": {"wait": 0, "first_byte": 1, "total": 9000},
        "size": {"records": 4000, "bytes": 1, "pages": 40, "columns": 3},
        "outcome": {"status": 200, "ok": True, "retries": 0, "error": ""},
    }
    calls.append(rules.from_api(paged, "fp", {}, at="t"))
    calls += [rules.from_adapter(_adapter_facts(), {}, "user", at=str(i)) for i in range(6)]
    said = {h["kind"]: h for h in rules.hints(calls)}
    assert "3,200,000 rows" in said["filter_at_source"]["words"]
    assert "sales_chart" in said["filter_at_source"]["words"]
    assert "40 pages" in said["larger_pages"]["words"]
    assert said["keep_as_table"]["object"] == {"kind": "table", "name": "Warehouse.orders"}


def test_the_agents_views() -> None:
    calls = [
        rules.from_adapter(_adapter_facts(ms={"total": float(ms)}, table=f"t{ms}"), {}, "user", at="t")
        for ms in (5, 500, 50)
    ]
    calls.append(rules.from_adapter(_adapter_facts(outcome={"ok": False, "error": "Boom"}), {}, "agent", "t"))
    figures: dict[str, Any] = {}
    for call in calls:
        rules.fold(figures, call)
    assert [c["ms"]["total"] for c in rules.view(calls, figures, "slowest", n=2)["calls"]] == [500.0, 220.0]
    assert len(rules.view(calls, figures, "errors")["calls"]) == 1
    by = rules.view(calls, figures, "table", name="Warehouse.t5")
    assert by["figures"]["count"] == 1 and len(by["calls"]) == 1
    summary = rules.view(calls, figures, "summary")
    assert summary["calls"] == 4 and summary["errors"] == 1
    with pytest.raises(rules.StatsError):
        rules.view(calls, figures, "everything")
