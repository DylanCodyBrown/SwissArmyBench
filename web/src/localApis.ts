/**
 * localApis.ts: the APIs page's Local sandbox APIs (the owner, 2026-11-21: "Instead of your API just call it local
 * sandbox apis"): the project's API.py, beside the imported APIs. Its endpoints run only against the project's
 * sandbox, through mock clients with the connections' own shape ("No never run against live data ever").
 *
 *   [HEAD]      its name, its target (FastAPI, Azure Functions, AWS Lambda), its base path; Run / Stop, where it
 *               runs; Open API.py (the Scripts page); New local sandbox API… while the project has none
 *   [PROBLEMS]  API.py's problems with their lines (Go to line), a start that failed with its line
 *   [ENDPOINTS] each one: method, path, summary, its data ("Mock of Warehouse (sqlserver)"); Try it: the path's and
 *               the query's boxes, the body prefilled with a made-up example from its model, Send: status, time,
 *               rows and the answer as a tree
 *   [LOG]       the request log while it runs (method, path, status, ms, rows; never a value), kept current
 *   The sandbox's panel (dataSandbox.ts) sits above it: Reset beside the API.
 *
 * ROUTING: GET /local-api · POST /local-api/new, /run, /stop, /call · PUT /local-api/settings · GET /local-api/log
 */
import { api, onNoticeWhile } from "./api";
import { button, h, openDialog, toast } from "./dom";
import { errorHere, errorNote } from "./errorNote";
import { busyClick, loadingBlock } from "./loading";
import { mountTree, type Value } from "./structureTree";
import { openOnPage } from "./workbenchPages";

interface Param { name: string; where: string; type: string; required: boolean; default: Value }
interface Endpoint {
  name: string;
  method: string;
  path: string;
  line: number;
  summary: string;
  params: Param[];
  returns: string;
  data: string[];
  writes: boolean;
}
interface State {
  project: string | null;
  file?: string;
  exists: boolean;
  settings?: { name: string; description: string; target: string; base_path: string };
  endpoints?: Endpoint[];
  models?: Record<string, { fields: Record<string, string>; line: number }>;
  problems?: { line: number; message: string }[];
  running: { port: number; url: string; since: string; endpoints: number } | null;
  failed?: { error: string; line: number | null } | null;
}

export const TARGET_WORDS: Record<string, string> = { fastapi: "FastAPI", azure_functions: "Azure Functions (Linux, Python)", aws_lambda: "AWS Lambda (Linux, Python)" };

const badge = (method: string): HTMLElement => h("span", { class: `api-method m-${method.toLowerCase()}` }, method);

/** A made-up value for a field's annotation (the Try it body's example). */
function example(kind: string, name: string, models: State["models"], depth = 0): Value {
  const bare = kind.replace(/\s*\|\s*None$/, "").replace(/^Optional\[(.*)\]$/, "$1").trim();
  const list = /^(?:list|List)\[(.*)\]$/.exec(bare);
  if (list) return [example(list[1]!, name, models, depth + 1)];
  if (models?.[bare] && depth < 3) return Object.fromEntries(Object.entries(models[bare]!.fields).map(([k, t]) => [k, example(t, k, models, depth + 1)]));
  if (bare === "int") return /id$/i.test(name) ? 101 : 3;
  if (bare === "float" || bare === "Decimal") return 12.5;
  if (bare === "bool") return true;
  if (bare === "date") return "2026-01-15";
  if (bare === "datetime") return "2026-01-15T09:30:00";
  if (bare.startsWith("dict")) return {};
  return name === "region" ? "West" : `made-up ${name}`;
}

