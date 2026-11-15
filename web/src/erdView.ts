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
 */
import { api } from "./api";
import { button, clear, h, toast } from "./dom";
import { contextOf, gridList, onAgentView, viewingErd } from "./panes";
import { currentModel, onRelationshipsChange } from "./relationships";
import { importRelationships, openRelationships } from "./relationshipsDialog";
import { effectiveTheme, onThemeChange } from "./theme";

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

async function render(): Promise<void> {
  // Read the model as main.ts keeps it (loaded at start and on each relationships_updated).
  // Loading it here would notify onRelationshipsChange, which redraws: a loop.
  const model = currentModel();
  const open = new Set(openTables());
  const covered = [...new Set([...Object.keys(model.tables), ...model.relationships.flatMap((r) => [r.from, r.to])])].filter((t) => open.has(t));
  const file = h("input", { type: "file", accept: ".tang,.json,application/json", hidden: true, onchange: () => void importModel(file) });
  const actions = h(
    "div",
    { class: "erd-actions" },
    file,
    button("Import relationships", () => file.click(), { icon: "import", title: "A .tang file (reviewed before it is applied) or a model as JSON" }),
    button("Manage relationships", () => openRelationships(), { icon: "crown" }),
  );
  // With a diagram on screen: its size. Fitted to the window as it is drawn; Actual size is for a
  // diagram too large to read when fitted (it then scrolls).
  const sizing = [
    button("Fit", () => { fitted = true; fit(); }, { icon: "max", title: "Fit the diagram to the window" }),
    button("Actual size", () => { fitted = false; fit(); }, { icon: "zoom" }),
  ];
  if (!covered.length) {
    clear(
      host,
      // ===== EMPTY STATE =====
      h(
        "div",
        { class: "erd-empty" },
        h("h1", { class: "sandbox-title" }, "Relationship diagram"),
        h("strong", {}, "No relationships yet."),
        button("Find relationships", () => openRelationships(true), { icon: "zoom", class: "primary" }),
        actions,
        await sharedModels(open),
      ),
    );
    return;
  }
  const slot = h("div", { class: "diagram erd-diagram", role: "img", "aria-label": `Relationships of ${covered.join(", ")}` });
  clear(
    host,
    h("h1", { class: "sandbox-title" }, "Relationship diagram"),
    actions,
    // ===== DIAGRAM =====
    slot,
  );
  actions.append(...sizing);
  try {
    const erd = await api<{ mermaid: string }>(`/relationships/erd?tables=${encodeURIComponent(covered.join(","))}`);
    const m = await diagrams();
    await m.drawDiagram(slot, erd.mermaid, effectiveTheme() !== "light");
    fitted = true; // a diagram just drawn fits the window
    fit();
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
    toast((e as Error).message, "error");
  }
}

async function importModel(file: HTMLInputElement): Promise<void> {
  const picked = file.files?.[0];
  file.value = "";
  if (picked) await importRelationships(picked);
}
