"""A made-up reinsurer's cessions, for the Accounting extension's tests and screenshots.

Made-up Re takes shares of three made-up cedants' business under three made-up treaties. Every name and
number here is invented.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

CEDANTS = ["Ashgrove Mutual", "Brindle Assurance", "Quillon Insurance"]
TREATIES = ["Property QS 2026", "Casualty XL 2026", "Marine QS 2026"]
PERIODS = ["2026-Q1", "2026-Q2"]


def cessions() -> pd.DataFrame:
    """One row per cedant, treaty and period: the premium ceded, the claims, the commission."""
    rows = []
    for c, cedant in enumerate(CEDANTS):
        for t, treaty in enumerate(TREATIES):
            for p, period in enumerate(PERIODS):
                premium = 10_000.0 * (c + 1) + 2_500.0 * t + 750.0 * p
                claims = round(premium * (0.35 + 0.1 * ((c + t + p) % 5)), 2)
                rows.append(
                    {
                        "cedant": cedant,
                        "treaty": treaty,
                        "period": period,
                        "premium": premium,
                        "claims": claims,
                        "commission": round(premium * 0.2, 2),
                        "loss_ratio": round(claims / premium, 4),
                    }
                )
    return pd.DataFrame(rows)


def statements() -> pd.DataFrame:
    """One row per cedant and period: the statement's header."""
    return pd.DataFrame(
        [
            {"cedant": cedant, "period": period, "address": f"{10 + i} Made-up Street", "currency": "USD"}
            for i, cedant in enumerate(CEDANTS)
            for period in PERIODS
        ]
    )


def lines() -> pd.DataFrame:
    """A statement's lines: each treaty's premium, claims and commission, with its booking date."""
    frame = cessions()
    frame["booked"] = [date(2026, 3 if p == "2026-Q1" else 6, 28) for p in frame["period"]]
    frame["balance"] = frame["premium"] - frame["claims"] - frame["commission"]
    return frame[["cedant", "period", "treaty", "booked", "premium", "claims", "commission", "balance"]]
