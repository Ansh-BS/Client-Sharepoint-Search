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

## Amendment: in-order subsequence tier

User request: typing `hmpl` should surface "Hampal" — letters `h`, `m`, `p`, `l`
appear in that order within the name (skipping over `a`, `a`), even though it's
neither a prefix nor a contiguous substring, and edit-distance fuzzy (tier 3 as
originally shipped) doesn't catch it either (deleting 2 of 6 chars exceeds the
0.25 threshold).

Adds a new **tier 3: in-order subsequence match** (VSCode Cmd-P style), inserted
between substring (now tier 2) and the existing edit-distance Fuse fallback
(now tier 4):

- A client's `name`/`id` matches if every character of the (lowercased) query
  appears in the field in the same order, not necessarily contiguous.
- **Scoring** (lower = better, for ranking within this tier): sum of gaps
  between consecutive matched character positions, plus the start index of the
  first match (rewards matches that start earlier and stay tight). Compute
  per-field (name and id), take the better of the two per client.
- Only clients not already placed in tier 1/2 are considered; only fills
  remaining slots up to `MAX_RESULTS` (8), same fill-until-full pattern as the
  other tiers.
- **Highlighting**: subsequence matches are non-contiguous, so each matched
  character gets its own `<mark class="match">`, not one span — render the
  field character-by-character, wrapping only the matched-position characters.
- Tier 4 (Fuse edit-distance fuzzy) still runs last, for real typo tolerance
  (wrong/transposed letters) that subsequence matching doesn't cover, only if
  slots remain after tier 3.

Updated tier order: **1 prefix → 2 substring → 3 in-order subsequence → 4 Fuse
fuzzy (typo tolerance)**.

## Build workflow (per user instruction)

1. Fable subagent: finalize the exact tiering/highlight/keyboard algorithm
   (pseudocode-level detail) from this design.
2. Opus subagent: implement in `search.js` / `style.css`.
3. Separate review subagent: review the diff for correctness bugs before merge.
