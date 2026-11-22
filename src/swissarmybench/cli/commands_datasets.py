"""The agent's datasets_* commands: datasets: loading, closing, Python sessions.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _q, command, opt, req


@command("datasets_list", "Open datasets with their sizes, plus the memory budget. No cell values.")
def list_datasets(a: dict[str, Any]) -> Any:
    return api.call("GET", "/datasets")


@command(
    "datasets_close",
    "Close a dataset and every grid on it (the Datasets popover's Close).",
    req("name", "Dataset name."),
)
def delete_dataset(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/datasets/{_q(a['name'])}")


@command(
    "datasets_rename",
    "Call a table by another name everywhere: its tabs, its grids (steps kept), the relationship model "
    "(a double-click on the tab, or the Pasted toast's name box).",
    req("name", "The table's name now."),
    req("to", "Its new name: 1 to 64 letters, digits, '_' or '-'."),
)
def rename_dataset(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/datasets/{_q(a['name'])}/rename", {"to": a["to"]})


@command(
    "datasets_load",
    "Load a CSV, TSV, Parquet, JSON-lines, Arrow or Excel file from a full path into a dataset and open a grid.",
    req("name", "New dataset name."),
    req("path", "Full path to the file. Pass the path, never the contents."),
    opt("sheet", "Sheet name for a workbook with several sheets (the error lists them)."),
    opt("new_grid", "Open a new grid even when the dataset already has one.", "bool"),
)
def load(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {"path": a["path"]}
    if a.get("sheet"):
        body["sheet"] = a["sheet"]
    if a.get("new_grid") is not None:
        body["new_grid"] = a["new_grid"]
    result = api.call("POST", f"/datasets/{_q(a['name'])}/load", body)
    return {k: result.get(k) for k in ("dataset", "grid", "version")}


@command(
    "datasets_sheets", "The sheet names of an Excel workbook.", req("path", "Full path to the .xlsx file.")
)
def sheets(a: dict[str, Any]) -> Any:
    return api.call("POST", "/files/sheets", {"path": a["path"]})


@command(
    "datasets_paste",
    "Make a dataset from pasted text (CSV, TSV or a copied table), the Paste button.",
    req("name", "New dataset name."),
    req("text", "The pasted text."),
)
def paste(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/datasets/{_q(a['name'])}/paste", a["text"])


@command(
    "datasets_sample",
    "Open the made-up sample store: customers, products, orders (Try it with sample data)",
)
def datasets_sample(a: dict[str, Any]) -> Any:
    return api.call("POST", "/samples/store")


@command(
    "datasets_python_sessions",
    "Python sessions (notebooks, scripts) reporting tables to the grid, and their tables.",
)
def list_processes(a: dict[str, Any]) -> Any:
    return api.call("GET", "/processes")


@command(
    "datasets_open_from_python",
    "Ask a running Python session to send one of its tables (datasets_python_sessions lists them)",
    req("process", "The session's id."),
    req("name", "The table's name in that session."),
)
def datasets_open_from_python(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/processes/{_q(a['process'])}/open", {"name": a["name"]})
