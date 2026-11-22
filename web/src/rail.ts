/**
 * rail.ts: the areas down the left of every page and window (the owner, 2026-11-16: "As much as I hate
 * to say it, this app needs a navigation pane somehow."; a slim icon rail, as VS Code's Activity Bar).
 * [SHARED]
 *
 *   [MARK]    the red mark first, above Connections (the owner, 2026-11-18: "Move this to the rail also reduce
 *             icon size just a bit so more fit. and give this button its own page for projects"): the
 *             Projects page (projectsPage.ts, open=projects, the home page's only); from another window it
 *             brings the home window forward showing Projects (nav.ts goHome). Alt+Home is the same.
 *   [AREAS]   Data after Variables (dataPage.ts, open=data: the one place to browse and find tables), Grids (the home page's tabbed grids, only the grids), Analyze, ERD, Notebooks,
 *             Scripts, Canvas (canvasPage.ts: the Streamlit canvas), Widgets (its own window), Blades, Connections, Session (what the agent made this
 *             session, a count of what is new on its icon: sessionPage.ts), and Extensions
 *             (extensionsPage.ts) and Settings pinned at the bottom. An icon each, its name in a tip on hover and on keyboard focus; Notebooks,
 *             Scripts and Apps wear their kind colours.
 *   [PAGES]   Every area lands on a page, never a dialog or a menu (the owner, 2026-11-16: "clicking the
 *             rail should land on a page not open a form"): the grids, Analyze, the ERD, a kind's
 *             landing page in the Workbench (workbenchLanding.ts), the blades page, the Connections page
 *             and the Settings page (areaPage.ts, over the page you are on: open=connections,
 *             open=settings).
 *   [GO]      A click is a navigation like any other (nav.ts): an area this page shows is pushed, so
 *             Back, Forward and a reload work. Connections and Settings show their pages where the page
 *             has them. An area another page shows takes this tab there (the owner, 2026-11-16: "the
 *             rail icons is opening a new tab every time instead of navigating the current page"): the
 *             home page for the grids, Analyze and the ERD; the Workbench for notebooks, scripts and apps
 *             (code still never sits in the grid page); the blades page.
 *   [KINDS]   Notebooks, Scripts and Apps land on that kind's page in the Workbench (?kind=notebook&
 *             view=list): its documents as cards, open ones first; New is on that page's panel, never in
 *             a menu beside the icon (the owner: "get rid of that its duplicated behavior we should only
 *             create things from the panel"). On every area, right-click, Ctrl+click or a middle click:
 *             Open in a new window (for a code area, a Workbench window of its own).
 *   [CURRENT] the area the address names is marked (a bar on the left edge, the icon brighter) with
 *             aria-current="page"; it follows every move (onAddress), Back and Forward too.
 *   [KEYS]    one stop in the Tab order (a toolbar): the arrows move between the areas, Enter goes;
 *             the mark is the first stop. Alt+Home is Home (Projects) everywhere (nav.ts).
 *   [ALWAYS]  No switch (the owner, 2026-11-16): the rail is the one way to the areas, so the top tabs and
 *             the Application row no longer repeat them.
 *   [AGENT]   app_navigate's areas run here (setAreaRunner), as a click would (new_window too).
 *   [NAMES]   The rail with its names beside the icons (the owner, 2026-11-19: several glyphs are alike), on
 *             until the user turns them off: the toggle at the rail's foot (Icons only / Show names) or the
 *             right-click menu. This computer's choice (GET/PUT /rail, rail.json; app_rail), every window
 *             follows (rail_changed); the last one is remembered here too so a page opens without a jump.
 *
 * Another window's area reaches the window that shows it as a message from this origin ({sab: "area"});
 * a window opened for it is given the area in its address (?view=analyze, ?open=settings, ?kind=script).
 */
