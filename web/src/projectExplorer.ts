/**
 * projectExplorer.ts: the Project Explorer (the owner, 2026-11-17: "Yes build it with projects as folders" /
 * "Make the project page sortable by card with explanations of project types for beginners"), drawn on the
 * Projects page (projectsPage.ts, open=projects: the rail's mark; the old Start view's place). [VIEW + WIRE]
 *
 *   [CARDS]   every project as a card: its name, its type (an extension's that is off: "needs the <Name>
 *             extension" with Install), last opened, last changed, its folder (shortened, whole on hover),
 *             what it holds, Git (its branch); a click opens it; a menu: Open, Show in folder, Copy project
 *             to…, Rename, Move left, Move right, Remove from list, Delete… (to the trash, on its typed name)
 *   [SORT]    Last opened, Name, Type, Last changed, Created (ascending or descending), or Custom: cards
 *             dragged (or moved left and right from their menu); remembered by the server
 *   [FILTER]  by type, All / Local / Shared, and a search box (name, folder, notebook names)
 *   [WHERE]   each card Local or Shared (the owner, 2026-11-18: "local projects and shared projects"): Shared
 *             when under Settings' Shared projects folder (pushed and pulled with Git; the app never runs
 *             git); Share (a local one copied there, no rows) and Make a local copy (copied_from shown)
 *   [TYPES]   "What kind of project?": each type explained for beginners, with its picture and Create; put
 *             away once read (remembered), always back from New project's "?"
 *   [EMPTY]   no projects yet: the type cards large, "Create your first project"
 *   [MISSING] a project that moved or went: Locate… and Remove from list
 *
 * ROUTING: GET /projects/explorer, POST /projects/sort | explained | rename | remove | locate | show | delete,
 *          POST /extensions/install; the project's own: projectFile.ts
 */
import { api, onNotice, onNoticeWhile } from "./api";
import { button, clear, h, icon, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { loadingBlock } from "./loading";
import { baseName, closeProject, copyProject, newProject, onProject, openProject, projectState, type ProjectState, when } from "./projectFile";
import { type ProjectType, typeCard, typePicture } from "./projectTypes";
import { cardActions, cardWords, sharedSync } from "./lazyPages";
import { errorHere, errorMark } from "./errorNote";
import { openFile, pasteData } from "./openFile";

export interface ProjectCard {
  path: string;
  name: string;
  type: string | null;
  type_name: string | null;
  opened: number | null;
  changed: number | null;
  created: number | null;
  open: boolean;
  in_folder: boolean;
  missing: boolean;
  needs?: { extension: string; name: string };
  where?: "local" | "shared";
  copied_from?: string;
  counts: { notebooks?: number; scripts?: number; apps?: number; tables?: number };
  git: { repository: boolean; branch: string | null } | null;
}

interface Listing {
  folder: string;
  local_folder?: string;
  shared_folder?: string | null;
  default_folder: string;
  projects: ProjectCard[];
  count: number;
  sort: { by: string; descending: boolean };
  types: ProjectType[];
  explained: boolean;
}

const SORTS: [string, string][] = [
  ["opened", "Last opened"],
  ["name", "Name"],
  ["type", "Type"],
  ["changed", "Last changed"],
  ["created", "Created"],
  ["custom", "Custom"],
];

let host: HTMLElement | null = null;
let listing: Listing | null = null;
let query = "";
let kind = "";
let where = "";
let loading = 0;
let opened: (state: ProjectState | null) => void = () => undefined;

const guard = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => errorHere(e));

/** Close project, from the Projects page (the owner, 2026-11-19: "I should be able to close a project from
 *  the project home"): projectFile.ts's close (unsaved changes asked about, Autosave saves first); the page
 *  stays, the card no longer marked Open. */
const closeOpen = (): HTMLButtonElement =>
  button("Close project", guard(() => closeProject().then(() => refreshExplorer())), { icon: "close", class: "explorer-close" });

