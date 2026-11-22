# Real-time statistics for every call (the owner, 2026-11-22)

Status: built (branch stats-changes, 2026-11-22): adapter.py 1.2.0 observe(), services/call_stats.py, the stats tool, the
Connections and APIs pages' figures; decisions in docs/ideas.md "Real-time statistics". Not built: the Environment page's
Used in with each use's cost (its page is branch environment's), the Performance Analyzer's timings folded in.

> "We should build real-time stats into the back end for the agent to read about the API calls: the time, the size of
> the return, along with the shape we've already saved, and we can do the same for connectors. There should be enough
> data to pass back to the agent so we can actually troubleshoot, and we can make performance upgrades to widgets,
> tables and logic based on statistics and readings." (spoken; transcribed)

## Each call's record (both adapters: adapter.py's reads, queries and writes; api_adapter.py's runs)
- **Time, in parts:** waiting in the connection's line, connecting, the first row or byte, the total.
- **Size:** rows, bytes, pages followed, columns returned against columns used.
- **What happened:** status, retries, an error's kind, and what was folded into the source (filters, limit, totals)
  against what DuckDB did after.
- **Who and where:** the user, the agent, a widget (canvas page and widget), a notebook cell, an endpoint; the table,
  connection or endpoint; the shape's fingerprint (it joins the shapes already kept).
- **Never a value.**

## Kept (the owner's answer)
- Each call's record in memory for this session (the last few thousand).
- The running figures per endpoint and per table (count, 50th and 95th percentile times, error rate, typical size,
  last called) kept with the project in `.sab/stats.json` (Git-ignored), so today can be compared with last week.

## Read by
- **The agent:** one tool, `stats(action)`: summary, slowest, errors, by endpoint or table, hints.
- **Hints in plain words** (as the Performance Analyzer's): a widget reading millions of rows to use three columns
  ("filter at the source"), an endpoint paged 40 times a call ("ask for larger pages"), a table read again and again
  with the same plan ("keep it as a table").
- **The pages:** the Connections and APIs pages show the figures per connection and endpoint; the Environment page's
  Used in carries each use's cost.
- Folds in what exists today: the Queries window's finished list, the connection call counts, the Performance
  Analyzer's call timings.
