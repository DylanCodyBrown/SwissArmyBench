"""The Blazor front end's C# style (the csharp-clean-code skill, enforced by blazor/.editorconfig and
Directory.Build.props): `dotnet format --verify-no-changes` finds nothing to change, and no C# or Razor
file holds a token. Skipped where the .NET SDK is not installed."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

BLAZOR = Path(__file__).resolve().parents[1] / "blazor"
PROJECT = BLAZOR / "SwissArmyBench.Web" / "SwissArmyBench.Web.csproj"


def _dotnet() -> str | None:
    found = shutil.which("dotnet")
    own = Path.home() / ".dotnet" / "dotnet"
    return found or (str(own) if own.is_file() else None)


@pytest.mark.skipif(_dotnet() is None, reason="the .NET SDK is not installed here")
def test_dotnet_format_finds_nothing_to_change() -> None:
    env = os.environ | {"DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    done = subprocess.run(  # noqa: S603 (our own command line)
        [str(_dotnet()), "format", str(PROJECT), "--verify-no-changes"],
        cwd=BLAZOR,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_no_token_or_secret_in_the_blazor_code() -> None:
    sources = [
        p for p in (BLAZOR / "SwissArmyBench.Web").rglob("*") if p.suffix in (".cs", ".razor", ".html")
    ]
    sources += list((BLAZOR / "interop").glob("*.js"))
    assert sources
    for path in sources:
        if "obj" in path.parts or "bin" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        # The page reads the token from its own address at run time (shell.js) and never keeps it.
        assert "Bearer " not in text or path.name == "shell.js", path
