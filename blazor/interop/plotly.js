// plotly.js: Plotly (the classic front end's same version, plotly.js-dist-min) for the <PlotlyChart> component: the
// Analyze board's cards and a notebook's figures.
//
// A figure is Plotly JSON ({"data": [...], "layout": {...}}), what Python's fig.to_json() writes: no functions. The
// page loads nothing from outside, so pictures in a layout must be inline (data:) and map traces, which fetch
// tiles from the internet, are refused (the classic lazy/plotly.ts's same rules). A figure may name the theme's
// colours ("theme:accent", "theme:accent/0.2"): read from the page's tokens at each draw.
import Plotly from "plotly.js-dist-min";

const MAP_TRACES = /^(scattergeo|choropleth|scattermapbox|choroplethmapbox|densitymapbox|scattermap|choroplethmap|densitymap)$/;

function safeFigure(text) {
  let figure;
  try {
    figure = JSON.parse(text);
  } catch {
    throw new Error("The figure is not JSON (Plotly's fig.to_json() writes it).");
  }
  if (!figure || typeof figure !== "object" || !Array.isArray(figure.data)) throw new Error('A Plotly figure is {"data": [...], "layout": {...}}.');
  if (figure.data.some((t) => MAP_TRACES.test(String(t?.type ?? "")))) throw new Error("Map traces are not supported (they load from the internet).");
  const layout = { ...(figure.layout ?? {}) };
  if (Array.isArray(layout.images)) layout.images = layout.images.filter((i) => typeof i.source === "string" && i.source.startsWith("data:image/"));
  delete layout.mapbox;
  delete layout.map;
  delete layout.geo;
  return { data: figure.data, layout };
}

function themed(value, where) {
  if (typeof value === "string") {
    const match = /^theme:([a-z0-9-]+)(?:\/(0?\.\d+|1))?$/.exec(value);
    if (!match) return value;
    const color = getComputedStyle(where).getPropertyValue(`--${match[1]}`).trim();
    if (!color) return value;
    if (!match[2] || !/^#[0-9a-f]{6}$/i.test(color)) return color;
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16));
    return `rgba(${r}, ${g}, ${b}, ${match[2]})`;
  }
  if (Array.isArray(value)) return value.map((v) => themed(v, where));
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, themed(v, where)]));
  return value;
}

/** The figure drawn into `host`; its error's words when it cannot be (shown by the component). */
export async function render(host, text) {
  let figure;
  try {
    figure = safeFigure(text);
  } catch (error) {
    return error.message;
  }
  const css = getComputedStyle(host);
  const fg = css.getPropertyValue("--fg").trim() || "#1c2228";
  const grid = css.getPropertyValue("--border").trim() || "#d5dbe1";
  const layout = themed(
    {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: '"Segoe UI", system-ui, sans-serif', color: fg, size: 12 },
      margin: { l: 48, r: 16, t: 32, b: 40 },
      autosize: true,
      ...figure.layout,
      xaxis: { gridcolor: grid, zerolinecolor: grid, ...(figure.layout.xaxis ?? {}) },
      yaxis: { gridcolor: grid, zerolinecolor: grid, ...(figure.layout.yaxis ?? {}) },
    },
    host,
  );
  await Plotly.react(host, themed(figure.data, host), layout, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["sendDataToCloud"] });
  if (!host.sabResize) {
    host.sabResize = new ResizeObserver(() => Plotly.Plots.resize(host));
    host.sabResize.observe(host);
  }
  return null;
}

export function destroy(host) {
  host.sabResize?.disconnect();
  host.sabResize = null;
  Plotly.purge(host);
}
