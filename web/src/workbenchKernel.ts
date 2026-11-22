/**
 * workbenchKernel.ts: a document's IPython kernel, and how a run's outputs are drawn. [WIRE + FUNCTION]
 *
 * ROUTING: [START] POST /workbench/kernels {python, path}: it starts with every vault's variables set
 *          [RUN]   POST /workbench/kernels/{id}/execute: read as it streams, one JSON output a line
 *          [STOP]  /interrupt, /restart, DELETE (on closing the document or the window)
 *
 *          [INPUT] POST /workbench/kernels/{id}/input {value}: the line input() asked for
 *
 * ONE SESSION A PROJECT (the owner, 2026-11-21; domain/project_python.py): a document of the open project
 * does not get a kernel of its own. START answers the project's one session (the same id for every
 * document: `session.shared`), so each document's Kernel here holds that id; Interrupt and Restart act on
 * the session for all of them, closing a document leaves it running, and the `session_restarted` and
 * `session_ended` notices reach every document (sessionHeard). A loose file keeps a kernel of its own.
 *
 * Outputs are nbformat's own records (drawn by workbenchOutputs.ts). The state is "running" from the
 * first Run until the last queued run ends (two runs sent at once run one after the other).
 */
import { api, ApiError, token } from "./api";
import type { Output, OutputArea } from "./workbenchOutputs";
import { problemsHere } from "./errorNote";

export type { Output } from "./workbenchOutputs";
export { drawOutputs } from "./workbenchOutputs";

export interface Done {
  ok: boolean;
  execution_count: number | null;
  /** The kernel process ended (out of memory, os._exit): the next Run starts a new one. */
  dead?: boolean;
  /** Restart ended this run. */
  restarted?: boolean;
  /** Interrupt cancelled it before it started. */
  cancelled?: boolean;
  error?: string;
}

/** What a run sends: code (Python, SQL on a connection, or DAX on a dataset), or a file run as Python would run it. */
export interface RunBody {
  code: string;
  /** table: a table's read-only cell (with `table`: it starts from the table as its maker made it).
   *  html: an HTML cell (`code` is its HTML; its names are filled from the kernel). */
  kind?: "code" | "sql" | "dax" | "file" | "table" | "html";
  table?: string;
  connection?: string | null;
  path?: string | null;
  args?: string;
}

/** An item of a run's stream: an output record, or the kernel asking for a line. */
export type RunItem = Output & { input_request?: { prompt: string; password: boolean } };

/** This window, for this page load: its kernels stop a minute after it is gone (closed or reloaded). */
export const WINDOW_ID: string = Math.random().toString(36).slice(2, 12);

/** What START says of a document's session: the project's one (shared), with the words the screen says. */
export interface Session {
  shared: boolean;
  words: string;
  kernel: string | null;
}

/** Every document's Kernel of this window (a project's documents share one session: each is told). */
const all = new Set<Kernel>();

/** A `session_restarted` or `session_ended` notice: every document of that session follows. True when
 *  one of this window's documents was in it. */
export function sessionHeard(notice: { type: string; kernel?: string; python?: string }): boolean {
  let any = false;
  for (const kernel of all) any = kernel.heard(notice) || any;
  return any;
}

export class Kernel {
  id: string | null = null;
  python = "";
  state: "off" | "starting" | "idle" | "busy" = "off";
  /** Runs sent and not yet ended (a second Run waits behind the first). */
  running = 0;
  /** The project's one Python session (every notebook and script of the project runs in it); false: a
   *  kernel of this document's own (a loose file). */
  shared = false;
  /** What Interrupt and Restart mean for a shared session, in the server's words. */
  sessionWords = "";
  /** This document asked for the restart under way (the others are told by the notice). */
  private restarting = false;
  private listeners: (() => void)[] = [];

  /** `project`: a document of a Workbench window (one not saved yet joins the open project's session);
   *  the Widgets window's kernel is always its own. */
  constructor(private readonly path: () => string | null, private readonly chosenPython: () => string | null, private readonly project = false) {
    all.add(this);
  }

  /** Runs under way in this window's other documents of the same shared session. */
  othersRunning(): number {
    if (!this.shared || !this.id) return 0;
    let n = 0;
    for (const other of all) if (other !== this && other.id === this.id) n += other.running;
    return n;
  }

