"""Updates and the tray: versions compared as PEP 440 says, what the release lists hold, which release is
offered, the tray's menu as data, and the update's plan (the helper's steps and its command lines).

The check (services/updates.py) is the one request that leaves the computer, by the owner's call
(2026-11-16): PyPI's JSON for `swissarmybench`, falling back to GitHub's latest release. It sends
nothing but that request. A pre-release is offered only to someone already on one.

Standard library only, no I/O: the service fetches, the tray draws, the helper runs (server/updater.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PACKAGE: str = "swissarmybench"
REPOSITORY: str = "DylanCodyBrown/SwissArmyBench"
PYPI_URL: str = f"https://pypi.org/pypi/{PACKAGE}/json"
GITHUB_URL: str = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
FEEDS: tuple[str, ...] = (PYPI_URL, GITHUB_URL)
CHECK_EVERY_SECONDS: float = 6 * 3600

# The tray's menu lists at most this many tables and documents each; the rest is one "N more" item.
MENU_MAX_ITEMS: int = 12


class UpdateError(ValueError):
    """A release list that cannot be read, or a request for an update that cannot be done."""


# ===== versions (PEP 440) =====

_VERSION = re.compile(
    r"""^\s*v?
    (?:(?P<epoch>[0-9]+)!)?
    (?P<release>[0-9]+(?:\.[0-9]+)*)
    (?:[-_.]?(?P<pre_l>alpha|beta|preview|pre|rc|a|b|c)[-_.]?(?P<pre_n>[0-9]+)?)?
    (?:-(?P<post_n1>[0-9]+)|[-_.]?(?P<post_l>post|rev|r)[-_.]?(?P<post_n2>[0-9]+)?)?
    (?:[-_.]?(?P<dev_l>dev)[-_.]?(?P<dev_n>[0-9]+)?)?
    (?:\+(?P<local>[a-z0-9]+(?:[-_.][a-z0-9]+)*))?
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)
_PRE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}
_PRE_NAME = ("a", "b", "rc")


@dataclass(frozen=True, order=False)
class Version:
    """A version as PEP 440 orders it (the local part is kept for its text and ignored in comparing)."""

    epoch: int
    release: tuple[int, ...]
    pre: tuple[int, int] | None  # (0 a, 1 b, 2 rc; its number)
    post: int | None
    dev: int | None
    text: str = field(compare=False)

    @property
    def is_prerelease(self) -> bool:
        return self.pre is not None or self.dev is not None

    def _key(self) -> tuple[Any, ...]:
        release = list(self.release)
        while len(release) > 1 and release[-1] == 0:
            release.pop()
        # A dev release of a final (1.0.dev1) sorts before its pre-releases (1.0a1); a final after them.
        if self.pre is None and self.post is None and self.dev is not None:
            pre: tuple[int, int, int] = (-1, 0, 0)
        elif self.pre is None:
            pre = (1, 0, 0)
        else:
            pre = (0, *self.pre)
        post = -1 if self.post is None else self.post
        dev = (1, 0) if self.dev is None else (0, self.dev)
        return (self.epoch, tuple(release), pre, post, dev)

    def __lt__(self, other: Version) -> bool:
        return self._key() < other._key()

    def __le__(self, other: Version) -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: Version) -> bool:
        return self._key() > other._key()

    def __ge__(self, other: Version) -> bool:
        return self._key() >= other._key()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Version) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __str__(self) -> str:
        """The normal form: 1.0.0rc1, 2!1.0.post2.dev3."""
        text = f"{self.epoch}!" if self.epoch else ""
        text += ".".join(str(part) for part in self.release)
        if self.pre is not None:
            text += f"{_PRE_NAME[self.pre[0]]}{self.pre[1]}"
        if self.post is not None:
            text += f".post{self.post}"
        if self.dev is not None:
            text += f".dev{self.dev}"
        return text


def parse_version(text: object) -> Version:
    """A version from its text; UpdateError when it is not one PEP 440 allows."""
    found = _VERSION.match(text) if isinstance(text, str) and len(text) <= 64 else None
    if found is None:
        raise UpdateError(f"{str(text)[:64]!r} is not a version.")
    g = found.groupdict()
    pre = None
    if g["pre_l"]:
        pre = (_PRE_RANK[g["pre_l"].lower()], int(g["pre_n"] or 0))
    post = None
    if g["post_n1"] is not None:
        post = int(g["post_n1"])
    elif g["post_l"]:
        post = int(g["post_n2"] or 0)
    dev = int(g["dev_n"] or 0) if g["dev_l"] else None
    release = tuple(int(part) for part in g["release"].split("."))
    return Version(int(g["epoch"] or 0), release, pre, post, dev, str(text).strip().lstrip("vV"))


def try_version(text: object) -> Version | None:
    try:
        return parse_version(text)
    except UpdateError:
        return None


# ===== the release lists =====


@dataclass(frozen=True)
class Release:
    version: Version
    source: str  # "pypi" | "github"


