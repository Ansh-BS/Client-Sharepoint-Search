# Vanilla + HeroUI Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the restored vanilla frontend HeroUI's colour system in both light and dark, a theme toggle that respects the OS by default, and HeroUI's pill button — without touching the search interaction that the design critique scored 4/4.

**Architecture:** One stylesheet, no build step. `static/style.css` gains a light token block and a dark one carrying identical names; every existing rule already reads `var(--name)`, so nothing below the token block changes for colour. A ~25-line `static/theme.js` resolves the theme before first paint.

**Tech Stack:** Flask + Jinja, vanilla CSS and JS, pytest. No Node, no bundler, no dependencies.

**Spec:** `docs/superpowers/specs/2026-07-23-vanilla-heroui-theme-design.md`

## Global Constraints

- Work on branch `vanilla-heroui-theme` (already created from `main`). Do not merge, do not push.
- Tests run from the repo root: `python -m pytest -q`. Baseline is **24 passed**.
- **No Node, no npm, no build step.** If a step seems to need one, it is wrong — stop and report.
- **Do not touch `static/search.js`.** The combobox, tier ranking, match highlighting and recents are the highest-rated part of this app and are out of scope entirely.
- Do not change any rule below the token block except the ones each task names explicitly. Colour changes must come from tokens.
- `--action*` (the gold) keeps its current values in both themes. HeroUI ships one accent; this project deliberately runs blue for keyboard state and gold for the one primary action.
- Every `localStorage` access is wrapped in try/catch. Blocked storage degrades to the OS preference, never to a thrown error.
- The CSP is `script-src 'self'` and `style-src 'self'`. No inline `<script>`, no inline `style=`. Both must stay strict.
- Bump `ASSET_VERSION` in `app.py` in the final task, not before — one bump covers the whole branch.

## File Structure

| File | Responsibility |
|---|---|
| `static/style.css` | **Modify.** Tokenise hardcoded colours, split `:root` into light + dark, restyle buttons. |
| `static/theme.js` | **Create.** Resolve and persist the theme before first paint; expose the toggle handler. |
| `templates/index.html` | **Modify.** Load `theme.js`; add the toggle to the topbar. |
| `templates/admin.html` | **Modify.** Same. |
| `templates/login.html` | **Modify.** Load `theme.js` only — no toggle (bare card, no topbar). |
| `app.py` | **Modify.** Bump `ASSET_VERSION`. No logic change. |
| `tests/test_theme.py` | **Create.** Token-parity, template wiring, toggle placement. |
| `tests/test_security_headers.py` | **Create.** Pin strict `style-src` and `script-src`. |
| `README.md` | **Modify.** Note the toggle and the `theme.js` cache-bust rule. |

---

## Task 1: Tokenise the hardcoded colours

Nine colours are written as literal `rgba()` **below** the token block. They all assume a dark page — white overlays for hover, a black modal backdrop. Light mode cannot override a literal, so they must become tokens first. This task changes no pixel: each new token holds exactly the value it replaces.

**Files:**
- Modify: `static/style.css`
- Test: `tests/test_theme.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: nine new token names available to Task 2 — `--overlay`, `--overlay`, `--cursor-glow`, `--cursor-glow-accent`, `--danger-ring`, `--danger-soft`, `--danger-soft-line` and `--backdrop`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_theme.py`:

```python
import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "static" / "style.css"


def _body(text):
    """Everything after the :root token block — the rules, not the palette."""
    end = text.index("}", text.index(":root {"))
    return text[end:]


def test_no_literal_colours_outside_the_token_block():
    """Rules must read var(--token). A literal here cannot be re-themed,
    which is exactly how a light mode ends up with white-on-white."""
    body = _body(CSS.read_text(encoding="utf-8"))
    literals = re.findall(r"rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}\b", body)
    # The open-in-new icon is an SVG data URI whose stroke is repainted by
    # mask-image, so its %23000 is not a rendered colour.
    literals = [c for c in literals if not c.startswith("#000")]
    assert literals == [], f"literal colours outside :root: {literals}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_theme.py -q`
