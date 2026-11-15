# Ideas and open notes

Out-of-scope ideas (plan section 0, rule 4), plus notes from the 2026-10-21 review of the plan
that haven't been folded back into it yet.

## Decisions made while building M0 and M1 (confirm or change)

- **Web framework: Starlette + uvicorn**, plus `websockets` for uvicorn's WebSocket support. The
  plan names no framework. The official MCP Python library is built on Starlette, which should
  help with M5.
- **Type checker: mypy strict.** The pip build of pyright downloads its engine from npm on first
  run, and the plan asks for no network calls beyond installing packages.
- **The grid page shell and static files need no token.** The plan says "token required on every
  request". A browser can't attach a header when it loads a page, so `/g/<id>` and `/static/` are
  public: they hold no data, only the page and the vendored library. The token goes in the URL
  fragment (`#token=`), which browsers never send to a server, and the page attaches it to every
  data request. Host and Origin are still checked on those paths.
- **WebSocket token as a subprotocol**, not a query parameter, so it never appears in the
  server's access log.
- **A request with no Origin header is allowed** (the push client never sends one); a request
  with a foreign Origin gets 403.
- **Separate caps for request body size and dataset size.** The plan's 6a measures the loaded
  Arrow size but also says to refuse on Content-Length. JSON is several times bigger than the
  same data in Arrow, so `max_push_body_bytes` (400 MiB) is separate from `max_dataset_bytes`.
- **Rows come back with the row count** (no separate `/count` route yet), and sort is a `sort=`
  query parameter. Both move to the step model in M3.
- **No thousands separators in grid numbers**, so identifier columns don't look like amounts.

## Decisions made while building M1-M8 (confirm or change)

- **Dependencies added under "build it out as robust as the plan":** sqlglot, mcp and
  xlsxwriter (the plan asked to check xlsxwriter first: BSD-2-Clause, and its in_memory mode is
  used so nothing goes to a temp folder); Monaco, Vega, Vega-Lite and vega-embed in the page
  (MIT and BSD-3, loaded only when first used); Playwright and openpyxl for tests only.
- **The step engine was built before M2**, since profiling, SQL, export and code generation
  all read the step view. Every grid change (header sort, chart click, agent edit) is a step.
- **Charts use a small declarative spec, not raw Vega-Lite** (charts/spec.py): strict
  validation is simple and the server can aggregate before drawing. The server then builds
  the Vega-Lite.
- **Generated code verification** runs only this package's own generated code, in process,
  with an import allowlist checked on the syntax tree. It is not a sandbox (that is M9). Since
  2026-11-12 it runs the code exactly as copied, in a namespace holding only the user's table
  (see "Copied code is one DuckDB query" below).
- **The approval endpoint trusts the browser.** Any process running as the same Windows user
  can read the connection file and approve its own request. The gate stops an agent that only
  has the MCP tools.
- **Group-by output is sorted by its keys** (blanks last), which matches pandas `sort=True`.
- **Header sort is the last word:** new steps go before the header-sort step.
- **The analysis panel starts collapsed in windows narrower than 1,100px** (VS Code's side
  browser, a laptop split).
- **The MCP server ships as a wheel in the plugin**, run with `uvx --from <wheel>`, so
  teammates need uv on their PATH.

## Decisions made on 2026-10-22 (confirm or change)

- **`%` is the only wildcard** (it was `*` and `?` in plan section 7), so a filter reads like SQL
  LIKE; `*`, `?` and `_` are literal.
- **Selection is Excel's, not checkboxes.** A header click now selects its column, so sorting
  moved to the arrow button in each header and to the ribbon's Column group.
- **Copy includes the header row** for whole rows, columns or everything, and not for a block of
  cells (Excel copies only cells; a header line helps when the whole table goes elsewhere).
  Copy stops at 200,000 rows and points to Export.
- **A SQL step reads only the table entering it**, never another dataset, so its generated
  Python needs no other data; joins stay a Pin-as-new-grid job. It names that table by the
  dataset's own name (2026-10-24, so the SQL pastes into the user's Python unchanged, where the
  table is a variable of that name) or `grid` (kept for older steps and recipes). In the SQL box
  a dataset name, the grid's own included, reads the rows as loaded, like the Python variable
  (0.6.0 briefly read the grid's view there instead, so Apply kept the box's rows; 0.6.1 went
  back so the box matches the notebook). So with earlier steps, the same text can give the box
  and the step different rows; with the SQL step first, the box, the step and the pasted Python
  all agree. A query with no defined order is sorted by every
  column (`ORDER BY ALL`).
- **Generated pandas and plain Python run a SQL step in DuckDB** (the plain target then needs
  duckdb, and says so in its header). There is no faithful pure-Python translation of SQL.
- **`read_grid` keeps the privacy caps** (20 rows at level 1, 200 at level 2) and the approval
  click; the agent's `limit` works inside them. Say if level 2 should allow more per read.
  (Superseded 2026-11-12: the privacy levels were removed; see below.)
- **The ribbon names what each tool acts on** (Table, Column, Cell, with the target in the
  caption); a Column or Cell tool is disabled, with the reason in its tooltip, until something
  it can act on is selected.

## Key Finder decisions (2026-10-22, confirm or change)

- **Both sides are grid views**, each after its own steps, so a grid can be filtered down
  before looking for its join. The target can be the grid's own dataset (a self-join such as
  parent_id to id); a column is never paired with itself.
- **Values compare as normalized text:** 42, 42.0 and '42' meet; a timestamp at midnight meets
  its date; Trim (on) and Ignore case (off) apply to text. Columns longer than 128 characters,
  true/false, lists, structs and binary columns are left out and listed with the reason.
- **Score** = (0.7 x overlap coefficient + 0.3 x the lower of the two percent-found figures) x
  min(1, log10(shared) / 3). The second term breaks the classic tie between a real reference
  and an unrelated running counter (an order_id of 1..6,000 contains every customer id of
  1..2,000, but covers them only a third of the way). The last factor keeps Y/N flags and small
  code lists below real keys.
- **Single columns only.** Composite keys (two columns that join only together) are a later
  step: the same inverted-index join over column pairs, with the candidate count kept small.
- The Key Finder is a natural companion to compare (below): a found pair can become the
  compare keys.

## The "+" tab and the window race (2026-10-23, confirm or change)

- **A table name in the "+" tab reads its tab's view**, after that tab's steps (Dylan's choice
  over the raw rows). Two tabs on one dataset: the name reads the first (oldest) grid, the one a
  re-push reuses. A dataset with no tab open reads its rows as loaded.
- **The result is stored, not live.** Run makes a dataset (source kind `sql_result`, with the
  query kept on `DatasetInfo.query`); a change to a table it reads doesn't rebuild it. Run again
  does, in place, keeping the tab's own steps.
- **Run again rebuilds only a table a query made.** `replace` on `POST /datasets/{name}/query`
  is refused for a pushed or loaded dataset, and without `replace` any name in use is refused, so
  a "+" tab can never overwrite another table by picking its name. A query can't read the table
  it builds.
- **The tray is the base data; the SQL box stays a step.** Both open the same Monaco editor, and
  each editor now keeps its own autocomplete names.
- **A push told to open a window holds the next pushes back** until that window connects, or 15
  seconds, so a script pushing three tables opens one window. The MCP's `open_grid` uses the same
  rule.
- Open: the pin path (`CREATE TABLE ... AS` in the SQL box) still fetches with
  `execute(q).to_arrow_table()`, which copies the rows once more than `cursor.sql(q)` (the "+"
  route uses the latter). Worth switching; left alone to keep this change to the "+" tab.
- Open: a closed "+" tab's Monaco editor isn't disposed (panes.ts has no pane-closed hook). Small,
  but it grows with every query tab closed in one page session.

## Copied code is one DuckDB query over the user's table (2026-11-12, confirm or change)

The owner's report: copied SQL and Python "never was the actual transformation script that would
work to transform the source table back in the ENV". Reproduced: the DuckDB copy only defined
`transform(con, rel)` (pyarrow, a `__sag_ord` column, a table registered as `source`), so pasting
it computed nothing and calling it on the user's DataFrame failed; the pandas and plain copies
also only defined `transform()` with helpers and imports. Verification ran them against an Arrow
relation, not the user's variable, so they were marked verified anyway.

- **The DuckDB copy is the default for every source**, and is the query itself: one statement over
  the table by its variable name (the dataset name). Copy as SQL gives the query; Copy as Python
  gives `import duckdb` and `orders_view = duckdb.sql("""...""").df()` (`.pl()` for Polars,
  `.to_arrow_table()` for Arrow, the relation for DuckDB, `.df()` otherwise). This is the plan's
  "Grids pushed from outside" bullet under Code-behind.
- **Built from the engine's own step pieces** (engine/steps.py helpers), not a translation. Row
  order without the hidden column: DuckDB's order preservation, plus `row_number() OVER ()` as the
  last sort key, because ORDER BY is not stable (docs/verified.md). Remove duplicates numbers its
  input in a subquery (`_row`), the one helper column, inside the query only.
- **Verification runs exactly the copied text** with `exec` in a fresh namespace holding only the
  user's variable, rebuilt as what was pushed, and reads back `<name>_view`. It is in process (a
  fresh interpreter per check took about 0.6 s, too slow for the golden suite); the tests also run
  every case in a fresh `python -I` (tests/test_copied_code.py). `duckdb.sql` uses DuckDB's default
  connection, so the server locks that connection down on first use (no file system, no extension
  downloads, no spilling, memory limit, then lock_configuration) and runs one check at a time.
- **pandas is not a server dependency**, so in an installed server `.df()` and the pandas
  translation could not be run. The DuckDB check then runs the same query over an Arrow table and
  says the final `.df()` was not run; the pandas translation reports "Not verified". Open: add
  pandas to the `[server]` extra (a dependency decision for the owner).
- **pandas and plain Python stay as secondary targets** ("longer translation" in the picker), and
  now end with `orders_view = transform(orders)` so they too transform the user's variable. The
  plain one reads a list of dicts, so it cannot run on a pushed DataFrame; the tab says what each
  option reads.
- Open: a pandas frame pushed with a non-default index arrives with that index as a column
  (`reset_index()` in the push client), which the user's own frame does not have, so the copy's
  `SELECT *` shows one column fewer than the grid. A list of dicts, a file or the clipboard has no
  variable DuckDB can read; the copy expects a DataFrame of that name and says so.

## The Sandbox (2026-11-13, the owner's request; page part done, server part after the refactor)

"The agent tab should be renamed to sandbox ... every single image output to land in the sandbox ...
more visual analytics languages ... dynamically size those graphs ... like a container ... savable
dashboards that ... open up with the workspace." The owner's choices: images come from Python (the
agent's or the user's draws the figure and sends the picture; SwissArmyGrid never runs agent code, so
no milestone 9); Plotly, Graphviz (DOT) and Apache ECharts besides Vega-Lite and Mermaid; the page part
first, the server part once the Cosmic Python refactor has landed.

- **Done (page):** the tab is Sandbox; a 12-column dashboard with 40px rows, each card resized from its
  corner grip (or the arrow keys on it), what it draws refitted to the card; renderers for Plotly
  4.2.0, ECharts 6.1.0 and Graphviz (@viz-js/viz 3.31.0), each loaded only when its first card draws;
  image cards (inline PNG, JPEG, GIF, WebP or SVG in an <img>, which never runs or loads anything);
  Plotly and ECharts take the theme's chart colours unless a figure sets its own.
- **Safety:** the grid page now has a Content Security Policy: only its own scripts, no inline
  handlers, nothing fetched from another host. Figures are cleaned besides: Graphviz and Mermaid SVG
  through svgSafe (no scripts, handlers, animations, embedded HTML or outside links); Plotly refuses map
  traces (they fetch tiles) and keeps only inline layout images; ECharts drops images, links, the
  graphic layer and the data view, and draws tooltips as text.
- **Done (server, 2026-11-13):** cards of no table (`POST /cards`: notes, figures, pictures, a table of
  its own rows; badged Python, Agent or Sandbox; they stay when grids close; the Sandbox's Add note
  makes one); `key` replaces a card in place, keeping its size and order; `sag.sandbox` (duck-typed,
  standard library only); a `vegalite` card for Altair, **refused from the agent** (Vega compiles its
  expressions and the page allows that; the agent has the checked `chart`), its data inline (any url or
  href refused, so it fetches nothing); `sandbox_formats` and `sandbox_add` with `file`, `key`, `size`
  and its own rows.
- **Done (2026-11-13): saved dashboards and their history**, with one change from the design below,
  **to confirm**: nothing is saved automatically. The rule is that nothing is written to disk except
  explicit exports, recipes and the audit log, and an automatic save or a daily snapshot would write
  chart points and table rows without a click. So a dashboard is saved on **Save** (Dashboards… in
  the Sandbox); saving the same name again adds a version (the last 60); History opens any version.
  Each card keeps what it showed ("frozen"), so a dashboard opens without its tables; a chart or query
  relinks to a grid on its table whenever one is open, by the table's name. The agent lists and reads
  (`sandbox_dashboards`); saving (it writes to disk), opening (it replaces the screen) and deleting are
  the user's. Still open: automatic save if wanted, a read-only look back ("Viewing 10 November"),
  comparing two versions (cards added, removed, changed), and one dashboard per workspace once
  workspaces exist.
- **Done (2026-11-13): data-bound figures.** A Plotly or ECharts card on a grid may carry a SELECT; the
  server runs it on the grid's view (its table's name reads the view, as in a SQL step; first 5,000
  rows) and fills the figure: Plotly trace fields that name a column, ECharts' `dataset.source`.
