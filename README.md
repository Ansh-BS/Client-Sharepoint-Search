# SharePoint Client Search

Internal staff site: type a client name (typos fine) or Client ID, get
fuzzy-matched suggestions with a button to the client's SharePoint folder.

## Run

    python app.py

Serves on http://127.0.0.1:5001 (benison-chatbot uses 5000).
Needs `.env` (copy `.env.example`): `SECRET_KEY`, `STAFF_PASSWORD`
(login for the search page), `ADMIN_PASSWORD` (extra password for
uploading a new spreadsheet on /admin).

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