Expected: FAIL, listing nine literals — the `rgba(255,255,255,…)` hovers, `rgba(220,38,38,.18)`, `rgba(91,140,255,.14)`, the `rgba(255,90,90,…)` pairs, and `rgba(0,0,0,.55)`.

- [ ] **Step 3: Add the nine tokens**

In `static/style.css`, inside `:root`, immediately after the `--action-disabled` line, add:

```css
  /* Overlays and glows. These were literal rgba() in the rules below, which
     made them impossible to re-theme — a white-on-white hover in light mode.
     Same values as before; only the indirection is new. */
  --overlay: rgba(255, 255, 255, .07);        /* topbar link hover */
  --cursor-glow: rgba(255, 255, 255, .06);       /* focus glow inside the box */
  --cursor-glow-accent: rgba(91, 140, 255, .14);     /* selected-row glow */
  --danger-ring: rgba(220, 38, 38, .18);      /* invalid-input focus ring */
  --danger-soft: rgba(255, 90, 90, .12);      /* error box fill */
  --danger-soft-line: rgba(255, 90, 90, .38); /* error box border */
  --backdrop: rgba(0, 0, 0, .55);             /* modal scrim */
```

- [ ] **Step 4: Replace the literals with the tokens**

Nine edits, each replacing the literal with `var(--token)`:

| Line | Was | Becomes |
|---|---|---|
| 148 | `background: rgba(255, 255, 255, .07);` | `background: var(--overlay);` |
| 238 | `rgba(255, 255, 255, .06), transparent 70%);` | `var(--cursor-glow), transparent 70%);` |
| 247 | `0 0 0 3px rgba(220, 38, 38, .18);` | `0 0 0 3px var(--danger-ring);` |
| 312 | `rgba(91, 140, 255, .14), transparent 70%);` | `var(--cursor-glow-accent), transparent 70%);` |
| 443 | `background: rgba(255, 90, 90, .12); border: 1px solid rgba(255, 90, 90, .38);` | `background: var(--danger-soft); border: 1px solid var(--danger-soft-line);` |
| 475 | `background: rgba(255, 90, 90, .1); border-color: rgba(255, 90, 90, .38);` | `background: var(--danger-soft); border-color: var(--danger-soft-line);` |
| 491 | `background: rgba(255, 255, 255, .06);` | `background: var(--overlay);` |
| 492 | `background: rgba(255, 255, 255, .06);` | `background: var(--overlay);` |
| 543 | `background: rgba(0, 0, 0, .55);` | `background: var(--backdrop);` |

Line 475 used `.1` where 443 used `.12`; both become `--danger-soft`. That is a deliberate one-off consolidation — a two-hundredths alpha difference between two error boxes is drift, not design.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_theme.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: `25 passed` — the 24 baseline plus the new one.

- [ ] **Step 7: Commit**

```bash
git add static/style.css tests/test_theme.py
git commit -m "refactor(css): tokenise the nine hardcoded overlay and state colours"
```

---

## Task 2: Split the palette into light and dark

**Files:**
- Modify: `static/style.css`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: the nine tokens from Task 1.
- Produces: `:root` (light) and `:root.dark` (dark) carrying identical token names, plus a shared block for values that do not vary by theme. A `dark` class on `<html>` selects the dark palette; Task 3 puts it there.

At the end of this task the site renders **light**, because nothing sets the class yet. That is the expected intermediate state.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_theme.py`:

```python
def _tokens(text, selector):
    start = text.index(selector + " {")
    block = text[start:text.index("\n}", start)]
    return set(re.findall(r"^\s*(--[a-z0-9-]+):", block, re.M))


def test_light_and_dark_define_the_same_tokens():
    """A token defined in one theme and not the other is the classic bug:
    it silently inherits the wrong value instead of failing loudly."""
    text = CSS.read_text(encoding="utf-8")
    light = _tokens(text, ":root")
    dark = _tokens(text, ":root.dark")
    assert light == dark, (
        f"only in light: {sorted(light - dark)}; only in dark: {sorted(dark - light)}"
    )


