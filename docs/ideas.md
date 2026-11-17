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
`transform(con, rel)` (pyarrow, a `__sab_ord` column, a table registered as `source`), so pasting
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
agent's or the user's draws the figure and sends the picture; Swiss Army Bench never runs agent code, so
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
  makes one); `key` replaces a card in place, keeping its size and order; `sab.sandbox` (duck-typed,
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
  - **`sab.sandbox(thing, title=None, *, key=None, size=None, kind=None)`** in Python (standard library
    only; it duck-types what it is given): a matplotlib or seaborn figure (`savefig`, PNG), a Plotly
    figure (`to_json`), an Altair chart (`to_dict`, drawn as Vega-Lite), a graphviz `Digraph`/`Source`
    (`.source`), a PIL image, PNG/JPEG/SVG bytes or a file path, a DataFrame (a table card, first rows),
    Markdown text (a note), and Mermaid, DOT or ECharts text with `kind=`. Explicit, not every image:
    the script decides what is worth showing. **`key=`** names a card, so running a cell again
    replaces its card instead of adding another. Returns the card's id. `sab sandbox ...` in the
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
  - **Saved dashboards:** the Sandbox is saved to disk as it changes and reopens when Swiss Army Bench
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
- **A pack** is a plugin with `blades/` and `tangs/` (and, if wanted, the Swiss Army Bench skill and MCP
  server). Swiss Army Bench finds installed, enabled packs and lists their blades and tangs with the pack
  and version; read-only (the installed copy is replaced on update): Save a copy into your own blades or
  a blade folder.
- **Collaboration is Git:** clone the marketplace repository, add the clone as a blade folder (already
  works), save blades and tangs there, commit, pull request, merge; teammates update.
- **`sab pack new`** scaffolds a marketplace repository (marketplace.json, one pack, README with the
  commands); **Add to pack** copies chosen blades and tangs into a pack folder. Swiss Army Bench's own
  repository may become a marketplace with an example pack on the made-up store.
- **Trust:** a pack blade is the marketplace maintainers' code, trusted as installing any plugin is;
  it runs only when used, and always shows its pack.
- **Built as designed**, and this repository is now a marketplace (`swissarmybench`: the skill and the
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
  `"swissarmybench": "tang", "format": 1`, so no other JSON file is taken for one, and a newer format is
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
  (`blades_list` gives names, kinds, descriptions, tags and the `sab.blade` line); send a secret's value
  (refused; the code says `secret("password")`); choose a blade folder (ignored, so a blade lands in the
  app); replace, change, remove, refresh, test or run a blade. A taken name is refused before the user is
  asked.
- **Open:** letting the agent edit a blade it made (behind the same Allow) and offering "save into a blade
  folder" in the approval window.

## Portable blades (2026-11-12, the owner's requests; confirm or change)

"A way to import a blade ... a format to make them portable", "blade folders that the app could search",
"a format or frontmatter" to tell blades from other Python, "descriptions and tags", and "pin blades
to favorite".

- **The frontmatter is a comment block**, `# /// swissarmybench-blade` ... `# ///` holding TOML, the
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
became **To Python**: the code is copied and queued (in memory, the last 20) and `sab.paste()` in
Jupyter or IPython puts it in the cell (set_next_input, replacing the cell that ran it) or at the
prompt; plain Python prints it. The agent can't queue code (it would land in the user's kernel). The
grid's automatic code-behind for notebook tables went with the tab; To Python is a click. Lost:
dropping a blade straight into a cell (drag gives its text instead) and Save as blade from a cell.

## The name off the screens (2026-11-13, the owner's request)

"The words Swiss Army Bench should appear nowhere in the app." Gone from every page title (the browser
tab names the grid in front: "orders", "Key Finder · orders"), the Application row's caption, the
bottom bar's credit (now "Created by Dylan Brown"), the Sandbox's empty state, the markdown export and
chart HTML footers, generated code's header comments, and the messages the page shows. Kept, because
changing them breaks installs or stored data: the package, `import swissarmybench as sab`, the
`swissarmybench` and `swissarmybench-mcp` commands, the `~/.swissarmybench` folder, the vault's service
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
15. First save: create the Swiss Army Bench folder in the home folder the first time it is needed. **Built (round 3).**
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
  `SWISSARMYBENCH_WORKBENCH_DIR` sets it, for tests.
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
  sab.paste; whether it stays.)
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
  A table sent by a Python outside the Workbench (Jupyter, a script in another editor, `sab.push` from
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
  type can differ in small ways). A connection: `sab.sql("Name", "<the query it was opened with>")`.
  A "+" tab: its query. **A paste: written out as one typed `VALUES` query when it has at most 200
  rows, 50 columns and 20,000 characters; else a note** saying to export it to a file and open that.
  A file dropped on the page (the browser gives no path) gets a note.
- **No steps: nothing to run.** The cell is one comment line; with steps it is `import duckdb` and the
  one statement. A sort made by clicking a header is a way of looking and stays out of the cell. A step
  that cannot run is said in the cell instead of a query that fails.
- **Safe to repeat, and not sent back.** The kernel keeps a reference to what was sent to the grid
  under each name; the Workbench runs a table's cell as `%%sab_table orders`, which puts that original
  back under the name first. The watcher sees the changed variable is the cell's own result and does
  not send it; when the maker ran again just before the cell did, it sends the new original instead.
  Run file (`%sab_run`) and a script's Run to here, Run from here and selections run a table's cell
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
- **The height:** a notebook keeps it in the cell's metadata (`swissarmybench.height`); a script on the
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
2. **To Python, Script as and the `sab.paste()` queue.** The queue of code waiting for the user's
   Python is gone: the page's part, the service and its routes, `sab.paste`, and the agent's
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

- `sab.paste()` is gone (AttributeError). Nothing replaces it: paste from the clipboard.
- A script calling the routes `/python/*`, `/grids/{id}/python`, `/grids/{id}/recipe`,
  `/catalogs/{name}/script`, `/agent/blades`, `/agent/blade-templates`, `/agent/query` or
  `/agent/view-state` gets 404. `/grids/{id}/code` ignores `target` and its answer has no `target`.
- An agent set-up that names `agent_read_grid`, `agent_query`, `agent_describe`, `agent_profile`,
  `agent_view_state`, `python_send`, `python_sent`, `python_grid_steps`, `catalog_script` or
  `steps_save_recipe` (an allow-list, a prompt) names tools that no longer exist.
- A saved recipe no longer comes back when its dataset is pushed again. The files are still in
  `~/.swissarmybench/recipes`.
- `table_profile` takes `grid` as a named argument now (`sab table_profile --grid <id>`), since it can
  take `dataset` instead.

## Power BI workspaces, DAX cells, and a real-world test bed (2026-11-15, the owner's calls; built: the connection, the DAX cell and the test bed)

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
- **Scheduling:** at first no export feature (a saved notebook runs top to bottom without the app,
  with its passwords from environment variables). Changed the same day: **Export as one Python script**
  and **Export as one notebook** (below, "One script, one notebook").
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
- **A dataset is named after its connection: `Finance/Sales model`.** A DAX cell, `sab.dax()`, the
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
    `result = sab.dax("Finance/Sales model", """EVALUATE ...""")`. SQL has no cell form in a script
    either (it is `sab.sql(...)` in Python), so this mirrors it: the file runs as it is, anywhere.
  - `sab.dax("Finance/Sales model", "EVALUATE ...")` in Python. `sab.sql` on a dataset still works
    (the same call underneath); the docs teach `sab.dax`. A table opened from a dataset has
    `sab.dax(...)` as its cell's load.
  - **Old cells:** a `%%sql Finance/Sales model` cell opens as a DAX cell (the slash says so), and so
    does a SQL cell whose connection is a Power BI one (a notebook saved when the connection was one
    dataset).
  - **Refused:** a DAX cell or `sab.dax` that names only the workspace (`Finance`) when it has several
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

**The first build, per dataset, on 2026-11-15** (the test bed, scheduling and the use cases came
after: below). **Not run against a real tenant:** Power BI and
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

**The real-world test bed: built (2026-11-15), all eleven use cases passing in Chromium.** `tools/testbed/`
(PostgreSQL and MariaDB started on ports of their own, made-up files, the Power BI and Key Vault
stand-ins) and `tests/e2e/test_real_world.py`, which skips with the reason when the bed is not up. The
use cases, each counting the user's clicks, keys, typed values, choices and drags (the table in
tools/testbed/README.md has what each does): 1 orders cleaned, the notebook saved, 35; 2 headless, 1;
3 as an Azure Function, 5; 4 Excel statements from a template with the Excel starters, 24; 5 a daily
CSV export run as the scheduled task, 12; 6 a CSV folder, workbook sheets and MariaDB, joins found, 35;
7 a Power BI dataset's relationships and tables, 26; 8 Power BI tied out against PostgreSQL, 10; 9 a
forecast as a Sandbox report printed to PDF, 14; 10 a story notebook, 20; 11 a project played and saved
as a zip whose page runs with AppTest elsewhere, 40. **Agent parity** for 1, 4 and 11: the same results
through the MCP commands alone (`connections_create`, `table_*`, `workbench_table_cells`,
`workbench_save`, `workbench_run_notebook`, `project_new`, `blades_snippet`, `streamlit_block_place`,
`streamlit_run`, `streamlit_save_as`); nothing was missing.

Decided while building (each can be changed):
- **Code of more than one line is pasted** in the tests (one typed value): Monaco indents each typed
  line after the last, as it does for a person typing.
- **A blade's line dropped on a cell or a script goes on a line of its own**, after the line it is
  dropped on (that line, when it is empty). Other text (a table's or a column's name) lands where it is
  dropped. The app takes drops itself: Monaco's own drop applied its snippet as plain text (`orders$0`).
- **A connection's table opened while a table of that name is open from elsewhere** (another
  connection, a file, Python; names differing only in case count as one, as DuckDB has it) is named
  after its connection too: `Warehouse_customers`, `Shop_invoices`. Opening it again from its own
  connection reloads it, as before.
- **The Diagram draws the whole model when none of its tables is open** (a Power BI dataset's
  relationships imported before its tables). With some open, it draws those, as before.
- **A last period that is not over is left out** of a time series and a forecast, and the words say so:
  "Left out 2026-11-01: its rows stop on 2026-11-01, before the month is over." It is not over when its
  rows stop before half way through it while the periods before it typically run past their middle; a
  table of one row on each period's first day (a budget) never is, nor a day, nor a series of fewer than
  four periods.
- **A snippet's form never starts a column on an identifier** (`order_id`, `customerId`) when another
  column is there and no hint in the blank's name fits.

**Gaps found, for the owner (not built):**
- **Open every table of a dataset (or schema) at once.** Use case 7 opens five tables one at a time:
  10 of its 26 actions. One action on the dataset's page (and an agent command) would make it 1.
- **Vault entries matched by name.** The Power BI form asks for each of the app registration's three
  entries; the vault holds `powerbi-tenant-id` and the rest. Picking the one entry whose name matches
  would save 3 actions on every Power BI workspace (connectionsWindow.ts; the vault sign-in work there).
- **A notebook for a project's pages.** New project… asks only for the folder: no pages notebook (the
  agent's `project_new` takes `notebooks`); New notebook starts empty, outside the project. Use case 11
  types `from data import invoices` and saves into the folder (5 actions), and putting Streamlit pieces
  into data.ipynb instead works but warns on each one. A "notebook in this project" choice would do.
- **A Python with Streamlit for a project** is chosen by its path (4 actions); the app could offer the
  ones it has seen with Streamlit.
- **A relative date filter** ("in the last N days", `current_date - INTERVAL`) would make a daily
  export a grid step that stays right each morning; use case 5 writes the day in Python.
- **A note card's table is cut at the card's edge** in the Sandbox and when printed (the forecast's
  95% range column, use case 9): a wide table in a 5-column note needs wrapping or a smaller font.
- **The forecast chart's two labels overlap** ("Held back to test" and "Forecast") when the held-back
  span is short.
- **Save as zip with unsaved notebooks** zips their saved copies (it says so): it could offer to save.
- **Connection test wording:** "It works: made a mariadb.connections.Connection." names a Python class.
- **The empty notebook cell** is a thin strip until something is typed (screenshots of a new notebook).

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
  `sab.connection`. So the same code runs unchanged in an Azure Function whose settings hold those
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
- **In notebooks:** `sab.connection("Orders API")` gives `conn` (and the connection is a variable by
  its name in every Workbench kernel, like the others). `sab.read("Orders API", "orders")` reads a
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
  (`swissarmybench.streamlit.pages`: each page's id, name and pieces, a piece by its cell's number
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
  `streamlit run` on a temporary folder (`swissarmybench-streamlit-*`), `--server.address=127.0.0.1`,
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
  folder is touched. It runs without Swiss Army Bench.
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
  to a block is a one-line diff). It holds `"swissarmybench": "streamlit-app"`, a version, and the
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
  the type `application/x-swissarmybench-cell`, a small JSON of the path, the number and the document's
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
  **Old pages are dropped, not read:** a notebook's `swissarmybench.streamlit.pages` is not written
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
  as a project. This replaced an earlier layout of the same day (a `sab_tables.py` module and a
  `workbench/` folder), and an earlier data.py rule ("generated, then yours", entries marked
  `# %% [data] name` and refreshed one at a time): both were built and taken out the same day.
- **Left open:** blade cells in data.ipynb are the user's own code (`fx = sab.blade("FX rates")`);
  there is no "add a blade" button. An unsaved data.ipynb or linked notebook is exported as it stands
  but zipped as its file (Save as says so). A project does not remember which Python it runs in beyond
  each notebook's own.

## A starter pack of blades (2026-11-15, the owner's calls; built)

"Can we preload a bunch of useful blades for calling the powerbi workspace like refresh dataset/dataflow,
get refresh status, and other useful blades, as well as some excel and flat file based blades for
manipulating excel files like add sheet, format, add border to cell, set cell values; some dax blades
for dax manipulation cells, and some html blades for creating a wide variety of basic html objects from
data and tables." Decided:

- **A built-in starter pack** ("Swiss Army Bench starters") in every install's blade list, grouped by family:
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

**Built (2026-11-15), on its own branch (`starter-pack`). Changed since the call above:** there is no
Streamlit kind of cell any more, so the Streamlit pieces are snippets for a **Python** cell, and a piece
dropped into a notebook names its cell (it then shows by name in the Streamlit cells pane, ready for a
canvas). 78 starters: Power BI 13, Excel 12, Files 3, DAX 11, HTML 10, Streamlit 29. Decided while
building (each can be changed):

- **Where the pack lives:** `src/swissarmybench/starters/*.blade.py`, inside the wheel, read as a pack
  (the label "Swiss Army Bench starters"), so a new version brings its own. It is **listed apart**
  (`/blades/starters`, the blade list's **Starters**, a line a family that folds, remembered in the
  browser; a search opens the families it finds something in), not in `/blades` or `sab.blades()`: the
  user's list, the Data panel's Variables and the agent's `blades_list` stay the user's own. It is
  **found by name** after the user's saved, folder and pack blades, so `sab.blade("Excel add sheet")`
  works anywhere, and a blade of the user's with the same name wins.
- **Read-only, Copy as your own:** saving or removing a starter is refused in plain words; its page
  shows "<family> starter: read-only", no kind picker and no settings, with **Copy as your own** (also
  the copy button on its row, its right-click menu and `blades_copy`). The copy is "<name> copy" (then
  "copy 2"), as a pack's Save a copy is named, or a name given; it keeps the family, and the copy opens.
- **A Python starter makes one function**, the blade's variable, documented in its first lines with the
  call that uses it: Power BI actions give back a small dict (a list or a history a DataFrame), Excel
  functions the workbook's path (so steps chain), split CSV the new files' paths. Each file holds its
  family's shared helpers itself (a starter copied as your own must stand alone); a test keeps the
  shared part the same in every file of the family.
- **Power BI actions sign in through the connection:** `sab.connection(WORKSPACE)` (the setting, found
  on the save screen like any; "Finance" as in these docs), or a dataset named with its connection
  (`refresh("Finance/Sales model")`, as the app names datasets), or `workspace=`. The connection's code
  now documents `conn.url` and a new `conn.access_token()` (the token, signed in again near its end);
  a connection saved before it is read by its `sign_in`/`token` fields. Signing in waits for the first
  call. Power BI's refusals become `PowerBIActionError` with its own message and what usually causes
  the status. Refresh and wait follows its own refresh by Power BI's request id.
- **Excel safety:** an edit saves the workbook in place (that is its job); a sheet or a file is never
  replaced without `overwrite=True`, and Write table refuses to write over cells that hold values.
  Autofit measures each value's text (Excel's own autofit needs Excel running).
- **Snippet, a blade kind:** text with placeholders `<<name>>`, `<<name: default>>`, and defaults made
  of others (`<<name: by_{column}>>`). Chosen over `{{measure}}` because the HTML cell's own
  `{{ name }}` must stay in a snippet as written, and because the app already reads `<...>` in code as
  "still to fill in". **What a placeholder asks for is read from its last word** (table, column, measure,
  name; a number when its default is one; else text), a column goes with the table of its first words
  (`date column` with `date table`), a name or a label follows its column (`by_region`, Region). In its
  file a snippet is one Python string, `snippet = r"""..."""`, so a blade file stays Python; in the app
  its code is the text.
- **A value is written for the place it stands in** (domain/snippets.py reads the snippet as its
  language does): in DAX the quote that closes the place is doubled (`'` in a table, `]` in a column or
  measure, `"` in text); in Python a string's inside is escaped (braces doubled in an f-string); bare in
  code only a name or a number goes in; HTML is escaped, and inside an HTML cell's `{{ }}` only a name.
  A line break is refused. The rules are the server's (`/blades/{name}/snippet`); the page's form only
  asks.
