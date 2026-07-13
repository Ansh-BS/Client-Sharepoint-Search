# Update the live PythonAnywhere site (manual file edit)

For a site that is **already deployed and running**. This is the manual
route: you copy each changed file's contents from your PC into
PythonAnywhere's own file editor, then Reload.

First-time deployment is a different job — see
[DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md).

Throughout, replace `<your-username>` with your PythonAnywhere username and
`<project-folder-name>` with the folder holding `app.py` on the server
(e.g. `sharepoint-search`).

---

## What you are copying up

Five files changed. Nothing else needs to move.

| # | File on your PC | Same path on the server |
|---|---|---|
| 1 | `static/style.css` | `/home/<your-username>/<project-folder-name>/static/style.css` |
| 2 | `static/search.js` | `/home/<your-username>/<project-folder-name>/static/search.js` |
| 3 | `templates/index.html` | `/home/<your-username>/<project-folder-name>/templates/index.html` |
| 4 | `templates/login.html` | `/home/<your-username>/<project-folder-name>/templates/login.html` |
| 5 | `templates/admin.html` | `/home/<your-username>/<project-folder-name>/templates/admin.html` |

`PRODUCT.md` also changed, but it is documentation with no effect at
runtime. Skip it — the server never reads it.

## What you must NOT touch

Leave these alone. They live only on the server and hold your real data and
secrets:

- **`.env`** — your `SECRET_KEY`, `STAFF_PASSWORD`, `ADMIN_PASSWORD`.
  Overwriting it takes the site down.
- **`data/clients.json`** — the real client list you uploaded through
  `/admin`. This is the live data. Nothing in this update changes it.

No Python code changed in this update, so `app.py`, `storage.py`, and
`xlsx_parser.py` stay as they are. No new packages either — you do **not**
need to re-run `pip install`.

---

## 1. Open the file editor on the server

1. Log in at [pythonanywhere.com](https://www.pythonanywhere.com/).
2. Go to the **Files** tab.
3. Navigate into `<project-folder-name>`, then into `static/`.

## 2. Replace each file, one at a time

Do these one by one. For **each** of the five files in the table above:

1. **On your PC**, open the file in VS Code. Select everything
   (`Ctrl+A`) and copy (`Ctrl+C`).
2. **On PythonAnywhere**, click the file name to open it in the editor.
3. Select everything already in it (`Ctrl+A`) and delete it. The file must
   end up empty before you paste — do not paste on top of the old contents,
   or you get both versions stacked and a broken file.
4. Paste (`Ctrl+V`).
5. Click **Save** (top right of the editor).
6. Click the folder path breadcrumb to go back, and repeat for the next
   file.

Order does not matter. All five must be done before you reload — a
half-updated site will look broken (new HTML against old CSS).

> The `templates/` files are in the `templates/` folder, not `static/`. Use
> the breadcrumb at the top of the Files tab to move between the two.

## 3. Reload the web app

Editing files changes nothing on the live site until you reload it.

1. Go to the **Web** tab.
2. Click the big green **Reload** button.
3. Wait for the tick.

## 4. Verify it actually worked

Open `https://<your-username>.pythonanywhere.com` and **hard-refresh** with
`Ctrl+F5` (see the stale-file note in Troubleshooting — a normal refresh
can serve you the old CSS and JS from your browser cache and make a
perfectly good deploy look broken).

Walk the five checks:

1. **Log in** with your staff password. The login page should look normal.
2. **Search a client** — type part of a name. Matching rows appear.
3. **Type a full client name and press `Enter`.** Their SharePoint folder
   opens in a new tab. This is the new behaviour.
4. **Type nonsense and press `Enter`.** The search box shakes and a red
   line appears under it explaining why nothing opened. It must **not**
   open a folder.
5. **Press `Tab` around the page.** Every button and link shows a visible
   purple focus ring.

If all five behave, the update is live.

---

## Troubleshooting

### The site looks half-broken, or the new behaviour is missing

Almost always a **stale cached file**, not a failed deploy. The page
references `style.css` and `search.js` by a plain name with no version
number, so browsers happily reuse the copies they already have.

Fix in this order:

1. **Hard-refresh**: `Ctrl+F5` (or `Ctrl+Shift+R`).
2. Still stale? Open the file directly to see which version the server is
   actually sending:
   `https://<your-username>.pythonanywhere.com/static/style.css`
   — if you see `--action: #0f766e` near the top, the server has the new
   file and the problem is purely your browser's cache. Clear it, or try a
   private window.
3. If that URL shows the **old** file, the paste didn't save. Go back to
   the Files tab, reopen it, confirm the contents, Save, and Reload again.

Worth knowing: **your colleagues will hit this too.** Their browsers will
keep the old CSS/JS until it expires. Tell them to hard-refresh once, or
ask me to add a version tag (`style.css?v=2`) to the templates, which
forces every browser to fetch fresh files and removes the problem
permanently.

### "Something went wrong" / 502 error page

The app crashed on startup. Because this update touched no Python, the
likeliest cause is a mangled paste in a template. Get the real error:

    cd ~/<project-folder-name>
    workon venv
    python3 -c "from app import app"

No output means the app imports fine — reload the Web tab again. A
traceback tells you the file and line to fix.

You can also check the **Error log** link on the Web tab. Templates are
compiled when first requested, so a broken `index.html` shows up as an
error on page load rather than at startup.

### I need to undo this

Every changed file is still in git on your PC, so nothing is lost. To get
the previous version of a file to paste back:

    cd "path/to/sharepoint-search"
    git show 548fa7c:static/style.css

That prints the old contents of that file (swap in whichever path you
need). Copy the output, paste it into the server's editor, Save, Reload.

The two commits in this update are:

- `b25b8ba` — Enter opens an exact name/ID match; hover no longer hijacks Enter
- `790f863` — WCAG AA contrast, focus rings, design tokens, states that teach

---

## This route gets painful — a note for next time

Hand-copying five files is fine once. It does not scale, and every manual
paste is a chance to ship a half-file.

The better loop is the git one: push your commits to a **private** GitHub
repo, then on the server run `git pull` and hit Reload. Two commands, no
copy-paste, and the server's code provably matches your machine's. That
path is already written up in
[DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md) §1(a) and
"Maintenance".

This repo currently has **no git remote**, so that route needs a private
GitHub repo creating first. Say the word and I'll walk you through it.
