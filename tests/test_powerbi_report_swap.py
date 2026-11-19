"""Use an existing report's pages (extensions/powerbi: domain/report_swap.py, the export's report): made-up
.pbit/.pbix files built here from the documented structure (a zip: Report/Layout in UTF-16 LE, DataModelSchema
as JSON); never a real customer's file."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench_powerbi.domain import report_swap as rules
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def vault(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SWISSARMYBENCH_EXTENSIONS", "streamlit,powerbi")
    with memory_keyring():
        yield


def column(entity: str, prop: str, alias: str | None = None) -> dict[str, Any]:
    source = {"Source": alias} if alias else {"Entity": entity}
    return {"Column": {"Expression": {"SourceRef": source}, "Property": prop}}


def measure(entity: str, prop: str) -> dict[str, Any]:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def visual(kind: str, selects: list[dict[str, Any]], refs: list[str]) -> dict[str, Any]:
    query = {
        "Commands": [
            {
                "SemanticQueryDataShapeCommand": {
                    "Query": {
                        "Version": 2,
                        "From": [{"Name": "s", "Entity": "Sales", "Type": 0}],
                        "Select": [s | {"Name": r} for s, r in zip(selects, refs, strict=True)],
                    }
                }
            }
        ]
    }
    config = {
        "name": kind,
        "singleVisual": {
            "visualType": kind,
            "projections": {"Values": [{"queryRef": r} for r in refs]},
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "s", "Entity": "Sales", "Type": 0}],
                "Select": selects,
            },
        },
    }
    return {
        "x": 0,
        "y": 0,
        "z": 0,
        "width": 300,
        "height": 200,
        "config": json.dumps(config),
        "query": json.dumps(query),
    }


def layout() -> dict[str, Any]:
    """A made-up report: a table, a chart, a slicer, a page filter, and a report measure."""
    table = visual(
        "tableEx",
        [column("Sales", "Region", "s"), column("Sales", "Amount", "s")],
        ["Sales.Region", "Sales.Amount"],
    )
    chart = visual(
        "clusteredColumnChart",
        [column("Sales", "Region", "s"), measure("Sales", "Total Sales")],
        ["Sales.Region", "Sales.Total Sales"],
    )
    slicer = visual("slicer", [column("Calendar", "Year")], ["Calendar.Year"])
    page_filter = [{"name": "f1", "expression": column("Sales", "Channel"), "type": "Categorical"}]
    extension = {
        "modelExtensions": [
            {
                "name": "extension",
                "entities": [
                    {
                        "name": "Sales",
                        "extends": "Sales",
                        "measures": [
                            {
                                "name": "Big Sales",
                                "expression": "CALCULATE([Total Sales], 'Sales'[Amount] > 100)",
                            }
                        ],
                    }
                ],
            }
        ]
    }
    return {
        "id": 0,
        "config": json.dumps(extension),
        "sections": [
            {
                "name": "ReportSection1",
                "displayName": "Overview",
                "filters": json.dumps(page_filter),
                "visualContainers": [table, chart, slicer],
            }
        ],
    }


SCHEMA = {
    "name": "Made-up model",
    "model": {
        "tables": [
            {
                "name": "Sales",
                "measures": [
                    {"name": "Total Sales", "expression": "SUM(Sales[Amount])", "formatString": "#,##0"},
                    {"name": "Lost", "expression": "SUM(Sales[Discount])"},
                ],
            }
        ]
    },
}


def pbit(extra: dict[str, bytes] | None = None, with_schema: bool = True) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("Version", "1.28".encode("utf-16-le"))
        z.writestr("Report/Layout", json.dumps(layout()).encode("utf-16-le"))
        z.writestr("Report/StaticResources/SharedResources/BaseThemes/CY24SU10.json", b"{}")
        if with_schema:
            z.writestr("DataModelSchema", json.dumps(SCHEMA).encode("utf-16-le"))
        z.writestr("DataModel", b"\x00binary that is never read")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return out.getvalue()


OURS = {"sales": ["region", "amount", "channel"], "calendar": ["year", "month"]}


def read(data: bytes, kind: str = "pbit") -> rules.Report:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = rules.wanted_entries((i.filename, i.file_size) for i in z.infolist())
        return rules.from_archive(kind, {n: z.read(n) for n in names})


def test_the_fields_of_a_table_a_chart_a_slicer_and_a_filter() -> None:
    report = read(pbit())
    assert set(report.files) == {"report.json", "StaticResources/SharedResources/BaseThemes/CY24SU10.json"}
    found = rules.fields_of(report.files)
    assert found == {
        ("Sales", "Region"): "column",
        ("Sales", "Amount"): "column",
        ("Sales", "Total Sales"): "measure",
        ("Calendar", "Year"): "column",
        ("Sales", "Channel"): "column",
    }
    assert [m["name"] for m in report.measures or []] == ["Total Sales", "Lost"]


def test_the_mapping_by_name_any_case_and_by_hand() -> None:
    report = read(pbit())
    found = rules.fields_of(report.files)
    proposed = rules.propose(found, OURS, measures=[("sales", "Total Sales")])
    by = {m.field: m for m in proposed}
    assert by[("Sales", "Region")].to == ("sales", "region") and by[("Sales", "Region")].matched
    assert by[("Sales", "Total Sales")].to == ("sales", "Total Sales")
    picked = rules.chosen(proposed, {"Calendar.Year": "calendar.month", "Sales.Channel": None})
    by = {m.field: m for m in picked}
    assert by[("Calendar", "Year")].to == ("calendar", "month") and not by[("Calendar", "Year")].matched
    assert by[("Sales", "Channel")].to is None
    with pytest.raises(rules.ReportError):
        rules.chosen(proposed, {"Calendar.Year": 3})


def test_every_reference_is_rewritten_and_a_left_one_stays() -> None:
    report = read(pbit())
    proposed = rules.propose(rules.fields_of(report.files), OURS, measures=[("sales", "Total Sales")])
    mapped = rules.chosen(proposed, {"Calendar.Year": "calendar.month", "Sales.Channel": None})
    files = rules.rewrite(report.files, mapped)
    after = rules.fields_of(files)
    assert ("sales", "region") in after and ("calendar", "month") in after
    assert ("sales", "Channel") in after  # left: its field name kept (its table follows the table's mapping)
    text = files["report.json"].decode()
    assert '\\"queryRef\\":\\"sales.region\\"' in text and "Sales.Region" not in text
    extension = json.loads(json.loads(text)["config"])["modelExtensions"][0]["entities"][0]
    assert extension["name"] == "sales"
    assert extension["measures"][0]["expression"] == "CALCULATE([Total Sales], sales[amount] > 100)"
    assert files["StaticResources/SharedResources/BaseThemes/CY24SU10.json"] == b"{}"


def test_the_models_measures_come_across_and_an_unmapped_one_is_said() -> None:
    report = read(pbit())
    mapped = rules.propose(rules.fields_of(report.files), OURS)
    brought, said = rules.bring_measures(report.measures or [], mapped, OURS)
    assert [(m.table, m.name, m.expression, m.format) for m in brought] == [
        ("sales", "Total Sales", "SUM(sales[amount])", "#,##0")
    ]
    assert said == ["Sales[Lost] names Sales[Discount], which this model maps to nothing"]


def test_unsafe_entries_are_refused_and_a_pbix_without_its_model_says_how() -> None:
    for bad in ("../evil.txt", "/etc/x", "C:/x", "Report/../../x"):
        with pytest.raises(rules.ReportError, match="unsafe"):
            read(pbit({bad: b"x"}))
    plain = read(pbit(with_schema=False), "pbix")
    assert plain.measures is None and "Power BI template" in plain.measures_note
    assert "could not be read (made-up reason)" in rules.unreadable_pbix("made-up reason")
    with pytest.raises(rules.ReportError, match="too large"):
        rules.wanted_entries([("Report/Layout", rules.MAX_ENTRY_BYTES + 1)])


def test_pbixrays_measures_are_read_from_its_rows() -> None:
    rows = [
        {
            "TableName": "Sales",
            "Name": "Total Sales",
            "Expression": "SUM(Sales[Amount])",
            "DisplayFolder": "KPIs",
        }
    ]
    assert rules.pbix_measures(rows) == [
        {
            "table": "Sales",
            "name": "Total Sales",
            "expression": "SUM(Sales[Amount])",
            "format": "",
            "folder": "KPIs",
        }
    ]


def test_tmdl_measures_are_read_back() -> None:
    tmdl = {
        "definition/tables/Sales.tmdl": "table Sales\r\n\tlineageTag: x\r\n\r\n"
        "\tmeasure 'Total Sales' = SUM(Sales[Amount])\r\n"
        "\t\tformatString: #,##0\r\n\t\tdisplayFolder: KPIs\r\n\r\n"
        "\tmeasure Big =\r\n\t\t\tVAR x = 1\r\n\t\t\tRETURN x\r\n"
        "\t\tlineageTag: y\r\n\r\n\tcolumn Amount\r\n\t\tdataType: double\r\n"
    }
    assert rules.tmdl_measures(tmdl) == [
        {
            "table": "Sales",
            "name": "Total Sales",
            "expression": "SUM(Sales[Amount])",
            "format": "#,##0",
            "folder": "KPIs",
        },
        {"table": "Sales", "name": "Big", "expression": "VAR x = 1\nRETURN x", "format": "", "folder": ""},
    ]


# ===== through the export =====


def project(client: Any, tmp_path: Path) -> Path:
    folder = tmp_path / "Swap"
    assert client.post("/project/new", json={"path": str(folder)}, headers=AUTH).status_code == 200
    (folder / "data").mkdir()
    (folder / "data" / "sales.csv").write_text("region,amount,channel\nN,10.5,web\nS,20.0,shop\n", "utf-8")
    (folder / "data" / "calendar.csv").write_text("year,month\n2026,1\n", "utf-8")
    for name in ("sales", "calendar"):
        body = {"path": str(folder / "data" / f"{name}.csv")}
        assert client.post(f"/datasets/{name}/load", json=body, headers=AUTH).status_code == 200
    return folder


def test_export_with_another_reports_pages(tmp_path: Path) -> None:
    dropped = tmp_path / "Made-up sales.pbit"
    dropped.write_bytes(pbit())
    before = dropped.read_bytes()
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        body: dict[str, Any] = {"tables": ["sales", "calendar"], "report": {"path": str(dropped)}}
        plan = client.post("/powerbi/plan", json=body, headers=AUTH).json()
        fields = {(f["table"], f["field"]): f for f in plan["report"]["fields"]}
        assert fields[("Sales", "Region")]["to"] == {"table": "sales", "field": "region"}
        assert fields[("Calendar", "Year")]["to"] == {"table": "calendar", "field": "year"}
        assert plan["report"]["measures"] == ["Total Sales"] and plan["report"]["said"]
        body |= {"mapping": {"Calendar.Year": "calendar.month"}, "bring_measures": True}
        done = client.post("/powerbi/export", json=body, headers=AUTH)
        assert done.status_code == 200, done.text
        report = folder / "powerbi" / "Swap.Report"
        pbir = json.loads((report / "definition.pbir").read_text())
        assert pbir["datasetReference"] == {"byPath": {"path": "../Swap.SemanticModel"}}
        layout = (report / "report.json").read_text()
        assert "calendar.month" in layout and "Calendar.Year" not in layout
        assert not (report / "definition").exists()  # the legacy layout: no PBIR pages beside it
        sales = (
            folder / "powerbi" / "Swap.SemanticModel" / "definition" / "tables" / "sales.tmdl"
        ).read_text()
        assert "measure 'Total Sales' = SUM(sales[amount])" in sales
    assert dropped.read_bytes() == before  # read, never changed
