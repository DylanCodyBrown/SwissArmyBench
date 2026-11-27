"""A code app's files as the app shows them: only the ones a person edits.

The owner (2026-11-17): "the project template is going to expose only the files that have to be touched in
the code app. Everything else makes it into the project folder but does not need to be exposed in the app,
only .ts files." And: each page owns everything it needs (domain/pages.py).

**Shown** (docs/ideas.md has the survey of what Microsoft's template, `pa app init` and `pa app add
data-source` write, and why each is shown or hidden): the `.ts` and `.tsx` files of `src/pages/` (each page's
folder), `src/shared/` (what pages share), `src/pages.ts` (the list of pages) and `src/App.tsx`. **Hidden**
(still in the folder, for Git, VS Code and pa): `main.tsx` (the template's entry), `src/generated/` (pa writes
the models and services again on every refresh), the template's demo CSS and pictures, `index.html`,
`package.json`, the TypeScript, Vite and ESLint configs, `power.config.json`, `.power/`, `.sab/`,
`node_modules/`, `dist/`. "Show all files" lists everything; a hidden file is read by its path.

Pure rules over paths.
"""

from __future__ import annotations

from collections.abc import Iterable

SHOWN_FOLDERS = ("src/pages/", "src/shared/")
SHOWN_FILES = frozenset({"src/pages.ts", "src/App.tsx"})


def shown(path: str) -> bool:
    """A file a person edits in a code app: a page's, a shared one, the list of pages, or App.tsx."""
    rel = path.replace("\\", "/").lstrip("/")
    if not rel.endswith((".ts", ".tsx")) or rel.endswith(".d.ts"):
        return False
    return rel in SHOWN_FILES or rel.startswith(SHOWN_FOLDERS)


def shown_files(paths: Iterable[str]) -> list[str]:
    """The shown ones of a folder's files, by path in any case's order."""
    return sorted((p.replace("\\", "/") for p in paths if shown(p)), key=str.casefold)
