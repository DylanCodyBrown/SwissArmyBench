/**
 * environmentActions.ts: what a row of the Environment does: its actions (the viewer's buttons and its "…"
 * menu), Insert into code, Open where it lives, a "Used in" link followed, Send to the agent, Keep, Show a
 * secret, the Rename, Remove and Clear dialogs, and the libraries' Install, Update and Pin through the one
 * install prompt (missingPackages.ts). Pulled out of environmentPage.ts's mountEnvironment (the craft review
 * of 2026-11-22, refactor 8): each takes the state record (environmentState.ts). [VIEW]
 *
 * ROUTING: POST /environment/open, /insert, /rename, /remove, /keep, /clear  ·  POST
 *          /environment/libraries/install, /update, /pin  ·  POST /variables/reveal (Show: the user's)
 */
import { api } from "./api";
import { append, button, h, openDialog, plural, toast } from "./dom";
import { type Item, removeWords, TAB_WORDS, type Used } from "./environmentRules";
import { load, select } from "./environmentMoves";
import { type Environment, kidsOf } from "./environmentState";
import { errorHere, showError } from "./errorNote";
import { busyButton } from "./loading";
import { promptInstall, type Missing } from "./missingPackages";
import { visit, withParams } from "./nav";
import { openMenu, type MenuEntry } from "./workbenchMenu";

export interface Action {
  label: string;
  run: () => void;
  primary?: boolean;
  icon?: string;
}

// ===== a row's actions =====

export function actionsOf(env: Environment, item: Item): Action[] {
  const insert = { label: item.kind === "library" ? "Insert import" : item.kind === "setting" ? `Insert \${${item.name}}` : "Insert into code", run: () => void insertCode(env, item) };
  const copy = { label: "Copy name", run: () => void copyText(item.name, "Copied its name.") };
  const rename = { label: "Rename…", run: () => renameDialog(env, item) };
  const remove = { label: "Remove…", run: () => removeDialog(env, item), icon: "trash" };
  const agent = { label: "Send to the agent", run: () => sendToAgent(env, item), icon: "agent" };
  if (item.kind === "table") {
    const kept = item.tags.includes("Keep");
    return [
      { label: "Open in Grids", run: () => void openItem(env, item), primary: true },
      insert,
      copy,
      ...(item.open ? [rename, { label: kept ? "Stop keeping with the project" : "Keep with the project", run: () => void keep(env, item, !kept) }] : []),
      ...(item.open && item.grids[0] ? [{ label: "Make a sandbox variant…", run: () => void import("./dataSandbox").then((m) => m.makeVariant("grid", item.name, () => void load(env))) }] : []),
      agent,
      remove,
    ];
  }
  if (item.kind === "structure") return [{ label: "Open in Structures", run: () => void openItem(env, item), primary: true }, insert, copy, ...(item.open ? [rename] : []), agent, remove];
  if (item.kind === "library") {
    return [
      ...(item.latest ? [{ label: `Update to ${item.latest}`, run: () => update(env, item), primary: true }] : []),
      ...(item.installed ? [{ label: item.pinned ? "Unpin" : `Pin at ${item.version}`, run: () => void pin(env, item, !item.pinned) }] : [{ label: "Install", run: () => install(env, item.name), primary: true }]),
      insert,
      remove,
    ];
  }
  if (item.kind === "setting") {
    return [
      ...(item.editable ? [{ label: "Change…", run: () => void import("./variableLinks").then((m) => m.addVariable(item.name, () => void load(env))), primary: true }] : []),
      ...(item.showable ? [{ label: env.revealed.has(item.id) ? "Hide" : "Show", run: () => void reveal(env, item), icon: "eye" }] : []),
      insert,
      copy,
      ...(item.renamable ? [rename, remove] : []),
    ];
  }
  return [insert, copy, rename, agent, remove];
}

/** A row's "…" menu: its actions. */
export function rowMenu(env: Environment, item: Item, anchor: HTMLElement): void {
  const entries: MenuEntry[] = actionsOf(env, item).map((a) => ({ label: a.label, run: a.run, icon: a.icon }));
  openMenu(anchor, `Actions for ${item.name}`, entries, { align: "right" });
}

export const addSetting = (env: Environment): void => void import("./variableLinks").then((m) => m.addVariable("", () => void load(env)));

// ===== going where a row lives =====

/** The page makes way for one of the home page's own views (a grid, Analyze, the ERD): its layer leaves
 *  the address, pushed, so Back brings the Environment again. */
function leave(env: Environment): void {
  if (!env.compact && new URLSearchParams(location.search).get("open") === "environment") visit(withParams({ open: null, at: null, type: null, name: null }));
}

