// Unit tests for the pure parts: which install runs the server and its tools, the Chrome launcher, and that the
// manifest offers the tools and the Open button. Run with mocha in Node.

import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";
import { infoFile, openCommand, samePath, serverModule, serverPythons, windowlessPython } from "../src/core/paths";
const TOOL = "C:\\Users\\me\\AppData\\Roaming\\uv\\tools\\swissarmybench\\Scripts\\python.exe";

describe("serverPythons", () => {
  it("starts from the uv tool install the installers make", () => {
    const found = serverPythons({ APPDATA: "C:\\Users\\me\\AppData\\Roaming" }, "C:\\Users\\me", "win32");
    assert.strictEqual(found[0], TOOL);
  });
  it("uses only UV_TOOL_DIR when it is set, as uv does", () => {
    const found = serverPythons({ UV_TOOL_DIR: "D:\\uvtools", APPDATA: "C:\\a" }, "C:\\Users\\me", "win32");
    assert.deepStrictEqual(found, [
      path.win32.join("D:\\uvtools", "swissarmybench", "Scripts", "python.exe"),
      path.win32.join("D:\\uvtools", "swissarmygrid", "Scripts", "python.exe"),
    ]);
  });
  it("uses only SWISSARMYBENCH_SERVER when it is set (a typo fails, it never falls back)", () => {
    assert.deepStrictEqual(serverPythons({ SWISSARMYBENCH_SERVER: "C:\\dev\\python.exe", APPDATA: "C:\\a" }, "C:\\u", "win32"), [
      "C:\\dev\\python.exe",
    ]);
  });
  it("finds the connection file the server and the push client use", () => {
    assert.strictEqual(infoFile({}, "C:\\Users\\me"), path.join("C:\\Users\\me", ".swissarmybench", "server.json"));
    assert.strictEqual(infoFile({ SWISSARMYBENCH_INFO: "C:\\t\\s.json" }, "C:\\Users\\me"), "C:\\t\\s.json");
  });

  // Swiss Army Bench was SwissArmyGrid: the old names still work for one release.
  it("reads the old variables when the new ones are not set", () => {
    assert.deepStrictEqual(serverPythons({ SWISSARMYGRID_SERVER: "C:\\old\\python.exe" }, "C:\\u", "win32"), ["C:\\old\\python.exe"]);
    assert.deepStrictEqual(serverPythons({ SWISSARMYBENCH_SERVER: "C:\\new.exe", SWISSARMYGRID_SERVER: "C:\\old.exe" }, "C:\\u", "win32"), ["C:\\new.exe"]);
    assert.strictEqual(infoFile({ SWISSARMYGRID_INFO: "C:\\t\\old.json" }, "C:\\Users\\me"), "C:\\t\\old.json");
  });
  it("reads the old state folder while only it is there, and the new one once it exists", () => {
    const home = path.join("C:", "Users", "me");
    const only = (...folders: string[]) => (file: string) => folders.some((f) => path.join(home, f) === file);
    assert.strictEqual(infoFile({}, home, only(".swissarmygrid")), path.join(home, ".swissarmygrid", "server.json"));
    assert.strictEqual(infoFile({}, home, only(".swissarmygrid", ".swissarmybench")), path.join(home, ".swissarmybench", "server.json"));
    assert.strictEqual(infoFile({}, home, only()), path.join(home, ".swissarmybench", "server.json"));
  });
  it("finds the old uv tool after the new one, and runs the old tool by its old package", () => {
    const found = serverPythons({ APPDATA: "C:\\Users\\me\\AppData\\Roaming" }, "C:\\Users\\me", "win32");
    assert.strictEqual(found.indexOf(TOOL), 0);
    const old = found.find((p) => p.includes("\\swissarmygrid\\"));
    assert.ok(old && found.indexOf(old) > 0);
    assert.strictEqual(serverModule(TOOL, "mcp.server"), "swissarmybench.mcp.server");
    assert.strictEqual(serverModule(old ?? "", "server"), "swissarmygrid.server");
    assert.strictEqual(serverModule("/home/x/.local/share/uv/tools/swissarmygrid/bin/python", "server"), "swissarmygrid.server");
    assert.strictEqual(serverModule("/home/x/.local/share/uv/tools/swissarmybench/bin/python", "server"), "swissarmybench.server");
  });
  it("compares Windows paths without case or trailing slashes", () => {
    assert.ok(samePath("C:\\A\\python.exe", "c:/a/PYTHON.EXE", "win32"));
    assert.ok(!samePath("C:\\A\\python.exe", "C:\\B\\python.exe", "win32"));
  });
});

