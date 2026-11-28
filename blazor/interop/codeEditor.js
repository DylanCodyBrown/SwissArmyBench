// codeEditor.js: Monaco (blazor/package.json's pinned version), wrapped for the <CodeEditor> component.
//
// One editor per call to create(). Its text goes to C# a moment after typing stops (Changed); the keys a page acts
// on (Shift+Enter, Ctrl+Enter, Ctrl+S...) go to C# by name (Key). The editors' intelligence is the server's, the
// same routes the classic editors ask (POST /workbench/intel/complete, signature, hover and lint): each request
// asks C# first for the editor's context (the kernel, the document, a notebook's other cells) and then goes
// straight to the server, so the member list stays quick.
import * as monaco from "monaco-editor";

// TypeScript and JavaScript have Monaco's own language service in a worker of their own (a code app's files, a
// data notebook's TypeScript cells); every other language the editor's worker.
self.MonacoEnvironment = {
  getWorker: (_id, label) =>
    new Worker(new URL(label === "typescript" || label === "javascript" ? "./ts.worker.js" : "./editor.worker.js", import.meta.url), { type: "module" }),
};

// ===== TypeScript: a code app's files and a data notebook's cells (the classic lazy/codeEditor.ts) =====

let typescriptReady = false;
let notebookReady = false;
// 2307/2792: a package not read here; 7016: its types; 2875: JSX's runtime package; 17004: JSX flag; 7026: JSX's
// element types (React's own types are in node_modules). A notebook's cells: 1375/1378 a top-level await in a
// cell (the kernel runs it), 2451 a name a cell declares again (run again, it replaces the first).
const IGNORED = [2307, 2792, 7016, 2875, 17004, 7026, 1375, 1378, 2451];
const projectLibs = new Map();

/** The language service set for a code app (React's JSX, modern modules), and the project's own files known to it
 *  (its generated models and services, its other modules), so imports between them resolve. */
export function typescriptProject(files) {
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
    ts.typescriptDefaults.setDiagnosticsOptions({ noSemanticValidation: false, noSyntaxValidation: false, diagnosticCodesToIgnore: IGNORED });
    ts.typescriptDefaults.setEagerModelSync(true);
  }
  for (const file of files ?? []) {
    const uri = `file:///${file.path.replace(/^\/+/, "")}`;
    projectLibs.get(uri)?.dispose();
    projectLibs.set(uri, ts.typescriptDefaults.addExtraLib(file.text, uri));
  }
}

/** A notebook's TypeScript cells: the kernel's `sab` known to the language service (once a page). */
export function typescriptNotebook(declarations) {
  if (notebookReady) return;
  notebookReady = true;
  typescriptProject([]);
  monaco.typescript.typescriptDefaults.addExtraLib(declarations, "file:///sab-notebook.d.ts");
}

// Monaco's own CSS, bundled beside this file: loaded once, by the first editor.
const css = new URL("./codeEditor.css", import.meta.url).href;
if (!document.querySelector(`link[href="${css}"]`)) {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = css;
  document.head.append(link);
}

// JSON's and HTML's language services would need workers of their own, which this page does not ship: they are
// switched off (the classic codeEditor.ts does the same); their colours stay. The server checks a structure's text.
const OFF = {
  completionItems: false,
  hovers: false,
  documentSymbols: false,
  colors: false,
  foldingRanges: false,
  diagnostics: false,
  selectionRanges: false,
  documentFormattingEdits: false,
  documentRangeFormattingEdits: false,
};
monaco.json.jsonDefaults.setModeConfiguration({ ...OFF, tokens: true });
monaco.html.htmlDefaults.setModeConfiguration({ ...OFF, links: false, documentHighlights: false, rename: false });

const THEMES = { light: "vs", dark: "vs-dark", "hc-light": "hc-light", "hc-dark": "hc-black" };
// Monaco's own names for ours: Power Query (M) is its "pq" (monaco-editor's languages/definitions/powerquery).
const LANGUAGES = { dax: "msdax", toml: "ini", tsx: "typescript", powerquery: "pq" };
const POWER_QUERY = "pq";
const TEXT_SETTLES_MS = 150;
const LINT_SETTLES_MS = 500;
const INTEL_LANGUAGES = ["python", "sql", "msdax"];

// Review comments (the owner, 2026-11-27): each editor's count of comments waiting, so the window asks before it
// closes with comments that were never sent (they live in this page's memory only).
const reviewCounts = new Map();
window.addEventListener("beforeunload", (event) => {
  let waiting = 0;
  for (const count of reviewCounts.values()) waiting += count;
  if (waiting === 0) return;
  event.preventDefault();
  event.returnValue = "";
});
// A comment's words as Monaco's hover shows them: plain text, never Markdown of the user's.
const plainHover = (text) => text.replace(/[\\`*_{}\[\]()#+\-.!|<>~]/g, "\\$&").replace(/\n/g, "  \n");
const REVIEW_CODE_MAX = 4000;

// Each editor's model to its C# side (the context a request carries) and its last lint's problems.
const owners = new WeakMap();
let registered = false;

const KINDS = {
  function: monaco.languages.CompletionItemKind.Function,
  method: monaco.languages.CompletionItemKind.Method,
  class: monaco.languages.CompletionItemKind.Class,
  module: monaco.languages.CompletionItemKind.Module,
  keyword: monaco.languages.CompletionItemKind.Keyword,
  property: monaco.languages.CompletionItemKind.Property,
  path: monaco.languages.CompletionItemKind.File,
  table: monaco.languages.CompletionItemKind.Struct,
  struct: monaco.languages.CompletionItemKind.Struct,
  column: monaco.languages.CompletionItemKind.Field,
  schema: monaco.languages.CompletionItemKind.Folder,
  connection: monaco.languages.CompletionItemKind.Reference,
};

/** The server's answer to one intelligence request, with the editor's context; null when it cannot say. */
async function ask(kind, model, extra) {
  const owner = owners.get(model);
  if (!owner || !owner.intel) return null;
  let context = {};
  try {
    context = (await owner.dotnet.invokeMethodAsync("IntelContext")) ?? {};
  } catch {
    return null; // the component went away meanwhile
  }
  const body = { ...context, text: model.getValue(), ...extra };
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const answer = await fetch(`/workbench/intel/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!answer.ok) return null;
      const found = await answer.json();
      // Late (Jedi's first look at a library): it goes on in the server, and asked once more it is quick.
      if (found && found.late && attempt === 0) continue;
      return found;
    } catch {
      return null;
    }
  }
  return null;
}

