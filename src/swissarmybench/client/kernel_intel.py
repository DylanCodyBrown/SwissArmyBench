"""Jedi's answers for the Workbench's editors: the member list, a call's parameter info and the hover.

Where a kernel has run, Jedi's Interpreter reads the kernel's own namespace (the live objects: a
DataFrame's columns, a function made in an earlier cell): the Workbench calls `ask()` as a user
expression in the kernel (nothing printed, nothing in the history). Where none has, the server calls
`answer()` with Jedi's Script over the document's text, its project folder (the scaffold files, pages,
scripts) and the document's environment's libraries.

Jedi ships with IPython (no new dependency). Nothing here reads a value whole: Jedi looks at types and
docstrings. Lines are 1-based and columns 0-based, as Jedi counts them.
"""

from __future__ import annotations

import json
import time
from typing import Any

from swissarmybench.domain import intellisense as rules

_MAX_ITEMS = 300
# Docstrings cost: the first ones are read until this long has passed, the rest come without.
_DOC_SECONDS = 0.35
_MAX_DOC = 4000


def _group(name: Any, path: str | None, project: str | None, namespace: dict[str, Any] | None) -> str:
    if name.type == "keyword":
        return "keyword"
    if name.type == "param":
        return "scope"
    module = str(name.module_path) if name.module_path else None
    if namespace is not None and name.name in namespace and name.module_name in ("__main__", ""):
        return "scope"
    if module is None or (path and module == path):
        return "scope" if name.module_name in ("__main__", "", None) or module == path else "library"
    if project and module.startswith(project):
        return "project"
    if name.module_name.split(".")[0] in ("swissarmybench", "swissarmygrid"):
        return "app"
    return "library"


def _returns(label: str) -> str:
    head, arrow, tail = label.rpartition(") -> ")
    return tail if arrow and head else ""


def _signature(sig: Any, origin: str = "") -> dict[str, Any]:
    """One signature for the page: its label, each parameter's span in it (the bold one), its words."""
    label = sig.to_string()
    doc = rules.parse_docstring(sig.docstring(raw=True))
    params = []
    at = label.find("(") + 1
    for p in sig.params:
        text = p.to_string()
        start = label.find(text, at)
        if start < 0:
            start = label.find(p.name, at)
            text = p.name
        span = [start, start + len(text)] if start >= 0 else None
        if start >= 0:
            at = start + len(text)
        kind = str(p.kind).rsplit(".", 1)[-1]
        params.append(
            {
                "name": p.name,
                "label": text,
                "span": span,
                "kind": kind,
                "required": "=" not in text and kind not in ("VAR_POSITIONAL", "VAR_KEYWORD"),
                "words": doc.params.get(p.name.lstrip("*"), ""),
                "type": doc.types.get(p.name, ""),
            }
        )
    return {
        "label": label,
        "name": sig.name,
        "params": params,
        "active": sig.index,
        "returns": _returns(label),
        "summary": doc.summary,
        "returns_words": doc.returns,
        "raises": list(doc.raises),
        "origin": origin or sig.module_name or "",
    }


def _script(request: dict[str, Any], namespace: dict[str, Any] | None, project: Any, environment: Any) -> Any:
    import jedi

    code = str(request["code"])
    if namespace is not None:
        return jedi.Interpreter(code, [namespace])
    return jedi.Script(code, path=request.get("path") or None, project=project, environment=environment)


