/**
 * structureTree.ts: a structure drawn as a tree (the Structures page, the APIs page's inputs, outputs,
 * schemas and the authoring screen's body). [SHARED]
 *
 *   [TREE]    each node a row: its key (or index), its type and, for an object or a list, its count;
 *             a value readable beside it. A caret folds and unfolds; nodes deeper than `depth` start
 *             folded, and a long list shows its first 200 items with Show more (quick at any size).
 *   [PATH]    a click selects a node: its path ($.orders[3].lines) said to `onSelect`.
 *   [SEARCH]  words marked in keys and values; the nodes on the way to a match unfold.
 *   [EDIT]    when the caller allows it: a double click edits a value (Set value) or a key (Rename key).
 *   [TEXT]    the text view: Monaco (lazy) in JSON, YAML, XML or TOML colours, its errors at their lines.
 */
import { h, icon } from "./dom";
import type { CodeEditor, Problem } from "./lazy/codeEditor";
import { effectiveTheme } from "./theme";
import { errorNote } from "./errorNote";

export type Value = null | boolean | number | string | Value[] | { [key: string]: Value };
export type Part = string | number;
export const FORMATS = ["json", "yaml", "xml", "toml"] as const;
export type Format = (typeof FORMATS)[number];
export const FORMAT_NAMES: Record<Format, string> = { json: "JSON", yaml: "YAML", xml: "XML", toml: "TOML" };

const NAME = /^[A-Za-z_][A-Za-z0-9_-]*$/;
const PAGE = 200;

export function pathText(parts: Part[]): string {
  let out = "$";
  for (const p of parts) out += typeof p === "number" ? `[${p}]` : NAME.test(p) ? `.${p}` : `[${JSON.stringify(p)}]`;
  return out;
}

export function kindOf(value: Value): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "list";
  if (typeof value === "object") return "object";
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "boolean";
  return "text";
}

export function nodeAt(value: Value, parts: Part[]): Value | undefined {
  let node: Value | undefined = value;
  for (const p of parts) {
    if (node === null || node === undefined || typeof node !== "object") return undefined;
    node = Array.isArray(node) ? (typeof p === "number" ? node[p] : undefined) : (node as Record<string, Value>)[String(p)];
  }
  return node;
}

export const isRecords = (value: Value | undefined): boolean =>
  Array.isArray(value) && value.length > 0 && value.slice(0, 50).every((v) => v !== null && typeof v === "object" && !Array.isArray(v));

export interface TreeOptions {
  /** Nodes deeper than this start folded. */
  depth?: number;
  onSelect?: (parts: Part[], value: Value) => void;
  /** Edits in the tree (the caller makes each a step, or changes its own value). */
  onSet?: (parts: Part[], value: Value) => void;
  onRename?: (parts: Part[], key: string, to: string) => void;
  /** A schema's tree (APIs): "string (date-time)" leaves read as types, a key's * as required. */
  schema?: boolean;
  label?: string;
}

export interface Tree {
  element: HTMLElement;
  set: (value: Value) => void;
  search: (words: string) => number;
  select: (parts: Part[]) => void;
  selected: () => Part[];
}

function shown(value: Value, schema: boolean): string {
  if (schema && typeof value === "string") return value;
  if (typeof value === "string") return JSON.stringify(value);
  return String(value);
}

