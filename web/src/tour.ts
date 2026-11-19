/**
 * The tour: what every place in Swiss Army Bench is for, for a first-time user. Its button sits on the
 * Projects page only (projectsPage.ts; the owner, 2026-11-16: "new here take a tour should be on the project
 * page and no where else"); until it has been opened once, a small "New here?" bubble sits beside it
 * (inline, so it never covers anything).
 *
 *   [TOUR]    the Projects page (the rail's mark) -> openTour()
 *   [GUIDED]  the owner, 2026-11-18: "the tutorial needs to move and highlight the item it is talking about,
 *             so the tutorial might need to stage a couple tables in the grid then remove them. it will need
 *             to navigate to pages as it goes and those descriptions could use a bit more detail". A card per
 *             place, in the rail's order: the tour goes there with the rail's own moves (nav.ts runArea, the
 *             grids' activateGrid and splitWith), waits a moment for the real control, scrolls it into view
 *             and lights it up (a spotlight); a control that does not come sits the card in the middle with
 *             "Not here right now." Back goes to the previous card's place. The Workbench and the blades
 *             page are other pages: their cards light the rail's icon and say so.
 *   [STAGED]  two small made-up tables (orders and customers sharing customer_id), pasted as the page's
 *             Ctrl+V pastes (POST /datasets/{name}/paste), named so they never take an open table's name,
 *             the orders sorted so Steps has one to show. Closing the tour at any point (Escape, Skip, the
 *             last card) closes exactly those two (DELETE /datasets/{name}, as the Open list's close) and
 *             goes back to where the tour started (nav.ts returnTo); the user's own tables stay as they were.
 *   [GAME]    five "which word is this?" rounds from the cards' clues, then a score drawn as opened blades.
 *
 * Keys: Right or Enter = next, Left = back, Escape = close (heard on the window while the tour is open, so
 * a page that takes the focus does not take the keys). Nothing is kept but "seen" in this browser
 * (dom.remember). A teaching aid of the page only: the agent has no command for it (docs/ideas.md).
 */

import { tourCards } from "./gates";
import { api, failure, token } from "./api";
import { button, h, icon, recall, remember } from "./dom";
import { here, historyDepth, layerShown, returnTo, runArea, visit, withParams } from "./nav";
import { forgetVariables, namesVariable, previewLine } from "./variableBox";
import { activateGrid, contextOf, splitPair, splitWith, unsplit } from "./panes";

/** Where a card takes the user: a rail's area, the tour's orders table, the two side by side, or a new
 *  connection's form (its type) with `text` typed into one of its boxes (a setting's name). */
type Place = { area: string } | { grid: "orders" | "pair" } | { form: string; setting: string; text: string };

interface Stop {
  icon: string;
  word: string;
  /** What it is, when you would use it, and how to reach it. */
  line: string;
  /** One line for the game: what it is, without its name. */
  clue: string;
  place?: Place;
  /** CSS selectors for the control to light up, tried in order; the first visible match wins.
   *  `{orders}` is the tour's orders grid. */
  target?: readonly string[];
  /** A line of code, when it is something you type. */
  code?: string;
  /** Shown only when this says so (an extension's area). */
  when?: () => boolean;
  /** A hands-on card: a practice box in the card, done once a variable is put in by typing (`type`) or by the
   *  right-click menu's Insert variable… (`menu`); Next waits for it, Skip, Back and Escape never do. */
  practice?: "type" | "menu";
}

/** The made-up variable the practice boxes offer, added for the tour when this computer has none of that name
 *  and removed when it ends (like its tables). */
const PRACTICE_VARIABLE = "TOUR_WAREHOUSE_HOST";
const PRACTICE_VALUE = "warehouse.example.com";
const HINT_MS = 8000;

const rail = (area: string): string => `.nav-rail [data-area="${area}"]`;
const page = (key: string, selector: string): string => `.area-page[data-page="${key}"] ${selector}`;
const railShown = (area: string) => (): boolean => {
  const item = document.querySelector<HTMLElement>(rail(area));
  return !!item && !item.hidden;
};

