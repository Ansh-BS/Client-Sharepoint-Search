# Google-style predictive search — design

Date: 2026-07-09

## Problem

`static/search.js` uses Fuse.js with `threshold: 0.4` + `ignoreLocation: true`. Fuzzy
scoring surfaces client names that share scattered letters with the query rather
than ones that actually start with or contain it — user types a name and gets an
unrelated client suggested first.

## Goal

Predictive-search UX like Google's box: results ranked by relevance to what's
literally typed, matched text highlighted, keyboard-navigable, still tolerant of
small typos as a last resort.

## Design

**Three-tier ranking** (client-side, over the full client list already fetched by
`init()`):

1. **Prefix match** — client `name` or `id` starts with the query (case-insensitive).
   Sorted alphabetically. Highest priority.
2. **Substring match** — query appears anywhere in `name`/`id`, not caught by tier 1.
3. **Fuzzy fallback** — Fuse.js (`threshold: 0.25`, down from 0.4) fills any
   remaining slots up to the 8-result cap, only when tiers 1–2 don't fill it.
   Provides typo tolerance without dominating exact/prefix results.

Dedup by `id` across tiers (an item found in tier 1 must not repeat in tier 3).

**Highlighting**: matched substring wrapped in `<mark class="match">` inside the
rendered name/id, mirroring Google's bolded-match convention.

**Keyboard nav**: ArrowUp/ArrowDown moves an `aria-selected` cursor across `<li>`
results, Enter opens the selected result's link (if any), Escape clears results.
Mouse hover still works via existing click-through anchor.

## Files touched

- `static/search.js` — replace single `fuse.search()` call with tiered
  match/rank/dedup, add highlight markup, add keydown handler.
- `static/style.css` — add `.match` highlight style and `li[aria-selected="true"]`
  selected-row style.

No backend or template changes — `templates/index.html` markup and `/api/clients`
endpoint are unchanged.

## Testing

No JS test harness in this project (tests/ is pytest, backend-only). Verify
manually: run the Flask dev server, exercise the search box in a browser —
prefix match, substring match, deliberate typo (fuzzy fallback), arrow-key nav,
Enter-to-open.

## Build workflow (per user instruction)

1. Fable subagent: finalize the exact tiering/highlight/keyboard algorithm
   (pseudocode-level detail) from this design.
2. Opus subagent: implement in `search.js` / `style.css`.
3. Separate review subagent: review the diff for correctness bugs before merge.
