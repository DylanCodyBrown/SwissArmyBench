/**
 * workbenchLineage.ts: a cell's lineage with its values, in an overlay (docs/ideas.md, lineage with
 * values and approved outputs, 2026-11-15). [WIRE]
 *
 *   [FLOW]    right-click a block on a canvas, or a cell of a notebook or script, and choose Lineage:
 *             the server traces it back through every cell to the data (services/lineage.py) and draws
 *             it as a Mermaid flowchart, top to bottom (the app's own Mermaid: lazy/diagram.ts, its
 *             drawing cleaned by lazy/svgSafe.ts)
 *   [VALUES]  on the left, one card per step in flow order, each beside its node: a table's rows and
 *             columns, its first rows and its row change from the step before; a value as itself; a
 *             chart as a small picture; an error in red where the flow broke
 *   [PICK]    a click on a card or a node marks both; a double-click (or Enter) goes to the cell
 *   [LIVE]    while it is open the values follow: a run in the window, a filter changed on a playing
 *             page, a grid step. Asked again every few seconds; drawn again only when a value changed
 *
 * ROUTING: POST /workbench/lineage (routes_lineage.py)
 */
import { api } from "./api";
import { button, clear, h, toast } from "./dom";
import { effectiveTheme } from "./theme";

export interface LineageTarget {
  /** A cell of a notebook or script: its path (or, unsaved, its title) and its own number. */
  document?: string | null;
  cell?: number;
  /** Or a block of a canvas's page. */
  app?: string;
  page?: string;
  block?: string;
}

export interface LineageNode {
  id: string;
  kind: "cell" | "controller" | "text" | "table" | "step" | "source";
  label: string;
  where: string;
  document: string | null;
  cell: number | null;
  doc_kind: "notebook" | "script" | "data" | null;
  makes: string[];
  reads: string[];
  table: string | null;
  step: number | null;
  target: boolean;
  on_page: boolean;
}

interface ValueItem {
  name: string;
  kind: "table" | "value" | "picture" | "chart" | "missing";
  rows?: number;
  columns?: number;
  names?: string[];
  head?: unknown[][];
  change?: number;
  text?: string;
  type?: string;
  png?: string;
}

interface NodeValue {
  items: ValueItem[];
  error: string | null;
  from: string;
  busy?: boolean;
}

export interface LineageGraph {
  target: string;
  nodes: LineageNode[];
  edges: { source: string; target: string; name: string; kind: string }[];
  notes: string[];
  mermaid: string;
  values?: Record<string, NodeValue>;
  busy?: boolean;
  mark?: string;
  playing?: boolean;
}

export interface LineageHost {
  /** The request for a target in this window (its cells as held now, its kernel, its errors). */
  body: (target: LineageTarget) => Record<string, unknown>;
  /** Go to a node's cell (open its file when it is not open). */
  goTo: (node: LineageNode) => void;
}

const POLL_MS = 3000;
const KINDS: Record<LineageNode["kind"], string> = { cell: "Cell", controller: "Controller", text: "Text", table: "Table", step: "Grid step", source: "Source" };

// Mermaid (lazy/diagram.ts), loaded the first time a lineage opens.
let diagramModule: Promise<typeof import("./lazy/diagram")> | null = null;
const diagrams = (): Promise<typeof import("./lazy/diagram")> => {
  diagramModule ??= import(/* external */ "/static/build/lazy/diagram.js" as string) as Promise<typeof import("./lazy/diagram")>;
  return diagramModule;
};

const count = new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 });
const plural = (n: number, word: string): string => `${count.format(n)} ${word}${n === 1 ? "" : "s"}`;
const signed = (n: number): string => (n > 0 ? `+${count.format(n)}` : n < 0 ? `−${count.format(-n)}` : "±0");

/** A theme colour as hex (Mermaid reads no other form), resolved inside the overlay. */
function colour(where: HTMLElement, name: string): string {
  const probe = h("span", { hidden: true });
  probe.style.color = `var(${name})`;
  where.append(probe);
  const rgb = getComputedStyle(probe).color.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  probe.remove();
  return rgb ? `#${rgb.slice(1, 4).map((v) => Number(v).toString(16).padStart(2, "0")).join("")}` : "#888888";
}

/** The server's Mermaid text with the kind colours of this window's theme in place of its neutral ones. */
function themed(text: string, where: HTMLElement): string {
  const notebook = colour(where, "--lineage-notebook");
  const script = colour(where, "--lineage-script");
  const soft = colour(where, "--accent-soft");
  const kept = text.split("\n").filter((line) => !line.trim().startsWith("classDef "));
  return [
    ...kept,
    `  classDef notebook stroke:${notebook},stroke-width:2px`,
    `  classDef data stroke:${notebook},stroke-width:3px`,
    `  classDef script stroke:${script},stroke-width:2px`,
    "  classDef source stroke-dasharray:4 3",
    `  classDef target fill:${soft},stroke-width:3px,color:${colour(where, "--fg")}`,
    "",
  ].join("\n");
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "number" ? count.format(value) : String(value);
}

