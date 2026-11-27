# /// swissarmybench-widget
# format = 1
# name = "de_edit_grid"
# description = "Edit, add and remove rows; Save hands the changes on"
# framework = "streamlit"
# group = "Data"
# pack = "Data entry"
# tags = []
# size = [8, 5]
# min_size = [4, 3]
# ///
import pandas as pd
import streamlit as st
from sab_canvas import Event, In, Table, key, sample

# The table to edit (empty: made-up sample data)
table_name: In[Table] = None
# The column that names each row
key_column = "product_id"  # column of table_name
# Rows can be added and taken away
add_rows = True
# The columns that cannot be changed
locked_columns = ["product_id"]
button = "Save changes"
# Fired on Save: the changes (edited, added, removed); the Canvas wires what it does (call an API.py endpoint, set a page value, rerun)
saved: Event[dict] = None


def _plain(value):
    """A cell as a plain Python value (for the page's hand-off: JSON-ready)."""
    if value is None or (not isinstance(value, (list, dict, str)) and pd.isna(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


frame = (table_name if table_name is not None else sample(kind="products")).reset_index(drop=True)
editor_key = key("editor")
st.data_editor(
    frame,
    num_rows="dynamic" if add_rows else "fixed",
    disabled=[c for c in locked_columns if c in frame.columns],
    hide_index=True,
    use_container_width=True,
    key=editor_key,
)
changes = st.session_state.get(editor_key) or {}
edited = changes.get("edited_rows", {}) or {}
added = changes.get("added_rows", []) or []
removed = changes.get("deleted_rows", []) or []
left, right = st.columns([3, 1])
left.caption(f"{len(edited)} changed · {len(added)} added · {len(removed)} removed")
if right.button(button, key=key("save"), disabled=not (edited or added or removed)):

    def _row_key(at):
        return _plain(frame.iloc[int(at)][key_column]) if key_column in frame.columns else int(at)

    saved(
        {
            "changed": [
                {"key": _row_key(at), "values": {c: _plain(v) for c, v in values.items()}}
                for at, values in edited.items()
            ],
            "added": [{c: _plain(v) for c, v in row.items()} for row in added],
            "removed": [_row_key(at) for at in removed],
        }
    )
    st.success("Changes handed to the page.")
