/**
 * rail.ts: the areas down the left of every page and window (the owner, 2026-11-16: "As much as I hate
 * to say it, this app needs a navigation pane somehow."; a slim icon rail, as VS Code's Activity Bar).
 * [SHARED]
 *
 *   [AREAS]   Grids (the home page's tabbed grids; the mark goes Home, the Start view), Sandbox, Diagram, Notebooks,
 *             Scripts, Apps (the Streamlit canvas), Blades, Connections, and Settings pinned at the
 *             bottom. An icon each, its name in a tip on hover and on keyboard focus; Notebooks,
 *             Scripts and Apps wear their kind colours. The mark stays in each page's top row.
 *   [GO]      A click is a navigation like any other (nav.ts): an area this page shows is pushed, so
 *             Back, Forward and a reload work. Connections and Settings open their layers (open=<key>)
 *             where the page has them. An area another window shows brings that window forward, or
 *             opens it: the home window (sab-home) for the grids, Sandbox and Diagram; the Workbench for
 *             notebooks, scripts and apps (code always opens in its own window, never the grid page);
 *             the blades page (plan decision 18: its own tab). This window is never sent away.
 *   [KINDS]   In the Workbench, Notebooks, Scripts and Apps bring that kind's document forward (its
 *             mode: ?kind=notebook in the address), or offer New and that kind's recent files. Right-
 *             click, Ctrl+click or a middle click: Open in a new window (a Workbench window of its own,
 *             as a popped-out tab's).
 *   [CURRENT] the area the address names is marked (a bar on the left edge, the icon brighter) with
 *             aria-current="page"; it follows every move (onAddress), Back and Forward too.
 *   [KEYS]    one stop in the Tab order (a toolbar): the arrows move between the areas, Enter goes;
 *             Alt+Home is Home (the Start view) everywhere (nav.ts).
 *   [PANEL]   Settings' Panels has its switch (app.rail): off, the rail is gone and the page takes its
 *             width back.
 *   [AGENT]   app_navigate's areas run here (setAreaRunner), as a click would (new_window too).
 *
 * Another window's area reaches the window that shows it as a message from this origin ({sab: "area"});
 * a window opened for it is given the area in its address (?view=sandbox, ?open=settings, ?kind=script).
 */
import { token } from "./api";
import { h, icon, toast } from "./dom";
import { type Kind, loadKindColours } from "./kindColours";
import { go, goHome, hasLayer, HOME_URL, homeWindow, namedWindow, onAddress, openLayer, type PageKind, setAreaRunner, visit, withParams } from "./nav";
import { loadPanels, onPanels } from "./panels";
import { openMenu } from "./workbenchMenu";

export type Area = "grids" | "sandbox" | "diagram" | "notebooks" | "scripts" | "apps" | "blades" | "connections" | "settings";

/** The rail's order (domain/navigation.py AREAS holds the same); the last one is pinned at the bottom.
 *  The code areas' icons are their documents' (kindColours.ts kindIcon). */
const AREAS: { area: Area; name: string; icon: string; kind?: Kind }[] = [
  { area: "grids", name: "Grids", icon: "grids" },
  { area: "sandbox", name: "Sandbox", icon: "sandbox" },
  { area: "diagram", name: "Diagram", icon: "diagram" },
  { area: "notebooks", name: "Notebooks", icon: "notebook", kind: "notebook" },
  { area: "scripts", name: "Scripts", icon: "code", kind: "script" },
  { area: "apps", name: "Apps", icon: "page", kind: "app" },
  { area: "blades", name: "Blades", icon: "blade" },
  { area: "connections", name: "Connections", icon: "plug" },
  { area: "settings", name: "Settings", icon: "cog" },
];
const isArea = (name: unknown): name is Area => AREAS.some((a) => a.area === name);
const kindOfArea = (area: Area): Kind | undefined => AREAS.find((a) => a.area === area)?.kind;
const areaOfKind = (kind: string | null): Area | null => AREAS.find((a) => a.kind === kind)?.area ?? null;

