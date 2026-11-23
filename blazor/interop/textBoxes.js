// textBoxes.js: a variable in any text box of the page (the classic variableAnywhere.ts and variableBox.ts, design
// principle 12.7). Document-level listeners, so a box drawn later needs nothing; the list and the Text menu are the
// C# component's (Layout/VariableAnywhere.razor), this file only watches the boxes and edits their text.
//
//   typing `${`          the C# side is told the name typed so far and where the box is; while its list is open the
//                        arrows, Enter, Tab and Escape go to it instead of the box
//   right-click a box    the C# side shows Text: Cut, Copy, Paste, Insert variable… (this file does the editing)
//
// Left alone: Monaco's own text area, search and filter boxes (type=search, role=searchbox, a label or placeholder
// that starts with Search, Filter or Find) and any box marked data-no-variables (with its children).

const TEXT_TYPES = new Set(["text", "password", "url", "tel", ""]);
const SEARCHY = /^\s*(search|filter|find)\b/i;
const LIST_KEYS = new Set(["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"]);

/** Whether a reference can be typed into this element. */
function takesVariables(el) {
  if (!(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) return false;
  if (el.readOnly || el.disabled) return false;
  if (el instanceof HTMLInputElement && !TEXT_TYPES.has(el.type)) return false;
  if (el.closest(".monaco-editor, [data-no-variables]")) return false;
  if (el.getAttribute("role") === "searchbox") return false;
  const named = `${el.getAttribute("aria-label") ?? ""}|${el.placeholder ?? ""}`;
  return !named.split("|").some((words) => SEARCHY.test(words)) && !/\b(search|filter)\b/i.test(el.className);
}

/** The name being typed after an unescaped `${` before the caret (null: none). */
function typingName(text, caret) {
  const found = /(^|[^$])\$\{([A-Za-z_][A-Za-z0-9_]*)?$/.exec(text.slice(0, caret));
  return found ? (found[2] ?? "") : null;
}

let box = null;
let open = false;
let mode = "typed";
let range = [0, 0];

const placeOf = (el) => {
  const r = el.getBoundingClientRect();
  return { left: r.left, top: r.top, bottom: r.bottom };
};

/** Whatever the page's own code listens for (Blazor's @bind hears input; a form writes on change). */
function told(el) {
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

export function install(listener) {
  const onInput = (event) => {
    const el = event.target;
    if (!takesVariables(el)) return;
    // A reference reads as text: a password box that holds one shows it.
    if (el instanceof HTMLInputElement && el.type === "password" && el.value.includes("${")) el.type = "text";
    const typing = typingName(el.value, el.selectionStart ?? el.value.length);
    if (typing !== null) {
      box = el;
      mode = "typed";
      open = true;
      listener.invokeMethodAsync("Typed", typing, placeOf(el));
    } else if (open && box === el && mode === "typed") {
      open = false;
      listener.invokeMethodAsync("Closed");
    }
  };
  const onKey = (event) => {
    if (!open || event.target !== box || !LIST_KEYS.has(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    listener.invokeMethodAsync("Key", event.key);
  };
  const onMenu = (event) => {
    const el = event.target;
    if (event.defaultPrevented || !takesVariables(el)) return;
    event.preventDefault();
    el.focus();
    box = el;
    range = [el.selectionStart ?? 0, el.selectionEnd ?? el.selectionStart ?? 0];
    const selected = range[1] > range[0] && el.type !== "password";
    // The keyboard's menu key or Shift+F10: under the box.
    const keyed = event.clientX === 0 && event.clientY === 0;
    const r = el.getBoundingClientRect();
    listener.invokeMethodAsync("Menu", keyed ? r.left + 8 : event.clientX, keyed ? r.bottom : event.clientY, selected);
  };
  const onBlur = (event) => {
    if (open && event.target === box) setTimeout(() => {
      if (document.activeElement !== box && open) {
        open = false;
        listener.invokeMethodAsync("Closed");
      }
    }, 150);
  };
  document.addEventListener("input", onInput, true);
  document.addEventListener("keydown", onKey, true);
  document.addEventListener("contextmenu", onMenu);
  document.addEventListener("focusout", onBlur);
  return {
    stop() {
      document.removeEventListener("input", onInput, true);
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("contextmenu", onMenu);
      document.removeEventListener("focusout", onBlur);
    },
  };
}

/** The list was closed by the C# side (a pick, Escape, a click elsewhere). */
export function closed() {
  open = false;
}

/** Insert variable…: the list opens at the caret of the box that was right-clicked. */
export function openAtCaret() {
  if (!box?.isConnected) return null;
  box.focus();
  box.setSelectionRange(range[0], range[1]);
  mode = "insert";
  open = true;
  return placeOf(box);
}

/** A picked name: "typed" replaces the name after `${` (and a closing brace already there); "insert" goes at the
 *  caret, over the selection. */
export function put(name) {
  const el = box;
  open = false;
  if (!el?.isConnected) return;
  el.focus();
  const start = el.selectionStart ?? el.value.length;
  const end = el.selectionEnd ?? start;
  const typed = mode === "typed" ? typingName(el.value, start) : null;
  const from = typed !== null ? start - typed.length - 2 : start;
  const to = typed !== null && el.value.charAt(end) === "}" ? end + 1 : end;
  el.setRangeText(`\${${name}}`, from, to, "end");
  told(el);
}

/** Cut and Copy of the right-clicked box's selection; false when the browser did not allow it. */
export async function copy(cut) {
  const el = box;
  if (!el) return false;
  try {
    await navigator.clipboard.writeText(el.value.slice(range[0], range[1]));
  } catch {
    return false;
  }
  if (cut) {
    el.focus();
    el.setRangeText("", range[0], range[1], "end");
    told(el);
  }
  return true;
}

/** Paste at the right-clicked box's caret; false when the browser did not allow it. */
export async function paste() {
  const el = box;
  if (!el) return false;
  let text;
  try {
    text = await navigator.clipboard.readText();
  } catch {
    return false;
  }
  el.focus();
  el.setRangeText(text, range[0], range[1], "end");
  told(el);
  return true;
}
