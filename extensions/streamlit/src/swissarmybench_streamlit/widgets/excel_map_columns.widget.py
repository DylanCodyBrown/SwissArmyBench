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
import re

import pandas as pd
import streamlit as st
from sab_canvas import key

# The session state key the uploaded table is under (empty, or nothing there: made-up sample data)
in_key = "uploaded"
# The fields the table must give, in order
fields = ["order_id", "customer_name", "product", "quantity", "unit_price", "order_date", "status"]
# The fields that must be matched (marked with a red star)
required_fields = ["order_id", "quantity"]
# How alike a column's name must be to match by itself (0 to 1)
match_cutoff: float = 0.6  # 0..1 step 0.05
# Said under a required field left unmatched
validation_message = "Match a column to this field."
# The session state key the mapped table is kept under (Validate rows reads it)
out_key = "mapped"


def _sample_orders():
    """Made-up orders as an export might send them: headers in its own words."""
    people = ["Ada Ashdown", "Bram Brookfield", "Cleo Calloway", "Dov Dunmore", "Esme Everly"]
    products = ["Desk lamp", "Kettle", "Planter", "Wok", "Notebook"]
    return pd.DataFrame(
        [
            {
                "Order No": 81000 + at,
                "Cust. name": people[at % 5],
                "Product": products[(at * 3) % 5],
                "Qty": [2, 1, 4, 0, 3, 12, 1, 2][at % 8],
                "Unit price": [24.5, 39.0, 12.99, 9.5, 3.25][at % 5],
                "Order date": pd.Timestamp(2026, 11, 1 + at),
                "Status": ["Delivered", "Shipped", "Pending", "Delivred"][at % 4],
            }
            for at in range(12)
        ]
    )


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


found = st.session_state.get(in_key) if in_key else None
frame = found if isinstance(found, pd.DataFrame) and len(found.columns) else _sample_orders()
columns = [str(c) for c in frame.columns]
choices = ["(none)", *columns]
mapping, missing = {}, []
for field in fields:
    guessed = _guess_for(field, columns)
    needed = field in required_fields
    picked = st.selectbox(
        field + (" :red[\\*]" if needed else ""),
        choices,
        index=choices.index(guessed) if guessed else 0,
        key=key(f"f_{field}"),
    )
    if picked != "(none)":
        mapping[field] = picked
    elif needed:
        missing.append(field)
        st.markdown(f":red[{validation_message}]")
mapped = pd.DataFrame({field: frame[column].values for field, column in mapping.items()})
st.session_state[out_key] = mapped
st.session_state[out_key + "_mapping"] = mapping
st.caption(
    f"{len(mapping)} of {len(fields)} fields matched"
    + (f"; still to match: {', '.join(missing)}" if missing else "")
)
st.dataframe(mapped.head(5), hide_index=True, use_container_width=True)
