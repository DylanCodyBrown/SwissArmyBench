"""The Blazor front end's structure, checked from its source (blazor/SwissArmyBench.Web; no .NET needed):

- one state pattern: every state service (State/) has its value and one `Changed` event (LiveUpdates also
  raises each notice as `NoticeArrived`), and every component or service that subscribes to an event
  unsubscribes in its Dispose (IDisposable or IAsyncDisposable);
- size limits from day one: no C# method over 80 lines, no .razor or .cs file over 400 lines, no page's
  code-behind over 300 lines. TOO_BIG lists what is over today; it only shrinks (as tests/test_architecture.py
  does for the Python).
"""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "blazor" / "SwissArmyBench.Web"
METHOD_LINES = 80
FILE_LINES = 400
PAGE_CODE_LINES = 300

# Over a limit today, with its size then: it may shrink, never grow, and leaves the list once it fits.
TOO_BIG: dict[str, int] = {}

EVENTS = ("Changed", "NoticeArrived", "LocationChanged")
SUBSCRIBE = re.compile(r"([\w.]+\.(?:" + "|".join(EVENTS) + r"))\s*\+=\s*([\w.]+)")
METHOD = re.compile(
    r"^    (?:public|private|protected|internal)[^=;]*\b(\w+)\s*\([^;]*$"  # a member's head that opens a body
)


def sources() -> list[Path]:
    return sorted(
        p
        for p in WEB.rglob("*")
        if p.suffix in (".cs", ".razor")
        and "obj" not in p.parts
        and "bin" not in p.parts
        and "Generated" not in p.parts
    )


def component_text(path: Path) -> str:
    """A component's whole source: its .razor and its .razor.cs (and a page's other partial parts)."""
    stem = path.name.split(".")[0]
    parts = [p for p in path.parent.glob(f"{stem}.*") if p.suffix in (".razor", ".cs")]
    return "\n".join(p.read_text(encoding="utf-8") for p in parts)


def test_every_subscription_is_undone_on_dispose() -> None:
    problems = []
    for path in sources():
        text = path.read_text(encoding="utf-8")
        whole = component_text(path)
        for source, handler in SUBSCRIBE.findall(text):
            if f"{source} -= {handler}" not in whole:
                problems.append(f"{path.relative_to(WEB)}: {source} += {handler} is never undone (-=)")
            if not re.search(r"@implements I(?:Async)?Disposable|:\s*[^{]*\bI(?:Async)?Disposable\b", whole):
                problems.append(f"{path.relative_to(WEB)}: subscribes to {source} but is not disposable")
    assert not problems, "\n".join(problems)


def test_every_state_service_has_one_changed_event() -> None:
    problems = []
    for path in sorted((WEB / "State").glob("*.cs")):
        text = path.read_text(encoding="utf-8")
        if not re.search(r"public sealed class \w+", text):
            continue  # a record (Notice, Note, Question): a value, not a service
        events = re.findall(r"public event [\w<>?]+ (\w+);", text)
        extra = [
            e for e in events if e != "Changed" and not (path.stem == "LiveUpdates" and e == "NoticeArrived")
        ]
        if "Changed" not in events or extra:
            problems.append(f"State/{path.name}: events {events}; a state service raises one Changed")
    assert not problems, "\n".join(problems)


def method_sizes(text: str) -> list[tuple[str, int]]:
    """Each method or property body's name and length in lines (its head to its closing brace)."""
    lines = text.splitlines()
    sizes = []
    for at, line in enumerate(lines):
        found = METHOD.match(line)
        if not found or line.rstrip().endswith(";"):
            continue
        end = next((i for i in range(at + 1, len(lines)) if lines[i] == "    }"), None)
        if end is not None and all(not METHOD.match(lines[i]) for i in range(at + 1, end)):
            sizes.append((found.group(1), end - at + 1))
    return sizes


def sizes_over() -> dict[str, int]:
    over: dict[str, int] = {}
    for path in sources():
        text = path.read_text(encoding="utf-8")
        name = str(path.relative_to(WEB))
        count = len(text.splitlines())
        if count > FILE_LINES:
            over[name] = count
        is_page = (
            "Pages" in path.parts
            and path.name.endswith(".razor.cs")
            and (path.with_suffix("").with_suffix(".razor")).is_file()
        )
        if is_page and "@page" in path.with_suffix("").with_suffix(".razor").read_text(encoding="utf-8"):
            if count > PAGE_CODE_LINES:
                over[f"{name} (page code-behind)"] = count
        for method, length in method_sizes(text):
            if length > METHOD_LINES:
                over[f"{name}:{method}"] = length
    return over


def test_sizes_stay_within_the_limits() -> None:
    over = sizes_over()
    grown = {k: v for k, v in over.items() if v > TOO_BIG.get(k, 0)}
    assert not grown, (
        f"Over the limits (methods {METHOD_LINES}, files {FILE_LINES}, page code {PAGE_CODE_LINES}): {grown}"
    )
    fitted = sorted(set(TOO_BIG) - set(over))
    assert not fitted, f"These fit now: take them out of TOO_BIG: {fitted}"


def test_wide_records_list_one_parameter_a_line() -> None:
    """A record of the server's answers reads as a list (the owner reads this code): a positional record whose
    one line would pass 118 characters puts each parameter on a line of its own."""
    wide = [
        f"{path.relative_to(WEB)}:{number}"
        for path in sources()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if line.startswith("public sealed record ")
        and "(" in line
        and line.rstrip().endswith((");", ")"))
        and len(line) > 118
    ]
    assert not wide, wide


def test_the_browsers_tab_wears_the_apps_icon() -> None:
    """A page in a browser had no icon: the browser asked the server for /favicon.ico on every first load
    (a 401, then a 404, in its console). index.html names the app's own mark, the launcher's icon as a PNG."""
    from swissarmybench.domain import desktop

    assert '<link rel="icon" type="image/png" href="favicon.png" />' in (
        WEB / "wwwroot" / "index.html"
    ).read_text(encoding="utf-8")
    assert (WEB / "wwwroot" / "favicon.png").read_bytes() == desktop.icon_png(64)