function itemView(item: ValueItem, many: boolean): HTMLElement {
  const name = many || item.kind === "table" ? h("span", { class: "wb-lin-name mono" }, item.name) : null;
  if (item.kind === "missing") return h("div", { class: "wb-lin-item" }, name, h("span", { class: "hint" }, "not run yet"));
  if (item.kind === "picture" && item.png) return h("div", { class: "wb-lin-item" }, name, h("img", { class: "wb-lin-picture", alt: item.name, src: `data:image/png;base64,${item.png}` }));
  if (item.kind === "chart") return h("div", { class: "wb-lin-item" }, name, h("span", { class: "hint" }, item.text ?? "a chart"));
  if (item.kind === "table") {
    const change = typeof item.change === "number" && item.change !== 0 ? h("span", { class: `wb-lin-change ${item.change < 0 ? "down" : "up"}`, title: "Rows from the step before" }, `${signed(item.change)} rows`) : null;
    const names = item.names ?? [];
    const table = h(
      "table",
      { class: "wb-lin-table" },
      h("thead", {}, h("tr", {}, ...names.map((n) => h("th", {}, n)))),
      h("tbody", {}, ...(item.head ?? []).map((row) => h("tr", {}, ...row.map((v) => h("td", {}, cell(v)))))),
    );
    return h(
      "div",
      { class: "wb-lin-item" },
      h("div", { class: "wb-lin-size" }, name, h("span", {}, `${plural(item.rows ?? 0, "row")} × ${plural(item.columns ?? 0, "column")}`), change),
      names.length ? h("div", { class: "wb-lin-head" }, table) : null,
    );
  }
  return h("div", { class: "wb-lin-item" }, name, h("span", { class: "wb-lin-value mono" }, item.text ?? ""));
}

let open: { refresh: () => void; close: () => void } | null = null;

/** Something the lineage may show changed (a run ended, a page ran again, a grid step): ask again. */
export function lineageNoticed(): void {
  open?.refresh();
}

/** Close the lineage overlay, if one is open. */
export function closeLineage(): void {
  open?.close();
}