function registerIntel() {
  if (registered) return;
  registered = true;
  for (const language of INTEL_LANGUAGES) {
    monaco.languages.registerCompletionItemProvider(language, {
      triggerCharacters: language === "msdax" ? [".", "'", "["] : [".", '"', "'"],
      provideCompletionItems: async (model, position) => {
        const offset = model.getOffsetAt(position);
        const found = await ask("complete", model, { offset });
        if (!found || !Array.isArray(found.items)) return { suggestions: [] };
        const range = Number.isInteger(found.start)
          ? monaco.Range.fromPositions(model.getPositionAt(found.start), model.getPositionAt(found.end ?? offset))
          : undefined;
        return {
          incomplete: true,
          suggestions: found.items.map((item, at) => ({
            label: item.label,
            insertText: item.snippet ?? item.label,
            insertTextRules: item.snippet ? monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet : undefined,
            kind: KINDS[item.kind] ?? monaco.languages.CompletionItemKind.Variable,
            detail: item.detail ?? item.kind ?? "",
            documentation: item.documentation ? { value: item.documentation } : undefined,
            sortText: item.sort ?? String(at).padStart(5, "0"),
            range,
          })),
        };
      },
    });
    monaco.languages.registerHoverProvider(language, {
      provideHover: async (model, position) => {
        const word = model.getWordAtPosition(position);
        if (!word) return null;
        const found = await ask("hover", model, { offset: model.getOffsetAt(position) });
        if (!found || !found.hover) return null;
        return {
          range: new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn),
          contents: [{ value: found.hover, supportHtml: false }],
        };
      },
    });
  }
  monaco.languages.registerSignatureHelpProvider("python", {
    signatureHelpTriggerCharacters: ["(", ","],
    signatureHelpRetriggerCharacters: [",", ")"],
    provideSignatureHelp: async (model, position) => {
      const found = await ask("signature", model, { offset: model.getOffsetAt(position) });
      if (!found || !Array.isArray(found.signatures) || found.signatures.length === 0) return null;
      const signatures = found.signatures.map((sig) => ({
        label: sig.label,
        documentation: { value: sig.summary ?? "" },
        parameters: (sig.params ?? []).map((p) => ({ label: p.span ?? p.label, documentation: { value: p.words ?? "" } })),
        activeParameter: sig.active ?? undefined,
      }));
      return { value: { signatures, activeSignature: 0, activeParameter: found.signatures[0].active ?? 0 }, dispose: () => {} };
    },
  });
}

// Ghost text (the classic inlineCompletion.ts and codeEditor.ts): from the provider the open project's mode declares
// for the editor's language (GitHub Copilot's routes, when that extension is on); the document is asked of C# (a
// script's text, or a notebook's code cells and the one being edited). Monaco's cancellation aborts the request and
// posts the provider's cancel; an item shown, accepted or partly accepted is told to its event route.
const inlineRegistered = new Set();
let inlineAsked = 0;

