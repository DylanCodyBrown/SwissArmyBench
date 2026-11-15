/**
 * workbenchStreamlit.ts: Streamlit pieces (docs/ideas.md, 2026-11-15): what a notebook, a script and
 * the page designer share. [FUNCTION + WIRE]
 *
 *   [PIECE]   a Streamlit cell is a piece: Python that draws with st.*. Open tables are DataFrames by
 *             name; a name a piece makes (`region = st.selectbox(...)`) drives the pieces that read it
 *   [APP]     each document with Streamlit cells has one app on the server (services/streamlit.py): its
 *             pieces as they are typed, its pages, one Streamlit process in the document's own Python.
 *             The server says each piece's state; this window only draws it
 *   [LIVE]    a piece shows live in its cell, in a frame of this server's (the app's pages are passed
 *             through under the app's own secret), sandboxed without the app's origin
 *   [STATE]   only what needs the user is said (no confirmation labels): not run yet, out of date (its
 *             code changed, or a table it names did), Streamlit missing from the notebook's Python
 *             (with Install). Nothing runs by itself
 *   [PAGES]   Push to page sends a piece to a page of the page designer (a window of its own); the
 *             pages are saved inside the notebook's file (a script: its `# %% [streamlit-pages]` block)
 *
 * ROUTING: /streamlit/apps... (routes_streamlit.py); the `streamlit_changed` notice {app}
 */
import { api, ApiError, token } from "./api";
import { h, toast } from "./dom";
import { effectiveTheme } from "./theme";
import type { HtmlState } from "./workbenchHtml";

/** A piece's pane without a saved height. */
export const PIECE_HEIGHT = 220;

export interface PieceState {
  cell: number;
  name: string;
  makes: string[];
  reads: string[];
  tables: string[];
  inputs: number[];
  problem: string | null;
  state: "notRun" | "outOfDate" | "current";
  changed: string[];
  code_changed: boolean;
  preview: string | null;
  pages: string[];
}

export interface Placed {
  id: string;
  cell: number;
  w: number;
  h: number | null;
}

export interface SavedPage {
  id: string;
  name: string;
  pieces: Placed[];
}

export interface PageState extends SavedPage {
  order: string[];
  tables: string[];
  problems: string[];
  rows: string[][];
  out_of_date: boolean;
  address: string | null;
}

export type AppProblem = { kind: "missing"; packages: string[]; python: string; command: string } | { kind: "failed"; message: string };

export interface AppState {
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
  pieces: PieceState[];
  pages: PageState[];
}

export interface ExportResult {
  folder: string;
  files: string[];
  pages: string[];
  tables: string[];
  problems: string[];
  run: string;
}

const listed = (names: string[]): string => (names.length <= 2 ? names.join(" and ") : `${names.slice(0, 2).join(", ")} and ${names.length - 2} more`);

/** What a missing or failed start says. */
export function problemText(problem: AppProblem): string {
  if (problem.kind === "missing") return `${listed(problem.packages)} ${problem.packages.length === 1 ? "is" : "are"} not installed in this document's Python (${problem.python}).`;
  return problem.message;
}

/** A frame's address for a page of the app: without Streamlit's own chrome, and without the app's
 *  list of pages (the designer and the cell show one page). */
export const frameAddress = (address: string): string => `${address}?embed=true&embed_options=${effectiveTheme().endsWith("dark") ? "dark_theme" : "light_theme"}&sag=frame`;

/** A piece as its cell draws it. */
export interface PieceView {
  /** The live piece's address (null: it has not run, so there is nothing to show). */
  address: string | null;
  state: HtmlState;
  notes: string[];
  /** Streamlit is missing from the document's Python: offer Install. */
  install: boolean;
  /** "makes region · reads orders" */
  part: string;
  /** The pages it is on. */
  pages: { id: string; name: string }[];
}

export function pieceView(app: AppState | null, cell: number, hasCode: boolean): PieceView {
  const piece = app?.pieces.find((p) => p.cell === cell);
  const quiet: HtmlState = { kind: "upToDate", label: "", short: "", runnable: false };
  if (!hasCode) return { address: null, state: quiet, notes: [], install: false, part: "", pages: [] };
  const notRun: HtmlState = { kind: "notRun", label: "Not run yet", short: "not run yet", runnable: true };
  if (!app || !piece) return { address: null, state: notRun, notes: [], install: false, part: "", pages: [] };
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
  const part = [piece.makes.length ? `makes ${piece.makes.join(", ")}` : "", piece.reads.length || piece.tables.length ? `reads ${[...piece.tables, ...piece.reads].join(", ")}` : ""].filter(Boolean).join(" · ");
  const pages = app.pages.filter((p) => piece.pages.includes(p.id)).map((p) => ({ id: p.id, name: p.name }));
  return { address: piece.preview ? frameAddress(piece.preview) : null, state, notes, install: app.problem?.kind === "missing", part, pages };
}

