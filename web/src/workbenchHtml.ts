/**
 * workbenchHtml.ts: HTML cells (docs/ideas.md, 2026-11-14): what a notebook and a script share.
 * [FUNCTION + WIRE]
 *
 *   [DESIGN]  the cell's HTML drawn as a design, in a pane whose bottom edge drags (and moves with the
 *             arrow keys, as the Workbench's splitters do). Without a saved height the pane takes the
 *             design's own
 *   [SAFE]    the design runs in a frame of its own (static/design.html), sandboxed: its scripts run,
 *             but it is not the app's origin, so it cannot reach the app, its token, the page's storage
 *             or the user's data; and the frame's policy loads nothing over the network (only what is
 *             inside the cell: inline scripts and styles, data addresses for pictures and fonts)
 *   [NAMES]   `{{ name }}` is filled from the cell's kernel when the cell runs (client/html_cells.py);
 *             the filling is the server's (domain/html_cells.py), so data can never become markup or
 *             script. Plain HTML has no names: it draws at once and is never out of date
 *   [STATE]   a cell with names compares its HTML with the HTML it last ran, and each name's mark with
 *             the mark from that run. Only a state that needs the user to act is said (the owner,
 *             2026-11-14: no confirmation labels): out of date (yellow, with Run), not run yet, not run
 *             since opening. A cell that is current says nothing. Nothing runs by itself
 *
 * ROUTING: POST /workbench/html/fill {html, values}: the design, its names filled
 *          POST /workbench/kernels/{id}/execute {code: html, kind: "html"}: run it; the output holds
 *          the values and their marks
 *          POST /workbench/kernels/{id}/html-marks {names}: what each name would draw now, as a mark
 */
import { api } from "./api";
import { button, h } from "./dom";
import type { Kernel, RunItem } from "./workbenchKernel";
import type { Output } from "./workbenchOutputs";

/** The output an HTML cell's run gives (client/html_cells.py MIME). */
export const HTML_MIME = "application/vnd.swissarmybench.html-cell+json";
/** The same, in an output saved before the rename to Swiss Army Bench (still read, for one release). */
const OLD_HTML_MIME = "application/vnd.swissarmygrid.html-cell+json";
/** What an HTML cell's output says about its names: under the new MIME type, else the old one. */
function htmlDetail(data: unknown): { values?: Record<string, HtmlValue>; marks?: Record<string, string> } | undefined {
  const held = data as Record<string, unknown> | undefined;
  return (held?.[HTML_MIME] ?? held?.[OLD_HTML_MIME]) as { values?: Record<string, HtmlValue>; marks?: Record<string, string> } | undefined;
}
export const HEIGHT_MIN = 60;
export const HEIGHT_MAX = 2000;
/** A design with no saved height takes its own, up to this. */
const AUTO_MAX = 640;
const NAME = /\{\{\s*([A-Za-z_]\w*)\s*\}\}/g;

/** The names a cell's HTML asks for, each once (domain/html_cells.py names). */
export function htmlNames(html: string): string[] {
  return [...new Set([...html.matchAll(NAME)].map((m) => m[1]!))].slice(0, 200);
}

export interface HtmlValue {
  kind: string;
  text?: string;
  html?: string;
  json?: string;
  size?: string;
}

/** What a cell's last run gave. `code` null: it has not run in this kernel (the values are a file's). */
export interface HtmlRun {
  code: string | null;
  at: Date | null;
  /** The cell came with the file (or a reload). */
  opened: boolean;
  values: Record<string, HtmlValue>;
  marks: Record<string, string>;
  /** The names whose variable has changed since the run. */
  changed: string[];
  /** The run's output, as the notebook saves it. */
  output: Output | null;
}

export type HtmlStateKind = "plain" | "upToDate" | "outOfDate" | "notRun" | "notRunSinceOpening";
export interface HtmlState {
  kind: HtmlStateKind;
  /** "Out of date · last run 10:42". Empty: nothing needs doing, so nothing is said. */
  label: string;
  short: string;
  runnable: boolean;
}

