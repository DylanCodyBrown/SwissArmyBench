/**
 * variableBox.ts: `${NAME}` in any box where a value is typed (design principle 12.7; the owner, 2026-11-18:
 * "a reserved char that allows us to use env variable almost anywhere in the app"). One box holds a value or
 * a reference; no picker beside it. [SHARED]
 *
 *   variableBox(input, options)   the box made a variable box, returned inside its row:
 *     typing `${`      the variables offered under the box (their names and their source as a word, never a
 *                      value), filtered as the name is typed; the arrows, Enter or Tab pick one, Escape closes;
 *                      the last row New variable… (the Add variable form with the typed name)
 *     {x}              a small button on the box: the same list, its pick put in at the caret
 *     the line under   what the box reads on this computer (a secret masked, never its value); a name not set
 *                      is the one error (errorNote.ts) with Set it; nothing when the box names no variable
 *   `$${NAME}` is the text itself: never offered, never read.
 *
 * ROUTING: GET /variables (names and sources)  ·  POST /variables/resolve (the line)  ·  notice variables_changed
 */
import { api, onNotice } from "./api";
import { h } from "./dom";
import { clearError, showError } from "./errorNote";
import { addVariable } from "./variableLinks";

interface Offered {
  name: string;
  words: string;
  secret: boolean;
}

interface Preview {
  value: string;
  masked: boolean;
  missing: string[];
  names: string[];
  error?: Record<string, unknown>;
}

export interface VariableBoxOptions {
  /** The box's own name, for the list's label ("Server"). */
  label?: string;
}

let offered: Promise<Offered[]> | null = null;
const refreshers = new Set<() => void>();

onNotice((n) => {
  if (n.type === "variables_changed") {
    offered = null;
    for (const refresh of refreshers) refresh();
  }
});

function variables(): Promise<Offered[]> {
  offered ??= api<{ variables: (Offered & { vault?: string })[] }>("/variables").then(
    // The source in words (a vault's own name with it), never a value.
    (r) => r.variables.map((v) => ({ name: v.name, words: v.vault ? `${v.words} · ${v.vault}` : v.words, secret: v.secret })),
    () => {
      offered = null;
      return [];
    },
  );
  return offered;
}

/** The name being typed after an unescaped `${` before the caret (null: none). */
export function typingName(text: string, caret: number): string | null {
  const found = /(^|[^$])\$\{([A-Za-z_][A-Za-z0-9_]*)?$/.exec(text.slice(0, caret));
  return found ? (found[2] ?? "") : null;
}

/** Whether the text names a variable (an escaped `$${` does not). */
export function namesVariable(text: string): boolean {
  return /(^|[^$])\$\{[A-Za-z_][A-Za-z0-9_]*(:-[^}]*)?\}/.test(text);
}

let boxes = 0;

/** The line under a box: what `text` reads on this computer, drawn again when a variable changes. Nothing
 *  when it names no variable; a name not set is the one error (9.5) with Set it; a secret masked. */
export function previewLine(): { line: HTMLElement; show: (text: string) => Promise<void> } {
  const line = h("div", { class: "variable-preview", "aria-live": "polite", hidden: true });
  let asked = 0;
  let current = "";
  const show = async (text: string): Promise<void> => {
    current = text;
    const mine = ++asked;
    if (!namesVariable(text)) {
      clearError(line);
      line.replaceChildren();
      line.hidden = true;
      return;
    }
    try {
      const answer = await api<Preview>("/variables/resolve", "POST", { text });
      if (mine !== asked) return;
      line.hidden = false;
      if (answer.missing.length && answer.error) {
        line.replaceChildren();
        showError(line, JSON.stringify(answer.error), { dismiss: false, agent: false });
      } else {
        clearError(line);
        line.replaceChildren(h("span", { class: "variable-preview-value mono", "data-masked": String(answer.masked), title: "What it reads on this computer" }, answer.value === "" ? "(empty)" : answer.value));
      }
    } catch {
      if (mine === asked) line.hidden = true;
    }
  };
  const refresh = (): void => {
    if (!line.isConnected) {
      refreshers.delete(refresh);
      return;
    }
    void show(current);
  };
  refreshers.add(refresh);
  return { line, show };
}

