# Design: return to the vanilla frontend, wearing HeroUI's theme

**Date:** 2026-07-23
**Status:** Approved (brainstorming). Next: writing-plans.
**Supersedes:** `2026-07-22-heroui-spa-rebuild-design.md` and `2026-07-23-ui-repair-design.md`

## Goal

Abandon the React + HeroUI SPA and return to the hand-written Flask/Jinja + vanilla
JS frontend, then give it HeroUI's colour system and button shape. Add a light theme
and a toggle, which the vanilla build never had.

## Why

The SPA rebuild was assessed at **25/40** against Nielsen's heuristics on 2026-07-23.
The vanilla build it replaced scored **35/40** on 2026-07-21
(`.impeccable/critique/2026-07-21T10-11-54Z__templates-index-html.md`). The rebuild
improved the backend and lost the interface: Client ID search, match highlighting,
recent searches, the keyboard combobox, and the tiered ranking all went, and an empty
query rendered the entire client list.

Reverting recovers all of it at no cost, because the code still exists on `main`. What
the SPA genuinely offered — HeroUI's modern palette and a dark/light toggle — is a
stylesheet's worth of work to port. The React runtime was never the part worth having.

## Starting point

Branch from **`main`**, which still holds the complete vanilla build:

| | |
|---|---|
| `static/style.css` | 560 lines, hand-written, dark-only |
| `static/search.js` | 690 lines — combobox, tiers, highlighting, recents |
| `static/toast.js`, `modal.js`, `upload.js`, `password.js` | 208 lines total |
| `templates/index.html`, `login.html`, `admin.html` | Jinja pages |
| `app.py` | Jinja routes + `/api/clients` + `ASSET_VERSION` |

`heroui-spa-rebuild` is **parked, not deleted** — the React work stays in git history.

Work happens on a new branch `vanilla-heroui-theme`, cut from `main`. The four SPA
documents (`2026-07-22-heroui-spa-rebuild-design.md` and its plan,
`2026-07-23-ui-repair-design.md` and its plan) live only on `heroui-spa-rebuild`; they
are copied across so the docs directory stays complete, each with a status line
marking it superseded by this design. A later reader must not follow an abandoned plan
because it was the only one they could find.

## Scope

**In scope:**
1. Restructure `style.css` tokens into light + dark sets using HeroUI's values.
2. Re-tune the twelve dark-only tokens that have no light equivalent.
3. Buttons adopt HeroUI's pill geometry and press behaviour — except the inset
   password-reveal button, which keeps its shape (see below).
4. A theme toggle: OS default, manual override, persisted, no flash.
5. Restore strict `style-src 'self'` in the CSP, with a test pinning it.

**Out of scope (YAGNI):**
- Input, dropzone, card, modal and toast **shape** — they take the new colours and keep
  their hand-made geometry. Only buttons change shape.
- The search box and its results panel. The panel is glued to the box, arrow keys move
  a selection through it, matched letters are underlined. It scored 4/4 and is the one
  thing worth protecting.
- The JSON API built for the SPA. Vanilla posts forms.
- Any Node toolchain. The vanilla build is buildless and that is the point.

## Decisions

### Blue stays for the keyboard, gold stays for the action

The vanilla CSS runs a deliberate two-colour system, and it carries meaning:

```css
/* Blue = selection / focus / match (where the keyboard is).
   Gold = the one primary action. */
--accent: #5b8cff;
--action: #f2c66b;
```

HeroUI ships a single accent. Collapsing to it would paint the "Open folder" pill the
same colour as the focus ring, and the 2026-07-21 critique specifically credited the
gold pill / amber badge distinction for carrying information without relying on colour
alone.

So: **HeroUI's neutrals and blue accent, the existing gold action.** HeroUI's
`--accent: oklch(62.04% .195 253.83)` is a blue in the same family as `#5b8cff`, so
the substitution is natural. Gold has no HeroUI equivalent and is kept as-is.

### Both themes diverge from HeroUI's shadow

HeroUI sets `--surface-shadow: 0 0 0 0 transparent inset` in dark mode — it drops
elevation entirely and separates surfaces by lightness alone. The vanilla composition
does not work that way: the search box is a single object floating at the optical
centre of an empty page, and `--lift` is what makes it float.

