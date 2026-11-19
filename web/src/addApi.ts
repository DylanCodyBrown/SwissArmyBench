/**
 * addApi.ts: Add API (docs/ideas.md, "Add API", the owner 2026-11-15; the form redrawn 2026-11-16, "The
 * Add API form, labelled"), drawn in the Connections window. [WIRE]
 *
 *   [START]    two clear choices: "I have an OpenAPI document" / "I'll list the endpoints myself"
 *   [SOURCE]   the document: its address, a file on this computer, or pasted
 *   [ADDRESS]  the name, where it is hosted (a preset: Azure Function App, AWS Lambda, Google; it fills
 *              the base address and the sign-in), the base address; Find its OpenAPI on a host that
 *              keeps one
 *   [AUTH]     the sign-in and its settings (the document's own scheme first, a preset's choices); a
 *              box per variable the client reads, for Try it (a secret typed goes to the keyring on Add)
 *   [ENDPOINTS] one card per endpoint, every field labelled: Method, Path, Parameters (each one's
 *              Needed tick; a path's {word} always needed), Read as a table, Columns to keep, Try it
 *   [FOLDER]   where API_<name>.py goes
 *   [PREVIEW]  each operation as the method it becomes (a table marked, Try it on a document's tables),
 *              the variables, the file, what a re-import changes (written nowhere until Add)
 *   [ADD]      API_<name>.py written, the connection saved, then its form
 *
 * ROUTING: GET /apis/choices; POST /apis/preview (as the form changes); POST /apis/try (Try it: an
 *          operation's first rows, nothing written); POST /apis (Add)
 */
