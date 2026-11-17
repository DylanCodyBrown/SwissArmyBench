/**
 * catalogRail.ts: the blades and catalog navigation of the blades page. [VIEW]
 *
 * Blades (saved code that reaches outside Python to load something) above the Catalog (a source
 * database's names and types, as a tree: schema -> table or view -> column and its type, searchable).
 * The page that mounts it decides where a table's details and the blade editor show. A drag gives
 * plain text: a name, a query, or a blade's sab.blade line, to drop into Jupyter or an editor.
 *
 * The tree loads lazily, so a catalog of half a million columns opens at once.
 */
import { api, errorText, query } from "./api";
import { type BladeSummary, bladeLine, kindLabel, runBlade } from "./bladeEditor";
import { connectionIcon, importRelationships, openConnections } from "./connectionsWindow";
import { chooseBladeFiles, editBladeFolders, exportBlades, importBlades, openPacks } from "./bladeLibrary";
import { openImport } from "./projectImport";
import { button, clear, formatCount, h, icon, type MenuItem, recall, remember, showMenu, toast } from "./dom";
import type { Move } from "./nav";
import { copyAsOwn, SNIPPET_DRAG, type StarterSummary, starters } from "./starters";

// ===== shapes the server sends (server/routes_catalog.py) =====

export interface CatalogInfo {
  name: string;
  dialect: string;
  source: "load" | "blade";
  loaded_at: number;
  databases: number;
  schemas: number;
  tables: number;
  views: number;
  columns: number;
}

interface SchemaRow {
  database: string;
  schema: string;
  tables: number;
  views: number;
  /** What the source said of a schema it could not list (a Power BI workspace's dataset that could not be read). */
  note?: string;
}

interface TableRow {
  database: string;
  schema: string;
  table: string;
  kind: "table" | "view";
  columns: number;
  /** What the source calls it for people (a Dataverse table's display name). */
  title?: string;
}

export interface ColumnRow {
  column: string;
  type: string;
  nullable: boolean | null;
  position: number | null;
  description: string | null;
}

interface ColumnHit {
  database: string;
  schema: string;
  table: string;
  kind: "table" | "view";
  column: string;
  type: string;
}

interface SearchResult {
  tables: TableRow[];
  columns: ColumnHit[];
  total_tables: number;
  total_columns: number;
}

// ===== theme: the same choice as the grid page, without loading the grid library =====

export function applyTheme(): void {
  const choice = recall("theme") ?? "system";
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const more = matchMedia("(prefers-contrast: more)").matches;
  const resolved = choice !== "system" ? choice : more ? (dark ? "hc-dark" : "hc-light") : dark ? "dark" : "light";
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.setProperty("--ui-zoom", recall("zoom") ?? "1");
}
/** Follow the grid page's theme and zoom, now and as they change in another tab. */
export function watchTheme(): void {
  applyTheme();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
  window.addEventListener("storage", (event) => {
    if (event.key === "swissarmybench.theme" || event.key === "swissarmybench.zoom") applyTheme();
  });
}

// ===== what the page provides, and what the rail gives back =====

/** A table's details, for the page to show. */
export interface TableView {
  catalog: string;
  table: string;
  kind: "table" | "view";
  where: string; // "sales in Warehouse"
  /** What the source calls it for people, when that is more than its name (a Dataverse table's). */
  title?: string;
  name: string; // quoted for the source's dialect
  select: string; // a first SELECT, quoted for the dialect
  dialect: string;
  columns: ColumnRow[];
  focusColumn?: string;
  /** Where it is, as the catalog names it (for Open as grid and the preview, on its connection). */
  schema?: string;
  database?: string;
  /** Its schema as the tree shows it ("sales", "Model", "(no schema)"): the trail's middle crumb. */
  schemaLabel?: string;
}

/** Whether the current model already holds this dataset's relationships (its tables say where they came from). */
async function relationshipsImported(connection: string, dataset: string): Promise<boolean> {
  try {
    const model = await api<{ tables: Record<string, { source?: string }> }>("/relationships");
    const from = `${dataset ? `${connection}/${dataset}` : connection} (Power BI)`;
    return Object.values(model.tables).some((t) => t.source === from);
  } catch {
    return true; // not known: nothing extra is offered
  }
}

/** A catalog's table as a grid, on the connection the catalog came from (a catalog is named after it).
 * A Power BI workspace's table (`dax`) arrives with an offer to bring its dataset's relationships
 * too (the table's schema is its dataset), until they are in the model. */
export async function openTableAsGrid(catalog: string, where: { schema?: string; table: string; database?: string }, dax = false): Promise<void> {
  toast(`Opening ${where.table}…`);
  try {
    const answer = await api<{ dataset: string; shown?: number; total?: number | null }>(`/connections/${encodeURIComponent(catalog)}/open`, "POST", where);
    const cut = answer.total && answer.shown !== undefined && answer.total > answer.shown;
    const dataset = where.schema ?? "";
    const offer = dax && !(await relationshipsImported(catalog, dataset)) ? { label: "Import its relationships", run: () => void importRelationships(catalog, dataset) } : undefined;
    toast(cut ? `${answer.dataset}: the first ${answer.shown!.toLocaleString()} of ${answer.total!.toLocaleString()} rows open as a grid.` : `${answer.dataset} is open as a grid.`, "info", offer);
  } catch (e) {
    toast(errorText(e), "error");
  }
}

/** A table's first rows, beside its columns (fetched from its connection; nothing is kept). */
function previewOf(view: TableView): HTMLElement {
  const host = h("div", { class: "table-preview" }, h("p", { class: "hint" }, "Reading the first rows…"));
  const where = { schema: view.schema, table: view.table, database: view.database };
  void api<{ columns: string[]; rows: unknown[][] }>(`/connections/${encodeURIComponent(view.catalog)}/preview`, "POST", where).then(
    (found) =>
      host.replaceChildren(
        h(
          "table",
          { class: "columns-table preview-table", "aria-label": "First rows" },
          h("thead", {}, h("tr", {}, ...found.columns.map((c) => h("th", {}, c)))),
          h("tbody", {}, ...found.rows.map((r) => h("tr", {}, ...r.map((v) => h("td", {}, v === null ? "" : String(v)))))),
        ),
      ),
    (e: Error) => host.replaceChildren(h("p", { class: "hint" }, errorText(e).split("\n")[0] ?? "")),
  );
  return host;
}