const clock = (at: Date): string => `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
const listed = (names: string[]): string => (names.length <= 2 ? names.join(" and ") : `${names.slice(0, 2).join(", ")} and ${names.length - 2} more`);

/** An HTML cell's state: plain HTML is never out of date; with names, its HTML against the HTML it
 *  last ran (so undoing an edit clears the yellow by itself), then its names' variables. */
export function htmlState(html: string, run: HtmlRun | undefined): HtmlState {
  if (!htmlNames(html).length) return { kind: "plain", label: "", short: "plain HTML", runnable: false };
  const ran = run?.code ?? null;
  const when = run?.at ? ` · last run ${clock(run.at)}` : "";
  if (ran !== null && ran === html && !run!.changed.length) return { kind: "upToDate", label: "", short: "", runnable: false };
  if (ran !== null && ran === html) return { kind: "outOfDate", label: `Out of date · ${listed(run!.changed)} changed${when}`, short: "out of date", runnable: true };
  if (ran !== null) return { kind: "outOfDate", label: `Out of date${when}`, short: "out of date", runnable: true };
  if (run?.opened) return { kind: "notRunSinceOpening", label: "Not run since opening", short: "not run since opening", runnable: true };
  return { kind: "notRun", label: "Not run yet", short: "not run yet", runnable: true };
}

/** The run a saved output holds (a notebook opened again): its values, not yet run in this kernel. */
export function runFromOutputs(outputs: Output[]): HtmlRun | undefined {
  for (const output of outputs) {
    const detail = htmlDetail(output.data);
    if (detail && typeof detail === "object") return { code: null, at: null, opened: true, values: detail.values ?? {}, marks: detail.marks ?? {}, changed: [], output };
  }
  return undefined;
}

export interface Filled {
  html: string;
  names: string[];
  missing: string[];
  waiting: string[];
  notes: string[];
}

/** The design: the HTML with its names filled from a run's values. Plain HTML is itself. */
export async function fillHtml(html: string, values: Record<string, HtmlValue>): Promise<Filled> {
  if (!htmlNames(html).length) return { html, names: [], missing: [], waiting: [], notes: [] };
  return api<Filled>("/workbench/html/fill", "POST", { html, values });
}

export interface HtmlRunResult {
  ok: boolean;
  run: HtmlRun | null;
  execution_count: number | null;
}

/** Run an HTML cell in the kernel: each name read from its variables. Anything else the run says (an
 *  error, a warning) goes to `other`. */
export async function runHtml(kernel: Kernel, html: string, other: (item: RunItem) => void): Promise<HtmlRunResult> {
  let run: HtmlRun | null = null;
  const done = await kernel.run({ code: html, kind: "html" }, (item) => {
    const detail = htmlDetail(item.data);
    if (detail && typeof detail === "object") run = { code: html, at: new Date(), opened: false, values: detail.values ?? {}, marks: detail.marks ?? {}, changed: [], output: item };
    else other(item);
  });
  return { ok: done.ok && run !== null, run, execution_count: done.execution_count };
}

/** Which of these runs' names would draw something else now (their variables changed). Null: the
 *  kernel is busy or away; ask again later. */
export async function changedNames(kernel: Kernel, runs: HtmlRun[]): Promise<Map<HtmlRun, string[]> | null> {
  const names = [...new Set(runs.flatMap((r) => Object.keys(r.marks)))];
  if (!kernel.id || !names.length) return null;
  try {
    const now = await api<{ busy: boolean; marks: Record<string, string> }>(`/workbench/kernels/${kernel.id}/html-marks`, "POST", { names });
    if (now.busy) return null;
    return new Map(runs.map((r) => [r, Object.keys(r.marks).filter((n) => now.marks[n] !== undefined && now.marks[n] !== r.marks[n])]));
  } catch {
    return null;
  }
}

// ===== the pane =====

/** What a live Streamlit page may do in its frame: run its scripts, send its forms, save a download.
 *  Never the app's origin (no allow-same-origin): it cannot read the app's token or storage. */
export const FRAME_SANDBOX = "allow-scripts allow-forms allow-downloads";

export interface DesignPane {
  element: HTMLElement;
  /** Draw this HTML (its names already filled). */
  show: (html: string) => void;
  /** Show a page of this server's instead (a Streamlit piece, live): the same frame while the address
   *  is the same, so its widgets keep what they hold. */
  showAddress: (address: string | null) => void;
  /** The cell's state and what the filling left out (plain HTML: no state). */
  setState: (state: HtmlState, notes: string[]) => void;
  /** The saved height (null: the design's own). */
  height: () => number | null;
  setHeight: (height: number | null) => void;
  /** The height it has on screen now. */
  shown: () => number;
  dispose: () => void;
}

const panes = new Set<{ frame: () => HTMLIFrameElement | null; ready: () => void; fits: (height: number) => void }>();
let listening = false;

/** Messages from the design frames. A design's own script can send anything: only the two the frame's
 *  shell and the height reporter send are read, and only as what they are (a word, a number). */
function listen(): void {
  if (listening) return;
  listening = true;
  window.addEventListener("message", (event) => {
    for (const pane of panes) {
      if (pane.frame()?.contentWindow !== event.source) continue;
      if (event.data === "sab-design-ready") pane.ready();
      else if (typeof event.data === "object" && event.data !== null && typeof (event.data as { sabDesignHeight?: unknown }).sabDesignHeight === "number") pane.fits((event.data as { sabDesignHeight: number }).sabDesignHeight);
      return;
    }
  });
}

// Tells the pane the design's height, so a design with no saved height is shown whole.
const REPORTER = `<script>(function(){var last=0;function say(){var h=Math.ceil(Math.max(document.documentElement.scrollHeight,document.body?document.body.scrollHeight:0));if(h!==last){last=h;parent.postMessage({sabDesignHeight:h},"*")}}addEventListener("load",say);if(window.ResizeObserver)new ResizeObserver(say).observe(document.documentElement);setTimeout(say,0)})()</script>`;

/** The page a design is drawn as: plain defaults in the app's colours (the design's own styles come
 *  after them and win), then the cell's HTML. */
function page(html: string, dark: boolean): string {
  const ink = dark ? "#e8ecef" : "#1c2228";
  const line = dark ? "#343c45" : "#d5dbe1";
  const base = `<style>html{color-scheme:${dark ? "dark" : "light"}}body{margin:12px;font:14px/1.45 "Segoe UI",system-ui,sans-serif;color:${ink};background:transparent}