const saved = (pages: SavedPage[]): SavedPage[] => pages.map((p) => ({ id: p.id, name: p.name, pieces: p.pieces.map((s) => ({ id: s.id, cell: s.cell, w: s.w, h: s.h })) }));

// ===== a script's pages: its `# %% [streamlit-pages]` block (domain/streamlit_cells.py) =====

const PAGES_LINE = /^# ?%%(?: \[\d+\])? \[streamlit-pages\]\s*$/;
const PAGES_NOTE = "# The pages of this file's Streamlit app (SwissArmyGrid's page designer keeps this block).";

function blockSpan(lines: string[]): [number, number] | null {
  const start = lines.findIndex((l) => PAGES_LINE.test(l));
  if (start < 0) return null;
  let end = start + 1;
  while (end < lines.length && lines[end]!.startsWith("#") && !/^# ?%%/.test(lines[end]!)) end++;
  return [start, end];
}

/** The pages a script's block holds (the server checks them when the app opens). */
export function scriptPages(text: string): SavedPage[] {
  const lines = text.split("\n");
  const span = blockSpan(lines);
  if (!span) return [];
  const found: SavedPage[] = [];
  for (const line of lines.slice(span[0] + 1, span[1])) {
    try {
      const page = JSON.parse(line.slice(1).trim()) as SavedPage;
      if (page && typeof page === "object" && !Array.isArray(page)) found.push(page);
    } catch {
      /* the block's own words */
    }
  }
  return found;
}

/** The script with its pages block as it should be: replaced where it is, added at the end, taken
 *  away when there are no pages. Nothing else in the file is touched. */
export function withScriptPages(text: string, pages: SavedPage[]): string {
  const lines = text.split("\n");
  const span = blockSpan(lines);
  const marker = span ? lines[span[0]]! : "# %% [streamlit-pages]";
  const block = pages.length ? [marker, PAGES_NOTE, ...saved(pages).map((p) => `# ${JSON.stringify(p)}`)] : [];
  if (span) {
    lines.splice(span[0], span[1] - span[0], ...block);
    return lines.join("\n");
  }
  if (!block.length) return text;
  return `${text.endsWith("\n") || !text ? text : `${text}\n`}${block.join("\n")}\n`;
}

// ===== a document's app =====

export interface PieceSource {
  cell: number;
  code: string;
}

export interface AppDocument {
  title: () => string;
  path: () => string | null;
  python: () => string | null;
  kernel: () => string | null;
  window: string;
  pieces: () => PieceSource[];
}

/** One document's Streamlit app, as this window knows it. Nothing is asked of the server until the
 *  document holds a piece. */
export class StreamlitDoc {
  state: AppState | null = null;
  private id: string | null = null;
  private opening: Promise<string> | null = null;
  private timer: number | null = null;
  private kept: string;
  private gone = false;

  constructor(
    private readonly doc: AppDocument,
    private initial: SavedPage[],
    /** The state changed; `pages`: the pages are not the ones last saved with the document. */
    private readonly changed: (pages: boolean) => void,
  ) {
    this.kept = JSON.stringify(saved(initial));
  }

  get app(): string | null {
    return this.id;
  }

  /** The pages, as the document's file keeps them. */
  pages(): SavedPage[] {
    return saved(this.state ? this.state.pages : this.initial);
  }

  private body(): Record<string, unknown> {
    return { title: this.doc.title(), document: this.doc.path(), python: this.doc.python(), kernel: this.doc.kernel(), window: this.doc.window, pieces: this.doc.pieces() };
  }

  private take(state: AppState, opened = false): AppState {
    this.state = state;
    const now = JSON.stringify(saved(state.pages));
    // What the server made of the file's pages (ids given) is not a change of the user's.
    const differs = !opened && now !== this.kept;
    this.kept = now;
    this.changed(differs);
    return state;
  }

  /** The app on the server, opened when it is not (or when the server no longer knows it). */
  ensure(): Promise<string> {
    if (this.id) return Promise.resolve(this.id);
    if (!this.opening) {
      this.opening = api<AppState>("/streamlit/apps", "POST", { ...this.body(), pages: this.pages() })
        .then((state) => {
          this.id = state.app;
          if (this.gone) void api(`/streamlit/apps/${state.app}`, "DELETE").catch(() => undefined);
          this.take(state, true);
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
      this.initial = this.pages();
      this.id = null;
      this.state = null;
      const again = await this.ensure();
      return this.take(await api<AppState>(`/streamlit/apps/${again}${path}`, method, body));
    }
  }

  /** The pieces changed (typed, added, moved, removed): the server hears after a short pause. */
  syncSoon(): void {
    if (!this.id && !this.doc.pieces().length) return;
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      this.timer = null;
      void this.sync().catch(() => undefined);
    }, 400);
  }

  sync(): Promise<AppState> {
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = null;
    return this.call("", "PUT", this.body());
  }

  /** Run or refresh: the pieces and pages as they stand, their tables read from the grid again. */
  run(): Promise<AppState> {
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = null;
    return this.call("/run", "POST", this.body());
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

  /** Push a piece to a page: an existing one (`page`), or a new one (named `name`, or "Page N"). */
  async push(cell: number, page?: string, name?: string): Promise<{ state: AppState; page: string }> {
    await this.sync(); // a piece just typed is known to the server first
    const id = this.id!;
    const done = page ? await api<AppState & { page: string }>(`/streamlit/apps/${id}/pages/${encodeURIComponent(page)}/pieces`, "POST", { cell }) : await api<AppState & { page: string }>(`/streamlit/apps/${id}/pages`, "POST", name ? { cell, name } : { cell });
    return { state: this.take(done), page: done.page };
  }

  async export(folder: string): Promise<ExportResult> {
    await this.sync();
    return api<ExportResult>(`/streamlit/apps/${this.id!}/export`, "POST", { folder });
  }

  /** A notice from the server: this app's pages or run changed somewhere (the designer, the agent). */
  noticed(app: string): void {
    if (app === this.id) void this.refresh().catch(() => undefined);
  }

  /** A table changed in the grid: a piece that names it may be out of date now. */
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

// ===== windows: the page designer, the app on its own =====

/** The page designer's window for an app (one window an app: asked again, it comes to the front). */
export function openDesigner(app: string, page?: string): void {
  const hash = new URLSearchParams({ token, app, ...(page ? { page } : {}) }).toString();
  const opened = window.open(`/designer#${hash}`, `swissarmygrid-designer-${app}`);
  if (!opened) toast("The browser blocked the page designer's window. Allow pop-ups for this address.", "error");
  else opened.focus();
}

/** The whole app in a window of its own (in a frame there, sandboxed as in a cell). */
export function openApp(app: string, page?: string): void {
  const hash = new URLSearchParams({ token, app, view: "app", ...(page ? { page } : {}) }).toString();
  const opened = window.open(`/designer#${hash}`, `swissarmygrid-app-${app}`);
  if (!opened) toast("The browser blocked the app's window. Allow pop-ups for this address.", "error");
  else opened.focus();
}

/** Push to page: the pages to pick from, and a new one. */
export function pushMenu(anchor: HTMLElement, pages: { id: string; name: string }[], on: string[], choose: (page: string | null) => void): void {
  document.querySelector(".menu")?.remove();
  const item = (text: string, page: string | null): HTMLElement =>
    h("button", { type: "button", role: "menuitem", onclick: () => { menu.remove(); choose(page); } }, text);
  const menu = h(
    "div",
    { class: "menu wb-push-menu", role: "menu", "aria-label": "Push to page" },
    ...pages.map((p) => item(on.includes(p.id) ? `${p.name} (again)` : p.name, p.id)),
    item("New page", null),
  );
  document.body.append(menu);
  const box = anchor.getBoundingClientRect();
  menu.style.top = `${Math.min(box.bottom + 4, innerHeight - menu.offsetHeight - 8)}px`;
  menu.style.left = `${Math.max(8, Math.min(box.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 8))}px`;
  (menu.querySelector("button") as HTMLButtonElement | null)?.focus();
  setTimeout(() => document.addEventListener("mousedown", function away(e) { if (!menu.contains(e.target as Node)) { menu.remove(); document.removeEventListener("mousedown", away); } }));
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      menu.remove();
      anchor.focus();
    }
  });
}

