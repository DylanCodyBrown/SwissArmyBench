"""TSX previews (phase 2): a TSX cell of a code app's data notebook drawn as a React component in the HTML
cells' walled-off frame, with its props from the notebook's values.

A TSX cell is a component module: its default export is drawn. Its first line may say its props as a
TypeScript expression worked out in the notebook's kernel (so a table a cell made is a prop):

    // props: { rows: byRegion, title: "Sales by region" }
    export default function Totals({ rows, title }: { rows: ByRegionRow[]; title: string }) { ... }

The project's own React (its node_modules, read, never changed or copied into the project) is bundled
with the component by `deno bundle` (Deno's own bundler, for the browser, no remote imports, no npm
downloads: `react` and `react-dom` resolved to the project's node_modules by an import map in the
notebook's temporary folder). The page is one document: the bundle inline, the props as JSON, nothing
loaded over the network. The front end hands it to the HTML cells' design frame (/blazor/design.html:
sandboxed without the app's origin, its Content-Security-Policy the base's html_cells.FRAME_POLICY).

Pure rules: the caller reads and writes the files and runs the bundler.
"""

from __future__ import annotations

import json
import re
from typing import Any

from swissarmybench.domain.html_cells import FRAME_POLICY

POLICY = FRAME_POLICY  # the HTML cells' frame: the same words (a test compares them)
MAX_PROPS_CHARS = 2_000_000
MAX_BUNDLE_CHARS = 8_000_000
_PROPS_LINE = re.compile(r"^\s*//\s*props\s*:\s*(.+?)\s*$")
_DEFAULT = re.compile(r"^\s*export\s+default\b", re.MULTILINE)
REACT_FILES = {
    "react": "react/index.js",
    "react/jsx-runtime": "react/jsx-runtime.js",
    "react/jsx-dev-runtime": "react/jsx-dev-runtime.js",
    "react-dom": "react-dom/index.js",
    "react-dom/client": "react-dom/client.js",
}


class PreviewError(ValueError):
    """A TSX cell that cannot be previewed, said plainly."""


def props_expression(source: str) -> str | None:
    """The props a TSX cell asks for (its first line's `// props: ...`), or None."""
    first = next((line for line in source.splitlines() if line.strip()), "")
    found = _PROPS_LINE.match(first)
    return found.group(1) if found else None


def props_code(expression: str | None) -> str:
    """Kernel code whose result is the props as JSON (application/json): the expression worked out with the
    notebook's values, a table result as its rows."""
    if not expression:
        return '({ [Symbol.for("Jupyter.display")]() { return { "application/json": {} }; } })'
    if "\n" in expression:
        raise PreviewError("The props are one line: // props: { rows: byRegion }")
    return (
        "await (async () => { const __sabProps = await (" + expression + "); "
        'return { [Symbol.for("Jupyter.display")]() { return { "application/json": '
        "JSON.parse(JSON.stringify(__sabProps ?? {})) }; } }; })()"
    )


def check_component(source: Any) -> str:
    if not isinstance(source, str) or not source.strip():
        raise PreviewError("The TSX cell is empty: write a component (export default function ...).")
    if not _DEFAULT.search(source):
        raise PreviewError(
            "A TSX cell draws its default export: write `export default function Name() {...}`."
        )
    return source


def missing_react(present: dict[str, bool]) -> str | None:
    """What the project lacks to draw a component (its node_modules' react and react-dom), or None."""
    lacking = [name for name in ("react", "react-dom") if not present.get(name)]
    if not lacking:
        return None
    return (
        f"The code app has no {' or '.join(lacking)} in its node_modules: install its packages first "
        "(npm install in the code app's folder)."
    )


def config(node_modules: str) -> str:
    """The bundler's deno.json (in the notebook's temporary folder): React resolved to the project's own
    node_modules (absolute file addresses), and TSX compiled for React's automatic runtime."""
    root = node_modules.replace("\\", "/").rstrip("/")
    prefix = "file:///" + root.lstrip("/")
    imports = {name: f"{prefix}/{path}" for name, path in REACT_FILES.items()}
    imports |= {"react/": f"{prefix}/react/", "react-dom/": f"{prefix}/react-dom/"}
    options = {"jsx": "react-jsx", "jsxImportSource": "react", "lib": ["dom", "dom.iterable", "esnext"]}
    return json.dumps({"imports": imports, "compilerOptions": options}, indent=2) + "\n"


ENTRY = """\
import { createElement } from "react";
import { createRoot } from "react-dom/client";
import Component from "./component.tsx";
const props = (globalThis as Record<string, unknown>).__SAB_PROPS__ ?? {};
const root = document.getElementById("root");
if (root) createRoot(root).render(createElement(Component as never, props as never));
"""


def bundle_argv(deno: str, entry: str, output: str, config_file: str) -> list[str]:
    """`deno bundle` for the browser: its deno.json (config) only, no remote or npm imports."""
    return [
        deno, "bundle", "--platform", "browser", "--format", "esm", "--no-remote", "--no-npm",
        "--no-lock", "--minify", "--config", config_file, "-o", output, entry,
    ]  # fmt: skip


def _script_safe(text: str) -> str:
    return re.sub(r"</(script)", r"<\\/\1", text, flags=re.IGNORECASE)


def page(bundle: str, props: Any, title: str = "Component") -> str:
    """The preview's one document: the props, then the bundle, both inline (the frame loads nothing)."""
    if len(bundle) > MAX_BUNDLE_CHARS:
        raise PreviewError("The component's bundle is too large to preview.")
    said = json.dumps(props if props is not None else {}, ensure_ascii=False)
    if len(said) > MAX_PROPS_CHARS:
        raise PreviewError("The props are too large to preview: pass fewer rows.")
    said = said.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    safe_title = re.sub(r"[<>&\"']", "", title)[:80]
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8" />\n'
        f"<title>{safe_title}</title>\n"
        "<style>body{margin:12px;font-family:system-ui,sans-serif;font-size:14px}</style>\n"
        '</head>\n<body>\n<div id="root"></div>\n'
        f"<script>window.__SAB_PROPS__ = {said};</script>\n"
        f'<script type="module">\n{_script_safe(bundle)}\n</script>\n</body>\n</html>\n'
    )


def bundle_error(output: str) -> str:
    """The bundler's complaint in a few lines (colour codes and its own warnings out)."""
    lines = [
        re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)
        for line in (output or "").splitlines()
        if "experimental" not in line and line.strip()
    ]
    return "\n".join(lines[-12:]) or "The component could not be bundled."
