/**
 * workbenchStatusBar.ts: the Workbench's status bar, for the focused document. Moved out of workbenchPage.ts
 * along its own heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [KERNEL]   its kernel, or the project's one Python session (its state only while it is not ready, as
 *              principle 7.9 asks; its menu always: Interrupt, Restart)
 *   [ENV]      its environment: a loose file's Python picker (New environment…, Another Python…); a
 *              project's document says the project's Python and goes to its libraries
 *   [CURSOR]   the cursor's line and column
 *   [PROBLEMS] the lint's count (errors and warnings), a click lists them; Ruff offered there only
 *   [TOGGLES]  the Data Explorer, the Console and the Environment; the mode's own toggles; Files and Blades
 *              (sideToggles: filled once the side panes exist)
 *
 * ROUTING: POST /workbench/environment (a loose file's Python).
 */
import { api } from "./api";
import { mountAppFooter } from "./appFooter";
import { button, clear, h, icon, toast } from "./dom";
import type { EnvironmentPane } from "./environmentPage";
import { errorHere } from "./errorNote";
import { chooseFile } from "./fileChooser";
import { inlineStatus } from "./inlineCompletion";
import { type Missing, promptInstall } from "./missingPackages";
import { projectPython } from "./projectSession";
import { runCommand } from "./workbenchCommands";
import { newEnvironment } from "./workbenchEnvironment";
import { onProblems, problemsOf, ruffOffer } from "./workbenchIntel";
import type { Kernel } from "./workbenchKernel";
import type { Layout } from "./workbenchLayout";
import { menuButton, type MenuEntry } from "./workbenchMenu";
import type { Doc, PythonChoice } from "./workbenchPage";

/** What the status bar asks of the page: its panes, the document in front and its cursor, the Pythons, the
 *  project's session, and the mode's toggles. */
export interface StatusHost {
  layout: Layout;
  variables: EnvironmentPane;
  modeToggles: HTMLElement;
  drawModeToggles: (doc: Doc | null) => void;
  explorer: { isOpen: () => boolean; popped: () => boolean };
  inSession: (doc: Doc | null | undefined) => boolean;
  sessionEntries: (kernel: Kernel, shared: boolean) => MenuEntry[];
  openProjectLibraries: () => void;
  kernelInstall: (doc: Doc) => (missing: Missing) => Promise<void>;
  folderOf: (path: string | null) => string;
  readonly current: Doc | null;
  readonly cursor: { line: number; column: number };
  readonly pythons: PythonChoice[];
}

// A kernel that is ready says nothing (principle 7.9): only the states that explain a wait, or need a click.
const STATE_WORDS: Record<string, string> = { off: "not started", starting: "starting…", busy: "running…" };

