/**
 * environmentColumns.ts: the Environment's columns, each tab its own (a column hides from its heading's menu,
 * kept per tab; the Workbench's pane keeps the compact ones), and the columns menu. Pulled out of
 * environmentPage.ts's mountEnvironment (the craft review of 2026-11-22, refactor 8). [VIEW]
 */
import { h, icon, plural, remember } from "./dom";
import { pin, update } from "./environmentActions";
import { select } from "./environmentMoves";
import type { Item, Kind } from "./environmentRules";
import { type Column, type Environment, hidden, hiddenKey, marked } from "./environmentState";
import { openMenu, type MenuEntry } from "./workbenchMenu";

/** Every tab's columns, drawn from the state record (the search marks, a shown secret, the index checked). */
export function columns(env: Environment): Record<Kind, Column[]> {
  const text = (cls: string, words: string): HTMLElement => h("span", { class: cls }, marked(words, env.query));
  const usedCell = (item: Item, none: string): HTMLElement =>
    item.used.length
      ? h("span", { class: "env-from" }, h("button", { type: "button", class: "env-link", "data-used": item.id, onclick: (e: MouseEvent) => (e.stopPropagation(), select(env, item.id, true)) }, plural(item.used.length, "place")))
      : h("span", { class: "env-from env-none" }, none);
  return {
    table: [
      { head: "Rows by columns", width: "130px", compact: true, cell: (it) => h("span", { class: "env-size" }, it.size) },
      { head: "Columns", width: "minmax(160px,2fr)", cell: (it) => text("env-val", it.value) },
      { head: "Grids", width: "110px", cell: (it) => h("span", { class: "env-from" }, it.grids.length ? h("span", { class: "env-tag env-tag-grid", title: "A grid is a view of this table, never a copy" }, `In ${plural(it.grids.length, "grid")}`) : h("span", { class: "env-none" }, "no grid")) },
      { head: "Used in", width: "110px", compact: true, cell: (it) => usedCell(it, "not used yet") },
      { head: "From", width: "minmax(130px,1fr)", cell: (it) => text("env-from", it.from) },
    ],
    variable: [
      { head: "Type", width: "110px", compact: true, cell: (it) => text("env-type", it.type) },
      { head: "Value", width: "minmax(200px,2.4fr)", compact: true, cell: (it) => text("env-val", it.value) },
      { head: "Used in", width: "110px", cell: (it) => usedCell(it, "not used yet") },
      { head: "From", width: "minmax(130px,1fr)", cell: (it) => text("env-from", it.from) },
    ],
    structure: [
      { head: "Format", width: "110px", compact: true, cell: (it) => text("env-type", it.type) },
      { head: "Size", width: "130px", compact: true, cell: (it) => h("span", { class: "env-size" }, it.size) },
      { head: "Paths", width: "minmax(180px,2fr)", cell: (it) => text("env-val", it.value) },
      { head: "Used in", width: "110px", cell: (it) => usedCell(it, "not used yet") },
      { head: "File", width: "minmax(150px,1fr)", cell: (it) => text("env-from", it.from) },
    ],
    setting: [
      { head: "Kind", width: "80px", compact: true, cell: (it) => h("span", { class: "env-type" }, it.type) },
      { head: "Value", width: "minmax(160px,1.4fr)", compact: true, cell: (it) => (env.revealed.has(it.id) ? h("span", { class: "env-val env-shown" }, env.revealed.get(it.id) ?? "") : text("env-val", it.value)) },
      { head: "Comes from", width: "minmax(180px,1.6fr)", cell: (it) => text("env-from", it.from) },
      { head: "Used in", width: "110px", cell: (it) => usedCell(it, "not used yet") },
    ],
    library: [
      {
        head: "Pinned",
        width: "86px",
        cell: (it) =>
          it.installed
            ? h(
                "button",
                {
                  type: "button",
                  class: `env-pin${it.pinned ? " on" : ""}`,
                  "data-pin": it.name,
                  "aria-pressed": String(Boolean(it.pinned)),
                  title: it.pinned
                    ? `Pinned to ${it.version} in requirements.txt: click to let it update`
                    : `Not pinned: click to keep it at ${it.version}`,
                  onclick: (e: MouseEvent) => (e.stopPropagation(), void pin(env, it, !it.pinned)),
                },
                it.pinned ? icon("pin") : null,
                it.pinned ? "Pinned" : "Pin",
              )
            : h("span", { class: "env-none" }, ""),
      },
      {
        head: "Version",
        width: "170px",
        compact: true,
        cell: (it) =>
          h(
            "span",
            { class: "env-type" },
            it.version || "not installed",
            it.latest
              ? h("button", { type: "button", class: "env-update", "data-update": it.name, title: `Update to ${it.latest}`, onclick: (e: MouseEvent) => (e.stopPropagation(), update(env, it)) }, `→ ${it.latest}`)
              : it.installed && env.listing?.checked
                ? h("span", { class: "env-latest" }, "latest")
                : null,
          ),
      },
      { head: "What it is for", width: "minmax(140px,1.4fr)", cell: (it) => text("env-from", it.value) },
      { head: "Imported in", width: "110px", compact: true, cell: (it) => usedCell(it, "not imported yet") },
    ],
  };
}

/** The tab's columns as shown: the pane's compact ones, less those its heading's menu hid. */
export function shownColumns(env: Environment, kind: Kind): Column[] {
  const off = hidden(kind);
  return columns(env)[kind].filter((c) => (!env.compact || c.compact) && !off.has(c.head));
}

/** The heading's menu: each column of the tab, ticked while shown. */
export function columnsMenu(env: Environment, anchor: HTMLElement): void {
  if (env.compact) return;
  const off = hidden(env.tab);
  const entries: MenuEntry[] = columns(env)[env.tab].map((c) => ({
    label: c.head,
    icon: off.has(c.head) ? undefined : "check",
    run: () => {
      if (off.has(c.head)) off.delete(c.head);
      else off.add(c.head);
      remember(hiddenKey(env.tab), [...off].join("|"));
      env.act.draw();
    },
  }));
  openMenu(anchor, "Columns", [{ label: "Columns", heading: true }, ...entries], { align: "right" });
}
