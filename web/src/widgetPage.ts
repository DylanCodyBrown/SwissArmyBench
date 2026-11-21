/**
 * widgetPage.ts: the Widgets window (the owner, 2026-11-21: "Widgets should be on the rail as well but it does
 * not open in the normal app pane it is a new tab completely separate from the app without the rail that gives
 * the user a Streamlit Cell (now called a widget) were the agent and the user can write code against any current
 * data or scripts or variables to create new widget with all of the autocomplete and Jedi completion and help
 * possible. The the user clicks run and the widget transforms in place into the object you wrote."). A window of
 * its own (static/widget.html), no rail.
 *
 *   [LIST]       left: the library's widgets, then the prebuilt ones by group; search; New widget
 *   [EDITOR]     middle: Monaco with the Workbench's intelligence (workbenchIntel.ts over a kernel of its own in
 *                the project's Python: Jedi's member list, signatures, hovers, the lint; Copilot's ghost text
 *                where the mode declares it); the code saved as you type (a prebuilt one is read-only: Copy as
 *                your own)
 *   [RUN]        Run (F5) turns the editor into the running widget, in place (the widget alone through the
 *                Streamlit proxy, with the properties' values); Edit (or Esc) turns it back into code. A run
 *                that fails says so in place, and its line is marked in the code
 *   [PROPERTIES] right: Name (checked live: available, taken, not a valid name) and Description (the file's
 *                header only), then the properties the code makes (its top-level plain values), each with its
 *                mask; a value is checked before it is kept and written into only its own characters
 *
 * ROUTING: /streamlit/widgets (list, new), …/{name} (get, save, header, delete), …/{name}/property, …/copy,
 * …/run, …/check, /streamlit/widgets/properties (live), …/check-name, …/check-value, …/context.
 */
import { api, connect, onNotice, requireSession } from "./api";
import { button, clear, h, icon } from "./dom";
import { clearError, errorHere, showError } from "./errorNote";
import { inlineSource } from "./inlineCompletion";
import type { CodeEditor } from "./lazy/codeEditor";
import { busy, busyButton, loadingBlock } from "./loading";
import { watchTheme } from "./catalogRail";
import { effectiveTheme, onThemeChange } from "./theme";
import { pythonCompleter } from "./workbenchCompletion";
import { pythonIntel, showProblems } from "./workbenchIntel";
import { Kernel, WINDOW_ID } from "./workbenchKernel";
import { type Prop, propertyField } from "./widgetFields";

export interface WidgetEntry {
  name: string;
  description: string;
  framework: string;
  group: string;
  tags: string[];
  size: [number, number];
  min_size: [number, number];
  prebuilt: boolean;
  properties: Prop[];
  problem: { error: string; fix: string; line: number | null } | null;
  hash: string;
}

interface WidgetFull extends WidgetEntry {
  code: string;
  file: string;
  kernel_path: string | null;
  kernel_setup: string;
}

export interface Context {
  tables: Record<string, string[] | null>;
  variables: string[];
}

const loadEditors = (): Promise<typeof import("./lazy/codeEditor")> => import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>;

const params = new URLSearchParams(location.search);
const root = document.getElementById("widgets")!;
let widgets: WidgetEntry[] = [];
let current: WidgetFull | null = null;
let context: Context = { tables: {}, variables: [] };
let editor: CodeEditor | null = null;
let query = "";
let running = false;
let saveTimer: number | null = null;
let propsTimer: number | null = null;
let applying = false;

const list = h("nav", { class: "wg-list", "aria-label": "Widgets" });
const search = h("input", { type: "search", class: "wg-search", placeholder: "Search widgets", "aria-label": "Search widgets", "data-no-variables": "" });
const listItems = h("div", { class: "wg-items", role: "listbox", "aria-label": "Widgets" });
const title = h("h1", { class: "wg-title" }, "Widgets");
const saved = h("span", { class: "wg-saved", "aria-live": "polite" });
const runButton = button("Run", () => void run(), { icon: "play", class: "primary wg-run", title: "Run (F5)" });
const editButton = button("Edit", () => edit(), { icon: "edit", class: "wg-edit", title: "Edit (Esc)" });
const copyButton = button("Copy as your own", () => void copyCurrent(), { icon: "copy", class: "wg-copy" });
const stage = h("div", { class: "wg-stage" });
const editorHost = h("div", { class: "wg-editor" });
const frameHost = h("div", { class: "wg-frame-host", hidden: true });
const ranNote = h("div", { class: "wg-ran-note" });
const props = h("aside", { class: "wg-props", "aria-label": "Properties" });

