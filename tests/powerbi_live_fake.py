"""A stand-in at the live link's seam: a running Power BI Desktop's open model
answering metadata and taking edits, and DAX for E's Local source. No Windows, .NET or Power BI Desktop is
needed (installing a .NET SDK here was refused). Made-up names only."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from swissarmybench_powerbi.domain import live_link as rules

PORT = 51234
FILE = r"C:\Users\made-up\Reports\Sales model.pbix"


class FakeDesktop:
    def __init__(self) -> None:
        self.model = rules.OpenModel(
            tables={
                "Sales": ["OrderKey", "CustomerKey", "ProductKey", "Amount"],
                "Customer": ["CustomerKey", "Region"],
                "Product": ["ProductKey", "Name"],
                "LocalDateTable_0001": ["Date"],
            },
            measures={},
            relationships=[("Sales", "CustomerKey", "Customer", "CustomerKey", True)],
        )
        self.applied: list[rules.Change] = []
        self.queries: list[str] = []

    def metadata(self) -> rules.OpenModel:
        return self.model

    def evaluate(self, dax: str) -> Any:
        self.queries.append(dax)
        return pa.table({"CustomerKey": [1, 2], "Region": ["North", "South"]})

    def apply(self, change: rules.Change) -> None:
        self.applied.append(change)
        if change.kind in ("measure_add", "measure_change"):
            self.model.measures[(change.table, change.name)] = change.expression
        elif change.kind == "relationship_add":
            self.model.relationships.append(
                (change.table, change.column, change.to_table, change.to_column, change.active)
            )


def instances() -> list[rules.Instance]:
    return [
        rules.Instance(
            PORT,
            r"C:\Users\made-up\AppData\Local\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces\w1",
            FILE,
        )
    ]
