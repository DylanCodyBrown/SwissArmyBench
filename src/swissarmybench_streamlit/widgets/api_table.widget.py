# /// swissarmybench-widget
# format = 1
# name = "api_table"
# description = "An API action's records as a table, a page at a time (the local sandbox API's GET, or any API's)"
# framework = "streamlit"
# group = "Data"
# tags = ["api"]
# size = [6, 4]
# min_size = [3, 2]
# ///
import os
import re

import streamlit as st
from sab_canvas import Out, Table, action, key, said

# The action whose records it shows (a GET that answers a list), read through api_adapter
endpoint = ""  # endpoint
# One box per {name} in the endpoint's path: a value, a variable or a page value
path_values = {}  # path values of endpoint
# Rows a page
page_size = 20  # 1..500
# The page of rows shown, for the widgets on the page that read it
rows: Out[Table] = None
# The query's names for the page (its limit and offset parameters)
limit_name = "limit"
offset_name = "offset"


def _given(value):
    """A path box's value: as typed, ${NAME} (a variable of this computer) or {{ name }} (a page value: the
    page's own st.session_state). None: not set."""
    text = str(value).strip()
    named = re.fullmatch(r"\$\{([A-Za-z_]\w*)\}", text)
    if named:
        return os.environ.get(named.group(1))
    paged = re.fullmatch(r"\{\{\s*([A-Za-z_]\w*)\s*\}\}", text)
    if paged:
        found = st.session_state.get(paged.group(1))
        return None if found is None or found == "" else found
    return value


def _inputs(wanted, values):
    """The action's path inputs, each {name} given from `values`: (inputs, None), or (None, the one missing)."""
    found = {}
    for name in dict.fromkeys(re.findall(r"\{(\w+)\}", wanted or "")):
        given = _given(values[name]) if name in values else None
        if given is None or given == "":
            return None, name
        found[name] = given
    return found, None


if not endpoint:
    st.info("Pick the endpoint in Properties: a GET of an API.")
else:
    inputs, missing = _inputs(endpoint, path_values)
    page = st.session_state.get(key("page"), 0)
    if missing:
        st.warning(f"Give {missing} in Properties (its path box).")
    else:
        answer = action(endpoint, inputs, query={limit_name: page_size, offset_name: page * page_size})
        if not answer["ok"]:
            st.info(said(answer))
        else:
            # The envelope's records (fields by path: customer.id); one record a table of one row.
            rows = answer["records"] if answer["kind"] == "records" else [answer.get("flat") or {}]
            st.dataframe(rows, use_container_width=True, hide_index=True)
            left, middle, right = st.columns([1, 2, 1])
            if left.button("Previous", key=key("previous"), disabled=page == 0):
                st.session_state[key("page")] = page - 1
                st.rerun()
            middle.caption(f"Page {page + 1}")
            full = answer["paging"]["more"] or len(rows) >= page_size
            if right.button("Next", key=key("next"), disabled=not full):
                st.session_state[key("page")] = page + 1
                st.rerun()
