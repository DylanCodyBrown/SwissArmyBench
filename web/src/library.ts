/**
 * library.ts: Settings' Team box and the library's notices. [SHARED]
 *
 * The owner (2026-11-19): "you have made linking a meta store and shared project folder way too difficult; the
 * settings menu makes no sense". A team is ONE GitHub repository: the team library (connections, key vaults,
 * variables, blades, APIs, relationship sets, colours, the shared catalog) at its top, the team's shared
 * projects in its projects/. The screen says Team library; the code keeps library, shared_folder, sync.
 *
 *   [TEAM]      no team: one line, Join a team… and Start a team…; joined: one row, "Team: owner/repo", its
 *               sync words only when something is to do (design principle 7.9), Pull, Push and "…" (Open on
 *               GitHub, Set up this computer, Show its folder, Leave the team); the local projects folder's row
 *               (projectExplorer.ts); Advanced (folded): the team library's folder and the shared projects
 *               folder as their own paths
 *   [FLOW]      Join a team… / Start a team…: one dialog, each step only when needed: GitHub sync's Install
 *               (the app restarts: the step is kept by the server, team.json, and taken up here after),
 *               Sign in (scmPage.ts teamSignIn), the repository (search, newest first) or a new one's owner
 *               and name, then Set up this computer inline
 *   [SETUP]     Set up this computer: the count at the top, each key vault (readable here, or its sign-in and
 *               Check again), each value to type once (the keyring, local/variables.toml, a connection's
 *               password), each connection's status, the shared projects not set up here, and Move to a vault
 *   [NOTICES]   said once: the move into the library, an older project's blades, a team library pointed at
 *               (library_notice), a pull's catalog change (catalog_changed from the folder); a step kept over
 *               Install's restart opens Settings on the Team box (libraryNotices, the home window only)
 *
 * ROUTING: GET /team, /team/repositories, /team/owners · POST /team/join, /team/start, /team/leave, /team/pull,
 * /team/push, /team/pending, /team/show · GET/PUT /library · GET /library/setup · POST /library/setup/move-to-vault
 * · POST /library/notices · POST /extensions/install · PUT /variables · PUT /blades/{name}/secrets · notices
 * team_changed, sync_changed, library_changed, library_notice, catalog_changed
 */
import { api, onNotice, onNoticeWhile } from "./api";
import { button, h, icon, openDialog, showMenu, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { busy, busyClick, loadingBlock } from "./loading";
import { openLayer } from "./nav";
import { localProjectsRow, sharedProjectsRow } from "./projectExplorer";
import { teamSignIn } from "./scmPage";
import { errorHere, errorNote } from "./errorNote";

type Action = "join" | "start";

interface TeamStatus {
  state: "none" | "joined";
  sync_on: boolean;
  needs: { id: string; name: string; words: string; installable: boolean } | null;
  signed_in: boolean;
  account: string | null;
  device: boolean;
  token_steps: string[];
  pending: { action: Action; step: string } | null;
  library_folder: string;
  library_default: boolean;
  shared_folder: string | null;
  team?: { repository: string; folder: string; projects: string; url: string | null; sync: { state: string; words: string } | null };
}

interface Repository {
  repository: string;
  private: boolean;
  pushed: string;
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

const present = (...nodes: (Node | null)[]): Node[] => nodes.filter((n): n is Node => n !== null);

const day = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString();
};

// ===== SETUP =====

/** Set up this computer's checklist, drawn into `host` (the Team box's flow, and "…", Set up this computer). */
function setupChecklist(host: HTMLElement): (check?: boolean) => Promise<void> {
  const draw = async (check = false): Promise<void> => {
    let s: Setup;
    try {
      s = await api<Setup>(check ? "/library/setup?check=1" : "/library/setup");
    } catch (e) {
      host.replaceChildren(errorNote(e));
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
        void done.then(() => void draw(), (e: Error) => errorHere(e));
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
        button(
          "Move to a vault",
          () =>
            void api("/library/setup/move-to-vault", "POST", { connection, secret, vault: pick.value, vault_secret: name.value }).then(
              () => {
                toast(`${connection}'s ${secret} now comes from ${pick.value}.`);
                void draw();
              },
              (e: Error) => errorHere(e),
            ),
          { class: "small line", icon: "key" },
        ),
      );
    };
    const item = (state: string, words: string, ...more: (HTMLElement | null)[]): HTMLElement =>
      h("li", { class: `setup-item setup-${state}` }, icon(state === "ready" || state === "works" ? "check" : state === "local" ? "warning" : "problem"), h("span", { class: "setup-words" }, words), ...more);
    host.replaceChildren(
      ...present(
        h("h3", { class: "setup-heading" }, s.heading, h("span", { class: `chip ${s.ready ? "setup-ready" : "setup-todo"}` }, s.words)),
        s.vaults.length ? h("h4", {}, "Key vaults") : null,
        s.vaults.length
          ? h("ul", { class: "setup-list" }, ...s.vaults.map((v) => item(v.state, `${v.name}: ${v.words}`, h("span", { class: "hint" }, v.fix ? `${v.gives} · ${v.fix.how ?? ""}` : v.gives), v.error ? h("span", { class: "hint setup-error", title: v.error }, v.error) : null)))
          : null,
        s.values.length ? h("h4", {}, "Needs a value on this computer") : null,
        s.values.length ? h("ul", { class: "setup-list" }, ...s.values.map((v) => item("todo", v.words, typed(v.kind === "password" ? { ...v.fix, name: v.name } : v.fix, v.connection)))) : null,
        s.connections.length ? h("h4", {}, "Connections") : null,
        s.connections.length ? h("ul", { class: "setup-list" }, ...s.connections.map((c) => item(c.state, `${c.name}: ${c.words}`, ...c.move_to_vault.map((m) => moveTo(c.name, m.secret, m.vaults))))) : null,
        s.projects.length ? h("h4", {}, "Shared projects") : null,
        s.projects.length ? h("ul", { class: "setup-list" }, ...s.projects.map((p) => item("todo", p.words))) : null,
        h("div", { class: "row" }, button("Check again", busyClick("Checking…", () => draw(true)), { icon: "reset", class: "small line" })),
      ),
    );
  };
  onNoticeWhile(host, (n) => {
    if ((n.type === "library_changed" || n.type === "variables_changed" || n.type === "blades_changed")) void draw();
  });
  return draw;
}

