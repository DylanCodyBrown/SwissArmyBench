// vega.js: Vega-Lite (the classic front end's same versions: vega, vega-lite, vega-embed) for the <VegaChart>
// component: the Analyze board's chart cards and Open large. The server already aggregated the data and made the
// Vega-Lite spec (domain/charts.py); this draws it in the app's theme (the classic lazy/charts.ts's rules: colours
// from the tokens, fill patterns for bar and area series so they never differ by colour alone, wheel zoom on
// scatter and line charts, a click on a bar, point or heatmap cell told back as its value for the cross-filter),
// and gives its pictures (PNG, SVG) for Download image and Download as HTML.
import embed from "vega-embed";

const drawn = new WeakMap();
let source = document.documentElement;

const token = (name) => getComputedStyle(source).getPropertyValue(name).trim() || "#888888";
const themeKey = () => source.closest("[data-sandbox-theme]")?.dataset.sandboxTheme || "app";
const isHc = () => {
  const key = themeKey();
  return (key === "app" ? document.documentElement.dataset.theme ?? "" : key).startsWith("hc");
};

const TEXTURES = [
  (ink) => `<path d="M-2 2l4-4M0 10L10 0M8 12l4-4" stroke="${ink}" stroke-width="1.6"/>`,
  () => "",
  (ink) => `<circle cx="5" cy="5" r="1.7" fill="${ink}"/>`,
  (ink) => `<path d="M0 3h10M0 8h10" stroke="${ink}" stroke-width="1.4"/>`,
  (ink) => `<path d="M3 0v10M8 0v10" stroke="${ink}" stroke-width="1.4"/>`,
  (ink) => `<path d="M0 0L10 10M10 0L0 10" stroke="${ink}" stroke-width="1.2"/>`,
  (ink) => `<rect x="0" y="0" width="5" height="5" fill="${ink}" fill-opacity="0.55"/><rect x="5" y="5" width="5" height="5" fill="${ink}" fill-opacity="0.55"/>`,
  (ink) => `<path d="M0 10L10 0" stroke="${ink}" stroke-width="2.6"/>`,
];

function patternDefs() {
  const ink = isHc() ? token("--bg") : "rgba(255,255,255,0.75)";
  const darkInk = isHc() ? token("--bg") : "rgba(0,0,0,0.45)";
  return TEXTURES.map((texture, i) => {
    const color = token(`--cat-${i + 1}`);
    const hex = color.replace("#", "");
    const lum = hex.length === 6 ? (0.299 * parseInt(hex.slice(0, 2), 16) + 0.587 * parseInt(hex.slice(2, 4), 16) + 0.114 * parseInt(hex.slice(4, 6), 16)) / 255 : 0.5;
    return `<pattern id="sab-pat-${themeKey()}-${i + 1}" patternUnits="userSpaceOnUse" width="10" height="10"><rect width="10" height="10" fill="${color}"/>${texture(lum > 0.6 ? darkInk : ink)}</pattern>`;
  }).join("");
}

function installPatterns() {
  const id = `sab-patterns-${themeKey()}`;
  let host = document.getElementById(id);
  if (!host) {
    host = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    host.id = id;
    host.setAttribute("aria-hidden", "true");
    host.setAttribute("style", "position:absolute;width:0;height:0;overflow:hidden");
    document.body.append(host);
  }
  host.innerHTML = `<defs>${patternDefs()}</defs>`;
}

const patterns = () => TEXTURES.map((_, i) => `url(#sab-pat-${themeKey()}-${i + 1})`);

