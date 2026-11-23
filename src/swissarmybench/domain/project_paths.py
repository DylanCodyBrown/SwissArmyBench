"""Is this path inside that folder? THE one rule (the craft review of 2026-11-22: it was written eight times,
with case and links handled differently, so the scaffold, the outline, the Environment and the Connections
page could disagree about whether a document is the project's).

  relative_in(path, folder, real=None)   the path's place inside the folder as a slash path, as it was
                                         written; None when it is not inside
  inside(path, folder, real=None)        the same as yes or no

The rule, from the text alone (nothing is read from disk here):

- either separator is the same separator, and a trailing one on the folder means nothing;
- letters are compared without case: Windows' and macOS's disks keep no case apart, and a project folder is
  never told from another by case alone (on Linux two folders that differ only so are taken as one, which
  the app never makes); the answer keeps the path's own spelling;
- the folder itself is not inside itself, and a path with a `..` part is never inside;
- links: a caller that can ask the disk hands its port in as `real` (os.path.realpath, an adapter's method).
  A path that is not inside as written is then asked again with both resolved, so a project reached through
  a link and a file named by its real place are the same project.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _slashed(path: str) -> str:
    return path.replace("\\", "/")


def _within(path: str, folder: str) -> str | None:
    clean = _slashed(path)
    root = _slashed(folder).rstrip("/") + "/"
    if ".." in clean.split("/"):
        return None
    # Folded piece by piece (never sliced after folding: a folded letter can be longer than itself).
    if clean[: len(root)].casefold() != root.casefold():
        return None
    return clean[len(root) :].strip("/") or None


def relative_in(path: Any, folder: Any, real: Callable[[str], str] | None = None) -> str | None:
    """Where `path` is inside `folder`, as a slash path in the path's own spelling; None when it is not
    inside (or either is not a path at all). `real`: the caller's port that resolves links, asked only when
    the path is not inside as written."""
    if not isinstance(path, str) or not isinstance(folder, str) or not path.strip() or not folder.strip():
        return None
    found = _within(path, folder)
    if found is None and real is not None:
        found = _within(real(path), real(folder))
    return found


def inside(path: Any, folder: Any, real: Callable[[str], str] | None = None) -> bool:
    """Whether `path` is inside `folder` (relative_in's rule)."""
    return relative_in(path, folder, real) is not None


def key(path: str) -> str:
    """A folder's key for comparing (the same rule: either separator, no trailing one, letters without case).
    One project folder written two ways (C:\\Users\\me\\Sales, c:/users/me/sales/) has one key."""
    return _slashed(path).rstrip("/").casefold()


def same(a: str, b: str) -> bool:
    """Whether two paths name the same folder (key's rule)."""
    return key(a) == key(b)
