"""The project scaffold (domain/scaffold.py, services/scaffold.py; Plans/adapter.plan.md "The exported
project: the fewest files that build the app", "Who writes what", "The sandbox lives in its own files").

The core files grow as the user works and shrink when a thing goes: adapter.py (the app's own bytes),
connections.py (a section per connection the project uses, names only), README.md's Variables block (never
a value), data.py's structures read as grids; the sandbox mirror (sandbox_data.py, sandbox_connections.py,
sandbox/) beside them, moved once out of .sab/sandbox/, removed together and nothing else. A made file edited
by hand is kept (Compare, Take the new one). An exported Streamlit app is the fewest files and runs alone in a
fresh folder (AppTest, in a Python with streamlit, duckdb and pyarrow: SWISSARMYBENCH_STREAMLIT_PYTHON).
Made-up data only."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest

from swissarmybench.adapters import adapter as the_adapter
from swissarmybench.adapters.sandbox import SandboxFiles, move_old
from swissarmybench.cli import commands
from swissarmybench.domain import sandbox as sandbox_rules
from swissarmybench.domain import scaffold as rules
from swissarmybench.server.app import create_app
from swissarmybench.settings import Settings
from tests.conftest import TOKEN
from tests.fake_keyring import memory_keyring
from tests.live_server import running
from tests.test_actions import ask

KEYRING_SECRET = "made-up-keyring-s3cret"
PLAIN_VALUE = "made-up-plain-value-41"
PYTHON = os.environ.get("SWISSARMYBENCH_STREAMLIT_PYTHON")
HERE = "import os, sys\nsys.path.insert(0, os.getcwd())\n"  # `python -I` leaves the folder off the path

# ===== the rules =====


def test_connections_are_marked_sections_with_names_only() -> None:
    text = rules.marked(
        [
            rules.Section("Warehouse", "def connect_warehouse():\n    return 1\n", ("WAREHOUSE_PASSWORD",)),
            rules.Section("finance-vault", "def vault_finance():\n    return 2\n", (), "key vault"),
        ]
    )
    assert rules.section_names(text) == ["Warehouse", "finance-vault"]
    assert "# Its variables (set where it runs, never here): WAREHOUSE_PASSWORD" in text
    assert text.index("# ===== end of Warehouse =====") < text.index("# ===== key vault: finance-vault =====")
    settings = (
        "SETTINGS: dict[str, str | None] = {\n"
        f"    'SHOP_HOST': {PLAIN_VALUE!r},  # a plain value\n"
        "    'SHOP_PASSWORD': None,  # this computer's keyring\n"
        "}\n"
        f"OTHER = {PLAIN_VALUE!r}\n"
    )
    stripped = rules.without_values(settings)
    assert "'SHOP_HOST': None,  # a plain value" in stripped
    assert stripped.count(PLAIN_VALUE) == 1  # only the block's values: the rest is left alone
    made = rules.connections_py(text)
    compile(made, "connections.py", "exec")
    assert made.startswith('"""connections.py') and "adapter.use(_source)" in made


def test_the_readme_variables_block_is_the_only_part_the_app_writes() -> None:
    mine = "# Shop\n\nMy own notes, kept byte for byte.\r\n\nMore of mine.\n"
    one = [rules.Variable("SHOP_PASSWORD", "This computer's keyring", ("connection Shop",))]
    added = rules.with_variables(mine, one)
    assert added is not None and added.startswith(mine.rstrip("\n"))
    assert "| `SHOP_PASSWORD` | This computer's keyring | connection Shop |" in added
    two = [*one, rules.Variable("REGION", "Plain value", ("data.ipynb",))]
    again = rules.with_variables(added, two)
    assert again is not None and again.count(rules.VARIABLES_OPEN) == 1 and "`REGION`" in again
    assert rules.with_variables(again, []) == mine  # the last one gone: the block goes, the rest as it was
    assert rules.with_variables(None, []) is None  # nothing to write
    assert rules.with_variables(None, one, "Shop").startswith("# Shop\n")  # type: ignore[union-attr]


