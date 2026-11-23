/**
 * canvasPage.ts: the Canvas (the owner, 2026-11-21: "instead of Apps on rail we could call it Canvas. we dont
 * wanna muddy the gui for the canvas. I want a simple grid container layout with sizing options ... we can drag
 * and draw containers or right click and insert all available streamlit widgets ... click in to see their
 * properties and edit them"). A page of its own (static/canvas.html) with the rail.
 *
 *   [TOP]        only the page tabs and +
 *   [BOARD]      the page at its width (wide 1200 px, centred 704 px), dots at the snap step (thinned to stay
 *                readable), zoom scaling the view only. Drag on empty grid (or in a container) to draw a
 *                container; drag an item to move it (into another container too), its corner to size it;
 *                snap to the step and to other items' edges and centres with guides (Alt: off for that drag);
 *                arrows nudge by the step (Shift: ten steps, Alt: one pixel); Delete removes; Ctrl+Z / Ctrl+Y
 *   [MENU]       right-click a container: Insert widget ▸ (every widget, grouped, with search), Insert
 *                container, Scrollable, Resizable, Delete; the empty grid: Insert container, Insert widget ▸
 *   [PANES]      Properties (nearest the canvas) and Widgets (at the far right), each its own pane, resizable,
 *                hidden or shown by the bottom bar's buttons (sidePanes.ts, shared with the code pages; remembered per canvas; a hidden Properties pane
 *                stays hidden on a selection, its button shows a dot). Widgets: a card per widget (its
 *                rendered preview, name, description), search, groups; drag a card in, double-click or Insert
 *                puts it in the selected container; hovering a card shows its preview large
 *   [BOTTOM]     sizing (Columns, Row height, Gap, Wide or Centred) | Snap and its step | Undo, Redo | Play,
 *                Launch, Export | Widgets, Properties | zoom (−, %, +, Fit). Narrow: the sizing folds into "…"
 *   [RUN]        Play (F5) shows the page live in place; its ▾ and every right-click menu's run group: Launch
 *                (Ctrl+F5: a build, its own window), Launch with the Performance Analyzer (Ctrl+Shift+F5: its
 *                window beside, recording from the first load), Builds… (canvasBuilds.ts: Compare in Monaco's
 *                diff editor, Restore), Export… (Ctrl+Shift+E)
 *   [ROBUST]     every change is a command the server checks (the layout's rules) and saves at once; each
 *                carries the version it was made on: another window's change is shown as a notice and the
 *                canvas as it is now, never written over; a missing widget is a placeholder (Replace, Remove);
 *                a broken file opens read-only with its line
 *
 * PARTS: the Widgets pane and the previews (canvasGallery.ts), the Properties pane (canvasProps.ts), the menus
 * (canvasMenus.ts), Play, Launch and Export (canvasRun.ts): each given a small host by this page.
 *
 * ROUTING: /streamlit/canvases (list, open), …/{canvas} (state), …/command, …/undo, …/redo, …/play, …/launch
 * (and …/builds, …/perf: routes_launch.py),
 * …/export; /streamlit/widgets (the gallery), …/{name}/preview, …/check-value.
 */
import { api, ApiError, connect, onNotice, requireSession, saidOf } from "./api";
import { type Guide, type Rect } from "./canvasSnap";
import { dotSpacing, gridLines, nudgeBy, snapRect, type Step } from "./canvasGrid";
import { watchTheme } from "./catalogRail";
import { askText, button, clear, dragPointer, dragResize, h, icon, type MenuEntry } from "./dom";
import { errorHere, showError } from "./errorNote";
import { loadingBlock } from "./loading";
import { mountNav, startNav } from "./nav";
import { mountNavRail, openWidgets } from "./rail";
import { nodeMarks, type Wiring, type WiringContext, wiresOverlay } from "./canvasWiring";
import type { Context, WidgetEntry } from "./widgetPage";
import { sidePanes } from "./sidePanes";
import { canvasProps } from "./canvasProps";
import { canvasMenus } from "./canvasMenus";
import { canvasRun } from "./canvasRun";
import { canvasGallery, clearPreviews, DRAG, preview, previewNotice, watchPreviewTheme } from "./canvasGallery";
import { loadPageRules } from "./workbenchPages";

interface Node {
  id: string;
  kind: "container" | "widget";
  show?: "both" | "desktop" | "phone";
  /** Hidden in the app: it runs and its Outs flow, the page gives it no space (drawn faded here). */
  hidden?: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
  props?: ContainerProps;
  children?: Node[];
  widget?: string;
  values?: Record<string, unknown>;
  /** Its Ins' sources and its Events' actions (services/canvas.py wire). */
  wires?: Record<string, Record<string, unknown>>;
}

export interface ContainerProps {
  title: string;
  border: boolean;
  padding: number;
  height: "fit" | "fixed";
  scrollable: boolean;
  resizable: boolean;
  background: string;
  columns: number;
}

interface Sizing {
  columns: number;
  row_height: number;
  gap: number;
  snap: boolean;
  step: Step;
}

interface Model {
  name: string;
  sizing: Sizing;
  pages: { id: string; name: string; children: Node[] }[];
}

interface State {
  canvas: string;
  path: string;
  name: string;
  version: number;
  model: Model;
  read_only: string | null;
  broken: { error: string; line: number | null; copy: string } | null;
  missing: string[];
  marks: Record<string, Record<string, string>>;
  notes: string[];
  undo: number;
  redo: number;
  made?: string | null;
  /** Each page's items in pixels at each layout's design width (desktop 1200, phone 390). */
  views: Record<string, Record<Layout, Node[]>>;
  design: Record<Layout, number>;
  /** Each instance's contract, sources, the Outs' readers, the wires, the broken ones. */
  wiring?: Wiring;
}

/** The page's model as the Canvas's modules see it (canvasProps.ts). */
export type CanvasNode = Node;
export type CanvasState = State;

