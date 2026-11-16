/**
 * projectImport.ts: bringing things into the open project, the same in the Workbench, the Connections
 * layer and the blades page. [WIRE] (The owner, 2026-11-16: "now objects are project scoped any notebooks
 * scripts or apps will have to be imported from another project".)
 *
 * ROUTING: [FROM]    Another project… (the file chooser: a .sab), A project folder…, a loose notebook,
 *                    script or app…, or This computer (its saved connections and blades)
 *                    -> POST /project/import/sources
 *          [PICK]    what it offers of the kind asked for, each a tick -> Import -> POST /project/import
 *                    (a document the project has a name for takes the next free name; a connection or
 *                    blade it has is skipped, and said)
 */
import { api } from "./api";
import { button, clear, h, openDialog, toast } from "./dom";
import { chooseFile } from "./fileChooser";

export type ImportKind = "documents" | "connections" | "blades";

interface Offered {
  from: string;
  kind: string;
  documents: { path: string; kind: string; made?: boolean }[];
  connections: { name: string; description: string }[];
  blades: { name: string; kind: string; description: string }[];
}

export interface Imported {
  documents: { from: string; path: string; full: string }[];
  connections: string[];
  blades: string[];
  skipped: string[];
  needs_password: Record<string, { missing: string[] }>;
}

const WORDS: Record<ImportKind, string> = { documents: "notebooks, scripts and apps", connections: "connections", blades: "blades" };
const DOCUMENT_SUFFIXES = [".ipynb", ".py", ".stapp.json"];

/** A loose notebook, script or app from outside the project: copied in. Its copy's whole path. */
export async function importFile(path: string): Promise<string> {
  const done = await api<Imported>("/project/import", "POST", { from: path });
  const copy = done.documents[0];
  if (!copy) throw new Error(`${path} was not imported.`);
  return copy.full;
}

/** The import dialog for one kind; resolves to what was imported, or null when closed. */
export function openImport(kind: ImportKind): Promise<Imported | null> {
  return new Promise((resolve) => {
    const { dialog, body, foot, close } = openDialog(`Import ${WORDS[kind]}`);
    dialog.classList.add("import-dialog");
    let done = false;
    let offered: Offered | null = null;
    const ticks: { name: string; box: HTMLInputElement }[] = [];
    const list = h("div", { class: "import-choices" });
    const go = button("Import", () => void finish(), { icon: "import", class: "primary" });
    go.disabled = true;
    const end = (value: Imported | null): void => {
      if (done) return;
      done = true;
      close();
      resolve(value);
    };
    dialog.addEventListener("close", () => end(null));

    const show = async (from: string | null): Promise<void> => {
      if (!from) return;
      try {
        offered = await api<Offered>("/project/import/sources", "POST", { from });
      } catch (e) {
        toast((e as Error).message, "error");
        return;
      }
      ticks.length = 0;
      const items = kind === "documents" ? offered.documents.map((d) => ({ name: d.path, note: d.made ? "made" : d.kind })) : offered[kind].map((c) => ({ name: c.name, note: c.description }));
      for (const item of items) {
        const box = h("input", { type: "checkbox", "data-name": item.name });
        ticks.push({ name: item.name, box });
      }
      // A loose file is the one imported: no choice to make.
      const loose = offered.kind === "file";
      if (loose) for (const t of ticks) t.box.checked = true;
      clear(
        list,
        h("h3", {}, offered.from === "computer" ? "This computer" : offered.from),
        items.length
          ? h("ul", { class: "import-list" }, ...items.map((item, i) => h("li", {}, h("label", {}, ticks[i]!.box, h("span", {}, item.name), item.note ? h("span", { class: "muted" }, item.note) : null))))
          : h("p", { class: "muted" }, `No ${WORDS[kind]} there.`),
      );
      go.disabled = !items.length;
    };

    const finish = async (): Promise<void> => {
      if (!offered) return;
      const chosen = ticks.filter((t) => t.box.checked).map((t) => t.name);
      if (!chosen.length) return toast("Tick what to import.", "error");
      try {
        const body = offered.kind === "file" ? { from: offered.from } : { from: offered.from, [kind]: chosen };
        const result = await api<Imported>("/project/import", "POST", body);
        for (const name of result.skipped) toast(`${name}: the project has one by that name.`);
        for (const name of Object.keys(result.needs_password)) toast(`${name} needs a password on this computer.`);
        end(result);
      } catch (e) {
        toast((e as Error).message, "error");
      }
    };

    const sources = h(
      "div",
      { class: "import-from" },
      button("Another project…", () => void chooseFile({ title: "Import from a project", mode: "file", suffixes: [".sab"] }).then(show), { icon: "project" }),
      button("A project folder…", () => void chooseFile({ title: "Import from a project folder", mode: "folder" }).then(show), { icon: "folder" }),
      kind === "documents"
        ? button("A file…", () => void chooseFile({ title: "Import a notebook, script or app", mode: "file", suffixes: DOCUMENT_SUFFIXES }).then(show), { icon: "notebook" })
        : button("This computer", () => void show("computer"), { icon: "desktop" }),
    );
    body.append(sources, list);
    foot.append(button("Cancel", () => end(null), { class: "ghost" }), go);
  });
}
