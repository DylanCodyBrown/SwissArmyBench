/**
 * lazy/codeEditor.ts: the Monaco editor for the Workbench (a notebook's cells, a script), the Python
 * connection form and the grid page's "+" tab (createSqlEditor, at the end). [WIRE]
 *
 * Python, SQL, DAX, HTML or Markdown; the theme follows the page. A cell editor grows with its text (no
 * scrollbar of its own); a script's fills its pane. Drop text on it (a table's name from the left panel)
 * and it lands where it was dropped; a blade's line lands on a line of its own (ownDrops).
 */
import * as monaco from "monaco-editor";

(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  // TypeScript and TSX (a code app's files) have Monaco's own language service, in a worker of its own.
  getWorker: (_id: string, label: string) =>
    new Worker(label === "typescript" || label === "javascript" ? "/static/build/ts.worker.js" : "/static/build/editor.worker.js", { type: "module" }),
};

// HTML is coloured by Monaco's own grammar (the tags, and the CSS and JavaScript inside them). Its
// language service would need a worker of its own, which this page does not ship: it is switched off.
monaco.html.htmlDefaults.setModeConfiguration({
  completionItems: false,
  hovers: false,
  documentSymbols: false,
  links: false,
  documentHighlights: false,
  rename: false,
  colors: false,
  foldingRanges: false,
  diagnostics: false,
  selectionRanges: false,
  documentFormattingEdits: false,
  documentRangeFormattingEdits: false,
});

export type EditorLanguage = "python" | "sql" | "dax" | "markdown" | "html" | "json" | "yaml" | "xml" | "toml" | "typescript" | "tsx" | "javascript" | "css" | "plaintext";
/** Monaco's own name for a language: its DAX grammar is `msdax` (keywords, functions, 'Table'[Column], [Measure]);
 *  TOML is coloured as INI (Structures: the server checks each format and says where an error is). */
const monacoId = (language: EditorLanguage): string => (language === "dax" ? "msdax" : language === "toml" ? "ini" : language === "tsx" ? "typescript" : language);

// ===== TypeScript: a code app's files (the Power Apps extension's), with Monaco's own language service =====

let typescriptReady = false;
const projectLibs = new Map<string, monaco.IDisposable>();

/** The language service set for a code app (React's JSX, modern modules), and the project's own files known
 *  to it (its generated models and services, its other modules), so imports between them resolve and the
 *  member lists, parameter info and hovers are the project's. Packages under node_modules are not read: a
 *  "cannot find module" for them is not shown. */
export function typescriptProject(files: { path: string; text: string }[]): void {
  const ts = monaco.typescript;
  if (!typescriptReady) {
    typescriptReady = true;
    ts.typescriptDefaults.setCompilerOptions({
      target: ts.ScriptTarget.ESNext,
      module: ts.ModuleKind.ESNext,
      moduleResolution: ts.ModuleResolutionKind.NodeJs,
      jsx: ts.JsxEmit.ReactJSX,
      allowNonTsExtensions: true,
      allowJs: true,
      esModuleInterop: true,
      strict: true,
      skipLibCheck: true,
    });
    // 2307/2792: a package not read here; 7016: its types; 2875: JSX's runtime package; 17004: JSX flag; 7026: JSX's element types (React's own types are in node_modules).
    ts.typescriptDefaults.setDiagnosticsOptions({ noSemanticValidation: false, noSyntaxValidation: false, diagnosticCodesToIgnore: [2307, 2792, 7016, 2875, 17004, 7026] });
    ts.typescriptDefaults.setEagerModelSync(true);
  }
  for (const file of files) {
    const uri = `file:///${file.path.replace(/^\/+/, "")}`;
    projectLibs.get(uri)?.dispose();
    projectLibs.set(uri, ts.typescriptDefaults.addExtraLib(file.text, uri));
  }
}

// JSON (Structures' text view) is coloured by Monaco's grammar; its language service would need a worker of
// its own: the server checks the text instead, and says the line of an error.
monaco.json.jsonDefaults.setModeConfiguration({
  documentFormattingEdits: false,
  documentRangeFormattingEdits: false,
  completionItems: false,
  hovers: false,
  documentSymbols: false,
  tokens: true,
  colors: false,
  foldingRanges: true,
  diagnostics: false,
  selectionRanges: false,
});

const THEMES: Record<string, string> = { light: "vs", dark: "vs-dark", "hc-light": "hc-light", "hc-dark": "hc-black" };

/** A completion: what it shows, what it inserts, its kind (variable, function, table, column...). */
export interface Suggestion {
  label: string;
  insert?: string;
  kind?: string;
  detail?: string;
  /** Where the insert goes, as offsets into the text (default: the word at the cursor). */
  start?: number;
  end?: number;
  /** What the typed text is matched against, when it is not the label: a DAX name's insert begins
   *  with the quote or bracket already typed ('Customer', [Total Sales]). */
  filter?: string;
  /** The documentation panel beside the list (markdown, no HTML). */
  documentation?: string;
  /** Inserted as a snippet: a call's required arguments as tab stops (`f(${1:a}, ${2:b})$0`). */
  snippet?: string;
  /** More edits it makes (an import line added), 1-based lines and columns. */
  edits?: { line: number; col: number; end_line: number; end_col: number; text: string }[];
  /** Its place in the list, as the server ranked it. */
  sort?: string;
  /** Drawn after the name, faded (a function's parameters), and at the row's right (its type or module). */
  labelDetail?: string;
  description?: string;
}

/** A problem the lint found as you type (services/intellisense.py): 1-based lines and columns. */
export interface IntelProblem {
  line: number;
  col: number;
  end_line: number;
  end_col: number;
  message: string;
  severity: "error" | "warning" | "hint" | "info";
  code: string;
  source: string;
  unnecessary?: boolean;
  fixes?: { kind: string; title: string; edits: { line: number; col: number; end_line: number; end_col: number; text: string }[] }[];
}

/** Parameter info for the call at the cursor (Jedi's signatures). */
export interface Signatures {
  signatures: {
    label: string;
    params: { name: string; label: string; span: [number, number] | null; words: string; type: string }[];
    active: number | null;
    returns: string;
    summary: string;
    returns_words: string;
  }[];
}

/** The editors' intelligence an editor asks (workbenchIntel.ts): parameter info, quick info, the lint. */
export interface Intel {
  signature?: (text: string, offset: number) => Promise<Signatures | null>;
  hover?: (text: string, offset: number) => Promise<string>;
  lint?: (text: string) => Promise<IntelProblem[] | null>;
  /** Told what the lint shows now (the status bar's count). */
  onLint?: (problems: IntelProblem[]) => void;
}
export type Completer = (text: string, offset: number) => Promise<Suggestion[]>;

/** A place a run's error went through (workbenchErrors.ts): a squiggle, a message at the line's end,
 *  a hover card, and quick fixes (Ctrl+.). Lines and columns 1-based; a null column marks the line. */
export interface Problem {
  line: number;
  col: number | null;
  endLine: number;
  endCol: number | null;
  message: string;
  /** Markdown for the hover card (escaped: no HTML). */
  hover: string;
  severity: "error" | "info";
  fixes: { kind: string; title: string; target?: string; text?: string; line?: string }[];
}
export type Helper = (text: string, offset: number) => Promise<string>;

/** `@cell7` in a comment links to cell 7: what the editor asks of its document. */
export interface CellLinks {
  /** The cell's first line of code (null: there is no such cell). */
  first: (number: number) => string | null;
  go: (number: number) => void;
}

