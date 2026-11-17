/**
 * projectExplorer.ts: the home page, the Project Explorer (the owner, 2026-11-17: "Yes build it with projects
 * as folders" / "Make the project page sortable by card with explanations of project types for beginners").
 * It replaces the Start view (/workspace?view=start; Home brings it). [VIEW + WIRE]
 *
 *   [CARDS]   every project as a card: its name, its type (an extension's that is off: "needs the <Name>
 *             extension" with Install), last opened, last changed, its folder (shortened, whole on hover),
 *             what it holds, Git (its branch); a click opens it; a menu: Open, Show in folder, Copy project
 *             to…, Rename, Move left, Move right, Remove from list, Delete… (to the trash, on its typed name)
 *   [SORT]    Last opened, Name, Type, Last changed, Created (ascending or descending), or Custom: cards
 *             dragged (or moved left and right from their menu); remembered by the server
 *   [FILTER]  by type, and a search box (name, folder, notebook names)
 *   [TYPES]   "What kind of project?": each type explained for beginners, with its picture and Create; put
 *             away once read (remembered), always back from New project's "?"
 *   [EMPTY]   no projects yet: the type cards large, "Create your first project"
 *   [MISSING] a project that moved or went: Locate… and Remove from list
 *
 * ROUTING: GET /projects/explorer, POST /projects/sort | explained | rename | remove | locate | show | delete,
 *          POST /extensions/install; the project's own: projectFile.ts
 */
import { api, onNotice } from "./api";
import { button, clear, h, icon, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { baseName, copyProject, importSab, newProject, openProject, type ProjectState, when } from "./projectFile";
import { type ProjectType, typeCard, typePicture } from "./projectTypes";

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
  sab?: boolean;
  needs?: { extension: string; name: string };
  counts: { notebooks?: number; scripts?: number; apps?: number; tables?: number };
  git: { repository: boolean; branch: string | null } | null;
}

interface Listing {
  folder: string;
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
let loading = 0;
let opened: (state: ProjectState | null) => void = () => undefined;
let extras: () => HTMLElement | null = () => null;

const guard = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => toast(e.message, "error"));

/** Start drawing the Project Explorer into `element` (each page once). `afterOpen`: what the page does
 *  once a project opened (its Grids); `head`: the page's own pieces in the header (the tour). */
export function mountExplorer(element: HTMLElement, afterOpen: (state: ProjectState | null) => void, head: () => HTMLElement | null): void {
  host = element;
  opened = afterOpen;
  extras = head;
  onNotice((notice) => {
    if (notice.type === "projects_changed" || notice.type === "project_changed") void refreshExplorer();
  });
}

/** Read the projects again and draw them. */
export async function refreshExplorer(): Promise<void> {
  if (!host) return;
  const asked = ++loading;
  const params = new URLSearchParams();
  if (kind) params.set("type", kind);
  if (query.trim()) params.set("q", query.trim());
  try {
    const read = await api<Listing>(`/projects/explorer${params.size ? `?${params.toString()}` : ""}`);
    if (asked !== loading) return;
    listing = read;
  } catch (e) {
    toast((e as Error).message, "error");
    return;
  }
  draw();
}

/** The explorer's page as it stands (drawn again on each read). */
export function drawExplorer(): void {
  if (listing) draw();
  else void refreshExplorer();
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
  guard(() => newProject(t).then((s) => opened(s)))();
}

function header(read: Listing, empty: boolean): HTMLElement {
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
    h("div", { class: "start-head" }, h("h2", {}, "Projects"), extras()),
    h(
      "div",
      { class: "start-actions" },
      button("New project", () => create(), { icon: "plus", class: "start-action primary-action" }),
      button("Open project…", guard(() => openProject().then((s) => opened(s))), { icon: "folder", class: "start-action" }),
      button("Open a .sab file…", guard(() => importSab().then((s) => opened(s))), { icon: "project", class: "start-action" }),
    ),
    empty ? null : h("div", { class: "explorer-tools" }, search, types, h("label", { class: "explorer-sort-label" }, h("span", {}, "Sort"), sort), direction),
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
  const openIt = guard(() => (c.sab ? importSab(c.path) : openProject(c.path)).then((s) => opened(s)));
  const meta: (HTMLElement | null)[] = [];
  if (c.missing) {
    meta.push(h("p", { class: "explorer-missing" }, c.sab ? "An old .sab file" : "Moved or deleted"));
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
      h("div", { class: "explorer-card-title" }, h("h3", {}, c.name), c.open ? h("span", { class: "explorer-open-mark" }, "Open") : null),
      typeLine,
      ...meta,
      h(
        "p",
        { class: "explorer-folder", title: c.path },
        icon("folder"),
        h("span", {}, short(c.path)),
        c.git?.repository ? h("span", { class: "explorer-git", title: "Git repository" }, icon("branch"), c.git.branch ?? "Git") : null,
      ),
    ),
    menuButton(c, read, openIt),
  );
  element.addEventListener("click", (e) => {
    if ((e.target as Element).closest("button, a, input, select")) return;
    if (!c.missing || c.sab) openIt();
  });
  element.addEventListener("keydown", (e) => {
    if (e.target !== element) return;
    if (e.key === "Enter" && (!c.missing || c.sab)) openIt();
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
      ...(c.sab ? [item("Import…", openIt)] : [item("Locate…", guard(() => locate(c)))]),
      item("Remove from list", guard(() => remove(c))),
    );
  } else {
    menu.append(
      item("Open", openIt),
      item("Show in folder", guard(() => api("/projects/show", "POST", { path: c.path }))),
      item("Copy project to…", guard(() => copyProject(c.path))),
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

/** Settings' Projects folder: where New project puts projects (the Project Explorer lists its projects). */
export function projectsFolderSection(): HTMLElement {
  const body = h("div", { class: "projects-folder-settings" });
  const draw = async (): Promise<void> => {
    let read: { folder: string; default_folder: string };
    try {
      read = await api<Listing>("/projects/explorer?q=");
    } catch (e) {
      body.replaceChildren(h("p", { class: "status-error" }, (e as Error).message));
      return;
    }
    const use = (body_: Record<string, unknown>): void =>
      void api("/projects/folder", "POST", body_).then(
        () => void draw(),
        (e: Error) => toast(e.message, "error"),
      );
    body.replaceChildren(
      h("p", { class: "library-folder" }, h("code", { class: "mono" }, read.folder)),
      h(
        "div",
        { class: "row" },
        button("Change…", () => void chooseFile({ title: "The projects folder", mode: "folder", start: read.folder }).then((f) => f && use({ folder: f })), { icon: "folder" }),
        read.folder === read.default_folder ? null : button("Default", () => use({ default: true }), { class: "ghost", title: read.default_folder }),
      ),
    );
  };
  void draw();
  return h("fieldset", { class: "fieldset projects-folder-fieldset" }, h("legend", {}, icon("project"), "Projects folder"), body);
}