// The panes beside the editor fold away and stay folded (design principle 8.14: never crowd the code).
const FOLDED = "sab.widgets.folded";
function folded(): { list: boolean; props: boolean } {
  try {
    return { list: false, props: false, ...(JSON.parse(localStorage.getItem(FOLDED) ?? "{}") as object) };
  } catch {
    return { list: false, props: false };
  }
}
function fold(pane: "list" | "props", on?: boolean): void {
  const now = folded();
  now[pane] = on ?? !now[pane];
  root.classList.toggle("no-list", now.list);
  root.classList.toggle("no-props", now.props);
  try {
    localStorage.setItem(FOLDED, JSON.stringify(now));
  } catch {
    /* no storage: folded for this window only */
  }
  window.requestAnimationFrame(() => editor?.layout());
}
const listToggle = button("Widgets list (Ctrl+B)", () => fold("list"), { icon: "panel", iconOnly: true, class: "ghost wg-fold" });
const propsToggle = button("Properties (Ctrl+Alt+B)", () => fold("props"), { icon: "properties", iconOnly: true, class: "ghost wg-fold" });

function layout(): void {
  root.classList.toggle("no-list", folded().list);
  root.classList.toggle("no-props", folded().props);
  clear(root);
  list.append(
    h("div", { class: "wg-list-top" }, search, button("New widget", () => void newWidget(), { icon: "plus", class: "wg-new" })),
    listItems,
  );
  stage.append(editorHost, frameHost);
  editButton.hidden = true;
  copyButton.hidden = true;
  root.append(
    list,
    h("section", { class: "wg-main" }, h("div", { class: "wg-bar" }, listToggle, title, saved, h("span", { class: "wg-grow" }), copyButton, editButton, runButton, propsToggle), ranNote, stage),
    props,
  );
}

// ===== the list =====

function drawList(): void {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = widgets.filter((w) => words.every((word) => `${w.name} ${w.description} ${w.group} ${w.tags.join(" ")}`.toLowerCase().includes(word)));
  clear(listItems);
  const mine = shown.filter((w) => !w.prebuilt);
  const groups: [string, WidgetEntry[]][] = [["Your widgets", mine]];
  for (const w of shown.filter((x) => x.prebuilt)) {
    const group = groups.find(([g]) => g === w.group);
    if (group) group[1].push(w);
    else groups.push([w.group, [w]]);
  }
  for (const [group, items] of groups) {
    if (!items.length && group !== "Your widgets") continue;
    listItems.append(h("div", { class: "wg-group" }, group));
    if (!items.length) listItems.append(h("div", { class: "wg-empty" }, query ? "None match." : "None yet: New widget, or Copy as your own."));
    for (const w of items) {
      const item = h(
        "button",
        { type: "button", class: `wg-item${current?.name === w.name ? " selected" : ""}`, role: "option", "aria-selected": String(current?.name === w.name), "data-widget": w.name, onclick: () => void select(w.name) },
        h("span", { class: "wg-item-name" }, w.name),
        h("span", { class: "wg-item-desc" }, w.description),
      );
      listItems.append(item);
    }
  }
}

async function loadList(): Promise<void> {
  const found = await api<{ widgets: WidgetEntry[] }>("/streamlit/widgets");
  widgets = found.widgets;
  drawList();
}

async function loadContext(): Promise<void> {
  try {
    context = await api<Context>("/streamlit/widgets/context");
  } catch {
    /* the pickers take a typed value */
  }
}

// ===== one widget =====

const kernel = new Kernel(
  () => current?.kernel_path ?? null,
  () => null,
);
let primed = false;
async function prime(): Promise<void> {
  if (primed || !current) return;
  primed = true;
  try {
    await kernel.run({ code: current.kernel_setup }, () => undefined);
  } catch {
    primed = false; // no kernel here: completion falls back to the editor's own
  }
}

