"""Build Swiss Army Bench: one wheel that is both the client and the server.

    python build.py            # the page (release build), then the wheel in dist/

The Blazor front end (blazor/, served at /blazor/ beside the classic page) is built too when the .NET SDK is
on PATH (blazor/publish.py), and copied into the wheel as swissarmybench/web_blazor/; without dotnet the wheel
is built without it, and build.py says so.

The wheel is one package with two installs:

    uv pip install swissarmybench-<version>-py3-none-any.whl              # the client, any environment
    uv tool install "swissarmybench-<version>-py3-none-any.whl[server]"   # the server, once per machine

The client is standard library only (`import swissarmybench as sab`), so it never touches a project's own
packages; the server's `swissarmybench` command runs the grid. The page ships inside the wheel
(pyproject.toml force-includes web/static), so it is built first, without source maps.
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
    """The version in pyproject.toml: the wheel, the extension and the installers all carry it."""
    with (HERE / "pyproject.toml").open("rb") as file:
        version: str = tomllib.load(file)["project"]["version"]
    return version


def run(command: list[str], cwd: Path) -> None:
    print(f"> {' '.join(command)}  (in {cwd.relative_to(HERE) or '.'})", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def build_blazor() -> None:
    """The Blazor front end into src/swissarmybench/web_blazor (the wheel's), or said plainly why not."""
    target = HERE / "src" / "swissarmybench" / "web_blazor"
    shutil.rmtree(target, ignore_errors=True)
    sys.path.insert(0, str(HERE / "blazor"))
    import publish  # type: ignore[import-not-found]  # blazor/publish.py

    if publish.dotnet() is None:
        print("The .NET SDK is not on PATH: the wheel is built without the Blazor front end.", flush=True)
        return
    print("> blazor/publish.py", flush=True)
    shutil.copytree(publish.publish(), target)
    if not (target / "index.html").is_file():
        sys.exit("The Blazor build wrote no index.html.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--skip-npm-install", action="store_true", help="Use web/node_modules as it is.")
    args = parser.parse_args()

    web = HERE / "web"
    if not args.skip_npm_install:
        run([NPM, "ci"], web)
    shutil.rmtree(web / "static" / "build", ignore_errors=True)
    run([NPM, "run", "build:release"], web)
    if not (web / "static" / "build" / "main.js").is_file():
        sys.exit("The page build wrote no web/static/build/main.js.")

    build_blazor()

    version = project_version()
    run(["uv", "build", "--wheel", "--out-dir", "dist"], HERE)
    wheel = HERE / "dist" / f"swissarmybench-{version}-py3-none-any.whl"
    if not wheel.is_file():
        sys.exit(f"uv build wrote no {wheel.name}.")
    print(f"\nBuilt {wheel.relative_to(HERE)}")
    # Each extension (extensions/<id>/, Plans/editions.plan.md): its own wheel, on the base's version.
    for folder in sorted(p.parent for p in (HERE / "extensions").glob("*/pyproject.toml")):
        with (folder / "pyproject.toml").open("rb") as file:
            project = tomllib.load(file)["project"]
        if project["version"] != version:
            sys.exit(f"{project['name']} is {project['version']}: an extension carries the base's {version}.")
        run(["uv", "build", "--wheel", "--out-dir", str(HERE / "dist")], folder)
        made = HERE / "dist" / f"{project['name'].replace('-', '_')}-{version}-py3-none-any.whl"
        if not made.is_file():
            sys.exit(f"uv build wrote no {made.name}.")
        print(f"Built {made.relative_to(HERE)}")
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
