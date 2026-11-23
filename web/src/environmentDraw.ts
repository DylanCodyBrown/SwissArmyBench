/**
 * environmentDraw.ts: the Environment drawn from its state record (environmentState.ts): the tabs with their
 * counts, the session line and the project's Python, the tools of the tab, the list's rows (a row unfolds in
 * place; the match marked; the place kept), the line naming the other tabs that match, and the viewer (the
 * row's facts, every place that uses it, its actions, the keys). Pulled out of environmentPage.ts's
 * mountEnvironment (the craft review of 2026-11-22, refactor 8). [VIEW]
 */
import { button, h, icon, plural } from "./dom";
import { actionsOf, addSetting, clearDialog, follow, installDialog, openItem, rowMenu, updateAll } from "./environmentActions";
import { columnsMenu, shownColumns } from "./environmentColumns";
import { select, setFolded, setTab, toggle, load } from "./environmentMoves";
import { emptyWords, type Item, KINDS, pythonWords, TAB_WORDS, USED_WORDS } from "./environmentRules";
import { type Column, type Environment, find, isOpen, items, kidsOf, kindMark, marked } from "./environmentState";
import { emptyState } from "./emptyState";
import { errorNote } from "./errorNote";
import { loadingBlock } from "./loading";
import { visit, withParams } from "./nav";
import { offerRow, pythonLine } from "./projectSession";

/** Draw the whole Environment again (the page's `env.act.draw`). */
export function draw(env: Environment): void {
  if (env.disposed) return;
  drawTabs(env);
  drawSession(env);
  drawTools(env);
  const { list, listing } = env;
  if (env.failed && !listing) {
    list.replaceChildren(errorNote(env.failed));
    env.viewer.replaceChildren();
    return;
  }
  if (!listing) {
    list.replaceChildren(loadingBlock("Loading the environment…"));
    return;
  }
  const columns = shownColumns(env, env.tab);
  list.style.setProperty("--env-cols", ["18px", env.compact ? "minmax(120px,1.2fr)" : "minmax(170px,1.3fr)", ...columns.map((c) => (env.compact ? "minmax(70px,1fr)" : c.width)), "30px"].join(" "));
  const shown = items(env);
  if (!find(env, env.selected) || find(env, env.selected)?.kind !== env.tab) env.selected = shown[0]?.id ?? null;
  const top = list.scrollTop;
  const focused = list.contains(document.activeElement);
  const head = h(
    "div",
    { class: "env-head", role: "presentation", oncontextmenu: (e: MouseEvent) => (e.preventDefault(), columnsMenu(env, e.currentTarget as HTMLElement)) },
    h("span", {}),
    h("span", {}, "Name"),
    ...columns.map((c) => h("span", {}, c.head)),
    env.compact ? h("span", {}) : h("button", { type: "button", class: "env-columns", "aria-label": "Columns", title: "Show or hide columns", onclick: (e: MouseEvent) => columnsMenu(env, e.currentTarget as HTMLElement) }, icon("more")),
  );
  const rows = shown.flatMap((item) => row(env, item, columns));
  list.replaceChildren(head, ...(rows.length ? rows : [emptyRow(env)]));
  list.scrollTop = top;
  if (focused) list.querySelector<HTMLElement>(".env-row.sel")?.focus({ preventScroll: true });
  const others = KINDS.filter((k) => k !== env.tab && (listing.counts[k] ?? 0) > 0);
  env.hint.replaceChildren(
    ...(env.query && others.length
      ? ["Also matches in ", ...others.flatMap((k, i) => [i ? ", " : "", h("button", { type: "button", class: "env-link", "data-go": k, onclick: () => setTab(env, k) }, `${TAB_WORDS[k]} (${listing.counts[k] ?? 0})`)])]
      : []),
  );
  drawViewer(env);
  env.element.classList.toggle("env-folded", env.folded);
}

function drawTabs(env: Environment): void {
  env.tabs.replaceChildren(
    ...KINDS.map((kind) => {
      const count = env.listing?.counts[kind] ?? 0;
      return h(
        "button",
        { type: "button", class: "env-tab", role: "tab", "data-kind": kind, "aria-selected": String(kind === env.tab), tabindex: kind === env.tab ? 0 : -1, onclick: () => setTab(env, kind) },
        TAB_WORDS[kind],
        h("i", { class: env.query && count ? "hot" : "", "data-count": kind }, String(count)),
      );
    }),
  );
}

