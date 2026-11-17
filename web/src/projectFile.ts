/**
 * projectFile.ts: a project is a folder (the owner, 2026-11-17), the same on the home page and in the
 * Workbench. [STATE + WIRE]
 *
 * ROUTING: [STATE]    GET /project (the open project, its unsaved mark, the tables that need a fix, the
 *                     recent ones), again on the project_changed notice and on any change a save would
 *                     write (a step, a table, a card, a relationship)
 *          [OPEN]     Open project… -> the file chooser (a folder) -> POST /project/open; unsaved work open:
 *                     asked first, and only then; a plain folder: "Make this folder a project?" (make)
 *          [NEW]      New project -> its name, its type (each explained: "?"), where (the projects folder,
 *                     or Choose another folder…) -> POST /project/new (scaffolded, opened, saved at once)
 *          [SAVE]     Save (Ctrl+S) -> POST /project/save (.sab/; a pasted table's "Keep its rows" asked
 *                     once); Copy project to… -> a new folder -> POST /project/copy
 *          [AUTOSAVE] the project group's switch -> POST /project/autosave (on by default)
 *          [IMPORT]   Open a .sab file… (one release) -> the .sab, then the folder it goes into -> POST
 *                     /project/import-sab
 *          [CLOSE]    Close project -> POST /project/close
 *          [FIX]      a table that did not come back -> its one click: Add connection, Find <file>,
 *                     Open <notebook>, Remove, Try again -> POST /project/fix
 *          [ASKED]    another program asked to open a project (or an old .sab) while unsaved work is open
 */
import { api, ApiError, onNotice, type Notice } from "./api";
import { button, h, openDialog, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { projectTypes, type ProjectType, typeCard } from "./projectTypes";

export interface ProjectTable {
  name: string;
  kind: string;
  from: string;
  needs_rows: boolean;
  keep_rows: boolean;
}

export interface Fix {
  kind: "add_connection" | "password" | "find_file" | "open_notebook" | "remove" | "retry";
  label: string;
  connection?: string;
  file?: string;
  suffix?: string;
  notebook?: string | null;
}

export interface Problem {
  table: string;
  state: string;
  message: string;
  fix: Fix;
}

export interface OpenProject {
  name: string;
  path: string | null;
  folder: string;
  type: string;
  dirty: boolean;
  read_only: string | null;
  serial: number;
  tables: ProjectTable[];
  problems: Problem[];
  layout: Record<string, unknown>;
  unsaved_documents: string[];
  autosave: boolean;
  autosave_error: string | null;
}

export interface RecentProject {
  path: string;
  opened: number;
  exists: boolean;
  sab?: boolean;
}

export interface ProjectState {
  project: OpenProject | null;
  loose: boolean;
  loose_tables: ProjectTable[];
  recent: RecentProject[];
  asked: string | null;
}

let state: ProjectState = { project: null, loose: false, loose_tables: [], recent: [], asked: null };
const listeners: ((state: ProjectState) => void)[] = [];
let timer: number | null = null;
let loading: Promise<ProjectState> | null = null;
let askedShown: string | null = null;

export function projectState(): ProjectState {
  return state;
}

/** Called with the state each time it is read again (the first time too, once it is loaded). */
export function onProject(listener: (state: ProjectState) => void): void {
  listeners.push(listener);
}

export async function loadProject(): Promise<ProjectState> {
  loading ??= api<ProjectState>("/project").then(
    (read) => {
      loading = null;
      state = read;
      for (const listener of listeners) listener(state);
      return state;
    },
    (e: unknown) => {
      loading = null;
      throw e;
    },
  );
  return loading;
}

function soon(): void {
  if (timer !== null) window.clearTimeout(timer);
  timer = window.setTimeout(() => {
    timer = null;
    void loadProject().catch(() => undefined);
  }, 250);
}

// What a save would write changed, or the project itself did: the mark follows.
const CHANGES = new Set(["project_changed", "grid_updated", "grid_shown", "grid_closed", "dataset_updated", "dataset_closed", "dataset_renamed", "cards_updated", "relationships_updated"]);

/** Start following the project (each page once). */
export function mountProject(): void {
  onNotice((notice: Notice) => {
    if (CHANGES.has(notice.type)) soon();
  });
  void loadProject().catch(() => undefined);
}

/** The project's name as a title shows it: "sales ●" with unsaved changes. */
export function projectLabel(project: OpenProject): string {
  return project.dirty ? `${project.name} ●` : project.name;
}

export function baseName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

export function folderOf(path: string): string {
  const at = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return at > 0 ? path.slice(0, at) : path;
}

/** The unsaved work that would go, in a sentence for the question, or null when nothing would. */
function wouldLose(): string | null {
  if (state.project?.dirty) return `${state.project.name} has unsaved changes.`;
  if (!state.project && state.loose) return "The open tables are not saved in a project.";
  return null;
}

/** POST, asking first when the server says unsaved work would go (409): the same request with discard. */
async function withQuestion(path: string, body: Record<string, unknown>, question: string): Promise<ProjectState | null> {
  try {
    return await api<ProjectState>(path, "POST", body);
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 409) throw e;
    await loadProject().catch(() => undefined);
    const lost = wouldLose() ?? "There are unsaved changes.";
    if (!confirm(`${lost}\n\n${question}`)) return null;
    return api<ProjectState>(path, "POST", { ...body, discard: true });
  }
}