- **The form** (dropped on a cell of its language, or the cell's More: **Insert a snippet…**, or the
  palette): one field a placeholder, its choices from the DAX cell's dataset (the loaded catalog's
  tables, columns and measures; a measure picked moves the measure's table with it) or the open tables
  and their columns, likely ones first by name (a date table, a date column, an amount). Insert puts the
  text where it was dropped, or at the cursor. A snippet on a cell of another language is refused ("An
  HTML snippet goes in an HTML cell."); dropped between cells, it makes a cell of its kind. A Streamlit
  piece fills an empty Python cell, else makes one below; it names a cell that has no name, from its
  header's `cell_name` (`<<label>> filter`: "Region filter"). In a script (by the palette or the agent)
  a snippet is a new cell: DAX and HTML as their cells are, a piece as `# %% Region filter`.
- **Streamlit pieces: a filter makes one name, the rows its pick leaves** (`by_region`), not the value
  picked: a display reads a table, so any display follows any filter, and filters chain (the date range
  reads `by_region` and makes `in_dates`). The sidebar panel makes several: the rows and each pick. A
  name that starts with `_` is a piece's own; the Streamlit cells pane and the canvas now say what a
  cell makes without those and without `st` and `pd` (the run order still counts every name). Each
  piece imports Streamlit itself, so it runs as it is under `streamlit run` and Streamlit's AppTest.
  Widgets carry `key="<name>_pick"`, with the reason beside them.
- **The agent** (the golden rule): `blades_starters`, `blades_copy`, `blades_snippet` (a snippet's
  blanks and choices, or its filled text) and `workbench_snippet_insert` (the window's
  `snippet.insert`; with `values`, no form). 232 commands; the tool list's budget is 55,000 characters.
- **Also:** the pip package names left domain/blades.py for domain/packages.py (re-exported), to keep
  the domain file under 1,500 lines.
- **Open:** a real Power BI tenant (the stand-in answers as the REST reference documents; a service
  principal may only refresh with NoNotification, and only a dataset's owner may change its
  parameters, as there). A dataflow's refresh status is its transactions; Power BI documents no
  "latest" for it. The DAX snippets are checked to fill and to pair their brackets and quotes, not run
  against a model. The HTML snippets mix colours with `color-mix()` (Edge and Chrome 111 and later).
  The map piece's background comes from the internet in the browser; its dots draw without it.

## Components: your own HTML and JavaScript in Streamlit (2026-11-15, the owner's call; built)

"Is there something even more simple that allows us to bring Rich HTML JavaScript style components
into" Streamlit, then: "Can we just build some more streamlined blades for these types of things".
Decided: no new cell kind and no app change; a seventh starter family, **Components** (9 pieces, the
pack now 87), Streamlit pieces for a Python cell (`language = "streamlit"`), documented for a learner as
the Streamlit family is. Built on branch `starter-components`:

- **The three ways, each piece names its own and why:** `st.html(..., unsafe_allow_javascript=True)`
  (on the page, one way: callout banner, animated KPI counter), a frame (one way: sortable table,
  gauge, timeline), and `st.components.v2.component(name, html=, css=, js=)` (on the page, two way:
  clickable cards, segmented slicer, copy table button, keyboard shortcuts). Every piece carries the
  same "Three ways" paragraph (a test keeps it the same).
- **The frame is `st.iframe`**, not `st.components.v1.html`: in Streamlit 1.67 the latter prints "Please
  replace `st.components.v1.html` with `st.iframe`. `st.components.v1.html` will be removed after
  2026-06-01". Its docstring also says an HTML string is framed with same-origin access to the app, so
  a frame is no security wall: the pieces escape data for a frame as for the page.
- **The two-way value:** the JavaScript is `export default function (component)`, given `data`,
  `setStateValue`, `setTriggerValue` and `parentElement`. `setStateValue("picked", v)` reruns the page
  and the mount call gives it back (`_result.picked`), kept until the next click; `setTriggerValue`
  holds for the one rerun it starts (the copy button, a key press). The mount names its values with
  `on_<name>_change=lambda: None` (needed for `default=`) and a `key=`; the current pick is read from
  `st.session_state[key]` and sent back in `data=` so the cards draw it picked.
- **A two-way piece makes what it sends back** (`picked_region`) **and the rows it leaves**
  (`by_region`), so it wires like a filter.
- **Data as data, never as code:** every placeholder stands in Python (a name, a number, or a string);
  the page's HTML gets `html.escape`d text through `string.Template` (CSS and JavaScript keep their
  braces); a frame's data is JSON in a `<script type="application/json">` with `<`, `>`, `&` written
  as `\u003c`, `\u003e`, `\u0026`; a component's goes in `data=`. The JavaScript writes values with
  `textContent` only.
- **Streamlit runs a component's function again on each new `data` and calls its cleanup only when it
  leaves the page** (read in 1.67's BidiComponent.js): the pieces draw afresh each time, and the
  keyboard piece takes its earlier listener off itself, or one press would be sent once per rerun.
- **Nothing from the internet:** SVG and CSS inline, no CDN; a test refuses URLs, `src=`, `fetch(`.
- **Open:** the app still asks for `streamlit>=1.36` for a project; these pieces need a recent
  Streamlit (checked with 1.67; v2 components and `st.iframe` are newer than 1.36). A frame follows the
  computer's light or dark setting, not the app's theme (the theme does not reach a frame).

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
  `sab.blade` line; its value shows when the focused kernel holds it). **Files:** a folded section at
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
  sales.stapp.json by Swiss Army Bench: change the canvas, not this file.`); only such pages of the same
  app are written over or taken away, and Save as says which file it left alone.
- **A linked file from outside the project** could take the name of the project's own file in the zip
  (data.py, a notebook beside it) and replace it there: it gets a name of its own (`data_2.py`).
- **Play runs when data.py cannot be written** (read-only) and says so; before, it failed outright.

**Named cells** (the owner: "make it possible to name cells so the panel can show them by name").
Any cell can have a name, one line of at most 80 characters; the cell's number stays its identity,
so `@cell7` and canvas links never change with it.
- A notebook keeps it in the cell's metadata, `swissarmybench.name`, which plain Jupyter keeps.
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
default on every time sab is opened" was read:** the switches are the server's, in memory, shared by
every window; a reload keeps them; a new start of Swiss Army Bench shows every panel again. If the owner
wants them remembered across starts, they would go to a small file in the state folder. The agent reads
and sets them with `app_panels`. Not switchable: the grid page's Application row (Settings is there)
and the Workbench's top bar (its "…" is how Settings is reached).

**Held back** (the reviewer would choose differently, the owner did not decide, so the builder's
choice stays): the copied cell lives on the Workbench's own clipboard (a BroadcastChannel), not the
system clipboard; Export keeps its folder that runs alone with the data as Parquet beside Save as; an
agent's Streamlit Export writes Parquet rows to a folder it names without the user's click (this
predates the canvas; a grid export by the agent needs a ticket); the page's removal asks with the
browser's own confirm box.

## Renamed from SwissArmyGrid (2026-11-15, the owner)

"I've decided to rename the app Swiss army bench." Depth: everything. The display name is **Swiss Army
Bench**; the package, wheel, uv tool and commands are `swissarmybench` (`swissarmybench`,
`swissarmybench-mcp`, `swissarmybench-context`), the short alias is `sab` (`import swissarmybench as sab`,
the `sab` terminal command, `%sab_run`, `%%sab_table`, `%%sab_html`, `%%sab`), and the MCP server, the
Claude Code plugin and its skill (`swissarmybench-use`), the marketplace, the VS Code extension, the
installers, the release workflow, the state folder (`~/.swissarmybench`), the environment variables
(`SWISSARMYBENCH_*`), the blade header, the notebook metadata key and the saved pages' mark line all
follow. The GitHub repository keeps its name for now (the owner renames it later), so its URLs stay. (Renamed by the owner the same day: DylanCodyBrown/SwissArmyBench; the links were updated, and the PyPI trusted publisher names the new repository.)

**The old names work for one release, then go** (all in `src/swissarmybench/renamed.py` or beside what
they keep, each tested in `tests/test_renamed.py`): `import swissarmygrid` (a small package that is the new
one under the old name, with a DeprecationWarning); the old commands (one line on stderr naming the new
one, then the new one); the `sag` magics and `sag` in a Workbench kernel; the old metadata key, blade
header, tang, Streamlit app and saved-page marks, read and written over with the new ones; the state
folder, moved on the server's first start (read where it is when it cannot move); the old environment
variables, read after the new ones; the keyring's old service, read and copied across on first read;
the page's remembered settings under the old prefix; the old websocket subprotocol; the old uv tool and
the old `swissarmygrid.chromePath` setting in the VS Code extension. Code the app writes always uses the
new names. **The next release removes them:** `src/swissarmygrid/`, `renamed.py` and every `OLD_*` name.

Decisions taken here (confirm or change): the user's Workbench folder `~/SwissArmyGrid` is not moved (it
holds the user's own files, and recent files point into it): it stays the folder while there is no
`~/SwissArmyBench`. Machine-facing names that cannot hold a space (the keyring service, the Windows mutex,
that folder) are `SwissArmyBench`. The release notes of 1.0.0 to 1.6.0 are history and keep the old name.
The installers remove the old `swissarmygrid` uv tool first, since the new one brings the old commands.

## A desktop app for Windows (2026-11-15, parked on the owner's call)

Asked: "is there a better way to deliver this app than the way we are. Like could it be packaged into a .exe and
feel more like a legitimate windows app?" The owner's answer: "No keep the UV installer as is for now."

Kept here in case it comes back:
- **Not a frozen .exe** (PyInstaller, Nuitka). The app starts real Python processes: blades (`python -I`),
  Jupyter kernels, each notebook's own environment made with uv, and Streamlit in the notebook's Python.
  A frozen exe has no Python to start.
- **An installer that brings its own Python instead:** the standalone Python builds uv uses, with the wheel
  installed, in the app's folder.
- **A native window shell:** pywebview, on Windows' own Edge engine (WebView2), the engine the browser tests
  target. Workbench pop-outs become real windows. Electron would add about 150 MB for nothing.
- **Install and update:** Velopack (a Setup.exe and updates in the background), or MSIX.
- **Signing:** Azure Trusted Signing, so there is no SmartScreen warning.
- **Windows touches:** a tray icon, file associations (.stapp.json, .blade.py), and `winget install`.
- **Needs before starting:** the owner's approval of two new dependencies (pywebview, Velopack) and of signing
  under a verified identity. A real Windows machine is needed to test dragging between two native windows.

## The agent's Streamlit Export waits for the user's Allow (the owner, 2026-11-15)

The owner's decision: **the agent's Streamlit Export needs the user's approval, the same way the grid's
export does.** Until now `streamlit_export` wrote a folder that runs alone, with Parquet copies of the
tables' rows, to any path, with no click from the user.

- **The same approval:** `Approvals` (services/agent.py), one for the whole server (bootstrap), and the
  same prompt in the page and the Workbench window (agentAccess.ts): "The agent wants to export the
  Streamlit app sales.stapp.json:", then the folder it writes (resolved: `..` and `~` worked out), the
  pages, and each table whose rows are copied. Deny, closing the prompt, or no answer in 3 minutes:
  refused (403), nothing written. No second mechanism and no new route.
- **Ask and write in one request:** the grid's export needs a ticket because its download is a second
  request (a GET); the Streamlit export asks inside its own request, so what is written is what the
  user allowed: that folder (refused if it no longer resolves to itself, e.g. a link put in its place)
  and those tables.
- **The window too:** `workbench_window` `canvas.export`, `canvas.saveAs` and `project.new` run in the
  page, which used to send them as the user's. A window command the agent sent now goes as the agent's
  request (`X-Actor: agent`, workbenchCommands.ts `run(args, {agent})`, api.ts `agentApi`), so the same
  rule holds there.
- **The user's own click** asks nothing, as before.
- **The other agent commands that write the user's data:** New project (`project_new`) and Save as
  (`streamlit_save_as`) ask the same way **only when data.ipynb would hold a pasted table's rows** (a
  small paste is written out in its read-only cell; Save as writes a data.ipynb into a folder that has
  none). Otherwise they write code only and ask nothing.
- **Left as they are (code only, or the owner's earlier call):** Export data.py (`project_export_data`:
  a pasted table is a stub there, never its rows), the canvas's file (`streamlit_save`: links only),
  the zip itself (outputs dropped, pasted rows taken out), Play (`streamlit_run`: the tables as Parquet
  in a temporary folder of the app's own, removed when it stops), and the Workbench's documents
  (`workbench_save`, `workbench_run`'s save): they hold what the agent wrote or ran in a kernel, and
  kernel code can write what its Python can, which the owner accepted on 2026-11-14.
- **Open:** a notebook the agent saves can hold outputs that show rows (`workbench_run` saves them).
  Gating every save would stop the agent working in the Workbench, and the kernel can write files
  anyway; say if the outputs should be dropped when the agent saves.

## Autonomy, and the agent's reach (the owner, 2026-11-15)

"I'm giving you autonomy to just go with your best judgment on everything although always lean towards
giving the agent when it needs to do the work."

Decided on that basis:
- **A notebook the agent saves keeps its outputs,** even outputs that show rows. Gating every save, or dropping
  outputs, would stop the agent working in the Workbench, and its kernel can write files anyway (accepted
  2026-11-14). The approval stays only where the owner asked for it: exports that copy rows to a folder.
- **The version is 1.7.0b2.** 1.7.0b1 was never tagged, but a wheel of it was given to the owner. The rename
  changed the wheel's name and commands, so the next build gets a new number.
- **Still as built, and not asked again:**
  - the Power BI sign-in uses Python's own web library for the app registration (no new dependency);
  - the canvas has no separate Cells list (the Data panel's Streamlit cells pane does that job);
  - the uv installer stays (the desktop app above is parked).

## Text cells on the canvas: Markdown and HTML cells on a Streamlit page (2026-11-15, the owner; built)

"Right we should definitely create some markdown blades and make it compatible to drive markdown cells
into streamlit app and make it compatible to drag HTML cells into the streamlit app." "If it were
possible to use a markdown so in a notebook it would be amazing." "Make sure the markdown and HTML
cells are available for streamlit." Built, for the first beta (0.0.1):

- **A Markdown or HTML cell goes on a canvas like a Python cell:** dragged by its number or head, from
  the Streamlit cells pane, or copied and pasted (a script's HTML cell by Copy the cell). The canvas
  commands take them as they are (`streamlit_block_place` and the rest): a block is a link, so the
  app's file is unchanged (no kind, no code) and old app files read as before.
- **On the page** a Markdown cell is `st.markdown(...)` and an HTML cell `st.html(...)`, with
  `unsafe_allow_javascript=True` only when the HTML holds a `<script>` the browser would run (found by
  the HTML cells' own reading: one inside a comment or a `<textarea>` does not count). Checked in
  Streamlit 1.67; the parameter came in Streamlit 1.52, so an export with such a block asks for
  `streamlit>=1.52`. An HTML cell's uses line is the app's: it is left off the page.
- **Names are reads.** `{{ region }}` in a text cell is read on the page through a small lambda per
  name, so Python's parser counts it as a read: the run order puts the filter first, the wiring
  ("reads region") and "place that cell here too" work as for a Python cell. A text cell makes
  nothing. A name no block makes shows *{{ region }} not found*, as in an HTML cell.
- **One filler, the HTML cells' own.** The page fills its names with domain/html_cells.py itself, a
  copy written beside the pages as `sab_text.py` (with a line on top saying what it is): it is standard
  library only and imports nothing of Swiss Army Bench, so an export and a saved project need nothing
  new installed. To make that true, the reading of a value by its shape (a DataFrame, a figure) moved
  from client/html_cells.py into domain/html_cells.py (`record_of`); the kernel's side calls it. The
  copy goes into the live app's folder, an export's folder (beside app.py) and a saved project (beside
  data.py, in the zip, and the README says it needs nothing new). Only when a block names a value: a
  plain Markdown or HTML block is written as its text. The Workbench does not open `sab_text.py` as a
  project's script.
- **Live Markdown in the notebook.** A Markdown cell with `{{ name }}` runs as an HTML cell does (the
  same `%%sab_html` run gives its values and marks) and shows its filled text when not being edited,
  with the HTML cells' states (Not run yet, Out of date · total changed, Run). A Markdown cell without
  names is plain Markdown, as before. **A value in Markdown is always text** (`markdown_text`): every
  Markdown mark (`\ ` * _ { } [ ] ( ) # + - . ! | ~ : $ = ^`) is escaped with a backslash and the
  markup characters as HTML's references, on one line (a line break would end a heading or a table's
  row). Inside code (a code span or a fenced block) only plain words and numbers go, as inside an HTML
  tag. A table alone on its line is a pipe table (first 50 rows, 30 columns, and what it leaves out);
  elsewhere its size. A picture says so (an HTML cell shows it). The Workbench's own Markdown renderer
  now reads a backslash escape and those references as their characters (Jupyter and Streamlit
  already do).
- **Decided while building** (each can be changed): a saved notebook keeps no values for a Markdown
  cell (nbformat gives a Markdown cell no outputs), so after opening it shows its names as written,
  "Not run yet", until it runs; the page writes Markdown with Streamlit's default (no raw HTML), as the
  Workbench shows it; a text block's title is its cell's name, else its first words without marks or
  tags, else "Markdown cell N"; the Streamlit cells pane lists a document's text cells under their own
  heading, **Text**, each marked **T** (the canvas's blocks too), every non-empty Markdown and HTML
  cell of the user's (not the Tables group's headings), so a documentation-heavy notebook lists many.
