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
from sab_canvas import key

_WIDGET = "admin_settings_form"
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
# The session state key the settings are handed to the page under ({"event": "save", ...})
save_event = "settings_saved"


def _save(payload):
    """The page's hand-off: {"event": "save", "widget": ..., "payload": ...} under save_event."""
    st.session_state[save_event] = {"event": "save", "widget": _WIDGET, "payload": payload}


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
        _save(values)
        st.success("Settings handed to the page.")
