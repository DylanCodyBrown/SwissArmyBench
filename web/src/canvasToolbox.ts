/**
 * canvasToolbox.ts: the designer's Toolbox and Document Outline, App mode's panels on a canvas's left (the
 * owner, 2026-11-19: "a canvas as flexible as WinForms and WPF"). [WIRE]
 *
 *   [TOOLBOX]  every Streamlit element and layout container, grouped (Input, Data, Charts, Text, Media,
 *              Layout, Status), with a search box. Drag one onto the page (or into a container), or click it:
 *              an element becomes a named cell of the app notebook and its block; a container is the
 *              canvas's own. The starters and your own components are a click away (the Starters panel)
 *   [OUTLINE]  the page as a tree in reading order (Visual Studio's Document Outline): the containers, their
 *              slots, the blocks. A click selects (Ctrl adds); drag a row onto another to put it before
 *              that one, or onto a slot to move it in; the eye hides it while designing, the pin locks it
 *
 * The lists come from the server (GET /streamlit/toolbox: domain/toolbox.py), so the agent's canvas_toolbox
 * reads the same; every action here is the canvas's own (workbenchCanvas.ts), so the agent's commands do it too.
 */
import { api } from "./api";
import { button, clear, h, icon } from "./dom";
import { errorHere, showError } from "./errorNote";
import { loadingBlock } from "./loading";
import { type CanvasView, TOOLBOX_CONTAINER, TOOLBOX_DRAG } from "./workbenchCanvas";
import type { BlockState, CanvasPage, ContainerState } from "./workbenchStreamlit";

export interface ToolParam {
  name: string;
  type: "text" | "number" | "bool" | "choice" | "list" | "any";
  default: unknown;
  words: string;
  category: string;
  choices: string[];
}

interface Tool {
  params: ToolParam[];
  id: string;
  group: string;
  label: string;
  words: string;
  kind: "element" | "container";
}

interface Catalog {
  groups: string[];
  items: Tool[];
}

const TOOL_ICONS: Record<string, string> = { Input: "sliders", Data: "table", Charts: "chart", Text: "markdown", Media: "image", Layout: "panel", Status: "info" };
const BOX_ICONS: Record<string, string> = { columns: "columns", tabs: "panel", expander: "expand", container: "max", form: "check", sidebar: "right", popover: "popout" };
const BLOCK_DRAG = "application/x-swissarmybench-block";

let catalog: Promise<Catalog> | null = null;
export const readToolbox = (): Promise<Catalog> => (catalog ??= api<Catalog>("/streamlit/toolbox").catch((e: unknown) => {
  catalog = null;
  throw e;
}));

/** The Toolbox, drawn into a panel's body. `starters`: open the Starters panel. */
export function drawToolbox(body: HTMLElement, canvas: () => CanvasView, starters: () => void): void {
  let filter = "";
  const list = h("div", { class: "tb-list" });
  const search = h("input", { type: "search", class: "app-input tb-search", placeholder: "Search the Toolbox", "aria-label": "Search the Toolbox" }) as HTMLInputElement;
  const draw = (found: Catalog): void => {
    const shown = found.items.filter((t) => !filter || `${t.label} ${t.id} ${t.words}`.toLowerCase().includes(filter));
    clear(
      list,
      ...found.groups
        .filter((g) => shown.some((t) => t.group === g))
        .map((g) =>
          h(
            "section",
            { class: "tb-group", "aria-label": g },
            h("h3", { class: "app-heading" }, g),
            h(
              "ul",
              { class: "tb-items", role: "list" },
              ...shown
                .filter((t) => t.group === g)
                .map((t) => {
                  const item = h("button", { type: "button", class: "tb-item", draggable: "true", title: t.words, dataset: { tool: t.id, kind: t.kind } }, icon(t.kind === "container" ? (BOX_ICONS[t.id] ?? "panel") : (TOOL_ICONS[t.group] ?? "page")), h("span", {}, t.label));
                  item.addEventListener("dragstart", (e) => {
                    e.dataTransfer?.setData(TOOLBOX_DRAG, JSON.stringify({ id: t.id, kind: t.kind }));
                    if (t.kind === "container") e.dataTransfer?.setData(TOOLBOX_CONTAINER, "1");
                    if (e.dataTransfer) e.dataTransfer.effectAllowed = "copy";
                  });
                  // A click puts it after the page's last block (or into the selected container).
                  item.addEventListener("click", () => {
                    const into = canvas().selectedContainer();
                    void canvas().addTool(t.id, t.kind, into ? { parent: into.id, slot: 0 } : undefined).catch((e: Error) => errorHere(e, {}, item));
                  });
                  return h("li", {}, item);
                }),
            ),
          ),
        ),
      shown.length ? null : h("p", { class: "hint app-empty" }, `Nothing in the Toolbox is called ${filter}`),
    );
  };
  search.addEventListener("input", () => {
    filter = search.value.trim().toLowerCase();
    void readToolbox().then(draw, () => undefined);
  });
  search.addEventListener("keydown", (e) => e.stopPropagation());
  clear(body, h("div", { class: "tb" }, search, list, button("Starters and your components", () => starters(), { icon: "star", class: "ghost tb-starters" })));
  clear(list, loadingBlock("Reading the Toolbox…"));
  void readToolbox().then(draw, (e: unknown) => showError(list, e));
}

