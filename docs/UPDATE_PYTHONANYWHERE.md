# Update the live PythonAnywhere site (manual file edit)

> **Superseded once the server is on git.** See
> [GIT_SETUP_PYTHONANYWHERE.md](GIT_SETUP_PYTHONANYWHERE.md) — a one-time
> setup after which every deploy is `git pull` + Reload, with no file list and
> no chance of a half-pasted file. Keep this document as the fallback for when
> the token expires or git is otherwise unavailable.

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

Six files. **Five are edits. One is a file that does not exist on the server
yet and has to be created** — see the ⚠ row.

| # | File on your PC | Same path on the server |
|---|---|---|
| 1 | `app.py` | `/home/<your-username>/<project-folder-name>/app.py` |
| 2 | `static/style.css` | `/home/<your-username>/<project-folder-name>/static/style.css` |
| 3 | ⚠ `static/password.js` — **new file, create it** | `/home/<your-username>/<project-folder-name>/static/password.js` |
| 4 | `templates/index.html` | `/home/<your-username>/<project-folder-name>/templates/index.html` |
| 5 | `templates/login.html` | `/home/<your-username>/<project-folder-name>/templates/login.html` |
| 6 | `templates/admin.html` | `/home/<your-username>/<project-folder-name>/templates/admin.html` |

**All six or none.** `app.py` sets `ASSET_VERSION`, now `"4"`, and the
templates read it to tag the stylesheet and scripts as `?v=4`. Copy the
templates without `app.py` and the tag renders empty, which breaks the cache
fix — so don't stop halfway.

**`static/search.js` did not change this time. Leave it alone.** All the
search behaviour — Enter to open, arrow keys, the shake, the cursor glow — is
unchanged; this update is the look of the page plus the password toggle.

`mockups/` and `tests/` are on your PC only. The server never reads them.
Don't copy them up.

No new packages were added, so you do **not** need to re-run `pip install`.

## What you must NOT touch

Leave these alone. They live only on the server and hold your real data and
secrets:

- **`.env`** — your `SECRET_KEY`, `STAFF_PASSWORD`, `ADMIN_USERNAMES`,
  `ADMIN_PASSWORD`.
  Overwriting it takes the site down.
- **`data/clients.json`** — the real client list you uploaded through
  `/admin`. This is the live data. Nothing in this update changes it.

`storage.py`, `xlsx_parser.py` and `static/search.js` are unchanged — leave
them alone too.

---

## 1. Open the file editor on the server