/** A structure as a tree in `host`'s place: folding, selection, search, edits when allowed. */
export function mountTree(value: Value, options: TreeOptions = {}): Tree {
  const depth = options.depth ?? 2;
  const open = new Map<string, boolean>();
  const more = new Map<string, number>();
  let current = value;
  let words = "";
  let selected: Part[] = [];
  const element = h("div", { class: "structure-tree", role: "tree", "aria-label": options.label ?? "Tree", tabindex: 0 });

  const matches = (text: string): boolean => Boolean(words) && text.toLowerCase().includes(words);
  const hasMatch = (node: Value, budget = { n: 2000 }): boolean => {
    if (!words || budget.n-- <= 0) return false;
    if (node === null || typeof node !== "object") return matches(String(node));
    if (Array.isArray(node)) return node.some((v) => hasMatch(v, budget));
    return Object.entries(node).some(([k, v]) => matches(k) || hasMatch(v, budget));
  };
  const mark = (text: string): Node[] => {
    if (!words) return [document.createTextNode(text)];
    const out: Node[] = [];
    const low = text.toLowerCase();
    let at = 0;
    for (let i = low.indexOf(words); i >= 0; i = low.indexOf(words, at)) {
      out.push(document.createTextNode(text.slice(at, i)), h("mark", {}, text.slice(i, i + words.length)));
      at = i + words.length;
    }
    out.push(document.createTextNode(text.slice(at)));
    return out;
  };

  const editInPlace = (target: HTMLElement, start: string, done: (text: string) => void): void => {
    const input = h("input", { class: "structure-edit", value: start, "aria-label": "Edit", spellcheck: false }) as HTMLInputElement;
    target.replaceChildren(input);
    input.focus();
    input.select();
    let finished = false;
    const finish = (keep: boolean): void => {
      if (finished) return;
      finished = true;
      if (keep && input.value !== start) done(input.value);
      else draw();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") finish(true);
      if (e.key === "Escape") finish(false);
      e.stopPropagation();
    });
    input.addEventListener("blur", () => finish(true));
  };

  const row = (key: Part | null, node: Value, parts: Part[], level: number): HTMLElement => {
    const id = pathText(parts);
    const kind = kindOf(node);
    const container = kind === "object" || kind === "list";
    const count = container ? (Array.isArray(node) ? node.length : Object.keys(node as object).length) : 0;
    const isOpen = open.get(id) ?? (level < depth || (words !== "" && hasMatch(node)));
    const here = pathText(selected) === id;
    const keyText = key === null ? "$" : typeof key === "number" ? `[${key}]` : key;
    const keySpan = h("span", { class: `structure-key${typeof key === "number" ? " index" : ""}${options.schema && typeof key === "string" && key.endsWith("*") ? " required" : ""}` }, ...mark(keyText));
    const line = h(
      "div",
      {
        class: `structure-row${here ? " selected" : ""}`,
        role: "treeitem",
        "aria-level": level + 1,
        "aria-selected": here ? "true" : "false",
        "aria-expanded": container ? (isOpen ? "true" : "false") : undefined,
        "data-path": id,
        style: `padding-left:${level * 16 + 4}px`,
      },
      container
        ? h("button", { type: "button", class: "structure-caret", "aria-label": isOpen ? "Fold" : "Unfold", tabindex: -1, onclick: (e: MouseEvent) => {
            e.stopPropagation();
            open.set(id, !isOpen);
            draw();
          } }, icon(isOpen ? "down" : "forward"))
        : h("span", { class: "structure-caret-space" }),
      keySpan,
    );
    if (container) {
      line.append(h("span", { class: `structure-type t-${kind}` }, kind === "list" ? `list · ${count}` : `object · ${count}`));
    } else {
      const valueSpan = h("span", { class: `structure-value t-${kind}` }, ...mark(shown(node, Boolean(options.schema))));
      line.append(h("span", { class: "structure-colon" }, ":"), valueSpan);
      if (options.onSet) {
        valueSpan.addEventListener("dblclick", (e) => {
          e.stopPropagation();
          editInPlace(valueSpan, typeof node === "string" ? node : JSON.stringify(node), (text) => {
            let typed: Value = text;
            if (typeof node !== "string") {
              try {
                typed = JSON.parse(text) as Value;
              } catch {
                typed = text;
              }
            }
            options.onSet?.(parts, typed);
          });
        });
      }
    }
    if (options.onRename && typeof key === "string") {
      keySpan.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        editInPlace(keySpan, key, (to) => options.onRename?.(parts.slice(0, -1), key, to));
      });
    }
    line.addEventListener("click", () => {
      // Marked in place (no redraw): a double click that follows lands on the same row.
      selected = parts;
      for (const was of element.querySelectorAll(".structure-row.selected")) {
        was.classList.remove("selected");
        was.setAttribute("aria-selected", "false");
      }
      line.classList.add("selected");
      line.setAttribute("aria-selected", "true");
      options.onSelect?.(parts, node);
    });
    const group = h("div", { class: "structure-node" }, line);
    if (container && isOpen) {
      const kids = h("div", { role: "group" });
      if (Array.isArray(node)) {
        const limit = more.get(id) ?? PAGE;
        node.slice(0, limit).forEach((v, i) => kids.append(row(i, v, [...parts, i], level + 1)));
        if (node.length > limit) {
          kids.append(h("button", { type: "button", class: "structure-more", style: `margin-left:${(level + 1) * 16 + 24}px`, onclick: () => {
            more.set(id, limit + PAGE * 5);
            draw();
          } }, `Show more (${node.length - limit})`));
        }
      } else {
        for (const [k, v] of Object.entries(node as Record<string, Value>)) kids.append(row(k, v, [...parts, k], level + 1));
      }
      group.append(kids);
    }
    return group;
  };

  const draw = (): void => {
    const top = element.scrollTop;
    element.replaceChildren(row(null, current, [], 0));
    element.scrollTop = top;
  };

  element.addEventListener("keydown", (e) => {
    const rows = [...element.querySelectorAll<HTMLElement>(".structure-row")];
    const at = rows.findIndex((r) => r.classList.contains("selected"));
    const go = (n: number): void => {
      const target = rows[Math.max(0, Math.min(rows.length - 1, n))];
      target?.click();
      element.querySelector(".structure-row.selected")?.scrollIntoView({ block: "nearest" });
    };
    if (e.key === "ArrowDown") go(at + 1);
    else if (e.key === "ArrowUp") go(at - 1);
    else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      const id = pathText(selected);
      open.set(id, e.key === "ArrowRight");
      draw();
    } else return;
    e.preventDefault();
  });

  draw();
  return {
    element,
    set: (v) => {
      current = v;
      if (nodeAt(v, selected) === undefined) selected = [];
      draw();
    },
    search: (text) => {
      words = text.trim().toLowerCase();
      draw();
      return element.querySelectorAll("mark").length;
    },
    select: (parts) => {
      selected = parts;
      for (let i = 0; i < parts.length; i++) open.set(pathText(parts.slice(0, i)), true);
      draw();
      element.querySelector(".structure-row.selected")?.scrollIntoView({ block: "nearest" });
    },
    selected: () => selected,
  };
}

