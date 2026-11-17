# /// swissarmybench-blade
# format = 1
# name = "Streamlit session state counter"
# kind = "snippet"
# description = "A button that counts its clicks: a value kept between reruns"
# tags = ["streamlit", "interaction", "session state"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<title>> counter"
# ///
snippet = r"""
# Session state counter: a button that counts its clicks, to show how a value is kept between
# reruns.
#
# Makes: nothing (the count lives in st.session_state["<<name: clicks>>"])
# Reads: nothing
#
# Streamlit functions:
#   st.session_state        a dictionary Streamlit keeps for each person's open page between reruns
#   st.button(label)        a button: True on the rerun its click starts, False on every other
#   st.metric(label, value) a big number with its label
#
# Why it is needed: a click reruns the whole script from the top, so a plain `count = 0` would start
# again at 0 every time. st.session_state survives the reruns; it is forgotten when the page closes.
import streamlit as st

if "<<name>>" not in st.session_state:  # the first run only
    st.session_state["<<name>>"] = 0
# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
if st.button("<<label: Add one>>", key="<<name>>_button"):
    st.session_state["<<name>>"] += 1
st.metric("<<title: Clicks>>", st.session_state["<<name>>"])
"""