function drawSession(env: Environment): void {
  const { listing } = env;
  // One Python per project (projectSession.ts): on the Libraries tab, its .venv as it is made, Try again
  // and what one session means; on every tab, a notebook's older environment offered until answered.
  const project = listing && env.tab === "library" ? pythonLine(listing.python, () => void load(env)) : null;
  env.projectHost.replaceChildren(...(project ? [project] : []), ...(listing?.python.offers ?? []).map((o) => offerRow(o, () => void load(env))));
  // The key vaults, on the Settings and secrets tab (they give settings; keyVaults.ts).
  env.vaults.element.hidden = env.tab !== "setting";
  if (!listing || env.compact) {
    env.session.replaceChildren();
    return;
  }
  const python = listing.python;
  env.session.replaceChildren(
    h("span", { class: "env-python", title: python.python }, pythonWords(python, listing.project)),
    h("span", {}, `tables in memory ${listing.memory} · nothing is saved unless you tick Keep`),
    h("span", { class: "env-grow" }),
    h("span", {}, "Updates by itself as your code runs · tables are added on the ", h("button", { type: "button", class: "env-link", onclick: () => visit(withParams({ open: "connections", at: null, type: null, name: null })) }, "Connections"), " page"),
  );
}

function drawTools(env: Environment): void {
  const made: HTMLElement[] = [];
  if (env.tab === "library") {
    const outdated = items(env, "library").filter((i) => i.latest && !i.pinned);
    if (outdated.length) made.push(button(`Update all not pinned (${outdated.length})`, () => updateAll(env, outdated), { class: "env-update-all" }));
    made.push(button("Install a library…", () => installDialog(env), { icon: "import", class: "primary env-install", title: "Installs into the project's environment and adds it to requirements.txt" }));
  }
  if (env.tab === "structure") {
    // New, Open and Paste are the Structures viewer's own (the page a structure's row opens into).
    made.push(button("New, open or paste…", () => void import("./structuresPage").then((m) => m.openStructures()), { icon: "plus", class: "env-structures" }));
  }
  if (env.tab === "setting") {
    // A key vault gives settings: added here, listed above the settings (keyVaults.ts).
    made.push(button("Add key vault", () => void env.vaults.add(), { icon: "key", class: "variables-add-vault" }));
    made.push(button("Add a setting…", () => addSetting(env), { icon: "plus", class: "primary env-add-setting" }));
  }
  if (!env.options.actions) made.push(button("Clear…", () => void clearDialog(env), { class: "ghost env-clear", title: "Clear what is not kept…" }));
  env.tools.replaceChildren(...made);
}

/** A row and, unfolded, its inner lines (only the ones a search matched inside). */
function row(env: Environment, item: Item, columns: Column[]): HTMLElement[] {
  const { query, selected } = env;
  const open = isOpen(env, item);
  const kids = kidsOf(env, item);
  const unfolds = kids.length > 0;
  const inside = Boolean(query && item.match && !item.match.own);
  const name = h(
    "span",
    { class: "env-name" },
    kindMark(item),
    h("span", {}, marked(item.name, query)),
    ...item.tags.map((t) => h("span", { class: `env-tag${t === "Keep" ? " env-tag-keep" : ""}` }, t)),
    inside ? h("span", { class: "env-why" }, "matched inside") : null,
  );
  const twist = h("span", { class: "env-twist", "data-twist": item.id, "aria-hidden": "true", onclick: (e: MouseEvent) => (e.stopPropagation(), toggle(env, item)) }, unfolds ? (open ? "▾" : "▸") : "");
  const more = h("button", { type: "button", class: "env-more", "aria-label": `Actions for ${item.name}`, title: "Actions", onclick: (e: MouseEvent) => (e.stopPropagation(), select(env, item.id), rowMenu(env, item, e.currentTarget as HTMLElement)) }, icon("more"));
  const main = h(
    "div",
    {
      class: `env-row${selected === item.id ? " sel" : ""}`,
      role: "treeitem",
      tabindex: selected === item.id ? 0 : -1,
      "aria-selected": String(selected === item.id),
      "aria-level": "1",
      "data-id": item.id,
      "data-name": item.name,
      onclick: () => select(env, item.id),
      ondblclick: () => void openItem(env, item),
    },
    twist,
    name,
    ...columns.map((c) => c.cell(item)),
    more,
  );
  if (unfolds) main.setAttribute("aria-expanded", String(open));
  const out = [main];
  if (open) {
    const wanted = query && item.match && !item.match.own ? new Set(item.match.kids) : null;
    kids.forEach((kid, i) => {
      if (wanted && !wanted.has(i)) return;
      out.push(
        h(
          "div",
          { class: "env-row env-child", role: "treeitem", "aria-level": "2", "data-parent": item.id },
          h("span", {}),
          h("span", { class: "env-name" }, h("span", {}, marked(kid[0], query))),
          h("span", { class: "env-type" }, marked(kid[1], query)),
          h("span", { class: "env-val", style: { gridColumn: `span ${Math.max(1, columns.length - 1)}` } }, marked(kid[2], query)),
          h("span", {}),
        ),
      );
    });
    if (item.more_kids) out.push(h("div", { class: "env-row env-child env-more-kids" }, h("span", {}), h("span", { class: "env-none", style: { gridColumn: `span ${columns.length + 1}` } }, `and ${plural(item.more_kids, "more", "more")}`), h("span", {})));
  }
  return out;
}