def releases_from_pypi(document: Any) -> list[Release]:
    """PyPI's JSON (/pypi/<name>/json): every release with at least one file that is not yanked."""
    if not isinstance(document, dict):
        raise UpdateError("PyPI's answer is not a release list.")
    listed = document.get("releases")
    found: list[Release] = []
    if isinstance(listed, dict):
        for text, files in listed.items():
            version = try_version(text)
            if version is None or not isinstance(files, list) or not files:
                continue
            if all(isinstance(f, dict) and f.get("yanked") is True for f in files):
                continue
            found.append(Release(version, "pypi"))
        return found
    info = document.get("info")
    version = try_version(info.get("version")) if isinstance(info, dict) else None
    if version is None:
        raise UpdateError("PyPI's answer names no version.")
    return [Release(version, "pypi")]


def releases_from_github(document: Any) -> list[Release]:
    """GitHub's latest release (/repos/<repo>/releases/latest): its tag, v0.0.2."""
    if not isinstance(document, dict):
        raise UpdateError("GitHub's answer is not a release.")
    if document.get("draft") is True:
        return []
    version = try_version(document.get("tag_name"))
    if version is None:
        raise UpdateError("GitHub's latest release has no version tag.")
    return [Release(version, "github")]


def releases_from(url: str, document: Any) -> list[Release]:
    """A feed's answer read by its shape: GitHub's release has a tag_name; PyPI's list has info."""
    if isinstance(document, dict) and "tag_name" in document:
        return releases_from_github(document)
    return releases_from_pypi(document)


def offered(current: Version, releases: list[Release]) -> Release | None:
    """The newest release offered to someone on `current` (a pre-release only to someone on one), or None
    when there is none newer."""
    allowed = [r for r in releases if current.is_prerelease or not r.version.is_prerelease]
    if not allowed:
        return None
    newest = max(allowed, key=lambda r: r.version._key())
    return newest if newest.version > current else None


def release_page(version: str) -> str:
    """What's new: the release's own page on GitHub (its notes), whichever feed found it."""
    return f"https://github.com/{REPOSITORY}/releases/tag/v{version}"


def wheel_url(version: str) -> str:
    return (
        f"https://github.com/{REPOSITORY}/releases/download/v{version}/{PACKAGE}-{version}-py3-none-any.whl"
    )


# ===== the update's plan =====


def requirement(version: str, source: str) -> str:
    """What uv installs: the version from PyPI, or the release's wheel when only GitHub was reached."""
    parse_version(version)
    if source == "github":
        return f"{PACKAGE}[server] @ {wheel_url(version)}"
    return f"{PACKAGE}[server]=={version}"


def install_command(
    uv: str,
    version: str,
    source: str,
    python: str,
    find_links: str | None = None,
    wheels: tuple[str, ...] = (),
) -> list[str]:
    """`uv tool install --force "swissarmybench[server]==X"` on the Python the app runs on now.
    `find_links`: a folder of wheels to look in as well (the tests' local wheel). `wheels`: the installed
    extensions' wheels at that version, each `--with` (an update keeps them; domain/extensions.py)."""
    # --refresh-package: the package index read again for the app itself (uv's cache can hold the list
    # from before this version was published, and say "no version of swissarmybench==X").
    command = [uv, "tool", "install", "--force", "--refresh-package", PACKAGE, "--python", python]
    kept = [part for wheel in wheels for part in ("--with", wheel)]
    if find_links:
        command += ["--find-links", find_links]
        return [*command, f"{PACKAGE}[server]=={version}", *kept]
    return [*command, requirement(version, source), *kept]


@dataclass(frozen=True)
class UpdatePlan:
    """What the helper does, in order: wait for the app's processes to end, install, check the version,
    start the app (which starts the tray and opens the page). On a failure: start the old version again
    (reinstalled first if it no longer starts) and leave a note that says why."""

    version: str
    current: str
    wait_pids: tuple[int, ...]
    install: tuple[str, ...]
    restore: tuple[str, ...]
    installed_version: tuple[str, ...]
    start: tuple[str, ...]
    info_file: str
    note_file: str
    environ: dict[str, str] = field(default_factory=dict)
    # Windows only: the tool's folder. Another program running from it (an editor's MCP server, a
    # terminal's sab) locks its files, so the helper stops every process whose program is inside it
    # before the install (never itself: it runs the base Python, outside that folder).
    stop_in: str = ""

    def steps(self) -> list[str]:
        return ["wait", *(["stop"] if self.stop_in else []), "install", "check", "start"]

    def to_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "current": self.current,
            "wait_pids": list(self.wait_pids),
            "install": list(self.install),
            "restore": list(self.restore),
            "installed_version": list(self.installed_version),
            "start": list(self.start),
            "info_file": self.info_file,
            "note_file": self.note_file,
            "environ": dict(self.environ),
            "stop_in": self.stop_in,
            "steps": self.steps(),
        }


