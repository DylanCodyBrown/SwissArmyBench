"""The canvas runtime (the Streamlit extension's server/sab_canvas.py) imported as the module it is, for a
test: a built app runs it beside Streamlit and its widgets module, so both are stood in for here (Streamlit
is never the app's dependency) and taken away again when the test ends."""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any

import pytest

NAME = "swissarmybench_streamlit.server.sab_canvas"


def load(monkeypatch: pytest.MonkeyPatch, headers: dict[str, str] | None = None, user: Any = None) -> Any:
    """The runtime, imported afresh with stand-ins for Streamlit (a request's headers, st.user, an empty
    session state) and for sab_widgets."""
    st = types.ModuleType("streamlit")
    st.context = types.SimpleNamespace(headers=headers or {})  # type: ignore[attr-defined]
    st.user = user or types.SimpleNamespace(is_logged_in=False)  # type: ignore[attr-defined]
    st.session_state = {}  # type: ignore[attr-defined]
    widgets = types.ModuleType("sab_widgets")
    widgets.CODE = {}  # type: ignore[attr-defined]
    widgets.VARIABLES = {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setitem(sys.modules, "sab_widgets", widgets)
    sys.modules.pop(NAME, None)
    module = importlib.import_module(NAME)
    del sys.modules[NAME]
    monkeypatch.setitem(sys.modules, NAME, module)  # there while the test runs; the next test's is its own
    return module
