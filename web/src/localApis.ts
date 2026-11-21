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
 *               rows and the answer as a tree; a refusal as the one error note (its sentence, API.py's line, Go to
 *               line, the answer behind Details). The made-up request is the server's (the endpoint's `try`)
 *   [LOG]       the request log while it runs (method, path, status, ms, rows; a refusal's words and line; never a
 *               value), kept current; Output: what API.py printed, folded
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
  /** Try it's body kept as its example (.sab/api_examples.json beside API.py), or null. */
  example?: Value | null;
  /** A made-up request from the endpoint's own definition (the server's; the kept example's body first). */
  try?: { path: Record<string, Value>; query: Record<string, Value>; body: Value };
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
  /** The framework targets (the backend's registry: the base's three and each extension's). */
  targets?: { id: string; label: string }[];
}

/** The targets' picker: the backend's list (an extension's target shows like the base's). */
function targetSelect(got: State, label: string): HTMLSelectElement {
  const chosen = got.settings?.target;
  return h("select", { "aria-label": label }, ...(got.targets ?? []).map((x) => h("option", { value: x.id, selected: x.id === chosen }, x.label))) as HTMLSelectElement;
}

const badge = (method: string): HTMLElement => h("span", { class: `api-method m-${method.toLowerCase()}` }, method);

/** An endpoint's open Try it, kept over a redraw (API.py saved, the API started again, another window's change):
 *  the same box with what was typed and its last answer, while the endpoint takes the same parameters. */
interface TryRef { e: Endpoint; got: State }
type TryKept = Map<string, { box: HTMLElement; ref: TryRef; shape: string }>;

