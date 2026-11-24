""".sql files on the Scripts page (the owner, 2026-11-24: "also we should allow .sql files" / "sql authorship
will have one place in scripts and not on the grid menu"): the header line that names the connection, the
statements and the one under the cursor, the table a run makes, the line an error points at."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks, project_scope, workbench_pages
from swissarmybench.domain import sql_files as rules
from tests.conftest import AGENT, AUTH, grid_id, push

ORDERS = pa.table(
    {"order_id": [1, 2, 3], "amount": [10.0, 20.0, 5.0], "month": ["2026-01", "2026-01", "2026-02"]}
)


def test_the_connection_header_is_read() -> None:
    assert rules.connection_of("-- connection: Warehouse\nSELECT 1") == "Warehouse"
    assert (
        rules.connection_of("-- a note\n--  Connection :  Finance Captive  \nSELECT 1") == "Finance Captive"
    )
    assert rules.connection_of("SELECT 1") is None
    assert rules.connection_of("-- connection:\nSELECT 1") is None
    # Only among the file's first comment lines: one further down is the query's own comment.
    assert rules.connection_of("SELECT 1;\n-- connection: Warehouse\n") is None


def test_the_header_is_written_replaced_and_taken_away() -> None:
    assert rules.with_connection("SELECT 1", "Warehouse") == "-- connection: Warehouse\nSELECT 1"
    assert rules.with_connection("-- connection: A\nSELECT 1", "B") == "-- connection: B\nSELECT 1"
    assert rules.with_connection("-- connection: A\nSELECT 1", None) == "SELECT 1"
    assert rules.with_connection("SELECT 1", None) == "SELECT 1"
    # Windows line ends kept.
    assert rules.with_connection("-- connection: A\r\nSELECT 1", "B") == "-- connection: B\r\nSELECT 1"
    assert rules.with_connection("SELECT 1\r\nFROM t", "B") == "-- connection: B\r\nSELECT 1\r\nFROM t"
    with pytest.raises(ValueError):
        rules.with_connection("SELECT 1", "two\nlines")


def test_statements_are_split_outside_strings_and_comments() -> None:
    text = "-- connection: W\nSELECT ';' AS a;\n\n/* ; */ SELECT 2\nFROM t; -- done\n"
    found = rules.statements(text)
    assert [s.line for s in found] == [2, 4]
    assert found[0].text == "SELECT ';' AS a"
    assert found[1].text == "/* ; */ SELECT 2\nFROM t"
    assert found[1].end_line == 5
    assert rules.statements("-- only a comment\n") == []


def test_the_statement_under_the_cursor() -> None:
    text = "SELECT 1;\nSELECT 2\nFROM t;\n\nSELECT 3"

    def at(line: int) -> str:
        found = rules.statement_at(text, line)
        assert found is not None
        return found.text

    assert at(1) == "SELECT 1"
    assert at(3) == "SELECT 2\nFROM t"
    assert at(4) == "SELECT 2\nFROM t"  # a blank line between two: the one before it
    assert at(5) == "SELECT 3"
    assert rules.statement_at("", 1) is None


def test_run_file_takes_one_query() -> None:
    assert rules.to_run("-- connection: W\nSELECT 1;\n", None, None).text.strip().endswith("SELECT 1")
    with pytest.raises(rules.SqlFileError) as said:
        rules.to_run("SELECT 1;\nSELECT 2;", None, None)
    assert said.value.line == 2
    assert "2 statements" in str(said.value)
    with pytest.raises(rules.SqlFileError):
        rules.to_run("-- nothing\n", None, None)
    # Run selection: the selected text, else the statement at the line.
    assert rules.to_run("SELECT 1;\nSELECT 2;", None, 2).text.strip() == "SELECT 2"
    picked = rules.to_run("SELECT 1;\nSELECT 2;", "SELECT 2", 2)
    assert (picked.text, picked.line) == ("SELECT 2", 2)


def test_the_table_is_named_after_the_file() -> None:
    assert rules.table_name("/home/u/sales/scripts/orders_by_month.sql") == "orders_by_month"
    assert rules.table_name("C:\\work\\Orders by month.SQL") == "Orders_by_month"
    assert rules.table_name(None) == "query"
    assert rules.table_name("/x/.sql") == "query"
    assert len(rules.table_name("/x/" + "a" * 100 + ".sql")) == 64


def test_the_line_an_error_points_at() -> None:
    statement = rules.Statement("SELECT\n  amount,\n  nope\nFROM orders", 4, 7)
    assert rules.error_line('Binder Error: Referenced column "nope" not found', statement) == 6
    assert rules.error_line('Parser Error: syntax error at or near "FROM"\n\nLINE 3: ...', statement) == 6
    assert rules.error_line("something else", statement) == 4


def test_a_file_for_a_table() -> None:
    assert rules.file_for("orders_by_month", "SELECT 1", None) == "SELECT 1\n"
    assert rules.file_for("t", "SELECT 1", "Warehouse") == "-- connection: Warehouse\nSELECT 1\n"
    assert rules.file_name("Orders by month") == "Orders_by_month.sql"


def test_a_sql_file_is_a_document_of_the_scripts_page() -> None:
    assert notebooks.kind_of("/p/scripts/orders.sql") == "sql"
    assert workbench_pages.page_of_path("/p/scripts/orders.SQL") == "scripts"
    assert workbench_pages.kind_of_path("orders.sql") == "sql"
    assert workbench_pages.page_of_kind("sql") == "scripts"
    assert workbench_pages.wrong_page("sql", "notebooks") == "A SQL file opens on the Scripts page, not here."
    assert [".sql", "sql"] in workbench_pages.rules()["path_kinds"]
    assert workbench_pages.page_for_command(None, {}, "file.newSql") == "scripts"
    # The project's own document: listed, carried by Copy project to and Git, never a made file.
    listed = project_scope.documents([("scripts/orders.sql", 10, 1.0), ("data.py", 10, 1.0)])
    sql = next(d for d in listed if d["path"] == "scripts/orders.sql")
    assert (sql["kind"], sql["made"]) == ("sql", False)


def test_the_scripts_tree_lists_the_sql_files() -> None:
    from swissarmybench.domain import code_tree

    group = code_tree.sql_group(
        ["scripts/orders_by_month.sql", "a.sql", ".sab/x.sql", "load.py", "builds/b/q.sql"]
    )
    assert group is not None
    assert (group["id"], group["name"], group["kind"]) == ("sql", "SQL files", "sql")
    assert [f["path"] for f in group["files"]] == ["a.sql", "scripts/orders_by_month.sql"]
    assert code_tree.sql_group(["load.py"]) is None


def test_a_document_renamed_keeps_its_kind_and_folder() -> None:
    assert workbench_pages.renamed("/p/scripts/q.sql", "orders_by_month") == "/p/scripts/orders_by_month.sql"
    assert workbench_pages.renamed("C:\\p\\a.ipynb", "b.ipynb") == "C:\\p\\b.ipynb"
    assert workbench_pages.renamed("/p/load.py", " loader.py ") == "/p/loader.py"
    for bad in ("", "a/b", "..", ".hidden", "b.py"):
        with pytest.raises(ValueError):
            workbench_pages.renamed("/p/a.ipynb", bad)
    with pytest.raises(ValueError):
        workbench_pages.renamed("/p/a.ipynb", "a")  # its name already


# ===== the server: a run builds the table, a failure names its line, Edit in Scripts, a rename =====


def test_a_sql_file_run_builds_its_table_and_again_replaces_it(client: TestClient, tmp_path: Path) -> None:
    grid_id(push(client, "orders", ORDERS))
    file = tmp_path / "orders_by_month.sql"
    file.write_text("-- totals by month\nSELECT month, sum(amount) AS total\nFROM orders\nGROUP BY month\n")
    built = client.post("/scripts/sql/run", json={"path": str(file)}, headers=AUTH)
    assert built.status_code == 200, built.text
    said = built.json()
    assert (said["table"], said["rows"], said["connection"], said["line"]) == ("orders_by_month", 2, None, 2)
    grid = said["grid"]
    # The page's unsaved text wins over the file's; the same table replaced, in the same grid.
    again = client.post(
        "/scripts/sql/run",
        json={"path": str(file), "text": "SELECT * FROM orders WHERE amount > 6", "connection": ""},
        headers=AGENT,
    )
    assert again.status_code == 200, again.text
    assert (again.json()["rows"], again.json()["grid"]) == (2, grid)


def test_run_selection_runs_the_statement_at_the_line(client: TestClient) -> None:
    push(client, "orders", ORDERS)
    text = "SELECT * FROM orders;\n\nSELECT order_id\nFROM orders\nWHERE amount < 15;\n"
    said = client.post("/scripts/sql/run", json={"text": text, "line": 4, "table": "small"}, headers=AUTH)
    assert said.status_code == 200, said.text
    assert (said.json()["table"], said.json()["rows"], said.json()["line"]) == ("small", 2, 3)


def test_a_failure_names_the_file_line(client: TestClient) -> None:
    push(client, "orders", ORDERS)
    text = "-- totals\nSELECT\n  amount,\n  nope\nFROM orders\n"
    said = client.post("/scripts/sql/run", json={"text": text, "table": "broken"}, headers=AUTH)
    assert said.status_code == 400
    body = said.json()
    assert body["line"] == 4, body
    assert body["where"] == "line 4"
    assert "nope" in body["details"]
    two = client.post("/scripts/sql/run", json={"text": "SELECT 1;\nSELECT 2;"}, headers=AUTH)
    assert (two.status_code, two.json()["line"]) == (400, 2)


def test_edit_in_scripts_makes_the_tables_sql_file_once(client: TestClient) -> None:
    push(client, "orders", ORDERS)
    sql = "SELECT * FROM orders WHERE amount > 6"
    made = client.post("/datasets/big/query", json={"sql": sql}, headers=AUTH)
    assert made.status_code == 200, made.text
    first = client.post("/scripts/sql/for-table", json={"table": "big"}, headers=AGENT)
    assert first.status_code == 200, first.text
    path = Path(first.json()["path"])
    assert (path.name, first.json()["made"]) == ("big.sql", True)
    assert path.read_text() == sql + "\n"
    path.write_text("SELECT * FROM orders WHERE amount > 1\n")
    second = client.post("/scripts/sql/for-table", json={"table": "big"}, headers=AUTH).json()
    assert second["made"] is False
    assert path.read_text() == "SELECT * FROM orders WHERE amount > 1\n"  # the user's edits kept
    # Running it replaces the table it came from.
    ran = client.post("/scripts/sql/run", json={"path": str(path)}, headers=AUTH)
    assert (ran.status_code, ran.json()["table"], ran.json()["rows"]) == (200, "big", 3)
    # A table that did not come from a query has none to edit.
    assert client.post("/scripts/sql/for-table", json={"table": "orders"}, headers=AUTH).status_code == 403


def test_a_document_is_renamed_and_its_recent_entry_follows(client: TestClient, tmp_path: Path) -> None:
    file = tmp_path / "q.sql"
    file.write_text("SELECT 1\n")
    opened = client.post("/workbench/open", json={"path": str(file)}, headers=AUTH)
    assert (opened.json()["kind"], opened.json()["page"]) == ("sql", "scripts")
    said = client.post("/workbench/rename", json={"path": str(file), "to": "orders_by_month"}, headers=AGENT)
    assert said.status_code == 200, said.text
    assert said.json()["to"].endswith("orders_by_month.sql")
    assert (tmp_path / "orders_by_month.sql").read_text() == "SELECT 1\n"
    assert not file.exists()
    recent = [r["path"] for r in client.get("/workbench/home", headers=AUTH).json()["recent"]]
    assert said.json()["to"] in recent
    assert str(file) not in recent
    renamed = str(tmp_path / "orders_by_month.sql")
    assert (
        client.post(
            "/workbench/rename", json={"path": renamed, "to": "orders_by_month"}, headers=AUTH
        ).status_code
        == 400
    )
    (tmp_path / "c.sql").write_text("")
    assert (
        client.post("/workbench/rename", json={"path": renamed, "to": "c"}, headers=AUTH).status_code == 409
    )
