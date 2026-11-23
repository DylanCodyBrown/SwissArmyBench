"""A blade's runs through the app (services/blade_runs.py), with stand-ins for the child process, the slots
and the Connections page's count: the rules that were the composition root's closures. Made-up names only."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from swissarmybench.domain.blades import Blade
from swissarmybench.services.blade_runs import BladeRuns


class Refused(RuntimeError):
    pass


class Store:
    def __init__(self, *blades: Blade) -> None:
        self._blades = {b.name: b for b in blades}

    def get(self, name: str) -> Blade:
        return self._blades[name]

    def saved_secrets(self, blade: Any) -> dict[str, str]:
        return {}


class Kept:
    def defined(self) -> list[str]:
        return ["REGION", "API_URL"]

    def kept_of(self, vault: str) -> dict[str, str]:
        return {"warehouse-password": "WAREHOUSE_PASSWORD"}

    def mapping(self, blade: Blade) -> dict[str, str]:
        return {"WAREHOUSE_PASSWORD": "warehouse-password", "REGION_2": "region"}


class Fake:
    """The child process, the gate and the count, each noting what it was asked."""

    def __init__(self, answer: dict[str, Any] | None = None, fails: Exception | None = None) -> None:
        self.answer = answer if answer is not None else {"ok": True}
        self.fails = fails
        self.jobs: list[tuple[dict[str, Any], float]] = []
        self.gated: list[tuple[Any, ...]] = []
        self.recorded: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.kept: list[tuple[str, list[dict[str, str]]]] = []
        self.events: list[tuple[Any, ...]] = []

    def payload(self, blade: Blade, mode: str, typed: dict[str, str], extra: Any = None) -> dict[str, Any]:
        return {"label": blade.name, "mode": mode, "typed": typed, "extra": extra}

    async def run(self, job: dict[str, Any], timeout: float, report: Any = None) -> dict[str, Any]:
        self.jobs.append((job, timeout))
        if report is not None:
            report("started", None, None)
        if self.fails is not None:
            raise self.fails
        return self.answer

    async def run_streaming(
        self, job: dict[str, Any], timeout: float, on_output: Any, started: Any, report: Any = None
    ) -> dict[str, Any]:
        self.jobs.append((job, timeout))
        on_output("stdout", "3 rows\n")
        return self.answer

    async def gate(self, *asked: Any) -> dict[str, Any]:
        self.gated.append(asked[:5])
        found: dict[str, Any] = await asked[5]()
        return found

    def record(self, *args: Any, **more: Any) -> None:
        self.recorded.append((args, more))

    async def keep_names(self, vault: str, names: list[dict[str, str]]) -> bool:
        self.kept.append((vault, names))
        return True


def runs(fake: Fake, *blades: Blade, load: dict[str, Any] | None = None) -> BladeRuns:
    return BladeRuns(
        Store(*blades),
        Kept(),
        payload=fake.payload,
        load_payload=lambda: load,
        run=fake.run,
        run_streaming=fake.run_streaming,
        failed=Refused,
        gate=fake.gate,
        record=fake.record,
        keep_names=fake.keep_names,
        report=lambda *event: fake.events.append(event),
        run_file=lambda name: f"/made-up/tmp/{name}",
        blade_seconds=30.0,
        vault_seconds=7.0,
    )


WAREHOUSE = Blade("Warehouse", "sql", code='import os\npassword = secret("WAREHOUSE_PASSWORD")\n')


def test_a_run_passes_the_connections_gate_and_is_counted_with_what_the_server_said() -> None:
    fake = Fake({"ok": True, "about": {"driver": "made-up 1.0"}})
    answer = asyncio.run(runs(fake, WAREHOUSE).run_blade(WAREHOUSE, "query", {}, {"sql": "SELECT 1"}))
    assert answer["ok"] is True
    assert fake.gated == [("Warehouse", "sql", WAREHOUSE.dialect, "query", {"sql": "SELECT 1"})]
    job, timeout = fake.jobs[0]
    assert timeout == 30.0 and job["yours"] == ["API_URL", "REGION"]  # the user's own names, sorted
    assert fake.recorded == [(("Warehouse", "query"), {"ok": True, "about": {"driver": "made-up 1.0"}})]
    assert fake.events == [("blade", "started", None, None)]  # a catalog load is told as "catalog"


def test_a_catalog_load_is_reported_as_one_and_a_failure_is_counted_then_raised() -> None:
    fake = Fake(fails=Refused("The server refused the sign-in."))
    with pytest.raises(Refused):
        asyncio.run(runs(fake, WAREHOUSE).run_blade(WAREHOUSE, "catalog", {}))
    assert fake.events == [("catalog", "started", None, None)]
    assert fake.recorded == [
        (("Warehouse", "catalog"), {"ok": False, "error": "The server refused the sign-in."})
    ]


def test_an_answer_with_no_about_is_counted_without_one() -> None:
    fake = Fake({"rows": 3, "about": "not a mapping"})
    asyncio.run(runs(fake, WAREHOUSE).run_blade(WAREHOUSE, "read", {}))
    assert fake.recorded == [(("Warehouse", "read"), {"ok": True, "about": None})]


def test_a_vault_that_loads_every_secret_gets_its_names_as_given_out_here() -> None:
    vault = Blade("Team vault", "vault")
    job: dict[str, Any] = {
        "vaults": [
            {"label": "Team vault", "every": True, "mapping": {"REGION_2": "the-region"}},
            {"label": "Other vault", "mapping": {"A": "a"}},  # only its own entries: left as it is
            {"label": "Gone vault", "every": True, "mapping": {}},  # no such blade: its kept names only
        ]
    }
    runs(Fake(), vault).given_out(job)
    first, second, third = job["vaults"]
    assert job["yours"] == ["API_URL", "REGION"]
    assert first["kept"] == {"warehouse-password": "WAREHOUSE_PASSWORD"}
    # The remembered names, the vault's own entries winning.
    assert first["mapping"] == {"WAREHOUSE_PASSWORD": "warehouse-password", "REGION_2": "the-region"}
    assert second == {"label": "Other vault", "mapping": {"A": "a"}}
    assert third["mapping"] == {} and "kept" in third


def test_the_ides_run_is_streamed_under_a_file_name_of_its_own_and_counted_as_a_test() -> None:
    fake = Fake({"ok": False, "failed": "NameError: name 'rows' is not defined"})
    heard: list[tuple[str, str]] = []
    asyncio.run(
        runs(fake, WAREHOUSE).stream_blade(
            WAREHOUSE, {}, "Warehouse.py", lambda kind, text: heard.append((kind, text)), lambda stop: None
        )
    )
    assert fake.jobs[0][0]["filename"] == "/made-up/tmp/Warehouse.py" and fake.jobs[0][0]["mode"] == "run"
    assert heard == [("stdout", "3 rows\n")] and fake.gated == []  # the IDE's Run takes no slot
    assert fake.recorded == [
        (("Warehouse", "test"), {"ok": False, "error": "NameError: name 'rows' is not defined"})
    ]


def test_a_kernels_vaults_give_their_values_and_keep_the_names_they_listed() -> None:
    fake = Fake(
        {
            "values": {"WAREHOUSE_PASSWORD": "made-up"},
            "names": {"Team vault": ["warehouse-password"], "Broken": "not a list"},
            "problems": ["Other vault: sign in first."],
        }
    )
    values, problems = asyncio.run(runs(fake, load={"mode": "load", "vaults": []}).vault_environment())
    assert values == {"WAREHOUSE_PASSWORD": "made-up"} and problems == ["Other vault: sign in first."]
    assert fake.jobs[0][1] == 7.0 and [vault for vault, _ in fake.kept] == ["Team vault"]
    assert [n["secret"] for n in fake.kept[0][1]] == ["warehouse-password"]


def test_no_vault_reads_nothing_and_a_slow_one_says_the_kernel_started_without_it() -> None:
    assert asyncio.run(runs(Fake()).vault_environment()) == ({}, [])
    slow = Fake(fails=Refused("The vaults did not finish in time."))
    values, problems = asyncio.run(runs(slow, load={"mode": "load"}).vault_environment())
    assert values == {} and problems == [
        "Reading the vaults took over 7 seconds: this kernel started without them."
    ]
    other = Fake(fails=Refused("Team vault: sign in first."))
    assert asyncio.run(runs(other, load={"mode": "load"}).vault_environment()) == (
        {},
        ["Team vault: sign in first."],
    )


def test_a_scripts_vault_variables_and_a_vault_that_is_gone() -> None:
    vault = Blade("Team vault", "vault")
    fake = Fake({"values": {"WAREHOUSE_PASSWORD": "made-up"}, "problems": []})
    wanted = {"Team vault": {"WAREHOUSE_PASSWORD": "warehouse-password"}}
    assert asyncio.run(runs(fake, vault).vault_values(wanted)) == ({"WAREHOUSE_PASSWORD": "made-up"}, [])
    assert fake.jobs[0][0]["mode"] == "load" and fake.jobs[0][1] == 7.0
    values, problems = asyncio.run(runs(Fake()).vault_values(wanted))  # no such vault here
    assert values == {} and len(problems) == 1
    failing = Fake(fails=Refused("Team vault: sign in first."))
    assert asyncio.run(runs(failing, vault).vault_values(wanted)) == ({}, ["Team vault: sign in first."])


def test_a_blades_secret_names_and_its_certificate_variables() -> None:
    code = 'import os\nverify = os.environ.get("WAREHOUSE_CA", r"C:\\made-up\\ca.pem")\n'
    made = runs(Fake(), WAREHOUSE, Blade("Trino", "sql", code=code))
    assert made.secrets_of("Warehouse") == WAREHOUSE.secrets and made.secrets_of("Gone") is None
    assert made.files_of("Trino") == ["WAREHOUSE_CA"] and made.files_of("Gone") == []
