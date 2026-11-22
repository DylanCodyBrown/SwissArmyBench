/**
 * structureDoc.ts: a structure's tab in the code pages' groups, beside the code (2026-11-22, the owner:
 * "When we open a json or yaml or xml file is it possible to open a collapsable navigation tree of nodes" /
 * "I want it beside the ide so you can search and explore" / "Does structures open as an ide? Or is it read
 * only"). A JSON, YAML, XML or TOML file opened from the Files pane, Open…, the Data Explorer, a file dropped
 * on the window or handed to the desktop app is this tab on the Notebooks or Scripts page, so it can sit in a
 * split next to a script. An IDE, not a save form (design principle 8.14; codeIde.ts is its shell). [WIRE]
 *
 *   [BAR]     codeIde.ts's slim bar: the name, the dirty dot, Save (Ctrl+S), Save as…, Cancel (the file
 *             again), Tree | Text | Both, Format, "…" (the Structures page, the lineage).
 *   [TEXT]    Monaco, editable at all times: the file's own text. Its realtime linter is the server's parse
 *             (PUT /structures/{id}: kept as typed; an error squiggled at its line and listed in Problems).
 *   [TREE]    structureTree.ts's tree in the editor's place (Tree) or beside it (Both), kept in step both
 *             ways: the text redraws it once it parses (its folds and the selected path kept where they still
 *             are); an edit in it (double-click a value or a key; right-click: Add key…, Duplicate, Delete,
 *             Move up, Move down; drag a list's item) is an edit of the file (POST /edit) and writes the text
 *             again in its format.
 *   [FIND]    the search box over the tree: the matches marked and their way unfolded; Enter and Shift+Enter
 *             (or the arrows) go to the next and previous one ("3 of 12").
 *   [PATH]    the selected node's path ($.orders[3].lines) with Copy path, and Copy as code beside a Python
 *             document (data["orders"][3]["lines"]: structurePaths.ts accessCode).
 *   [STEPS]   the transform side, apart from editing: Pick, Filter…, Sort…, Flatten and Open as grid make a
 *             view of the file through steps (the tree shows "Through its steps"; the text stays the file's);
 *             a step's × takes it away. Save writes the text, never the steps.
 *   [DISK]    Save writes the text only when its bytes change; a file changed on disk is noticed (the
 *             file_changed notice): taken at once with nothing unsaved, else Reload / Keep mine; a Save over
 *             it is refused until then. A text that does not parse is saved with a warning naming its line.
 *
 * ROUTING: POST /structures/open {path, view: file} · GET /structures/{id}?view= · PUT /structures/{id} {text,
 *          view} · POST /structures/{id}/edit, /format, /reload, /keep-mine, /save {text, hash, force?},
 *          /save-as {path, as_text}, /steps, /steps/remove, /grid
 */
import { api, ApiError } from "./api";
import { codeIde, type CodeIde } from "./codeIde";
import { button, h, icon, openDialog, showMenu, toast, type MenuItem } from "./dom";
import { errorHere } from "./errorNote";
import { chooseFile } from "./fileChooser";
import type { EditorLanguage, IntelProblem } from "./lazy/codeEditor";
import { promptForError } from "./missingPackages";
import { accessCode, errorPlace, matchPaths } from "./structurePaths";
import { FORMAT_NAMES, type Format, isRecords, kindOf, mountTree, nodeAt, type Part, pathText, type Tree, type Value } from "./structureTree";
import { effectiveTheme } from "./theme";

interface Step {
  op: string;
  path: string;
  words: string;
}

interface Shown {
  id: string;
  name: string;
  format: Format;
  path: string | null;
  text?: string;
  value?: Value;
  hash: string | null;
  text_error: string | null;
  text_dirty: boolean;
  steps: Step[];
  error: string | null;
  written?: string | null;
  warning?: string | null;
}

export type StructureView = "tree" | "text" | "both";

export interface StructureDocHost {
  /** A Python document is open in this window (Copy as code is offered beside one). */
  pythonBeside: () => boolean;
  /** The tab's unsaved dot. */
  dirty: (dirty: boolean) => void;
  /** Saved under another name (Save as). */
  renamed: (title: string, path: string) => void;
  /** Its file is gone and the user closes it. */
  close: () => void;
  /** The Structures page, on this structure. */
  openPage: (id: string) => void;
}

