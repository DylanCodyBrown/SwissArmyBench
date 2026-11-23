"""The page's pure modules run as the page runs them (the front end's unit tests): a module of web/src is
bundled by the page's own esbuild and its exported functions are called by Node, each call a list of
[name, ...arguments]. Skipped where Node or the page's packages are not there (needs_node)."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
ESBUILD = WEB / "node_modules" / ".bin" / "esbuild"

needs_node = pytest.mark.skipif(
    shutil.which("node") is None or not ESBUILD.exists(), reason="Node and the page's packages are needed"
)

# The calls run in order in one process, so a call that sets something (usePageRules) holds for the next.
_CALLS = """
import * as module from "./module.mjs";
const asked = JSON.parse(process.argv[2]);
const out = [];
for (const [name, ...args] of asked) out.push((await module[name](...args)) ?? null);
console.log(JSON.stringify(out));
"""


def bundled(folder: Path, source: str, more: str = "") -> Callable[..., list[Any]]:
    """web/src/<source> bundled into `folder`; the answer calls its exported functions: run([name, *args],
    ...) gives each call's result, in order (undefined as None). `more`: TypeScript added beside the
    module's exports (a small caller, where a function takes what JSON cannot carry); it names the module
    as "@module"."""
    module = (WEB / "src" / source).as_posix()
    entry = folder / "entry.ts"
    entry.write_text(
        f'export * from "{module}";\n' + more.replace('"@module"', f'"{module}"'), encoding="utf-8"
    )
    built = subprocess.run(  # noqa: S603
        [
            str(ESBUILD),
            str(entry),
            "--bundle",
            "--format=esm",
            "--platform=node",
            f"--outfile={folder / 'module.mjs'}",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert built.returncode == 0, built.stderr
    (folder / "calls.mjs").write_text(_CALLS, encoding="utf-8")

    def run(*asked: list[Any]) -> list[Any]:
        done = subprocess.run(  # noqa: S603
            ["node", str(folder / "calls.mjs"), json.dumps(asked)],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert done.returncode == 0, done.stderr
        return list(json.loads(done.stdout))

    return run
