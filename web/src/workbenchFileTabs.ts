/**
 * workbenchFileTabs.ts: the Workbench's tabs that are not a notebook or a script: a structure's file beside the
 * code, a library's source read-only, a code app's file. Moved out of workbenchPage.ts along its own headings
 * (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [STRUCTURE] a JSON, YAML, XML or TOML file (or an open structure by its id) as a tab, one tab a file: its
 *               tree and its text, an IDE (structureDoc.ts; 2026-11-22, the owner: "I want it beside the ide so
 *               you can search and explore"), on the page it was opened from
 *   [LIBRARY]   an installed library's file, read-only (go to definition outside the project: the owner's IDE
 *               shows it), at a line
 *   [CODEFILE]  a code app's file (the Power Apps extension's plug-in: workbenchCodeFile.ts): TypeScript or TSX
 *               with Monaco's own language service; New makes one in the mode's first language
 *
 * ROUTING: POST /scripts/library-file, DELETE /structures/{id} (a closed tab's, in the page's close).
 */
import { api } from "./api";
import { askText, h, icon } from "./dom";
import { errorHere } from "./errorNote";
import { activeMode } from "./modes";
import { openStructures } from "./lazyPages";
import { openStructureDoc, type StructureDoc } from "./structureDoc";
import type { Part } from "./structureTree";
import { effectiveTheme } from "./theme";
import { newCodeFile, openCodeFile } from "./workbenchCodeFile";
import type { Doc } from "./workbenchPage";

/** What these tabs ask of the page: its documents, a tab made, shown and closed, the tabs and the Files pane
 *  drawn again, and the editors. */
export interface FileTabsHost {
  docs: Doc[];
  makeDoc: (kind: Doc["kind"], title: string, path: string | null, modified: number | null) => Doc;
  show: (doc: Doc) => void;
  close: (doc: Doc, moved?: boolean) => void;
  drawTabs: () => void;
  remember: () => void;
  filesChanged: () => void;
  editors: () => Promise<typeof import("./lazy/codeEditor")>;
  readonly current: Doc | null;
}

const baseName = (path: string): string => path.split(/[\\/]/).pop() ?? path;

