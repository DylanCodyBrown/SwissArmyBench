"""The endpoint wizard's patterns (the owner, 2026-11-21: "a handful of api types that are universal to the
sandbox that covers 99% of coding needs" / "one uniform wizard for creating a sandbox api" / "Steps are
different depending on the API. Widgets handle transformations, APIs handle getting the data as performant as
possible"). Each pattern is data: its question, the steps the wizard asks (its own, never five fixed ones),
how well a table's shape fits it and why in one sentence, the widgets that pair with its endpoints, and ONE
template that writes its code from its fields and the table's catalog.

  table      list (a page), get, create, update, delete by a key        domain/api_scaffold.py's CRUD set
  choices    a dropdown's choices: a value and its label, searched
  search     the rows that match: each chosen column a filter, a text search, a sort, a page
  summary    totals per group (and per month, quarter or year)
  bulk       many rows at once: checked, a dry run that lists the problems, then all or none
  action     a named change to the rows whose keys are sent, all or none
  versions   every version of a thing, its current one, a new version (earlier ones never changed)
  reconcile  two tables by a key: matched, missing on each side, differing values
  export     a CSV file or an Excel workbook to save

Every template is written in the scaffold's one style: the adapter's `connection(name).read / .query /
.write` (adapters/adapter.py's Connection), never a per-source client, so the code runs on the sandbox here
and on the real connection in an export. The API's job is fetching and writing fast: the filters, the
columns, the sort, the page and the keys go to the source in the read's plan; no endpoint reads a whole large
table a call. Summary folds its period, group and totals into the plan (the adapter sends them to the source
where it can, else groups only the columns it needs over the stream); Reconcile is one statement in the
source's own SQL through `query` where the source has SQL, and where it has none (Dataverse's Web API,
SharePoint, two different connections) it reads only the columns it needs and DuckDB does the rest over the
stream, said in the endpoint's own words.

One marker comment under the block's banner names the pattern (`# pattern: summary of orders`): the APIs
page labels the endpoints by it. The code is the user's from then on: nothing here reads it back to rewrite
it. An extension adds its own patterns as data (its API_PATTERNS: Registry.add, from_extension).

Pure text: standard library and sqlglot only.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import api_pattern_code as code
from swissarmybench.domain.api_pattern_code import Made, Taken, Target, partner
from swissarmybench.domain.api_scaffold import ScaffoldError

__all__ = ["MARKER", "PATTERNS", "Made", "Pairing", "Pattern", "Registry", "Step", "Taken", "Target",
           "from_extension", "marked", "partner", "pattern_at"]  # fmt: skip

MARKER = re.compile(r"^# pattern: ([a-z][a-z0-9_]*)(?: of (.+?))?\s*$")
# ===== what a pattern is =====


@dataclass(frozen=True)
class Step:
    """One thing the wizard asks for a pattern. `kind`: column (one), columns (several), choice, text,
    table (a second sandbox table), totals (rows of a total and its column), sets (rows of a column and the
    value it is set to). `of`: the columns offered (any, text, number, date, whole: whole numbers; shared:
    the ones both tables have)."""

    id: str
    label: str
    kind: str = "column"
    of: str = "any"
    help: str = ""
    required: bool = True
    choices: tuple[tuple[str, str], ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "of": self.of,
            "help": self.help,
            "required": self.required,
            "choices": [{"value": v, "label": w} for v, w in self.choices],
        }


@dataclass(frozen=True)
class Pairing:
    """A widget that pairs with one of a pattern's endpoints: `role` is the endpoint's part in the pattern
    (its function's first word: list, create, choices…), `port` the widget's endpoint property, or the In it
    is wired into."""

    widget: str
    role: str
    port: str = "endpoint"
    words: str = ""
    # Widget properties the pairing also sets, each to a field of the endpoint's answer by its place
    # (Choices answers the value then the label: a select's column of options is the label, 1).
    sets: tuple[tuple[str, int], ...] = ()

    def to_json(self) -> dict[str, Any]:
        said = {"widget": self.widget, "role": self.role, "port": self.port, "words": self.words}
        return said | ({"sets": dict(self.sets)} if self.sets else {})


Maker = Callable[[Target, Mapping[str, Any], "Taken", "Target | None"], Made]
Fit = Callable[[Target, Sequence[Target]], tuple[int, str]]
Defaults = Callable[[Target, "Target | None"], dict[str, Any]]


@dataclass(frozen=True)
class Pattern:
    id: str
    label: str
    question: str  # what it is for, in one sentence
    steps: tuple[Step, ...]
    widgets: tuple[Pairing, ...]
    make: Maker
    fit: Fit
    defaults: Defaults
    tables: int = 1
    roles: tuple[str, ...] = ()  # its endpoints' parts (their functions' first words), the longest first
    extension: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "question": self.question,
            "tables": self.tables,
            "steps": [s.to_json() for s in self.steps],
            "widgets": [w.to_json() for w in self.widgets],
            "extension": self.extension,
        }


# ===== the registry =====

_KEY = Step("key", "Its key", "column", help="The column that tells one row from another.")

PATTERNS: dict[str, Pattern] = {
    p.id: p
    for p in (
        Pattern(
            "table",
            "Table",
            "Its rows a page at a time, and one row read, made, changed or deleted by its key.",
            (Step("key", "Its key", "column", help="Get, update and delete are by it."),),
            (
                Pairing("api_table", "list", words="An API table shows its rows a page at a time."),
                Pairing("api_form", "create", words="An API form adds a row."),
            ),
            code.make_table,
            code.fit_table,
            lambda target, other: {"key": code.key_of(target)},
            roles=("list", "get", "create", "update", "delete"),
        ),
        Pattern(
            "choices",
            "Choices",
            "The choices of a dropdown: a value and the label shown for it.",
            (
                Step(
                    "value",
                    "The value",
                    "column",
                    help="What a choice stands for (its key, or a column's values).",
                ),
                Step("label", "The label shown", "column", help="What the user reads; ?search= looks in it."),
            ),
            (
                Pairing(
                    "select_box",
                    "choices",
                    "options_table",
                    "A select box takes them as its options.",
                    (("options_column", 1),),
                ),
                Pairing(
                    "input_select",
                    "choices",
                    "options_table",
                    "A select input takes them as its options.",
                    (("options_column", 1),),
                ),
            ),
            code.make_choices,
            code.fit_choices,
            code.defaults_choices,
            roles=("choices",),
        ),
        Pattern(
            "search",
            "Search",
            "The rows that match: a text search, a filter per column, a sort, a page.",
            (
                Step(
                    "text",
                    "Text search looks in",
                    "column",
                    "text",
                    "?q= finds the rows whose text holds it.",
                    False,
                ),
                Step(
                    "filters",
                    "Filter by",
                    "columns",
                    help="Each becomes its own optional parameter (a date: from and to).",
                    required=False,
                ),
                Step("columns", "Columns it answers", "columns", help="Only these are read from the source."),
                Step("sort", "Sorted by", "column", help="The default; ?sort= takes another."),
            ),
            (Pairing("api_table", "search", words="An API table shows what matches, a page at a time."),),
            code.make_search,
            code.fit_search,
            code.defaults_search,
            roles=("search",),
        ),
        Pattern(
            "summary",
            "Summary",
            "Totals per group: sums, counts and averages, by a column or by month, quarter or year.",
            (
                Step("group", "Group by", "columns", help="Each also becomes a filter.", required=False),
                Step("totals", "Totals", "totals", help="count needs no column."),
                Step("date", "Date column (for a period)", "column", "date", required=False),
                Step(
                    "period",
                    "Period",
                    "choice",
                    required=False,
                    choices=(
                        ("", "None"),
                        ("day", "Day"),
                        ("week", "Week (from Monday)"),
                        ("month", "Month"),
                        ("quarter", "Quarter"),
                        ("year", "Year"),
                    ),
                ),
            ),
            (
                Pairing("bar_chart", "summary", "table_name", "A bar chart draws the totals."),
                Pairing("data_table", "summary", "table_name", "A table lists the totals."),
            ),
            code.make_summary,
            code.fit_summary,
            code.defaults_summary,
            roles=("summary",),
        ),
        Pattern(
            "bulk",
            "Bulk upload",
            "Many rows at once: checked first, a dry run that lists the problems, then all written or none.",
            (
                _KEY,
                Step(
                    "mode",
                    "What an upload does",
                    "choice",
                    choices=(
                        ("merge", "Add the new rows and update the rest"),
                        ("insert", "Add new rows only"),
                    ),
                ),
                Step(
                    "required",
                    "Required columns",
                    "columns",
                    help="A row without one is a problem.",
                    required=False,
                ),
            ),
            (Pairing("api_button", "bulk", words="An API button sends the rows it is given."),),
            code.make_bulk,
            code.fit_bulk,
            code.defaults_bulk,
            roles=("bulk",),
        ),
        Pattern(
            "action",
            "Action",
            "A named change (approve, close, cancel) to the rows whose keys are sent, all of them or none.",
            (
                Step("name", "Its name", "text", help="One word for what it does: approve, close, cancel."),
                _KEY,
                Step("sets", "It sets", "sets", help="Each column and the value it is set to."),
                Step(
                    "only",
                    "Only while this column…",
                    "column",
                    help="Checked first: a row that is not is refused.",
                    required=False,
                ),
                Step("only_value", "…is", "text", required=False),
                Step(
                    "log",
                    "Also adds a row to",
                    "table",
                    help="Another table of the same connection (an audit): a row a key, written with the "
                    "change in one transaction, both or neither.",
                    required=False,
                ),
            ),
            (Pairing("api_button", "action", words="An API button runs it."),),
            code.make_action,
            code.fit_action,
            code.defaults_action,
            roles=("action",),
        ),
        Pattern(
            "versions",
            "Versions",
            "Every version of a thing kept: its versions, its current one, a new version added.",
            (
                Step(
                    "of",
                    "A version of",
                    "column",
                    help="The column that says which thing a row is a version of.",
                ),
                Step("version", "Version number", "column", "whole", "A whole number: 1, 2, 3."),
            ),
            (Pairing("api_table", "versions", words="An API table lists one thing's versions."),),
            code.make_versions,
            code.fit_versions,
            code.defaults_versions,
            roles=("new_version", "versions", "current"),
        ),
        Pattern(
            "reconcile",
            "Reconcile",
            "Two tables compared by a key: matched, missing on each side, differing values.",
            (
                Step("other", "Compared with", "table"),
                Step("key", "The key both share", "columns", "shared"),
                Step("compare", "Compare these columns", "columns", "shared", required=False),
            ),
            (
                Pairing("api_metric", "reconcile", words="An API metric shows a count."),
                Pairing("api_table", "rows", words="An API table lists the compared rows."),
            ),
            code.make_reconcile,
            code.fit_reconcile,
            code.defaults_reconcile,
            tables=2,
            roles=("rows", "reconcile"),
        ),
        Pattern(
            "export",
            "Export",
            "A CSV file or an Excel workbook of its rows to save.",
            (
                Step("columns", "Columns it carries", "columns"),
                Step(
                    "format", "As", "choice", choices=(("csv", "A CSV file"), ("xlsx", "An Excel workbook"))
                ),
                Step("sort", "Sorted by", "column"),
            ),
            (),
            code.make_export,
            code.fit_export,
            code.defaults_export,
            roles=("export",),
        ),
    )
}


@dataclass
class Registry:
    """The patterns: the base's nine, then what each extension that is on adds (its API_PATTERNS)."""

    patterns: dict[str, Pattern] = field(default_factory=lambda: dict(PATTERNS))

    def add(self, pattern: Pattern) -> None:
        self.patterns[pattern.id] = pattern

    def get(self, wanted: Any) -> Pattern:
        found = self.patterns.get(str(wanted or "table").strip().lower())
        if found is None:
            raise ScaffoldError(f"The pattern is one of: {', '.join(self.patterns)}.")
        return found

    def listed(self) -> list[dict[str, Any]]:
        return [p.to_json() for p in self.patterns.values()]

    def ranked(self, target: Target, others: Sequence[Target] = ()) -> list[dict[str, Any]]:
        """Every pattern against a table's shape, the best fit first: whether it fits and why, in one
        sentence (the way Analyze ranks by its contracts)."""
        found = []
        for at, pattern in enumerate(self.patterns.values()):
            score, why = pattern.fit(target, others)
            said = {"pattern": pattern.id, "label": pattern.label, "question": pattern.question}
            found.append((-score, at, said | {"fits": score > 0, "score": score, "why": why}))
        return [f[2] for f in sorted(found, key=lambda f: (f[0], f[1]))]

    def planned(
        self,
        wanted: Any,
        target: Target,
        fields: Mapping[str, Any] | None = None,
        other: Target | None = None,
    ) -> dict[str, Any]:
        """A pattern's own steps for a table: each with the columns it offers and its value (the one given,
        else the default the table's shape suggests)."""
        pattern = self.get(wanted)
        given = dict(fields or {})
        defaults = pattern.defaults(target, other)
        steps = []
        for step in pattern.steps:
            options = target.of(step.of) if step.kind in ("column", "columns", "totals", "sets") else []
            if step.of == "shared":
                options = code.columns_shared(target, other) if other is not None else []
            value = given[step.id] if step.id in given else defaults.get(step.id)
            if step.kind == "table":
                value = other.name if other is not None else ""
            steps.append(step.to_json() | {"options": options, "value": value})
        values = {s["id"]: s["value"] for s in steps if s["kind"] != "table"}
        return {"pattern": pattern.id, "label": pattern.label, "question": pattern.question,
                "tables": pattern.tables, "steps": steps, "fields": values,
                "widgets": [w.to_json() for w in pattern.widgets]}  # fmt: skip

    def make(
        self,
        wanted: Any,
        target: Target,
        fields: Mapping[str, Any] | None = None,
        taken: Taken | None = None,
        other: Target | None = None,
    ) -> Made:
        """The pattern's code for the table: its fields (the ones not given: its defaults) into its one
        template."""
        pattern = self.get(wanted)
        if not target.names:
            raise ScaffoldError(f"{target.name} has no columns.")
        if pattern.tables == 2 and other is None:
            raise ScaffoldError(f"{pattern.label} compares two tables: pick the second one.")
        merged = pattern.defaults(target, other) | {
            k: v for k, v in dict(fields or {}).items() if v is not None
        }
        return pattern.make(target, merged, taken or Taken(), other)

    def role(self, wanted: str, function: str) -> str:
        """An endpoint's part in its pattern, from its function's name (list_orders: list; an action's own
        word: action)."""
        pattern = self.patterns.get(wanted)
        if pattern is None:
            return ""
        if function.endswith("_rows") and "rows" in pattern.roles:
            return "rows"
        for role in pattern.roles:
            if function == role or function.startswith(role + "_"):
                return role
        return "action" if "action" in pattern.roles else ""

    def pairings(self, wanted: str, function: str) -> list[dict[str, Any]]:
        """The widgets that pair with one endpoint of a pattern."""
        pattern = self.patterns.get(wanted)
        role = self.role(wanted, function)
        return [w.to_json() for w in pattern.widgets if w.role == role] if pattern is not None else []


def _pairing(given: Mapping[str, Any]) -> Pairing:
    """An extension's pairing as its fields: `sets` as {property: the answer's field's place}."""
    sets = given.get("sets") or {}
    pairs = tuple((str(k), int(v)) for k, v in (sets.items() if isinstance(sets, Mapping) else sets))
    return Pairing(**{k: v for k, v in given.items() if k != "sets"}, sets=pairs)


def from_extension(raw: Any, extension: str) -> Pattern:
    """An extension's API_PATTERNS item: a Pattern, or {id, label, question, steps, widgets, make, fit?,
    defaults?, tables?, roles?} (steps and widgets as Step and Pairing, or their fields)."""
    if isinstance(raw, Pattern):
        return Pattern(**{**raw.__dict__, "extension": extension})
    given = dict(raw)
    make = given.get("make")
    if not callable(make) or not str(given.get("id") or "").strip():
        raise ValueError(f"{extension}'s API pattern needs an id and a make(target, fields, taken, other).")
    steps = tuple(s if isinstance(s, Step) else Step(**s) for s in given.get("steps") or ())
    widgets = tuple(w if isinstance(w, Pairing) else _pairing(w) for w in given.get("widgets") or ())
    label = str(given.get("label") or given["id"])
    return Pattern(
        str(given["id"]).strip().lower(),
        label,
        str(given.get("question") or ""),
        steps,
        widgets,
        make,
        given.get("fit") or (lambda target, others: (50, f"{label} over {target.name}.")),
        given.get("defaults") or (lambda target, other: {}),
        int(given.get("tables") or 1),
        tuple(given.get("roles") or ()),
        extension,
    )


def marked(text: str) -> dict[int, tuple[str, str]]:
    """API.py's pattern markers: each `# pattern: <id> of <tables>` line's number -> (id, its tables)."""
    found = {}
    for at, line in enumerate(text.split("\n"), 1):
        hit = MARKER.match(line)
        if hit:
            found[at] = (hit.group(1), hit.group(2) or "")
    return found


def pattern_at(text: str, line: int) -> tuple[str, str]:
    """The pattern an endpoint at `line` was made by (and its tables): the nearest marker above it, with no
    other banner (`# =====`) in between; ("", "") for an endpoint written by hand."""
    lines = text.split("\n")
    for at in range(min(line, len(lines)) - 1, -1, -1):
        hit = MARKER.match(lines[at])
        if hit:
            return hit.group(1), hit.group(2) or ""
        if lines[at].startswith("# =====") and not (at + 1 < len(lines) and MARKER.match(lines[at + 1])):
            return "", ""
    return "", ""
