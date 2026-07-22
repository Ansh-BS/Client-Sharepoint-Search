# Richer Admin Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add toasts (success/cancel), a native `<dialog>` modal for the destructive confirm, and a drag-drop/validating upload form to the admin page — using native browser primitives only.

**Architecture:** Progressive enhancement over the existing server-rendered admin flow (upload → preview → result, full-page POSTs). New JS only *presents* what the server renders; forms still POST and work JS-off. Three small admin-only modules: `toast.js`, `modal.js`, `upload.js`. No React, no HeroUI, no bundler.

**Tech Stack:** Flask + Jinja, vanilla JS/CSS, CSP `script-src 'self'` / `default-src 'self'`, no build step.

## Global Constraints

- **No new dependencies, no build step.** Native `<dialog>`, drag-drop API, ARIA-live only. CSP unchanged (external scripts blocked — every script loads from `static/`).
- **Admin-only.** All three JS files load on `templates/admin.html` only. Do NOT modify `templates/login.html`, `templates/index.html`, or `static/search.js` — their inline error handling is already correct.
- **Toasts fire for success + cancel only, never errors.** Inline error rendering (`<p class="error" role="alert">`) stays exactly as-is.
- **Server logic unchanged.** `app.py` gets a one-line `ASSET_VERSION` bump and nothing else. No route/status-code changes.
- **JS-off must still work:** dialog renders inline (`open` attribute), forms POST, errors render server-side.
- **Reuse existing CSS tokens** — `--surface`, `--surface-sunk`, `--ink`, `--muted`, `--border-strong`, `--accent`, `--accent-soft`, `--danger`, `--ok-ink`, `--ok-bg`, `--ok-line`, `--radius`, `--radius-sm`, `--lift`, `--dur`, `--ease-out`, `--sp-2`, `--sp-3`, `--sp-4`, `--sp-6`. Respect the existing `@media (prefers-reduced-motion: reduce)` pattern.
- **Existing pytest suite (24 passing) must stay green.** No JS test harness exists; JS/CSS/HTML verification is manual browser, with the exact steps given per task.
- **`ASSET_VERSION` is currently `"9"`** in `app.py` (bumped to `"10"` in Task 4).

---

### Task 1: Toast system + success toast on confirm

**Files:**
- Create: `static/toast.js`
- Modify: `static/style.css` (append toast rules)
- Modify: `templates/admin.html` (result branch `#flash` + include `toast.js`)
- Test: manual browser

**Interfaces:**
- Produces: global `window.toast(msg, level)` where `level ∈ {"success","info","error"}`; and a loader that, on page load, pops a toast from a server `#flash` element and from `sessionStorage["toast-pending"]`. Later tasks (`modal.js`) rely on the `sessionStorage["toast-pending"]` = `JSON.stringify({msg, level})` contract.

- [ ] **Step 1: Create `static/toast.js`**

```js
// Transient feedback. Loaded on admin only — the one page that fires toasts
// (success on confirm, info on cancel). Errors are NOT toasts: they render
// inline server-side where they persist. CSP is script-src 'self', so server
// -> toast messages arrive via a hidden #flash element, never an inline script.
const AUTO_DISMISS_MS = 5000;

function container() {
  let el = document.getElementById("toast-container");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast-container";
    el.className = "toast-container";
    el.setAttribute("aria-live", "polite");
    document.body.appendChild(el);
  }
  return el;
}

function toast(msg, level = "info") {
  if (!msg) return;
  const node = document.createElement("div");
  node.className = "toast toast--" + level;

  const text = document.createElement("span");
  text.className = "toast__msg";
  text.textContent = msg;
  node.appendChild(text);

  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast__close";
  close.setAttribute("aria-label", "Dismiss");
  close.textContent = "×"; // ×
  node.appendChild(close);

  container().appendChild(node);
  requestAnimationFrame(() => node.classList.add("toast--in"));

  let timer = null;
  const remove = () => {
    node.classList.remove("toast--in");
    node.addEventListener("transitionend", () => node.remove(), { once: true });
    setTimeout(() => node.remove(), 400); // fallback if no transition fires
  };
  const dismiss = () => { if (timer) { clearTimeout(timer); timer = null; } remove(); };
  const arm = () => { timer = setTimeout(dismiss, AUTO_DISMISS_MS); };

  close.addEventListener("click", dismiss);
  node.addEventListener("mouseenter", () => { if (timer) { clearTimeout(timer); timer = null; } });
  node.addEventListener("mouseleave", arm);
  arm();
}
window.toast = toast;

// Source 1: server-rendered success element (present only on the result page).
function readFlash() {
  const el = document.getElementById("flash");
  if (!el) return;
  const msg = el.dataset.msg;
  const level = el.dataset.level || "info";
  el.remove();
  if (msg) toast(msg, level);
}

// Source 2: client one-shot set before navigating (e.g. cancel in modal.js).
function readPending() {
  let raw = null;
  try { raw = sessionStorage.getItem("toast-pending"); } catch (e) { return; }
  if (!raw) return;
  try { sessionStorage.removeItem("toast-pending"); } catch (e) { /* ignore */ }
  try {
    const data = JSON.parse(raw);
    if (data && data.msg) toast(data.msg, data.level || "info");
  } catch (e) { /* malformed, ignore */ }
}

readFlash();
readPending();
```

