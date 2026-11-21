"""Lineage with values (services/lineage.py), for the Workbench window and the agent.

POST   /workbench/lineage    {"document", "cell", "cells"?|"text"?, "kernel"?, "errors"?, "values"?} or
                             {"app", "page", "block", "values"?}: from that cell or canvas block back
                             through every cell to the data: the nodes in flow order, the edges, the
                             Mermaid text, and each node's value, summarised
"""

from __future__ import annotations

from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import with_body
from swissarmybench.services.lineage import Lineage


def routes(lineage: Lineage) -> list[BaseRoute]:
    return [Route("/workbench/lineage", with_body(lineage.trace), methods=["POST"])]