const WORKBENCH_WINDOW = "swissarmybench-workbench";
const CATALOG_WINDOW = "swissarmybench-catalog";
const LAYER_OFF = { open: null, at: null, type: null, name: null };

export interface RailOptions {
  /** The Workbench: bring a document of `kind` forward, or (from the rail: `anchor`) offer New and its
   *  recent files. */
  showKind?: (kind: Kind, anchor: HTMLElement | null) => void;
}

let kind: PageKind = "home";
let options: RailOptions = {};
let items: HTMLButtonElement[] = [];

/** The area the address names on this page (null: none, a Workbench with no document of a kind). */
function currentArea(url: URL): Area | null {
  const open = url.searchParams.get("open");
  if (open === "settings" || open === "connections") return open;
  if (kind === "catalog") return "blades";
  if (kind === "workbench") return areaOfKind(url.searchParams.get("kind"));
  const view = kind === "home" ? url.searchParams.get("view") : null;
  if (view === "sandbox" || view === "diagram") return view;
  if (view === "start") return null; // Home (startView.ts): no area of the rail's
  return "grids"; // the grids (and the steps and Key Finder windows, which are a grid's)
}

/** A home window opened for `area`: the area in its address. */
function arrivalUrl(area: Area): string {
  if (area === "sandbox" || area === "diagram") return `${HOME_URL}?view=${area}`;
  if (area === "settings" || area === "connections") return `${HOME_URL}?open=${area}`;
  return HOME_URL;
}

/** The home window shows `area`: told by a message, or opened at the area's address. */
function inHome(area: Area): void {
  const found = homeWindow();
  if (!found) return;
  if (found.fresh || found.win === window) found.win.location.href = arrivalUrl(area);
  else found.win.postMessage({ sab: "area", area }, location.origin);
  found.win.focus();
}

const withToken = (path: string, more: Record<string, string> = {}): string => {
  const hash = new URLSearchParams({ ...(token ? { token } : {}), ...more }).toString();
  return hash ? `${path}#${hash}` : path;
};

/** Another page's window by its name, brought forward (told `area`), or opened at `path`. */
function inWindow(name: string, path: string, area?: Area): void {
  const found = namedWindow(name);
  if (!found) return;
  if (found.fresh) found.win.location.href = withToken(path);
  else if (area) found.win.postMessage({ sab: "area", area }, location.origin);
  found.win.focus();
}

/** A Workbench window of its own for `kind` (the owner's "external tab"), as a popped-out tab's. */
function newKindWindow(k: Kind): void {
  const opened = window.open(withToken(`/workbench?kind=${k}`, { fresh: "1", popped: "1" }), `swissarmybench-workbench-${Date.now()}`, "popup,width=1200,height=800");
  if (opened) opened.focus();
  else toast("The browser blocked the new window: allow pop-ups for this address.", "error");
}

const itemOf = (area: Area): HTMLButtonElement | null => items.find((i) => i.dataset.area === area && i.offsetParent !== null) ?? null;

/** Go to `area`, as its click does (`newWindow`: a code area in a Workbench window of its own). */
export function goArea(area: Area, newWindow = false): void {
  const k = kindOfArea(area);
  if (k) {
    if (newWindow) newKindWindow(k);
    else if (kind === "workbench" && options.showKind) {
      void go(withParams({ kind: k }), "push");
      options.showKind(k, itemOf(area));
    } else inWindow(WORKBENCH_WINDOW, `/workbench?kind=${k}`, area);
    return;
  }
  switch (area) {
    case "grids":
      // The grids (Home is the Start view, 2026-11-16): here, or in the home window brought forward.
      if (kind === "home") visit(withParams({ ...LAYER_OFF, view: null }, HOME_URL));
      else inHome(area);
      return;
    case "sandbox":
    case "diagram":
      if (kind === "home") visit(withParams({ ...LAYER_OFF, view: area }, HOME_URL));
      else inHome(area);
      return;
    case "settings":
    case "connections":
      if (hasLayer(area)) openLayer(area);
      else inHome(area);
      return;
    case "blades":
      if (kind !== "catalog") inWindow(CATALOG_WINDOW, "/catalog");
      return;
  }
}

