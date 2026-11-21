# /// swissarmybench-widget
# format = 1
# name = "api_table"
# description = "A local sandbox API's GET endpoint as a table, a page at a time"
# framework = "streamlit"
# group = "Data"
# tags = ["api"]
# size = [6, 4]
# min_size = [3, 2]
# ///
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import streamlit as st
from sab_canvas import Out, Table, key

# The endpoint whose rows it shows (a GET that answers a list)
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


if not endpoint:
    st.info("Pick the endpoint in Properties: a GET of the local sandbox API.")
else:
    method, path, missing = _path(endpoint, path_values)
    page = st.session_state.get(key("page"), 0)
    if missing:
        st.warning(f"Give {missing} in Properties (its path box).")
    else:
        rows, problem = _call(method, path, query={limit_name: page_size, offset_name: page * page_size})
        if problem:
            st.info(problem)
        else:
            st.dataframe(
                rows if isinstance(rows, list) else [rows], use_container_width=True, hide_index=True
            )
            left, middle, right = st.columns([1, 2, 1])
            if left.button("Previous", key=key("previous"), disabled=page == 0):
                st.session_state[key("page")] = page - 1
                st.rerun()
            middle.caption(f"Page {page + 1}")
            full = isinstance(rows, list) and len(rows) >= page_size
            if right.button("Next", key=key("next"), disabled=not full):
                st.session_state[key("page")] = page + 1
                st.rerun()
