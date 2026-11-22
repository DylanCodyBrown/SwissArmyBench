"""The Environment's rules (domain/environment.py): rows, Used in, the one search, requirements.txt, Clear."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swissarmybench.domain import environment as rules
from swissarmybench.domain.environment import Document, Item, Used

NOTEBOOK = Document(
    "/p/data.ipynb",
    "data.ipynb",
    (
        (1, "import pandas as pd\nimport duckdb"),
        (4, "late = orders[orders.status == 'Held']"),
        (6, "monthly = orders.groupby('month').sum() * tax_rate"),
        (7, "%%sql\nSELECT * FROM Customers"),
    ),
)
SCRIPT = Document("/p/load_orders.py", "load_orders.py", ((None, "import pyarrow as pa\nprint(orders)"),))


def test_cells_that_use_a_name_are_listed_by_document_with_their_numbers() -> None:
    found = rules.cell_uses([NOTEBOOK, SCRIPT], ["orders", "tax_rate", "nothing"])
    assert [u.words for u in found["orders"]] == ["data.ipynb · cells 4, 6", "load_orders.py"]
    assert found["orders"][0].link == {"to": "document", "path": "/p/data.ipynb", "cell": 4}
    assert [u.words for u in found["tax_rate"]] == ["data.ipynb · cell 6"]
    assert "nothing" not in found
    # A Python name is matched as written; a table's name in SQL in any case.
    assert "customers" not in rules.cell_uses([NOTEBOOK], ["customers"])
    assert (
        rules.cell_uses([NOTEBOOK], ["customers"], fold=True)["customers"][0].words == "data.ipynb · cell 7"
    )


def test_a_name_in_a_comment_is_not_a_use() -> None:
    """The sweep, 2026-11-22: a new project's API.py holds a commented example about an orders table, so a
    table called orders (the sample store's) said "Used in API.py" before anything used it."""
    api = rules.Document(
        "/p/API.py",
        "API.py",
        ((None, '"""Endpoints."""\n# db.read("orders", limit=5)\nlimit = 5  # of the orders\n'),),
    )
    assert "orders" not in rules.cell_uses([api], ["orders"], fold=True)
    used = rules.Document("/p/API.py", "API.py", ((None, 'rows = db.read("orders")  # every row\n'),))
    assert rules.cell_uses([used], ["orders"], fold=True)["orders"][0].words == "API.py"
    # A SQL cell is not Python (a # there is the source's own: a T-SQL temporary table), and code that does
    # not read as Python yet (half typed) is looked at as it is written.
    sql = rules.Document("/p/n.ipynb", "n.ipynb", ((3, "%%sql Shop\nSELECT * FROM #orders"),))
    assert rules.cell_uses([sql], ["orders"], fold=True)["orders"][0].words == "n.ipynb · cell 3"
    half = rules.Document("/p/n.ipynb", "n.ipynb", ((4, "total = orders['amount'].sum("),))
    assert rules.cell_uses([half], ["orders"])["orders"][0].words == "n.ipynb · cell 4"


def test_a_canvas_widget_that_names_a_table_is_a_use() -> None:
    canvas = (
        '{"pages": [{"id": "p1", "name": "Sales page", "children": [{"kind": "container", "children": ['
        '{"kind": "widget", "id": "w1", "widget": "revenue_chart", "values": {"table": "orders"}},'
        '{"kind": "widget", "id": "w2", "widget": "region_picker", "wires": {"options": {"value": "regions"}'
        "}}"
        "]}]}]}"
    )
    found = rules.canvas_uses([("sales", canvas), ("broken", "{not json")], ["orders", "regions", "x"])
    assert found["orders"][0].words == "Canvas · Sales page · revenue_chart"
    assert found["orders"][0].link == {"to": "canvas", "canvas": "sales", "page": "Sales page", "item": "w1"}
    assert found["regions"][0].kind == "widget"
    assert "x" not in found


def test_endpoints_analyses_the_erd_and_tables_made_from_a_table() -> None:
    endpoint = SimpleNamespace(
        method="GET",
        path="/orders",
        line=12,
        connections=["Warehouse"],
        sql=[{"text": "SELECT * FROM Orders"}],
    )
    assert rules.endpoint_uses([endpoint], ["orders"])["orders"][0].words == "API.py · GET /orders"
    cards = [{"id": "c1", "grid": "g1", "title": "Outliers on amount"}, {"id": "c2", "kind": "note"}]
    assert rules.analysis_uses(cards, {"g1": "orders"})["orders"][0].words == "Analyze · Outliers on amount"
    relationship = SimpleNamespace(from_table="orders", to_table="customers")
    erd = rules.erd_uses([relationship])
    assert erd["orders"][0].words == erd["customers"][0].words == "ERD · orders → customers"
    made = rules.made_from({"orders": None, "monthly": "SELECT month FROM orders GROUP BY 1"})
    assert [u.words for u in made["orders"]] == ["monthly (made from it)"]
    assert "monthly" not in made
    grids = rules.grid_uses(
        [{"id": "g1", "name": "orders", "steps": 3}, {"id": "g2", "name": "late", "steps": 0}]
    )
    assert [u.words for u in grids] == ["orders (3 steps)", "late"]


ITEMS = [
    Item(
        "table",
        "orders",
        "Table",
        "1,204 × 3",
        "order_id, customer_id, amount",
        "Warehouse",
        used=(Used("cell", "data.ipynb · cell 4"),),
        kids=(
            ("order_id", "whole number", ""),
            ("customer_id", "whole number", ""),
            ("amount", "decimal", ""),
        ),
    ),
    Item("table", "targets", "Table", "5 × 3", "region, month, target", "Made in the app · pasted"),
    Item("variable", "tax_rate", "Number", "", "0.0825", "data.ipynb · cell 2"),
    Item("variable", "CustomerKey", "Whole number", "", "4417", "data.ipynb · cell 3"),
    Item("setting", "WAREHOUSE_HOST", "Setting", "", "sql.larkfield.example", "the library's variables.toml"),
]


def test_one_search_runs_over_every_tab_by_the_explorers_matching() -> None:
    found, counts = rules.searched(ITEMS, "cust")
    assert [(i.name, m.own, m.kids) for i, m in found] == [
        ("orders", True, (1,)),  # its look names customer_id, and so does a column inside
        ("CustomerKey", True, ()),
    ]
    assert counts == {"table": 1, "variable": 1, "structure": 0, "setting": 0, "library": 0}
    assert rules.also(counts, "table") == [{"kind": "variable", "name": "Variables", "count": 1}]
    # By parts and in any case, a value's type, where it is used, where it comes from.
    assert [i.name for i, _ in rules.searched(ITEMS, "customerid")[0]] == ["orders"]
    assert [i.name for i, _ in rules.searched(ITEMS, "pasted")[0]] == ["targets"]
    assert [i.name for i, _ in rules.searched(ITEMS, "warehouse")[0]] == ["orders", "WAREHOUSE_HOST"]
    # A row matched only inside says which rows.
    inside = rules.match(ITEMS[0], ["decimal"])
    assert (inside.own, inside.kids) == (False, (2,))
    assert len(rules.searched(ITEMS, "")[0]) == len(ITEMS)


REQUIREMENTS = "# the project's libraries\nduckdb==1.4.2\npandas\npsycopg[binary]>=3  # the warehouse\n"


def test_requirements_are_read_pinned_and_unpinned_without_touching_other_lines() -> None:
    read = rules.requirements(REQUIREMENTS)
    assert [(r.name, r.spec, r.pinned) for r in read] == [
        ("duckdb", "==1.4.2", "1.4.2"),
        ("pandas", "", None),
        ("psycopg[binary]", ">=3", None),
    ]
    pinned = rules.with_pin(REQUIREMENTS, "Pandas", "2.3.3")
    assert pinned == REQUIREMENTS.replace("pandas\n", "pandas==2.3.3\n")
    assert rules.with_pin(pinned, "pandas", "2.3.3") == pinned  # the same again changes no byte
    assert rules.without_pin(pinned, "pandas") == REQUIREMENTS
    kept = rules.with_pin(REQUIREMENTS, "psycopg", "3.2.1")
    assert "psycopg[binary]==3.2.1  # the warehouse\n" in kept  # its extras and its comment stay
    added = rules.with_library(REQUIREMENTS, "polars")
    assert added == REQUIREMENTS + "polars\n"
    assert rules.with_library(added, "Polars") == added
    assert rules.without_library(added, "polars") == REQUIREMENTS
    assert rules.with_library("", "pandas") == "pandas\n"
    with pytest.raises(rules.EnvironmentRuleError):
        rules.with_pin(REQUIREMENTS, "pandas", "2.3.3; echo")
    with pytest.raises(rules.EnvironmentRuleError):
        rules.check_library("pandas --index-url http://x")


def test_the_libraries_tab_lists_what_is_required_or_imported_with_pins_and_newer_versions() -> None:
    imports = rules.imported_in([NOTEBOOK, SCRIPT])
    assert [u.words for u in imports["pandas"]] == ["data.ipynb · cell 1"]
    assert [u.words for u in imports["pyarrow"]] == ["load_orders.py"]
    installed = {"duckdb": "1.4.2", "pandas": "2.3.3", "pyarrow": "21.0.0", "pip": "25.0", "six": "1.17.0"}
    items = rules.library_items(
        installed,
        rules.requirements("duckdb==1.4.2\npandas\npolars\n"),
        imports,
        {"duckdb": "1.4.3", "pandas": "2.3.3", "pyarrow": "20.0.0"},
    )
    assert [i.name for i in items] == [
        "duckdb",
        "pandas",
        "polars",
        "pyarrow",
    ]  # pip and six: nobody chose them
    by = {i.name: i for i in items}
    assert by["duckdb"].more["pinned"] and by["duckdb"].more["latest"] == "1.4.3"
    assert by["duckdb"].value == "The table engine"
    assert by["pandas"].more["latest"] is None and not by["pandas"].more["pinned"]
    assert by["polars"].type == "not installed" and not by["polars"].more["installed"]
    assert by["pyarrow"].more["latest"] is None  # an older one on the index is never offered
    assert by["pyarrow"].origin == "installed, not in requirements.txt"
    assert rules.newer("1.35.1", "1.36.0") == "1.36.0" and rules.newer("1.36.0", None) is None


def test_a_secret_setting_never_carries_its_value() -> None:
    secret = rules.setting_item(
        {
            "name": "WAREHOUSE_PASSWORD",
            "from": "keyring",
            "set": True,
            "secret": True,
            "value": "made-up-word",
        },
        [Used("connection", "Warehouse")],
    )
    assert secret.value == f"{rules.MASK} (set)" and secret.sub == "secret" and secret.type == "Secret"
    assert "made-up-word" not in str(secret.to_json())
    assert secret.more["showable"]
    vault = rules.setting_item(
        {
            "name": "API_KEY",
            "from": "vault",
            "set": True,
            "vault": "larkfield-vault",
            "vault_secret": "api-key",
        },
        [],
    )
    # The vault and the secret's name, never a value.
    assert vault.origin == "key vault · larkfield-vault · api-key" and not vault.more["showable"]
    assert vault.kids[0] == ("comes from", "source", "key vault larkfield-vault, entry api-key")
    plain = rules.setting_item(
        {"name": "WAREHOUSE_HOST", "from": "value", "set": True, "value": "sql.example"}, []
    )
    assert plain.value == "sql.example" and plain.type == "Setting"
    uses = rules.setting_uses(
        [
            {"kind": "connection", "name": "Warehouse"},
            {"kind": "connection", "name": "Warehouse", "how": "password"},  # the box it fills
            {"kind": "notebook", "name": "data.ipynb", "path": "/p/d", "cell": 3},
        ]
    )
    assert [(u.kind, u.words) for u in uses] == [
        ("connection", "Warehouse"),
        ("connection", "Warehouse · Password"),
        ("cell", "data.ipynb · cell 3"),
    ]


def test_clear_takes_what_is_ticked_and_never_a_kept_table() -> None:
    items = [
        Item("table", "orders", tags=("Keep",)),
        Item("table", "scratch"),
        Item("table", "orders · sandbox", sub="sandbox"),
        Item("variable", "tax_rate"),
        Item("structure", "rates", more={"open": "s1"}),
        Item("structure", "order_form", more={"open": None}),
    ]
    plan = rules.clear_plan(items)
    assert plan == {"tables": ["scratch"], "variables": ["tax_rate"], "structures": ["rates"]}
    assert rules.clear_choice({"tables": True, "variables": True}) == ["tables", "variables"]
    assert rules.clear_words(plan, ["tables", "variables"]) == "Clear 1 table, 1 variable"
    with pytest.raises(rules.EnvironmentRuleError):
        rules.clear_choice({})
    with pytest.raises(rules.EnvironmentRuleError):
        rules.clear_choice({"tables": "yes"})


def test_rows_are_named_and_inserted_into_code() -> None:
    assert rules.item_id(None, "table:orders") == ("table", "orders")
    assert rules.item_id("variable", "tax_rate") == ("variable", "tax_rate")
    with pytest.raises(rules.EnvironmentRuleError):
        rules.item_id("grid", "orders")
    assert rules.insert_code("table", "orders") == {"sql": "SELECT * FROM orders", "python": "orders"}
    assert rules.insert_code("table", "orders-2026")["python"] == 'sab.table("orders-2026")'
    assert rules.insert_code("structure", "rates") == {"python": 'sab.structure("rates")'}
    assert rules.insert_code("setting", "WAREHOUSE_HOST")["text"] == "$" + "{WAREHOUSE_HOST}"
    assert rules.insert_code("library", "scikit-learn", "import sklearn") == {"python": "import sklearn"}
    assert rules.insert_code("library", "mssql-python") == {"python": "import mssql_python"}
    assert rules.type_words("pandas.core.frame.DataFrame") == "Table" and rules.type_words("Order") == "Order"
    assert rules.table_size(1204880, 9) == "1,204,880 × 9"
    assert rules.columns_look(list("abcdefghi")) == "a, b, c, d, +5"
