# Deploy to PythonAnywhere (free tier)

Puts this app online at `https://<your-username>.pythonanywhere.com`,
staff login and all. No code changes needed — `app.py` already exposes a
module-level `app` that the WSGI server can import.

Throughout, replace `<your-username>` with your real PythonAnywhere
username and `<project-folder-name>` with the folder the code ends up in
(e.g. `sharepoint-search`).

## 0. Make an account

Sign up at [pythonanywhere.com](https://www.pythonanywhere.com/). The
"Beginner" plan is free, no credit card. Signup is self-explanatory — do
that yourself, then come back here.

## 1. Get the code onto the server

Pick **one** of these. Option (a) makes future updates a two-command
chore; option (b) is a one-time copy with no easy re-sync.

### Option (a) — git clone (recommended)

Requires this repo to be on GitHub (or similar) and reachable by you. A
**private** repo is fine — for private repos you'll need PythonAnywhere to
authenticate (add a deploy key, or clone over HTTPS with a personal access
token). A public repo just clones with no setup. Either way, keep the repo
private if you're unsure: `data/` is gitignored so no client data is in it,
but the repo is still your internal tool.

On the Web dashboard open **Consoles → Bash**, then:

    git clone <your-repo-url> <project-folder-name>

That leaves the code at `/home/<your-username>/<project-folder-name>`.

### Option (b) — zip and upload (no git)

1. On your own PC, zip the project folder — but **exclude** `data/`,
   `.env`, `__pycache__/`, `.git/`, and `.pytest_cache/`. Just the code:
   `app.py`, `storage.py`, `xlsx_parser.py`, `import_xlsx.py`,
   `requirements.txt`, `README.md`, and the `static/`, `templates/`,
   `tests/`, `docs/` folders.
2. On PythonAnywhere go to the **Files** tab and upload the zip into your
   home directory.
3. Open **Consoles → Bash** and unzip it:

       unzip <your-zip-name>.zip -d <project-folder-name>

   Check that `app.py` is directly inside
   `/home/<your-username>/<project-folder-name>` (not nested one level
   deeper). If it's nested, move it or re-zip without the extra folder.

There is no `git pull` update path with this option — to update later you
re-upload a fresh zip.

## 2. Create the virtualenv and install dependencies

In the Bash console, from anywhere:

    mkvirtualenv --python=/usr/bin/python3.10 venv

That creates a virtualenv named `venv` and activates it (your prompt shows
`(venv)`). If `python3.10` isn't offered, use another 3.x that is —
`python3.11` — and remember which you picked; the Web tab must match it in
step 4.

Install the requirements into it:

    cd ~/<project-folder-name>
    pip install -r requirements.txt

The virtualenv lives at `/home/<your-username>/.virtualenvs/venv` — note
that path, you'll paste it in step 4.

## 3. Create the real `.env` file on the server

The app refuses to start without `SECRET_KEY`, `STAFF_PASSWORD`, and
`ADMIN_PASSWORD`. You create these directly on the server and fill in your
**own** real values. This document never sees or sets them — you type your
own secrets into your own server's file.

First generate a strong secret key. In the Bash console:

    python3 -c "import secrets; print(secrets.token_hex(32))"

Copy the long hex string it prints. Then create the file:

    cd ~/<project-folder-name>
    nano .env

Paste in these three lines, replacing every `<...>` with your real values
(the `SECRET_KEY` value is the hex string you just generated):

    SECRET_KEY=<paste-the-generated-hex-key-here>
    STAFF_PASSWORD=<choose-your-own-staff-login-password>
    ADMIN_PASSWORD=<choose-a-different-admin-upload-password>

Make `STAFF_PASSWORD` (the search-page login) and `ADMIN_PASSWORD` (the
extra password to upload a spreadsheet) different from each other. Save in
nano with `Ctrl+O`, `Enter`, then exit with `Ctrl+X`.

Leave `SESSION_COOKIE_SECURE` out entirely — it defaults to secure, which
is correct because PythonAnywhere serves your site over HTTPS.

## 4. Set up the web app

1. Go to the **Web** tab → **Add a new web app**.
2. It asks about a framework — choose **Manual configuration** (NOT the
   "Flask" option). This app already exists; the Flask wizard would
   scaffold a throwaway app over it.
3. Pick the **same Python version** you used in step 2 (e.g. Python 3.10).
4. It creates the app and drops you on its config page. Fill in three
   fields there:
   - **Source code**: `/home/<your-username>/<project-folder-name>`
   - **Working directory**: `/home/<your-username>/<project-folder-name>`
     (same path — the app loads `.env` from the working directory, so this
     must point at the folder that holds your `.env`)
   - **Virtualenv**: `/home/<your-username>/.virtualenvs/venv`
5. In the **Code** section, click the link to the **WSGI configuration
   file** (path looks like
   `/var/www/<your-username>_pythonanywhere_com_wsgi.py`). Delete
   everything in it and paste the contents of
   `docs/pythonanywhere_wsgi_template.py` from this repo, then fix the two
   placeholders in it (`<your-username>`, `<project-folder-name>`). Save.

## 5. Add the static files mapping

Flask serves its `static/` folder itself, but under PythonAnywhere's WSGI
setup those requests would otherwise route through the Python app (slow) or
404. Map them so the server delivers CSS/JS/logo directly.

On the **Web** tab, in the **Static files** section, **Enter URL /
Directory**:

- **URL**: `/static/`
- **Directory**: `/home/<your-username>/<project-folder-name>/static`

Every `url_for('static', ...)` reference (the stylesheet, `search.js`,
`fuse.min.js`, `logo.png`) resolves through this mapping.

## 6. Reload and visit

Click the big green **Reload** button at the top of the Web tab. Then open:

    https://<your-username>.pythonanywhere.com

You should get the login page. Log in with the `STAFF_PASSWORD` you set in
step 3.

If you instead get an error page, open the Web tab's **Error log** link —
the most common causes are a wrong path in the WSGI file, the virtualenv
field not matching the Python version, or a missing line in `.env`.

## 7. Upload the real client data

The server starts with an empty client list. Load the real data through the
app's own admin screen — exactly like using it locally:

1. Log in at `/` with your `STAFF_PASSWORD`.
2. Go to `/admin`.
3. Enter your `ADMIN_PASSWORD` and choose your real client spreadsheet
   (`.xlsx`).
4. Upload. It parses and saves; you'll see a count and any rows missing a
   link.

**This is the only way real client data should ever reach the server.**
Never commit it to git, never put it in the zip, never upload the
spreadsheet file through the Files tab. Only this `/admin` form. The app
writes it to `data/clients.json` on the server, which stays there.

## Troubleshooting

**"502 backend error" / "Something went wrong" on the site.** The WSGI
process crashed on startup. Don't just stare at the Web tab's Error log —
it can appear blank right after a change if you haven't clicked **Reload**
yet. Get the real traceback directly instead:

    cd ~/<project-folder-name>
    workon venv
    python3 -c "from app import app"

If this prints a traceback, that's your real error. If it prints **nothing**,
the import itself is fine and the problem is more likely a stale Reload or a
field mismatch on the Web tab — re-check **Source code** / **Working
directory** / **Virtualenv**, then Reload again.

**`SystemExit: Missing required .env values: SECRET_KEY, STAFF_PASSWORD,
ADMIN_PASSWORD`** (this is what the command above will print if `.env` isn't
being picked up). Two likely causes, check in order:

1. **`.env` isn't in the project folder.** The app loads it from the
   **Working directory** you set on the Web tab — if you ran `nano .env`
   from your home directory (`~`) instead of `~/<project-folder-name>`, it's
   in the wrong place. Check both:

       ls -la ~/<project-folder-name>/.env
       ls -la ~/.env

   If it turns up in your home directory instead, move it:

       mv ~/.env ~/<project-folder-name>/.env

2. **`.env` exists but is empty or malformed.** Confirm with:

       cat ~/<project-folder-name>/.env

   You should see exactly three lines, `KEY=value`, no quotes, no spaces
   around the `=`. If it's blank, nano wasn't saved — redo it (`nano .env`,
   type the three lines, `Ctrl+O`, **Enter**, `Ctrl+X`) and verify with
   `cat` again immediately, don't skip that check.

After fixing either case, re-run the `python3 -c "from app import app"`
check — no output means it's fixed — then click **Reload** on the Web tab
before reloading the site in your browser.

## Maintenance

**Dormancy.** Free PythonAnywhere web apps get paused after a stretch of no
traffic (around a month). This is **not** data loss — the file system
(including `data/clients.json`) is persistent, unlike some free hosts. If
the site is dead after a quiet spell, log into the PythonAnywhere
dashboard, go to the **Web** tab, and click **Reload** (there may also be a
"run until 3 months from today" style button to re-enable it). It comes
back with the data intact.

**Updating the app (git-clone path only).** When you change the code:

    cd ~/<project-folder-name>
    git pull

Then click **Reload** on the Web tab. That's the whole loop — no build
step, no pipeline needed for a low-traffic internal tool. (If you deployed
via the zip method, "update" means re-uploading a fresh zip and reloading.)