function themeConfig(scale, narrow) {
  const fg = token("--fg");
  const hc = isHc();
  const muted = hc ? fg : token("--muted");
  const grid = hc ? token("--fg") : token("--border");
  const font = '"Segoe UI", system-ui, sans-serif';
  const size = Math.round(12 * scale);
  return {
    background: null,
    font,
    view: { stroke: null },
    title: { color: fg, font, fontSize: Math.round(13.5 * scale), fontWeight: 600, anchor: "start" },
    axis: {
      labelColor: muted, titleColor: fg, domainColor: token("--border-strong"), domainWidth: hc ? 2 : 1, tickColor: grid,
      gridColor: grid, gridOpacity: hc ? 0.45 : 0.7, labelFont: font, titleFont: font, labelFontSize: size,
      titleFontSize: size, titleFontWeight: 600, labelSeparation: 8,
    },
    legend: {
      labelColor: fg, titleColor: fg, labelFont: font, titleFont: font, labelFontSize: size, titleFontSize: size,
      symbolSize: 180, symbolStrokeColor: fg, symbolStrokeWidth: 1, orient: narrow ? "bottom" : "right",
      direction: narrow ? "horizontal" : "vertical", columns: narrow ? 3 : undefined,
    },
    range: { category: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => token(`--cat-${i}`)) },
    mark: { color: token("--cat-1") },
    bar: { stroke: fg, strokeWidth: hc ? 1.5 : 0.8, strokeOpacity: hc ? 1 : 0.7 },
    rect: { stroke: token("--bg"), strokeWidth: 0.5 },
    point: { filled: true, size: 48 },
    line: { strokeWidth: hc ? 3.5 : 2.5 },
  };
}

function withPatterns(spec) {
  const mark = spec.mark?.type;
  const encoding = spec.encoding;
  if (!encoding?.color || (mark !== "bar" && mark !== "area")) return spec;
  const { strokeDash: _dash, ...rest } = encoding;
  return { ...spec, encoding: { ...rest, color: { ...encoding.color, scale: { range: patterns() } } } };
}

function withYTicks(spec) {
  const y = spec.encoding?.y;
  if (!y || y.type !== "quantitative") return spec;
  return { ...spec, encoding: { ...spec.encoding, y: { ...y, axis: { ...y.axis, tickCount: 4 } } } };
}

// Labels are never dropped: they turn when they would not fit side by side at this width.
function fitLabels(spec, width, fontSize) {
  const encoding = spec.encoding;
  const x = encoding?.x;
  const values = spec.data?.values ?? [];
  if (x?.type === "temporal" && width) {
    if (x.axis?.format === "%b %Y") {
      const months = new Set(values.map((v) => String(v.x).slice(0, 7))).size || 12;
      const step = Math.max(1, Math.ceil((months * 70) / Math.max(120, width - 90)));
      return withYTicks({ ...spec, encoding: { ...encoding, x: { ...x, axis: { ...x.axis, tickCount: { interval: "month", step } } } } });
    }
    const ticks = Math.max(3, Math.min(12, Math.floor((width - 80) / 90)));
    return withYTicks({ ...spec, encoding: { ...encoding, x: { ...x, axis: { ...x.axis, tickCount: ticks } } } });
  }
  if (!x || x.type !== "nominal" || !width) return withYTicks(spec);
  const labels = [...new Set(values.map((v) => String(v.x)))];
  const longest = labels.reduce((most, l) => Math.max(most, l.length), 0);
  const plot = Math.max(120, width - 90);
  const fits = longest * fontSize * 0.6 + 10 <= plot / Math.max(1, labels.length);
  const crowded = labels.length * fontSize * 1.1 > plot;
  const base = { ...x.axis, title: null };
  const angled = { ...base, labelAngle: -35, labelAlign: "right", labelBaseline: "top" };
  const axis = fits ? base : crowded ? { ...angled, labelOverlap: "greedy" } : angled;
  return withYTicks({ ...spec, encoding: { ...encoding, x: { ...x, axis } } });
}

function thinBars(spec, width) {
  const bars = (spec.data?.values ?? []).length;
  if (spec.mark?.type !== "bar" || !width || !bars || Math.max(120, width - 90) / bars >= 4) return spec;
  return { ...spec, mark: { ...spec.mark, strokeWidth: 0 } };
}

const RAW_X = "sab_raw_x";
const RAW_Y = "sab_raw_y2";

