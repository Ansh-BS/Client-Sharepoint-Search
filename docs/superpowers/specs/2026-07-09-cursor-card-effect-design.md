# Cursor-card illumination effect — design

Date: 2026-07-09

## Context

A React/Framer-Motion "CursorCards" component (built earlier in a separate
Next.js sandbox project, `ink-reveal-component` — unrelated codebase, only
the *visual effect* is being ported) gives cards a mouse-following radial
glow: a soft illumination spot tracks the cursor within each card, fading in
on proximity/hover and out on leave.

Client SharePoint Search has no React, no build step, no Tailwind — plain
Flask + vanilla JS/CSS (`static/search.js`, `static/style.css`). The effect
is ported as native CSS custom properties + a `mousemove`/`pointerenter`/
`pointerleave` listener, no new dependencies.

## Scope

Applies to every `#results li` (all result tiers 1-5 and recent-search rows
— they already share one visual "card" style: white background, border,
rounded corners, per `static/style.css`). No proximity-before-hover
pre-glow (the React version's 100px extended-proximity trick existed to
compensate for React's per-card isolation needing a shared container to
know about nearby-but-outside cursor position); native `pointerenter`/
`pointerleave` on each `<li>` is sufficient and simpler for a flat DOM list.

## Design

**CSS** (`static/style.css`): each `#results li` gets a `::before`
pseudo-element, `position: absolute; inset: 0; border-radius: inherit;
pointer-events: none;`, background a `radial-gradient(180px circle at
var(--mx, 50%) var(--my, 50%), rgba(79,70,229,.16), transparent 70%)`
(indigo, matching the existing `#4f46e5`/`.selected` accent — no new palette
introduced), opacity `0` by default, `opacity 1` via a `.glow` class,
transition on `opacity` only (200ms). `li` itself needs `position: relative;
overflow: hidden` (already has `border-radius` — `overflow:hidden` keeps the
glow clipped to the rounded corners) and `isolation: isolate` so the
pseudo-element sits correctly relative to existing children (`.info`, the
"Open folder" button, `mark.match`, etc. — all already `position: static`,
unaffected).

**JS** (`static/search.js`): one delegated `pointermove` listener on
`#results` (not one listener per `<li>` — results re-render on every
keystroke, so per-element listeners would leak/need constant rebinding;
delegation on the stable parent avoids that entirely). On `pointermove`,
`event.target.closest("li")` to find the hovered row, compute
`(clientX - rect.left)`/`(clientY - rect.top)` as percentages, set them as
inline `--mx`/`--my` CSS custom properties on that `<li>` only (cheap — one
element touched per move, not the whole list). A `pointerover`/`pointerout`
pair (delegated the same way, checking `closest("li")` differs between
`target`/`relatedTarget`) toggles the `.glow` class so the fade transition
only plays on actual enter/leave, not every pixel of movement.

**Interaction with keyboard-selection**: the existing `.selected` class
(from arrow-key navigation) stays untouched — the glow is a separate,
purely-pointer-driven layer that can coexist with keyboard selection
(a keyboard-selected row shows both its indigo selection ring and, if the
mouse happens to also be over it, the glow — no conflict, verified during
implementation).

**Performance**: `pointermove` fires often, but the handler only does a
`closest()` DOM lookup + `getBoundingClientRect()` + two custom-property
writes — cheap, no rAF throttling needed at this list size (≤8 rows).

## Files touched

`static/style.css` (new `::before` rule + `li` position/overflow/isolation),
`static/search.js` (three delegated listeners on `#results`: `pointermove`,
`pointerover`, `pointerout`).

## Testing

Manual browser verification: hover a result card, confirm the glow follows
the cursor and is clipped to the card's rounded corners; move between cards,
confirm the glow fades out on the old card and in on the new one; confirm
keyboard arrow-selection still shows its own indigo ring independently;
confirm no regression to click/Enter-to-open or the existing search tiers.
