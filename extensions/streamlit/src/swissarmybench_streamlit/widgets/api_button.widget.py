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
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import streamlit as st
from sab_canvas import Event, key

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


def _call(method, path, body=None, query=None, root=False):
    """One request to the project's local sandbox API (its address and key from Play, Launch or a deploy)."""
    base = os.environ.get("SAB_API_URL", "")
    if not base:
        return None, "Run the local sandbox API (the APIs page), then Play again."
    url = base.rstrip("/") + ("" if root else os.environ.get("SAB_API_BASE", "")) + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    data = None if body is None else json.dumps(body, default=str).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + os.environ.get("SAB_API_KEY", ""),
        "Content-Type": "application/json",
    }
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data, headers, method=method), timeout=30
        ) as r:
            raw = r.read()
            return (json.loads(raw) if raw else None), None
    except urllib.error.HTTPError as failed:
        try:
            said = json.loads(failed.read() or b"{}").get("error") or failed.reason
        except ValueError:
            said = failed.reason
        return None, f"{failed.code}: {said}"
    except OSError as failed:
        return None, f"The local sandbox API could not be reached ({getattr(failed, 'reason', failed)})."


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
        answer, problem = _call(method, path, body if method in ("POST", "PUT", "PATCH") else None)
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