  /** The others of the same session draw again (their status says the session is busy). */
  private tellOthers(): void {
    if (!this.shared || !this.id) return;
    for (const other of all) if (other !== this && other.id === this.id) for (const l of other.listeners) l();
  }

  /** The project's session as the server said it when the document opened: taken at once while it runs
   *  (its variables and completions are live before this document's first Run). */
  join(session: Session | null | undefined, python: string | null): void {
    if (!session?.shared) return;
    this.shared = true;
    this.sessionWords = session.words;
    if (session.kernel && !this.id && this.state === "off") this.adopt(session.kernel, python ?? "");
  }

  heard(notice: { type: string; kernel?: string; python?: string }): boolean {
    if (!this.id || notice.kernel !== this.id) return false;
    if (notice.type === "session_restarted") {
      if (notice.python) this.python = notice.python;
      const mine = this.restarting;
      this.set(this.running ? "busy" : "idle");
      return !mine;
    }
    if (notice.type === "session_ended") {
      this.id = null;
      this.set("off");
      return true;
    }
    return false;
  }

  /** The document closed for good: no notice reaches it any more. */
  forget(): void {
    all.delete(this);
  }

  onState(listener: () => void): void {
    this.listeners.push(listener);
  }

  /** What the editors' intelligence asks with: the kernel once it runs (its live names), the document's
   *  path (its project's modules) and the Python chosen for it (its libraries). */
  intel(): { kernel: string | null; path: string | null; python: string | null } {
    return { kernel: this.state === "idle" ? this.id : null, path: this.path(), python: this.python || this.chosenPython() };
  }

  private set(state: Kernel["state"]): void {
    this.state = state;
    for (const l of this.listeners) l();
  }

  private pending: Promise<string> | null = null;

  /** The kernel's id, started when there is none; two asking while it starts share the one start. */
  ensure(): Promise<string> {
    if (this.id) return Promise.resolve(this.id);
    this.pending ??= this.start().finally(() => {
      this.pending = null;
    });
    return this.pending;
  }

  private async start(): Promise<string> {
    this.set("starting");
    try {
      const started = await api<{ kernel: string; python: string; vaults?: { set: string[]; problems: string[] }; session?: Session | null }>("/workbench/kernels", "POST", { python: this.chosenPython(), path: this.path(), window: WINDOW_ID, project: this.project });
      // A vault that could not be read, or a project's Python that does not run: said, and the code runs.
      problemsHere(started.vaults?.problems ?? [], "The Python session started, with something to know.", { level: "warning" });
      this.id = started.kernel;
      this.python = started.python;
      this.shared = !!started.session?.shared;
      this.sessionWords = started.session?.words ?? "";
      this.set("idle");
      return started.kernel;
    } catch (e) {
      this.set("off");
      throw e;
    }
  }