def plan_update(
    *,
    version: str,
    current: str,
    source: str,
    uv: str,
    tool_python: str,
    python_version: str,
    wait_pids: list[int],
    info_file: str,
    note_file: str,
    find_links: str | None = None,
    environ: dict[str, str] | None = None,
    stop_in: str = "",
    wheels: tuple[str, ...] = (),
    restore_wheels: tuple[str, ...] = (),
) -> UpdatePlan:
    """The plan for updating from `current` to `version`; `tool_python` is the app's own Python (the uv
    tool's), which runs the new version once it is installed. `stop_in` (Windows): the tool's folder,
    whose programs still running are stopped before the install. `wheels`, `restore_wheels`: the installed
    extensions' wheels at `version` and at `current` (each kept, `--with`)."""
    if parse_version(version) <= parse_version(current) and find_links is None:
        raise UpdateError(f"{version} is not newer than {current}.")
    start = (tool_python, "-m", f"{PACKAGE}.server", "start")
    probe = "import importlib.metadata as m; print(m.version('swissarmybench'))"
    return UpdatePlan(
        version=version,
        current=current,
        wait_pids=tuple(pid for pid in wait_pids if pid > 0),
        install=tuple(install_command(uv, version, source, python_version, find_links, wheels)),
        restore=tuple(install_command(uv, current, "pypi", python_version, find_links, restore_wheels)),
        installed_version=(tool_python, "-I", "-c", probe),
        start=start,
        info_file=info_file,
        note_file=note_file,
        environ=dict(environ or {}),
        stop_in=stop_in,
    )


def update_question(version: str, at_risk: dict[str, Any]) -> str:
    """The question before an update that would lose something (the tray's box, the agent's Allow)."""
    lines = [f"The app stops, installs {version} and starts again. Nothing is saved for you."]
    unsaved = [str(name) for name in at_risk.get("unsaved", [])]
    if unsaved:
        lines.append("Unsaved changes are lost: " + ", ".join(unsaved))
    kernels = int(at_risk.get("kernels", 0))
    if kernels:
        lines.append(f"{kernels} running kernel{'s stop' if kernels != 1 else ' stops'}.")
    return "\n".join(lines)


# ===== the tray's menu =====


@dataclass(frozen=True)
class MenuItem:
    """One line of the tray's menu: `id` names its action ("-" a separator); `checked` None: no check."""

    id: str
    text: str = ""
    checked: bool | None = None
    enabled: bool = True
    default: bool = False

    @property
    def separator(self) -> bool:
        return self.id == "-"


SEPARATOR = MenuItem("-")


@dataclass(frozen=True)
class TrayState:
    running: bool
    update: str | None = None  # the version offered
    tables: tuple[tuple[str, str], ...] = ()  # (grid id, its table's name)
    documents: tuple[tuple[str, str, bool], ...] = ()  # (key, title, unsaved changes)
    startup: bool | None = None  # start at sign-in: None where there is no such thing
    startup_label: str = "Start with Windows"  # "Open at login" on macOS and Linux
    gave_up: bool = False  # the server died RESTARTS times in a row: the tray stopped starting it
    failed: str | None = None  # the last update's failure, said once


def tooltip(state: TrayState) -> str:
    if not state.running:
        return "Swiss Army Bench: stopped"
    if state.update:
        return f"Update available: {state.update}"
    return "Swiss Army Bench"


def _listed(prefix: str, entries: list[tuple[str, str]], more_id: str) -> list[MenuItem]:
    shown = [MenuItem(f"{prefix}:{key}", text) for key, text in entries[:MENU_MAX_ITEMS]]
    if len(entries) > MENU_MAX_ITEMS:
        shown.append(MenuItem(more_id, f"{len(entries) - MENU_MAX_ITEMS} more…"))
    return shown


def tray_menu(state: TrayState) -> list[MenuItem]:
    """The right-click menu, top to bottom. An update comes first; then what is open (tables, the
    Workbench's documents); then the pages; then the app itself."""
    items: list[MenuItem] = []
    if state.running and state.update:
        items += [
            MenuItem("update", f"Update to {state.update}"),
            MenuItem("whats_new", "What's new"),
            SEPARATOR,
        ]
    if state.running:
        items.append(MenuItem("open", "Open", default=True))
        tables = _listed("table", list(state.tables), "open")
        documents = _listed(
            "document",
            [(key, f"{title} •" if unsaved else title) for key, title, unsaved in state.documents],
            "workbench",
        )
        if tables or documents:
            items += [SEPARATOR, *tables, *([SEPARATOR] if tables and documents else []), *documents]
        items += [
            SEPARATOR,
            MenuItem("workbench", "Open the Workbench"),
            MenuItem("blades", "Open the blades page"),
        ]
        items += [SEPARATOR, MenuItem("restart", "Restart")]
    elif state.gave_up:
        items += [MenuItem("start", "Swiss Army Bench stopped: Restart", default=True), SEPARATOR]
    else:
        items += [MenuItem("start", "Start", default=True), SEPARATOR]
    if state.startup is not None:
        items.append(MenuItem("startup", state.startup_label, checked=state.startup))
    items.append(MenuItem("quit", "Stop and quit" if state.running else "Quit"))
    return items