/** An empty tab: one line; an empty Settings and secrets tab leads somewhere (emptyState.ts). */
function emptyRow(env: Environment): HTMLElement {
  if (env.tab === "setting" && !env.query) {
    return emptyState({ icon: "variables", line: "A setting is a value typed once, such as a server's name or a password, then written ${NAME} in any box.", action: { label: "Add a setting…", icon: "plus", run: () => addSetting(env) }, sample: false });
  }
  return h("div", { class: "env-empty" }, emptyWords(env.tab, env.query));
}

// ===== the viewer =====

function drawViewer(env: Environment): void {
  const { viewer, folded } = env;
  const item = find(env, env.selected);
  const fold = button(folded ? "Show the viewer" : "Hide the viewer", () => setFolded(env, !folded), { icon: "panel", iconOnly: true, class: "ghost env-fold", title: folded ? "Show the viewer (Ctrl+B)" : "Hide the viewer (Ctrl+B)" });
  if (folded) {
    viewer.replaceChildren(fold);
    return;
  }
  if (!item) {
    viewer.replaceChildren(h("h2", { class: "env-side-title" }, h("span", {}, "Select a row"), fold), h("div", { class: "env-side-part env-keys" }, "Click a row, or use the keys below."), keysHelp());
    return;
  }
  const actions = actionsOf(env, item);
  const used = item.used.length
    ? h(
        "ul",
        { class: "env-used", "aria-label": "Used in" },
        ...item.used.map((u) => h("li", {}, h("span", { class: "env-tag" }, USED_WORDS[u.kind] ?? u.kind), h("button", { type: "button", class: "env-link", "data-used-kind": u.kind, title: "Go there", onclick: () => follow(env, u) }, u.words))),
      )
    : h("span", { class: "env-keys" }, item.kind === "library" ? "Not imported yet." : "Not used anywhere yet.");
  const python = item.kind === "table" && item.in_python ? (h("input", { type: "checkbox", class: "env-python-too" }) as HTMLInputElement) : null;
  env.pythonTick = python;
  viewer.replaceChildren(
    h("h2", { class: "env-side-title" }, h("span", { class: "env-side-name" }, item.name), h("span", { class: "env-tag" }, item.type), fold),
    h(
      "div",
      { class: "env-side-part" },
      h("div", { class: "env-kv" }, h("span", {}, item.kind === "library" ? "Version" : "Size"), h("span", {}, item.size || "—"), h("span", {}, item.kind === "setting" ? "Comes from" : item.kind === "structure" ? "File" : "From"), h("span", {}, item.from || "—")),
      h("b", {}, `${item.kind === "library" ? "Imported in" : "Used in"} ${plural(item.used.length, "place")}`),
      used,
      item.kind === "table" ? h("span", { class: "env-keys" }, item.grids.length ? "Its grids are views of this one table: no copies." : item.open ? "Not shown in a grid yet: Open in Grids makes a view, not a copy." : "It is in Python only: no grid shows it yet.") : null,
      h("div", { class: "env-actions" }, ...actions.map((a) => button(a.label, a.run, { class: a.primary ? "primary small" : "small", icon: a.icon }))),
      python ? h("label", { class: "env-keys env-python-label" }, python, " Also delete it in Python (Remove)") : null,
    ),
    keysHelp(),
  );
}

const keysHelp = (): HTMLElement =>
  h(
    "div",
    { class: "env-side-part env-keys" },
    h("kbd", {}, "↑"), " ", h("kbd", {}, "↓"), " move · ",
    h("kbd", {}, "→"), " open a level · ",
    h("kbd", {}, "←"), " close · ",
    h("kbd", {}, "Enter"), " open it · ",
    h("kbd", {}, "F2"), " rename · ",
    h("kbd", {}, "Del"), " remove · ",
    h("kbd", {}, "/"), " search",
  );
