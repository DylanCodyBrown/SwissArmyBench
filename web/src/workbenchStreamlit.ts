/**
 * workbenchStreamlit.ts: Streamlit in the Workbench (docs/ideas.md, the Streamlit canvas, 2026-11-15):
 * what a notebook, a script and a Streamlit app's canvas share. [FUNCTION + WIRE]
 *
 *   [LIVE]    there is no Streamlit kind of cell. A Python cell that calls Streamlit (the server finds
 *             it with Python's parser: domain/streamlit_use.py) is shown live in its own cell, in a
 *             frame of this server's (sandboxed without the app's origin), and does not run in the
 *             kernel. Open tables are DataFrames by name
 *   [DOC]     each open notebook or script tells the server its Python cells as they are typed
 *             (services/streamlit.py): the server says which are live and each one's state, and a
 *             canvas that links to a cell reads it from there, saved or not
 *   [STATE]   only what needs the user is said (no confirmation labels): not run yet, out of date (its
 *             code changed, or a table it names did), Streamlit missing from the document's Python
 *             (with Install). Nothing runs by itself
 *   [LINK]    a cell's link (its file's path and the cell's own number): what a drag carries and what
 *             Copy puts on the Workbench's own clipboard, shared by every Workbench window (a
 *             BroadcastChannel: memory only). A canvas takes it as a block; a notebook pastes the cell
 *
 * ROUTING: /streamlit/apps... (routes_streamlit.py); the `streamlit_changed` notice {app}
 */
import { api, ApiError } from "./api";
import { h } from "./dom";
import { effectiveTheme } from "./theme";
import type { HtmlState } from "./workbenchHtml";

/** A live cell's pane without a saved height. */
export const PIECE_HEIGHT = 220;

export interface PieceState {
  cell: number;
  name: string;
  makes: string[];
  reads: string[];
  tables: string[];
  inputs: number[];
  problem: string | null;
  state: "notRun" | "outOfDate" | "current" | "missing";
  changed: string[];
  code_changed: boolean;
  preview: string | null;
}

export type AppProblem = { kind: "missing"; packages: string[]; python: string; command: string } | { kind: "failed"; message: string };

interface AppCommon {
  app: string;
  title: string;
  document: string | null;
  python: string;
  running: boolean;
  path: string | null;
  address: string | null;
  folder: string | null;
  generation: number;
  ran_at: number | null;
  problem: AppProblem | null;
  notes: string[];
}

/** A notebook's or script's own app: its live cells. */
export interface AppState extends AppCommon {
  kind: "document";
  pieces: PieceState[];
}

/** A block of a canvas: a link to a cell, and its place on the 12-column grid. */
export interface BlockState {
  id: string;
  document: string;
  cell: number;
  row: number;
  column: number;
  w: number;
  h: number | null;
  name: string | null;
  where: string;
  makes: string[];
  reads: string[];
  tables: string[];
  problem: string | null;
  /** In red on the block: the cell is gone, or its file is (the path and the number). */
  missing: string | null;
  state: "notRun" | "outOfDate" | "current" | "missing";
  changed: string[];
}

export interface CanvasPage {
  id: string;
  name: string;
  blocks: BlockState[];
  order: string[];
  tables: string[];
  problems: string[];
  rows: string[][];
  out_of_date: boolean;
  address: string | null;
}

export interface CanvasState extends AppCommon {
  kind: "canvas";
  unsaved: string[];
  pages: CanvasPage[];
}

/** The pages as the app's file keeps them (and as the server takes them back). */
export interface SavedPage {
  id?: string;
  name: string;
  blocks: { id?: string; document: string; cell: number; row: number; column: number; w: number; h: number | null }[];
}

export const savedPages = (pages: (CanvasPage | SavedPage)[]): SavedPage[] =>
  pages.map((p) => ({ id: p.id, name: p.name, blocks: p.blocks.map((b) => ({ id: b.id, document: b.document, cell: b.cell, row: b.row, column: b.column, w: b.w, h: b.h })) }));

export interface ExportResult {
  folder: string;
  files: string[];
  pages: string[];
  tables: string[];
  problems: string[];
  run: string;
}

export interface SaveAsResult {
  path: string;
  project: string;
  files: string[];
  pages: string[];
  data: string[];
  fill_in: string[];
  problems: string[];
}

const listed = (names: string[]): string => (names.length <= 2 ? names.join(" and ") : `${names.slice(0, 2).join(", ")} and ${names.length - 2} more`);

/** What a missing or failed start says. */
export function problemText(problem: AppProblem): string {
  if (problem.kind === "missing") return `${listed(problem.packages)} ${problem.packages.length === 1 ? "is" : "are"} not installed in this document's Python (${problem.python}).`;
  return problem.message;
}

/** A frame's address for a page of the app: without Streamlit's own chrome, and without the app's
 *  list of pages (a canvas and a cell show one page). */
export const frameAddress = (address: string): string => `${address}?embed=true&embed_options=${effectiveTheme().endsWith("dark") ? "dark_theme" : "light_theme"}&sag=frame`;

