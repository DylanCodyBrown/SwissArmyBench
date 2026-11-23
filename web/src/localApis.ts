/**
 * localApis.ts: the APIs page's Local sandbox APIs (the owner, 2026-11-21: "Instead of your API just call it local
 * sandbox apis"): the project's API.py, beside the imported APIs. Its endpoints run only against the project's
 * sandbox, through mock clients with the connections' own shape ("No never run against live data ever").
 *
 *   [BAR]       one slim bar as the blade IDE's (design principle 8.14; the owner approved the critic's proposal 2,
 *               2026-11-21): its name, a dot and where it runs, "The agent may write" with Stop while the agent's
 *               writes are allowed for the session, Run / Stop, Open API.py, Properties, "…" (New endpoint…: the
 *               wizard, endpointWizard.ts; Will this work for real?, Export…). PROPERTIES (closed until asked for): its target
 *               (FastAPI, Azure Functions, AWS Lambda: asked here and at New, never again at Export), its base
 *               path, its description. New local sandbox API… (with its target) while the project has none
 *   [PROBLEMS]  API.py's problems with their lines (Go to line), a start that failed with its line
 *   [ENDPOINTS] each one: method, path, the pattern that made it (Table, Search…: its marker comment), summary, its data ("Mock of Warehouse (sqlserver)"); Try it: the path's and
 *               the query's boxes, the body prefilled with a made-up example from its model, Send: status, time,
 *               rows and the answer as a tree; a refusal as the one error note (its sentence, API.py's line, Go to
 *               line, the answer behind Details). The made-up request is the server's (the endpoint's `try`)
 *   [LOG]       the request log while it runs (method, path, status, ms, rows; a refusal's words and line; never a
 *               value), kept current; Output: what API.py printed, folded
 *   The sandbox's panel (dataSandbox.ts) sits above it: Reset beside the API.
 *
 * The Scripts page's API.py tab has the same endpoints beside the code (endpointsPane: Endpoints, closed until
 * asked for; the owner approved the critic's proposal 3, 2026-11-21): Run / Stop, each endpoint's Try it, the
 * requests.
 *
 * ROUTING: GET /local-api · POST /local-api/new, /run, /stop, /call, /agent-writes · PUT /local-api/settings ·
 *          GET /local-api/log, /local-api/targets
 */
import { api, onNoticeWhile } from "./api";
import { button, h, openDialog, showMenu } from "./dom";
import { newEndpoint } from "./endpointWizard";
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
  /** The pattern the wizard made it by (API.py's marker comment); null for one written by hand. */
  pattern?: { id: string; label: string; of: string; role: string } | null;
  /** A made-up request from the endpoint's definition and its learned shape (the server's; no kept value). */
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
  /** The agent may write through the API for the rest of this session (one Allow; the sandbox only). */
  agent_writes?: boolean;
}

/** A small button of the slim bar (codeIde.ts's look). */
const small = (label: string, run: (e: MouseEvent) => void, icon: string, extra: { class?: string; title?: string; iconOnly?: boolean } = {}): HTMLButtonElement =>
  button(label, run, { icon, class: `ide-btn ${extra.class ?? "ghost"}`, title: extra.title ?? label, iconOnly: extra.iconOnly });

