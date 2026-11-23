/**
 * workbenchMove.ts: a document MOVES to another Workbench window (the owner, 2026-11-15). Moved out of
 * workbenchPage.ts along its own heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   Popped out into a window of its own, or moved back to the main window: its unsaved text, its cell
 *   numbers, its outputs and its running kernel go with it, and this window's tab closes once the other
 *   has taken it (the server holds it on the way: /workbench/handoffs). Never two live copies.
 *
 * ROUTING: POST /workbench/handoffs, GET and DELETE /workbench/handoffs/{id}, POST .../{id}/take
 */
import { api, token } from "./api";
import type { ExplorerState } from "./dataExplorer";
import type { Descriptions } from "./workbenchDocModes";
import { WINDOW_ID } from "./workbenchKernel";
import type { CellData } from "./workbenchNotebook";
import type { Doc, PythonChoice } from "./workbenchPage";
import type { CodePage } from "./workbenchPages";
import type { Remembered } from "./workbenchRestore";

/** What a move asks of the page: which documents move, this window's place, a document opened and closed,
 *  an Explorer's search handed back, and the page's redraws. */
export interface MoveHost {
  page: CodePage;
  moves: (doc: Doc) => boolean;
  isMainWindow: () => boolean;
  close: (doc: Doc, moved?: boolean) => void;
  explorerBack: (state: ExplorerState) => void;
  openNotebook: (path: string | null, cells: CellData[], modified: number | null, nextCell?: number, dictionary?: Descriptions) => Doc;
  openScript: (path: string | null, text: string, modified: number | null) => Doc;
  show: (doc: Doc) => void;
  drawTabs: () => void;
  drawStatus: () => void;
  remember: () => void;
  dataBody: (doc: Doc) => { dictionary?: Descriptions };
  readonly pythons: PythonChoice[];
}

export function documentMoves(host: MoveHost) {
  const { page, moves, isMainWindow, close, explorerBack, openNotebook, openScript, show, drawTabs, drawStatus, remember, dataBody } = host;

  /** A document as it moves: everything the window holds of it. */
  function movingState(doc: Doc): Remembered & { title: string } {
    return {
      kind: doc.notebook ? "notebook" : "script",
      path: doc.path,
      title: doc.title,
      modified: doc.modified,
      dirty: doc.dirty,
      python: doc.python,
      ...(doc.notebook ? { cells: doc.notebook.cells(), next_cell: doc.notebook.nextCell(), ...dataBody(doc) } : { text: doc.script!.text() }),
    };
  }

  /** Hand a document to another window (`to`: a window's id; null: a new window, opened for it). Its
   *  tab here closes once that window has taken it; if none does, it stays. */
  async function moveOut(doc: Doc, to: string | null): Promise<{ title: string; window: "new" | "main" }> {
    if (!moves(doc)) throw new Error("Only a notebook, a script or a Streamlit app moves to another window.");
    const kernel = doc.kernel?.id ?? null;
    const { id } = await api<{ id: string }>("/workbench/handoffs", "POST", { document: movingState(doc), kernel, to });
    if (to === null) {
      const hash = new URLSearchParams({ token, take: id, fresh: "1", popped: "1" }).toString();
      const opened = window.open(`/${page}#${hash}`, `swissarmybench-workbench-${Date.now()}`, "popup,width=1200,height=800"); // a pop-out keeps its page
      if (!opened) {
        await api(`/workbench/handoffs/${id}`, "DELETE").catch(() => undefined);
        throw new Error("The browser blocked the new window. Allow pop-ups for this address.");
      }
    }
    doc.element.classList.add("moving"); // nothing typed here now: it is on its way
    const until = Date.now() + (to === null ? 30000 : 8000);
    while (Date.now() < until) {
      await new Promise((done) => setTimeout(done, 250));
      const state = await api<{ taken: boolean }>(`/workbench/handoffs/${id}`).catch(() => ({ taken: false }));
      if (!state.taken) continue;
      doc.kernel?.release(); // it runs on, the other window's now
      close(doc, true);
      return { title: doc.title, window: to === null ? "new" : "main" };
    }
    const cancelled = await api<{ cancelled: boolean }>(`/workbench/handoffs/${id}`, "DELETE").catch(() => ({ cancelled: true }));
    if (!cancelled.cancelled) {
      doc.kernel?.release();
      close(doc, true);
      return { title: doc.title, window: to === null ? "new" : "main" };
    }
    doc.element.classList.remove("moving");
    throw new Error(to === null ? `The new window did not take ${doc.title}: it stays here.` : `The main Workbench window is not open: ${doc.title} stays here.`);
  }

  /** Pop a document out into a Workbench window of its own (so it can sit on another screen). */
  const popOut = (doc: Doc): Promise<{ title: string; window: "new" | "main" }> => moveOut(doc, null);

  /** A popped-out window's document back to the main window. */
  function moveToMain(doc: Doc): Promise<{ title: string; window: "new" | "main" }> {
    if (isMainWindow()) throw new Error("This is the main Workbench window.");
    return moveOut(doc, "main"); // the main window that takes it first (the server makes sure only one does)
  }

  /** Take a document another window handed to this one: as it was there, its kernel still running. */
  async function takeDocument(id: string): Promise<void> {
    const taken = await api<{ document: Remembered & { title: string }; kernel: string | null }>(`/workbench/handoffs/${id}/take`, "POST", { window: WINDOW_ID, page: page });
    if ((taken.document as { kind: string }).kind === "explorer") return explorerBack(taken.document as unknown as ExplorerState);
    const r = taken.document;
    const doc = r.kind === "notebook" ? openNotebook(r.path, r.cells ?? [], r.modified, r.next_cell, r.dictionary) : openScript(r.path, r.text ?? "", r.modified);
    if (!r.path && r.title) doc.title = r.title;
    doc.python = r.python;
    if (r.python && !host.pythons.some((p) => p.python === r.python)) host.pythons.push({ python: r.python, version: "", ipykernel: true, swissarmybench: true });
    doc.dirty = r.dirty;
    if (taken.kernel && doc.kernel) doc.kernel.adopt(taken.kernel, r.python ?? "");
    show(doc);
    drawTabs();
    drawStatus();
    remember();
  }

  return { popOut, moveToMain, takeDocument };
}