- **A Markdown starter family** (10, snippets for a Markdown cell): title with subtitle, section heading
  with a value, KPI sentence, callout, key figures table, what this page shows, executive summary, data
  dictionary entry, change log entry, footer with source and refresh time. Each one's description ends
  with the names it reads (`(reads region, total_sales)`, a test holds it to its text); a Markdown
  snippet has no comment of its own, because an HTML comment would show as text on a Streamlit page.
  A typed value is written for its place: inside `{{ }}` a Python name only; inside code as typed (no
  backtick); elsewhere its formatting, linking and name marks escaped (`\ ` * _ [ ] { } | ~ $`, markup
  as references), the rest as typed, so "Made-up, 2026-01-31" reads as it is. Snippet insertion takes
  Markdown cells (the cell's menu, a drop, the palette, `workbench_snippet_insert`); a wrong kind is
  refused ("A Markdown snippet goes in a Markdown cell."). 88 starters.
- **The agent** (the golden rule): the canvas commands place them; `streamlit_cells` lists them with
  their `kind`; `workbench_html_cells` and `workbench_html_run` take a Markdown cell with names;
  `workbench_html_fill` fills a Markdown cell's text with `markdown: true`.
- **Not built:** Markdown cells in scripts (a script has none); pictures in a Markdown cell's names;
  dragging a script's cell (it is copied, as before).
- **Mermaid in a Markdown cell** (the owner, the same day: "Make sure our markdown cell supports
  mermaid rendering."). A ```mermaid block in a Markdown cell is drawn as a diagram when the cell is
  not being edited, by the app's own Mermaid (lazy/diagram.ts, loaded the first time one is needed:
  strict, labels as SVG text, its drawing cleaned by lazy/svgSafe.ts; nothing comes from the
  internet). A broken diagram says why in its place ("This diagram could not be drawn: Parse error on
  line 3 ..."). A script has no Markdown cells, so this is notebooks only. **`{{ name }}` in a
  Mermaid block is Mermaid text** (`mermaid_text`): letters, digits, spaces, `.` and `,` as they are,
  every other ASCII mark in its full-width form (U+FF01 to U+FF5E: a value's `-->` draws as
  `－－＞`, its `"`, `[`, `%%` and `;` mean nothing to Mermaid), so a value can close no label, draw
  no link and start no comment, directive or statement. Mermaid's own entity codes (`#45;`) were tried
  first and show as `&#45;` in this app's drawings (labels are plain SVG text, `htmlLabels: false`, a
  safety setting kept), hence the full-width forms. A name not run yet shows as written, in the same
  form (bare `{{ }}` would be Mermaid's hexagon). A cell that is only a diagram is called "Mermaid
  diagram" on a canvas.
- **On a Streamlit page a Mermaid block stays a code block.** Streamlit's Markdown draws no Mermaid,
  and there is no simple offline way: drawing it needs Mermaid's JavaScript in the browser (about 3 MB,
  inlined into every page through `st.html` with scripts allowed) or a headless browser to draw it to
  SVG when the page is written (Node and Chromium, not this app's to install). The page shows the
  diagram's text; nothing is loaded from a CDN. To be decided by the owner if wanted.

## Power Apps: a separate future project (the owner, 2026-11-15)

Considered: importing a connection from a custom connector's OpenAPI file, a Dataverse connection,
building Power Apps code apps (TypeScript, `pac code`) or canvas apps, and blades for pac's first-class
connectors. The owner: "Power Apps need to remain in their own workbench so that might be a future project
and would actually lend itself to a VS Code extension much better." Not built here.

Kept in case they come back on their own:
- **OpenAPI file → a "Python (your own code)" connection.** GET operations that return arrays become
  tables, the response schemas become their columns, the security type maps to the vault, and other
  operations become action blades. This works for any OpenAPI service, not only Power Platform.
- **Dataverse:** moved out (the owner, 2026-11-16: "Add Dataverse to 0.0.7"): a connection of its own,
  without Power Apps. See "Dataverse: a connection type" below.

## Add API: an OpenAPI file or a short form, made into a ready-to-call connection (the owner, 2026-11-15; first after the beta) — built 2026-11-15

The owner: "if we could create a connection type that literally turns an openapi json into a ready to call
connection type it would be a power feature. You could take a function app or lambda create an openapi.json
then the app could create a new python script that lives beside data called API_Nameoffunctionapp.py where
all the apis for that function app are accessible and we could add the connection in the same step. We
could add a button to the app called ADD API. Or you could use a form to add as many endpoints as you want
and select an auth type."

Planned:
- **An "Add API" button** in the Data panel, the Connections window and the palette, with an agent command too.
- **Two ways in:**
  - an OpenAPI file (2.0 or 3.x), from a file, a URL or pasted (an Azure Function app's OpenAPI extension, or
    an AWS API Gateway export);
  - **a form:** the base URL, an auth type (none; API key in a header or query; bearer; basic; Azure Function
    key `x-functions-key`; OAuth 2.0 client credentials; the vault's app registration), and any number of
    endpoints (method, path, parameters, and whether the answer is a table).
- **In one step it writes `API_<name>.py` beside data.py:**
  - a client class with one typed method per operation, documented from the spec, with paging and retries;
  - array answers come back as DataFrames;
  - standard library only, so the same file runs in an Azure Function;
  - secrets read from environment variables mapped to the vault, never written in the file.
- **It adds the connection in the same step** (the "Python (your own code)" kind): Connect imports the client,
  List the tables lists the GET operations that return arrays, and Read a table calls one with the row limit.
  The catalog, Open as grid, SQL cells and data.py all work as for any connection.
- **Re-import when the spec changes:** the file is marked as made from the spec, the change is shown before it
  is written, and the user's own code lives in their notebooks, never in the made file.
- **Tests:** made-up specs (2.0 and 3.x, each auth type) against a local stand-in service, and the made file
  imported in a plain Python.
- **Auth types (the owner: "Support oauth2 and API keys and jwt"):**
  - **API keys:** in a header (any name, `x-functions-key` included), a query parameter, or a cookie.
  - **OAuth 2.0:**
    - client credentials (unattended runs, the Azure Function);
    - authorization code with PKCE in the browser, for trying it by hand, with the refresh token kept in the keyring;
    - device code for machines with no browser;
    - tokens cached until shortly before they expire;
    - the vault's app registration for Microsoft APIs.
  - **JWT:**
    - a ready-made bearer token (from the vault or keyring);
    - a token got from the API's own login endpoint (username and password, or a key) and refreshed on 401;
    - a JWT the client signs itself: HS256 with the standard library; RS256 and ES256 through `cryptography`
      when the user's Python has it (the made file says so; it is not a dependency of the app).
  - **Basic and bearer,** as before.
  - Every secret comes from an environment variable mapped to the vault or keyring, never written in
    `API_<name>.py`. The spec's `securitySchemes` (or `securityDefinitions`) pick the type and fill the form.
- **Presets for the three big function hosts (the owner: "lambda and function apps are the two big
  supported apis as well as Google's ... fire[base]"):**
  - **Azure Function App:** the function key (`x-functions-key`), or Entra ID through the vault's app registration.
  - **AWS Lambda:** none, an API key (`x-api-key`), a Cognito JWT, or IAM with Signature Version 4 (function
    URLs and API Gateway). SigV4 becomes its own auth type: signed requests from an access key in the vault,
    with the standard library.
  - **Google (Firebase, Cloud Functions, Cloud Run):** a Firebase ID token (JWT), or a Google identity token
    minted from a service account key in the vault (RS256, through `cryptography` when present).
  - A preset fills the form (the URL pattern, the auth type, the header names), then reads the OpenAPI
    document if the host has one, or the endpoints are added by hand.

Built (2026-11-15, branch add-api). Decisions made in building it:
- **Where it is:** the Connections window's footer (**Add API**, beside Add connection), the Workbench's
  **+ Table** menu and its palette (`data.addApi`), and the agent's `connections_api_choices` and
  `connections_api_add` (`preview=true` writes nothing). It is drawn inside the Connections window; after
  Add, the new connection's own form opens (the Python connection form), so where each variable comes
  from is chosen there with the controls that already exist, then Test and Save.
- **One file per feature, two in the domain:** `domain/apis.py` (the spec, the form, the auth types, the
  presets, the connection's boxes, the changes) and `domain/api_clients.py` (the made file's text). The made
  file's fixed parts are text templates in the domain (it may not import urllib); every value from the spec
  goes in as a literal (JSON-quoted) or a checked name, and docstrings are escaped, so a spec cannot write
  code (a test tries).
- **The made file is one class** (`OrdersApi` in `API_Orders.py`): the auth's code is the class's own private
  methods, only the chosen type's, with only its imports. No `from __future__`, `Optional[...]` types, so it
  runs on Python 3.9+ and can be pasted inline. The constructor takes `base_url` (else `<PREFIX>_URL`, else
  the spec's) and each secret as an argument, else from its environment variable; a needed one missing fails
  at once, by name. Retries: 429 always, 5xx and unreachable only for idempotent methods, `Retry-After`
  honoured, backoff doubling. Paging: a `Link: rel="next"`, a next link in the answer (`@odata.nextLink`,
  `nextLink`, `next`, `links.next`), else the operation's own page-token, page-number or offset parameter;
  a page that repeats ends it; `max_rows` stops early. Rows are found at the schema's wrapper key
  (`items`, `value`, `data`...). `tables()` and `read()` are the connection's List the tables and Read a
  table; a table whose columns no schema names is asked for one row.
- **Tables are the GET operations that answer rows and need no argument,** named after their path's words
  (`/v1/orders` -> `orders`), in their first tag's schema (else `api`).
- **Variables:** `<PREFIX>_API_KEY`, `_TOKEN`, `_USERNAME`/`_PASSWORD`, `_CLIENT_ID`/`_CLIENT_SECRET` (and a
  `{tenant}` in an OAuth URL becomes `<PREFIX>_TENANT`), `_JWT_SECRET`/`_PRIVATE_KEY`,
  `_SERVICE_ACCOUNT_KEY` (the key's JSON), `_FIREBASE_API_KEY`/`_EMAIL`/`_PASSWORD` or `_ID_TOKEN`; SigV4 reads
  AWS's own names (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`), which a Lambda sets.
  Connect passes each one (`os.environ["..."]`), so the Python connection's form finds and maps them.
- **Connect loads the file by its path** (`importlib`, registered as `API_<name>` in `sys.modules`), so the
  connection works from any notebook and the blade runner, and a notebook beside it imports the same module.
- **Entra ID** is OAuth 2.0 client credentials against `login.microsoftonline.com/{tenant}` with the
  app's `api://<application id>/.default` scope (the vault's app registration is three variables mapped to
  the vault). **Cognito** is a ready JWT. **AWS SigV4's service** is read from the address (`lambda-url` ->
  lambda, else execute-api) unless set. **Google's audience** is the address's root unless set. Firebase's
  sign-in and refresh addresses are settings (Google's by default) so a stand-in can take them.
- **OAuth's browser sign-in** listens on 127.0.0.1 (a free port unless set: RFC 8252's loopback redirect).
  Device code prints its message on stderr. A refresh token goes to the keyring when `keyring` is there,
  else lasts as long as that Python.
- **YAML:** read only when the app's Python has PyYAML (it is not a dependency); otherwise the message asks
  for JSON. Fetching a document's address is Add API's one outbound request, at the user's (or agent's) word.
- **Re-import:** the file's first lines mark it (`# swissarmybench-api: {...}`: what it was made from, the
  base URL and auth settings, no secret). The changes compare each method's signature and its
  `METHOD /path` (read with ast), plus the auth and the address. A file without the mark, or a connection
  of that name that does not load this file, is never replaced (409). Re-adding keeps the connection's
  variable sources.
- **Not opened as a tab:** `API_<name>.py` is a `.py` in the project, so Open project lists it with the
  scripts (left as it is).
- **A SQL cell on any Python connection** (not only Add API's): DuckDB in the kernel over its tables, each
  read whole by Read a table the first time a cell names it (`client/sql_cell.py`).
- **For the exporter (branch one-script):** `Apis.inline(folder, codes)` (services/apis.py) gives, for each
  `API_` module the code imports that Add API made and that is beside the notebook, `{"module", "code"}`:
  the file without its docstring plus three lines that make `import API_Orders` find it. The wiring is the
  merge's.
### The Add API form, labelled (the owner, 2026-11-16) — built 2026-11-16, branch add-api-form

The owner's words, with a screenshot of the form: "no idea how to fill out this form to add an API this is
really ugly and and not user friendly, those inputs are not even labelled." (One cramped row of unlabelled
boxes per endpoint, the pink OpenAPI / Endpoints toggles, the base URL after the endpoints.)

Built, inside the form only (web/src/addApi.ts and its styles; how the form is opened is unchanged):
- **Two clear choices at the top**, as the connection type picker's tiles: **I have an OpenAPI document** /
  **I'll list the endpoints myself** (a radio group, the chosen one marked in the theme's teal, not the
  accent). Nothing else shows until one is chosen.