- [ ] **Step 2: Append toast CSS to `static/style.css`**

Add at the end of the file:

```css
/* -------------------------------------------------------------- toasts */
/* Transient success/info feedback (admin only). Bottom-right stack; the
   container is the aria-live region so messages are announced once. */
.toast-container {
  position: fixed; right: var(--sp-4); bottom: var(--sp-4); z-index: 100;
  display: flex; flex-direction: column; gap: var(--sp-2);
  max-width: min(360px, calc(100vw - 2 * var(--sp-4)));
}
.toast {
  display: flex; align-items: flex-start; gap: var(--sp-3);
  padding: .7rem .8rem; border-radius: var(--radius-sm);
  background: var(--surface); color: var(--ink);
  border: 1px solid var(--border-strong); box-shadow: var(--lift);
  font-size: .9375rem;
  opacity: 0; transform: translateY(8px);
  transition: opacity var(--dur) var(--ease-out),
              transform var(--dur) var(--ease-out);
}
.toast--in { opacity: 1; transform: none; }
.toast--success { background: var(--ok-bg); color: var(--ok-ink); border-color: var(--ok-line); }
.toast__msg { flex: 1; }
/* Override the global full-width primary button for this inline dismiss. */
.toast__close {
  width: auto; min-height: 0; margin: 0; padding: 0 .2rem;
  background: none; border: 0; color: inherit;
  font-size: 1.15rem; line-height: 1; cursor: pointer; opacity: .7;
}
.toast__close:hover { background: none; opacity: 1; }
@media (prefers-reduced-motion: reduce) {
  .toast { transform: none; transition: opacity var(--dur) var(--ease-out); }
  .toast--in { transform: none; }
}
```

- [ ] **Step 3: Add the success `#flash` element to the result branch of `templates/admin.html`**

In the `{% if result %}` branch, immediately after the opening `<h1>Client list replaced</h1>` line (line ~22), add:

```html
    <div id="flash" data-level="success"
         data-msg="Client list replaced — {{ result.count }} client{{ '' if result.count == 1 else 's' }} now live." hidden></div>
```

- [ ] **Step 4: Include `toast.js` in `templates/admin.html`**

Change the script block at the bottom (currently just `password.js`) to add `toast.js` after it:

```html
<script src="{{ url_for('static', filename='password.js', v=asset_v) }}"></script>
<script src="{{ url_for('static', filename='toast.js', v=asset_v) }}"></script>
```

- [ ] **Step 5: Manual browser verification**

Run `python app.py`, log in, go to `/admin`. Upload a valid `.xlsx`, click "Review changes" to reach preview, then click "Replace list…".
Expected: on the "Client list replaced" page, a **success toast** slides in bottom-right ("Client list replaced — N clients now live."), auto-dismisses after ~5 s, pauses on hover, and closes immediately on the `×`. The result panel (missing list) still renders normally.

