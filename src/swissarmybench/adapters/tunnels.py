"""devtunnel's file on this computer (domain/sharing.py's rules; server/tunnels.py runs it).

download  on the first share only (never with the app's install): one GET from Microsoft's download store
          over HTTPS (the host the official install script uses; a redirect anywhere else refused), at most
          200 MB, its bytes checked against the store's Content-MD5, then the signature check it is handed
          (server/tunnels.py: Windows' Authenticode, macOS' code signature); kept as the state folder's
          devtunnel/devtunnel[.exe] only when every check passed (a temporary file, then one replace)
stand-in  SWISSARMYBENCH_DEVTUNNEL_STANDIN names a Python file that stands in for the program (tests): the
          "download" is that file's bytes with their own Content-MD5, run by this Python; nothing leaves
          the computer
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import platform
import sys
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from swissarmybench.domain import sharing as rules
from swissarmybench.domain.sharing import SharingError

STANDIN_ENV: str = "SWISSARMYBENCH_DEVTUNNEL_STANDIN"
_TIMEOUT: float = 120.0

# One GET: (the bytes, the answer's headers with lower-case names). Tests pass their own.
Fetch = Callable[[str], tuple[bytes, dict[str, str]]]
# The system's signature check of a downloaded file (system, its temporary path): True when signed rightly.
Verify = Callable[[str, Path], bool]


def https_fetch(url: str) -> tuple[bytes, dict[str, str]]:
    """The file from Microsoft's download store: HTTPS, its host checked before and after any redirect."""
    if urllib.parse.urlsplit(url).hostname != rules.DOWNLOAD_HOST or not url.startswith("https://"):
        raise SharingError("devtunnel is downloaded from Microsoft's download store only.")
    request = urllib.request.Request(url, headers={"User-Agent": "swissarmybench"})  # noqa: S310 (https)
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as answer:  # noqa: S310 (https, the host checked)
        final = answer.geturl()
        if urllib.parse.urlsplit(final).hostname != rules.DOWNLOAD_HOST or not final.startswith("https://"):
            raise SharingError("The download was sent somewhere other than Microsoft's download store.")
        data = answer.read(rules.MAX_BYTES + 1)
        headers = {k.lower(): v for k, v in answer.headers.items()}
    if len(data) > rules.MAX_BYTES:
        raise SharingError("The download is larger than devtunnel is: it was not kept.")
    return data, headers


def standin_fetch(path: str) -> Fetch:
    def fetch(url: str) -> tuple[bytes, dict[str, str]]:
        data = Path(path).read_bytes()
        md5 = base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode("ascii")
        return data, {"content-md5": md5}

    return fetch


class TunnelFiles:
    """Where devtunnel is kept, and its download."""

    def __init__(
        self, folder: Path, environ: dict[str, str] | None = None, fetch: Fetch | None = None
    ) -> None:
        environ = dict(os.environ if environ is None else environ)
        self._folder = folder
        self.standin = environ.get(STANDIN_ENV) or None
        self._fetch = fetch or (standin_fetch(self.standin) if self.standin else https_fetch)

    def system(self) -> tuple[str, str]:
        return rules.system_of(sys.platform, platform.machine())

    @property
    def path(self) -> Path:
        if self.standin:
            return self._folder / "devtunnel_standin.py"
        return self._folder / rules.program_name(self.system()[0])

    def installed(self) -> bool:
        try:
            return self.path.is_file()
        except SharingError:
            return False

    def checks(self) -> str:
        """Which checks this computer's download passes (said in the dialog's details and the docs)."""
        try:
            return rules.CHECKS[self.system()[0]]
        except SharingError as error:
            return str(error)

    def command(self, args: list[str]) -> list[str]:
        if self.standin:
            return [sys.executable, "-I", str(self.path), *args]
        return [str(self.path), *args]

    def install(self, verify: Verify) -> None:
        system, cpu = ("linux", "x64") if self.standin else self.system()
        data, headers = self._fetch(rules.download_url(system, cpu))
        if len(data) > rules.MAX_BYTES:
            raise SharingError("The download is larger than devtunnel is: it was not kept.")
        if not rules.checksum_matches(data, headers.get("content-md5")):
            raise SharingError(rules.CHECKSUM_REFUSED)
        self._folder.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(dir=self._folder, prefix=".devtunnel-")
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            temporary = Path(name)
            temporary.chmod(0o755)
            if not self.standin and not verify(system, temporary):
                raise SharingError(rules.SIGNATURE_REFUSED)
            os.replace(temporary, self.path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(name)