async function select(name: string, keepUrl = false): Promise<void> {
  if (running) edit();
  await flush();
  try {
    current = await api<WidgetFull>(`/streamlit/widgets/${encodeURIComponent(name)}`);
  } catch (e) {
    errorHere(e, {}, listItems);
    return;
  }
  if (!keepUrl) history.replaceState(null, "", `?name=${encodeURIComponent(name)}${location.hash}`);
  document.title = `${name} · Widgets`;
  title.textContent = current.name;
  saved.textContent = current.prebuilt ? "Prebuilt: read-only" : "";
  copyButton.hidden = !current.prebuilt;
  drawList();
  await showEditor(current);
  drawProps();
}

async function showEditor(widget: WidgetFull): Promise<void> {
  if (editor) {
    applying = true;
    editor.setValue(widget.code);
    applying = false;
    editor.setReadOnly(widget.prebuilt);
    editor.lint();
    return;
  }
  clear(editorHost, loadingBlock("Loading the editor…"));
  const m = await loadEditors();
  clear(editorHost);
  const names = (): { connections: string[]; blades: string[] } => ({ connections: [], blades: [] });
  const python = pythonCompleter(kernel, names);
  const docName = (): string => current?.file || `${current?.name ?? "widget"}.widget.py`;
  const intel = pythonIntel(kernel, { notebook: false, document: docName });
  editor = m.createCodeEditor(editorHost, {
    language: "python",
    value: widget.code,
    theme: effectiveTheme(),
    readOnly: widget.prebuilt,
    readOnlyMessage: "A prebuilt widget is read-only: Copy as your own to change it.",
    keys: { f5: () => void run(), escape: () => edit() },
    complete: async (text, offset) => {
      void prime();
      return (await intel.complete(text, offset)) ?? python(text, offset);
    },
    intel: {
      signature: intel.signature,
      hover: intel.hover,
      lint: intel.lint,
      onLint: (problems) => showProblems(`widget:${docName()}`, { document: docName(), place: "", problems, reveal: (line, column) => editor?.reveal(line, column) }),
    },
    help: (code, offset) => kernel.help(code, offset),
    inline: inlineSource(() => (current ? { key: `widget-${current.name}`, name: `${current.name}.py`, kind: "script", language: "python", text: editor?.value() ?? "" } : null)),
  });
  editor.onChange(() => {
    if (applying || !current) return;
    if (!current.prebuilt) {
      saved.textContent = "Saving…";
      if (saveTimer !== null) window.clearTimeout(saveTimer);
      saveTimer = window.setTimeout(() => void save(), 700);
    }
    if (propsTimer !== null) window.clearTimeout(propsTimer);
    propsTimer = window.setTimeout(() => void liveProps(), 250);
  });
  onThemeChange(() => editor?.setTheme(effectiveTheme()));
  void kernel.ensure().then(() => prime()).catch(() => undefined);
}

/** The code saved below its header (never a prebuilt one). */
async function save(): Promise<void> {
  saveTimer = null;
  if (!current || current.prebuilt || !editor) return;
  const code = editor.value();
  try {
    const after = await api<WidgetFull>(`/streamlit/widgets/${encodeURIComponent(current.name)}`, "PUT", { code });
    if (current && current.name === after.name) {
      current = { ...current, ...after, code };
      saved.textContent = "Saved";
    }
  } catch (e) {
    saved.textContent = "Not saved";
    errorHere(e, {}, saved);
  }
}

async function flush(): Promise<void> {
  if (saveTimer !== null) {
    window.clearTimeout(saveTimer);
    await save();
  }
}

/** The properties as the code is now (live as it is typed). */
async function liveProps(): Promise<void> {
  propsTimer = null;
  if (!current || !editor) return;
  try {
    const found = await api<{ properties: Prop[]; problem: WidgetEntry["problem"] }>("/streamlit/widgets/properties", "POST", { code: editor.value() });
    current = { ...current, properties: found.properties, problem: found.problem };
    drawProps();
  } catch {
    /* the pane keeps what it showed */
  }
}

// ===== the Properties pane =====

let checkTimer: number | null = null;