def test_both_themes_set_color_scheme():
    """Native controls — scrollbar, the search field's clear ×, the file
    button — follow color-scheme, not our tokens."""
    text = CSS.read_text(encoding="utf-8")
    assert "color-scheme: light" in text
    assert "color-scheme: dark" in text


def test_theme_independent_values_are_not_duplicated():
    """Spacing, motion and the gold action do not vary by theme. Duplicating
    them into both blocks invites the two copies to drift apart."""
    text = CSS.read_text(encoding="utf-8")
    for token in ("--sp-4", "--radius", "--dur", "--ease-out", "--mono",
                  "--display", "--action", "--action-hover"):
        assert len(re.findall(rf"^\s*{token}:", text, re.M)) == 1, \
            f"{token} is defined more than once"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_theme.py -q`
Expected: FAIL — there is no `:root.dark` block yet.

- [ ] **Step 3: Restructure the token block**

Replace the whole `:root { … }` block (lines 50-118, ending at the line with the closing `}` after `--icon-open`) with three blocks.

First, the theme-independent values:

```css
/* Values that do not vary by theme. Kept in one block so the two palettes
   below cannot drift apart on spacing or motion.

   The gold action is here on purpose. HeroUI ships a single accent; this app
   runs two — blue for wherever the keyboard is (focus, selection, matched
   letters) and gold for the one primary action. Collapsing them would paint
   the "Open folder" pill the same colour as the focus ring. */
:root {
  --action: #f2c66b;
  --action-hover: #f6d488;
  --action-active: #e3b757;
  --action-disabled: #6b5e3d;
  --on-accent: #1c1c1e;   /* dark ink sits on the gold in both themes */

  --sp-1: .25rem; --sp-2: .5rem; --sp-3: .7rem;
  --sp-4: 1rem; --sp-6: 1.5rem; --sp-8: 2rem;
  --radius: 12px;
  --radius-sm: 7px;

  --dur: 180ms;
  --ease-out: cubic-bezier(.22, 1, .36, 1);

  --mono: ui-monospace, "SF Mono", "Cascadia Mono", Consolas, Menlo, monospace;
  --display: "Poppins", system-ui, -apple-system, "Segoe UI", sans-serif;

  --icon-open: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'><path d='M14 5h5v5'/><path d='M19 5l-8 8'/><path d='M18 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5'/></svg>");
}
```

Then light, the default:

```css
/* Light — HeroUI's own palette. Its published oklch values for the surfaces,
   ink and accent; the overlays, glows and semantic fills are derived from
   them because HeroUI has no direct equivalent. */