export function statusBar(host: StatusHost) {
  const { layout, variables, folderOf } = host;

  /** Run in another Python from the next Run on (a running kernel is stopped first). A loose file's only:
   *  a project's documents run in the project's one Python (the Environment's Libraries tab). */
  function useEnvironment(doc: Doc, python: string): void {
    doc.python = python;
    const pythons = host.pythons;
    if (!pythons.some((p) => p.python === python)) pythons.push({ python, version: "", ipykernel: true, swissarmybench: true });
    if (doc.kernel?.id) {
      doc.kernel.stop();
      toast("Kernel stopped");
    }
    if (doc.path) void api("/workbench/environment", "POST", { path: doc.path, python }).catch((e: Error) => errorHere(e));
    drawStatus();
  }

  /** A Python by its environment's last two folders (project/.venv); this app's own by those words. */
  function pythonName(python: string): string {
    if (python === host.pythons[0]?.python) return "This app's Python";
    return python
      .replace(/[\\/](bin[\\/]python[\d.]*|Scripts[\\/]python\.exe)$/i, "")
      .split(/[\\/]/)
      .filter(Boolean)
      .slice(-2)
      .join("/");
  }

  function pythonPicker(doc: Doc): HTMLElement {
    if (host.inSession(doc)) {
      // One Python per project: nothing to pick. What it is, and the way to its libraries.
      const project = projectPython();
      const words = project?.own ? "The project's Python" : project?.status === "making" ? "This app's Python (the project's is being made)" : "This app's Python";
      return button(words, () => host.openProjectLibraries(), { class: "ghost wb-env-project", title: `${project?.words ?? ""} Libraries: the Environment page.`.trim() });
    }
    const select = h("select", { class: "wb-env-pick", "aria-label": "Environment", title: "Environment" }) as HTMLSelectElement;
    const pythons = host.pythons;
    const own = pythons[0];
    const label = (p: PythonChoice): string => `${pythonName(p.python)}${p.version ? ` (${p.version})` : ""}${p.ipykernel ? "" : ", no ipykernel"}`;
    for (const p of pythons) select.append(h("option", { value: p.python, title: p.python, selected: (doc.python ?? own?.python) === p.python }, label(p)));
    select.append(h("option", { value: "__new" }, "New environment…"), h("option", { value: "__other" }, "Another Python…"));
    select.addEventListener("change", async () => {
      if (select.value === "__new") {
        const made = await newEnvironment({ folder: folderOf(doc.path), document: doc.path, appVersion: own?.version ?? "" });
        if (made) {
          useEnvironment(doc, made.python);
          if (made.imports.length && doc.notebook) doc.notebook.add("code", made.imports.join("\n"), true);
        }
        drawStatus();
        return;
      }
      if (select.value === "__other") {
        const path = await chooseFile({ title: "Choose a Python", mode: "file", start: folderOf(doc.path) });
        if (path) useEnvironment(doc, path);
        drawStatus();
        return;
      }
      useEnvironment(doc, select.value);
    });
    return select;
  }

  const kernelHost = h("span", { class: "wb-status-kernel" });
  const envHost = h("span", { class: "wb-status-env" });
  const cursorHost = h("span", { class: "wb-status-cursor" });
  const consoleToggle = button("Console", () => {
    layout.toggle("console");
    drawStatus();
  }, { class: "ghost wb-toggle wb-console-toggle", pressed: false });
  const variablesToggle = button("Environment", () => {
    if (layout.toggle("right")) void variables.refresh();
    drawStatus();
  }, { class: "ghost wb-toggle wb-variables-toggle", pressed: false });
  const explorerToggle = button("Data Explorer", () => void runCommand("view.explorer").catch((e: Error) => errorHere(e)), {
    class: "ghost wb-toggle wb-explorer-toggle",
    pressed: false,
    title: "Data Explorer (Ctrl+Shift+E)",
  });
  // The lint's count for the document in front (errors and warnings; unused names are faded, not counted):
  // a click lists every problem, and goes to the one picked. Nothing shows while there is none.
  const problemsButton = menuButton(
    button("Problems", () => undefined, { icon: "warning", class: "ghost wb-problems" }),
    "Problems",
    () => {
      const found = problemsOf(problemsKey(host.current));
      const entries: MenuEntry[] = found.flatMap((s) =>
        s.problems.map((p) => ({
          label: `${s.place ? `${s.place}, ` : ""}line ${p.line}: ${p.message.replace(/`/g, "")}${p.code ? ` (${p.code})` : ""}`,
          icon: p.severity === "error" ? "problem" : p.severity === "warning" ? "warning" : "info",
          run: () => s.reveal(p.line, p.col),
        })),
      );
      const listed: MenuEntry[] = entries.length ? entries : [{ label: "No problems", disabled: true }];
      // Ruff, offered here only (quietly: never a prompt by itself): into the document's own Python.
      const doc = host.current;
      const ruff = doc ? ruffOffer(problemsKey(doc)) : null;
      if (ruff && doc) {
        listed.push(null, {
          label: "Check with Ruff too: install ruff…",
          icon: "import",
          run: () => void promptInstall(ruff, { force: true, install: host.kernelInstall(doc), then: () => relint(doc) }),
        });
      }
      return listed;
    },
    { above: true },
  );
  problemsButton.hidden = true;
  /** The key the editors' problems are kept under for a document (workbenchIntel.ts's document). */
  function problemsKey(doc: Doc | null): string {
    if (!doc) return "\u0000none";
    return doc.path ?? (doc.kind === "notebook" ? "Untitled notebook" : "Untitled script");
  }
  function drawProblems(): void {
    const doc = host.current;
    const found = doc && (doc.notebook || doc.script) ? problemsOf(problemsKey(doc)).flatMap((s) => s.problems) : [];
    const errors = found.filter((p) => p.severity === "error").length;
    const warnings = found.filter((p) => p.severity === "warning").length;
    problemsButton.hidden = errors + warnings === 0;
    const words = [errors ? `${errors} ${errors === 1 ? "error" : "errors"}` : "", warnings ? `${warnings} ${warnings === 1 ? "warning" : "warnings"}` : ""]
      .filter(Boolean)
      .join(", ");
    const label = problemsButton.querySelector(".btn-label");
    if (label) label.textContent = words;
    problemsButton.setAttribute("aria-label", words ? `Problems: ${words}` : "Problems");
    problemsButton.title = words;
    problemsButton.classList.toggle("has-errors", errors > 0);
  }
  onProblems(drawProblems);
  /** Check a document's editors again (Ruff came in). */
  function relint(doc: Doc): void {
    doc.script?.relint();
    doc.notebook?.relint();
  }
  // The app's one footer (appFooter.ts), the Workbench's own parts in its middle: the panes' switches on the right.
  // Files and Blades' buttons (sidePanes.ts) at the end, as the Canvas's Widgets and Properties: put in once the panes exist.
  const sideToggles = h("span", { class: "wb-side-toggles", role: "group", "aria-label": "Panes" });
  mountAppFooter(
    layout.status,
    [explorerToggle, kernelHost, envHost, cursorHost, problemsButton, inlineStatus()],
    [consoleToggle, host.modeToggles, variablesToggle, sideToggles],
  );

  function drawCursor(): void {
    const doc = host.current;
    const cursor = host.cursor;
    cursorHost.textContent = doc?.notebook || doc?.script ? `Line ${cursor.line}, column ${cursor.column}` : "";
  }

  /** The status bar: the kernel (its state only while it is not ready, as principle 7.9 asks; its menu
   *  always), the environment, the cursor; the Console and Variables toggles. */
  function drawStatus(): void {
    const doc = host.current;
    const kernel = doc?.kernel;
    if (doc && kernel) {
      // A project's document: the project's one Python session (busy while any of its documents runs).
      const shared = host.inSession(doc);
      const elsewhere = kernel.state === "idle" && kernel.othersRunning() > 0;
      const look = elsewhere ? "busy" : kernel.state;
      const words = elsewhere ? "running another document's code…" : STATE_WORDS[kernel.state];
      const name = shared ? "Python session" : "Kernel";
      const knob = h(
        "button",
        {
          type: "button",
          class: `btn ghost wb-kernel ${look}${shared ? " shared" : ""}`,
          "aria-label": name,
          title: shared ? kernel.sessionWords || projectPython()?.session || "" : "Kernel: Interrupt, Restart",
        },
        h("span", { class: "wb-dot", "aria-hidden": "true" }),
        h("span", {}, name),
        words ? h("span", { class: `wb-state ${look}` }, words, kernel.running > 1 ? ` (${kernel.running - 1} waiting)` : "") : null,
        icon("down"),
      ) as HTMLButtonElement;
      menuButton(knob, name, () => host.sessionEntries(kernel, shared), { above: true });
      clear(kernelHost, knob);
      // Not drawn again while the picker is in use (a run's state changes would close it).
      if (!envHost.contains(document.activeElement) || envHost.dataset.doc !== String(doc.id)) {
        clear(envHost, pythonPicker(doc));
        envHost.dataset.doc = String(doc.id);
      }
    } else {
      clear(kernelHost, doc ? h("span", { class: "hint" }, doc.kind === "blade" ? "Blade" : doc.kind === "structure" ? "Structure" : "Table") : null);
      clear(envHost);
      envHost.dataset.doc = "";
    }
    drawCursor();
    drawProblems();
    explorerToggle.setAttribute("aria-pressed", String(host.explorer.isOpen() || host.explorer.popped()));
    const state = layout.state();
    consoleToggle.setAttribute("aria-pressed", String(state.console));
    variablesToggle.setAttribute("aria-pressed", String(state.right));
    consoleToggle.disabled = !doc?.console;
    consoleToggle.title = doc?.console ? "Console (Ctrl+2)" : "No console for what is in front";
    variablesToggle.hidden = doc?.kind === "script";
    host.drawModeToggles(doc);
  }

  /** The environment's picker drawn again on the next status (the project's Python changed). */
  const forgetPicker = (): void => void (envHost.dataset.doc = "");

  return { drawStatus, drawCursor, forgetPicker, sideToggles };
}
