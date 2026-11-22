/**
 * dataSandbox.ts: the project's sandbox (services/sandbox.py; the owner, 2026-11-21: "transform scaffold create an
 * app then test it out and then reset the data changes and try again"). The data a local sandbox API reads and
 * writes, and nothing else; never a connection. (Not the Analyze board's old sandbox*.ts: another word.)
 *
 *   [ADD]    Add to sandbox… from the grid's Table row: the open table's view, after its steps; from the panel:
 *            an open table, a file, or an empty table by its columns. Rows go to disk only by this action.
 *   [PANEL]  the tables (rows, where each came from, the client its rows are mocked as, its changes), Open in
 *            Grids (follows every write), Remove; Reset (back to the baseline), Set as baseline, Save
 *            checkpoint…, each checkpoint's Restore and Delete; the change log's line, live (sandbox_changed).
 *   [SORT]   every column heading sorts the list (name, rows, source, created, last changed; again: the other
 *            way), remembered in this browser (the owner, 2026-11-21: "We need all sandbox tables to be sortable")
 *   [MOCK]   a table from a file, its columns or a grid of no connection's: "Mocked as" picks the connection whose
 *            kind and dialect its mock client takes (or the plain DuckDB client)
 *   [VARIANT] Make a sandbox variant… (a grid's Table row, the Structures page): a copy with its own designation
 *            ("orders · sandbox", or the name given), its origin kept and shown, a distinct mark; never writes back
 *
 * ROUTING: GET /sandbox?sort=&order= · POST /sandbox/tables, /tables/remove, /tables/open, /tables/variant,
 *          /tables/mock, /reset, /baseline, /checkpoints, /checkpoints/restore
 */
import { api, onNoticeWhile } from "./api";
import { button, dateTime, h, icon, openDialog, recall, remember, toast } from "./dom";
import { errorHere } from "./errorNote";
import { chooseFile } from "./fileChooser";
import { busy, busyClick, loadingBlock } from "./loading";
import { newEndpoint } from "./endpointWizard";

export interface SandboxTable {
  name: string;
  rows: number;
  columns: { name: string; type: string; key: boolean }[];
  source_words: string;
  client: { kind: string; connection?: string; template?: string };
  sql: string;
  open: boolean;
  changes: { inserted: number; updated: number; deleted: number };
  type: string;
  title: string;
  variant: { title: string; origin: Record<string, string>; copied_at: string } | null;
  origin_words: string;
  added_at: string | null;
  changed_at: string | null;
  mockable: boolean;
  mocked: boolean;
}

export interface SandboxState {
  project: string | null;
  tables: SandboxTable[];
  baseline_at: string | null;
  checkpoints: { name: string; at: string }[];
  log_words?: string;
  mock_choices?: string[];
  sort?: { by: string; order: string; choices: Record<string, string> };
}

const SORT_KEY = "sandbox.sort";
/** The list's sort, as this browser remembered it: "name asc" by default. */
export function sandboxSort(): { sort: string; order: string } {
  const [sort, order] = (recall(SORT_KEY) ?? "name asc").split(" ");
  return { sort: sort || "name", order: order === "desc" ? "desc" : "asc" };
}

const KIND_WORDS: Record<string, string> = { database: "database", dataverse: "Dataverse", sharepoint: "SharePoint", powerbi: "Power BI", file: "file", python: "Python" };

/** "Mock of Warehouse (sqlserver)" or "Plain DuckDB": the client a sandbox table's rows answer as. */
export function clientWords(client: SandboxTable["client"]): string {
  if (!client.connection || client.kind === "duckdb") return "Plain DuckDB client";
  const what = client.template || KIND_WORDS[client.kind] || client.kind;
  return `Mock of ${client.connection} (${what})`;
}

/** Make a sandbox variant… of an open table (the grid's Table row) or a structure (the Structures page): a copy
 *  with its own designation ("orders · sandbox", or the name given) and its origin kept. */
export function makeVariant(from: "grid" | "structure", origin: string, made?: () => void, path?: string): void {
  const { body, foot, close } = openDialog("Make a sandbox variant");
  const name = h("input", { "aria-label": "Its name", placeholder: `${origin} · sandbox`, spellcheck: false }) as HTMLInputElement;
  body.append(
    h("p", {}, `A copy of ${from === "grid" ? "the open table" : "the structure's records"} `, h("strong", {}, origin), " in the project's sandbox. It never writes back."),
    h("label", { class: "field" }, h("span", {}, "Its name"), name),
  );
  foot.append(
    button("Cancel", () => close()),
    button("Make", busyClick("Making…", async (b) => {
      try {
        const done = await api<{ added: string; rows: number; title: string }>("/sandbox/tables/variant", "POST", { from, [from === "grid" ? "table" : "structure"]: origin, path, name: name.value.trim() || undefined });
        close();
        toast(`${done.title} is in the sandbox: ${done.rows.toLocaleString()} rows.`);
        made?.();
      } catch (e) {
        errorHere(e, {}, b);
      }
    }), { class: "primary" }),
  );
  name.focus();
}

