# SharePoint Client Search — Design Spec

**Date:** 2026-07-08
**Status:** Approved by user (brainstorming session)

## Purpose

Internal staff website: type a client name (even misspelled), get fuzzy-matched
suggestions, click through to the client's SharePoint folder link. Replaces
manually hunting through `SharePoint Links for Clients S.A.xlsx`.

## Source data

`SharePoint Links for Clients S.A.xlsx` (lives in `file management/`, outside
this repo — client data is never committed). Sheet1, header row then data:

| Column | Content |
|--------|---------|
| A | Client ID (e.g. `NAS313`) |
| B | Particulars — client full name |
| C | Cell text = name; **hyperlink target** = SharePoint folder URL |

Current file: 219 clients, 36 rows have no hyperlink, no duplicate names.

## Architecture

Standalone project at `file management/sharepoint-search/`. Python **Flask**
app on port **5001** (benison-chatbot owns 5000). Same conventions as
benison-chatbot: session login, secrets in `.env`, openpyxl for xlsx.

No database. Parsed data stored as `data/clients.json`
(`[{id, name, link|null}]`), regenerated on each admin upload. `data/` is
gitignored.

### Routes

| Route | Auth | Purpose |
|-------|------|---------|
| `GET/POST /login` | — | Staff password → session cookie |
| `GET /` | staff session | Search page |
| `GET /api/clients` | staff session | Full client list as JSON |
| `GET/POST /admin` | admin password | Upload replacement xlsx |
| `GET /logout` | — | Clear session |

Two passwords in `.env`: `STAFF_PASSWORD` (login/search) and
`ADMIN_PASSWORD` (upload page). Plus `SECRET_KEY` for sessions.

### Search: client-side fuzzy (chosen approach)

Search page fetches `/api/clients` once, then **Fuse.js** in the browser does
fuzzy matching as the user types. Chosen over a server-side
`rapidfuzz` endpoint (needless latency at 219 rows) and over a database with
trigram search (overkill for one spreadsheet). Fuse.js is vendored locally
(no CDN dependency).

## Search page behavior

- Single search box, autofocus; results update live after 2+ characters.
- Matches on **name and Client ID** (typing `NAS313` works).
- Fuzzy + word-order-insensitive: "Afsana Rehman" → "Afsana Rahman",
  surname-first works. Fuse threshold tuned loose enough for typos, tight
  enough to avoid noise (~0.4, verify manually).
- Top ~8 matches listed: name, Client ID, then either an **"Open folder"**
  button (SharePoint link, new tab) or a **"No link on file"** badge.
  Linkless clients still appear so staff know the client exists.
- No matches → "No client found."

## Admin upload page

- Gate: staff session required first, then admin password confirms the
  upload action.
- Accepts `.xlsx` with the layout above. Parsing rules:
  - Skip header row and any row with empty name.
  - Missing hyperlink → client kept, `link: null`.
- On success: replace `data/clients.json` atomically; show summary —
  "N clients imported, M missing links" + names of linkless clients.
- On failure (not xlsx, wrong columns, zero valid rows): clear error message,
  **existing data untouched**.
- Initial setup: import the current spreadsheet so the site works day one
  (one-off CLI command `python import_xlsx.py <path>` reusing the same parser).

## Error handling

- All app routes redirect to `/login` when session missing.
- `/api/clients` returns 401 JSON when unauthenticated.
- Passwords and secret key from `.env`; app refuses to start if unset.

## Testing

- **pytest**: xlsx parser (valid file, missing links, malformed/empty file,
  wrong columns), login gate on `/` and `/api/clients`, admin password gate,
  upload replaces data / bad upload preserves data.
- **Manual/browser**: fuzzy matching quality with known misspellings;
  link opens correct SharePoint folder.

## Out of scope (YAGNI)

- Per-user accounts, roles, audit logs.
- Editing individual clients in the app (spreadsheet stays source of truth).
- Auto-sync with SharePoint or the folder copy of the xlsx.
- Deployment beyond running locally like benison-chatbot.