/** Open the lineage overlay for a cell or a block. What it shows, for the agent. */
export async function openLineage(target: LineageTarget, host: LineageHost): Promise<LineageGraph> {
  open?.close();
  const back = document.activeElement as HTMLElement | null;
  const title = h("span", { class: "wb-lin-target" });
  const values = h("div", { class: "wb-lin-values", role: "list", "aria-label": "Values" });
  const chart = h("div", { class: "wb-lin-chart", "aria-label": "Flow" });
  const flow = h("div", { class: "wb-lin-flow" }, values, chart);
  const notes = h("div", { class: "hint wb-lin-notes" });
  const close = (): void => {
    window.clearInterval(timer);
    resize.disconnect();
    shade.remove();
    document.removeEventListener("keydown", keys, true);
    if (open === handle) open = null;
    back?.focus?.();
  };
  const panel = h(
    "div",
    { class: "wb-lineage", role: "dialog", "aria-modal": "true", "aria-label": "Lineage" },
    h("div", { class: "wb-lin-top" }, h("h2", {}, "Lineage"), title, h("span", { class: "spacer" }), button("Close", close, { icon: "close", iconOnly: true, class: "ghost", title: "Close (Escape)" })),
    h("div", { class: "wb-lin-body" }, flow, notes),
  );
  const shade = h("div", { class: "wb-lineage-shade lineage" }, panel);
  shade.addEventListener("mousedown", (e) => {
    if (e.target === shade) close();
  });
  const keys = (e: KeyboardEvent): void => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
    }
  };
  document.addEventListener("keydown", keys, true);
  document.body.append(shade);

  let graph: LineageGraph | null = null;
  let drawn = ""; // the Mermaid text last drawn
  let shownMark = "";
  let picked: string | null = null;
  let asking = false;
  const cards = new Map<string, HTMLElement>();
  const shapes = new Map<string, Element>();

  const ask = (): Promise<LineageGraph> => api<LineageGraph>("/workbench/lineage", "POST", host.body(target));

  const nodeOf = (id: string): LineageNode | undefined => graph?.nodes.find((n) => n.id === id);

  const pick = (id: string | null, scroll = true): void => {
    picked = id;
    for (const [key, card] of cards) card.classList.toggle("picked", key === id);
    for (const [key, shape] of shapes) shape.classList.toggle("picked", key === id);
    if (id && scroll) cards.get(id)?.scrollIntoView({ block: "nearest" });
  };
  const go = (id: string): void => {
    const node = nodeOf(id);
    if (!node || node.cell === null) return;
    close();
    host.goTo(node);
  };

  /** Each card beside its node: at the node's height, below the card before it when they would meet. */
  const place = (): void => {
    if (!graph) return;
    const top = flow.getBoundingClientRect().top;
    const at = graph.nodes.map((n) => ({ id: n.id, y: shapes.get(n.id)?.getBoundingClientRect().top ?? 0 })).sort((a, b) => a.y - b.y);
    let below = 0;
    for (const { id, y } of at) {
      const card = cards.get(id);
      if (!card) continue;
      const want = Math.max(0, y - top);
      const y0 = Math.max(want, below);
      card.style.top = `${y0}px`;
      below = y0 + card.offsetHeight + 8;
    }
    values.style.minHeight = `${below}px`;
  };
  const resize = new ResizeObserver(() => place());
  resize.observe(chart);

  const drawCards = (): void => {
    if (!graph) return;
    cards.clear();
    clear(values);
    for (const node of graph.nodes) {
      const value = graph.values?.[node.id];
      const items = value?.items ?? [];
      const card = h(
        "article",
        {
          class: `wb-lin-card kind-${node.kind} ${node.doc_kind ? `doc-${node.doc_kind}` : ""} ${node.target ? "target" : ""} ${value?.error ? "broke" : ""}`,
          role: "listitem",
          tabindex: 0,
          "aria-label": `${node.label}, ${node.where || KINDS[node.kind]}`,
          dataset: { node: node.id },
        },
        h("div", { class: "wb-lin-card-head" }, h("span", { class: "wb-lin-label" }, node.label), node.on_page ? h("span", { class: "wb-lin-page", title: "On the page" }, "page") : null),
        h("div", { class: "hint wb-lin-where" }, node.where || KINDS[node.kind]),
        value?.error ? h("div", { class: "wb-lin-error error-text", role: "alert" }, `⚠ ${value.error}`) : null,
        ...items.map((item) => itemView(item, items.length > 1)),
        value?.busy ? h("div", { class: "hint" }, "busy") : null,
      );
      card.addEventListener("click", () => pick(node.id, false));
      card.addEventListener("dblclick", () => go(node.id));
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter") go(node.id);
        else if (e.key === " ") pick(node.id, false);
        else return;
        e.preventDefault();
      });
      cards.set(node.id, card);
      values.append(card);
    }
    pick(picked, false);
  };

  const drawChart = async (): Promise<void> => {
    if (!graph) return;
    const text = themed(graph.mermaid, panel);
    if (text === drawn) return;
    drawn = text;
    const m = await diagrams();
    await m.drawDiagram(chart, text, effectiveTheme().endsWith("dark"));
    shapes.clear();
    const svg = chart.querySelector("svg");
    if (svg) {
      // Drawn at its own size: the cards line up with the nodes as drawn.
      svg.classList.remove("fit-svg");
      const box = (svg.getAttribute("viewBox") ?? "").split(/[\s,]+/).map(Number);
      svg.style.width = box[2] ? `${box[2]}px` : "";
      svg.style.maxWidth = "100%";
      svg.style.maxHeight = "";
    }
    for (const g of chart.querySelectorAll("g.node")) {
      const found = /(?:^|-)flowchart-(n\d+)-\d+$/.exec(g.id);
      if (!found) continue;
      const id = found[1]!;
      shapes.set(id, g);
      (g as SVGGElement).style.cursor = "pointer";
      g.addEventListener("click", () => pick(id));
      g.addEventListener("dblclick", () => go(id));
    }
    pick(picked, false);
  };

  const draw = async (next: LineageGraph): Promise<void> => {
    graph = next;
    const mine = next.nodes.find((n) => n.target);
    title.textContent = mine ? `${mine.label} · ${mine.where}` : "";
    notes.textContent = next.notes.join(" ");
    shownMark = next.mark ?? "";
    drawCards();
    await drawChart();
    place();
  };

  const refresh = (): void => {
    if (asking || !document.body.contains(shade)) return;
    asking = true;
    void ask()
      .then(async (next) => {
        if (next.mark !== shownMark || next.mermaid !== graph?.mermaid) await draw(next);
      })
      .catch(() => undefined)
      .finally(() => (asking = false));
  };
  const timer = window.setInterval(() => {
    if (document.visibilityState === "visible") refresh();
  }, POLL_MS);
  const handle = { refresh, close };
  open = handle;

  try {
    const first = await ask();
    await draw(first);
    (values.querySelector(".wb-lin-card.target") as HTMLElement | null)?.focus();
    return first;
  } catch (e) {
    close();
    toast((e as Error).message, "error");
    throw e;
  }
}