export function variableBox(input: HTMLInputElement, options: VariableBoxOptions = {}): HTMLElement {
  const id = `variable-list-${++boxes}`;
  input.classList.add("variable-input");
  input.setAttribute("autocomplete", "off");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-controls", id);
  const list = h("ul", { id, class: "variable-list", role: "listbox", hidden: true, "aria-label": `Variables${options.label ? ` for ${options.label}` : ""}` });
  const insert = h("button", { type: "button", class: "btn icon variable-insert", title: "Insert a variable", "aria-label": "Insert a variable" }, "{x}") as HTMLButtonElement;
  let items: Offered[] = [];
  let active = 0;
  // Where a pick goes: replacing the name typed after `${` (typed) or at the caret ({x}).
  let mode: "typed" | "button" = "typed";

  const close = (): void => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  };
  const put = (name: string): void => {
    const caret = input.selectionStart ?? input.value.length;
    const before = input.value.slice(0, caret);
    const after = input.value.slice(caret);
    const typed = mode === "typed" ? typingName(input.value, caret) : null;
    const head = typed !== null ? before.slice(0, before.length - typed.length) : `${before}\${`;
    const tail = after.startsWith("}") ? after.slice(1) : after;
    input.value = `${head}${name}}${tail}`;
    const at = head.length + name.length + 1;
    input.setSelectionRange(at, at);
    close();
    input.focus();
    // As typed: the form hears the new text (a password box shows a reference as text), then that it is done.
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    void preview();
  };
  const paint = (filter: string): void => {
    const wanted = filter.toLowerCase();
    const shown = items.filter((v) => v.name.toLowerCase().includes(wanted));
    active = Math.min(active, shown.length);
    list.replaceChildren(
      ...shown.map((v, i) =>
        h(
          "li",
          { id: `${id}-${i}`, role: "option", class: `variable-option${i === active ? " active" : ""}`, "aria-selected": String(i === active), "data-name": v.name, onmousedown: (e: Event) => (e.preventDefault(), put(v.name)) },
          h("span", { class: "mono" }, v.name),
          h("span", { class: "muted" }, v.words),
        ),
      ),
      h(
        "li",
        { id: `${id}-new`, role: "option", class: `variable-option variable-new${active === shown.length ? " active" : ""}`, "aria-selected": String(active === shown.length), onmousedown: (e: Event) => (e.preventDefault(), newVariable(filter)) },
        filter ? `New variable ${filter.toUpperCase()}…` : "New variable…",
      ),
    );
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    input.setAttribute("aria-activedescendant", active === shown.length ? `${id}-new` : `${id}-${active}`);
  };
  const newVariable = (typed: string): void => {
    close();
    addVariable(typed.toUpperCase(), (name) => put(name));
  };
  const filterNow = (): string | null => (mode === "button" ? "" : typingName(input.value, input.selectionStart ?? input.value.length));
  const open = async (how: "typed" | "button"): Promise<void> => {
    mode = how;
    items = await variables();
    const filter = filterNow();
    if (filter === null) return close();
    paint(filter);
  };

  input.addEventListener("input", () => {
    if (typingName(input.value, input.selectionStart ?? input.value.length) !== null) void open("typed");
    else if (mode === "typed") close();
    schedule();
  });
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    const count = list.children.length;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : count - 1)) % count;
      paint(filterNow() ?? "");
    } else if (e.key === "Enter" || e.key === "Tab") {
      const chosen = list.children[active] as HTMLElement | undefined;
      if (!chosen) return;
      e.preventDefault();
      e.stopPropagation();
      if (chosen.dataset.name) put(chosen.dataset.name);
      else newVariable(filterNow() ?? "");
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
    }
  });
  // Away from the box (not to its own {x}): the list closes.
  input.addEventListener("blur", () => setTimeout(() => document.activeElement !== input && close(), 150));
  insert.addEventListener("click", () => {
    input.focus();
    void open("button");
  });

  // ----- the line under the box: what it reads here -----
  const shown = previewLine();
  const line = shown.line;
  let timer = 0;
  const preview = (): Promise<void> => shown.show(input.value);
  const schedule = (): void => {
    clearTimeout(timer);
    timer = window.setTimeout(() => void preview(), 250);
  };
  input.addEventListener("change", schedule);
  void preview();

  return h("span", { class: "variable-box" }, h("span", { class: "variable-box-row" }, input, insert), list, line);
}
