/**
 * addApi.ts: Add API (docs/ideas.md, "Add API", the owner 2026-11-15), drawn in the Connections window.
 * [WIRE]
 *
 *   [PRESET]   Azure Function App, AWS Lambda, Google: the address's pattern and the sign-in choices
 *              filled in; Find its OpenAPI tries where the host keeps one (Azure's extension)
 *   [SOURCE]   an OpenAPI document (its address, a file on this computer, or pasted) or the endpoints
 *              typed in a form: a method, a path, its parameters (* needed), and whether it is a table
 *   [AUTH]     the auth type and its settings (the document's own scheme first, a preset's choices)
 *   [PREVIEW]  each operation as the method it becomes (a table marked), the variables it reads, the
 *              file, and, when it is there, what a re-import changes (written nowhere until Add)
 *   [ADD]      API_<name>.py written, the connection saved, then its form: where each variable comes from
 *
 * ROUTING: GET /apis/choices; POST /apis/preview (as the form changes); POST /apis (Add)
 */
import { api, errorText } from "./api";
import { button, clear, h, toast } from "./dom";
import { chooseFile } from "./fileChooser";

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

interface Plan {
  connection: string;
  module: string;
  file: string;
  path: string;
  exists: boolean;
  taken: string | null;
  connection_exists: boolean;
  variables: { name: string; required: boolean; secret: boolean }[];
  changes: { added: string[]; removed: string[]; changed: string[]; same: number; auth: boolean; base_url: boolean; any: boolean } | null;
  spec: { title: string; source: string; base_url: string; operations: Operation[]; tables: { table: string }[]; auth: Auth; schemes: (Auth & { name: string })[] };
}

export interface AddApiHost {
  body: HTMLElement;
  foot: HTMLElement;
  /** Where API_<name>.py goes: an open project's folder (none: the Workbench's own). */
  folder?: string;
  back: () => void;
  /** Saved: the connection's own form follows (where each variable comes from). */
  added: (name: string) => void;
}

let choices: Promise<Choices> | null = null;
const count = (n: number, word: string): string => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;