export function fileTabs(host: FileTabsHost) {
  const { docs, makeDoc, show, close, drawTabs, remember } = host;

  // ===== a structure's file beside the code (2026-11-22, the owner: "I want it beside the ide so you can search
  // and explore"): its tree and its text, an IDE (structureDoc.ts), on the page it was opened from =====

  /** A Python document is open in this window: the structure's Copy as code is offered. */
  const pythonBeside = (): boolean => docs.some((d) => d.kind === "script" || d.kind === "notebook");

  /** A structure's file (or an open structure by its id) as a tab in the focused group; one tab a file. `at`: a
   *  node to select. */
  async function openStructureTab(target: { path?: string; id?: string }, at: Part[] | null = null): Promise<Doc | null> {
    const already = docs.find((d) => d.structure && ((target.path && d.path === target.path) || (target.id && d.structure.id === target.id)));
    if (already) {
      show(already);
      if (at?.length) already.structure!.select(at);
      return already;
    }
    const doc = makeDoc("structure", target.path ? baseName(target.path) : "Structure", target.path ?? null, null);
    let view: StructureDoc | null = null;
    try {
      view = await openStructureDoc(
        target,
        {
          pythonBeside,
          dirty: (dirty) => {
            if (doc.dirty === dirty) return;
            doc.dirty = dirty;
            drawTabs();
          },
          renamed: (title, path) => {
            doc.title = title;
            doc.path = path;
            drawTabs();
            remember();
            host.filesChanged();
          },
          close: () => close(doc, true),
          openPage: (id) => openStructures(id),
        },
        at,
      );
    } catch (e) {
      docs.splice(docs.indexOf(doc), 1);
      errorHere(e);
      return null;
    }
    if (!view) {
      docs.splice(docs.indexOf(doc), 1); // a missing package: its prompt is up
      return null;
    }
    doc.structure = view;
    doc.path = view.path() ?? doc.path;
    if (!target.path) doc.title = view.title();
    doc.element.append(view.element);
    show(doc);
    return doc;
  }

  /** The structure in front (or the one of `path`), for the palette's and the agent's structure commands. */
  function structureOf(args: Record<string, unknown>): StructureDoc {
    const path = typeof args.path === "string" ? args.path : null;
    const doc = path ? docs.find((d) => d.structure && d.path === path) : host.current?.structure ? host.current : docs.find((d) => d.structure);
    if (!doc?.structure) throw new Error(path ? `${path} is not open as a structure here: structure.open opens it.` : "No structure is open here: structure.open opens one.");
    if (doc !== host.current) show(doc);
    return doc.structure;
  }

  // ===== a library's source, read-only (go to definition outside the project: the owner's IDE shows it) =====

  /** An installed library's file in a tab of its own, read-only (marked so), at `line`; one tab a file. */
  async function openLibraryDoc(path: string, line: number, module: string | null): Promise<void> {
    const already = docs.find((d) => d.kind === "library" && d.path === path);
    if (already) {
      show(already);
      already.libraryAt?.(line);
      return;
    }
    const said = await api<{ text: string }>("/scripts/library-file", "POST", { path });
    const doc = makeDoc("library", baseName(path), path, null);
    const codeHost = h("div", { class: "wb-library-code", "data-own-zoom": "" });
    doc.element.append(
      h("div", { class: "wb-library-bar", role: "note" }, icon("key"), h("span", { class: "chip ide-readonly" }, "read-only"), h("span", { class: "hint", title: path }, module ?? path)),
      codeHost,
    );
    show(doc);
    const m = await host.editors();
    const editor = m.createCodeEditor(codeHost, { language: path.endsWith(".pyi") || path.endsWith(".py") ? "python" : "plaintext", value: said.text, theme: effectiveTheme(), readOnly: true, readOnlyMessage: "A library's own source: read-only here." });
    doc.libraryAt = (at) => editor.reveal(at, 1);
    editor.reveal(line, 1);
  }

  // ===== a code app's files (the Power Apps extension's plug-in: workbenchCodeFile.ts) =====

  /** A file of the open code app, in the editor (TypeScript or TSX with Monaco's own language service). */
  async function openCodeFileDoc(path: string): Promise<void> {
    const already = docs.find((d) => d.kind === "codefile" && d.codefile?.path === path);
    if (already) return show(already);
    const doc = makeDoc("codefile", baseName(path), path, null);
    try {
      doc.codefile = await openCodeFile(path, effectiveTheme(), () => {
        if (!doc.dirty) {
          doc.dirty = true;
          drawTabs();
        }
      });
    } catch (e) {
      docs.splice(docs.indexOf(doc), 1);
      errorHere(e);
      return;
    }
    doc.element.append(doc.codefile.element);
    show(doc);
  }

  /** The mode's first language when it is not Python: New makes a file of it (a code app: TypeScript). */
  const scriptLanguage = (): string | null => {
    const first = activeMode().mode.languages[0];
    return first && first !== "python" ? first : null;
  };
  const LANGUAGE_WORDS: Record<string, string> = { typescript: "TypeScript", tsx: "TSX", python: "Python" };
  async function newModeFile(language: string): Promise<void> {
    const ending = language === "tsx" ? ".tsx" : ".ts";
    const name = await askText(`New ${LANGUAGE_WORDS[language] ?? language} file (in src/shared, or a path under src/pages/<Page>/)`, `module${ending}`);
    if (!name) return;
    try {
      const path = await newCodeFile(name.endsWith(ending) || /\.(ts|tsx)$/.test(name) ? name : `${name}${ending}`);
      await openCodeFileDoc(path);
    } catch (e) {
      errorHere(e);
    }
  }

  return { openStructureTab, structureOf, openLibraryDoc, openCodeFileDoc, scriptLanguage, newModeFile, LANGUAGE_WORDS };
}