describe("windowlessPython", () => {
  const tool = path.win32.join("C:", "Users", "x", "AppData", "Roaming", "uv", "tools", "swissarmybench", "Scripts");
  const has = (...files: string[]) => (file: string) => files.some((f) => samePath(f, file, "win32"));

  it("starts the server with pythonw.exe on Windows, so no console window appears", () => {
    const python = path.win32.join(tool, "python.exe");
    const pythonw = path.win32.join(tool, "pythonw.exe");
    assert.strictEqual(windowlessPython(python, "win32", has(pythonw)), pythonw);
  });
  it("keeps python.exe when there is no pythonw.exe beside it", () => {
    const python = path.win32.join(tool, "python.exe");
    assert.strictEqual(windowlessPython(python, "win32", has()), python);
  });
  it("leaves other platforms and other interpreters alone", () => {
    assert.strictEqual(windowlessPython("/home/x/.local/share/uv/tools/swissarmybench/bin/python", "linux", () => true), "/home/x/.local/share/uv/tools/swissarmybench/bin/python");
    const other = path.win32.join("C:", "dev", "py.exe");
    assert.strictEqual(windowlessPython(other, "win32", () => true), other);
  });
});

describe("the Open button", () => {
  const tool = path.win32.join("C:", "Users", "x", "AppData", "Roaming", "uv", "tools", "swissarmybench", "Scripts");

  it("runs the uv tool's `swissarmybench.server open`: the desktop app, else the browser", () => {
    const python = "/home/x/.local/share/uv/tools/swissarmybench/bin/python";
    assert.deepStrictEqual(openCommand(python, "linux", () => true), {
      command: python,
      args: ["-m", "swissarmybench.server", "open"],
    });
  });
  it("uses pythonw.exe on Windows (no console window), and the old tool's module name for the old tool", () => {
    const python = path.win32.join(tool, "python.exe");
    const pythonw = path.win32.join(tool, "pythonw.exe");
    assert.strictEqual(openCommand(python, "win32", (f) => samePath(f, pythonw, "win32")).command, pythonw);
    const old = path.win32.join("C:", "uv", "tools", "swissarmygrid", "Scripts", "python.exe");
    assert.deepStrictEqual(openCommand(old, "win32", () => false).args, ["-m", "swissarmygrid.server", "open"]);
  });
  it("no longer opens Chrome: no chromePath setting", () => {
    const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "package.json"), "utf8"));
    assert.strictEqual(manifest.contributes.configuration, undefined);
    const source = fs.readFileSync(path.resolve(__dirname, "../../src/extension.ts"), "utf8");
    assert.ok(source.includes("openCommand(python"), "the button runs the app's own open");
    assert.ok(!/chrome/i.test(source));
  });
});

describe("the manifest", () => {
  const manifest = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../../package.json"), "utf8"));

  it("offers Swiss Army Bench's MCP tools to VS Code", () => {
    assert.deepStrictEqual(manifest.contributes.mcpServerDefinitionProviders, [{ id: "swissarmybench", label: "Swiss Army Bench" }]);
    const source = fs.readFileSync(path.resolve(__dirname, "../../src/extension.ts"), "utf8");
    assert.ok(source.includes('registerMcpServerDefinitionProvider("swissarmybench"'), "registered under the id the manifest names");
    assert.ok(source.includes('"-m", serverModule(python, "mcp.server")'), "the uv tool install's own MCP server");
  });

  it("has one command, Open Swiss Army Bench, on every editor and notebook toolbar", () => {
    assert.deepStrictEqual(manifest.contributes.commands.map((c: { command: string }) => c.command), ["swissarmybench.open"]);
    const isOpen = (item: { command: string; when?: string }) => item.command === "swissarmybench.open" && item.when === undefined;
    assert.ok(manifest.contributes.menus["editor/title"].some(isOpen));
    assert.ok(manifest.contributes.menus["notebook/toolbar"].some(isOpen));
    const icon = manifest.contributes.commands[0].icon.light;
    assert.ok(fs.existsSync(path.resolve(__dirname, "../..", icon)));
    assert.ok(fs.readFileSync(path.resolve(__dirname, "../../.vscodeignore"), "utf8").includes(`!${icon}`));
  });

  it("needs a VS Code with the MCP server API", () => {
    assert.ok(/\^1\.(10[1-9]|1[1-9]\d)/.test(manifest.engines.vscode), manifest.engines.vscode);
  });
});
