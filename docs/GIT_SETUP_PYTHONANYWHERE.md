# One-time: put the live PythonAnywhere site on git

Do this **once**. Afterwards, every deploy is `git pull` + Reload, and the
six-file hand-copy in [UPDATE_PYTHONANYWHERE.md](UPDATE_PYTHONANYWHERE.md)
is obsolete.

Repo: `https://github.com/Ansh-BS/Client-Sharepoint-Search.git` (private).

Throughout, replace `<project>` with the folder on the server holding `app.py`
(e.g. `sharepoint-search`).

---

## What makes this fiddly

Two facts shape every step below.

1. **PythonAnywhere free accounts block outbound SSH.** The usual GitHub
   "deploy key" route needs port 22 and will not work. It has to be HTTPS with
   a token.

2. **The live folder is not a git repo, and it holds two files that exist
   nowhere else:**
   - `.env` — `SECRET_KEY`, `STAFF_PASSWORD`, `ADMIN_PASSWORD`
   - `data/clients.json` — the real client list, with every SharePoint URL

   Both are gitignored, so they are **not** on GitHub and never will be. That
   is deliberate: it is why the repo is safe. It also means the server's copy
   is the only copy. Everything below is built around not touching them.

---

## Step 1 — make a read-only token

On GitHub: **Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token**.

| Field | Value |
|---|---|
| Name | `pythonanywhere-deploy` |
| Repository access | **Only select repositories** → `Client-Sharepoint-Search` |
| Permissions → Repository → **Contents** | **Read-only** |
| Expiration | your choice — **write the date down** |

Read-only is the point: the server only ever needs to *pull*. If this token
ever leaks, it cannot rewrite your code or reach any other repo.

GitHub shows the token **once**. Copy it now.

> When the token expires, `git pull` on the server starts failing with an
> authentication error. That is the cause — generate a new token and re-run
> Step 3's `git fetch` to re-enter it.

## Step 2 — back up the two irreplaceable files

Open a **Bash console** (Consoles tab):

```bash
cd ~
cp <project>/.env  env-backup-$(date +%F)
cp <project>/data/clients.json  clients-backup-$(date +%F).json
ls -la env-backup-* clients-backup-*
```

**Do not skip this.** Every other step is recoverable from GitHub. These two
files are not — losing `.env` takes the site down, losing `clients.json` means
re-uploading the spreadsheet through `/admin`.

## Step 3 — turn the live folder into a git working copy

```bash
cd ~/<project>
git init
git remote add origin https://github.com/Ansh-BS/Client-Sharepoint-Search.git
git fetch origin
```

It will ask for credentials:

- **Username:** `Ansh-BS`
- **Password:** paste the **token** from Step 1 — *not* your GitHub password.
  GitHub stopped accepting passwords over git in 2021; it will simply fail.

Now adopt the repo's state:

```bash
git reset --hard origin/main
git branch -M main
git branch --set-upstream-to=origin/main main
```

**What `git reset --hard` actually does here**, because the name is alarming:
it overwrites every file git *tracks* with GitHub's version — which **is** the
deploy, since the repo holds the new redesign. It leaves **untracked** files
completely alone. `.env` and `data/` are gitignored, therefore untracked,
therefore untouched. That is the whole trick.

It also means any hand-edit made directly on the server, to a tracked file, is
discarded. From now on the repo is the single source of truth — edit on your
PC, commit, push, pull. Never edit code in the PythonAnywhere editor again.

## Step 4 — verify before you reload

```bash
ls -la .env data/clients.json     # both must still exist
git log --oneline -1              # the commit you just pushed
ls static/password.js             # the new file, pulled in automatically
```

If `.env` or `clients.json` is missing: **stop, do not reload.** Restore from
the Step 2 backup:

```bash
cp ~/env-backup-<date>  ~/<project>/.env
cp ~/clients-backup-<date>.json  ~/<project>/data/clients.json
```

## Step 5 — reload and check the site

**Web** tab → green **Reload**. Then walk the checks:

1. **Login page** — no logo, and an eye icon inside the right end of the
   password box.
2. **Click the eye** — the password becomes readable, the icon gains a slash.
   It must not submit the form.
3. **Log in** — the search box sits mid-page under "Which client's folder?".
4. **Type part of a client name** — matches appear in one panel hanging off the
   bottom of the box.
5. **Full name + `Enter`** — folder opens. **Nonsense + `Enter`** — the box
   shakes, a red line explains, and no folder opens.
6. **`Tab` around** — everything gets a visible purple focus ring.

---

## Every deploy from now on

On your PC:

```bash
git add -A
git commit -m "..."
git push
```

On the server (Bash console):

```bash
cd ~/<project> && git pull
```

Then **Web** tab → **Reload**. Done.

Still bump `ASSET_VERSION` in `app.py` whenever you change `style.css`,
`search.js` or `password.js` — git changes the files, but only that number
forces staff browsers to stop using their cached copies.

### Optional: stop retyping the token

```bash
git config credential.helper store
```

The next `git pull` saves the token to `~/.git-credentials` **in plaintext** on
the server. Given it is a read-only, single-repo token, that trade is
reasonable. If you would rather not, leave this off and paste the token each
pull.

---

## Rolling back a bad deploy

The reason this whole setup is worth it. To go back to the previous commit:

```bash
cd ~/<project>
git log --oneline -5          # find the commit you want
git checkout <commit-hash>
```

Then **Reload**. To return to the latest:

```bash
git checkout main && git pull
```

Compare that with the old route, which was pasting old file contents back in
by hand, one file at a time — the same error-prone process that caused the
breakage in the first place.

## If `git pull` fails

**`Authentication failed`** — the token expired, or you typed your GitHub
password instead of the token. Make a new token (Step 1) and re-run
`git fetch origin` to be prompted again.

**`Your local changes would be overwritten`** — someone edited a tracked file
directly on the server. Throw the server-side edit away:

```bash
git reset --hard origin/main
```

(`.env` and `data/` are untracked, so this is safe for them — as in Step 3.)

**Timeout / cannot reach github.com** — free-tier accounts reach the internet
through a proxy whitelist. `github.com` is on it over HTTPS, so this should not
happen; if it does, check you used the `https://` URL and not `git@github.com:`.
