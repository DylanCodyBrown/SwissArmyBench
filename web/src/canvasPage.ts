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
 *                hidden or shown by the bottom bar's buttons (remembered per canvas; a hidden Properties pane
 *                stays hidden on a selection, its button shows a dot). Widgets: a card per widget (its
 *                rendered preview, name, description), search, groups; drag a card in, double-click or Insert
 *                puts it in the selected container; hovering a card shows its preview large
 *   [BOTTOM]     sizing (Columns, Row height, Gap, Wide or Centred) | Snap and its step | Undo, Redo | Play,
 *                Launch, Export | Widgets, Properties | zoom (−, %, +, Fit). Narrow: the sizing folds into "…"
 *   [ROBUST]     every change is a command the server checks (the layout's rules) and saves at once; each
 *                carries the version it was made on: another window's change is shown as a notice and the
 *                canvas as it is now, never written over; a missing widget is a placeholder (Replace, Remove);
 *                a broken file opens read-only with its line
 *
 * ROUTING: /streamlit/canvases (list, open), …/{canvas} (state), …/command, …/undo, …/redo, …/play, …/launch,
 * …/export; /streamlit/widgets (the gallery), …/{name}/preview, …/check-value.
 */
import { api, ApiError, connect, onNotice, requireSession, saidOf } from "./api";
import { type Guide, type Rect } from "./canvasSnap";
import { dotSpacing, gridLines, nudgeBy, snapRect, type Step } from "./canvasGrid";
import { watchTheme } from "./catalogRail";
import { button, clear, h, icon, toast } from "./dom";
import { clearError, errorHere, showError } from "./errorNote";
import { chooseFile } from "./fileChooser";
import { busyButton, loadingBlock } from "./loading";
import { mountNav, startNav } from "./nav";
import { mountNavRail, openWidgets } from "./rail";
import { effectiveTheme } from "./theme";
import { type Prop, propertyField } from "./widgetFields";
import type { Context, WidgetEntry } from "./widgetPage";

interface Node {
  id: string;
  kind: "container" | "widget";
  x: number;
  y: number;
  w: number;
  h: number;
  props?: ContainerProps;
  children?: Node[];
  widget?: string;
  values?: Record<string, unknown>;
}

interface ContainerProps {
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
  width: "wide" | "centered";
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
}

const WIDTHS = { wide: 1200, centered: 704 } as const;
const root = document.getElementById("canvas")!;
const params = new URLSearchParams(location.search);
const WINDOW = Math.random().toString(36).slice(2, 10);
let state: State | null = null;
let page = "";
let selected: string[] = [];
let widgets: WidgetEntry[] = [];
let context: Context = { tables: {}, variables: [] };
let zoom = 1;

// ===== the frame =====

const tabs = h("div", { class: "cvs-tabs", role: "tablist", "aria-label": "Pages" });
const top = h("header", { class: "cvs-top" }, tabs);
const notice = h("div", { class: "cvs-notice", role: "status", hidden: true });
const board = h("div", { class: "cvs-board", "aria-label": "Canvas", tabindex: "0" });
const scaler = h("div", { class: "cvs-scaler" }, board);
const viewport = h("div", { class: "cvs-viewport" }, scaler);
const live = h("div", { class: "cvs-live", hidden: true });
const propsPane = h("aside", { class: "cvs-pane cvs-props", "aria-label": "Properties" });
const galleryPane = h("aside", { class: "cvs-pane cvs-gallery", "aria-label": "Widgets" });
const bottom = h("footer", { class: "cvs-bottom", role: "toolbar", "aria-label": "Canvas" });
const stage = h("div", { class: "cvs-stage" }, viewport, live);
const body = h("div", { class: "cvs-body" }, stage, propsPane, galleryPane);

function layout(): void {
  clear(root, top, notice, body, bottom);
  for (const pane of [propsPane, galleryPane]) {
    const grip = h("div", { class: "cvs-grip", role: "separator", "aria-orientation": "vertical", title: "Drag to resize" });
    pane.before(grip);
    grip.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const start = e.clientX;
      const width = pane.getBoundingClientRect().width;
      const move = (m: PointerEvent): void => {
        pane.style.width = `${Math.max(200, Math.min(560, width - (m.clientX - start)))}px`;
      };
      const up = (): void => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        remember();
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });
  }
}

// ===== remembered per canvas: the panes (this computer), the zoom (this session) =====

interface Kept {
  widgets: boolean;
  properties: boolean;
  widgetsWidth?: string;
  propertiesWidth?: string;
}

