"""Widgets and canvases on disk.

WidgetFiles: the open project's widgets/ folder (at its top, shared in Git with the project), the library's
widgets/ folder (one `<name>.widget.py` each, written atomically and only when its bytes change, so a save
that changes nothing changes nothing in Git) and the extension's prebuilt widgets (read-only, shipped in the
package's widgets/ folder).

CanvasFiles: a canvas file (`<app>.canvas.json`, a project file): read with a stamp (what it was when read, so
a change made elsewhere is seen before anything is written over it), written atomically only when its bytes
change, and a copy of a file that does not read kept beside it (the file itself is never written over).

PreviewFiles: the state folder's cache of widget previews (PNG), by the widget file's hash and the theme.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench_streamlit.domain import widgets as rules

PREBUILT = Path(__file__).resolve().parents[1] / "widgets"


# Where a widget lives, in the order a name is found: the open project's widgets/ (its top, shared in Git with
# it), the library's widgets/, the extension's prebuilt ones. A name in the project wins over the library's.
PLACES: tuple[str, ...] = ("project", "library", "prebuilt")


class WidgetFiles:
    def __init__(
        self,
        library: Callable[[], Path] | None,
        made: Callable[[], object] = lambda: None,
        prebuilt: Path = PREBUILT,
        project: Callable[[], str | Path | None] = lambda: None,
    ) -> None:
        self._library = library
        self._made = made
        self._prebuilt = prebuilt
        self._project = project

    def folder(self, place: str = "library") -> Path | None:
        if place == "prebuilt":
            return self._prebuilt
        if place == "project":
            top = self._project()
            return None if not top else Path(top) / rules.FOLDER
        return None if self._library is None else self._library() / rules.FOLDER

    def _files(self, folder: Path | None) -> list[Path]:
        if folder is None or not folder.is_dir():
            return []
        return sorted(p for p in folder.glob("*" + rules.SUFFIX) if p.is_file())

    def all(self) -> list[tuple[str, str, str]]:
        """(file name, text, place) for every widget file: the project's, the library's, then the prebuilt
        ones."""
        found: list[tuple[str, str, str]] = []
        for place in PLACES:
            for path in self._files(self.folder(place)):
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                found.append((path.name, text, place))
        return found

    def path(self, name: str, place: str = "library") -> Path | None:
        folder = self.folder(place)
        return None if folder is None else folder / rules.file_name(name)

    def place_of(self, name: str) -> str | None:
        """Where the widget of this name is found first (None: nowhere)."""
        for place in PLACES:
            path = self.path(name, place)
            if path is not None and path.is_file():
                return place
        return None

    def read(self, name: str, place: str | None = None) -> tuple[str, str] | None:
        """(its text, its place): the first found (or in `place`)."""
        for one in (place,) if place else PLACES:
            path = self.path(name, one)
            if path is not None and path.is_file():
                try:
                    return path.read_text(encoding="utf-8"), one
                except (OSError, UnicodeDecodeError):
                    return None
        return None

    def write(self, name: str, text: str, place: str = "library") -> bool:
        if place == "prebuilt":
            raise PermissionError("A prebuilt widget is read-only.")
        path = self.path(name, place)
        if path is None:
            raise PermissionError(
                "Open a project first: its widgets are in its widgets/ folder."
                if place == "project"
                else "This server keeps no library (a test's): widgets are not saved."
            )
        if place == "library":
            self._made()
        return write_atomic(path, text, if_changed=True, newline="\n")

    def remove(self, name: str, place: str = "library") -> None:
        path = self.path(name, place) if place != "prebuilt" else None
        if path is not None:
            path.unlink(missing_ok=True)

    def where(self, name: str, place: str = "library") -> str:
        path = self.path(name, place) if place != "prebuilt" else None
        return str(path) if path is not None else ""


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class CanvasFiles:
    @staticmethod
    def read(path: str) -> tuple[str, str]:
        """The file's text and its stamp."""
        data = Path(path).read_bytes()
        return data.decode("utf-8"), hashlib.sha256(data).hexdigest()

    @staticmethod
    def stamp(path: str) -> str | None:
        try:
            return hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError:
            return None

    @staticmethod
    def write(path: str, text: str) -> str:
        """Written atomically (only when its bytes change); its new stamp."""
        write_atomic(path, text, if_changed=True, newline="\n")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def keep_copy(path: str) -> str:
        """A copy of a file that does not read, beside it (one per content): the copy's path."""
        source = Path(path)
        data = source.read_bytes()
        copy = source.with_name(f"{source.name}.broken-{hashlib.sha256(data).hexdigest()[:8]}")
        if not copy.exists():
            shutil.copyfile(source, copy)
        return str(copy)

    @staticmethod
    def exists(path: str) -> bool:
        return os.path.isfile(path)


class PreviewFiles:
    def __init__(self, folder: Path | None) -> None:
        self._folder = folder

    def path(self, key: str) -> Path | None:
        return None if self._folder is None else self._folder / f"{key}.png"

    def get(self, key: str) -> bytes | None:
        path = self.path(key)
        try:
            return path.read_bytes() if path is not None else None
        except OSError:
            return None

    def put(self, key: str, data: bytes) -> None:
        path = self.path(key)
        if path is not None:
            write_atomic(path, data)

    def failed(self, key: str) -> str | None:
        path = self.path(key)
        if path is None:
            return None
        try:
            return path.with_suffix(".failed").read_text(encoding="utf-8")
        except OSError:
            return None

    def fail(self, key: str, said: str) -> None:
        path = self.path(key)
        if path is not None:
            write_atomic(path.with_suffix(".failed"), said[:2000])


def read_text(path: str) -> str | None:
    """A small text file (a project's data.py), or None when it is not there."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def folder_names(folder: str) -> list[str]:
    """The names of a folder's files (a project's canvases)."""
    try:
        return sorted(p.name for p in Path(folder).iterdir() if p.is_file())
    except OSError:
        return []