/** What a document gives its Streamlit cells (the notebook's and the script's views call these). */
export interface StreamlitHost {
  state: () => AppState | null;
  /** The pieces changed. */
  changed: () => void;
  /** Run or refresh the app (false: it did not start). */
  run: () => Promise<boolean>;
  install: () => void;
  /** Push to page: the menu at `anchor`. */
  push: (cell: number, anchor: HTMLElement) => void;
  designer: (page?: string) => void;
}

/** A piece's own tools in its pane's bar: Install (when Streamlit is missing), the pages it is on,
 *  Push to page. */
export interface PieceTools {
  elements: HTMLElement[];
  draw: (view: PieceView) => void;
}

export function pieceTools(host: StreamlitHost | undefined, cell: () => number): PieceTools {
  const install = h("button", { type: "button", class: "btn wb-piece-install", title: "Install Streamlit, pandas and pyarrow into this document's Python", onclick: () => host?.install() }, "Install");
  const where = h("span", { class: "wb-piece-pages" });
  const push = h("button", { type: "button", class: "btn ghost wb-piece-push", title: "Push this piece to a page of the page designer", onclick: (e: Event) => host?.push(cell(), e.currentTarget as HTMLElement) }, "Push to page");
  install.hidden = true;
  return {
    elements: [install, where, push],
    draw: (view) => {
      install.hidden = !view.install;
      where.replaceChildren(
        ...view.pages.map((p) => h("button", { type: "button", class: "link wb-piece-page", title: `Open ${p.name} in the page designer`, onclick: () => host?.designer(p.id) }, p.name)),
      );
      where.hidden = !view.pages.length;
    },
  };
}
