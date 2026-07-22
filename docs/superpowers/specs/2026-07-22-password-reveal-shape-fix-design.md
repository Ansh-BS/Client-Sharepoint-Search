# Password reveal shape-shift fix — design

**Date:** 2026-07-22
**Scope:** `static/style.css` only. Login + admin password fields.

## Problem

Clicking the reveal (unhide) button on a password field makes the input box
visibly change shape — it collapses to unstyled browser-default dimensions.

Affected: `templates/login.html` (`#password`) and
`templates/admin.html` (`#admin_password`). Both use the same `.field` +
`.reveal` markup and the same `password.js` handler.

## Root cause

`static/password.js` toggles visibility by flipping the input's `type`
attribute between `password` and `text`:

```js
input.type = shown ? "password" : "text";
```

But the box styling in `static/style.css` is bound to the type attribute:

```css
input[type=password], input[type=file] {
  width: 100%; padding: .6rem .75rem; ...
  border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
}
input[type=password]:focus-visible, input[type=file]:focus-visible { ... }
```

When the type becomes `text`, the input matches **none** of the box
selectors. It loses width, padding, border, border-radius, background, and the
focus ring — reverting to the browser default input box. That is the shape
change. Re-clicking (back to `password`) restores it.

The `.field` / `.reveal` layout, the SVG icon swap, and the JS are all correct.
The defect is purely the type-coupled CSS selector.

## Fix (Approach A — vanilla, chosen)

Scope the box styling to the field wrapper instead of the type attribute, so it
holds across the `password` ⇄ `text` swap.

The `.field` wrapper contains exactly one reveal-able password input on both
pages, so `.field input` is a precise target and matches regardless of current
type. The admin file picker (`input[type=file]`) is never toggled, so it keeps
its own type-based rule.

### Changes in `static/style.css`

1. **Box rule** (currently `input[type=password], input[type=file] { … }`):
   split so the shared box declarations apply to `.field input, input[type=file]`.
   `.field input` now carries width/padding/border/radius/background/transition.

2. **Focus rule** (currently
   `input[type=password]:focus-visible, input[type=file]:focus-visible { … }`):
   retarget to `.field input:focus-visible, input[type=file]:focus-visible`.

3. Leave the existing `.field input { margin-bottom: 0; padding-right: 2.9rem; }`
   rule as-is; it already scopes to `.field input` and composes with the above.

No specificity regression: `.field input` (0,1,1) still yields consistent box
styling in both states, and `padding-right: 2.9rem` for the button gutter
continues to apply because `.field` inputs are always inside `.field`.

### Not changed

- `password.js` — untouched.
- `templates/login.html`, `templates/admin.html` — untouched.
- `.reveal` button, SVG eye/eye-off icons, `aria-pressed` state styling.
- `input[type=search]` (search page) — different component, unaffected.

## Rejected alternatives

- **HeroUI v3 / React rewrite.** Wrong tool. App is Flask + Jinja + vanilla JS
  with `script-src 'self'` CSP and no build step. Adding React means a bundler,
  npm toolchain, CSP rewrite, and rewriting both templates as components — a
  stack migration to fix a one-line CSS scoping bug. Rejected.
- **Add `input[type=text]` to the selector lists.** Works, but leaks
  password-box styling onto any future generic `type=text` input site-wide.
  Rejected in favour of the scoped `.field input`.
- **`-webkit-text-security` masking without changing type.** Inconsistent
  support, keeps a text input semantically. Rejected.

## Verification

Manual, both pages:

1. Login page: type into password, click reveal → text shown, **box does not
   move or resize**; border/padding/radius identical. Click again → masked,
   still no shift.
2. Focus ring: click reveal, confirm the accent focus ring still renders on the
   input in the revealed (`text`) state.
3. Caret: after reveal, caret stays at end of value (existing `password.js`
   behavior) and typing continues in place.
4. Admin page: repeat 1–3 on `#admin_password`. Confirm the `input[type=file]`
   picker above it is visually unchanged.
5. Search page unaffected (no `.field`, different rule).

## Deploy note

Per project convention: CSS shows live but bump `ASSET_VERSION` so the cache-
busting `v=asset_v` query updates and clients pull the new stylesheet.
