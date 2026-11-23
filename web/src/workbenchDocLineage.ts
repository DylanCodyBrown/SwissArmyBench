/**
 * workbenchDocLineage.ts: the Workbench's documents as the lineage sees them (workbenchLineage.ts draws it).
 * Moved out of workbenchPage.ts along its own heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [BODY]     the request for a target: a cell of a document open here goes with the cells (or the text) as
 *              the window holds them, and each cell's last error
 *   [GO TO]    a double-click on a node: its cell, in its document (opened when it is not open here)
 *   [OVERLAY]  the lineage overlay for a cell; data.ipynb's Lineage view, drawn in place
 */
import { drawLineageEmpty } from "./workbenchDocModes";
import { type LineageGraph, type LineageNode, type LineageTarget, openLineage } from "./workbenchLineage";
import type { CellData, NotebookView } from "./workbenchNotebook";
import type { Doc } from "./workbenchPage";
import type { ScriptView } from "./workbenchScript";

/** What the lineage asks of the page: its documents and the one in front, a file opened, a document shown,
 *  a document's cells' view, and data.ipynb's Lineage view left for its cells. */
export interface LineageHost {
  docs: Doc[];
  readonly current: Doc | null;
  open: (path?: string) => Promise<void>;
  show: (doc: Doc) => void;
  viewOf: (doc: Doc) => NotebookView | ScriptView | undefined;
  backToCells: (doc: Doc) => void;
}

/** A document as the lineage names it: its path, or its title while it has none. */
export const docName = (doc: Doc): string => doc.path ?? doc.title;

export function documentLineage(host: LineageHost) {
  const { docs, open, show, viewOf } = host;

  /** The error each cell's last run ended with, by its number ("KeyError: 'amount'"). */
  function cellErrors(cells: CellData[]): Record<string, string> {
    const found: Record<string, string> = {};
    for (const c of cells) {
      const error = c.outputs.find((o) => o.output_type === "error");
      if (error && c.number) found[String(c.number)] = `${String(error.ename ?? "Error")}: ${String(error.evalue ?? "")}`.trim();
    }
    return found;
  }

  /** The request for a target: a cell of a document open here goes with the cells as the window holds them. */
  function lineageBody(target: LineageTarget): Record<string, unknown> {
    if (target.app) return { app: target.app, page: target.page, block: target.block };
    const doc = docs.find((d) => (d.notebook || d.script) && docName(d) === target.document);
    if (!doc) return { document: target.document, cell: target.cell };
    const base = { document: docName(doc), cell: target.cell, kernel: doc.kernel?.id ?? null };
    if (doc.script) return { ...base, text: doc.script.text() };
    const cells = doc.notebook!.cells();
    const lean = cells.map(({ kind, source, connection, number, role, table, name }) => ({ kind, source, connection, number, role, table, name }));
    return { ...base, cells: lean, errors: cellErrors(cells) };
  }

  /** Double-click on a node: its cell, in its document (opened when it is not open here). */
  async function goToNode(node: LineageNode): Promise<void> {
    if (node.cell === null || !node.document) return;
    let doc = docs.find((d) => (d.notebook || d.script) && (docName(d) === node.document || d.path === node.document));
    if (!doc) {
      await open(node.document);
      doc = docs.find((d) => d.path === node.document);
    }
    if (!doc) return;
    show(doc);
    viewOf(doc)?.goTo(node.cell);
  }

  const lineageHost = { body: lineageBody, goTo: (node: LineageNode) => void goToNode(node) };

  /** The Data mode's Lineage view: data.ipynb's selected cell (else its last numbered one) back to the
   *  data, drawn in place by the lineage overlay's own code; a double-click on a node goes back to the
   *  cells, at that cell. */
  async function dataLineage(doc: Doc, into: HTMLElement, cell?: number): Promise<LineageGraph | null> {
    const numbered = doc.notebook!.cells().filter((c) => c.number && c.kind !== "markdown" && c.source.trim());
    const number = cell ?? doc.notebook!.selectedNumber() ?? numbered[numbered.length - 1]?.number ?? null;
    if (!number) {
      drawLineageEmpty(into);
      return null;
    }
    const own = {
      body: lineageBody,
      goTo: (node: LineageNode) => {
        host.backToCells(doc);
        void goToNode(node);
      },
    };
    return openLineage({ document: docName(doc), cell: number }, own, into);
  }

  /** The lineage overlay: a cell of a document; without a target, the front document's selected cell (the
   *  cursor's in a script). */
  async function showLineage(target?: LineageTarget & { number?: number }, into?: HTMLElement): Promise<LineageGraph> {
    let chosen: LineageTarget | null = null;
    if (target?.app || target?.document) chosen = target;
    else if (host.current?.notebook || host.current?.script) {
      const number = target?.number ?? target?.cell ?? (host.current.notebook ? host.current.notebook.selectedNumber() : host.current.script!.cursorCell());
      if (!number) throw new Error("Select a cell first.");
      chosen = { document: docName(host.current), cell: number };
    }
    if (!chosen) throw new Error("No notebook, script or Streamlit app is in front.");
    return openLineage(chosen, lineageHost, into);
  }

  // For the agent's palette and the tests: the overlay, or (`into`) the same flow drawn in that element.
  (window as unknown as { openLineage: (target?: LineageTarget & { number?: number }, into?: HTMLElement) => Promise<LineageGraph> }).openLineage = showLineage;

  return { showLineage, dataLineage };
}
