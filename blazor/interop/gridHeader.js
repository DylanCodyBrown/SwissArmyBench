// gridHeader.js: the grid's own column header and its corner (the classic gridView.ts StatsHeader and CornerHeader,
// headerCard.ts), imported by agGrid.js.
//
//   the header  the name (a click selects the column, Shift extends, Ctrl adds; a double-click renames it in place;
//               a right-click its menu), the sort button (↑ ↓ ⇅, a number when several keys; Shift+click adds a
//               key), and, with Column profiles in the headers on, its distinct count, blank share and a tiny
//               histogram. Resting on it a moment shows its card: type, blanks, distinct, range, mean, a small
//               picture of its values, the three most common.
//   the corner  Select all (Ctrl+A), and the switch for the column profiles in the headers (remembered).

const HOVER_MS = 450;
const PROFILES_KEY = "sab.blazor.headerProfiles";

/** Whether the headers show the column profiles (this browser's choice). */
export function profilesOn() {
  try {
    return localStorage.getItem(PROFILES_KEY) === "1";
  } catch {
    return false;
  }
}

function setProfiles(on) {
  try {
    localStorage.setItem(PROFILES_KEY, on ? "1" : "0");
  } catch {
    /* storage blocked: this page only */
  }
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}

const count = (n) => Number(n ?? 0).toLocaleString();
const number = (v) => (typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) < 1 && v !== 0 ? 4 : 2 }) : String(v ?? ""));
const LABEL_WORDS = new Set(["year", "yr", "fy", "id", "key", "code", "zip", "postcode", "sku"]);

/** A year or an identifier: its digits, not 2,018. */
function isLabelColumn(column, low, high) {
  const words = column.replace(/([a-z0-9])([A-Z])/g, "$1 $2").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  if (words.some((w) => LABEL_WORDS.has(w) || w.endsWith("year"))) return true;
  const yearish = (v) => typeof v === "number" && Number.isInteger(v) && v >= 1800 && v <= 2200;
  return yearish(low) && yearish(high);
}
const plain = (v) => (typeof v === "number" ? (Number.isInteger(v) ? String(v) : String(Number(v.toFixed(2)))) : String(v ?? ""));

// ===== the card on resting over a header =====

let card = null;
let timer = 0;
let hovered = null;

export function hideCard() {
  window.clearTimeout(timer);
  hovered = null;
  card?.remove();
  card = null;
}

for (const type of ["scroll", "wheel", "keydown"]) document.addEventListener(type, hideCard, { capture: true, passive: true });

function bars(counts) {
  const top = Math.max(0, ...counts);
  if (!counts.length || !top) return null;
  return el("div", { class: "header-card-bars", "aria-hidden": "true" }, ...counts.map((n) => el("span", { style: `height: ${Math.max(n ? 6 : 0, (100 * n) / top)}%` })));
}

function line(label, value) {
  return el("div", { class: "header-card-line" }, el("span", { text: label }), el("strong", { text: value }));
}

function drawCard(p) {
  const lines = [
    line("Blank", p.blanks ? `${count(p.blanks)} (${p.blank_percent}%)` : "none"),
    line("Distinct", `${count(p.distinct)}${p.all_unique ? " · every row different" : ""}`),
  ];
  let picture = null;
  if (p.family === "number") {
    const label = isLabelColumn(p.column, p.min, p.max);
    const value = (v) => (label ? plain(v) : number(v));
    lines.push(line("Range", `${value(p.min)} to ${value(p.max)}`));
    if (p.mean != null) lines.push(line("Mean", number(p.mean)));
    picture = bars((p.histogram ?? []).map((b) => b.count));
  } else if (p.family === "date" || p.family === "timestamp") {
    if (p.earliest != null) lines.push(line("Range", `${p.earliest} to ${p.latest}`));
    picture = bars((p.by_month ?? []).map((m) => m.count));
  } else if (p.family === "text" && p.shortest != null) {
    lines.push(line("Length", p.shortest === p.longest ? `${p.shortest}` : `${p.shortest} to ${p.longest}`));
  }
  const common = p.family === "number" || !p.top_values.length || p.all_unique
    ? null
    : el("ol", { class: "header-card-top" }, ...p.top_values.slice(0, 3).map((t) => el("li", {}, el("span", { text: t.value === null ? "(blank)" : String(t.value) }), el("span", { class: "hint", text: count(t.count) }))));
  return el("div", { class: "header-card", role: "tooltip" }, el("div", { class: "header-card-head" }, el("strong", { text: p.column }), el("span", { class: "hint", text: String(p.type).toLowerCase() })), ...lines, picture, common);
}

/** The pointer rests on a header: after a moment, its card (not while a button is held: a drag selects). */
function hover(header, column, own, buttons) {
  hideCard();
  if (buttons) return;
  hovered = header;
  timer = window.setTimeout(() => {
    own.profile(column)
      .then((p) => {
        if (hovered !== header || !header.isConnected) return;
        card = drawCard(p);
        card.style.left = "-9999px";
        document.body.append(card);
        const box = (header.closest(".ag-header-cell") ?? header).getBoundingClientRect();
        card.style.left = `${Math.max(8, Math.min(box.left, window.innerWidth - card.offsetWidth - 8))}px`;
        card.style.top = `${box.bottom + 4}px`;
      })
      .catch(() => undefined);
  }, HOVER_MS);
}

