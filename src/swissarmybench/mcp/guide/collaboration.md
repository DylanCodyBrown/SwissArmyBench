# The Collaboration panel: the team's notes and threads

One floating panel over every page, opened from the small icon at the top right of every window (or
Ctrl+Shift+M). It holds what people write: notes, their threads, reactions, resolves and pins, as small files in
the open project's `.sab/collaboration/`. They travel with the project's own Pull and Push (the team repository);
a project that is not in the team's shared projects folder keeps them on this computer only. The change log is not
in the panel.

## Reading
- `collaboration_list`: the threads (oldest first), the channels (`#general` and the team's own), the objects
  that have threads, unread counts, `shared` and the team's sync words. `where` narrows it to `#<channel>` or an
  object's key (`cell:data.ipynb#7`, `table:orders`); `filter` is all, mentions, page (with `page`: the file or
  table in front, or a JSON list of them) or unresolved.
- `collaboration_thread(thread)`: every message, its Markdown, reactions, and each reference with `href` (where
  it opens) and `gone` (no longer in the project).
- `collaboration_search(words)`, `collaboration_unread` (the counts, and `news`: what is new to the user since
  they last read here), `collaboration_profile` (the user's name in the panel).

## Writing: one command
- `collaboration_post(body, channel | anchor, title)` starts a thread in a channel or on an object (`anchor`:
  `{"kind", "path", "id", "text"}` from `collaboration_objects`); `collaboration_post(body, thread)` replies in
  one. It always posts as "Claude for <the user's name>".
- That is the agent's only way to write here (the owner, 2026-11-25). Editing, deleting, reacting, resolving,
  pinning, making a channel, opening the panel and the user's name are the user's own: their routes answer 403.

## Markdown and references
- CommonMark with tables, fenced code (```sql, ```python), task lists (`- [ ]`), quotes, links and emoji.
- An object is a link: `[@data.ipynb cell 7](sab:cell/data.ipynb#7)`, `[@orders](sab:table/orders)`,
  `[@orders.amount](sab:column/orders#amount)`. Take them from `collaboration_objects(words, page)`: the page's
  objects first (`page`), then people, then the rest of the project: cells (by their number, which never changes),
  notebooks, scripts and their functions, .sql files, API.py's endpoints, canvas widgets, saved analyses, open
  tables and columns, connections.
- A person is `@login` (the logins `collaboration_objects` lists under people); a mention counts toward their
  unread badge.

## Privacy
- The files hold names, words and the references only, never a table's rows or a value. Do not paste rows or
  secrets into a note.
