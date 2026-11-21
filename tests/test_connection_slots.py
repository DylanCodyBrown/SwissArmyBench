"""The slots rule (domain/connection_slots.py): per connection a total and an agent's share, a line first
come first served within a priority, the words, the limits, and the SQL formatted for reading."""

from __future__ import annotations

import pytest

from swissarmybench.domain import connection_slots as rules
from swissarmybench.domain.connection_slots import Board, Limits, LimitsError, Ticket
from swissarmybench.domain.query_text import format_sql


def ticket(n: int, caller: str = "user", conn: str = "Warehouse", priority: int = 0) -> Ticket:
    return Ticket(id=f"t{n}", connection=conn, caller=caller, priority=priority)


def test_defaults_and_validation() -> None:
    assert Limits() == Limits(8, 4, 120)
    assert rules.check_limits(None) == Limits()
    assert rules.check_limits({"total": "16", "agent": 6}) == Limits(16, 6, 120)
    assert rules.check_limits({"total": 2}) == Limits(2, 2, 120)  # the agent's share follows down
    assert rules.check_limits({"agent": 0}) == Limits(8, 0, 120)
    for bad in (
        {"total": 0},
        {"total": 65},
        {"total": 4, "agent": 5},
        {"wait": 0},
        {"total": "x"},
        {"foo": 1},
    ):
        with pytest.raises(LimitsError):
            rules.check_limits(bad)
    assert rules.limits_of_header({"total": 999}) == Limits()  # a bad hand edit reads as the defaults
    assert Limits().header() == {}
    assert Limits(12, 4, 60).header() == {"total": 12, "wait": 60}


def test_total_and_agent_share() -> None:
    board = Board(lambda name: Limits(3, 2, 120))
    started = []
    for n in range(3):
        started += board.ask(ticket(n, "agent"), now=0)
    assert [t.id for t in started] == ["t0", "t1"]  # the agent's share is 2
    started = board.ask(ticket(10, "user"), now=1)
    assert [t.id for t in started] == ["t10"]  # the user goes ahead of the agent's waiting one
    assert board.ask(ticket(11, "user"), now=2) == []  # the total is full
    status = board.status("warehouse")
    assert (status["running"], status["waiting"], status["agent_running"]) == (3, 2, 2)
    assert status["words"] == "Running 3 of 3 · 2 waiting"
    assert status["full_words"] == "Running 3 of 3 · 2 waiting · agent 2 of 2"
    # The agent's t0 ends: the agent's waiting t2 is first in line and takes it (FIFO).
    _, started = board.leave("t0", now=3)
    assert [t.id for t in started] == ["t2"]
    _, started = board.leave("t10", now=4)
    assert [t.id for t in started] == ["t11"]


def test_fifo_place_and_priority() -> None:
    board = Board(lambda name: Limits(1, 1, 120))
    board.ask(ticket(0), now=0)
    board.ask(ticket(1, "background", priority=rules.BACKGROUND), now=1)
    board.ask(ticket(2), now=2)
    board.ask(ticket(3), now=3)
    places = {t.id: board.place(t) for t in board.tickets()}
    assert places == {"t0": None, "t2": 1, "t3": 2, "t1": 3}  # the user's interactive work goes first
    _, started = board.leave("t2", now=4, outcome="cancelled")  # a cancel frees its place in line
    assert started == [] and board.place(board.get("t3")) == 1  # type: ignore[arg-type]
    assert board.finished[0].outcome == "cancelled"


def test_lines_are_per_connection_and_leases_expire() -> None:
    board = Board(lambda name: Limits(1, 1, 30))
    assert board.ask(ticket(0, conn="Warehouse"), now=0)
    assert board.ask(ticket(1, conn="Lake"), now=0)
    kernel = Ticket(id="k", connection="Lake", kernel="abc")
    board.ask(kernel, now=0)
    board.renew("k", now=0, seconds=15)
    assert board.expired(10) == [] and board.expired(16) == [kernel]
    assert board.overdue(29) == [] and board.overdue(30) == [kernel]
    assert board.leave("nope", now=1) == (None, [])


def test_words() -> None:
    assert rules.waiting_words("Warehouse", 3, 8) == "Waiting: 3rd in line for Warehouse (8 queries running)"
    assert rules.kernel_words("Warehouse", 2) == "Waiting for a slot on Warehouse (2nd in line)"
    assert [rules.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "13th",
        "21st",
        "22nd",
        "101st",
    ]
    assert rules.waiting_words("Lake", 1, 1).endswith("(1 query running)")
    assert rules.gave_up_words("Warehouse", 120, 8).startswith("Waited 2 minutes for a slot on Warehouse")
    assert rules.status_words(0, 0, 8) == "Running 0 of 8"


def test_ticket_json_keeps_sql_for_the_user_only() -> None:
    t = Ticket(id="a", connection="Warehouse", sql="SELECT 1", dialect="duckdb")
    assert "sql" not in t.to_json(5)
    assert t.to_json(5, with_sql=True)["sql"] == "SELECT 1"


def test_format_sql() -> None:
    long = (
        "select order_id, customer_id, amount, region from orders o join customers c on o.customer_id = c.id "
        "where amount > 100 and region = '${REGION}' order by amount desc"
    )
    pretty = format_sql(long, "postgres")
    lines = pretty.splitlines()
    assert lines[0] == "SELECT" and "FROM orders AS o" in lines and "'${REGION}'" in pretty
    assert any(line.startswith("WHERE") for line in lines) and len(lines) > 6
    assert format_sql("selec from where (", "duckdb") == "selec from where ("  # left as it came
    assert format_sql("EVALUATE 'Sales'", "dax") == "EVALUATE 'Sales'"  # DAX as written
    assert "TOP 5" in format_sql("select top 5 * from dbo.Sales", "sqlserver")
