# Craft review, 2026-11-22

The craft-review skill (.claude/skills/craft-review/SKILL.md, adapted from uncle-bob-craft) applied to the whole
repository by three read-only readers: the composition and services; the domain, adapters, client and sab_excel.py;
the extensions and the front end. Nothing was changed by the review. Their three reports follow in full after the
combined ranking.

## The combined ranking (risk reduced per effort)

| # | Refactor | Size | What it buys |
|---|---|---|---|
| 1 | Tests that tie the hand copies together: the dialect-name tables and alias lists, `sab_excel.cell_value` against `adapter.sheet_value`, the write-capability operations against the adapter's modes, the page's `canvasWiring.fits` against `widget_contract.fits`, the two page-of-a-file tables | small | The drifts become visible and stop growing; no behaviour change |
| 2 | One layers test for every extension (four have none) and fix its two breaches (Power BI imports the server; Copilot's service imports its adapter) | small | The layer rule enforced where nothing checks it |
| 3 | One "is this path inside the project?" rule (eight copies today, case and links handled differently) | small | Scaffold, outline, Environment and Connections stop disagreeing on Windows or through a link |
| 4 | One `allowed()` for the agent's Allow (31 hand-written call sites, 30 wordings) | small to medium | The golden rule's safety exception written once |
| 5 | A typed port for Actions onto the API explorer (it calls private methods); a public seam for the tests' fake runner (seven tests swap a private field) | small | The fastest-growing new service and ten tests stop depending on private names |
| 6 | The canvas `RUNTIME` (940 lines kept as a string) made a real file, as sab_perf.py is | small | Code every exported app runs becomes linted, typed, formatted |
| 7 | Move the save rules out of `adapters/blades.py`, and reconcile its two different "secrets follow a rename" behaviours (owner's call on which is right) | small to medium | One rule, one sentence; a latent keyring bug closed |
| 8 | Use cases out of `bootstrap.py` into their services, one closure at a time; check every late-bound attribute at the end of bootstrap(); then cap bootstrap.py and cli/commands.py at today's size | medium | The composition root reads as wiring again; the rules get tests at their own layer |
| 9 | Declare the seams extensions really use in hooks.py (about 30 base members read by name today, many through getattr(..., None)) | medium | A base rename becomes a type error instead of a feature quietly going dark |
| 10 | Split the hottest files along their own headings: the endpoint wizard out of LocalApi, the data door out of Sandbox, the command registry and watchers out of workbenchPage.ts (3,658 lines, 18 jobs) | medium | Each changes for one reason; fewer merge collisions |
| 11 | Serve the rules the page copies (connection-kind wording, the file page table, structure suffixes, a vault secret's variable name) from the backend | small to medium | The front end / back end rule applied; a first slice of the manifest boundary |
| 12 | One record per connection kind (today one kind is named in up to 16 domain files and a new kind touched 18 files plus 4 in web/) | large, in slices | A new kind becomes one entry plus its code module |
| 13 | Dead write helpers out of client/write_sql.py; adapter.py's ceiling made meaningful (owner's call); api_adapter's 11-argument chain into one internal record; errors.explain as a table of rules | small each | Less to read, less to mislead |

## What is in good shape

The dependency direction holds in substance, not only in imports: no file, clock, environment or network use in
the domain (checked on the syntax tree, not by text), no service I/O, thin routes, one place where an error becomes
an answer. adapter.py and api_adapter.py are readable for their size and the best-tested code reviewed. Patterns and
API targets are data with registries. The front end's shared pieces (error note, loading, file chooser, the IDE frame)
are really shared. Extension domains are clean.


---

# Craft review: the composition and the use cases

Read-only review, 2026-11-22. Area: `bootstrap.py`, `services/` (82 files, 31,674 lines), `services/hooks.py`,
`extensions.py`, `server/app.py`, `server/http.py`, and the shape of `cli/commands.py`. Nothing was edited. I
did not run the tests, ruff or mypy; every number below is from `wc`, `grep` or `git log` on this checkout.

## The short version

The layers hold. The trouble is in one place: `bootstrap.py` is no longer only wiring. It grew from 999 lines
(17 Nov) to 2,406 (22 Nov), is touched by 53 of the 214 non-merge commits to `src` since 19 Nov, and now holds
use cases and rules of its own. It is also the one large file the 1,500-line test does not cap, so it is where
code goes when a service is full. Most of the findings below are a consequence of that.

## 1. Boundaries

The dependency direction is sound.

- No service imports an adapter or the server. The only hit is a line of generated code inside a string
  (`services/actions.py:603`).
- No service reads or writes a file, the environment or the network directly; I searched for every common file
  call and found only port methods.
- The 61 route modules are thin (4,634 lines in all, the largest 373) and only 9 import a domain module.
- `server/app.py` builds no adapter; it asks `bootstrap()` and hands each route module its own service.

Two breaches the import test cannot see:

- **`bootstrap.py` holds use cases and rules** (finding 1).
- **`services/actions.py` reaches into another service's private parts** (finding 3).

## 2 and 3. Findings (design principles and smells together), ranked by risk reduced per effort

### 1. Use cases and rules live in the composition root — medium, the best buy

`bootstrap.py` has 33 nested functions and 52 top-level ones. Many are behaviour, not wiring:

- `bootstrap.py:2185` `used()`: which connections the open project uses (its documents, open tables and
  `API.py`). This decides what `connections.py` in the project scaffold contains.
- `bootstrap.py:1631` `_connections_named_in`: globs a project folder, reads every notebook and script, and
  applies the reference rule. That is file reading in the root, outside any adapter.
- `bootstrap.py:1663` `_shared_opened`: decides "only works on this machine" for a shared project and tells
  the pages.
- `bootstrap.py:952`: `if blade.kind in ("sql", "other") and mode in slot_rules.KINDS` decides which runs wait
  in a connection's line and which are counted.
- `bootstrap.py:1742` `sandbox_view_rows`: runs a grid query.
- `bootstrap.py:1841` `_open_work`: what an update would lose.
- `bootstrap.py:2096` `_publish_api`: writes the process environment.

Risk of change: changing "what counts as the project using a connection" means editing bootstrap, and the
same question is answered again by `_used_in` (`:601`), `_project_use` (`:1450`) and
`services/relationship_scope.py`. None of these closures has a test at its own layer: no test calls
`bootstrap()` directly, so they run only under whole-server tests.

Refactor: move each into the service that owns the question, as a method given ports. For example
`ProjectUse` in `services/project_scope.py` for the three "what the project uses" functions, and the slot gate
into `services/connection_slots.py`. One closure at a time, tests green after each. It buys back a root that
reads as a parts list, and rules that can be tested with fakes.

### 2. "Is this path inside the project?" is written at least eight times, differently — small

- `bootstrap.py:610`: case-folded, no real path.
- `bootstrap.py:2171`: real path, not case-folded.
- `services/project_outline.py:194`, `services/context_md.py:146`, `services/project_scope.py:162`,
  `services/api_export.py:125`: neither.
- `domain/script_ide.py:271` and `domain/code_tree.py:202`: two more copies.
- `domain/project_python.py:41` `in_project` already exists.

Risk of change: on Windows (a case-insensitive disk), or with a project reached through a link, the scaffold,
the outline, the Environment and the Connections page can disagree about whether a document is the project's.
A fix to one copy leaves seven.

Refactor: one domain function for the text rule, with the real path resolved by the caller's port, used
everywhere. An hour or two; it removes a class of "works here, not there" bugs.

### 3. `services/actions.py` uses the API explorer's private methods and is typed `Any` — small

`actions.py:107, 124, 158, 160, 315` call `self._explorer._apis()` and `._document()`; `:218` calls
`self._explorer._library.read()`. The constructor (`:68-80`) takes `explorer`, `local_api`, `hooks`,
`api_adapter` and `stats` all as `Any`.

Risk of change: this is the fourth fastest-changing service (9 commits in three days). A rename inside
`api_explorer.py` breaks Actions at run time, and mypy cannot see it. This is the only private reach across
services I found.

Refactor: a small `Protocol` in `actions.py` (`apis()`, `document(api)`, `read(file)`), and make those three
public on the explorer.

### 4. Half the wiring happens after construction, by setting attributes — medium

`bootstrap.py` has 49 assignments of the form `service.attribute = ...` after the service is built (for
example `:1220` `connections.approvals`, `:1586-1589`, `:1601-1605`, `:1811-1838`), 16 `listeners.append` or
`opened.append` calls, and 6 `b.has("...")` checks (`:1061, 1269-1286, 1321`).

Risk of change:

- A service's real dependencies are not in its constructor. `ConnectionService` has `variable_check` and
  `open_view` as `None` until two later parts run (`services/connections.py:55, 59`).
- Reordering the parts list (`bootstrap.py:873-891`) can silently leave one `None` or skip a `has()` branch.
  Nothing fails at start.
- A test that builds the service alone gets different behaviour from the app.

Some of this is unavoidable (true cycles: sandbox and local API, workbench and project Python). Refactor in
two steps:

1. Small: at the end of `bootstrap()`, check that every late-bound attribute is set, so a wrong order fails
   at start, not on a click.
2. Medium: where there is no real cycle, pass it in the constructor.

### 5. A new connection kind is edited into many files — large, do it a slice at a time

Measured on the commit that added lakes and SharePoint (`da15f90`): 18 existing Python files edited (6 domain,
4 services, 2 client, 2 adapters and server, the templates, the guides) plus 4 in `web/`, besides its own new
files.

Today `services/connections.py` has about 20 kind comparisons. The read path (`:415-479`, `:546-593`,
`:640-755`) branches on Power BI, lakes, Dataverse, SQL Server and Python by name. `dataverse` is named in 8
service files and `sqlserver` in 4. `ADAPTER_DIALECTS` (`connections.py:858`) is a second list of dialects
beside the adapter's own `DIALECTS`.

Risk of change: the next kind means finding every branch again, and a missed one shows as a wrong count or a
wrong origin name for that kind only.

The adapter work is already moving this the right way (dialects as data in `adapter.py`). Refactor: finish it
in the service. One per-kind record in `domain/connection_tables.py` (how it counts, how it reads, what its
origin is called, whether filters go to the source) that `ConnectionService` looks up instead of branching.
Start with the count and the origin name.

### 6. Five services each do several jobs, and two sit on the line cap — medium each

| File | Lines | Public methods | Jobs |
|---|---|---|---|
| `services/blades.py` | 1,489 | 83 | the store's facade, the IDE's save, running, analysis blades, the starter pack and snippets, import and export (eight marked sections) |
| `services/relationships.py` | 1,500 | — | four classes: Key Finder, Compares, Models, Finder |
| `services/sandbox.py` | 1,171 | 84 | the sandbox's tables and checkpoints, the API's data door and mock dialects, grid editing, the Connections card |
| `services/local_api.py` | 846 | — | hosting the API, and the endpoint wizard (plan, scaffold, paired) |
| `services/workbench.py` | 986 | 75 | files, kernels, the project session, window handoffs, HTML cells |

`blades.py` and `relationships.py` are at the 1,500 cap, so the next addition has to go somewhere else, and
the uncapped place is bootstrap. `sandbox.py` had 13 commits in three days and `local_api.py` had 18, the most
of any service.

Risk of change: a wizard change and a hosting change collide in one class, and the same for a Reset fix and a
mock-dialect fix.

Refactor, in this order:

1. The wizard out of `LocalApi` into its own class.
2. The API's data door out of `Sandbox`.
3. Analysis blades out of `BladeService`.

The one-file-per-feature rule allows two classes in a file, as `relationships.py` already does.

### 7. The "agent waits for the user's Allow" rule is written 31 times — small to medium

There are 31 `approvals.ask(...)` call sites in `services/`, each with its own `if who == "agent"` and its own
refusal sentence. Those are 30 different wordings, one without "(or did not answer)":
`"The user declined: the project's private switch was not changed."`. `who == "agent"` appears 65 times in 36
service files. The `Approvals` port is declared three times and passed as `Any` elsewhere (for example
`services/api_export.py:52`).

Risk of change: the golden rule's exceptions are a safety property, and each new action re-implements them by
hand. A forgotten `if` is an agent action with no Allow, and nothing structural catches it.

Refactor: one method on the approvals object, for example
`await approvals.allowed(who, subject, action, detail, otherwise="nothing changed")`, that raises `Refused`,
and one port in `services/ports.py`.

### 8. `Built` and `Services` are two records of the same things — small

`Built` (`bootstrap.py:732`, about 110 fields) and `Services` (`:217`, 91 fields) overlap, and `_services()`
(`:2290`) builds another 20 or so services inline while copying the rest.

Risk of change: a new service is named in six places in two files (its import, a `Built` field, its part, a
`Services` field, the `_services` argument, the route in `app.py`), plus `cli/commands.py` and
`tests/test_cli.py`. mypy catches a miss, so this is friction more than danger. But it is part of why
bootstrap is in a quarter of all commits.

Refactor: build the last 20 in a part like the others, and let `Services` be a typed view of `Built`.

### 9. `cli/commands.py` is one 5,619-line file — small, mechanical

It holds 390 functions in one registry and is touched by 49 of 214 commits. Each command is a thin call to a
route, which is right. The `Registrar` (`commands.py:86`) already lets an extension keep its commands in its
own file.

Risk of change: every feature branch edits the same file (there were 51 merges in three days), and nobody
reads it whole.

Refactor: the same registrar, one module per area prefix (`cli/commands_tables.py`, `..._connections.py`),
imported by `commands.py`. It needs a word on the depth rule; `cli/` is already a folder, so it fits.

### 10. `audit_log` means two things — small

The flag is tested 21 times in `bootstrap.py` as "may this server write state files at all" (`library.json`,
`follow.json`, `rail.json`, the one-time migrations at `:1537`).

Risk of change: a reader cannot tell why turning the audit log off stops the library migration, and a new
state file's author has to know to copy the idiom.

Refactor: rename it to what it is (for example `persist`) and add one helper, `b.state_file("rail.json")`,
that returns `None` when off.

### 11. Extensions get the whole `Services` record, and a few bypass `hooks.py` — small

`extension.routes(ctx)` hands over everything; extensions read about 45 different attributes. Most late
binding goes through `hooks.py`, which is small (80 lines) and well described. Three places do not:

- `extensions/powerbi/.../extension.py:195` sets `services.app_registrations.query_hints`.
- `extensions/powerapps/.../extension.py:161` sets `services.projects.opened`.
- `extensions/git/.../extension.py:142` appends to `services.sab_projects.opened`.

Extensions also store their own services on the base's record (`services.widgets = ...`, 14 such lines).

Risk of change: renaming a base service's attribute breaks an extension at start, with no type check.

Refactor: add those three to `Hooks`, and give extensions a place of their own on the record
(`services.extension["streamlit"]`).

### 12. An extension's manifest is 18 module attributes read with `getattr` in four files — small

`ID`, `MODE`, `AREAS`, `RAIL`, `PANEL`, `PAGE_ACTIONS`, `API_PATTERNS`, `API_TARGETS`, `SECRET_PATHS` and
others are read in `extensions.py`, `bootstrap.py`, `server/app.py` and `cli/commands.py`.

Risk of change: a misspelt attribute in an extension is silently "not there".

Refactor: one `Protocol` or dataclass in `extensions.py` listing every name once, and one function that reads
a module into it and reports unknown upper-case names.

## 4. The refactors worth doing, in order

| # | What | Size | What it buys |
|---|---|---|---|
| 2 | One "inside the project" rule | small | Removes eight drifting copies; fixes case and link disagreements |
| 3 | A port for Actions onto the API explorer | small | The fastest-growing new service stops depending on private names |
| 1 | Use cases out of bootstrap, one closure at a time | medium | The root reads as wiring again; the rules get fake-based tests; "what the project uses" is one answer |
| 7 | One `allowed()` for the agent's Allow | small to medium | The safety rule is written once; one sentence shape |
| 4a | Check late-bound attributes at the end of `bootstrap()` | small | A wrong part order fails at start |
| 6 | Split the wizard from `LocalApi`, the data door from `Sandbox` | medium | The two hottest services each change for one reason; room under the cap |
| 9 | `commands.py` by area | small | Fewer merge collisions |
| 10 | `audit_log` renamed, a `state_file` helper | small | Clarity |
| 5 | Connection kinds as one per-kind record | large, in slices | A new kind stops being an 18-file edit |
| 8, 11, 12 | The two records; hooks; the manifest type | small each | Less friction, typed extension seams |

Add `bootstrap.py` and `cli/commands.py` to the line-cap test once 1 and 9 are under way, with today's size
as the ceiling, so they only shrink.

## 5. Tests

- `tests/test_architecture.py` (9 tests) covers the import directions, the depth, who may name an adapter,
  and the 1,500-line cap for `domain`, `services`, `adapters` and `server`. It does not cap `bootstrap.py` or
  `cli/commands.py`, and it cannot see attribute wiring or private reach.
- `tests/test_service_layer.py` has 5 tests on fakes. 24 of the 270 test files import a service directly;
  most behaviour is covered through the HTTP door.
- Risk left: the logic inside bootstrap (finding 1) and the late wiring (finding 4) are exercised only when a
  whole server is built.

## What is in good shape

- The layer rule is kept, in substance and not just in imports: services do no I/O of their own, routes do
  not hold rules, and the HTTP door has one place where an error becomes an answer (`server/http.py`, 315
  lines, clear).
- `server/app.py` (501 lines) is readable: one list of routes, one lifespan, the extensions mounted from
  data.
- A new feature lands cleanly. The call statistics commit (`f6b3a24`) added its own four files and touched
  only the three composition files plus the services that report to it.
- API patterns and targets are data with a registry an extension can add to; a new pattern is a new entry,
  not a chain.
- `hooks.py` is the right size and is documented entry by entry.
- The `Built` record and the parts list (`bootstrap.py:873-891`) were a real improvement. The order of
  construction is now one readable list; what remains is to empty the parts of behaviour.

---

# Craft review: domain/, adapters/, client/, sab_excel.py

Read-only review, 2026-11-22. Nothing was edited. Method: `.claude/skills/craft-review/SKILL.md`, in its order.
Paths are under `src/swissarmybench/`.

## What was measured

| area | files | lines | notes |
|---|---|---|---|
| domain/ | 119 | 58,408 | 3,844 functions across the three folders; 70 over 60 lines, 18 over 100 |
| adapters/ | 43 | 15,380 | adapter.py 4,434 (ceiling 4,450), api_adapter.py 2,097 (ceiling 3,000) |
| client/ | 24 | 6,985 | write_sql.py 991, sql_cell.py 919 |
| sab_excel.py | 1 | 1,637 | |

Files at the 1,500-line ceiling the architecture test sets: `domain/script_export.py` 1,500, `domain/blades.py`
1,499, `domain/sql_server.py` 1,440, `domain/api_clients.py` 1,396.

Most changed since 2026-11-19 (commits touching the file): adapter.py 29 (28 of them on 2026-11-22),
domain/local_api.py 14, adapters/sandbox.py 11, domain/sab_files.py 10, domain/api_targets.py 10,
domain/sandbox.py 9, domain/navigation.py 8, domain/api_scaffold.py 8.

## 1. Boundaries

The dependency direction holds, and it holds beyond what the test can see. I walked every domain file's syntax
tree (so text inside strings is ignored) looking for real calls to open a file, read the clock, the environment,
the platform, a socket, a process or a random number: none. Time arrives as an argument (`parse_blade(..., now=)`).
The only oddities in real domain code are harmless: `domain/grids.py:21` holds a `threading.Lock` in a domain
record, and `domain/blades.py:560` opens a zip, but from bytes in memory.

Where it blurs, and should be said: about 4,900 lines of the domain are Python kept as text that does do I/O
when it runs somewhere else: `lake_code.py` (1,067 of its 1,104 lines are text), `api_clients.py` (908),
`sql_server.py` (851), `sharepoint.py` (811), `dataverse.py` (576), `script_runtime.py` (532), plus `entra.py`,
`keystores.py`, `certificate_files.py`. That is legitimate (the domain assembles a connection's code; it never
runs it), and the tests do run that text against stand-ins. But ruff, mypy and the import test see none of it,
and the adapter depends on it silently (finding 3).

`adapters/` imports only `services/ports.py` from the service layer (three files, for the `SqlSession` port):
correct. `client/` imports domain and adapters only inside functions so the plain client stays standard-library:
correct. One real breach is the other way round: business rules inside an adapter (finding 2).

## 2 and 3. Findings (SOLID breaches and smells together, most costly first)

**1. A connection kind has no single place where it declares itself (open/closed; rigidity; repetition).**
Counting files that name one kind: Dataverse is named in 14 domain files, 2 adapters, 2 client files and 8
services; SQL Server in 16 domain files; Trino in 12 domain files plus `client/write_sql.py` and `adapter.py`;
`sharepoint_docs` in 8 domain files. The per-kind tables I found, each keyed by the kind's word and each
maintained by hand:
- `domain/connection_tables.py:36` TABLE_KINDS, `:91` PATH_KINDS, `:92` VERSIONED, `:418` _FILTER_DIALECTS
- `domain/catalogs.py:29` DIALECTS and `:49` _DIALECT_ALIASES
- `domain/query_text.py:11` _SQLGLOT_DIALECTS
- `domain/sandbox_dialects.py:31` SQLGLOT, `:43` PARAMSTYLE, `:54` WORDS, `:72` its own alias list
- `domain/write_capability.py:59` WRITABLE, `:110` READ_ONLY
- `domain/portability.py:115` KINDS, `:149` SQL_SERVER_WAYS
- `domain/app_registrations.py:280` CHECKED_KINDS, `:294` AREAS, and six `if kind == ...` branch points (`:318`-`:407`)
- `domain/lakes.py:48` KINDS, `:51` LABELS, `:105` ENV_PREFIX
- `domain/context_md.py:149` repeats PATH_KINDS as a literal tuple
- `client/write_sql.py:113` ENGINES and `client/sql_cell.py:506` _SCANNED (by driver)
- `adapters/adapter.py:1072` DIALECTS and `:4133` _DRIVERS

The plainest case of the same rule written several times: "this dialect's name in sqlglot" exists as three full
tables (connection_tables, query_text, sandbox_dialects) and two inline ones (`api_pattern_code.py:479`,
`intellisense.py:830`), and "this word is another name for that dialect" as three (`catalogs.py:49`,
`sandbox_dialects.py:72`, `intellisense.py:830`). No test ties them, and they already disagree: `pg` is an
alias only in intellisense, `mariadb` only in catalogs and sandbox_dialects, `azuresql` and `redshift` only in
catalogs. Risk: adding one kind (say Databricks as a full SQL kind, already half present: it is in
`adapter.DIALECTS` but its starter says dialect "other", see `tests/test_adapter_boundary.py:191`) means editing
about ten files, and a missed one fails quietly (a filter not sent to the source, a query not formatted, the
sandbox refusing its SQL) rather than loudly. Only write_capability has a test that refuses an undecided kind
(`tables_kinds_covered`); that is the model to copy.

**2. `adapters/blades.py` decides business rules (boundary; single responsibility; repetition).**
`BladeStore` is 50 methods doing three jobs: the blades' files, pins and blade folders, and the keyring. Inside
its write paths it also decides rules that belong to the use case: "a starter is read-only" is written three
times with three different sentences (`:422`, `:471`, `:509`), "a blade with that name already exists" twice
(`:437`, `:517`), "a secret blade has no code" (`:474`), and "secrets follow a rename" twice with different
behaviour: `set_header` (`:445`) moves every secret, `save` (`:523`) moves only those the new blade still
names. Risk: the next rule about what may be saved (a team library's read-only items, say) gets added to one of
three paths; the two rename behaviours are already a latent bug, since a rename from the Properties panel and a
rename through Save leave different things in the keyring.

**3. The adapter recognises a connection's kind by which methods its client happens to have (fragility).**
`adapter.py:4169`: a client with `rows` and `catalog` is a lake or SharePoint; if it also has `described` it is
Dataverse. `adapter.py:2536`: a client with `write_delta` is a lake, one with `create` and `ids` is a
SharePoint list. Those method names live as text in `domain/dataverse.py:409`, `domain/lake_code.py` and
`domain/sharepoint.py`, in strings no tool checks, and nothing in either file says "the adapter depends on
this name". Risk: giving the SharePoint client a `described` method for some other feature silently turns it
into a Dataverse source. And because a connection's code is copied into each user's saved file, older saved
connections keep older method sets; `sql_server.py` has `is_old` / `upgraded` for that, the other kinds do not.
The current text is tested against stand-ins (`tests/test_adapter_odata.py`, `test_adapter_rows.py`), so today
it works; the risk is in the next change.

**4. The cell-value rule for a workbook is written twice and has already drifted (repetition).**
`sab_excel.py:138` `cell_value` and `adapters/adapter.py:3262` `sheet_value` both call themselves the one rule
(long whole numbers, dates before 1900-03-01 and zoned times as text, decimals as numbers, text never a
formula). They differ: sab_excel handles numpy scalars, pandas' missing time and writes lists as JSON by
`json.dumps`; the adapter's goes through `_as_text`. The constants are also separate (`EXACT_DIGITS` /
`EXCEL_DIGITS`, `FIRST_DAY` / `EXCEL_FIRST_DAY`). Two standalone files cannot import each other, so the copy is
justified, but no test holds them equal, unlike the SQL Server catalog query (`adapter.py:985` is byte for byte
`sql_server.py:1224`, and `tests/test_catalog_listing.py:135` proves it). Risk: the grid's Excel export and a
connection's write into a sheet store the same value differently.

**5. adapter.py's line ceiling is not acting as a limit (viscosity).**
`tests/test_architecture.py:262` allows 4,450 lines; the file is at 4,434. The comment above it records the
ceiling being raised ten times on 2026-11-22 alone (3,000 to 4,450). The one-file design is the owner's and is
right for an export; the issue is that every feature costs a ceiling edit, so the number tells nobody anything,
and the file now holds seven sources. Inside it the per-source write code is the bulk: SQL Server's write
(`_ServerWrite`, `:1810`, about 600 lines), Dataverse's (`_Dataverse`, `:2605`), the lakes'
(`_lake_written`, `:2948`, 56 lines, 26 branches), files and Excel (`:3013`-`:3593`). The file already has
numbered sections (`# ===== 2. Sources =====`), which is what makes it still readable. Risk: with 16 lines of
room, the next change either raises the ceiling an eleventh time or gets squeezed in the wrong shape.

**6. Three vocabularies for a write (repetition; opacity).**
The adapter's modes: insert, update, merge, delete, truncate (`adapter.py:129`). The Write starters' words:
append, create, replace, upsert, delete, mapped at `client/write_sql.py:821` ADAPTER_MODES. The capability
table's operations: append, create, replace, upsert, delete, update, optimize, vacuum
(`domain/write_capability.py:57`-`:105`). `WRITE_MODES` is held equal to the adapter by a test; `WRITABLE`'s
operations are held to nothing, and since every write became the adapter's they describe the old starters (the
Connections page can say "optimize, vacuum" for Delta while `sab.write` offers five modes and neither of
those). Risk: the page, the agent and `sab.write` tell the user three different lists for one connection.

**7. Leftovers in `client/write_sql.py` from before the writes moved to the adapter (needless complexity).**
`each_values` (`:591`) and `each_where` (`:602`) have no caller anywhere in src, extensions, tests or examples;
`each_batch`, `copy`, `transaction`, `where_keys` and `found` are reachable only from them or from each other,
and `tests/test_adapter_boundary.py:198` forbids starters from calling them. The module's opening example
(`:3`-`:12`) still teaches the old way (`with w.transaction(): w.each_batch(upsert)`). `ENGINES` (`:113`, about
230 lines: each database's quoting, types and drivers) now overlaps `adapter.DIALECTS` and `_DRIVERS`. Risk: a
reader fixes or extends the dead path; the file is 991 lines of which roughly a third is live.

**8. Four very large, heavily branched functions carry core behaviour (opacity).**
- `domain/table_cells.py:395` `arrange`: 242 lines, 115 branch points, closures over eight local dictionaries.
  It decides where every cell of a document goes; it is also in the top 30 most changed.
- `domain/blades.py:817` `_detect`: 192 lines, 76 branch points, nested helper functions that write into a
  shared dictionary. Every connection form depends on it.
- `domain/script_export.py:755` `plan`: 191 lines, 66 branch points, 7 arguments.
- `domain/errors.py:99` `explain`: 183 lines, 64 branch points: one long chain of "if the error looks like".
All four are well tested from outside (table_cells has 36 tests in two files, blades is imported by 32 test
files), which is why they are safe today. Risk: a change inside means holding the whole function in the head;
`explain` in particular is a list of rules that wants to be a table (a new error type added as an entry, not as
another branch).

**9. `domain/blades.py` and `domain/script_export.py` are at the ceiling and have several jobs (single
responsibility).** blades.py holds seven marked sections: reading code, the portable file's format, writing it,
reading it, zips, settings detection (430 lines), writing a value back, and the Blade record with its parser. 49
places import it. It has already shed `blade_templates`, `packages`, `blade_suggestions`, `blade_tables` and
`blade_header`, re-exporting some. Risk: at 1,499 of 1,500 lines the next blade feature forces a split in a
hurry; the settings part (`:600`-`:1170`) has its own reason to change (the connection forms) and is the
natural one to move.

**10. `domain/connection_tables.py` has two jobs (single responsibility).** Lines 36-290: what a connection is
(the kinds' contract, names resolved). Lines 288-690: SQL text work with sqlglot (finding `[Conn].table`
references, rewriting them, deciding which filters and limit can be sent to the source; `pushdown` at `:529` is
72 lines with 49 branch points). The second half changes when DuckDB SQL handling changes, the first when a
kind is added. It also imports `dataverse`, `lakes`, `powerbi` and `web_calls`, so `write_capability` (which
imports it for TABLE_KINDS) drags all four. Risk: modest; it mostly makes finding 1 harder to fix.

**11. `api_adapter.py`'s call path passes 10 to 12 arguments through five functions (opacity).**
`run` (`:1503`, 11 arguments), `_call` (`:1587`, 89 lines, 11), `_single_envelope` (`:1708`, 12),
`_records_envelope` (`:1678`, 11), `_envelope` (`:1757`, 10). The same bundle (action, inputs, the request, the
timings, the known shape) travels the whole way. Risk: each new fact for the statistics or drift check adds a
parameter to five signatures. Internal only; the public contract need not change.

**12. Small things worth saying.** `sab_excel.py:1008` `build_statements` is 147 lines with 13 arguments and
does planning, naming, numbering, writing and the register in one body. `adapters/sandbox.py` also holds
`ExportFolder` (`:564`) and `LocalApiFiles` (`:605`), which are not the sandbox. CLAUDE.md's layout entry for
`adapter.py` and `api_adapter.py` is interleaved (the adapter's text continues inside the api_adapter entry and
says both "Allowed 3,000 lines" and "Allowed 4,450"), and `client/kernel_variables.py` is not in the layout.

## 4. The refactors worth doing, ranked by risk reduced per effort

1. **Tie the copies together with tests (small; an hour or two; no behaviour change).** One test that every
   key of `catalogs.DIALECTS` that speaks SQL has an entry in the sqlglot-name tables and that the tables agree
   where they overlap; one that runs a list of sample values through `sab_excel.cell_value` and
   `adapter.sheet_value` and asserts the same answers; one that every operation in `write_capability.WRITABLE`
   maps to an adapter mode or is listed as a starter-only extra. Buys: findings 1, 4 and 6 stop drifting today,
   and the tests will show the existing differences so each can be decided.
2. **One function for a dialect's sqlglot name and its other names (small).** Put `sqlglot_name(dialect)` and
   the alias table in `domain/catalogs.py` (it already owns DIALECTS and aliases) and have connection_tables,
   query_text, sandbox_dialects, api_pattern_code and intellisense call it. Removes five copies. Risk: the
   three tables differ on the lake kinds ("structured" in one, "duckdb" in another, absent in the third), so
   each caller keeps its own small exception; the test from step 1 pins that first.
3. **Delete the dead write helpers and rewrite the module's opening example (small).** In
   `client/write_sql.py`: `each_values`, `each_where`, then whatever only they reached. Buys about 60 lines and
   a module whose first page describes how it works now. Risk: a user's own copied starter might call them;
   `GONE_METHODS` (`:983`) already exists to answer such a call in one line, so add them there.
4. **Move the save rules out of `BladeStore` (small to medium).** A pure function in `domain/blades.py`
   (or `blade_tables.py`), something like `may_change(blade, what) -> None or BladeError`, holding "starter is
   read-only", "secret blade has no code", "name taken", and one `secrets_after_rename(old, new)`; the store
   calls it from its three paths. Later, split the keyring half of the store into its own small class in the
   same file. Buys: one sentence, one rename behaviour, and the rules testable without files. Risk: the two
   rename behaviours must be reconciled; that is a decision for the owner (which is right?).
5. **Let a connection's client say what it is (small; additive to adapter.py, so its own commit).** Add a
   class attribute to the generated classes in the text (`sab_source = "odata"`, `"rows"`, `"list"`), have
   `source_from` and `Rows.write` read it first and fall back to today's method sniffing for saved older
   connections. Write the expected method names once, as a comment block or a `Protocol` per source beside
   `Source` (`adapter.py:454`). Buys: finding 3; nothing breaks, the contract only grows.
6. **One record per connection kind (medium to large; do after 1 and 2).** A `domain/connection_kinds.py` with
   one frozen record per kind: its words for list and read, whether its tables are paths, whether it has
   versions, its sqlglot name, its write capability, its Entra scope and area, its label and group. The
   existing tables become views derived from it (keep their names so callers do not change), and a test
   refuses a kind with a missing field. Buys: a new kind is one entry plus its code module; finding 10's split
   falls out of it. Risk: touches about ten domain files and the lazy imports in `app_registrations.py:393`
   show there are import cycles to untangle; do it one table at a time, tests green after each.
7. **adapter.py: stop raising the ceiling by hand (small, the owner's call).** Either drop the ceiling for the
   two one-file modules and instead cap each numbered section or each function (say 80 lines; today only
   `dialect_sql`, 60 lines and 30 branches, is near), or keep one generous ceiling and stop recording each
   step. An export must stay one file, but the repository's copy could be built from parts (one per source)
   by `build.py` with a test that the built file equals the committed one; that is a medium change and only
   worth it if the file keeps growing at this week's rate.
8. **Turn `errors.explain` into a table of rules; extract `arrange`'s phases (medium each).** For `explain`:
   a list of (matches, explain) pairs tried in order. For `arrange`: name the phases it already has in comments
   (number the cells, find each table's maker, decide what blocks a move, lay out) as functions over one small
   record instead of eight closures. Buys: finding 8 for the two that change most. Risk: both are behaviour
   the tests pin tightly, which makes this safe but slow; do it only when next changing them.
9. **Move settings detection out of blades.py (small to medium).** `domain/blade_settings.py` taking
   `:600`-`:1170`, re-exported from blades.py as the earlier splits were. Buys 570 lines of room under the
   ceiling and one reason to change per file.
10. **A request record inside `api_adapter.py` (small, internal).** One private dataclass carrying what
    `run` hands down, so `_call` and the three envelope functions take two or three arguments. No public change.

## 5. Tests

What covers it: the adapters are the best-tested part reviewed. adapter.py has 18 test files (about 140
tests) against DuckDB, SQL stand-ins, a SQL Server stand-in, Trino, OData, the lakes, files and Excel;
api_adapter.py has 29 tests; the code-as-text modules are executed against stand-ins (`test_sql_server.py`,
`test_lakes.py`, `test_dataverse.py`, `driver_check.py` checks each starter's calls against its installed
driver). Copies that must stay equal are mostly held by tests: the catalog listings
(`test_catalog_listing.py:135`), the write modes (`test_sab_write.py:171`), the kinds' write decision
(`test_starters_write.py:217`).

What does not: nothing ties the sqlglot-name tables or the alias lists; nothing ties `cell_value` to
`sheet_value`; `WRITABLE`'s operations are tied to nothing; `query_text.py` has one test file;
`analysis_cards.py` (1,382 lines, five functions over 100 lines) has one; the two rename paths in `BladeStore`
are not tested against each other; the text modules are run but never linted or type-checked (a test that
compiles each assembled connection's code and runs pyflakes over it would be cheap). Risk left: the drift
described in findings 1, 4 and 6, which would show up as a wrong answer on one kind rather than a failing test.

## What is in good shape

- The domain is clean: no file, clock, environment or network use in real code across 119 files; time and
  the environment come in as arguments.
- Import directions are right in all three folders, and the plain client stays standard-library by importing
  the adapter only when a write or a workbook read actually runs.
- adapter.py and api_adapter.py are readable for their size: numbered sections, a change list at the top, no
  function over 60 lines in adapter.py, dialects as data (`Dialect`, `DIALECTS`) rather than branches.
- Where a copy is forced by the one-file rule, the habit of pinning it with a test already exists; findings
  1, 4 and 6 are the places that habit has not reached yet.
- `domain/write_capability.py` is the pattern for finding 1: a table per kind plus a test that refuses a kind
  nobody decided.
- `adapters/atomic_files.py` is one small shared way to write a file, and the other adapters use it.

---

# Craft review: the extensions and the front end (web/src)

Read-only review, 2026-11-22. Nothing was edited. Scope: `extensions/*` (Streamlit most of all) and
`web/src/*.ts`. Not run: the tests, ruff, mypy, the type check (the skill says they are separate). The base's own
Python was read only where an extension touches it.

Measured: web/src is 172 files, 59,408 lines; the six extensions' Python is 37,088 lines. Since 2026-11-19: 116
commits touched web/src, 74 touched extensions. Most changed: workbenchPage.ts (31 commits, +1,001 / -885 lines),
services/canvas.py and extension.py of Streamlit (17 each), connectionsWindow.ts (16), canvas_build.py (14 commits,
+1,831 lines), canvasPage.ts (11 commits, +1,638 lines: almost the whole file is three days old).

## 1. Boundaries

The direction is right nearly everywhere. No extension domain module imports a service, an adapter or the server;
no extension reads a private (`_name`) attribute of a base service; the front end's extension-only pages are their
own files (7,690 lines in 19 files) and only four shared files call an extension's address directly. The breaches:

- **Extensions wire themselves into the base past hooks.py.** `services/hooks.py` names eight seams, but the
  extensions' composition roots also read about thirty base service members by name and write onto base objects:
  - `extensions/streamlit/.../extension.py:260` sets `local_api.api_uses = ...`; `:306` appends to
    `services.ws.live.listeners` (found by a double `getattr`); `:280` takes `services.local_api.paired`;
    `:128-279` has ten `getattr(services, "<name>", None)` lookups (library, sab_projects, variables,
    connection_tables, local_api, actions, scaffold).
  - `extensions/git/.../extension.py:141-142` appends to `services.sab_projects.saved` and `.opened`; it also calls
    `project_explorer.set_folder`, `library.set_folder`, `shared_catalog.refresh`.
  - Power BI reads `datasets.origins.get`, `connections.blade`, `app_registrations.query_hints`,
    `project_tables.used`; Power Apps reads `connections.open_table`, `connection_tables.prepare`,
    `api_explorer.document_of`.
  Risk: renaming or reshaping any of these base members breaks an extension with no type error (everything is
  `Any` or `getattr`, so mypy cannot see it) and, for the `getattr(..., None)` ones, with no error at all: the
  feature just goes quiet (a widget's endpoint picker empty, Play no longer following live data).
- **Two layer breaches inside extensions that no test catches:**
  `extensions/powerbi/.../services/project.py:264` imports `swissarmybench.server.blade_templates`;
  `extensions/copilot/.../services/copilot.py:36` imports its own adapter (`adapters.language_server`). Only
  Streamlit (`tests/test_streamlit_extension.py:89`) and Power Apps (`tests/test_powerapps_rules.py:395`) have a
  layers test; Power BI, Git, Copilot and Accounting have none, and `tests/test_architecture.py` looks only at
  `src/swissarmybench`.
- **The front end decides things the backend also decides** (findings 3 and 4 below).
- **The Streamlit domain does no I/O itself.** The `os`, `tempfile`, `pandas`, `streamlit` imports that a search
  finds in `domain/canvas_build.py` are all inside the `RUNTIME` text (finding 5), not run by the app.

## 2. SOLID, where it bites

- **Single responsibility: `web/src/workbenchPage.ts` (3,658 lines, 138 top-level functions, 66 imports, 24
  module-level variables, 13 route families).** Its own section headings name eighteen jobs: documents, the tables'
  cells, projects and New entries, the modes, lineage, a structure's tab, a library's read-only source, a code
  app's files, files, the file-changed watcher, the three bars, the Data Explorer, zoom, full screen, restore, the
  rail, start, and a 770-line command registry (line 2889 on). Every Workbench feature is a reason to edit it; that
  is why it has 31 commits in three days.
- **Single responsibility: one function is the whole feature** in `workbenchNotebook.ts` (`notebookView`, 1,816
  lines, 81 inner functions, 17 `let`s), `workbenchScript.ts` (`scriptView`, 792), `environmentPage.ts`
  (`mountEnvironment`, 770) and `structureDoc.ts` (`mountStructureDoc`, 558). Nothing inside can be tested or
  reused without the whole closure; any inner function can change any of the shared variables.
- **Single responsibility: `canvasPage.ts` (1,509 lines, 62 functions, 16 module-level variables)** holds the
  frame, the server calls, the page tabs, the bottom bar, the board, selecting/moving/sizing, the menus, the
  Widgets pane, the Properties pane, Play/Launch/Export and the landing list.
- **Single responsibility: the Streamlit composition root holds rules.** `extension.py:226-258` (`api_uses`) reads
  every `*.canvas.json` from disk and walks widgets, values and wires; `:316-334` (`canvas_put`) sequences three
  canvas commands. These are a use case and a canvas rule living in the wiring file, untested except through it.
- **Interface segregation / dependency inversion: `services/widgets.py` `Widgets`** takes 16 constructor arguments
  (12 of them loose callables) and five more are set on it afterwards (`excel_files`, `endpoints`,
  `endpoint_fields`, `api_files`, `renamed`); `Canvases` takes 13 and gets `launches` and `paired` set later. All
  typed `Any` or bare `Callable`. A forgotten late assignment is a silent default, not an error.
- **Open/closed: connection kinds are named in the page.** `connectionsWindow.ts:113-115` (`LAKE_KINDS`,
  `readsByCode`), `:408-410` (the "how to use it" line chosen per dialect), `:775-778`, `:1202`;
  `connectionTree.ts:162-188`, `queryTab.ts:94-95`, `dataBrowse.ts:219` (`tables_kind === "powerbi"`). A new
  connection kind means editing four front-end files as well as the backend.

## 3. Smells, each with its place and cost

1. **Needless repetition, backend rule copied into the page (will drift):**
   - `web/src/canvasWiring.ts:64-71` `fits()` is a hand copy of
     `extensions/streamlit/.../domain/widget_contract.py:317` `fits()`; `canvasWiring.ts:194-204` also decides
     which sources each port type may take, which `domain/canvas_wiring.py` checks again on the server. A new port
     type or conversion must be added twice; when they differ the picker offers a wire the server then refuses.
   - `web/src/workbenchPages.ts:31-50` (`pageOfPath`, `pageOfKind`, `wrongPage` and its sentence) repeats
     `src/swissarmybench/domain/workbench_pages.py:27-74` word for word (the file's own comment says so).
   - The structure file suffixes are listed in `structurePaths.ts:49-50`, `workbenchPage.ts:1648`,
     `structuresPage.ts:156` and in `domain/workbench_pages.py` (`STRUCTURE_SUFFIXES`, `_NOT_STRUCTURES`).
   - `connectionsWindow.ts:446-451` `envFor` re-implements `domain/blades.py env_name_for_secret` (a vault
     secret's variable name); the comment names the Python it copies.
2. **Opacity: a 940-line program kept as a string.** `domain/canvas_build.py:585-1521` is `RUNTIME`, the canvas
   runtime every built and exported app carries (viewer sign-in claims, API calls, wiring, Parquet reads). As text
   it is invisible to ruff, mypy and the formatter; tests reach it by `exec` and by string search
   (`tests/test_canvas_gaps.py:324-325, 538`, `tests/test_play_live.py:65`). It grew most of the file's +1,831
   lines in three days. The repository already has the better pattern: `server/sab_perf.py` and `sab_excel.py` are
   real files that are copied or inlined.
3. **Needless repetition in the front end:**
   - Page tabs, undo/redo and the resize grip exist in `canvasKit.ts` ("what the canvases share") but only
     `excelCanvas.ts` imports it; `canvasPage.ts:330-355` draws its own tabs and keeps its own history.
   - Nine hand-written drag-to-resize handlers (`sidePanes.ts:75`, `codeIde.ts:265`, `workbenchLayout.ts:113`,
     `workbenchExplorer.ts:178`, `scmPage.ts:351`, `workbenchHtml.ts:276`, `workbenchGroups.ts:336`,
     `canvasKit.ts:139`, `aiPanel.ts`).
   - Five menu implementations: `dom.ts:506 showMenu` (17 files), `workbenchMenu.ts:39 openMenu` (5),
     `workbenchAgent.ts:93 contextMenu` (2), `canvasPage.ts:886 menu`, `scmPage.ts:135 menu`.
   - 32 uses of the browser's own `prompt()` / `confirm()` (for example `canvasPage.ts:342, 1459`,
     `connectionsWindow.ts:791`, `codeAppPage.ts:321`) beside the app's own dialog (`dom.ts:394 openDialog`): two
     looks for the same question, and the built-in ones cannot be styled or driven by the agent.
4. **Rigidity: remnants of removed things.** `.stapp.json` (app notebooks went 2026-11-21) is still handled in
   `workbenchPages.ts:34`, `structurePaths.ts:50`, `projectImport.ts:38`, `sessionPage.ts:251`,
   `workbenchLanding.ts:84`; the kind "app" and the words "A Streamlit app" are in the shared
   `workbenchPages.ts:45` (an extension named in shared front-end code).
5. **Fragility in the tests' seam.** Seven test files replace a private field,
   `client.app.state.ctx.live_runs._runner = FakeRunner()` (`tests/test_canvas_routes.py:31`,
   `test_widgets_routes.py:26`, `test_canvas_launch.py:244`, `test_canvas_gaps.py:336`, `test_play_live.py:107`,
   `test_api_widget_paths.py:86`, `test_widget_connection_tables.py:79`); `test_canvas_launch.py:358, 382` reads
   `launches._running`; `test_scm.py:60` clears `git._remote`; `test_powerapps.py:384` sets
   `powerapps._api_documents`. Renaming one private field breaks seven files.
6. **Viscosity: the front end has no unit-test habit and no formatter.** `web/package.json` has only `build` and
   `typecheck`. Two pure modules are tested through Node (`tests/test_canvas_snap.py`,
   `tests/test_structure_paths.py`); everything else is reachable only by a browser test. 625 lines are longer
   than 200 characters and 95 longer than 300 (the longest 530, `connectionsWindow.ts`), which makes diffs and
   reviews of these files hard to read. So the easy path for the next rule is to write it inline in a page file.

## 4. The refactors worth doing, ranked by risk reduced per effort

| # | Refactor | Size | What it buys |
|---|----------|------|--------------|
| 1 | **One layers test for every extension.** Lift `test_the_package_keeps_the_layers` into a parametrised test over all six packages (Accounting's flat layout declared as such), then fix the two breaches it finds (Power BI `services/project.py:264`: hand `BY_ID` in from its root; Copilot `services/copilot.py:36`: move the three names behind a port). | small | The rule CLAUDE.md states for extensions becomes enforced for four packages that have nothing today. |
| 2 | **Serve the rules the page copies.** Put `fits` and each port type's allowed sources into the canvas state the server already sends; let `/app/mode` (or the page's first answer) carry the structure suffixes, the page-of-a-file table and the wrong-page sentence; ask the server for a vault secret's variable name. Delete `canvasWiring.fits`, the three suffix lists, `envFor`, and the `.stapp.json` remnants. | small to medium | Removes five places where a backend change silently disagrees with the page; it is the front end / back end rule applied. |
| 3 | **Make `RUNTIME` a real file** (`server/sab_canvas.py`, read as text by the builder the way `sab_perf.py` is copied), and import it in tests instead of `exec` and string search. | small | 940 lines of code every exported app runs become linted, typed and formatted. `canvas_build.py` drops to about 580 lines of actual building. |
| 4 | **Declare the seams the extensions already use in hooks.py** (project opened/saved listeners, a live-notice listener, `api_uses`, the open project's folder, variable names, connection table listing and read) as typed fields, and have the extensions use only those. Move `api_uses` and `canvas_put` out of `extension.py` into the Streamlit services (the canvas walk into `domain/canvas_wiring.py`, the file read behind `CanvasFiles`). | medium | A base rename becomes a type error instead of a feature going quiet; the root becomes wiring only. Give `Widgets` and `Canvases` one small typed port each (a `Project` port, a `Tables` port, an `Apis` port) in place of 16 loose callables and seven late assignments. |
| 5 | **Split workbenchPage.ts along its own headings.** First the pieces with no shared state: the command registry (line 2889 on, about 770 lines), the file-changed watcher (1694-1880), zoom and full screen (2458-2683), restore (2684-2791). | medium, in small steps | The file with the most churn in the repository loses about 1,400 lines without changing behaviour; later changes touch a 200-line module instead. |
| 6 | **Connection kinds as data in the page.** Have the connections listing answer what the page now works out per dialect: `reads_by_code`, the "how to use it" line, which detail actions exist (Import relationships, the Dataverse switch), the sign-in legend. | medium | A new connection kind stops needing edits in `connectionsWindow.ts`, `connectionTree.ts`, `queryTab.ts` and `dataBrowse.ts`. It is the first slice of the manifest boundary the project plans. |
| 7 | **One drag-resize helper and one menu.** Give `dom.ts` a single `dragResize(handle, {axis, onMove, onEnd})` and move the nine handlers onto it; fold `canvasPage.menu` and `workbenchAgent.contextMenu` into `showMenu` (scmPage's is a deliberate VS Code copy: leave it). Have `canvasPage.ts` use `canvasKit.pageTabs` and `history`, or delete the claim that they are shared. Replace `prompt()`/`confirm()` with one `askText` / `askYesNo` on `openDialog`. | medium | One behaviour for pointer capture, keyboard and focus; the agent and the desktop app see one kind of question. |
| 8 | **Break up the four giant closures**, starting with `notebookView`: pull out what needs no closure state (cell drawing, the Tables group, the DAX and SQL cell heads) into functions that take a small state record. | large | Makes the notebook testable in parts. Worth doing only after 5; the risk of regressions is real and only browser tests cover it. |
| 9 | **A public seam for the test runner.** `LiveRuns.use_runner(runner)` (or a stand-in named by an environment variable, as `SWISSARMYBENCH_DEVTUNNEL_STANDIN` does), and the same for `git._remote` and `powerapps._api_documents`. | small | Ten test files stop depending on private field names. |

## 5. Tests

- Covered well: the Streamlit extension has 24 test files (domain rules as pure tests, routes over a real app,
  every prebuilt widget run headless), Power BI 12, Power Apps 6, Git 5, Accounting 4, Copilot 3, each with a
  stand-in for the outside service. 114 browser test files.
- Not covered: layering in four of six extensions (refactor 1); the copied rules agreeing with their Python
  originals (no test compares `canvasWiring.fits` with `widget_contract.fits`, or the two page-of-a-file tables);
  the front end's pure logic outside two modules; the `RUNTIME` text beyond `exec` and string matching.
- Risk left: workbenchPage.ts and canvasPage.ts change daily and are protected only by browser tests (10 files
  for the Workbench, 6 for canvas and widgets).

## In good shape

- **Extension domains are clean**: no file, clock or network use in any `domain/` module of any extension; Git's
  domain imports only seven standard-library modules.
- **Extensions never read a base service's private state**; where a hook exists (`team`, `dataset_aliases`,
  `share_targets`, `canvas_put`, `app_pages`, `project_app`) it is used.
- **The front end's shared pieces are really shared**: `errorNote.ts` has 101 importers, `loading.ts` 52,
  `fileChooser.ts` 20, `missingPackages.ts` 15; only six `toast()` calls carry error-like words. `codeIde.ts` is
  the one IDE frame for the blade screen, the Widgets window and a structure's tab.
- **The "host" interface pattern** (26 `…Host` / `…Options` interfaces) keeps most panels independent of the page
  that mounts them; it is the right tool for refactors 5 and 8.
- **Extension-only front-end code is contained** in its own files; the Power BI panel, extension cards, rail areas
  and page actions are drawn from backend data, generically.
- **The extensions' tests go through the routes** with stand-ins rather than mocks of the base, apart from the
  private-field swaps in finding 5.
