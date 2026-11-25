// collaboration.js: the Collaboration panel's own JavaScript (Layout/CollaborationPanel): the floating card moved by
// its title bar and resized by its edge (its place kept per kind of window in this browser's storage), the
// Ctrl+Shift+M key that shows and hides it on every page, the composer's keys (Enter sends, Shift+Enter a new line,
// Ctrl+B, Ctrl+I, Ctrl+Shift+X, Ctrl+Shift+C, Ctrl+Alt+C, Ctrl+K, Ctrl+Shift+7, 8 and 9: Slack's), a pasted
// picture read as base64 (5 MB at most), and the SQL and Python code blocks coloured by Monaco's own colouriser.

const MIN_WIDTH = 300;
const MIN_HEIGHT = 260;
const MARGIN = 8;
const MAX_PICTURE = 5 * 1024 * 1024;

const storageKey = (kind) => `sab.blazor.collaboration.${kind}`;

function recall(kind) {
  try {
    const kept = JSON.parse(localStorage.getItem(storageKey(kind)) ?? "null");
    return kept && typeof kept === "object" ? kept : null;
  } catch {
    return null; // storage blocked or a value of another shape: the default place
  }
}

function remember(kind, value) {
  try {
    localStorage.setItem(storageKey(kind), JSON.stringify(value));
  } catch {
    /* storage blocked: the place lasts this page only */
  }
}

/** This window's kind: the desktop app's named window (sab-home, sab-notebooks...), else the page's address. */
export function windowKind() {
  if (window.name && window.name.startsWith("sab-")) return window.name;
  const page = location.pathname.replace(/^\/blazor\/?/, "").split("/")[0];
  return page || "home";
}

/** Whether the panel was open in this kind of window (null: never said). */
export function recallOpen(kind) {
  const kept = recall(kind);
  return kept && typeof kept.open === "boolean" ? kept.open : null;
}

export function rememberOpen(kind, open) {
  remember(kind, { ...(recall(kind) ?? {}), open });
}

function clamp(box) {
  const width = Math.min(Math.max(box.width, MIN_WIDTH), window.innerWidth - 2 * MARGIN);
  const height = Math.min(Math.max(box.height, MIN_HEIGHT), window.innerHeight - 2 * MARGIN);
  const left = Math.min(Math.max(box.left, MARGIN), window.innerWidth - width - MARGIN);
  const top = Math.min(Math.max(box.top, MARGIN), window.innerHeight - height - MARGIN);
  return { left, top, width, height };
}

function apply(panel, box) {
  panel.style.left = `${box.left}px`;
  panel.style.top = `${box.top}px`;
  panel.style.width = `${box.width}px`;
  panel.style.height = `${box.height}px`;
}

/** The card placed where it was in this kind of window (else at the right, above the status bar), moved by its title
 *  bar and resized by its corner; each move kept. */
export function place(panel, handle, edge, kind) {
  const kept = recall(kind)?.box;
  const start = kept ?? {
    width: 380,
    height: Math.min(620, window.innerHeight - 80),
    left: window.innerWidth - 380 - 24,
    top: Math.max(MARGIN, window.innerHeight - Math.min(620, window.innerHeight - 80) - 40),
  };
  let box = clamp(start);
  apply(panel, box);
  const save = () => remember(kind, { ...(recall(kind) ?? {}), box });

  const drag = (element, move) => (down) => {
    if (down.button !== 0 || down.target.closest("button, input, select, a")) return;
    down.preventDefault();
    element.setPointerCapture(down.pointerId);
    const from = { x: down.clientX, y: down.clientY, box: { ...box } };
    const moved = (e) => {
      box = clamp(move(from, e.clientX - from.x, e.clientY - from.y));
      apply(panel, box);
    };
    const up = () => {
      element.removeEventListener("pointermove", moved);
      element.removeEventListener("pointerup", up);
      element.removeEventListener("pointercancel", up);
      save();
    };
    element.addEventListener("pointermove", moved);
    element.addEventListener("pointerup", up);
    element.addEventListener("pointercancel", up);
  };
  const moving = drag(handle, (from, dx, dy) => ({ ...from.box, left: from.box.left + dx, top: from.box.top + dy }));
  const sizing = drag(edge, (from, dx, dy) => ({ ...from.box, width: from.box.width + dx, height: from.box.height + dy }));
  const resized = () => {
    box = clamp(box);
    apply(panel, box);
  };
  handle.addEventListener("pointerdown", moving);
  edge.addEventListener("pointerdown", sizing);
  window.addEventListener("resize", resized);
  return {
    stop() {
      handle.removeEventListener("pointerdown", moving);
      edge.removeEventListener("pointerdown", sizing);
      window.removeEventListener("resize", resized);
    },
  };
}

/** Ctrl+Shift+M on every page: the panel shown or hidden. */
export function installKeys(listener) {
  const heard = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && !e.altKey && e.key.toUpperCase() === "M") {
      e.preventDefault();
      listener.invokeMethodAsync("Toggle");
    }
  };
  document.addEventListener("keydown", heard);
  return { stop: () => document.removeEventListener("keydown", heard) };
}

// ===== The composer =====

const FORMATS = {
  bold: { around: ["**", "**"], placeholder: "bold" },
  italic: { around: ["*", "*"], placeholder: "italic" },
  strike: { around: ["~~", "~~"], placeholder: "struck" },
  code: { around: ["`", "`"], placeholder: "code" },
  block: { around: ["```sql\n", "\n```"], placeholder: "SELECT 1", lines: true },
  link: { around: ["[", "](https://)"], placeholder: "words" },
  bullets: { prefix: () => "- " },
  numbers: { prefix: (n) => `${n + 1}. ` },
  quote: { prefix: () => "> " },
  task: { prefix: () => "- [ ] " },
};

