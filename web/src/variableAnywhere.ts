/**
 * variableAnywhere.ts: a variable in any box of the app (design principle 12.7; the owner, 2026-11-19: "a right
 * click and insert env var menu and a auto complete when ${ is typed anywhere"). Installed once per page (main,
 * the blades page, the Workbench): document-level listeners, so a box drawn later needs nothing. [SHARED]
 *
 *   typing `${`          in any text box or text area (a password box too: a password field holds a reference)
 *                        the variables are listed under the box (variableBox.ts's list: the name and its source
 *                        in words, never a value), filtered as the name is typed; the arrows move, Enter or Tab
 *                        put in NAME and the closing brace, Escape closes; New variable… last
 *   right-click a box    the app's menu: Cut, Copy, Paste, then Insert variable… (the same list; the pick
 *                        replaces the selection at the caret)
 *   the editors          lazy/codeEditor.ts reads `globalThis.sabVariables` (the list, New variable…) for a SQL
 *                        editor's completion after `${` and its own Insert variable… (never a Python cell)
 *
 * Left alone: boxes with their own list (variableBox.ts), Monaco's own text area, and boxes where a reference
 * makes no sense: search and filter boxes (type=search, role=searchbox, or a label or placeholder that starts
 * with Search, Filter or Find) and any box marked `data-no-variables` (with its children).
 */
import { button, h, showMenu } from "./dom";
import { typingName, variables, type Offered } from "./variableBox";
import { addVariable } from "./variableLinks";
import { errorHere } from "./errorNote";

type Box = HTMLInputElement | HTMLTextAreaElement;

const TEXT_TYPES = new Set(["text", "password", "url", "tel", ""]);
const SEARCHY = /^\s*(search|filter|find)\b/i;

