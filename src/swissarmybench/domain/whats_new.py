"""What's New (the owner, 2026-11-25: "a what's new page that opens and closes as an overlay when a user
update ... simple bullet points updates with a time stamp in a markdown file ... new features and bug fixes
seperated"; "Short descriptions as possible"): WHATSNEW.md, shipped in the package, read into releases.

The file's shape, held by `problems` (tests/test_whats_new.py and the release's version check):

    # What's new in Swiss Army Bench            (a title, once)
    ## 0.0.39 · 2026-11-25 14:30 UTC           (a release: its version and when, newest first)
    ### New features                           (exactly these two sections, in this order)
    - Collaboration panel                      (a bullet: one short line, MAX_BULLET characters at most)
    ### Bug fixes
    - Fixed: sab_api install error

Which releases to show: every one newer than the version last seen on this computer (`whats_new.json`), the
newest first; nothing on a brand new install (the version is recorded, nothing shown). Pure rules: no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from swissarmybench.domain import updates

FILE = "WHATSNEW.md"
FEATURES = "New features"
FIXES = "Bug fixes"
SECTIONS = (FEATURES, FIXES)
MAX_BULLET = 60  # the owner: "Short descriptions as possible"
TIME_FORMAT = "%Y-%m-%d %H:%M"
_RELEASE = re.compile(r"^## (\S+) · (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC$")
_SECTION = re.compile(r"^### (.+)$")
_BULLET = re.compile(r"^- (.+)$")
_NEXT: dict[str | None, str] = {None: FEATURES, FEATURES: FIXES, FIXES: ""}  # the section that may come next


class WhatsNewError(ValueError):
    """WHATSNEW.md is not in its shape: said with its line."""


@dataclass
class Release:
    version: str
    time: str  # "2026-11-25 14:30" (UTC)
    features: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "time": f"{self.time} UTC",
            "features": self.features,
            "fixes": self.fixes,
        }

    def markdown(self) -> str:
        """The release's two sections as the window shows them (the app's own Markdown)."""
        parts = []
        for title, bullets in ((FEATURES, self.features), (FIXES, self.fixes)):
            parts.append(f"### {title}\n" + ("\n".join(f"- {b}" for b in bullets) if bullets else "None."))
        return "\n\n".join(parts)


def _section(release: Release, name: str) -> list[str]:
    return release.features if name == FEATURES else release.fixes


def parse(text: str) -> list[Release]:
    """WHATSNEW.md's releases in the file's order; WhatsNewError on the first line out of shape."""
    releases: list[Release] = []
    section: str | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line or (line.startswith("# ") and not releases):
            continue
        if found := _RELEASE.match(line):
            version, time = found.groups()
            if updates.try_version(version) is None:
                raise WhatsNewError(f"Line {number}: {version} is not a version.")
            try:
                datetime.strptime(time, TIME_FORMAT)
            except ValueError:
                raise WhatsNewError(f"Line {number}: {time} is not a time (YYYY-MM-DD HH:MM UTC).") from None
            releases.append(Release(version, time))
            section = None
        elif found := _SECTION.match(line):
            name = found.group(1).strip()
            if not releases or name not in SECTIONS:
                raise WhatsNewError(
                    f'Line {number}: a section is "### {FEATURES}" or "### {FIXES}", under a release.'
                )
            if name != _NEXT[section]:
                raise WhatsNewError(f"Line {number}: each release has {FEATURES} then {FIXES}, once each.")
            section = name
        elif found := _BULLET.match(line):
            if section is None:
                raise WhatsNewError(f"Line {number}: a bullet goes under {FEATURES} or {FIXES}.")
            words = found.group(1).strip()
            if len(words) > MAX_BULLET:
                raise WhatsNewError(
                    f"Line {number}: a bullet is {MAX_BULLET} characters at most, a few words."
                )
            _section(releases[-1], section).append(words)
        else:
            raise WhatsNewError(f"Line {number}: only a release, its two sections and short bullets.")
    return releases


def problems(text: str) -> list[str]:
    """Everything wrong with the file: its shape, both sections in every release, newest first, each version
    once."""
    try:
        releases = parse(text)
    except WhatsNewError as error:
        return [str(error)]
    found: list[str] = []
    if not releases:
        found.append("WHATSNEW.md has no release.")
    keys = [updates.parse_version(r.version) for r in releases]
    if keys != sorted(keys, reverse=True) or len(set(keys)) != len(keys):
        found.append("The releases go newest first, each version once.")
    for release in releases:
        block = text.split(f"## {release.version} · ", 1)[1].split("\n## ", 1)[0]
        if not all(f"### {name}" in block for name in SECTIONS):
            found.append(f"{release.version}: it has both {FEATURES} and {FIXES}.")
    return found


def has(releases: list[Release], version: str) -> bool:
    """Whether a version has its entry (the release refuses a version without one)."""
    wanted = updates.try_version(version)
    return wanted is not None and any(updates.try_version(r.version) == wanted for r in releases)


def newer_than(releases: list[Release], seen: str | None, upto: str | None = None) -> list[Release]:
    """The releases newer than the version last seen (none seen: none), up to the running one, newest
    first."""
    last = updates.try_version(seen) if seen else None
    top = updates.try_version(upto) if upto else None
    if last is None:
        return []
    kept = [
        r
        for r in releases
        if (v := updates.try_version(r.version)) is not None and v > last and (top is None or v <= top)
    ]
    return sorted(kept, key=lambda r: updates.parse_version(r.version), reverse=True)


def should_open(current: str, seen: str | None) -> bool:
    """Opens by itself on the first start after an update: the running version newer than the one last seen.
    A brand new install (nothing seen) records its version and opens nothing."""
    now, last = updates.try_version(current), updates.try_version(seen) if seen else None
    return now is not None and last is not None and now > last
