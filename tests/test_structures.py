"""Structures' rules (domain/structures.py): formats, paths, steps, records, shapes. Made-up data only: a
gates file, a field mapping and an orders payload."""

from __future__ import annotations

import tomllib
from typing import Any

import pytest

from swissarmybench.domain import structures as rules
from swissarmybench.domain.structures import StructureError, check_step

GATES: dict[str, Any] = {
    "gates": [
        {"name": "release", "enabled": True, "rollout": 50, "owners": ["ana", "bo"]},
        {"name": "beta", "enabled": False, "rollout": 5, "owners": []},
        {"name": "dark mode", "enabled": True, "rollout": 100, "owners": ["cy"]},
    ],
    "version": 3,
}
MAPPING: dict[str, Any] = {"fields": {"cust_id": "customer_id", "amt": "amount", "dt": "order_date"}}
ORDERS: dict[str, Any] = {
    "orders": [
        {"id": 1, "status": "open", "total": 120.5, "customer": {"name": "Acme Ltd", "region": "North"},
         "lines": [{"sku": "A-1", "qty": 2}]},
        {"id": 2, "status": "shipped", "total": 40, "customer": {"name": "Birch Co", "region": "South"},
         "lines": []},
        {"id": 3, "status": "open", "total": 999, "customer": {"name": "Cedar Inc", "region": "North"},
         "lines": [{"sku": "B-2", "qty": 1}, {"sku": "C-3", "qty": 4}]},
    ],
    "next": None,
}  # fmt: skip


def run(value: Any, *steps: dict[str, Any]) -> Any:
    return rules.apply(value, [check_step(s) for s in steps])


# ===== paths =====


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ("$", ()),
        ("", ()),
        ("$.orders[3].lines", ("orders", 3, "lines")),
        ('$["unit price"][0]', ("unit price", 0)),
        ("$.orders[*].customer", ("orders", None, "customer")),
        ("orders.lines", ("orders", "lines")),
        ("$.a-b", ("a-b",)),
        ("$[-1]", (-1,)),
    ],
)
def test_a_path_reads_into_its_parts_and_back(text: str, parts: tuple[Any, ...]) -> None:
    assert rules.parse_path(text) == parts
    assert rules.parse_path(rules.format_path(parts)) == parts


def test_an_odd_key_is_written_quoted() -> None:
    assert rules.format_path(("orders", 3, "unit price")) == '$.orders[3]["unit price"]'


@pytest.mark.parametrize("bad", ["$.", "$[x]", "$[1", '$["a]', "$#"])
def test_a_path_that_cannot_be_read_says_so(bad: str) -> None:
    with pytest.raises(StructureError):
        rules.parse_path(bad)


def test_a_wildcard_resolves_to_every_item_with_its_own_path() -> None:
    found = rules.resolve(ORDERS, rules.parse_path("$.orders[*].customer.region"))
    assert [(rules.format_path(w), v) for w, v in found] == [
        ("$.orders[0].customer.region", "North"),
        ("$.orders[1].customer.region", "South"),
        ("$.orders[2].customer.region", "North"),
    ]
    assert rules.get(ORDERS, "$.orders[-1].id") == 3
    with pytest.raises(StructureError, match="not there"):
        rules.get(ORDERS, "$.orders[9]")


# ===== steps =====


def test_pick_makes_the_branch_the_structure_and_leaves_the_original() -> None:
    assert run(ORDERS, {"op": "pick", "path": "$.orders[0].lines"}) == [{"sku": "A-1", "qty": 2}]
    assert ORDERS["orders"][0]["lines"] == [{"sku": "A-1", "qty": 2}]


def test_filter_keeps_the_items_whose_field_passes() -> None:
    kept = run(ORDERS, {"op": "filter", "path": "$.orders", "field": "status", "test": "=", "value": "open"})
    assert [o["id"] for o in kept["orders"]] == [1, 3]
    big = run(ORDERS, {"op": "filter", "path": "$.orders", "field": "total", "test": ">", "value": "100"})
    assert [o["id"] for o in big["orders"]] == [1, 3]  # typed as text, compared as numbers
    north = run(ORDERS, {"op": "filter", "path": "orders", "field": "customer.region", "value": "North"})
    assert [o["id"] for o in north["orders"]] == [1, 3]
    on = run(GATES, {"op": "filter", "path": "$.gates", "field": "enabled", "value": "true"})
    assert [g["name"] for g in on["gates"]] == ["release", "dark mode"]
    owned = run(
        GATES, {"op": "filter", "path": "$.gates", "field": "owners", "test": "contains", "value": "cy"}
    )
    assert [g["name"] for g in owned["gates"]] == ["dark mode"]
    some = run(
        ORDERS, {"op": "filter", "path": "$.orders[*].lines", "field": "qty", "test": ">=", "value": 2}
    )
    assert [len(o["lines"]) for o in some["orders"]] == [1, 0, 1]


