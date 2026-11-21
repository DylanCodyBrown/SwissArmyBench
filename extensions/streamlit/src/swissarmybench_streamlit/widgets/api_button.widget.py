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
from sab_canvas import key

# The endpoint it calls
endpoint = ""  # endpoint
label = "Call"
# The path's values, by name
path_values = {}
# The body it sends (a POST, PUT or PATCH)
body = {}
show_answer = True


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


def _path(wanted, values):
    """The endpoint's method and path, its {names} filled from `values` (None: one is missing)."""
    method, _, path = (wanted or "").partition(" ")
    for name in re.findall(r"\{(\w+)\}", path):
        if name not in values:
            return method, None, name
        path = path.replace("{" + name + "}", urllib.parse.quote(str(values[name]), safe=""))
    return method, path, None


if st.button(label, key=key("button"), disabled=not endpoint):
    method, path, missing = _path(endpoint, path_values)
    if missing:
        st.warning(f"Give {missing} in path_values.")
    else:
        answer, problem = _call(method, path, body if method in ("POST", "PUT", "PATCH") else None)
        if problem:
            st.error(problem)
        elif show_answer:
            st.json(answer)
        else:
            st.success("Done.")
if not endpoint:
    st.caption("Pick the endpoint in Properties.")