function openSetup(): void {
  const { dialog, body } = openDialog("Set up this computer", true);
  dialog.classList.add("team-setup-dialog");
  const host = h("div", { class: "library-setup" }, loadingBlock("Checking what this computer needs…"));
  body.append(host);
  void setupChecklist(host)(true);
}

// ===== FLOW: Join a team…, Start a team… =====

const STEP_NAMES: Record<Action, [string, string][]> = {
  join: [["install", "GitHub sync"], ["sign_in", "Sign in"], ["pick", "Repository"], ["setup", "Set up"]],
  start: [["install", "GitHub sync"], ["sign_in", "Sign in"], ["name", "Name"], ["setup", "Set up"]],
};

let flowOpen = false;

/** The one dialog that walks Join a team… or Start a team…, from the first step still to do. */
export function openTeamFlow(action: Action): void {
  if (flowOpen) return;
  flowOpen = true;
  const { dialog, body, close } = openDialog(action === "join" ? "Join a team" : "Start a team");
  dialog.classList.add("team-flow");
  dialog.dataset.action = action;
  dialog.addEventListener("close", () => {
    flowOpen = false;
  });
  const strip = h("ol", { class: "team-steps", "aria-label": "Steps" });
  const page = h("div", { class: "team-step" });
  body.append(strip, page);

  const mark = (at: string): void => {
    const steps = STEP_NAMES[action];
    const index = steps.findIndex(([k]) => k === at);
    strip.replaceChildren(
      ...steps.map(([key, name], i) =>
        h("li", { class: `team-step-name ${i < index ? "done" : i === index ? "current" : ""}`, "data-step": key, "aria-current": i === index ? "step" : undefined }, i < index ? icon("check") : h("span", { class: "team-step-number" }, String(i + 1)), name),
      ),
    );
    dialog.dataset.step = at;
  };

  const next = async (): Promise<void> => {
    let s: TeamStatus;
    try {
      s = await busy(page, "Looking at this computer…", api<TeamStatus>("/team"));
    } catch {
      return;
    }
    const at = !s.sync_on ? "install" : !s.signed_in ? "sign_in" : action === "join" ? "pick" : "name";
    mark(at);
    if (at === "install") install(s);
    else if (at === "sign_in") page.replaceChildren(teamSignIn(s, () => void next()));
    else if (at === "pick") void pick();
    else void name(s);
  };

  const install = (s: TeamStatus): void => {
    const needs = s.needs;
    const go = button(
      "Install",
      busyClick("Installing…", async () => {
        await api("/team/pending", "POST", { action });
        try {
          const done = await api<{ changing?: unknown }>("/extensions/install", "POST", { id: needs?.id });
          if (done.changing) page.replaceChildren(h("h3", { class: "team-step-title" }, needs?.words ?? ""), loadingBlock(`Installing ${needs?.name ?? ""}: the app starts again and Settings opens here.`));
        } catch (e) {
          await api("/team/pending", "POST", { action: null }).catch(() => undefined);
          page.append(errorNote(e));
        }
      }),
      { icon: "extensions", class: "primary team-install" },
    );
    page.replaceChildren(h("h3", { class: "team-step-title" }, needs?.words ?? ""), h("div", { class: "row" }, go));
  };

  const pick = async (): Promise<void> => {
    let found: Repository[];
    try {
      found = (await busy(page, "Asking GitHub for your repositories…", api<{ repositories: Repository[] }>("/team/repositories"))).repositories;
    } catch {
      return;
    }
    const search = h("input", { type: "search", class: "input team-search", placeholder: "Search", "aria-label": "Search the repositories", autocomplete: "off" });
    const list = h("ul", { class: "team-repos", role: "listbox", "aria-label": "Repositories" });
    const join = (repository: string): void => {
      void busy(page, `Copying ${repository}…`, api<{ joined: string }>("/team/join", "POST", { repository })).then(
        () => setup(repository),
        () => undefined,
      );
    };
    const draw = (): void => {
      const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
      const shown = found.filter((r) => words.every((w) => r.repository.toLowerCase().includes(w)));
      list.replaceChildren(
        ...(shown.length
          ? shown.map((r) =>
              h(
                "li",
                { role: "option" },
                h("button", { type: "button", class: "team-repo", "data-repository": r.repository, onclick: () => join(r.repository) }, icon("source-control"), h("span", { class: "team-repo-name" }, r.repository), r.private ? h("span", { class: "chip" }, "Private") : null, h("span", { class: "hint team-repo-day" }, day(r.pushed))),
              ),
            )
          : [h("li", { class: "hint team-repos-none" }, "No repository")]),
      );
    };
    search.addEventListener("input", draw);
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") list.querySelector<HTMLButtonElement>(".team-repo")?.click();
    });
    draw();
    page.replaceChildren(search, list);
    search.focus();
  };

  const name = async (s: TeamStatus): Promise<void> => {
    let owners: string[];
    try {
      owners = (await busy(page, "Asking GitHub who can own it…", api<{ owners: string[] }>("/team/owners"))).owners;
    } catch {
      return;
    }
    const owner = h("select", { class: "team-owner", "aria-label": "Owner" }, ...owners.map((o) => h("option", { value: o }, o)));
    const input = h("input", { type: "text", class: "input team-name", value: "team-library", "aria-label": "Repository name", autocomplete: "off", spellcheck: "false" });
    const start = (): void => {
      const body_ = { name: input.value, owner: owner.value === s.account ? null : owner.value };
      void busy(page, `Making ${owner.value}/${input.value.trim()} on GitHub…`, api<{ started: string }>("/team/start", "POST", body_)).then(
        (done) => setup(done.started),
        () => undefined,
      );
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") start();
    });
    page.replaceChildren(
      h("div", { class: "team-new-name" }, owner, h("span", { class: "team-slash" }, "/"), input),
      h("p", { class: "hint" }, "Private. Your library goes in; passwords never do."),
      h("div", { class: "row" }, button("Start the team", start, { icon: "plus", class: "primary team-create" })),
    );
    input.select();
  };

  const setup = (repository: string): void => {
    mark("setup");
    const host = h("div", { class: "library-setup" }, loadingBlock("Checking what this computer needs…"));
    page.replaceChildren(h("h3", { class: "team-step-title team-joined-title" }, icon("check"), `Team: ${repository}`), host, h("div", { class: "row team-done" }, button("Done", close, { class: "primary" })));
    void setupChecklist(host)(true);
  };

  void next();
}

