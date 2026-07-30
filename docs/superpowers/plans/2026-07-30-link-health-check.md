# Link Health Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect and report SharePoint client links that no longer resolve, and surface the broken ones to an admin, without ever mutating the client list.

**Architecture:** A pure stdlib-`urllib` engine (`link_health.py`) issues concurrent `HEAD` requests and classifies each link by HTTP status (`401`=alive, `404`=dead, `200`/other=suspect). A CLI (`check_links.py`) runs the engine and writes a small JSON report beside `clients.json`. The `/admin` page reads that report and renders a "Link health" panel; an optional, env-gated background re-run button is added only if SharePoint is reachable from the deployed server.

**Tech Stack:** Python 3, Flask, stdlib `urllib`/`concurrent.futures` (no new dependency), pytest.

## Global Constraints

- **No new dependency** — engine uses stdlib only (`urllib`, `concurrent.futures`, `socket`, `datetime`). `requirements.txt` stays flask/flask-limiter/python-dotenv/openpyxl/pytest.
- **Report-only** — nothing in this feature ever writes, edits, or deletes `clients.json` or a client row. The engine reads links and reports; that is all.
- **Detection rule (empirically verified 2026-07-30):** `401`→`ok`, `404`→`dead`, `200`/`3xx`/anything-else→`suspect`, empty link→`nolink`, timeout/conn-fail→`error`. Redirects are NOT followed — classification is on the first response's status code.
- **`suspect` means "needs review", never "delete"** — the check is unauthenticated and cannot prove a folder is gone.
- **`data/` is gitignored** — `clients.json` and `link_health.json` are server-side, untracked. The report is written beside `clients.json` wherever the check runs.
- **Report path derives from the clients path** — `link_health.json` sits in the same directory as the resolved `clients.json` (so the `CLIENTS_JSON` env override used in tests moves both together).
- **No JavaScript added** — stays in the pytest suite; no JS test runner.
- Test conventions: `tests/conftest.py` provides `client`, `logged_in`, `data_path`, `make_xlsx` fixtures. `data_path` sets `CLIENTS_JSON` to a `tmp_path` file. Admin routes require staff login (`logged_in`).

---

## Task 0: Reachability test (MANUAL — user runs, decides Task 5)

Not a coding task. Before Task 5, the user runs this in a **PythonAnywhere Bash console** to learn whether the free-tier proxy lets the server reach SharePoint:

```bash
python3 -c "import urllib.request as u; r=u.Request('https://benisonsolvers.sharepoint.com/:f:/s/OnSelfAssessment/IgAK0Zi84ZFOT7PGKH0LX5RdAbCWuBJdTTtmSZEUFotmWC4?e=hqEVEA', method='HEAD'); \
import urllib.error;
try:
    u.urlopen(r, timeout=15)
except urllib.error.HTTPError as e:
    print('status', e.code)
except Exception as e:
    print('BLOCKED', type(e).__name__, e)"
```

- Prints `status 401` → **reachable**; implement Task 5's button, deploy with `LINK_CHECK_ENABLED=1`.
- Prints `BLOCKED ...` (proxy/403/timeout) → **not reachable**; still implement Task 5 (it degrades safely), but leave `LINK_CHECK_ENABLED` unset in the server `.env`; the button stays hidden and `check_links.py` is run from the office machine that has `clients.json`.

Tasks 1–4 are identical regardless of the outcome.

---

## Task 1: Report persistence in `storage.py`

Add report read/write beside `clients.json`, and DRY the existing atomic-write logic into one helper.

**Files:**
- Modify: `storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: existing `_resolve(path)`.
- Produces:
  - `report_path(path=None) -> str` — path to `link_health.json` in the same dir as the resolved clients path.
  - `save_report(report: dict, path=None) -> None` — atomic write of the report JSON.
  - `load_report(path=None) -> dict | None` — the report dict, or `None` if the file does not exist.
  - `_atomic_write_json(obj, dest) -> None` — internal helper reused by `save_clients`, `save_pending`, `save_report`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_storage.py`:

