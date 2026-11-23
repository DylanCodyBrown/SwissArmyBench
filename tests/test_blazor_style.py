"""The Blazor front end's C# style (the csharp-clean-code skill, enforced by blazor/.editorconfig and
Directory.Build.props): `dotnet format --verify-no-changes` finds nothing to change in the app or its tests,
the bUnit tests pass (blazor/SwissArmyBench.Web.Tests: the shared components, the state services' subscribe
and unsubscribe, the Grids ribbon's logic), and no C# or Razor file holds a token. Skipped where the .NET
SDK is not installed."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

BLAZOR = Path(__file__).resolve().parents[1] / "blazor"
PROJECT = BLAZOR / "SwissArmyBench.Web" / "SwissArmyBench.Web.csproj"
TESTS = BLAZOR / "SwissArmyBench.Web.Tests" / "SwissArmyBench.Web.Tests.csproj"
ENV = os.environ | {"DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}


def _dotnet() -> str | None:
    found = shutil.which("dotnet")
    own = Path.home() / ".dotnet" / "dotnet"
    return found or (str(own) if own.is_file() else None)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (our own command line)
        [str(_dotnet()), *args],
        cwd=BLAZOR,
        capture_output=True,
        text=True,
        timeout=900,
        env=ENV,
        check=False,
    )


@pytest.mark.skipif(_dotnet() is None, reason="the .NET SDK is not installed here")
@pytest.mark.parametrize("project", [PROJECT, TESTS], ids=["app", "tests"])
def test_dotnet_format_finds_nothing_to_change(project: Path) -> None:
    done = _run("format", str(project), "--verify-no-changes")
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.skipif(_dotnet() is None, reason="the .NET SDK is not installed here")
def test_the_bunit_tests_pass() -> None:
    done = _run("test", "--project", str(TESTS))
    assert done.returncode == 0, done.stdout[-6000:] + done.stderr[-3000:]


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