def test_rename_remove_set_and_add() -> None:
    renamed = run(ORDERS, {"op": "rename", "path": "$.orders[*].customer", "key": "region", "to": "area"})
    assert renamed["orders"][1]["customer"] == {"name": "Birch Co", "area": "South"}
    assert list(renamed["orders"][0]["customer"]) == ["name", "area"]  # the key keeps its place
    removed = run(ORDERS, {"op": "remove", "path": "$.orders[*].lines"}, {"op": "remove", "path": "$.next"})
    assert "lines" not in removed["orders"][0] and "next" not in removed
    two = run(ORDERS, {"op": "remove", "path": "$.orders[*]"})
    assert two["orders"] == []
    mapped = run(MAPPING, {"op": "set", "path": "$.fields.amt", "value": "amount_usd"})
    assert mapped["fields"]["amt"] == "amount_usd"
    new_key = run(MAPPING, {"op": "set", "path": "$.fields.qty", "value": "quantity"})
    assert new_key["fields"]["qty"] == "quantity"
    added = run(GATES, {"op": "add", "path": "$.gates[*]", "key": "team", "value": "core"})
    assert {g["team"] for g in added["gates"]} == {"core"}
    with pytest.raises(StructureError, match=r"Step 1 .*has team already"):
        run(added, {"op": "add", "path": "$.gates[0]", "key": "team", "value": "x"})
    with pytest.raises(StructureError, match="no key"):
        run(MAPPING, {"op": "rename", "path": "$.fields", "key": "nope", "to": "x"})


def test_sort_and_flatten() -> None:
    by_total = run(ORDERS, {"op": "sort", "path": "$.orders", "field": "total", "descending": True})
    assert [o["id"] for o in by_total["orders"]] == [3, 1, 2]
    by_name = run(GATES, {"op": "sort", "path": "$.gates", "field": "name"})
    assert [g["name"] for g in by_name["gates"]] == ["beta", "dark mode", "release"]
    flat = run(ORDERS, {"op": "flatten", "path": "$.orders"})
    assert flat["orders"][0]["customer.region"] == "North" and "customer" not in flat["orders"][0]
    assert flat["orders"][0]["lines"] == [{"sku": "A-1", "qty": 2}]  # a list stays a list


def test_a_step_that_cannot_apply_says_which_and_why() -> None:
    with pytest.raises(StructureError, match=r"Step 2 \(Keep \$.version where"):
        run(
            GATES,
            {"op": "pick", "path": "$"},
            {"op": "filter", "path": "$.version", "field": "x", "value": 1},
        )
    for bad in (
        {"op": "zap"},
        {"op": "rename", "path": "$", "key": "a"},
        {"op": "remove", "path": "$"},
        {"op": "set"},
    ):
        with pytest.raises(StructureError):
            check_step(bad)


def test_each_step_in_plain_words() -> None:
    words = [
        rules.describe(check_step(s))
        for s in (
            {"op": "pick", "path": "orders"},
            {"op": "filter", "path": "$.orders", "field": "status", "value": "open"},
            {"op": "rename", "path": "$.fields", "key": "amt", "to": "amount"},
            {"op": "sort", "path": "$.orders", "field": "total", "descending": True},
            {"op": "flatten", "path": "$.orders"},
        )
    ]
    assert words == [
        "Pick $.orders",
        "Keep $.orders where status = open",
        "Rename amt to amount in $.fields",
        "Sort $.orders by total, largest first",
        "Flatten $.orders",
    ]


# ===== formats =====