function draw(url: URL): void {
  const now = currentArea(url);
  const stop = now ?? AREAS[0]!.area;
  for (const item of items) {
    const here = item.dataset.area === now;
    item.classList.toggle("current", here);
    if (here) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
    // One stop in the Tab order: the current area's (the arrows reach the others).
    item.tabIndex = item.dataset.area === stop ? 0 : -1;
  }
}

function onKey(e: KeyboardEvent): void {
  const at = items.indexOf(e.target as HTMLButtonElement);
  if (at < 0 || e.altKey || e.ctrlKey || e.metaKey) return;
  const to = { ArrowDown: at + 1, ArrowRight: at + 1, ArrowUp: at - 1, ArrowLeft: at - 1, Home: 0, End: items.length - 1 }[e.key];
  if (to === undefined) return;
  e.preventDefault();
  const next = items[(to + items.length) % items.length]!;
  for (const item of items) item.tabIndex = item === next ? 0 : -1;
  next.focus();
}

function item(area: (typeof AREAS)[number]): HTMLButtonElement {
  const grids = area.area === "grids";
  const element = h(
    "button",
    {
      type: "button",
      class: ["nav-rail-item", area.area === "settings" ? "nav-rail-bottom" : "", area.kind ? `nav-rail-kind km-${area.kind}` : ""].filter(Boolean).join(" "),
      "data-area": area.area,
      "aria-label": area.name,
      "aria-keyshortcuts": undefined,
      "aria-haspopup": area.area === "settings" || area.area === "connections" ? "dialog" : area.kind ? "menu" : undefined,
      // Ctrl+click (Cmd+click): a new window, as a link's new tab.
      onclick: (e: MouseEvent) => goArea(area.area, !!area.kind && (e.ctrlKey || e.metaKey)),
    },
    icon(area.icon),
    // The name, on hover and on focus (a `title` would show the same words a second time).
    h("span", { class: "nav-rail-tip", "aria-hidden": "true" }, area.name),
  );
  if (area.kind) {
    // A middle click: a new window too (its mousedown would start the browser's autoscroll).
    element.addEventListener("mousedown", (e) => {
      if (e.button === 1) e.preventDefault();
    });
    element.addEventListener("auxclick", (e) => {
      if (e.button !== 1) return;
      e.preventDefault();
      goArea(area.area, true);
    });
    element.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      openMenu(element, area.name, [{ label: "Open in a new window", icon: "popout", run: () => goArea(area.area, true) }], { beside: true });
    });
  }
  return element;
}

/** Each page's composition mounts the rail once (mountNavRail), right after mountNav. */
export function mountNavRail(page: PageKind, given: RailOptions = {}): void {
  kind = page;
  options = given;
  items = AREAS.map(item);
  const toolbar = h("div", { class: "nav-rail-items", role: "toolbar", "aria-label": "Areas", "aria-orientation": "vertical", onkeydown: onKey }, ...items);
  document.body.prepend(h("nav", { class: "nav-rail", "aria-label": "Areas" }, toolbar));
  document.body.classList.add("has-rail");
  draw(new URL(location.href));
  onAddress(draw);
  setAreaRunner((area, newWindow) => {
    if (!isArea(area)) return false;
    goArea(area, newWindow);
    return true;
  });
  // The rail on or off: the page's width changes, so the grid, Monaco and the canvas measure again.
  onPanels(() => window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize"))));
  void loadPanels();
  void loadKindColours(); // the code areas wear the kind colours chosen in Settings
  // Another window's rail: the area it asked this window for (a message from this origin only).
  window.addEventListener("message", (e: MessageEvent) => {
    const said = e.data as { sab?: unknown; area?: unknown } | null;
    if (e.origin !== location.origin || said?.sab !== "area") return;
    if (said.area === "home") goHome(); // another window's mark: Home (the Start view)
    else if (isArea(said.area)) goArea(said.area);
  });
}

/** The Workbench's code area's item, when the rail shows (a kind's menu opens beside it). */
export function railItem(k: Kind): HTMLElement | null {
  const area = areaOfKind(k);
  return area ? itemOf(area) : null;
}
