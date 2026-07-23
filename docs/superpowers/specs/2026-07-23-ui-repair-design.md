# Design: SPA layout repair, app chrome, and search states

> **SUPERSEDED 2026-07-23.** The React SPA was abandoned and the vanilla
> Flask/Jinja frontend restored. See
> `docs/superpowers/specs/2026-07-23-vanilla-heroui-theme-design.md`.
> This document is kept for history; do not implement it.


**Date:** 2026-07-23
**Status:** Approved (brainstorming). Next: writing-plans.
**Branch:** `heroui-spa-rebuild` (continues the SPA rebuild; not yet merged to `main`)

## Goal

Repair what the React rebuild broke or dropped. The reported symptom — the "Sign in"
and "Review changes" buttons welded to the input above them — is one CSS bug, but
investigating it surfaced four correctness and dead-end problems that matter more.
Fix all five, and restore recent searches.

This is not a redesign. The visual language, HeroUI component set, and page structure
stay as they are.

## Background: why the buttons are attached

HeroUI puts card spacing on the block, not the slots:

```css
.card         { display:flex; flex-direction:column; gap:12px; padding:16px }
.card__content{ display:flex; flex-direction:column }   /* no padding of its own */
.card__footer { display:flex; flex-direction:row }      /* no padding of its own */
```

`gap` only separates **direct children** of the flex container. In `Login.tsx:36` and
`Admin.tsx:104` a `<form>` wraps content and footer:

```
.card  (flex column, gap 12px)
├── .card__header      ← the gap applies here…
└── <form>             ← …and stops here. display:block.
    ├── .card__content ← 0px between these two
    └── .card__footer  ← so the button sits flush against the input
```

`Search.tsx` has no form, which is why only those two screens are affected.

## Critique that motivated the scope

Assessed against Nielsen's 10 heuristics using the impeccable methodology
(`plugins/marketplaces/impeccable/.../reference/critique.md`, applied by hand — the
plugin is on disk but not installed). Deterministic scan: `detect.mjs --json
frontend/src` returned `[]`, exit 0; it is markup-oriented and likely sees little in
TSX. No browser inspection — source reading only.

**25/40 (Acceptable).** The prior vanilla build scored **35/40** on 2026-07-21
(`.impeccable/critique/2026-07-21T10-11-54Z__templates-index-html.md`). The backend
improved in the rebuild; the interface lost ground.

Lowest scores: user control (2 — no logout), consistency (2 — the gap bug),
recognition (2 — recents and match highlighting gone), flexibility (2 — keyboard
combobox gone), minimalism (2 — every client rendered on load), error recovery
(2 — load failure indistinguishable from empty), help (2 — admin lost its
spreadsheet-layout note).

## Scope

**In scope** — the gap bug, plus the four P0/P1 issues, plus recent searches:

1. **[P0]** Network failure renders as "No matching clients."
2. **[P1]** No way to log out.
3. **[P1]** `/admin` unreachable except by typing the URL.
4. **[P1]** Blank query renders every client.
5. **[P2]** The card gap bug.
6. Recent searches (user request; also the recognition-heuristic regression).

**Out of scope (YAGNI)** — deliberately left for a later pass:

- Keyboard combobox, arrow-key navigation, Enter-to-open.
- Match highlighting in results.
- The admin spreadsheet-layout help note.
- Any visual redesign or new personality.

## Components

### `components/AppHeader.tsx` (new)

One header shared by Search and Admin, so the two screens cannot drift apart again.

- **Layout:** page title left; theme toggle, one nav link, and Log out right.
- **Props:** `title: string` and `nav: ReactNode` (the caller supplies its own link).
  Search passes a link to `/admin` labelled "Admin"; Admin passes a link to `/`
  labelled "← Search".
- **Log out:** `POST /api/logout` → clear auth state → clear recent searches →
  navigate to `/login`.
- **Depends on:** `useAuth`, `recentSearches`, React Router's `Link`/`useNavigate`.
- `ThemeToggle` moves inside it; `Search.tsx` stops rendering it directly.

Clearing recents on logout is deliberate: client names should not survive sign-out on
a shared office machine.

### `lib/recentSearches.ts` (new)

Plain module over `localStorage`. No React, so it is testable on its own.

- **Storage key:** `sharepoint-search:recents`.
- **Shape:** `string[]`, newest first, max 3, case-insensitively de-duplicated.
- **API:** `getRecents(): string[]`, `addRecent(query: string): void`,
  `clearRecents(): void`.
