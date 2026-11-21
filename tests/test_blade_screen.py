"""The blade screen (the owner, 2026-11-17; its code editable since 2026-11-21's blade IDE,
tests/test_blade_ide.py): the header written, the code's bytes as they were; a table blade has
a table name of its own, checked as it is typed ("Shouldnt the table it makes be namable by me with a
realtime check for available names"); the catalog checkbox went ("all blades should be in the catalog
already"): a connection's tables are always listed. Made-up data only."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.client import blades_client
from swissarmybench.domain import blade_tables
from swissarmybench.domain.blade_tables import with_header
from swissarmybench.domain.blades import read_blade
from swissarmybench.server.blade_templates import TEMPLATES
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


TABLE_BLADE = """# /// swissarmybench-blade
# format = 1
# name = "Monthly sales"
# kind = "other"
# description = "Made-up sales by month"
# variable = "monthly"
# ///
import pandas as pd\r
\r
\r
def monthly() -> pd.DataFrame:   # odd spacing and CRLF line ends: the user's own bytes\r
    return pd.DataFrame({"month": ["2026-01"], "total": [10.5]})\r
"""


def code_of(text: str) -> str:
    return text.split("# ///\n", 2)[-1] if "\r" not in text else text.split("# ///\n")[-1]


# ===== the header: the table name read and written, the code's bytes untouched =====


def test_the_table_name_is_written_into_the_header_and_the_code_is_untouched() -> None:
    blade = read_blade(TABLE_BLADE.replace("\r\n", "\n"))
    assert "table" not in blade  # none set: the name its code makes
    changed = with_header(TABLE_BLADE, blade | {"table": "monthly_sales", "tags": ["sales"]})
    assert '# table = "monthly_sales"' in changed and '# tags = ["sales"]' in changed
    body = TABLE_BLADE[TABLE_BLADE.index("# ///\n", 10) + len("# ///\n") :]
    assert changed.endswith(body)  # every byte after the header, CRLF and all
    assert read_blade(changed.replace("\r\n", "\n"))["table"] == "monthly_sales"
    # Read again and written again: the same bytes.
    again = read_blade(changed.replace("\r\n", "\n"))
    assert with_header(changed, again | {"code": again["code"]}) == changed


# ===== the live check's every answer =====


def check(name: str, blade: str | None = "Mine") -> blade_tables.NameCheck:
    return blade_tables.check_name(
        name,
        blade=blade,
        open_tables=["orders"],
        connections=["Sales DB"],
        blade_tables={"Monthly sales": "monthly_sales", "Mine": "my_table"},
        reserved=["select", "from"],
    )


def test_the_live_check_says_each_answer_in_plain_words() -> None:
    assert check("fresh_name").to_json() == {"name": "fresh_name", "available": True, "said": "available"}
    assert check("ORDERS").said == "ORDERS is already a table"
    assert check("sales db").said.startswith("not a valid name")  # a space: no table can be called that
    assert check("Sales-DB").available  # not the connection's name
    assert (
        blade_tables.check_name(
            "warehouse", blade=None, open_tables=[], connections=["Warehouse"], blade_tables={}, reserved=[]
        ).said
        == "warehouse is a connection"
    )
    assert check("Monthly_Sales").said == "Monthly_Sales is Monthly sales's table"
    assert check("my_table").available  # a blade may keep its own
    assert check("my_table", blade="Other").said == "my_table is Mine's table"
    assert check("Select").said == "not a valid name: Select is a word DuckDB's SQL keeps for itself"
    assert check("").said.startswith("not a valid name")
    assert check("x" * 65).said.startswith("not a valid name")


def test_only_a_table_blade_names_a_table() -> None:
    assert blade_tables.names_table("other", None)
    assert not blade_tables.names_table("other", "csv")  # a file connection: named through it
    assert not blade_tables.names_table("other", "python")
    assert not blade_tables.names_table("sql", "sqlite")
    assert not blade_tables.names_table("vault", None) and not blade_tables.names_table("snippet", None)
    assert not blade_tables.names_table("other", None, {"api": "Orders"})  # a web call: its API's


# ===== the routes: New blade, the check, saving, no route edits code =====


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        yield test_client


def made_table_blade(client: TestClient, table: str = "monthly_sales") -> dict[str, Any]:
    made: dict[str, Any] = ok(
        client.post(
            "/blades/new", json={"template": "table", "name": "Monthly sales", "table": table}, headers=AUTH
        )
    )
    return made


def test_new_blade_makes_a_file_in_the_librarys_blades_folder(client: TestClient) -> None:
    choices = ok(client.get("/blades/new", headers=AUTH))["choices"]
    assert [c["id"] for c in choices][:4] == ["table", "code", "secret", "snippet"]
    assert {"summary", "pareto", "correlations"} <= {c["id"] for c in choices}
    assert not {"sqlite", "csv", "azure_key_vault"} & {c["id"] for c in choices}  # connections: their page
    made = made_table_blade(client)
    file = Path(made["file"])
    assert file.parent.name == "blades" and file.name == "monthly_sales.blade.py" and file.is_file()
    assert '# table = "monthly_sales"' in file.read_text(encoding="utf-8")
    for choice in ("code", "secret", "snippet", "summary"):
        assert ok(client.post("/blades/new", json={"template": choice}, headers=AUTH))["name"]
    assert client.post("/blades/new", json={"template": "sqlite"}, headers=AUTH).status_code == 400


def test_an_edited_file_shows_its_new_code_without_a_restart(client: TestClient) -> None:
    file = Path(made_table_blade(client)["file"])
    text = file.read_text(encoding="utf-8").replace(
        '"name": ["Ada", "Bea", "Cy"]', '"name": ["Dot", "Eve", "Flo"]'
    )
    file.write_text(text + "# changed in my own editor\n", encoding="utf-8")
    code = ok(client.get("/blades/Monthly%20sales", headers=AUTH))["code"]
    assert '"Dot"' in code and code.endswith("# changed in my own editor\n")


def test_the_check_is_one_route_for_the_page_and_the_agent(client: TestClient) -> None:
    made_table_blade(client)
    ok(client.put("/datasets/orders", json={"columns": ["a"], "data": [[1]]}, headers=AUTH))
    ok(
        client.post(
            "/connections",
            json={
                "name": "Sales DB",
                "kind": "sql",
                "template": "sqlite",
                "dialect": "sqlite",
                "code": "import sqlite3\nconn = sqlite3.connect(':memory:')\n",
            },
            headers=AUTH,
        )
    )

    def said(name: str, blade: str = "Another") -> str:
        for who in (AUTH, AGENT):
            answer = ok(client.get("/blades/table-name", params={"name": name, "blade": blade}, headers=who))
        return str(answer["said"])

    assert said("fresh") == "available"
    assert said("orders") == "orders is already a table"
    assert said("Sales DB").startswith("not a valid name")
    assert said("monthly_sales") == "monthly_sales is Monthly sales's table"
    assert said("monthly_sales", "Monthly sales") == "available"
    assert said("where") == "not a valid name: where is a word DuckDB's SQL keeps for itself"


def test_saving_refuses_a_taken_name_with_the_same_words(client: TestClient) -> None:
    made_table_blade(client)
    ok(client.put("/datasets/orders", json={"columns": ["a"], "data": [[1]]}, headers=AUTH))
    refused = client.put("/blades/Monthly%20sales", json={"table": "orders"}, headers=AUTH)
    assert refused.status_code == 400 and "orders is already a table" in refused.text
    taken = client.post(
        "/blades/new", json={"template": "table", "name": "Other", "table": "monthly_sales"}, headers=AUTH
    )
    assert taken.status_code == 400 and "monthly_sales is Monthly sales's table" in taken.text


def test_the_header_changes_and_the_codes_bytes_do_not(client: TestClient) -> None:
    file = Path(made_table_blade(client)["file"])
    file.write_bytes(file.read_bytes().replace(b"\n", b"\r\n"))  # the user's own line ends
    before = file.read_bytes()
    body = before[before.index(b"# ///\r\n", 10) :]
    unchanged = ok(client.put("/blades/Monthly%20sales", json={"table": "monthly_sales"}, headers=AUTH))
    assert unchanged["table"] == "monthly_sales" and file.read_bytes() == before  # nothing changed: no byte
    ok(
        client.put(
            "/blades/Monthly%20sales",
            json={
                "name": "Sales by month",
                "description": "Made-up",
                "tags": ["sales"],
                "table": "sales_by_month",
            },
            headers=AUTH,
        )
    )
    after = file.read_bytes()
    assert (
        after.endswith(body)
        and b'# table = "sales_by_month"' in after
        and b'# name = "Sales by month"' in after
    )
    assert ok(client.get("/blades/Sales%20by%20month", headers=AUTH))["table"] == "sales_by_month"


def test_only_its_code_and_header_are_changed_never_its_kind(client: TestClient) -> None:
    """The blade IDE (the owner, 2026-11-21) saves code (tests/test_blade_ide.py); its kind and variable
    follow from the code, never set by hand."""
    file = Path(made_table_blade(client)["file"])
    before = file.read_bytes()
    whole = ok(client.get("/blades/Monthly%20sales", headers=AUTH))
    for who in (AUTH, AGENT):
        for change in ({"kind": "analysis"}, {"variable": "other"}):
            refused = client.put("/blades/Monthly%20sales", json=change, headers=who)
            assert refused.status_code == 400 and "follows from its code" in refused.text, change
    # The whole blade as blades_get gave it, unchanged but for its words: taken (its code as it was).
    ok(client.put("/blades/Monthly%20sales", json=whole | {"description": "Still made-up"}, headers=AUTH))
    assert file.read_bytes().endswith(before[before.index(b"# ///\n", 10) :])
    assert (
        client.post("/blades/fill", json={"code": "x = 1\n", "values": {}}, headers=AUTH).status_code == 200
    )
    assert file.read_bytes().endswith(before[before.index(b"# ///\n", 10) :])  # fill saves nothing


def test_show_its_file_is_the_users_click_only(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from swissarmybench.server import file_manager

    shown: list[str] = []
    monkeypatch.setattr(file_manager, "reveal", shown.append)
    file = made_table_blade(client)["file"]
    assert client.post("/blades/Monthly%20sales/show", headers=AGENT).status_code == 403
    assert ok(client.post("/blades/Monthly%20sales/show", headers=AUTH)) == {"shown": file} and shown == [
        file
    ]


def test_a_connections_listing_is_shown_and_a_function_blade_has_none(client: TestClient) -> None:
    made_table_blade(client)
    function = ok(client.get("/blades/Monthly%20sales", headers=AUTH))
    assert function["catalog"] is None and function["names_table"] and function["connection"] is None
    # A connection saved before with no listing query (the catalog checkbox off): its starter's on read.
    ok(
        client.post(
            "/blades",
            json={
                "name": "Bakery",
                "kind": "sql",
                "template": "sqlite",
                "dialect": "sqlite",
                "code": "import sqlite3\nconn = sqlite3.connect(':memory:')\n",
            },
            headers=AUTH,
        )
    )
    bakery = ok(client.get("/blades/Bakery", headers=AUTH))
    sqlite = next(t for t in TEMPLATES if t.id == "sqlite")
    assert bakery["catalog"] == {"language": sqlite.catalog_language, "command": sqlite.catalog_command}
    assert bakery["has_catalog"] and not bakery["names_table"]
    assert "[catalog]" not in Path(bakery["file"]).read_text(encoding="utf-8")  # nothing written
    # By its dialect when its starter is not known.
    assert blade_tables.listing_for("sql", None, "postgres", TEMPLATES) == next(
        (t.catalog_language, t.catalog_command) for t in TEMPLATES if t.id == "postgres"
    )
    assert blade_tables.listing_for("other", None, "other", TEMPLATES) is None


def test_the_connections_tree_and_the_data_explorer_still_list_a_connections_tables(
    client: TestClient, tmp_path: Path
) -> None:
    import sqlite3

    database = tmp_path / "bakery.db"
    with sqlite3.connect(database) as made:
        made.execute("CREATE TABLE loaves (id INTEGER, name TEXT)")
    ok(
        client.post(
            "/blades",
            json={
                "name": "Bakery",
                "kind": "sql",
                "template": "sqlite",
                "dialect": "sqlite",
                "code": f"import sqlite3\nconn = sqlite3.connect({str(database)!r})\n",
            },
            headers=AUTH,
        )
    )
    ok(client.post("/blades/Bakery/refresh", headers=AUTH))  # its starter's listing query, filled on read
    found = ok(client.get("/explorer/search", params={"q": "loaves"}, headers=AUTH))
    assert any(r["name"] == "loaves" for g in found["groups"] for r in g["results"])
    tree = ok(client.get("/connections/Bakery/tree", headers=AUTH))
    assert "loaves" in str(tree)


# ===== where the table's name lands =====


def test_the_data_explorer_lists_a_blades_table_by_its_name(client: TestClient) -> None:
    made_table_blade(client)
    found = ok(client.get("/explorer/search", params={"q": "monthly_sales"}, headers=AUTH))
    [hit] = [r for g in found["groups"] for r in g["results"] if r["name"] == "monthly_sales"]
    assert hit["detail"] == "Monthly sales's table" and hit["insert"]["sql"] == "monthly_sales"
    assert hit["insert"]["python"] == 'make_table = sab.blade("Monthly sales")'


def test_sab_blade_registers_its_table_under_its_name(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pd = pytest.importorskip("pandas")
    made_table_blade(client)
    spec = ok(client.get("/blades/Monthly%20sales/python", headers=AUTH))
    assert spec["table"] == "monthly_sales"
    shell = types.SimpleNamespace(user_ns={})
    ipython = types.ModuleType("IPython")
    ipython.get_ipython = lambda: shell  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "IPython", ipython)
    monkeypatch.setattr(blades_client, "_spec", lambda name: spec)
    make_table = blades_client.blade("Monthly sales")
    assert make_table.__name__ == "make_table" and "monthly_sales" not in shell.user_ns
    frame = make_table()
    assert shell.user_ns["monthly_sales"] is frame and isinstance(frame, pd.DataFrame)
    # A blade whose code makes the table itself: registered at once; none set: nothing registered.
    assert blades_client._named(frame, "") is frame
    assert blades_client.register_table("by_month", frame) is frame and shell.user_ns["by_month"] is frame
