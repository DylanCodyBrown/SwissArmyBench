"""An analysis result as the Analyze board's cards (the owner, 2026-11-19: "Every analysis should
automatically push to the analysis visualization area"; design principle 8.7).

Each result reads as a report: a note (a title, the verdict in bold, a table of the key rows, the cautions)
and a Plotly chart beside it, sized to share one row (the note five columns, the chart seven). Charts name
the theme's colours ("theme:accent"), which the page resolves when it draws, so they look right in every
theme. The same cards whoever ran it: the user's Run, the agent's analyze_run, `sab.analyze` in Python.

Also here, for the cards' actions: a result's rows for Open as grid, and its hand-offs to the next tool
(design principle 8.8: Show these rows, Regression with these, Test together...). Standard library only.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

Card = dict[str, Any]
BASE_LAYOUT: dict[str, Any] = {"font": {"size": 12}, "hovermode": "closest"}


def fmt(v: Any) -> str:
    """A value as the page writes it: whole numbers with thousands' commas, others to two places."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        if not math.isfinite(v):
            return "∞" if v > 0 else "-∞" if v < 0 else ""
        if v.is_integer() and abs(v) < 1e15:
            return f"{int(v):,}"
        text = f"{v:,.2f}".rstrip("0").rstrip(".")
        return text if text not in ("-0", "") else "0"
    return str(v)


# A column whose numbers are labels, not amounts: a year or an identifier reads without separators
# ("2018", "100234"), never "2,018". By its name's words, or whole numbers that all read as years.
LABEL_WORDS = frozenset({"year", "yr", "fy", "id", "key", "code", "zip", "postcode", "sku"})