type Layout = "desktop" | "phone";
/** The widths a layout can be previewed at (the built page fits any of them). */
const RANGE: Record<Layout, [number, number]> = { desktop: [768, 1920], phone: [320, 767] };

const root = document.getElementById("canvas")!;
const params = new URLSearchParams(location.search);
const WINDOW = Math.random().toString(36).slice(2, 10);
let state: State | null = null;
let page = "";
let selected: string[] = [];
let widgets: WidgetEntry[] = [];
let context: Context & WiringContext = { tables: {}, variables: [] };
// The Wiring view: lines between the widgets that pass values (remembered for the session).
let showWires = (() => {
  try {
    return sessionStorage.getItem("sab-canvas-wires") === "1";
  } catch {
    return false;
  }
})();
let zoom = 1;
let layout: Layout = "desktop";
const previewWidth: Record<Layout, number> = { desktop: 1200, phone: 390 };

// ===== the frame =====

const tabs = h("div", { class: "cvs-tabs", role: "tablist", "aria-label": "Pages" });
// The top row's far right (the coordinator's plan, 2026-11-21): ▶ Play with its ▾ (Launch), and Export…; while
// the app runs, Play is Stop. The right-click menu keeps the same group; the bottom bar holds none of them.
const playButton = button("Play", () => void (running() ? stopRunning() : play()), { icon: "play", class: "cvs-play", title: "Play (F5)" });
const playMore = button("More ways to run", (e) => {
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
  menu(r.left, r.bottom + 2, launchEntries(false));
}, { icon: "down", iconOnly: true, class: "cvs-play-more" });
const exportButton = button("Export", () => void exportApp(), { icon: "export", class: "cvs-export", title: "Export… (Ctrl+Shift+E)" });
// Always shown, a block of their own (the owner: "make them look permanent and pronounced"): the tabs scroll.
// The Shared mark (shareApp.ts) beside Play while the launched app is shared with the organization.
const shareHolder = h("span", { class: "cvs-share" });
const runBar = h("span", { class: "cvs-run", role: "group", "aria-label": "Run the app" }, shareHolder, h("span", { class: "cvs-split" }, playButton, playMore), exportButton);
const top = h("header", { class: "cvs-top" }, tabs, h("span", { class: "cvs-grow" }), runBar);
const notice = h("div", { class: "cvs-notice", role: "status", hidden: true });
const board = h("div", { class: "cvs-board", "aria-label": "Canvas", tabindex: "0" });
const scaler = h("div", { class: "cvs-scaler" }, board);
const viewport = h("div", { class: "cvs-viewport" }, scaler);
const live = h("div", { class: "cvs-live", hidden: true });
const propsPane = h("aside", { class: "cvs-pane cvs-props", "aria-label": "Properties" });
const galleryPane = h("aside", { class: "cvs-pane cvs-gallery", "aria-label": "Widgets" });
const bottom = h("footer", { class: "cvs-bottom", role: "toolbar", "aria-label": "Canvas" });
const stage = h("div", { class: "cvs-stage" }, viewport, live);
// While the page plays, its bar's right-click is the same run group (Stop playing first).
live.addEventListener("contextmenu", (e) => {
  if ((e.target as HTMLElement).closest(".cvs-live-frame")) return;
  e.preventDefault();
  menu(e.clientX, e.clientY, runGroup(false));
});
const body = h("div", { class: "cvs-body" }, stage, propsPane, galleryPane);

function layoutPage(): void {
  clear(root, top, notice, body, bottom);
  panes.mount();
}

// ===== remembered per canvas: the panes (this computer: sidePanes.ts), the zoom (this session) =====

const keptKey = (): string => `sab.canvas.panes:${state?.path ?? ""}`;
const panes = sidePanes(
  keptKey,
  [
    { id: "widgets", label: "Widgets", icon: "blade", pane: galleryPane },
    { id: "properties", label: "Properties", icon: "properties", pane: propsPane },
  ],
  { toggleClass: "cvs-toggle", gripClass: "cvs-grip", changed: () => propsDot() },
);
const applyPanes = (): void => panes.apply();
function zoomKey(): string {
  return `sab.canvas.zoom:${state?.path ?? ""}`;
}
function viewKey(): string {
  return `sab.canvas.view:${state?.path ?? ""}`;
}
function rememberView(): void {
  try {
    sessionStorage.setItem(viewKey(), JSON.stringify({ layout, previewWidth }));
  } catch {
    /* this window only */
  }
}
function setLayout(next: Layout): void {
  layout = next;
  rememberView();
  selected = selected.filter((id) => find(id));
  drawBottom();
  drawBoard();
  drawProps();
}
function setZoom(next: number): void {
  zoom = Math.max(0.25, Math.min(4, Math.round(next * 100) / 100));
  try {
    sessionStorage.setItem(zoomKey(), String(zoom));
  } catch {
    /* this window only */
  }
  zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
  drawBoard();
}

// ===== the server =====

async function send(kind: string, body: Record<string, unknown>): Promise<State | null> {
  if (!state) return null;
  try {
    const after = await api<State>(`/streamlit/canvases/${state.canvas}/command`, "POST", { kind, version: state.version, window: WINDOW, layout, ...body });
    take(after);
    return after;
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      await reload();
      say(String(saidOf(e)?.error ?? "The canvas changed: it is shown as it is now. Do it again."));
    } else {
      errorHere(e, {}, board);
    }
    return null;
  }
}

async function reload(): Promise<void> {
  if (!state) return;
  take(await api<State>(`/streamlit/canvases/${state.canvas}`));
}

function say(words: string): void {
  notice.textContent = words;
  notice.hidden = !words;
  if (words) window.setTimeout(() => (notice.textContent === words ? (notice.hidden = true) : undefined), 8000);
}

