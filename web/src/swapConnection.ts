/**
 * swapConnection.ts: a table's connection swapped for another (the owner, 2026-11-16: "we also need button
 * the the table row to swap a tables connection ... I deleted the edp but need its queries to run on the
 * other"). The rules and the reading again are the server's (services/connection_swap.py). [WIRE]
 *
 *   [TABLE ROW]   Connection: <its connection> -> openConnectionChooser(table): the other connections
 *   [CHOOSER]     a connection -> POST /tables/{t}/connection: swapped (Undo in a toast and on the strip),
 *                 or pick (its candidates, the other's catalog tree, Write a query…), or review (the
 *                 SQL window)
 *   [SQL WINDOW]  ?panel=connsql&to=Trino&table=a&table=b: each query looked over, then run on `to`; Skip;
 *                 Run all as they are
 *   [THE STRIP]   a table waiting for a deleted connection: Use another connection… -> openMoveChooser:
 *                 every table of that connection moved at once (POST /connections/{c}/move)
 *   [THE CODE]    after a swap or a move: the cells that named the old connection, each ticked: Point
 *                 these at <new> (POST /connections/{c}/repoint)
 */
import { api, onNotice } from "./api";
import { append, button, clear, h, icon, openDialog, toast } from "./dom";

export interface TableConnection {
  table: string;
  connection: string | null;
  exists: boolean;
  how: string;
  place: Place | null;
  sql: string | null;
  open: boolean;
  others: string[];
  undo: boolean;
  undo_connection: string | null;
}

interface Place {
  database: string;
  schema: string;
  table: string;
}

interface Pick {
  table: string;
  to: string;
  from: string | null;
  was: Place;
  candidates: Place[];
  schemas: { database: string; schema: string; tables: number }[];
  sql: string;
}

interface Swapped {
  table: string;
  from: string | null;
  to: string;
  steps_problems: string[];
}

interface Answer {
  swapped?: Swapped;
  review?: { table: string; to: string; from: string | null; sql: string };
  pick?: Pick;
  failed?: string;
}

interface Reference {
  document: string;
  title: string;
  kind: string;
  how: string;
  line: string;
  cell: number | null;
  name?: string;
  pickable: boolean;
}

const known = new Map<string, TableConnection>();
const listeners: (() => void)[] = [];
/** The swaps made from this page, for the strip's Undo (until undone, or dismissed). */
let recent: Swapped[] = [];

const enc = encodeURIComponent;
const changed = (): void => listeners.forEach((l) => l());

/** Who redraws when a table's connection is known, or a swap changed it (the ribbon, the strip). */
export function onConnectionChange(listener: () => void): void {
  listeners.push(listener);
}

onNotice((notice) => {
  if (notice.type === "table_connection" || notice.type === "dataset_renamed" || notice.type === "dataset_closed") {
    if (notice.dataset) known.delete(notice.dataset);
    changed();
  }
});

async function load(table: string): Promise<TableConnection> {
  const state = await api<TableConnection>(`/tables/${enc(table)}/connection`);
  known.set(table, state);
  return state;
}

/** The Table row's button: the table's connection by name (fetched once, then followed). */
export function connectionLabel(table: string): string {
  const state = known.get(table);
  if (!state) {
    void load(table).then(changed).catch(() => undefined);
    return "Connection…";
  }
  if (!state.connection) return state.how === "query" ? "Connection: Query" : "Connection…";
  return `Connection: ${state.connection}`;
}

export function recentSwaps(): Swapped[] {
  return recent;
}

export function forgetSwap(table: string): void {
  recent = recent.filter((s) => s.table !== table);
  changed();
}

export async function undoSwap(table: string): Promise<void> {
  try {
    await api(`/tables/${enc(table)}/connection/undo`, "POST", {});
  } catch (e) {
    toast((e as Error).message, "error");
  }
  forgetSwap(table);
}

function swappedDone(done: Swapped): void {
  recent = [...recent.filter((s) => s.table !== done.table), done];
  known.delete(done.table);
  changed();
  toast(`${done.table}: ${done.to}`, "info", { label: "Undo", run: () => void undoSwap(done.table) });
  for (const problem of done.steps_problems) toast(`${done.table}: ${problem}`, "error");
}