export const STOPS: readonly Stop[] = [
  {
    icon: "star",
    word: "Hi!",
    line: "Swiss Army Bench keeps your tables live beside DuckDB SQL, on one screen. This tour walks the rail on the left from top to bottom and takes you to each place as it goes. It has opened two small made-up tables to show things on; they close when the tour ends.",
    clue: "",
  },
  {
    icon: "project",
    word: "Projects",
    line: "This page. A project is a folder: its notebooks, scripts and apps, and the tables it opens. New project starts one, a card opens one. The red mark at the top of the rail, or Alt+Home, brings you back here from anywhere.",
    clue: "Every project as a card; the red mark at the top of the rail brings it back.",
    place: { area: "projects" },
    target: [rail("projects")],
  },
  {
    icon: "plug",
    word: "Connections",
    line: "Where your data comes from: databases, files, Power BI, Dataverse, lakes or your own Python. Every connection lists its tables, and DuckDB SQL can name them by the connection. Click Connections on the rail, then Add connection.",
    clue: "Where your data comes from: a database, a file, Power BI.",
    place: { area: "connections" },
    target: [page("connections", ".area-page-actions .btn.primary"), page("connections", ".area-page-head")],
    code: "SELECT * FROM [Sales].orders",
  },
  {
    icon: "apis",
    word: "APIs",
    line: "Web services your tables can come from. Add API reads an OpenAPI document, or a few calls you describe, and each call that returns a table can be queried like any other. Click APIs on the rail, then Add API.",
    clue: "Web services, each call that returns a table queried like any other.",
    place: { area: "apis" },
    target: [page("apis", ".apis-add"), page("apis", ".area-page-head")],
  },
  {
    icon: "variables",
    word: "Variables",
    line: "Names for the settings and passwords your code reads, such as WAREHOUSE_PASSWORD. A value can live on this computer, in the keyring or in a key vault, so nothing secret sits in a notebook. Click Variables on the rail; key vaults are added here too.",
    clue: "Names for settings and passwords, the values kept out of your code.",
    place: { area: "variables" },
    target: [page("variables", ".variables-add"), page("variables", ".area-page-head")],
  },
  {
    icon: "variables",
    word: "Using a variable",
    line: "A dollar sign and a brace around a variable's name, typed into any box in the app (a connection's server or password, an API's address, a file path, a setting, a SQL query), always reads that variable from the Variables page at the moment it is used. The value stays out of shared files, and each computer fills in its own. Type a dollar sign and a brace, or right-click a box, to insert one.",
    clue: "Typed into a box, it reads its value from this computer at the moment it is used.",
    place: { form: "postgres", setting: "server", text: "${WAREHOUSE_HOST}" },
    target: [page("connections", '.field[data-setting="server"] .variable-box-row')],
    code: "${WAREHOUSE_HOST}",
  },
  {
    icon: "edit",
    word: "Type it",
    line: "Your turn. Type a dollar sign and an opening brace into this box, then pick a variable from the list that opens.",
    clue: "",
    practice: "type",
  },
  {
    icon: "variables",
    word: "Right-click it",
    line: "Or right-click inside any box and choose Insert variable… from the menu. Try it here.",
    clue: "",
    practice: "menu",
  },
  {
    icon: "data",
    word: "Data Catalog",
    line: "Every table and column your connections reach, in one place. Type a few letters to search them all, or browse a connection's tree, then open a table as a grid. Click Data Catalog on the rail.",
    clue: "Every table and column your connections reach. Browse it or search it.",
    place: { area: "data" },
    target: [page("data", ".ex-search"), page("data", ".area-page-head")],
  },
  {
    icon: "rows",
    word: "Grid",
    line: "A table, live: pushed from Python, opened from a file, pasted, or read from a connection. Each one gets a tab along the top; this one is the tour's. Drag a tab to move it, or right-click it to rename, compare or close it.",
    clue: "A table you pushed from Python. One tab each.",
    place: { grid: "orders" },
    target: ['.tabs-row .tab-item[data-grid="{orders}"]', ".tabs-row"],
    code: "sab.push(orders)",
  },
  {
    icon: "filter",
    word: "Ribbon",
    line: "Filter, sort, choose columns, group and clean, a click each. Your data never changes: every click adds a step on top of the original. The Column row under it acts on the columns you select.",
    clue: "Filter, sort, clean. Your data never changes.",
    place: { grid: "orders" },
    target: ['.ribbon-group[aria-label^="Table tools"]', ".ribbon"],
  },
  {
    icon: "steps",
    word: "Steps",
    line: "Every click is a step, in order, and together they make one DuckDB query. Ctrl+Z undoes the last one, and View steps lists them all to change or remove any one. The tour sorted its orders by amount, so there is one to see.",
    clue: "Every click, in order, as one DuckDB query. Ctrl+Z undoes the last.",
    place: { grid: "orders" },
    target: [".steps-strip"],
  },
  {
    icon: "profile",
    word: "Profile",
    line: "A column at a glance: how many are blank, the most common values, and how the numbers spread. Click Profile in the Table row for every column, or select a column and use Profile in the Column row.",
    clue: "A column at a glance: blanks, top values, spread.",
    place: { grid: "orders" },
    target: ['.ribbon-group[aria-label^="Table tools"] [aria-label="Profile"]'],
  },
  {
    icon: "columns",
    word: "Compare",
    line: "Two tables side by side, matched row by row on the keys you pick. See what matches, what is on one side only and which values differ. Drag one tab onto another, or right-click a tab and choose Compare with.",
    clue: "Two tables side by side, row by row.",
    place: { grid: "pair" },
    target: ['.ribbon-group[aria-label^="Compare tools"]', ".tabs-row"],
  },
  {
    icon: "zoom",
    word: "Key Finder",
    line: "Finds the columns two tables share and how well they would join, such as customer_id here. Use it before a compare or a join when you are not sure which columns line up. Click Key Finder in the Table row; it opens in a window of its own.",
    clue: "Finds the columns two tables share.",
    place: { grid: "pair" },
    target: ['.ribbon [aria-label="Key Finder"]'],
  },
  {
    icon: "crown",
    word: "Relationships",
    line: "The joins between your tables, kept as a set you can save, share with your team and run to test. Click Relationships in the Table row to see the keys and joins in use.",
    clue: "Saved joins between tables. Run one to test it.",
    place: { grid: "pair" },
    target: ['.ribbon [aria-label="Relationships"]'],
  },
  {
    icon: "diagram",
    word: "ERD",
    line: "The keys and joins between your open tables, drawn as a diagram. Find relationships looks for them, or import a set you saved. Click ERD on the rail.",
    clue: "The keys and joins between your open tables, drawn.",
    place: { area: "erd" },
    target: ["#erd-view .erd-diagram", "#erd-view .btn.primary", "#erd-view"],
  },
  {
    icon: "structures",
    word: "Structures",
    line: "Nested data, such as JSON, YAML, XML and TOML, opened as a document. Walk its tree, pick and flatten parts with steps, then open the records as a grid. Click Structures on the rail, then New, Open or Paste.",
    clue: "Nested data as a document: walk its tree, flatten it into a grid.",
    place: { area: "structures" },
    target: [page("structures", ".area-page-actions"), page("structures", ".area-page-head")],
  },
  {
    icon: "blade",
    word: "Blades",
    line: "Saved Python that loads data, from a database query to a file reader, one file each. Run one from a notebook with sab.blade, or copy one from the starter pack. Click Blades on the rail; it opens the blades page.",
    clue: "Saved code that loads data: a database, a file.",
    target: [rail("blades")],
    code: 'conn = sab.blade("Warehouse")',
  },
  {
    icon: "notebook",
    word: "Notebooks",
    line: "Python, SQL and DAX cells on a live kernel, with every open table as a read-only cell holding its steps as DuckDB. Notebooks open in a window of their own, so code can sit on another screen. Click Notebooks on the rail.",
    clue: "Python and SQL cells, in a window of its own.",
    target: [rail("notebooks")],
  },
  {
    icon: "code",
    word: "Scripts",
    line: "A plain Python file, run top to bottom, with its run settings and a history of its runs. Use one for work you repeat on a schedule. Click Scripts on the rail; they open in the Workbench window too.",
    clue: "A plain Python file, run top to bottom, on a schedule if you like.",
    target: [rail("scripts")],
  },
  {
    icon: "page",
    word: "Apps",
    line: "A Streamlit app built from your notebook's cells, laid out on a canvas and played live in place. Export it to run on its own. Click Apps on the rail.",
    clue: "A Streamlit app laid out on a canvas from your notebook's cells.",
    target: [rail("apps")],
    when: railShown("apps"),
  },
  {
    icon: "image",
    word: "Analyze",
    line: "Every analysis across the top, in everyday words: odds, outliers, fit tests, regression, forecasts, tie-outs. The table is already picked, so you usually only press Run. Each result lands on the board below, with charts, notes and your own cards; save it as a dashboard or print it. Click Analyze on the rail.",
    clue: "Every analysis in one place; each result lands on the board.",
    place: { area: "analyze" },
    target: ["#ai-panel .analyze-toolbar", "#ai-panel"],
  },
  {
    icon: "session",
    word: "Session",
    line: "What happened this session, newest first: what you did and what your agent did. Each entry links to what it changed, and Follow the agent brings its work to the front as it happens. Click Session on the rail.",
    clue: "What you and your agent did this session, newest first.",
    place: { area: "session" },
    target: [page("session", ".area-page-actions"), page("session", ".area-page-head")],
  },
  {
    icon: "extensions",
    word: "Extensions",
    line: "Extra areas that plug into the same app: Streamlit apps, Accounting workbooks, Power Apps and more. One click installs or removes one. Click Extensions near the bottom of the rail.",
    clue: "Extra areas that plug into the same app, one click to install.",
    place: { area: "extensions" },
    target: [page("extensions", ".extension-card"), page("extensions", ".area-page-head")],
  },
  {
    icon: "cog",
    word: "Settings",
    line: "Your theme, the meta store folder your team shares, the projects folders, which panels show, and updates. Click Settings at the bottom of the rail.",
    clue: "Your theme, folders, panels and updates.",
    place: { area: "settings" },
    target: [page("settings", "fieldset"), page("settings", ".area-page-head")],
  },
  {
    icon: "agent",
    word: "Agent",
    line: "Your AI helper: whatever you can do here, it can do too, and it asks you before it exports or keeps rows. Launch Claude in the status bar starts it with this app's tools ready; its choices are here in Settings, under Claude.",
    clue: "Your AI helper. Sees what you see, asks before it exports.",
    place: { area: "settings" },
    target: [page("settings", ".claude-fieldset"), page("settings", ".area-page-head")],
  },
];

