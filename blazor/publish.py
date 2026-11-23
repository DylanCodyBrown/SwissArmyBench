"""Build the Blazor front end into blazor/publish/wwwroot: what the server serves at /blazor/ in a checkout,
and what build.py copies into the wheel as swissarmybench/web_blazor/.

    python blazor/publish.py            the interop bundles (node), then `dotnet publish -c Release`
    python blazor/publish.py --debug    the same, a Debug build (quicker; source maps)

Needs the .NET SDK on PATH (the version blazor/global.json names) and web/node_modules (`npm ci` in web/),
whose packages the interop files bundle (SAB_NODE_MODULES names another folder). Standard library only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "SwissArmyBench.Web"
OUT = HERE / "publish"
# web/node_modules, or the folder SAB_NODE_MODULES names (a worktree may share another checkout's).
NODE_MODULES = Path(os.environ.get("SAB_NODE_MODULES") or HERE.parent / "web" / "node_modules")


def dotnet() -> str | None:
    """The dotnet command on PATH, else the user's own install (~/.dotnet: Microsoft's install script's)."""
    found = shutil.which("dotnet")
    if found:
        return found
    own = Path.home() / ".dotnet" / ("dotnet.exe" if sys.platform == "win32" else "dotnet")
    return str(own) if own.is_file() else None


def publish(debug: bool = False, node_modules: Path = NODE_MODULES) -> Path:
    """The interop bundles, then the app published; the folder the server serves (publish/wwwroot)."""
    command = dotnet()
    if command is None:
        raise RuntimeError("The .NET SDK is not on PATH: the Blazor front end is not built.")
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is not installed: the Blazor front end's interop files are not built.")
    subprocess.run([node, str(HERE / "interop" / "build.mjs"), str(node_modules)], check=True)  # noqa: S603
    if OUT.exists():
        shutil.rmtree(OUT)
    configuration = "Debug" if debug else "Release"
    subprocess.run(  # noqa: S603 (our own command line)
        [command, "publish", str(PROJECT), "-c", configuration, "-o", str(OUT), "--nologo"],
        check=True,
        cwd=HERE,
    )
    return OUT / "wwwroot"


if __name__ == "__main__":
    print(publish(debug="--debug" in sys.argv))
