/**
 * catalogPage.ts: the blades and catalog page, in its own tab (plan decisions 14-18). [COMPOSITION]
 *
 * The rail (catalogRail.ts) on the left; the main area shows a table's columns with a first SELECT,
 * the blade save screen, or a welcome. Dragging gives plain text: a blade its `sab.blade(...)` line,
 * a table or column its quoted name.
 *
 * Getting around (nav.ts): the mark at the top-left brings the home window forward. Each view is in the
 * address, so the browser's Back and Forward move between them and a reload keeps the one shown:
 *   /catalog                                  the welcome            "Blades"
 *   ?catalog=Warehouse                        a catalog              "Blades · Warehouse"
 *   ?catalog=Warehouse&schema=sales           a schema (a dataset)   "Blades · Warehouse › sales"
 *   ?catalog=…&schema=…&table=orders          a table (&column=)     "Blades · Warehouse › sales › orders"
 *   ?blade=refresh_sales  ·  ?blade=          the editor, a new blade's templates
 * (&database= when the catalog has several.) A catalog's views carry a trail (Catalog › Warehouse › sales
 * › orders) and a Back named for the level above; the editor's Back is its Cancel.
 */
import { handleAgentNotice, loadApprovals } from "./agentAccess";
import { connect, onNotice, openedWith, requireSession } from "./api";
import { watchConnectionColours } from "./connectionColours";
import { type BladeKind, editBlade, showTemplatePicker } from "./bladeEditor";
import { type CatalogInfo, type CatalogPlace, mountRail, schemaDetails, tableDetails, type TableView, watchTheme } from "./catalogRail";
import { betaMark, mountBeta } from "./betaNotes";
import { installZoomInput, zoomControl } from "./zoom";
import { button, clear, formatCount, h, toast } from "./dom";
import { appMark, backButton, backTo, crumbs, go, type Move, mountNav, setTitle, startNav } from "./nav";
import { mountNavRail } from "./rail";
import "./settingsWindow"; // the rail's Settings opens here too (open=settings)

watchTheme();

const detail = document.getElementById("detail") as HTMLElement;
const liveNote = document.querySelector<HTMLElement>(".cat-live");
let editing = false; // the save screen holds work not saved yet
// No token and no good cookie (a bookmark after a restart): the page says how to open the app.
void requireSession();
watchConnectionColours(); // a connection's colour on its blade (connectionColours.ts)

const PAGE = "Blades";
const WELCOME = "/catalog";

/** A view's address on this page: only the words it needs. */
function address(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== undefined) search.set(key, value);
  const text = search.toString();
  return `${WELCOME}${text ? `?${text}` : ""}`;
}
const catalogUrl = (catalog: string): string => address({ catalog });
const schemaUrl = (catalog: string, schema: string, database?: string): string => address({ catalog, database, schema });

function showWelcome(how: Move = "auto"): void {
  editing = false;
  setTitle(PAGE);
  void go(WELCOME, how);
  clear(
    detail,
    h("h2", {}, "Blades and the catalog"),
    h("div", { class: "row-actions" }, button("New blade", () => openEditor(null), { icon: "plus", class: "primary" })),
  );
}

/** A catalog's own page: what it holds; its schemas are in the tree beside it. */
function showCatalog(info: CatalogInfo, how: Move = "auto"): void {
  setTitle(PAGE, info.name);
  void go(catalogUrl(info.name), how);
  const parts = [`${formatCount(info.schemas)} schema${info.schemas === 1 ? "" : "s"}`, `${formatCount(info.tables)} table${info.tables === 1 ? "" : "s"}`];
  if (info.views) parts.push(`${formatCount(info.views)} view${info.views === 1 ? "" : "s"}`);
  parts.push(`${formatCount(info.columns)} column${info.columns === 1 ? "" : "s"}`, info.dialect === "dax" ? "DAX" : info.dialect);
  clear(detail, h("div", { class: "row-actions" }, backButton(PAGE, WELCOME)), h("h2", {}, info.name), h("p", { class: "hint" }, parts.join(" · ")));
}

/** Nothing at the address (a table gone since, a blade removed): said, with the way back. */
function showMissing(words: string): void {
  editing = false;
  setTitle(PAGE);
  clear(detail, h("div", { class: "row-actions" }, backButton(PAGE, WELCOME)), h("p", { class: "status-error", role: "alert" }, words));
}

/** The blade the editor shows ("" a new one), while it is open. */
let editorOf: string | null = null;

