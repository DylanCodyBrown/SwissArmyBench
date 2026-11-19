/**
 * canvasPane.ts: the canvas's property pane (the owner, 2026-11-19: "a property pane for everything on the
 * app canvas, and ways to see all things related to the canvas"): WinForms' Properties window for a Streamlit
 * app's canvas. One pane for whatever is selected: a block, a page, or the app. [WIRE]
 *
 *   [GRID]       the selected block's properties as a grid: its own (name, place, size, lock, hide), then each
 *                Streamlit element its cell calls with every property Streamlit gives it. Categorized or A to Z,
 *                a search box, the focused property's one line at the foot. A property is a plain value (edited
 *                here), a binding (to a name, a session state key, a variable: shown as what it is), or code
 *                (read-only, Go to cell). Right-click: Reset to default, Bind to…, Go to cell
 *   [USES]       what it depends on, each a link: tables (opened beside the canvas: columns, steps in words,
 *                first rows, Open as grid), variables (the Variables page), connections (their cards), the
 *                cells that make the names it reads (Go to cell), what it is used by, a line of its lineage
 *   [STREAMLIT]  State: each widget's key, its value Now (the running app only: Play first) and its Default
 *                (written into the cell's code). Cache: each function st.cache_data or st.cache_resource
 *                decorates: ttl, max_entries, show_spinner, persist written into the decorator; Cache this
 *                function; Clear this cache (Now)
 *   [EVENTS]     a widget's on_change or on_click: Add handler writes the function's stub into the cell and
 *                goes to it
 *   [CODE]       the exact code the page runs for the block, read-only, with Go to cell
 *
 * WRITING BACK: the server answers a change with a plan (the cell's code before and after: only the
 * characters named change); the window makes it in the open document like typing, so the editor's Undo
 * (and the canvas's) takes it back. Code that is not a plain value is refused there, in words.
 *
 * ROUTING: GET /streamlit/apps/{app}/inspect, GET /streamlit/tables/{name},
 *          POST …/blocks/{block}/code, POST /streamlit/apps/{app}/now (routes_canvas.py)
 */
import { api } from "./api";
import { button, clear, h, icon, showMenu, type MenuItem } from "./dom";
import { errorHere, showError } from "./errorNote";
import { kindIcon, kindOfPath } from "./kindColours";
import { busy, busyButton, loadingBlock } from "./loading";
import type { CanvasView } from "./workbenchCanvas";
import { type BlockState, type Controller, controllerOf, type SessionRow, shownValue } from "./workbenchStreamlit";

/** A change to a cell's code, as the server planned it. */
export interface CodePlan {
  app: string;
  document: string;
  cell: number;
  where: string;
  do: string;
  before: string;
  code: string;
  changed: boolean;
  edits: { start: number; end: number; text: string }[];
  line: number | null;
  handler: string | null;
}

export interface PaneHost {
  goToCell: (document: string, cell: number, line?: number | null) => void;
  renameCell: (document: string, cell: number, name: string) => Promise<void>;
  lineage?: (block: string) => void;
  /** Make a plan's change in the open document (like typing: undoable). False: it could not be made. */
  applyCode: (plan: CodePlan) => Promise<boolean>;
  openVariable: (name: string) => void;
  openConnection: (name: string) => void;
  openGrid: (grid: string) => void;
  /** The page settings' form (the app, nothing selected). */
  drawSettings: (body: HTMLElement) => void;
}

interface Value {
  kind: "literal" | "name" | "state" | "variable" | "expression";
  source: string;
  value: unknown;
  target: string | null;
  form: string;
}

interface Param {
  name: string;
  type: "text" | "number" | "bool" | "choice" | "list" | "any";
  default: unknown;
  words: string;
  category: string;
  choices: string[];
}

interface Widget {
  index: number;
  call: string;
  title: string;
  line: number;
  target: string | null;
  widget: boolean;
  label: string | null;
  key: string | null;
  state_key: string | null;
  arguments: Record<string, Value>;
  default: string | null;
  event: string | null;
  events: Record<string, { handler: string | null; source: string }>;
  params: Param[];
  held: boolean;
  now: unknown;
  spread: boolean;
}

interface CacheRow {
  name: string;
  line: number;
  cache: "data" | "resource" | null;
  settings: Record<string, Value>;
  document: string;
  cell: number;
  where: string;
  own: boolean;
}

interface Uses {
  tables: { name: string; dataset: string; grid: string; rows: number; columns: number; steps: number }[];
  variables: { name: string; defined: boolean; set: boolean; source?: string; value?: unknown; secret?: boolean }[];
  connections: string[];
  cells: { name: string; document: string | null; cell: number | null; where: string; title?: string; block: string | null }[];
  used_by: { names: string[]; block: string; page: string; page_name: string; title: string; where: string }[];
  lineage: { kind: string; label: string; where: string | null; document: string | null; cell: number | null; target: boolean }[];
}

export interface Inspected {
  app: string;
  running: boolean;
  target: "app" | "page" | "block";
  page?: { id: string; name: string };
  block?: { id: string; name: string | null; named: boolean; kind: string | null; document: string; cell: number; where: string; missing: string | null };
  blocks?: { id: string; name: string | null; where: string }[];
  tables?: string[];
  problem?: string | null;
  editable?: boolean;
  makes?: string[];
  widgets?: Widget[];
  uses?: Uses;
  cache?: CacheRow[];
  code?: string;
}