import { api, onNotice, token } from "./api";
import { h, icon } from "./dom";
import type { Kind } from "./kindColours";
import { goHome, hasLayer, HOME_URL, layerShown, onAddress, openLayer, type PageKind, PROJECTS_URL, setAreaRunner, visit, withParams } from "./nav";
import { onUnseen } from "./sessionPage";
// The APIs, Structures, Code App (a plug-in: shown while it is on), Source Control (a plug-in: shown while the
// backend names its area) and Extensions pages' layers, on every page with the rail; each page loads when first
// opened (lazyPages.ts).
import { APIS, CODE_APP, codeAppOn, EXTENSIONS, SCM, scmOn } from "./lazyPages";
import { canvasOn } from "./modes";
import { PAGE_WINDOW as PAGE_WINDOWS, pageOfKind, thisPage } from "./workbenchPages";
import "./environmentPage"; // the Environment page's layer, on every page with the rail
import "./variablesPage"; // the key vaults' and settings' manager (open=variables): a layer, off the rail
import { openMenu } from "./workbenchMenu";
import { errorHere } from "./errorNote";
import { DATA } from "./dataPage"; // the Data page's layer, on every page with the rail
import { panelAreas } from "./extensionArea"; // an extension's area drawn from its data (GET /app/areas)
import { firstOpen, isClosed, loadGates, onGates, removeGateCover, showGateLine } from "./gates";

export type Area = "projects" | "grids" | "analyze" | "erd" | "notebooks" | "scripts" | "canvas" | "widgets" | "blades" | "connections" | "session" | "variables" | "apis" | "structures" | "environment" | "extensions" | "codeapp" | "scm" | "settings" | "data";

/** The rail's order (domain/navigation.py AREAS holds the same); the last one is pinned at the bottom.
 *  The code areas' icons are their documents' (kindColours.ts kindIcon). */
const AREAS: { area: Area; name: string; icon: string; kind?: Kind; plugin?: () => Promise<boolean>; keys?: string }[] = [
  // The mark, first (the owner, 2026-11-18): Home, the Projects page.
  // Home, an ordinary item with a house (the owner, 2026-11-21: "a + is confusing just make this a normal icon" /
  // "just call it home instead of projects"): the Projects page (open=projects), Alt+Home, first.
  { area: "projects", name: "Home", icon: "home", keys: "Alt+Home" },
  // In the order of the work (the owner, 2026-11-17: "rearrange the rail to make since. In order of
  // workflow"): where the data comes from, getting and shaping it, web data, tools, building, presenting,
  // then the log.
  { area: "connections", name: "Connections", icon: "plug" },
  // The library's APIs, their explorer (apisPage.ts): beside Connections (the owner, 2026-11-18).
  { area: "apis", name: APIS, icon: "apis" },
  // The Environment (the owner, 2026-11-21/22): everything the project holds (tables, variables, structures,
  // settings and secrets, libraries), in the Structures and Variables places (environmentPage.ts). The
  // Structures page stays as the viewer a structure's row opens into (open=structures).
  { area: "environment", name: "Environment", icon: "environment" },
  { area: "data", name: DATA, icon: "data" }, // the one place to browse and find tables (dataPage.ts)
  { area: "grids", name: "Grids", icon: "grids" },
  { area: "erd", name: "ERD", icon: "diagram" },
  { area: "blades", name: "Blades", icon: "blade" },
  // Scripts beside Blades (the owner, 2026-11-21: "scripts and blades should be beside each other on the
  // rail"); Notebooks and Scripts are two pages (workbenchPages.ts).
  { area: "scripts", name: "Scripts", icon: "code", kind: "script" },
  { area: "notebooks", name: "Notebooks", icon: "notebook", kind: "notebook" },
  // An extension's area: its plug-in says whether it is on here (hidden until it says so).
  { area: "codeapp", name: CODE_APP, icon: "codeapp", plugin: codeAppOn },
  // The Canvas (the owner, 2026-11-21: "instead of Apps on rail we could call it Canvas"), an extension's
  // (Streamlit, preinstalled): a page of its own (canvas.html), shown while a mode offers it.
  { area: "canvas", name: "Canvas", icon: "page", plugin: () => canvasOn("streamlit") },
  // Widgets (the owner, 2026-11-21): not in this window's pane, a window of its own with no rail
  // (static/widget.html: the list, one widget's editor, its Properties).
  { area: "widgets", name: "Widgets", icon: "sliders", plugin: () => canvasOn("streamlit") },
  // An extension's area the backend names (GET /app/areas), as VS Code's activity bar has it.
  { area: "scm", name: SCM, icon: "source-control", plugin: scmOn },
  { area: "analyze", name: "Analyze", icon: "sandbox" },
  { area: "session", name: "Session", icon: "session" }, // what the agent made this session (sessionPage.ts)
  // What plugs into the base (extensionsPage.ts), above Settings at the bottom (the owner, 2026-11-17).
  { area: "extensions", name: EXTENSIONS, icon: "extensions" },
  { area: "settings", name: "Settings", icon: "cog" },
];
/** The areas that are a page of the rail's over any page (areaPage.ts), each its own layer (open=<area>). */
const LAYERS: readonly Area[] = ["projects", "settings", "connections", "session", "environment", "variables", "apis", "structures", "extensions", "codeapp", "scm", "data"];
// The pages a row of the Environment opens into: the rail marks Environment while one shows.
const UNDER_ENVIRONMENT: readonly string[] = ["structures", "variables"];
// The areas an on extension names with a page drawn from data (extensionArea.ts), each its own layer.
const DATA_AREAS = new Set<string>();
const isLayer = (name: string | null): name is Area => LAYERS.includes(name as Area) || DATA_AREAS.has(name ?? "");
const isArea = (name: unknown): name is Area => AREAS.some((a) => a.area === name) || DATA_AREAS.has(String(name));
const kindOfArea = (area: Area): Kind | undefined => AREAS.find((a) => a.area === area)?.kind;
const areaOfKind = (kind: string | null): Area | null => AREAS.find((a) => a.kind === kind)?.area ?? null;