function openEditor(name: string | null, how: Move = "auto"): void {
  editorOf = name ?? "";
  void go(address({ blade: editorOf }), how);
  setTitle(PAGE, name ?? "New blade");
  // The editor draws under its Back; Back (and Cancel) leave it for the welcome.
  const lead = h("div", { class: "row-actions" });
  const host = h("div", {});
  clear(detail, lead, host);
  const closed = (): void => {
    editing = false;
    rail.editorClosed();
    backTo(WELCOME);
  };
  lead.append(backButton(PAGE, WELCOME, () => {
    editing = false;
    rail.editorClosed();
  }));
  const saved = (savedName: string): void => {
    editing = false; // saved: nothing to lose, so a click in the tree shows what was clicked again
    rail.bladeSaved(savedName);
    editorOf = savedName;
    setTitle(PAGE, savedName);
    void go(address({ blade: savedName }), "replace"); // a new blade has its name now
  };
  if (name !== null) {
    editing = true;
    void editBlade(host, name, null, "other" as BladeKind, saved, closed);
    return;
  }
  editing = false;
  void showTemplatePicker(host, (template, kind) => {
    editing = true;
    void editBlade(host, null, template, kind, saved, closed);
  });
}

const rail = mountRail({
  bladesHost: document.getElementById("blades") as HTMLElement,
  catalogHost: document.getElementById("catalog") as HTMLElement,
  editBlade: (name) => openEditor(name),
  isEditing: () => editing,
  showTable: (view, how) => showTable(view, how),
  showSchema: (label, catalog, dialect, schema, note, database, how) => {
    setTitle(PAGE, `${catalog} › ${label}`);
    void go(schemaUrl(catalog, schema, database), how ?? "auto");
    clear(
      detail,
      crumbs([{ label: "Catalog", url: WELCOME }, { label: catalog, url: catalogUrl(catalog) }, { label }]),
      h("div", { class: "row-actions" }, backButton(catalog, catalogUrl(catalog))),
      ...schemaDetails(label, catalog, dialect, schema, note),
    );
  },
  catalogPicked: (info) => showCatalog(info),
});

function showTable(view: TableView, how: Move = "auto"): void {
  const schemaLabel = view.schemaLabel ?? view.schema ?? "";
  const up = schemaUrl(view.catalog, view.schema ?? "", view.database);
  setTitle(PAGE, `${view.catalog} › ${schemaLabel} › ${view.table}`);
  void go(address({ catalog: view.catalog, database: view.database, schema: view.schema ?? "", table: view.table, column: view.focusColumn }), how);
  clear(
    detail,
    crumbs([{ label: "Catalog", url: WELCOME }, { label: view.catalog, url: catalogUrl(view.catalog) }, { label: schemaLabel, url: up }, { label: view.table }]),
    h("div", { class: "row-actions" }, backButton(schemaLabel, up)),
    ...tableDetails(view),
  );
  detail.querySelector('[aria-current="true"]')?.scrollIntoView({ block: "nearest" });
}

/** Show what an address names (a reload, Back, Forward, a breadcrumb, the agent). */
async function showAddress(url: URL): Promise<void> {
  const params = url.searchParams;
  const blade = params.get("blade");
  const catalog = params.get("catalog");
  if (editing) {
    // The editor holds work: the browser's Back does not throw it away. It stays, its address in front.
    if (blade !== editorOf) {
      toast("Save or cancel the blade first.");
      void go(address({ blade: editorOf ?? "" }), "push");
    }
    return;
  }
  if (blade !== null) {
    if (blade && !rail.blades().some((b) => b.name === blade)) {
      showMissing(`There is no blade called ${blade}.`);
      return;
    }
    openEditor(blade || null, "replace");
    return;
  }
  if (catalog) {
    const place: CatalogPlace = { catalog };
    for (const key of ["database", "schema", "table", "column"] as const) {
      const value = params.get(key);
      if (value !== null) place[key] = value;
    }
    if (!(await rail.goTo(place, "replace"))) {
      showMissing(`${[place.catalog, place.schema, place.table].filter(Boolean).join(" › ")} is not in the catalog.`);
      return;
    }
    if (place.schema === undefined && place.table === undefined) {
      const info = rail.catalogs().find((c) => c.name.toLowerCase() === catalog.toLowerCase());
      if (info) showCatalog(info, "replace");
    }
    return;
  }
  showWelcome("replace");
}

const opened = new URL(location.href);
mountNav("catalog", { show: (url) => void showAddress(url) });
mountNavRail("catalog"); // the grids, Visualizations and the ERD are the home window's
document.querySelector(".cat-top")?.prepend(appMark());
setTitle(PAGE);
void rail
  .loadBlades()
  .then(() => rail.loadCatalogs(opened.searchParams.get("catalog") ?? openedWith.get("catalog") ?? undefined))
  .then(() => showAddress(opened))
  .then(() => startNav(opened));
connect((live) => {
  if (liveNote) liveNote.textContent = live ? "" : "Not connected to the server";
  if (live) void loadApprovals(); // an agent's request (an export, say) asks here too
}, { catalog: "1" });
onNotice((notice) => {
  handleAgentNotice(notice);
  if (notice.type === "catalogs_changed") void rail.loadCatalogs();
  if (notice.type === "blades_changed") void rail.loadBlades();
});

// Beta mode on the blades page: the right-click notes and the Beta mark, from the start (not after an editor closes).
mountBeta("catalog");
document.querySelector(".cat-top")?.append(zoomControl(), betaMark());
installZoomInput();