:root {
  color-scheme: light;

  --bg: oklch(97.02% 0 0);
  --surface: #fff;
  --surface-sunk: oklch(95.24% .0013 286.37);
  --border: oklch(90% .004 286.32);
  --border-strong: oklch(84% .005 286.32);

  --ink: oklch(21.03% .0059 285.89);
  --ink-soft: oklch(37% .008 285.9);
  --muted: oklch(55.17% .0138 285.94);

  --accent: oklch(62.04% .195 253.83);
  --accent-hover: oklch(56% .195 253.83);
  --accent-active: oklch(50% .19 253.83);
  --accent-disabled: oklch(85% .05 253.83);
  --accent-soft: oklch(95% .03 253.83);
  --accent-ink: oklch(45% .17 253.83);
  --accent-ring: oklch(62.04% .195 253.83 / .35);

  --skeleton: oklch(93% .002 286.3);
  --skeleton-sheen: oklch(96.5% .002 286.3);

  --danger: oklch(52% .19 24.63);
  --danger-line: oklch(58% .2 24.63);
  --warn-ink: oklch(48% .12 72.33);
  --warn-bg: oklch(96.5% .03 85);
  --warn-line: oklch(88% .06 80);
  --ok-ink: oklch(45% .12 150.81);
  --ok-bg: oklch(96.5% .03 155);
  --ok-line: oklch(87% .07 152);

  /* Light elevation is HeroUI's own surface-shadow: a hairline, not a pool. */
  --lift: 0 2px 4px 0 #0000000a, 0 1px 2px 0 #0000000f, 0 0 1px 0 #0000000f;

  --overlay: oklch(0% 0 0 / .06);
  --cursor-glow: oklch(0% 0 0 / .04);
  --cursor-glow-accent: oklch(62.04% .195 253.83 / .10);
  --danger-ring: oklch(52% .19 24.63 / .22);
  --danger-soft: oklch(52% .19 24.63 / .08);
  --danger-soft-line: oklch(52% .19 24.63 / .28);
  --backdrop: oklch(0% 0 0 / .4);
}
```

Then dark:

```css
/* Dark — HeroUI's dark palette for surfaces, ink and border. Everything else
   is the original hand-tuned dark build, which was designed against this page
   and measured against it.

   One deliberate divergence: HeroUI sets --surface-shadow to none in dark and
   separates surfaces by lightness alone. This layout does not work that way —
   the search box is a single object floating at the optical centre of an empty
   page, and --lift is what makes it float. So the dark shadow stays. */
:root.dark {
  color-scheme: dark;

  --bg: oklch(12% .005 285.823);
  --surface: oklch(21.03% .0059 285.89);
  --surface-sunk: oklch(25.7% .0037 286.14);
  --border: oklch(28% .006 286.033);
  --border-strong: #48484c;

  --ink: oklch(99.11% 0 0);
  --ink-soft: #c8c8cc;
  --muted: oklch(70.5% .015 286.067);

  --accent: oklch(62.04% .195 253.83);
  --accent-hover: #7099ff;
  --accent-active: #4a7dff;
  --accent-disabled: #3a4a75;
  --accent-soft: #24324e;
  --accent-ink: #accbff;
  --accent-ring: rgba(91, 140, 255, .4);

  --skeleton: #303033;
  --skeleton-sheen: #3c3c40;

  --danger: oklch(65.32% .2328 25.74);
  --danger-line: #ff5a5a;
  --warn-ink: oklch(82.03% .1388 76.34);
  --warn-bg: #352b18;
  --warn-line: #574726;
  --ok-ink: #6ee7b7;
  --ok-bg: #17281f;
  --ok-line: #265c44;

  --lift: 0 1px 2px rgba(0, 0, 0, .4), 0 18px 40px -16px rgba(0, 0, 0, .7);

  --overlay: rgba(255, 255, 255, .07);
  --cursor-glow: rgba(255, 255, 255, .06);
  --cursor-glow-accent: rgba(91, 140, 255, .14);
  --danger-ring: rgba(220, 38, 38, .18);
  --danger-soft: rgba(255, 90, 90, .12);
  --danger-soft-line: rgba(255, 90, 90, .38);
  --backdrop: rgba(0, 0, 0, .55);
}
```

Note `--on-accent` moved to the shared block: dark ink on the gold reads correctly in both themes, because the gold itself does not change.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_theme.py -q`
Expected: PASS — 4 tests. If token-parity fails, the message names exactly which token is missing from which block.

- [ ] **Step 5: Verify contrast in the light theme — do not skip this**

The original CSS claimed `--muted` clears 4.5:1 on both `--surface` and `--bg`. That was measured for dark only. The light values above are **proposed, not measured.** Check each pair below and darken the foreground until it passes. A contrast checker that accepts `oklch()`, or DevTools' colour picker, will do.

| Foreground | Background | Needs |
|---|---|---|
| `--muted` | `--bg` | 4.5:1 |
| `--muted` | `--surface` | 4.5:1 |
| `--ink-soft` | `--surface` | 4.5:1 |
| `--danger` | `--surface` | 4.5:1 |
| `--warn-ink` | `--warn-bg` | 4.5:1 |
| `--ok-ink` | `--ok-bg` | 4.5:1 |
| `--accent-ink` | `--accent-soft` | 4.5:1 |
| `--accent` | `--surface` | 3:1 (focus ring, non-text) |

