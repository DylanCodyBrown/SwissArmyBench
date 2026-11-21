"""The blade tab's Properties and New blade's scaffold (the owner, 2026-11-21: "the blade format requires
extra stuff so we should add those properties to the ide experience along with the option to save the blade.
we should scaffold a blank blade for the user"). Every header field for the kinds it applies to;
a save refused when the code lacks its kind's part; New blade by a name and a kind,
a blank valid blade that runs at once.
Made-up data only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import blade_header
from swissarmybench.domain.blade_header import SCAFFOLD_KINDS, Shape, applies, required_part, scaffold
from swissarmybench.domain.blades import BladeError, parse_blade, read_blade, write_blade
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        yield test_client


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


TABLE = Shape("other", None, names_table=True)
DATABASE = Shape("sql", "database", names_table=False)
SNIPPET = Shape("snippet", None, names_table=False)
SECRET = Shape("secret", None, names_table=False)
PYTHON = Shape("other", "python", names_table=False, template="python")


def test_only_the_fields_a_kind_has_apply() -> None:
    assert applies("table", TABLE) and not applies("table", DATABASE)
    assert applies("dialect", DATABASE) and not applies("dialect", TABLE)
    assert applies("queries.total", DATABASE) and not applies("queries.total", TABLE)
    assert applies("language", SNIPPET) and not applies("variable", SNIPPET)
    assert applies("env_names", SECRET) and not applies("variable", SECRET)
    assert applies("read.command", PYTHON) and applies("row_limit", PYTHON)
    for shape in (TABLE, DATABASE, SNIPPET, SECRET, PYTHON):
        assert all(applies(k, shape) for k in ("name", "description", "tags"))


def test_a_properties_save_becomes_what_the_file_writes() -> None:
    blade = scaffold("connection", "Shop")
    changes = blade_header.changes(blade, {"queries.total": "4", "catalog.command": "SELECT 1"}, DATABASE)
    assert changes["queries"] == {"total": 4}
    assert changes["catalog"] == {"language": "sql", "command": "SELECT 1"}
    with pytest.raises(BladeError, match="not a field"):
        blade_header.changes(blade, {"table": "x"}, DATABASE)
    with pytest.raises(BladeError, match="follows from"):
        blade_header.changes(blade, {"secrets": ["A"]}, DATABASE)
    mapping = blade_header.changes(
        {}, {"vault_mapping": "SHOP_KEY = shop-key\n"}, Shape("vault", "vault", False)
    )
    assert mapping["vault_mapping"] == [{"env": "SHOP_KEY", "secret": "shop-key"}]


def test_the_required_part_is_said_with_its_line() -> None:
    no_return = "def make_table():\n    rows = 1\n"
    found = required_part(TABLE, no_return, "make_table")
    assert found is not None and found.line == 1 and "return" in found.message
    assert required_part(TABLE, "def make_table():\n    return 1\n", "make_table") is None
    assert required_part(TABLE, "def make_table(a):\n    return a\n", "make_table") is not None
    broken = required_part(TABLE, "x = (\n", "x")
    assert broken is not None and "not valid Python" in broken.message
    analysis = Shape("analysis", None, False)
    assert required_part(analysis, "def analyze():\n    return 1\n", "analyze") is not None
    assert required_part(PYTHON, "conn = 1\n", "conn", catalog="", read="x") is not None
    assert required_part(PYTHON, "conn = 1\n", "conn", catalog="x", read="y") is None


@pytest.mark.parametrize("kind", SCAFFOLD_KINDS)
def test_every_scaffold_is_a_valid_blade_that_reads_back(kind: str) -> None:
    made = parse_blade(scaffold(kind, "Fresh"))
    again = read_blade(write_blade(made.to_json()))
    assert again["name"] == "Fresh"
    shape = Shape(made.kind, "database" if made.kind == "sql" else None, names_table=kind == "table")
    assert required_part(shape, made.code, made.variable) is None


# ===== the doors =====


def test_new_blade_by_name_and_kind_runs_at_once(client: TestClient) -> None:
    made = ok(client.post("/blades/new", json={"name": "Orders", "kind": "table"}, headers=AGENT))
    assert made["scaffold"] is True and made["line"] > 1
    ran = ok(client.post("/blades/Orders/run", json={}, headers=AUTH))
    assert ran["ok"] and ran["result"]["total"] == 3 and "customer" in ran["result"]["columns"]
    taken = client.post("/blades/new", json={"name": "Orders", "kind": "table"}, headers=AUTH)
    assert taken.status_code >= 400 and "already" in taken.text
    ok(client.post("/blades/new", json={"name": "Sizes", "kind": "analysis"}, headers=AUTH))
    tried = ok(client.post("/blades/Sizes/run", json={}, headers=AUTH))
    assert tried["ok"] and "6 rows" in tried["result"]["text"]  # the made-up rows


def test_every_header_field_is_set_and_shown(client: TestClient) -> None:
    ok(client.post("/blades/new", json={"name": "Shop", "kind": "connection"}, headers=AUTH))
    fields = {f["key"]: f for f in ok(client.get("/blades/Shop/header", headers=AGENT))["fields"]}
    assert fields["dialect"]["value"] == "duckdb" and "duckdb" in fields["dialect"]["choices"]
    assert fields["queries.total"]["value"] == 8 and "table" not in fields
    answer = ok(
        client.put("/blades/Shop/header", json={"queries.total": 4, "description": "A shop"}, headers=AGENT)
    )
    shown = {f["key"]: f["value"] for f in answer["fields"]}
    assert shown["queries.total"] == 4 and shown["description"] == "A shop"
    detail = ok(client.get("/blades/Shop", headers=AUTH))
    assert "total = 4" in Path(detail["file"]).read_text()
    refused = client.put("/blades/Shop/header", json={"table": "shop"}, headers=AGENT)
    assert refused.status_code == 400 or refused.status_code == 422


def test_a_save_without_its_kinds_part_is_refused_with_its_line(client: TestClient) -> None:
    made = ok(client.post("/blades/new", json={"name": "Loaves", "kind": "table"}, headers=AUTH))
    before = Path(made["file"]).read_bytes()
    code = "import pandas as pd\n\n\ndef make_table():\n    rows = 3\n"
    refused = client.put("/blades/Loaves", json={"code": code}, headers=AUTH)
    assert refused.status_code == 422 and refused.json()["line"] == 4
    assert Path(made["file"]).read_bytes() == before  # nothing written
    saved = ok(
        client.put(
            "/blades/Loaves", json={"code": code + "    return rows\n", "family": "Bakery"}, headers=AUTH
        )
    )
    assert saved["name"] == "Loaves"
    assert 'family = "Bakery"' in Path(made["file"]).read_text()