/** The Project Explorer on this page (once). `afterOpen`: what the page does once a project opened (its
 *  Grids). */
export function mountExplorer(afterOpen: (state: ProjectState | null) => void): void {
  opened = afterOpen;
  // The open project at the top and on its card follows the project as it is read again.
  onProject(() => {
    if (host?.isConnected && listing) draw();
  });
  onNotice((notice) => {
    if (notice.type === "projects_changed" || notice.type === "project_changed") void refreshExplorer();
  });
}

/** Draw the explorer into `element` (the Projects page's body, each time it opens), read again. */
export function explorerInto(element: HTMLElement): void {
  host = element;
  if (listing) draw();
  else clear(host, loadingBlock("Loading the projects…", { height: "240px" }));
  void refreshExplorer();
}

/** Read the projects again and draw them (only while the explorer is on show). */
export async function refreshExplorer(): Promise<void> {
  if (!host?.isConnected) return;
  const asked = ++loading;
  const params = new URLSearchParams();
  if (kind) params.set("type", kind);
  if (where) params.set("where", where);
  if (query.trim()) params.set("q", query.trim());
  try {
    const read = await api<Listing>(`/projects/explorer${params.size ? `?${params.toString()}` : ""}`);
    if (asked !== loading) return;
    listing = read;
  } catch (e) {
    errorHere(e);
    return;
  }
  draw();
}

const short = (path: string): string => {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.length > 3 ? `…/${parts.slice(-3).join("/")}` : path;
};

function draw(): void {
  if (!host || !listing) return;
  const read = listing;
  const empty = read.count === 0;
  const page = h("div", { class: "start-page project-explorer-page" });
  page.append(header(read, empty));
  if (empty) {
    page.append(
      h(
        "section",
        { class: "start-section explorer-empty", "aria-label": "Create your first project" },
        h("h2", { class: "explorer-empty-title" }, "Create your first project"),
        h("div", { class: "pt-cards large" }, ...read.types.map((t) => typeCard(t, (picked) => create(picked), true))),
      ),
    );
  } else {
    page.append(typesStrip(read), cardsSection(read));
  }
  clear(host, page);
}

function create(t?: ProjectType): void {
  guard(() => newProject(t, host ?? undefined).then((s) => opened(s)))();
}

function header(read: Listing, empty: boolean): HTMLElement {
  // The project open now, said at the top with its Close (it may be filtered out of the cards).
  const open = projectState().project;
  const search = h("input", { type: "search", class: "explorer-search", placeholder: "Search projects", "aria-label": "Search projects", value: query });
  let typing = 0;
  search.addEventListener("input", () => {
    query = search.value;
    window.clearTimeout(typing);
    typing = window.setTimeout(() => void refreshExplorer().then(() => document.querySelector<HTMLInputElement>(".explorer-search")?.focus()), 200);
  });
  const types = h("select", { class: "explorer-type", "aria-label": "Type" }, h("option", { value: "" }, "All types"), ...read.types.map((t) => h("option", { value: t.type }, t.title || t.name)));
  types.value = kind;
  types.addEventListener("change", () => {
    kind = types.value;
    void refreshExplorer();
  });
  const places = h(
    "select",
    { class: "explorer-where", "aria-label": "Local or shared" },
    h("option", { value: "" }, "All"),
    h("option", { value: "local" }, "Local"),
    h("option", { value: "shared" }, "Shared"),
  );
  places.value = where;
  places.addEventListener("change", () => {
    where = places.value;
    void refreshExplorer();
  });
  const sort = h("select", { class: "explorer-sort", "aria-label": "Sort by" }, ...SORTS.map(([value, label]) => h("option", { value }, label)));
  sort.value = read.sort.by;
  sort.addEventListener("change", guard(() => api("/projects/sort", "POST", { by: sort.value, descending: sort.value === "name" || sort.value === "type" ? false : true }).then(() => refreshExplorer())));
  const direction = button(read.sort.descending ? "Descending" : "Ascending", guard(() => api("/projects/sort", "POST", { by: read.sort.by, descending: !read.sort.descending }).then(() => refreshExplorer())), {
    icon: read.sort.descending ? "down" : "up",
    iconOnly: true,
    class: "ghost explorer-direction",
  });
  direction.toggleAttribute("disabled", read.sort.by === "custom");
  return h(
    "section",
    { class: "start-section explorer-head", "aria-label": "Projects" },
    h(
      "div",
      { class: "start-actions" },
      button("New project", () => create(), { icon: "plus", class: "start-action primary-action" }),
      button("Open project…", guard(() => openProject(undefined, host ?? undefined).then((s) => opened(s))), { icon: "folder", class: "start-action" }),
      // A file or a copied table straight to a grid, no project needed (the owner, 2026-11-19).
      button("Open a file…", () => void openFile(), { icon: "file", class: "start-action" }),
      button("Paste data", () => pasteData(), { icon: "copy", class: "start-action", title: "A table copied from Excel or a web page" }),
    ),
    open ? h("p", { class: "explorer-open-line" }, h("strong", {}, open.name), " is open", closeOpen()) : null,
    empty ? null : h("div", { class: "explorer-tools" }, search, places, types, h("label", { class: "explorer-sort-label" }, h("span", {}, "Sort"), sort), direction),
  );
}