- [ ] **Step 6: Commit**

```bash
git add static/toast.js static/style.css templates/admin.html
git commit -m "feat: toast system + success toast on client-list replace"
```

---

### Task 2: Preview modal + cancel toast

**Files:**
- Create: `static/modal.js`
- Modify: `templates/admin.html` (restructure so the preview branch is a `<dialog>`, add `data-role` hooks, include `modal.js`)
- Modify: `static/style.css` (append `dialog.modal` rules)
- Test: manual browser

**Interfaces:**
- Consumes: the `sessionStorage["toast-pending"]` = `JSON.stringify({msg, level})` contract from Task 1 (`toast.js` reads it on the next page load).
- Consumes markup hooks (added this task): `#preview-modal`, a cancel `<form data-role="cancel-form">`, and a cancel `<button data-role="cancel">`.

- [ ] **Step 1: Restructure `templates/admin.html` so the preview is a dialog**

Currently the three states all live inside one `<main><div class="card"> … </div></main>`. Change `<main>` so the **preview** state is a `<dialog>` (styled as a card) and the other states keep the `.card` wrapper. Replace the whole `<main> … </main>` block with:

```html
<main>
{% if preview %}
  {# --- review before committing (modal) --------------------------- #}
  <dialog class="modal card" id="preview-modal" open>
    <h1>Review before replacing</h1>
    <p class="sub"><strong>Nothing has changed yet.</strong> This is what the upload
      will do to the live list. Confirm to apply it.</p>

    <p class="review-line">Replaces the current <strong>{{ preview.current_count }}</strong>
      client{{ '' if preview.current_count == 1 else 's' }} with
      <strong>{{ preview.count }}</strong> from the new file{% if preview.added %},
      <strong>{{ preview.added|length }}</strong> of them new{% endif %}.</p>

    {% if preview.dropped %}
      <details open class="danger-block">
        <summary>{{ preview.dropped|length }} client{{ '' if preview.dropped|length == 1 else 's' }} will stop being findable</summary>
        <p>{{ 'This client is' if preview.dropped|length == 1 else 'These clients are' }} in the current
          list but not the new file. After replacing, searching for
          {{ 'them' if preview.dropped|length != 1 else 'this name' }} returns nothing.</p>
        <ul>{% for name in preview.dropped %}<li>{{ name }}</li>{% endfor %}</ul>
      </details>
    {% endif %}

    {% if preview.missing %}
      <details{% if not preview.dropped %} open{% endif %}>
        <summary>{{ preview.missing|length }} client{{ '' if preview.missing|length == 1 else 's' }} with no SharePoint link</summary>
        <p>They stay searchable, but show “No link on file” until a URL is added
          to the spreadsheet.</p>
        <ul>{% for name in preview.missing %}<li>{{ name }}</li>{% endfor %}</ul>
      </details>
    {% endif %}

    <div class="btn-row">
      <form method="post">
        <input type="hidden" name="action" value="confirm">
        <input type="hidden" name="token" value="{{ preview.token }}">
        <button type="submit">Replace list with {{ preview.count }} client{{ '' if preview.count == 1 else 's' }}</button>
      </form>
      <form method="post" data-role="cancel-form">
        <input type="hidden" name="action" value="cancel">
        <button type="submit" class="secondary" data-role="cancel">Cancel</button>
      </form>
    </div>
  </dialog>

{% else %}
  <div class="card">
  {% if result %}
    {# --- committed --------------------------------------------------- #}
    <h1>Client list replaced</h1>
    <div id="flash" data-level="success"
         data-msg="Client list replaced — {{ result.count }} client{{ '' if result.count == 1 else 's' }} now live." hidden></div>
    <p class="ok" role="status">{{ result.count }} clients imported. The search box is
      live with the new list.</p>
    {% if result.missing %}
      <details open>
        <summary>{{ result.missing|length }} client{{ '' if result.missing|length == 1 else 's' }} with no SharePoint link</summary>
        <p>They stay searchable, but show “No link on file” until a URL is added
          to the spreadsheet.</p>
        <ul>{% for name in result.missing %}<li>{{ name }}</li>{% endfor %}</ul>
      </details>
    {% endif %}
    <p class="hint"><a href="{{ url_for('admin') }}">Upload another spreadsheet</a></p>

  {% else %}
    {# --- upload form ------------------------------------------------- #}
    <h1>Replace the client list</h1>
    <p class="sub">Upload the SharePoint links spreadsheet. It replaces the current
      list outright — you'll see exactly what changes before anything is saved.</p>

    {% if error %}<p class="error" role="alert">{{ error }}</p>{% endif %}

    <form method="post" enctype="multipart/form-data">
      <label for="file">Spreadsheet (.xlsx)</label>
      <input id="file" type="file" name="file" accept=".xlsx" required>

      <label for="admin_password">Admin password</label>
      <div class="field">
        <input id="admin_password" type="password" name="admin_password"
               autocomplete="current-password" required>
        <button type="button" class="reveal" data-for="admin_password"
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

      <button type="submit">Review changes</button>
    </form>

    <p class="hint">Expected layout: first sheet — column A Client ID,
      column B client name, column C cell whose hyperlink is the SharePoint
      folder. Header row is ignored.</p>
  {% endif %}
  </div>
{% endif %}
</main>
```