```python
from storage import load_report, save_report, report_path


def test_load_report_missing_returns_none(tmp_path):
    assert load_report(tmp_path / "clients.json") is None


def test_save_then_load_report_roundtrip(tmp_path):
    p = tmp_path / "clients.json"
    report = {"checked_at": "2026-07-30T11:00:00Z", "total": 1,
              "counts": {"ok": 1, "dead": 0, "suspect": 0, "nolink": 0, "error": 0},
              "flagged": []}
    save_report(report, p)
    assert load_report(p) == report


def test_report_sits_beside_clients(tmp_path):
    p = tmp_path / "clients.json"
    assert report_path(p) == str(tmp_path / "link_health.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_storage.py -k report -v`
Expected: FAIL with `ImportError: cannot import name 'load_report'`.

- [ ] **Step 3: Write minimal implementation**

In `storage.py`, add the helper and refactor the two existing `mkstemp`/`os.replace` blocks in `save_clients` and `save_pending` to call it, then add the report functions:

```python
def _atomic_write_json(obj, dest):
    directory = os.path.dirname(dest) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, dest)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def report_path(path=None):
    base = _resolve(path)
    return os.path.join(os.path.dirname(base) or ".", "link_health.json")


def save_report(report, path=None):
    _atomic_write_json(report, report_path(path))


def load_report(path=None):
    src = report_path(path)
    if not os.path.exists(src):
        return None
    with open(src, encoding="utf-8") as f:
        return json.load(f)
```

Refactor `save_clients` body to:

```python
def save_clients(clients, path=None):
    _atomic_write_json(clients, _resolve(path))
```

And in `save_pending`, replace its `mkstemp`/`fdopen`/`os.replace` block with `_atomic_write_json(clients, dest)` (keep the `_TOKEN_RE`/`dest is None` guard and the `_sweep_pending(path)` call before the write).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_storage.py -v`
Expected: PASS (new report tests + all existing storage tests still green after the refactor).

- [ ] **Step 5: Commit**

```bash
git add storage.py tests/test_storage.py
git commit -m "feat: report persistence beside clients.json + atomic-write helper"
```

---

## Task 2: Detection engine `link_health.py`

**Files:**
- Create: `link_health.py`
- Test: `tests/test_link_health.py`

**Interfaces:**
- Consumes: nothing from the app.
- Produces:
  - `check_link(url, timeout=15) -> tuple[str, int | None]` — `(category, status)`; category in `{"ok","dead","suspect","nolink","error"}`.
  - `check_all(clients, workers=8, timeout=15) -> dict` — report dict with keys `checked_at`, `total`, `counts` (dict of the five categories), `flagged` (list of `{"id","name","category","status"}` for every non-`ok` client).

- [ ] **Step 1: Write the failing test**

Create `tests/test_link_health.py`:

```python
import urllib.error

import link_health


def _fake_opener(mapping):
    """mapping: url -> int status, or url -> Exception to raise."""
    class _Resp:
        def __init__(self, status):
            self.status = status
        def close(self):
            pass
    class _Opener:
        def open(self, req, timeout=None):
            outcome = mapping[req.full_url]
            if isinstance(outcome, Exception):
                raise outcome
            if 400 <= outcome:
                raise urllib.error.HTTPError(req.full_url, outcome, "e", {}, None)
            return _Resp(outcome)
    return _Opener()


def test_classify_alive_401(monkeypatch):
    monkeypatch.setattr(link_health, "_opener",
                        _fake_opener({"http://x": 401}))
    assert link_health.check_link("http://x") == ("ok", 401)


def test_classify_dead_404(monkeypatch):
    monkeypatch.setattr(link_health, "_opener",
                        _fake_opener({"http://x": 404}))
    assert link_health.check_link("http://x") == ("dead", 404)


def test_classify_suspect_200(monkeypatch):
    monkeypatch.setattr(link_health, "_opener",
                        _fake_opener({"http://x": 200}))
    assert link_health.check_link("http://x") == ("suspect", 200)


def test_classify_error_on_timeout(monkeypatch):
    monkeypatch.setattr(link_health, "_opener",
                        _fake_opener({"http://x": TimeoutError()}))
    assert link_health.check_link("http://x") == ("error", None)


def test_empty_link_is_nolink():
    assert link_health.check_link("") == ("nolink", None)
    assert link_health.check_link(None) == ("nolink", None)