/** "makes region · reads orders" */
export const partsOf = (what: { makes: string[]; reads: string[]; tables: string[] }): string =>
  [what.makes.length ? `makes ${what.makes.join(", ")}` : "", what.tables.length || what.reads.length ? `reads ${[...what.tables, ...what.reads].join(", ")}` : ""].filter(Boolean).join(" · ");

/** A live cell as its cell draws it. */
export interface PieceView {
  /** The server says this cell calls Streamlit. */
  live: boolean;
  /** The live cell's address (null: it has not run, so there is nothing to show). */
  address: string | null;
  state: HtmlState;
  notes: string[];
  /** Streamlit is missing from the document's Python: offer Install. */
  install: boolean;
  /** "makes region · reads orders" */
  part: string;
}

export function pieceView(app: AppState | null, cell: number, hasCode: boolean): PieceView {
  const piece = app?.pieces.find((p) => p.cell === cell);
  const quiet: HtmlState = { kind: "upToDate", label: "", short: "", runnable: false };
  if (!hasCode || !app || !piece) return { live: false, address: null, state: quiet, notes: [], install: false, part: "" };
  const notRun: HtmlState = { kind: "notRun", label: "Not run yet", short: "not run yet", runnable: true };
  const notes: string[] = [];
  if (app.problem) notes.push(problemText(app.problem));
  if (piece.problem) notes.push(`Not whole Python yet: ${piece.problem}.`);
  for (const note of app.notes) if (piece.tables.some((t) => note.startsWith(`${t} `) || note.startsWith(`${t}:`))) notes.push(note);
  let state = quiet;
  if (piece.state === "notRun") state = notRun;
  else if (piece.state === "outOfDate") {
    const why = piece.changed.length ? ` · ${listed(piece.changed)} changed` : "";
    state = { kind: "outOfDate", label: `Out of date${why}`, short: "out of date", runnable: true };
  }
  return { live: true, address: piece.preview ? frameAddress(piece.preview) : null, state, notes, install: app.problem?.kind === "missing", part: partsOf(piece) };
}

/** Code that may call Streamlit, by a quick look (the server's parser has the last word): a
 *  document with none of it is not sent to the server until it is linked or saved. */
export const mayUseStreamlit = (code: string): boolean => /\bst\s*\.|streamlit/.test(code);

// ===== a document's app =====

export interface PieceSource {
  cell: number;
  code: string;
  /** The cell's own name (none: it has none). */
  name?: string;
}

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

// ===== the Streamlit cells pane (the Data panel): every cell that calls Streamlit =====

export interface PaneCell {
  cell: number;
  name: string;
  /** It has a name of its own (else `name` is its first comment line or first line). */
  named: boolean;
  where: string;
  makes: string[];
  reads: string[];
  tables: string[];
}

export interface PaneDocument {
  /** Its path (null: never saved, so nothing can link to it yet). */
  document: string | null;
  title: string;
  /** A window holds it open (else it is a project's file on disk). */
  open: boolean;
  cells: PaneCell[];
}

/** A cell of data.ipynb as the export reads it (domain/projects.py DataCell). */
export interface EveryCell {
  kind: string;
  source: string;
  role: string;
  table: string | null;
  number: number | null;
}

export interface AppDocument {
  title: () => string;
  path: () => string | null;
  python: () => string | null;
  kernel: () => string | null;
  window: string;
  /** Its Python cells (the user's own), by number. */
  cells: () => PieceSource[];
  unsaved: () => boolean;
  /** Every cell, for a project's data.ipynb (its export data.py is written from them); else null. */
  every: () => EveryCell[] | null;
}

/** One notebook's or script's app, as this window knows it. The server hears of a document once it
 *  has a file (a canvas may link to it) or code that may call Streamlit. */
export class StreamlitDoc {
  state: AppState | null = null;
  private id: string | null = null;
  private opening: Promise<string> | null = null;
  private timer: number | null = null;
  private sent = "";
  private gone = false;

  constructor(
    private readonly doc: AppDocument,
    private readonly changed: () => void,
  ) {}

  get app(): string | null {
    return this.id;
  }

  private body(): Record<string, unknown> {
    const every = this.doc.every();
    return { title: this.doc.title(), document: this.doc.path(), python: this.doc.python(), kernel: this.doc.kernel(), window: this.doc.window, cells: this.doc.cells(), unsaved: this.doc.unsaved(), ...(every ? { every } : {}) };
  }

  private take(state: AppState): AppState {
    this.state = state;
    this.changed();
    return state;
  }

  private wanted(): boolean {
    return !!this.id || !!this.doc.path() || this.doc.cells().some((c) => mayUseStreamlit(c.code));
  }

