/**
 * connectionColours.ts: each connection's colour, worn by everything tied to it (the owner, 2026-11-16:
 * "choose connection colors that everything associated with that connection is painted that color, cells,
 * grids, app cells ... reserve the rail colors for the rail"). [STATE + WIRE]
 *
 * A colour is this computer's, the same in every project (2026-11-17: connections are a library outside
 * any project); the server keeps it (colours.toml) and makes it readable in each theme. It is always a
 * stripe or a dot, never a background: text stays readable.
 *
 * Any element that names its connections wears them: `data-connections="Warehouse|Finance"` (one name or
 * several, in order). This module paints every such element on the page, now and as they are drawn (a
 * MutationObserver), and again when a colour, a connection, the kind colours or the theme changes; the
 * places that draw them only set the attribute. CSS reads `--conn-a` (the first) and `--conn-b` (the
 * second, a second mark beside the first; the first again when there is one).
 *
 * ROUTING: GET /connection-colours, PUT /connection-colours/{name}, POST /connection-colours/uses
 * (routes_connection_colours.py); the `connection_colours_changed`, `blades_changed` and
 * `kind_colours_changed` notices.
 */
import { api, onNotice } from "./api";
import { h } from "./dom";
import { effectiveTheme, onThemeChange } from "./theme";
import { errorHere } from "./errorNote";

export interface ConnectionColour {
  name: string;
  /** The colour it wears (its own, or the next free one in its turn). */
  colour: string;
  /** The colour the user chose (null: it wears the next free one). */
  chosen: string | null;
  /** The colour each theme shows. */
  themes: Record<string, string>;
}

export interface PaletteColour {
  name: string;
  colour: string;
  themes: Record<string, string>;
}

interface Listing {
  connections: ConnectionColour[];
  palette: PaletteColour[];
}

let listing: Listing = { connections: [], palette: [] };
const listeners: (() => void)[] = [];
let loading: Promise<void> | null = null;

const fold = (name: string): string => name.trim().toLocaleLowerCase();

/** The connection's entry, by its name in any case (undefined: no such connection). */
export function connectionColour(name: string | null | undefined): ConnectionColour | undefined {
  if (!name) return undefined;
  const key = fold(name);
  return listing.connections.find((c) => fold(c.name) === key);
}

/** The colour a connection shows in the current theme (null: no such connection). */
export function colourOf(name: string | null | undefined): string | null {
  const found = connectionColour(name);
  return found ? (found.themes[effectiveTheme()] ?? found.colour) : null;
}

export const connectionColours = (): ConnectionColour[] => listing.connections;
export const palette = (): PaletteColour[] => listing.palette;

export function onConnectionColours(listener: () => void): void {
  listeners.push(listener);
}

function take(next: Listing): void {
  listing = { connections: next.connections ?? [], palette: next.palette ?? [] };
  paint(document);
  for (const listener of listeners) listener();
}

/** Read every connection's colour (once at a time; later calls share the read in flight). */
export function loadConnectionColours(): Promise<void> {
  loading ??= api<Listing>("/connection-colours")
    .then(take, () => undefined /* an older server: no colours */)
    .finally(() => (loading = null));
  return loading;
}

/** Choose a connection's colour (null: the next free one). Refused with the server's words. */
export async function setConnectionColour(name: string, colour: string | null): Promise<void> {
  take(await api<Listing>(`/connection-colours/${encodeURIComponent(name)}`, "PUT", { colour }));
}

/** Which connections each cell names (the server reads Python with ast; nothing runs). */
export async function cellConnections(cells: { kind: string; source?: string; connection?: string | null }[]): Promise<string[][]> {
  if (!cells.length) return [];
  try {
    return (await api<{ cells: string[][] }>("/connection-colours/uses", "POST", { cells })).cells;
  } catch {
    return cells.map(() => []);
  }
}

/** Set an element's connections (the marks follow by themselves). Empty: none. */
export function markConnections(el: HTMLElement, names: (string | null | undefined)[]): void {
  const own = names.filter((n): n is string => !!n);
  if (own.length) el.dataset.connections = own.join("|");
  else delete el.dataset.connections;
}

/** A small dot in a connection's colour (a card's head, a group's head, a reference). */
export function connectionDot(name: string): HTMLElement {
  const dot = document.createElement("span");
  dot.className = "conn-dot";
  dot.dataset.connections = name;
  dot.setAttribute("aria-hidden", "true");
  return dot;
}

/** A connection's colour as a swatch: a click shows the palette (each colour as this theme shows it), Other…
 *  (any colour; the rail's are refused with the server's words) and Next free. On its card and its detail. */
export function colourPicker(name: string): HTMLButtonElement {
  const swatch = h("button", {
    type: "button",
    class: "conn-swatch",
    "data-connections": name,
    "aria-label": `${name}'s colour`,
    "aria-haspopup": "menu",
    title: `${name}'s colour`,
    onclick: (e: MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      showPalette(name, swatch);
    },
  }) as HTMLButtonElement;
  return swatch;
}

function choose(name: string, colour: string | null): void {
  void setConnectionColour(name, colour).catch((e: unknown) => errorHere(e));
}

