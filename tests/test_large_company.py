"""The made-up retail business (tools/testbed/large_company.py): the same rows for the same seed, every key
joins, each scale's size, the deliberate problems documented. Small runs in the quick suite; medium is
behind the `medium` marker (SWISSARMYBENCH_TEST_MEDIUM=1) and large's timing behind `slow`
(SWISSARMYBENCH_TEST_SLOW=1)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import duckdb
import pytest
from tools.testbed import large_company as lc


def _made(scale: str = "small", seed: int = lc.SEED) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    lc.generate(connection, scale, seed)
    return connection


@pytest.fixture(scope="module")
def small() -> duckdb.DuckDBPyConnection:
    return _made()


def _fingerprint(connection: duckdb.DuckDBPyConnection) -> dict[str, tuple[int, int]]:
    out = {}
    for table in lc.TABLES:
        row = connection.execute(f"SELECT count(*), sum(hash(t)) FROM {table} t").fetchone()
        assert row is not None
        out[table] = (int(row[0]), int(row[1] or 0))
    return out


def test_the_same_seed_makes_the_same_rows_and_another_seed_others(small: duckdb.DuckDBPyConnection) -> None:
    again = _fingerprint(_made())
    assert _fingerprint(small) == again
    other = _fingerprint(_made(seed=7))
    assert other["orders"] != again["orders"] and other["order_lines"] != again["order_lines"]


def _check_keys(connection: duckdb.DuckDBPyConnection) -> None:
    for child, column, parent, key in lc.FOREIGN_KEYS:
        orphans = connection.execute(
            f"SELECT count(*) FROM {child} c WHERE c.{column} IS NOT NULL "
            f"AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{key} = c.{column})"
        ).fetchone()
        assert orphans == (0,), (child, column, parent)
    for table, keys in lc.KEYS.items():
        columns = ", ".join(keys)
        row = connection.execute(
            f"SELECT count(*) - (SELECT count(*) FROM (SELECT DISTINCT {columns} FROM {table})) FROM {table}"
        ).fetchone()
        assert row is not None
        if table == "orders":  # the orders sent twice, and only those
            twice = connection.execute(
                "SELECT count(*) FROM data_quality_issues WHERE problem = 'duplicate row'"
            ).fetchone()
            assert row == twice
        else:
            assert row == (0,), table


def test_every_foreign_key_joins_and_every_key_is_unique(small: duckdb.DuckDBPyConnection) -> None:
    _check_keys(small)


def test_small_is_about_ten_thousand_order_lines(small: duckdb.DuckDBPyConnection) -> None:
    rows = {t: small.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in lc.TABLES}  # type: ignore[index]
    assert 9_500 <= rows["order_lines"] <= 10_500
    assert rows["regions"] == 8 and rows["categories"] == 20
    assert all(rows[t] > 0 for t in lc.TABLES), rows


def test_the_data_is_skewed_seasonal_and_has_its_nulls(small: duckdb.DuckDBPyConnection) -> None:
    # the top tenth of customers place more than a third of the orders
    share = small.execute(
        "WITH c AS (SELECT customer_id, count(*) n FROM orders GROUP BY 1), "
        "r AS (SELECT n, ntile(10) OVER (ORDER BY n DESC) d FROM c) "
        "SELECT sum(n) FILTER (WHERE d = 1) / sum(n) FROM r"
    ).fetchone()
    assert share is not None and share[0] > 0.33
    by_month = dict(small.execute("SELECT month(order_date), count(*) FROM orders GROUP BY 1").fetchall())
    assert by_month[12] > 1.5 * by_month[2]
    nulls = small.execute(
        "SELECT (SELECT count(*) FROM customers WHERE phone IS NULL), "
        "(SELECT count(*) FROM orders WHERE employee_id IS NULL AND channel = 'Online'), "
        "(SELECT count(*) FROM orders WHERE employee_id IS NULL AND channel <> 'Online'), "
        "(SELECT count(*) FROM shipments WHERE delivered_on IS NULL), "
        "(SELECT count(*) FROM support_tickets WHERE closed_at IS NULL)"
    ).fetchone()
    assert nulls is not None and nulls[0] > 0 and nulls[1] > 0 and nulls[2] == 0
    assert nulls[3] > 0 and nulls[4] > 0
    late = small.execute("SELECT count(*) FROM shipments WHERE status = 'Late'").fetchone()
    assert late is not None and late[0] > 0


def test_the_deliberate_problems_are_documented_and_findable(small: duckdb.DuckDBPyConnection) -> None:
    kinds = dict(small.execute("SELECT problem, count(*) FROM data_quality_issues GROUP BY 1").fetchall())
    assert kinds == {
        "duplicate row": 3,
        "late-arriving row": 3,
        "negative quantity": 3,
        "delivered before shipped": 3,
        "duplicate customer": 3,
    }
    negative = small.execute("SELECT count(*) FROM order_lines WHERE quantity < 0").fetchone()
    assert negative == (3,)
    late = small.execute(
        "SELECT count(DISTINCT order_id) FROM orders WHERE loaded_at > order_date + INTERVAL 30 DAY"
    ).fetchone()
    assert late == (3,)
    early = small.execute("SELECT count(*) FROM shipments WHERE delivered_on < shipped_on").fetchone()
    assert early == (3,)
    twins = small.execute(
        "SELECT count(*) FROM (SELECT email FROM customers GROUP BY email HAVING count(*) > 1)"
    ).fetchone()
    assert twins == (3,)


def test_build_writes_parquet_outside_the_repository_only(tmp_path: Path) -> None:
    report = lc.build(tmp_path / "out", "small", duckdb_file=True)
    assert report.rows["order_lines"] > 9_000
    for table in lc.TABLES:
        assert (tmp_path / "out" / f"{table}.parquet").is_file()
    back = duckdb.connect(str(tmp_path / "out" / "larkfield.duckdb"), read_only=True)
    assert back.execute("SELECT count(*) FROM order_lines").fetchone() == (report.rows["order_lines"],)
    read = (
        duckdb.connect().execute(f"SELECT count(*) FROM '{tmp_path / 'out' / 'orders.parquet'}'").fetchone()
    )
    assert read == (report.rows["orders"],)
    with pytest.raises(ValueError, match="outside the repository"):
        lc.build(lc.REPOSITORY / "build" / "larkfield", "small")


def test_the_command_line_writes_and_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert lc.main(["--scale", "small", "--out", str(tmp_path)]) == 0
    said = capsys.readouterr().out
    assert "order_lines" in said and "small written to" in said
    assert lc.main(["--scale", "small", "--out", str(lc.REPOSITORY / "x")]) == 2


@pytest.mark.medium
@pytest.mark.skipif(
    not os.environ.get("SWISSARMYBENCH_TEST_MEDIUM"), reason="set SWISSARMYBENCH_TEST_MEDIUM=1"
)
def test_medium_is_about_a_million_order_lines_and_its_keys_join() -> None:
    connection = _made("medium")
    lines = connection.execute("SELECT count(*) FROM order_lines").fetchone()
    assert lines is not None and 950_000 <= lines[0] <= 1_050_000
    _check_keys(connection)


@pytest.mark.slow
@pytest.mark.skipif(not os.environ.get("SWISSARMYBENCH_TEST_SLOW"), reason="set SWISSARMYBENCH_TEST_SLOW=1")
def test_large_builds_ten_million_order_lines_in_under_a_minute(tmp_path: Path) -> None:
    started = time.perf_counter()
    report = lc.build(tmp_path, "large")
    took = time.perf_counter() - started
    assert 9_500_000 <= report.rows["order_lines"] <= 10_500_000
    assert took < 60, took