  /** The app on the server, opened when it is not (or when the server no longer knows it). */
  ensure(): Promise<string> {
    if (this.id) return Promise.resolve(this.id);
    if (!this.opening) {
      const body = this.body();
      this.opening = api<AppState>("/streamlit/apps", "POST", body)
        .then((state) => {
          this.id = state.app;
          this.sent = JSON.stringify(body);
          if (this.gone) void api(`/streamlit/apps/${state.app}`, "DELETE").catch(() => undefined);
          this.take(state);
          return state.app;
        })
        .finally(() => (this.opening = null));
    }
    return this.opening;
  }

  /** A call on the app; an app the server forgot (it restarted) is opened again, once. */
  private async call(path: string, method: string, body?: unknown): Promise<AppState> {
    const id = await this.ensure();
    try {
      return this.take(await api<AppState>(`/streamlit/apps/${id}${path}`, method, body));
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 404 || this.id !== id || !/app is not open/.test(e.message)) throw e;
      this.id = null;
      this.state = null;
      const again = await this.ensure();
      return this.take(await api<AppState>(`/streamlit/apps/${again}${path}`, method, body));
    }
  }

  /** The cells changed (typed, added, moved, removed, saved): the server hears after a short pause. */
  syncSoon(): void {
    if (!this.wanted()) return;
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      this.timer = null;
      void this.sync().catch(() => undefined);
    }, 400);
  }

  /** The server has the document as it stands now (nothing is sent when nothing changed). */
  async sync(): Promise<AppState | null> {
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = null;
    if (!this.wanted()) return this.state;
    const body = this.body();
    const said = JSON.stringify(body);
    if (this.id && said === this.sent && this.state) return this.state;
    const state = await this.call("", "PUT", body);
    this.sent = said;
    return state;
  }

  /** Whether a cell is live, by the server's word on the code as it stands now. */
  async isLive(cell: number): Promise<boolean> {
    const state = await this.sync().catch(() => null);
    return !!state?.pieces.some((p) => p.cell === cell);
  }

  /** Run or refresh: the live cells as they stand, their tables read from the grid again. */
  async run(): Promise<AppState> {
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = null;
    const body = this.body();
    const state = await this.call("/run", "POST", body);
    this.sent = JSON.stringify(body);
    return state;
  }

  refresh(): Promise<AppState> {
    return this.call("", "GET");
  }

  stop(): Promise<AppState> {
    return this.call("/stop", "POST");
  }

  /** Streamlit, pandas and pyarrow into the document's own Python; then the app runs. */
  async install(): Promise<AppState> {
    const id = await this.ensure();
    const done = await api<{ ok: boolean; output: string }>(`/streamlit/apps/${id}/install`, "POST");
    if (!done.ok) throw new Error(done.output.trim().split("\n").slice(-6).join("\n") || "The install failed.");
    return this.run();
  }

  /** A notice from the server: this app's run changed somewhere (the agent). */
  noticed(app: string): void {
    if (app === this.id) void this.refresh().catch(() => undefined);
  }

  /** A table changed in the grid: a live cell that names it may be out of date now. */
  tablesChanged(): void {
    if (this.id && this.state?.running) void this.refresh().catch(() => undefined);
  }

  /** The document closed: its app goes (its process, its temporary folder). */
  close(): void {
    this.gone = true;
    if (this.timer !== null) window.clearTimeout(this.timer);
    if (this.id) void api(`/streamlit/apps/${this.id}`, "DELETE").catch(() => undefined);
  }
}

/** What a document gives its live cells (the notebook's and the script's views call these). */
export interface StreamlitHost {
  state: () => AppState | null;
  /** The cells changed. */
  changed: () => void;
  /** Whether the cell calls Streamlit, by the server's word on its code as it stands. */
  isLive: (cell: number) => Promise<boolean>;
  /** Run or refresh the app (false: it did not start). */
  run: () => Promise<boolean>;
  install: () => void;
  /** The document's path (null: never saved) and title: what a cell's link names. */
  link: () => { document: string | null; title: string };
}

/** A live cell's own tool in its pane's bar: Install (when Streamlit is missing). */
export interface PieceTools {
  elements: HTMLElement[];
  draw: (view: PieceView) => void;
}

export function pieceTools(host: StreamlitHost | undefined): PieceTools {
  const install = h("button", { type: "button", class: "btn wb-piece-install", title: "Install Streamlit, pandas and pyarrow into this document's Python", onclick: () => host?.install() }, "Install");
  install.hidden = true;
  return {
    elements: [install],
    draw: (view) => {
      install.hidden = !view.install;
    },
  };
}

// ===== a cell's link: what a drag carries, what Copy keeps =====

/** The drag's type: a small JSON of the document's path and the cell's number. */
export const CELL_DRAG = "application/x-swissarmygrid-cell";

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
const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("swissarmygrid-workbench-clipboard");
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

/** A drag's cell link, when it carries one. */
export function draggedLink(data: DataTransfer | null): CellLink | null {
  const raw = data?.getData(CELL_DRAG);
  if (!raw) return null;
  try {
    const link = JSON.parse(raw) as CellLink;
    return typeof link.cell === "number" ? link : null;
  } catch {
    return null;
  }
}
