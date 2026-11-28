"""New file on the Scripts page (the owner, 2026-11-27: "turn the + new script on the scripts into a drop down
combo that asks what file type you wanna create. SQL python json etc. then scaffolds it for you"): each type's
starter (Python compiles; JSON, YAML, TOML and XML load; the SQL parses), a name's ending filled in and
checked, the folder inside the project, a taken name refused; the route and the agent's command."""

from __future__ import annotations

import ast
import importlib.util
import json
import tomllib
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pyarrow as pa
import pytest
import sqlglot
from starlette.testclient import TestClient

from swissarmybench.cli import commands
from swissarmybench.domain import new_files as rules
from swissarmybench.domain import notebooks, sql_files, structures, workbench_pages
from tests.conftest import AGENT, AUTH, make_client, push

ORDERS = pa.table({"order_id": [1, 2, 3], "amount": [10.0, 20.0, 5.0]})


def of(type_id: str) -> rules.FileType:
    return rules.type_of(type_id)


# ===== the starters =====


def test_the_python_starter_compiles_and_has_a_typed_main() -> None:
    text = rules.python_starter("load_orders.py")
    tree = ast.parse(text)
    compile(text, "load_orders.py", "exec")
    assert ast.get_docstring(tree, clean=True) == "load_orders: what this script does."
    assert "from __future__ import annotations\n" in text
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    assert main.name == "main" and isinstance(main.returns, ast.Constant) and main.returns.value is None
    assert text.rstrip().endswith('if __name__ == "__main__":\n    main()')
    assert rules.starter(of("python"), "load_orders.py") == text


def test_the_sql_starter_names_where_it_runs_and_parses() -> None:
    over_tables = rules.sql_starter(None, "orders")
    assert over_tables.splitlines()[0] == "-- connection:"
    assert sql_files.connection_of(over_tables) is None  # DuckDB over the open tables
    parsed = [s for s in sqlglot.parse(over_tables, read="duckdb") if s is not None]
    assert len(parsed) == 1
    assert parsed[0].sql(dialect="duckdb", comments=False) == 'SELECT * FROM "orders" LIMIT 100'
    assert [s.text for s in sql_files.statements(over_tables)] == ['SELECT *\nFROM "orders"\nLIMIT 100']
    # A table's name is quoted as DuckDB quotes one.
    assert 'FROM "odd ""name"""' in rules.sql_starter(None, 'odd "name"')
    # No table open: a commented hint, nothing to run yet.
    hint = rules.sql_starter()
    assert sql_files.statements(hint) == [] and "No table is open yet" in hint
    assert [s for s in sqlglot.parse(hint, read="duckdb") if s is not None] == []
    # A connection: its header line, and a hint in its own SQL (an open table is not the connection's).
    on = rules.sql_starter("Finance Captive", "orders")
    assert on.splitlines()[0] == "-- connection: Finance Captive"
    assert sql_files.connection_of(on) == "Finance Captive" and sql_files.statements(on) == []
    assert rules.starter(of("sql"), "q.sql", {"connection": "Finance Captive"}) == on
    with pytest.raises(ValueError):
        rules.sql_starter("two\nlines")


def test_the_structure_starters_load_as_empty_documents() -> None:
    assert json.loads(rules.json_starter()) == {}
    assert json.loads(rules.yaml_starter()) == {}  # a flow mapping: YAML's and JSON's alike
    assert tomllib.loads(rules.toml_starter("settings.toml")) == {}
    root = ElementTree.fromstring(rules.xml_starter().encode())  # noqa: S314 (our own starter's text)
    assert root.tag == "root" and len(root) == 0
    # And as the Structures tab reads them.
    for fmt, name in (("json", "data.json"), ("toml", "settings.toml"), ("xml", "data.xml")):
        kind = of(fmt)
        assert structures.format_of(name) == fmt
        structures.parse(rules.starter(kind, name), fmt)
        assert workbench_pages.is_structure_path(f"structures/{name}")


