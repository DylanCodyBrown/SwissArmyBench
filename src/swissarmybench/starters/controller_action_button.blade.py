# /// swissarmybench-blade
# format = 1
# name = "Controller action button"
# kind = "snippet"
# description = "A button whose callback puts the page's filters back, safely twice"
# tags = ["streamlit", "controller", "action"]
# family = "Controllers"
# language = "streamlit"
# cell_name = "<<label>>"
# ///
snippet = r"""
# Action button: a button that does one thing when clicked. Here it puts the page's filters back as
# they open, by forgetting the picks their widgets hold.
#
# Makes: nothing (it changes st.session_state, the picks)
# Reads: nothing
# Role: action
#
# Streamlit functions:
#   st.button(label, on_click)   a button; on_click is a function Streamlit runs on the click,
#                                before the page reruns
#   st.session_state             a dictionary Streamlit keeps for each person's open page between
#                                reruns: each widget's pick is in it, under the widget's key
#
# Why a callback: it runs before the rerun, so the whole page then sees what it did (a button's
# True comes too late for the widgets above it). st.session_state survives the reruns, so the picks
# stay until something forgets them: here, the callback.
#
# Idempotent: clicking twice leaves the page as one click does. The callback sets things to how
# they open; it never adds or counts, so a double click or an extra rerun does no harm.
import streamlit as st

_KEYS = [key.strip() for key in "<<widget keys: by_region_pick>>".split(",") if key.strip()]


def _put_back() -> None:
    for key in _KEYS:
        if key in st.session_state:
            del st.session_state[key]  # the widget opens again as it was written


# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
st.button("<<label: Clear the filters>>", on_click=_put_back, key="<<name: clear_filters>>_button")
"""