function typesStrip(read: Listing): HTMLElement {
  const section = h("section", { class: `start-section explorer-types${read.explained ? " put-away" : ""}`, "aria-label": "What kind of project?" });
  const toggle = button(read.explained ? "What kind of project?" : "Put away", guard(() => api("/projects/explained", "POST", { explained: !read.explained }).then(() => refreshExplorer())), {
    icon: read.explained ? "help" : "close",
    class: "ghost explorer-types-toggle",
  });
  section.append(h("div", { class: "explorer-types-head" }, read.explained ? null : h("h2", {}, "What kind of project?"), toggle));
  if (!read.explained) section.append(h("div", { class: "pt-cards" }, ...read.types.map((t) => typeCard(t, (picked) => create(picked)))));
  return section;
}

// ===== the cards =====

let dragged: string | null = null;

function cardsSection(read: Listing): HTMLElement {
  const grid = h("div", { class: "explorer-cards", role: "list" });
  grid.append(...read.projects.map((c) => card(c, read)));
  if (!read.projects.length) grid.append(h("p", { class: "explorer-none" }, "No project matches."));
  return h("section", { class: "start-section", "aria-label": "Your projects" }, grid);
}

function counts(c: ProjectCard): string {
  const said: string[] = [];
  const add = (n: number | undefined, one: string, many: string): void => {
    if (n) said.push(`${n} ${n === 1 ? one : many}`);
  };
  add(c.counts.notebooks, "notebook", "notebooks");
  add(c.counts.scripts, "script", "scripts");
  add(c.counts.apps, "app", "apps");
  add(c.counts.tables, "table", "tables");
  return said.join(" · ") || "Empty";
}

