# Admin-Password Gate on /admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require the admin password to view `/admin` (whole-session unlock), and remove the now-redundant admin-password prompt from the upload step.

**Architecture:** A second session gate (`session["admin"]`) layered on the existing staff gate. A new `@admin_required` decorator and an `/admin/unlock` route set it; `/admin` swaps to `@admin_required`, which covers the page and every POST action on it. Then the upload step's own password check and field are removed.

**Tech Stack:** Python 3, Flask, flask-limiter, pytest. No new dependency, no JavaScript.

## Global Constraints

- No new dependency. No new JS. No `ASSET_VERSION` bump (the new template reuses existing `style.css`/`password.js`/`theme.js`).
- `ADMIN_PASSWORD` is a shared secret; no per-user roles. "Admin" = knows the password.
- Constant-time password comparison (`hmac.compare_digest`), matching `/login` and the current upload check.
- Admin implies staff: the admin gate checks `session["staff"]` first (→ `/login`, or 401 JSON for `/api/` paths), then `session["admin"]` (→ `/admin/unlock`).
- Whole-session unlock: `session["admin"]` persists until `/logout` (which already does `session.clear()`), no timeout.
- Test env already sets `ADMIN_PASSWORD="adminpw"`, `STAFF_PASSWORD="staffpw"` in `tests/conftest.py`.

---

## Task 1: Admin gate — decorator, unlock route, template, fixture, test repoint

Add the gate and unlock flow. After this task `/admin` requires staff **and** admin; the upload form and its server-side password check are left untouched (upload is temporarily double-gated — harmless), so all existing upload tests keep passing once repointed to the new `admin` fixture.