def test_check_all_report_shape(monkeypatch):
    clients = [
        {"id": "A1", "name": "Alive", "link": "http://ok"},
        {"id": "D1", "name": "Dead", "link": "http://dead"},
        {"id": "S1", "name": "Suspect", "link": "http://susp"},
        {"id": "N1", "name": "NoLink", "link": ""},
    ]
    monkeypatch.setattr(link_health, "check_link", lambda url, timeout=15: {
        "http://ok": ("ok", 401),
        "http://dead": ("dead", 404),
        "http://susp": ("suspect", 200),
        "": ("nolink", None),
    }[url])
    report = link_health.check_all(clients, workers=2)
    assert report["total"] == 4
    assert report["counts"] == {"ok": 1, "dead": 1, "suspect": 1,
                                "nolink": 1, "error": 0}
    flagged_ids = {f["id"] for f in report["flagged"]}
    assert flagged_ids == {"D1", "S1", "N1"}   # every non-ok, ok excluded
    assert report["checked_at"].endswith("Z")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_link_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_health'`.

- [ ] **Step 3: Write minimal implementation**

Create `link_health.py`:

```python
"""Best-effort health check of client SharePoint links.

Unauthenticated HEAD requests distinguish alive from dead shares (verified
2026-07-30): a live share answers 401 (auth wall, resource exists), a
revoked/typo'd token answers 200 (generic login/error page), a missing site
answers 404. This cannot prove folder contents or permissions, so any non-ok
result is "needs review", never grounds to delete a client.
"""
import datetime
import socket
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

USER_AGENT = "benison-link-health-check/1.0"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Classify on the first response; a 3xx must not be followed to a login page.
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _classify(code):
    if code == 401:
        return "ok"
    if code == 404:
        return "dead"
    return "suspect"


def check_link(url, timeout=15):
    if not url:
        return ("nolink", None)
    req = urllib.request.Request(url, method="HEAD",
                                headers={"User-Agent": USER_AGENT})
    try:
        resp = _opener.open(req, timeout=timeout)
        code = getattr(resp, "status", None) or resp.getcode()
        resp.close()
    except urllib.error.HTTPError as exc:
        code = exc.code
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        return ("error", None)
    return (_classify(code), code)


def check_all(clients, workers=8, timeout=15):
    counts = {"ok": 0, "dead": 0, "suspect": 0, "nolink": 0, "error": 0}
    flagged = []

    def _one(c):
        cat, status = check_link(c.get("link"), timeout)
        return c, cat, status

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for c, cat, status in ex.map(_one, clients):
            counts[cat] += 1
            if cat != "ok":
                flagged.append({"id": c.get("id", ""), "name": c.get("name", ""),
                                "category": cat, "status": status})

    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return {
        "checked_at": now.isoformat().replace("+00:00", "Z"),
        "total": len(clients),
        "counts": counts,
        "flagged": flagged,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_link_health.py -v`
Expected: PASS (all six tests).

- [ ] **Step 5: Commit**

```bash
git add link_health.py tests/test_link_health.py
git commit -m "feat: link health detection engine (stdlib urllib, HEAD classify)"
```

---

## Task 3: CLI `check_links.py`

**Files:**
- Create: `check_links.py`
- Test: `tests/test_check_links.py`

**Interfaces:**
- Consumes: `storage.load_clients`, `storage.save_report`, `storage.load_report`, `link_health.check_all`.
- Produces: `main(argv=None) -> dict` — loads clients, runs the engine, writes the report, prints a one-line summary, returns the report.

- [ ] **Step 1: Write the failing test**

Create `tests/test_check_links.py`:

```python
import check_links
import link_health
from storage import load_report, save_clients


def test_cli_writes_report_beside_clients(tmp_path, monkeypatch, capsys):
    p = tmp_path / "clients.json"
    save_clients([{"id": "A1", "name": "Alive", "link": "http://ok"},
                  {"id": "D1", "name": "Dead", "link": "http://dead"}], p)
    monkeypatch.setattr(link_health, "check_link", lambda url, timeout=15:
                        ("ok", 401) if url == "http://ok" else ("dead", 404))

    report = check_links.main(["--clients", str(p), "--workers", "2"])

    on_disk = load_report(p)
    assert on_disk == report
    assert on_disk["counts"]["dead"] == 1
    assert [f["id"] for f in on_disk["flagged"]] == ["D1"]
    assert "1 dead" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_links.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'check_links'`.

