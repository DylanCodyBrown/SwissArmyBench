/**
 * kindColours.ts: the colour of each kind of Workbench document (the owner, 2026-11-15: "App violet,
 * notebook blue, script green"). [FUNCTION + WIRE]
 *
 * Always a thin edge or a small mark beside the kind's icon, never a background, never amber (amber is
 * out of date). The colours are grid.css's tokens (--kind-app, --kind-notebook, --kind-script, one set
 * per theme): fixed, not a setting (the owner's simplicity pass, 2026-11-21).
 */

export type Kind = "app" | "notebook" | "script";
const listeners: (() => void)[] = [];

/** A file's kind by its name: a Streamlit app's file, a notebook, a script (null: none of them). */
export function kindOfPath(path: string | null | undefined): Kind | null {
  const name = (path ?? "").toLowerCase();
  if (name.endsWith(".stapp.json")) return "app";
  if (name.endsWith(".ipynb")) return "notebook";
  if (name.endsWith(".py")) return "script";
  return null;
}

/** The open project's folder (null: none open); workbenchPage.ts keeps it current. Every notebook is a
 *  notebook (the owner, 2026-11-22: "that concept is gone we just have notebooks"): data.ipynb, the one data.py
 *  is made from, wears no kind of its own. */
let projectFolder: string | null = null;
const slashes = (path: string): string => path.replace(/\\/g, "/");

/** A project opened or closed: the notebooks' kinds follow (onProjectFolder's listeners redraw). */
export function setProjectFolder(folder: string | null): void {
  const next = folder ? slashes(folder).replace(/\/+$/, "") : null;
  if (next === projectFolder) return;
  projectFolder = next;
  for (const listener of listeners) listener();
}

export const projectOpen = (): boolean => projectFolder !== null;

/** The open project's folder, as last set (null: none). */
export const projectFolderNow = (): string | null => projectFolder;

/** The icon a document of this kind shows: every notebook the notebook's (2026-11-22). */
export function kindIcon(kind: Kind | null, _path?: string | null): string {
  if (kind === "notebook") return "notebook";
  return kind === "app" ? "page" : kind === "script" ? "code" : "file";
}

/** Called when the project folder changes (the notebooks' kinds follow). */
export function onProjectFolder(listener: () => void): void {
  listeners.push(listener);
}
