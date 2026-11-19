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
import { analysisEntries } from "./analyzePage";
import { betaCommands } from "./betaNotes";
import { updateCommands } from "./updates";
import { claudeCommands } from "./claudeLaunch";
import { cellCommands } from "./cellMenu";
import { focusedCell } from "./gridView";
import { activateGrid, activeContext, closeDraft, closeGrid, compareWith, currentView, gridList, newQueryTab, openWorkbench, renameActive, showAgentView, showErdView, showGridView } from "./panes";
import { appKey, closeWindow, inApp } from "./desktopApp";
import { setGridZoom } from "./theme";
import { api } from "./api";
import { mountExplorer } from "./dataExplorer";
import { openData } from "./dataPage";
import { button, openDialog, toast } from "./dom";
import { openVariables } from "./variablesPage";
import { openPalette, setCommandSource, type Command } from "./workbenchCommands";
import { errorHere } from "./errorNote";

/** The keys the page already has, shown beside the command they run. */
const KEYS: Record<string, string> = {
  // The desktop app's (desktopApp.ts): the browser's keys are the app's there.
  ...(inApp() ? { "Tabs: New table from a query": "Ctrl+T" } : {}),
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
  out.push({ id: "application.find-data", group: "Application", title: "Find data…", keys: "Ctrl+K", run: () => openFindData() });
  out.push(...betaCommands()); // beta mode on or off, Leave a note…, Export beta log…
  out.push(...updateCommands()); // Update to X, What's new
  out.push(...claudeCommands()); // Launch Claude
  // The ribbon's rows, each under its own name; the Analyze button is its menu's entries.
  for (const row of document.querySelectorAll<HTMLElement>(".ribbon .ribbon-group")) {
    const name = row.querySelector(".ribbon-caption strong")?.textContent?.trim() ?? "Table";
    out.push(...buttonsOf(name, row, "button", (b) => b.getAttribute("aria-haspopup") === "menu"));
  }
  out.push(...buttonsOf("Steps", document, ".steps-strip button", (b) => b.classList.contains("steps-count")));
  // The Analyze page's analyses, from its own list (8.3: one list feeds the toolbar, the palette, the agent).
  out.push(...analysisEntries().map(([label, open]): Command => ({ id: `analyze.${slug(label)}`, group: "Analyze", title: label, run: open })));
  // Tabs: where to go, what to open, and the table in front.
  out.push(
    { id: "tabs.analyze", group: "Tabs", title: "Go to Analyze", run: () => showAgentView() },
    { id: "tabs.erd", group: "Tabs", title: "Go to ERD", run: () => showErdView() },
    { id: "tabs.workbench", group: "Tabs", title: "Open the Workbench", run: () => openWorkbench() },
    ...gridList().map(({ id, label }): Command => ({ id: `tabs.go.${id}`, group: "Tabs", title: `Go to ${label}`, run: () => { showGridView(); void activateGrid(id); } })),
    ...buttonsOf("Tabs", document, ".tabs-row > button"),
  );
  out.push(...tabKeys());
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

// ===== the browser's keys, the app's (desktopApp.ts): Ctrl+W, Ctrl+T, Ctrl+N, Ctrl+Tab, Ctrl+Shift+T =====

/** Ctrl+W: the tab in front closes (a table's, the query draft); on the Analyze board or the ERD the grids come
 *  back; with no tab left, false: the window closes (the shell's own Ctrl+W). */
function closeTab(): boolean {
  const view = currentView();
  const active = activeContext();
  if (view === "grid" && active) {
    void closeGrid(active.id);
    return true;
  }
  if (view === "query") {
    closeDraft();
    return true;
  }
  if (gridList().length && view !== "grid") {
    showGridView();
    return true;
  }
  return false;
}

/** Ctrl+Tab and Ctrl+Shift+Tab: the next or previous table, round the tab row. */
function cycleTabs(by: number): void {
  const list = gridList();
  if (!list.length) return;
  const at = list.findIndex((g) => g.id === activeContext()?.id);
  const next = list[(Math.max(at, 0) + by + list.length) % list.length];
  showGridView();
  if (next) void activateGrid(next.id);
}

/** Ctrl+Shift+T (tabs_reopen): the last closed table again, its steps kept; its tab arrives by the server's
 *  grid_shown. */
export async function reopenTab(): Promise<void> {
  try {
    await api("/grids/reopen", "POST");
  } catch (e) {
    if ((e as { status?: number }).status === 404) toast("No closed table to reopen.");
    else errorHere(e);
  }
}

function tabKeys(): Command[] {
  const keys = (k: string): string | undefined => (inApp() ? k : undefined);
  return [
    { id: "tabs.closeTab", group: "Tabs", title: "Close the tab", keys: keys("Ctrl+W"), when: () => gridList().length > 0 || currentView() === "query", whyNot: "no tab is open", run: () => void closeTab() },
    { id: "tabs.next", group: "Tabs", title: "Next tab", keys: keys("Ctrl+Tab"), when: () => gridList().length > 1, whyNot: "one table or none is open", run: () => cycleTabs(1) },
    { id: "tabs.previous", group: "Tabs", title: "Previous tab", keys: keys("Ctrl+Shift+Tab"), when: () => gridList().length > 1, whyNot: "one table or none is open", run: () => cycleTabs(-1) },
    { id: "tabs.reopen", group: "Tabs", title: "Reopen the last closed tab", keys: keys("Ctrl+Shift+T"), run: () => reopenTab() },
  ];
}

/** In the desktop app only: the browser's keys, the app's. In a browser they stay the browser's. */
function mountAppKeys(): void {
  if (!inApp()) return;
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented) return;
    const key = appKey(event);
    if (key === "Ctrl+W") {
      // No tab left: the window closes (its page asked first, as its close button would).
      event.preventDefault();
      if (!closeTab()) closeWindow();
      return;
    }
    const run: Record<string, () => void> = {
      "Ctrl+T": () => void newQueryTab(),
      "Ctrl+N": () => void newQueryTab(),
      "Ctrl+Tab": () => cycleTabs(1),
      "Ctrl+Shift+Tab": () => cycleTabs(-1),
      "Ctrl+Shift+T": () => void reopenTab(),
    };
    const action = run[key];
    if (!action) return;
    event.preventDefault();
    document.querySelector(".menu")?.remove();
    action();
  });
}

