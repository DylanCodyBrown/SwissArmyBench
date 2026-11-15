# ruff: noqa: F811
"""HTML cells (docs/ideas.md, 2026-11-14), in a real browser: the two faces, the pane that resizes, the
walled-off frame (its scripts run; nothing loads over the network; it cannot reach the app), and
`{{ name }}` filled from the kernel, in a notebook and in a script. Made-up data only."""

from __future__ import annotations

import http.server
import json
import re
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, FrameLocator, Locator, Page, expect

from swissarmygrid.domain import html_cells, notebooks
from tests.e2e.test_table_cells_page import (
    close_tables,
    open_as_grid,
    open_workbench,
    type_cell,
    window,
)
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_workbench_page import add_cell, start

CARD = (
    "<style>.card{padding:16px;border-radius:12px;background:#0b6e4f;color:#fff}</style>\n"
    '<div class="card"><h2 id="title">Orders</h2><p>A made-up card</p></div>\n'
    "<script>document.getElementById('title').textContent = 'Orders, scripted';</script>"
)


# What a design tries, and says in its own page. ADDRESS is a web server that is not the app.
PROBE = """
<img id="pic" src="ADDRESS/remote.png">
<link rel="stylesheet" href="ADDRESS/remote.css">
<script src="ADDRESS/remote.js"></script>
<img id="inline" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8'/%3E">
<p id="out">not run</p>
<script>
  const say = (id, text) => {
    const p = document.createElement("p");
    p.id = id;
    p.textContent = text;
    document.body.append(p);
  };
  const attempt = (id, closed, what) => {
    try { say(id, what()); } catch (e) { say(id, closed); }
  };
  document.getElementById("out").textContent = "scripts run";
  fetch("ADDRESS/fetched").then(() => say("fetch", "fetched"), () => say("fetch", "fetch failed"));
  fetch("/datasets").then((r) => say("app", "app answered " + r.status), () => say("app", "app not reached"));
  attempt("parent", "parent closed", () => "parent title: " + parent.document.title);
  attempt("top", "top closed", () => "token: " + top.location.hash);
  attempt("storage", "storage closed", () => "storage: " + localStorage.length);
  attempt("cookie", "cookie closed", () => "cookie: [" + document.cookie + "]");
  attempt("popup", "popup refused", () => (window.open("ADDRESS/popup") ? "popup opened" : "popup refused"));
  new Image().src = "ADDRESS/beacon.png";
  try { new WebSocket("SOCKET/socket"); } catch (e) { /* refused */ }
  say("origin", "origin: " + self.origin);
  setTimeout(() => say("remote", "width " + document.getElementById("pic").naturalWidth), 600);
</script>
"""


def design(cell: Locator) -> FrameLocator:
    return cell.frame_locator(".wb-design-frame")


def html_cells_of(server: dict[str, Any]) -> list[dict[str, Any]]:
    return list(window(server, "html.list")["cells"])


def new_notebook(browser: Browser, server: dict[str, Any]) -> Page:
    close_tables(server)
    workbench = open_workbench(browser, server)
    start(workbench)
    expect(workbench.locator(".wb-cell .monaco-editor").first).to_be_visible(timeout=20000)
    return workbench


@pytest.fixture
def outside() -> Iterator[tuple[str, list[str]]]:
    """A web server that is not the app (another port: another origin), and what was asked of it."""
    asked: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            asked.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"from outside")

        do_POST = do_GET

        def log_message(self, *args: Any) -> None:
            pass

    listening = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=listening.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{listening.server_address[1]}", asked
    listening.shutdown()


