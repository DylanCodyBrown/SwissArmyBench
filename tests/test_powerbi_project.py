"""The Power BI project (extensions/powerbi): a .pbix read with pbixray (faked behind its interface: tests/
powerbi_pbix_fake.py), the .pbix file connection (C), the import as a project (B), To finish setting up (H)
and
Read Power BI from (E). The published dataset is found through tests/powerbi_standin.py. Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench_powerbi.adapters import pbix_reader
from swissarmybench_powerbi.domain import pbix_file as pf
from swissarmybench_powerbi.domain import pbix_import as rules
from tests import powerbi_pbix_fake as fake
from tests import powerbi_standin as made_up
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_powerbi import saved_connection


@pytest.fixture(autouse=True)
def extension_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SWISSARMYBENCH_EXTENSIONS", "streamlit,powerbi")
    with memory_keyring():
        yield


THIN = "Data Source=powerbi://api.powerbi.com/v1.0/myorg/Finance;Initial Catalog=Sales model"


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


# ===== C: the .pbix file connection's rules =====


def test_a_path_is_code_and_a_variable_is_the_environment() -> None:
    assert pf.path_code(r"C:\Reports\Sales model.pbix") == repr(r"C:\Reports\Sales model.pbix")
    assert pf.path_code("${REPORTS}/Sales.pbix") == "os.environ[\"REPORTS\"] + '/Sales.pbix'"
    with pytest.raises(pf.PbixError, match=r"a \.pbit or \.pbip has no rows"):
        pf.path_code("Sales.pbit")
    body = pf.connection_body("Sales file", "${REPORTS}/Sales.pbix")
    assert body["template"] == "python" and body["tags"] == [pf.TAG]
    assert body["variables"] == [{"name": "REPORTS", "from": "env"}]
    assert pf.path_of(body["code"]) == "${REPORTS}/Sales.pbix"
    assert pf.path_of(pf.connect_code(r"C:\Reports\Sales.pbix")) == r"C:\Reports\Sales.pbix"


def test_the_card_says_as_of_read_only_and_the_portability_note() -> None:
    card = pf.card(fake.MODEL, r"C:\Reports\Sales model.pbix")
    assert card["tables"] == ["Sales", "Customer", "Product"]  # Power BI's own date tables left out
    assert card["as_of"] == "as of 2026-11-02 14:05"
    assert card["read_only"].startswith("Read-only") and card["portability"].startswith(
        "Only works on your machine"
    )
    assert pf.card(None, "https://contoso.example/x.pbix")["portability"] == ""


def test_the_connection_code_reads_through_pbixray(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The three boxes, run against a made-up pbixray (the real one is the extension's dependency)."""
    import sys
    import types

    import pandas as pd

    class Made:
        def __init__(self, path: str) -> None:
            self.path = path
            self.schema = pd.DataFrame(
                [
                    {"TableName": t.name, "ColumnName": c.name, "PandasDataType": c.type}
                    for t in fake.MODEL.tables
                    for c in t.columns
                ]
            )

        def get_table(self, name: str) -> pd.DataFrame:
            return pd.DataFrame({"CustomerKey": [1, 2, 3], "Region": ["North", "South", "East"]})

    monkeypatch.setitem(sys.modules, "pbixray", types.SimpleNamespace(PBIXRay=Made))
    monkeypatch.setenv("REPORTS", str(tmp_path))
    body = pf.connection_body("Sales file", "${REPORTS}/Sales.pbix")
    names: dict[str, Any] = {}
    exec(body["code"], names)  # noqa: S102 (the made-up boxes, as the child process runs them)
    assert names["conn"].path == str(tmp_path / "Sales.pbix")
    listing = eval(body["catalog"]["command"], names)  # noqa: S307 (made-up boxes)
    assert {r["table"] for r in listing} == {"Sales", "Customer", "Product"}
    rows, total = eval(  # noqa: S307 (made-up boxes)
        pf.READ_CODE.splitlines()[1], names | {"rows": names["conn"].get_table("Customer"), "limit": 2}
    )
    assert len(rows) == 2 and total == 3


def test_a_thin_report_names_its_dataset() -> None:
    connections = {"Connections": [{"ConnectionString": THIN}]}
    assert pf.thin_target(json.dumps(connections)) == ("Sales model", "Finance")
    assert pf.thin_target("not json") == ("", "")


def test_the_reader_tells_a_thin_report_without_pbixray(tmp_path: Path) -> None:
    import zipfile

    thin = tmp_path / "Thin.pbix"
    connections = {"Connections": [{"ConnectionString": THIN}]}
    with zipfile.ZipFile(thin, "w") as archive:
        archive.writestr("Connections", json.dumps(connections))
    model = pbix_reader.read(str(thin))
    assert model.thin and model.thin_dataset == "Sales model" and model.thin_workspace == "Finance"