function take(next: State): void {
  const first = !state || state.canvas !== next.canvas;
  state = next;
  if (!next.model.pages.some((p) => p.id === page)) page = next.model.pages[0]?.id ?? "";
  selected = selected.filter((id) => find(id));
  if (next.notes.length) say(next.notes.join(" "));
  if (first) drawRun(); // the Shared mark for this canvas's app
  if (first) {
    try {
      zoom = Number(sessionStorage.getItem(zoomKey())) || 1;
    } catch {
      zoom = 1;
    }
    zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
    try {
      const kept2 = JSON.parse(sessionStorage.getItem(viewKey()) ?? "null") as { layout?: Layout; previewWidth?: Record<Layout, number> } | null;
      if (kept2?.layout === "phone" || kept2?.layout === "desktop") layout = kept2.layout;
      if (kept2?.previewWidth) Object.assign(previewWidth, kept2.previewWidth);
    } catch {
      /* the defaults */
    }
    applyPanes();
    document.title = `${next.name} · Canvas`;
  }
  drawTabs();
  drawBottom();
  drawBoard();
  drawProps();
}

// ===== the model, read =====

/** The page in front, its items as the layout in front has them (pixels at the layout's design width). */
const pageOf = (): { id: string; name: string; children: Node[] } | undefined => {
  const p = state?.model.pages.find((x) => x.id === page);
  return p ? { id: p.id, name: p.name, children: state?.views[p.id]?.[layout] ?? [] } : undefined;
};

function find(id: string): { node: Node; parent: Node | null } | null {
  const look = (children: Node[], parent: Node | null): { node: Node; parent: Node | null } | null => {
    for (const child of children) {
      if (child.id === id) return { node: child, parent };
      const found = child.children ? look(child.children, child) : null;
      if (found) return found;
    }
    return null;
  };
  for (const p of state?.model.pages ?? []) {
    const found = look(state?.views[p.id]?.[layout] ?? [], null);
    if (found) return found;
  }
  return null;
}

/** The layout's design width: every place is in its pixels. */
const pageWidth = (): number => state?.design[layout] ?? (layout === "phone" ? 390 : 1200);
/** How wide the page is shown (its preview width) over its design width: x and w are drawn times this. */
const stretch = (): number => previewWidth[layout] / pageWidth();
const X = (v: number): number => v * stretch();
const editable = (): boolean => Boolean(state && !state.read_only && !state.broken);

/** An item's top-left corner in page pixels. */
function absolute(id: string): { x: number; y: number } {
  let x = 0;
  let y = 0;
  let at = find(id);
  while (at) {
    x += at.node.x;
    y += at.node.y;
    at = at.parent ? find(at.parent.id) : null;
  }
  return { x, y };
}

// ===== the top bar: the page tabs =====

function drawTabs(): void {
  clear(tabs);
  for (const p of state?.model.pages ?? []) {
    const tab = h("button", { type: "button", role: "tab", class: `cvs-tab${p.id === page ? " current" : ""}`, "aria-selected": String(p.id === page), "data-page": p.id }, p.name);
    tab.addEventListener("click", () => {
      page = p.id;
      selected = [];
      drawTabs();
      drawBoard();
      drawProps();
    });
    tab.addEventListener("dblclick", async () => {
      const name = await askText("The page's name", p.name);
      if (name && name.trim() && name !== p.name) void send("change_page", { page: p.id, name: name.trim() });
    });
    tab.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      menu(e.clientX, e.clientY, [
        { label: "Rename…", run: () => tab.dispatchEvent(new MouseEvent("dblclick")) },
        { label: "Delete page", run: () => void send("remove_page", { page: p.id }), disabled: (state?.model.pages.length ?? 0) < 2 },
      ]);
    });
    tabs.append(tab);
  }
  tabs.append(button("New page", () => void send("add_page", {}).then((s) => (s?.made ? ((page = s.made), drawTabs(), drawBoard()) : undefined)), { icon: "plus", iconOnly: true, class: "ghost cvs-tab-add" }));
}

// ===== the bottom bar =====

const zoomLabel = h("button", { type: "button", class: "cvs-zoom-label", title: "Back to 100%", onclick: () => setZoom(1) }, "100%");
const widgetsToggle = panes.toggle("widgets");
const propsToggle = panes.toggle("properties");
const undoButton = button("Undo", () => void undo(false), { icon: "undo", iconOnly: true, class: "ghost", title: "Undo (Ctrl+Z)" });
const redoButton = button("Redo", () => void undo(true), { icon: "redo", iconOnly: true, class: "ghost", title: "Redo (Ctrl+Y)" });
const sizingMore = button("More sizing", (e) => sizingMenu(e.currentTarget as HTMLElement), { icon: "more", iconOnly: true, class: "ghost cvs-sizing-more" });

function propsDot(): void {
  const hidden = !panes.shown("properties");
  propsToggle.classList.toggle("has-dot", hidden && selected.length > 0);
}

function numberBox(label: string, value: number, min: number, max: number, change: (v: number) => void): HTMLElement {
  const input = h("input", { type: "number", class: "cvs-num", value: String(value), min, max, "aria-label": label, disabled: !editable() });
  input.addEventListener("change", () => {
    const v = Number(input.value);
    if (Number.isInteger(v) && v >= min && v <= max) change(v);
    else input.value = String(value);
  });
  return h("label", { class: "cvs-field" }, h("span", {}, label), input);
}

function sizingControls(): HTMLElement[] {
  const s = state!.model.sizing;
  return [
    numberBox("Columns", s.columns, 1, 48, (v) => void send("sizing", { columns: v })),
    numberBox("Row height", s.row_height, 8, 400, (v) => void send("sizing", { row_height: v })),
    numberBox("Gap", s.gap, 0, 64, (v) => void send("sizing", { gap: v })),
  ];
}

