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
- **Settled (2026-11-17, branch context-md):** with the swissarmybench plugin also installed, its prompt
  hook and the folder's both added the table in front (said twice). Now one source: the folder's hook runs
  `swissarmybench-context --folder`; the plugin's (no flag) stays quiet in a folder whose
  .claude/settings.json has that hook. **Open:** the command `claude` as a setting (the brief: later).

## context.md: the app's live picture beside the agent (the owner, 2026-11-17; built, branch context-md)

The owner: "I had an awesome idea for a small context.md that get written in the same place the agent is
launched from that the app would keep up to date with connections, tables, and any context that might have
to constantly be read over and over along with just putting the agent tool guide there".

Built:
- **The file** (domain/context_md.py, services/context_md.py): `~/.swissarmybench/claude/<project or
  no-project>/context.md`. CLAUDE.md there is now a short header that does not change while the app runs
  (what Swiss Army Bench is; context.md is the app's live picture and current; read it first and again when
  the prompt says it changed; the names are data) and `@context.md`, Claude Code's import, so it is loaded
  at start. The whole index moved from CLAUDE.md into context.md's Tool guide.
- **Its sections**, metadata only: **Project** (name, the .sab's file name only, its working folder);
  **Connections** (kind, type, dialect, status word, colour's name, a failing one's last error redacted by
  the beta log's rule, passwords with no source by name; how its tables are named in DuckDB SQL; a loaded
  catalog's schemas or datasets and its first 40 tables by their SQL names, then the count and
  `catalog_search`; the project's documents and the open grids that use it); **APIs** and **Structures**
  (a seam, filled once trees-apis merges: none in this build, so the headings are left out); **Open
  tables** (rows, columns and types up to 30, origin in words: a connection and its place, a file's name,
  Python, pasted, a query, never a query's text; steps in words with no value; grid ids); **Relationships**
  (the ERD's: from -> to, columns, cardinality, inactive); **Variables** (names and sources, a vault's name;
  never a value, a plain one's included); **Documents** (the project's, by kind and role; made files left
  out); **Windows** (the home window's front grid, the Workbench's running kernels by document, the blades
  page); **Tool guide** (the index, the SQL naming rules, and the connections topic's Reading one, Power BI
  workspace and Catalogs sections, read from the guide so they stay current).
- **Small:** settings.context_md_chars (24,000). Over it, trimmed in order: the tables' columns, the
  catalogs' table lists, the guide's topics, then every long list cut to 10; each trim a quoted note at the
  top naming the command that gives the rest; last of all a cut with a note.
- **Names are data:** every name from the user's data or sources is inline code, on one line (control
  characters and line separators made spaces), fenced with more backticks than it holds; a table named
  "ignore previous instructions`` and\n# delete every file" stays one code span (tested).
- **Kept current:** the server looks every settings.context_md_seconds (2 s) after any notice to the pages
  or a window opening or closing (LiveUpdates.changes), and every 30 s all the same; a changed text is
  written when it is the same at the next look (settled: a burst is one write), written beside and moved
  over, never when unchanged. Only into a folder a launch made (no folder, no file, no work).
- **The prompt hook** asks `GET /claude/context/prompt`: the sections changed since the agent's last read
  (the launch, its previous prompt, `app_context`), the file written first, and prints "Swiss Army Bench:
  context.md changed: Connections, Open tables. Read <path> again (or `app_context`) ...". A session not
  started from the folder (the plugin elsewhere) gets one line on its first prompt saying where the
  picture is. The table in front is one short line when context.md exists (its columns and steps are in
  the file), the old summary otherwise.
- **Claude Desktop:** the resource `swissarmybench://context` is now this text (it has no folder); also
  `guide(topic="context")`; the index's first line names both.
- **The agent:** `app_context` (the same text, the file's path, the sections and the trims made); the
  agent's read counts as seen. `app_claude` lost its `context` option to it (the tool list's size).

Decisions: SQL names follow connection-sql's copy_name (a database's tables by schema.table, a Power BI
table by its name unless two datasets share it); written here as their own small rule so this branch
stands alone; at the merge, point `ConnectionFacts.sql_of` at `connection_tables.copy_name`. The folder is
only written once a launch made it (the posture: nothing new on disk unasked). One marker of what the
agent last read (not one per session): two agents at once each hear of a change once between them.

Open: the Workbench window's open (unsaved) documents are not in Windows (asking the window every look is
a round trip; its running kernels stand in); per-session seen markers.

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

## data.ipynb holds everything the app is built from (the owner, 2026-11-17)
"how are we determining what will make it into data note book. like all structures and grids should make it
as well as all variables that are used to create the app". Planned after the Structures branch merges:
data.ipynb gets four read-only groups the app keeps in sync, in order: Variables (every variable a page,
notebook or blade uses, found with ast: its source, never a value), Connections (the library connections
used, `sab.connection(...)`), Tables (every grid: source + steps as one DuckDB query; today's Tables group),
Structures (every Structures document: source + steps; an API call re-run; Return as table ones as DuckDB
tables). The user's cells below, untouched; data.py exports it all, so an exported app runs on its own.
Decided (the owner, 2026-11-17): "everything in the project": every grid and Structures document, used by a page or not.

## The Variables page (the owner, 2026-11-16; built, branch variables-page)

The owner: "after Imported my keyvault and it made a ton on local vairables, that we actually need a workspace
Variable page for the rail to help manage project variables"; "should be able to add new local env variables
from the page easily and browse what is there and for variables that are not from the key vault you can see
their current values". Then (2026-11-17): "Apis, Connections they live OUTSIDE of the project" / "so they
become a library of connections" (Plans/library.plan.md).

### Built
- **A page on the rail** after Connections (open=variables, areaPage.ts; its own `{x}` icon): every variable
  this computer gives or something reads, grouped by source: a key vault's entry (the vault and the
  secret's name), a plain value (shown), the keyring (dots, **Show** on the user's click), this computer's
  environment (shown, unless it reads as a secret: behind Show), not set (a certificate file's default
  path said). Search; a chip per source.
- **Uses**: connections (a password by `secret()`, a certificate or keystore file mapped to a variable, a
  Python connection's code), notebook and script cells (`os.environ[...]`, `.get`, `getenv`, `secret()`, by
  ast), each script's Run settings. A connection opens its card, a cell opens in the Workbench.
- **Add variable** (prominent, in the heading row): name, value, kept as Plain value, **This computer only**
  or Keyring (secret); a secret-looking name goes to the keyring and is refused as a plain value. Edit,
  Rename (connections' code, a vault's mapping and Run settings follow; the notebooks and scripts still
  reading the old name are listed, never edited), Remove (what uses it shown first; a vault entry's
  secret stays in the vault).
- **At once**: the values are set in the server's environment (and given back when removed or when the
  server stops), so a connection's next run, a scheduled script and a kernel started from now on read
  them; a change answers how many kernels run (a toast: they read it after a restart).
- **The agent**: `variables_list` (sources, uses, plain values; never a keyring's, a secret's or a vault's
  value), `variables_set` (`kept="keyring"`: sets a secret, never reads it back), `variables_rename`,
  `variables_remove`. `/variables/reveal` is 403 for the agent (NOT_COMMANDS). The Session page names
  each change, never a value.

### Decisions
- **This computer's, not the project's** (the owner, 2026-11-17, overriding the brief's project scope): the
  page shows the same variables with or without a project open, and a .sab never holds one.
- **Shareable and local apart** (Plans/library.plan.md): `variables.json` in the state folder holds each
  variable's name and source and a plain value's value unless it is "this computer only"; `local/variables.json`
  holds the local values. A keyring's value stays in the keyring (`variable/<NAME>`). Both files behind one
  adapter (adapters/variables.py VariableFiles: sorted keys, no write when nothing changed), so the library
  change moves them to `library/variables.toml` and `library/local/` by changing two paths (and the format).
- A cloned file with no local values reads its local and keyring variables as Not set on that computer.
- Show stays with the user: the golden rule's exception (no answer the agent gets holds a password's value).

The export (the owner, 2026-11-17): "I feel like the export/ build app should create 4 pythons called Variables,
Structures, Data, and Connections along with any app pages": variables.py, connections.py, data.py,
structures.py (from data.ipynb's four groups; imports in one direction: variables <- connections <- data,
structures <- pages) and pages/*.py.

## Connection colours (the owner, 2026-11-16; built, branch connection-colours)

The owner: "can we add a feature where we can choose connection colors that everything associated with that
connection is painted that color, cells, grids, app cells that are associated with that connection etc.?
reserve the rail colors for the rail. I even thing we need tab groups from the grid based on connections".
Then (2026-11-17) connections became this computer's library (Plans/library.plan.md), so a colour is the
connection's on this computer, the same in every project.

Built:
- **The colour** (domain/connection_colours.py): eight palette colours (Teal, Magenta, Olive, Orchid, Rust,
  Pine, Brown, Slate) a new connection is given in turn (the first none wears, else the least worn). The
  rail's colours are refused when chosen (a hue within 18 degrees of a kind colour as the user chose it, of
  the accent red, or amber; a grey has no hue and passes); a kept colour that a later kind colour comes near
  is shown turned just far enough away, its own kept. Every theme shows it made readable by the kind
  colours' rule (4.5 to 1 against the page and panels, 7 to 1 in high contrast).
- **Kept** in colours.toml (adapters/connection_colours.py, the state folder's for now; the library's
  colours.toml later by a path change): keyed by name, sorted keys, one `"name" = "#rrggbb"` line each, a
  save that changes nothing writes nothing. A rename carries the colour; a connection with no line wears
  the next free one in its turn (by name). Not in the blade record, not in a .sab.
- **Worn** (web/src/connectionColours.ts): any element with `data-connections="A|B"` is painted (a
  MutationObserver; `--conn-a`, `--conn-b`), so each place only names its connections: the Connections
  page's cards (the left edge, a swatch) and references, the grid tabs (a stripe along the foot), the
  notebook cells (POST /connection-colours/uses: the server reads them with connection_usage's ast rules;
  two connections: two stripes), a script's `# %%` cells (a margin stripe, codeEditor.setStripes), canvas
  blocks (a top stripe; the left edge stays the kind colour), the Data panel's tables, the Session page's
  connection entries. A table's read-only cell wears its load's connection by the same rule.
- **Tab groups** (panes.ts): a group per connection by the table's origin (GET /grids' `origin`), files,
  pasted, Python and query tables in their own; heads only once a connection's table is open. `order` is
  kept grouped (each group where its first tab was), so the keys and tab drags walk it unchanged; a head
  folds its group (the front tab stays) and drags the whole group.
- **The agent:** `connections_colours` reads every colour and the palette, and sets one (null: the next
  free); a change is a `connection_colours_changed` notice every window follows, and a Session entry.

Decisions: a stripe, never a background; vaults have no colour (no tables; not on a tab or a cell);
`/connection-colours/uses` is page plumbing (NOT_COMMANDS: the agent reads cells with connections_usage).
Open: entries about a grid (not a connection) on the Session page are not coloured by the grid's origin;
a removed connection's line stays in colours.toml (it returns if the name comes back).


## Structures and the APIs page (the owner, 2026-11-17; built, branch trees-apis)

The owner's words:
- "when an API returns data or a payload or you need to author a Json, Yaml, Xml or other type of data
  structure, we need a place to visualize them differently like a pretty place to render it that
  functions like the grids, where you can transform and save json configurations as well as view returned
  payloads from apis."
- "no see you can have json, yaml, and xml that is not a part of an api, they could be used for gates,
  mapping, and other various things within an application unrelated to APIS"
- "I also feel like we need to move the Api feature to its own rail Icon ... so I can easily browse and
  explore Apis that are set up and see thier input and output structures"
- "Apis need thier own page so they can be imported managed, refreshed when the api changes and
  searchable" (an explorer like Django REST Framework's browsable API: built as our own design)
- "Apis, Connections they live OUTSIDE of the project, I dont wanna have to go hunt an api every project."
- "APIS and web calls will be built by using blades"; "they are not really connections, UNLESS they return
  a table"; "APIs are connections but they dont get the connection treatment here".
- "so we need an option on web call blade to return as table. This is the gate for making it querable
  from DuckDB"; "alright just let duckdb to the conversion then"; most of his APIs are "header and rows".
- "We should be able from the ApI page to quickly open a screen, Author an API call using an apis payload,
  then the results will show up in the structure page retaining their lineage"
- "rearrange the rail to make since. In order of workflow."

### Built
- **Structures** (the name is the owner's; "Trees" was refused): JSON, YAML, XML, TOML as documents (tabs),
  a tree and its text side by side, steps replayed on the original (Pick, Filter, Rename, Remove, Set, Add,
  Sort, Flatten; undo, redo, the strip), Open as grid at any path, Save / Save as. The project's own
  `structures/` folder goes into the .sab, and the structures open at Save open again with the project
  (project.json `structures.open`). `sab.structure`, `sab.structure_table`, `sab.show_structure`; the
  Variables pane's Open in Structures; references (the connection finder's, with Structures' own calls).
- **APIs page**: cards (base address, sign-in type, operations, tables, calls, source and when it was
  read), one search across every API and operation (words marked), the explorer (operations by tag with
  method badges; description as markdown drawn as DOM, no HTML; inputs; body and outputs as schema trees
  with made-up examples; Schemas, each with where it is used), Author a call (a screen of its own: inputs
  prefilled, the body in a tree and its JSON, checked against the schema as it is typed), Send (the answer
  in Structures with its status, time, headers), Save as web call, Refresh (the diff, then Apply), Check
  for changes, Rename, Delete (the code that uses it first; the agent's waits for the user's Allow).
- **APIs as blades in this computer's library**: Add API writes `~/.swissarmybench/library/apis/<name>/`:
  `API_<name>.py` (the made client, its signing code kept), the **API blade** (`Orders`: the client, its
  secrets' sources named, never a value), one **web call blade** per operation (`Orders.list_orders`: its
  inputs and body are its settings; its code calls through `sab.blade("Orders")`), `openapi.json` (the
  document as read; a form-made API's operations written as one) and `source.json` (where it was read
  from, when, the switch). The blade store reads that folder like a blade folder, whatever project is
  open; a .sab never carries an API.
- **Return as table** (off by default) is the one gate to DuckDB SQL: an API's tables are exactly its web
  calls with it on (`web_calls.table_calls`, the contract for the connection-sql work), read through the
  API blade's own List the tables and Read a table boxes, made again whenever a web call is saved. DuckDB
  converts: the pages read go to `response` (one row per page, its JSON in `page`); records are unnested
  (`unnest(r, recursive := true)` flattens nested objects; a list inside a record stays a LIST); header and
  rows are projected by position with the header's types (`DUCKDB_TYPES`) winning. The conversion is SQL in
  the blade's header, editable. A required input with no value: the table says `(needs <name> (<where>))`.
- **Lineage**: a structure's origin is its call (API, operation, the inputs and body sent: a sign-in input
  hidden; when; status), then each step, then each grid made from it with the grid's own steps, drawn with
  domain/lineage.py's Mermaid. Run again sends the same call and keeps the steps. A grid made from it has
  origin `structure` (its table cell loads it with `sab.structure_table(...)` once the structure is saved).
- **Write rows with this call** (the owner: "Most writes happen via api anyway"): on a POST, PUT, PATCH or
  DELETE, an open table's (or a Structures list's) columns mapped onto the request's fields (matched by
  name, case and `_`/`-` ignored; nested body fields; a constant instead; a required field unmapped named
  and blocking), a dry run first (the first three requests exactly, the rows, the calls: nothing sent),
  then one call per row or batched (the body an array), one at a time, 429s paced by Retry-After (the API
  blade's retries). The results: one row per input row (its key columns, status, the answer's id or a
  chosen field, the error, the time) as a structure and a grid; Retry the failed rows sends only those;
  the lineage is the input table, the call, the results. Saved as a web call blade in mode "write rows"
  (its mapping in the header's `[web_call.mapping]`); in a cell: settings, the table, `dry_run = True`, one
  call (`api.write_rows`). The agent's `apis_write_rows` dry-runs by default; sending follows the guide's
  rule (only after the user said to write, in their own words).
- **The rail**, in the order of the work: Connections, Variables (where the data comes from), Grids, ERD
  (getting and shaping it), APIs, Structures (web data), Blades (tools), Notebooks, Scripts, Apps
  (building), Visualizations (presenting), Session (the log); Settings at the bottom. The Connections page
  lost Add API and its API cards: a line links to the APIs page.

### Decisions
- One page code constant per name (`STRUCTURES`, `APIS`); commands, files and the client are named after
  them, so a rename is one pass.
- XML: ElementTree with a DOCTYPE or an entity declaration refused outright (no defusedxml here).
  Attributes are `@name`, text beside children `#text`, a repeated child a list.
- TOML is written here (standard library: tables, arrays of tables, inline values); a null or a list at the
  top cannot be TOML, and Save as says so (save as JSON or YAML) rather than changing the data.
- YAML through PyYAML only when this Python has it: the one missing-package answer otherwise.
- The text view is the steps' result, read-only while there are steps (edits there would have no place
  in the steps); edits in the tree are steps. Text edits with no steps replace the original.
- Check for changes is a request the user configured to their own API (an address they gave), on the
  page's opening or Refresh only: not the app's update check, and never in the background.
- Older API connections (API_<name>.py beside a project, before the library) keep working and are listed
  on the APIs page as older; **Make into blades** (on the user's click, or `apis_make_into_blades`) reads
  the document again from the address it was made from or an openapi.json beside it (else the user picks
  the file), makes the library's API blade and web calls under the same connection name (its variables'
  sources kept), and leaves the old file where it is.
- The API blade still loads the made client (`API_<name>.py`, now in the API's library folder beside its
  blades: the signing code reused as the owner said) rather than holding it inline; the explorer reads the
  client's mark there. Inlining it into the API blade's own code is open.
- Header-and-rows with no types in the header come out as text (DuckDB's own detection is not run on a
  position projection); the header's types, when given, are cast with TRY_CAST.
- **Unnest this column** (built after the merge): a LIST or STRUCT column's right-click in its grid, and
  `column_unnest`, adds a SQL step the user can read and change (a list: a row per item, an empty or blank
  list kept as a blank row; a struct: its fields as `<column>.<field>`, never clashing with a column).
- The conversion is shown and edited: "The DuckDB query" on an operation that is a table (Save the query,
  Make it again), in Author a call while Return as table is on, and in Return as table…'s dialog.
- The lineage runs on to the notebook and script cells that read the structure by name (sab.structure;
  sab.structure_table after its last grid).
- After the merge with connection-sql: the API blade stays in `/connections` marked `tables_kind: "api"` (so
  DuckDB SQL names its tables); the Connections page and the Grids landing leave those out, and context.md
  lists an API in its own APIs section, not under Connections.

## A connection's tables in DuckDB SQL (the owner, 2026-11-17; built, branch connection-sql)

The owner's words, after his agent imported a Power BI dataset's relationships (14 model_* tables) from
his workspace connection "Finance Captive" and could not open the tables: "regardless, the app needs to
make it easy for me as the user to use that connection to get those tables" / "right now it does not" /
"I feel like I should be able to write duckdb as Select * from [Finance Captive].EntityName" / "once the
connection is in the book". Then: "I think we need to ensure any connection is that way, it exposes tables
that we can write duckdb against" / "that is the definition of a connection here". On Dataverse: "Dataverse
tds is the only method I like here". On APIs: "APIs are connections but they dont get the connection
treatment here", "they are not really connections, UNLESS they return a table".

### Built
- **The contract** (domain/connection_tables.py, services/connection_tables.py): every kind of connection
  lists its tables and reads one through the same two calls, `places` and `read`. TABLE_KINDS says how
  each kind does it: database (its catalog, a SELECT in its SQL), powerbi (datasets, then tables; DAX),
  dataverse (the SQL endpoint's INFORMATION_SCHEMA and T-SQL), dataverse_web (a connection saved for the
  Web API), python (List the tables, Read a table), api (an Add API connection's table-returning calls),
  file (the file or a workbook's sheets), folder (its files). NO_TABLES says why the rest have none: a
  key vault is "not a connection: a source of secrets for variables". tests/test_connection_kinds.py goes
  through every starter (blade_templates.py and starters/) and each kind on a made-up stand-in, so a new
  kind cannot be added without its tables.
- **DuckDB SQL names them by the connection**: `[Finance Captive].Sales`, `"Finance Captive".Sales`,
  `[Finance Captive]."Sales model".Date` (Power BI, when two datasets share a name; the error names the
  datasets), `[C].schema.table`, `[C].database.schema.table` (any case, an exact spelling wins a tie),
  `[Exports].orders` (a folder's orders.csv). Square brackets are rewritten to quotes for a connection's
  name only, outside strings and comments, before sqlglot or DuckDB see them. Where: the "+" tab's query
  and the SQL box (the app's locked DuckDB: each read is registered as `__sab_conn_<n>`, the guard lets
  exactly those through), a notebook's `%%sql` cell whose connection is **DuckDB** and `sab.sql(query)`
  (the kernel's DuckDB: the app reads each table and sends it as Arrow; the kernel's own DataFrames join
  in by name). The agent writes the same SQL through tabs_new_query and steps_run_sql.
- **Never a cut table** (the coordinator's correctness rule, 2026-11-17): a query reads every row it
  needs, never the connection's Rows to open (that is for opening a grid). The columns the query uses and
  its plain filters (a column compared with values: `=`, `IN` for text; `<`, `>`, `<>`, BETWEEN for
  numbers and dates; IS NULL) go to a SQL source in its own dialect; DuckDB applies them again. A LIMIT
  goes only for one table with no join, group, distinct, order, window or aggregate and every condition
  sent. The source counts first (with the filters); past `max_connection_query_rows` (5,000,000;
  SWISSARMYBENCH_MAX_QUERY_ROWS) it is refused with the table, the count and "add a WHERE that narrows
  it". DAX, Python, the Web API and files read whole (Python and the Web API at most the limit plus one).
- **Read once a session**, kept by (connection, table, what was sent): each answer's `connection_reads`
  says the rows, when, the filters and LIMIT sent; the "+" tab's line and a cell's output show it; the "+"
  tab's toast and `connections_sql_refresh` drop the reads.
- **The Connections page's tree** (connectionTree.ts, in a card's detail): datasets or schemas and their
  tables with a search; each table Open, Preview, Copy name; a group Open all (a confirm with the count,
  each its own grid), Import its relationships (Power BI), Query in a notebook (a new `%%sql` cell, or the
  cell on the clipboard when no Workbench is open). The catalog loads when it is not (its state said). The
  Grids landing's connections open it. APIs are not on the Connections page (their own page has them) but
  their tables are in SQL and its completion.
- **In a notebook**: a DuckDB `%%sql` cell shows the connections it names in its head (connection colours
  can paint `.wb-sql-conn`); completion offers the connections after `[`, then a connection's datasets or
  schemas and tables after `[Name].` (from its tree, never loading a catalog to complete).
- **A grid from such a query** keeps its query as its origin: a project reopens it by running it again,
  and its read-only cell reads `sab.sql(<the query>)`.
- **Dataverse on its SQL endpoint**: the starter's catalog is INFORMATION_SCHEMA on the endpoint, and its
  tables open, preview and read in SQL with T-SQL; the endpoint off says so plainly (its administrator
  turns it on in the Power Platform admin center; no fallback to the Web API). A connection saved for the
  Web API keeps working; its detail has **Web API (switch to the SQL endpoint)** (one click,
  `connections_dataverse_sql_endpoint`). The Web API stays for FetchXML, choice labels and `sab.read`.
- **The agent**: connections_tables, connections_open_dataset, connections_sql_reads,
  connections_sql_refresh, connections_dataverse_sql_endpoint; the query tools' help says the naming; the
  index and the connections guide.

### Decisions
- A SQL **step** does not name connections: a step reads only the table entering it (guard_step), and its
  generated Python must not reach a connection on every view. Joining a connection's table into a grid is
  the "+" tab's query (or the SQL box's pin).
- `%%sql` with no connection and no `%sql_connect` default is DuckDB; with a default it still runs there.
  A new SQL cell still starts on the first connection, unless its text names a connection's table.
- Text filters go only as `=` and `IN`: a source comparing text without case (SQL Server) or ordering it
  another way would otherwise leave rows out; with `=` it can only send more, and DuckDB filters again.
- The kernel fetches each read from the app as Arrow (GET /connections/sql/reads/{id}); a query naming no
  connection never asks the app (a cheap look for `FROM x.` first).
- API: today's Add API connection is a Python connection tagged "api" (its List the tables are its
  table-returning calls); `is_api` is the one place to change when web call blades with **Return as
  table** arrive (`web_call_table(header)` is written against that header already).

### Next
- A function blade that returns a table could be named in SQL the same way (`[My blade].result`).
- DAX could take the columns (SELECTCOLUMNS) and simple filters (CALCULATETABLE) as SQL sources do.
- Settings could set the query limit in the page (today an environment variable).

## The Data Explorer (the owner, 2026-11-17; built, branch data-explorer)

"perhaps the data pane can move to its own pane called Data Explorer that allows use to quickly search but
column names, table name, connection to quickly find data like the structures". Then: "that Data Explorer
should have the option to pop it out into another tab just like the structure explorer".

**Built.**
- **A pane, not the Data panel:** the Workbench's left pane (workbenchExplorer.ts), beside every document
  (the data notebook, app notebooks, scripts, canvases, a landing page), off until opened (the status bar's
  Data Explorer, Ctrl+Shift+E); open or closed, its width and its search are this window's (session
  storage). Resizable by its right edge. The Data panel is gone: its tables and blade variables are
  Explorer results; its project files sit at the Explorer's foot; "+ Table" and "+ Blade" are in its head.
  Its Streamlit cells and Starters are App mode's left panels (workbenchModes.ts gained `where: "left"`):
  a canvas opens with Streamlit cells; Starters is the other one. Settings' switch is **Data Explorer**
  (`workbench.explorer`; `workbench.data`, `.tables`, `.blades` gone). Ctrl+B is gone with the fold.
- **One search** (domain/explorer.py, services/explorer.py, GET /explorer/search, `explorer_search`):
  connections (never a key vault: no tables, so not a connection), their loaded catalogs' tables and
  columns (the catalog's own search, each table with its DuckDB SQL name by connection_tables.copy_name),
  catalogs loaded with sab.load, the open tables and their columns (types, where they came from),
  variables (name and source; never a value) and blades (their call). Any case, by parts: `cust` finds
  `customer_id` and `CustomerKey`; `customerid` finds `customer_id`; several words may spread over the
  path (`orders cust`) but one must be in the result's own name. Grouped in a fixed order, each counted,
  25 a group. A connection whose catalog is not loaded is an **offer** (Load its catalog), loaded by
  catalog_loading in the background, the search again on `catalogs_changed`.
- **Structures and APIs** (registered once trees-apis merged): every open structure and saved structure
  file by name; an open one's keys by their paths (`$.orders[].customer.id`, a list's items as `[]`, up to
  2,000 a structure), each with the parts of one place that has it: **Open at this node** opens the
  Structures page with that node selected (a saved file is opened first), **Copy path** copies the
  pointer. A saved file that is not open is found by name only (its text is not read for a search). APIs:
  each web call with Return as table on (web_calls.is_table: never a write rows call) by its SQL name
  (`[Orders API].listOrders`), its method and path, and its columns with their DuckDB types; Copy SQL name,
  Insert, Query in a notebook. A provider that fails is skipped; `register(name, provider)` adds another.
- **Actions** (buttons, a right-click menu, Enter = the first): a table Open as grid, Preview (nothing
  kept), Copy SQL name, Insert, Query in a notebook; a column Copy name, Insert, Show tables with this
  column (`column=`: the same name in every connection and open table); a connection Show its tables,
  Load its catalog; a variable Open in Variables; a blade Insert its call. **Insert** writes what the
  cell's language writes (a SQL cell `SELECT * FROM [Shop].customers`, a Python cell
  `sab.sql("SELECT * FROM [Shop].customers")`, a column's name, a variable as `os.environ["NAME"]`); a
  cell of neither kind gets a new cell below. **Drag** carries the same pair (EXPLORER_DRAG; Monaco's drop
  picks by its language).
- **Pop out** (explorerPage.ts, /workbench?panel=explorer, "Data Explorer", with the rail): the search,
  filters and scroll travel by a workbench handoff (kind "explorer"); the named window
  `swissarmybench-explorer`; Insert there goes to the Workbench window's focused cell through
  `workbench_window` (`explorer.insert`; the button's tip names the cell, `explorer.target`); a drag from it
  drops into a cell there. **Move back** hands the search to the main window (a handoff to "main"), its
  pane opens, the window closes. The two talk over a BroadcastChannel ("here?", "here", "gone", "back",
  "search"), so a reloaded Workbench knows it is out, and the agent's `explorer.moveBack` and
  `explorer.search` reach it.
- **Home page:** Ctrl+K (Find data…, also in the palette) opens the same component in a dialog, with
  Open the Data Explorer for its window.
- **The agent:** `explorer_search` (names and types only), the window's `explorer.search`,
  `explorer.insert`, `explorer.popOut`, `explorer.moveBack`, `view.explorer`; the guide's connections
  topic has "Finding data", carried into context.md's tool guide.

With the main line merged (2026-11-17), the Data panel's last rule (not beside a script or a landing
page, a499bac and 4a19ff9) is the Explorer's default: it is off until opened, beside anything.

**Decisions.** The pop-out window is a page of its own (explorer.html), not a whole Workbench window: it
holds no documents or kernels, so it never takes a document's handoff. Catalog matching stays the catalog's
own SQL `contains` per word (the folded `customerid` form works for open tables, variables and blades, not
inside catalogs). A canvas drop of a result is not built (a block is a cell's link; a table has no cell to
link to until code reads it). Fixed on the way: grid.css had one unclosed rule (`.conn-block.conn-worn.conn-two`),
which swallowed every rule after it (the Connections page's tree styles among them).

## The Data page (the owner, 2026-11-17; built, branch data-page)

"we dont even need catalog if its just tables" / "yea I said a long time ago we needed a standalone DATA
rail icon and page" / "for this purpose", and "then we dont have to put it in variables". The Data page is
**the one place to browse tables**: the Blades page's Catalog panel goes (branch blade-screen), and the
Variables page keeps only variables and key vaults (nothing about tables there).

**Built.**
- **The rail:** **Data** after Variables (Connections, Variables, Data, Grids, ERD, APIs, Structures,
  Blades…), our own line icon (stacked disks, `data` in dom.ts). A page of the rail's over any page
  (areaPage.ts), open=data: a nav.ts layer, so Back, Forward and a reload work; Open in a new window on
  request; from every page and window with the rail. `app_navigate(to="data")` (domain/navigation.py AREAS).
- **The page is the Data Explorer's fourth host** (dataPage.ts), not a fork: dataExplorer.ts gained a
  `browse` host option whose view is dataBrowse.ts (the tree and the detail side). The search, its chips,
  the connection picker and the recent searches are the same; the actions are the same function.
- **Browsing first:** with nothing typed, GET /explorer/browse (services/explorer.py `Explorer.browse`,
  domain/explorer.py's browse rules): each connection (never a key vault) with its colour, its status (its
  catalog's state: N tables, Not loaded, loading, failed and why, Needs a password) and its tables in the
  groups its tree has (connection_tables.tree with `load=False`: a look never loads a catalog; **Load** does,
  by catalog_loading, and `catalog_loading` notices redraw the status). A table opens to its columns and
  types (GET /explorer/table, read once and kept for the page). Then **Open tables** (with their columns),
  **Structures** (documents and their paths), **APIs** (table-returning calls and their columns) and
  **Blades** whose result is a table (a blade that names its table, which blade-screen adds, else a
  function blade that is not a web call). Names only, never a value.
- **Typed:** the same tree narrowed (GET /explorer/search): a table under its connection and schema, a
  matched column under its table (open); a connection matched by name keeps all its tables (closed); the
  other kinds as their own groups.
- **Actions:** a table's are the Explorer's (Open as grid, Preview, Copy SQL name, Insert, Query in a
  notebook); a connection's Load, Show only this, Copy name; a dataset's or schema's **Import its
  relationships** where the kind has them (Power BI, SQL Server: domain/explorer.py `imports_relationships`).
  **Insert** shows only while a Workbench window has a document in front (`explorer.target`, read on the
  window's focus).
- **The detail side:** the selected table's columns (name, type, nulls), where it comes from, its SQL name
  (Copy), the code that reads it (a `%%sql` cell's and a Python cell's, `df = sab.sql("SELECT * FROM ...
  LIMIT 100")`), and its actions. Under the tree when the window is narrow.
- **Drag** a table or a column into a Workbench cell (EXPLORER_DRAG, the same `dragData` as the results);
  **keys**: the arrows through the tree (Right opens, Left closes or goes up), Enter runs a table's first
  action (Open as grid) or opens a group, Down from the search goes into the tree, **/** focuses the search.
- **One page, not two (decision):** the pane's Pop out opens the Data page in a window of its own
  (`/workspace?open=data&q=...`, the named window `swissarmybench-explorer`) and closes the pane; the old
  popped-out window (explorerPage.ts, explorer.html, its handoffs, BroadcastChannel and Move back) is gone,
  and its address `/workbench?panel=explorer` redirects (302) to `/workspace?open=data` (the browser keeps
  the #token). `explorer.moveBack` is gone; `explorer.popOut` opens the Data page. Ctrl+K's **Open the
  Data page** takes the dialog's search there (`openData`).
- **The agent:** `explorer_browse` (the tree, names only), `explorer_table` (a table's detail), the existing
  `explorer_search`, `connections_open_table`, `connections_preview_table`, `connections_load_catalog`,
  `connections_import_relationships`, `workbench_window` (`cell.insertBelow`, `explorer.insert`). index.md's
  row is `explorer_`, `catalog_`: Data page; the connections guide's "Finding data" says the rest.
- **The tour:** its Catalog stop is a **Data** stop on the rail's Data icon.

**Decisions.** Open as grid from the page opens the grid behind it (a toast says so) and leaves the page
where it was, so several can open in a row; an open table's Open as grid shows its tab (the page makes way).
The browse tree draws 500 tables a group (the search finds the rest), like the Connections page's tree.
Columns are read per table when it opens, not for the whole catalog at once.
## Blades and functions are two things (the owner, 2026-11-17)
"I think we should seperate the different types of blades, function blades should be called something else but I hate the name cuts" / "when you right click in the workbench ide and insert you get two options insert a blade or insert a function".
- **Function**: code you call (import_excel, write_sql_server): inserting one writes its def into the project's functions.py and puts only the call in the cell.
- **Blade**: text dropped straight into a cell (the snippets: DAX, HTML, Markdown, Streamlit, Python).
- The Workbench's right-click (notebook cells and the Scripts IDE): **Insert a blade…** and **Insert a function…**, each a searchable picker with its form for placeholders. Analyses stay in the Analyze menu; an API's endpoints are web calls on the APIs page; connections are connections.
- The rail's Blades page keeps the word, with Blades and Functions shown apart. The renames in the UI, the guide and the agent's commands (functions_list, functions_insert beside blades_*) come with the data notebook change (functions.py).

## Lakes and SharePoint as connections (the owner, 2026-11-17; built, branch lakes-sharepoint)

The owner's words: "OneLake, Data Lake and SharePoint as connections, each exposing tables DuckDB can query,
by the rule we just set. Yes do this." / "Delta lake as well" / "SharePoint should be for the things we can
convert to tables for the grid" / "There can be a generic SharePoint connection type for retrieving
documents" / "Those documents could be csvs, or an Excel file which we could turn into a table" / "My only
SharePoint connection is graph via ropc though" / "All should be mapable to env vars" / "writes are meant
to be handled with blades and cells in notebooks".

### Built
- **Five kinds**, each a starter with its own form, card, icon and sign-ins (server/blade_templates.py
  LAKES), in the Connections page's own group **Lakes and SharePoint**: `onelake` (a Fabric lakehouse's
  Delta tables under Tables/ and its CSV and Parquet files under Files/, through the OneLake DFS endpoint;
  a warehouse by T-SQL on its SQL endpoint, TDS 1433, the Entra token beside the connection string),
  `datalake` (an ADLS Gen2 container and folder: Parquet, CSV, JSON files, Delta folders, hive-partitioned
  folders and a job's part files, one table each), `delta` (every folder holding a _delta_log under a root:
  a folder here, abfss://, s3://, to a depth), `sharepoint` (a site's lists, only lists), `sharepoint_docs`
  (each library's file index, and its tabular documents: CSV, Parquet, JSON lines, each workbook's sheets
  and named tables).
- **One contract**: they are database connections (kind sql, each its own dialect) whose catalog and read
  are the connection's own code (`catalog = conn.catalog()`, `conn.rows(table, schema=..., limit=...,
  columns=..., filters=..., frame=...)`, domain/lakes.py READ), as Dataverse's Web API was. TABLE_KINDS has
  the five; tests/test_connection_kinds.py stands each one in.
- **One implementation each** (all text, domain/): domain/entra.py (the sign-in: as you, managed identity,
  an app registration whose secret is a vault's, and ROPC with or without the client secret), domain/
  lake_code.py (the stores: a folder here, ADLS Gen2/OneLake through the DFS API with a token, a SAS or an
  account key that signs a one-hour read-only SAS here, S3 through DuckDB's httpfs; a Delta table's log;
  the one reader; the writes), domain/sharepoint.py (one Graph client for both SharePoint kinds).
- **Reading a Delta table**: DuckDB's `delta_scan` where it works (a folder here; abfss:// with the azure
  extension and an access-token secret made in that Python's DuckDB, never written down), else the
  deltalake package when it is installed, else the table's log read here (the last checkpoint, then each
  commit) and its active files read with DuckDB's `read_parquet` over HTTPS with the token as a header of a
  DuckDB secret scoped to the storage's address (a partition's values as columns; a filter on a partition
  column reads only its files). Each read says which (`read_with` in the query's answer: "DuckDB's
  delta_scan", "its Delta log, read here, and DuckDB's read_parquet", "Microsoft Graph ($filter sent)").
  A table with deletion vectors or column mapping, read without delta_scan, asks for deltalake (the
  missing-package prompt).
- **Names** (domain/connection_tables.py PATH_KINDS): a table's folders, then its name:
  `[Lake].sales.orders`, `[Fabric].Files.raw."regions.csv"` (or `.regions`), `[Team Docs].Documents.Finance.
  "Budget 2026.xlsx".Summary`. The last parts are enough when they name one table; the whole path, then an
  exact spelling, wins a tie; an ambiguous one names its candidates. **Time travel**: `[Lake].sales.
  "orders@v12"`, `"orders@2026-11-01"` (that day's end) or `@2026-11-01T09:30`; quoted so any SQL reads it,
  and an unquoted `orders@v12` after a connection's name is quoted for you. A kind with no versions says so.
  context.md's naming rules say all of this.
- **Filters sent**: a query's plain conditions go to these kinds as (column, op, value) (`Pushed.filters`):
  a lake applies them in its DuckDB (DuckDB's own pushdown; a partition's files pruned first), SharePoint
  sends them as Graph's `$filter` with `$select` (with the Prefer header; a filter Graph refuses, a column
  not indexed, is applied by DuckDB instead). DuckDB applies every filter again. No silent truncation: the
  query limit counts as for every kind.
- **The tree** shows each table's words: a Delta table's version, size and partition columns ("Delta v1 ·
  3.2 KB · partitioned by region"), a file's format, file count and size, a sheet or named table.
- **SharePoint lists**: columns typed by their definitions (choice and text as text, number and currency as
  DOUBLE, dateTime as TIMESTAMP, boolean); a lookup and a person as their display text with `<column>_id`
  (texts read once from the target list and the User Information List). Paging by @odata.nextLink.
- **SharePoint documents**: read into memory only, never written to disk, kept by the file's eTag (an
  unchanged file is downloaded once in that Python); a workbook's sheets and named tables read from its
  XML (stdlib); `header_row` is the connection's setting. Other documents are the **SharePoint** family of
  starters (list files, a document as a table, download into a folder, upload a DataFrame or a file with a
  dry run, a Word or PDF document's text).
- **ROPC** (the owner's own SharePoint sign-in), offered first for SharePoint: MSAL's
  acquire_token_by_username_password when msal is installed, else the same POST with the standard library.
  Entra's codes in plain words (AADSTS50126, 50076/50079 MFA, 7000218, 65001 naming the Graph permissions).
  The token is in memory only (refreshed five minutes before it runs out). Offered to OneLake and Data
  Lake only if the owner asks.
- **Every setting from an environment variable**: domain/certificate_files.py TOP_LEVEL names the five
  kinds' settings (and Dataverse's tenant and client ids); each field offers "From an environment
  variable" with a suggested name (SHAREPOINT_TENANT_ID, DATALAKE_ACCOUNT, DELTA_LAKE_ROOT...), written as
  `os.environ.get("NAME", "<this computer's value>")`; blades.env_settings lists them (export, Run
  settings, the Variables page's uses, context.md). A password's environment variable is offered as
  SHAREPOINT_PASSWORD etc.
- **%%sql**: a lake's cursor is its own DuckDB with every table a view (sales.orders); OneLake's with a SQL
  endpoint is T-SQL there; SharePoint has none (it says so).
- **Writes** (the connection's code: LakeWrites, SharePointLists.create/update/delete): a Delta table
  appended, overwritten or merged by keys (deltalake's merge), a delete by a condition, optimize/compact
  and vacuum (each with a dry run; vacuum refuses under 168 hours unless allow_shorter=True in the cell),
  a Parquet or CSV file put through the DFS API (create, append, flush) or a temporary file replaced here;
  dry runs count by DuckDB on the table as it is (matches by key, rows a condition hits). SharePoint list
  items by $batch (20 a request), each 429 retried after its Retry-After; an update by id or a key column.
- **The Write starters** (the Write family's shape: one typed function a target, and call snippets with
  dry_run=True): **Write to a Delta table** (Delta append, overwrite, merge, delete, optimize, vacuum),
  **Write to a lake file** (Lake Parquet file, Lake CSV file), **Write to a SharePoint list** (SharePoint
  list create, update, delete). domain/write_capability.py marks onelake, datalake, delta and sharepoint
  writable, sharepoint_docs read-only (its documents: the SharePoint upload file starter).
- **The one reusable rule for environment variables**: domain/certificate_files.py `mappable(setting)`
  (with `plain_name(identifier, keywords)` and TOP_LEVEL): every settings read, write and the form's choice
  ask it; SQL Server's fields (branch sql-server) can join TOP_LEVEL or ENV_MAPPABLE the same way.

### Decisions
- The five are database connections with their own dialects, not a new connection kind: every page and
  command that knows a database knows them (forms, sign-ins, passwords, Test, the tree, the agent's
  commands); what is theirs is their dialect's own read (domain/lakes.py read_by_code).
- Dataverse's sign-in code was not changed: entra.py is a new copy shared by the five (one
  SWISSARMYBENCH_LOGIN_URL for the stand-in), to keep the Dataverse branch's merges simple.
- Remote Parquet and CSV are read with DuckDB's httpfs and the token as a header (one way for the stand-in
  and Azure), not the azure extension; Delta tries the azure extension's delta_scan first in the real world.
- deltalake, msal, pypdf are imported only when used (importlib), so a connection does not ask for them up
  front; azure-identity is the "As you" sign-in's own import (the missing-package prompt).
- The constants of the connections' code are one tuple line (not settings the form would show).
- The library is optional in a document's name; the index table is named by the library's display name.
## Writing data: Write blades for the connections that write (the owner, 2026-11-17; built, branch write-blades)

The owner: "Also writes are meant to be handled with blades and cells in notebooks. So really go through
and create a set of blades that can write to each of our data sources that can be quickly copied into a
cell". Then, the same day: "Write blades should be geared towards our connection types. Most of our
connections don't support it"; "SQL server and azure SQL are two things I use alot so make them robust";
"Most writes happen via api anyway" (API writes moved to the APIs page's Write rows with this call,
branch trees-apis); and, of an idea to compile INSERT/UPDATE/DELETE written in SQL into writes: "it sound
like a lot to get wrong with the write back an we should just build all of those as blades". So there is
no SQL writes layer: every write is a blade, explicit in its cell.

Built:
- **What each kind writes** (domain/write_capability.py): every connection kind the app has is writable
  (its operations and how) or read-only (why, in plain words). A kind is connection_tables' tables kind
  (TABLE_KINDS: database, powerbi, dataverse, dataverse_web, python, api, file, folder), and for a
  database or a file its form's template; a test holds every tables kind to writable, read-only or "by
  its template". Writable: SQL Server, Azure SQL,
  PostgreSQL, MySQL, MariaDB, Oracle, SQLite (the read-only connection's file opened again to write),
  Trino (by its connector), ODBC, Dataverse (the Web API; TDS is read-only, whichever way the connection reads),
  CSV, Excel, Parquet, JSON and folder files.
  Read-only: Power BI (refresh is its action: write the source, then refresh), DuckDB (opened read-only), Snowflake, BigQuery, Redshift, Databricks (their own bulk
  loads), Db2, Teradata, ClickHouse, SAP HANA, Vertica, SAP ASE, Access, your own Python, an API (the APIs page's
  Write rows with this call, branch trees-apis). The Connections page's card shows Writes or Read-only (the
  starters or the reason on hover), its detail the words; `connections_list`, `connections_overview`,
  `connections_types` carry `writes` for the agent. Tests: every writable kind has a Write starter, every
  starter names writable kinds only, a read-only kind has none.
- **The Write family** (56 starters, src/swissarmybench/starters/write_*.blade.py): 13 functions, one
  a target (`write_to_*.blade.py`: Write to SQL Server, Write to SQLite, ... Write to an Excel sheet), and
  43 calls, one an operation (SQLite upsert, ...): Python snippets (a new snippet language, `python`, for a Python cell; a new placeholder kind, `connection`, offered from
  the saved connections, those of the snippet's kind first). Databases: append, create table, replace,
  upsert, delete for SQL Server, PostgreSQL, MySQL/MariaDB, SQLite, Oracle and Trino; ODBC without upsert
  (no one statement every driver takes). Dataverse: create, update, upsert, delete. Files: CSV, Parquet, partitioned Parquet, JSON, Excel sheet. Listed in Write too:
  Excel write table, Excel range as table, Power BI refresh dataset, Power BI refresh and wait (`also`).
- **A function a target, a call a cell** (the owner, 2026-11-17: function blades will be written into the
  project's functions.py and a cell gets only the call: "the only thing inserted into the notebook is
  Importexcel() not the entire blade"). Each Write function is ONE public function with a typed
  signature (`write_sql_server(connection: str, table: str, rows: Any, mode: str = "append", keys:
  Sequence[str] = (), batch_size: int = 1000, identity_insert: bool = False, dry_run: bool = True) ->
  SqlServerWrite`), private helpers (`_upsert`, a mode each), its imports and constants: nothing runs on
  import, so it drops into functions.py as it is (a test holds every one to that). A Write starter's text
  is the call only, its placeholders filled by the form and `dry_run=True` its last argument. Until
  functions.py exists the call is reached as the Excel starters are, one line before it:
  `write_sqlite = sab.blade("Write to SQLite")`; **the functions.py branch replaces that line** (an
  import from functions.py, or nothing). The Connections page's "Writes:" lists the calls.
- **The same shape in every write**: `dry_run=True` the default (it checks, counts what it can
  count cheaply, says the statements, shows 5 rows, changes nothing); one transaction where the target
  has them (a failure rolls back and names its batch and rows; Trino and Dataverse's
  change sets say what was written before it); counts and time at the end, and a difference from the
  last dry run said; the connection's own sign-in (`sab.connection`), never a secret in the cell; its
  packages imported at the function's top (the missing-package prompt installs them into the notebook's
  environment). The agent's rule is in the calls, the functions' docstrings, every description and in `guide(topic="writing")`: dry_run False only
  after the user said to write, in their own words, in this conversation.
- **A shared helper per target, the statements in the function** (client/writes.py: the rows staged in a
  DuckDB of their own, the report; write_sql.py: each database's quoting, marks, values and types;
  write_dataverse.py). Standard library only (the plain client's rule): DuckDB and the
  driver come from the cell's own Python.
- **SQL Server and Azure SQL, made robust** (SqlServerWrite): the target's types from sys.columns size
  every value (setinputsizes: varchar stays varchar, nvarchar Unicode, decimals their precision and
  scale; NaN and NaT NULL); fast_executemany, batches sized by row width, multi-row VALUES under 2,100
  parameters without it; upsert and delete staged in a #temp table of the target's types (COLLATE
  DATABASE_DEFAULT), then one MERGE ... WITH (HOLDLOCK), or UPDATE then INSERT where MERGE is refused
  (a savepoint, the same transaction); keys default to the primary key (none: refused); IDENTITY_INSERT
  only when the rows carry the identity column and identity_insert is chosen; computed columns refused;
  enabled triggers said in the dry run; the dry run's counts from one COUNT join against the staged keys;
  Azure's passing errors (40613, 40197, 40501, 49918, 10928, 10929, 4221), a deadlock (1205) and a
  dropped connection (08S01, 10053, 10054) run the whole transaction again on a fresh connection after
  1, 2, 4 seconds.

Decisions:
- One starter per source and kind of write, not one generic writer: the cell is what the user reads and
  changes, so the statement is in it. The helpers hold only what the starters of one target share.
- MySQL and Oracle replace with DELETE, not TRUNCATE (theirs commits by itself); their CREATE TABLE
  commits by itself, so a failed create drops the table again.
- A dry run reads only (SQL Server's stages keys in tempdb, rolled back). Counts it cannot get cheaply
  are said as uncounted (more than 200,000 keys).
- Dataverse's atomicity is a change set (up to 1,000 rows): a batch_size of up to 1,000 is one
  transaction; a larger write says which batches went in before a refusal.
- No `set`/`where` translation for any target: an update by condition is a SQL cell's own statement.
- Power BI is read-only (the owner's example, 2026-11-17: "Power BI read-only (refresh is the action)"):
  the push-dataset starters an earlier pass made were removed, so a read-only kind has no Write starter.
  Its refreshes stay listed in the Write family (`also`): after the source is written, refresh the model.
- No API write starter and no pointer starter: an API's read-only reason says "the APIs page's Write rows
  with this call", on its card and to the agent.

## SQL Server and Azure SQL, made robust (2026-11-17, branch sql-server) — built

The owner: "SQL server and azure SQL are two things I use alot so make them robust". Built in
domain/sql_server.py; the two starters (sqlserver, azuresql) make a `SqlServer` object written as text, the
way Dataverse and Power BI are, so the app, a Workbench kernel and an export run the same code.

- **Connecting.** The driver: `driver="auto"` takes ODBC Driver 18, then 17, then Microsoft's mssql-python
  (imported by name: only pyodbc is a package the form asks for), then any other "SQL Server" ODBC driver;
  none: the install command for this system (winget, brew, apt/dnf with Microsoft's repository, or pip
  install mssql-python), never a silent failure. Eight sign-ins (the form's Sign in; Azure SQL has seven,
  no Windows): Windows (Trusted_Connection), SQL login, Entra as you (azure-identity's AzureCli, VS Code,
  then InteractiveBrowser, chained), managed identity and app registration with a vault's secret (both the
  standard library's requests), app registration with a certificate (azure-identity), Entra password and
  the driver's Entra default. A token goes in SQL_COPT_SS_ACCESS_TOKEN (TOKEN_CODE, which Dataverse's SQL
  endpoint now uses too) and is taken again, on a new connection, five minutes before it runs out.
- **Options**, folded under Options in the form: Encryption (mandatory, optional, strict; on Driver 17
  yes/no, strict refused in words), Trust server certificate, Host name in certificate, port or instance
  (server\instance), Read only intent, Multi subnet failover, the driver, login and query timeouts.
  ConnectRetryCount=3 always (the driver reconnects an idle connection).
- **Read-only intent is on by default** (the brief): reads ask for a read replica where there is one; the
  Write starters take `conn.for_writes()` (the same settings without it), so writes always reach the
  primary. A `%%sql` UPDATE on a read replica gets error 3906 said with its fix (untick it).
- **Errors in plain words** (ERRORS: number or SQLSTATE -> meaning and fix), the driver's own text after
  them in brackets, raised as the driver's own class with its SQLSTATE first (code that catches
  pyodbc.Error still does; the Write starters' `transient()` still reads it). SQL Server never tells a
  client a login failure's state, so 18456 lists what the states mean and points at the server's log.
- **Retries:** Azure's transient numbers on connect (1, 2, 4... seconds, at most 16 apart, five tries) and
  on a read (SELECT/WITH, not SELECT INTO: again on a new connection); never a write (the Write starters
  run the whole transaction again). 40613 (a paused serverless database) is waited for up to 60 s, each
  wait printed ("resuming") where the code runs; the card says Resuming when the last error was that one.
- **Reads:** `conn.read_arrow(sql)` fetches 50,000 rows a batch into Arrow typed from the driver's
  description (decimal(p,s) and money exact, tinyint uint8, real float32, datetimeoffset an instant in
  UTC, time, uuid as text, binary); a column whose values do not fit becomes text. Open as grid uses it
  (server/blade_runner.py prefers a source's own read_arrow). Output converters for datetimeoffset (-155),
  CLR types (-151) and sql_variant (-150); a plain read of one table (`SELECT [TOP n] *|[cols] FROM [s].[t]
  [WHERE]`) writes geography, geometry and hierarchyid as `.ToString()` and sql_variant as a CAST (sys.columns
  asked once per table).
- **Cancel:** each statement runs on a worker thread while the caller waits; an interrupt (the kernel's
  Interrupt) sends the cursor's cancel (SQLCancel) and re-raises.
- **Catalog** from the system views (SQL Server 2016 and later: no CONCAT_WS, which 2016 lacks): exact
  types, primary key, identity, computed, sparse and period columns, MS_Description, synonyms (their
  object's columns when it is in this database), each table's rows from sys.partitions and its temporal
  history as the table's title. One database: the connection's own (listing every database needs
  dynamic SQL per database; not done). Open as grid counts a table's rows from sys.partitions
  (`sql_server.count_sql`; a view is counted); a filtered count stays COUNT(*).
- **Foreign keys into the ERD:** `connections_import_relationships` (the same route and command as a Power
  BI dataset's) on a SQL Server connection reads sys.foreign_keys (and unique indexes: a key whose columns
  are unique is one-to-one); composite keys whole; a disabled one inactive. The connection's page has
  Import relationships.
- **The card:** Test answers `about()` (driver, sign-in, @@VERSION's first line, edition, service
  objective, collation); the card and its page say it, a case-sensitive collation once. A failing card
  carries its last error in plain words (memory only).
- **Environment variables** (the owner, 2026-11-17): server, database, user, client_id and tenant_id may
  each be "From an environment variable" on these two forms. Merged with lakes-sharepoint into one
  mechanism (certificate_files.py): lakes' `mappable()`, `plain_name()` and TOP_LEVEL (tenant_id and
  client_id keep those names, so Power BI's and Dataverse's forms are unchanged), plus FILE_SETTINGS (the
  certificate and keystore files) and PLACE_SETTINGS (server, database, user: KEYWORDS' names). One rule,
  `says_source()`: a setting's answer carries `env` when it is mapped, and unmapped only for a file or a
  TOP_LEVEL setting; a server, database or user offers the choice only where the form's `env_settings`
  says (the SQL Server forms). One refusal: a number or an on/off setting never comes from a variable.
- **One token code:** sql_server.TOKEN_CODE (`token_struct`, the token beside an ODBC connection string) is
  the text Dataverse's SQL endpoint and OneLake's (lakes.py `_TDS`) both use; Dataverse's generated code is
  unchanged byte for byte, OneLake's imports struct. Microsoft Entra's sign-ins themselves stay two:
  entra.py (the lake and SharePoint kinds: as you, managed identity, app secret, ROPC) and sql_server.py's
  (its eight ways, each a keyword of the SqlServer call). Follow-up: SQL Server's managed identity and app
  secret requests could call entra.py's text once its sign_in(scope) shape fits the SqlServer object.
- Not done: arrow-odbc (not measured: no server here); listing every database on the server; a live
  "resuming" while a child process waits (the card says it after); the grid's Cancel of a connection read
  ends its child process (the server notices the closed connection), it does not send SQLCancel.

## The editions' names (the owner, 2026-11-17)
"we should probably just call this the streamlit edition": today's app is **Swiss Army Bench Streamlit Edition**
(data work and Streamlit apps); beside it **Swiss Army Bench Power Apps Edition** (Plans/code-apps.plan.md).
The Lite edition's plan was scrapped (the owner, 2026-11-17: "Scrap the plan for the light app"); its status-bar
name switch (SWISSARMYBENCH_EDITION=lite) goes with the Streamlit Edition rename. The visible name changes (status bar, titles, installer
messages, README); the PyPI package, the uv tool and the commands stay `swissarmybench` and `sab`, so installed
copies keep updating.

## The editors' intelligence: completion like C#'s and a lint as you type (the owner, 2026-11-17; built, branch intellisense)

The owner: "can we get a basic realtime lint built into the workbench if it isnt already" and "make sure
the code completion is robust to suggest and explain like c# does the function and its inputs. and detect
all the connections, functions, variables and anything in the scaffolded files so we can quickly create
python here"; then "I figure jedi handles most of this". b/scriptside.md's completion and diagnostics items
(the Scripts IDE brief) are built here; that brief builds its tree, go to definition, rename, format and
debugger on them.

### Built
- **One server door for every Python editor** (notebook cells, scripts, the console) and SQL cells:
  `POST /workbench/intel/{complete,signature,hover,lint}` (services/intellisense.py), worked out in one
  worker thread, within a second (else nothing, quietly; the page asks once more and the answer, warmed,
  is quick), a request a newer one from the same editor overtook is skipped, answers kept by the text.
- **Jedi does the Python work** (client/kernel_intel.py): where the document's kernel has run and is idle,
  Jedi's Interpreter over the kernel's own namespace, asked in the kernel as a user expression (the live
  objects: a DataFrame's columns, a variable's type and shape on hover); otherwise Jedi's Script over the
  text, a notebook's earlier cells first (IPython's lines made Python of the same lines), `sab` known, the
  project folder on the path (its modules, pages, scripts) and the document's own Python's libraries
  (Jedi's environment for that Python).
- **The member list:** each name's kind icon, its parameters after it and its return type or module at the
  row's right, the documentation panel beside the list (open from the start once per page, then Monaco
  keeps the user's choice): the docstring's summary, each parameter's words, returns, raises, where it
  comes from. A function's required arguments as tab stops. Ranked: names in scope, the project's, the
  app's, libraries', keywords; what was chosen lately first in its group (kept in the browser).
- **Where Jedi cannot see:** connections in `sab.connection/sql/read("…")` and `%%sql …`, variables in
  `os.environ[…]`, `os.environ.get`, `os.getenv`, `secret("…")` (their source shown, never a value),
  blades in `sab.blade("…")` (their description), structures in `sab.structure("…")`, an open table's
  columns in `orders["…"]` and `orders.` (identifiers only), connections by their code names; `sab.`
  offers the package's calls, never its layers. `[Connection].` inside SQL stays connectionSql.ts's.
- **Auto-import:** a name from the project's functions.py, data.py, structures.py, variables.py or
  connections.py completes with its `from <module> import <name>`: it joins an existing line of that
  module, else goes after the imports at the top (a blank line before code); in a notebook, at the cell's
  top until data-notebook's module-imports cell lands.
- **Parameter info** on `(` and `,` (and kept as the cursor moves): Jedi's signatures (overloads with up
  and down), the current parameter bold (its span in the label), its words from the docstring (Google,
  NumPy and reST read by domain/intellisense.py's parse_docstring), the return type and its words.
- **Quick info** on hover: the signature or the kernel variable's type (and shape), the docstring; the
  kernel's own help when Jedi says nothing.
- **The lint**, 400 ms after typing stops: Python's compile (a notebook cell's magics and `!` lines are not
  errors; a %%sql or %%html cell is not Python), then a small ast pass (undefined names knowing builtins,
  the kernel's names, the names earlier cells make and later cells use; unused imports; an f-string
  without placeholders; `== None`; a bare `except:`; a star import said as unknowable), pyflakes when the
  app's Python has it, Ruff when the document's Python has it (its own rules and fixes; the project's or
  the document's folder's settings, else Ruff's defaults). Squiggles: errors red, warnings yellow, unused
  faded. Ctrl+. fixes: add the import (the project's modules, common aliases like pd, the standard
  library), remove the unused import, define a name from the Variables page
  (`NAME = os.environ["NAME"]`), use the close name, Ruff's own. SQL cells: DuckDB's parser for a DuckDB
  cell (`[Connection].table` read as a name), sqlglot in the connection's dialect otherwise; DAX not checked.
- **The status bar** counts the front document's errors and warnings (nothing while there is none); a
  click lists every problem and goes to the one picked. The page tells the server what each document
  shows, and the agent reads the same.
- **The agent:** `workbench_complete` (replaces the kernel-only one: the kernel is optional now),
  `workbench_signature` (with `hover`), `workbench_problems` (each open document's, or a file checked
  now: a notebook cell by cell in order).

### Decisions
- Jedi, not a home-made analyser (the owner's call): the only parsing kept is a parameter's words from
  its docstring (Jedi gives the docstring whole) and the small lint for when neither pyflakes nor Ruff is
  there. No new dependency: Jedi comes with IPython; pyflakes and Ruff are used only where they are.
- Ruff is never installed by the app on its own and never prompted for: the lint answer carries the
  missing-package shape (`ruff.missing`), and the Problems list ends with "Check with Ruff too: install
  ruff…" (the missing-package prompt, into the document's own Python through its console). A Python
  without Ruff is looked at again a minute on, and a lint without Ruff is not kept, so it joins in once
  installed.
- In a notebook cell, Ruff's rules that do not fit a cell are dropped: imports not at the top, their
  order, the missing final newline, a last line that is the cell's output (I001, E402, F404, W292, B018).
  An undefined name is the app's own check only (it knows the kernel's and other cells' names).
- Cells before and after are the document's order, not the run order.
- The kernel's answer is not kept (its namespace changes with each run); the Script's is kept by the text.

### Next
- Unused variables and redefinitions without pyflakes or Ruff; the run order for a
  notebook's cells before; go to definition, references and rename (the Scripts IDE brief).

## Extensions: the rail's Extensions page and one-click install (the owner, 2026-11-17; built, branch extensions)
"add an extension button to the rail to show what extensions are available to install and one click installs
them"; then "For now focus on the streamlit edition like we currently have and get that build out the door"; then
"It's not an edition now it's the streamlit extension. Preinstalled".

**Built:** the rail's **Extensions** icon (a puzzle piece, above Settings at the bottom) and its page
(open=extensions): a card per extension with its status (**Preinstalled**, Available, Installed, **Coming**) and
version. The catalog (domain/extensions.py): Streamlit preinstalled; Accounting and Power Apps coming, a line each
from Plans/editions.plan.md. Discovery of installed extension packages under the entry-point group
`swissarmybench.extensions` at start (adapters/extensions.py; `SWISSARMYBENCH_EXTENSIONS` for tests and
development only). Install and Remove reuse the update's helper (server/updater.py `launch_change`): the app stops,
`uv tool install --force "swissarmybench[server]==<this version>" --with <each kept extension's wheel>`, the
version checked, the app started; the old set again and a note on a failure. The wheel's address is the GitHub
release of this exact version. An update of the base keeps every installed extension (`--with` its wheel at the new
version; the restore at the old one). Remove asks the user first; the agent's `extensions_install` and
`extensions_remove` wait for Allow; `extensions_list` reads. A development checkout (no uv receipt) answers 409 with
what to run instead. The status bar's name is **Swiss Army Bench** (the Streamlit Edition name went); the version
mark's tooltip lists the installed extensions ("Extensions: Streamlit"). The installers' closing line and README's
heading say Swiss Army Bench.

**Decisions:** an extension the catalog does not list but that is installed shows as Installed; it is not kept
`--with` on an update (its wheel's address is unknown), so an update's `--force` drops it: an extension of ours is
always in the catalog. A preinstalled extension stays Preinstalled even when a package says it is installed. The
card follows the restart by /health: answering, stopped, then a new server (its own token: this page's link ends,
the new app opens its own page).

**Left out (later work, on the owner's narrowing):** the separate `swissarmybench-streamlit` package (its own
pyproject, the same version, the entry point); gating the Streamlit features behind one capability check (the Apps
area, the canvas, App mode, the cells pane, the starter families, New Streamlit app, the `streamlit_*` commands
answering plainly without it); moving the Streamlit code out of the base; build.py building the extension wheel;
release.yml publishing only the base wheel to PyPI (a second project would be refused) while the GitHub release
carries the extension wheels; the update helper adding Streamlit `--with` for installs from before extensions; the
installers' line about the Extensions page; the test suite running with the extension switched on. **PyPI later:**
PyPI's trusted publishing covers only `swissarmybench`; publishing `swissarmybench-streamlit` there needs the owner
to add a publisher for the new project on pypi.org first, then the install can use `--with
swissarmybench-streamlit==<version>` instead of the GitHub wheel's address.

## The library: connections, APIs, vaults, blades and variables outside any project (the owner, 2026-11-17; built, branch library)

The owner: "Apis, Connections they live OUTSIDE of the project, I dont wanna have to go hunt an api every
project." / "so they become a library of connections" / "and apis" / "that library is the thing I wanted
to push to a github repo so it can be shared as a code base with fellow users later". Blades go in it too.
Plans/library.plan.md. This replaces "Project scope: everything is the project's own" (2026-11-16) for
connections, APIs, vaults, blades and variables; projects keep their documents, tables, grids, Structures,
Visualizations, model and saved dashboards.

### Built
- **The folder** (adapters/library.py LibraryFolder, domain/library.py): `~/.swissarmybench/library`, or the
  folder Settings' **Library** names (library.json: the path only). `connections/`, `vaults/`,
  `blades/<name>.blade.py`, `apis/<name>/`, `tangs/<name>.tang`, `variables.toml`, `colours.toml`, `local/`;
  README.md and .gitignore (`local/`, `*.tmp`, `*.part`) written on the first write into it, never over the
  user's own.
- **Every store reads and writes there, project open or not:** the blade store writes each saved blade as
  its portable file (the `# /// swissarmybench-blade` header) in vaults/, connections/ or blades/ by what
  it is (domain/library.py folder_for, on connection_kind), and reads them back (cached by modification
  time and size); a kind change moves the file; a rename writes the new file and removes the old. The
  Variables page's two files are TOML (variables.toml sorted by name: `[variables.NAME] from = "value"`;
  local/variables.toml `[values]`); colours.toml, the APIs' apis/ and the tangs follow the folder by a
  callable, so changing it is one call (bootstrap's library_moved).
- **Stable:** a file is written only when its text changes (the blade's text has no timestamps: its times
  are the file's), so a save that changes nothing changes no byte and no modification time.
- **Never a secret:** secrets stay in the keyring under `blade/<name>/<secret>` and `variable/<NAME>`.
- **Key vaults on the Variables page** (a thing with no tables is not a connection): a card each and
  **Add key vault** (a vault type's form, the Connections page's, as before: its detail, Edit and Test are
  unchanged). The Connections page lists no vaults and offers no vault types, except from a password's
  **New vault**, which still makes one in place.
- **Migration, once, said:** at start, this computer's older stores (state folder's blades/*.json,
  variables.json and local/variables.json, colours.toml, tangs/) are written as library files (a name
  the library has already stays as it is) and the old files moved to `backup/before-library-<date>/`; the
  page says it once (POST /library/notices, taken at page load). An older project's own `.sab/blades`
  are copied in when it opens (services/library.py take): the same text skipped, a different one kept as
  **`<name> from <project>`** (a blade name has no brackets, so not `<name> (from <project>)`), its keyring
  values copied to the new name; the notice (`library_notice`) lists them; the working folder's copy is
  removed, so the next save leaves `.sab/blades` out. An older app still opens the new file (it finds no
  blades of the project's own).
- **Import** of connections and blades from another project goes into the library the same way (no
  project needs to be open for it); the import dialog's **This computer** source is gone (the library is
  this computer's).
- **A clone on another computer:** pointed at by Settings' Library, it opens with the same connections,
  vaults, blades, APIs, variables and colours; each connection's missing password is "Needs a password"
  with **Set the password** (the existing fix); a local variable is empty until set there; a keyring
  variable is Not set.
- **The agent:** `library_info` (the folder, counts, Git or not, what stays local, what never goes in, the
  notices), `library_set_folder` (waits for the user's Allow: every store changes), the area `library` and
  the guide topic `library`; the existing connection, blade, variable, API and tang commands act on the
  library. The app never runs git.

### Decisions
- Saved blades are portable `.blade.py` files, not JSON: they diff well and are the format blade folders
  and packs already use, so a library can be turned into a pack.
- Per-item "switched off on this computer" in local/ was not built (nothing switches library items off
  yet); local/ holds the local variable values.
- Several libraries at once (yours plus a team's, read-only) is not built: one library at a time, and blade
  folders and packs stay read-only extras as before.
- The library's README and .gitignore are written on the first write, not at start, so a server that never
  saves anything writes nothing.


## The Accounting extension (the owner, 2026-11-17; built, branch ext-accounting)
"the accounting edition includes a project type where the deliverable is an Excel workbook and the workflow is
simply connection, data, build an python excel automation. The canvas can used to build excel files with pivots
and charts and tools to import and build cession statements and invoices from python." Plans/editions.plan.md,
"Extension: Accounting", "Project modes", and its decisions 2 and 3.

### Built
- **The package:** `extensions/accounting/` (`swissarmybench-accounting`, the base's version, depends on
  `swissarmybench[server]`; entry point `accounting = "swissarmybench_accounting.extension:describe"` in
  `swissarmybench.extensions`, as the extensions branch reads them). build.py builds its wheel beside the base's
  and refuses one whose version is not the base's. Its Python: `runtime.py` (the one generator), `design.py`
  and `templates.py` (rules, no I/O), `exporter.py` (workbook.py's text), `files.py` (files, the preview),
  `service.py`, `routes.py` (under /accounting), `commands.py` (12 agent commands), `extension.py` (what the
  base reads: describe(), MODE, AREAS, routes(), scaffold(), commands()).
- **The switch:** `swissarmybench/extensions.py`: `extension_on(id)` (installed entry points, or
  SWISSARMYBENCH_EXTENSIONS; "-id" turns an installed one off), `enabled()`, `modes()`, `mode_of()`. Off,
  nothing of Accounting shows: no routes (GET /accounting is 404), no commands, no project type, no canvas.
- **Project types and modes:** a project folder's `.sab/project.json` says its type (`bi`, or an extension's);
  `project_new(type=...)`, New <type> project… in the Workbench's project menu. The mode is DATA (the base's in
  extensions.BASE_MODE; Accounting's in its MODE: canvases ["excel"], families ["Excel", "Write", "Files"],
  languages ["python"], no cell kinds, tools ["workbook_", "template_", "statements_"], export ["workbook.py",
  "workbook"]), read through services/modes.py (`GET /app/mode`, `/app/modes`, `app_mode`) and web/src/modes.ts.
  While an Accounting project is open: New and the empty state offer "New Excel workbook" (and not the Streamlit
  canvas: the mode names the canvases), the Blades page and Insert a snippet… show its families first with
  "Show all", and the MCP lists its tools first (mcp/server.py asks /app/mode each time the list is asked for).
  No `if type == "accounting"` in shared code.
- **The Accounting project:** data.ipynb and data.py as every project, `workbook.design.json`, `workbook.py`,
  `templates/`; no Streamlit app.
- **The Excel canvas** (excelCanvas.ts; its machinery shared with the Streamlit canvas through canvasKit.ts:
  Undo/Redo, the tabs, the resize grip, which workbenchCanvas.ts now uses too): sheets as tabs; title, text,
  table, pivot and chart blocks on a grid of cells (drag, the corner, arrow keys, Delete); Properties for the
  selected block or the sheet (freeze panes, orientation, paper, fit to width, header, footer). Play builds the
  workbook from the open tables, each through its grid's steps, and shows each sheet as built
  (excelPreview.ts: formats, merged cells, fills, colour rules, totals worked out, charts drawn where they are
  anchored); Download; Export workbook.py.
- **Templates** (excelTemplates.ts): Import keeps the workbook's layout, formats, merged cells and named
  ranges; a click on a cell names its place (its named range first) and binds it to a value (a column, text with
  {column} names, the number, the date) or to a table of lines that grows (rows inserted under the area: the
  formulas, merged cells and named ranges below moved, a total's range made longer, the area's style on the new
  rows). Saved as templates/<name>.xlsx and templates/<name>.bind.json.
- **Statements and invoices:** `build_statements(template, data, lines, group_by, out_folder, dry_run=True,
  ...)` in runtime.py (so workbook.py has it too): one workbook per group or one workbook of sheets, named from
  columns, numbered (`{"start", "pattern": "INV-{n:05d}"}`), dated; the dry run first (files, rows, totals);
  nothing written over unless asked; register.csv beside them, opened as a grid.

### Decisions
- **One generator:** runtime.py is the builder Play runs and the text Export writes into workbook.py whole (the
  design as a Python literal, the tables from data.py by their variable names). Tested by building both ways
  and comparing the workbooks cell by cell (value and number format).
- **openpyxl only** (already a server dependency): it reads templates and writes their copies, so the built
  workbooks use it too; xlsxwriter is not used. No new dependency.
- **Pivots are summaries** (the owner's decision): one `GROUP BY GROUPING SETS` in DuckDB gives the cells,
  each row's and column's total and the grand total (an average's total is every row's average, not the
  average of averages); written as a formatted table. A chart of a pivot shows its cells, never its totals.
- **A table's total row is Excel's own formula** (`=SUM(C6:C23)`): it stays live when someone edits the
  workbook, and the preview works it out.
- **Each block's query runs in a DuckDB of its own**, the tables registered by name, then
  `enable_external_access = false` and `lock_configuration = true`: a query cannot read a file or reach the
  network. The same in workbook.py.
- **The real build is the dry run's request**: refused (409) without that dry run in this session; the agent's
  waits for the user's Allow as well ("files written only after the user said to").
- **A design is data only**: no rows in workbook.design.json; the preview and the built bytes live in memory.
- A template's numbering and date are bindings like any other place.
- The Excel canvas is a Workbench document (Doc kind "workbook"); it is not kept in the session restore (the
  server's design ids do not outlive it): it opens again from its file.

### Next
- Wire into the extensions branch (its catalog, Install, the Extensions page) once it merges: replace this
  branch's extensions.py discovery with its adapters/extensions.py, keep `extension_on`, MODE and modes().
- context.md: the project's type and the installed extensions; the mode's guide topics first.
- Number formats per locale (the currency symbol), a template's table bound to several areas, images (a logo).
- With the extension on, the MCP tool list is about 4,000 characters longer (79,551 against the base's 75,558).

## The Power Apps extension, phase 1: code apps with Microsoft's own command lines (the owner, 2026-11-17; built, branch ext-powerapps)

The owner: "pac actually simplifies a ton of this and instead of writing custom code to manage the project we
let pac cli do the work ... The custom connector API we get for free, and we actually get a browsable power
automate connector list for free with pac to import it and its shape in the API explorer." "Powerapps edition
and accounting edition are where I can get the most value"; "Build the other two extensions in parallel".
And on modes: "for a code app it's typescript react, and additional cell types with blades for typescript".

**Built:** `extensions/powerapps/` (`swissarmybench-powerapps`, the base's version, entry point
`powerapps = "swissarmybench_powerapps.extension"`, project type `codeapp`), its own layers (domain:
cli_lines, tools, project, connectors; services: powerapps; adapters: runner, files, environment_api;
server: routes; commands; five TypeScript and React starters). The front end's plug-ins in the shared
`web/`: the rail's **Code App** area and page (codeAppPage.ts), a code app's file in the Workbench's editor
(workbenchCodeFile.ts, Monaco's own TypeScript service: its worker `ts.worker.js` is built now).

**Decisions:**
1. **The docs moved past the plan: `pa`, not `pac code`.** Microsoft's code apps documentation (2026-11-10)
   builds code apps with the npm **Power Apps CLI** (`pa`, `@microsoft/power-apps-cli`, Node.js 22 or later);
   `pac code` is "(Preview) ... will be deprecated". So the app runs `pa` for the app (sign-in, init, data
   sources, connectors and connections, push, the code apps list) and `pac` for what `pa` does not do: the
   environments list (`pac env list`), its sign-in profiles, custom connectors (`pac connector create`), and
   a connector's definition's token (`pac auth token`). Both are "the Power Platform tools" on the page.
2. **New code app = Microsoft's quickstart, step for step:** `npx degit
   github:microsoft/PowerAppsCodeApps/templates/vite <folder>`, `npm install`, `pa app init --display-name
   --environment-id`; `.sab/project.json` records `{"type": "codeapp"}` (the Accounting branch's project
   type file), and the open code app is the open project (`projects.opened`), so the base's mode follows it.
3. **Every value on a command line is checked:** one line, no leading dash, and never anything that looks
   like a secret (a `password=`, a JWT, a long run of key characters): refused before anything runs. Sign-in
   is the CLIs' own browser sign-in; their tokens stay in their own stores. `pac auth token`'s output is read
   in memory for one request and never streamed, kept, logged or shown.
4. **Every run** (its words only, never a value twice: "pa app init", "npm run build") streams to the page
   (`powerapps_output`), is kept for the session (`powerapps_runs`), and goes to the audit log, so the
   Session page says "Ran pa app push (done)". stdin is closed: a command that would prompt fails at once.
5. **Missing tools** are the base's missing-package answer (422, `python: "tool"`, this system's install
   command): winget, brew or apt for Node.js, `npm install --global @microsoft/power-apps-cli`, `dotnet tool
   install --global Microsoft.PowerApps.CLI.Tool`; a `sudo` or piped command is the user's to run (said, not
   run). Installing waits for the user's Allow when the agent asks. Deno is listed as phase 2 and blocks
   nothing; .NET shows only while pac is missing.
6. **Connectors in the APIs explorer's model:** `pa connector list --json` lists them; one's shape is its
   Swagger 2.0 read by `domain/api_explorer.explore` (the same operations, inputs, outputs, schemas and
   made-up examples), read-only (no Author a call, no Return as table), its internal operations left out, each
   operation's `operation_id` (the generated service's method, `ContosotasksService.ListTasks`). The
   definition comes from the code app's own `.power/schemas/` (the CLI's download), else from the
   environment's connectivity service the CLI itself reads (`connectivity/connectors/<name>?api-version=1`,
   `properties.swagger`) with pac's sign-in. **Add to app** = `pa app add data-source` with the chosen
   connection. The Code App page draws the explorer itself (the APIs page's classes and its `mountTree`);
   apisPage.ts is not changed.
7. **Run live** = the template's dev server (`npm run dev -- --port <free> --strictPort --host 127.0.0.1
   --base /powerapps/live/<key>/`), passed through this server exactly as Streamlit's live pages
   (`streamlit_proxy.routes` now takes a prefix), so the pane's address carries its own secret and the page's
   frame policy stays `frame-src 'self'`; the frame is sandboxed without our origin. Local Play (where
   connectors answer: inside make.powerapps.com, in the user's own browser profile) is the dev server's
   printed play address, else the one the CLI builds. Without the Power Apps Vite plugin, Run live says to
   use `pa app run` in a terminal.
8. **Push** = `npm run build`, then `pa app push` (the docs' two steps); the link it prints is the app's.
   The agent's push waits for Allow; a dry run says what would run. **Versions:** the CLI lists no versions of
   an app: Versions shows `pa app list` (this app marked) and this session's pushes.
9. **Custom connectors** from an API on the APIs page (`ApiExplorer.document_of`): `apiDefinition.swagger.json`
   (OpenAPI 3 converted to Swagger 2.0: servers to host/basePath/schemes, requestBody to a body parameter,
   components to definitions, `nullable` to `x-nullable`) and `apiProperties.json` (the sign-in mapped: none,
   API key, Basic, a bearer token as an API key in Authorization, OAuth 2.0's authorization code flow as an
   `oAuthSetting` with an empty client id; the others said plainly); a dry run shows both; then written in the
   app's `connectors/<api>/` and `pac connector create` (or update with a connector id). No secret in either.
10. **The code app mode, as data** (the Accounting branch's shape, `MODE` in the extension module, read by
    `extensions.mode_of`/`services/modes.py`; this branch takes that base code as the Accounting branch has
    it): canvases `components` (TSX previews, phase 2), families TypeScript, React, Connectors, languages
    typescript and tsx, cell kinds typescript and tsx, tools `powerapps_`, export push. Read by the front end
    without naming the type: the Workbench's New makes a file in the mode's first language when it is not
    Python ("New TypeScript file"), "+ Cell" lists the mode's cell kinds it cannot run as "(coming)", the
    Blades page lists the mode's families first (the others behind "Every family").
11. **Snippets in TypeScript and TSX** (`domain/snippets.py`): a value is written for where it stands (a
    string: escaped; a template literal: `${` escaped too; bare: a TypeScript name, never a reserved word).
12. **An extension's other seams** (beside the Accounting branch's routes, commands and areas): `STARTERS`
    (its starter blades), `SECRET_PATHS` (its live pages' secret paths, for the guard), `SESSION_RULES` (its
    Session page words) and `stop(services)` (its processes end with the server).

**The connector spike (plan section 5): a connector's generated service cannot be called from outside the
app's own page.** Read in the Power Apps client library (`@microsoft/power-apps` 1.6.0, its
`DefaultPowerAppsBridge` and `RuntimeDataClient`): every data call asks the host for a token
(`AppIdentityServicePlugin.getAppAccessTokenAsync`) and sends its HTTP request through the host
(`AppHttpClientPlugin.sendHttpAsync`), over a `MessageChannel` it opens with `window.parent.postMessage`
and an anti-CSRF token the host hands back. With no Power Apps host as the page's parent (a notebook cell
in Deno or Node, or our pane), the calls wait for an answer that never comes. So TypeScript notebook cells
cannot call connectors directly. Routes left for phase 2, not built: (a) a small bridge component inside the
running app (Local Play) that takes requests from the bench and calls the services there, in the user's
browser, signed in; (b) Dataverse alone from the notebook through the existing Dataverse connection (the
Web API or TDS), which needs no host. Not checked against a running host (no tenant here).

**Phase 2 (built since: "The Power Apps extension, phase 2" below; the bridge decided against there):** the data notebook's TypeScript and TSX cells on Deno's Jupyter kernel with DuckDB's
Node package (`@duckdb/node-api`) sharing one DuckDB with the SQL cells; `data.ts` as data.py is today;
TSX previews (the `components` canvas) with sample props from made-up data or a table's first rows; TSX
blades bound to Dataverse; TypeScript functions; the bridge above; canvas apps (`.msapp` source, Power Fx
IntelliSense, `pac canvas` or what current pac uses).

**Open:** app_navigate does not know the `codeapp` area (navigation's AREAS is the base's list; the agent
works through the `powerapps_` tools); Settings' Extensions section (the extensions branch) and this
extension's Install there come with that branch's merge.

## Projects are folders, and the home page is the Project Explorer (the owner, 2026-11-17; built, branch project-folders)

The owner: "I think we need to just consider entire folders projects and take out the .sab" / "that way we
can share entire projects in git repos nativly", then "Yes build it with projects as folders" / "Make the
project page sortable by card with explanations of project types for beginners". This **reverses** "Projects
as one .sab file" (2026-11-16): a folder is what Git, VS Code and Jupyter already understand, the library is
already a folder, and the scaffold was a folder anyway.

### Built
- **A project is a folder.** Its documents are ordinary files at its top; the app's state is `.sab/`:
  `project.json` (format, type, tables with sources and steps, tabs, windows, autosave; sorted keys, no
  timestamp, no name: the folder's is the project's), `visualizations.json` (Visualizations as left),
  `visualizations/` (saved dashboards; an older `.sab/dashboards` is moved once on open), `model.json`,
  `data/<table>.parquet` only on "Keep its rows". Each file is written only when its bytes change, so a
  save that changes nothing changes nothing in Git. No zip, no working folder in the temporary folder.
- **Data stays out of Git by default:** `.sab/.gitignore` (`data/`, the app's own) and the scaffold's
  `.gitignore` (`.sab/data/`, written only when the project has none), and a README that says why and how
  to commit data on purpose.
- **New** (a name, a type, the projects folder or Choose another folder…; scaffolded, opened, saved at
  once; Autosave on by default), **Open** (a folder; a plain folder answers `not_a_project`, and "Make this
  folder a project?" scaffolds around it, never writing over a file; a folder with data.ipynb and no .sab/
  opens as is), **Save**, **Copy project to…** (rows only on a tick; the agent's with rows on Allow),
  **Close**. The ● mark is still worked out against what .sab/ would hold.
- **Old .sab files, one release:** Open a .sab file… (and `swissarmybench open x.sab`, a double-click's
  command) imports one into a folder the user picks: every entry checked by the old reader (no `..`, no
  absolute path, no link, sizes), its manifest, Visualizations, model, rows and dashboards placed in
  `.sab/`. The installers stop registering .sab and take an earlier registration away (Windows HKCU, the
  Linux MIME type and desktop entry); `server/sab-file.*` stay for that release.
- The .sab conversion removed (the owner, 2026-11-17): Open a .sab file…, `project_import_sab`,
  `/project/import-sab`, a .sab as an import source, the zip reader, `server/sab-file.*` and
  `max_project_file_bytes` are gone; `swissarmybench open x.sab` says "x.sab: this version opens project
  folders only." and starts nothing; the installers still take an earlier .sab registration away; an older
  project folder's `.sab/blades` are still adopted into the library (branch remove-sab-import).
- **The Project Explorer** (the home page, replacing the Start view): every project in the projects folder
  (Settings: Projects folder, `projects.json`; default `~/Swiss Army Bench Projects`) and every one opened
  from elsewhere (recent_projects.json, folders). A card: name, type (its colour and picture; an off
  extension's "Needs the Accounting extension" with Install), last opened, last changed, created, folder
  (short, whole on hover), counts, Git (a repository, its branch from `.git/HEAD`, never running git), Open
  on click; a menu: Open, Show in folder, Copy project to…, Rename, Move left/right, Remove from list,
  Delete… (to the system's trash on the typed name). Sort by Last opened, Name, Type, Last changed,
  Created, or Custom (drag; kept in projects.json); a type filter and a search box. Missing projects last,
  with Locate… and Remove from list.
- **Types for beginners:** "What kind of project?" cards on the page and behind New project's "?": plain
  words (title, for whom, what you get, an example) from each mode (`BASE_MODE` and each extension's
  `MODE`: `title`, `for_whom`, `explain`, `example`), a small picture drawn by us, Create. Put away once
  read (remembered). With no projects: the cards large, "Create your first project".
- **The agent:** project_new (name/type/folder), project_open (make), project_save, project_copy,
  project_import_sab, projects_list, projects_sort, project_rename, project_remove_from_list,
  projects_folder_set (waits for Allow), project_types. Show in folder and Delete are the user's own.

### Decisions
- **Design principle 7.1 is overridden here, on the owner's explicit ask:** the type cards explain in
  sentences. Nowhere else.
- **The Streamlit app type** is the base's words for now (`STREAMLIT_KIND`: a base project with its app's
  canvas, `make: {"type": "bi", "app": true}`); a mode of type `streamlit` (the Streamlit extension's, branch
  ext-streamlit) replaces it automatically. A base project with a canvas is shown as a Streamlit app.
- An Analysis project starts without a canvas (`app` defaults to true only for the Streamlit type).
- `project_new` no longer writes a pasted table's rows into data.ipynb (rows stay out by default), so it
  asks nothing; `/projects` (the scaffold alone) stays for the extensions' own New.
- Rename renames the folder (never the open project's); Remove from list hides a projects-folder project
  (projects.json `hidden`) and never touches a file.
- Delete moves to the system's trash: Windows' Recycle Bin (SHFileOperationW with FOF_ALLOWUNDO), the
  Finder's Trash (osascript), the freedesktop Trash on Linux; never a plain delete. No new dependency.

### Next
- The release after: remove the OLD_* names (the .sab import, the zip reader and `server/sab-file.*`
  went on 2026-11-17).


## The Streamlit extension: preinstalled, a package of its own (the owner, 2026-11-17; built, branch ext-streamlit)

"It's not an edition now it's the streamlit extension. Preinstalled" / "build the other extensions as well".
Streamlit was listed as preinstalled but was part of the base package. Now it is `swissarmybench-streamlit`
(extensions/streamlit/, the base's version, entry point `streamlit = "swissarmybench_streamlit.extension"`),
plugged in like Accounting and Power Apps, and installed with every install.

**Built:**
1. **The package** with the Cosmic Python layers inside it: domain (streamlit_cells, controllers, thin_cells,
   app_settings), services (streamlit, streamlit_ports, streamlit_documents with the Workbench's AppFile,
   controllers), adapters (streamlit_files), server (streamlit_apps, routes_streamlit, routes_controllers),
   commands.py (every streamlit_* tool and the Workbench's canvas and live-cell commands: workbench_new_app,
   workbench_canvas*, workbench_live_*), extension.py (describe, MODE with the beginners' title, for_whom,
   explain and example, AREAS, STARTERS, SECRET_PATHS, routes, stop, scaffold, project_app), and its 52
   starters (Streamlit, Components, Controllers, Text and layout).
2. **The base without it** is the BI base: the base's mode offers no canvas, the rail's Apps area hides, the
   Workbench sends no document to /streamlit and offers no New Streamlit app, a `.stapp.json` says which
   extension opens it, a Python cell that calls Streamlit is a plain cell, a new BI project has no canvas and
   no Streamlit requirement, a `streamlit` project is refused plainly, the agent's streamlit_* tools are not
   listed and a call names the extension (`extensions_install id=streamlit`), and the door (/streamlit/...)
   answers 404 naming it (every catalog extension that is off answers so on /<id>/...).
3. **With it** everything is as before (the full suite runs with it on: tests/conftest.py puts its src on the
   path and in PYTHONPATH and adds `streamlit` to SWISSARMYBENCH_EXTENSIONS before the app is imported).
4. **Preinstalled:** the installers download (or find beside a given wheel) `swissarmybench_streamlit-<v>-...whl`
   and install it `--with` the base; build.py already builds every extension's wheel and release.yml attaches
   dist/* (the install jobs find it beside the base's wheel; tools/smoke_install.py checks it is installed,
   its project type is offered and its routes answer). The catalog lists Streamlit **installed**, marked
   `preinstalled` (the card says Preinstalled), with Remove (asked first); removed, it is **available** again.
   Every update keeps it (`--with` its wheel). An update from 0.0.17 (Streamlit built in, its updater knows
   nothing of the package) brings it back at the new version's first start: `bring_back()` installs it once
   through the same helper (the app restarts), unless the user removed it (extensions.json `removed`) or it was
   tried at this version (`tried`).

**Decisions:**
- **What stayed in the base:** domain/streamlit_use.py (kernels and data.py ask "does this cell call
  Streamlit"), server/streamlit_proxy.py (a generic live-page proxy: the Power Apps extension mounts it too; its
  secret path is now each extension's SECRET_PATHS, the guard names none), and a new domain/cell_facts.py (a
  cell's body, title, facts, widget calls, indented: lineage, script export and data.py use them; the
  extension's streamlit_cells imports them). The Session page's words for the canvas's audit entries stay in
  domain/session_log.py (they only describe entries). domain/projects.py keeps the Save as zip's README text.
- **The base's hooks** (services/hooks.py): the open documents the windows hold, unsaved titles, `held`, a
  canvas, a playing page's notes, kernel_stopped, stop_orphans, canvas_references, the Workbench's app file,
  the cells shown live, a BI project's app. Every one has a plain default; the extension fills them in its
  routes(). data.ipynb -> data.py moved out of the Streamlit service into the base (services/data_export.py).
- **The open documents' registry is still the Streamlit service's** (windows send their cells to
  /streamlit/apps). Without the extension the base reads saved files: data.py from the saved data.ipynb, the
  Connections page's references from the recent files, lineage from the files. Moving that registry to a base
  route is front-end work of its own (the manifest boundary).
- **The BI project's canvas while the extension is on:** today's app offered the Streamlit canvas in every
  project (BASE_MODE's canvases). The extension declares `BASE_MODE_ADDS = {"canvases": ["streamlit"]}` and
  extensions.base_mode() adds it, so nothing changed for a user with it; the base's own BASE_MODE has none.
- **Bring-back at first start rather than at the old version's update:** 0.0.17's updater cannot know the
  package; a PyPI dependency cannot point at a GitHub release wheel. A copy that is not a uv tool never does it.

**Open:** a front-end manifest of what is on (the rail asks `/app/modes` for the canvas kind today); the
Session words and the zip README could move into the package when the manifest boundary lands.

## The Power Apps extension, phase 2: the data notebook on Deno (the owner, 2026-11-17; built, branch ext-powerapps-2)

The owner: "we can use Dataverse to get the grids and transform the data with typescript ... Then we just get
a data notebook with SQL and typescript cells ... on the back of duck db"; "build the other extensions as well".

**Built:** a code app's data notebook (`data.ipynb` in the code app's folder): TypeScript, SQL and TSX cells;
Open as grid of any table result; data.ts and Use in app; TSX previews; Dataverse sources into grids; the
agent's `powerapps_notebook`, `powerapps_ts_run`, `powerapps_ts_grid`, `powerapps_data_ts`,
`powerapps_tsx_preview`, `powerapps_dataverse_grid`. Extension: domain `ts_notebook.py`, `data_ts.py`,
`tsx_preview.py`; services `notebook.py`; adapters `deno_kernel.py`, `notebook_files.py`. Base: two cell kinds
in `domain/notebooks.py` (`typescript`, `tsx`: OTHER_KERNEL), a mode field `cell_routes` (extensions.py), and
in `web/` the generic `routedCells.ts` with the notebook, outputs, modes and Code App page wired to it.

**Decisions:**
1. **One Deno kernel per notebook runs both TypeScript and SQL** (`deno jupyter --kernel`, driven by
   jupyter_client as the base's kernels are), so the two kinds share one DuckDB (`@duckdb/node-api` 2.0.0-r.1,
   the same DuckDB 2.0 as the app's Python): a SQL cell is `await sab.sql("...")` in that kernel. A SQL cell
   with a connection of its own (`%%sql Warehouse`) still runs in the Python kernel, in the database's SQL.
2. **The mode says where a kind runs, as data** (`MODE["cell_routes"]`: name, language, run, preview, grid,
   types, install). The front end never names the extension: `routedCells.ts` posts to the routes the mode
   declared, and a kind with no route is not offered (or said plainly when a notebook has one).
3. **The kernel's `sab`:** `sab.sql` (a string, or a tagged template whose values are bound as `$p1...`
   parameters, never written into the SQL), `sab.table(name, rows)` (an array of objects as a DuckDB table,
   through a JSON-lines file in the notebook's temporary folder), `sab.tables()`, `sab.db`. A table result
   is one MIME bundle (`application/vnd.swissarmybench.table+json`: columns, DuckDB's types, the first 200
   rows, the total, an id) drawn as a plain table (data, never markup).
4. **The open tables** (a tab in the grid, after its steps) are views by their names over Parquet files in
   the notebook's temporary folder, written again only when one changed (the Streamlit run's mark); never
   in the project. The Python kernel's Tables group is not made in such a notebook (its tables are views).
5. **Connections' tables:** a query naming `[Connection].table` asks this server first through the kernel's
   own route (`/powerapps/notebook/prepare/<key>`: a secret path like Run live's, the key per notebook, no
   token in the kernel); the base's `connection_tables.prepare` reads each table and the extension writes it
   as Parquet beside the views.
6. **Open as grid** writes the result whole by its id (`COPY (...) TO ... (FORMAT parquet)` in the kernel),
   read here and stored as a table; the file is removed. Only an id of the form `r<n>` is accepted.
7. **Errors:** Deno's error record plus the error panel's detail in the base's shape (a frame per
   `<anonymous>:line:col` in the cell, a ReferenceError's "Run the cell that makes ...", a DuckDB error's
   place by the base's `sql_position`, DuckDB 2.0's "Table with name X does not exist" read too).
8. **Editor:** TypeScript and TSX cells use Monaco's own TypeScript service (the phase 1 worker), the
   kernel's `sab` declared from the route `types`; each cell is a script, so a name one cell declares is
   known in the next; top-level await and a name declared again are not flagged.
9. **data.ts** (Use in app writes `src/shared/data.ts`, since the pages addendum below): each TypeScript cell's top-level declarations exported in
   the notebook's order; a cell using the kernel (`sab.`, `Deno.`, DuckDB, a `jsr:` import) left in the
   notebook with a comment; `npm:pkg@x` imports made the package's plain name, gathered once; typed results:
   each name a cell made that holds a table result now (asked of the kernel) gets `XRow` and `X = XRow[]`
   from DuckDB's types as JSON reads them (BIGINT, DECIMAL and dates as strings). It reads the notebook as
   saved (the agent's and the page's), or the cells sent. Since the constraint below: also SOURCES and small
   results as constants, and never anything that imports DuckDB.
10. **TSX previews:** the cell's default export bundled by `deno bundle` for the browser (no remote, no npm
    downloads; a deno.json in the temporary folder resolves `react` and `react-dom` to the project's own
    node_modules, JSX for React's automatic runtime), one document with the props inline, shown in the HTML
    cells' design frame (design.html, its FRAME_POLICY: nothing over the network). Props: the first line's
    `// props: {...}`, worked out in the notebook's kernel and passed as JSON.
11. **Dataverse into grids:** a Dataverse source's environment address is the environment's URL (`pac env
    list`, listed once if not yet); the library's Dataverse connection whose `url` has that host opens the
    table through the base's Open (TDS where the connection uses the SQL endpoint); with none, the answer
    names the connection to add.
12. **Deno is a tool like the others now** (Install on the strip): Linux installs with `npm install --global
    deno` (Deno's own page lists npm everywhere; it runs without a shell). `DENO_NO_PACKAGE_JSON=1` for the
    kernel: the code app's package.json is the app's, and read, Deno refuses every npm: specifier it does not
    list.

**The connector bridge (phase 2's first route from the spike): not built, on purpose.** A bridge inside the
running app would have to take requests from this server while the app runs under Local Play, which is
`make.powerapps.com` in the user's own browser: that page reaching `http://127.0.0.1:<port>` crosses Private
Network Access (a public page asking a local address needs a preflight this server would have to answer
with `Access-Control-Allow-Private-Network` and an allowed origin of Microsoft's), and the bridge would then
let any process that can reach it make the user's signed-in app call any connector operation. That opens
the server to an outside origin (the posture: our own Origin only) and hands out the user's connector
access; neither can be checked without a tenant. Dataverse from the notebook goes through the Dataverse
connection instead (route b), which is built.

**Open:** the Workbench's kernel controls (Interrupt, Restart, the status bar's kernel) act on the Python
kernel; the Deno kernel's are the agent's `powerapps_notebook` and end with the server. A notebook closed in
the Workbench keeps its Deno kernel until the server stops. TSX blades bound to Dataverse, TypeScript
functions and canvas apps remain later work.

### Phase 2, addendum: the files a code app shows, and its pages (the owner, 2026-11-17; built, branch ext-powerapps-2)

The owner: "I want the agent to understand that it should survey the generated project code and the project
template is going to expose only the files that have to be touched in the code app. Everything else makes it
into the project folder but does not need to be exposed in the app, only .ts files." Then: "Right now I develop
react by treating each page as a lane. We should do the same", and "Lanes should be pages". (A first scaffold
shaped otherwise was held and dropped: "I don't want to pretend react is streamlit though.")

**The survey (2026-11-17):** Microsoft's template copied for real (`npx degit
github:microsoft/PowerAppsCodeApps/templates/vite`; degit fell back to a git clone) and its packages installed
(`npm install`: React 19.2, TypeScript 5.9, Vite 7, `@microsoft/power-apps` and its Vite plugin); `pa app init`
and `pa app add data-source` from their documented output (no tenant here: the recorded stand-in).

| File | Made by | Shown | Why |
|---|---|---|---|
| `src/App.tsx` | template | yes | the app's root: the page switcher |
| `src/pages.ts`, `src/pages/<Page>/**` | the starter files, New page | yes | where a person works |
| `src/shared/**` (`.ts`, `.tsx`) | the starter files, Use in app (`data.ts`) | yes | what pages share |
| `src/main.tsx` | template | no | the entry: renders App, never changed |
| `src/App.css`, `src/index.css`, `src/assets/react.svg`, `public/vite.svg` | template | no | the template's demo look |
| `index.html` | template | no | the page Vite serves; only its title changes, rarely |
| `package.json`, `package-lock.json` | template, npm | no | packages: npm's |
| `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, `vite.config.ts`, `eslint.config.js` | template | no | build settings |
| `.gitignore`, `README.md` | template | no | Git's and the template's |
| `power.config.json` | `pa app init`, data sources | no | pa owns it |
| `src/generated/models/*Model.ts`, `src/generated/services/*Service.ts` | `pa app add data-source` | no | written again on every refresh; read by the pages' hooks |
| `.power/schemas/**` | `pa app add data-source` | no | pa's downloads |
| `.sab/project.json`, `data.ipynb` | this app | no (the notebook opens from Data notebook) | the app's own |
| `node_modules/`, `dist/` | npm, the build | no | never listed |
| any other `.ts` outside pages and shared | a person | no | listed with Show all files; pages and shared are the places |

**Built:**
1. **Shown, not moved:** the Code App page's file tree, the Workbench's project files (the mode's
   `project_files` route) and the agent's `powerapps_files` list only the shown set; everything else stays in
   the folder for Git, VS Code and pa. A quiet "Show all files" (off at each start; the agent's `all=true`)
   lists the rest; a hidden file is read by its path.
2. **Pages** (domain/pages.py): `src/pages/<Page>/` with `<Page>Page.tsx` (the root: its state in useReducer,
   handed down by props), `components/` (only this page's), `hooks/` (`use<Page>`: loading, error and refresh,
   over the generated service when it is named, else made-up rows), `state.ts` (the page's reducer, never
   app-wide), `types.ts`, `index.ts` (its one public face: the page and its entry). `src/pages.ts` is the list
   of pages; App.tsx draws a button per page and the chosen one below (no router). `src/shared/` holds what
   pages share: the Page type, `useLoad`, `DataTable`, `FormField`, the app's context (signed-in user,
   environment), and `data.ts` (Use in app writes it there now: the notebook's fixed results, never the data
   layer).
3. **The starter files** at New code app (`powerapps_scaffold` again for an older app): src/shared, the
   Accounts page, src/pages.ts and App.tsx's switcher; each only where no file is (a person's App.tsx is kept;
   the template's own is replaced).
4. **New page** (the Code App page's button, `powerapps_pages(name, source?)`): the folder, its line in
   src/pages.ts, opened in the Workbench.
5. **The rule:** a page importing another page's code (or a shared file importing a page) is flagged in the
   editor as it is typed (`/powerapps/project/lint`, `powerapps_lint`), with the fix "Move it to
   src/shared/".
6. **Starters** (families React and TypeScript): React page, Hook over a generated service, Page reducer,
   Shared component, Form with state.
7. **Defaults, each in one place to swap:** hand-written hooks (no query library), the switcher in App.tsx (no
   router), plain controlled inputs (no form library), no new package. The template's own TypeScript settings
   (verbatimModuleSyntax, erasableSyntaxOnly, noUnusedLocals) and ESLint (react-hooks, react-refresh) pass the
   starter files and a new page over a generated service (checked with the installed template).
8. The generated service's read-all method is read from its file (`getAll`; Microsoft's docs also show
   `getall`); a service without one (a connector's actions) gives a page with made-up rows.

### Phase 2, constraint: nothing the app ships imports DuckDB (the owner, 2026-11-17)

The owner: "I can't change the code apps security policy." Source: Microsoft Learn, **How to: Configure Content
Security Policy** for code apps (learn.microsoft.com/power-apps/developer/code-apps/how-to/content-security-policy,
ms.date 2026-04-07): enforced by default, set per environment by its administrator; the defaults include
`script-src 'self' <platform>`, `worker-src 'none'`, `child-src 'none'`, `connect-src 'none'`. DuckDB-Wasm needs
a worker and WebAssembly past that, and DuckDB's Node package (`@duckdb/node-api`) does not run in a browser
at all. (The enforcement date the coordinator gave, 2026-01-30, is not on the page.)

**Decided:**
1. The data notebook keeps DuckDB: its TypeScript and SQL cells run on Deno with `@duckdb/node-api` (the
   notebook's own engine for exploring and transforming).
2. **data.ts (src/shared/data.ts) is plain TypeScript:** the result types (interfaces from the notebook's
   result tables' columns); `SOURCES`, where each result comes from (the tables its query read, the app's
   Dataverse sources marked: a page's hook reads them itself); small fixed results as constants (lookup
   tables, at most 50 rows and 20,000 characters of JSON), and a bigger one said plainly (a comment, and
   `left` in the answer). Never the query, and no SQL translated into TypeScript.
3. A cell importing DuckDB (any specifier naming duckdb) or a `.wasm` file stays in the notebook, and
   `data_ts.no_duckdb` refuses a data.ts that would still name one. An `enum` stays too (the template builds
   with `erasableSyntaxOnly`).
4. Tests: no data.ts and no starter file contains a DuckDB import; the template's own tsc (its browser
   settings) builds the starter files with a data.ts holding types, SOURCES and a constant.

**Open (the owner is choosing):** how transformed results reach the app. Not built.

## The system's own file dialog, and a better page picker (the owner, 2026-11-17; built, branch file-dialogs)

"the file picker for the entire app is terrible". The app runs on the user's own computer, so the server opens
the operating system's own dialog on the user's click and answers the real path.

- **One door.** Every pick goes through fileChooser.ts's chooseFile (a test checks no other module lists folders):
  it asks GET /dialogs once per page; when system dialogs open, POST /dialogs/choose and nothing of the page's
  shows (a cancel is null; a second click while one is open says "A file dialog is already open"); an answer of
  `unavailable` (the dialog's process failed) falls back to the page's picker for the rest of that page.
- **Per system** (domain/file_dialogs.py; server/dialog_runner.py runs it, ten minutes at most, one at a time):
  Windows: Tk first (uv's Python ships Tk; since Tk 8.6 its dialogs are the modern IFileDialog; DPI-aware,
  `-topmost`), else PowerShell (Windows Forms' Open and Save dialogs owned by a hidden topmost form;
  IFileOpenDialog with FOS_PICKFOLDERS for folders, never the old FolderBrowserDialog tree). macOS: osascript's
  choose file / choose folder / choose file name after `activate` (NSOpenPanel and NSSavePanel; no Tk dock icon),
  else Tk. Linux: kdialog on KDE, else zenity, else kdialog, else Tk; nothing without DISPLAY or WAYLAND_DISPLAY.
  The values travel as arguments or an environment variable (JSON), never in a script's text.
  `SWISSARMYBENCH_SYSTEM_DIALOGS=off` turns them off (the tests set it: the page's own picker everywhere).
- **The user's own.** POST /dialogs/choose is 403 for the agent, like Show in folder; every command takes a path,
  `files_list` finds one, `files_new_folder` is New folder's command (the golden rule). GET /dialogs and POST
  /dialogs/recent are page plumbing (NOT_COMMANDS).
- **The page's picker, made good:** places down the side (Home, Desktop, Documents, Downloads where they are, XDG's
  names on Linux, OneDrive's on Windows; Projects; Library; Recent; Drives), a clickable breadcrumb and the path
  box, Filter as you type, folders then files with modified date and size, New folder (folder and save picks),
  Hidden files (dot names; Windows' hidden attribute), a click selects and a double-click (or Enter) opens or
  picks, arrows, Home, End, Backspace up, Escape closes; a missing start folder shows the nearest that is there.
  Single-click no longer picks a file (the tests double-click now).
- **Recent folders per kind of pick** (`file:.csv,.xlsx`, `folder`, `save`; a caller may name its own `kind`):
  dialogs.json in the state folder, eight per kind, forty kinds, paths only; a system dialog's pick is remembered
  by the server, a page pick by POST /dialogs/recent.
- Left as they were: the three browser `<input type=file>` uploads (a blade import, a tang import, a theme
  import): they send bytes, not a path, and the browser's own dialog is already the system's.

## The blade screen: code read-only, a table name of its own, no catalog checkbox or panel (the owner, 2026-11-17; built, branch blade-screen)

The owner, on a starter's screen ("SharePoint document as a table"): "Shouldnt the table it makes be namable
by me with a realtime check for available names" (chose "a table name of its own"); "also that code box
should be bigger autosize and be formated" / "the code box is read only though blades can only be edited in
the folder not from the app"; "what the heck does add to catalog do, all blades should be in the catalog
already"; then "and yea we dont even need catalog if its just tables, we handle that in the variable page
already".

### Built
- **The code is read-only, for every blade.** The screen (bladeEditor.ts) shows it in Monaco (its language's
  colours, line numbers, no typing), as tall as the code: 4 lines at least, about 70% of the window at most,
  then it scrolls; wide lines scroll sideways (codeEditor.ts's new `fit` option). Under it the file's path
  and **Show its file** (server/file_manager.py `reveal`: Explorer's /select, the Finder's -R, else the
  folder; the user's click, 403 for the agent, in NOT_COMMANDS); a starter's or a pack's: **Copy as your own**.
- **Removed:** the code box's editing, the Kind switch, the Settings fields that wrote into the code
  (/blades/fill stays: it saves nothing, and the Connections forms use it), Save and refresh the catalog, Save
  and test, Save a copy, the template picker's Paste my own code and the "Keep it in" choice. PUT
  /blades/{name} changes the file's header only (name, description, tags, table); anything else sent must be
  as it is, else 400 "<name>'s code is edited in its file (<path>), never in the app". Agent commands:
  **blades_create removed** (it saved code); **blades_update narrowed** (name, new_name, description, tags,
  table: no code, kind, dialect, catalog, vault mapping); **blades_new added** (a file from a template; no
  template: the choices); **blades_table_name_check added**. POST /blades stays as the HTTP door that
  creates a blade with its code (tests and the import's own path use it; no page or command sends code to it).
- **New blade** (the left panel): A table (a DataFrame), Any code, Secret blade, Snippet (Markdown), and the
  analysis starters; the file is made in the library's blades/ and shown in its folder. Connections are made
  on the Connections page. A file edited outside shows at once (the store reads a file again when its time or
  size changes).
- **Its table is called** (domain/blade_tables.py): for kind "other" that is no connection and no web call;
  `table = "..."` in the header (domain/blades.py `with_header` rewrites the header, the bytes after it as they
  were, CRLF too; a save that changes nothing writes nothing). The live check, GET
  /blades/table-name?name=&blade= (debounced 250 ms on the page): a dataset name's rule, DuckDB's reserved
  words (keyword_category 'reserved', SqlGrammar.reserved), other blades' table names, connections' names
  (not vaults), the open tables; any case. Save refuses with the same words; so does New blade with a table.
- **Where the name lands:** `sab.blade(...)` (client/blades_client.py) in Jupyter, IPython or a Workbench kernel
  makes its result the variable of that name (a function blade's each time it is called, `functools.wraps`):
  DuckDB SQL (%%sql, sab.sql read the namespace's DataFrames by name), the Variables panel, and the Open list
  (the watcher, so Open as grid names the grid so). The Data Explorer lists it as a result under that name
  (its SQL insert the name). There was no other place: no app path opens a blade's result as a grid by itself.
  The spec (/blades/{name}/python, client/standalone.py) carries `table`.
- **No catalog checkbox.** A connection's listing query is shown read-only in a folded **How its tables are
  listed**; function, code and snippet blades have none. A connection saved with no listing query gets its
  starter's (by template, else the dialect's first database starter) as the store reads it (BladeStore
  `listing`, from bootstrap); nothing is written until the connection is next saved.
- **No catalog panel on the blades page** (catalogPage.ts, catalog.html): its picker, search, tree, table
  views and their addresses (?catalog=…) went, and app_navigate's `catalog:<name>/<schema>/<table>` places.
  Kept: services/catalogs.py, catalog_loading.py, adapters/catalogs.py, every `catalog_*` command (other
  features and the agent read loaded catalogs), and the Workbench's "+ Table" catalog tree (catalogRail.ts
  draws it only where a page gives `catalogHost`).

### Decisions
- Folder blades and an API's blades are header-edited in their own files; Remove shows only for files the app
  keeps (the library's): a blade folder's file is the user's to delete.
- Other blades' default names (their variables) do not count as taken: only names set in a header.
- The Workbench's "+ Table" catalog tree stays (it is not the blades page); worth asking the owner.

### Next
- The images 20-catalog.png and 21-blade-save.png in the user guide are no longer referenced: new screenshots.

## Relationship sets, and the Relationships window that manages them (the owner, 2026-11-17; built, branch relationship-sets)

The owner, on the "Relationships and tangs" dialog with about forty imported foreign keys: "drop tang its cheesy
and look at that form, I cant mass delete anything or manage those at all and they dont fit in the window". Then:
"and when a connection is delete from the app just remove the associated relationships it held".

**The name.** A tang is now a **relationship set** (in sentences "saved relationships", "a saved set"): it says
what it is, where tang needed the knife explained. The dialog is **Relationships**; its sections **Saved sets**,
**Find relationships**, **In use now**; **Save as tang** is **Save as a set…**. The file is
`<name>.relationships.json` (still one file per item, marked `"swissarmybench": "relationship-set"`, sorted as
before), in the library's `relationship-sets/` (was `tangs/`) and a pack's `relationship-sets/`. A save that
changes nothing but the time writes no byte (the library is a Git repository). Decisions:
- Renamed like the earlier renames: everything shown, written or listed uses the new words; the old ones answer
  for one release: `.tang` files (and the `"tang"` mark) read everywhere they were (library, shared folders, a
  pack's `tangs/`, an import, a project's `.sab/model.json`), the routes `POST /relationships/tangs` and
  `GET /relationships/tang`, the commands `relationships_save_tang`, `_export_tang`, `_import_tang` (OLD_NAMES:
  run, never listed), the arguments `relationships_check(tang=)` and `packs_add(tangs=)` (OLD_ARGS, the `sab`
  dispatcher). The library's `tangs/` is written as `relationship-sets/` once at start, the old folder kept in
  `backup/before-relationship-sets-<date>/` and said once on the page; a file that does not read is only in the
  backup. A library pointed at a clone that still has `tangs/` reads it until that clone's own start moves it.
- Internal names kept the old word where renaming was churn only: none of the Python's public names did (read_set,
  write_set, RelationshipSetError, set_file_name); the tour's card is now **Saved set**; CSS classes are `set-*`.
- `relationships_library` and `relationships_apply_library` kept their names (no "tang" in them).

**The window.** In use now is a manager: a checkbox per row, Select all (of the filtered rows), shift-click
ranges, the count ("12 selected"), **Delete selected**, **Run on** and **Run off** for the selection, Kind
(many-to-one, one-to-one, one-to-many, many-to-many) and Run changed in place, a row's ⋯ menu (Run on/off,
Delete), a filter by table or column, sort by any column (a third click: the order they came in), **Group by
From table**. Every change has one **Undo** in its toast, which puts back all of that change (the server keeps
the last 20 states of the joins in use: delete, edit, apply and import each push one). Decisions:
- **Run** is `active` (whether a join is used; Power BI's inactive relationship), as the brief asked; the old
  Run column (the check against the open tables) is **Check**, and the saved sets' Run button is **Check** too,
  so one word does not mean two things.
- Fits the window: a fixed table layout, the names cut in the middle (forty foreign keys differ at their ends:
  `gen…_line_07`), all of each in its tooltip; the table scrolls up and down inside the dialog, never sideways;
  under 960px the Note column steps aside (it is in the Check tooltip) and the toolbar's and footer's words
  fold to icons (design principle 3.6). Tested at 700px and 1600px: scrollWidth <= clientWidth for the dialog,
  its body, the table's box and the footer, and the dialog inside the viewport.
- A menu opened from a modal dialog now lives inside it (dom.ts showMenu, as the toasts already did): before,
  the page around a modal was inert and the menu could not be clicked.
- Saved sets: Apply, Check, and a ⋯ menu with Rename…, Export, Delete. A pack's or built-in set says why it
  cannot be renamed or deleted here (it changes in its repository).
- The agent: `relationships_delete(joins)`, `relationships_update(joins, kind, active)`, `relationships_undo`,
  `relationships_save_set`, `relationships_export_set(name?)`, `relationships_import_set`,
  `relationships_rename_set`, `relationships_delete_set` (waits for the user's Allow: it deletes the user's file).
  Filter, sort and group are views of `relationships_get`'s answer, so they have no command of their own.

**A deleted connection's relationships.** Deleting a connection (the Connections page's Remove, `blades_delete`)
takes out of the joins in use every one to or from a table the connection brought: a table whose recorded source
is the connection (`connection:<name>` for a database's foreign keys, `<name>/<dataset> (Power BI)` for a
dataset's), or, with no recorded source, one of the open tables read from it (ConnectionSwap.tables_of). Those
tables' keys and sources go too. The delete's answer carries `relationships_removed`, the page's toast says
"Removed 40 relationships that came from <name>.", and the ERD redraws on the server's notice. Saved sets are
the user's files: left alone. `relationships_undo` puts the joins back (the connection itself is not restored).

**The ERD draws the tables the project uses.** The owner (2026-11-17): "Relationships should filter the erd to
only the tables that are being used in the project": importing a connection's foreign keys drew all forty of its
tables. With a project open, a table is **used** when it is open, is one of the project's tables
(`.sab/project.json`), or its name stands as a word in one of the project's documents' code (a notebook's cell
sources, never its outputs; a script as it is): `%%sql` and `%%dax` cells, `sab.sql`, `sab.read`,
`sab.connection` calls, `[FI-Atlas].gl_entry`, `dbo.Vendor` for a table opened as `dbo_Vendor`
(domain/relationships.py named_in, code_of; services/relationship_scope.py). A relationship is drawn when both
its ends are used; the model keeps every one (the ERD's FK marks follow the drawn joins only). Decisions:
- Words, not a SQL parse: one rule for SQL, DAX and Python, and a cell that does not parse still counts. A word
  that happens to be a table's name shows that table: a false "used" is a box too many, never a lost join.
- **Tables in this project** (the default) / **All tables**: a switch on the ERD with the count of the hidden
  ones by connection ("34 more tables from FI-Atlas are not used in this project.", from the tables' recorded
  source), and the same switch over **In use now** in the Relationships window. With no project open the ERD
  is as before (the open tables, else the whole model) and no switch shows.
- The agent: `erd_text` and `erd_draw` take `scope` (project, the default, or all), `GET /relationships/erd?scope=`
  and `relationships_scope` (`GET /relationships/scope`) answer which tables are used and hidden.


## Drivers that run anywhere, and "Only works on your machine" (the owner, 2026-11-17; built, branch drivers)

The owner's words: "its odbc" / "odbc does not work on function apps" / "this is the wrong type of connectors";
"We need both Python-TDS for Dataverse and mssql for azure and sql server connections"; "any connector that does
not scale to a function app needs to carry a warning that it will only work on your machine"; widened: "save
that rule, we want to advise against any connectors that only work locally for the user, this is meant to scale
to a function app or up to a hosted streamlit application". The owner approved the two packages (mssql-python,
python-tds); they are the connections' own, as pyodbc was (PIP_NAMES, the missing-package prompt), never the
app's dependency.

### Built
- **SQL Server and Azure SQL on mssql-python.** domain/sql_server.py's SqlServer imports only `mssql_python`
  (Microsoft's driver, its own ODBC driver inside the wheel: nothing installed by hand, Linux included). No
  driver lookup, no ODBC Driver 18 preference, no winget/brew/apt prompt, no Driver option or choice. Its
  connection string uses only the keys mssql-python takes (it refuses any other: a test holds them to its
  list). The Entra token goes beside it as before (attrs_before 1256); ActiveDirectoryDefault and
  ActiveDirectoryPassword are the driver's own; Windows is Trusted_Connection. Its Arrow batches
  (`cursor.arrow_batch`) are read and cast to the same types the rows' path makes (UTC instants, time in
  microseconds, plain strings and bytes); a column its Arrow cannot read (sql_variant) falls back to the rows,
  read again. Cancel: mssql-python's cursor has no cancel(), so its statement handle's `_cancel()` (SQLCancel,
  safe from another thread) is called. An older code's `driver=` keyword is taken and ignored (`**older`).
- **Errors by their words.** mssql-python says "Driver Error: <the SQLSTATE's words>; DDBC Error: [Microsoft]
  [SQL Server]<the server's words>" with no native number. ERRORS keeps its numbers; WORDS maps each known
  number's words to it (Login failed, Cannot open database, the firewall's "is not allowed to access the
  server", "not currently available", the busy and throttling words, a deadlock, read-only); a dropped
  connection by its socket code in hex (0x2745, 0x2746, 0x274C) or "Communication link failure"; a server not
  found by 0x2AF9/0x2AFA. The same words make a passing error (`transient`, `passing`, write_sql's
  TRANSIENT_WORDS), so the retries and the serverless wait work as before. A missing mssql-python is the
  import's own ModuleNotFoundError (never wrapped), which the Install prompt reads.
- **Writes.** client/write_sql.py knows `mssql_python` connections as SQL Server; executemany binds arrays by
  itself (no fast_executemany; it is set only on an older pyodbc connection); mssql-python takes a type for
  every parameter or none, so input_sizes fills the ones pyodbc left to the driver (bit, ints, floats, money,
  date, datetime; uniqueidentifier and datetimeoffset as their text), and clears them after the batches (it
  keeps them for the next statements). #temp staging, MERGE WITH (HOLDLOCK), whole-transaction retries: as
  before. write_to_sql_server.blade.py imports mssql_python.
- **Dataverse's SQL endpoint on python-tds.** `sql_connect` calls `pytds.connect(server, port=5558,
  cafile=certifi.where(), validate_host=True, access_token_callable=<the connection's token>, autocommit,
  login_timeout)`: TLS by pyOpenSSL against certifi's authorities (python-tds encrypts only with a cafile), the
  token by Entra's federated authentication. `?` marks become python-tds's `%s` (a literal % doubled, marks in
  quotes and brackets kept); a statement with no parameters is sent alone (python-tds %-formats any statement
  given a parameters tuple, an empty one too: found against a real server). Its packages: python-tds,
  pyOpenSSL, certifi (an export leaves them out when no SQL runs on it). tests/dataverse_tds_standin.py now
  stands in at `pytds.connect` with the real Dataverse code signing in at the Web API stand-in.
- **OneLake's SQL endpoint on mssql-python** (lakes.SQL_ENDPOINT, the shared TOKEN_CODE): a Fabric SQL endpoint
  is Azure SQL's kind of endpoint, so it follows "mssql for azure and sql server", not python-tds.
- **Update to the new driver.** `sql_server.is_old` knows the app's earlier starter code (its runtime with
  `import pyodbc` and `pyodbc.drivers()`); `upgraded` writes today's head (the way's imports, the runtime) and
  keeps the user's own lines after it (the credential, `conn = SqlServer(...)` with every setting) but the
  `driver=` line. Golden files: tests/golden/sql_server/old_*.txt, new_*.txt, code_*.txt. The card says
  `update_driver`; its page has **Update to the new driver** (POST /connections/{name}/update-driver; the
  agent's `connections_update_driver`). A connection of the user's own code is refused, never rewritten.
- **domain/portability.py**: LocalOnly(key, reason, instead) and its words, "Only works on your machine:
  <reason>. On a Function App or hosted Streamlit app use <instead>." Rules by kind (odbc, access, sybase; a
  file kind whose path is not a web or cloud address), by code (pyodbc imported, Windows sign-in, a sign-in as
  you: Entra's interactive, Azure command line and VS Code credentials, Snowflake's externalbrowser; a
  certificate file, a certificate or keystore setting at a plain path, a local Delta folder, an AWS profile,
  the keyring read in code, a .env at a path) and by password source (the keyring). SQL Server's own code is
  judged by its `sign_in=` (its runtime holds every way's words).
- **Shown:** the form (the kind's `local` under its note; each sign-in's `local` beside the choice; the keyring's
  note when Saved on this computer is picked), the card (one amber line) and its page, a Write starter for those
  kinds (`blades_starters`' `local`, the Blades list's mark), the script export and the Streamlit extension's
  Export and Save as (`check: true` answers the notes; the page asks "Export it anyway?" before it writes; the
  agent's answer carries `local` and `local_words`). The agent's guide (connections.md) says the rule.
- **Portable defaults** (new connections only; a saved one keeps its code and its sources): SQL Server starts
  with SQL login, Azure SQL with an app registration whose secret is a vault's, Dataverse with the app
  registration, OneLake and the Data Lake with the app registration, Delta with Azure's app registration (the
  folder on this computer and an AWS profile last), Snowflake with a password from a vault (single sign-on in a
  browser is this computer's only), a new password from An environment variable (the keyring when chosen).

### Decisions
- SharePoint keeps its username and password (ROPC) first: the owner's own connection, and ROPC needs no
  desktop. The Azure Key Vault blade keeps DefaultAzureCredential first: without the browser it is a managed
  identity in Azure, so it runs there.
- Entra password (ActiveDirectoryPassword) and the driver's default are not flagged: neither needs this
  computer (the default needs azure-identity, which its code now imports so the Install prompt offers it).
- An exported script and a Streamlit export are still written when the user says so: the warning asks, it does
  not refuse (the agent's export writes and says it in its answer).
- BigQuery's `gcloud auth application-default login` and a Python connection's own code are not judged beyond
  the rules' words (a rule only says what it can tell from the code).

### Next
- A real Azure SQL, a Fabric SQL endpoint and a Dataverse TDS endpoint with Entra tokens: not reachable here.
- Fold mssql-python's `bulkcopy` (TDS bulk insert) into the Write starter for large appends.

## The project's outline: ARCHITECTURE.md (the owner, 2026-11-17; built, branch project-outline)

The owner: "The next logical step here is designing a way to easily export markdown context about a project.
Like a uniform export that outlines the project from an architectural standpoint". The owner's decisions:
written as **ARCHITECTURE.md at the project folder's top** (on Export, plus a download); written **for people
joining the project** (plain words, diagrams, a short summary per section, long lists folded); columns with
**names and types only** (never a number or value from the data: no row counts, no profiles).

### Built
- domain/project_outline.py (pure: facts in, text out) and services/project_outline.py (gathers them). The same
  eight sections in the same order every time; an empty one says "None.": Overview (name, type in its mode's
  words, purpose = README.md's first paragraph or "Not written yet", the folder as a text tree with each file's
  role, data.py and pages/*.py marked made), Data sources (each connection and API the project uses: type,
  sign-in, portability, the variables it needs by name and source, used by), Data model (each table it uses:
  where it comes from, columns by name and type, the relationships among them; a Mermaid `erDiagram`),
  Transformations (each table's steps in words and as one DuckDB query; data.ipynb's named cells: makes and
  reads), Lineage (one Mermaid `flowchart LR`: sources, tables, the named cells, the deliverables), Deliverables
  (notebooks, scripts, apps with their pages and the cells each block links, saved Visualizations dashboards),
  Running it (packages, scripts' run settings by variable name and source, a checklist for a Function App or a
  hosted Streamlit app), Open issues (tables to fix, passwords with no source here, local-only connections,
  the lint's errors and warnings per document).
- Deterministic: sorted, no timestamp, no version in its header; ARCHITECTURE.md is never in its own layout. Export
  writes it through SabArchive.write_state (atomic, only when its bytes change).
- GET /project/outline (text/markdown), POST /project/outline (writes; {file, path, written, text}); the agent's
  `project_outline` (`write: true` writes, as Export does; not destructive, no Allow). Export outline in the
  project's group of the Application row and the Workbench's project menu (`project.outline`); its toast offers
  Download. New project's README mentions Export outline in one line; the scaffold makes no ARCHITECTURE.md.
- An app's pages come through services/hooks.py (`app_pages`, filled by the Streamlit extension's
  `outline_pages`), so the base never names the extension.

### Seams (replaced at merge)
- A. `UsedTables.used(project: str) -> set[str]` (project = the folder): today ProjectTables: the open tables,
  .sab/project.json's tables, and the `[Connection].table` names its documents' DuckDB SQL names (SQL cells,
  and string constants in Python cells; read by sqlglot). The relationship-sets branch's notion replaces it.
- B. `Portability.verdict(connection: Mapping) -> {"portable": bool | None, "reason": str, "instead": str}`,
  `connection` = {name, kind, type, template, dialect, sign_in}. Today NotChecked: portable None, "Not checked
  yet" (no guessing). The drivers branch's rule replaces it; False lists the connection in Open issues and the
  checklist says "Only works on your machine: <reason>. On a Function App or hosted Streamlit app use <instead>."

### Decisions
- A table's source query text (a connection's SQL, a "+" tab's) is not written (as context.md); the grid's steps
  are, as the brief asks: their words (domain/steps.py's describe_step) and the DuckDB query, so a filter's
  typed value appears there. Rows, counts and profiles never do.
- Script arguments are counted, never written (their text may be a value).
- The lint is the app's own small one (domain/intellisense.py), never Ruff, so the count is the same on every
  computer; the open tables' names are known names.
- Data files (CSV, Excel) are not in the layout (the project's own files, as sab_files' `packed`); the tables
  that read them name them.

### Next
- Wire the two seams to the drivers and relationship-sets branches' rules.
- A table named only through `sab.sql("Shop", "...")` Python strings in a connection's own dialect is not yet a
  used table (only DuckDB SQL's `[Connection].table`).

## The meta store: a shared catalog, setup from it, local and shared projects (the owner, 2026-11-17/18; built, branch shared-catalog)

The owner's words: "My next idea is a shared meta store on GitHub. It would be a json or something in the back of
the app and any connection made in a project would save to a centralized catalog it would sync and prune in
realtime"; on how it syncs: "No you point the app to a GitHub meta store folder on your machine. You push and pull
as projects are created"; then (2026-11-18) "Connections are shared and the vault env vars are shared as well so
minimal setup is required for new people", "Meta store folder in settings. And we should introduce the idea of
local projects and shared projects and put another setting for shared projects folder in settings", and "work a
shared project and clone it into a local project". Git: the owner is still deciding whether the app runs it; until
then it does not (nothing here runs git, makes a network call or guesses git state).

### Built
- **The shared catalog: the library's `catalog/<connection>.json`** (domain/shared_catalog.py, adapters/ and
  services/shared_catalog.py). One file per connection (its name made file-safe as its blade's file is): kind
  (how it lists its tables) and starter; per table its database, schema, name, kind, columns (name, type,
  nullable, key: primary or foreign), primary key, the relationships whose from- (else to-) table it is,
  `used_by` (project folders' names, never paths) and `state` (present, or gone with `gone_since`, a date).
  Never a value: no row count, profile, relationship note or evidence (they can carry numbers from the data), no
  secret, no server address beyond the connection's own file.
- **Byte-stable, merge-friendly.** Sorted keys, one table per block, one column or relationship per line; no time
  that changes on every save. A test merges two people's independent additions with `git merge-file` (git in the
  test only) and gets exactly the file either would write with both. Known limit: two people adding tables that
  sort next to each other touch neighbouring lines (JSON's comma), which Git calls a conflict; the app then says
  so and waits (below).
- **Written on the event**, the user's and the agent's alike: a connection saved (BladeService.blade_saved); its
  tables listed successfully (BladeService.tables_listed: Refresh, a catalog loading itself, the Connections
  page's tree); the relationships in use changed (Models.listeners: "edit" takes a deleted relationship out,
  "replace" (a project's model) only adds); a project opened or saved (its folder's name into `used_by` of the
  tables it uses: open tables, its tables, names its documents' code says, relationship_scope's rule; out of the
  ones it no longer uses; other projects' names left alone). Written atomically, only when its bytes change.
- **Pruned.** A deleted connection's file goes (the hook that removes its relationships). A table a successful
  listing no longer finds is `gone` since today; still gone 30 days later (settings.shared_catalog_prune_days)
  it is removed. A failed listing (sign-in, offline) changes nothing.
- **Read again after a pull.** The folder's files' stamps are looked at every 3 s (no new dependency); a file
  changed from outside is read again, the pages told (`catalog_changed`), and the page says once "Catalog
  updated from the library: N connections changed". Settings shows the counts and "Last change picked up from
  the folder: <date>". A file with merge conflict markers or broken JSON is reported with its name and never
  written over until it reads (the user finishes the merge). The app does not guess git state.
- **Readers.** Explorer search and browse (a "From the shared catalog" section: a teammate's table "From the
  shared catalog: not connected here", or Set up this connection when its connection file came with the
  library); the ERD's All tables (`/relationships/erd?scope=all` merges the catalog's model under the one in
  use); context.md's "Shared catalog" section. Agent: `catalog_shared`, `catalog_shared_table`,
  `catalog_shared_refresh`.
- **Set up from the meta store** (domain/ and services/library_setup.py; Settings' Meta store folder section,
  GET /library/setup). Each key vault in vaults/ checked by its own names() in a child process (20 s at most):
  readable, or the sign-in that fixes it ("Sign in to Azure", how: az login, then Check again) and how many
  variables it gives ("Sign in to Azure gives 12 variables"); each value still needed here (a keyring variable,
  a local one, a connection's password with no source here: project_scope's rule), typed once inline (the
  keyring, local/variables.toml, the connection's own secret); each connection's status (works; needs a sign-in
  to <vault>, its password, a value; or only works on your machine, the portability rule's words); the shared
  projects whose connections are not set up here; the count ("3 things to set up", "Ready: 9 connections
  work"). A connection whose password is in this computer's keyring offers **Move to a vault** (a vault's new
  entry, the code reading it from there: the next person needs nothing). Said once when the meta store is
  pointed at a folder that already holds connections. Agent: `library_setup`, `library_setup_move_to_vault`;
  typing a secret's value stays the user's.
- **Meta store folder.** Settings' Library folder is labelled Meta store folder, with "Connections, key vaults,
  variables and the shared catalog: point it at your clone of the team's GitHub repository." A label only: the
  code, library.json and ~/.swissarmybench/library keep their names.
- **Local and shared projects.** Settings' Projects folder became two: Local projects folder (as before; the
  older `folder` key of projects.json read as it, written as `local_folder`) and Shared projects folder (none by
  default; a folder the user pushes and pulls with Git). The Project Explorer scans both; each card is Local or
  Shared (by which folder it is under; one opened from elsewhere is Local), filtered All / Local / Shared. New
  project asks Local or Shared (Shared offered once its folder is set). A local card's **Share** copies it into
  the shared folder (as Copy project to: never .sab/data/, its .git left behind, the original kept), then opens
  the copy (the agent's on Allow). A shared card's **Make a local copy** copies it into the local folder (no
  rows, no .git, the shared one untouched; a name taken asks for another), writes `copied_from` (the shared
  project's folder name) into its .sab/project.json, shown on the card, and opens it (no Allow: like New
  project). Opening or making a shared project whose connections only work on this machine says so once ("2
  connections in this shared project only work on your machine: teammates and a Function App can't use them").
  Agent: `projects_folders` (was projects_folder_set: read for one release), `project_share`,
  `project_copy_local`, `project_new(where="shared")`.

### Decisions
- JSON, as the brief said, rather than TOML (whose tables need no commas and would merge more cleanly still).
- The file's `kind` is how a connection lists its tables (connection_tables.tables_kind), so the catalog names a
  teammate's table in DuckDB SQL the way the connection would.
- A relationship lives in its from-table's block when that table is the connection's, else in its to-table's;
  the user's deletions are the only removals (a project closing never takes one out).
- `used_by` counts only this computer's connections for the open project (a teammate's same-named table is not
  marked used by a project here).
- "A project-only connection is offered Move to the meta store": since the library, a project holds no
  connection of its own (an older project's .sab/blades move in as it opens), so there is none to offer.

### Open
- Several meta stores at once (a personal one beside the team's) is the library plan's rule 5, not built.
- Whether the app runs git (pull and push buttons) is the owner's open decision.

## The GitHub Copilot extension: Copilot's code completion in the Workbench (the owner, 2026-11-18; built, branch ext-copilot)

The owner's words: "Wanted to GitHub Copilot repo code completion anyway". Chosen: **an extension, off until
installed**: a "GitHub Copilot" card on the Extensions page (one click Install, then sign in to Copilot); not
installed, nothing is sent; Settings has an On switch; Copilot is off for a project marked private.

**What it is built on.** GitHub publishes the **Copilot Language Server** for editors other than its own (npm
`@github/copilot-language-server`, repository github/copilot-language-server-release; read 2026-11-18 at 1.572.0).
Its licence is **MIT**; its use is under **GitHub Copilot's terms** (the README links the "GitHub Terms for
Additional Products and Features", GitHub Copilot section), and it needs a Copilot plan (Copilot Free counts).
Integrating it into an editor is what it is published for, so nothing here works around anything. The protocol,
followed as its README documents it: LSP (JSON-RPC 2.0 with Content-Length headers) over stdio (`--stdio`);
`initialize` with `initializationOptions.editorInfo` and `editorPluginInfo`, then `initialized`, then
`workspace/didChangeConfiguration` (and `workspace/configuration` answered); `textDocument/didOpen`, `didChange`
(incremental) and `didClose`, and the custom `textDocument/didFocus`; `signIn` (device flow: `userCode`,
`verificationUri`, the `github.copilot.finishDeviceFlow` command through `workspace/executeCommand`), `checkStatus`
(not in the README; in the server's method table: OK, MaybeOK, NotSignedIn, NotAuthorized), `signOut`;
`textDocument/inlineCompletion` with the README's additions (the version, `formattingOptions`), its items'
`command` run with `workspace/executeCommand` after an accept, `textDocument/didShowCompletion` and
`textDocument/didPartiallyAcceptCompletion` (the length from the item's start); `$/cancelRequest`. Its
`initialize` answer also lists `notebookDocumentSync` (notebook "*"): a notebook is sent as a notebook.

**Decisions.**
- **Backend only**, as every extension (CLAUDE.md's front/back rule): `extensions/copilot/` (`swissarmybench-copilot`,
  entry point `copilot`, on the base's version, its wheel on the release like the others; `available` in the
  catalog). The language server is never a Python dependency: the extension's own **Install the language server**
  runs `npm install --prefix <state>/copilot --ignore-scripts --save-exact @github/copilot-language-server@1.572.0`,
  and Node.js (20.8+, found as the Power Apps extension finds it, with the same missing-tool answer) runs
  `dist/language-server.js --stdio`. One server for the app, started when it is needed and on; it stops with the
  app, and when switched off.
- **The front end stays generic.** The modes carry `inline_completion` (each on extension's INLINE_COMPLETION: its
  name, languages and routes, as data, like `cell_routes`); `lazy/codeEditor.ts` registers Monaco's inline
  completions provider for Python and SQL and asks the declared route (debounce 250 ms; Monaco's cancellation aborts
  the fetch and posts `cancel`, which sends `$/cancelRequest`); shown, accepted (Monaco's end of lifetime: accepted)
  and partly accepted (Monaco's own count from the range's start, which is the server's) go back through `event`.
  Ghost text, Tab takes it, Esc lets it go (the notebook's Escape waits while ghost text shows), Ctrl+Right a word,
  Alt+] / Alt+[ cycle: Monaco's own keys, VS Code's. The status bar's "Completions: <name> · on/off" draws the
  name the backend gives; a click toggles. Nothing in web/ names Copilot. The Extensions card and Settings draw the
  extension's **panel** (GET /extensions lists its route): lines, switches, actions and a code with a page to open,
  as data (extensionPanel.ts), so the device flow's code is shown by generic code too.
- **The lazy editor is a bundle of its own** (esbuild without splitting): it cannot read modes.ts's state, so the
  Workbench hands each editor an `inlineSource` (ask, tell) instead of the editor importing it.
- **What is sent:** only the document being edited: a script's text, or a notebook's code cells (Python and SQL,
  the user's: not the read-only table cells) as one notebook with the cell being edited asked in. Never outputs,
  rows or variables' values. Addresses are made up (`file:///swissarmybench/<a key per window>/<file name>`); no
  workspace folder is sent, so the server has none of the user's folders to read. At most 20 documents are held;
  the oldest is closed for a new one.
- **Nothing is sent** before the server is installed, while off (the server is not even started; turning it off
  stops it), before sign-in, or for a project marked **private**: then not even a didOpen, and what was open is
  closed. `private: true` lives in `.sab/project.json` (an unknown field the manifest keeps), set by the project
  group's **Private** switch (POST /project/private; the agent's `project_private` waits for Allow).
- **Sign-in** is the server's own device flow, the user's only (403 for the agent; the agent's panel answer leaves
  the code out). The page opens github.com/login/device on the user's click, then the client runs
  `finishDeviceFlow`; the server's `window/showDocument` for the same page is answered success without opening
  anything (the client says it supports showDocument so the server does not open a browser itself). On success the
  switch is on. "Signed in, no plan" (NotAuthorized) is said plainly.
- **Telemetry off:** `telemetry.telemetryLevel: "off"` in the configuration (the server turns its telemetry on only
  for "all"), in both the notification and the `workspace/configuration` answer. The accept command and the
  shown/partial notifications are still sent, as the README asks (the server's own bookkeeping).
- **No token anywhere of ours:** the server keeps its own sign-in (GitHub's apps.json in its folder); copilot.json
  holds the switch and the login's name only; the server's stderr and `window/logMessage` are dropped, never
  logged; audit entries carry names and states only.
- **The agent:** `copilot_status` (installed, on, signed-in login, private, ready, the panel's words),
  `copilot_toggle`, `copilot_install` (Allow). Completions are the editor's: the agent has its own model and
  `workbench_complete`.

**Open.** The real server answering completions was not seen (no Copilot plan here); `textDocument/copilotSuggest`
(unified suggestions) and next edit suggestions are not used; GitHub Enterprise (`github-enterprise.uri`) and a
proxy setting are not offered; the notebook's cell addresses are `<notebook>#cell-<n>` (not VS Code's
vscode-notebook-cell scheme), which the server took in the stand-in only.


## GitHub sync and the Source Control page: the Git extension (the owner, 2026-11-18; built, branch github-sync)

The owner's words: "It would be neat if you were able to connect a local GitHub repo and push and pull and fork
projects so you could work a shared project and clone it into a local project"; chosen: **"Built-in, signed in to
GitHub"** (no Git needed on the computer: the app talks to GitHub's web API with the user's GitHub sign-in); "fork"
is a local copy (Make a local copy, built with the shared catalog). Then: "add a simple indicator at the bottom that
the project is out of sync"; "can we literally steal VS Code's panel for git with the graph and commit and show it
with a diff navigator on a new rail icon that shows up when you install the git extension"; "literally clone to
exactly no deviation" (VS Code is MIT: its code and look reused with its notice; Git Graph's code is not used).

**Why no Git:** a teammate on a locked-down laptop, a Function App, a hosted page: none can be asked to install Git,
and running a binary from the app is a second door to secure. GitHub's REST and Git Data APIs do everything the
meta store and shared projects need: a tree read, blobs, a commit on a base tree, the ref moved fast-forward.

**Built:**
- `extensions/git` (swissarmybench-git), available in the Extensions catalog (one click: Install). Off, none of it runs:
  no rail icon, no footer mark, no Settings section; its `github_`/`scm_` tools answer which extension they need.
  The front end draws its area from the backend (GET /app/areas: `{area, name, icon, mark}`), so web/ never
  names the extension (the plug-in page reads `/git/...` routes as the Code App page reads `/powerapps/...`).
- Sign-in: a fine-grained personal access token pasted once (the steps on the page), or **Sign in with GitHub**
  (the device flow) once the owner registers an OAuth App and fills `CLIENT_ID` in `extension.py` (empty: the
  button says to use a token). The token is the keyring's `SwissArmyBench / github/token` only; the login is kept
  in sync.json. Signing in and out are the user's (403 for the agent).
- Each folder (meta store, shared projects) cloned (into an empty or new folder, which Settings then points at) or
  connected (compared; nothing written: a file different on both sides comes as a conflict at the first Pull).
  The link lives in the state folder's `sync.json`, keyed by the folder's path (repository, branch, the last
  synced commit, each file's blob SHA: the three-way merge's base, the staged files, the conflicts): never in the
  repository, so nothing of the app's own state is pushed.
- Pull: theirs where only they changed; both changed: diff3 by lines (difflib), clean or a conflict (the local file
  kept, `<name>.theirs` beside it, listed; resolved by deleting the .theirs); deleted there and unchanged here goes,
  changed here stays (said). The shared catalog reads a pulled meta store at once.
- Push (and Commit): blobs, a tree on the head's tree, a commit, the ref PATCHed with force false: GitHub moved,
  Pull first (409); a conflict waiting, refused; a file that looks like it holds a secret (a keyring value of this
  computer's, a token's shape, a password literal), refused and named. `.gitignore` (every level), `local/` at the
  top, `.sab/data/` anywhere, `.git/` and `*.theirs` never go; a file over 50 MB is left out and said.
- Status words: Not connected, Up to date, 3 changes to push, 2 behind: Pull, Conflicts: 2 (Not pulled yet: Pull
  after Connect). GitHub is asked (the head, a compare) only on an action or when Settings, the Explorer or the page
  asks, at most once a minute per folder; the footer reads the cached answer and the files here: no polling.
- The footer's mark (`areaMarks.ts`, generic): "↑3 to push", "↓2 behind", "Conflicts: 2", amber, for the open
  project's shared folder (its own files), else the meta store; nothing when up to date, not connected or no
  project is open. Read again on `sync_changed` (Pull, Push, Commit, a save, an opened project).
- The Source Control page: VS Code's Source Control view and Source Control Graph, from VS Code's source (scm.css,
  scmHistory.ts's swimlanes, the git extension's menus, words, letters and colour keys; the Dark Modern and Light
  Modern colours; codicons from Monaco's font): the repositories (the meta store; the shared projects scoped to the
  open project), "Message (Ctrl+Enter to commit on "main")", ✓ Commit with Commit, Commit & Push, Commit & Sync,
  Merge Changes / Staged Changes / Changes with counts, each file's icon, name, greyed folder and letter
  (A M D U !), the inline actions (Open File, Discard Changes, Stage Changes / Unstage Changes), the menus (the
  view's "..." with Commit, Changes, Pull, Push, Branch, Remote, Stash, Tags, Worktrees), View as Tree / List,
  Discard's and smart commit's questions in VS Code's words, Sync Changes ↓N; the graph (lanes, the HEAD ring,
  main and origin/main labels, Incoming Changes, a commit's hover, its files opened under it, Load More...);
  Monaco's diff editor with VS Code's default diff options, F7 / Shift+F7, Inline View, the files beside it and
  Previous/Next File. Settings' GitHub section; a shared card's Pull and Push and its words; Share asks "Push
  <name> to GitHub now?".

**Deviations from VS Code (each needs a local Git repository the GitHub-API approach does not have), shown disabled
as VS Code shows a disabled command:** Commit (Amend) and its Staged/All forms, Commit (Signed Off) forms, Undo
Last Commit, Abort Rebase; Sync (Rebase), Pull (Rebase), Pull from..., Push to..., Fetch (Prune), Fetch From All
Remotes (in the "..." menu; the graph's Fetch button asks GitHub again); Merge..., Rebase Branch..., Create Branch
From..., Rename Branch..., Delete Branch..., Delete Remote Branch..., Publish Branch...; Remote (Add, Remove);
every Stash entry; Tags; Worktrees; Show Git Output; Checkout (Detached), Create Tag..., Cherry Pick and the three
Compare entries on a graph row; Add to .gitignore and Reveal in File Explorer View on a file; staging part of a
file (Stage Change in the diff). **Others, said plainly:** "Commit" goes straight to GitHub (no local commit, so
no "Sync Changes ↑N" after it; Commit and Commit & Push do the same); Open File says where the file is (files
are edited in their own editors); file icons are the codicon file glyph, not VS Code's Seti icon theme; the
message box is a textarea, not a Monaco editor; the side bar's views are not resizable against each other (the
sash between the side bar and the editor is); a commit's hover is the page's own, with the same facts. No
side-by-side screenshot with VS Code itself: no VS Code or code-server runs here; the values were taken from VS
Code's source (main branch, 2026-11-18).

**Open:** the OAuth App's client id (the owner registers it: Settings shows Sign in with GitHub once filled in);
GitHub's 100 MB push limit and LFS are not handled (50 MB is the API's per-file limit and the app's); a tree
GitHub truncates (over 100,000 entries) is refused, said.

## A desktop app? Stays in the browser (the owner, 2026-11-18)

The owner asked whether Swiss Army Bench should be a desktop app ("I still really want to build this as a desktop
app ... What did I gain by keeping it in a web browser"). Weighed: pywebview (the system's web engine) breaks
`window.open` pop-outs, dragging between windows, downloads, print to PDF and runs WebKit on Linux ("Pywebview
seems like it kills functionality"); Electron keeps everything (Chromium, as the tests use) at about 150 MB and an
installer per system; Tauri is small but has pywebview's gaps. The owner's call: "Just keep it as is". The app
stays a local server with browser pages; a desktop shell remains possible later as a thin layer (Electron) over
the same server and pages, with nothing rewritten.

## Swiss Army Bench as a desktop app on PySide6; the server's life follows the app; the tray gone (the owner, 2026-11-18; built, branch ext-desktop)

**The owner's words, in order.** After weighing pywebview ("seems like it kills functionality"), Electron, Tauri,
a native Rust shell and a PWA: "I like the pyside6. Can we just build it side by side here as an optional install
version?" Then, while it was built as an optional extension: "The thing that is giving me heartburn is how the
server has to be managed separate. I wanted the server to simply run while the app is active and shutdown when
it's not instead of all this crazy server background junk", with "Stay up while they're busy" for the agent, VS
Code and Python, and the tray and start at sign-in: "Remove them entirely". Then: "We should just package this as
the desktop app pyside6", and "Change that to the primary install. It's not an extension it is the app framework
now and it should have been since the start".

**The options weighed.** pywebview draws with the system's own engine (WebView2 on Windows, WebKit on macOS,
WebKitGTK on Linux): three engines, each with its own gaps (named windows, downloads, printing), the reason it
"kills functionality". Electron and Tauri are a second toolchain (Node.js or Rust) and a second runtime beside the
Python one, with an installer of their own. A PWA is still the browser's window and its rules. **PySide6 with Qt
WebEngine** is Chromium on every system (the engine the browser tests already run), installed with uv like
everything else, driven from Python in the app's own package: window.open, downloads, printing, permissions and
the profile are all in reach. Its cost is its size.

**Decisions (the app).**
- **The primary install, not an extension.** The shell first built as `extensions/desktop` (swissarmybench-desktop)
  moved into the base: domain/desktop.py (rules), adapters/desktop.py (its channel and record), services/desktop.py
  (desktop_status, desktop_open), server/desktop.py (starting it, telling it to open a page; no Qt),
  server/desktop_shell.py (the Qt app), routes_desktop.py. No catalog entry, no extension hooks.
- **PySide6 is the `[server]` extra's**, pinned: `PySide6-Essentials==6.12.0`, `PySide6-Addons==6.12.0`,
  `PySide6-WebEngine==6.12.0.140` (released 2026-10-08). Since 6.12 Qt WebEngine is a wheel of its own (WebEngine
  needs Addons, Addons needs Essentials); the `PySide6` meta-package would add `PySide6-Pdf`, unused. pystray and
  Pillow went with the tray. **Size** (Linux x86-64, Python 3.12, measured): the `[server]` install 499 MB before,
  1,146 MB after (PySide6 667 MB). Windows x64 downloads 82 + 41 + 132 MB. 6.12 has no Qt WebEngine for Windows on
  ARM (its WebEngine wheel is empty): there the browser opens.
- **Opening it:** `swissarmybench` (no arguments) and `swissarmybench open [folder]` open the app;
  `open --browser` (and the right-click menu's **Open in browser**, Ctrl+Shift+B) a browser tab on the same server.
  `swissarmybench start` runs the server and opens the app's window (`--no-window` not; `--no-browser` is its old
  name). VS Code's start (no command, SWISSARMYBENCH_STARTED_BY=vscode) and the older `swissarmybench --port N` stay
  the server only. Where the app cannot run (no display, no Qt WebEngine) the browser opens, as before.
- **The app is a process of its own**, one at a time (its lock, desktop.json): one QApplication, each page a
  QMainWindow with a QWebEngineView, all on one persistent profile in `desktop/profile`. It starts the server when
  none runs (`start --no-window`); a second start hands its page to the first. **The channel:** 127.0.0.1, a port the
  system picks and a fresh key, both in desktop.json (owner-only). One JSON line each way: `{"open": page}` or
  `{"status": true}`. The token never travels on it or on a command line: a page is its path and fragment without
  the token, and the app adds the running server's token from its connection file. Chosen over the live-updates
  socket because `swissarmybench open` and a starting app must reach it with no server running.
- **window.open** is QWebEnginePage.createWindow: a new app window. Named windows (nav.ts's `sab-home`,
  `swissarmybench-workbench`) are found by Chromium itself, as in a browser; a page's `focus()` of another window
  raises it (a small script the app adds to each page reports focus() and window.name on the console; nothing in
  web/). The app's own opens reuse the window named `sab-home` for the home page, or a window showing the same page.
- **Inside and outside:** only `http://127.0.0.1:<port>` (and about:blank, about:srcdoc, a blob: of that origin)
  loads inside; http, https and mailto elsewhere open in the system's browser; a frame that loads one by itself is
  refused; data: only in a frame; file:, javascript: and the rest refused. A window.open to elsewhere closes its
  empty window.
- **Permissions:** the clipboard for the app's origin only; every other permission denied, asked every time.
- **Downloads:** a Save dialog (QFileDialog, the suggested name, in Downloads), then the progress and **Show in
  folder**. **Print to PDF:** window.print() and Ctrl+P ask where, then printToPdf.
- **Keys** a browser had: F12 developer tools (a window of their own), F11 full screen, Alt+Left/Right back and
  forward, F5 and Ctrl+R reload, Ctrl+W close. **Closing a window asks its page first** (RequestClose: the
  Workbench's beforeunload says when work is unsaved). Window titles are the page's, never its address (Chromium's
  first title carries the token). Each kind of window remembers its size, place and maximized state.
- **File dialogs:** `/dialogs/choose` stays: on Windows it already is the system's IFileDialog (Tk's), on macOS the
  system's own, on Linux zenity or kdialog; a QFileDialog would show the same.
- **The launcher:** the installers add the app with its icon: Windows a Start menu shortcut to the tool's
  `pythonw.exe -m swissarmybench.server app` (no console; `-DesktopShortcut` a desktop one too; the .ico written by
  `swissarmybench icon`, made with the standard library); macOS `~/Applications/Swiss Army Bench.app`, a small
  bundle whose executable runs `swissarmybench` (no icon of its own yet); Linux a `.desktop` entry and an SVG icon
  in `~/.local/share`. They open the app once at the end (not with --no-start, on a build machine or with no
  display); `--uninstall` / `-Uninstall` removes the launcher and the tool.
- **Updates** are the pages' Update notice only. The helper waits for the server, ends the app (desktop.json's pid,
  `end_pids`), installs, and its start step (`start`) opens the new version's app. Chosen over the app reloading
  itself: the new version's Qt and code must be the ones running.

**Decisions (the server's life, services/lifecycle.py).**
- The app's windows are the pages' sockets on /ws (not VS Code's openers, not the agent's event socket). The last
  one closed: the server stops **30 s** later (a reload or a slow tab never ends it); before the first one,
  **120 s**; the desktop app's last window closed: at once (2 s), as it tells the server (POST /lifecycle/closed).
- A **client that is not a page** (each request with the token, not the pages' cookie: the agent, VS Code, a push,
  a kernel's report) keeps it up **10 minutes** after its last request with still no window. VS Code connected or a
  request under way (not a listener that waits by design) is **busy**: no stop. Settings (and
  SWISSARMYBENCH_LIFE_GRACE, _START_GRACE, _IDLE) hold the times; the test suite sets them to a day.
- **Unsaved work:** the stop first saves an open project with unsaved changes as Autosave does; with Autosave off
  it does not stop (`held`, said by app_lifecycle) until a window comes back and the user decides. Tables with no
  project are not held for (they came from files, connections and pushes); a Workbench window's unsaved document
  asks when its window closes.
- The agent, VS Code and a push do **not** start a server (as before this change: the client only connects; VS
  Code's extension starts it). The plain client stays standard library only with no process started.
- **The tray and start at sign-in are gone**: server/tray.py, server/autostart.py, /updates/tray, /autostart,
  app_autostart (an old call says it went), the tray's watchdog, pystray and Pillow. `swissarmybench tray`,
  `autostart` and `--no-tray`, the installers' `--no-autostart`/`-NoAutostart` are taken for one release.
  **Migration:** the first start removes the old sign-in entry (only when it is the tray's) and ends a tray still
  running (tray.json's pid; on Linux only a process whose command line is ours), and the page says once: "The tray
  icon is gone: Swiss Army Bench now runs while it's open."
- The agent: `app_lifecycle` (windows, last client, busy, held, seconds left, why), `desktop_status`,
  `desktop_open(page)`.

## The update button, top right (the owner, 2026-11-18)

"can the app pop up an update button in the top right when an update is available then warn that it will
restart once updated". Built: **Update available** sits in every window's top-right corner (fixed, green, only
while an update exists; red "Update failed" with the reason), and leaves the status bar. A click always warns
first: "Swiss Army Bench closes, installs X and opens again by itself", with What's new, and lists unsaved
documents and running kernels when there are any (Update and restart). The server's POST /updates/install now
always answers the user's first ask with {"confirm": ...}; the agent's still waits for the user's Allow.

## Your own packages kept across updates and extension changes (the owner, 2026-11-18)

"everytime I add an extension or update, im having to reinstall all of the imports" (`No module named 'azure'`):
`uv tool install --force` makes the app's environment again from the app and its extensions only, so what
Install now had added went. Now the helper (server/updater.py) reads the app's own environment just before and
passes the user's packages `--with` to the new one and to the restore: the packages nothing of the app's needs
(swissarmybench, its extensions and everything they need at any depth), only the tops (azure-identity, not the
azure-core it brings), so uv resolves their needs again (domain/updates.py `own_packages`). Read from the
environment, not a list kept, so packages installed before this fix are kept too.

## The guided tour (the owner, 2026-11-18; built, branch tour-guided)

The owner: "the tutorial needs to move and highlight the item it is talking about, so the tutorial might need to
stage a couple tables in the grid then remove them. it will need to navigate to pages as it goes and those
descriptions could use a bit more detail". A front-end change on the owner's word (web/src/tour.ts).

**Decisions.**
- **Each card goes to its place** with the rail's own moves (nav.ts `runArea`, as a rail click; the grids by
  panes.ts `activateGrid` and, for Compare, Key Finder and Relationships, `splitWith(..., quiet)` so the two tour
  tables sit side by side with no key picker). It waits up to 2.5 s for the control, scrolls it into view and lights
  it up; a control that never comes leaves the card in the middle with "Not here right now." The spotlight follows
  its control while the page settles (every 300 ms; a control drawn again is found again).
- **Back** shows the previous card, which goes to its own place (Analyze after Compare: one table again).
- **Closing** (Escape, Skip, the last card's Start) goes back to the history entry the tour started on (nav.ts
  `returnTo`: the entries it made go, and the start address is put back where a table's arrival replaced it), then
  closes exactly the tables it opened (`DELETE /datasets/{name}`, the Open list's close). A table that arrives while
  the tour is already closed is closed at once.
- **The staged tables:** a dozen made-up customers (`tour_customers`: customer_id, name, city) and a dozen orders
  (`tour_orders`: order_id, customer_id, product, quantity, amount, order_date), pasted as Ctrl+V pastes
  (`POST /datasets/{name}/paste`, tab-separated). A name an open table has gets `_2`, `_3`... The orders are sorted by
  amount (one step) so Steps has one to light up; the step goes with the table.
- **The cards, in the rail's order:** Hi!, Connections, APIs, Variables, Data Catalog, Grid, Ribbon, Steps, Profile,
  Analyze (fit test, outliers, regression and time series folded into it: they all pointed at its one button),
  Compare, Key Finder, Relationships (was "Saved set"), ERD, Structures, Blades, Notebooks, Scripts, Apps (only while
  its rail icon shows), Visualizations, Session, Extensions, Settings, Agent (Settings' Claude section). Gone: Table
  cell (in Notebooks' words), Fit test, Outliers, Regression, Time series, Data (now Data Catalog), Pack. Blades,
  Notebooks, Scripts and Apps are other pages (the blades page, the Workbench window): their cards light the rail's
  icon, the card beside it, and say so. Each card's words: what it is, when you'd use it, how to reach it; a short
  `clue` of its own is the game's (the long words name the place, which would give the answer away).
- `where` went (the tour goes there itself). The keys are heard on the window while the tour is open (a page that
  takes the focus does not take them); Enter outside the card is Next.
- **The agent (golden rule), 2026-11-18:** the tour is a page-only teaching aid; no command, as nothing it does is
  work the agent would want (app_navigate and the table commands already do each move).

## The mark on the rail, and Projects as a page of its own (the owner, 2026-11-18; built, branch projects-page)

The owner, with a screenshot of the red "+" mark at the top-left of the grid page's tab row: "Move this to the rail
also reduce icon size just a bit so more fit. and give this button its own page for projects dont share the grid as
the home page". A front-end change on the owner's word.

**Decisions.**
- **The mark is the rail's first item** (rail.ts AREAS, area `projects`), above Connections, on every page and window
  with the rail (the grid page, the area pages, the blades page, the Workbench, the Key Finder window). Its look is
  kept (the red square, the white +, nav.ts `markIcon`), its tip says "Projects Alt+Home" (`aria-keyshortcuts`), and
  it is the rail's first stop for the arrow keys and Home. It left the tab bar, the title bar, the blades page's top
  and the Workbench's top row.
- **Projects is a rail page over the home page** (projectsPage.ts with areaPage.ts, `open=projects`), the way
  Settings, Connections and Session work: Back, Forward and a reload keep it, the mark is marked current while on it.
  Only the home page registers it, so from another window the mark (and Alt+Home, and the rail's `projects` area)
  brings the home window forward showing Projects (nav.ts goHome; a home window opened fresh loads
  `/workspace?open=projects`). It holds the Project Explorer (its header lost its own "Projects" heading: the page's
  heading is it) and the Tour with its "New here?" bubble in the heading row. Settings keeps the projects folders.
- **The grid page is only the grids.** The Start view left panes.ts (no `start` AppView, no setEmptyView): with no
  table the grid page shows the Grids landing, a project open or not; with no project it adds "No project is open."
  and a link to Projects, and lists the connections either way.
- **The app opens on Projects** when the home page starts at plain `/workspace` with no table and no project (as the
  Start view did), replacing its first entry; a rail click made while the page was still starting wins. The desktop
  app and `swissarmybench open` keep loading `/workspace` (domain/desktop.py HOME_PAGE unchanged), so both stay in
  step; `swissarmybench open <folder>` opens the project and lands on its grids as before.
- **Old addresses:** `/workspace?view=start` lands on Projects (replaced); app_navigate's `start` and app_snapshot's
  `start` are old names for `projects` for one release (domain/navigation.py SAME, services/snapshots.py OLD_AREAS).
- **Leaving Projects:** a project opened or made there leaves for its grids (pushed: Back returns); a table that
  arrives (a push, the agent) makes Projects give way (replaced), as it took the Start view's place before. A project
  the agent opens while Projects is on show, with no table, leaves the page as it is (its card marked open).
- **The agent (golden rule):** app_navigate `projects` (and `home`) shows it; app_snapshot area `projects` draws it.
  The Session page's project entries go to Projects.
- **Smaller rail icons:** 24px (from 28), the item height clamp(34px, (100vh - 40px) / 19, 46px), the current bar
  8px from each end, the Session count moved to sit on the smaller icon's corner; `--rail-w` stays 60px.
- **The tour** starts from Projects and returns there; a new second card, Projects, lights the mark on the rail.

## One loading state that gates what is loading, and one error component (the owner, 2026-11-18; built, branch uniform-loading)

The owner: "Let's improve loading things with a uniform loading form. I noticed some things say in tiny text loading
and they don't gate the thing that is loading." Made design principles 8.12 (loading) and 9.5 (errors).

- **One module, web/src/loading.ts, on every page and window.** `busy(host, words, work, {abort, onCancel,
  errorIn})` gates exactly the element that is loading: `inert` and `aria-busy` at once (a click lands nowhere, a
  second start waits behind the first), and after 150 ms a translucent cover over exactly its box (a sibling placed
  each frame over the host's rectangle, so its Cancel stays clickable; the host's corners), a spinner and the words
  at the body text's size on a raised panel ("Loading Shop's tables…", "Connecting to Warehouse…"), the time taken
  after 3 s, Cancel when given an AbortController (the fetch's signal; `onCancel` for a server's cancel route), and
  an error in place through errorNote.ts. Work under 150 ms draws nothing. A tall host (over 320 px) has its words
  near its top, where the eye is. `loadingBlock(words, {height, inline})` is an empty area's placeholder (centred,
  its height kept). `busyButton(button, work, words)` / `busyClick(words, work)` keep a button disabled with a small
  spinner and its own words ("Testing…") until the work ends; a second click does nothing (a capturing listener
  swallows clicks at once, the look comes after 150 ms; an icon-only button shows the spinner only). `markBusy` draws
  a button busy from a view's own state (a canvas's Play, a query's Run) and returns what puts it back.
- **Tokens** (grid.css, each theme): `--busy-cover` (the cover's translucent fill), `--busy-spin`, `--busy-track`;
  the spinner's pairs are in test_contrast.py. Reduced motion: the spinner stands still (the global rule), the time
  still counts. A busy button keeps full opacity (busy, not unavailable).
- **Roles:** the cover's words and the placeholder are `role=progressbar` with the words as their name, not
  `status` (a page's own status line keeps its role, so tests and screen readers find one).
- **errorNote.ts (9.5):** `errorNote(error, extra)` draws the word and icon (Error, Warning), what happened (the
  first sentence), where, the fixes as buttons (a missing package's refusal brings Install now), the rest folded
  behind Details with Copy, and Send to the agent (the inbox, as the Workbench does); `warningNote`, `showError` /
  `clearError` in place, `errorToast` for background work (Show), `errorParts` reads an ApiError, Error, string or
  the server's JSON refusal ({error|message, where, details|traceback, missing}). loading.ts shows its errors with
  it. The app's other error toasts and status-error lines are a separate pass (not this branch).
- **Used everywhere the loading words were:** the Connections page (list, detail, types, form; Test and Save gate
  the form; the detail's Test, Refresh catalog, Import relationships, Open as grid, Update to the new driver busy,
  their failures in place), its tree (gated while it loads, Open all gated, Preview and Open busy), the Python
  connection form, Add API (the form, Find its OpenAPI, the preview, Try it, Add gating the form), the APIs page
  (cards' Refresh gates the card, Apply, Send, Save as web call), Structures (the page, Run again gates it), the
  Key Finder (gated while it compares, its error in place; Compare on these and Add as relationship busy; the
  values sample), the Data Explorer and the Data page (previews, a catalog's load, the tree's lazy branches, each
  action button busy while its work runs), the Variables, Session and APIs pages, the blade screen (Save, Test,
  New blade's templates), the catalog rail's Refresh and Open as grid, the Tables list, the steps strip's Load all
  rows (the grid gated), the steps window's verify, the Analyze menu's forms (fit test, outliers, odds, find
  predictors, regression, time series, forecast, tie-out: placeholders and busy Run buttons), the profile, the
  Data shape check, the ERD's Find relationships and Check, the file picker's list (gated while a folder is read),
  the Workbench's variables pane, Run as scheduled, a notebook environment's Make it, the query tab's Run, the
  Streamlit canvas (Play and Test this page gate the canvas), the Excel canvas's Play, the Code App page (files,
  connectors, Refresh, Make it, Run live, Install, Sign in, Push, Open as grid), Install now, the Extensions page's
  Install and Remove, Launch Claude's Look again, the Projects page (its first load, and a project's open or new
  gates the page once the folder is chosen), Export's Save and Download.
- **Left as they are:** status words of background work (8.5: a catalog's "Loading its tables…" state on the Data
  page, a kernel's "starting…"), and the Source Control page (VS Code's own look, cloned exactly).
- **The agent:** unaffected; no new user action, so no new command (no Cancel route was added: no slow route has a
  server-side cancel yet; `onCancel` is there for the first one).

## Every error looks and reads the same: one shape from the server, the note in place (the owner, 2026-11-18; built, branch uniform-errors)

The owner: "Errors should be presented to users in one uniform way as much as possible." Design principle 9.5, the
second pass (the component came with uniform-loading).

- **The server's one shape** (domain/refusals.py, server/http.py): every refusal is JSON `{error, where?, fixes?,
  details?}`: `error` one plain sentence (a longer message keeps its whole text in `details`), `where` the named
  thing, `fixes` `[{label, action, ...}]` with `action` one of install, set_variable, sign_in, open_settings,
  try_again (and `command` for the agent where one exists), `details` the source's own words. The fields pages and
  the agent read stay beside it (`missing`, `missing_variables`, `needs`, `install_here`). The use cases' outcomes
  (Refused, NotFound, Conflict, TimedOut) are `Explained`: `NotFound("...", where=..., fixes=[...])`; a plain one
  answers as before, in the shape. DuckDB's and sqlglot's errors keep their words in `details`; a failed run
  ("Shop failed: OperationalError: ... (line 5)") reads "Shop failed: unable to open database file." with
  "OperationalError: ... (line 5)" as details and its connection as where. The guard's 401/403, an unknown address
  and a method not taken answer the shape too; the routes that chose their own status use `error_as` / `refusal`.
  Refusals are written as UTF-8 (not \u escapes). The agent (cli/api.py) reads a words-only refusal as its words,
  exactly as the plain answers read, and a fuller one as its JSON (where, fixes and their commands).
- **The page reads it** through ApiError: `message` is the sentence, `said` the whole answer (`saidOf(e)`), so every
  place that showed `e.message` shows words, never JSON. errorParts turns the server's fixes into buttons (Install
  now, Set it, Sign in and Open its settings to the connection's page).
- **In place, not toasts.** Every `toast(..., "error")` became the note (322 of them): `errorHere(e)` puts it where
  the user's last action was (the control's row inside its card, panel, pane, section, form, cell or dialog; a
  dialog's footer button: the body's foot; a control in a page's bar (ribbon, title and tab rows, status bar, rail,
  toolbars): a note floating just under the bar beside it; a menu item: its opener). Pressing the same control
  again takes its note away first, so a retry that works leaves none. Three minutes after the press, or with the
  control gone, the work is the page's own and the note is a toast. Places that hold their own place use
  showError/clearError (forms: the connection forms, a step's form, Export, a starter's form, the theme form), the
  grid's rows (over the grid, with Try again), a card's drawing (the lazy drawers throw; their callers draw the note).
- **Background only: errorToast**, the same note in a toast (Close, Details, Send to the agent), with Show when
  there is a place: a failed Autosave (Show: the project's group on Grids; Save now), a table that did not open
  from Python, a dataset closed elsewhere, a page another window asked for, the blade import's problems once its
  dialog closed, and the Source Control page's notifications (VS Code shows its own as notifications; its page's
  words and look are unchanged). `toast()` takes no error kind any more.
- **status-error lines and the one-off styles** (error-text, `p.error`, node-error, cv-problem, missing-error,
  connection-error, team-install-error) became errorNote; a one-line row's mark (a card's "catalog not loaded", a
  password with no source, the steps strip's broken step, a tree's row, an API's answer, the blades tree's "!")
  is `errorMark`, the note's inline form (the icon, the word for screen readers, the words, the message in its
  tip). Their CSS left grid.css.
- **Warnings use warningNote, their words kept:** "Only works on your machine" (the form, the sign-in, the
  password, the detail; the card's and a starter's as the warning mark), a stale result's "Out of date: run
  again", the Key Finder's time limit, a kernel started without a vault's variables, steps that no longer fit after
  a connection swap.
- **Kept:** the Workbench's error panel (9.1) and its kernel notices ("Cancelled"), the Source Control page.
- **The agent:** no new user action, no new command; it reads the same refusals (above).

## Desktop quick wins and desktop enhancements (the owner, 2026-11-18: "Agreed"; built, branch desktop-wins)

The survey of the desktop app (read only) listed small fixes; each was checked before it was changed.

### Part A: the small fixes

- **Startup:** server/__main__.py imported uvicorn and the whole app (create_app: bootstrap, every route) at its top,
  which the app's own process (launcher -> __main__.main -> the desktop shell) never uses. Both, and the heartbeat
  filter, now load inside `start()` (uvicorn's Server subclass is made there too). `import
  swissarmybench.server.__main__`: 0.56-0.60 s before, 0.13 s after (importtime, warm); a process that imports it,
  0.60-0.66 s before, 0.16-0.19 s after. What is left is adapters/state_files.py importing domain/relationships
  (sqlglot, about 0.1 s) for `info_file_path`: left as it is (shared file).
- **A push or open_grid with nothing to show it:** only VS Code's openers were asked, so with only the app (or a
  Workbench window) open nothing showed it. LiveUpdates.ask_opener now falls back to `fallback`, set by the running
  server (`start`, unless SWISSARMYBENCH_NO_BROWSER=1, which the tests set): server/desktop.py `show` opens the
  workspace on the grid in the desktop app (started when it is not open), else the browser. The push client's words
  no longer say the app lives in VS Code.
- **Tray leftovers removed:** `take_server_events` and server_events.json (nothing writes it since the tray went),
  SWISSARMYBENCH_TRAY in the updater's test, the Bridge's unused open_address, AppWindow.popup, LiveUpdates'
  test-only openers_gone_for. Words fixed: the signed-out page ("from its launcher"), app_navigate's home notice,
  routes_desktop, app.py, bootstrap's open_work, services/updates.py, updates.ts, install.ps1.
- **A clean quit over the app's channel:** `{"quit": true}` closes every window without asking its page, keeps
  each window's place (windows.json), tells the server closed and ends the app. `swissarmybench stop` quits the app
  first, then stops the server (the installers already run it); the update's helper asks the app to quit before it
  would end it (SystemOps.quit, standard library: it speaks the channel itself), and ends it only when it is still
  there 5 s later. **Unsaved work:** an update already warned in the page (updates.ts: the restart and what would be
  lost) and `stop` is the user's own word in a terminal, so both quit with closing set: no page is asked.
- **No blocking on the window thread:** the shell trusts the server that answered once (its process id and token,
  while that process lives and the connection file names it): opening a page makes no request. Finding the server
  and starting it runs on a thread of its own that tells the window thread when it answered (the 300 ms timer and
  its 2 s health checks went). Closing the last window posts /lifecycle/closed from a thread (2 s limit; the
  process waits for it at its end; server/lifecycle.py post_json, not a copy). The first window shows at once with
  a plain "Starting…" page while the server comes up, and the first page loads into it.
- **VS Code's button opened Chrome:** it now runs `<the uv tool's python> -m swissarmybench.server open` (the app,
  else the browser), pythonw.exe on Windows; core/chrome.ts and the `chromePath` setting are gone (nothing else
  used them). Should that command not start, the button falls back to the server and the default browser.
- **Print to PDF in Visualizations was real:** Qt's window.print() returns at once while the Save dialog is up and
  fires no afterprint, so the page's 1.5 s fallback took its print layout and its `@page` size away before
  printToPdf ran: the PDF came out A4 (594.96 x 840.96 pt) with the whole page in it. Now the shell fires
  `afterprint` once the PDF is written (or the dialog is cancelled), the page waits for it in the app (`sabApp`
  marks the app; the browser keeps its 1.5 s), and Chromium takes the page's `@page` size: Letter landscape comes
  out 792 x 612 pt.

### Part B: desktop enhancements

- **The browser's keys are the app's (in the app only).** The shell's script puts `window.sabApp` on every page
  (desktopApp.ts reads it); in a browser the keys stay the browser's. Grid page: Ctrl+W closes the tab in front
  (a table's, the query draft; on Visualizations or the ERD the grids come back), and the window once no tab is
  left; Ctrl+T and Ctrl+N a new query tab; Ctrl+Tab and Ctrl+Shift+Tab go round the tables; Ctrl+Shift+T reopens
  the last closed tab. Workbench: Ctrl+W the document in front (the window when none), Ctrl+T and Ctrl+N a new
  notebook (decided: the Workbench has no query tab, a new notebook is its new tab), Ctrl+Tab and Ctrl+Shift+Tab
  the documents, Ctrl+Shift+T the last closed table (in the home window). They are commands of the pages'
  registries (gridCommands.ts `tabs.closeTab`, `tabs.next`, `tabs.previous`, `tabs.reopen`; the Workbench's
  `file.closeTab`, `tabs.reopen`), so the palette shows their keys and the agent's workbench_window runs them.
  **F5, Ctrl+R and Ctrl+W are the page's first now:** the shell's own shortcuts took F5 before the Workbench
  could (its F5 runs); the shell's script reloads or closes only when the page left the key alone.
- **Ctrl+Shift+T reopens what the session knows:** closing a grid (or its table) remembers its table (by name
  and the store's serial, so another table of that name is never taken for it), steps and settings, and the
  file it was read from; the newest that can come back does: a new grid on the table while it is open, else the
  table read again from its file. The last twenty, in memory only. The agent: `tabs_reopen`.
- **Open with:** the installers register the app for this user only: Linux a .desktop `MimeType` (text/csv,
  Parquet, xlsx, ipynb, folders) and a shared-mime-info package with a blade's own type (`*.blade.py`), the
  default only for that type (`xdg-mime default`); macOS the bundle's document types (Alternate for csv,
  parquet, xlsx, ipynb; Owner for an exported `com.swissarmybench.blade` UTI, and QFileOpenEvent handled by the
  app's QApplication); Windows HKCU `SwissArmyBench.File` and each extension's `OpenWithProgids` (never the
  default; a .blade.py is a .py to Windows, so .py is offered). `--uninstall` / `-Uninstall` removes them.
- **`swissarmybench open <file>`** hands the file to the running app over its channel (`{"file": path}`; the
  app started first when none runs: one app, never a second). The app (server/desktop.py file_page, off its
  window thread) asks the server: a table loads by its path under its file's name (never replacing an open
  table: `_2`), a notebook opens in the Workbench window that is open (workbench_window `file.open`), else a
  Workbench window at `/workbench?file=<path>` opens it; a blade of the library opens on the blades page,
  another .blade.py in the Workbench; a folder as a project (as before). Where the app cannot run (or
  `--browser`) the server reads it and the browser shows it.
- **Drag and drop in:** a file dropped from the system on a window is opened by its real path (a filter on each
  window's view and the child that draws the page), so a table's origin is the file and a project reads it
  again; the browser keeps its upload. **Drag out (a tab dropped as a CSV) was not built:** Qt WebEngine hands a
  page's drag to Qt only as its MIME data, so it would need the page to start a native QDrag through the shell
  with a temporary file and its removal; not small, left for later.
- **Files that refresh themselves:** services/file_watch.py stats each file-read table's file every 3 s (the
  server, so the browser sees it too), stamped by the table's version when it was read; a change is said once
  (`file_changed`), `datasets_list` carries `changed_on_disk`. The tab shows a dot and the pane a bar: Changed on
  disk, Reload (POST /datasets/{name}/reload: read again in place, its grids and steps kept), Not now (the stamp
  taken as it is now: said again only on the next change). Never reloaded by itself; a file that is gone is not
  said. The agent: `tabs_reload` (`not_now`).
## A variable anywhere a value is typed: `${NAME}` (the owner, 2026-11-18; built, branch variable-refs)

The owner: "everything in a connection should have the option for a env variable ... a reserved char that allows
us to use env variable almost anywhere in the app" (like SSRS's expressions); "The drop downs were for the
connections ... they take up space when a ${ could be used"; "Let's do it. ${ it is". The rules: design
principle 12.7. Phase A (the rules, the backend, the agent) and Phase B (the forms: one box, `${` offers the
variables, the line under the box, the tour's card; 2026-11-19) are built.

- **The rules (domain/variable_refs.py, standard library only):** a reference is `${` + NAME + `}` or
  `${NAME:-default}` (the default literal up to the first `}`: no nesting); `$${NAME}` is the text; anything else
  is as typed. One pass: a value is never read again. `escape` writes a literal back so reading it gives the same
  text (a box shows a saved `${` as `$${`).
- **A connection's fields:** a connection is its code, so a field holding `${NAME}` is written into the code as
  `os.environ["NAME"]` (`os.environ.get("NAME", "default")`, joined to its text by `+`, `int(...)` for a number)
  and read back from those shapes as the box's text (`text` beside `value` in every setting). The library, a
  shared project and an export hold the name; the code reads the value where it runs (the server's environment
  has every variable's value; a vault's entry runs its vault first: providers counts a setting's names). The older
  "From an environment variable" mappings (certificate files, SQL Server's places) read as `${NAME:-path}`; the
  old `{"value", "env"}` form still works until the forms change; `{"text": ...}` is the one box's form.
- **Not done in a connection string's part** (`Server=...;` inside one literal): refused with a plain message
  (type the value, or write the connection with keywords). Splitting the literal would not read back as one
  setting.
- **Passwords:** a password field is a variable already (`secret("WAREHOUSE_PASSWORD")`). Each connection's own
  saved password (`secret("password")` in its own keyring entry) became, once at start, a keyring variable of the
  name the page already showed it under (`SALES_DB_PASSWORD`), the code renamed, the connection files copied to
  `backup/before-variables-<date>/` first; said once on the page. Its old keyring entry is left (nothing lost). A
  name already taken leaves that one as it was. A second start finds nothing to move: no byte changes.
- **SQL:** a reference outside strings, quoted names (`"x"`, `` `x` ``, T-SQL's and the app's `[x]`) and comments
  (`--`, `/* */`, MySQL's `#`), and dollar-quoted text, is a bound parameter: DuckDB `$1` (the SQL box, the "+"
  tab, `sab.sql`'s DuckDB), the driver's own PEP 249 paramstyle in a `%%sql` cell (sqlite3 and pyodbc `?`,
  psycopg `%(p1)s` with every `%` doubled, SQLAlchemy `:p1`); ClickHouse, BigQuery and Spark take none (refused).
  Where a name goes (after FROM, JOIN, INTO, AS, beside a `.`, glued to a name, before `(`) it is refused, never
  pasted. **Our own scanner, not sqlglot's tokenizer:** the plain client (a `%%sql` cell in any Python) cannot
  count on sqlglot, and sqlglot's tokens keep no comment positions; a test checks our string spans against
  sqlglot's tokens.
- **Paths, Run settings, an API:** a dataset's file path and a structure's are resolved at use (the dataset's
  origin keeps the typed text; a structure's open path is the resolved one, as before). Run settings' arguments
  are resolved from what the run is given (the log keeps the typed text). An API's base address holding `${NAME}`
  is written into API_<name>.py as `os.environ[...]`; Try it's typed inputs are resolved (its origin keeps the
  text).
- **Missing:** one error, 422 `{"error": "NAME is not set on this computer (where).", "where",
  "missing_variables", "fixes": [{"label": "Set it", "command": "variables_set", "page": "variables", "name"}]}`;
  a connection's Test checks its settings first; a run that reaches `os.environ["NAME"]` says the same words.
- **The first start's list:** saved settings whose literal text now reads as `${NAME}` are said once
  (`variable_refs.json` marks it, written only once something was listed, so a start that finds nothing writes
  nothing). They still mean the text until the user saves them again.
- **The agent:** `variables_resolve(text)` (the preview: a secret masked by the same rule as Show; names not set
  with the error) and `variables_uses(name)` (fields by setting, passwords, code, Run settings).
- **blades.py kept under 1,500 lines:** its settings' suggestions moved to domain/blade_suggestions.py (blades.py
  keeps `suggest_settings`, which reads it when asked), a vault's secret names as variables to variable_refs.py
  (re-exported).
- **Not built here:** a reference in DAX; a structure's saved path kept as the typed text; static API headers
  (an API has none beside its sign-in); Streamlit pages and data.py inherit the connection's code, so they read
  `os.environ` already; a `%%sql` cell's export as a script keeps the cell's text.

### Phase B: the forms (2026-11-19)

- **One box, web/src/variableBox.ts:** `variableBox(input)` makes any text box a variable box: typing `${`
  lists the variables under it (GET /variables: the name and its source in words, a vault's name with it; never
  a value), filtered as the name is typed; arrows, Enter or Tab pick, Escape closes; the last row is New
  variable… (with the typed name). A `{x}` button on the box opens the same list at the caret. Under the box,
  `previewLine()`: POST /variables/resolve's value (a secret as dots), or the one error (errorNote.ts) with Set
  it; nothing when the box names no variable; drawn again on `variables_changed`. The box is an ARIA combobox
  pattern (aria-autocomplete, aria-controls, aria-activedescendant) without the role, so the boxes keep their
  textbox role and their labels.
- **Set it and New variable… open the Add variable form in place** (web/src/variableLinks.ts: a dialog with the
  Variables page's three fields), not the Variables page itself: a half-filled connection form is kept, and
  the box that asked puts the new name in. errorNote.ts gives every refusal with `missing_variables` its Set it.
- **Where:** every connection form field (connectionsWindow.ts: the "from" pickers and the password's source,
  vault and entry pickers gone; certificate and keystore paths take `${NAME:-path}`; a number's box is text
  with a numeric keyboard), a Python connection's variables (each listed with its line; the source pickers and
  typed values gone: the Variables page keeps them; a mapping saved before stays as it was), Add API's base
  address, a blade's settings (the import's fill-in), Run settings' Arguments.
- **Passwords:** one box holds `${NAME}` alone, or a typed password (shown as dots, a reference as text). A
  typed one is used for Test as it is and, on Save, kept as a keyring variable named after the connection and
  its label (`WAREHOUSE_PASSWORD`), the code then asking for it; amber while typed (the keyring works only
  here). `${NAME}` mixed with other text in a password box is refused in words (a password is never partly a
  variable). A key vault's secret is its variable's name; a vault that loads every secret runs first when one is
  missing, as before.
- **A connection's code changes one at a time:** leaving one box for another sent two changes at once, and the
  second could start from the code before the first (a password renamed while Encryption changed). They now go
  in turn, and a setting's place in the code is read again when a rename moved it.
- **A Python connection's variable a vault gives** runs that vault first (adapters/blades.py providers), as a
  setting's variable already did, now that no mapping is saved with the connection.
- **The Variables page** shows a connection's use with its box: `Warehouse · Server`.
- **The tour:** a card after Variables, "Using a variable": it opens a made-up PostgreSQL form, puts
  `${WAREHOUSE_HOST}` in its Server box and lights the box; the form is never saved and closing the tour goes
  back past it. Its clue: "Typed into a box, it reads its value from this computer at the moment it is used."
- **Not changed:** Run settings' per-variable sources (a scheduled run's own environment: a different thing
  from a box's text); Add API's sign-in settings and the values typed for Try it (an API's own variables,
  kept in the keyring on Add, as before); the file chooser's folder box (it moves the picker, it is not a
  saved value).

### Anywhere: typing a dollar-brace, and right-click, Insert variable… (the owner, 2026-11-19)

The owner: "We should make a right click and insert env var menu and a auto complete when ${ is typed anywhere";
and for the tour: "Add to the tutorial and make users type in a sample input box and make the user right click".

- **web/src/variableAnywhere.ts**, installed once in each page's entry (main.ts, catalogPage.ts, workbenchPage.ts):
  document-level listeners, so a box drawn later needs nothing. In any text box or text area (password boxes
  too; a password box shows a reference as text), typing `${` opens the same list as the forms' boxes, as one
  floating list under the box (inside the top dialog when one is open; over the tour); Enter or Tab put in
  `${NAME}` (a closing brace already there is used), Escape closes, New variable… last. The page hears the
  change as typing (input, then change).
- **Right-click** any such box: the app's own menu, Cut, Copy, Paste, then Insert variable… (the pick replaces
  the selection at the caret); the keyboard's menu key or Shift+F10 opens it under the box. Beta mode's Leave a
  note… follows, as on every menu. Paste reads the clipboard (the desktop app allows it; a browser that refuses
  says to use Ctrl+V).
- **Left alone:** Monaco's own text area (the editors have their own), boxes with their own list (variableBox.ts),
  search and filter boxes (type=search, role=searchbox, a label or placeholder that starts with Search, Filter or
  Find, or a class naming search or filter), anything inside `[data-no-variables]`, read-only and disabled boxes,
  and non-text inputs (numbers, dates, ticks).
- **Editors:** a SQL editor (a Workbench SQL cell, the "+" tab's query) completes the variables after `${`
  (Monaco's completion, its trigger the brace) and has Insert variable… in its right-click menu. Not a Python
  cell (Python reads `os.environ["NAME"]`; the editor already completes names there) and not DAX (the backend
  does not read a reference in DAX).
- **The agent needs nothing new:** it passes text with references directly (every command takes the text as
  typed); `variables_resolve` previews one.
- **The tour, hands on:** after "Using a variable", two cards with a practice box in the card: Type it (type a
  dollar-brace, pick from the list) and Right-click it (Insert variable… from the menu). Next waits until the
  box holds a variable, then the card says it worked and shows what it reads; a hint after 8 seconds; Skip,
  Back and Escape always work (an open list or menu takes Escape first). The list always has one to pick: the
  tour adds TOUR_WAREHOUSE_HOST (warehouse.example.com, made up) when this computer has none of that name and
  removes it when it ends, like its two tables. Not in the game (no clue).


## Join a team: one Team box in Settings, one repository (the owner, 2026-11-19; built, branch team-join)

The owner: "you have made linking a meta store and shared project folder way too difficult; the settings menu
makes no sense". Decided with the owner: **one GitHub repository** holds the team library and the team's shared
projects (its `projects/`); **Settings only** (one Team box, first after Theme); the screen says **Team library**.

Built:
- **The Team box** replaces Settings' Meta store folder, Projects folders and GitHub sections. No team: "Share
  connections, variables and projects with your team." with **Join a team…** and **Start a team…**; joined: one
  row, "Team: owner/repo", the sync words, **Pull**, **Push** and "…" (Open on GitHub, Set up this computer, Show
  its folder, Leave the team). Under both: "New projects go in <folder> · Change…". **Advanced** (folded, closed):
  the Team library folder and the Shared projects folder as their own paths (Change…, Default / None) and Set up
  this computer, for a team that keeps them in two repositories or syncs another way.
- **Join a team… / Start a team…** is one dialog with a strip of its steps (GitHub sync, Sign in, Repository or
  Name, Set up); it opens at the first step still to do. Install hands over to the Extensions machinery (the app
  restarts); the step is kept in the state folder's `team.json` (never localStorage) for a day, and the new
  window's start (libraryNotices) opens Settings, whose Team box opens the flow where it was. Sign in: Sign in
  with GitHub (the device flow) first, Use a token folded under it (open when the device flow is not available).
  The repositories are those the account can push to, newest push first, searchable.
- **The local copy's place:** the state folder's `team/<owner>-<repo>/`, not Documents/Swiss Army Bench/Team:
  the library's own default already lives in the state folder (`~/.swissarmybench/library`) and nothing asks
  the user for its path; the projects in it are reached from the Projects page, so the folder need not be seen
  (Show its folder opens it). A second Join of the same repository pulls into the same copy; a folder there
  holding other files is refused, said.
- **Start a team:** a private repository (the account's or one of its organisations') made with GitHub's first
  commit, then the layout written (README.md saying what goes where, .gitignore with local/ and .sab/data/,
  projects/README.md so the folder exists on GitHub), this computer's library copied in (local/ too, kept here
  by the .gitignore; its own README.md and .gitignore replaced) and pushed as one commit. The token needs
  Administration to make a repository: the token's steps say so.
- **Leave:** asked first ("Keep a copy of the team's connections, vaults, variables and blades in this computer's
  own library?": Keep a copy / Leave without a copy). The library and the shared projects folder go back to what
  they were before joining (kept in team.json); with a copy, every team item this library lacks is copied (an
  item it has, different, stays as it is, counted). The local copy stays on disk; the message says where.
- **One link for both folders:** the shared projects folder inside the team library has no link of its own: the
  Git extension's sync finds the link above it (`_covering`), so a shared card's Pull and Push, its words and
  the footer's mark work as before; a card's Push still sends only its project's files.
- **The agent:** `team_status` (repositories and owners as options), `team_join`, `team_start`, `team_leave`
  (each on Allow; `team_leave` without keep returns the question); Pull and Push are `github_pull`/`github_push`.
  Signing in stays the user's own. The base finds the extension that syncs with GitHub by what it provides
  (`provides=("team",)` in the catalog), never by its id; the extension hands the base its TeamPort through
  services/hooks.py's `team`.
- **Words:** Set up from the meta store is **Set up this computer**; the Git extension's words say the team
  library; the Source Control page's quick pick says Team library folder.

Decisions and notes:
- **Design principle 7.9 and the brief:** the brief listed the Joined row's sync word as "up to date / 2 changes
  to push / behind: Pull"; 7.9 says no confirmation labels, so the row says nothing while up to date and shows the
  word only when there is something to do. No other rule there contradicts this work.
- The library's counts and the shared catalog's counts left Settings with the Meta store folder (7.1).
- Not changed (another branch's file): tour.ts's Settings card still says "the meta store folder your team
  shares, the projects folders"; it should say "your team".

## Analyze: the analyses on their own page, a contract each, results that land by themselves (the owner, 2026-11-19; built, branch analyze-page)

The owner: "Let's move the analyze from the table bar to the visualizations pane and then rename the
visualizations pane Analyze. The new analyze pane's functions should be across the top with its own toolbar for
every single analyze option we have. This page becomes the place where users can input columns and tables
through guided, exact, very user friendly forms" / "Every analysis should automatically push to the analysis
visualization area. That's the whole point of moving it here." / "make it stupid simple" / "We need a data
structure contract format for each analysis ... then present that to the agent, and mock up a sample to include
in each analysis input window" / "and even suggestions for the current data to get the best analysis" / "as
robust as possible". Design principles 8.7 (rewritten) and 8.13 (new).

Built:
- **The rename.** Visualizations is Analyze: the rail, the page's title, `?view=analyze`, app_navigate and
  app_snapshot (`analyze`), the Session page's words, `analyze_*` commands (the chart's code is
  `analyze_chart_code`, since `analyze_code` is an analysis's code), `sab.analyze`, project.json's `analyze` key.
  The old names answer for one release: `?view=visualizations` and `?view=sandbox`, the old areas, `sandbox_*`
  and `visualizations_*` (cli/commands.py OLD_NAMES: run, never listed), `sab.visualizations` (warns once a
  session) and `sab.sandbox`, a project.json's `visualizations` or `sandbox` key. Files on disk keep their names
  (`.sab/visualizations.json`, `visualizations/`), as do internal names (aiPanel.ts, sandbox*.ts, CSS classes,
  client/visualizations_client.py). The old `/visualizations/theme*` routes went (only the page called them).
- **A contract per analysis** (domain/analysis_contracts.py, FORMAT 1): id, the everyday question, the technical
  name, what you get, the toolbar group; the table (rows at least and rows that are better, one row per what,
  two tables); the slots (plain words, the kinds accepted: number, whole number, date, text category, yes/no;
  how many: one, one or more, optional, none or more; the checks, each "must" or "should", in words and as a
  check; name hints); the options (type, default, allowed values, one line); the output (cards, a table
  result's columns); its own fixes; a deterministic made-up sample. Fourteen built in; an analysis blade's is
  read from its code and never run: its `CONTRACT` dictionary, else from whether `analyze` takes `columns`.
- **One checker** (domain/analysis_facts.py check_column, domain/analyze.py plan): a table's facts in one DuckDB
  pass (types, filled and different values, ranges, values at or below zero, whether every number is whole,
  text that reads as numbers or as dates in each of three styles, different days and months), then the
  few-valued columns' values and every column's first values. Per slot: fits or not and why in plain words;
  cautions for a "should". The form, the chips, the column-first buttons, Check this table, the agent's
  analyze_check and sab.analyze.check all call it. The old Data shape rules went (domain/analysis.py
  shape_notes and form_defaults, the /shape-check and /analysis-defaults routes, cheatSheets.ts), and the
  tools `analyze_shape` and `analyze_defaults` with them (a call says to use analyze_check or analyze_plan).
- **The form** (web/src/analyzePage.ts): a panel beside the board. The table line with Change (open tables,
  Find data… for a connection's), the chips (a native list per slot: only what fits, each with its type and a
  few values; "Does not fit" lists the rest with why), the cautions, Make it fit, one sentence, Run (gated,
  Cancel), More options, What your data should look like (the contract in words, the sample with the slots'
  columns marked, Try it on this sample). What can I do with a column? and Check this table are two more
  faces of the same panel. The last columns and options come back per table and analysis (this session).
- **Fixes as grid steps** (domain/analysis_fixes.py): text to number (commas, spaces and a currency sign
  dropped; nan and inf are blank), text to date (ISO, month/day/year or day/month/year: one style for the
  column; both offered when both read every value, never guessed), a month column from a date, the ten most
  common values and Other, blanks left out, values above zero, a yes/no column from Y/N and 1/0 in any
  spelling or from one value of a text column, and (the Outliers contract's own) totals per month or per key.
  Each has its count from the facts (the top-ten's from one query) and is applied only on Apply, on a button
  that names it ("Read when as dates and run"), or by the agent (`analyze_fix`, `steps_add`, or analyze_run's
  `apply_fixes`).
- **The ranking** (rank): fits now, fits after its fixes (planned against what each fix would make: a column
  whose ranges are not known until it is applied passes the range checks, and the run reads the real facts
  after applying), or does not; a score and a one-line reason; the top three are never ones that do not fit.
- **Runs** (services/analyze.py): the existing run_* functions on the grid's view, with a time limit said in
  plain words and a token to cancel by; the cards are made on the server (domain/analysis_cards.py), so the
  agent's and Python's runs land with no window open; they land at the top, newest first, as cards of no grid
  (what a run found stays when its table closes) carrying `analysis`: the run, its inputs, its actions and
  hand-offs. A run's result is kept in memory (60) for Show the math, Open as grid and Copy code.
- **The agent:** analyze_contracts, analyze_tables, analyze_check, analyze_plan, analyze_column, analyze_fix,
  analyze_run, analyze_cancel, analyze_runs, analyze_sample; the resource swissarmybench://analyze/contracts.
- **Python:** `sab.analyze(fig)` (a card), `sab.analyze.<analysis>(df, ...)` (the same plan and request, then
  the swissarmybench.stats function; its cards land through POST /analyze/land when the app runs),
  `sab.analyze.<analysis>("orders")` (an open table: run in the app), `.check`, `.contract`, `.contracts`,
  `.sample`.

Decisions:
- **Nothing on the grid:** the Table row's Analyze menu, the column header's Odds, Fit test, Outliers and Find
  what predicts it, and the Compare row's Tie-out went. **Compare stays** (it is a view of two grids, not an
  analysis). The grid keeps a column's quick Profile popup, the Table row's Profile, and the plain sends
  (Profile to Analyze, Send value, Send the row); Distinct values to Analyze is the Analyze page's odds run
  now. **The Key Finder's window stays on the ribbon:** it does more than report (it samples, and its pairs
  become relationships); Analyze's "Which columns join two tables?" is its report as a card.
- **Tie-out without a compare:** an unregistered Compare passed to TieOut.run, grouped and totalled by its own
  suggestion, so nothing appears on the grid page.
- **The fit test is three questions:** first digits (Benford), each value as common as expected, two columns
  related. **Logistic regression** is Predict a number with a yes/no target and a hidden "Counts as yes".
- **Samples keep real column names** (amount, region, late) with each slot's columns named beside them, not
  the slot keys as names: the form marks and labels the slot's column ("Amounts" over "amount"), and the
  sample reads like a table. A blade's generic sample does use its slot keys. Time-series and forecast
  samples are 24 monthly rows (a season shows), not about 8.
- **A chip is a native list**, not a custom popup: keyboard and screen readers work as everywhere, the
  columns that do not fit sit in the same list, disabled, with the reason.
- **The date fix never guesses** between month/day and day/month, and the number fix reads only what DuckDB
  reads after dropping commas, spaces and a currency sign: a European "1.234,50" is not offered as a number.
- **Group by a period and by a key** are suggestions (the Outliers contract's own: unusual months or
  customers), not needed fixes: time series and forecast group by period themselves. The needed "period" fix
  is a month column from a date, for a slot that wants a category.
- **Memory is the session's:** the last columns and options per table and analysis are not written to a
  project.
- **The lower-level tools stay** (column_fit_test, column_outliers, analyze_odds...) for what the form does
  not ask (shares, thresholds, a forecast's predictors); they answer the agent only and land nothing.

Left:
- A contract cannot yet declare a fix of its own as data in a blade's CONTRACT (the built-in Outliers one
  does, in code).
- Forecast's predictors, a time series' split by a category and a fit test against given shares are not in
  the form (the lower-level tools have them).
- Cancel stops a run's own queries; a tie-out or Key Finder in flight finishes unseen and lands nothing.

## The Python cleanup: duplicates merged, dead code out (the owner, 2026-11-19, the overnight optimisation pass; built, branch opt-clean)
Behaviour kept; only what the evidence showed was unused or copied. The analysis code, anything named
analyze/visualizations/sandbox and the one-release rename shims were left alone.
- **One route wrapper:** server/http.py's `safely` (beside error_response) for the thirteen copies, and its
  `with_body` / `with_actor` for routes_team.py's and the Git extension's. Many routes still write their own
  try/except inline: the same answer, left as they were.
- **One identifier quote:** domain/datasets.quote for DuckDB (catalogs, connection_tables, web_calls);
  catalogs.quote_identifier(..., "sqlserver") for the bracket rule (count_sql, context.md's connection names);
  sql_cell uses client/writes.quote. Quoting written into a connection's or an export's code as text
  (sql_server's runtime, lakes' SQL endpoint, script_runtime, lake_code) stays text.
- **One atomic write:** adapters/atomic_files.py: write_atomic (a unique temporary name in the same folder,
  O_EXCL, fsync, one os.replace; the mode given, else the existing file's own, else the umask's;
  if_changed), `replacing` for the two zips, and JsonFile (now atomic) that desktop.json's RecordFile (0o600),
  windows.json's JsonState and update.json's switch stand on. ColoursFile stays its own class (TOML text, a
  path that follows the library). A new file that went through tempfile.mkstemp before (an API's files, a
  structure, a new notebook from the Workbench) is now the umask's mode (0o644 typically), not 0o600: the
  blade files that must be owner-only say so (mode=0o600). The client's and the extensions' code-as-text
  writers (lineage_values, writes.py, app_settings' page code) keep theirs: they cannot import the server.
- **Dead functions:** app_pid, json_text, model_tables, is_structure_file, iter_keys, read_by_code, lookup_in
  (no caller). Test-only: removed with their tests where no rule the app relies on stood behind them
  (missing_imports, dax_column, spec_urls: the Add API dialog joins spec_paths itself, suggested_variable;
  web_call_table was web_calls.is_table, the test calls that); kept where the test is an invariant over real
  data (portability.portable_first, write_capability.tables_kinds_covered and kinds_named) or the function is
  used by a copied file (domain/html_cells.page_html: a Streamlit page's sab_text.py).
- **The client:** client/kernel_values.py (type_name, is_table, namespace) for six modules; cli/api.py takes
  push_client.info_file. lineage_values, domain/approvals and domain/html_cells keep their own `_cut` and
  `_namespace`: each travels as a standalone file.
- **Commands:** cli/commands.Registrar is the base's `@command` and each extension's (`command =
  Registrar(COMMANDS)`).
- Lines: src and extensions 131,165 -> 130,840 Python lines (399 added, 724 removed); tests +147 / -35.

## The canvas's property pane, and a designer as flexible as WinForms and WPF (the owner, 2026-11-19; built, branch canvas-designer)

The owner: "I think we need a property pane for everything on the app canvas, and ways to see all things
related to the canvas. For example if it relies on a table or variable, I should be able to click through and
see that table and variables. From here we can edit things in Streamlit like state and cache as well for a
widget." Then: "Take a pass at making the canvas far more usable. Think about WinForms and WPF. Let's aim for
a canvas as flexible as that." Decided with the owner: edits are BOTH, clearly split (Now: the running app
only; Default and cache settings: the cell's code); a table it uses opens beside the canvas.

**Built.**

- **One pane** (App mode's Properties, `canvasPane.ts`; `GET /streamlit/apps/{app}/inspect`): a block, a page,
  or the app. Properties as a grid (Categorized or A to Z, a search box, the focused property's line at the
  foot, right-click: Reset to default, Bind to…, Go to cell); Uses (tables opened beside the canvas with their
  columns, steps in words and first rows, Open as grid; variables to the Variables page; connections; the cells
  that make the names it reads; Used by; a line of its lineage, from `domain/lineage.py`'s graph); Streamlit
  (State: key, Now, Default; Bindings; Cache: the decorator's settings, Cache this function, Clear this cache);
  Events (Add handler); Code (the exact code the page runs for the block, read-only, Go to cell).
- **Writing back** (`domain/widget_code.py`): the call or decorator is found with Python's parser and ONLY its
  characters change (golden before/after files: comments, spacing and line breaks stay). The server answers a
  plan; the window makes it in the open document like typing (the editor's Undo takes it back, and so does the
  canvas's: one history). Code that is not a plain value is refused in words and shown read-only.
- **Now** (`POST …/now`): a numbered file in the running app's own temporary folder, read at the page's start;
  each session makes what it has not made yet, once; a session started later starts fresh. Clear this cache
  runs after the blocks (the function is defined by then) and the page runs once more.
- **The designer:** the Toolbox (`domain/toolbox.py`: every element with its properties as data; a drop makes
  the cell in the app notebook and its block); layout containers (columns by their ratios, tabs, expander,
  container, form, sidebar, popover) that hold blocks and each other, each slot a 12-column grid of its own,
  kept in the app's file (version 2 only when a page uses them) and exported as plain Streamlit; the Document
  Outline (select, move, hide, lock); multi-select (Ctrl+click, a rubber band), align, same size, distribute
  and Reset layout as one change (`domain/designer.py`); snaplines and equal-gap markers (`canvasSnap.ts`);
  Shift+arrows, Ctrl+C/V/D, Delete; events and bindings; the ruler, Wide/Centered/Phone, sample rows.

**Decisions.**

1. A container is the canvas's own (no cell behind it): `page.containers` beside `page.blocks`, so everything
   that reads a page's blocks (the run order, lineage, controllers, the Connections page) is unchanged.
2. The layout is still drawn first as empty slots, and each block runs in its own slot: a container is opened
   where it sits (`_in_c1 = st.columns([2, 1])`, `_in_c2 = _in_c1[1].tabs([...])`), not as a `with` around its
   blocks, so the run order by names keeps working across containers. The Streamlit drawn is the same.
3. A form's button is the form's own (`applied = _in_c4.form_submit_button('Apply')`), named when asked.
4. Hidden is design-time only (Visual Studio's): the page still draws the block. Locked refuses a move or a
   size on the server, so the agent's commands are refused the same way.
5. "Reopens on the canvas identical" is the app's file: written, read back, written again byte for byte; the
   export made from what was read back runs under AppTest. Reading exported Python back into a canvas is not
   built (the canvas's file is the source; the export is its output).
6. The app's file holds no block ids (as before); a container has one (blocks name their parent by it).
7. Wide and Centered on the design surface ARE the app's layout setting (one truth); Phone only narrows the board.
8. The State panel stays as the whole session's list; the pane is where a selection's state is seen and set.
9. Snaplines: the grid snaps every move to a column, so the guides say what lines up (edges with edges,
   centres with centres) rather than pull; the maths (`snapped` too) is tested as the page runs it.
10. The binding lines on the board are the existing wiring (the names a block makes, to the blocks that read
    them); a binding to a session state key is listed in the pane, not drawn.

**Not built (said plainly).** SQL and DAX cells as canvas blocks (a `%%sql` or `%%dax` cell is not offered to
a page today: `linkable` takes Python, Markdown and HTML cells; the portable translation is the script
exporter's and needs its connection pieces); wrapping independent blocks in `st.fragment` on export; a cache's
hits and size (Streamlit exposes none cheaply); a vertical ruler (rows are as tall as what they draw); opening
a connection's own card from Uses (it opens the Connections page); the agent changing a cell's code in an app
opened without a window (refused with the fix: open it in the Workbench).

## Export to Power BI… from the ERD page (the owner, 2026-11-19: "Make a powerbi desktop file with our model exported an option on the erd page"; built, branch powerbi-export)

SAB builds the dataset (tables and relationships); the user builds the report in Power BI Desktop. Decisions:
- **The file is a Power BI Project (.pbip)**, Microsoft's documented text format (never the binary .pbix): the
  .pbip, `<Name>.SemanticModel/` (definition.pbism 5.0, TMDL: database, model, relationships, expressions,
  tables/) and `<Name>.Report/` (definition.pbir 4.0 by path, the smallest PBIR report: one empty page). In
  the open project's `powerbi/` (written only when bytes change; an earlier export's stale table files and
  rows removed, so Power BI never reads a table no longer ticked); with no project, a zip of the same folder.
  Byte-stable: sorted tables, CRLF (Power BI Desktop's own end of line), lineage tags uuid5 of the names.
- **Types:** int64, double, decimal, string, dateTime, boolean; anything else string, said in the dialog.
  Columns a key or join names are `summarizeBy: none`, other numbers `sum`.
- **Relationships:** one column each side and the same type (else left out, said); the one-active-path rule by a
  union-find over the active joins, strongest first (the evidence's percentage, then the model's order).
- **Power Query:** one table-driven domain file (domain/power_query.py): SQL Server/Azure SQL, PostgreSQL,
  MySQL/MariaDB, Snowflake, Databricks, Oracle, Dataverse's SQL endpoint, SharePoint lists, CSV/Excel/Parquet
  files, Data Lake Parquet, Delta and OneLake Delta. A connection's settings are read from its code
  (blades.detect_settings): `${NAME}` becomes a Power Query parameter (its value the variable's shareable plain
  value, else empty); a user name or password is never a setting, so never written.
- **Steps:** a database table's steps go as the source's own SQL (sqlglot from DuckDB), as a native query;
  DuckDB's own SQL that sqlglot would pass through unchanged (GROUP BY ALL, SELECT * EXCLUDE/REPLACE, QUALIFY
  where the dialect has none, COLUMNS) and unknown functions are refused and said: the table goes without its
  steps. A file goes as it is (said).
- **No source Power Query can read** (pasted, pushed, a "+" query, Python, an API, a Power BI dataset read with
  DAX): Include its rows writes Parquet into `<Name>.SemanticModel/data/` (Git-ignored), read from a
  `DataFolder` parameter; the agent's export with rows waits for the user's Allow.
- **Open in Power BI Desktop** (Windows, when .pbip has a program) or Show its folder: the user's click only.
- Release note (pending): "Export to Power BI… on the ERD page: your tables, relationships and each table's
  Power Query as a Power BI Project that Power BI Desktop opens with a double-click."
- **The Power BI extension** (the owner, 2026-11-19: the Power BI work is an extension): extensions/powerbi
  (swissarmybench-powerbi), available in the Extensions catalog. The base gained one generic seam: an on
  extension's PAGE_ACTIONS ({page, id, label, icon, title}) in every mode's `page_actions`; the ERD draws them
  and a click runs the web plug-in registered under that id (web/src/pageActions.ts). The agent's command is
  `powerbi_export` (its own prefix, its guide topic powerbi.md).
- **Use an existing report's pages** (the owner, 2026-11-19: "replace a current Power BI report's model by dragging
  and dropping a pbix into the app"): in the dialog, a drop zone and Choose file… (.pbix, .pbit, .pbip); the
  report's pages, visuals, themes and bookmarks go into <Name>.Report/ pointed at our model (definition.pbir by
  path). A .pbix/.pbit is read as a zip: Report/Layout (the legacy layout, UTF-16 LE) is written as report.json
  (PBIR-Legacy, which definition.pbir 4.0 opens), or a PBIR definition/ folder as it is; StaticResources too.
  DataModel is never opened. Every field the visuals, filters and slicers name (Entity/Property, a query's From
  aliases, queryRef) is mapped by name in any case; unmatched ones get a picker or Leave it; a left field keeps
  its name (its table follows the table's mapping). The report's own measures (modelExtensions) and the model's
  measures (a .pbit's DataModelSchema, a .pbip's TMDL, a .pbix's through pbixray) are rewritten through the
  mapping; a measure naming an unmapped column is said, not written. A browser drop sends the file's bytes
  (POST /powerbi/report: kept in memory, the last one only); a chosen file goes by its path. The agent:
  `powerbi_export` with `report`, `mapping` (and `dry_run` for the proposed mapping).
- Later phases asked for on 2026-11-19 (the import, a .pbix file connection by pbixray, Edit in
  Power BI Desktop, the gated Power BI project type): not built on this branch yet.

## The canvas's remaining work, then Launch, builds and the Performance Analyzer (the owner, 2026-11-19; built, branch canvas-rest)

The owner: "did we add DAX cells to the canvas?" (no, then), and: "One of my biggest concerns we should tackle is
performance over the web socket ... we also need a performance analyzer. This will be a separate tab. Not a rail
icon, just a separate window that can be launched from the app canvas ... Also ... build a way to launch the app
canvas in a new tab ... along with a build version history every time we launch, think Visual Studio." Decided
with the owner: builds live in the project folder, shared in Git ("we just have apps in folders"); the analyzer
records only when it is opened.

**Built.**

- **SQL and DAX blocks.** A `%%sql`/`%%dax` cell is a canvas block. Its page code is the script exporter's own
  reading of the cell (`domain/script_export.py` `query_cell`, which `plan` now uses too: one translation) as a
  call of `sab_queries.py` beside the pages; `domain/page_queries.py` writes that module from the exporter's plan
  (`_shared`: each connection's own code, its settings read from the environment, no password) plus the page's
  `sql`/`dax`. `{{ name }}` in a query is a page value (read outside strings and comments by one scanner, the same
  text in the domain and in the page): SQL binds it in the driver's paramstyle, DAX writes it as a literal
  (text, numbers, TRUE()/FALSE(), BLANK(), DATE(), {lists}). Queries run on one worker thread (a connection is
  used from the thread that made it: SQLite and others refuse a second). The block's **view** (table; bar, line,
  area chart with x and y; metric; cache off) is the block's own, in the app's file. The pane's SQL/DAX query
  section: connection (the cell head's picker), Result, Show as, Cache (on by default, said), Parameters (each
  with the block that gives it), the tables its query names (sqlglot; a DAX block's dataset's tables when its
  catalog is loaded). The Toolbox's SQL query and DAX query make the cell (named `query_<n>`, its result's name)
  and the block; the Streamlit cells panel lists them under Queries; a query block wears its connection's colour.
- **Fragments.** `fragment_blocks`: a block that calls an input widget, whose names no other block on the page
  reads, that does not read a name before making it, that sits in no form or sidebar, and whose code runs as a
  function body unchanged, runs as `@st.fragment` (Play, export, Save as). The pane says Reruns: Alone or The
  whole page. Query blocks are cached by default (`st.cache_data` on the query and its values).
- **The designer's gaps.** Session state bindings drawn on the board (dashed, the key on the line) from each
  block's `state_keys` and `state_reads`; several blocks: every shared property (place, size, Locked, Hidden, a
  query's Show as, each property of the element their cells share, Mixed where they differ; a widget's key
  never); Add to app on each live cell (the app in front, else the first open, else a new one); Uses opens a
  connection's own card (open=connections&at=detail&name=) and a variable at its name (open=variables&name=).
- **Launch** (the canvas's Launch, Ctrl+F5; F5 with the analyzer): the export written as a build in
  `builds/<app>/<n>/` (app.py, app_pages/, sab_queries.py, data.py as made, requirements.txt, README.txt, the
  canvas's file, cells.json, build.json: number, time, the canvas's hash, what changed in words, result, first
  load, saved sessions; sorted JSON), then a run folder of its own (the same export with each block timed for the
  analyzer and the window's title "<app> · build <n>", the tables as Parquet, sab_perf.py) served under
  /streamlit/launch/<key>/; the page opens it with window.open (the desktop app's own window, a browser's tab).
  Builds: newest first; Compare (Monaco's diff editor); Open (read-only); Relaunch; Restore (each cell whose
  code differs, as a plan the window makes like typing; the layout). Every build is kept (`keep` can trim).
- **The Performance Analyzer** (`/streamlit/perf?app=`, its own window): attaching switches `sab_perf.on` in the
  run folder and the proxy's tap (`streamlit_proxy.routes(tap=)`) keeps each websocket message's kind, element,
  path and size (`domain/perf.py`'s protobuf wire reader; tested on messages Streamlit's own classes wrote,
  tests/golden/perf). sab_perf.py beside the pages records each rerun (its blocks' times, sab_queries' queries,
  urllib and pandas reads, each cache's calls and misses with argument digests, each dataframe's shape). The
  trigger is the browser's own ask (the widget whose value changed), else the page's. Tabs: Timeline, Calls,
  Cache, Web socket, Hints; Pause, Clear, Save into the build (perf-<time>.json); saved sessions open from Builds.
  Hints: a table sent whole each rerun (≥1 MB), a block that reruns (≥50 ms) though it reads nothing the changed
  widget gives, a cache that always misses (the argument new each call), a slow query (≥200 ms) run again with
  the same text, many small messages (≥200 under 300 bytes) in one rerun.
- The agent: `streamlit_block_change` view=, `canvas_add` element=sql_query/dax_query, `app_launch`, `app_stop`,
  `builds_list`, `builds_compare`, `build_relaunch`, `build_restore`, `perf_attach` (pause, clear, detach,
  save), `perf_session`, `perf_hints`.

**Decisions.**

1. `{{ name }}` names a page value in a query (as text cells already do); `${NAME}` stays a variable.
2. The build is the plain export; the run's copy adds the timing lines and the window's title (so two builds
   compare by their code alone, and the analyzer costs nothing until it is attached).
3. An old build relaunches as built: its blocks are not timed (the socket is still recorded).
4. The trigger comes from the socket: the first ask seen after attaching holds every widget, so it says
   "rerun" rather than guess.
5. A fragment's own reruns are seen on the socket; the page's records time only full reruns.
6. Streamlit keeps a dataframe it has sent (ref_hash): only a table not sent before travels again, so the
   big-table hint counts what really travelled.

**Not built (said plainly).** `{{ name }}` in a %%sql/%%dax cell run in the notebook (the kernel sends it
as typed: the value is the page's); `${NAME}` in an exported SQL query (the script exporter's own gap); a
setting in Settings for the number of builds kept (the service takes `keep`; the default keeps every one);
Restore for an app opened without a window (refused with the fix); the analyzer for Play (it attaches to a
launch); window titles from a page settings title (the settings' title wins).

## A first run, empty pages and the layout: feel-c (the owner, 2026-11-19: approved from the feel survey; built, branch feel-c)

Survey items 7, 8, 9, 12, 13 and 15.

- **Empty pages lead somewhere** (web/src/emptyState.ts): Connections, Variables, Session and a kind's landing page in
  the Workbench (Notebooks, Scripts, Apps) show their icon, one sentence, the primary button (Add connection, Add
  variable, Launch Claude, New notebook / script / Streamlit app) and **Try it with sample data**: the made-up
  sample store (domain/sample_data.py: customers, products, orders; the same rows every time; orders join both)
  opened under free names (POST /samples/store, `datasets_sample`), then the grids. Variables has no sample
  (tables are not variables); in the Workbench the sample is followed by a new document of that kind, so its
  Tables group lists them. A new notebook's first Python cell, empty, says "Shift+Enter runs · %%sql for DuckDB
  SQL · drag a table here" faintly (Monaco's placeholder: gone at the first key).
- **The finder draws at once** (relationshipsDialog.ts): Find relationships adds the confident joins (80% or
  more) straight away, with one Undo in the toast in place of Accept the ticked joins, and draws them as the ERD
  (Mermaid, the same lazy drawing) beside the list as a side panel; a row's tick adds or takes out that join
  (each with Undo). The confidence bars are green when sure and grey otherwise, never the brand red. Draw diagram
  (to Analyze) stays in the foot; erdView.ts is not changed.
- **Add connection** (connectionsWindow.ts): the back button and the crumb at the top (as a connection's detail
  has them), a search box focused on arrival (type to filter by name, id or group; Enter opens the first left;
  "No connection type matches."), and the kinds this browser opened last first in their own group (localStorage,
  a convenience: no duplicated tile, so each tile stays one).
- **Projects** has **Open a file…** and **Paste data** beside New project and Open project… (openFile.ts
  pasteData: a box a copied table is pasted into; it opens as a grid at once, named pasted_<time>). **Ctrl+K**
  (dataExplorer.ts) puts the results used last first as **Recently used** while nothing is typed (each taken
  out of its kind's group, keys only, in localStorage), and its foot says the keys (↑ ↓ move · Enter opens ·
  Esc closes). Recent notebooks are not in Ctrl+K: it finds data, and the Notebooks page lists them.
- **The rail's names** (rail.ts): the rail shows each area's name beside its icon (176px) until the user turns it
  off: the toggle at its foot (Icons only / Show names) or the right-click menu. This computer's choice, kept in
  the state folder's `rail.json` (GET/PUT /rail, `app_rail`), every window following (`rail_changed`); the last
  one is also remembered in the page so it opens without a jump. Under 900px wide the rail is the icons alone,
  whatever the switch. The icon rail itself looks as before.
- **Close a project from Projects** (the owner, 2026-11-19: "I should be able to close a project from the project
  home"; projectExplorer.ts): while a project is open, its card (marked Open) and the page's top line ("<name>
  is open") each carry **Close project**: projectFile.ts's close as before (unsaved changes asked about; Autosave
  saves first); the Projects page stays and the Open mark goes. The agent's is `project_close` (already there).
- **Layout** (gridView.ts, grid.css, ribbon.ts): a short table's columns grow in proportion to fill the width
  (at most four times their own; a column the user drags or Auto width stops it for that grid); the
  Application row takes no band while it is empty (no project open); the Table row's tools that fold to an icon
  say what they do in their tooltip. None of them has a key of its own today, so no key is named (feel-b's
  shortcuts overlay is where keys are added).

**Release notes (pending):**

- **Every empty page leads somewhere:** one line of what it holds, the button that fills it, and **Try it with
  sample data**, which opens three made-up tables (customers, products, orders) to play with.
- **The rail shows its names** beside the icons; **Icons only** at its foot (or a right-click) brings back the slim
  rail, and the choice is remembered.
- **Projects:** **Open a file…** and **Paste data** sit beside New project, so a file or a copied table opens
  without making a project first.
- **Find relationships** adds the joins it is sure of straight away and draws them, with **Undo**.
- **Add connection** has a search box and the kinds you used last first.
- **Ctrl+K** shows what you used last first, and the keys at its foot.
- A short table fills the window's width, and the empty Application row is gone.
- **Close a project from Projects:** the open project is named at the top with **Close project**, and its card has one too.

## Everyday comforts (the owner approved the feel survey, 2026-11-19; built, branch feel-b)

The survey's items 3, 4, 5, 6, 10, 11 and 14. Decisions:
- **Filter by ticking values (3).** The Filter form starts on the selected column (the Table row's Filter
  too, not the first column) and, for text and numbers, on "is one of" with a checklist: the column's values
  most common first with their row counts, a search box (any case, a plain substring: `%` is text), Select
  all over what is shown, the ticks kept while searching. Blanks are not a value to tick ("is blank" is its
  own condition); the foot says how many. The values are the view entering the step being edited (`upto`).
  `GET /grids/{id}/values?column=&search=&limit=&upto=` (200 by default, 2,000 at most, `more` when cut),
  kept by view key in Profiles' cache; the agent's `column_values` (tool budget 86,600).
- **Keyboard shortcuts (4).** `?` outside a text box and Ctrl+/ outside an editor (Monaco keeps Ctrl+/ for a
  comment) open one sheet built from the same command list as the palette (8.3): every command with keys, by
  group, with a find box. The Workbench registers it as `help.shortcuts` (the agent's workbench_window too).
- **The palette (5).** The grid page lists the ribbon's rows, Steps, Cell and Tabs first; Application,
  Analyze, Launch Claude, updates and beta after. The steps strip's buttons were listed twice (as the ribbon's
  Transformations row and as Steps): once now, as Steps. Any group and title appears once. A command that
  cannot run shows its reason in its row (not only a tooltip). The recently used (the last 8, this browser's
  localStorage, every read and write in try/catch) come first, in both the grid page's and the Workbench's.
- **Undo after a removal (6).** Closing a tab ("Closed orders · Undo": tabs_reopen's route), removing a column
  or keeping only some ("Removed the column region"), removing a step, clearing the steps: a toast with Undo,
  bound to that grid's own steps whichever grid is in front by then. toast() was already able to carry it.
- **A header's numbers (10).** Resting on a header for 450 ms shows a card from the column's profile (the
  server keeps it by view; the page keeps each answer for the same steps): type, blanks, distinct, range,
  mean, a 20-bin histogram (dates: by month) or the three most common values. The native tooltip went. The
  bars are muted, not brand red. **The status bar:** id-like columns (domain/grids.py `id_like`: a whole-number
  column named id, `*_id`, `*Id`, key, code, no, num, number) are counted, never summed or averaged; Sum shows
  the columns' scale (`display_digits`: integers 0, DECIMAL its scale, floats 2), Average at least two; a
  small fraction keeps four significant digits. `cell_selection_stats` answers `id_like` and `digits`.
- **Copy with headers and as Markdown (11).** The cell menu (and the palette's Cell group) has Copy, Copy with
  headers and Copy as Markdown; with no selection the one cell under its column's name. The export gained
  `format=md` (domain/export.py `markdown_table`: pipes escaped, line breaks as `<br>`, number columns
  right-aligned). A right-click into a block no longer collapses it to the clicked cell (the focus change
  counted as a keyboard move).
- **Run feedback (14).** A cell's head shows "Running… 3 s" once a run passes a second, then the time it took
  ("320 ms", "4.2 s", "2 min 5 s"). The first run gates the cell with loading.ts's busy() "Starting Python…"
  (8.12); Kernel.ensure() now shares one start between callers, so two runs never start two kernels. A cell
  that has run keeps its Name box showing (faint) instead of only on hover or selection.

Release notes (pending):
- Filter lists a column's values with their counts: tick the ones to keep, search to find one.
- Press ? for every keyboard shortcut.
- The command palette leads with the table's commands and the ones you used lately, and says why a command is off.
- Closing a tab, removing a column or a step, and clearing the steps can be undone from the message they leave.
- Rest the pointer on a column header to see its numbers and a small histogram.
- The status bar never sums an id column, and shows Sum and Average to the column's scale.
- Copy with headers and Copy as Markdown on a cell's menu.
- A notebook cell shows how long it ran, and says "Starting Python…" on the first run.

## Feel, part A: SQL sees the open tables, and the polish bugs (the owner approved the feel survey, 2026-11-19; built, branch feel-a)

### Built
- **A DuckDB SQL cell sees the open grids by their names** (`%%sql` with no connection, `sab.sql(query)`, a
  Workbench SQL cell on DuckDB): when DuckDB says a table is missing and a grid of that name is open (any case),
  the kernel asks `GET /workbench/tables/{name}/arrow` for the grid's view, its steps applied, every row, and
  registers it for that one query (`orders: the open table in Grids, 20,000 rows as its grid shows them`).
  Read-only, read again on every query, never kept in the kernel; this Python's own table of the name wins. At
  most 20 such tables a query. The server audits each read (`table_read_by_sql`).
- **The missing table's error** (domain/errors.py): DuckDB's "Table with name X does not exist!" is caught
  (`missing_table`); a "Did you mean" naming one of DuckDB's own tables (pg_*, duckdb_*, sqlite_*,
  information_schema, pragma_*) is dropped from the message and from the fixes; a close name of the user's stays
  a fix. The explanation says the table this query cannot see, and the panel's words point "above", where the
  message is. When the name is open in Grids (a Python cell's `duckdb.sql(...)`, or the app away) the first fix is
  "orders is open in Grids: add its table cell" (kind `table`): the document takes the table's read-only cell
  (workbenchPage.ts giveTable; a cell already in another document stays there and that is said). The agent's
  `workbench_window` command `tables.add` does the same. A SQL cell's raw `UsageError:` text is no longer
  printed above the panel: the panel says it once.
- **Polish:** tabs fill a row before they wrap (each tab's basis its least width, up to 200px, the name
  ellipsed with its full name on hover; the front tab its whole name; another tab's × on hover or focus, as
  browsers' narrow tabs), so nine tables sit on one row at 1024px; the palette's "No matches" inside the
  list's inset; Find data closes on one Escape (text or not) and Ctrl+Shift+P closes it before the palette
  opens; Settings' boxes keep their lines at the top (no spread radios, no tall Beta buttons), Claude's two
  pickers line up with the path's room (Check for updates left to the coordinator's change), the agent prompt names "the Swiss
  Army Bench MCP server"; the tour is one button (the "New here?" bubble on a first visit, Tour once seen: grid.css hides Tour while the
  bubble is there);
  every search box without a style of its own looks like the other inputs; a relationship's "inactive" and
  "in use" badges keep a space; the ERD's status bar says ERD only; a cell's kind and connection pickers are
  quiet, the app's own (border on hover, a drawn chevron; the system's in forced colours).

### Decisions
- The grid's view goes over as Arrow on demand, not a view in the kernel's DuckDB: the kernel is another
  process; the read is per query so a step changed in the grid is seen by the next run.
- Only a missing **undotted** name is looked up (a dotted one is a connection's table, already handled).

### Release note (pending)
- A notebook's DuckDB SQL reads the tables open in Grids by their names, with their steps.
- A missing table's error is said once, without DuckDB's own-table guess; a table open in Grids is one click
  from its table cell.
- Tabs fit nine to a row at 1024px; Find data closes on one Escape; Settings' boxes tidied; one tour button.


## The Power BI extension, part 2: a .pbix as a project (2026-11-19, the owner's calls; built, branch powerbi-2)

Built in the extension (backend and data); the base gained only generic seams.

- **Two paths that never cross.** Reading a .pbix is pbixray's only (domain/pbix_file.py, adapters/pbix_reader.py);
  editing is the live Power BI Desktop link only (domain/live_link.py, adapters/live_link.py). Nothing matches a
  pbixray connection to a live link. The one exception is Read Power BI from's Local source.
- **C, the .pbix file connection:** a Python connection (Connect, List the tables, Read a table) whose code reads
  the file with pbixray; tagged `powerbi file`; its path `${NAME}`-able; "as of" its last refresh; read-only and
  why; the portability note for a path on this disk. Its relationships are offered to the ERD.
- **B, the import:** `POST /powerbi/import` (`powerbi_import_project`, dry run first): connections per distinct
  source (reused by kind, server and database), Power Query parameters as plain variables, the published dataset
  (a thin report's own; else by the file's name; several or none: asked), the file connection, `.sab/powerbi.json`
  (each table's M and its Source SQL's digest, measures with folders and formats, relationships), data.ipynb,
  relationships into the ERD, each table as `<Table>_Source` and `<Table>_PowerBI` grids with a Compare. The
  import always finishes: what failed is listed. Round trip rules: round_trip_m and with_native_query (an untouched
  table's M byte for byte; a changed notebook query as a native query). **Not wired yet:** part 1's export reading
  `.sab/powerbi.json` (the rules are there and tested).
- **H, To finish setting up:** rows for the app registration, the published dataset, a source's password, a source
  kind we cannot read; each with one fix; `powerbi_setup_status`.
- **G, app registrations:** a base library item (`app-registrations/<name>.toml`: three variable names). Test and
  Check again make an access report (sign-in, workspaces, datasets, one COUNTROWS through executeQueries) kept as
  `<name>.access.json` (names, marks, reasons, time, computer); `GET /connections/{name}/access` is a connection's
  Access section. Non-Power BI connections say "not checked" with why (Azure SQL, Dataverse, SharePoint and lakes
  are not reached yet). The Power BI project's choice re-points its SQL Server sources after a dry run.
  **Left out:** the Access section drawn on the Connections page, and context.md's one line per connection.
- **E, Read Power BI from:** Published | Local, kept in .sab/project.json (`powerbi_source`); the file is the
  fallback, said. The `_PowerBI` grids read again on a switch. **Left out:** `%%dax` cells and DuckDB SQL following
  the switch with no code change (they name the workspace connection as before).
- **F, gates:** a mode's `areas`, `first_open` and `tour`; `GET/POST /app/gates` (`app_gates`); rail.ts hides a
  closed area, an address or a goArea to one shows one line with Open every feature; Settings' Open every feature
  in this project; the first-open pop-up once per project. An extension's rail area with a `panel` route is drawn
  from data (extensionArea.ts; extensionPanel.ts gained choices, rows and notes). **Left out:** the palette's and
  the Workbench's New entries asking the gates; the tour's own card list (the mode carries it).
- **D, Edit in Power BI Desktop:** discovery every 15 seconds while wanted (Windows), status pushed
  (`powerbi_live`), the open model as names, a dry run, Apply through TOM (pythonnet, Windows marker; Microsoft's
  model client libraries 19.82.0 net45 fetched once, SHA-256 pinned). Agent: `powerbi_edit_files`, `_model`,
  `_plan`, `_apply` (Allow).
- **Opening a file:** an extension's `OPENS` (suffix: route); `swissarmybench open report.pbix` and a dropped file
  are offered on the Power BI page (Make a Power BI project for it; Import its model; Use its pages on our model).

Release notes: Power BI projects from a .pbix; the .pbix connection; app registrations with access reports; Read
Power BI from Published or Local; project types that keep features closed; Edit in Power BI Desktop (Windows).

## The Power BI extension, part 3: what part 2 left (2026-11-19, the owner's calls; built, branch powerbi-3)

Part 2's "not wired yet" and "left out" lines, each built:

- **The round trip:** part 1's export reads `.sab/powerbi.json` and data.ipynb (`PowerBIProject.kept`, set on
  `PowerBIExport.kept`): each kept table goes in place of its two grids, an untouched one with its M byte for byte,
  one whose `<Table> source` `%%sql` cell changed with the new native query (Sql.Database's Query option, else
  Value.NativeQuery; its Power Query parameters still named); the measures with their display folders and formats
  (another report's brought measures added after them, by table and name). The import now keeps each table's
  columns and types (pbixray's pandas types as Power BI's); an older state takes its Source grid's columns. A
  calculated table (no M) stays out. Rules: `pbix_import.round_trip_tables`, `notebook_queries`, `kept_measures`.
- **The switch reaches everything:** the project has ONE dataset connection name, the model's (`dataset_name`),
  which is not a saved connection but resolves through Read Power BI from. A generic base seam,
  `hooks.dataset_aliases`: connection tables list and read it (DuckDB SQL `[Sales model].Customer`: Published reads
  the workspace's dataset, Local Power BI Desktop's open model by DAX, else the file; a read is kept per source, so
  a switch reads again), and a kernel's `%%dax 'Sales model'` cell (client/sql_cell.py asks
  `GET /connections/sql/alias`, then sends its DAX to `POST /connections/sql/alias/dax`, Arrow back, the source's
  words printed). The import scaffolds its `%%dax` cells against that name. The file answers whole tables only
  (`EVALUATE 'Sales'`), refused in words otherwise. Compares follow because the `_PowerBI` grids are read again in
  place (the grid kept); the import's Compare now names its key (a relationship's column both grids have, else the
  first shared) and keeps its id (it read a key that was never there).
- **The Access section drawn** (web/src/connectionAccess.ts): on a connection card's detail, each registration that
  signs it in: its one line, when and on which computer it was checked, each item (✓, ✗ with reason and fix, not
  checked with why), Check again. A registration's sign-in is part of each connection's section. context.md's
  Connections says each connection's access in one line, its Project the gates of the open project.
- **The other Microsoft kinds checked, read-only** (adapters MicrosoftProbe): Azure SQL (mssql-python with the token:
  the databases it sees, SELECT TOP 0 on its catalog's tables; no driver here: not checked, said), Dataverse
  (WhoAmI, its security roles' names), SharePoint (the site, its lists' and libraries' names), OneLake and Data
  Lake (one listing of the named path; a Delta root on abfss:// too). Re-pointing (`signed_in_with`) makes any of
  those kinds sign in with the registration: its kind's app-registration starter, its place settings carried by
  their keys (a `${NAME}` kept), the secret as `os.environ[...]`. A folder, S3 or on-premises kind is left alone.
- **Gates everywhere:** the palette (Command.area, else `areaOfCommand` by id) and the Workbench's New entries
  (`gatedRun`) show the one line instead of running; the agent's commands are never gated. An address that lands
  on a closed area is covered by the line (a popover beside the rail, so a page layer shown before it is covered
  too). The tour on a gated project is its greeting then the mode's own cards.
- **The Power BI page's actions:** Edit in Power BI Desktop shows its dry run on the page (the generic panel's
  `review`: each change, Apply, Cancel; the agent's Apply waits for the user's Allow); Use another report's pages
  opens the export dialog right there with its report part first (the panel's `open`: a plug-in by id,
  pageActions.ts openPlugin).
- **mcp/index.md:** Power BI's key tools and app registrations' access in the table (trimmed elsewhere to stay
  under 4,000 characters); the powerbi guide topic says the round trip, the switch, the access report and gates.

Not done: grid titles saying the source ("Sales model · Local") beyond the status words; the Workbench's status
bar showing it.

Release notes: a Power BI project's export writes its original Power Query back (a changed notebook query as a
native query); its one dataset connection follows Read Power BI from in SQL, DAX cells and Compare; a connection's
Access section; access reports for Azure SQL, Dataverse, SharePoint and the lakes; closed features stay closed in
the palette, the New menu and the tour; Edit in Power BI Desktop's dry run on the Power BI page.

## Trino's client certificate from a key vault (the owner, 2026-11-20: "we need to make it possible that certificates can be retrieved from the vault for the Trino connection"; built, branch trino-vault-cert)

- **Three ways to sign in** (domain/keystores.py SIGN_INS): Username and password; **Client certificate (from a
  key vault)** (TRINO_VAULT, before the file's way: its code holds the file way's mark too, and the form takes the
  first that fits; its own mark `keystore = os.environ["`); **Client certificate (a file on this computer)** (the
  old keystore way, renamed).
- **The vault's value is the keystore:** `keystore = os.environ["NAME"]` (the box's `${NAME}`, a vault's variable).
  keystore_files reads a value that is not a file's path as base64 PKCS#12 or JKS (by the decoded first bytes) or
  PEM text (a BEGIN line; the leaf found by its public key), the same reader, the same 0600 files removed at exit.
  A file's PEM works too now. An error never holds the value (a long value is "neither a file's path nor a
  certificate", the variable named).
- **Its password:** `keystore_password`, a variable or none (Key Vault's own have none). The one password that is a
  setting, and only as a variable or empty (certificate_files.VARIABLE_ONLY): a typed value is refused by
  blades_fill, so it never lands in the code. Every other password stays `secret("...")`.
- **Every certificate file from a vault:** a certificate file setting (verify, sslrootcert, sslcert, sslkey, ssl_ca,
  ssl_cert, ssl_key) whose box is exactly one `${NAME}` (no default) is written
  `certificate_file(os.environ["NAME"])`; CERTIFICATE_FILE is put in the code while a setting uses it and taken out
  with its last use. A path as itself; PEM text (or base64 of it) as a 0600 file in a 0700 folder removed at exit.
  `${NAME:-path}` stays the plain mapped path (a default says it is a path). A keystore is never wrapped.
- **No amber note on the vault way:** Trino's CA `verify` defaults to empty (the system's trusted authorities) in all
  three ways, so the password way and the vault way run on a Function App; the file way keeps the note. A path typed
  into a certificate's box brings the note back, as before.
- **The export:** a setting's variable a vault maps (or a vault that loads every secret gives, for a `${NAME}` with
  no default) is FROM_VAULTS, read by the vault's own code where it runs (script_export.setting_sources), and the
  vault is written out; the certificate is never in the script.
- **The agent:** the same through connections_test, connections_add and blades_fill (the golden rule); no answer
  holds the certificate. No new command.
- **Release note:** Trino signs in with a client certificate from a key vault (base64 PKCS#12 or PEM), and any
  certificate file (PostgreSQL, MySQL, Trino's CA) may come from a vault's variable; it runs on a Function App.

## Find connections on this computer (the owner, 2026-11-20: "Is it possible to scan the computer's common apps for connections and import them. DBeaver, SSMS, ODBC, etc." / "You could scan the app directory for hints of what to search for"; built, branch find-connections)

- **Release note:** Connections, **Find connections on this computer…**: the connections DBeaver, SSMS, ODBC, Azure
  Data Studio, VS Code, JetBrains, pgAdmin 4, MySQL Workbench, HeidiSQL and Office keep, and a few seconds' search of
  the app settings folders, listed in one place to tick and import; never a password.
- Built: domain/found_connections.py (the model, parsing, the list, the import body), domain/found_readers.py (the
  readers as data and pure functions, PLACES per system, the hint scan and what it never opens),
  adapters/found_connections.py (files per system, the registry through a seam, pgAdmin read-only, the walk with
  its caps and Cancel), services/found_connections.py, routes_found_connections.py, web/src/findConnections.ts;
  `connections_find` and `connections_import_found`, both on the user's Allow.
- Decisions: on the click only, read-only; no Found field can hold a password, every string scrubbed again;
  nothing found is kept but in memory (the last list, for import by id) and the audit says counts only. An ODBC data
  source whose driver we have a connection for, with its server, imports as that kind (SQL Server on mssql-python,
  portable); else as an ODBC data source (amber). Windows sign-in imports with SQL Server's windows way (amber). A
  connection's name keeps letters, digits, spaces, `_ - .` (Shop (dev) -> Shop dev). A `Server=` + `Database=`
  string with no driver named reads as SQL Server (.NET's SqlClient). The password is
  `secret("<NAME>_PASSWORD")` and that keyring variable is declared, not set (Needs a password on its card).
  Already added is the same kind family (SQL Server and Azure SQL; MySQL and MariaDB), server (localhost, ., (local)
  and 127.0.0.1 alike; a named instance its own) and database, or the same file or data source. The hint scan reads
  JSON, XML, .config, INI, .properties, TOML, YAML (strings only), .conf, .dsn, .odc, .udl up to 256 KB, 4 levels, 4,000
  files, 4 seconds; Windows AppData Roaming and Local and ProgramData, macOS Application Support, Linux ~/.config
  and ~/.local/share (not /etc: only its odbc.ini is read). SSMS 17's SqlStudio.bin (binary) is said, not read.
- Open: Power BI Desktop is left to the Power BI extension; a YAML object (host, port, database) is not read as an
  object (no YAML in the domain); Toad, Navicat, SQL Developer, Snowflake's SnowSQL config and DataGrip's
  per-project user names beyond dataSources.local.xml are not read yet.


## A key vault's variables kept over a restart (the owner, 2026-11-20: "Every time I update or reopen the app my Vault variables disappear. I have to go to the key vault, open it and read the variables all over again."; built, branch vault-names)

- **Cause:** a vault saved with "Every secret in the vault" (vault_all, the form's default) writes no names to its
  file; they came only from reading the vault (the form, a kernel's start), in memory.
- **Built:** every read of a vault's names is kept in the library's `local/vault-names/<vault>.json` (git-ignored;
  names and each one's variable, the time read; sorted, byte-stable, written only when the names change; never a
  value). The Variables page, the `${` list, context.md, Set up this computer and a Workbench kernel's Variables
  pane read them as the vault's variables at once. Once the first window is open each such vault is read again in
  a child process (a few at once; a vault that signs in with a window skipped); a failure keeps the names and the
  vault's card says "Names from <time>" with Read again. The vault's card shows how many variables it gives. A
  deleted vault's file goes, a renamed one's follows, a file whose vault is gone goes at start.
- **Decisions:** the form's default stays Every secret (the owner's earlier choice). The file's time is when these
  names were first read (a read that gives the same names writes nothing). A draft vault read in the form is kept
  under its typed name (pruned at start if never saved). Read again is the existing `connections_vault_secrets`
  (no new command). `auto_read_vaults` (Settings) is off in the tests' make_client, on in the app.
- **One name, one variable (the owner, 2026-11-20: "make sure that we handle env variable collisions by not
  allowing duplicate variables, and if any overlap in the vault then they get prefixed by the vault name"):**
  domain/vault_names.py assign gives every vault's variables at once: your own variables (variables.toml, local/,
  the keyring) and a vault's explicit entries keep their names; a vault that loads every secret gives a taken
  name as `<VAULT>_<NAME>` (the vault's name upper case, letters, digits and _), then `_2`; two such vaults:
  the one whose name sorts first keeps it. The variable given is kept in the names file, and a name given
  before stays while it is free, so it never jumps between starts (decision: a vault that arrives later and
  sorts first does not take a name already given out; it is the one prefixed). A Workbench kernel's load lists
  every vault first and gives the names by the same function (the server sends your variables' names and
  each vault's kept ones), so the kernel's environment and the Variables page agree; a connection's run gets
  the same names for what is remembered. Adding or renaming a variable, or a vault entry, to a taken name is
  refused: "X is already a variable (from Team Vault). Pick another name." (the agent alike); the vault form
  marks a row that collides as it is typed. The Variables page says why a name is prefixed ("named
  TEAM_VAULT_X: X was taken by Finance"); the `${` list already shows each one's source and vault.
- **The owner's live case (0.0.29):** "I mapped the vars in the vault, then went back to Connections and they
  don't show when I type the dollar-brace." With Every secret ticked the form saves only renamed rows, and the
  listing never named a vault_all vault's variables. Now the form's read names go with the save (vault_names,
  kept in the names file, never in the vault's own file) and the listing gives them at once; the form reads
  the `${` list again after saving. tests/e2e/test_vault_names_page.py does the owner's steps.
- **Release note:** Key vaults that load every secret keep their variables when the app restarts or updates: no
  need to open the vault and read it again. A variable name is never given twice: a vault's secret whose name
  is taken comes as VAULTNAME_NAME. Their names are read again by themselves at start; the card says how
  many variables each vault gives.

## Every connection type against its client (the owner, 2026-11-20: "I saw a lot of connection types that were not actually supported by those clients"; and "the dataverse connection didnt support mfa with user and password"; built, branch connection-audit)

Every starter of the Add connection forms, each way to sign in, checked against the library a fresh install gets
(tests/driver_check.py: compiles; every function, class and keyword exists in the installed library; SQL Server's
connection strings through mssql-python's own parser and Authentication values). tests/test_connection_drivers.py
runs it over every way (a driver not installed is skipped) and again in SWISSARMYBENCH_DRIVERS_PYTHON.

### Fixed and removed
- **Removed** from SQL Server's and Azure SQL's "as you" chain: VisualStudioCodeCredential. azure-identity's works
  only on Windows with the azure-identity-broker package (which the code never installs) and the VS Code Azure
  Resources extension, so it never signed anyone in. The way is "Microsoft Entra: as you (Azure command line, else a
  browser)". A saved code keeps its own chain (Update to the new driver keeps its import).
- **Fixed** Azure Key Vault's "As you (Azure CLI, VS Code or Windows sign-in)": DefaultAzureCredential's VS Code and
  Windows (broker) parts need azure-identity-broker too; now "As you (Azure command line or Azure PowerShell)".
  The amber reason for "as you" no longer names VS Code.
- **Fixed** MariaDB: its starter used the mariadb package, whose wheels are Windows only (Linux and macOS build it
  against MariaDB Connector/C, which a Function App lacks); it is PyMySQL now (MariaDB speaks MySQL's protocol),
  checked against a real MariaDB (the test bed).
- Everything else matched its library: see docs/verified.md for the table.

### The New query page (built 2026-11-20)
- The owner, on the Grids landing and the tab row's "+": "get rid of all of this this should just be a new query
  page, with the active connections and you can click one to start a new grid sql". One page for both
  (startView.ts): Open tables (DuckDB) first while a grid is open, then the connections Query from offers (one rule:
  queryTab.ts queryConnections); a click opens the draft with Query from set and the editor's cursor after FROM.
  Open a file, Paste, Query, Catalog, Add connection and the Projects link left it (the folder button and Ctrl+V
  stay); no connection is the empty state. The agent: app_navigate new_query and query:<connection>.

### Multi-factor sign-in
- A new way, **Username, with multi-factor sign-in (a browser window, or a code on another device)**: Dataverse
  (Web API and SQL endpoint: one sign_in), SQL Server and Azure SQL (after the Entra password), OneLake, Data Lake,
  Delta on Azure (after As you), SharePoint lists and documents (after the two ROPC ways). One class,
  domain/entra.py MultiFactorSignIn: azure-identity's InteractiveBrowserCredential (login_hint the username, the
  tenant), DeviceCodeCredential when no browser opens; TokenCachePersistenceOptions(name="swissarmybench") (the
  system's encrypted cache; none on a Linux without a keyring: that run's memory only) and the AuthenticationRecord
  kept (~/.IdentityService/swissarmybench-<hash>.json, 0600: ids and the username, never a token), so later runs are
  silent and MFA is asked only when Microsoft wants it.
- SQL Server: the token from that credential beside the connection string, not mssql-python's
  ActiveDirectoryInteractive. It exists (mssql-python 1.18), but outside Windows it is an in-memory
  InteractiveBrowserCredential per process with no username hint: MFA on every Test, kernel and run.
- Amber: "Only works on your machine: it needs you to approve the sign-in. On a Function App or hosted Streamlit app
  use an app registration or a managed identity." (portability MFA; before "as you", said once).
- Every ROPC way and SQL Server's Entra password (ActiveDirectoryPassword) says one line on the form (the way's
  `note`): it cannot do multi-factor sign-in, pick the new way. AADSTS50076 and AADSTS50079 name it (Entra's
  words in the lake and SharePoint code; SQL Server's error table, before its "login failed").

## Widgets and the Canvas (the owner, 2026-11-21; built, branch widgets-canvas)

His words: "I actually have a better idea than a app notebook, we can add a section called widgets that makes more
since for our version of app notebooks anyway. and we should just build widgets and be able to browse them in the
selected app framework ... we can pack in tons of prebuilt widgets that can drag to the canvas. and instead of Apps
on rail we could call it Canvas. we dont wanna muddy the gui for the canvas. I want a simple grid container layout
with sizing options at the top, we can drag and draw containers or right click and insert all available streamlit
widgets that we create like buttons and tables, click in to see their properties and edit them ... containers must
have a property to make them scrollable and even resizable. Creating a widget is what will replace the concept of
app cells and app notebooks. Widgets should be on the rail as well but it does not open in the normal app pane it is
a new tab completely separate from the app without the rail ... The the user clicks run and the widget transforms in
place into the object you wrote. The properties pane should expose any variables that was created to configure the
widget and should auto detect its type with masks." Then: "The we need to make the canvas builder robust"; "we need
a way to insert widgets, and we need a pane on the right that shows available widgets with a small preview of it
rendered with its name and description which can be entered in the properties menu of the widget builder"; "size
and zoom controls should be at the bottom"; "should be able to turn on snap to", "with a very fine precision",
"finer than the precision I see in this mockup"; "the widgets should be hover to see a larger preview and they
should not share a pane ... a button at the bottom called properties that allows us to completely hide the
properties pane ... undo play launch export should be in the bottom bar as well".

Decisions:
- A widget is the library's `widgets/<name>.widget.py` (a `swissarmybench-widget` TOML header: name, description,
  framework, group, tags, size and min_size in grid cells; then its code). Its properties are its top-level plain
  values, found with ast, never run: types and masks bool (switch), int and float (number, `# a..b` a range), str,
  colour, date, datetime, time, choice (`Literal[...]`, `# choices:`), table, column (`# column of <property>`, else
  the first table property), variable (`os.environ["NAME"]`, `"${NAME}"`), path, list and dict (JSON). An annotation
  wins over the guess and says when the value disagrees. The comment lines above are its help. A value is checked
  (a bad colour, a column not in the table, a variable not set here: one sentence and the fix) and written into only
  its own characters. The header is written alone (Name checked live; a rename follows every canvas's instances).
- 56 prebuilt widgets ship with the extension (`swissarmybench_streamlit/widgets/`, read-only, Copy as your own),
  each drawn from made-up sample data when no table is picked; a test runs all of them with AppTest.
- The Widgets window is `static/widget.html` (its own build page, no rail): the list, Monaco with the Workbench's
  intelligence over a kernel of its own (primed with the runtime, so `from sab_canvas import table` completes),
  Copilot's ghost text where on. It is built on codeIde.ts (the blade IDE's shell: the slim bar, Monaco, its
  Properties pane, the Output | Result | Problems panel; codeIde gained `actions`, `stage`, `propertiesOpen`,
  `setStage` and `toggleProperties`, generic). One two-state switch, **Code | Preview** (the coordinator,
  2026-11-21), replaced Run and Edit: Preview (F5, chosen over Ctrl+Shift+V because F5 already meant run in
  the Workbench and the blade IDE) runs the widget through the Streamlit proxy (/streamlit/run/) and shows it in
  the editor's place; Code (Esc) goes back; a failing run is the error panel in the Preview with "Go to line N in
  the code" (the line also marked); the view is remembered per widget in sessionStorage. Its panes fold (Ctrl+B,
  Ctrl+Alt+B), as design principle 8.14 asks.
- The Canvas is a page of its own (`static/canvas.html`, with the rail; the rail's Apps is Canvas, `apps` answers
  as `canvas` one release in app_navigate, `?kind=app` goes to the page). Its file is `<app>.canvas.json`, a
  project file, sorted and byte-stable (format 2). **Two layouts, Phone and Desktop** (the owner, 2026-11-21:
  "Canvas should only have two layouts phone portrait and desktop just like powerapps but ... always resizable";
  domain/canvas_layouts.py): every item is in both, `at: {desktop: {x, y, w, h}, phone: {...}}`, x and w fractions
  of the parent's width (6 digits: a pixel round-trips at both design widths), y and h pixels; `show` (both,
  desktop, phone). The pixel engine (canvas_model.py) keeps its rules: each layout is viewed in pixels at its
  design width (desktop 1200, phone 390), the command applied there, the fractions written back; an item new to
  one layout is placed in the other (phone: stacked full width under what is there, in reading order; desktop:
  the first free place at its size). Format 1 files are read as desktop with a phone layout made (said once).
  The built page fills the browser's width (layout wide): each box `left: calc((100% + 2px) * fx - 1px)` inside a
  bordered parent, desktop CSS by default and the phone's under `@media (max-width: 767px)`, so it picks its layout
  by width with no rerun; the page root is `flex: none` (Streamlit's own `flex: 1 1 0%` made it 0 px high). The
  canvas view previews any width in the layout's range by its frame's right-edge handle (desktop 768-1920,
  phone 320-767, its px shown), x and w drawn scaled; layout and preview width kept per canvas for the session.
  Play's address is the app's own (the played page is its default): a page's path said "Page not found" first.
  Columns, row height and gap are a guide to snap to, never a limit. Snap (on by default, kept with the canvas) puts edges on the step (1, 2, 4, 8 px or a grid
  cell) and on other items' edges and centres within 4 screen pixels with guides (canvasSnap.ts's maths); Alt places
  freely for one drag; arrows nudge by the step (Shift ten, Alt one pixel); the dots thin out to stay 12 screen
  pixels apart; zoom scales the view only and is kept per canvas for the session.
- The layout's rules live in the model (domain/canvas_model.py) for the user's moves and the agent's alike: no
  overlap among siblings, nothing leaves its container or the page's width, no widget below its min_size, no
  container smaller than what it holds; a widget dropped into a full container grows it (its siblings settle
  down). Changing the width scales what is on the page; changing the columns moves each edge that sat on a column
  line to the new nearest line, then settles. A command that breaks a rule is refused with why.
- The built page reproduces the pixels: the page is an st.container keyed `sab-page` (CSS: position relative, the
  page's width and its height); each container and widget is an st.container keyed `sab-<id>` placed absolutely by
  its key's CSS (a child inside a bordered container takes the 1 px border off), scrollable is st.container's own
  height, resizable is CSS `resize: both`, padding and background are CSS. The e2e test measures the played boxes
  against the canvas within 1 px. The pages folder is `app_pages/` (a `pages/` folder Streamlit would list as pages
  of its own beside st.navigation's).
- One builder for Play, Launch, a widget run alone, a preview and Export (canvas_build.py): each widget is run by
  `sab_canvas.render` with its properties' values (its assignments made `pass`, line numbers kept), wrapped: its
  failure is its own error panel in its place, a missing table or variable is said there, a slow one shows the
  spinner; the page runs on.
- Robust: every change is a command saved at once (atomically, only when its bytes change) and undoable (Ctrl+Z,
  Ctrl+Y); each carries the version it was made on (another window's change is a notice and the canvas as it is
  now, never written over); a file changed on disk is read again before anything is written; a broken file is
  reported with its line, a copy kept beside it, never written over; a newer format opens read-only; an instance
  of a widget gone from the library is a placeholder with Replace and Remove; overrides of properties a widget's
  code no longer has are dropped and said once; a value that no longer fits its type is marked and the default
  used on the page. A test drives 40 random sequences of 60 commands and checks every rule after each step.
- Previews: each widget rendered once off screen through Play's own run path and photographed by Qt WebEngine (the
  desktop app's own engine, already a dependency) in a child process; kept in the state folder's widget-previews/
  by the widget file's hash and the theme; one at a time in the background; the gallery shows a placeholder until
  it is there, a failing one's mark.
- The Canvas's layout (the owner's, with the coordinator's mockup): the top row holds the page tabs and +, and at
  its right end Play and Export as a block of their own (the owner, 2026-11-21: "Move play launch export to a
  right click in the canvas", then, on the coordinator's plan, "make them look permanent and pronounced"): Play
  the page's primary button (34 px, the accent fill, bold 14 px, a soft shadow) with its ▾ (Launch, Ctrl+F5),
  Stop in its place while the app plays or is launched; Export a raised secondary button; never folded, the tabs
  scroll instead. The same group (Play Shift+F5, Launch Ctrl+F5, Export… Ctrl+Shift+E; Stop while running) ends
  every right-click menu of the canvas. (Launch with the Performance Analyzer and Builds… came back on the widget
  canvas, branch canvas-rest2: below.) The bottom bar holds the sizing with Desktop | Phone and the preview width,
  Snap and its step, Undo and Redo, the Widgets and Properties toggles and the zoom; Properties (nearest the canvas) and Widgets (far right) are two panes, each resizable and hidden
  completely by its toggle (remembered per canvas; a hidden Properties pane stays hidden on a selection, its button
  shows a dot); a card's hover shows its preview at 480 px.

What went (dropped, the owner's "Drop support for app notebooks and the old canvases"): app notebooks (app.ipynb in a
new Streamlit project), `.stapp.json` canvases (opening one says "App notebooks and their canvases were replaced by
widgets"), live Streamlit cells in notebooks, the Streamlit cells pane, cell links, the controllers' `# Makes:`
contract and Test this page, thin cells and Move to data.ipynb, the designer (the property pane on cells' code, the
Toolbox of raw Streamlit elements, containers of blocks, arrange, the outline), App mode's page settings and State,
the Performance Analyzer, and every command of theirs (an old call says why). The data notebook stays (data.ipynb,
its SQL and table cells, data.py; Notebooks and Scripts for data work). The Streamlit starters stay as snippets.
Their front-end modules went too (branch canvas-rest2, below).

## The Canvas's rest: app notebooks dropped for good, the analyzer and Builds back, connections' tables (built 2026-11-21, branch canvas-rest2)

The owner's calls carried out: "Drop support" for app notebooks and the old canvases; Launch with the
Performance Analyzer in Play's ▾ and the right-click run group; Builds' Compare and Restore; a table property
that takes a connection's table; use case 11 written again for the new Canvas.

Decisions:
- **App notebooks, everywhere:** "New app notebook", the appNotebook kind, word and icon, the landing's App
  notebooks and notebook_kind's app role went (a notebook in a project is THE data notebook or a plain one; the
  agent's documents carry a role only for data.ipynb). Live Streamlit cells went from notebooks and scripts: a
  cell that calls Streamlit runs in the kernel like any other (the script outline has no "streamlit" kind any
  more, Run file keeps its lines, arrange counts what it makes), hooks.live_cells went. App mode's panels and
  their Settings switches (Streamlit cells, Properties, State, Starters) went. Opening an old .stapp.json says
  "App notebooks and their canvases were replaced by widgets: make a new canvas and insert widgets." in one
  line (the page before asking the server; the server's own open says the same); `file.newApp` opens the
  Canvas page. A cell's name and copy moved to cellClipboard.ts. Deleted: workbenchCanvas.ts, canvasPane.ts,
  canvasLaunch.ts, canvasToolbox.ts, workbenchStreamlit.ts, workbenchCellsPane.ts, workbenchApp.ts,
  workbenchStarters.ts (canvasSnap.ts and canvasKit.ts stay: the Canvas and the Excel canvas use them).
- **Lineage's values:** they came from the old extension's held documents (hooks.held), gone with live cells,
  so the agent's lineage had no values (the lineage e2e test's KeyError 'n4'). The lineage code was fixed, not
  the test: it asks the Workbench for the kernel started for the document (Workbench.kernel_for) when no
  extension holds it.
- **Launch with the Performance Analyzer** (Ctrl+Shift+F5): the launch's window and the analyzer's both open on
  the key or click (one opened after the wait would be blocked), the analyzer recording from the first load.
  F5 is Play, Ctrl+F5 Launch, Ctrl+Shift+E Export, each shown in the menus. sab_perf.py goes beside a launch's
  pages only (never into the build); the ONE builder's runtime (sab_canvas) imports it when it is there and
  times each widget instance around render(), and each page calls sab.begin and sab.finish: an export has no
  sab_perf, so nothing is timed and its code is the same. Blocks are widget instances, titled "<widget>
  (<id>)"; the hints know each instance's tables. The "needless rerun" hint needs which widget makes a value,
  which the canvas does not know: it does not fire here (left).
- **Builds** (format 2): build.json's "changed" compares the canvases in words (pages added or gone, an
  instance added, taken off, given other values or another widget, the layout) and each widget whose code
  changed (sab_widgets.py read with ast); an app notebook's old build says "The first build on the Canvas".
  Compare two builds, or one with the canvas as it is now (what a launch now would build), in Monaco's diff
  editor; Relaunch an old one; **Restore** puts its canvas.json back as ONE change through the canvas's rules
  (Undo takes it back) and leaves the library's widgets as they are (a widget changed since is said); an old app
  build has no canvas.json and says so. Routes /streamlit/canvases/{canvas}/launch, …/builds…, …/perf…; the
  agent's app_launch (analyzer, stop), canvas_builds and canvas_perf, each by an action (the tool list's
  budget: canvas_list, canvas_show and canvas_stop were folded into canvas_open, canvas_move and canvas_play and
  answer one release; canvas_redo is canvas_undo redo=true).
- **A table property takes `[Conn].table`**, in the same picker as the open tables and now data.ipynb's
  (data.py's top-level names, read with ast): grouped Sample, Open tables, data.ipynb, a group per connection
  (its loaded catalog's tables as SQL names them; not loaded yet: "Type a table of <Conn>…": nothing is loaded
  for asking). A run reads it with ConnectionTables.read_named (the same read a query's [Conn].table gets: the
  one gate, so the connection's query limit and its line) into data/<stem>.parquet, the stem made safe with a
  digest by one rule the runtime shares (a test checks they agree). A value naming no connection here is said
  with the fix; an export carries the rows read when it was made (as it does for open tables).
- **Use case 11** (tests/e2e/test_real_world.py): the invoices opened from PostgreSQL, a Streamlit project, a
  widget written in the Widgets window and previewed, placed on the canvas (a container drawn, right-click
  Insert widget), seen in the Phone layout, played, exported, and the export run by AppTest in a plain Python:
  33 actions (ceiling 34); 11a the agent's commands only (a widget, a canvas, a headless check, a launch, its
  build).
- **Merged share-app:** Share… stays in Play's ▾ and the run group while launched, beside the analyzer and
  Builds….

## The blade IDE (built 2026-11-21, branch blade-ide)

The owner (2026-11-21), on the blade screen: "this entire panel should be an ide, with small save, saves, cancel
buttons at the top and a play button to execute with a realtime linter and output at the bottom to see the
results. This is an IDE not a save form". It reverses 2026-11-17's "blades can only be edited in the folder".
Decisions: the editor shows the code after the header (its lines are the code's; the header is Properties');
Save refuses code that does not parse (the file would stop being a blade); the header's variable follows a
renamed function; the outside-edit check is the file's stamp (sha256, 16 hex), polled every 2 s while shown;
Run is Test's child process (never a kernel: a blade runs where sab.blade runs it), its prints streamed as NDJSON,
secrets scrubbed from every line and answer; a function with no required arguments is called (a table blade);
the error panel is client/kernel_errors.py's, the code compiled under a temporary-folder name so its frames are
"your file". codeIde.ts and its runPanel are shared pieces for the Scripts page's blade tab (the owner: blades move
into the Scripts page) and the Widgets window. Design principle 8.14 holds it: Properties closed and the panel
folded until wanted.
## Each connection's slots and the Queries window (the owner, 2026-11-21: "we should probably throttle how many queries an agent can run in parallel per connection" / "we should probably add a robust standalone popout panel in the connection to show queries that are in progress" / "format the sql in a proper marked up box to make it easy to read with a proper code highlighter"; built, branch connection-throttle)

His answers:
- **Who it applies to:** everyone, with a lower share for the agent: one limit per connection covers every query
  (the user, notebooks and scripts in Workbench kernels, background catalog loads, the agent), and the agent's
  share is smaller, so it can never take all of a connection's slots.
- **Over the limit:** the query waits in line, shows its place and a Cancel, and gives up with a plain message
  after a time limit.
- **Default:** 8 at once per connection, at most 4 of them the agent's; both changeable on each connection's card.

Decisions as built:
- The rule is domain/connection_slots.py (pure: a Board of lines, the clock given): FIFO within a priority (the
  user's interactive work ahead of background catalog loads); an agent query waiting for the agent's share lets the
  user's behind it go first. Words: "Waiting: 3rd in line for Warehouse (8 queries running)", "Running 3 of 8 · 1
  waiting", the window's "· agent 2 of 4". The wait limit is 2 minutes by default (1 s to an hour); the refusal is
  the one shape with Try again (408).
- The limits live in the connection's library file header as a `[queries]` table (total, agent, wait), written
  only when they differ from the defaults, so no existing file changes; a form's save keeps them; a bad hand edit
  reads as the defaults. Validation: total 1 to 64, the agent's at most the total (0 allowed: the agent runs
  nothing there); a total lowered under the agent's share takes the agent's down with it.
- The one gate is bootstrap's run_blade (every connection run in the server: [Conn].table reads, the "+" draft's
  connection query, catalog listing and loading, tests, blade runs, Analyze's and the agent's reads). The work is
  its own task, so Cancel kills the child process (server/blade_runner.py now kills it on cancellation) and the
  slot is always given back.
- Who: a request's X-Actor (the agent), X-Sab-Client (the page's id, every page request carries it: its Cancel
  finds its query), X-Kernel (a Workbench kernel). A kernel's caller is the first of its runs still going (the
  Workbench now records who started each execute: the user or the agent); kernels run cells one at a time, so
  this is reliable for one cell at a time; a user's cell queued behind the agent's in the same kernel is counted
  as the agent's until the agent's ends (said here, not fixed).
- Kernels lease a slot (POST /connections/slots/acquire, renew, release; 15 s lease, renewed every 5 s while the
  query runs, polled every half second while it waits: the cell shows "Waiting for a slot on Warehouse (2nd in
  line)" in place and can be interrupted). A dead kernel's slot expires; a stopped kernel's goes back at once.
  Outside a Workbench kernel, or with no app answering: no gate, never a failure.
- A catalog load whose slot timed out or was cancelled is not kept as a failed catalog.
- The Queries window is /workspace?panel=queries[&connection=<name>], a named window per connection (or All
  connections). Live through the `connection_slots` notice (names and counts only, never SQL; the window asks the
  list again on each notice, never polls); the SQL is fetched for an opened row only, formatted on the server
  (domain/query_text.py: sqlglot's pretty printer in the query's dialect; DAX and what does not parse as written;
  `${NAME}` as written) and refused to the agent (403); Monaco's read-only SQL with line numbers, up to 45% of the
  window. Finished: this session's last 50, memory only, Clear. A restart is said ("The app restarted: these
  queries ended."). Past 200 rows only the visible ones are drawn (fixed row height); arrows, Enter, Delete.
- The agent: connections_slots, connections_queries (clear), connections_cancel_query (its own freely, the user's
  on the user's Allow), connections_set_limits; the guide's connections topic says to batch. A Session entry when
  the agent waited more than 3 s.
- Not gated (each named in the report): see docs/verified.md.

## Notebooks and Scripts, two pages; the Scripts page a Python IDE (built 2026-11-21, branch separate-pages)

The owner's words (2026-11-21): "notebooks and scripts should not reuse the same page they are seperate things" /
"right now they all open tabbed beside each other"; on the Scripts landing: "scripts should open to on the page a new
script creator just like it does but without all of this at the top. What it should have is a project file explorer
to browse and open all project scripts"; "Scripts will open Tabbed inside the ide with their names at the top and we
will see their code"; "the ide pane should be fullscreenable"; "scripts autoupdate when they are touched anywhere in
the app"; "this is meant to expose the high level code of everything in the app for fine tuning"; "maybe the
navigation and blade pane can split the left screen" / "navigation on top, blade on bottom"; "I want prioritize the
ide real estate"; the rail: "scripts and blades should be beside each other", "Apis and Structure should be side by
side", "a + is confusing just make this a normal icon", "just call it home instead of projects", "rename Data
Catalog to just catalog, and Source Control to GIT". Earlier (2026-11-17): "the scripts rail page should simply be a
navigation for the project files with our robust IDE for python ... a by module navigation tree on the left to
navigate all of the scripts(except the notebooks) those are edited in the notebooks page exclusivly".

Decisions:
- **Two pages, one page code.** /notebooks (window sab-notebooks) and /scripts (sab-scripts) serve the same
  workbench.html; the window's path says which it is (workbenchPages.ts thisPage). A notebook, an app's canvas and a
  workbook design open on the Notebooks page (the canvas stays there until the widgets-canvas branch moves it); a
  .py only on the Scripts page. makeDoc refuses the other kind; open() hands the other page's file to its window
  (asked through the server's workbench_window with `page`, else that window opened on it); the handoff take
  refuses a wrong-kind document in one line ("A notebook opens on the Notebooks page, not here."): that is the
  wrong-kind drop (tabs never drag between windows; a pop-out keeps its page). /workbench?kind= redirects; an old
  /workbench#open=load.py goes to the Scripts page before anything draws.
- **The agent:** workbench_window takes `page` (else args.path's page, the kind file.newScript or file.newApp makes,
  else the window last used); app_navigate takes window notebooks or scripts ("workbench": either). The live socket
  says each window's page.
- **Restore per page:** session storage `workbench-documents:<page>`; the old mixed key split by kind once (its groups
  start again). The project's .sab layout keeps `workbench.notebooks` and `workbench.scripts`; an older layout's list
  is read for this page's kind only.
- **No top bar** on either page: Save in the document's row (Ctrl+S), Save as… in its "…" (Ctrl+Shift+S), New and
  the page's menu ("Workbench menu") at the explorer's head; with nothing open, Scripts shows its creator (one
  sentence, New script, Try it with sample data), Notebooks its Start a notebook / Start an app.
- **The explorer** (codeExplorer.ts, GET /scripts/tree, GET /project/tree?page=notebooks): Your scripts by module
  (`scripts/etl/load.py` is etl.load), Project code (data.py made from data.ipynb, pages/*.py from the canvas:
  read-only with a key until edited by hand, then a pencil), the library's Connections, APIs, Key vaults and Widgets
  (the folder once it exists), Generated (each open table's transformations, read-only, Fine-tune as a script: a
  new scripts/<table>_tuned.py). Each module unfolds to its outline (ast; as typed for the open one). Folds to a
  strip (Ctrl+B), resizes, remembered per page. Never a notebook on Scripts.
- **Blades below the files** on the Scripts page (a splitter, each folds); the rail's Blades lands there
  (/scripts?pane=blades). A blade opens as a tab: `bladeDoc()` in workbenchPage.ts composes the blade IDE's
  editBlade (its Properties pane, Run with Output / Result / Problems, a starter's Save refused with Copy as your
  own). That function is the seam for the blade IDE's pieces.
- **The IDE's moves** over the editors' one intelligence (Jedi's project world, shared with services/intellisense.py):
  F12 Go to definition (another module's file opened at the line; a library's place said), Shift+F12 references
  (a list), F2 rename across the project's modules (a preview of each line; a made file skipped with why; the open
  document's change in its editor, the others written), Shift+Alt+F Format (Ruff in the script's Python, else said),
  Ctrl+Shift+F search and replace across the scripts (regex, case, word; Replace all's preview). Monaco's own
  bindings for those keys give way.
- **Full screen** (F11, the tab row's button, the agent's view.fullScreen): the rail, the explorer, the console and
  Variables and the status bar go; Escape or the button comes back; remembered per page for the session. The code's
  own zoom (Ctrl+wheel, Ctrl+= - 0 over the documents; view.codeSize) as the blade IDE has it, per page.
- **file_changed** (services/code_files.py): {path, hash, by} at once for the app's writes (a save, a rename, a
  replace, Fine-tune) and within a few seconds for anything else (the open project's and the library's .py and
  .ipynb looked at, off the loop). An unchanged script reloads in place; one with unsaved edits shows Changed
  elsewhere: Reload / Keep mine / Compare (Monaco's diff), and Save waits for the choice; a gone file: Save as /
  Close. The open and save answers carry the hash, so a window's own save is not said back to it.
- **Edited by hand:** a made file saved by the user or the agent is recorded in .sab/hand-edited.json; data.py's
  regenerate then keeps it (New project, a Save as) and Export data.py asks (409: keep, or replace=true).

Left (not built this round): the debugger (breakpoints, debugpy through the kernel's debug_request); New package,
Rename, Delete and Duplicate in the tree; go to definition into a library opening it read-only; the blades' header
fields beyond the blade IDE's Properties and New blade's blank scaffold by kind (blades_header_set, blades_save);
the old /catalog page's redirect to the Blades pane (its import, export and folders dialogs still there); Notebooks'
clean reload in place (a notebook changed elsewhere asks even when unchanged here); the desktop app's window full
screen (the page's full screen only).

## The blade tab: every header field, New blade's scaffold (built 2026-11-21, branch scripts-rest)

The owner (2026-11-21): "the blade format requires extra stuff so we should add those properties to the ide
experience along with the option to save the blade. we should scaffold a blank blade for the user".

Decisions:
- **One table of fields** (domain/blade_header.py FIELDS): every key the `# /// swissarmybench-blade` header writes,
  with its words and type; `applies(key, shape)` says which a kind has (a table blade: variable, table; a database:
  dialect, rows to open, queries.total/agent/wait, catalog.language/command; a Python connection: read.command too;
  a snippet: language, cell_name; a vault: vault_all, vault_mapping; a secret: env_names). Kind, secrets, template,
  web_call and variables are shown read-only (they follow from the code or the file). The details answer carries
  `header`; Properties draws it generically (bladeProperties), each box checked as typed (name and table by the
  server's checks, variable against what the code makes, numbers, names, mappings and tags by their rules).
- Save sends the code and only the changed fields (name, description, tags and table always, as before); the
  server writes the header through set_header (parse_blade checks it all). A field the kind has not is refused.
- **Before a save**: compiling, and the kind's required part (required_part): a table blade's function takes no
  required argument and returns something; an analysis takes 1 or 2 arguments; a Python connection has its listing
  and Read a table; a vault's reader is a function. Refused 422 with `line`: the line marked in the editor, the one
  error note in Result. A starter's or a pack's Save stays refused first (Copy as your own).
- **New blade** asks a name (checked live) and a kind: table, code, analysis, connection (DuckDB in memory with
  made-up orders and its listing query), snippet, secret. The scaffold has comments on what to write and made-up
  rows; Run works at once (an analysis is tried on six made-up rows by the IDE's Run). It opens as a tab, the
  cursor in its body, Properties open (the only time they open by themselves).
- The agent: blades_new(name, kind), blades_header_set(name, fields) (none: the fields and values).
- The editor never showed the header (it is Properties'), so "fold the header away" holds as built.

## The old blades page goes (built 2026-11-21, branch scripts-rest)

- /catalog redirects (302) to /scripts?pane=blades, every query word kept: ?blade=<name> opens that blade's tab
  (one tab a blade; the word leaves the address once shown), ?blade= New blade, ?open=settings the layer.
  catalogPage.ts and static/catalog.html are gone; the build has no catalog page.
- The Blades pane's head: New blade (+) and one "…" (Import blades…, Import from a project…, Export every blade,
  Blade folders…, Packs…) instead of a row of icons (8.14).
- The agent: app_navigate's window "catalog" is read as "scripts" for one release; blade:<name> and new_blade are
  the Scripts page's. desktop_open's "blades" opens /scripts?pane=blades; a .blade.py opened with the app opens
  its tab there. sab.load's address is the Catalog page (/workspace?open=data).
- Elsewhere (the Session page's links, Analyze's "your analyses"): openBladeOnScripts tells the open Scripts
  window (POST /navigate) or opens one on the address.
- In a blade's tab on the Scripts page, Ctrl+S, F5 and the code's zoom keys are the blade IDE's, not the page's.

## The Scripts explorer's tree actions (built 2026-11-21, branch scripts-rest)

- Right-click a module of the user's (or F2 / Delete on its row): Rename…, Duplicate, Delete; an `__init__.py`
  adds Rename package…, New package here…, Delete package. New package at the explorer's head. Made, read-only,
  library and generated files have none.
- Rename (POST /scripts/files/move): the new name in the same folder (or a path inside the project); the plan
  first: the module's imports across the project rewritten (domain/script_ide.py import_rewrite: `import a.b`,
  `from a.b import x`, `from a import b` kept under its old name there, `b as` its alias; a module moving to
  another package out of a `from a import b, c` gets an import line of its own), previewed and the made files
  skipped as F2's rename is. Usages like `a.b.f()` after `import a.b` are not rewritten (said here). Apply moves
  the file (or the package folder) and writes; `code_file_moved` {from, to} retargets every window's open tabs.
- Duplicate: `<stem>_copy.py`, then `_copy_2`, opened. Delete: the system's trash (server/file_manager.py), the
  user's own (403 for the agent; NOT_COMMANDS), a dialog first. A made file is refused with what it is made from.
- The agent: workbench_file(action move | package | duplicate).

## A library's source, read-only (built 2026-11-21, branch scripts-rest)

- F12 on a name an installed library defines opens that file in a tab of its own (kind `library`): a "read-only"
  chip and the module's name over Monaco read-only, at the line; one tab a file (F12 again moves its line). Not
  kept in the session's restore.
- POST /scripts/library-file reads only a .py or .pyi of Python's own folders (the app's stdlib, purelib,
  platlib) or any site-packages, dist-packages or typeshed folder (a script's own environment): never another
  file of the computer's (domain/script_ide.py library_file). The agent: workbench_definition(source=true).

## Notebooks reload in place (built 2026-11-21, branch scripts-rest)

- A notebook changed elsewhere with nothing unsaved here takes the file's cells in the same tab, as a script does:
  its view made again from the file (notebookOf) in place of the old, the kernel and its names kept, the selected
  cell kept where it can be. Only a notebook with unsaved edits shows Changed elsewhere (Reload / Keep mine /
  Compare); a gone file says so.

## The desktop app's window full screen (built 2026-11-21, branch scripts-rest)

- F11 and the tab row's full-screen button on the Notebooks and Scripts pages make the window itself full screen
  too in the desktop app: the page calls window.sabApp.fullScreen(on) (desktopApp.ts windowFullScreen), the shell
  hears it on its console channel and calls PySide6's showFullScreen, or back: showMaximized when it was
  maximized, else showNormal. Escape, F11 again or the button leave both. In a browser nothing more happens.
- The shell's own F11 (QShortcut) asks the page first (window.sabFullScreen): a page with a full screen of its
  own takes it (and asks for the window's); any other page toggles the window alone, as before.
- Checked under Qt off screen (tests/desktop_drive.py: F11 twice on the Notebooks page).

## Layout as 8.14 says (built 2026-11-21, branch scripts-rest)

- The blade tab's Properties is closed each time a blade opens (no longer remembered open); it opens by itself
  only on a brand-new scaffold.
- codeIde.ts's panel (Output | Result | Problems) stays folded to its tabs until something runs or a lint error
  appears (it opens on Problems then; a fold by the user's own click holds until the next run); the first time
  it opens with no height of its own it takes about 30% of the area, and a dragged height is remembered.
- The Workbench's console opens on a run as before, now at about 30% (leftTop 70%), its size remembered.
- The minimap was already off by default (lazy/codeEditor.ts); the browser test checks it.

## The Scripts page's debugger (built 2026-11-21, branch scripts-rest)

- The kernel's own debugger: ipykernel ships debugpy (no new dependency); the Jupyter debug protocol over the
  control channel (server/kernels.py debug: debug_request; debug_event from iopub into its own queue).
  initialize and attach once per kernel, dumpCell (the script's text to the kernel's file for it), setBreakpoints
  there, configurationDone, then the text runs as a cell in the document's kernel. Its names stay in the kernel
  after (as Run's do); `__file__` and `sys.argv` are a cell's, not %run's (said).
- services/debugger.py: a session per kernel (domain/debugger.py Session: state idle, running, paused, ended;
  frames; output, memory only), a watcher task reading the events (stopped: stackTrace; continued; output: a log
  point's words), `debug_state` notices (no output in the notice; read with GET /workbench/debug). Steps set
  running before they are sent (the run may end before the answer). Stop: no breakpoints, continue, interrupt.
- The page (workbenchDebug.ts): glyph margin breakpoints (a dot; a ringed dot conditional; a diamond log point)
  that follow edits (Monaco decorations), right-click menu, F9; the bug button and Ctrl+Shift+D; while paused F5,
  F10, F11 (into: full screen stays F11 otherwise), Shift+F11, Shift+F5; the paused line highlighted; the panel
  under the code only while debugging (8.14): Call stack (a library frame opens read-only), Variables (Locals
  and Globals, unfolding), Watch, Output, Debug console.
- The agent: workbench_debug(action, document) (the tool list stays under 99,500: blades_update now takes the
  code alone, the header is blades_header_set's; a few blades_ descriptions shortened).

## Share a running app (the owner, 2026-11-21: "I just wanted a place for a user to host a POC so others can connect to it like an app"; built, branch share-app)

The owner's answers: **organization only** (people open the link after signing in with their Microsoft work account,
Microsoft Dev Tunnels; no public links at all); **until you stop it** (Stop sharing, the app's stop, Swiss Army Bench
closing: a link always ends with its app); **the tunnel program** downloaded the first time someone shares, never with
the app's install ("Sharing needs devtunnel: Install now"), into the state folder, checked.

Decisions:
- **What goes through the tunnel:** only the app's own 127.0.0.1 port. For a launched Streamlit app that is a *shared
  run*: a second Streamlit process of the launch's own run folder (the same build and tables), at the address's root,
  in the launch's Python (server/streamlit_apps.py SHARED_FLAGS: `--server.baseUrlPath=` (root),
  `--server.enableCORS=true` and `--server.enableXsrfProtection=true` forced over an app's own config.toml,
  `--server.fileWatcherType=none`, `--server.runOnSave=false`; `--server.address=127.0.0.1` as every run). Why it
  works behind the tunnel unchanged: devtunnel rewrites Host to `localhost` and Origin to `http(s)://localhost` by
  default, so Streamlit's web socket origin check (same origin, or localhost) passes and the XSRF cookie is the
  tunnel's own origin's. The proxy (/streamlit/launch/<key>/) is never tunnelled, nor this server: domain/sharing.py
  check_port refuses the server's port, and every command line is built from a checked port.
- **Organization only, never anonymous:** `devtunnel create --labels swissarmybench --json` (no `-a`), `devtunnel
  access create <id> --tenant`, then `devtunnel access list --json` read back: an anonymous entry, or no tenant entry,
  deletes the tunnel and shares nothing. `_line` refuses `-a`, `--allow-anonymous`, `--anonymous` on any line. A
  sign-in with no tenant (a personal Microsoft account: Entra's consumers tenant; GitHub) is refused ("Sign in with
  your work account"). A policy that blocks it (Dev Tunnels' group policies "Disable Dev Tunnels", "Allow only selected
  Microsoft Entra tenant IDs", or Conditional Access) is said with what to ask IT; never a fallback.
- **The tunnel:** `devtunnel port create <id> --port-number <app port> --protocol http`, `devtunnel host <id>`, the
  address read from host's line for that port (`https://<id>-<port>.<region>.devtunnels.ms/`, never the -inspect one),
  ready on "Ready to accept connections". Stop: host stopped, `devtunnel delete <id> --force`. A tunnel left by a crash
  (its label, none running) is deleted before the next one is made. No description is sent (nothing of the app's goes
  to the service but its traffic).
- **The download and its check (which):** `https://tunnelsassetsprod.blob.core.windows.net/cli/<file>` (the host and
  files Microsoft's own install script, aka.ms/DevTunnelCliInstall, and aka.ms/TunnelsCliDownload use; HTTPS, a
  redirect elsewhere refused, 200 MB at most). Microsoft Learn publishes **no SHA-256** for devtunnel, so the checks
  are: the **Content-MD5** Microsoft's download store publishes with the file (every system), and the **signature**
  where Microsoft signs it: Windows' Authenticode (Get-AuthenticodeSignature: Valid, O=Microsoft Corporation), macOS'
  code signature (codesign --verify --strict, TeamIdentifier=UBF8T346G9, Microsoft Corporation's). Linux: no signature
  is published, the checksum only. Kept only when every check passed.
- **Sign-in** is the user's own (403 for the agent): `devtunnel user login --entra`, in the browser, or
  `--use-device-code-auth` (the dialog shows the code, Copy, Open the page). devtunnel keeps its own token in the
  system's key chain; the app never sees it.
- **The agent:** `sharing_status`; `sharing_start` (installs devtunnel if needed) and `sharing_stop` on the user's
  Allow (it publishes outward). The Session log: "Shared <app> with the organization", "Stopped sharing <app> (why)":
  never the link, a tunnel id or a token.
- **The page (generic):** web/src/shareApp.ts: `openShareDialog({kind, id, title})` and `shareMark(app)` (also
  `globalThis.sabShare`). On the new Canvas (merged from widgets-canvas): **Share…** in Play's ▾ (beside Stop the
  launched app) and in every right-click menu's run group while the app is launched; the Shared mark beside Play.
  The backend target reads LiveRuns' `launch-<canvas>` run (its folder and Python: `launched`) and hears
  `LiveRuns.ended` (the run stopped, or written again by a new Launch): the share ends with it.
- **Power Apps' dev server does not fit:** Run live loads the code app into Power Apps' own player from the local
  dev server (`_localAppUrl`), so a colleague's browser could not use a tunnelled dev server as the app; Push to the
  environment is how a code app is shared. The seam stays open (hooks.share_targets[kind]).

Not done: the tenant's display name ("Your organization: <name>") — devtunnel's `user show` does not say it; Graph
would need another sign-in, so "Your organization" stands alone until a source is found.

## Widget starter packs and a large made-up business (the owner, 2026-11-21; built, branch data-and-packs)

His words: "Build some widget starter packs. Build a large dataset." Then: "Preload the release library with a ton of
widgets that cover most objects. The big ones for me are user inputs. And dealing with excel files from streamlit."

Decisions:
- **A pack is a header field, not a folder:** `pack = "Sales dashboard"` in a prebuilt widget's header (written only
  when set, so every older file keeps its bytes); `domain/widget_packs.py` holds the packs' order and one-line
  descriptions. The listing puts the packs' widgets first, in that order, then the plain groups; the Widgets window,
  the Canvas's Widgets pane and Insert widget head them by pack (the pane and the window show the description under
  the heading). A widget belongs to one pack; the 56 older prebuilt ones stay in their groups.
- **Eight packs, 53 widgets:** Sales dashboard (5), Operations (4), Customer service (5), Data entry (4), Admin (3),
  User inputs (22: every Streamlit input, each with label, help, placeholder where Streamlit has one, default,
  required, disabled, its session state key and a validation message; one red-star marker and one red error line),
  Excel (6: upload with sheet by name or number, header row and range, types guessed; column matching by name with
  short words read as their field's (Order No is order_id, Qty quantity) and difflib; row rules; formatted
  download, several sheets; a template with Excel's own checks; the round trip), Form builder (4: designer, picker,
  fill, submissions; definitions and submissions plain JSON).
- **Data in and out without storage of their own:** a widget that reads data takes a table property (and column
  properties) and draws its own made-up rows until one is picked; widgets pass values by session state keys
  (`filter_key`, `selected_key`, `in_key`/`out_key`, `definition_key`, `submissions_key`); one that hands data on
  puts `{"event": "save", "widget", "payload"}` under its `save_event` key, for the page or a local API to keep.
- **openpyxl:** the app's dependency, not necessarily the project's Python where widgets run; an Excel widget that
  finds none says `pip install openpyxl` in its place (an old .xls says the same of xlrd).
- **Larkfield Goods** (tools/testbed/large_company.py): 14 tables, DuckDB SQL over range() with hash-based randomness
  (deterministic by seed and scale), skewed customers and products, a November and December peak, growth, nulls
  where they would be; the deliberate problems (an order sent twice, a late-arriving order, a negative quantity, a
  delivery before its shipment, a customer entered twice) listed in data_quality_issues. small 10k order lines,
  medium 1M, large 10M; written as Parquet (and optionally one DuckDB file) only outside the repository.

Open (proposals for the owner, not built): a choice list from a table's column; a default from another widget's
value; a property kind for "a table or a session state value" (so an upload's table feeds a table property); a
list-of-tables property (Excel download's sheets are names in a list today); an event kind the canvas wires (today
the save event is a session state key); the runtime's sample() by kind (each pack widget carries its own made-up
rows); shared helpers for the pack's marker and error look (each widget carries its own copy); the editors' small
lint calls a format spec inside an f-string (`f"{x:.1%}"`) "an f-string without placeholders" (older widgets too).

## Local sandbox APIs over the project's sandbox (the owner, 2026-11-21; branch local-apis)

The owner: "the goal is to be able to build a ready to go backend, front end app and API here. If we could build
api's here that could host locally inside the app so the streamlit could use our API as a testing ground with our
connections we would have the full stack. And a fully functional POC" / "We need to actually make apis just read and
write our local data through the API. Not use the connectors that way we could transform scaffold create an app then
test it out and then reset the data changes and try again. It makes for the ultimate sandbox" / "Instead of your API
just call it local sandbox apis" / "The goal is to see how your app will behave with mock data ... Things that get
built should always hand back to a client that mimics the connections client shape" / "No never run against live data
ever" / "So this project now needs a new file in the back called API.py".

### Part 1: the sandbox (built)
- `.sab/sandbox/` in the project folder: `sandbox.duckdb` (opened by the server only, external access off, no
  spill folder, one lock), `baseline.duckdb` and `checkpoints/<name>.duckdb` (whole-file copies taken after a
  CHECKPOINT with the file closed: Reset is one copy and gives back exactly the baseline), `sandbox.json` (each
  table's source and the client its rows are mocked as, the baseline's time, the checkpoints, the change log).
  Git-ignored: `.sab/.gitignore` has `sandbox/` and the scaffold's `.gitignore` `.sab/sandbox/`; an older project's
  `.sab/.gitignore` is written again when its sandbox is first made.
- Tables come in only on the user's Add to sandbox (or the agent's `sandbox_add`): an open grid's view after its
  steps (the grid's Table row: Add to sandbox), a connection's table read once through the connection (its query
  row limit applies; never read again), a file, or an empty table by its columns (text, integer, number, decimal,
  yes/no, date, timestamp; a key). Adding or removing a table makes the sandbox the baseline again.
- Each table remembers its client: the connection it came from (directly, or an open grid's origin) with its
  tables kind, template and dialect; a file or an empty table is `duckdb` (a plain DuckDB client).
- The change log counts each mock client's inserted, updated and deleted rows per table since the baseline; a
  checkpoint keeps the log it was saved with; Reset empties it.
- Writes are statements of their own (domain/sandbox.py): every name checked against the table's columns, every
  value bound, one transaction per call (all or none); a read is one SELECT by DuckDB's own parse.
- A sandbox table shows in Grids as `sandbox_<table>` (Open in Grids), its grid given the rows again after each
  write, where it is (store_table's follow); DuckDB SQL names it `[Sandbox].orders` (a dataset alias of the base's
  hooks: its words carry the sandbox's version, so a read after a write is read again); the Catalog has a Sandbox
  section after Open tables.
- Decision: the word `sandbox` is the project's sandbox now. The Analyze board's old `sandbox_*` command names (one
  release since 2026-11-16) went: GONE_NAMES says each is `analyze_*`; `visualizations_*` still run.
- Agent: `sandbox_list`, `sandbox_add`, `sandbox_remove`, `sandbox_open`, `sandbox_reset` (waits for Allow),
  `sandbox_checkpoint` (save, delete, baseline), `sandbox_restore`.

### Part 2: API.py, mock clients, hosted locally (built)
- One local sandbox API per project: `API.py` at its top, the user's own file, made by New project (an older
  project's on New local sandbox API…). Its settings are its header (`# /// swissarmybench-api`: name,
  description, target, base_path), the blade file's style: the Scripts editor keeps it as comments, so the file
  stays self-contained (the brief's .sab/api.json alternative was not needed).
- Endpoints are typed functions under our `@endpoint(method, path)` (sab_api: server/api_runtime.py, standard
  library, copied into each export). A path's names are parameters; a TypedDict, dataclass, dict or list
  parameter is the JSON body; the rest the query's. `ApiError(status, words)`; `records(cursor)`.
- `connection(name)` is a mock with the real client's shape (the owner's design change: "Things that get built
  should always hand back to a client that mimics the connections client shape"): MockDbApi (any DB-API
  database), MockSqlServer (the starter's SqlServer), MockDataverse (rows/read with OData, fetch with FetchXML,
  the SQL endpoint's cursor), MockSharePoint (the lists starter's), MockDuckDB (`connection("Sandbox")`: a
  table from a file or made empty). tests/test_sandbox_clients.py holds every public method of each real class
  (taken from its starter's own code) against its mock, and runs one function through sqlite3 and its mock, and
  through Dataverse's stand-in and its mock: the same answers. Not mocked yet (refused in one sentence naming
  the kind): lakes, SharePoint documents, Power BI, a Python connection, an API connection; the Write starters
  were not run against the mocks.
- The mock speaks its source: its SQL (T-SQL, PostgreSQL, MySQL, Snowflake, SQLite, Oracle, Trino, DuckDB) and
  marks (?, %s, %(n)s, :n, :1, $1) made DuckDB SQL by sqlglot on the server, each mark a numbered parameter in its
  own order (OFFSET ? ROWS FETCH NEXT ? ROWS keeps its values); dbo.orders is orders; SELECT, INSERT, UPDATE,
  DELETE only; MERGE, EXEC, CREATE, temporary tables, system views, a Web API call refused with the line.
- "No never run against live data ever": no Live switch. The API's process (server/api_host.py, `python -I`, the
  app's Python with Starlette and uvicorn) gets an environment made from nothing (domain/local_api.py
  runner_env: the system's few, an empty home and state folder, its four SAB_ values), and the app's own client
  functions (sab.connection, .blade, .read, .sql, .dax, .load) are taken over before API.py is imported: the
  mock, or a refusal. Its one door is the sandbox's data route by a key of its own (/sandbox/data/<key>, a secret
  path of the guard's). tests/test_local_api.py checks the environment holds no secret and the real client is
  refused.
- Hosted on 127.0.0.1 on a port the system gives, with a key of its own (Authorization: Bearer); started again
  when API.py changes (a look each second while it runs); a start that fails says API.py's line. FastAPI is not
  the app's dependency (it is not installed): the local host is Starlette, which FastAPI is built on; the
  FastAPI target's export lists fastapi in its own requirements.
- The APIs page: the sandbox's panel, then Local sandbox APIs (target, base path, Run/Stop, each endpoint's data
  words, Try it with a made-up body from its model, problems with Go to line, the request log every 2 s), then
  the imported APIs. A kernel: `sab.api().get(path)` through the app (timed, logged).
- The agent: one `api(action)` command (state, new, settings, run, stop, call, log, address, openapi); a write
  call waits for Allow.

### Part 3: framework targets and Export (built)
- Targets are data (domain/api_targets.py Target: id, label, words, render(bundle), run hint), a Registry the
  extensions that are on add to (their API_TARGETS: {id, label, words, render, run}); backend only.
- Each export: API.py as it is (the endpoints never change), sab_api.py (the one request handler every target
  calls: sab_api.handle), connections.py (each connection the endpoints use as its own portable code, made by the
  script export's machinery: settings from the environment, a vault by managed identity; `connection("Sandbox")`
  a copy of the sandbox, data/sandbox.duckdb, only on the user's tick, copied to the temporary folder at start
  since the platforms' package folders are read-only), openapi.json, README.md (the endpoints, files, how to run
  it here, the deploy commands, the portability checklist with each "Only works on your machine" note, the
  variables to set), requirements.txt. FastAPI: main.py, a route per endpoint (async, the endpoint in a thread),
  its OpenAPI. Azure Functions: function_app.py (the v2 model: @app.function_name and @app.route per endpoint,
  FUNCTION auth level), host.json (routePrefix "" so the paths are API.py's), local.settings.json (names, empty
  values), .funcignore. AWS Lambda: lambda_function.py (REST 1.0 and HTTP 2.0 events, function URLs, a stage
  stripped), template.yaml (SAM, Python 3.12, an HTTP API).
- `exports/api/<target>/` is a made folder (code_tree's made_from: "API.py"): written only when bytes change, a
  file the export no longer makes removed, a file edited by hand (.sab/hand-edited.json) kept until Replace;
  Compare shows both. The zip the brief mentions was not built (the folder is the deliverable).
- Checked: tests/test_api_export.py exports the three for one API.py whose endpoints use a made-up SQLite
  connection, then runs each with no app against the REAL connection (its keyring password given as the
  platform's variable): the Lambda handler with made-up REST and HTTP events, the Azure app's functions, the
  FastAPI app served; the answers are the sandbox mock's. With SWISSARMYBENCH_EXPORT_PYTHON naming a Python that
  has fastapi 0.165, azure-functions 1.26 and duckdb, the same test runs against the real packages (done
  2026-11-21: passed); without, small stand-ins of their few names. FastAPI and azure-functions are never the
  app's dependencies, only the exports' requirements.

### Part 4: New endpoint from a table; the Scripts page (built)
- New endpoint from a table (the Local sandbox APIs' button, a sandbox row's New endpoint, `api(scaffold)`):
  the table and its key (its primary key by default; a column picked), then the CRUD set appended to API.py in
  the source's own style (domain/api_scaffold.py); a name or path API.py has already is refused. Written to the
  file (the Scripts page takes the change as any change on disk; it is not one undoable edit in an open editor:
  the file is the user's, and a reload is what the page does with an edit from outside).
- The Scripts page's explorer has a Local sandbox API group (API.py and exports/api/**: made, read-only, "made
  from API.py"); completion in API.py: `connection("|")` offers Sandbox and each mocked connection, a table after
  FROM/JOIN/INTO/UPDATE in an execute() string offers the sandbox's tables.
- ARCHITECTURE.md lists API.py in the tree and, when it has endpoints, a Local sandbox API deliverable (what it
  mocks, each method and path); it is not counted as a script.

### Part 5: the API widgets and the canvas (built)
- Four new prebuilt widget files (extensions/streamlit/.../widgets/api_*.widget.py, no canvas code): api_table
  (a GET's list, paged with limit and offset, Previous and Next), api_form (a POST or PUT: its fields from the
  running API's body model, GET /__sab/endpoints on its host), api_button, api_metric (a field of an object, or a
  list's count). Each reaches the API by SAB_API_URL, SAB_API_KEY and SAB_API_BASE with the standard library; with
  none it says how to start it (so AppTest renders each without an error).
- A new property mask, `endpoint` (widget_properties.py: `# endpoint` or `Endpoint`; a value "GET /path", checked
  against API.py's endpoints when known; the Canvas's and the Widgets window's field a picker of them,
  widgetFields.ts; the endpoints from GET /streamlit/widgets/context).
- Play and Launch: the base puts SAB_API_URL, SAB_API_KEY and SAB_API_BASE in its own environment while the API
  runs (services/local_api.py publish), so a Streamlit process started afterwards inherits them: no canvas code
  changed. An app playing before Run is started again to see it.
- Payload shapes (the owner's design change: "a Payload shapes panel shows the endpoint's answer schema beside
  what the widgets using it expect"): GET /local-api/shapes, api(shapes), a table on the Local sandbox APIs
  section: each canvas instance with an endpoint value (the extension's api_uses reads the project's
  *.canvas.json), what its widget expects, the endpoint's model, each mismatch in one sentence.
- Not done: the canvas Export writing SAB_API_URL as a variable to set (that is the canvas service's export, left
  alone under the rule that this branch adds widget files and a mask only); the API export's README lists the
  API's own variables, and the widgets name theirs in their code.

## The sandbox's gaps, approved (the owner, 2026-11-21; built, branch sandbox-gaps)

The owner approved the gaps the local sandbox API work listed, and added one: "We need all sandbox tables to be
sortable. The moment a sandbox table is created it gets a connection type of sandbox. And grid table or structure
can become a sandbox variant and should get its own designation."

- **Keep "Reset one table".** Kept as built (`sandbox(reset, {"table"})`, the row's Reset, the grid bar's Reset).
- **Mocked as a connection.** A table from a file, its columns or a grid of no connection's (`mockable`: its first
  client named none) gets a "Mocked as" picker on its row (the saved connections with tables); its mock client then
  takes that connection's kind, template and dialect (`client` in sandbox.json, `mocked: true`, `origin_client`
  kept). A table read from a connection is refused ("it answers as Shop already"); the Sandbox itself is refused;
  null puts the plain DuckDB client back. `sandbox(mock)`, POST /sandbox/tables/mock.
- **Keep a Try it body.** Decision: **beside API.py, not in it**: the project's `.sab/api_examples.json` (by
  "METHOD /path", sorted, byte-stable, shared in Git with the project). API.py stays the user's code and its
  settings only; writing JSON bodies into its TOML header would grow the file the user reads. Try it starts from
  the kept body; the OpenAPI document shows it as the request body's example. Only an endpoint that takes a body;
  20,000 characters at most; null forgets it. `api(example)`, POST /local-api/example.
- **Edit sandbox rows in a grid.** A sandbox grid (sandbox_<table>) is editable: double-click, Enter or F2 opens a
  box over the cell (sandboxGrid.ts; other grids still open the value viewer, through gridView.ts's one
  registerCellEditor seam); Add row (a box per column) and Delete rows (the selected rows) on the bar over the grid.
  An edit names its row by every value the grid shows (`rowid = (SELECT rowid ... IS NOT DISTINCT FROM ... LIMIT
  1)`), so a sorted or filtered view edits the right row; a grid whose steps change its columns is refused (edit by
  `where` instead). Each value is checked first with DuckDB's TRY_CAST to its column's type ("'abc' is not a
  number: amount is DOUBLE.", said under the box, which stays open); an empty box is blank but for text; yes/no
  for a BOOLEAN. A row changed since it was shown: 409, the grid shown again. Every edit is a sandbox write in the
  change log (Last changed set) and Reset undoes it. `sandbox(edit)` (row places or `where`).
- **Export names the API variables.** A canvas Export whose app calls the local sandbox API (SAB_API_URL in its
  files) answers `variables` and `warnings` and writes README.md with "Variables to set where it runs"
  (SAB_API_URL, SAB_API_KEY, SAB_API_BASE); the Canvas page shows the warnings in its notice line.
- **Path fields for API widgets.** A new mask, `path_values` (`# path values of endpoint`): one box per `{name}` in
  the chosen endpoint's path, following the endpoint picked (widgetFields.ts, small). Each box takes a value, a
  variable reference or `{{ name }}`, a page value; checked (a name the path lacks, a variable not set here, a
  malformed page value). The four API widgets read a box at run time (_given): a variable from the environment, a
  page value from the page's st.session_state. Decision: a page value is st.session_state[name] until the
  widget-gaps branch's page values land (to align then).
- **Sortable.** Every list of sandbox tables sorts by name, rows, source, created or last changed
  (domain/sandbox.py sort_tables; ties by name): GET /sandbox?sort=&order= and `sandbox(list, {sort, order})`;
  the APIs page's sandbox list's headings (aria-sort; remembered in this browser) and the Catalog's Sandbox
  section (its Sort button, the same remembered choice). In its grid a sandbox table sorts as any grid does (the
  header's sort, the steps), and edits follow the view.
- **A real connection kind.** Every sandbox table has `type: "sandbox"`; "sandbox" is a TABLE_KINDS kind (listed
  and read through the one contract: the alias carries `tables_kind`, its tree listed with no catalog to load;
  write_capability says it writes only by itself). The Connections page has the project's Sandbox card (its own
  group: tables, the change log, "Local test data, never live") and a page of it (the sandbox panel: tables,
  Reset). Its colour is its own indigo #3a3aa0 (none of the palette's, clear of the rail's), listed `fixed` and
  refused if set. Never exported as a connection: the API export already left it out; script exports'
  connections_code drops it too.
- **Sandbox variants.** "Make a sandbox variant" on the grid's Table row (it replaces Add to sandbox there) and on
  the Structures page (a list of records); `sandbox(variant)`. The designation is "orders · sandbox" (SQL name
  orders_sandbox), then "orders · sandbox 2", or the user's own name (its SQL name made of it). Its origin (which
  table and its connection, connection, or structure and path; when copied) is kept in sandbox.json and shown on
  its row, in its tab (the sandbox mark and the designation), the bar over its grid and its lineage (the grid's
  origin, kind "sandbox": its designation and origin; its read-only cell loads it with sab.sql over
  [Sandbox].<table>); a branch icon wherever tables are listed. Nothing names a way back: a variant never writes
  to its origin. A connection's table read once is a variant too; files and empty tables are plain sandbox tables.

Gaps to approve (not built):
- A saved connection itself named "Sandbox" hides the project's Sandbox in DuckDB SQL (saved names win, as for any
  alias): refuse the name, or rename it on save?
- Page values: the API widgets read `{{ name }}` from st.session_state; align with the widget-gaps branch's page
  values when it merges.
- Edits of LIST, STRUCT, MAP and other nested columns in the grid are refused (edit them through the API).
- The Catalog's Sandbox section sorts in the page only (the agent sorts through `sandbox(list)`).

## Widget I/O contract and the canvas's wiring (the owner, 2026-11-21; built, branch widget-gaps)

The owner approved the widget gaps (choices from a table, a default from another widget, a page value as a
table, a several-tables picker, events wired on the Canvas, openpyxl and xlrd in a project's Python), then
added: "Make a way for input and out from widgets to be defined and clear. Perhaps the app detects a certain
format". The contract replaces the "page value as a table" property kind that was first planned: page values
ARE the Outs.

- **The format** (domain/widget_contract.py, read with ast, never run): `orders: In[Table] = None`, `region:
  In[str] = "All"`, `picked: Out[int] = None`, `saved: Event[dict]` (or `= None`, so a linter knows the name).
  Types: Table, str, int, float, bool, date, datetime, list[...], dict. `sab_canvas.In[...]`, a string
  annotation and `In["list[str]"]` read too; a declaration twice: the first counts; `_private` and anything
  not at the top level are not part of the contract; a bad marker, type or starting value is listed with its
  problem in one sentence. Plain values stay properties; together they are the contract (`contract` in
  `widgets_get` and `widgets_properties`).
- **The wiring** (domain/canvas_wiring.py; the canvas file's `wires` beside an instance's `values`,
  byte-stable): an In's source is a table, an Out (`{"out": "w3.filtered"}`, its type fitting; int feeds
  float, records feed a Table), a page value an action set, a GET endpoint's answer, a variable or a typed
  value; a list[Table] In an ordered list (the several-tables picker). An Event's wire is its actions in order
  (call an endpoint with the payload, a part of it or a field each as the body and path values; set a page
  value; rerun). **Decisions:** an unwired In takes the page's one Out of its name and a fitting type by itself
  (so the packs work as dropped: `sales_filter`, `ticket_id`, `uploaded` -> `mapped` -> `valid`,
  `form_definition`, `form_submissions`); an Event's last payload is readable as an Out; a broken wire (its
  widget or Out deleted, a type changed) stays in the file (Undo brings the widget back and the wire holds),
  marked at both ends, listed before Play and said in its place while the In takes its starting value.
- **The builder** (one, for Play, Launch and Export): the page runs each widget after what it reads (siblings
  ordered by their reads; the boxes are placed by CSS, so the order is free), so a value arrives on the first
  run. sab_canvas.render gives each In its source's value (coerced: records to a table, text to a number or a
  date), each Out its last value and keeps it after the run (`sab:<instance>.<port>` in session state), each
  Event a callable. An export's README.md lists SAB_API_URL, SAB_API_KEY and SAB_API_BASE (the deployed API)
  when its events call one.
- **Migration:** all 113 prebuilt widgets declare their Ins, Outs and Events (table properties became
  `table_name: In[Table]`, `state_key` became each input's `value: Out[...]` with `default_from: In[...]`, the
  selects got `options_table: In[Table]` and `options_column`, the pack keys became Ins and Outs, save_event
  became Events). An instance's value for a name that is now an In (an older canvas, `canvas_set_values`,
  `canvas_insert_widget`) is wired as it opens: a table's name `{"table"}`, a list `{"tables"}`, else
  `{"value"}`, said once. **Upgrade to In/Out** (domain/widget_upgrade.py; the Widgets window, a preview
  first; `widgets_upgrade`) rewrites a user widget's string session state keys (or a property holding one) as
  declarations; a write inside a block or a function is kept and said.
- **Hygiene:** the inputs' `_label`/`_problem` are the runtime's `marked`/`problem`; `sample(kind=...)` gives
  sales, orders, products, tickets and stock, so 14 pack widgets lost their own rows.
- **Packages:** a new environment gets openpyxl and xlrd (domain/environments.py EXCEL); a Python set up for
  Streamlit gets them with Streamlit (streamlit_apps.py EXTRAS, said as `extras` and never blocking); an older
  one keeps the widget's own "needs openpyxl" line. The app's own server's dependencies are unchanged.
- **The Canvas:** Properties | Inputs | Outputs | Events (canvasWiring.ts), a selected widget's sources and
  readers lit, the bottom bar's **Wiring** view, broken wires marked and listed before Play. The agent:
  `canvas_wire`, `canvas_state`'s `wiring`, `widgets_upgrade`.
- Gaps (not built, to approve): an In wired from an Out of another canvas page (refused: a page's own Outs
  only); an Out's columns for a column property wired from it (typed instead); the Wiring view's lines go
  between boxes' centres, not ports.

## The canvas's gaps: hidden widgets, the viewer, wires across pages, a project's widgets (the owner approved them, 2026-11-21; built, branch canvas-gaps)

The owner approved nine gaps the widget-gaps and test-app branches listed, and three fixes. Built:

1. **Hidden in the app** (a widget instance's `"hidden": true`; `canvas_move hidden=true`; the Canvas's Layout
   section). It runs and its Outs flow; the played, launched and exported page give it no space (CSS
   `display: none` in both layouts; the page's height ends at the last shown item). The canvas draws it faded
   with an eye-off mark. **Decision:** a container with no title holding only hidden widgets takes no space
   either (a widget dropped on the page alone gets a container round it: api_bridge's 60 px blank row is
   gone). A container cannot be hidden in the app (Show on covers that).
2. **Who is viewing:** the app's own Out `app.viewer` (a str), readable by any In (`{"out": "app.viewer"}`; an
   In[str] called viewer takes it by itself), and `sab_canvas.viewer()` / `viewer_info()` in a widget. Never
   invented: Azure App Service's sign-in headers (X-MS-CLIENT-PRINCIPAL-NAME, only when WEBSITE_SITE_NAME says
   it is App Service: elsewhere anyone could send them), else Streamlit's own `st.user` when the app signs
   people in, else SAB_LOCAL_VIEWER (this computer's user name, set by Play and Launch only), else "unknown".
   **Dev Tunnels:** Microsoft Learn's Dev Tunnels security page describes the tunnel's access checks and
   "header rewriting" but documents no header that carries the visitor's identity to the app, so a shared
   app's viewer is "unknown" (the shared run is given no SAB_LOCAL_VIEWER: the host's own name would be a lie
   there).
3. **Sandbox tables as inputs:** a table In's picker offers the project's sandbox tables first (`[Sandbox].t`,
   the connection-tables contract's Sandbox alias, read from the sandbox file: never live data). No change to
   the sandbox or the local API builder's files: the extension's own connection listing names the Sandbox's
   tables (extension.py).
4. **Wires across pages:** an In reads any page's Out (`{"out": "w3.x"}`: instance ids are the canvas's own),
   kept in the app's session state (`sab:<ref>`, which st.navigation keeps across pages), said "<page> ·
   <widget>.<port>". Automatic wires stay on their page. Until the other page has run in the session, the In
   takes its starting value. The Wiring view draws it as a stub with the page's name; a broken one is marked.
5. **A wired table's columns:** `wiring.columns`: an Out[Table[Row]]'s declared fields, else the columns Play
   last saw (sab_canvas writes `.sab_columns.json` beside the played app: names only, only in Play); a column
   property wired from that Out offers them in a box that still takes a typed name.
6. **Port-to-port lines:** a dot per In on a widget's left edge and per Out or Event on its right; each line
   from the exact Out dot to the In dot.
7. **Typed payloads:** `saved: Event[Order]` (and `Out[Table[Row]]`) with Order a TypedDict or dataclass of
   the widget's own: the port's `schema` and `fields`; the Events' body boxes offer them. `Event[dict]` works
   as before.
8. **File:** a contract type (`sab_canvas.File`: name, size, type, bytes; `as_file`). input_file,
   input_camera and input_audio give `file: Out[File]`; excel_upload takes `file: In[File]` (wired by itself
   from a page's one `file`), reading it instead of its own upload (a type it does not take is said).
9. **A project's widgets folder:** `<project>/widgets/` (shared in Git with the project) beside the library's:
   the lists show This project, Library, Prebuilt; a project's name wins ("Instead of the library's");
   `widgets_copy to=project|library`, `widgets_new where=project`; a save writes where the widget lives; an
   export carries the project's widgets it uses in `widgets/`. examples/forms_recon's api_bridge is now a real
   project widget (its test no longer copies it into the library).

Fixes: excel_map_columns keys its pickers by the columns it maps (a real upload guesses again); a
container's title is in the flow with its widgets in a box below it (one line, 28 px, reserved as the canvas
draws it; a wrapped title pushes them down; one drawn in the title's line sits under it); the api_* widgets
call the runtime's one `api_call` (their own HTTP helper went). Found on the way: an export said every app
calls the API (the runtime itself holds api_call): now only a widget's or the wiring's use counts.

Gaps to approve (not built): a container Hidden in the app with a title; the viewer's other claims (email,
object id, roles from X-MS-CLIENT-PRINCIPAL); an Out's columns from a run that Launch (not Play) made. Also
found, not built: examples/forms_recon's canvas predates the widget contract (its form_picker, form_designer and
api_bridge instances still name session keys the contract replaced), so its browser test fails on the base too:
rewire it to the contract (form_definition Out into an In, the designer's `saved` Event calling PUT /forms/{id}
in place of the second api_bridge). BUILT (2026-11-21, branch api-approved): form_designer took `start_from:
In[dict]` (what its definition_key did: the picker's form to start from), the designer's `saved` Event calls PUT
/forms/{form_id} (the second api_bridge went), the project's api_bridge declares named Ins (trigger, form, period,
loaded_by, records, run, status and the reconciliation's fields) that its `@name` templates read and Outs `answer`
(an object) and `listed` (a list); every instance wired through the agent's canvas_set_values, canvas_wire and
canvas_delete; canvas_set_values with null now takes away a value the widget no longer has.

## The forms and reconciliation test app and the local API's stress test (the owner, 2026-11-21; branch test-app)

The owner: "create a local API using the local API builder and scripts. Build some widget starter packs. Build a
large dataset. Build three app pages and stress test the API against the data" / "Make your mock something like
it" (his POC: forms people design and fill, a column store, a reconciliation run the same way every month).

### Built
- examples/forms_recon: a project made by the app through the agent's commands only (project_new, datasets_load,
  tabs_new_query for the Trino copy, sandbox add from a grid and by columns, workbench_save for API.py,
  workbench_format, widgets_new and widgets_save for api_bridge, canvas_page/add_container/insert_widget/move for the
  pages, canvas_play check, app_launch). API.py: forms and their fields with versions; batches (typed, Excel, a
  source table) and entries stored long (form, batch, row, field, a value in its field's type); the column store
  per form by DuckDB PIVOT; reconciliation definitions (source table, keys, compares with tolerances, totals) and
  runs per month (or "all"), results kept and paged by status, sign-off. Three pages: Form designer, Fill and load,
  Reconcile, in Desktop and Phone layouts.
- Decisions: the sandbox's data is Git-ignored, so the example holds no rows: its test adds Larkfield Goods' small
  scale itself. A new number is taken inside its INSERT (`max + 1` in one statement) since the mock has no
  sequences. The project's widget api_bridge lives in the library; its file is kept in the example (widgets/),
  copied from the library (gap 6).
- The stress test (tests/stress/, SWISSARMYBENCH_STRESS=1) and its numbers: docs/verified.md.

### Performance fixes in the local sandbox API builder (fixes, not features)
1. `executemany` was one HTTP request and one DuckDB execute a row (100k rows: hours); now one call per 50,000 sets,
   the statement translated once, and a plain `INSERT ... VALUES (?, ...)` goes in as one columnar insert (Arrow),
   all in one transaction (services/sandbox.py `sql_many`, adapters/sandbox.py `insert_columns`, `change_many`).
2. `connection("Sandbox")` is one MockDuckDB for the process, and its execute() kept its answer on the object: two
   requests at once fetched each other's rows. Its answer is now per thread.
3. Every mock call listed every table and counted each one's rows (`files.tables()`), and read sandbox.json from
   disk: the names are now read once until a table is added, dropped or put back, and sandbox.json read again only
   when it changes.
4. sqlglot parsed each statement on every call: the translation is kept by its words (an LRU of 512).
5. One lock held every read: reads and writes now share the file (DuckDB's own transactions), and only a reset,
   baseline, checkpoint or a table added or dropped holds it alone.
6. The hosting process's socket did not say TCP, so asyncio never set TCP_NODELAY: every request after a kept-open
   connection's first waited about 40 ms (Nagle and delayed ACK). The mock's door to the app keeps its connection
   open too (it opened one per call).

### Gaps to approve (none built; the test app works round each)
1. **A widget's event cannot call an endpoint.** Form designer's Save, Fill a form's Submit and Validate rows' valid
   rows land in session state; nothing sends them to API.py. Worked round with api_bridge (a widget made in the
   Widgets window: a trigger key, path values and body from page values). Add: an "on <event>, call <endpoint>"
   wiring on the canvas. M. (The widget-gaps branch: canvas events wired to API endpoints.)
2. **An API's answer cannot feed another widget.** Form picker's forms, the batches list and the results table come
   from the API; prebuilt widgets read tables by name or their own lists. Worked round with api_bridge's result_key
   and its own table and metrics view. Add: page values as tables. M. (widget-gaps.)
3. **api_table, api_button and api_form take fixed path values and bodies**: the picked form and month cannot go
   in. Add: a path value or body field from a page value. S. (widget-gaps: default_from_key.)
4. **Choices are fixed lists**: the months, the source tables, the fields Map columns asks for (they should be the
   picked form's). Add: choices from a table or a page value. S-M. (widget-gaps: table-fed choices.)
5. **Map columns keeps the guesses it made for its made-up sample** after a real upload (its selectboxes keep their
   state), so line_id and amount had to be picked by hand. Add: key its pickers by the uploaded columns. S (a fix
   to a prebuilt widget).
6. **A project cannot carry its own widgets**: they live in the library, so the example's api_bridge was copied out
   of it by hand to keep the example whole. Add: a project's widgets/ folder read beside the library, or widget
   Export and Import. M.
7. **A file's table cannot say which connection it stands in for**: Add to sandbox from a file is always the plain
   DuckDB mock, so the "Trino" and "Dynamics 365" copies are mocked as DuckDB, not as Trino's or Dataverse's
   clients. Add: "mocked as" a connection (or kind and dialect) on a file's or grid's Add to sandbox. S-M.
8. **The mock refuses CREATE**: no view or table, so the column store is a PIVOT run again on every page (64 ms for
   a month of 42k entries; 0.33 s for 1M), and no sequence, so numbers are `max + 1`. Add: CREATE VIEW, CREATE
   TABLE AS and sequences on the sandbox, undone by Reset. M.
9. **An endpoint cannot list the sandbox's tables or columns** (system views refused): it cannot check a source
   table's name or offer its columns. Add: the mock's own tables() and columns() for connection("Sandbox"). S.
10. **A read past 10,000 rows is cut without a word** (MAX_ROWS_ANSWERED): the mock's fetchall() returns the first
    10,000 and the endpoint cannot tell. Add: say it (an error naming the limit) or page underneath. S.
11. **Every agent write through `api call` waits for Allow**, so the agent cannot build test data in the sandbox
    without the user clicking each one; the writes here went through the played pages. Add: "Allow the agent's
    writes to this sandbox for this session" (Reset undoes them). S.
12. **A widget that only moves data still takes a place** (api_bridge's fetch: a 60 px blank row on the page).
    Add: a hidden instance (no box) on the canvas. S.
13. **Who is using the app**: sign-off and "loaded by" are typed names; a played, launched or shared app gives
    widgets no viewer identity. Add: the viewer's name (a shared app's Entra user) as a page value. M.
14. **A long container title wraps over its first widget** in a narrow played page (Reconcile's title did). Add:
    the title's height follows its lines. S.

## The API builder against our good designs (the owner, 2026-11-21: "Use a critic agent/fable to improve the API builder using our good app designs"; branch api-critic)

A critic used the builder as a user would (a made-up clinic and depot: sandbox tables, New endpoint from a
table, API.py edited, Run, Try it, Export, a canvas form's Save wired to an endpoint; through the agent's
commands and the pages) and held it against the designs that already feel right: the blade IDE (8.14: the code's
bytes are the file's, Run beside the code, a failure with its line), the Analyze contract (8.13: one definition
read by the form, the sample, the fixes and the agent), the Canvas's contract and wiring (a mismatch refused
with its reason before Play), the connection forms' live checks, the one loading state and the one error note.

### Fixed (existing behaviour; tests/test_local_api_critic.py, tests/e2e/test_local_apis_page.py)
- **API.py was corrupted by the Scripts page.** With a table open, API.py in front took the Tables group (`# region
  Tables`, a `duckdb.read_csv` of the user's own file), showed as changed, and a Save wrote it in: the header was
  no longer the file's first lines (name, target and base path read as the defaults), the API's process read a
  real file, and every line number moved by nine. API.py never takes a table's cell now (workbenchPage.ts).
- **Run file on API.py failed and offered to install `sab_api` from the package index.** Its main Run is **Run
  API** (F5): saved, then hosted as the APIs page hosts it; a start that fails is said there with its line. No
  Run as scheduled on it.
- **New endpoint from a table over a date or timestamp column made an API.py that did not start** (`NameError:
  name 'date' is not defined`). The import is written, among API.py's own imports (no lint note, no `noqa`).
- **A refusal was a red status and a raw JSON tree.** Try it shows the one error note: the sentence, "API.py line
  N" (the host notes the failing line of an endpoint's own error; the mock's refusal carries its own), Go to
  line, the answer behind Details, Send to the agent. `api(call)` answers `error`, `line`, `where` too; the
  request log says a refusal's words and line. The API's own answer is unchanged (an export answers the same).
- **An open Try it lost what was typed** on every redraw (API.py saved, the API started again, any file changed
  anywhere): the edit, save, try again loop. The box, its values and its last answer are kept while the endpoint
  takes the same parameters; the box being typed in keeps the keyboard.
- **What API.py printed was never read:** past the pipe's 64 KB the endpoint that printed waited for ever. Both
  pipes are read to their end; the last 200 lines are `api(log)`'s `output` and the page's folded Output.
- **One definition.** The Try it body was made up by the page's own rule and the Canvas's field list by a third:
  the endpoint's `fields` (type, required) and `try` (a made-up request; the kept example first) are the
  server's (domain/local_api.py body_fields, made_up), read by Try it, the Event mapping, Payload shapes and the
  agent. The targets' picker reads the backend's registry (an extension's target was never offered: the page
  had its own list of three).
- **Payload shapes did not look at Events.** An Event wired to call an endpoint is listed and checked: a mapped
  field the body lacks, a required one not sent, a `{name}` of the path with no value, a body sent to an endpoint
  that takes none. "Fits" went (7.9).
- **A path no endpoint answers** was the framework's bare "Not Found" (no key asked, not logged): it is the API's
  own `{"error": "No endpoint answers GET /x."}`, as an export answers. The log counted an error as one row.
- **An export of `connection("Sandbox")` endpoints with no rows** said so only in README.md: the answer's
  `warnings` and an amber note in the dialog say it.
- **A canvas export always listed SAB_API_URL, SAB_API_KEY and SAB_API_BASE** (the runtime's own api_call was
  read as a use): only an app that calls the API lists them (tests/test_api_widget_paths.py failed on it).
- **Words:** "key is not a int" is "not a whole number" (a number, true or false, a date); a mock's refusal said
  "API.py line 139: Line 1: ..." and says the line once; "Variables to set: (none)" is "None."; "it uses []"
  went; "No APIs yet." under a project's own API is "No imported APIs yet."; the failed start's toast went (its
  note is in place); a settings refusal shows at its own box; the guide's Event wire is `{"actions": [...]}`.

### Proposals to approve (none built), best first
1. **The body is checked against its model.** A TypedDict body is passed through as sent: a wrong type is a 500
   from the database ("Conversion Error"), an unknown field is silently dropped by the CRUD set, `required` is in
   the OpenAPI document only. Check it in sab_api (422 naming the field, as a dataclass body's unknown field is
   already), so the model, Try it, the widgets and the export agree at run time too. S-M. (Changes what an
   existing API.py answers: the owner's call.)
2. **One slim bar for the API, as the blade IDE's.** The head is nine controls over two rows (name, Target, Base
   path, status, Run, Open API.py, New endpoint, Will this work for real?, Export) above a Sandbox head of four
   more. Name, the dot, Run / Stop, Open API.py, and "…" for the rest; Target only in Export (it is asked there
   again); Base path in Properties. M.
3. **Try it beside the code.** The loop is two windows (Scripts for API.py, the APIs page for Try it). An
   Endpoints pane on API.py's tab (folded, 8.14): each endpoint, Try it, the answer and the request log under the
   editor as a blade's Output | Result | Problems. M-L.
4. **An Event's payload has fields.** `saved: Event[dict]` says nothing of what it sends, so the Canvas asks for
   `values.patient` typed by hand once per body field (six for a six-column table). Let a widget declare the
   payload's fields (or read them from a table In's columns) and map by name by itself, as Analyze picks the
   obvious column; a mismatch then reads as an In's does. M.
5. **The sandbox keeps its keys.** A table's key is known (New endpoint asks for it) but the sandbox takes a
   second row with the same key where the real database would refuse: an app passes here and fails live. A
   PRIMARY KEY (and NOT NULL where the source says so) on the sandbox table, refused in the source's words. M.
6. **Allow the agent's writes to this sandbox for the session** (the test app's gap 11): every `api(call)` write
   waits for Allow, so an agent cannot fill test data; Reset undoes anything it does. S.
7. **A read past 10,000 rows says so** (the test app's gap 10) and **the mock answers its own tables() and
   columns()** (gap 9): the two refusals met first in real use. S each.
8. **API.py's problems as you type.** The Scripts page lints Python but not the API's own rules (a path with no
   parameter, two endpoints on one path, a connection with no table in the sandbox yet, SQL the mock will
   refuse): they show only on the APIs page. Squiggles in the editor from the same parse; `sab_api` and the
   sandbox's tables and columns in completion. M.
9. **New endpoint from a table asks less and names better.** `get_visits`, `create_visits` and `/visits/{key}`:
   singular names (get_visit) and the key's own name in the path (`/visits/{visit_id}`); a tick per operation
   (a read-only source needs list and get only); a preview of the code before it is written, as a blade's
   scaffold. S-M.
10. **Export's Compare in Monaco's diff editor** (the Canvas's Builds compare has it; the export shows two
    `<pre>` side by side), and **Export… from the agent as a dry run** (what would be written, kept, removed). S.
11. **`api(state)` in brief.** The agent's state answers the whole OpenAPI document every time (10 KB for nine
    endpoints): `state` without it, `openapi` for it. S.
12. **A saved connection named "Sandbox"** (the earlier gap) is refused on save. S.


## Next project type: Databricks (the owner, 2026-11-21, for future reference)
"The next canvas instead of tools we create will probably be for databricks." Not designed yet: ask the owner first.
It follows design principle 13a's last rule: the Databricks extension may look and work completely differently, but
reads and writes only through the shared tools (the connections' read/write contract, the sandbox, the local sandbox
API and its targets, convert.py, the widget contract); none of those changes shape for it.
## Simplicity pass, 2026-11-21 (the owner: "find over complications and just uncomplicates them"; built, branch simplify)

The rule is design principle 13, "Build the simplest thing for the task at hand", with the owner's three
additions of the same day: generated code reads like a roadmap; more than three def levels draws heavy
criticism and two mild; one universal tool over several special ones. A simplification never changes what
the user sees, what a route answers, what an agent command does or a file's format; a feature is never
removed here (the questions for the owner are in the branch's report).

How it was measured, not guessed: a dead-code scan (vulture, with and without the tests as callers) and a
word count per name across src, extensions, web and tests; identical function bodies by their syntax tree;
front-end exports nothing imports; nesting by the syntax tree (Python's ast; the page's TypeScript through
esbuild and acorn).

What was simplified (11 commits, one each, so any one can be reverted):

| What | Lines |
|---|---|
| `sab_queries.py`, the old app canvas's query module nothing wrote any more (domain/page_queries.py, script_runtime's two texts, the service's query_module) | -290 |
| Five extension hooks nothing fills since app notebooks went (canvas, read_trace, kernel_stopped, stop_orphans, canvas_references) and the lineage service's canvas-block path behind them | -81 |
| 30 names with no caller (13 constants, 11 functions and methods, 4 types, 2 kept alive only by their own test) | -176 |
| 200 route handlers' own `try/except Exception: return error_response(error)`: `http.safely` where they are registered | -601 |
| 72 handlers that only forwarded their body: `http.with_body` and `with_actor` | -187 |
| Functions three levels deep and the deepest blocks flattened (http.answered, http.json_lines, module-level factories, three helpers) | +22 |
| One loader for Monaco and one for the diagrams (web/src/lazyLoad.ts), instead of eleven copies | -31 |
| The connection form's field order as module functions, not closures four deep | +5 |
| The library's text folder (read, write only when changed) written once (atomic_files.TextFolder) | -17 |
| Six front-end exports nothing imports | -78 |
| Generated code as a roadmap: a "Laid out top to bottom" sentence in the 51 starters with functions, a line over each of the 28 uncommented Write mode functions, the exported script's and notebook's layout in their heads | +192 |

In all 175 files, 2,756 lines out and 1,514 in: 1,242 fewer, 1,434 fewer without the roadmap text the owner
asked for.

Nesting, before and after:

| | Before | After |
|---|---|---|
| Python functions at def level 2 (mild) | 938 | 865 |
| Python functions at def level 3 | 23 | 9 |
| Python functions deeper than 3 (heavy) | 0 | 0 |
| Python's deepest block nesting | 9 (claude_finder's registry walk) | 7 (an excluded file) |
| Python functions with blocks 6 or deeper | 6 | 3 |
| Page functions named at level 4 (heavy) | 12 | 9 |
| Page functions named at level 3 | 189 | 189 |

Decisions:
- **Strict over broad.** A handler lost its try/except only when the try was its whole body, so no error
  path changes; handlers with code before the try or another except keep theirs (about 50).
- **Unfilled is not always dead.** Three more hooks (documents, held, unsaved) also lost their filler when
  app notebooks went, but base features read them (a swapped connection's cells in an open document, the
  Connections page's references in open documents): that is a regression to decide on, not code to delete.
  Left as they are and reported.
- **The ports stay.** Most service Protocols have one implementation; REFACTOR.md asks for them (the layers),
  so they are not "a class with one user" here.
- **The starters stay self-contained.** 2,100 lines of them are identical helpers (Power BI's sign-in in 13,
  Excel's open and save in 12, the Write modes in 8): a starter is copied as the user's own file, so the
  copies are the design. Whether one universal write function should replace the 70 Write starters is a
  question for the owner.
- Left for the second pass (their builders merge first): everything under extensions/streamlit, the local
  sandbox API and sandbox files, codeIde.ts, canvas*.ts, widget*.ts, workbenchPage.ts.


## One adapter (the owner, 2026-11-21)
The owner's model replaces the per-feature data paths: API -> sab_adapter.py -> tables; Connections -> sab_adapter.py
-> Grids; Grids -> Notebooks; Grids, Blades, Variables, Structures -> Widgets -> Canvas. The adapter streams reads and
writes and holds nothing; grids (named Arrow tables) are the only data kept; an export is the fewest files that build
the app. The per-source mock clients are dropped (the owner: "use my model"). Plan: Plans/adapter.plan.md.

**Phase 1 built (2026-11-21, branch adapter).** Decisions:
- Where it lives: `src/swissarmybench/adapters/sab_adapter.py`. It is a driven adapter (DuckDB and Arrow), so the
  layers test allows its imports there and the wheel ships it; it imports nothing of `swissarmybench` (a test holds
  it to the standard library, duckdb and pyarrow, and runs a copy of it alone), so an export copies its bytes as they
  are. The API's process names it `sab_adapter` (`from sab_adapter import read, Plan`).
- The contract: `tables(source)`, `read(source, table, plan) -> (RecordBatchReader, Folded)`, `write(source, table,
  batches, key, mode) -> Counts` (insert, update, merge, delete; all or none), `grid(name)`, `refresh(name)`;
  `from_json(pages, columns, strict)` (DuckDB's json_transform a page at a time; the first page's types when none
  are given). A source is any object with the three functions; `use(find)` says how a name is found.
- The plan: columns, filters ([column, op, value]: = != < <= > >= in between like, is null), sort, limit, offset,
  group and totals (count, count_distinct, sum, avg, min, max). A source says which parts it folded; they must be the
  first ones in SQL's order (filters, group, totals, columns, sort, offset, limit), and the rest is done by DuckDB over
  the stream. DuckDB folds it all.
- Holding nothing: a read is a reader that keeps its connection (the sandbox's: its gate) only while read. DuckDB
  2.0 copies a DB-API result's Arrow (`execute(...).to_arrow_table()` warns), so the adapter reads
  `con.sql(sql, params=...).to_arrow_reader(50_000)`.
- Grids: in the app the dataset store keeps a grid (the adapter's `make_grid` makes it); `Grids` and `grid(name)` are
  for a kernel, the API's process and an export.
- Moved: the sandbox's Open in Grids and [Sandbox].table; a DuckDB file connection's Open as grid (its child process
  reads the user's own connection through the adapter: the limit folded, the count a total, DuckDB's own types); a
  local sandbox API's sandbox (sab_adapter.Remote: /sandbox/data/<key>/tables, /read as an Arrow IPC stream with
  X-Sab-Folded, /write an Arrow IPC stream in; /sandbox/adapter/* with the token); every SQL mock's tables() and
  columns(); the SharePoint mock's rows(), read(), create(), update(), delete() (its rows typed by the list's
  columns, strict).
- What stays on the mocks: SQL in a source's dialect (cursor().execute, read_arrow), Dataverse's OData and FetchXML
  text, MockDuckDB's SQL, the ids() lookup: they need domain/sandbox_dialects.py, so they go when each kind becomes a
  backend with its own folding (Order 2). Small change: the SharePoint mock's update and delete now answer the rows
  changed (was: the rows given), and an empty read keeps its columns' types (was: text).
- Not built, and what each needs: contract.json loading (a JSON schema, the base reading MODE from it); folder
  extensions; the endpoint wizard; the other connection kinds as backends (each kind's tables, read folding its
  plan into its dialect by sqlglot or OData/Graph, write by its Write starter's statements); the export's file list
  (sab_adapter.py beside sab_api.py: an API.py that imports sab_adapter is not exportable until then); a kernel's
  `sab.grid` (the client importing the adapter lazily: the plain client stays standard library); the answer path
  (Arrow to JSON for an endpoint's answer, a request body through from_json and its model); streaming the child
  process's answer (today one Arrow IPC base64 in its JSON line) and a write's body (Starlette reads it whole).
- An Excel workbook (the owner, Plans/excel.plan.md) fits the contract as one more source: tables its sheets and
  named tables, read folding nothing (DuckDB does the plan over its batches), write a sheet. Its "sheet replaced,
  others kept" needs a `replace` mode MODES does not have yet.
- The places outside the adapter that still open a driver or turn JSON into rows (tests/test_adapter_boundary.py, -s
  prints them): adapters/catalogs, codegen, database, datasets (read_json), export, found_connections (sqlite3),
  intellisense, sandbox, views, apis and library (read_json), bootstrap.py, stats.py, server/http.py, routes_agent,
  routes_grids (duckdb), client/sql_cell (duckdb, from_pylist, from_records), structures_client (from_records),
  writes and write_sql, server/sandbox_clients (from_pylist, from_records for the SQL mocks), the 14 Write starters;
  SQL text: domain/api_clients and powerapps' ts_notebook (read_json_auto), domain/sharepoint and blade_templates
  (read_json); the extensions' accounting runtime (duckdb), service (read_json), powerbi's pbix readers (pbixray).
  Many are the app's own engine (the locked DuckDB, views, the SQL box), not a source's data: the later steps decide
  which are "data calls" under the rule.

**Phase 2 built (2026-11-22, branch adapter-2).** Decisions:
- `truncate` (the owner's fifth mode): `write(source, table, mode="truncate")` with no rows clears the table and keeps
  its columns; with rows, DELETE then INSERT in the one transaction. The change log counts it as deleted plus
  inserted rows.
- The words (the owner, 2026-11-22): `table(name)`, `Tables`, `TableSource`, `make_table`. Phase 1 was unreleased, so
  no old name is kept.
- SQL databases are one backend, `Sql`, with each dialect's rules as data (`DIALECTS`), not one class per kind: the
  same plan, a different quote, mark, LIMIT/OFFSET/FETCH form (T-SQL's TOP and its ORDER BY) and catalog. The
  adapter stays standard library + duckdb + pyarrow (an export copies it), so the dialect SQL is written by it and
  the tests read every dialect's query back with sqlglot. Marks follow the driver's paramstyle. A connection that
  types its own Arrow (SQL Server's `read_arrow`) is read by it when nothing is bound, so its types stay. A write
  is the source's own INSERT/UPDATE/DELETE in one transaction; a merge asks which keys are there (100 at a time),
  updates those and inserts the rest (portable, not a MERGE statement: the SQL Write starter's MERGE WITH
  (HOLDLOCK) and #temp staging stay the starter's); Trino (no transactions) is read-only through the adapter.
- Dataverse's Web API is `OData`: filters (eq, ne, lt, le, gt, ge; in as or; between as ge and le; null; a like with
  only a leading or trailing % as contains, startswith, endswith), columns, sort and limit folded into the
  connection's own rows(); a choice's label or a lookup's name cannot be filtered or sorted in OData, so such a
  plan is done by DuckDB over the answer. FetchXML aggregates (group, totals) are not folded yet. Records typed by
  the metadata through from_json. Its count is the one Dataverse gave (`OData.total`).
- The lakes and SharePoint share one backend, `Rows`, over their own `rows(table, schema, limit, columns, filters)`
  (Graph's $filter, a file's partitions are theirs): filters, columns and limit folded; a sort stops the limit.
- The open tables are a source served by the app (`/workbench/tables/adapter/tables|read`, the same Arrow IPC shape
  as the sandbox's door; `Remote` takes headers for the token). `sab.table(name, columns, filters, sort, limit)`
  reads it (Arrow; the plain client without duckdb or pyarrow reads the whole view as before). A kernel's DuckDB SQL
  naming an open table reads it through `sab.table`.
- API payloads: sab_api reaches sab_adapter only when it is beside it. Arrow results are answered by `to_json`
  (written a batch at a time; the same JSON as plain) or `to_ipc` for `Accept: application/vnd.apache.arrow.stream`
  (a widget); a body `Annotated[pa.Table, Model]` is checked as `list[Model]` then made Arrow by from_json, strict;
  API.py's reader shows it as `list[Model]`.
- Export: every API target has `sab_adapter.py` and duckdb, pyarrow in its requirements. The canvas and script
  exports do not yet: nothing in them reads through the adapter, and a file nothing uses is not exported.
- Left of the simplicity pass: renamed.py and `%%sag` are gone; the five route modules lost their catch-all guards
  (routes_connection_tables keeps its two own answers, narrowed to their types). bootstrap()'s split by area is not
  done (it is the next merge-conflict magnet: the adapter work touches it in two places only).

**For the owner to decide (not built)** (decided 2026-11-22, Plans/adapter.plan.md "after phase 2"; built in phase 3, below):
1. The mock clients and sandbox_dialects.py. An endpoint today runs SQL in its source's own dialect (forms_recon's
   API.py, the scaffold's CRUD). Taking the mocks away means endpoint code calls the adapter (read with a Plan,
   write by mode) instead of SQL text, and SQL that a Plan cannot say (joins, a CTE) needs a home: (a) the adapter
   gains `query(source, sql)` in the source's dialect, and the sandbox backend keeps translating it (so
   sandbox_dialects.py stays as the sandbox's part of the adapter); (b) endpoints write DuckDB SQL over
   `table(name)`s only; (c) both. Recommended: (a) for compatibility, with the scaffold moving to Plans.
2. Writes for Dataverse, SharePoint and the lakes through the adapter: the Write starters' $batch, Graph and Delta
   writes become each backend's `write` (and truncate: a Delta overwrite; a SharePoint list cleared item by item).
3. The app's Catalog listing through `tables()`: today it runs the connection's own (editable) List the tables
   query; the adapter's listing would ignore a user's edit. Keep the user's query as the listing, the adapter's
   as the export's?
- What each later piece needs from phase 2: contract.json loading needs nothing of the adapter; folder extensions
  add sources by the three functions (`Sql` with a new `Dialect`, or their own class); the Environment page needs
  `table(name)` in a session (built: `sab.table`) and the open tables' listing (built: the adapter's tables door);
  the Excel module is a `Rows`-like source plus a `replace` mode (truncate covers "clear a sheet"); sab.write is
  `write()` through the open tables or a connection (the open tables' write is not built: it is a grid edit, the
  sandbox grid's only); the endpoint wizard writes Plans and `Annotated[pa.Table, Model]` bodies.
- The boundary list now (tests/test_adapter_boundary.py, -s prints it): moved and enforced: a database connection's
  Open as grid for every dialect the adapter knows; a kernel's read of an open table; a local sandbox API's process
  opens no driver; the mocks' listings and SharePoint's reads and writes. Still outside: adapters/catalogs,
  codegen, database, datasets (read_json, the engine's loaders), export, found_connections (sqlite3), intellisense,
  sandbox, views, apis and library (read_json), bootstrap.py, stats.py, server/http.py, routes_agent, routes_grids
  (duckdb), client/sql_cell (duckdb, from_pylist, from_records), structures_client (from_records), writes and
  write_sql, server/sandbox_clients (the SQL mocks' SQL), blade_runner's old SQL path (dialects the adapter does not
  know), the Write starters; SQL text in api_clients, ts_notebook, sharepoint and blade_templates; the extensions'
  accounting runtime and service, powerbi's pbix readers.
**Phase 3 built (2026-11-22, branch adapter-3).** Decisions:
- `query(source, sql, params)` is one statement in the source's own SQL and its driver's marks (params by place,
  or by name as a dict); a read is streamed, a write runs in its own transaction and answers its RETURNING rows,
  else one `count` column (DuckDB's own `Count` renamed, so every source says it alike). A source with no SQL
  (OData, Rows) refuses in one sentence; the sandbox's Dataverse is SELECT only, as the SQL endpoint.
- `Connection` is in the adapter (sab_adapter.py), not sab_api: an export copies it with the rest, and sab_api's
  `connection(name)` gives it when sab_adapter is beside it. `read` takes a Plan or its parts by name; `write`
  takes Arrow or a list of dicts; `records()` takes Arrow (and a cursor, as before).
- The JSON op door (`/sandbox/data`, `/sandbox/data/{key}`: query, table, insert/update/delete, sql, sql_many,
  odata, fetchxml, list, client, more) went with the mocks: the adapter's door is tables, read, query and write
  as Arrow. Dataverse's OData and FetchXML text and a SharePoint list's filter text are no longer translated: an
  endpoint reads them with a plan, which the real source folds into its own OData or Graph call.
- What a user's own API.py sees differently (say it to the owner): `connection(name)` no longer has its real
  client's shape (cursor(), execute(), rows(), fetch(), create()...): an API.py written for the mocks must move to
  read, query and write (the refusal says so in one line). A refusal's type in Try it is `AdapterError` (was
  `MockError`); its words are the same. New endpoint from a table writes one style for every source (was T-SQL,
  OData, list calls by source). A read past 10,000 rows is one stream (no `more` pages).
- Writes: the protocol code moved into the adapter for Dataverse (stdlib HTTP on the connection's own address and
  token); SharePoint lists and the lakes keep their protocol in their connection's own code (create, update,
  delete, ids; write_delta, delete_delta, write_file) and the adapter drives it, as Rows' read does. Dataverse and
  SharePoint have no transaction across batches: a refusal says what was written before it. A Delta `update` is a
  merge of only the keys that are there; a lake or plain file takes truncate and insert only.
- A dry run is the adapter's `planned()`: counts by reads through the source (a key a hundred values at a time as
  an `in` filter the source folds), so every source's dry run is the same code. An update with a key that is not
  there stops in the starter ("an update only changes rows that are there (merge adds the others)").
- The starters keep their names, modes and dry_run; Dataverse and SharePoint lists take `truncate` (new).
- "Edited" (the Catalog's listing): a connection's List the tables differs, whitespace aside, from its starter's
  listing query (or its language does). An unedited one is listed by `tables()` in the connection's child process
  only for the dialects whose adapter listing is its starter's row for row (DuckDB, SQLite: a test compares the
  two; PostgreSQL: the same information_schema query). The adapter's Table carries schema, kind and database and
  its Column nullability (not compared, so earlier equalities hold).
- Files: DuckDB's readers (read_csv, read_parquet, read_json), each file a table by its path without its suffix; a
  write is a file written beside and put in its place. The app's own Open as grid of a file connection stays on its
  loader: its pyarrow fallbacks (a stray value read as text, cp1252 and latin-1 files) type some files otherwise.
- The engine: exports, the "+" tab's and SQL box's tables and a kernel's view read through `query` over the app's
  DuckDB session (`DuckDB.session` uses a connection as it is; a kernel's view takes a cursor of its own, as the
  session may hold an unfinished execute). The window reads stay rowid ranges over the view cache.
- sab_adapter.py is allowed 2,400 lines in tests/test_architecture.py (one file by design: an export copies it).
- bootstrap(): six more module-level helpers (extensions and the update helper, the Team box, sharing, updates,
  catalog_of, used_in), the code as it was.

**For the owner to approve (not built):**
1. The old API.py client shape is refused, not kept: keep it so (the plan's "the mock clients go"), or give one
   release of a cursor-shaped helper over `query`?
2. A file connection's Open as grid through the adapter: accept DuckDB's types for CSV (a stray value fails the
   column, a cp1252 file needs `encoding`), or move the loader's fallbacks into the adapter's Files?
3. The Catalog through the adapter for MySQL, Oracle and Snowflake lists only the connection's own database or
   schema (the adapter's catalog query) where their starters list every non-system schema: widen the adapter's
   query to the starter's scope (then switch them), or keep the starters'?
4. The grid's windows and the analyses through the adapter need the view cache as a source of its own (a plan
   with a rowid range, or `query` over the cache table): is that the next step, or are they "the engine's own"?

- What each later piece needs now: contract.json loading needs nothing of the adapter. The eight-file export:
  connections.py already wires `source_from` and `Connection`; data.py needs `TableSource`s per table. Folder
  extensions add sources by the three functions (plus `query`). The Environment page reads `sab.table` and the
  open tables' listing (built). The Excel module is a `Rows`-like or `Files`-like source plus a `replace` mode
  (truncate clears a sheet). sab.write is `write()` with `planned()` as its dry run (built for every source the
  adapter writes). The endpoint wizard writes `connection(name).read/query/write` (the scaffold's style).
- The boundary list now (tests/test_adapter_boundary.py, -s prints it; 42 places): moved and enforced: a local
  sandbox API's process opens no driver and has no mock client; the sandbox's door is the adapter's four calls;
  the app-written endpoints and forms_recon call only the adapter; every export's rows, a query made a table and
  a kernel's view read through `query`; Open as grid for every dialect the adapter knows; a kernel's read of an
  open table. Still outside: adapters/apis, catalogs, codegen, database, datasets (its loaders, read_json),
  found_connections (sqlite3), intellisense, library (read_json), sandbox, views; bootstrap.py, stats.py,
  server/http.py, routes_agent, routes_grids; client/sql_cell, structures_client, write_sql, writes (DuckDB
  staging); the 12 Write starters not yet on the adapter (and the 4 that are keep `import duckdb` as their package
  mark); SQL text in api_clients, sharepoint, blade_templates; the extensions' accounting runtime and service,
  powerapps' ts_notebook, powerbi's pbix readers.

**Phase 4 built (2026-11-22, branch adapter-4).** Each change says which of the two concepts it is about (the
owner, 2026-11-22, design principle 12a): the project scaffold (sab_adapter.py and the Write starters it calls,
what an export carries) or the app (sab.write, connections_write, the Catalog, the engine). Decisions:
- The adapter only grows (12b): every change to it is its own commit and adds (Files' format, options and
  partitions; a write's Batch; Sql's value; arrow_of; listed; Column.description and position;
  Table.description). One change was caught and taken back before it landed: a failed SQL batch first raised
  the adapter's own error in place of the driver's (a caller catching the driver's would have broken); it now
  raises the driver's own error with its Batch beside it (error.sab_batch, batch_of, its notes).
- tables() keeps each dialect's own scope (MySQL's DATABASE(), Oracle's USER, Snowflake's and Databricks'
  current schema): an exported API.py names a MySQL table by its bare name. The Catalog's whole listing is a
  new call, listed(), the starter's own listing text kept in the adapter (an export copies it whole) with the
  shape of its rows; a test holds each the same as its starter's, whitespace aside.
- The Write starters: the nine moved keep their names, modes and dry_run; their checks (columns, keys, the
  table there or not) stay in SqlWrite, their writing is the adapter's. What a user sees differently: a dry
  run of an upsert lists UPDATE then INSERT (was ON CONFLICT, ON DUPLICATE KEY UPDATE or MERGE); PostgreSQL
  inserts with INSERT (was COPY: slower on very large appends); create makes the table, then writes in its own
  transaction, and takes the table away when the write fails (was one transaction for PostgreSQL and SQLite).
  The counts, the 5-row sample, "batch 2 (rows 3 to 4) failed" and the note when the target changed are as
  they were.
- Kept on their own, for the owner: **SQL Server** (its rows staged in a #temp table of the target's exact types
  with setinputsizes, one MERGE WITH (HOLDLOCK), Azure's passing errors running the whole transaction again,
  identity_insert, keys defaulting to the primary key: the adapter's generic Sql write has none of that; moving
  it means that robustness moves into the adapter as SQL Server's write, about 400 lines), **Trino** (no
  transactions: the adapter's Sql writes only in one; a write a batch at a time with "the rows before it were
  written" is a decision) and the **Excel sheet** (moves with the Excel module, Plans/excel.plan.md).
- sab.write's dry_run defaults to False (the brief's signature); its report is the starters' (counts, words, a
  5-row sample). connections_write runs it in the connection's child process, through the connection's query
  slots (the Queries window says "write"); its dry run needs no Allow, its write waits for the user's.
- A file connection's Open as grid (accepted by the owner): DuckDB's readers and types. What changes: the
  delimiter is DuckDB's sniffer's (a semicolon file is three columns, not one); a stray value further down a
  CSV, or a cp1252 or latin-1 file, refuses with DuckDB's words (was: the column as text, the encoding tried
  again); a JSON array of mixed records is DuckDB's union of types (was Python's reader, text where kinds
  mixed). Open file, a dropped file and a workbook keep the loader. Reload and the project read it again the
  same way (Origin.adapted; the project's source "reader": "adapter"). No existing test changed.
- The engine: one seam, the cursor every grid query gets (Workspace.grid_query, an Analyze run, a highlight's
  check): adapters/views.py's Adapted, its execute the adapter's query over the app's DuckDB session, its fetch*
  reading that Arrow answer with DuckDB's own values (a HUGEINT an int, an INTERVAL a timedelta, a MAP a dict).
  The steps' compile (DESCRIBE), the view cache's CREATE TABLE AS and the windows all go through it. Speed
  (docs/verified.md): a window 1 to 2 ms slower (5 to 7 ms, the budget is 300); pyarrow loads its pandas
  bridge the first time a table is made in Python (about 300 ms), so the view engine loads it in a background
  thread at start, off the first step change's way.
- bootstrap()'s split by area (step 5, no behaviour change): three more module-level helpers, the code as it
  was: _explorer (the Data Explorer's sources), _app_registrations (with each registration's connections) and
  _variables_once (the one-time password move and the ${NAME} listing). bootstrap() is 1,168 lines (was
  1,245); the rest of it is the services' wiring, each block naming the services it needs: the next helpers
  (the sandbox's seams, Set up this computer, context.md and Launch Claude) take ten or more of them each,
  so a split there means a small record of the shared services first (a decision, not done here).
- What each later piece needs now: contract.json loading needs nothing of the adapter. The eight-file export:
  connections.py wires source_from and Connection; data.py needs a TableSource per table; listed() gives a
  catalog for its README. Folder extensions add a Dialect (its listing and shape too) or a source. The
  Environment page reads sab.table and the open tables' listing. The API adapter is a source by the three
  calls (plus query). The Excel module is a Files-like source (a workbook's sheets as tables) plus a `replace`
  mode. The endpoint wizard writes connection(name).read/query/write. SQL Server's and Trino's starters onto the
  adapter need the owner's word (above).
- The boundary list now (tests/test_adapter_boundary.py, -s prints it; 42 places): moved and enforced in
  phase 4: the 13 Write functions but SQL Server, Trino and Excel write only through the adapter (no
  statement of their own); the engine's cursor (every grid query, an Analyze run, a highlight's check); a file
  connection's Open as grid. Still outside: adapters/apis, catalogs, codegen, database, found_connections
  (sqlite3), intellisense, library, sandbox (read_json, its own DuckDB file); datasets and views (DuckDB itself:
  the engine's session and loaders); export; bootstrap.py, stats.py (sab.analyze on a DataFrame),
  server/http.py, routes_agent, routes_grids; client/sql_cell, structures_client, write_sql and writes (the
  rows staged in DuckDB); the starters' driver imports (their package's mark); SQL text in api_clients,
  sharepoint, blade_templates; the extensions' accounting runtime and service, powerapps' ts_notebook, powerbi's
  pbix readers.

## The approved API and sandbox items, and three canvas gaps (the owner, 2026-11-21; branch api-approved)

BUILT, each with its decision:
- **forms_recon rewired to the widget contract.** form_designer took `start_from: In[dict]` (what its
  definition_key did: the picker's form to start from); its `saved` Event calls `PUT /forms/{form_id}` with
  `{title, fields}` mapped and `form_id` from the payload's `name` (the second api_bridge went); the project's
  api_bridge declares named Ins (trigger, form, period, loaded_by, records, run, status and the reconciliation's
  six fields) that its `@name` templates read, and Outs `answer` (an object) and `listed` (a list). Done through
  the agent's own canvas commands. `canvas_set_values` with null now takes away a value the widget no longer has
  (the upgrade's leftovers could not be removed before).
- **No connection called Sandbox** (any case, the form, a blade or a rename): refused in one sentence.
- **A read past 10,000 rows**: every mock's real counterpart hands back every row, so the mock pages underneath
  (the rest kept as Arrow, read while the gate is held so no cursor stays open on a file Reset replaces; 16 kept
  reads at most, a page asked for once gone says so). Decision: paging, never a cut, never an error.
- **tables() and columns()** on the SQL mocks (plain DuckDB, DB-API, SQL Server); Dataverse's and SharePoint's
  had theirs.
- **CREATE through the mock**: a view, a table from a query (T-SQL's SELECT INTO too), a sequence
  (`NEXT VALUE FOR` made `nextval`), and their DROP; never over a table the user added; recorded in sandbox.json
  as that connection's table ("Made by the API"), so the next statement may use it; Reset and Restore drop the
  records the file no longer holds. A view with a bound value is refused (DuckDB, like PostgreSQL, cannot keep
  one). Plain `CREATE TABLE t (cols)` stays refused: Add table… makes an empty one.
- **One Allow for the agent's writes**: the first write asks, the Allow covers the session for the open
  project's sandbox; `api writes {allow:false}` and the bar's Stop take it back.
- **The Catalog's Sandbox sort for the agent**: `explorer_browse` and `explorer_search` take `sort` and `order`,
  the sandbox list's own rule.
- **LIST, STRUCT and MAP cells**: a small JSON box in the sandbox grid (Enter writes, Shift+Enter a new line),
  JSON checked in the page, the shape checked by DuckDB's `CAST(?::JSON AS <its type>)` and refused in words.
- **The body checked against its model** in sab_api (TypedDict and dataclass, nested, `list[Model]`,
  `NotRequired`, `total=False`): 422 with `error` naming the field and `field` its path. Numbers as FastAPI's
  own (pydantic's lax mode) takes them, since an export to FastAPI answers the same and a form's boxes send
  text or 3.0: a whole number takes 3, 3.0 and "3" (never True or 3.5), a number takes "12.5"; each converted
  before the endpoint gets it. Text must be text; dates must read as ISO text (kept as sent). First found
  strict, the widget wiring test (Streamlit's number box sends 3.0) showed why.
- **The sandbox keeps its keys**: a column list's key, one asked for at Add, a connection's from the shared
  catalog, or New endpoint from a table's; kept in sandbox.json and put back after Reset and an older
  checkpoint's Restore; DuckDB's refusals said as a database says them ("Duplicate key: a row with sku: A-1 is
  there already (its primary key)."). Rows that repeat a key at Add: in without it, and why.
- **API.py in its editor**: its own rules, a connection with no sandbox table and SQL the mock would refuse as
  squiggles (source "API.py"); the sandbox's columns inside its SQL strings (three-quoted ones too), sab_api's
  names after `from sab_api import`, and Jedi reading `sab_api` as the runtime (the import lines rewritten,
  never the cursor's, so positions hold).
- **One slim bar** on the APIs page (name, where it runs, the agent's session mark, Run, Open API.py,
  Properties folded, "…"); the Target asked at New and in Properties, said (never asked) at Export.
- **Try it beside the code**: API.py's Endpoints panel on the Scripts page (closed until its status-bar toggle;
  its own switch in Settings' Panels); API.py has no Run settings or Run history panel (its Run is Run API).
- **api(state) brief**: the OpenAPI document only with `{"full": true}` (or `openapi`).
- **A container Hidden in the app** (titled too): faded with the eye-off mark, no space when played, launched or
  exported, its widgets running.
- **The viewer's email, id and roles**: `app.viewer_email`, `app.viewer_id`, `app.viewer_roles` from App
  Service's X-MS-CLIENT-PRINCIPAL (only with WEBSITE_SITE_NAME) or st.user's email; empty otherwise, never this
  computer's; `sab_canvas.viewer()` returns them all (it returned the name before: a change for a widget that
  called it).
- **Columns from Launch**: the Canvas reads a launched run's columns as Play's (launched runs already recorded
  them; only the Canvas did not look).

Gaps found on the way (proposals, not built):
1. The Endpoints panel's Go to line is an icon on its own row in a narrow panel: a smaller row for narrow panes.
2. A read past 10,000 rows now arrives whole: an endpoint that lists a 10M-row table without a LIMIT would pull
   it all into the API's process, as the real client would. A warning in Will this work for real? when a GET's
   SQL has no LIMIT and its table is large. S.
3. The body check refuses a number where text is wanted (pydantic does too); a widget that sends an id as a
   number to a str field gets a 422. Payload shapes could say it before Play. S.
4. Squiggles for API.py come from the server's parse on each lint (each pause in typing) and a dialect check of
   each SQL string: fast at today's sizes; for a very large API.py, keep the parse by the text's hash. S.
5. `sab_canvas.viewer()` changed from a name to a dict; no prebuilt widget called it, but a user's own may have.
   A one-release `viewer_name()` would ease it. S.

## Extensions as folders (the owner, 2026-11-21)
"Extensions should be loadable as a folder in the app so users can create them with their own agents as needed and
transform the app." Answers: in the library folder (library/extensions/<name>/, shared through Git); the library is
trusted (loads without asking, as blades do); a missing package through the one Install now prompt. Plan:
Plans/folder-extensions.plan.md.

## The simplicity pass: decided (the owner, 2026-11-21)
The owner's answers to the critic's list: Plans/simplify-decisions.plan.md (four cleanups, eleven removals, six merges,
what stays, and the connection colour as the card's highlight, not a dot).

## One way to make Excel: decided (the owner, 2026-11-21)
One module, sab_excel, behind the adapter; openpyxl only (xlsxwriter goes; large plain exports get slower: accepted);
the twelve cell-level starters removed (three remain); any project type may deliver a workbook. Plan: Plans/excel.plan.md.

## The Environment (the owner, 2026-11-21): being designed
"One shared space for all tables at the env level ... each project should have its own env ... a simple trigger and
watcher for any tables, vars, structures ... easy to browse on one screen ... RStudio handles this concept
beautifully." Answers: one environment per project replaces per-notebook environments; "variables" means the Python
values code makes (the library's ${NAME} settings page stays its own); the screen is called Environment. A Fable agent
is designing it from RStudio's Environment pane, Positron's Variables pane, Spyder and VS Code (a mockup and questions
to follow). Today: the watcher (client/watcher.py) finds tables in a kernel by class; the Workbench's Variables pane
shows the front kernel's values; neither browses, deletes or manages the project's tables.
Decided (2026-11-21): one process for the project as RStudio, a table shared at once, the ${NAME} settings page merged
into the Environment page, the .venv in the project folder, Remove with an "Also delete it in Python" tick.
Plan: Plans/environment.plan.md.
**The "Now" part: built (branch simplify-2, 2026-11-21).** One commit an item, each saying what a user on the old
thing now sees:
- Removed: the SwissArmyGrid old names (renamed.py keeps `env` only, for client/sql_cell.py until the adapter
  merges; its %%sag magic stays there too); the Sandbox and Visualizations old names; the old tray's cleanup;
  Settings' Panels (the Endpoints panel keeps its status-bar toggle); custom kind colours (the fixed tokens stay);
  the tour's matching game; ECharts and Graphviz (no app drawing used either: only the two card kinds went; a saved
  card of either says it is no longer drawn); Packs (the starter pack's constants moved to blade_templates.py);
  approved outputs and --check-approved; Run as scheduled and the run history (Run settings stay: Run file's
  arguments and the Variables page read them); the VS Code extension.
- The Write starters: 54 calls became 17, one a target, the mode a text placeholder (the snippet machinery has no
  dropdown); the Connections page says a kind's operations.
- Cleanups: every route guarded once (http.guarded at the app; 252 safely wrappers and 35 generic excepts went;
  five route files the adapter branch owns keep theirs); the app canvas's leftovers (html_cells' pages, sab_text,
  lineage's page walk, ~1,200 lines of dead CSS); bootstrap's self-contained parts as module-level helpers (the
  services' wiring waits for the adapter); nine "write when changed" adapters on write_atomic(if_changed=True);
  dom.ts's dateTime and plural.
- The connection colour is its box's border and tint; the dot and the card's corner swatch went.
- Not done here, and why: the base's .stapp.json recognition (the Streamlit extension's one-line "gone" for an old
  app canvas needs it); streamlit_use.py (still used); the server's VS Code opener path in live_updates; the rest of
  bootstrap's split and cleanup 4 (after the adapter).

## The API adapter (the owner, 2026-11-22): proposed
api_adapter.py: any API's answer in, one envelope out, with active payload detection (format, envelope, paging, types)
and drift handling (fields bound by path; added, missing, retyped and moved fields adapt; an unsure rename offered once,
never guessed). Plan: Plans/api-adapter.plan.md.
