# What users love in app builders and data-app tools (research, 2026-11-19)

Asked by the owner: "thoroughly research app builders like Hex and WinForms and Power Apps ... find everybody's
favorite features". Gathered by a research agent from the web. Reddit could not be reached, so user voices come
from Hacker News, the Streamlit and Bubble forums, G2/Capterra/Trustpilot summaries, blogs and GitHub issue votes.
Many comparison blogs are written by vendors: weighed accordingly. The strongest hard evidence is Streamlit's
most-upvoted open GitHub issues (pulled 2026-11-19).

## The top 20 features to bring in (ranked)

1. **Reactive cells: only the affected cells run again** (Hex, Observable, marimo, Shiny). Hex reviewers: "feels
   like magic" (https://g2.com/products/hex-technologies/reviews); on HN (marimo, 2024-01) simonw misses
   "cell reactivity", bluish29 names "the hidden state of Jupyter Notebooks"
   (https://news.ycombinator.com/item?id=38971966); a caveat: "state is not tracked perfectly". We already read each
   cell's makes/reads (cell_facts.py, notebook_flow.py). Large.
2. **Build the app by dragging notebook cells onto a layout** (Hex's App builder, "Add to app" on each cell:
   https://learn.hex.tech/docs/build-apps/app-builder; Plotly App Studio: https://dash.plotly.com/app-studio-changelog).
   Our canvas already does this: add "Add to app" on every cell and "Reset layout". Small.
3. **Fix Streamlit's whole-script rerun in what we export.** "whole script will run everytime on any interaction
   ... biggest mistake" (https://discuss.streamlit.io/t/biggest-mistake-to-build-on-streamlit/83680;
   https://github.com/streamlit/streamlit/issues/5827). The canvas wraps each block in `@st.fragment` and caches
   each data cell, so users get Shiny-like behaviour without learning it. Medium.
4. **A property pane where any property can be an expression** (WinForms property grid and events tab, Power Apps'
   formula bar, Retool/Appsmith/ToolJet bindings). WinForms devs "get more done in a day" than with XAML
   (https://forum.codeproject.com/post/4059806;
   https://dev.to/mtmattei/why-microsoft-wont-revive-winforms-and-what-developers-are-using-instead-3bla). A
   property takes a constant, a `${VAR}`, a widget's value or a Python expression. Medium.
5. **Inputs that are plain Python variables, with defaults scheduled runs use** (Hex:
   https://learn.hex.tech/docs/develop-logic/scheduled-runs; Tableau and Power BI parameters). Maps onto the
   controllers' `# Makes:` contract. Small.
6. **Cross-filtering and click-to-set-a-parameter** (Tableau actions:
   https://help.tableau.com/current/pro/desktop/en-gb/actions_parameters.htm; Power BI cross-highlight). Selecting
   points filters every other block; generate Streamlit's `on_select`. Medium.
7. **A query panel with transformers and a raw/transformed view** (Retool:
   https://docs.retool.com/queries/guides/transformers; "results shown immediately",
   https://www.g2.com/products/retool/reviews). Ours: a DuckDB SQL cell plus a Python transform, a live grid under
   each. Medium.
8. **SQL in markdown for report pages** (Evidence; HN 2021-08: "I just want metrics in a simple blog like page",
   https://news.ycombinator.com/item?id=28304781). Our HTML/markdown cells running named DuckDB queries. Medium.
9. **Layout containers, not absolute positions** (Power Apps containers, WinForms Dock/Anchor, WPF panels,
   Streamlit's 2025 flex containers: https://docs.streamlit.io/develop/quick-reference/release-notes/2025).
   "PowerApps does not have responsiveness as a core concept"
   (https://powerusers.microsoft.com/t5/Building-Power-Apps/canvas-apps-production-ready/m-p/749669); Streamlit
   #6867 (71 votes). Medium.
10. **Document outline with drag to reparent** (Visual Studio, Power Apps Tree view, Hex Outline). Big Power Apps
    apps get slow and hard to navigate
    (https://powerusers.microsoft.com/t5/Building-Power-Apps/Slow-performance-in-Power-Apps-Studio-when-building-large-apps/m-p/957682).
    Small.
11. **Snaplines, align/distribute, smart tags** (WinForms, Blend). Small.
12. **Design-time sample data** (WPF/Blend's d:DataContext, Hex's live preview); our contracts' made-up samples.
    Small.
13. **Styles and themes as resources** (WPF resource dictionaries, Power Apps themes: "a handful of predefined
    themes isn't great", https://dev.to/wyattdave/power-apps-top-8-missing-features-1d9j); export to
    .streamlit/config.toml plus CSS. Medium.
14. **Reusable components with their own inputs and outputs** (Power Apps component libraries, Retool modules,
    Streamlit Custom Components v2). Medium.
15. **Named formulas: app-level computed values** (Power Fx App.Formulas:
    https://www.microsoft.com/en-us/power-platform/blog/power-apps/power-fx-introducing-named-formulas/; makers say
    they "often don't update when a dependent variable updates"): ours reactive by construction. Small.
16. **Editable tables that write back** (Sigma input tables: "a bridge from Excel",
    https://g2.com/products/sigma-computing-sigma/reviews; Glide; Retool). Streamlit #7749 (90 votes), #6272 (67).
    Our Write starters do it with a dry run. Medium.
17. **Version history with diff and restore, as Git-friendly text** (Appsmith Git sync, Retool releases, marimo's
    plain .py: simonw "the Marimo file format is just Python"; Jupyter's "python-in-JSON is miserable"). Small.
18. **Debugging and testing** (Power Apps Monitor and Test Studio; "debugging ... complex formulas ... can become
    difficult", https://www.capterra.com/p/228526/Microsoft-Power-Apps/reviews/?rating=4): a run timeline (which
    cells ran, why, how long). Medium.
19. **Scheduled refresh and notifications** (Hex, Mode, Observable data loaders:
    https://observablehq.com/blog/data-loaders-for-the-win). Medium.
20. **Small widgets Streamlit users keep asking for:** export to standalone HTML (#611, 221 votes), copy to
    clipboard (#6726, 94), local storage (#5105, 66), hierarchical navigation (#5889, 58), cell tooltips (#7564,
    59), a standalone executable (#1370, 85): as starter components; static HTML export with stlite/Pyodide.

## The top 10 complaints to avoid
1. Whole-app reruns and awkward state (Streamlit's first complaint).
2. Lock-in: no export as code (Retool's JSON-only export:
   https://community.retool.com/t/retool-due-diligence-vendor-lock-in-and-licensing/64711; Bubble). FlutterFlow
   praised for real Dart export (behind a paywall).
3. Opaque or per-seat pricing and sudden changes (Bubble's workload units; Retool's self-hosting, secondary source:
   https://alm0stsurely.github.io/2026/02/26/asymptotic-cost-convenience/; HN:
   https://news.ycombinator.com/item?id=38534920).
4. Silent data truncation (Power Apps delegation:
   https://learn.microsoft.com/power-apps/maker/canvas-apps/delegation-overview). Our rule: always say when a result
   was limited.
5. Logic spread across the UI ("spaghetti code all over the place", HN 2023-12).
6. The editor slows down on big apps (Power Apps 100+ screens, Hex past ~70 cells).
7. A designer that rewrites your code (XAML: "rearranges code when they drag controls",
   https://forum.codeproject.com/post/4153943). Designer edits keep the user's own bytes.
8. Fixed components that cap the design (Glide; HN: "lack of control ... billed as a feature").
9. Weak debugging and slow support (FlutterFlow, 2025).
10. Mobile and layout breakage (Evidence's launch; Power Apps responsive layouts): preview several widths.

## Five differentiators nobody does well yet
1. A reactive designer that exports plain Streamlit (reactive while designing; generated code that reruns as
   little as possible with fragments and caches): portable and fast together.
2. One DuckDB engine shared by the grid, the notebook, the app and the report, each block's SQL visible and its
   lineage clickable all the way to the exported app.
3. Desktop-first and offline, no seat pricing, the data staying local.
4. A WinForms-quality designer for Python data apps (property grid, events, snaplines, outline, design-time data):
   no Python tool offers it today (Anvil comes closest).
5. The agent drives the designer through the same commands as the user (with approvals); with Figma Dev Mode's
   "Code Connect" idea: every canvas block shows the exact code it exports.

Little independent evidence was found for Mode, Budibase, ToolJet, Glide and Tableau; Reddit was not reachable.
