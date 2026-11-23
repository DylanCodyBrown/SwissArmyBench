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
  });
  const model = editor.getModel();
  const owner = { dotnet, intel: !!options.intel, language };
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
    dotnet.invokeMethodAsync("Key", name, editor.getValue()).catch(() => {});
  };
  const K = monaco.KeyMod;
  const C = monaco.KeyCode;
  editor.addCommand(K.Shift | C.Enter, key("run"));
  editor.addCommand(K.CtrlCmd | C.Enter, key("runHere"));
  editor.addCommand(K.Alt | C.Enter, key("runInsert"));
  editor.addCommand(K.CtrlCmd | C.KeyS, key("save"));
  editor.addCommand(K.CtrlCmd | K.Shift | C.KeyS, key("saveAs"));
  editor.addCommand(C.F5, key("runFile"));
  editor.addCommand(K.Shift | C.Escape, key("escape"));

  return {
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