function sizingMenu(anchor: HTMLElement): void {
  const r = anchor.getBoundingClientRect();
  const panel = h("div", { class: "cvs-menu cvs-sizing-menu", role: "dialog", "aria-label": "Sizing" }, ...sizingControls());
  floating(panel, r.left, r.top - 8, true);
}

function drawBottom(): void {
  if (!state) return;
  const s = state.model.sizing;
  const snap = h("input", { type: "checkbox", class: "cvs-snap", role: "switch", checked: s.snap, disabled: !editable(), "aria-label": "Snap" });
  snap.addEventListener("change", () => void send("sizing", { snap: snap.checked }));
  const step = h("select", { class: "cvs-step", "aria-label": "Snap step", disabled: !editable() || !s.snap });
  for (const [value, label] of [["1", "1 px"], ["2", "2 px"], ["4", "4 px"], ["8", "8 px"], ["grid", "Grid cell"]]) step.append(h("option", { value, selected: String(s.step) === value }, label));
  step.addEventListener("change", () => void send("sizing", { step: step.value === "grid" ? "grid" : Number(step.value) }));
  undoButton.disabled = !editable() || state.undo === 0;
  redoButton.disabled = !editable() || state.redo === 0;
  const sep = (): HTMLElement => h("span", { class: "cvs-sep", "aria-hidden": "true" });
  // Phone or Desktop (the owner: "Canvas should only have two layouts phone portrait and desktop").
  const layouts = h("span", { class: "cvs-seg cvs-layouts", role: "group", "aria-label": "Layout" });
  for (const [value, label, glyph] of [["desktop", "Desktop", "desktop"], ["phone", "Phone", "phone"]] as const) {
    layouts.append(h("button", { type: "button", class: `cvs-seg-item${layout === value ? " on" : ""}`, "aria-pressed": String(layout === value), "data-layout": value, onclick: () => setLayout(value) }, icon(glyph), label));
  }
  // The preview width, typed (the frame's right-edge handle drags it): within the layout's range.
  const [low, high] = RANGE[layout];
  const widthBox = h("input", { type: "number", class: "cvs-num cvs-preview-width", min: low, max: high, value: previewWidth[layout], "aria-label": "Preview width (px)", title: `Preview width: ${low} to ${high} px` });
  widthBox.addEventListener("change", () => {
    const v = Math.round(Number(widthBox.value));
    if (!Number.isFinite(v)) return;
    previewWidth[layout] = Math.max(low, Math.min(high, v));
    widthBox.value = String(previewWidth[layout]);
    rememberView();
    drawBoard();
  });
  // The owner (2026-11-21): "Move play launch export to a right click in the canvas": not in this bar.
  clear(
    bottom,
    h("span", { class: "cvs-group cvs-sizing" }, ...sizingControls()),
    sizingMore,
    layouts,
    h("label", { class: "cvs-field cvs-width-field" }, widthBox, h("span", {}, "px")),
    sep(),
    h("label", { class: "cvs-field" }, snap, h("span", {}, "Snap")),
    step,
    sep(),
    undoButton,
    redoButton,
    sep(),
    widgetsToggle,
    propsToggle,
    button("Wiring", () => {
      showWires = !showWires;
      try {
        sessionStorage.setItem("sab-canvas-wires", showWires ? "1" : "0");
      } catch {
        /* the session's own */
      }
      drawBottom();
      drawBoard();
    }, { icon: "link", class: "ghost cvs-toggle cvs-wiring-toggle", pressed: showWires, title: "Show the wires between widgets" }),
    h("span", { class: "cvs-grow" }),
    button("Zoom out", () => setZoom(zoom / 1.25), { icon: "minus", iconOnly: true, class: "ghost" }),
    zoomLabel,
    button("Zoom in", () => setZoom(zoom * 1.25), { icon: "plus", iconOnly: true, class: "ghost" }),
    button("Fit", () => setZoom((viewport.clientWidth - 48) / previewWidth[layout]), { class: "ghost cvs-fit" }),
  );
  propsDot();
}

async function undo(redo: boolean): Promise<void> {
  if (!state || !editable()) return;
  try {
    take(await api<State>(`/streamlit/canvases/${state.canvas}/${redo ? "redo" : "undo"}`, "POST", { window: WINDOW }));
  } catch (e) {
    errorHere(e, {}, bottom);
  }
}

// ===== the board =====

let guidesLayer: HTMLElement | null = null;

function drawBoard(): void {
  if (!state) return;
  const s = state.model.sizing;
  const current = pageOf();
  const children = current?.children ?? [];
  const height = Math.max(600, ...children.map((c) => c.y + c.h + 200));
  const spacing = dotSpacing(s.snap ? s.step : 1, zoom);
  board.style.width = `${previewWidth[layout]}px`;
  board.style.height = `${height}px`;
  board.style.transform = `scale(${zoom})`;
  board.style.setProperty("--dots", `${spacing}px`);
  scaler.style.width = `${(previewWidth[layout] + 24) * zoom}px`;
  scaler.style.height = `${height * zoom}px`;
  board.classList.toggle("read-only", !editable());
  const columns = h("div", { class: "cvs-columns", "aria-hidden": "true" });
  if (s.snap && s.step === "grid") {
    const lines = gridLines(pageWidth(), s.columns, s.gap);
    for (let i = 0; i < lines.length; i += 2) columns.append(h("div", { class: "cvs-column", style: { left: `${X(lines[i]!)}px`, width: `${X(lines[i + 1]! - lines[i]!)}px` } }));
  }
  guidesLayer = h("div", { class: "cvs-guides", "aria-hidden": "true" });
  clear(board, columns, ...children.map((c) => drawNode(c)), guidesLayer, widthHandle());
  if (showWires) {
    const boxOf = (id: string): { x: number; y: number; w: number; h: number } | null => {
      const at = find(id);
      if (!at || !(state?.wiring?.ports[id]?.page === page)) return null;
      const corner = absolute(id);
      return { x: X(corner.x), y: corner.y, w: X(at.node.w), h: at.node.h };
    };
    board.append(wiresOverlay(state.wiring, boxOf, page, previewWidth[layout], height, pageNames()));
  }
  if (state.broken) board.append(h("div", { class: "cvs-broken" }, icon("warning"), `${state.broken.error}${state.broken.line ? ` (line ${state.broken.line})` : ""}. A copy is kept at ${state.broken.copy}.`));
  else if (state.read_only) board.append(h("div", { class: "cvs-broken" }, icon("warning"), state.read_only));
  else if (!children.length) board.append(h("div", { class: "cvs-empty" }, "Drag on the grid to draw a container, or drag a widget here from Widgets."));
}

