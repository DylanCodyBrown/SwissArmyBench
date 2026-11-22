"""A workbook cell's value has one rule written twice: sab_excel.cell_value (the workbook builder) and
adapter.sheet_value (a connection's write into a sheet). Both files stand alone, so neither imports the other;
this test holds the two copies to the same answers (the craft review of 2026-11-22 found them apart on numpy's
scalars and pandas' missing time). Made-up values only."""

from __future__ import annotations

import datetime as dt
import decimal
import enum
import uuid
from typing import Any

import pytest

from swissarmybench import sab_excel
from swissarmybench.adapters import adapter


class Colour(enum.Enum):
    RED = "red"


ZONE = dt.timezone(dt.timedelta(hours=2))
SAMPLES: list[Any] = [
    None,
    True,
    False,
    0,
    -7,
    10**15 - 1,
    10**15,
    -(10**15),
    12345678901234567890,
    0.0,
    1.5,
    -2.25e-9,
    float("nan"),
    float("inf"),
    float("-inf"),
    "",
    "plain",
    "=SUM(A1:A2)",
    "+1",
    "@name",
    "tab\tand\nline",
    "bell\x07",
    "_x0041_ kept literal",
    decimal.Decimal("12.50"),
    decimal.Decimal("0.123456789012345"),
    decimal.Decimal("1234567890.1234567890"),
    decimal.Decimal("NaN"),
    decimal.Decimal("Infinity"),
    dt.date(2024, 2, 29),
    dt.date(1900, 2, 28),
    dt.date(1900, 3, 1),
    dt.date(1, 1, 1),
    dt.datetime(2024, 2, 29, 13, 45, 10, 250000),
    dt.datetime(1899, 12, 31, 23, 59),
    dt.datetime(2024, 2, 29, 13, 45, tzinfo=dt.UTC),
    dt.datetime(2024, 2, 29, 13, 45, tzinfo=ZONE),
    dt.time(9, 30),
    dt.time(9, 30, tzinfo=dt.UTC),
    dt.timedelta(hours=26, seconds=5),
    b"bytes",
    bytearray(b"more"),
    [1, "two", None],
    (1, 2),
    [],
    {"id": 7, "when": dt.date(2024, 1, 1), "lines": [{"n": 1}]},
    {},
    {1, 2}.__class__(),
    uuid.UUID("12345678-1234-5678-1234-567812345678"),
    Colour.RED,
    1 + 2j,
    range(3),
]


def _numpy_samples() -> list[Any]:
    np = pytest.importorskip("numpy")
    return [
        np.int64(7),
        np.int64(10**15),
        np.int32(-3),
        np.uint8(200),
        np.float64(1.5),
        np.float32(0.5),
        np.float64("nan"),
        np.float64("inf"),
        np.bool_(True),
        np.str_("text"),
        np.datetime64("2024-02-29T13:45:10"),
        np.datetime64("1899-12-31"),
        np.datetime64("NaT", "s"),
        np.timedelta64(90, "m"),
        np.array([1, 2, 3]),
        np.array(5),
    ]


def _pandas_samples() -> list[Any]:
    pd = pytest.importorskip("pandas")
    return [
        pd.Timestamp("2024-02-29 13:45:10"),
        pd.Timestamp("1899-12-31"),
        pd.Timestamp("2024-02-29 13:45", tz="Europe/Paris"),
        pd.NaT,
        pd.Timedelta(minutes=90),
        pd.NA,
    ]


def _same(value: Any) -> None:
    ours = sab_excel.cell_value(value)
    theirs = adapter.sheet_value(value)
    # by type and words, so nan equals nan and 1 never equals True nor 1.0
    assert (type(ours[0]), repr(ours[0]), ours[1]) == (type(theirs[0]), repr(theirs[0]), theirs[1]), repr(
        value
    )


@pytest.mark.parametrize("value", SAMPLES, ids=lambda v: f"{type(v).__name__}:{str(v)[:24]!r}")
def test_both_copies_hold_a_value_the_same(value: Any) -> None:
    _same(value)


def test_both_copies_hold_numpys_scalars_the_same() -> None:
    for value in _numpy_samples():
        _same(value)
    np = pytest.importorskip("numpy")
    assert sab_excel.cell_value(np.int64(7)) == (7, False)  # a number, never its text
    assert adapter.sheet_value(np.int64(7)) == (7, False)
    assert adapter.sheet_value(np.float64("nan")) == ("nan", True)


def test_both_copies_hold_pandas_values_the_same() -> None:
    for value in _pandas_samples():
        _same(value)
    pd = pytest.importorskip("pandas")
    assert adapter.sheet_value(pd.NaT) == (None, False)  # a missing time is a blank cell


def test_the_limits_are_the_same_numbers() -> None:
    assert sab_excel.EXACT_DIGITS == adapter.EXCEL_DIGITS
    assert sab_excel.FIRST_DAY == adapter.EXCEL_FIRST_DAY
    assert sab_excel._UNWRITABLE.pattern == adapter._UNWRITABLE.pattern
    text = "bell\x07 _x0041_ \x00"
    assert sab_excel.cell_text(text) == adapter._sheet_text(text)