/** A script's cells, for folding and drawing (domain/table_cells.py outline). Lines are 1-based. */
export interface ScriptOutline {
  region: [number, number] | null;
  cells: {
    number: number | null;
    line: number;
    end: number;
    role: string;
    table: string | null;
    grouped: boolean;
    first: string;
    /** html: an HTML cell (its lines hold the HTML as one Python string). */
    kind?: "code" | "html" | "streamlit";
    /** An HTML cell's HTML (null: its lines are not one string yet; `problem` says why). */
    html?: string | null;
    problem?: string | null;
    /** The last line of the string that holds the HTML. */
    html_end?: number;
    /** Its pane's saved height (null: the design's own). */
    height?: number | null;
  }[];
}

/** What a script's editor draws beside its Tables group: the words after a line, and its colour. */
export interface LineNote {
  line: number;
  text: string;
  /** stale: out of date (yellow). */
  tone: "plain" | "stale";
  /** Draw the line as a cell's marker. */
  marker?: boolean;
}

// Each editor's own completer and help (a notebook cell's kernel and connection, a script's kernel).
const completers = new WeakMap<monaco.editor.ITextModel, { complete?: Completer; help?: Helper; intel?: Intel }>();
// What the lint shows on each editor (its fixes are Ctrl+.'s).
const linted = new WeakMap<monaco.editor.ITextModel, IntelProblem[]>();
const LINT = "sab-lint";
// The lint waits this long after the last keystroke.
const LINT_MS = 400;
const RECENT = "sab-intel-recent"; // workbenchIntel.ts reads it

/** A completion was chosen: it comes first next time, in its group. */
function chosen(label: string): void {
  try {
    const list = [label, ...(JSON.parse(localStorage.getItem(RECENT) ?? "[]") as string[]).filter((l) => l !== label)].slice(0, 50);
    localStorage.setItem(RECENT, JSON.stringify(list));
  } catch {
    /* no storage: nothing remembered */
  }
}
let chosenRegistered = false;
// Monaco's suggest widget, as far as opening its documentation panel goes (not in its public API).
interface SuggestWidget {
  onDidShow: (listener: () => void) => unknown;
  onDidFocus?: (listener: () => void) => unknown;
  _isDetailsVisible: () => boolean;
  toggleDetails: () => void;
}
let detailsOpened = false;
const cellLinks = new WeakMap<monaco.editor.ITextModel, CellLinks>();
const outlines = new WeakMap<monaco.editor.ITextModel, ScriptOutline>();
const CELL_LINK = /@cell(\d+)\b/g;

/** Where a line's comment starts (0-based column; -1: it has none). Python's `#`, SQL's `--`; a
 *  Markdown cell is all words; DAX's is `--`, as SQL's. A `#` inside a quoted text on the line is not a comment. */
function commentStart(line: string, language: string): number {
  if (language === "markdown" || language === "html") return 0;
  const mark = language === "sql" || language === "msdax" ? "--" : "#";
  let quote = "";
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]!;
    if (quote) {
      if (ch === "\\") i++;
      else if (ch === quote) quote = "";
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (line.startsWith(mark, i)) return i;
  }
  return -1;
}

/** The cell links on a line: each one's number and columns (1-based, end exclusive). */
function linksOn(line: string, language: string): { number: number; start: number; end: number }[] {
  const from = commentStart(line, language);
  if (from < 0) return [];
  const found: { number: number; start: number; end: number }[] = [];
  for (const match of line.matchAll(CELL_LINK)) {
    if (match.index >= from) found.push({ number: Number(match[1]), start: match.index + 1, end: match.index + 1 + match[0].length });
  }
  return found;
}

function linkAt(model: monaco.editor.ITextModel, position: monaco.IPosition): { number: number; range: monaco.Range } | null {
  if (!cellLinks.has(model)) return null;
  const hit = linksOn(model.getLineContent(position.lineNumber), model.getLanguageId()).find((l) => position.column >= l.start && position.column <= l.end);
  return hit ? { number: hit.number, range: new monaco.Range(position.lineNumber, hit.start, position.lineNumber, hit.end) } : null;
}

// Fired when a script's outline changes: Monaco asks for the folds again.
const foldsChanged = new monaco.Emitter<monaco.languages.FoldingRangeProvider>();

/** Folding by indentation (what Monaco does by itself for Python), as ranges. */
function indentRanges(model: monaco.editor.ITextModel): monaco.languages.FoldingRange[] {
  const count = model.getLineCount();
  const indents: number[] = [];
  for (let line = 1; line <= count; line++) {
    const text = model.getLineContent(line);
    indents.push(text.trim() ? text.length - text.trimStart().length : -1);
  }
  const ranges: monaco.languages.FoldingRange[] = [];
  const open: { line: number; indent: number }[] = [];
  let lastCode = 0;
  for (let line = 1; line <= count + 1; line++) {
    const indent = line <= count ? indents[line - 1]! : 0;
    if (indent < 0) continue;
    while (open.length && open[open.length - 1]!.indent >= indent) {
      const started = open.pop()!;
      if (lastCode > started.line) ranges.push({ start: started.line, end: lastCode });
    }
    if (line <= count) open.push({ line, indent });
    lastCode = line;
  }
  return ranges;
}

/** Python folds: its blocks, a script's Tables group, each table of it, each cell. */
function foldingRanges(model: monaco.editor.ITextModel): monaco.languages.FoldingRange[] {
  const ranges = indentRanges(model);
  const outline = outlines.get(model);
  if (!outline) return ranges;
  if (outline.region) ranges.push({ start: outline.region[0], end: outline.region[1], kind: monaco.languages.FoldingRangeKind.Region });
  for (const [i, cell] of outline.cells.entries()) {
    // A table's own cells fold as one: its maker's marker down to the end of its transformations.
    const next = outline.cells[i + 1];
    const pair = cell.grouped && cell.role === "maker" && next?.role === "transformations" && next.table === cell.table;
    const end = pair ? next.end : cell.end;
    const alone = cell.role !== "transformations" || outline.cells[i - 1]?.role !== "maker" || outline.cells[i - 1]?.table !== cell.table || !cell.grouped;
    if ((pair || alone) && end > cell.line) ranges.push({ start: cell.line, end });
  }
  return ranges;
}
// Each editor's problems from its last failed run (cleared by the next edit or run).
const problems = new WeakMap<monaco.editor.ITextModel, Problem[]>();
const PROBLEMS = "sab-run";

function rangeOf(model: monaco.editor.ITextModel, p: Problem): monaco.Range {
  const last = Math.min(Math.max(p.endLine, p.line), model.getLineCount());
  const line = Math.min(p.line, model.getLineCount());
  const start = p.col ?? model.getLineFirstNonWhitespaceColumn(line) ?? 1;
  const end = p.endCol ?? model.getLineMaxColumn(last);
  return new monaco.Range(line, Math.max(1, start), last, Math.max(start + (line === last ? 1 : 0), end));
}
const registered = new Set<string>();
let editorCount = 0;
const KINDS: Record<string, monaco.languages.CompletionItemKind> = {
  function: monaco.languages.CompletionItemKind.Function,
  method: monaco.languages.CompletionItemKind.Method,
  class: monaco.languages.CompletionItemKind.Class,
  module: monaco.languages.CompletionItemKind.Module,
  instance: monaco.languages.CompletionItemKind.Variable,
  statement: monaco.languages.CompletionItemKind.Variable,
  keyword: monaco.languages.CompletionItemKind.Keyword,
  param: monaco.languages.CompletionItemKind.Variable,
  path: monaco.languages.CompletionItemKind.File,
  property: monaco.languages.CompletionItemKind.Property,
  table: monaco.languages.CompletionItemKind.Struct,
  struct: monaco.languages.CompletionItemKind.Struct,
  variable: monaco.languages.CompletionItemKind.Variable,
  view: monaco.languages.CompletionItemKind.Interface,
  schema: monaco.languages.CompletionItemKind.Folder,
  column: monaco.languages.CompletionItemKind.Field,
  connection: monaco.languages.CompletionItemKind.Reference,
};

