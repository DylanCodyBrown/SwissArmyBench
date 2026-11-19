"""A made-up .pbix as pbixray would read it (behind adapters/pbix_reader.py): two SQL
sources (a SQL Server and a PostgreSQL named by a Power Query parameter), three tables, two relationships (one
inactive), a measure in a display folder. Made-up names only. `fake_pbix` writes a zip that looks like one."""

from __future__ import annotations

import zipfile
from pathlib import Path

from swissarmybench_powerbi.domain import pbix_file as pf

SALES_M = """let
    Source = Sql.Database("sql01.contoso.example", "SalesDb"),
    dbo_Sales = Source{[Schema="dbo",Item="Sales"]}[Data],
    #"Filtered Rows" = Table.SelectRows(dbo_Sales, each [Amount] > 0)
in
    #"Filtered Rows\""""
CUSTOMER_M = """let
    Source = Sql.Database("sql01.contoso.example", "SalesDb"),
    Navigation = Source{[Schema="dbo",Item="Customer"]}[Data]
in
    Navigation"""
PRODUCT_M = """let
    Source = PostgreSQL.Database(PgHost, "ops"),
    Navigation = Source{[Schema="public",Item="product"]}[Data]
in
    Navigation"""

MODEL = pf.PbixModel(
    "Sales model",
    tables=(
        pf.PTable(
            "Sales",
            (
                pf.PColumn("OrderKey", "int64"),
                pf.PColumn("CustomerKey", "int64"),
                pf.PColumn("ProductKey", "int64"),
                pf.PColumn("Amount", "float64"),
            ),
            SALES_M,
        ),
        pf.PTable(
            "Customer", (pf.PColumn("CustomerKey", "int64"), pf.PColumn("Region", "string")), CUSTOMER_M
        ),
        pf.PTable("Product", (pf.PColumn("ProductKey", "int64"), pf.PColumn("Name", "string")), PRODUCT_M),
        pf.PTable("LocalDateTable_0001", (pf.PColumn("Date", "datetime64[ns]"),), ""),
    ),
    relationships=(
        pf.PRelationship("Sales", "CustomerKey", "Customer", "CustomerKey", True),
        pf.PRelationship("Sales", "ProductKey", "Product", "ProductKey", False),
    ),
    measures=(pf.PMeasure("Sales", "Total Sales", "SUM(Sales[Amount])", "KPIs", "#,0"),),
    parameters={"PgHost": "pg01.contoso.example"},
    refreshed="2026-11-02T14:05:00",
)


def fake_pbix(folder: Path, name: str = "Sales model.pbix") -> Path:
    path = folder / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("DataModel", b"made-up")
        archive.writestr("Version", b"1.28")
    return path


def reader(path: str) -> pf.PbixModel:
    if not path.lower().endswith(".pbix"):
        raise pf.PbixError("Use a .pbix file.")
    return MODEL