const keptKey = (): string => `sab.canvas.panes:${state?.path ?? ""}`;
function kept(): Kept {
  try {
    return { widgets: true, properties: true, ...(JSON.parse(localStorage.getItem(keptKey()) ?? "{}") as Partial<Kept>) };
  } catch {
    return { widgets: true, properties: true };
  }
}
function remember(change: Partial<Kept> = {}): void {
  const now = { ...kept(), ...change, widgetsWidth: galleryPane.style.width || undefined, propertiesWidth: propsPane.style.width || undefined };
  try {
    localStorage.setItem(keptKey(), JSON.stringify(now));
  } catch {
    /* no storage: this window only */
  }
  applyPanes();
}
function applyPanes(): void {
  const now = kept();
  galleryPane.hidden = !now.widgets;
  propsPane.hidden = !now.properties;
  (galleryPane.previousElementSibling as HTMLElement | null)?.toggleAttribute("hidden", !now.widgets);
  (propsPane.previousElementSibling as HTMLElement | null)?.toggleAttribute("hidden", !now.properties);
  if (now.widgetsWidth) galleryPane.style.width = now.widgetsWidth;
  if (now.propertiesWidth) propsPane.style.width = now.propertiesWidth;
  widgetsToggle.setAttribute("aria-pressed", String(now.widgets));
  propsToggle.setAttribute("aria-pressed", String(now.properties));
  propsDot();
}
function zoomKey(): string {
  return `sab.canvas.zoom:${state?.path ?? ""}`;
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
    const after = await api<State>(`/streamlit/canvases/${state.canvas}/command`, "POST", { kind, version: state.version, window: WINDOW, ...body });
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
  if (first) {
    try {
      zoom = Number(sessionStorage.getItem(zoomKey())) || 1;
    } catch {
      zoom = 1;
    }
    zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
    applyPanes();
    document.title = `${next.name} · Canvas`;
  }
  drawTabs();
  drawBottom();
  drawBoard();
  drawProps();
}

// ===== the model, read =====

const pageOf = (): State["model"]["pages"][number] | undefined => state?.model.pages.find((p) => p.id === page);

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
    const found = look(p.children, null);
    if (found) return found;
  }
  return null;
}