const ROUNDS = 5;
const SEEN = "tour.seen";
/** How long a card waits for its control before it says it is not here. */
const WAIT_MS = 2500;

/** The Projects page's Tour button, with the "New here?" bubble until the tour is opened once. While the bubble
 *  is there it is the one tour button (grid.css hides Tour beside it, feel-a: two said the same thing). */
export function tourButton(): HTMLElement {
  const btn = button("Tour", () => openTour(), {
    icon: "help",
    class: "ribbon-btn tour-btn",
    title: "What everything means: a guided tour",
  });
  btn.setAttribute("aria-haspopup", "dialog");
  if (recall(SEEN)) return btn;
  const bubble = h(
    "span",
    { class: "tour-bubble" },
    h("button", { type: "button", class: "tour-bubble-go", onclick: () => openTour() }, "New here? Take the tour"),
    button("Not now", () => markSeen(), { icon: "close", iconOnly: true, class: "ghost" }),
  );
  btn.classList.add("tour-new");
  return h("span", { class: "tour-slot" }, btn, bubble);
}

function markSeen(): void {
  remember(SEEN, "1");
  document.querySelectorAll(".tour-bubble").forEach((b) => b.remove());
  document.querySelectorAll(".tour-new").forEach((b) => b.classList.remove("tour-new"));
}