**Files:**
- Modify: `app.py` (add `admin_required` after `staff_required` ~line 86; add `admin_unlock` route just before `admin()` ~line 140; change `/admin`'s `@staff_required` → `@admin_required` at `app.py:142`)
- Create: `templates/admin_unlock.html`
- Modify: `tests/conftest.py` (add `admin` fixture after `logged_in` ~line 55)
- Modify: `tests/test_admin.py` (repoint `/admin`-touching tests to `admin`; add unlock tests)

**Interfaces:**
- Consumes: existing `session`, `hmac`, `os`, `url_for`, `render_template`, `redirect`, `request`, `jsonify`, `wraps`, `limiter` (all already imported in `app.py`).
- Produces:
  - `admin_required(view)` decorator.
  - `admin_unlock` endpoint at `GET/POST /admin/unlock`.
  - `admin` pytest fixture (staff-logged-in + admin-unlocked test client).

- [ ] **Step 1: Write the failing unlock tests**

Add to `tests/test_admin.py` (after the existing imports at top; `load_clients`/`save_clients` are already imported there):

```python
def test_admin_requires_unlock(logged_in, data_path):
    resp = logged_in.get("/admin")
    assert resp.status_code == 302
    assert "/admin/unlock" in resp.headers["Location"]


def test_unlock_page_shown_to_staff(logged_in):
    resp = logged_in.get("/admin/unlock")
    assert resp.status_code == 200
    assert b"Admin password" in resp.data


def test_unlock_correct_password_grants_access(logged_in, data_path):
    resp = logged_in.post("/admin/unlock", data={"password": "adminpw"})
    assert resp.status_code == 302
    assert "/admin" in resp.headers["Location"]
    assert logged_in.get("/admin").status_code == 200


def test_unlock_wrong_password_rejected(logged_in, data_path):
    resp = logged_in.post("/admin/unlock", data={"password": "nope"})
    assert b"Wrong admin password" in resp.data
    assert logged_in.get("/admin").status_code == 302  # still locked


def test_unlock_requires_staff_login(client):
    resp = client.get("/admin/unlock")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_logout_clears_admin(admin, data_path):
    assert admin.get("/admin").status_code == 200
    admin.get("/logout")
    resp = admin.get("/admin")
    assert resp.status_code == 302  # session cleared -> gate redirects
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_admin.py -k "unlock or logout_clears" -v`
Expected: FAIL — `admin` fixture not found / `/admin/unlock` returns 404, and `GET /admin` returns 200 (no gate yet) so `test_admin_requires_unlock` fails.

- [ ] **Step 3: Add the `admin_required` decorator**

In `app.py`, immediately after the `staff_required` function (after its `return wrapped`, ~line 86):

```python
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("staff"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthenticated"}), 401
            return redirect(url_for("login"))
        if not session.get("admin"):
            return redirect(url_for("admin_unlock"))
        return view(*args, **kwargs)
    return wrapped
```

- [ ] **Step 4: Add the `/admin/unlock` route**

In `app.py`, just before the `@app.route("/admin", ...)` line (~line 140):

```python
@app.route("/admin/unlock", methods=["GET", "POST"])
@limiter.limit("10 per 15 minutes", methods=["POST"])
@staff_required
def admin_unlock():
    error = None
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""),
                               os.getenv("ADMIN_PASSWORD")):
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Wrong admin password."
    return render_template("admin_unlock.html", error=error)
```

- [ ] **Step 5: Gate `/admin` with the new decorator**

In `app.py`, change the decorator on the `admin` view (`app.py:142`) from `@staff_required` to `@admin_required`. Leave the `@app.route` and `@limiter.limit` lines above it unchanged.

- [ ] **Step 6: Create the unlock template**

Create `templates/admin_unlock.html` (mirrors `login.html` + a minimal topbar so the staffer can navigate back or log out):

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unlock admin — Client SharePoint Search</title>
<script src="{{ url_for('static', filename='theme.js', v=asset_v) }}"></script>
<link rel="stylesheet" href="{{ url_for('static', filename='style.css', v=asset_v) }}">
</head>
<body>
<header class="topbar topbar-end">
  <nav>
    <a href="{{ url_for('index') }}">Search</a>
    <a href="{{ url_for('logout') }}">Log out</a>
    <button type="button" id="theme-toggle" class="theme-toggle"
            aria-pressed="false">Dark</button>
  </nav>
</header>

<main class="narrow">
  <div class="card">
    <h1>Unlock admin</h1>
    <p class="sub">Enter the admin password to manage the client list. Ask the
      office manager if you don't have it.</p>
    {% if error %}<p class="error" role="alert">{{ error }} Check caps lock and try again.</p>{% endif %}
    <form method="post">
      <label for="password">Admin password</label>
      <div class="field">
        <input id="password" type="password" name="password"
               autocomplete="current-password" autofocus required
               {% if error %}aria-invalid="true"{% endif %}>
        <button type="button" class="reveal" data-for="password"
                aria-pressed="false" aria-label="Show password">
          <svg class="eye" viewBox="0 0 20 20" fill="none" stroke="currentColor"
               stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
               aria-hidden="true">
            <path d="M1.5 10S4.7 4.5 10 4.5 18.5 10 18.5 10 15.3 15.5 10 15.5 1.5 10 1.5 10Z"/>
            <circle cx="10" cy="10" r="2.5"/>
          </svg>
          <svg class="eye-off" viewBox="0 0 20 20" fill="none" stroke="currentColor"
               stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
               aria-hidden="true">
            <path d="M7.8 5A7.9 7.9 0 0 1 10 4.5c5.3 0 8.5 5.5 8.5 5.5a15 15 0 0 1-2.4 3"/>
            <path d="M13.9 13.9A7.6 7.6 0 0 1 10 15.5C4.7 15.5 1.5 10 1.5 10a15 15 0 0 1 3.9-4.3"/>
            <path d="M8.3 8.4a2.5 2.5 0 0 0 3.4 3.4"/>
            <path d="M3 3l14 14"/>
          </svg>
        </button>
      </div>
      <button type="submit">Unlock admin</button>
    </form>
  </div>
</main>
<script src="{{ url_for('static', filename='password.js', v=asset_v) }}"></script>
</body>
</html>
```

- [ ] **Step 7: Add the `admin` fixture**

In `tests/conftest.py`, after the `logged_in` fixture:

```python
@pytest.fixture
def admin(logged_in):
    """Staff-logged-in client that has also unlocked the admin page."""
    logged_in.post("/admin/unlock", data={"password": "adminpw"})
    return logged_in
```

- [ ] **Step 8: Repoint the existing admin tests to the `admin` fixture**

In `tests/test_admin.py`, every test that GETs or POSTs `/admin` currently takes `logged_in`. Replace the `logged_in` parameter with `admin` (and every `logged_in` reference in that test's body with `admin`) for these tests:

`test_wrong_admin_password_rejected`, `test_preview_does_not_modify_data`, `test_confirm_replaces_data_and_reports`, `test_preview_warns_about_dropped_clients`, `test_cancel_discards_preview`, `test_confirm_without_preview_rejected`, `test_bad_file_keeps_existing_data`, `test_no_file_selected`, `test_admin_shows_no_check_yet`, `test_admin_shows_all_ok`, `test_admin_lists_flagged`, `test_button_hidden_when_disabled`, `test_button_shown_when_enabled`, `test_check_links_post_disabled_is_refused`, `test_check_links_post_enabled_runs`.

Do NOT change `test_admin_requires_staff_login` (uses `client`) or the new unlock tests from Step 1 (they intentionally use `logged_in`/`client`/`admin` as written).

The helper functions `preview`, `confirm`, `upload` take the client as their first argument — callers now pass `admin`. Leave the helpers themselves unchanged in this task (they still send `admin_password`, which the still-present upload check accepts).

- [ ] **Step 9: Run the full admin suite**

Run: `python -m pytest tests/test_admin.py -v`
Expected: PASS — the 6 new unlock/logout tests, plus all repointed existing tests (upload still works because the `admin` fixture unlocks and the helpers still send the upload password).

- [ ] **Step 10: Run the whole suite**

Run: `python -m pytest -q`
Expected: all pass (other test files unaffected).

- [ ] **Step 11: Commit**

```bash
git add app.py templates/admin_unlock.html tests/conftest.py tests/test_admin.py
git commit -m "feat: gate /admin behind an admin-password unlock (whole-session)"
```

---

## Task 2: Remove the redundant upload password

Now that viewing `/admin` requires the admin password, drop the upload step's own password field and server check.

**Files:**
- Modify: `app.py` (delete the `admin_password` check in the preview branch, `app.py:192-194`)
- Modify: `templates/admin.html` (remove the admin-password field block, `templates/admin.html:101-123`)
- Modify: `tests/test_admin.py` (update `preview`/`upload` helpers; drop the wrong-password upload test; drop the stray `admin_password` form key; add no-password-needed tests)

**Interfaces:**
- Consumes: the `admin` fixture and unlock route from Task 1.
- Produces: an upload flow that needs no password beyond the page gate.

- [ ] **Step 1: Write the failing tests**

In `tests/test_admin.py`, add:

```python
def test_admin_page_has_no_password_field(admin, data_path):
    resp = admin.get("/admin")
    assert b'name="admin_password"' not in resp.data


def test_upload_needs_no_admin_password(admin, data_path, make_xlsx, tmp_path):
    p = make_xlsx(tmp_path / "new.xlsx", [("N1", "New Client", "https://x")])
    resp = upload(admin, p)
    assert b"Client list replaced" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == ["New Client"]
```

Then update the `preview` and `upload` helpers at the top of the file to send no password:

```python
def preview(client, path):
    """Step 1: upload for review. Returns the response (data NOT yet saved)."""
    with open(path, "rb") as f:
        return client.post(
            "/admin",
            data={"file": (f, "upload.xlsx")},
            content_type="multipart/form-data",
        )


def upload(client, path):
    """Full two-step replace: preview then confirm. Returns the confirm resp."""
    resp = preview(client, path)
    token = _token(resp)
    return confirm(client, token)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_admin.py -k "no_password or needs_no_admin" -v`
Expected: FAIL — the field is still present (`test_admin_page_has_no_password_field` fails), and with the helper now sending no password the still-present server check rejects the upload (`test_upload_needs_no_admin_password` fails with "Wrong admin password").

- [ ] **Step 3: Remove the server-side upload password check**

In `app.py`, the preview branch currently starts (`app.py:191-194`):

```python
        else:  # preview: parse and stash, but change nothing yet
            if not hmac.compare_digest(request.form.get("admin_password", ""),
                                       os.getenv("ADMIN_PASSWORD")):
                error = "Wrong admin password."
            else:
                file = request.files.get("file")
                ...
```

Delete the `if not hmac.compare_digest(...) ... error = "Wrong admin password."` guard and dedent its `else:` body one level, so the branch becomes:

```python
        else:  # preview: parse and stash, but change nothing yet
            file = request.files.get("file")
            if file is None or not file.filename:
                error = "No file selected."
            else:
                ...  # unchanged: parse_xlsx, diff, save_pending, build preview
```

Keep the rest of the branch (the `try/except ParseError`, `_diff_clients`, token minting, `save_pending`, `preview` dict) exactly as-is, only dedented.

- [ ] **Step 4: Remove the password field from the upload form**

In `templates/admin.html`, delete the admin-password block (`templates/admin.html:101-123`): the `<label for="admin_password">Admin password</label>` line, the `<div class="field"> ... </div>` wrapper containing the `admin_password` `<input>` and its `.reveal` `<button>` with the two SVGs. Leave the `<p id="file-info" ...>` line above it and the `<button type="submit">Review changes</button>` below it. The form is now: dropzone label + file input + `file-info` + submit.

- [ ] **Step 5: Drop the obsolete wrong-password test and stray key**

In `tests/test_admin.py`:
- Delete `test_wrong_admin_password_rejected` entirely — the upload no longer checks a password; wrong-password behaviour is now covered by `test_unlock_wrong_password_rejected` (Task 1).
- In `test_no_file_selected`, remove `admin_password` from the posted data so it reads `admin.post("/admin", data={})` (action defaults to preview; no file → "No file selected").

- [ ] **Step 6: Run to verify green**

Run: `python -m pytest tests/test_admin.py -v`
Expected: PASS — new no-password tests pass, upload flow works with no password, deleted test gone.

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add app.py templates/admin.html tests/test_admin.py
git commit -m "feat: drop redundant upload password now that /admin is gated"
```

---

## Post-implementation (not a coding task)

- **Manual smoke test:** `python app.py` → log in (staff) → click Admin → unlock page appears → enter admin password → `/admin` opens → upload form has no password field → log out → Admin prompts for unlock again.
- Deploy is the usual `git pull` + Reload on PythonAnywhere; no new env vars, no `ASSET_VERSION` bump.
- Pushing to origin still needs explicit user OK.

## Self-Review notes

- **Spec coverage:** `admin_required` (Task 1 Step 3), `/admin/unlock` route (Step 4), decorator swap (Step 5), unlock template mirroring login (Step 6), whole-session flag + logout clears it (tests Step 1), drop upload password check + field (Task 2 Steps 3-4), fixture + test repoint (Task 1 Steps 7-8), obsolete test removal (Task 2 Step 5). All spec sections mapped.
- **Type/name consistency:** endpoint `admin_unlock` / `url_for("admin_unlock")` match; `admin` fixture used consistently; `session["admin"]` set in the route and cleared by existing `session.clear()`.
- **No placeholders:** every code step carries full code; the one "…unchanged" region (Task 2 Step 3) explicitly names what stays and only removes/dedents.
