"""Review comments on code (the owner, 2026-11-27: "highlight a part by draging mouse over that section
right click then make a comment, then a send to agent button to send all comments to and agent then reset the
file so no comments are retained"), in the browser on a made-up script: drag over lines, right-click,
Comment…, type; a second one on the cursor's line by its key; Save writes none of them; a send that fails
keeps them; Send to agent gives agent_inbox both in order with their lines and code, the editor is left with
none and the file's bytes are as before. Then the comments following an edit, the question before a tab
closes, the agent's own note and the screen state's count; and every kind of editor taking one."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, open_page

CODE = (
    '"""Made-up totals."""\n'
    "import os\n"
    "\n"
    "rows = [3, 4, 5]\n"
    "total = 0\n"
    "for row in rows:\n"
    "    total += row\n"
    "print(total)\n"
)


def script(server: dict[str, Any], name: str) -> Path:
    """A made-up project open on the module's server with one script; the script's file."""
    state = call(server, "POST", "/project/new", {"path": str(server["tmp"] / "projects" / name)})
    folder = Path(state.get("folder") or state["project"]["folder"])
    made = folder / "scripts" / "load.py"
    made.parent.mkdir(exist_ok=True)
    made.write_bytes(CODE.encode())
    return made


def open_script(browser: Browser, server: dict[str, Any], made: Path) -> Page:
    page = open_page(browser, server, f"scripts?path={made}")
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("load.py")
    expect(page.locator(".wb-script-editor .view-lines")).to_contain_text("for row in rows:")
    page.wait_for_timeout(700)  # the first lint settles: the lines are not drawn again under the mouse
    return page


def line(page: Page, text: str) -> dict[str, float]:
    """Where a line of the script is on screen (Monaco draws its lines again as it colours them)."""
    found = page.locator(".wb-script-editor .view-line", has_text=text).first
    for _ in range(40):
        box = found.bounding_box() if found.count() else None
        if box is not None:
            return {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]}
        page.wait_for_timeout(100)
    raise AssertionError(f"the line {text!r} is not on screen")


def drag_over(page: Page, first: str, last: str) -> None:
    """The mouse dragged from the start of one line to the end of another."""
    start, end = line(page, first), line(page, last)
    page.mouse.move(start["x"] + 1, start["y"] + start["height"] / 2)
    page.mouse.down()
    page.mouse.move(end["x"] + 60, end["y"] + end["height"] / 2, steps=6)
    width = page.locator(".wb-script-editor .view-line", has_text=last).first.locator("> span").bounding_box()
    assert width is not None
    page.mouse.move(width["x"] + width["width"] + 2, end["y"] + end["height"] / 2, steps=4)
    page.mouse.up()


def comment_by_menu(page: Page, first: str, last: str, words: str) -> None:
    drag_over(page, first, last)
    at = line(page, last)
    page.mouse.click(at["x"] + 30, at["y"] + at["height"] / 2, button="right")
    item = page.locator(".monaco-menu .action-label", has_text="Annotate…")
    expect(page.locator(".monaco-menu .action-label").first).to_have_text("Annotate…")  # the top of the menu
    expect(item).to_be_visible()
    page.wait_for_timeout(300)  # Monaco's menu takes no click in its first moment (the right click's release)
    item.click()
    box = page.locator(".review-box")
    expect(box).to_be_visible()
    box.locator("textarea").fill(words)
    box.get_by_role("button", name="Annotate", exact=True).click()
    expect(box).to_have_count(0)


def agent(server: dict[str, Any], command: str, args: dict[str, Any]) -> Any:
    """workbench_window as the agent calls it."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{server['port']}/workbench/window",
        data=json.dumps({"command": command, "args": args, "page": "scripts"}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {server['token']}",
            "Content-Type": "application/json",
            "X-Actor": "agent",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (127.0.0.1)
        return json.loads(response.read())["result"]


def test_two_comments_are_sent_in_one_go_and_the_file_is_untouched(
    browser: Browser, server: dict[str, Any]
) -> None:
    made = script(server, "made_up_review")
    before = made.read_bytes()
    call(server, "GET", "/agent/inbox?take=1")  # nothing of an earlier test waits
    page = open_script(browser, server, made)
    expect(page.locator(".review-panel")).to_have_count(0)  # no comments: no bar

    # Drag over two lines, right-click, Comment…, type.
    comment_by_menu(page, "for row in rows:", "total += row", "Use sum() here.")
    expect(page.locator(".wb-tab.active .wb-tab-comments")).to_have_text("1")
    expect(page.locator(".review-count")).to_have_text("1 annotation")
    expect(page.locator(".review-where")).to_have_text("lines 6-7")
    expect(page.locator(".wb-script-editor .sab-comment").first).to_be_visible()  # the range, highlighted
    expect(page.locator(".wb-script-editor .sab-comment-mark").first).to_be_visible()  # its gutter mark

    # A second one with nothing selected covers the cursor's line (Ctrl+Alt+M).
    at = line(page, "import os")
    page.mouse.click(at["x"] + 20, at["y"] + at["height"] / 2)
    page.keyboard.press("Control+Alt+m")
    box = page.locator(".review-box")
    expect(box.locator(".review-box-head")).to_contain_text("Line 2")
    box.locator("textarea").fill("Is this import used?")
    box.locator("textarea").press("Control+Enter")
    expect(page.locator(".wb-tab.active .wb-tab-comments")).to_have_text("2")
    expect(page.locator(".wb-tab.active .wb-tab-comments")).to_have_attribute("aria-label", "2 annotations")
    expect(page.locator(".review-where")).to_have_text(["line 2", "lines 6-7"])  # in the file's order
    expect(page.locator(".review-words")).to_have_text(["Is this import used?", "Use sum() here."])

    # Hovering the commented code shows the comment.
    hovered = line(page, "for row in rows:")
    page.mouse.move(hovered["x"] + 40, hovered["y"] + hovered["height"] / 2)
    expect(page.locator(".monaco-hover-content").first).to_contain_text("Annotation")
    expect(page.locator(".monaco-hover-content").first).to_contain_text("Use sum")

    # A click in the list goes to its lines; Edit opens its words again.
    page.locator(".review-go").nth(1).click()
    page.locator(".review-edit").nth(1).click()
    expect(box.locator("textarea")).to_have_value("Use sum() here.")
    box.locator("textarea").fill("Use sum(rows) here.")
    box.get_by_role("button", name="Save").click()
    expect(page.locator(".review-words").nth(1)).to_have_text("Use sum(rows) here.")

    # The screen state says how many wait on the tab, never what they say.
    def counted() -> bool:
        windows = call(server, "GET", "/screen/scripts")
        return '"comments": 2' in json.dumps(windows) and "Use sum" not in json.dumps(windows)

    page.wait_for_function("() => true")
    for _ in range(40):
        if counted():
            break
        page.wait_for_timeout(250)
    assert counted()

    # The agent reads the comments that wait; it cannot send them.
    waiting = agent(server, "comments", {})
    assert [(c["where"], c["comment"], c["by"]) for c in waiting["comments"]] == [
        ("line 2", "Is this import used?", "user"),
        ("lines 6-7", "Use sum(rows) here.", "user"),
    ]
    with pytest.raises(urllib.error.HTTPError) as refused:
        agent(server, "review.send", {})
    assert "Only the user sends annotations" in refused.value.read().decode()

    # Save (Ctrl+S) writes no comment: the file is as it was.
    page.locator(".wb-script-editor .view-lines").click()
    page.keyboard.press("Control+s")
    page.wait_for_timeout(600)
    assert made.read_bytes() == before

    # A send that fails keeps every comment and says why.
    page.route("**/agent/inbox/review", lambda route: route.fulfill(status=500, json={"error": "It broke."}))
    page.get_by_role("button", name="Send to agent").click()
    expect(page.locator(".review-error")).to_contain_text("Not sent: It broke. The annotations are kept.")
    expect(page.locator(".review-item")).to_have_count(2)
    expect(page.locator(".wb-tab.active .wb-tab-comments")).to_have_text("2")
    assert call(server, "GET", "/agent/inbox")["items"] == []
    page.unroute("**/agent/inbox/review")

    # Send to agent: both, as one message; then the editor holds no comment.
    page.get_by_role("button", name="Send to agent").click()
    expect(page.locator(".review-panel")).to_have_count(0)
    expect(page.locator(".wb-tab-comments")).to_have_count(0)
    expect(page.locator(".wb-script-editor .sab-comment")).to_have_count(0)
    expect(page.locator(".wb-script-editor .sab-comment-mark")).to_have_count(0)
    expect(page.locator(".note-corner")).to_contain_text("Sent 2 annotations to the agent")

    items = call(server, "GET", "/agent/inbox?take=1")["items"]  # what agent_inbox reads
    assert len(items) == 1 and items[0]["kind"] == "review"
    text = items[0]["text"]
    assert items[0]["title"] == f"Annotations on {made} (2)"
    assert text.startswith(f"Annotations on {made}: 2 annotations.")
    first, second = text.index("1. line 2\n"), text.index("2. lines 6-7\n")
    assert first < text.index("import os") < text.index("Annotation: Is this import used?") < second
    code = text.index("for row in rows:\n    total += row")
    assert second < code < text.index("Annotation: Use sum(rows) here.")

    # The file on disk is byte for byte what it was.
    assert made.read_bytes() == before
    assert agent(server, "comments", {})["comments"] == []
    page.close()


def test_comments_follow_edits_and_a_tab_asks_before_it_throws_them_away(
    browser: Browser, server: dict[str, Any]
) -> None:
    made = script(server, "made_up_review_edits")
    page = open_script(browser, server, made)
    comment_by_menu(page, "for row in rows:", "total += row", "Use sum() here.")
    expect(page.locator(".review-where")).to_have_text("lines 6-7")

    # Two lines typed at the top: the comment moves with its code.
    top = line(page, "Made-up totals")
    page.mouse.click(top["x"] + 2, top["y"] + top["height"] / 2)
    page.keyboard.press("Control+Home")
    page.keyboard.type("# one\n# two\n")
    expect(page.locator(".review-where")).to_have_text("lines 8-9")

    # The agent leaves a note of its own on a line: marked as the agent's, and it takes it back.
    noted = agent(server, "comments.add", {"line": 4, "comment": "This import is not used."})
    expect(page.locator(".review-item.by-agent .review-words")).to_have_text("This import is not used.")
    expect(page.locator(".wb-tab.active .wb-tab-comments")).to_have_text("2")
    expect(page.locator(".wb-script-editor .sab-comment-agent").first).to_be_visible()
    theirs = next(c for c in noted["comments"] if c["by"] == "user")
    with pytest.raises(urllib.error.HTTPError):
        agent(server, "comments.remove", {"id": theirs["id"]})  # the user's comment is the user's
    agent(server, "comments.remove", {"id": noted["made"]})
    expect(page.locator(".review-item")).to_have_count(1)

    # Closing the tab asks first: the comments live only on this page.
    page.locator(".wb-tab.active .tab-close").click()
    asked = page.locator(".dialog", has_text="1 annotation not yet sent to the agent")
    expect(asked).to_contain_text("changes that are not saved and")  # one question for both
    asked.get_by_role("button", name="Cancel").click()
    expect(page.locator(".review-item")).to_have_count(1)

    # Delete from the list: none left, the bar goes.
    page.locator(".review-delete").click()
    expect(page.locator(".review-panel")).to_have_count(0)
    expect(page.locator(".wb-script-editor .sab-comment")).to_have_count(0)
    assert made.read_bytes() == CODE.encode()  # never saved: what was typed and commented stayed on the page
    page.close()


def comment_by_key(page: Page, editor: str, words: str) -> None:
    """The cursor's line of an editor commented with Ctrl+Alt+M."""
    page.locator(f"{editor} .view-line").first.click()
    page.keyboard.press("Control+Alt+m")
    box = page.locator(".review-box")
    box.locator("textarea").fill(words)
    box.locator("textarea").press("Control+Enter")
    expect(box).to_have_count(0)


def test_every_editor_of_the_pages_takes_a_comment(browser: Browser, server: dict[str, Any]) -> None:
    """A .sql file, a Markdown file, a blade's IDE and a notebook's cell (its comment names its cell)."""
    made = script(server, "made_up_review_kinds")
    call(server, "GET", "/agent/inbox?take=1")
    query = made.with_name("totals.sql")
    query.write_text("SELECT 1 AS made_up;\n", encoding="utf-8")
    notes = made.with_name("notes.md")
    notes.write_text("# Made-up notes\n", encoding="utf-8")

    page = open_page(browser, server, f"scripts?path={query}")
    expect(page.locator(".wb-sql .view-lines")).to_contain_text("made_up")
    comment_by_key(page, ".wb-sql", "Name the column.")
    expect(page.locator(".wb-tab.active .wb-tab-comments")).to_have_text("1")
    page.get_by_role("button", name="Send to agent").click()
    expect(page.locator(".wb-tab-comments")).to_have_count(0)
    page.close()

    # A Markdown file opens read; its Source view is the editor that takes an annotation.
    page = open_page(browser, server, f"scripts?path={notes}")
    page.click(".wb-view-source")
    expect(page.locator(".wb-text-source .view-lines")).to_contain_text("Made-up notes")
    comment_by_key(page, ".wb-text-source", "A better heading?")
    page.get_by_role("button", name="Send to agent").click()
    expect(page.locator(".wb-tab-comments")).to_have_count(0)

    # A blade's IDE.
    page.click(".wb-status button:has-text('Blades')")
    page.locator(".blades-pane button[aria-label='New blade']").click()
    dialog = page.locator(".dialog", has_text="New blade")
    dialog.locator("input[aria-label=Name]").fill("made_up_reviewed")
    dialog.locator("button:has-text('Create')").click()
    ide = page.locator(".blade-ide")
    expect(ide.locator(".ide-name")).to_have_text("made_up_reviewed")
    expect(ide.locator(".view-lines")).not_to_be_empty()
    comment_by_key(page, ".blade-ide .ide-editor", "Why three rows?")
    expect(page.locator(".wb-tab.active .wb-tab-comments")).to_have_text("1")
    expect(ide.locator(".sab-comment-mark").first).to_be_visible()
    page.get_by_role("button", name="Send to agent").click()
    expect(page.locator(".wb-tab-comments")).to_have_count(0)
    call(server, "DELETE", "/blades/made_up_reviewed")
    page.close()

    # A notebook's code cell: the comment says which cell.
    path = str(server["tmp"] / "workbench" / "made_up_review.ipynb")
    cells = [
        {"kind": "code", "source": "rows = [1, 2]", "number": 1},
        {"kind": "code", "source": "total = sum(rows)\nprint(total)", "number": 2},
    ]
    call(server, "POST", "/workbench/save", {"path": path, "cells": cells, "next_cell": 3})
    page = open_page(browser, server, f"notebooks?path={path}")
    expect(page.locator(".wb-cell .view-lines").nth(1)).to_contain_text("total = sum(rows)")
    page.locator(".wb-cell").nth(1).locator(".view-line").first.click()
    page.keyboard.press("Control+Alt+m")
    box = page.locator(".review-box")
    box.locator("textarea").fill("Print it with a label.")
    box.locator("textarea").press("Control+Enter")
    expect(page.locator(".review-where")).to_have_text("cell 2, line 1")
    expect(page.locator(".wb-tab.active .wb-tab-comments")).to_have_text("1")
    page.get_by_role("button", name="Send to agent").click()
    expect(page.locator(".review-panel")).to_have_count(0)
    page.close()

    texts = [item["text"] for item in call(server, "GET", "/agent/inbox?take=1")["items"]]
    assert len(texts) == 4
    assert "totals.sql: 1 annotation." in texts[0] and "Annotation: Name the column." in texts[0]
    assert "notes.md: 1 annotation." in texts[1] and "# Made-up notes" in texts[1]
    assert "Annotations on made_up_reviewed: 1 annotation." in texts[2]
    assert "1. cell 2, line 1\n```\ntotal = sum(rows)\n```\nAnnotation: Print it with a label." in texts[3]
    assert query.read_text(encoding="utf-8") == "SELECT 1 AS made_up;\n"
    assert notes.read_text(encoding="utf-8") == "# Made-up notes\n"
