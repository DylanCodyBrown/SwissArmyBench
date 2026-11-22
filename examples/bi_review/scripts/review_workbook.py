"""The month's review as an Excel workbook (made-up data): revenue by region, with a total row.

It reads the open table monthly_sales (DuckDB SQL over it), and the starter "Excel make a workbook" lays it
out by the design below (sab_excel builds it). It writes workbooks/monthly_review.xlsx at the project's top.
"""

from pathlib import Path

import swissarmybench as sab

make_workbook = sab.blade("Excel make a workbook")
by_region = sab.sql("""
SELECT region, sum(orders) AS orders, round(sum(revenue), 2) AS revenue
FROM monthly_sales GROUP BY region ORDER BY revenue DESC
""")
DESIGN = {
    "title": "Larkfield monthly sales review",
    "sheets": [
        {
            "name": "Review",
            "freeze": "A3",
            "blocks": [
                {"id": "title", "kind": "title", "cell": "A1", "text": "Revenue by region", "w": 3},
                {
                    "id": "regions",
                    "kind": "table",
                    "cell": "A2",
                    "source": {"table": "by_region"},
                    "total_row": True,
                    "columns": [
                        {"name": "region", "label": "Region", "width": 18},
                        {"name": "orders", "format": "integer", "total": "sum"},
                        {"name": "revenue", "format": "currency", "total": "sum"},
                    ],
                    "conditional": [{"column": "revenue", "op": "<", "value": 350000, "fill": "F8D7DA"}],
                },
            ],
        }
    ],
}
OUT = Path(__file__).resolve().parents[1] / "workbooks" / "monthly_review.xlsx"
OUT.parent.mkdir(exist_ok=True)
made = make_workbook(OUT, {"by_region": by_region}, DESIGN)
print(made)
