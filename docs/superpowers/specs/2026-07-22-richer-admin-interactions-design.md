# Richer admin interactions (toasts, modal, better forms) — design

**Date:** 2026-07-22
**Scope:** `static/` (new JS + CSS), `templates/` (admin, login, index).
No new dependencies, no build step, CSP unchanged.

## Goal

Add three richer interactions to the app — **toasts**, a **modal** for the
destructive confirm, and a **better upload form** — using native browser
primitives only. No React, no HeroUI, no bundler. The evaluated alternative
(React + HeroUI) was rejected: for these three specific interactions, native
`<dialog>` + a small toast helper deliver the same UX with none of the
toolchain, CSP-rewrite, or deploy-pipeline cost.

## Principle: progressive enhancement, not a rewrite

The Flask server keeps owning all rendering and logic. The new JS only
*presents* what the server already produces — it never re-implements the diff
rendering or the POST flow in the browser. Consequences:

- No duplication of Jinja logic in JavaScript.
- Every path works with JavaScript disabled: `<dialog>` renders as a normal
  inline card, forms POST, server-rendered errors show.
- The admin flow committed earlier (upload → preview → confirm/result,
  server-rendered, full-page POSTs) is unchanged on the server.

## Current state (reference)

`templates/admin.html` is a three-state server-rendered page inside one
`.card`:
- **upload** (`else` branch, ~lines 77–118): file input + admin password + a
  "Review changes" submit.
- **preview** (`elif preview`, ~lines 35–75): review copy, optional
  `details.danger-block` (dropped clients), optional missing-links `details`,
  and a `.btn-row` with two forms — `action=confirm` (with hidden token) and
  `action=cancel`.
- **result** (`if result`, ~lines 20–33): "Client list replaced" panel with
  optional missing-links list.

`app.py /admin` handles `action` = preview (default) / confirm / cancel.
Errors are set into `error` and rendered as `<p class="error" role="alert">`.
`templates/login.html` renders a wrong-password `<p class="error">`.
`static/search.js` fetches results and already has a catch branch for network
failure.

## Components

### 1. Toasts — `static/toast.js` + CSS

**Module** exposes a single global `window.toast(msg, level)`:
- `level ∈ {"success", "error", "info"}` (default `"info"`).
- Lazily creates one `.toast-container` appended to `<body>`.
  Container has `aria-live="polite"`; for `level === "error"` the individual
  toast node carries `role="alert"` (assertive) so errors interrupt.
- Each toast: message text + a dismiss `×` button (`aria-label="Dismiss"`).
  Auto-dismisses after 5000 ms; hovering pauses the timer; dismiss button
  removes immediately. Multiple toasts stack vertically.
- Animation: slide+fade in/out. Under `@media (prefers-reduced-motion:
  reduce)`, fade only, no transform.

Toasts fire only for **transient positive/neutral feedback** — never for
errors. Errors are form-validation state: they must persist, and the app
already renders them inline (`<p class="error" role="alert">` on login and
admin; a rich `stateRow` with retry guidance in `search.js`). A toast that
vanishes after 5 s would be strictly worse there, so all inline error rendering
stays exactly as-is and unchanged.

**Two flash sources, both read by `toast.js` on load:**

1. **Server flash element** (success). On the admin **result** page the
   template renders, just before its scripts:
   ```html
   <div id="flash" data-level="success"
        data-msg="Client list replaced — {{ result.count }} clients now live." hidden></div>
   ```
   `toast.js` reads `#flash` (if present and `data-msg` non-empty), calls
   `toast(msg, level)`, then removes the node. No inline script (CSP
   `script-src 'self'`). This is additive: the persistent result panel still
   renders the missing-links list.

2. **Client one-shot** (cancel). The admin **Cancel** button's handler in
   `modal.js` sets `sessionStorage["toast-pending"]` to
   `{"msg":"Upload cancelled — nothing was changed.","level":"info"}` before
   its form POSTs. After the redirect back to the upload form, `toast.js`
   reads and clears that key and pops the toast. No server change for cancel.

`toast.js` checks the server `#flash` first, then `sessionStorage`.

**Not applied to:** form errors (stay inline, unchanged) and the
missing/dropped **lists** (content you must read — stay as persistent panels).

### 2. Modal — `static/modal.js` + CSS

The **preview** state renders its card inside
`<dialog class="modal" id="preview-modal">`. `modal.js`:
- On load, if `#preview-modal` exists, calls `.showModal()` → native
  focus-trap, `Esc`-to-close, inert background, native `::backdrop`.
- Moves initial focus to the **Cancel** button (safe default for a
  destructive action), not the red Confirm.
- Backdrop click closes the dialog (treated as cancel — see below).
- Closing via `Esc`/backdrop/Cancel button also submits the `cancel` form (or
  navigates to `url_for('admin')`) so the server discards the pending token.
  The Cancel button closes the dialog immediately for snappiness, then its
  `<form action=cancel>` POST proceeds.