/** The first visible element for any of `selectors`, in their order, or null. */
function visible(selectors: readonly string[]): HTMLElement | null {
  for (const selector of selectors) {
    for (const el of document.querySelectorAll<HTMLElement>(selector)) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return el;
    }
  }
  return null;
}

function shuffled<T>(items: readonly T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j] as T, out[i] as T];
  }
  return out;
}

const pause = (ms: number): Promise<void> => new Promise((done) => window.setTimeout(done, ms));

// ===== the staged tables =====

interface Table {
  name: string;
  grid: string;
}
interface Staged {
  orders: Table;
  customers: Table;
  /** The orders' sort, added once the page holds the table (added before, the page could miss it). */
  sorted?: Promise<unknown>;
}

const CUSTOMERS = ["Ada Fernwood", "Bo Calder", "Cy Marlow", "Dee Ashby", "Eli Brook", "Fay Linden", "Gus Harrow", "Hal Penrose", "Ivy Tamsin", "Jo Quill", "Kit Rowan", "Lu Merrin"];
const CITIES = ["Northvale", "Easton Cove", "Westmere", "Southby"];
const PRODUCTS = ["Anvil", "Bolt", "Cog", "Dowel"];

/** Tab-separated text, as Excel copies it: the made-up customers and their orders. */
function tsv(rows: (string | number)[][]): string {
  return rows.map((r) => r.join("\t")).join("\n") + "\n";
}
const customersText = (): string => tsv([["customer_id", "name", "city"], ...CUSTOMERS.map((name, i) => [i + 1, name, CITIES[i % CITIES.length]!])]);
const ordersText = (): string =>
  tsv([
    ["order_id", "customer_id", "product", "quantity", "amount", "order_date"],
    ...Array.from({ length: 12 }, (_, i) => [1001 + i, ((i * 5) % 12) + 1, PRODUCTS[i % PRODUCTS.length]!, (i % 4) + 1, ((i * 37) % 90) + 12.5, `2026-0${(i % 9) + 1}-${String(10 + i).padStart(2, "0")}`]),
  ]);

