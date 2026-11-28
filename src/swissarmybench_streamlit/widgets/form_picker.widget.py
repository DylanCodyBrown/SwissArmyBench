# /// swissarmybench-widget
# format = 1
# name = "form_picker"
# description = "Pick one of several forms"
# framework = "streamlit"
# group = "Forms"
# pack = "Form builder"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Out, key

label = "Form"
# The forms to pick from (data in): each a definition with its name, title and fields
forms = [
    {
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
    },
    {
        "name": "stock_count",
        "title": "Stock count",
        "fields": [
            {"name": "product", "label": "Product", "type": "text", "required": True},
            {"name": "counted", "label": "Counted", "type": "number", "required": True, "format": "0..10000"},
            {"name": "counted_on", "label": "Counted on", "type": "date", "required": True},
        ],
    },
]
# A list of forms to pick from instead (another widget's, or an endpoint's answer; not wired: the ones above)
forms_in: In[list[dict]] = None
# The picked form's definition, for the page's form_fill (it reads it by itself)
form_definition: Out[dict] = None


found = forms_in
choices = found if isinstance(found, list) and found else forms
titles = [f.get("title") or f.get("name") or f"Form {at + 1}" for at, f in enumerate(choices)]
if not titles:
    st.info("No forms to pick from.")
else:
    picked = st.selectbox(label, range(len(titles)), format_func=lambda at: titles[at], key=key("form"))
    chosen = choices[picked]
    form_definition = chosen
    needed = sum(1 for f in chosen.get("fields") or [] if f.get("required"))
    st.caption(f"{len(chosen.get('fields') or [])} fields, {needed} required")