/** Properties shown or not (this browser's choice; closed until asked for). */
let propsOpen = false;
try {
  propsOpen = localStorage.getItem("sab.localApi.props") === "on";
} catch {
  /* private window: closed */
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
      head.append(button("New local sandbox API…", () => void newApi(() => void draw()), { icon: "plus", class: "primary" }));
      section.replaceChildren(head, h("p", { class: "empty-note" }, "The project has no API.py yet."));
      return;
    }
    const s = got.settings!;
    const target = targetSelect(got, "Its target");
    target.addEventListener("change", () => void saveSettings({ target: target.value }, target));
    const base = h("input", { "aria-label": "Its base path", value: s.base_path, placeholder: "/api", class: "mono local-api-base", spellcheck: false }) as HTMLInputElement;
    base.addEventListener("change", () => void saveSettings({ base_path: base.value }, base));
    const about = h("input", { "aria-label": "Its description", value: s.description, placeholder: "What it is for", spellcheck: true }) as HTMLInputElement;
    about.addEventListener("change", () => void saveSettings({ description: about.value }, about));
    const props = h("div", { class: "local-api-props", role: "group", "aria-label": "Properties", hidden: !propsOpen },
      h("label", { class: "field-inline" }, h("span", { class: "muted" }, "Target"), target),
      h("label", { class: "field-inline" }, h("span", { class: "muted" }, "Base path"), base),
      h("label", { class: "field-inline local-api-about" }, h("span", { class: "muted" }, "Description"), about),
    );
    const propsBtn = small("Properties", () => {
      propsOpen = !propsOpen;
      props.hidden = !propsOpen;
      propsBtn.setAttribute("aria-pressed", String(propsOpen));
      try {
        localStorage.setItem("sab.localApi.props", propsOpen ? "on" : "off");
      } catch {
        /* kept for this page only */
      }
    }, "properties", { iconOnly: true });
    propsBtn.setAttribute("aria-pressed", String(propsOpen));
    const runWords = got.running ? `Running on ${got.running.url} since ${got.running.since}` : "Not running";
    const more = small("More", (e) => {
      const at = (e.currentTarget as HTMLElement).getBoundingClientRect();
      showMenu(at.left, at.bottom + 2, "More", [
        ["plus", "New endpoint…", () => void newEndpoint()],
        ["check", "Will this work for real?", () => void checkReal(more, got)],
        ["export", "Export…", () => openExport(got)],
      ]);
    }, "more", { iconOnly: true, title: "More" });
    const bar = h("div", { class: "ide-bar local-api-bar", role: "toolbar", "aria-label": "Local sandbox API" },
      h("span", { class: "ide-title" }, h("span", { class: "ide-name local-api-name" }, s.name)),
      h("span", { class: `local-api-dot${got.running ? " on" : ""}`, "aria-hidden": "true" }),
      h("span", { class: `local-api-status${got.running ? " on" : ""}`, role: "status" }, runWords),
      agentMark(got, () => void draw()),
      h("span", { class: "ide-bar-gap" }),
      got.running
        ? small("Stop", busyClick("Stopping…", (b) => act(b, "/local-api/stop")), "stop")
        : small("Run", busyClick("Starting…", (b) => act(b, "/local-api/run")), "play", { class: "primary" }),
      small("Open API.py", () => void openOnPage(got.file!, { line: 1 }), "code"),
      propsBtn,
      more,
    );
    head.className = "local-api-head";
    head.replaceChildren(h("h2", {}, "Local sandbox APIs"), bar, props);
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
      endpoints.length ? h("div", { class: "local-api-endpoints", role: "list" }, ...endpoints) : h("p", { class: "empty-note" }, "API.py has no endpoints yet: write one with @endpoint, or New endpoint… (the bar's …)."),
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
                  h(
                    "tbody",
                    {},
                    ...l.log.slice(-50).reverse().map((r) =>
                      h(
                        "tr",
                        {},
                        h("td", {}, r.at),
                        h("td", {}, badge(r.method)),
                        h("td", { class: "mono" }, r.path),
                        h(
                          "td",
                          { class: r.status >= 400 ? "bad" : "" },
                          String(r.status),
                          r.error ? h("span", { class: "local-api-log-error" }, ` ${r.error}`) : "",
                          r.line
                            ? button("Go to line", () => void openOnPage(got.file!, { line: r.line! }), { icon: "code", iconOnly: true, class: "ghost", title: `API.py line ${r.line}` })
                            : "",
                        ),
                        h("td", { class: "num" }, String(r.ms)),
                        h("td", { class: "num" }, r.rows === null ? "" : String(r.rows)),
                      ),
                    ),
                  ))
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
      e.pattern ? h("span", { class: "local-api-pattern", title: `Made by the ${e.pattern.label} pattern over ${e.pattern.of}; the code is yours to change` }, e.pattern.label) : null,
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
  // The form starts from the endpoint's learned shape (the server's `try`: made-up values by learned type).
  const first = e.try?.body ?? null;
  const body = bodyParam ? (h("textarea", { "aria-label": "Body", rows: 6, class: "mono", spellcheck: false, "data-no-variables": "" }, JSON.stringify(first, null, 2)) as HTMLTextAreaElement) : null;
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
  /** What to know before deploying, each one sentence (connection("Sandbox") exported without its rows). */
  warnings?: string[];
  sandbox: boolean;
}

/** Export…: the API for its target, a ready-to-deploy folder (exports/api/<target>/), its real connections'
 *  own code; the variables to set; a file edited by hand kept (Replace, Compare). */