/** A name no open table has: `base`, else base_2, base_3... */
function freeName(base: string, taken: Set<string>): string {
  let name = base;
  for (let n = 2; taken.has(name); n += 1) name = `${base}_${n}`;
  taken.add(name);
  return name;
}

async function paste(name: string, text: string): Promise<Table> {
  const response = await fetch(`/datasets/${encodeURIComponent(name)}/paste`, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: text });
  if (!response.ok) throw await failure(response);
  const shown = (await response.json()) as { grid: string; dataset: string };
  return { name: shown.dataset, grid: shown.grid };
}

/** Open the tour's two tables (the orders get their sort in toGrids, so Steps has one). Each table opened is
 *  handed to `opened` at once, so a close while staging still closes it. */
async function stage(opened: (t: Table) => void): Promise<Staged> {
  const taken = new Set((await api<{ datasets: { name: string }[] }>("/datasets")).datasets.map((d) => d.name));
  const customers = await paste(freeName("tour_customers", taken), customersText());
  opened(customers);
  const orders = await paste(freeName("tour_orders", taken), ordersText());
  opened(orders);
  return { orders, customers };
}

/** Close exactly the tables the tour opened. */
async function unstage(tables: readonly Table[]): Promise<void> {
  await Promise.all(tables.map((t) => api(`/datasets/${encodeURIComponent(t.name)}`, "DELETE").catch(() => undefined)));
}

/** Until `ready` holds (a tab that arrives by a notice), or `ms` passed. */
async function until(ready: () => boolean, ms = WAIT_MS): Promise<boolean> {
  for (const end = Date.now() + ms; Date.now() < end; await pause(80)) if (ready()) return true;
  return ready();
}

/** The grids, the tour's orders in front (its customers beside it for `pair`). */
async function toGrids(staged: Staged, pair: boolean): Promise<void> {
  const workspace = document.querySelector<HTMLElement>(".workspace");
  if (layerShown() || workspace?.dataset.view !== "grid") runArea("grids");
  const { orders, customers } = staged;
  if (!(await until(() => !!contextOf(orders.grid) && !!contextOf(customers.grid)))) return;
  // The sort for the Steps card, once the page holds the orders' grid, so its notice is heard.
  staged.sorted ??= api(`/grids/${encodeURIComponent(orders.grid)}/steps`, "POST", { steps: [{ kind: "sort", params: { keys: [["amount", "desc"]] } }] }).catch(() => undefined);
  await staged.sorted;
  const split = splitPair();
  const ours = !!split && split.some((c) => c.id === orders.grid) && split.some((c) => c.id === customers.grid);
  if (pair) {
    if (!ours) await splitWith(customers.grid, orders.grid, "right", true); // quiet: no key picker
    await activateGrid(orders.grid);
  } else if (ours) unsplit(orders.grid);
  else await activateGrid(orders.grid);
}

// ===== the tour =====

/** Whether the tour is on show: it moves the user itself, so a table that arrives meanwhile (its own staged
 *  tables among them) never takes the user anywhere (main.ts's grid_shown). */
export function touring(): boolean {
  return document.querySelector(".tour") !== null;
}

/** A gated project type's card: its area's rail icon and name, the mode's words (they are the game's clue too). */
function modeStop(card: { area: string; words: string }): Stop {
  const item = document.querySelector<HTMLElement>(rail(card.area));
  const word = item?.querySelector(".nav-rail-name")?.textContent?.trim() || item?.getAttribute("aria-label") || card.area;
  const icon = item?.querySelector("[data-icon]")?.getAttribute("data-icon") ?? "star";
  return { icon, word, line: card.words, clue: card.words, place: { area: card.area }, target: [rail(card.area)] };
}

