/**
 * sessionPage.ts: the Session page, on the rail after Connections (the owner, 2026-11-16: "when the agent is
 * driving the app and adding things, I want to see objects that were created in a log make that a new
 * page called Session on the rail"), and Follow the agent ("lets make it so the AI agent can activate
 * things on the page, so when it working on a diagram I can what it in realtime"). [SHARED]
 *
 *   [LOG]     this session's entries, newest first, live (the `session_entry` notice): when, what (plain
 *             words), where (the area), each a link to its object: a grid, a card, a relationship, a
 *             connection, a blade, a notebook's cell. Names and counts only (domain/session_log.py).
 *   [FILTER]  The agent (the default) | Me | Both, remembered per viewer.
 *   [FOLLOW]  a switch here and in Settings (the server's, kept across restarts; the agent reads it and is
 *             refused the change). On: each agent action brings its area to the front in the home window
 *             (main.ts setFollower: the grids, Visualizations, the ERD), the object scrolled to and pulsed;
 *             a cell's in the Workbench window (workbenchPage.ts). Off: nothing moves.
 *   [WAIT]    never while the user types in a box, has a dialog open, or reads a page of the rail's
 *             (Session, Settings, Connections): the latest action waits until they leave it; the rail's
 *             Session icon counts what they have not seen.
 *   [PAGE]    a page of the rail's over any page (areaPage.ts), in the address as open=session.
 *
 * ROUTING: GET /session-log?who=  ·  PUT /session-log/follow {on}  ·  notices session_entry, session_follow
 */
import { api, onNotice, type Notice } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { openReference } from "./connectionsWindow";
import { button, h, icon, recall, remember, toast } from "./dom";
import { dismissDialog, go, homeWindow, HOME_URL, layerOpened, layerShown, registerLayer, runArea, setOverTitle, visit, watchLayerDialog, withParams } from "./nav";

export interface Target {
  place: "grid" | "dataset" | "card" | "relationship" | "connection" | "blade" | "cell" | "document" | "area";
  grid?: string;
  dataset?: string;
  card?: string;
  relationships?: string[];
  name?: string;
  path?: string;
  cell?: number | null;
  area?: string;
}

export interface Entry {
  id: number;
  time: string;
  actor: "agent" | "user";
  action: string;
  what: string;
  area: string;
  target: Target | null;
}

type Who = "agent" | "user" | "both";
const WHO: { who: Who; label: string }[] = [
  { who: "agent", label: "The agent" },
  { who: "user", label: "Me" },
  { who: "both", label: "Both" },
];
const AREA_NAMES: Record<string, string> = {
  grids: "Grids",
  visualizations: "Visualizations",
  erd: "ERD",
  notebooks: "Notebooks",
  scripts: "Scripts",
  apps: "Apps",
  blades: "Blades",
  connections: "Connections",
  project: "Project",
};
const AREA_ICONS: Record<string, string> = {
  grids: "grids",
  visualizations: "sandbox",
  erd: "diagram",
  notebooks: "notebook",
  scripts: "code",
  apps: "page",
  blades: "blade",
  connections: "plug",
  project: "folder",
};
/** How long an action waits for the user to leave a box or a dialog before it is only counted. */
const WAIT_MS = 60_000;

let entries: Entry[] = [];
let loaded = false;
let follow = true;
let unseen = 0;
const unseenListeners: ((n: number) => void)[] = [];
const followListeners: ((on: boolean) => void)[] = [];
let follower: ((entry: Entry) => boolean) | null = null;
let goer: ((target: Target) => boolean) | null = null;
let pending: { entry: Entry; at: number } | null = null;
let waiting = 0;

const who = (): Who => {
  const saved = recall("session.who");
  return saved === "user" || saved === "both" ? saved : "agent";
};

// ===== the page's hooks =====

/** The home page (main.ts): how it brings an agent's object to the front (true: it did). */
export function setFollower(run: (entry: Entry) => boolean): void {
  follower = run;
}

/** The home page (main.ts): how it goes to an object of its own (a grid, a card, a relationship). */
export function setGoer(go: (target: Target) => boolean): void {
  goer = go;
}

/** The rail's Session icon: what arrived from the agent that the user has not seen. */
export function onUnseen(listener: (n: number) => void): void {
  unseenListeners.push(listener);
  listener(unseen);
}

export function onFollow(listener: (on: boolean) => void): void {
  followListeners.push(listener);
}

export const following = (): boolean => follow;

function setUnseen(n: number): void {
  unseen = n;
  for (const listener of unseenListeners) listener(n);
}

/** A soft pulse on `element` (the theme's accent; a still outline when motion is reduced). */
export function pulse(element: Element | null | undefined, ms = 2400): void {
  if (!element) return;
  element.classList.remove("follow-pulse");
  void (element as HTMLElement).offsetWidth; // start the animation again
  element.classList.add("follow-pulse");
  window.setTimeout(() => element.classList.remove("follow-pulse"), ms);
}

