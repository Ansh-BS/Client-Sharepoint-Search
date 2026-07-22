# Password Reveal Shape-Shift Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the password input box changing shape when the reveal button toggles it, on both login and admin pages.

**Architecture:** The reveal button flips the input's `type` between `password` and `text`. The box styling is currently bound to `input[type=password]`, so it vanishes when type becomes `text`. Rebind the box + focus styling to the `.field input` wrapper selector so it survives the swap. CSS-only change.

**Tech Stack:** Flask + Jinja templates, vanilla CSS (no build step), CSP `script-src 'self'`.

## Global Constraints

- Stay vanilla: no React, no HeroUI, no bundler, no new dependencies.
- Touch `static/style.css` only. Do not modify `password.js`, `login.html`, or `admin.html`.
- Do not alter `input[type=search]` (search page) or the `.reveal` button / icon rules.
- CSS variable names referenced (`--border-strong`, `--radius-sm`, `--accent`, `--accent-ring`, `--ink`, `--surface`, `--dur`, `--ease-out`) must stay exactly as-is.
- On CSS change, bump `ASSET_VERSION` per project cache-busting convention.

---

### Task 1: Rebind password box styling off the type attribute

**Files:**
- Modify: `static/style.css:391-401`
- Modify: `app.py` (bump `ASSET_VERSION`)
- Test: manual browser verification (no CSS unit harness in this repo)

**Interfaces:**
- Consumes: existing `.field input { margin-bottom: 0; padding-right: 2.9rem; }` rule at `static/style.css:417` (unchanged; composes with new rules).
- Produces: `.field input` now carries full box styling in both `password` and `text` states.

- [ ] **Step 1: Read current rules to confirm exact text**

Run/read `static/style.css:391-401`. Confirm the two rules read:

```css
input[type=password], input[type=file] {
  width: 100%; padding: .6rem .75rem; font: inherit; font-size: .9375rem;
  color: var(--ink); background: var(--surface);
  border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
  transition: border-color var(--dur) var(--ease-out),
              box-shadow var(--dur) var(--ease-out);
}
input[type=password]:focus-visible, input[type=file]:focus-visible {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
}
```

- [ ] **Step 2: Retarget the box rule selector**

Change the first selector from `input[type=password], input[type=file]` to `.field input, input[type=file]`:

```css
.field input, input[type=file] {
  width: 100%; padding: .6rem .75rem; font: inherit; font-size: .9375rem;
  color: var(--ink); background: var(--surface);
  border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
  transition: border-color var(--dur) var(--ease-out),
              box-shadow var(--dur) var(--ease-out);
}
```

- [ ] **Step 3: Retarget the focus rule selector**

Change the focus selector from `input[type=password]:focus-visible, input[type=file]:focus-visible` to `.field input:focus-visible, input[type=file]:focus-visible`:

```css
.field input:focus-visible, input[type=file]:focus-visible {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
}
```

- [ ] **Step 4: Bump ASSET_VERSION**

In `app.py`, find the `ASSET_VERSION` assignment and increment it (bump the value so `v=asset_v` cache-bust changes). Example: `ASSET_VERSION = "7"` → `ASSET_VERSION = "8"`.

- [ ] **Step 5: Manual browser verification — login**

Run the app locally (`python app.py`), open the login page.
1. Type into the password field.
2. Click reveal → password shows as text; **box does not move, resize, or lose its border/padding/radius.**
3. Click reveal again → masked; still no shift.
4. In revealed (text) state, confirm the accent focus ring renders on the input.
5. Caret stays at end of value; typing continues in place.

Expected: no layout shift in any state.

- [ ] **Step 6: Manual browser verification — admin**

Open the admin page, repeat Step 5 checks on `#admin_password`. Also confirm the `input[type=file]` picker above it is visually unchanged (still styled).

Expected: identical no-shift behavior; file input unaffected.

- [ ] **Step 7: Commit**

```bash
git add static/style.css app.py
git commit -m "fix: password reveal no longer reshapes the input box

Box + focus styling was bound to input[type=password]; flipping type to
text on reveal dropped it. Scope to .field input so it survives the swap.
Covers login and admin. Bump ASSET_VERSION for cache-bust."
```

---

## Notes for the executor

- This repo has a pytest suite (`tests/`), but it covers Flask routes/auth, not CSS rendering. No automated test asserts box geometry — verification is manual browser inspection, as above. Do not fabricate a passing CSS test.
- Deploy (when the user asks) is `git pull` on the PythonAnywhere server + Reload. Do not push; local commit only unless instructed.
- HTML template edits would need a server restart (templates cached, `debug=False`); this change is CSS-only so it shows live once `ASSET_VERSION` is bumped and the server serves the new file.
