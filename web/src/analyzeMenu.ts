/**
 * analyzeMenu.ts: the Table row's Analyze menu, and the actions every analysis result shares
 * (Plans/analyze-menu.plan.md).
 *
 *   [ANALYZE ▾]        Odds, Fit test, Find predictors, Outliers: each opens its form, filled from the
 *                      selected columns (analysisDialog.ts), else from formDefaults(): never an
 *                      identifier column
 *   [SEND TO SANDBOX]  a report-style note and its chart, side by side (analysisCards.ts; POST cards).
 *                      The window stays open; the toast's Show closes it and goes to the card
 *                      (sandboxShow.ts)
 *   [OPEN AS GRID]     a tabular result as a new grid (PUT /datasets/{name}?new_grid=1, JSON rows);
 *                      the window closes and the new tab is in front
 *   [COPY CODE]        the analysis as Python for a notebook: POST /grids/{id}/analysis-code, then
 *                      copied to the clipboard, imports first
 */
import { api, grid } from "./api";
import { analysisBlades, openBladesPage, runBladeAnalysis } from "./bladeAnalysis";
import type { SandboxCard } from "./analysisCards";
import { button, closeDialogs, h, icon, toast } from "./dom";
import { sentToast } from "./sandboxShow";
import { state } from "./state";
import { busyClick } from "./loading";
import { errorHere } from "./errorNote";

export interface ResultActions {
  /** The analysis's name for the server (odds, predictors, outliers, fit_test) and the request it ran. */
  analysis: string;
  body: Record<string, unknown>;
  /** The result as Visualizations cards: a report-style note and its chart (analysisCards.ts). */
  cards: () => SandboxCard[];
  /** The result as rows, for a new grid (and the name to give it). */
  rows?: () => { name: string; rows: Record<string, unknown>[] };
  /** The result as the server sent it, for Show the math (its proof is worked from these numbers). */
  result?: () => unknown;
}

/** The menu's entries: [icon, label, open]. analysisDialog.ts fills it, to keep the imports one-way. */
const entries: [string, string, () => void][] = [];

export function registerAnalysis(iconName: string, label: string, open: () => void): void {
  entries.push([iconName, label, open]);
}

/** The menu's built-in entries as [label, open], for the command palette (gridCommands.ts). */
export function analysisEntries(): [string, () => void][] {
  return entries.map(([, label, open]) => [label, open]);
}

export function analyzeButton(): HTMLButtonElement {
  const btn = button("Analyze", (event) => openMenu(event), {
    icon: "fit",
    class: "ribbon-btn",
  });
  btn.setAttribute("aria-haspopup", "menu");
  btn.append(h("span", { class: "menu-caret", "aria-hidden": "true" }, "▾"));
  return btn;
}

function openMenu(event: MouseEvent): void {
  document.querySelector(".menu")?.remove();
  const anchor = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const menu = h(
    "div",
    { class: "menu", role: "menu", "aria-label": "Analyze" },
    ...entries.map(([name, label, run]) =>
      h("button", { type: "button", role: "menuitem", onclick: () => { menu.remove(); run(); } }, icon(name), label),
    ),
  );
  document.body.append(menu);
  menu.style.top = `${anchor.bottom + 4}px`;
  menu.style.left = `${Math.min(anchor.left, window.innerWidth - menu.offsetWidth - 8)}px`;
  (menu.querySelector("button") as HTMLButtonElement | null)?.focus();
  // Your own analyses (analysis blades), under the built-in ones.
  void analysisBlades().then((mine) => {
    if (!menu.isConnected) return;
    menu.append(
      h("div", { class: "menu-rule", role: "separator" }),
      h("div", { class: "menu-label" }, "Your analyses"),
      ...mine.map((blade) => h("button", { type: "button", role: "menuitem", title: blade.description || blade.name, onclick: () => { menu.remove(); void runBladeAnalysis(blade); } }, icon("cog"), blade.name)),
      h("button", { type: "button", role: "menuitem", onclick: () => { menu.remove(); openBladesPage(); } }, icon("plus"), mine.length ? "Make another…" : "Make your own…"),
    );
  });
  setTimeout(() =>
    document.addEventListener("click", function away(e) {
      if (!menu.contains(e.target as Node)) {
        menu.remove();
        document.removeEventListener("click", away);
      }
    }),
  );
  menu.addEventListener("keydown", (e) => {
    const items = [...menu.querySelectorAll<HTMLButtonElement>("button")];
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "Escape") menu.remove();
    else if (e.key === "ArrowDown") items[(at + 1) % items.length]?.focus();
    else if (e.key === "ArrowUp") items[(at - 1 + items.length) % items.length]?.focus();
    else return;
    e.preventDefault();
  });
}

