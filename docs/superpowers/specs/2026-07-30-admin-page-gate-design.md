# Admin-Password Gate on /admin — Design

**Date:** 2026-07-30
**Status:** Approved, ready for implementation plan

## Problem

Today any logged-in staff member can open `/admin` — the page that replaces the
entire client list. The admin password (`ADMIN_PASSWORD`) is only checked at the
moment of upload, not to view the page. The owner wants the admin *page itself*
gated: a staffer must enter the admin password before reaching `/admin`.

## Goal

Require the admin password to view `/admin` (and all its actions). Once entered,
admin access lasts the whole session (until logout). Remove the now-redundant
admin-password prompt from the upload step.

## Decisions (from brainstorming)

- **Whole-session unlock.** Enter the admin password once → `session["admin"]`
  stays true until logout. No re-prompt, no idle timeout.
- **Drop the upload-time password.** Viewing `/admin` already requires the
  password, so re-typing it to upload is redundant — remove that field and its
  server check.
- **No per-user admin role.** `ADMIN_PASSWORD` is a shared secret; "admin" means
  "knows the admin password", exactly as today. No accounts/roles are added.

## Architecture

A second session gate layered on top of the existing staff-login gate.

### 1. `@admin_required` decorator (`app.py`)

Mirrors `staff_required`. Requires **both** `session["staff"]` and
`session["admin"]`:

- no `session["staff"]` → redirect to `/login` (or 401 JSON for `/api/` paths,
  matching `staff_required`'s existing behaviour).
- staff but no `session["admin"]` → redirect to `/admin/unlock`.
- both present → run the view.

Admin implies staff (staff checked first), so `/admin` never needs both
decorators — `@admin_required` alone replaces `@staff_required` on that route.

### 2. `/admin/unlock` route (`app.py`)

```
GET  -> render admin_unlock.html (password form)
POST -> hmac.compare_digest(form["password"], ADMIN_PASSWORD)
        correct  -> session["admin"] = True; redirect to /admin
        wrong    -> re-render with error
```

- Decorated `@staff_required` (must be logged in as staff before unlocking admin;
  a stranger can't reach the unlock form).
- Rate-limited `@limiter.limit("10 per 15 minutes", methods=["POST"])`, same as
  `/login`.
- Constant-time comparison (`hmac.compare_digest`), same as the current
  upload-password check and `/login`.

### 3. `/admin` route changes (`app.py`)

- Swap `@staff_required` → `@admin_required`. This one change gates **GET, the
  upload preview/confirm/cancel POSTs, and the link-health `check_links` POST** —
  the whole page and all its actions.
- **Delete** the `admin_password` check in the preview branch (currently
  `app.py:168-170`, the `if not hmac.compare_digest(request.form.get("admin_password", ...))`
  guard). The page gate replaces it. The preview branch proceeds straight to
  `file = request.files.get("file")`.
- The confirm branch's session-bound `token` is CSRF protection, not the
  password — **unchanged**.

### 4. `/logout` (`app.py`)

Already `session.clear()` → drops `admin` alongside `staff`. **No change.**

### 5. Templates

- **New** `templates/admin_unlock.html`: mirrors `login.html` — `<main class="narrow">`,
  a `.card`, one password field with the reveal-eye button and `password.js`,
  heading "Unlock admin", sub-text explaining the admin password is needed, and
  an error slot (`role="alert"`). Submit button "Unlock admin".
- **Edit** `templates/admin.html`: remove the admin-password field block from the
  upload form — the `<label for="admin_password">`, the `.field` wrapper with the
  `admin_password` input, and its reveal-eye `<button>`. The upload form becomes
  file dropzone + `file-info` + "Review changes". Leave everything else
  (preview modal, result panel, link-health section) untouched.

## Data flow

```
staff logs in (/login, STAFF_PASSWORD)      -> session["staff"] = True
clicks "Admin" (not yet unlocked)           -> @admin_required -> redirect /admin/unlock
enters ADMIN_PASSWORD (/admin/unlock POST)  -> session["admin"] = True -> redirect /admin
/admin now open all session (GET + uploads + link-health) until /logout
/logout -> session.clear() -> both flags gone
```

## Error handling / edge cases

- Wrong admin password on unlock → re-render unlock page with error, no flag set,
  rate-limited after repeated attempts.
- Direct GET/POST to `/admin` or `/admin/unlock` while not staff-logged-in →
  `/login` (staff gate runs first).
- Non-HTML `/api/` paths are unaffected (they use `@staff_required`, not admin).
- Deep-link to `/admin` while staff-but-not-admin → unlock page (not a 403 dead
  end); after unlock, redirect lands on `/admin`.

## Testing (pytest, existing suite — no new runner, no JS tests)

**Fixture change (`tests/conftest.py`):** the existing `logged_in` fixture is
staff-only; add an **`admin` fixture** that depends on `logged_in` and POSTs
`/admin/unlock` with the test `ADMIN_PASSWORD` ("adminpw", already set in
conftest). Repoint the existing admin tests (`tests/test_admin.py`) that GET/POST
`/admin` from `logged_in` to `admin`, since they now redirect to unlock otherwise.

**New tests:**
- GET `/admin` as staff-not-admin → 302 to `/admin/unlock`.
- GET `/admin/unlock` as staff → 200, shows the form.
- POST `/admin/unlock` correct password → sets `session["admin"]`, redirect to
  `/admin`, and a subsequent GET `/admin` → 200.
- POST `/admin/unlock` wrong password → re-render with error, no admin access.
- GET/POST `/admin/unlock` while not logged in as staff → redirect `/login`.
- Upload flow works through the `admin` fixture with **no** `admin_password` in
  the form data (proves the field/check are gone).
- `/logout` then GET `/admin` → redirect (admin flag cleared).

**Update existing tests:** `test_wrong_admin_password_rejected` (upload with wrong
password) no longer applies to the upload step — replace it with the unlock-page
wrong-password test above. Any admin test posting `admin_password` in form data
drops that key.

## Non-goals

- No per-user admin accounts or roles.
- No idle timeout / re-prompt (whole-session was chosen).
- No change to the staff-login flow, the `/api/` gate, or the link-health feature
  beyond it now sitting behind the admin gate.

## Files touched

- `app.py` — `admin_required` decorator, `/admin/unlock` route, `/admin`
  decorator swap + delete upload-password check.
- `templates/admin_unlock.html` — new.
- `templates/admin.html` — remove upload-password field.
- `tests/conftest.py` — `admin` fixture.
- `tests/test_admin.py` — repoint to `admin` fixture, swap the wrong-password
  test, add unlock tests.

No `ASSET_VERSION` bump needed (no CSS/JS change — `admin_unlock.html` reuses
existing `style.css`/`password.js`).
