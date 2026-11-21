# /// swissarmybench-widget
# format = 1
# name = "excel_map_columns"
# description = "Match an upload's columns to your fields: by name, then by hand"
# framework = "streamlit"
# group = "Forms"
# pack = "Excel"
# tags = []
# size = [6, 6]
# min_size = [3, 3]
# ///
import difflib
import hashlib
import re

import pandas as pd
import streamlit as st
from sab_canvas import In, Out, Table, key, sample

# The table to map: the page's excel_upload's, wired by itself (none yet: made-up sample data)
uploaded: In[Table] = None
# The fields the table must give, in order
fields = ["order_id", "customer_name", "product", "quantity", "unit_price", "order_date", "status"]
# The fields that must be matched (marked with a red star)
required_fields = ["order_id", "quantity"]
# How alike a column's name must be to match by itself (0 to 1)
match_cutoff: float = 0.6  # 0..1 step 0.05
# Said under a required field left unmatched
validation_message = "Match a column to this field."
# The mapped table, for the page's excel_validate_rows (it reads it by itself)
mapped: Out[Table] = None
# Which column each field took
mapping: Out[dict] = None


# Short words a header often uses, read as the field's word
_SAME = {
    "no": "id",
    "nr": "id",
    "num": "id",
    "number": "id",
    "qty": "quantity",
    "cust": "customer",
    "amt": "amount",
    "desc": "description",
    "dt": "date",
    "prod": "product",
    "ref": "id",
}


def _plain(name):
    """A name's words in small letters, the short ones read as their field's word: Order No is orderid."""
    return "".join(_SAME.get(w, w) for w in re.findall(r"[a-z0-9]+", str(name).lower()))


def _guess_for(field, columns):
    """The column whose name matches the field: the same letters first, then the closest by difflib."""
    same = [c for c in columns if _plain(c) == _plain(field)]
    if same:
        return same[0]
    alike = {_plain(c): c for c in columns}
    near = difflib.get_close_matches(_plain(field), list(alike), n=1, cutoff=float(match_cutoff))
    if near:
        return alike[near[0]]
    words = [c for c in columns if _plain(field)[:3] and _plain(c).startswith(_plain(field)[:3])]
    return words[0] if len(words) == 1 else None


frame = uploaded if uploaded is not None and len(uploaded.columns) else sample(kind="orders")
columns = [str(c) for c in frame.columns]
choices = ["(none)", *columns]
# The pickers are keyed by the columns they choose from: a real upload's columns guess again, never keeping the
# sample's picks
_of = hashlib.sha256("\x1f".join(columns).encode("utf-8")).hexdigest()[:8]
mapping, missing = {}, []
for field in fields:
    guessed = _guess_for(field, columns)
    needed = field in required_fields
    picked = st.selectbox(
        field + (" :red[\\*]" if needed else ""),
        choices,
        index=choices.index(guessed) if guessed else 0,
        key=key(f"f_{field}_{_of}"),
    )
    if picked != "(none)":
        mapping[field] = picked
    elif needed:
        missing.append(field)
        st.markdown(f":red[{validation_message}]")
mapped = pd.DataFrame({field: frame[column].values for field, column in mapping.items()})

st.caption(
    f"{len(mapping)} of {len(fields)} fields matched"
    + (f"; still to match: {', '.join(missing)}" if missing else "")
)
st.dataframe(mapped.head(5), hide_index=True, use_container_width=True)
