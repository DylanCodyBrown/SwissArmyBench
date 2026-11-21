/**
 * workbenchIde.ts: the Scripts page's IDE moves (the owner, 2026-11-17: "this is the IDE workbench for all the
 * scripts it should have everything a python ide needs"), over the server's (services/script_ide.py); the
 * completion, signatures, hovers and the lint stay workbenchIntel.ts's (one intelligence). [WIRE]
 *
 *   [F12]      Go to definition: this file's line, another project module opened at it, a library's place said.
 *   [SHIFT+F12] Find all references: a list of every use across the project, each a click to its line.
 *   [F2]       Rename symbol across the project's modules: a preview of each changed line, the made files it
 *              skips (and why), then Apply (the open document's change in its editor, unsaved; the others
 *              written, and every window follows: file_changed).
 *   [FORMAT]   Shift+Alt+F: Ruff's format in the script's Python, or why not.
 *   [SEARCH]   Ctrl+Shift+F: search across the project's scripts (regex, case, whole word), a results list,
 *              Replace all with its preview.
 */
import { api } from "./api";
import { button, clear, h, icon, openDialog, toast } from "./dom";
import { errorHere } from "./errorNote";

export interface IdeDoc {
  path: () => string | null;
  text: () => string;
  python: () => string | null;
  replaceText: (text: string) => void;
  reveal: (line: number, column?: number) => void;
}

export interface IdeHost {
  /** Open a file at a line (another project module), on this page. */
  openAt: (path: string, line: number) => void;
  /** An installed library's file, read-only in a tab of its own, at a line. */
  openLibrary?: (path: string, line: number, module: string | null) => void;
}

interface Place {
  path: string | null;
  line: number;
  column: number;
  name: string;
  module: string | null;
  in_project: boolean;
  builtin: boolean;
  text?: string;
}

const baseName = (path: string): string => path.split(/[\\/]/).pop() ?? path;
const same = (a: string | null, b: string | null): boolean => !!a && !!b && a.replace(/\\/g, "/") === b.replace(/\\/g, "/");

function go(doc: IdeDoc, host: IdeHost, place: Place): void {
  if (!place.path || same(place.path, doc.path())) doc.reveal(place.line, place.column);
  else host.openAt(place.path, place.line);
}

async function definition(doc: IdeDoc, host: IdeHost, line: number, column: number): Promise<void> {
  const said = await api<{ definitions: Place[] }>("/scripts/definition", "POST", { text: doc.text(), line, column, path: doc.path() });
  const found = said.definitions[0];
  if (!found) return toast("No definition found here.");
  if (found.in_project || !found.path || same(found.path, doc.path())) return go(doc, host, found);
  // A library's: its file read-only in a tab of its own (marked read-only), never for editing.
  if (host.openLibrary && /\.pyi?$/.test(found.path)) return host.openLibrary(found.path, found.line, found.module);
  toast(`${found.name}: ${found.builtin ? "built in" : `in ${found.module ?? "a library"}`}, line ${found.line}.`);
}

function placeList(doc: IdeDoc, host: IdeHost, places: Place[], close: () => void): HTMLElement {
  const byFile = new Map<string, Place[]>();
  for (const p of places) byFile.set(p.path ?? doc.path() ?? "", [...(byFile.get(p.path ?? doc.path() ?? "") ?? []), p]);
  return h(
    "div",
    { class: "ide-results", role: "tree" },
    ...[...byFile].map(([file, found]) =>
      h(
        "section",
        { class: "ide-results-file" },
        h("strong", { title: file }, icon("code"), baseName(file), h("span", { class: "hint" }, ` ${found.length}`)),
        ...found.map((p) =>
          h("button", { type: "button", class: "ide-result", role: "treeitem", "data-line": String(p.line), onclick: () => (close(), go(doc, host, p)) }, h("span", { class: "ide-result-line" }, String(p.line)), h("span", { class: "mono" }, p.text ?? p.name)),
        ),
      ),
    ),
  );
}

async function references(doc: IdeDoc, host: IdeHost, line: number, column: number): Promise<void> {
  const said = await api<{ references: Place[] }>("/scripts/references", "POST", { text: doc.text(), line, column, path: doc.path() });
  if (!said.references.length) return toast("No references found.");
  const { body, close } = openDialog(`References: ${said.references[0]!.name} (${said.references.length})`, true);
  body.append(placeList(doc, host, said.references, close));
}

interface Preview {
  path: string;
  lines: { line: number; before: string; after: string }[];
}

function previewList(preview: Preview[], skipped: { path: string; why: string }[]): HTMLElement {
  return h(
    "div",
    { class: "ide-preview" },
    ...preview.map((p) =>
      h(
        "section",
        { class: "ide-results-file", "data-path": p.path },
        h("strong", { title: p.path }, baseName(p.path)),
        ...p.lines.map((l) => h("div", { class: "ide-change" }, h("span", { class: "ide-result-line" }, String(l.line)), h("del", { class: "mono" }, l.before), h("ins", { class: "mono" }, l.after))),
      ),
    ),
    ...skipped.map((s) => h("p", { class: "ide-skipped" }, icon("warning"), h("strong", {}, baseName(s.path)), `: ${s.why}`)),
  );
}

