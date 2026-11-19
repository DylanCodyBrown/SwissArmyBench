"""`sab.analyze` in Python: the same contracts, the same checker and the same functions as the page and the
agent (one source, design principle 8.3); a result's cards on the board when the app runs. Made-up data."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from starlette.testclient import TestClient

import swissarmybench as sab
from swissarmybench import stats
from swissarmybench.client import analyze_client
from swissarmybench.client.push_client import ServerNotRunningError
from swissarmybench.domain import analysis_contracts as C
from tests.analyze_data import orders
from tests.conftest import AUTH, grid_id, make_client, push

LOCAL = [c.id for c in C.CONTRACTS if not c.two_tables]


@pytest.fixture
def no_app(monkeypatch: pytest.MonkeyPatch) -> None:
    def call(*args: Any, **kwargs: Any) -> Any:
        raise ServerNotRunningError("not running")

    monkeypatch.setattr(analyze_client, "_call", call)


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with make_client(tmp_path) as client:

        def call(method: str, path: str, body: bytes | None = None, content_type: str = "") -> Any:
            response = client.request(
                method, path, content=body, headers=AUTH | {"Content-Type": "application/json"}
            )
            if response.status_code != 200:
                raise RuntimeError(f"Swiss Army Bench refused ({response.status_code}): {response.text}")
            return response.json()

        monkeypatch.setattr(analyze_client, "_call", call)
        yield client


def frame() -> pd.DataFrame:
    made: pd.DataFrame = orders().to_pandas()
    return made


def test_the_contract_and_the_sample_are_the_pages_own(no_app: None) -> None:
    contract = sab.analyze.contract("benford")
    assert contract == C.contract("benford").to_json() | {"sample": C.sample("benford")}
    assert [c["id"] for c in sab.analyze.contracts()["contracts"]] == [c.id for c in C.CONTRACTS]
    sample = sab.analyze.sample("forecast")
    assert list(sample.columns) == ["order_month", "amount"] and len(sample) == 24
    assert str(sample["order_month"].dtype).startswith("datetime64")
    assert list(sab.analyze.sample("tie_out", other=True).columns) == ["region", "amount"]
    with pytest.raises(ValueError, match="No analysis 'astrology'"):
        sab.analyze.contract("astrology")
    with pytest.raises(AttributeError, match=r"sab\.analyze has no 'astrology'"):
        sab.analyze.astrology(frame())
    assert "benford" in dir(sab.analyze) and str(sab.analyze.benford.__doc__).startswith(
        "Do the first digits"
    )


@pytest.mark.parametrize("analysis", LOCAL)
def test_every_analysis_runs_on_its_own_sample_in_python(no_app: None, analysis: str) -> None:
    result = getattr(sab.analyze, analysis)(sab.analyze.sample(analysis))
    assert isinstance(result, dict) and result


def test_an_analysis_picks_its_columns_as_the_page_does_and_gives_stats_numbers(no_app: None) -> None:
    data = frame()
    assert sab.analyze.benford(data) == stats.fit_test(data, columns=["amount"], expected="benford")
    assert sab.analyze.odds(data) == stats.odds(
        data, column="region", outcome={"column": "late", "values": ["yes"]}
    )
    explicit = sab.analyze.outliers(data, column="units", method="iqr")
    assert explicit == stats.outliers(data, column="units", look="amount", method="iqr")
    ahead = sab.analyze.forecast(data, horizon=3)
    assert len(ahead["forecast"]) == 3
    tried = sab.analyze.whatif(data, **{"value:units": 4})
    assert tried["values"]["units"] == 4.0 and tried["prediction"]


def test_a_table_that_does_not_fit_says_what_is_missing_and_how_to_make_it_fit(no_app: None) -> None:
    data = pd.DataFrame({"amount": [f"{100 + (i * 37) % 900}" for i in range(40)]})
    with pytest.raises(
        ValueError, match=r"Nothing in data fits amounts.* Make it fit: Read amount as numbers"
    ):
        sab.analyze.benford(data)
    with pytest.raises(ValueError, match="Region is a text column: amounts needs a number column"):
        sab.analyze.benford(frame(), column="region")
    with pytest.raises(ValueError, match="nope is not a column of this table"):
        sab.analyze.benford(frame(), column="nope")
    with pytest.raises(TypeError, match=r"sab\.analyze\.benford has no 'colour': it takes column, digits"):
        sab.analyze.benford(frame(), colour="red")
    with pytest.raises(TypeError, match="runs on two open tables"):
        sab.analyze.tie_out(frame(), other=frame())


def test_check_ranks_the_analyses_for_a_dataframe_with_the_same_checker(no_app: None) -> None:
    checked = sab.analyze.check(frame())
    assert [e["analysis"] for e in checked["top"]] == ["time_series", "forecast", "predictors"]
    one = sab.analyze.check(frame(), "benford")
    assert one["ready"] is True and one["columns"] == {"column": "amount"}
    text = pd.DataFrame({"amount": [f"{100 + (i * 37) % 900}" for i in range(40)]})
    fixes = sab.analyze.check(text, "benford")["fixes"]
    assert fixes[0]["kind"] == "text_to_number" and fixes[0]["steps"][0]["kind"] == "sql"


def test_with_the_app_running_a_dataframes_result_lands_on_the_board(app: TestClient) -> None:
    result = sab.analyze.benford(frame(), name="orders")
    cards = app.get("/cards", headers=AUTH).json()["cards"]
    assert [c["kind"] for c in cards] == ["note", "plotly"]
    assert cards[0]["origin"] == "Python" and cards[0]["dataset"] == "orders"
    assert cards[0]["analysis"]["analysis"] == "benford" and cards[0]["analysis"]["columns"] == {
        "column": "amount"
    }
    run = cards[0]["analysis"]["run"]
    assert "markdown" in app.get(f"/analyze/runs/{run}/math", headers=AUTH).json()
    assert result["results"][0]["column"] == "amount"
    sab.analyze.odds(frame(), board=False)
    assert len(app.get("/cards", headers=AUTH).json()["cards"]) == 2  # kept off the board


def test_an_open_table_by_its_name_runs_in_the_app_two_tables_too(app: TestClient) -> None:
    grid_id(push(app, "orders", orders()))
    ledger = orders().select(["region", "amount"]).slice(0, 100)
    grid_id(push(app, "ledger", ledger))
    result = sab.analyze.benford("orders")
    assert result["results"][0]["column"] == "amount"
    tied = sab.analyze.tie_out("orders", other=app.get("/grids", headers=AUTH).json()["grids"][1]["grid"])
    assert tied["left_name"] == "orders" and tied["right_name"] == "ledger"
    assert sab.analyze.check("orders")["dataset"] == "orders"
    with pytest.raises(RuntimeError, match="Nothing in ledger fits dates"):
        sab.analyze.time_series("ledger")


def test_a_result_that_is_not_one_is_refused_by_the_board(app: TestClient) -> None:
    refused = app.post(
        "/analyze/land", json={"analysis": "benford", "dataset": "x", "result": {"nonsense": 1}}, headers=AUTH
    )
    assert refused.status_code == 400 and refused.json()["error"].startswith(
        "That is not a result of Benford"
    )
    assert app.get("/cards", headers=AUTH).json()["cards"] == []
