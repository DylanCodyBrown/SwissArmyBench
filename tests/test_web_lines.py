"""The front end's lines stay readable: no web/src line is over 300 characters (the craft review of
2026-11-22: 95 such lines made diffs and reviews of those files hard to read). No formatter is added (a
new dependency is the owner's call: docs/ideas.md "Review fixes E"); a long line is wrapped by hand."""

from __future__ import annotations

from pathlib import Path

LIMIT = 300
SOURCE = Path(__file__).resolve().parents[1] / "web" / "src"

# Files left as they are, each with its reason.
EXCLUDED = {
    # VS Code's Source Control view and graph, copied as they are (THIRD_PARTY_NOTICES.md): kept by decision.
    "scmPage.ts": "a copy of VS Code's Source Control view",
    "scmGraph.ts": "a copy of VS Code's scmHistory.ts",
    # Being split into parts by another change (the four giant closures): their lines are wrapped there.
    "workbenchNotebook.ts": "split by another change",
    "workbenchScript.ts": "split by another change",
    "environmentPage.ts": "split by another change",
    "structureDoc.ts": "split by another change",
}


def test_no_front_end_line_is_over_300_characters() -> None:
    long: list[str] = []
    for path in sorted(SOURCE.rglob("*.ts")):
        if path.name in EXCLUDED:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if len(line) > LIMIT:
                long.append(f"{path.relative_to(SOURCE).as_posix()}:{number} ({len(line)} characters)")
    assert not long, "Wrap these lines by hand:\n" + "\n".join(long)


def test_every_excluded_file_is_there() -> None:
    """An exclusion names a file that exists (a renamed or removed one is taken out of the list)."""
    for name in EXCLUDED:
        assert (SOURCE / name).is_file(), name
