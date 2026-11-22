/**
 * structuresPage.ts: the Structures page, on the rail after APIs (the owner, 2026-11-17: "we need a place
 * to visualize them differently like a pretty place to render it that functions like the grids, where
 * you can transform and save json configurations as well as view returned payloads from apis"; the name
 * is the owner's: Structures). Grids hold rows and columns; Structures hold nested data. [SHARED]
 *
 *   [TABS]    an open structure is a tab, as a table's grid is: a file (Open…: .json, .yaml, .xml, .toml),
 *             pasted text (its format found), New (an object or a list), an API's answer (the APIs page),
 *             a Workbench kernel's dict or list. With none open, the project's structure files as cards.
 *   [VIEWS]   the tree and the text side by side (or one of them): a click on a node says its path
 *             ($.orders[3].lines, Copy); a double click edits a value or a key (each a step); the text in
 *             its format's colours, its error at its line, edited only while there are no steps (then the
 *             file's own text, kept as typed). A file opened from the code pages' Files pane is a tab there
 *             instead, beside the code (structureDoc.ts): its text always the file's, the steps a view.
 *   [STEPS]   a strip of steps as the grid's: Pick, Filter, Rename, Remove, Set, Add, Sort, Flatten, each
 *             from the selected node's actions; Undo, Redo; a step's × removes it.
 *   [MAKE]    Open as grid (a list of records at any path); Save, Save as (JSON, YAML, XML, TOML);
 *             an API's answer: Run again (the same call, the steps kept), Return as table… on a list (its
 *             web call blade, switched on), and the Lineage (the call, the steps, the grids made).
 *   [PAGE]    a page of the rail's over any page (areaPage.ts), in the address as open=structures.
 *
 * ROUTING: /structures (GET list, POST new), /structures/open, /structures/paste, /structures/{id} (GET,
 *          PUT text|format|name, DELETE), /steps, /steps/remove, /undo, /redo, /grid, /save, /save-as,
 *          /run-again, /lineage  ·  PUT /apis/{api}/calls/{operation}  ·  notice structures_changed
 */
