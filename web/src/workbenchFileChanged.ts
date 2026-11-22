/**
 * workbenchFileChanged.ts: a document whose file changed anywhere (the owner, 2026-11-21: "scripts autoupdate
 * when they are touched anywhere in the app"; services/code_files.py's file_changed notice). Moved out of
 * workbenchPage.ts along its own heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [FOLLOW]  a document with nothing unsaved is read again in place (a script's text with its cursor and
 *             scroll kept; a notebook's cells, the same tab and kernel); this window's own save says nothing
 *   [BAR]     one with unsaved edits, or whose file is gone, gets a bar over it: Reload, Keep mine, Compare
 *             (Monaco's diff editor); a gone file: Save as…, Close. Never silently overwritten
 *
 * ROUTING: POST /workbench/open (the file as it is now)
 */
import { api } from "./api";
import { button, h, icon, openDialog } from "./dom";
import { errorHere, errorToast } from "./errorNote";
import { effectiveTheme } from "./theme";
import type { CellData, NotebookView } from "./workbenchNotebook";
import type { Doc } from "./workbenchPage";

/** What the watcher asks of the page: its documents and the one in front, a notebook's view made again, its
 *  redraws, Save and Close, and the Files pane read again. */
export interface FileChangedHost {
  docs: () => Doc[];
  current: () => Doc | null;
  notebookOf: (doc: Doc, cells: CellData[], nextCell?: number) => NotebookView;
  drawTablesTool: () => void;
  drawTabs: () => void;
  remember: () => void;
  save: (doc: Doc | null, as?: boolean) => Promise<boolean>;
  close: (doc: Doc) => void;
  refreshFiles: () => void;
}

export interface FileChanged {
  /** A file_changed notice: each document of that file follows (in place when unchanged here). */
  changed: (path: string, hash: string | null) => void;
  /** The bar over a document goes (it was saved, or its choice was made). */
  clear: (doc: Doc) => void;
}

export function fileChangedWatcher(host: FileChangedHost): FileChanged {
  function clearElsewhere(doc: Doc): void {
    doc.elsewhere?.bar.remove();
    delete doc.elsewhere;
  }

  type Reread = { path: string; modified: number; text?: string; cells?: CellData[]; next_cell?: number; hash?: string | null };

  /** The document read again from its file: a script's text in place (its cursor and scroll kept), a notebook's
   *  cells as they are now. */
  async function reloadDoc(doc: Doc): Promise<void> {
    const found = await api<Reread>("/workbench/open", "POST", { path: doc.path });
    if (doc.script) doc.script.replaceText(found.text ?? "");
    else if (doc.notebook) {
      // In place (the owner, 2026-11-21: notebooks follow a change as scripts do): the same tab, the same kernel
      // and its names, the selected cell kept where it can be; only the cells are the file's now.
      const at = doc.notebook.selected();
      const old = doc.notebook;
      const fresh = host.notebookOf(doc, found.cells ?? [], found.next_cell);
      old.element.replaceWith(fresh.element);
      old.dispose();
      doc.notebook = fresh;
      if (at >= 0 && at < (found.cells ?? []).length) fresh.select(at);
      if (doc === host.current()) host.drawTablesTool();
    }
    doc.modified = found.modified;
    doc.hash = found.hash ?? null;
    doc.dirty = false;
    clearElsewhere(doc);
    host.drawTabs();
    host.remember();
  }

  /** Its file and this window's text side by side (Monaco's diff editor). */
  async function compareDoc(doc: Doc): Promise<void> {
    const found = await api<Reread>("/workbench/open", "POST", { path: doc.path });
    const mine = doc.script?.text() ?? JSON.stringify(doc.notebook?.cells().map((c) => c.source) ?? [], null, 1);
    const theirs = found.text ?? JSON.stringify((found.cells ?? []).map((c) => c.source), null, 1);
    const { dialog, body } = openDialog(`${doc.title}: the file, and yours`, true);
    const host = h("div", { class: "wb-compare", style: { height: "60vh" } });
    body.append(host);
    const lib = (await import(/* external */ "/static/build/lazy/codeEditor.js" as string)) as typeof import("./lazy/codeEditor");
    const viewer = lib.createDiffViewer(host, effectiveTheme());
    viewer.show(theirs, mine, doc.path ?? doc.title);
    dialog.addEventListener("close", () => viewer.dispose());
  }

  /** The bar over a document whose file changed elsewhere while it was edited here (or went away). */
  function elsewhereBar(doc: Doc, hash: string | null): void {
    clearElsewhere(doc);
    const guard = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => errorHere(e));
    const bar = h(
      "div",
      { class: "wb-elsewhere", role: "status" },
      icon("warning"),
      h("span", {}, hash === null ? "This file is gone." : "Changed elsewhere."),
      ...(hash === null
        ? [button("Save as…", () => void host.save(doc, true), { class: "line" }), button("Close", () => host.close(doc), { class: "ghost" })]
        : [
            button("Reload", guard(() => reloadDoc(doc)), { class: "primary" }),
            button(
              "Keep mine",
              guard(async () => {
                const found = await api<Reread>("/workbench/open", "POST", { path: doc.path });
                doc.modified = found.modified; // Save writes this window's text over it
                doc.hash = found.hash ?? null;
                clearElsewhere(doc);
              }),
              { class: "line" },
            ),
            button("Compare", guard(() => compareDoc(doc)), { class: "ghost" }),
          ]),
    );
    doc.elsewhere = { hash, bar };
    doc.element.prepend(bar);
  }

  /** A file_changed notice: each document of that file follows (in place when unchanged here). */
  function fileChanged(path: string, hash: string | null): void {
    for (const doc of host.docs().filter((d) => d.path === path)) {
      if (doc.structure) {
        doc.structure.changedOnDisk(hash); // the structure's own (taken at once when clean; else Reload / Keep mine)
        continue;
      }
      if (hash !== null && hash === doc.hash) continue; // this window's own save, or the same text
      if (hash === null || doc.dirty || !(doc.script || doc.notebook)) elsewhereBar(doc, hash);
      else void reloadDoc(doc).catch((e: Error) => errorToast(e));
    }
    host.refreshFiles();
  }

  return { changed: fileChanged, clear: clearElsewhere };
}