export function openTour(): void {
  markSeen();
  document.querySelector(".tour")?.remove();
  const own = tourCards(); // a gated project type's own short list (its mode's tour)
  const stops = own ? [STOPS[0]!, ...own.map(modeStop)] : STOPS.filter((s) => !s.when || s.when());
  const before = document.activeElement as HTMLElement | null;
  const startUrl = here();
  const startDepth = historyDepth();
  const spot = h("div", { class: "tour-spot", "aria-hidden": "true" });
  const card = h("div", { class: "tour-card", "aria-live": "polite" });
  const root = h("div", { class: "tour", role: "dialog", "aria-modal": "true", "aria-label": "Tour" }, spot, card);
  let index = 0;
  let serial = 0; // the card on show: a slower move for an earlier card is dropped
  let closed = false;
  let place: () => void = () => undefined;
  let focusing: HTMLElement | null = null;
  const opened: Table[] = [];
  const staging = stage((t) => {
    if (closed) void unstage([t]);
    else opened.push(t);
  }).catch(() => null); // no tables (a refused paste): the cards that need them say "not here"

  // The practice cards' variable: added when the first of them shows and this computer has none of its name.
  let practiceVariable: Promise<boolean> | null = null;
  const stageVariable = (): Promise<boolean> =>
    (practiceVariable ??= api<{ variables: { name: string }[] }>("/variables")
      .then((r) => (r.variables.some((v) => v.name === PRACTICE_VARIABLE) ? false : api("/variables", "PUT", { name: PRACTICE_VARIABLE, value: PRACTICE_VALUE, from: "value" }).then(() => true)))
      .catch(() => false));
  const close = (): void => {
    if (closed) return;
    void practiceVariable?.then((made) => made && api(`/variables/${PRACTICE_VARIABLE}`, "DELETE").catch(() => undefined));
    closed = true;
    serial += 1;
    root.remove();
    window.removeEventListener("resize", onResize);
    window.removeEventListener("keydown", onKey, true);
    window.clearInterval(follow);
    const ours = [...opened];
    // Back where the tour started first, so a closed table's tab never takes the user anywhere.
    void returnTo(startDepth, startUrl)
      .then(() => unstage(ours))
      .then(() => {
        if (before?.isConnected) before.focus();
      });
  };
  const onResize = (): void => place();
  const onKey = (event: KeyboardEvent): void => {
    const typing = event.target instanceof HTMLInputElement && card.contains(event.target);
    const listOpen = !!document.querySelector(".variable-float, .context-menu");
    if (listOpen && ["Escape", "ArrowUp", "ArrowDown", "Enter", "Tab"].includes(event.key)) return; // the list's
    if (typing && ["ArrowLeft", "ArrowRight", "Enter"].includes(event.key)) return; // the box's own keys
    if (event.key === "Escape") close();
    else if (event.key === "ArrowRight" && index < stops.length && !card.querySelector(".tour-actions button.primary:disabled")) show(index + 1);
    else if (event.key === "ArrowLeft" && index > 0 && index < stops.length) show(index - 1);
    else if (event.key === "Enter" && !card.contains(event.target as Node) && focusing) focusing.click();
    else return;
    event.preventDefault();
    event.stopPropagation();
  };
  window.addEventListener("resize", onResize);
  window.addEventListener("keydown", onKey, true);
  // The page under it settles (a grid draws, a page loads its list): the spotlight follows its control.
  const follow = window.setInterval(() => place(), 300);
  // A click on the dimmed page closes nothing: an accidental click shouldn't lose your place.

  /** Light up `target` (or nothing) and put the card beside it, inside the window. */
  const aim = (target: HTMLElement | null, selectors: readonly string[] = []): void => {
    let el = target;
    place = () => {
      if (el && !el.isConnected) el = visible(selectors); // the page drew it again
      const gutter = 16;
      const width = Math.min(380, window.innerWidth - 2 * gutter);
      card.style.width = `${width}px`;
      const r = el?.getBoundingClientRect();
      if (!el || !r || r.width === 0) {
        root.classList.add("tour-dim");
        spot.hidden = true;
        card.style.left = `${(window.innerWidth - width) / 2}px`;
        card.style.top = `${Math.max(gutter, (window.innerHeight - card.offsetHeight) / 2)}px`;
        return;
      }
      root.classList.remove("tour-dim");
      spot.hidden = false;
      const pad = 6;
      Object.assign(spot.style, {
        left: `${r.left - pad}px`,
        top: `${r.top - pad}px`,
        width: `${r.width + 2 * pad}px`,
        height: `${r.height + 2 * pad}px`,
      });
      const below = r.bottom + pad + 12;
      const above = r.top - pad - 12 - card.offsetHeight;
      let top: number;
      let left: number;
      // A rail icon: the card beside it, so it never covers the icons under it.
      if (el.closest(".nav-rail")) top = -1;
      else if (below + card.offsetHeight + gutter <= window.innerHeight) top = below;
      else if (above >= gutter) top = above;
      else top = -1;
      if (top >= 0) {
        left = Math.min(Math.max(gutter, r.left + r.width / 2 - width / 2), window.innerWidth - width - gutter);
      } else {
        // A rail icon, or too tall for room above or below: beside it, on the side with room.
        top = Math.min(Math.max(gutter, r.top + r.height / 2 - card.offsetHeight / 2), window.innerHeight - card.offsetHeight - gutter);
        const right = r.right + pad + 12;
        left = right + width + gutter <= window.innerWidth ? right : Math.max(gutter, r.left - pad - 12 - width);
      }
      card.style.left = `${left}px`;
      card.style.top = `${Math.max(gutter, top)}px`;
    };
    place();
  };

  const dots = (at: number): HTMLElement =>
    h(
      "div",
      { class: "tour-dots", "aria-label": `${at + 1} of ${stops.length}` },
      ...stops.map((_, i) => h("span", { class: `tour-dot ${i < at ? "done" : i === at ? "here" : ""}` })),
    );

  /** Take the user to `stop`'s place: the rail's own move, or the tour's tables. */
  const goTo = async (stop: Stop): Promise<void> => {
    const to = stop.place;
    if (!to) return;
    if ("area" in to) {
      runArea(to.area);
      return;
    }
    if ("form" in to) {
      // A made-up connection's form, never saved: the tour's close goes back past it (returnTo).
      visit(withParams({ open: "connections", at: "form", type: to.form, name: null }));
      const box = `.area-page[data-page="connections"] .field[data-setting="${to.setting}"] input`;
      // The first form loads its types first (1-3 s on a busy computer).
      if (!(await until(() => !!visible([box]), 15000))) return;
      const input = visible([box]) as HTMLInputElement;
      if (input.value !== to.text) {
        input.value = to.text;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
      return;
    }
    const staged = await staging;
    if (staged) await toGrids(staged, to.grid === "pair");
  };

  /** A practice box for a hands-on card: done once it holds a variable; a hint after a while. */
  const practiceBox = (how: "type" | "menu", next: HTMLButtonElement, mine: number): HTMLElement => {
    next.disabled = true;
    // The box opens once the made-up variable is there, so the list always has one to pick.
    const box = h("input", { type: "text", class: "mono", "aria-label": "Server", spellcheck: false, autocomplete: "off", disabled: true }) as HTMLInputElement;
    void stageVariable().then(() => {
      forgetVariables();
      box.disabled = false;
      if (mine === serial && !done) box.focus();
    });
    const said = h("p", { class: "tour-practice-said", role: "status" });
    const { line, show: shown } = previewLine();
    let done = false;
    box.addEventListener("input", () => {
      if (done || !namesVariable(box.value)) return;
      done = true;
      said.textContent = "It worked. Here it reads:";
      said.classList.remove("tour-hint");
      void shown(box.value);
      next.disabled = false;
      focusing = next;
    });
    // A page the last card opened may still take the focus as it settles: the box keeps it for a moment.
    const keep = (event: FocusEvent): void => {
      const to = event.target as Element | null;
      if (mine === serial && !done && to && !card.contains(to) && !to.closest(".variable-float, .context-menu, dialog")) box.focus();
    };
    document.addEventListener("focusin", keep);
    window.setTimeout(() => document.removeEventListener("focusin", keep), 2500);
    window.setTimeout(() => {
      if (done || mine !== serial) return;
      said.textContent = how === "type" ? "Type a dollar sign, then an opening brace." : "Right-click inside the box.";
      said.classList.add("tour-hint");
    }, HINT_MS);
    return h("div", { class: "tour-practice", "data-practice": how }, h("label", { class: "field" }, h("span", {}, "Server"), box), said, line);
  };

  const show = (at: number): void => {
    index = at;
    const mine = ++serial;
    if (at >= stops.length) return game();
    const stop = stops[at] as Stop;
    const last = at === stops.length - 1;
    const next = button(last ? "Play" : "Next", () => show(at + 1), { icon: last ? "play" : "expand", class: "primary" });
    const missing = h("p", { class: "tour-missing", hidden: true }, "Not here right now.");
    card.replaceChildren(
      h("div", { class: "tour-icon" }, icon(stop.icon)),
      h("h2", { class: "tour-word" }, stop.word),
      h("p", { class: "tour-line" }, stop.line),
      stop.code ? h("code", { class: "tour-code" }, stop.code) : "",
      stop.practice ? practiceBox(stop.practice, next, mine) : "",
      missing,
      dots(at),
      h(
        "div",
        { class: "tour-actions" },
        button("Skip", close, { class: "ghost" }),
        at > 0 ? button("Back", () => show(at - 1), { icon: "back", class: "ghost" }) : null,
        next,
      ),
    );
    focusing = next;
    const practice = card.querySelector<HTMLInputElement>(".tour-practice input");
    (practice ?? next).focus();
    if (!stop.target) {
      aim(null);
      void goTo(stop);
      return;
    }
    aim(null);
    void (async () => {
      await goTo(stop);
      const staged = await staging;
      const selectors = (stop.target ?? []).map((s) => s.replace("{orders}", staged?.orders.grid ?? ""));
      await until(() => mine !== serial || !!visible(selectors));
      if (mine !== serial) return;
      const target = visible(selectors);
      missing.hidden = !!target;
      target?.scrollIntoView({ block: "nearest", inline: "nearest" });
      aim(target, selectors);
      // A page that opened took the focus: the card has it again.
      if (!card.contains(document.activeElement)) next.focus();
    })();
  };

  /** Five rounds of "which word is this?": the clue, three words to pick from. */
  const game = (): void => {
    const words = stops.filter((s) => s.clue);
    const rounds = shuffled(words).slice(0, ROUNDS);
    let round = 0;
    let score = 0;
    const play = (): void => {
      if (closed) return;
      if (round >= rounds.length) return finish();
      const answer = rounds[round] as Stop;
      const others = shuffled(words.filter((s) => s !== answer)).slice(0, 2);
      const choices = shuffled([answer, ...others]);
      const buttons = choices.map((choice) =>
        h(
          "button",
          {
            type: "button",
            class: "tour-choice",
            onclick: () => {
              buttons.forEach((b) => (b.disabled = true));
              const right = choice === answer;
              if (right) score++;
              buttons[choices.indexOf(answer)]?.classList.add("right");
              if (!right) buttons[choices.indexOf(choice)]?.classList.add("wrong");
              round++;
              window.setTimeout(play, right ? 650 : 1300);
            },
          },
          icon(choice.icon),
          h("span", {}, choice.word),
        ),
      );
      card.replaceChildren(
        h("p", { class: "tour-kicker" }, `Round ${round + 1} of ${rounds.length}`),
        h("p", { class: "tour-clue" }, answer.clue),
        h("div", { class: "tour-choices" }, ...buttons),
        h("div", { class: "tour-actions" }, button("Skip", finish, { class: "ghost" })),
      );
      aim(null);
      focusing = null;
      buttons[0]?.focus();
    };
    const finish = (): void => {
      if (closed) return;
      const cheer = score === rounds.length ? "Sharp!" : score >= 3 ? "Nicely done." : "You'll pick it up fast.";
      const knife = h(
        "div",
        { class: "tour-knife", "aria-label": `${score} of ${rounds.length}` },
        ...rounds.map((_, i) => h("span", { class: `tour-blade ${i < score ? "open" : ""}`, style: { "--i": String(i) } })),
        h("span", { class: "tour-handle" }),
      );
      const done = button("Start", close, { icon: "check", class: "primary" });
      card.replaceChildren(
        knife,
        h("h2", { class: "tour-word" }, `${score} of ${rounds.length}. ${cheer}`),
        h("p", { class: "tour-line" }, "Push a table from any Python to begin:"),
        h("code", { class: "tour-code" }, "import swissarmybench as sab\nsab.push(df)"),
        h("div", { class: "tour-actions" }, button("Again", () => show(0), { icon: "back", class: "ghost" }), done),
      );
      aim(null);
      focusing = done;
      done.focus();
    };
    play();
  };

  document.body.append(root);
  show(0);
}