function card(c: ProjectCard, read: Listing): HTMLElement {
  const typeKey = c.type ?? "none";
  const element = h("article", {
    class: `explorer-card type-${typeKey}${c.missing ? " missing" : ""}${c.open ? " is-open" : ""}`,
    role: "listitem",
    "data-path": c.path,
    "data-type": typeKey,
    draggable: c.missing ? "false" : "true",
    tabindex: "0",
    "aria-label": c.name,
  });
  const openIt = guard(() => openProject(c.path, host ?? undefined).then((s) => opened(s)));
  const meta: (HTMLElement | null)[] = [];
  if (c.missing) {
    meta.push(h("p", { class: "explorer-missing" }, "Moved or deleted"));
  } else {
    meta.push(
      h("p", { class: "explorer-counts" }, counts(c)),
      h(
        "dl",
        { class: "explorer-times" },
        h("dt", {}, "Opened"),
        h("dd", {}, c.opened ? when(c.opened) : "Never"),
        h("dt", {}, "Changed"),
        h("dd", {}, c.changed ? when(c.changed) : "—"),
      ),
    );
  }
  const typeLine = c.needs
    ? h("span", { class: "explorer-needs" }, `Needs the ${c.needs.name} extension`, button("Install", guard(() => install(c.needs!.extension)), { class: "ghost explorer-install" }))
    : c.type_name
      ? h("span", { class: "explorer-type-name" }, c.type_name)
      : null;
  element.append(
    h("div", { class: "explorer-card-figure", "aria-hidden": "true" }, typePicture(typeKey)),
    h(
      "div",
      { class: "explorer-card-body" },
      h(
        "div",
        { class: "explorer-card-title" },
        h("h3", {}, c.name),
        h("span", { class: `explorer-where-mark where-${c.where ?? "local"}` }, c.where === "shared" ? "Shared" : "Local"),
        c.open ? h("span", { class: "explorer-open-mark" }, "Open") : null,
      ),
      c.open ? closeOpen() : null,
      typeLine,
      c.copied_from ? h("p", { class: "hint explorer-copied" }, `Copied from ${c.copied_from}`) : null,
      ...meta,
      h(
        "p",
        { class: "explorer-folder", title: c.path },
        icon("folder"),
        h("span", {}, short(c.path)),
        c.git?.repository ? h("span", { class: "explorer-git", title: "Git repository" }, icon("branch"), c.git.branch ?? "Git") : null,
      ),
      syncLine(c),
    ),
    menuButton(c, read, openIt),
  );
  element.addEventListener("click", (e) => {
    if ((e.target as Element).closest("button, a, input, select")) return;
    if (!c.missing) openIt();
  });
  element.addEventListener("keydown", (e) => {
    if (e.target !== element) return;
    if (e.key === "Enter" && !c.missing) openIt();
  });
  // Custom order: drag a card onto another (any sort turns into Custom).
  element.addEventListener("dragstart", (e) => {
    dragged = c.path;
    e.dataTransfer?.setData("text/plain", c.path);
    element.classList.add("dragging");
  });
  element.addEventListener("dragend", () => {
    dragged = null;
    element.classList.remove("dragging");
  });
  element.addEventListener("dragover", (e) => {
    if (dragged && dragged !== c.path) {
      e.preventDefault();
      element.classList.add("drop-target");
    }
  });
  element.addEventListener("dragleave", () => element.classList.remove("drop-target"));
  element.addEventListener("drop", (e) => {
    e.preventDefault();
    element.classList.remove("drop-target");
    const from = dragged ?? e.dataTransfer?.getData("text/plain");
    if (!from || from === c.path) return;
    const order = read.projects.map((p) => p.path).filter((p) => p !== from);
    order.splice(order.indexOf(c.path), 0, from);
    guard(() => api("/projects/sort", "POST", { order }).then(() => refreshExplorer()))();
  });
  return element;
}

/** A shared card's sync words (GitHub sync, where the backend has it): "↑2 to push", "↓1 behind", "Conflicts: 1". */
function syncLine(c: ProjectCard): HTMLElement | null {
  if (c.where !== "shared" || c.missing) return null;
  const line = h("p", { class: "explorer-sync", hidden: true });
  void sharedSync().then((status) => {
    const words = cardWords(status, c.name);
    line.hidden = !words;
    line.textContent = words ?? "";
    syncFor.set(c.path, cardActions(status, c.path));
  });
  return line;
}
const syncFor = new Map<string, { label: string; run: () => Promise<unknown> }[]>();

