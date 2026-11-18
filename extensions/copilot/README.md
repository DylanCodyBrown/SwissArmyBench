# Swiss Army Bench: GitHub Copilot

GitHub Copilot's code completion (ghost text) in the Workbench's notebook cells and scripts.

- Installed from the app's Extensions page (one click), then **Install the language server** on its card:
  GitHub's Copilot Language Server (`@github/copilot-language-server`, MIT, pinned) goes into the app's
  state folder (`copilot/`) with `npm install --prefix`. It needs Node.js 20.8 or later.
- **Sign in** with GitHub's device flow: the card shows the code; open github.com/login/device, enter it.
  A GitHub Copilot plan is needed (Copilot Free counts). The sign-in is the language server's own; the app
  never sees or keeps the token.
- What is sent: only the document being edited (a cell's text with the notebook's other code cells, or a
  script's text). Never outputs, tables' rows or variables' values. Nothing at all while it is off, before it
  is installed and signed in, or for a project marked private. Telemetry is switched off.

GitHub Copilot's terms apply:
https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features#github-copilot
