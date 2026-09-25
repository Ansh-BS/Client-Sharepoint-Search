# Client SharePoint Search

Internal staff site: type a client name (typos fine) or Client ID, get
fuzzy-matched suggestions with a button to the client's SharePoint folder.

## Run

    python app.py

Serves on http://127.0.0.1:5001 (benison-chatbot uses 5000).
Needs `.env` (copy `.env.example`): `SECRET_KEY`, `STAFF_PASSWORD`
(login for the search page), `ADMIN_USERNAMES` (comma-separated) and
`ADMIN_PASSWORD` (the second credential pair that unlocks /admin). Every
listed admin shares the one password but signs in under their own name;
unlocks and every confirmed change are logged to the server log with that
name. The search-page login asks for the staff password only — no
username.

## Update the client list

Either upload the new xlsx on **/admin** (staff login, then admin
password), or from the command line:

    python import_xlsx.py "../SharePoint Links for Clients S.A.xlsx"

Expected spreadsheet layout: first sheet, header row, then
column A = Client ID, column B = client name, column C = cell whose
**hyperlink** is the SharePoint folder URL. Rows without a name are
skipped; rows without a hyperlink show a "No link on file" badge.

## Tests

    python -m pytest tests/ -v

## Notes

- Data lives in `data/clients.json` (gitignored — client data never
  committed). Uploads replace it atomically; a bad upload leaves the
  old data untouched.
- Fuse.js v7 is vendored at `static/fuse.min.js`; no CDN at runtime.
- Search: min 2 characters, top 8 results, threshold 0.4.
- Light and dark themes. First visit follows the OS; the toggle in the top
  right overrides it and the choice is remembered. `static/theme.js` runs
  before first paint so the page never flashes the wrong theme.
- Colours come from HeroUI's palette (`:root` light, `:root.dark` dark, same
  token names in both). Rules read `var(--token)` only — a literal colour in a
  rule cannot be re-themed, and `tests/test_theme.py` fails if one appears.
