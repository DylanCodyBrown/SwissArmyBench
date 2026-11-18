"""What the language server holds of the editors' documents, and the messages that keep it current.

The README asks for textDocument/didOpen, didChange (incremental) and didClose; the server also takes
notebookDocument/* (its initialize answer lists notebookDocumentSync), so a notebook is sent as a notebook:
its code cells, each a text document of its own, and a completion is asked in the cell being edited (the
server reads the notebook's other code cells as its context).

Only what the editor sent is sent: a script's text, or a notebook's code cells' text (never an output, a
table's rows or a variable's value). The addresses are made up (file:///swissarmybench/<key>/<name>): no
folder of the user's is named, so the server has nothing of theirs to read on its own.

  Mirror.text(key, name, language, text)       -> (uri, version, messages)
  Mirror.notebook(key, name, cells, current)   -> (the current cell's uri, its version, messages)
  Mirror.close_all()                           -> messages (didClose for each)

At most MAX_DOCUMENTS are held; the one used longest ago is closed for a new one. Pure: no I/O, no clock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from swissarmybench_copilot.domain.lsp import change_between, notification

MAX_DOCUMENTS = 20
MAX_TEXT = 512 * 1024  # a document longer than this is not sent (the server skips such files too)
MAX_CELLS = 400
LANGUAGES = ("python", "sql")
ROOT = "file:///swissarmybench"
NOTEBOOK_TYPE = "jupyter-notebook"


class DocumentError(ValueError):
    """What the editor sent is not a document this sends."""


def _key(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip("-.")[:80]
    if not text:
        raise DocumentError("A document needs its key.")
    return text


def _name(value: Any, default: str) -> str:
    text = str(value or "").replace("\\", "/").rsplit("/", 1)[-1].strip()[:120]
    return text or default


def language_of(value: Any) -> str:
    text = str(value or "python").lower()
    if text not in LANGUAGES:
        raise DocumentError(f"{text} is not a language completions are asked for ({', '.join(LANGUAGES)}).")
    return text


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise DocumentError("A document's text is a string.")
    if len(value) > MAX_TEXT:
        raise DocumentError("The document is too long to send.")
    return value


@dataclass
class _Text:
    uri: str
    language: str
    version: int
    text: str


@dataclass
class _Notebook:
    uri: str
    version: int
    cells: list[_Text] = field(default_factory=list)


@dataclass
class Mirror:
    texts: dict[str, _Text] = field(default_factory=dict)
    notebooks: dict[str, _Notebook] = field(default_factory=dict)
    used: list[str] = field(default_factory=list)  # uris, the one used last at the end

    # ===== a script (one text document) =====

    def text(self, key: Any, name: Any, language: Any, text: Any) -> tuple[str, int, list[dict[str, Any]]]:
        lang, body = language_of(language), _text(text)
        uri = f"{ROOT}/{_key(key)}/{quote(_name(name, 'script.py'))}"
        out = self._room(uri)
        held = self.texts.get(uri)
        if held is None:
            held = _Text(uri, lang, 1, body)
            self.texts[uri] = held
            out.append(notification("textDocument/didOpen", {"textDocument": _item(held)}))
        else:
            change = change_between(held.text, body)
            if change is not None:
                held.version += 1
                held.text = body
                out.append(
                    notification(
                        "textDocument/didChange",
                        {"textDocument": {"uri": uri, "version": held.version}, "contentChanges": [change]},
                    )
                )
        self._touch(uri)
        return uri, held.version, out

    # ===== a notebook (its code cells) =====

    def notebook(
        self, key: Any, name: Any, cells: Any, current: Any
    ) -> tuple[str, int, list[dict[str, Any]]]:
        """`cells`: the notebook's code cells in order, each {"id", "text", "language"}; `current`: the id of
        the cell being edited."""
        if not isinstance(cells, list) or not cells or len(cells) > MAX_CELLS:
            raise DocumentError("A notebook is sent with its code cells (1 to 400).")
        uri = f"{ROOT}/{_key(key)}/{quote(_name(name, 'notebook.ipynb'))}"
        wanted: list[tuple[str, str, str]] = []
        for cell in cells:
            if not isinstance(cell, dict):
                raise DocumentError("Each cell is {id, text, language}.")
            cell_uri = f"{uri}#cell-{_key(cell.get('id'))}"
            wanted.append((cell_uri, language_of(cell.get("language")), _text(cell.get("text", ""))))
        if len({w[0] for w in wanted}) != len(wanted):
            raise DocumentError("Two cells have the same id.")
        if sum(len(w[2]) for w in wanted) > MAX_TEXT:
            raise DocumentError("The notebook is too long to send.")
        mine = f"{uri}#cell-{_key(current)}"
        if mine not in {w[0] for w in wanted}:
            raise DocumentError("The cell being edited is not among the cells sent.")
        out = self._room(uri)
        held = self.notebooks.get(uri)
        if held is None:
            held = _Notebook(uri, 1, [_Text(u, lang, 1, t) for u, lang, t in wanted])
            self.notebooks[uri] = held
            out.append(
                notification(
                    "notebookDocument/didOpen",
                    {
                        "notebookDocument": {
                            "uri": uri,
                            "notebookType": NOTEBOOK_TYPE,
                            "version": held.version,
                            "cells": [{"kind": 2, "document": c.uri} for c in held.cells],
                        },
                        "cellTextDocuments": [_item(c) for c in held.cells],
                    },
                )
            )
        else:
            change = self._notebook_change(held, wanted)
            if change:
                held.version += 1
                out.append(
                    notification(
                        "notebookDocument/didChange",
                        {
                            "notebookDocument": {"uri": uri, "version": held.version},
                            "change": {"cells": change},
                        },
                    )
                )
        self._touch(uri)
        cell = next(c for c in held.cells if c.uri == mine)
        return cell.uri, cell.version, out

    def _notebook_change(self, held: _Notebook, wanted: list[tuple[str, str, str]]) -> dict[str, Any]:
        change: dict[str, Any] = {}
        before = {c.uri: c for c in held.cells}
        order = [w[0] for w in wanted]
        languages = {u: lang for u, lang, _ in wanted}
        if order != [c.uri for c in held.cells] or any(
            before[u].language != lang for u, lang in languages.items() if u in before
        ):
            # The cells moved, came or went (or one's language changed): the whole list again, the new ones
            # opened, the gone closed.
            kept = {u: c for u, c in before.items() if languages.get(u) == c.language}
            opened = [_Text(u, lang, 1, t) for u, lang, t in wanted if u not in kept]
            closed = [c for u, c in before.items() if u not in kept]
            cells = [kept.get(u) or next(o for o in opened if o.uri == u) for u in order]
            change["structure"] = {
                "array": {
                    "start": 0,
                    "deleteCount": len(held.cells),
                    "cells": [{"kind": 2, "document": c.uri} for c in cells],
                },
                "didOpen": [_item(c) for c in opened],
                "didClose": [{"uri": c.uri} for c in closed],
            }
            held.cells = cells
        texts = []
        now = {c.uri: c for c in held.cells}
        for u, _, t in wanted:
            cell = now[u]
            edit = change_between(cell.text, t)
            if edit is not None:
                cell.version += 1
                cell.text = t
                texts.append({"document": {"uri": u, "version": cell.version}, "changes": [edit]})
        if texts:
            change["textContent"] = texts
        return change

    # ===== closing =====

    def close(self, uri: str) -> list[dict[str, Any]]:
        if uri in self.texts:
            del self.texts[uri]
            self.used = [u for u in self.used if u != uri]
            return [notification("textDocument/didClose", {"textDocument": {"uri": uri}})]
        held = self.notebooks.pop(uri, None)
        if held is None:
            return []
        self.used = [u for u in self.used if u != uri]
        return [
            notification(
                "notebookDocument/didClose",
                {"notebookDocument": {"uri": uri}, "cellTextDocuments": [{"uri": c.uri} for c in held.cells]},
            )
        ]

    def close_all(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for uri in [*self.texts, *self.notebooks]:
            out += self.close(uri)
        return out

    def clear(self) -> None:
        """The server went away: it holds nothing now."""
        self.texts.clear()
        self.notebooks.clear()
        self.used.clear()

    def _room(self, uri: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while uri not in self.used and len(self.used) >= MAX_DOCUMENTS:
            out += self.close(self.used[0])
        return out

    def _touch(self, uri: str) -> None:
        self.used = [u for u in self.used if u != uri] + [uri]


def _item(doc: _Text) -> dict[str, Any]:
    return {"uri": doc.uri, "languageId": doc.language, "version": doc.version, "text": doc.text}