const pageWidth = (): number => WIDTHS[state?.model.sizing.width ?? "wide"];
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
    tab.addEventListener("dblclick", () => {
      const name = prompt("The page's name", p.name);
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
const widgetsToggle = button("Widgets", () => remember({ widgets: !kept().widgets }), { icon: "blade", class: "ghost cvs-toggle", pressed: true });
const propsToggle = button("Properties", () => remember({ properties: !kept().properties }), { icon: "properties", class: "ghost cvs-toggle", pressed: true });
const undoButton = button("Undo", () => void undo(false), { icon: "undo", iconOnly: true, class: "ghost", title: "Undo (Ctrl+Z)" });
const redoButton = button("Redo", () => void undo(true), { icon: "redo", iconOnly: true, class: "ghost", title: "Redo (Ctrl+Y)" });
const sizingMore = button("More sizing", (e) => sizingMenu(e.currentTarget as HTMLElement), { icon: "more", iconOnly: true, class: "ghost cvs-sizing-more" });

function propsDot(): void {
  const hidden = !kept().properties;
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
  const width = h("span", { class: "cvs-seg", role: "group", "aria-label": "Page width" });
  for (const [value, label] of [["wide", "Wide"], ["centered", "Centred"]] as const) {
    width.append(h("button", { type: "button", class: `cvs-seg-item${s.width === value ? " on" : ""}`, "aria-pressed": String(s.width === value), disabled: !editable(), onclick: () => void send("sizing", { width: value }) }, label));
  }
  return [
    numberBox("Columns", s.columns, 1, 48, (v) => void send("sizing", { columns: v })),
    numberBox("Row height", s.row_height, 8, 400, (v) => void send("sizing", { row_height: v })),
    numberBox("Gap", s.gap, 0, 64, (v) => void send("sizing", { gap: v })),
    width,
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
  clear(
    bottom,
    h("span", { class: "cvs-group cvs-sizing" }, ...sizingControls()),
    sizingMore,
    sep(),
    h("label", { class: "cvs-field" }, snap, h("span", {}, "Snap")),
    step,
    sep(),
    undoButton,
    redoButton,
    sep(),
    button("Play", () => void play(), { icon: "play", class: "ghost cvs-play" }),
    button("Launch", () => void launch(), { icon: "popout", class: "ghost cvs-launch" }),
    button("Export", () => void exportApp(), { icon: "export", class: "ghost cvs-export" }),
    sep(),
    widgetsToggle,
    propsToggle,
    h("span", { class: "cvs-grow" }),
    button("Zoom out", () => setZoom(zoom / 1.25), { icon: "minus", iconOnly: true, class: "ghost" }),
    zoomLabel,
    button("Zoom in", () => setZoom(zoom * 1.25), { icon: "plus", iconOnly: true, class: "ghost" }),
    button("Fit", () => setZoom((viewport.clientWidth - 48) / pageWidth()), { class: "ghost cvs-fit" }),
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
  board.style.width = `${pageWidth()}px`;
  board.style.height = `${height}px`;
  board.style.transform = `scale(${zoom})`;
  board.style.setProperty("--dots", `${spacing}px`);
  scaler.style.width = `${pageWidth() * zoom}px`;
  scaler.style.height = `${height * zoom}px`;
  board.classList.toggle("read-only", !editable());
  const columns = h("div", { class: "cvs-columns", "aria-hidden": "true" });
  if (s.snap && s.step === "grid") {
    const lines = gridLines(pageWidth(), s.columns, s.gap);
    for (let i = 0; i < lines.length; i += 2) columns.append(h("div", { class: "cvs-column", style: { left: `${lines[i]}px`, width: `${lines[i + 1]! - lines[i]!}px` } }));
  }
  guidesLayer = h("div", { class: "cvs-guides", "aria-hidden": "true" });
  clear(board, columns, ...children.map((c) => drawNode(c)), guidesLayer);
  if (state.broken) board.append(h("div", { class: "cvs-broken" }, icon("warning"), `${state.broken.error}${state.broken.line ? ` (line ${state.broken.line})` : ""}. A copy is kept at ${state.broken.copy}.`));
  else if (state.read_only) board.append(h("div", { class: "cvs-broken" }, icon("warning"), state.read_only));
  else if (!children.length) board.append(h("div", { class: "cvs-empty" }, "Drag on the grid to draw a container, or drag a widget here from Widgets."));
}

const entry = (name: string): WidgetEntry | undefined => widgets.find((w) => w.name === name);

function drawNode(node: Node): HTMLElement {
  const place = { left: `${node.x}px`, top: `${node.y}px`, width: `${node.w}px`, height: `${node.h}px` };
  const isSelected = selected.includes(node.id);
  if (node.kind === "container") {
    const p = node.props!;
    const element = h(
      "div",
      {
        class: `cvs-node cvs-container${isSelected ? " selected" : ""}${p.scrollable ? " scrollable" : ""}${p.border ? "" : " borderless"}`,
        "data-id": node.id,
        style: { ...place, ...(p.background ? { background: p.background } : {}) },
      },
      p.title ? h("div", { class: "cvs-container-title" }, p.title) : null,
      ...(node.children ?? []).map((c) => drawNode(c)),
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
    { class: `cvs-node cvs-widget${isSelected ? " selected" : ""}${missing ? " missing" : ""}${marks ? " marked" : ""}`, "data-id": node.id, "data-widget": node.widget ?? "", style: place },
    missing
      ? h(
          "div",
          { class: "cvs-missing" },
          h("span", {}, `${node.widget} is not in the library any more.`),
          button("Replace", (e) => replaceMenu(node, e.currentTarget as HTMLElement), { class: "ghost" }),
          button("Remove", () => void send("delete", { id: node.id }), { class: "ghost" }),
        )
      : preview(node.widget ?? "", "cvs-widget-preview"),
    h("div", { class: "cvs-widget-name" }, known?.name ?? node.widget ?? ""),
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
  for (const element of board.querySelectorAll<HTMLElement>(".cvs-node")) element.classList.toggle("selected", ids.includes(element.dataset.id ?? ""));
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
    tolerance: 4 / zoom,
    sizing,
  };
}

function drawGuides(found: Guide[], parent: Node | null): void {
  if (!guidesLayer) return;
  const at = parent ? absolute(parent.id) : { x: 0, y: 0 };
  clear(guidesLayer);
  for (const g of found) {
    const style = g.axis === "v" ? { left: `${at.x + g.at}px`, top: `${at.y + g.from}px`, height: `${g.to - g.from}px` } : { top: `${at.y + g.at}px`, left: `${at.x + g.from}px`, width: `${g.to - g.from}px` };
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
  return { x: (e.clientX - r.left) / zoom, y: (e.clientY - r.top) / zoom };
}

function hook(element: HTMLElement, node: Node): void {
  element.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
    e.stopPropagation();
    board.focus({ preventScroll: true });
    const additive = e.shiftKey || e.ctrlKey || e.metaKey;
    if (additive) select(selected.includes(node.id) ? selected.filter((i) => i !== node.id) : [...selected, node.id]);
    else if (!selected.includes(node.id)) select([node.id]);
    if (!editable() || additive) return;
    const sizing = (e.target as HTMLElement).dataset.handle === "se";
    const start = pagePoint(e);
    const at = find(node.id);
    if (!at) return;
    let moved: Rect | null = null;
    const ghost = element;
    const move = (m: PointerEvent): void => {
      const now = pagePoint(m);
      const dx = now.x - start.x;
      const dy = now.y - start.y;
      if (!moved && Math.abs(dx) + Math.abs(dy) < 3 / zoom) return;
      const raw: Rect = sizing ? { id: node.id, left: node.x, top: node.y, width: node.w + dx, height: node.h + dy } : { id: node.id, left: node.x + dx, top: node.y + dy, width: node.w, height: node.h };
      const done = snapRect(raw, snapFor(node, at.parent, sizing, m.altKey));
      moved = done.rect;
      ghost.style.left = `${moved.left}px`;
      ghost.style.top = `${moved.top}px`;
      ghost.style.width = `${moved.width}px`;
      ghost.style.height = `${moved.height}px`;
      ghost.classList.add("dragging");
      drawGuides(done.guides, at.parent);
    };
    const up = (u: PointerEvent): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      ghost.classList.remove("dragging");
      if (guidesLayer) clear(guidesLayer);
      if (!moved) return;
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
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
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
board.addEventListener("pointerdown", (e) => {
  if (e.button !== 0 || !state) return;
  const target = e.target as HTMLElement;
  if (target.closest(".cvs-node") && !target.classList.contains("cvs-container")) return;
  select([]);
  if (!editable()) return;
  board.focus({ preventScroll: true });
  const start = pagePoint(e);
  const parent = containerAt(start.x, start.y, null);
  const origin = parent ? absolute(parent.id) : { x: 0, y: 0 };
  const band = h("div", { class: "cvs-band" });
  board.append(band);
  let made: Rect | null = null;
  const move = (m: PointerEvent): void => {
    const now = pagePoint(m);
    const raw: Rect = { id: "new", left: Math.min(start.x, now.x) - origin.x, top: Math.min(start.y, now.y) - origin.y, width: Math.abs(now.x - start.x), height: Math.abs(now.y - start.y) };
    const fake: Node = { id: "new", kind: "container", x: 0, y: 0, w: 0, h: 0 };
    const placed = snapRect({ ...raw }, snapFor(fake, parent, false, m.altKey)).rect;
    const sized = snapRect({ ...placed, width: raw.left + raw.width - placed.left, height: raw.top + raw.height - placed.top }, snapFor(fake, parent, true, m.altKey)).rect;
    made = sized;
    Object.assign(band.style, { left: `${origin.x + sized.left}px`, top: `${origin.y + sized.top}px`, width: `${sized.width}px`, height: `${sized.height}px` });
  };
  const up = (): void => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    band.remove();
    const r: Rect | null = made;
    if (!r || r.width < 16 || r.height < 16) return;
    void send("add_container", { page, parent: parent?.id ?? null, x: Math.max(0, r.left), y: Math.max(0, r.top), w: r.width, h: r.height }).then((s) => (s?.made ? select([s.made]) : undefined));
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
});

board.addEventListener("contextmenu", (e) => {
  if ((e.target as HTMLElement).closest(".cvs-node")) return;
  e.preventDefault();
  if (!editable()) return;
  const point = pagePoint(e);
  menu(e.clientX, e.clientY, [
    { label: "Insert container", run: () => void send("add_container", { page, x: Math.round(point.x), y: Math.round(point.y) }) },
    { label: "Insert widget", sub: (x, y) => widgetMenu(x, y, (name) => void send("insert_widget", { page, widget: name, x: Math.round(point.x), y: Math.round(point.y) })) },
  ]);
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
  if (e.key === "Insert" && galleryFocus) return void insert(galleryFocus, selectedContainer());
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

// ===== menus =====

interface MenuEntry {
  label: string;
  run?: () => void;
  sub?: (x: number, y: number) => void;
  checked?: boolean;
  disabled?: boolean;
}

let floatingOpen: HTMLElement[] = [];
function closeFloating(): void {
  for (const f of floatingOpen) f.remove();
  floatingOpen = [];
}
function floating(element: HTMLElement, x: number, y: number, above = false, keep = false): void {
  if (!keep) closeFloating();
  document.body.append(element);
  floatingOpen.push(element);
  const r = element.getBoundingClientRect();
  element.style.left = `${Math.min(x, window.innerWidth - r.width - 8)}px`;
  element.style.top = `${above ? Math.max(8, y - r.height) : Math.min(y, window.innerHeight - r.height - 8)}px`;
}
document.addEventListener("pointerdown", (e) => {
  if (!(e.target as HTMLElement).closest(".cvs-menu")) closeFloating();
});

function menu(x: number, y: number, entries: MenuEntry[]): void {
  const element = h("div", { class: "cvs-menu", role: "menu" });
  for (const item of entries) {
    const row = h(
      "button",
      { type: "button", role: item.checked === undefined ? "menuitem" : "menuitemcheckbox", class: "cvs-menu-item", disabled: item.disabled, "aria-checked": item.checked === undefined ? undefined : String(item.checked) },
      h("span", { class: "cvs-check" }, item.checked ? "✓" : ""),
      h("span", {}, item.label),
      item.sub ? h("span", { class: "cvs-sub" }, "▸") : null,
    );
    row.addEventListener("click", () => {
      if (item.sub) {
        const r = row.getBoundingClientRect();
        item.sub(r.right, r.top);
        return;
      }
      closeFloating();
      item.run?.();
    });
    if (item.sub) row.addEventListener("mouseenter", () => row.click());
    element.append(row);
  }
  floating(element, x, y);
}

function nodeMenu(node: Node, e: MouseEvent): void {
  if (!editable()) return;
  if (node.kind === "container") {
    const p = node.props!;
    menu(e.clientX, e.clientY, [
      { label: "Insert widget", sub: (x, y) => widgetMenu(x, y, (name) => void insert(name, node.id), true) },
      { label: "Insert container", run: () => void send("add_container", { page, parent: node.id, w: Math.min(200, node.w), h: Math.min(120, node.h) }) },
      { label: "Scrollable", checked: p.scrollable, run: () => void send("set_container", { id: node.id, props: { scrollable: !p.scrollable } }) },
      { label: "Resizable by viewers", checked: p.resizable, run: () => void send("set_container", { id: node.id, props: { resizable: !p.resizable } }) },
      { label: "Delete", run: () => void send("delete", { id: node.id }) },
    ]);
    return;
  }
  menu(e.clientX, e.clientY, [
    { label: "Edit widget", run: () => openWidgets(node.widget) },
    { label: "Replace widget", sub: (x, y) => widgetMenu(x, y, (name) => void send("replace_widget", { id: node.id, widget: name }), true) },
    { label: "Delete", run: () => void send("delete", { id: node.id }) },
  ]);
}

/** Every widget of the framework, grouped, with search: `pick` takes one. */
function widgetMenu(x: number, y: number, pick: (name: string) => void, keep = false): void {
  const search = h("input", { type: "search", class: "cvs-menu-search", placeholder: "Search widgets", "aria-label": "Search widgets", "data-no-variables": "" });
  const list = h("div", { class: "cvs-menu-list", role: "menu" });
  const draw = (): void => {
    const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
    clear(list);
    let group = "";
    for (const w of grouped().filter((x2) => words.every((word) => `${x2.name} ${x2.description} ${x2.group}`.toLowerCase().includes(word)))) {
      const heading = w.prebuilt ? w.group : "Your widgets";
      if (heading !== group) {
        group = heading;
        list.append(h("div", { class: "cvs-menu-group" }, heading));
      }
      list.append(
        h(
          "button",
          {
            type: "button",
            role: "menuitem",
            class: "cvs-menu-item",
            "data-widget": w.name,
            title: w.description,
            onclick: () => {
              closeFloating();
              pick(w.name);
            },
          },
          h("span", { class: "cvs-check" }),
          h("span", {}, w.name),
        ),
      );
    }
  };
  search.addEventListener("input", draw);
  draw();
  const element = h("div", { class: "cvs-menu cvs-widget-menu", role: "dialog", "aria-label": "Insert widget" }, search, list);
  if (keep) {
    for (const f of floatingOpen.filter((f2) => f2.classList.contains("cvs-widget-menu"))) f.remove();
    floatingOpen = floatingOpen.filter((f2) => !f2.classList.contains("cvs-widget-menu"));
  }
  floating(element, x, y, false, keep);
  search.focus();
}

// ===== the Widgets pane =====

const DRAG = "application/x-sab-widget";
let galleryFocus: string | null = null;
let galleryQuery = "";
const previews = new Map<string, { state: string; url?: string; said?: string }>();

const grouped = (): WidgetEntry[] => [...widgets].sort((a, b) => Number(a.prebuilt) - Number(b.prebuilt) || a.group.localeCompare(b.group) || a.name.localeCompare(b.name));

/** A widget's rendered preview: the picture when it is made, a placeholder until then, its mark when it failed. */
function preview(name: string, className: string): HTMLElement {
  const holder = h("div", { class: `${className} cvs-preview`, "data-preview": name });
  const show = (): void => {
    const p = previews.get(name);
    if (p?.state === "ready" && p.url) clear(holder, h("img", { src: p.url, alt: `${name}, rendered`, draggable: "false" }));
    else if (p?.state === "failed") clear(holder, h("div", { class: "cvs-preview-failed", title: p.said ?? "" }, icon("warning"), "Did not render"));
    else clear(holder, h("div", { class: "cvs-preview-wait" }, name));
  };
  show();
  void ask(name).then(show);
  return holder;
}

const asking = new Map<string, Promise<void>>();
function ask(name: string): Promise<void> {
  const known = previews.get(name);
  if (known && known.state !== "coming") return Promise.resolve();
  const running = asking.get(name);
  if (running) return running;
  const made = (async () => {
    const theme = effectiveTheme().includes("dark") ? "dark" : "light";
    for (let tries = 0; tries < 90; tries++) {
      try {
        const said = await api<{ state: string; url?: string; said?: string }>(`/streamlit/widgets/${encodeURIComponent(name)}/preview?theme=${theme}`);
        previews.set(name, said);
        if (said.state !== "coming") break;
      } catch {
        previews.set(name, { state: "failed", said: "The preview could not be asked for." });
        break;
      }
      await new Promise((r) => window.setTimeout(r, 2000));
    }
    for (const holder of document.querySelectorAll<HTMLElement>(`[data-preview="${CSS.escape(name)}"]`)) {
      const p = previews.get(name);
      if (p?.state === "ready" && p.url) clear(holder, h("img", { src: p.url, alt: `${name}, rendered`, draggable: "false" }));
      else if (p?.state === "failed") clear(holder, h("div", { class: "cvs-preview-failed", title: p.said ?? "" }, icon("warning"), "Did not render"));
    }
  })().finally(() => asking.delete(name));
  asking.set(name, made);
  return made;
}

let hoverTimer: number | null = null;
let bigPreview: HTMLElement | null = null;
function hidePreview(): void {
  if (hoverTimer !== null) window.clearTimeout(hoverTimer);
  hoverTimer = null;
  bigPreview?.remove();
  bigPreview = null;
}

function drawGallery(): void {
  const search = h("input", { type: "search", class: "cvs-gallery-search", placeholder: "Search widgets", value: galleryQuery, "aria-label": "Search widgets", "data-no-variables": "" });
  const cards = h("div", { class: "cvs-cards" });
  const draw = (): void => {
    const words = galleryQuery.toLowerCase().split(/\s+/).filter(Boolean);
    clear(cards);
    let group = "";
    for (const w of grouped().filter((x) => words.every((word) => `${x.name} ${x.description} ${x.group} ${x.tags.join(" ")}`.toLowerCase().includes(word)))) {
      const heading = w.prebuilt ? w.group : "Your widgets";
      if (heading !== group) {
        group = heading;
        cards.append(h("div", { class: "cvs-gallery-group" }, heading));
      }
      const card = h(
        "div",
        { class: `cvs-card${galleryFocus === w.name ? " focused" : ""}`, draggable: "true", tabindex: "0", role: "button", "data-widget": w.name, "aria-label": `${w.name}: ${w.description}` },
        preview(w.name, "cvs-card-preview"),
        h("div", { class: "cvs-card-name" }, w.name),
        h("div", { class: "cvs-card-desc" }, w.description),
      );
      card.addEventListener("dragstart", (e) => {
        hidePreview();
        e.dataTransfer?.setData(DRAG, w.name);
        e.dataTransfer?.setData("text/plain", w.name);
      });
      card.addEventListener("focus", () => {
        galleryFocus = w.name;
        for (const c of cards.querySelectorAll(".cvs-card")) c.classList.toggle("focused", c === card);
      });
      card.addEventListener("click", () => card.focus());
      card.addEventListener("dblclick", () => {
        if (editable()) void insert(w.name, selectedContainer());
      });
      card.addEventListener("keydown", (e) => {
        if ((e.key === "Insert" || e.key === "Enter") && editable()) {
          e.preventDefault();
          e.stopPropagation();
          void insert(w.name, selectedContainer());
        }
      });
      card.addEventListener("mouseenter", () => {
        hidePreview();
        hoverTimer = window.setTimeout(() => {
          const r = card.getBoundingClientRect();
          bigPreview = h("div", { class: "cvs-big-preview", role: "tooltip" }, preview(w.name, "cvs-big-image"), h("div", { class: "cvs-card-name" }, w.name), h("div", { class: "cvs-card-desc" }, w.description));
          document.body.append(bigPreview);
          const width = 496;
          bigPreview.style.left = `${Math.max(8, r.left - width - 12)}px`;
          bigPreview.style.top = `${Math.max(8, Math.min(r.top, window.innerHeight - bigPreview.getBoundingClientRect().height - 8))}px`;
        }, 400);
      });
      card.addEventListener("mouseleave", hidePreview);
      cards.append(card);
    }
  };
  search.addEventListener("input", () => {
    galleryQuery = search.value;
    draw();
  });
  draw();
  clear(galleryPane, h("div", { class: "cvs-pane-head" }, h("h2", {}, "Widgets"), button("Open the Widgets window", () => openWidgets(), { icon: "popout", iconOnly: true, class: "ghost" })), search, cards);
}

// ===== the Properties pane =====

function section(title: string, ...children: (HTMLElement | null)[]): HTMLElement {
  return h("section", { class: "cvs-props-section" }, h("h3", {}, title), ...children);
}

function sizeFields(node: Node): HTMLElement {
  const boxes = (["x", "y", "w", "h"] as const).map((key) => {
    const input = h("input", { type: "number", class: "cvs-num", value: String(node[key]), min: key === "w" || key === "h" ? 1 : 0, "aria-label": { x: "Left", y: "Top", w: "Width", h: "Height" }[key], disabled: !editable() });
    input.addEventListener("change", () => {
      const v = Math.round(Number(input.value));
      if (Number.isFinite(v)) void send("move", { id: node.id, [key]: v });
    });
    return h("label", { class: "cvs-field" }, h("span", {}, { x: "X", y: "Y", w: "W", h: "H" }[key]), input);
  });
  return h("div", { class: "cvs-size" }, ...boxes, h("span", { class: "cvs-px" }, "px"));
}

function containerFields(node: Node): HTMLElement[] {
  const p = node.props!;
  const set = (props: Partial<ContainerProps>): void => void send("set_container", { id: node.id, props });
  const flag = (label: string, key: "border" | "scrollable" | "resizable"): HTMLElement => {
    const input = h("input", { type: "checkbox", role: "switch", class: "wg-switch", checked: p[key], disabled: !editable(), "aria-label": label, "data-prop": key });
    input.addEventListener("change", () => set({ [key]: input.checked }));
    return h("label", { class: "cvs-flag" }, input, h("span", {}, label));
  };
  const title = h("input", { class: "wg-input", value: p.title, "aria-label": "Title", disabled: !editable(), "data-no-variables": "" });
  title.addEventListener("change", () => set({ title: title.value }));
  const height = h("select", { class: "wg-input", "aria-label": "Height", disabled: !editable() }, h("option", { value: "fit", selected: p.height === "fit" }, "Fit"), h("option", { value: "fixed", selected: p.height === "fixed" }, "Fixed"));
  height.addEventListener("change", () => set({ height: height.value as ContainerProps["height"] }));
  const background = h("input", { type: "text", class: "wg-input", value: p.background, placeholder: "none", "aria-label": "Background", disabled: !editable(), "data-no-variables": "" });
  background.addEventListener("change", () => set({ background: background.value.trim() }));
  return [
    h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, "Title"), title),
    flag("Border", "border"),
    flag("Scrollable", "scrollable"),
    flag("Resizable", "resizable"),
    h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, "Height"), height),
    numberBox("Padding", p.padding, 0, 64, (v) => set({ padding: v })),
    numberBox("Columns inside", p.columns, 1, 48, (v) => set({ columns: v })),
    h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, "Background"), background),
    h("div", { class: "wg-label" }, "Size"),
    sizeFields(node),
  ];
}

function drawProps(): void {
  if (!state) return;
  clear(propsPane, h("div", { class: "cvs-pane-head" }, h("h2", {}, "Properties")));
  const nodes = selected.map((id) => find(id)).filter((x): x is { node: Node; parent: Node | null } => x !== null);
  if (!nodes.length) {
    propsPane.append(h("p", { class: "cvs-props-none" }, "Select a container or a widget."));
    return;
  }
  const first = nodes[0]!.node;
  const same = nodes.every((n) => n.node.kind === first.kind && n.node.widget === first.widget);
  if (!same) {
    propsPane.append(h("p", { class: "cvs-props-none" }, `${nodes.length} selected: they share no properties.`));
    return;
  }
  if (first.kind === "container") {
    propsPane.append(section(nodes.length > 1 ? `CONTAINERS (${nodes.length})` : "CONTAINER", ...containerFields(first)));
    return;
  }
  const known = entry(first.widget ?? "");
  propsPane.append(
    section(
      "WIDGET",
      h("div", { class: "cvs-widget-line" }, h("span", { class: "cvs-widget-title" }, first.widget ?? ""), button("Edit widget", () => openWidgets(first.widget), { class: "ghost cvs-edit-widget" })),
      known ? h("div", { class: "wg-prop-help" }, known.description) : h("div", { class: "wg-field-line" }, "This widget is not in the library any more."),
    ),
  );
  if (known) {
    const marks = state.marks[first.id] ?? {};
    const values: Record<string, unknown> = { ...Object.fromEntries(known.properties.map((p) => [p.name, p.default])), ...(first.values ?? {}) };
    const fields = known.properties.map((prop: Prop) =>
      propertyField(
        prop,
        values,
        context,
        !editable(),
        async (value, said) => {
          const checked = await api<{ ok: boolean; said?: string; fix?: string }>("/streamlit/widgets/check-value", "POST", { name: known.name, property: prop.name, value, values });
          if (!checked.ok) return said(`${checked.said ?? ""} ${checked.fix ?? ""}`.trim());
          said("");
          for (const n of nodes) await send("set_values", { id: n.node.id, values: { [prop.name]: value } });
        },
        { marked: marks[prop.name] ?? null, overridden: nodes.length === 1 && Object.hasOwn(first.values ?? {}, prop.name), onReset: () => void send("set_values", { id: first.id, values: { [prop.name]: null } }) },
      ),
    );
    propsPane.append(section("PROPERTIES", ...fields));
  }
  if (nodes.length === 1) propsPane.append(section("SIZE", sizeFields(first)));
}

// ===== Play, Launch, Export =====

async function play(): Promise<void> {
  if (!state) return;
  const go = bottom.querySelector<HTMLButtonElement>(".cvs-play")!;
  await busyButton(go, async () => {
    try {
      const said = await api<{ ok: boolean; url?: string; problem?: { message?: string; command?: string } }>(`/streamlit/canvases/${state!.canvas}/play`, "POST", { page });
      if (!said.ok || !said.url) return void showError(notice, new Error(said.problem?.message ?? `Streamlit is not in this Python${said.problem?.command ? `: ${said.problem.command}` : ""}.`));
      clearError(notice);
      clear(live, h("div", { class: "cvs-live-bar" }, h("span", {}, "Playing"), button("Edit", () => stopPlay(), { icon: "edit", class: "ghost cvs-edit" })), h("iframe", { class: "cvs-live-frame", src: said.url, title: "The page, playing" }));
      live.hidden = false;
      viewport.hidden = true;
    } catch (e) {
      errorHere(e, {}, go);
    }
  });
}

function stopPlay(): void {
  live.hidden = true;
  viewport.hidden = false;
  clear(live);
  if (state) void api(`/streamlit/canvases/${state.canvas}/stop`, "POST", {}).catch(() => undefined);
}

async function launch(): Promise<void> {
  if (!state) return;
  const go = bottom.querySelector<HTMLButtonElement>(".cvs-launch")!;
  const opened = window.open("about:blank", `sab-launch-${state.canvas}`, "popup,width=1300,height=860");
  await busyButton(go, async () => {
    try {
      const said = await api<{ ok: boolean; url?: string; title?: string; problem?: { message?: string } }>(`/streamlit/canvases/${state!.canvas}/launch`, "POST", {});
      if (!said.ok || !said.url) {
        opened?.close();
        return void errorHere(new Error(said.problem?.message ?? "The app did not start."), {}, go);
      }
      if (opened) opened.location.href = said.url;
      else errorHere("The browser blocked the new window: allow pop-ups for this address.", {}, go);
      toast(`${said.title ?? "The app"} launched.`);
    } catch (e) {
      opened?.close();
      errorHere(e, {}, go);
    }
  });
}

async function exportApp(): Promise<void> {
  if (!state) return;
  const go = bottom.querySelector<HTMLButtonElement>(".cvs-export")!;
  const folder = await chooseFile({ title: "Export the app into", mode: "folder", start: state.path.replace(/[\\/][^\\/]*$/, "") });
  if (!folder) return;
  await busyButton(go, async () => {
    try {
      const done = await api<{ folder: string; files: string[] }>(`/streamlit/canvases/${state!.canvas}/export`, "POST", { folder });
      toast(`Exported: ${done.files.length} files in ${done.folder}`);
    } catch (e) {
      errorHere(e, {}, go);
    }
  });
}

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
        () => {
          const name = prompt("The new canvas's name", "App");
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
  if (!(await requireSession())) return;
  mountNav("canvas");
  mountNavRail("canvas");
  startNav();
  const path = params.get("path");
  if (!path) return void landing().catch((e) => errorHere(e, {}, root));
  layout();
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
    if (said.type === "canvas_changed" && state && said.canvas === state.canvas && said.window !== WINDOW) {
      void reload().then(() => say("The canvas changed in another window: it is shown as it is now."));
    }
    if (said.type === "widgets_changed") {
      void api<{ widgets: WidgetEntry[] }>("/streamlit/widgets").then((l) => {
        widgets = l.widgets;
        previews.clear();
        drawGallery();
        void reload();
      });
    }
  });
}

void start();
