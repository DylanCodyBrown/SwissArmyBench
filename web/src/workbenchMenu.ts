/**
 * workbenchMenu.ts: the Workbench's drop-down menus (the top bar's "…", a group's "+ Cell" and "…",
 * the status bar's kernel menu, the Data panel's "+ Table"). [FUNCTION]
 *
 *   one menu at a time; the arrow keys move between its entries, Escape closes it and gives the focus
 *   back to its button; a click outside closes it. An entry with nothing to act on is disabled and
 *   its tooltip says why (design principle 5.1)
 */
import { clear, type MenuEntry as Shown, extraMenuItems, h, icon, showEntries } from "./dom";

export interface MenuItem {
  label: string;
  run?: () => void;
  /** Shown on the right: "Ctrl+O". */
  keys?: string;
  icon?: string;
  disabled?: boolean;
  /** Why it is disabled, or what it adds (a tooltip). */
  title?: string;
  /** A small muted label over the entries after it. */
  heading?: boolean;
  /** A document's kind colour on its icon (kindColours.ts): "app", "notebook", "script". */
  mark?: string;
}

/** null: a line between entries. */
export type MenuEntry = MenuItem | null;

let shown: HTMLElement | null = null;

export function closeMenu(): void {
  shown?.remove();
  shown = null;
}

/** Open a menu under (or over) its button; `beside`: to its right, level with it (the rail's menus). It is
 *  the app's one menu (dom.ts showEntries) in the Workbench's look: its entries' keys at the right, a kind's
 *  colour on an icon, headings between groups. */
export function openMenu(anchor: HTMLElement, label: string, entries: MenuEntry[], options: { align?: "left" | "right"; above?: boolean; beside?: boolean } = {}): HTMLElement {
  closeMenu();
  // Opened by a right-click (a tab's menu): beta mode's "Leave a note…" at its end.
  const extra = extraMenuItems();
  if (extra.length) entries = [...entries, null, ...extra.map((e): MenuItem => ({ label: e.label, icon: e.icon, run: e.run }))];
  // A line between entries only: never first, last or twice.
  const rows: Shown[] = [];
  const from = new Map<Shown, MenuItem>();
  let line = false;
  for (const entry of entries) {
    if (entry === null) {
      line = rows.length > 0;
      continue;
    }
    const row: Shown = { label: entry.label, run: entry.run, disabled: entry.disabled, why: entry.title, heading: entry.heading, group: line };
    line = false;
    from.set(row, entry);
    rows.push(row);
  }
  const menu = showEntries(0, 0, label, rows, {
    menu: "menu wb-menu",
    rule: "wb-menu-line",
    heading: false,
    anchor,
    closing: () => {
      shown = null;
      anchor.setAttribute("aria-expanded", "false");
    },
    place: (made) => {
      const box = anchor.getBoundingClientRect();
      const left = options.beside ? box.right + 4 : options.align === "right" ? box.right - made.offsetWidth : box.left;
      const top = options.beside
        ? Math.max(8, Math.min(box.top, innerHeight - made.offsetHeight - 8))
        : options.above
          ? Math.max(8, box.top - made.offsetHeight - 4)
          : Math.min(box.bottom + 4, innerHeight - made.offsetHeight - 8);
      return { left: Math.max(8, Math.min(left, innerWidth - made.offsetWidth - 8)), top };
    },
    dress: (row, shownAs) => {
      const entry = from.get(shownAs)!;
      if (entry.mark) row.className = `km-${entry.mark}`;
      else row.removeAttribute("class");
      // "disabled" follows the entry alone: its tooltip may say what it adds, not only why it is off.
      row.disabled = Boolean(entry.disabled);
      if (entry.keys) row.setAttribute("aria-keyshortcuts", entry.keys);
      clear(
        row,
        entry.icon ? icon(entry.icon) : h("span", { class: "wb-menu-gap", "aria-hidden": "true" }),
        h("span", { class: "wb-menu-text" }, entry.label),
        // The keys are seen, not read into the entry's name (aria-keyshortcuts carries them).
        entry.keys ? h("kbd", { "aria-hidden": "true" }, entry.keys) : null,
      );
    },
  });
  anchor.setAttribute("aria-expanded", "true");
  shown = menu;
  return menu;
}

/** A button that opens a menu (a second click closes it). */
export function menuButton(anchor: HTMLButtonElement, label: string, entries: () => MenuEntry[], options: { align?: "left" | "right"; above?: boolean } = {}): HTMLButtonElement {
  anchor.setAttribute("aria-haspopup", "menu");
  anchor.setAttribute("aria-expanded", "false");
  anchor.onclick = () => {
    if (shown?.isConnected && anchor.getAttribute("aria-expanded") === "true") {
      closeMenu();
      anchor.setAttribute("aria-expanded", "false");
      return;
    }
    openMenu(anchor, label, entries(), options);
  };
  return anchor;
}
