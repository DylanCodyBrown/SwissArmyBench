"""The shared catalog's rules (domain/shared_catalog.py; the owner, 2026-11-17: "a shared meta store on
GitHub ... any connection made in a project would save to a centralized catalog it would sync and prune in
realtime"). One file per connection: names, types, keys and usage, never a value or a secret; the same catalog
is the same bytes; two people's additions merge cleanly; a successful listing marks what it lost gone, a
failed one changes nothing; gone tables go after 30 days. Made-up data only. Git runs in these tests only."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from swissarmybench.domain import shared_catalog as rules
from swissarmybench.domain.relationships import Model, Relationship

GOLDEN = Path(__file__).parent / "golden" / "shared_catalog" / "warehouse.json"
TODAY = "2026-11-18"


def rows(*tables: tuple[str, str, list[tuple[str, str]]]) -> list[rules.Listed]:
    return [
        rules.Listed("", schema, table, column, kind, column != "id")
        for schema, table, columns in tables
        for column, kind in columns
    ]


ORDERS = ("sales", "orders", [("id", "INTEGER"), ("customer_id", "INTEGER"), ("amount", "DECIMAL(12,2)")])
CUSTOMERS = ("sales", "customers", [("id", "INTEGER"), ("region", "VARCHAR")])
PRODUCTS = ("sales", "products", [("id", "INTEGER"), ("label", "VARCHAR")])


def model() -> Model:
    return Model(
        keys={"customers": ("id",), "orders": ("id",)},
        sources={"orders": "connection:Warehouse", "customers": "connection:Warehouse"},
        relationships=(
            Relationship(
                "orders",
                ("customer_id",),
                "customers",
                ("id",),
                note="12 orders point at customer 4471",  # a value from the data: never kept
                evidence="99% of values found, 12 orphans",  # numbers from the data: never kept
            ),
        ),
    )


def warehouse() -> rules.Catalog:
    made = rules.listed(
        rules.Catalog("Warehouse", "database", "postgres"), rows(ORDERS, CUSTOMERS), TODAY, 30
    )
    made = rules.with_model(made, model())
    return rules.with_usage(made, "Sales review", {"orders", "customers"})


def test_the_file_is_the_golden_text_byte_for_byte_and_reads_back_the_same() -> None:
    text = rules.render(warehouse())
    assert text == GOLDEN.read_text(encoding="utf-8")
    again = rules.parse(text, "catalog/warehouse.json")
    assert rules.render(again) == text  # the same catalog is the same bytes
    # The same events in another order make the same file.
    other = rules.with_usage(
        rules.with_model(
            rules.listed(
                rules.Catalog("Warehouse", "database", "postgres"), rows(CUSTOMERS, ORDERS), TODAY, 30
            ),
            model(),
        ),
        "Sales review",
        {"customers", "orders"},
    )
    assert rules.render(other) == text
    assert rules.file_name("Warehouse") == "warehouse.json"
    assert rules.file_name("Finance Captive / EU") == "finance_captive_eu.json"


def test_names_types_and_keys_only_never_a_value_or_a_secret() -> None:
    text = rules.render(warehouse())
    for value in ("4471", "99%", "orphans", "12 orders"):
        assert value not in text, value
    table = rules.parse(text).tables["sales.orders"]
    assert table.primary_key == ("id",)
    as_json = table.to_json()
    keys = {c["name"]: c.get("key", "") for c in as_json["columns"]}
    assert keys == {"id": "primary", "customer_id": "foreign", "amount": ""}
    assert as_json["relationships"] == [
        {
            "from": "orders",
            "from_columns": ["customer_id"],
            "to": "customers",
            "to_columns": ["id"],
            "kind": "many-to-one",
        }
    ]
    assert as_json["used_by"] == ["Sales review"]
    # A catalog's fields are names: a planted password in a connection's code never reaches here, as the
    # catalog is made from listings and the model alone (the HTTP test plants one in a real connection).
    assert set(rules.Catalog("X").to_json()) == {"format", "connection", "kind", "template", "tables"}


def test_a_successful_listing_marks_what_went_gone_a_failed_one_changes_nothing_and_30_days_prune() -> None:
    first = warehouse()
    # A failed listing is never applied (the service only applies a listing that succeeded): nothing changes.
    assert rules.render(first) == rules.render(rules.parse(rules.render(first)))
    # The next successful listing has no customers: gone since today, its keys and used_by kept.
    second = rules.listed(first, rows(ORDERS, PRODUCTS), "2026-11-20", 30)
    gone = second.tables["sales.customers"]
    assert (gone.state, gone.gone_since, gone.used_by) == ("gone", "2026-11-20", ("Sales review",))
    assert second.tables["sales.products"].state == "present"
    # Listed again while gone: present again, the date gone.
    back = rules.listed(second, rows(ORDERS, CUSTOMERS), "2026-11-25", 30)
    assert (back.tables["sales.customers"].state, back.tables["sales.customers"].gone_since) == (
        "present",
        "",
    )
    assert back.tables["sales.products"].gone_since == "2026-11-25"
    # Still gone: the date stays as it was (the file does not change day by day).
    later = rules.listed(second, rows(ORDERS, PRODUCTS), "2026-12-01", 30)
    assert later.tables["sales.customers"].gone_since == "2026-11-20"
    assert rules.render(rules.listed(later, rows(ORDERS, PRODUCTS), "2026-12-02", 30)) == rules.render(later)
    # 30 days after it went (a fake clock): removed.
    assert "sales.customers" in rules.prune(later, "2026-12-19", 30).tables
    assert "sales.customers" not in rules.prune(later, "2026-12-20", 30).tables
    assert "sales.customers" not in rules.listed(later, rows(ORDERS, PRODUCTS), "2026-12-20", 30).tables


def test_a_deleted_relationship_goes_and_a_project_stops_using_a_table() -> None:
    made = warehouse()
    removed = rules.without_joins(made, [rules.Join("orders", ("customer_id",), "customers", ("id",))])
    assert removed.tables["sales.orders"].relationships == ()
    other = rules.with_usage(made, "Churn study", {"customers"})
    assert other.tables["sales.customers"].used_by == ("Churn study", "Sales review")
    dropped = rules.with_usage(other, "Sales review", {"orders"})
    assert dropped.tables["sales.customers"].used_by == ("Churn study",)  # someone else's stays
    assert dropped.tables["sales.orders"].used_by == ("Sales review",)
    # A document's code names a table: used (relationship_scope's rule: words, dbo.Orders as dbo_Orders).
    assert rules.used_names(made, set(), ["SELECT * FROM [Warehouse].sales.orders"]) >= {"orders"}


def test_a_bad_file_says_so_with_its_name() -> None:
    text = rules.render(warehouse())
    conflicted = text.replace(
        '"kind": "database",', '<<<<<<< ours\n  "kind": "database",\n=======\n  "kind": "db",\n>>>>>>> theirs'
    )
    with pytest.raises(rules.CatalogFileError, match=r"catalog/warehouse\.json has merge conflict markers"):
        rules.parse(conflicted, "catalog/warehouse.json")
    with pytest.raises(rules.CatalogFileError, match=r"catalog/warehouse\.json does not read as JSON"):
        rules.parse(text[:-5], "catalog/warehouse.json")


@pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed (the test's tool, never the app's)"
)
def test_two_peoples_independent_additions_merge_cleanly(tmp_path: Path) -> None:
    alphabet = [(("sales", f"table_{c}", [("id", "INTEGER")])) for c in "bdfhjl"]
    base = rules.listed(rules.Catalog("Warehouse", "database", "postgres"), rows(*alphabet), TODAY, 30)
    # One adds a table near the start and uses another; the other adds one near the end.
    ours = rules.listed(base, rows(*alphabet, ("sales", "table_c", [("id", "INTEGER")])), TODAY, 30)
    ours = rules.with_usage(ours, "Sales review", {"table_h"})
    theirs = rules.listed(
        base, rows(*alphabet, ("sales", "table_k", [("id", "INTEGER"), ("v", "VARCHAR")])), TODAY, 30
    )
    files = {}
    for name, cat in (("base", base), ("ours", ours), ("theirs", theirs)):
        files[name] = tmp_path / f"{name}.json"
        files[name].write_text(rules.render(cat), encoding="utf-8", newline="\n")
    done = subprocess.run(  # noqa: S603 (the test's own files)
        ["git", "merge-file", "-p", str(files["ours"]), str(files["base"]), str(files["theirs"])],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout
    merged = rules.parse(done.stdout)
    assert {"sales.table_c", "sales.table_k"} <= set(merged.tables)
    assert merged.tables["sales.table_h"].used_by == ("Sales review",)
    both = rules.with_usage(
        rules.listed(
            base,
            rows(
                *alphabet,
                ("sales", "table_c", [("id", "INTEGER")]),
                ("sales", "table_k", [("id", "INTEGER"), ("v", "VARCHAR")]),
            ),
            TODAY,
            30,
        ),
        "Sales review",
        {"table_h"},
    )
    assert done.stdout == rules.render(both)  # the merge is the file either would write with both
