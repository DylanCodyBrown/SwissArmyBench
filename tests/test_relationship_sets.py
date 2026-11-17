"""Relationship sets (saved, shared sets of relationships; tangs until 2026-11-17), managing the joins in
use, and the finder's rules, in the domain: no DuckDB here.

Made-up table and column names only.
"""

from __future__ import annotations

import json

import pytest

from swissarmybench.domain.relationships import (
    Candidate,
    Model,
    Relationship,
    RelationshipSetError,
    conflicts,
    edit_joins,
    from_connection,
    join_keys,
    judge,
    key_family,
    merge,
    name_likeness,
    parse_model,
    path_between,
    read_set,
    same_set,
    set_file_name,
    suggest,
    without_connection,
    without_joins,
    write_set,
)

SALES = {
    "name": "Sales store",
    "description": "The made-up store's joins",
    "tags": ["sales", "orders-function-app"],
    "saved_at": "2026-11-13T09:14:00",
    "author": "Avery",
    "tables": {
        "orders": {
            "primary_key": ["order_id"],
            "columns": [["order_id", "BIGINT"], ["customer_id", "BIGINT"]],
        },
        "customers": {"primary_key": ["cust_key"], "columns": [["cust_key", "BIGINT"]]},
    },
    "relationships": [
        {
            "from": "orders",
            "from_columns": ["customer_id"],
            "to": "customers",
            "to_columns": ["cust_key"],
            "note": "about 1% orphans",
            "evidence": "99% of values found, 120 orphans",
        },
        {
            "from": "orders",
            "from_columns": ["ship_date"],
            "to": "calendar",
            "to_columns": ["date_key"],
            "active": False,
        },
    ],
}


# ===== the .relationships.json file =====


def test_a_set_round_trips_everything_and_starts_with_its_marker() -> None:
    model = parse_model(SALES)
    text = write_set(model)
    assert text.lstrip().startswith('{\n  "swissarmybench": "relationship-set",\n  "format": 1,')
    back = read_set(text)
    assert back == model
    assert back.tags == ("sales", "orders-function-app") and back.author == "Avery"
    assert back.columns["orders"] == (("order_id", "BIGINT"), ("customer_id", "BIGINT"))
    assert back.relationships[0].evidence == "99% of values found, 120 orphans"
    assert back.relationships[1].active is False
    assert set_file_name("Sales store") == "sales_store.relationships.json"


@pytest.mark.parametrize(
    ("text", "says"),
    [
        ("not json at all", "not readable"),
        (json.dumps(SALES), 'does not start with "swissarmybench": "relationship-set"'),
        (json.dumps({"swissarmybench": "blade", "format": 1}), "does not start with"),
        (json.dumps({"swissarmybench": "tang", "format": 2, "name": "x"}), "format 2"),
        (json.dumps({"swissarmybench": "tang", "format": 1, "name": "x", "tags": "sales"}), "tags"),
        (
            json.dumps({"swissarmybench": "tang", "format": 1, "relationships": [{"from": "a"}]}),
            "hold together",
        ),
    ],
)
def test_anything_but_a_set_is_refused_with_its_reason(text: str, says: str) -> None:
    with pytest.raises(RelationshipSetError, match=says):
        read_set(text)


def test_an_old_model_file_still_reads_and_names_may_have_spaces() -> None:
    old = {"name": "sample_store", "tables": {"orders": {"primary_key": ["order_id"]}}, "relationships": []}
    assert parse_model(old).name == "sample_store"
    assert parse_model(SALES).name == "Sales store"
    with pytest.raises(ValueError, match="name"):
        parse_model({"name": "a/b"})


def test_applying_a_second_set_wins_and_says_what_it_changed() -> None:
    base = parse_model(SALES)
    other = parse_model(
        {
            "name": "Shipping",
            "tags": ["logistics"],
            "tables": {"orders": {"primary_key": ["order_id", "line_no"]}},
            "relationships": [
                {
                    "from": "orders",
                    "from_columns": ["customer_id"],
                    "to": "customers",
                    "to_columns": ["cust_key"],
                    "kind": "one-to-one",
                }
            ],
        }
    )
    assert conflicts(base, other) == [
        "orders -> customers: many-to-one becomes one-to-one",
        "orders's key: order_id becomes order_id, line_no",
    ]
    merged = merge(base, other)
    assert merged.tags == ("sales", "orders-function-app", "logistics")
    assert [r.kind for r in merged.relationships if r.to_table == "customers"] == ["one-to-one"]
    assert conflicts(base, base) == []


# ===== the finder's rules =====


@pytest.mark.parametrize(
    ("column", "table", "key", "least"),
    [
        ("category_id", "categories", "category_id", 1.0),
        ("customer_id", "customers", "cust_key", 0.9),  # the table's name, singular
        ("home_store", "stores", "store_id", 0.9),  # the table's name inside the column's
        ("order_date", "calendar", "date_key", 0.9),  # the key's stem inside the column's
        ("cust_ref", "customers", "id", 0.6),  # a shortened stem
    ],
)
def test_names_that_point_at_a_key(column: str, table: str, key: str, least: float) -> None:
    assert name_likeness(column, table, key) >= least