export function localApisSection(): HTMLElement {
  const section = h("section", { class: "local-apis", "aria-label": "Local sandbox APIs" });
  const tries: TryKept = new Map();
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
    const target = targetSelect(got, "Its target");
    target.addEventListener("change", () => void saveSettings({ target: target.value }, target));
    const base = h("input", { "aria-label": "Its base path", value: s.base_path, placeholder: "/api", class: "mono local-api-base", spellcheck: false }) as HTMLInputElement;
    base.addEventListener("change", () => void saveSettings({ base_path: base.value }, base));
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
    const endpoints = (got.endpoints ?? []).map((e) => endpointRow(e, got, tries));
    const still = new Set((got.endpoints ?? []).map((e) => `${e.method} ${e.path}`));
    for (const key of [...tries.keys()]) if (!still.has(key)) tries.delete(key);
    // The box being typed in keeps the keyboard and the cursor's place through the redraw.
    const typing = document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement ? document.activeElement : null;
    const held = typing && section.contains(typing) && typing.closest(".local-api-try") ? { box: typing, start: typing.selectionStart, end: typing.selectionEnd } : null;
    const log = h("div", { class: "local-api-log" });
    const shapes = h("div", { class: "local-api-shapes" });
    void drawShapes(shapes);
    section.replaceChildren(
      head,
      ...problemNotes,
      shapes,
      endpoints.length ? h("div", { class: "local-api-endpoints", role: "list" }, ...endpoints) : h("p", { class: "empty-note" }, "API.py has no endpoints yet: write one with @endpoint, or New endpoint from a table."),
      log,
    );
    if (held?.box.isConnected) {
      held.box.focus({ preventScroll: true });
      if (held.start !== null && held.end !== null) held.box.setSelectionRange(held.start, held.end);
    }
    window.clearInterval(logTimer);
    if (got.running) {
      const readLog = async (): Promise<void> => {
        if (!log.isConnected) return window.clearInterval(logTimer);
        try {
          const l = await api<{ log: { at: string; method: string; path: string; status: number; ms: number; rows: number | null; error?: string; line?: number }[]; output?: string[] }>("/local-api/log");
          const said = (l.output ?? []).slice(-200);
          const wasOpen = log.querySelector<HTMLDetailsElement>(".local-api-output")?.open ?? false;
          log.replaceChildren(
            h("h3", {}, "Requests"),
            l.log.length
              ? h("table", { class: "sandbox-tables" }, h("thead", {}, h("tr", {}, ...["At", "Method", "Path", "Status", "ms", "Rows"].map((w) => h("th", {}, w)))),
                  h("tbody", {}, ...l.log.slice(-50).reverse().map((r) => h("tr", {}, h("td", {}, r.at), h("td", {}, badge(r.method)), h("td", { class: "mono" }, r.path), h("td", { class: r.status >= 400 ? "bad" : "" }, String(r.status), r.error ? h("span", { class: "local-api-log-error" }, ` ${r.error}`) : "", r.line ? button("Go to line", () => void openOnPage(got.file!, { line: r.line! }), { icon: "code", iconOnly: true, class: "ghost", title: `API.py line ${r.line}` }) : ""), h("td", { class: "num" }, String(r.ms)), h("td", { class: "num" }, r.rows === null ? "" : String(r.rows))))))
              : h("p", { class: "muted" }, "No requests yet."),
            // What API.py printed (its last lines): folded until asked for, there only when it printed.
            said.length ? h("details", { class: "local-api-output", open: wasOpen }, h("summary", {}, `Output · ${said.length} ${said.length === 1 ? "line" : "lines"}`), h("pre", { class: "mono" }, said.join("\n"))) : "",
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
      await api<State>(path, "POST", {});
      await draw();
    } catch (e) {
      errorHere(e, {}, b);
    }
  };
  const saveSettings = async (change: Record<string, string>, control: HTMLElement): Promise<void> => {
    try {
      await api("/local-api/settings", "PUT", change);
      await draw();
    } catch (e) {
      errorHere(e, {}, control);
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

function endpointRow(e: Endpoint, got: State, tries: TryKept): HTMLElement {
  const key = `${e.method} ${e.path}`;
  const shape = JSON.stringify([e.params, got.settings?.base_path ?? ""]);
  const old = tries.get(key);
  const ref: TryRef = old?.shape === shape ? Object.assign(old.ref, { e, got }) : { e, got };
  const tryBox = old?.shape === shape ? old.box : h("div", { class: "local-api-try", hidden: true });
  tries.set(key, { box: tryBox, ref, shape });
  const row = h("article", { class: "local-api-endpoint", role: "listitem", "data-endpoint": e.name },
    h("div", { class: "local-api-endpoint-head" },
      badge(e.method),
      h("code", {}, (got.settings?.base_path ?? "") + e.path),
      h("span", {}, e.summary),
      ...e.data.map((d) => h("span", { class: "local-api-data" }, d)),
      button("Try it", () => {
        tryBox.hidden = !tryBox.hidden;
        if (!tryBox.hidden && !tryBox.childElementCount) drawTry(tryBox, ref);
      }, { icon: "play" }),
      button("Go to line", () => void openOnPage(got.file!, { line: e.line }), { icon: "code", iconOnly: true, title: `${e.name}: API.py line ${e.line}` }),
    ),
    tryBox,
  );
  return row;
}

function drawTry(box: HTMLElement, ref: TryRef): void {
  const { e, got } = ref; // its parameters and paths (the same while this box lives); the rest is read from ref
  const inputs = new Map<string, HTMLInputElement>();
  const fields = e.params.filter((p) => p.where !== "body").map((p) => {
    const start = (p.where === "path" ? e.try?.path : e.try?.query)?.[p.name] ?? p.default ?? "";
    const input = h("input", { "aria-label": p.name, value: String(start), spellcheck: false }) as HTMLInputElement;
    inputs.set(p.name, input);
    return h("label", { class: "field-inline" }, h("span", { class: "muted" }, `${p.name} (${p.where})`), input);
  });
  const bodyParam = e.params.find((p) => p.where === "body");
  const first = e.example ?? e.try?.body ?? null;
  const body = bodyParam ? (h("textarea", { "aria-label": "Body", rows: 6, class: "mono", spellcheck: false, "data-no-variables": "" }, JSON.stringify(first, null, 2)) as HTMLTextAreaElement) : null;
  // Keep as its example: the edited body becomes the endpoint's example payload (Try it starts from it; the
  // OpenAPI document shows it), kept beside API.py in .sab/api_examples.json.
  const keep = body
    ? button("Keep as its example", busyClick("Keeping…", async (b) => {
        let sent: unknown;
        try {
          sent = JSON.parse(body.value || "null");
        } catch {
          errorHere("The body is not JSON.", {}, b);
          return;
        }
        try {
          await api("/local-api/example", "POST", { endpoint: `${e.method} ${e.path}`, body: sent });
          ref.e.example = sent as Value;
          toast(`Kept as ${e.method} ${e.path}'s example (.sab/api_examples.json).`);
        } catch (err) {
          errorHere(err, {}, b);
        }
      }), { icon: "save", class: "local-api-keep" })
    : "";
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
        const got2 = await api<{ status: number; ms: number; rows: number | null; body: Value; error?: string; line?: number; where?: string }>("/local-api/call", "POST", { method: e.method, path: (got.settings?.base_path ?? "") + path, query, body: sent });
        const said = h("div", { class: `local-api-said${got2.status >= 400 ? " bad" : ""}`, role: "status" }, `${got2.status} · ${got2.ms} ms${got2.rows === null ? "" : ` · ${got2.rows} ${got2.rows === 1 ? "row" : "rows"}`}`);
        if (got2.status >= 400) {
          // A refusal is the one error note (9.5), in place: its sentence, where in API.py, Go to line, the
          // answer's own JSON behind Details.
          const line = got2.line ?? ref.e.line;
          answer.replaceChildren(said, errorNote(got2.error ?? `${e.method} ${path} answered ${got2.status}.`, {
            where: got2.where ?? `${ref.e.name}: API.py line ${line}`,
            fixes: [{ label: "Go to line", icon: "code", run: () => void openOnPage(ref.got.file!, { line }) }],
            details: JSON.stringify(got2.body, null, 2),
          }));
        } else {
          answer.replaceChildren(said, got2.body === null || got2.body === undefined ? "" : mountTree(got2.body, { depth: 2 }).element);
        }
      } catch (err) {
        errorHere(err, {}, b);
      }
    }), { class: "primary" }), keep),
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
  /** What to know before deploying, each one sentence (connection("Sandbox") exported without its rows). */
  warnings?: string[];
  sandbox: boolean;
}

