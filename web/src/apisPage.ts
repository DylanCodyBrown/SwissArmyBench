/**
 * apisPage.ts: the APIs page, on the rail after the ERD (the owner, 2026-11-17: "move the Api feature to
 * its own rail Icon ... so I can easily browse and explore Apis that are set up and see thier input and
 * output structures"; "Apis need thier own page so they can be imported managed, refreshed when the api
 * changes and searchable"; "from the ApI page to quickly open a screen, Author an API call using an apis
 * payload, then the results will show up in the structure page retaining their lineage"). An explorer
 * of our own design. APIs are this computer's library, never a project's. [SHARED]
 *
 *   [CARDS]   one per API: its title, base address, sign-in type (never a secret), operations, tables
 *             (web calls with Return as table on), calls this session, where it was read from and when;
 *             Refresh (what changed, then Apply), Check for changes, Rename, Delete (the code that uses
 *             it first), the folder. Add API (addApi.ts) is the heading row's.
 *   [SEARCH]  one box across every API and operation: the API, the method's badge, the path, the words
 *             marked where they matched.
 *   [EXPLORE] an API's operations down the left, grouped by tag (folds), each a method badge and its
 *             path; its schemas after them. The right: the operation's description (markdown, no HTML),
 *             its inputs (a table), its body (a tree and an example), its outputs (each status: a tree
 *             and an example), Return as table's state and its SQL name (Copy name for SQL).
 *   [WRITE]   Write rows with this call (a POST, PUT, PATCH or DELETE): an open table's columns mapped onto
 *             the request's fields (matched by name; a value instead; a required one unmapped named), a
 *             dry run first (the first three requests, the rows, the calls), Send (the results as a grid
 *             and a structure), Save as web call (mode "write rows").
 *   [AUTHOR]  Author a call: a screen of its own (the inputs prefilled, the body in the tree and the text,
 *             checked against the schema as it is typed, the declared headers; the sign-in is the API
 *             blade's). Send: its answer opens in Structures with its lineage. Save as web call (Return
 *             as table on or off: the one gate to SQL).
 *   [PAGE]    a page of the rail's over any page (areaPage.ts), in the address as open=apis.
 *
 * ROUTING: GET /apis, /apis/search, /apis/{name}  ·  POST/PUT /apis/{name}/calls/{op}  ·  POST /refresh,
 *          /refresh/apply, /delete, /make-into-blades  ·  PUT /check, /name  ·  Add API: addApi.ts
 */
