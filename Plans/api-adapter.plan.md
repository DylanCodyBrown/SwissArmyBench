# The API adapter: any payload in, one shape out (the owner, 2026-11-22)

Status: built (branch api-adapter, 2026-11-22: steps 1 to 6 below; what is left under "Not yet"). Cared for as design principle 12b (equal to adapter.py). Comes after the data adapter's phase 3 (it hands table-shaped answers to it).

> "How do we handle API actions. They don't have to go through the adapter but I feel like they need their own to
> standardize outputs. Kinda like how Power Automate online standardizes" / "api_adapter.py and we should think more
> universal input. Like a dynamic adapter that can literally take any input, determine what it is, and shape its output
> for our widgets and app. Like active payload detection. So even if their returned payload changes we don't have to
> change code, it adapts."

## Two adapters, one each
- `adapter.py`: tables (read, query, write) from connections. Unchanged.
- `api_adapter.py`: actions (calls to any API that do something or answer something). Standard library only, copied
  into exports like adapter.py. Where an answer is table-shaped it hands it to adapter as a table: the one
  crossing point.

## One call, one envelope
`run(action, inputs)` (an action: an OpenAPI operation Add API already read, a web call blade, a local sandbox API
endpoint, an extension's or blade's own) answers, for every API:

| Field | What it holds |
|---|---|
| `ok`, `status` | did it work; the HTTP status (or the action's own) |
| `kind` | what the answer is: `records`, `record`, `value`, `file`, `empty`, `text` |
| `records` / `record` / `value` / `file` | the answer in that shape (records also as a table through adapter) |
| `paging` | more pages and how they were followed (or stopped) |
| `shape` | the answer's fingerprint and any drift from the last time (below) |
| `raw` | the answer as it came, for the viewer and the agent |
| `error` | the app's one refusal shape: what happened, where, the fixes |

Inputs are checked first (a missing or wrong field refused, naming it); sign-in from the connection; retries on
throttling (429, Retry-After) and passing errors; all the same for every API.

## Active payload detection
The answer's shape is found, not configured (building on domain/web_calls.py's common shapes and domain/structures.py):
- **Format:** JSON, JSON lines, XML (no DOCTYPE or entity), CSV or TSV text, YAML, a file (by content type and first
  bytes), plain text.
- **Envelope:** the records found wherever they sit: a top-level list; `value`, `data`, `items`, `results`, `records`,
  `rows` and the like; a header-and-rows pair; a single object (a record); a scalar (a value).
- **Paging:** `@odata.nextLink`, `next`/`links.next`, a `Link` header, a cursor or token field, offset and limit, page
  numbers; followed to the end within the call's limit, said in `paging`.
- **Types:** each field's type read from its values (dates, numbers in text, booleans), nested objects flattened by
  path for a table (`customer.id`) and kept whole in `record`.

## When the payload changes, the code does not
Consumers bind to **field paths** (`customer.id`, `amount`), never positions, and the adapter remembers each action's
last **shape fingerprint** (paths and types). On every answer:
- **A field added:** it appears (a new column, a new path to pick). Nothing breaks.
- **A field missing:** its value is empty (null); bindings to it keep working and are marked.
- **A type changed** (a number arriving as text, a date in another format): coerced to the known type where it reads
  cleanly, else kept as text, and marked.
- **The envelope changed** (records moved under `data`, one page became paged): found again by detection; consumers
  see the same records.
- **Matching is forgiving:** paths match in any case and across camelCase, snake_case and spaces (`CustomerID` =
  `customer_id`).
- **A rename it cannot be sure of** (a field gone and a new one with values like it): never guessed silently. It is
  offered once as "customerNo looks like customer_id: use it?", and the answer is remembered for that action.
- **Every drift is said once:** a notice and a line on the action ("2 fields new, 1 missing since 14 Nov"), in the
  Session log and to the agent; never a failure unless a binding the user marked required is missing.

