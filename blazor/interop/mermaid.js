// mermaid.js: Mermaid (blazor/package.json's pinned version) for the <MermaidDiagram> component: the ERD and lineage.
// The text is the server's (domain/relationships.py mermaid_erd); "strict" security keeps any label from running
// script, and the drawing's colours are the app's tokens, read at each render so both themes draw right.
import mermaid from "mermaid";

let made = 0;

function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function setUp() {
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: "base",
    themeVariables: {
      background: token("--bg"),
      primaryColor: token("--raised"),
      primaryTextColor: token("--fg"),
      primaryBorderColor: token("--border-strong"),
      lineColor: token("--muted"),
      textColor: token("--fg"),
      fontFamily: '"Segoe UI", system-ui, sans-serif',
      attributeBackgroundColorOdd: token("--raised"),
      attributeBackgroundColorEven: token("--surface"),
      mainBkg: token("--surface-2"),
      edgeLabelBackground: token("--bg"),
    },
  });
}

/** The diagram `text` drawn into `host` (its SVG replacing what was there). */
export async function render(host, text) {
  setUp();
  made += 1;
  const { svg } = await mermaid.render(`sab-mermaid-${made}`, text);
  host.innerHTML = svg;
}

/**
 * A diagram someone is writing (a .mmd file, a ```mermaid block): checked first, so a mistake never blanks the
 * drawing. Drawn: null. Not: Mermaid's own message and the line it points at ({ message, line }; line 0 when it
 * names none), the last good drawing left as it was.
 */
export async function draw(host, text) {
  setUp();
  try {
    await mermaid.parse(text);
    made += 1;
    const { svg } = await mermaid.render(`sab-mermaid-${made}`, text);
    host.innerHTML = svg;
    return null;
  } catch (error) {
    document.getElementById(`dsab-mermaid-${made}`)?.remove(); // what a failed render leaves on the page
    const message = String(error?.message ?? error);
    const found = /line (\d+)/i.exec(message);
    const line = found ? Number(found[1]) : (error?.hash?.loc?.first_line ?? 0);
    return { message, line: Number(line) || 0 };
  }
}
