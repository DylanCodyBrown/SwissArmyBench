"""Stockroom: a made-up folder extension for the tests (tests/test_folder_extensions.py copies this folder
into a test's library as extensions/stockroom/). Never shipped.

It is laid out in the order the app reads it:
  the manifest   ID, NAME, VERSION, DESCRIPTION, ADDS, REQUIRES, AREAS
  routes         GET /stockroom/count: a made-up stockroom's shelf counts
  commands       stockroom_count (commands.py)
Its project type is contract.json's: a Stockroom project with stock_report.md as its deliverable.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

# ===== the manifest =====

ID = "stockroom"
NAME = "Stockroom"
VERSION = "0.1.0"
DESCRIPTION = "A made-up stockroom's shelf counts, and a Stockroom project type."
ADDS = ["The Stockroom project type", "Shelf counts: GET /stockroom/count"]
REQUIRES: list[str] = []
AREAS = (("stockroom", "Stockroom: a made-up stockroom's shelf counts"),)

# Made-up shelves (never real data).
SHELVES = {"A1": 12, "A2": 0, "B1": 7}


def describe() -> dict[str, Any]:
    return {"id": ID, "name": NAME, "description": DESCRIPTION, "version": VERSION, "adds": ADDS}


# ===== routes: the composition root =====


def routes(seams: Any) -> list[BaseRoute]:
    async def count(request: Request) -> JSONResponse:
        return JSONResponse({"shelves": SHELVES, "total": sum(SHELVES.values())})

    return [Route("/stockroom/count", count)]


# ===== commands: the agent's =====


def commands() -> dict[str, Any]:
    from .commands import COMMANDS

    return COMMANDS
