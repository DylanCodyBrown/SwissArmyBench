# /// swissarmybench-blade
# format = 1
# name = "Controller form with validation"
# kind = "snippet"
# description = "A range of numbers in a form, checked on Submit; the rows change only when it passes"
# tags = ["streamlit", "controller", "form"]
# family = "Controllers"
# language = "streamlit"
# cell_name = "<<label>> form"
# ///
snippet = r"""
# Form with validation: two numbers that take effect together when Submit is clicked, and only once
# they make sense; until then the rows stay as they were and the form says what to fix.
#
# Makes: <<name: in_range>>: table = <<table>>
#   the rows of <<table>> whose <<value column>> is between the two numbers last accepted
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.form(key)                    a form: the widgets inside `with` wait for its Submit button
#   st.number_input(label, value)   a box for a number, with - and + buttons
#   st.form_submit_button(label)    the form's Submit button: True on the rerun its click starts
#   st.session_state                a dictionary Streamlit keeps for each person's open page between reruns
#   st.error(text)                  a red message box: what to fix
#   st.caption(text)                small, quiet text
#
# Why st.session_state: the range accepted last must be kept while a wrong one is shown, and a
# plain variable starts over on every rerun. st.session_state survives the reruns.
import streamlit as st

_values = <<table>>["<<value column>>"]
_kept = "<<name>>_accepted"
if _kept not in st.session_state:  # the first run: every row
    st.session_state[_kept] = (float(_values.min()), float(_values.max()))
# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
with st.form("<<name>>_form"):
    _low = st.number_input("<<low label: From>>", value=st.session_state[_kept][0], key="<<name>>_low")
    _high = st.number_input("<<high label: To>>", value=st.session_state[_kept][1], key="<<name>>_high")
    _sent = st.form_submit_button("<<button: Show>>")
if _sent:
    if _low > _high:
        st.error(f"<<low label>> ({_low:,.2f}) is more than <<high label>> ({_high:,.2f}): swap them.")
    else:
        st.session_state[_kept] = (_low, _high)
_from, _to = st.session_state[_kept]
<<name>> = <<table>>[_values.between(_from, _to)]
st.caption(f"{len(<<name>>):,} rows from {_from:,.2f} to {_to:,.2f}")
"""
