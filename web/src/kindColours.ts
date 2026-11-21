/**
 * kindColours.ts: the colour of each kind of Workbench document (the owner, 2026-11-15: "App violet,
 * notebook blue, script green"). [FUNCTION + WIRE]
 *
 * Always a thin edge or a small mark beside the kind's icon, never a background, never amber (amber is
 * out of date). The defaults are grid.css's tokens (--kind-app, --kind-notebook, --kind-script, one set
 * per theme). A colour chosen in Settings is the server's (domain/kind_colours.py: made readable in
 * each theme, shared by every window, kept across restarts); the page puts the current theme's on
 * <html> and follows a change of theme or of the choice at once.
 *
 * ROUTING: GET /kind-colours, PUT /kind-colours (routes_kind_colours.py); the `kind_colours_changed` notice
 */
import { api, onNotice } from "./api";
import { effectiveTheme, onThemeChange } from "./theme";

export type Kind = "app" | "notebook" | "script";
export const KINDS: Kind[] = ["app", "notebook", "script"];

export interface KindColour {
  kind: Kind;
  name: string;
  /** The user's choice (null: the theme's own). */
  chosen: string | null;
  /** The colour each theme shows. */
  themes: Record<string, string>;
}

let colours: KindColour[] = [];
const listeners: (() => void)[] = [];

/** A file's kind by its name: a Streamlit app's file, a notebook, a script (null: none of them). */
export function kindOfPath(path: string | null | undefined): Kind | null {
  const name = (path ?? "").toLowerCase();
  if (name.endsWith(".stapp.json")) return "app";
  if (name.endsWith(".ipynb")) return "notebook";
  if (name.endsWith(".py")) return "script";
  return null;
}

/** The open project's folder (null: none open). In a project, data.ipynb at its top is THE data notebook;
 *  every other notebook is plain (app notebooks went, 2026-11-21: widgets on the Canvas replaced them).
 *  workbenchPage.ts keeps it current. */
let projectFolder: string | null = null;
const slashes = (path: string): string => path.replace(/\\/g, "/");

/** A project opened or closed: the notebooks' kinds follow (onKindColours' listeners redraw). */
export function setProjectFolder(folder: string | null): void {
  const next = folder ? slashes(folder).replace(/\/+$/, "") : null;
  if (next === projectFolder) return;
  projectFolder = next;
  for (const listener of listeners) listener();
}

export const projectOpen = (): boolean => projectFolder !== null;

/** A notebook's role by its whole path (the same rule as domain/project_scope.py notebook_kind): "data"
 *  for data.ipynb (at the project's top; with no project open, anywhere: its Data mode is its own), ""
 *  (plain) for every other notebook. */
export function notebookRole(path: string | null | undefined): "data" | "" {
  if (!path) return "";
  const whole = slashes(path);
  const data = /(^|\/)data\.ipynb$/i.test(whole);
  if (!projectFolder || !/^(\/|[a-z]:\/)/i.test(whole)) return data ? "data" : "";
  if (!whole.toLowerCase().startsWith(`${projectFolder.toLowerCase()}/`)) return "";
  return whole.slice(projectFolder.length + 1).toLowerCase() === "data.ipynb" ? "data" : "";
}

/** A notebook's word by its role: Data notebook, Notebook. */
export function notebookWord(path: string | null | undefined): string {
  return notebookRole(path) === "data" ? "Data notebook" : "Notebook";
}

/** The icon a document of this kind shows: the data notebook has its own (the owner, 2026-11-16), a
 *  notebook with its corner marked. Without a path: the kind's own icon. */
export function kindIcon(kind: Kind | null, path?: string | null): string {
  if (kind === "notebook") return path !== undefined && notebookRole(path) === "data" ? "dataNotebook" : "notebook";
  return kind === "app" ? "page" : kind === "script" ? "code" : "file";
}

function apply(): void {
  const theme = effectiveTheme();
  const root = document.documentElement;
  for (const kind of KINDS) {
    const found = colours.find((c) => c.kind === kind);
    if (found?.chosen) root.style.setProperty(`--kind-${kind}`, found.themes[theme] ?? found.chosen);
    else root.style.removeProperty(`--kind-${kind}`);
  }
  for (const listener of listeners) listener();
}

function take(list: KindColour[]): void {
  colours = list;
  apply();
}

export const kindColours = (): KindColour[] => colours;

export function onKindColours(listener: () => void): void {
  listeners.push(listener);
}

export async function loadKindColours(): Promise<void> {
  try {
    take((await api<{ kinds: KindColour[] }>("/kind-colours")).kinds);
  } catch {
    /* an older server: the theme's own colours */
  }
}

export async function setKindColour(kind: Kind, colour: string | null): Promise<void> {
  take((await api<{ kinds: KindColour[] }>("/kind-colours", "PUT", { [kind]: colour })).kinds);
}

onNotice((notice) => {
  if (notice.type === "kind_colours_changed") take((notice as unknown as { kinds: KindColour[] }).kinds);
});
onThemeChange(() => apply());