export function localApisSection(): HTMLElement {
  const section = h("section", { class: "local-apis", "aria-label": "Local sandbox APIs" });
  let logTimer = 0;
  const draw = async (): Promise<void> => {
    let got: State;
    try {
      got = await api<State>("/local-api");
    } catch (e) {
      section.replaceChildren(h("h2", {}, "Local sandbox APIs"));
      errorHere(e, {}, section);
      return;
    }
    const head = h("div", { class: "sandbox-head" }, h("h2", {}, "Local sandbox APIs"));
    if (!got.project) {
      section.replaceChildren(head, h("p", { class: "empty-note" }, "Open a project: its local sandbox API is its API.py."));
      return;
    }
    if (!got.exists) {
      head.append(button("New local sandbox API…", busyClick("Making API.py…", async (b) => {
        try {
          await api("/local-api/new", "POST", {});
          await draw();
        } catch (e) {
          errorHere(e, {}, b);
        }
      }), { icon: "plus", class: "primary" }));
      section.replaceChildren(head, h("p", { class: "empty-note" }, "The project has no API.py yet."));
      return;
    }
    const s = got.settings!;
    const target = h("select", { "aria-label": "Its target" }, ...Object.entries(TARGET_WORDS).map(([id, words]) => h("option", { value: id, selected: id === s.target }, words))) as HTMLSelectElement;
    target.addEventListener("change", () => void saveSettings({ target: target.value }));
    const base = h("input", { "aria-label": "Its base path", value: s.base_path, placeholder: "/api", class: "mono local-api-base", spellcheck: false }) as HTMLInputElement;
    base.addEventListener("change", () => void saveSettings({ base_path: base.value }));
    const runWords = got.running ? `Running on ${got.running.url} since ${got.running.since}` : "Not running";
    head.append(
      h("span", { class: "local-api-name" }, s.name),
      h("label", { class: "field-inline" }, h("span", { class: "muted" }, "Target"), target),
      h("label", { class: "field-inline" }, h("span", { class: "muted" }, "Base path"), base),
      h("span", { class: `local-api-status${got.running ? " on" : ""}`, role: "status" }, runWords),
      got.running
        ? button("Stop", busyClick("Stopping…", (b) => act(b, "/local-api/stop")), { icon: "stop" })
        : button("Run", busyClick("Starting…", (b) => act(b, "/local-api/run")), { icon: "play", class: "primary" }),
      button("Open API.py", () => void openOnPage(got.file!, { line: 1 }), { icon: "code" }),
      button("New endpoint from a table…", () => void newEndpoint(), { icon: "plus" }),
      button("Will this work for real?", busyClick("Checking…", (b) => checkReal(b, got)), { icon: "check", title: "Each endpoint's SQL against its connection's loaded catalog: never a query on the source" }),
      button("Export…", () => openExport(got), { icon: "export" }),
    );
    const problems = [...(got.problems ?? []), ...(got.failed ? [{ line: got.failed.line ?? 1, message: got.failed.error }] : [])];
    const problemNotes = problems.map((p) => errorNote(p.message, { where: `API.py line ${p.line}`, fixes: [{ label: "Go to line", run: () => void openOnPage(got.file!, { line: p.line }) }] }));
    const endpoints = (got.endpoints ?? []).map((e) => endpointRow(e, got));
    const log = h("div", { class: "local-api-log" });
    section.replaceChildren(
      head,
      ...problemNotes,
      endpoints.length ? h("div", { class: "local-api-endpoints", role: "list" }, ...endpoints) : h("p", { class: "empty-note" }, "API.py has no endpoints yet: write one with @endpoint, or New endpoint from a table."),
      log,
    );
    window.clearInterval(logTimer);
    if (got.running) {
      const readLog = async (): Promise<void> => {
        if (!log.isConnected) return window.clearInterval(logTimer);
        try {
          const l = await api<{ log: { at: string; method: string; path: string; status: number; ms: number; rows: number | null }[] }>("/local-api/log");
          log.replaceChildren(
            h("h3", {}, "Requests"),
            l.log.length
              ? h("table", { class: "sandbox-tables" }, h("thead", {}, h("tr", {}, ...["At", "Method", "Path", "Status", "ms", "Rows"].map((w) => h("th", {}, w)))),
                  h("tbody", {}, ...l.log.slice(-50).reverse().map((r) => h("tr", {}, h("td", {}, r.at), h("td", {}, badge(r.method)), h("td", { class: "mono" }, r.path), h("td", { class: r.status >= 400 ? "bad" : "" }, String(r.status)), h("td", { class: "num" }, String(r.ms)), h("td", { class: "num" }, r.rows === null ? "" : String(r.rows))))))
              : h("p", { class: "muted" }, "No requests yet."),
          );
        } catch {
          window.clearInterval(logTimer);
        }
      };
      void readLog();
      logTimer = window.setInterval(() => void readLog(), 2000);
    }
  };
  const act = async (b: HTMLElement, path: string): Promise<void> => {
    try {
      const done = await api<State>(path, "POST", {});
      if (done.failed) toast("API.py did not start: its problem is shown.");
      await draw();
    } catch (e) {
      errorHere(e, {}, b);
    }
  };
  const saveSettings = async (change: Record<string, string>): Promise<void> => {
    try {
      await api("/local-api/settings", "PUT", change);
      await draw();
    } catch (e) {
      errorHere(e);
    }
  };
  section.append(loadingBlock("Reading API.py…"));
  void draw();
  let timer = 0;
  onNoticeWhile(section, (n) => {
    if (n.type !== "local_api_changed" && n.type !== "project_changed" && n.type !== "file_changed") return;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => void draw(), 200);
  });
  return section;
}