/** The SQL window: the queries of `tables` looked over, then run on `to`. */
export function openSqlWindow(to: string, tables: string[], sql?: string): void {
  const at = new URL("/workspace", location.origin);
  at.searchParams.set("panel", "connsql");
  at.searchParams.set("to", to);
  for (const t of tables) at.searchParams.append("table", t);
  if (sql) at.searchParams.set("sql", sql);
  const opened = window.open(`${at.pathname}${at.search}`, "sab-connsql", "popup,width=960,height=680");
  if (opened) opened.focus();
  else toast("The browser blocked the SQL window: allow pop-ups for this address.", "error");
}

async function swap(table: string, body: Record<string, unknown>, close: () => void, host: HTMLElement): Promise<void> {
  let answer: Answer;
  try {
    answer = await api<Answer>(`/tables/${enc(table)}/connection`, "POST", body);
  } catch (e) {
    toast((e as Error).message, "error");
    return;
  }
  const to = String(body.to);
  if (answer.swapped) {
    close();
    swappedDone(answer.swapped);
    await offerRepoint(answer.swapped.from, to);
  } else if (answer.review) {
    close();
    openSqlWindow(to, [table]);
    await offerRepoint(answer.review.from, to);
  } else if (answer.pick) {
    drawPick(answer.pick, host, close);
  } else if (answer.failed) {
    toast(answer.failed, "error");
  }
}

function placeWords(p: Place): string {
  return [p.database, p.schema, p.table].filter(Boolean).join(".");
}

/** The other connection's tables to choose from: the ones of that name, then its catalog tree. */
function drawPick(pick: Pick, host: HTMLElement, close: () => void): void {
  const choose = (place: Place): void => void swap(pick.table, { to: pick.to, place }, close, host);
  const tree = h("ul", { class: "swap-tree", "aria-label": `${pick.to} catalog` });
  for (const schema of pick.schemas) {
    const branch = h("li", {});
    const tables = h("ul", { class: "swap-tables" });
    const label = [schema.database, schema.schema].filter(Boolean).join(".") || pick.to;
    const toggle = button(label, async () => {
      if (tables.childElementCount) {
        clear(tables);
        return;
      }
      const params = new URLSearchParams({ schema: schema.schema, limit: "500" });
      if (schema.database) params.set("database", schema.database);
      try {
        const found = await api<{ tables: Place[] }>(`/catalogs/${enc(pick.to)}/tables?${params}`);
        clear(tables, ...found.tables.map((t) => h("li", {}, button(t.table, () => choose(t), { icon: "table", class: "ghost" }))));
      } catch (e) {
        toast((e as Error).message, "error");
      }
    }, { icon: "schema", class: "ghost" });
    branch.append(toggle, tables);
    tree.append(branch);
  }
  clear(
    host,
    h("p", { class: "swap-was" }, icon("exclude"), h("strong", {}, placeWords(pick.was)), h("span", {}, ` · ${pick.to}`)),
    pick.candidates.length
      ? h("div", { class: "swap-candidates" }, ...pick.candidates.map((c) => button(placeWords(c), () => choose(c), { icon: "table" })))
      : null,
    tree,
    h("div", { class: "row-actions" }, button("Write a query…", () => {
      close();
      openSqlWindow(pick.to, [pick.table], pick.sql);
    }, { icon: "sql", class: "ghost" })),
  );
}

