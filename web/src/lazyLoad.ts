/** The heavy modules that load the first time something needs them: one loader each, shared by every page. */
import { h } from "./dom";

/** Monaco's stylesheet, linked once (a page that links it itself is left as it is). */
export function loadEditorStyles(): void {
  if (!document.querySelector('link[href="/static/build/lazy/codeEditor.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/build/lazy/codeEditor.css" }));
  }
}

let editors: Promise<typeof import("./lazy/codeEditor")> | null = null;
/** Monaco (lazy/codeEditor.ts), with its stylesheet. */
export function loadEditors(): Promise<typeof import("./lazy/codeEditor")> {
  loadEditorStyles();
  return (editors ??= import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>);
}

let diagrams: Promise<typeof import("./lazy/diagram")> | null = null;
/** Mermaid and Graphviz (lazy/diagram.ts). */
export function loadDiagrams(): Promise<typeof import("./lazy/diagram")> {
  return (diagrams ??= import(/* external */ "/static/build/lazy/diagram.js" as string) as Promise<typeof import("./lazy/diagram")>);
}
