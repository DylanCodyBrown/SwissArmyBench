"""A text document's tab (the owner, 2026-11-27: "Our markdown reader and inline editor would be a great
addition" / "html, markdown, and renderable code should get a preview toggle" / "Mermaid support and uml
support" / "The idea is the context documentation for a project can be created and edited"), in the browser on
a made-up project: a .md opens rendered, a click edits one block in place and Escape writes only that block
back, a task box ticks in the file, a ```mermaid block draws; the one Preview toggle and its three views,
remembered per tab; an HTML page drawn in the walled-off frame, where a script cannot reach the app; each UML
starter draws without an error; a broken diagram shows its error line; a diagram saved as SVG and PNG."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, open_page

README = (
    "# Made-up shop\r\n"
    "\r\n"
    "The first paragraph, as it was.\r\n"
    "\r\n"
    "## Plan\r\n"
    "\r\n"
    "- [ ] Check the totals\r\n"
    "- [x] Load the orders\r\n"
    "  - from the warehouse\r\n"
    "\r\n"
    "| Table | Rows |\r\n"
    "|---|---|\r\n"
    "| orders | weekly |\r\n"
    "\r\n"
    "```python\r\n"
    "total = 6 * 7\r\n"
    "```\r\n"
    "\r\n"
    "```mermaid\r\n"
    "flowchart LR\r\n"
    "    load[Load] --> check[Check]\r\n"
    "```\r\n"
    "\r\n"
    "See [the notes](docs/notes.md) and ![the logo](docs/logo.svg).\r\n"
)
LOGO = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
    '<rect width="40" height="20" fill="#2f6fde"/></svg>'
)
# A page whose script does its own work, then tries to reach the app's page, its cookie and its storage.
PAGE = """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><title>Made-up page</title></head>
  <body>
    <h1 id="made-up-heading">Made-up page</h1>
    <p id="ran">not run</p>
    <p id="reached">nothing tried</p>
    <img id="beside" src="logo.svg" alt="beside" />
    <script>
      document.getElementById("ran").textContent = "ran: " + (6 * 7);
      var got = [];
      try { got.push("title=" + parent.document.title); } catch (e) { got.push("parent blocked"); }
      try { got.push("cookie=" + document.cookie); } catch (e) { got.push("cookie blocked"); }
      try { got.push("storage=" + localStorage.length); } catch (e) { got.push("storage blocked"); }
      try { parent.document.body.setAttribute("data-reached", "yes"); }
      catch (e) { got.push("write blocked"); }
      document.getElementById("reached").textContent = got.join("; ");
      fetch("/project")
        .then(function () { document.title = "fetched"; })
        .catch(function () { document.title = "fetch blocked"; });
    </script>
  </body>