Record the measured ratios in a comment above the light block, replacing the inherited "clears 4.5:1" claim so the next person knows it was checked and when.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: `28 passed`.

- [ ] **Step 7: Commit**

```bash
git add static/style.css tests/test_theme.py
git commit -m "feat(css): light and dark palettes from HeroUI's token values"
```

---

## Task 3: Theme resolution and the toggle

**Files:**
- Create: `static/theme.js`
- Modify: `templates/index.html`, `templates/admin.html`, `templates/login.html`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: the `dark` class contract from Task 2.
- Produces: `theme.js` applying the class before first paint, and a toggle button with `id="theme-toggle"` in the topbar of the search and admin pages. Storage key is `theme`, values `"light"` and `"dark"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_theme.py`:

```python
def test_every_page_loads_theme_js_before_the_stylesheet(logged_in):
    """theme.js must run before first paint, or the page paints in the wrong
    theme and visibly flips. Before the stylesheet link is the safe spot."""
    for path in ("/", "/admin"):
        html = logged_in.get(path).get_data(as_text=True)
        assert "theme.js" in html, f"{path} does not load theme.js"
        assert html.index("theme.js") < html.index("style.css"), \
            f"{path} loads theme.js after the stylesheet"


def test_login_page_loads_theme_js(client):
    html = client.get("/login").get_data(as_text=True)
    assert "theme.js" in html
    assert html.index("theme.js") < html.index("style.css")


def test_theme_js_is_not_deferred_or_async():
    """defer/async would let the page paint first — the exact flash this
    script exists to prevent."""
    for name in ("index.html", "login.html", "admin.html"):
        html = (Path(__file__).resolve().parent.parent / "templates" / name).read_text(encoding="utf-8")
        line = next(ln for ln in html.splitlines() if "theme.js" in ln)
        assert "defer" not in line and "async" not in line, f"{name}: {line}"


def test_toggle_is_on_the_signed_in_pages(logged_in):
    for path in ("/", "/admin"):
        assert 'id="theme-toggle"' in logged_in.get(path).get_data(as_text=True)


def test_toggle_is_not_on_the_login_page(client):
    """The login page is a deliberately bare centred card with no topbar.
    It still honours the saved choice, because theme.js is in its head."""
    assert 'id="theme-toggle"' not in client.get("/login").get_data(as_text=True)


def test_no_inline_script_anywhere():
    """CSP is script-src 'self'. An inline script would need a nonce or hash."""
    for name in ("index.html", "login.html", "admin.html"):
        html = (Path(__file__).resolve().parent.parent / "templates" / name).read_text(encoding="utf-8")
        assert "<script>" not in html, f"{name} has an inline script"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_theme.py -q`
Expected: FAIL — no `theme.js`, no toggle.

- [ ] **Step 3: Write `static/theme.js`**

```javascript
// Theme resolution. Loaded synchronously in <head>, before the stylesheet, so
// the class lands before first paint and the page never flashes the wrong
// theme. Deliberately not an inline script: the CSP is script-src 'self', and
// inlining would mean maintaining a nonce or a hash.
(function () {
  var KEY = "theme";

  function stored() {
    try {
      var v = localStorage.getItem(KEY);
      return v === "light" || v === "dark" ? v : null;
    } catch (e) {
      // Storage blocked by policy or private mode. Fall back to the OS.
      return null;
    }
  }

  function prefersDark() {
    return typeof matchMedia === "function" &&
      matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function apply(theme) {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }

  function current() {
    return document.documentElement.classList.contains("dark") ? "dark" : "light";
  }

  apply(stored() || (prefersDark() ? "dark" : "light"));

  // The button does not exist yet — <head> runs before <body> is parsed.
  document.addEventListener("DOMContentLoaded", function () {
    var button = document.getElementById("theme-toggle");
    if (!button) return;   // login page has no toggle, by design

    function sync() {
      var dark = current() === "dark";
      button.setAttribute("aria-pressed", String(dark));
      button.textContent = dark ? "Light" : "Dark";
    }

    sync();
    button.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      apply(next);
      try {
        localStorage.setItem(KEY, next);
      } catch (e) {
        // Not persisted; the choice still holds for this page view.
      }
      sync();
    });
  });
})();
```