function endpointRow(e: Endpoint, got: State): HTMLElement {
  const tryBox = h("div", { class: "local-api-try", hidden: true });
  const row = h("article", { class: "local-api-endpoint", role: "listitem", "data-endpoint": e.name },
    h("div", { class: "local-api-endpoint-head" },
      badge(e.method),
      h("code", {}, (got.settings?.base_path ?? "") + e.path),
      h("span", {}, e.summary),
      ...e.data.map((d) => h("span", { class: "local-api-data" }, d)),
      button("Try it", () => {
        tryBox.hidden = !tryBox.hidden;
        if (!tryBox.hidden && !tryBox.childElementCount) drawTry(tryBox, e, got);
      }, { icon: "play" }),
      button("Go to line", () => void openOnPage(got.file!, { line: e.line }), { icon: "code", iconOnly: true, title: `${e.name}: API.py line ${e.line}` }),
    ),
    tryBox,
  );
  return row;
}

function drawTry(box: HTMLElement, e: Endpoint, got: State): void {
  const inputs = new Map<string, HTMLInputElement>();
  const fields = e.params.filter((p) => p.where !== "body").map((p) => {
    const input = h("input", { "aria-label": p.name, value: p.default === null || p.default === undefined ? String(example(p.type, p.name, got.models)) : String(p.default), spellcheck: false }) as HTMLInputElement;
    inputs.set(p.name, input);
    return h("label", { class: "field-inline" }, h("span", { class: "muted" }, `${p.name} (${p.where})`), input);
  });
  const bodyParam = e.params.find((p) => p.where === "body");
  const body = bodyParam ? (h("textarea", { "aria-label": "Body", rows: 6, class: "mono", spellcheck: false }, JSON.stringify(example(bodyParam.type, bodyParam.name, got.models), null, 2)) as HTMLTextAreaElement) : null;
  const answer = h("div", { class: "local-api-answer" });
  box.append(
    h("div", { class: "local-api-fields" }, ...fields),
    body ? h("label", { class: "field" }, h("span", {}, `${bodyParam!.name} (the body, JSON)`), body) : "",
    h("div", { class: "local-api-try-actions" }, button("Send", busyClick("Sending…", async (b) => {
      let path = e.path;
      const query: Record<string, string> = {};
      for (const p of e.params) {
        const value = inputs.get(p.name)?.value ?? "";
        if (p.where === "path") path = path.replace(`{${p.name}}`, encodeURIComponent(value));
        else if (p.where === "query" && value !== "") query[p.name] = value;
      }
      let sent: unknown = undefined;
      if (body) {
        try {
          sent = JSON.parse(body.value || "null");
        } catch {
          errorHere("The body is not JSON.", {}, b);
          return;
        }
      }
      try {
        const got2 = await api<{ status: number; ms: number; rows: number | null; body: Value }>("/local-api/call", "POST", { method: e.method, path: (got.settings?.base_path ?? "") + path, query, body: sent });
        answer.replaceChildren(
          h("div", { class: `local-api-said${got2.status >= 400 ? " bad" : ""}`, role: "status" }, `${got2.status} · ${got2.ms} ms${got2.rows === null ? "" : ` · ${got2.rows} rows`}`),
          mountTree(got2.body, { depth: 2 }).element,
        );
      } catch (err) {
        errorHere(err, {}, b);
      }
    }), { class: "primary" })),
    answer,
  );
}

