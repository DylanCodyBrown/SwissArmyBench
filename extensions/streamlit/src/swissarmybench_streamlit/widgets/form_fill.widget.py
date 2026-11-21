# /// swissarmybench-widget
# format = 1
# name = "form_fill"
# description = "Fill in any designed form, with its checks; Submit hands the answers on"
# framework = "streamlit"
# group = "Forms"
# pack = "Form builder"
# tags = []
# size = [6, 8]
# min_size = [3, 4]
# ///
import datetime
import re

import streamlit as st
from sab_canvas import Event, In, Out, key

# The form to fill when no definition comes in
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
# The form's definition from the page's form_picker or form_designer (wired by itself; not wired: the one above)
form_definition: In[dict] = None
button = "Submit"
# Said under a required field left empty
validation_message = "Fill this in."
thanks = "Thank you: your answers were handed on."
# Every submission so far, for the page's form_submissions (it reads them by itself)
form_submissions: Out[list[dict]] = None
# Fired on Submit: the submission (form, submitted_at, values); the Canvas wires what it does (call an API.py endpoint, set a page value, rerun)
saved: Event[dict] = None


def _range(text):
    found = re.fullmatch(r"\s*(-?[0-9.]+)\s*\.\.\s*(-?[0-9.]+)\s*", str(text or ""))
    return (float(found[1]), float(found[2])) if found else (None, None)


def _input(field, at):
    """One field drawn by its type; its value."""
    kind, label = field.get("type", "text"), field.get("label") or field.get("name", "")
    label += " :red[\\*]" if field.get("required") else ""
    start, where = field.get("default"), key(f"f{at}_{field.get('name', '')}")
    if kind == "number":
        low, high = _range(field.get("format"))
        return st.number_input(
            label,
            min_value=low,
            max_value=high,
            value=float(start) if start not in (None, "") else None,
            step=1.0,
            format="%g",
            key=where,
        )
    if kind == "money":
        return st.number_input(
            label,
            min_value=0.0,
            value=float(start) if start not in (None, "") else None,
            step=0.01,
            format="%.2f",
            key=where,
        )
    if kind == "date":
        return st.date_input(label, datetime.date.fromisoformat(start) if start else None, key=where)
    if kind == "choice":
        choices = field.get("choices") or []
        return st.selectbox(
            label,
            choices,
            index=choices.index(start) if start in choices else None,
            placeholder="Choose",
            key=where,
        )
    if kind == "yes/no":
        return st.radio(
            label,
            ["yes", "no"],
            index=["yes", "no"].index(start) if start in ("yes", "no") else None,
            horizontal=True,
            key=where,
        )
    if kind == "file":
        return st.file_uploader(label, key=where)
    if field.get("format") == "long":
        return st.text_area(label, start or "", key=where)
    return st.text_input(label, start or "", key=where)


def _problem(field, value):
    if value is None or value == "" or value == []:
        return validation_message if field.get("required") else None
    if field.get("type") == "number":
        low, high = _range(field.get("format"))
        if low is not None and not low <= value <= high:
            return f"Give a number from {low:g} to {high:g}."
    if (
        field.get("type") == "text"
        and field.get("format") not in (None, "", "long")
        and not re.fullmatch(field["format"], str(value))
    ):
        return "This does not have the right form."
    return None


def _plain(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "getvalue"):
        return {"file": value.name, "size": value.size}
    return value


found = form_definition
form = found if isinstance(found, dict) and found.get("fields") is not None else definition
fields = form.get("fields") or []
values = {}
with st.form(key("form")):
    if form.get("title"):
        st.markdown(f"**{form['title']}**")
    for at, field in enumerate(fields):
        values[field.get("name", f"field_{at}")] = _input(field, at)
    sent = st.form_submit_button(button)
if sent:
    problems = {f.get("name"): _problem(f, values.get(f.get("name"))) for f in fields}
    problems = {n: p for n, p in problems.items() if p}
    for field in fields:
        if field.get("name") in problems:
            st.markdown(f":red[{field.get('label') or field.get('name')}: {problems[field.get('name')]}]")
    if not problems:
        submission = {
            "form": form.get("name", ""),
            "submitted_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "values": {n: _plain(v) for n, v in values.items()},
        }
        form_submissions = [*(form_submissions or []), submission]
        saved(submission)
        st.success(thanks)