- [ ] **Step 4: Wire the templates**

In **all three** of `templates/index.html`, `templates/login.html` and `templates/admin.html`, add this line to `<head>` **immediately before** the existing stylesheet `<link>`:

```html
<script src="{{ url_for('static', filename='theme.js', v=asset_v) }}"></script>
```

No `defer`, no `async` — both would defeat the point.

Then in `templates/index.html` and `templates/admin.html` only, add the toggle as the last child of the topbar `<nav>`. For `index.html`:

```html
<header class="topbar topbar-end">
  <nav>
    <a href="{{ url_for('admin') }}">Admin</a>
    <a href="{{ url_for('logout') }}">Log out</a>
    <button type="button" id="theme-toggle" class="theme-toggle"
            aria-pressed="false" aria-label="Switch between light and dark">Dark</button>
  </nav>
</header>
```

For `admin.html`, the same `<button>` line appended after its `Log out` link, leaving its three existing links untouched.

- [ ] **Step 5: Style the toggle**

The base `button` rule is a full-width gold action button — completely wrong for a topbar control. Add this immediately after the `.topbar nav a[aria-current]` rule in `static/style.css`:

```css
/* The toggle is corner furniture, not an action. It borrows the nav links'
   size and colour rather than the primary button's, so it sits with them
   instead of competing with the search box. */
.theme-toggle {
  width: auto; min-height: 0; margin: 0;
  font: inherit; font-size: .8125rem; font-weight: 400;
  padding: .25rem .55rem; border: 0; border-radius: var(--radius-sm);
  background: none; color: var(--muted); cursor: pointer;
  transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out);
}
.theme-toggle:hover { background: var(--overlay); color: var(--ink); }
.theme-toggle:active { background: var(--overlay); transform: none; }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_theme.py -q`
Expected: PASS — 10 tests.

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: `34 passed`.

- [ ] **Step 8: Commit**

```bash
git add static/theme.js static/style.css templates/ tests/test_theme.py
git commit -m "feat: light/dark toggle with OS default and no flash on load"
```

---

## Task 4: HeroUI's button

**Files:**
- Modify: `static/style.css`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no new tokens. Geometry only.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_theme.py`:

```python
def test_primary_button_is_a_heroui_pill():
    text = CSS.read_text(encoding="utf-8")
    block = text[text.index("\nbutton {"):text.index("button:hover")]
    assert "border-radius: 24px" in block, "button is not a pill"
    assert "border-radius: 10px" not in block, "old rounded-rectangle radius left behind"


def test_button_press_is_a_scale_not_a_nudge():
    text = CSS.read_text(encoding="utf-8")
    assert "transform: scale(.97)" in text


def test_reduced_motion_disables_the_button_transform():
    """The rest of this stylesheet already honours prefers-reduced-motion;
    a new transform must not be the one thing that ignores it."""
    text = CSS.read_text(encoding="utf-8")
    block = text[text.index("prefers-reduced-motion"):]
    assert "button:active" in block and "transform: none" in block
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_theme.py -q`
Expected: FAIL — the radius is still `10px`.

- [ ] **Step 3: Restyle the button**

Replace the `button` rule and its `:active` line in `static/style.css`:

```css
button {
  width: 100%; min-height: 40px; margin-top: var(--sp-2);
  padding: .6rem 1rem; font: inherit; font-size: .9375rem; font-weight: 700;
  border: 0; border-radius: 10px;
  background: var(--action); color: var(--on-accent); cursor: pointer;
  transition: background var(--dur) var(--ease-out);
}
button:hover { background: var(--action-hover); }
button:active { background: var(--action-active); transform: translateY(1px); }
```

with:

```css
/* HeroUI's button geometry: a stadium, and a press that scales rather than
   nudges. Full width is this app's own — the login and admin forms are single
   -column, so the action spans the card. */
