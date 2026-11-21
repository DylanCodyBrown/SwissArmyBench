# /// swissarmybench-widget
# format = 1
# name = "image"
# description = "A picture from a file or an address"
# framework = "streamlit"
# group = "Text"
# tags = []
# size = [4, 3]
# min_size = [2, 2]
# ///
import streamlit as st

# A picture's path or address (empty: a made-up picture)
path = ""  # path
caption = "Our team"

if path:
    st.image(path, caption=caption or None, use_container_width=True)
else:
    st.image(
        "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='160'><rect width='320' height='160' rx='12' "
        "fill='#e8eef7'/><circle cx='110' cy='80' r='38' fill='#9db4d8'/><rect x='170' y='52' width='90' height='56' "
        "rx='8' fill='#c5d3ea'/></svg>",
        caption=caption or None,
    )