def answer(
    request: dict[str, Any],
    namespace: dict[str, Any] | None = None,
    project: Any = None,
    environment: Any = None,
) -> dict[str, Any]:
    """{"ask": "complete" | "signature" | "hover", "code", "line", "column", "path"?, "folder"?}: Jedi's
    answer. `project` and `environment` are Jedi's (the server's Script); `namespace` the kernel's."""
    script = _script(request, namespace, project, environment)
    line, column = int(request["line"]), int(request["column"])
    path = request.get("path") or None
    folder = request.get("folder") or None
    ask = request.get("ask")
    if ask == "signature":
        return {"signatures": [_signature(s) for s in script.get_signatures(line, column)[:6]]}
    if ask == "hover":
        return _hover(script, line, column, _word(str(request["code"]), line, column), namespace)
    items = []
    deadline = time.monotonic() + _DOC_SECONDS
    for c in script.complete(line, column)[:_MAX_ITEMS]:
        group = _group(c, path, folder, namespace)
        item: dict[str, Any] = {
            "label": c.name,
            "kind": c.type,
            "group": group,
            "module": c.module_name or "",
        }
        if c.type in ("function", "class") and time.monotonic() < deadline:
            try:
                sigs = c.get_signatures()
            except Exception:
                sigs = []
            if sigs:
                item["detail"] = sigs[0].to_string()
                item["params"] = [
                    (
                        p.name,
                        "=" not in p.to_string() and not p.name.startswith("*"),
                        str(p.kind).endswith("KEYWORD_ONLY"),
                    )
                    for p in sigs[0].params
                ]
        if time.monotonic() < deadline and c.type != "keyword":
            try:
                doc = c.docstring(raw=True)
            except Exception:
                doc = ""
            if doc or item.get("detail"):
                origin = c.module_name if group in ("library", "project", "app") else ""
                item["documentation"] = rules.markdown_doc(
                    str(item.get("detail") or ""), doc[:_MAX_DOC], origin
                )
        elif c.type in ("statement", "instance") and namespace is not None and c.name in namespace:
            item["detail"] = type(namespace[c.name]).__name__
        items.append(item)
    return {"items": items}


def _word(code: str, line: int, column: int) -> str:
    lines = code.split("\n")
    text = lines[line - 1] if 0 < line <= len(lines) else ""
    start = column
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
        start -= 1
    end = column
    while end < len(text) and (text[end].isalnum() or text[end] == "_"):
        end += 1
    return text[start:end]


def _hover(
    script: Any, line: int, column: int, word: str, namespace: dict[str, Any] | None
) -> dict[str, Any]:
    """The name at the cursor: what it is (a signature, a type), its docstring, where it comes from. A
    kernel's variable says its type as it is now."""
    if namespace is not None and word in namespace and not callable(namespace[word]):
        kind = type(namespace[word])
        shape = getattr(namespace[word], "shape", None)
        size = f" ({' by '.join(str(n) for n in shape)})" if isinstance(shape, tuple) else ""
        return {"hover": f"_variable_\n\n```python\n{word}: {kind.__module__}.{kind.__qualname__}\n```{size}"}
    try:
        names = script.help(line, column) or script.infer(line, column)
    except Exception:
        names = []
    if not names:
        return {"hover": ""}
    n = names[0]
    try:
        sigs = n.get_signatures()
    except Exception:
        sigs = []
    if sigs:
        head = sigs[0].to_string()
    elif n.type == "instance":
        head = f"{n.name}: {n.full_name or n.name}"
    else:
        head = n.description
    try:
        doc = n.docstring(raw=True)
    except Exception:
        doc = ""
    origin = n.module_name if n.module_name not in ("__main__", "") else ""
    kind = {"instance": "variable", "statement": "variable"}.get(n.type, n.type)
    return {"hover": f"_{kind}_\n\n" + rules.markdown_doc(head, doc[:_MAX_DOC], origin)}


def ask(request_json: str) -> str:
    """In a Workbench kernel: Jedi's Interpreter over the kernel's own namespace. A JSON text back."""
    try:
        from IPython import get_ipython

        shell = get_ipython()
        namespace = dict(shell.user_ns) if shell is not None else {}
        return json.dumps(answer(json.loads(request_json), namespace=namespace))
    except Exception as error:  # Jedi stumbled: the server answers instead
        return json.dumps({"error": f"{type(error).__name__}: {error}"[:300]})


def names() -> str:
    """In a Workbench kernel: the names its namespace holds (for the lint's undefined names). JSON."""
    try:
        from IPython import get_ipython

        shell = get_ipython()
        found = [n for n in (shell.user_ns if shell is not None else {}) if not n.startswith("_")]
        return json.dumps(sorted(found)[:5000])
    except Exception:
        return "[]"