// ===== the user is busy: never moved from under them =====

/** True while the user types in a box, has a dialog open, or reads a page of the rail's. */
export function userBusy(): boolean {
  if (document.querySelector("dialog[open], .wb-palette")) return true;
  if (layerShown()) return true;
  const active = document.activeElement;
  if (!(active instanceof HTMLElement)) return false;
  if (active.isContentEditable || active.closest(".monaco-editor")) return true;
  if (active instanceof HTMLTextAreaElement || active instanceof HTMLSelectElement) return true;
  return active instanceof HTMLInputElement && !["checkbox", "radio", "button", "submit", "range", "color", "file"].includes(active.type);
}

function tryFollow(entry: Entry): void {
  if (!follow || !follower || entry.actor !== "agent") return;
  if (userBusy()) {
    pending = { entry, at: Date.now() };
    if (!waiting) waiting = window.setInterval(retry, 400);
    return;
  }
  follower(entry);
}

function retry(): void {
  if (!pending || Date.now() - pending.at > WAIT_MS || !follow) {
    pending = null;
    window.clearInterval(waiting);
    waiting = 0;
    return;
  }
  if (userBusy()) return;
  const { entry } = pending;
  pending = null;
  window.clearInterval(waiting);
  waiting = 0;
  follower?.(entry);
}

// ===== the log =====

async function load(): Promise<void> {
  const got = await api<{ entries: Entry[]; follow: boolean }>("/session-log?who=both&limit=1000");
  // Notices that arrived while it loaded are kept (by their numbers).
  const known = new Set(got.entries.map((e) => e.id));
  entries = [...entries.filter((e) => !known.has(e.id)), ...got.entries].sort((a, b) => b.id - a.id);
  loaded = true;
  setFollowState(got.follow);
}

function setFollowState(on: boolean): void {
  if (on === follow) return;
  follow = on;
  for (const listener of followListeners) listener(on);
}

/** Follow the agent on or off (the user's: the Session page's switch, Settings'). */
export async function setFollow(on: boolean): Promise<void> {
  const done = await api<{ follow: boolean }>("/session-log/follow", "PUT", { on });
  setFollowState(done.follow);
}

/** The Follow switch, as the Session page and Settings show it. */
export function followSwitch(): HTMLElement {
  const input = h("input", { type: "checkbox", role: "switch", class: "switch-input", "aria-label": "Follow the agent", dataset: { follow: "1" } }) as HTMLInputElement;
  input.checked = follow;
  input.addEventListener("change", () => void setFollow(input.checked).catch((e: Error) => {
    input.checked = follow;
    toast(e.message, "error");
  }));
  onFollow((on) => (input.checked = on));
  if (!loaded) void load().then(() => (input.checked = follow)).catch(() => undefined);
  return h("label", { class: "autosave-switch follow-switch" }, input, h("span", {}, "Follow the agent"));
}

onNotice((notice: Notice) => {
  if (notice.type === "session_follow") setFollowState((notice as unknown as { follow: boolean }).follow);
  if (notice.type !== "session_entry") return;
  const entry = (notice as unknown as { entry: Entry }).entry;
  if (!entry || entries.some((e) => e.id === entry.id)) return;
  entries.unshift(entry);
  if (entries.length > 1000) entries.length = 1000;
  redraw?.();
  if (entry.actor !== "agent" || layerShown() === "session") return; // read on the page: seen
  if (follow && follower) {
    if (!userBusy()) {
      if (follower(entry)) return; // brought to the front: seen
    } else tryFollow(entry); // waits until they leave the box or the dialog; the rail counts it meanwhile
  }
  setUnseen(unseen + 1);
});

// ===== going to an entry's object =====

function arrivalUrl(t: Target): string {
  if (t.place === "grid" && t.grid) return `/g/${encodeURIComponent(t.grid)}`;
  if (t.place === "card") return `${HOME_URL}?view=visualizations`;
  if (t.place === "relationship") return `${HOME_URL}?view=erd`;
  if (t.place === "area" && (t.area === "visualizations" || t.area === "erd")) return `${HOME_URL}?view=${t.area}`;
  return HOME_URL;
}