/** The sandbox panel: its tables, Reset, checkpoints and the change log, kept live. */
export function sandboxPanel(): HTMLElement {
  const panel = h("section", { class: "sandbox-panel", "aria-label": "Sandbox" });
  const draw = async (): Promise<void> => {
    let got: SandboxState;
    const { sort, order } = sandboxSort();
    try {
      got = await api<SandboxState>(`/sandbox?sort=${sort}&order=${order}`);
    } catch (e) {
      panel.replaceChildren(h("h2", {}, "Sandbox"));
      errorHere(e, {}, panel);
      return;
    }
    const head = h("div", { class: "sandbox-head" }, h("h2", {}, "Sandbox"));
    if (!got.project) {
      panel.replaceChildren(head, h("p", { class: "empty-note" }, "Open a project: its sandbox lives in its folder."));
      return;
    }
    head.append(
      h("span", { class: "sandbox-log muted", role: "status" }, got.log_words ?? ""),
      button("Add table…", () => chooseSource(() => void draw()), { icon: "plus" }),
      button("Reset", busyClick("Resetting…", (b) => act(b, "/sandbox/reset", {}, "The sandbox is back to its baseline.")), { icon: "reset", title: "Every table back to the baseline" }),
      button("Set as baseline", busyClick("Setting…", (b) => act(b, "/sandbox/baseline", {}, "This is the baseline now.")), { title: "Reset comes back to the sandbox as it is now" }),
      button("Save checkpoint…", () => saveCheckpoint(), { icon: "save" }),
    );
    const rows = got.tables.map((t) =>
      h("tr", { "data-table": t.name, class: t.variant ? "sandbox-variant" : "" },
        h("td", {},
          h("span", { class: "sandbox-mark", title: t.variant ? "A sandbox variant" : "A sandbox table" }, icon(t.variant ? "branch" : "sandbox")),
          h("strong", {}, t.title),
          h("div", { class: "muted mono" }, t.sql),
          t.origin_words ? h("div", { class: "muted sandbox-origin" }, t.origin_words) : ""),
        h("td", { class: "num" }, t.rows.toLocaleString()),
        h("td", {}, t.source_words, t.mockable ? mockPicker(t, got.mock_choices ?? []) : h("div", { class: "muted" }, clientWords(t.client))),
        h("td", { class: "muted" }, dateTime(t.added_at)),
        h("td", { class: "muted" }, dateTime(t.changed_at)),
        h("td", { class: "muted" }, [t.changes.inserted && `${t.changes.inserted} inserted`, t.changes.updated && `${t.changes.updated} updated`, t.changes.deleted && `${t.changes.deleted} deleted`].filter(Boolean).join(", ")),
        h("td", { class: "sandbox-actions" },
          button("Open in Grids", busyClick("Opening…", (b) => act(b, "/sandbox/tables/open", { table: t.name }, "")), { icon: "rows" }),
          button("New endpoint", () => void newEndpoint(t.name), { icon: "plus", title: `New endpoint over ${t.name}: the wizard` }),
          button(`Reset ${t.name}`, busyClick("Resetting…", (b) => act(b, "/sandbox/reset", { table: t.name }, `${t.name} is back to its baseline.`)), { icon: "reset", iconOnly: true, title: `Reset ${t.name} alone` }),
          button(`Remove ${t.name}`, busyClick("Removing…", (b) => act(b, "/sandbox/tables/remove", { table: t.name }, `${t.name} is out of the sandbox.`)), { icon: "trash", iconOnly: true, title: `Remove ${t.name}` }),
        ),
      ),
    );
    const points = got.checkpoints.map((c) =>
      h("li", {}, h("span", {}, c.name), h("span", { class: "muted" }, ` ${new Date(c.at).toLocaleString()} `),
        button("Restore", busyClick("Restoring…", (b) => act(b, "/sandbox/checkpoints/restore", { name: c.name }, `Restored ${c.name}.`))),
        button("Delete", busyClick("Deleting…", (b) => act(b, "/sandbox/checkpoints", { name: c.name, action: "delete" }, "")), { icon: "trash", iconOnly: true, title: `Delete ${c.name}` }),
      ),
    );
    panel.replaceChildren(
      head,
      got.tables.length
        ? h("table", { class: "sandbox-tables" }, h("thead", {}, h("tr", {}, ...heads(sort, order), h("th", {}, "Changes"), h("th", {}, ""))), h("tbody", {}, ...rows))
        : h("p", { class: "empty-note" }, "No tables yet: Add table…, or Add to sandbox on a grid's Table row."),
      points.length ? h("div", { class: "sandbox-checkpoints" }, h("h3", {}, "Checkpoints"), h("ul", {}, ...points)) : "",
    );
  };
  /** The sortable headings: a click sorts by it; again, the other way. */
  const heads = (sort: string, order: string): HTMLElement[] =>
    [["name", "Table"], ["rows", "Rows"], ["source", "From"], ["created", "Created"], ["changed", "Last changed"]].map(([key, words]) => {
      const on = key === sort;
      const th = h("th", { "aria-sort": on ? (order === "desc" ? "descending" : "ascending") : "none" },
        h("button", { class: `sandbox-sort${on ? " on" : ""}`, type: "button", title: `Sort by ${words!.toLowerCase()}` }, words!, on ? icon(order === "desc" ? "sortdown" : "sortup") : ""));
      th.querySelector("button")!.addEventListener("click", () => {
        remember(SORT_KEY, `${key} ${on && order === "asc" ? "desc" : "asc"}`);
        void draw();
      });
      return th;
    });
  const mockPicker = (t: SandboxTable, choices: string[]): HTMLElement => {
    const pick = h("select", { "aria-label": `${t.name}: mocked as`, class: "sandbox-mock" },
      h("option", { value: "" }, "Plain DuckDB client"),
      ...choices.map((c) => h("option", { value: c, selected: t.mocked && t.client.connection === c }, `Mocked as ${c}`))) as HTMLSelectElement;
    pick.addEventListener("change", async () => {
      try {
        await api("/sandbox/tables/mock", "POST", { table: t.name, connection: pick.value || null });
        await draw();
      } catch (e) {
        errorHere(e, {}, pick);
      }
    });
    return h("div", { class: "sandbox-mocked" }, pick);
  };
  const act = async (b: HTMLElement, path: string, body: unknown, said: string): Promise<void> => {
    try {
      await api(path, "POST", body);
      if (said) toast(said);
      await draw();
    } catch (e) {
      errorHere(e, {}, b);
    }
  };
  const saveCheckpoint = (): void => {
    const { body, foot, close } = openDialog("Save checkpoint");
    const name = h("input", { "aria-label": "Checkpoint name", value: `Checkpoint ${new Date().toLocaleTimeString()}`.replace(/:/g, ".") }) as HTMLInputElement;
    body.append(name);
    foot.append(button("Cancel", () => close()), button("Save", busyClick("Saving…", async (b) => {
      try {
        await api("/sandbox/checkpoints", "POST", { name: name.value.trim(), action: "save" });
        close();
        await draw();
      } catch (e) {
        errorHere(e, {}, b);
      }
    }), { class: "primary" }));
    name.select();
  };
  panel.append(loadingBlock("Reading the sandbox…"));
  void draw();
  let timer = 0;
  onNoticeWhile(panel, (n) => {
    if (n.type !== "sandbox_changed" && n.type !== "project_changed") return;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => void draw(), 150);
  });
  return panel;
}


