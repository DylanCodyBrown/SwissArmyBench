/**
 * erdView.ts: the ERD tab: the keys and joins between the open tables, as a diagram. [WIRE + EXPORT]
 *
 * The second app-level tab, after Agent. It draws the current relationship model (routes_models.py)
 * for the tables that are open: one box per table holding only its key columns, crow's-foot lines
 * for the joins (Mermaid erDiagram, drawn by the lazy diagram chunk). With no relationships for
 * the open tables it says so, and offers the ways to get some: import a model file, or apply a
 * shared model.
 *
 * ROUTING: [DIAGRAM]          -> read-only, from GET /relationships/erd (redrawn on relationships_updated)
 *          [EMPTY STATE]      -> read-only, when no relationship covers an open table
 *          [IMPORT]           Import relationships: file picker -> relationshipsDialog.importRelationships()
 *          [FIT]              the diagram is fitted to the window when drawn; Fit does it again -> fit()
 *          [SHARED MODELS]    Apply -> applyShared(name)
 *          [MANAGE]           -> relationshipsDialog.openRelationships()
 *          [FIND]             -> openRelationships(true): the window, its finder already running
 *          [FOLLOW]           the agent added a relationship (Follow the agent, sessionPage.ts): its line
 *                             and its two tables pulse as the diagram draws it -> highlightRelationships()
 */
import { api } from "./api";
import { button, clear, h } from "./dom";
import { contextOf, gridList, onAgentView, viewingErd } from "./panes";
import { currentModel, onRelationshipsChange, projectScope, scopeSwitch } from "./relationships";
import { importRelationships, openRelationships } from "./relationshipsDialog";
import { pulse } from "./sessionPage";
import { effectiveTheme, onThemeChange } from "./theme";
import { errorHere } from "./errorNote";

let host: HTMLElement;
let diagramModule: Promise<typeof import("./lazy/diagram")> | null = null;
const diagrams = (): Promise<typeof import("./lazy/diagram")> => {
  diagramModule ??= import(/* external */ "/static/build/lazy/diagram.js" as string) as Promise<typeof import("./lazy/diagram")>;
  return diagramModule;
};

export function mountErd(element: HTMLElement): void {
  host = element;
  const redraw = (): void => { if (viewingErd()) void render(); };
  onAgentView(redraw);
  onRelationshipsChange(redraw);
  onThemeChange(redraw);
  // A fitted diagram follows the window's size.
  new ResizeObserver(() => { if (fitted && viewingErd()) fit(); }).observe(host);
}

// Whether the diagram is fitted to the window (so a window resize fits it again) or at its own size.
let fitted = true;
const MAX_GROW = 2; // a small diagram is not blown up past twice its own size

/** Size the diagram: fitted, the largest that shows whole in the room under the buttons (never
 * more than twice its own size); else its own size, scrolling when the window is smaller. */
function fit(): void {
  const slot = host.querySelector<HTMLElement>(".erd-diagram");
  const svg = slot?.querySelector<SVGSVGElement>("svg");
  if (!slot || !svg) return;
  const [, , width, height] = (svg.getAttribute("viewBox") ?? "").split(/[\s,]+/).map(Number);
  if (!width || !height) return;
  const pad = parseFloat(getComputedStyle(host).paddingBottom) || 0;
  const roomWide = slot.clientWidth;
  const roomHigh = host.clientHeight - (slot.getBoundingClientRect().top - host.getBoundingClientRect().top + host.scrollTop) - pad - 4;
  const scale = fitted ? Math.min(MAX_GROW, roomWide / width, Math.max(40, roomHigh) / height) : 1;
  svg.style.maxWidth = "none";
  svg.style.maxHeight = "none";
  svg.style.width = `${Math.floor(width * scale)}px`;
  svg.style.height = `${Math.floor(height * scale)}px`;
  slot.dataset.fitted = String(fitted);
}

