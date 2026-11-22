"""The agent's compare_* commands: compare (two grids side by side).

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _q, command, opt, req


@command(
    "compare_create",
    "Line two grids up on key columns (the page's split compare). Counts only.",
    req("left", "Left grid id."),
    req("right", "Right grid id."),
    req("keys", "[[left column, right column], ...]", "json"),
    opt("mode", "outer (default), anti, cross or diff."),
    opt("anti_side", "For anti: left or right."),
    opt(
        "show",
        "true: the user's grid page puts the two grids side by side, lined up (the Key Finder's Compare on these).",
        "bool",
    ),
)
def compare_create(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {
        "left": a["left"],
        "right": a["right"],
        "keys": a["keys"],
        "mode": a.get("mode") or "outer",
    }
    if a.get("anti_side"):
        body["anti_side"] = a["anti_side"]
    if a.get("show") is not None:
        body["show"] = a["show"]
    return api.call("POST", "/compares", body)


@command(
    "compare_list",
    "The compares that are running (the user's too: the two grids side by side), each with its id, its "
    "two grids and tables, keys, mode and counts.",
)
def compare_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/compares")


@command("compare_read", "A compare's counts: matched, left only, right only.", req("compare", "Compare id."))
def compare_read(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/compares/{_q(a['compare'])}")


@command(
    "compare_change",
    "Change a compare's keys, mode (outer, anti, cross, diff), anti side or diff options.",
    req("compare", "Compare id."),
    opt("keys", "[[left column, right column], ...]", "json"),
    opt("mode", "outer, anti, cross or diff (only rows that differ)."),
    opt("anti_side", "left or right."),
    opt(
        "diff",
        "{tolerance, percent, trim, ignore_case, skip: [cols], column, only_differing: the page shows "
        "only the keys and the columns that differ (true unless set false)}.",
        "json",
    ),
)
def compare_change(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("keys", "mode", "anti_side", "diff") if a.get(k) is not None}
    return api.call("PATCH", f"/compares/{_q(a['compare'])}", body)


@command(
    "compare_tie_out",
    "Do both grids add up the same per group? Without group or measures: the choices.",
    req("compare", "Compare id."),
    opt("group", "Shared columns to group by.", "json"),
    opt("measures", "Shared number columns to total.", "json"),
    opt("tolerance", "Still ties within this (0).", "json"),
    opt("tolerance_kind", "absolute or percent."),
)
def compare_tie_out(a: dict[str, Any]) -> Any:
    path = f"/compares/{_q(a['compare'])}/tie-out"
    if a.get("group") is None and a.get("measures") is None:
        return api.call("GET", path)
    body = {k: a[k] for k in ("group", "measures", "tolerance", "tolerance_kind") if a.get(k) is not None}
    return api.call("POST", path, body)


@command("compare_remove", "Stop a compare (Stop compare).", req("compare", "Compare id."))
def compare_remove(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/compares/{_q(a['compare'])}")


@command(
    "compare_rows",
    "One side's rows of a compare, aligned, with the cells that differ.",
    req("compare", "Compare id."),
    req("side", "left or right."),
    opt("start", "First row.", "int"),
    opt("end", "End row, exclusive.", "int"),
    values=True,
)
def compare_rows(a: dict[str, Any]) -> Any:
    params = {"side": a["side"], "start": a.get("start"), "end": a.get("end")}
    return api.call("GET", f"/compares/{_q(a['compare'])}/rows", params=params)


@command(
    "compare_key_group",
    "The rows a compare row's key also covers.",
    req("compare", "Compare id."),
    req("row", "Compare row position.", "int"),
    values=True,
)
def compare_key_group(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/compares/{_q(a['compare'])}/key-group", params={"row": a["row"]})


@command(
    "compare_set_focus",
    "Cross compare: pick a row on one side to filter the other.",
    req("compare", "Compare id."),
    req("side", "left or right."),
    req("position", "The picked row.", "int"),
)
def compare_set_focus(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", f"/compares/{_q(a['compare'])}/focus", {"side": a["side"], "position": a["position"]}
    )


@command("compare_clear_focus", "Cross compare: clear the picked row.", req("compare", "Compare id."))
def compare_clear_focus(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/compares/{_q(a['compare'])}/focus")


@command(
    "compare_grids",
    "One-shot compare of two grids on key columns: matched, left-only and right-only counts. No cell values.",
    req("left", "Left grid id."),
    req("right", "Right grid id."),
    req("keys", "[[left column, right column], ...]", "json"),
)
def compare_grids(a: dict[str, Any]) -> Any:
    made = api.call(
        "POST", "/compares", {"left": a["left"], "right": a["right"], "keys": a["keys"], "mode": "outer"}
    )
    try:
        return {"left": a["left"], "right": a["right"], "keys": a["keys"], "counts": made.get("counts")}
    finally:
        api.call("DELETE", f"/compares/{made['compare']}")


@command(
    "compare_tie_out_show",
    "Filter both grids of a compare to one tie-out group (as clicking its row)",
    req("compare", "The compare's id."),
    req("group", "The grouping columns, as the tie-out gave them.", "list"),
    req("keys", "The group's keys, as the tie-out gave them.", "list"),
)
def compare_tie_out_show(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", f"/compares/{_q(a['compare'])}/tie-out/show", {"group": a["group"], "keys": a["keys"]}
    )