export function showAddApi(host: AddApiHost): void {
  const { body, foot } = host;
  const status = h("div", { class: "connection-result add-api-preview", role: "status" });
  const failed = (e: unknown): void => void status.replaceChildren(h("p", { class: "status-error" }, errorText(e)));
  clear(body, h("p", { class: "hint" }, "Loading…"));
  clear(foot);
  (choices ??= api<Choices>("/apis/choices")).then(
    (found) => draw(found),
    (e) => {
      choices = null;
      clear(body, h("p", { class: "status-error" }, errorText(e)));
      foot.append(button("Back", host.back, { icon: "back" }));
    },
  );

  function draw(found: Choices): void {
    const types = new Map(found.auth_types.map((t) => [t.id, t]));
    let mode: "document" | "form" = "document";
    let named = false; // the name typed (not the document's title)
    let documentAuth: Auth | null = null; // what the document's security scheme asks for
    let auth: Auth = { type: "none" };
    let authTouched = false;

    // ===== the preset, the name =====
    const preset = h("select", { "aria-label": "Preset" }, h("option", { value: "" }, "None"), ...found.presets.map((p) => h("option", { value: p.id }, p.label))) as HTMLSelectElement;
    const name = h("input", { type: "text", "aria-label": "Name", placeholder: "Orders", maxlength: 64, spellcheck: false }) as HTMLInputElement;
    name.addEventListener("input", () => {
      named = name.value.trim() !== "";
      later();
    });

    // ===== the source: a document, or the form's endpoints =====
    const pick = (to: "document" | "form"): void => {
      mode = to;
      documentTab.setAttribute("aria-pressed", String(to === "document"));
      formTab.setAttribute("aria-pressed", String(to === "form"));
      documentPart.hidden = to !== "document";
      formPart.hidden = to !== "form";
      later();
    };
    const documentTab = button("OpenAPI", () => pick("document"), { pressed: true, class: "segment" });
    const formTab = button("Endpoints", () => pick("form"), { pressed: false, class: "segment" });
    let fromFile = "";
    const url = h("input", { type: "url", class: "mono", "aria-label": "OpenAPI document's address", placeholder: "https://…/openapi.json", spellcheck: false }) as HTMLInputElement;
    const pasted = h("textarea", { class: "mono connection-code", rows: 6, spellcheck: false, "aria-label": "OpenAPI document" }) as HTMLTextAreaElement;
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
      "div",
      { class: "add-api-document" },
      h("label", { class: "field" }, h("span", {}, "Address"), h("span", { class: "field-row" }, url, button("Read", useUrl, { icon: "import" }), browse)),
      fileName,
      h("details", { class: "connection-code-box" }, h("summary", {}, "Paste"), pasted),
    );

    const rows = h("div", { class: "add-api-endpoints" });
    const endpoint = (method = "GET", path = "", parameters = "", table = true): void => {
      const verb = h("select", { "aria-label": "Method" }, ...found.methods.map((m) => h("option", { value: m, selected: m === method }, m))) as HTMLSelectElement;
      const where = h("input", { type: "text", class: "mono", "aria-label": "Path", placeholder: "/orders/{id}", value: path, spellcheck: false }) as HTMLInputElement;
      const params = h("input", { type: "text", class: "mono", "aria-label": "Parameters", placeholder: "status, id*", value: parameters, spellcheck: false }) as HTMLInputElement;
      const isTable = h("input", { type: "checkbox", checked: table, "aria-label": "Table" }) as HTMLInputElement;
      const row = h("div", { class: "add-api-endpoint" }, verb, where, params, h("label", { class: "field-flag" }, isTable, h("span", {}, "Table")), button("Remove", () => {
        row.remove();
        later();
      }, { icon: "trash", iconOnly: true, class: "ghost" }));
      for (const input of [verb, where, params, isTable]) input.addEventListener(input instanceof HTMLInputElement && input.type === "text" ? "input" : "change", () => later());
      rows.append(row);
    };
    endpoint();
    const formPart = h("div", { class: "add-api-form", hidden: true }, rows, button("Endpoint", () => {
      endpoint();
      (rows.lastElementChild?.querySelector("input[aria-label='Path']") as HTMLInputElement | null)?.focus();
    }, { icon: "plus" }));
    const endpoints = (): Record<string, unknown>[] =>
      [...rows.querySelectorAll<HTMLElement>(".add-api-endpoint")].map((row) => ({
        method: (row.querySelector("select") as HTMLSelectElement).value,
        path: (row.querySelector("input[aria-label='Path']") as HTMLInputElement).value.trim(),
        parameters: (row.querySelector("input[aria-label='Parameters']") as HTMLInputElement).value,
        table: (row.querySelector("input[aria-label='Table']") as HTMLInputElement).checked,
      })).filter((e) => e.path);

    // ===== the base URL, and a preset's OpenAPI document =====
    const baseUrl = h("input", { type: "url", class: "mono", "aria-label": "Base URL", placeholder: "https://…", spellcheck: false }) as HTMLInputElement;
    baseUrl.addEventListener("input", () => {
      drawFind();
      later();
    });
    const find = button("Find its OpenAPI", () => void findDocument(), { icon: "zoom" });
    const drawFind = (): void => {
      const chosen = found.presets.find((p) => p.id === preset.value);
      find.hidden = !chosen?.spec_paths.length || !/^https?:\/\/[^<>]+$/.test(baseUrl.value.trim());
    };
    const findDocument = async (): Promise<void> => {
      const chosen = found.presets.find((p) => p.id === preset.value);
      const root = /^(https?:\/\/[^/]+)/.exec(baseUrl.value.trim())?.[1];
      if (!chosen || !root) return;
      status.replaceChildren(h("p", { class: "hint" }, "Looking…"));
      for (const path of chosen.spec_paths) {
        try {
          await api<Plan>("/apis/preview", "POST", { spec_url: root + path, folder: host.folder || undefined });
          url.value = root + path;
          pick("document");
          useUrl();
          return;
        } catch {
          // not there: the next place
        }
      }
      status.replaceChildren(h("p", { class: "status-error" }, "No OpenAPI document there: add the endpoints."));
      pick("form");
    };

    // ===== the auth =====
    const authType = h("select", { "aria-label": "Sign in" }) as HTMLSelectElement;
    const settingsHost = h("div", { class: "connection-fields" });
    const drawAuthChoices = (): void => {
      const chosen = found.presets.find((p) => p.id === preset.value);
      const offered: HTMLElement[] = [];
      if (documentAuth && mode === "document") offered.push(h("optgroup", { label: "The document's" }, h("option", { value: "doc:" }, types.get(documentAuth.type)?.label ?? documentAuth.type)));
      if (chosen) offered.push(h("optgroup", { label: chosen.label }, ...chosen.auths.map((a, i) => h("option", { value: `preset:${i}` }, a.label))));
      offered.push(h("optgroup", { label: "Every type" }, ...found.auth_types.map((t) => h("option", { value: `type:${t.id}` }, t.label))));
      authType.replaceChildren(...offered);
      const same = [...authType.options].find((o) => o.value === `type:${auth.type}`);
      if (!authTouched && documentAuth && mode === "document") authType.value = "doc:";
      else if (same && authType.value !== same.value && !authType.value.startsWith("preset:")) authType.value = same.value;
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
        const shown = (): boolean => !s.when || (auth[s.when.setting] ?? types.get(auth.type)?.settings.find((o) => o.id === s.when!.setting)?.default) === s.when.is;
        let input: HTMLInputElement | HTMLSelectElement;
        if (s.choices.length) {
          input = h("select", { "aria-label": s.label }, ...s.choices.map((c) => h("option", { value: c.value, selected: (auth[s.id] ?? s.default) === c.value }, c.label))) as HTMLSelectElement;
        } else {
          input = h("input", { type: "text", class: "mono", "aria-label": s.label, value: auth[s.id] ?? s.default, spellcheck: false }) as HTMLInputElement;
        }
        input.addEventListener(input instanceof HTMLSelectElement ? "change" : "input", () => {
          auth[s.id] = input.value;
          authTouched = true;
          if (input instanceof HTMLSelectElement) drawSettings(); // a choice shows its own settings
          later();
        });
        return shown() ? h("label", { class: "field" }, h("span", {}, s.label), input) : null;
      });
      settingsHost.replaceChildren(...inputs.filter((i): i is HTMLLabelElement => i !== null));
    };
    preset.addEventListener("change", () => {
      const chosen = found.presets.find((p) => p.id === preset.value);
      if (chosen) {
        if (!baseUrl.value.trim()) baseUrl.value = chosen.urls[0]?.url ?? "";
        authTouched = true;
        drawAuthChoices();
        authType.value = "preset:0";
        chooseAuth();
        if (!chosen.spec_paths.length) pick("form");
      } else drawAuthChoices();
      drawFind();
      later();
    });

    // ===== where the file goes =====
    const folder = h("input", { type: "text", class: "mono", "aria-label": "Folder", value: host.folder ?? "", placeholder: "Workbench folder", spellcheck: false }) as HTMLInputElement;
    folder.addEventListener("change", () => later(0));
    const folderBrowse = button("Browse…", () => {
      void chooseFile({ title: "Where API_<name>.py goes", mode: "folder", start: folder.value || host.folder }).then((path) => {
        if (!path) return;
        folder.value = path;
        later(0);
      });
    }, { icon: "folder" });

    // ===== what it would write =====
    const sent = (): Record<string, unknown> | null => {
      const out: Record<string, unknown> = {};
      if (mode === "form") {
        const list = endpoints();
        if (!list.length || !baseUrl.value.trim()) return null;
        out.form = { title: name.value.trim() || "API", base_url: baseUrl.value.trim(), endpoints: list };
      } else {
        if (fromFile) out.spec_path = fromFile;
        else if (pasted.value.trim()) out.spec = pasted.value;
        else if (url.value.trim()) out.spec_url = url.value.trim();
        else return null;
        if (baseUrl.value.trim()) out.base_url = baseUrl.value.trim();
      }
      if (named) out.name = name.value.trim();
      if (authTouched || mode === "form") out.auth = auth;
      if (folder.value.trim()) out.folder = folder.value.trim();
      return out;
    };
    let plan: Plan | null = null;
    let asked = 0;
    let waiting = 0;
    const later = (ms = 450): void => {
      window.clearTimeout(waiting);
      waiting = window.setTimeout(() => void preview(), ms);
    };
    const preview = async (): Promise<void> => {
      const mine = ++asked;
      const body = sent();
      add.disabled = true;
      if (!body) {
        plan = null;
        status.replaceChildren();
        return;
      }
      status.replaceChildren(h("p", { class: "hint" }, "Reading…"));
      try {
        const got = await api<Plan>("/apis/preview", "POST", body);
        if (mine !== asked) return;
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
          baseUrl.placeholder = got.spec.base_url || "https://…";
        }
        drawPlan(got);
        add.disabled = Boolean(got.taken);
      } catch (e) {
        if (mine !== asked) return;
        plan = null;
        failed(e);
      }
    };
    const drawPlan = (p: Plan): void => {
      const changed = new Set([...(p.changes?.added ?? []), ...(p.changes?.changed ?? [])]);
      const ops = h(
        "ul",
        { class: "add-api-operations" },
        ...p.spec.operations.map((o) =>
          h(
            "li",
            { class: changed.has(o.name) ? "changed" : "" },
            h("code", { class: "add-api-method" }, o.method),
            h("code", {}, o.path),
            h("span", { class: "hint" }, `${o.name}()`),
            o.readable ? h("span", { class: "badge" }, "Table") : null,
            p.changes?.added.includes(o.name) ? h("span", { class: "badge" }, "New") : p.changes?.changed.includes(o.name) ? h("span", { class: "badge" }, "Changed") : null,
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
        p.taken ? h("p", { class: "status-error" }, p.taken) : null,
        summary ? h("p", { class: "hint" }, summary) : null,
        h("p", { class: "hint" }, `${p.spec.title} · ${p.spec.source} · ${count(p.spec.operations.length, "operation")} · ${count(p.spec.tables.length, "table")}`),
        ops,
        p.variables.length > 1 ? h("p", { class: "hint add-api-variables" }, ...p.variables.slice(1).map((v) => h("code", { title: v.required ? "Needed" : "Optional" }, v.name))) : null,
      );
    };

    // ===== Add =====
    const add = button("Add", () => void save(), { icon: "plus", class: "primary" });
    add.disabled = true;
    const save = async (): Promise<void> => {
      const body = sent();
      if (!body || !plan) return;
      add.disabled = true;
      try {
        const done = await api<Plan & { saved: { name: string } }>("/apis", "POST", body);
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
    clear(
      body,
      h("h3", {}, "Add API"),
      h("div", { class: "add-api" },
        h("label", { class: "field" }, h("span", {}, "Preset"), preset),
        h("label", { class: "field" }, h("span", {}, "Name"), name),
        h("div", { class: "segmented", role: "group", "aria-label": "From" }, documentTab, formTab),
        documentPart,
        formPart,
        h("label", { class: "field" }, h("span", {}, "Base URL"), h("span", { class: "field-row" }, baseUrl, find)),
        h("fieldset", { class: "connection-passwords add-api-auth" }, h("legend", {}, "Sign in"), h("label", { class: "field" }, h("span", {}, "Type"), authType), settingsHost),
        h("label", { class: "field" }, h("span", {}, "Folder"), h("span", { class: "field-row" }, folder, folderBrowse)),
        status,
      ),
    );
    foot.append(button("Back", host.back, { icon: "back" }), add);
    url.focus();
  }
}