- [ ] **Step 3: Write minimal implementation**

Create `check_links.py`:

```python
"""CLI: check every client's SharePoint link and write a health report.

Runs the same engine the admin button uses. Safe to run on a PC/office
machine or on the server; it writes link_health.json beside clients.json and
never edits the client list.

    python check_links.py [--workers 8] [--timeout 15] [--clients path.json]
"""
import argparse

from link_health import check_all
from storage import load_clients, save_report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check client SharePoint links.")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--clients", default=None,
                    help="clients.json path (default: CLIENTS_JSON env or data/)")
    args = ap.parse_args(argv)

    clients = load_clients(args.clients)
    report = check_all(clients, workers=args.workers, timeout=args.timeout)
    save_report(report, args.clients)
    c = report["counts"]
    print(f'{c["ok"]} ok, {c["dead"]} dead, {c["suspect"]} suspect, '
          f'{c["nolink"]} no-link, {c["error"]} error')
    return report


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_links.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add check_links.py tests/test_check_links.py
git commit -m "feat: check_links CLI runs the engine and writes the report"
```

---

## Task 4: Admin display panel

Show the last report on `/admin` (read-only). No button yet.

**Files:**
- Modify: `app.py` (the `admin` view + a context value for the enabled flag), `app.py:ASSET_VERSION`
- Modify: `templates/admin.html`
- Modify: `static/style.css`
- Test: `tests/test_admin.py`

**Interfaces:**
- Consumes: `storage.load_report`.
- Produces: `admin.html` renders a `health` panel when `render_template` is passed `health=<report|None>` and `link_check_enabled=<bool>`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_admin.py`:

```python
from storage import save_report


def test_admin_shows_no_check_yet(logged_in, data_path):
    resp = logged_in.get("/admin")
    assert b"No link check has been run yet" in resp.data


def test_admin_shows_all_ok(logged_in, data_path):
    save_report({"checked_at": "2026-07-30T11:00:00Z", "total": 3,
                 "counts": {"ok": 3, "dead": 0, "suspect": 0, "nolink": 0,
                            "error": 0}, "flagged": []}, data_path)
    resp = logged_in.get("/admin")
    assert b"All 3 links OK" in resp.data


def test_admin_lists_flagged(logged_in, data_path):
    save_report({"checked_at": "2026-07-30T11:00:00Z", "total": 2,
                 "counts": {"ok": 0, "dead": 1, "suspect": 1, "nolink": 0,
                            "error": 0},
                 "flagged": [
                     {"id": "D1", "name": "Dead Client", "category": "dead",
                      "status": 404},
                     {"id": "S1", "name": "Suspect Client", "category": "suspect",
                      "status": 200}]}, data_path)
    resp = logged_in.get("/admin")
    assert b"Dead Client" in resp.data
    assert b"Suspect Client" in resp.data
    assert b"dead" in resp.data and b"suspect" in resp.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_admin.py -k "check or ok or flagged" -v`
Expected: FAIL (`No link check has been run yet` not in response).

- [ ] **Step 3: Write minimal implementation**

In `app.py`, import `load_report` (extend the existing storage import line) and add near `ASSET_VERSION`:

```python
LINK_CHECK_ENABLED = os.getenv("LINK_CHECK_ENABLED", "").strip().lower() in (
    "1", "true", "yes")
```

Bump the cache tag: `ASSET_VERSION = "12"` (style.css changes this task).

Change the final `render_template` in `admin()` to pass the report and flag:

```python
    return render_template("admin.html", result=result, error=error,
                           preview=preview, health=load_report(),
                           link_check_enabled=LINK_CHECK_ENABLED)