def test_the_yaml_starter_loads_with_pyyaml() -> None:
    yaml = pytest.importorskip("yaml")
    assert yaml.safe_load(rules.yaml_starter()) == {}
    structures.parse(rules.starter(of("yaml"), "settings.yaml"), "yaml")


def test_markdown_text_and_a_notebook() -> None:
    assert rules.markdown_starter("month end.md") == "# month end\n"
    assert rules.text_starter() == ""
    cells, _ = notebooks.read_document(rules.notebook_starter())
    assert cells == [] and json.loads(rules.notebook_starter())["nbformat"] == 4
    assert rules.starter(of("markdown"), "notes.md") == "# notes\n"
    assert rules.starter(of("text"), "notes.txt") == ""


def test_every_type_has_a_starter_and_opens_on_its_page() -> None:
    for kind in rules.TYPES:
        name = rules.named(kind, kind.suggested)
        assert name == kind.suggested + kind.ending
        if not kind.maker:  # a type its own maker writes (Import Power BI queries…) has no starter text
            assert isinstance(rules.starter(kind, name), str)
        home = "scripts" if kind.kind == "structure" else workbench_pages.page_of_path(name)
        assert home == kind.page, kind.id
    assert of("notebook").page == "notebooks"  # the two-pages rule
    assert [t["id"] for t in rules.types()][:2] == ["python", "sql"]
    assert rules.type_of(None).id == "python" and rules.type_of(" SQL ").id == "sql"
    with pytest.raises(rules.NewFileError, match="type is one of"):
        rules.type_of("cobol")


# ===== the name, the folder, a taken name =====


def test_a_names_ending_is_filled_in_and_checked() -> None:
    assert rules.named(of("sql"), "orders_by_month") == "orders_by_month.sql"
    assert rules.named(of("sql"), " orders by month.SQL ") == "orders by month.SQL"
    assert rules.named(of("yaml"), "settings.yml") == "settings.yml"
    assert rules.named(of("yaml"), "settings") == "settings.yaml"
    assert rules.named(of("python"), "load_orders") == "load_orders.py"
    with pytest.raises(rules.NewFileError, match="names a JSON file"):
        rules.named(of("sql"), "orders.json")
    with pytest.raises(rules.NewFileError, match="not a module's name"):
        rules.named(of("python"), "load orders")
    with pytest.raises(rules.NewFileError, match="keeps for its own"):
        rules.named(of("json"), "sales.canvas.json")
    for bad in ("", "  ", ".hidden", "a/b", "a\\b", "what?", ".sql"):
        with pytest.raises(rules.NewFileError):
            rules.named(of("sql"), bad)
    with pytest.raises(rules.NewFileError, match="at most"):
        rules.named(of("text"), "n" * 200)


def test_the_folder_stays_inside_the_project() -> None:
    assert rules.folder_of(of("python"), None) == "scripts"
    assert rules.folder_of(of("json"), None) == "structures"
    assert rules.folder_of(of("notebook"), None) == ""
    assert rules.folder_of(of("sql"), "") == ""  # the project's top, said
    assert rules.folder_of(of("sql"), " scripts\\reports/ ") == "scripts/reports"
    for bad in ("..", "scripts/../..", "/etc", "C:\\made-up", ".sab", "scripts/.hidden"):
        with pytest.raises(rules.NewFileError):
            rules.folder_of(of("sql"), bad)
    assert rules.folders(["scripts/etl/load.py", "functions.py", ".venv/x.py"]) == [
        "",
        "docs",
        "docs/decisions",
        "docs/diagrams",
        "scripts",
        "scripts/etl",
        "structures",
    ]