- **Recorded when the user clicks through to a client**, not on every keystroke — a
  click is what proves the query worked. Storing the query text (`"ben"`), not the
  client name; clicking a recent refills the search box.
- Every read and write is wrapped in try/catch. A browser with storage disabled
  degrades to "no recents", never to a crash.

### `lib/auth.tsx` (modify)

Add `logout()` to the auth context: posts `/api/logout`, sets `staff` false. The
endpoint and its test already exist; nothing in the UI called it.

### `routes/Search.tsx` (modify)

Replace the single result list with explicit states:

| Condition | Renders |
|---|---|
| clients still loading | spinner (unchanged) |
| **load failed** | "Couldn't load the client list." + Retry button |
| empty query, recents exist | "Recent searches" + up to 3 chips + "412 clients" |
| empty query, no recents | "Type at least 2 letters. 412 clients." |
| 1 character | same hint |
| 2+ characters | "3 of 412 match" + up to 8 results |

- The 8-result cap matches the prior vanilla build.
- The count line is a live region so a screen reader hears the result count change.
- Retry re-runs the same fetch.

### `routes/Login.tsx`, `routes/Admin.tsx` (modify)

Move `<form>` outside `<Card>`:

```jsx
<form onSubmit={submit}>
  <Card>
    <Card.Header>…</Card.Header>
    <Card.Content>…</Card.Content>
    <Card.Footer>…</Card.Footer>
  </Card>
</form>
```

Header, Content and Footer become direct flex children of `.card` again, so HeroUI's
`gap-3` applies. No hardcoded spacing value, nothing to drift if HeroUI changes it.

Rejected alternatives:
- `<form className="contents">` — one word, but `display:contents` risks dropping the
  form from the accessibility tree.
- `<form className="flex flex-col gap-3">` — duplicates HeroUI's spacing token, which
  then silently diverges if HeroUI changes it.

Admin also gains `AppHeader`, replacing its bare `<h1>`.

## Data flow

```
AuthProvider ──useAuth()──► AppHeader ──logout()──► POST /api/logout
                                     └──clearRecents()──► localStorage

Search ──apiGet('/api/clients')──► clients | loadError
       └─ query === ''  ──► getRecents() ──► recent chips ──click──► setQuery(recent)
       └─ query.length >= 2 ──► fuse.search ──► top 8 ──click──► addRecent(query)
```

## Error handling

- **Client list fetch fails:** distinct `loadError` state, not an empty array. This is
  the P0 — today `.catch(() => setClients([]))` tells staff there are no clients when
  the API is down.
- **Logout request fails:** clear local auth state and redirect anyway. The cookie may
  survive server-side, but leaving the user apparently signed in on a shared machine is
  the worse failure.
- **localStorage unavailable or corrupt:** every access try/catch'd; treated as empty.

## Testing

Vitest + Testing Library, alongside the existing frontend tests.

**`lib/recentSearches.test.ts`**
- round-trips a query
- caps at 3, newest first
- de-duplicates case-insensitively
- `clearRecents` empties it
- survives a throwing `localStorage` without propagating

**`components/AppHeader.test.tsx`**
- renders the supplied title and nav link
- Log out calls `/api/logout`, clears recents, and navigates to `/login`
- still navigates when the logout request rejects

**`routes/Search.test.tsx`** (extend)
- failed client fetch shows the error and a Retry button, *not* "No matching clients"
- Retry refetches and renders results
- empty query with stored recents lists them; clicking one fills the box
- empty query with no recents shows the hint
- 1 character shows the hint; 2 characters show results
- results are capped at 8 and the count reports the true total
- clicking a result records the query

**`routes/Login.test.tsx`, `routes/Admin.test.tsx`** (extend)
- regression guard for the layout bug: assert `.card__footer` is a **direct child** of
  `.card` (`footer.parentElement` carries the `card` class), so re-introducing a
  wrapper element fails the test rather than silently collapsing the spacing

**Backend:** unchanged. No API changes in this work.

## Verification

- `cd frontend && npm run test -- --run` — all green
- `npm run lint` — no new warnings
- `python -m pytest -q` — still 34 passed
- `npm run build`, commit `frontend/dist`, then load `http://127.0.0.1:5001` in a
  browser: buttons detached from inputs on both forms, header on both screens, logout
  works, recents appear and clear on logout, no console errors, no CSP violations

## Open question

Recents store the **query text** you typed, not the client you opened. If reopening a
client in one click is more useful than replaying a search, say so before
implementation — it changes `recentSearches.ts` and the chip click handler, nothing
else.
