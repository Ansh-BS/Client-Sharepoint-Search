# Bulk Link Health Check — Design

**Date:** 2026-07-30
**Status:** Approved, ready for implementation plan

## Problem

Every client row carries a SharePoint sharing `link`. When a share is revoked,
the folder is deleted, or a token is mistyped on import, the link silently
breaks. Staff only discover it at the worst moment — mid-task, clicking a dead
link. Per PRODUCT.md design principle 3 ("every state teaches; a dead end is a
defect"), an unreachable link is a silent defect the tool should surface, not
wait for a user to trip over.

There are 220 clients today. No current mechanism verifies links resolve — only
a client-side *format* check (`isValidLink` in `search.js`), which cannot tell a
live share from a revoked one.

## Goal

Detect and report links that no longer resolve, so an admin can fix the
spreadsheet before staff hit them. **Report only — never mutate `clients.json`,
never delete.**

## Detection method (empirically established)

Unauthenticated HTTP requests to the sharing URLs discriminate alive from dead.
Verified 2026-07-30 with `curl -I` against real client links on both the
`OnSelfAssessment` and `OnLimitedCompanies` sites:

| Case | HTTP status | Interpretation |
|------|-------------|----------------|
| Valid share token | **401** Unauthorized (auth wall) | share recognized → **alive** |
| Corrupted / revoked token, valid site | **200** (generic login/error page) | token not recognized → **suspect** |
| Nonexistent site path | **404** | site/path gone → **dead** |

A `HEAD` request is enough to get the status (no body needed), so checks are
cheap.

**Caveat, load-bearing:** this is an *unauthenticated* heuristic. A `401` proves
SharePoint recognizes the share token; it does **not** prove the folder still has
content, has the right permissions, or that a given staff member can open it.
Conversely a `200` is *probably* a revoked/expired share but the check cannot be
certain. Therefore non-`ok` results are labelled **"needs review"**, and the
engine never deletes or edits a client on the strength of them.

## Architecture

Four units, each independently testable.

### 1. Detection engine — `link_health.py`

Pure, location-agnostic module. **Stdlib `urllib` only** — no new dependency
(the project ships flask + openpyxl only; `requests` is not a dep, and the
PythonAnywhere free tier should not need a new install).

```
check_link(url, timeout) -> (category, status)
```

Classification:

| Category | Trigger | Meaning |
|----------|---------|---------|
| `nolink`  | empty / missing `link` | no SharePoint link on file |
| `ok`      | HTTP 401 | share recognized (alive) |
| `dead`    | HTTP 404 | site / path gone |
| `suspect` | HTTP 200 / 3xx / any other status | token unrecognized → likely revoked, **needs review** |
| `error`   | timeout / connection failure | inconclusive, re-check later |

```
check_all(clients, workers=8, timeout=15) -> report dict
```

Runs `HEAD` requests concurrently via `ThreadPoolExecutor`, sets a descriptive
`User-Agent`, and returns the report dict below. Expected wall time ~30–60s for
220 links.

**Invariants:**
- Engine only *reads* links and *reports*. It never writes `clients.json`, never
  deletes, never edits a client.
- No aggressive retry — one attempt per link; `error` category captures
  transient failures for the next run.

### 2. Report file — `data/link_health.json`

Server-side, **untracked** (all of `data/` is gitignored — same as
`clients.json`). Sits beside `clients.json` wherever the check runs.

```json
{
  "checked_at": "2026-07-30T11:05:00Z",
  "total": 220,
  "counts": { "ok": 214, "dead": 2, "suspect": 3, "nolink": 1, "error": 0 },
  "flagged": [
    { "id": "DAV099", "name": "Adam Davies", "category": "dead", "status": 404 },
    { "id": "NAS313", "name": "Abbas Hassan Nasser", "category": "suspect", "status": 200 }
  ]
}
```

- Stores summary counts + only the **flagged** (non-`ok`) rows — keeps the file
  tiny and is exactly what the admin panel needs.
- The `link` value is omitted from the report; admin already has it via
  `clients.json`, so duplicating 220 URLs is avoided.
- `checked_at` is UTC ISO-8601.
- Written atomically (tmp file + `os.replace`), reusing the pattern already in
  `storage.py`.

### 3. CLI — `check_links.py`

Standalone script, runnable identically on a PC/office machine or the server.

- loads clients via `storage.load_clients()`
- runs `check_all`
- writes `data/link_health.json` atomically
- prints a one-line summary to stdout, e.g. `214 ok, 2 dead, 3 suspect, 1 no-link, 0 error`
- `argparse` knobs: `--workers`, `--timeout`, `--clients` path, `--out` path

This is the single engine both trigger paths invoke.

### 4. Admin display + optional server button

**Display (always present):** `/admin` GET reads `data/link_health.json` and
renders a "Link health" panel below the existing upload form:

- last-checked time shown relative ("3 hours ago") plus the counts row
- a table of **flagged** clients: id, name, category badge, status code. Badge
  pairs colour with text (accessibility principle: colour is never the sole
  carrier of meaning)
- empty states that teach:
  - no report file yet → "No link check has been run yet."
  - report present, zero flagged → "All 220 links OK ✓"

**Re-run button (gated — see reachability decision):**

- POST `action="check_links"` on `/admin`, `@staff_required`, covered by the
  existing `10 per 15 minutes` limiter
- runs `check_all` on a **background thread**, writes the report; the page
  responds immediately with "Check running… refresh in a minute"
- wired in **only if** SharePoint is reachable from the deployed server, gated
  behind a `LINK_CHECK_ENABLED` flag. If the PythonAnywhere free tier blocks
  outbound requests to `*.sharepoint.com`, the button is omitted, the panel
  stays display-only, and `check_links.py` is run on the office machine that
  holds `clients.json`.

## Deployment / run-location decision (open, resolved by a test)

PythonAnywhere free tier restricts outbound HTTP to a proxy whitelist, so the
server may not reach SharePoint. **Step 1 of the implementation plan is a
reachability test the user runs in a PythonAnywhere console** (e.g. a one-line
`urllib`/`curl` HEAD against a known-alive link, expecting `401`):

- **Reachable → 401:** enable the server button (`LINK_CHECK_ENABLED=1`); checks
  can run live on the server against the server's `clients.json`. Optionally an
  OS-scheduled run later.
- **Blocked:** leave the button off; run `check_links.py` on the office/PC
  machine that has a copy of `clients.json`; the report lives server-side and the
  admin panel displays whatever the last run wrote.

Because `data/` is untracked, the report never travels by git — it is written
next to `clients.json` on whichever machine runs the check. The engine, report
format, CLI, and admin display are all identical across both outcomes; only the
button wiring differs.

## Testing (pytest, existing 44-test suite — no new runner)

- **Engine** (`test_link_health.py`): monkeypatch `urllib` responses → assert
  401→`ok`, 404→`dead`, 200→`suspect`, timeout→`error`, empty link→`nolink`.
  Verify the engine issues `HEAD` and never writes `clients.json`.
- **Report**: shape is correct, only non-`ok` rows appear in `flagged`, counts
  sum to `total`, write is atomic.
- **CLI**: run against a fixture client list → correct report file written;
  stdout summary matches.
- **Admin**: GET renders the panel from a fixture report across three states
  (no report / all-ok / has-flagged); the re-run button is absent when
  `LINK_CHECK_ENABLED` is off.

No JavaScript is added, so no JS test runner is introduced.

## Non-goals

- Not an authenticated / Graph-API check — no app registration, no verifying
  folder contents or per-user permissions.
- Not auto-repair — the tool never edits or deletes clients; an admin fixes the
  spreadsheet and re-uploads through the existing preview/confirm flow.
- Not real-time — links are checked on demand (or on a schedule later), not on
  every search.

## Config knobs

- `workers` (default 8) — concurrency
- `timeout` (default 15s) — per-request
- `LINK_CHECK_ENABLED` — gates the server-side re-run button
