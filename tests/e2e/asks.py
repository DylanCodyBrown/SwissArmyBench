"""The app's own questions in a browser test (web/src/dom.ts askYesNo, askText: a dialog of class `ask`,
never the browser's confirm() or prompt()). A test that used to accept the browser's dialogs says how these
are answered: accept_asks(page) says yes to each as it appears (typing an answer where one is asked for);
without it a question stays open, as it does for a person."""

from __future__ import annotations

from collections.abc import Callable

from playwright.sync_api import Locator, Page


def accept_asks(
    page: Page,
    text: str | Callable[[str], str | None] | None = None,
    heard: list[str] | None = None,
) -> None:
    """Every question the page asks from now on is answered yes. `text`: what is typed when it asks for a
    line (a string, or a function of the question's words; None: what the box already holds). `heard`: each
    question's words, as they were asked."""
    dialog = page.locator("dialog.ask[open]")

    def answer(asked: Locator) -> None:
        words = asked.get_attribute("data-question") or ""
        if heard is not None:
            heard.append(words)
        box = asked.locator("input.ask-text")
        if box.count():
            typed = text(words) if callable(text) else text
            if typed is not None:
                box.fill(typed)
        asked.locator("button.ask-ok").click()

    page.add_locator_handler(dialog, answer)


def answer_ask(page: Page, text: str | None = None, yes: bool = True) -> str:
    """The one question open now, answered (yes, or Cancel); its words."""
    asked = page.locator("dialog.ask[open]")
    asked.wait_for(timeout=15000)
    words = asked.get_attribute("data-question") or ""
    if text is not None:
        asked.locator("input.ask-text").fill(text)
    asked.locator("button.ask-ok" if yes else "button.ask-cancel").click()
    return words
