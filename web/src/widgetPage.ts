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
 *   [CODE|PREVIEW] one two-state switch in the slim bar (the owner, 2026-11-21: "one two-state switch: Code |
 *                Preview"): Preview (F5) runs the widget and shows it in the editor's place (the widget alone
 *                through the Streamlit proxy, with the properties' values); Code (or Esc) turns it back into
 *                code. A run that fails shows the error panel in the Preview with a link to its line in the
 *                Code. Which one a widget was in is remembered for the session (sessionStorage)
 *   [IDE]        the middle is codeIde.ts (the blade IDE's shell: the slim bar, Monaco, Properties, the
 *                Output | Result | Problems panel folded until wanted)
 *   [PROPERTIES] right: Name (checked live: available, taken, not a valid name) and Description (the file's
 *                header only), then the properties the code makes (its top-level plain values), each with its
 *                mask; a value is checked before it is kept and written into only its own characters
 *
 * ROUTING: /streamlit/widgets (list, new), …/{name} (get, save, header, delete), …/{name}/property, …/copy,
 * …/run, …/check, /streamlit/widgets/properties (live), …/check-name, …/check-value, …/context.
 */
import { api, connect, onNotice, requireSession } from "./api";
import { button, clear, h, icon } from "./dom";
import { errorHere, showError } from "./errorNote";
import { inlineSource } from "./inlineCompletion";
import type { CodeEditor } from "./lazy/codeEditor";
import { type CodeIde, codeIde } from "./codeIde";
import { busy, loadingBlock } from "./loading";
import { watchTheme } from "./catalogRail";
import { effectiveTheme, onThemeChange } from "./theme";
import { pythonCompleter } from "./workbenchCompletion";
import { pythonIntel, showProblems } from "./workbenchIntel";
import { Kernel, WINDOW_ID } from "./workbenchKernel";
import { type Prop, propertyField } from "./widgetFields";
import { headingElement, headingOf } from "./widgetPacks";
import { loadPageRules } from "./workbenchPages";

export interface WidgetEntry {
  name: string;
  description: string;
  framework: string;
  group: string;
  /** The starter pack a prebuilt widget belongs to ("": none) and the pack's description. */
  pack: string;
  pack_description: string;
  tags: string[];
  size: [number, number];
  min_size: [number, number];
  prebuilt: boolean;
  /** Where it lives (the project's widgets/ first) and the places further down it wins over. */
  where?: "project" | "library" | "prebuilt";
  hides?: string[];
  properties: Prop[];
  /** Its contract: Ins, Outs and Events declared in its code (domain/widget_contract.py). */
  contract?: { ins: ContractPort[]; outs: ContractPort[]; events: ContractPort[] };
  problem: { error: string; fix: string; line: number | null } | null;
  hash: string;
}

interface ContractPort {
  name: string;
  type: string;
  words: string;
  default: unknown;
  help: string;
  line: number;
  problem: string | null;
}

interface WidgetFull extends WidgetEntry {
  code: string;
  file: string;
  kernel_path: string | null;
  kernel_setup: string;
  /** Upgrade to In/Out is offered: its code hands values on by session state keys. */
  upgradable?: boolean;
}

export interface Context {
  tables: Record<string, string[] | null>;
  variables: string[];
}


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
const search = h("input", { type: "search", class: "wg-search", placeholder: "Search", "aria-label": "Search widgets", "data-no-variables": "" });
const listItems = h("div", { class: "wg-items", role: "listbox", "aria-label": "Widgets" });
const saved = h("span", { class: "wg-saved", "aria-live": "polite" });
const copyButton = button("Copy as your own", () => void copyCurrent(), { icon: "copy", class: "ide-btn ghost wg-copy" });
// Copy to project / Copy to library: the same widget in the other place (the project's wins on its canvases).
const placeButton = button("Copy to project", () => void copyCurrent(current?.where === "project" ? "library" : "project", placeButton), { icon: "copy", class: "ide-btn ghost wg-copy-place" });
let projectOpen = false;
// Code | Preview: one two-state switch (F5 Preview, Esc Code).
const codeTab = h("button", { type: "button", class: "wg-mode-item on", "aria-pressed": "true", "data-mode": "code", title: "Code (Esc)", onclick: () => edit() }, icon("code"), "Code");
const previewTab = h("button", { type: "button", class: "wg-mode-item", "aria-pressed": "false", "data-mode": "preview", title: "Preview (F5)", onclick: () => void run() }, icon("play"), "Preview");
const modeSwitch = h("span", { class: "wg-mode", role: "group", "aria-label": "Code or Preview" }, codeTab, previewTab);
const frameHost = h("div", { class: "wg-frame-host" });
const props = h("div", { class: "wg-props", "aria-label": "Properties" });
const main = h("section", { class: "wg-main" });
let ide: CodeIde | null = null;

// The widgets list folds away and stays folded (design principle 8.14: never crowd the code); Properties is
// codeIde.ts's own pane (its switch, Ctrl+Alt+B).
const FOLDED = "sab.widgets.folded";
function folded(): { list: boolean } {
  try {
    return { list: false, ...(JSON.parse(localStorage.getItem(FOLDED) ?? "{}") as object) };
  } catch {
    return { list: false };
  }
}
function fold(on?: boolean): void {
  const now = folded();
  now.list = on ?? !now.list;
  root.classList.toggle("no-list", now.list);
  try {
    localStorage.setItem(FOLDED, JSON.stringify(now));
  } catch {
    /* no storage: folded for this window only */
  }
  window.requestAnimationFrame(() => editor?.layout());
}
const listToggle = button("Widgets list (Ctrl+B)", () => fold(), { icon: "panel", iconOnly: true, class: "ide-btn ghost wg-fold" });

/** Which a widget was in, Code or Preview, for this session. */
function viewOf(name: string): "code" | "preview" {
  try {
    return sessionStorage.getItem(`sab.widgets.view:${name}`) === "preview" ? "preview" : "code";
  } catch {
    return "code";
  }
}
function keepView(name: string, view: "code" | "preview"): void {
  try {
    sessionStorage.setItem(`sab.widgets.view:${name}`, view);
  } catch {
    /* this widget's view is not remembered */
  }
}
function drawMode(): void {
  codeTab.classList.toggle("on", !running);
  codeTab.setAttribute("aria-pressed", String(!running));
  previewTab.classList.toggle("on", running);
  previewTab.setAttribute("aria-pressed", String(running));
}

function layout(): void {
  root.classList.toggle("no-list", folded().list);
  clear(root);
  list.append(
    h("div", { class: "wg-list-top" }, search, button("New widget", () => void newWidget(), { icon: "plus", class: "wg-new" })),
    listItems,
  );
  copyButton.hidden = true;
  clear(main, loadingBlock("Loading the editor…"));
  root.append(list, main);
}

// ===== the list =====

function drawList(): void {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = widgets.filter((w) => words.every((word) => `${w.name} ${w.description} ${w.group} ${w.pack} ${w.tags.join(" ")}`.toLowerCase().includes(word)));
  clear(listItems);
  const groups: [string, WidgetEntry[]][] = [
    ["This project", shown.filter((w) => w.where === "project")],
    ["Library", shown.filter((w) => !w.prebuilt && w.where !== "project")],
  ];
  for (const w of shown.filter((x) => x.prebuilt)) {
    const group = groups.find(([g]) => g === headingOf(w));
    if (group) group[1].push(w);
    else groups.push([headingOf(w), [w]]);
  }
  for (const [group, items] of groups) {
    if (!items.length && (group !== "Library" || groups[0]![1].length)) continue;
    listItems.append(items[0] ? headingElement("wg-group", items[0]) : h("div", { class: "wg-group" }, group));
    if (!items.length) listItems.append(h("div", { class: "wg-empty" }, query ? "None match." : "None yet: New widget, or Copy as your own."));
    for (const w of items) {
      const item = h(
        "button",
        { type: "button", class: `wg-item${current?.name === w.name ? " selected" : ""}`, role: "option", "aria-selected": String(current?.name === w.name), "data-widget": w.name, onclick: () => void select(w.name) },
        h("span", { class: "wg-item-name" }, w.name),
        w.hides?.length ? h("span", { class: "wg-item-hides", title: `This project's ${w.name} is used instead of the ${w.hides.join(" and ")}'s` }, `Instead of the ${w.hides.join(" and ")}'s`) : null,
        h("span", { class: "wg-item-desc" }, w.description),
      );
      listItems.append(item);
    }
  }
}

async function loadList(): Promise<void> {
  const found = await api<{ widgets: WidgetEntry[]; project_folder?: string }>("/streamlit/widgets");
  projectOpen = Boolean(found.project_folder);
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
  if (running) toCode();
  await flush();
  try {
    current = await api<WidgetFull>(`/streamlit/widgets/${encodeURIComponent(name)}`);
  } catch (e) {
    errorHere(e, {}, listItems);
    return;
  }
  if (!keepUrl) history.replaceState(null, "", `?name=${encodeURIComponent(name)}${location.hash}`);
  document.title = `${name} · Widgets`;
  ide?.setName(current.name);
  saved.textContent = current.prebuilt ? "Prebuilt: read-only" : "";
  copyButton.hidden = !current.prebuilt;
  placeButton.hidden = current.prebuilt || (current.where !== "project" && !projectOpen);
  const placeWords = current.where === "project" ? "Copy to library" : "Copy to project";
  placeButton.querySelector(".btn-label")!.textContent = placeWords;
  placeButton.setAttribute("aria-label", placeWords);
  placeButton.title = placeWords;
  drawList();
  await showEditor(current);
  drawProps();
  if (viewOf(name) === "preview") void run();
}

async function showEditor(widget: WidgetFull): Promise<void> {
  if (editor && ide) {
    applying = true;
    ide.setValue(widget.code, true);
    applying = false;
    editor.setReadOnly(widget.prebuilt);
    editor.lint();
    return;
  }
  const names = (): { connections: string[]; blades: string[] } => ({ connections: [], blades: [] });
  const python = pythonCompleter(kernel, names);
  const docName = (): string => current?.file || `${current?.name ?? "widget"}.widget.py`;
  const intel = pythonIntel(kernel, { notebook: false, document: docName });
  // The blade IDE's shell (codeIde.ts): the slim bar (the list's fold, the name, Saved, Copy as your own,
  // Code | Preview, Properties), Monaco with the Workbench's intelligence, the panel folded until wanted.
  ide = codeIde({
    name: widget.name,
    badge: saved,
    language: "python",
    value: widget.code,
    theme: effectiveTheme,
    actions: [copyButton, placeButton, modeSwitch],
    stage: frameHost,
    properties: props,
    propertiesOpen: true,
    remember: "widgets",
    editor: {
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
    },
  });
  ide.element.querySelector(".ide-bar")?.prepend(listToggle);
  clear(main, ide.element);
  editor = await ide.ready;
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
    const found = await api<{ properties: Prop[]; contract: WidgetEntry["contract"]; problem: WidgetEntry["problem"] }>("/streamlit/widgets/properties", "POST", { code: editor.value() });
    current = { ...current, properties: found.properties, contract: found.contract, problem: found.problem };
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
    const own = (): string => current?.name ?? widget.name;
    const said = await api<{ ok: boolean; state: string; said: string }>(`/streamlit/widgets/check-name?name=${encodeURIComponent(name.value)}&own=${encodeURIComponent(own())}`);
    line.textContent = name.value === own() ? "" : said.said; // a rename may have landed meanwhile
    line.dataset.state = said.state;
    return said.ok;
  };
  name.addEventListener("input", () => {
    if (checkTimer !== null) window.clearTimeout(checkTimer);
    checkTimer = window.setTimeout(() => void check(), 150);
  });
  // Enter sends it and so does the change that follows: one at a time, the second sees the first's answer.
  let committing: Promise<void> = Promise.resolve();
  const commit = (): Promise<void> => (committing = committing.then(commitOnce, commitOnce));
  const commitOnce = async (): Promise<void> => {
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
      const before = current.name;
      const after = await api<WidgetFull>(`/streamlit/widgets/${encodeURIComponent(before)}`, "PATCH", changes);
      if (after.name !== before) keepView(after.name, viewOf(before));
      current = { ...current, ...after };
      ide?.setName(after.name);
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
  props.append(headerFields(widget));
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
  props.append(...contractSections(widget));
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

/** The contract, read-only: its Inputs, Outputs and Events as the code declares them (the Canvas wires them);
 *  Upgrade to In/Out for a widget that hands values on by session state keys (a preview first). */
function contractSections(widget: WidgetFull): HTMLElement[] {
  const out: HTMLElement[] = [];
  const port = (p: ContractPort, kind: string): HTMLElement =>
    h(
      "div",
      { class: `wg-prop wg-port${p.problem ? " marked" : ""}`, "data-port": p.name, "data-direction": kind },
      h("div", { class: "wg-prop-head" }, h("span", { class: "wg-prop-name" }, p.name), h("span", { class: "wg-prop-mask" }, kind === "event" ? "Event" : `${kind === "in" ? "In" : "Out"} · ${p.words}`)),
      p.help ? h("div", { class: "wg-prop-help" }, p.help) : null,
      p.problem ? h("div", { class: "wg-field-line" }, p.problem) : null,
    );
  const c = widget.contract;
  if (c?.ins.length) out.push(h("section", { class: "wg-contract", "data-section": "inputs" }, h("h3", {}, "Inputs"), ...c.ins.map((p) => port(p, "in"))));
  if (c?.outs.length) out.push(h("section", { class: "wg-contract", "data-section": "outputs" }, h("h3", {}, "Outputs"), ...c.outs.map((p) => port(p, "out"))));
  if (c?.events.length) out.push(h("section", { class: "wg-contract", "data-section": "events" }, h("h3", {}, "Events"), ...c.events.map((p) => port(p, "event"))));
  if (widget.upgradable && !widget.prebuilt) {
    const said = h("div", { class: "wg-field-line", hidden: true });
    out.push(
      h(
        "section",
        { class: "wg-contract wg-upgrade" },
        button("Upgrade to In/Out…", () => void upgradePreview(widget, said), { icon: "link", class: "ghost wg-upgrade-button" }),
        said,
      ),
    );
  }
  return out;
}

async function upgradePreview(widget: WidgetFull, said: HTMLElement): Promise<void> {
  try {
    await flush();
    const plan = await api<{ diff: string; changes: { key: string; port: string; direction: string; type: string }[]; kept: string[] }>(`/streamlit/widgets/${encodeURIComponent(widget.name)}/upgrade`, "POST", {});
    const dialog = h(
      "dialog",
      { class: "wg-upgrade-dialog", "aria-label": "Upgrade to In/Out" },
      h("h2", {}, "Upgrade to In/Out"),
      h("ul", {}, ...plan.changes.map((c) => h("li", {}, `${c.key}: ${c.port}: ${c.direction === "in" ? "In" : "Out"}[${c.type}]`))),
      plan.kept.length ? h("p", { class: "wg-prop-help" }, `Kept as it is: ${plan.kept.join("; ")}`) : null,
      h("pre", { class: "wg-upgrade-diff" }, plan.diff),
      h(
        "div",
        { class: "wg-dialog-buttons" },
        button("Cancel", () => dialog.close(), { class: "ghost" }),
        button("Apply", async () => {
          try {
            const done = await api<{ saved: WidgetFull }>(`/streamlit/widgets/${encodeURIComponent(widget.name)}/upgrade`, "POST", { apply: true });
            dialog.close();
            applying = true;
            editor?.replaceText(done.saved.code);
            applying = false;
            current = { ...widget, ...done.saved };
            drawProps();
          } catch (e) {
            errorHere(e, {}, dialog);
          }
        }, { class: "primary" }),
      ),
    );
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  } catch (e) {
    said.hidden = false;
    errorHere(e, {}, said);
  }
}

// ===== Run in place =====

async function run(): Promise<void> {
  if (!current || !editor || !ide) return;
  const widget = current;
  const code = editor.value();
  running = true;
  keepView(widget.name, "preview");
  drawMode();
  ide.setStage(true);
  try {
    const said = await busy(frameHost, `Running ${widget.name}…`, api<{ ok: boolean; url?: string; problem?: { kind: string; message?: string; feature?: string; command?: string } }>(`/streamlit/widgets/${encodeURIComponent(widget.name)}/run`, "POST", { code, window: WINDOW_ID }), { errorIn: false });
    if (!running || current !== widget) return;
    if (!said.ok || !said.url) {
      failed(new Error(said.problem?.message ?? (said.problem?.kind === "missing" ? `Streamlit widgets need ${said.problem.command ?? "Streamlit"} in this Python.` : "The widget did not run.")), null);
      return;
    }
    clear(frameHost, h("iframe", { class: "wg-frame", src: said.url, title: `${widget.name}, running` }));
    // Its errors, headless: the error panel in the Preview, its line linked to the Code (and marked there).
    void api<{ ok: boolean; pages?: { failed: string[]; exceptions: string[] }[] }>(`/streamlit/widgets/${encodeURIComponent(widget.name)}/check`, "POST", { code })
      .then((checked) => {
        const found = (checked.pages ?? []).flatMap((p) => [...p.failed, ...p.exceptions]);
        if (!found.length || !running || current !== widget) return;
        const line = /\(line (\d+)\)/.exec(found.join("\n"));
        const at = line ? Number(line[1]) : null;
        if (at) editor?.setProblems([{ line: at, col: null, endLine: at, endCol: null, message: found[0]!, hover: found[0]!, severity: "error", fixes: [] }]);
        failed(new Error(found[0]!), at);
      })
      .catch(() => undefined);
  } catch (e) {
    failed(e, null);
  }
}

/** A failed run: the error panel in the Preview, above what drew; a link back to its line in the Code. */
function failed(error: unknown, line: number | null): void {
  const note = h("div", { class: "wg-preview-error" });
  frameHost.prepend(note);
  showError(note, error);
  if (line !== null) {
    note.append(
      button(`Go to line ${line} in the code`, () => {
        edit();
        editor?.reveal(line, 1);
      }, { icon: "code", class: "ghost wg-goto-line" }),
    );
  }
}

function edit(): void {
  if (current) keepView(current.name, "code");
  toCode();
}

/** Back to the code (the remembered view left as it is: another widget chosen). */
function toCode(): void {
  if (!running) return;
  running = false;
  clear(frameHost);
  drawMode();
  ide?.setStage(false);
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

async function copyCurrent(to?: "project" | "library", from: HTMLElement = copyButton): Promise<void> {
  if (!current) return;
  try {
    const made = await api<WidgetFull>(`/streamlit/widgets/${encodeURIComponent(current.name)}/copy`, "POST", to ? { to } : {});
    await loadList();
    await select(made.name);
  } catch (e) {
    errorHere(e, {}, from);
  }
}

// ===== start =====

async function start(): Promise<void> {
  watchTheme();
  if (!(await requireSession())) return;
  await loadPageRules();
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
      if (current && (said.name === current.name || said.old === current.name) && saveTimer === null && !editor?.hasFocus() && !props.contains(document.activeElement)) void select(said.name, true);
    }
    if (notice.type === "tables_changed" || notice.type === "dataset_added" || notice.type === "dataset_closed") void loadContext().then(drawProps);
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
      e.preventDefault();
      if (e.altKey) ide?.toggleProperties();
      else fold();
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
