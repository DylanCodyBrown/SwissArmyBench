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
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import streamlit as st
from sab_canvas import Out

# The endpoint it reads (a GET answering an object, or a list: its first row, or how many)
endpoint = ""  # endpoint
# The path's values, by name
path_values = {}
# The answer's field that holds the number (empty: how many rows a list holds)
field = ""
label = "Value"
prefix = ""
suffix = ""
# The number shown, for the widgets on the page that read it
value: Out[float] = None


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


if not endpoint:
    st.metric(label, "-")
    st.caption("Pick the endpoint in Properties.")
else:
    method, path, missing = _path(endpoint, path_values)
    answer, problem = (None, f"Give {missing} in path_values.") if missing else _call(method, path)
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
