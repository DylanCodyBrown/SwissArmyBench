# /// swissarmybench-widget
# format = 1
# name = "admin_settings_form"
# description = "A form of named settings (text, numbers, switches); Save hands them on"
# framework = "streamlit"
# group = "Forms"
# pack = "Admin"
# tags = []
# size = [5, 5]
# min_size = [3, 3]
# ///
import streamlit as st
from sab_canvas import Event, key

title = "Settings"
# Each setting and its value: text, a whole number, a number or a switch (true/false)
settings = {
    "Company name": "Larkfield Goods",
    "Currency": "EUR",
    "Low stock warning": 10,
    "VAT rate": 0.2,
    "Send a daily email": True,
}
# The settings that must not be left empty
required = ["Company name", "Currency"]
button = "Save settings"
# Said under a required setting left empty
validation_message = "Fill this in."
# Fired on Save: the settings; the Canvas wires what it does (call an API.py endpoint, set a page value, rerun)
saved: Event[dict] = None


values = {}
with st.form(key("form")):
    if title:
        st.markdown(f"**{title}**")
    for at, (name, value) in enumerate((settings or {}).items()):
        label = name + (" :red[\\*]" if name in required else "")
        if isinstance(value, bool):
            values[name] = st.toggle(label, value, key=key(f"s{at}"))
        elif isinstance(value, int):
            values[name] = st.number_input(label, value=value, step=1, key=key(f"s{at}"))
        elif isinstance(value, float):
            values[name] = st.number_input(label, value=value, format="%.4g", key=key(f"s{at}"))
        else:
            values[name] = st.text_input(label, str(value), key=key(f"s{at}"))
    saved = st.form_submit_button(button)
if saved:
    empty = [n for n in required if str(values.get(n, "")).strip() == ""]
    for name in empty:
        st.markdown(f":red[{name}: {validation_message}]")
    if not empty:
        saved(values)
        st.success("Settings handed to the page.")