@pytest.mark.parametrize(
    ("column", "table", "key"),
    [("quantity", "categories", "category_id"), ("customer_id", "orders", "order_id")],
)
def test_names_that_do_not(column: str, table: str, key: str) -> None:
    assert name_likeness(column, table, key) == 0.0


def candidate(**over: object) -> Candidate:
    base: dict[str, object] = {
        "from_table": "orders",
        "from_columns": ("customer_id",),
        "to_table": "customers",
        "to_columns": ("cust_key",),
        "from_distinct": 2000,
        "to_distinct": 2000,
        "shared": 1980,
        "from_unique": False,
        "to_unique": True,
        "types": ("integer", "integer"),
    }
    return Candidate(**(base | over))  # type: ignore[arg-type]


def test_a_real_join_is_suggested_with_its_reasons() -> None:
    found = judge(candidate())
    assert found is not None and found.relationship.kind == "many-to-one" and found.orphans == 20
    assert any("99% of orders.customer_id" in r for r in found.reasons)
    assert any("20 values have no match" in r for r in found.reasons)
    text = judge(candidate(types=("text", "integer")))
    assert text is not None and text.relationship.note == "text on one side, a number on the other"


@pytest.mark.parametrize(
    ("why", "over"),
    [
        ("the key is not unique", {"to_unique": False}),
        ("too few values found", {"shared": 1200}),
        (
            "a small number column in a small key, no name",
            {
                "from_columns": ("quantity",),
                "to_table": "categories",
                "to_columns": ("category_id",),
                "from_distinct": 10,
                "to_distinct": 12,
                "shared": 10,
            },
        ),
        (
            "two counters from 1, no name",
            {
                "from_table": "customers",
                "from_columns": ("cust_key",),
                "to_table": "orders",
                "to_columns": ("order_id",),
                "from_unique": True,
                "from_distinct": 2000,
                "to_distinct": 20000,
                "shared": 2000,
            },
        ),
        ("a float is never a key", {"types": ("float", "float")}),
    ],
)
def test_accidents_are_not_suggested(why: str, over: dict[str, object]) -> None:
    assert judge(candidate(**over)) is None, why


def test_an_implied_join_is_dropped_and_a_second_path_is_inactive() -> None:
    found = suggest(
        [
            candidate(
                from_table="returns",
                from_columns=("order_id", "line_no"),
                to_table="order_lines",
                to_columns=("order_id", "line_no"),
                from_distinct=2000,
                to_distinct=60000,
                shared=2000,
            ),
            candidate(
                from_table="order_lines",
                from_columns=("order_id",),
                to_table="orders",
                to_columns=("order_id",),
                from_distinct=20000,
                to_distinct=20000,
                shared=20000,
            ),
            # returns.order_id -> orders is the path above: not suggested on its own
            candidate(
                from_table="returns",
                from_columns=("order_id",),
                to_table="orders",
                to_columns=("order_id",),
                from_distinct=2000,
                to_distinct=20000,
                shared=2000,
            ),
            candidate(
                from_columns=("order_date",),
                to_table="calendar",
                to_columns=("date_key",),
                from_distinct=1000,
                to_distinct=1096,
                shared=1000,
                from_position=3,
                types=("date", "date"),
            ),
            candidate(
                from_columns=("ship_date",),
                to_table="calendar",
                to_columns=("date_key",),
                from_distinct=1000,
                to_distinct=1096,
                shared=999,
                from_position=4,
                types=("date", "date"),
            ),
        ]
    )
    joins = {
        (s.relationship.from_table, s.relationship.from_columns, s.relationship.to_table): s.relationship
        for s in found
    }
    assert ("returns", ("order_id",), "orders") not in joins
    assert ("returns", ("order_id", "line_no"), "order_lines") in joins
    assert joins[("orders", ("order_date",), "calendar")].active is True
    ship = joins[("orders", ("ship_date",), "calendar")]
    assert ship.active is False and "second path" in ship.note


def test_the_path_between_two_tables() -> None:
    rels = (
        Relationship("order_lines", ("order_id",), "orders", ("order_id",)),
        Relationship("order_lines", ("sku",), "products", ("sku",)),
        Relationship("products", ("category_id",), "categories", ("category_id",)),
    )
    chain = path_between(rels, "orders", "categories")
    assert [(r.from_table, r.to_table) for r in chain] == [
        ("order_lines", "orders"),
        ("order_lines", "products"),
        ("products", "categories"),
    ]
    assert path_between(rels, "orders", "regions") == []
    assert path_between(rels, "orders", "orders") == []


