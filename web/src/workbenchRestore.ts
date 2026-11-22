/**
 * workbenchRestore.ts: a Workbench page's documents kept over a reload. Moved out of workbenchPage.ts along
 * its own heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [KEEP]     the open notebooks, scripts and structures in this window's session storage (the browser's,
 *              never a file), a little after each change: a saved document by its path (it comes back from
 *              its file), a changed one with its text; the groups as they are; the project's files
 *   [RESTORE]  after a reload or a crashed tab: each comes back, the groups and the one in front with them
 *   [PAGES]    per page (the owner, 2026-11-21): the Notebooks page's and the Scripts page's documents each
 *              their own; a session from before, both kinds in one, is split by kind once
 */
import type { CellData } from "./workbenchNotebook";
import type { SavedLayout } from "./workbenchGroups";
import type { Descriptions } from "./workbenchDocModes";
import { type CodePage, splitSession, wrongPage } from "./workbenchPages";
import type { Doc, ProjectFiles, PythonChoice } from "./workbenchPage";

export interface Remembered {
  kind: "notebook" | "script" | "structure";
  path: string | null;
  modified: number | null;
  dirty: boolean;
  python: string | null;
  text?: string;
  cells?: CellData[];
  next_cell?: number;
  dictionary?: Descriptions;
}

/** What the session's memory asks of the page: its documents, the one in front, its groups, the project's
 *  files, and how a document is opened and shown. */
export interface RestoreHost {
  page: CodePage;
  docs: () => Doc[];
  current: () => Doc | null;
  groups: {
    save: (key: (doc: Doc) => number | null) => SavedLayout;
    restore: (layout: SavedLayout, doc: (key: number) => Doc | undefined) => void;
  };
  project: () => ProjectFiles | null;
  setProject: (project: ProjectFiles | null) => void;
  listProject: () => void;
  pythons: () => PythonChoice[];
  open: (path: string) => Promise<unknown>;
  openNotebook: (path: string | null, cells: CellData[], modified: number | null, nextCell?: number, dictionary?: Descriptions) => Doc;
  openScript: (path: string | null, text: string, modified: number | null) => Doc;
  show: (doc: Doc) => void;
  drawTabs: () => void;
  dataBody: (doc: Doc) => { dictionary?: Descriptions };
  reportSab: () => Promise<void>;
}

export interface SessionMemory {
  /** This window's session storage key (a fresh window forgets it). */
  key: string;
  /** Keep the open documents soon (a little after the change). */
  remember: () => void;
  /** Keep them now. */
  rememberNow: () => void;
  /** The documents open before a reload (false: there were none). */
  restore: () => Promise<boolean>;
}

export function sessionMemory(host: RestoreHost): SessionMemory {
  // Per page (the owner, 2026-11-21): the Notebooks page's and the Scripts page's documents each their own; a
  // session from before, both kinds in one, is split by kind once (workbenchPages.ts splitSession).
  const key = `workbench-documents:${host.page}`;
  try {
    splitSession(sessionStorage, "workbench-documents");
  } catch {
    /* storage refused: nothing to split */
  }
  let rememberTimer: number | null = null;

  /** Keep the open documents in this window's session storage (the browser's, never a file), so a
   *  reload or a crashed tab brings them back with their unsaved text. */
  function rememberNow(): void {
    if (rememberTimer !== null) window.clearTimeout(rememberTimer);
    rememberTimer = null;
    const kept = (withOutputs: boolean): Remembered[] =>
      host.docs()
        .filter((d) => d.notebook || d.script || (d.structure && d.path))
        .map((d): Remembered => d.structure ? { kind: "structure", path: d.path, modified: null, dirty: false, python: null } : ({
          kind: d.notebook ? "notebook" : "script",
          path: d.path,
          modified: d.modified,
          dirty: d.dirty,
          python: d.python,
          // A saved document comes back from its file; only changed ones keep their text here.
          ...(d.dirty || !d.path ? (d.notebook ? { cells: d.notebook.cells().map((c) => (withOutputs ? c : { ...c, outputs: [] })), next_cell: d.notebook.nextCell(), ...host.dataBody(d) } : { text: d.script!.text() }) : {}),
        }));
    // A structure comes back from its file (its unsaved text is the server's, kept while it is open).
    const code = host.docs().filter((d) => d.notebook || d.script || (d.structure && d.path));
    const front = host.current();
    const at = front ? code.indexOf(front) : -1;
    // The groups as they are: each document by its place among them (a blade or a table is left out).
    const layoutNow = host.groups.save((d) => (code.includes(d) ? code.indexOf(d) : null));
    try {
      sessionStorage.setItem(key, JSON.stringify({ docs: kept(true), current: at, groups: layoutNow, project: host.project() }));
    } catch {
      try {
        sessionStorage.setItem(key, JSON.stringify({ docs: kept(false), current: at, groups: layoutNow, project: host.project() })); // too big with outputs
      } catch {
        /* storage refused: a reload starts empty, as before */
      }
    }
  }

  function remember(): void {
    if (rememberTimer === null)
      rememberTimer = window.setTimeout(() => {
        rememberNow();
        void host.reportSab(); // the open project keeps this window's documents and groups for its next save
      }, 800);
  }

  /** The documents open before a reload (false: there were none). */
  async function restore(): Promise<boolean> {
    type Saved = { docs: Remembered[]; current: number; groups?: SavedLayout; project?: ProjectFiles | null } | null;
    const read = (): Saved => {
      try {
        return JSON.parse(sessionStorage.getItem(key) ?? "null") as Saved;
      } catch {
        return null;
      }
    };
    const saved = read();
    if (!saved?.docs?.length) return false;
    host.setProject(saved.project ?? null);
    host.listProject();
    const opened: Doc[] = [];
    const byKey = new Map<number, Doc>();
    for (const [key, r] of saved.docs.entries()) {
      if (r.path && !r.dirty) {
        await host.open(r.path); // fresh from its file
        const reopened = host.docs().find((d) => d.path === r.path);
        if (reopened) {
          opened.push(reopened);
          byKey.set(key, reopened);
        }
        continue;
      }
      if (wrongPage(r.kind, host.page) || r.kind === "structure") continue; // the other page's
      const doc = r.kind === "notebook" ? host.openNotebook(r.path, r.cells ?? [], r.modified, r.next_cell, r.dictionary) : host.openScript(r.path, r.text ?? "", r.modified);
      doc.python = r.python;
      if (r.python && !host.pythons().some((p) => p.python === r.python)) host.pythons().push({ python: r.python, version: "", ipykernel: true, swissarmybench: true });
      doc.dirty = r.dirty;
      opened.push(doc);
      byKey.set(key, doc);
    }
    // The groups as they were (their tabs, sizes and the focused one); without them, the one in front.
    if (saved.groups) host.groups.restore(saved.groups, (key) => byKey.get(key));
    else {
      const back = byKey.get(saved.current) ?? opened[opened.length - 1];
      if (back) host.show(back);
    }
    host.drawTabs();
    return opened.length > 0;
  }

  return { key, remember, rememberNow, restore };
}