const entry = (name: string): WidgetEntry | undefined => widgets.find((w) => w.name === name);

/** The canvas's pages' names by id (a wire from another page says its page's name). */
const pageNames = (): Record<string, string> => Object.fromEntries((state?.model.pages ?? []).map((p) => [p.id, p.name]));

function drawNode(node: Node): HTMLElement {
  const place = { left: `${X(node.x)}px`, top: `${node.y}px`, width: `${X(node.w)}px`, height: `${node.h}px` };
  const isSelected = selected.includes(node.id);
  const elsewhere = (node.show ?? "both") !== "both" && node.show !== layout ? " hidden-here" : "";
  if (node.kind === "container") {
    const p = node.props!;
    const element = h(
      "div",
      {
        class: `cvs-node cvs-container${elsewhere}${node.hidden ? " app-hidden" : ""}${isSelected ? " selected" : ""}${p.scrollable ? " scrollable" : ""}${p.border ? "" : " borderless"}`,
        "data-id": node.id,
        style: { ...place, ...(p.background ? { background: p.background } : {}) },
      },
      p.title ? h("div", { class: "cvs-container-title" }, p.title) : null,
      ...(node.children ?? []).map((c) => drawNode(c)),
      node.hidden ? h("div", { class: "cvs-hidden-mark", title: "Hidden in the app" }, icon("eye-off")) : null,
      h("div", { class: "cvs-handle", "data-handle": "se", "aria-hidden": "true" }),
    );
    hook(element, node);
    return element;
  }
  const known = entry(node.widget ?? "");
  const missing = state?.missing.includes(node.id) ?? false;
  const marks = state?.marks[node.id];
  const element = h(
    "div",
    { class: `cvs-node cvs-widget${elsewhere}${node.hidden ? " app-hidden" : ""}${isSelected ? " selected" : ""}${missing ? " missing" : ""}${marks ? " marked" : ""}${nodeMarks(node.id, selected, state?.wiring)}`, "data-id": node.id, "data-widget": node.widget ?? "", style: place },
    missing
      ? h(
          "div",
          { class: "cvs-missing" },
          h("span", {}, `${node.widget} is not in the library any more.`),
          button("Replace", (e) => replaceMenu(node, e.currentTarget as HTMLElement), { class: "ghost" }),
          button("Remove", () => void send("delete", { id: node.id }), { class: "ghost" }),
        )
      : preview(node.widget ?? "", "cvs-widget-preview"),
    missing ? null : instanceText(node, known?.properties ?? []),
    h("div", { class: "cvs-widget-name" }, known?.name ?? node.widget ?? ""),
    node.hidden ? h("div", { class: "cvs-hidden-mark", title: "Hidden in the app" }, icon("eye-off")) : null,
    h("div", { class: "cvs-handle", "data-handle": "se", "aria-hidden": "true" }),
  );
  hook(element, node);
  return element;
}

function replaceMenu(node: Node, anchor: HTMLElement): void {
  const r = anchor.getBoundingClientRect();
  widgetMenu(r.left, r.bottom, (name) => void send("replace_widget", { id: node.id, widget: name }));
}

// ===== selecting, moving, sizing =====

function select(ids: string[]): void {
  selected = ids;
  for (const element of board.querySelectorAll<HTMLElement>(".cvs-node")) {
    const id = element.dataset.id ?? "";
    element.classList.toggle("selected", ids.includes(id));
    for (const mark of ["wire-source", "wire-reader"]) element.classList.toggle(mark, nodeMarks(id, ids, state?.wiring).includes(mark));
  }
  drawProps();
  propsDot();
}

function snapFor(node: Node, parent: Node | null, sizing: boolean, alt: boolean): Parameters<typeof snapRect>[1] {
  const s = state!.model.sizing;
  const siblings = (parent ? parent.children : pageOf()?.children) ?? [];
  return {
    on: s.snap && !alt,
    step: s.step,
    grid: { columns: parent ? parent.props!.columns : s.columns, rowHeight: s.row_height, gap: s.gap, width: parent ? parent.w : pageWidth() },
    others: siblings.filter((o) => o.id !== node.id).map((o) => ({ id: o.id, left: o.x, top: o.y, width: o.w, height: o.h })),
    tolerance: 4 / zoom / stretch(),
    sizing,
  };
}

function drawGuides(found: Guide[], parent: Node | null): void {
  if (!guidesLayer) return;
  const at = parent ? absolute(parent.id) : { x: 0, y: 0 };
  clear(guidesLayer);
  for (const g of found) {
    const style = g.axis === "v" ? { left: `${X(at.x + g.at)}px`, top: `${at.y + g.from}px`, height: `${g.to - g.from}px` } : { top: `${at.y + g.at}px`, left: `${X(at.x + g.from)}px`, width: `${X(g.to - g.from)}px` };
    guidesLayer.append(h("div", { class: `cvs-guide ${g.axis}`, style }));
  }
}

