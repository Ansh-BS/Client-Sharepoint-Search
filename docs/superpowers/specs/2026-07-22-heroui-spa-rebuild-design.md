# Design: sharepoint-search → React + HeroUI v3 SPA

**Date:** 2026-07-22
**Status:** Approved (brainstorming). Next: writing-plans.

## Goal

Rebuild the entire sharepoint-search frontend (all 3 pages — public search, login,
admin upload) as a single-page React app using HeroUI v3, replacing the current
Flask/Jinja server-rendered templates + vanilla JS. Flask becomes a JSON API and
static server. Visual language adopts HeroUI v3's own modern look (rounded surfaces,
oklch neutrals, clean spacing), with a light + dark toggle.

## Decisions (locked in brainstorming)

- **Scope:** all 3 pages.
- **Serving:** same-origin — Vite builds to `frontend/dist/`, Flask serves it. No CORS,
  no separate host.
- **Search:** client-side fuzzy (Fuse.js in React over `/api/clients`). Current dataset
  size makes a server search endpoint unnecessary.
- **Theme:** light + dark toggle, HeroUI-native modern aesthetic.
- **Build/deploy:** build locally, commit `frontend/dist/` to the repo. Deploy stays
  `git pull` + Reload on PythonAnywhere — no Node required on the server.

## Non-goals (YAGNI)

- No server-side search endpoint.
- No E2E/Playwright suite (component + API tests only).
- No new auth model — keep the existing Flask session cookie.
- No CDN / separate static host.
- No feature additions beyond parity with today's three pages + a dark-mode toggle.

## Architecture

**Monorepo.** Add `frontend/` (Vite + React 19 + TypeScript + Tailwind CSS v4 +
HeroUI v3) inside the existing repo. Python backend stays at the repo root.

**Flask = JSON API + static server.**
- Vite builds to `frontend/dist/`.
- Flask serves `dist/assets/*` (hashed JS/CSS) and returns `dist/index.html` for every
  non-`/api`, non-asset route (SPA catch-all).
- Because `index.html` is always returned for app routes, deep links and refreshes work;
  React Router renders the right view client-side.

**Client routing (React Router):** `/` (search), `/login`, `/admin`.
An auth guard calls `GET /api/me` on load; if not staff, redirect to `/login`.

## API surface (Flask)

All under `/api/`. `staff_required` already returns `401 {"error":"unauthenticated"}`
for `/api/*`, so the guard is mostly in place.

| Method | Route | Body / params | Response | Notes |
|--------|-------|---------------|----------|-------|
| POST | `/api/login` | `{password}` | 200 `{staff:true}` / 401 `{error}` | Sets session. Rate-limited 10/15min |
| POST | `/api/logout` | — | 204 | Clears session |
| GET | `/api/me` | — | `{staff: bool}` | Public; SPA auth bootstrap |
| GET | `/api/clients` | — | `[{id,name,link}]` | **Exists today.** staff_required |
| POST | `/api/admin/preview` | multipart `file`, `admin_password` | `{token,count,current_count,added[],dropped[],missing[]}` / 400 `{error}` | staff_required. Rate-limited |
| POST | `/api/admin/confirm` | `{token}` | `{count,missing[]}` / 400 `{error}` | staff_required |
| POST | `/api/admin/cancel` | `{token}` | 204 | staff_required |

The admin preview→confirm→cancel logic (xlsx parse, pending stash, session-bound
token acting as CSRF guard, constant-time compare, diff of dropped/added/missing) is
**unchanged** — only the transport changes from form-POST + `render_template` to
JSON responses. `_client_key`, `_diff_clients`, `parse_xlsx`, `storage.*` untouched.

## Auth & CSRF

- Keep the Flask **session cookie**: `HTTPOnly`, `SameSite=Lax`, `Secure` (as today).
  Same-origin SPA → the cookie is sent automatically; no tokens, no CORS.
- CSRF defense for state-changing endpoints:
  - `SameSite=Lax` blocks the cookie on cross-site POSTs.
  - Require `Content-Type: application/json` (or a custom header like `X-Requested-With`)
    on `/api/login`, `/api/logout`, `/api/admin/confirm`, `/api/admin/cancel`. A cross-site
    HTML form cannot set these, so it cannot forge the request.
  - `/api/admin/preview` and `/api/admin/confirm` additionally keep the existing
    session-bound token flow.
- The SPA's `lib/api.ts` fetch wrapper always sends `credentials: 'same-origin'` and the
  JSON content-type / custom header.

## CSP

- Vite output is hashed, same-origin JS/CSS → **`script-src 'self'` stays strict.**
- **Risk to verify at build:** React/HeroUI may emit inline `style="…"` attributes
  (e.g. Modal positioning, animations). `style-src 'self'` blocks inline styles. If the
  built app needs them, relax **only** `style-src` to `'self' 'unsafe-inline'` — never
  `script-src`. Confirm empirically before finalizing headers; document the final CSP.