const LAYER_OFF = { open: null, at: null, type: null, name: null, q: null, kinds: null, connection: null, column: null };

let kind: PageKind = "home";
let items: HTMLButtonElement[] = [];

/** The area the address names on this page (null: none, a Workbench with no document of a kind). */
function currentArea(url: URL): Area | null {
  const open = url.searchParams.get("open");
  if (open && UNDER_ENVIRONMENT.includes(open)) return "environment";
  if (isLayer(open)) return open;
  if (kind === "catalog") return "blades";
  if (kind === "canvas") return "canvas";
  if (kind === "workbench" && url.searchParams.get("pane") === "blades") return "blades"; // the Scripts page's Blades
  if (kind === "workbench") return areaOfKind(url.searchParams.get("kind")) ?? (thisPage() === "scripts" ? "scripts" : "notebooks");
  const view = kind === "home" ? url.searchParams.get("view") : null;
  if (view === "analyze") return "analyze";
  if (view === "erd") return "erd";
  if (view === "start") return "projects"; // the old Start view's address (one release): Projects
  return "grids"; // the grids (and the steps and Key Finder windows, which are a grid's)
}

/** A home window opened for `area`: the area in its address. */
function arrivalUrl(area: Area): string {
  if (area === "analyze" || area === "erd") return `${HOME_URL}?view=${area}`;
  if (area === "projects") return PROJECTS_URL;
  if (isLayer(area)) return `${HOME_URL}?open=${area}`;
  return HOME_URL;
}

const withToken = (path: string, more: Record<string, string> = {}): string => {
  const hash = new URLSearchParams({ ...(token ? { token } : {}), ...more }).toString();
  return hash ? `${path}#${hash}` : path;
};