The first pass of this work took HeroUI's shadow as-is in **light** (a hairline —
HeroUI can afford that because it doesn't rely on elevation to separate surfaces) and
kept the vanilla dark shadow pool in **dark**. That was wrong in the same direction as
the dark case, just discovered later, by a whole-branch review that measured it:
light's `--surface` vs `--bg` is 1.09:1 and the old `--border-strong` vs `--surface`
was 1.64:1, so nothing but a 1.5:1 line told the box, panel, cards and the info toast
apart from the empty page under them. HeroUI can drop elevation in light because *it*
doesn't depend on the object floating; this layout does, in both themes.

So the divergence goes both ways: `--lift` gets its own shadow pool in **light**
(softer than dark's, since a dark-strength pool reads as a stain on a near-white
page) and keeps the original vanilla pool in **dark**. `--border-strong` was also
raised in light, from L 84% to L 62%, clearing 3:1 (non-text contrast) against both
`--surface` and `--bg` — the search input's border is otherwise the only cue that it's
a text field. Both reasons are recorded in the CSS comments next to `--lift` and
`:root.dark`.

### Derived values are hardcoded, not computed

HeroUI derives most tokens with `color-mix(in oklab, …)` behind an `@supports` guard.
For a hand-maintained stylesheet with no build step, a literal value is easier to read
and needs no fallback. Derived tokens (`--accent-soft`, `--accent-ring`, `--warn-bg`,
`--ok-bg`, `--skeleton`) are written as literal `oklch()` values, with a comment
recording the HeroUI formula they came from.

### Radius is unchanged except on buttons

Scope is colours plus buttons. `--radius: 12px` and `--radius-sm: 7px` stay. Only the
`button` rule takes HeroUI's `24px` pill.

## Token architecture

`:root` splits into two blocks carrying the same thirty names:

```css
:root      { color-scheme: light; /* light values */ }
:root.dark { color-scheme: dark;  /* dark values  */ }
```

`color-scheme` must move into each block — it is currently a single `dark` at `:root`
and governs native controls (scrollbar, the `×` in the search input, the file button).

Every existing rule already reads `var(--name)`, so no rule below the token block
needs editing for colour. That is what makes this a stylesheet change rather than a
rewrite.

### Direct mappings (HeroUI values, verified from the built stylesheet)

| Vanilla token | Light | Dark |
|---|---|---|
| `--bg` | `oklch(97.02% 0 0)` | `oklch(12% .005 285.823)` |
| `--surface` | `#fff` | `oklch(21.03% .0059 285.89)` |
| `--surface-sunk` | `oklch(95.24% .0013 286.37)` | `oklch(25.7% .0037 286.14)` |
| `--border` | `oklch(90% .004 286.32)` | `oklch(28% .006 286.033)` |
| `--ink` | `oklch(21.03% .0059 285.89)` | `oklch(99.11% 0 0)` |
| `--muted` | `oklch(55.17% .0138 285.94)` | `oklch(70.5% .015 286.067)` |
| `--accent` | `oklch(62.04% .195 253.83)` | `oklch(62.04% .195 253.83)` |
| `--danger` | `oklch(59.4% .1967 24.63)` | `oklch(65.32% .2328 25.74)` |
| `--warn-ink` | `oklch(78.19% .1585 72.33)` | `oklch(82.03% .1388 76.34)` |
| `--ok-ink` | `oklch(73.29% .1935 150.81)` | `oklch(73.29% .1935 150.81)` |

### Tokens with no light equivalent yet

These are currently tuned for a near-black page and must be given light values:

`--border-strong`, `--ink-soft`, `--accent-hover`, `--accent-active`,
`--accent-disabled`, `--accent-soft`, `--accent-ink`, `--accent-ring`,
`--skeleton`, `--skeleton-sheen`, `--warn-bg`, `--warn-line`, `--ok-bg`, `--ok-line`,
`--danger-line`, `--lift`.

`--action*` (gold) and the scale/motion tokens (`--sp-*`, `--radius*`, `--dur`,
`--ease-out`, `--mono`) are mode-independent and stay in a shared block.

### Contrast requirement

The CSS comment claims `--muted` clears 4.5:1 against both `--surface` and `--bg`.
That was verified for dark only. **It must be re-verified for light**, along with
`--ink-soft` and the three semantic ink colours on their light backgrounds. Any pair
that fails gets darkened until it passes; the measured ratios go in a comment.

## Buttons

