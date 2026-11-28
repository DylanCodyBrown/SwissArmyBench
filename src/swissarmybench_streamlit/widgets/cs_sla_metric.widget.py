# /// swissarmybench-widget
# format = 1
# name = "cs_sla_metric"
# description = "The share of tickets answered within their SLA"
# framework = "streamlit"
# group = "Data"
# pack = "Customer service"
# tags = []
# size = [3, 2]
# min_size = [2, 1]
# ///
import pandas as pd
import streamlit as st
from sab_canvas import In, Table, sample

# The tickets table (empty: made-up sample data)
table_name: In[Table] = None
response_column = "first_response_minutes"  # column of table_name
sla_column = "sla_hours"  # column of table_name
label = "First response within SLA"
# The share you aim to meet
target: float = 0.9  # 0..1 step 0.01


frame = table_name if table_name is not None else sample(kind="tickets")
if response_column not in frame.columns or sla_column not in frame.columns:
    st.warning(f"Pick the SLA columns: {response_column} or {sla_column} is not in the table.")
else:
    minutes = pd.to_numeric(frame[response_column], errors="coerce")
    allowed = pd.to_numeric(frame[sla_column], errors="coerce") * 60
    known = minutes.notna() & allowed.notna()
    met = int((minutes[known] <= allowed[known]).sum())
    share = met / int(known.sum()) if known.any() else 0.0
    st.metric(label, f"{share:.0%}", f"{share - target:+.0%} against the {target:.0%} target")
    st.caption(f"{met} of {int(known.sum())} tickets answered within their service level agreement")