/** One completion and one hover provider per language, asking the editor's own completer. */
function register(language: string): void {
  if (registered.has(language)) return;
  registered.add(language);
  if (!chosenRegistered) {
    chosenRegistered = true;
    monaco.editor.registerCommand("sab.intel.chosen", (_accessor, label: string) => chosen(label));
  }
  monaco.languages.registerCompletionItemProvider(language, {
    triggerCharacters: language === "msdax" ? [".", "'", "["] : [".", "\"", "'"],
    provideCompletionItems: async (model, position) => {
      const own = completers.get(model)?.complete;
      if (!own) return { suggestions: [] };
      const offset = model.getOffsetAt(position);
      const found = await own(model.getValue(), offset);
      const word = model.getWordUntilPosition(position);
      const wordRange = new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn);
      return {
        // Asked again as typing goes on: the kernel's list changes with what is typed (a DataFrame's
        // columns come once a letter follows the dot), and it answers in well under a tenth of a second.
        incomplete: true,
        suggestions: found.map((s, i) => {
          const range = s.start !== undefined ? monaco.Range.fromPositions(model.getPositionAt(s.start), model.getPositionAt(s.end ?? offset)) : wordRange;
          return {
            label: s.labelDetail || s.description ? { label: s.label, detail: s.labelDetail, description: s.description } : s.label,
            insertText: s.snippet ?? s.insert ?? s.label,
            insertTextRules: s.snippet ? monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet : undefined,
            filterText: s.filter ?? (s.labelDetail || s.description ? s.label : undefined),
            kind: KINDS[s.kind ?? ""] ?? monaco.languages.CompletionItemKind.Text,
            detail: s.detail ?? s.kind,
            documentation: s.documentation ? { value: s.documentation, supportHtml: false } : undefined,
            additionalTextEdits: s.edits?.map((e) => ({ range: new monaco.Range(e.line, e.col, e.end_line, e.end_col), text: e.text })),
            command: { id: "sab.intel.chosen", title: "", arguments: [s.label] },
            range,
            sortText: s.sort ?? String(i).padStart(5, "0"), // the order the completer gave
          };
        }),
      };
    },
  });
  monaco.languages.registerHoverProvider(language, {
    provideHover: async (model, position) => {
      // A problem under the pointer: its card first (Monaco's own marker hover sits above it).
      const here = (problems.get(model) ?? []).find((p) => rangeOf(model, p).containsPosition(position));
      if (here) return { range: rangeOf(model, here), contents: [{ value: here.hover, supportHtml: false }] };
      // A link to a cell: that cell's first line.
      const link = linkAt(model, position);
      if (link) {
        const first = cellLinks.get(model)!.first(link.number);
        const words = first === null ? `There is no cell ${link.number} in this document.` : `Cell ${link.number}` + (first ? "\n```\n" + first.replace(/```/g, "ˋˋˋ") + "\n```" : " (empty)");
        return { range: link.range, contents: [{ value: words, supportHtml: false }] };
      }
      // Quick info: the signature or the variable's type, and the docstring (Jedi's); else the kernel's help.
      const own = completers.get(model);
      const word = model.getWordAtPosition(position);
      if (own?.intel?.hover && word) {
        const words = await own.intel.hover(model.getValue(), model.getOffsetAt(position));
        if (words) return { range: new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn), contents: [{ value: words, supportHtml: false }] };
      }
      const help = own?.help;
      if (!help) return null;
      const text = await help(model.getValue(), model.getOffsetAt(position));
      return text ? { contents: [{ value: "```\n" + text.replace(/```/g, "ˋˋˋ") + "\n```" }] } : null;
    },
  });
  // Parameter info while a call is typed: each signature (overloads with up and down), the current
  // parameter bold with its own words, the return type.
  if (language === "python")
    monaco.languages.registerSignatureHelpProvider("python", {
      signatureHelpTriggerCharacters: ["(", ","],
      signatureHelpRetriggerCharacters: [",", ")"],
      provideSignatureHelp: async (model, position) => {
        const ask = completers.get(model)?.intel?.signature;
        if (!ask) return null;
        const found = await ask(model.getValue(), model.getOffsetAt(position));
        if (!found) return null;
        const returns = (sig: Signatures["signatures"][number]): string =>
          sig.returns ? `**Returns** \`${sig.returns}\`${sig.returns_words ? `: ${sig.returns_words}` : ""}` : sig.returns_words ? `**Returns** ${sig.returns_words}` : "";
        const signatures = found.signatures.map((sig) => ({
          label: sig.label,
          documentation: { value: [sig.summary, returns(sig)].filter(Boolean).join("\n\n") },
          parameters: sig.params.map((p) => ({
            label: (p.span ?? p.label) as [number, number] | string,
            documentation: { value: [`\`${p.label}\``, p.words].filter(Boolean).join(": ") },
          })),
          activeParameter: sig.active ?? undefined,
        }));
        return { value: { signatures, activeSignature: 0, activeParameter: found.signatures[0]?.active ?? 0 }, dispose: () => undefined };
      },
    });
  if (language === "python") monaco.languages.registerFoldingRangeProvider("python", { onDidChange: foldsChanged.event, provideFoldingRanges: (model) => foldingRanges(model) });
  // Quick fixes (Ctrl+., the light bulb, the hover's "Quick Fix…"): a close name, an import.
  monaco.languages.registerCodeActionProvider(language, {
    provideCodeActions: (model, range) => {
      const actions: monaco.languages.CodeAction[] = [];
      // The lint's fixes: add the import, remove the unused one, define it from the Variables page, a close name.
      for (const p of linted.get(model) ?? []) {
        const at = new monaco.Range(p.line, p.col, p.end_line, p.end_col);
        if (!at.intersectRanges(range) && at.startLineNumber !== range.startLineNumber) continue;
        for (const fix of p.fixes ?? []) {
          if (!fix.edits.length) continue;
          actions.push({
            title: fix.title.replace(/`/g, ""),
            kind: "quickfix",
            isPreferred: actions.length === 0,
            edit: { edits: fix.edits.map((e) => ({ resource: model.uri, textEdit: { range: new monaco.Range(e.line, e.col, e.end_line, e.end_col), text: e.text }, versionId: model.getVersionId() })) },
          });
        }
      }
      for (const p of problems.get(model) ?? []) {
        const at = rangeOf(model, p);
        if (!at.intersectRanges(range) && at.startLineNumber !== range.startLineNumber) continue;
        for (const fix of p.fixes) {
          const edit = fixEdit(model, at, fix);
          if (!edit) continue;
          actions.push({ title: fix.title.replace(/`/g, ""), kind: "quickfix", isPreferred: actions.length === 0, edit: { edits: [{ resource: model.uri, textEdit: edit, versionId: model.getVersionId() }] } });
        }
      }
      return { actions, dispose: () => undefined };
    },
  });
}

/** The text edit a fix makes: the close name in place of the wrong one on the failing line(s), or an
 *  import line at the top. */
function fixEdit(model: monaco.editor.ITextModel, at: monaco.Range, fix: Problem["fixes"][number]): monaco.languages.TextEdit | null {
  if (fix.kind === "import" && fix.line) return { range: new monaco.Range(1, 1, 1, 1), text: `${fix.line}\n` };
  if (fix.kind !== "replace" || !fix.target || fix.text === undefined) return null;
  const pattern = new RegExp(`(?<![\\w])${fix.target.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\w])`);
  for (let line = at.startLineNumber; line <= at.endLineNumber; line++) {
    const text = model.getLineContent(line);
    const found = pattern.exec(text);
    if (found) return { range: new monaco.Range(line, found.index + 1, line, found.index + 1 + fix.target.length), text: fix.text };
  }
  return null;
}

/** The changed pieces between two lists of lines: `removed` old lines from line `start` (1-based)
 *  become `lines`. The same lines at the start and the end are left alone; a small middle is compared
 *  line by line (longest common run), a large one is one piece. */
export function lineHunks(before: string[], after: string[]): { start: number; removed: number; lines: string[] }[] {
  let head = 0;
  while (head < before.length && head < after.length && before[head] === after[head]) head++;
  let tail = 0;
  while (tail < before.length - head && tail < after.length - head && before[before.length - 1 - tail] === after[after.length - 1 - tail]) tail++;
  const a = before.slice(head, before.length - tail);
  const b = after.slice(head, after.length - tail);
  if (!a.length && !b.length) return [];
  if (a.length * b.length > 250_000 || !a.length || !b.length) return [{ start: head + 1, removed: a.length, lines: b }];
  // Longest common subsequence of the middle's lines.
  const width = b.length + 1;
  const table = new Uint32Array((a.length + 1) * width);
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) table[i * width + j] = a[i] === b[j] ? table[(i + 1) * width + j + 1]! + 1 : Math.max(table[(i + 1) * width + j]!, table[i * width + j + 1]!);
  }
  const hunks: { start: number; removed: number; lines: string[] }[] = [];
  let i = 0;
  let j = 0;
  let open: { start: number; removed: number; lines: string[] } | null = null;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      open = null;
      i++;
      j++;
      continue;
    }
    if (!open) hunks.push((open = { start: head + i + 1, removed: 0, lines: [] }));
    if (j < b.length && (i >= a.length || table[i * width + j + 1]! >= table[(i + 1) * width + j]!)) open.lines.push(b[j++]!);
    else {
      open.removed++;
      i++;
    }
  }
  return hunks;
}