```

In `templates/admin.html`, inside the `{% else %}` branch, **after** the closing `</div>` of the upload-form `<div class="card">` and before the `{% endif %}` that closes the preview/else, add:

```html
  <section class="card link-health">
    <h2>Link health</h2>
    {% if not health %}
      <p class="sub">No link check has been run yet. Run
        <code>python check_links.py</code>{% if link_check_enabled %} or use the
        button below{% endif %} to check every client's SharePoint link.</p>
    {% else %}
      <p class="sub">Last checked {{ health.checked_at }}.
        {{ health.counts.ok }} ok, {{ health.counts.dead }} dead,
        {{ health.counts.suspect }} suspect, {{ health.counts.nolink }} no-link,
        {{ health.counts.error }} error.</p>
      {% if not health.flagged %}
        <p class="ok" role="status">All {{ health.total }} links OK ✓</p>
      {% else %}
        <table class="health-table">
          <thead><tr><th>Client ID</th><th>Name</th><th>Status</th><th>Code</th></tr></thead>
          <tbody>
          {% for f in health.flagged %}
            <tr>
              <td>{{ f.id }}</td>
              <td>{{ f.name }}</td>
              <td><span class="badge badge-{{ f.category }}">{{ f.category }}</span></td>
              <td>{{ f.status if f.status is not none else '—' }}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      {% endif %}
    {% endif %}
  </section>
```

In `static/style.css`, append (colour paired with the text label, per the accessibility rule — the word "dead"/"suspect" carries the meaning, colour only reinforces):

```css
.link-health { margin-top: 1rem; }
.health-table { width: 100%; border-collapse: collapse; margin-top: .5rem; }
.health-table th, .health-table td {
  text-align: left; padding: .4rem .5rem;
  border-bottom: 1px solid var(--border);
}
.badge {
  display: inline-block; padding: .1rem .5rem; border-radius: 999px;
  font-size: .85em; font-weight: 600;
}
.badge-dead    { background: var(--danger-bg); color: var(--danger-fg); }
.badge-suspect { background: var(--warn-bg);   color: var(--warn-fg); }
.badge-nolink  { background: var(--muted-bg);  color: var(--muted-fg); }
.badge-error   { background: var(--muted-bg);  color: var(--muted-fg); }
```

> If any of `--danger-bg/-fg`, `--warn-bg/-fg`, `--muted-bg/-fg` are not already defined in the `:root` blocks of `style.css`, add them in both the light `:root` block and the `:root.dark` block, choosing values that meet 4.5:1 text contrast (reuse the existing error colour for danger). Check with a grep for `--danger` / `--warn` / `--muted` before adding, to avoid duplicates.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin.py -v`
Expected: PASS (new panel tests + all existing admin tests).

- [ ] **Step 5: Commit**

```bash
git add app.py templates/admin.html static/style.css tests/test_admin.py
git commit -m "feat: link-health panel on admin page (read-only)"
```

---

## Task 5: Gated server re-run button

Add a background re-run button, shown only when `LINK_CHECK_ENABLED`.

**Files:**
- Modify: `app.py` (the `admin` POST branch; add `threading` import)
- Modify: `templates/admin.html`
- Test: `tests/test_admin.py`

**Interfaces:**
- Consumes: `link_health.check_all`, `storage.save_report`, `storage.load_clients`, `LINK_CHECK_ENABLED`.
- Produces: POST `action="check_links"` on `/admin` — if enabled, starts a background thread that writes the report and re-renders with `checking=True`; if disabled, sets `error`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_admin.py`:

```python
import app as app_module


def test_button_hidden_when_disabled(logged_in, data_path, monkeypatch):
    monkeypatch.setattr(app_module, "LINK_CHECK_ENABLED", False)
    resp = logged_in.get("/admin")
    assert b'value="check_links"' not in resp.data


def test_button_shown_when_enabled(logged_in, data_path, monkeypatch):
    monkeypatch.setattr(app_module, "LINK_CHECK_ENABLED", True)
    resp = logged_in.get("/admin")
    assert b'value="check_links"' in resp.data


def test_check_links_post_disabled_is_refused(logged_in, data_path, monkeypatch):
    monkeypatch.setattr(app_module, "LINK_CHECK_ENABLED", False)
    resp = logged_in.post("/admin", data={"action": "check_links"})
    assert b"not enabled" in resp.data