/** A Workbench window of its own for `kind` (the owner's "external tab"), as a popped-out tab's. */
function newKindWindow(k: Kind): void {
  const opened = window.open(withToken(`/${pageOfKind(k) ?? "notebooks"}?kind=${k}`, { fresh: "1", popped: "1" }), `swissarmybench-workbench-${Date.now()}`, "popup,width=1200,height=800");
  if (opened) opened.focus();
  else errorHere("The browser blocked the new window: allow pop-ups for this address.");
}


/** The Widgets window (one of its own, brought forward when it is open), optionally on one widget. */
export function openWidgets(name?: string): void {
  const opened = window.open(withToken(`/streamlit/widget${name ? `?name=${encodeURIComponent(name)}` : ""}`), "sab-widgets", "popup,width=1300,height=820");
  if (opened) opened.focus();
  else errorHere("The browser blocked the new window: allow pop-ups for this address.");
}

/** The page that shows `area`, at the area's address. */
function pageUrl(area: Area): string {
  const k = kindOfArea(area);
  if (k) return `/${pageOfKind(k) ?? "notebooks"}?kind=${k}&view=list`; // that kind's page (workbenchPages.ts)
  // Blades live on the Scripts page, under its files (the owner, 2026-11-21: "navigation on top, blade on bottom").
  if (area === "blades") return "/scripts?kind=script&pane=blades";
  if (area === "canvas") return "/streamlit/canvas";
  return arrivalUrl(area);
}

/** Go to `area`, as its click does: in this tab (the owner, 2026-11-16: "the rail icons is opening a new
 *  tab every time instead of navigating the current page, the open in new tab is optional"). The page
 *  that shows the area moves here, or this tab goes to it; `newWindow` (right-click, Ctrl+click, a middle
 *  click) opens it in a window of its own instead. */
export function goArea(area: Area, newWindow = false): void {
  if (isClosed(area)) {
    showGateLine(area); // a feature this project's type keeps closed: one line, Open every feature
    return;
  }
  if (area === "widgets") {
    openWidgets();
    return;
  }
  const k = kindOfArea(area);
  if (newWindow) {
    if (k) newKindWindow(k);
    else if (!window.open(withToken(pageUrl(area)), "_blank")) errorHere("The browser blocked the new window: allow pop-ups for this address.");
    return;
  }
  if (area === "blades" && kind === "workbench" && thisPage() === "scripts") {
    // Here: the Blades pane unfolded and focused (workbenchPage.ts listens).
    visit(withParams({ ...LAYER_OFF, pane: "blades" }));
    window.dispatchEvent(new CustomEvent("sab-blades"));
    return;
  }
  if (area === "blades" && kind === "workbench") {
    const other = window.open("", PAGE_WINDOWS.scripts);
    let fresh = true;
    try {
      fresh = !other || other.location.href === "about:blank";
    } catch {
      fresh = true;
    }
    if (other && !fresh) other.postMessage({ sab: "area", area }, location.origin);
    else if (other) other.location.href = withToken(pageUrl(area));
    other?.focus();
    return;
  }
  if (k && kind === "workbench") {
    const page = pageOfKind(k) ?? "notebooks";
    if (page === thisPage()) {
      // That kind's landing page, here (the page over it, if one is, makes way).
      visit(withParams({ ...LAYER_OFF, kind: k, view: "list" }));
      return;
    }
    // The other page (Notebooks or Scripts): its own window, brought forward (never its tabs here: the owner,
    // 2026-11-21), and told to show the area; opened at it when there is none.
    const other = window.open("", PAGE_WINDOWS[page]);
    let fresh = true;
    try {
      fresh = !other || other.location.href === "about:blank";
    } catch {
      fresh = true;
    }
    if (other && !fresh) {
      other.postMessage({ sab: "area", area }, location.origin);
      other.focus();
    } else if (other) {
      other.location.href = withToken(pageUrl(area));
      other.focus();
    } else errorHere("The browser blocked the new window: allow pop-ups for this address.");
    return;
  }
  if (kind === "home" && (area === "grids" || area === "analyze" || area === "erd")) {
    visit(withParams({ ...LAYER_OFF, view: area === "grids" ? null : area }, HOME_URL));
    return;
  }
  if (isLayer(area) && hasLayer(area)) {
    openLayer(area);
    return;
  }
  // Projects is the home window's: another window brings it forward showing Projects (its Workbench kernels
  // stay where they are).
  if (area === "projects") {
    goHome();
    return;
  }
  if (area === "blades" && kind === "catalog") {
    if (layerShown() || new URLSearchParams(location.search).get("open")) visit(withParams(LAYER_OFF)); // the page makes way
    return;
  }
  // Another page shows it: this tab goes there (the Workbench asks first when an edit is unsaved).
  location.assign(withToken(pageUrl(area)));
}

