# The API adapter: any payload in, one shape out (the owner, 2026-11-22)

Status: decided; not built. Cared for as design principle 12b (equal to adapter.py). Comes after the data adapter's phase 3 (it hands table-shaped answers to it).

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
4. **A discovery report first:** each endpoint, what was learned, what is proposed; the user ticks what to build, then
   it writes into the project scaffold: a notebook (one cell per endpoint reading into a table), a script (one
   function per action), widgets wired onto a starter canvas page. Endpoints that change data stay actions with
   their forms; discovery never calls them.
The agent runs the same discovery and gets the same report (`actions(action="discover")`).