Note: this folds in Task 1's `#flash` element (Step 3 already added it; keep it here). The upload form is unchanged from current — Task 3 restructures it.

- [ ] **Step 2: Create `static/modal.js`**

```js
// Preview modal. The server renders the review card as <dialog open> so it
// works with JS off (an in-flow card). Here we upgrade it to a true modal:
// drop `open`, call showModal() for focus-trap, backdrop, and Esc handling.
//
// In the preview state the dialog is the ONLY thing on the page (the upload
// form is not rendered). So closing must not just hide the dialog — that would
// reveal a blank page. Esc and backdrop clicks route through the server cancel
// form, which navigates back to the upload form.
const dialog = document.getElementById("preview-modal");

function queueCancelToast() {
  try {
    sessionStorage.setItem("toast-pending",
      JSON.stringify({ msg: "Upload cancelled — nothing was changed.", level: "info" }));
  } catch (e) { /* storage disabled: skip the toast, cancel still works */ }
}

if (dialog && typeof dialog.showModal === "function") {
  const cancelForm = dialog.querySelector('form[data-role="cancel-form"]');
  const cancelBtn = dialog.querySelector('[data-role="cancel"]');

  dialog.removeAttribute("open");
  dialog.showModal();

  // Safe default focus: Cancel, not the destructive Replace.
  if (cancelBtn) cancelBtn.focus();

  function doCancel() {
    queueCancelToast();
    if (cancelForm) cancelForm.submit(); // navigates; dialog stays until then
  }

  // Cancel button submits its own form; just queue the toast alongside it.
  if (cancelForm) cancelForm.addEventListener("submit", queueCancelToast);

  // Esc fires the dialog 'cancel' event. Prevent the instant close (blank page)
  // and route through the server cancel instead.
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); doCancel(); });

  // Backdrop click = a click landing on the dialog element itself.
  dialog.addEventListener("click", (e) => { if (e.target === dialog) doCancel(); });
}
```

- [ ] **Step 3: Append modal CSS to `static/style.css`**

```css
/* --------------------------------------------------------------- modal */
/* The preview dialog. Also carries .card, so background/border/radius/shadow/
   padding come from .card; here we only size it and dim the backdrop. When
   shown via showModal() the browser centres it in the top layer. */
dialog.modal {
  max-width: 32rem; width: calc(100vw - 2 * var(--sp-4));
  color: var(--ink); /* dialog UA default colour is canvastext */
}
dialog.modal::backdrop { background: rgba(0, 0, 0, .55); }
```

- [ ] **Step 4: Include `modal.js` in `templates/admin.html`**

Add after the `toast.js` include:

```html
<script src="{{ url_for('static', filename='modal.js', v=asset_v) }}"></script>
```

- [ ] **Step 5: Manual browser verification**