/** Whether a reference can be typed into this element (see the module's comment). */
export function takesVariables(el: EventTarget | null): el is Box {
  if (!(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) return false;
  if (el.readOnly || el.disabled) return false;
  if (el instanceof HTMLInputElement && !TEXT_TYPES.has(el.type)) return false;
  if (el.closest(".monaco-editor, [data-no-variables]")) return false;
  if (el.getAttribute("role") === "searchbox") return false;
  const named = `${el.getAttribute("aria-label") ?? ""}|${el.placeholder ?? ""}`;
  return !named.split("|").some((words) => SEARCHY.test(words)) && !/\b(search|filter)\b/i.test(el.className);
}

// ===== the one floating list =====

let list: HTMLUListElement | null = null;
let target: Box | null = null;
let items: Offered[] = [];
let active = 0;
/** "typed": the pick replaces the name after `${`; "insert": it goes at the caret (Insert variable…). */
let mode: "typed" | "insert" = "typed";

function close(): void {
  list?.remove();
  list = null;
  target?.removeAttribute("aria-activedescendant");
  target?.setAttribute("aria-expanded", "false");
  target = null;
}

function filterNow(): string | null {
  if (!target) return null;
  return mode === "insert" ? "" : typingName(target.value, target.selectionStart ?? target.value.length);
}

function put(name: string): void {
  const box = target;
  if (!box) return;
  const start = box.selectionStart ?? box.value.length;
  const end = box.selectionEnd ?? start;
  const typed = mode === "typed" ? typingName(box.value, start) : null;
  const from = typed !== null ? start - typed.length - 2 : start;
  const to = typed !== null && box.value.charAt(end) === "}" ? end + 1 : end;
  close();
  box.focus();
  box.setRangeText(`\${${name}}`, from, to, "end");
  // As typed: the page hears the new text, then that the box is done (a form writes it on change).
  box.dispatchEvent(new Event("input", { bubbles: true }));
  box.dispatchEvent(new Event("change", { bubbles: true }));
}

function newVariable(typed: string): void {
  const box = target;
  close();
  addVariable(typed.toUpperCase(), (name) => {
    if (!box?.isConnected) return;
    target = box;
    mode = "insert";
    put(name);
  });
}

function paint(): void {
  if (!list || !target) return;
  const filter = filterNow();
  if (filter === null) return close();
  const wanted = filter.toLowerCase();
  const shown = items.filter((v) => v.name.toLowerCase().includes(wanted));
  active = Math.min(active, shown.length);
  const id = "variable-anywhere";
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
  target.setAttribute("aria-expanded", "true");
  target.setAttribute("aria-activedescendant", active === shown.length ? `${id}-new` : `${id}-${active}`);
  place();
}

function place(): void {
  if (!list || !target) return;
  const r = target.getBoundingClientRect();
  const below = r.bottom + 2;
  const room = window.innerHeight - below - 8;
  list.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - list.offsetWidth - 8))}px`;
  list.style.top = room >= Math.min(260, list.offsetHeight) ? `${below}px` : `${Math.max(8, r.top - 2 - list.offsetHeight)}px`;
}

/** The list under `box`: after a typed `${` ("typed"), or from Insert variable… ("insert"). */
export async function openList(box: Box, how: "typed" | "insert"): Promise<void> {
  if (target !== box) {
    close();
    active = 0;
  }
  target = box;
  mode = how;
  items = await variables();
  if (target !== box) return;
  if (!list) {
    list = h("ul", { class: "variable-list variable-float", role: "listbox", "aria-label": "Variables" }) as HTMLUListElement;
    // Inside the top dialog when one is open (the rest of the page is inert), as menus are.
    ([...document.querySelectorAll<HTMLDialogElement>("dialog[open]")].pop() ?? document.body).append(list);
    box.setAttribute("aria-controls", "variable-anywhere");
    list.id = "variable-anywhere";
  }
  paint();
}

function onInput(event: Event): void {
  const box = event.target;
  if (!takesVariables(box) || box.classList.contains("variable-input")) return;
  if (box instanceof HTMLInputElement && box.type === "password" && box.value.includes("${")) box.type = "text"; // a reference reads as text
  const typing = typingName(box.value, box.selectionStart ?? box.value.length);
  if (typing !== null) void openList(box, "typed");
  else if (target === box && mode === "typed") close();
}

function onKey(event: KeyboardEvent): void {
  if (!list || !target || event.target !== target) return;
  const count = list.children.length;
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    active = (active + (event.key === "ArrowDown" ? 1 : count - 1)) % count;
    paint();
  } else if (event.key === "Enter" || event.key === "Tab") {
    const chosen = list.children[active] as HTMLElement | undefined;
    if (!chosen) return;
    if (chosen.dataset.name) put(chosen.dataset.name);
    else newVariable(filterNow() ?? "");
  } else if (event.key === "Escape") close();
  else return;
  event.preventDefault();
  event.stopPropagation();
}

// ===== right-click: Cut, Copy, Paste, Insert variable… =====

function onMenu(event: MouseEvent): void {
  const box = event.target;
  if (event.defaultPrevented || !takesVariables(box)) return;
  event.preventDefault();
  box.focus();
  const start = box.selectionStart ?? 0;
  const end = box.selectionEnd ?? start;
  const selected = box.value.slice(start, end);
  const hidden = box.type === "password";
  const edit = (text: string): void => {
    box.focus();
    box.setRangeText(text, box.selectionStart ?? start, box.selectionEnd ?? end, "end");
    box.dispatchEvent(new Event("input", { bubbles: true }));
  };
  const copy = async (cut: boolean): Promise<void> => {
    try {
      await navigator.clipboard.writeText(selected);
      if (cut) edit("");
    } catch {
      errorHere("The browser did not allow the copy: use Ctrl+C.");
    }
  };
  const paste = async (): Promise<void> => {
    try {
      edit(await navigator.clipboard.readText());
    } catch {
      errorHere("The browser did not allow the paste: use Ctrl+V.");
    }
  };
  // The keyboard's menu key or Shift+F10: under the box.
  const r = box.getBoundingClientRect();
  const keyed = event.clientX === 0 && event.clientY === 0;
  showMenu(keyed ? r.left + 8 : event.clientX, keyed ? r.bottom : event.clientY, "Text", [
    ["edit", "Cut", () => void copy(true), !selected || hidden ? "Nothing selected" : undefined],
    ["copy", "Copy", () => void copy(false), !selected || hidden ? "Nothing selected" : undefined],
    ["import", "Paste", () => void paste()],
    "-",
    ["variables", "Insert variable…", () => {
      box.focus();
      box.setSelectionRange(start, end);
      void openList(box, "insert");
    }],
  ]);
}

let installed = false;

/** Once per page: the listeners, and the editors' hook (`globalThis.sabVariables`). */
export function installVariableAnywhere(): void {
  if (installed) return;
  installed = true;
  document.addEventListener("input", onInput, true);
  document.addEventListener("keydown", onKey, true);
  document.addEventListener("contextmenu", onMenu);
  document.addEventListener("focusout", (e) => {
    if (e.target === target) setTimeout(() => document.activeElement !== target && close(), 150);
  });
  window.addEventListener("resize", () => place());
  document.addEventListener("scroll", () => place(), true);
  (globalThis as { sabVariables?: unknown }).sabVariables = {
    list: () => variables(),
    add: (name: string, done: (name: string) => void) => addVariable(name, done),
  };
}

/** For a page that wants a button for it (unused by the forms, which have variableBox's {x}). */
export const insertVariableButton = (box: Box): HTMLElement => button("Insert variable", () => void openList(box, "insert"), { icon: "variables", iconOnly: true, class: "ghost small" });
