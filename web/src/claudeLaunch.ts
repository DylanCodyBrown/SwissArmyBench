/**
 * claudeLaunch.ts: Launch Claude in the status bars, Settings' Claude, and the palettes' commands. [SHARED]
 *
 * The owner (2026-11-16): "a launch claude command on the home page in the bottom footer use a claude icon,
 * when its clicked it should start a claude code cli session in the proper folder so the claude agent
 * inherits the context it needs to understand SAB"; "with a setting in the settings go launch it with bypass
 * permissions"; and "a launcher that checks the machine for the installed claude desktop app and launch it
 * the same way ... dynamically finding it will be the key".
 *
 *   [LAUNCH]     the status bar's button: straight to the one Claude found, a small menu when both are
 *                (Claude Code in a terminal, Claude Desktop), the install help when none is
 *   [DESKTOP]    the first time a Desktop install's config file is written: one plain question
 *   [SETTINGS]   which Claude Code and which Claude Desktop (what was found, or Other…), bypass permissions
 *                mode (Claude Code; off unless turned on), a Desktop's config file when the search cannot tell
 *
 * The server does the finding, the files and the starting (services/claude.py); the page never builds a
 * command. ROUTING: GET/PUT /claude, POST /claude/launch
 */
import { api } from "./api";
import { button, h, icon, openDialog, showMenu, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import type { Command } from "./workbenchCommands";
import { busyClick } from "./loading";

type Kind = "code" | "desktop";

interface Found {
  kind: Kind;
  path: string;
  name: string;
  source: string;
  official: boolean;
}

interface Help {
  kind: Kind;
  message: string;
  commands: string[];
  url: string;
}

interface Config {
  path: string;
  known: boolean;
  places: string[];
  allowed?: boolean;
}

interface Side {
  found: Found[];
  chosen: string | null;
  help: Help | null;
  config?: Config;
}

export interface ClaudeState {
  platform: string;
  bypass: boolean;
  code: Side;
  desktop: Side;
}

interface Launched {
  launched: Kind | null;
  choose?: Kind[];
  missing?: Help[];
  confirm?: Config;
  config_unknown?: Config;
  error?: string;
  terminal?: string;
  bypass?: boolean;
  changed?: boolean;
  backup?: string | null;
}

const NAMES: Record<Kind, string> = { code: "Claude Code", desktop: "Claude Desktop" };

let state: ClaudeState | null = null;

async function load(refresh = false): Promise<ClaudeState | null> {
  try {
    state = await api<ClaudeState>(refresh ? "/claude?refresh=1" : "/claude");
  } catch {
    state = null; // an older server: no Launch Claude
  }
  return state;
}

/** The status bar's Launch Claude (its icon our own line drawing, never a company's logo). */
export function launchButton(): HTMLButtonElement {
  const launch = h("button", { type: "button", class: "claude-launch", "aria-label": "Launch Claude" }, icon("claude"), h("span", { class: "claude-launch-label" }, "Launch Claude")) as HTMLButtonElement;
  launch.addEventListener("click", () => {
    const box = launch.getBoundingClientRect();
    void launchClaude(undefined, { x: box.left, y: box.top - 8 });
  });
  return launch;
}

/** Launch Claude: the one found, the user's pick when both are, the install help when none is. */
export async function launchClaude(app?: Kind, at?: { x: number; y: number }, confirmed = false): Promise<void> {
  let answer: Launched;
  try {
    answer = await api<Launched>("/claude/launch", "POST", { ...(app ? { app } : {}), ...(confirmed ? { confirmed } : {}) });
  } catch (e) {
    toast((e as Error).message, "error");
    return;
  }
  if (answer.choose) {
    const x = at?.x ?? window.innerWidth / 2;
    const y = at?.y ?? window.innerHeight / 2;
    showMenu(x, y, "Launch Claude", [
      ["claude", "Claude Code in a terminal", () => void launchClaude("code")],
      ["claude", "Claude Desktop", () => void launchClaude("desktop")],
    ]);
    return;
  }
  if (answer.missing) {
    showMissing(answer.missing);
    return;
  }
  if (answer.confirm) {
    askToWrite(answer.confirm);
    return;
  }
  if (answer.config_unknown) {
    askForConfig(answer.config_unknown);
    return;
  }
  if (answer.error) {
    toast(answer.error, "error");
    return;
  }
  if (answer.launched === "code") toast(`Claude Code started in ${answer.terminal ?? "a terminal"}${answer.bypass ? " (bypass permissions)" : ""}.`);
  if (answer.launched === "desktop") toast(answer.changed ? "Claude Desktop started. If it was already open, quit it and start it again to load Swiss Army Bench." : "Claude Desktop started.");
}

/** None found: what to install, its commands to copy, and where to choose an install the search missed. */
function showMissing(missing: Help[]): void {
  const first: Kind = missing[0]?.kind ?? "code";
  const { dialog, body, foot, close } = openDialog(missing.length > 1 ? "Claude is not installed" : `${NAMES[first]} is not installed`);
  dialog.classList.add("claude-missing");
  for (const help of missing) {
    body.append(
      h(
        "section",
        { class: "claude-help", "data-kind": help.kind },
        h("h3", {}, icon("claude"), NAMES[help.kind]),
        ...help.commands.map((command) =>
          h(
            "div",
            { class: "claude-command" },
            h("code", { class: "mono" }, command),
            button("Copy", () => void navigator.clipboard.writeText(command).then(() => toast("Copied.")), { icon: "copy", iconOnly: true }),
          ),
        ),
        h("a", { href: help.url, target: "_blank", rel: "noopener noreferrer" }, help.kind === "code" ? "Claude Code's setup" : "Download Claude Desktop"),
      ),
    );
  }
  foot.append(
    button("Choose its file…", () => {
      close();
      void chooseOther(first).then((ok) => {
        if (ok) void launchClaude(first);
      });
    }, { icon: "folder" }),
    button("Look again", () => {
      close();
      void load(true).then(() => launchClaude());
    }, { icon: "reset", class: "primary" }),
  );
  dialog.showModal();
}

/** The first time this app writes into a Claude Desktop install's config: one plain question. */
function askToWrite(config: Config): void {
  const { dialog, body, foot, close } = openDialog("Add Swiss Army Bench to Claude Desktop?");
  dialog.classList.add("claude-confirm");
  body.append(
    h("p", {}, "Its MCP settings get a swissarmybench server; everything else in the file stays, and a copy of it is kept first."),
    h("code", { class: "mono claude-config-path" }, config.path),
  );
  foot.append(
    button("Cancel", close),
    button("Add and start", () => {
      close();
      void launchClaude("desktop", undefined, true);
    }, { class: "primary", icon: "check" }),
  );
  dialog.showModal();
}

/** A company's build with no config file where one would be: the user names it (or uses the likeliest). */
function askForConfig(config: Config): void {
  const { dialog, body, foot, close } = openDialog("Where does this Claude Desktop keep its settings?");
  dialog.classList.add("claude-confirm");
  body.append(h("p", {}, "No claude_desktop_config.json was found for it. The likeliest place:"), h("code", { class: "mono claude-config-path" }, config.path));
  foot.append(
    button("Choose the file…", () => {
      close();
      void chooseConfig().then((done) => {
        if (done) void launchClaude("desktop");
      });
    }, { icon: "folder" }),
    button("Use this place", () => {
      close();
      void launchClaude("desktop", undefined, true);
    }, { class: "primary", icon: "check" }),
  );
  dialog.showModal();
}

async function chooseOther(kind: Kind): Promise<boolean> {
  const path = await chooseFile({ title: `Choose ${NAMES[kind]}`, mode: "file" });
  if (!path) return false;
  try {
    state = await api<ClaudeState>("/claude", "PUT", { [kind]: path });
    return true;
  } catch (e) {
    toast((e as Error).message, "error");
    return false;
  }
}

async function chooseConfig(): Promise<boolean> {
  const desktop = state?.desktop.chosen ?? (await load())?.desktop.chosen;
  if (!desktop) return false;
  const path = await chooseFile({ title: "Choose claude_desktop_config.json", mode: "save", name: "claude_desktop_config.json", start: state?.desktop.config?.path });
  if (!path) return false;
  try {
    state = await api<ClaudeState>("/claude", "PUT", { config: { [desktop]: path } });
    return true;
  } catch (e) {
    toast((e as Error).message, "error");
    return false;
  }
}

/** Settings' Claude: which Claude Code and Claude Desktop (found, or Other…), bypass permissions mode. */
export function claudeSection(): HTMLElement {
  const lists = h("div", { class: "claude-installs" });
  const bypass = h("input", { type: "checkbox", class: "claude-bypass" }) as HTMLInputElement;
  const draw = (): void => {
    lists.replaceChildren(...(["code", "desktop"] as Kind[]).map((kind) => side(kind)));
    bypass.checked = state?.bypass === true;
  };
  const side = (kind: Kind): HTMLElement => {
    const s = state?.[kind];
    const found = s?.found ?? [];
    const select = h(
      "select",
      { "aria-label": NAMES[kind], class: `claude-choice`, "data-kind": kind, disabled: !found.length },
      ...(found.length ? found.map((f) => h("option", { value: f.path, selected: f.path === s?.chosen, title: f.source }, kind === "desktop" && f.name !== "Claude" ? `${f.name}: ${f.path}` : f.path)) : [h("option", { value: "" }, "Not found")]),
    ) as HTMLSelectElement;
    select.addEventListener("change", () => void put({ [kind]: select.value }));
    const row = h(
      "div",
      { class: "claude-side" },
      h("span", { class: "claude-side-name" }, NAMES[kind]),
      select,
      button("Other…", () => void chooseOther(kind).then(draw), { icon: "folder", class: "ghost" }),
    );
    if (kind === "desktop" && s?.config) {
      row.append(
        h("span", { class: "claude-side-name" }, "Its settings file"),
        h("code", { class: "mono claude-config-path", title: s.config.known ? "" : "Not found: the likeliest place" }, s.config.path),
        button("Choose…", () => void chooseConfig().then(draw), { icon: "folder", class: "ghost" }),
      );
    }
    return row;
  };
  const put = async (body: Record<string, unknown>): Promise<void> => {
    try {
      state = await api<ClaudeState>("/claude", "PUT", body);
    } catch (e) {
      toast((e as Error).message, "error");
    }
    draw();
  };
  bypass.addEventListener("change", () => void put({ bypass: bypass.checked }));
  void load().then(draw);
  return h(
    "fieldset",
    { class: "fieldset claude-fieldset" },
    h("legend", {}, icon("claude"), "Claude"),
    lists,
    h(
      "div",
      { class: "updates-row" },
      h("label", { class: "check" }, bypass, "Start Claude Code with bypass permissions"),
      button("Look again", busyClick("Looking…", () => load(true).then(draw)), { icon: "reset", class: "ghost" }),
    ),
  );
}

/** The palette's commands (the Workbench's registry, the grid page's list). */
export function claudeCommands(): Command[] {
  return [
    { id: "app.launchClaude", group: "Application", title: "Launch Claude", run: () => launchClaude() },
    { id: "app.launchClaudeCode", group: "Application", title: "Launch Claude Code in a terminal", run: () => launchClaude("code") },
    { id: "app.launchClaudeDesktop", group: "Application", title: "Launch Claude Desktop", run: () => launchClaude("desktop") },
  ];
}