button {
  width: 100%; min-height: 40px; margin-top: var(--sp-2);
  padding: .6rem 1rem; font: inherit; font-size: .9375rem; font-weight: 700;
  border: 0; border-radius: 24px;
  background: var(--action); color: var(--on-accent); cursor: pointer;
  transition: background var(--dur) var(--ease-out),
              transform 250ms var(--ease-out);
}
button:hover { background: var(--action-hover); }
button:active { background: var(--action-active); transform: scale(.97); }
```

- [ ] **Step 4: Keep the secondary button in step**

`button.secondary` sets no `border-radius`, so it picks up the pill automatically. But it **does** override `:active`, and that line still carries the old nudge — leaving the Cancel button beside a scaling Replace button pressing differently. Change:

```css
button.secondary:active { background: var(--overlay); transform: translateY(1px); }
```

to:

```css
button.secondary:active { background: var(--overlay); transform: scale(.97); }
```

(the background is already `var(--overlay)` after Task 1).

`button.reveal` and `.theme-toggle` both override `border-radius` and `transform` on purpose and must keep doing so: the reveal sits flush inside the password field's right edge, and the toggle is a nav-sized control. Leave both alone.

- [ ] **Step 5: Add the reduced-motion guard**

The stylesheet already has a `@media (prefers-reduced-motion: reduce)` block (it disables the skeleton animation). Add inside it:

```css
  button:active { transform: none; }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_theme.py -q`
Expected: PASS — 13 tests.

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: `37 passed`.

- [ ] **Step 8: Commit**

```bash
git add static/style.css tests/test_theme.py
git commit -m "feat(css): HeroUI pill geometry and press scale on buttons"
```

---

## Task 5: Pin the CSP, bump the cache tag, update the docs

**Files:**
- Create: `tests/test_security_headers.py`
- Modify: `app.py`, `README.md`
- Test: full suite

**Interfaces:**
- Consumes: everything above.
- Produces: a test pinning the strict CSP; `ASSET_VERSION` bumped once for the branch.

- [ ] **Step 1: Write the security header test**

Create `tests/test_security_headers.py`:

```python
def _csp(client):
    return client.get("/login").headers["Content-Security-Policy"]


def test_styles_are_locked_to_self(client):
    """The React build needed style-src 'unsafe-inline' because React Aria
    writes inline style attributes at runtime. Vanilla does not, so the strict
    policy is back — and stays."""
    csp = _csp(client)
    assert "style-src 'self';" in csp
    assert "unsafe-inline" not in csp


def test_scripts_are_locked_to_self(client):
    csp = _csp(client)
    assert "script-src 'self';" in csp
    assert "unsafe-eval" not in csp


def test_framing_and_base_uri_locked(client):
    csp = _csp(client)
    assert "default-src 'self';" in csp
    assert "frame-ancestors 'none';" in csp
    assert "base-uri 'self';" in csp


def test_other_hardening_headers_present(client):
    headers = client.get("/login").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
```

- [ ] **Step 2: Run it to confirm the policy is already strict**

Run: `python -m pytest tests/test_security_headers.py -q`
Expected: PASS — 4 tests, with no change to `app.py`. This branch came from `main`, which never had the SPA's relaxation. The test exists to stop it coming back.

- [ ] **Step 3: Bump `ASSET_VERSION` and widen its comment**

In `app.py`, change `ASSET_VERSION = "10"` to `"11"`, and replace the comment above it:

```python
# Cache-busting tag for the CSS and JS under static/. Browsers reuse a cached
# copy of a URL they've seen before, so a deploy that changes those files
# leaves staff staring at the old ones. Bump this on every deploy that touches
# style.css, search.js, theme.js or any of the other static scripts; the
# changed URL forces a fresh fetch. Templates read it via asset_v().
ASSET_VERSION = "11"
```

- [ ] **Step 4: Update the README**

In `README.md`, add to the Notes list:

```markdown
- Light and dark themes. First visit follows the OS; the toggle in the top
  right overrides it and the choice is remembered. `static/theme.js` runs
  before first paint so the page never flashes the wrong theme.