def test_pbixray_frames_become_the_model() -> None:
    import pandas as pd

    class Frames:
        schema = pd.DataFrame([{"TableName": "Sales", "ColumnName": "Amount", "PandasDataType": "float64"}])
        power_query = pd.DataFrame([{"TableName": "Sales", "Expression": fake.SALES_M}])
        relationships = pd.DataFrame(
            [
                {
                    "FromTableName": "Sales",
                    "FromColumnName": "CustomerKey",
                    "ToTableName": "Customer",
                    "ToColumnName": "CustomerKey",
                    "IsActive": False,
                    "Cardinality": "M:1",
                    "CrossFilteringBehavior": "BothDirections",
                }
            ]
        )
        dax_measures = pd.DataFrame(
            [
                {
                    "TableName": "Sales",
                    "Name": "Total",
                    "Expression": "SUM(Sales[Amount])",
                    "DisplayFolder": "KPIs",
                }
            ]
        )
        m_parameters = pd.DataFrame(
            [{"ParameterName": "PgHost", "Expression": '"pg01" meta [IsParameterQuery=true]'}]
        )
        metadata = pd.DataFrame([{"Name": "LastUpdate", "Value": "2026-11-02T14:05:00"}])

    model = pbix_reader.from_pbixray(Frames(), "Sales model")
    assert model.tables[0].m == fake.SALES_M and model.parameters == {"PgHost": "pg01"}
    assert not model.relationships[0].active and model.relationships[0].both_ways
    assert model.measures[0].folder == "KPIs" and pf.as_of(model.refreshed) == "as of 2026-11-02 14:05"


# ===== B: the import's plan =====


def test_the_plan_reuses_a_connection_and_makes_the_rest() -> None:
    existing = [
        {
            "name": "Warehouse",
            "kind": "sqlserver",
            "settings": {"server": "SQL01.contoso.example"},
            "database": "salesdb",
        }
    ]
    plan = rules.plan(
        fake.MODEL, "Sales model", existing, [{"connection": "Finance", "dataset": "Sales model"}]
    )
    assert [(c.name, c.kind, c.reused) for c in plan.connections] == [
        ("Warehouse", "sqlserver", True),
        ("Ops", "postgres", False),
    ]
    assert plan.connections[1].settings == {"server": "${PgHost}", "database": "ops"}
    assert plan.variables == {"PgHost": "pg01.contoso.example"}
    sales = plan.tables[0]
    assert (sales.connection, sales.schema, sales.table, sales.steps_after) == (
        "Warehouse",
        "dbo",
        "Sales",
        True,
    )
    assert sales.source_sql() == "SELECT * FROM dbo.Sales"
    assert plan.dataset == {"connection": "Finance", "dataset": "Sales model"}


def test_the_dataset_is_asked_when_not_one() -> None:
    two = [
        {"connection": "Finance", "dataset": "Sales model"},
        {"connection": "Sales WS", "dataset": "Sales model"},
    ]
    found, choices = rules.find_dataset(fake.MODEL, two, None)
    assert found is None and choices == two  # never guessed
    found, choices = rules.find_dataset(fake.MODEL, [], None)
    assert found is None and choices == []
    picked, _ = rules.find_dataset(fake.MODEL, two, {"connection": "Sales WS", "dataset": "Sales model"})
    assert picked == {"connection": "Sales WS", "dataset": "Sales model"}


def test_the_notebook_has_a_sql_and_a_dax_cell_per_table() -> None:
    plan = rules.plan(fake.MODEL, "Sales model", [], [{"connection": "Finance", "dataset": "Sales model"}])
    cells = rules.notebook_cells(plan, "Finance")
    named = {c.get("name"): c["source"] for c in cells}
    assert named["Sales source"] == "%%sql SalesDb\nSELECT * FROM dbo.Sales"
    assert named["Product in Power BI"] == "%%dax Finance/Sales model\nEVALUATE 'Product'"
    book = json.loads(rules.notebook_json(cells))
    assert book["nbformat"] == 4 and book["cells"][1]["metadata"]["swissarmybench"]["name"] == "Sales source"


def test_the_round_trip_keeps_an_untouched_m_and_sends_a_changed_query() -> None:
    plan = rules.plan(fake.MODEL, "Sales model", [], [])
    state = rules.state_json(plan, "Sales model.pbix", "", "Sales model file")
    kept = state["tables"][1]
    assert rules.round_trip_m(kept, "SELECT * FROM dbo.Customer") == ("kept", fake.CUSTOMER_M)
    kind, query = rules.round_trip_m(kept, "SELECT * FROM dbo.Customer WHERE Region = 'North'")
    assert kind == "query"
    rebuilt = rules.with_native_query(fake.CUSTOMER_M, query)
    assert 'Sql.Database("sql01.contoso.example", "SalesDb", [Query="SELECT' in rebuilt
    assert rules.write_state(state) == rules.write_state(json.loads(rules.write_state(state)))  # byte-stable


