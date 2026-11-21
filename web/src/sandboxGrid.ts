/**
 * sandboxGrid.ts: a sandbox table's grid (services/sandbox.py; the owner approved "Edit sandbox rows in a grid" and
 * "any grid table or structure can become a sandbox variant and should get its own designation", 2026-11-21).
 *
 *   [BAR]    above a sandbox grid (sandbox_<table>): the Sandbox badge, its designation ("orders · sandbox") and
 *            origin ("A sandbox variant of orders (Warehouse), copied …"), "Local test data", then Add row,
 *            Delete rows (the selected rows) and Reset <table>
 *   [EDIT]   double-click, Enter or F2 on a cell: a box over the cell; Enter writes it (POST /sandbox/edit: a
 *            sandbox write, counted in the change log; Reset undoes it); a value its column's type refuses is
 *            said under the box, which stays open; Esc leaves it
 *   [TITLE]  the tab's words: its designation (sandboxTitle)
 *
 * ROUTING: GET /sandbox · POST /sandbox/edit, /sandbox/reset
 */
import { api, onNotice } from "./api";
import { button, h, icon, openDialog } from "./dom";
import { errorHere, errorNote } from "./errorNote";
import { busyClick } from "./loading";
import { registerCellEditor, selection } from "./gridView";
import type { SandboxState, SandboxTable } from "./dataSandbox";

const PREFIX = "sandbox_";
let known: Map<string, SandboxTable> = new Map();
let reading: Promise<void> | null = null;
const listeners: (() => void)[] = [];

async function read(): Promise<void> {
  try {
    const got = await api<SandboxState>("/sandbox");
    known = new Map(got.tables.map((t) => [`${PREFIX}${t.name}`, t]));
  } catch {
    known = new Map();
  }
  for (const l of listeners) l();
}

function ensure(): Promise<void> {
  reading ??= read();
  return reading;
}

onNotice((n) => {
  if (n.type !== "sandbox_changed" && n.type !== "project_changed") return;
  reading = read();
});

/** A grid's dataset is a sandbox table's (its table, else null). */
export const sandboxTable = (dataset: string): SandboxTable | null => known.get(dataset) ?? null;

/** The tab's words for a sandbox grid: its designation, else its dataset's name. */
export function sandboxTitle(dataset: string): string {
  if (!dataset.startsWith(PREFIX)) return dataset;
  void ensure();
  return known.get(dataset)?.title ?? dataset;
}

/** Called when what is known of the sandbox changes (a tab's words follow). */
export function onSandboxKnown(listener: () => void): void {
  listeners.push(listener);
}

/** The bar above a sandbox grid; nothing for any other grid. */
export function drawSandboxBar(slot: HTMLElement, dataset: string): void {
  if (!dataset.startsWith(PREFIX)) return;
  const draw = (): void => {
    const t = known.get(dataset);
    if (!t) {
      slot.replaceChildren();
      return;
    }
    slot.replaceChildren(
      h("div", { class: "sandbox-bar", role: "group", "aria-label": `Sandbox table ${t.name}`, "data-connections": "Sandbox" },
        h("span", { class: "sandbox-badge" }, icon(t.variant ? "branch" : "sandbox"), "Sandbox"),
        h("strong", { class: "sandbox-designation" }, t.title),
        h("span", { class: "sandbox-origin muted" }, t.origin_words || t.source_words),
        h("span", { class: "sandbox-live muted" }, "Local test data, never live"),
        h("span", { class: "spacer" }),
        button("Add row", () => addRow(t), { icon: "plus" }),
        button("Delete rows", busyClick("Deleting…", (b) => deleteRows(t, b)), { icon: "trash", title: "Delete the selected rows from the sandbox table" }),
        button(`Reset ${t.name}`, busyClick("Resetting…", async (b) => {
          try {
            await api("/sandbox/reset", "POST", { table: t.name });
          } catch (e) {
            errorHere(e, {}, b);
          }
        }), { icon: "reset", title: `Put ${t.name} back to the baseline` }),
      ),
    );
  };
  listeners.push(() => {
    if (slot.isConnected || !slot.childElementCount) draw();
  });
  void ensure().then(draw);
}

async function deleteRows(t: SandboxTable, b: HTMLElement): Promise<void> {
  const rows: number[] = [];
  for (const [first, last] of selection.kind === "rows" || selection.kind === "cells" ? selection.rows : []) for (let r = first; r <= last && rows.length < 500; r++) rows.push(r);
  if (!rows.length) {
    errorHere("Select the rows to delete first (their numbers at the left).", {}, b);
    return;
  }
  try {
    await api("/sandbox/edit", "POST", { table: t.name, op: "delete", rows });
    selection.clear();
  } catch (e) {
    errorHere(e, {}, b);
  }
}

function addRow(t: SandboxTable): void {
  const { body, foot, close } = openDialog(`Add a row to ${t.name}`);
  const boxes = t.columns.map((c) => {
    const input = h("input", { "aria-label": c.name, placeholder: c.type, spellcheck: false, "data-column": c.name }) as HTMLInputElement;
    body.append(h("label", { class: "field" }, h("span", {}, c.name, h("span", { class: "muted" }, ` ${c.type}${c.key ? " · key" : ""}`)), input));
    return input;
  });
  foot.append(
    button("Cancel", () => close()),
    button("Add", busyClick("Adding…", async (b) => {
      const values: Record<string, string> = {};
      for (const box of boxes) if (box.value !== "") values[box.dataset.column!] = box.value;
      try {
        await api("/sandbox/edit", "POST", { table: t.name, op: "insert", values });
        close();
      } catch (e) {
        errorHere(e, {}, b);
      }
    }), { class: "primary" }),
  );
  boxes[0]?.focus();
}

/** A sandbox grid's cell edited in place (gridView.ts asks first: true when it took the cell). */
export function editSandboxCell(dataset: string, row: number, column: string, cell: HTMLElement, current: () => Promise<unknown>): boolean {
  const t = known.get(dataset);
  if (!t || !t.columns.some((c) => c.name === column)) return false;
  document.querySelector(".sandbox-cell-edit")?.remove();
  const at = cell.getBoundingClientRect();
  const input = h("input", { class: "sandbox-cell-input", "aria-label": `${column}, row ${row + 1}`, spellcheck: false, "data-no-variables": "" }) as HTMLInputElement;
  const box = h("div", { class: "sandbox-cell-edit", style: `left:${at.left}px;top:${at.top}px;min-width:${Math.max(at.width, 140)}px` }, input);
  document.body.append(box);
  void current().then((v) => {
    input.value = v === null || v === undefined ? "" : String(v);
    input.select();
  });
  input.focus();
  let sending = false;
  const leave = (): void => {
    box.remove();
    cell.focus();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      leave();
    } else if (e.key === "Enter" && !sending) {
      e.preventDefault();
      sending = true;
      void api("/sandbox/edit", "POST", { table: t.name, op: "update", row, column, value: input.value }).then(
        () => leave(),
        (err: unknown) => {
          sending = false;
          // In place: under the box, which stays open with what was typed (9.5).
          box.querySelector(".error-note")?.remove();
          box.append(errorNote(err, { agent: false }));
          input.focus();
        },
      );
    }
    e.stopPropagation();
  });
  input.addEventListener("blur", () => {
    window.setTimeout(() => {
      if (!sending && box.isConnected && !box.contains(document.activeElement) && !document.querySelector(".error-note:hover")) box.remove();
    }, 200);
  });
  return true;
}

registerCellEditor(editSandboxCell);