- **Next (server, after the refactor), the owner's follow-up:** "a sag command to push anything to the
  sandbox ... the script can push anything that is visual"; "the MCPs should be fully aware of what
  tools are available to build graphs and charts"; "an agent can push rendered markdown ... resizable
  like a text box"; "no gaps in MCP tools ... the agents will need to understand what they are looking
  at, what's available and what data they can plot with". The design:
  - **`sag.sandbox(thing, title=None, *, key=None, size=None, kind=None)`** in Python (standard library
    only; it duck-types what it is given): a matplotlib or seaborn figure (`savefig`, PNG), a Plotly
    figure (`to_json`), an Altair chart (`to_dict`, drawn as Vega-Lite), a graphviz `Digraph`/`Source`
    (`.source`), a PIL image, PNG/JPEG/SVG bytes or a file path, a DataFrame (a table card, first rows),
    Markdown text (a note), and Mermaid, DOT or ECharts text with `kind=`. Explicit, not every image:
    the script decides what is worth showing. **`key=`** names a card, so running a cell again
    replaces its card instead of adding another. Returns the card's id. `sag sandbox ...` in the
    terminal does the same for files.
  - **Cards not tied to a table:** a card from Python or the agent may belong to no grid ("Python").
  - **The agent's tools:** `sandbox_formats` (every card kind, its exact format, limits, a small
    example of each, and how sizing works: what it can build); `sandbox_add` for every kind, Markdown
    notes included (an image from a file path the agent saved, since the MCP server runs on the same
    computer); `sandbox_update`; `sandbox_layout` (sizes and order, to arrange a dashboard);
    `sandbox_list` describing each card (kind, title, size, the table it uses, a short summary of its
    content, never a whole image) so the agent understands what is on screen; `app_snapshot` of the
    Sandbox to see it.
  - **What data it can plot with:** the existing table tools (open tables, columns and types,
    profiles, `agent_query`) plus **data-bound figures**: a Plotly or ECharts card may name a table and
    a query; the server runs it (capped at 5,000 rows, as charts are) and fills the figure (ECharts'
    `dataset.source`, Plotly columns by name). Big data never passes through the agent, and the card
    follows the table's steps.
  - **Sizes on the server**, so a dashboard is the same in every browser; notes size like a text box.
  - **Saved dashboards:** the Sandbox is saved to disk as it changes and reopens when SwissArmyGrid
    starts; named dashboards save and open (`sandbox_save`, `sandbox_open`); once workspaces exist
    (plan phase 1), each workspace opens with its own. A card drawn from a table that is not open
    says so, and draws when the table is pushed again.
  - **Sandbox history and time travel** (the owner: "make the entire sandbox have a history where you
    can save snapshots of the sandbox at a period in time and you can time [travel]"): a snapshot is
    the whole Sandbox frozen, every card's size and place and the data it showed (a chart's computed
    points, a result table's rows, notes, figures and images as they were), so it opens later even
    when its tables are gone. Named snapshots on demand ("Save snapshot"), and one automatic snapshot
    a day (the day's first change); automatic ones trimmed to the last 60, named ones kept until
    deleted; files beside the saved dashboards. A timeline across the Sandbox steps back and forward
    read-only ("Viewing 10 November 2026, 09:14 · Back to now · Restore this"); Restore makes that
    moment the live Sandbox (cards reconnect to their tables when open, else keep their frozen
    picture) after snapshotting the current one first. Comparing two moments marks cards added,
    removed or changed. Agent: list, take and read snapshots; restoring is the user's click.

## Steel and Swiss army knife red (2026-11-13, the owner's request; confirm or change)

"Design the default theme in the app to be steel and Swiss army knife red." The light and dark themes
(and so "system", the default) are now brushed-steel greys with one red: `#c8102e` in light (5.9:1 on
white, white text on it 5.9:1), `#ff6b73` in dark (with dark text on red buttons).

- **Red is the brand and the main action:** the table's title, the open tab's top edge, primary and
  pressed buttons, the first chart series, and a thin marker line on the active row and column.
- **Steel is everything else:** surfaces, borders, the focus ring (dark steel in light, light steel in
  dark, so it never reads as an error), and where you are in the grid (steel fill, red line).
- **Errors keep a deeper red of their own** (`#a3141f`), always with words or an icon; danger buttons are
  outlined, primary ones solid.
- The tab bar has a slight brushed-steel gradient (`--steel-sheen`); the high contrast themes stay flat
  and unchanged. No cross, flag or other mark: colours only.
- **Open:** keep the old blue as a "Classic" theme in Settings if anyone misses it; the user guide's
  screenshots still show blue.

## The golden rule (2026-11-14, the owner)

"Every single thing that user can do the AI should be able to also do it for mcp." Asked how it
meets the old refusals, the owner chose: everything, no prompts. Built: every route serves the agent
but answering approvals and /blades/{name}/python (password values); 172 commands. Exports keep their
Allow (the owner's question named connections, blades, code and packages; exports were not asked
about). Open: whether exports should drop their Allow too.

## Connections, the SQL cell and the Workbench (2026-11-13/14, the owner's requests; built)

Plans/workbench-and-connections.plan.md. The owner's answers: connections are databases and files
(vaults and secrets stay blades); adding one is a form per type with the code underneath; the Workbench
(notebooks, scripts with a console, connections, the data explorer, blades) always opens in its own
window from its tab; an IPython kernel behind our own editor (jupyter_client and ipykernel approved);
scripts are an editor with a Python console. Connections share the blade store rather than a copy of it.
Then (2026-11-14): the Workbench completes as you type (kernel for Python, the data explorer's catalog
for SQL cells); a connection's password comes from the keyring, an environment variable or a key vault;
each notebook can have its own environment, made from library presets and remembered. Open: inline
suggestions written by an AI model (the owner mentioned GitHub's code completion; not asked yet).

## Packs: blades and tangs from a Claude Code plugin marketplace (2026-11-13, the owner's idea; built)

"Use the Claude marketplace to source blades and tangs, so they could be stored in a GitHub repo and
collaborated with." From the Claude Code docs (code.claude.com/docs/en/plugins/: create-marketplace,
marketplace-reference, manifest-reference, install, loading, org):

- A marketplace is a repository with `.claude-plugin/marketplace.json` (name, owner, plugins); each
  plugin is copied as a unit into `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` on install
  (the root can be moved with `CLAUDE_CODE_PLUGIN_CACHE_DIR`), so folders Claude Code does not
  interpret, such as `blades/` and `tangs/`, travel with it. `claude plugin list --json` and
  `installed_plugins.json` give the install paths; `enabledPlugins` in the settings says which are on.
- Updates: `/plugin marketplace update` fetches the repository; with no `version` in the plugin, every
  new commit is an update (its version is the commit), with one, the string must change.
- Team-wide: a project's `.claude/settings.json` `extraKnownMarketplaces` makes the marketplace known;
  each person still installs once; only managed settings install automatically.

The design:
- **A pack** is a plugin with `blades/` and `tangs/` (and, if wanted, the SwissArmyGrid skill and MCP
  server). SwissArmyGrid finds installed, enabled packs and lists their blades and tangs with the pack
  and version; read-only (the installed copy is replaced on update): Save a copy into your own blades or
  a blade folder.
- **Collaboration is Git:** clone the marketplace repository, add the clone as a blade folder (already
  works), save blades and tangs there, commit, pull request, merge; teammates update.
- **`sag pack new`** scaffolds a marketplace repository (marketplace.json, one pack, README with the
  commands); **Add to pack** copies chosen blades and tangs into a pack folder. SwissArmyGrid's own
  repository may become a marketplace with an example pack on the made-up store.
- **Trust:** a pack blade is the marketplace maintainers' code, trusted as installing any plugin is;
  it runs only when used, and always shows its pack.
- **Built as designed**, and this repository is now a marketplace (`swissarmygrid`: the skill and the
  agent tools; `sample-store`: the example pack). Decisions made on the way: the pack routes and the
  Packs window are the user's (the agent cannot list or change packs); Add to pack writes only into a
  pack inside the blade folders, keeps existing files unless asked to replace, and New marketplace
  refuses a folder that is not empty; packs carry no `version`, so every commit is an update.
- **Open:** Claude Code's `installed_plugins.json` is not documented, so it is read loosely, with a
  scan of the cache as the fallback; check it again when Claude Code changes. A project's
  `extraKnownMarketplaces` could be offered from the Packs window so a team's repository suggests the
  marketplace by itself.

## Tangs and the relationship finder (2026-11-13, the owner's requests; confirm or change)

"The hardest part of my job is trying to determine how two tables relate to each other"; "a name for
relationships that are saved"; "a different file format ... so they're not confused with other json
files and you can run them in the application to make sure they work"; "if I discover a relationship
my coworkers have no way of knowing: share relationships in the same way we can share blades".

- **The name is the owner's: tangs.** A saved set of relationships is a tang (the part of a blade that
  anchors it into the handle). The `.tang` file is JSON that must start with
  `"swissarmygrid": "tang", "format": 1`, so no other JSON file is taken for one, and a newer format is
  refused by name.
- **Shared like blades, through the same folders:** the blade folders are searched for `.tang` files
  (four levels deep, hidden folders and environments skipped), so one team folder carries both. Save as
  tang writes to the person's own tangs or one of those folders, nowhere else. Older model JSON still
  reads.
- **Who and when:** a tang keeps its saved time and, if the person writes it, who saved it; never read
  from the computer. Each join keeps its evidence ("Found 2026-11-13: 91% of values in customers, 201
  orphans").
- **Running a tang** checks each join in the open tables (each dataset as pushed, before a grid's
  steps): holds, holds with orphans, broken, not open; a column's type change since saving is noted.
- **The finder's rules** (domain/relationships.py): the key side unique; 80% of the other side's values
  in it; names that point at the key; a key with under 50 values needs a name match; two counters from 1
  need coverage; floats and booleans are never keys; two-column keys searched among key-like columns
  only (a price is the most varied column of an order line); implied joins dropped; of two joins
  between the same tables, the first column's is active. Scored on the made-up store's answer key: all
  ten, no decoys.
- **Rejected suggestions** are remembered while the server runs, not across restarts.
- **Open:** keys of three columns found by containment alone; foreign keys read from a loaded catalog;
  the relationships view of plan phase 4 (draggable tables).

## Fill in your values (2026-11-12, the owner's request; confirm or change)

"Have blades auto detect ... the variables that are defined inside of the blades, so when somebody imports
a new blade it will suggest what variables to enter."

- **Read from the code, not declared in the header.** Any blade works, with no extra writing by its
  author; a header list would go stale the moment the code changed.
- **What counts:** connection keyword arguments (`host=`, `port=`, `dbname=`, `user=`, `account=`,
  `warehouse=`, `http_path=`, `vault_url=`, ...); the known parts of a connection string (Server,
  Database, UID, DSN, DBQ, Driver, Port, HOSTNAME...); top-level names given a literal or `Path(...)`; a
  path passed to `connect`, `read_csv` and the like. Never anything named like a password, token or key.
- **Placeholders:** `my-`/`my_`/`your-`, `example`, `<...>`, `changeme`, and a starter's own example path.
- **Suggestions:** the same setting in the user's other blades (most used first), then a short list of
  standard environment variables (`PGHOST`, `SNOWFLAKE_ACCOUNT`, `AWS_REGION`...), never a password one.
- **Writing back** replaces only that value's characters; a raw string stays raw; a backslash in a plain
  connection string is written doubled; a value that would break the code (a `;` in a connection string,
  a line break) is refused with a plain message.
- **Open:** suggestions from a loaded catalog's server name; settings for the agent's `blades_create`
  (it already lists them in the approval window).

## The agent makes blades (2026-11-12, the owner's request; confirm or change)

"Make it possible for the agents through MCP to create blades for you." Three commands:
`blades_list`, `blades_templates` and `blades_create`.

- **A proposal, saved on Allow.** It uses the same approval window as an agent export, now also on the
  blades page and the notebook tab. The window shows the blade's whole `.blade.py` file (the code
  included), what it imports that isn't installed, and that its code runs whenever the blade is used.
  Saving runs nothing. An unanswered request is declined after 3 minutes.
- **What the agent still can't do:** read an existing blade's code, catalog command or secret status
  (`blades_list` gives names, kinds, descriptions, tags and the `sag.blade` line); send a secret's value
  (refused; the code says `secret("password")`); choose a blade folder (ignored, so a blade lands in the
  app); replace, change, remove, refresh, test or run a blade. A taken name is refused before the user is
  asked.
- **Open:** letting the agent edit a blade it made (behind the same Allow) and offering "save into a blade
  folder" in the approval window.

## Portable blades (2026-11-12, the owner's requests; confirm or change)

"A way to import a blade ... a format to make them portable", "blade folders that the app could search",
"a format or frontmatter" to tell blades from other Python, "descriptions and tags", and "pin blades
to favorite".

- **The frontmatter is a comment block**, `# /// swissarmygrid-blade` ... `# ///` holding TOML, the
  same shape as Python's inline script metadata (PEP 723), so a blade file stays a runnable, lintable
  Python file and Git diffs read well. It must open the file: a header further down does not count,
  so a file that merely mentions the marker is never taken for a blade.
- **`.blade.py` is the suggested name, not the mark.** In a blade folder any `.py` file that starts with
  the header is a blade; the name is only for people.
- **Secrets travel as names only.** An imported blade asks for its values on its save screen.
- **Folder blades are the folder's.** Saving writes the file back (the header is rewritten, the code
  kept); the app never deletes one. A blade saved in the app wins a name clash with a folder blade,
  and the clash shows in import as "already exists".
- **Favourites are per computer** (`blade_pins.json`), never in the shared file, so one person's pins
  don't travel to a team folder.
- **Open:** a tag-only view (group the list by tag) and a "pull from Git" button for a folder are not
  built; the search and tag chips cover finding a blade for now.

## Privacy levels removed (2026-11-12, the owner's decision)

"Remove the privacy levels from the app." The agent now always sees everything, as level 3 gave.

- **Removed:** levels 0 to 3 and their picker in Settings ("What the agent may see"); column masks
  and the column-lineage tracer that existed only for them (server/masking.py, the context's
  `derived_columns`); the level-0 checks (server/level_zero.py, `ctx.agent_made`,
  `Grid.agent_steps`); step-value hiding (server/step_privacy.py); row-read approvals ("Run row
  reads without asking me"); engine error text hidden by level (the EngineErrorRedaction
  middleware); the PIVOT refusal; `min_level` in the command registry and the catalog's
  `available` flag; `/agent/policy` and the `agent_policy` command; `privacy_level` and `masked`
  in agent results.
- **Kept, since they are security rather than per-level privacy:** an agent export still waits for
  the user's click and is written only against the one-time ticket that click gives
  (`routes_agent.ExportTickets`); the approval popup and `/agent/approvals`; the token on every
  data route and the Host/Origin guard; `X-Actor: agent`; the agent activity list (the audit log);
  `<untrusted-data>` wrapping of values in MCP results; an agent never gets the token (URLs come
  back without it); every `/blades` route refuses the agent; the routes that were always the
  user's alone (approving, `/workspace/active`, the snapshot upload, the Key Finder's value
  samples, shutdown, the audit log).
- **Reads are capped at 1,048,576 rows** (one Excel sheet), as level 3 was.

## Agent privacy hardening (2026-11-12, superseded the same day: the levels were removed)

- **Approved agent exports are masked.** The file follows `/agent/read`: masks traced to the source
  columns, level 1 text masking, the level's per-read row cap (20 / 200), and level 0 exports only
  `scope=profile`. One click is one read's worth of rows, since the agent can read the file back.