/** A "Used in" link: a table's row here, else the place itself (a grid, a cell, a connection, a page). */
export function follow(env: Environment, used: Used): void {
  const link = used.link;
  if (link.to === "table" && link.name) {
    select(env, `table:${link.name}`, true);
    return;
  }
  void import("./sessionPage").then(({ goToTarget }) => {
    if (link.to === "grid" && link.grid) (leave(env), goToTarget({ place: "grid", grid: link.grid }));
    else if (link.to === "document" && link.path) goToTarget({ place: "cell", path: link.path, cell: link.cell ?? null });
    else if (link.to === "connection" && link.name) goToTarget({ place: "connection", name: link.name });
    else if (link.to === "analyze" || link.to === "erd") (leave(env), goToTarget({ place: "area", area: link.to }));
    else if (link.to === "canvas") goToTarget({ place: "area", area: "canvas" });
  });
}

/** Open a row where it lives: a table in Grids, a structure in Structures, anything else in the viewer. */
export async function openItem(env: Environment, item: Item): Promise<void> {
  try {
    if (item.kind === "structure") {
      let id = typeof item.open === "string" ? item.open : null;
      if (!id && item.path) id = (await api<{ id: string }>("/structures/open", "POST", { path: item.path })).id;
      const page = await import("./structuresPage");
      page.openStructures(id);
      return;
    }
    if (item.kind !== "table") {
      select(env, item.id, true);
      return;
    }
    const got = await api<{ link: { to: string; grid?: string } }>("/environment/open", "POST", { kind: item.kind, name: item.name });
    if (got.link.to === "python") {
      toast(`Opening ${item.name} from Python…`); // its session sends it: the grid arrives by itself
      return;
    }
    const { goToTarget } = await import("./sessionPage");
    if (got.link.grid) {
      leave(env);
      goToTarget({ place: "grid", grid: got.link.grid });
    }
  } catch (e) {
    errorHere(e);
  }
}

// ===== what a row does =====

async function copyText(words: string, said: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(words);
    toast(said);
  } catch {
    errorHere("The clipboard is not available here.");
  }
}

async function insertCode(env: Environment, item: Item): Promise<void> {
  try {
    const code = await api<{ python?: string; sql?: string; text?: string }>("/environment/insert", "POST", { kind: item.kind, name: item.name });
    if (env.options.insert?.(code)) return;
    const words = code.text ?? code.python ?? code.sql ?? item.name;
    await copyText(words, `Copied: ${words}`);
  } catch (e) {
    errorHere(e);
  }
}

function sendToAgent(env: Environment, item: Item): void {
  const lines = [`${TAB_WORDS[item.kind]}: ${item.name} (${item.type}${item.size ? `, ${item.size}` : ""})`, item.from ? `From: ${item.from}` : "", ...item.used.map((u) => `Used in: ${u.words}`), ...kidsOf(env, item).map((k) => `  ${k[0]}: ${k[1]}`)];
  void import("./workbenchAgent").then((m) => m.sendToAgent({ kind: "code", title: `Environment · ${item.name}`, text: lines.filter(Boolean).join("\n") }));
}

async function keep(env: Environment, item: Item, to: boolean): Promise<void> {
  try {
    await api("/environment/keep", "POST", { name: item.name, keep: to });
    toast(to ? `${item.name} is kept with the project.` : `${item.name} is no longer kept with the project.`);
    await load(env);
  } catch (e) {
    errorHere(e);
  }
}

/** Show a secret's value on the user's click (Hide takes it away). */
async function reveal(env: Environment, item: Item): Promise<void> {
  if (env.revealed.has(item.id)) {
    env.revealed.delete(item.id);
    env.act.draw();
    return;
  }
  try {
    env.revealed.set(item.id, (await api<{ value: string }>("/variables/reveal", "POST", { name: item.name })).value);
    env.act.draw();
  } catch (e) {
    errorHere(e);
  }
}

// ===== the dialogs =====

export function renameDialog(env: Environment, item: Item): void {
  const { dialog, body, foot, close } = openDialog(`Rename ${item.name}`);
  dialog.classList.add("env-dialog");
  const to = h("input", { type: "text", class: "mono", "aria-label": "New name", value: item.name, spellcheck: false, "data-no-variables": "" }) as HTMLInputElement;
  const said = h("div", {});
  const run = async (): Promise<void> => {
    try {
      await api("/environment/rename", "POST", { kind: item.kind, name: item.name, to: to.value.trim() });
      close();
      env.selected = `${item.kind}:${to.value.trim()}`;
      await load(env);
    } catch (e) {
      showError(said, e);
    }
  };
  body.append(h("label", { class: "field" }, h("span", {}, "New name"), to), said);
  const rename = button("Rename", () => void busyButton(rename, run(), "Renaming…"), { class: "primary" });
  to.addEventListener("keydown", (e) => {
    if (e.key === "Enter") rename.click();
  });
  foot.append(button("Cancel", close, { class: "ghost" }), rename);
  to.select();
}

