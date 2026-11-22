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
    assert set(by) == {"{slug}.canvas.json", "builds/"} and by["builds/"]["grows_on"] == ["launch"]
    assert by["{slug}.canvas.json"]["present"] and not by["builds/"]["present"]  # no Launch yet
    # The base's scaffold names no extension's file: it reads them from the contract.
    base = Path(rules.__file__).read_text(encoding="utf-8") + Path(
        rules.__file__.replace("domain", "services")
    ).read_text(encoding="utf-8")
    for named in ("canvas.json", "builds/", "workbook", "powerbi/", "power.config.json", "app.py"):
        assert named not in base, named
