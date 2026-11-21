/**
 * queriesWindow.ts: the Queries window (?panel=queries&connection=<name>), a window of its own per connection
 * or every connection's (the owner, 2026-11-21: "a robust standalone popout panel in the connection to show
 * queries that are in progress").
 *
 *   [HEADER]    the connection (or All connections), "Running 3 of 8 · 1 waiting · agent 2 of 4", its limits
 *   [LIST]      each running or waiting query: connection, who, what and its tables, Waiting (its place) or
 *               Running, started, elapsed (ticking), rows; Cancel, Open its source. Arrows move, Enter
 *               opens, Delete cancels (asked first). Past 200 rows only the visible ones are drawn.
 *   [SQL]       the opened query's SQL formatted for reading (the server's, the user's only) in Monaco's
 *               read-only SQL (line numbers, sized to it up to half the window); Copy, Copy as written,
 *               Open in a new query. Nothing loads for a row that is not opened.
 *   [FINISHED]  this session's last 50: time taken, rows, OK / Cancelled / Failed and why; Clear
 *
 * Live through the live socket's `connection_slots` notice (the list asked again, never polled); a closed and
 * reopened window shows the state at once. A restart is said: "The app restarted: these queries ended."
 */

import { api, connect, onNotice } from "./api";
import { limitsForm, type SlotStatus } from "./connectionSlots";
import { button, clear, h, icon, toast } from "./dom";
import { errorHere } from "./errorNote";
import type { EditorLanguage } from "./lazy/codeEditor";
import { effectiveTheme } from "./theme";

interface Query {
  id: string;
  connection: string;
  caller: string;
  who: string;
  kind: string;
  what: string;
  targets: string[];
  state: "running" | "waiting";
  queued_at: number;
  started_at: number | null;
  elapsed: number;
  source: { kernel?: string; document?: string; cell?: number | string };
  has_sql: boolean;
  place?: number;
  words?: string;
  rows?: number;
}

interface Finished {
  id: string;
  connection: string;
  who: string;
  what: string;
  targets: string[];
  outcome: string;
  reason: string;
  ended_at: number;
  seconds: number;
  rows?: number;
  has_sql: boolean;
}

interface Listing {
  queries: Query[];
  finished: Finished[];
  connections: SlotStatus[];
  started: string;
  now: number;
}

interface Sql {
  id: string;
  connection: string;
  sql: string;
  formatted: string;
  language: string;
}

const ROW_HEIGHT = 34;
const VIRTUAL_PAST = 200;
const OUTCOMES: Record<string, string> = { ok: "OK", cancelled: "Cancelled", failed: "Failed", "timed out": "Timed out", ended: "Ended" };