- **Step values at level 0.** Every agent view of steps (tabs_get, view-state, context, the step
  commands' answers) shows the same redacted form (server/step_privacy.py). Chosen over refusing
  the steps_* commands at level 0: the server applies one change by index or id
  (`POST /grids/{id}/step-ops`), so the commands never read values back. A redacted list posted back
  unchanged keeps the user's values; a half-edited one is refused.
- **Level 0 SQL rule** (server/level_zero.py): a non-number column (text, date, boolean, list,
  struct, JSON, anything untraced) may only be counted, grouped by without being returned, tested
  with IS NULL, or passed through. Functions, casts, comparisons, sorts, set operations and
  PIVOT/UNPIVOT on it are refused in agent SQL, steps, table cards and charts. Number-ness follows
  the data: a number the user computed from text (`length(client)`) is not a number column.
- **Open, by choice:** sort steps on text are allowed at level 0 (they change only what the user
  sees; with a limit step they reveal row order, not values), though `ORDER BY text` in agent SQL
  is refused. `table_matching` switches change how the user's own hidden filter values match, so the
  row count can move. The Key Finder's "longest value is N characters" equals the profile's
  `longest`, which level 0 already shows. Key Finder and compare skip agent-made tables and grids
  with an agent SQL, bucket or categorize step, since they can hold values the agent chose.

## Next: grid tabs, split view and compare (to plan)

Asked for on 2026-10-22: grids open as tabs in one window instead of new browser windows (move,
close, reorder), dragging one tab onto another splits the view into two grids side by side (the
side panels follow whichever grid was clicked last), and a Compare group on the ribbon lines the
two grids up by primary keys for an anti join, an outer join or a cross compare. This changes
the page from one grid per page to several, so it gets its own plan before any code.

## Not built (yet)

- Milestone 9, the agent Python sandbox: the plan says ask first.
- The VS Code extension ("View in grid" on a file or a debugger variable) and the Jupyter
  display hook: the plan lists them as extras after M4.
- A SQL box query that joins another dataset can't be a step (see above); pinning it works,
  but the pinned grid's Python starts from the pinned result.
- Splitting an export across several Excel sheets: an export over the row limit is refused
  with a message instead.

## Known gaps in the first M1 slice (most now closed)

- JSON push loses types: dates arrive as ISO text and decimals as strings. The Arrow push format
  fixes this and should come next.
- No `gen` request numbers yet; AG Grid drops stale blocks on its own for now.
- The dataset (50) and grid (20) count limits, and the 500-character cell truncation, aren't
  enforced yet.
- No Content-Security-Policy header on the page. Worth adding; AG Grid's theming API injects
  style tags, so it needs a nonce or `style-src 'unsafe-inline'`.
- The bundle registers `AllCommunityModule` (1.1 MB). Register only the modules in use.

## Review notes on the plan itself

- Section 0 rule 7 and the M0 check say "section 12" for the verify list; it is section 17.
- The push client's size pre-check uses pandas `memory_usage(deep=True)`, which overstates text
  columns compared with the Arrow size the server measures, so it can refuse frames the server
  would accept. Measure with pyarrow when it's installed.
- The push client doesn't validate or escape the dataset name before putting it in the URL, uses
  a 10-second timeout that a large push can exceed, and reports a stale connection file (left by
  a crashed server) as a raw connection error.
- Four implementations per operation (engine + DuckDB, pandas and plain-Python generators) is a
  lot of work for M4 and M6. Consider shipping the DuckDB generator first and adding pandas only
  when someone needs it.

## The fit test and outliers (2026-11-13, the owner's request; built)

"A chi-square goodness of fit I can quickly use on a set of columns, and a quick outlier deviation
analysis where I can find the liars within a column, by frequency or amount."

- **Where:** the Column row (Fit test on the selected columns, Outliers on one), and the agent tools
  `column_fit_test` and `column_outliers`. Domain math and query text in domain/analysis.py; no new
  dependency (the chi-square p-value is the regularized incomplete gamma, tested against textbook
  critical values).
- **Fit test:** even, Benford first digit and first two digits (with Nigrini's mean absolute
  deviation ranges), another grid's column, the caller's shares, and two columns together
  (independence, Cramér's V). Every result gives an effect size in words beside p, because with
  many rows any difference is significant. More than 200 values: refused, with "bucket it first".
- **Outliers by amount:** robust (median and median absolute deviation, Iglewicz and Hoaglin's 3.5;
  falls back to the mean absolute deviation when over half the values are equal), Tukey's quartile
  fences (1.5), or z-scores (3); optionally within each group of another column (groups under 5
  values are not judged).
- **Outliers by frequency:** a value is flagged only when its count is unusual on two scales, and
  its score is the weaker: against the other values' counts on a log scale (natural popularity
  differs by a few times), and against counting noise (Anscombe's square-root transform, where chance
  is one unit wide). Neither alone worked: the log scale alone flagged 990 among values seen 1,000
  times; noise alone missed a typo seen twice among values seen 500 to 2,000 times. Checked on four
  made-up shapes in tests/test_analysis.py.
- **Show these rows** is a SQL step with the fences written as numbers (frozen when found), not a
  live subquery: a plain `SELECT * FROM grid WHERE ...` keeps the grid's row order, while a subquery
  would make the guard sort by every column. Pushing new data does not move the fences; run Outliers
  again for new ones.
- **Open:** a Sandbox card for a fit test's bars; a "Flag as a column" choice (a categorize step)
  beside Show these rows; outliers by date (gaps, a burst on one day).

## Marimo stripped (2026-11-13, the owner's call)

"Strip marimo: it's heavy and not well adopted. Jupyter and Python in the terminal." The notebook tab,
its blade rail, the /marimo proxy, the notebook cookie and the marimo dependency are gone. To notebook
became **To Python**: the code is copied and queued (in memory, the last 20) and `sag.paste()` in
Jupyter or IPython puts it in the cell (set_next_input, replacing the cell that ran it) or at the
prompt; plain Python prints it. The agent can't queue code (it would land in the user's kernel). The
grid's automatic code-behind for notebook tables went with the tab; To Python is a click. Lost:
dropping a blade straight into a cell (drag gives its text instead) and Save as blade from a cell.

## The name off the screens (2026-11-13, the owner's request)

"The words Swiss army grid should appear nowhere in the app." Gone from every page title (the browser
tab names the grid in front: "orders", "Key Finder · orders"), the Application row's caption, the
bottom bar's credit (now "Created by Dylan Brown"), the Sandbox's empty state, the markdown export and
chart HTML footers, generated code's header comments, and the messages the page shows. Kept, because
changing them breaks installs or stored data: the package, `import swissarmygrid as sag`, the
`swissarmygrid` and `swissarmygrid-mcp` commands, the `~/.swissarmygrid` folder, the vault's service
name for blade secrets, browser storage keys, and the Parquet provenance key. The MCP server and its
agent guide still use the name (the agent's view, not the app's); to confirm.

## Chart furniture (2026-11-13, the owner: "no love given to legends and labels")

Every Plotly figure now gets its furniture from the renderer (lazy/plotly.ts), under whatever the
figure sets: a thin axis line with small outward ticks, quiet tick labels with thousands separated,
light dotted grid lines, the axis title in the muted ink with room made for it, the legend across the
top from the left, a hover label in the theme's colours. Figures from Python get the same unless they
say otherwise. Time series and forecast: the data in ink (red is the alarm colour), the trend and the
forecast in the accent, the x axis untitled (dates speak), labelled marker lines ("Level stepped",
"Held back to test", "Forecast"), one hover box per date. The summary above a chart is a calm box
(the first sentence as its headline), not the red "doesn't fit" box. The season is a diverging bar
list around a typical period; numbers are rounded to four significant figures throughout.
`theme:accent/0.2` names a theme colour seen through, for bands.

## The Workbench's error panel (2026-11-14)

The owner: "make the inline error trapping and stack tracing the best part of this app ... I love the
Visual Studio style hover error panel." Research (an agent's survey of IDEs and libraries, kept in the
session's notes): Visual Studio's Exception Helper and PyCharm's frames-and-variables set the bar; no web
service may see the user's code or data, so nothing leaves the computer.

