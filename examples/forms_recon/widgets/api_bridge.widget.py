# /// swissarmybench-widget
# format = 1
# name = "api_bridge"
# description = "Send a page value to a local sandbox API endpoint, or fetch one into a page value"
# framework = "streamlit"
# group = "Forms"
# tags = []
# size = [4, 2]
# min_size = [1, 1]
# ///
import hashlib
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
# The path's {names}: a page value ("@form_saved.payload.name": a session state key, dotted for a part) or as written
path_values = {}
# The query: each "@key" a page value, anything else as written
query = {}
# The body: a page value's key, dotted for a part (empty: none)
body_key = ""
# More of the body: each "@key" a page value, anything else as written
body_extra = {}
# Send when this page value changes (an event another widget hands over); empty: on the button
trigger_key = ""
button = "Send"
# Call it on every run, with no button (a GET whose answer other widgets read)
auto = False
# The page value the answer is kept under (other widgets read it)
result_key = ""
# Rows sent in parts of this many (0: one call); the rest go to rest_endpoint, its {names} from the first answer
part_rows: int = 0  # 0..100000
rest_endpoint = ""  # endpoint
show_answer = True
# How the answer shows: json, table (a list's rows) or metrics (an object's numbers)
show_as = "json"  # json, table, metrics
# Only these fields of the answer (empty: every one)
show_fields = []


def _call(method, path, body=None):
    base = os.environ.get("SAB_API_URL", "")
    if not base:
        return None, "Run the local sandbox API (the APIs page), then Play again."
    url = base.rstrip("/") + os.environ.get("SAB_API_BASE", "") + path
    data = None if body is None else json.dumps(body, default=str).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + os.environ.get("SAB_API_KEY", ""),
        "Content-Type": "application/json",
    }
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data, headers, method=method), timeout=600
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
        return (
            None,
            f"The local sandbox API could not be reached ({getattr(failed, 'reason', failed)}).",
        )


def _value(path):
    """A page value by its dotted key; a table as its rows."""
    head, *rest = str(path).split(".")
    found = st.session_state.get(head)
    for part in rest:
        found = found.get(part) if isinstance(found, dict) else None
    to_dict = getattr(found, "to_dict", None)
    if callable(to_dict):
        found = json.loads(found.to_json(orient="records", date_format="iso"))
    return found


def _filled(value):
    if isinstance(value, str) and value.startswith("@"):
        return _value(value[1:])
    if isinstance(value, dict):
        return {k: _filled(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_filled(v) for v in value]
    return value


def _path(wanted, values):
    method, _, path = (wanted or "").partition(" ")
    for name in re.findall(r"\{(\w+)\}", path):
        given = _filled(values.get(name))
        if given in (None, ""):
            return method, None, name
        path = path.replace("{" + name + "}", urllib.parse.quote(str(given), safe=""))
    asked = {k: v for k, v in _filled(query).items() if v not in (None, "")}
    if asked:
        path += "?" + urllib.parse.urlencode(
            {k: str(v).lower() if isinstance(v, bool) else v for k, v in asked.items()}
        )
    return method, path, None


def _send():
    method, path, missing = _path(endpoint, path_values)
    if missing:
        return None, f"{missing} has no value yet."
    body = _value(body_key) if body_key else None
    extra = _filled(body_extra)
    if extra:
        body = {**(body if isinstance(body, dict) else {}), **extra}
    rows = body.get("rows") if isinstance(body, dict) else None
    if not (
        part_rows and rest_endpoint and isinstance(rows, list) and len(rows) > part_rows
    ):
        return _call(method, path, body)
    answer, problem = _call(method, path, {**body, "rows": rows[:part_rows]})
    for at in range(part_rows, len(rows), part_rows):
        if problem:
            break
        more, _, rest = rest_endpoint.partition(" ")
        rest = re.sub(
            r"\{(\w+)\}", lambda m: str((answer or {}).get(m.group(1), "")), rest
        )
        answer, problem = _call(more, rest, {"rows": rows[at : at + part_rows]})
    return answer, problem


def _show(answer):
    if show_fields and isinstance(answer, dict):
        answer = {k: answer.get(k) for k in show_fields}
    elif show_fields and isinstance(answer, list):
        answer = [
            {k: r.get(k) for k in show_fields} if isinstance(r, dict) else r
            for r in answer
        ]
    if show_as == "table" and isinstance(answer, list):
        st.caption(f"{len(answer)} rows")
        st.dataframe(answer, hide_index=True, use_container_width=True)
    elif show_as == "metrics" and isinstance(answer, dict):
        numbers = [
            (k, v)
            for k, v in answer.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        for column, (name, number) in zip(st.columns(max(1, len(numbers))), numbers):
            column.metric(name.replace("_", " ").capitalize(), f"{number:,}")
    else:
        st.json(answer, expanded=False)


if not endpoint:
    st.info("Pick the endpoint in Properties.")
else:
    answer, problem, sent = None, None, False
    if auto:
        _, _, waiting = _path(endpoint, path_values)
        if waiting:
            st.caption(f"Waiting for {waiting}.")
        else:
            answer, problem = _send()
            sent = True
    elif trigger_key:
        event = st.session_state.get(trigger_key)
        mark = (
            hashlib.sha1(
                json.dumps(event, sort_keys=True, default=str).encode()
            ).hexdigest()
            if event
            else ""
        )
        if event and st.session_state.get(key("sent")) != mark:
            st.session_state[key("sent")] = mark
            answer, problem = _send()
            sent = True
    elif st.button(button, key=key("button")):
        answer, problem = _send()
        sent = True
    if sent:
        if problem:
            st.error(problem)
        else:
            if result_key:
                st.session_state[result_key] = answer
            if not auto:
                st.success(f"{endpoint}: done.")
            if show_answer:
                _show(answer)
