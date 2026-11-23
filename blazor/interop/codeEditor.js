// codeEditor.js: Monaco (the classic front end's same version), wrapped for the <CodeEditor> component.
//
// One editor per call to create(). Its text goes to C# a moment after typing stops (Changed); the keys a page acts
// on (Shift+Enter, Ctrl+Enter, Ctrl+S...) go to C# by name (Key). The editors' intelligence is the server's, the
// same routes the classic editors ask (POST /workbench/intel/complete, signature, hover and lint): each request
// asks C# first for the editor's context (the kernel, the document, a notebook's other cells) and then goes
// straight to the server, so the member list stays quick.
import * as monaco from "monaco-editor";

self.MonacoEnvironment = {
  getWorker: () => new Worker(new URL("./editor.worker.js", import.meta.url), { type: "module" }),
};

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
const LANGUAGES = { dax: "msdax", toml: "ini", tsx: "typescript" };
const TEXT_SETTLES_MS = 150;
const LINT_SETTLES_MS = 500;
const INTEL_LANGUAGES = ["python", "sql", "msdax"];

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

async function lint(model, language) {
  const found = await ask("lint", model, { language: language === "msdax" ? "dax" : language });
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
  owner?.dotnet.invokeMethodAsync("Linted", markers.filter((m) => m.severity >= monaco.MarkerSeverity.Warning).length).catch(() => {});
}

/** The page's theme for every editor (Monaco has one theme at a time). */
export function setTheme(theme) {
  monaco.editor.setTheme(THEMES[theme] ?? "vs");
}

/**
 * An editor in `host`. options: value, language (python, sql, dax, markdown, html, json...), readOnly, grow (a
 * notebook cell: as tall as its text, no scrollbar of its own), minLines, intel (ask the server), theme.
 */
export function create(host, dotnet, options) {
  registerIntel();
  const language = LANGUAGES[options.language] ?? options.language ?? "plaintext";
  const grow = !!options.grow;
  const editor = monaco.editor.create(host, {
    value: options.value ?? "",
    language,
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
    readOnly: !!options.readOnly,
    readOnlyMessage: { value: options.readOnlyMessage ?? "This cell follows the grid: change the table's steps there." },
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
    if (!owner.intel || !INTEL_LANGUAGES.includes(owner.language) || editor.getOption(monaco.editor.EditorOption.readOnly)) return;
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
    getValue: () => editor.getValue(),
    /** Text from C#: the cursor kept where it was, and no Changed told back. */
    setValue: (text) => {
      if (text === editor.getValue()) return;
      const where = editor.getPosition();
      quiet = true;
      editor.executeEdits("sab", [{ range: model.getFullModelRange(), text }]);
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
      resize?.disconnect();
      owners.delete(model);
      editor.dispose();
      model.dispose();
    },
  };
}
