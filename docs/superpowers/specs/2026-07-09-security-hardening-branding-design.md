# Security hardening + branding — design

Date: 2026-07-09

## Context

Project renamed/confirmed as **Client SharePoint Search** (the page already
titles itself this; README/docstrings get aligned). A security audit against
the sibling `benison-chatbot` project (separate, unrelated app — only its
*security patterns* are being ported, not its architecture) identified three
applicable gaps, approved for implementation:

1. **Rate limiting** on `/login` and `/admin` POST — brute-forceable shared
   password today, zero throttle.
2. **Security headers** — zero set today (chatbot sets X-Content-Type-Options,
   X-Frame-Options, Referrer-Policy, CSP, HSTS, no-cache on HTML).
3. **Session cookie hardening** — HttpOnly, SameSite, Secure (env-overridable
   for local HTTP dev), not explicitly configured today (Flask defaults only).

Plus: add the company logo (`benison's logo wit no name 1.png`, 1536×1024
RGBA, transparent) to the page header, resized/optimized for web use.

## Design

### 1. Rate limiting

Add `flask-limiter` to `requirements.txt`. In `app.py`:
- `Limiter(key_func=get_remote_address, default_limits=[])` — empty default so
  only decorated routes throttle, matching chatbot's pattern.
- `@limiter.limit("10 per 15 minutes", methods=["POST"])` on `/login`.
  (Raised to 30 on 2026-09-25 — staff share one office address, so ten
  attempts is a firm-wide allowance, not a per-person one.)
- `@limiter.limit("10 per 15 minutes", methods=["POST"])` on `/admin` (the
  admin-password check on file upload — same brute-force shape as login).
- No `ProxyFix` — this app runs directly (no reverse proxy in front today);
  adding it now would be speculative and, if ever wrong, would let an
  attacker spoof `X-Forwarded-For` to bypass the limiter. Skip until the app
  is actually deployed behind a proxy.

  > **SUPERSEDED 2026-09-25.** The premise expired: the app was deployed to
  > PythonAnywhere, which load-balances web apps, so `get_remote_address` now
  > returns the balancer for every request — the limiter pooled the whole firm
  > into one bucket and the audit log recorded one constant address. The
  > reasoning above still stands and is why the replacement is opt-in rather
  > than unconditional: `app.client_ip()` reads the forwarding headers only
  > when `TRUST_PROXY` is set, which is off by default and set solely on the
  > server. It reads PythonAnywhere's documented `X-Real-IP` rather than using
  > `ProxyFix`, and falls back to the rightmost `X-Forwarded-For` hop, never
  > the caller-chosen leftmost one. See
  > `docs/superpowers/plans/2026-09-25-client-ip-behind-proxy.md`.

### 2. Security headers

One `@app.after_request` hook (chatbot's `app.py:117-135` adapted, minus the
CORS/CDN-specific CSP origins this app doesn't need — no external scripts,
fonts, or CDNs are loaded here, so CSP can be simpler/stricter):
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Content-Security-Policy: default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`
  (no `'unsafe-inline'` — this app's CSS/JS are already external files, not
  inline, so a strict CSP costs nothing)
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (harmless
  on plain HTTP — browsers only honour it over HTTPS)
- HTML responses: `Cache-Control: no-cache, no-store, must-revalidate`,
  `Pragma: no-cache`, `Expires: 0` (so a UI change is never served stale)

### 3. Session cookie hardening

In `create_app`-equivalent setup in `app.py`:
- `SESSION_COOKIE_HTTPONLY = True`
- `SESSION_COOKIE_SAMESITE = "Lax"`
- `SESSION_COOKIE_SECURE` — default `True` (fail-safe), overridable via
  `SESSION_COOKIE_SECURE=false` env var for non-HTTPS LAN testing (chatbot's
  exact pattern). Localhost/127.0.0.1 counts as a secure context in modern
  browsers, so local dev over `http://127.0.0.1:5001` keeps working with the
  default `True`.

### 4. Branding — logo

- Resize/optimize `benison's logo wit no name 1.png` (1536×1024, 2MB) down to
  a header-appropriate size (e.g. ~200px tall, preserving aspect ratio and
  alpha transparency) and save as `static/logo.png` — the 2MB original is
  too large to ship as a page asset.
- Add to `templates/index.html` header, to the left of the "Client SharePoint
  Search" heading, sized via CSS (e.g. `height: 40px`) to sit inline with the
  title. Also add to `login.html` above the password form (first thing a
  user sees) and `admin.html` header, for consistency across all three pages.
- Alt text: `"Benison Solvers"`.

### 5. Naming consistency

- `README.md` title `# SharePoint Client Search` → `# Client SharePoint Search`.
- `app.py` module docstring `"""SharePoint client search — ..."""` →
  `"""Client SharePoint Search — Flask app (port 5001)."""`.
- `templates/index.html`/`login.html`/`admin.html` `<title>` tags already say
  "Client SharePoint Search" / "Log in — Client SharePoint Search" /
  similar — verify consistent, adjust if any drift.

## Files touched

`app.py`, `requirements.txt`, `templates/index.html`, `templates/login.html`,
`templates/admin.html`, `static/style.css` (logo sizing), `static/logo.png`
(new, resized asset), `README.md`.

## Testing

Manual verification via running the dev server + browser: confirm headers
present on a response (`curl -I`), confirm rate limit triggers after 10 rapid
POSTs to `/login`, confirm cookie flags via browser devtools, confirm logo
renders on all three pages, confirm existing search/login/admin flows still
work (regression check — this touches `app.py`, the most central file).
