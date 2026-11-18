/**
 * library.ts: the meta store (the library, Plans/library.plan.md: connections, APIs, vaults, blades, relationship
 * sets, variables, colours and the shared catalog in one folder made to be a Git repository). [SHARED]
 *
 *   [SETTINGS]  Settings' Meta store folder (the library folder; the owner, 2026-11-18: "Meta store folder in
 *               settings"): where it is, Change… (a clone of the team's GitHub repository) and Default, what is
 *               in it, the shared catalog's counts and the last change picked up from the folder
 *   [SETUP]     Set up from the meta store: the count at the top, each key vault (readable here, or its
 *               sign-in and Check again), each value to type once (the keyring, local/variables.toml, a
 *               connection's password), each connection's status, the shared projects not set up here, and
 *               Move to a vault for a keyring password
 *   [NOTICES]   said once: the move into the library, an older project's blades, a team's meta store pointed
 *               at (library_notice), a pull's catalog change (catalog_changed from the folder)
 *
 * ROUTING: GET/PUT /library · GET /library/setup · POST /library/setup/move-to-vault · POST /library/notices ·
 * PUT /variables · PUT /blades/{name}/secrets · notices library_changed, library_notice, catalog_changed
 */
import { api, onNotice } from "./api";
import { button, h, icon, toast } from "./dom";
import { chooseFile } from "./fileChooser";

interface Info {
  folder: string;
  default: string;
  is_default: boolean;
  git: boolean;
  counts: Record<string, number>;
  local: string[];
  never: string[];
  catalog?: { connections: number; tables: number; gone: number; picked_up: string; not_here: string[]; problems: { file: string; error: string }[] };
}

interface Fix {
  kind: string;
  label: string;
  how?: string;
  name?: string;
  connection?: string;
}

interface Setup {
  heading: string;
  count: number;
  ready: boolean;
  words: string;
  vaults: { name: string; state: string; words: string; error: string; gives: string; fix: Fix | null }[];
  values: { name: string; kind: string; words: string; connection?: string; fix: Fix }[];
  connections: { name: string; state: string; words: string; move_to_vault: { secret: string; vaults: string[] }[] }[];
  projects: { name: string; words: string }[];
}

const COUNT_WORDS: [string, string][] = [
  ["connections", "connections"],
  ["vaults", "key vaults"],
  ["apis", "APIs"],
  ["blades", "blades"],
  ["relationship_sets", "relationship sets"],
];

const present = (...nodes: (Node | null)[]): Node[] => nodes.filter((n): n is Node => n !== null);

const when = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
};

