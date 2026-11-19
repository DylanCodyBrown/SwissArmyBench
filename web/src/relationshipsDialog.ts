/**
 * relationshipsDialog.ts: the Relationships window: saved sets, the finder, and the joins in use. [WIRE + EXPORT]
 *
 * A **relationship set** is a saved set of relationships, kept as a .relationships.json file (a "tang"
 * until the owner's call, 2026-11-17: "drop tang its cheesy"). Sets are shared like blades: the blade
 * folders (a team share or a repository) are searched for them, so a set one person saves there is in a
 * coworker's list the next time this window opens.
 *
 *   SAVED SETS  every set found (the person's own and the shared ones): search, apply, check against the
 *               open tables, and from its menu rename, export, delete (not a pack's or a built-in one)
 *   FIND        the relationship finder: how the open tables join, worked out from the data, each
 *               suggestion with its evidence; tick and accept, or reject
 *   IN USE NOW  the joins in use, managed (the owner, 2026-11-17: "I cant mass delete anything or manage
 *               those at all and they dont fit in the window"): a checkbox per row, select all (of the
 *               filtered rows), shift-click ranges, the count; Delete selected and Run on/off for the
 *               selection; a filter (table or column), sort by any column, group by From table; a row's
 *               Kind and Run changed in place, its own menu. Every change has one Undo (the toast's).
 *               It fits the window down to 700px: fixed columns, long names cut with their tooltip.
 *
 * ROUTING: [APPLY / CHECK a set]    -> POST /relationships/library/{name} / POST /relationships/check
 *          [RENAME / DELETE / EXPORT a set] -> PATCH / DELETE / GET /relationships/sets/{name}
 *          [IMPORT]                 -> POST /relationships/import (review, then apply)
 *          [EXPORT]                 -> GET /relationships/set (a .relationships.json download)
 *          [SAVE AS A SET]          -> POST /relationships/sets
 *          [DELETE / KIND / RUN]    -> POST /relationships/delete, /relationships/update; [UNDO] /relationships/undo
 *          [FIND]                   -> POST /relationships/find; [ACCEPT] -> POST /relationships; [REJECT] -> /reject
 *          [DRAW DIAGRAM]           -> a diagram card in Visualizations
 * The agent's: relationships_delete, _update, _undo, _save_set, _export_set, _rename_set, _delete_set.
 */
import { api, download, grid } from "./api";
import { append, button, clear, h, icon, openDialog, showMenu, toast, type MenuItem } from "./dom";
import { showAgentView } from "./panes";
import { saveBlob } from "./profileView";
import { currentModel, loadRelationships, projectScope, scopeSwitch, type Join, type RelationshipScope } from "./relationships";
import { busyClick, loadingBlock } from "./loading";
import { errorHere, errorNote } from "./errorNote";

interface SavedSet {
  name: string;
  description: string;
  tags: string[];
  saved_at: string;
  author: string;
  file: string;
  where: "mine" | "shared" | "package" | "environment" | "pack";
  set: boolean;
  tables: string[];
  open_tables: string[];
  relationships: number;
}

interface Library {
  models: SavedSet[];
  folders: string[];
  shared_folders: string[];
  problems: string[];
}

interface Suggestion extends Join {
  confidence: number;
  containment: number;
  coverage: number;
  orphans: number;
  reasons: string[];
  known: boolean;
}

interface RunResult extends Join {
  status: "holds" | "orphans" | "broken" | "not open";
  detail: string;
  match?: number;
  orphan_samples?: unknown[];
  actual_kind?: string;
  notes?: string[];
}

const KINDS = ["many-to-one", "one-to-one", "one-to-many", "many-to-many"];
const WHERE: Record<SavedSet["where"], string> = { mine: "Mine", shared: "Shared", package: "Built in", environment: "Folder", pack: "Pack" };
// Where a saved set can be renamed or deleted here (a pack's changes in its repository).
const EDITABLE: SavedSet["where"][] = ["mine", "shared"];
const STATUS: Record<RunResult["status"], [string, string]> = {
  holds: ["check", "Holds"],
  orphans: ["filter", "Holds, with orphans"],
  broken: ["close", "Broken"],
  "not open": ["minus", "Not open"],
};

function on(r: Join): string {
  return r.from_columns.map((c, i) => (c === r.to_columns[i] ? c : `${c} = ${r.to_columns[i]}`)).join(", ");
}

/** A join's name: its two ends and their columns (what the server deletes and changes it by). */
function keyOf(r: Join): string {
  return JSON.stringify([r.from, r.from_columns, r.to, r.to_columns]);
}