1. Log in at [pythonanywhere.com](https://www.pythonanywhere.com/).
2. Go to the **Files** tab.
3. Navigate into `<project-folder-name>`.

## 2. Create the one new file first

`static/password.js` is new. It is the code behind the eye icon that reveals
a typed password. If you skip it, the login page still works, but clicking the
eye does nothing.

1. On the **Files** tab, go into the `static/` folder.
2. In the **"Enter new file name"** box at the top of the file list, type
   `password.js` and click **New file**. It opens empty in the editor.
3. On your PC, open `static/password.js` in VS Code, select all (`Ctrl+A`),
   copy (`Ctrl+C`).
4. Paste into the empty server editor and click **Save**.

> Creating it in the wrong folder is the easy mistake. It must sit next to
> `style.css` and `search.js` inside `static/`, not beside `app.py`.

## 3. Replace the five existing files, one at a time

For **each** of files 1, 2, 4, 5 and 6 in the table above:

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

Order does not matter. All six must be done before you reload — a
half-updated site will look broken (new HTML against old CSS).

> The `templates/` files are in the `templates/` folder, not `static/`. Use
> the breadcrumb at the top of the Files tab to move between the two.

## 4. Reload the web app

Editing files changes nothing on the live site until you reload it.

1. Go to the **Web** tab.
2. Click the big green **Reload** button.
3. Wait for the tick.

## 5. Verify it actually worked

Open `https://<your-username>.pythonanywhere.com`. A normal refresh is
enough — the `?v=4` tag means browsers cannot serve you a stale stylesheet
or script.

Walk the six checks:

1. **The login page.** No logo on it any more, and a small **eye icon** sits
   inside the right-hand end of the password box.
2. **Click the eye.** Your typed password becomes readable and the icon gains
   a slash through it. Click again and it hides. The page must **not** submit
   when you click it.
3. **Log in.** The search box now sits in the **middle of an empty page**, under
   the question "Which client's folder?". This is the new layout.
4. **Search a client** — type part of a name. The matches now appear in a
   **single panel hanging directly off the bottom of the box**, not as separate
   floating cards.
5. **Type a full client name and press `Enter`.** Their SharePoint folder
   opens in a new tab. **Type nonsense and press `Enter`** — the box shakes and
   a red line explains why nothing opened. It must **not** open a folder.
6. **Press `Tab` around the page.** Every button, link and the eye icon shows a
   visible purple focus ring.

If all six behave, the update is live.

---

## Troubleshooting

### The eye icon is there but clicking it does nothing

You skipped step 2, or saved `password.js` into the wrong folder. Check the
server actually has it:

    https://<your-username>.pythonanywhere.com/static/password.js?v=4

You should see JavaScript beginning with a `// Password reveal.` comment. A
**404** means the file is missing or is in the wrong directory — it belongs in
`static/`.

### The site looks half-broken, or the old layout is still there

The page now requests `style.css?v=4` and `password.js?v=4`. Because the URL
changed, every browser — yours and your colleagues' — is forced to fetch the
new files. Nobody needs to hard-refresh. That is the whole point of the tag.

So if the site still looks wrong, suspect a **failed paste**, not a cache.
Check what the server is actually holding:

    https://<your-username>.pythonanywhere.com/static/style.css?v=4

If you see `--radius: 12px` and a `button.reveal` rule, the server has the new
file. If not, that paste didn't save — reopen it on the Files tab, confirm the
contents, Save, and Reload.

Then view the page source (`Ctrl+U`) and check the stylesheet link really
says `?v=4`. If it says plain `style.css` with no tag, you copied the
templates but **not `app.py`** — go back and do that one too.

### "Something went wrong" / 502 error page

The app crashed on startup. This update touched one line of Python
(`ASSET_VERSION`), so the likeliest cause is still a mangled paste in a
template. Get the real error:

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
    git show 7b23560:static/style.css

That prints the pre-redesign contents of that file (swap in whichever path
you need — `7b23560` is the commit the live site was running before this
update). Copy the output, paste it into the server's editor, Save, Reload.

`static/password.js` has no previous version — it is new. To undo it, delete
it on the Files tab; nothing else references it once the old templates are
back.

The commits in this update are:

- `71a4708` — three redesign directions as standalone mockups (design only, not deployed)
- `6eb9c85` — the command-bar layout and the password reveal toggle
- `4577dec` — merge into `master`

---

## Next time you change the CSS or the JS

**Bump `ASSET_VERSION` in `app.py` before you deploy.**

    ASSET_VERSION = "4"    ->    ASSET_VERSION = "5"

That one number is what forces every staff browser to fetch the new
stylesheet and scripts. Change `style.css`, `search.js` or `password.js`
without bumping it and your colleagues keep running the old files — the site
will look unchanged to them and correct to you, which is a miserable thing to
debug.

Only that one line needs editing; the templates read it automatically. If a
deploy touches none of the CSS or JS, leave the number alone.

## This route gets painful — a note for next time

Hand-copying six files is fine once. It does not scale, and every manual
paste is a chance to ship a half-file. This update made that worse: it added
a **new** file, and "create this one, overwrite those five" is exactly the
kind of instruction that gets half-followed.

The better loop is the git one: push your commits to a **private** GitHub
repo, then on the server run `git pull` and hit Reload. Two commands, no
copy-paste, no new-file trap, and the server's code provably matches your
machine's. That path is already written up in
[DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md) §1(a) and
"Maintenance".

This repo currently has **no git remote**, so that route needs a private
GitHub repo creating first. Say the word and I'll walk you through it.