def test_check_links_post_enabled_runs(logged_in, data_path, monkeypatch):
    monkeypatch.setattr(app_module, "LINK_CHECK_ENABLED", True)
    ran = {}
    def fake_check_all(clients, **kw):
        ran["called"] = True
        return {"checked_at": "2026-07-30T11:00:00Z", "total": 0,
                "counts": {"ok": 0, "dead": 0, "suspect": 0, "nolink": 0,
                           "error": 0}, "flagged": []}
    monkeypatch.setattr(app_module, "check_all", fake_check_all)
    resp = logged_in.post("/admin", data={"action": "check_links"})
    assert b"Check running" in resp.data
```

Note: the background thread runs `fake_check_all` fast; if the assertion on `ran` is flaky under threading, assert only on the response text (`Check running`), which is set synchronously.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_admin.py -k "button or check_links_post" -v`
Expected: FAIL (`value="check_links"` not present; POST returns the upload form).

- [ ] **Step 3: Write minimal implementation**

In `app.py`, add `import threading` (top) and extend the storage/engine imports so `check_all`, `save_report`, `load_clients` are available (add `from link_health import check_all`). Referencing `LINK_CHECK_ENABLED` and `check_all` as module globals (`app_module.` in tests) requires they are looked up at call time — they already are, since the view reads the module global.

In `admin()`, add a branch alongside the existing `if action == "cancel"` / `elif action == "confirm"` chain, **before** the final `else:` preview branch:

```python
        elif action == "check_links":
            if not LINK_CHECK_ENABLED:
                error = "Link checking is not enabled on this server."
            else:
                snapshot = load_clients()

                def _run(clients):
                    save_report(check_all(clients))

                threading.Thread(target=_run, args=(snapshot,),
                                 daemon=True).start()
                checking = True
```

Initialise `checking = False` at the top of `admin()` beside `result = None`, and pass it to the template:

```python
    return render_template("admin.html", result=result, error=error,
                           preview=preview, health=load_report(),
                           link_check_enabled=LINK_CHECK_ENABLED,
                           checking=checking)
```

In `templates/admin.html`, inside the `.link-health` section, at the top of the `{% else %}` (report exists) area OR just under the `<h2>`, add the running notice and the button:

```html
    {% if checking %}
      <p class="ok" role="status">Check running… refresh in a minute to see results.</p>
    {% endif %}
    {% if link_check_enabled %}
      <form method="post" class="inline-form">
        <input type="hidden" name="action" value="check_links">
        <button type="submit" class="secondary">Check all links now</button>
      </form>
    {% endif %}
```

Place this block so it renders in both the "no report yet" and "report exists" states (i.e. inside `.link-health` but outside the `{% if not health %}/{% else %}` split — e.g. right after the `<h2>Link health</h2>`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass (44 prior + the new link-health/report/CLI/admin tests).

- [ ] **Step 6: Commit**

```bash
git add app.py templates/admin.html tests/test_admin.py
git commit -m "feat: gated background re-run button for link health"
```

---

## Post-implementation (not a coding task)

- **Deploy note:** `data/` is untracked, so `link_health.json` is written on whichever machine runs the check; nothing to push. If Task 0 showed the server is reachable, set `LINK_CHECK_ENABLED=1` in the server `.env` and reload; otherwise run `python check_links.py` on the office machine that holds `clients.json`.
- **ASSET_VERSION** was bumped to `12` in Task 4 (style.css changed) — required for staff to get the new CSS after deploy.
- **Manual smoke test:** log in as staff → `/admin` → confirm the "Link health" panel renders; if enabled, click "Check all links now", wait, refresh, confirm flagged clients (if any) appear.
- Pushing to origin still needs explicit user OK (standing rule).

## Self-Review notes

- **Spec coverage:** engine+classification (Task 2), report file+CLI (Tasks 1,3), admin display (Task 4), gated server button + reachability gate (Tasks 0,5), report-only invariant (asserted implicitly — no task writes clients.json), tests in pytest with no JS runner (all tasks). Config knobs `workers`/`timeout`/`LINK_CHECK_ENABLED` present.
- **Type consistency:** `check_link -> (category, status)` and `check_all -> report dict` names/shapes match across Tasks 2, 3, 5; report keys (`checked_at/total/counts/flagged`, flagged rows `id/name/category/status`) identical in engine, storage tests, CLI, and template.
- **No placeholders:** every code step contains full code.
