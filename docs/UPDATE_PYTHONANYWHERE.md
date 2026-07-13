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

Six files changed. Nothing else needs to move.

| # | File on your PC | Same path on the server |
|---|---|---|
| 1 | `app.py` | `/home/<your-username>/<project-folder-name>/app.py` |
| 2 | `static/style.css` | `/home/<your-username>/<project-folder-name>/static/style.css` |
| 3 | `static/search.js` | `/home/<your-username>/<project-folder-name>/static/search.js` |
| 4 | `templates/index.html` | `/home/<your-username>/<project-folder-name>/templates/index.html` |
| 5 | `templates/login.html` | `/home/<your-username>/<project-folder-name>/templates/login.html` |
| 6 | `templates/admin.html` | `/home/<your-username>/<project-folder-name>/templates/admin.html` |

**All six or none.** `app.py` now sets `ASSET_VERSION`, and the three
templates read it to tag the stylesheet and script as `?v=2`. Copy the
templates without `app.py` and the tag renders empty, which breaks the
cache fix — so don't stop halfway.

`PRODUCT.md` also changed, but it is documentation with no effect at
runtime. Skip it — the server never reads it.

No new packages were added, so you do **not** need to re-run
`pip install`.

## What you must NOT touch

Leave these alone. They live only on the server and hold your real data and
secrets:

- **`.env`** — your `SECRET_KEY`, `STAFF_PASSWORD`, `ADMIN_PASSWORD`.
  Overwriting it takes the site down.
- **`data/clients.json`** — the real client list you uploaded through
  `/admin`. This is the live data. Nothing in this update changes it.

`storage.py` and `xlsx_parser.py` are unchanged — leave them alone too.

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

Open `https://<your-username>.pythonanywhere.com`. A normal refresh is
enough — the `?v=2` tag means browsers cannot serve you a stale stylesheet
or script.

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

The page now requests `style.css?v=2` and `search.js?v=2`. Because the URL
changed, every browser — yours and your colleagues' — is forced to fetch
the new files. Nobody needs to hard-refresh. That is the whole point of the
tag.

So if the site still looks wrong, suspect a **failed paste**, not a cache.
Check what the server is actually holding:

    https://<your-username>.pythonanywhere.com/static/style.css?v=2

If you see `--action: #0f766e` near the top, the server has the new file.
If you see the old file, that paste didn't save — reopen it on the Files
tab, confirm the contents, Save, and Reload.

Then view the page source (`Ctrl+U`) and check the stylesheet link really
says `?v=2`. If it says plain `style.css` with no tag, you copied the
templates but **not `app.py`** — go back and do that one too.

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

## Next time you change the CSS or the JS

**Bump `ASSET_VERSION` in `app.py` before you deploy.**

    ASSET_VERSION = "2"    ->    ASSET_VERSION = "3"

That one number is what forces every staff browser to fetch the new
stylesheet and script. Change `style.css` or `search.js` without bumping it
and your colleagues keep running the old files — the site will look
unchanged to them and correct to you, which is a miserable thing to debug.

Only that one line needs editing; the three templates read it
automatically. If a deploy touches neither `style.css` nor `search.js`,
leave the number alone.

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
