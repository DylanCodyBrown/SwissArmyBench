"""forms_recon: its data, exported from data.ipynb by Swiss Army Bench. Do not edit: change data.ipynb.

    from data import orders

No rows and no passwords are kept here: each table is read again the way it was loaded.
"""

import functools

try:  # under Streamlit this runs once and is kept; in a plain kernel Python keeps it
    import streamlit as _st

    _once = _st.cache_resource(show_spinner=False) if _st.runtime.exists() else functools.cache
except ImportError:  # no Streamlit here (a notebook's kernel): nothing of it is needed
    _once = functools.cache