def test_to_finish_lists_what_is_left_and_each_row_goes_when_done() -> None:
    plan = rules.plan(fake.MODEL, "Sales model", [], [])
    state = rules.state_json(plan, "x.pbix", "", "x file")
    rows = rules.to_finish(state, ["Contoso BI"], {"SalesDb": "a password"})
    assert [r["id"] for r in rows] == ["registration", "dataset", "connection:SalesDb"]
    assert rows[0]["fix"]["choices"] == ["Contoso BI"]
    done = state | {
        "registration": "Contoso BI",
        "dataset": {"connection": "Finance", "dataset": "Sales model"},
    }
    assert [r["id"] for r in rules.to_finish(done, [], {})] == []


# ===== B, C, E, H over HTTP: the stand-in's published dataset, the fake reader =====


@pytest.fixture
def standin(monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


def test_a_pbix_imported_as_a_project_ready_to_work(tmp_path: Path, standin: made_up.StandIn) -> None:
    pbix = fake.fake_pbix(tmp_path)
    with make_client(tmp_path) as client:
        client.app.state.ctx.powerbi_project.reader = fake.reader  # type: ignore[attr-defined]
        saved_connection(client)  # the Finance workspace: the stand-in's three datasets
        body = {"path": str(pbix), "folder": str(tmp_path / "projects")}
        planned = ok(client.post("/powerbi/import", json=body | {"dry_run": True}, headers=AGENT))
        assert planned["dataset"] == {"connection": "Finance", "dataset": "Sales model"}
        assert [c["name"] for c in planned["connections"]] == ["SalesDb", "Ops"]
        assert not (tmp_path / "projects" / "Sales model").exists()  # a dry run makes nothing

        done = ok(client.post("/powerbi/import", json=body, headers=AUTH))
        folder = Path(done["folder"])
        assert done["type"] == "powerbi" and (folder / ".sab" / "powerbi.json").is_file()
        state = json.loads((folder / ".sab" / "powerbi.json").read_text())
        assert state["measures"][0]["folder"] == "KPIs" and state["tables"][0]["m"] == fake.SALES_M
        book = json.loads((folder / "data.ipynb").read_text())
        assert any("%%dax Finance/Sales model" in "".join(c["source"]) for c in book["cells"])
        names = {c["name"] for c in ok(client.get("/connections", headers=AUTH))["connections"]}
        assert {"SalesDb", "Ops", "Sales model file", "Finance"} <= names
        variables = ok(client.get("/variables", headers=AUTH))
        assert "PgHost" in json.dumps(variables)
        pairs = {p["table"]: p for p in done["grids"]}
        assert pairs["Customer"]["in_power_bi"], json.dumps(
            pairs["Customer"]
        )  # read through the published dataset
        assert pairs["Customer"]["source_error"]  # no server here: said, the import still finished
        rows = {r["id"] for r in done["to_finish"]}
        assert "registration" in rows and "dataset" not in rows
        assert "connection:SalesDb" in rows  # its password is asked on this computer

        # E: the source, its words; Local with no Power BI Desktop falls back to the file, said.
        source = ok(client.get("/powerbi/source", headers=AGENT))
        assert source["words"] == "Sales model · Published"
        switched = ok(client.put("/powerbi/source", json={"source": "local"}, headers=AGENT))
        assert (
            switched["effective"] == "file"
            and "Open Sales model.pbix in Power BI Desktop" in switched["note"]
        )
        assert "Reading the file as of its last save: 2026-11-02 14:05" in switched["note"]
        project = json.loads((folder / ".sab" / "project.json").read_text())
        assert project["powerbi_source"] == "local"

        # H: a fix clears its row.
        fixed = ok(
            client.post(
                "/powerbi/setup", json={"action": "registration", "registration": "none"}, headers=AGENT
            )
        )
        assert "registration" not in {r["id"] for r in fixed["to_finish"]}

        # C: the file connection's card and its relationships into the ERD.
        card = ok(client.get("/powerbi/file-connection/Sales%20model%20file", headers=AGENT))
        assert card["as_of"] == "as of 2026-11-02 14:05" and card["tables"] == [
            "Sales",
            "Customer",
            "Product",
        ]
        page = ok(client.get("/powerbi/page", headers=AGENT))
        assert page["project"] and page["actions"][0]["label"] == "Refresh from the file"
