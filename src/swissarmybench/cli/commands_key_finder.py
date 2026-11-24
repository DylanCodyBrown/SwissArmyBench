"""The agent's key_finder_* commands: key Finder.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _q, command, opt, req


@command(
    "key_finder_candidates",
    "The open tables the Key Finder can compare this one against.",
    req("grid", "The open table's id."),
)
def key_finder_candidates(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/grids/{_q(a['grid'])}/key-finder")


@command(
    "key_finder_run",
    "Key Finder: likely join columns between an open table and another (or every other open table with target='*'), "
    "plus the table's likely primary key. Counts only, no cell values.",
    req("grid", "The open table's id."),
    opt("target", "Another open table's id, or * for all (default *)."),
    opt("trim", "Trim text first (default true).", "bool"),
    opt("ignore_case", "Ignore case (default false).", "bool"),
    opt("max_length", "Skip columns with longer values (default 128).", "int"),
    opt("top", "Keep this many pairs (default 25).", "int"),
)
def key_finder_run(a: dict[str, Any]) -> Any:
    options = {
        "trim": True if a.get("trim") is None else a["trim"],
        "ignore_case": bool(a.get("ignore_case")),
        "max_length": int(a.get("max_length") or 128),
    }
    result = api.call(
        "POST", f"/grids/{_q(a['grid'])}/key-finder", {"target": a.get("target") or "*", "options": options}
    )
    result["pairs"] = result["pairs"][: max(1, int(a.get("top") or 25))]
    return result


@command(
    "key_finder_sample",
    "Values a column pair shares and does not (the Key Finder's sample)",
    req("grid", "The open table's id."),
    req("target", "The other table's id."),
    req("source_column", "This table's column."),
    req("target_column", "The other table's column."),
    opt("options", '{"trim", "ignore_case", "max_length"}', "json"),
    values=True,
)
def key_finder_sample(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("target", "source_column", "target_column")} | {
        "options": a.get("options") or {}
    }
    return api.call("POST", f"/grids/{_q(a['grid'])}/key-finder/sample", body)