// ===== TEAM =====

/** Settings' Team box, first after Theme: no team (Join a team…, Start a team…) or joined (one row), the local
 *  projects folder, Advanced (folded). */
export function teamSection(): HTMLElement {
  const main = h("div", { class: "team-main" });
  const libraryRow = h("div", { class: "team-advanced-row library-row" });
  const advanced = h("details", { class: "team-advanced" }, h("summary", {}, "Advanced"), libraryRow, sharedProjectsRow(), h("div", { class: "row" }, button("Set up this computer", openSetup, { icon: "check", class: "small line team-setup" })));
  let resumed = false;

  const act = (route: string): Promise<unknown> =>
    api<{ words?: string }>(route, "POST").then(
      (d) => {
        if (d.words) toast(d.words);
        void draw();
      },
      (e: Error) => errorHere(e),
    );

  const leave = (s: TeamStatus): void => {
    const repository = s.team?.repository ?? "";
    const { body, foot, close } = openDialog(`Leave ${repository}`);
    body.append(h("p", {}, "Keep a copy of the team's connections, vaults, variables and blades in this computer's own library?"));
    const go = (keep: boolean) => (): void => {
      void api<{ words: string }>("/team/leave", "POST", { keep }).then(
        (done) => {
          close();
          toast(done.words);
          void draw();
        },
        (e: Error) => errorHere(e),
      );
    };
    foot.append(button("Keep a copy", go(true), { class: "primary team-leave-keep" }), button("Leave without a copy", go(false), { class: "line team-leave-plain" }), button("Cancel", close, { class: "ghost" }));
  };

  const drawLibraryRow = (s: TeamStatus): void => {
    const use = (folder: string | null): void =>
      void api("/library", "PUT", { folder }).then(
        () => void draw(),
        (e: Error) => errorHere(e),
      );
    libraryRow.replaceChildren(
      h("span", { class: "team-advanced-label" }, "Team library folder"),
      h("code", { class: "mono library-folder-path" }, s.library_folder),
      button("Change…", () => void chooseFile({ title: "The team library folder", mode: "folder", start: s.library_folder }).then((f) => f && use(f)), { icon: "folder", class: "small line" }),
      ...(s.library_default ? [] : [button("Default", () => use(null), { class: "ghost small" })]),
    );
  };

  const draw = async (remote = false): Promise<void> => {
    let s: TeamStatus;
    try {
      s = await api<TeamStatus>(remote ? "/team?remote=1" : "/team");
    } catch (e) {
      main.replaceChildren(errorNote(e));
      return;
    }
    drawLibraryRow(s);
    const team = s.team;
    if (s.state === "joined" && team) {
      const more = button(
        "More",
        (e) => {
          const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
          showMenu(r.left, r.bottom + 4, team.repository, [
            ["globe", "Open on GitHub", () => team.url && window.open(team.url, "_blank", "noopener"), team.url ? undefined : "GitHub sync is not installed"],
            ["check", "Set up this computer", openSetup],
            ["folder", "Show its folder", () => void api("/team/show", "POST").catch((error: Error) => errorHere(error))],
            "-",
            ["close", "Leave the team", () => leave(s)],
          ]);
        },
        { icon: "more", iconOnly: true, class: "ghost team-more" },
      );
      main.replaceChildren(
        h(
          "div",
          { class: "team-joined" },
          icon("user"),
          h("span", { class: "team-name-words" }, "Team: ", h("strong", {}, team.repository)),
          team.sync ? h("span", { class: `team-sync team-sync-${team.sync.state}` }, team.sync.words) : null,
          h("span", { class: "team-actions" }, button("Pull", busyClick("Pulling…", () => act("/team/pull")), { class: "small line team-pull" }), button("Push", busyClick("Pushing…", () => act("/team/push")), { class: "small line team-push" }), more),
        ),
      );
    } else {
      main.replaceChildren(
        h("p", { class: "team-none" }, "Share connections, variables and projects with your team."),
        h("div", { class: "row" }, button("Join a team…", () => openTeamFlow("join"), { icon: "user", class: "primary team-join" }), button("Start a team…", () => openTeamFlow("start"), { icon: "plus", class: "line team-start" })),
      );
    }
    if (s.pending && !resumed) {
      resumed = true;
      openTeamFlow(s.pending.action);
    }
  };
  void draw(true);
  onNoticeWhile(main, (n) => {
    if (n.type === "team_changed" || n.type === "sync_changed" || n.type === "library_changed") void draw();
  });
  return h("fieldset", { class: "fieldset team-fieldset" }, h("legend", {}, icon("user"), "Team"), main, localProjectsRow(), advanced);
}

// ===== NOTICES =====

let listening = false;

/** What the library says once on this page: the move into it, a team library pointed at, a pull's catalog
 * change; and a Join or Start kept over Install's restart: Settings opens on the Team box, which goes on. */
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
  void api<TeamStatus>("/team").then(
    (s) => {
      if (s.pending) openLayer("settings");
    },
    () => undefined,
  );
}