## Where it shows
- Widgets' Events and the canvas's wiring: one action picker and its output paths to pick (dynamic content, as Power
  Automate's), with the drift marks.
- The APIs page: Try it shows the envelope, the detected kind, paging and shape.
- API.py and notebooks: `run(...)` from api_adapter (`sab.run` in a kernel).
- The agent: one grouped tool, actions(action): list, describe, run (anything that changes something outside the app
  waits for the user's Allow), shape (the fingerprint and drift).

## The owner's answers (2026-11-22)
- **Your own local sandbox API's endpoints are actions too:** every API, yours or outside, goes through api_adapter;
  the canvas has one action picker and one envelope.
- **Only a field marked required may fail a call on drift;** everything else adapts with a note.

## It learns from every call (the owner, 2026-11-22)
"The key to api_adapter will be the robust dynamic payload we build into the front end. I imagine we use the return
type but don't trust it. We auto detect data types, then every payload for every call and return type we keep a
history of that return in a permanent table. So it actually learns from the API as it uses it and adapts. Same for sent
payloads as well ... So when an agent explores an API through the app there is a stored history of the last time that
endpoint was called and a def will then scan that struct and expose to the widgets an updated contract."
- **The declared return type is a first guess, never trusted:** every answer's types are detected from what came back.
- **The current shape per endpoint, both ways, replaced when it changes** (the owner: "It's not kept forever because
  when a new shape is detected it replaces"): for each endpoint, the shape of what is sent and of what comes back:
  every field path with its detected type, whether it can be empty, its value format (a date style, a number as
  text), the status and kind, and when it was last seen. A call with the same shape only updates "last seen"; a new
  shape replaces the old one, and what changed (fields new, gone, retyped) is said once as the drift note, then the
  old shape is gone.
- **The learned contract:** one function (`learn(endpoint)`) reads the current shape and exposes it to the widgets (the
  canvas's field pickers, an Event's payload fields, the drift marks) instead of the declared one.
- **The agent sees it:** for each endpoint, the last call (what was sent, what came back, when), the current shape and
  the last change.
- **What is kept (the owner's answers):** each endpoint's **current shape** only, shared with the team in the library
  (`apis/<name>/shapes/`, one small file per endpoint, byte-stable, replaced when the shape changes). **Values are never
  kept** (the owner: "No need to ever keep values"): no example payloads, no tick, nothing of an answer's or a request's
  values on disk, in the library or in the project.
## Discover an API (the owner, 2026-11-22)
"The spec file is the front door." An API enters the app only through its specification (an OpenAPI 3.x or Swagger
2.0 document, uploaded or fetched, or written by Add API's form); every endpoint, input and declared shape comes from
it, and what is learned only refines it, never replaces the specification.

"This is about learning an API. We should have a def that can run on an API after we upload its specs and it will
discover and map the payloads to build widgets, scripts and notebooks etc." So `discover(api)`, in api_adapter.py:
1. **Read the specification:** every endpoint, its inputs and its declared answers (a first guess).
2. **Probe, read-only, on the user's Allow** (the owner's answer; once per API, the agent's too): one GET per read
   endpoint at the smallest page size, its required inputs filled from other endpoints' answers (an id from
   `GET /orders` for `GET /orders/{id}`), at most a set number of calls, never an endpoint that writes (those are learned
   from the specification). The shapes found become each endpoint's current shape; no value is kept.
3. **Map each endpoint by its shape:** a list of records to a table (an API table widget, a grid); one record to a
   detail card or an edit form; a single value to a metric; a file to a download; a request body to an input form
   (each field's type picks its box: a closed set of values a dropdown, a date a date picker); ids shared between
   endpoints to a master and detail pair.
4. **No separate report** (the owner: "No need for a discovery report, the API page is all we need"): what was
   learned shows on the APIs page itself, on each endpoint (its learned shape, what it maps to, Build: a notebook cell,
   a script function, a widget on a canvas page); nothing is built until the user picks it there. Endpoints that change
   data stay actions with their forms; discovery never calls them.
The agent runs the same discovery (`actions(action="discover")`) and reads the same endpoints' learned shapes.

## Built (branch api-adapter, 2026-11-22)
1. **api_adapter.py 1.0.0** (the app's `adapters/api_adapter.py`; the project scaffold's `api_adapter.py`, the same
   bytes): `run(action, inputs)`, inputs checked first, the one envelope (ok, status, kind, records / record / value /
   file / text, paging, shape with drift and marks, sent, raw with sign-in headers hidden, error in the refusal shape),
   `facts` per call and `observe(hook)` (the statistics' seam, Plans/stats.plan.md: times, sizes, outcome, who; nothing
   by default). Detection: JSON, JSON lines, XML (no DOCTYPE or entity), CSV, TSV, YAML (PyYAML where present), a file,
   text; the envelope (a list; value/data/items/results...; one or two levels down; a lone wrapper; header and rows;
   the one list beside count/next words), paging (a next link, a Link header, a cursor into the action's token input,
   offset and limit, page numbers; the call's limits, a repeated page), types read from values. Drift against the
   last shape: added, missing (null, marked), retyped (coerced where it reads cleanly), moved; a rename offered only
   when one candidate is alike (a guess otherwise); paths matched in any case and style. Retries: 429 (Retry-After,
   30 s at most) any method; passing errors (5xx, unreachable) only for a method that changes nothing.
   Sign-in: `http(base, auth)` (bearer, an API key in a header or the query, basic: environment variables read at
   each call) or `from_client(client)` (an API_<name>.py client's own). Tested alone in an empty folder.
2. **The specification is the front door:** `actions(doc)` reads OpenAPI 3.x and Swagger 2.0 (refs, allOf, a
   requestBody or a body parameter, a declared answer's kind, envelope and fields as the first guess; a path
   `{placeholder}` the document forgot is a required input all the same). The app names each action as the APIs page
   names its operation.
3. **The current shape, both ways:** `apis/<name>/shapes/<action>.json` (the local sandbox API's in the project's
   `.sab/api-shapes/`): returned (status, kind, format, envelope, each path's type, format and whether it can be empty,
   the fingerprint) and sent (each path, query and body field's type); seen (a day), changed, the change (said once:
   the Session log and `api_shape_changed` to the pages), the offers, the renames taken and declined. Byte-stable
   (sorted, written only when its bytes change). No value, ever. `learn(shape, action)` is the widgets' contract.
4. **discover(api):** on the Allow (asked once per API this session; the agent's too), one GET per read endpoint with
   its limit-like input at 1, required path inputs filled from other answers' ids (memory only), 20 calls at most, never
   a write; for a library API the whole probe runs in one child process through its API blade. Mapped by shape:
   records a table or grid, a record a detail card or form, a value a metric, a file a download, a write a form (its
   body fields' boxes by type: a closed set a dropdown, a date a date picker); master and detail pairs.
5. **The APIs page:** each operation's **What it answers** (learned or declared, maps to, fields with their marks, the
   drift line, rename offers, Run, Build: a notebook cell or a script function to copy, a widget on the project's
   canvas page: a library API's records as a data table on `[API].action`, Return as table switched on; the local
   API's records wired to its endpoint, its writes an API form, a value an API metric); **Discover** at the API's foot;
   the list marks each operation's learned kind and drift. `sab.run(api, action, inputs)` and `sab.records(answer)` in
   Python.
6. **The agent:** `actions(action)`: list, describe, run (a write by the agent waits for Allow), shape, discover,
   offer, build. The tool count grew by one, inside the budget.

## Not yet (decisions for the owner)
- The canvas's Events and the API widgets still call the local sandbox API directly (sab_canvas.api_call): routing them
  through api_adapter means carrying api_adapter.py into every built app and returning envelopes to the widgets
  (their answers would be flattened records). Asked first.
- The Local sandbox APIs panel shows no learned section of its own (its endpoints are actions: `actions(api="local")`,
  and Build works for them); one action picker shared by the canvas and the APIs page is not built.
- Author a call's Send still goes through the web call blade (Structures keeps its lineage); Run on the learned section
  is api_adapter's.
- `.sab/api_examples.json` (Try it's Keep as its example) keeps a payload's values; the owner's "No need to ever keep
  values" may mean it goes.
- Build's cell and function are answered to copy; putting them straight into a notebook or script is not built.
- Remembered Allow for discovery is per session (memory), not kept.

## The owner's answers after the first build (2026-11-22)
- The canvas's Events and the API widgets go through api_adapter: one action picker for any API; every built app
  carries api_adapter.py; the prebuilt API widgets read the envelope's records.
- Try it's "Keep as its example" is removed (.sab/api_examples.json goes; values are never kept); Try it fills its form
  from the learned shape.
- Build inserts: a notebook cell into data.ipynb, or a function into a script the user picks, and opens it there.
- Discover's Allow is remembered per API (kept with the API in the library, until the user takes it back; the agent's
  too).