/** Find data… (Ctrl+K): the Data Explorer's search in a dialog over the grids (dataExplorer.ts, the same
 *  component as the Workbench's pane), so finding data does not need the Workbench. Insert goes into the
 *  Workbench's selected cell; Open the Data Explorer opens its window with the same search. */
export function openFindData(): void {
  if (document.querySelector("dialog.find-data[open]")) return;
  const { dialog, body, foot, close } = openDialog("Find data", true);
  dialog.classList.add("find-data");
  const explorer = mountExplorer({
    insert: async (r) => {
      const got = await api<{ result: { document: string; cell: number | null } }>("/workbench/window", "POST", { command: "explorer.insert", args: { insert: r.insert, name: r.name } });
      return got.result.cell ? `cell ${got.result.cell} of ${got.result.document}` : got.result.document;
    },
    target: () => "the Workbench's selected cell",
    showGrid: (grid) => {
      close();
      showGridView();
      void activateGrid(grid);
    },
    openVariable: () => {
      close();
      openVariables();
    },
  });
  body.append(explorer.element);
  foot.append(
    button("Open the Data page", () => {
      const state = explorer.state();
      close();
      openData(state);
    }, { icon: "data", class: "line", title: "The Data page, with this search" }),
  );
  explorer.focus();
}

/** Ctrl+Shift+P opens the palette, wherever the cursor is; Ctrl+K, Find data. */
export function mountGridCommands(): void {
  setCommandSource(commands);
  mountAppKeys();
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      document.querySelector(".menu")?.remove();
      openFindData();
      return;
    }
    if (!(event.ctrlKey || event.metaKey) || !event.shiftKey || event.altKey || event.key.toLowerCase() !== "p") return;
    event.preventDefault();
    // A menu left open would sit over the palette.
    document.querySelector(".menu")?.remove();
    openPalette();
  });
}
