"""workbook.py: a month's reconciliations as one Excel workbook, beside the app (made-up data).

    python workbook.py 2026-10            writes workbooks/forms_recon_2026_10.xlsx

Any project may deliver a workbook beside its own deliverable (Plans/excel.plan.md): this Streamlit project's
is its app; this is its monthly workbook. It reads the month's latest run of each reconciliation from the
project's sandbox through the adapter (adapter.py), and sab_excel (sab_excel.py) lays it out: both are the
project scaffold's files, beside this one. It runs without Swiss Army Bench.

Laid out top to bottom: the settings, the design, reading a month, making the workbook, the entry point.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ===== settings =====

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / ".sab" / "sandbox" / "sandbox.duckdb"  # the project's sandbox: where API.py keeps its runs
FOLDER = HERE / "workbooks"

# Each reconciliation's latest run of the month, and what did not match in those runs (DuckDB SQL).
RUNS = """SELECT recon_id, run_id, period, matched, differences, only_entries, only_source, duplicates
FROM recon_runs WHERE period = ? QUALIFY row_number() OVER (PARTITION BY recon_id ORDER BY run_id DESC) = 1
ORDER BY recon_id"""
RESULTS = f"""SELECT r.recon_id, s.status, s.record_key, s.difference, s.fields_off
FROM recon_results s JOIN ({RUNS.rpartition("ORDER BY")[0]}) r USING (run_id)
WHERE s.status <> 'matched' ORDER BY r.recon_id, s.status, s.record_key"""


# ===== the design: what the workbook looks like (plain data; sab_excel builds it) =====


def design(period: str) -> dict[str, Any]:
    """A Summary sheet (each reconciliation's counts, a chart) and a sheet of what did not match."""
    counts = ["matched", "differences", "only_entries", "only_source", "duplicates"]
    return {
        "title": f"Reconciliations {period}",
        "sheets": [
            {
                "name": "Summary",
                "freeze": "A4",
                "print": {
                    "orientation": "landscape",
                    "fit_width": True,
                    "footer": f"Reconciliations {period}",
                },
                "blocks": [
                    {
                        "id": "title",
                        "kind": "title",
                        "cell": "A1",
                        "text": f"Reconciliations, {period}",
                        "w": 6,
                    },
                    {
                        "id": "runs",
                        "kind": "table",
                        "cell": "A3",
                        "source": {"table": "runs"},
                        "total_row": True,
                        "columns": [
                            {"name": "recon_id", "label": "Reconciliation", "width": 28},
                            *({"name": c, "format": "integer", "total": "sum"} for c in counts),
                        ],
                        "conditional": [{"column": "differences", "op": ">", "value": 0, "fill": "F8D7DA"}],
                    },
                    {
                        "id": "chart",
                        "kind": "chart",
                        "cell": "I3",
                        "chart": "column",
                        "from": "runs",
                        "category": "Reconciliation",
                        "series": ["differences", "only_entries", "only_source", "duplicates"],
                        "title": "What did not match",
                    },
                ],
            },
            {
                "name": "To look at",
                "freeze": "A2",
                "blocks": [
                    {
                        "id": "results",
                        "kind": "table",
                        "cell": "A1",
                        "source": {"table": "results"},
                        "filter": True,
                        "columns": [
                            {"name": "recon_id", "label": "Reconciliation", "width": 28},
                            {"name": "status", "label": "Status"},
                            {"name": "record_key", "label": "Key", "width": 24},
                            {"name": "difference", "label": "Difference", "format": "number"},
                            {"name": "fields_off", "label": "Fields off", "width": 30},
                        ],
                    }
                ],
            },
        ],
    }


# ===== reading: a month's latest runs and what did not match, through the adapter =====


def read_month(period: str, sandbox: Path = SANDBOX) -> dict[str, Any]:
    """The month's grids, as Arrow: `runs` (one row a reconciliation) and `results` (what did not match)."""
    import adapter  # the project scaffold's adapter.py, beside this file

    source = adapter.DuckDB.file(str(sandbox))
    runs = adapter.query(source, RUNS, [period]).read_all()
    if not runs.num_rows:
        raise SystemExit(f"No reconciliation was run for {period}: run one in the app first.")
    return {"runs": runs, "results": adapter.query(source, RESULTS, [period]).read_all()}


# ===== writing: the month's workbook =====


def monthly_workbook(grids: dict[str, Any], period: str, folder: Path = FOLDER) -> str:
    """The month's workbook made from its grids: workbooks/forms_recon_<yyyy>_<mm>.xlsx. Its path."""
    import sab_excel  # the project scaffold's sab_excel.py, beside this file

    out = Path(folder) / f"forms_recon_{period.replace('-', '_')}.xlsx"
    made: str = sab_excel.build(grids, design(period), out=out)
    return made


# ===== the entry point =====


def main(argv: list[str] | None = None) -> str:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("Say the month: python workbook.py 2026-10")
    made = monthly_workbook(read_month(args[0]), args[0])
    print(f"Wrote {made}")
    return made


if __name__ == "__main__":
    main()