async function rename(doc: IdeDoc, line: number, column: number, word: string): Promise<void> {
  const to = prompt(`Rename ${word || "the symbol"} to`, word);
  if (!to || to === word) return;
  const body = { text: doc.text(), line, column, path: doc.path(), to };
  const plan = await api<{ preview: Preview[]; skipped: { path: string; why: string }[]; changes: Record<string, string> }>("/scripts/rename", "POST", body);
  const { body: host, foot, close } = openDialog(`Rename ${word} to ${to}`, true);
  host.append(previewList(plan.preview, plan.skipped));
  foot.append(
    button(
      "Apply",
      () =>
        void (async () => {
          const mine = doc.path();
          const done = await api<{ written: string[] }>("/scripts/rename", "POST", { ...body, apply: true, unsaved: true });
          // This document's own change, in its editor (unsaved: Save writes it).
          const own = Object.entries(plan.changes).find(([p]) => same(p, mine))?.[1] ?? (mine ? undefined : plan.changes[Object.keys(plan.changes)[0] ?? ""]);
          if (own !== undefined) doc.replaceText(own);
          close();
          toast(`Renamed in ${done.written.length + (own !== undefined ? 1 : 0)} file(s).`);
        })().catch((e: Error) => errorHere(e)),
      { class: "primary" },
    ),
    button("Cancel", () => close(), { class: "ghost" }),
  );
}

async function format(doc: IdeDoc): Promise<void> {
  const said = await api<{ formatted: boolean; text?: string; why?: string; changed?: boolean }>("/scripts/format", "POST", { text: doc.text(), python: doc.python() });
  if (!said.formatted) return errorHere(said.why ?? "Not formatted.");
  if (said.changed && said.text !== undefined) doc.replaceText(said.text);
  else toast("Already formatted.");
}

/** The editor's moves for one document (lazy/codeEditor.ts IdeMoves). */
export function ideMoves(doc: IdeDoc, host: IdeHost): { definition: (l: number, c: number) => void; references: (l: number, c: number) => void; rename: (l: number, c: number, w: string) => void; format: () => void } {
  const guard = (p: Promise<void>): void => void p.catch((e: Error) => errorHere(e));
  return {
    definition: (l, c) => guard(definition(doc, host, l, c)),
    references: (l, c) => guard(references(doc, host, l, c)),
    rename: (l, c, w) => guard(rename(doc, l, c, w)),
    format: () => guard(format(doc)),
  };
}

/** Search across the project's scripts (Ctrl+Shift+F), with Replace all and its preview. */
export function searchScripts(host: IdeHost, front: () => IdeDoc | null): void {
  const { body, foot, close } = openDialog("Search in scripts", true);
  const query = h("input", { type: "search", class: "ide-search", "aria-label": "Search", placeholder: "Search", "data-no-variables": "" }) as HTMLInputElement;
  const to = h("input", { type: "text", class: "ide-search", "aria-label": "Replace", placeholder: "Replace", "data-no-variables": "" }) as HTMLInputElement;
  const flag = (label: string, title: string): HTMLInputElement => h("input", { type: "checkbox", "aria-label": label, title }) as HTMLInputElement;
  const regex = flag("Regular expression", "Use a regular expression");
  const caseOn = flag("Match case", "Match case");
  const word = flag("Whole word", "Match whole word");
  const results = h("div", { class: "ide-results-host" });
  const flags = (): Record<string, unknown> => ({ query: query.value, regex: regex.checked, case: caseOn.checked, word: word.checked });
  let timer: number | null = null;
  const find = async (): Promise<void> => {
    if (!query.value) return void clear(results);
    const said = await api<{ results: { path: string; matches: { line: number; column: number; text: string }[] }[]; count: number }>("/scripts/search", "POST", flags());
    const doc = front();
    const places: Place[] = said.results.flatMap((r) => r.matches.map((m) => ({ path: r.path, line: m.line, column: m.column, name: query.value, module: null, in_project: true, builtin: false, text: m.text.trim() })));
    clear(results, h("p", { class: "hint ide-count" }, `${said.count} result${said.count === 1 ? "" : "s"} in ${said.results.length} file${said.results.length === 1 ? "" : "s"}`), doc ? placeList(doc, host, places, close) : h("p", {}, ""));
  };
  const later = (): void => {
    if (timer !== null) window.clearTimeout(timer);
    timer = window.setTimeout(() => void find().catch((e: Error) => errorHere(e)), 250);
  };
  for (const input of [query, regex, caseOn, word]) input.addEventListener("input", later);
  const replaceAll = button(
    "Replace all…",
    () =>
      void (async () => {
        const plan = await api<{ preview: Preview[]; skipped: { path: string; why: string }[]; count: number }>("/scripts/replace", "POST", { ...flags(), to: to.value });
        clear(results, h("p", { class: "hint" }, `${plan.count} replacement${plan.count === 1 ? "" : "s"}:`), previewList(plan.preview, plan.skipped));
        clear(
          foot,
          button(
            "Apply",
            () =>
              void api<{ written: string[] }>("/scripts/replace", "POST", { ...flags(), to: to.value, apply: true })
                .then((done) => (close(), toast(`Replaced in ${done.written.length} file(s).`)))
                .catch((e: Error) => errorHere(e)),
            { class: "primary" },
          ),
          button("Cancel", () => close(), { class: "ghost" }),
        );
      })().catch((e: Error) => errorHere(e)),
    { class: "line" },
  );
  body.append(
    h("div", { class: "ide-search-row" }, query, h("label", {}, regex, ".*"), h("label", {}, caseOn, "Aa"), h("label", {}, word, "ab")),
    h("div", { class: "ide-search-row" }, to, replaceAll),
    results,
  );
  query.focus();
}

