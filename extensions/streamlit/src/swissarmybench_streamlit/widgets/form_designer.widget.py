# /// swissarmybench-widget
# format = 1
# name = "form_designer"
# description = "Design a form: add, rename, order and remove fields, each with its type and checks"
# framework = "streamlit"
# group = "Forms"
# pack = "Form builder"
# tags = []
# size = [10, 7]
# min_size = [6, 4]
# ///
import re

import pandas as pd
import streamlit as st
from sab_canvas import key

_WIDGET = "form_designer"
_TYPES = ["text", "number", "money", "date", "choice", "yes/no", "file"]
# The form to start from (data in): a name, a title and its fields
definition = {
    "name": "site_visit",
    "title": "Site visit report",
    "fields": [
        {
            "name": "store",
            "label": "Store",
            "type": "choice",
            "required": True,
            "choices": ["Larkfield Shop", "Marshby Depot", "Fernhaven Shop"],
        },
        {"name": "visited_on", "label": "Visited on", "type": "date", "required": True},
        {"name": "visitor", "label": "Your name", "type": "text", "required": True},
        {"name": "staff_on_duty", "label": "Staff on duty", "type": "number", "format": "0..50"},
        {"name": "till_float", "label": "Till float", "type": "money"},
        {"name": "clean", "label": "Shop floor clean", "type": "yes/no", "default": "yes"},
        {"name": "photo", "label": "A photo", "type": "file"},
        {"name": "notes", "label": "Notes", "type": "text", "format": "long"},
    ],
}
# The session state key a definition may come from instead, and is kept under on Save (data out)
definition_key = "form_definition"
button = "Save form"
# The session state key the form is handed to the page under ({"event": "save", ...})
save_event = "form_saved"


def _save(payload):
    """The page's hand-off: {"event": "save", "widget": ..., "payload": ...} under save_event."""
    st.session_state[save_event] = {"event": "save", "widget": _WIDGET, "payload": payload}


start = st.session_state.get(definition_key) if definition_key else None
form = start if isinstance(start, dict) and start.get("fields") is not None else definition
left, right = st.columns(2)
title = left.text_input("Title :red[\\*]", form.get("title", ""), key=key("title"))
name = right.text_input(
    "Name :red[\\*]", form.get("name", ""), key=key("name"), help="Small letters, digits and _"
)
rows = pd.DataFrame(
    [
        {
            "order": at + 1,
            "name": f.get("name", ""),
            "label": f.get("label", ""),
            "type": f.get("type", "text"),
            "required": bool(f.get("required")),
            "choices": ", ".join(str(c) for c in f.get("choices") or []),
            "default": str(f.get("default", "") or ""),
            "format": str(f.get("format", "") or ""),
        }
        for at, f in enumerate(form.get("fields") or [])
    ],
    columns=["order", "name", "label", "type", "required", "choices", "default", "format"],
)
st.caption("Add a row for a field, change its order number to move it, select a row and Delete to remove it.")
edited = st.data_editor(
    rows,
    num_rows="dynamic",
    hide_index=True,
    use_container_width=True,
    column_config={
        "order": st.column_config.NumberColumn("Order", min_value=1, step=1, width="small"),
        "name": st.column_config.TextColumn("Name *", required=True),
        "label": st.column_config.TextColumn("Label"),
        "type": st.column_config.SelectboxColumn("Type *", options=_TYPES, required=True),
        "required": st.column_config.CheckboxColumn("Required"),
        "choices": st.column_config.TextColumn(
            "Choices", help="For a choice: its choices, with commas between"
        ),
        "default": st.column_config.TextColumn("Default"),
        "format": st.column_config.TextColumn(
            "Format", help="A number's range (0..50), a text's pattern, long for several lines"
        ),
    },
    key=key("fields"),
)


def _definition(edited):
    fields = []
    for _, row in edited.sort_values("order", na_position="last").iterrows():
        if not str(row["name"] or "").strip():
            continue
        field = {
            "name": str(row["name"]).strip(),
            "label": str(row["label"] or row["name"]).strip(),
            "type": row["type"] or "text",
        }
        if bool(row["required"]):
            field["required"] = True
        if field["type"] == "choice":
            field["choices"] = [c.strip() for c in str(row["choices"] or "").split(",") if c.strip()]
        for extra in ("default", "format"):
            if str(row[extra] or "").strip():
                field[extra] = str(row[extra]).strip()
        fields.append(field)
    return {"name": name.strip(), "title": title.strip(), "fields": fields}


made = _definition(edited)
problems = []
if not made["title"]:
    problems.append("Give the form a title.")
if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", made["name"]):
    problems.append("Give the form a name: small letters, digits and _ , starting with a letter.")
names = [f["name"] for f in made["fields"]]
problems += [
    f"Two fields are called {n}: give one another name."
    for n in sorted({n for n in names if names.count(n) > 1})
]
problems += [
    f"{f['name']}: a choice needs its choices."
    for f in made["fields"]
    if f["type"] == "choice" and not f.get("choices")
]
problems += [
    f"{n}: a field's name is small letters, digits and _ ."
    for n in names
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", n)
]
for problem in problems:
    st.markdown(f":red[{problem}]")
st.caption(f"{len(made['fields'])} fields")
if st.button(button, key=key("save"), type="primary", disabled=bool(problems)):
    if definition_key:
        st.session_state[definition_key] = made
    _save(made)
    st.success(f"{made['title']} handed to the page.")