interface TablePreview {
  name: string;
  dataset: string;
  grid: string;
  rows: number;
  columns: { name: string; type: string }[];
  steps: string[];
  head: unknown[][];
}

const ROLES: Record<Controller["role"], string> = { filter: "Filter", action: "Action", view: "View", "": "Model work" };
const CATEGORIES = ["Design", "Appearance", "Data", "Behaviour", "Layout", "State", "Other"];
const BIND_WORDS: Record<string, string> = { name: "a name", state: "session state", variable: "a variable", expression: "an expression" };
const CACHE_WORDS: Record<string, string> = {
  ttl: "How long a result is kept: seconds, or words like 1h. Empty: for ever.",
  max_entries: "The most results kept; the oldest goes first. Empty: no limit.",
  show_spinner: "A turning mark while the function runs.",
  persist: "Keep the results on disk, across restarts (st.cache_data only).",
};

const chip = (name: string): HTMLElement => h("span", { class: "app-chip mono" }, name);

/** What is typed for a property, as the value it means: JSON when it is JSON, else the text itself. */
export function typedValue(text: string, type: Param["type"]): unknown {
  const typed = text.trim();
  if (type === "text") return text;
  if (type === "number") {
    if (typed === "") return null;
    const n = Number(typed);
    if (Number.isNaN(n)) throw new Error("That is not a number.");
    return n;
  }
  if (type === "list") {
    if (typed === "") return [];
    if (typed.startsWith("[")) return JSON.parse(typed) as unknown;
    // Words between commas: numbers stay numbers.
    return typed.split(",").map((part) => (part.trim() !== "" && !Number.isNaN(Number(part)) ? Number(part) : part.trim()));
  }
  if (typed === "") return null;
  try {
    return JSON.parse(typed) as unknown;
  } catch {
    return text;
  }
}