/** An address on a closed area: its page covered by the one line (not seen behind it); elsewhere, no cover. */
function coverIfClosed(url: URL): void {
  const now = currentArea(url);
  if (now && isClosed(now)) showGateLine(now, true);
  else removeGateCover();
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
  const shown = items.filter((i) => !i.hidden);
  const at = shown.indexOf(e.target as HTMLButtonElement);
  if (at < 0 || e.altKey || e.ctrlKey || e.metaKey) return;
  const to = { ArrowDown: at + 1, ArrowRight: at + 1, ArrowUp: at - 1, ArrowLeft: at - 1, Home: 0, End: shown.length - 1 }[e.key];
  if (to === undefined) return;
  e.preventDefault();
  const next = shown[(to + shown.length) % shown.length]!;
  for (const item of items) item.tabIndex = item === next ? 0 : -1;
  next.focus();
}

function item(area: (typeof AREAS)[number]): HTMLButtonElement {
  const element = h(
    "button",
    {
      type: "button",
      class: ["nav-rail-item", area.area === "projects" ? "nav-rail-mark" : "", area.area === "extensions" ? "nav-rail-bottom" : "", area.kind ? `nav-rail-kind km-${area.kind}` : ""].filter(Boolean).join(" "),
      "data-area": area.area,
      "aria-label": area.name,
      "aria-keyshortcuts": area.keys,
      // Ctrl+click (Cmd+click): a new window, as a link's new tab.
      onclick: (e: MouseEvent) => goArea(area.area, e.ctrlKey || e.metaKey),
    },
    icon(area.icon),
    // The Session icon: what the agent made that the user has not seen yet (sessionPage.ts).
    area.area === "session" ? h("span", { class: "nav-rail-count", "aria-hidden": "true", hidden: true }) : null,
    // The name beside the icon while the rail shows its names (showNames).
    h("span", { class: "nav-rail-name", "aria-hidden": "true" }, area.name),
    // The name, on hover and on focus (a `title` would show the same words a second time).
    h("span", { class: "nav-rail-tip", "aria-hidden": "true" }, area.name, area.keys ? h("kbd", {}, area.keys) : null),
  );
  if (area.plugin) {
    element.hidden = true;
    void area.plugin().then((on) => {
      element.hidden = !on;
      // The Git extension's area: its name as the backend gives it.
      if (on && area.area === "scm") {
        element.setAttribute("aria-label", SCM);
        for (const part of element.querySelectorAll(".nav-rail-name")) part.textContent = SCM;
        element.querySelector(".nav-rail-tip")?.firstChild?.replaceWith(document.createTextNode(SCM));
      }
    });
  }
  {
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
      openMenu(
        element,
        area.name,
        [
          { label: "Open in a new window", icon: "popout", run: () => goArea(area.area, true) },
          { label: names ? "Icons only" : "Show names", icon: names ? "collapse" : "expand", run: () => void setRailNames(!names) },
        ],
        { beside: true },
      );
    });
  }
  return element;
}

// ===== the rail's names =====

const NAMES_KEY = "sab.railNames";
let names = true;
let toggle: HTMLButtonElement | null = null;

