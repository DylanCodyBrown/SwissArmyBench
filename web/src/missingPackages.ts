/**
 * A missing package, said in the user's face (the owner, 2026-11-16): one prompt for every place that
 * finds one (a connection's form, a blade, a run that failed on an import, a Streamlit app, Test this
 * page, a notebook's cell, a YAML API document).
 *
 *   [PROMPT]    "Install <package>?"   <Feature> will not work without <package>.
 *               [Not now]  [Install now]      Install now: progress here, then done or the error,
 *                                             then the caller's retry (what the user was doing)
 *   [REMINDER]  [Install <package>]           where the feature is used, after Not now; it opens the
 *                                             prompt again (Not now holds for the session: no nagging)
 *
 * The server's answers carry one shape (domain/packages.py): {"missing": {feature, packages, python,
 * command}}; "python" is "app" (the app's own Python: POST /blades/install) or another Python's path
 * (a Streamlit app's, a document's), whose place passes its own installer.
 */

import { api } from "./api";
import { button, h, icon, openDialog, toast } from "./dom";
import { loadingBlock, markBusy } from "./loading";

export interface Missing {
  feature: string;
  packages: string[];
  /** "app": the app's own Python; else the path of the Python they go into. */
  python: string;
  command: string;
}

/** Installs the packages, or throws an Error whose message is what went wrong, in plain words. */
export type Installer = (missing: Missing) => Promise<void>;

export interface PromptOptions {
  /** Where they go: the app's own Python unless said otherwise. */
  install?: Installer;
  /** Run once they are installed: what the user was doing, again. */
  then?: () => void | Promise<void>;
  /** The user asked (the reminder): shown even after Not now. */
  force?: boolean;
}

/** "a", "a and b", "a, b and c". */
export function listed(packages: string[]): string {
  return packages.length > 1 ? `${packages.slice(0, -1).join(", ")} and ${packages[packages.length - 1]}` : packages.join("");
}

/** The prompt's title and its one sentence. */
export function promptWords(missing: Missing): { title: string; sentence: string } {
  const names = listed(missing.packages);
  return { title: `Install ${names}?`, sentence: `${missing.feature} will not work without ${names}.` }; // the owner's words: "<feature> will not work without <package> Install now?"
}

// ===== Not now: held for this session (this tab), per package and Python =====

const STORE = "sab-missing-not-now";
const notNow = new Set<string>(
  (() => {
    try {
      return JSON.parse(sessionStorage.getItem(STORE) ?? "[]") as string[];
    } catch {
      return [];
    }
  })(),
);

const keysOf = (missing: Missing): string[] => missing.packages.map((p) => `${missing.python}\u0000${p.toLowerCase()}`);

/** Not now was said for every one of these packages this session. */
export function dismissed(missing: Missing): boolean {
  return missing.packages.length > 0 && keysOf(missing).every((k) => notNow.has(k));
}

function dismiss(missing: Missing): void {
  for (const k of keysOf(missing)) notNow.add(k);
  try {
    sessionStorage.setItem(STORE, JSON.stringify([...notNow]));
  } catch {
    // storage blocked: held in this page only
  }
}

// ===== reading the server's answers =====

function isMissing(value: unknown): value is Missing {
  const m = value as Missing | null;
  return !!m && typeof m === "object" && typeof m.feature === "string" && Array.isArray(m.packages) && m.packages.length > 0 && typeof m.python === "string";
}

/** The missing packages an answer or an error names ({"missing": {...}}), or null. */
export function missingOf(answer: unknown): Missing | null {
  let found: unknown = answer;
  if (answer instanceof Error) {
    if (!answer.message.startsWith("{")) return null;
    try {
      found = JSON.parse(answer.message);
    } catch {
      return null;
    }
  }
  const inner = found && typeof found === "object" ? (found as { missing?: unknown }).missing : null;
  return isMissing(inner) ? inner : null;
}

/** An install's failure in plain words: its last lines of output when it answered with them. */
export function installError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  try {
    const said = JSON.parse(message) as { output?: string; error?: string };
    const out = (said.output ?? said.error ?? "").trim();
    return out ? out.split("\n").slice(-8).join("\n") : "The install failed.";
  } catch {
    return message || "The install failed.";
  }
}