type Opened = ProjectState & { not_a_project?: string; sab?: string };

/** Open project…: a folder (the file chooser when no path is given). A plain folder: made a project around
 *  its files when the user says so; an old .sab file: imported into a folder. */
export async function openProject(path?: string): Promise<ProjectState | null> {
  const chosen = path ?? (await chooseFile({ title: "Open project", mode: "folder", start: state.recent.find((r) => r.exists)?.path }));
  if (!chosen) return null;
  let opened = (await withQuestion("/project/open", { path: chosen }, `Let them go and open ${baseName(chosen)}?`)) as Opened | null;
  if (!opened) return null;
  if (opened.sab) return importSab(opened.sab);
  if (opened.not_a_project) {
    if (!confirm(`${baseName(opened.not_a_project)} is not a project yet.\n\nMake this folder a project? Nothing in it is written over.`)) return null;
    opened = (await withQuestion("/project/open", { path: chosen, make: true }, `Let them go and open ${baseName(chosen)}?`)) as Opened | null;
    if (!opened) return null;
  }
  return loadProject(); // a table that did not come back shows in the strip under the tabs, with its fix
}

/** New project: its name, its type (each explained for beginners), where it goes; scaffolded, opened and
 *  saved at once. The tables open now (with no project) go into it. `preset`: a type chosen already (a
 *  type's card on the home page). */
export async function newProject(preset?: ProjectType): Promise<ProjectState | null> {
  const chosen = await chooseNewProject(preset);
  if (!chosen) return null;
  const made = await withQuestion("/project/new", chosen, "Let them go and start a new project?");
  if (!made) return null;
  return loadProject();
}

/** New project's dialog: resolves to what /project/new is sent, or null when closed. */
async function chooseNewProject(preset?: ProjectType): Promise<Record<string, unknown> | null> {
  const listed = await api<{ types: ProjectType[]; folder: string }>("/projects/types");
  const types = listed.types.length ? listed.types : await projectTypes();
  return new Promise((resolve) => {
    const { dialog, body, foot, close } = openDialog("New project", true);
    dialog.classList.add("new-project");
    let kind = preset ?? types[0];
    let folder: string | null = null;
    let done = false;
    const name = h("input", { type: "text", class: "new-project-name", "aria-label": "Name", value: "", placeholder: "Name", maxlength: "60" });
    const where = h("span", { class: "new-project-where", title: listed.folder }, listed.folder);
    const kinds = h("div", { class: "new-project-types", role: "radiogroup", "aria-label": "Type" });
    const explained = h("div", { class: "new-project-explained pt-cards" });
    explained.hidden = true;
    const drawKinds = (): void => {
      kinds.replaceChildren(
        ...types.map((t) => {
          const pick = h("button", { type: "button", role: "radio", class: "new-project-type", "aria-checked": String(t.type === kind?.type), "data-type": t.type, title: t.for_whom }, t.title || t.name);
          pick.addEventListener("click", () => {
            kind = t;
            drawKinds();
          });
          return pick;
        }),
        button("What kind of project?", () => {
          explained.hidden = !explained.hidden;
        }, { icon: "help", iconOnly: true, class: "ghost new-project-help" }),
      );
    };
    drawKinds();
    explained.append(
      ...types.map((t) =>
        typeCard(t, (picked) => {
          kind = picked;
          drawKinds();
          explained.hidden = true;
          name.focus();
        }),
      ),
    );
    const other = button("Choose another folder…", () => {
      void chooseFile({ title: "New project: where its folder goes", mode: "folder", start: folder ?? listed.folder }).then((picked) => {
        if (!picked) return;
        folder = picked;
        where.textContent = picked;
        where.title = picked;
      });
    }, { icon: "folder", class: "ghost" });
    body.append(
      h("label", { class: "field" }, h("span", {}, "Name"), name),
      h("div", { class: "field" }, h("span", {}, "Type"), kinds),
      explained,
      h("div", { class: "new-project-folder" }, h("span", {}, "In"), where, other),
    );
    const finish = (value: Record<string, unknown> | null): void => {
      if (done) return;
      done = true;
      close();
      resolve(value);
    };
    const create = (): void => {
      const called = name.value.trim();
      if (!called) {
        name.focus();
        return;
      }
      finish({ name: called, ...(folder ? { folder } : {}), ...(kind?.make ?? {}) });
    };
    name.addEventListener("keydown", (e) => {
      if (e.key === "Enter") create();
    });
    dialog.addEventListener("close", () => finish(null));
    foot.append(button("Cancel", () => finish(null), { class: "ghost" }), button("Create", create, { icon: "plus", class: "primary" }));
    name.focus();
  });
}

