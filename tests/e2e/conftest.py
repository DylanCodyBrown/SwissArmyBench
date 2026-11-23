"""Shared for the browser tests: each test leaves no project open behind it.

A project is a folder now (the owner, 2026-11-17), and opening one from the Workbench makes it THE open
project of the module's shared server: a test that opened one closes it (its unsaved changes let go), so
the next test's windows do not open its documents too."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from playwright.sync_api import (
    Browser,
    BrowserContext,
    ConsoleMessage,
    Page,
    Playwright,
    expect,
    sync_playwright,
)

E2E = Path(__file__).resolve().parent
# What a browser test waits for at most: an expect and a page's action alike. Playwright's own five
# seconds for an expect failed tests on a busy machine (a parallel run, other work) that pass alone.
# A page's load keeps Playwright's 30 s (a busy machine's first load of the page's scripts is slow).
WAIT_MS = 15_000
LOAD_MS = 30_000
expect.set_options(timeout=WAIT_MS)


@pytest.fixture(scope="module", autouse=True)
def classic_pages() -> Iterator[None]:
    """The classic pages' tests see the classic pages: Blazor is the default since the swap (the owner,
    2026-11-23), and the classic pages stay one release. Every server a module starts inherits it; the Blazor
    tests' own server sets it back (tests/e2e/blazor/conftest.py)."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("SWISSARMYBENCH_FRONTEND", "classic")
        yield


class _Shared:
    """The one browser of the run: started when a test first asks for it, stopped once the run leaves
    tests/e2e (Playwright's sync API holds an event loop on this thread, which asyncio.run in the other
    tests could not share), started again if the run comes back (a parallel worker's files are mixed)."""

    playwright: Playwright | None = None
    browser: Browser | None = None

    def get(self) -> Browser:
        if self.browser is None or not self.browser.is_connected():
            self.stop()
            from tests.e2e.test_ui import launch_browser

            self.playwright = sync_playwright().start()
            self.browser = launch_browser(self.playwright)
        return self.browser

    def close_contexts(self) -> None:
        if self.browser is not None and self.browser.is_connected():
            for context in list(self.browser.contexts):
                try:
                    context.close()
                except Exception:  # noqa: S110 (already gone with its page)
                    pass

    def stop(self) -> None:
        browser, playwright = self.browser, self.playwright
        self.browser = self.playwright = None
        try:
            if browser is not None:
                browser.close()
        finally:
            if playwright is not None:
                playwright.stop()


_SHARED = _Shared()

# AG Grid's errors in any page's console (a module the page did not register says "error #200"): every
# context and page the tests make is listened to, and no_ag_grid_errors fails the test that saw one
# (gridView.ts registers only the modules it uses).
AG_GRID_ERRORS: list[str] = []


def _ag_grid_error(message: ConsoleMessage) -> None:
    if message.type == "error" and "AG Grid" in message.text:
        AG_GRID_ERRORS.append(message.text)


class _BrowserHandle:
    """What the `browser` fixture hands out: the shared browser, whichever is running now, with each new
    context and page waiting WAIT_MS by default."""

    def new_context(self, **options: Any) -> BrowserContext:
        context = _SHARED.get().new_context(**options)
        context.on("console", _ag_grid_error)
        context.set_default_timeout(WAIT_MS)
        context.set_default_navigation_timeout(LOAD_MS)
        return context

    def new_page(self, **options: Any) -> Page:
        page = _SHARED.get().new_page(**options)
        page.context.on("console", _ag_grid_error)
        page.context.set_default_timeout(WAIT_MS)
        page.context.set_default_navigation_timeout(LOAD_MS)
        return page

    def __getattr__(self, name: str) -> Any:
        return getattr(_SHARED.get(), name)


@pytest.fixture(scope="session")
def shared_browser() -> Iterator[Browser]:
    yield cast(Browser, _BrowserHandle())
    _SHARED.stop()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> Iterator[None]:
    """After a module's last test (its own fixtures gone): its pages closed, as when each module had a
    browser of its own; and the browser stopped when the next test is not a browser test."""
    yield
    if nextitem is None or E2E not in nextitem.path.parents:
        _SHARED.stop()
    elif nextitem.path != item.path:
        _SHARED.close_contexts()


@pytest.fixture(autouse=True)
def no_ag_grid_errors() -> Iterator[None]:
    """AG Grid logged no error in any page of the test (a missing module is "AG Grid: error #200")."""
    AG_GRID_ERRORS.clear()
    yield
    seen = list(AG_GRID_ERRORS)
    AG_GRID_ERRORS.clear()
    assert not seen, f"AG Grid logged errors: {seen[:3]}"


@pytest.fixture(autouse=True)
def no_project_left_open(request: pytest.FixtureRequest) -> Iterator[None]:
    yield
    if "server" not in request.fixturenames:
        return
    from tests.e2e.test_ui import call

    server: dict[str, Any] = request.getfixturevalue("server")
    try:
        if call(server, "GET", "/project")["project"]:
            call(server, "POST", "/project/close", {"discard": True})
    except Exception:  # noqa: S110 (a server that stopped: nothing is open)
        pass
