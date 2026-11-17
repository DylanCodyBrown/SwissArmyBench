"""A code app's files as the app shows them: only the ones a person edits.

The owner (2026-11-17): "the project template is going to expose only the files that have to be touched in
the code app. Everything else makes it into the project folder but does not need to be exposed in the app,
only .ts files."

**Shown** (docs/ideas.md has the survey of what Microsoft's template, `pa app init` and `pa app add
data-source` write, and why each is shown or hidden): the `.ts` and `.tsx` files under `src/` that a person
edits: `App.tsx`, `data.ts` (the data notebook's export) and any module of their own. **Hidden** (still in the
folder, for Git, VS Code and pa): `main.tsx` (the template's entry: it renders App and is not changed),
`src/generated/` (pa writes the models and services again on every refresh), `*.d.ts`, CSS and pictures,
`index.html`, `package.json`, the TypeScript, Vite and ESLint configs, `power.config.json`, `.power/`,
`.sab/`, `node_modules/`, `dist/`. "Show all files" lists everything; a hidden file is read by its path.

Pure rules over paths.
"""

from __future__ import annotations

from collections.abc import Iterable

HIDDEN_UNDER_SRC = ("src/generated/",)
HIDDEN_FILES = frozenset({"src/main.tsx", "src/vite-env.d.ts"})


def shown(path: str) -> bool:
    """A file a person edits in a code app: a .ts or .tsx under src/, not generated, not a declaration
    file, not the template's entry."""
    rel = path.replace("\\", "/").lstrip("/")
    if not rel.startswith("src/") or not rel.endswith((".ts", ".tsx")) or rel.endswith(".d.ts"):
        return False
    return rel not in HIDDEN_FILES and not rel.startswith(HIDDEN_UNDER_SRC)


def shown_files(paths: Iterable[str]) -> list[str]:
    """The shown ones of a folder's files, by path in any case's order."""
    return sorted((p.replace("\\", "/") for p in paths if shown(p)), key=str.casefold)