/** The deepest container under a point of the page (not `skip` nor inside it). */
function containerAt(px: number, py: number, skip: string | null): Node | null {
  let best: Node | null = null;
  const walk = (children: Node[], ox: number, oy: number): void => {
    for (const c of children) {
      if (c.kind !== "container" || c.id === skip) continue;
      const x = ox + c.x;
      const y = oy + c.y;
      if (px >= x && px <= x + c.w && py >= y && py <= y + c.h) {
        best = c;
        walk(c.children ?? [], x, y);
      }
    }
  };
  walk(pageOf()?.children ?? [], 0, 0);
  return best;
}

function pagePoint(e: MouseEvent): { x: number; y: number } {
  const r = board.getBoundingClientRect();
  return { x: (e.clientX - r.left) / zoom / stretch(), y: (e.clientY - r.top) / zoom };
}

function hook(element: HTMLElement, node: Node): void {
  let sizing = false;
  let start = { x: 0, y: 0 };
  let at: ReturnType<typeof find> = null;
  let moved: Rect | null = null;
  const ghost = element;
  dragPointer(element, {
    onStart: (e) => {
      if ((e.target as HTMLElement).closest("button")) return false;
      e.stopPropagation();
      board.focus({ preventScroll: true });
      const additive = e.shiftKey || e.ctrlKey || e.metaKey;
      if (additive) select(selected.includes(node.id) ? selected.filter((i) => i !== node.id) : [...selected, node.id]);
      else if (!selected.includes(node.id)) select([node.id]);
      if (!editable() || additive) return false;
      sizing = (e.target as HTMLElement).dataset.handle === "se";
      start = pagePoint(e);
      at = find(node.id);
      moved = null;
      return at ? undefined : false;
    },
    onMove: (_dx, _dy, m) => {
      if (!at) return;
      const now = pagePoint(m);
      const dx = now.x - start.x;
      const dy = now.y - start.y;
      if (!moved && Math.abs(dx) + Math.abs(dy) < 3 / zoom) return;
      const raw: Rect = sizing ? { id: node.id, left: node.x, top: node.y, width: node.w + dx, height: node.h + dy } : { id: node.id, left: node.x + dx, top: node.y + dy, width: node.w, height: node.h };
      const done = snapRect(raw, snapFor(node, at.parent, sizing, m.altKey));
      moved = done.rect;
      ghost.style.left = `${X(moved.left)}px`;
      ghost.style.top = `${moved.top}px`;
      ghost.style.width = `${X(moved.width)}px`;
      ghost.style.height = `${moved.height}px`;
      ghost.classList.add("dragging");
      drawGuides(done.guides, at.parent);
    },
    onEnd: (u) => {
      ghost.classList.remove("dragging");
      if (guidesLayer) clear(guidesLayer);
      if (!moved || !at) return;
      if (!u) return drawBoard(); // the pointer was taken away: it stays where it was
      const r: Rect = moved;
      if (sizing) {
        void send("move", { id: node.id, w: Math.max(1, r.width), h: Math.max(1, r.height) }).then((s) => (s ? undefined : drawBoard()));
        return;
      }
      // Dropped over another container: it goes in there.
      const point = pagePoint(u);
      const target = containerAt(point.x, point.y, node.id);
      const now = at.parent?.id ?? null;
      if ((target?.id ?? null) !== now && (target || node.kind === "container")) {
        const origin = target ? absolute(target.id) : { x: 0, y: 0 };
        const from = at.parent ? absolute(at.parent.id) : { x: 0, y: 0 };
        const x = Math.max(0, Math.round(from.x + r.left - origin.x));
        const y = Math.max(0, Math.round(from.y + r.top - origin.y));
        void send("move", { id: node.id, parent: target?.id ?? "", x, y }).then((s) => (s ? undefined : drawBoard()));
        return;
      }
      void send("move", { id: node.id, x: Math.max(0, r.left), y: Math.max(0, r.top) }).then((s) => (s ? undefined : drawBoard()));
    },
  });
  element.addEventListener("dblclick", (e) => {
    e.stopPropagation();
    if (node.kind === "widget" && node.widget) openWidgets(node.widget);
  });
  element.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!selected.includes(node.id)) select([node.id]);
    nodeMenu(node, e);
  });
  element.addEventListener("dragover", (e) => {
    if (node.kind === "container" && e.dataTransfer?.types.includes(DRAG)) {
      e.preventDefault();
      e.stopPropagation();
      element.classList.add("drop");
    }
  });
  element.addEventListener("dragleave", () => element.classList.remove("drop"));
  element.addEventListener("drop", (e) => {
    element.classList.remove("drop");
    const name = e.dataTransfer?.getData(DRAG);
    if (node.kind !== "container" || !name) return;
    e.preventDefault();
    e.stopPropagation();
    const point = pagePoint(e);
    const origin = absolute(node.id);
    void insert(name, node.id, Math.max(0, Math.round(point.x - origin.x)), Math.max(0, Math.round(point.y - origin.y)));
  });
}

