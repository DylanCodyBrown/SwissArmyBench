# The Collaboration panel: the team's notes, threads and activity

One floating panel over every page (Ctrl+Shift+M, or the status bar's Collaboration button). It holds the
team's notes, their threads, reactions and the project's activity (each person's changes in words), all as
small files in the open project's `.sab/collaboration/`. They travel with the project's own Pull and Push (the
team repository); a project that is not in the team's shared projects folder keeps them on this computer only.

## Reading
- `collaboration_list`: the timeline (threads and activity, oldest first), the channels (`#general` and the
  team's own), the objects that have threads, unread counts, `shared` and the team's sync words.
  `where` narrows it to `#<channel>` or an object's key (`cell:data.ipynb#7`, `table:orders`); `filter` is
  all, mentions, page (with `page`: the file or table in front), unresolved, activity or notes.
- `collaboration_thread(thread)`: every message, its Markdown, reactions, and each reference with `href`
  (where it opens) and `gone` (no longer in the project).
- `collaboration_search(words)`, `collaboration_activity(n, who)`, `collaboration_unread`.

## Writing (you post as "Claude for <the user's name>")
- `collaboration_post(body, channel | anchor, title)`: a new thread in a channel, or on an object (`anchor`:
  `{"kind", "path", "id", "text"}` from `collaboration_objects`).
- `collaboration_reply(body, thread)`; `collaboration_reply(body, activity)` replies to a change (its thread
  is made the first time).
- `collaboration_edit` (only your own messages), `collaboration_react` (on, or off when it is yours),
  `collaboration_resolve` (`resolved=false` opens it again), `collaboration_pin`, `collaboration_channel`.
- `collaboration_show(anchor | where)`: open the panel in the user's windows on that object or channel.
- You never delete a message, not even your own: deleting is the user's.

## Markdown and references
- CommonMark with tables, fenced code (```sql, ```python), task lists (`- [ ]`), quotes and links.
- An object is a link: `[@data.ipynb cell 7](sab:cell/data.ipynb#7)`, `[@orders](sab:table/orders)`,
  `[@orders.amount](sab:column/orders#amount)`. Take them from `collaboration_objects(words)`, which gives
  each object's `link`: cells (by their number, which never changes), notebooks, scripts and their functions,
  .sql files, API.py's endpoints, canvas widgets, saved analyses, open tables and columns, connections.
- A person is `@login` (the logins `collaboration_objects` lists under people); a mention counts toward
  their unread badge.

## Privacy
- The files hold names, words and the references only, never a table's rows or a value; the activity is the
  change log's words (names and types). Do not paste rows or secrets into a note.
