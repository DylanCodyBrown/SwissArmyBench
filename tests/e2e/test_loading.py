# ruff: noqa: F811, E501, S603
"""The one loading state (web/src/loading.ts, the owner 2026-11-18: "a uniform loading form ... they don't
gate the thing that is loading"), on its own in a real browser: the module bundled by esbuild into a bare
page with grid.css, no server. busy() covers exactly its element's box, makes it inert and aria-busy, shows
nothing for quick work, cancels through an AbortController, shows an error where the work was; loadingBlock()
holds its place; busyButton() refuses a second click."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
ESBUILD = WEB / "node_modules" / ".bin" / "esbuild"


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> str:
    if not ESBUILD.exists() and not shutil.which("esbuild"):
        pytest.skip("esbuild is not installed (npm install in web/)")
    folder = tmp_path_factory.mktemp("loading")
    out = folder / "loading.js"
    entry = folder / "entry.ts"
    source = (WEB / "src").as_posix()
    entry.write_text(
        f'export * from "{source}/loading";\n'
        f'export {{ errorNote as errorNoteFor, warningNote as warningNoteFor }} from "{source}/errorNote";\n',
        encoding="utf-8",
    )
    subprocess.run(
        [str(ESBUILD), str(entry), "--bundle", "--format=iife", "--global-name=L", f"--outfile={out}"],
        cwd=WEB,
        check=True,
        capture_output=True,
    )
    return out.read_text(encoding="utf-8")


def page_with(browser: Browser, bundle: str, theme: str = "light") -> Page:
    page = browser.new_page(viewport={"width": 700, "height": 500})
    css = (WEB / "static" / "grid.css").read_text(encoding="utf-8")
    page.set_content(
        f"""<!doctype html><html data-theme="{theme}"><head><style>{css}</style></head><body>
        <div style="padding:40px; display:block">
          <section id="card" style="width:300px; height:160px; border:1px solid; margin-top:20px">
            <button id="inside" type="button">Inside</button>
          </section>
          <div id="empty"></div>
          <button id="go" class="btn" type="button"><span class="btn-label">Test</span></button>
        </div></body></html>"""
    )
    page.add_script_tag(content=bundle)
    page.evaluate(
        """() => {
          window.clicks = 0;
          document.querySelector('#inside').addEventListener('click', () => window.clicks++);
          window.later = () => { let release, fail; const p = new Promise((a, b) => { release = a; fail = b; });
            return { p, release, fail }; };
        }"""
    )
    return page


def test_busy_covers_the_box_and_gates_it(browser: Browser, bundle: str) -> None:
    page = page_with(browser, bundle)
    page.evaluate(
        """() => { window.w = later(); window.run = L.busy(document.querySelector('#card'),
             "Loading Finance Captive's tables…", w.p); }"""
    )
    card = page.locator("#card")
    # At once, before anything is drawn: inert and busy, so a click lands nowhere.
    expect(card).to_have_attribute("aria-busy", "true")
    assert page.evaluate("document.querySelector('#card').inert") is True
    cover = page.locator(".busy-cover")
    expect(cover).to_be_visible()
    expect(cover).to_contain_text("Loading Finance Captive's tables…")
    box, over = card.bounding_box(), cover.bounding_box()
    assert box and over
    for key in ("x", "y", "width", "height"):
        assert abs(box[key] - over[key]) < 1.5, (key, box, over)
    # The words are the body's size, not a hint's.
    size = page.evaluate("getComputedStyle(document.querySelector('.busy-words')).fontSize")
    assert size == page.evaluate("getComputedStyle(document.body).fontSize")
    page.locator("#inside").click(force=True)
    assert page.evaluate("window.clicks") == 0
    # A second start while busy is the same work, not another.
    assert page.evaluate("L.isBusy(document.querySelector('#card'))") is True
    page.evaluate("() => w.release(7)")
    assert page.evaluate("window.run") == 7
    expect(cover).to_have_count(0)
    expect(card).not_to_have_attribute("aria-busy", "true")
    page.locator("#inside").click()
    assert page.evaluate("window.clicks") == 1
    page.close()


def test_quick_work_shows_no_cover(browser: Browser, bundle: str) -> None:
    page = page_with(browser, bundle)
    page.evaluate(
        """() => { window.seen = false;
             const watch = new MutationObserver(() => { if (document.querySelector('.busy-cover')) seen = true; });
             watch.observe(document.body, { childList: true, subtree: true });
             return L.busy(document.querySelector('#card'), 'Loading…', new Promise((r) => setTimeout(r, 40))); }"""
    )
    page.wait_for_timeout(250)
    assert page.evaluate("window.seen") is False
    page.close()


def test_slow_work_shows_the_time_taken(browser: Browser, bundle: str) -> None:
    page = page_with(browser, bundle)
    page.evaluate("() => { window.w = later(); L.busy(document.querySelector('#card'), 'Reading…', w.p); }")
    elapsed = page.locator(".busy-cover .busy-elapsed")
    expect(elapsed).to_be_hidden()
    expect(elapsed).to_have_text("3 s", timeout=5000)
    page.evaluate("() => w.release()")
    page.close()


def test_cancel_aborts_and_shows_no_error(browser: Browser, bundle: str) -> None:
    page = page_with(browser, bundle)
    page.evaluate(
        """() => { window.abort = new AbortController(); window.cancelled = 0;
             window.outcome = L.busy(document.querySelector('#card'), 'Connecting to Warehouse…',
               (signal) => new Promise((_, fail) => signal.addEventListener('abort',
                 () => fail(new DOMException('stopped', 'AbortError')))),
               { abort, onCancel: () => cancelled++ }).then(() => 'done', (e) => e.name); }"""
    )
    page.get_by_role("button", name="Cancel").click()
    assert page.evaluate("window.outcome") == "AbortError"
    assert page.evaluate("[abort.signal.aborted, cancelled]") == [True, 1]
    expect(page.locator(".busy-cover")).to_have_count(0)
    expect(page.locator(".busy-error")).to_have_count(0)
    page.close()


def test_an_error_shows_in_place(browser: Browser, bundle: str) -> None:
    page = page_with(browser, bundle)
    page.evaluate(
        """() => { window.w = later(); window.outcome = L.busy(document.querySelector('#card'), 'Loading…', w.p)
             .catch((e) => e.message); }"""
    )
    page.evaluate("() => w.fail(new Error('The database said no'))")
    assert page.evaluate("window.outcome") == "The database said no"
    # The one error component (errorNote.ts, 9.5), at the top of the gated part.
    note = page.locator("#card > .error-note")
    expect(note).to_have_attribute("role", "alert")
    expect(note.locator(".error-note-word")).to_have_text("Error")
    expect(note.locator(".error-note-what")).to_have_text("The database said no")
    expect(note.get_by_role("button", name="Send to the agent")).to_be_visible()
    # A retry clears it (it never lingers), and a second failure is one note, not two.
    page.evaluate(
        """() => { window.w = later(); window.outcome = L.busy(document.querySelector('#card'), 'Loading…', w.p)
             .catch((e) => e.message); }"""
    )
    expect(note).to_have_count(0)
    page.evaluate("() => w.fail(new Error('Still no'))")
    expect(note).to_have_count(1)
    note.get_by_role("button", name="Close").click()
    expect(note).to_have_count(0)
    page.close()


def test_error_note_parts(browser: Browser, bundle: str) -> None:
    """errorNote's parts in their order: the word, what happened, where, the fixes, Details with Copy, Send to
    the agent; the server's JSON refusal read; a warning in its own colour without Send to the agent."""
    page = page_with(browser, bundle)
    page.evaluate(
        """() => { window.tried = 0; document.querySelector('#empty').append(L.errorNoteFor(
             new Error(JSON.stringify({ error: 'Warehouse did not answer.\\nTimeout after 30 s at sales.orders',
                                        where: 'Warehouse · sales.orders' })),
             { fixes: [{ label: 'Try again', run: () => tried++ }] })); }"""
    )
    note = page.locator("#empty .error-note")
    expect(note.locator(".error-note-what")).to_have_text("Warehouse did not answer.")
    expect(note.locator(".error-note-where")).to_have_text("Warehouse · sales.orders")
    note.get_by_role("button", name="Try again").click()
    assert page.evaluate("window.tried") == 1
    details = note.locator("details.error-note-details")
    expect(details.locator("pre")).to_be_hidden()
    details.locator("summary").click()
    expect(details.locator("pre")).to_contain_text("Timeout after 30 s")
    expect(details.get_by_role("button", name="Copy")).to_be_visible()
    color = page.evaluate("getComputedStyle(document.querySelector('#empty .error-note-word')).color")
    assert color == "rgb(163, 20, 31)"  # --error, light
    page.evaluate(
        """() => document.querySelector('#empty').replaceChildren(L.warningNoteFor({ what: 'Only works on your machine.' }))"""
    )
    warning = page.locator("#empty .error-note.warning")
    expect(warning.locator(".error-note-word")).to_have_text("Warning")
    expect(warning.get_by_role("button", name="Send to the agent")).to_have_count(0)
    page.close()