// ===== the explorer's tree actions (2026-11-21): New package, Rename, Duplicate, Delete =====

/** Rename a module or a package (`path`): the new name, then its imports' preview across the project (as F2's
 *  rename shows it), then Apply. `done` gets the new path. */
export function renameFile(path: string, done: (to: string) => void): void {
  const isPackage = !path.endsWith(".py");
  const current = baseName(path).replace(/\.py$/, "");
  const { body, foot, close } = openDialog(`Rename ${baseName(path)}`, true);
  const input = h("input", { type: "text", value: current, "aria-label": "New name", spellcheck: "false", "data-no-variables": "" }) as HTMLInputElement;
  const result = h("div", { class: "ide-results-host" });
  let planned = "";
  const plan = async (): Promise<boolean> => {
    const to = input.value.trim();
    if (!to || to === current) return false;
    const said = await api<{ preview: Preview[]; skipped: { path: string; why: string }[]; new_module: string; module: string }>("/scripts/files/move", "POST", { path, to });
    planned = to;
    clear(
      result,
      h("p", { class: "hint" }, `${said.module} becomes ${said.new_module}`, said.preview.length ? `: its imports in ${said.preview.length} file${said.preview.length === 1 ? "" : "s"} follow.` : "."),
      previewList(said.preview, said.skipped),
    );
    return true;
  };
  const apply = async (): Promise<void> => {
    if (planned !== input.value.trim() && !(await plan())) return;
    const said = await api<{ to: string }>("/scripts/files/move", "POST", { path, to: planned, apply: true });
    close();
    toast(`Renamed to ${baseName(said.to)}.`);
    done(said.to);
  };
  let timer = 0;
  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => void plan().catch((e: Error) => clear(result, h("p", { class: "error-text" }, e.message))), 300);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") void apply().catch((err: Error) => errorHere(err));
  });
  body.append(h("label", { class: "field" }, h("span", {}, isPackage ? "Package name" : "Module name"), input), result);
  foot.append(button("Rename", () => void apply().catch((e: Error) => errorHere(e)), { class: "primary" }), button("Cancel", () => close(), { class: "ghost" }));
  input.select();
}

/** A copy beside it (`load_copy.py`): its path. */
export async function duplicateFile(path: string): Promise<string> {
  const said = await api<{ path: string }>("/scripts/files/duplicate", "POST", { path });
  toast(`Made ${baseName(said.path)}.`);
  return said.path;
}

/** Delete: to the system's trash, on the user's word (the agent cannot). */
export function deleteFile(path: string, done: () => void): void {
  const { body, foot, close } = openDialog(`Delete ${baseName(path)}?`);
  body.append(h("p", {}, `${baseName(path)} goes to the trash.`));
  foot.append(
    button("Move to the trash", () => void api<{ to: string }>("/scripts/files/delete", "POST", { path }).then((said) => (close(), toast(`${baseName(path)} is in ${said.to}.`), done())).catch((e: Error) => errorHere(e)), { class: "danger" }),
    button("Cancel", () => close(), { class: "ghost" }),
  );
}

/** New package: its name; made in `parent` (a folder of the project's; none: scripts/). */
export function newPackage(parent: string | null, done: (init: string) => void): void {
  const { body, foot, close } = openDialog("New package");
  const input = h("input", { type: "text", "aria-label": "Package name", spellcheck: "false", placeholder: "pipeline", "data-no-variables": "" }) as HTMLInputElement;
  const make = (): void =>
    void api<{ path: string }>("/scripts/files/package", "POST", { name: input.value.trim(), parent })
      .then((said) => (close(), done(said.path)))
      .catch((e: Error) => errorHere(e));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") make();
  });
  body.append(h("label", { class: "field" }, h("span", {}, "Package name"), input));
  foot.append(button("Create", make, { class: "primary" }), button("Cancel", () => close(), { class: "ghost" }));
  input.focus();
}