@pytest.mark.parametrize(
    ("duckdb_type", "family"),
    [
        ("BIGINT", "integer"),
        ("DOUBLE", "float"),
        ("DECIMAL(18,0)", "integer"),
        ("DECIMAL(10,2)", "float"),
        ("VARCHAR", "text"),
        ("DATE", "date"),
        ("BOOLEAN", "boolean"),
    ],
)
def test_key_families(duckdb_type: str, family: str) -> None:
    assert key_family(duckdb_type) == family


def test_a_model_without_set_fields_is_unchanged_in_json() -> None:
    plain = Model(name="x", keys={"a": ("id",)})
    assert plain.to_json() == {
        "name": "x",
        "description": "",
        "tables": {"a": {"primary_key": ["id"]}},
        "relationships": [],
    }


# ===== managing the joins in use =====


def _joins(n: int) -> dict[str, object]:
    """A made-up model of n joins from fact_<i> to dim_<i>."""
    return {
        "name": "Made-up warehouse",
        "relationships": [
            {"from": f"fact_{i}", "from_columns": ["key"], "to": f"dim_{i}", "to_columns": ["key"]}
            for i in range(n)
        ],
    }


def _key(i: int) -> dict[str, object]:
    return {"from": f"fact_{i}", "from_columns": ["key"], "to": f"dim_{i}", "to_columns": ["key"]}


def test_joins_are_deleted_by_their_ends_and_a_missing_one_is_skipped() -> None:
    model = parse_model(_joins(40))
    keys = join_keys([_key(i) for i in range(12)] + [{**_key(99)}])
    smaller, removed = without_joins(model, keys)
    assert removed == 12 and len(smaller.relationships) == 28
    assert smaller.relationships[0].from_table == "fact_12"
    with pytest.raises(ValueError, match="joins"):
        join_keys([])
    with pytest.raises(ValueError, match="from"):
        join_keys([{"from": "a b"}])


def test_kind_and_run_change_only_the_named_joins() -> None:
    model = parse_model(_joins(5))
    keys = join_keys([_key(1), _key(3)])
    changed, count = edit_joins(model, keys, active=False)
    assert count == 2 and [r.active for r in changed.relationships] == [True, False, True, False, True]
    again, count = edit_joins(changed, keys, active=False)
    assert count == 0 and again == changed  # already off: nothing changes
    kinds, count = edit_joins(model, join_keys([_key(0)]), kind="one-to-one")
    assert count == 1 and kinds.relationships[0].kind == "one-to-one"
    with pytest.raises(ValueError, match="kind must be one of"):
        edit_joins(model, keys, kind="sideways")
    with pytest.raises(ValueError, match="kind"):
        edit_joins(model, keys)


@pytest.mark.parametrize(
    ("source", "connection", "theirs"),
    [
        ("connection:FI-Atlas", "FI-Atlas", True),
        ("connection:fi-atlas", "FI-Atlas", True),
        ("Finance/Sales model (Power BI)", "Finance", True),
        ("Finance (Power BI)", "Finance", True),
        ("Financed/Sales (Power BI)", "Finance", False),
        ("connection:FI-Atlas-2", "FI-Atlas", False),
        ("examples/sample_store.py", "FI-Atlas", False),
    ],
)
def test_which_tables_a_connection_brought(source: str, connection: str, theirs: bool) -> None:
    assert from_connection(source, connection) is theirs


def test_a_deleted_connection_takes_its_relationships_and_leaves_the_rest() -> None:
    model = parse_model(
        {
            "name": "Mixed",
            "tables": {
                "gl_entry": {"primary_key": ["entry_id"], "source": "connection:FI-Atlas"},
                "gl_account": {"source": "connection:FI-Atlas"},
                "store": {"primary_key": ["store_id"]},
            },
            "relationships": [
                {"from": "gl_entry", "from_columns": ["account"], "to": "gl_account", "to_columns": ["id"]},
                {"from": "sales", "from_columns": ["store_id"], "to": "store", "to_columns": ["store_id"]},
                # No recorded source: matched by the tables read from the connection.
                {"from": "ledger", "from_columns": ["store_id"], "to": "store", "to_columns": ["store_id"]},
            ],
        }
    )
    left, removed = without_connection(model, "fi-atlas", {"ledger"})
    assert removed == 2
    assert [(r.from_table, r.to_table) for r in left.relationships] == [("sales", "store")]
    assert (
        "gl_entry" not in left.keys
        and "gl_account" not in left.sources
        and left.keys["store"] == ("store_id",)
    )
    same, none = without_connection(model, "Warehouse", set())
    assert none == 0 and same == model


def test_a_set_saved_again_with_only_a_new_time_is_the_same_set() -> None:
    from dataclasses import replace

    model = parse_model(SALES)
    assert same_set(model, replace(model, saved_at="2026-11-17T09:00:00+00:00"))
    assert not same_set(model, replace(model, description="Other"))
