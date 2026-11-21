"""The gate (services/connection_slots.py) with a slow stand-in connection: 12 queries on a limit of 8, the
agent's 4 -> never more than 8 at once, never more than 4 of the agent's, the line kept in order, a Cancel
frees its place, a timeout gives up with Try again, a killed kernel's lease expires. Made-up names only."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from swissarmybench.domain import connection_slots as rules
from swissarmybench.domain.connection_slots import Limits
from swissarmybench.services.connection_slots import Caller, ConnectionSlots, calling_as
from swissarmybench.services.workspace import TimedOut


class Live:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.sent.append(message)


class Audit:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str, Any]] = []

    def write(self, actor: str, action: str, dataset: Any = None, **more: Any) -> None:
        self.entries.append((actor, action, dataset))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def gate(limits: Limits | None = None, clock: Any = None) -> ConnectionSlots:
    limits = limits or Limits(8, 4, 120)
    return ConnectionSlots(Live(), Audit(), lambda name: limits, clock=clock or (lambda: 0.0))  # type: ignore[arg-type]


def test_twelve_queries_on_eight_slots_and_the_agents_four() -> None:
    async def scenario() -> None:
        slots = gate(clock=asyncio.get_event_loop().time)
        running: list[str] = []
        most = {"all": 0, "agent": 0}
        order: list[str] = []
        release = asyncio.Event()

        async def query(name: str, role: str) -> str:
            async def work() -> str:
                running.append(role)
                order.append(name)
                most["all"] = max(most["all"], len(running))
                most["agent"] = max(most["agent"], running.count("agent"))
                await release.wait()
                await asyncio.sleep(0.01)
                running.remove(role)
                return name

            with calling_as(Caller(role, "The agent" if role == "agent" else "You")):
                return await slots.run("Warehouse", work, kind="query", sql="SELECT 1")

        names = [(f"a{i}", "agent") for i in range(6)] + [(f"u{i}", "user") for i in range(6)]
        tasks = [asyncio.create_task(query(n, r)) for n, r in names]
        await asyncio.sleep(0.05)
        status = slots.board.status("Warehouse")
        assert (status["running"], status["agent_running"], status["waiting"]) == (8, 4, 4)
        assert status["full_words"] == "Running 8 of 8 · 4 waiting · agent 4 of 4"
        listed = slots.queries("Warehouse")["queries"]
        waiting = [q for q in listed if q["state"] == "waiting"]
        assert [q["place"] for q in waiting] == [1, 2, 3, 4]
        assert waiting[0]["words"] == "Waiting: 1st in line for Warehouse (8 queries running)"
        assert all("sql" not in q for q in listed)  # never the SQL in the list (the agent reads it too)
        release.set()
        done = await asyncio.gather(*tasks)
        assert sorted(done) == sorted(n for n, _ in names)
        assert most == {"all": 8, "agent": 4}
        # First come, first served within each share: the agent's in the order they asked, the user's too.
        assert [n for n in order if n.startswith("a")] == [f"a{i}" for i in range(6)]
        assert [n for n in order if n.startswith("u")] == [f"u{i}" for i in range(6)]
        assert slots.board.status("Warehouse")["running"] == 0
        assert len(slots.board.finished) == 12 and all(f.outcome == "ok" for f in slots.board.finished)

    asyncio.run(scenario())


def test_cancel_frees_a_place_and_stops_a_running_one() -> None:
    async def scenario() -> None:
        slots = gate(Limits(1, 1, 120), clock=asyncio.get_event_loop().time)
        forever = asyncio.Event()

        async def slow() -> str:
            await forever.wait()
            return "never"

        first = asyncio.create_task(slots.run("Lake", slow))
        second = asyncio.create_task(slots.run("Lake", slow))
        await asyncio.sleep(0.02)
        ids = {q["state"]: q["id"] for q in slots.queries()["queries"]}
        assert set(ids) == {"running", "waiting"}
        await slots.cancel(ids["waiting"])
        with pytest.raises(TimedOut, match="Cancelled"):
            await second
        await slots.cancel(ids["running"])  # the work's own task is cancelled (a child process killed)
        with pytest.raises(TimedOut, match="Cancelled"):
            await first
        assert slots.board.tickets() == []
        assert [f.outcome for f in slots.board.finished] == ["cancelled", "cancelled"]

    asyncio.run(scenario())


def test_a_wait_past_its_limit_gives_up_with_try_again_and_an_error_frees_the_slot() -> None:
    async def scenario() -> None:
        slots = gate(Limits(1, 1, 1), clock=asyncio.get_event_loop().time)
        hold = asyncio.Event()

        async def slow() -> str:
            await hold.wait()
            return "ok"

        async def broken() -> str:
            raise RuntimeError("made-up driver error")

        first = asyncio.create_task(slots.run("Warehouse", slow))
        await asyncio.sleep(0.01)
        with pytest.raises(TimedOut) as said:
            await slots.run("Warehouse", slow)
        assert said.value.fixes == [{"label": "Try again", "action": "try_again"}]
        assert "for a slot on Warehouse" in str(said.value)
        hold.set()
        await first
        with pytest.raises(RuntimeError):
            await slots.run("Warehouse", broken)
        assert slots.board.tickets() == []  # the error gave its slot back
        assert slots.board.finished[0].outcome == "failed"

    asyncio.run(scenario())


def test_a_kernels_lease_expires_when_it_stops_renewing() -> None:
    async def scenario() -> None:
        clock = Clock()
        slots = gate(Limits(1, 1, 120), clock=clock)
        slots.kernel_caller = lambda kernel: Caller("agent", "The agent", kernel=kernel)
        got = slots.acquire({"connection": "Warehouse", "sql": "SELECT 1"}, "k1")
        assert got["state"] == "running"
        waiting = slots.acquire({"connection": "Warehouse"}, "k2")
        assert (
            waiting["state"] == "waiting"
            and waiting["words"] == "Waiting for a slot on Warehouse (1st in line)"
        )
        assert slots.board.get(got["ticket"]).caller == "agent"  # type: ignore[union-attr]
        clock.now += 10
        assert slots.renew(waiting["ticket"])["state"] == "waiting"  # k2 keeps renewing
        clock.now += rules.LEASE_SECONDS - 5  # k1 died: it renewed nothing
        assert slots.expire() == [got["ticket"]]
        assert slots.renew(waiting["ticket"])["state"] == "running"
        assert slots.renew(got["ticket"])["state"] == "ended"
        slots.release(waiting["ticket"], {"outcome": "ok", "rows": 3})
        assert slots.board.finished[0].ticket.rows == 3

    asyncio.run(scenario())


def test_the_agent_waiting_long_is_a_session_entry() -> None:
    async def scenario() -> None:
        clock = Clock()
        slots = gate(Limits(1, 1, 120), clock=clock)
        hold = asyncio.Event()

        async def slow() -> str:
            await hold.wait()
            return "ok"

        first = asyncio.create_task(slots.run("Warehouse", slow))
        await asyncio.sleep(0)
        with calling_as(Caller("agent", "The agent")):
            second = asyncio.create_task(slots.run("Warehouse", slow))
        await asyncio.sleep(0.01)
        clock.now += 5
        hold.set()
        await asyncio.gather(first, second)
        entries = slots._audit.entries  # type: ignore[attr-defined]
        assert ("agent", "connection_slot_waited", "Warehouse") in entries

    asyncio.run(scenario())


def test_outside_a_workbench_kernel_or_with_no_app_there_is_no_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    from swissarmybench.client import connection_slot

    monkeypatch.delenv("SWISSARMYBENCH_KERNEL", raising=False)
    ran = []
    with connection_slot.slot("Warehouse", "query", sql="SELECT 1"):
        ran.append("plain Python")
    monkeypatch.setenv("SWISSARMYBENCH_KERNEL", "abc123")
    monkeypatch.setattr(connection_slot, "_read_info", lambda: None)  # no app answering
    with connection_slot.slot("Warehouse", "query"):
        ran.append("no app")
    assert ran == ["plain Python", "no app"]
    assert connection_slot.kernel_headers() == {"X-Kernel": "abc123", "X-Sab-Client": "kernel-abc123"}