import { api, saidOf } from "./api";
import { showAddApi } from "./addApi";
import { openAreaPage, type PageElement } from "./areaPage";
import { button, h, icon, openDialog, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { busy, busyClick, loadingBlock } from "./loading";
import { promptForError } from "./missingPackages";
import { dismissDialog, registerLayer, setOverTitle, watchLayerDialog } from "./nav";
import { mountText, mountTree, type Part, pathText, type Value } from "./structureTree";
import { openStructures } from "./structuresPage";
import { errorHere, errorMark, errorNote, warningNote } from "./errorNote";
import { APIS } from "./lazyPages";
import { sandboxPanel } from "./dataSandbox";

/** The page's name, in one place. */

interface Card {
  name: string;
  title: string;
  version: string;
  base_url: string;
  auth: string;
  operations: number;
  tables: string[];
  calls: { total: number };
  source: { kind: string; address: string; read_at: string; check: boolean };
  file: string | null;
  problem: string | null;
}

interface Parameter {
  name: string;
  in: string;
  type: string;
  required: boolean;
  default: Value;
  description: string;
  enum: string[];
  example: Value;
}

interface Answer {
  status: string;
  description: string;
  media: string;
  schema: Value;
  example: Value;
}

interface Operation {
  id: string;
  name: string;
  method: string;
  path: string;
  summary: string;
  description: string;
  tags: string[];
  deprecated: boolean;
  parameters: Parameter[];
  body: { required: boolean; description: string; media: string; schema: Value; example: Value } | null;
  responses: Answer[];
  schemas: string[];
  blade: string | null;
  as_table: boolean;
  table: { records: string; shape: string; conversion?: string } | null;
  inputs: Record<string, Record<string, Value>>;
  body_saved: Value;
  sql_name: string | null;
}

interface Explored {
  name: string;
  title: string;
  version: string;
  description: string;
  base_url: string;
  auth: string;
  operations: Operation[];
  schemas: { name: string; description: string; schema: Value; example: Value; used_by: string[]; uses: string[] }[];
}

interface Hit {
  api: string;
  operation: string;
  name: string;
  method: string;
  path: string;
  summary: string;
  matched: Record<string, string[]>;
}

let shownPage: PageElement | null = null;

registerLayer("apis", {
  isOpen: () => Boolean(shownPage?.open),
  open: () => drawPage(),
  show: () => undefined,
  dismiss: () => {
    if (shownPage) dismissDialog(shownPage);
  },
});

async function call<T>(path: string, method = "GET", body?: unknown): Promise<T | null> {
  try {
    return await api<T>(path, method, body);
  } catch (e) {
    const said: unknown = saidOf(e) ?? e;
    if (!promptForError(said)) errorHere(e);
    return null;
  }
}

const badge = (method: string): HTMLElement => h("span", { class: `api-method m-${method.toLowerCase()}` }, method);

/** Markdown as plain DOM (paragraphs, lists, **bold**, *italic*, `code`): never HTML. */
function markdown(text: string): HTMLElement {
  const out = h("div", { class: "api-description" });
  const inline = (line: string): Node[] => {
    const nodes: Node[] = [];
    const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
    let at = 0;
    for (const m of line.matchAll(pattern)) {
      nodes.push(document.createTextNode(line.slice(at, m.index)));
      const part = m[0];
      nodes.push(part.startsWith("**") ? h("strong", {}, part.slice(2, -2)) : part.startsWith("`") ? h("code", {}, part.slice(1, -1)) : h("em", {}, part.slice(1, -1)));
      at = (m.index ?? 0) + part.length;
    }
    nodes.push(document.createTextNode(line.slice(at)));
    return nodes;
  };
  let list: HTMLElement | null = null;
  for (const block of text.split(/\n{2,}/)) {
    for (const line of block.split("\n")) {
      const item = /^\s*[-*]\s+(.*)$/.exec(line);
      if (item) {
        list ??= out.appendChild(h("ul"));
        list.append(h("li", {}, ...inline(item[1]!)));
      } else if (line.trim()) {
        list = null;
        out.append(h("p", {}, ...inline(line.replace(/^#+\s*/, ""))));
      }
    }
    list = null;
  }
  return out;
}

const marked = (text: string, words: string[]): Node[] => {
  if (!words.length) return [document.createTextNode(text)];
  const pattern = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "ig");
  return text.split(pattern).map((part, i) => (i % 2 ? h("mark", {}, part) : document.createTextNode(part)));
};

function drawPage(): void {
  const { element, body, actions, foot, setHeading } = openAreaPage("apis", APIS);
  shownPage = element;
  body.classList.add("apis-page");
  setOverTitle(APIS);
  const search = h("input", { type: "search", class: "apis-search", placeholder: "Search every API", "aria-label": "Search every API", spellcheck: false }) as HTMLInputElement;
  let timer = 0;
  search.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => void (search.value.trim() ? showSearch(search.value.trim()) : showCards()), 250);
  });
  actions.replaceChildren(search, button("Add API", () => showAdd(), { icon: "plus", class: "primary apis-add" }));

  // ----- the cards -----

  const showCards = async (): Promise<void> => {
    setHeading(APIS);
    setOverTitle(APIS);
    foot.replaceChildren();
    const got = await call<{ apis: Card[]; older: { name: string }[] }>("/apis");
    if (!got || !element.open) return;
    if (!got.apis.length && !got.older.length) {
      body.replaceChildren(sandboxPanel(), h("div", { class: "apis-empty" }, h("p", { class: "empty-note" }, "No APIs yet.")));
      return;
    }
    body.replaceChildren(
      sandboxPanel(),
      h("div", { class: "apis-cards", role: "list" }, ...got.apis.map(card)),
      ...(got.older.length
        ? [h("section", { class: "apis-older" }, h("h2", {}, "Older API connections"), h("p", { class: "muted" }, "Made before APIs were blades; they keep working."), h("ul", {}, ...got.older.map((o) => h("li", {}, icon("plug"), h("span", {}, o.name), button("Make into blades", () => void makeIntoBlades(o.name), { class: "ghost api-make-blades" })))))]
        : []),
    );
    for (const c of got.apis) if (c.source.check && c.source.kind === "address") void refresh(c.name, true);
  };

  const card = (c: Card): HTMLElement => {
    const read = c.source.read_at ? new Date(c.source.read_at).toLocaleString() : "";
    const check = h("input", { type: "checkbox", role: "switch", class: "switch-input", "aria-label": `Check ${c.name} for changes`, checked: c.source.check }) as HTMLInputElement;
    check.addEventListener("change", () => void call(`/apis/${encodeURIComponent(c.name)}/check`, "PUT", { on: check.checked }));
    return h(
      "article",
      { class: "api-card", role: "listitem", "data-api": c.name },
      h("button", { type: "button", class: "api-card-open", onclick: () => void explore(c.name) },
        h("span", { class: "api-card-name" }, icon("apis"), c.name),
        h("span", { class: "muted" }, [c.title !== c.name ? c.title : "", c.version].filter(Boolean).join(" · ")),
      ),
      h("div", { class: "api-card-base mono", title: "Its base address" }, c.base_url),
      h("div", { class: "api-card-facts" },
        h("span", {}, `${c.operations} operation${c.operations === 1 ? "" : "s"}`),
        h("span", {}, c.tables.length ? `${c.tables.length} table${c.tables.length === 1 ? "" : "s"}` : "no tables"),
        h("span", {}, `sign-in: ${c.auth}`),
        h("span", {}, `${c.calls.total ?? 0} call${c.calls.total === 1 ? "" : "s"} this session`),
      ),
      h("div", { class: "api-card-source muted" }, c.source.kind === "address" ? c.source.address : c.source.kind === "file" ? c.source.address : c.source.kind === "form" ? "Made with the form" : "Pasted", read ? ` · read ${read}` : ""),
      c.problem ? errorNote(c.problem) : null,
      h("div", { class: "api-card-actions" },
        button("Refresh", busyClick("Refreshing…", (b) => busy(b.closest<HTMLElement>(".api-card") ?? b, `Reading ${c.name} again…`, refresh(c.name))), { icon: "reset" }),
        c.source.kind === "address" ? h("label", { class: "autosave-switch" }, check, h("span", {}, "Check for changes")) : null,
        button("Rename", () => rename(c.name), { icon: "rename" }),
        button("Copy folder", () => void navigator.clipboard.writeText((c.file ?? "").replace(/[\\/][^\\/]*$/, "")).then(() => toast("Copied the folder's path")), { icon: "folder" }),
        button("Delete", () => void remove(c.name), { icon: "trash" }),
      ),
    );
  };

  const refresh = async (name: string, quiet = false): Promise<void> => {
    const got = await call<{ diff: { added: { id: string; method: string; path: string }[]; removed: { id: string; method: string; path: string }[]; changed: { id: string; method: string; path: string; changes: string[] }[]; any: boolean; base_url: boolean } }>(`/apis/${encodeURIComponent(name)}/refresh`, "POST", {});
    if (!got) return;
    const d = got.diff;
    if (!d.any) {
      if (!quiet) toast(`${name} has not changed.`);
      return;
    }
    const { dialog, body: box, foot: buttons, close } = openDialog(`${name}: what changed`, true);
    dialog.classList.add("api-diff");
    const group = (title: string, rows: { id: string; method: string; path: string; changes?: string[] }[], kind: string): HTMLElement | null =>
      rows.length ? h("section", { class: `api-diff-${kind}` }, h("h3", {}, `${title} (${rows.length})`), h("ul", {}, ...rows.map((r) => h("li", {}, badge(r.method), h("code", {}, r.path), h("span", { class: "muted" }, ` ${r.id}`), r.changes ? h("ul", { class: "api-diff-notes" }, ...r.changes.map((c) => h("li", {}, c))) : null)))) : null;
    box.append(...[group("Added", d.added, "added"), group("Removed", d.removed, "removed"), group("Changed", d.changed, "changed")].filter((x): x is HTMLElement => x !== null));
    if (d.base_url) box.append(h("p", {}, "Its base address changed."));
    buttons.append(button("Not now", () => close()), button("Apply", busyClick("Applying…", async () => {
      const done = await busy(box, `Applying ${name}'s changes…`, call(`/apis/${encodeURIComponent(name)}/refresh/apply`, "POST", {}));
      close();
      if (done) {
        toast(`${name} is up to date.`);
        void showCards();
      }
    }), { class: "primary" }));
  };

  const rename = (name: string): void => {
    const { body: box, foot: buttons, close } = openDialog(`Rename ${name}`);
    const input = h("input", { "aria-label": "New name", value: name }) as HTMLInputElement;
    box.append(input);
    buttons.append(button("Cancel", () => close()), button("Rename", async () => {
      const done = await call<{ references: unknown[] }>(`/apis/${encodeURIComponent(name)}/name`, "PUT", { name: input.value });
      close();
      if (done) {
        if (done.references.length) toast(`${done.references.length} place${done.references.length === 1 ? "" : "s"} in code still name ${name}.`);
        void showCards();
      }
    }, { class: "primary" }));
    input.focus();
    input.select();
  };

  /** Make into blades: an older API connection made into the library's blades (only on this click). Its
   * document is read again from where it was made; when Add API did not keep it, the user picks it. */
  const makeIntoBlades = async (name: string): Promise<void> => {
    const path = `/apis/${encodeURIComponent(name)}/make-into-blades`;
    let done: { web_calls: string[] } | null = null;
    try {
      done = await api<{ web_calls: string[] }>(path, "POST", {});
    } catch (e) {
      if (!/spec_path/.test((e as Error).message)) {
        errorHere(e);
        return;
      }
      const file = await chooseFile({ title: `${name}'s OpenAPI document`, mode: "file", suffixes: [".json", ".yaml", ".yml"] });
      if (!file) return;
      done = await call<{ web_calls: string[] }>(path, "POST", { spec_path: file });
    }
    if (!done) return;
    toast(`${name} is blades now: its API blade and ${done.web_calls.length} web calls.`);
    await showCards();
  };

  const remove = async (name: string): Promise<void> => {
    const asked = await call<{ references: { title: string; how: string; line: string }[] }>(`/apis/${encodeURIComponent(name)}/delete`, "POST", {});
    if (!asked) return;
    const { body: box, foot: buttons, close } = openDialog(`Delete ${name}?`);
    box.append(
      h("p", {}, "Its API blade, its web call blades and its folder go."),
      asked.references.length
        ? h("div", {}, h("p", {}, "Code that uses it:"), h("ul", { class: "api-references" }, ...asked.references.map((r) => h("li", {}, h("strong", {}, r.title), " ", h("code", {}, r.line)))))
        : h("p", { class: "muted" }, "No code uses it."),
    );
    buttons.append(button("Cancel", () => close()), button("Delete", async () => {
      const done = await call(`/apis/${encodeURIComponent(name)}/delete`, "POST", { confirm: true });
      close();
      if (done) void showCards();
    }, { class: "danger" }));
  };

  const showAdd = (): void => {
    setHeading(APIS, " › Add API");
    setOverTitle(`${APIS} › Add API`);
    showAddApi({ body, foot, backTo: { label: APIS, url: "?open=apis" }, added: (name) => void explore(name) });
  };

  // ----- search -----

  const showSearch = async (q: string): Promise<void> => {
    const got = await call<{ results: Hit[] }>(`/apis/search?q=${encodeURIComponent(q)}`);
    if (!got || !element.open || search.value.trim() !== q) return;
    const words = q.split(/\s+/).filter(Boolean);
    foot.replaceChildren();
    body.replaceChildren(
      got.results.length
        ? h("ol", { class: "api-results", "aria-label": "Results" }, ...got.results.map((r) =>
            h("li", {}, h("button", { type: "button", class: "api-result", onclick: () => void explore(r.api, r.operation) },
              h("span", { class: "api-result-api" }, ...marked(r.api, words)),
              badge(r.method),
              h("code", { class: "api-result-path" }, ...marked(r.path, words)),
              h("span", { class: "api-result-name" }, ...marked(r.name, words)),
              h("span", { class: "muted api-result-where" }, Object.keys(r.matched).filter((k) => !["api", "name", "path"].includes(k)).join(", ")),
            )),
          ))
        : h("p", { class: "empty-note" }, "No match."),
    );
  };

  // ----- the explorer -----

  const explore = async (name: string, operation: string | null = null): Promise<void> => {
    const got = await call<Explored>(`/apis/${encodeURIComponent(name)}`);
    if (!got || !element.open) return;
    setHeading(APIS, ` › ${got.name}`);
    setOverTitle(`${APIS} › ${got.name}`);
    foot.replaceChildren(button(`← ${APIS}`, () => void showCards(), { class: "ghost" }));
    const left = h("nav", { class: "api-ops", "aria-label": `${got.name}'s operations` });
    const right = h("div", { class: "api-detail" });
    const tags = new Map<string, Operation[]>();
    for (const op of got.operations) {
      const tag = op.tags[0] || "Other";
      tags.set(tag, [...(tags.get(tag) ?? []), op]);
    }
    const pick = (draw: () => void, item: HTMLElement): void => {
      left.querySelectorAll(".current").forEach((x) => x.classList.remove("current"));
      item.classList.add("current");
      draw();
    };
    for (const [tag, ops] of tags) {
      const group = h("details", { class: "api-tag", open: true }, h("summary", {}, tag, h("span", { class: "count" }, String(ops.length))));
      for (const op of ops) {
        const item = h("button", { type: "button", class: "api-op", "data-operation": op.id, title: op.name }, badge(op.method), h("code", {}, op.path), op.as_table ? icon("table") : null);
        item.addEventListener("click", () => pick(() => showOperation(got, op, right), item));
        group.append(item);
      }
      left.append(group);
    }
    if (got.schemas.length) {
      const group = h("details", { class: "api-tag api-schemas", open: true }, h("summary", {}, "Schemas", h("span", { class: "count" }, String(got.schemas.length))));
      for (const s of got.schemas) {
        const item = h("button", { type: "button", class: "api-op", "data-schema": s.name }, icon("schema"), h("span", {}, s.name));
        item.addEventListener("click", () => pick(() => showSchema(got, s, right), item));
        group.append(item);
      }
      left.append(group);
    }
    body.replaceChildren(h("div", { class: "api-explorer" }, left, right));
    const first = (operation && left.querySelector<HTMLElement>(`[data-operation="${CSS.escape(operation)}"]`)) || left.querySelector<HTMLElement>(".api-op");
    first?.click();
  };

  const treeBlock = (title: string, value: Value, schema: boolean): HTMLElement =>
    h("div", { class: "api-tree-block" }, h("h4", {}, title), mountTree(value, { depth: 3, schema, label: title }).element);

  const showSchema = (got: Explored, s: Explored["schemas"][number], right: HTMLElement): void => {
    right.replaceChildren(
      h("h2", { class: "api-op-title" }, icon("schema"), s.name),
      s.description ? markdown(s.description) : "",
      h("div", { class: "api-two" }, treeBlock("Schema", s.schema, true), treeBlock("Example", s.example, false)),
      s.used_by.length ? h("p", {}, "Used by: ", ...s.used_by.map((id) => h("button", { type: "button", class: "link", onclick: () => void explore(got.name, id) }, id))) : "",
    );
  };

  const showOperation = (got: Explored, op: Operation, right: HTMLElement): void => {
    const inputs = op.parameters.length
      ? h("table", { class: "api-params" }, h("thead", {}, h("tr", {}, ...["Name", "Where", "Type", "Required", "Default", "Description"].map((t) => h("th", {}, t)))), h("tbody", {}, ...op.parameters.map((p) => h("tr", {}, h("td", { class: "mono" }, p.name), h("td", {}, p.in), h("td", {}, p.type), h("td", {}, p.required ? "yes" : ""), h("td", { class: "mono" }, p.default === null || p.default === undefined ? "" : JSON.stringify(p.default)), h("td", {}, p.description)))))
      : h("p", { class: "muted" }, "No parameters.");
    right.replaceChildren(
      h("h2", { class: "api-op-title" }, badge(op.method), h("code", {}, op.path)),
      h("p", { class: "api-op-name" }, op.name, op.deprecated ? h("span", { class: "api-deprecated" }, " deprecated") : ""),
      op.description ? markdown(op.description) : "",
      h("div", { class: "api-op-actions" },
        button("Author a call", () => author(got, op, right), { icon: "edit", class: "primary api-author" }),
        ["POST", "PUT", "PATCH", "DELETE"].includes(op.method) ? button("Write rows with this call", () => void writeRows(got, op, right), { icon: "rows", class: "api-write" }) : null,
        op.sql_name ? h("span", { class: "api-sql" }, icon("table"), h("code", {}, `SELECT * FROM ${op.sql_name}`), button("Copy name for SQL", () => void navigator.clipboard.writeText(op.sql_name!).then(() => toast(`Copied ${op.sql_name}`)), { icon: "copy", iconOnly: true, class: "ghost" })) : h("span", { class: "muted" }, "Not a table (Return as table is off)."),
      ),
      op.sql_name ? conversionBox(got, op) : "",
      h("section", { class: "api-inputs" }, h("h3", {}, "Inputs"), inputs, op.body ? h("div", { class: "api-two" }, treeBlock(`Body${op.body.required ? " (required)" : ""}`, op.body.schema, true), treeBlock("Example", op.body.example, false)) : ""),
      h("section", { class: "api-outputs" }, h("h3", {}, "Outputs"), ...op.responses.map((r) => h("div", { class: "api-answer" }, h("h4", {}, h("span", { class: `api-status s${r.status[0]}` }, r.status), " ", r.description), r.schema ? h("div", { class: "api-two" }, treeBlock("Schema", r.schema, true), treeBlock("Example", r.example, false)) : h("p", { class: "muted" }, "No body.")))),
      op.schemas.length ? h("p", { class: "muted" }, "Schemas: ", op.schemas.join(", ")) : "",
    );
  };

  /** Return as table's conversion: DuckDB's own query over the pages read (`response`, one row per page,
   * its JSON in `page`), the user's to read and change. */
  const conversionBox = (got: Explored, op: Operation): HTMLElement => {
    const sql = h("textarea", { class: "mono api-conversion-sql", "aria-label": "The DuckDB query", rows: 6, spellcheck: "false" }) as HTMLTextAreaElement;
    sql.value = op.table?.conversion ?? "";
    const save = async (made: boolean): Promise<void> => {
      const done = await call<{ web_call: { conversion: string } }>(`/apis/${encodeURIComponent(got.name)}/calls/${encodeURIComponent(op.id)}`, "PUT", made ? { as_table: true, records: op.table?.records ?? "$" } : { as_table: true, conversion: sql.value });
      if (!done) return;
      toast(made ? "The query is made again from the settings." : "Saved the query.");
      await explore(got.name, op.id);
    };
    return h("details", { class: "api-conversion" },
      h("summary", {}, "The DuckDB query"),
      sql,
      h("div", { class: "api-conversion-actions" },
        button("Save the query", busyClick("Saving…", () => save(false)), { icon: "save" }),
        button("Make it again", busyClick("Making…", () => save(true)), { class: "ghost", title: "From the rows path and the header" }),
      ),
    );
  };

  // ----- Author a call: a screen of its own -----

  const author = (got: Explored, op: Operation, right: HTMLElement): void => {
    setHeading(APIS, ` › ${got.name} › ${op.method} ${op.path}`);
    const fields = new Map<string, HTMLInputElement>();
    const saved = (p: Parameter): Value => op.inputs?.[p.in]?.[p.name] ?? null;
    const row = (p: Parameter): HTMLElement => {
      const start = saved(p) ?? p.default ?? p.example ?? "";
      const input = h("input", { "aria-label": p.name, value: start === null ? "" : typeof start === "string" ? start : JSON.stringify(start), placeholder: p.type, "data-param": `${p.in}:${p.name}` }) as HTMLInputElement;
      fields.set(`${p.in}:${p.name}`, input);
      return h("label", { class: "api-input" }, h("span", { class: "api-input-name" }, p.name, p.required ? h("span", { class: "required", "aria-label": "required" }, "*") : null, h("span", { class: "muted" }, ` ${p.in} · ${p.type}`)), input, p.description ? h("span", { class: "muted api-input-help" }, p.description) : null);
    };
    const params = op.parameters.filter((p) => p.in !== "header");
    const headers = op.parameters.filter((p) => p.in === "header");
    let body: Value = (op.body_saved ?? op.body?.example ?? null) as Value;
    const problems = h("div", { class: "api-body-problems", "aria-live": "polite" });
    const check = (): void => {
      // The body against its schema: one warning, each problem in its list (it may still be sent).
      const found = op.body?.schema ? checkAgainst(body, op.body.schema, []) : [];
      problems.replaceChildren(
        ...(found.length
          ? [warningNote({ what: found.length === 1 ? found[0]! : `The body does not fit its schema in ${found.length} places.`, details: found.length > 1 ? found.slice(0, 20).join("\n") : undefined, dismiss: false })]
          : []),
      );
    };
    let bodyTree = mountTree(body, { depth: 3, label: "Body", onSet: (parts, v) => setAt(parts, v), onRename: (parts, key, to) => renameAt(parts, key, to) });
    const treeHost = h("div", { class: "api-body-tree" }, bodyTree.element);
    const text = mountText(JSON.stringify(body, null, 2), "json", (t) => {
      try {
        body = JSON.parse(t) as Value;
        text.setError(null);
        redrawTree(false);
      } catch (e) {
        const where = /position (\d+)/.exec((e as Error).message);
        const line = where ? t.slice(0, Number(where[1])).split("\n").length : 1;
        text.setError(`Not JSON: line ${line}: ${(e as Error).message}`);
      }
      check();
    }, "Body as JSON");
    const redrawTree = (andText: boolean): void => {
      const fresh = mountTree(body, { depth: 3, label: "Body", onSet: (parts, v) => setAt(parts, v), onRename: (parts, key, to) => renameAt(parts, key, to) });
      treeHost.replaceChildren(fresh.element);
      bodyTree = fresh;
      if (andText) text.set(JSON.stringify(body, null, 2), "json");
      check();
    };
    const setAt = (parts: Part[], v: Value): void => {
      if (!parts.length) body = v;
      else {
        let node = body as Record<string | number, Value>;
        for (const p of parts.slice(0, -1)) node = node[p] as Record<string | number, Value>;
        node[parts[parts.length - 1]!] = v;
      }
      redrawTree(true);
    };
    const renameAt = (parts: Part[], key: string, to: string): void => {
      let node = body as Record<string | number, Value>;
      for (const p of parts) node = node[p] as Record<string | number, Value>;
      const entries = Object.entries(node).map(([k, v]) => [k === key ? to : k, v] as const);
      for (const k of Object.keys(node)) delete node[k];
      for (const [k, v] of entries) node[k] = v;
      redrawTree(true);
    };
    const values = (): Record<string, Record<string, Value>> => {
      const out: Record<string, Record<string, Value>> = {};
      for (const p of op.parameters) {
        const raw = fields.get(`${p.in}:${p.name}`)?.value ?? "";
        if (raw === "") continue;
        let v: Value = raw;
        if (/^(integer|number)/.test(p.type) && raw.trim() !== "" && !Number.isNaN(Number(raw))) v = Number(raw);
        else if (p.type.startsWith("boolean")) v = raw === "true";
        (out[p.in] ??= {})[p.name] = v;
      }
      return out;
    };
    const asTable = h("input", { type: "checkbox", "aria-label": "Return as table", checked: op.as_table }) as HTMLInputElement;
    const records = h("input", { "aria-label": "Records path", value: op.table?.records ?? "$", class: "mono", placeholder: "$.items" }) as HTMLInputElement;
    // The conversion: DuckDB's query over the answer, shown while Return as table is on; sent only when edited.
    const query = h("textarea", { class: "mono api-conversion-sql", "aria-label": "The DuckDB query", rows: 5, spellcheck: "false", placeholder: "Made from the rows path when saved" }) as HTMLTextAreaElement;
    query.value = op.table?.conversion ?? "";
    let queryEdited = false;
    query.addEventListener("input", () => (queryEdited = true));
    const queryBox = h("details", { class: "api-conversion", hidden: !asTable.checked }, h("summary", {}, "The DuckDB query"), query);
    asTable.addEventListener("change", () => (queryBox.hidden = !asTable.checked));
    const result = h("div", { class: "api-send-result", role: "status" });
    const send = async (): Promise<void> => {
      result.replaceChildren(loadingBlock(`Calling ${op.id}…`, { height: "48px" }));
      const done = await call<{ status: number; ms: number; structure: string; said: string; suggest_table: { records: string } | null }>(`/apis/${encodeURIComponent(got.name)}/calls/${encodeURIComponent(op.id)}`, "POST", { inputs: values(), ...(op.body ? { body } : {}) });
      if (!done) {
        result.replaceChildren();
        return;
      }
      result.replaceChildren(
        h("p", {}, h("span", { class: `structures-status ${done.status < 300 ? "ok" : "bad"}` }, String(done.status)), ` ${done.ms} ms `, done.said ? errorMark(done.said) : ""),
        done.suggest_table && !asTable.checked ? h("p", { class: "muted api-suggest" }, `It answers rows at ${done.suggest_table.records}: Return as table can make it a table.`) : "",
        button("Open in Structures", () => openStructures(done.structure), { icon: "structures" }),
      );
      openStructures(done.structure);
    };
    const save = async (): Promise<void> => {
      const done = await call<{ blade: string; sql_name: string | null; web_call: { records: string; shape: string; conversion?: string } }>(`/apis/${encodeURIComponent(got.name)}/calls/${encodeURIComponent(op.id)}`, "PUT", { inputs: values(), ...(op.body ? { body } : {}), as_table: asTable.checked, ...(asTable.checked ? { records: records.value || "$", ...(queryEdited && query.value.trim() ? { conversion: query.value } : {}) } : {}) });
      if (!done) return;
      // The explorer's copy follows (Back shows it as saved).
      Object.assign(op, { blade: done.blade, sql_name: done.sql_name, as_table: Boolean(done.sql_name), table: done.web_call });
      toast(done.sql_name ? `Saved ${done.blade}: ${done.sql_name} is a table.` : `Saved ${done.blade}.`);
    };
    right.replaceChildren(
      h("div", { class: "api-author-screen" },
        h("h2", { class: "api-op-title" }, badge(op.method), h("code", {}, `${got.base_url}${op.path}`)),
        h("section", {}, h("h3", {}, "Inputs"), params.length ? h("div", { class: "api-inputs-form" }, ...params.map(row)) : h("p", { class: "muted" }, "No parameters.")),
        headers.length ? h("section", {}, h("h3", {}, "Headers"), h("div", { class: "api-inputs-form" }, ...headers.map(row))) : "",
        h("p", { class: "muted api-signin" }, icon("key"), `Sign-in (${got.auth}) is the API blade's: never shown here.`),
        op.body ? h("section", { class: "api-body" }, h("h3", {}, "Body"), h("div", { class: "api-body-split" }, treeHost, h("div", { class: "api-body-text" }, text.element)), problems) : "",
        h("div", { class: "api-author-actions" },
          button("Send", busyClick("Sending…", send), { icon: "play", class: "primary api-send" }),
          h("label", { class: "autosave-switch" }, asTable, h("span", {}, "Return as table")),
          h("label", { class: "api-records" }, h("span", {}, "Rows at"), records),
          button("Save as web call", busyClick("Saving…", save), { icon: "save" }),
          button("Back", () => showOperation(got, op, right), { class: "ghost" }),
        ),
        queryBox,
        result,
      ),
    );
    check();
    void bodyTree;
  };

  // ----- Write rows with this call: a table's rows through a POST, PUT, PATCH or DELETE -----

  const writeRows = async (got: Explored, op: Operation, right: HTMLElement): Promise<void> => {
    setHeading(APIS, ` › ${got.name} › Write rows with ${op.method} ${op.path}`);
    const listed = await call<{ datasets: { name: string }[] }>("/datasets");
    const tables = (listed?.datasets ?? []).map((d) => d.name);
    const table = h("select", { "aria-label": "The rows" }, ...tables.map((t) => h("option", { value: t }, t))) as HTMLSelectElement;
    const targets: { field: string; required: boolean }[] = [
      ...op.parameters.map((p) => ({ field: `${p.in}.${p.name}`, required: p.required })),
      ...leaves(op.body?.schema ?? null, "body", true),
    ];
    const pickers = new Map<string, { select: HTMLSelectElement; value: HTMLInputElement }>();
    const mappingRows = h("tbody");
    const batch = h("input", { type: "checkbox", "aria-label": "Batch" }) as HTMLInputElement;
    const shown = h("div", { class: "api-write-result", role: "status" });
    const columnsOf = async (): Promise<string[]> => {
      const dry = await call<{ columns: string[]; mapping: Record<string, { column?: string; value?: Value }> }>(`/apis/${encodeURIComponent(got.name)}/calls/${encodeURIComponent(op.id)}/write`, "POST", { table: table.value });
      if (!dry) return [];
      mappingRows.replaceChildren(
        ...targets.map((t) => {
          const select = h("select", { "aria-label": `${t.field} from` }, h("option", { value: "" }, "(not sent)"), ...dry.columns.map((c) => h("option", { value: `column:${c}` }, c)), h("option", { value: "value" }, "A value…")) as HTMLSelectElement;
          const value = h("input", { "aria-label": `${t.field}'s value`, hidden: true, class: "mono" }) as HTMLInputElement;
          const found = dry.mapping[t.field];
          if (found?.column) select.value = `column:${found.column}`;
          else if (found && "value" in found) {
            select.value = "value";
            value.value = JSON.stringify(found.value);
            value.hidden = false;
          }
          select.addEventListener("change", () => (value.hidden = select.value !== "value"));
          pickers.set(t.field, { select, value });
          return h("tr", { "data-field": t.field }, h("td", { class: "mono" }, t.field, t.required ? h("span", { class: "required" }, "*") : null), h("td", {}, select, value));
        }),
      );
      return dry.columns;
    };
    const mapping = (): Record<string, { column?: string; value?: Value }> => {
      const out: Record<string, { column?: string; value?: Value }> = {};
      for (const [field, { select, value }] of pickers) {
        if (select.value.startsWith("column:")) out[field] = { column: select.value.slice(7) };
        else if (select.value === "value") {
          let v: Value = value.value;
          try {
            v = JSON.parse(value.value) as Value;
          } catch {
            v = value.value;
          }
          out[field] = { value: v };
        }
      }
      return out;
    };
    const run = async (dryRun: boolean): Promise<void> => {
      const answer = await call<{ dry_run?: boolean; rows: number; calls: number; first?: { inputs: Value; body: Value }[]; missing?: string[]; written?: number; failed?: number; structure?: string }>(
        `/apis/${encodeURIComponent(got.name)}/calls/${encodeURIComponent(op.id)}/write`,
        "POST",
        { table: table.value, mapping: mapping(), batch: batch.checked, dry_run: dryRun },
      );
      if (!answer) return;
      if (answer.dry_run) {
        shown.replaceChildren(
          h("p", {}, `${answer.rows} rows, ${answer.calls} call${answer.calls === 1 ? "" : "s"}. Nothing was sent.`),
          answer.missing?.length ? errorNote(`Map these first: ${answer.missing.join(", ")}`) : "",
          ...(answer.first ?? []).map((f, i) => h("details", { open: i === 0 }, h("summary", {}, `Request ${i + 1}`), h("pre", { class: "mono" }, JSON.stringify(f, null, 2)))),
        );
      } else {
        shown.replaceChildren(h("p", {}, `${answer.written} written, ${answer.failed} failed.`), answer.structure ? button("Open the results in Structures", () => openStructures(answer.structure!), { icon: "structures" }) : "");
        if (answer.structure) openStructures(answer.structure);
      }
    };
    table.addEventListener("change", () => void columnsOf());
    right.replaceChildren(
      h("div", { class: "api-author-screen api-write-screen" },
        h("h2", { class: "api-op-title" }, badge(op.method), h("code", {}, op.path)),
        h("label", { class: "api-input" }, h("span", {}, "The rows"), table),
        h("section", {}, h("h3", {}, "Mapping"), h("table", { class: "api-params api-mapping" }, h("thead", {}, h("tr", {}, h("th", {}, "Field"), h("th", {}, "From"))), mappingRows)),
        h("div", { class: "api-author-actions" },
          h("label", { class: "autosave-switch" }, batch, h("span", {}, "One call for many rows")),
          button("Dry run", () => void run(true), { icon: "eye", class: "primary api-dry-run" }),
          button("Send", busyClick("Sending…", () => run(false)), { icon: "play", class: "api-write-send" }),
          button("Save as web call", async () => {
            const saved = await call<{ blade: string }>(`/apis/${encodeURIComponent(got.name)}/calls/${encodeURIComponent(op.id)}/write`, "PUT", { mapping: mapping(), batch: batch.checked, table: table.value });
            if (saved) toast(`Saved ${saved.blade}.`);
          }, { icon: "save" }),
          button("Back", () => showOperation(got, op, right), { class: "ghost" }),
        ),
        shown,
      ),
    );
    if (tables.length) await columnsOf();
    else shown.replaceChildren(h("p", { class: "empty-note" }, "No table is open."));
  };

  watchLayerDialog(element, "apis", [], () => {
    if (shownPage === element) shownPage = null;
  });
  body.append(loadingBlock("Loading the APIs…"));
  void showCards();
}

/** A body checked against its schema's tree (domain/api_explorer.py's schema_tree): a required key
 *  (name*) missing, a value of another type. The words say where. */
export function checkAgainst(value: Value, schema: Value, at: Part[]): string[] {
  const where = pathText(at);
  if (typeof schema === "string") {
    const word = schema.split(/[\s(:]/)[0] ?? "";
    if (value === null || word === "any" || schema.startsWith("→")) return [];
    const ok: Record<string, boolean> = {
      string: typeof value === "string",
      integer: typeof value === "number" && Number.isInteger(value),
      number: typeof value === "number",
      boolean: typeof value === "boolean",
      object: typeof value === "object" && !Array.isArray(value),
      array: Array.isArray(value),
    };
    if (word in ok && !ok[word]) return [`${where} is ${word}${schema.includes(":") ? schema.slice(schema.indexOf(":")) : ""}`];
    const choices = schema.includes(": ") ? schema.slice(schema.indexOf(": ") + 2).split(" | ") : [];
    if (choices.length && typeof value === "string" && !choices.includes(value)) return [`${where} is one of ${choices.join(", ")}`];
    return [];
  }
  if (Array.isArray(schema)) {
    if (!Array.isArray(value)) return [`${where} is a list`];
    return value.flatMap((v, i) => checkAgainst(v, schema[0] ?? "any", [...at, i]));
  }
  if (schema && typeof schema === "object") {
    if (value === null || typeof value !== "object" || Array.isArray(value)) return [`${where} is an object`];
    const out: string[] = [];
    for (const [key, inner] of Object.entries(schema)) {
      const name = key.replace(/\*$/, "");
      if (key.endsWith("*") && !(name in value)) out.push(`${pathText([...at, name])} is required`);
      if (name in value) out.push(...checkAgainst((value as Record<string, Value>)[name]!, inner, [...at, name]));
    }
    return out;
  }
  return [];
}

/** A body schema's leaves as request fields (domain/write_rows.py fields): body.customer.name; a nested
 *  field is required when it and every object above it are. */
function leaves(tree: Value, prefix: string, required: boolean): { field: string; required: boolean }[] {
  if (!tree || typeof tree !== "object" || Array.isArray(tree)) return [];
  const out: { field: string; required: boolean }[] = [];
  for (const [key, inner] of Object.entries(tree)) {
    const name = key.replace(/\*$/, "");
    const needed = required && key.endsWith("*");
    if (inner && typeof inner === "object" && !Array.isArray(inner) && Object.keys(inner).length) out.push(...leaves(inner, `${prefix}.${name}`, needed));
    else if (!Array.isArray(inner)) out.push({ field: `${prefix}.${name}`, required: needed });
  }
  return out;
}