/** The Document Outline of the page in front, drawn into a panel's body. */
export function drawOutline(body: HTMLElement, canvas: () => CanvasView): void {
  const c = canvas();
  const page = c.page();
  if (!page || (!page.blocks.length && !page.containers.length)) return void clear(body, h("p", { class: "hint app-empty" }, "The page has no blocks yet"));
  const blocks = new Map(page.blocks.map((b) => [b.id, b]));
  const boxes = new Map(page.containers.map((b) => [b.id, b]));
  const selected = new Set(c.selectedIds());
  const change = (id: string, change: Record<string, unknown>): void => void c.changeBlock(id, change);

  const drop = (target: HTMLElement, into: (dragged: string) => Record<string, unknown> | null): void => {
    target.addEventListener("dragover", (e) => {
      if (!e.dataTransfer?.types.includes(BLOCK_DRAG)) return;
      e.preventDefault();
      e.stopPropagation();
      target.classList.add("ol-over");
    });
    target.addEventListener("dragleave", () => target.classList.remove("ol-over"));
    target.addEventListener("drop", (e) => {
      const raw = e.dataTransfer?.getData(BLOCK_DRAG);
      target.classList.remove("ol-over");
      if (!raw) return;
      e.preventDefault();
      e.stopPropagation();
      const dragged = (JSON.parse(raw) as { block: string }).block;
      const body = into(dragged);
      if (body) change(dragged, body);
    });
  };

  const node = (item: BlockState | ContainerState, depth: number): HTMLElement[] => {
    const box = boxes.get(item.id) ?? null;
    const title = box ? box.title : ((item as BlockState).name ?? (item as BlockState).where);
    const row = h(
      "div",
      { class: `ol-row${selected.has(item.id) ? " selected" : ""}${item.hidden ? " hidden-item" : ""}`, role: "treeitem", "aria-level": depth + 1, "aria-selected": String(selected.has(item.id)), tabindex: 0, draggable: String(!item.locked && box?.kind !== "sidebar"), dataset: { item: item.id }, style: { paddingLeft: `${8 + depth * 14}px` } },
      icon(box ? (BOX_ICONS[box.kind] ?? "panel") : "page"),
      h("span", { class: "ol-title" }, title),
      h("span", { class: "spacer" }),
      button(item.hidden ? `Show ${title}` : `Hide ${title} while designing`, (e) => {
        e.stopPropagation();
        change(item.id, { hidden: !item.hidden });
      }, { icon: "eye", iconOnly: true, class: `ghost ol-eye${item.hidden ? " off" : ""}` }),
      button(item.locked ? `Unlock ${title}` : `Lock ${title}`, (e) => {
        e.stopPropagation();
        change(item.id, { locked: !item.locked });
      }, { icon: "pin", iconOnly: true, class: `ghost ol-lock${item.locked ? " on" : ""}` }),
    );
    const pick = (e: MouseEvent | KeyboardEvent): void => {
      if (e.ctrlKey || e.metaKey || e.shiftKey) c.selectMany(selected.has(item.id) ? [...selected].filter((s) => s !== item.id) : [...selected, item.id]);
      else c.select(item.id);
    };
    row.addEventListener("click", pick);
    row.addEventListener("keydown", (e) => {
      if (e.target !== row) return;
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        pick(e);
      } else if (e.key === "Delete") {
        c.select(item.id);
        void c.removeSelected();
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const rows = [...body.querySelectorAll<HTMLElement>(".ol-row")];
        rows[rows.indexOf(row) + (e.key === "ArrowDown" ? 1 : -1)]?.focus();
      }
    });
    row.addEventListener("dragstart", (e) => {
      e.dataTransfer?.setData(BLOCK_DRAG, JSON.stringify({ block: item.id, w: item.w }));
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
    });
    // Dropped on a row: before it, in its grid.
    drop(row, (dragged) => (dragged === item.id ? null : { parent: item.parent, slot: item.slot, row: item.row, column: 1, insert: true }));
    if (!box) return [row];
    const inside = Array.from({ length: box.slots }, (_, slot) => {
      const held = grid(page, `${box.id}:${slot}`, depth + (box.slots > 1 ? 2 : 1));
      if (box.slots === 1) return held.length ? held : [slotRow(box, slot, depth + 1, "Drop a block here")];
      return [slotRow(box, slot, depth + 1, box.slot_names[slot] ?? `Slot ${slot + 1}`), ...held];
    }).flat();
    return [row, ...inside];
  };

  const slotRow = (box: ContainerState, slot: number, depth: number, label: string): HTMLElement => {
    const row = h("div", { class: "ol-slot hint", dataset: { slot: `${box.id}:${slot}` }, style: { paddingLeft: `${8 + depth * 14}px` } }, label);
    drop(row, (dragged) => (dragged === box.id ? null : { parent: box.id, slot }));
    return row;
  };

  function grid(p: CanvasPage, key: string, depth: number): HTMLElement[] {
    return (p.grids[key] ?? []).flat().flatMap((id) => {
      const item = blocks.get(id) ?? boxes.get(id);
      return item ? node(item, depth) : [];
    });
  }

  const bar = page.containers.find((b) => b.kind === "sidebar");
  const top = h("div", { class: "ol-slot ol-page hint", dataset: { slot: "" } }, page.name);
  drop(top, () => ({ parent: null }));
  clear(body, h("div", { class: "ol", role: "tree", "aria-label": `Outline of ${page.name}` }, top, ...grid(page, "", 1), ...(bar ? node(bar, 1) : [])));
}