```css
/* now */
button { padding: .6rem 1.1rem; border-radius: 10px; }
button:active { transform: translateY(1px); }

/* after */
button { height: 40px; padding: 0 1rem; border-radius: 24px; }
button:active { transform: scale(.97); }
```

HeroUI's own transition timing comes with it, and a
`@media (prefers-reduced-motion: reduce)` block disables the transform — the vanilla
build already respects reduced motion elsewhere and should stay consistent.

Colours continue to come from `--action` / `--action-hover` / `--action-active` /
`--action-disabled`. `a.open` (the results pill) is already `border-radius: 999px` and
needs nothing. `button.reveal` (the password eye) keeps its square-ish inset shape —
it sits flush inside the password field and a pill would break that seam.

## Theme toggle

### `static/theme.js` (new, ~25 lines)

Loaded as a **render-blocking `<script src>` in `<head>`**, before the stylesheet link.
Deliberately not inline: the CSP is `script-src 'self'`, and an inline script would
need a nonce or hash. External and synchronous means the class is on `<html>` before
first paint, so there is no flash of the wrong theme.

Resolution order:
1. `localStorage.getItem("theme")` — `"light"` or `"dark"` if the user has chosen.
2. Otherwise `matchMedia("(prefers-color-scheme: dark)")`.
3. Apply or remove `dark` on `document.documentElement`.

Every storage access is wrapped in try/catch. Blocked storage degrades to the OS
preference, never to a thrown error — an unguarded `localStorage` read during render
was the one genuine blocker found in the SPA work, and it is not worth repeating.

The module also exposes the toggle handler, which flips the class, writes the choice,
and updates the control's `aria-pressed`.

### The control

A `<button>` in the existing `header.topbar > nav`, beside Admin / Log out, on the
**search and admin pages**.

**The login page gets no toggle.** It is a deliberately bare centred card with no
topbar, and adding chrome to it costs more than it returns. It still honours the saved
choice, because `theme.js` is in the shared `<head>`.

Accessibility: the button carries `aria-pressed` reflecting the dark state and a
`aria-label` that names the action rather than the state. It is reachable in the tab
order alongside the other nav items and takes the same focus ring.

## Security

Vanilla has no React Aria writing inline style attributes at runtime, so the CSP
relaxation forced by the SPA is no longer needed:

```
style-src 'self'          (not 'self' 'unsafe-inline')
```

`tests/test_security_headers.py` is ported from the SPA branch with its assertion
flipped to the strict form, so this cannot quietly regress. `script-src 'self'` stays
pinned as it already is.

## Error handling

- **`localStorage` unavailable or throwing:** theme resolution falls back to the OS
  preference; the toggle still works for the session but does not persist.
- **`theme.js` fails to load:** the page renders in light (no `dark` class). Content
  is fully usable; only the theme is wrong. Acceptable for a same-origin static file.
- **No stored value and no `matchMedia` support:** light, matching HeroUI's own
  default.

## Testing

No Node, no vitest — the build is buildless and stays that way. Tests are Python,
against the rendered HTML:

- every page links `theme.js` in `<head>`, before the stylesheet, with the `?v=` tag
- `style.css` and `theme.js` both carry the current `ASSET_VERSION`
- the toggle control renders on the search and admin pages
- the toggle control does **not** render on the login page
- security headers assert strict `style-src 'self'` and no `unsafe-inline`
- the existing suite (parser, storage, auth, admin) stays green

Theme switching itself, the light-mode appearance, and the no-flash behaviour are
**browser-verified by the user** — the same gate the layout fix went through, since
subagents cannot drive a browser.

## Deploy

Unchanged from the pre-SPA flow and simpler than the SPA's: `git pull` on
PythonAnywhere, then Reload. No Node on the server, no committed `dist`, no build step.

The static mapping reverts from `/assets/` → `frontend/dist/assets` back to
`/static/` → `static`. The deploy docs revert to their pre-SPA form with the
`ASSET_VERSION` guidance restored — **bump it whenever `style.css` or `theme.js`
changes**, or staff keep the cached copies and the deploy appears to do nothing.

## Open question

`--action` gold is kept because it carries meaning the critique credited. If you would
rather go pure HeroUI and let the single accent do both jobs, that is a four-token
change (`--action*` become aliases of `--accent*`) plus a re-check that the "Open
folder" pill still reads as the primary action next to a same-coloured focus ring.