interface Exported {
  target: { id: string; label: string; run: string };
  folder: string;
  files: string[];
  written: string[];
  kept: { file: string; theirs: string; yours: string }[];
  variables: string[];
  notes: { reason?: string; instead?: string }[];
  sandbox: boolean;
}

/** Export…: the API for its target, a ready-to-deploy folder (exports/api/<target>/), its real connections'
 *  own code; the variables to set; a file edited by hand kept (Replace, Compare). */
function openExport(got: State): void {
  const { body, foot, close } = openDialog("Export the local sandbox API", true);
  const target = h("select", { "aria-label": "Target" }, ...Object.entries(TARGET_WORDS).map(([id, words]) => h("option", { value: id, selected: id === got.settings?.target }, words))) as HTMLSelectElement;
  const usesSandbox = (got.endpoints ?? []).some((e) => e.data.some((d) => d.startsWith("The sandbox")));
  const rows = h("input", { type: "checkbox", "aria-label": "Include the sandbox's rows" }) as HTMLInputElement;
  const result = h("div", { class: "local-api-exported" });
  body.append(
    h("label", { class: "field" }, h("span", {}, "Target"), target),
    usesSandbox ? h("label", { class: "field-inline" }, rows, h("span", {}, "Include the sandbox's rows (data/sandbox.duckdb), for the endpoints that use connection(\"Sandbox\")")) : "",
    result,
  );
  const run = async (b: HTMLElement, replace: string[] = []): Promise<void> => {
    try {
      const done = await api<Exported>("/local-api/export", "POST", { target: target.value, rows: rows.checked, replace });
      result.replaceChildren(
        h("p", {}, `${done.target.label}: ${done.files.length} files in `, h("code", {}, done.folder), done.written.length ? ` (${done.written.length} written)` : " (nothing changed)"),
        done.target.run ? h("p", { class: "muted" }, "Run it there with ", h("code", {}, done.target.run), "; README.md has the deploy steps.") : "",
        h("h3", {}, "Variables to set where it runs"),
        done.variables.length ? h("ul", {}, ...done.variables.map((v) => h("li", {}, h("code", {}, v)))) : h("p", { class: "muted" }, "None."),
        ...done.notes.map((n) => errorNote(`Only works on your machine: ${n.reason ?? ""}. ${n.instead ?? ""}`, { level: "warning", agent: false })),
        ...done.kept.map((k) => h("div", { class: "local-api-kept" },
          h("span", {}, h("code", {}, k.file), " was edited by hand: kept."),
          button("Replace", busyClick("Replacing…", (bb) => run(bb, [k.file]))),
          button("Compare", () => {
            const { body: box } = openDialog(`${k.file}: yours and the export's`, true);
            box.append(h("div", { class: "local-api-compare" }, h("pre", { class: "mono" }, k.yours), h("pre", { class: "mono" }, k.theirs)));
          }),
        )),
      );
    } catch (e) {
      errorHere(e, {}, b);
    }
  };
  foot.append(button("Close", () => close()), button("Export", busyClick("Exporting…", (b) => run(b)), { class: "primary" }));
}

