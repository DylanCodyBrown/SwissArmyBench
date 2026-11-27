"""A Markdown file as blocks (domain/markdown_blocks.py; the owner, 2026-11-27: "Our markdown reader and inline
editor would be a great addition"): the splitting (front matter, fenced code holding blank lines, nested
lists, tables), and an edit written back into only its block's characters (byte for byte outside it, the
file's CRLF kept), a task box ticked by one character."""

from __future__ import annotations

import pytest

from swissarmybench.domain import markdown_blocks as rules

DOC = (
    "---\n"
    "title: A made-up plan\n"
    "---\n"
    "\n"
    "# Plan\n"
    "\n"
    "The first paragraph\n"
    "runs over two lines.\n"
    "\n"
    "- Load the orders\n"
    "  - from the warehouse\n"
    "  - from the files\n"
    "\n"
    "  A line that belongs to the first item.\n"
    "- [ ] Check the totals\n"
    "- [x] Write it down\n"
    "\n"
    "```python\n"
    "x = 1\n"
    "\n"
    "# a comment, not a heading\n"
    "y = 2\n"
    "```\n"
    "\n"
    "| Region | Sales |\n"
    "|---|---:|\n"
    "| North | 10 |\n"
    "| South | 20 |\n"
    "\n"
    "> A quote\n"
    "> over two lines\n"
    "\n"
    "---\n"
    "\n"
    "```mermaid\n"
    "flowchart TD\n"
    "    a --> b\n"
    "```\n"
    "The last line, with no blank line before it.\n"
)


def kinds(text: str) -> list[str]:
    return [b.kind for b in rules.blocks(text)]


def test_the_blocks_of_a_document_in_order() -> None:
    found = rules.blocks(DOC)
    assert [b.kind for b in found] == [
        "front_matter",
        "heading",
        "paragraph",
        "list",
        "code",
        "table",
        "quote",
        "rule",
        "diagram",
        "paragraph",
    ]
    assert [b.index for b in found] == list(range(len(found)))
    # Each block's text is exactly its characters of the file, and no two overlap.
    for block in found:
        assert DOC[block.start : block.end] == block.text
    assert all(a.end <= b.start for a, b in zip(found, found[1:], strict=False))
    front, heading, paragraph, items, code, table = found[:6]
    assert front.text == "---\ntitle: A made-up plan\n---" and front.line == 1 and front.lines == 3
    assert heading.text == "# Plan" and heading.line == 5
    assert paragraph.text == "The first paragraph\nruns over two lines."
    # A nested list with a blank line and an indented line inside is one block; its task boxes counted.
    assert items.text.startswith("- Load the orders\n  - from the warehouse")
    assert items.text.endswith("- [x] Write it down") and items.tasks == 2 and items.lines == 7
    # Fenced code keeps its blank line and its "#" line: one block, its language said.
    assert code.language == "python" and "\n\n# a comment, not a heading\n" in code.text
    assert table.text.count("\n") == 3
    assert found[8].language == "mermaid"


def test_front_matter_is_only_at_the_very_top_and_needs_its_end() -> None:
    assert kinds("---\ntitle: x\n---\n\nText\n") == ["front_matter", "paragraph"]
    assert kinds("Text\n\n---\ntitle: x\n---\n") == ["paragraph", "rule", "paragraph", "rule"]
    assert kinds("---\nnever closed\n") == ["rule", "paragraph"]


def test_a_fence_not_closed_takes_the_rest_and_a_longer_fence_holds_a_shorter() -> None:
    assert kinds("```\ncode\n\n# still code\n") == ["code"]
    nested = "````md\n```python\nx\n```\n````\n\nafter\n"
    found = rules.blocks(nested)
    assert [b.kind for b in found] == ["code", "paragraph"] and found[0].lines == 5
    assert kinds("~~~\na\n~~~\nb\n") == ["code", "paragraph"]


def test_an_edit_changes_only_its_blocks_characters() -> None:
    found = rules.blocks(DOC)
    paragraph = found[2]
    after = rules.replace(DOC, 2, "One new line.")
    assert after == DOC[: paragraph.start] + "One new line." + DOC[paragraph.end :]
    assert after[: paragraph.start] == DOC[: paragraph.start]
    assert after.endswith(DOC[paragraph.end :])
    # The same text written back changes nothing at all.
    for block in found:
        assert rules.replace(DOC, block.index, block.text) == DOC
    # What is typed with a trailing new line is the block all the same.
    assert rules.replace(DOC, 1, "# Plan\n") == DOC