function openExport(got: State): void {
  const { body, foot, close } = openDialog("Export the local sandbox API", true);
  // Its target is asked once (New, or Properties): said here, never asked again.
  const chosen = got.settings?.target ?? "";
  const target = { value: chosen };
  const targetWords = (got.targets ?? []).find((t) => t.id === chosen)?.label ?? chosen;
  const usesSandbox = (got.endpoints ?? []).some((e) => e.data.some((d) => d.startsWith("The sandbox")));
  const rows = h("input", { type: "checkbox", "aria-label": "Include the sandbox's rows" }) as HTMLInputElement;
  const result = h("div", { class: "local-api-exported" });
  body.append(
    h("p", { class: "local-api-target" }, "For ", h("strong", {}, targetWords), h("span", { class: "muted" }, " (its target: change it in Properties)")),
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

/** "The agent may write" while one Allow lets the agent write through the API this session (the sandbox only),
 *  with Stop: its writes ask again. */
function agentMark(got: State, redraw: () => void): HTMLElement | string {
  if (!got.agent_writes) return "";
  return h("span", { class: "local-api-agent", title: "One Allow lets the agent write through the local sandbox API for the rest of this session: the sandbox only, never live; Reset undoes it" },
    "The agent may write",
    small("Stop", busyClick("Stopping…", async (b) => {
      try {
        await api("/local-api/agent-writes", "POST", { allow: false });
        redraw();
      } catch (e) {
        errorHere(e, {}, b);
      }
    }), "stop", { title: "Stop: each of the agent's writes asks again" }),
  );
}

/** New local sandbox API…: its target asked once (Export never asks again), then API.py made. */
async function newApi(made: () => void): Promise<void> {
  const { body, foot, close } = openDialog("New local sandbox API");
  let targets: { id: string; label: string }[] = [];
  try {
    targets = (await api<{ targets: { id: string; label: string }[] }>("/local-api/targets")).targets;
  } catch {
    /* the default target (FastAPI) */
  }
  const pick = h("select", { "aria-label": "Its target" }, ...targets.map((t, i) => h("option", { value: t.id, selected: i === 0 }, t.label))) as HTMLSelectElement;
  body.append(h("label", { class: "field" }, h("span", {}, "Its target (where it is deployed; Export makes it ready for this)"), pick));
  foot.append(button("Cancel", () => close()), button("Make API.py", busyClick("Making API.py…", async (b) => {
    try {
      await api("/local-api/new", "POST", pick.value ? { target: pick.value } : {});
      close();
      made();
    } catch (e) {
      errorHere(e, {}, b);
    }
  }), { class: "primary" }));
}

/** API.py's endpoints beside its code (the Scripts page's tab, its Endpoints panel): Run / Stop, each endpoint's
 *  Try it, the requests; drawn again when API.py or the API changes, while it is shown. */
export function endpointsPane(body: HTMLElement): void {
  const kept = paneTries.get(body) ?? new Map();
  paneTries.set(body, kept);
  const draw = async (): Promise<void> => {
    let got: State;
    try {
      got = await api<State>("/local-api");
    } catch (e) {
      body.replaceChildren();
      errorHere(e, {}, body);
      return;
    }
    if (!got.exists) {
      body.replaceChildren(h("p", { class: "empty-note" }, "The project has no API.py yet."));
      return;
    }
    const act = (path: string) => busyClick(path.endsWith("stop") ? "Stopping…" : "Starting…", async (b) => {
      try {
        await api(path, "POST", {});
        await draw();
      } catch (e) {
        errorHere(e, {}, b);
      }
    });
    const line = h("div", { class: "local-api-pane-bar" },
      h("span", { class: `local-api-dot${got.running ? " on" : ""}`, "aria-hidden": "true" }),
      h("span", { class: `local-api-status${got.running ? " on" : ""}`, role: "status" }, got.running ? `Running on ${got.running.url}` : "Not running"),
      agentMark(got, () => void draw()),
      h("span", { class: "ide-bar-gap" }),
      small("New endpoint…", () => void newEndpoint(), "plus"),
      got.running ? small("Stop", act("/local-api/stop"), "stop") : small("Run", act("/local-api/run"), "play", { class: "primary" }),
    );
    const rows = (got.endpoints ?? []).map((e) => endpointRow(e, got, kept));
    body.replaceChildren(
      line,
      rows.length ? h("div", { class: "local-api-endpoints", role: "list" }, ...rows) : h("p", { class: "empty-note" }, "No endpoints yet: write one with @endpoint."),
    );
  };
  void draw();
  let timer = 0;
  onNoticeWhile(body, (n) => {
    if (n.type !== "local_api_changed" && n.type !== "project_changed" && n.type !== "file_changed") return;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => void draw(), 300);
  });
}

const paneTries = new WeakMap<HTMLElement, TryKept>();

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
