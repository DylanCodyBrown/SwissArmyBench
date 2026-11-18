"""The tables a project uses, and the ERD drawn of them (the owner, 2026-11-17: "Relationships should filter
the erd to only the tables that are being used in the project"). domain/relationships.py has the rules.

  used     the open tables, the project's tables (.sab/project.json) and the model's tables its documents
           name; None with no project open (everything is drawn, as before)
  scope    what is drawn and what is not, counted by the connection it came from
  erd      the ERD for "project" (the tables used; the default) or "all"

A relationship is drawn when both its ends are used; the model keeps every one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from swissarmybench.domain.relationships import Model, code_of, hidden_words, named_in, used_scope
from swissarmybench.services.relationships import Models

# What the composition root gives: None with no project open, else the project's own table names and its
# documents as (path, text).
ProjectDocuments = Callable[[], tuple[set[str], list[tuple[str, str]]] | None]

SCOPES = ("project", "all")


class ProjectTables:
    def __init__(
        self, models: Models, project: ProjectDocuments, shared: Callable[[], Model] | None = None
    ) -> None:
        self.models = models
        self.ws = models.ws
        self._project = project
        # The shared catalog's model (services/shared_catalog.py): All tables draws a teammate's tables too.
        self.shared = shared

    def used(self) -> set[str] | None:
        """The tables the open project uses (None: no project open)."""
        found = self._project()
        if found is None:
            return None
        names, documents = found
        open_names = {i.name for i in self.ws.store.all()}
        texts = [code_of(path, text) for path, text in documents]
        return open_names | names | named_in(texts, self.models.model.tables())

    def scope(self, scope: str | None = None) -> dict[str, Any]:
        """What the ERD draws: the tables in the project (or all), the hidden ones and their count's words."""
        chosen = _scope(scope)
        used = self.used() if chosen == "project" else None
        answer = used_scope(self.models.model, used)
        return answer | {"scope": chosen if used is not None else "all", "words": hidden_words(answer)}

    def erd(self, wanted: set[str], scope: str | None = None) -> dict[str, Any]:
        """The ERD: of `wanted` when named, else of the tables the project uses (scope "project", the
        default) or of every table ("all"). With no project open, as before (the open tables, else all)."""
        if wanted:
            return self.models.erd(wanted)
        if scope == "all" and self.shared is not None:
            return self.models.erd(set(), self.shared())
        drawn = self.scope(scope)
        if not drawn["project"]:
            return self.models.erd(set())
        if not drawn["tables"]:
            raise ValueError(
                "None of the relationships' tables is used in this project: draw all tables to see them."
            )
        return self.models.erd(set(drawn["tables"])) | {"hidden": drawn["hidden"], "words": drawn["words"]}


def _scope(raw: str | None) -> str:
    if raw in (None, ""):
        return "project"
    if raw not in SCOPES:
        raise ValueError('scope is "project" (the tables this project uses) or "all".')
    return str(raw)