function menuButton(c: ProjectCard, read: Listing, openIt: () => void): HTMLElement {

  const menu = h("div", { class: "explorer-menu", role: "menu" });
  menu.hidden = true;
  const item = (label: string, act: () => void, cls = ""): HTMLElement =>
    h(
      "button",
      {
        type: "button",
        role: "menuitem",
        class: `explorer-menu-item ${cls}`,
        onclick: (e: Event) => {
          e.stopPropagation();
          menu.hidden = true;
          act();
        },
      },
      label,
    );
  const at = read.projects.findIndex((p) => p.path === c.path);
  const move = (by: number): void => guard(() => api("/projects/sort", "POST", { move: c.path, by }).then(() => refreshExplorer()))();
  if (c.missing) {
    menu.append(
      item("Locate…", guard(() => locate(c))),
      item("Remove from list", guard(() => remove(c))),
    );
  } else {
    menu.append(
      item("Open", openIt),
      item("Show in folder", guard(() => api("/projects/show", "POST", { path: c.path }))),
      item("Copy project to…", guard(() => copyProject(c.path))),
      ...(c.where === "shared"
        ? [item("Make a local copy", guard(() => copyLocal(c)))]
        : read.shared_folder
          ? [item("Share", guard(() => share(c)))]
          : []),
      item("Rename", guard(() => rename(c))),
      ...(at > 0 ? [item("Move left", () => move(-1))] : []),
      ...(at >= 0 && at < read.projects.length - 1 ? [item("Move right", () => move(1))] : []),
      item("Remove from list", guard(() => remove(c))),
      item("Delete…", guard(() => remove(c, true)), "danger"),
    );
  }
  const toggle = button(`${c.name}: more`, () => {
    const show = menu.hidden;
    for (const other of document.querySelectorAll<HTMLElement>(".explorer-menu")) other.hidden = true;
    menu.hidden = !show;
    if (show && c.where === "shared") {
      // A shared card's Pull and Push (GitHub sync, where the backend has it), known once its words came.
      for (const old of menu.querySelectorAll(".explorer-sync-item")) old.remove();
      const copy = [...menu.querySelectorAll<HTMLElement>(".explorer-menu-item")].find((b) => b.textContent === "Make a local copy");
      for (const a of syncFor.get(c.path) ?? []) {
        const run = guard(async () => {
          await a.run();
          await refreshExplorer();
        });
        copy?.before(item(a.label, run, "explorer-sync-item"));
      }
    }
    if (show) menu.querySelector<HTMLElement>("button")?.focus();
  }, { icon: "more", iconOnly: true, class: "ghost explorer-more" });
  toggle.addEventListener("click", (e) => e.stopPropagation());
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      menu.hidden = true;
      toggle.focus();
    }
  });
  return h("div", { class: "explorer-menu-wrap" }, toggle, menu);
}

document.addEventListener("click", () => {
  for (const menu of document.querySelectorAll<HTMLElement>(".explorer-menu")) menu.hidden = true;
});

/** Share and Make a local copy: the copy made (no rows), then opened; a name taken asks for another. */
async function copyTo(c: ProjectCard, path: string, words: string): Promise<void> {
  let name: string | undefined;
  for (;;) {
    try {
      const done = await api<{ opened: boolean; why?: string; project?: ProjectState["project"] }>(path, "POST", { path: c.path, ...(name ? { name } : {}) });
      toast(done.opened ? words : `${words}. ${done.why ?? ""}`.trim());
      await refreshExplorer();
      if (done.opened) opened(await api<ProjectState>("/project"));
      return;
    } catch (e) {
      const said = (e as Error).message;
      const free = /"([^"]+)" is free/.exec(said)?.[1];
      if (!free) throw e;
      const asked = prompt(`${said}\n\nName the copy:`, free)?.trim();
      if (!asked) return;
      name = asked;
    }
  }
}

const share = async (c: ProjectCard): Promise<void> => {
  await copyTo(c, "/projects/share", `${c.name} is shared`);
  // "Push it to GitHub now?" when the shared projects folder is connected.
  const shared = listing?.shared_folder;
  if (shared) await (await import("./scmPage")).offerPush(`${shared.replace(/[\\/]+$/, "")}/${c.name}`, c.name);
};
const copyLocal = (c: ProjectCard): Promise<void> => copyTo(c, "/projects/copy-local", `A local copy of ${c.name} is made`);