import { api, ApiError, onNotice } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { askYesNo, button, h, icon, openDialog, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { busy, busyClick, loadingBlock } from "./loading";
import { promptForError } from "./missingPackages";
import { STRUCTURES } from "./lazyPages";
import { dismissDialog, layerOpened, registerLayer, setOverTitle, watchLayerDialog } from "./nav";
import { FORMAT_NAMES, FORMATS, type Format, isRecords, kindOf, mountText, mountTree, nodeAt, type Part, pathText, type TextView, type Tree, type Value } from "./structureTree";
import { effectiveTheme } from "./theme";
import { errorHere, errorMark, errorNote } from "./errorNote";
import { makeVariant } from "./dataSandbox";
import { structureSuffixes } from "./structurePaths";

/** The page's name, in one place (the owner chose it, 2026-11-17): the rail, the title, the tabs. */

export interface StepJson {
  op: string;
  path: string;
  words: string;
}

export interface Summary {
  id: string;
  name: string;
  format: Format;
  path: string | null;
  origin: { kind: string; api?: string; operation?: string; method?: string; path?: string; status?: number; ms?: number; headers?: Record<string, string>; at?: string; said?: string };
  steps: StepJson[];
  can_redo: boolean;
  dirty: boolean;
  version: number;
  type: string;
  count: number | null;
  nodes: number;
  error: string | null;
}

interface Shown extends Summary {
  value?: Value;
  text?: string;
  text_error?: string;
  /** With steps: their result written in its format (the text view, read-only here). */
  result_text?: string;
}

interface FileCard {
  name: string;
  file: string;
  path: string;
  format: Format;
  size: number;
  open: string | null;
}

let shownPage: PageElement | null = null;
let reload: (() => void) | null = null;
let wanted: string | null = null; // a structure to bring to the front when the page draws
let wantedAt: Part[] | null = null; // and the node to select in it (the Data Explorer's Open at this node)

registerLayer("structures", {
  isOpen: () => Boolean(shownPage?.open),
  open: () => drawPage(),
  show: () => undefined,
  dismiss: () => {
    if (shownPage) dismissDialog(shownPage);
  },
});

onNotice((n) => {
  if (n.type === "structures_changed") reload?.();
});

/** The Structures page, opened by the user (the rail's icon); `id`: that structure in front. */
export function openStructures(id: string | null = null, at: Part[] | null = null): void {
  wanted = id;
  wantedAt = at;
  if (shownPage?.open) {
    reload?.();
    return;
  }
  layerOpened("structures");
  drawPage();
}

const size = (bytes: number): string => (bytes < 1024 ? `${bytes} B` : bytes < 1024 ** 2 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 ** 2).toFixed(1)} MB`);

async function call<T>(path: string, method = "GET", body?: unknown): Promise<T | null> {
  try {
    return await api<T>(path, method, body);
  } catch (e) {
    if (!promptForError(e instanceof ApiError ? safeJson(e.message) : e)) errorHere(e);
    return null;
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function drawPage(): void {
  const { element, body, actions } = openAreaPage("structures", STRUCTURES);
  shownPage = element;
  body.classList.add("structures-page");
  setOverTitle(STRUCTURES);
  let open: Summary[] = [];
  let files: FileCard[] = [];
  let front: string | null = wanted;
  let doc: Shown | null = null;
  let tree: Tree | null = null;
  let text: TextView | null = null;
  let view = "both";
  let selected: Part[] = [];
  const tabs = h("div", { class: "structures-tabs", role: "tablist", "aria-label": STRUCTURES });
  const main = h("div", { class: "structures-main" });
  body.append(tabs, main);
  actions.replaceChildren(
    button("New", () => void newOne("object"), { icon: "plus", class: "primary" }),
    button("Open…", () => void openFile(), { icon: "folder" }),
    button("Paste", () => paste(), { icon: "copy" }),
  );

  const newOne = async (kind: string): Promise<void> => {
    const made = await call<Summary>("/structures", "POST", { kind, name: "Untitled" });
    if (made) await go(made.id);
  };
  const openFile = async (): Promise<void> => {
    const path = await chooseFile({ title: `Open a ${STRUCTURES.toLowerCase().replace(/s$/, "")}`, mode: "file", suffixes: structureSuffixes() });
    if (!path) return;
    const made = await call<Summary>("/structures/open", "POST", { path });
    if (made) await go(made.id);
  };
  const paste = (): void => {
    const { dialog, body: box, foot, close } = openDialog("Paste");
    const area = h("textarea", { class: "mono structures-paste", rows: 14, spellcheck: false, "aria-label": "Text", placeholder: '{"gates": []}' }) as HTMLTextAreaElement;
    const format = h("select", { "aria-label": "Format" }, h("option", { value: "" }, "Find the format"), ...FORMATS.map((f) => h("option", { value: f }, FORMAT_NAMES[f]))) as HTMLSelectElement;
    const name = h("input", { "aria-label": "Name", placeholder: "Name", value: "Pasted" }) as HTMLInputElement;
    box.append(h("div", { class: "structures-paste-row" }, name, format), area);
    foot.append(
      button("Cancel", () => close()),
      button("Open", async () => {
        const made = await call<Summary>("/structures/paste", "POST", { text: area.value, format: format.value || undefined, name: name.value || "Pasted" });
        if (made) {
          close();
          await go(made.id);
        }
      }, { class: "primary" }),
    );
    dialog.addEventListener("close", () => undefined);
    area.focus();
  };

  const go = async (id: string): Promise<void> => {
    front = id;
    await load();
  };

  const load = async (): Promise<void> => {
    if (!element.open) return;
    const got = await call<{ open: Summary[]; files: FileCard[] }>("/structures");
    if (!got) return;
    open = got.open;
    files = got.files;
    if (wanted) {
      front = wanted;
      wanted = null;
    }
    if (!front || !open.some((s) => s.id === front)) front = open.at(-1)?.id ?? null;
    drawTabs();
    if (front) {
      doc = await call<Shown>(`/structures/${encodeURIComponent(front)}`);
      drawDoc();
    } else {
      doc = null;
      drawLanding();
    }
  };
  reload = () => void load();

  const drawTabs = (): void => {
    tabs.replaceChildren(
      ...open.map((s) =>
        h(
          "div",
          { class: `structures-tab${s.id === front ? " current" : ""}`, role: "tab", "aria-selected": s.id === front ? "true" : "false", "data-structure": s.id },
          h("button", { type: "button", class: "structures-tab-name", onclick: () => void go(s.id) }, icon(s.origin.kind === "api" ? "bolt" : "json"), s.name, s.dirty ? h("span", { class: "structures-dirty", "aria-label": "Unsaved" }, "●") : null),
          h("button", { type: "button", class: "structures-tab-close", "aria-label": `Close ${s.name}`, title: "Close", onclick: async () => {
            if (s.dirty && !(await askYesNo(`${s.name} has changes that are not saved. Close it?`))) return;
            await call(`/structures/${encodeURIComponent(s.id)}`, "DELETE");
            if (front === s.id) front = null;
            await load();
          } }, icon("close")),
        ),
      ),
    );
    tabs.hidden = open.length === 0;
  };

  const drawLanding = (): void => {
    text?.dispose();
    text = null;
    tree = null;
    if (!files.length) {
      main.replaceChildren(h("div", { class: "structures-empty" }, h("p", { class: "empty-note" }, "Nothing open."), h("div", { class: "structures-empty-actions" }, button("New object", () => void newOne("object"), { icon: "plus" }), button("New list", () => void newOne("list"), { icon: "plus" }), button("Open…", () => void openFile(), { icon: "folder" }))));
      return;
    }
    main.replaceChildren(
      h(
        "div",
        { class: "structures-cards", role: "list" },
        ...files.map((f) => {
          const used = h("span", { class: "structures-card-used muted" });
          void api<{ references: unknown[] }>(`/structures/references?name=${encodeURIComponent(f.name)}`).then((r) => {
            used.textContent = r.references.length ? `used in ${r.references.length} place${r.references.length === 1 ? "" : "s"}` : "";
          }, () => undefined);
          return h(
            "button",
            { type: "button", class: "structures-card", role: "listitem", "data-file": f.file, onclick: async () => {
              const made = await call<Summary>("/structures/open", "POST", { path: f.path });
              if (made) await go(made.id);
            } },
            h("span", { class: "structures-card-name" }, icon("json"), f.name),
            h("span", { class: "structures-card-meta muted" }, `${FORMAT_NAMES[f.format]} · ${size(f.size)}`),
            used,
          );
        }),
      ),
    );
  };

  // ----- one structure -----

  const step = async (s: Record<string, unknown>): Promise<void> => {
    if (!doc) return;
    const done = await call<Shown>(`/structures/${encodeURIComponent(doc.id)}/steps`, "POST", s);
    if (done) {
      doc = done;
      drawDoc();
      await refreshTabs();
    }
  };
  const refreshTabs = async (): Promise<void> => {
    const got = await call<{ open: Summary[]; files: FileCard[] }>("/structures");
    if (got) {
      open = got.open;
      drawTabs();
    }
  };
  const act = async (path: string, method = "POST", body: unknown = {}): Promise<void> => {
    if (!doc) return;
    const done = await call<Shown>(`/structures/${encodeURIComponent(doc.id)}${path}`, method, body);
    if (done) {
      if ("value" in done || "text" in done) doc = done;
      else doc = await call<Shown>(`/structures/${encodeURIComponent(doc.id)}`);
      drawDoc();
      await refreshTabs();
    }
  };

  const ask = (title: string, fields: { name: string; label: string; value?: string; options?: string[] }[], run: (values: Record<string, string>) => void): void => {
    const { body: box, foot, close } = openDialog(title);
    const inputs = new Map<string, HTMLInputElement | HTMLSelectElement>();
    for (const f of fields) {
      const input = f.options
        ? (h("select", { "aria-label": f.label }, ...f.options.map((o) => h("option", { value: o, selected: o === f.value }, o))) as HTMLSelectElement)
        : (h("input", { "aria-label": f.label, value: f.value ?? "", spellcheck: false }) as HTMLInputElement);
      inputs.set(f.name, input);
      box.append(h("label", { class: "structures-field" }, h("span", {}, f.label), input));
    }
    foot.append(button("Cancel", () => close()), button(title, () => {
      const values: Record<string, string> = {};
      for (const [k, v] of inputs) values[k] = v.value;
      close();
      run(values);
    }, { class: "primary" }));
    (box.querySelector("input, select") as HTMLElement | null)?.focus();
  };

  const parseValue = (text: string): Value => {
    try {
      return JSON.parse(text) as Value;
    } catch {
      return text;
    }
  };

  const nodeActions = (): HTMLElement => {
    const where = pathText(selected);
    const node = doc?.value === undefined ? undefined : nodeAt(doc.value, selected);
    const kind = node === undefined ? "" : kindOf(node);
    const bar = h("div", { class: "structures-node-actions", role: "toolbar", "aria-label": "The selected node" });
    const fields = isRecords(node) ? [...new Set((node as Record<string, Value>[]).slice(0, 50).flatMap((r) => Object.keys(r)))] : [];
    bar.append(h("code", { class: "structures-path", title: "Its path" }, where), button("Copy path", () => void navigator.clipboard.writeText(where).then(() => toast(`Copied ${where}`)), { icon: "copy", iconOnly: true, class: "ghost" }));
    if (!doc || doc.error) return bar;
    if (selected.length) bar.append(button("Pick", () => void step({ op: "pick", path: where }), { icon: "zoom", title: "The tree becomes this branch" }));
    if (kind === "list") {
      bar.append(
        button("Filter…", () => ask("Filter", [{ name: "field", label: "Field", value: fields[0] ?? "" }, { name: "test", label: "Test", value: "=", options: ["=", "!=", ">", ">=", "<", "<=", "contains", "starts with", "exists", "missing"] }, { name: "value", label: "Value" }], (v) => void step({ op: "filter", path: where, field: v.field, test: v.test, value: v.value })), { icon: "filter" }),
        button("Sort…", () => ask("Sort", [{ name: "field", label: "Field", value: fields[0] ?? "" }, { name: "order", label: "Order", value: "Smallest first", options: ["Smallest first", "Largest first"] }], (v) => void step({ op: "sort", path: where, field: v.field, descending: v.order === "Largest first" })), { icon: "sortup" }),
      );
      if (isRecords(node)) bar.append(button("Flatten", () => void step({ op: "flatten", path: where }), { icon: "rows", title: "Nested objects as dotted keys" }));
      if (isRecords(node) || (Array.isArray(node) && node.length)) {
        bar.append(button("Open as grid", busyClick("Opening…", () => act("/grid", "POST", { path: where }).then(() => toast("Opened as a grid"))), { icon: "grids", class: "structures-to-grid" }));
        // Its records as a sandbox variant (its own designation, the structure as its origin; never written back).
        if (isRecords(node)) bar.append(button("Make a sandbox variant", () => makeVariant("structure", doc!.name, undefined, where), { icon: "branch", class: "structures-to-sandbox" }));
      }
      if (doc.origin.kind === "api" && doc.origin.api && doc.origin.operation) {
        bar.append(button("Return as table…", () => void returnAsTable(where), { icon: "table", title: "Save its web call with Return as table on (its API's table in SQL)" }));
      }
    }
    if (kind === "object") {
      bar.append(
        button("Add key…", () => ask("Add key", [{ name: "key", label: "Key" }, { name: "value", label: "Value", value: '""' }], (v) => void step({ op: "add", path: where, key: v.key, value: parseValue(v.value ?? "") })), { icon: "plus" }),
      );
    }
    if (selected.length) {
      const last = selected[selected.length - 1];
      if (typeof last === "string") bar.append(button("Rename key…", () => ask("Rename key", [{ name: "to", label: "New name", value: last }], (v) => void step({ op: "rename", path: pathText(selected.slice(0, -1)), key: last, to: v.to })), { icon: "rename" }));
      if (kind !== "object" && kind !== "list") bar.append(button("Set value…", () => ask("Set value", [{ name: "value", label: "Value (JSON)", value: JSON.stringify(node) }], (v) => void step({ op: "set", path: where, value: parseValue(v.value ?? "") })), { icon: "edit" }));
      bar.append(button("Remove", () => void step({ op: "remove", path: where }), { icon: "trash" }));
    }
    return bar;
  };

  const returnAsTable = async (at: string): Promise<void> => {
    if (!doc || !doc.origin.api || !doc.origin.operation) return;
    const where = `/apis/${encodeURIComponent(doc.origin.api)}/calls/${encodeURIComponent(doc.origin.operation)}`;
    const saved = await call<{ sql_name: string | null; web_call: { records: string; conversion: string } }>(where, "PUT", { as_table: true, structure: doc.id, at });
    if (!saved?.sql_name) return;
    // What it became: its name in DuckDB SQL, and DuckDB's own query over the answer (the user's to change).
    const { dialog, body: box, foot, close } = openDialog(`Return as table · ${saved.sql_name}`, true);
    dialog.classList.add("structures-as-table");
    const sql = h("textarea", { class: "mono api-conversion-sql", "aria-label": "The DuckDB query", rows: 8, spellcheck: "false" }) as HTMLTextAreaElement;
    sql.value = saved.web_call.conversion;
    box.append(
      h("p", {}, h("code", {}, `SELECT * FROM ${saved.sql_name}`), h("span", { class: "muted" }, ` · rows at ${saved.web_call.records}`)),
      h("label", { class: "structures-field" }, h("span", {}, "The DuckDB query"), sql),
    );
    foot.append(
      button("Save the query", async () => {
        if (await call(where, "PUT", { as_table: true, conversion: sql.value })) {
          toast("Saved the query.");
          close();
        }
      }, { icon: "save", class: "primary" }),
      button("Copy name for SQL", () => void navigator.clipboard.writeText(saved.sql_name!).then(() => toast(`Copied ${saved.sql_name}`)), { icon: "copy" }),
      button("Close", close, { class: "ghost" }),
    );
  };

  const lineage = async (): Promise<void> => {
    if (!doc) return;
    const got = await call<{ mermaid: string; nodes: { kind: string; label: string; where: string }[]; origin: Record<string, unknown> }>(`/structures/${encodeURIComponent(doc.id)}/lineage`);
    if (!got) return;
    const { dialog, body: box } = openDialog(`Lineage · ${doc.name}`, true);
    dialog.classList.add("structures-lineage");
    const chart = h("div", { class: "structures-lineage-chart" });
    const list = h("ol", { class: "structures-lineage-list" }, ...got.nodes.map((n) => h("li", { "data-kind": n.kind }, h("strong", {}, n.label), n.where ? h("span", { class: "muted" }, ` · ${n.where}`) : null)));
    const sent = got.origin.kind === "api" ? h("details", { class: "structures-lineage-sent" }, h("summary", {}, "What was sent"), h("pre", { class: "mono" }, JSON.stringify({ inputs: got.origin.inputs, body: got.origin.body, at: got.origin.at }, null, 2))) : null;
    box.append(chart, list, sent ?? "");
    try {
      const m = await (import(/* external */ "/static/build/lazy/diagram.js" as string) as Promise<typeof import("./lazy/diagram")>);
      await m.drawDiagram(chart, got.mermaid, effectiveTheme().endsWith("dark"));
    } catch {
      chart.remove(); // the list says the same
    }
  };

  const drawDoc = (): void => {
    if (!doc) return;
    const current = doc;
    text?.dispose();
    text = null;
    const toolbar = h("div", { class: "structures-toolbar", role: "toolbar", "aria-label": current.name });
    const format = h("select", { class: "structures-format", "aria-label": "Format", onchange: () => void act("", "PUT", { format: format.value }) }, ...FORMATS.map((f) => h("option", { value: f, selected: f === current.format }, FORMAT_NAMES[f]))) as HTMLSelectElement;
    const views = h("div", { class: "segmented", role: "group", "aria-label": "View" }, ...[["tree", "Tree"], ["both", "Both"], ["text", "Text"]].map(([v, label]) => {
      const b = button(label!, () => {
        view = v!;
        drawDoc();
      }, { pressed: view === v });
      b.dataset.view = v;
      return b;
    }));
    const search = h("input", { type: "search", class: "structures-search", placeholder: "Search", "aria-label": "Search the tree", spellcheck: false }) as HTMLInputElement;
    search.addEventListener("input", () => tree?.search(search.value));
    toolbar.append(
      format,
      views,
      search,
      button("Undo", () => void act("/undo"), { icon: "undo", iconOnly: true }),
      button("Redo", () => void act("/redo"), { icon: "redo", iconOnly: true }),
    );
    if (current.origin.kind === "api") toolbar.append(button("Run again", () => void busy(main, `Calling ${current.origin.operation ?? current.name} again…`, act("/run-again")), { icon: "play", title: "The same call, the steps kept" }));
    toolbar.append(
      button("Lineage", () => void lineage(), { icon: "lineage" }),
      button("Save", () => void (current.path ? act("/save") : saveAs()), { icon: "save", class: current.dirty ? "primary" : "" }),
      button("Save as…", () => void saveAs(), { icon: "save" }),
    );
    const parts: Node[] = [toolbar];
    if (current.origin.kind === "api") {
      const o = current.origin;
      const status = h("span", { class: `structures-status ${o.status && o.status < 300 ? "ok" : "bad"}` }, String(o.status ?? ""));
      parts.push(
        h(
          "div",
          { class: "structures-origin" },
          icon("bolt"),
          h("span", { class: "structures-call" }, `${o.method ?? ""} ${o.path ?? ""}`),
          h("span", { class: "muted" }, `${o.api ?? ""} · ${o.operation ?? ""}`),
          status,
          h("span", { class: "muted" }, `${o.ms ?? 0} ms`),
          o.said ? errorMark(o.said) : null,
          h("details", { class: "structures-headers" }, h("summary", {}, "Headers"), h("table", {}, ...Object.entries(o.headers ?? {}).map(([k, v]) => h("tr", {}, h("th", {}, k), h("td", { class: "mono" }, v))))),
        ),
      );
    }
    parts.push(
      h(
        "div",
        { class: "structures-steps", role: "list", "aria-label": "Steps" },
        ...(current.steps.length
          ? current.steps.map((s, i) => h("span", { class: "structures-step", role: "listitem", "data-op": s.op }, h("span", {}, s.words), h("button", { type: "button", class: "structures-step-x", "aria-label": `Remove step ${i + 1}`, title: "Remove", onclick: () => void act("/steps/remove", "POST", { index: i }) }, icon("close"))))
          : [h("span", { class: "muted structures-no-steps" }, "No steps")]),
      ),
    );
    if (current.error) parts.push(errorNote(current.error));
    const value = current.value ?? null;
    const split = h("div", { class: `structures-split view-${view}` });
    if (view !== "text") {
      tree = mountTree(value, {
        depth: current.nodes > 5000 ? 1 : 2,
        label: current.name,
        onSelect: (p) => {
          selected = p;
          actionsSlot.replaceChildren(nodeActions());
        },
        onSet: (p, v) => void step({ op: "set", path: pathText(p), value: v }),
        onRename: (p, key, to) => void step({ op: "rename", path: pathText(p), key, to }),
      });
      if (wantedAt && nodeAt(value, wantedAt) !== undefined) {
        selected = wantedAt;
        wantedAt = null;
      }
      if (selected.length && nodeAt(value, selected) !== undefined) tree.select(selected);
      else selected = [];
      split.append(h("div", { class: "structures-pane tree-pane" }, tree.element));
    } else tree = null;
    if (view !== "tree") {
      let timer = 0;
      // With steps the text view shows their result, read-only (as this page always did); with none it is the
      // file's own text, kept as typed (2026-11-22), its error at its line.
      text = mountText((current.steps.length ? current.result_text : current.text) ?? "", current.format, (t) => {
        window.clearTimeout(timer);
        timer = window.setTimeout(async () => {
          try {
            const done = await api<Shown>(`/structures/${encodeURIComponent(current.id)}`, "PUT", { text: t, view: "result" });
            text?.setError(done.text_error ?? null);
            if (done.text_error) return;
            doc = { ...done, text: t };
            tree?.set(done.value ?? null);
            void refreshTabs();
          } catch (e) {
            text?.setError((e as Error).message);
          }
        }, 500);
      }, `${current.name} as ${FORMAT_NAMES[current.format]}`);
      text.setReadOnly(current.steps.length > 0);
      if (current.text_error) text.setError(current.text_error);
      split.append(h("div", { class: "structures-pane text-pane" }, text.element));
    }
    const actionsSlot = h("div", { class: "structures-actions-slot" });
    actionsSlot.append(nodeActions());
    parts.push(actionsSlot, split);
    main.replaceChildren(...parts);
  };

  const saveAs = async (): Promise<void> => {
    if (!doc) return;
    const current = doc;
    ask("Save as", [{ name: "name", label: "Name", value: current.name }, { name: "format", label: "Format", value: current.format, options: [...FORMATS] }], (v) => {
      void call<Summary & { written: string }>(`/structures/${encodeURIComponent(current.id)}/save-as`, "POST", { name: v.name, format: v.format }).then(async (done) => {
        if (done) {
          toast(`Saved ${done.written}`);
          await load();
        }
      });
    });
  };

  watchLayerDialog(element, "structures", [], () => {
    if (shownPage === element) shownPage = null;
    reload = null;
    text?.dispose();
  });
  main.append(loadingBlock(`Loading ${STRUCTURES.toLowerCase()}…`));
  void load();
}