def test_a_taken_name_is_refused_in_one_sentence() -> None:
    there = {"scripts/orders.sql"}
    assert rules.place(of("sql"), "returns", None, there.__contains__) == "scripts/returns.sql"
    assert rules.place(of("markdown"), "notes", "", there.__contains__) == "notes.md"
    with pytest.raises(rules.NameTaken) as refused:
        rules.place(of("sql"), "orders", "scripts", there.__contains__)
    assert str(refused.value) == "scripts/orders.sql is there already: pick another name."


# ===== the route and the command =====


def ok(answer: Any) -> Any:
    assert answer.status_code == 200, answer.text
    return answer.json()


def project(client: TestClient, tmp_path: Path) -> Path:
    state = ok(client.post("/project/new", json={"path": str(tmp_path / "work" / "shop")}, headers=AUTH))
    return Path(state.get("folder") or state["project"]["folder"])


def test_new_file_writes_each_types_starter_into_the_project(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        # No project open: a new file still needs its folder (tests/test_named_files.py has the rest).
        refused = client.post("/scripts/files/new", json={"type": "sql", "name": "q"}, headers=AUTH)
        assert refused.status_code == 400 and "No project is open" in refused.json()["error"]
        assert ok(client.get("/scripts/files/new", headers=AUTH))["project"] is False
        folder = project(client, tmp_path)
        options = ok(client.get("/scripts/files/new", headers=AUTH))
        assert options["project"] is True and options["default"] == "python"
        assert [t["id"] for t in options["types"]] == [t.id for t in rules.TYPES]
        assert {"", "scripts", "structures"} <= set(options["folders"])

        # SQL with no table open: the hint; with one open: its first rows; on a connection: its header.
        made = ok(client.post("/scripts/files/new", json={"type": "sql", "name": "first"}, headers=AUTH))
        assert made["relative"] == "scripts/first.sql" and made["kind"] == "sql" and made["page"] == "scripts"
        assert Path(made["path"]) == folder / "scripts" / "first.sql"
        assert "No table is open yet" in (folder / "scripts" / "first.sql").read_text(encoding="utf-8")
        push(client, "orders", ORDERS)
        ok(client.post("/scripts/files/new", json={"type": "sql", "name": "orders_first"}, headers=AUTH))
        text = (folder / "scripts" / "orders_first.sql").read_text(encoding="utf-8")
        assert text.startswith("-- connection:\n") and 'FROM "orders"\nLIMIT 100;' in text
        ran = ok(
            client.post(
                "/scripts/sql/run", json={"path": made["path"][:-9] + "orders_first.sql"}, headers=AUTH
            )
        )
        assert ran["table"] == "orders_first" and ran["connection"] is None
        on = {"type": "sql", "name": "books", "folder": "scripts/finance", "connection": "Finance Captive"}
        ok(client.post("/scripts/files/new", json=on, headers=AUTH))
        books = (folder / "scripts" / "finance" / "books.sql").read_text(encoding="utf-8")
        assert sql_files.connection_of(books) == "Finance Captive"

        # The dialog's live check: where it would go, nothing written.
        checked = {"type": "sql", "name": "later", "check": True}
        would = ok(client.post("/scripts/files/new", json=checked, headers=AUTH))
        assert would["relative"] == "scripts/later.sql" and would["made"] is False
        assert not (folder / "scripts" / "later.sql").exists()

        # A taken name: one plain sentence, nothing overwritten.
        taken = client.post("/scripts/files/new", json={"type": "sql", "name": "first.sql"}, headers=AUTH)
        assert taken.status_code == 409
        assert taken.json()["error"] == "scripts/first.sql is there already: pick another name."

        # Python (the default type), the structures, Markdown, text and a notebook.
        script = ok(client.post("/scripts/files/new", json={"name": "load_orders"}, headers=AUTH))
        assert script["type"] == "python" and script["relative"] == "scripts/load_orders.py"
        compile((folder / "scripts" / "load_orders.py").read_text(encoding="utf-8"), "load_orders.py", "exec")
        tree = ok(client.get("/scripts/tree", headers=AUTH))
        listed = {f["path"] for g in tree["groups"] for f in g["files"]}
        assert {"scripts/load_orders.py", "scripts/first.sql", "README.md"} <= listed, sorted(listed)
        for kind, name in (("json", "data"), ("yaml", "settings"), ("toml", "settings"), ("xml", "data")):
            made = ok(client.post("/scripts/files/new", json={"type": kind, "name": name}, headers=AUTH))
            assert made["kind"] == "structure" and made["relative"].startswith("structures/")
            if kind == "yaml" and importlib.util.find_spec("yaml") is None:
                continue  # PyYAML is the project's own: the Structures tab says so
            opened = ok(client.post("/structures/open", json={"path": made["path"]}, headers=AUTH))
            assert opened.get("text_error") is None, opened
        notes = ok(
            client.post("/scripts/files/new", json={"type": "markdown", "name": "notes"}, headers=AUTH)
        )
        assert notes["relative"] == "notes.md" and notes["kind"] == "text"
        opened = ok(client.post("/workbench/open", json={"path": notes["path"]}, headers=AUTH))
        assert opened["kind"] == "text" and opened["text"] == "# notes\n"
        saved = {
            "path": notes["path"],
            "text": "# notes\n\nA made-up line.\n",
            "modified": opened["modified"],
        }
        ok(client.post("/workbench/save", json=saved, headers=AUTH))
        assert (folder / "notes.md").read_text(encoding="utf-8").endswith("A made-up line.\n")
        plain = ok(client.post("/scripts/files/new", json={"type": "text", "name": "todo"}, headers=AUTH))
        assert (folder / "todo.txt").read_text(encoding="utf-8") == "" and plain["page"] == "scripts"
        book = ok(
            client.post("/scripts/files/new", json={"type": "notebook", "name": "explore"}, headers=AUTH)
        )
        assert book["page"] == "notebooks" and book["relative"] == "explore.ipynb"
        assert ok(client.post("/workbench/open", json={"path": book["path"]}, headers=AUTH))["cells"] == []

        # Never outside the project, never a wrong ending; the agent may make one too.
        for body in (
            {"type": "sql", "name": "out", "folder": "../elsewhere"},
            {"type": "sql", "name": "orders.json"},
            {"type": "cobol", "name": "x"},
            {"type": "python", "name": "not a module"},
        ):
            assert client.post("/scripts/files/new", json=body, headers=AUTH).status_code in (400, 422), body
        assert not (tmp_path / "work" / "elsewhere").exists()
        agent = ok(
            client.post("/scripts/files/new", json={"type": "json", "name": "agent_made"}, headers=AGENT)
        )
        assert agent["relative"] == "structures/agent_made.json"


def test_the_agents_command_makes_a_file_of_a_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str, Any]] = []

    def call(method: str, path: str, body: Any = None, **_: Any) -> Any:
        sent.append((method, path, body))
        return {"ok": True}

    monkeypatch.setattr("swissarmybench.cli.api.call", call)
    run = commands.REGISTRY["workbench_file"].run
    run(
        {
            "action": "new",
            "type": "sql",
            "to": "orders_by_month",
            "path": "scripts",
            "connection": "Warehouse",
        }
    )
    run({"action": "new", "to": "load_orders"})
    run({"action": "types"})
    # An old call with no name: refused in one sentence, nothing sent.
    assert run({"action": "new", "type": "sql"}) == {
        "error": "Give the file a name (to): a new file is made only once it is named."
    }
    assert sent == [
        (
            "POST",
            "/scripts/files/new",
            {"type": "sql", "name": "orders_by_month", "folder": "scripts", "connection": "Warehouse"},
        ),
        (
            "POST",
            "/scripts/files/new",
            {"type": None, "name": "load_orders", "folder": None, "connection": None},
        ),
        ("GET", "/scripts/files/new", None),
    ]
    names = {a.name for a in commands.REGISTRY["workbench_file"].args}
    assert {"type", "connection"} <= names
