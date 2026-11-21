# /// swissarmybench-widget
# format = 1
# name = "api_metric"
# description = "One number from a local sandbox API's GET endpoint"
# framework = "streamlit"
# group = "Data"
# tags = ["api"]
# size = [3, 2]
# min_size = [2, 1]
# ///
import os
import re
import urllib.parse

import streamlit as st
from sab_canvas import Out, api_call

# The endpoint it reads (a GET answering an object, or a list: its first row, or how many)
endpoint = ""  # endpoint
# One box per {name} in the endpoint's path: a value, a variable or a page value
path_values = {}  # path values of endpoint
# The answer's field that holds the number (empty: how many rows a list holds)
field = ""
label = "Value"
prefix = ""
suffix = ""
# The number shown, for the widgets on the page that read it
value: Out[float] = None


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


def _path(wanted, values):
    """The endpoint's method and path, its {names} filled from `values` (None: one is missing)."""
    method, _, path = (wanted or "").partition(" ")
    for name in re.findall(r"\{(\w+)\}", path):
        given = _given(values[name]) if name in values else None
        if given is None or given == "":
            return method, None, name
        path = path.replace("{" + name + "}", urllib.parse.quote(str(given), safe=""))
    return method, path, None


if not endpoint:
    st.metric(label, "-")
    st.caption("Pick the endpoint in Properties.")
else:
    method, path, missing = _path(endpoint, path_values)
    answer, problem = (
        (None, f"Give {missing} in Properties (its path box).") if missing else api_call(method, path)
    )
    if problem:
        st.metric(label, "-")
        st.caption(problem)
    else:
        row = answer[0] if isinstance(answer, list) and answer and field else answer
        value = (
            len(answer)
            if isinstance(answer, list) and not field
            else (row or {}).get(field)
            if isinstance(row, dict)
            else row
        )
        st.metric(label, f"{prefix}{value}{suffix}")
