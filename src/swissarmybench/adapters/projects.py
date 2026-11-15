"""A project's folder on disk (domain/projects.py has the rules; services/projects.py and
services/streamlit.py the use cases): made, listed, its own files read and written, zipped.

Everything here is at the user's own word: a folder they named (New project), the project's exports
(data.py, pages/*.py), a zip they chose (Save as). A file that is there is replaced only where the use
case says so: data.py is never written over by New project, and a page of pages/ only when the use
case says it is its own.
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Callable
from pathlib import Path

MAX_TEXT_BYTES: int = 20_000_000


class ProjectFiles:
    @staticmethod
    def _folder(folder: str) -> Path:
        try:
            root = Path(folder).expanduser().resolve()
            try:
                root.stat()
            except FileNotFoundError:
                pass
            return root
        except OSError as error:
            raise FileNotFoundError(
                f"{folder[:200]} is not a folder this computer can use ({error})."
            ) from None

    def folder_of(self, path: str) -> str:
        return str(Path(path).expanduser().resolve().parent)

    def make(self, parent: str, name: str) -> str:
        """A new project's folder (or one that is there and holds no data.py yet)."""
        root = self._folder(parent)
        if not root.is_dir():
            raise FileNotFoundError(f"The folder {root} is not there.")
        made = root / name
        if made.exists() and not made.is_dir():
            raise FileExistsError(f"{made} is a file: pick another name.")
        if (made / "data.py").exists() or (made / "data.ipynb").exists():
            raise FileExistsError(f"{made} is a project already (it has its data): open it.")
        made.mkdir(exist_ok=True)
        return str(made)

    def names(self, folder: str) -> list[str]:
        """The folder's own files (not its folders'), by name."""
        root = self._folder(folder)
        if not root.is_dir():
            raise FileNotFoundError(f"The folder {root} is not there.")
        return sorted(entry.name for entry in os.scandir(root) if entry.is_file())

    def path(self, folder: str, name: str) -> str:
        return str(self._folder(folder) / name)

    def read(self, folder: str, name: str) -> str | None:
        """A file of the project's as text (None: it is not there)."""
        file = self._folder(folder) / name
        if not file.is_file():
            return None
        if file.stat().st_size > MAX_TEXT_BYTES:
            raise ValueError(f"{file.name} is too large to read here.")
        return file.read_bytes().decode("utf-8-sig")

    def write(self, folder: str, name: str, text: str) -> str:
        """Write a file of the project's whole (a temporary file renamed over it)."""
        root = self._folder(folder)
        if not root.is_dir():
            raise FileNotFoundError(f"The folder {root} is not there.")
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        if file.is_file() and not os.access(file, os.W_OK):
            raise PermissionError(f"{file} is read-only.")
        partial = file.with_name(f".{file.name}.saving")
        partial.write_bytes(text.encode("utf-8"))
        os.replace(partial, file)
        return str(file)

    def replace_pages(self, folder: str, files: dict[str, str], own: Callable[[str], bool]) -> list[str]:
        """The project's pages/*.py as the canvas has them now: each written, and a page the canvas
        no longer has taken away; but only a page `own` says is the app's (by its text). Another file
        there is left as it is: the names of those that were not written over."""
        pages = self._folder(folder) / "pages"

        def mine(file: Path) -> bool:
            try:
                return own(file.read_bytes()[:4096].decode("utf-8-sig", "replace"))
            except OSError:
                return False

        left: list[str] = []
        for name, text in files.items():
            file = self._folder(folder) / name
            if file.is_file() and not mine(file):
                left.append(name)
                continue
            self.write(folder, name, text)
        written = {Path(name).name for name in files}
        for old in pages.glob("*.py") if pages.is_dir() else []:
            if old.name not in written and mine(old):
                old.unlink(missing_ok=True)
        return left

    def relative(self, folder: str, path: str) -> str | None:
        """A file's path inside the project, with forward slashes (None: it is outside)."""
        try:
            return Path(path).expanduser().resolve().relative_to(self._folder(folder)).as_posix()
        except (ValueError, OSError):
            return None

    def zip(self, path: str, files: dict[str, str]) -> tuple[str, list[str]]:
        """One zip of text files, at the path the user chose (its folder must be there)."""
        try:
            target = Path(path).expanduser().resolve()
        except OSError as error:
            raise FileNotFoundError(
                f"{path[:200]} is not a place this computer can save ({error})."
            ) from None
        if target.suffix.lower() != ".zip":
            target = target.with_name(target.name + ".zip")
        if not target.parent.is_dir():
            raise FileNotFoundError(f"The folder {target.parent} is not there.")
        if target.is_dir():
            raise FileNotFoundError(f"{target} is a folder: name a zip file.")
        partial = target.with_name(f".{target.name}.saving")
        try:
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as out:
                for name in sorted(files):
                    out.writestr(name, files[name].encode("utf-8"))
            os.replace(partial, target)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return str(target), sorted(files)