async function post(route, body, signal) {
  const answer = await fetch(route, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  return answer.ok ? answer.json() : null;
}

function registerInline(language) {
  if (inlineRegistered.has(language)) return;
  inlineRegistered.add(language);
  monaco.languages.registerInlineCompletionsProvider(language, {
    debounceDelayMs: 250,
    provideInlineCompletions: async (model, position, _context, token) => {
      const owner = owners.get(model);
      const provider = owner?.inline?.find((p) => p.languages.includes(language));
      if (!provider || token.isCancellationRequested) return { items: [] };
      let document = null;
      try {
        document = await owner.dotnet.invokeMethodAsync("InlineDocument");
      } catch {
        return { items: [] };
      }
      if (!document) return { items: [] };
      const abort = new AbortController();
      const request = `b${++inlineAsked}`;
      const listening = token.onCancellationRequested(() => {
        abort.abort();
        if (provider.cancel) post(provider.cancel, { request }).catch(() => {});
      });
      try {
        const options = model.getOptions();
        const body = { request, document, position: { line: position.lineNumber - 1, character: position.column - 1 }, tab_size: options.tabSize, insert_spaces: options.insertSpaces };
        const found = (await post(provider.complete, body, abort.signal).catch(() => null))?.items ?? [];
        const items = found.map((item) => ({
          insertText: item.text,
          range: item.range
            ? new monaco.Range(item.range.start.line + 1, item.range.start.character + 1, item.range.end.line + 1, item.range.end.character + 1)
            : new monaco.Range(position.lineNumber, position.column, position.lineNumber, position.column),
          sabId: item.id,
          sabEvent: provider.event,
        }));
        return { items, enableForwardStability: true };
      } finally {
        listening.dispose();
      }
    },
    handleItemDidShow: (_c, item) => item.sabEvent && post(item.sabEvent, { id: item.sabId, kind: "shown" }).catch(() => {}),
    handlePartialAccept: (_c, item, accepted) => item.sabEvent && post(item.sabEvent, { id: item.sabId, kind: "partial", length: accepted }).catch(() => {}),
    handleEndOfLifetime: (_c, item, reason) => {
      if (reason.kind === monaco.languages.InlineCompletionEndOfLifeReasonKind.Accepted && item.sabEvent) post(item.sabEvent, { id: item.sabId, kind: "accepted" }).catch(() => {});
    },
    disposeInlineCompletions: () => undefined,
  });
}

const SEVERITY = {
  error: monaco.MarkerSeverity.Error,
  warning: monaco.MarkerSeverity.Warning,
  info: monaco.MarkerSeverity.Info,
  hint: monaco.MarkerSeverity.Hint,
};

/** A Power Query file's problems before a run (POST /scripts/pq/problems: what cannot run, each with its line and
 *  column; nothing is read), in the lint's shape. A name the problem is about is underlined whole. */
async function powerQueryProblems(model) {
  const owner = owners.get(model);
  if (!owner || !owner.intel) return null;
  let context = {};
  try {
    context = (await owner.dotnet.invokeMethodAsync("IntelContext")) ?? {};
  } catch {
    return null;
  }
  try {
    const answer = await fetch("/scripts/pq/problems", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: model.getValue(), path: context.path ?? undefined }),
    });
    if (!answer.ok) return null;
    const found = await answer.json();
    const problems = (found.problems ?? []).map((p) => {
      const line = Math.min(Math.max(1, p.line ?? 1), model.getLineCount());
      const col = Math.max(1, p.column ?? 1);
      const word = model.getWordAtPosition({ lineNumber: line, column: col });
      const named = p.name && model.getLineContent(line).startsWith(p.name, col - 1) ? col + p.name.length : 0;
      const end = named || word?.endColumn || model.getLineMaxColumn(line);
      return { line, col, end_col: Math.max(end, col + 1), message: p.message, source: "Power Query", severity: "error" };
    });
    return { problems };
  } catch {
    return null;
  }
}

async function lint(model, language) {
  const found = language === POWER_QUERY ? await powerQueryProblems(model) : await ask("lint", model, { language: language === "msdax" ? "dax" : language });
  if (!found || !Array.isArray(found.problems) || model.isDisposed()) return;
  const markers = found.problems.map((p) => ({
    startLineNumber: p.line,
    startColumn: p.col,
    endLineNumber: p.end_line ?? p.line,
    endColumn: p.end_col ?? p.col + 1,
    message: p.message,
    source: p.source,
    code: p.code,
    severity: SEVERITY[p.severity] ?? monaco.MarkerSeverity.Warning,
    tags: p.unnecessary ? [monaco.MarkerTag.Unnecessary] : [],
  }));
  monaco.editor.setModelMarkers(model, "sab-lint", markers);
  const owner = owners.get(model);
  if (owner) owner.ruffMissing = !!(found.ruff && !found.ruff.used && found.ruff.missing);
  owner?.dotnet.invokeMethodAsync("Linted", markers.filter((m) => m.severity >= monaco.MarkerSeverity.Warning).length).catch(() => {});
}

/** Text coloured as `language` (the Collaboration panel's code blocks): Monaco's HTML, its text escaped. */
export function colorize(text, language, theme) {
  if (theme) monaco.editor.setTheme(THEMES[theme] ?? "vs");
  return monaco.editor.colorize(text, LANGUAGES[language] ?? language, { tabSize: 4 });
}

function editorIn(host) {
  return monaco.editor.getEditors().find((editor) => host.contains(editor.getContainerDomNode())) ?? null;
}

/**
 * The editor inside `host` and a preview beside it (interop/documents.js): `told(part)` as the editor scrolls
 * (0 its top, 1 its end), `to(part)` scrolls it there.
 */
export function scrollLink(host, told) {
  const editor = editorIn(host);
  if (!editor) return null;
  const most = () => Math.max(0, editor.getScrollHeight() - editor.getLayoutInfo().height);
  const heard = editor.onDidScrollChange((event) => {
    if (event.scrollTopChanged) told(most() > 0 ? editor.getScrollTop() / most() : 0);
  });
  return { to: (part) => editor.setScrollTop(part * most()), stop: () => heard.dispose() };
}

/** A preview's problem on its source's line in the editor inside `host` (line 0: none). */
export function previewProblem(host, line, message) {
  const model = editorIn(host)?.getModel();
  if (!model) return;
  const at = Math.min(Math.max(1, line), model.getLineCount());
  const marks = line > 0 ? [{ startLineNumber: at, endLineNumber: at, startColumn: 1, endColumn: model.getLineMaxColumn(at), message, severity: monaco.MarkerSeverity.Error }] : [];
  monaco.editor.setModelMarkers(model, "preview", marks);
}

/** The page's theme for every editor (Monaco has one theme at a time). */
export function setTheme(theme) {
  monaco.editor.setTheme(THEMES[theme] ?? "vs");
}

/**
 * An editor in `host`. options: value, language (python, sql, dax, markdown, html, json...), readOnly, grow (a
 * notebook cell: as tall as its text, no scrollbar of its own), minLines, intel (ask the server), theme.
 */
