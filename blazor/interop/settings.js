// settings.js: Settings' section list (Pages/Settings/SettingsPage). The page is one column of boxes; the list on
// its left jumps to a box and marks the one in view. Each section is a `.settings-section` wrapper (display:
// contents) round its box: a wrapper whose box is not drawn (no update to install) is left out of the list.

const TOP_ROOM = 24; // how far under the scroller's top a box may start and still be the one in view

function boxOf(section) {
  return section.firstElementChild;
}

function drawn(section) {
  const box = boxOf(section);
  return !!box && box.offsetHeight > 0;
}

/**
 * Watches the page's sections: tells C# (OnSections) which are drawn and which one is in view, as the page
 * scrolls and as boxes come and go. Returns { jump(id), dispose() }.
 */
export function watch(layout, dotnet) {
  const scroller = layout.closest(".area-page-body") ?? document.documentElement;
  let said = "";
  let frame = 0;
  let pinned = null; // the section just jumped to stays marked until the user scrolls by hand

  const sections = () => [...layout.querySelectorAll(".settings-section")].filter(drawn);

  const current = (shown) => {
    if (pinned && shown.some((s) => s.dataset.section === pinned)) {
      return pinned;
    }
    const top = scroller.getBoundingClientRect().top + TOP_ROOM;
    let found = shown[0];
    for (const section of shown) {
      if (boxOf(section).getBoundingClientRect().top <= top) {
        found = section;
      }
    }
    const scrolls = scroller.scrollHeight > scroller.clientHeight + 1;
    if (scrolls && scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2) {
      found = shown[shown.length - 1]; // at the very bottom the last box can never reach the top
    }
    return found?.dataset.section ?? "";
  };

  const report = () => {
    frame = 0;
    const shown = sections();
    const ids = shown.map((s) => s.dataset.section);
    const now = current(shown);
    const saying = `${ids.join(",")}|${now}`;
    if (saying !== said) {
      said = saying;
      dotnet.invokeMethodAsync("OnSections", ids, now).catch(() => {});
    }
  };
  const soon = () => {
    frame ||= requestAnimationFrame(report);
  };
  const byHand = () => {
    pinned = null;
    soon();
  };

  scroller.addEventListener("scroll", soon, { passive: true });
  for (const type of ["wheel", "touchmove", "pointerdown", "keydown"]) {
    scroller.addEventListener(type, byHand, { passive: true });
  }
  window.addEventListener("resize", soon);
  const changes = new MutationObserver(soon);
  changes.observe(layout, { childList: true, subtree: true });
  report();

  return {
    jump(id) {
      const section = sections().find((s) => s.dataset.section === id);
      if (!section) {
        return;
      }
      const box = boxOf(section);
      pinned = id;
      const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      box.scrollIntoView({ block: "start", behavior: calm ? "auto" : "smooth" });
      box.tabIndex = -1;
      box.focus({ preventScroll: true }); // the keyboard goes on from the section jumped to
      soon();
    },
    dispose() {
      scroller.removeEventListener("scroll", soon);
      for (const type of ["wheel", "touchmove", "pointerdown", "keydown"]) {
        scroller.removeEventListener(type, byHand);
      }
      window.removeEventListener("resize", soon);
      changes.disconnect();
      cancelAnimationFrame(frame);
    },
  };
}