/** New endpoint from a table: the CRUD set over a sandbox table, appended to API.py in its source's own style.
 *  `table`: the one to start on (the sandbox panel's row). */
export async function newEndpoint(table?: string): Promise<void> {
  const { body, foot, close } = openDialog("New endpoint from a table");
  let listed: { tables: { name: string; columns: { name: string; type: string; key: boolean }[]; client: { kind: string; connection?: string } }[] };
  try {
    listed = await api("/sandbox");
  } catch (e) {
    close();
    errorHere(e);
    return;
  }
  if (!listed.tables.length) {
    body.append(h("p", { class: "empty-note" }, "The sandbox has no tables yet: Add to sandbox first."));
    foot.append(button("Close", () => close()));
    return;
  }
  const pick = h("select", { "aria-label": "Table" }, ...listed.tables.map((t) => h("option", { value: t.name, selected: t.name === table }, t.name))) as HTMLSelectElement;
  const key = h("select", { "aria-label": "Its key" }) as HTMLSelectElement;
  const fill = (): void => {
    const t = listed.tables.find((x) => x.name === pick.value) ?? listed.tables[0]!;
    key.replaceChildren(...t.columns.map((c) => h("option", { value: c.name, selected: c.key }, `${c.name} (${c.type})`)));
  };
  pick.addEventListener("change", fill);
  fill();
  body.append(
    h("label", { class: "field" }, h("span", {}, "Table"), pick),
    h("label", { class: "field" }, h("span", {}, "Its key (get, update and delete by it)"), key),
    h("p", { class: "muted" }, "List (with limit and offset), get, create, update and delete, in the source's own style."),
  );
  foot.append(button("Cancel", () => close()), button("Add to API.py", busyClick("Adding…", async (b) => {
    try {
      const done = await api<{ added: string[]; line: number; file: string }>("/local-api/scaffold", "POST", { table: pick.value, key: key.value });
      close();
      toast(`API.py has ${done.added.length} new endpoints for ${pick.value}.`);
      if (done.file) void openOnPage(done.file, { line: done.line });
    } catch (e) {
      errorHere(e, {}, b);
    }
  }), { class: "primary" }));
}

/** Will this work for real?: each endpoint's SQL against its connection's catalog as loaded here (no query). */
async function checkReal(b: HTMLElement, got: State): Promise<void> {
  let done: { checks: { endpoint: string; line: number; connection: string; state: string; words: string }[]; ok: boolean };
  try {
    done = await api("/local-api/check", "POST", {});
  } catch (e) {
    errorHere(e, {}, b);
    return;
  }
  const { body, foot, close } = openDialog("Will this work for real?", true);
  const mark: Record<string, string> = { works: "Works", sandbox: "Sandbox only", no_catalog: "Not checked", differs: "Differs", unknown: "Not checked", unreadable: "Could not read" };
  body.append(
    done.checks.length
      ? h("table", { class: "sandbox-tables" }, h("thead", {}, h("tr", {}, ...["Endpoint", "Connection", "", ""].map((w) => h("th", {}, w)))),
          h("tbody", {}, ...done.checks.map((c) => h("tr", {},
            h("td", {}, h("code", {}, c.endpoint)),
            h("td", {}, c.connection),
            h("td", { class: c.state === "differs" ? "bad" : "" }, mark[c.state] ?? c.state),
            h("td", {}, c.words, " ", button("Go to line", () => void openOnPage(got.file!, { line: c.line }), { icon: "code", iconOnly: true, title: `API.py line ${c.line}` })),
          ))))
      : h("p", { class: "empty-note" }, "No endpoint sends SQL to check."),
  );
  foot.append(button("Close", () => close()));
}
