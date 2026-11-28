"""A realistic multi-query section document (the shape Power BI keeps a dataset's queries in) run to the
tables worked out by hand. Made-up data: a small shop. Imports only duckpq, duckdb and the standard library."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import duckdb

import duckpq

DOCUMENT = """section Shop;

shared Server = "shop-sql.example" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true];

shared MinimumAmount = 20 meta [IsParameterQuery = true, Type = "Number"];

shared Customers = let
    Source = Sql.Database(Server, "shop"),
    dbo_Customers = Source{[Schema = "dbo", Item = "Customers"]}[Data],
    #"Renamed Columns" = Table.RenameColumns(dbo_Customers, {{"CustomerName", "Customer"}}),
    #"Trimmed Text" = Table.TransformColumns(#"Renamed Columns", {{"Customer", Text.Trim, type text}}),
    #"Uppercased Country" = Table.TransformColumns(#"Trimmed Text", {{"Country", Text.Upper, type text}})
in
    #"Uppercased Country";

shared Orders = let
    Source = Csv.Document(File.Contents("orders.csv"), [Delimiter = ",", Columns = 5, Encoding = 65001]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers", {{"OrderId", Int64.Type},
        {"CustomerId", Int64.Type}, {"OrderDate", type date}, {"Amount", type number}, {"Status", type text}}),
    #"Filtered Rows" = Table.SelectRows(#"Changed Type", each [Status] <> "cancelled" and [Amount] >= MinimumAmount),
    #"Added Month" = Table.AddColumn(#"Filtered Rows", "Month", each Date.StartOfMonth([OrderDate]), type date),
    #"Added Size" = Table.AddColumn(#"Added Month", "Size", each if [Amount] >= 100 then "large" else "small", type text)
in
    #"Added Size";

shared OrdersWithCustomer = let
    Merged = Table.NestedJoin(Orders, {"CustomerId"}, Customers, {"CustomerId"}, "Customers", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Merged, "Customers", {"Customer", "Country"}, {"Customer", "Country"}),
    Removed = Table.RemoveColumns(Expanded, {"Status"}),
    Sorted = Table.Sort(Removed, {{"OrderId", Order.Ascending}})
in
    Sorted;

shared SalesByCountry = let
    Grouped = Table.Group(OrdersWithCustomer, {"Country"}, {
        {"Total", each List.Sum([Amount]), type number},
        {"Orders", each Table.RowCount(_), Int64.Type},
        {"Largest", each List.Max([Amount]), type number}}),
    Sorted = Table.Sort(Grouped, {{"Total", Order.Descending}})
in
    Sorted;

shared MonthlyBySize = let
    Picked = Table.SelectColumns(Orders, {"Month", "Size", "Amount"}),
    Pivoted = Table.Pivot(Picked, {"large", "small"}, "Size", "Amount", List.Sum),
    Sorted = Table.Sort(Pivoted, {"Month"})
in
    Sorted;
"""

ORDERS = """OrderId,CustomerId,OrderDate,Amount,Status
1,10,2024-01-05,120.00,shipped
2,11,2024-01-17,15.50,shipped
3,10,2024-02-02,40.00,shipped
4,12,2024-02-09,300.00,cancelled
5,12,2024-02-20,99.99,open
6,99,2024-03-01,100.00,open
"""


def shop(folder: Path) -> Any:
    (folder / "orders.csv").write_text(ORDERS, encoding="utf-8")
    database = duckdb.connect(str(folder / "shop.duckdb"))
    database.execute("CREATE SCHEMA dbo")
    database.execute(
        "CREATE TABLE dbo.Customers AS SELECT * FROM (VALUES (10, '  Ann Lee ', 'se'), (11, 'Bo Ek', 'no'), "
        "(12, 'Cy Dahl', 'se')) v(CustomerId, CustomerName, Country)"
    )
    database.close()

    def resolver(source: duckpq.Source) -> Any:
        if source.function == "Sql.Database" and source.arguments == ("shop-sql.example", "shop"):
            return str(folder / "shop.duckdb")
        return None

    return resolver


def test_the_shops_queries_run_to_the_expected_tables(tmp_path: Path) -> None:
    tables = duckpq.run(DOCUMENT, resolver=shop(tmp_path), folder=str(tmp_path))
    assert list(tables) == ["Customers", "Orders", "OrdersWithCustomer", "SalesByCountry", "MonthlyBySize"]
    assert tables["Customers"].fetchall() == [
        (10, "Ann Lee", "SE"),
        (11, "Bo Ek", "NO"),
        (12, "Cy Dahl", "SE"),
    ]
    day = dt.date
    assert tables["Orders"].columns == [
        "OrderId",
        "CustomerId",
        "OrderDate",
        "Amount",
        "Status",
        "Month",
        "Size",
    ]
    assert tables["Orders"].fetchall() == [
        (1, 10, day(2024, 1, 5), 120.0, "shipped", day(2024, 1, 1), "large"),
        (3, 10, day(2024, 2, 2), 40.0, "shipped", day(2024, 2, 1), "small"),
        (5, 12, day(2024, 2, 20), 99.99, "open", day(2024, 2, 1), "small"),
        (6, 99, day(2024, 3, 1), 100.0, "open", day(2024, 3, 1), "large"),
    ]
    assert tables["OrdersWithCustomer"].columns == [
        "OrderId", "CustomerId", "OrderDate", "Amount", "Month", "Size", "Customer", "Country",
    ]  # fmt: skip
    assert [(r[0], r[6], r[7]) for r in tables["OrdersWithCustomer"].fetchall()] == [
        (1, "Ann Lee", "SE"), (3, "Ann Lee", "SE"), (5, "Cy Dahl", "SE"), (6, None, None),
    ]  # fmt: skip
    assert tables["SalesByCountry"].fetchall() == [("SE", 259.99, 3, 120.0), (None, 100.0, 1, 100.0)]
    assert tables["MonthlyBySize"].columns == ["Month", "large", "small"]
    assert tables["MonthlyBySize"].fetchall() == [
        (day(2024, 1, 1), 120.0, None),
        (day(2024, 2, 1), None, 139.99),
        (day(2024, 3, 1), 100.0, None),
    ]


def test_a_parameter_given_changes_every_query_that_names_it(tmp_path: Path) -> None:
    tables = duckpq.run(
        DOCUMENT, resolver=shop(tmp_path), folder=str(tmp_path), parameters={"MinimumAmount": 100}
    )
    assert [r[0] for r in tables["Orders"].fetchall()] == [1, 6]
    assert tables["SalesByCountry"].fetchall() == [("SE", 120.0, 1, 120.0), (None, 100.0, 1, 100.0)]


def test_one_query_alone_reads_only_what_it_names(tmp_path: Path) -> None:
    """Orders names no database: it runs with no resolver at all."""
    shop(tmp_path)
    orders = duckpq.run_query(DOCUMENT, "Orders", folder=str(tmp_path))
    assert len(orders.fetchall()) == 4
