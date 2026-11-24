"""Missing packages found and installed by themselves before a connection or blade runs (the owner,
2026-11-24, on a key vault's "No module named 'azure'": "the app is still not auto detecting missing packages
and installing them")."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from swissarmybench.adapters import blade_run
from swissarmybench.domain.connection_slots import AGENT
from swissarmybench.server import blade_runner
from swissarmybench.services.blade_runs import BladeRuns
from swissarmybench.services.connection_slots import Caller, calling_as

LACKING = ("azure", "madeupthing")  # what this Python stands in as lacking
VAULT = "from azure.identity import DefaultAzureCredential\nfrom azure.keyvault.secrets import SecretClient\n"


def test_what_the_code_imports_and_this_python_lacks_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWISSARMYBENCH_AUTO_INSTALL", "on")
    asked: list[list[str]] = []

    async def install(pips: list[str]) -> tuple[int | None, str]:
        asked.append(pips)
        return 0, ""

    monkeypatch.setattr(blade_runner, "install_packages", install)
    monkeypatch.setattr(blade_run, "installed", lambda dotted: dotted.split(".")[0] not in LACKING)
    code = VAULT + "import json\nimport duckdb\nimport madeupthing\n"
    got = asyncio.run(blade_runner.install_missing([code, VAULT]))
    # Known names only, each once; the standard library, what is here and a guessed name left alone.
    assert asked == [["azure-identity", "azure-keyvault-secrets"]]
    assert got == ["azure-identity", "azure-keyvault-secrets"]


def test_nothing_missing_or_a_failed_install_says_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWISSARMYBENCH_AUTO_INSTALL", "on")

    async def failing(pips: list[str]) -> tuple[int | None, str]:
        return 1, "no network"

    monkeypatch.setattr(blade_runner, "install_packages", failing)
    monkeypatch.setattr(blade_run, "installed", lambda dotted: dotted.split(".")[0] not in LACKING)
    assert asyncio.run(blade_runner.install_missing(["import duckdb\n"])) == []
    assert asyncio.run(blade_runner.install_missing([VAULT])) == []  # the run then says Install now


def test_off_installs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWISSARMYBENCH_AUTO_INSTALL", "off")

    async def never(pips: list[str]) -> tuple[int | None, str]:
        raise AssertionError("installed while off")

    monkeypatch.setattr(blade_runner, "install_packages", never)
    assert asyncio.run(blade_runner.install_missing([VAULT])) == []


def _runs(seen: list[list[str]]) -> BladeRuns:
    async def install_missing(codes: list[str]) -> list[str]:
        seen.append(codes)
        return []

    unused: Any = None
    return BladeRuns(
        unused,
        unused,
        payload=unused,
        load_payload=unused,
        run=unused,
        run_streaming=unused,
        failed=RuntimeError,
        gate=unused,
        record=unused,
        keep_names=unused,
        report=unused,
        run_file=unused,
        blade_seconds=1,
        vault_seconds=1,
        install_missing=install_missing,
    )


def test_a_users_run_installs_its_code_and_its_vaults_first_the_agents_waits_for_install_now() -> None:
    seen: list[list[str]] = []
    runs = _runs(seen)
    job = {"code": "import pyodbc\n", "vaults": [{"code": VAULT}]}
    asyncio.run(runs.ready(job))
    assert seen == [["import pyodbc\n", VAULT]]
    with calling_as(Caller(AGENT, "Agent")):
        asyncio.run(runs.ready(job))
    assert len(seen) == 1  # the agent's install is the user's Allow (Install now)
