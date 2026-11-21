# /// swissarmybench-widget
# format = 1
# name = "api_form"
# description = "A form that sends a row to a local sandbox API's POST or PUT endpoint"
# framework = "streamlit"
# group = "Forms"
# tags = ["api"]
# size = [5, 4]
# min_size = [3, 3]
# ///
import os
import re
import urllib.parse

import streamlit as st
from sab_canvas import Event, api_call, key

# The endpoint it sends to (a POST or a PUT whose body is a row)
endpoint = ""  # endpoint
# One box per {name} in the endpoint's path: a value, a variable or a page value
path_values = {}  # path values of endpoint
# The fields (empty: its body's, as API.py's model gives them)
fields = []
button = "Send"
# Fired once the row was sent ({"request", "answer"}); the Canvas wires what it does next
sent: Event[dict] = None


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


def _model(wanted):
    """The endpoint's body fields and their types, from the running API."""
    found, problem = api_call("GET", "/__sab/endpoints", root=True)
    if problem or not isinstance(found, dict):
        return {}
    method, _, path = wanted.partition(" ")
    for e in found.get("endpoints") or []:
        if e["method"] == method and e["path"] == path:
            return e.get("body") or {}
    return {}


if not endpoint:
    st.info("Pick the endpoint in Properties: a POST or PUT of the local sandbox API.")
elif not os.environ.get("SAB_API_URL"):
    st.info("Run the local sandbox API (the APIs page), then Play again.")
else:
    model = _model(endpoint)
    names = list(fields) or list(model)
    with st.form(key("form")):
        values = {}
        for name in names:
            kind = model.get(name, "str")
            if kind == "bool":
                values[name] = st.checkbox(name, key=key(name))
            elif kind in ("int", "float"):
                values[name] = st.number_input(name, value=0 if kind == "int" else 0.0, key=key(name))
            else:
                values[name] = st.text_input(name, key=key(name))
        sent = st.form_submit_button(button)
    if sent:
        method, path, missing = _path(endpoint, path_values)
        if missing:
            st.warning(f"Give {missing} in Properties (its path box).")
        else:
            answer, problem = api_call(method, path, {k: v for k, v in values.items() if v not in ("", None)})
            if problem:
                st.error(problem)
            else:
                st.success("Sent.")
                st.json(answer)
                sent({"request": values, "answer": answer})
