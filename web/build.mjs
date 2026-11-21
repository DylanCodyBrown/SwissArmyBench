// The page's build (npm run build, build:release, watch): esbuild, run here so each page splits on its own.
//
// Each page (the grid page, the blades page, the Workbench, the Performance Analyzer) is a build of its
// own with code splitting: a page loaded when first opened (lazyPages.ts, the tour, html-to-image) is a
// chunk beside it, and a module the page shares with it is one more chunk the page loads at its start; no
// chunk is shared between two pages, so each page holds exactly the modules it held before. The editor,
// the charts and the workers (lazy/*, *.worker) and build/grid.css are one build as before: a page loads
// them by their address (/static/build/...), never through a chunk.
//
//   node build.mjs              development: minified, with source maps
//   node build.mjs --release    the wheel's: no source maps
//   node build.mjs --watch      development, rebuilt on save
// SAB_METAFILE=<folder> writes each build's esbuild metafile there (to measure what a page loads).
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import * as esbuild from "esbuild";

const release = process.argv.includes("--release");
const watch = process.argv.includes("--watch");

const PAGES = { main: "src/main.ts", catalog: "src/catalogPage.ts", workbench: "src/workbenchPage.ts", perf: "src/perfPage.ts", widget: "src/widgetPage.ts" };
const OTHERS = {
  grid: "static/grid.css",
  "lazy/codeEditor": "src/lazy/codeEditor.ts",
  "lazy/charts": "src/lazy/charts.ts",
  "lazy/diagram": "src/lazy/diagram.ts",
  "lazy/plotly": "src/lazy/plotly.ts",
  "lazy/echarts": "src/lazy/echarts.ts",
  "lazy/graphviz": "src/lazy/graphviz.ts",
  "editor.worker": "monaco-editor/editor/editor.worker.js",
  "ts.worker": "monaco-editor/language/typescript/ts.worker.js",
};

const common = {
  bundle: true,
  format: "esm",
  target: "es2022",
  outdir: "static/build",
  external: ["/static/build/*"],
  loader: { ".ttf": "file" },
  sourcemap: !release,
  minify: true,
  logLevel: "warning",
  metafile: Boolean(process.env.SAB_METAFILE),
};

const builds = [
  ...Object.entries(PAGES).map(([name, entry]) => ({
    ...common,
    entryPoints: { [name]: entry },
    splitting: true,
    chunkNames: `chunks/${name}-[hash]`,
  })),
  { ...common, entryPoints: OTHERS },
];

// A chunk from an earlier build is not left in the wheel.
rmSync("static/build/chunks", { recursive: true, force: true });

if (watch) {
  for (const options of builds) await (await esbuild.context(options)).watch();
  console.log("Watching src/ and static/grid.css: reload the page after a change.");
} else {
  const started = Date.now();
  const results = await Promise.all(builds.map((options) => esbuild.build(options)));
  if (process.env.SAB_METAFILE) {
    mkdirSync(process.env.SAB_METAFILE, { recursive: true });
    results.forEach((result, at) => writeFileSync(`${process.env.SAB_METAFILE}/${Object.keys(builds[at].entryPoints)[0].replace("/", "-")}.json`, JSON.stringify(result.metafile)));
  }
  console.log(`Built static/build/ in ${Date.now() - started} ms${release ? " (release)" : ""}.`);
}