function headerFields(widget: WidgetFull): HTMLElement {
  const name = h("input", { class: "wg-name", value: widget.name, "aria-label": "Name", spellcheck: "false", "data-no-variables": "", readOnly: widget.prebuilt });
  const line = h("div", { class: "wg-name-line", "aria-live": "polite" });
  const description = h("textarea", { class: "wg-description", rows: 2, "aria-label": "Description", "data-no-variables": "", readOnly: widget.prebuilt }, widget.description);
  const check = async (): Promise<boolean> => {
    const said = await api<{ ok: boolean; state: string; said: string }>(`/streamlit/widgets/check-name?name=${encodeURIComponent(name.value)}&own=${encodeURIComponent(widget.name)}`);
    line.textContent = name.value === widget.name ? "" : said.said;
    line.dataset.state = said.state;
    return said.ok;
  };
  name.addEventListener("input", () => {
    if (checkTimer !== null) window.clearTimeout(checkTimer);
    checkTimer = window.setTimeout(() => void check(), 150);
  });
  const commit = async (): Promise<void> => {
    if (!current || current.prebuilt) return;
    const changes: Record<string, string> = {};
    if (name.value !== current.name) {
      if (!(await check())) return;
      changes.name = name.value;
    }
    if (description.value.trim() !== current.description) changes.description = description.value;
    if (!Object.keys(changes).length) return;
    await flush();
    try {
      const after = await api<WidgetFull>(`/streamlit/widgets/${encodeURIComponent(current.name)}`, "PATCH", changes);
      current = { ...current, ...after };
      title.textContent = after.name;
      document.title = `${after.name} · Widgets`;
      history.replaceState(null, "", `?name=${encodeURIComponent(after.name)}${location.hash}`);
      line.textContent = "";
      await loadList();
    } catch (e) {
      errorHere(e, {}, line);
    }
  };
  name.addEventListener("change", () => void commit());
  name.addEventListener("keydown", (e) => {
    if (e.key === "Enter") void commit();
  });
  description.addEventListener("change", () => void commit());
  return h(
    "div",
    { class: "wg-header" },
    h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, "Name"), name),
    line,
    h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, "Description"), description),
  );
}

function drawProps(): void {
  clear(props);
  if (!current) return;
  const widget = current;
  props.append(h("h2", { class: "wg-props-title" }, "Properties"), headerFields(widget));
  if (widget.problem) props.append(h("div", { class: "wg-props-problem" }, icon("warning"), `${widget.problem.error} ${widget.problem.fix}`));
  const values: Record<string, unknown> = Object.fromEntries(widget.properties.map((p) => [p.name, p.default]));
  if (!widget.properties.length && !widget.problem) props.append(h("p", { class: "wg-props-none" }, "A top-level value in the code (title = \"Sales\") is a property."));
  for (const prop of widget.properties) {
    props.append(
      propertyField(prop, values, context, widget.prebuilt, async (value, said) => {
        if (!current || !editor) return;
        const checked = await api<{ ok: boolean; said?: string; fix?: string }>("/streamlit/widgets/check-value", "POST", { code: editor.value(), property: prop.name, value, values });
        if (!checked.ok) return said(`${checked.said ?? ""} ${checked.fix ?? ""}`.trim());
        said("");
        await flush();
        const after = await api<WidgetFull>(`/streamlit/widgets/${encodeURIComponent(current.name)}/property`, "POST", { property: prop.name, value, code: editor.value(), values });
        applying = true;
        editor.replaceText(after.code);
        applying = false;
        current = { ...current, ...after };
        saved.textContent = "Saved";
        values[prop.name] = value;
        if (running) void run();
      }),
    );
  }
  if (!widget.prebuilt) {
    props.append(
      h(
        "div",
        { class: "wg-props-foot" },
        button(
          "Delete widget",
          () => {
            if (!current || !confirm(`Delete ${current.name} from the library?`)) return;
            void api(`/streamlit/widgets/${encodeURIComponent(current.name)}`, "DELETE")
              .then(async () => {
                current = null;
                await loadList();
                const first = widgets[0];
                if (first) await select(first.name);
              })
              .catch((e) => errorHere(e, {}, props));
          },
          { icon: "trash", class: "ghost danger" },
        ),
      ),
    );
  }
}

// ===== Run in place =====

