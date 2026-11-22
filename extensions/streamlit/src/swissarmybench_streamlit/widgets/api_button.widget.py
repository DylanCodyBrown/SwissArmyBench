# /// swissarmybench-widget
# format = 1
# name = "api_button"
# description = "A button that calls an API's action (the local sandbox API's endpoint, or any API's)"
# framework = "streamlit"
# group = "Buttons"
# tags = ["api"]
# size = [3, 1]
# min_size = [2, 1]
# ///
import os
import re

import streamlit as st
from sab_canvas import Event, action, data, key, said

# The action it calls, through api_adapter
endpoint = ""  # endpoint
label = "Call"
# One box per {name} in the endpoint's path: a value, a variable or a page value
path_values = {}  # path values of endpoint
# The body it sends (a POST, PUT or PATCH)
body = {}
show_answer = True

# Fired once the action answered ({"answer": ...}); the Canvas wires what it does next
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


def _inputs(wanted, values):
    """The action's path inputs, each {name} given from `values`: (inputs, None), or (None, the one missing)."""
    found = {}
    for name in dict.fromkeys(re.findall(r"\{(\w+)\}", wanted or "")):
        given = _given(values[name]) if name in values else None
        if given is None or given == "":
            return None, name
        found[name] = given
    return found, None


if st.button(label, key=key("button"), disabled=not endpoint):
    inputs, missing = _inputs(endpoint, path_values)
    if missing:
        st.warning(f"Give {missing} in Properties (its path box).")
    else:
        writes = endpoint.rpartition(" ")[0].rpartition(" ")[2] in ("POST", "PUT", "PATCH")
        answer = action(endpoint, inputs, body=body if writes else None)
        if not answer["ok"]:
            st.error(said(answer))
        else:
            got = data(answer)
            answered({"answer": got})
            if show_answer:
                st.json(got)
            else:
                st.success("Done.")
if not endpoint:
    st.caption("Pick the endpoint in Properties.")