/** The open tables' dataset names (the model names tables by dataset). */
function openTables(): string[] {
  return [...new Set(gridList().map((g) => contextOf(g.id)?.dataset).filter((d): d is string => !!d))];
}

// Each draw's number: a slower, older draw (the model was still loading) never paints over a newer one.
let renders = 0;
// With a project open: all of the model's tables (true), or only those the project uses (the default; the
// owner, 2026-11-17: "Relationships should filter the erd to only the tables that are being used").
let showAll = false;

async function render(): Promise<void> {
  const mine = ++renders;
  // Read the model as main.ts keeps it (loaded at start and on each relationships_updated).
  // Loading it here would notify onRelationshipsChange, which redraws: a loop.
  const model = currentModel();
  const open = new Set(openTables());
  const named = [...new Set([...Object.keys(model.tables), ...model.relationships.flatMap((r) => [r.from, r.to])])];
  // The open tables' part of the model; none of them open (a Power BI dataset's relationships just
  // imported, its tables not opened yet): the whole model, rather than "No relationships yet".
  const openPart = named.filter((t) => open.has(t));
  const scope = named.length ? await projectScope() : null;
  if (mine !== renders) return;
  const inProject = scope?.project === true;
  // A project open: the tables it uses (or all). None open: the open tables, else the whole model.
  const covered = inProject ? (showAll ? named : scope.tables) : openPart.length || !model.relationships.length ? openPart : named;
  const switcher = inProject
    ? h(
        "div",
        { class: "erd-scope" },
        scopeSwitch(showAll, (all) => {
          showAll = all;
          void render();
        }),
        scope.words ? h("span", { class: "hint erd-hidden" }, scope.words) : null,
      )
    : null;
  const file = h("input", { type: "file", accept: ".json,.tang,application/json", hidden: true, onchange: () => void importModel(file) });
  const actions = h(
    "div",
    { class: "erd-actions" },
    file,
    button("Import relationships", () => file.click(), { icon: "import", title: "A saved set (reviewed before it is applied) or a model as JSON" }),
    button("Manage relationships", () => openRelationships(), { icon: "crown" }),
  );
  // With a diagram on screen: its size. Fitted to the window as it is drawn; Actual size is for a
  // diagram too large to read when fitted (it then scrolls).
  const sizing = [
    button("Fit", () => { fitted = true; fit(); }, { icon: "max", title: "Fit the diagram to the window" }),
    button("Actual size", () => { fitted = false; fit(); }, { icon: "zoom" }),
  ];
  if (!covered.length && inProject && named.length) {
    clear(
      host,
      h("h1", { class: "sandbox-title" }, "ERD"),
      actions,
      switcher,
      h("p", { class: "hint" }, "None of the relationships' tables is used in this project."),
    );
    return;
  }
  if (!covered.length) {
    const shared = await sharedModels(open);
    if (mine !== renders) return;
    clear(
      host,
      // ===== EMPTY STATE =====
      h(
        "div",
        { class: "erd-empty" },
        h("h1", { class: "sandbox-title" }, "ERD"),
        h("strong", {}, "No relationships yet."),
        button("Find relationships", () => openRelationships(true), { icon: "zoom", class: "primary" }),
        actions,
        shared,
      ),
    );
    return;
  }
  const slot = h("div", { class: "diagram erd-diagram", role: "img", "aria-label": `Relationships of ${covered.join(", ")}` });
  clear(
    host,
    h("h1", { class: "sandbox-title" }, "ERD"),
    actions,
    switcher,
    // ===== DIAGRAM =====
    slot,
  );
  actions.append(...sizing);
  try {
    // All tables: every table, the shared catalog's (the library's catalog/: a teammate's) among them.
    const erd = await api<{ mermaid: string }>(
      inProject && showAll ? "/relationships/erd?scope=all" : `/relationships/erd?tables=${encodeURIComponent(covered.join(","))}`,
    );
    const m = await diagrams();
    if (mine !== renders) return;
    await m.drawDiagram(slot, erd.mermaid, effectiveTheme() !== "light");
    fitted = true; // a diagram just drawn fits the window
    fit();
    drawn = erd.mermaid;
    marked();
  } catch (e) {
    slot.textContent = (e as Error).message;
  }
}

