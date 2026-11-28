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
import pandas as pd
import streamlit as st
from sab_canvas import Event, In, Table, key, sample

# The table the record comes from (empty: made-up sample data)
table_name: In[Table] = None
key_column = "product_id"  # column of table_name
# The record to decide on, by its key (not wired: the first row)
record_key: In[str] = None
approve_label = "Approve"
reject_label = "Reject"
# A reason is needed to reject
reason_required = True
# Said while a rejection has no reason
validation_message = "Say why it is rejected."
# Fired on Approve and on Reject: the decision (key, decision, reason, record); the Canvas wires what each does
approved: Event[dict] = None
rejected: Event[dict] = None


def _plain(value):
    """A cell as a plain Python value (for the page's hand-off: JSON-ready)."""
    if value is None or (not isinstance(value, (list, dict, str)) and pd.isna(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


frame = table_name if table_name is not None else sample(kind="products")
if frame.empty:
    st.info("No records to decide on.")
else:
    wanted = record_key
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
    approved_now = left.button(approve_label, type="primary", key=key("approve"))
    rejected_now = right.button(reject_label, key=key("reject"))
    if rejected_now and reason_required and not reason.strip():
        st.markdown(f":red[{validation_message}]")
    elif approved_now or rejected_now:
        decision = "approved" if approved_now else "rejected"
        (approved if approved_now else rejected)(
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
