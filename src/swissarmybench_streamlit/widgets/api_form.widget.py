# /// swissarmybench-widget
# format = 1
# name = "api_form"
# description = "A form that sends a row to an API's action (the local sandbox API's POST or PUT, or any API's)"
# framework = "streamlit"
# group = "Forms"
# tags = ["api"]
# size = [5, 4]
# min_size = [3, 3]
# ///
import os
import re

import streamlit as st
from sab_canvas import Event, action, data, key, said, takes

# The action it sends to (a POST or a PUT whose body is a row), through api_adapter
endpoint = ""  # endpoint
# One box per {name} in the endpoint's path: a value, a variable or a page value
path_values = {}  # path values of endpoint
# The fields (empty: its body's, as the API's specification gives them)
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
    st.info("Pick the endpoint in Properties: a POST or PUT of an API.")
else:
    # The body's fields as the action takes them: each one's box by its type (a closed set a dropdown).
    model = {f["name"]: f for f in takes(endpoint)["body"]}
    names = list(fields) or list(model)
    with st.form(key("form")):
        values = {}
        for name in names:
            box = model.get(name, {}).get("box", "text")
            kind = model.get(name, {}).get("type", "string")
            if box == "switch":
                values[name] = st.checkbox(name, key=key(name))
            elif box == "number":
                values[name] = st.number_input(name, value=0 if kind == "integer" else 0.0, key=key(name))
            elif box == "dropdown":
                values[name] = st.selectbox(name, model[name].get("choices") or [], key=key(name))
            elif box == "date":
                picked = st.date_input(name, value=None, key=key(name))
                values[name] = picked.isoformat() if picked else None
            else:
                values[name] = st.text_input(name, key=key(name))
        sent = st.form_submit_button(button)
    if sent:
        inputs, missing = _inputs(endpoint, path_values)
        if missing:
            st.warning(f"Give {missing} in Properties (its path box).")
        else:
            answer = action(endpoint, inputs, body={k: v for k, v in values.items() if v not in ("", None)})
            if not answer["ok"]:
                st.error(said(answer))
            else:
                got = data(answer)
                st.success("Sent.")
                st.json(got)
                sent({"request": values, "answer": got})
