"""App mode (the Workbench's modes, 2026-11-15): a Streamlit app's page settings (title, icon, wide or
centred, logo, theme colours) kept in its file and written into the live page, an export and the saved
pages (st.set_page_config, st.logo, .streamlit/config.toml); and the live page's state for the State
panel (st.session_state, each key with its block). Made-up data only."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench_streamlit.domain import app_settings as rules
from swissarmybench_streamlit.domain import streamlit_cells
from tests.conftest import AUTH
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command
from tests.test_streamlit_apps import (
    STREAMLIT_PYTHON,
    FakeRunner,
    _canvas,
    _files,
    _notebook,
    _ok,
    needs_streamlit,
    served,  # noqa: F401 (the server with a stand-in Streamlit)
)


def test_page_settings_are_checked_and_changed_a_part_at_a_time() -> None:
    first = rules.changed(rules.AppSettings(), {"title": " Sales ", "icon": "📈", "layout": "centered"})
    assert (first.title, first.icon, first.layout) == ("Sales", "📈", "centered")
    coloured = rules.changed(first, {"colours": {"primary": "#C8102E", "text": "#1c2228"}})
    assert coloured.colours == {"primary": "#c8102e", "text": "#1c2228"} and coloured.title == "Sales"
    assert rules.changed(coloured, {"colours": {"text": None}}).colours == {"primary": "#c8102e"}
    for bad, words in (
        ([], "Send the page settings"),
        ({"size": 3}, "No page setting is called 'size'"),
        ({"layout": "narrow"}, '"wide" or "centered"'),
        ({"title": "two\nlines"}, "one line"),
        ({"icon": "x" * 9}, "at most 8"),
        ({"colours": {"accent": "#ffffff"}}, "No theme colour"),
        ({"colours": {"primary": "red"}}, "#rrggbb"),
    ):
        with pytest.raises(rules.AppSettingsError, match=words):
            rules.changed(rules.AppSettings(), bad)
    assert rules.read_settings({"title": 7, "layout": "centered"}) == rules.AppSettings(layout="centered")


def test_the_apps_file_keeps_them_beside_the_pages() -> None:
    settings = rules.AppSettings(
        title="Sales", icon="📈", layout="centered", logo="logo.png", colours={"primary": "#c8102e"}
    )
    page = streamlit_cells.Page("p1", "Overview")
    text = streamlit_cells.write_app([page], settings=rules.file_line(settings))
    assert json.loads(text)["settings"]["layout"] == "centered"
    assert rules.read_app_settings(text) == settings
    assert [p.name for p in streamlit_cells.read_app(text)] == ["Overview"]
    # The defaults are not written: an app's file stays as it was.
    plain = streamlit_cells.write_app([page], settings=rules.file_line(rules.AppSettings()))
    assert "settings" not in plain and rules.read_app_settings(plain) == rules.AppSettings()


def test_they_become_set_page_config_logo_and_the_theme() -> None:
    settings = rules.AppSettings(
        title="Sales", icon="📈", layout="centered", logo="logo.png", colours={"primary": "#c8102e"}
    )
    assert rules.page_head(settings, "sales") == [
        "st.set_page_config(page_title='Sales', page_icon='📈', layout='centered')",
        "st.logo('logo.png')",
    ]
    assert rules.page_head(rules.AppSettings(), "sales") == [
        "st.set_page_config(page_title='sales', layout='wide')"
    ]
    toml = rules.config_toml(settings, "sales.stapp.json")
    assert toml is not None and toml.splitlines()[1:] == ["[theme]", 'primaryColor = "#c8102e"']
    assert rules.is_own_config(toml) and rules.is_own_config(None)
    assert not rules.is_own_config('[theme]\nbase = "dark"\n')
    assert rules.config_toml(rules.AppSettings(), "sales") is None
    # The saved pages start with them, before the layout; the export's app.py too.
    pieces = {
        ("/x/sales.ipynb", 3): streamlit_cells.PieceCode(
            3, "Hi", "import streamlit as st\nst.title('Hi')", "sales.ipynb @cell3"
        )
    }
    page = streamlit_cells.Page(
        "p1", "Overview", [streamlit_cells.Block("b1", "/x/sales.ipynb", 3, 1, 1, 12, None)]
    )
    head = rules.page_head(settings, "sales")
    saved = streamlit_cells.saved_pages([page], pieces, [], app="sales.stapp.json", head=head)
    code = saved.files["pages/overview.py"]
    ast.parse(code)
    assert (
        code.index("st.set_page_config(") < code.index("st.logo(") < code.index(streamlit_cells.LAYOUT_LINE)
    )
    made = streamlit_cells.export("sales", [page], pieces, [], head=head, config=toml)
    assert "st.logo('logo.png')" in made.files["app.py"] and made.files[".streamlit/config.toml"] == toml


def test_a_blocks_widget_keys_and_the_state_rows() -> None:
    code = 'region = st.selectbox("Region", ["East"], key="region_pick")\nst.slider("Rows", 1, 10)'
    assert rules.widget_keys(code, "b1") == ["region_pick"]
    held = {"region_pick": "East", "b2_1": 10, "last_loaded": "2026-11-15 09:12", "_sab_hidden": 1}
    rows = rules.state_rows(
        held, [("b1", "Region filter", code), ("b2", "Largest orders", "st.slider('n', 1, 9)")]
    )
    assert rows == [
        {"key": "region_pick", "value": "East", "block": "Region filter"},
        {"key": "b2_1", "value": 10, "block": "Largest orders"},
        {"key": "last_loaded", "value": "2026-11-15 09:12", "block": None},
    ]
    assert rules.shown_value({"kind": "DataFrame", "rows": 10}) == "DataFrame, 10 rows"
    assert rules.block_values(rows, "Region filter") == [("region_pick", '"East"')]
    assert rules.state_rows("nope", []) == []


def test_the_canvas_takes_them_and_play_writes_them(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, runner = served
    path = str(_notebook(tmp_path))
    app = _canvas(client)["app"]
    base = f"/streamlit/apps/{app}"
    _ok(client.post(f"{base}/pages", headers=AUTH, json={"document": path, "cell": 3, "w": 6}))
    done = _ok(
        client.put(
            f"{base}/settings",
            headers=AUTH,
            json={"title": "Sales", "layout": "centered", "colours": {"primary": "#c8102e"}},
        )
    )
    assert done["settings"]["title"] == "Sales" and done["settings"]["colours"] == {"primary": "#c8102e"}
    assert client.put(f"{base}/settings", headers=AUTH, json={"layout": "tall"}).status_code == 400
    _ok(client.post(f"{base}/run", headers=AUTH))
    root = _files(runner)
    manifest = json.loads((root / "manifest.json").read_text())
    assert (manifest["title"], manifest["layout"], manifest["icon"]) == ("Sales", "centered", None)
    assert (root / ".streamlit" / "config.toml").read_text().endswith('primaryColor = "#c8102e"\n')
    page = next(root.glob("page_p1_*.py")).read_text()
    ast.parse(page)
    assert "\n_sab_state()\n" in page and page.rstrip().endswith("st.rerun()")  # then what Now asked
    # The State panel: what the live page last wrote, each key with its block.
    assert _ok(client.get(f"{base}/session", headers=AUTH))["state"] == []
    (root / rules.STATE_FILE).write_text(json.dumps({"b1_1": "East", "count": 3}))
    state = _ok(client.get(f"{base}/session", headers=AUTH))["state"]
    assert state == [
        {"key": "b1_1", "value": "East", "block": "Region filter"},
        {"key": "count", "value": 3, "block": None},
    ]


def test_the_workbench_saves_and_opens_them_with_the_pages(client: TestClient, tmp_path: Path) -> None:
    path = str(tmp_path / "sales.stapp.json")
    settings = {
        "title": "Sales",
        "icon": "📈",
        "layout": "centered",
        "logo": "logo.png",
        "colours": {"text": "#1c2228"},
    }
    _ok(client.post("/workbench/save", headers=AUTH, json={"path": path, "pages": [], "settings": settings}))
    opened = _ok(client.post("/workbench/open", headers=AUTH, json={"path": path}))
    assert opened["settings"] == settings
    assert _ok(client.post("/streamlit/apps", headers=AUTH, json={"path": path}))["settings"] == settings


def test_the_agent_sets_page_settings_and_reads_the_state(live: Live, tmp_path: Path) -> None:  # noqa: F811
    app = command("streamlit_open", path=str(_notebook(tmp_path)))
    assert "app" in app
    canvas = live.user("POST", "/streamlit/apps", {"canvas": True, "title": "sales", "pages": []})
    done = command("streamlit_page_settings", app=canvas["app"], settings={"icon": "📈"})
    assert done["settings"]["icon"] == "📈"
    assert command("streamlit_state", app=canvas["app"])["state"] == []


STATE_RUN = """
import json, sys
from pathlib import Path
from streamlit.testing.v1 import AppTest
at = AppTest.from_file(sys.argv[1], default_timeout=60).run()
at.selectbox[0].set_value("West").run()
held = json.loads((Path(sys.argv[1]).parent / "_sab_state.json").read_text())
print(json.dumps({"errors": [str(e.value) for e in at.exception], "state": held}))
"""


@needs_streamlit
def test_the_real_page_writes_its_session_state(tmp_path: Path) -> None:
    page = tmp_path / "page.py"
    code = 'import streamlit as st\nregion = st.selectbox("Region", ["East", "West"], key="region_pick")\n'
    code += 'st.session_state["seen"] = [1, 2]\nimport pandas as pd\n'
    code += 'st.session_state["rows"] = pd.DataFrame({"a": [1, 2]})\n'
    page.write_text(code + rules.STATE_TAIL)
    assert STREAMLIT_PYTHON is not None
    done = subprocess.run(  # noqa: S603 (the test's own Streamlit Python)
        [STREAMLIT_PYTHON, "-c", STATE_RUN, str(page)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    out: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["state"]["region_pick"] == "West" and out["state"]["seen"] == [1, 2]
    assert out["state"]["rows"] == {"kind": "DataFrame", "rows": 2}
