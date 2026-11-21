/**
 * workbenchCodeFile.ts: a code app's file in the Workbench's editor, the Power Apps extension's plug-in
 * (codeAppPage.ts opens /workbench?codefile=<path>). TypeScript and TSX with Monaco's own language service:
 * the member list with its documentation, parameter info, hovers, go to definition and the errors as you
 * type, over the project's own files (its generated models and services among them). [PLUG-IN]
 *
 *   [OPEN]    the file read from the open code app (GET /powerapps/project/file); a generated file says so
 *             (the CLI writes it again when its data source changes).
 *   [SAVE]    Ctrl+S (the Workbench's Save) writes it back (PUT /powerapps/project/file); Run live reloads.
 */
import { api } from "./api";
import { h } from "./dom";
import type { CodeEditor, EditorLanguage, Problem } from "./lazy/codeEditor";
import { loadEditors } from "./lazyLoad";

export interface CodeFileView {
  element: HTMLElement;
  path: string;
  language: string;
  text: () => string;
  save: () => Promise<void>;
  dispose: () => void;
}

interface FileAnswer {
  path: string;
  full_path: string;
  language: string;
  text: string;
  generated: boolean;
}

const MONACO: Record<string, EditorLanguage> = { typescript: "typescript", tsx: "tsx", javascript: "javascript", json: "json", css: "css", html: "html", markdown: "markdown" };

/** The project's TypeScript files, known to the language service (the one being edited left out: its own
 *  model speaks for it). */
async function projectFiles(except: string): Promise<{ path: string; text: string }[]> {
  const project = await api<{ generated?: { path: string }[] }>("/powerapps/project");
  const tree = await api<{ tree: { children?: unknown[] } }>("/powerapps/project/files");
  const paths = new Set((project.generated ?? []).map((g) => g.path));
  const walk = (node: { path?: string; children?: unknown[] }): void => {
    if (node.children) for (const c of node.children) walk(c as { path?: string; children?: unknown[] });
    else if (node.path && /\.(ts|tsx)$/.test(node.path) && node.path.startsWith("src/")) paths.add(node.path);
  };
  walk(tree.tree);
  paths.delete(except);
  const read = await Promise.all([...paths].slice(0, 200).map((p) => api<FileAnswer>(`/powerapps/project/file?path=${encodeURIComponent(p)}`).catch(() => null)));
  return read.filter((f): f is FileAnswer => f !== null).map((f) => ({ path: f.path, text: f.text }));
}

/** A new file of the open code app (New in the code app mode): src/<name>, empty; its path. */
export async function newCodeFile(name: string): Promise<string> {
  const clean = name.trim().replace(/\\/g, "/").replace(/^\/+/, "");
  if (!clean || clean.includes("..")) throw new Error("A file's name, such as orders.ts.");
  // Outside a page's folder, a file is shared by the pages (src/shared/); a page's own goes in its folder.
  const path = clean.startsWith("src/") ? clean : `src/shared/${clean}`;
  const there = await api<FileAnswer>(`/powerapps/project/file?path=${encodeURIComponent(path)}`).then(() => true, () => false);
  if (there) throw new Error(`${path} is there already: open it from the Code App page.`);
  await api("/powerapps/project/file", "PUT", { path, text: "" });
  return path;
}

/** A code app's file as an editor, its text read from the open code app. */
export async function openCodeFile(path: string, theme: string, changed: () => void): Promise<CodeFileView> {
  const found = await api<FileAnswer>(`/powerapps/project/file?path=${encodeURIComponent(path)}`);
  const m = await loadEditors();
  const language = MONACO[found.language] ?? "plaintext";
  if (language === "typescript" || language === "tsx") m.typescriptProject(await projectFiles(found.path).catch(() => []));
  const host = h("div", { class: "wb-codefile-editor" });
  const element = h(
    "div",
    { class: "wb-codefile", "data-path": found.path, "data-language": found.language },
    h("div", { class: "wb-codefile-head" }, h("code", {}, found.path), found.generated ? h("span", { class: "muted" }, " made by the Power Apps CLI: adding or refreshing its data source writes it again") : null),
    host,
  );
  const editor: CodeEditor = m.createCodeEditor(host, { language, value: found.text, theme, path: found.path });
  // The app's own rule beside TypeScript's: a page never imports another page's code (moved to src/shared/).
  let linting = 0;
  const lint = (): void => {
    const ticket = ++linting;
    void api<{ problems: Problem[] }>("/powerapps/project/lint", "POST", { path: found.path, text: editor.value() })
      .then((r) => ticket === linting && editor.setProblems(r.problems))
      .catch(() => undefined);
  };
  let soon: number | null = null;
  editor.onChange(() => {
    changed();
    if (soon !== null) clearTimeout(soon);
    soon = window.setTimeout(lint, 400);
  });
  lint();
  return {
    element,
    path: found.path,
    language: found.language,
    text: () => editor.value(),
    save: async () => {
      await api("/powerapps/project/file", "PUT", { path: found.path, text: editor.value() });
    },
    dispose: () => editor.dispose(),
  };
}
