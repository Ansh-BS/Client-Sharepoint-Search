# Plan — correct client IP behind the PythonAnywhere proxy

Spec: none written. This plan argues from three findings raised in the
2026-09-25 review of this repo, and from the PythonAnywhere behaviour
documented at https://help.pythonanywhere.com/pages/WebAppClientIPAddresses/
("web apps are load-balanced ... `remote_addr` gives the load-balancer's
internal IP; the real address is in `X-Real-IP`"). Rulings made without a
spec are provisional.

## The findings

1. `app.py:57` keys `Limiter` on `get_remote_address`, i.e.
   `request.remote_addr`. On the deployed host that is the load balancer,
   identical for every request. The `10 per 15 minutes` limit on `/login`
   is therefore a **firm-wide** budget: one staff member mistyping the
   password ten times locks out the whole office. Availability defect.
2. Every audit line (`app.py:113`, `246`, `249`) logs that same constant
   address, so the admin audit log's "from where" half is dead.
3. `WHAT_THIS_IS.md` promises "brute-force protection ... locks them out
   after a handful of attempts". True in code, misleading in effect.

## The root cause and its limit

All three share one cause: the app never reads the proxy's forwarding
headers. Reading them fixes 2 outright and 3's accuracy.

It does **not** fully fix 1. Office staff share one NAT'd public WAN
address, so a correct per-client-IP limiter still puts the whole office in
one bucket. Correct IP is necessary but not sufficient; the limit values
must also tolerate a shared office address. Both parts are in scope.

## Global Constraints

- Trusting a forwarding header when nothing trustworthy sets it lets any
  caller spoof their identity and bypass the limiter entirely — the exact
  risk `docs/superpowers/specs/2026-07-09-security-hardening-branding-design.md:33`
  declined ProxyFix over. That doc's premise ("no reverse proxy in front
  today") expired at deployment; its reasoning did not. So the new
  behaviour is **opt-in via env and off by default**: local dev and any
  direct-exposed run keep today's semantics.
- No new runtime dependency.
- Existing 109 tests stay green.
- Local only. Do not push (see the repo's standing instruction).

## Interfaces

- Task 1 **produces** `app.client_ip()` and the module constant
  `app.TRUST_PROXY`.
- Task 2 **consumes** `client_ip` as the limiter key func and the audit
  field; it changes only limit *values*.
- Task 3 consumes nothing; docs only.

---

## Task 1 — read the real client address when a trusted proxy is in front

Files: `app.py`, `tests/test_client_ip.py` (new), `.env.example`

1. Write `tests/test_client_ip.py` covering, against a request carrying
   `X-Real-IP: 203.0.113.7` and `X-Forwarded-For: 198.51.100.1, 203.0.113.7`:
   - `TRUST_PROXY` off (default) → `client_ip()` returns `request.remote_addr`,
     ignoring both headers.
   - `TRUST_PROXY` on → returns `203.0.113.7` from `X-Real-IP`.
   - `TRUST_PROXY` on, no `X-Real-IP`, `X-Forwarded-For` present → returns
     the **rightmost** entry. Rationale: a client may send its own
     `X-Forwarded-For`; an appending proxy leaves the value it added last,
     so the rightmost hop is the only one the proxy vouches for. Taking
     the leftmost would read attacker-controlled input.
   - `TRUST_PROXY` on, neither header → falls back to `request.remote_addr`.
   Expected: 4 failures, `client_ip` not defined.
2. Implement `TRUST_PROXY` (read from env, same false-y parsing style as
   `SESSION_COOKIE_SECURE` but defaulting **off**) and `client_ip()` in
   `app.py`. Expected: 4 pass.
3. Add `TRUST_PROXY` to `.env.example`, commented, with the warning that it
   must be set only when a proxy really is in front.
4. Run `python -m pytest -q`. Expected: 113 passed.
5. Commit.

## Task 2 — key the limiter and the audit log on the real address, and size the limits for a shared office address

Files: `app.py`, `tests/test_client_ip.py`

1. Write the failing tests:
   - The limiter's key func is `client_ip`, not `get_remote_address`.
   - With `TRUST_PROXY` on, two `/login` failures from two different
     `X-Real-IP` values do not share a bucket: exhausting one address's
     budget still leaves the other able to attempt.
   - An audit line records the forwarded address, not the peer address.
   Expected: failures.
2. Swap the limiter key func and the `_audit`/unlock-log IP source to
   `client_ip`. Expected: pass.
3. Raise the auth limits. `/login` and `/admin/unlock` go from
   `10 per 15 minutes` to `30 per 15 minutes`, because an entire office
   shares one public address and ten attempts across ~10 people is a
   self-inflicted outage. Thirty still caps an online guessing attack at
   ~2,900/day against a single shared password. Add a test asserting the
   configured value so the number is a decision, not a drift. Expected: pass.
4. Run `python -m pytest -q`. Expected: all green.
5. Commit.

## Task 3 — make the docs match the code

Files: `WHAT_THIS_IS.md`, `README.md`, `docs/DEPLOY_PYTHONANYWHERE.md`,
`docs/superpowers/specs/2026-07-09-security-hardening-branding-design.md`

1. `WHAT_THIS_IS.md`: restate the brute-force claim accurately — per-address
   throttling, and that a whole office sharing one internet connection
   shares one allowance.
2. `README.md`: document `TRUST_PROXY`.
3. `docs/DEPLOY_PYTHONANYWHERE.md`: add the step that sets `TRUST_PROXY=1`
   in the server `.env`, and a way to confirm the app now sees real
   addresses (check the error log's `ip=` field after one unlock).
4. `docs/superpowers/specs/2026-07-09-security-hardening-branding-design.md`:
   mark the "No ProxyFix" decision superseded, naming what changed
   (deployment put a proxy in front) rather than deleting the reasoning.
5. No test step — prose. Run `python -m pytest -q` to confirm nothing broke.
6. Commit.

## Review Focus

- `client_ip()` with a malformed or empty header value (`X-Forwarded-For: ,,`,
  whitespace-only `X-Real-IP`) — must not return an empty string as a
  limiter key, because an empty key silently pools every caller into one
  bucket, recreating finding 1.
- Whether `TRUST_PROXY` defaulting off leaves the deployed app in the
  broken state until someone edits the server `.env` — a fix that ships
  disabled is not a fix.
