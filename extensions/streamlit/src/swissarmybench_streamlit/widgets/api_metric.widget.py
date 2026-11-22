# /// swissarmybench-widget
# format = 1
# name = "api_metric"
# description = "One number from an API action's answer (the local sandbox API's GET, or any API's)"
# framework = "streamlit"
# group = "Data"
# tags = ["api"]
# size = [3, 2]
# min_size = [2, 1]
# ///
import os
import re

import streamlit as st
from sab_canvas import Out, action, said

# The action it reads (a GET answering a value, an object, or a list: its first row, or how many)
endpoint = ""  # endpoint
# One box per {name} in the endpoint's path: a value, a variable or a page value
path_values = {}  # path values of endpoint
# The answer's field that holds the number, by its path (empty: the value, or how many rows a list holds)
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
    st.metric(label, "-")
    st.caption("Pick the endpoint in Properties.")
else:
    inputs, missing = _inputs(endpoint, path_values)
    answer = None if missing else action(endpoint, inputs)
    problem = f"Give {missing} in Properties (its path box)." if missing else said(answer)
    if problem:
        st.metric(label, "-")
        st.caption(problem)
    else:
        # The envelope by its kind: records (how many, or the first one's field), a record's field, a value.
        if answer["kind"] == "records":
            found = answer["records"]
            value = (found[0].get(field) if found else None) if field else len(found)
        elif answer["kind"] == "record":
            value = answer["flat"].get(field) if field else answer["record"]
        else:
            value = answer.get("value", answer.get("text"))
        st.metric(label, f"{prefix}{value}{suffix}")