- **What it uses:** stack_data (MIT, already in every kernel's Python: IPython needs it) for the failing
  expression's values, and the standard library's `traceback` for columns, chains and Python's own "Did
  you mean". No new dependency. A Python without stack_data still gets the frames, without values.
- **Not taken:** friendly-traceback (last release 2022; its idea of plain explanations inspired ours,
  written anew for data work), rich and better-exceptions (terminals), any web API.
- **How:** after a failed run the server asks the kernel (a silent user expression, before another run
  can change anything) for the error taken apart; domain/errors.py adds the words and fixes. The
  notebook still saves Jupyter's standard error record; the panel's reading is never written to disk.
- **Open:** "Rerun with the debugger" (ipykernel's debugpy) is a bigger step: ask the owner first. A
  Problems list for the window, the peek view under a script's line, DuckDB's `errors_as_json` on the
  app's own connections.

## Open: two browser tests that fail only in the full run (2026-11-14)

`test_the_grid_scrolls_freely_through_a_column_wider_than_the_view` (the first wheel notch scrolls
nothing) and `test_key_finder_ranks_join_columns_with_percent_match` (the result table's header shows
"Other table" where the compared table's name belongs) failed in two full runs, but pass in
`pytest tests/e2e` (130 of 130) and alone. Worth finding which earlier test leaves state behind.

## Key vaults are connections (2026-11-14, the owner's call)

"It should be able to add an Azure password vault and then map the needed secrets in it directly into
environment variables for the workspace", then: "Key vaults should be another connection, not a blade."
So a vault blade (kind `vault`) is a third kind of connection beside databases and files: made in the
Connections window, listed there under Key vaults with its entries, marked a connection on the blades
lists. It is not a variable in the Workbench and not a SQL cell's source (its secrets are already
environment variables there). Read the vault calls the vault code's `names()` (the starters for Azure,
AWS Secrets Manager and Parameter Store, Google and a `.env` file have one) in a child process and
answers names only; the user ticks the ones needed. Every Workbench kernel starts with every vault's
entries in its environment: the server runs the vaults in a child process as the kernel starts (60
seconds at most) and passes the values into that kernel's environment, the one place values cross the
server. They are never saved, never in an answer to the page or the agent, never in the audit log (it
records the variables' names). A vault that fails is named in a message and the kernel starts without
it. A restart keeps the variables (jupyter_client reuses the environment). Open: a vault that is slow to
sign in slows every kernel's start; caching the values for the session was left out on purpose.

## A vault's secrets under their own names, every one (2026-11-14, the owner's call)

The point (the owner): "develop your Lambda or Azure Function apps with a vault and use the same exact
credentials that you'll be using in the cloud on your local machine", and "why don't we just import the
names right out of the vault". So a vault may load every secret it holds (`vault_all`, the default for a
new one): its names() is read each time a kernel starts, so a secret added later is there next time, and
each is a variable under its own name, case kept (SqlPassword), `--` as `__` (Azure's convention for a
section, as .NET configuration reads it), any other character a variable cannot hold as `_`. The mapping
then only renames. This replaced the upper-case suggestion (warehouse-password -> WAREHOUSE_PASSWORD):
the vault's own name is what the cloud's code most often reads. A vault whose code has no names() cannot
load every secret and says so. The Variables pane lists what the vaults set at the last kernel start
(names only), since such a vault names its variables only when it runs.

The hybrid (the owner, 2026-11-14): "whenever you add a vault it gives you a list of the secrets names and
you can choose to map those to environment variables or you can just leave them as is". So the vault's
form reads the list itself once it can (every setting filled in, or a saved vault opened to edit), and a
secret's box starts empty with the vault's name as its placeholder: empty means that name, typed means
mapped.

## Trino: a linked .pem and SSL (2026-11-14, the owner's request)

The starter is https with a password (BasicAuthentication) and a certificate file, and passes trino its own
requests session with trust_env off: otherwise REQUESTS_CA_BUNDLE wins over the linked .pem. The cost:
that session also ignores HTTPS_PROXY, so a Trino reached through a proxy needs `session.proxies` set in the
code. Open: signing in with a client certificate (trino.auth.CertificateAuthentication, a .pem and its key)
instead of a password, as a second starter, if the owner wants it.

## Sign in three ways; Trust server certificate (2026-11-14, the owner's request)

"We need a trust server cert checkbox. Also the Azure and SQL Server connections should allow MFA and
basic as well as Windows login." A starter may carry several ways to sign in (Template.sign_ins: label,
a text only that code holds, the code); the form's Sign in swaps the code and fills the new one with the
values typed so far (by setting name; a value still a placeholder is not carried). SQL Server: Windows
(Trusted_Connection), user name and password (UID and PWD={secret}: braces, so a password may hold ;),
MFA (ActiveDirectoryInteractive). Azure SQL: MFA, user name and password, Windows (ActiveDirectoryIntegrated).
On/off settings are checkboxes: TrustServerCertificate and Encrypt in a connection string (yes/no),
trust_server_certificate in code (True/False); no other True/False becomes a field. The starters now say
TrustServerCertificate=no (they said yes): a server with a self-signed certificate needs the tick.
Open: one Workbench browser test (the console's step-by-step run, "row 1") failed once in a combined run and
passed three runs after; a timing race to look at.

## Catalogs load themselves (2026-11-14, the owner's call)

"We should auto load the catalog in a separate thread so it can background load and feed the
autocomplete." services/catalog_loading.py: each load is Refresh's own run (a child process, so the
server never waits), a few at once (settings.catalogs_at_once, 2), never twice at once for a connection.
When: a connection saved (who: the user); start-up, every connection but one that signs in with a browser
window or device code (ActiveDirectoryInteractive, externalbrowser...), which waits, and none past the
catalog limit; first use (a SQL cell's completion asks POST /connections/{name}/catalog once per page, the
agent's connections_load_catalog). A failure is kept with its reason and not retried unasked. The
Connections window redraws as loads land; only the newest draw paints (two overlapping draws had doubled
its buttons). Catalogs stay in memory: a restart loads them again rather than keeping table names on disk.
The tests' server has it off unless a test is about it (child processes in every test would slow the suite).

## The usability test and the owner's decisions (2026-11-14)

An agent drove every area of the app in a browser with made-up data against two rules from the owner: "if it takes more than 3 clicks or actions and can be reduced then it should be considered as an improvement", and placement ("if ... a feature isn't conveniently located beside the thing that it's controlling or two features work better side by side on the screen then it should be considered as well"). It found 20 improvements and 11 bugs; the owner chose, one at a time:

1. Open a file: "Open file…" button beside "+" (app file picker) AND drop a file anywhere on the page. Workbook with several sheets: ask which sheets (first ticked), each ticked sheet its own tab. **Built (rounds 1 and 2).**
2. Open as grid: on the catalog table (tree and page), on a file connection's row, and in the catalog tree's right-click menu. Row limit: configured per connection, with a clear warning on the grid that it is truncated, the source's full row count, and a button to retrieve all. The catalog table page shows a preview of the first rows beside its column list. **Built (rounds 1 and 2).**
3. Column tools: double-click a header to rename in place; Sort A to Z, Sort Z to A, Filter…, Rename…, Remove, Keep only, Group by… in the header's right-click menu (above the analyses); the Column row's Rename… opens only the selected column, focused. No header menu button. **Built (rounds 1 and 2).**
4. Step forms: cursor in the first empty field, Enter presses Add step, Escape closes. (No prefill from the cell.) **Built (rounds 1 and 2).**
5. Compare: keep the tab drag; add "Compare with…" on a tab's right-click (NOT a Table row button). Diff: both halves scroll together to the first differing column; "Only differing columns" toggle, on by default (key + differing columns). Keep the compare across a reload; prefer the key unique on both sides. **Built (round 3).**
6. Analysis defaults: never default to an identifier column; Time series and Forecast start on the row count; others on the first number column that is not an ID. **Built (round 3).**
7. Regression: every column but the target and IDs ticked to start. **Built (round 3).**
8. After sending: the window stays; the toast has a Show button that closes the window and goes to the destination. Open as grid closes the window and shows the new tab. **Built (round 3).**
9. Reopen: each closed table in the Datasets list gets Open (the original, not a copy); the list moves to the ≡ button beside "+" in the tab strip. (No Ctrl+Shift+T. Finders and closed tables: not chosen here; raise again with the bugs.) **Built (round 3).**
10. Paste: a name box in the "Pasted" toast (cursor in it, Enter); double-click a tab's title to rename that table everywhere. (No "paste here" line.) **Built (rounds 1 and 2).**
11. File connections: Name filled from the picked file (and used by Test when empty); Test shows the first rows and the columns. (Placeholder paths and the word "blade" not chosen.) **Built (round 3).**
12. Driver: an Install button beside the "not installed" note in the Connections form; the form updates when done; the command stays visible. **Built (round 3).**
13. Vault picker: "Entry in the vault" lists the vault's secrets by name (read in the background); picking one applies it. **Built (round 3).**
14. Database forms: Server, Port, Catalog/Database; then User and Password; then Certificate file and Trust server certificate together. Same order on every database form. Label the password box. **Built (round 3).**
15. First save: create the SwissArmyGrid folder in the home folder the first time it is needed. **Built (round 3).**
16. Workbench: Open as grid on every table output (DataFrame, SQL result); in a notebook the console starts as a thin bar and grows when used or dragged; New notebook puts the cursor in the first cell. (Variables icon unchanged.) **Built (rounds 1 and 2).**
17. Steps: Ctrl+Z undoes the last step, Ctrl+Y / Ctrl+Shift+Z redoes; the strip counts a header sort as a step; hovering "N steps" lists the steps in plain words, each with a remove ×. (No recipes list.) **Built (round 3).**
18. Keyboard: Ctrl+Shift+P command palette on the grid page (every grid-page action); Enter / F2 on a cell opens the value viewer. (No Alt+G, no access keys.) **Built (round 3).**
19. Settings: a header-profiles toggle in the grid's top-left corner (above the row numbers); one zoom for the page, the Sandbox included. (Theme stays in Settings; the tour pill stays.) **Built (round 3).**
20. Relationships: the diagram fits the window when drawn plus a Fit button; Key Finder rows get "Compare on these" and "Add as relationship"; one name for the relationship file everywhere: "Import relationships". **Built (round 3).**

Bugs: fix all 11 (Workbench: SQL error panel "s.notes is not iterable", new SQL cell's connection box; Connections: empty-Name Test message, stale "Not installed" note on a vault; Compare and relationships: Diff jump scrolls only the left, Find relationships includes closed tables and both directions of a pair, Key Finder crowns ship_date over order_date, compare lost on reload, wrong key pre-ticked; Server: stop lingers and crashes on open long-polls). Kernels of a closed Workbench window stop a minute after it closes.

**Round 3, built on 2026-11-15** (decisions 5 to 9, 11 to 15 and 17 to 20; docs/verified.md has what was
checked). Decided while building; confirm or change:

- **5. Compare.** A tab's right-click menu has Compare with…, Rename and Close. With one other table
  open, Compare with… takes it at once; with several it lists them. The right-clicked table goes on
  the left. *Only differing columns* is a toggle in the Compare row, shown in Diff mode, on to start;
  it is the compare's own option (`diff.only_differing`), so the agent sets it and it survives a
  reload, and it does not join the two sides again. Both halves scroll sideways together **by column,
  not by pixel** (each side sizes its columns to its own values). "A compare survives a reload": the
  page remembers which compare is its own; the server kept it all along, and a compare whose grid
  has closed is now stopped and its table dropped. The key ticked to start is the best pair that is
  **unique on both sides** and covers half of either table, else the best pair that covers half
  (`preferred_key`); a known relationship still comes first.
- **6. An identifier** (one rule, `domain/analysis.py is_identifier`): by name, a column whose last
  word is id, key, uuid or guid (a *number* column also: number, no, num, nr, code, zip, postcode,
  phone); by its values, a whole-number or text column where every one of more than 20 filled rows
  is different (counted over the view's first 10,000 rows). A date or a number with decimals is never
  one. **A column the user selected first is still used as it is,** identifier or not: for Time
  series and Forecast that means a number column whose *header* is selected (not a clicked cell).
- **7. Regression.** The ticks follow a change of target until the user touches a box; then they stay.
  A text column with a different value in every row (a note, a name) is an identifier by the rule
  above, so it is offered and not ticked.
- **8. After sending.** Show closes every open window, goes to the Sandbox and outlines the card for a
  moment. Toasts raised while a window is open now sit inside it (a modal window makes the rest of the
  page unusable, so a toast's button could not be pressed). Open as grid also closes the Connections
  window on the grid page. In the Workbench's window the grid is another window, so nothing closes
  there, and the Key Finder's own window has no Sandbox tab, so its toast has no Show.
- **9. Reopen.** The list is called **Tables** (the button's name; it was "Open a table from Python").
  Open on a closed table makes a grid on the table itself. The bin removes a table from memory and
  asks first, as before. **The memory meter stayed in the status bar** (principle 5.9 puts it there,
  only past 80% of the budget) and a click on it opens the list; the budget's numbers, which the old
  Datasets list had, moved with the list.
- **11. File connections.** Test shows the first 20 rows. A workbook shows its first sheet; a folder
  has no one table, so no preview. A file that cannot be read still passes its test (it is there) and
  says why its rows could not be shown.
- **12. Driver.** Install puts the packages into the app's own Python (where Test and Refresh run).
  The command stays in view until the install is done; then the note goes, since nothing is left to
  do (principle 7.9).
- **13. Vault picker.** Entry in the vault lists the vault's saved entries and every secret it holds;
  picking applies at once. "A secret by name…" stays, for a vault that does not list its secrets.
- **14. Database forms.** The rule is `domain/connections.py form_order`: server (or account,
  project, data source, path), port, catalog, database, then anything else in the code's order; the
  user (after Sign in, where a type has several ways); each password as two labelled boxes ("Password
  comes from", "Password"); then encrypt, the certificate file and Trust server certificate.
- **15. First save.** The folder is made when the file chooser first looks at it (the Workbench's Save
  and Open start there), as well as on a save into it. Only that folder is ever made.
  `SWISSARMYGRID_WORKBENCH_DIR` sets it, for tests.
- **17. Steps.** Undo takes back **the last change to the steps**, whatever it was (a step added,
  removed, edited, switched off or moved, the steps cleared, a header sort, a step a chart or a
  tie-out added), 100 changes deep, for each grid; a new change ends what can be redone. The strip's
  Undo used to drop the last step in the list; it is the same undo now, with Redo beside it. A
  header's two clicks (ascending, then descending) are two changes. The steps list opens on hover,
  focus or a click, and a step that is switched off is listed as off.
- **18. Keyboard.** The palette is the Workbench's, fed from this page's own buttons each time it
  opens, so a button added to a row is a command the same day. Also listed: the Analyze menu's
  entries, the tabs, and the cell menu on the cell in front. **No agent command was added for the
  palette itself:** every action in it already has one.
- **19. Settings.** The corner holds the profiles switch and, in the room left, Select all as before.
  The Sandbox's own zoom control is gone.
- **20. Relationships.** The diagram also follows the window's size while fitted. **Actual size was
  added beside Fit** (not asked for): without it Fit had nothing to undo, and a large diagram fitted
  to a small window cannot be read. Compare on these puts the two tables side by side *in the grid
  window* (the Key Finder has its own). Import relationships takes a .tang (reviewed first) or a
  model as JSON, in both places.

**Where a decision met a later one, and what was done:**

- Decision 9 said the memory meter "moves with the list" if it lived in the Datasets list. Since the
  cleanup the meter shows only past 80% of the budget, in the status bar (principle 5.9). It stayed
  there, and a click on it opens the list; the budget's numbers moved with the list.
- Decision 17's strip had "Undo (the last step)". With a real undo that button would have been a
  second, different undo beside Ctrl+Z, so it became the same one.
- Decision 18 says "every grid-page action". The Cell row is gone (the cleanup), so a cell's actions
  are listed from its right-click menu, on the cell in front. Send the row to Sandbox is not listed:
  it needs the row a right-click gives.
- Decision 8's toasts and principle 7.9 (no confirmation labels): "In the Sandbox: …" and "Opened as
  …" are on the cleanup's list of real feedback, so they stay; Show was added to the first.
- Decision 19 takes a setting out of Settings; the theme stays there, as decided.

**Also fixed in round 3:** the file chooser put the first folder's path in front of a path being
typed (one browser test in six failed on it); `blades_install` sent a bare list the route refused;
Ctrl+Z outside an editor in the Workbench could reach the browser's own undo and change an editor's
text unseen (what the HTML cell's "undo works only right after Edit HTML" turned out to be: the
editor's undo was never broken, it takes typing back a few words at a time).

## Every table has a read-only cell: its transformations in DuckDB SQL (2026-11-14, the owner's calls; built)

Replaces an Apply-button idea from the same day (dropped: a button far from the grid, a "did I press
it?" state, and a notebook that no longer held its own transformations). The owner: "Transformations
are read only and always appear as the last steps in a table cell with the output always being the
original table name. Transformations are not two way and table cells are read only. Transformations
should be code behind in the read only cell using duck db." Decided:

- **Every table, always,** has its own read-only cell in the Workbench notebook or script it belongs
  to, from the moment it exists. In a script it is a `# %% [table] orders` block closed by a plain
  `# %%` (the cell marker VS Code, Spyder, PyCharm and Jupytext read), so the file still runs as Python.
- **Only the transformations are in it,** as one DuckDB query, ending in the table's own name:
  `orders = duckdb.sql("""SELECT ... FROM orders ...""").df()`. The code that made the table stays the
  user's own editable cell. A table no code made (a file, a paste, a connection) has its load first in
  its cell, then the transformations as the last lines.
- **One way only.** Transformations are made in the grid; the cell follows and is never typed in.
- **DuckDB covers them all:** the grid's 11 step kinds (filter, sort, columns, rename, group by,
  distinct, limit, transform, bucket, categorize, SQL) already compile to one DuckDB query
  (domain/steps.py compile_view), the query the grid itself runs; the generated DuckDB code is already
  checked against the grid's rows. The pandas and plain-Python translations can go.
- **Nothing runs by itself.** A grid change rewrites the cell at once and turns it yellow: "Out of
  date · last run 10:42 · Run". The variable changes when the user runs it. The cell keeps the code it
  last ran and compares the text, so undoing a change clears the yellow by itself. "Not run yet" before
  its first run; "Not run since opening" after a reload.
- **All tables at the top, in a Tables group** (replaces "under its maker"). Each table is a group of
  its own: the user's cell that made it (still theirs, editable) and its read-only transformations
  cell, moved together, so the file still runs top to bottom. The group orders itself: the imports the
  tables need first, then each table after the tables it is made from (a join after its two sides).
  Collapsed, a table is one line ("orders · 3 steps"; see the rule on confirmation labels below);
  the whole group collapses to one line ("Tables · 4 tables · 1 out of date"), so the user works on their script without scrolling past
  transformations. It **starts collapsed** when a file opens, and the line turns yellow when any table
  inside is out of date. In a .ipynb the groups are markdown headings ("Tables", one per table), which
  JupyterLab also folds; in a script they are `# region Tables` / `# endregion` (VS Code folds them)
  around `# %% [table]` and `# %% [transformations]` cells.
- **A maker that cannot move stays put, marked.** When the cell that makes a table needs something the
  user's code defines further down (a helper function, a variable), that table's cells stay where they
  are, and the Tables group lists it with a link: "orders is made at @cell7 (it needs make_dates)".
- **Every cell has a number that never changes,** given when the cell is made, never reused or shifted
  when cells move or go (not the run count `[3]`). Saved in the cell's metadata in a .ipynb and on its
  marker line in a script (`# %% [7]`), so it survives any editor. **A comment links to a cell as
  `# @cell7`:** a click in the Workbench jumps there, a hover shows its first line; elsewhere it is a
  plain comment.
- **The output is the table's own name.** So a second run never transforms an already-transformed
  table, the app keeps a reference to the original the maker cell made (no copy) and the table's cell
  always starts from it; top to bottom, the maker makes it and the cell transforms it once. Cost: the
  original and the transformed table are both in memory while working.
- **The copy buttons go:** Copy as SQL, Copy as Python and To Python leave the steps strip and are not
  moved anywhere; the table's cell is the code. (Open: the catalog's Script as also queues code for
  sag.paste; whether it stays.)
- **The uses line** (the owner, 2026-11-14). When one of the user's own cells (a notebook cell, or a
  script's `# %%` cell) names an open table, the app keeps one comment line at the top of that cell:
  `# uses orders @cell3, customers @cell5`. Each link goes to that table's read-only cell. The line
  follows the typing after a short pause, never moves the cursor or the text, and goes when the cell
  uses no table any more. Only that first line, recognised exactly by its format, is ever changed.
  Real Python names only: not in a string or a comment, not part of a longer name (`orders_2026`),
  not an attribute (`x.orders`). A table's own cell, its maker cell and Markdown cells get no line;
  a `%%sql` cell gets `-- uses orders @cell3`. It is saved in the file as an ordinary comment.

Proposed, not yet asked (not built): cells that use an out-of-date table get a quieter mark; the grid's
steps strip and the Variables pane say "Out of date in <notebook> · Run" too. Built with the rest, by
the golden rule: the agent reads what is out of date and runs a table's cell. Limit: a notebook in plain
Jupyter or a script in another editor cannot be written live, and with the copy buttons gone the grid has
no way into it (the steps window's Code tab still copies the query).

Built on 2026-11-14 (domain/table_cells.py, services/table_cells.py, client/table_cells.py,
web/src/workbenchTables.ts, the notebook and script views). Decided while building; confirm or change:

- **Which tables get a cell, and where.** A table is open when it has a tab in the grid. Its cell goes
  into the document whose kernel sent it; else a document that already holds its cell (its file); else,
  for a table no Python made (a file, a paste, a connection, a "+" tab's query), the document in front.
  A table sent by a Python outside the Workbench (Jupyter, a script in another editor, `sag.push` from
  a terminal) gets no cell: its code lives where the app cannot write (the limit above). Once a
  document has a table it keeps it; a table closed in the grid keeps its cell in the file ("not open in
  the grid"), and only then can the cell be deleted.
- **The maker** is the first of the user's cells that gives the table's name a value without reading
  it (found by reading the code with Python's own parser, not by watching runs), so a later
  `orders = orders.dropna()` is not the maker. A table whose name no cell sets (made in the console,
  a result opened as a grid) has a note in its cell instead of a load.
- **When a maker moves.** It moves with the imports it needs when those are in a cell of imports only.
  It stays put, listed with its reason, when it needs a name another of the user's cells makes
  (`it needs make_dates`), when a cell above it sets a name it also sets, when it needs a table that
  stays put, or when it is in a script's main code. Cells move only at calm moments (a table opened
  or closed, a cell run, a file opened), never while typing.
- **A script's main code is not a cell.** The code before the first `# %%` (all of a script without
  markers) never moves and has no number; the plain `# %%` after `# endregion` closes the group, and
  the main code follows it. A table made there is listed as "made in the script's main code" and its
  cell goes after that code. Marker form: `# %% [7] [table] orders Load the orders` (number, part,
  then the user's own words). A script's cell numbers continue from the highest in the file when it
  is opened again (a notebook keeps its count in its metadata, so there a number is never reused).
- **A load for each origin.** A file: `duckdb.read_csv / read_parquet / read_json(path).df()`, a
  workbook `pd.read_excel(path, sheet_name=...)` (the server reads files with Arrow, so a column's
  type can differ in small ways). A connection: `sag.sql("Name", "<the query it was opened with>")`.
  A "+" tab: its query. **A paste: written out as one typed `VALUES` query when it has at most 200
  rows, 50 columns and 20,000 characters; else a note** saying to export it to a file and open that.
  A file dropped on the page (the browser gives no path) gets a note.
- **No steps: nothing to run.** The cell is one comment line; with steps it is `import duckdb` and the
  one statement. A sort made by clicking a header is a way of looking and stays out of the cell. A step
  that cannot run is said in the cell instead of a query that fails.
- **Safe to repeat, and not sent back.** The kernel keeps a reference to what was sent to the grid
  under each name; the Workbench runs a table's cell as `%%sag_table orders`, which puts that original
  back under the name first. The watcher sees the changed variable is the cell's own result and does
  not send it; when the maker ran again just before the cell did, it sends the new original instead.
  Run file (`%sag_run`) and a script's Run to here, Run from here and selections run a table's cell
  the same way. Run as plain Python elsewhere, the file makes the table and transforms it once.
- **A reopened file's steps.** A notebook keeps each table cell's steps in the cell's metadata, and a
  grid opened with no steps for a table whose cell came with the file gets them back. A script has no
  such place: there the cell is rewritten to the grid's (empty) steps when its table is opened again.
- **Folding.** A file's group starts folded; a group made while working shows its tables, and a table
  whose maker just moved in shows open, so the cell being worked in is not folded away.
- **A link lands on** the table's read-only cell (the transformations), for a uses line; a note's link
  ("made at @cell7") on the maker.
- **The pandas and plain-Python generators stayed** at first, in the steps window's Code tab and the
  agent's `steps_python`. They were removed later the same day (see "Cleanup, 2026-11-14" below).

## No confirmation labels: only states that need the user to act (2026-11-14, the owner's rule; built)

The owner, on the table cells' screenshots: "The first screenshot you said up to date. This is an
example of useless information. We only care if things are out of date. Confirmation labels is bad app
design." (docs/design-principles.md has the principle.) Applied to table cells and HTML cells:

- **Gone:** "Up to date" (and "last run 10:42" on its own), "No steps yet", "0 steps". A cell that is
  current shows no badge and no state word, in a notebook cell's head, a table's folded line, the
  Tables group's line, an HTML cell's bar and a script's marker notes.
- **Still shown, because they need action:** "Out of date · last run HH:MM" with Run (yellow), "Not run
  yet", "Not run since opening", "not open in the grid", and errors.
- **Folded lines.** A table with no steps is its name alone ("customers"); with steps it keeps the
  count, which is about its content ("orders · 3 steps"). The group: "Tables · 4 tables", and
  "Tables · 4 tables · 1 out of date" (yellow) only when one is.
- The toolbar's Run tables still appears only when a cell needs a run. The agent still reads each
  cell's state by name (`upToDate`, `outOfDate`...): only the screen stays quiet.

## HTML cells: a design drawn from its HTML (2026-11-14, the owner's request and decisions; built)

The owner: "A new type of notebook and python cell called a html cell. Where html can be used to render
designs in a resizable pane. And any html entered just auto renders. So when you click into the cell you
see code but when it's not active you see a rendered design. This can allow rapid prototyping or story
telling." Decided by the owner:

- **A new cell kind, HTML,** in notebooks and scripts, beside Python, SQL and Markdown.
- **Two faces.** Active, it shows its HTML in the editor with HTML colouring; not active, the design.
- **It renders by itself** when the cell is left; plain HTML needs no Run.
- **A resizable pane:** drag its bottom edge, or the keyboard; the height is saved in the file.
- **In a .ipynb** it is a code cell starting with `%%html` (IPython's own cell magic). **In a script**
  it is a `# %% [html]` cell holding the HTML in a Python string.
- **JavaScript runs, walled off:** a sandboxed frame that allows scripts but not the app's origin.
- **Nothing loads from the internet:** the frame's policy allows only what is inside the cell.
- **Python data by name:** `{{ name }}` is filled from the cell's kernel when the cell runs; a value as
  escaped text, a table as an HTML table with a row cap. A cell with names uses the table cells'
  "Out of date · last run HH:MM · Run" state; an unknown name is a plain marker; the uses line applies.

Built on 2026-11-14 (domain/html_cells.py, client/html_cells.py, web/src/workbenchHtml.ts,
web/static/design.html, the notebook and script views). Decided while building; confirm or change:

- **How the cell opens.** A click inside the design goes to the design, so a prototype's own buttons
  and scripts work. The HTML opens from the cell's head (a click anywhere on it), its Edit HTML button,
  Enter on the selected cell, or the agent's command. The design shows again when the editor is left
  (a click elsewhere, Escape, a run); switching to another window is not leaving. An empty cell stays
  open.
- **The command-mode key is H** (Y, M and S were taken; Jupyter's own H shows its key list, which this
  app has in the palette).
- **A script's form: a string by itself.** `# %% [7] [html] height=320`, then `r"""`, the HTML on its
  own lines, `"""`. A statement that is only a string does nothing when Python runs it and makes no
  name; it needs no import, so the file runs anywhere. It is written raw (as typed) whenever Python can
  hold it that way, with `'''` when the HTML has `"""`, and escaped only when it has both. A string
  given a name (`card = """..."""`) is read as the HTML too. Python after the string, in the same
  cell, stays in view; the toolbar's HTML button closes the cell with a plain `# %%` when code follows.
- **A script's two faces.** One editor holds the whole script, so: with the cursor in the cell its
  lines show; with the cursor elsewhere they are put away and the design is drawn under the marker
  line, which says "HTML · click this line to edit". **Limit: in a script the HTML is coloured as a
  Python string, not as HTML** (the notebook's editor colours it as HTML).
- **The height:** a notebook keeps it in the cell's metadata (`swissarmygrid.height`); a script on the
  marker (`height=320`). Without one the pane takes the design's own height (up to 640); limits 60 to
  2,000 pixels. A double-click on the edge (or Enter) goes back to the design's own height.
- **How the frame is walled off.** The design is drawn in a frame loaded from the app's own static
  page (`/static/design.html`), sandboxed with scripts allowed and nothing else: no same origin (so no
  token, storage, cookies or parent page), no pop-ups, no forms, no top navigation. That page carries
  the policy `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:;
  font-src data:; media-src data:; form-action 'none'; base-uri 'none'`. It is a page of its own, not
  text written into the Workbench page, because a frame made from text inherits the Workbench's own
  policy, which (rightly) allows no inline script. Leaving the frame for another site is refused by the
  Workbench's existing `frame-src 'self'`. Checked in a browser: a remote picture, stylesheet and script
  do not load; fetch, a socket, a pop-up, a form, a link and a script's own navigation reach nothing.
- **Where a name stands decides what goes in** (so data can never become markup or script):
  among the words, escaped text, a table, or a picture; inside a `<script>`, a JavaScript literal (a
  number, a quoted text, a table as a list of rows); inside a tag or a `<style>`, plain words and
  numbers only (anything else is left out and said under the design); inside a comment, nothing. The
  reading of the HTML follows the browser's own rules and errs to the stricter part.
- **Only a variable's name** goes between the braces: no expression, no attribute, nothing runs.
- **Caps:** a table among the words shows its first 50 rows and 30 columns and says so ("first 50 of
  1,204 rows"); inside a `<script>` it is its first 1,000 rows; a text is cut at 10,000 characters, a
  table's cell at 200; a picture over 3 MB is left out with a note.
- **Pictures are in:** a matplotlib figure (saved as PNG) and anything that gives a PNG of itself
  (`_repr_png_`: a PIL image, an IPython Image) become an image from a data address, which the frame's
  policy allows. Plotly figures are not (they need their library, which the frame cannot load).
- **Out of date covers the variables too.** A run keeps a short mark of what each name drew. After
  any run in the document ends, the cell's names are marked again in the kernel; a different mark, and
  the cell says "Out of date · total changed · last run 10:42". The mark is of what the design would
  draw (a table's first 1,000 rows), so a change further down a long table is not seen.
- **While out of date the design still follows the HTML,** filled with the values of the last run (a
  name added since shows as written, marked). The values travel with the run's output.
- **Saved with the notebook:** the cell's last run is its output (the filled design as `text/html`,
  what plain Jupyter and GitHub show, and the values beside it), so a file opened again shows the
  design as it was, and says "Not run since opening". Plain HTML saves no output.
- **Run file fills a script's HTML cells after the file has run,** from the variables it left (the
  string itself does nothing in Python). Ctrl+Enter in the cell runs it alone.
- **The uses line:** `<!-- uses orders @cell3 -->` as the first line of a notebook's HTML cell (it fits
  the existing rule: only a first line in exactly that form is the app's, and it never makes the cell
  out of date). In a script it is the Python comment form above the string, so the HTML stays as typed.
- **The agent** (the golden rule): `workbench_html_add`, `workbench_html_cells`, `workbench_html_run`,
  `workbench_html_resize` in the window; `workbench_run` with kind html, `workbench_html_fill` and
  `workbench_html_marks` without one. The window's palette has the same under HTML.

Not built: HTML colouring inside a script's string; Plotly figures by name; expressions in the braces
(`{{ total * 2 }}`); a design that reads the page's theme (it gets the app's text colour and a
transparent background, and its own styles win); plain HTML saved with an output for GitHub to show.

## Cleanup, 2026-11-14: what was removed and why (the owner's decisions; built)

After a survey of the whole app for things nobody needs, the owner went through the findings one at a
time. Each of these was his call. The rule behind most of them is principle 7.9 (show only what needs
action) and the app's purpose (DuckDB SQL does the transforming).

**Removed**

1. **The pandas and plain-Python translations of a grid's steps.** The steps are copied as one DuckDB
   query and nothing else. The two generators (about 650 lines) and the list-of-dicts paths of the
   check that ran them are gone. The code route, the steps window's Code tab and `steps_python` lost
   their `target` argument rather than keeping one that takes a single value: with one answer there is
   nothing to choose. The DuckDB copy is still run exactly as copied and compared with the grid.
2. **To Python, Script as and the `sag.paste()` queue.** The queue of code waiting for the user's
   Python is gone: the page's part, the service and its routes, `sag.paste`, and the agent's
   `python_send`, `python_sent` and `python_grid_steps`. The catalog's Script as went with it (its
   route and `catalog_script`); a table's right-click keeps Open as grid. On an analysis result, To
   Python is now **Copy code**: the same checked code, imports first, on the clipboard, and "Copied."
   The agent still reads that code with `analyze_code`.
3. **The old agent door for blades** (`/agent/blades`, `/agent/blade-templates`): the propose-then-Allow
   window from before the golden rule. The agent saves blades as the user does. Approvals stay, for
   exports.
4. **Saved recipes.** Save recipe, its route, the port, the files' code, the silent re-apply when a
   dataset of the same name arrived, and `steps_save_recipe`. A dataset's first grid always starts with
   no steps. Recipe files already in a state folder are left alone and no longer read.
5. **The ribbon's Cell row.** Keep these, Exclude these, View value and Copy are on the cell's
   right-click menu, where they already were. The ribbon is Application, Table, Column (and Compare
   while two grids are side by side).
6. **The steps window's copy of the ribbon and its pop-out button.** The window (`?panel=steps`) shows
   only the steps: the list, Add a SQL step and the Code tab. The panel's in-page mode (collapse to a
   rail) had no caller since the grid took the whole page, so it went too.
7. **Fit test and Outliers in the Column row.** They stay in the Analyze menu and on a column header's
   right-click menu. The tour points at Analyze for both.
8. **The refresh icon on each connection's row** in the catalog side bar. The one beside the catalog
   picker stays, and so does Save and refresh the catalog on a blade's save screen.
9. **Confirmation labels** (principle 7.9), each removed or shown only when it needs action:
   "No steps" (the strip and the steps window); "live" (only "not live: push again" shows); the data
   meter (only past 80% of the budget; Datasets always has the numbers); "v1" beside the title (the
   version shows from 2 on); "catalog loaded"; "Kernel: ready" with its green dot, "This app's Python",
   "Notebook" and "Python script" in the Workbench's status bar; the installed packages' chips and
   "All installed" (only missing packages are listed, with Install; Copy install command stays, as it
   is for the user's own Python); the "Verified identical on N rows" badge (the Copy buttons being
   there say it; "Not verified" keeps its difference); and the toasts Saved, Closed X, Removed X,
   Removed the X catalog, Blade folders saved, Applied X, Imported X (a relationship model) and
   "X: now in Tables, at the top" (a second toast beside "X is open as a grid", which made a browser
   test fail now and then).
   **Kept, because they are real feedback:** "Copied.", "X is open as a grid.", "Sent to …", the
   progress words of slow jobs, "updated to version N", "The agent changed this grid's view.", "Kernel
   stopped", "Restarted", empty-list lines inside an opened window, analysis verdicts, the "Saved"
   placeholder in a password box, and "Imported theme X" in the Sandbox.
10. **The five old `agent_` reads, merged into the page's own commands.** What each could do that its
    twin could not was moved first:
    - `agent_read_grid` -> `row_read` with `format=csv` (the view as CSV, headed by its row count, up
      to 1,048,576 rows a read);
    - `agent_describe` and `agent_profile` -> `table_profile` with `dataset` in place of `grid`, for a
      table with no grid (with `column`, that column's full profile); `column_profile` is unchanged;
    - `agent_view_state` -> `tabs_get`, which now also gives `view_rows`, `selected_rows` and
      `highlights`;
    - `agent_query` -> `steps_run_sql`, which already ran one guarded SELECT where `grid` is the grid's
      view and any open table can be read by name, so nothing was added. It needs a grid id (any grid;
      `tabs_create_grid` gives one for a table with none), and unlike `agent_query` it also takes
      CREATE TABLE ... AS SELECT, as the user's own SQL does (the golden rule).
    `/agent/query` and `/agent/view-state` are gone; `/agent/read`, `/agent/describe` and
    `/agent/profile` stay because `row_read` and `table_profile` use them. 183 commands (187 after round 3).
11. **The Variables pane's "Connections and blades" block** (the side bar lists them). A connection a
    cell has opened shows under Your variables. The Environment block shows only when there are
    variables of a vault, a secret blade or a password to list (no heading over "None"). The agent's
    `workbench_variables` is unchanged: it is the only command that reads a kernel's variables, and it
    still gives every connection (opened or not) and the environment names.

**Added**

12. **Remove this theme**, beside the Sandbox's theme picker while an imported theme is chosen (it asks
    first). The agent could already do this (`sandbox_theme_remove`) and the page could not. The 20
    built-in themes have no such button.

**Kept on purpose** (the owner said so): the empty table cell's comment ("# rainfall: no transformations
yet…"), all 20 Sandbox themes, and `push(start_server=…, open=…)` quietly accepted and ignored.

**Also put right:** the package's first line said the grids live inside VS Code; CLAUDE.md said the VS
Code extension was not built; `tabs_cancel`'s help named a Cancel button the page does not have; the
README and the agent's guide still described the Allow window for a new blade, and gave old command
counts.

**What a user's own code or files could notice**

- `sag.paste()` is gone (AttributeError). Nothing replaces it: paste from the clipboard.
- A script calling the routes `/python/*`, `/grids/{id}/python`, `/grids/{id}/recipe`,
  `/catalogs/{name}/script`, `/agent/blades`, `/agent/blade-templates`, `/agent/query` or
  `/agent/view-state` gets 404. `/grids/{id}/code` ignores `target` and its answer has no `target`.
- An agent set-up that names `agent_read_grid`, `agent_query`, `agent_describe`, `agent_profile`,
  `agent_view_state`, `python_send`, `python_sent`, `python_grid_steps`, `catalog_script` or
  `steps_save_recipe` (an allow-list, a prompt) names tools that no longer exist.
- A saved recipe no longer comes back when its dataset is pushed again. The files are still in
  `~/.swissarmygrid/recipes`.
- `table_profile` takes `grid` as a named argument now (`sag table_profile --grid <id>`), since it can
  take `dataset` instead.

## Power BI workspaces, DAX cells, and a real-world test bed (2026-11-15, the owner's calls; the connection and the DAX cell built)

The owner's work: notebooks scheduled and run in an Azure Function app; notebooks that make Excel
invoices and CSVs; models built here and taken into Power BI dashboards. Decided:

- **A Power BI connection that reads** datasets (semantic models) with DAX, through Power BI's
  Execute Queries web request, signed in with Microsoft's `azure-identity` (browser sign-in, or a service
  principal for unattended runs). First built per dataset; **corrected to per workspace, with a DAX
  cell** (below).
  **Made from the owner's vault:** "My vault has a client secret and app registration for Power BI API
  calls; this should be how that connection is created." The default sign-in is that app registration
  (service principal): its tenant id, client id and client secret are picked as entries of the vault, so
  the same notebook runs in an Azure Function with the vault's names in its environment. Browser sign-in
  is the second choice, for trying a dataset by hand. Its catalog lists tables, columns and measures; Open as grid runs
  `EVALUATE TOPN(<rows to open>, 'Table')`; a notebook's SQL cell on it holds DAX.
- **It also reads the dataset's relationships** into the app's relationship model (the Diagram, the Key
  Finder's known joins, tangs), so an existing Power BI model's joins arrive with its tables.
- Not chosen: exporting the app's model as a Power BI project.
- **The test bed stages what runs here:** real SQLite, DuckDB, PostgreSQL and MariaDB in the container,
  and realistic made-up CSVs, workbooks, Parquet and JSON; cloud services (SQL Server, Azure Key Vault,
  Power BI) are checked against local stand-ins. Made-up data only.
- **Scheduling:** no export feature. The test bed proves a saved notebook runs top to bottom without
  the app, with its passwords from environment variables, as an Azure Function would run it.
- **Ten real-world use cases** to run end to end in a real browser, counting actions:
  1. orders from a database, cleaned in the grid, the notebook saved;
  2. that notebook run headless;
  3. the same with passwords from environment variables;
  4. Excel invoices, one workbook per customer from a template;
  5. a daily CSV export;
  6. a CSV folder, workbook sheets and a database table combined, joins found;
  7. an existing Power BI dataset's tables and relationships read in;
  8. a Power BI dataset tied out against its source database;
  9. a forecast as a Sandbox report, printed to PDF;
  10. a story notebook with HTML cells.

**Per workspace, and a DAX cell (the owner, 2026-11-15; built the same day).** The first build made
the connection per dataset. The owner: "That's wrong: you designed the connection per dataset; it
should be per workspace." And: "Which means we needed support for a new kind of cell, a DAX cell."
What it is now (docs/verified.md has what was checked):

- **The connection is a workspace.** The starter is "Power BI workspace" (still `powerbi`). Its form
  asks for the workspace id and the sign-in, never a dataset. The three sign-ins are as they were.
- **The object's shape,** as a database connection gives every schema:
  `conn.datasets()` lists each dataset's name and id (`GET .../groups/{workspace}/datasets`);
  `conn.dataset("Sales model")` is one of them, by its name or its id;
  `conn.dataset("Sales model").cursor()` runs DAX on it (`conn.cursor(dataset="Sales model")` is the
  same); `conn.cursor()` with no dataset is the workspace's one dataset, refused with their names when
  it has several. Two datasets with one name are told apart by the start of their ids.
- **A dataset is named after its connection: `Finance/Sales model`.** A DAX cell, `sag.dax()`, the
  agent's commands and a table's source in the Diagram all say it that way. No connection's name has
  a slash, so the first slash always splits the two.
- **The catalog** is the workspace, then each dataset (the schema level), then its tables, then their
  columns and measures (a measure still marked on its table). It loads itself as before; each dataset
  is asked the three ways below. **Datasets are read one after another, at most 25 of them and for at
  most 200 seconds** (each takes two queries or more; Power BI takes 120 a minute). One that cannot be
  read, or was not reached, gets an error mark on itself only (a circled "!", its reason on hover and
  on its page); the others load.
- **Open as grid** sends `EVALUATE TOPN(...)` to the table's own dataset, with the row limit and the
  "first N of M rows" note. **A grid is named after its table; when two of the workspace's datasets
  hold a table of that name, after the dataset too:** both have Date, so they open as
  `Sales_model_Date` and `Budget_model_Date` (the app's table names take no spaces or dots). The clash
  is read from the loaded catalog: before it has loaded, a table opens under its own name.
- **Import its relationships is per dataset, in one place and one offer:** on a dataset in the catalog
  (its page and its right-click), and on the "is open as a grid" message for that table's dataset,
  shown until that dataset's relationships are in the model. **It left the connection's row in the
  Connections window:** a workspace has several datasets, and a row has no clean place to pick one.
  The model's tables are named as they open as grids (the Date clash included); each table's source
  reads "Finance/Sales model (Power BI)".
- **A DAX cell is a cell kind of its own,** beside Python, SQL, Markdown and HTML: in the kind picker,
  the toolbar's **DAX** button, the palette (Make it a DAX cell, Add a DAX cell) and command mode's
  **X** (S was SQL's; X is free and is DAX's last letter).
  - Its picker lists only Power BI workspaces' datasets (`Finance/Sales model`; one that could not be
    read last). A SQL cell's picker no longer offers a Power BI connection. The list comes from each
    workspace's loaded catalog, so listing never opens a sign-in window; a workspace whose catalog is
    not loaded shows by its own name and loads when the picker is first opened.
  - Colouring is Monaco's own DAX grammar (`msdax`: keywords, functions, `'Table'[Column]`,
    `[Measure]`). No new dependency.
  - Completion: DAX's keywords and functions, and that dataset's tables (`'Sales'`), columns
    (`'Sales'[Amount]`; after `'Sales'[` that table's columns) and measures (`[Total Sales]`). Never
    SQL's words, never another dataset's names, nothing from the kernel.
  - In a `.ipynb` it is a code cell that starts `%%dax Finance/Sales model` (quoted when the name has
    a space), so plain Jupyter with the client runs it. The kernel registers `%%dax` as it does
    `%%sql`, with the same options (`-> name`, `--grid`). Its result is a DataFrame, handled exactly
    as a SQL cell's.
  - **In a script it is plain Python under a marker:** `# %% [dax]`, then
    `result = sag.dax("Finance/Sales model", """EVALUATE ...""")`. SQL has no cell form in a script
    either (it is `sag.sql(...)` in Python), so this mirrors it: the file runs as it is, anywhere.
  - `sag.dax("Finance/Sales model", "EVALUATE ...")` in Python. `sag.sql` on a dataset still works
    (the same call underneath); the docs teach `sag.dax`. A table opened from a dataset has
    `sag.dax(...)` as its cell's load.
  - **Old cells:** a `%%sql Finance/Sales model` cell opens as a DAX cell (the slash says so), and so
    does a SQL cell whose connection is a Power BI one (a notebook saved when the connection was one
    dataset).
  - **Refused:** a DAX cell or `sag.dax` that names only the workspace (`Finance`) when it has several
    datasets, with a short message naming them. A workspace of one dataset needs no dataset named.
  - **No uses line on a DAX cell.** `Sales` in DAX is the dataset's table, never the open table Sales
    in the kernel, so the app writes no `-- uses` line there.
- **A connection saved per dataset still works.** Its code makes one dataset with no list of
  datasets: it is treated as a workspace of one. Its tree has the one node (Model), no dataset is
  named anywhere, and a DAX cell names the connection alone.
- **Test connection** signs in and lists the workspace's datasets: "It works: signed in and found 3
  datasets."
- **The agent** (the golden rule): `connections_datasets` lists a workspace's datasets (asked of Power
  BI, with ids), `connections_import_relationships` takes a `dataset`, `workbench_dax_add` adds a DAX
  cell on a dataset, and `workbench_run` takes kind `dax` with the dataset as its connection. 190
  commands (188 before).
- **The stand-in** is a workspace of three made-up datasets: Sales model, Budget model (a Date table
  of its own) and Broken model (answers every query with an error).

**The first build, per dataset, on 2026-11-15** (the test bed, scheduling and the ten use cases
are still to do). **Not run against a real tenant:** Power BI and
Microsoft's sign-in are stood in for on this computer (tests/powerbi_standin.py). Decided while
building, and still so except where the block above changed it (marked):

- **The app registration signs in with Python's standard library, not azure-identity.** Microsoft's
  client credentials request is one web request, so the default sign-in needs no package at all: the
  same code runs in an Azure Function as it is, and the tests prove the request end to end (the
  stand-in receives the tenant, the client id and the secret). azure-identity will not sign in to
  anything but an https address, so its service principal could not have been tested here.
  **azure-identity is used for the browser sign-in only** (InteractiveBrowserCredential), installed
  with the form's Install button. The queries use the standard library too, not `requests`: on a
  company computer it trusts the certificates Windows trusts, which `requests` does not.
- **Three ways to sign in** (the form's Sign in): *App registration, from a key vault* (the default:
  tenant id, client id and client secret each start on "A key vault" with the entry picker); *App
  registration, ids typed here* (the two ids as plain fields, the secret from a password source);
  *Browser sign-in, as yourself*. The three values in the first way may also come from an environment
  variable or this computer, as any password may.
- **The code names what the vault names.** Picking `powerbi-client-secret` writes
  `secret("powerbi_client_secret")`: the vault's own name as a variable (the existing rule). An Azure
  Function's settings must use those names.
- **Two environment variables move the connection:** `POWERBI_API_URL` and `POWERBI_LOGIN_URL`
  (defaults: api.powerbi.com and login.microsoftonline.com). The tests point them at the stand-in; a
  government or China cloud would set them too.
- **Making the connection signs in and lists the workspace's datasets** (changed: it was one small
  query on the one dataset), so Test connection means the sign-in works and the workspace is reached,
  not only that the code ran.
- **Measures are marked on their own table** (type "measure, Decimal"), not under a Measures node: a
  measure belongs to a table in Power BI, search and completion find it there, and a Measures table
  could not be opened as a grid. (Changed: each dataset is a node of its own, by its name; only a
  connection saved per dataset has the one node called **Model**.)
- **Open as grid opens the whole table** (`EVALUATE TOPN(n, 'Table')`; every row: `EVALUATE 'Table'`):
  no columns are picked, since the catalog lists measures beside them.
- **The catalog asks three ways:** `INFO.VIEW.COLUMNS()` and `INFO.VIEW.MEASURES()`; where those are not
  known, `INFO.TABLES()`, `INFO.COLUMNS()` and `INFO.MEASURES()` (ids and numbered types resolved);
  where the sign-in may not read the model's description at all, `COLUMNSTATISTICS()` (tables and
  columns, no types, no measures). The date tables Power BI makes by itself (LocalDateTable_,
  DateTableTemplate_) and the hidden RowNumber columns are left out.
- **Power BI's limits** (100,000 rows or 1,000,000 values for one query, 15 MB, 120 queries a minute):
  an answer that reaches the row or value limit is **refused with a message**, never handed over as if
  whole. So a table of 100,000 rows or more cannot be loaded whole ("Load all rows" says why); Rows
  to open below the limit works. An answer cut at 15 MB cannot be told by its size and is not caught
  unless Power BI marks it.
- **Column names** lose their table (`Sales[Amount]` is Amount, `[Total Sales]` is Total Sales); a
  name two tables share in one answer keeps its table. Power BI's text dates become dates.
- **Relationships:** `INFO.VIEW.RELATIONSHIPS()`, else `INFO.RELATIONSHIPS()` with the ids resolved.
  Tables are named as they open as grids; Many to One is many-to-one and so on; "filters both ways" is
  the join's note; an inactive one stays inactive and **the Diagram now draws an inactive join dashed,
  labelled "inactive"** (for every model, not only Power BI's). The model is merged under the
  connection's name with the existing rules (the dataset's wins a join both name; the answer and the
  message say what changed). (Changed: per dataset; see above for the names and the source.)
- **Import its relationships** was in three places, the connection's row among them. (Changed: see
  above.)
- **DAX cells** were SQL cells on the connection, listed as "Sales model (DAX)". (Changed: a kind of
  their own; see above.) **The uses line no longer reads a word inside a bracketed or double-quoted
  name of several words** (`[Total Sales]`, `"Total Sales"`) as the table Sales; this holds for SQL
  cells.
- **The agent:** `connections_import_relationships` was new (188 commands then).
- **Also changed:** a connection that fails now shows its message in the Connections window and the
  catalog, not the JSON around it (`{"error": ...}` was shown as it came).
- **Open:** a real tenant has not been tried. What it needs: the admin setting Dataset Execute Queries
  REST API; "service principals can use Power BI APIs" for the app registration, which must be a
  member of the workspace; Read and Build permission on each dataset. Whether the INFO functions answer
  through Execute Queries for a sign-in with only Build permission is not known (hence the
  COLUMNSTATISTICS fallback). Datasets with row-level security do not take a service principal. Whether
  the datasets list names a dataset the sign-in may not query is not known either: such a one would
  show with the error mark.

## A connection from your own Python (2026-11-15, the owner's request; built)

"I want a new feature to build a connection from raw python. With env variables mapping, and boxes to
supply the python table from the connection to feed the catalog." Built as a connection type,
**Python (your own code)**. Decided:

- **Where it is:** its own group, **Your own code**, in Add connection, between Files and Key vaults,
  and under the same heading in the list. It is not a database (no dialect, no SQL), and "Other" on
  the blades page already means code that is not a connection.
- **Three boxes, one connection.** **Connect** makes `conn`, any object. **List the tables** returns
  the catalog for `conn`. **Read a table** returns a table's rows. Each box is the Workbench's Python
  editor, with one short line saying what it gives back. It is saved as one blade (kind `other`,
  template `python`): Connect is the blade's code, List the tables its catalog command, and Read a
  table and the variables are two new fields. The starter is a small web service client, standard
  library only, so it runs as it is once its two variables have values.
- **The variables are found, not typed.** Every name the three boxes read through `os.environ["X"]`,
  `os.environ.get("X")`, `os.getenv("X")` or `secret("X")` is found with ast, as the boxes are typed
  (also `environ` and `getenv` imported from os). A name built at run time (an f-string) is not one.
- **Each variable's source:** this computer's environment (the default: the code as it is), saved on
  this computer (the keyring), a key vault's entry (the same vault and entry pickers as a password),
  or a plain value for a name that is no secret (a URL, a region). The user marks which by choosing
  the source; a plain value is kept with the connection and written to its portable file, a secret's
  value never is.
- **The code is never changed.** A database's password is renamed in its code to point at a vault.
  Here the mapping is kept beside the code and the values are set as environment variables before the
  code runs (the vault runs first, with only this connection's entries), in the child process and in
  `sag.connection`. So the same code runs unchanged in an Azure Function whose settings hold those
  names. A variable the code cannot run without that has no value is named before the code fails on it.
- **The catalog's shape:** a list of dicts or a DataFrame, one row per column: `table`, `column`, and
  optionally `schema`, `type`, `description`. An INFORMATION_SCHEMA result's names work too. Another
  shape says what is missing ("This has no table and no column (it has: name, columns)"). An empty box
  means no catalog. It loads itself like any connection's catalog.
- **The count comes back with the rows: `(rows, total)`.** One box, not two: a second box would make a
  second request and could disagree with the first. Read a table is given `conn`, `schema`, `table`
  and `limit` (None means all) and returns a DataFrame, an Arrow table, a list of dicts (whatever push
  accepts), or `(rows, total)`. Code that ignores `limit` and returns every row is also right: the
  app keeps the first rows and knows the count. With no count and exactly `limit` rows the grid shows
  no note, since nothing says there are more.
- **Rows to open** is on this form too (10,000 unless set), as on a database's.
- **Test connection** runs Connect, then List the tables, then the first table's first 20 rows, and
  shows them; the first box to fail says which box and which line. A saved connection's **Test** shows
  the same rows under its row in the list.
- **In notebooks:** `sag.connection("Orders API")` gives `conn` (and the connection is a variable by
  its name in every Workbench kernel, like the others). `sag.read("Orders API", "orders")` reads a
  table with the connection's own Read a table box; a table opened from the catalog has that line as
  its read-only cell's load, and the catalog page shows it where a database shows a first SELECT.
  **A SQL cell needed no wiring:** `%%sql` already runs on anything with `.cursor()`, so it works when
  `conn` is a DB-API connection and says plainly when it is not. Nothing was added that guesses at
  other SQL-like methods.
- **The portable file** gains two sections, `[read]` (the Read a table box) and `[variables]`
  (`ORDERS_API_KEY = { from = "vault", vault = "Team vault", secret = "orders-api-key" }`), beside
  the `[catalog]` it already had. Files written before load as they did.
- **The agent** (the golden rule): `connections_python_save` (new, changed, or `test=true` to only
  run it), `connections_python_variables` (the names the boxes read), `connections_python_tables`
  (run List the tables now); reading a table is `connections_preview_table` and
  `connections_open_table`, as for any connection. 191 commands.
- **Also fixed:** a saved connection's form did not carry its Rows to open, so editing a database
  connection showed the box empty and saving cleared it.
- **Open:** the Python editor in the form has no completion (it is the Workbench's editor without a
  kernel). A person's pasted, indented code is kept as pasted; the browser test types unindented lines
  because the editor indents typed lines itself.

## Streamlit cells (2026-11-15, the owner's calls; built)

**Replaced the same day, in part** (see "The Streamlit canvas" and "Projects" below): **Push to page,
the page designer window, the Streamlit kind of cell, the pages kept inside the notebook's file, and
the T key are gone.** What stays from this section: blocks talk by shared names, tables by name, a
live cell in its cell, one Streamlit process an app behind the proxy, the out-of-date rule, Install,
Export.

"I also use the app to develop streamlit applications. So it would be cool if we could create a
streamlit cell in the notebook so I can build streamlit widgets/pages from the data." Decided:

- **Pieces, assembled like Lego** (replaces "a page per cell"): "The idea is you can build small pieces
  and widgets in workbench. Then you can push those to the page and assemble them like Legos." Each
  Streamlit cell is a piece (a chart, a filter, a table, a number). **Push to page** sends it to a
  **page designer**: a window of its own (not the Sandbox), a grid you drop pieces onto, resize and move,
  with several pages. Pages are saved inside the notebook file with their pieces (Claude's call, to
  confirm).
- **Pieces talk by shared names:** a piece that makes a value (a selectbox making `region`) drives every
  piece on the same page that reads `region`. Underneath, a page is one Streamlit page: its layout is
  drawn first as empty slots (`st.columns`/`st.container`), then the pieces run in the order their names
  need (ast: what each makes and reads), each filling its own slot, so a filter can sit anywhere.
- **Tables by name:** in a Streamlit cell, `orders` (any table the notebook made or the grid shows) is
  there as a DataFrame of the table after its grid steps, handed over each time the page runs. Other
  Python variables are not shared.
- **Live in the cell,** like an HTML cell: click in to see the code, click away to see the piece live in
  a resizable pane with its widgets working. The page designer shows whole pages live; a button opens the
  app in its own window.
- **Export as Streamlit app:** the designed pages as a runnable folder (app.py, one page each, the same
  layout, the data as Parquet, requirements.txt).
- Streamlit runs from the notebook's own Python (installed with Install, like a driver); it is not a
  dependency of the app. Built after the Power BI connection, before the real-world test bed.

**Built (2026-11-15). Decided while building** (each can be changed):

- **The cell in a file.** In a notebook a Streamlit cell is a code cell whose first line is the comment
  `# %% [streamlit]`; the rest is plain Python. A comment was chosen over a magic so plain Jupyter runs
  the cell as it is (with `import streamlit as st` it draws nothing and fails nothing). In a script it
  is `# %% [7] [streamlit] height=320`, then plain Python. Its first comment line is the piece's name
  (`# Region filter`); without one it is "Piece N" (N: the cell's own number). A page is named by the
  user ("Page N" until then): the cell names the piece, not the page, now that a page holds many.
- **A piece runs in the notebook's Streamlit app, never in the kernel.** Run all, Run file and the
  agent's `workbench_run_notebook` leave its lines out and run the app once instead. So a piece sees
  the open tables and the names other pieces make, and nothing else of the kernel (the owner's rule).
- **Pages are saved inside the notebook file** (to confirm): in its metadata
  (`swissarmygrid.streamlit.pages`: each page's id, name and pieces, a piece by its cell's number
  with its width and height). A script keeps them in a `# %% [streamlit-pages]` block: comments
  only, one page a line as JSON, so the file is still Python.
- **The board:** 12 columns; a piece is 2 to 12 wide (6 when pushed) and as tall as what it draws,
  or 1 to 30 rows of 40 pixels. Pieces flow left to right in their order, a row holding as many as
  fit, so "move" is a place in that order and the filter goes below the total by coming after it.
  The page designer draws the board as cards (name, cell, what it makes and reads, its size) and the
  page itself live under it, as ONE Streamlit page: pieces in separate frames could not share a name.
- **Shared names:** by Python's own parser, as table cells read code. The first placed piece that
  makes a name is its maker. A cycle is written on the page, in each piece's slot ("Total and Filter
  need each other's names (region, total): no order runs them"), and listed in the page's problems.
  A piece that reads a name made only by a piece that is not on the page says "push that piece here
  too". A piece that fails shows its error in its own slot; the others still run.
- **A piece alone, in its cell,** is shown with the pieces that make the names it reads above it
  (each under a line "region comes from the piece in cell 2"), so its widgets and links work there.
- **Widget keys:** each widget call without a key gets `key="<placed id>_<n>"`, written into the code
  by position (the text is otherwise as typed); two copies of one piece on a page do not clash.
- **Tables:** every table open in the grid, under its name as a Python variable, after its grid's
  steps (a sort made by clicking a header is a way of looking, not a step). Each run writes the
  tables the pages name as Parquet into the app's temporary folder, a table again only when it
  changed; the page's first lines read them (`st.cache_data`, keyed by the file's time).
- **Out of date** is the server's word: a piece's code against the code that last ran (the uses line
  never counts), and a mark of each table it names (name, version, steps) against the mark when it
  last ran. Nothing runs by itself; Run refreshes the data and every page. A piece keeps what its
  widgets hold through a run.
- **One process a document,** in the document's own Python (its environment; else this app's):
  `streamlit run` on a temporary folder (`swissarmygrid-streamlit-*`), `--server.address=127.0.0.1`,
  a free port, headless, usage statistics off. It is started through a few lines that watch this
  server and end with it. It stops when the document closes, its kernel stops, its Workbench window
  has been gone a minute, or the server stops; the folder goes with it.
- **The live pages come through the app's own server** (the proxy, not a wider frame policy):
  `/streamlit/live/<app>-<secret>/...`, Streamlit's files and its websocket, with Streamlit given
  that path as its base. Chosen because the Workbench's policy stays `frame-src 'self'`, the port
  never reaches a page, and the Host check still applies. The secret is random, made when the app
  opens, and is not the server's token (an address cannot carry a header, and the token never goes
  into an address). The frames are sandboxed without the app's origin (as an HTML cell's design), so
  a page cannot read the app's token or storage; the app in its own window is such a frame too.
- **Streamlit missing:** the cell says which packages the document's Python lacks, with Install
  (streamlit, pandas, pyarrow into that Python: uv when it is there, else pip). Not installed for
  the user unasked, and never added to the app's dependencies.
- **Export** (the Streamlit app menu, the designer's Export, the palette, `streamlit_export`):
  `app.py` (`st.navigation` over the pages), `app_pages/<page>.py` for each page as designed,
  `data/<table>.parquet`, `requirements.txt` (streamlit, pandas, pyarrow and what the pieces import,
  the standard library left out) and `README.txt`. Its own files are replaced; nothing else in the
  folder is touched. It runs without SwissArmyGrid.
- **The agent:** 22 commands (210 in all). In the window: `workbench_streamlit_add`, `_cells`, `_run`,
  `_push`, `_resize`, `_designer`. By the app's id: `streamlit_apps`, `_open` (a saved file's app,
  without the window), `_app` (pieces, pages and layouts), `_sync`, `_run`, `_address`, `_stop`,
  `_close`, `_install`, `_export`, `_page_add`, `_page_change`, `_page_remove`, `_piece_push`,
  `_piece_place`, `_piece_remove`.
- **Keys:** T in command mode makes the cell a Streamlit cell (S and H were taken).
- **Left open:** a piece's pane does not fit its own height (the page is another origin: it cannot
  say); it starts at 220 pixels and resizes. The designer has no drag to reorder pages (the agent's
  `streamlit_page_change` moves one). A script's uses line and a notebook's apply to a piece as to
  any cell (only for a table whose cell the document holds).

## The Streamlit canvas (2026-11-15, the owner's calls)

**Replaces Push to page and the page designer window of "Streamlit cells" above.** The owner:
"The streamlit app itself should just be a canvas in its own workbench window. And you can drag cells
or copy and then hit play to render it into a page. That push to page button is bad design." And, of
the whole: "Essential we have built a data first style ide for streamlit". The four answers:

1. **Where the canvas lives:** "A Workbench document tab". New app opens a canvas tab beside notebooks
   and scripts, saved as its own file; it pops out into a window of its own like any document.
2. **What a dropped cell is:** "A link to the cell". The canvas points at the notebook's (or script's)
   cell; editing the cell changes the app on the next Play. The app depends on that notebook.