/** Export…: the API for its target, a ready-to-deploy folder (exports/api/<target>/), its real connections'
 *  own code; the variables to set; a file edited by hand kept (Replace, Compare). */
function openExport(got: State): void {
  const { body, foot, close } = openDialog("Export the local sandbox API", true);
  const target = targetSelect(got, "Target");
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
        ...(done.warnings ?? []).map((w) => errorNote(w, { level: "warning", agent: false })),
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

/** Payload shapes: each canvas widget that uses an endpoint, what it expects beside what the endpoint answers,
 *  each mismatch said before Play. Nothing shows while no widget uses one. */
async function drawShapes(host: HTMLElement): Promise<void> {
  let got: { uses: { canvas: string; page: string; widget: string; event?: string; endpoint: string; expects: string; answers: { fields?: Record<string, string>; body?: Record<string, string> }; problems: string[] }[] };
  try {
    got = await api("/local-api/shapes");
  } catch {
    return;
  }
  if (!got.uses.length) return;
  const fields = (f?: Record<string, string>): string => (f ? Object.entries(f).map(([k, t]) => `${k}: ${t}`).join(", ") : "");
  host.replaceChildren(
    h("h3", {}, "Payload shapes"),
    h("table", { class: "sandbox-tables" },
      h("thead", {}, h("tr", {}, ...["Widget", "Endpoint", "Expects", "Answers", ""].map((w) => h("th", {}, w)))),
      h("tbody", {}, ...got.uses.map((u) => h("tr", {},
        h("td", {}, `${u.widget}${u.event ? ` · ${u.event}` : ""} `, h("span", { class: "muted" }, `${u.canvas.replace(/\.canvas\.json$/, "")} › ${u.page}`)),
        h("td", { class: "mono" }, u.endpoint),
        h("td", {}, u.expects),
        h("td", { class: "mono" }, fields(u.answers.body ?? u.answers.fields)),
        h("td", { class: u.problems.length ? "bad" : "" }, u.problems.join(" ")),
      ))),
    ),
  );
}
