/**
 * areaMarks.ts: the footer's marks an extension's rail area answers (the owner, 2026-11-18: "add a simple
 * indicator at the bottom that the project is out of sync"). Generic: the backend names each area and its mark
 * route (GET /app/areas: {area, name, mark}); the page never names an extension. [SHARED]
 *
 * A mark shows only while its route answers one ({"mark": {"words", "state", "title"?}}: "↑3 to push",
 * "↓2 behind", "Conflicts: 2"), amber; nothing when it answers null (up to date, not connected, no project).
 * Read once a page and again on the notices that change it (sync_changed, project_changed, projects_changed):
 * never on a timer. A click opens the area's page.
 */
import { api, onNotice } from "./api";
import { h } from "./dom";
import { hasLayer, HOME_URL, openLayer } from "./nav";

interface Area { area: string; name: string; mark: string }
interface Mark { words: string; state: string; title?: string; name?: string }

let areas: Promise<Area[]> | null = null;
const marks = new Set<() => void>();

onNotice((n) => {
  if (n.type === "sync_changed" || n.type === "project_changed" || n.type === "projects_changed") for (const draw of marks) draw();
});

/** The marks' place in the footer (before the update notice). */
export function areaMarks(): HTMLElement {
  const host = h("span", { class: "area-marks" });
  const draw = async (): Promise<void> => {
    areas ??= api<{ areas: Area[] }>("/app/areas").then((got) => got.areas.filter((a) => a.mark), () => []);
    const shown: HTMLElement[] = [];
    for (const area of await areas) {
      const got = await api<{ mark: Mark | null }>(area.mark).catch(() => ({ mark: null }));
      if (!got.mark) continue;
      const mark = got.mark;
      shown.push(
        h(
          "button",
          {
            type: "button",
            class: `area-mark area-mark-${mark.state}`,
            "data-area": area.area,
            title: `${area.name}: ${mark.name ? `${mark.name}, ` : ""}${mark.words}`,
            onclick: () => {
              if (hasLayer(area.area)) openLayer(area.area);
              else location.assign(`${HOME_URL}?open=${encodeURIComponent(area.area)}${location.hash}`);
            },
          },
          mark.words,
        ),
      );
    }
    host.replaceChildren(...shown);
  };
  const again = (): void => {
    if (!host.isConnected) {
      marks.delete(again); // a footer drawn again: the old one's marks stop
      return;
    }
    void draw();
  };
  marks.add(again);
  void draw();
  return host;
}
