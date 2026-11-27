"""Build Swiss Army Bench: one wheel that is both the client and the server.

    python build.py            # the front end (release build), then the wheel in dist/

The front end (blazor/, served at /blazor/) is built by blazor/publish.py (its npm packages, then `dotnet
publish`) and copied into the wheel as swissarmybench/web_blazor/. It needs Node.js and the .NET SDK (the
version blazor/global.json names): without them build.py stops and says so, since a wheel without its pages
would open nothing.

The wheel is one package with two installs:

    uv pip install swissarmybench-<version>-py3-none-any.whl              # the client, any environment
    uv tool install "swissarmybench-<version>-py3-none-any.whl[server]"   # the server, once per machine

The client is standard library only (`import swissarmybench as sab`), so it never touches a project's own
packages; the server's `swissarmybench` command runs the app. The front end ships inside the wheel
(pyproject.toml names src/swissarmybench/web_blazor as an artifact), so it is built first.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
NPM = "npm.cmd" if sys.platform == "win32" else "npm"


def project_version() -> str:
    """The version in pyproject.toml: the wheel and the installers carry it."""
    with (HERE / "pyproject.toml").open("rb") as file:
        version: str = tomllib.load(file)["project"]["version"]
    return version


def run(command: list[str], cwd: Path) -> None:
    print(f"> {' '.join(command)}  (in {cwd.relative_to(HERE) or '.'})", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def build_blazor() -> None:
    """The Blazor front end into src/swissarmybench/web_blazor (the wheel's); without dotnet, said plainly."""
    target = HERE / "src" / "swissarmybench" / "web_blazor"
    shutil.rmtree(target, ignore_errors=True)
    sys.path.insert(0, str(HERE / "blazor"))
    import publish  # type: ignore[import-not-found]  # blazor/publish.py

    if publish.dotnet() is None:
        sys.exit("The .NET SDK is not on PATH: the front end (blazor/) cannot be built, nor the wheel.")
    print("> blazor/publish.py", flush=True)
    shutil.copytree(publish.publish(), target)
    if not (target / "index.html").is_file():
        sys.exit("The Blazor build wrote no index.html.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--skip-npm-install", action="store_true", help="Use blazor/node_modules as it is.")
    args = parser.parse_args()

    if not args.skip_npm_install:
        run([NPM, "ci"], HERE / "blazor")
    build_blazor()

    version = project_version()
    run(["uv", "build", "--wheel", "--out-dir", "dist"], HERE)
    wheel = HERE / "dist" / f"swissarmybench-{version}-py3-none-any.whl"
    if not wheel.is_file():
        sys.exit(f"uv build wrote no {wheel.name}.")
    print(f"\nBuilt {wheel.relative_to(HERE)}")
    # The installers, with this version written in: they go in the release beside the wheel.
    for name in ("install.sh", "install.ps1"):
        text = (HERE / "installer" / name).read_text(encoding="utf-8").replace("__VERSION__", version)
        (HERE / "dist" / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote dist/{name}")

    print("\nInstall the server once per machine, and the client wherever you push from:")
    print(f'  uv tool install --force "{wheel}[server]"')
    print(f'  uv pip install "{wheel}"')


if __name__ == "__main__":
    main()