// ===== the text view: Monaco, loaded when first needed =====

let editors: Promise<typeof import("./lazy/codeEditor")> | null = null;
export function loadEditors(): Promise<typeof import("./lazy/codeEditor")> {
  if (!document.querySelector('link[href="/static/build/lazy/codeEditor.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/build/lazy/codeEditor.css" }));
  }
  return (editors ??= import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>);
}

export interface TextView {
  element: HTMLElement;
  value: () => string;
  set: (text: string, format: Format) => void;
  setReadOnly: (readOnly: boolean) => void;
  /** An error at its line ("line 3, column 5: ..."), or none. */
  setError: (message: string | null) => void;
  dispose: () => void;
}

/** The text view: a plain box at once, Monaco in its place as soon as it has loaded. */
export function mountText(text: string, format: Format, onChange: (text: string) => void, label = "Text"): TextView {
  const plain = h("textarea", { class: "mono structure-text-plain", spellcheck: false, "aria-label": label }, text) as HTMLTextAreaElement;
  plain.addEventListener("input", () => onChange(plain.value));
  const host = h("div", { class: "structure-text-host" }, plain);
  const error = h("div", { class: "structure-text-error", hidden: true });
  const element = h("div", { class: "structure-text" }, host, error);
  let editor: CodeEditor | null = null;
  let gone = false;
  let readOnly = false;
  let quiet = false;
  void loadEditors().then(
    (m) => {
      if (gone || !host.isConnected) return;
      const mount = h("div", { class: "structure-monaco", "aria-label": label });
      host.replaceChildren(mount);
      editor = m.createCodeEditor(mount, { language: format, value: plain.value, theme: effectiveTheme(), readOnly });
      editor.onChange(() => {
        if (!quiet && editor) onChange(editor.value());
      });
    },
    () => undefined, // the plain box stays
  );
  return {
    element,
    value: () => editor?.value() ?? plain.value,
    set: (next, fmt) => {
      quiet = true;
      if (editor) {
        editor.setLanguage(fmt);
        if (editor.value() !== next) editor.setValue(next);
      } else if (plain.value !== next) plain.value = next;
      quiet = false;
    },
    setReadOnly: (on) => {
      readOnly = on;
      editor?.setReadOnly(on);
      plain.readOnly = on;
    },
    setError: (message) => {
      error.hidden = !message;
      error.replaceChildren(...(message ? [errorNote(message, { dismiss: false })] : []));
      const found = message ? /line (\d+)(?:, column (\d+))?/.exec(message) : null;
      const problems: Problem[] = found
        ? [{ line: Number(found[1]), col: found[2] ? Number(found[2]) : null, endLine: Number(found[1]), endCol: null, message: message ?? "", hover: message ?? "", severity: "error", fixes: [] }]
        : [];
      editor?.setProblems(problems);
    },
    dispose: () => {
      gone = true;
      editor?.dispose();
    },
  };
}