/** Into the app's own Python (where connections and blades run): POST /blades/install. */
export const intoApp: Installer = async (missing) => {
  await api<{ ok: boolean }>("/blades/install", "POST", { packages: missing.packages });
};

// ===== the prompt =====

const open = new Map<string, Promise<boolean>>();

/** Put the prompt in the user's face. True once the packages are installed (and `then` has run);
 * false on Not now, or at once when Not now was said for them this session (unless forced). */
export function promptInstall(missing: Missing, options: PromptOptions = {}): Promise<boolean> {
  const key = keysOf(missing).join("\u0001");
  if (!options.force && dismissed(missing)) return Promise.resolve(false);
  const already = open.get(key);
  if (already) return already;
  const shown = new Promise<boolean>((resolve) => {
    const words = promptWords(missing);
    const { dialog, body, foot, close } = openDialog(words.title, false, { history: false });
    dialog.classList.add("missing-packages");
    dialog.dataset.packages = missing.packages.join(" ");
    const state = h("p", { class: "missing-state", role: "status" });
    const failed = h("pre", { class: "code-box missing-error", hidden: true });
    body.append(h("p", { class: "missing-sentence" }, words.sentence), state, failed);
    let done = false;
    let busy = false;
    const finish = (installed: boolean): void => {
      if (done) return;
      done = true;
      open.delete(key);
      if (!installed) dismiss(missing);
      resolve(installed);
    };
    // Closed any way but Install now (Escape, the X): Not now. Never while it installs.
    dialog.addEventListener("cancel", (event) => {
      if (busy) event.preventDefault();
    });
    dialog.addEventListener("close", () => finish(false));
    const later = button("Not now", () => close(), { class: "ghost" });
    const go = button("Install now", () => void run(), { class: "primary", icon: "import", title: missing.command });
    const run = async (): Promise<void> => {
      busy = true;
      later.disabled = true;
      const restore = markBusy(go, "Installing…"); // the one loading state (loading.ts)
      dialog.classList.add("busy");
      failed.hidden = true;
      state.className = "missing-state";
      state.replaceChildren(loadingBlock(`Installing ${listed(missing.packages)}…`, { inline: true }));
      try {
        await (options.install ?? intoApp)(missing);
      } catch (error) {
        busy = false;
        restore();
        later.disabled = false;
        dialog.classList.remove("busy");
        state.className = "missing-state status-error";
        state.replaceChildren("The install failed.");
        failed.textContent = installError(error);
        failed.hidden = false;
        go.querySelector(".btn-label")!.textContent = "Try again";
        go.setAttribute("aria-label", "Try again");
        return;
      }
      busy = false;
      state.className = "missing-state status-ok";
      state.replaceChildren(icon("check"), `Installed ${listed(missing.packages)}.`);
      done = true;
      open.delete(key);
      close();
      toast(`Installed ${listed(missing.packages)}.`);
      resolve(true);
      try {
        await options.then?.();
      } catch (error) {
        toast((error as Error).message, "error");
      }
    };
    foot.append(later, go);
    go.focus();
  });
  open.set(key, shown);
  return shown;
}

/** The small reminder where the feature is used, after Not now: "Install <package>", which opens the
 * prompt again. Its title is the command, for the user's own Python too. */
export function reminder(missing: Missing, options: PromptOptions = {}): HTMLElement {
  return h(
    "span",
    { class: "missing-reminder" },
    button(`Install ${listed(missing.packages)}`, () => void promptInstall(missing, { ...options, force: true }), { icon: "import", class: "ghost small", title: missing.command }),
  );
}

/** Where a place finds packages missing: the prompt (unless Not now was said), and the reminder for its
 * slot. Returns the reminder. */
export function noticeMissing(missing: Missing, options: PromptOptions = {}): HTMLElement {
  void promptInstall(missing, options);
  return reminder(missing, options);
}

/** An error that names missing packages: the prompt, true when it was one (the caller says nothing more). */
export function promptForError(error: unknown, options: PromptOptions = {}): boolean {
  const missing = missingOf(error);
  if (!missing) return false;
  void promptInstall(missing, options);
  return true;
}

