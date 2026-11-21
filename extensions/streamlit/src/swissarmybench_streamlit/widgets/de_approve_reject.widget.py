# /// swissarmybench-widget
# format = 1
# name = "de_approve_reject"
# description = "One record with Approve and Reject (a reason to reject)"
# framework = "streamlit"
# group = "Buttons"
# pack = "Data entry"
# tags = []
# size = [5, 5]
# min_size = [3, 3]
# ///
import datetime

import pandas as pd
import streamlit as st
from sab_canvas import key, table

_WIDGET = "de_approve_reject"
# The table the record comes from (empty: made-up sample data)
table_name = ""  # table
key_column = "product_id"  # column of table_name
# The session state key a picked record's key is kept under (none picked: the first row)
selected_key = "record"
approve_label = "Approve"
reject_label = "Reject"
# A reason is needed to reject
reason_required = True
# Said while a rejection has no reason
validation_message = "Say why it is rejected."
# The session state key the decision is handed to the page under ({"event": "save", ...})
save_event = "decision_saved"


def _sample():
    """Made-up products (the shape of products, with a category name)."""
    rows = []
    names = ["Desk lamp", "Storage box", "Cushion", "Planter", "Trowel", "Kettle", "Claw hammer", "Notebook"]
    categories = [
        "Lighting",
        "Storage",
        "Textiles",
        "Planters",
        "Garden tools",
        "Small appliances",
        "Hand tools",
        "Paper",
    ]
    for at, name in enumerate(names):
        rows.append(
            {
                "product_id": 100 + at,
                "sku": f"LG-{100 + at:06d}",
                "product_name": name,
                "category": categories[at],
                "unit_price": round(4.99 + at * 7.5, 2),
                "launched_on": datetime.date(2024, 1 + at, 10),
                "discontinued": at == 5,
            }
        )
    frame = pd.DataFrame(rows)
    frame["launched_on"] = pd.to_datetime(frame["launched_on"])
    return frame


def _save(payload):
    """The page's hand-off: {"event": "save", "widget": ..., "payload": ...} under save_event."""
    st.session_state[save_event] = {"event": "save", "widget": _WIDGET, "payload": payload}


def _plain(value):
    """A cell as a plain Python value (for the page's hand-off: JSON-ready)."""
    if value is None or (not isinstance(value, (list, dict, str)) and pd.isna(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


frame = table(table_name) if table_name else _sample()
if frame.empty:
    st.info("No records to decide on.")
else:
    wanted = st.session_state.get(selected_key)
    found = (
        frame[frame[key_column].astype(str) == str(wanted)]
        if wanted is not None and key_column in frame.columns
        else frame.iloc[0:0]
    )
    record = (found if len(found) else frame).iloc[0]
    st.dataframe(
        pd.DataFrame({"field": record.index, "value": [str(v) for v in record.values]}),
        hide_index=True,
        use_container_width=True,
    )
    reason = st.text_input("Reason" + (" :red[\\*]" if reason_required else ""), key=key("reason"))
    left, right, _ = st.columns([1, 1, 3])
    approved = left.button(approve_label, type="primary", key=key("approve"))
    rejected = right.button(reject_label, key=key("reject"))
    if rejected and reason_required and not reason.strip():
        st.markdown(f":red[{validation_message}]")
    elif approved or rejected:
        decision = "approved" if approved else "rejected"
        _save(
            {
                "key": _plain(record.get(key_column)),
                "decision": decision,
                "reason": reason.strip(),
                "record": {c: _plain(v) for c, v in record.items()},
            }
        )
        st.session_state[key("last")] = decision
    if st.session_state.get(key("last")):
        st.caption(f"Last decision: {st.session_state[key('last')]}")