// Drawing a container on empty grid (or empty room in a container).
{
  let start = { x: 0, y: 0 };
  let parent: Node | null = null;
  let origin = { x: 0, y: 0 };
  let band: HTMLElement | null = null;
  let made: Rect | null = null;
  dragPointer(board, {
    onStart: (e) => {
      if (!state) return false;
      const target = e.target as HTMLElement;
      if (target.closest(".cvs-node") && !target.classList.contains("cvs-container")) return false;
      select([]);
      if (!editable()) return false;
      board.focus({ preventScroll: true });
      start = pagePoint(e);
      parent = containerAt(start.x, start.y, null);
      origin = parent ? absolute(parent.id) : { x: 0, y: 0 };
      band = h("div", { class: "cvs-band" });
      board.append(band);
      made = null;
      return undefined;
    },
    onMove: (_dx, _dy, m) => {
      if (!band) return;
      const now = pagePoint(m);
      const raw: Rect = { id: "new", left: Math.min(start.x, now.x) - origin.x, top: Math.min(start.y, now.y) - origin.y, width: Math.abs(now.x - start.x), height: Math.abs(now.y - start.y) };
      const fake: Node = { id: "new", kind: "container", x: 0, y: 0, w: 0, h: 0 };
      const placed = snapRect({ ...raw }, snapFor(fake, parent, false, m.altKey)).rect;
      const sized = snapRect({ ...placed, width: raw.left + raw.width - placed.left, height: raw.top + raw.height - placed.top }, snapFor(fake, parent, true, m.altKey)).rect;
      made = sized;
      Object.assign(band.style, { left: `${X(origin.x + sized.left)}px`, top: `${origin.y + sized.top}px`, width: `${X(sized.width)}px`, height: `${sized.height}px` });
    },
    onEnd: (up) => {
      band?.remove();
      band = null;
      const r: Rect | null = made;
      if (!up || !r || r.width < 16 || r.height < 16) return;
      void send("add_container", { page, parent: parent?.id ?? null, x: Math.max(0, r.left), y: Math.max(0, r.top), w: r.width, h: r.height }).then((s) => (s?.made ? select([s.made]) : undefined));
    },
  });
}

board.addEventListener("contextmenu", (e) => {
  if ((e.target as HTMLElement).closest(".cvs-node")) return;
  e.preventDefault();
  const point = pagePoint(e);
  const own: MenuEntry[] = editable()
    ? [
        { label: "Insert container", run: () => void send("add_container", { page, x: Math.round(point.x), y: Math.round(point.y) }) },
        { label: "Insert widget", sub: (x, y) => widgetMenu(x, y, (name) => void send("insert_widget", { page, widget: name, x: Math.round(point.x), y: Math.round(point.y) })) },
      ]
    : [];
  menu(e.clientX, e.clientY, [...own, ...runGroup(own.length > 0)]);
});

board.addEventListener("dragover", (e) => {
  if (e.dataTransfer?.types.includes(DRAG)) e.preventDefault();
});
board.addEventListener("drop", (e) => {
  const name = e.dataTransfer?.getData(DRAG);
  if (!name) return;
  e.preventDefault();
  const point = pagePoint(e);
  void insert(name, null, Math.round(point.x), Math.round(point.y));
});

async function insert(name: string, parent: string | null, x?: number, y?: number): Promise<void> {
  const body: Record<string, unknown> = { page, widget: name, parent };
  if (x !== undefined && y !== undefined) Object.assign(body, { x, y });
  const after = await send("insert_widget", body);
  if (after?.made) select([after.made]);
}

/** Where a double-click or Insert puts a widget: the selected container, or the selected widget's. */
function selectedContainer(): string | null {
  const at = selected[0] ? find(selected[0]) : null;
  if (!at) return null;
  return at.node.kind === "container" ? at.node.id : (at.parent?.id ?? null);
}

// Keys: arrows nudge, Delete removes, Ctrl+Z / Ctrl+Y, Esc, Insert.
document.addEventListener("keydown", (e) => {
  // The run group's keys, anywhere on the page (the browser's own F5 never reloads the canvas).
  // F5 Play, Ctrl+F5 Launch, Ctrl+Shift+F5 Launch with the Performance Analyzer (Visual Studio's keys).
  if (e.key === "F5" && state) {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) void launch(e.shiftKey);
    else void play();
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "e" && state) {
    e.preventDefault();
    return void exportApp();
  }
  const typing = (e.target as HTMLElement).closest("input, textarea, select, [contenteditable]");
  if (typing) return;
  if ((e.ctrlKey || e.metaKey) && !e.altKey) {
    if (e.key.toLowerCase() === "z") {
      e.preventDefault();
      void undo(e.shiftKey);
    } else if (e.key.toLowerCase() === "y") {
      e.preventDefault();
      void undo(true);
    } else if (e.key === "=" || e.key === "+") {
      e.preventDefault();
      setZoom(zoom * 1.25);
    } else if (e.key === "-") {
      e.preventDefault();
      setZoom(zoom / 1.25);
    } else if (e.key === "0") {
      e.preventDefault();
      setZoom(1);
    }
    return;
  }
  if (e.key === "Escape") {
    closeFloating();
    hidePreview();
    if (!live.hidden) return void stopPlay();
    return select([]);
  }
  if (!state || !editable()) return;
  if ((e.key === "Delete" || e.key === "Backspace") && selected.length) {
    e.preventDefault();
    const ids = [...selected];
    select([]);
    void (async () => {
      for (const id of ids) if (find(id)) await send("delete", { id });
    })();
    return;
  }
  if (e.key === "Insert" && gallery.focused()) return void insert(gallery.focused()!, selectedContainer());
  const arrows: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  const arrow = arrows[e.key];
  if (arrow && selected.length === 1) {
    e.preventDefault();
    const at = find(selected[0]!);
    if (!at) return;
    const s = state.model.sizing;
    const by = nudgeBy(s.snap ? s.step : 1, e, { columns: at.parent ? at.parent.props!.columns : s.columns, rowHeight: s.row_height, gap: s.gap, width: at.parent ? at.parent.w : pageWidth() });
    void send("move", { id: at.node.id, x: Math.max(0, at.node.x + arrow[0] * by), y: Math.max(0, at.node.y + arrow[1] * by) });
  }
});

viewport.addEventListener(
  "wheel",
  (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    setZoom(zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1));
  },
  { passive: false },
);

// ===== menus (canvasMenus.ts) =====

const menus = canvasMenus({
  editable: () => editable(),
  send: (kind, body) => send(kind, body),
  insert: (name, parent) => insert(name, parent),
  grouped: () => grouped(),
  playing: () => !live.hidden,
  play: () => play(),
  stopPlay: () => stopPlay(),
  launch: (analyzer) => launch(analyzer),
  stopLaunch: () => stopLaunch(),
  exportApp: () => exportApp(),
  get buildsHost() {
    return run.buildsHost;
  },
  get state() {
    return state;
  },
  get page() {
    return page;
  },
  get launched() {
    return run.isLaunched();
  },
});
const { closeFloating, floating, menu, launchEntries, runGroup, shareable, nodeMenu, widgetMenu } = menus;

