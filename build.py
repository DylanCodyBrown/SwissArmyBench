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
import base64
import hashlib
import shutil
import subprocess
import sys
import tomllib
import zipfile
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


# The packages the extensions were before they were built in (the owner, 2026-11-27). An install of 0.0.42 or
# older updates with its own, older, updater, which asks uv for each installed extension's wheel at the new
# version from this version's GitHub release (`--with <address>`), and fails when one is not there. So each
# release still carries a wheel of each name: EMPTY (no code, no entry point), needing only the app at this
# version. The app never asks for them; an update made by this version or a newer one leaves them out.
TRANSITION_PACKAGES = (
    "swissarmybench_accounting",
    "swissarmybench_copilot",
    "swissarmybench_git",
    "swissarmybench_powerapps",
    "swissarmybench_powerbi",
    "swissarmybench_streamlit",
)


def transition_wheels(version: str) -> list[Path]:
    """An empty wheel for each package an extension used to be, in dist/ (standard library only)."""
    made: list[Path] = []
    for package in TRANSITION_PACKAGES:
        info = f"{package}-{version}.dist-info"
        files = {
            f"{info}/METADATA": (
                f"Metadata-Version: 2.1\nName: {package.replace('_', '-')}\nVersion: {version}\n"
                "Summary: Built into Swiss Army Bench: this package is empty and only lets an older "
                "install update.\nRequires-Python: >=3.12\n"
                f"Requires-Dist: swissarmybench[server]=={version}\n"
            ),
            f"{info}/WHEEL": (
                "Wheel-Version: 1.0\nGenerator: swissarmybench build.py\nRoot-Is-Purelib: true\n"
                "Tag: py3-none-any\n"
            ),
        }
        record = "".join(
            f"{name},sha256={_urlsafe_sha256(text.encode())},{len(text.encode())}\n"
            for name, text in files.items()
        )
        files[f"{info}/RECORD"] = record + f"{info}/RECORD,,\n"
        wheel = HERE / "dist" / f"{package}-{version}-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, text in files.items():
                archive.writestr(zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0)), text)
        made.append(wheel)
    return made


def _urlsafe_sha256(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


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
    for made in transition_wheels(version):
        print(f"Built {made.relative_to(HERE)} (empty: an older install's update asks for it)")
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