async function rename(c: ProjectCard): Promise<void> {
  const name = prompt(`Rename ${c.name}`, c.name)?.trim();
  if (!name || name === c.name) return;
  await api("/projects/rename", "POST", { path: c.path, name });
  await refreshExplorer();
}

async function remove(c: ProjectCard, trash = false): Promise<void> {
  if (trash) {
    const typed = prompt(`Delete ${c.name}: its folder goes to the trash.\n\nType ${c.name} to delete it.`);
    if (typed === null) return;
    const done = await api<{ to: string }>("/projects/delete", "POST", { path: c.path, confirm: typed });
    toast(`${c.name} is in ${done.to}`);
  } else {
    await api("/projects/remove", "POST", { path: c.path });
  }
  await refreshExplorer();
}

async function locate(c: ProjectCard): Promise<void> {
  const found = await chooseFile({ title: `Locate ${c.name}`, mode: "folder", start: listing?.folder });
  if (!found) return;
  await api("/projects/locate", "POST", { path: c.path, to: found });
  await refreshExplorer();
}

async function install(extension: string): Promise<void> {
  await api("/extensions/install", "POST", { id: extension });
  toast("Installing: the app restarts when it is done.");
}

export { baseName };

interface Folders {
  folder: string;
  default_folder: string;
  shared_folder: string | null;
}

/** Settings' local projects folder, one row in the Team box (library.ts): "New projects go in <folder> ·
 *  Change…" (Default when moved). It is not a team thing: a team's projects are the shared ones. */
export function localProjectsRow(): HTMLElement {
  const row = h("p", { class: "team-local-projects" });
  const draw = async (): Promise<void> => {
    const read = await api<Folders>("/projects/folder").catch((e: Error) => {
      row.replaceChildren(errorMark(e.message));
      return null;
    });
    if (!read) return;
    const use = (body: Record<string, unknown>): void => void api("/projects/folder", "POST", body).then(() => void draw(), (e: Error) => errorHere(e));
    row.replaceChildren(
      "New projects go in ",
      h("code", { class: "mono projects-local" }, read.folder),
      " · ",
      h("button", { type: "button", class: "link team-local-change", onclick: () => void chooseFile({ title: "The local projects folder", mode: "folder", start: read.folder }).then((f) => f && use({ folder: f })) }, "Change…"),
      read.folder === read.default_folder ? "" : " · ",
      read.folder === read.default_folder ? "" : h("button", { type: "button", class: "link", title: read.default_folder, onclick: () => use({ default: true }) }, "Default"),
    );
  };
  void draw();
  onNoticeWhile(row, (n) => {
    if (n.type === "projects_changed") void draw();
  });
  return row;
}

/** The Team box's Advanced fold (library.ts): the shared projects folder as its own path, Change… and None,
 *  for a team that keeps its projects in a second repository or a folder synced another way. */
export function sharedProjectsRow(): HTMLElement {
  const row = h("div", { class: "team-advanced-row projects-shared-row" });
  const draw = async (): Promise<void> => {
    const read = await api<Folders>("/projects/folder").catch(() => null);
    if (!read) return;
    const use = (body: Record<string, unknown>): void => void api("/projects/folder", "POST", body).then(() => void draw(), (e: Error) => errorHere(e));
    row.replaceChildren(
      h("span", { class: "team-advanced-label" }, "Shared projects folder"),
      read.shared_folder ? h("code", { class: "mono projects-shared" }, read.shared_folder) : h("span", { class: "hint projects-shared" }, "None"),
      button("Change…", () => void chooseFile({ title: "The shared projects folder", mode: "folder", start: read.shared_folder ?? read.folder }).then((f) => f && use({ which: "shared", folder: f })), { icon: "folder", class: "small line" }),
      ...(read.shared_folder ? [button("None", () => use({ which: "shared", default: true }), { class: "ghost small" })] : []),
    );
  };
  void draw();
  onNoticeWhile(row, (n) => {
    if (n.type === "projects_changed" || n.type === "team_changed") void draw();
  });
  return row;
}