/** Open a .sab file… (one release): an old project file unpacked into a folder the user picks (each entry
 *  checked by the server), then opened as a project folder. */
export async function importSab(path?: string): Promise<ProjectState | null> {
  const file = path ?? (await chooseFile({ title: "Open a .sab file", mode: "file", suffixes: [".sab"] }));
  if (!file) return null;
  const stem = baseName(file).replace(/\.sab$/i, "");
  const listed = await api<{ folder: string }>("/projects/types").catch(() => ({ folder: "" }));
  const target = await chooseFile({ title: `${baseName(file)}: the folder it becomes`, mode: "save", start: listed.folder || folderOf(file), name: stem });
  if (!target) return null;
  const done = await withQuestion("/project/import-sab", { path: file, folder: target }, `Let them go and open ${stem}?`);
  if (!done) return null;
  toast(`${stem} is a folder now: ${target}`);
  return loadProject();
}

/** An Autosave switch (a checkbox in the switch role). */
export function autosaveSwitch(on: boolean, changed?: (on: boolean) => void): { element: HTMLElement; input: HTMLInputElement } {
  const input = h("input", { type: "checkbox", role: "switch", class: "switch-input", "aria-label": "Autosave" });
  input.checked = on;
  if (changed) input.addEventListener("change", () => changed(input.checked));
  return { element: h("label", { class: "autosave-switch" }, input, h("span", {}, "Autosave")), input };
}

/** Autosave on or off for the open project (kept in its .sab/project.json). */
export async function setAutosave(on: boolean): Promise<ProjectState> {
  await api("/project/autosave", "POST", { on });
  return loadProject();
}

export async function closeProject(): Promise<ProjectState | null> {
  const done = await withQuestion("/project/close", {}, "Let them go and close the project?");
  if (!done) return null;
  return loadProject();
}

/** The tables with no source to read again, each with its "Keep its rows" tick; resolves to the choices,
 *  or null when closed. */
function chooseRows(tables: ProjectTable[], title: string, action: string): Promise<Record<string, boolean> | null> {
  return new Promise((resolve) => {
    const { dialog, body, foot, close } = openDialog(title);
    dialog.classList.add("save-project");
    let done = false;
    const ticks = tables.map((t) => {
      const box = h("input", { type: "checkbox", "data-table": t.name });
      box.checked = t.keep_rows;
      return { name: t.name, box };
    });
    body.append(
      h(
        "ul",
        { class: "keep-rows" },
        ...ticks.map(({ name, box }) => h("li", {}, h("strong", {}, name), h("label", {}, box, h("span", {}, "Keep its rows")))),
      ),
    );
    const finish = (value: Record<string, boolean> | null): void => {
      if (done) return;
      done = true;
      close();
      resolve(value);
    };
    dialog.addEventListener("close", () => finish(null));
    foot.append(
      button("Cancel", () => finish(null), { class: "ghost" }),
      button(action, () => finish(Object.fromEntries(ticks.map(({ name, box }) => [name, box.checked]))), { icon: "save", class: "primary" }),
    );
  });
}

const askedRows = new Set<string>();

/** Save: the project's .sab/ (the documents by their own Save). A pasted table's "Keep its rows" is asked
 *  once. With no project open, the open work becomes one (New project). */
export async function saveProject(): Promise<ProjectState | null> {
  await loadProject();
  const project = state.project;
  if (!project) {
    if (!state.loose) return null;
    return newProject();
  }
  if (project.read_only) {
    toast(project.read_only, "error");
    return null;
  }
  let keep: Record<string, boolean> | undefined;
  const asking = project.tables.filter((t) => t.needs_rows && !t.keep_rows && !askedRows.has(t.name));
  if (asking.length) {
    const chosen = await chooseRows(asking, "Save project", "Save");
    if (chosen === null) return null;
    for (const t of asking) askedRows.add(t.name);
    keep = chosen;
  }
  for (const hook of beforeSave) await hook().catch(() => undefined);
  const saved = await api<ProjectState & { saved: string; notes: string[] }>("/project/save", "POST", keep ? { keep_rows: keep } : {});
  for (const note of saved.notes ?? []) toast(note);
  toast("Saved");
  return loadProject();
}

