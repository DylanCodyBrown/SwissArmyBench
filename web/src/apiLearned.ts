/**
 * apiLearned.ts: what the APIs page shows of api_adapter (Plans/api-adapter.plan.md; the owner, 2026-11-22: "No
 * need for a discovery report, the API page is all we need"). [SHARED]
 *
 *   [DISCOVER] Discover: the read-only probe (the app asks Allow once per API and remembers it with the
 *              API until it is taken back: "Discover allowed since <day>", Take it back); each read
 *              endpoint called once at its smallest page; what was learned shows on each endpoint.
 *   [LEARNED]  an endpoint's learned shape (else its declared one, marked so): its kind, what it maps to
 *              (a table, a detail card, a metric, a download, a form), each field's path and type with its
 *              drift mark (new, retyped), the drift line, a rename offered once (Use it / No); Run (its
 *              envelope: kind, status, pages); Build: a notebook cell, a script function, a widget on a
 *              canvas page. Nothing is built until the user picks it.
 *
 * ROUTING: GET /actions?api=, /actions/{api}/{action}  ·  POST /actions/run, /actions/discover, /actions/allow,
 *          /actions/offer, /actions/build
 */
import { api } from "./api";
import { button, h, openDialog, toast } from "./dom";
import { busy, busyClick } from "./loading";
import { errorHere, errorNote, warningNote } from "./errorNote";
import { openOnPage } from "./workbenchPages";
import { type Figures, figuresLine } from "./callFigures";

export interface Learned {
  name: string;
  kind: string;
  learned: boolean;
  drift: string;
  maps_to: string[];
  offers: number;
}

interface Field {
  path: string;
  type: string;
  format: string;
  empty: boolean;
  mark: string;
}

interface Contract {
  learned: boolean;
  kind: string;
  envelope: string;
  fields: Field[];
  drift: string;
  missing: string[];
  offers: { from: string; to: string; said: string }[];
  seen: string;
  maps_to: string[];
}

const MAPS: Record<string, string> = {
  table: "a table",
  grid: "a grid",
  detail: "a detail card",
  form: "a form",
  metric: "a metric",
  download: "a download",
  text: "text",
};

const at = (apiName: string, action: string): string => `/actions/${encodeURIComponent(apiName)}/${encodeURIComponent(action)}`;

/** Since when each API's discovery is allowed (null: not), as learnedOf last read it. */
const ALLOWED = new Map<string, string | null>();

/**
 * Discover's remembered Allow, beside its button: since when, and Take it back (asked again at the next
 * Discover). Nothing while it is not allowed. `done` redraws.
 */
export function discoverAllowed(apiName: string, done: () => void): HTMLElement | string {
  const since = ALLOWED.get(apiName);
  if (!since) return "";
  return h(
    "span",
    { class: "api-discover-allowed muted" },
    `Discover allowed since ${since}`,
    button("Take it back", busyClick("Taking it back…", async (b) => {
      try {
        await api("/actions/allow", "POST", { api: apiName, allow: false });
        ALLOWED.set(apiName, null);
        done();
      } catch (e) {
        errorHere(e, {}, b);
      }
    }), { class: "ghost api-discover-forget" }),
  );
}

/** Each action's learned facts by name, for the operations' list (its drift mark). */
export async function learnedOf(apiName: string): Promise<Map<string, Learned>> {
  try {
    const got = await api<{ apis: { api: string; allowed_since?: string | null; actions: Learned[] }[] }>(`/actions?api=${encodeURIComponent(apiName)}`);
    ALLOWED.set(apiName, got.apis[0]?.allowed_since ?? null);
    return new Map((got.apis[0]?.actions ?? []).map((a) => [a.name, a]));
  } catch {
    return new Map();
  }
}