export interface StructureDoc {
  element: HTMLElement;
  id: string;
  path: () => string | null;
  title: () => string;
  dirty: () => boolean;
  save: () => Promise<boolean>;
  saveAs: () => Promise<boolean>;
  /** A file_changed notice for its file (hash null: it is gone). */
  changedOnDisk: (hash: string | null) => void;
  /** The search box's words: the matches (count), the first in front. */
  search: (words: string) => { count: number; at: number };
  /** The next (1) or previous (-1) match. */
  next: (by: 1 | -1) => { count: number; at: number; path: string | null };
  /** A node selected by its path ($.orders[3]): its way unfolded. */
  select: (path: string | Part[]) => { path: string; code: string };
  setView: (view: StructureView) => void;
  format: () => Promise<void>;
  /** What the agent reads of it ("structure.state"). */
  state: () => Record<string, unknown>;
  dispose: () => void;
}

const LANGUAGE: Record<Format, EditorLanguage> = { json: "json", yaml: "yaml", xml: "xml", toml: "toml" };
const VIEW_KEY = "sab-structure-view";

function keptView(): StructureView {
  try {
    const said = localStorage.getItem(VIEW_KEY);
    return said === "text" || said === "both" ? said : "tree";
  } catch {
    return "tree";
  }
}

/** A path's text read back into its parts (the tree's own: no [*]). */
export function partsOf(path: string): Part[] {
  const parts: Part[] = [];
  const re = /\.([A-Za-z_][A-Za-z0-9_-]*)|\[(-?\d+)\]|\[("(?:[^"\\]|\\.)*")\]/g;
  const body = path.trim().replace(/^\$/, "");
  let at = 0;
  for (let m = re.exec(body); m; m = re.exec(body)) {
    if (m.index !== at) throw new Error(`${path}: a path goes on with .name, [n] or ["key"].`);
    at = re.lastIndex;
    parts.push(m[1] ?? (m[2] !== undefined ? Number(m[2]) : (JSON.parse(m[3]!) as string)));
  }
  if (at !== body.length) throw new Error(`${path}: a path goes on with .name, [n] or ["key"].`);
  return parts;
}

/** Open a structure's file (or an open structure by its id) as a tab's view. A missing package (YAML needs
 *  PyYAML) is the app's one prompt, and nothing opens. */
export async function openStructureDoc(target: { path?: string; id?: string }, host: StructureDocHost, at: Part[] | null = null): Promise<StructureDoc | null> {
  let first: Shown;
  try {
    first = target.path
      ? await api<Shown>("/structures/open", "POST", { path: target.path, view: "file" })
      : await api<Shown>(`/structures/${encodeURIComponent(target.id ?? "")}?view=file`);
  } catch (e) {
    if (promptForError(e)) return null;
    throw e;
  }
  return mountStructureDoc(first, host, at);
}

