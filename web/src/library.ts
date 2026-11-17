/**
 * library.ts: the library (Plans/library.plan.md: connections, APIs, vaults, blades, relationship sets, variables and
 * colours in one folder made to be a Git repository, whatever project is open). [SHARED]
 *
 *   [SETTINGS]  Settings' Library: where the folder is, Change… (a folder: a clone of a team's library) and
 *               Default, what is in it, that it is made to be a Git repository and what never goes in
 *   [NOTICES]   the move into the library said once: this computer's older stores (taken at page load) and
 *               an older project's own blades (the library_notice notice)
 *
 * ROUTING: GET/PUT /library · POST /library/notices · notices library_changed, library_notice
 */
import { api, onNotice } from "./api";
import { button, h, icon, toast } from "./dom";
import { chooseFile } from "./fileChooser";

interface Info {
  folder: string;
  default: string;
  is_default: boolean;
  git: boolean;
  counts: Record<string, number>;
  local: string[];
  never: string[];
}

const COUNT_WORDS: [string, string][] = [
  ["connections", "connections"],
  ["vaults", "key vaults"],
  ["apis", "APIs"],
  ["blades", "blades"],
  ["relationship_sets", "relationship sets"],
];

/** Settings' Library section. */
export function librarySection(): HTMLElement {
  const body = h("div", { class: "library-settings" });
  const draw = async (): Promise<void> => {
    let info: Info;
    try {
      info = await api<Info>("/library");
    } catch (e) {
      body.replaceChildren(h("p", { class: "status-error" }, (e as Error).message));
      return;
    }
    const use = (folder: string | null): void =>
      void api<Info>("/library", "PUT", { folder }).then(
        () => {
          toast(folder ? `The library is ${folder} now.` : "The library is the default folder now.");
          void draw();
        },
        (e: Error) => toast(e.message, "error"),
      );
    const counts = COUNT_WORDS.map(([key, words]) => `${info.counts[key] ?? 0} ${words}`).join(" · ");
    body.replaceChildren(
      h("p", { class: "library-folder" }, h("code", { class: "mono" }, info.folder), info.git ? h("span", { class: "chip" }, "Git") : null),
      h("p", { class: "hint library-counts" }, counts),
      h(
        "div",
        { class: "row" },
        button("Change…", () => void chooseFile({ title: "The library folder", mode: "folder", start: info.folder }).then((f) => f && use(f)), { icon: "folder" }),
        info.is_default ? null : button("Default", () => use(null), { class: "ghost", title: info.default }),
      ),
      h("p", { class: "hint" }, "A Git repository's working copy: commit and push it with your own tools. Never in it: ", info.never.join(", "), ". This computer only: local/ and the keyring."),
    );
  };
  void draw();
  onNotice((n) => {
    if (n.type === "library_changed" && body.isConnected) void draw();
  });
  return h("fieldset", { class: "fieldset library-fieldset" }, h("legend", {}, icon("folder"), "Library"), body);
}

let listening = false;

/** The move into the library, said once on this page: what the server kept for it, and what comes. */
export function libraryNotices(): void {
  if (listening) return;
  listening = true;
  onNotice((n) => {
    const text = (n as { text?: string }).text;
    if (n.type === "library_notice" && text) toast(text);
  });
  void api<{ notices: { text: string }[] }>("/library/notices", "POST").then(
    (r) => r.notices.forEach((n) => toast(n.text)),
    () => undefined,
  );
}
