/**
 * cellClipboard.ts: a cell's name and its copy, shared by notebooks and scripts (once part of the live
 * Streamlit cells' module; app notebooks and live cells were replaced by widgets, 2026-11-21).
 *
 *   [NAMES]  a cell's name as typed, a script marker's own words
 *   [COPY]   a copied cell (C), pasted in any Workbench window (V): kept across windows by a BroadcastChannel
 */

// ===== a cell's name (docs/ideas.md, named cells, 2026-11-15) =====

export const MAX_CELL_NAME = 80;

/** A cell's name as typed: one line, at most 80 characters ("" is no name). */
export const cleanName = (typed: string): string => typed.replace(/[\r\n]+/g, " ").trim().slice(0, MAX_CELL_NAME);

// A script cell's name is its marker's own words (domain/table_cells.py marker_words): words that
// would read as the marker's grammar are written after a backslash.
const GRAMMAR = /^(?:\[(?:\d+|table|transformations|html|streamlit)\]|height=\d|\\)/;
const MARKER = /^(# ?%%(?: \[\d+\])?(?: \[(?:table|transformations)\] [A-Za-z_][\w-]*)?(?: \[(?:html|streamlit)\])?(?: height=\d{1,5})?)((?: .*)?)$/;

export const markerWords = (name: string): string => (GRAMMAR.test(name) ? `\\${name}` : name);

export function markerName(words: string): string {
  const said = words.trim();
  return said.startsWith("\\") && GRAMMAR.test(said.slice(1)) ? said.slice(1) : said;
}

/** A marker line's own words (the cell's name as written), or null when the line is no marker. */
export function markerWordsOf(line: string): string | null {
  const found = MARKER.exec(line);
  return found ? (found[2] ?? "") : null;
}

/** A marker line with the cell's name in place of its words. */
export function withMarkerName(line: string, name: string): string {
  const found = MARKER.exec(line);
  if (!found) return line;
  return name ? `${found[1]} ${markerWords(name)}` : found[1]!;
}


// ===== a copied cell: what Copy keeps =====

export interface CellLink {
  /** The notebook's or script's path (null: it has no file yet, so nothing can link to it). */
  document: string | null;
  cell: number;
  /** The document's name, for what is said. */
  title: string;
}

/** A copied cell: its link, and the cell itself (for a paste into a notebook). */
export interface CopiedCell extends CellLink {
  kind: string;
  source: string;
  connection: string | null;
  height: number | null;
}

let copied: CopiedCell | null = null;
const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("swissarmybench-workbench-clipboard");
if (channel) {
  channel.onmessage = (e: MessageEvent) => {
    const message = e.data as { copied?: CopiedCell; ask?: boolean } | null;
    if (message?.copied) copied = message.copied;
    // A window that just opened asks what was copied before it was there.
    else if (message?.ask && copied) channel.postMessage({ copied });
  };
  channel.postMessage({ ask: true });
}

/** Copy a cell: every Workbench window can paste it. */
export function copyCell(cell: CopiedCell): void {
  copied = cell;
  channel?.postMessage({ copied: cell });
}

export const copiedCell = (): CopiedCell | null => copied;