def test_the_sandbox_mirror_names_tables_never_values_or_paths() -> None:
    tables: dict[str, dict[str, Any]] = {
        "customers": {
            "source": {"kind": "connection", "connection": "Shop", "table": "customers", "sql": "SELECT 1"},
            "client": {"connection": "Shop", "kind": "sql", "dialect": "sqlite"},
            "key": ["customer_id"],
        },
        "notes": {"source": {"kind": "file", "file": "/home/someone/private/notes.csv"}, "client": {}},
    }
    data = rules.sandbox_data_py(tables, "2026-11-22T10:00:00Z", ["before the demo", "after"])
    assert data is not None
    space: dict[str, Any] = {}
    exec(compile(data, "sandbox_data.py", "exec"), space)  # noqa: S102 (the text made above)
    assert space["TABLES"]["customers"] == {
        "as": "Shop",
        "from": {"connection": "Shop", "kind": "connection", "table": "customers"},
        "key": ["customer_id"],
    }
    assert space["TABLES"]["notes"]["from"] == {"file": "notes.csv", "kind": "file"}
    assert space["CHECKPOINTS"] == ["after", "before the demo"] and space["FOLDER"] == "sandbox"
    assert "/home/someone" not in data and "SELECT 1" not in data
    mirror = rules.sandbox_connections_py(tables)
    assert mirror is not None and rules.section_names(mirror) == ["Shop"]
    assert "import connections" not in mirror and "secret(" not in mirror  # never the app's guts
    compile(mirror, "sandbox_connections.py", "exec")
    assert rules.sandbox_data_py({}, None, []) is None and rules.sandbox_connections_py({}) is None


def test_a_made_file_edited_by_hand_is_kept_and_taken_only_when_asked() -> None:
    app_text, older, hand = "# made v2\n", "# made v1\n", "# mine\n"
    written = {"connections.py": rules.digest(older)}
    plan = rules.plan({"connections.py": app_text}, {"connections.py": older}, written)
    assert plan.by("write") == ["connections.py"]  # what the app wrote: updated
    plan = rules.plan({"connections.py": app_text}, {"connections.py": hand}, written)
    assert plan.by("edited") == ["connections.py"]  # edited by hand: kept
    plan = rules.plan({"connections.py": None}, {"connections.py": hand}, written)
    assert plan.by("edited") == ["connections.py"]  # never removed either
    plan = rules.plan({"connections.py": None}, {"connections.py": older}, written)
    assert plan.by("remove") == ["connections.py"]  # nothing uses it now: its section, its file, go
    plan = rules.plan(
        {"connections.py": app_text}, {"connections.py": hand}, written, take=["connections.py"]
    )
    assert plan.by("write") == ["connections.py"]  # Take the new one
    plan = rules.plan(
        {"connections.py": app_text}, {"connections.py": older}, written, hand=["connections.py"]
    )
    assert plan.by("edited") == ["connections.py"]  # marked edited by the Scripts page's rule
    assert rules.plan({"adapter.py": None}, {"adapter.py": None}, {}).changes[0].action == "none"