function showPalette(name: string, anchor: HTMLElement): void {
  document.querySelector(".conn-palette")?.remove();
  const theme = effectiveTheme();
  const own = connectionColour(name);
  const close = (): void => {
    menu.remove();
    document.removeEventListener("mousedown", away);
    anchor.focus();
  };
  const away = (event: Event): void => {
    if (!menu.contains(event.target as Node)) close();
  };
  const other = h("input", {
    type: "color",
    value: own?.colour ?? "#0e7c7b",
    "aria-label": "Other colour",
    onchange: (e: Event) => {
      choose(name, (e.target as HTMLInputElement).value);
      close();
    },
  });
  const menu = h(
    "div",
    { class: "menu conn-palette", role: "menu", "aria-label": `${name}'s colour` },
    h("div", { class: "menu-label" }, `${name}'s colour`),
    h(
      "div",
      { class: "conn-palette-swatches" },
      ...palette().map((p) =>
        h("button", {
          type: "button",
          role: "menuitemradio",
          class: "conn-palette-swatch",
          "aria-checked": String(own?.colour === p.colour),
          "aria-label": p.name,
          title: p.name,
          "data-colour": p.colour,
          style: `--swatch: ${p.themes[theme] ?? p.colour}`,
          onclick: () => {
            choose(name, p.colour);
            close();
          },
        }),
      ),
    ),
    h("label", { class: "conn-palette-other" }, other, "Other…"),
    own?.chosen
      ? h("button", { type: "button", role: "menuitem", class: "conn-palette-free", onclick: () => { choose(name, null); close(); } }, "Next free")
      : null,
  );
  document.body.append(menu);
  const box = anchor.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(box.left, window.innerWidth - menu.offsetWidth - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(box.bottom + 4, window.innerHeight - menu.offsetHeight - 8))}px`;
  menu.querySelector<HTMLButtonElement>("[aria-checked=true], .conn-palette-swatch")?.focus();
  menu.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      close();
      return;
    }
    const items = [...menu.querySelectorAll<HTMLElement>(".conn-palette-swatch, input, .conn-palette-free")];
    const at = items.indexOf(document.activeElement as HTMLElement);
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (step && at >= 0) {
      event.preventDefault();
      items[(at + step + items.length) % items.length]?.focus();
    }
  });
  setTimeout(() => document.addEventListener("mousedown", away));
}

function paintOne(el: HTMLElement): void {
  const names = (el.dataset.connections ?? "").split("|").filter(Boolean);
  const colours = names.map((n) => colourOf(n)).filter((c): c is string => !!c);
  if (!colours.length) {
    el.style.removeProperty("--conn-a");
    el.style.removeProperty("--conn-b");
    el.classList.remove("conn-worn", "conn-two");
    return;
  }
  el.style.setProperty("--conn-a", colours[0]!);
  el.style.setProperty("--conn-b", colours[1] ?? colours[0]!);
  el.classList.add("conn-worn");
  el.classList.toggle("conn-two", colours.length > 1);
  const worn = names.filter((n) => colourOf(n)).map((n) => connectionColour(n)!.name);
  if (!el.title && !el.dataset.connTitled) {
    el.dataset.connTitled = "1";
    el.title = worn.join(", ");
  }
}

/** Paint every element under `root` that names its connections. */
export function paint(root: ParentNode): void {
  if (root instanceof HTMLElement && root.dataset.connections !== undefined) paintOne(root);
  for (const el of root.querySelectorAll<HTMLElement>("[data-connections]")) paintOne(el);
}

let pending = new Set<HTMLElement>();
let scheduled = false;
function soon(el: HTMLElement): void {
  pending.add(el);
  if (scheduled) return;
  scheduled = true;
  requestAnimationFrame(() => {
    scheduled = false;
    const now = pending;
    pending = new Set();
    for (const one of now) if (one.isConnected) paint(one);
  });
}

/** A drawn node worth painting: it, or something in it, names connections. A grid's rows and cells never
 * do (AG Grid adds them by the hundred as it scrolls), so nothing inside a grid is looked into. */
function namesConnections(node: HTMLElement): boolean {
  if (node.dataset.connections !== undefined) return true;
  if (node.closest(".ag-root-wrapper")) return false;
  return node.querySelector("[data-connections]") !== null;
}

let watching = false;
/** Paint as the page draws, and follow every change. Call once per page. */
export function watchConnectionColours(): void {
  if (watching) return;
  watching = true;
  new MutationObserver((changes) => {
    for (const change of changes) {
      if (change.type === "attributes") soon(change.target as HTMLElement);
      else for (const node of change.addedNodes) if (node instanceof HTMLElement && namesConnections(node)) soon(node);
    }
  }).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-connections"] });
  void loadConnectionColours();
}

onNotice((notice) => {
  if (notice.type === "connection_colours_changed") take(notice as unknown as Listing);
  else if (notice.type === "blades_changed" || notice.type === "kind_colours_changed" || notice.type === "project_changed") void loadConnectionColours();
});
onThemeChange(() => paint(document));
