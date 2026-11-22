"""uv and pip stood in for (SWISSARMYBENCH_LIBRARIES_STANDIN names this file): the Environment's Libraries tab
installs, updates and removes made-up libraries in a made-up `.venv`, and a made-up package index answers
their newest versions on 127.0.0.1. Standard library only; nothing is downloaded and nothing runs.

  python libraries_standin.py install <python> [--upgrade] name[==version] ...
  python libraries_standin.py uninstall <python> name ...
  python libraries_standin.py venv <project folder> name[==version] ...   (the project's own .venv made)

`make_venv(project, libraries)` lays the environment out as the app reads it (a Python's place, pyvenv.cfg,
each library's metadata folder); `Index(versions)` is the package index.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# What the stand-in installs when no version is asked for (the made-up index's newest).
NEWEST = {"duckdb": "1.4.3", "pandas": "2.3.3", "polars": "1.36.0", "pyarrow": "22.0.0", "openpyxl": "3.1.5"}


def site_packages(project: Path) -> Path:
    return project / ".venv" / "lib" / "python3.12" / "site-packages"


def _folder(site: Path, name: str, version: str) -> Path:
    return site / f"{name.replace('-', '_')}-{version}.dist-info"


def remove(site: Path, name: str) -> None:
    for old in site.glob(f"{name.replace('-', '_')}-*.dist-info"):
        for file in old.iterdir():
            file.unlink()
        old.rmdir()


def put(site: Path, name: str, version: str) -> None:
    remove(site, name)
    folder = _folder(site, name, version)
    folder.mkdir(parents=True)
    text = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    (folder / "METADATA").write_text(text, encoding="utf-8")


def make_venv(project: Path, libraries: dict[str, str]) -> Path:
    """A project's .venv as the Libraries tab reads it. Returns its Python's place (an empty file)."""
    python = project / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")
    (project / ".venv" / "pyvenv.cfg").write_text("version = 3.12.7\n", encoding="utf-8")
    for name, version in libraries.items():
        put(site_packages(project), name, version)
    return python


class Index:
    """A made-up package index on 127.0.0.1: GET /<name>/json answers {"info": {"version": ...}}."""

    def __init__(self, versions: dict[str, str]) -> None:
        self.versions = dict(versions)
        self.asked: list[str] = []
        index = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                name = self.path.strip("/").split("/")[0].lower()
                index.asked.append(name)
                version = index.versions.get(name)
                body = json.dumps({"info": {"name": name, "version": version}} if version else {}).encode()
                self.send_response(200 if version else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def main(argv: list[str]) -> int:
    action, python, *rest = argv
    if action == "venv":  # python is the project's folder here: its made-up .venv, as the app makes one
        folder = Path(python)
        if (folder / "venv-fails.txt").exists():  # a test's way to say: this computer cannot make one
            print("error: No interpreter found for the made-up project")
            return 2
        chosen = {}
        for spec in rest:
            name = spec.split("==")[0].split("[")[0]
            chosen[name] = spec.partition("==")[2] or NEWEST.get(name.lower(), "1.0.0")
        make_venv(folder, chosen)
        print(f"Made {folder / '.venv'}")
        return 0
    project = Path(python).parent.parent.parent
    site = site_packages(project)
    for spec in [r for r in rest if not r.startswith("-")]:
        name, _, version = spec.partition("==")
        if action == "uninstall":
            remove(site, name)
            print(f"Uninstalled {name}")
        else:
            put(site, name, version or NEWEST.get(name.lower(), "1.0.0"))
            print(f"Installed {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