/** An entry's link: its object, where it is (this page, the home window, the Workbench, a page). */
export function goToTarget(t: Target | null): void {
  if (!t) return;
  if ((t.place === "cell" || t.place === "document") && t.path) {
    const kind = t.path.endsWith(".stapp.json") ? "app" : t.path.endsWith(".ipynb") ? "notebook" : "script";
    void openReference({ document: t.path, title: t.path, kind, how: "", line: "", cell: t.cell ?? null }).catch((e: Error) => toast(e.message, "error"));
    return;
  }
  if (t.place === "connection" && t.name) {
    visit(withParams({ open: "connections", at: "detail", type: null, name: t.name }));
    return;
  }
  if (t.place === "blade" && t.name) {
    if (location.pathname === "/catalog") visit(withParams({ open: null, at: null, type: null, name: null, blade: t.name }, "/catalog"));
    else location.assign(`/catalog?blade=${encodeURIComponent(t.name)}`);
    return;
  }
  if (t.place === "area" && t.area && !["grids", "visualizations", "erd"].includes(t.area)) {
    if (t.area === "project") visit(withParams({ open: null, at: null, type: null, name: null, view: "start" }, HOME_URL));
    else runArea(t.area);
    return;
  }
  // The home page's own: a grid, a table, a card, a relationship, its views.
  if (goer) {
    // The page makes way with no history move of its own: the view's move is the entry, so Back
    // brings the Session page again.
    if (shownPage?.open) dismissDialog(shownPage);
    if (!goer(t)) toast("It is not open any more.", "error");
    // The same view as before (nothing to push): the page's words leave the address.
    window.setTimeout(() => {
      if (new URLSearchParams(location.search).get("open") === "session" && !shownPage?.open) void go(withParams({ open: null, at: null, type: null, name: null }), "replace");
    }, 300);
    return;
  }
  const found = homeWindow();
  if (!found) return;
  if (found.fresh) found.win.location.href = arrivalUrl(t);
  else found.win.postMessage({ sab: "session-go", target: t }, location.origin);
  found.win.focus();
}

// Another window's link: the home page goes to its object (a message from this origin only).
window.addEventListener("message", (e: MessageEvent) => {
  const said = e.data as { sab?: unknown; target?: Target } | null;
  if (e.origin !== location.origin || said?.sab !== "session-go" || !said.target || !goer) return;
  if (!goer(said.target)) toast("It is not open any more.", "error");
});

// ===== the page =====

function timeWord(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? "" : at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function entryRow(e: Entry): HTMLElement {
  const area = AREA_NAMES[e.area] ?? e.area;
  const what = h("span", { class: "session-what" }, e.what);
  return h(
    "li",
    { class: `session-entry by-${e.actor}`, "data-entry": String(e.id), "data-action": e.action },
    h("time", { class: "session-time", datetime: e.time }, timeWord(e.time)),
    h("span", { class: "session-area", title: area }, icon(AREA_ICONS[e.area] ?? "grids"), h("span", {}, area)),
    e.target
      ? h("button", { type: "button", class: "session-link", title: `Go to it (${area})`, onclick: () => goToTarget(e.target) }, what)
      : what,
    h("span", { class: `session-who ${e.actor}` }, e.actor === "agent" ? "Agent" : "You"),
  );
}

let shownPage: PageElement | null = null;
let redraw: (() => void) | null = null;

registerLayer("session", {
  isOpen: () => Boolean(shownPage?.open),
  open: () => drawSession(),
  show: () => undefined,
  dismiss: () => {
    if (shownPage) dismissDialog(shownPage);
  },
});

/** The Session page, opened by the user (the rail's icon). */
export function openSession(): void {
  if (shownPage?.open) return;
  layerOpened("session");
  drawSession();
}

function drawSession(): void {
  const { element, body, actions } = openAreaPage("session", "Session");
  shownPage = element;
  body.classList.add("session-page");
  setOverTitle("Session");
  setUnseen(0);
  const filter = h("div", { class: "segmented session-filter", role: "group", "aria-label": "Whose" });
  const list = h("ol", { class: "session-list", "aria-label": "This session", "aria-live": "polite" });
  const draw = (): void => {
    if (!element.open) return;
    const now = who();
    filter.replaceChildren(
      ...WHO.map((w) => {
        const b = button(w.label, () => {
          remember("session.who", w.who);
          draw();
        }, { pressed: now === w.who });
        b.dataset.who = w.who;
        return b;
      }),
    );
    const kept = entries.filter((e) => now === "both" || e.actor === now);
    if (!loaded) list.replaceChildren(h("li", { class: "hint" }, "Loading…"));
    else if (!kept.length) list.replaceChildren(h("li", { class: "empty-note" }, now === "user" ? "Nothing yet." : "Nothing from the agent yet."));
    else list.replaceChildren(...kept.map(entryRow));
    setUnseen(0);
  };
  redraw = draw;
  actions.replaceChildren(filter, followSwitch());
  body.append(list);
  watchLayerDialog(element, "session", [], () => {
    if (shownPage === element) shownPage = null;
    redraw = null;
  });
  draw();
  void load().then(draw, (e: Error) => list.replaceChildren(h("li", { class: "status-error" }, e.message)));
}

// The switch's state and what arrived before this page opened (a reload: the counted ones are gone).
void load().catch(() => undefined);