// ===== the Widgets pane (canvasGallery.ts) =====

const gallery = canvasGallery({
  pane: galleryPane,
  editable: () => editable(),
  insert: (name, parent) => insert(name, parent),
  selectedContainer: () => selectedContainer(),
  get widgets() {
    return widgets;
  },
});
const { drawGallery, grouped, hidePreview } = gallery;

/** The instance's own words over its preview. The picture is the widget's, drawn once with its defaults (one
 *  per widget file and theme: server/previews.py); a picture per instance would mean a Streamlit run and a
 *  photograph per edit, so the instance's title (or label, heading, text) is laid over its top instead, only
 *  where it differs from the default the picture shows. Never a table, a wire or a secret: text properties. */
const INSTANCE_TEXT = ["title", "label", "heading", "header", "text", "caption"];
function instanceText(node: Node, properties: { name: string; default: unknown }[]): HTMLElement | null {
  const values = node.values ?? {};
  for (const name of INSTANCE_TEXT) {
    const value = values[name];
    const plain = properties.find((p) => p.name === name)?.default;
    if (typeof value === "string" && value.trim() && value !== plain && !value.startsWith("out:")) {
      return h("div", { class: "cvs-instance-text", title: `${name}: ${value}` }, value);
    }
  }
  return null;
}

// ===== the Properties pane (canvasProps.ts) =====

const { drawProps } = canvasProps({
  pane: propsPane, window: WINDOW, send, take, reload, find, entry, pageNames, numberBox,
  editable: () => editable(),
  get state() {
    return state;
  },
  get selected() {
    return selected;
  },
  get context() {
    return context;
  },
});

/** The page frame's right edge: dragged, the page is previewed at another width within its layout's range
 *  (the built page fits any of them); its width in px beside it. */
function widthHandle(): HTMLElement {
  const label = h("span", { class: "cvs-width-label" }, `${previewWidth[layout]} px`);
  const grip = h("div", { class: "cvs-width-handle", role: "separator", "aria-orientation": "vertical", "aria-label": "Page width", title: "Drag to preview another width" }, label);
  let from = 0;
  // The board (this grip with it) is drawn again at each step: dragPointer hears the moves at the window.
  dragResize(grip, {
    start: () => void (from = previewWidth[layout]),
    move: (dx) => {
      const [low, high] = RANGE[layout];
      previewWidth[layout] = Math.round(Math.max(low, Math.min(high, from + dx / zoom)));
      drawBoard();
    },
    end: rememberView,
    stop: true,
  });
  return grip;
}

// ===== Play, Launch, Export (canvasRun.ts) =====

const run = canvasRun({
  live, viewport, stage, notice, playButton, shareHolder, previewWidth, say, take,
  shareable: () => shareable(),
  get state() {
    return state;
  },
  get page() {
    return page;
  },
  get layout() {
    return layout;
  },
});
const { running, stopRunning, drawRun, play, stopPlay, stopLaunch, launch, exportApp } = run;

// ===== the landing: the project's canvases =====

async function landing(): Promise<void> {
  const listed = await api<{ folder: string | null; canvases: { name: string; path: string }[]; old: { name: string; said: string }[] }>("/streamlit/canvases");
  const list = h("div", { class: "cvs-landing" }, h("h1", {}, "Canvas"));
  if (!listed.folder) list.append(h("p", {}, "Open a project first: its canvases are its files."));
  for (const c of listed.canvases) list.append(h("a", { class: "cvs-landing-item", href: `?path=${encodeURIComponent(c.path)}` }, icon("page"), c.name));
  for (const o of listed.old) list.append(h("div", { class: "cvs-landing-old" }, icon("info"), `${o.name}: ${o.said}`));
  if (listed.folder) {
    list.append(
      button(
        "New canvas",
        async () => {
          const name = await askText("The new canvas's name", "App");
          if (name) void api<State>("/streamlit/canvases", "POST", { name, folder: listed.folder }).then((s) => location.assign(`?path=${encodeURIComponent(s.path)}${location.hash}`));
        },
        { icon: "plus", class: "primary" },
      ),
    );
  }
  clear(root, list);
}

// ===== start =====

async function start(): Promise<void> {
  watchTheme();
  watchPreviewTheme();
  if (!(await requireSession())) return;
  await loadPageRules();
  mountNav("canvas");
  mountNavRail("canvas");
  startNav();
  const path = params.get("path");
  if (!path) return void landing().catch((e) => errorHere(e, {}, root));
  layoutPage();
  board.append(loadingBlock("Opening the canvas…"));
  try {
    const [listing, ctx] = await Promise.all([api<{ widgets: WidgetEntry[] }>("/streamlit/widgets"), api<Context>("/streamlit/widgets/context")]);
    widgets = listing.widgets;
    context = ctx;
    take(await api<State>("/streamlit/canvases", "POST", { path }));
  } catch (e) {
    clear(board);
    showError(board, e);
    return;
  }
  drawGallery();
  connect(() => undefined, { canvas: "1", window: WINDOW });
  onNotice((n) => {
    const said = n as unknown as { type: string; canvas?: string; window?: string };
    previewNotice(said);
    if (said.type === "canvas_changed" && state && said.canvas === state.canvas && said.window !== WINDOW) {
      void reload().then(() => say("The canvas changed in another window: it is shown as it is now."));
    }
    if (said.type === "widgets_changed") {
      void api<{ widgets: WidgetEntry[] }>("/streamlit/widgets").then((l) => {
        widgets = l.widgets;
        clearPreviews();
        drawGallery();
        void reload();
      });
    }
  });
}

void start();