/** Settings' Meta store folder section, with Set up from the meta store under it. */
export function librarySection(): HTMLElement {
  const body = h("div", { class: "library-settings" });
  const setup = h("div", { class: "library-setup" });
  const draw = async (): Promise<void> => {
    let info: Info;
    try {
      info = await api<Info>("/library");
    } catch (e) {
      body.replaceChildren(h("p", { class: "status-error" }, (e as Error).message));
      return;
    }
    const use = (folder: string | null): void =>
      void api<Info>("/library", "PUT", { folder }).then(
        () => {
          toast(folder ? `The meta store is ${folder} now.` : "The meta store is the default folder now.");
          void draw();
          void drawSetup(true);
        },
        (e: Error) => toast(e.message, "error"),
      );
    const counts = COUNT_WORDS.map(([key, words]) => `${info.counts[key] ?? 0} ${words}`).join(" · ");
    const catalog = info.catalog;
    body.replaceChildren(
      ...present(
      h("p", { class: "hint" }, "Connections, key vaults, variables and the shared catalog: point it at your clone of the team's GitHub repository."),
      h("p", { class: "library-folder" }, h("code", { class: "mono" }, info.folder), info.git ? h("span", { class: "chip" }, "Git") : null),
      h("p", { class: "hint library-counts" }, counts),
      catalog
        ? h(
            "p",
            { class: "hint library-catalog" },
            `Shared catalog: ${catalog.connections} connection${catalog.connections === 1 ? "" : "s"} · ${catalog.tables} table${catalog.tables === 1 ? "" : "s"}`,
            catalog.picked_up ? ` · Last change picked up from the folder: ${when(catalog.picked_up)}` : "",
          )
        : null,
      ...(catalog?.problems ?? []).map((p) => h("p", { class: "status-error library-problem" }, p.error)),
      h(
        "div",
        { class: "row" },
        button("Change…", () => void chooseFile({ title: "The meta store folder", mode: "folder", start: info.folder }).then((f) => f && use(f)), { icon: "folder" }),
        info.is_default ? null : button("Default", () => use(null), { class: "ghost", title: info.default }),
      ),
      h("p", { class: "hint" }, "A Git repository's working copy: commit, push and pull it with your own tools. Never in it: ", info.never.join(", "), ". This computer only: local/ and the keyring."),
      ),
    );
  };
  // ===== SETUP =====
  const drawSetup = async (check = false): Promise<void> => {
    let s: Setup;
    try {
      s = await api<Setup>(check ? "/library/setup?check=1" : "/library/setup");
    } catch (e) {
      setup.replaceChildren(h("p", { class: "status-error" }, (e as Error).message));
      return;
    }
    const typed = (fix: Fix, connection?: string): HTMLElement => {
      const input = h("input", { type: fix.kind === "local" ? "text" : "password", class: "setup-value", "aria-label": fix.label, placeholder: fix.label, autocomplete: "off" });
      const save = (): void => {
        const value = input.value;
        if (!value) return;
        const done =
          fix.kind === "password"
            ? api(`/blades/${encodeURIComponent(connection ?? fix.connection ?? "")}/secrets`, "PUT", { [fix.name ?? ""]: value })
            : api("/variables", "PUT", fix.kind === "local" ? { name: fix.name, value, local: true } : { name: fix.name, value, from: "keyring" });
        void done.then(() => void drawSetup(), (e: Error) => toast(e.message, "error"));
      };
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") save();
      });
      return h("span", { class: "setup-fix" }, input, button("Save", save, { class: "small line" }));
    };
    const moveTo = (connection: string, secret: string, vaults: string[]): HTMLElement => {
      const pick = h("select", { "aria-label": "The key vault" }, ...vaults.map((v) => h("option", { value: v }, v)));
      const name = h("input", { type: "text", placeholder: "The secret's name in the vault", "aria-label": "The secret's name in the vault", value: `${connection}-${secret}`.toLowerCase().replace(/[^a-z0-9-]+/g, "-") });
      return h(
        "span",
        { class: "setup-fix" },
        pick,
        name,
        button("Move to a vault", () => void api("/library/setup/move-to-vault", "POST", { connection, secret, vault: pick.value, vault_secret: name.value }).then(
          () => { toast(`${connection}'s ${secret} now comes from ${pick.value}.`); void drawSetup(); },
          (e: Error) => toast(e.message, "error"),
        ), { class: "small line", icon: "key" }),
      );
    };
    const item = (state: string, words: string, ...more: (HTMLElement | null)[]): HTMLElement =>
      h("li", { class: `setup-item setup-${state}` }, icon(state === "ready" || state === "works" ? "check" : state === "local" ? "warning" : "problem"), h("span", { class: "setup-words" }, words), ...more);
    setup.replaceChildren(
      ...present(
      h("h3", { class: "setup-heading" }, s.heading, h("span", { class: `chip ${s.ready ? "setup-ready" : "setup-todo"}` }, s.words)),
      s.vaults.length ? h("h4", {}, "Key vaults") : null,
      s.vaults.length
        ? h("ul", { class: "setup-list" }, ...s.vaults.map((v) => item(v.state, `${v.name}: ${v.words}`, h("span", { class: "hint" }, v.fix ? `${v.gives} · ${v.fix.how ?? ""}` : v.gives), v.error ? h("span", { class: "hint setup-error", title: v.error }, v.error) : null)))
        : null,
      s.values.length ? h("h4", {}, "Needs a value on this computer") : null,
      s.values.length ? h("ul", { class: "setup-list" }, ...s.values.map((v) => item("todo", v.words, typed(v.kind === "password" ? { ...v.fix, name: v.name } : v.fix, v.connection)))) : null,
      s.connections.length ? h("h4", {}, "Connections") : null,
      s.connections.length
        ? h("ul", { class: "setup-list" }, ...s.connections.map((c) => item(c.state, `${c.name}: ${c.words}`, ...c.move_to_vault.map((m) => moveTo(c.name, m.secret, m.vaults)))))
        : null,
      s.projects.length ? h("h4", {}, "Shared projects") : null,
      s.projects.length ? h("ul", { class: "setup-list" }, ...s.projects.map((p) => item("todo", p.words))) : null,
      h("div", { class: "row" }, button("Check again", () => void drawSetup(true), { icon: "reset", class: "small line" })),
      ),
    );
  };
  void draw();
  void drawSetup();
  onNotice((n) => {
    if (!body.isConnected) return;
    if (n.type === "library_changed" || n.type === "catalog_changed") void draw();
    if (n.type === "library_changed" || n.type === "variables_changed" || n.type === "blades_changed") void drawSetup();
  });
  return h(
    "fieldset",
    { class: "fieldset library-fieldset" },
    h("legend", {}, icon("folder"), "Meta store folder"),
    body,
    setup,
  );
}

let listening = false;

/** What the meta store says once on this page: the move into it, a team's meta store pointed at, a pull's
 * catalog change. */
export function libraryNotices(): void {
  if (listening) return;
  listening = true;
  onNotice((n) => {
    const said = n as { text?: string; words?: string; from?: string; changed?: number };
    if (n.type === "library_notice" && said.text) toast(said.text);
    if (n.type === "catalog_changed" && said.from === "folder" && said.changed && said.words) toast(said.words);
  });
  void api<{ notices: { text: string }[] }>("/library/notices", "POST").then(
    (r) => r.notices.forEach((n) => toast(n.text)),
    () => undefined,
  );
}