import { api } from "./api";
import { promptForError } from "./missingPackages";
import { button, clear, h, hasIcon, icon, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { busy, busyClick, loadingBlock } from "./loading";
import { backButton } from "./nav";
import { variableBox } from "./variableBox";
import { errorNote } from "./errorNote";

interface Setting {
  id: string;
  label: string;
  default: string;
  choices: { value: string; label: string }[];
  when: { setting: string; is: string } | null;
}

interface AuthType {
  id: string;
  label: string;
  settings: Setting[];
}

type Auth = { type: string } & Record<string, string>;

interface Preset {
  id: string;
  label: string;
  urls: { label: string; url: string }[];
  auths: (Auth & { label: string })[];
  spec_paths: string[];
}

interface Choices {
  auth_types: AuthType[];
  presets: Preset[];
  methods: string[];
}

interface Operation {
  name: string;
  method: string;
  path: string;
  summary: string;
  table: boolean;
  readable: boolean;
}

interface Variable {
  name: string;
  required: boolean;
  secret: boolean;
}

interface Plan {
  connection: string;
  module: string;
  file: string;
  path: string;
  exists: boolean;
  taken: string | null;
  connection_exists: boolean;
  variables: Variable[];
  changes: { added: string[]; removed: string[]; changed: string[]; same: number; auth: boolean; base_url: boolean; any: boolean } | null;
  spec: { title: string; source: string; base_url: string; operations: Operation[]; tables: { table: string }[]; auth: Auth; schemes: (Auth & { name: string })[] };
}

interface Tried {
  operation: string;
  table: string;
  columns: string[];
  rows: unknown[][];
}

export interface AddApiHost {
  body: HTMLElement;
  foot: HTMLElement;
  /** Where the document chooser starts (the files go in the library: apis/<name>/). */
  folder?: string;
  /** Where its Back goes (nav.backButton). */
  backTo: { label: string; url: string };
  /** Saved: the connection's own form follows (where each variable comes from). */
  added: (name: string) => void;
}

let choices: Promise<Choices> | null = null;
const count = (n: number, word: string): string => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
const field = (label: string, control: HTMLElement, extra = ""): HTMLLabelElement => h("label", { class: `field ${extra}`.trim() }, h("span", {}, label), control);
const shown = (value: unknown): string => (value === null || value === undefined ? "" : typeof value === "object" ? JSON.stringify(value) : String(value));
/** A parameter box's names: "status, id*" -> status, id (a typed * still means needed). */
const namesOf = (text: string): { name: string; starred: boolean }[] =>
  text
    .split(",")
    .map((n) => n.trim())
    .filter(Boolean)
    .map((n) => ({ name: n.replace(/\*+$/, "").trim(), starred: n.endsWith("*") }))
    .filter((n) => n.name);
const placeholders = (path: string): string[] => [...path.matchAll(/\{([^{}]+)\}/g)].map((m) => m[1]!.trim()).filter(Boolean);

/** Try it's answer: the first rows, as the other connection forms show a table's. */
function triedTable(got: Tried): HTMLElement[] {
  return [
    h("p", { class: "status-ok" }, `It works: ${got.table}, the first ${count(got.rows.length, "row")}.`),
    h(
      "div",
      { class: "connection-preview", tabindex: 0, role: "region", "aria-label": `${got.table}'s first rows` },
      h("table", { class: "small" }, h("thead", {}, h("tr", {}, ...got.columns.map((c) => h("th", {}, c)))), h("tbody", {}, ...got.rows.map((row) => h("tr", {}, ...row.map((v) => h("td", { class: typeof v === "number" ? "num" : "" }, shown(v))))))),
    ),
  ];
}

export function showAddApi(host: AddApiHost): void {
  const { body, foot } = host;
  const status = h("div", { class: "connection-result add-api-preview", role: "status" });
  const failed = (e: unknown): void => void status.replaceChildren(errorNote(e));
  clear(body, loadingBlock("Loading the form…"));
  clear(foot);
  (choices ??= api<Choices>("/apis/choices")).then(
    (found) => draw(found),
    (e) => {
      choices = null;
      clear(body, errorNote(e));
      foot.append(backButton(host.backTo.label, host.backTo.url));
    },
  );

  function draw(found: Choices): void {
    const types = new Map(found.auth_types.map((t) => [t.id, t]));
    let mode: "document" | "form" | null = null;
    let named = false; // the name typed (not the document's title)
    let documentAuth: Auth | null = null; // what the document's security scheme asks for
    let auth: Auth = { type: "none" };
    let authTouched = false;

    // ===== the start: two choices =====
    const choice = (label: string, iconName: string, to: "document" | "form"): HTMLButtonElement => {
      const made = button(label, () => pick(to), { class: "connection-type add-api-start", icon: iconName });
      made.setAttribute("role", "radio");
      made.setAttribute("aria-checked", "false");
      return made;
    };
    const documentTab = choice("I have an OpenAPI document", "api-openapi", "document");
    const formTab = choice("I'll list the endpoints myself", "api-form", "form");
    const pick = (to: "document" | "form"): void => {
      mode = to;
      documentTab.setAttribute("aria-checked", String(to === "document"));
      formTab.setAttribute("aria-checked", String(to === "form"));
      rest.hidden = false;
      documentPart.hidden = to !== "document";
      formPart.hidden = to !== "form";
      drawAuthChoices();
      later();
    };

    // ===== the document =====
    let fromFile = "";
    const url = h("input", { type: "url", class: "mono", placeholder: "https://…/openapi.json", spellcheck: false }) as HTMLInputElement;
    const pasted = h("textarea", { class: "mono connection-code", rows: 6, spellcheck: false }) as HTMLTextAreaElement;
    const fileName = h("span", { class: "hint mono" });
    const useUrl = (): void => {
      fromFile = "";
      pasted.value = "";
      fileName.textContent = "";
      later(0);
    };
    url.addEventListener("change", useUrl);
    url.addEventListener("keydown", (e) => e.key === "Enter" && useUrl());
    pasted.addEventListener("input", () => {
      fromFile = "";
      url.value = "";
      fileName.textContent = "";
      later();
    });
    const browse = button("File…", () => {
      void chooseFile({ title: "OpenAPI document", mode: "file", suffixes: [".json", ".yaml", ".yml"], start: host.folder }).then((path) => {
        if (!path) return;
        fromFile = path;
        url.value = "";
        pasted.value = "";
        fileName.textContent = path;
        later(0);
      });
    }, { icon: "folder" });
    const documentPart = h(
      "section",
      { class: "add-api-part", hidden: true },
      field("OpenAPI document's address", h("span", { class: "field-row" }, url, button("Read", useUrl, { icon: "import" }), browse)),
      fileName,
      h("details", { class: "connection-code-box" }, h("summary", {}, "Paste it instead"), field("OpenAPI document", pasted)),
    );

    // ===== the name, where it is hosted, its address =====
    const name = h("input", { type: "text", placeholder: "Orders", maxlength: 64, spellcheck: false }) as HTMLInputElement;
    name.addEventListener("input", () => {
      named = name.value.trim() !== "";
      later();
    });
    const preset = h("select", {}, h("option", { value: "" }, "Anywhere"), ...found.presets.map((p) => h("option", { value: p.id }, p.label))) as HTMLSelectElement;
    // One box (12.7): an address, or one with a variable in it (https://NAME.example.com with a dollar-brace),
    // written into API_<name>.py as os.environ[...].
    const baseUrl = h("input", { type: "text", inputmode: "url", class: "mono", placeholder: "https://api.example.com/v1", spellcheck: false }) as HTMLInputElement;
    baseUrl.addEventListener("input", () => {
      drawFind();
      later();
    });
    const find = button("Find its OpenAPI", busyClick("Looking…", () => findDocument()), { icon: "zoom" });
    const drawFind = (): void => {
      const chosen = found.presets.find((p) => p.id === preset.value);
      find.hidden = !chosen?.spec_paths.length || !/^https?:\/\/[^<>]+$/.test(baseUrl.value.trim());
    };
    const findDocument = async (): Promise<void> => {
      const chosen = found.presets.find((p) => p.id === preset.value);
      const root = /^(https?:\/\/[^/]+)/.exec(baseUrl.value.trim())?.[1];
      if (!chosen || !root) return;
      status.replaceChildren(loadingBlock(`Looking for ${root}'s OpenAPI document…`, { height: "48px" }));
      for (const path of chosen.spec_paths) {
        try {
          await api<Plan>("/apis/preview", "POST", { spec_url: root + path });
          url.value = root + path;
          pick("document");
          useUrl();
          return;
        } catch {
          // not there: the next place
        }
      }
      status.replaceChildren(errorNote("No OpenAPI document there: list the endpoints."));
      pick("form");
    };

    // ===== the sign-in =====
    const authType = h("select", {}) as HTMLSelectElement;
    const settingsHost = h("div", { class: "connection-fields" });
    const valuesHost = h("div", { class: "connection-fields add-api-values" });
    const typed = new Map<string, HTMLInputElement>(); // a variable's value, for Try it (and the keyring on Add)
    let secretNames = new Set<string>();
    const drawValues = (wanted: Variable[]): void => {
      secretNames = new Set(wanted.filter((v) => v.secret).map((v) => v.name));
      valuesHost.replaceChildren(
        ...wanted.map((v) => {
          let input = typed.get(v.name);
          if (!input || input.type !== (v.secret ? "password" : "text")) {
            input = h("input", { type: v.secret ? "password" : "text", class: "mono", autocomplete: "off", spellcheck: false, placeholder: "This computer's environment" }) as HTMLInputElement;
            typed.set(v.name, input);
          }
          return field(v.name, input);
        }),
      );
    };
    const values = (): Record<string, string> => Object.fromEntries([...typed].filter(([, i]) => i.value && valuesHost.contains(i)).map(([n, i]) => [n, i.value]));
    const drawAuthChoices = (): void => {
      const chosen = found.presets.find((p) => p.id === preset.value);
      const offered: HTMLElement[] = [];
      if (documentAuth && mode === "document") offered.push(h("optgroup", { label: "The document's" }, h("option", { value: "doc:" }, types.get(documentAuth.type)?.label ?? documentAuth.type)));
      if (chosen) offered.push(h("optgroup", { label: chosen.label }, ...chosen.auths.map((a, i) => h("option", { value: `preset:${i}` }, a.label))));
      offered.push(h("optgroup", { label: "Every type" }, ...found.auth_types.map((t) => h("option", { value: `type:${t.id}` }, t.label))));
      const before = authType.value;
      authType.replaceChildren(...offered);
      const same = [...authType.options].find((o) => o.value === `type:${auth.type}`);
      if (!authTouched && documentAuth && mode === "document") authType.value = "doc:";
      else if ([...authType.options].some((o) => o.value === before) && before.startsWith("preset:")) authType.value = before;
      else if (same) authType.value = same.value;
    };
    const chooseAuth = (): void => {
      const value = authType.value;
      const chosen = found.presets.find((p) => p.id === preset.value);
      if (value === "doc:" && documentAuth) auth = { ...documentAuth };
      else if (value.startsWith("preset:") && chosen) {
        const { label: _label, ...rest } = chosen.auths[Number(value.slice(7))]!;
        auth = { ...rest } as Auth;
      } else auth = { type: value.slice(5) };
      drawSettings();
    };
    authType.addEventListener("change", () => {
      authTouched = true;
      chooseAuth();
      later();
    });
    const drawSettings = (): void => {
      const type = types.get(auth.type);
      const inputs = (type?.settings ?? []).map((s) => {
        const visible = !s.when || (auth[s.when.setting] ?? types.get(auth.type)?.settings.find((o) => o.id === s.when!.setting)?.default) === s.when.is;
        let input: HTMLInputElement | HTMLSelectElement;
        if (s.choices.length) {
          input = h("select", {}, ...s.choices.map((c) => h("option", { value: c.value, selected: (auth[s.id] ?? s.default) === c.value }, c.label))) as HTMLSelectElement;
        } else {
          input = h("input", { type: "text", class: "mono", value: auth[s.id] ?? s.default, spellcheck: false }) as HTMLInputElement;
        }
        input.addEventListener(input instanceof HTMLSelectElement ? "change" : "input", () => {
          auth[s.id] = input.value;
          authTouched = true;
          if (input instanceof HTMLSelectElement) drawSettings(); // a choice shows its own settings
          later();
        });
        return visible ? field(s.label, input) : null;
      });
      settingsHost.replaceChildren(...inputs.filter((i): i is HTMLLabelElement => i !== null));
    };
    // The preset's own icon beside its box (a function host's bolt; none: Add API's own).
    const presetIcon = h("span", { class: "add-api-preset-icon", "aria-hidden": "true" });
    const drawPresetIcon = (): void => presetIcon.replaceChildren(icon(hasIcon(`api-${preset.value}`) ? `api-${preset.value}` : "api-openapi"));
    drawPresetIcon();
    preset.addEventListener("change", () => {
      drawPresetIcon();
      const chosen = found.presets.find((p) => p.id === preset.value);
      if (chosen) {
        if (!baseUrl.value.trim()) baseUrl.value = chosen.urls[0]?.url ?? "";
        authTouched = true;
        drawAuthChoices();
        authType.value = "preset:0";
        chooseAuth();
        if (!chosen.spec_paths.length && mode !== "form") pick("form");
      } else drawAuthChoices();
      drawFind();
      later();
    });

    // ===== the endpoints: one card each =====
    const cards = h("div", { class: "add-api-endpoints" });
    const cardsOf = (): HTMLElement[] => [...cards.querySelectorAll<HTMLElement>(".add-api-endpoint")];
    interface Card {
      element: HTMLElement;
      sent: () => Record<string, unknown>;
      path: () => string;
    }
    const cardData = new WeakMap<HTMLElement, Card>();
    const renumber = (): void => cardsOf().forEach((c, i) => {
      const title = c.querySelector(".add-api-endpoint-title");
      if (title) title.textContent = `Endpoint ${i + 1}`;
      c.setAttribute("aria-label", `Endpoint ${i + 1}`);
    });
    const endpoint = (method = "GET", path = "", parameters = "", table = true): HTMLElement => {
      const verb = h("select", {}, ...found.methods.map((m) => h("option", { value: m, selected: m === method }, m))) as HTMLSelectElement;
      const where = h("input", { type: "text", class: "mono", placeholder: "/orders/{id}", value: path, spellcheck: false }) as HTMLInputElement;
      const params = h("input", { type: "text", class: "mono", placeholder: "status, limit", value: parameters, spellcheck: false }) as HTMLInputElement;
      const isTable = h("input", { type: "checkbox", checked: table }) as HTMLInputElement;
      const columns = h("input", { type: "text", class: "mono", placeholder: "All", spellcheck: false }) as HTMLInputElement;
      const columnsField = field("Columns to keep", columns);
      // Each parameter's Needed tick (a path's {word} is always needed); "id*" typed still ticks it.
      const needed = new Set(namesOf(parameters).filter((n) => n.starred).map((n) => n.name));
      const neededHost = h("div", { class: "add-api-needed", role: "group", "aria-label": "Needed" });
      const drawNeeded = (): void => {
        const inPath = placeholders(where.value);
        const listed = namesOf(params.value);
        for (const n of listed) if (n.starred) needed.add(n.name);
        const all = [...new Set([...inPath, ...listed.map((n) => n.name)])];
        neededHost.hidden = all.length === 0;
        neededHost.replaceChildren(
          h("span", { class: "add-api-needed-label" }, "Needed"),
          ...all.map((p) => {
            const always = inPath.includes(p);
            const tick = h("input", { type: "checkbox", checked: always || needed.has(p), disabled: always }) as HTMLInputElement;
            tick.addEventListener("change", () => {
              if (tick.checked) needed.add(p);
              else needed.delete(p);
              drawTry();
              later();
            });
            return h("label", { class: "add-api-chip", title: always ? `${p} is in the path` : undefined }, tick, h("span", { class: "mono" }, p));
          }),
        );
      };
      const out = h("div", { class: "add-api-try", role: "status" });
      const tryButton = button("Try it", busyClick("Trying…", () => tryCard()), { icon: "play" });
      const drawTry = (): void => {
        const asked = placeholders(where.value).length > 0 || namesOf(params.value).some((n) => needed.has(n.name));
        const why = verb.value !== "GET" ? "Only a GET is tried" : !isTable.checked ? "Tick Read as a table to try it" : asked ? "It needs a value for a parameter" : !where.value.trim() ? "Give it a path" : "";
        tryButton.disabled = Boolean(why);
        tryButton.title = why || "Try it";
        columnsField.hidden = !isTable.checked;
      };
      const card = h(
        "section",
        { class: "add-api-endpoint", role: "group" },
        h("div", { class: "add-api-endpoint-head" }, h("span", { class: "add-api-endpoint-title" }), tryButton, button("Remove endpoint", () => {
          card.remove();
          renumber();
          later();
        }, { icon: "trash", iconOnly: true, class: "ghost" })),
        h("div", { class: "add-api-endpoint-fields" }, field("Method", verb, "add-api-method-field"), field("Path", where)),
        field("Parameters", params),
        neededHost,
        h("label", { class: "field-flag" }, isTable, h("span", {}, "Read as a table")),
        columnsField,
        out,
      );
      const tryCard = async (): Promise<void> => {
        const at = cardsOf().filter((c) => cardData.get(c)!.path()).indexOf(card);
        await tryOperation(at, out);
      };
      cardData.set(card, {
        element: card,
        path: () => where.value.trim(),
        sent: () => ({
          method: verb.value,
          path: where.value.trim(),
          parameters: namesOf(params.value)
            .map((n) => (needed.has(n.name) ? `${n.name}*` : n.name))
            .join(", "),
          table: isTable.checked,
          ...(isTable.checked && columns.value.trim() ? { columns: columns.value.trim() } : {}),
        }),
      });
      where.addEventListener("input", () => {
        drawNeeded();
        drawTry();
        later();
      });
      params.addEventListener("input", () => {
        drawNeeded();
        drawTry();
        later();
      });
      columns.addEventListener("input", () => later());
      for (const input of [verb, isTable]) input.addEventListener("change", () => {
        drawTry();
        later();
      });
      drawNeeded();
      drawTry();
      cards.append(card);
      renumber();
      return card;
    };
    endpoint();
    const formPart = h(
      "section",
      { class: "add-api-part", hidden: true },
      h("h4", {}, "Endpoints"),
      cards,
      button("Add an endpoint", () => {
        const made = endpoint();
        made.querySelector<HTMLInputElement>("input[type='text']")?.focus();
      }, { icon: "plus" }),
    );
    const endpoints = (): Record<string, unknown>[] => cardsOf().map((c) => cardData.get(c)!).filter((c) => c.path()).map((c) => c.sent());

    // ===== where the file goes =====

    // ===== what it would write =====
    const sent = (): Record<string, unknown> | null => {
      const out: Record<string, unknown> = {};
      if (mode === "form") {
        const list = endpoints();
        if (!list.length || !baseUrl.value.trim()) return null;
        out.form = { title: name.value.trim() || "API", base_url: baseUrl.value.trim(), endpoints: list };
      } else if (mode === "document") {
        if (fromFile) out.spec_path = fromFile;
        else if (pasted.value.trim()) out.spec = pasted.value;
        else if (url.value.trim()) out.spec_url = url.value.trim();
        else return null;
        if (baseUrl.value.trim()) out.base_url = baseUrl.value.trim();
      } else return null;
      if (named) out.name = name.value.trim();
      if (authTouched || mode === "form") out.auth = auth;
      return out;
    };
    let plan: Plan | null = null;
    let asked = 0;
    let waiting = 0;
    const later = (ms = 450): void => {
      window.clearTimeout(waiting);
      waiting = window.setTimeout(() => void preview(), ms);
    };
    const preview = async (): Promise<Plan | null> => {
      const mine = ++asked;
      const body = sent();
      add.disabled = true;
      if (!body) {
        plan = null;
        status.replaceChildren();
        return null;
      }
      status.replaceChildren(loadingBlock("Reading the API…", { height: "48px" }));
      try {
        const got = await api<Plan>("/apis/preview", "POST", body);
        if (mine !== asked) return null;
        plan = got;
        if (!named) name.value = got.connection;
        if (mode === "document") {
          const before = documentAuth?.type;
          documentAuth = got.spec.auth;
          if (!authTouched) auth = { ...got.spec.auth };
          if (before !== documentAuth.type || !authTouched) {
            drawAuthChoices();
            drawSettings();
          }
          baseUrl.placeholder = got.spec.base_url || "https://api.example.com/v1";
        }
        drawValues(got.variables.slice(1)); // the first is the base address's own
        drawPlan(got);
        add.disabled = Boolean(got.taken);
        return got;
      } catch (e) {
        if (mine !== asked) return null;
        plan = null;
        failed(e);
        promptForError(e, { then: () => void preview() }); // a YAML document and no PyYAML: install, read again
        return null;
      }
    };
    // Try it: an operation's first rows (by its place among the endpoints, or by its name), written nowhere.
    const tryOperation = async (which: number | string, out: HTMLElement): Promise<void> => {
      out.replaceChildren(loadingBlock(typeof which === "string" ? `Trying ${which}…` : "Trying it…", { height: "48px" }));
      window.clearTimeout(waiting);
      const fresh = await preview();
      const body = sent();
      const operation = typeof which === "string" ? which : fresh?.spec.operations[which]?.name;
      if (!body || !operation) {
        out.replaceChildren(errorNote(mode === "form" && !baseUrl.value.trim() ? "Give the base address first." : "Fix the form first."));
        return;
      }
      try {
        out.replaceChildren(...triedTable(await api<Tried>("/apis/try", "POST", { ...body, try: operation, values: values() })));
      } catch (e) {
        out.replaceChildren(errorNote(e));
      }
    };
    const documentTry = h("div", { class: "add-api-try", role: "status" });
    const drawPlan = (p: Plan): void => {
      const changed = new Set([...(p.changes?.added ?? []), ...(p.changes?.changed ?? [])]);
      const ops = h(
        "ul",
        { class: "add-api-operations", "aria-label": "What it makes" },
        ...p.spec.operations.map((o) =>
          h(
            "li",
            { class: changed.has(o.name) ? "changed" : "" },
            h("code", { class: "add-api-method" }, o.method),
            h("code", {}, o.path),
            h("span", { class: "hint" }, `${o.name}()`),
            o.readable ? h("span", { class: "badge" }, "Table") : null,
            p.changes?.added.includes(o.name) ? h("span", { class: "badge" }, "New") : p.changes?.changed.includes(o.name) ? h("span", { class: "badge" }, "Changed") : null,
            o.readable && mode === "document" ? button(`Try ${o.name}`, busyClick("Trying…", () => tryOperation(o.name, documentTry)), { icon: "play", iconOnly: true, class: "ghost add-api-op-try", title: "Try it" }) : null,
          ),
        ),
        ...(p.changes?.removed ?? []).map((n) => h("li", { class: "removed" }, h("span", { class: "hint" }, `${n}()`), h("span", { class: "badge" }, "Removed"))),
      );
      const changes = p.changes;
      const summary = changes
        ? changes.any
          ? [changes.auth ? "Sign-in changed" : "", changes.base_url ? "Address changed" : ""].filter(Boolean).join(" · ")
          : "No changes"
        : "";
      clear(
        status,
        h("p", { class: "hint add-api-file" }, h("code", {}, p.path), p.exists ? h("span", { class: "badge" }, "Replaces") : null),
        p.taken ? errorNote(p.taken) : null,
        summary ? h("p", { class: "hint" }, summary) : null,
        h("p", { class: "hint" }, `${p.spec.title} · ${p.spec.source} · ${count(p.spec.operations.length, "operation")} · ${count(p.spec.tables.length, "table")}`),
        ops,
        mode === "document" ? documentTry : null,
        p.variables.length > 1 ? h("p", { class: "hint add-api-variables" }, ...p.variables.slice(1).map((v) => h("code", { title: v.required ? "Needed" : "Optional" }, v.name))) : null,
      );
    };

    // ===== Add =====
    // Adding writes its files: the form is gated until it is done (loading.ts).
    const add = button("Add", busyClick("Adding…", () => busy(body, `Adding ${name.value.trim() || "the API"}…`, save())), { icon: "plus", class: "primary" });
    add.disabled = true;
    const save = async (): Promise<void> => {
      const body = sent();
      if (!body || !plan) return;
      // A value typed for Try it is kept as the connection's: a secret in the keyring, the rest plainly.
      const given = values();
      const keep = Object.keys(given).length
        ? {
            variables: Object.entries(given).map(([n, v]) => (secretNames.has(n) ? { name: n, from: "keyring" } : { name: n, from: "value", value: v })),
            secrets: Object.fromEntries(Object.entries(given).filter(([n]) => secretNames.has(n))),
          }
        : {};
      add.disabled = true;
      try {
        const done = await api<Plan & { saved: { name: string } }>("/apis", "POST", { ...body, ...keep });
        toast(`Added ${done.connection}: ${done.file}`);
        host.added(done.saved.name);
      } catch (e) {
        add.disabled = false;
        failed(e);
      }
    };

    drawAuthChoices();
    authType.value = "type:none";
    drawSettings();
    drawFind();
    const rest = h(
      "div",
      { class: "add-api-rest", hidden: true },
      documentPart,
      h(
        "section",
        { class: "add-api-part" },
        h("div", { class: "connection-fields" }, field("Name", name), field("Hosted on", h("span", { class: "field-row" }, presetIcon, preset))),
        field("Base address", h("span", { class: "field-row" }, variableBox(baseUrl, { label: "Base address" }), find)),
      ),
      h("section", { class: "add-api-part add-api-auth" }, h("div", { class: "connection-fields" }, field("Sign in", authType)), settingsHost, valuesHost),
      formPart,
      // Where the files go is this computer's library (apis/<name>/, 2026-11-17): the preview says it.
      status,
    );
    clear(
      body,
      h("h3", {}, "Add API"),
      h("div", { class: "add-api" }, h("div", { class: "add-api-starts", role: "radiogroup", "aria-label": "Start from" }, documentTab, formTab), rest),
    );
    foot.append(backButton(host.backTo.label, host.backTo.url), add);
    documentTab.focus();
  }
}