// `${` in a SQL editor lists this computer's variables (the classic variableBox.ts list: each name and its source in
// words, never a value), asked of GET /variables when it is typed.
let variablesListed = false;
function variableCompletion() {
  if (variablesListed) return;
  variablesListed = true;
  monaco.languages.registerCompletionItemProvider("sql", {
    triggerCharacters: ["{"],
    async provideCompletionItems(model, position) {
      const before = model.getLineContent(position.lineNumber).slice(0, position.column - 1);
      const typed = /\$\{([A-Za-z0-9_]*)$/.exec(before);
      if (!typed) return { suggestions: [] };
      const range = new monaco.Range(position.lineNumber, position.column - typed[1].length, position.lineNumber, position.column);
      const answer = await fetch("/variables", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : { variables: [] }), () => ({ variables: [] }));
      return {
        incomplete: false,
        suggestions: (answer.variables ?? []).map((v) => ({
          label: v.name,
          kind: monaco.languages.CompletionItemKind.Variable,
          insertText: `${v.name}}`,
          filterText: v.name,
          range,
          detail: v.vault ? `${v.words} · ${v.vault}` : v.words,
          sortText: `0${v.name}`,
        })),
      };
    },
  });
}

function modelAt(path, value, language) {
  const uri = monaco.Uri.parse(`file:///${path.replace(/\\/g, "/").replace(/^\/+/, "")}`);
  monaco.editor.getModel(uri)?.dispose();
  return monaco.editor.createModel(value, language, uri);
}

