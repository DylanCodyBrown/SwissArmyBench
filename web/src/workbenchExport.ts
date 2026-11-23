/**
 * workbenchExport.ts: what the Workbench exports. Moved out of workbenchPage.ts along its own heading (the
 * craft review of 2026-11-22), unchanged. [EXPORT]
 *
 *   [DATA]    Export data.py: written again from the project's data.ipynb, as it stands
 *   [SCRIPT]  Export as one Python script… / as one notebook…: the document in front as one self-contained
 *             file (its connections, vault lookups and grid steps written out); what cannot go is named
 *             first, a connection that only works on this computer is said before anything is written
 *
 * ROUTING: POST /projects/export-data, POST /workbench/export-script
 */
import { agentApi, api } from "./api";
import { askYesNo, toast } from "./dom";
import { errorHere } from "./errorNote";
import { chooseFile } from "./fileChooser";
import type { Doc, ProjectFiles } from "./workbenchPage";

/** What the exports ask of the page: its documents, which is the project's data.ipynb, a file's folder, the
 *  open project's files and the folder a file chooser starts in. */
export interface ExportHost {
  docs: Doc[];
  isData: (doc: Doc) => boolean;
  folderOf: (path: string | null) => string;
  readonly project: ProjectFiles | null;
  readonly homeFolder: string;
}

const baseName = (path: string): string => path.split(/[\\/]/).pop() ?? path;

export function documentExports(host: ExportHost) {
  const { docs, isData, folderOf } = host;

  /** Export data.py: written again from the host.project's data.ipynb, as it stands here. */
  async function exportData(): Promise<unknown> {
    const data = docs.find(isData);
    const folder = data?.path ? folderOf(data.path) : host.project?.folder;
    if (!folder) throw new Error("No host.project is open (a folder with a data.ipynb).");
    const done = await api<{ path: string; names: string[]; fill_in: string[]; skipped: string[] }>("/projects/export-data", "POST", { folder });
    for (const said of done.skipped) toast(said);
    if (done.fill_in.length) errorHere(`data.py cannot read ${done.fill_in.join(", ")} again: add the code that reads it to data.ipynb.`);
    return done;
  }

  interface ExportAnswer {
    path: string | null;
    file: string;
    problems: string[];
    lint: string[];
    stubs: string[];
    skipped: string[];
    settings: { variable: string; secret: boolean }[];
    ask?: string;
    run?: string;
    /** Each connection it uses that runs only on this computer (domain/portability.py), in one paragraph. */
    local?: { connection: string; local: { key: string; reason: string; instead: string; words: string }[] }[];
    local_words?: string;
  }

  /** Export as one Python script… (or as one notebook…): the document as it stands here (saved or
   * not) as one self-contained file that runs with plain `python` (or top to bottom in any Jupyter),
   * written where the file chooser says (docs/ideas.md, 2026-11-15). What cannot be exported is named
   * by its cell first, and the rest goes out with a FILL IN stub for each only when the user says so.
   * `to`: where it goes (the agent's palette call); without it, the file chooser opens. */
  async function exportDocument(doc: Doc | null, format: "script" | "notebook", to?: string, agent = false): Promise<ExportAnswer | null> {
    if (!doc || (!doc.notebook && !doc.script)) throw new Error("Open a notebook or a script to export.");
    const ending = format === "notebook" ? ".ipynb" : ".py";
    const stem = (doc.path ? baseName(doc.path) : doc.title).replace(/\.(ipynb|py)$/i, "");
    const suggested = `${stem.trim().replace(/\W+/g, "_").replace(/^_+|_+$/g, "").toLowerCase() || "job"}_automation${ending}`;
    let path = to;
    if (!path) {
      const title = format === "notebook" ? "Export as one notebook" : "Export as one Python script";
      path = (await chooseFile({ title, mode: "save", start: doc.path ?? host.project?.folder ?? host.homeFolder, name: suggested })) ?? undefined;
      if (!path) return null;
    }
    if (!path.toLowerCase().endsWith(ending)) path += ending;
    const body: Record<string, unknown> = {
      format,
      to: path,
      path: doc.path,
      name: doc.title,
      ...(doc.notebook ? { kind: "notebook", cells: doc.notebook.cells() } : { kind: "script", text: doc.script!.text() }),
    };
    const call = agent ? agentApi : api;
    // A connection it uses that runs only on this computer is said before anything is written (the owner,
    // 2026-11-17: "this is meant to scale to a function app or up to a hosted streamlit application").
    if (!agent) {
      const looked = await call<ExportAnswer>("/workbench/export-script", "POST", { ...body, check: true });
      if (looked.local_words && !(await askYesNo(`${looked.local_words}\n\nExport it anyway?`))) {
        toast("Nothing was exported.");
        return null;
      }
    }
    let done = await call<ExportAnswer>("/workbench/export-script", "POST", body);
    if (done.ask) {
      const said = [...done.problems, ...done.lint].map((p) => `• ${p}`).join("\n");
      if (agent || !(await askYesNo(`These cannot be exported:\n${said}\n\nExport the rest, with a stub that raises FILL IN for each?`))) {
        if (!agent) toast("Nothing was exported.");
        return done;
      }
      done = await call<ExportAnswer>("/workbench/export-script", "POST", { ...body, stub: true });
    }
    for (const said of done.skipped) toast(said);
    const secrets = done.settings.filter((s) => s.secret).map((s) => s.variable);
    const note = secrets.length ? ` Set ${secrets.join(", ")} where it runs.` : "";
    toast(`Exported ${done.file}${done.stubs.length ? ` (FILL IN: ${done.stubs.join(", ")})` : ""}.${note}`);
    return done;
  }

  return { exportData, exportDocument };
}
