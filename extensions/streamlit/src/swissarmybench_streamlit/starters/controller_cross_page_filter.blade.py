# /// swissarmybench-blade
# format = 1
# name = "Controller cross-page filter"
# kind = "snippet"
# description = "A dropdown filter whose pick follows the reader from page to page"
# tags = ["streamlit", "controller", "filter", "session state"]
# family = "Controllers"
# language = "streamlit"
# cell_name = "<<label>> filter (every page)"
# ///
snippet = r"""
# Cross-page filter: one pick for every page of the app. Put this cell on each page that needs it:
# a region picked on one page is the region on the next.
#
# Makes: <<pick name: {column}>>: str = "All"; <<name: by_{column}>>: table = <<table>>
#   <<pick name>>: the value picked, as text ("All": every value)
#   <<name>>: the rows of <<table>> whose <<column>> is the one picked
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.session_state                        a dictionary Streamlit keeps for each person's open
#                                           app between reruns, on every page
#   st.selectbox(label, options, index)     a dropdown that opens on options[index]
#
# Why not the widget's own pick: Streamlit forgets a widget's value once a page without it is
# shown. So the pick is copied (by on_change, when it changes) under a name of its own in
# st.session_state, which survives the reruns and the change of page; on each page the dropdown
# opens on it.
import streamlit as st

_SHARED = "<<shared name: every_page_{column}>>"
if _SHARED not in st.session_state:  # the app's first run
    st.session_state[_SHARED] = "All"
_options = ["All", *sorted(<<table>>["<<column>>"].dropna().astype(str).unique())]
_index = _options.index(st.session_state[_SHARED]) if st.session_state[_SHARED] in _options else 0


def _keep() -> None:
    st.session_state[_SHARED] = st.session_state["<<name>>_pick"]


# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
st.selectbox("<<label>>", _options, index=_index, key="<<name>>_pick", on_change=_keep)
<<pick name>> = st.session_state[_SHARED]
if <<pick name>> == "All":
    <<name>> = <<table>>
else:
    <<name>> = <<table>>[<<table>>["<<column>>"].astype(str) == <<pick name>>]
"""