function showNames(on: boolean): void {
  names = on;
  document.documentElement.classList.toggle("rail-names", on);
  try {
    localStorage.setItem(NAMES_KEY, on ? "1" : "0");
  } catch {
    /* no storage: the server's answer still holds */
  }
  if (toggle) {
    const label = on ? "Icons only" : "Show names";
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
    toggle.setAttribute("aria-expanded", String(on));
    toggle.replaceChildren(icon(on ? "collapse" : "expand"), h("span", { class: "nav-rail-name", "aria-hidden": "true" }, label));
  }
  // The page's width changed: the grid, Monaco and the canvas measure again.
  window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
}

/** The rail with its names (true) or the icons alone; every window follows. */
export async function setRailNames(on: boolean): Promise<void> {
  showNames(on);
  try {
    showNames((await api<{ labels: boolean }>("/rail", "PUT", { labels: on })).labels);
  } catch (error) {
    errorHere(error);
  }
}

function startNames(): void {
  let kept: string | null = null;
  try {
    kept = localStorage.getItem(NAMES_KEY);
  } catch {
    /* no storage */
  }
  showNames(kept !== "0"); // a first run: the names
  void api<{ labels: boolean }>("/rail")
    .then((said) => {
      if (said.labels !== names) showNames(said.labels);
    })
    .catch(() => undefined);
  onNotice((notice) => {
    if (notice.type === "rail_changed") showNames(Boolean((notice as unknown as { labels: boolean }).labels));
  });
}

/** Each page's composition mounts the rail once (mountNavRail), right after mountNav. */
export function mountNavRail(page: PageKind): void {
  kind = page;
  items = AREAS.map(item);
  const toolbar = h("div", { class: "nav-rail-items", role: "toolbar", "aria-label": "Areas", "aria-orientation": "vertical", onkeydown: onKey }, ...items);
  toggle = h("button", { type: "button", class: "nav-rail-toggle", onclick: () => void setRailNames(!names) });
  document.body.prepend(h("nav", { class: "nav-rail", "aria-label": "Areas" }, toolbar, toggle));
  startNames();
  document.body.classList.add("has-rail");
  draw(new URL(location.href));
  onAddress(draw);
  onAddress(coverIfClosed);
  // An extension's areas drawn from data, before Session (their pages registered as layers).
  void panelAreas().then((found) => {
    const before = items.find((i) => i.dataset.area === "session") ?? null;
    for (const area of found) {
      if (items.some((i) => i.dataset.area === area.area)) continue;
      DATA_AREAS.add(area.area);
      const made = item({ area: area.area as Area, name: area.name, icon: area.icon });
      items.splice(before ? items.indexOf(before) : items.length, 0, made);
      toolbar.insertBefore(made, before);
    }
    draw(new URL(location.href));
  });
  // A project type's gates: its closed areas hidden here; an address that names one says so in one line.
  onGates(() => {
    for (const i of items) i.toggleAttribute("data-gated", isClosed(i.dataset.area ?? ""));
    coverIfClosed(new URL(location.href));
  });
  void loadGates();
  firstOpen(() => goArea("settings"));
  // The Session icon's count, and its name with the count for a screen reader.
  const session = items.find((i) => i.dataset.area === "session");
  onUnseen((n) => {
    const count = session?.querySelector<HTMLElement>(".nav-rail-count");
    if (!session || !count) return;
    count.hidden = n === 0;
    count.textContent = n > 99 ? "99+" : String(n);
    session.setAttribute("aria-label", n ? `Session, ${n} new` : "Session");
  });
  setAreaRunner((area, newWindow) => {
    if (!isArea(area)) return false;
    goArea(area, newWindow);
    return true;
  });
  // Another window's rail: the area it asked this window for (a message from this origin only).
  window.addEventListener("message", (e: MessageEvent) => {
    const said = e.data as { sab?: unknown; area?: unknown } | null;
    if (e.origin !== location.origin || said?.sab !== "area") return;
    if (said.area === "home") goHome(); // another window's mark: Home (Projects)
    else if (isArea(said.area)) goArea(said.area);
  });
}
