# The change log (the owner, 2026-11-22)

Status: decided; not built.

> "A change tracking, event based tracker that would write to a per project change log, so when a table structure,
> an API, or anything is modified the agent could quickly run an MCP tool that would return the last recorded change
> on an object."

## One event per change
- **What counts:** a table's structure (columns added, gone, retyped), source or steps; a connection's settings or
  sign-in; an API's specification or an endpoint's learned shape (the API adapter's drift); an endpoint added to or
  changed in API.py; a widget's code or properties; a canvas page; a notebook cell's or a script's code; a setting or
  variable (by name); a library added, updated, pinned or removed.
- **Each entry:** when; who (the user, the agent, the app itself as for a detected drift); the object (kind and name);
  what changed, in plain words and as a structural difference (columns, fields, settings by name); the fingerprint
  before and after. **Never a value.**
- **Written as it happens,** one line per change, by one event that the services raise; the Session page reads the
  same events (the "one log" merge of Plans/simplify-decisions.plan.md).

## Kept (the owner's answers)
- In the project, **not shared**: `.sab/changes.jsonl` (Git-ignored): this computer's changes only.
- **Everything kept** (a full history; small, since it never holds values).

## For the agent
One tool, `changes(action)`: `last(object)` (the most recent change to it), `history(object, n)`, `since(time)` (all
changes since a moment, e.g. since the agent last looked), and a search by kind or by who.