export interface CodeEditor {
  value: () => string;
  setValue: (text: string) => void;
  /** The selected text, or the cursor's line when nothing is selected. */
  selection: () => string;
  /** What is selected, null when nothing is: its text, and its first and last line (1-based). */
  selected: () => { text: string; startLine: number; endLine: number; wholeLines: string } | null;
  cursorLine: () => number;
  lineCount: () => number;
  /** Lines `start` to `end` (1-based, both included). */
  lines: (start: number, end: number) => string;
  /** The cursor to the start of a line, scrolled into view. */
  moveTo: (line: number) => void;
  /** Make the text `text` by changing only the lines that differ, in one edit that undoes with the
   *  typing before it. The cursor stays on its own text and that text stays where it is on screen.
   *  False: nothing differed. */
  replaceText: (text: string) => boolean;
  /** Typing is refused (a table's read-only cell); the app still writes with replaceText. */
  setReadOnly: (readOnly: boolean) => void;
  /** A script's cells: folds for the Tables group, each table and each cell. */
  setOutline: (outline: ScriptOutline | null) => void;
  /** Fold the lines that start at these line numbers (a script's Tables group, a table). */
  fold: (lines: number[]) => void;
  unfold: (lines: number[]) => void;
  /** Words drawn after lines (a table's state beside its marker), and cell markers drawn as rules. */
  setLineNotes: (notes: LineNote[]) => void;
  /** Connection colours (connectionColours.ts): a stripe in the margin beside each run of lines (a
   *  script's cell) that names a connection; two colours side by side for two connections. [] clears. */
  setStripes: (stripes: Stripe[]) => void;
  /** A new line as Enter makes it (keeping the indent). */
  insertNewline: () => void;
  /** Put text in as one edit (undone at once): where a point on the editor is (a drop), else at the
   *  cursor, over what is selected. */
  insertAt: (text: string, x?: number, y?: number) => void;
  /** The cursor at the very end of the text. */
  atEnd: () => boolean;
  /** The cursor's offset into the text. */
  cursorOffset: () => number;
  /** Told the cursor's line and column whenever it moves. */
  onCursor: (listener: (line: number, column: number) => void) => void;
  /** Gets the keyboard focus (a notebook knows which cell is being edited). */
  onFocus: (listener: () => void) => void;
  onBlur: (listener: () => void) => void;
  hasFocus: () => boolean;
  /** Show a failed run's problems (squiggles, end-of-line messages); [] clears them. */
  setProblems: (list: Problem[]) => void;
  /** Make a fix's edit (replace a name, add an import); false when it no longer applies. */
  applyFix: (fix: Problem["fixes"][number], near: number) => boolean;
  /** The cursor to a line and column, scrolled into view, with the focus. */
  reveal: (line: number, column?: number) => void;
  setLanguage: (language: EditorLanguage) => void;
  /** Panes drawn between lines (a script's HTML cells as designs): each after its line, at its height. */
  setZones: (zones: Zone[]) => void;
  /** Lines not shown (a script's HTML cell while its design shows): first and last line of each run. */
  setHidden: (ranges: [number, number][]) => void;
  focus: () => void;
  setTheme: (theme: string) => void;
  /** Lint now (the language or the kernel changed), and what the lint shows. */
  lint: () => void;
  lintProblems: () => IntelProblem[];
  /** Told of every change; `undo`: it was an undo or a redo (the app does not answer those with edits). */
  onChange: (listener: (change: { undo: boolean }) => void) => void;
  layout: () => void;
  dispose: () => void;
}

/** Lines `start` to `end` (1-based) wearing these colours (#rrggbb, the first one or two). */
export interface Stripe {
  start: number;
  end: number;
  colours: string[];
}