export function removeDialog(env: Environment, item: Item): void {
  const { dialog, body, foot, close } = openDialog(`Remove ${item.name}`);
  dialog.classList.add("env-dialog");
  const python = item.kind === "table" && item.in_python ? (h("input", { type: "checkbox", class: "env-python-too" }) as HTMLInputElement) : null;
  if (python) python.checked = Boolean(env.pythonTick?.checked) || !item.open;
  const said = h("div", {});
  append(body, h("p", {}, removeWords(item, plural(item.grids.length, "grid"))), item.used.length ? h("p", { class: "env-keys" }, `Used in ${plural(item.used.length, "place")}: ${item.used.slice(0, 4).map((u) => u.words).join("; ")}${item.used.length > 4 ? "…" : ""}`) : null, python ? h("label", { class: "env-python-label" }, python, " Also delete it in Python") : null, said);
  const run = async (): Promise<void> => {
    try {
      await api("/environment/remove", "POST", { kind: item.kind, name: item.name, python: Boolean(python?.checked) });
      close();
      await load(env);
    } catch (e) {
      showError(said, e);
    }
  };
  const remove = button("Remove", () => void busyButton(remove, run(), "Removing…"), { class: "danger" });
  foot.append(button("Cancel", close, { class: "ghost" }), remove);
  remove.focus();
}

/** Clear…: what is not kept, by kind, each with its names (a dry run first). */
export async function clearDialog(env: Environment): Promise<void> {
  let would: Record<string, string[]>;
  let choices: Record<string, string>;
  try {
    ({ would, choices } = await api<{ would: Record<string, string[]>; choices: Record<string, string> }>("/environment/clear", "POST", { dry_run: true }));
  } catch (e) {
    errorHere(e);
    return;
  }
  const { dialog, body, foot, close } = openDialog("Clear the environment");
  dialog.classList.add("env-dialog");
  const ticks = Object.entries(choices).map(([key, label]) => {
    const names = would[key] ?? [];
    const box = h("input", { type: "checkbox", "data-clear": key }) as HTMLInputElement;
    box.disabled = names.length === 0;
    return { key, box, row: h("label", { class: "env-clear-row" }, box, h("span", {}, `${label} (${names.length})`), names.length ? h("span", { class: "env-keys" }, names.slice(0, 6).join(", ") + (names.length > 6 ? "…" : "")) : null) };
  });
  const said = h("div", {});
  body.append(h("p", {}, "Kept tables, settings and libraries stay."), ...ticks.map((t) => t.row), said);
  const run = async (): Promise<void> => {
    try {
      await api("/environment/clear", "POST", Object.fromEntries(ticks.map((t) => [t.key, t.box.checked])));
      close();
      await load(env);
    } catch (e) {
      showError(said, e);
    }
  };
  const clear = button("Clear", () => void busyButton(clear, run(), "Clearing…"), { class: "danger" });
  foot.append(button("Cancel", close, { class: "ghost" }), clear);
}

// ===== libraries: through the one install prompt (missingPackages.ts) =====

const missing = (env: Environment, names: string[], feature: string): Missing => ({ feature, packages: names, python: env.listing?.python.python ?? "app", command: `uv pip install --python ${env.listing?.python.python ?? "python"} ${names.join(" ")}` });

function install(env: Environment, name: string): void {
  void promptInstall(missing(env, [name], "The project"), { force: true, install: async () => void (await api("/environment/libraries/install", "POST", { name })), then: () => load(env) });
}

export function installDialog(env: Environment): void {
  const { dialog, body, foot, close } = openDialog("Install a library");
  dialog.classList.add("env-dialog");
  const name = h("input", { type: "text", class: "mono", "aria-label": "Library", placeholder: "polars", spellcheck: false, "data-no-variables": "" }) as HTMLInputElement;
  body.append(h("label", { class: "field" }, h("span", {}, "Library"), name), h("p", { class: "env-keys" }, "Into the project's environment, and into requirements.txt so a teammate gets it."));
  const next = button("Install…", () => {
    const wanted = name.value.trim();
    if (!wanted) return;
    close();
    install(env, wanted);
  }, { class: "primary" });
  name.addEventListener("keydown", (e) => {
    if (e.key === "Enter") next.click();
  });
  foot.append(button("Cancel", close, { class: "ghost" }), next);
  name.focus();
}

export function update(env: Environment, item: Item): void {
  void promptInstall(missing(env, [`${item.name}==${item.latest ?? ""}`], `Update ${item.name}`), { force: true, install: async () => void (await api("/environment/libraries/update", "POST", { name: item.name })), then: () => load(env) });
}

export function updateAll(env: Environment, outdated: Item[]): void {
  void promptInstall(missing(env, outdated.map((i) => `${i.name}==${i.latest ?? ""}`), "Update all not pinned"), { force: true, install: async () => void (await api("/environment/libraries/update", "POST", { all: true })), then: () => load(env) });
}

export async function pin(env: Environment, item: Item, to: boolean): Promise<void> {
  try {
    await api("/environment/libraries/pin", "POST", { name: item.name, pinned: to });
    await load(env);
  } catch (e) {
    errorHere(e);
  }
}
