# /// swissarmybench-widget
# format = 1
# name = "api_button"
# description = "A button that calls a local sandbox API's endpoint"
# framework = "streamlit"
# group = "Buttons"
# tags = ["api"]
# size = [3, 1]
# min_size = [2, 1]
# ///
import os
import re
import urllib.parse

import streamlit as st
from sab_canvas import Event, api_call, key

# The endpoint it calls
endpoint = ""  # endpoint
label = "Call"
# One box per {name} in the endpoint's path: a value, a variable or a page value
path_values = {}  # path values of endpoint
# The body it sends (a POST, PUT or PATCH)
body = {}
show_answer = True

# Fired once the endpoint answered ({"answer": ...}); the Canvas wires what it does next
answered: Event[dict] = None


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


if st.button(label, key=key("button"), disabled=not endpoint):
    method, path, missing = _path(endpoint, path_values)
    if missing:
        st.warning(f"Give {missing} in Properties (its path box).")
    else:
        answer, problem = api_call(method, path, body if method in ("POST", "PUT", "PATCH") else None)
        if problem:
            st.error(problem)
        else:
            answered({"answer": answer})
            if show_answer:
                st.json(answer)
            else:
                st.success("Done.")
if not endpoint:
    st.caption("Pick the endpoint in Properties.")