function ends(r: Join): Pick<Join, "from" | "from_columns" | "to" | "to_columns"> {
  return { from: r.from, from_columns: r.from_columns, to: r.to, to_columns: r.to_columns };
}

const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? "" : "s"}`;

function when(iso: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** A table cell that never widens its column: the text cut with an ellipsis, all of it in the tooltip. */
function cut(text: string, cls = ""): HTMLTableCellElement {
  // Cut in the middle: forty foreign keys share their first words and differ at the end (…entry_line_07),
  // so the end always shows and the start gives way.
  const tail = text.length > 18 ? text.slice(-8) : "";
  return h(
    "td",
    { class: `rel-cut ${cls}`.trim(), title: text },
    h("span", { class: "rel-mid" }, h("span", { class: "rel-head" }, tail ? text.slice(0, -8) : text), tail ? h("span", { class: "rel-tail" }, tail) : null),
  ) as HTMLTableCellElement;
}

/** Import relationships (one name, wherever it is offered: this window's footer and the ERD tab). The
 * file is a relationship set (a .relationships.json, or an older .tang: reviewed first, what it would
 * change, then applied, kept or shared) or a relationship model as JSON (applied as it is). `after`: once
 * something was applied. */
export async function importRelationships(picked: File, after: () => Promise<void> = async () => {}): Promise<void> {
  const text = await picked.text();
  // A model as JSON ({"tables", "relationships"}): merged into the joins in use, as before.
  let model: unknown;
  try {
    model = JSON.parse(text);
  } catch {
    model = undefined;
  }
  // A saved set is JSON too, marked "swissarmybench" ("swissarmygrid" before the first rename): reviewed below.
  if (model && typeof model === "object" && !Array.isArray(model) && !("swissarmybench" in model) && !("swissarmygrid" in model)) {
    try {
      await api("/relationships", "POST", { model });
      await after();
    } catch (e) {
      errorHere(`Could not import ${picked.name}: ${(e as Error).message}`);
    }
    return;
  }
  let review: { set: { name: string; description: string; tags?: string[]; author?: string; relationships: Join[] }; open_tables: string[]; missing_tables: string[]; changes: string[] };
  let shared: string[] = [];
  try {
    review = await api("/relationships/import", "POST", { text });
    shared = (await api<Library>("/relationships/library")).shared_folders;
  } catch (e) {
    errorHere(`${picked.name}: ${(e as Error).message}`);
    return;
  }
  const t = review.set;
  const { body: rb, foot: rf, close: rc } = openDialog(`Import ${t.name}`);
  const where = h("select", { "aria-label": "Keep it in" }, h("option", { value: "" }, "Just apply it"), h("option", { value: "mine" }, "Apply and keep it in my saved sets"), ...shared.map((f) => h("option", { value: f }, `Apply and share it: ${f}`)));
  append(
    rb,
    t.description ? h("p", {}, t.description) : null,
    t.tags?.length ? h("div", { class: "chips" }, ...t.tags.map((g) => h("span", { class: "chip" }, g))) : null,
    h("p", { class: "hint" }, `${t.relationships.length} joins${t.author ? `, saved by ${t.author}` : ""}. Tables open: ${review.open_tables.join(", ") || "none"}${review.missing_tables.length ? `; not open: ${review.missing_tables.join(", ")}` : ""}.`),
    review.changes.length ? h("div", { class: "warning-text" }, h("strong", {}, "It changes what you use now: "), h("ul", {}, ...review.changes.map((c) => h("li", {}, c)))) : h("p", { class: "hint" }, "Only adds; changes nothing."),
    h("ul", { class: "hint" }, ...t.relationships.slice(0, 30).map((r) => h("li", {}, `${r.from} → ${r.to} on ${on(r)} (${r.kind})`))),
    h("label", { class: "field" }, h("span", {}, "Then"), where),
  );
  rf.append(
    button("Cancel", rc, { class: "ghost" }),
    button("Apply", () => {
      const save = where.value !== "";
      void api<{ where?: string }>("/relationships/import", "POST", { text, apply: true, save, folder: save && where.value !== "mine" ? where.value : null }).then(async (a) => {
        rc();
        toast(`Applied ${t.name}${a.where ? ` and kept it (${a.where === "shared" ? "shared" : "yours"})` : ""}.`);
        await after();
      }, (e: Error) => errorHere(e));
    }, { class: "primary", icon: "check" }),
  );
}

type SortKey = "from" | "to" | "on" | "kind" | "run" | "check";
const COLUMNS: [SortKey | null, string, string][] = [
  [null, "", "rel-col-pick"],
  ["from", "From", "rel-col-from"],
  ["to", "To", "rel-col-to"],
  ["on", "On", "rel-col-on"],
  ["kind", "Kind", "rel-col-kind"],
  ["run", "Run", "rel-col-run"],
  ["check", "Check", "rel-col-check"],
  [null, "Note", "rel-col-note"],
  [null, "", "rel-col-menu"],
];

/** The Relationships window; `startFinding` runs the finder at once (the empty ERD tab's button). */
export function openRelationships(startFinding = false): void {
  const { dialog, body, foot, close } = openDialog("Relationships", true);
  dialog.classList.add("rel-dialog");
  foot.classList.add("rel-foot");
  const setsHost = h("section", { class: "rel-section", "aria-labelledby": "rel-sets" });
  const findHost = h("section", { class: "rel-section", "aria-labelledby": "rel-find" });
  const currentHost = h("section", { class: "rel-section rel-current", "aria-labelledby": "rel-current" });
  let library: Library = { models: [], folders: [], shared_folders: [], problems: [] };
  let setFilter = "";
  let runs: RunResult[] | null = null;
  // The joins in use, as this window manages them.
  const selected = new Set<string>();
  let anchor: string | null = null; // the last row clicked, for a shift-click range
  let filter = "";
  let sort: { key: SortKey; down: boolean } | null = null;
  let grouped = false;
  let shown: Join[] = []; // the rows drawn, in their order (select all and ranges use it)
  // With a project open, the joins whose two tables it uses (by default) or all of them.
  let scope: RelationshipScope | null = null;
  let showAll = false;

  body.append(setsHost, findHost, currentHost);
  const file = h("input", { type: "file", accept: ".json,.tang,application/json", hidden: true, onchange: () => void importFile() }) as HTMLInputElement;
  foot.append(
    file,
    button("Import relationships", () => file.click(), { icon: "import", title: "A saved set (reviewed before it is applied) or a model as JSON" }),
    button("Export", () => void exportCurrent(), { icon: "export", title: "Download as .relationships.json" }),
    button("Save as a set…", () => saveDialog(), { icon: "save" }),
    button("Draw diagram", () => void drawErd(close), { icon: "link", title: "To Visualizations" }),
    button("Close", close, { class: "primary" }),
  );

  // ===== SAVED SETS =====
  async function loadLibrary(): Promise<void> {
    try {
      library = await api<Library>("/relationships/library");
    } catch (e) {
      errorHere(e);
    }
    renderSets();
  }

  function setMenu(t: SavedSet, at: HTMLElement): void {
    const box = at.getBoundingClientRect();
    const locked = EDITABLE.includes(t.where) ? undefined : t.where === "pack" ? "A pack's set changes in its repository" : "Read-only here";
    const items: MenuItem[] = [
      ["rename", "Rename…", () => renameSet(t), locked],
      ["export", "Export", () => void exportSaved(t.name)],
      "-",
      ["trash", "Delete", () => void deleteSet(t), locked],
    ];
    showMenu(box.left, box.bottom, `${t.name}`, items);
  }

  function renderSets(): void {
    const text = setFilter.toLowerCase();
    const listed = library.models.filter((t) => !text || [t.name, t.description, t.author, ...t.tags].some((f) => f.toLowerCase().includes(text)));
    const search = h("input", { type: "search", class: "cat-search", placeholder: "Search", "aria-label": "Search saved sets", value: setFilter });
    search.addEventListener("input", () => {
      setFilter = search.value;
      const at = search.selectionStart;
      renderSets();
      const again = setsHost.querySelector<HTMLInputElement>("input[type=search]");
      again?.focus();
      if (at !== null) again?.setSelectionRange(at, at);
    });
    clear(
      setsHost,
      h("h3", { id: "rel-sets" }, "Saved sets"),
      library.models.length ? search : null,
      listed.length
        ? h(
            "ul",
            { class: "set-list" },
            ...listed.map((t) =>
              h(
                "li",
                { class: "set-item", "data-name": t.name },
                h(
                  "div",
                  { class: "set-text" },
                  h("div", { class: "pack-title" }, h("strong", {}, t.name), h("span", { class: `badge set-where ${t.where}`, title: t.file }, WHERE[t.where])),
                  t.description ? h("div", { class: "hint" }, t.description) : null,
                  t.tags.length ? h("div", { class: "chips" }, ...t.tags.map((g) => h("span", { class: "chip" }, g))) : null,
                  h(
                    "div",
                    { class: "hint" },
                    `${plural(t.relationships, "join")} · ${t.open_tables.length} of ${t.tables.length} tables open`,
                    t.saved_at ? ` · saved ${when(t.saved_at)}` : "",
                    t.author ? ` by ${t.author}` : "",
                  ),
                ),
                h(
                  "span",
                  { class: "row-actions" },
                  button("Check", busyClick("Checking…", () => run(t.name)), { icon: "play", class: "ghost", title: "Check against the open tables" }),
                  button("Apply", () => void apply(t.name), { class: "primary", title: "Merge into the joins in use" }),
                  button(`More for ${t.name}`, (e) => setMenu(t, e.currentTarget as HTMLElement), { icon: "more", iconOnly: true, class: "ghost", title: "Rename, export, delete" }),
                ),
              ),
            ),
          )
        : h("p", { class: "hint" }, library.models.length ? "No saved set matches." : "No saved sets yet."),
      library.problems.length ? errorNote(`Could not read: ${library.problems.join("; ")}`) : null,
      library.shared_folders.length ? h("p", { class: "hint" }, `Shared folders: ${library.shared_folders.join(" · ")}`) : null,
    );
  }

  async function apply(name: string): Promise<void> {
    try {
      const answer = await api<{ changed: string[] }>(`/relationships/library/${encodeURIComponent(name)}`, "POST");
      toast(answer.changed.length ? `Applied ${name}; it changed: ${answer.changed.join("; ")}.` : `Applied ${name}.`, "info", { label: "Undo", run: () => void undo() });
      await renderCurrent();
    } catch (e) {
      errorHere(e);
    }
  }

  function renameSet(t: SavedSet): void {
    const { body: rb, foot: rf, close: rc } = openDialog(`Rename ${t.name}`);
    const name = h("input", { type: "text", value: t.name, maxlength: "64", "aria-label": "New name" }) as HTMLInputElement;
    rb.append(h("label", { class: "field" }, h("span", {}, "Name"), name));
    const go = (): void => {
      void api(`/relationships/sets/${encodeURIComponent(t.name)}`, "PATCH", { name: name.value.trim() }).then(async () => {
        rc();
        toast(`Renamed to ${name.value.trim()}.`);
        await loadLibrary();
      }, (e: Error) => errorHere(e));
    };
    name.addEventListener("keydown", (e) => {
      if (e.key === "Enter") go();
    });
    rf.append(button("Cancel", rc, { class: "ghost" }), button("Rename", go, { class: "primary", icon: "rename" }));
    name.select();
  }

  async function deleteSet(t: SavedSet): Promise<void> {
    if (!confirm(`Delete the saved set ${t.name}? Its file goes.`)) return;
    try {
      await api(`/relationships/sets/${encodeURIComponent(t.name)}`, "DELETE");
      toast(`Deleted ${t.name}.`);
      await loadLibrary();
    } catch (e) {
      errorHere(e);
    }
  }

  async function exportSaved(name: string): Promise<void> {
    try {
      const got = await download(`/relationships/sets/${encodeURIComponent(name)}`);
      saveBlob(got.blob, got.name);
    } catch (e) {
      errorHere(e);
    }
  }

  async function run(name?: string): Promise<void> {
    try {
      const answer = await api<{ set: string; results: RunResult[] }>("/relationships/check", "POST", name ? { set: name } : {});
      if (name) showRunDialog(answer.set, answer.results);
      else {
        runs = answer.results;
        drawCurrent();
      }
    } catch (e) {
      errorHere(e);
    }
  }

  // ===== FIND =====
  function renderFindStart(): void {
    clear(
      findHost,
      h("h3", { id: "rel-find" }, "Find relationships"),
      button("Find relationships", () => void find(), { icon: "zoom", class: "primary" }),
    );
  }

  async function find(): Promise<void> {
    clear(findHost, h("h3", { id: "rel-find" }, "Find relationships"), loadingBlock("Looking for relationships among the open tables…"));
    let found: { tables: string[]; suggestions: Suggestion[]; keys: Record<string, string[]>; seconds: number };
    try {
      found = await api("/relationships/find", "POST", {});
    } catch (e) {
      renderFindStart();
      errorHere(e);
      return;
    }
    const picked = new Set(found.suggestions.filter((s) => !s.known && s.confidence >= 0.8).map((_, i) => i));
    const rows = found.suggestions.map((s, i) => {
      const box = h("input", { type: "checkbox", checked: picked.has(found.suggestions.indexOf(s)) && !s.known, disabled: s.known, "aria-label": `Accept ${s.from} to ${s.to}` }) as HTMLInputElement;
      box.addEventListener("change", () => (box.checked ? picked.add(i) : picked.delete(i)));
      return h(
        "li",
        { class: `suggestion ${s.known ? "known" : ""}` },
        box,
        h(
          "div",
          { class: "set-text" },
          h(
            "div",
            {},
            h("strong", {}, s.from),
            " → ",
            h("strong", {}, s.to),
            h("span", { class: "hint" }, ` on ${on(s)} · ${s.kind}`),
            s.active === false ? h("span", { class: "badge" }, "inactive") : null,
            s.known ? h("span", { class: "badge" }, icon("crown"), "in use") : null,
          ),
          h("div", { class: "confidence", title: `Confidence ${Math.round(s.confidence * 100)}%` }, h("span", { style: { "--share": `${Math.round(s.confidence * 100)}%` } })),
          h("details", {}, h("summary", {}, s.evidence ?? "Why"), h("ul", { class: "hint" }, ...s.reasons.map((r) => h("li", {}, r)))),
        ),
        s.known
          ? null
          : button("Reject", () => {
              void api("/relationships/reject", "POST", { from: s.from, from_columns: s.from_columns, to: s.to, to_columns: s.to_columns }).then(() => void find());
            }, { icon: "close", iconOnly: true, class: "ghost", title: "Do not suggest again" }),
      );
    });
    clear(
      findHost,
      h("h3", { id: "rel-find" }, "Find relationships"),
      h("p", { class: "hint" }, `${found.suggestions.length} joins across ${found.tables.length} tables (${found.seconds} seconds).`),
      found.suggestions.length ? h("ul", { class: "suggestion-list" }, ...rows) : h("p", { class: "hint" }, "No joins found."),
      h(
        "div",
        { class: "row-actions" },
        button("Accept the ticked joins", () => void accept(found, picked), { class: "primary", icon: "check" }),
        button("Find again", () => void find(), { class: "ghost" }),
      ),
    );
  }

  async function accept(found: { suggestions: Suggestion[]; keys: Record<string, string[]> }, picked: Set<number>): Promise<void> {
    const chosen = found.suggestions.filter((_, i) => picked.has(i));
    if (!chosen.length) return errorHere("No joins ticked.");
    const tables: Record<string, { primary_key: string[] }> = {};
    for (const s of chosen) if (found.keys[s.to]) tables[s.to] = { primary_key: found.keys[s.to]! };
    const relationships = chosen.map(({ confidence: _c, containment: _a, coverage: _v, orphans: _o, reasons: _r, known: _k, ...join }) => join);
    try {
      await api("/relationships", "POST", { model: { tables, relationships } });
      toast(`Accepted ${chosen.length} joins.`);
      await renderCurrent();
      await find();
    } catch (e) {
      errorHere(e);
    }
  }

  // ===== IN USE NOW: the joins in use, managed =====
  const result = (r: Join): RunResult | undefined =>
    runs?.find((x) => x.from === r.from && x.to === r.to && x.from_columns.join() === r.from_columns.join() && x.to_columns.join() === r.to_columns.join());

  function sortValue(r: Join, key: SortKey): string {
    if (key === "on") return on(r);
    if (key === "run") return r.active === false ? "1" : "0";
    if (key === "check") return String(["holds", "orphans", "broken", "not open"].indexOf(result(r)?.status ?? "") + 1);
    return String(r[key]);
  }

  /** The rows to draw: filtered by table or column, sorted, grouped by From table. */
  function visible(all: Join[]): Join[] {
    const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
    const used = scope?.project && !showAll ? new Set(scope.tables) : null;
    let rows = all.filter((r) => {
      if (used && !(used.has(r.from) && used.has(r.to))) return false;
      const text = [r.from, r.to, ...r.from_columns, ...r.to_columns].join(" ").toLowerCase();
      return words.every((w) => text.includes(w));
    });
    const compare = (a: Join, b: Join): number => {
      if (grouped) {
        const g = a.from.localeCompare(b.from);
        if (g) return sort?.key === "from" && sort.down ? -g : g;
      }
      if (!sort) return 0;
      const c = sortValue(a, sort.key).localeCompare(sortValue(b, sort.key), undefined, { numeric: true });
      return sort.down ? -c : c;
    };
    rows = rows.map((r, i) => [r, i] as const).sort((a, b) => compare(a[0], b[0]) || a[1] - b[1]).map(([r]) => r);
    return rows;
  }

  async function renderCurrent(): Promise<void> {
    await loadRelationships();
    scope = await projectScope();
    // Rows that are gone are no longer selected.
    const now = new Set(currentModel().relationships.map(keyOf));
    for (const k of [...selected]) if (!now.has(k)) selected.delete(k);
    drawCurrent();
  }

  async function change(joins: Join[], what: { kind?: string; active?: boolean }, words: string): Promise<void> {
    try {
      const answer = await api<{ changed: number }>("/relationships/update", "POST", { joins: joins.map(ends), ...what });
      await renderCurrent();
      if (answer.changed) toast(`${words}: ${plural(answer.changed, "relationship")}.`, "info", { label: "Undo", run: () => void undo() });
    } catch (e) {
      errorHere(e);
    }
  }

  async function remove(joins: Join[]): Promise<void> {
    if (!joins.length) return;
    try {
      const answer = await api<{ removed: number }>("/relationships/delete", "POST", { joins: joins.map(ends) });
      for (const j of joins) selected.delete(keyOf(j));
      await renderCurrent();
      toast(`Deleted ${plural(answer.removed, "relationship")}.`, "info", { label: "Undo", run: () => void undo() });
    } catch (e) {
      errorHere(e);
    }
  }

  async function undo(): Promise<void> {
    try {
      await api("/relationships/undo", "POST");
      await renderCurrent();
      toast("Undone.");
    } catch (e) {
      errorHere(e);
    }
  }

  function pick(r: Join, box: HTMLInputElement, shift: boolean): void {
    const key = keyOf(r);
    if (shift && anchor !== null) {
      const keys = shown.map(keyOf);
      const [a = -1, b = -1] = [keys.indexOf(anchor), keys.indexOf(key)].sort((x, y) => x - y);
      if (a >= 0 && b >= 0) for (const k of keys.slice(a, b + 1)) box.checked ? selected.add(k) : selected.delete(k);
    } else if (box.checked) selected.add(key);
    else selected.delete(key);
    anchor = key;
    drawCurrent();
  }

  function rowMenu(r: Join, at: HTMLElement): void {
    const box = at.getBoundingClientRect();
    showMenu(box.left, box.bottom, `${r.from} → ${r.to}`, [
      [r.active === false ? "play" : "stop", r.active === false ? "Run on" : "Run off", () => void change([r], { active: r.active === false }, r.active === false ? "Run on" : "Run off")],
      "-",
      ["trash", "Delete", () => void remove([r])],
    ]);
  }

  function header(): HTMLElement {
    const all = shown.length > 0 && shown.every((r) => selected.has(keyOf(r)));
    const some = shown.some((r) => selected.has(keyOf(r)));
    const head = h("input", { type: "checkbox", checked: all, "aria-label": "Select all" }) as HTMLInputElement;
    head.indeterminate = some && !all;
    head.addEventListener("change", () => {
      for (const r of shown) head.checked ? selected.add(keyOf(r)) : selected.delete(keyOf(r));
      drawCurrent();
    });
    return h(
      "thead",
      {},
      h(
        "tr",
        {},
        ...COLUMNS.map(([key, label, cls]) => {
          if (cls === "rel-col-pick") return h("th", { scope: "col", class: cls }, head);
          if (!key) return h("th", { scope: "col", class: cls }, label);
          const active = sort?.key === key;
          return h(
            "th",
            { scope: "col", class: cls, "aria-sort": active ? (sort!.down ? "descending" : "ascending") : "none" },
            h(
              "button",
              {
                type: "button",
                class: "rel-sort",
                title: `Sort by ${label}`,
                onclick: () => {
                  sort = active ? (sort!.down ? null : { key, down: true }) : { key, down: false };
                  drawCurrent();
                },
              },
              label,
              active ? icon(sort!.down ? "sortdown" : "sortup") : null,
            ),
          );
        }),
      ),
    );
  }

  function row(r: Join): HTMLElement {
    const ran = result(r);
    const key = keyOf(r);
    const box = h("input", { type: "checkbox", checked: selected.has(key), "aria-label": `Select ${r.from} to ${r.to}` }) as HTMLInputElement;
    box.addEventListener("click", (e) => pick(r, box, e.shiftKey));
    const kind = h("select", { class: "rel-kind", "aria-label": `Kind of ${r.from} to ${r.to}` }, ...KINDS.map((k) => h("option", { value: k, selected: k === r.kind }, k))) as HTMLSelectElement;
    kind.addEventListener("change", () => void change([r], { kind: kind.value }, `Kind ${kind.value}`));
    const use = h("input", { type: "checkbox", class: "rel-run-switch", role: "switch", checked: r.active !== false, "aria-label": `Run ${r.from} to ${r.to}`, title: r.active === false ? "Off: kept but not used" : "On: used" }) as HTMLInputElement;
    use.addEventListener("change", () => void change([r], { active: use.checked }, use.checked ? "Run on" : "Run off"));
    const note = ran && ran.status !== "holds" ? ran.detail : r.note ?? "";
    return h(
      "tr",
      { class: `${ran ? `run-${ran.status.replace(" ", "-")}` : ""} ${selected.has(key) ? "selected" : ""} ${r.active === false ? "rel-off" : ""}`.trim(), "data-key": key },
      h("td", { class: "rel-col-pick" }, box),
      cut(r.from, "rel-col-from"),
      cut(r.to, "rel-col-to"),
      cut(on(r), "rel-col-on"),
      h("td", { class: "rel-col-kind" }, kind),
      h("td", { class: "rel-col-run" }, use),
      h("td", { class: "rel-cut rel-col-check", title: ran?.detail ?? "Not checked yet" }, ...(ran ? [icon(STATUS[ran.status][0]), h("span", { class: "rel-check-word" }, ` ${STATUS[ran.status][1]}`)] : ["—"])),
      cut(note, "rel-col-note hint"),
      h("td", { class: "rel-col-menu" }, button(`More for ${r.from} to ${r.to}`, (e) => rowMenu(r, e.currentTarget as HTMLElement), { icon: "more", iconOnly: true, class: "ghost" })),
    );
  }

  function drawCurrent(): void {
    const model = currentModel();
    const keys = Object.entries(model.tables).filter(([, t]) => t.primary_key?.length);
    shown = visible(model.relationships);
    const picked = model.relationships.filter((r) => selected.has(keyOf(r)));
    const focused = document.activeElement instanceof HTMLInputElement && document.activeElement.classList.contains("rel-filter");
    const search = h("input", { type: "search", class: "cat-search rel-filter", placeholder: "Filter by table or column", "aria-label": "Filter relationships", value: filter }) as HTMLInputElement;
    search.addEventListener("input", () => {
      filter = search.value;
      drawCurrent();
    });
    const rows: HTMLElement[] = [];
    let group = "";
    for (const r of shown) {
      if (grouped && r.from !== group) {
        group = r.from;
        const count = shown.filter((x) => x.from === group).length;
        rows.push(h("tr", { class: "rel-group" }, h("th", { colspan: String(COLUMNS.length), scope: "rowgroup", title: group }, group, h("span", { class: "hint" }, ` · ${count}`))));
      }
      rows.push(row(r));
    }
    clear(
      currentHost,
      h("h3", { id: "rel-current" }, "In use now", model.name !== "current" ? h("span", { class: "hint rel-model-name", title: model.name }, ` (${model.name})`) : null),
      model.relationships.length
        ? h(
            "div",
            { class: "rel-tools", role: "toolbar", "aria-label": "Relationships in use" },
            search,
            button("Group by From table", () => {
              grouped = !grouped;
              drawCurrent();
            }, { icon: "group", class: "ghost", pressed: grouped }),
            h("span", { class: "rel-count", role: "status" }, picked.length ? `${picked.length} selected` : `${shown.length} of ${model.relationships.length}`),
            button("Run on", () => void change(picked, { active: true }, "Run on"), { icon: "play", class: "ghost", title: "Use the selected joins" }),
            button("Run off", () => void change(picked, { active: false }, "Run off"), { icon: "stop", class: "ghost", title: "Keep the selected joins but do not use them" }),
            button("Delete selected", () => void remove(picked), { icon: "trash", class: "danger" }),
          )
        : null,
      model.relationships.length && scope?.project
        ? h(
            "div",
            { class: "rel-scope" },
            scopeSwitch(showAll, (all) => {
              showAll = all;
              drawCurrent();
            }),
            scope.words ? h("span", { class: "hint rel-hidden", title: scope.words }, scope.words) : null,
          )
        : null,
      model.relationships.length
        ? h("div", { class: "rel-scroll" }, h("table", { class: "small rel-table" }, header(), h("tbody", {}, ...rows)))
        : h("p", { class: "hint" }, "No joins in use yet."),
      keys.length ? h("p", { class: "hint rel-keys" }, "Keys: ", ...keys.map(([t, spec], i) => [i ? " · " : "", h("strong", {}, t), ` (${(spec.primary_key ?? []).join(", ")})`]).flat()) : null,
      model.relationships.length ? h("div", { class: "row-actions" }, button("Check against the open tables", busyClick("Checking…", () => run()), { icon: "play" })) : null,
    );
    for (const b of currentHost.querySelectorAll<HTMLButtonElement>(".rel-tools > button:not([aria-pressed])")) b.disabled = !picked.length;
    if (focused) {
      search.focus();
      search.setSelectionRange(search.value.length, search.value.length);
    }
  }

  // ===== files =====
  async function importFile(): Promise<void> {
    const picked = file.files?.[0];
    file.value = "";
    if (!picked) return;
    await importRelationships(picked, async () => {
      await loadLibrary();
      await renderCurrent();
    });
  }

  async function exportCurrent(): Promise<void> {
    try {
      const got = await download("/relationships/set");
      saveBlob(got.blob, got.name);
    } catch (e) {
      errorHere(e);
    }
  }

  function saveDialog(): void {
    const model = currentModel();
    const { body: sb, foot: sf, close: sc } = openDialog("Save as a set");
    const name = h("input", { type: "text", value: model.name !== "current" ? model.name : "", maxlength: "64", "aria-label": "Set name" });
    const description = h("textarea", { rows: "2", "aria-label": "Description" }) as HTMLTextAreaElement;
    description.value = model.description ?? "";
    const tags = h("input", { type: "text", value: (model.tags ?? []).join(", "), "aria-label": "Tags", placeholder: "sales, finance" });
    const author = h("input", { type: "text", value: model.author ?? "", maxlength: "100", "aria-label": "Saved by", placeholder: "Optional" });
    const where = h("select", { "aria-label": "Save it in" }, h("option", { value: "" }, "My saved sets"), ...library.shared_folders.map((f) => h("option", { value: f }, `Shared: ${f}`)));
    sb.append(
      h("label", { class: "field" }, h("span", {}, "Name"), name),
      h("label", { class: "field" }, h("span", {}, "Description"), description),
      h("label", { class: "field" }, h("span", {}, "Tags"), tags),
      h("label", { class: "field" }, h("span", {}, "Saved by"), author),
      h("label", { class: "field" }, h("span", {}, "Save it in"), where),
    );
    sf.append(
      button("Cancel", sc, { class: "ghost" }),
      button("Save", () => {
        const payload = { name: name.value.trim(), description: description.value.trim(), tags: tags.value.split(",").map((t) => t.trim()).filter(Boolean), author: author.value.trim(), folder: where.value || null };
        void api<{ where: string; file: string }>("/relationships/sets", "POST", payload).then(async (a) => {
          sc();
          toast(`Saved ${payload.name} ${a.where === "shared" ? "in the shared folder" : "in your saved sets"}.`);
          await loadLibrary();
          await renderCurrent();
        }, (e: Error) => errorHere(e));
      }, { class: "primary", icon: "save" }),
    );
    name.focus();
  }

  void loadLibrary();
  if (startFinding) {
    void find();
    findHost.scrollIntoView({ block: "start" });
  } else renderFindStart();
  void renderCurrent();
}

/** A saved set's check, in a window of its own. */
function showRunDialog(name: string, results: RunResult[]): void {
  const { body, foot, close } = openDialog(`Check ${name}`, true);
  body.append(
    h(
      "table",
      { class: "small rel-run" },
      h("thead", {}, h("tr", {}, ...["Join", "Result", "Detail"].map((t) => h("th", { scope: "col" }, t)))),
      h(
        "tbody",
        {},
        ...results.map((r) =>
          h(
            "tr",
            { class: `run-${r.status.replace(" ", "-")}` },
            h("td", {}, `${r.from} → ${r.to} on ${on(r)}`),
            h("td", {}, icon(STATUS[r.status][0]), ` ${STATUS[r.status][1]}`),
            h(
              "td",
              {},
              r.detail,
              r.orphan_samples?.length ? h("div", { class: "hint" }, `Orphans, for example: ${r.orphan_samples.map((v) => JSON.stringify(v)).join(", ")}`) : null,
              ...(r.notes ?? []).map((n) => h("div", { class: "hint" }, n)),
            ),
          ),
        ),
      ),
    ),
  );
  foot.append(button("Close", close, { class: "primary" }));
}

async function drawErd(close: () => void): Promise<void> {
  try {
    const erd = await api<{ mermaid: string }>("/relationships/erd");
    await api(`${grid}/cards`, "POST", { kind: "diagram", title: "Relationships", body: erd.mermaid });
    close();
    showAgentView();
    toast("Diagram sent to Visualizations.");
  } catch (e) {
    errorHere(e);
  }
}
