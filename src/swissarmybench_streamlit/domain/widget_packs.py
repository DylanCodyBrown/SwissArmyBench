"""Widget starter packs (the owner, 2026-11-21: "Build some widget starter packs" / "Preload the release
library with a ton of widgets that cover most objects"): prebuilt widgets grouped by the kind of page they
make. A widget names its pack in its header (`pack = "Sales dashboard"`); the Widgets window and the
Canvas's Widgets pane show each pack as a group of its own, in this order, before the plain groups, with
its description.

The widgets that read data take a table property (and its column properties) and show made-up rows until one
is picked, so a pack's page draws at once; a table property can later name an API's result. The ones that
hand data on (a form's Save, an approval) put a plain Python shape in the page's session state under their
`save_event` key: {"event": "save", "widget": ..., "payload": ...}, for the page (or a local API) to keep.

Pure rules: no I/O, standard library only.
"""

from __future__ import annotations

from typing import Any

PACKS: dict[str, str] = {
    "Sales dashboard": "A sales overview page: the KPIs, revenue by month, the top products, a map by region "
    "and the filter bar that drives them.",
    "Operations": "A stock and delivery page: inventory status, what is low, the shipments' timeline and how "
    "many are late.",
    "Customer service": "A support desk page: the ticket queue, one ticket's detail, tickets by status, the "
    "SLA met and a reply form.",
    "Data entry": "A page to add and correct records: a form made from a table, an editable grid, approve or "
    "reject, and the validation messages.",
    "Admin": "An administration page: the users, the audit log and a settings form.",
    "User inputs": "Every Streamlit input with its real options: a label, help, placeholder, default, "
    "required (the same marker and error look throughout), disabled and its session state key.",
    "Excel": "Workbooks in and out: upload and preview a sheet, map its columns, validate its rows, download "
    "tables and templates as formatted Excel, and the round trip.",
    "Form builder": "Design a form, pick one, fill it in with validation and see its submissions: "
    "definitions and submissions as plain JSON, handed to the page on Save.",
}


def order(pack: str) -> int:
    """A pack's place (an unknown one after the known; none at the end)."""
    names = list(PACKS)
    if not pack:
        return len(names) + 1
    return names.index(pack) if pack in PACKS else len(names)


def listing() -> list[dict[str, Any]]:
    return [{"name": name, "description": description} for name, description in PACKS.items()]
