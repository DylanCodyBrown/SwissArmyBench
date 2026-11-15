/**
 * stepsStrip.ts: the grid's steps in one line under its title (plan decision 13). [VIEW]
 *
 * The Table Transformations panel and the SQL box left the grid page, which gives the grid the whole
 * page. The ribbon adds steps. This strip says how many are on (a sort made by clicking a header
 * is one of them) and offers:
 *   [N STEPS]  hover, focus or click: the steps in plain words, each with a remove × -> stepOp(delete)
 *   Undo (Ctrl+Z) · Redo (Ctrl+Y) · Clear · Edit steps (the full panel, in a tab of its own).
 * Undo takes back the last change to the steps, whatever it was (a step added, removed or edited,
 * the steps cleared, a header sort); Redo makes it again. The keys work while the grid is in front
 * and the cursor is not in a text box or an editor.
 *
 * The steps as code are the table's own read-only cell in the Workbench (docs/ideas.md, 2026-11-14):
 * Copy as SQL and Copy as Python left this strip (the steps window's Code tab has them).
 */
import { api, token } from "./api";
import { button, clear, h, icon, toast } from "./dom";
import { state } from "./state";
import type { GridInfo } from "./api";

let host: HTMLElement;

function openStepsWindow(): void {
  const info = state.info;
  if (!info) return;
  const page = `/g/${encodeURIComponent(info.grid)}`;
  const opened = window.open(`${page}?panel=steps#token=${encodeURIComponent(token)}`, `steps-${page}`, "width=440,height=820");
  if (!opened) toast("The browser blocked the steps window.", "error");
}

function render(): void {
  const info = state.info;
  if (!info) {
    clear(host);
    return;
  }
  // Every step that is on, a header sort among them: it changes what the grid shows like any other.
  const on = info.steps.filter((s) => s.enabled !== false);
  // No words when there are none (principle 7.9): a count of zero is not something to act on.
  const label = on.length === 0 ? "" : on.length === 1 ? "1 step" : `${on.length} steps`;
  // Opened from a connection with fewer rows than it holds: said plainly, beside the table, with the rest
  // one click away (the owner's call, 2026-11-14).
  const opened = info.opened;
  const loadAll = async (): Promise<void> => {
    if (!opened) return;
    toast(`Loading every row of ${opened.table}…`);
    try {
      const where = { database: opened.database, schema: opened.schema, table: opened.table, all: true };
      await api(`/connections/${encodeURIComponent(opened.connection)}/open`, "POST", where);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };
  clear(
    host,
    opened
      ? h(
          "span",
          { class: "opened-note", role: "status" },
          `First ${opened.shown.toLocaleString()} of ${opened.total.toLocaleString()} rows`,
          button("Load all rows", () => void loadAll(), { icon: "import", class: "ghost" }),
        )
      : null,
    label ? stepsCount(label, info.steps) : null,
    info.step_error ? h("span", { class: "status-error" }, `Step ${info.step_error.index + 1}: ${info.step_error.message}`) : null,
    disabledUnless(info.can_undo, button("Undo", () => void state.undo().catch(failed), { icon: "back", iconOnly: true, class: "ghost", title: info.can_undo ? "Undo the last step change (Ctrl+Z)" : "Nothing to undo" })),
    disabledUnless(info.can_redo, button("Redo", () => void state.redo().catch(failed), { icon: "forward", iconOnly: true, class: "ghost", title: info.can_redo ? "Redo (Ctrl+Y)" : "Nothing to redo" })),
    disabledUnless(info.steps.length > 0, button("Clear the steps", () => void state.saveSteps([]).catch(failed), { icon: "trash", iconOnly: true, class: "ghost" })),
    button("Edit steps", openStepsWindow, { icon: "steps", class: "ghost" }),
  );
}

const failed = (e: Error): void => toast(e.message, "error");

function disabledUnless(usable: boolean | undefined, btn: HTMLButtonElement): HTMLButtonElement {
  btn.disabled = !usable;
  return btn;
}

/** "3 steps": hovering it, focusing it or clicking it lists the steps in plain words, each with a
 * remove ×. The list stays while the pointer or the focus is on the count or inside the list. */
function stepsCount(label: string, steps: GridInfo["steps"]): HTMLElement {
  const list = h(
    "ol",
    { class: "steps-list", role: "list", "aria-label": "Steps", hidden: true },
    ...steps.map((s) =>
      h(
        "li",
        { class: s.enabled === false ? "off" : "" },
        h("span", { class: "steps-words" }, `${s.description ?? s.kind}${s.enabled === false ? " (off)" : ""}`),
        button(`Remove: ${s.description ?? s.kind}`, () => void state.stepOp({ op: "delete", id: s.id }).catch(failed), { icon: "close", iconOnly: true, class: "ghost small" }),
      ),
    ),
  );
  const count = h("button", { type: "button", class: "steps-count", "aria-haspopup": "true", "aria-expanded": "false" }, label, h("span", { class: "menu-caret", "aria-hidden": "true" }, icon("down")));
  const wrap = h("span", { class: "steps-hover" }, count, list);
  let closing = 0;
  const show = (on: boolean): void => {
    window.clearTimeout(closing);
    if (on) {
      list.hidden = false;
      count.setAttribute("aria-expanded", "true");
    } else {
      // A moment's grace: the pointer crossing from the count to the list must not close it.
      closing = window.setTimeout(() => {
        list.hidden = true;
        count.setAttribute("aria-expanded", "false");
      }, 250);
    }
  };
  wrap.addEventListener("mouseenter", () => show(true));
  wrap.addEventListener("mouseleave", () => show(false));
  wrap.addEventListener("focusin", () => show(true));
  wrap.addEventListener("focusout", (e) => { if (!wrap.contains(e.relatedTarget as Node | null)) show(false); });
  wrap.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || list.hidden) return;
    e.stopPropagation();
    window.clearTimeout(closing);
    list.hidden = true;
    count.setAttribute("aria-expanded", "false");
  });
  return wrap;
}

/** Ctrl+Z, Ctrl+Y and Ctrl+Shift+Z: undo and redo the grid's steps, unless the keys belong to
 * something else: a text box, an editor, a dialog, or a tab that is not a grid. */
function onUndoKeys(event: KeyboardEvent): void {
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
  const key = event.key.toLowerCase();
  const redo = key === "y" || (key === "z" && event.shiftKey);
  if (!redo && key !== "z") return;
  const target = event.target instanceof Element ? event.target : null;
  if (target?.closest("input, textarea, select, [contenteditable], .monaco-editor")) return;
  if (document.querySelector("dialog[open]") || document.body.classList.contains("agent-view") || !state.info) return;
  event.preventDefault();
  void (redo ? state.redo() : state.undo()).catch(failed);
}

export function mountStepsStrip(element: HTMLElement): void {
  host = element;
  host.classList.add("steps-strip");
  host.setAttribute("role", "group");
  host.setAttribute("aria-label", "Steps");
  state.on("info", render);
  document.addEventListener("keydown", onUndoKeys);
}
