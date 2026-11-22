"""The Accounting extension: what it is and what it brings, as the base reads it (its entry point:
`accounting = "swissarmybench_accounting.extension"` in the group `swissarmybench.extensions`).

  ID, NAME, DESCRIPTION, ADDS   the extension, said for the Extensions page and context.md
  PROJECT_TYPE, MODE            the project type it adds and its mode, as DATA (Plans/editions.plan.md,
                                "Project modes"): the Excel canvas, Excel and accounting families, Python,
                                no extra cell kinds, the agent's tool group, the export
  FRONT_END                     the front-end plug-ins it names (they live in the shared web/)
  routes(services)              its routes, given the base's services (bootstrap's Services)
  scaffold(name, data_names)    an Accounting project's own files: workbook.design.json, workbook.py,
                                templates/
  COMMANDS                      its agent commands (commands.py), added to the base's registry when on
"""

from __future__ import annotations

from typing import Any

from swissarmybench_accounting import __version__

ID = "accounting"
NAME = "Accounting"
VERSION = __version__
DESCRIPTION = (
    "Accounting work whose deliverable is an Excel workbook, built by a Python automation that runs anywhere."
)
ADDS = [
    "The Accounting project: data.ipynb, workbook.py and workbook.design.json",
    "The Excel canvas: sheets of tables, pivots (summaries DuckDB computes), Excel's own charts, formats",
    "Templates imported from existing workbooks, bound to data",
    "Cession statements and invoices built from a template: dry run first, numbered, dated, a register",
]
PROJECT_TYPE = "accounting"
FRONT_END = ["excel-canvas"]
# Its commands' areas (cli/commands.py AREAS: the prefix, then what it works on).
AREAS = (
    (
        "workbook",
        "Accounting: a workbook's design on the Excel canvas (sheets, blocks), Play, Export workbook.py",
    ),
    ("template", "Accounting: templates imported from existing workbooks, their places bound to data"),
    ("statements", "Accounting: statements and invoices built from a template (dry run first), the register"),
)
MODE: dict[str, Any] = {
    "type": PROJECT_TYPE,
    "name": NAME,
    "deliverable": "an Excel workbook",
    "canvases": ["excel"],
    "families": ["Excel", "Write", "Files"],
    "languages": ["python"],
    "cell_kinds": [],
    "tools": ["workbook_", "template_", "statements_"],
    "export": ["workbook.py", "workbook"],
    # The Project Explorer's words for beginners.
    "title": "Accounting workbook",
    "for_whom": "For accountants who hand over the same Excel workbook every month or quarter.",
    "explain": (
        "Design the workbook once: sheets of tables, pivots and charts from your data. A Python automation "
        "builds it again whenever the data changes. You get data.ipynb, workbook.design.json and workbook.py."
    ),
    "example": "Example: the quarterly cession statements for each reinsurer, built in one click.",
}
# The Accounting project's own functions, beside the Excel starters (Insert a function…).
FUNCTIONS = [
    {
        "name": "build_statements",
        "family": "Statements and invoices",
        "description": "One statement or invoice per group, from a template; dry run first",
        "code": 'plan = build_statements("templates/statement.xlsx", statements, lines, group_by=["cedant", "period"], out_folder="statements", name="{cedant} {period}.xlsx", dry_run=True)',
    },
    {
        "name": "fill_template",
        "family": "Statements and invoices",
        "description": "A template's places filled from one row and its lines",
        "code": 'book = fill_template("templates/invoice.xlsx", bindings, row, lines)',
    },
    {
        "name": "build_workbook",
        "family": "Statements and invoices",
        "description": "The design built into a workbook from the tables",
        "code": "build_workbook(DESIGN, load_tables(), 'workbook.xlsx')",
    },
]


def describe() -> dict[str, Any]:
    """What its entry point gives (`swissarmybench_accounting.extension:describe`): the extension as the
    Extensions page shows it, and its project type's mode."""
    return {
        "id": ID,
        "name": NAME,
        "description": DESCRIPTION,
        "version": VERSION,
        "adds": list(ADDS),
        "package": "swissarmybench-accounting",
        "project_type": PROJECT_TYPE,
        "mode": dict(MODE),
        "front_end": list(FRONT_END),
    }


def routes(services: Any) -> list[Any]:
    """Its routes, built from the base's services (the composition root's Services)."""
    from swissarmybench_accounting import routes as door
    from swissarmybench_accounting.service import Accounting

    def project_folder() -> str | None:
        current = services.sab_projects.current
        found = current.folder if current is not None else services.projects.opened
        return str(found) if found else None

    async def store_table(name: str, table: Any, kind: str, new_grid: bool, who: str) -> Any:
        return await services.datasets.store_table(name, table, kind, new_grid, who)

    accounting = Accounting(services.ws, services.agent.approvals, store_table, project_folder)

    def functions() -> dict[str, Any]:
        families = services.blades.starters()["families"]
        wanted = [f for f in families if f["family"] in ("Excel",)]
        writes = [
            b
            for f in families
            if f["family"] == "Write"
            for b in f["blades"]
            if "excel" in (b.get("tags") or [])
        ]
        listed = [{"family": f["family"], "functions": f["blades"]} for f in wanted]
        if writes:
            listed.append({"family": "Write", "functions": writes})
        return {"families": [{"family": "Statements and invoices", "functions": FUNCTIONS}, *listed]}

    return door.routes(accounting, MODE, functions)


def scaffold(name: str, data_names: list[str]) -> dict[str, Any]:
    """An Accounting project's files (beside data.ipynb and data.py): the design, its workbook.py, and the
    templates folder. No Streamlit app."""
    from swissarmybench_accounting import design as rules
    from swissarmybench_accounting import exporter, files

    made = rules.new_design(name)
    text = exporter.workbook_py(made, files.runtime_text(), rules.tables_read(made))
    import json

    return {
        "app": False,
        "files": {
            exporter.DESIGN_FILE: json.dumps(made, indent=2) + "\n",
            exporter.FILE: text,
            "templates/README.md": "Templates: existing workbooks imported here (Import template…), each with its\n<name>.bind.json beside it.\n",
        },
        "requirements": ["openpyxl>=3.1", "duckdb>=1.2", "pandas>=2.2"],
    }


def commands() -> dict[str, Any]:
    """Its agent commands, for the base's registry (cli/commands.py adds them when this is on)."""
    from swissarmybench_accounting.commands import COMMANDS

    return COMMANDS
