# /// swissarmybench-widget
# format = 1
# name = "api_bridge"
# description = "Call an API action (through api_adapter) with the values its Ins are wired to; hand its answer on"
# framework = "streamlit"
# group = "Forms"
# tags = []
# size = [4, 2]
# min_size = [1, 1]
# ///
import hashlib
import json
import re
import urllib.parse

import streamlit as st
from sab_canvas import In, Out, Table, action, key, said

# The endpoint it calls
endpoint = ""  # endpoint
# The path's {names}: "@form.name" is an In's value (dotted for a part), anything else as written
path_values = {}
# The query: each "@name" an In's value, anything else as written
query = {}
# The body: each "@name" an In's value (dotted for a part; "@trigger" the whole event), anything else as written
body_extra = {}
button = "Send"
# Call it on every run, with no button (a GET whose answer other widgets read)
auto = False
# Rows sent in parts of this many (0: one call); the rest go to rest_endpoint, its {names} from the first answer
part_rows: int = 0  # 0..100000
rest_endpoint = ""  # endpoint
show_answer = True
# How the answer shows: json, table (a list's rows) or metrics (an object's numbers)
show_as = "json"  # json, table, metrics
# Only these fields of the answer (empty: every one)
show_fields = []

# Send when this changes (another widget's Event, as form_fill's saved); not wired: on the button
trigger: In[dict] = None
# The values the templates above read by name
form: In[dict] = None
period: In[str] = None
loaded_by: In[str] = None
records: In[Table] = None
run: In[dict] = None
status: In[str] = None
source_table: In[str] = None
key_field: In[str] = None
key_column: In[str] = None
compare_field: In[str] = None
compare_column: In[str] = None
tolerance: In[float] = None
# The answer, for other widgets: an object's, or a list's
answer: Out[dict] = None
listed: Out[list] = None

_INS = {
    "trigger": trigger,
    "form": form,
    "period": period,
    "loaded_by": loaded_by,
    "records": records,
    "run": run,
    "status": status,
    "source_table": source_table,
    "key_field": key_field,
    "key_column": key_column,
    "compare_field": compare_field,
    "compare_column": compare_column,
    "tolerance": tolerance,
}


def _call(method, path, body=None):
    """One call through api_adapter (the runtime's action): the answer as it came, or the problem in a line."""
    answer = action(f"{method} {path}", body=body, timeout=600)
    if not answer["ok"]:
        return None, said(answer)
    return (answer.get("raw") or {}).get("body"), None


def _value(path):
    """An In's value by its dotted name; a table as its rows."""
    head, *rest = str(path).split(".")
    found = _INS.get(head)
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
    body = _filled(body_extra) or None
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
    got, problem, sent = None, None, False
    if auto:
        _, _, waiting = _path(endpoint, path_values)
        if waiting:
            st.caption(f"Waiting for {waiting}.")
        else:
            got, problem = _send()
            sent = True
    elif trigger is not None:
        mark = hashlib.sha1(json.dumps(trigger, sort_keys=True, default=str).encode()).hexdigest()
        if st.session_state.get(key("sent")) != mark:
            st.session_state[key("sent")] = mark
            got, problem = _send()
            sent = True
    elif st.button(button, key=key("button")):
        got, problem = _send()
        sent = True
    if sent:
        if problem:
            st.error(problem)
        else:
            if isinstance(got, dict):
                answer = got
            elif isinstance(got, list):
                listed = got
            if not auto:
                st.success(f"{endpoint}: done.")
            if show_answer:
                _show(got)
