"""Export as one Python script (services/script_export.py), for the Workbench window and the agent
(the golden rule: `workbench_export_script`).

POST /workbench/export-script  {"path", "cells"? | "text"?, "kind"?, "to"?, "stub"?, "check"?}: the
                               notebook or script as one .py that runs with plain `python <file>`
"""

from __future__ import annotations

from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import with_body
from swissarmybench.services.script_export import ScriptExports


def routes(exports: ScriptExports) -> list[BaseRoute]:
    return [Route("/workbench/export-script", with_body(exports.export), methods=["POST"])]