3. **Play:** "Blocks, then the live page". Before Play, blocks on the 12-column grid; Play turns the
   canvas into the running page in place; Edit goes back to the blocks.
4. **Which cells:** "Any Python cell". The Streamlit kind of cell is gone.

**Built (2026-11-15). Decided while building** (each can be changed):

- **The app's file is `<name>.stapp.json`:** JSON written by hand so each block is one line (a change
  to a block is a one-line diff). It holds `"swissarmygrid": "streamlit-app"`, a version, and the
  pages; a page is a name and its blocks; a block is `{"document", "cell", "row", "column", "width",
  "height"}`. No ids, no code. `document` is relative to the app's own file, with forward slashes, so
  the two move together (another drive keeps the whole path). **`row` is one more field than the owner
  listed** (column, width, height): without it a block could not sit under an empty stretch of the row
  above, so the grid would not be a grid.
- **The grid:** 12 columns; a block is 2 to 12 wide (6 when placed), as tall as what it draws or 1 to
  30 rows of 40 pixels. No two blocks share a column of a row: the block just moved or placed keeps its
  place and the neighbour it would lie on starts a row below. Rows are counted from 1 with none empty.
  A new block with no place goes beside the last one when the row has room, else below. On the page a
  row is `st.columns` with the gaps as empty columns, so a block sits where it was put.