function withRawValues(spec) {
  if (!spec.data?.values) return spec;
  return { ...spec, data: { ...spec.data, values: spec.data.values.map((v) => ("x" in v ? { ...v, [RAW_X]: v.x, [RAW_Y]: v.y2 } : v)) } };
}

/** The spec (Vega-Lite JSON) drawn into `host`; a click on a bar, point or cell calls the component's Selected
 * with its value (and a heatmap cell's row value). Its error's words when it cannot be drawn. */
export async function render(host, text, options, component) {
  source = host;
  installPatterns();
  let copy;
  try {
    copy = withRawValues(withPatterns(JSON.parse(text)));
  } catch {
    return "The chart's spec is not JSON.";
  }
  delete copy.$schema;
  if (options.height) copy.height = options.height;
  const mark = copy.mark?.type;
  if (options.zoomable && (mark === "point" || mark === "line" || mark === "area")) {
    copy = { ...copy, params: [{ name: "zoom", select: "interval", bind: "scales" }] };
  }
  const narrow = host.clientWidth > 0 && host.clientWidth < 480;
  const scale = options.large ? 1.3 : 1;
  copy = thinBars(fitLabels(copy, host.clientWidth, 12 * scale), host.clientWidth);
  drawn.get(host)?.view.finalize();
  try {
    const result = await embed(host, copy, { actions: false, renderer: "svg", config: themeConfig(scale, narrow && !options.large), tooltip: { theme: "custom" } });
    drawn.set(host, result);
    if (component) {
      const heatmap = mark === "rect";
      result.view.addEventListener("click", (_event, item) => {
        // A line or area path carries only its first point: only bars, points and cells name one value.
        if (item?.mark?.marktype !== "rect" && item?.mark?.marktype !== "symbol") return;
        const datum = item.datum;
        if (!datum || !(RAW_X in datum)) return;
        component.invokeMethodAsync("Selected", JSON.stringify(datum[RAW_X] ?? null), heatmap ? JSON.stringify(datum[RAW_Y] ?? null) : null);
      });
    }
    return null;
  } catch (error) {
    return String(error?.message ?? error);
  }
}

async function toSvg(host) {
  const result = drawn.get(host);
  if (!result) return null;
  return (await result.view.toSVG()).replace(/(<svg[^>]*>)/, `$1<defs>${patternDefs()}</defs>`);
}

async function toPng(host) {
  const svg = await toSvg(host);
  if (!svg) return null;
  const image = new Image();
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  await image.decode();
  const canvas = document.createElement("canvas");
  canvas.width = image.width * 2;
  canvas.height = image.height * 2;
  const context = canvas.getContext("2d");
  context.fillStyle = token("--bg");
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.scale(2, 2);
  context.drawImage(image, 0, 0);
  return canvas.toDataURL("image/png");
}

function save(href, name) {
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
}

/** Download image (PNG): the chart's picture at twice its size. */
export async function downloadPng(host, title) {
  const url = await toPng(host);
  if (url) save(url, `${title || "chart"}.png`);
}

/** Download as HTML: the chart's SVG in a page of its own, with its dataset and the time. */
export async function downloadHtml(host, title, dataset) {
  const svg = await toSvg(host);
  if (!svg) return;
  const escape = (s) => s.replace(/</g, "&lt;");
  const page = `<!doctype html><meta charset="utf-8"><title>${escape(title)}</title><body style="font-family:Segoe UI,sans-serif;background:#fff;margin:24px">${svg}<p style="color:#57606a">${dataset ? `Dataset ${escape(dataset)}, ` : ""}${new Date().toISOString()}</p></body>`;
  const url = URL.createObjectURL(new Blob([page], { type: "text/html" }));
  save(url, `${title.replace(/[^A-Za-z0-9_-]+/g, "_") || "chart"}.html`);
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/** The board's markdown export: the chart's picture. */
export const picture = (host) => toPng(host);

export function destroy(host) {
  drawn.get(host)?.view.finalize();
  drawn.delete(host);
}
