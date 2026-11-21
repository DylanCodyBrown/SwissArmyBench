# /// swissarmybench-widget
# format = 1
# name = "map_points"
# description = "Points on a map from latitude and longitude"
# framework = "streamlit"
# group = "Charts"
# tags = []
# size = [6, 5]
# min_size = [3, 3]
# ///
import streamlit as st
from sab_canvas import In, Table, sample

# The table to show (empty: made-up sample data)
table_name: In[Table] = None
latitude = "lat"  # column of table_name
longitude = "lon"  # column of table_name
colour = "#d62728"
size = 800  # 10..10000

frame = table_name if table_name is not None else sample()
if latitude in frame.columns and longitude in frame.columns:
    st.map(frame, latitude=latitude, longitude=longitude, color=colour, size=size)
else:
    st.info("Pick the latitude and longitude columns.")
