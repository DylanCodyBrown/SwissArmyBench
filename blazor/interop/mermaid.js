// mermaid.js: Mermaid (the classic front end's same version) for the <MermaidDiagram> component: the ERD and lineage.
// The text is the server's (domain/relationships.py mermaid_erd); "strict" security keeps any label from running
// script, and the drawing's colours are the app's tokens, read at each render so both themes draw right.
import mermaid from "mermaid";

let made = 0;

function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** The diagram `text` drawn into `host` (its SVG replacing what was there). */
export async function render(host, text) {
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
    },
  });
  made += 1;
  const { svg } = await mermaid.render(`sab-mermaid-${made}`, text);
  host.innerHTML = svg;
}