export interface RailHost {
  bladesHost: HTMLElement;
  catalogHost: HTMLElement;
  /** Open the blade editor: a saved blade by name, or a new one (null). */
  editBlade(name: string | null): void;
  /** True while the editor holds unsaved work: the tree then keeps the page as it is. */
  isEditing(): boolean;
  /** `how`: a click is a move the user made (pushed into the address, nav.ts), an arrow key's walk
   *  through the tree is not (replaced), nor is showing an address. */
  showTable(view: TableView, how?: Move): void;
  /** A schema's page; a Power BI workspace's (`dialect` "dax") is a dataset: `schema` its name, `note`
   *  why it could not be read. */
  showSchema?(label: string, catalog: string, dialect: string, schema: string, note: string, database?: string, how?: Move): void;
  /** The catalog picked in the picker (the blades page shows it). */
  catalogPicked?(catalog: CatalogInfo): void;
  /** In the Workbench every connection is there by its name: drag and copy give the name alone. */
  connectionsByName?: boolean;
}

export interface Rail {
  loadBlades(): Promise<void>;
  loadCatalogs(select?: string): Promise<void>;
  /** The editor saved `name`: mark it and reload the list. */
  bladeSaved(name: string): void;
  /** The editor closed: nothing is marked. */
  editorClosed(): void;
  blades(): BladeSummary[];
  /** The loaded catalogs, and the one in the picker. */
  catalogs(): CatalogInfo[];
  current(): CatalogInfo | null;
  /** Open the tree at a place an address names, and show it (false: it is not there). */
  goTo(place: CatalogPlace, how?: Move): Promise<boolean>;
}

/** A place in the catalog, as the blades page's address names it. */
export interface CatalogPlace {
  catalog: string;
  database?: string;
  schema?: string;
  table?: string;
  column?: string;
}

/** Code and the imports it needs, carried beside a drag's plain text (for pages that place cells). */
export const DROP_TYPE = "application/x-sab-drop";

export function copy(text: string, what: string): void {
  void navigator.clipboard.writeText(text).then(
    () => toast(`Copied ${what}.`),
    () => toast("The browser did not allow copying.", "error"),
  );
}

/** A schema's page. A Power BI workspace's is one of its datasets, with Import its relationships; one
 * that could not be read says why instead. */
export function schemaDetails(label: string, catalog: string, dialect: string, schema = "", note = ""): HTMLElement[] {
  if (dialect !== "dax") return [h("h2", {}, label), h("p", { class: "hint" }, `Schema in ${catalog}`)];
  return [
    h("h2", {}, label),
    h("p", { class: "hint" }, `Dataset in ${catalog} · DAX`),
    note
      ? h("p", { class: "status-error", role: "alert" }, note)
      : h("div", { class: "row-actions" }, button("Import its relationships", () => void importRelationships(catalog, schema), { icon: "import", class: "primary" })),
  ];
}

/** A table's columns and a first SELECT (a Power BI dataset's: a first EVALUATE), for the page to show
 * (main area or dialog). */
export function tableDetails(view: TableView): HTMLElement[] {
  const dax = view.dialect === "dax";
  // A connection from the user's own Python has no SQL: its first line reads the table by its own code.
  const own = view.dialect === "python";
  const first = dax ? "EVALUATE" : own ? "line" : "SELECT";
  const measures = view.columns.filter((c) => c.type.startsWith("measure")).length;
  const counted = dax && measures ? `${view.columns.length - measures} columns, ${measures} measure${measures === 1 ? "" : "s"} · DAX` : `${view.columns.length} columns · ${dax ? "DAX" : own ? "Python" : view.dialect}`;
  const rows = view.columns.map((c) =>
    h(
      "tr",
      {
        "aria-current": c.column === view.focusColumn ? "true" : undefined,
        style: c.column === view.focusColumn ? { background: "var(--selected)" } : undefined,
      },
      h("td", {}, c.column),
      h("td", {}, c.type),
      h("td", {}, c.nullable === null ? "" : c.nullable ? "yes" : "no"),
      h("td", { class: "hint" }, c.description ?? ""),
    ),
  );
  return [
    h("h2", {}, view.table, view.kind === "view" ? h("span", { class: "hint" }, "  view") : null, view.title ? h("span", { class: "hint" }, `  ${view.title}`) : null),
    h("p", { class: "hint" }, `${view.where} · ${counted}`),
    h(
      "div",
      { class: "row-actions" },
      button("Open as grid", () => void openTableAsGrid(view.catalog, { schema: view.schema, table: view.table, database: view.database }, dax), { icon: "rows", class: "primary" }),
      button("Copy the name", () => copy(view.name, "the name"), { icon: "copy" }),
      button(`Copy the ${first}`, () => copy(view.select, `the ${first}`), { icon: own ? "code" : "sql" }),
    ),
    h("pre", { class: "code-box", "aria-label": own ? "The line that reads it" : `A first ${first}` }, view.select),
    h(
      "table",
      { class: "columns-table" },
      h("thead", {}, h("tr", {}, h("th", {}, "Column"), h("th", {}, "Type"), h("th", {}, "Nullable"), h("th", {}, "Description"))),
      h("tbody", {}, ...rows),
    ),
    // Its first rows, beside the columns (the page's empty side once).
    h("h3", {}, "First rows"),
    previewOf(view),
  ];
}