- **A link names a saved file.** A cell of a notebook that has no file yet cannot be linked; the canvas
  says "Save X first". The cell's own number (never changed, never reused) is the link, so moving cells
  in the notebook never breaks one.
- **Getting a cell onto the canvas:** drag a Python cell by its number or its head (HTML drag and drop,
  the type `application/x-swissarmygrid-cell`, a small JSON of the path, the number and the document's
  name; it works between two Workbench windows); onto the board at the place dropped, onto the app's
  tab or a page's tab at the end. **Copy** (C in command mode, More: Copy, the palette's Copy the cell)
  keeps the link and the cell on the Workbench's own clipboard, shared by every Workbench window
  through a BroadcastChannel (memory only: not the system clipboard, which a page cannot read without
  a permission prompt); Ctrl+V on a canvas places the link, V in a notebook pastes the cell (new: a
  notebook had no copy and paste before). **A script's cell is copied, not dragged** (Copy the cell
  with the cursor in it): its marker is a line of text in the editor, with no handle to drag. Open.
- **Play reads the cells as they are now:** from the open document that holds the file, saved or not
  (each Workbench window tells the server its documents' Python cells as they are typed, after a
  0.4-second pause), else from the file. The run order still comes from the names the cells make and
  read, never from the layout.
- **Out of date** ("Out of date · Play", on the Play button while the page shows): a linked cell's code
  differs from what last ran, a table it names changed in the grid, or the layout changed. Nothing runs
  by itself, a layout change included (before, the designer's live page followed every change).
- **A block whose cell or file is gone** says so in red with the path and the number, and the page
  shows the same words in that block's slot. It can be placed again or taken off.
- **Any Python cell; which are shown live.** The clear rule (domain/streamlit_use.py, by ast): a
  Python cell is live when it CALLS Streamlit: `st.something(...)`, a call through the name the cell
  imports streamlit under, a call of a name imported from streamlit, or `with st.sidebar:`. **An import
  alone does not count** (the owner's words were "imports streamlit, or calls `st.`"): `import streamlit
  as st` beside `import pandas as pd` draws nothing, and taking it out of the kernel would take `pd`
  from every other cell. **`st` means Streamlit unless the document gives it another value**
  (`from scipy import stats as st`). Half-typed code is not live yet.
- **A live cell does not run in the kernel** (the default the owner named): Streamlit code in a
  kernel only warns. Run on it runs the document's Streamlit app; Run all, Run file and the agent's
  `workbench_run_notebook` leave it out. A live cell alone is drawn with the LIVE cells that make the
  names it reads, as before; a plain cell's variables are the kernel's and are not shared.
- **Old files.** A notebook saved with the Streamlit kind opens with that cell as a Python cell: the
  marker line goes, the code, the number and the pane's height stay (a Python cell keeps a `height`
  now). A script's `# %% [streamlit]` marker reads as a plain `# %%` cell (`# %% [7] height=300`).
  **Old pages are dropped, not read:** a notebook's `swissarmygrid.streamlit.pages` is not written
  back; a script's `# %% [streamlit-pages]` block stays in the file as the comments it always was.
  Reading them would have needed a place to put them (a new app's file) and the owner said offer nothing.
- **The app's Python** is its first linked file's own (the open document's choice, else the one
  remembered for the file), else this app's. One Streamlit process an app, behind the proxy, as before.
- **Open app in its own window is gone with the designer's page:** pop the canvas out (the tab's
  button, the palette) and Play. `streamlit_address` still gives the app's own address.
- **Export stays** (the Export… button, `streamlit_export`): the folder that runs alone, with the
  data as Parquet. It is cheap (it was built) and different from Save as: a copy of the rows that runs
  anywhere, against pages for your own app that read the data again.
- **The agent** (the golden rule): in the window `workbench_new_app`, `workbench_canvas`,
  `workbench_canvas_play`, `workbench_canvas_edit`, `workbench_cell_copy`, `workbench_cell_paste`,
  `workbench_live_cells`, `workbench_live_run`, `workbench_live_resize`, `workbench_pop_out`,
  `workbench_project_open`; by the app's id `streamlit_apps`, `_open`, `_app`, `_run`, `_address`,
  `_stop`, `_close`, `_install`, `_save`, `_export`, `_save_as`, `_page_add`, `_page_change`,
  `_page_remove`, `_block_place`, `_block_change`, `_block_remove`; `project_new`, `project_files`,
  `project_export_data`. Gone: `workbench_streamlit_*` (add, cells, run, push, resize, designer),
  `streamlit_sync`, `streamlit_piece_*`. 224 commands (215 before; 228 after the review below); the tool list stays under 53,500
  characters (the descriptions are shorter).
- **In the redesigned Workbench** (merged the same day): an app's canvas is the tab kind "page"
  (New Streamlit app in a group's "+" and the top bar's "…"; Start an app on the empty page); Play,
  Edit, Export… and Save as zip… sit in the group's row of controls; the canvas's own pages are tabs
  inside it (two rows of tabs: the documents', then the app's pages). "+ Cell" has no Streamlit entry.
- **Left open:** dragging a script's cell; pages cannot be reordered by dragging their tabs
  (`streamlit_page_change` moves one); a block's height on the canvas is a hint of the page's (14
  pixels a row), not its real height; the Workbench's layout was left alone (a redesign is drawn).

## Projects: a data-first IDE for Streamlit (2026-11-15, the owner's calls)

The owner: "Essential we have built a data first style ide for streamlit". And: "I want the standard
export format to be data.py then page.py where you work on the data. So maybe notebook.ipynb is the
3rd component here that is optional. You can use a notebook to mock up and do data analysis but then
you can copy that into the streamlit page. Or the notebook is the product when your not building an
app. But regardless you always start with data or blades of some kind to manipulate variables for the
app or notebook". Then: "you can have two notebooks here one for data analysis and one for streamlit
mocks. And multiple pages." And last, settling how data.py is made: **"Data.ipynb is the canvas for
data.py export"**.

- **The symmetry: data.ipynb -> data.py, and the app's canvas -> pages/*.py.** A project is a folder:

  ```
  sales/
  ├─ data.ipynb         the data's canvas: the tables' read-only cells, blade cells, the user's own
  │                     code cells that shape variables. The user works here
  ├─ data.py            its EXPORT. Never edited by hand
  ├─ sales.stapp.json   the app's canvas (pages, blocks, links)
  ├─ pages/*.py         its EXPORT: one module a page, each starting with `from data import ...`
  ├─ *.ipynb, *.py      any number of notebooks and scripts (analysis, mock-ups): optional
  └─ requirements.txt
  ```

- **One source for a table (the rule):** a table's read-only cell lives in **data.ipynb**. In a
  Workbench window that has a project's data.ipynb open, a table no document made goes there, not to
  the document in front. Every other notebook and every page starts with `from data import ...`.
  data.py is written from data.ipynb and by nothing else, so nothing a user typed is ever written over.
- **data.py is data.ipynb's code cells in order** (domain/projects.py): a table's cell as it stands
  (its load, then the grid's steps as one DuckDB query: the same text as the read-only cell); Markdown,
  outputs, SQL, DAX and HTML cells, cells that call Streamlit, the uses lines and IPython's own lines
  (`%magic`, `!command`) left out, and what was left out said. It is written again on **Play**, on
  **Save as**, and on **Export data.py** (the Project menu, the palette, `project_export_data`), from
  the open data.ipynb (saved or not; from the file otherwise, with each open table's cell as the grid
  has it now).
- **It imports in a plain kernel and is kept under Streamlit:** its code sits in one `_load()` whose
  names become the module's; `_load` is wrapped by `st.cache_resource` when Streamlit is running
  (`st.runtime.exists()`), by `functools.cache` otherwise, and with no Streamlit installed nothing of
  it is needed. Code that cannot sit in a function (`from x import *`, `global`) runs as the module
  itself: Python keeps an imported module, under Streamlit too.
- **No rows, no secrets.** A table the app cannot read again (pasted, dropped, sent from Python with
  no cell that makes it) is a clearly marked stub in data.py (`# ===== FILL IN: customers =====`,
  `customers = None`), so the module still imports and only the page that reads it fails; Save as and
  the README name it. A connection is named, never its password.
- **Play reads the grid; the saved pages read data.py** (Claude's call, to confirm). While playing, a
  table comes from the grid as Parquet, as before: fast, and exactly what the grid shows. Any other
  name data.py gives (a variable a code cell of data.ipynb shapes) is imported from a copy of data.py
  in the app's temporary folder. The saved pages import everything from data.py.
- **Notebooks sit beside data.py, not in notebooks/** (the coordinator suggested a folder): `from data
  import ...` then works with no path line in every notebook. Any number of them, any names.
- **New project** (a group's "+", the top bar's "…", the palette, `project_new`): a folder with
  data.ipynb (a read-only cell for each open table), data.py, the app's canvas (unless asked not to),
  the notebooks asked for (each starting with `from data import ...`) and requirements.txt. A folder
  that already has a data.py is refused. **Open project** opens its files as tabs: data.ipynb first
  and in front, the canvas, the notebooks, the scripts (data.py is an export: not opened); the Data panel
  lists the project's files, data.py set in under data.ipynb as its output. A folder with no data.ipynb is not a project. Loose notebooks, scripts
  and apps outside a project work as before.
- **Save as** (the canvas's **Save as zip…**, named so beside the top bar's Save as…, which saves
  the file under another name; the palette; `streamlit_save_as`) zips the project, which is
  the folder of the app's file: both exports are written again (a folder with no data.ipynb gets one
  first, with a cell for each table the pages name), requirements.txt gets the lines it lacks (the
  user's lines stay), and the zip holds README.txt, data.ipynb, data.py, pages/*.py,
  requirements.txt, the app's file and the notebooks and scripts it links to. A linked file outside the
  folder comes along at the zip's top and the zip's copy of the app's file links to it there. Every
  notebook in the zip has its outputs dropped and a pasted table's rows taken out. The zip opens again
  as a project. This replaced an earlier layout of the same day (a `sag_tables.py` module and a
  `workbench/` folder), and an earlier data.py rule ("generated, then yours", entries marked
  `# %% [data] name` and refreshed one at a time): both were built and taken out the same day.
- **Left open:** blade cells in data.ipynb are the user's own code (`fx = sag.blade("FX rates")`);
  there is no "add a blade" button. An unsaved data.ipynb or linked notebook is exported as it stands
  but zipped as its file (Save as says so). A project does not remember which Python it runs in beyond
  each notebook's own.

## A starter pack of blades (2026-11-15, the owner's calls)

"Can we preload a bunch of useful blades for calling the powerbi workspace like refresh dataset/dataflow,
get refresh status, and other useful blades, as well as some excel and flat file based blades for
manipulating excel files like add sheet, format, add border to cell, set cell values; some dax blades
for dax manipulation cells, and some html blades for creating a wide variety of basic html objects from
data and tables." Decided:

- **A built-in starter pack** ("SwissArmyGrid starters") in every install's blade list, grouped by family:
  Power BI, Excel, Files, DAX, HTML. Read-only; any one can be copied and changed as the user's own.
  Updates arrive with new versions of the app.
- **Power BI workspace actions:** refresh a dataset; refresh a dataflow; the refresh status (latest and
  history); refresh and wait until done; list datasets, reports and dataflows; read and update a
  dataset's parameters; take over a dataset; read the refresh schedule. They sign in through the user's
  Power BI workspace connection (its vault sign-in), never their own copy of the secret.
- **Excel and flat files** (openpyxl, already the app's): add a sheet, set cell values, write a table to
  a sheet, borders, fonts and fills, number formats, autofit widths, freeze panes, merge cells,
  conditional colours, a range as an Excel table, copy a template workbook; combine a folder of CSVs,
  split a CSV by a column, change a file's delimiter or encoding.
- **DAX and HTML pieces drop into a cell:** a new blade kind, Snippet. Dragged onto a DAX or HTML cell
  (or picked from the cell's menu), its settings ask for the names it needs (a measure, a table, a
  column) and it is inserted as text to edit. DAX: year to date, same period last year, running total,
  top N by a measure, percent of total, a measure by month, date-table checks, the INFO functions for
  documenting a model. HTML: a styled table from a DataFrame, a KPI tile, a row of KPI cards, a progress
  bar, a badge, a bar chart in CSS, a list, a header block, a card grid, an invoice layout.
- **A Streamlit family, robust and clearly documented** (the owner: "Adding a robust amount of streamlit
  blades will be helpful with clear documentation on what they do. I'm learning streamlit and it seems
  like the modularity of it makes it perfect for this"). Streamlit pieces as snippets for Streamlit cells:
  filters that make shared names (selectbox, multiselect, date range, number range, text search, toggle, a
  sidebar filter panel); displays that read them (a metric with its change, a row of metrics, a table with
  formatted columns, an editable table, bar, line and area charts, a map from latitude and longitude, a
  progress bar, a status message); layout (tabs, an expander, columns, a bordered container); interaction
  (a CSV or Excel download, a form with Submit, an uploaded file as a table, session state shown with a
  counter, a cached slow query); feedback (success, warning, error, a toast). Each piece opens with what
  it does, the names it makes and reads, and every Streamlit function it uses in one plain line; the lines
  a learner would trip on are commented (why a widget needs a key, why the script reruns top to bottom).
  The user guide gets "Learning Streamlit with the starter pieces": one page built from five pieces, then
  every piece by what it is for.
- Built after the Power BI per-workspace work is merged (the Power BI actions use that connection).

## The Workbench redesign (2026-11-15, the owner's calls; built)

"So visually try to redesign the workbench a bit to make notebook/script and app page optional and two
separate spaces." "Right now it's all crammed together." "Or you can have two notebooks here one for
data analysis and one for streamlit mocks. And multiple pages." "Should be able to arrange and add as
many tabs a you want to the workbench." "Data.ipynb is the canvas for data.py export." The owner chose
a mockup (a top row, a Data panel, tab groups, a status bar) and said: "build no fable". Built on its
own branch (`workbench-redesign`); the app pages themselves (a canvas of blocks linked to cells, Play
and Edit), projects and data.py are another branch's, which this one leaves room for. Decided:

- **One row on top:** the app's mark, the focused document's name with a dot while it has unsaved
  changes, Save, Save as…, and "…" (New notebook, New script, Open…, Recent, Split right, Split down,
  collapse the Data panel, Layout, Commands). It replaces the toolbar's three rows. Until projects exist
  the name is the focused document's; a project's name takes its place when there is one.
- **The Data panel, on the left,** in place of the side bar. **Tables:** the tables open in the grid,
  each with its rows, where it came from (the file's name, the connection's name, Python, Pasted,
  Query; the server's table listing now gives `rows` and `source`) and its steps. A click goes to the
  table's read-only cell in the focused document (a message when it has none); a drag gives its name
  to code. **Variables:** the blades that are not connections (a click opens one, a drag gives its
  `sag.blade` line; its value shows when the focused kernel holds it). **Files:** a folded section at
  the bottom, hidden until a project exists (`setFiles`, the hook for the app pages' branch). The arrow
  (or Ctrl+B) folds the panel to a narrow bar; remembered in this browser.
- **"+ Table" and "+ Blade" keep what the side bar offered,** without a permanent rail: "+ Table" is a
  menu (Open file…, each connection, Search the catalog…, Add connection…); a connection or the search
  opens the catalog (its picker, search and tree, unchanged) in a panel beside the Data panel, and a
  table there opens its page as before. "+ Blade" opens the saved blades and connections the same way
  (New blade, import, export, folders, packs). Escape or a click elsewhere puts the panel away.
- **Tab groups, as Visual Studio Code's editor groups** (workbenchGroups.ts): any number of tabs of any
  kind; drag a tab along a row to reorder it; drag it over a group for the five-way guide (the middle
  moves it there, an edge splits that side: right, left, up or down); splitters between groups (drag,
  arrow keys, a double-click shares evenly); a group goes with its last tab. A document is in one group
  at a time (no second view of the same notebook: two editors on one kernel's cells would fight).
  Splitting needs a second tab in the group: one stays, one moves (the command says so, the menu entry
  is disabled with that reason).
- **Each tab shows its kind:** an icon and a thin colour mark on its top edge. Data (blue, the
  palette's second colour: a notebook named data.ipynb), Notebook (steel grey: notebooks, scripts, a
  blade being edited, a catalog table's page), App page (the accent red: registered by the app pages
  later). The kinds are a registry (`registerTabKind`): a kind with `start` is offered by a group's "+"
  and by the empty state.
- **One row per group:** its tabs and "+" on the left; when it is focused, its document's controls on
  the right. A notebook: "+ Cell ▾" (Python, SQL, DAX, HTML, Streamlit, Markdown), Run all, "…". A
  script: "+ Cell ▾" (DAX, HTML, Streamlit), Run file, "…". "…" holds the rest (Run statement or Clear
  every output, Open…, Recent, Save as…, Interrupt, Restart, the Streamlit app's entries when it has
  pieces, Split right, Split down, Close). Run tables stays in the row, and only while a table's cell
  waits (principle 7.9). Unfocused groups show only their tabs. A narrow group shows the controls'
  icons without their words.
- **The status bar** (for the focused document): the kernel, with a menu (Interrupt, Restart); the
  environment picker; the cursor's line and column; then Console and Variables, pressed while open.
  The kernel's state is said only while it is not ready ("not started", "starting…", "running…"):
  a ready kernel says nothing (principle 7.9), where the mockup said "Kernel idle". The console and
  Variables open as before (under the groups, on the right) but start closed; a run in the console (a
  script's Run file, the agent's `console.run`) opens it so its output is seen. A notebook's console no
  longer shows as a title bar.
- **Nothing open:** two icons and two buttons, "Start a notebook" and "Start an app". "Start an app" is
  disabled (its tooltip says app pages are not here yet) until the app pages register their kind; it
  looked right disabled, so it stays rather than hiding. No Recent list there any more (it is in "…").
- **The layout comes back after a reload** with the documents: the groups, which tabs where, the one
  in front of each, the sizes and the focused group, kept in the window's session storage with the
  rest. A blade being edited or a catalog table's page is not kept, as before.
- **Every new window action is a command** (the palette, the keys, the agent's `workbench_window`):
  `group.splitRight` (`Ctrl+\`), `group.splitDown`, `group.moveTab` (a group, a place in its row, or a
  side to split), `group.moveToNext`, `group.focus`, `group.focusNext`, `group.focusPrevious`,
  `tab.moveLeft`, `tab.moveRight`, `view.toggleSidebar` (now the Data panel, with `collapsed`),
  `view.toggleConsole` and `view.toggleRight` (with `show`), `data.goToTable`, `data.openFile`,
  `data.browse`, `data.blades`, `data.closeFlyout`, `data.addConnection`, and `data.list` for the agent.
  `documents` lists the groups.
- **Words:** full words everywhere ("Collapse the Data panel", "Document menu", "Add cell"); menus show
  their keys beside each entry; no explaining text was added.
- **Kept out of this branch,** so the two merge cleanly: the app pages, projects, data.py and the
  removal of the Streamlit cell; and the notebook's cell logic (one style rule lets a cell's editor
  follow a narrower group).

## The canvas's review, and four more of the owner's asks (2026-11-15)

The Streamlit canvas and projects were reviewed end to end by another agent (the owner asked for the
work to be checked without the builder's model). What changed, and why:

- **Edit | Play is one pair** (the mockups c-app-edit and d-app-play): the mode in front raised and
  underlined in the accent, the other flat on a grey track. Before, after Play the Edit button looked
  pressed while the live page showed. Play while the page shows runs it again; out of date it reads
  "Out of date · Play" in the warning colours.
- **The status bar on a canvas** said "Streamlit app" (explaining text, principle 7.1). It shows the
  Python the app runs in (its first linked file's, by its environment's last two folders, the whole
  path in its tooltip) and "starting…" while Play starts it; nothing else.
- **No rows leave, in two more places.** A script linked from the canvas went into Save as's zip as
  it was, with a small pasted table's rows written out in its read-only cell: that cell is a stub now,
  as a notebook's was. And data.py kept a pasted table's rows when a cell of the user's also made the
  table: the pasted cell is left out (and said), the user's cell is the table.
- **Save as writes over only its own pages.** It took away every pages/*.py the canvas did not write
  this time and wrote over any file of the same name, so a page of the user's own, or of a second app
  in the folder, was lost. A saved page's second line names its app's file (`# Written from
  sales.stapp.json by SwissArmyGrid: change the canvas, not this file.`); only such pages of the same
  app are written over or taken away, and Save as says which file it left alone.
- **A linked file from outside the project** could take the name of the project's own file in the zip
  (data.py, a notebook beside it) and replace it there: it gets a name of its own (`data_2.py`).
- **Play runs when data.py cannot be written** (read-only) and says so; before, it failed outright.

**Named cells** (the owner: "make it possible to name cells so the panel can show them by name").
Any cell can have a name, one line of at most 80 characters; the cell's number stays its identity,
so `@cell7` and canvas links never change with it.
- A notebook keeps it in the cell's metadata, `swissarmygrid.name`, which plain Jupyter keeps.
- **A script keeps it on the cell's marker line, as the marker's own words**: `# %% [7] Region filter`,
  `# %% [9] [html] height=320 Report`. Those words were already kept (a marker's title) and are what
  VS Code and Jupytext show as the cell's title, so a script needs no new syntax, and old scripts'
  marker words become their cells' names. A name that would read as the marker's grammar (`[html]`,
  `[3]`, `height=300`, or a backslash) is written after a backslash, which reading takes off.
- It is typed in the cell's head after its number (hidden until the head is hovered or the cell
  selected, while it has none), or set by More: Name…, the palette's Name the cell… and the agent's
  `workbench_cell_name`. A canvas block and the Streamlit cells pane call a cell by its name; without
  one, as before (its first comment line, else its first line).

**The Streamlit cells pane** (the owner: "On the left under data add another pane that aggregates
all the notebook cells that the are streamlit and make it so you can drag and drop from there"): a
section of the Data panel under Tables and Variables, "Streamlit cells", folding like the files. Every
Python cell that calls Streamlit (domain/streamlit_use.py) from the open notebooks and scripts (as
their windows hold them, saved or not) and, with a project open, from the project's notebooks and
scripts on disk; grouped by document; each by name, its `@cell` and "makes … · reads …". A drag places
its link on a canvas (the same link a cell's own drag carries, so it works onto another window's canvas
too); a click goes to the cell, opening its file when it is not open; a cell on the canvas page in front
has a check mark (the front canvas, else the last one in front). The server says when the list changes
(`streamlit_cells`); the agent lists it with `streamlit_cells` (by folder) and `data.streamlitCells`
(the window's own, with the marks).

**A tab pops out, and moves back** (the owner: "pop the notebook tab and app tab into two windows and
drag and drop that way"). Before, Open in its own window saved the document, opened it again from its
file in a new window and stopped its kernel.
- **The document moves:** its unsaved text, its cell numbers and names, its outputs and its running
  kernel. The server holds it on the way (memory, two minutes at most: `/workbench/handoffs`) and gives
  the kernel to the window that takes it, so the kernel stops only a minute after that window is gone.
  The window it leaves closes its tab once the other has taken it; if none takes it, it stays (never
  two live copies, never none). A canvas moves with its pages; a running Streamlit app restarts on Play.
- From the tab's right-click menu, the group's "…", the palette (Open the document in its own window,
  Move the document to the main window) and the agent's `workbench_pop_out` and `workbench_move_back`.
  "The main window" is one the user opened, not one a tab was popped into (a popped window remembers
  that through a reload); with two such windows open, the first to answer takes the document.
- A popped window is a Workbench window like any other (the Data panel, the Streamlit cells pane, its
  own groups and layout, restored per window).

**Panels in Settings** (the owner: "add app level settings with a option to hide or turn panels off
if wanted by the user they default on every time sag is opened"). The Settings window (the grid page's
cog; now also the Workbench's "…": Settings…) has a Panels section, a switch per panel: the
Workbench's Data panel, its Tables, Blade variables and Streamlit cells, Console, Variables and the
status bar; the grid page's ribbon, steps strip and status bar. A panel turned off is gone (not folded)
from every window at once, and its commands say "… is turned off in Settings (Panels)". **How "they
default on every time sag is opened" was read:** the switches are the server's, in memory, shared by
every window; a reload keeps them; a new start of SwissArmyGrid shows every panel again. If the owner
wants them remembered across starts, they would go to a small file in the state folder. The agent reads
and sets them with `app_panels`. Not switchable: the grid page's Application row (Settings is there)
and the Workbench's top bar (its "…" is how Settings is reached).

**Held back** (the reviewer would choose differently, the owner did not decide, so the builder's
choice stays): the copied cell lives on the Workbench's own clipboard (a BroadcastChannel), not the
system clipboard; Export keeps its folder that runs alone with the data as Parquet beside Save as; an
agent's Streamlit Export writes Parquet rows to a folder it names without the user's click (this
predates the canvas; a grid export by the agent needs a ticket); the page's removal asks with the
browser's own confirm box.