/** Add table…: an open table, a file, or an empty table by its columns. */
function chooseSource(added: () => void): void {
  const { body, foot, close } = openDialog("Add a table to the sandbox", true);
  const kind = h("select", { "aria-label": "From" },
    h("option", { value: "grid" }, "An open table (its view, after its steps)"),
    h("option", { value: "file" }, "A file (CSV, Excel, Parquet, JSON)"),
    h("option", { value: "columns" }, "An empty table, by its columns"),
  ) as HTMLSelectElement;
  const name = h("input", { "aria-label": "Its name in the sandbox", placeholder: "orders", spellcheck: false }) as HTMLInputElement;
  const table = h("input", { "aria-label": "The open table", placeholder: "The open table's name" }) as HTMLInputElement;
  let path = "";
  const pathWords = h("span", { class: "muted mono" });
  const pick = button("Choose file…", async () => {
    const chosen = await chooseFile({ title: "A table's file", mode: "file", suffixes: [".csv", ".xlsx", ".parquet", ".json"] });
    if (chosen) {
      path = chosen;
      pathWords.textContent = chosen;
    }
  });
  const columns = h("textarea", { "aria-label": "Columns", rows: 4, placeholder: "id integer key\nnote text\nwhen date", spellcheck: false }) as HTMLTextAreaElement;
  const parts = { grid: h("div", { class: "field" }, table), file: h("div", { class: "field" }, pick, pathWords), columns: h("div", { class: "field" }, columns) };
  const show = (): void => {
    for (const [k, el] of Object.entries(parts)) el.hidden = k !== kind.value;
  };
  kind.addEventListener("change", show);
  body.append(h("label", { class: "field" }, h("span", {}, "From"), kind), ...Object.values(parts), h("label", { class: "field" }, h("span", {}, "Its name in the sandbox"), name));
  show();
  foot.append(button("Cancel", () => close()), button("Add", busyClick("Adding…", async (b) => {
    const given: Record<string, unknown> = { from: kind.value, name: name.value.trim() || undefined };
    if (kind.value === "grid") given.table = table.value.trim();
    if (kind.value === "file") given.path = path;
    if (kind.value === "columns") {
      given.columns = columns.value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
        const [n, t, k] = l.split(/\s+/);
        return { name: n, type: t ?? "text", key: k === "key" };
      });
    }
    try {
      await busy(body, "Adding the table…", api("/sandbox/tables", "POST", given));
      close();
      added();
    } catch (e) {
      errorHere(e, {}, b);
    }
  }), { class: "primary" }));
}
