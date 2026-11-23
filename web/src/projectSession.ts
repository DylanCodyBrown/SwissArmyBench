/**
 * projectSession.ts: one Python per project, as the pages say it. [WIRE + FUNCTION]
 *
 * The owner, 2026-11-21 (Plans/environment.plan.md, step 4): every notebook and script of the open project
 * runs in ONE Python session, in the project's own `.venv` (made by the app in the background as a project
 * is made or opened; the app's own Python runs the code until it is ready). The rules and every word are
 * the server's (domain/project_python.py); this module only holds what it last said and says it.
 *
 * ROUTING: GET  /environment/python                       the state below
 *          POST /environment/python {make: true}          make the project's .venv now (Try again)
 *          POST /environment/python {offer, add}          a notebook's older environment: add its libraries, or not
 *          notice project_python {status, words, said?}   the making started, ended or failed; a project changed
 *
 *   loadProjectPython   ask the server (a page's start, and after a notice)
 *   projectPython       what it last said (null: not asked yet)
 *   inProject           whether a document is the open project's (one not saved yet is, in a project)
 *   heardProjectPython  a notice taken: the state, and its one line as a toast (once a window)
 *   projectPythonNotices  the same for a page with no handler of its own (the home page)
 *   pythonLine          the Environment's line: the state's words, Make it now / Try again, the session's words
 *   offerMoved          the one line when a notebook that had its own environment opens: Add them, Not now
 */
import { api, onNotice } from "./api";
import { button, h, toast, toastNode } from "./dom";
import { errorHere } from "./errorNote";
import { busyClick } from "./loading";

export interface Offer {
  document: string;
  libraries: string[];
  words: string;
}

export interface ProjectPython {
  /** none (no project open), making, ready, missing, failed. */
  status: "none" | "making" | "ready" | "missing" | "failed";
  words: string;
  python: string;
  version?: string;
  own: boolean;
  problem: string | null;
  /** The one session's words (a project only): what Interrupt and Restart mean for every document. */
  session: string | null;
  /** The open project's folder, and its session's kernel while it runs. */
  folder: string | null;
  kernel: string | null;
  offers: Offer[];
}

let state: ProjectPython | null = null;

export const projectPython = (): ProjectPython | null => state;

export async function loadProjectPython(): Promise<ProjectPython | null> {
  try {
    state = await api<ProjectPython>("/environment/python");
  } catch {
    state = null; // an older server, or one stopping: every document keeps a session of its own
  }
  return state;
}

const plain = (path: string): string => path.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();

/** Whether a document is the open project's: its file is inside the project's folder; one not saved yet
 *  is, while a project is open. The server decides the same way when the session starts. */
export function inProject(path: string | null): boolean {
  const folder = state?.folder;
  if (!folder) return false;
  if (!path) return true;
  return plain(path).startsWith(plain(folder) + "/");
}

/** A `project_python` notice: the state as it is now, its one line said once in this window. */
export function heardProjectPython(notice: { type: string; said?: string | null } & Partial<ProjectPython>): boolean {
  if (notice.type !== "project_python") return false;
  const { type: _type, said, ...rest } = notice;
  state = { ...(state ?? { offers: [], folder: null, kernel: null, session: null, problem: null, own: false, python: "", words: "", status: "none" }), ...rest } as ProjectPython;
  if (said) toast(said);
  return true;
}

let listening = false;

/** A page that is not the Workbench says the project's Python's one line too (the home page: New project,
 *  Open project), and keeps the state for whoever asks. */
export function projectPythonNotices(): void {
  if (listening) return;
  listening = true;
  onNotice((n) => void heardProjectPython(n as unknown as { type: string }));
}

const make = async (): Promise<void> => {
  state = await api<ProjectPython>("/environment/python", "POST", { make: true });
};

/** The Environment's line about the project's Python: what it is now, the one button when there is
 *  something to do, and what one session means. Nothing with no project open. */
export function pythonLine(python: ProjectPython, then: () => void): HTMLElement | null {
  if (python.status === "none" || !python.status) return null;
  const line = h("div", { class: `env-project-python ${python.status}`, role: "status" });
  line.append(h("span", { class: "env-project-python-words", title: python.problem ?? python.python }, python.words));
  if (python.status === "missing" || python.status === "failed") {
    line.append(
      button(python.status === "failed" ? "Try again" : "Make it now", busyClick("Starting…", (b) => make().then(then, (e: Error) => errorHere(e, {}, b))), { class: "line env-make-python", title: "Makes .venv in the project's folder with the libraries requirements.txt names" }),
    );
  }
  if (python.session) line.append(h("span", { class: "env-project-session", title: python.session }, "One Python session for the whole project"));
  return line;
}

/** A notebook's older environment answered: its libraries installed into the project's Python and written
 *  to requirements.txt (through the server's one install), or left (Not now). */
export async function answerOffer(offer: Offer, add: boolean): Promise<void> {
  state = await api<ProjectPython>("/environment/python", "POST", { offer: offer.document, add });
}

/** An offer's row: its one line, Add them, Not now. */
export function offerRow(offer: Offer, then: () => void): HTMLElement {
  const row = h("div", { class: "env-offer", role: "note" }, h("span", {}, offer.words));
  if (offer.libraries.length) {
    row.append(
      button(
        offer.libraries.length === 1 ? "Add it" : "Add them",
        busyClick("Installing…", (b) => answerOffer(offer, true).then(then, (e: Error) => errorHere(e, {}, b))),
        { class: "line env-offer-add", title: `Installs ${offer.libraries.join(", ")} into the project's Python and adds them to requirements.txt` }
      ),
      button("Not now", (event) => void answerOffer(offer, false).then(then, (e: Error) => errorHere(e, {}, event.currentTarget as HTMLElement)), { class: "ghost env-offer-skip" }),
    );
  }
  return row;
}

/** The one line when a notebook that had its own environment opens in a project (the server read it once). */
export function offerMoved(offer: Offer | null | undefined): void {
  if (!offer) return;
  if (!offer.libraries.length) {
    toast(offer.words);
    return;
  }
  const note = offerRow(offer, () => item.remove());
  note.classList.add("toast-offer");
  const item = toastNode(note, `offer:${offer.document}`, 60000);
}