.sab-table{border-collapse:collapse;font-size:13px}.sab-table th,.sab-table td{padding:3px 10px;border-bottom:1px solid ${line};text-align:left}.sab-table thead th{border-bottom-width:2px}
.sab-table caption{caption-side:bottom;text-align:left;font-size:12px;opacity:.75;padding-top:6px}</style>`;
  return `<!doctype html><meta charset="utf-8">${base}${html}${REPORTER}`;
}

export function designPane(options: {
  dark: () => boolean;
  /** The saved height (null: the design's own). */
  height: number | null;
  /** The user sized the pane (null: back to the design's own height). */
  resized: (height: number | null) => void;
  run: () => void;
  /** The height without a saved one, until the design says its own (a Streamlit piece never does). */
  fit?: number;
  /** More for the bar's right end (a live cell's Install); the bar then always shows. */
  tools?: HTMLElement[];
}): DesignPane {
  listen();
  let saved = options.height;
  let fit = options.fit ?? 160; // the design's own height, once it says
  let html = "";
  let frame: HTMLIFrameElement | null = null;
  const stage = h("div", { class: "wb-design-stage" });
  const status = h("span", { class: "wb-design-state", role: "status" });
  const run = button("Run", () => options.run(), { icon: "play", class: "ghost wb-design-run", title: "Run: fill the names from the kernel (Ctrl+Enter)" });
  const bar = h("div", { class: "wb-design-bar" }, status, h("span", { class: "spacer" }), run, ...(options.tools ?? []));
  let address: string | null = null;
  const notes = h("div", { class: "wb-design-notes hint" });
  const grip = h("div", { class: "wb-design-grip", role: "separator", tabindex: 0, "aria-orientation": "horizontal", "aria-label": "Resize the design", "aria-valuemin": HEIGHT_MIN, "aria-valuemax": HEIGHT_MAX, title: "Drag to resize the design (arrow keys too; double-click fits it)" });
  const element = h("div", { class: "wb-design" }, bar, stage, notes, grip);
  bar.hidden = !options.tools;
  status.hidden = true;
  notes.hidden = true;

  const now = (): number => Math.max(HEIGHT_MIN, Math.min(saved ?? Math.min(fit, AUTO_MAX), HEIGHT_MAX));
  const layout = (): void => {
    const height = now();
    stage.style.height = `${height}px`;
    grip.setAttribute("aria-valuenow", String(height));
    grip.setAttribute("aria-valuetext", saved === null ? `${height} pixels, fitted to the design` : `${height} pixels`);
    element.classList.toggle("sized", saved !== null);
  };
  const size = (height: number | null, tell = true): void => {
    saved = height === null ? null : Math.max(HEIGHT_MIN, Math.min(HEIGHT_MAX, Math.round(height)));
    layout();
    if (tell) options.resized(saved);
  };

  const self = {
    frame: () => frame,
    ready: () => frame?.contentWindow?.postMessage(page(html, options.dark()), "*"),
    fits: (height: number) => {
      if (!Number.isFinite(height)) return;
      fit = Math.max(HEIGHT_MIN, Math.min(HEIGHT_MAX, Math.ceil(height)));
      if (saved === null) layout();
    },
  };
  panes.add(self);

  grip.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    grip.setPointerCapture(e.pointerId);
    element.classList.add("dragging"); // the frame lets the pointer through while it drags
    const start = e.clientY;
    const from = now();
    const move = (m: PointerEvent): void => size(from + m.clientY - start, false);
    const up = (): void => {
      element.classList.remove("dragging");
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", up);
      grip.removeEventListener("pointercancel", up);
      options.resized(saved);
    };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
    grip.addEventListener("pointercancel", up);
  });
  grip.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 80 : 16;
    if (e.key === "ArrowUp") size(now() - step);
    else if (e.key === "ArrowDown") size(now() + step);
    else if (e.key === "Home") size(HEIGHT_MIN);
    else if (e.key === "End") size(HEIGHT_MAX);
    else if (e.key === "Enter" || e.key === " ") size(null);
    else return;
    e.preventDefault();
    e.stopPropagation();
  });
  grip.addEventListener("dblclick", () => size(null));
  layout();

  return {
    element,
    show: (next) => {
      html = next;
      // A new frame each time: the old design's scripts stop, and the new one starts clean.
      const fresh = h("iframe", { class: "wb-design-frame", sandbox: "allow-scripts", title: "Design", src: "/static/design.html", referrerpolicy: "no-referrer" }) as HTMLIFrameElement;
      frame = fresh;
      address = null;
      stage.replaceChildren(fresh);
    },
    showAddress: (next) => {
      if (next === address) return;
      address = next;
      html = "";
      if (next === null) {
        frame = null;
        stage.replaceChildren();
        return;
      }
      // Sandboxed without the app's origin, as a design is: the page cannot reach the app or its token.
      const fresh = h("iframe", { class: "wb-design-frame wb-piece-frame", sandbox: FRAME_SANDBOX, title: "Streamlit piece", src: next, referrerpolicy: "no-referrer" }) as HTMLIFrameElement;
      frame = fresh;
      stage.replaceChildren(fresh);
    },
    setState: (state, said) => {
      bar.hidden = !state.label && !options.tools; // a cell that is current says nothing
      status.hidden = !state.label;
      status.textContent = state.label;
      status.className = `wb-design-state ${state.kind}`;
      run.hidden = !state.runnable;
      element.classList.toggle("stale", state.kind === "outOfDate");
      notes.hidden = !said.length;
      notes.replaceChildren(...said.map((n) => h("div", {}, n)));
      layout();
    },
    height: () => saved,
    setHeight: (height) => size(height, false),
    shown: now,
    dispose: () => {
      panes.delete(self);
      frame = null;
      element.remove();
    },
  };
}

/** A script's HTML cell as its lines (domain/html_cells.py script_body): the HTML as one Python
 *  string that does nothing, written as it is whenever Python can hold it that way. */
export function scriptBody(html: string): string {
  const inner = html.endsWith("\n") ? html.slice(0, -1) : html;
  for (const quotes of ['"""', "'''"]) {
    if (!inner.includes(quotes) && !inner.includes("\r")) return `r${quotes}\n${inner}\n${quotes}\n`;
  }
  return `"""\n${inner.replace(/\\/g, "\\\\").replace(/"""/g, '\\"\\"\\"').replace(/\r/g, "\\r")}\n"""\n`;
}
