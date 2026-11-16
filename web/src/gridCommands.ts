/**
 * gridCommands.ts: the grid page's command palette (Ctrl+Shift+P). [FUNCTION + WIRE]
 *
 * The owner's decision 18: every grid-page action in one filtered list, each showing its keys; Enter
 * runs it. The palette itself is the Workbench's (workbenchCommands.ts openPalette); what differs is
 * where the list comes from. The Workbench names its commands in a registry. This page's actions
 * already are its buttons, so the list is read from them each time the palette opens:
 *
 *   Application, Table, Column, Compare   every button of the ribbon's rows, as it stands: its
 *                    words, whether it can be used now, and why not (its tooltip). The Analyze
 *                    menu is listed entry by entry
 *   Steps            the strip's Undo, Redo, Clear the steps and View steps (a step's own Remove is
 *                    in the list under "N steps", which the palette does not open)
 *   Tabs             Go to each tab; New table from a query, Open file…, Tables; for the table in
 *                    front: Compare with…, Rename, Close
 *   Cell             the cell menu's entries, on the cell in front (View value, Copy, Keep these…)
 *
 * So a button added to a row is in the palette the same day, with no second list to keep. Running
 * a command presses its button (found again by its row and words when the palette closes).
 *
 * ROUTING: Ctrl+Shift+P -> openPalette() <- setCommandSource(commands)
 */
import { analysisEntries } from "./analyzeMenu";
import { betaCommands } from "./betaNotes";
import { updateCommands } from "./updates";
import { cellCommands } from "./cellMenu";
import { focusedCell } from "./gridView";
import { activateGrid, activeContext, closeGrid, compareWith, gridList, openWorkbench, renameActive, showAgentView, showErdView, showGridView } from "./panes";
import { setGridZoom } from "./theme";
import { openPalette, setCommandSource, type Command } from "./workbenchCommands";

/** The keys the page already has, shown beside the command they run. */
const KEYS: Record<string, string> = {
  "Steps: Undo": "Ctrl+Z",
  "Steps: Redo": "Ctrl+Y",
  "Application: Zoom in": "Ctrl+=",
  "Application: Zoom out": "Ctrl+-",
  "Cell: View value": "Enter",
  "Cell: Copy": "Ctrl+C",
};

const slug = (text: string): string => text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const shown = (element: HTMLElement): boolean => element.getClientRects().length > 0;
const words = (b: HTMLButtonElement): string => (b.getAttribute("aria-label") || b.textContent || "").trim();

/** Every button under `root` as a command of `group`. Pressing the command presses the button as it
 * is then (a row may have been drawn again since the palette opened). */
function buttonsOf(group: string, root: ParentNode, selector: string, skip: (b: HTMLButtonElement) => boolean = () => false): Command[] {
  const found: Command[] = [];
  const seen = new Set<string>();
  const all = (): HTMLButtonElement[] => [...root.querySelectorAll<HTMLButtonElement>(selector)].filter((b) => shown(b) && !skip(b));
  for (const b of all()) {
    const title = words(b);
    if (!title || seen.has(title)) continue;
    seen.add(title);
    const now = (): HTMLButtonElement | undefined => all().find((x) => words(x) === title);
    found.push({
      id: `${slug(group)}.${slug(title)}`,
      group,
      title: b.getAttribute("aria-pressed") === "true" ? `${title} (on)` : title,
      keys: KEYS[`${group}: ${title}`],
      when: () => now() !== undefined && !now()!.disabled,
      whyNot: b.title && b.title !== title ? b.title : "nothing to act on",
      run: () => now()?.click(),
    });
  }
  return found;
}

function commands(): Command[] {
  const out: Command[] = [];
  const active = activeContext();
  const onGrid = !document.body.classList.contains("agent-view");
  // The Application row is on every tab.
  // The tour bubble's two buttons are a one-time offer, not commands (Tour is already in the row).
  out.push(...buttonsOf("Application", document, ".app-row button", (b) => b.closest(".tour-bubble") !== null));
  out.push({ id: "application.zoom-reset", group: "Application", title: "Zoom 100%", keys: "Ctrl+0", run: () => setGridZoom(1) });
  out.push(...betaCommands()); // beta mode on or off, Leave a note…, Export beta log…
  out.push(...updateCommands()); // Update to X, What's new, Check for updates
  // The ribbon's rows, each under its own name; the Analyze button is its menu's entries.
  for (const row of document.querySelectorAll<HTMLElement>(".ribbon .ribbon-group")) {
    const name = row.querySelector(".ribbon-caption strong")?.textContent?.trim() ?? "Table";
    out.push(...buttonsOf(name, row, "button", (b) => b.getAttribute("aria-haspopup") === "menu"));
    if (row.querySelector("button[aria-haspopup='menu']") && shown(row)) {
      out.push(...analysisEntries().map(([label, open]): Command => ({ id: `analyze.${slug(label)}`, group: "Analyze", title: label, run: open })));
    }
  }
  out.push(...buttonsOf("Steps", document, ".steps-strip button", (b) => b.classList.contains("steps-count")));
  // Tabs: where to go, what to open, and the table in front.
  out.push(
    { id: "tabs.visualizations", group: "Tabs", title: "Go to Visualizations", run: () => showAgentView() },
    { id: "tabs.erd", group: "Tabs", title: "Go to ERD", run: () => showErdView() },
    { id: "tabs.workbench", group: "Tabs", title: "Open the Workbench", run: () => openWorkbench() },
    ...gridList().map(({ id, label }): Command => ({ id: `tabs.go.${id}`, group: "Tabs", title: `Go to ${label}`, run: () => { showGridView(); void activateGrid(id); } })),
    ...buttonsOf("Tabs", document, ".tabs-row > button"),
  );
  if (active) {
    const many = gridList().length > 1;
    out.push(
      { id: "tabs.compare-with", group: "Tabs", title: `Compare ${active.dataset} with…`, when: () => many, whyNot: "Open another table to compare with", run: () => compareWith(active.id) },
      { id: "tabs.rename", group: "Tabs", title: `Rename ${active.dataset}`, keys: "F2", run: () => { showGridView(); renameActive(); } },
      { id: "tabs.close", group: "Tabs", title: `Close ${active.dataset}`, keys: "Delete", run: () => void closeGrid(active.id) },
    );
  }
  // The cell in front: what its right-click menu offers.
  if (onGrid && active) {
    const cell = focusedCell();
    out.push(...cellCommands().map(([title, run]): Command => ({ id: `cell.${slug(title)}`, group: "Cell", title, keys: KEYS[`Cell: ${title}`], when: () => cell !== null, whyNot: "Click a cell first", run })));
  }
  return out;
}

/** Ctrl+Shift+P opens the palette, wherever the cursor is. */
export function mountGridCommands(): void {
  setCommandSource(commands);
  document.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || !event.shiftKey || event.altKey || event.key.toLowerCase() !== "p") return;
    event.preventDefault();
    // A menu left open would sit over the palette.
    document.querySelector(".menu")?.remove();
    openPalette();
  });
}
