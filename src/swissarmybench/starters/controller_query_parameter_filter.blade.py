# /// swissarmybench-blade
# format = 1
# name = "Controller query parameter filter"
# kind = "snippet"
# description = "A dropdown filter kept in the page's address (?region=South), so a link opens it filtered"
# tags = ["streamlit", "controller", "filter", "link"]
# family = "Controllers"
# language = "streamlit"
# cell_name = "<<label>> filter (in the address)"
# ///
snippet = r"""
# Query parameter filter: the pick is in the page's address, as ?<<param: {column}>>=South, so a link
# opens the page already filtered, and the address follows the reader's picks (to send on).
#
# Makes: <<pick name: {column}>>: str = "All"; <<name: by_{column}>>: table = <<table>>
#   <<pick name>>: the value picked, as text ("All": every value)
#   <<name>>: the rows of <<table>> whose <<column>> is the one picked
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.query_params                       the address's ?name=value parts, like a dictionary: read
#                                         one, set one (the address changes), or delete one
#   st.selectbox(label, options, index)   a dropdown that opens on options[index]
#
# A value in the address that no option has (a typo, an old link) opens on "All" instead of
# stopping the page.
import streamlit as st

_PARAM = "<<param>>"
_options = ["All", *sorted(<<table>>["<<column>>"].dropna().astype(str).unique())]
_asked = st.query_params[_PARAM] if _PARAM in st.query_params else "All"
# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
<<pick name>> = st.selectbox(
    "<<label>>",
    _options,
    index=_options.index(_asked) if _asked in _options else 0,
    key="<<name>>_pick",
)
if <<pick name>> == "All":
    if _PARAM in st.query_params:
        del st.query_params[_PARAM]  # the plain address: every value
    <<name>> = <<table>>
else:
    st.query_params[_PARAM] = <<pick name>>
    <<name>> = <<table>>[<<table>>["<<column>>"].astype(str) == <<pick name>>]
"""