export function create(host, dotnet, options) {
  registerIntel();
  const language = LANGUAGES[options.language] ?? options.language ?? "plaintext";
  const grow = !!options.grow;
  // A file of a project (a code app's): its model by its path, so the TypeScript service resolves its imports.
  const pathModel = options.path ? modelAt(options.path, options.value ?? "", language) : null;
  const editor = monaco.editor.create(host, {
    ...(pathModel ? { model: pathModel } : { value: options.value ?? "", language }),
    theme: THEMES[options.theme] ?? "vs",
    automaticLayout: !grow,
    minimap: { enabled: false },
    lineNumbers: grow ? "off" : "on",
    folding: !grow,
    lineDecorationsWidth: grow ? 6 : 10,
    scrollBeyondLastLine: false,
    renderLineHighlight: grow ? "none" : "line",
    overviewRulerLanes: 0,
    scrollbar: grow ? { vertical: "hidden", horizontal: "auto", alwaysConsumeMouseWheel: false, handleMouseWheel: false } : {},
    wordWrap: language === "markdown" ? "on" : "off",
    fontSize: 13,
    tabSize: 4,
    insertSpaces: true,
    quickSuggestions: { other: true, comments: false, strings: true },
    fixedOverflowWidgets: true,
    // The right-click menu in the page itself: in a shadow root it had none of Monaco's bundled CSS (codeEditor.css
    // is linked from the page), so it drew with no background and, in the dark theme, could hardly be read.
    useShadowDOM: false,
    readOnly: !!options.readOnly,
    readOnlyMessage: { value: options.readOnlyMessage ?? "This cell follows the Tables page: change the table's steps there." },
    placeholder: options.placeholder,
    glyphMargin: !!options.breakpoints,
  });
  const model = editor.getModel();
  const owner = { dotnet, intel: !!options.intel, language, inline: options.inline ?? [] };
  for (const provider of owner.inline) provider.languages.forEach(registerInline);
  owners.set(model, owner);

  const minLines = options.minLines ?? 1;
  const fit = () => {
    const line = editor.getOption(monaco.editor.EditorOption.lineHeight);
    const height = Math.max(editor.getContentHeight(), minLines * line + 8);
    host.style.height = `${Math.round(height)}px`;
    editor.layout({ width: host.clientWidth, height });
  };
  let resize = null;
  if (grow) {
    editor.onDidContentSizeChange(fit);
    resize = new ResizeObserver(() => editor.layout({ width: host.clientWidth, height: host.clientHeight }));
    resize.observe(host);
    fit();
  }

  let textTimer = 0;
  let lintTimer = 0;
  let quiet = false; // a setValue from C# is not a change to tell C# about
  const lintSoon = () => {
    const linted = INTEL_LANGUAGES.includes(owner.language) || owner.language === POWER_QUERY;
    if (!owner.intel || !linted || editor.getOption(monaco.editor.EditorOption.readOnly)) return;
    clearTimeout(lintTimer);
    lintTimer = setTimeout(() => lint(model, owner.language), LINT_SETTLES_MS);
  };
  editor.onDidChangeModelContent(() => {
    lintSoon();
    if (quiet) return;
    clearTimeout(textTimer);
    textTimer = setTimeout(() => dotnet.invokeMethodAsync("Changed", editor.getValue()).catch(() => {}), TEXT_SETTLES_MS);
  });
  editor.onDidFocusEditorText(() => dotnet.invokeMethodAsync("Focused").catch(() => {}));
  lintSoon();
  // The screen state (screen.js, the agent's app_screen) reads this editor's cursor, selected lines and problem
  // count here: numbers only, never its text.
  const onScreen = {
    host,
    at: 0,
    read: () => {
      const picked = editor.getSelection();
      return {
        focused: editor.hasTextFocus(),
        at: onScreen.at,
        line: picked?.positionLineNumber ?? 1,
        column: picked?.positionColumn ?? 1,
        from: picked?.startLineNumber ?? 1,
        to: picked?.endLineNumber ?? 1,
        problems: monaco.editor.getModelMarkers({ resource: model.uri }).length,
      };
    },
  };
  (window.sabScreenEditors ??= new Set()).add(onScreen);
  editor.onDidFocusEditorText(() => (onScreen.at = Date.now()));

  // The keys a page acts on: told to C# by name, the text sent first so C# runs what is on screen.
  const key = (name) => () => {
    clearTimeout(textTimer);
    editor.trigger("sab", "hideSuggestWidget", {});
    dotnet.invokeMethodAsync("Key", name, editor.getValue()).catch(() => {});
  };
  // Each key as an action of this editor (addAction is bound to its own editor; addCommand would run the last
  // editor's handler whichever editor has the focus, a known Monaco behaviour with several editors on a page).
  const K = monaco.KeyMod;
  const C = monaco.KeyCode;
  const keys = [
    ["run", K.Shift | C.Enter],
    ["runHere", K.CtrlCmd | C.Enter],
    ["runInsert", K.Alt | C.Enter],
    ["save", K.CtrlCmd | C.KeyS],
    ["saveAs", K.CtrlCmd | K.Shift | C.KeyS],
    ["runFile", C.F5],
    ["escape", K.Shift | C.Escape],
  ];
  for (const [name, binding] of keys) {
    editor.addAction({ id: `sab.${name}`, label: name, keybindings: [binding], run: key(name) });
  }

  // The Scripts page's IDE moves (the classic workbenchIde.ts): Go to Definition (F12), Find All References
  // (Shift+F12), Rename Symbol (F2), Format Document (Shift+Alt+F), told to C# with the cursor's place and word;
  // the first and the third also in the editor's right-click menu, as the classic editor has them.
  // The code's own zoom (the classic codeIde.ts): Ctrl+= and Ctrl+- (and Ctrl + wheel) over the code size the code
  // alone, Ctrl+0 back to 100%; told to C# by name so the bar shows the size.
  if (options.zoom) {
    for (const [name, binding] of [["zoomIn", K.CtrlCmd | C.Equal], ["zoomOut", K.CtrlCmd | C.Minus], ["zoomReset", K.CtrlCmd | C.Digit0]]) {
      editor.addAction({ id: `sab.${name}`, label: name, keybindings: [binding], run: key(name) });
    }
    host.addEventListener("wheel", (event) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      key(event.deltaY < 0 ? "zoomIn" : "zoomOut")();
    }, { passive: false });
  }

  if (options.ide) {
    const ide = (name) => () => {
      const at = editor.getPosition();
      if (!at) return;
      const word = model.getWordAtPosition(at)?.word ?? "";
      dotnet.invokeMethodAsync("Ide", name, editor.getValue(), at.lineNumber, at.column, word).catch(() => {});
    };
    const moves = [
      ["definition", "Go to Definition", [C.F12], "navigation", 1],
      ["references", "Find All References", [K.Shift | C.F12], "navigation", 2],
      ["rename", "Rename Symbol", [C.F2], "1_modification", 1],
      ["format", "Format Document", [K.Shift | K.Alt | C.KeyF], "1_modification", 2],
    ];
    for (const [name, label, keybindings, group, order] of moves) {
      editor.addAction({ id: `sab.ide.${name}`, label, keybindings, contextMenuGroupId: group, contextMenuOrder: order, run: ide(name) });
    }
  }

  // The editor's own right-click menu (the classic lazy/codeEditor.ts): Send to the agent (and with a question…), the
  // page's actions for this editor (a cell's Lineage), Insert variable… in SQL, and beta mode's Leave a note…; each
  // told to C# by its id with the selection (or the cursor's line).
  const menu = options.menu ?? {};
  const picked = (id) => () => {
    const chosen = editor.getSelection();
    const line = chosen?.startLineNumber ?? editor.getPosition()?.lineNumber ?? 1;
    const end = chosen && !chosen.isEmpty() ? chosen.endLineNumber : line;
    const text = chosen && !chosen.isEmpty() ? model.getValueInRange(chosen) : model.getLineContent(line);
    dotnet.invokeMethodAsync("Menu", id, line, end, text).catch(() => {});
  };
  if (menu.agent) {
    editor.addAction({ id: "sab.sendToAgent", label: "Send to the agent", contextMenuGroupId: "0_agent", contextMenuOrder: 1, run: picked("sendToAgent") });
    editor.addAction({ id: "sab.sendToAgentAsk", label: "Send to the agent with a question…", contextMenuGroupId: "0_agent", contextMenuOrder: 2, run: picked("sendToAgentAsk") });
  }
  for (const action of menu.actions ?? []) {
    editor.addAction({ id: `sab.page.${action.id}`, label: action.label, contextMenuGroupId: "1_cell", contextMenuOrder: 1, run: picked(action.id) });
  }
  if (language === "sql") {
    variableCompletion();
    editor.addAction({
      id: "sab.insertVariable",
      label: "Insert variable…",
      contextMenuGroupId: "9_cutcopypaste",
      contextMenuOrder: 9,
      run: () => {
        editor.trigger("sab", "type", { text: "${" });
        editor.trigger("sab", "editor.action.triggerSuggest", {});
      },
    });
  }
  if (menu.beta) {
    editor.addAction({ id: "sab.leaveNote", label: "Leave a note…", contextMenuGroupId: "9_beta", contextMenuOrder: 1, run: picked("leaveNote") });
  }


  // Review comments (the owner, 2026-11-27): select, right-click, Annotate… (Ctrl+Alt+M; "annotations" on screen, the owner 2026-11-27: the code kept "comment"). A comment is a decoration
  // of this editor and nothing else: never text of the model, so Save cannot write one. Monaco moves its range as
  // lines are added above it; the places are told to C# (Components/ReviewComments) a moment after an edit.
  const reviews = new Map(); // id -> { marks, text, agent }
  const reviewRange = (id) => reviews.get(id)?.marks.getRange(0) ?? null;
  const reviewPlaces = () =>
    [...reviews.keys()].map((id) => {
      const range = reviewRange(id);
      const code = range.isEmpty() ? model.getLineContent(range.startLineNumber) : model.getValueInRange(range);
      return { id, line: range.startLineNumber, column: range.startColumn, end: range.endLineNumber, endColumn: range.endColumn, code: code.slice(0, REVIEW_CODE_MAX) };
    });
  const reviewLook = (text, agent) => ({
    className: agent ? "sab-comment sab-comment-agent" : "sab-comment",
    linesDecorationsClassName: agent ? "sab-comment-mark sab-comment-agent" : "sab-comment-mark",
    hoverMessage: { value: `**${agent ? "The agent's note" : "Annotation"}**  \n${plainHover(text)}` },
    stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
  });
  const reviewCounted = () => {
    if (reviews.size > 0) reviewCounts.set(reviews, reviews.size);
    else reviewCounts.delete(reviews);
    host.dataset.comments = String(reviews.size);
  };
  let reviewTimer = 0;
  const reviewAt = (line, column) =>
    [...reviews.keys()].find((id) => {
      const range = reviewRange(id);
      return column === null ? range.startLineNumber <= line && line <= range.endLineNumber : range.containsPosition({ lineNumber: line, column });
    }) ?? null;
  // The comment box asked for: at an existing comment (its id, or the cursor inside one with nothing selected),
  // else for the selection, else for the cursor's whole line.
  const reviewAsk = (id) => {
    const chosen = editor.getSelection();
    const cursor = editor.getPosition();
    if (id === null && cursor && (!chosen || chosen.isEmpty())) id = reviewAt(cursor.lineNumber, cursor.column);
    let range = id === null ? null : reviewRange(id);
    if (!range && chosen && !chosen.isEmpty()) {
      // Whole lines dragged over end at the next line's first column: that line is not part of it.
      const short = chosen.endColumn === 1 && chosen.endLineNumber > chosen.startLineNumber;
      const end = short ? chosen.endLineNumber - 1 : chosen.endLineNumber;
      range = new monaco.Range(chosen.startLineNumber, chosen.startColumn, end, short ? model.getLineMaxColumn(end) : chosen.endColumn);
    }
    if (!range) {
      const line = cursor?.lineNumber ?? 1;
      range = new monaco.Range(line, 1, line, model.getLineMaxColumn(line));
    }
    editor.revealRangeInCenterIfOutsideViewport(range);
    const at = editor.getScrolledVisiblePosition({ lineNumber: range.endLineNumber, column: 1 });
    const box = host.getBoundingClientRect();
    const info = editor.getLayoutInfo();
    dotnet.invokeMethodAsync("CommentAsk", {
      id,
      line: range.startLineNumber,
      column: range.startColumn,
      end: range.endLineNumber,
      endColumn: range.endColumn,
      x: box.left + info.contentLeft,
      y: box.top + (at ? at.top + at.height : 0) + 2,
      text: id === null ? "" : reviews.get(id).text,
    }).catch(() => {});
  };
  if (options.comments) {
    editor.addAction({
      id: "sab.comment",
      label: "Annotate…",
      keybindings: [K.CtrlCmd | K.Alt | C.KeyM],
      // The very top of the menu (the owner, 2026-11-27): Monaco draws the "navigation" group first.
      contextMenuGroupId: "navigation",
      contextMenuOrder: 0,
      run: () => reviewAsk(null),
    });
    // A click on a comment's mark in the gutter opens it.
    editor.onMouseDown((e) => {
      if (e.target.type !== monaco.editor.MouseTargetType.GUTTER_LINE_DECORATIONS || !e.event.leftButton) return;
      const found = reviewAt(e.target.position?.lineNumber ?? 0, null);
      if (found !== null) reviewAsk(found);
    });
    editor.onDidChangeModelContent(() => {
      if (reviews.size === 0) return;
      clearTimeout(reviewTimer);
      reviewTimer = setTimeout(() => dotnet.invokeMethodAsync("CommentsMoved", reviewPlaces()).catch(() => {}), TEXT_SETTLES_MS);
    });
  }
  const reviewAdd = (c) => {
    reviews.get(c.id)?.marks.clear();
    const last = Math.min(Math.max(c.end, c.line), model.getLineCount());
    const first = Math.min(c.line, last);
    const range = new monaco.Range(first, c.column || 1, last, c.endColumn || model.getLineMaxColumn(last));
    reviews.set(c.id, { marks: editor.createDecorationsCollection([{ range, options: reviewLook(c.text, c.agent) }]), text: c.text, agent: !!c.agent });
    reviewCounted();
  };
  for (const kept of options.reviewNotes ?? []) reviewAdd(kept);

  // The debugger's gutter (the classic workbenchDebug.ts): a click in the glyph margin toggles a breakpoint, a right
  // click there or on a line number opens its menu; both told to C# by the line.
  const breakpointDecorations = editor.createDecorationsCollection([]);
  const executionDecoration = editor.createDecorationsCollection([]);
  if (options.breakpoints) {
    // The debugger's keys in the editor (F9 toggles; while paused F10 steps over, Shift+F11 out, Shift+F5 stops).
    const debugKeys = [
      ["toggleBreakpoint", C.F9],
      ["stepOver", C.F10],
      ["stepOut", K.Shift | C.F11],
      ["stopDebugging", K.Shift | C.F5],
    ];
    for (const [name, binding] of debugKeys) {
      editor.addAction({ id: `sab.${name}`, label: name, keybindings: [binding], run: key(name) });
    }
    const G = monaco.editor.MouseTargetType;
    const lineOf = (e) => (e.target.type === G.GUTTER_GLYPH_MARGIN || e.target.type === G.GUTTER_LINE_NUMBERS ? (e.target.position?.lineNumber ?? null) : null);
    editor.onMouseDown((e) => {
      if (e.target.type !== G.GUTTER_GLYPH_MARGIN || !e.event.leftButton) return;
      const line = lineOf(e);
      if (line) dotnet.invokeMethodAsync("Gutter", line, false, 0, 0).catch(() => {});
    });
    editor.onContextMenu((e) => {
      const line = lineOf(e);
      if (line === null) return;
      e.event.preventDefault();
      dotnet.invokeMethodAsync("Gutter", line, true, e.event.posx, e.event.posy).catch(() => {});
    });
  }

  return {
    /** Review comments: one drawn ({id, line, column, end, endColumn, text, agent}), its words changed, one or
     *  all taken away, each one's place and code as the edits left it, one shown, the box asked for. */
    addComment: reviewAdd,
    updateComment: (id, text) => {
      const found = reviews.get(id);
      if (!found) return;
      const range = reviewRange(id);
      found.text = text;
      found.marks.set([{ range, options: reviewLook(text, found.agent) }]);
    },
    removeComment: (id) => {
      reviews.get(id)?.marks.clear();
      reviews.delete(id);
      reviewCounted();
    },
    clearComments: () => {
      for (const found of reviews.values()) found.marks.clear();
      reviews.clear();
      reviewCounted();
    },
    commentPlaces: reviewPlaces,
    revealComment: (id) => {
      const range = reviewRange(id);
      if (!range) return;
      editor.revealRangeInCenter(range);
      editor.setPosition(range.getStartPosition());
      editor.focus();
    },
    askComment: (id) => reviewAsk(id ?? null),
    /** The whole lines from..to selected (the agent's and a test's way to a selection). */
    selectLines: (from, to) => {
      const last = Math.min(Math.max(to, from), model.getLineCount());
      editor.setSelection(new monaco.Range(Math.min(from, last), 1, last, model.getLineMaxColumn(last)));
      editor.focus();
    },
    /** The breakpoints drawn in the gutter: [{line, kind: plain | condition | log, title}]. */
    setBreakpoints: (marks) =>
      breakpointDecorations.set(
        marks.map((m) => ({
          range: new monaco.Range(m.line, 1, m.line, 1),
          options: {
            glyphMarginClassName: `sab-breakpoint bp-${m.kind}`,
            glyphMarginHoverMessage: m.title ? { value: m.title } : undefined,
            stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
          },
        })),
      ),
    /** The breakpoints' lines as edits have moved them. */
    breakpointLines: () => breakpointDecorations.getRanges().map((r) => r.startLineNumber),
    /** The line a paused run stopped at (highlighted, scrolled to); 0 clears it. */
    setExecutionLine: (line) => {
      if (!line) return void executionDecoration.clear();
      executionDecoration.set([{ range: new monaco.Range(line, 1, line, 1), options: { isWholeLine: true, className: "sab-paused-line", glyphMarginClassName: "sab-paused-arrow" } }]);
      editor.revealLineInCenterIfOutsideViewport(line);
    },
    cursorLine: () => editor.getPosition()?.lineNumber ?? 0,
    /** The lint's problems as drawn (the status bar's Problems list), and whether Ruff could check it too. */
    problems: () => monaco.editor.getModelMarkers({ resource: model.uri, owner: "sab-lint" })
      .filter((m) => m.severity >= monaco.MarkerSeverity.Warning)
      .map((m) => ({ line: m.startLineNumber, col: m.startColumn, message: m.message })),
    ruffMissing: () => owners.get(model)?.ruffMissing === true,
    /** Problems the page's own rule found (a code app's pages rule): {line, col, endLine, endCol, message, severity}. */
    setProblems: (list) =>
      monaco.editor.setModelMarkers(
        model,
        "sab-app",
        (list ?? []).map((p) => ({
          startLineNumber: p.line,
          startColumn: p.col ?? 1,
          endLineNumber: p.endLine ?? p.end_line ?? p.line,
          endColumn: p.endCol ?? p.end_col ?? (p.col ?? 1) + 1,
          message: p.hover ? `${p.message}\n${p.hover}` : p.message,
          severity: SEVERITY[p.severity] ?? monaco.MarkerSeverity.Warning,
        })),
      ),
    /** A place in the code shown, the cursor there. */
    reveal: (line, col) => {
      editor.revealLineInCenter(line);
      editor.setPosition({ lineNumber: line, column: col });
      editor.focus();
    },
    /** F1: the server's help on the name at the cursor (its hover's words), or null. */
    helpAtCursor: async () => {
      const position = editor.getPosition();
      if (!position) return null;
      const found = await ask("hover", model, { offset: model.getOffsetAt(position) });
      return found?.hover ?? null;
    },
    setFontSize: (px) => editor.updateOptions({ fontSize: px }),
    getValue: () => editor.getValue(),
    /** Text from C#: the cursor kept where it was, and no Changed told back. */
    setValue: (text) => {
      if (text === editor.getValue()) return;
      const where = editor.getPosition();
      quiet = true;
      // Only the part that differs is replaced (what both texts start and end with stays), so what is drawn on
      // the unchanged lines (review comments, breakpoints) stays on them instead of collapsing to the first line.
      const old = editor.getValue();
      const most = Math.min(old.length, text.length);
      let head = 0;
      while (head < most && old.charCodeAt(head) === text.charCodeAt(head)) head++;
      let tail = 0;
      while (tail < most - head && old.charCodeAt(old.length - 1 - tail) === text.charCodeAt(text.length - 1 - tail)) tail++;
      const range = monaco.Range.fromPositions(model.getPositionAt(head), model.getPositionAt(old.length - tail));
      editor.executeEdits("sab", [{ range, text: text.slice(head, text.length - tail) }]);
      quiet = false;
      if (where) editor.setPosition(where);
    },
    setLanguage: (name) => {
      owner.language = LANGUAGES[name] ?? name;
      monaco.editor.setModelLanguage(model, owner.language);
      monaco.editor.setModelMarkers(model, "sab-lint", []);
      lintSoon();
    },
    setReadOnly: (on) => editor.updateOptions({ readOnly: !!on }),
    lintNow: () => lint(model, owner.language),
    /** The selected text ("" when none) and its first line, else the cursor's (a SQL file's Run selection). */
    selected: () => {
      const chosen = editor.getSelection();
      if (chosen && !chosen.isEmpty()) return { text: model.getValueInRange(chosen), line: chosen.startLineNumber };
      return { text: "", line: editor.getPosition()?.lineNumber ?? 1 };
    },
    /** A run's failure at its line (a SQL file's): marked in the code and shown; null clears it. */
    markError: (line, message) => {
      if (!line) return void monaco.editor.setModelMarkers(model, "sab-run", []);
      const end = model.getLineMaxColumn(Math.min(line, model.getLineCount()));
      monaco.editor.setModelMarkers(model, "sab-run", [
        { startLineNumber: line, startColumn: 1, endLineNumber: line, endColumn: end, message: message ?? "", severity: monaco.MarkerSeverity.Error },
      ]);
      editor.revealLineInCenterIfOutsideViewport(line);
    },
    /** The selected text, else the cursor's whole line (a script's Run selection). */
    selection: () => {
      const selected = editor.getSelection();
      if (selected && !selected.isEmpty()) return model.getValueInRange(selected);
      const line = editor.getPosition()?.lineNumber ?? 1;
      return model.getLineContent(line);
    },
    /** Text on a line of its own after the cursor's line (a blade's line dropped in from the Blades pane). */
    insertLine: (text) => {
      const line = editor.getPosition()?.lineNumber ?? model.getLineCount();
      const end = model.getLineMaxColumn(line);
      const lead = model.getLineContent(line).trim() ? "\n" : "";
      editor.executeEdits("sab", [{ range: new monaco.Range(line, end, line, end), text: lead + text }]);
      editor.focus();
    },
    focus: () => editor.focus(),
    revealLine: (line) => {
      editor.revealLineInCenter(line);
      editor.setPosition({ lineNumber: line, column: 1 });
      editor.focus();
    },
    dispose: () => {
      clearTimeout(textTimer);
      clearTimeout(lintTimer);
      clearTimeout(reviewTimer);
      reviewCounts.delete(reviews);
      resize?.disconnect();
      window.sabScreenEditors?.delete(onScreen);
      owners.delete(model);
      editor.dispose();
      model.dispose();
    },
  };
}