export function mountRail(host: RailHost): Rail {
  // ===== state =====

  const { bladesHost, catalogHost } = host;

  let blades: BladeSummary[] = [];
  let catalogs: CatalogInfo[] = [];
  let current: CatalogInfo | null = null;
  let selectedBlade: string | null = null;

  const catalogPath = (name: string): string => `/catalogs/${encodeURIComponent(name)}`;

  // ===== quoting for the source's dialect (as engine/catalog.py) =====

  function quoteName(name: string, dialect: string): string {
    if (dialect === "dax") return `'${name.replaceAll("'", "''")}'`; // a table: 'Order Lines'
    if (dialect === "sqlserver" || dialect === "dataverse") return `[${name.replaceAll("]", "]]")}]`;
    if (dialect === "mysql") return `\`${name.replaceAll("`", "``")}\``;
    return `"${name.replaceAll('"', '""')}"`;
  }

  function qualified(row: { database: string; schema: string; table: string }): string {
    const dialect = current?.dialect ?? "other";
    if (dialect === "dax") return quoteName(row.table, dialect); // the schema is the dataset the DAX is sent to
    if (dialect === "dataverse") return quoteName(row.table, dialect); // its one schema needs no naming
    const parts = [current && current.databases > 1 ? row.database : "", row.schema, row.table].filter(Boolean);
    return parts.map((p) => quoteName(p, dialect)).join(".");
  }

  // ===== blades =====

  let startersAsked: Promise<unknown> | null = null;
  // The open project's mode (app_mode): its blade families come first, the rest behind Every family.
  let modeFamilies: string[] = [];
  let everyFamily = false;
  async function loadBlades(): Promise<void> {
    // The starters come with the app and do not change while it runs: asked once, beside the first list.
    startersAsked ??= starters().then((found) => (starterFamilies = found), () => undefined);
    await api<{ mode: { families: string[] } }>("/app/mode").then((got) => {
      const fresh = (got.mode.families ?? []).filter((f) => !modeFamilies.includes(f));
      modeFamilies = got.mode.families ?? [];
      for (const family of fresh) openFamilies.add(family); // the mode's families open at first
    }, () => undefined);
    try {
      [blades] = await Promise.all([api<{ blades: BladeSummary[] }>("/blades").then((r) => r.blades), startersAsked]);
    } catch (error) {
      toast((error as Error).message, "error");
      blades = [];
    }
    renderBlades();
  }

  // The built-in starter pack, by family, after the user's own blades; each family folds (remembered
  // in this browser), and a search opens the families it finds something in.
  let starterFamilies: { family: string; blades: StarterSummary[] }[] = [];
  const openFamilies = new Set<string>((recall("starters.open") ?? "").split("|").filter(Boolean));

  function starterItem(starter: StarterSummary): HTMLElement {
    const snippet = starter.kind === "snippet";
    const language = starter.language ?? "streamlit";
    const line = snippet ? starter.name : bladeLine({ name: starter.name, kind: starter.kind as BladeSummary["kind"], variable: starter.variable });
    return h(
      "li",
      {
        class: "blade-item starter-item",
        draggable: "true",
        "data-starter": starter.name,
        "aria-current": starter.name === selectedBlade ? "true" : undefined,
        title: `${starter.description}${snippet ? "" : `\n${line}`}`,
        ondragstart: (event: DragEvent) => {
          event.dataTransfer?.setData("text/plain", line);
          if (snippet) event.dataTransfer?.setData(SNIPPET_DRAG, JSON.stringify({ name: starter.name, language }));
          else event.dataTransfer?.setData("application/x-sab-blade", JSON.stringify({ name: starter.name, kind: starter.kind, line }));
          if (event.dataTransfer) event.dataTransfer.effectAllowed = "copy";
        },
        oncontextmenu: (event: MouseEvent) => {
          event.preventDefault();
          showMenu(event.clientX, event.clientY, starter.name, [
            ["copy", "Copy as your own", () => void copyAsOwn(starter.name).then((made) => made && void loadBlades().then(() => openBlade(made)))],
            ["edit", "Open", () => openBlade(starter.name)],
            ...(snippet ? [] : [["code", "Copy the sab.blade line", () => copy(line, "the line")] as MenuItem]),
          ]);
        },
      },
      h("span", { class: `blade-kind ${snippet ? `snippet ${language}` : "other"}` }, icon(snippet ? (LANGUAGE_ICONS[language] ?? "copy") : "bolt"), snippet ? { dax: "DAX", html: "HTML", markdown: "Markdown", streamlit: "Streamlit", python: "Python", typescript: "TypeScript", tsx: "TSX" }[language] : "Python"),
      h("span", { class: "blade-text" }, h("button", { class: "blade-name", type: "button", onclick: () => openBlade(starter.name) }, starter.name)),
      button("Copy as your own", () => void copyAsOwn(starter.name).then((made) => made && void loadBlades().then(() => openBlade(made))), { icon: "copy", iconOnly: true, class: "ghost" }),
    );
  }

  function renderStarters(): void {
    const searching = bladeSearch.value.trim() !== "" || bladeTag !== null;
    const all = starterFamilies.map((f) => ({ family: f.family, shown: f.blades.filter((b) => bladeMatches(b)) })).filter((f) => f.shown.length);
    // The mode's families first (a code app's: TypeScript, React, Connectors); the others behind Every family.
    const mine = all.filter((f) => modeFamilies.includes(f.family)).sort((a, b) => modeFamilies.indexOf(a.family) - modeFamilies.indexOf(b.family));
    const others = all.filter((f) => !modeFamilies.includes(f.family));
    const families = modeFamilies.length && !everyFamily && !searching ? mine : [...mine, ...others];
    if (!all.length) return;
    bladeList.append(h("li", { class: "blade-group" }, h("span", {}, "Starters")));
    if (modeFamilies.length && !searching && others.length) {
      const more = h("button", { type: "button", class: "link starter-every", "aria-pressed": String(everyFamily), onclick: () => { everyFamily = !everyFamily; renderBladeList(); } }, everyFamily ? "This project's families only" : `Every family (${others.length} more)`);
      bladeList.append(h("li", { class: "starter-every-row" }, more));
    }
    for (const { family, shown } of families) {
      const open = searching || openFamilies.has(family);
      const toggle = h(
        "button",
        {
          type: "button",
          class: "starter-family",
          "aria-expanded": String(open),
          onclick: () => {
            if (openFamilies.has(family)) openFamilies.delete(family);
            else openFamilies.add(family);
            remember("starters.open", [...openFamilies].join("|"));
            renderBladeList();
          },
        },
        icon(open ? "down" : "forward"),
        h("span", { class: "starter-family-icon" }, icon(FAMILY_ICONS[family] ?? "bolt")),
        h("span", {}, family),
        h("span", { class: "hint" }, String(shown.length)),
      );
      bladeList.append(h("li", { class: "starter-family-row", "data-family": family }, toggle));
      if (open) for (const starter of shown) bladeList.append(starterItem(starter));
    }
  }

  // The blades list: a search (names, descriptions, tags), tag chips to narrow it, favourites first.
  let bladeTag: string | null = null;
  const bladeSearch = h("input", {
    class: "cat-search",
    type: "search",
    placeholder: "Search",
    "aria-label": "Search blades",
    spellcheck: "false",
  });
  bladeSearch.addEventListener("input", () => renderBladeList());
  const bladeTags = h("div", { class: "chips blade-tags", role: "group", "aria-label": "Tags" });
  const bladeList = h("ul", { class: "blade-list", "aria-label": "Saved blades" });

  function bladeMatches(blade: { name: string; description?: string; tags?: string[] }): boolean {
    const tags = blade.tags ?? [];
    if (bladeTag && !tags.some((t) => t.toLowerCase() === bladeTag)) return false;
    const text = bladeSearch.value.trim().toLowerCase();
    if (!text) return true;
    return [blade.name, blade.description ?? "", ...tags].some((field) => field.toLowerCase().includes(text));
  }

  async function setPinned(blade: BladeSummary, pinned: boolean): Promise<void> {
    try {
      await api(`/blades/${encodeURIComponent(blade.name)}/pin`, "PUT", { pinned });
      blade.pinned = pinned;
      renderBladeList();
    } catch (error) {
      toast((error as Error).message, "error");
    }
  }

  function renderBladeList(): void {
    // Every tag once (as first written), the chosen one pressed; a click narrows the list to it.
    const allTags = new Map<string, string>();
    for (const blade of blades) for (const tag of blade.tags ?? []) if (!allTags.has(tag.toLowerCase())) allTags.set(tag.toLowerCase(), tag);
    if (bladeTag && !allTags.has(bladeTag)) bladeTag = null;
    clear(
      bladeTags,
      ...[...allTags].sort(([a], [b]) => a.localeCompare(b)).map(([key, tag]) =>
        button(tag, () => {
          bladeTag = bladeTag === key ? null : key;
          renderBladeList();
        }, { class: "chip tag-chip", pressed: bladeTag === key, title: bladeTag === key ? "Clear filter" : undefined }),
      ),
    );
    bladeTags.hidden = allTags.size === 0;
    const shown = blades.filter(bladeMatches).sort((a, b) => Number(b.pinned) - Number(a.pinned));
    clear(bladeList);
    // Connections (databases and files) first, under their own heading; then the other blades.
    const connections = shown.filter((b) => b.connection);
    const others = shown.filter((b) => !b.connection);
    const heading = (text: string, extra: HTMLElement | null = null): HTMLElement => h("li", { class: "blade-group" }, h("span", {}, text), extra);
    if (connections.length || !blades.some((b) => b.connection)) {
      bladeList.append(heading("Connections", button("Add connection", () => void openConnections().then(() => void loadBlades()), { icon: "plus", iconOnly: true, class: "ghost" })));
    }
    let othersHeading = false;
    for (const blade of [...connections, ...others]) {
      if (!blade.connection && !othersHeading) {
        bladeList.append(heading("Blades"));
        othersHeading = true;
      }
      const line = host.connectionsByName && blade.code_name ? blade.code_name : bladeLine(blade);
      const item = h(
        "li",
        {
          class: "blade-item",
          draggable: "true",
          "aria-current": blade.name === selectedBlade ? "true" : undefined,
          title: `${blade.description ? blade.description + "\n" : ""}${line}`,
          ondragstart: (event: DragEvent) => {
            event.dataTransfer?.setData("text/plain", line);
            event.dataTransfer?.setData("application/x-sab-blade", JSON.stringify({ name: blade.name, kind: blade.kind, line }));
            event.dataTransfer?.setData(DROP_TYPE, JSON.stringify({ code: line, imports: ["import swissarmybench as sab"] }));
          },
        },
        button(blade.pinned ? "Unpin" : "Pin", () => void setPinned(blade, !blade.pinned), {
          icon: "star",
          iconOnly: true,
          class: `ghost star${blade.pinned ? " on" : ""}`,
          pressed: blade.pinned,
        }),
        blade.connection
          ? h("span", { class: `blade-kind ${blade.connection === "database" ? "sql" : "other"}` }, icon(connectionIcon(blade.template, blade.connection)), { database: "Database", file: "File", vault: "Key vault", python: "Python" }[blade.connection] ?? "File")
          : h("span", { class: `blade-kind ${blade.kind}` }, icon(BLADE_ICONS[blade.kind] ?? "bolt"), kindLabel(blade.kind)),
        h(
          "span",
          { class: "blade-text" },
          h("button", { class: "blade-name", type: "button", onclick: () => openBlade(blade.name) }, blade.name),
          host.connectionsByName && blade.code_name ? h("code", { class: "blade-code-name", title: "Name in code" }, blade.code_name) : null,
          blade.tags?.length ? h("span", { class: "blade-item-tags" }, blade.tags.join(" · ")) : null,
        ),
        blade.source === "folder" ? h("span", { class: "blade-file", title: blade.path ?? "" }, "file") : null,
        blade.source === "pack" ? h("span", { class: "blade-file blade-pack", title: `${blade.pack ?? ""}, read-only` }, "pack") : null,
        button(blade.connection ? "Copy the sab.connection line" : "Copy the sab.blade line", () => copy(line, "the line"), { icon: "copy", iconOnly: true, class: "ghost", title: line }),
      );
      bladeList.append(item);
    }
    renderStarters();
    if (!shown.length && blades.length && !bladeList.querySelector(".starter-item")) bladeList.append(h("li", { class: "empty" }, "No blade matches."));
  }

  function renderBlades(): void {
    clear(
      bladesHost,
      h(
        "div",
        { class: "rail-head" },
        h("h2", { id: "blades-title" }, "Connections and blades"),
        button("Import blades", () => chooseBladeFiles(() => void loadBlades()), { icon: "import", iconOnly: true, class: "ghost", title: "Import .blade.py or zip" }),
        // From another project, or this computer's saved blades (projectImport.ts).
        button("Import from a project", () => void openImport("blades").then((done) => done && loadBlades()), { icon: "project", iconOnly: true, class: "ghost", title: "From another project, or this computer's" }),
        button("Export every blade", () => void exportBlades(), { icon: "export", iconOnly: true, class: "ghost" }),
        button("Blade folders", () => void editBladeFolders(() => void loadBlades()), { icon: "folder", iconOnly: true, class: "ghost" }),
        button("Packs", () => void openPacks(() => void loadBlades()), { icon: "group", iconOnly: true, class: "ghost" }),
        button("New blade", () => void newBlade(), { icon: "plus", class: "ghost" }),
      ),
      // The list always shows (its Connections heading has Add connection); the search only once there is something to search.
      blades.length || starterFamilies.length
        ? h("div", {}, bladeSearch, bladeTags, bladeList)
        : h("div", {}, bladeList, h("p", { class: "empty" }, "No blades")),
    );
    renderBladeList();
  }

  // Dropping .blade.py, .py or .zip files on the blades opens the import review.
  bladesHost.addEventListener("dragover", (event) => {
    if (event.dataTransfer?.types.includes("Files")) {
      event.preventDefault();
      bladesHost.classList.add("dropping");
    }
  });
  bladesHost.addEventListener("dragleave", () => bladesHost.classList.remove("dropping"));
  bladesHost.addEventListener("drop", (event) => {
    bladesHost.classList.remove("dropping");
    const files = [...(event.dataTransfer?.files ?? [])];
    if (!files.length) return;
    event.preventDefault();
    void importBlades(files, () => void loadBlades());
  });

  async function newBlade(): Promise<void> {
    selectedBlade = null;
    renderBlades();
    host.editBlade(null);
  }

  function openBlade(name: string): void {
    selectedBlade = name;
    renderBlades();
    host.editBlade(name);
  }

  async function refresh(name: string): Promise<void> {
    toast(`Refreshing ${name}...`);
    const answer = await runBlade<{ catalog: CatalogInfo }>(name, "refresh");
    if (!answer) return;
    toast(`${name}: ${formatCount(answer.catalog.tables)} tables, ${formatCount(answer.catalog.columns)} columns.`);
    await loadCatalogs(answer.catalog.name);
  }

  // ===== catalogs: picker and search =====

  const picker = h("select", { "aria-label": "Catalog" });
  const search = h("input", {
    class: "cat-search",
    type: "search",
    placeholder: "Search",
    "aria-label": "Search the catalog",
    spellcheck: "false",
  });
  const tree = h("ul", { class: "cat-tree", role: "tree", "aria-label": "Catalog tree", tabindex: "0" });
  const results = h("div", { class: "cat-tree", hidden: true, role: "region", "aria-label": "Search results" });
  const catalogActions = h("span", { class: "row-actions" });

  async function loadCatalogs(select?: string): Promise<void> {
    try {
      catalogs = (await api<{ catalogs: CatalogInfo[] }>("/catalogs")).catalogs;
    } catch (error) {
      toast((error as Error).message, "error");
      catalogs = [];
    }
    const wanted = select ?? current?.name ?? recall("catalog");
    current = catalogs.find((c) => c.name.toLowerCase() === (wanted ?? "").toLowerCase()) ?? catalogs[0] ?? null;
    renderPicker();
    await showCatalog();
  }

  function renderPicker(): void {
    clear(picker);
    for (const c of catalogs) picker.append(h("option", { value: c.name, selected: c === current }, c.name));
    picker.disabled = catalogs.length === 0;
    const blade = current ? blades.find((b) => b.name.toLowerCase() === current?.name.toLowerCase() && b.has_catalog) : undefined;
    clear(
      catalogActions,
      blade ? button("Refresh", () => void refresh(blade.name), { icon: "play", iconOnly: true, class: "ghost", title: `Refresh ${blade.name}` }) : null,
      current
        ? button("Remove this catalog", () => {
            const target = current;
            if (!target) return;
            void api(catalogPath(target.name), "DELETE").then(() => {
              current = null;
              void loadCatalogs();
            }, (error: Error) => toast(error.message, "error"));
          }, { icon: "trash", iconOnly: true, class: "ghost" })
        : null,
    );
  }

  picker.addEventListener("change", () => {
    current = catalogs.find((c) => c.name === picker.value) ?? null;
    if (current) remember("catalog", current.name);
    renderPicker();
    void showCatalog();
    if (current) host.catalogPicked?.(current);
  });

  function renderCatalogSection(): void {
    clear(
      catalogHost,
      h("div", { class: "rail-head" }, h("h2", { id: "catalog-title" }, "Catalog")),
      h("div", { class: "catalog-picker" }, picker, catalogActions),
      search,
      tree,
      results,
    );
  }

  // ===== the tree =====

  type NodeKind = "schema" | "table" | "column" | "more";

  interface NodeData {
    kind: NodeKind;
    database: string;
    schema: string;
    /** A schema the source could not list: what it said. */
    note?: string;
    table?: string;
    tableKind?: "table" | "view";
    /** A table's name for people, when it says more than its name. */
    title?: string;
    column?: string;
    type?: string;
    offset?: number;
    loaded?: boolean;
  }

  const nodes = new WeakMap<HTMLElement, NodeData>();

  /** A node's icon: a schema (a Power BI dataset its bars), a table or view, a column by its kind of value. */
  function nodeIcon(data: NodeData): string {
    if (data.kind === "schema") return current?.dialect === "dax" ? "powerbi" : "schema";
    if (data.kind === "table") return data.tableKind === "view" ? "view" : "table";
    const type = (data.type ?? "").toLowerCase();
    if (/int|dec|num|float|double|real|money|serial/.test(type)) return "number";
    if (/date|time/.test(type)) return "calendar";
    if (/bool|bit\b|^bit/.test(type)) return "toggle";
    return "case";
  }

  function treeItem(data: NodeData, depth: number, label: string, meta: string, expandable: boolean): HTMLElement {
    const item = h("li", { role: "treeitem", "aria-level": String(depth + 1), "aria-selected": "false", tabindex: "-1" });
    if (expandable) item.setAttribute("aria-expanded", "false");
    const node = h(
      "div",
      { class: `node ${data.kind === "more" ? "more" : ""}` },
      h("span", { class: "twisty", "aria-hidden": "true" }, expandable ? "▸" : ""),
      data.kind === "more" ? null : h("span", { class: `node-icon node-${data.kind}` }, icon(nodeIcon(data))),
      h("span", { class: "node-label" }, label),
      data.kind === "table" && data.tableKind === "view" ? h("span", { class: "node-kind" }, "view") : null,
      data.kind === "table" && data.title ? h("span", { class: "node-kind" }, data.title) : null,
      // A dataset that could not be read: marked on itself only, the reason on hover and on its page.
      data.note ? h("span", { class: "node-error", role: "img", "aria-label": `Error: ${data.note}`, title: data.note }, "!") : null,
      meta ? h("span", { class: "node-meta" }, meta) : null,
    );
    node.style.setProperty("--depth", String(depth)); // a custom property needs setProperty, not assignment
    item.append(node);
    if (data.kind === "table") {
      node.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        event.stopPropagation();
        showMenu(event.clientX, event.clientY, data.table ?? "table", [
          ["rows", "Open as grid", () => void openTableAsGrid(current?.name ?? "", { schema: data.schema, table: data.table ?? "", database: current && current.databases > 1 ? data.database : undefined }, current?.dialect === "dax")],
        ]);
      });
    }
    if (data.kind === "schema" && current?.dialect === "dax" && !data.note) {
      // A Power BI workspace's dataset: its relationships come from here.
      node.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const name = current?.name ?? "";
        showMenu(event.clientX, event.clientY, data.schema || name, [["import", "Import its relationships", () => void importRelationships(name, data.schema)]]);
      });
    }
    if (data.kind === "table" || data.kind === "column") {
      item.draggable = true;
      item.addEventListener("dragstart", (event) => {
        event.stopPropagation();
        const dragged = dragOf(data, item);
        event.dataTransfer?.setData("text/plain", dragged.text);
        if (dragged.imports.length) event.dataTransfer?.setData(DROP_TYPE, JSON.stringify({ code: dragged.text, imports: dragged.imports }));
      });
    }
    nodes.set(item, data);
    return item;
  }

  function dragText(data: NodeData): string {
    if (data.kind === "column" && data.column && current?.dialect === "dax") return daxColumn(data.column, data.table ?? "", data.type ?? "");
    if (data.kind === "column" && data.column) return quoteName(data.column, current?.dialect ?? "other");
    return qualified({ database: data.database, schema: data.schema, table: data.table ?? "" });
  }

  /** A first SELECT over a table, quoted for the dialect (as engine/catalog.py's select_sql). */
  /** What a tree item gives when dragged: its name, or for a table a query over it. */
  function dragOf(data: NodeData, _item: HTMLElement): { text: string; imports: string[] } {
    return { text: dragText(data), imports: [] };
  }

  /** A DAX name: a column 'Sales'[Amount]; a measure, which has no table in front, [Total Sales]. */
  function daxColumn(column: string, table: string, type: string): string {
    const name = `[${column.replaceAll("]", "]]")}]`;
    return type.startsWith("measure") ? name : quoteName(table, "dax") + name;
  }

  /** A table's name for people, when it says more than its own name does (Account for account: no). */
  function titled(t: TableRow): string | undefined {
    const bare = (s: string): string => s.toLowerCase().replace(/[^a-z0-9]/g, "");
    return t.title && bare(t.title) !== bare(t.table) ? t.title : undefined;
  }

  function schemaLabel(row: { database: string; schema: string }): string {
    // A Power BI workspace's schemas are its datasets; a connection saved for one dataset has one node, its model.
    const schema = row.schema || (current?.dialect === "dax" ? "Model" : "(no schema)");
    return current && current.databases > 1 && row.database ? `${row.database}.${schema}` : schema;
  }

  async function showCatalog(): Promise<void> {
    clear(tree);
    search.value = "";
    results.hidden = true;
    tree.hidden = false;
    if (!current) {
      tree.append(h("li", { class: "empty" }, "No catalog loaded"));
      return;
    }
    remember("catalog", current.name);
    let schemas: SchemaRow[];
    try {
      schemas = (await api<{ schemas: SchemaRow[] }>(`${catalogPath(current.name)}/schemas`)).schemas;
    } catch (error) {
      toast((error as Error).message, "error");
      return;
    }
    for (const row of schemas) {
      const count = row.views ? `${formatCount(row.tables)} + ${formatCount(row.views)} views` : formatCount(row.tables);
      const unread = Boolean(row.note) && row.tables + row.views === 0; // nothing under it to open
      tree.append(treeItem({ kind: "schema", database: row.database, schema: row.schema, note: row.note }, 0, schemaLabel(row), unread ? "" : count, !unread));
    }
    const first = tree.querySelector<HTMLElement>('[role="treeitem"]');
    if (first) select(first, false);
    if (schemas.length === 1 && first) await expand(first);
  }

  function group(item: HTMLElement): HTMLElement {
    let list = item.querySelector<HTMLElement>(":scope > ul");
    if (!list) {
      list = h("ul", { role: "group" });
      item.append(list);
    }
    return list;
  }

  async function loadChildren(item: HTMLElement, data: NodeData, offset = 0): Promise<void> {
    if (!current) return;
    const list = group(item);
    if (data.kind === "schema") {
      const page = await api<{ total: number; tables: TableRow[] }>(
        `${catalogPath(current.name)}/tables${query({ schema: data.schema, database: current.databases > 1 ? data.database : undefined, offset, limit: 500 })}`,
      );
      for (const t of page.tables) {
        list.append(
          treeItem({ kind: "table", database: t.database, schema: data.schema, table: t.table, tableKind: t.kind, title: titled(t) }, 1, t.table, formatCount(t.columns), true),
        );
      }
      const shown = offset + page.tables.length;
      if (shown < page.total) {
        list.append(treeItem({ kind: "more", database: data.database, schema: data.schema, offset: shown }, 1, `Show more (${formatCount(page.total - shown)} left)`, "", false));
      }
    } else if (data.kind === "table" && data.table) {
      const columns = await tableColumns(data);
      for (const c of columns) {
        list.append(treeItem({ kind: "column", database: data.database, schema: data.schema, table: data.table, column: c.column, type: c.type }, 2, c.column, c.type, false));
      }
    }
    data.loaded = true;
  }

  async function tableColumns(data: { database: string; schema: string; table?: string }): Promise<ColumnRow[]> {
    if (!current || !data.table) return [];
    const answer = await api<{ columns: ColumnRow[] }>(
      `${catalogPath(current.name)}/columns${query({ schema: data.schema, table: data.table, database: current.databases > 1 ? data.database : undefined })}`,
    );
    return answer.columns;
  }

  async function expand(item: HTMLElement): Promise<void> {
    const data = nodes.get(item);
    if (!data || item.getAttribute("aria-expanded") === null) return;
    if (!data.loaded) {
      try {
        await loadChildren(item, data);
      } catch (error) {
        toast((error as Error).message, "error");
        return;
      }
    }
    item.setAttribute("aria-expanded", "true");
    group(item).hidden = false;
    const twisty = item.querySelector<HTMLElement>(":scope > .node > .twisty");
    if (twisty) twisty.textContent = "▾";
  }

  function collapse(item: HTMLElement): void {
    if (item.getAttribute("aria-expanded") !== "true") return;
    item.setAttribute("aria-expanded", "false");
    group(item).hidden = true;
    const twisty = item.querySelector<HTMLElement>(":scope > .node > .twisty");
    if (twisty) twisty.textContent = "▸";
  }

  function select(item: HTMLElement, show = true, how: Move = "auto"): void {
    for (const old of tree.querySelectorAll<HTMLElement>('[aria-selected="true"]')) {
      old.setAttribute("aria-selected", "false");
      old.tabIndex = -1;
    }
    item.setAttribute("aria-selected", "true");
    item.tabIndex = 0;
    item.querySelector(".node")?.scrollIntoView({ block: "nearest" });
    if (show) void showNode(item, how);
  }

  /** Every item a person can see now (not inside a collapsed parent), in order. */
  function visibleItems(): HTMLElement[] {
    return [...tree.querySelectorAll<HTMLElement>('[role="treeitem"]')].filter((item) => {
      let parent = item.parentElement?.closest<HTMLElement>('[role="treeitem"]');
      while (parent) {
        if (parent.getAttribute("aria-expanded") !== "true") return false;
        parent = parent.parentElement?.closest<HTMLElement>('[role="treeitem"]');
      }
      return true;
    });
  }

  async function activate(item: HTMLElement): Promise<void> {
    const data = nodes.get(item);
    if (!data) return;
    if (data.kind === "more") {
      const parent = item.parentElement?.closest<HTMLElement>('[role="treeitem"]');
      const parentData = parent ? nodes.get(parent) : undefined;
      item.remove();
      if (parent && parentData) await loadChildren(parent, parentData, data.offset ?? 0);
      return;
    }
    if (item.getAttribute("aria-expanded") === "true") collapse(item);
    else await expand(item);
  }

  tree.addEventListener("click", (event) => {
    const item = (event.target as HTMLElement).closest<HTMLElement>('[role="treeitem"]');
    if (!item) return;
    select(item);
    void activate(item);
  });

  tree.addEventListener("keydown", (event) => {
    const items = visibleItems();
    const at = items.findIndex((i) => i.getAttribute("aria-selected") === "true");
    const item = items[at];
    const move = (to: HTMLElement | undefined): void => {
      if (!to) return;
      event.preventDefault();
      select(to, true, "replace"); // walking the tree: one entry, the place it stops (Enter or a click pushes)
    };
    switch (event.key) {
      case "ArrowDown":
        move(items[at + 1]);
        break;
      case "ArrowUp":
        if (at <= 0) {
          event.preventDefault();
          search.focus();
        } else move(items[at - 1]);
        break;
      case "Home":
        move(items[0]);
        break;
      case "End":
        move(items[items.length - 1]);
        break;
      case "ArrowRight":
        if (!item) break;
        event.preventDefault();
        if (item.getAttribute("aria-expanded") === "false") void expand(item);
        else if (item.getAttribute("aria-expanded") === "true") move(items[at + 1]);
        break;
      case "ArrowLeft":
        if (!item) break;
        event.preventDefault();
        if (item.getAttribute("aria-expanded") === "true") collapse(item);
        else move(item.parentElement?.closest<HTMLElement>('[role="treeitem"]') ?? undefined);
        break;
      case "Enter":
      case " ":
        if (!item) break;
        event.preventDefault();
        void activate(item);
        break;
      default:
        // Typing a letter starts a search, like a file tree.
        if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          search.focus();
        }
    }
  });


  // ===== details: a table's columns and a first SELECT, shown by the page =====

  async function showNode(item: HTMLElement, how: Move = "auto"): Promise<void> {
    const data = nodes.get(item);
    if (!data || !current) return;
    if (host.isEditing()) {
      toast("Save or cancel the blade first.");
      return;
    }
    if (data.kind === "table" || data.kind === "column") await showTable(data, data.column, how);
    if (data.kind === "schema") host.showSchema?.(schemaLabel(data), current.name, current.dialect, data.schema, data.note ?? "", current.databases > 1 ? data.database : undefined, how);
  }

  async function showTable(data: NodeData, focusColumn?: string, how: Move = "auto"): Promise<void> {
    if (!current || !data.table) return;
    let answer: { columns: ColumnRow[]; select: string; dialect: string };
    try {
      answer = await api(
        `${catalogPath(current.name)}/columns${query({ schema: data.schema, table: data.table, database: current.databases > 1 ? data.database : undefined })}`,
      );
    } catch (error) {
      toast((error as Error).message, "error");
      return;
    }
    // A connection from the user's own Python: no SELECT, the line that reads the table in a notebook.
    const text = (value: string): string => JSON.stringify(value);
    // A Dataverse environment's is read through its Web API too, by the same line (its one schema unnamed).
    const dataverse = current.dialect === "dataverse";
    const own = dataverse || blades.find((b) => b.name.toLowerCase() === current!.name.toLowerCase())?.connection === "python";
    const line = `sab.read(${text(current.name)}, ${text(data.table)}${data.schema && !dataverse ? `, schema=${text(data.schema)}` : ""})`;
    host.showTable({
      catalog: current.name,
      table: data.table,
      kind: data.tableKind ?? "table",
      where: `${schemaLabel(data)} in ${current.name}`,
      title: data.title,
      name: qualified({ database: data.database, schema: data.schema, table: data.table }),
      select: own ? line : answer.select,
      dialect: own ? "python" : answer.dialect,
      columns: answer.columns,
      focusColumn,
      schema: data.schema,
      schemaLabel: schemaLabel(data),
      database: current.databases > 1 ? data.database : undefined,
    }, how);
  }

  // ===== search =====

  let searchTimer = 0;
  let searchSerial = 0;

  search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => void runSearch(), 150);
  });

  search.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      search.value = "";
      void runSearch();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      const first = results.hidden ? visibleItems()[0] : results.querySelector<HTMLElement>("button");
      if (first && results.hidden) {
        select(first);
        first.focus();
      } else first?.focus();
    } else if (event.key === "Enter") {
      results.querySelector<HTMLElement>("button")?.click();
    }
  });

  results.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const buttons = [...results.querySelectorAll<HTMLElement>("button")];
    const at = buttons.indexOf(document.activeElement as HTMLElement);
    const next = buttons[at + (event.key === "ArrowDown" ? 1 : -1)];
    event.preventDefault();
    if (next) next.focus();
    else if (event.key === "ArrowUp") search.focus();
  });

  async function runSearch(): Promise<void> {
    const text = search.value.trim();
    const serial = ++searchSerial;
    if (!text || !current) {
      results.hidden = true;
      tree.hidden = false;
      return;
    }
    let found: SearchResult;
    try {
      found = await api<SearchResult>(`${catalogPath(current.name)}/search${query({ q: text, limit: 50 })}`);
    } catch (error) {
      toast((error as Error).message, "error");
      return;
    }
    if (serial !== searchSerial) return; // a newer search is on its way
    const hit = (label: string, meta: string, onPick: () => void, drag: string): HTMLElement =>
      h(
        "button",
        {
          type: "button",
          class: "node",
          style: { width: "100%", border: "0", background: "none", color: "inherit", font: "inherit", textAlign: "left" },
          draggable: "true",
          onclick: onPick,
          ondragstart: (event: DragEvent) => event.dataTransfer?.setData("text/plain", drag),
        },
        h("span", { class: "node-label" }, label),
        h("span", { class: "node-meta" }, meta),
      );
    const dialect = current.dialect;
    clear(
      results,
      h("div", { class: "result-group" }, `Tables (${formatCount(found.total_tables)})`),
      ...found.tables.map((t) =>
        hit(`${t.schema ? t.schema + "." : ""}${t.table}`, t.kind === "view" ? "view" : formatCount(t.columns), () => void reveal(t.database, t.schema, t.table), qualified(t)),
      ),
      h("div", { class: "result-group" }, `Columns (${formatCount(found.total_columns)})`),
      ...found.columns.map((c) =>
        hit(`${c.table}.${c.column}`, c.type, () => void reveal(c.database, c.schema, c.table, c.column), dialect === "dax" ? daxColumn(c.column, c.table, c.type) : quoteName(c.column, dialect)),
      ),
      found.total_tables + found.total_columns === 0 ? h("p", { class: "empty" }, "Nothing matches.") : null,
    );
    tree.hidden = true;
    results.hidden = false;
  }

  const find = (parent: ParentNode, match: (d: NodeData) => boolean): HTMLElement | undefined =>
    [...parent.querySelectorAll<HTMLElement>(':scope > [role="treeitem"], :scope > ul > [role="treeitem"]')].find((i) => {
      const d = nodes.get(i);
      return d !== undefined && match(d);
    });
  const schemaItemOf = (database: string, schema: string): HTMLElement | undefined =>
    find(tree, (d) => d.kind === "schema" && d.schema === schema && (!current || current.databases < 2 || d.database === database));

  /** Open the tree at a table (and column) found by search, and show it (false: it is not there). */
  async function reveal(database: string, schema: string, table: string, column?: string, how: Move = "auto"): Promise<boolean> {
    if (host.isEditing()) {
      toast("Save or cancel the blade first.");
      return false;
    }
    search.value = "";
    results.hidden = true;
    tree.hidden = false;
    const schemaItem = schemaItemOf(database, schema);
    if (!schemaItem) return false;
    await expand(schemaItem);
    let tableItem = find(group(schemaItem), (d) => d.kind === "table" && d.table === table);
    // A table past the first page: keep showing more until it appears.
    while (!tableItem) {
      const more = find(group(schemaItem), (d) => d.kind === "more");
      if (!more) break;
      await activate(more);
      tableItem = find(group(schemaItem), (d) => d.kind === "table" && d.table === table);
    }
    if (!tableItem) return false;
    await expand(tableItem);
    const target = column ? (find(group(tableItem), (d) => d.kind === "column" && d.column === column) ?? tableItem) : tableItem;
    select(target, false);
    tree.focus();
    const data = nodes.get(tableItem);
    if (!data) return false;
    await showTable(data, column, how);
    return true;
  }

  /** The tree at the place an address names: its catalog picked, then its schema or table shown. */
  async function goTo(place: CatalogPlace, how: Move = "replace"): Promise<boolean> {
    if (current?.name.toLowerCase() !== place.catalog.toLowerCase()) {
      if (!catalogs.some((c) => c.name.toLowerCase() === place.catalog.toLowerCase())) catalogs = (await api<{ catalogs: CatalogInfo[] }>("/catalogs").catch(() => ({ catalogs }))).catalogs;
      const wanted = catalogs.find((c) => c.name.toLowerCase() === place.catalog.toLowerCase());
      if (!wanted) return false;
      current = wanted;
      renderPicker();
      await showCatalog();
    }
    const database = place.database ?? "";
    const schema = place.schema ?? "";
    if (place.table) return reveal(database, schema, place.table, place.column, how);
    if (place.schema === undefined) return true;
    const item = schemaItemOf(database, schema);
    if (!item) return false;
    select(item, false);
    const data = nodes.get(item)!;
    host.showSchema?.(schemaLabel(data), current!.name, current!.dialect, data.schema, data.note ?? "", current!.databases > 1 ? data.database : undefined, how);
    return true;
  }

  // ===== start =====

  renderBlades();
  renderCatalogSection();

  return {
    loadBlades,
    loadCatalogs,
    bladeSaved(name: string): void {
      selectedBlade = name;
      void loadBlades().then(renderPicker);
    },
    editorClosed(): void {
      selectedBlade = null;
      renderBlades();
    },
    blades: () => blades,
    catalogs: () => catalogs,
    current: () => current,
    goTo,
  };
}

/** Each blade kind's icon, each starter family's, each snippet language's (dom.ts ICONS). */
const BLADE_ICONS: Record<string, string> = { sql: "sql", other: "bolt", vault: "key", secret: "key", analysis: "fit", snippet: "copy" };
const LANGUAGE_ICONS: Record<string, string> = { dax: "formula", html: "html", markdown: "markdown", streamlit: "page", python: "code", typescript: "codeapp", tsx: "codeapp" };
const FAMILY_ICONS: Record<string, string> = {
  "Power BI": "powerbi",
  Excel: "excel",
  Files: "folder",
  DAX: "formula",
  HTML: "html",
  Markdown: "markdown",
  Streamlit: "page",
  Controllers: "sliders",
  "Text and layout": "align",
  Components: "group",
  Write: "export",
};