def test_an_html_cell_shows_its_html_when_edited_and_its_design_when_left(
    browser: Browser, server: dict[str, Any]
) -> None:
    workbench = new_notebook(browser, server)
    # "+ Cell" adds one, with the cursor in it.
    add_cell(workbench, "HTML")
    cell = workbench.locator(".wb-cell.kind-html")
    expect(cell).to_have_count(1)
    expect(cell.locator("select[aria-label='Cell kind']")).to_have_value("html")
    expect(cell.locator(".monaco-editor")).to_be_visible(timeout=20000)
    cell.locator(".monaco-editor").click()
    workbench.keyboard.insert_text(CARD)
    # Being edited: its HTML, coloured as HTML (a tag is not coloured as plain text is).
    expect(cell.locator(".wb-design")).to_be_hidden()
    tag = cell.locator(".view-lines span", has_text=re.compile(r"^div$")).first
    plain = cell.locator(".view-lines span", has_text=re.compile(r"made-up")).first
    assert tag.evaluate("e => getComputedStyle(e).color") != plain.evaluate("e => getComputedStyle(e).color")
    # Left: it draws by itself, no Run. Its script ran.
    workbench.locator(".wb-cell").first.locator(".monaco-editor").click()
    expect(cell).to_have_class(re.compile(r"\brendered\b"))
    expect(cell.locator(".wb-editor")).to_be_hidden()
    expect(design(cell).locator("#title")).to_have_text("Orders, scripted", timeout=20000)
    assert design(cell).locator(".card").evaluate("e => getComputedStyle(e).color") == "rgb(255, 255, 255)"
    # Plain HTML says nothing about being current, and has no Run of its own.
    expect(cell.locator(".wb-design-bar")).to_be_hidden()
    listed = html_cells_of(server)
    assert listed[0]["state"] == "plain" and listed[0]["names"] == [] and listed[0]["html"] == CARD

    # A click on the cell's head opens the HTML again; Escape leaves it and the design is back.
    cell.locator(".wb-number").click()
    expect(cell.locator(".wb-editor")).to_be_visible()
    expect(cell.locator(".wb-design")).to_be_hidden()
    workbench.keyboard.press("Control+End")
    workbench.keyboard.insert_text("\n<p id='more'>One more line</p>")
    workbench.keyboard.press("Escape")
    expect(design(cell).locator("#more")).to_have_text("One more line", timeout=20000)
    # The Edit button and Enter open it too; a click inside the design stays in the design.
    design(cell).locator("#more").click()
    expect(cell).to_have_class(re.compile(r"\brendered\b"))
    expect(cell).to_have_class(re.compile(r"\bselected\b"))
    cell.get_by_role("button", name="Edit HTML").click()
    expect(cell.locator(".wb-editor")).to_be_visible()
    workbench.keyboard.press("Escape")
    expect(cell.locator(".wb-design")).to_be_visible()
    workbench.keyboard.press("Enter")
    expect(cell.locator(".wb-editor")).to_be_visible()
    workbench.keyboard.press("Escape")

    # Command mode: H makes a cell HTML, Y makes it Python again; the palette has both.
    first = workbench.locator(".wb-cell").first
    first.locator(".wb-number").click()
    workbench.keyboard.press("Escape")
    workbench.keyboard.press("h")
    expect(first).to_have_class(re.compile(r"\bkind-html\b"))
    workbench.keyboard.press("y")
    expect(first).to_have_class(re.compile(r"\bkind-code\b"))
    commands = {c["id"]: c for c in window(server, "commands")}
    assert commands["cell.toHtml"]["keys"] == "H" and "html.add" in commands and "html.run" in commands


def test_the_design_runs_walled_off_and_loads_nothing_over_the_network(
    browser: Browser, server: dict[str, Any], outside: tuple[str, list[str]]
) -> None:
    address, asked = outside
    workbench = new_notebook(browser, server)
    probe = PROBE.replace("ADDRESS", address).replace("SOCKET", address.replace("http", "ws"))
    window(server, "html.add", source=probe)
    cell = workbench.locator(".wb-cell.kind-html")
    frame = design(cell)
    # Its scripts run...
    expect(frame.locator("#out")).to_have_text("scripts run", timeout=20000)
    expect(frame.locator("#inline")).to_have_js_property("naturalWidth", 8)  # what is inside the cell loads
    # ...but nothing reaches the network, the app, the page around it or its storage.
    expect(frame.locator("#fetch")).to_have_text("fetch failed")
    expect(frame.locator("#app")).to_have_text("app not reached")
    expect(frame.locator("#parent")).to_have_text("parent closed")
    expect(frame.locator("#top")).to_have_text("top closed")
    expect(frame.locator("#storage")).to_have_text("storage closed")
    expect(frame.locator("#cookie")).to_have_text("cookie closed")
    expect(frame.locator("#popup")).to_have_text("popup refused")
    expect(frame.locator("#origin")).to_have_text("origin: null")
    expect(frame.locator("#remote")).to_have_text("width 0")
    assert cell.locator(".wb-design-frame").get_attribute("sandbox") == "allow-scripts"

    # Going somewhere else is refused too: by a link, by a script, by a form.
    leave = f"""
<a id="link" href="{address}/by-link">a link</a>
<form id="form" action="{address}/by-form"><button>send</button></form>
<p id="still">still here</p>
<script>
  setTimeout(() => {{ try {{ document.getElementById("form").submit(); }} catch (e) {{}} }}, 50);
  setTimeout(() => document.getElementById("link").click(), 150);
  setTimeout(() => {{ try {{ top.location.href = "{address}/by-top"; }} catch (e) {{}} }}, 250);
  setTimeout(() => {{ location.href = "{address}/by-script"; }}, 350);
</script>
"""
    window(server, "html.add", source=leave)
    second = workbench.locator(".wb-cell.kind-html").nth(1)
    expect(design(second).locator("#still")).to_have_text("still here", timeout=20000)
    workbench.wait_for_timeout(1500)
    assert asked == [], f"the design reached the network: {asked}"
    assert "/workbench" in workbench.url  # the page around it did not go anywhere