/** A name a grid (and a Python variable) can carry: letters, digits and underscores. */
export function tableName(...parts: string[]): string {
  return parts.map((p) => p.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "")).filter(Boolean).join("_") || "result";
}

/** The buttons under a result: Send to Visualizations, Open as grid (when it has rows), Copy code. */
export function resultButtons(actions: ResultActions): HTMLButtonElement[] {
  const out = [
    button("Send to Visualizations", () => void toSandbox(actions), { icon: "image" }),
  ];
  if (actions.rows) out.push(button("Open as grid", busyClick("Opening…", () => toGrid(actions)), { icon: "rows" }));
  if (actions.result) {
    const result = actions.result;
    out.push(button("Show the math", () => void showTheMath(actions.analysis, result()), { icon: "steps", title: "Step by step, to Visualizations" }));
  }
  out.push(button("Copy code", () => void copyCode(actions), { icon: "copy", title: "This analysis as Python, for a notebook" }));
  return out;
}

/** The proof of a result (domain/proofs.py), as a note in Visualizations beside the result's cards. */
export async function showTheMath(analysis: string, result: unknown): Promise<void> {
  try {
    const proof = await api<{ title: string; markdown: string }>("/analysis-proof", "POST", { analysis, result, dataset: datasetName() });
    const made = await api(`${grid}/cards`, "POST", { kind: "note", title: proof.title, body: proof.markdown, size: { w: 8, h: 14 } });
    sentToast("In Visualizations: the math, step by step.", made);
  } catch (e) {
    errorHere(e);
  }
}

/** Add cards to Visualizations, filed with the grid in front; says what arrived, with Show (the
 * window it was sent from stays open). */
export async function sendCards(cards: SandboxCard[]): Promise<void> {
  try {
    let first: unknown;
    // Each card is sent; the first is the one Show goes to. (`first ??= await api(...)` sent only the
    // note: ??= does not run its right side once `first` is set, so the chart never arrived.)
    for (const card of cards) {
      const made = await api(`${grid}/cards`, "POST", card);
      first ??= made;
    }
    sentToast(`In Visualizations: ${cards.length === 1 ? "a note" : "a note and its chart"}.`, first);
  } catch (e) {
    errorHere(e);
  }
}

async function toSandbox(actions: ResultActions): Promise<void> {
  try {
    await sendCards(actions.cards());
  } catch (e) {
    errorHere(e);
  }
}

async function toGrid(actions: ResultActions): Promise<void> {
  if (!actions.rows) return;
  const { name, rows } = actions.rows();
  if (!rows.length) {
    toast("Nothing to put in a grid.");
    return;
  }
  try {
    // The JSON push takes pandas' "split" shape: the column names, then each row's values in order.
    const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
    const data = rows.map((row) => columns.map((c) => row[c] ?? null));
    await api(`/datasets/${encodeURIComponent(name)}?new_grid=1`, "PUT", { columns, data });
    // The new table arrives as a tab in front (the server's grid_shown notice): the window it came
    // from closes, so the tab is what the user sees.
    closeDialogs();
    toast(`Opened as ${name}.`);
  } catch (e) {
    errorHere(e);
  }
}

/** The analysis as one cell of Python (its imports first), on the clipboard. */
async function copyCode(actions: ResultActions): Promise<void> {
  try {
    const made = await api<{ code: string; imports: string[] }>(`${grid}/analysis-code`, "POST", { analysis: actions.analysis, body: actions.body });
    const text = made.imports.length ? [...made.imports, "", made.code].join("\n") : made.code;
    await navigator.clipboard.writeText(text).then(
      () => toast("Copied."),
      () => errorHere("The browser blocked the clipboard."),
    );
  } catch (e) {
    errorHere(e);
  }
}

/** What the forms start on in this view (GET analysis-defaults; the rule is domain/analysis.py's). */
export interface FormDefaults {
  /** Identifier columns: by name, or every row a different whole number or text. */
  identifiers: string[];
  /** The first number column that is not an identifier. */
  number: string | null;
  /** The column a form with any column starts on. */
  column: string | null;
  /** A regression's starting predictors: every column but the identifiers. */
  predictors: string[];
}

/** Never an identifier as a default. If the server cannot say, the forms start as they did before. */
export async function formDefaults(): Promise<FormDefaults> {
  try {
    return await api<FormDefaults>(`${grid}/analysis-defaults`);
  } catch {
    const columns = state.info?.columns ?? [];
    return { identifiers: [], number: null, column: columns[0]?.name ?? null, predictors: columns.map((c) => c.name) };
  }
}

/** The dataset this grid shows, for naming result grids. */
export function datasetName(): string {
  return state.info?.dataset ?? "table";
}