def test_loading_block_keeps_its_place(browser: Browser, bundle: str) -> None:
    page = page_with(browser, bundle)
    page.evaluate(
        "() => document.querySelector('#empty').append(L.loadingBlock('Loading the catalog…', { height: '200px' }))"
    )
    block = page.locator("#empty .loading-block")
    box = block.bounding_box()
    assert box and box["height"] >= 199
    expect(block).to_have_attribute("role", "progressbar")
    expect(block).to_have_attribute("data-shown", "")
    expect(block.locator(".busy-words")).to_be_visible()
    expect(block).to_contain_text("Loading the catalog…")
    page.close()


def test_busy_button_refuses_a_second_click(browser: Browser, bundle: str) -> None:
    page = page_with(browser, bundle)
    page.evaluate(
        """() => { window.starts = 0; window.w = later(); const go = document.querySelector('#go');
             go.addEventListener('click', () => { starts++; L.busyButton(go, w.p, 'Testing…'); }); }"""
    )
    go = page.locator("#go")
    go.click()
    expect(go).to_be_disabled()
    expect(go).to_have_text("Testing…")
    expect(go.locator(".busy-spinner")).to_have_count(1)
    go.dispatch_event("click")
    go.focus()
    page.keyboard.press("Enter")
    assert page.evaluate("window.starts") == 1
    page.evaluate("() => w.release()")
    expect(go).to_be_enabled()
    expect(go).to_have_text("Test")
    expect(go.locator(".busy-spinner")).to_have_count(0)
    page.close()


def test_dark_theme_tokens(browser: Browser, bundle: str) -> None:
    page = page_with(browser, bundle, theme="dark")
    page.evaluate("() => { window.w = later(); L.busy(document.querySelector('#card'), 'Loading…', w.p); }")
    expect(page.locator(".busy-cover")).to_be_visible()
    background = page.evaluate("getComputedStyle(document.querySelector('.busy-cover')).backgroundColor")
    assert background == "rgba(18, 21, 24, 0.72)"
    page.evaluate("() => w.release()")
    page.close()
