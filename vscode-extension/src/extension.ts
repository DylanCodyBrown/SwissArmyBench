// extension.ts -- Swiss Army Bench in VS Code, and nothing more: its MCP tools as VS Code's own tools (agent mode, any
// model), and a button that opens Swiss Army Bench, as the app's icon does. The server and the tools are installed with uv
// (install.sh, install.ps1); the extension only points VS Code at them.

import { spawn } from "child_process";
import * as fs from "fs";
import * as vscode from "vscode";
import { ensureRunning, NOT_INSTALLED, serverPython, workspaceUrl } from "./vscode/server";
import { openCommand, serverModule } from "./core/paths";

export function activate(ctx: vscode.ExtensionContext): void {
  const log = vscode.window.createOutputChannel("Swiss Army Bench");

  // ===== THE TOOLS: the uv tool install's MCP server, offered to VS Code =====
  const changed = new vscode.EventEmitter<void>();
  ctx.subscriptions.push(
    log,
    changed,
    vscode.lm.registerMcpServerDefinitionProvider("swissarmybench", {
      onDidChangeMcpServerDefinitions: changed.event,
      provideMcpServerDefinitions: () => {
        const python = serverPython();
        if (!python) {
          log.appendLine(NOT_INSTALLED);
          return [];
        }
        return [new vscode.McpStdioServerDefinition("Swiss Army Bench", python, ["-m", serverModule(python, "mcp.server")])];
      },
    }),
  );

  // ===== THE BUTTON: Swiss Army Bench opened, as its launcher does: the desktop app (started with its server when it
  // is not open; its home window forward when it is), the browser where the app cannot run =====
  const viaBrowser = async (): Promise<void> => {
    const info = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Window, title: "Swiss Army Bench" },
      () => ensureRunning(),
    );
    await vscode.env.openExternal(vscode.Uri.parse(workspaceUrl(info)));
  };
  const open = async (): Promise<void> => {
    try {
      const python = serverPython();
      if (!python) throw new Error(NOT_INSTALLED);
      changed.fire(); // installed now, if it was not when VS Code started
      const { command, args } = openCommand(python, process.platform, fs.existsSync);
      // Detached with its output dropped: closing VS Code never closes the app.
      const child = spawn(command, args, { detached: true, windowsHide: true, stdio: "ignore", env: { ...process.env } });
      child.once("error", (error) => {
        log.appendLine(`${command} could not start: ${error.message}`);
        viaBrowser().catch((failed) => void vscode.window.showErrorMessage((failed as Error).message));
      });
      child.unref();
    } catch (error) {
      log.appendLine(String(error));
      void vscode.window.showErrorMessage((error as Error).message);
    }
  };
  const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  item.text = "$(table) Swiss Army Bench";
  item.command = "swissarmybench.open";
  item.show();
  ctx.subscriptions.push(item, vscode.commands.registerCommand("swissarmybench.open", open));
}

export function deactivate(): void {
  // Nothing to stop: Swiss Army Bench keeps running, as the app does, until it is closed.
}