function ordinal(n: number): string {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} min ${s % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

const at = (epoch: number): string => new Date(epoch * 1000).toLocaleTimeString();

let editors: Promise<typeof import("./lazy/codeEditor")> | null = null;
function loadEditors(): Promise<typeof import("./lazy/codeEditor")> {
  if (!document.querySelector('link[href="/static/build/lazy/codeEditor.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/build/lazy/codeEditor.css" }));
  }
  return (editors ??= import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>);
}

export async function mountQueriesWindow(): Promise<void> {
  const params = new URLSearchParams(location.search);
  let connection = params.get("connection") || null;
  for (const selector of [".tabbar", ".titlebar", ".app-row", ".ribbon", ".workspace", ".statusbar", "#steps-panel"]) document.querySelector(selector)?.remove();
  document.body.classList.add("queries-window");

  let listing: Listing = { queries: [], finished: [], connections: [], started: "", now: Date.now() / 1000 };
  let offset = 0; // the server's clock less this page's (elapsed ticks here)
  let selected: string | null = null;
  let opened: string | null = null;
  let restarted = false;
  let shownStart = "";
  let sqlEditor: { dispose: () => void } | null = null;

  const picker = h("select", { class: "queries-connection", "aria-label": "Connection" }) as HTMLSelectElement;
  const counts = h("span", { class: "queries-counts", role: "status" });
  const limitsHost = h("div", { class: "queries-limits" });
  const note = h("div", { class: "queries-note", hidden: true });
  const list = h("div", { class: "queries-list", role: "grid", tabindex: "0", "aria-label": "Queries in progress" });
  const spacer = h("div", { class: "queries-spacer" });
  const rows = h("div", { class: "queries-rows" });
  list.append(spacer, rows);
  const empty = h("p", { class: "queries-empty" }, "No query is running or waiting.");
  const sqlPane = h("section", { class: "queries-sql", "aria-label": "SQL", hidden: true });
  const finishedRows = h("tbody", {});
  const finished = h(
    "section",
    { class: "queries-finished", "aria-label": "Finished" },
    h("div", { class: "queries-finished-head" }, h("h2", {}, icon("history"), "Finished"), button("Clear", () => void api("/connections/queries/clear", "POST", {}).then(refresh, (e: unknown) => errorHere(e)), { icon: "clean", class: "ghost" })),
    h("table", { class: "queries-finished-table" }, h("thead", {}, h("tr", {}, ...["Connection", "Who", "What", "Result", "Took", "Rows", "Ended"].map((t) => h("th", {}, t)))), finishedRows),
  );
  const head = h("tr", { class: "queries-head", role: "row" }, ...["Connection", "Who", "What", "State", "Started", "Elapsed", "Rows", ""].map((t) => h("th", { role: "columnheader" }, t)));
  document.body.append(
    h(
      "main",
      { class: "queries-main" },
      h("header", { class: "queries-top" }, h("h1", {}, icon("rows"), "Queries"), picker, counts, limitsHost),
      note,
      h("table", { class: "queries-header-table", "aria-hidden": "true" }, h("thead", {}, head)),
      list,
      empty,
      sqlPane,
      finished,
    ),
  );

  const title = (): void => {
    document.title = `${connection ?? "All connections"} · Queries`;
  };
  const shown = (): Query[] => listing.queries.filter((q) => !connection || q.connection.toLocaleLowerCase() === connection.toLocaleLowerCase());

  const fillPicker = async (): Promise<void> => {
    let names: string[] = [];
    try {
      names = (await api<{ connections: SlotStatus[] }>("/connections/slots")).connections.map((c) => c.connection);
    } catch {
      /* the listing says it */
    }
    if (connection && !names.some((n) => n.toLocaleLowerCase() === connection!.toLocaleLowerCase())) names.unshift(connection);
    clear(picker, h("option", { value: "" }, "All connections"), ...names.map((n) => h("option", { value: n }, n)));
    picker.value = connection ?? "";
  };
  picker.addEventListener("change", () => {
    connection = picker.value || null;
    const url = new URL(location.href);
    if (connection) url.searchParams.set("connection", connection);
    else url.searchParams.delete("connection");
    history.replaceState(history.state, "", url.pathname + url.search + url.hash);
    title();
    drawLimits();
    draw();
  });

  const drawLimits = (): void => {
    clear(limitsHost, connection ? limitsForm(connection, true) : null);
  };

  const countWords = (): string => {
    if (connection) {
      const s = listing.connections.find((c) => c.connection.toLocaleLowerCase() === connection!.toLocaleLowerCase());
      return s ? s.full_words : "Running 0";
    }
    const running = listing.queries.filter((q) => q.state === "running").length;
    const waiting = listing.queries.length - running;
    const agent = listing.queries.filter((q) => q.state === "running" && q.caller === "agent").length;
    return `Running ${running}${waiting ? ` · ${waiting} waiting` : ""} · agent ${agent}`;
  };

  const stateWords = (q: Query): string => (q.state === "waiting" ? `Waiting · ${ordinal(q.place ?? 1)} in line` : "Running");
  const elapsedOf = (q: Query): number => Date.now() / 1000 + offset - (q.started_at ?? q.queued_at);

  const cancel = async (q: Query): Promise<void> => {
    try {
      await api(`/connections/queries/${encodeURIComponent(q.id)}/cancel`, "POST", {});
    } catch (e) {
      errorHere(e, { where: q.connection });
    }
  };

  const openSource = (q: Query): void => {
    if (q.source.document) {
      window.open(`/workbench?file=${encodeURIComponent(q.source.document)}${location.hash}`, "sab-workbench");
      return;
    }
    void api("/navigate", "POST", { to: "grids" }).catch(() => undefined); // the page that asked: the home window
  };

  const row = (q: Query, index: number): HTMLElement => {
    const elapsed = h("td", { class: "queries-elapsed" }, clock(elapsedOf(q)));
    elapsed.dataset.since = String(q.started_at ?? q.queued_at);
    const tr = h(
      "tr",
      {
        class: `queries-row st-${q.state}${q.id === selected ? " selected" : ""}${q.id === opened ? " opened" : ""}`,
        role: "row",
        "data-id": q.id,
        "data-connections": q.connection,
        "aria-selected": String(q.id === selected),
        style: { height: `${ROW_HEIGHT}px` },
        onclick: () => {
          selected = q.id;
          toggle(q);
        },
      },
      h("td", { class: "queries-connection-name" }, q.connection),
      h("td", { class: `queries-who who-${q.caller}` }, q.who),
      h("td", { class: "queries-what" }, q.what, q.targets.length ? h("span", { class: "queries-targets" }, q.targets.join(", ")) : null),
      h("td", { class: "queries-state", title: q.words ?? "" }, stateWords(q)),
      h("td", {}, q.started_at ? at(q.started_at) : "—"),
      elapsed,
      h("td", { class: "queries-rows-read" }, q.rows === undefined ? "" : q.rows.toLocaleString()),
      h(
        "td",
        { class: "queries-actions" },
        button("Cancel", (e) => {
          e.stopPropagation();
          void cancel(q);
        }, { icon: "stop", class: "ghost queries-cancel" }),
        button("Open its source", (e) => {
          e.stopPropagation();
          openSource(q);
        }, { icon: "forward", iconOnly: true, class: "ghost" }),
      ),
    );
    tr.dataset.index = String(index);
    return tr;
  };

  /** Only the rows in view, past VIRTUAL_PAST (each row a fixed height); every row before that. */
  const drawRows = (): void => {
    const all = shown();
    list.classList.toggle("virtual", all.length > VIRTUAL_PAST);
    if (all.length <= VIRTUAL_PAST) {
      spacer.style.height = "0px";
      rows.style.transform = "";
      clear(rows, h("table", { class: "queries-table" }, h("tbody", {}, ...all.map(row))));
      return;
    }
    const first = Math.max(0, Math.floor(list.scrollTop / ROW_HEIGHT) - 10);
    const count = Math.ceil(list.clientHeight / ROW_HEIGHT) + 20;
    spacer.style.height = `${all.length * ROW_HEIGHT}px`;
    rows.style.transform = `translateY(${first * ROW_HEIGHT}px)`;
    clear(rows, h("table", { class: "queries-table" }, h("tbody", {}, ...all.slice(first, first + count).map((q, i) => row(q, first + i)))));
  };
  list.addEventListener("scroll", () => {
    if (shown().length > VIRTUAL_PAST) requestAnimationFrame(drawRows);
  });

  const drawFinished = (): void => {
    const done = listing.finished.filter((f) => !connection || f.connection.toLocaleLowerCase() === connection.toLocaleLowerCase());
    clear(
      finishedRows,
      ...done.map((f) =>
        h(
          "tr",
          { class: `queries-done out-${f.outcome.replace(" ", "-")}`, "data-id": f.id },
          h("td", {}, f.connection),
          h("td", {}, f.who),
          h("td", {}, f.what, f.targets.length ? h("span", { class: "queries-targets" }, f.targets.join(", ")) : null),
          h("td", { class: "queries-outcome", title: f.reason }, OUTCOMES[f.outcome] ?? f.outcome, f.reason ? h("span", { class: "queries-reason" }, f.reason) : null),
          h("td", {}, clock(f.seconds)),
          h("td", {}, f.rows === undefined ? "" : f.rows.toLocaleString()),
          h("td", {}, at(f.ended_at)),
        ),
      ),
    );
    finished.hidden = done.length === 0;
  };

  const draw = (): void => {
    counts.textContent = countWords();
    const all = shown();
    empty.hidden = all.length > 0;
    list.hidden = all.length === 0;
    if (selected && !all.some((q) => q.id === selected)) selected = all[0]?.id ?? null;
    drawRows();
    drawFinished();
  };

  /** The opened query's SQL, as the server formatted it, in Monaco's read-only SQL (asked only when opened). */
  const toggle = (q: Query): void => {
    if (opened === q.id) {
      opened = null;
      sqlEditor?.dispose();
      sqlEditor = null;
      sqlPane.hidden = true;
      draw();
      return;
    }
    opened = q.id;
    draw();
    void showSql(q);
  };

  const showSql = async (q: { id: string; connection: string; has_sql: boolean }): Promise<void> => {
    sqlEditor?.dispose();
    sqlEditor = null;
    sqlPane.hidden = false;
    const heading = h("h2", {}, icon("sql"), q.connection);
    if (!q.has_sql) {
      clear(sqlPane, heading, h("p", { class: "queries-empty" }, "No SQL text: a catalog listing, a test or a connect."));
      return;
    }
    let found: Sql;
    try {
      found = await api<Sql>(`/connections/queries/${encodeURIComponent(q.id)}/sql`);
    } catch (e) {
      clear(sqlPane, heading);
      errorHere(e, { where: q.connection }, sqlPane);
      return;
    }
    if (opened !== q.id) return;
    const host = h("div", { class: "queries-sql-box", "data-language": found.language }, h("pre", { class: "code-box" }, found.formatted));
    const copy = (text: string): void => void navigator.clipboard.writeText(text).then(() => toast("Copied"));
    clear(
      sqlPane,
      h(
        "div",
        { class: "queries-sql-head" },
        heading,
        button("Copy", () => copy(found.formatted), { icon: "copy" }),
        button("Copy as written", () => copy(found.sql), { icon: "copy", class: "ghost" }),
        button("Open in a new query", () => void api("/navigate", "POST", { to: `query:${found.connection}` }).catch((e: unknown) => errorHere(e)), { icon: "plus", class: "ghost" }),
      ),
      host,
    );
    try {
      const m = await loadEditors();
      if (opened !== q.id || !host.isConnected) return;
      const box = h("div", { class: "queries-sql-monaco" });
      host.replaceChildren(box);
      sqlEditor = m.createCodeEditor(box, {
        language: (found.language === "dax" ? "dax" : "sql") as EditorLanguage,
        value: found.formatted,
        theme: effectiveTheme(),
        readOnly: true,
        readOnlyMessage: "A query's SQL is shown as it ran.",
        fit: { min: 3, maxShare: 0.45 },
      });
    } catch {
      /* the plain box stays */
    }
  };

  // ===== the keys: arrows move, Enter opens, Delete cancels (asked first) =====
  list.addEventListener("keydown", (e: KeyboardEvent) => {
    const all = shown();
    if (!all.length) return;
    let index = Math.max(0, all.findIndex((q) => q.id === selected));
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      index = Math.min(all.length - 1, Math.max(0, index + (e.key === "ArrowDown" ? 1 : -1)));
      selected = all[index]!.id;
      const top = index * ROW_HEIGHT;
      if (top < list.scrollTop) list.scrollTop = top;
      else if (top + ROW_HEIGHT > list.scrollTop + list.clientHeight) list.scrollTop = top + ROW_HEIGHT - list.clientHeight;
      draw();
    } else if (e.key === "Enter") {
      e.preventDefault();
      const q = all[index];
      if (q) toggle(q);
    } else if (e.key === "Delete") {
      e.preventDefault();
      const q = all[index];
      if (q && confirm(`Cancel ${q.who}'s ${q.what} on ${q.connection}?`)) void cancel(q);
    }
  });

  // ===== live: the notice asks again (never a poll); the elapsed time ticks here =====
  let asking: Promise<void> | null = null;
  let again = false;
  const refresh = async (): Promise<void> => {
    if (asking) {
      again = true;
      return asking;
    }
    asking = (async () => {
      try {
        const got = await api<Listing>("/connections/queries");
        offset = got.now - Date.now() / 1000;
        if (shownStart && got.started !== shownStart && listing.queries.length) {
          // The app restarted: what this window showed running or waiting ended with it.
          restarted = true;
          const ended = listing.queries.map((q): Finished => ({ id: q.id, connection: q.connection, who: q.who, what: q.what, targets: q.targets, outcome: "ended", reason: "the app restarted", ended_at: got.now, seconds: elapsedOf(q), has_sql: false }));
          got.finished = [...ended, ...got.finished];
        }
        shownStart = got.started;
        listing = got;
        note.hidden = !restarted;
        note.textContent = restarted ? "The app restarted: these queries ended." : "";
        draw();
      } catch (e) {
        errorHere(e, {}, counts);
      }
    })();
    try {
      await asking;
    } finally {
      asking = null;
      if (again) {
        again = false;
        void refresh();
      }
    }
  };
  onNotice((notice) => {
    if (notice.type === "connection_slots") void refresh();
  });
  window.setInterval(() => {
    for (const cell of document.querySelectorAll<HTMLElement>(".queries-elapsed")) {
      cell.textContent = clock(Date.now() / 1000 + offset - Number(cell.dataset.since));
    }
  }, 1000);

  title();
  drawLimits();
  await fillPicker();
  connect((live, reconnected) => {
    document.body.classList.toggle("offline", !live);
    if (reconnected) void refresh();
  }, { window: "queries" });
  await refresh();
  list.focus();
}