- Colours come from HeroUI's palette (`:root` light, `:root.dark` dark, same
  token names in both). Rules read `var(--token)` only — a literal colour in a
  rule cannot be re-themed, and `tests/test_theme.py` fails if one appears.
```

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: `41 passed`.

- [ ] **Step 6: Manual check in the browser**

Start the server:

```powershell
Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
python app.py
```

At `http://127.0.0.1:5001` with DevTools open:

1. **First load, OS in light mode** — page is light. Switch the OS to dark, reload — page is dark. No stored choice yet.
2. **Click the toggle** — theme flips, label changes. Reload — the choice sticks, and there is **no flash** of the other theme.
3. **Search** — type two letters. Matched letters are underlined, arrow keys move the selection, Enter opens the folder. Check in **both** themes: the selected-row tint and the match underline must be visible in light, not just dark.
4. **Type a Client ID** — it still finds the client.
5. **Login page** — no toggle, but it honours the saved theme.
6. **Admin** — dropzone, preview modal and toasts all readable in light; the modal backdrop dims rather than washes out.
7. **Buttons** — pill-shaped, and they scale down on press.
8. **Block site data** (DevTools → Application) and reload — page falls back to the OS preference, no blank screen, toggle still works for the session.
9. Console: no errors, **no CSP violations**.

- [ ] **Step 7: Commit**

```bash
git add app.py README.md tests/test_security_headers.py
git commit -m "chore: pin the strict CSP, bump the asset tag, document the themes"
```

- [ ] **Step 8: Finish the branch**

Use superpowers:finishing-a-development-branch. Local merge to `main` only — no push without explicit approval.

---

## Self-Review (completed by plan author)

**Spec coverage:**

| Spec item | Task |
|---|---|
| Tokens split into light + dark using HeroUI's values | 2 |
| The twelve-plus dark-only tokens get light values | 2 |
| Contrast re-verified for light | 2, Step 5 |
| Buttons take HeroUI pill geometry and press | 4 |
| Password-reveal button keeps its shape | 4, Step 4 |
| Toggle: OS default, manual override, persisted | 3 |
| No flash — external blocking script, not inline | 3, plus tests for `defer`/`async` and inline `<script>` |
| Toggle on search + admin, absent on login | 3 |
| Guarded `localStorage` | 3 |
| Strict `style-src 'self'` pinned by a test | 5 |
| `ASSET_VERSION` bumped, `theme.js` in its remit | 5 |
| Search box and panel untouched | Global constraint; no task edits `search.js` |
| No Node, no build step | Global constraint |

**Gap found and closed during review:** the spec did not account for the nine hardcoded `rgba()` colours below the token block. Light mode cannot override a literal, so Task 1 was added to tokenise them first. Without it, Task 2 would have produced a light page with white-on-white hovers and a dark-tuned error box.

**Second gap found and closed:** the toggle is a `<button>`, and the base `button` rule is a full-width gold action. Dropped into the topbar it would have rendered as a full-width gold bar across the nav. Task 3 Step 5 adds `.theme-toggle` to override it.

**Placeholders:** none. Every code step contains complete code.

**Type consistency:** storage key `theme` with values `"light"`/`"dark"`, class `dark` on `document.documentElement`, control id `theme-toggle`, `ASSET_VERSION = "11"` — used identically across tasks 2-5.

**Honest limitation:** the light palette values in Task 2 are **derived, not measured**. Task 2 Step 5 requires checking eight foreground/background pairs and adjusting until each passes, then recording the measured ratios. A reviewer should treat a missing ratio comment as an incomplete task, not a cosmetic omission.