Confirm and Cancel remain real `<form method="post">` POSTs with unchanged
server logic. With JS off, `<dialog>` without `open` would be hidden — so the
template renders the dialog with the `open` attribute by default and
`modal.js` upgrades it: it removes `open` and calls `showModal()` for the
true modal behavior. JS-off users see the preview as a normal inline card.

The `details.danger-block` dropped-clients list keeps its existing
`max-height`/scroll inside the modal body.

### 3. Better upload form — `static/upload.js` + CSS

Enhance the **upload** state form:
- **Drop zone**: the file input is wrapped in a `<label class="dropzone">`.
  `dragover`/`dragenter` add `.dropzone--over`; `drop` sets
  `input.files = e.dataTransfer.files` and fires the change handler. Clicking
  the label opens the picker (native label behavior).
- **Filename + validation**: on `change`, show the chosen filename and size.
  Validate client-side: extension must be `.xlsx` and size ≤ 10 MB. Show
  inline "✓ Ready to upload" or "✗ Not an .xlsx file" / "✗ File too large
  (max 10 MB)". This is early feedback only — server validation
  (`parse_xlsx` / `ParseError`) remains authoritative.
- **Loading state**: on form `submit`, disable the submit button and set its
  text to "Working…" so a slow parse does not appear frozen. Re-enable is
  moot (page navigates on response).

With JS off, the plain `<input type="file" required>` and submit work as they
do today.

## File structure

- Create `static/toast.js` — toast helper + flash reader (server `#flash`
  then `sessionStorage["toast-pending"]`). Loaded on **admin only** (the only
  page that fires toasts).
- Create `static/modal.js` — preview dialog controller + Cancel one-shot
  toast flag. Admin only.
- Create `static/upload.js` — dropzone + validation + loading. Admin only.
- Modify `static/style.css` — add `.toast`, `.toast-container`,
  `dialog.modal` + `::backdrop`, `.dropzone` (+ `--over`, valid/invalid
  states). Reuse existing tokens (`--danger`, `--accent`, `--surface`,
  `--radius`, `--dur`, `--ease-out`, `--ok-ink`/`--ok-bg`/`--ok-line`) and the
  existing reduced-motion block.
- Modify `templates/admin.html`:
  - result state → render the `#flash` success element.
  - upload form → dropzone markup + filename/validation slots.
  - preview card → wrapped in `<dialog class="modal" open>`.
  - include `toast.js`, `modal.js`, `upload.js` (keep `password.js`).
  - inline `.error` rendering stays exactly as-is.
- **No change** to `templates/login.html`, `templates/index.html`, or
  `static/search.js` — their inline error handling is already correct, and
  toasts do not apply there.
- Modify `app.py` — **bump `ASSET_VERSION` only**. No logic change: the
  success toast rides the already-server-rendered result page; cancel is
  client-side.

Each JS file has one responsibility and is small enough to reason about
whole. All three load on admin only; no other page changes.

## Error handling & fallback

- **JS disabled**: dialog renders inline (`open`), forms POST, errors render
  inline exactly as today (error rendering is server-side and untouched, so
  there is no double-messaging to reconcile). The success `#flash` element is
  `hidden`, so JS-off users simply don't get the extra success toast — the
  result panel already states the outcome.
- **`<dialog>` unsupported** (very old browsers): `showModal` absent →
  `modal.js` no-ops, card shows inline. Acceptable.
- **Toast never blocks**: purely additive; failure to toast never breaks a
  form submit. `sessionStorage` access is wrapped in try/catch (may be
  disabled) — the cancel toast is silently skipped if unavailable.

## Testing

- **Server**: `app.py` change is a one-line `ASSET_VERSION` bump — no route
  logic changes. The existing pytest suite (`tests/`, 24 passing — routes,
  auth, admin preview/confirm) must stay green unchanged. No new server tests
  needed (no server behavior added).
- **JS**: DOM-only, no JS test harness in the repo. Verification is manual
  browser, documented step-by-step in the implementation plan — consistent
  with how the app's other CSS/JS is verified.
- **a11y**: native `<dialog>` focus-trap + `Esc`; toast container `aria-live`
  (polite); `prefers-reduced-motion` honored; dropzone reachable by keyboard
  via the wrapped `<label for>`/input. Inline errors keep their existing
  `role="alert"`.

## Deploy note

Per project convention: bump `ASSET_VERSION` (templates + static change) so
`v=asset_v` cache-busts. HTML template edits need a server Reload (templates
cached, `debug=False`); CSS/JS refresh via the version bump. Deploy =
`git pull` + Reload on PythonAnywhere.

## Rejected alternatives

- **React + HeroUI islands / SPA.** Requires Vite build, bundling into
  `static/`, a build step every deploy, CSP reconsideration, and rewriting
  admin.html (and possibly index.html) as components — a stack migration to
  gain toasts/modals/forms that native primitives already provide. HeroUI
  would earn its cost for heavy widgets (async comboboxes, data grids, date
  pickers), which are out of scope. Rejected.
- **Full AJAX preview** (fetch preview, render modal client-side, fetch
  confirm). Would duplicate the Jinja diff-rendering in JS. Rejected in favour
  of modal-on-load progressive enhancement, which keeps the server as the
  single source of rendering.