const KEYS = {
  "Ctrl+B": "bold",
  "Ctrl+I": "italic",
  "Ctrl+Shift+X": "strike",
  "Ctrl+Shift+C": "code",
  "Ctrl+Alt+C": "block",
  "Ctrl+K": "link",
  "Ctrl+Shift+7": "numbers",
  "Ctrl+Shift+8": "bullets",
  "Ctrl+Shift+9": "quote",
};

function keyName(e) {
  // Shift+7 types "&" on many keyboards: the key's own place (Digit7) names it.
  const key = e.code?.startsWith("Digit") ? e.code.slice(5) : e.key.length === 1 ? e.key.toUpperCase() : e.key;
  return [e.ctrlKey || e.metaKey ? "Ctrl" : "", e.altKey ? "Alt" : "", e.shiftKey ? "Shift" : "", key].filter(Boolean).join("+");
}

function edit(box, value, start, end) {
  box.value = value;
  box.setSelectionRange(start, end);
  box.dispatchEvent(new Event("input", { bubbles: true }));
}

function format(box, kind) {
  const how = FORMATS[kind];
  if (!how) return;
  const { selectionStart: s, selectionEnd: e, value } = box;
  if (how.prefix) {
    const from = value.lastIndexOf("\n", s - 1) + 1;
    const lines = value.slice(from, e).split("\n");
    const made = lines.map((line, n) => how.prefix(n) + line).join("\n");
    edit(box, value.slice(0, from) + made + value.slice(e), from + made.length, from + made.length);
    return;
  }
  const chosen = value.slice(s, e) || how.placeholder;
  const [before, after] = how.around;
  const lead = how.lines && s > 0 && value[s - 1] !== "\n" ? "\n" : "";
  const made = lead + before + chosen + after;
  const at = s + lead.length + before.length;
  edit(box, value.slice(0, s) + made + value.slice(e), at, at + chosen.length);
}

function readPicture(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => resolve("");
    reader.readAsDataURL(file);
  });
}

/** The composer's box: its keys, what is typed (with the caret, for `@` and `:`), pictures pasted. */
export function composer(box, listener) {
  let popup = false;
  const typed = () => listener.invokeMethodAsync("Typed", box.value, box.selectionStart ?? box.value.length);
  const keys = (e) => {
    if (e.isComposing) return;
    if (popup && ["ArrowUp", "ArrowDown", "Enter", "Tab", "Escape"].includes(e.key)) {
      e.preventDefault();
      listener.invokeMethodAsync("PopupKey", e.key);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      listener.invokeMethodAsync("Send");
      return;
    }
    const kind = KEYS[keyName(e)];
    if (kind) {
      e.preventDefault();
      format(box, kind);
    }
  };
  const pasted = async (e) => {
    const files = [...(e.clipboardData?.files ?? [])].filter((f) => f.type.startsWith("image/"));
    if (files.length === 0) return;
    e.preventDefault();
    for (const file of files) {
      if (file.size > MAX_PICTURE) {
        listener.invokeMethodAsync("TooBig", file.name || "The picture");
        continue;
      }
      listener.invokeMethodAsync("Pasted", file.type, await readPicture(file));
    }
  };
  box.addEventListener("keydown", keys);
  box.addEventListener("input", typed);
  box.addEventListener("click", typed);
  box.addEventListener("paste", pasted);
  return {
    format: (kind) => {
      format(box, kind);
      box.focus();
    },
    /** The `count` characters before the caret replaced by `text` (a picked object or emoji). */
    replaceBefore(count, text) {
      const at = box.selectionStart ?? box.value.length;
      const from = Math.max(0, at - count);
      edit(box, box.value.slice(0, from) + text + box.value.slice(at), from + text.length, from + text.length);
      box.focus();
    },
    insert(text) {
      const at = box.selectionStart ?? box.value.length;
      edit(box, box.value.slice(0, at) + text + box.value.slice(box.selectionEnd ?? at), at + text.length, at + text.length);
    },
    set(text) {
      edit(box, text, text.length, text.length);
    },
    setPopup(open) {
      popup = open;
    },
    focus: () => box.focus(),
    stop() {
      box.removeEventListener("keydown", keys);
      box.removeEventListener("input", typed);
      box.removeEventListener("click", typed);
      box.removeEventListener("paste", pasted);
    },
  };
}

/** The panel's list scrolled to its end (the newest, as Slack shows it). */
export function scrollEnd(panel) {
  const list = panel?.querySelector(".collab-scroll");
  if (list) list.scrollTop = list.scrollHeight;
}

// ===== Code blocks coloured (Monaco's colouriser, loaded only when a block shows) =====

let colouring = null;

/** Every ```sql and ```python block under `root` coloured once. */
export async function highlight(root) {
  const blocks = [...(root?.querySelectorAll("pre code[data-lang]:not([data-coloured])") ?? [])];
  if (blocks.length === 0) return;
  // The page's own codeEditor.js beside this file (one Monaco for the page), never bundled in here.
  colouring ??= import(new URL("./codeEditor.js", import.meta.url).href);
  const editor = await colouring;
  for (const block of blocks) {
    block.dataset.coloured = "1";
    try {
      block.innerHTML = await editor.colorize(block.textContent ?? "", block.dataset.lang, document.documentElement.dataset.theme);
    } catch {
      /* left plain: its text is already shown */
    }
  }
}