/** The Table row's Connection…: the table's connection, the others to move it to, its undo. */
export async function openConnectionChooser(table: string): Promise<void> {
  let state: TableConnection;
  try {
    state = await load(table);
  } catch (e) {
    toast((e as Error).message, "error");
    return;
  }
  const { body, foot, close } = openDialog(`Connection: ${table}`);
  body.classList.add("swap-chooser");
  const current = state.connection
    ? h("p", { class: `swap-current${state.exists ? "" : " missing"}` }, icon("sql"), h("strong", {}, state.connection), state.exists ? null : h("span", { class: "swap-missing" }, "deleted"))
    : h("p", { class: "swap-current" }, icon(state.how === "query" ? "sql" : "rows"), h("strong", {}, state.how === "query" ? "Query" : table));
  const list = h(
    "div",
    { class: "swap-others", role: "list" },
    ...state.others.map((name) => h("div", { role: "listitem" }, button(name, () => void swap(table, { to: name }, close, body), { icon: "sql", class: "swap-other" }))),
  );
  clear(body, current, state.others.length ? list : h("p", { class: "empty-note" }, "No other connections"));
  if (state.undo) foot.append(button(`Undo (${state.undo_connection ?? "back"})`, () => {
    close();
    void undoSwap(table);
  }, { icon: "undo", class: "ghost" }));
}

/** The strip's Use another connection…: every table of a (deleted) connection moved at once. */
export async function openMoveChooser(from: string): Promise<void> {
  let names: string[];
  try {
    const listed = await api<{ connections: { name: string; connection: string }[] }>("/connections");
    names = listed.connections.filter((c) => (c.connection === "database" || c.connection === "python") && c.name.toLowerCase() !== from.toLowerCase()).map((c) => c.name);
  } catch (e) {
    toast((e as Error).message, "error");
    return;
  }
  const { body, close } = openDialog(`Use another connection for ${from}`);
  body.classList.add("swap-chooser");
  const move = async (to: string, asIs: boolean): Promise<void> => {
    let answer: { moved: Swapped[]; review: { table: string }[]; pick: Pick[]; failed: { table: string; error: string }[] };
    try {
      answer = await api(`/connections/${enc(from)}/move`, "POST", { to, run_as_is: asIs });
    } catch (e) {
      toast((e as Error).message, "error");
      return;
    }
    for (const done of answer.moved) swappedDone(done);
    for (const failed of answer.failed) toast(`${failed.table}: ${failed.error}`, "error");
    if (!answer.review.length && !answer.pick.length) {
      close();
      await offerRepoint(from, to);
      return;
    }
    // Queries to look over, and tables to pick: one by one.
    const queries = answer.review.map((r) => r.table);
    clear(
      body,
      queries.length
        ? h(
            "div",
            { class: "swap-review" },
            h("p", {}, icon("sql"), h("strong", {}, queries.join(", "))),
            h("div", { class: "row-actions" },
              button("Review…", () => openSqlWindow(to, queries), { icon: "sql", class: "primary" }),
              button("Run as they are", () => void move(to, true), { icon: "play" })),
          )
        : null,
      ...answer.pick.map((pick) => {
        const host = h("div", { class: "swap-pick" });
        drawPick(pick, host, () => host.remove());
        return host;
      }),
      h("div", { class: "row-actions" }, button("Point the code…", () => void offerRepoint(from, to, true), { icon: "code", class: "ghost" })),
    );
  };
  clear(
    body,
    h("p", { class: "swap-current missing" }, icon("sql"), h("strong", {}, from)),
    names.length
      ? h("div", { class: "swap-others", role: "list" }, ...names.map((name) => h("div", { role: "listitem" }, button(name, () => void move(name, false), { icon: "sql", class: "swap-other" }))))
      : h("p", { class: "empty-note" }, "No other connections"),
  );
}

/** The cells that named the old connection, each ticked: Point these at the new one. Shown only when
 *  there are some (`always`: say so when there are none). */