async function run(): Promise<void> {
  if (!current || !editor) return;
  const widget = current;
  clearError(ranNote);
  await busyButton(runButton, async () => {
    try {
      const said = await busy(stage, `Running ${widget.name}…`, api<{ ok: boolean; url?: string; problem?: { kind: string; message?: string; feature?: string; command?: string } }>(`/streamlit/widgets/${encodeURIComponent(widget.name)}/run`, "POST", { code: editor!.value(), window: WINDOW_ID }), { errorIn: false });
      if (!said.ok || !said.url) {
        showError(ranNote, new Error(said.problem?.message ?? (said.problem?.kind === "missing" ? `Streamlit widgets need ${said.problem.command ?? "Streamlit"} in this Python.` : "The widget did not run.")));
        return;
      }
      const frame = h("iframe", { class: "wg-frame", src: said.url, title: `${widget.name}, running` });
      clear(frameHost, frame);
      editorHost.hidden = true;
      frameHost.hidden = false;
      running = true;
      runButton.textContent = "Run again";
      editButton.hidden = false;
      // Its errors, headless: said above the frame, and the line marked in the code.
      void api<{ ok: boolean; pages?: { failed: string[]; exceptions: string[] }[] }>(`/streamlit/widgets/${encodeURIComponent(widget.name)}/check`, "POST", { code: editor!.value() })
        .then((checked) => {
          const failed = (checked.pages ?? []).flatMap((p) => [...p.failed, ...p.exceptions]);
          if (!failed.length) return;
          showError(ranNote, new Error(failed[0]!));
          const line = /\(line (\d+)\)/.exec(failed.join("\n"));
          if (line) editor?.setProblems([{ line: Number(line[1]), col: null, endLine: Number(line[1]), endCol: null, message: failed[0]!, hover: failed[0]!, severity: "error", fixes: [] }]);
        })
        .catch(() => undefined);
    } catch (e) {
      showError(ranNote, e);
    }
  });
}

function edit(): void {
  if (!running) return;
  running = false;
  frameHost.hidden = true;
  clear(frameHost);
  editorHost.hidden = false;
  editButton.hidden = true;
  runButton.replaceChildren(icon("play"), "Run");
  editor?.layout();
  editor?.focus();
  void api("/streamlit/widgets/stop", "POST", { window: WINDOW_ID }).catch(() => undefined);
}

// ===== new, copy =====

async function newWidget(): Promise<void> {
  try {
    const made = await api<WidgetFull>("/streamlit/widgets", "POST", {});
    await loadList();
    await select(made.name);
  } catch (e) {
    errorHere(e, {}, list);
  }
}

async function copyCurrent(): Promise<void> {
  if (!current) return;
  try {
    const made = await api<WidgetFull>(`/streamlit/widgets/${encodeURIComponent(current.name)}/copy`, "POST", {});
    await loadList();
    await select(made.name);
  } catch (e) {
    errorHere(e, {}, copyButton);
  }
}

// ===== start =====

async function start(): Promise<void> {
  watchTheme();
  if (!(await requireSession())) return;
  layout();
  search.addEventListener("input", () => {
    query = search.value;
    drawList();
  });
  listItems.append(loadingBlock("Loading the widgets…"));
  await Promise.all([loadList(), loadContext()]);
  const wanted = params.get("name");
  const first = wanted && widgets.some((w) => w.name === wanted) ? wanted : (widgets.find((w) => !w.prebuilt) ?? widgets[0])?.name;
  if (first) await select(first, true);
  connect(() => undefined, { widgets: "1", window: WINDOW_ID });
  onNotice((notice) => {
    if (notice.type === "widgets_changed") {
      void loadList();
      const said = notice as unknown as { name: string; old?: string | null };
      // Changed by the agent (or another window) while it is not being typed in: shown as it is now.
      if (current && (said.name === current.name || said.old === current.name) && saveTimer === null && !editor?.hasFocus()) void select(said.name, true);
    }
    if (notice.type === "tables_changed" || notice.type === "dataset_added" || notice.type === "dataset_closed") void loadContext().then(drawProps);
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
      e.preventDefault();
      fold(e.altKey ? "props" : "list");
    }
    if (e.key === "Escape" && running) edit();
    if (e.key === "F5") {
      e.preventDefault();
      void run();
    }
  });
  window.addEventListener("pagehide", () => {
    void flush();
    void fetch("/streamlit/widgets/stop", { method: "POST", credentials: "same-origin", keepalive: true, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ window: WINDOW_ID }) });
  });
}

void start();