/** Shared models with at least one table open, each with Apply. */
async function sharedModels(open: Set<string>): Promise<HTMLElement | null> {
  try {
    const library = await api<{ models: { name: string; description: string; open_tables: string[]; tables: string[] }[] }>("/relationships/library");
    const fitting = library.models.filter((m) => m.open_tables.some((t) => open.has(t)));
    if (!fitting.length) return null;
    return h(
      "div",
      { class: "erd-shared" },
      h("h3", {}, "Shared models"),
      ...fitting.map((m) =>
        h(
          "div",
          { class: "erd-shared-row" },
          h("span", {}, h("strong", {}, m.name), ` · ${m.open_tables.length} of ${m.tables.length} tables open`),
          button("Apply", () => void applyShared(m.name), { class: "primary" }),
        ),
      ),
    );
  } catch {
    return null;
  }
}

async function applyShared(name: string): Promise<void> {
  try {
    await api(`/relationships/library/${encodeURIComponent(name)}`, "POST");
  } catch (e) {
    errorHere(e);
  }
}

async function importModel(file: HTMLInputElement): Promise<void> {
  const picked = file.files?.[0];
  file.value = "";
  if (picked) await importRelationships(picked);
}

// ===== Follow the agent: a relationship just added, highlighted as it is drawn =====

/** The Mermaid text on screen (its relationship lines are drawn in its order). */
let drawn = "";
/** The relationships to highlight ("orders.customer_id -> customers.id"), until a diagram shows them. */
let wanted: { keys: string[]; until: number } | null = null;
const HIGHLIGHT_WAIT_MS = 8000;

/** Highlight these relationships once the ERD draws them (now, if it shows them already). */
export function highlightRelationships(keys: string[]): void {
  wanted = { keys, until: Date.now() + HIGHLIGHT_WAIT_MS };
  if (viewingErd()) marked();
}

/** A relationship's two tables, by its key's words. */
function tablesOf(key: string): [string, string] | null {
  const [left, right] = key.split(" -> ");
  if (!left || !right) return null;
  return [left.slice(0, left.lastIndexOf(".")), right.slice(0, right.lastIndexOf("."))];
}

const ident = (name: string): string => name.replace(/[^A-Za-z0-9_-]/g, "_") || "_";

function marked(): void {
  if (!wanted || Date.now() > wanted.until) {
    wanted = null;
    return;
  }
  const svg = host?.querySelector<SVGSVGElement>(".erd-diagram svg");
  if (!svg || !drawn) return;
  const lines = svg.querySelectorAll<SVGPathElement>("path.relationshipLine");
  // The relationship lines in the text's order: "    orders }o--|| customers : ..."
  const order = drawn.split("\n").map((line) => /^\s{4}(\S+) \S+ (\S+) : "/.exec(line)).filter((m): m is RegExpExecArray => !!m);
  let found = 0;
  for (const key of wanted.keys) {
    const tables = tablesOf(key);
    if (!tables) continue;
    const a = ident(tables[0]);
    const b = ident(tables[1]);
    const at = order.findIndex((m) => (m[1] === a && m[2] === b) || (m[1] === b && m[2] === a));
    if (at < 0 || !lines[at]) continue;
    found += 1;
    const line = lines[at]!;
    line.dataset.followed = key;
    pulse(line, 4000);
    for (const name of [a, b]) pulse(svg.querySelector(`g[id^="entity-${CSS.escape(name)}-"]`), 4000);
    if (found === 1) (line as unknown as HTMLElement).scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }
  if (found) wanted = null;
}
