// snapshot.js: the agent's app_snapshot answered (services/snapshots.py): the page draws the area it was asked for
// with html-to-image (picture.js's package) and sends the PNG straight to the server, never through C#. Only the page
// answers; one that is not on screen keeps quiet (another window may be), one that does not show the area says so.
import { toPng } from "html-to-image";

// What each area is called on the page (services/snapshots.py AREAS).
const AREAS = {
  app: "body",
  ribbon: ".ribbon",
  grid: ".ag-root-wrapper",
  steps: ".steps-strip",
  analyze: ".analyze-board",
  projects: ".area-page",
};

const send = (path, body, type) => fetch(path, { method: "POST", body, headers: { "Content-Type": type } });

function bytesOf(dataUrl) {
  const text = atob(dataUrl.slice(dataUrl.indexOf(",") + 1));
  const bytes = new Uint8Array(text.length);
  for (let at = 0; at < text.length; at++) bytes[at] = text.charCodeAt(at);
  return bytes;
}

/** Draw `area` at `scale` and send it as request `id`'s answer; true when the picture went. */
export async function answer(id, area, scale) {
  if (document.visibilityState !== "visible") return false;
  const wanted = encodeURIComponent(id);
  const element = document.querySelector(AREAS[area] ?? AREAS.app);
  const box = element?.getBoundingClientRect();
  if (!element || !box || box.width < 1 || box.height < 1) {
    await send(`/snapshots/${wanted}/error`, `the page in front does not show the ${area} area`, "text/plain");
    return false;
  }
  try {
    const whole = element === document.body;
    const width = Math.round(whole ? window.innerWidth : box.width);
    const height = Math.round(whole ? window.innerHeight : box.height);
    const picture = await toPng(element, {
      width,
      height,
      pixelRatio: scale,
      cacheBust: false,
      backgroundColor: getComputedStyle(document.body).backgroundColor,
    });
    const sent = await send(`/snapshots/${wanted}?width=${width * scale}&height=${height * scale}`, bytesOf(picture), "image/png");
    return sent.ok;
  } catch (error) {
    await send(`/snapshots/${wanted}/error`, String(error?.message ?? error), "text/plain");
    return false;
  }
}