def _words(name: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [w.lower() for w in re.split(r"[^A-Za-z0-9]+", spaced) if w]


def is_label_column(column: Any, low: Any = None, high: Any = None) -> bool:
    """True for a year or an identifier: its name says so (fiscal_year, CustomerKey, order_id), or its
    lowest and highest are whole numbers between 1800 and 2200 (years)."""
    if any(w in LABEL_WORDS or w.endswith("year") for w in _words(str(column or ""))):
        return True

    def yearish(v: Any) -> bool:
        return (
            isinstance(v, (int, float))
            and not isinstance(v, bool)
            and float(v).is_integer()
            and 1800 <= v <= 2200
        )

    return yearish(low) and yearish(high)


def plain(v: Any) -> str:
    """A label's number as its digits: 2018, not 2,018 (anything else as fmt writes it)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return fmt(v)
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return str(v) if isinstance(v, int) else fmt(v).replace(",", "")


def pct(v: float | None) -> str:
    if v is None:
        return ""
    return f"{100 * v:.{1 if v < 0.1 else 0}f}%"


def p_text(p: float) -> str:
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


def signed(v: float) -> str:
    return f"{'+' if v > 0 else ''}{fmt(v)}"


def _cell(v: Any) -> str:
    return fmt(v).replace("|", "\\|").replace("\n", " ")


def md_table(head: list[str], rows: list[list[Any]], right: list[bool] | None = None) -> str:
    right = right or []
    rule = ["---:" if i < len(right) and right[i] else "---" for i in range(len(head))]
    lines = [f"| {' | '.join(head)} |", f"| {' | '.join(rule)} |"]
    lines += [f"| {' | '.join(_cell(c) for c in r)} |" for r in rows]
    return "\n".join(lines)


def pair(title: str, markdown: str, figure: dict[str, Any] | None) -> list[Card]:
    """A note and its chart, sized to sit side by side: the note five columns, the chart seven."""
    lines = markdown.count("\n") + 1
    h = max(7, min(18, math.ceil((lines * 23 + 60) / 52)))
    cards: list[Card] = [
        {"kind": "note", "title": title, "body": markdown, "size": {"w": 5 if figure else 12, "h": h}}
    ]
    if figure is not None:
        cards.append(
            {
                "kind": "plotly",
                "title": f"{title} (chart)",
                "body": json.dumps(figure),
                "size": {"w": 7, "h": h},
            }
        )
    return cards


def _log_ticks(values: list[float]) -> dict[str, Any]:
    finite = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v) and v > 0]
    low = min([1.0, *finite]) / 1.15
    high = max([1.0, *finite]) * 1.15
    nice = [0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1, 1.5, 2, 3, 5, 7, 10, 20, 50, 100, 200, 500]
    ticks = [v for v in nice if low <= v <= high]
    return {
        "range": [math.log10(low), math.log10(high)],
        "tickvals": ticks,
        "ticktext": [str(t) for t in ticks],
        "minor": {"showgrid": False},
    }


# ===== the fit test =====


def fit_cards(r: dict[str, Any], expected: str, pair_names: list[str] | None = None) -> list[Card]:
    what = f"{pair_names[0]} and {pair_names[1]}" if pair_names else str(r.get("column") or "")
    benford = expected.startswith("benford")
    title = f"{'First digits' if benford else 'Fit test'}: {what}"
    lines = [
        f"# {title}",
        f"**{r['verdict']}**",
        "",
        md_table(
            ["Chi-square", "Degrees of freedom", "p-value", "Rows", r["effect_name"]],
            [
                [
                    fmt(r["statistic"]),
                    fmt(r["df"]),
                    p_text(r["p"]),
                    fmt(r["n"]),
                    f"{fmt(r['effect_size'])} ({r['effect']})",
                ]
            ],
            [True] * 5,
        ),
    ]
    if r.get("conformity"):
        lines += [
            "",
            f"Benford's law: **{r['conformity']}** (mean absolute deviation of the digit shares "
            f"{fmt(r.get('conformity_mad') or 0)}, Nigrini's ranges).",
        ]
    figure: dict[str, Any] | None = None
    categories = r.get("categories")
    cells = r.get("cells")
    if categories:
        far = sorted(categories, key=lambda c: -abs(c["residual"]))[:8]
        lines += [
            "",
            "#### Furthest from expected",
            md_table(
                ["Value", "Seen", "Expected", "Off by"],
                [[c["value"], c["observed"], c["expected"], signed(c["residual"])] for c in far],
                [False, True, True, True],
            ),
        ]
        shown = categories if benford else categories[:30]
        x = [c["value"] for c in shown]
        figure = {
            "data": [
                {
                    "type": "bar",
                    "name": "Seen",
                    "x": x,
                    "y": [c["observed"] for c in shown],
                    "marker": {
                        "color": [
                            "theme:accent" if abs(c["residual"]) >= 2 else "theme:border-strong"
                            for c in shown
                        ]
                    },
                },
                {
                    "type": "scatter",
                    "mode": "lines+markers",
                    "name": "Expected",
                    "x": x,
                    "y": [c["expected"] for c in shown],
                    "line": {"color": "theme:fg", "width": 2},
                    "marker": {"size": 5},
                },
            ],
            "layout": BASE_LAYOUT
            | {
                "xaxis": {"type": "category", "title": {"text": "First digits" if benford else what}},
                "yaxis": {"title": {"text": "Rows"}},
                "legend": {"orientation": "h", "y": 1.08},
                "bargap": 0.25,
            },
        }
    elif cells and pair_names:
        top = cells[:10]
        lines += [
            "",
            "#### The combinations furthest from independence",
            md_table(
                [pair_names[0], pair_names[1], "Seen", "Expected", "Off by"],
                [[c["a"], c["b"], c["observed"], c["expected"], signed(c["residual"])] for c in top],
                [False, False, True, True, True],
            ),
        ]
        bars = list(reversed(top))
        figure = {
            "data": [
                {
                    "type": "bar",
                    "orientation": "h",
                    "x": [c["residual"] for c in bars],
                    "y": [f"{c['a']} · {c['b']}" for c in bars],
                    "marker": {"color": ["theme:accent" if c["residual"] > 0 else "theme:ok" for c in bars]},
                    "hovertemplate": "%{y}: %{x:.2f}<extra></extra>",
                }
            ],
            "layout": BASE_LAYOUT
            | {
                "xaxis": {"title": {"text": "Seen against expected (standardized)"}, "zeroline": True},
                "yaxis": {"automargin": True},
            },
        }
    if r.get("warnings"):
        lines += ["", *(f"> {w}" for w in r["warnings"])]
    return pair(title, "\n".join(lines), figure)


# ===== odds =====


def odds_cards(r: dict[str, Any]) -> list[Card]:
    values = r["values"]
    if not r.get("outcome"):
        top = values[:15]
        markdown = "\n".join(
            [
                f"# How often each {r['column']} shows up",
                f"**{fmt(len(values))} values over {fmt(r['rows'])} rows.**"
                + (f" {r['column']} is a number, shown in equal-sized ranges." if r.get("bucketed") else ""),
                "",
                md_table(
                    [r["column"], "Rows", "Share", "1 in"],
                    [[v["value"], v["rows"], pct(v["share"]), fmt(v["one_in"])] for v in top],
                    [False, True, True, True],
                ),
            ]
        )
        bars = list(reversed(top))
        return pair(
            f"Odds: {r['column']}",
            markdown,
            {
                "data": [
                    {
                        "type": "bar",
                        "orientation": "h",
                        "x": [v["share"] for v in bars],
                        "y": [v["value"] for v in bars],
                        "marker": {"color": "theme:accent"},
                        "hovertemplate": "%{y}: %{x:.1%}<extra></extra>",
                    }
                ],
                "layout": BASE_LAYOUT
                | {
                    "xaxis": {"title": {"text": "Share of rows"}, "tickformat": ".0%"},
                    "yaxis": {"automargin": True, "type": "category"},
                },
            },
        )
    outcome = r["outcome"]
    top = values[0] if values else None
    clear_values = [v for v in values if v.get("clear")]
    lines = [
        f"# Odds of {outcome} by {r['column']}",
        f"{outcome}: **{pct(r.get('rate'))}** of {fmt(r['rows'])} rows. "
        f"{(r.get('together') or {}).get('verdict', '')}",
    ]
    if top and top.get("clear"):
        lines += [
            "",
            f"**{top['value']}: {outcome} {pct(top.get('rate'))} of the time, against "
            f"{pct(top.get('rest_rate'))} "
            f"elsewhere: {fmt(top.get('odds_ratio'))} times the odds.**",
        ]

    def bold(v: dict[str, Any]) -> str:
        mark = "**" if v.get("clear") else ""
        return f"{mark}{v['value']}{mark}{' *' if v.get('small') else ''}"

    lines += [
        "",
        md_table(
            [r["column"], "Rows", f"{outcome} rate", "Elsewhere", "Odds ratio", "95% range"],
            [
                [
                    bold(v),
                    v["rows"],
                    pct(v.get("rate")),
                    pct(v.get("rest_rate")),
                    fmt(v.get("odds_ratio")),
                    f"{fmt(v.get('low'))} to {fmt(v.get('high'))}",
                ]
                for v in values[:15]
            ],
            [False, True, True, True, True, True],
        ),
        "",
        "> Bold values are clearly different: their range leaves out 1."
        + (" * fewer than 30 rows: rough." if any(v.get("small") for v in values) else "")
        + ("" if clear_values else " No value is clearly different."),
    ]
    shown = list(reversed(values[:20]))

    def colour(v: dict[str, Any]) -> str:
        if not v.get("clear"):
            return "theme:muted"
        return "theme:accent" if (v.get("odds_ratio") or 1) > 1 else "theme:ok"

    figure = {
        "data": [
            {
                "type": "scatter",
                "mode": "markers",
                "x": [v.get("odds_ratio") for v in shown],
                "y": [v["value"] for v in shown],
                "error_x": {
                    "type": "data",
                    "symmetric": False,
                    "array": [(v.get("high") or 0) - (v.get("odds_ratio") or 0) for v in shown],
                    "arrayminus": [(v.get("odds_ratio") or 0) - (v.get("low") or 0) for v in shown],
                    "color": "theme:muted",
                    "thickness": 1.5,
                    "width": 4,
                },
                "marker": {"size": 10, "color": [colour(v) for v in shown]},
                "hovertemplate": "%{y}: %{x:.2f} times the odds<extra></extra>",
            }
        ],
        "layout": BASE_LAYOUT
        | {
            "xaxis": {
                "type": "log",
                "title": {"text": f"Odds ratio for {outcome} (log scale; 1 means no difference)"},
                **_log_ticks([x for v in shown for x in (v.get("low") or 1, v.get("high") or 1)]),
            },
            "yaxis": {"automargin": True, "type": "category"},
            "shapes": [
                {
                    "type": "line",
                    "x0": 1,
                    "x1": 1,
                    "yref": "paper",
                    "y0": 0,
                    "y1": 1,
                    "line": {"color": "theme:fg", "width": 1, "dash": "dot"},
                }
            ],
            "showlegend": False,
        },
    }
    return pair(f"Odds of {outcome} by {r['column']}", "\n".join(lines), figure)


# ===== find predictors =====

_STRENGTH_COLOUR = {
    "strong": "theme:accent",
    "moderate": "theme:warn",
    "weak": "theme:muted",
    "none": "theme:border",
}


def predictors_cards(r: dict[str, Any]) -> list[Card]:
    candidates = r["candidates"]
    worth = [c for c in candidates if c["strength"] in ("strong", "moderate")]
    target = r["target"]
    names = ", ".join(c["column"] for c in worth)
    lines = [
        f"# What goes with {target}",
        f"**{names} {'goes' if len(worth) == 1 else 'go'} with {target}.**"
        if worth
        else f"**No column goes clearly with {target}.**",
        "",
        md_table(
            ["Column", "Strength", "Cramér's V", "Correlation", "Note"],
            [
                [
                    c["column"],
                    c["strength"],
                    fmt(c["v"]),
                    "" if c.get("correlation") is None else fmt(c["correlation"]),
                    f"says the same as {c['same_as']}" if c.get("same_as") else (c.get("note") or ""),
                ]
                for c in candidates[:15]
            ],
            [False, False, True, True, False],
        ),
    ]
    if r.get("redundant"):
        keep = ", ".join(f"{p['keep']} (not {p['drop']})" for p in r["redundant"])
        lines += ["", f"For a regression keep one of each pair: {keep}."]
    if r.get("skipped"):
        lines += ["", f"> Skipped: {'; '.join(f'{s["column"]} ({s["reason"]})' for s in r['skipped'])}."]
    bars = list(reversed(candidates[:15]))
    figure = {
        "data": [
            {
                "type": "bar",
                "orientation": "h",
                "x": [c["v"] for c in bars],
                "y": [f"{c['column']} (= {c['same_as']})" if c.get("same_as") else c["column"] for c in bars],
                "marker": {
                    "color": [_STRENGTH_COLOUR.get(c["strength"], "theme:muted") for c in bars],
                    "opacity": [0.45 if c.get("same_as") else 1 for c in bars],
                },
                "hovertemplate": "%{y}: Cramér's V %{x:.2f}<extra></extra>",
            }
        ],
        "layout": BASE_LAYOUT
        | {
            "xaxis": {
                "title": {"text": f"How much each tells about {target} (Cramér's V)"},
                "range": [0, max([0.35, *(c["v"] for c in bars)]) * 1.05],
            },
            "yaxis": {"automargin": True, "type": "category"},
            "shapes": [
                {
                    "type": "line",
                    "x0": x,
                    "x1": x,
                    "yref": "paper",
                    "y0": 0,
                    "y1": 1,
                    "line": {"color": "theme:border-strong", "width": 1, "dash": "dot"},
                }
                for x in (0.1, 0.2, 0.3)
            ],
            "showlegend": False,
        },
    }
    return pair(f"Predictors of {target}", "\n".join(lines), figure)


# ===== outliers =====

_METHOD_WORDS = {
    "robust": "distance from the median",
    "iqr": "quartile fences (Tukey)",
    "zscore": "mean and standard deviation",
}


def amount_cards(r: dict[str, Any], column: str, method: str) -> list[Card]:
    total = r["low"] + r["high"]
    by = r.get("by")
    lines = [
        f"# Unusual values of {column}{f' within each {by}' if by else ''}",
        f"**{fmt(total)} of {fmt(r['rows'])} values look out of place: {fmt(r['high'])} high, "
        f"{fmt(r['low'])} low.**"
        if total
        else f"**Nothing stands out among {fmt(r['rows'])} values.**",
        "",
        f"Judged by {_METHOD_WORDS.get(method, method)}.",
    ]
    fences = r.get("fences") or []
    one = fences[0] if fences and not by else None
    if one and one.get("low_fence") is not None:
        lines.append(
            f"Usual range: **{fmt(one['low_fence'])} to {fmt(one['high_fence'])}** (median "
            f"{fmt(one['median'])})."
        )
    if by and fences:
        lines += [
            "",
            f"#### {fmt(r['groups_flagged'])} of {fmt(r['groups'])} {by} values have outliers",
            md_table(
                [by, "Values", "Usual range", "Low", "High"],
                [
                    [
                        f.get("group") or "(blank)",
                        f["rows"],
                        f"{fmt(f['low_fence'])} to {fmt(f['high_fence'])}",
                        f["low"],
                        f["high"],
                    ]
                    for f in fences[:10]
                ],
                [False, True, False, True, True],
            ),
        ]
    outliers = r.get("outliers") or []
    if outliers:
        lines += [
            "",
            "#### The furthest out",
            md_table(
                [*([by] if by else []), column, "Score"],
                [
                    [*([o.get("group") or "(blank)"] if by else []), o["value"], signed(o["score"])]
                    for o in outliers[:10]
                ],
                [*([False] if by else []), True, True],
            ),
        ]

    def y(group: Any) -> str:
        return str(group if group is not None else "(blank)") if by else "all"

    groups = (
        list(dict.fromkeys([*(y(f.get("group")) for f in fences), *(y(o.get("group")) for o in outliers)]))
        if by
        else ["all"]
    )
    fenced = fences if by else fences[:1]
    points = [
        v
        for f in fenced
        for v in (f.get("median"), f.get("low_fence"), f.get("high_fence"))
        if isinstance(v, (int, float))
    ]
    points += [o["value"] for o in outliers]
    xaxis: dict[str, Any] = {"title": {"text": f"{column}: the usual range shaded"}}
    if points:
        positive = all((f.get("median") or 0) > 0 for f in fenced) and all(o["value"] >= 0 for o in outliers)
        low = max(0.0, min(points)) if positive else min(points)
        high = max(points)
        pad = (high - low) * 0.04 or 1
        xaxis["range"] = [0 if positive and low == 0 else low - pad, high + pad]
    figure = {
        "data": [
            {
                "type": "scatter",
                "mode": "markers",
                "x": [o["value"] for o in outliers],
                "y": [y(o.get("group")) for o in outliers],
                "marker": {"size": 10, "color": "theme:accent", "line": {"color": "theme:fg", "width": 1}},
                "hovertemplate": "%{x}<extra></extra>",
                "name": "Outliers",
            },
            {
                "type": "scatter",
                "mode": "markers",
                "x": [f.get("median") for f in fenced],
                "y": [y(f.get("group")) for f in fenced],
                "marker": {"symbol": "line-ns-open", "size": 18, "color": "theme:fg"},
                "hovertemplate": "median %{x}<extra></extra>",
                "name": "Median",
            },
        ],
        "layout": BASE_LAYOUT
        | {
            "xaxis": xaxis,
            "yaxis": {"type": "category", "automargin": True, "categoryarray": groups, "visible": bool(by)},
            "shapes": [
                {
                    "type": "rect",
                    "xref": "x",
                    "yref": "y",
                    "x0": f["low_fence"],
                    "x1": f["high_fence"],
                    "y0": groups.index(y(f.get("group"))) - 0.3,
                    "y1": groups.index(y(f.get("group"))) + 0.3,
                    "fillcolor": "theme:ok",
                    "opacity": 0.18,
                    "line": {"width": 0},
                }
                for f in fenced
                if f.get("low_fence") is not None and f.get("high_fence") is not None
            ],
            "showlegend": False,
        },
    }
    return pair(f"Unusual values of {column}", "\n".join(lines), figure)


def frequency_cards(r: dict[str, Any], column: str) -> list[Card]:
    total = r["rarer"] + r["commoner"]
    lines = [
        f"# Values of {column} seen too often or too rarely",
        f"**{fmt(total)} of {fmt(r['distinct'])} values stand out: {fmt(r['rarer'])} rarer and "
        f"{fmt(r['commoner'])} "
        f"commoner than the usual {fmt(r['typical'])} rows per value.**"
        if total
        else f"**Nothing stands out among {fmt(r['distinct'])} values (usually {fmt(r['typical'])} "
        f"rows each).**",
    ]
    outliers = r.get("outliers") or []
    if outliers:
        lines += [
            "",
            md_table(
                ["Value", "Rows", "", "Score"],
                [
                    [o["value"], o["count"], "rarer" if o["score"] < 0 else "commoner", fmt(o["score"])]
                    for o in outliers[:15]
                ],
                [False, True, False, True],
            ),
        ]
    title = f"Unusual values of {column}"
    if not outliers:
        return pair(title, "\n".join(lines), None)
    shown = outliers[:20]
    counts = [o["count"] for o in shown]
    typical = r["typical"] or 1
    spread = max([*counts, typical]) / max(1, min([*counts, typical]))
    log = spread > 50
    figure = {
        "data": [
            {
                "type": "bar",
                "x": [o["value"] for o in shown],
                "y": counts,
                "marker": {"color": ["theme:ok" if o["score"] < 0 else "theme:accent" for o in shown]},
                "hovertemplate": "%{x}: %{y} rows<extra></extra>",
            }
        ],
        "layout": BASE_LAYOUT
        | {
            "xaxis": {"type": "category", "title": {"text": column}},
            "yaxis": {"title": {"text": "Rows"}, "type": "log" if log else "linear"},
            "shapes": [
                {
                    "type": "line",
                    "xref": "paper",
                    "x0": 0,
                    "x1": 1,
                    "y0": typical,
                    "y1": typical,
                    "line": {"color": "theme:fg", "width": 1, "dash": "dot"},
                }
            ],
            "annotations": [
                {
                    "xref": "paper",
                    "x": 1,
                    "y": math.log10(typical) if log else typical,
                    "text": f"usual: {fmt(r['typical'])} rows",
                    "showarrow": False,
                    "xanchor": "right",
                    "yanchor": "bottom",
                    "font": {"size": 10},
                }
            ],
            "showlegend": False,
        },
    }
    return pair(title, "\n".join(lines), figure)


# ===== regression and what-if =====


def regression_cards(r: dict[str, Any]) -> list[Card]:
    linear = r["kind"] == "linear"
    terms = r["coefficients"][1:]
    f = r.get("fit") or {}
    fit = (
        md_table(
            ["R-squared", "Adjusted", "Typical miss", "Rows used"],
            [[fmt(f.get("r2")), fmt(f.get("adj_r2")), fmt(f.get("rmse")), fmt(r["n"])]],
            [True] * 4,
        )
        if linear
        else md_table(
            ["Right", "Guessing", "McFadden R-squared", "Rows used"],
            [
                [
                    pct(f.get("accuracy") or 0),
                    pct(f.get("majority") or 0),
                    fmt(f.get("pseudo_r2")),
                    fmt(r["n"]),
                ]
            ],
            [True] * 4,
        )
    )
    what = r["target"] if linear else r.get("outcome")

    def b(c: dict[str, Any]) -> str:
        mark = "**" if c["p"] < 0.05 else ""
        return f"{mark}{c['term']}{mark}"

    lines = [
        f"# {'What moves' if linear else 'What raises the odds of'} {what}",
        f"**{r['verdict']}**",
        "",
        fit,
        "",
        "#### Each effect, the others held steady",
        md_table(
            ["Term", "In words", "Effect" if linear else "Odds ratio", "95% range", "p"],
            [
                [
                    b(c),
                    c["words"],
                    fmt(c["coefficient"] if linear else c.get("odds_ratio")),
                    f"{fmt(c['low'])} to {fmt(c['high'])}",
                    p_text(c["p"]),
                ]
                for c in terms[:15]
            ],
            [False, False, True, True, True],
        ),
    ]
    if r.get("references"):
        lines += [
            "",
            f"Categories are compared with {', '.join(f'{k} = {v}' for k, v in r['references'].items())}.",
        ]
    if r.get("left_out"):
        n = r["left_out"]
        lines += [
            "",
            f"{fmt(n)} row{'' if n == 1 else 's'} with a blank in a used column "
            f"{'was' if n == 1 else 'were'} left out.",
        ]
    lines += [
        "",
        "> It shows what goes together, not what causes what.",
        *(f"> {w}" for w in r.get("warnings") or []),
    ]
    shown = list(reversed(terms[:20]))

    def point(c: dict[str, Any]) -> float:
        return float(c["coefficient"] if linear else (c.get("odds_ratio") or 1))

    def colour(c: dict[str, Any]) -> str:
        if c["p"] >= 0.05:
            return "theme:muted"
        return "theme:accent" if (point(c) > 0 if linear else point(c) > 1) else "theme:ok"

    figure = {
        "data": [
            {
                "type": "scatter",
                "mode": "markers",
                "x": [point(c) for c in shown],
                "y": [c["term"] for c in shown],
                "error_x": {
                    "type": "data",
                    "symmetric": False,
                    "array": [c["high"] - point(c) for c in shown],
                    "arrayminus": [point(c) - c["low"] for c in shown],
                    "color": "theme:muted",
                    "thickness": 1.5,
                    "width": 4,
                },
                "marker": {"size": 10, "color": [colour(c) for c in shown]},
                "hovertemplate": "%{y}: %{x:.3g}<extra></extra>",
            }
        ],
        "layout": BASE_LAYOUT
        | {
            "xaxis": {
                "title": {"text": f"Effect on {r['target']} (per 1 unit, or against the reference)"},
                "zeroline": True,
                "zerolinewidth": 2,
            }
            if linear
            else {
                "type": "log",
                "title": {"text": f"Odds ratio for {what} (log scale)"},
                **_log_ticks([x for c in shown for x in (c["low"], c["high"])]),
            },
            "yaxis": {"automargin": True, "type": "category"},
            "shapes": []
            if linear
            else [
                {
                    "type": "line",
                    "x0": 1,
                    "x1": 1,
                    "yref": "paper",
                    "y0": 0,
                    "y1": 1,
                    "line": {"color": "theme:fg", "width": 1, "dash": "dot"},
                }
            ],
            "showlegend": False,
        },
    }
    return pair(f"Regression: {what}", "\n".join(lines), figure)


def what_if_cards(fit: dict[str, Any], prediction: dict[str, Any], values: dict[str, Any]) -> list[Card]:
    """The what-if: the row tried, the estimate and its range."""
    target = fit["target"] if fit["kind"] == "linear" else fit.get("outcome")
    estimate = prediction.get("estimate", prediction.get("probability"))
    low, high = prediction.get("low"), prediction.get("high")
    shown = pct(estimate) if fit["kind"] != "linear" and isinstance(estimate, (int, float)) else fmt(estimate)
    lines = [
        f"# What if: {target}",
        f"**About {shown}** (95% range {fmt(low)} to {fmt(high)})."
        if low is not None
        else f"**About {shown}.**",
        "",
        md_table(["Column", "Set to"], [[k, v] for k, v in values.items()], [False, True]),
        "",
        "> From the regression on the same columns; it shows what goes together, not what causes what.",
    ]
    return [
        {"kind": "note", "title": f"What if: {target}", "body": "\n".join(lines), "size": {"w": 5, "h": 8}}
    ]


# ===== time series and forecast =====


def _marker(x: str, text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "type": "line",
            "x0": x,
            "x1": x,
            "yref": "paper",
            "y0": 0,
            "y1": 1,
            "layer": "below",
            "line": {"color": "theme:muted", "width": 1, "dash": "dash"},
        },
        {
            "x": x,
            "yref": "paper",
            "y": 1,
            "text": text,
            "showarrow": False,
            "xanchor": "left",
            "yanchor": "top",
            "xshift": 4,
            "font": {"size": 11, "color": "theme:muted"},
            "bgcolor": "theme:bg/0.85",
        },
    )


_UNIFIED = {"hovermode": "x unified", "hoverdistance": 30}


def time_series_cards(r: dict[str, Any]) -> list[Card]:
    what, period = r["what"], r["period"]
    lines = [
        f"# {what} by {period}",
        *((f"**{w}.**" if i == 0 else f"- {w}") for i, w in enumerate(r.get("words") or [])),
    ]
    if r.get("seasonal") and r.get("season_index"):
        multiplicative = r.get("multiplicative")
        lines += [
            "",
            "#### The season",
            md_table(
                ["", f"Against a typical {period}" if multiplicative else "Difference"],
                [
                    [
                        s["position"],
                        f"{'+' if s['index'] >= 1 else ''}{(s['index'] - 1) * 100:.0f}%"
                        if multiplicative
                        else fmt(s["index"]),
                    ]
                    for s in r["season_index"]
                ],
                [False, True],
            ),
        ]
    recent = (r.get("growth") or [])[-6:]
    if recent:
        lines += [
            "",
            "#### Lately",
            md_table(
                [period, what, "Change", "Against a season ago"],
                [
                    [
                        g["period"],
                        g["value"],
                        "" if g.get("change") is None else f"{g['change'] * 100:.1f}%",
                        "" if g.get("season_ago") is None else f"{g['season_ago'] * 100:.1f}%",
                    ]
                    for g in recent
                ],
                [False, True, True, True],
            ),
        ]
    if r.get("gaps"):
        lines += ["", f"> {len(r['gaps'])} {period}s had no rows."]
    points = r.get("points") or []
    x = [p["period"] for p in points]
    data: list[dict[str, Any]]
    if r.get("lines"):
        data = [
            {
                "type": "scatter",
                "mode": "lines",
                "name": line["name"],
                "x": [p["period"] for p in line["points"]],
                "y": [p["value"] for p in line["points"]],
                "line": {"width": 1.8},
            }
            for line in r["lines"]
        ]
    else:
        data = [
            {
                "type": "scatter",
                "mode": "lines",
                "name": what,
                "x": x,
                "y": [p["value"] for p in points],
                "line": {"color": "theme:fg", "width": 1.5},
                "hovertemplate": "%{y:,.4~r}<extra></extra>",
            },
            {
                "type": "scatter",
                "mode": "lines",
                "name": "Trend",
                "x": x,
                "y": [p["trend"] for p in points],
                "line": {"color": "theme:accent", "width": 2.5, "shape": "spline", "smoothing": 0.6},
                "opacity": 0.9,
                "hovertemplate": "Trend %{y:,.4~r}<extra></extra>",
            },
        ]
    if r.get("anomalies"):
        data.append(
            {
                "type": "scatter",
                "mode": "markers",
                "name": "Stands out",
                "x": [a["period"] for a in r["anomalies"]],
                "y": [a["value"] for a in r["anomalies"]],
                "marker": {"size": 10, "color": "theme:accent", "line": {"color": "theme:bg", "width": 2}},
                "hovertemplate": "Stands out: %{y:,.4~r}<extra></extra>",
            }
        )
    marks = [_marker(s["period"], "Level stepped") for s in r.get("shifts") or []]
    figure = {
        "data": data,
        "layout": BASE_LAYOUT
        | _UNIFIED
        | {
            "xaxis": {"type": "date", "showgrid": False},
            "yaxis": {"title": {"text": f"{what} per {period}"}, "rangemode": "tozero"},
            "shapes": [m[0] for m in marks],
            "annotations": [m[1] for m in marks],
        },
    }
    return pair(f"Time series: {what}", "\n".join(lines), figure)


def forecast_cards(r: dict[str, Any]) -> list[Card]:
    what, period = r["what"], r["period"]
    ahead = r.get("forecast") or []
    lines = [
        f"# Forecast: {what} by {period}",
        *((f"**{w}**" if i == 0 else f"- {w}") for i, w in enumerate(r.get("words") or [])),
        "",
        md_table(
            [period, "Forecast", "80% range", "95% range"],
            [
                [
                    f["period"],
                    f["estimate"],
                    f"{fmt(f['low80'])} to {fmt(f['high80'])}",
                    f"{fmt(f['low95'])} to {fmt(f['high95'])}",
                ]
                for f in ahead[:12]
            ],
            [False, True, True, True],
        ),
    ]
    if r.get("predictors"):

        def said(p: dict[str, Any]) -> str:
            how = {"value": f"set to {fmt(p.get('value'))}", "trend": "its own trend"}.get(
                p.get("future", ""), "its last value"
            )
            return f"{p['column']} ({how})"

        lines += ["", f"Predictors: {', '.join(said(p) for p in r['predictors'])}."]
    fx = [f["period"] for f in ahead]

    def band(low: list[float], high: list[float], colour: str, name: str) -> dict[str, Any]:
        return {
            "type": "scatter",
            "mode": "lines",
            "name": name,
            "x": fx + fx[::-1],
            "y": high + low[::-1],
            "fill": "toself",
            "fillcolor": colour,
            "line": {"width": 0},
            "hoverinfo": "skip",
        }

    marks = ([_marker(r["check"]["from"], "Held back to test")] if r.get("check") else []) + (
        [_marker(fx[0], "Forecast")] if fx else []
    )
    history = r.get("history") or []
    figure = {
        "data": [
            band([f["low95"] for f in ahead], [f["high95"] for f in ahead], "theme:accent/0.12", "95% range"),
            band([f["low80"] for f in ahead], [f["high80"] for f in ahead], "theme:accent/0.24", "80% range"),
            {
                "type": "scatter",
                "mode": "lines",
                "name": what,
                "x": [h["period"] for h in history],
                "y": [h["value"] for h in history],
                "line": {"color": "theme:fg", "width": 1.5},
                "hovertemplate": "%{y:,.4~r}<extra></extra>",
            },
            {
                "type": "scatter",
                "mode": "lines",
                "name": "The model's fit",
                "x": [h["period"] for h in history],
                "y": [h["fitted"] for h in history],
                "line": {"color": "theme:cat-2", "width": 1, "dash": "dot"},
                "hovertemplate": "Fit %{y:,.4~r}<extra></extra>",
            },
            {
                "type": "scatter",
                "mode": "lines+markers",
                "name": "Forecast",
                "x": fx,
                "y": [f["estimate"] for f in ahead],
                "line": {"color": "theme:accent", "width": 2.5},
                "marker": {"size": 5, "color": "theme:accent"},
                "hovertemplate": "Forecast %{y:,.4~r}<extra></extra>",
            },
        ],
        "layout": BASE_LAYOUT
        | _UNIFIED
        | {
            "xaxis": {"type": "date", "showgrid": False},
            "yaxis": {"title": {"text": f"{what} per {period}"}},
            "shapes": [m[0] for m in marks],
            "annotations": [m[1] for m in marks],
        },
    }
    return pair(f"Forecast: {what}", "\n".join(lines), figure)


# ===== describe, check, compare =====


def profile_cards(r: dict[str, Any], dataset: str) -> list[Card]:
    columns = r.get("columns") or []
    markdown = "\n".join(
        [
            f"# Profile of {dataset}",
            f"**{fmt(r.get('rows'))} rows, {fmt(len(columns))} columns, "
            f"{fmt(r.get('duplicate_rows'))} duplicate rows.**",
            "",
            md_table(
                ["Column", "Type", "Blank", "Blank %", "Different values", "Lowest", "Highest"],
                [
                    [
                        c.get("column"),
                        str(c.get("type", "")).lower(),
                        c.get("blanks"),
                        f"{c.get('blank_percent')}%",
                        c.get("distinct"),
                        *(
                            (plain(c.get("min")), plain(c.get("max")))
                            if is_label_column(c.get("column"), c.get("min"), c.get("max"))
                            else (c.get("min"), c.get("max"))
                        ),
                    ]
                    for c in columns
                ],
                [False, False, True, True, True, False, False],
            ),
        ]
    )
    return [
        card | {"size": {"w": 12, "h": card["size"]["h"]}}
        for card in pair(f"Profile of {dataset}", markdown, None)
    ]


def check_cards(notes: list[dict[str, str]], suggested: list[dict[str, Any]], dataset: str) -> list[Card]:
    lines = [f"# Check: {dataset}", ""]
    lines += [f"- {'⚠ ' if n['level'] == 'warn' else ''}{n['text']}" for n in notes]
    if suggested:
        lines += [
            "",
            "#### What makes sense for this table",
            *(f"1. {s['label']} ({s['name']})" for s in suggested),
        ]
    return [
        {
            "kind": "note",
            "title": f"Check: {dataset}",
            "body": "\n".join(lines),
            "size": {"w": 6, "h": max(6, min(16, 3 + len(lines) // 2))},
        }
    ]


def tie_out_cards(r: dict[str, Any], left: str, right: str) -> list[Card]:
    columns, rows = tie_out_rows(r, left, right)
    note = (
        f"# Tie-out: {left} and {right}\n\n**{r['words']}**\n\nGrouped by "
        f"{', '.join(r.get('group_by') or []) or 'nothing (one total)'}; "
        f"totals of {', '.join(r.get('measures') or []) or 'rows only'}."
    )
    return [
        {"kind": "note", "title": f"Tie-out: {left} and {right}", "body": note, "size": {"w": 4, "h": 7}},
        {
            "kind": "table",
            "title": f"Tie-out by {', '.join(r.get('group_by') or []) or 'total'}",
            "columns": columns,
            "rows": rows[:100],
            "size": {"w": 8, "h": 10},
        },
    ]


def tie_out_rows(r: dict[str, Any], left: str, right: str) -> tuple[list[str], list[list[Any]]]:
    group_by = list(r.get("group_by") or [])
    columns = [*(group_by or ["group"]), f"rows {left}", f"rows {right}", "row difference"]
    for m in r.get("measures") or []:
        columns += [f"{m} {left}", f"{m} {right}", f"{m} difference"]
    columns.append("status")
    rows: list[list[Any]] = []
    for g in r.get("groups") or []:
        row: list[Any] = list(g.get("group") or []) if group_by else ["All rows"]
        row += [g.get("left_rows"), g.get("right_rows"), g.get("row_difference")]
        for m in g.get("measures") or []:
            row += [m.get("left"), m.get("right"), m.get("difference")]
        row.append(g.get("status"))
        rows.append([v if v is None or isinstance(v, (str, int, float, bool)) else str(v) for v in row])
    return columns, rows


def key_finder_cards(r: dict[str, Any]) -> list[Card]:
    source = r.get("source") or "this table"
    pairs = r.get("pairs") or []

    def share(v: Any) -> str:
        return f"{round(100 * float(v or 0))}%"

    targets = ", ".join(f"`{t.get('dataset')}`" for t in r.get("targets") or []) or "no other table"
    key = r.get("unique_key") or {}
    lines = [
        f"# Join columns for {source}",
        f"**{fmt(len(pairs))} column pair{'' if len(pairs) == 1 else 's'} share values** with {targets}.",
    ]
    if isinstance(key, dict) and key.get("columns"):
        lines.append(f"Its rows are told apart by {', '.join(key['columns'])}.")
    lines += [
        "",
        md_table(
            [
                f"{source} column",
                "Table",
                "Column",
                "Relationship",
                f"Found from {source}",
                "Found from the other",
                "Shared values",
            ],
            [
                [
                    p.get("source_column"),
                    p.get("target_dataset"),
                    p.get("target_column"),
                    p.get("relationship"),
                    share(p.get("source_found")),
                    share(p.get("target_found")),
                    p.get("shared"),
                ]
                for p in pairs[:15]
            ],
            [False, False, False, False, True, True, True],
        ),
    ]
    return [
        {
            "kind": "note",
            "title": f"Join columns for {source}",
            "body": "\n".join(lines),
            "size": {"w": 12, "h": min(16, 5 + min(15, len(pairs)))},
        }
    ]


# ===== every analysis, by its id =====


def cards_for(analysis_id: str, result: dict[str, Any], body: dict[str, Any], dataset: str) -> list[Card]:
    """The board's cards for one result of an Analyze analysis (domain/analyze.py's ids, or a route's
    name from Python: fit_test, outliers, odds, predictors, regression, time_series, forecast)."""
    if analysis_id in ("benford", "fit", "together", "fit_test"):
        expected = str(body.get("expected") or "even")
        if "results" in result:
            return [c for one in result["results"] for c in fit_cards(one, expected)]
        return fit_cards(result, "together", list(result.get("columns") or body.get("columns") or []))
    if analysis_id == "outliers":
        column = str(body.get("column") or "")
        if result.get("look") == "frequency":
            return frequency_cards(result, column)
        return amount_cards(result, column, str(body.get("method") or "robust"))
    if analysis_id == "odds":
        return odds_cards(result)
    if analysis_id == "predictors":
        return predictors_cards(result)
    if analysis_id == "regression":
        return regression_cards(result)
    if analysis_id == "whatif":
        return what_if_cards(result["fit"], result["prediction"], result["values"]) + regression_cards(
            result["fit"]
        )
    if analysis_id == "time_series":
        return time_series_cards(result)
    if analysis_id == "forecast":
        return forecast_cards(result)
    if analysis_id == "profile":
        return profile_cards(result, dataset)
    if analysis_id == "check":
        return check_cards(result.get("notes") or [], result.get("suggested") or [], dataset)
    if analysis_id == "tie_out":
        return tie_out_cards(
            result, str(result.get("left_name") or "left"), str(result.get("right_name") or "right")
        )
    if analysis_id == "key_finder":
        return key_finder_cards(result)
    raise ValueError(f"No cards for {analysis_id!r}.")


def result_rows(
    analysis_id: str, result: dict[str, Any], body: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """A result as rows for Open as grid, or None when it has no table to open."""
    if analysis_id in ("benford", "fit", "together", "fit_test"):
        listed = result.get("results") or [result]
        if len(listed) == 1 and listed[0].get("categories"):
            return [dict(c) for c in listed[0]["categories"]]
        if result.get("cells"):
            return [dict(c) for c in result["cells"]]
        return None
    if analysis_id == "outliers":
        column = str(body.get("column") or "value")
        if result.get("look") == "frequency":
            return [
                {column: o["value"], "rows": o["count"], "score": o["score"]}
                for o in result.get("outliers") or []
            ]
        by = result.get("by")
        return [
            {**({by: o.get("group")} if by else {}), column: o["value"], "score": o["score"]}
            for o in result.get("outliers") or []
        ]
    if analysis_id == "odds":
        return [dict(v) for v in result.get("values") or []]
    if analysis_id == "predictors":
        return [
            {
                "column": c["column"],
                "kind": c.get("kind"),
                "strength": c["strength"],
                "cramers_v": c["v"],
                "p": c.get("p"),
                "correlation": c.get("correlation"),
                "same_as": c.get("same_as"),
                "note": c.get("note"),
            }
            for c in result.get("candidates") or []
        ]
    if analysis_id in ("regression", "whatif"):
        fit = result["fit"] if analysis_id == "whatif" else result
        return [
            {
                "term": c["term"],
                "coefficient": c["coefficient"],
                "low": c["low"],
                "high": c["high"],
                "p": c["p"],
                **({"odds_ratio": c["odds_ratio"]} if "odds_ratio" in c else {}),
                "effect": c["words"],
            }
            for c in fit.get("coefficients") or []
        ]
    if analysis_id == "time_series":
        return [dict(p) for p in result.get("points") or []]
    if analysis_id == "forecast":
        return [dict(f) for f in result.get("forecast") or []]
    if analysis_id == "profile":
        return [dict(c) for c in result.get("columns") or []]
    if analysis_id == "tie_out":
        columns, rows = tie_out_rows(
            result, str(result.get("left_name") or "left"), str(result.get("right_name") or "right")
        )
        return [dict(zip(columns, r, strict=True)) for r in rows]
    if analysis_id == "key_finder":
        return [dict(p) for p in result.get("pairs") or []] or None
    return None


def next_steps(analysis_id: str, result: dict[str, Any], body: dict[str, Any]) -> list[dict[str, Any]]:
    """The hand-offs to the next tool (8.8), each a step for the table ({"label", "step"}) or another
    analysis with its columns ({"label", "analysis", "columns"})."""
    out: list[dict[str, Any]] = []
    if analysis_id == "outliers":
        if result.get("step"):
            out.append({"label": "Show these rows", "step": result["step"]})
        if result.get("exclude_step"):
            out.append({"label": "Exclude these", "step": result["exclude_step"]})
    elif analysis_id == "predictors":
        picks = [
            c["column"]
            for c in result.get("candidates") or []
            if c["strength"] in ("strong", "moderate") and not c.get("same_as")
        ]
        if picks:
            out.append(
                {
                    "label": "Predict it from these",
                    "analysis": "regression",
                    "columns": {"target": result["target"], "predictors": picks},
                }
            )
        if picks:
            out.append(
                {
                    "label": f"Test {result['target']} and {picks[0]} together",
                    "analysis": "together",
                    "columns": {"first": result["target"], "second": picks[0]},
                }
            )
    elif analysis_id == "odds" and result.get("outcome"):
        outcome = (body.get("outcome") or {}).get("column")
        if outcome:
            out.append(
                {
                    "label": "Test the two together",
                    "analysis": "together",
                    "columns": {"first": result["column"], "second": outcome},
                }
            )
    elif analysis_id in ("regression", "whatif"):
        fit = result["fit"] if analysis_id == "whatif" else result
        steps = fit.get("steps") or {}
        if steps.get("predicted"):
            out.append({"label": "Add the predicted column", "step": steps["predicted"]})
        if steps.get("miss"):
            out.append({"label": "Add the miss column", "step": steps["miss"]})
    elif analysis_id == "time_series" and result.get("step"):
        out.append({"label": "Show the periods that stand out", "step": result["step"]})
    if analysis_id == "time_series":
        out.append(
            {
                "label": "What comes next?",
                "analysis": "forecast",
                "columns": {"date": body.get("date"), "metric": body.get("metric") or ""},
            }
        )
    return out