Reach the preview state (upload valid `.xlsx` + admin password → "Review changes").
Expected:
1. Preview renders as a **centred modal** over a dimmed backdrop; focus is on **Cancel**.
2. **Confirm** ("Replace list…") still replaces the list and shows the result page + success toast (Task 1).
3. **Cancel** button returns to the upload form and shows an info toast "Upload cancelled — nothing was changed."
4. **Esc** does the same as Cancel (back to upload form + toast), not a blank page.
5. **Backdrop click** does the same.
6. JS-off check (disable JS, reach preview via form POST): the review card renders inline (not a blank page), Confirm/Cancel still POST and work.

- [ ] **Step 6: Commit**

```bash
git add static/modal.js static/style.css templates/admin.html
git commit -m "feat: preview confirm/cancel as a native <dialog> modal + cancel toast"
```

---

### Task 3: Better upload form (dropzone + validation + loading)

**Files:**
- Create: `static/upload.js`
- Modify: `templates/admin.html` (upload branch → dropzone markup + file-info + `data-role="upload-form"`; include `upload.js`)
- Modify: `static/style.css` (append `.dropzone` / `.file-info` rules)
- Test: manual browser

**Interfaces:**
- Consumes markup hooks (added this task): `form[data-role="upload-form"]`, `#file`, `.dropzone`, `#file-info`.

- [ ] **Step 1: Replace the upload form markup in `templates/admin.html`**

In the upload branch (the innermost `{% else %}`), replace the current form block:

```html
    <form method="post" enctype="multipart/form-data">
      <label for="file">Spreadsheet (.xlsx)</label>
      <input id="file" type="file" name="file" accept=".xlsx" required>

      <label for="admin_password">Admin password</label>
```

with (note `data-role="upload-form"`, the `.dropzone` label wrapping the input, and the `#file-info` line):

```html
    <form method="post" enctype="multipart/form-data" data-role="upload-form">
      <label class="dropzone" for="file">
        <span class="dropzone__label">Spreadsheet (.xlsx)</span>
        <span class="dropzone__hint">Drag the file here, or click to choose</span>
        <input id="file" type="file" name="file" accept=".xlsx" required>
      </label>
      <p id="file-info" class="file-info" role="status" aria-live="polite"></p>

      <label for="admin_password">Admin password</label>
```

Leave the rest of the form (the `.field` password block and the "Review changes" submit button) unchanged.

- [ ] **Step 2: Create `static/upload.js`**

```js
// Upload form enhancement: drag-drop, client-side validation (early feedback
// only — parse_xlsx on the server stays authoritative), and a submit loading
// state so a slow parse doesn't look frozen. All no-ops if the form is absent
// (i.e. on the preview/result states).
const MAX_BYTES = 10 * 1024 * 1024; // 10 MB

const form = document.querySelector('form[data-role="upload-form"]');
const input = document.getElementById("file");
const zone = document.querySelector(".dropzone");
const info = document.getElementById("file-info");
const submitBtn = form ? form.querySelector('button[type="submit"]') : null;

function humanSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function describe() {
  info.className = "file-info";
  const file = input.files && input.files[0];
  if (!file) { info.textContent = ""; return; }
  if (!/\.xlsx$/i.test(file.name)) {
    info.textContent = "✗ Not an .xlsx file: " + file.name;
    info.classList.add("file-info--bad");
    return;
  }
  if (file.size > MAX_BYTES) {
    info.textContent = "✗ Too large (" + humanSize(file.size) + ", max 10 MB): " + file.name;
    info.classList.add("file-info--bad");
    return;
  }
  info.textContent = "✓ Ready: " + file.name + " (" + humanSize(file.size) + ")";
  info.classList.add("file-info--ok");
}

if (form && input && zone && info) {
  input.addEventListener("change", describe);

  ["dragenter", "dragover"].forEach((ev) =>
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      zone.classList.add("dropzone--over");
    }));
  ["dragleave", "drop"].forEach((ev) =>
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      zone.classList.remove("dropzone--over");
    }));
  zone.addEventListener("drop", (e) => {
    const files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length) { input.files = files; describe(); }
  });

  form.addEventListener("submit", () => {
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Working…"; }
  });
}
```

- [ ] **Step 3: Append dropzone CSS to `static/style.css`**

