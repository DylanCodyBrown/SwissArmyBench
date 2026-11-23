"""The Workbench's code zoom, its pure part (web/src/workbenchView.ts: the size kept between 8 and 40 px, a
step of 1 px and of 2 px from 20 px on, which keys ask for what), run by Node as the page runs it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.web_unit import bundled, needs_node

pytestmark = needs_node


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return bundled(tmp_path_factory.mktemp("workbench-view"), "workbenchView.ts")


def test_a_size_stays_between_8_and_40_whole_pixels(run: Any) -> None:
    sizes = [13, 7, 8, 40, 41, 400, -3, 13.4, 13.5, 0]
    assert run(*[["clampFont", px] for px in sizes]) == [13, 8, 8, 40, 40, 40, 8, 13, 14, 8]


def test_a_step_is_one_pixel_and_two_from_twenty_on(run: Any) -> None:
    asked = [(13, 1), (13, -1), (19, 1), (20, 1), (20, -1), (22, -1), (39, 1), (40, 1), (8, -1), (9, -1)]
    assert run(*[["steppedFont", now, by] for now, by in asked]) == [14, 12, 20, 22, 18, 20, 40, 40, 8, 8]
    # Up and back down lands where it began, below 20 and well above it.
    for start in (10, 13, 24, 30):
        up = run(["steppedFont", start, 1])[0]
        assert run(["steppedFont", up, -1])[0] == start


def test_the_zoom_keys(run: Any) -> None:
    keys = ["=", "+", "-", "0", "1", "a", "Enter"]
    assert run(*[["zoomKey", key] for key in keys]) == [1, 1, -1, 0, None, None, None]


def test_the_page_file_lost_the_parts_that_moved() -> None:
    """workbenchPage.ts is split along its own headings (the craft review of 2026-11-22): the command list,
    the code zoom and full screen, the file-changed watcher, the restore, the bars, the status bar, the tabs
    beside the code, the side panes, the tables' owners, the modes' panels and the exports each a module of
    their own."""
    source = Path(__file__).resolve().parents[1] / "web" / "src"
    page = (source / "workbenchPage.ts").read_text(encoding="utf-8")
    assert len(page.splitlines()) < 2000
    for name, mark in (
        ("workbenchCommandList.ts", 'id: "file.newNotebook"'),
        ("workbenchView.ts", "wb-fullscreen:"),
        ("workbenchFileChanged.ts", "Changed elsewhere."),
        ("workbenchRestore.ts", "workbench-documents:"),
        ("workbenchBars.ts", '"Workbench menu"'),
        ("workbenchStatusBar.ts", "wb-status-kernel"),
        ("workbenchFileTabs.ts", "/scripts/library-file"),
        ("workbenchSides.ts", "/scripts/fine-tune"),
        ("workbenchTableOwners.ts", "wb-tables-tool"),
        ("workbenchDocPanels.ts", "wb-mode-toggles"),
        ("workbenchExport.ts", "/workbench/export-script"),
    ):
        assert mark in (source / name).read_text(encoding="utf-8"), name
        assert mark not in page, name
