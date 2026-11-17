# /// swissarmybench-blade
# format = 1
# name = "Streamlit form with submit"
# kind = "snippet"
# description = "Fields that take effect together, when Submit is clicked"
# tags = ["streamlit", "interaction", "form"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>> form"
# ///
snippet = r"""
# Form with Submit: fields whose values take effect together, only when Submit is clicked.
#
# Makes: <<name: chosen>>
#   the rows of <<table>> whose <<value column>> is at least the amount in the form
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.form(key)                    a form: the widgets inside `with` wait for its Submit button
#   st.number_input(label, value)   a box for a number, with - and + buttons
#   st.form_submit_button(label)    the form's Submit button: True on the rerun its click starts
#   st.caption(text)                small, quiet text
#
# Outside a form, each widget reruns the page as soon as it changes. Inside one, the page reruns only
# when Submit is clicked, so several fields can be filled first.
import streamlit as st

with st.form("<<name>>_form"):
    _least = st.number_input("<<label: Smallest amount>>", value=0.0, step=10.0)
    _sent = st.form_submit_button("<<button: Show>>")
<<name>> = <<table>>[<<table>>["<<value column>>"] >= _least]
if _sent:
    st.caption(f"{len(<<name>>):,} rows of {_least:,.2f} or more")
"""