def test_a_structure_read_as_a_grid_has_its_line_in_data_py(tmp_path: Path) -> None:
    (tmp_path / "structures").mkdir()
    feed = {"orders": [{"id": 1, "customer": {"region": "North"}}, {"id": 2, "customer": {"region": "West"}}]}
    (tmp_path / "structures" / "feed.json").write_text(json.dumps(feed), encoding="utf-8")
    base = '"""data.py"""\n\nimport duckdb\n'
    made = rules.with_structures(base, [rules.StructureGrid("feed", "structures/feed.json", "$.orders")])
    assert (
        made.startswith(base.rstrip("\n")) and "feed = _records('structures/feed.json', '$.orders')" in made
    )
    assert rules.with_structures(made, []) == base  # taken out again, the rest as it was
    (tmp_path / "data.py").write_text(made, encoding="utf-8")
    done = subprocess.run(  # noqa: S603 (this Python, the test's own script)
        [sys.executable, "-I", "-c", HERE + "import data, json; print(json.dumps(data.feed.to_dict('records')))"],  # noqa: E501
        cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == [
        {"id": 1, "customer.region": "North"},
        {"id": 2, "customer.region": "West"},
    ]


def _read_by_data_py(folder: Path, names: str) -> Any:
    done = subprocess.run(  # noqa: S603 (this Python, the test's own script)
        [sys.executable, "-I", "-c", HERE + f"import data, json; print(json.dumps([{names}], default=str))"],
        cwd=folder, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_yaml_xml_and_toml_structures_have_their_lines_too(tmp_path: Path) -> None:
    """The sweep, 2026-11-22: only a JSON structure got its data.py line. Each format is read as the app
    reads it (XML's attributes as "@name", TOML's dates as text), with the standard library but YAML."""
    folder = tmp_path / "structures"
    folder.mkdir()
    (folder / "rates.toml").write_text(
        '[[rates]]\ncode = "EUR"\nrate = 1.08\nsince = 2026-01-05\n\n[[rates]]\ncode = "GBP"\nrate = 1.27\n'
        "since = 2026-02-01\n",
        encoding="utf-8",
    )
    (folder / "catalog.xml").write_text(
        '<catalog><item sku="A1"><name>Lamp</name><price>12.5</price></item>'
        '<item sku="B2"><name>Desk</name><price>140</price></item></catalog>',
        encoding="utf-8",
    )
    (folder / "gates.yaml").write_text("gates:\n  - name: review\n    limit: 500\n", encoding="utf-8")
    grids = [
        rules.StructureGrid("catalog", "structures/catalog.xml", "$.catalog.item"),
        rules.StructureGrid("rates", "structures/rates.toml", "$.rates"),
    ]
    (tmp_path / "data.py").write_text(rules.with_structures('"""data.py"""\n', grids), encoding="utf-8")
    assert _read_by_data_py(tmp_path, "data.catalog.to_dict('records'), data.rates.to_dict('records')") == [
        [{"@sku": "A1", "name": "Lamp", "price": "12.5"}, {"@sku": "B2", "name": "Desk", "price": "140"}],
        [
            {"code": "EUR", "rate": 1.08, "since": "2026-01-05"},
            {"code": "GBP", "rate": 1.27, "since": "2026-02-01"},
        ],
    ]
    # YAML is PyYAML's: without it the line says what to install; with it (stood in for here) it reads.
    yaml_grid = [rules.StructureGrid("gates", "structures/gates.yaml", "$.gates")]
    (tmp_path / "data.py").write_text(rules.with_structures('"""data.py"""\n', yaml_grid), encoding="utf-8")
    missing = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", HERE + "import data"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    if "pip install pyyaml" in missing.stderr:  # this Python has no PyYAML: a stand-in that reads this file
        (tmp_path / "yaml.py").write_text(
            "def safe_load_all(text):\n    return [{'gates': [{'name': 'review', 'limit': 500}]}]\n",
            encoding="utf-8",
        )
    assert _read_by_data_py(tmp_path, "data.gates.to_dict('records')") == [[{"name": "review", "limit": 500}]]
    # XML that declares an entity is refused here as in the app.
    (folder / "catalog.xml").write_text('<!DOCTYPE x [<!ENTITY a "b">]><catalog/>', encoding="utf-8")
    (tmp_path / "data.py").write_text(rules.with_structures('"""data.py"""\n', grids[:1]), encoding="utf-8")
    refused = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", HERE + "import data"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert refused.returncode != 0 and "DOCTYPE" in refused.stderr


def test_data_py_written_again_from_data_ipynb_keeps_its_structures(tmp_path: Path) -> None:
    """The sweep, 2026-11-22: Export data.py (data.ipynb's own write) dropped the structures' part until
    the scaffold's next refresh. The part is carried over as it stands."""
    grids = [rules.StructureGrid("rates", "structures/rates.toml", "$.rates")]
    old = rules.with_structures('"""data.py"""\n\norders = 1\n', grids)
    new = '"""data.py"""\n\norders = 2\n'
    kept = rules.keeping_structures(old, new)
    assert kept == rules.with_structures(new, grids) and "orders = 2" in kept
    assert rules.keeping_structures(new, new) == new and rules.keeping_structures(None, new) == new


# ===== the sandbox's move and its removal =====


def test_an_older_projects_sandbox_moves_once_and_is_checked(tmp_path: Path) -> None:
    old = tmp_path / ".sab" / "sandbox"
    (old / "checkpoints").mkdir(parents=True)
    with duckdb.connect(str(old / "sandbox.duckdb")) as made:
        made.execute("CREATE TABLE orders AS SELECT 1 AS id, 'North' AS region")
    (old / "sandbox.json").write_text('{"format": 1, "tables": {}}\n', encoding="utf-8")
    (old / "checkpoints" / "before.duckdb").write_bytes(b"made-up")
    (tmp_path / ".gitignore").write_text(".sab/data/\n.sab/sandbox/\n", encoding="utf-8")
    files = SandboxFiles(str(tmp_path))
    assert files.moved and not old.exists()
    assert (tmp_path / "sandbox" / "checkpoints" / "before.duckdb").read_bytes() == b"made-up"
    assert files.table_names() == ["orders"]
    assert "\nsandbox/\n" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert not SandboxFiles(str(tmp_path)).moved  # once
    # A sandbox/ the user already has is never mixed with it: the old folder stays where it is.
    other = tmp_path.parent / (tmp_path.name + "_other")
    (other / ".sab" / "sandbox").mkdir(parents=True)
    (other / ".sab" / "sandbox" / "sandbox.json").write_text("{}", encoding="utf-8")
    (other / "sandbox").mkdir()
    (other / "sandbox" / "mine.txt").write_text("the user's own", encoding="utf-8")
    assert not move_old(other) and (other / ".sab" / "sandbox" / "sandbox.json").is_file()
    # Remove the sandbox: its folder and its two files, nothing else.
    for name in (sandbox_rules.DATA_FILE, sandbox_rules.CONNECTIONS_FILE, "API.py", "connections.py"):
        (tmp_path / name).write_text("# made-up\n", encoding="utf-8")
    removed = files.drop_all()
    assert removed == ["sandbox/", "sandbox_data.py", "sandbox_connections.py"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [".gitignore", ".sab", "API.py", "connections.py"]


# ===== through the app =====


@pytest.fixture
def shop(tmp_path: Path) -> Iterator[tuple[int, Path, Path]]:
    """A running app, a made-up SQLite connection Shop (its password in the keyring) and a project."""
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute("CREATE TABLE customers (customer_id INTEGER, city TEXT)")
        made_up.executemany(
            "INSERT INTO customers VALUES (?, ?)", [(1, "Springfield"), (2, "Shelbyville"), (3, "Ogdenville")]
        )
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        'assert secret("password")\n'
        f'path = Path(r"{database}")\n'
        "conn = sqlite3.connect(path)\n"
    )
    settings = Settings(
        state_dir=tmp_path / "state",
        export_dir=tmp_path / "exports",
        auto_load_catalogs=False,
        projects_dir=tmp_path / "projects",
        workbench_dir=tmp_path / "wb",
    )
    with memory_keyring(), running(lambda port: create_app(port, TOKEN, settings)) as (port, _server):
        connection = {
            "name": "Shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code,
            "secrets": {"password": KEYRING_SECRET},
        }  # fmt: skip
        ask(port, "POST", "/connections", connection)
        folder = tmp_path / "shop"
        ask(port, "POST", "/project/new", {"path": str(folder)})
        yield port, folder, database


SQL_CELL: dict[str, Any] = {"cell_type": "code", "metadata": {}, "outputs": [], "execution_count": None,
            "source": ["%%sql Shop\n", "SELECT * FROM customers"]}  # fmt: skip


def _use_shop(folder: Path, on: bool) -> None:
    notebook = json.loads((folder / "data.ipynb").read_text(encoding="utf-8"))
    cells = [c for c in notebook["cells"] if "%%sql Shop" not in "".join(c.get("source") or [])]
    notebook["cells"] = [*cells, SQL_CELL] if on else cells
    (folder / "data.ipynb").write_text(json.dumps(notebook, indent=1), encoding="utf-8")


def _secret_free(folder: Path) -> None:
    for file in folder.rglob("*"):
        if file.is_file() and file.suffix in (".py", ".md", ".json"):
            assert KEYRING_SECRET not in file.read_text(encoding="utf-8", errors="replace"), file


def test_the_scaffold_grows_with_a_connection_and_shrinks_when_it_goes(
    shop: tuple[int, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, folder, _ = shop
    # The agent's command through this server (its own door, as the agent: no Allow needed for these).
    monkeypatch.setattr(
        commands.api,  # type: ignore[attr-defined]
        "call",
        lambda method, path, body=None: ask(port, method, path, body, True),
    )
    before = sorted(p.name for p in folder.iterdir())
    status = ask(port, "GET", "/project/scaffold")
    assert status["to_write"] == [] and status["connections"] == []  # nothing used: nothing written
    first = ask(port, "POST", "/project/scaffold", {})
    assert first["written"] == [], first
    assert sorted(p.name for p in folder.iterdir()) == before  # never all at once at New project
    _use_shop(folder, True)
    done = ask(port, "POST", "/project/scaffold", {})
    # (Written by this call, or by the refresh the notices start a moment after: the files are what count.)
    assert done["connections"] == ["Shop"] and done["kept"] == []
    assert (folder / "adapter.py").read_bytes() == Path(the_adapter.__file__).read_bytes()  # the same bytes
    text = (folder / "connections.py").read_text(encoding="utf-8")
    assert rules.section_names(text) == ["Shop"] and "SHOP_PASSWORD" in text
    readme = (folder / "README.md").read_text(encoding="utf-8")
    assert "| `SHOP_PASSWORD` |" in readme and "connection Shop" in readme
    _secret_free(folder)
    assert ask(port, "POST", "/project/scaffold", {})["written"] == []  # nothing changed: no byte written
    # Edited by hand: kept, offered as Compare / Take the new one (the agent's command, the same calls).
    (folder / "connections.py").write_text(text + "\n# my own line\n", encoding="utf-8")
    kept = commands.REGISTRY["project_scaffold"].run({"action": "status"})
    assert [k["file"] for k in kept["kept"]] == ["connections.py"] and "# my own line" in kept["kept"][0][
        "yours"
    ]
    taken = commands.REGISTRY["project_scaffold"].run({"action": "take", "file": "connections.py"})
    assert "connections.py" in taken["written"]
    assert (folder / "connections.py").read_text(encoding="utf-8") == text
    # The connection no longer used: its section, its file and its variable go; adapter.py stays only while
    # something reads through it (API.py's endpoints, the sandbox).
    _use_shop(folder, False)
    gone = ask(port, "POST", "/project/scaffold", {})
    assert gone["connections"] == [] and not (folder / "adapter.py").exists()
    assert not (folder / "connections.py").exists() and "SHOP_PASSWORD" not in (
        folder / "README.md"
    ).read_text(encoding="utf-8")


def test_a_toml_structure_opened_as_a_grid_has_its_line_and_export_data_keeps_it(
    shop: tuple[int, Path, Path],
) -> None:
    """The sweep, 2026-11-22: through the app. A TOML structure's grid gets its data.py line (only JSON
    did), and data.ipynb's own write of data.py (Export data.py) leaves the line where it is."""
    port, folder, _ = shop
    (folder / "structures").mkdir()
    rates = folder / "structures" / "rates.toml"
    rates.write_text('[[rates]]\ncode = "EUR"\nrate = 1.08\n', encoding="utf-8")
    opened = ask(port, "POST", "/structures/open", {"path": str(rates)})
    ask(port, "POST", f"/structures/{opened['id']}/grid", {"path": "$.rates", "name": "rates"})
    ask(port, "POST", "/project/scaffold", {})
    line = "rates = _records('structures/rates.toml', '$.rates')"
    assert line in (folder / "data.py").read_text(encoding="utf-8")
    ask(port, "POST", "/projects/export-data", {"folder": str(folder), "replace": True})
    assert line in (folder / "data.py").read_text(encoding="utf-8")
    assert ask(port, "POST", "/project/scaffold", {})["written"] == []  # nothing to put back


def test_the_sandbox_mirror_grows_beside_the_app_and_goes_with_remove(shop: tuple[int, Path, Path]) -> None:
    port, folder, _ = shop
    ask(port, "POST", "/sandbox/tables", {"from": "connection", "connection": "Shop", "table": "customers"})
    assert (folder / "sandbox" / "sandbox.duckdb").is_file() and not (folder / ".sab" / "sandbox").exists()
    ask(port, "POST", "/sandbox/checkpoints", {"name": "first"})
    ask(port, "POST", "/project/scaffold", {})
    assert all((folder / f).is_file() for f in ("sandbox_data.py", "sandbox_connections.py", "adapter.py"))
    data = (folder / "sandbox_data.py").read_text(encoding="utf-8")
    assert "'customers'" in data and "'first'" in data and "Springfield" not in data
    mirror = (folder / "sandbox_connections.py").read_text(encoding="utf-8")
    assert rules.section_names(mirror) == ["Shop"] and "sqlite3" not in mirror  # never the real code
    assert not (folder / "connections.py").exists()  # the app's files never name the sandbox
    _secret_free(folder)
    # The mirror runs the project's adapter on the sandbox alone, with no app (the project closed in it:
    # DuckDB lets one process at a time hold the file).
    ask(port, "POST", "/project/close", {})
    script = HERE + (
        "import json, sandbox_connections, adapter\n"
        "reader, _ = adapter.read('Shop', 'customers')\n"
        "print(json.dumps(sorted(reader.read_all().column('city').to_pylist())))\n"
    )
    ran = subprocess.run(  # noqa: S603 (this Python, the test's own script)
        [sys.executable, "-I", "-c", script], cwd=folder, capture_output=True, text=True, timeout=120,
        check=False,
    )  # fmt: skip
    assert ran.returncode == 0, ran.stderr
    assert json.loads(ran.stdout) == ["Ogdenville", "Shelbyville", "Springfield"]
    # Remove the sandbox (the agent's waits for Allow; the user's here): the three, nothing else.
    ask(port, "POST", "/project/open", {"folder": str(folder)})
    left = sorted(p.name for p in folder.iterdir() if not p.name.startswith("sandbox"))
    removed = ask(port, "POST", "/sandbox/drop", {})
    assert removed["removed"] == ["sandbox/", "sandbox_data.py", "sandbox_connections.py"]
    assert sorted(p.name for p in folder.iterdir()) == left


needs_streamlit = pytest.mark.skipif(not PYTHON, reason="SWISSARMYBENCH_STREAMLIT_PYTHON names no Python")

RUN_APP = textwrap.dedent(
    """
    import json, os, sys
    sys.path.insert(0, os.getcwd())
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    print("SAB-RUN " + json.dumps({
        "exceptions": [str(e.value)[:500] for e in at.exception],
        "said": [str(e.value)[:500] for e in at.error] + [str(w.value)[:500] for w in at.warning],
        "frames": [f.value.to_dict(orient="records") for f in at.dataframe],
    }, default=str))
    """
)


@needs_streamlit
def test_an_exported_app_is_the_fewest_files_and_runs_alone(
    shop: tuple[int, Path, Path], tmp_path: Path
) -> None:
    port, folder, _ = shop
    canvas = ask(port, "POST", "/streamlit/canvases", {"name": "Shop", "folder": str(folder)})["canvas"]
    path = f"/streamlit/canvases/{canvas}/command"
    ask(port, "POST", path, {"kind": "add_container", "x": 0, "y": 0, "w": 900, "h": 600})
    values = {"table_name": "[Shop].customers"}
    ask(
        port,
        "POST",
        path,
        {"kind": "insert_widget", "parent": "c1", "widget": "data_table", "values": values},
    )
    out = tmp_path / "exported"
    done = ask(port, "POST", f"/streamlit/canvases/{canvas}/export", {"folder": str(out)})
    files = set(done["files"])
    assert files <= {"adapter.py", "connections.py", "data.py", "API.py", "app.py", "widgets.py",
                     "requirements.txt", "README.md"}, files  # fmt: skip
    assert {"adapter.py", "connections.py", "app.py", "widgets.py", "requirements.txt"} <= files
    assert len(files) <= 8 and not any(f.startswith("sandbox") or f.startswith("data/") for f in files)
    assert "SHOP_PASSWORD" in done["variables"]
    _secret_free(out)
    # A fresh folder holding only those files, run by a Python that has never seen the app.
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    for name in files:
        (fresh / name).write_bytes((out / name).read_bytes())
    ran = subprocess.run(  # noqa: S603 (a Python with Streamlit, the test's own script)
        [str(PYTHON), "-I", "-c", RUN_APP], cwd=fresh, capture_output=True, text=True, timeout=600,
        check=False,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "SHOP_PASSWORD": "made-up-from-the-host"},
    )  # fmt: skip
    line = next((x for x in reversed(ran.stdout.splitlines()) if x.startswith("SAB-RUN ")), None)
    assert line, ran.stdout[-2000:] + ran.stderr[-2000:]
    found = json.loads(line[len("SAB-RUN ") :])
    assert not found["exceptions"] and not found["said"], found
    assert sorted(r["city"] for r in found["frames"][0]) == ["Ogdenville", "Shelbyville", "Springfield"]


def test_the_deliverable_is_read_from_the_types_contract(
    shop: tuple[int, Path, Path], tmp_path: Path
) -> None:
    port, _, _ = shop
    folder = tmp_path / "dash"
    ask(port, "POST", "/project/new", {"path": str(folder), "type": "streamlit"})
    listed = ask(port, "GET", "/project/scaffold")["deliverable"]
    assert listed["type"] == "streamlit" and listed["deliverable"] == "a Streamlit app"
    by = {f["path"]: f for f in listed["files"]}
    # The file's own name, never the contract's unfilled {slug} (Home's Deliverable card showed it).
    assert set(by) == {"dash.canvas.json", "builds/"} and by["builds/"]["grows_on"] == ["launch"]
    assert by["dash.canvas.json"]["present"] and not by["builds/"]["present"]  # no Launch yet
    assert by["dash.canvas.json"]["listed"] == "{slug}.canvas.json"
    # The base's scaffold names no extension's file: it reads them from the contract.
    base = Path(rules.__file__).read_text(encoding="utf-8") + Path(
        rules.__file__.replace("domain", "services")
    ).read_text(encoding="utf-8")
    for named in ("canvas.json", "builds/", "workbook", "powerbi/", "power.config.json", "app.py"):
        assert named not in base, named


def test_an_exports_api_client_is_loaded_from_beside_connections_py() -> None:
    """An API's connection loads its client from where this computer's library keeps it; an export
    carries the file and loads it from beside connections.py (found building the field service test app,
    2026-11-22: the exported app named a path of the computer it was made on)."""
    here = "C:\\\\Users\\\\dana\\\\library\\\\apis\\\\Orders\\\\API_Orders.py"
    code = (
        "import importlib.util\nimport os\n"
        f'spec = importlib.util.spec_from_file_location("API_Orders", "{here}")\n'
        "API_Orders = importlib.util.module_from_spec(spec)\n"
    )
    text, clients = rules.clients_beside(code)
    assert clients == {"API_Orders": "C:\\Users\\dana\\library\\apis\\Orders\\API_Orders.py"}
    assert "dana" not in text and 'os.path.abspath(__file__)), "API_Orders.py"))' in text
    compile(text, "connections.py", "exec")
    assert rules.clients_beside("conn = 1\n") == ("conn = 1\n", {})


@needs_streamlit
def test_an_export_reading_a_connection_and_the_sandbox_keeps_both(
    shop: tuple[int, Path, Path], tmp_path: Path
) -> None:
    """A canvas reading a connection's table and a sandbox table: the export reads the first through
    connections.py and carries the second as its own copy. The sandbox's table was dropped with the
    connection's (no copy, and connections.py never names the sandbox), so its widget failed where it
    ran (found building the field service test app, 2026-11-22)."""
    port, folder, _ = shop
    ask(port, "POST", "/sandbox/tables", {"from": "connection", "connection": "Shop", "table": "customers"})
    canvas = ask(port, "POST", "/streamlit/canvases", {"name": "Both", "folder": str(folder)})["canvas"]
    path = f"/streamlit/canvases/{canvas}/command"
    for table in ("[Shop].customers", "[Sandbox].customers"):
        ask(
            port,
            "POST",
            path,
            {"kind": "insert_widget", "widget": "data_table", "values": {"table_name": table}},
        )
    out = tmp_path / "exported"
    done = ask(port, "POST", f"/streamlit/canvases/{canvas}/export", {"folder": str(out)})
    files = set(done["files"])
    copies = [f for f in files if f.startswith("data/")]
    assert {"adapter.py", "connections.py"} <= files and len(copies) == 1 and "Sandbox_customers" in copies[0]
    fresh = tmp_path / "fresh"
    for name in files:
        (fresh / name).parent.mkdir(parents=True, exist_ok=True)
        (fresh / name).write_bytes((out / name).read_bytes())
    ran = subprocess.run(  # noqa: S603 (a Python with Streamlit, the test's own script)
        [str(PYTHON), "-I", "-c", RUN_APP], cwd=fresh, capture_output=True, text=True, timeout=600,
        check=False,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "SHOP_PASSWORD": "made-up-from-the-host"},
    )  # fmt: skip
    line = next((x for x in reversed(ran.stdout.splitlines()) if x.startswith("SAB-RUN ")), None)
    assert line, ran.stdout[-2000:] + ran.stderr[-2000:]
    found = json.loads(line[len("SAB-RUN ") :])
    assert not found["exceptions"] and not found["said"], found
    assert [len(frame) for frame in found["frames"]] == [3, 3]


def test_connections_py_reads_a_connection_by_its_own_read_a_table(tmp_path: Path) -> None:
    """A connection of your own Python (an API's tables too) is read by its own Read a table, not by a
    client the adapter knows: connections.py handed the adapter that client and the read failed ("The
    adapter cannot tell what Orders is"; found building the field service test app, 2026-11-22). Its READERS
    are the adapter's source now: the table read whole by its code, the plan done by DuckDB over it."""
    parts = (
        "def connect_notes():\n"
        "    def read(schema, table, limit):\n"
        "        rows = [{'id': 1, 'city': 'Springfield'}, {'id': 2, 'city': 'Ogdenville'}]\n"
        "        return rows, len(rows)\n"
        "    return object(), read\n\n\n"
        "MADE = {'Notes': lambda: connect_notes()[0]}\n"
        "READERS = {'Notes': connect_notes}\n\n\n"
        "def connection(name):\n"
        "    return MADE[name]()\n"
    )
    (tmp_path / "connections.py").write_text(rules.connections_py(parts), encoding="utf-8")
    (tmp_path / "adapter.py").write_bytes(Path(the_adapter.__file__).read_bytes())
    script = HERE + (
        "import json, connections, adapter\n"
        "plan = adapter.plan_from({'filters': [['city', '=', 'Ogdenville']], 'columns': ['id']})\n"
        "some, folded = adapter.read('Notes', 'cities', plan)\n"
        "every, _ = adapter.read('Notes', 'cities')\n"
        "try:\n"
        "    adapter.write('Notes', 'cities', adapter.arrow_of([{'id': 3}]))\n"
        "    refused = ''\n"
        "except adapter.AdapterError as error:\n"
        "    refused = str(error)\n"
        "found = [some.read_all().to_pylist(), list(folded.parts), every.read_all().num_rows, refused]\n"
        "print(json.dumps(found))\n"
    )
    ran = subprocess.run(  # noqa: S603 (this Python, the test's own script)
        [sys.executable, "-I", "-c", script], cwd=tmp_path, capture_output=True, text=True, timeout=120,
        check=False,
    )  # fmt: skip
    assert ran.returncode == 0, ran.stderr
    assert json.loads(ran.stdout) == [
        [{"id": 2}],
        [],
        2,
        "Notes takes no writes here: it is read by its own Read a table.",
    ]
