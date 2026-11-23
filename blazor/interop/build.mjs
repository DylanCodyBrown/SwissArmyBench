// build.mjs: bundles each interop file (one per JavaScript widget) into SwissArmyBench.Web/wwwroot/js/.
//
//   node interop/build.mjs [node_modules folder]
//
// The widgets are the classic front end's own packages at the same versions (web/package.json): AG Grid, Monaco,
// Plotly, Vega and Mermaid. They are read from web/node_modules (run `npm ci` in web/ first), or the folder given.
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { existsSync } from "node:fs";

const here = path.dirname(fileURLToPath(import.meta.url));
const modules = path.resolve(process.argv[2] ?? path.join(here, "..", "..", "web", "node_modules"));
const esbuild = createRequire(path.join(modules, "noop.js"))("esbuild");
const out = path.join(here, "..", "SwissArmyBench.Web", "wwwroot", "js");

const entries = {
  shell: "shell.js",
  agGrid: "agGrid.js",
  codeEditor: "codeEditor.js",
  plotly: "plotly.js",
  vega: "vega.js",
  mermaid: "mermaid.js",
  picture: "picture.js",
  // The Canvas's pointer capture, keys and zoom (Pages/Canvas).
  canvas: "canvas.js",
  // A file saved from an answer's bytes (Export to Power BI's zip).
  files: "files.js",
  // The Excel canvas's built sheet: its charts placed over their anchor cells (Pages/Accounting).
  workbook: "workbook.js",
  // Monaco's own worker (the editor's tokens and folding off the page's thread), beside codeEditor.js.
  "editor.worker": path.join(modules, "monaco-editor", "esm", "vs", "editor", "editor.worker.js"),
};

const started = Date.now();
await esbuild.build({
  // A widget's file not written yet is left out (the pages that need it say so).
  entryPoints: Object.fromEntries(
    Object.entries(entries)
      .map(([name, file]) => [name, path.isAbsolute(file) ? file : path.join(here, file)])
      .filter(([, file]) => existsSync(file)),
  ),
  bundle: true,
  format: "esm",
  target: "es2022",
  outdir: out,
  nodePaths: [modules],
  loader: { ".ttf": "file" },
  minify: true,
  logLevel: "warning",
});
console.log(`Built blazor interop into ${out} in ${Date.now() - started} ms.`);
