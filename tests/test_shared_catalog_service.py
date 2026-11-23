"""Which of this computer's connections the shared catalog keeps (services/shared_catalog.py
connections_here): the rule that was the composition root's closure. Made-up names only."""

from __future__ import annotations

from swissarmybench.domain.blades import Blade
from swissarmybench.services.shared_catalog import Here, connections_here


def test_the_connections_with_tables_and_never_a_vault_a_web_call_or_plain_code() -> None:
    blades = [
        Blade("Warehouse", "sql", dialect="postgres", template="postgres"),
        Blade("Team vault", "vault", template="azure_key_vault"),
        Blade("Get orders", "sql", dialect="postgres", web_call={"api": "Orders"}),
        Blade("Tidy names", "other"),
        Blade("Exports", "other", template="folder"),
    ]
    assert connections_here(blades) == [
        Here("Warehouse", "database", "postgres"),
        Here("Exports", "folder", "folder"),
    ]
