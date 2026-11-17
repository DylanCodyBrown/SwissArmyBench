"""Add API's files and fetches (domain/apis.py and domain/api_clients.py have the rules,
services/apis.py the use case).

  the spec     an OpenAPI document from a file on this computer or an address (at the user's word, or
               the agent's: the one outbound request Add API makes), JSON, or YAML when this Python has
               PyYAML (it is not a dependency of the app)
  the file     API_<name>.py written beside data.py (a project) or in the Workbench's own folder, and
               the made files beside a notebook read back (the exporter pastes them inline)
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from swissarmybench.domain import apis
from swissarmybench.domain.packages import MissingPackagesError, missing_packages

MAX_SPEC_BYTES: int = apis.MAX_SPEC_CHARS
MAX_CLIENT_BYTES: int = 20_000_000
FETCH_SECONDS: float = 20.0


def _decoded(raw: bytes, where: str) -> str:
    if len(raw) > MAX_SPEC_BYTES:
        raise apis.ApiError(f"{where} is too big for an OpenAPI document (10 MB at most).")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise apis.ApiError(f"{where} is not text (UTF-8).") from None


class SpecSource:
    def read_file(self, path: str) -> tuple[str, str]:
        """A document on this computer: its text, and where it is (a relative server is read against it)."""
        file = Path(path).expanduser()
        try:
            if not file.is_file():
                raise FileNotFoundError(f"{path[:300]} is not a file.")
            if file.stat().st_size > MAX_SPEC_BYTES:
                raise apis.ApiError(f"{file.name} is too big for an OpenAPI document (10 MB at most).")
            return _decoded(file.read_bytes(), file.name), ""
        except OSError as error:
            raise FileNotFoundError(f"{path[:300]} could not be read ({error.strerror or error}).") from None

    def fetch(self, url: str) -> tuple[str, str]:
        """A document at an address (http or https): its text, and the address it came from in the end."""
        if not url.startswith(("http://", "https://")) or len(url) > 2_000:
            raise apis.ApiError("The OpenAPI document's address is an http or https URL.")
        accept = {"Accept": "application/json, application/yaml;q=0.9, */*;q=0.5"}
        request = urllib.request.Request(url, headers=accept)  # noqa: S310 (http(s) only)
        try:
            with urllib.request.urlopen(request, timeout=FETCH_SECONDS) as answer:  # noqa: S310 (http(s) only)
                raw = answer.read(MAX_SPEC_BYTES + 1)
                return _decoded(raw, url.split("?")[0]), str(answer.geturl())
        except urllib.error.HTTPError as error:
            raise apis.ApiError(f"{url.split('?')[0]} answered {error.code} ({error.reason}).") from None
        except (urllib.error.URLError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise apis.ApiError(f"{url.split('?')[0]} could not be reached ({reason}).") from None

    def document(self, text: str) -> dict[str, Any]:
        """The document's JSON object; YAML through PyYAML, when this Python has it."""
        if not apis.looks_like_yaml(text):
            return apis.read_json(text)
        try:
            import yaml  # type: ignore[import-untyped]  # optional: PyYAML is not a dependency of the app
        except ImportError:
            # The one missing-package answer: the page's prompt offers PyYAML (into the app's Python).
            raise MissingPackagesError(
                missing_packages("Reading YAML API documents", ["PyYAML"], sys.executable, own=True)
            ) from None
        try:
            found = yaml.safe_load(text)
        except yaml.YAMLError as error:
            raise apis.ApiError(f"The OpenAPI document is not YAML that can be read ({error}).") from None
        if not isinstance(found, dict):
            raise apis.ApiError("The OpenAPI document is an object, with openapi (or swagger) and paths.")
        return found


class ApiFiles:
    def folder(self, folder: str) -> str:
        root = Path(folder).expanduser()
        if not root.is_dir():
            raise FileNotFoundError(f"The folder {folder[:300]} is not there.")
        return str(root.resolve())

    def path(self, folder: str, name: str) -> str:
        return str(Path(folder) / name)

    def read(self, path: str) -> str | None:
        file = Path(path)
        if not file.is_file():
            return None
        if file.stat().st_size > MAX_CLIENT_BYTES:
            return ""  # not one Add API made: too big to be
        return file.read_text(encoding="utf-8", errors="replace")

    def write(self, path: str, text: str) -> None:
        """Written whole or not at all (a file beside it, then moved into place)."""
        file = Path(path)
        file.parent.mkdir(parents=True, exist_ok=True)  # an API's own folder in the library
        handle, temporary = tempfile.mkstemp(prefix=f".{file.stem}-", suffix=file.suffix, dir=file.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
                out.write(text)
            os.replace(temporary, file)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def clients(self, folder: str) -> dict[str, str]:
        """The API_*.py files in a folder, by module name, with their text."""
        root = Path(folder).expanduser()
        if not root.is_dir():
            return {}
        found: dict[str, str] = {}
        for file in sorted(root.glob("API_*.py")):
            text = self.read(str(file))
            if text:
                found[file.stem] = text
        return found


class ApiLibrary(ApiFiles):
    """This computer's APIs (the owner, 2026-11-17: "Apis, Connections they live OUTSIDE of the project"):
    one folder each under the library's apis/ folder (~/.swissarmybench/library/apis/<name>/), holding
    API_<name>.py, openapi.json (the document as read, or a form's operations written as one) and
    source.json (where it was read from, when, and the check-for-changes switch). Text only: no
    secret, no response."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def folder_for(self, name: str) -> str:
        return str(self.root / name)

    def folders(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return [str(f) for f in sorted(self.root.iterdir(), key=lambda f: f.name.casefold()) if f.is_dir()]

    def find(self, folder: str, pattern: str) -> list[str]:
        return [str(f) for f in sorted(Path(folder).glob(pattern))]

    def remove(self, folder: str) -> None:
        """An API's folder, gone (only one inside the library)."""
        target = Path(folder).resolve()
        if not target.is_relative_to(self.root.resolve()) or target == self.root.resolve():
            raise apis.ApiError("Only an API's own folder in the library is removed.")
        shutil.rmtree(target, ignore_errors=True)