</html>
"""


def project(server: dict[str, Any], name: str) -> Path:
    state = call(server, "POST", "/project/new", {"path": str(server["tmp"] / "projects" / name)})
    folder = Path(state.get("folder") or state["project"]["folder"])
    (folder / "docs").mkdir(exist_ok=True)
    (folder / "README.md").write_bytes(README.encode("utf-8"))
    (folder / "docs" / "logo.svg").write_text(LOGO, encoding="utf-8")
    (folder / "docs" / "notes.md").write_text("# Notes\n\nA made-up note.\n", encoding="utf-8")
    return folder


def doc(folder: Path, relative: str) -> str:
    return f"scripts?path={folder / relative}"


def saved(page: Page) -> None:
    expect(page.locator(".wb-tab.active .wb-tab-dirty")).to_have_text("")


def test_a_markdown_file_opens_rendered_and_one_block_is_edited_in_place(
    browser: Browser, server: dict[str, Any], page_errors: list[str]
) -> None:
    folder = project(server, "made_up_docs")
    page = open_page(browser, server, doc(folder, "README.md"))
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    reader = page.locator(".wb-textfile .md-reader")
    # It opens read: the toggle says so, no editor is drawn, every block is its own box.
    expect(page.locator(".wb-view-preview")).to_have_text("Read")
    expect(page.locator(".wb-view-preview")).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".wb-textfile .monaco-editor")).to_have_count(0)
    expect(reader.locator("h1")).to_have_text("Made-up shop")
    expect(reader.locator(".md-block")).to_have_count(7)
    expect(reader.locator("table.md-table td").first).to_have_text("orders")
    expect(reader.locator("li li")).to_have_text("from the warehouse")  # a nested list
    expect(reader.locator("pre code[data-lang=python] span").first).to_be_visible()  # coloured
    expect(reader.locator(".md-block.kind-diagram svg")).to_be_visible()  # the ```mermaid block drawn
    expect(reader.locator(".md-block.kind-diagram pre")).to_have_count(0)
    # A picture beside the file is read through the server; nothing is fetched from the web.
    picture = reader.locator("img.md-image")
    expect(picture).to_have_attribute("alt", "the logo")
    assert page.evaluate("(img) => img.complete && img.naturalWidth > 0", picture.element_handle())

    # Click a paragraph: its source text in place; edit it; Escape: drawn again, the file changed only there.
    paragraph = reader.locator(".md-block.kind-paragraph").first
    paragraph.click()
    box = reader.locator("textarea.md-block-edit")
    expect(box).to_be_focused()
    expect(box).to_have_value("The first paragraph, as it was.")
    expect(reader.locator("textarea")).to_have_count(1)
    box.fill("The first paragraph, **edited** in place.")
    page.keyboard.press("Escape")
    expect(reader.locator("textarea")).to_have_count(0)
    expect(reader.locator(".md-block.kind-paragraph").first.locator("strong")).to_have_text("edited")
    saved(page)
    after = README.replace("The first paragraph, as it was.", "The first paragraph, **edited** in place.")
    assert (folder / "README.md").read_bytes() == after.encode("utf-8")  # byte for byte elsewhere, CRLF kept

    # Click away finishes an edit too (a heading this time).
    reader.locator(".md-block.kind-heading").nth(1).click()
    reader.locator("textarea.md-block-edit").fill("## The plan")
    reader.locator("h1").click()
    expect(reader.locator("h2")).to_have_text("The plan")
    after = after.replace("## Plan", "## The plan")
    expect(reader.locator("textarea.md-block-edit")).to_have_value("# Made-up shop")  # the block clicked
    page.keyboard.press("Escape")
    saved(page)
    assert (folder / "README.md").read_bytes() == after.encode("utf-8")

    # Ticking a task box writes the file: one character.
    boxes = reader.locator(".md-task input[type=checkbox]")
    expect(boxes.nth(0)).not_to_be_checked()
    boxes.nth(0).click()
    expect(boxes.nth(0)).to_be_checked()
    expect(reader.locator("textarea")).to_have_count(0)  # a tick is not an edit of the block
    saved(page)
    ticked = after.replace("- [ ] Check the totals", "- [x] Check the totals")
    assert (folder / "README.md").read_bytes() == ticked.encode("utf-8")
    boxes.nth(1).click()
    expect(boxes.nth(1)).not_to_be_checked()
    saved(page)
    assert b"- [ ] Load the orders" in (folder / "README.md").read_bytes()

    # A link to another file of the project opens it, as a document of its own.
    reader.get_by_role("link", name="the notes").click()
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("notes.md")
    expect(page.locator(".wb-doc-body:not([hidden]) .md-reader h1")).to_have_text("Notes")
    assert page_errors == []
    page.close()


def test_the_toggle_has_three_views_remembered_by_each_tab(browser: Browser, server: dict[str, Any]) -> None:
    folder = project(server, "made_up_views")
    page = open_page(browser, server, doc(folder, "README.md"))
    shown = page.locator(".wb-doc-body:not([hidden]) .wb-textfile")
    expect(shown).to_have_attribute("data-view", "preview")

    page.click(".wb-view-split")
    expect(shown).to_have_attribute("data-view", "split")
    expect(shown.locator(".wb-text-source .monaco-editor")).to_be_visible()
    expect(shown.locator(".md-reader h1")).to_have_text("Made-up shop")
    # Split's preview only shows (its source is beside it), and follows typing after a short pause.
    shown.locator(".md-block.kind-paragraph").first.click()
    expect(shown.locator("textarea.md-block-edit")).to_have_count(0)
    shown.locator(".wb-text-source .monaco-editor .view-lines").click()
    page.keyboard.press("Control+Home")
    page.keyboard.press("End")
    page.keyboard.type(" typed")
    expect(shown.locator(".md-reader h1")).to_have_text("Made-up shop typed")
    assert call(server, "GET", "/screen/focused")["tab"]["view"] == "split"  # the agent's app_screen says it

    # Another document, another view; back on the first tab its view is as it was left.
    page.goto(
        f"http://127.0.0.1:{server['port']}/blazor/{doc(folder, 'docs/notes.md')}#token={server['token']}"
    )
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("notes.md")
    page.close()

    page = open_page(browser, server, doc(folder, "README.md"))
    page.locator(".files-pane .files-item[data-path='docs/notes.md']").click()
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("notes.md")
    notes = page.locator(".wb-doc-body:not([hidden]) .wb-textfile")
    expect(notes).to_have_attribute("data-view", "preview")
    page.click(".wb-doc-body:not([hidden]) ~ * .wb-view-source, .wb-view-source")
    expect(notes).to_have_attribute("data-view", "source")
    expect(notes.locator(".md-reader")).to_have_count(0)
    page.locator(".wb-tab", has_text="README.md").click()
    expect(page.locator(".wb-doc-body:not([hidden]) .wb-textfile")).to_have_attribute("data-view", "preview")
    page.locator(".wb-tab", has_text="notes.md").click()
    expect(page.locator(".wb-doc-body:not([hidden]) .wb-textfile")).to_have_attribute("data-view", "source")

    # Plain text has no preview and no toggle.
    (folder / "todo.txt").write_text("made-up to do\n", encoding="utf-8")
    page.goto(f"http://127.0.0.1:{server['port']}/blazor/{doc(folder, 'todo.txt')}#token={server['token']}")
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("todo.txt")
    expect(page.locator(".wb-view-toggle")).to_have_count(0)
    page.close()


def test_an_html_page_runs_in_the_walled_off_frame_and_cannot_reach_the_app(
    browser: Browser, server: dict[str, Any]
) -> None:
    folder = project(server, "made_up_html")
    (folder / "docs" / "page.html").write_text(PAGE, encoding="utf-8")
    page = open_page(browser, server, doc(folder, "docs/page.html"))
    shown = page.locator(".wb-textfile")
    expect(shown).to_have_attribute("data-view", "source")  # it opens in the editor, in HTML
    expect(page.locator(".wb-view-preview")).to_have_text("Preview")
    title = page.title()
    page.click(".wb-view-split")

    frame_element = shown.locator("iframe.wb-preview-frame")
    expect(frame_element).to_have_attribute(
        "sandbox", "allow-scripts"
    )  # no allow-same-origin: not the app's origin
    expect(frame_element).to_have_attribute("src", "/blazor/design.html")
    frame = shown.frame_locator("iframe.wb-preview-frame")
    expect(frame.locator("#made-up-heading")).to_have_text("Made-up page")
    expect(frame.locator("#ran")).to_have_text("ran: 42")  # its own script runs, inside the frame
    reached = frame.locator("#reached")
    expect(reached).to_contain_text("parent blocked")
    said = reached.inner_text()
    assert "title=" not in said and "write blocked" in said  # the app's page is out of reach
    assert server["token"] not in said and "sab_" not in said  # no cookie, no token
    assert "storage blocked" in said  # no storage of the app's origin (an opaque origin has none)
    # Nothing loads beside the file or over the network, and the app's page was never written to.
    assert frame.locator("#beside").evaluate("(img) => img.naturalWidth") == 0
    page.wait_for_timeout(500)
    assert page.title() == title
    assert page.evaluate("document.body.getAttribute('data-reached')") is None
    assert page.locator("#made-up-heading").count() == 0  # never part of the app's own page
    expect(shown.locator(".wb-preview-note")).to_contain_text(
        "loads nothing from this computer or the network"
    )
    child = next(f for f in page.frames if f != page.main_frame)
    assert child.evaluate("document.title") == "fetch blocked"  # the frame's policy: no request leaves it
    assert child.evaluate("window.origin") == "null"

    # The preview follows typing; Preview alone fills the tab.
    shown.locator(".wb-text-source .monaco-editor .view-lines").click()
    page.keyboard.press("Control+F")
    page.keyboard.type("not run")
    page.keyboard.press("Escape")
    page.keyboard.type("typed here")
    expect(frame.locator("#made-up-heading")).to_be_visible()
    page.click(".wb-view-preview")
    expect(shown.locator(".wb-text-source")).to_have_count(0)
    expect(shown.frame_locator("iframe.wb-preview-frame").locator("#made-up-heading")).to_be_visible()

    # An SVG file: a picture in the same walled-off frame.
    page.goto(
        f"http://127.0.0.1:{server['port']}/blazor/{doc(folder, 'docs/logo.svg')}#token={server['token']}"
    )
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("logo.svg")
    page.click(".wb-view-split")
    picture = page.locator(".wb-textfile").frame_locator("iframe.wb-preview-frame").locator("img")
    expect(picture).to_be_visible()
    assert picture.evaluate("(img) => img.naturalWidth") == 40
    expect(page.locator(".wb-text-preview svg")).to_have_count(0)  # never drawn into the app's page
    page.close()


def test_each_uml_starter_draws_and_a_broken_diagram_shows_its_line(
    browser: Browser, server: dict[str, Any], page_errors: list[str]
) -> None:
    folder = project(server, "made_up_uml")
    kinds = ("flowchart", "class", "sequence", "state", "er", "gantt")
    for kind in kinds:
        made = call(
            server,
            "POST",
            "/scripts/files/new",
            {"type": "diagram", "name": f"made_up_{kind}", "variant": kind},
        )
        assert made["relative"] == f"docs/diagrams/made_up_{kind}.mmd"
    page = open_page(browser, server, "scripts")
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    for kind in kinds:
        page.goto(
            f"http://127.0.0.1:{server['port']}/blazor/{doc(folder, f'docs/diagrams/made_up_{kind}.mmd')}"
            f"#token={server['token']}"
        )
        expect(page.locator(".wb-tab.active .tab-label")).to_have_text(f"made_up_{kind}.mmd")
        page.click(".wb-view-split")
        diagram = page.locator(".wb-textfile .wb-diagram")
        expect(diagram.locator("svg")).to_be_visible()
        expect(diagram).to_have_attribute("data-drawn", "true")
        expect(diagram.locator(".wb-preview-error")).to_have_count(0)  # each starter is a valid diagram
        expect(page.locator("#blazor-error-ui")).to_be_hidden()

    # The New file dialog's Diagram has its kinds to pick from.
    page.click(".wb-top-new")
    page.click(".context-menu [role=menuitem]:has-text('Diagram')")
    dialog = page.locator(".dialog[aria-label='New Diagram']")
    expect(dialog.get_by_label("Kind").locator("option")).to_have_text(
        [
            "Flowchart (activity)",
            "Class diagram",
            "Sequence diagram",
            "State diagram",
            "Entity-relationship diagram",
            "Gantt chart",
        ]
    )
    dialog.get_by_label("Kind").select_option("sequence")
    dialog.get_by_label("Name").fill("made_up_calls")
    dialog.locator(".new-file-create").click()
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_calls.mmd")
    assert (folder / "docs" / "diagrams" / "made_up_calls.mmd").read_text().startswith("sequenceDiagram\n")

    # A broken diagram: Mermaid's own message and its line, the last good drawing left in place.
    page.click(".wb-view-split")
    shown = page.locator(".wb-doc-body:not([hidden]) .wb-textfile")
    expect(shown.locator(".wb-diagram svg")).to_be_visible()
    shown.locator(".wb-text-source .monaco-editor .view-lines").click()
    page.keyboard.press("Control+End")
    page.keyboard.type("    User-->>>!!! App: not a message\n")
    error = shown.locator(".wb-preview-error")
    expect(error).to_contain_text("Line 9")
    expect(error.locator(".wb-preview-error-words")).not_to_be_empty()
    expect(shown.locator(".wb-diagram svg")).to_be_visible()  # never a blank preview
    expect(shown.locator(".wb-text-source .squiggly-error")).not_to_have_count(0)  # marked on its line
    assert page_errors == []
    page.close()


def test_a_diagram_is_saved_beside_its_file_as_svg_and_png(browser: Browser, server: dict[str, Any]) -> None:
    folder = project(server, "made_up_pictures")
    call(
        server, "POST", "/scripts/files/new", {"type": "diagram", "name": "made_up_flow", "variant": "class"}
    )
    page = open_page(browser, server, doc(folder, "docs/diagrams/made_up_flow.mmd"))
    expect(page.locator(".wb-save-svg")).to_be_disabled()  # Source: nothing is drawn to save
    page.click(".wb-view-preview")
    expect(page.locator(".wb-textfile .wb-diagram svg")).to_be_visible()
    page.click(".wb-save-svg")
    expect(page.locator(".note-corner")).to_contain_text("Saved made_up_flow.svg")
    page.click(".wb-save-png")
    expect(page.locator(".note-corner")).to_contain_text("Saved made_up_flow.png")
    diagrams = folder / "docs" / "diagrams"
    assert "<svg" in (diagrams / "made_up_flow.svg").read_text(encoding="utf-8")[:200]
    assert (diagrams / "made_up_flow.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    page.close()