def test_the_frames_page_carries_the_policy_the_rules_name() -> None:
    shell = (Path(__file__).parents[2] / "web" / "static" / "design.html").read_text(encoding="utf-8")
    assert f'content="{html_cells.FRAME_POLICY}"' in shell
    assert shell.count("Content-Security-Policy") == 1
    page = (Path(__file__).parents[2] / "web" / "static" / "workbench.html").read_text(encoding="utf-8")
    # The Workbench lets a frame load only from the app itself: a design cannot go to another site.
    assert "frame-src 'self'" in page


def test_the_designs_pane_resizes_and_its_height_is_saved(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    close_tables(server)
    book = tmp_path / "design.ipynb"
    book.write_text(
        notebooks.write_notebook([notebooks.Cell("html", "<h1>Made-up heading</h1>")]), encoding="utf-8"
    )
    workbench = open_workbench(browser, server, book)
    cell = workbench.locator(".wb-cell.kind-html")
    expect(design(cell).locator("h1")).to_have_text("Made-up heading", timeout=20000)
    stage = cell.locator(".wb-design-stage")
    grip = cell.get_by_role("separator", name="Resize the design")
    # With no saved height the pane takes the design's own.
    expect(grip).to_have_attribute("aria-valuetext", re.compile("fitted to the design"))
    fitted = stage.bounding_box()["height"]  # type: ignore[index]
    assert 60 <= fitted < 200 and html_cells_of(server)[0]["height"] is None

    # Drag its bottom edge down by 150.
    box = grip.bounding_box()
    assert box is not None
    workbench.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    workbench.mouse.down()
    workbench.mouse.move(box["x"] + box["width"] / 2, box["y"] + 150, steps=5)
    workbench.mouse.up()
    dragged = stage.bounding_box()["height"]  # type: ignore[index]
    assert abs(dragged - (fitted + 150)) <= 6
    assert html_cells_of(server)[0]["height"] == round(dragged)
    expect(workbench.locator(".wb-tabs .tab-item").first).to_contain_text("●")  # a change to save

    # The keyboard: arrows, as the Workbench's splitters; Enter fits it to the design again.
    grip.focus()
    workbench.keyboard.press("ArrowDown")
    workbench.keyboard.press("Shift+ArrowDown")
    assert html_cells_of(server)[0]["height"] == round(dragged) + 96
    workbench.keyboard.press("ArrowUp")
    assert html_cells_of(server)[0]["height"] == round(dragged) + 80
    workbench.keyboard.press("Enter")
    assert html_cells_of(server)[0]["height"] is None
    # The agent sizes it too.
    window(server, "html.resize", number=1, height=300)
    assert abs(stage.bounding_box()["height"] - 300) <= 1  # type: ignore[index]

    # Saved in the file: the cell's metadata, in a cell plain Jupyter draws.
    window(server, "file.save")
    saved = json.loads(book.read_text(encoding="utf-8"))["cells"][0]
    assert saved["source"][0] == "%%html\n" and saved["metadata"]["swissarmygrid"]["height"] == 300
    workbench.close()
    again = open_workbench(browser, server, book)
    expect(again.locator(".wb-cell.kind-html .wb-design-stage")).to_have_css("height", "300px", timeout=20000)


VALUES = (
    "import pandas as pd\n"
    "total = 1204\n"
    "name = '<img src=x onerror=\"document.body.id=`pwned`\"><script>document.body.id=`pwned`</script>'\n"
    "stores = pd.DataFrame({'store': [f'Store {i} <b>' for i in range(1, 121)], 'amount': range(120)})\n"
)
STORY = (
    "<h1 id='headline'>{{ total }} orders</h1>\n"
    "<p id='who'>From {{ name }}</p>\n"
    "{{ stores }}\n"
    "<p id='none'>{{ nobody }}</p>\n"
    "<p id='bar' title=\"{{ name }}\" style='width: {{ total }}px'>bar</p>\n"
    "<script>const rows = {{ stores }}; const who = {{ name }};\n"
    "document.getElementById('bar').dataset.rows = rows.length + ' rows, ' + typeof who;</script>"
)


def test_names_are_filled_from_the_kernel_and_the_cell_goes_out_of_date(
    browser: Browser, server: dict[str, Any]
) -> None:
    workbench = new_notebook(browser, server)
    type_cell(workbench, 0, VALUES)
    workbench.keyboard.press("Control+Enter")
    expect(workbench.locator(".wb-cell").first.locator(".wb-count")).to_have_text(
        re.compile(r"\[\d+\]"), timeout=90000
    )
    window(server, "html.add", source=STORY)
    cell = workbench.locator(".wb-cell.kind-html")
    frame = design(cell)
    state = cell.locator(".wb-design-state")
    # Before its run: the design, each name as written, and what to do.
    expect(frame.locator("#headline")).to_have_text("{{ total }} orders", timeout=20000)
    expect(state).to_have_text("Not run yet")
    assert html_cells_of(server)[0]["names"] == ["total", "name", "stores", "nobody"]

    cell.locator(".wb-design").get_by_role("button", name="Run").click()
    expect(frame.locator("#headline")).to_have_text("1204 orders", timeout=60000)
    # A cell that is current says nothing.
    expect(cell.locator(".wb-design-bar")).to_be_hidden()
    # Data is text, never markup or script.
    expect(frame.locator("#who")).to_have_text(
        'From <img src=x onerror="document.body.id=`pwned`"><script>document.body.id=`pwned`</script>'
    )
    assert frame.locator("body").get_attribute("id") is None and frame.locator("#who img").count() == 0
    # A table, up to its cap, saying what it leaves out.
    expect(frame.locator("table.sag-table tbody tr")).to_have_count(50)
    expect(frame.locator("table.sag-table caption")).to_have_text("first 50 of 120 rows")
    expect(frame.locator("table.sag-table tbody tr").first).to_have_text("Store 1 <b>0")
    # An unknown name is a plain marker, and the design is whole.
    expect(frame.locator("#none")).to_have_text("{{ nobody }} not found")
    expect(cell.locator(".wb-design-notes")).to_contain_text("{{ nobody }} was not found in the kernel.")
    # Inside a tag: a number goes in, hostile text is left out and said; inside a script: a literal.
    bar = frame.locator("#bar")
    assert bar.get_attribute("title") == "" and bar.get_attribute("style") == "width: 1204px"
    assert bar.get_attribute("data-rows") == "120 rows, string"
    expect(cell.locator(".wb-design-notes")).to_contain_text("{{ name }} is left out of a tag")

    # A variable it names changes: out of date, yellow, saying which.
    window(server, "console.run", code="total = 1300")
    expect(state).to_have_text(
        re.compile(r"^Out of date · total changed · last run \d\d:\d\d$"), timeout=30000
    )
    expect(cell).to_have_class(re.compile(r"\bstale\b"))
    expect(frame.locator("#headline")).to_have_text("1204 orders")  # nothing runs by itself
    assert window(server, "html.run")["cells"][0]["state"] == "upToDate"
    expect(frame.locator("#headline")).to_have_text("1300 orders", timeout=30000)
    expect(cell.locator(".wb-design-bar")).to_be_hidden()

    # Its HTML changes: the design follows at once, with the values of the last run, and says Out of date.
    cell.get_by_role("button", name="Edit HTML").click()
    workbench.keyboard.press("Control+Home")
    workbench.keyboard.insert_text("<h2 id='new'>New: {{ total }}</h2>\n")
    workbench.keyboard.press("Escape")
    expect(frame.locator("#new")).to_have_text("New: 1300", timeout=20000)
    expect(state).to_have_text(re.compile(r"^Out of date · last run \d\d:\d\d$"))

    # Undoing the edit clears it by itself. The editor's own undo, as in any cell: it takes the typing
    # back a few words at a time, so Ctrl+Z is pressed until the HTML is as it was. After a pause, so
    # the keys reach the editor: pressed in the instant after Edit HTML they once reached the page
    # before the editor had the keyboard, and the browser's own undo took the whole edit back in one
    # go, which is what this test used to pass on (and fail on, whenever the editor was quicker).
    def html_now() -> str:
        return str(next(c["source"] for c in window(server, "doc.read")["cells"] if c["kind"] == "html"))

    cell.get_by_role("button", name="Edit HTML").click()
    expect(cell.locator(".monaco-editor")).to_be_visible()
    workbench.wait_for_timeout(700)
    assert html_now().startswith("<h2 id='new'>")
    presses = 0
    while html_now() != STORY and presses < 30:
        workbench.keyboard.press("Control+z")
        presses += 1
    assert html_now() == STORY and 1 <= presses < 30, presses
    workbench.keyboard.press("Escape")
    expect(cell.locator(".wb-design-bar")).to_be_hidden(timeout=20000)
    expect(frame.locator("#new")).to_have_count(0)
    # Ctrl+Enter in the HTML runs it.
    cell.get_by_role("button", name="Edit HTML").click()
    workbench.keyboard.press("Control+End")
    workbench.keyboard.insert_text("\n<p id='tail'>{{ total }} again</p>")
    workbench.keyboard.press("Control+Enter")
    expect(frame.locator("#tail")).to_have_text("1300 again", timeout=30000)
    expect(cell.locator(".wb-design-bar")).to_be_hidden()

    # A restarted kernel holds none of it: the cell has not run there.
    window(server, "run.restart")
    expect(state).to_have_text("Not run yet", timeout=60000)


def test_a_saved_html_cell_opens_with_its_last_design_and_its_uses_line(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    close_tables(server)
    book = tmp_path / "story.ipynb"
    cells = [
        notebooks.Cell("code", "import pandas as pd"),
        notebooks.Cell("code", "sales = pd.DataFrame({'store': ['North', 'South'], 'amount': [10, 20]})"),
        notebooks.Cell("code", "total = int(sales.amount.sum())"),
        notebooks.Cell("html", "<h1 id='t'>{{ total }} sold</h1>\n{{ sales }}", height=260),
    ]
    book.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    workbench = open_workbench(browser, server, book)
    cell = workbench.locator(".wb-cell.kind-html")
    state = cell.locator(".wb-design-state")
    expect(state).to_have_text("Not run yet", timeout=20000)
    workbench.get_by_role("button", name="Run all").click()
    expect(design(cell).locator("#t")).to_have_text("30 sold", timeout=90000)
    expect(design(cell).locator("table tbody tr")).to_have_count(2)

    # The table opens in the grid: the cell that asks for it says so on its first line, with a link.
    open_as_grid(server, "sales")
    expect(workbench.locator(".wb-tcell.role-transformations")).to_have_count(1, timeout=20000)
    workbench.wait_for_timeout(1500)
    first = str(html_cells_of(server)[0]["html"]).split("\n")[0]
    assert re.fullmatch(r"<!-- uses sales @cell\d+ -->", first), first
    # The app's own line does not make the cell out of date.
    expect(cell.locator(".wb-design-bar")).to_be_hidden()

    # Saved: IPython's own cell magic, the filled design as its output, the height.
    window(server, "file.save")
    saved = json.loads(book.read_text(encoding="utf-8"))["cells"]
    html = next(c for c in saved if c["metadata"].get("swissarmygrid", {}).get("kind") == "html")
    assert html["source"][0] == "%%html\n" and html["metadata"]["swissarmygrid"]["height"] == 260
    assert "30 sold" in html["outputs"][0]["data"]["text/html"]
    workbench.close()
    close_tables(server)

    # Opened again: the design as it was last drawn, and that it has not run since.
    again = open_workbench(browser, server, book)
    cell = again.locator(".wb-cell.kind-html")
    expect(design(cell).locator("#t")).to_have_text("30 sold", timeout=20000)
    expect(cell.locator(".wb-design-state")).to_have_text("Not run since opening")
    expect(cell.locator(".wb-design-stage")).to_have_css("height", "260px")


SCRIPT = (
    "total = 42\n"
    "# %% [1] [html] height=180 The card\n"
    'r"""\n'
    "<h1 id='t'>{{ total }} orders</h1>\n"
    "<p id='p'>A made-up card</p>\n"
    '"""\n'
    "# %% [2]\n"
    'print("after the card", total)\n'
)


def test_a_scripts_html_cell_shows_its_design_under_its_marker(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    close_tables(server)
    script = tmp_path / "story.py"
    script.write_text(SCRIPT, encoding="utf-8")
    workbench = open_workbench(browser, server, script)
    editor = workbench.locator(".wb-script-editor")
    lines = editor.locator(".view-lines")
    expect(lines).to_contain_text("# %% [1] [html] height=180 The card", timeout=20000)
    pane = editor.locator(".wb-design.in-script")
    frame = pane.frame_locator(".wb-design-frame")
    # The cursor is elsewhere: the design shows under the marker and the cell's lines are put away.
    expect(frame.locator("#p")).to_have_text("A made-up card", timeout=20000)
    expect(frame.locator("#t")).to_have_text("{{ total }} orders")
    expect(lines).not_to_contain_text("A made-up card")
    expect(lines).to_contain_text('print("after the card", total)')
    expect(pane.locator(".wb-design-stage")).to_have_css("height", "180px")
    expect(pane.locator(".wb-design-state")).to_have_text("Not run yet")
    expect(lines).to_contain_text("HTML · click this line to edit · Not run yet")
    assert window(server, "doc.read")["text"] == SCRIPT  # showing it changed nothing in the file

    # A click on the marker: the cursor is in the cell, so its lines show and its design does not.
    lines.locator("span", has_text="[html]").first.click()
    expect(lines).to_contain_text("<p id='p'>A made-up card</p>", timeout=20000)
    expect(pane).to_be_hidden()
    # Typed, then left: the design is back, with what was typed.
    window(server, "html.edit", number=1)
    workbench.keyboard.press("End")
    workbench.keyboard.insert_text("\n<p id='typed'>typed here</p>")
    workbench.keyboard.press("Control+End")
    expect(frame.locator("#typed")).to_have_text("typed here", timeout=20000)
    expect(lines).not_to_contain_text("typed here")

    # Run file runs the file as plain Python, then fills the cell's names from what it left.
    workbench.get_by_role("button", name="Run file").click()
    expect(workbench.locator(".wb-console-log")).to_contain_text("after the card 42", timeout=90000)
    expect(frame.locator("#t")).to_have_text("42 orders", timeout=30000)
    expect(pane.locator(".wb-design-bar")).to_be_hidden()  # current: nothing to say
    expect(lines).not_to_contain_text("Not run yet")
    # A variable changes: out of date; the agent runs it.
    window(server, "console.run", code="total = 50")
    expect(pane.locator(".wb-design-state")).to_have_text(
        re.compile(r"^Out of date · total changed · last run \d\d:\d\d$"), timeout=30000
    )
    cells = window(server, "html.run", number=1)["cells"]
    assert cells[0]["state"] == "upToDate" and cells[0]["names"] == ["total"]
    expect(frame.locator("#t")).to_have_text("50 orders", timeout=30000)

    # Its pane resizes: the height goes on the marker line.
    grip = pane.get_by_role("separator", name="Resize the design")
    box = grip.bounding_box()
    assert box is not None
    workbench.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    workbench.mouse.down()
    workbench.mouse.move(box["x"] + box["width"] / 2, box["y"] + 100, steps=5)
    workbench.mouse.up()
    expect(lines).to_contain_text(re.compile(r"\[html\]\sheight=2[78]\d\sThe"), timeout=20000)
    window(server, "html.resize", number=1, height=200)
    assert "# %% [1] [html] height=200 The card\n" in window(server, "doc.read")["text"]
    expect(pane.locator(".wb-design-stage")).to_have_css("height", "200px", timeout=20000)

    # The toolbar adds a cell after the cursor's, as one string that does nothing; the agent adds
    # one with HTML that a raw string cannot hold.
    window(server, "html.add", source='<p id="q">a """ and \'\'\' and a \\ </p>', height=90)
    text = window(server, "doc.read")["text"]
    assert '# %% [3] [html] height=90\n"""\n<p id="q">a \\"\\"\\" and \'\'\' and a \\\\ </p>\n"""\n' in text
    added = next(c for c in html_cells_of(server) if c["number"] == 3)
    assert added["html"] == '<p id="q">a """ and \'\'\' and a \\ </p>' and added["height"] == 90
    namespace: dict[str, Any] = {}
    exec(text, namespace)  # noqa: S102 (the file still runs as plain Python)
    assert namespace["total"] == 42
    add_cell(workbench, "HTML")
    expect(lines).to_contain_text("# %% [4] [html]", timeout=20000)