// ===== the header =====

export class Header {
  init(params) {
    const name = params.column.getColId();
    const own = params.sab;
    this.own = own;
    this.params = params;
    this.element = el("div", { class: "sab-header", "aria-label": `${name} (${params.type ?? ""})` });
    const label = el("span", { class: "sab-header-name", text: params.displayName });
    this.label = label;
    this.element.addEventListener("mousedown", (event) => {
      hideCard();
      if (event.button !== 0 || event.target.closest("button, input")) return;
      own.headerDown(name, event);
    });
    this.element.addEventListener("mouseenter", (event) => hover(this.element, name, own, event.buttons));
    this.element.addEventListener("mouseleave", hideCard);
    this.element.addEventListener("dblclick", (event) => {
      if (!event.target.closest("button")) this.rename();
    });
    this.element.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      own.headerMenu(name, event);
    });
    const sort = el("button", { type: "button", class: "sab-header-sort", title: `Sort by ${name} (Shift+click adds a key)`, "aria-label": `Sort by ${name}` });
    this.sort = sort;
    sort.addEventListener("click", (event) => {
      event.stopPropagation();
      params.progressSort(event.shiftKey);
    });
    const top = el("div", { class: "sab-header-top" }, label, sort);
    this.element.append(top);
    if (profilesOn()) {
      const stats = own.stats[name];
      this.element.append(el("div", { class: "sab-header-stats", text: stats ? `${count(stats.distinct)} distinct · ${stats.blank_percent}% blank` : " " }));
      const spark = own.sparks[name];
      this.element.append(spark ? el("div", { class: "sab-header-spark", "aria-hidden": "true" }, ...spark.map((v) => el("span", { style: `height: ${v}%` }))) : el("div", { class: "sab-header-spark-empty", "aria-hidden": "true" }));
    }
    this.drawSort = () => {
      const now = params.column.getSort();
      const index = params.column.getSortIndex();
      const many = own.sortedCount() > 1;
      sort.textContent = now === "asc" ? `↑${many && index != null ? index + 1 : ""}` : now === "desc" ? `↓${many && index != null ? index + 1 : ""}` : "⇅";
      sort.classList.toggle("active", Boolean(now));
      this.element.setAttribute("aria-sort", now === "asc" ? "ascending" : now === "desc" ? "descending" : "none");
    };
    this.drawSort();
    params.column.addEventListener("sortChanged", this.drawSort);
    // The whole header cell is marked (the element is put in it after init: marked again on the next frame).
    this.mark = () => (this.element.closest(".ag-header-cell") ?? this.element).classList.toggle("col-selected", own.columnSelected(name));
    own.marks.add(this.mark);
    requestAnimationFrame(this.mark);
  }

  /** The name becomes a box; the new name is a rename step. Enter keeps it, Escape leaves it, a click away keeps. */
  rename() {
    const name = this.params.column.getColId();
    if (this.label.querySelector("input")) return;
    const box = el("input", { type: "text", class: "sab-header-rename", value: name, "aria-label": `New name for ${name}`, spellcheck: "false" });
    let done = false;
    const finish = (keep) => {
      if (done) return;
      done = true;
      const next = box.value.trim();
      this.label.replaceChildren(this.params.displayName);
      if (keep && next && next !== name) this.own.renamed(name, next);
    };
    box.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") finish(true);
      else if (e.key === "Escape") finish(false);
    });
    box.addEventListener("blur", () => finish(true));
    box.addEventListener("mousedown", (e) => e.stopPropagation());
    this.label.replaceChildren(box);
    box.focus();
    box.select();
  }

  getGui() {
    return this.element;
  }

  refresh() {
    return false;
  }

  destroy() {
    this.params.column.removeEventListener("sortChanged", this.drawSort);
    this.own.marks.delete(this.mark);
  }
}

/** The corner above the row numbers: the switch for column profiles in the headers, and Select all. */
export class Corner {
  init(params) {
    const own = params.sab;
    const on = profilesOn();
    const profiles = el("button", {
      type: "button",
      class: "btn ghost icon sab-corner-profiles",
      "aria-label": "Column profiles in the headers",
      "aria-pressed": on ? "true" : "false",
      title: on ? "Hide the column profiles in the headers" : "Show each column's profile in its header",
    });
    profiles.textContent = "▥";
    profiles.addEventListener("click", () => {
      setProfiles(!profilesOn());
      own.profilesChanged();
    });
    const all = el("button", { type: "button", class: "sab-corner", title: "Select all (Ctrl+A)", "aria-label": "Select all" });
    all.addEventListener("click", () => own.selectAll());
    this.element = el("div", { class: "sab-corner-cell" }, profiles, all);
  }

  getGui() {
    return this.element;
  }

  refresh() {
    return false;
  }
}