// One small class per colour pair, made once on the page (the margin's stripe needs a class).
const stripeClasses = new Map<string, string>();
function stripeClass(colours: string[]): string {
  const [a, b] = [colours[0]!, colours[1] ?? colours[0]!].map((c) => c.toLowerCase().replace(/[^#0-9a-f]/g, ""));
  const key = `${a}${b}`;
  let name = stripeClasses.get(key);
  if (!name) {
    name = `sab-stripe-${a!.slice(1)}-${b!.slice(1)}`;
    stripeClasses.set(key, name);
    const style = document.createElement("style");
    style.textContent = `.${name}{background:linear-gradient(to right,${a} 0 3px,${b} 3px 6px,transparent 6px)!important;width:6px!important;margin-left:0}`;
    document.head.append(style);
  }
  return name;
}

/** A pane between a script's lines. */
export interface Zone {
  id: string;
  /** The line it comes after (1-based). */
  afterLine: number;
  height: number;
  element: HTMLElement;
}

export interface CodeEditorOptions {
  language: EditorLanguage;
  value: string;
  theme: string;
  /** Grow with the text (a notebook cell); otherwise fill the host (a script). */
  grow?: boolean;
  /** Keys: Shift+Enter, Ctrl+Enter (and F9), F5. Enter, Up and Down (the console): taken only with
   *  no suggestion list open; Up and Down answer false to move the cursor as usual. */
  keys?: {
    shiftEnter?: () => void;
    ctrlEnter?: () => void;
    f5?: () => void;
    escape?: () => void;
    enter?: () => void;
    up?: () => boolean;
    down?: () => boolean;
    /** F1: help on the name at the cursor (instead of Monaco's own command list). */
    f1?: () => void;
  };
  placeholder?: string;
  /** Completions at the cursor (the kernel, a connection's catalog), and help on hover. */
  complete?: Completer;
  help?: Helper;
  /** `@cell7` in a comment is a link: a click goes there, a hover shows the cell's first line. */
  cellLinks?: CellLinks;
  readOnly?: boolean;
  /** The right-click menu's Send to the agent: the selected code, or the error under the cursor. */
  sendToAgent?: (what: { text: string; startLine: number; endLine: number; problem: Problem | null }, withQuestion: boolean) => void;
  /** More of the right-click menu's own entries (Lineage): each run with the line it was opened on. */
  actions?: { id: string; label: string; run: (line: number) => void }[];
  /** Parameter info, quick info and the lint as you type (workbenchIntel.ts). */
  intel?: Intel;
  /** The file's path in its project (a code app's src/App.tsx): its model's address, so TypeScript reads
   *  it as .ts or .tsx and resolves its imports. */
  path?: string;
}

/** Beta mode's "Leave a note…" in the editor's own right-click menu. The page (betaNotes.ts, another
 *  bundle) puts its hook on globalThis while beta mode is on; the item shows only then. */
interface NoteHook {
  on: () => boolean;
  open: (target: Element) => void;
}
const noteHook = (): NoteHook | undefined => (globalThis as { sabLeaveNote?: NoteHook }).sabLeaveNote;

function addNoteAction(editor: monaco.editor.IStandaloneCodeEditor, host: HTMLElement): void {
  const shown = editor.createContextKey<boolean>("sabBetaNotes", false);
  // A right button pressed: the menu that follows shows the item only while beta mode is on.
  editor.onMouseDown((e) => {
    if (e.event.rightButton) shown.set(noteHook()?.on() === true);
  });
  editor.addAction({ id: "sab.leaveNote", label: "Leave a note…", contextMenuGroupId: "9_beta", contextMenuOrder: 1, precondition: "sabBetaNotes", run: () => noteHook()?.open(host.querySelector(".monaco-editor") ?? host) });
}

/** The blade list's drag type: its `sab.blade(...)` line is a statement, so it lands on a line of its own. */
const BLADE_DRAG = "application/x-sab-blade";
/** A Data Explorer result's drag (dataExplorer.ts): {sql, python}, the code for each kind of cell. */
const EXPLORER_DRAG = "application/x-sab-explorer";

/** Text dropped on an editor, put in by the app. Monaco's own drop inserts text as a snippet, and the
 *  standalone editor applies a snippet as plain text: `orders` arrived as `orders$0`, a `$` escaped. A
 *  blade's line goes on its own line after the one it is dropped on (that line, when it is empty); other
 *  text where it is dropped. A drag of the app's own (a snippet's form, a cell) is left to whoever takes it. */
function ownDrops(editor: monaco.editor.IStandaloneCodeEditor): void {
  const node = editor.getDomNode();
  if (!node) return;
  node.addEventListener("dragover", (e) => {
    if (!e.dataTransfer?.types.includes("text/plain")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  });
  node.addEventListener("drop", (e) => {
    const text = e.dataTransfer?.getData("text/plain");
    const model = editor.getModel();
    if (!text || !model || editor.getOption(monaco.editor.EditorOption.readOnly)) return;
    e.preventDefault();
    const at = editor.getTargetAtClientPoint(e.clientX, e.clientY)?.position ?? editor.getPosition() ?? new monaco.Position(model.getLineCount(), 1);
    let range = new monaco.Range(at.lineNumber, at.column, at.lineNumber, at.column);
    let put = text;
    // A Data Explorer result (dataExplorer.ts EXPLORER_DRAG): its code as this editor's language writes it.
    const explored = e.dataTransfer?.getData(EXPLORER_DRAG);
    if (explored) {
      try {
        const insert = JSON.parse(explored) as { sql?: string; python?: string };
        put = (model.getLanguageId() === "sql" ? insert.sql : insert.python) ?? insert.python ?? insert.sql ?? text;
      } catch {
        /* the plain text, then */
      }
    }
    if (e.dataTransfer?.types.includes(BLADE_DRAG)) {
      const end = model.getLineMaxColumn(at.lineNumber);
      if (model.getLineContent(at.lineNumber).trim()) {
        range = new monaco.Range(at.lineNumber, end, at.lineNumber, end);
        put = `\n${text}`;
      } else {
        range = new monaco.Range(at.lineNumber, 1, at.lineNumber, end);
      }
    }
    editor.pushUndoStop();
    editor.executeEdits("drop", [{ range, text: put, forceMoveMarkers: true }]);
    editor.pushUndoStop();
    editor.focus();
  });
}

export function createCodeEditor(host: HTMLElement, options: CodeEditorOptions): CodeEditor {
  // A project file's model has its own address (a .tsx file is read as TSX); else Monaco names one.
  const uri = options.path ? monaco.Uri.parse(`file:///${options.path.replace(/^\/+/, "")}`) : null;
  if (uri) monaco.editor.getModel(uri)?.dispose();
  const ownModel = uri ? monaco.editor.createModel(options.value, monacoId(options.language), uri) : null;
  const editor = monaco.editor.create(host, {
    ...(ownModel ? { model: ownModel } : { value: options.value, language: monacoId(options.language) }),
    theme: THEMES[options.theme] ?? "vs",
    automaticLayout: !options.grow,
    minimap: { enabled: false },
    lineNumbers: options.grow ? "off" : "on",
    glyphMargin: false,
    folding: !options.grow,
    lineDecorationsWidth: options.grow ? 6 : 10,
    scrollBeyondLastLine: false,
    renderLineHighlight: options.grow ? "none" : "line",
    overviewRulerLanes: 0,
    hideCursorInOverviewRuler: true,
    scrollbar: options.grow ? { vertical: "hidden", horizontal: "auto", alwaysConsumeMouseWheel: false, handleMouseWheel: false } : {},
    wordWrap: options.language === "markdown" ? "on" : "off",
    fontSize: 13,
    tabSize: 4,
    insertSpaces: true,
    dropIntoEditor: { enabled: false }, // ownDrops: Monaco's own drop leaves a snippet's $0 behind
    // Suggestions as you type, inside strings too (a connection's name in sab.connection("…"), SQL in a string).
    quickSuggestions: { other: true, comments: false, strings: true },
    wordBasedSuggestions: "currentDocument",
    fixedOverflowWidgets: true,
    placeholder: options.placeholder,
    readOnly: options.readOnly ?? false,
    // A read-only cell says nothing when typed in: its head says why.
    readOnlyMessage: { value: "This cell follows the grid: change the table's steps there." },
  });
  const model = editor.getModel();
  if (model && (options.complete || options.help || options.cellLinks || options.intel)) {
    completers.set(model, { complete: options.complete, help: options.help, intel: options.intel });
    for (const language of ["python", "sql", "msdax", "markdown", "html"]) register(language);
  }
  // Cell links: drawn as links, followed on a plain click.
  const linkMarks = editor.createDecorationsCollection([]);
  const drawLinks = (): void => {
    const m = editor.getModel();
    if (!m || !cellLinks.has(m)) return;
    const marks: monaco.editor.IModelDeltaDecoration[] = [];
    for (let line = 1; line <= m.getLineCount(); line++) {
      const text = m.getLineContent(line);
      if (!text.includes("@cell")) continue;
      for (const link of linksOn(text, m.getLanguageId())) marks.push({ range: new monaco.Range(line, link.start, line, link.end), options: { inlineClassName: "wb-cell-link" } });
    }
    linkMarks.set(marks);
  };
  if (model && options.cellLinks) {
    cellLinks.set(model, options.cellLinks);
    drawLinks();
    editor.onDidChangeModelContent(drawLinks);
    editor.onDidChangeModelLanguage(drawLinks);
    editor.onMouseUp((e) => {
      const m = editor.getModel();
      const at = e.target.position;
      if (!m || !at || e.event.leftButton === false || e.event.ctrlKey || e.event.shiftKey || e.event.altKey) return;
      if (e.target.type !== monaco.editor.MouseTargetType.CONTENT_TEXT || !editor.getSelection()?.isEmpty()) return;
      const link = linkAt(m, at);
      if (link) options.cellLinks!.go(link.number);
    });
  }
  const notes = editor.createDecorationsCollection([]);
  const stripes = editor.createDecorationsCollection([]);
  const zones = new Map<string, { zoneId: string; zone: monaco.editor.IViewZone; widget: monaco.editor.IOverlayWidget; element: HTMLElement }>();
  const hiddenBy = { name: "sab-html-cells" };
  const keys = options.keys ?? {};
  // The run keys come first, even with the suggestion list open (it would take Ctrl+Enter for itself):
  // the list closes and the code runs.
  editor.onKeyDown((e) => {
    const run =
      e.keyCode === monaco.KeyCode.Enter && e.shiftKey && !e.ctrlKey && !e.metaKey ? keys.shiftEnter
      : e.keyCode === monaco.KeyCode.Enter && (e.ctrlKey || e.metaKey) && !e.shiftKey ? keys.ctrlEnter
      : e.keyCode === monaco.KeyCode.F9 ? keys.ctrlEnter
      : undefined;
    if (!run) return;
    e.preventDefault();
    e.stopPropagation();
    editor.trigger("keyboard", "hideSuggestWidget", null);
    run();
  });
  // Monaco's addCommand goes into one keybinding service shared by every editor on the page: without a
  // key of this editor's own in the condition, the console's Enter ran in a notebook cell (the newlines
  // typed there vanished), and the last cell's Escape answered for every cell.
  const own = `sabEditor${++editorCount}`;
  editor.createContextKey(own, true);
  if (keys.f5) editor.addCommand(monaco.KeyCode.F5, keys.f5, own);
  if (keys.f1) editor.addCommand(monaco.KeyCode.F1, keys.f1, own);
  if (keys.enter) editor.addCommand(monaco.KeyCode.Enter, keys.enter, `${own} && !suggestWidgetVisible`);
  if (keys.up) editor.addCommand(monaco.KeyCode.UpArrow, () => { if (!keys.up!()) editor.trigger("keyboard", "cursorUp", null); }, `${own} && !suggestWidgetVisible`);
  if (keys.down) editor.addCommand(monaco.KeyCode.DownArrow, () => { if (!keys.down!()) editor.trigger("keyboard", "cursorDown", null); }, `${own} && !suggestWidgetVisible`);
  if (keys.escape) editor.addCommand(monaco.KeyCode.Escape, keys.escape, `${own} && !suggestWidgetVisible`);

  // A failed run's marks, gone as soon as the code is edited (they describe the code that ran).
  const lens = editor.createDecorationsCollection([]);
  editor.onDidChangeModelContent(() => {
    const model = editor.getModel();
    if (model && problems.get(model)?.length) {
      problems.set(model, []);
      monaco.editor.setModelMarkers(model, PROBLEMS, []);
      lens.clear();
    }
  });

  // The lint, a moment after typing stops (never in the way of typing): its marks replace the last ones.
  let lintTimer = 0;
  let lintAsked = 0;
  const lintNow = async (): Promise<void> => {
    const m = editor.getModel();
    const ask = options.intel?.lint;
    if (!m || !ask) return;
    const version = m.getVersionId();
    const mine = ++lintAsked;
    const found = await ask(m.getValue());
    if (found === null || mine !== lintAsked || m.isDisposed() || m.getVersionId() !== version) return;
    linted.set(m, found);
    monaco.editor.setModelMarkers(
      m,
      LINT,
      found.map((p) => ({
        severity: p.severity === "error" ? monaco.MarkerSeverity.Error : p.severity === "warning" ? monaco.MarkerSeverity.Warning : p.severity === "info" ? monaco.MarkerSeverity.Info : monaco.MarkerSeverity.Hint,
        message: p.message.replace(/`/g, ""),
        code: p.code,
        source: p.source,
        tags: p.unnecessary ? [monaco.MarkerTag.Unnecessary] : [],
        startLineNumber: p.line,
        startColumn: p.col,
        endLineNumber: p.end_line,
        endColumn: p.line === p.end_line ? Math.max(p.end_col, p.col + 1) : p.end_col,
      })),
    );
    options.intel?.onLint?.(found);
  };
  // The documentation panel beside the member list from the start (as Visual Studio shows it): opened
  // once for the page; after that Monaco keeps the user's own choice (Ctrl+Space shows or hides it).
  if (options.intel) {
    const once = editor.onDidFocusEditorText(() => {
      once.dispose();
      try {
        const controller = editor.getContribution("editor.contrib.suggestController") as unknown as { widget: { value: SuggestWidget } };
        const widget = controller.widget.value;
        // Shown each time the list opens until it once could be (an item with no words has no panel).
        const open = (): void => {
          if (detailsOpened || widget._isDetailsVisible()) return;
          widget.toggleDetails();
          detailsOpened = widget._isDetailsVisible();
        };
        widget.onDidShow(open);
        widget.onDidFocus?.(open);
      } catch {
        /* Monaco's own parts moved: the panel opens with Ctrl+Space */
      }
    });
  }
  if (options.intel?.lint) {
    editor.onDidChangeModelContent(() => {
      window.clearTimeout(lintTimer);
      lintTimer = window.setTimeout(() => void lintNow(), LINT_MS);
    });
    lintTimer = window.setTimeout(() => void lintNow(), LINT_MS);
  }

  if (options.sendToAgent) {
    const send = (withQuestion: boolean): void => {
      const model = editor.getModel();
      const chosen = editor.getSelection();
      if (!model || !chosen) return;
      const line = chosen.startLineNumber;
      const problem = chosen.isEmpty() ? (problems.get(model) ?? []).find((p) => p.severity === "error" && line >= p.line && line <= Math.max(p.line, p.endLine)) ?? null : null;
      const range = chosen.isEmpty()
        ? new monaco.Range(problem?.line ?? line, 1, problem ? Math.max(problem.line, problem.endLine) : line, model.getLineMaxColumn(problem ? Math.max(problem.line, problem.endLine) : line))
        : chosen;
      const text = model.getValueInRange(range);
      if (!problem && !text.trim()) return; // a blank line, nothing selected: nothing to send
      options.sendToAgent!({ text, startLine: range.startLineNumber, endLine: range.endLineNumber, problem }, withQuestion);
    };
    editor.addAction({ id: "sab.sendToAgent", label: "Send to the agent", contextMenuGroupId: "0_agent", contextMenuOrder: 1, run: () => send(false) });
    editor.addAction({ id: "sab.sendToAgentAsk", label: "Send to the agent with a question…", contextMenuGroupId: "0_agent", contextMenuOrder: 2, run: () => send(true) });
  }

  for (const action of options.actions ?? []) {
    editor.addAction({ id: action.id, label: action.label, contextMenuGroupId: "1_cell", contextMenuOrder: 1, run: () => action.run(editor.getPosition()?.lineNumber ?? 1) });
  }

  addNoteAction(editor, host);
  ownDrops(editor);

  const fit = (): void => {
    if (!options.grow) return;
    const height = Math.max(editor.getContentHeight(), 22);
    host.style.height = `${height}px`;
    editor.layout({ width: host.clientWidth, height });
  };
  if (options.grow) {
    editor.onDidContentSizeChange(fit);
    new ResizeObserver(() => editor.layout({ width: host.clientWidth, height: host.clientHeight })).observe(host);
    fit();
  }
  return {
    value: () => editor.getValue(),
    setValue: (text) => editor.setValue(text),
    selection: () => {
      const model = editor.getModel();
      const chosen = editor.getSelection();
      if (!model || !chosen) return "";
      if (!chosen.isEmpty()) return model.getValueInRange(chosen);
      return model.getLineContent(chosen.startLineNumber);
    },
    selected: () => {
      const model = editor.getModel();
      const chosen = editor.getSelection();
      if (!model || !chosen || chosen.isEmpty()) return null;
      // A selection ending at the start of a line (dragged down past a line's end) leaves that line out.
      const endLine = chosen.endColumn === 1 && chosen.endLineNumber > chosen.startLineNumber ? chosen.endLineNumber - 1 : chosen.endLineNumber;
      const wholeLines = model.getValueInRange(new monaco.Range(chosen.startLineNumber, 1, endLine, model.getLineMaxColumn(endLine)));
      return { text: model.getValueInRange(chosen), startLine: chosen.startLineNumber, endLine, wholeLines };
    },
    cursorLine: () => editor.getPosition()?.lineNumber ?? 1,
    lineCount: () => editor.getModel()?.getLineCount() ?? 1,
    lines: (start, end) => {
      const model = editor.getModel();
      if (!model) return "";
      const last = Math.min(end, model.getLineCount());
      return model.getValueInRange(new monaco.Range(start, 1, last, model.getLineMaxColumn(last)));
    },
    moveTo: (line) => {
      const last = editor.getModel()?.getLineCount() ?? 1;
      const at = Math.max(1, Math.min(line, last));
      editor.setPosition({ lineNumber: at, column: 1 });
      editor.revealLineInCenterIfOutsideViewport(at);
    },
    replaceText: (text) => {
      const m = editor.getModel();
      if (!m || m.getValue() === text) return false;
      const before = m.getLinesContent();
      const after = text.split("\n");
      const hunks = lineHunks(before, after);
      if (!hunks.length) return false;
      // Where each old line lands: a line in a changed piece goes to that piece's new place.
      const mapLine = (line: number): number => {
        let shift = 0;
        for (const hunk of hunks) {
          if (line < hunk.start) break;
          if (line < hunk.start + hunk.removed) return Math.max(1, Math.min(hunk.start + shift + Math.min(line - hunk.start, Math.max(0, hunk.lines.length - 1)), after.length));
          shift += hunk.lines.length - hunk.removed;
        }
        return Math.max(1, Math.min(line + shift, after.length));
      };
      const at = editor.getPosition();
      const topBefore = at ? editor.getTopForLineNumber(at.lineNumber) - editor.getScrollTop() : 0;
      const selections = (editor.getSelections() ?? []).map((sel) => new monaco.Selection(mapLine(sel.selectionStartLineNumber), sel.selectionStartColumn, mapLine(sel.positionLineNumber), sel.positionColumn));
      const last = before.length;
      const edits = hunks.map((hunk) => {
        // Whole lines: from the start of the first changed line (or the end of the line before, at the
        // end of the text) so that no stray newline is left behind.
        if (hunk.start > last) return { range: new monaco.Range(last, m.getLineMaxColumn(last), last, m.getLineMaxColumn(last)), text: "\n" + hunk.lines.join("\n") };
        const end = hunk.start + hunk.removed;
        if (end > last) {
          const from = hunk.start > 1 && !hunk.lines.length ? new monaco.Position(hunk.start - 1, m.getLineMaxColumn(hunk.start - 1)) : new monaco.Position(hunk.start, 1);
          return { range: new monaco.Range(from.lineNumber, from.column, last, m.getLineMaxColumn(last)), text: hunk.lines.join("\n") };
        }
        return { range: new monaco.Range(hunk.start, 1, end, 1), text: hunk.lines.length ? hunk.lines.join("\n") + "\n" : "" };
      });
      const wasReadOnly = editor.getOption(monaco.editor.EditorOption.readOnly);
      if (wasReadOnly) editor.updateOptions({ readOnly: false });
      editor.executeEdits("sab-tables", edits, selections.length ? selections : undefined);
      if (wasReadOnly) editor.updateOptions({ readOnly: true });
      // The line the cursor is on stays where it was on screen (a script scrolls by the lines added above).
      const now = editor.getPosition();
      if (at && now && !options.grow) editor.setScrollTop(editor.getTopForLineNumber(now.lineNumber) - topBefore);
      return true;
    },
    setReadOnly: (readOnly) => {
      if (editor.getOption(monaco.editor.EditorOption.readOnly) !== readOnly) editor.updateOptions({ readOnly });
    },
    setOutline: (outline) => {
      const m = editor.getModel();
      if (!m) return;
      if (outline) outlines.set(m, outline);
      else outlines.delete(m);
      foldsChanged.fire({ provideFoldingRanges: (model) => foldingRanges(model) });
    },
    fold: (lines) => {
      if (lines.length) void editor.getAction("editor.fold")?.run({ selectionLines: lines.map((l) => l - 1), levels: 1 });
    },
    unfold: (lines) => {
      if (lines.length) void editor.getAction("editor.unfold")?.run({ selectionLines: lines.map((l) => l - 1), levels: 1 });
    },
    setLineNotes: (list) => {
      const m = editor.getModel();
      if (!m) return;
      notes.set(
        list
          .filter((n) => n.line >= 1 && n.line <= m.getLineCount())
          .flatMap((n) => {
            const end = m.getLineMaxColumn(n.line);
            const marks: monaco.editor.IModelDeltaDecoration[] = [];
            if (n.marker) marks.push({ range: new monaco.Range(n.line, 1, n.line, 1), options: { isWholeLine: true, className: n.tone === "stale" ? "wb-marker-line stale" : "wb-marker-line" } });
            if (n.text) marks.push({ range: new monaco.Range(n.line, Math.max(1, end - 1), n.line, end), options: { showIfCollapsed: true, after: { content: `   ${n.text}`, inlineClassName: n.tone === "stale" ? "wb-line-note stale" : "wb-line-note" } } });
            return marks;
          }),
      );
    },
    setStripes: (list) => {
      const m = editor.getModel();
      if (!m) return;
      stripes.set(
        list
          .filter((s) => s.colours.length && s.start >= 1 && s.start <= m.getLineCount())
          .map((s) => ({
            range: new monaco.Range(s.start, 1, Math.min(s.end, m.getLineCount()), 1),
            options: { isWholeLine: true, linesDecorationsClassName: stripeClass(s.colours) },
          })),
      );
    },
    insertNewline: () => editor.trigger("keyboard", "type", { text: "\n" }),
    insertAt: (text, x, y) => {
      const model = editor.getModel();
      if (!model) return;
      // Where it was dropped (a point on the editor), else the cursor (or what is selected).
      const dropped = x !== undefined && y !== undefined ? editor.getTargetAtClientPoint(x, y)?.position : null;
      const range = dropped ? new monaco.Range(dropped.lineNumber, dropped.column, dropped.lineNumber, dropped.column) : (editor.getSelection() ?? new monaco.Range(1, 1, 1, 1));
      editor.pushUndoStop();
      editor.executeEdits("snippet", [{ range, text, forceMoveMarkers: true }]);
      editor.pushUndoStop();
    },
    atEnd: () => {
      const model = editor.getModel();
      const at = editor.getPosition();
      if (!model || !at) return true;
      const last = model.getLineCount();
      return at.lineNumber === last && at.column === model.getLineMaxColumn(last);
    },
    cursorOffset: () => {
      const model = editor.getModel();
      const at = editor.getPosition();
      return model && at ? model.getOffsetAt(at) : 0;
    },
    onCursor: (listener) => void editor.onDidChangeCursorPosition((e) => listener(e.position.lineNumber, e.position.column)),
    onFocus: (listener) => void editor.onDidFocusEditorText(listener),
    onBlur: (listener) => void editor.onDidBlurEditorText(listener),
    hasFocus: () => editor.hasTextFocus(),
    setProblems: (list) => {
      const model = editor.getModel();
      if (!model) return;
      problems.set(model, list);
      monaco.editor.setModelMarkers(
        model,
        PROBLEMS,
        list.map((p) => {
          const r = rangeOf(model, p);
          return { severity: p.severity === "error" ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Info, message: p.message, source: "Python", startLineNumber: r.startLineNumber, startColumn: r.startColumn, endLineNumber: r.endLineNumber, endColumn: r.endColumn };
        }),
      );
      // The message at the end of the failing line (Error Lens), and the line itself marked.
      lens.set(
        list.flatMap((p) => {
          const line = Math.min(Math.max(p.endLine, p.line), model.getLineCount());
          const end = model.getLineMaxColumn(line);
          return [
            { range: new monaco.Range(Math.min(p.line, model.getLineCount()), 1, line, 1), options: { isWholeLine: true, className: p.severity === "error" ? "wb-problem-line" : "wb-call-line" } },
            {
              // On the line's last character (an empty range shows no text after it).
              range: new monaco.Range(line, Math.max(1, end - 1), line, end),
              options: { showIfCollapsed: true, after: { content: `   ${p.message.split("\n")[0]!.slice(0, 160)}`, inlineClassName: p.severity === "error" ? "wb-problem-lens" : "wb-call-lens" } },
            },
          ];
        }),
      );
    },
    applyFix: (fix, near) => {
      const model = editor.getModel();
      if (!model) return false;
      const line = Math.min(Math.max(1, near), model.getLineCount());
      const edit = fixEdit(model, new monaco.Range(line, 1, line, model.getLineMaxColumn(line)), fix) ?? (fix.kind === "replace" ? fixEdit(model, model.getFullModelRange(), fix) : null);
      if (!edit) return false;
      editor.executeEdits("sab-fix", [{ range: monaco.Range.lift(edit.range), text: edit.text }]);
      return true;
    },
    reveal: (line, column = 1) => {
      editor.setPosition({ lineNumber: line, column });
      editor.revealLineInCenterIfOutsideViewport(line);
      editor.focus();
    },
    setLanguage: (language) => {
      const model = editor.getModel();
      if (model) monaco.editor.setModelLanguage(model, monacoId(language));
      editor.updateOptions({ wordWrap: language === "markdown" ? "on" : "off" });
    },
    setZones: (list) => {
      const wanted = new Map(list.map((z) => [z.id, z]));
      editor.changeViewZones((accessor) => {
        for (const [id, held] of zones) {
          if (wanted.has(id) && wanted.get(id)!.element === held.element) continue;
          accessor.removeZone(held.zoneId);
          editor.removeOverlayWidget(held.widget);
          zones.delete(id);
        }
        for (const z of list) {
          const held = zones.get(z.id);
          if (held) {
            if (held.zone.afterLineNumber !== z.afterLine || held.zone.heightInPx !== z.height) {
              held.zone.afterLineNumber = z.afterLine;
              held.zone.heightInPx = z.height;
              accessor.layoutZone(held.zoneId);
            }
            continue;
          }
          // The zone makes the room; the pane itself is laid over it, so it takes the pointer.
          const place = (): void => {
            const info = editor.getLayoutInfo();
            z.element.style.left = `${info.contentLeft}px`;
            z.element.style.width = `${Math.max(120, info.contentWidth - info.verticalScrollbarWidth - 12)}px`;
          };
          const zone: monaco.editor.IViewZone = {
            afterLineNumber: z.afterLine,
            heightInPx: z.height,
            domNode: document.createElement("div"),
            showInHiddenAreas: true,
            onDomNodeTop: (top) => {
              z.element.style.top = `${top}px`;
              place();
            },
          };
          z.element.style.position = "absolute";
          const widget: monaco.editor.IOverlayWidget = { getId: () => `sab.zone.${own}.${z.id}`, getDomNode: () => z.element, getPosition: () => null };
          editor.addOverlayWidget(widget);
          zones.set(z.id, { zoneId: accessor.addZone(zone), zone, widget, element: z.element });
        }
      });
    },
    setHidden: (ranges) => {
      // Monaco's own way of not showing lines (folding uses it too, under its own name).
      (editor as unknown as { setHiddenAreas: (ranges: monaco.IRange[], source: unknown) => void }).setHiddenAreas(
        ranges.filter(([from, to]) => to >= from).map(([from, to]) => new monaco.Range(from, 1, to, 1)),
        hiddenBy,
      );
    },
    focus: () => editor.focus(),
    setTheme: (theme) => monaco.editor.setTheme(THEMES[theme] ?? "vs"),
    onChange: (listener) => void editor.onDidChangeModelContent((e) => listener({ undo: e.isUndoing || e.isRedoing })),
    layout: () => (options.grow ? fit() : editor.layout()),
    lint: () => void lintNow(),
    lintProblems: () => {
      const m = editor.getModel();
      return (m && linted.get(m)) || [];
    },
    dispose: () => {
      window.clearTimeout(lintTimer);
      options.intel?.onLint?.([]);
      editor.getModel()?.dispose();
      editor.dispose();
    },
  };
}

// ===== the "+" tab's SQL editor (queryTab.ts) =====
// The same Monaco as the Workbench's, so the page ships and loads one copy. Column names (and `grid`
// plus open dataset names) autocomplete; Ctrl+Enter runs.

// Each editor's own names: the SQL box offers one grid's columns, a query tray every open table's.
const namesOf = new WeakMap<monaco.editor.ITextModel, { columns: string[]; tables: string[] }>();
let sqlNamesRegistered = false;

export interface SqlEditor {
  value: () => string;
  setValue: (text: string) => void;
  focus: () => void;
  setTheme: (theme: string) => void;
  setNames: (columns: string[], tables: string[]) => void;
  /** Free the editor and its text model (a "+" tab's tray when its tab closes). */
  dispose: () => void;
}

export function createSqlEditor(host: HTMLElement, initial: string, onRun: () => void, theme: string): SqlEditor {
  if (!sqlNamesRegistered) {
    sqlNamesRegistered = true;
    monaco.languages.registerCompletionItemProvider("sql", {
      provideCompletionItems: (model, position) => {
        const names = namesOf.get(model);
        if (!names) return { suggestions: [] }; // a Workbench cell's: its own completer answers
        const word = model.getWordUntilPosition(position);
        const range = new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn);
        const quote = (n: string): string => (/^[a-z_][a-z0-9_]*$/.test(n) ? n : `"${n.replace(/"/g, '""')}"`);
        return {
          suggestions: [
            ...names.columns.map((n) => ({ label: n, kind: monaco.languages.CompletionItemKind.Field, insertText: quote(n), range, detail: "column" })),
            ...names.tables.map((n) => ({ label: n, kind: monaco.languages.CompletionItemKind.Struct, insertText: quote(n), range, detail: n === "grid" ? "this grid's view" : "dataset" })),
          ],
        };
      },
    });
  }
  const editor = monaco.editor.create(host, {
    value: initial,
    language: "sql",
    theme: THEMES[theme] ?? "vs",
    minimap: { enabled: false },
    automaticLayout: true,
    fontSize: 13,
    scrollBeyondLastLine: false,
    wordWrap: "on",
    ariaLabel: "SQL query",
    dropIntoEditor: { enabled: false },
  });
  ownDrops(editor);
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, onRun);
  addNoteAction(editor, host);
  return {
    value: () => editor.getValue(),
    setValue: (text) => editor.setValue(text),
    focus: () => editor.focus(),
    setTheme: (t) => monaco.editor.setTheme(THEMES[t] ?? "vs"),
    setNames: (columns, tables) => {
      const model = editor.getModel();
      if (model) namesOf.set(model, { columns, tables });
    },
    // The editor made its model from `value`, so disposing the editor disposes the model too.
    dispose: () => editor.dispose(),
  };
}