def test_crlf_is_kept_and_what_is_typed_takes_the_files_line_ends() -> None:
    text = DOC.replace("\n", "\r\n")
    found = rules.blocks(text)
    assert [b.kind for b in found] == kinds(DOC)
    assert rules.line_end(text) == "\r\n" and rules.line_end(DOC) == "\n"
    paragraph = found[2]
    after = rules.replace(text, 2, "Two new\nlines.")
    assert after == text[: paragraph.start] + "Two new\r\nlines." + text[paragraph.end :]
    assert "\n" not in after.replace("\r\n", "")  # never a lone line feed
    assert rules.replace(text, 4, found[4].text.replace("\r\n", "\n")) == text  # a textarea's own \n


def test_an_emptied_block_goes_with_the_blank_line_after_it() -> None:
    text = "# A\n\nGone soon.\n\nStays.\n"
    assert rules.replace(text, 1, "  ") == "# A\n\nStays.\n"
    assert rules.replace("only\n", 0, "") == ""


def test_a_new_block_goes_after_another_with_a_blank_line_between() -> None:
    text = "# A\n\nFirst.\n"
    assert rules.insert_after(text, 0, "Added.") == "# A\n\nAdded.\n\nFirst.\n"
    assert rules.insert_after(text, 1, "Last.") == "# A\n\nFirst.\n\nLast.\n"
    assert rules.insert_after(text, -1, "Top.") == "Top.\n\n# A\n\nFirst.\n"
    assert rules.insert_after("# A\r\n", 0, "x\ny") == "# A\r\n\r\nx\r\ny\r\n"


def test_a_task_box_is_ticked_by_one_character() -> None:
    items = rules.blocks(DOC)[3]
    ticked = rules.tick(DOC, 3, 0)
    assert len(ticked) == len(DOC)
    changed = [i for i, (a, b) in enumerate(zip(DOC, ticked, strict=True)) if a != b]
    assert len(changed) == 1 and DOC[changed[0]] == " " and ticked[changed[0]] == "x"
    assert items.start < changed[0] < items.end
    assert rules.tick(ticked, 3, 0) == DOC  # switched back
    assert rules.tick(DOC, 3, 1, done=True) == DOC  # ticked already
    assert "- [ ] Write it down" in rules.tick(DOC, 3, 1, done=False)
    for bad in (2, -1, True, "0"):
        with pytest.raises(rules.BlockError):
            rules.tick(DOC, 3, bad)
    with pytest.raises(rules.BlockError, match="no task boxes"):
        rules.tick(DOC, 2, 0)


def test_a_block_that_is_not_there_is_said_in_one_sentence() -> None:
    with pytest.raises(rules.BlockError, match="0 to 9"):
        rules.replace(DOC, 10, "x")
    with pytest.raises(rules.BlockError):
        rules.replace(DOC, "1", "x")
    with pytest.raises(rules.BlockError, match="no blocks"):
        rules.replace("\n\n", 0, "x")
    with pytest.raises(rules.BlockError):
        rules.replace(DOC, 1, None)


def test_the_title_is_the_first_headings_words() -> None:
    assert rules.title(DOC) == "Plan"
    assert rules.title("Text\n\n## Second level ##\n") == "Second level"
    assert rules.title("```\n# not a heading\n```\n") == ""


def test_tables_lists_and_paragraphs_end_where_the_next_block_starts() -> None:
    assert kinds("text\n# Heading\nmore\n") == ["paragraph", "heading", "paragraph"]
    assert kinds("| a | b |\n|---|---|\n| 1 | 2 |\nnot a row\n") == ["table", "paragraph"]
    assert kinds("a | b\nplain\n") == ["paragraph"]  # no rule row: not a table
    assert kinds("1. one\n2. two\n\nafter\n") == ["list", "paragraph"]
    assert kinds("- one\n\n- two\n") == ["list"]  # a loose list is one list
    assert kinds("- one\ntext right after\n# H\n") == ["list", "heading"]
