# /// swissarmybench-widget
# format = 1
# name = "form_submissions"
# description = "A form's submissions as a table, downloadable"
# framework = "streamlit"
# group = "Data"
# pack = "Form builder"
# tags = []
# size = [8, 5]
# min_size = [4, 3]
# ///
import pandas as pd
import streamlit as st
from sab_canvas import key, table

# The submissions (data in): a table (each row one), or the session state key Fill a form adds them to
table_name = ""  # table
submissions_key = "form_submissions"
# Only this form's submissions (empty: every form)
form_name = ""
file_name = "submissions.csv"


def _sample():
    """Made-up submissions of the site visit form."""
    stores = ["Larkfield Shop", "Marshby Depot", "Fernhaven Shop"]
    return [
        {
            "form": "site_visit",
            "submitted_at": f"2026-11-{10 + at:02d}T{9 + at % 8:02d}:15:00",
            "values": {
                "store": stores[at % 3],
                "visited_on": f"2026-11-{10 + at:02d}",
                "visitor": ["Ada", "Bram", "Cleo"][at % 3],
                "staff_on_duty": 3 + at % 4,
                "till_float": 150.0 + at * 10,
                "clean": "yes" if at % 4 else "no",
            },
        }
        for at in range(6)
    ]


if table_name:
    frame = table(table_name)
else:
    found = st.session_state.get(submissions_key) if submissions_key else None
    shown = found if isinstance(found, list) and found else _sample()
    if not (isinstance(found, list) and found):
        st.caption("Made-up submissions shown until a form is submitted.")
    frame = pd.DataFrame(
        [
            {"form": s.get("form"), "submitted_at": s.get("submitted_at"), **(s.get("values") or {})}
            for s in shown
        ]
    )
if form_name and "form" in frame.columns:
    frame = frame[frame["form"] == form_name]
st.caption(f"{len(frame)} submissions")
st.dataframe(frame, hide_index=True, use_container_width=True)
st.download_button(
    "Download",
    frame.to_csv(index=False).encode("utf-8"),
    file_name or "submissions.csv",
    "text/csv",
    key=key("download"),
)
