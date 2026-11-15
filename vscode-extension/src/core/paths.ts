// paths.ts -- where Swiss Army Bench's pieces live on this machine: the connection file the server writes, and the
// Python the extension starts the server with. Pure functions of the environment, so the tests can pass their own.

import * as path from "path";

export type Env = Record<string, string | undefined>;

// Swiss Army Bench was SwissArmyGrid. For one release the old names still work here as in the server
// (src/swissarmybench/renamed.py): the old environment variables, the old state folder while it has not
// moved, and the old uv tool. The next release drops them.
const OLD_STATE = ".swissarmygrid";
export const OLD_TOOL = "swissarmygrid";

/** A variable by its new name (SWISSARMYBENCH_X), else its old one (SWISSARMYGRID_X). */
export function setting(env: Env, name: string): string | undefined {
  return env[`SWISSARMYBENCH_${name}`] || env[`SWISSARMYGRID_${name}`];
}

/** The connection file: SWISSARMYBENCH_INFO, else ~/.swissarmybench/server.json (the server and every client agree);
 *  ~/.swissarmygrid/server.json while only the old state folder is there (the server moves it on its first start). */
export function infoFile(env: Env, home: string, exists: (file: string) => boolean = () => false): string {
  const named = setting(env, "INFO");
  if (named) return named;
  const own = path.join(home, ".swissarmybench");
  const old = path.join(home, OLD_STATE);
  return path.join(!exists(own) && exists(old) ? old : own, "server.json");
}

/**
 * The Pythons that may run the server, in the order to try them:
 *   1. SWISSARMYBENCH_SERVER (or the old SWISSARMYGRID_SERVER), a python.exe with the server installed (for working on Swiss Army Bench itself: the repo's
 *      .venv). When it is set it is the only one, so a typo fails loudly instead of quietly using another install.
 *   2. The uv tool install the installers make: <uv tool dir>/swissarmybench/Scripts/python.exe (bin/python elsewhere),
 *      then the one SwissArmyGrid's installers made before the rename (<uv tool dir>/swissarmygrid/...).
 *      UV_TOOL_DIR, when set, is uv's tool folder and the only one: uv installs there and nowhere else.
 */
export function serverPythons(env: Env, home: string, platform: string): string[] {
  const named = setting(env, "SERVER");
  if (named) return [named];
  // The target platform's path rules, not this machine's: the tests build Windows paths on any host.
  const p = platform === "win32" ? path.win32 : path.posix;
  const python = platform === "win32" ? ["Scripts", "python.exe"] : ["bin", "python"];
  const roots: string[] = [];
  if (env.UV_TOOL_DIR) roots.push(env.UV_TOOL_DIR);
  else {
    if (platform === "win32" && env.APPDATA) roots.push(p.join(env.APPDATA, "uv", "tools"));
    roots.push(p.join(env.XDG_DATA_HOME || p.join(home, ".local", "share"), "uv", "tools"));
  }
  return ["swissarmybench", OLD_TOOL].flatMap((tool) => roots.map((root) => p.join(root, tool, ...python)));
}

/** A module of the server as an installed Python names it: the old swissarmygrid tool has only the old package. */
export function serverModule(python: string, module: string): string {
  const tool = path.win32.basename(path.win32.dirname(path.win32.dirname(python))); // win32 splits on both slashes
  return `${tool.toLowerCase() === OLD_TOOL ? "swissarmygrid" : "swissarmybench"}.${module}`;
}

/**
 * The Python to *start* the server with: on Windows the pythonw.exe beside python.exe, when there is one.
 *
 * A venv's python.exe is only a launcher: it starts the real interpreter as a child. Node's windowsHide hides the
 * launcher, but the child is a console program with no console to share, so Windows gives it a new, visible one, and
 * closing that window ends the server. pythonw.exe is the same interpreter built without a console, so nothing appears
 * (checked 2026-10-23: one conhost.exe attached with python.exe, none with pythonw.exe, the server answering and
 * writing its log either way). Elsewhere, or without a pythonw.exe, the python itself.
 */
export function windowlessPython(python: string, platform: string, exists: (file: string) => boolean): string {
  if (platform !== "win32" || path.win32.basename(python).toLowerCase() !== "python.exe") return python;
  const pythonw = path.win32.join(path.win32.dirname(python), "pythonw.exe");
  return exists(pythonw) ? pythonw : python;
}

/** The same file named two ways? Windows paths ignore case and either slash. */
export function samePath(a: string, b: string, platform: string): boolean {
  const normalize = platform === "win32" ? path.win32.normalize : path.posix.normalize;
  const norm = (p: string): string => normalize(p).replace(/[\\/]+$/, "");
  return platform === "win32" ? norm(a).toLowerCase() === norm(b).toLowerCase() : norm(a) === norm(b);
}