  /** Run code; each output as it arrives; the run's end. */
  async run(body: RunBody, onOutput: (o: RunItem) => void): Promise<Done> {
    const id = await this.ensure();
    this.running++;
    this.set("busy");
    this.tellOthers();
    try {
      const response = await fetch(`/workbench/kernels/${id}/execute`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        // The document this code runs for: a project's one session runs every document's.
        body: JSON.stringify({ ...body, document: this.path() }),
      });
      if (response.status === 404) {
        this.id = null; // the server restarted or the kernel was stopped: start a new one next time
        throw new ApiError(404, "The kernel was gone: run again.");
      }
      if (!response.ok || !response.body) throw new ApiError(response.status, await response.text());
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = "";
      let done: Done = { ok: false, execution_count: null };
      for (;;) {
        const { value, done: finished } = await reader.read();
        if (value) pending += decoder.decode(value, { stream: true });
        let at: number;
        while ((at = pending.indexOf("\n")) >= 0) {
          const line = pending.slice(0, at).trim();
          pending = pending.slice(at + 1);
          if (!line) continue;
          const item = JSON.parse(line) as RunItem & { done?: Done };
          if (item.done) done = item.done;
          else onOutput(item);
        }
        if (finished) break;
      }
      if (done.dead) this.id = null;
      return done;
    } finally {
      this.running = Math.max(0, this.running - 1);
      this.set(!this.id ? "off" : this.running ? "busy" : "idle");
      this.tellOthers();
    }
  }

  /** The line input() (or getpass, pdb) asked for. */
  async answer(value: string): Promise<void> {
    if (this.id) await api(`/workbench/kernels/${this.id}/input`, "POST", { value });
  }

  /** Whether the console's code is a whole statement yet: "complete", "incomplete" (with the next
   *  line's indent) or "invalid". Before the kernel starts, a guess from the last line. */
  async isComplete(code: string): Promise<{ status: string; indent?: string }> {
    if (this.id && this.state !== "starting") {
      try {
        return await api(`/workbench/kernels/${this.id}/is-complete`, "POST", { code });
      } catch {
        /* the guess below */
      }
    }
    const last = code.trimEnd().split("\n").pop() ?? "";
    const open = (code.match(/[([{]/g)?.length ?? 0) > (code.match(/[)\]}]/g)?.length ?? 0);
    return /[:\\]$/.test(last) || open ? { status: "incomplete", indent: "    " } : { status: "complete" };
  }

  /** The kernel's completions at `offset` (nothing before it has started: typing never starts one). */
  async complete(code: string, offset: number): Promise<{ matches: string[]; start: number; end: number; types: Record<string, string> } | null> {
    if (!this.id || this.state === "starting") return null;
    try {
      return await api(`/workbench/kernels/${this.id}/complete`, "POST", { code, offset });
    } catch {
      return null;
    }
  }

  /** The signature and help of the name at `offset`. */
  async help(code: string, offset: number): Promise<string> {
    if (!this.id || this.state === "starting") return "";
    try {
      return (await api<{ help: string }>(`/workbench/kernels/${this.id}/inspect`, "POST", { code, offset })).help;
    } catch {
      return "";
    }
  }

  async interrupt(): Promise<void> {
    if (this.id) await api(`/workbench/kernels/${this.id}/interrupt`, "POST");
  }

  /** A fresh Python. False: there was no kernel to restart (none has started yet). */
  async restart(): Promise<boolean> {
    if (!this.id) return false;
    this.set("starting");
    this.restarting = true;
    try {
      await api(`/workbench/kernels/${this.id}/restart`, "POST");
    } finally {
      this.restarting = false;
      this.set(this.running ? "busy" : "idle");
    }
    return true;
  }

  /** A running kernel that came with a document from another window: this one's now. */
  adopt(id: string, python: string): void {
    this.id = id;
    this.python = python;
    this.set("idle");
  }

  /** Let go of the kernel without stopping it (its document moved to another window). */
  release(): void {
    this.id = null;
    this.set("off");
  }

  /** Stop it (the document closed). `leaving`: the window is closing, so the request must outlive it.
   *  The project's one session is left running for its other documents (the server keeps it; `session`:
   *  stop it for all of them, the next Run starts a new one). */
  stop(leaving = false, session = false): void {
    if (!this.id) return;
    const id = this.id;
    this.id = null;
    void fetch(`/workbench/kernels/${id}${session ? "?session=1" : ""}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` }, keepalive: leaving }).catch(() => undefined);
    this.set("off");
  }
}

/** Run into an output area: outputs as they come, a box when the code asks for a line, and a plain
 *  word when the run did not end the usual way (the kernel stopped, Restart, Interrupt before it ran). */
export async function runInto(kernel: Kernel, body: RunBody, area: OutputArea): Promise<Done> {
  try {
    const done = await kernel.run(body, (item) => {
      const asked = item.input_request;
      if (asked) area.ask(asked.prompt, asked.password, (value) => kernel.answer(value).catch((e: Error) => area.notice(e.message, "error")));
      else area.add(item);
    });
    area.finish();
    if (done.dead) area.notice("The kernel stopped: every variable is gone.", "error");
    else if (done.restarted) area.notice("Ended by Restart");
    else if (done.cancelled) area.notice("Cancelled");
    return done;
  } catch (e) {
    area.finish();
    area.notice((e as Error).message, "error");
    return { ok: false, execution_count: null, error: (e as Error).message };
  }
}
