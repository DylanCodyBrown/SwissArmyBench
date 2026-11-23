// tour.js: the tour's spotlight and card placed beside the control a card is about (the classic tour.ts aim), and
// its keys heard on the window while it is open (so a page that takes the focus does not take them). The cards'
// words, the staged tables and the moves are the C# component's (Layout/Tour/TourHost.razor).

const GUTTER = 16;
const PAD = 6;
const CARD_WIDTH = 380;
const FOLLOW_MS = 300;

const pause = (ms) => new Promise((done) => setTimeout(done, ms));

/** The first visible element for any of `selectors`, in their order, or null. */
function visible(selectors) {
  for (const selector of selectors) {
    let found;
    try {
      found = document.querySelectorAll(selector);
    } catch {
      continue;
    }
    for (const el of found) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return el;
    }
  }
  return null;
}

function place(root, card, spot, el) {
  const width = Math.min(CARD_WIDTH, window.innerWidth - 2 * GUTTER);
  card.style.width = `${width}px`;
  const r = el?.isConnected ? el.getBoundingClientRect() : null;
  if (!r || r.width === 0) {
    root.classList.add("tour-dim");
    spot.hidden = true;
    card.style.left = `${(window.innerWidth - width) / 2}px`;
    card.style.top = `${Math.max(GUTTER, (window.innerHeight - card.offsetHeight) / 2)}px`;
    return;
  }
  root.classList.remove("tour-dim");
  spot.hidden = false;
  Object.assign(spot.style, { left: `${r.left - PAD}px`, top: `${r.top - PAD}px`, width: `${r.width + 2 * PAD}px`, height: `${r.height + 2 * PAD}px` });
  const below = r.bottom + PAD + 12;
  const above = r.top - PAD - 12 - card.offsetHeight;
  let top;
  let left;
  // A rail icon: the card beside it, so it never covers the icons under it.
  if (el.closest(".nav-rail")) top = -1;
  else if (below + card.offsetHeight + GUTTER <= window.innerHeight) top = below;
  else if (above >= GUTTER) top = above;
  else top = -1;
  if (top >= 0) {
    left = Math.min(Math.max(GUTTER, r.left + r.width / 2 - width / 2), window.innerWidth - width - GUTTER);
  } else {
    top = Math.min(Math.max(GUTTER, r.top + r.height / 2 - card.offsetHeight / 2), window.innerHeight - card.offsetHeight - GUTTER);
    const right = r.right + PAD + 12;
    left = right + width + GUTTER <= window.innerWidth ? right : Math.max(GUTTER, r.left - PAD - 12 - width);
  }
  card.style.left = `${left}px`;
  card.style.top = `${Math.max(GUTTER, top)}px`;
}

export function start(root, card, spot, listener) {
  let selectors = [];
  let target = null;
  let serial = 0;
  const follow = setInterval(() => {
    if (target && !target.isConnected) target = visible(selectors); // the page drew it again
    place(root, card, spot, target);
  }, FOLLOW_MS);
  const onKey = (event) => {
    const typing = event.target instanceof HTMLInputElement && card.contains(event.target);
    const listOpen = !!document.querySelector(".variable-float, .context-menu");
    if (listOpen && ["Escape", "ArrowUp", "ArrowDown", "Enter", "Tab"].includes(event.key)) return; // the list's
    if (typing && ["ArrowLeft", "ArrowRight", "Enter"].includes(event.key)) return; // the box's own keys
    if (event.key === "Enter" && card.contains(event.target)) return; // the focused button's own click
    if (!["Escape", "ArrowRight", "ArrowLeft", "Enter"].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    listener.invokeMethodAsync("Key", event.key);
  };
  window.addEventListener("keydown", onKey, true);
  return {
    /** Light up the first of `wanted` that shows within `ms` (null: none, the card in the middle). */
    async aim(wanted, ms) {
      const mine = ++serial;
      selectors = wanted ?? [];
      target = null;
      place(root, card, spot, null);
      if (!selectors.length) return false;
      for (const end = Date.now() + ms; Date.now() < end && !visible(selectors); await pause(80)) {
        if (mine !== serial) return false;
      }
      if (mine !== serial) return false;
      target = visible(selectors);
      target?.scrollIntoView({ block: "nearest", inline: "nearest" });
      place(root, card, spot, target);
      return !!target;
    },
    /** A connection form's box with `text` typed into it (the "Using a variable" card), within `ms`. */
    async typeInto(selector, text, ms) {
      for (const end = Date.now() + ms; Date.now() < end && !visible([selector]); await pause(80));
      const box = visible([selector]);
      if (!(box instanceof HTMLInputElement) || box.value === text) return;
      box.value = text;
      box.dispatchEvent(new Event("change", { bubbles: true }));
    },
    stop() {
      serial += 1;
      clearInterval(follow);
      window.removeEventListener("keydown", onKey, true);
    },
  };
}