/** A plain value as its box shows it. */
export function shownText(value: unknown, type: Param["type"]): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return type === "any" && value !== "" && (/^[\d\-[{"]/.test(value) || ["true", "false", "null"].includes(value)) ? JSON.stringify(value) : value;
  if (Array.isArray(value) && type === "list" && value.every((v) => typeof v === "string" || typeof v === "number") && !value.some((v) => typeof v === "string" && (v.includes(",") || v.trim() !== v || v === "" || !Number.isNaN(Number(v))))) return value.join(", ");
  return JSON.stringify(value);
}

export interface PaneView {
  /** Draw it into the Properties panel's body. */
  draw: (body: HTMLElement) => void;
  /** The selection or the app changed: read again. */
  refresh: () => void;
  /** What it last read (for the agent's canvas.properties). */
  shown: () => Inspected | null;
  /** The live page's state, when known. */
  setRows: (rows: SessionRow[]) => void;
}

export function canvasPane(canvas: () => CanvasView, host: PaneHost): PaneView {
  let body: HTMLElement | null = null;
  let seen: Inspected | null = null;
  let asked = 0;
  let key = "";
  let sort: "category" | "name" = "category";
  let filter = "";
  let widgetAt = 0;
  let table: TablePreview | null = null;
  let rows: SessionRow[] = [];
  const open: Record<string, boolean> = { properties: true, uses: true, streamlit: true, events: true, code: false };
  const words = h("div", { class: "cp-words hint", role: "status" });

  const selection = (): { page: string | null; block: string | null } => {
    const c = canvas();
    return { page: c.page()?.id ?? null, block: c.selected()?.id ?? null };
  };

  async function read(own = false): Promise<void> {
    const c = canvas();
    const app = c.app();
    if (!app) return;
    const { page, block } = selection();
    const mine = ++asked;
    const query = new URLSearchParams({ ...(page ? { page } : {}), ...(block ? { block } : {}) }).toString();
    const now = `${app}|${page}|${block}`;
    const work = api<Inspected>(`/streamlit/apps/${encodeURIComponent(app)}/inspect${query ? `?${query}` : ""}`);
    try {
      // A new selection is gated while it is read (8.12); the same one read again draws over itself.
      const next = body && now !== key ? await busy(body, "Reading its properties…", work, { errorIn: false }) : await work;
      if (mine !== asked) return;
      if (now !== key) {
        table = null;
        widgetAt = 0;
      }
      const same = now === key;
      key = now;
      seen = next;
      // A box being typed in is not drawn over by a refresh from elsewhere (only by its own change).
      const typing = !!body && body.contains(document.activeElement) && document.activeElement !== body;
      if (same && typing && !own) return;
      const held = typing ? (document.activeElement as HTMLElement).closest<HTMLElement>("[data-property], [data-event], .cp-state, .cp-cache") : null;
      const at = held ? [held.dataset.property, (document.activeElement as HTMLElement).dataset.field, held.dataset.widget, held.dataset.function] : null;
      render();
      if (at && same) {
        const again = [...(body?.querySelectorAll<HTMLElement>("input, select") ?? [])].find((el) => {
          const row = el.closest<HTMLElement>("[data-property], [data-event], .cp-state, .cp-cache");
          return !!row && row.dataset.property === at[0] && el.dataset.field === at[1] && row.dataset.widget === at[2] && row.dataset.function === at[3];
        });
        again?.focus();
      }
    } catch (e) {
      if (mine !== asked || !body) return;
      seen = null;
      showError(body, e);
    }
  }

  // ===== writing back: a plan from the server, made in the open document =====

  async function change(blockId: string, request: Record<string, unknown>, from?: HTMLElement): Promise<CodePlan | null> {
    const c = canvas();
    const page = c.page();
    if (!page || !c.app()) return null;
    try {
      const plan = await api<CodePlan>(`/streamlit/apps/${encodeURIComponent(c.app()!)}/pages/${encodeURIComponent(page.id)}/blocks/${encodeURIComponent(blockId)}/code`, "POST", request);
      if (plan.changed && !(await host.applyCode(plan))) return null;
      await read(true);
      return plan;
    } catch (e) {
      errorHere(e, {}, from ?? body);
      void read(true); // the box goes back to what the code says
      return null;
    }
  }

  async function now(request: Record<string, unknown>, from: HTMLElement): Promise<boolean> {
    const app = canvas().app();
    if (!app) return false;
    try {
      await api(`/streamlit/apps/${encodeURIComponent(app)}/now`, "POST", request);
      return true;
    } catch (e) {
      errorHere(e, {}, from);
      return false;
    }
  }

  // ===== the property grid =====

  interface Row {
    name: string;
    category: string;
    words: string;
    editor: HTMLElement;
    menu?: () => MenuItem[];
    set: boolean;
  }

  function describe(text: string): void {
    words.textContent = text;
  }

  function gridRow(row: Row): HTMLElement {
    const line = h(
      "div",
      { class: `cp-row${row.set ? " set" : ""}`, role: "row", dataset: { property: row.name }, title: row.words },
      h("span", { class: "cp-name", role: "rowheader" }, row.name),
      h("span", { class: "cp-value", role: "cell" }, row.editor),
    );
    line.addEventListener("focusin", () => describe(row.words));
    line.addEventListener("mouseenter", () => describe(row.words));
    if (row.menu) {
      line.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        showMenu(e.clientX, e.clientY, row.name, row.menu!());
      });
    }
    return line;
  }

  /** An input that commits on change and on Enter; Escape puts back what the code says. */
  function box(value: string, label: string, commit: (typed: string, input: HTMLInputElement) => void, more: Record<string, unknown> = {}): HTMLInputElement {
    const input = h("input", { type: "text", class: "app-input cp-input", value, "aria-label": label, ...more }) as HTMLInputElement;
    input.addEventListener("change", () => commit(input.value, input));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") input.blur();
      if (e.key === "Escape") {
        input.value = value;
        input.blur();
      }
      e.stopPropagation();
    });
    return input;
  }

  function bindForm(blockId: string, widget: Widget, name: string, kind: string, anchor: HTMLElement): void {
    const prompts: Record<string, string> = { name: "The name (another cell's, or a widget's value)", state: "The session state key", variable: "The variable's name", expression: "A short Python expression" };
    const now = widget.arguments[name];
    const start = now && now.kind === kind ? (now.target ?? now.source) : kind === "expression" && now ? now.source : "";
    const input = box(start, prompts[kind] ?? "", (typed) => {
      form.remove();
      if (typed.trim()) void change(blockId, { do: "bind", widget: widget.index, name, kind, target: typed.trim() }, anchor);
    }, { placeholder: prompts[kind] ?? "", class: "app-input cp-input mono" });
    const form = h("div", { class: "cp-bind", dataset: { bind: kind } }, h("span", { class: "hint" }, `Bind ${name} to ${BIND_WORDS[kind]}`), input);
    anchor.after(form);
    input.focus();
  }

  function widgetRows(blockId: string, widget: Widget, editable: boolean, where: { document: string; cell: number }): Row[] {
    const known = new Map(widget.params.map((p) => [p.name, p]));
    const names = [...widget.params.map((p) => p.name), ...Object.keys(widget.arguments).filter((n) => !known.has(n) && !n.startsWith("on_"))];
    return names.map((name): Row => {
      const param: Param = known.get(name) ?? { name, type: "any", default: null, words: `${name}: as written in the cell.`, category: "Other", choices: [] };
      const value = widget.arguments[name] as Value | undefined;
      const send = (typed: unknown, from: HTMLElement): void => void change(blockId, { do: "set", widget: widget.index, name, value: typed }, from);
      let editor: HTMLElement;
      if (value && value.kind !== "literal") {
        // A binding (or code): shown as what it is. Code is read-only here, with Go to cell.
        const said = value.kind === "expression" ? "code" : `bound to ${BIND_WORDS[value.kind]}`;
        editor = h(
          "span",
          { class: `cp-bound cp-${value.kind}`, title: said, dataset: { kind: value.kind } },
          icon(value.kind === "expression" ? "code" : "link"),
          h("code", { class: "mono" }, value.source),
          value.kind === "expression" ? button("Go to cell", () => host.goToCell(where.document, where.cell, widget.line), { icon: "forward", iconOnly: true, class: "ghost" }) : null,
        );
      } else if (!editable) {
        editor = h("span", { class: "mono" }, value ? value.source : "");
      } else if (param.type === "bool") {
        const tick = h("input", { type: "checkbox", "aria-label": name, checked: value ? value.value === true : param.default === true }) as HTMLInputElement;
        tick.addEventListener("change", () => send(tick.checked, tick));
        editor = tick;
      } else if (param.type === "choice") {
        const current = value ? String(value.value) : String(param.default ?? "");
        const select = h("select", { class: "app-input cp-input", "aria-label": name }, ...[...new Set([...param.choices, current])].map((c) => h("option", { value: c, selected: c === current }, c))) as HTMLSelectElement;
        select.addEventListener("change", () => send(select.value === "None" ? null : select.value, select));
        editor = select;
      } else {
        const shown = value ? shownText(value.value, param.type) : "";
        const placeholder = param.default === null || param.default === undefined ? "" : shownText(param.default, param.type);
        editor = box(shown, name, (typed, input) => {
          if (typed === shown) return;
          // An emptied box takes the property out of the call (Streamlit's own default again).
          if (typed.trim() === "" && value && param.type !== "text") return void change(blockId, { do: "reset", widget: widget.index, name }, input);
          try {
            send(value?.form === "date" ? typed.trim() : typedValue(typed, param.type), input);
          } catch (e) {
            errorHere(e, {}, input);
          }
        }, { placeholder, inputmode: param.type === "number" ? "decimal" : undefined });
      }
      const menu = (): MenuItem[] => {
        const anchor = body?.querySelector<HTMLElement>(`.cp-row[data-property="${CSS.escape(name)}"]`) ?? editor;
        const locked = !editable ? "The cell is not whole Python yet" : undefined;
        const code = value?.kind === "expression" ? "It is code: change it in its cell" : locked;
        return [
          ["reset", "Reset to default", () => void change(blockId, { do: "reset", widget: widget.index, name }, anchor), !value ? "It is at its default" : locked],
          "-",
          ...(["name", "state", "variable", "expression"] as const).map((kind): MenuItem => ["link", `Bind to ${BIND_WORDS[kind]}…`, () => bindForm(blockId, widget, name, kind, anchor), kind === "expression" ? locked : code]),
          "-",
          ["forward", "Go to cell", () => host.goToCell(where.document, where.cell, widget.line)],
        ];
      };
      return { name, category: param.category, words: param.words, editor, menu, set: !!value };
    });
  }

  function designRows(block: BlockState, seenBlock: NonNullable<Inspected["block"]>): Row[] {
    const c = canvas();
    const number = (name: string, value: number | null, min: number, max: number, send: (n: number | null) => void, empty = ""): HTMLInputElement =>
      box(value === null ? "" : String(value), name, (typed, input) => {
        const n = typed.trim() === "" ? null : Math.round(Number(typed));
        if (n !== null && (Number.isNaN(n) || n < min || n > max)) return void errorHere(`${name} is ${min} to ${max}.`, {}, input);
        send(n);
      }, { inputmode: "numeric", placeholder: empty, dataset: { field: name.toLowerCase() } });
    const name = box(block.name ?? "", "Name", (typed, input) => {
      if (typed.trim() !== (block.name ?? "")) void host.renameCell(block.document, block.cell, typed.trim()).catch((e: Error) => errorHere(e, {}, input));
    }, { maxlength: 80, dataset: { field: "name" } });
    const kind = kindOfPath(block.document) ?? "notebook";
    const source = h("button", { type: "button", class: `link app-source km-${kind}`, title: block.document, onclick: () => host.goToCell(block.document, block.cell) }, icon(kindIcon(kind, block.document)), h("span", { class: "mono" }, seenBlock.where));
    return [
      { name: "Name", category: "Design", words: "The block's name: its cell's own, renamed in its document.", editor: name, set: true },
      { name: "Cell", category: "Design", words: "The cell this block links to. A click goes there.", editor: source, set: true },
      ...(seen?.makes?.length ? [{ name: "Makes", category: "Design", words: "The names its cell makes: other blocks read them.", editor: h("span", { class: "app-chips" }, ...seen.makes.filter((m) => !m.startsWith("_")).map(chip)), set: true }] : []),
      { name: "Row", category: "Layout", words: "Its row on the page, from 1.", editor: number("Row", block.row, 1, 60, (n) => n && void c.changeBlock(block.id, { row: n, column: block.column })), set: true },
      { name: "Column", category: "Layout", words: "The column it starts in, 1 to 12.", editor: number("Column", block.column, 1, 12, (n) => n && void c.changeBlock(block.id, { row: block.row, column: n })), set: true },
      { name: "Width", category: "Layout", words: "How many of the page's 12 columns it takes.", editor: number("Width", block.w, 2, 12, (n) => n && void c.changeBlock(block.id, { w: n })), set: true },
      { name: "Height", category: "Layout", words: "Its height in rows of 40 pixels. Empty: as tall as what it draws.", editor: number("Height", block.h, 1, 30, (n) => void c.changeBlock(block.id, { h: n }), "Fits"), set: block.h !== null },
    ];
  }

  function grid(all: Row[]): HTMLElement {
    const shown = all.filter((r) => !filter || r.name.toLowerCase().includes(filter.toLowerCase()));
    if (!shown.length) return h("p", { class: "hint app-empty" }, filter ? `No property is called ${filter}` : "No properties");
    if (sort === "name") return h("div", { class: "cp-grid", role: "grid" }, ...[...shown].sort((a, b) => a.name.localeCompare(b.name)).map(gridRow));
    const groups = CATEGORIES.filter((c) => shown.some((r) => r.category === c));
    return h("div", { class: "cp-grid", role: "grid" }, ...groups.flatMap((c) => [h("div", { class: "cp-category", role: "presentation" }, c), ...shown.filter((r) => r.category === c).map(gridRow)]));
  }

  // ===== sections =====

  function section(id: string, title: string, count: number | null, ...children: (HTMLElement | null)[]): HTMLElement | null {
    const held = children.filter((c): c is HTMLElement => c !== null);
    if (!held.length) return null;
    const details = h("details", { class: `cp-section cp-${id}`, dataset: { section: id } }, h("summary", { class: "app-heading" }, title, count ? h("span", { class: "cp-count" }, String(count)) : null), ...held) as HTMLDetailsElement;
    details.open = open[id] ?? true;
    details.addEventListener("toggle", () => (open[id] = details.open));
    return details;
  }

  const list = (title: string, items: HTMLElement[]): HTMLElement | null =>
    items.length ? h("div", { class: "cp-list", dataset: { list: title.toLowerCase() } }, h("div", { class: "cp-list-title" }, title), h("ul", { class: title === "Used by" ? "app-feeds cp-items" : "cp-items" }, ...items.map((i) => h("li", {}, i)))) : null;

  const link = (ic: string, label: string, run: () => void, hint = ""): HTMLElement => h("button", { type: "button", class: "link cp-link", onclick: run }, icon(ic), h("span", {}, label), hint ? h("span", { class: "hint" }, hint) : null);

  async function showTable(name: string, from: HTMLElement): Promise<void> {
    try {
      table = await busyButton(from as HTMLButtonElement, api<TablePreview>(`/streamlit/tables/${encodeURIComponent(name)}`), "Reading…");
      render();
      body?.querySelector(".cp-table")?.scrollIntoView({ block: "nearest" });
    } catch (e) {
      errorHere(e, {}, from);
    }
  }

  function tablePreview(t: TablePreview): HTMLElement {
    return h(
      "div",
      { class: "cp-table", role: "region", "aria-label": t.name, dataset: { table: t.name } },
      h(
        "div",
        { class: "cp-table-head" },
        h("strong", { class: "mono" }, t.name),
        h("span", { class: "hint" }, `${t.rows.toLocaleString()} ${t.rows === 1 ? "row" : "rows"} · ${t.columns.length} columns`),
        h("span", { class: "spacer" }),
        button("Open as grid", () => host.openGrid(t.grid), { icon: "export", class: "ghost cp-open-grid" }),
        button(`Close ${t.name}`, () => {
          table = null;
          render();
        }, { icon: "close", iconOnly: true, class: "ghost" }),
      ),
      t.steps.length ? h("ol", { class: "cp-steps" }, ...t.steps.map((s) => h("li", {}, s))) : null,
      h(
        "div",
        { class: "cp-table-scroll", tabindex: 0 },
        h(
          "table",
          { class: "app-state cp-rows" },
          h("thead", {}, h("tr", {}, ...t.columns.map((c) => h("th", { title: c.type }, c.name, h("span", { class: "hint cp-type" }, c.type.toLowerCase()))))),
          h("tbody", {}, ...t.head.map((row) => h("tr", {}, ...row.map((v) => h("td", { class: "mono" }, v === null ? "" : String(v)))))),
        ),
      ),
    );
  }

  function usesSection(uses: Uses, blockId: string): HTMLElement | null {
    const c = canvas();
    const tables = uses.tables.map((t) => link("table", t.name, () => void 0, `${t.rows.toLocaleString()} rows${t.steps ? ` · ${t.steps} ${t.steps === 1 ? "step" : "steps"}` : ""}`));
    tables.forEach((el, i) => el.addEventListener("click", () => void showTable(uses.tables[i]!.name, el)));
    const variables = uses.variables.map((v) =>
      link("variables", v.name, () => host.openVariable(v.name), !v.defined && !v.set ? "not set on this computer" : v.secret || v.value === undefined ? (v.source ?? "set") : String(v.value)),
    );
    const connections = uses.connections.map((name) => {
      const el = link("plug", name, () => host.openConnection(name));
      el.dataset.connections = name;
      return el;
    });
    const cells = uses.cells.map((cell) => link("forward", cell.name, () => (cell.block ? c.select(cell.block) : cell.document && cell.cell ? host.goToCell(cell.document, cell.cell) : undefined), cell.where));
    const usedBy = uses.used_by.map((u) => link("forward", u.title, () => (u.page === c.page()?.id ? c.select(u.block) : c.showPage(u.page, u.block)), `${u.names.join(", ")}${u.page === c.page()?.id ? "" : ` · ${u.page_name}`}`));
    const path = uses.lineage.length > 1
      ? h(
          "div",
          { class: "cp-lineage", role: "list", "aria-label": "Lineage" },
          ...uses.lineage.flatMap((n, i) => [
            i ? h("span", { class: "cp-arrow", "aria-hidden": "true" }, "→") : null,
            h("span", { class: `app-chip cp-node cp-${n.kind}${n.target ? " target" : ""}`, role: "listitem", title: n.where ?? n.label }, n.target ? "this block" : n.label),
          ]),
          host.lineage ? button("Lineage…", () => host.lineage!(blockId), { icon: "lineage", class: "ghost app-lineage" }) : null,
        )
      : null;
    const count = tables.length + variables.length + connections.length + cells.length + usedBy.length;
    return section("uses", "Uses", count, list("Tables", tables), table ? tablePreview(table) : null, list("Variables", variables), list("Connections", connections), list("Cells", cells), list("Used by", usedBy), path);
  }

  function stateSection(blockId: string, widgets: Widget[], running: boolean): HTMLElement | null {
    const keyed = widgets.filter((w) => w.widget);
    if (!keyed.length) return null;
    return h(
      "div",
      { class: "cp-part", dataset: { part: "state" } },
      h("div", { class: "cp-list-title" }, "State"),
      ...keyed.map((w) => {
        const keyBox = box(w.key ?? "", "Key", (typed, input) => {
          if (typed.trim() === (w.key ?? "")) return;
          void change(blockId, typed.trim() ? { do: "set", widget: w.index, name: "key", value: typed.trim() } : { do: "reset", widget: w.index, name: "key" }, input);
        }, { placeholder: w.state_key ?? "", class: "app-input cp-input mono", dataset: { field: "key" } });
        const type: Param["type"] = "any";
        const nowBox = running
          ? box(w.held ? shownText(w.now, type) : "", "Now", (typed, input) => {
              if (!w.state_key) return;
              try {
                void now(typed.trim() === "" ? { key: w.state_key, forget: true } : { key: w.state_key, value: typedValue(typed, type) }, input);
              } catch (e) {
                errorHere(e, {}, input);
              }
            }, { class: "app-input cp-input mono", dataset: { field: "now" }, placeholder: w.held ? "" : "Not held yet" })
          : h("span", { class: "hint cp-play-first" }, "Play the page to see its live state");
        const param = w.params.find((p) => p.name === w.default);
        const value = w.default ? (w.arguments[w.default] as Value | undefined) : undefined;
        const defaultBox = !w.default
          ? h("span", { class: "hint" }, "It has no default")
          : value && value.kind !== "literal"
            ? h("span", { class: "cp-bound", dataset: { kind: value.kind } }, icon(value.kind === "expression" ? "code" : "link"), h("code", { class: "mono" }, value.source))
            : box(value ? shownText(value.value, param?.type ?? "any") : "", "Default", (typed, input) => {
                try {
                  void change(blockId, typed.trim() === "" && value ? { do: "reset", widget: w.index, name: w.default } : { do: "set", widget: w.index, name: "default", value: value?.form === "date" ? typed.trim() : typedValue(typed, param?.type ?? "any") }, input);
                } catch (e) {
                  errorHere(e, {}, input);
                }
              }, { class: "app-input cp-input mono", dataset: { field: "default" }, placeholder: param?.default === null || param?.default === undefined ? "" : shownText(param.default, param.type) });
        return h(
          "div",
          { class: "cp-state", dataset: { widget: String(w.index) } },
          h("div", { class: "cp-state-title" }, h("strong", {}, w.label ?? w.title), h("span", { class: "hint mono" }, w.call)),
          h("label", { class: "cp-row" }, h("span", { class: "cp-name" }, "Key"), h("span", { class: "cp-value" }, keyBox)),
          h("label", { class: "cp-row", title: "The running app only: its session state. The cell's code does not change." }, h("span", { class: "cp-name" }, "Now"), h("span", { class: "cp-value" }, nowBox)),
          h("label", { class: "cp-row", title: `Written into the cell's code${w.default ? ` (${w.default}=)` : ""}.` }, h("span", { class: "cp-name" }, "Default"), h("span", { class: "cp-value" }, defaultBox)),
        );
      }),
    );
  }

  function cacheSection(blockId: string, caches: CacheRow[], running: boolean): HTMLElement | null {
    if (!caches.length) return null;
    const c = canvas();
    return h(
      "div",
      { class: "cp-part", dataset: { part: "cache" } },
      h("div", { class: "cp-list-title" }, "Cache"),
      ...caches.map((f) => {
        const where = f.own ? {} : { document: f.document, cell: f.cell };
        const send = (kind: string | null, settings: Record<string, unknown> | undefined, from: HTMLElement): void => void change(blockId, { do: "cache", function: f.name, kind, ...(settings ? { settings } : {}), ...where }, from);
        const title = h("div", { class: "cp-state-title" }, h("strong", { class: "mono" }, `${f.name}()`), f.own ? null : link("forward", f.where, () => host.goToCell(f.document, f.cell, f.line)));
        if (!f.cache) return h("div", { class: "cp-cache", dataset: { function: f.name } }, title, button("Cache this function", (e) => send("data", undefined, e.currentTarget as HTMLElement), { icon: "plus", class: "ghost cp-cache-add" }));
        const kind = h("select", { class: "app-input cp-input", "aria-label": "Cache" }, h("option", { value: "data", selected: f.cache === "data" }, "st.cache_data"), h("option", { value: "resource", selected: f.cache === "resource" }, "st.cache_resource"), h("option", { value: "" }, "Not cached")) as HTMLSelectElement;
        kind.addEventListener("change", () => send(kind.value || null, undefined, kind));
        const setting = (name: string, type: Param["type"]): HTMLElement => {
          const value = f.settings[name] as Value | undefined;
          let editor: HTMLElement;
          if (value && value.kind !== "literal") editor = h("span", { class: "cp-bound", dataset: { kind: value.kind } }, icon("code"), h("code", { class: "mono" }, value.source));
          else if (type === "bool") {
            const tick = h("input", { type: "checkbox", "aria-label": name, checked: value ? value.value !== false && value.value !== null : name === "show_spinner" }) as HTMLInputElement;
            tick.addEventListener("change", () => send(f.cache, { [name]: name === "persist" ? (tick.checked ? "disk" : null) : tick.checked }, tick));
            editor = tick;
          } else {
            const shown = value ? shownText(value.value, "any") : "";
            editor = box(shown, name, (typed, input) => {
              if (typed === shown) return;
              try {
                send(f.cache, { [name]: typed.trim() === "" ? null : typedValue(typed, type === "number" ? "number" : "any") }, input);
              } catch (e) {
                errorHere(e, {}, input);
              }
            }, { class: "app-input cp-input mono", dataset: { field: name } });
          }
          const row = h("label", { class: `cp-row${value ? " set" : ""}`, title: CACHE_WORDS[name], dataset: { property: name } }, h("span", { class: "cp-name" }, name), h("span", { class: "cp-value" }, editor));
          row.addEventListener("focusin", () => describe(CACHE_WORDS[name] ?? ""));
          return row;
        };
        const clearButton = button("Clear this cache", (e) => {
          const from = e.currentTarget as HTMLButtonElement;
          void busyButton(from, now({ clear: f.name }, from), "Clearing…");
        }, { icon: "reset", class: "ghost cp-cache-clear", title: running ? "The running app only: this function's kept results go" : "Play the page first: this clears the running app's cache" });
        clearButton.disabled = !running;
        void c;
        return h("div", { class: "cp-cache", dataset: { function: f.name } }, title, h("label", { class: "cp-row set" }, h("span", { class: "cp-name" }, "Kind"), h("span", { class: "cp-value" }, kind)), setting("ttl", "any"), setting("max_entries", "number"), setting("show_spinner", "bool"), f.cache === "data" ? setting("persist", "bool") : null, clearButton);
      }),
    );
  }

  function eventsSection(blockId: string, widgets: Widget[], where: { document: string; cell: number }, editable: boolean): HTMLElement | null {
    const having = widgets.filter((w) => w.event);
    if (!having.length) return null;
    const add = async (w: Widget, from: HTMLElement): Promise<void> => {
      const plan = await change(blockId, { do: "handler", widget: w.index, event: w.event }, from);
      if (plan?.line) host.goToCell(where.document, where.cell, plan.line);
    };
    return section(
      "events",
      "Events",
      having.filter((w) => w.events[w.event!]).length,
      h(
        "div",
        { class: "cp-grid", role: "grid" },
        ...having.map((w) => {
          const set = w.events[w.event!];
          const row = h(
            "div",
            { class: `cp-row${set ? " set" : ""}`, role: "row", dataset: { event: w.event!, widget: String(w.index) }, title: set ? "Its handler. A double-click goes to it." : "A double-click writes its handler into the cell." },
            h("span", { class: "cp-name", role: "rowheader" }, h("span", {}, w.event!), h("span", { class: "hint" }, w.label ?? w.call)),
            h(
              "span",
              { class: "cp-value", role: "cell" },
              set
                ? h("button", { type: "button", class: "link mono cp-handler", onclick: (e: Event) => void add(w, e.currentTarget as HTMLElement) }, set.handler ?? set.source)
                : (() => {
                    const b = button("Add handler", (e) => void add(w, e.currentTarget as HTMLElement), { icon: "plus", class: "ghost cp-add-handler" });
                    b.disabled = !editable;
                    return b;
                  })(),
            ),
          );
          row.addEventListener("dblclick", (e) => {
            if (editable && !(e.target as HTMLElement).closest("button")) void add(w, row);
          });
          return row;
        }),
      ),
    );
  }

  function controllerSection(block: BlockState): HTMLElement | null {
    const controller = controllerOf(block);
    if (!controller) return null;
    return section(
      "controller",
      "Controller",
      null,
      h("div", { class: "pp-row" }, h("span", { class: "app-label" }, "Role"), h("span", { class: "app-role", dataset: { role: controller.role } }, ROLES[controller.role])),
      ...controller.makes.map((m) => h("div", { class: "pp-row app-make", dataset: { name: m.name } }, chip(m.name), h("span", { class: "hint mono" }, m.default === null ? m.type : `${m.type} = ${m.default}`))),
      ...controller.problems.map((p) => h("div", { class: "cv-block-missing", role: "alert" }, p)),
    );
  }

  function toolbar(title: string): HTMLElement {
    const search = h("input", { type: "search", class: "app-input cp-search", placeholder: "Search properties", "aria-label": "Search properties", value: filter }) as HTMLInputElement;
    search.addEventListener("input", () => {
      filter = search.value.trim();
      const at = search.selectionStart;
      render();
      const again = body?.querySelector<HTMLInputElement>(".cp-search");
      again?.focus();
      if (again && at !== null) again.setSelectionRange(at, at);
    });
    search.addEventListener("keydown", (e) => e.stopPropagation());
    const pick = (how: "category" | "name", label: string, ic: string): HTMLButtonElement => button(label, () => {
      sort = how;
      render();
    }, { icon: ic, iconOnly: true, pressed: sort === how, class: `ghost cp-sort-${how}` });
    return h("div", { class: "cp-toolbar" }, h("div", { class: "cp-target", title }, title), h("div", { class: "cp-tools" }, h("span", { class: "cv-group", role: "group", "aria-label": "Order" }, pick("category", "Categorized", "rows"), pick("name", "Alphabetical", "sortup")), search));
  }

  function render(): void {
    if (!body) return;
    const c = canvas();
    const block = c.selected();
    const many = c.selection();
    describe("");
    if (many.length > 1) return void clear(body, toolbar(`${many.length} blocks`), multiSection(many), words);
    if (!seen || seen.target === "app" || (seen.target === "block" && !block) || (seen.target === "page" && block)) {
      // Nothing selected (or not read yet): the app's page settings.
      const settings = h("div", { class: "cp-settings" });
      host.drawSettings(settings);
      return void clear(body, h("div", { class: "cp-toolbar" }, h("div", { class: "cp-target" }, c.page()?.name ?? "The app")), settings, seen ? null : loadingBlock("Reading its properties…"));
    }
    if (seen.target === "page") {
      const settings = h("div", { class: "cp-settings" });
      host.drawSettings(settings);
      return void clear(
        body,
        h("div", { class: "cp-toolbar" }, h("div", { class: "cp-target" }, seen.page?.name ?? "Page")),
        section("blocks", "Blocks", seen.blocks?.length ?? 0, list("On this page", (seen.blocks ?? []).map((b) => link("forward", b.name ?? b.where, () => c.select(b.id), b.name ? b.where : ""))), list("Tables", (seen.tables ?? []).map((t) => {
          const el = link("table", t, () => void 0);
          el.addEventListener("click", () => void showTable(t, el));
          return el;
        })), table ? tablePreview(table) : null),
        section("app", "The app", null, settings),
        rows.length ? section("session", "Session state", rows.length, sessionTable(rows)) : null,
      );
    }
    if (!block || !seen.block) return;
    const where = { document: seen.block.document, cell: seen.block.cell };
    const widgets = seen.widgets ?? [];
    if (widgetAt >= widgets.length) widgetAt = 0;
    const widget = widgets[widgetAt] as Widget | undefined;
    const picker = widgets.length > 1
      ? (() => {
          const select = h("select", { class: "app-input cp-element", "aria-label": "Element" }, ...widgets.map((w, i) => h("option", { value: String(i), selected: i === widgetAt }, `${w.label ?? w.target ?? w.title} · ${w.call}`))) as HTMLSelectElement;
          select.addEventListener("change", () => {
            widgetAt = Number(select.value);
            render();
          });
          return select;
        })()
      : null;
    const all = [...designRows(block, seen.block), ...(widget ? widgetRows(block.id, widget, seen.editable === true, where) : [])];
    const streamlit = section("streamlit", "Streamlit", null, stateSection(block.id, widgets, seen.running), cacheSection(block.id, seen.cache ?? [], seen.running));
    clear(
      body,
      toolbar(block.name ?? seen.block.where),
      seen.block.missing ? h("div", { class: "cv-block-missing", role: "alert" }, seen.block.missing) : null,
      seen.problem ? h("div", { class: "cv-block-missing", role: "alert" }, seen.problem) : null,
      section("properties", "Properties", null, picker, widget ? h("div", { class: "cp-element-title hint" }, `st.${widget.call} · ${widget.title}`) : null, grid(all)),
      seen.uses ? usesSection(seen.uses, block.id) : null,
      streamlit,
      eventsSection(block.id, widgets, where, seen.editable === true),
      controllerSection(block),
      seen.code ? section("code", "Code", null, h("pre", { class: "cp-code mono", tabindex: 0, "aria-label": "The code the page runs for this block" }, seen.code), button("Go to cell", () => host.goToCell(where.document, where.cell), { icon: "forward", class: "ghost cp-go" })) : null,
      words,
    );
  }

  function sessionTable(held: SessionRow[]): HTMLElement {
    return h(
      "table",
      { class: "app-state" },
      h("thead", {}, h("tr", {}, h("th", {}, "Key"), h("th", {}, "Value"), h("th", {}, "Block"))),
      h("tbody", {}, ...held.map((r) => h("tr", { dataset: { key: r.key } }, h("td", { class: "mono" }, r.key), h("td", { class: "mono" }, shownValue(r.value)), h("td", {}, r.block ?? "")))),
    );
  }

  /** Several blocks selected: the properties they share (their size), set on all of them at once. */
  function multiSection(blocks: BlockState[]): HTMLElement {
    const c = canvas();
    const same = <T,>(pick: (b: BlockState) => T): T | undefined => (blocks.every((b) => pick(b) === pick(blocks[0]!)) ? pick(blocks[0]!) : undefined);
    const field = (name: string, value: number | null | undefined, min: number, max: number, body: (n: number | null) => Record<string, unknown>): Row => ({
      name,
      category: "Layout",
      words: `${name}: set on all ${blocks.length} blocks.`,
      set: value !== undefined,
      editor: box(value === undefined || value === null ? "" : String(value), name, (typed, input) => {
        const n = typed.trim() === "" ? null : Math.round(Number(typed));
        if (n !== null && (Number.isNaN(n) || n < min || n > max)) return void errorHere(`${name} is ${min} to ${max}.`, {}, input);
        if (n === null && name === "Width") return;
        void c.changeBlocks(blocks.map((b) => b.id), body(n));
      }, { placeholder: value === undefined ? "Mixed" : "", dataset: { field: name.toLowerCase() } }),
    });
    return h("div", {}, grid([field("Width", same((b) => b.w), 2, 12, (n) => ({ w: n })), field("Height", same((b) => b.h), 1, 30, (n) => ({ h: n }))]));
  }

  return {
    draw: (into) => {
      body = into;
      body.classList.add("cp");
      render();
      void read();
    },
    refresh: () => void read(),
    shown: () => seen,
    setRows: (next) => {
      const changed = JSON.stringify(next) !== JSON.stringify(rows);
      rows = next;
      // The live values moved: the Now boxes follow, unless one is being typed in.
      if (changed && body && !body.contains(document.activeElement)) void read();
    },
  };
}