@pytest.mark.parametrize(
    ("text", "fmt"),
    [('{"a": 1}', "json"), ("[1, 2]", "json"), ("<a/>", "xml"), ("[server]\nport = 1", "toml"),
     ("title = 'x'", "toml"), ("a: 1\nb: [1]", "yaml"), ("- a\n- b", "yaml"), ('{"a": ', "json")],
)  # fmt: skip
def test_a_pasted_texts_format_is_detected(text: str, fmt: str) -> None:
    assert rules.detect(text) == fmt


def test_json_errors_say_the_line() -> None:
    with pytest.raises(StructureError, match="line 2"):
        rules.parse('{\n  "a": }', "json")


def test_xml_reads_into_a_structure_and_round_trips() -> None:
    text = (
        '<gates version="3"><gate name="release"><rollout>50</rollout><owner>ana</owner><owner>bo</owner>'
        '</gate><gate name="beta"><rollout>5</rollout></gate><note>made up</note></gates>'
    )
    value = rules.parse(text, "xml")
    assert value == {
        "gates": {
            "@version": "3",
            "gate": [
                {"@name": "release", "rollout": "50", "owner": ["ana", "bo"]},
                {"@name": "beta", "rollout": "5"},
            ],
            "note": "made up",
        }
    }
    assert rules.parse(rules.dump(value, "xml"), "xml") == value


@pytest.mark.parametrize(
    "text",
    [
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><lolz>&lol;</lolz>',
        '<!doctype x SYSTEM "file:///etc/hostname"><x/>',
        "<x><!ENTITY y 'z'></x>",
    ],
)
def test_xml_with_a_doctype_or_an_entity_is_refused_outright(text: str) -> None:
    with pytest.raises(StructureError, match="refused"):
        rules.parse(text, "xml")


def test_a_structure_is_written_as_xml_under_one_root() -> None:
    written = rules.dump(GATES, "xml")
    assert written.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<root>')
    with pytest.raises(StructureError, match="XML element"):
        rules.dump({"1 bad": 1}, "xml")


def test_toml_reads_and_writes_tables_and_arrays_of_tables() -> None:
    written = rules.dump(GATES, "toml")
    assert "[[gates]]" in written and 'name = "dark mode"' in written
    assert tomllib.loads(written) == GATES
    odd = {"server": {"host": "127.0.0.1", "ports": [8000, 8001], "tls": {"on": False}}, "a b": 1.5}
    assert tomllib.loads(rules.dump(odd, "toml")) == odd
    assert rules.parse("when = 2026-11-17T10:00:00\n", "toml") == {"when": "2026-11-17T10:00:00"}


def test_toml_cannot_hold_null_or_a_list_at_the_top_and_says_so() -> None:
    with pytest.raises(StructureError, match=r"null\), at \$.next"):
        rules.dump(ORDERS, "toml")
    with pytest.raises(StructureError, match="object at the top"):
        rules.dump([1, 2], "toml")


# ===== records, shapes, names =====


def test_records_flatten_for_a_grid() -> None:
    rows = rules.records(ORDERS["orders"])
    assert rows[0] == {
        "id": 1, "status": "open", "total": 120.5, "customer.name": "Acme Ltd", "customer.region": "North",
        "lines": '[{"sku": "A-1", "qty": 2}]',
    }  # fmt: skip
    assert rules.records(["a", "b"]) == [{"value": "a"}, {"value": "b"}]
    with pytest.raises(StructureError, match="not a list"):
        rules.records({"a": 1})
    assert rules.record_lists(ORDERS) == ["$.orders", "$.orders[0].lines"]


def test_the_shape_has_types_and_counts_but_no_values() -> None:
    found = rules.shape(ORDERS)
    assert found["keys"]["orders"]["count"] == 3
    assert found["keys"]["orders"]["items"]["keys"]["customer"]["keys"]["region"] == {"type": "text"}
    assert "Acme" not in str(found)
    cut = rules.preview({"items": list(range(50)), "text": "x" * 500}, items=5, chars=10)
    assert cut["items"][-1] == "<45 more>" and cut["text"] == "x" * 10 + "…"


def test_names_and_files() -> None:
    assert rules.file_name("gates", "yaml") == "gates.yaml"
    assert rules.file_name("gates.json", "toml") == "gates.toml"
    assert rules.name_of("conf/gates.yml") == "gates"
    assert rules.format_of("A.XML") == "xml" and rules.format_of("a.csv") is None
    with pytest.raises(StructureError):
        rules.check_name("a/b")
