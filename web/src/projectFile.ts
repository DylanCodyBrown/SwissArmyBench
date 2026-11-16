/**
 * projectFile.ts: a project as one .sab file, the same on the home page and in the Workbench. [STATE + WIRE]
 *
 * ROUTING: [STATE]    GET /project (the open project, its unsaved mark, the tables that need a fix, the
 *                     recent ones), again on the project_changed notice and on any change a save would
 *                     write (a step, a table, a card, a relationship)
 *          [OPEN]     Open project… -> the file chooser (.sab) -> POST /project/open; unsaved work open:
 *                     asked first, and only then
 *          [NEW]      New project -> POST /project/new (the same question)
 *          [SAVE]     Save (Ctrl+S) -> POST /project/save; the first save, and Save as…, ask where
 *                     (the file chooser) after the per-table "Keep its rows in the file" ticks
 *          [CLOSE]    Close project -> POST /project/close
 *          [FIX]      a table that did not come back -> its one click: Add connection, Find <file>,
 *                     Open <notebook>, Remove, Try again -> POST /project/fix
 *          [ASKED]    a double-click on a .sab while unsaved work is open: the page asks
 */
import { api, ApiError, onNotice, type Notice } from "./api";
import { button, h, openDialog, toast } from "./dom";
import { chooseFile } from "./fileChooser";

export interface ProjectTable {
  name: string;
  kind: string;
  from: string;
  needs_rows: boolean;
  keep_rows: boolean;
}

export interface Fix {
  kind: "add_connection" | "find_file" | "open_notebook" | "remove" | "retry";
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
  temporary: boolean;
  dirty: boolean;
  read_only: string | null;
  serial: number;
  tables: ProjectTable[];
  problems: Problem[];
  layout: Record<string, unknown>;
  unsaved_documents: string[];
}

export interface RecentProject {
  path: string;
  opened: number;
  exists: boolean;
}

export interface ProjectState {
  project: OpenProject | null;
  loose: boolean;
  recent: RecentProject[];
  asked: string | null;
}

let state: ProjectState = { project: null, loose: false, recent: [], asked: null };
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

/** Open project…: a .sab (the file chooser when no path is given). */
export async function openProject(path?: string): Promise<ProjectState | null> {
  const chosen = path ?? (await chooseFile({ title: "Open project", mode: "file", suffixes: [".sab"], start: state.recent[0]?.path }));
  if (!chosen) return null;
  const opened = await withQuestion("/project/open", { path: chosen }, `Let them go and open ${baseName(chosen)}?`);
  if (!opened) return null;
  return loadProject(); // a table that did not come back shows in the strip under the tabs, with its fix
}

/** New project: the tables open now go into it (with no project open). */
export async function newProject(): Promise<ProjectState | null> {
  const made = await withQuestion("/project/new", {}, "Let them go and start a new project?");
  if (!made) return null;
  return loadProject();
}

export async function closeProject(): Promise<ProjectState | null> {
  const done = await withQuestion("/project/close", {}, "Let them go and close the project?");
  if (!done) return null;
  return loadProject();
}

/** The tables with no source to read again, each with its "Keep its rows in the file" tick; resolves
 *  to the choices, or null when closed. None to choose: at once. */
function chooseRows(project: OpenProject): Promise<Record<string, boolean> | null> {
  const choosing = project.tables.filter((t) => t.needs_rows);
  if (!choosing.length) return Promise.resolve({});
  return new Promise((resolve) => {
    const { dialog, body, foot, close } = openDialog("Save project as");
    dialog.classList.add("save-project");
    let done = false;
    const ticks = choosing.map((t) => {
      const box = h("input", { type: "checkbox", "data-table": t.name });
      box.checked = t.keep_rows;
      return { name: t.name, box };
    });
    body.append(
      h(
        "ul",
        { class: "keep-rows" },
        ...ticks.map(({ name, box }) =>
          h("li", {}, h("strong", {}, name), h("label", {}, box, h("span", {}, "Keep its rows in the file"))),
        ),
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
      button("Save as…", () => finish(Object.fromEntries(ticks.map(({ name, box }) => [name, box.checked]))), { icon: "save", class: "primary" }),
    );
  });
}

/** Save (as: Save as…). The first save of a project made here asks where. With no project open, the
 *  open work is saved as one. */
export async function saveProject(as = false): Promise<ProjectState | null> {
  await loadProject();
  if (!state.project) {
    // No project yet: the open work becomes one (its tables go into its data.ipynb), saved where asked.
    await api("/project/new", "POST", {});
    await loadProject();
  }
  const project = state.project;
  if (project?.read_only) {
    toast(project.read_only, "error");
    return null;
  }
  let path: string | undefined;
  let keep: Record<string, boolean> | undefined;
  if (as || !project?.path) {
    const fake: OpenProject = project ?? { name: "project", path: null, folder: "", temporary: true, dirty: true, read_only: null, serial: 0, tables: [], problems: [], layout: {}, unsaved_documents: [] };
    const chosen = await chooseRows(fake);
    if (chosen === null) return null;
    keep = chosen;
    const suggested = `${project?.name && project.name !== "New project" ? project.name : "project"}.sab`;
    const start = project?.path ?? state.recent[0]?.path;
    const picked = await chooseFile({ title: "Save project as", mode: "save", suffixes: [".sab"], start, name: suggested });
    if (!picked) return null;
    path = picked.toLowerCase().endsWith(".sab") ? picked : `${picked}.sab`;
  }
  const folder = project && !project.temporary && !project.path ? project.folder : undefined;
  for (const hook of beforeSave) await hook().catch(() => undefined);
  const saved = await api<ProjectState & { saved: string; notes: string[] }>("/project/save", "POST", { ...(path ? { path } : {}), ...(keep ? { keep_rows: keep } : {}), ...(folder ? { folder } : {}) });
  for (const note of saved.notes ?? []) toast(note);
  toast("Saved");
  return loadProject();
}

/** A folder project (today's: a folder with data.ipynb) saved as one .sab file. */
export async function saveFolderAsFile(folder: string): Promise<ProjectState | null> {
  const picked = await chooseFile({ title: "Save as .sab", mode: "save", suffixes: [".sab"], start: folder, name: `${baseName(folder)}.sab` });
  if (!picked) return null;
  const path = picked.toLowerCase().endsWith(".sab") ? picked : `${picked}.sab`;
  await api("/project/save", "POST", { folder, path });
  toast("Saved");
  return loadProject();
}

/** A table that did not come back: its one click. `addConnection` and `openNotebook` are the page's. */
export async function fixTable(problem: Problem, how: { addConnection: (name: string) => void; openNotebook: (path: string) => void; retry?: boolean }): Promise<void> {
  const fix = problem.fix;
  if (how.retry || fix.kind === "retry") {
    await api("/project/fix", "POST", { table: problem.table });
  } else if (fix.kind === "remove") {
    await api("/project/fix", "POST", { table: problem.table, remove: true });
  } else if (fix.kind === "find_file") {
    const picked = await chooseFile({ title: `Find ${fix.file ?? problem.table}`, mode: "file", suffixes: fix.suffix ? [fix.suffix] : undefined, start: state.project?.path ?? undefined });
    if (!picked) return;
    await api("/project/fix", "POST", { table: problem.table, path: picked });
  } else if (fix.kind === "add_connection") {
    how.addConnection(fix.connection ?? "");
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

/** Another program asked to open a .sab (a double-click) while unsaved work is open: ask once. */
export async function answerAsked(): Promise<void> {
  const asked = state.asked;
  if (!asked || askedShown === asked) return;
  askedShown = asked;
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