/** Keep its rows… : the project's pasted tables, each ticked or not (any time, not only once). */
export async function keepRows(): Promise<ProjectState | null> {
  await loadProject();
  const project = state.project;
  const tables = project?.tables.filter((t) => t.needs_rows) ?? [];
  if (!project || !tables.length) return null;
  const chosen = await chooseRows(tables, "Keep rows", "Save");
  if (chosen === null) return null;
  await api("/project/save", "POST", { keep_rows: chosen });
  return loadProject();
}

/** Copy project to…: a new folder (saved first); its kept rows only on a tick. `folder`: a project that is
 *  not open (the Project Explorer's card). */
export async function copyProject(folder?: string): Promise<string | null> {
  const source = folder ?? state.project?.folder;
  if (!source) return null;
  const target = await chooseFile({ title: `Copy ${baseName(source)} to`, mode: "save", start: folderOf(source), name: `${baseName(source)} copy` });
  if (!target) return null;
  const data = confirm("Copy the rows kept in .sab/data too?\n\nOK: with them. Cancel: without (data is sensitive).");
  const done = await api<{ copied: string }>("/project/copy", "POST", { path: target, data, ...(folder ? { folder } : {}) });
  toast(`Copied to ${done.copied}`);
  return done.copied;
}

/** A table that did not come back: its one click. `addConnection` and `openNotebook` are the page's. */
export async function fixTable(problem: Problem, how: { addConnection: (name: string) => void; setPassword: (name: string) => void; openNotebook: (path: string) => void; retry?: boolean }): Promise<void> {
  const fix = problem.fix;
  if (how.retry || fix.kind === "retry") {
    await api("/project/fix", "POST", { table: problem.table });
  } else if (fix.kind === "remove") {
    await api("/project/fix", "POST", { table: problem.table, remove: true });
  } else if (fix.kind === "find_file") {
    const picked = await chooseFile({ title: `Find ${fix.file ?? problem.table}`, mode: "file", suffixes: fix.suffix ? [fix.suffix] : undefined, start: state.project?.folder ?? undefined });
    if (!picked) return;
    await api("/project/fix", "POST", { table: problem.table, path: picked });
  } else if (fix.kind === "add_connection") {
    how.addConnection(fix.connection ?? "");
    return;
  } else if (fix.kind === "password") {
    how.setPassword(fix.connection ?? "");
    return;
  } else if (fix.kind === "open_notebook" && fix.notebook && state.project) {
    const sep = state.project.folder.includes("\\") && !state.project.folder.includes("/") ? "\\" : "/";
    how.openNotebook(`${state.project.folder}${sep}${fix.notebook.split("/").join(sep)}`);
    return;
  }
  await loadProject();
  const still = state.project?.problems.find((p) => p.table === problem.table);
  if (still) toast(still.message, "error");
}

/** Another program asked to open a project (`swissarmybench open`) while unsaved work is open: ask once.
 *  An old .sab file: its import. */
export async function answerAsked(): Promise<void> {
  const asked = state.asked;
  if (!asked || askedShown === asked) return;
  askedShown = asked;
  if (/\.sab$/i.test(asked)) {
    await api("/project/open", "POST", { cancel: true });
    await importSab(asked).catch((e: Error) => toast(e.message, "error"));
    askedShown = null;
    return;
  }
  const lost = wouldLose() ?? "There are unsaved changes.";
  if (confirm(`${lost}\n\nLet them go and open ${baseName(asked)}?`)) {
    await api("/project/open", "POST", { path: asked, discard: true });
  } else {
    await api("/project/open", "POST", { cancel: true });
  }
  askedShown = null;
  await loadProject();
}

/** A window's layout for the next save (the Workbench's documents and groups; the home page's tabs). */
export async function reportLayout(window: "workbench" | "home" | "diagram", layout: Record<string, unknown>, unsaved?: string[]): Promise<void> {
  if (!state.project) return;
  await api("/project/layout", "POST", { window, layout, ...(unsaved ? { unsaved } : {}) }).catch(() => undefined);
}

const beforeSave: (() => Promise<void>)[] = [];

/** Run before every save from this window: its layout reported first. */
export function onBeforeSave(hook: () => Promise<void>): void {
  beforeSave.push(hook);
}

/** "2 hours ago": when a recent project was last opened. */
export function when(seconds: number): string {
  const ago = Math.max(0, Date.now() / 1000 - seconds);
  if (ago < 60) return "Just now";
  if (ago < 3600) return `${Math.floor(ago / 60)} min ago`;
  if (ago < 86400) return `${Math.floor(ago / 3600)} h ago`;
  const days = Math.floor(ago / 86400);
  if (days < 7) return days === 1 ? "Yesterday" : `${days} days ago`;
  return new Date(seconds * 1000).toLocaleDateString();
}
