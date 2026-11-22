"""Stockroom's agent command (the golden rule): the made-up shelf counts."""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.commands import Command, Registrar

COMMANDS: dict[str, Command] = {}
command = Registrar(COMMANDS)


@command("stockroom_count", "The made-up stockroom's shelf counts")
def stockroom_count(a: dict[str, Any]) -> Any:
    return api.call("GET", "/stockroom/count")