/** Discover: the read-only probe on the app's Allow. `done` redraws what was learned. */
export function discoverButton(apiName: string, host: () => HTMLElement, done: () => void): HTMLButtonElement {
  return button(
    "Discover",
    busyClick("Discovering…", async (b) => {
      try {
        const got = await busy(host(), `Learning ${apiName}: one read-only call per read endpoint…`, api<{ calls: number; skipped: Record<string, string> }>("/actions/discover", "POST", { api: apiName }));
        toast(`${apiName}: ${got.calls} call${got.calls === 1 ? "" : "s"} made, nothing that writes.`);
        done();
      } catch (e) {
        errorHere(e, {}, b);
      }
    }),
    { icon: "zoom", class: "api-discover", title: "Call each read endpoint once and learn what it answers (you are asked first)" },
  );
}

function fieldRows(contract: Contract): HTMLElement {
  if (!contract.fields.length) return h("p", { class: "muted" }, "No fields.");
  return h(
    "table",
    { class: "api-learned-fields" },
    h("thead", {}, h("tr", {}, ...["Field", "Type", ""].map((t) => h("th", {}, t)))),
    h(
      "tbody",
      {},
      ...contract.fields.map((f) =>
        h(
          "tr",
          { "data-field": f.path, class: f.mark ? `mark-${f.mark}` : "" },
          h("td", { class: "mono" }, f.path),
          h("td", {}, f.type + (f.format && f.format !== "mixed" ? (f.format === "text" ? " in text" : ` (${f.format})`) : "") + (f.empty ? ", can be empty" : "")),
          h("td", { class: "api-learned-mark" }, f.mark),
        ),
      ),
      ...contract.missing.map((p) => h("tr", { "data-field": p, class: "mark-missing" }, h("td", { class: "mono" }, p), h("td", { class: "muted" }, "gone"), h("td", { class: "api-learned-mark" }, "missing"))),
    ),
  );
}

/** The project's files a built function never goes into (the server refuses them too). */
const NOT_SCRIPTS = ["API.py", "data.py", "adapter.py", "api_adapter.py", "connections.py", "sab_api.py"];

/**
 * The script a built function goes into: one of the open project's, or a new one by its name. Answers its
 * path inside the project; "" with no project open (the code is shown to copy); null when cancelled.
 */
async function pickScript(): Promise<string | null> {
  const got = await api<{ project: string | null; documents: { path: string }[] }>("/project/documents?kind=script");
  if (!got.project) return "";
  const mine = got.documents.map((d) => d.path).filter((p) => !NOT_SCRIPTS.includes(p.split("/").pop() ?? "") && !/(^|\/)API_\w+\.py$/.test(p));
  return new Promise((resolve) => {
    const { dialog, body, foot, close } = openDialog("Put the function in a script");
    const fresh = h("input", { "aria-label": "New script", value: "api_functions.py", spellcheck: false, "data-no-variables": "" }) as HTMLInputElement;
    const pick = h("select", { "aria-label": "Script" }, ...mine.map((p) => h("option", { value: p }, p)), h("option", { value: "" }, "A new script…")) as HTMLSelectElement;
    const named = h("label", { class: "field" }, h("span", {}, "Its name"), fresh);
    const follow = (): void => {
      named.hidden = pick.value !== "";
    };
    pick.addEventListener("change", follow);
    follow();
    body.append(h("label", { class: "field" }, h("span", {}, "Script"), pick), named);
    let done = false;
    const end = (value: string | null): void => {
      if (done) return;
      done = true;
      close();
      resolve(value);
    };
    dialog.addEventListener("close", () => end(null));
    foot.append(
      button("Cancel", () => end(null)),
      button("Put it there", () => end(pick.value || fresh.value.trim() || "api_functions.py"), { class: "primary api-build-put" }),
    );
  });
}

/** The code Build made, to copy into a notebook cell or a script (no project is open to put it in). */
function showCode(title: string, code: string): void {
  const { body, foot, close } = openDialog(title);
  body.append(h("pre", { class: "mono api-built-code" }, code));
  foot.append(
    button("Close", () => close()),
    button("Copy", () => void navigator.clipboard.writeText(code).then(() => toast("Copied: paste it where you want it")), { icon: "copy", class: "primary" }),
  );
}