- Keep `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, HSTS.
- HTML `Cache-Control: no-store` still applies to `index.html`; hashed assets can be
  long-cached (add far-future cache headers for `dist/assets/*`). `ASSET_VERSION` is
  retired — Vite's content hashes replace it.

## Frontend structure

```
frontend/
  index.html
  vite.config.ts            # react + @tailwindcss/vite plugins; build.outDir = dist
  package.json
  src/
    main.tsx                # createRoot; mounts <App/>
    App.tsx                 # Router + HeroUI theme + <Toast.Provider/>
    routes/
      Search.tsx            # SearchField + Fuse.js over /api/clients; result list
      Login.tsx             # password field → POST /api/login
      Admin.tsx             # dropzone upload → preview Modal → confirm; toasts
    lib/
      api.ts                # fetch wrapper: credentials, json header, 401 → /login
      auth.tsx              # auth context + <RequireStaff> guard
    components/             # shared bits (ThemeToggle, ClientRow, etc.)
    theme/tokens.css        # HeroUI theme import + any brand overrides (light+dark)
  dist/                     # built output, committed to git
```

**Component mapping (HeroUI v3):**
- Search: `SearchField`/`Input`, result rows in a `Card` or simple list, `Link` to
  SharePoint URL, "No link on file" state for `link == ""`.
- Login: `Card` + `TextField`/`Label`/`Input` (password) + `Button`. Inline error text.
- Admin: dropzone (drag-drop + click), client-side file validation, `Modal`
  (trigger/Backdrop/Container/Dialog) for the preview/confirm step, `Toast`
  (`toast.success` on replace, `toast.info` on cancel), `Button` loading state.
- Global: `Switch` for dark-mode toggle; `Spinner` for async states.

**Search behavior:** on load, `GET /api/clients` once; build a Fuse index over `name`;
filter live as the user types; empty query shows all (or a prompt). Mirrors current
`search.js` behavior. Reuse the existing dataset shape `{id, name, link}`.

## Testing

- **Backend (pytest):** rewrite the suite for the JSON API — `/api/login` success/fail
  + rate limit, `/api/me`, `/api/clients` auth guard (401 unauth), admin
  preview→confirm→cancel happy path, wrong admin password, expired/invalid token,
  bad file. Keep coverage at least at parity with the current 24 tests.
- **Frontend (Vitest + React Testing Library):** search filtering, auth guard redirect,
  admin preview→confirm flow, file validation messages, theme toggle.
- No JS E2E harness (out of scope).

## Deploy

- Local: `npm ci && npm run build` in `frontend/` → `frontend/dist/`, commit `dist/`.
- Server (PythonAnywhere): `git pull` + Reload. No Node on the server.
- WSGI serves Flask; Flask serves `dist/`. Confirm the WSGI/static config points at the
  catch-all + assets correctly (update `docs/DEPLOY_*` / `UPDATE_PYTHONANYWHERE.md`).

## Phasing (feeds the implementation plan)

0. **Backend API.** Add `/api/login`, `/api/logout`, `/api/me`, `/api/admin/preview`,
   `/api/admin/confirm`, `/api/admin/cancel` alongside the existing HTML routes (both
   work during migration). Add/rewrite pytest for the JSON endpoints.
1. **Scaffold `frontend/`.** Vite + React + Tailwind v4 + HeroUI wired; theme + router
   + `Toast.Provider`. Build the Search page against `/api/clients`.
2. **Login + auth guard.** `Login.tsx`, `lib/auth.tsx`, `RequireStaff`, `lib/api.ts`
   401 handling.
3. **Admin flow.** Dropzone → `/api/admin/preview` → Modal → `/api/admin/confirm` /
   `/api/admin/cancel`, with toasts and loading states. Frontend tests.
4. **Cutover.** Flask serves `dist/` (catch-all + assets), delete Jinja templates
   (`index.html`, `login.html`, `admin.html`) and the old `static/*.js` / `style.css`,
   finalize CSP (verify style-src), retire `ASSET_VERSION`, update deploy docs, full
   regression (backend + frontend).

## Risks / open items

- **style-src / CSP:** may need `'unsafe-inline'` for inline styles — verify at Phase 4.
- **dist in git:** committing built assets bloats history slightly; acceptable trade for
  a Node-free server. Consider a `.gitattributes`/squash later if it grows.
- **Session cookie + fetch:** ensure `Secure` cookie works on the PA HTTPS domain and
  that local dev (`SESSION_COOKIE_SECURE=false`) still logs in.
- **Rate limiter:** `flask-limiter` keys on remote address; unchanged, but confirm the
  JSON login path is covered by the same limit as the old form path.
