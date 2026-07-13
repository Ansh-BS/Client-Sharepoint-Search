# Product

## Register

product

## Users

Benison Solvers office staff, on desktop, mid-task. Someone is on a call or
working a client file and needs that client's SharePoint folder *now*. They are
not technical: they know client names, they do not know Client IDs by heart, and
they should never have to learn a syntax, a filter, or a keyboard convention to
get where they are going.

The job: from a half-remembered client name to the right SharePoint folder, in
one screen, without asking anyone.

## Product Purpose

A single search box over the firm's client list. Type a name (typos forgiven) or
a Client ID, get the matching clients, open the folder. An admin uploads a new
spreadsheet when the client list changes; nothing else in the product needs
explaining.

Success: a non-technical member of staff finds the folder on the first try, and
never opens the wrong client's folder.

## Brand Personality

Calm, plain, dependable. The quiet competence of an accountancy firm's internal
tooling. Nothing shouts, nothing surprises, nothing needs a tutorial. The
interface should be forgettable — noticed only when it fails, which it should
not.

Voice: sentence case, plain English, no jargon. Errors say what happened and
what to do next.

## Anti-references

- **Generic AI/SaaS landing page.** No gradient text, no hero-metric blocks, no
  tiny uppercase tracked eyebrows above sections, no purple-gradient decoration.
  This is a tool, not a pitch.
- **Not** minimal to the point of coldness: this serves non-technical staff, so
  empty and error states must teach rather than merely state.

The existing cursor-following glow on the search box and result rows is a
deliberate, spec'd choice (`docs/superpowers/specs/2026-07-09-cursor-card-effect-design.md`)
and stays. It is the one moment of character.

## Design Principles

1. **The typed name is the interface.** Everything else on the page is
   subordinate to the search box. Resist adding chrome.
2. **Forgive the user, never guess for them.** Typos, partial names, and wrong
   case all still find the client. But when the match is ambiguous — two clients
   sharing an ID, no exact hit — the product stops and shows the options rather
   than opening something plausible. Opening the wrong client's folder is the
   expensive failure, not a slow search.
3. **Every state teaches.** Empty, loading, no-match, and no-link-on-file each
   tell a non-technical user what happened and what to do next. "No client found"
   is a dead end; a dead end is a defect.
4. **Keyboard and mouse are equal citizens.** Enter opens the exact match; the
   pointer opens the clicked one. Neither path may hijack the other (hover must
   never change what Enter does).
5. **Familiar over clever.** Standard affordances, standard controls. A staff
   member fluent in Outlook and Excel should need no instruction here.

## Accessibility & Inclusion

WCAG 2.1 AA.

- All text meets 4.5:1 contrast (3:1 for large text). The teal "Open folder"
  button currently fails at ~3.1:1 and must be darkened.
- Visible focus indicators on every interactive element; never removed without
  replacement.
- The search + results pattern is exposed as a proper combobox/listbox to
  assistive tech, with result counts announced via a live region.
- All motion (the shake, the glow, transitions) respects
  `prefers-reduced-motion: reduce`.
- Colour is never the only carrier of meaning: the selected row, the error state,
  and the "no link on file" badge each pair colour with text or shape.