/**
 * Monaco's diff editor in `host` (a build's files compared; the Source Control page's diff): show(before, after, file)
 * puts two texts side by side (or inline), their language from the file's name; next() and previous() move between
 * the changes (F7, Shift+F7).
 */
export function createDiff(host, options) {
  const viewer = monaco.editor.createDiffEditor(host, {
    theme: THEMES[options.theme] ?? "vs",
    automaticLayout: true,
    readOnly: true,
    originalEditable: false,
    renderSideBySide: !options.inline,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    fontSize: 13,
  });
  const EXTENSIONS = { py: "python", sql: "sql", json: "json", md: "markdown", html: "html", js: "javascript", ts: "typescript", tsx: "typescript", yaml: "yaml", yml: "yaml", toml: "ini", xml: "xml", css: "css" };
  let models = [];
  const show = (before, after, file) => {
    const language = EXTENSIONS[(file ?? "").split(".").pop()?.toLowerCase() ?? ""] ?? "plaintext";
    const made = [monaco.editor.createModel(before ?? "", language), monaco.editor.createModel(after ?? "", language)];
    viewer.setModel({ original: made[0], modified: made[1] });
    models.forEach((m) => m.dispose());
    models = made;
  };
  return {
    show,
    next: () => viewer.goToDiff("next"),
    previous: () => viewer.goToDiff("previous"),
    setInline: (on) => viewer.updateOptions({ renderSideBySide: !on }),
    dispose: () => {
      viewer.dispose();
      models.forEach((m) => m.dispose());
    },
  };
}

/** Compare: Monaco's diff editor, the file's text (left) against this page's (right), read-only. */
export function diff(host, original, modified, language, theme) {
  const lang = LANGUAGES[language] ?? language ?? "plaintext";
  const editor = monaco.editor.createDiffEditor(host, {
    theme: THEMES[theme] ?? "vs",
    readOnly: true,
    originalEditable: false,
    automaticLayout: true,
    renderSideBySide: true,
    minimap: { enabled: false },
  });
  const left = monaco.editor.createModel(original, lang);
  const right = monaco.editor.createModel(modified, lang);
  editor.setModel({ original: left, modified: right });
  return {
    dispose: () => {
      editor.dispose();
      left.dispose();
      right.dispose();
    },
  };
}