- **The order you think in:** (the document's address, when that is the choice), **Name** and **Hosted on**
  (the preset, renamed: "Anywhere", Azure Function App, AWS Lambda, Google; it fills the base address and
  the sign-in), **Base address** (with Find its OpenAPI), **Sign in** (its settings in a box of their own),
  **Endpoints**, **Save the file in** (the folder), then the preview.
- **Every field labelled**, by a real `<label>`: Method, Path, Parameters, Read as a table, Columns to keep,
  each sign-in setting. A test checks that no visible input, select or textarea is left without a label.
- **The `*` replaced:** the box is Parameters (`status, limit`), and each name gets a **Needed** tick as a
  chip under it; a path's `{word}` is shown ticked and fixed. A typed `id*` still ticks it. (The owner's
  screenshot read the box as columns; it was the parameters. **Columns to keep** is now a box of its own,
  shown when Read as a table is ticked: the form's `columns`, which the page had never offered.)
- **One card per endpoint**, numbered, with its own Remove and **Try it**.
- **Try it** (`POST /apis/try`, the agent's `connections_api_add(try_it=<operation>)`): the client is made
  as Add would make it, pasted into a draft Python connection (`api_clients.inline`, written nowhere) and
  its Read a table run in a child process for the first 5 rows. Offered on a GET read as a table that needs
  no value (otherwise disabled, its tooltip says why; the server refuses the rest in plain words). A
  document's tables each have a Try button in the preview list.
- **A box per variable the file reads** (`ORDERS_API_KEY`, a password box for a secret) under the sign-in:
  what is typed is used by Try it (a secret as a typed password, never kept by the try), and on **Add** it
  is kept as the connection's (a secret in the keyring, the rest as a plain value). Empty: this computer's
  environment. **Decision:** typed once, not twice; the connection's form after Add can still point it at a
  vault. A vault is not offered for Try it itself (left for later).
- **Calm spacing**, the other connection forms' field look, at most 860 px wide; light, dark and a narrow
  window checked by screenshots. `input[type="url"]` now has the shared field look (it had the browser's).
- A failed try (no key, the API's 401) is a 400 with the run's message, not a 500.

## Beta mode: the beta log and notes (the owner, 2026-11-15)

"After the beta release I will probably have a whole host of things to fix or I don't like. So let's build
in a log that I can dump back to you that doesn't expose data but lets you have enough info to fix issues
the server runs into. Also give me a temporary ability to right click anything in the app and leave a note
on that visual that saves to the log so you can trace what was the issue and I can tell you what is wrong."

And: "Make it so we can turn off beta mode easily and turn it back on at any point if we need this level of
testing down the road."

Decided:
- **A new thing on disk, the owner's call for the beta:** `~/.swissarmybench/logs/beta-<day>-<part>.jsonl`,
  one JSON line per event, about 7 days or 20 MB kept, pictures in `logs/pictures/`. Written by a thread of
  its own from a queue (a full queue drops the event), at most 600 events a minute (then a "dropped" line).
- **Never in it:** cell values, SQL, code, secrets, environment values, file contents, full paths. Messages
  are redacted (quoted text, numbers of five digits or more, e-mail addresses, key=value secrets, long
  tokens, DuckDB's `LINE 1:` echo; the home folder is `~`, a path's folders and file name hidden, its
  extension kept); table and column names are `table#n`, `col#n`, the mapping in memory only. The
  server's frames are file:line and function names. A note's element never keeps a cell's or an editor's
  words (the page sends none; the server drops them again for data roles and places).
- **Kept as typed:** a note's own words (the user's message to the developer). The picture only when ticked.
- **One switch, Beta mode,** for the log and the notes together (two switches were not worth it). It
  lasts across restarts in `beta.json` (unlike the panels); `SWISSARMYBENCH_BETA=1` or `0` wins, and then
  the switch is locked. Off: nothing written, no "Leave a note…", no listener on any page; the files
  stay until Clear the log, so they can still be exported. On again: at once, no restart.
- **The default is ON for 0.0.1.** The release after the beta flips ONE constant:
  `BETA_MODE_DEFAULT` in `src/swissarmybench/domain/beta_log.py` (a saved choice and the variable still win).
- **The agent** reads the same redacted log (`app_beta_log`, `app_beta_notes`), switches beta mode
  (`app_beta_mode`), clears it and exports the zip (`app_beta_log_export`: its zip leaves the notes'
  pictures out; only the user's export carries them). A note itself is the user's own words, typed in the
  page: no command leaves one (tests/test_cli.py NOT_COMMANDS lists the page's error report route).
- **Slow** is 2 seconds to the first byte (`Settings.beta_slow_seconds`); routes that wait on purpose (a
  snapshot, a window's answer, a kernel's start, a new environment, an export's Allow) are not slow.
- **Open:** a value the user's own code puts unquoted into an exception message ("cannot parse Globex")
  is not recognised as data; DuckDB and Python quote values, which the redaction hides.

## One script, one notebook: Export as one Python script… / as one notebook… (the owner, 2026-11-15; built)

The owner: "I need to be able to export any data analysis notebook as an inline python automation where
all connections, vault logic, and data transformations are bundled into one python script that is just
downloadable." And: "It's not runnable with UV, it's runnable as standalone from any Python terminal."
And: "Notebooks can also be exported as inline self contained automations. For context my current
notebook scheduler supports running jupyter notebooks and python scripts but they have to be linear and
self contained with any connections or data imports inline." On the vault: "The app reg secret is a
vault secret." and "No need to enter from the machine."

Decided:
- **Two renderings of one plan** (domain/script_export.py `plan`; the helpers' text in
  domain/script_runtime.py): the script (`render_script`) and the notebook (`render_notebook`). The order:
  the package check, the settings, the helpers, the vaults and connections, each table's load and grid
  steps as one DuckDB query, then the cells. Markdown is comments in the script, Markdown cells in the
  notebook.
- **Plain `python <file>`:** REQUIREMENTS (module -> pip requirement, lower versions where they matter:
  duckdb>=1.1, pandas>=2.0, openpyxl>=3.1...) checked with importlib before anything third-party is
  imported (every such import sits inside a function or `run()`). Missing: one message with the exact
  `"<sys.executable>" -m pip install ...` and exit 3. `--install` runs that pip, only when asked. The
  PEP 723 header stays, as comments, for uv users; nothing relies on it. Exit codes: 0, 1 failed, 2 a
  setting missing, 3 a package missing.
- **`main()`** raises on failure (an Azure Function's run then shows as failed); `cli()` logs to stdout and
  turns that into the exit code. The top comment gives the Function's timer trigger and its
  requirements.txt (the same list).
- **SETTINGS:** every environment variable the script reads, one per line, where it came from (the
  keyring, a key vault's entry, a secret blade, a plain value, the notebook's own code); a plain value is
  its default, a secret is never written. Checked together before anything runs; a vault's are read from
  the vault then too (a missing role fails first). The notebook's settings cell is tagged `parameters`
  (papermill); passwords are best given as environment variables (papermill writes its parameters into
  the notebook it runs).
- **The pieces are the blades' own code**, each a small cached function: a database's Connect (its
  `secret("x")` reads the variable SETTINGS names), a file's path (DuckDB views, as the SQL cell makes
  them), a Power BI workspace (its sign-in and DAX, already standard library), your own Python's Connect
  and Read a table, a blade (the Excel starters' functions). `%%sql`, `%%dax`, `sab.sql`, `sab.dax`,
  `sab.read`, `sab.blade`, `sab.connection` and a connection named by its Workbench variable (`shop`) call
  them; the package's import goes.
- **An Azure Key Vault is read by the standard library** (no azure-identity, no azure-keyvault-secrets
  in REQUIREMENTS): the variable when set, else the managed identity (IDENTITY_ENDPOINT and
  IDENTITY_HEADER in a Function App or App Service, `AZURE_CLIENT_ID` for a user-assigned one; a VM's
  IMDS with a 2-second wait), then, for a vault that signs in as you and only when azure-identity is
  installed, DefaultAzureCredential; then Key Vault's REST GET (`/secrets/<entry>?api-version=7.4`),
  which needs only "get secret". Tokens and values are kept in memory for the run. A 403 says the Key
  Vault Secrets User role. A vault that loads every secret finds an Azure entry by its name (no list
  permission needed). Any other vault is its own code.
- **The Azure Key Vault connection's Sign in:** As you (DefaultAzureCredential) or Managed identity (an
  optional client id). An app registration lives IN the vault as entries (Power BI's), never typed on
  this computer to open the vault: an app-registration sign-in for the vault was built, then dropped on
  the owner's call the same day. A saved vault without the choice reads as As you.
- **Left out, with a line that says so:** HTML cells, Streamlit's cells, `display()`, a cell's last bare
  expression, `sab.push`/`sandbox`/`watch`/`load`. IPython's lines translated where Python has the same
  (`%pip install` into REQUIREMENTS, `%env` (a secret's name becomes a setting, its value dropped),
  `%cd`, `%time`, `%matplotlib` and `%load_ext` dropped); others (`!cmd`, `%run`, `%%bash`), `import *`,
  a top-level `await`, `sab.stats` are refused by cell. With `stub`, each such cell is a stub that raises
  FILL IN and the rest is exported; the page asks first.
- **A table no load can read again** (pasted, dropped, pushed) is a stub that raises FILL IN; its grid
  steps stay after it. No rows are ever written.
- **Checked before writing:** it compiles; ruff (`--isolated`, E9, F63, F7, F82: an undefined name) when
  the app's Python has it, each finding named by its cell; no saved password's value (every inlined
  piece's keyring values are checked); no pasted rows. A value or a row: refused (403), nothing written.
- **The agent** (the golden rule): `workbench_export_script(path, format, to, stub, check)`, one command
  with a format argument rather than two; the window's palette `file.exportScript` and
  `file.exportNotebook`. Code only, so it asks no Allow.
- **Open:** an exported script cannot follow a closed table's grid steps (a table not open is exported as
  its cell last held it); a user's function that writes another cell's variable with `global` now writes
  the module's (the cells run inside `run()`).
- **Add API's clients travel inline (the integration, 2026-11-15):** an `API_<name>.py` beside the
  document that its code imports (`import API_Orders`, `from API_Orders import OrdersApi`), and that Add
  API made (its mark), is written inside the script (its own section after the connections) and the
  notebook (a cell of its own), followed by the lines that put it in `sys.modules`, so the import works
  without the file (services/apis.py `inline`, given to the exporter by bootstrap). It is no
  requirement; what it imports is (pandas, for its DataFrames). The variables it reads are SETTINGS
  (optional: "the API client reads it when no argument gives it"), never their values. Not yet: a
  notebook that reads the API through its connection (`sab.read("Orders", ...)`) exports the
  connection's Connect, which loads the file from where it was written.
- **Approved outputs in the export: not wired (the integration, 2026-11-15).** domain/approvals.py is
  standalone, but the exported script drops what a cell only shows (its last bare expression,
  display()), which is what an approval snapshots, and an approval holds a table's first rows, which an
  export never writes. A `--check-approved` export needs the cells' outputs captured in `run()` and the
  approvals carried without their rows (`without_rows`); `python -m swissarmybench.client.standalone
  x.ipynb --check-approved` does the check meanwhile.

## Controllers, Test this page, thin cells, and two starter families (the owner, 2026-11-15: "Do it"; built)

From the plan after the beta (controllers, thin cells) and "Non-data cells on the canvas" (the Text and
layout family, the pinned footer). Built on its own branch (`controllers`). Decided while building (each
can be changed):

- **The contract is the header's Makes line, and it is Python:** `# Makes: region: str = "All";
  by_region: table = orders`, read with Python's own parser (annotated names, `;` between). Types: str,
  int, float, bool, date, list, table, any; a default is a plain value (a date as "2026-01-31", written
  on the page as a date), and a table's default is another table's name. The starter pieces' existing
  "Makes: by_region" and "Makes: nothing (it only shows)" lines are contracts of names only, so every
  piece already has one, and the starters' header test now reads Makes through the same parser. The
  line is case-insensitive and only read in the cell's leading comments. `# Role: filter|action|view`
  is optional; otherwise a button with a callback is an action, a cell that makes names with a widget
  is a filter, any other cell that calls Streamlit is a view, and the rest is model work ("").
- **What a contract checks:** a name it declares that the code never makes, a type that is not one of
  the list, a default that is not its type, a default that is a name for anything but a table. Red on
  the block. A name the code makes but the line leaves out is not a problem (helpers).
- **A missing maker gives its default:** when a block reads a name whose maker is linked (in any file
  the canvas links to) but not on the page, and that maker's contract has a default, the page writes
  `region = 'All'  # Region filter, sales.ipynb @cell3` once above the blocks (a table default puts the
  table in the page's preamble), and the block says quietly `region = 'All' · Region filter is not on
  this page`. The live page, the export and the saved pages all do it. Without a default the old red
  "place that cell here too" stays.
- **The check** is in every canvas state (it is cheap: Python's parser), so there is no Check button:
  the defaults used, contract problems, a name two blocks make (the first placed wins, as before), and
  a cycle named with its blocks and names. `streamlit_check` gives the same to the agent, with each
  controller.
- **The Properties panel's API (for the wb-modes branch):** every canvas block in `GET
  /streamlit/apps/{app}` carries `controller`: `{"role", "makes": [{"name", "type", "default",
  "declared"}], "widgets": [{"kind", "key", "label", "form", "callback"}], "params", "problems",
  "declared"}` (null for a text block or a gone cell), plus `defaults`, `contract`, `thin` and
  `failures`; in TypeScript, `Controller`, `controllerOf(block)` and `BlockState` in
  workbenchStreamlit.ts; in Python, `domain/controllers.describe(code).to_json()`.
- **Test this page** (beside Play; `streamlit_test`; the window's `canvas.test`): the page written as
  the live page is, but each block also records its error in `st.session_state`, into a temporary
  folder of its own with the tables it reads as Parquet (and data.py, written as Play writes it); then
  a runner under Streamlit's AppTest, in the app's own Python (`python -I`), opens the page and tries
  each widget with a plain-text key: a selectbox, radio, pills or segmented control's first six
  options; a multiselect none, all and the first; a slider's ends (a range: whole, lowest, highest); a
  toggle both ways; a number box's ends (else 0 and -1); a text box empty and a text nothing matches; a
  date range of one day; a button clicked twice (a widget in a form presses its Submit). One at a time,
  each put back after; then each query parameter the page reads (`st.query_params`, also through a
  name the cell gives a text) set to nothing and to a value no option has, on a fresh page. 150 seconds
  in all; what was not tried is said. Failures land on their blocks in red (the value tried, the
  error, at most three a block, each error once); passing blocks show nothing; a toast says the count.
  A result holds while the blocks' code, tables and defaults are what was tested (moving a block keeps
  it; adding one, or changing a cell, drops it). A Python without Streamlit says so, as Play does.
- **Thin cells:** a hint on a code block (not a text block, not a cell of data.ipynb) whose cell calls
  Streamlit and has a top-level assignment that filters, groups or joins an open table or a data.py
  name and reads nothing else (a widget's pick makes it a controller's work: it stays; a name starting
  with `_` stays; a line sharing its line stays; a name given again by a line that stays stops the
  move). Lines that only read moved names move too. **Move to data.ipynb** (the hint's button,
  `workbench_canvas_move_to_data`) appends a cell named after the first name at the end of the
  project's data.ipynb (the canvas's folder), headed `# From Big orders, views.ipynb cell 3` (never an
  `@cell` link: in data.ipynb it would name one of its own cells), with the imports those lines use, and
  leaves `from data import big` where the lines were. The window makes both changes in its open
  documents (opening them when they are not) and leaves them unsaved, as typing does; a project without
  data.ipynb is refused in plain words.
- **The Controllers family (5):** a filter with defaults (its contract explained for a learner), a form
  with validation (a range refused with what to fix, the last good range kept in session state), an
  action button whose callback puts the page's filters back by forgetting their widgets' keys
  (idempotent: twice is once), a cross-page filter (the pick copied by on_change into a session-state
  name of its own, because Streamlit forgets a widget's value on a page without it), and a query
  parameter filter (opens from `?region=South`, writes the pick back, an unknown value opens on All).
- **The Text and layout family (9):** title with subtitle, section heading, divider, caption, callout,
  logo, image (both read from beside the app, a missing picture said), spacer (`st.html` with a box of
  a height, so it runs on Streamlit before `st.space`), and a footer with its source, row count and read
  time, pinned to the bottom of the window by default ("Pin to the bottom: yes"): a keyed container and
  a `<style>` through st.html, on Streamlit's own light or dark background (`st.context.theme.type`; a
  theme with colours of its own is not matched). 111 starters; the two families come after Streamlit.
- **Agent commands:** `streamlit_check`, `streamlit_test`, `workbench_canvas_move_to_data` (240
  commands; the tool list's budget is 57,000 characters).
- **Open:** a widget whose key is worked out as the page runs (an f-string) is not tried; AppTest has no
  browser, so a component's JavaScript is not exercised; Test this page runs one page at a time; the
  State panel and the Controller role's editing in Properties are the wb-modes branch's.
## Lineage with values, and approved outputs (the owner, 2026-11-15: "Do it"; built)

The owner: "the cell tracing you showed from app back through every cell to the data should be a flow
chart mermaid that gets created in reality in an overlay. You can right click the streamlit cell on the
app bench tab and select lineage and boom see the whole thing." And: "Maybe with an output cell per cell
on the left so you can see outputs and variable values as they flow through the cells".

- **The graph** (domain/lineage.py): from a canvas block or any cell, back to the data by what each cell
  reads. A name comes from: on a canvas page, the first block placed that makes it (the page's own run
  order); else the nearest cell above in the same document (else the first below); else the project's
  data.ipynb (its last maker: data.py runs top to bottom; `from data import x` goes there too); else an
  open table. `@cell7` in a comment is a dotted edge. A table's read-only cell goes back through each
  enabled grid step (one node each; a header's sort is a way of looking, left out) to the user's cell
  that made it, else to its origin (file, connection, paste). Connections and files named in code
  (`sab.sql("Shop", ...)`, `pd.read_csv("x.csv")`) and a SQL or DAX cell's connection are sources. A
  cell with a Streamlit widget (or a `# makes:` header, the controllers branch's contract) is a
  controller (a hexagon). Names made only by an import are not edges. Nodes in flow order: makers
  first, ties broken by data.ipynb first, then each document's own order. At most 120 nodes.
- **The overlay** (web/src/workbenchLineage.ts): right-click a block (the canvas), a cell's head or
  output, or a line in the editor (notebook or script), or More: Lineage, or the palette, or
  `window.openLineage(target, into?)` (the agent's and the tests' door; `into` draws it in place, as
  the Data mode's Lineage view does). The Mermaid flowchart top to
  bottom on the right, drawn at its own size with the app's Mermaid and cleaned as every drawing is;
  each node shows its name, `doc @cellN` and its value in a word ("1,204 rows", "West"). On the left one
  card per node, placed at its node's height (pushed down when two would meet). Kind colours: a card's
  left edge and a node's stroke in the notebook's blue or the script's green (the `--kind-*` tokens when
  the theme has them, else `--cat-2`, `--cat-3`); a block on the page is marked "page" in violet.
- **Values** (services/lineage.py, client/lineage_values.py): summarised, never whole. A table: rows,
  columns, the first 5 rows of 12 columns, the row change from the table before it in the flow (a grid
  step: from the step before). A value: itself, cut at 400 characters. A figure: a small PNG (40 dpi).
  An error in red: the cell's last run in the window, or the block's on a playing page. Where from: a
  block on a playing page from what the page noted as it ran (`sab_lineage.py`, a copy of
  client/lineage_values.py beside the live page only, writing `lineage-<page>.json` in the app's
  temporary folder); else the cell's document's kernel (a user expression, as the Variables pane);
  tables and steps from the grid. **Decided:** a kernel holds one value per name, so two cells that make
  the same name show its latest value. A cell that calls Streamlit does not run in the kernel: its values
  come from a playing page only.
- **Live:** asked again every 3 seconds while open and the window is visible, and at once when a run
  ends, a grid changes or a Streamlit app changes; drawn again only when a value changed. A filter
  changed on the page (or in State, which reruns the page) reaches the cards through the page's notes.
- **Approved outputs** (domain/approvals.py, web/src/workbenchApprovals.ts): Approve the output (the
  cell's More and right-click menus, the palette's Approve the cell's output, `workbench_cell_approve`)
  keeps a snapshot in the cell's metadata (`swissarmybench.approved`, with when): the printed text
  (stdout only: stderr holds warnings, which differ between computers), each table read from the HTML
  pandas and Polars show (columns, first 50 rows, the whole shape), a mark of each picture or chart,
  the error. Memory addresses and run counts make no difference. After each run the cell is compared;
  a difference shows an amber "⚠ Changed since approved" note with the lines (a text diff; a table's
  shape, columns added and removed, changed cells, 20 at most and the rest counted) and Approve this
  output. The same output shows nothing (no confirmation labels). Markdown cells have no approval;
  scripts have no metadata, so no approvals (a script's cells are traced, not approved).
- **Headless:** `python -m swissarmybench.client.standalone data.ipynb --check-approved` runs the
  notebook top to bottom in its own folder (IPython when the Python has it, plain Python otherwise),
  stops at a failing cell, compares each approved output, prints a report and exits 1 when any cell
  failed or changed. **For the one-script export:** domain/approvals.py imports nothing of the package
  and only the standard library, so it can be inlined; `snapshot(outputs)`, `compare(approval, snapshot)`
  and `summary(diff)` are its whole interface.
- **No rows leave in a zip:** Save as keeps each approval's marks and shapes only (`without_rows`), so
  `--check-approved` on the unzipped project still tells a change ("rows: 3 → 2", "the printed text
  changed"), without the cells.
- **Agent:** `workbench_lineage` (the graph, its Mermaid and each value; values marked as the user's
  data), `workbench_lineage_show` (the overlay on screen), `workbench_cell_approve` (`remove`),
  `workbench_approvals`, `workbench_approval_check` (outputs against an approval, no window).
- **Open:** the cards line up with the nodes by height, but nodes on one rank stack their cards; a
  wide flow scrolls with the cards. The kind colour tokens come from the wb-modes branch; this branch
  falls back to the chart series colours until they merge.
## Kind colours and the Workbench's four modes (2026-11-15, the owner's calls; built)

The owner: "App violet, notebook blue, script green", and approved the modes' mockup (App, Notebook, Script,
Data) with corrections: never "pieces" on screen (they are cells: "Data | Starters", "Source cell"); the
source document's colour wherever a cell shows; violet only for the app. Built on branch `wb-modes`:

- **Kind colours:** tokens per theme in grid.css (`--kind-app`, `--kind-notebook`, `--kind-script`;
  domain/kind_colours.py holds the same, and a test keeps them equal and at 4.5 to 1 against the page and
  the panels, 7 to 1 in the high contrast themes, since `@cell7` is written in them). Shown as a thin edge
  or a mark beside the kind's icon on tabs, the group's band (its front document's), the Data panel's
  files, the Streamlit cells pane and canvas blocks (by source document, with `doc @cellN` in that
  colour), Properties' Source cell, and the Recent and Move menus. data.ipynb is a notebook (blue) with the
  data's own icon; a blade or a catalog table wears none. Amber is refused as a kind's colour.
- **Settings' Kind colours, shared by every window, kept across restarts** (Claude's call): a colour is a
  choice made on purpose, unlike a panel switched off for a while, so it is kept in `kind_colours.json`
  in the state folder (the panels deliberately are not). A chosen colour is made readable in each theme
  (moved toward black or white, its hue kept). The agent: `app_kind_colours`.
- **Each document's panels sit beside it in its group** (workbenchModes.ts), so two groups side by side
  keep their own (mockup 10); the status bar's toggles are the focused document's. Each has a switch in
  Settings' Panels (Properties, State, Starters, Outline, Run settings, Run history).
- **App:** a click selects a block (violet outline); Properties shows its name (renaming it names the
  cell in its document), width and height, Source cell, makes, reads, Feeds and its widget's value on the
  live page; the wiring is violet arrows from it to each block that reads what it makes. With no block
  selected, the **page settings** (title, icon, Wide or Centred, logo, theme colours) are kept in the
  app's file (`"settings"`, one line; old files read as before) and written into the live page (the
  entry's `st.set_page_config` and `st.logo`, `.streamlit/config.toml` in its folder), the export (app.py
  and `.streamlit/config.toml`) and the saved pages (each pages/*.py starts with them; the project and the
  zip get `.streamlit/config.toml`, never over one of the user's own, told by its first line). The logo is
  a path relative to the app's file; it is not copied into an export. Edit's tools: undo and redo (the
  layout, 50 steps, this window's), align (left edge, centre, right edge, full width), duplicate (another
  block linked to the same cell), zoom (50 to 150%). Play's Desktop, Tablet (820 px) or Phone (390 px),
  and Light or Dark through Streamlit's own `embed_options` for the app only.
- **State:** the live page writes what its session holds (`st.session_state`: widget values by key, the
  page's own values; a plain value as itself, else what it is, "DataFrame, 10 rows") to `_sab_state.json`
  in the app's temporary folder after each run (a tail added to each live page only, never to an export
  or a saved page); the panel reads it every 1.5 seconds while it is open and the page plays, each key with
  the block whose widget it is. **Reset state** opens the page again with a fresh session.
- **Starters:** the Data panel's Data | Starters shows the 29 Streamlit starters in their five families
  (by their tags: Filters 7, Displays 10, Layout 4, Interaction 6, Feedback 2), each with a small sketch.
  A drop (or a click: the end of the page) fills the starter's form, writes it as a real named cell of the
  project's mockups notebook (one beside the app whose name says mock; else `app mockups.ipynb` beside it,
  made and saved; an existing file of that name is opened, never replaced), saves that notebook and
  places the cell's block where it was dropped. The agent: `canvas.addStarter` with `values` (no form).
- **Notebook:** each cell remembers the code it last ran and when (this kernel's order of runs);
  domain/notebook_flow.py says edited (its code changed) or out of date (a name it reads was made again
  since it ran, or its maker is edited or out of date) with the names. Only these states are shown
  (principle 7.9). The Outline: headings and named cells, the stale ones marked. Run up to here on the
  selected cell. Open as grid on a DataFrame's output was already there. Present: the notebook as a
  document (text and outputs; code cells that drew nothing are left out), the Data panel folded while it
  shows.
- **Script:** Run settings: arguments (Run file passes them too, as `sys.argv`) and each variable the
  script needs: those it reads (by line; only `os.environ["X"]` counts as required) and each connection's
  and blade's passwords (`sab.read("Warehouse")`: WAREHOUSE_PASSWORD, as a run without the app looks
  for it). Sources: This computer, a Plain value (refused for a name that reads like a secret), a Key
  vault's secret (read through the vault blade when the run starts). Kept by the script's path in
  `run_settings.json` (a plain value only, never a secret's). The keyring is not offered as a source for
  a script (no place to type a value safely here yet). **Run as scheduled** (server/script_runner.py):
  `python <script> <arguments>` in the script's own Python and folder, a fresh process, with
  `SWISSARMYBENCH_INFO` naming a file that is not there, so the client finds no app and reads connections
  as an exported script does (client/standalone.py; branch one-script's exported script runs the same
  way); output kept to its last 256 KB, stopped after 30 minutes. **Run history:** memory only (a run's
  log may hold what the script printed), the last 50 runs of a script, Run file included (its log is not
  kept: it is in the console).
- **Data (data.ipynb):** Cells | Lineage | Dictionary. The Dictionary lists data.ipynb's tables, each
  column with its type in plain words (Whole number, Decimal, Text, Date, Date and time, True or false,
  List, Record...) and where it comes from (the table's source, or "Step 2" when that grid step made it,
  from the compiled view's stages). Descriptions are typed in place, kept in data.ipynb's metadata
  (`swissarmybench.dictionary`: they travel with the file and the zip), make the notebook unsaved, and
  are written into data.py as a comment block under its first lines (from the open data.ipynb, saved or
  not). **Lineage** (merged with the lineage branch, 2026-11-15): the overlay's own flow drawn in place
  (`openLineage(target, host, into)`), for data.ipynb's selected cell, else its last; a double-click on
  a node goes back to Cells at that cell; its place shows the word Lineage only while there is no
  cell. Properties shows a block's controller (role, makes with types and defaults, its contract's
  problems) and Lineage… opens the overlay.
- **The agent** (the golden rule): `app_kind_colours`, `streamlit_page_settings`, `streamlit_state`,
  `workbench_script_settings`, `workbench_script_run`, `workbench_script_history`, `project_dictionary`;
  and in the window `mode.panel`, `canvas.select`, `canvas.properties`, `canvas.settings`,
  `canvas.session`, `canvas.resetState`, `canvas.undo`, `canvas.redo`, `canvas.duplicate`, `canvas.align`,
  `canvas.zoom`, `canvas.preview`, `canvas.addStarter`, `data.starters`, `data.starterList`,
  `notebook.runOrder`, `notebook.outline`, `run.upToHere`, `notebook.present`, `script.runScheduled`,
  `script.history`, `data.view`, `dictionary.list`, `dictionary.describe`. The tool list's budget is
  59,000 characters.
- **Not built here** (other branches' or later): text cells' "Text and layout" starters and the "Pin to
  the bottom" footer option, live markdown on pages beyond what text cells already do, controllers and
  the contract check, lineage's own view, approved outputs. A Run file's log in the history.


## The tray icon, updates, and start at sign-in (the owner, 2026-11-16; built, branch tray-update)

The owner, after installing the 0.0.1 beta on Windows: "we should add a button that appears in the tray
saying an update is available and you can right click to update". Then: "Swiss Army Bench should start
itself then stay running when it's on the computer." The plan's tray (Plans/standalone-workspaces.plan.md,
the owner's spec of 2026-11-12) is built with what exists today: tables and Workbench documents stand in
for workspaces.

- **The tray** (`swissarmybench tray`, server/tray.py; pystray and Pillow, the plan's decision 6, in the
  `[server]` extra only): a left click opens `/workspace#token=…`; the right-click menu, as data in
  domain/updates.py (`tray_menu`): Update to X and What's new first when there is one, then Open, the
  open tables and the Workbench window's documents (a • for unsaved changes; read as the menu opens on
  Windows, every 5 seconds elsewhere), Open the Workbench, Open the blades page, Restart, Start with
  Windows (Open at login on macOS and Linux), Stop and quit. Stopped: Start (or, after the watchdog gave
  up, "Swiss Army Bench stopped: Restart"). The icon is the pages' mark drawn with Pillow; an update adds
  a blue dot and the tooltip "Update available: X". One tray at a time: the server's InstanceLock, named
  for tray.json (which holds its process id for the update's helper).
- **`swissarmybench start`** starts the tray as its own process (no window) unless `--no-tray`, VS Code
  started it, or `SWISSARMYBENCH_TRAY=0` (the tests, the smoke test); on Linux only with a display and
  pystray. A second `start` while one runs starts its tray if it has none.
- **The check** (services/updates.py, adapters/updates.py): PyPI's JSON, then GitHub's latest release,
  at start and every six hours; nothing but the GET (Python's own User-Agent, no query, no cookies); a
  pre-release offered only to someone on one; yanked releases and releases with no files never. PEP 440
  is implemented in the domain (standard library only; no `packaging` dependency). The switch, Settings'
  "Check for updates", is kept in update.json; off sends nothing; turned on asks at once.
  `SWISSARMYBENCH_UPDATE_FEED` names a stand-in (the tests) or "none" (the test suite, the smoke test).
- **Recorded in the posture**: CLAUDE.md's posture line and design principle 11.1 (the one request that
  leaves the computer, by the owner's call).
- **Update to X**: asks first only when a notebook has unsaved changes (the Workbench window's
  "documents" answer and the Streamlit registry's unsaved flag) or a kernel runs; saves nothing. The
  agent's (`app_update`) always waits for the user's Allow, through the existing approval prompt. The
  server writes the plan, copies server/updater.py (standard library only) to a temporary folder and
  starts it with the base Python, outside the tool's environment that uv replaces, detached (Windows:
  CREATE_NO_WINDOW, a new process group, out of the terminal's job when allowed), then stops. The
  helper waits for the server's and the tray's processes, runs `uv tool install --force --python <the
  running minor> "swissarmybench[server]==X"` (three tries: Windows can hold a just-ended program's
  files; "files in use" named in the note), checks the installed version, starts the app (its tray, its
  page). On a failure it writes update_failed.json and starts the old version, reinstalling it first if
  it no longer starts. **Decision:** when only GitHub answered, uv installs that release's wheel by its
  URL rather than asking PyPI for a version it may not have. **Decision:** a copy not installed by uv
  (no uv-receipt.toml) is refused in words, never half-updated.
  **Added on the navigation branch (2026-11-16, the coordinator):** on Windows an editor's MCP server
  running from the same uv tool folder locks its files too, so the plan names the tool's folder
  (`stop_in`, Windows only) and the helper, once the app's own processes are gone, stops every process
  whose program is inside it (PowerShell's process list with each program's path; never itself, which
  runs the base Python outside that folder), then installs. Not stopped: a `swissarmybench-mcp.exe`
  launcher in uv's bin folder (outside the tool's folder; its Python child inside is stopped, so it ends).
- **The status bars** (web/src/updates.ts): a quiet green "Update available" in the grid page's and the
  Workbench's status bars only while there is one (principle 7.9: never "up to date"); its menu has
  Update to X and What's new. "Update failed" (red) carries the reason. The `update_changed` and
  `app_updating` notices keep every window current. Palette commands: Update to X, What's new, Check for
  updates on and off.
- **Start at sign-in** (server/autostart.py; the owner: "start itself then stay running"): on by the
  installers, off with the tray's tick or `swissarmybench autostart off`. **Decision:** a Startup folder
  shortcut on Windows (not a Task Scheduler task: no registration, no admin, listed in Windows' Startup
  apps) to the tool's `pythonw.exe -m swissarmybench.server tray`; a LaunchAgent with RunAtLoad on macOS
  (KeepAlive only for a crashed tray, never after Stop and quit); an XDG autostart entry on Linux (not a
  systemd user service: a tray needs the desktop session). The tray starts the server when none runs.
- **Stays running**: a server started by hand, the tray or at sign-in never stops on its own. The tray
  tells a crash (its connection file left, its process gone) from a stop on purpose (the file removed),
  restarts a crashed server at most 3 times in 5 minutes, then says "Swiss Army Bench stopped: Restart".
  What it saw goes to server_events.json, which the next server writes into the beta log (process kind
  "server": crash, restart, failed) and removes.
- **`swissarmybench start --background`**: the server detached, no console, returning at once; the tray
  uses the same command line (`start --no-browser --no-tray`, detached, with the console Python beside a
  pythonw so CREATE_NO_WINDOW reaches its kernels).
- **The installers** turn on start at sign-in, start the app in the background and open its page once;
  `-NoAutostart -NoStart` / `--no-autostart --no-start`, `SWISSARMYBENCH_NO_AUTOSTART=1` and any `CI`
  skip them; the release workflow passes the flags and fails if `autostart status` is not off. The
  PowerShell 5.1 `Quiet` helper stays.
- **0.0.2's page address** pointed at `/`, which the guard answers with 401: `page_address` (now in
  server/lifecycle.py, shared by `open`, `start` and the tray) uses `/workspace`.
- **The agent** (the golden rule): `app_update_check` (now, on), `app_update`, `app_autostart`. The tray's
  menu route (`/updates/tray`) is plumbing (tests/test_cli.py NOT_COMMANDS).
- **Not built:** a menu item per workspace and New workspace (workspaces are not built); a Windows toast
  with buttons (pystray's notification is plain text).
- **The token out of sight, and bookmarks (the owner, 2026-11-16, "yes fold them in"):** the owner asked
  why the app needs a token to open. It stays (any website could otherwise call 127.0.0.1), but the user
  never sees or handles it. The pages already cleared `#token=` from the address bar (api.ts keeps it in
  the tab's session storage); now each page trades it once at `POST /session` for the `sab_<port>`
  cookie (HttpOnly, SameSite=Strict, Path=/, no Secure; its value a per-start secret in memory, never
  the token). The guard takes the cookie beside the Bearer token, only with the Host and Origin checks,
  and on POST, PUT, PATCH and DELETE only with our own Origin header; the websocket takes it too. A
  page with neither says "Open Swiss Army Bench from its tray icon, or run `swissarmybench open`." (the
  page's script for the page shells; the guard's plain page for any other address a browser asks for).
  Pop-out windows still get the token in their fragment; the Streamlit proxy keeps its path secret.
  Agents, the push client and VS Code keep the Bearer token. Found on the way: catalogPage.ts mounts
  beta mode inside the blade editor's `closed` callback (a stray indent from an earlier merge), so the
  blades page's Beta mark appears only after an editor closes; left as it was, reported.

## Navigation (the owner, 2026-11-16; built, branch navigation)

The owner, on the first real use of the beta: "I've noticed there is no navigation in the app to get
back to the home page or go back anywhere. No back buttons."

### The survey: every page and window, how it is reached and left (before this change)

| Place | Reached by | Left by | Where the user was stuck |
|---|---|---|---|
| `/workspace`, the home page: grid tabs, Sandbox, Diagram, the "+" query draft | the tray, `swissarmybench open`, a push | closing the browser tab | no mark at all; a tab switch left no trace in the address, so the browser's Back left the app (or did nothing), a reload lost the Sandbox or Diagram in front, and the title stayed "Grid" on the Sandbox |
| `/g/{id}` | a push's link | the same page as `/workspace` | its address never followed the tab in front: it kept naming the first grid |
| `/catalog`, the blades page: welcome, a table, a schema (a Power BI dataset), the blade editor, the template picker | Blades and catalog (Application row), Analyze's blades | closing the tab | no way home; every view one address, so Back left the app and a reload lost the table shown; no trail for Catalog > schema > table; the title always "Blades and catalog" |
| `/workbench` and its pop-out windows | the Workbench tab, the tray | closing the window | the mark was a picture, not a link; nothing brought the home window forward; the title read "sales.ipynb · Workbench" (the place last) |
| The steps window (`/g/{id}?panel=steps`) | Edit steps | closing the window | no mark, no way to the home window |
| The Key Finder window (`/g/{id}?panel=keys`) | the Table row | closing the window | no mark, no way to the home window |
| Settings (a dialog) | the Application row, the Workbench's "…" | Close, Escape | flat (no nested sections): only Back closing it was missing; a reload lost it |
| Connections: the list, Add connection's types, a type's form, Edit, Python (your own code), Add API, then the new connection's form | the Application row, the blades page, the Workbench | Close, a "Back" in the footer | the footer's Back did not say where it went; the browser's Back left the app with the dialog open; a reload lost the form; no trail for Connections > Add connection > PostgreSQL |
| The file chooser | Browse… in any form | Choose, Cancel | its folder walk has `..` and Go; the browser's Back left the app under it |
| Key Finder, Compare (key picker), Analyze's forms (odds, fit test, outliers, find predictors, regression, time series, forecast), tie-out, export, step forms, profiles, the Tables (Open) dialog, relationships and tangs, packs, imports | buttons and menus | Close, Escape | one task each (principle 4.4): their own setup and results on one screen, Compare's setup one click away again (the Compare row's Keys…). The only trap: the browser's Back (or a mouse's back button) left the page under an open dialog |
| The tour | the question mark | Skip, Start | has its own Back between cards; the browser's Back left the app under it |
| Error and empty states | | | "Could not open this grid" (a page that failed to start) and the steps window of a closed table offered nothing; the blades page's "Nothing matches." and the home page's "No grids open" are the places themselves |
| The signed-out page | a bookmark after a restart | | a dead end by design: there is no session to go home to; it says how to open the app |

### Built: one navigation model, everywhere (web/src/nav.ts)

- **The mark goes home.** Every page and window starts its top row with the mark (the red square and its
  cross, the tab's icon), a link to `/workspace` named and titled "Home". On the home page it is the
  grid view (closing what is open over it). In any other window it brings the home window to the front
  when one is open (first the window that opened this one, up the opener chain, so the agent's nav.home
  needs no pop-up; else `window.open("", "sab-home")`: the home page names its window `sab-home`) and
  opens it when not. **Decision:** with pop-ups blocked it says so; it never sends the window it is in
  home instead (a Workbench would lose its kernels). Alt+Home does the same everywhere. **Decision:** the mark carries no word: the product's
  name stays off the screens (principle 7.8); "Home" is its name and tooltip.
- **Views live in the address, and Back is the browser's.** `history.pushState` on each move the user
  makes; a move the app makes by itself (a closed tab, the draft built into a table, a page showing its
  address at load) replaces the entry instead, so Back never walks through things the user did not do.
  **Decision:** "made by the user" is the browser's own user activation (a click or a key in the last
  few seconds), so the many places that switch tabs did not each need a flag; a push that brings a table
  forward right after a click counts as the user's. One queue orders every history move, so a dialog
  closed (history.back) and another opened at once never lose an entry to each other. The token never enters
  the address (the cookie keeps the session, 0.0.4), so a reload keeps the view.
  - Home: `/g/{id}` for a table in front, `/workspace?view=sandbox`, `?view=diagram`, `?view=query`
    (the "+" draft: a reload brings back an empty draft).
  - Over it: `&open=settings`, `&open=connections` with `&at=types`, `&at=form&type=postgres`,
    `&at=edit&name=Warehouse`, `&at=api`. **Decision:** a saved form, and Add API's new connection,
    replace their entry (Back then goes to where the form was opened from, not to a form already done).
    **Decision:** a key vault made from a password's form (the form waits, kept) stays outside the
    address, with its own Back to that form.
  - The blades page: `/catalog?catalog=Warehouse&schema=sales&table=orders` (`&database=` when the
    catalog has several), `?catalog=…&schema=…` (a schema or a Power BI dataset), `?blade=<name>` (the
    editor), `?blade=` (a new blade's template picker). `?catalog=Warehouse` alone is a new, small page:
    the catalog's name and what it holds (schemas, tables, views, columns, its dialect), the trail's
    middle crumb. The editor with work in it keeps the browser's Back from throwing it away (the old
    "Save or cancel the blade first."); its own Back is its Cancel. An arrow key's walk through the tree
    replaces the entry (one entry where it stops); a click pushes.
  - **Every other dialog** pushes an entry with no new words in the address: Back closes the dialog on
    top, Forward does not bring it back (its work is gone). **Decision:** an agent's approval ("The
    agent is asking") is the one dialog Back does not close: it waits for Allow or Deny.
  - **Decision: the Workbench's documents are not in the address.** They are a session restored on
    reload already, with their own keys (Ctrl+Alt+Page Up and Down); a document per Back would fight the
    editor's own undo. Back there closes dialogs and moves inside Connections.
- **A visible Back (←)** where a view was entered from another, named for where it goes: "← Connections",
  "← Add connection", "← sales" (a table's schema), "← Warehouse", "← Blades". It goes back in the browser's history when that is where
  it came from, and to the named place otherwise (a bookmark of a form).
- **Breadcrumbs past one level**, each crumb a link: Connections › Add connection › PostgreSQL;
  Catalog › Warehouse › sales › orders.
- **Titles name the place, the page first:** the table's name on the home page ("orders"), "Sandbox",
  "Diagram", the draft's name; "Blades · Warehouse › sales › orders", "Blades · refresh_sales",
  "Blades · New blade"; "Workbench · sales.ipynb"; "Table Transformations · orders" (the steps window);
  "Key Finder · orders"; over the page: "Settings", "Connections › Add connection › PostgreSQL" (and
  "Workbench · Connections" in the Workbench). With nothing open the home page is "Home".
- **No dead ends:** "Could not open this grid" offers Home; a catalog address whose table is gone and an
  unknown blade say so, with "← Blades"; a Connections address whose connection is gone says so, with
  "← Connections"; a `/g/{id}` of a closed table shows the table in front and its address. The steps and
  Key Finder windows now have the mark (their table closed: the mark is the way out).
- **The agent** (the golden rule): `app_navigate` (to: home, back, forward, sandbox, diagram, query,
  settings, connections, add_connection, add_api, grid:<id>, catalog; window: home, catalog, workbench);
  the Workbench's `workbench_window` commands `nav.home`, `nav.back` and `nav.forward` (also in its
  palette). The server checks the place (domain/navigation.py) and that such a window is open (the
  blades page is now told apart on the socket), and writes the move to the audit log; the window does the
  move itself, as the user's would be done.
- **Not built:** Back between the Workbench's documents (above); the Key Finder window's results and
  Compare's key picker stay one screen each (Compare's setup is one click away again, the Compare row's
  Keys…); Forward onto a plain dialog's entry does nothing visible (its entry is turned into the page's).

## The rail: a slim icon navigation pane (the owner, 2026-11-16; built, branch nav-rail)

The owner, after 0.0.6's navigation: "As much as I hate to say it, this app needs a navigation pane
somehow." Asked which kind, the owner chose **a slim icon rail**: a narrow strip down the left of every
page and window, as VS Code's Activity Bar, an icon per area with its name on hover. Two corrections
the same day: "Data is just the tabbed datagrids and you should call it grids" (Data became Grids, and
the old Home entry, the same place, went); and "Shouldn't the app canvas be on the rail separate from
the workbench. We could split notebooks, scripts, and app canvas on the rail as well and give options to
open them in an external tab." And: "do we still get a cell navigator to help build the streamlit app
page?" (yes: below).

### Built (web/src/rail.ts, one module mounted by each page's composition)

- **The areas, top to bottom:** Grids (the home page's tabbed grids), Sandbox, Diagram, Notebooks,
  Scripts, Apps (the Streamlit canvas), Blades, Connections, and Settings pinned at the bottom. 48px wide,
  fixed at the left of the home page (`/workspace`, `/g/{id}`), the blades page, the Workbench and its
  pop-out windows, the steps window and the Key Finder window. The page moves right by its width
  (`body.has-rail`'s padding), so nothing sits under it; a window under 600px keeps it at 48px.
- **Icons:** our own line icons in the one set (dom.ts ICONS): a grid with its tab, the Sandbox's cards,
  two tables and their join, a blade, a plug, the cog. Notebooks, Scripts and Apps use their documents'
  own icons (notebook, code, page) in their kind colours (blue, green, violet: the theme's tokens or the
  colour chosen in Settings). No other text (principle 7.1): the name shows in a tip on hover **and on
  keyboard focus**; each item has its `aria-label`. **Decision:** no `title`: the tip already shows the
  name, and a `title` would show it a second time a moment later.
- **A rail click is a navigation like any other (nav.ts):** an area the page shows is pushed (Back,
  Forward and a reload work, and the mark follows them: `onAddress`); Connections and Settings open their
  layers (`open=<key>`) on the page you are on (the blades page now has Settings too); an area another
  window shows brings that window forward, or opens it: Grids, Sandbox and Diagram the home window
  (`sab-home`; told by a message from this origin which area to show), Notebooks, Scripts and Apps the
  Workbench window (code always opens in its own window, never the grid page), Blades the blades page
  (**decision:** plan decision 18 keeps it in a tab of its own, so the rail brings that tab forward
  rather than turning the home tab into the blades page). A window opened for an area is given it in
  its address (`?view=sandbox`, `?open=settings`, `/workbench?kind=script`). This window is never sent
  away from its work.
- **Notebooks, Scripts, Apps in the Workbench:** the kind's document in front (the one in front already,
  else the last opened of that kind), so the Workbench is in that kind's mode; none open: a menu beside
  the rail's item with New notebook (script, Streamlit app), that kind's recent files and Open…. The
  kind is in the address (`?kind=notebook`): a rail click pushes it, a tab click replaces it (the
  documents themselves stay out of the address, as 0.0.6 decided), so Back after a rail move brings the
  previous kind forward again. **Open in a new window** (the owner's "external tab"): right-click, a
  Ctrl+click (Cmd+click) or a middle click on any of the three, from any page: a Workbench window of its
  own for that kind, as a popped-out tab's window (`fresh`, `popped`); it opens at that kind's menu.
  **Decision:** it does not hand the document in front over (the tab's own "Move to a new window" does
  that); it is a new window for the kind.
- **Apps keeps the cell navigator.** Apps opens (or unfolds) the Data panel and its Streamlit cells pane
  beside the canvas: the rail, then the Data panel, then the canvas, side by side; the Starters switch
  stays. **Found and fixed:** the pane listed only the open documents' cells (and a project's files), so
  a canvas whose notebook was not open in a window showed "No cells call Streamlit" beside its own
  linked blocks (the App mode screenshot: "app mockups.ipynb" was not open). It now also lists every
  notebook and script an open canvas links to, read from its file as the canvas reads it, and a
  project's data.ipynb lists its named cells (the model a page reads) beside its Streamlit cells.
- **The current area** has a bar on its left edge (the accent; the kind colour for the code areas) and
  its icon at full strength, with `aria-current="page"`: Grids for the grids (and the steps and Key
  Finder windows, which are a grid's), the Sandbox and Diagram views, Settings or Connections while
  their layer is open, Blades on the blades page, the front document's kind in the Workbench.
- **Keys:** the rail is one Tab stop (`role="navigation"` "Areas" around a vertical toolbar): the arrows
  move between the areas (round at the ends), Home and End, Enter goes. Alt+Home is still the grids.
- **The mark stays** at the top-left of each page's top row and still goes home (Alt+Home).
  **Decision:** Grids is that same place, so from another window the mark now also brings the grids to
  the front there (closing what is over them), not only the window.
- **Settings' Agent activity list: removed (the owner, 2026-11-16):** "also remove the agent activity log
  from settings". The audit log itself stays (on disk, GET /audit); only the Settings list went.
- **Settings' Panels:** a switch, "Navigation rail" (Every page), on at every start like the others.
  Off: the rail is gone from every window at once and the page takes its width back; the grid, Monaco
  and the canvas measure again (a resize). **Removed (the owner, 2026-11-16):** "Looking at the screen
  shot, why are the sandbox diagram and workbench still at the top now that they are accessible from the
  rail", then "okay then remove the setting to remove from the rail". Built: the rail has no switch and
  is always there; the top tabs are only grids (the Sandbox, Diagram and Workbench tabs are gone); the
  Application row keeps the project's group, Tour and Zoom (Settings, Connections and Blades and catalog
  are the rail's); the tour points at the rail. The palette's "Go to Sandbox", "Go to Diagram" and "Open
  the Workbench" and the agent's app_navigate are unchanged.
- **The agent (the golden rule):** `app_navigate` takes every rail area from every window (`grids` and
  `home` are the same place), and `new_window: true` for notebooks, scripts and apps. The rail's switch
  is a panel, so `app_panels` covers it.
- **Not built:** a document list inside the rail (the menu shows recent files only when no document of
  the kind is open); the rail's order is fixed.

## Icons: a glow-up (the owner, 2026-11-16; built, branch nav-rail)

The owner: "And it needs a glow up with icons. For example our connection panel has no icons on the
connection types."

### Built

- **One set** (web/src/dom.ts `ICONS`), our own line icons, now about 140. **Decision:** the set stays
  in dom.ts (a `web/src/icons.ts` would only move it); shared parts (a database's cylinder, a file's
  sheet, a lock, a cloud) are named constants above it.
- **Connections:** every type the server offers has an icon of its own, named by the type's id
  (`postgres`, `excel`, `azure_key_vault`, ...; `connectionIcon` in connectionsWindow.ts, falling back
  to the group's): each database the cylinder with its own mark (a server rack for SQL Server, a cloud
  for Azure SQL, a snowflake, a magnifier for BigQuery, a feather for SQLite, a duck for DuckDB, bars for
  ClickHouse, ...; no two alike), Power BI its bars, files their sheet, grid, columns, braces or folder,
  Python a prompt, each vault its lock, shield, cloud or triangle. **No brand logos** (trademarks, and
  nothing loads from the network). The type tiles are a picker: the icon beside the name, tinted by the
  group (the theme's category tokens: databases blue, files green, vaults magenta, Python violet; never amber),
  a hover that takes the group's colour, a clear focus ring. The saved connections list: each row its
  type's icon in a soft square. Add API: OpenAPI and Endpoints have theirs, and the preset its own
  beside its box (Azure Function App, AWS Lambda, Google).
- **The sweep:** the catalog tree's nodes (a schema, a table, a view; a column by its kind of value:
  number, text, date, true/false), the blades list (a connection its type's icon, a blade its kind's),
  the starter pack's families (Power BI, Excel, Files, DAX, HTML, Markdown, Streamlit, Controllers, Text
  and layout, Components) and a snippet's language, the Data panel's tables by their file's kind, the
  Sandbox's card kinds beside each title, Settings' sections (every legend), and the home page's
  Sandbox and Diagram tabs now wear the rail's icons for them. Menus already had icons on every entry
  (Analyze, the right-click menus); empty states kept their words.
- **Checked by tests/test_icons.py:** every type the server offers and every Add API preset has its own
  icon in the set, no two alike; every icon name the page asks for by name exists (none drawn blank).
- **Merge note:** the `dataverse` branch adds one type with the icon name `dataverse` to the same set;
  `connectionIcon` picks it up by the type's id.

## Dataverse: a connection type (the owner, 2026-11-16; built, branch dataverse)

The owner: "Add Dataverse to 0.0.7". Before this, on 2026-11-15, Dataverse was parked with Power Apps
(above); the note kept there said it "reads through its read-only TDS endpoint (SQL Server style) and
writes through the Web API, signed in with the vault's app registration as Power BI is". It is now a
connection on its own, without Power Apps. Reading only; writing is later.

Built (domain/dataverse.py, its starter in server/blade_templates.py, tests/dataverse_standin.py):
- **The form:** Dataverse, under Databases, with its own icon. The environment's Address
  (`https://your-org.crm.dynamics.com`) and Sign in: **As you** (azure-identity's
  DefaultAzureCredential with the browser allowed: the Azure command line's sign-in, else a browser
  window; in Azure, the app's managed identity), **Managed identity** (for an Azure Function, by
  Azure's own local request: no package), **An app registration** (tenant id and client id typed, the
  client secret a key vault's entry). Test before saving: it signs in (WhoAmI), counts the tables and
  shows the first rows of `account` (or the first table).
- **The catalog:** the Web API's metadata (`EntityDefinitions`, `$filter=IsPrivate eq false`, with their
  `Attributes` expanded), loaded in the background as other catalogs are: one schema (dbo, as the SQL
  endpoint names its tables), each table by its logical name with its display name, each column with
  Dataverse's type (String, Money, Lookup, Picklist...) and its display name.
- **Reading a table** (Open as grid, the preview, `sab.read`, the catalog's first line, Test): the Web
  API's OData (`$select`, `$filter`, `$orderby`, `$top`, `$count`, paging by `@odata.nextLink` with
  `Prefer: odata.maxpagesize`) and the formatted values annotation. No admin setting is needed.
  `conn.read(table, columns=, filter=, order_by=, limit=)`, `conn.rows` (with the count),
  `conn.fetch(fetch_xml)`, `conn.tables()`, `conn.columns(table)`, `conn.get(path)` for anything else.
- **SQL:** `%%sql <connection>` and `sab.sql` on the read-only SQL endpoint (TDS,
  `<org>.crm.dynamics.com,5558`) through pyodbc and ODBC Driver 18, signed in with the same Entra token
  (SQL_COPT_SS_ACCESS_TOKEN). An environment with the endpoint off: the cell says so in plain words
  (an admin turns on "Enable TDS endpoint" in the Power Platform admin center) and the error panel
  offers a cell that reads the table instead (`account = sab.read("Sales CRM", "account")`; a fix of a
  new kind, `cell`; in a script it is copied).
- **Export as one Python script:** the connection inlined as its own code, like Power BI's; a managed
  identity signs in inside an Azure Function, As you too (DefaultAzureCredential uses the managed
  identity there). pyodbc is required only when a SQL cell runs on it.
- **The starter pack:** a Dataverse family: "Dataverse FetchXML query" and "Dataverse choice options"
  (a choice column's numbers and labels), each through the connection's own sign-in.
- **The agent:** no new command: `connections_types`, `connections_test`, `connections_create`,
  `connections_load_catalog`, `catalog_*`, `connections_open_table` and `connections_preview_table`
  already reach it; the index and the connections guide name it.

Decisions:
- **It is a database connection** (kind sql, dialect `dataverse`) whose `conn` also reads by itself:
  the app opens its tables through `conn.rows` (READ), never through SQL, so Open as grid works where
  the SQL endpoint is off. Its dialect quotes as T-SQL and names a table alone (`[account]`): the
  endpoint has the one schema.
- **The client secret is a key vault's only** (the owner's rule): the form offers a key vault or an
  environment variable, never "Saved on this computer"; the server refuses a typed secret on Test, Save
  and `blades_secrets`. The ids are typed (they are not secrets).
- **A choice column reads as its labels** (Picklist, State, Status, multi-select); **a Yes/No column
  stays true or false**; a lookup keeps its id under its own name, and its name column
  (`primarycontactidname`, as the SQL endpoint has it) holds the formatted value. Money, numbers and
  dates read as themselves, never the formatted text Dataverse also sends.
- **Counts:** `$count` says up to 5,000; past that, Dataverse's own RetrieveTotalRecordCount (a snapshot)
  gives the total for a whole table; a filtered read past 5,000 has none.
- **The token never leaves the environment:** a next page outside its address is not followed; plain
  http only to 127.0.0.1 (the stand-in).
- **Display names in the catalog:** a catalog row with a table but no column, and a description, is that
  table's name for people (adapters/catalogs.py `titles`); the tree shows it beside the table only when
  it says more than the name (User for systemuser; not Account for account).
- Not built: writing (the Web API's POST and PATCH), FetchXML paging past its first page, the catalog
  read per table for very large environments (one request with every table's columns).

## Projects as one .sab file (the owner, 2026-11-16; built, branch sab-projects)

The owner: "We should work on a proprietary format for projects where they can be saved in a .sab file
and this file can be opened from any session to get back to project you are working on. The home page
should show recent projects and have a open option for projects."

The owner's two choices, asked and answered:
1. **"One file holds it all":** a .sab is a single file (a zip inside, like .docx or .pbix) holding the
   notebooks, scripts and app canvases, the open grids with their steps, the Sandbox, the relationships
   and the window layout. While open it is unpacked to a working folder; Save writes back into the .sab.
2. **"Rows only on a tick":** each table keeps where it came from and its steps, and is read again on
   open. A pasted or pushed table has no source, so Save as offers "Keep its rows in the file" per table,
   off by default.

### Built
- **The format** (domain/sab_files.py): `project.json` (format 1, the app version, the name, the tables
  with their sources and every grid's steps, the home page's tabs, the Workbench's documents and groups,
  the diagram), the project's own files at their paths, `sandbox/sandbox.json`, `model.tang`, and
  `data/<table>.parquet` only for ticked tables. A source is a connection with its database, schema and
  table (by name, never a password), a file (relative to the .sab when it sits beside it, its old full
  path kept as a second place to look), the project notebook whose kernel sent it, a "+" tab's query, or
  pasted/pushed with `rows`. Fields this version does not know are kept when the file is saved again
  (the manifest's, a table's, a source's, a grid's). A newer format opens read-only, in plain words.
- **Safety** (adapters/sab_files.py): every entry is checked before anything is written (no `..`, no
  absolute path or drive, no link, no name twice, counts and sizes capped in settings.py), and each one is
  counted again as it is read, so a zip that lies about its sizes stops. The save writes a temporary file
  beside the target, then one replace.
- **Open** (services/sab_projects.py): the project's files into a working folder of its own in the
  system's temporary folder (removed on close and when the server stops); each table read again (queries
  last, they read the others), its steps applied as where it starts (no undo entry); the Sandbox, the
  model and the layout as they were. Nothing runs code on open: a notebook-made table says "Open
  data.ipynb", and its steps wait for it (they apply when it arrives, by any way). A table that cannot
  come back gets a state and one click: Add connection Warehouse (then Try again), Find orders.csv, Open
  data.ipynb, Remove. Never a dead end.
- **Unsaved changes are worked out, not tracked:** what a save would write (tables, sources, steps, the
  Sandbox, the model, the working folder's files) against what the last save or open wrote, plus the
  Workbench's unsaved documents (it reports them). Opening or starting another project asks only then;
  loose tables (no project open) count as unsaved work. New project takes the open loose tables into its
  data.ipynb (their pasted rows never written out in a cell).
- **Save:** the Workbench's project documents are saved first (the server asks the window,
  `project.saveDocuments`); notebooks go in without their outputs and a pasted table's rows written in a
  cell are taken out (rows go in only as ticked Parquet). The Sandbox goes in without what its charts
  and query tables showed (they redraw on their tables); a table card sent with its own rows keeps them,
  and counts as rows for the agent's Allow. The first save of a project made in the app asks where.
- **The home page:** a Start view (`/workspace?view=start`, in the address, so Back and a reload keep it):
  New project, Open project… (the file chooser, .sab), the recent projects (name, folder, when; a missing
  one is marked, with Remove from the list), the recent notebooks and scripts beneath (each opens in the
  Workbench window). It shows when nothing is open and when the last table closes; Home (the mark,
  Alt+Home, the agent's nav home) brings it back. The project's group sits first in the Application row
  (its name, ● with unsaved changes, Save, Save as…, Close); Ctrl+S saves; tables to fix sit in a strip
  under the tabs, only while there are some.
- **The Workbench:** the project's name and ● in its top row (its menu: Save project as…, Close project,
  Open project file…); Save covers the project when the document in front is one of its own; a folder
  project's **Save as .sab…**; it opens a project's documents and groups as saved, and closes them when
  the project closes. Opening or starting a project from the Start view opens the Workbench window.
- **Opening from anywhere:** `swissarmybench open sales.sab` starts the app in the background when it is
  not running, opens the project (the page asks first when unsaved work would be lost) and shows the
  home window when none is open. The installers register .sab: Windows for the current user only
  (HKCU\Software\Classes, `SwissArmyBench.Project`, the package's `server/sab-file.ico`,
  `"swissarmybench.exe" open "%1"`), Linux desktops as an XDG MIME type, icon and desktop entry. macOS:
  not registered (it needs an app bundle); `swissarmybench open` works there.
- **The golden rule:** `project_open`, `project_save` (keep_rows), `project_save_as` (a folder project
  too), `project_recent` (and remove), `project_new` (no folder: a .sab project; a folder: as before),
  `project_close`, `project_table_fix`; the guide's new topic `projects`. The agent's save asks the
  user's Allow only when it keeps rows.

### Decisions
- **Home is the Start view** (the mark, Alt+Home, the agent's `app_navigate` home); the rail's **Grids**
  (merged from nav-rail) shows the grids, an area of its own (`app_navigate` grids is no longer home).
  On the Start view the rail marks no area.
- One project open at a time; opening one closes the open tables, Sandbox and model (after asking when
  they hold unsaved work).
- The Sandbox's saved dashboards stay the user's own (in the state folder); the .sab holds the Sandbox
  as it is. (Superseded the same day by Project scope, below: the saved dashboards are the project's.)
- The project's name is its file's name (Power BI's way); Save as renames it.
- Data files beside a project (CSV, Excel, Parquet, JSON) are never packed: their tables keep the path.
- The diagram is drawn from the model (no positions to keep yet): `diagram` is an empty object for now.
- A double-click shows a console window for a moment on Windows (uv's launcher is a console program).
- `swissarmybench uninstall` does not exist, so nothing removes the association yet.

## Project scope: everything is the project's own (the owner, 2026-11-16; built, branch project-scope)

The owner, in order:
1. "start a new project opened the workbench. The first thing it should do is have the user save a
   project file to the machine and ask about autosave with a button to turn it on and off. When the
   project is created the first step is to get data into the app, so we start in grids"
2. "new here take a tour should be on the project page and no where else"
3. "now objects are project scoped any notebooks scripts of apps will have to be imported from another
   project"
4. On connections and blades in a project (the reading given to the owner, who said "go ahead and build
   it all"): each project holds its own connection and blade definitions in the .sab, so a project
   opened on another computer brings them; passwords stay with each computer (environment, keyring or
   vault) and a .sab never holds one; on a new computer the user is asked once for the password or where
   it comes from. Import copies a connection or blade from another project, or from the connections
   already saved on this computer.
5. "Grids" with no table open lands on a Grids page: the ways to bring data in and the project's tables.

### Built
- **New project is saved first** (services/sab_projects.py `new`): the file chooser in save mode (name
  and folder), `POST /project/new {"path"}` writes the .sab at once (refused without a path, or when its
  folder is not there: a project is never without its file), then **Autosave**, a switch, then the
  project's **Grids**. The open loose tables go into it with their connections, copied in from this
  computer's (and the vaults their passwords come from).
- **Autosave** (`POST /project/autosave {"on"}`, `project_autosave`): kept in project.json at once (only
  project.json is rewritten: the switch saves nothing else); on, the server looks every couple of seconds
  (`Settings.autosave_seconds`) and saves quietly once what a save would write has stayed the same for
  one look; the ● clears by itself. A failed quiet save is said in the project's state (`autosave_error`,
  the switch's tip). The switch sits in the project's group of the Application row.
- **The Grids landing** (startView.ts, `/workspace?view=grids`): with a project open and no table, Open
  a file…, Paste, Query, the project's connections (each opens its catalog), Catalog, Add connection, and
  the project's tables that did not come back, each with its fix. No project: the Start page. Closing the
  last table brings the landing (or the Start page with no project).
- **The tour** is on the Start page only: the Application row lost its Tour button; the Workbench and the
  blades page never had one.
- **Notebooks, scripts and apps are the project's** (services/project_scope.py): `GET
  /project/documents?kind=` (`project_documents`) lists them; the Workbench's Recent… is **In this
  project…**, its Open… copies a file from outside the project in (an import) and opens the copy; its
  **Import…** takes notebooks, scripts and apps from another .sab, a project folder or a loose file. The
  Start page's recent notebooks and scripts are gone.
- **Connections, blades and dashboards are the project's**: kept in its working folder's `.sab/blades`
  (the blade store's own JSON: code, names, where each password comes from, never a value) and
  `.sab/dashboards`, and so inside the .sab. Each open, new and close points the blade store and the
  dashboards at the project (`use_project` in bootstrap.py); the catalogs follow (a connection the new
  project lacks loses its catalog, its own load as at start). A second project sees none of the first's.
- **Passwords stay with each computer**, found by the connection's name: its keyring, an environment
  variable, a vault (the project's own), a secret blade. None of those here: the connection's
  `needs_password` (`GET /connections`) says which, with **Set the password** (its Edit form), and a table
  from it waits with "Shop needs a password on this computer" · Set the password · Try again.
- **Import** (`POST /project/import/sources`, `POST /project/import`, `project_import(source, list?)`):
  from another .sab (its entries checked as on open), a project folder, a loose file, or **This computer**
  (the saved connections and blades in ~/.swissarmybench/blades, as before projects held their own). A
  document whose name the project has takes the next free one (analysis 2.ipynb); a connection or blade
  whose name it has is skipped and said. The dialog (projectImport.ts) is the same in the Workbench, the
  Connections layer (Import…) and the blades page (Import from a project).

### Decisions
- **The rail with no project open stays as it is.** The home page shows the Start page and nothing else
  of a project; but `sab.push` from Python lands a table with no project open (the product's first
  promise), so the rail's areas keep working for that loose work, on this computer's own connections and
  blades. Saving it (Ctrl+S) makes it a project. The Workbench's Notebooks, Scripts and Apps pages (the
  rail-pages branch) should say "Open a project" when `GET /project/documents` answers `project: null`.
- **With no project open the stores are this computer's** (the blade store at ~/.swissarmybench/blades,
  dashboards in the state folder), so the agent and a pushing Python session work as before; with one
  open they are the project's. "This computer's" is also where Import's This computer reads.
- A project's removal or rename of a connection leaves its password in the keyring: another project
  may use the same name.
- The tang library (shared relationships) stays shared: tangs are made to travel between projects, like
  packs and blade folders, which also stay this computer's read-only libraries in every project. Themes
  and the kind colours stay this computer's.
- Opening a project lands on its Grids too (the Workbench window is no longer opened for it): its
  documents come back when the Workbench opens.
- Settings has no Autosave switch of its own here (the rail-pages branch redraws Settings); the
  project's group has it, and `project_autosave` is the agent's.
- A Streamlit canvas imported alone keeps its links as they were (relative to its file): import the
  notebooks its blocks link to with it.
## Every rail icon lands on a page (the owner, 2026-11-16; built, branch rail-pages)

The owner, the same day as the rail:
1. "the rail icons is opening a new tab every time instead of navigating the current page, the open in
   new tab is optional" (a rail click moves this tab; Ctrl+click, a middle click and the right-click's
   Open in a new window open another);
2. "every time I click the rail it pops out a box from the icon to create something get rid of that its
   duplicated behavior we should only create things from the panel";
3. "connection rail icon should open a connections page where all the active connections are presented
   as cards and I can click one to see all the references in the workbench that use that connection and
   an overview of its configuration and how many times it has been called this session";
4. "the same for others clicking the rail should land on a page not open a form".

### Built
- **A rail icon is a page.** Grids, Sandbox, Diagram and Blades were pages already. Notebooks, Scripts
  and Apps land on their kind's page in the Workbench; Connections and Settings are pages of their own
  (web/src/areaPage.ts) over whichever page you are on, the whole width right of the rail. No area opens a
  dialog or a menu any more; the right-click's one item, Open in a new window, stays (it is asked for).
- **The Workbench's landing page for a kind** (web/src/workbenchLanding.ts, `?kind=notebook&view=list`):
  its documents as cards, the ones open in this window first (the one in front marked, ● when unsaved,
  "Open"), then the others (today the recent files of that kind; `projectDocuments` is the one seam
  project-scope's list replaces). Its own panel has New (notebook, script, Streamlit app) and Open….
  A card's click is a move (pushed): Back comes back to the cards. An app chosen there (or New Streamlit
  app) still unfolds the Data panel's Streamlit cells beside the canvas.
- **The Connections page** (`open=connections`, the address the dialog had): a card per connection,
  grouped (databases, files, your own code, key vaults): its type's icon, name, type, a status word and
  its calls this session ("3 calls · 2 min ago"); Add connection and Add API in its heading row. A card
  opens its **detail** (`at=detail&name=`): Used in (each notebook or script cell, canvas block and open
  grid that uses it; a click opens that cell in the Workbench: this window's when the page is the
  Workbench, else the Workbench window, opened at the cell when there is none), Configuration (type,
  description, sign-in, its settings, each password's source by kind and name, the vault's entries, the
  name in code), Calls this session (catalog loads, queries, table reads, tests, connects, the last use);
  Open as grid, Edit, Test, Refresh catalog, Copy for Python, Remove. Edit's Back returns to the detail,
  Save shows it again. The forms (connectionsWindow.ts, addApi.ts, pythonConnectionForm.ts) open in the
  page as they did in the dialog.
- **References** (domain/connection_usage.py): `%%sql Warehouse`, `%%dax Finance/Sales model`, and in
  Python the client's calls `sab.sql`, `sab.dax`, `sab.read`, `sab.blade`, `sab.connection` (any alias of
  the module, and a function imported by name) with the name as their first argument, read with ast: a
  comment or a name inside another string is no use. A table's read-only cell whose load names it is
  marked "Table cell". A canvas block is a use when the cell it links to is one. Open grids read from it
  (their origin) are listed too.
- **Calls** (services/connection_usage.py, memory only): every run of a connection the app makes (a
  catalog load, a table read, a query, a test: the one place the server runs a connection's code,
  bootstrap's run_blade) and a Workbench kernel's report (client/connection_use.py: `%%sql`/`sab.sql`/
  `%%dax`/`sab.dax` a query, `sab.read` a read, `sab.blade`/`sab.connection` a connect), a fire-and-forget
  POST /connections/{name}/used from a daemon thread, carrying only the name and the kind.
- **Status, a cheap check (never a run):** Failing (its last call failed, or its catalog did not load),
  Needs a password (one is in none of its places: the keyring, a vault that maps it or loads every secret,
  this computer's environment), Works (its last call worked), Ready (not used yet).
- **Settings is a page** (`open=settings`), its sections side by side as the width allows; no Close (the
  rail or Back leaves).
- **The agent (the golden rule):** `connections_overview` (the cards) and `connections_usage` (a card's
  detail); `app_navigate(to="connection:<name>")` shows the detail; the Workbench window's `file.openCell`
  opens a reference's cell. The index and the guide's connections and grids topics say so.

### Decisions
- **The landing page, not the last document:** a rail click on Notebooks shows that kind's page even when
  a notebook is open; the open ones are its first cards, one click away, and Back returns from a card. A
  tab click or a document opened any other way (Open…, the agent, a reference) takes the page away.
- **The addresses stay the layers' (`open=settings`, `open=connections&at=...`)** rather than new
  `view=` words: every old address, bookmark and the agent's places land on the pages unchanged, and the
  page under them keeps its own view (a grid, a document). One page at a time: opening one makes the other
  go (Back brings it again).
- **The Connections page in the Workbench and the blades page too,** over the page, so a kernel or an
  editor is never left to reach it.
- **Status needs no sign-in check:** a browser-window sign-in (Power BI, MFA) cannot be known without
  running it, so such a connection reads Ready until its first call.
- **Not counted:** code in the user's own Jupyter or terminal (no SWISSARMYBENCH_KERNEL there); a vault's
  own runs.
- **Seams with project-scope:** references are looked for in the Workbench's recent files, the documents
  open in a Workbench window and the open project's files (bootstrap.usage_documents); the landing page's
  other documents come from `projectDocuments` (workbenchLanding.ts). Each is one function to swap for the
  project's documents list.
- **Not built:** references in unsaved edits of an open document (its saved file is read); a count of
  the calls each reference made.

## The Sandbox is Visualizations, the Diagram is the ERD (the owner, 2026-11-16; built, branch renames)

The owner:
1. "the Sandbox page title should be Visualizations now. rename all Sandbox refs to Visualizations"
2. "Relationship should jsut be ERD": the rail's Diagram and its page title ("Relationship diagram")
   are "ERD", with the tour and the help. "Relationships" stays for the things on that page (Find
   relationships, Import relationships, Manage relationships): they are the joins themselves.

(Earlier sections of this file keep the old words: they are the history as it was decided.)

### Built
- **Every Sandbox the user sees is Visualizations:** the rail's item and tip, the page's heading and
  title ("Analysis Sandbox" too), the status bar, the palette's Go to Visualizations, every Send to
  Visualizations (results, a cell's and a header's right-click, profiles, the value viewer, the Key
  Finder, cheat sheets, the Workbench's pictures), the toasts ("In Visualizations: …", "Sent to
  Visualizations"), the theme picker (Visualizations theme), the dashboards' confirm, the markdown export's
  heading, the tour, the user guide, SKILL.md, README, CLAUDE.md, design principles, the agent's index and
  guide. A card from before badged "Sandbox" is badged Visualizations.
- **The Diagram is the ERD:** the rail's item and tip, the page's heading and title (was "Relationship
  diagram"), the status bar, the palette's Go to ERD, a new tour stop (ERD, after Visualizations: twenty
  words now), the help. Design principle 7.4's example changed: ERD is a name the owner asked for.
- **Under the hood:** the agent's `sandbox_*` commands are `visualizations_*` (twelve); the area is
  `visualizations`; `sab.visualizations(...)` (client/visualizations_client.py, was sandbox_client.py);
  `?view=visualizations` and `?view=erd`; app_navigate's `visualizations` and `erd`; app_snapshot's area
  `visualizations`; the theme routes `/visualizations/themes` and `/visualizations/theme` (the page and
  the server ship together, so no old route is kept); a .sab writes `visualizations/visualizations.json`
  under the manifest key `visualizations`.
- **The old names, one release** (as SwissArmyGrid's): `sab.sandbox` (a DeprecationWarning, not in
  `__all__`); every `sandbox_*` command (cli/commands.py OLD_NAMES, `current_name`): run by `sab` and by
  an MCP call by name (the tool manager's lookup resolves it), never listed, so the tool list is the same
  size; app_navigate `sandbox` and `diagram` (domain/navigation.py SAME); app_snapshot `sandbox`; the
  addresses `?view=sandbox` and `?view=diagram` (land, then the address is replaced with the new word, and
  the rail marks the area); a .sab's `sandbox` key and `sandbox/sandbox.json` entry (read; the next save
  writes the new ones). Dashboards had no Sandbox name in their files: nothing to read twice.

### Decisions
- Internal names stayed where renaming buys nothing: aiPanel.ts, sandboxThemes.ts, sandboxDashboards.ts,
  sandboxPages.ts, sandboxExport.ts, sandboxShow.ts, the `agent` view key, CSS classes (`.sandbox-title`),
  the rail icon's id, test file names (test_sandbox*.py), the .sab layout's `diagram` window key. The TS
  identifiers (SandboxCard, profileToSandbox) too: only words a user or an agent reads changed.
- The old command names are aliases at the dispatcher, not listed tools: twelve more tools would add
  about 3,000 characters to every agent's tool list for names no new agent should use.
- "Visualizations" reads as a page's name, singular: "Visualizations is empty", "In Visualizations: a
  note and its chart".

## The Workbench, the owner's feedback (the owner, 2026-11-16; built, branch workbench-feedback)

The owner, with two screenshots (the Scripts page; data.ipynb open): "new script and open should be in
the bar above along with the save and save as. Also Shouldnt cell 1 have the table inside of it? and the
cell should horizontally autoscale. Also I think we need to differentiate with seperate icons the data
notebook vs the app notebooks. The first thing I did was go to scripts thinking that is where I could see
the transformations."

### Built
- **New and Open… in the top bar**, after Save and Save as… (Save as… now wears the save icon, so the
  folder is Open…'s). New is the kind on show: the landing page's, else the document in front's (a data
  or app notebook makes a notebook), else the address's, else a notebook. The landing pages lost their
  left panel: a heading and the cards only. New from a landing pushes the move (Back returns there).
- **A table's cell shows its table.** A notebook's Tables group and each table open unfolded (each table
  once: a fold the user makes stays). A table's cell the app wrote whole (no cell of the user's makes the
  table: its load and its transformations, as in a project's data.ipynb) runs by itself once on opening,
  starting the kernel, quietly (no unsaved mark); `%%sab_table` now returns the table, so the cell shows
  it as any cell ending in a DataFrame does. Its output is never saved (it is drawn again on opening, and
  data.ipynb keeps no rows); Open as grid is not offered on it (the grid has it). A new project's
  data.ipynb already starts with the tables' cells and no empty cell of the user's.
- **Cells fill the pane:** the 1,100-pixel cap went; 24 pixels each side. Table outputs scroll sideways
  in their frame. (A table's cell also lost the empty design pane it drew below its code: the "two faces"
  rule hid it for `.wb-cell` only.)
- **Three notebook icons** (dom.ts): `notebook`, `dataNotebook` (its corner a small table) and
  `appNotebook` (its corner a small app page), in the tabs, the landing cards, the Data panel's files and
  the Connections page's references (kindColours.ts kindIcon, notebookRole). An app's notebook: one an
  open canvas places a block of, or one a project's .stapp.json links (`/project/documents` gives each
  notebook's `role`: data, app or ""; domain/project_scope.py notebook_roles). Kind colours unchanged.
- **Transformations on the Scripts and Notebooks pages:** above the documents, a card per open table
  ("orchard_q · 2 steps", each step in plain words from the server's `step_words`); a click opens the
  table's read-only cell in the document that holds it (data.ipynb opened in a project when it is not),
  unfolded and in view. With no document for it, the grid's steps window. The agent:
  `workbench_window("tables.transformations", {"table": ...})`.

### Decisions
- A card opens the read-only cell, not the steps window: the user is in the Workbench looking for code,
  and the cell is the transformations as code, with the steps in its comments; the steps window is the
  fallback when no document holds the table.
- Only the app's own cells run by themselves. A table made by the user's cell waits for Run: their code
  never runs unasked (it may read a database, take minutes, or change things).
- No maximum width: code and tables both use the room; a reader who wants narrower splits the group.
- A landing in the address keeps its kind while documents come back under it after a reload (the old
  code let a restored notebook turn the Scripts page into the Notebooks page).

## Data notebooks and app notebooks (the owner, 2026-11-16; built, branch notebook-kinds)

"also I didnt see that data notebooks and app notebooks had been seperated in the app yet. the data panel
is nice but it should only show on app notebooks its useless in a data notebook"

### Built
- **Two kinds in a project:** data.ipynb at the project's top is THE data notebook; every other notebook
  in the project is an **app notebook**, whether a canvas uses it yet or not. Outside a project a notebook
  is plain. The rule: domain/project_scope.py `notebook_roles` (the documents list's `role`) and
  `notebook_kind` (a whole path and the open project's folder); the page's mirror is kindColours.ts
  `notebookRole` (setProjectFolder, from the Workbench's open project, folder or .sab), with
  `notebookWord` for the word.
- **Each kind its icon and word:** the tab kinds `dataNotebook` (was `data`), `appNotebook`, `notebook`;
  a tab's icon carries the word as its tooltip and the tab's tooltip starts with it ("App notebook:
  /…/views.ipynb"); the landing cards' and the Data panel's files' icons too.
- **The Notebooks page** groups its cards under **Data notebook** and **App notebooks** (and
  **Notebooks** for one open from outside the project), after the Transformations. In a project the
  top bar's New is **New app notebook** (the "…" and "+" menus too); an untitled notebook made while a
  project is open is an app notebook (its tab says so before it is saved).
- **The Data panel** is not there beside the data notebook (hidden, its flyout closed, its fold kept);
  it is beside app notebooks, canvases, scripts, plain notebooks and the landing pages. Beside the data
  notebook the "…" menu does not offer Collapse/Expand the Data panel and `view.toggleSidebar` (Ctrl+B)
  is refused with "the Data panel is not beside the data notebook". The agent: "documents" gives each
  notebook's `role` and `panes.data_panel` "away".

### Decisions
- **Kind colours stay three** (app violet, notebook blue, script green): both notebook kinds are
  notebooks; the icon and the word tell them apart, and a fourth colour would crowd the tabs.
- **data.ipynb outside a project stays the data notebook:** its Data mode (Cells | Lineage | Dictionary)
  goes by the name already, so its icon and panel follow the same rule. A data.ipynb in a subfolder of a
  project is an app notebook (one data notebook per project).
- **A canvas's link (relative to its app's file) in a project** is an app notebook (or the data notebook
  by its name): the app is the project's. Outside a project a canvas no longer makes a notebook an app
  notebook (the 0.0.11 rule); the brief's "outside a project, plain".
- **Scripts keep the Data panel:** their Tables region uses the tables, and a script feeds an app too.
- The documents list no longer reads the project's apps to find roles (the rule needs only the path).
- Not changed: the Connections page's references (it does not know the open project: a data.ipynb shows
  the data icon, any other notebook the plain one).

## Launch Claude: Claude Code or Claude Desktop, with the context (the owner, 2026-11-16; built, branch launch-claude)

The owner: "can you put a launch claude command on the home page in the bottom footer use a claude icon,
when its clicked it should start a claude code cli session in the proper folder so the claude agent
inherits the context it needs to understand SAB"; then "with a setting in the settings go launch it with
bypass permissions"; then "write a launcher that checks the machine for the installed claude desktop app
and launch it the same way. alot of the users will have a 3p claude install so dynamically finding it
will be th ekey".

Not the in-page terminal (Plans/agent-terminal-and-context.plan.md's T1, removed 2026-11-01, stays
removed): a button that opens the user's OWN terminal application, or Claude Desktop.

- **The button** (web/src/claudeLaunch.ts): "Launch Claude" with our own sparkle line icon (dom.ts
  `claude`: eight rays round an open centre; never Anthropic's logo, principle 7.11) in the home page's
  status bar and the Workbench's; Launch Claude, Launch Claude Code in a terminal and Launch Claude
  Desktop in both palettes. One Claude found: straight to it. Both: a small menu (Claude Code in a
  terminal, Claude Desktop). None: "Claude is not installed", each kind's official install commands
  with Copy (`curl -fsSL https://claude.ai/install.sh | bash`, on Windows `irm https://claude.ai/install.ps1
  | iex`, and `npm install -g @anthropic-ai/claude-code`), the download page for Desktop, "Choose its
  file…" and "Look again": never a dead end (8.11).
- **Finding Claude** (domain/claude.py's rules, server/claude_finder.py's probes): loosely, by name (any
  app whose name, bundle id or target says Claude; never its uninstaller, updater or helpers), both kinds
  apart by where they live (a `claude` in a bin folder, npm's shim, the native installer's folder is
  Claude Code; an app's own folder is Desktop). Windows: App Paths and Uninstall keys (HKCU and HKLM,
  64- and 32-bit views), Store packages and Start menu shortcuts' targets (one PowerShell call),
  %LOCALAPPDATA%\AnthropicClaude and Programs folders, PATH, ~/.local/bin, npm's global bin, WinGet's
  links. macOS: /Applications and ~/Applications (each Info.plist), Spotlight (mdfind by name and bundle
  id), PATH, ~/.claude/local/claude, Homebrew. Linux: .desktop files (the user's, the system's,
  Flatpak's, Snap's; the Exec line as an argument list), PATH, ~/.claude/local/claude, npm. Each install
  once; the official first (an Anthropic publisher, `com.anthropic.*`, the AnthropicClaude folder).
  Found on the first Launch or Settings visit (not at start), kept until Look again.
- **Claude Code's folder** (the "proper folder"): `~/.swissarmybench/claude/<project name, made safe, or
  no-project>/`, written again at each launch: CLAUDE.md (what the app is, how to work it through its MCP
  tools, the whole index, and what is open now: the project's name, its .sab and working folder, each
  table's rows, columns and types and its steps in words, the connections by name and type, the documents
  by kind), `.mcp.json` (the `swissarmybench` server, this install's own `swissarmybench-mcp`; no token)
  and `.claude/settings.json` (the prompt hook, as plugin/hooks/hooks.json; the folder's own MCP server
  enabled; **no permission granted**). `claude --add-dir <the project's working folder>` so it reads the
  notebooks and scripts. **Decision:** metadata only, stricter than the prompt hook: a filter's value is
  "equals a value", a SQL step "A SQL step" (its text could carry values), never a row (tested with a
  made-up value).
- **The terminal** (domain `terminal`): Windows Terminal (`wt -d <folder> claude …`, a literal `;`
  escaped as `\;`), else **a new console of its own** (CREATE_NEW_CONSOLE; **decision:** rather than `cmd
  /c start`, whose parsing would read `&` and `^` in a path); macOS Terminal through `osascript`, the line
  passed as an argument (`on run argv … do script (item 1 of argv)`) with every part `shlex.quote`d, the
  only shell line, tested to read back exactly; Linux x-terminal-emulator, gnome-terminal, konsole or
  xterm, the first found. Always an argument list; a project name with quotes, spaces, `;`, `$()` and
  backticks tested. Claude Code's own session markers (CLAUDECODE…) are left out of its environment, so
  one started from a server that a Claude Code session started does not refuse as nested.
- **Bypass permissions** (the owner's second message): Settings, Claude, "Start Claude Code with bypass
  permissions", off unless turned on, kept in claude.json; adds `--dangerously-skip-permissions`.
  **Decision:** off by default; the brief's "keep permissions conservative" holds until the user turns it on.
- **Claude Desktop "the same way"**: it takes no folder, so its context comes through its MCP config. On
  the user's click: where that install keeps claude_desktop_config.json (a Store package's own folder; a
  folder named after the app, as Electron names it, so a company's build named differently is found; the
  official place), the `swissarmybench` server set with every other entry untouched, a dated backup first,
  written beside it and moved over it, no token; then the app started (its Exec line, `open -a`, a Store
  app's `shell:AppsFolder` id). **Asked once per file** ("Add Swiss Army Bench to Claude Desktop?"), never
  again. An unofficial build with no config file anywhere: "Where does this Claude Desktop keep its
  settings?" with the likeliest place and Choose the file…. A file that is not JSON is never touched (the
  reason said). Desktop reads its config on start: when it changed, the toast says to quit and start it
  again if it was open. Its context: the index and the guide (resources already), and **the new resource
  `swissarmybench://context`**, the same "What is open now" read fresh.
- **Settings, Claude**: what was found for each kind (a choice; the found one's source on hover), Other…
  (the file chooser) for an install the search missed, the chosen Desktop's settings file and Choose…,
  the bypass switch, Look again. Kept in `~/.swissarmybench/claude.json`.
- **Trust**: launching and choosing are the user's alone (an agent does not start another agent, nor
  pick what gets launched): `POST /claude/launch` and `PUT /claude` refuse `X-Actor: agent` (403);
  NOT_COMMANDS says why. The agent reads what was found and the summary (`app_claude`, `context=true`).
  127.0.0.1, the token and Origin as every route.
- **Not checked on real Windows or macOS** (no such machine here): the registry, PowerShell, Start
  menu, Store, Spotlight and Terminal paths run against made-up answers only.
- **Open:** if the swissarmybench plugin is also installed in Claude Code, its prompt hook and the
  folder's both add the table in front (said twice); the command `claude` as a setting (the brief: later).

## Trino by a keystore; certificate files from an environment variable (2026-11-16, branch trino-keystore) — built

The owner: "my trino connection uses a keystore file"; "Its saved as .keystore and the difficult part is,
if I want to keep the parity of everything I create here can run in the function app, then I have to map
that file from the function apps location"; it "Signs me in (client certificate)"; "I have saved it to the
function app it is not in the vault". Then: "okay then lets just make this one setting optional to map to
an env variable", and "or any other connections that need to map to a keystore or cert, should have the
option to create a local Env." (A general "every setting of every connection from a variable" was asked
and dropped the same day; nothing of it was built.)

- **Trino signs in two ways** (domain/keystores.py, `sign_ins` on the starter): **Username and password**
  (as before) or **Client certificate (keystore)**: `keystore`, `keystore_alias` (the entry when it holds
  several), the CA `verify` and Trust server certificate as before, and the password always
  `secret("TRINO_KEYSTORE_PASSWORD")` (keyring, environment, vault; the form offers the variable of that
  name first, as for any upper-case secret name).
- **The keystore is read by code inside the connection's own code** (`keystore_files`), so the app, a
  kernel, an export and a function app run the same thing. The format by its first bytes (JKS 0xFEEDFEED,
  JCEKS 0xCECECECE, else PKCS#12), never the name; PKCS#12 with cryptography, JKS/JCEKS with **pyjks, a
  package of the connection** (packages.py maps `jks` to pyjks; Install offers it), never the app's. The
  key and chain become two PEM files in a mkdtemp folder (0700, files 0600 by os.open; on Windows the
  user's own temp folder) removed at exit; `trino.auth.CertificateAuthentication(cert, key)` (trino 0.340).
  Errors in words: wrong password, no private key, several keys without an alias (their names), an unknown
  format, pyjks missing (the pip line), no file at the path (the variable that set it, when one did).
- **Test asks Trino** (server/blade_runner.py): Trino connects on its first query, so a Trino connection's
  Test runs `SELECT 1` ("signed in"; refused: "Trino did not let it in: ..."). Both Trino ways gain this.
- **A certificate file setting kind** (domain/certificate_files.py, one place): settings named
  certificate file (verify, sslrootcert, ssl_ca, ca), keystore, client certificate file (sslcert,
  ssl_cert) and client key file (sslkey, ssl_key) offer **Path** or **From an environment variable**. Mapped,
  the code says `verify = os.environ.get("LAKE_CERTIFICATE_FILE", r"C:\certs\ca.pem")` (the variable wins;
  this computer's path is the default; `import os` written in when missing), read back by ast, so Edit
  shows it again. The suggestion: `<CONNECTION>_<SETTING>` (WAREHOUSE_CERTIFICATE_FILE), the keystore's
  always TRINO_KEYSTORE_PATH. No other field is mapped (refused in words). Connection strings (ODBC
  `Key=value;`) have no certificate file setting in any starter today, so they are not mapped.
- **The shape a Variables page reads:** the mapping lives in the code only; `blades.env_settings(code)`
  gives `[{"variable", "setting", "key", "default"}]`; a setting's JSON has `"env": name | null` exactly
  when it is mappable (absent otherwise).
- **Export as one script** lists a mapped file as `where = "file"` ("a certificate or keystore file's
  path; set it to where the file is here (an Azure Function app: an Application setting)"), never its
  bytes; SETTINGS holds None for it (the code keeps the local default). Not mapped: not listed.
  **Run settings** list a named connection's mapped files (`files_of`, bootstrap) beside its passwords.
- **Agent:** `blades_fill` takes `{"value", "env"}` for such a setting; connections_types carries the
  sign-ins; the connections guide topic says both.
- Add API has no certificate file setting today, so nothing changed there.

## The Session page and Follow the agent (the owner, 2026-11-16; built, branch session-page)

The owner: "when the agent is driving the app and adding things, I want to see objects that were created
in a log make that a new page called Session on the rail. and while you are at it, lets make it so the AI
agent can activate things on the page, so when it working on a diagram I can what it in realtime".

- **The Session page** (web/src/sessionPage.ts, a page of the rail's like Settings and Connections:
  open=session over any page; the icon after Connections, dom.ts `session`): this session's log, newest
  first, live (`session_entry` notices): when, what in plain words, the area, and a link to the object
  (a grid, a table, a card, a relationship on the ERD, a connection's detail, a blade, a notebook or
  script at its cell). A link to the home page's own objects closes the page with no history move of
  its own, so Back brings the Session page again. The agent / Me / Both, remembered per viewer (the
  agent's by default).
- **Built on the audit log, not beside it**: the composition root hands every service an audit that
  writes the file as before and then tells the session log (services/session_log.py `Heard`). The rules
  (domain/session_log.py) keep only actions that make or change something (reads, navigation, snapshots
  and settings make no entry) and write each one's words field by field, so a detail nobody named never
  reaches the page: never a query's text, a step's values, a cell value or a secret (a test feeds every
  rule a made-up value, query and password and finds none). What was missing so each entry names its
  object was added to the audit writes: a step's grid, op and kind; a card's id; the relationships a
  change added and removed (orders.customer_id -> customers.id); a blade's kind (connection or blade)
  and the real actor (blades and connections wrote "user" for the agent's saves); a Workbench command's
  document and selected cell (the window's answer carries `place`); a canvas page's app and file.
  Memory only, 1,000 entries: a new start begins with none (the audit log is the record on disk).
- **Follow the agent: default ON** (the owner's ask is to watch it work; OFF would make the feature
  invisible until found). A switch on the Session page and in Settings, the server's (every window
  follows), kept across restarts in follow.json. ON: the home window brings the area to the front (the
  address replaced: a move of the app's, not the user's) and pulses the object: the ERD with the new
  relationship's line (and its tables) highlighted as Mermaid draws it, Visualizations scrolled to the
  card, a grid with its steps count pulsing; the Workbench window scrolls to the cell the agent changed
  and pulses it. Other areas (connections, blades, the project) only log: moving the home window to the
  blades page would lose its place, and a page over the grids would block the next follow.
- **Never steals focus**: a text box with the focus (inputs, text areas, Monaco), an open dialog, the
  command palette or a page of the rail's on screen (the user is reading it): the latest move waits (up
  to a minute) until they leave it, and the rail's Session icon counts it. OFF: nothing moves; the
  icon counts the agent's entries until the Session page is opened.
- **The agent**: `app_session` (who, limit) reads the log and the switch; the switch is the user's (PUT
  /session-log/follow: 403 for X-Actor agent; NOT_COMMANDS says why: an agent that could turn it off
  could work unseen). app_navigate's areas include `session`.
- **Found on the way**: the ERD's draw raced itself (a draw started before the model loaded finished
  after the one with the model and painted "No relationships yet" over it); each draw now has a number
  and only the newest paints.

## A missing package, in the user's face (the owner, 2026-11-16; built, branch package-prompt)

The owner: "also I created the Key valut connection and along the way it poped up the detection that I
needed to install some things with UV, that was nice but I think we should make it more visible, and it
should be a popup in the user face saying this <insert feature> will not work with out<insert package
name> Install now?"

### Built
- **One shape on the server** (domain/packages.py): every place that finds a package missing answers
  `{"missing": {"feature", "packages", "python", "command"}}`. `python` is "app" (the app's own Python,
  where connections and blades run) or the path of the Python they go into. `MissingPackagesError` turns
  into a 422 `{"error": "<Feature> will not work without <package>.", "missing": ...}` (server/http.py).
- **The places:** a connection's form (`/connections/types`, `/connections/{name}`, `/blades/inspect`:
  the starter's feature, "Key Vault connections", "Trino / Presto connections"); a blade (`/blades/inspect`:
  "The Sales blade"); a run that stopped on an import (test, refresh, open, preview, tables, datasets,
  relationships, vault secrets, an analysis blade: `run_failure` names the connection's kind or the
  blade); a YAML OpenAPI document with no PyYAML ("Reading YAML API documents", once a plain refusal);
  a Streamlit app ("Streamlit apps") and Test this page ("Test this page"), whose `problem` is the shape
  with its kind; a Workbench run that stopped on an import ("This code", the kernel's Python: the
  error detail's `missing`, and the agent's `workbench_run` output says it too).
- **One prompt in the page** (web/src/missingPackages.ts): "<Feature> needs <package>", one sentence
  "<Feature> will not work without <package>." (several: "a, b and c"), **Not now** and **Install now**
  (primary). Install now: a spinner and "Installing…", then the toast "Installed …" and the caller's retry
  (the form read again, the test or the run again, Play again, the page tested again, the cell run
  again); a failure is said plainly with the install's last lines, and **Try again**. Not now (or Escape,
  or the X): the prompt goes, and a small **Install <package>** reminder stays where the feature is used
  (its command beside it on a form); Not now holds for that package and Python for the session
  (sessionStorage, this tab), the reminder opens it again on a click.
- **Installers as today:** the app's Python through `POST /blades/install` (uv, else pip); a Streamlit
  app's through its own install; a document's in its console (`%pip install`, uv when it has no pip),
  then the module imported there, so a failed install is said, not retried in a loop.
- **The agent:** the same answers; `blades_install`, `streamlit_install` and `%pip install` in a kernel
  (`workbench_run`) as before; the guides (connections, streamlit, workbench) and SKILL.md say how.

### Decisions
- **When the prompt comes:** at once where a place opens (a connection's form, a blade on its save screen,
  the Python connection form) or a run stops (Test, Refresh, Play, Test this page, a cell). Never while
  code is being typed (the blade editor and the Python form read their code as it is typed): there the
  reminder says it, and the prompt waits for the next open or run.
- **Not now is per package and per Python** (the brief's "for that package this session"): another
  feature needing the same package does not ask again either; the reminder is always there.
- The old quiet notes went: the form's "Driver not installed: … Install", the save screen's Install
  button, the run-failure dialog's Install, the canvas's primary Install (now a small reminder).
- The prompt's dialog takes no history entry (Back does not close it): it is a question, not a place.
- **Not built here:** the Trino keystore's pyjks (branch trino-keystore): its form says the shape through
  `/blades/inspect` like every other, so it should need nothing more than a feature name, if any.

## Swapping a table's connection (the owner, 2026-11-16; built, branch swap-connection)

The owner's words: "we also need button the the table row to swap a tables connection", "for example my
local agent created an odbc connection when it shouldnt have", "not I have a trino and an edp", "I deleted
the edp but need its queries to run on the other", "so I need a option to swap that sql to run on
trino(non odbc)".

### Built
- **The Table row's Connection: EDP** (ribbon.ts, swapConnection.ts): it names the table's connection
  (from its origin, or the project's file for a table waiting to come back) and opens a chooser of the
  other connections that hold tables. Choosing one reads the table again from it with the SAME steps: the
  first grid takes the new rows, so the tab, its steps and any other grid stay (services/connection_swap.py).
  - A catalog table is matched in the other's catalog (domain/connection_swap.py match_place): the name in
    any case, the schema then the database breaking a tie, and an ODBC database may be Trino's catalog
    (database matching the other's schema counts). The catalog is loaded first when it is not
    (CatalogLoading.ready). Not found, or a tie: the other's catalog tree to pick from (the ones of that
    name first), or Write a query… with a first SELECT in the other's dialect.
  - A query (a table read by a query on a connection, or the "+" tab's query) opens in the SQL window
    (`?panel=connsql`, the SQL step's window pattern: as big as the user likes) holding it, then Run on
    Trino. Only one read runs (SELECT, WITH, VALUES, EVALUATE).
  - A new kind of table source: a connection's query (origin connection + sql, no place): project.json
    keeps it (`source` connection with `sql` and no `table`) and a project reads it again by its query.
  - Its read-only cell follows on its own (the origin changed).
- **A deleted connection** (startView.ts): a waiting table's strip row (No connection EDP) has **Use
  another connection…**: every table that used it (waiting or open) moves at once (POST
  /connections/{name}/move); the queries come back to look over one by one in the SQL window (Review…),
  or **Run as they are**; tables not found are picked in the same dialog.
- **The code follows, with a click:** after a swap or a move, the cells that named the old connection
  (connection_usage's reference finder: `%%sql`, `%%dax`, sab.sql/read/dax/blade/connection), each
  ticked: **Point these at Trino** rewrites the name only, in the ticked cells (domain/connection_swap.py:
  ast for Python, the first line for a SQL or DAX cell; `EDP -> orders` and `EDP/Sales model` keep their
  other words). An open document changes in the Workbench window (doc.repoint: the window's own unsaved
  text, unsaved until Save, or autosaved); any other's file is written (in a project, its working folder:
  the .sab follows on Save or Autosave).
- **Undo:** the toast's, the strip's (a row EDP → Trino with Undo, until put away) and the chooser's: the
  table's rows and origin as they were (a waiting table waits again). Nothing is deleted.
- **The agent:** `table_connection`, `table_swap_connection` (answers swapped, pick or review),
  `table_swap_undo`, `connections_move_tables`, `connections_repoint` (lists without `to`); the index and
  the connections guide.

### Decisions
- The undo keeps the old rows in memory (the last swap of each table only), so it works when the old
  connection is gone.
- A table's read-only cell and a canvas block are not offered to tick: they follow their table or cell.
- A document not open in a Workbench window is written directly (outside a project that is its save);
  open ones change in the window so the user's unsaved text is never overwritten.
- A query moved with "Run as they are" that fails is listed with the source's words; the table keeps its
  old connection.
- The "+" tab's query (DuckDB over the open tables) can be moved onto a connection through the SQL window:
  it then runs there and becomes a connection's query.