```css
/* ------------------------------------------------------------ dropzone */
.dropzone {
  display: block; cursor: pointer; text-align: center;
  padding: var(--sp-6); margin-bottom: var(--sp-3);
  border: 1.5px dashed var(--border-strong); border-radius: var(--radius-sm);
  background: var(--surface-sunk);
  transition: border-color var(--dur) var(--ease-out),
              background var(--dur) var(--ease-out);
}
.dropzone--over { border-color: var(--accent); background: var(--accent-soft); }
.dropzone__label { display: block; font-weight: 600; }
.dropzone__hint { display: block; font-size: .8125rem; color: var(--muted); margin-top: .2rem; }
.dropzone input[type=file] { display: block; width: 100%; margin-top: var(--sp-3); font-size: .8125rem; }
.file-info { font-size: .8125rem; margin: 0 0 var(--sp-4); min-height: 1.2em; }
.file-info--ok { color: var(--ok-ink); }
.file-info--bad { color: var(--danger); }
```

- [ ] **Step 4: Include `upload.js` in `templates/admin.html`**

Add after the `modal.js` include:

```html
<script src="{{ url_for('static', filename='upload.js', v=asset_v) }}"></script>
```

- [ ] **Step 5: Manual browser verification**

On the admin upload form:
1. **Drag** an `.xlsx` onto the dashed zone → zone highlights on drag-over, and on drop the filename appears as "✓ Ready: name (size)".
2. Pick a **non-xlsx** file → "✗ Not an .xlsx file: …" in danger colour.
3. Click-to-choose still opens the native picker; selecting a valid file shows "✓ Ready…".
4. Submit with a valid file + password → the "Review changes" button becomes disabled and reads "Working…" during the POST.
5. JS-off check: the plain file input + submit still work.

- [ ] **Step 6: Commit**

```bash
git add static/upload.js static/style.css templates/admin.html
git commit -m "feat: drag-drop upload zone with validation and loading state"
```

---

### Task 4: ASSET_VERSION bump + full regression

**Files:**
- Modify: `app.py` (`ASSET_VERSION`)
- Test: `pytest` (full suite) + full manual admin flow

- [ ] **Step 1: Bump `ASSET_VERSION` in `app.py`**

Change `ASSET_VERSION = "9"` to `ASSET_VERSION = "10"` so the new/changed static files and templates cache-bust on deploy.

- [ ] **Step 2: Run the server test suite**

Run: `python -m pytest -q`
Expected: `24 passed` (no server behavior changed; the suite must be green and unchanged).

- [ ] **Step 3: Full manual flow pass**

Log in → admin. Walk the complete flow once end to end:
- Upload form: dropzone validation + "Working…" on submit (Task 3).
- Preview: modal + backdrop, Cancel/Esc/backdrop → upload form + "cancelled" toast (Task 2).
- Confirm: result page + success toast (Task 1).
- Confirm the search page and login page are visually unchanged (not touched by this work).

Expected: all interactions behave; no console errors.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "chore: bump ASSET_VERSION for richer-admin-interactions assets"
```

---

## Notes for the executor

- **Do not touch** `templates/login.html`, `templates/index.html`, or `static/search.js`. If a task seems to need a change there, stop — it's out of scope per the spec.
- **No JS test harness** exists; the pytest suite covers server routes only. Do not fabricate a passing JS test. JS/CSS/HTML deliverables are verified by the manual browser steps in each task.
- Script include order in `admin.html` (final): `password.js`, `toast.js`, `modal.js`, `upload.js`. `toast.js` must load before `modal.js`/`upload.js` conceptually (defines `window.toast`), though modal/upload use `sessionStorage`/DOM, not `window.toast` directly.
- Local server run: `python app.py` (port 5001). Stop it with `Get-NetTCPConnection -LocalPort 5001 | Select-Object -Expand OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }`.
- Deploy (when the user asks) = `git pull` + Reload on PythonAnywhere. Template edits need the Reload (templates cached, `debug=False`); the `ASSET_VERSION` bump cache-busts CSS/JS. Local commits only unless told to push.