function mountStructureDoc(first: Shown, host: StructureDocHost, at: Part[] | null): StructureDoc {
  const id = first.id;
  const where = `/structures/${encodeURIComponent(id)}`;
  let shown = first;
  let fileValue: Value = first.value ?? null; // the file's value (its text's last good parse)
  let resultValue: Value | null = null; // through its steps
  let sent = first.text ?? ""; // the text the server holds
  let hash = first.hash;
  let view: StructureView = keptView();
  let through = false; // the tree shows the file through its steps
  let selected: Part[] = at ?? [];
  let matches: Part[][] = [];
  let matchAt = -1;
  let lastWords = ""; // the words the matches are of
  let problems: IntelProblem[] = [];

  // ----- the tree's stage: search, the path, the steps, the tree -----
  const search = h("input", { type: "search", class: "sd-search", placeholder: "Search keys and values", "aria-label": "Search the structure", spellcheck: false, "data-no-variables": "" }) as HTMLInputElement;
  const count = h("span", { class: "sd-count muted", "aria-live": "polite" });
  const prev = button("Previous match", () => void step(-1), { icon: "up", iconOnly: true, class: "ghost sd-prev", title: "Previous match (Shift+Enter)" });
  const next = button("Next match", () => void step(1), { icon: "down", iconOnly: true, class: "ghost sd-next", title: "Next match (Enter)" });
  const throughSwitch = h("div", { class: "segmented sd-through", role: "group", "aria-label": "What the tree shows" });
  const findBar = h("div", { class: "sd-find", role: "search" }, icon("zoom"), search, count, prev, next, h("span", { class: "wb-grow" }), throughSwitch);
  const pathBar = h("div", { class: "sd-path", role: "toolbar", "aria-label": "The selected node" });
  const stepsBar = h("div", { class: "sd-steps", role: "list", "aria-label": "Steps", hidden: true });
  const errorBar = h("div", { class: "sd-error", role: "status", hidden: true });
  const treeHost = h("div", { class: "sd-tree" });
  const stage = h("div", { class: "sd-stage" }, findBar, pathBar, stepsBar, errorBar, treeHost);
  let tree: Tree | null = null;

  const shownValue = (): Value => (through && resultValue !== null ? resultValue : fileValue);

  // ----- the IDE -----
  const viewSwitch = h("div", { class: "segmented sd-views", role: "group", "aria-label": "View" });
  const formatBtn = button("Format", () => void format(), { icon: "align", class: "ghost ide-btn sd-format", title: "Format: written again in its own format" });
  const chip = h("span", { class: "chip sd-format-chip" }, FORMAT_NAMES[first.format]);
  const ide: CodeIde = codeIde({
    name: first.name,
    badge: chip,
    language: LANGUAGE[first.format],
    value: sent,
    theme: effectiveTheme,
    save: () => save(),
    saveAs: () => void saveAs(),
    revert: async () => {
      if (!shown.path) return null;
      const again = await call<Shown>(`${where}/reload`, "POST", {});
      if (!again) return null;
      took(again);
      return again.text ?? "";
    },
    actions: [viewSwitch, formatBtn],
    menu: () => [
      { label: "Open on the Structures page", icon: "structures", run: () => host.openPage(id) },
      { label: "Copy path", icon: "copy", run: () => copyPath() },
      { label: "Copy as code", icon: "code", run: () => copyCode() },
    ],
    editor: { intel: { lint: (text) => lint(text) } },
    remember: "structure",
    stage,
  });
  ide.element.classList.add("structure-ide");
  const element = h("div", { class: "structure-doc", "data-structure": id }, ide.element);
  let gone = false;

  async function call<T>(path: string, method = "GET", body?: unknown): Promise<T | null> {
    try {
      return await api<T>(path, method, body);
    } catch (e) {
      if (!promptForError(e)) errorHere(e);
      return null;
    }
  }

  const tellDirty = (): void => host.dirty(ide.dirty());
  void ide.ready.then((editor) => editor.onChange(() => tellDirty()), () => undefined);

  // ----- the text's realtime linter: the server's parse, the tree following -----
  function problemOf(message: string): IntelProblem[] {
    const place = errorPlace(message) ?? { line: 1, column: 1 };
    // Underlined from where it is to its line's end (at least one character), as a code editor marks it.
    const length = (sent.split("\n")[place.line - 1] ?? "").length;
    return [{ line: place.line, col: place.column, end_line: place.line, end_col: Math.max(place.column + 1, length + 1), message, severity: "error", code: "parse", source: FORMAT_NAMES[shown.format] }];
  }
  async function lint(text: string): Promise<IntelProblem[] | null> {
    if (text === sent) return problems;
    let done: Shown;
    try {
      done = await api<Shown>(where, "PUT", { text, view: through ? "result" : "file" });
    } catch {
      return null; // the server will say so on the next action
    }
    sent = text;
    took(done, false);
    return problems;
  }

  /** An answer of the server's taken in: its value into the tree, its error into Problems. */
  function took(done: Shown, withText = true): void {
    shown = { ...shown, ...done };
    if (done.hash !== undefined) hash = done.hash;
    if (withText && typeof done.text === "string") sent = done.text;
    problems = done.text_error ? problemOf(done.text_error) : [];
    errorBar.hidden = !done.text_error;
    errorBar.replaceChildren(...(done.text_error ? [icon("warning"), h("span", {}, `${done.text_error} The tree shows the last text that parsed.`)] : []));
    if (done.value !== undefined && !done.text_error) {
      if (through) resultValue = done.value;
      else fileValue = done.value;
    }
    if (done.value !== undefined && done.text_error && through) resultValue = done.value;
    if (through && done.error) {
      errorBar.hidden = false;
      errorBar.replaceChildren(icon("warning"), h("span", {}, done.error));
    }
    drawSteps();
    tree?.set(shownValue());
    if (search.value.trim()) runSearch(false);
    drawPath();
  }

  // ----- views -----
  function setView(v: StructureView): void {
    view = v;
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      /* not remembered */
    }
    ide.element.classList.toggle("view-both", v === "both");
    ide.setStage(v !== "text");
    if (v === "both") {
      // The tree beside the text: both shown (codeIde shows one; the class lays them side by side).
      (ide.element.querySelector(".ide-editor") as HTMLElement | null)?.removeAttribute("hidden");
      void ide.ready.then((e) => e.layout(), () => undefined);
    }
    for (const b of viewSwitch.querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.view === v));
  }
  for (const [v, label] of [["tree", "Tree"], ["text", "Text"], ["both", "Both"]] as const) {
    const b = button(label, () => setView(v), { pressed: view === v, class: "sd-view-btn" });
    b.dataset.view = v;
    viewSwitch.append(b);
  }

  function drawThrough(): void {
    throughSwitch.hidden = !shown.steps.length;
    throughSwitch.replaceChildren(
      ...([["file", "The file"], ["result", "Through its steps"]] as const).map(([v, label]) => {
        const b = button(label, () => void showThrough(v === "result"), { pressed: through === (v === "result"), class: "sd-view-btn" });
        b.dataset.through = v;
        return b;
      }),
    );
  }

  async function showThrough(on: boolean): Promise<void> {
    if (on === through) return;
    through = on;
    if (on) {
      const got = await call<Shown>(where);
      resultValue = got?.value ?? null;
    }
    drawTree();
    drawThrough();
    drawPath();
  }

  // ----- the tree -----
  function drawTree(): void {
    const editing = !through;
    tree = mountTree(shownValue(), {
      depth: 2,
      label: shown.name,
      onSelect: (p) => {
        selected = p;
        drawPath();
      },
      ...(editing
        ? {
            onSet: (p: Part[], v: Value) => void edit({ op: "set", path: pathText(p), value: v }),
            onRename: (p: Part[], key: string, to: string) => void edit({ op: "rename", path: pathText(p), key, to }),
            onMenu: (p: Part[], v: Value, at2: { x: number; y: number }) => nodeMenu(p, v, at2),
            onMove: (p: Part[], to: number) => void edit({ op: "move", path: pathText(p), to }),
          }
        : {}),
    });
    if (selected.length && nodeAt(shownValue(), selected) !== undefined) tree.select(selected);
    else selected = [];
    if (search.value.trim()) runSearch(false);
    treeHost.replaceChildren(tree.element);
  }

  function nodeMenu(p: Part[], v: Value, place: { x: number; y: number }): void {
    const last = p[p.length - 1];
    const items: MenuItem[] = [
      ["copy", "Copy path", () => copyPath()],
      ...(host.pythonBeside() ? ([["code", "Copy as code", () => copyCode()]] as MenuItem[]) : []),
      "-",
    ];
    if (kindOf(v) === "object") items.push(["plus", "Add key…", () => addKey(p)]);
    if (p.length) {
      items.push(["duplicate", "Duplicate", () => void edit({ op: "duplicate", path: pathText(p) })]);
      if (typeof last === "number") {
        const parent = nodeAt(fileValue, p.slice(0, -1));
        const size = Array.isArray(parent) ? parent.length : 0;
        if (last > 0) items.push(["up", "Move up", () => void edit({ op: "move", path: pathText(p), to: last - 1 })]);
        if (last < size - 1) items.push(["down", "Move down", () => void edit({ op: "move", path: pathText(p), to: last + 1 })]);
      }
      items.push(["trash", "Delete", () => void edit({ op: "remove", path: pathText(p) })]);
    }
    showMenu(place.x, place.y, `${pathText(p)} actions`, items);
  }

  async function edit(body: Record<string, unknown>): Promise<void> {
    const done = await call<Shown>(`${where}/edit`, "POST", { ...body, view: "file" });
    if (!done) return;
    if (body.op === "remove" && pathText(selected).startsWith(String(body.path))) selected = selected.slice(0, -1);
    took(done);
    ide.setValue(done.text ?? sent);
    tellDirty();
  }

  function ask(title: string, fields: { name: string; label: string; value?: string; options?: string[] }[], run: (values: Record<string, string>) => void): void {
    const { body, foot, close } = openDialog(title);
    const inputs = new Map<string, HTMLInputElement | HTMLSelectElement>();
    for (const f of fields) {
      const input = f.options
        ? (h("select", { "aria-label": f.label }, ...f.options.map((o) => h("option", { value: o, selected: o === f.value }, o))) as HTMLSelectElement)
        : (h("input", { "aria-label": f.label, value: f.value ?? "", spellcheck: false }) as HTMLInputElement);
      inputs.set(f.name, input);
      body.append(h("label", { class: "structures-field" }, h("span", {}, f.label), input));
    }
    const go = (): void => {
      const values: Record<string, string> = {};
      for (const [k, v] of inputs) values[k] = v.value;
      close();
      run(values);
    };
    body.addEventListener("keydown", (e) => {
      if (e.key === "Enter") (e.preventDefault(), go());
    });
    foot.append(button("Cancel", () => close()), button(title.replace(/…$/, ""), go, { class: "primary" }));
    (body.querySelector("input, select") as HTMLElement | null)?.focus();
  }

  const parseValue = (text: string): Value => {
    try {
      return JSON.parse(text) as Value;
    } catch {
      return text;
    }
  };

  function addKey(p: Part[]): void {
    ask("Add key…", [{ name: "key", label: "Key" }, { name: "value", label: "Value (JSON, or plain text)", value: '""' }], (v) => void edit({ op: "add", path: pathText(p), key: v.key, value: parseValue(v.value ?? "") }));
  }

  // ----- the path bar: Copy path, Copy as code, the node's edits and the transform side -----
  function copyPath(): void {
    const text = pathText(selected);
    void navigator.clipboard.writeText(text).then(() => toast(`Copied ${text}`), () => toast(text));
  }
  function copyCode(): void {
    const text = accessCode(selected);
    void navigator.clipboard.writeText(text).then(() => toast(`Copied ${text}`), () => toast(text));
  }

  function drawPath(): void {
    const node = nodeAt(shownValue(), selected);
    const kind = node === undefined ? "" : kindOf(node);
    const words = pathText(selected);
    const parts: (Node | null)[] = [
      h("code", { class: "sd-path-text", title: "Its path" }, words),
      button("Copy path", () => copyPath(), { icon: "copy", iconOnly: true, class: "ghost sd-copy-path", title: "Copy path" }),
      host.pythonBeside() ? button("Copy as code", () => copyCode(), { icon: "code", class: "ghost sd-copy-code", title: `Copy as code: ${accessCode(selected)} (data: the file's value)` }) : null,
      h("span", { class: "wb-grow" }),
    ];
    if (!through && node !== undefined) {
      if (kind === "object") parts.push(button("Add key…", () => addKey(selected), { icon: "plus", class: "ghost sd-add" }));
      if (selected.length) {
        parts.push(
          button("Duplicate", () => void edit({ op: "duplicate", path: words }), { icon: "duplicate", iconOnly: true, class: "ghost sd-duplicate" }),
          button("Delete", () => void edit({ op: "remove", path: words }), { icon: "trash", iconOnly: true, class: "ghost sd-delete" }),
        );
      }
    }
    if (node !== undefined) parts.push(transformButton(node, words));
    pathBar.replaceChildren(...parts.filter((p): p is Node => p !== null));
  }

  function transformButton(node: Value, at2: string): HTMLElement {
    const fields = isRecords(node) ? [...new Set((node as Record<string, Value>[]).slice(0, 50).flatMap((r) => Object.keys(r)))] : [];
    const list = Array.isArray(node);
    const b = button("Transform", () => {
      const r = b.getBoundingClientRect();
      const items: MenuItem[] = [];
      if (at2 !== "$") items.push(["zoom", "Pick: only this branch", () => void addStep({ op: "pick", path: at2 })]);
      if (list) {
        items.push(
          ["filter", "Filter…", () => ask("Filter…", [{ name: "field", label: "Field", value: fields[0] ?? "" }, { name: "test", label: "Test", value: "=", options: ["=", "!=", ">", ">=", "<", "<=", "contains", "starts with", "exists", "missing"] }, { name: "value", label: "Value" }], (v) => void addStep({ op: "filter", path: at2, field: v.field, test: v.test, value: v.value }))],
          ["sortup", "Sort…", () => ask("Sort…", [{ name: "field", label: "Field", value: fields[0] ?? "" }, { name: "order", label: "Order", value: "Smallest first", options: ["Smallest first", "Largest first"] }], (v) => void addStep({ op: "sort", path: at2, field: v.field, descending: v.order === "Largest first" }))],
        );
        if (isRecords(node)) items.push(["rows", "Flatten", () => void addStep({ op: "flatten", path: at2 })]);
      }
      if (list && (node as Value[]).length && (through || !shown.steps.length)) {
        items.push(["grids", "Open as grid", () => void openGrid(at2)]);
      }
      if (!items.length) items.push(["info", "Pick a list or a branch to transform it", () => undefined]);
      showMenu(r.left, r.bottom + 2, "Transform", items);
    }, { icon: "steps", class: "ghost sd-transform", title: "Make a view of it through steps, or a grid (the file stays as it is)" });
    return b;
  }

  async function addStep(s: Record<string, unknown>): Promise<void> {
    const done = await call<Shown>(`${where}/steps`, "POST", s);
    if (!done) return;
    shown = { ...shown, ...done, text: shown.text };
    through = true;
    resultValue = done.value ?? null;
    drawSteps();
    drawTree();
    drawPath();
  }

  async function openGrid(at2: string): Promise<void> {
    const done = await call<{ dataset: string; rows: number }>(`${where}/grid`, "POST", { path: at2 });
    if (done) toast(`Opened ${done.dataset} as a grid (${done.rows} rows).`);
  }

  function drawSteps(): void {
    stepsBar.hidden = !shown.steps.length;
    stepsBar.replaceChildren(
      h("span", { class: "muted sd-steps-label" }, "Steps"),
      ...shown.steps.map((s, i) =>
        h("span", { class: "structures-step", role: "listitem", "data-op": s.op }, h("span", {}, s.words), h("button", { type: "button", class: "structures-step-x", "aria-label": `Remove step ${i + 1}`, title: "Remove", onclick: async () => {
          const done = await call<Shown>(`${where}/steps/remove`, "POST", { index: i });
          if (!done) return;
          shown = { ...shown, ...done, text: shown.text };
          resultValue = done.value ?? null;
          if (!shown.steps.length) through = false;
          drawSteps();
          drawTree();
          drawPath();
        } }, icon("close"))),
      ),
    );
    drawThrough();
  }

  // ----- search and explore -----
  function runSearch(go: boolean): void {
    lastWords = search.value.trim();
    const words = search.value;
    tree?.search(words);
    matches = matchPaths(shownValue(), words);
    if (!matches.length) matchAt = -1;
    else if (go || matchAt < 0 || matchAt >= matches.length) matchAt = 0;
    drawCount();
    if (go && matchAt >= 0) reveal(matches[matchAt]!);
    else if (!matches.length) tree?.found(null);
  }
  function drawCount(): void {
    count.textContent = !search.value.trim() ? "" : matches.length ? `${matchAt + 1} of ${matches.length}${matches.length >= 1000 ? "+" : ""}` : "No matches";
    prev.disabled = next.disabled = matches.length < 2;
  }
  function reveal(parts: Part[]): void {
    selected = parts;
    tree?.select(parts);
    tree?.found(parts);
    drawPath();
  }
  function step(by: 1 | -1): { count: number; at: number; path: string | null } {
    if (!matches.length) return { count: 0, at: -1, path: null };
    matchAt = (matchAt + by + matches.length) % matches.length;
    drawCount();
    reveal(matches[matchAt]!);
    return { count: matches.length, at: matchAt, path: pathText(matches[matchAt]!) };
  }
  let searchTimer = 0;
  search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => runSearch(true), 150);
  });
  search.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      window.clearTimeout(searchTimer);
      if (search.value.trim() !== lastWords) {
        runSearch(true);
      } else step(e.shiftKey ? -1 : 1);
    } else if (e.key === "Escape" && search.value) {
      e.preventDefault();
      search.value = "";
      runSearch(false);
    }
  });

  // ----- saving, the file on disk -----
  async function save(): Promise<boolean> {
    if (!shown.path) return saveAs();
    const text = ide.value();
    saving = true;
    try {
      const done = await api<Shown>(`${where}/save`, "POST", { text, hash });
      sent = text;
      took({ ...done, text }, true);
      ide.markClean(text);
      ide.note(null);
      tellDirty();
      if (done.warning) warn(done.warning);
      else toast(done.written ? `Saved ${shown.name}.` : `${shown.name} is saved already.`);
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        changedNote(true);
        return false;
      }
      if (!promptForError(e)) errorHere(e);
      return false;
    } finally {
      saving = false;
      // A notice heard while saving (the Save's own one comes before its answer): compared now.
      if (heard !== undefined) {
        const said = heard;
        heard = undefined;
        changedOnDisk(said);
      }
    }
  }

  function warn(words: string): void {
    ide.note(h("div", { class: "ide-note-row sd-warning", role: "status" }, icon("warning"), h("span", {}, words), button("OK", () => ide.note(null), { class: "ghost ide-btn" })));
  }

  async function saveAs(): Promise<boolean> {
    const suffix = { json: ".json", yaml: ".yaml", xml: ".xml", toml: ".toml" }[shown.format];
    const chosen = await chooseFile({ title: `Save ${shown.name} as`, mode: "save", start: shown.path ?? undefined, name: `${shown.name}${suffix}` });
    if (!chosen) return false;
    await lint(ide.value());
    const done = await call<Shown>(`${where}/save-as`, "POST", { path: chosen, as_text: true });
    if (!done) return false;
    took(done, false);
    shown = { ...shown, ...done };
    ide.markClean(ide.value());
    ide.setName(done.name);
    const written = done.path ?? chosen;
    host.renamed(written.split(/[\\/]/).pop() ?? written, written);
    tellDirty();
    toast(`Saved ${done.path ?? chosen}`);
    return true;
  }

  async function reloadNow(): Promise<void> {
    const again = await call<Shown>(`${where}/reload`, "POST", {});
    if (!again) return;
    took(again);
    ide.setValue(again.text ?? "", true);
    ide.note(null);
    tellDirty();
  }

  function changedNote(onSave = false): void {
    ide.note(
      h(
        "div",
        { class: "ide-note-row sd-elsewhere", role: "status" },
        icon("warning"),
        h("span", {}, onSave ? `${shown.name} changed on disk since it was read: nothing was written.` : `${shown.name} changed on disk.`),
        button("Reload", () => void reloadNow(), { class: "primary ide-btn" }),
        button("Keep mine", async () => {
          const kept = await call<Shown>(`${where}/keep-mine`, "POST", {});
          if (!kept) return;
          hash = kept.hash;
          ide.note(null);
          ide.setExtraDirty(true); // what is on disk is not this text: Save writes
          tellDirty();
        }, { class: "ghost ide-btn" }),
      ),
    );
  }

  let saving = false;
  let heard: string | null | undefined;
  function changedOnDisk(said: string | null): void {
    if (gone) return;
    if (saving) {
      heard = said;
      return;
    }
    if (said !== null && said === hash) return; // its own Save, or the same text
    if (said === null) {
      ide.note(h("div", { class: "ide-note-row sd-elsewhere", role: "status" }, icon("warning"), h("span", {}, "This file is gone."), button("Save as…", () => void saveAs(), { class: "ide-btn" }), button("Close", () => host.close(), { class: "ghost ide-btn" })));
      return;
    }
    if (!ide.dirty()) void reloadNow();
    else changedNote();
  }

  async function format(): Promise<void> {
    await lint(ide.value());
    const done = await call<Shown>(`${where}/format`, "POST", { view: "file" });
    if (!done) return;
    took(done);
    ide.setValue(done.text ?? sent);
    tellDirty();
  }

  // ----- first draw -----
  setView(view);
  drawSteps();
  drawTree();
  if (at && nodeAt(fileValue, at) !== undefined) reveal(at);
  drawPath();
  if (first.text_error) took(first, false);

  return {
    element,
    id,
    path: () => shown.path,
    title: () => shown.name,
    dirty: () => ide.dirty(),
    save,
    saveAs,
    changedOnDisk,
    search: (words) => {
      search.value = words;
      runSearch(true);
      return { count: matches.length, at: matchAt };
    },
    next: (by) => step(by),
    select: (path) => {
      const parts = typeof path === "string" ? partsOf(path) : path;
      if (nodeAt(shownValue(), parts) === undefined) throw new Error(`${pathText(parts)} is not there.`);
      reveal(parts);
      return { path: pathText(parts), code: accessCode(parts) };
    },
    setView,
    format,
    state: () => ({
      id,
      name: shown.name,
      path: shown.path,
      format: shown.format,
      view,
      through,
      dirty: ide.dirty(),
      selected: pathText(selected),
      code: accessCode(selected),
      search: search.value,
      matches: matches.length,
      match: matchAt >= 0 ? pathText(matches[matchAt]!) : null,
      text_error: shown.text_error,
      steps: shown.steps.map((s) => s.words),
    }),
    dispose: () => {
      gone = true;
      ide.dispose();
    },
  };
}