export async function offerRepoint(from: string | null, to: string, always = false): Promise<void> {
  if (!from || from.toLowerCase() === to.toLowerCase()) return;
  let refs: Reference[];
  try {
    refs = (await api<{ references: Reference[] }>(`/connections/${enc(from)}/references`)).references.filter((r) => r.pickable);
  } catch {
    return;
  }
  if (!refs.length) {
    if (always) toast(`No cells name ${from}`);
    return;
  }
  const { body, foot, close } = openDialog(`Point these at ${to}`, true);
  body.classList.add("swap-repoint");
  const boxes = refs.map((ref) => {
    const box = h("input", { type: "checkbox", checked: true, "aria-label": `${ref.title} cell ${ref.cell ?? ""}` }) as HTMLInputElement;
    const row = h(
      "label",
      { class: "swap-ref" },
      box,
      icon(ref.kind === "script" ? "code" : "notebook"),
      h("strong", {}, ref.title),
      ref.cell !== null ? h("span", { class: "swap-ref-cell" }, `@cell${ref.cell}`) : null,
      ref.name ? h("span", { class: "swap-ref-name" }, ref.name) : null,
      h("code", {}, ref.line),
    );
    return { ref, box, row };
  });
  clear(body, ...boxes.map((b) => b.row));
  foot.append(
    button(`Point these at ${to}`, async () => {
      const picks = boxes.filter((b) => b.box.checked).map((b) => ({ document: b.ref.document, cell: b.ref.cell }));
      if (!picks.length) {
        close();
        return;
      }
      try {
        const done = await api<{ cells: number; failed: { document: string; error: string }[] }>(`/connections/${enc(from)}/repoint`, "POST", { to, picks });
        for (const failed of done.failed) toast(`${failed.document}: ${failed.error}`, "error");
        toast(`${done.cells} ${done.cells === 1 ? "cell" : "cells"}: ${to}`);
      } catch (e) {
        toast((e as Error).message, "error");
        return;
      }
      close();
    }, { icon: "code", class: "primary" }),
  );
}

// ===== the SQL window (?panel=connsql) =====

/** Each table's query in a window of its own, as big as the user likes: looked over, then run on `to`. */
export async function mountConnectionSqlWindow(): Promise<void> {
  const params = new URLSearchParams(location.search);
  const to = params.get("to") ?? "";
  const queue = params.getAll("table");
  const given = params.get("sql");
  document.title = `${to} · SQL`;
  for (const selector of [".tabbar", ".titlebar", ".app-row", ".ribbon", ".workspace", ".statusbar"]) document.querySelector(selector)?.remove();
  document.body.classList.add("sql-window");
  const queryOf = async (table: string): Promise<string> => {
    if (given && queue.length === 1) return given;
    try {
      return (await api<TableConnection>(`/tables/${enc(table)}/connection`)).sql ?? "";
    } catch {
      return "";
    }
  };
  const next = async (): Promise<void> => {
    const table = queue.shift();
    if (table === undefined) {
      window.close();
      return;
    }
    const { dialog, body, foot } = openDialog(`${table} · ${to}`, true, { history: false });
    const box = h("textarea", { class: "code-input", rows: "16", spellcheck: "false", "aria-label": "SQL", style: { width: "100%", fontFamily: '"Cascadia Code", Consolas, monospace' } }) as HTMLTextAreaElement;
    box.value = await queryOf(table);
    clear(body, h("div", { class: "form-grid", style: { gridTemplateColumns: "1fr" } }, box));
    let moved = false;
    const advance = (): void => {
      moved = true;
      dialog.close();
      void next();
    };
    // Closed with its own X or Escape: the window goes with it.
    dialog.addEventListener("close", () => {
      if (!moved) window.close();
    });
    const run = async (table_: string, sql: string): Promise<boolean> => {
      try {
        const answer = await api<Answer>(`/tables/${enc(table_)}/connection`, "POST", { to, sql });
        if (answer.failed) throw new Error(answer.failed);
        for (const problem of answer.swapped?.steps_problems ?? []) toast(`${table_}: ${problem}`, "error");
        return true;
      } catch (e) {
        toast(`${table_}: ${(e as Error).message}`, "error");
        return false;
      }
    };
    append(
      foot,
      button(`Run on ${to}`, async () => {
        if (await run(table, box.value)) advance();
      }, { icon: "play", class: "primary" }),
      queue.length
        ? button("Run all as they are", async () => {
            if (!(await run(table, box.value))) return;
            while (queue.length) {
              const other = queue.shift()!;
              await run(other, await queryOf(other));
            }
            moved = true;
            window.close();
          }, { icon: "play" })
        : null,
      button(queue.length ? "Skip" : "Cancel", advance, { class: "ghost" }),
    );
    box.focus();
  };
  await next();
}
