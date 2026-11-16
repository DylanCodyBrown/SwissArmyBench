/**
 * workbenchMenu.ts: the Workbench's drop-down menus (the top bar's "…", a group's "+ Cell" and "…",
 * the status bar's kernel menu, the Data panel's "+ Table"). [FUNCTION]
 *
 *   one menu at a time; the arrow keys move between its entries, Escape closes it and gives the focus
 *   back to its button; a click outside closes it. An entry with nothing to act on is disabled and
 *   its tooltip says why (design principle 5.1)
 */
import { extraMenuItems, h, icon } from "./dom";

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

let shown: { menu: HTMLElement; away: (e: Event) => void } | null = null;

export function closeMenu(): void {
  if (!shown) return;
  shown.menu.remove();
  document.removeEventListener("mousedown", shown.away, true);
  shown = null;
}

/** Open a menu under (or over) its button; `beside`: to its right, level with it (the rail's menus). */
export function openMenu(anchor: HTMLElement, label: string, entries: MenuEntry[], options: { align?: "left" | "right"; above?: boolean; beside?: boolean } = {}): HTMLElement {
  closeMenu();
  document.querySelector(".menu")?.remove(); // another module's menu
  // Opened by a right-click (a tab's menu): beta mode's "Leave a note…" at its end.
  const extra = extraMenuItems();
  if (extra.length) entries = [...entries, null, ...extra.map((e): MenuItem => ({ label: e.label, icon: e.icon, run: e.run }))];
  const menu = h("div", { class: "menu wb-menu", role: "menu", "aria-label": label });
  let lastWasLine = true;
  for (const entry of entries) {
    if (entry === null) {
      if (!lastWasLine) menu.append(h("div", { class: "wb-menu-line", role: "separator" }));
      lastWasLine = true;
      continue;
    }
    lastWasLine = false;
    if (entry.heading) {
      menu.append(h("div", { class: "menu-label" }, entry.label));
      continue;
    }
    const item = h(
      "button",
      {
        type: "button",
        role: "menuitem",
        class: entry.mark ? `km-${entry.mark}` : undefined,
        disabled: entry.disabled,
        title: entry.title,
        "aria-keyshortcuts": entry.keys,
        onclick: () => {
          closeMenu();
          anchor.setAttribute("aria-expanded", "false");
          entry.run?.();
        },
      },
      entry.icon ? icon(entry.icon) : h("span", { class: "wb-menu-gap", "aria-hidden": "true" }),
      h("span", { class: "wb-menu-text" }, entry.label),
      // The keys are seen, not read into the entry's name (aria-keyshortcuts carries them).
      entry.keys ? h("kbd", { "aria-hidden": "true" }, entry.keys) : null,
    );
    menu.append(item);
  }
  if (menu.lastElementChild?.classList.contains("wb-menu-line")) menu.lastElementChild.remove();
  document.body.append(menu);
  const box = anchor.getBoundingClientRect();
  const left = options.beside ? box.right + 4 : options.align === "right" ? box.right - menu.offsetWidth : box.left;
  menu.style.left = `${Math.max(8, Math.min(left, innerWidth - menu.offsetWidth - 8))}px`;
  if (options.beside) menu.style.top = `${Math.max(8, Math.min(box.top, innerHeight - menu.offsetHeight - 8))}px`;
  else if (options.above) menu.style.top = `${Math.max(8, box.top - menu.offsetHeight - 4)}px`;
  else menu.style.top = `${Math.min(box.bottom + 4, innerHeight - menu.offsetHeight - 8)}px`;
  anchor.setAttribute("aria-expanded", "true");
  const items = (): HTMLButtonElement[] => [...menu.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
  items()[0]?.focus();
  menu.addEventListener("keydown", (e) => {
    const list = items();
    const at = list.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "ArrowDown") list[(at + 1) % list.length]?.focus();
    else if (e.key === "ArrowUp") list[(at - 1 + list.length) % list.length]?.focus();
    else if (e.key === "Home") list[0]?.focus();
    else if (e.key === "End") list[list.length - 1]?.focus();
    else if (e.key === "Escape" || e.key === "Tab") {
      closeMenu();
      anchor.setAttribute("aria-expanded", "false");
      if (e.key === "Escape") anchor.focus();
      else return;
    } else return;
    e.preventDefault();
    e.stopPropagation();
  });
  const away = (e: Event): void => {
    if (menu.contains(e.target as Node) || anchor.contains(e.target as Node)) return;
    closeMenu();
    anchor.setAttribute("aria-expanded", "false");
  };
  document.addEventListener("mousedown", away, true);
  shown = { menu, away };
  return menu;
}

/** A button that opens a menu (a second click closes it). */
export function menuButton(anchor: HTMLButtonElement, label: string, entries: () => MenuEntry[], options: { align?: "left" | "right"; above?: boolean } = {}): HTMLButtonElement {
  anchor.setAttribute("aria-haspopup", "menu");
  anchor.setAttribute("aria-expanded", "false");
  anchor.onclick = () => {
    if (shown && anchor.getAttribute("aria-expanded") === "true") {
      closeMenu();
      anchor.setAttribute("aria-expanded", "false");
      return;
    }
    openMenu(anchor, label, entries(), options);
  };
  return anchor;
}
