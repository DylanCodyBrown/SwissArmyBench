# /// swissarmybench-blade
# format = 1
# name = "Streamlit map"
# kind = "snippet"
# description = "A dot on a map for each row, from its latitude and longitude"
# tags = ["streamlit", "display", "map"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "Map of <<table>>"
# ///
snippet = r"""
# Map: a dot on a world map for each row, placed by its latitude and longitude.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table with a latitude and a longitude column (decimal degrees: 51.5, -0.12)
#
# Streamlit functions:
#   st.map(table, latitude, longitude)   a map with a dot at each row's place
#
# Rows with no place are left out first. The map's background is drawn from map pictures the browser
# fetches from the internet; without them the dots still show on a blank map.
import streamlit as st

st.map(
    <<table>>.dropna(subset=["<<latitude column: lat>>", "<<longitude column: lon>>"]),
    latitude="<<latitude column: lat>>",
    longitude="<<longitude column: lon>>",
)
"""