/** One endpoint's learned section: its shape, what it maps to, the drift, Run and Build. */
export function learnedSection(apiName: string, action: string, writes: boolean, inputs: () => Record<string, unknown>): HTMLElement {
  const section = h("section", { class: "api-learned", "data-action": action }, h("h3", {}, "What it answers"));
  const draw = async (): Promise<void> => {
    let got: { contract: Contract };
    const endpoint = `${apiName} ${action}`; // its running figures (services/call_stats.py), small
    const figures = api<{ figures: Record<string, Figures> }>(`/stats/figures?kind=endpoint&names=${encodeURIComponent(endpoint)}`).catch(() => ({ figures: {} as Record<string, Figures> }));
    try {
      got = await api<{ contract: Contract }>(at(apiName, action));
    } catch (e) {
      section.replaceChildren(h("h3", {}, "What it answers"), errorNote(String((e as Error).message)));
      return;
    }
    const c = got.contract;
    const maps = c.maps_to.map((m) => MAPS[m] ?? m).join(" or ");
    section.replaceChildren(
      h("h3", {}, "What it answers"),
      h(
        "p",
        { class: "api-learned-line" },
        h("span", { class: `api-learned-kind ${c.learned ? "learned" : "declared"}` }, c.kind || "not known yet"),
        c.learned ? ` · seen ${c.seen}` : " · as its specification declares it",
        maps ? ` · maps to ${maps}` : "",
        figuresLine((await figures).figures[endpoint]),
      ),
      c.drift ? warningNote({ what: c.drift }) : "",
      ...c.offers.map((o) =>
        h(
          "div",
          { class: "api-learned-offer" },
          h("span", {}, o.said),
          button("Use it", () => void answer(o, true), { class: "primary" }),
          button("No", () => void answer(o, false)),
        ),
      ),
      fieldRows(c),
      h(
        "div",
        { class: "api-learned-actions" },
        writes ? null : button("Run", busyClick("Running…", (b) => run(b)), { icon: "play", class: "api-run" }),
        h("span", { class: "muted" }, "Build:"),
        button("Notebook cell", busyClick("Building…", (b) => build("cell", b)), { icon: "notebook", class: "api-build-cell" }),
        button("Script function", busyClick("Building…", (b) => build("function", b)), { icon: "code", class: "api-build-function" }),
        button("Widget on a canvas", busyClick("Building…", (b) => build("widget", b)), { icon: "page", class: "api-build-widget" }),
      ),
    );
  };
  const answer = async (o: { from: string; to: string }, take: boolean): Promise<void> => {
    await api("/actions/offer", "POST", { api: apiName, action, from: o.from, to: o.to, take });
    await draw();
  };
  const run = async (b: HTMLElement): Promise<void> => {
    try {
      const got = await api<{ ok: boolean; status: number; kind: string; paging: { pages: number }; records?: unknown[]; error: { error: string } | null }>("/actions/run", "POST", { api: apiName, action, inputs: inputs() });
      if (!got.ok && got.error) errorHere(new Error(got.error.error), {}, b);
      else toast(`${got.status}: ${got.kind}${got.records ? `, ${got.records.length} record${got.records.length === 1 ? "" : "s"}` : ""} in ${got.paging.pages} page${got.paging.pages === 1 ? "" : "s"}`);
      await draw();
    } catch (e) {
      errorHere(e, {}, b);
    }
  };
  const build = async (as: string, b: HTMLElement): Promise<void> => {
    try {
      // A function goes into a script the user picks; a cell into the project's data.ipynb.
      const path = as === "function" ? await pickScript() : "";
      if (path === null) return;
      const got = await api<{ as: string; code?: string; path?: string; cell?: number; line?: number; canvas?: string; widget?: string }>("/actions/build", "POST", { api: apiName, action, as, inputs: inputs(), ...(path ? { path } : {}) });
      // Put where it belongs and opened there (Notebooks at the cell, Scripts at the function's line).
      if (got.path) await openOnPage(got.path, got.cell ? { cell: got.cell } : { line: got.line ?? null });
      else if (got.code) showCode(as === "cell" ? "A notebook cell" : "A script function", got.code);
      else toast(`Put ${got.widget} on ${got.canvas}.`);
    } catch (e) {
      errorHere(e, {}, b);
    }
  };
  void busy(section, "Reading what it answers…", draw());
  return section;
}
