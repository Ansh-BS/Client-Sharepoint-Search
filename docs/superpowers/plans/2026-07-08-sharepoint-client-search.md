# SharePoint Client Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Login-gated Flask website where staff type a (possibly misspelled) client name or ID and get fuzzy-matched suggestions linking to the client's SharePoint folder.

**Architecture:** Flask app on port 5001. An xlsx parser converts the "SharePoint Links for Clients" spreadsheet into `data/clients.json`; the search page fetches that list once via `/api/clients` and does fuzzy matching client-side with vendored Fuse.js. An admin page (staff session + separate admin password) uploads a replacement xlsx atomically.

**Tech Stack:** Python 3.10+, Flask 3.x, openpyxl, python-dotenv, pytest, Fuse.js 7 (vendored), vanilla JS/CSS. All Python deps already installed system-wide — no venv needed.

**Spec:** `docs/superpowers/specs/2026-07-08-sharepoint-client-search-design.md`

## Global Constraints

- Project root: `C:\Users\Ansh 2\Documents\vs code\file management\sharepoint-search` — all paths below relative to it; run all commands from it.
- App binds `127.0.0.1:5001` (benison-chatbot owns 5000).
- Required `.env` keys: `SECRET_KEY`, `STAFF_PASSWORD`, `ADMIN_PASSWORD`. App refuses to start if any unset.
- Optional env `CLIENTS_JSON` overrides the data file path (tests use it); default `data/clients.json`.
- Client record shape everywhere: `{"id": str, "name": str, "link": str-or-null}`.
- No client data in git: `data/` and `.env` gitignored; the real spreadsheet stays outside the repo at `..\SharePoint Links for Clients S.A.xlsx`.
- Fuse.js vendored at `static/fuse.min.js` (v7.0.0); no CDN at runtime.
- Search behavior: results after 2+ chars, top 8 matches, Fuse `threshold: 0.4`, `ignoreLocation: true`, keys name (weight 0.7) + id (0.3).
- Parser module is named `xlsx_parser.py` (NOT `parser.py` — avoids stdlib shadowing).
- openpyxl must load workbooks WITHOUT `read_only=True` (read-only mode drops hyperlinks).
- Test commands: `python -m pytest tests/ -v` from project root.
- Commit after every task; never push (local-only repo by user rule).

---

### Task 1: Project scaffolding + xlsx parser

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`
- Create: `xlsx_parser.py`
- Create: `tests/conftest.py` (partial — env + `make_xlsx` fixture only)
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `xlsx_parser.parse_xlsx(source) -> list[dict]` — `source` is a path or file-like object; returns `[{"id": str, "name": str, "link": str|None}, ...]`; raises `xlsx_parser.ParseError` (subclass of `Exception`) on invalid file or zero valid rows. Also test fixture `make_xlsx(path, rows, header=True)` where `rows` is a list of `(client_id, name, link_or_None)` tuples.

- [ ] **Step 1: Create scaffolding files**

`requirements.txt`:
```
flask>=3.0
python-dotenv>=1.0
openpyxl>=3.1
pytest>=8.0
```

`.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
data/
.env
```

`.env.example`:
```
SECRET_KEY=replace-with-long-random-string
STAFF_PASSWORD=replace-me
ADMIN_PASSWORD=replace-me-with-something-different
```

- [ ] **Step 2: Write conftest with env defaults and xlsx-builder fixture**

`tests/conftest.py`:
```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("STAFF_PASSWORD", "staffpw")
os.environ.setdefault("ADMIN_PASSWORD", "adminpw")

import openpyxl
import pytest


@pytest.fixture
def make_xlsx():
    """Build a spreadsheet matching the real file's layout.

    rows: list of (client_id, name, link_or_None). Column C gets the name
    as cell text and the link (if any) as the cell's hyperlink target.
    """
    def _make(path, rows, header=True):
        wb = openpyxl.Workbook()
        ws = wb.active
        if header:
            ws.append(["Client ID", "Particulars", "Sharepoint Path"])
        for cid, name, link in rows:
            ws.append([cid, name, name])
            if link:
                ws.cell(row=ws.max_row, column=3).hyperlink = link
        wb.save(path)
        return path
    return _make
```

- [ ] **Step 3: Write the failing parser tests**

`tests/test_parser.py`:
```python
import pytest

from xlsx_parser import parse_xlsx, ParseError


def test_parses_clients_with_links(tmp_path, make_xlsx):
    p = make_xlsx(tmp_path / "ok.xlsx", [
        ("NAS313", "Abbas Hassan Nasser", "https://example.sharepoint.com/a"),
        ("RAO026", "Abdul Ammar Amin Rao", "https://example.sharepoint.com/b"),
    ])
    assert parse_xlsx(p) == [
        {"id": "NAS313", "name": "Abbas Hassan Nasser",
         "link": "https://example.sharepoint.com/a"},
        {"id": "RAO026", "name": "Abdul Ammar Amin Rao",
         "link": "https://example.sharepoint.com/b"},
    ]


def test_missing_hyperlink_gives_none(tmp_path, make_xlsx):
    p = make_xlsx(tmp_path / "nolink.xlsx", [("AHM407", "Aizaz Ahmed", None)])
    assert parse_xlsx(p) == [{"id": "AHM407", "name": "Aizaz Ahmed", "link": None}]


def test_rows_without_name_skipped(tmp_path, make_xlsx):
    p = make_xlsx(tmp_path / "gap.xlsx", [
        ("X1", "Real Client", "https://example.com/x"),
        ("X2", "", None),
    ])
    assert [c["name"] for c in parse_xlsx(p)] == ["Real Client"]


def test_not_an_xlsx_raises(tmp_path):
    p = tmp_path / "fake.xlsx"
    p.write_bytes(b"this is not a zip")
    with pytest.raises(ParseError):
        parse_xlsx(p)


def test_header_only_raises(tmp_path, make_xlsx):
    p = make_xlsx(tmp_path / "empty.xlsx", [])
    with pytest.raises(ParseError):
        parse_xlsx(p)
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_parser.py -v`
Expected: 5 errors/failures — `ModuleNotFoundError: No module named 'xlsx_parser'`

- [ ] **Step 5: Implement the parser**

`xlsx_parser.py`:
```python
"""Parse the 'SharePoint Links for Clients' spreadsheet into client dicts."""
import openpyxl


class ParseError(Exception):
    """Raised when the uploaded file is not a usable client spreadsheet."""


def parse_xlsx(source):
    """Parse an xlsx (path or file-like) into a list of client dicts.

    Layout: first sheet, one header row, then A=Client ID, B=client name,
    C=cell whose hyperlink target is the SharePoint folder URL.
    Rows with an empty name are skipped; a missing hyperlink gives
    link=None. Raises ParseError for unreadable files or zero valid rows.
    NOTE: must not use read_only=True — that mode drops hyperlinks.
    """
    try:
        wb = openpyxl.load_workbook(source)
    except Exception as exc:
        raise ParseError(f"Not a valid .xlsx file: {exc}") from exc

    clients = []
    for row in wb.worksheets[0].iter_rows(min_row=2):
        if len(row) < 3:
            continue
        cid = str(row[0].value).strip() if row[0].value else ""
        name = str(row[1].value).strip() if row[1].value else ""
        if not name:
            continue
        link_cell = row[2]
        link = link_cell.hyperlink.target if link_cell.hyperlink else None
        clients.append({"id": cid, "name": name, "link": link})

    if not clients:
        raise ParseError(
            "No client rows found — wrong file or wrong sheet layout.")
    return clients
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_parser.py -v`
Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore .env.example xlsx_parser.py tests/
git commit -m "feat: project scaffolding and xlsx client parser"
```

---

### Task 2: JSON storage + one-off import CLI

**Files:**
- Create: `storage.py`, `import_xlsx.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `xlsx_parser.parse_xlsx`, `xlsx_parser.ParseError` (Task 1).
- Produces: `storage.load_clients(path=None) -> list[dict]` (empty list if file absent) and `storage.save_clients(clients, path=None)` (atomic write). When `path` is None both resolve, at call time, to env `CLIENTS_JSON` or `<project>/data/clients.json`. CLI: `python import_xlsx.py <xlsx-path>` prints `"N clients imported, M missing links."` then one `  no link: <name>` line per linkless client; exits 1 on ParseError or bad usage.

- [ ] **Step 1: Write the failing storage tests**

`tests/test_storage.py`:
```python
from storage import load_clients, save_clients


def test_load_missing_file_returns_empty(tmp_path):
    assert load_clients(tmp_path / "nope.json") == []


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "clients.json"
    data = [{"id": "A1", "name": "Test Client", "link": None}]
    save_clients(data, p)
    assert load_clients(p) == data


def test_save_replaces_existing(tmp_path):
    p = tmp_path / "clients.json"
    save_clients([{"id": "A", "name": "Old", "link": None}], p)
    save_clients([{"id": "B", "name": "New", "link": "https://x"}], p)
    assert [c["name"] for c in load_clients(p)] == ["New"]


def test_env_var_overrides_default_path(tmp_path, monkeypatch):
    p = tmp_path / "override.json"
    monkeypatch.setenv("CLIENTS_JSON", str(p))
    save_clients([{"id": "E1", "name": "Env Client", "link": None}])
    assert load_clients() == [{"id": "E1", "name": "Env Client", "link": None}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_storage.py -v`
Expected: 4 errors — `ModuleNotFoundError: No module named 'storage'`

- [ ] **Step 3: Implement storage**

`storage.py`:
```python
"""Atomic load/save of the client list as data/clients.json."""
import json
import os
import tempfile

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "clients.json")


def _resolve(path):
    return os.fspath(path) if path else os.environ.get("CLIENTS_JSON", DEFAULT_PATH)


def load_clients(path=None):
    path = _resolve(path)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_clients(clients, path=None):
    path = _resolve(path)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(clients, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_storage.py -v`
Expected: 4 passed

- [ ] **Step 5: Write the import CLI**

`import_xlsx.py`:
```python
"""One-off CLI: import a client spreadsheet into data/clients.json."""
import sys

from storage import save_clients
from xlsx_parser import ParseError, parse_xlsx


def main():
    if len(sys.argv) != 2:
        print("Usage: python import_xlsx.py <path-to-xlsx>")
        sys.exit(1)
    try:
        clients = parse_xlsx(sys.argv[1])
    except ParseError as exc:
        print(f"Import failed: {exc}")
        sys.exit(1)
    save_clients(clients)
    missing = [c["name"] for c in clients if not c["link"]]
    print(f"{len(clients)} clients imported, {len(missing)} missing links.")
    for name in missing:
        print(f"  no link: {name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Smoke-test the CLI against the real spreadsheet (data/ is gitignored, safe)**

Run: `python import_xlsx.py "../SharePoint Links for Clients S.A.xlsx"`
Expected: `219 clients imported, 36 missing links.` followed by 36 `  no link:` lines; `data/clients.json` now exists.

- [ ] **Step 7: Commit**

```bash
git add storage.py import_xlsx.py tests/test_storage.py
git commit -m "feat: atomic clients.json storage and import CLI"
```

---

### Task 3: Flask app — login, session gate, clients API

**Files:**
- Create: `app.py`, `templates/login.html`, `templates/index.html`, `static/style.css`
- Modify: `tests/conftest.py` (add Flask fixtures)
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `storage.load_clients` (Task 2).
- Produces: Flask `app` importable from `app.py` with routes `GET/POST /login`, `GET /logout`, `GET /` (staff-gated), `GET /api/clients` (staff-gated; 401 JSON `{"error": "unauthenticated"}` when logged out). Decorator `staff_required`. Session key: `session["staff"] = True`. Test fixtures `client` (Flask test client with temp data path) and `logged_in` (client with staff session). Task 5 will add an `/admin` route to this same `app.py` and an "Admin" nav link already present in `index.html`.

- [ ] **Step 1: Add Flask fixtures to conftest**

Append to `tests/conftest.py`:
```python
@pytest.fixture
def data_path(tmp_path, monkeypatch):
    p = tmp_path / "clients.json"
    monkeypatch.setenv("CLIENTS_JSON", str(p))
    return p


@pytest.fixture
def client(data_path):
    from app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"password": "staffpw"})
    return client
```

- [ ] **Step 2: Write the failing auth tests**

`tests/test_auth.py`:
```python
from storage import save_clients


def test_index_redirects_when_logged_out(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_wrong_password_shows_error(client):
    resp = client.post("/login", data={"password": "nope"})
    assert b"Wrong password" in resp.data


def test_right_password_logs_in(client):
    resp = client.post("/login", data={"password": "staffpw"},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert b"search" in resp.data.lower()


def test_api_unauthenticated_gets_401_json(client):
    resp = client.get("/api/clients")
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "unauthenticated"}


def test_api_returns_clients_when_logged_in(logged_in, data_path):
    save_clients([{"id": "A1", "name": "Test Client", "link": None}], data_path)
    resp = logged_in.get("/api/clients")
    assert resp.status_code == 200
    assert resp.get_json() == [{"id": "A1", "name": "Test Client", "link": None}]


def test_logout_clears_session(logged_in):
    logged_in.get("/logout")
    assert logged_in.get("/").status_code == 302
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v`
Expected: 6 errors — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 4: Implement the Flask app**

`app.py`:
```python
"""SharePoint client search — Flask app (port 5001)."""
import os
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for)

from storage import load_clients

load_dotenv()

_missing = [k for k in ("SECRET_KEY", "STAFF_PASSWORD", "ADMIN_PASSWORD")
            if not os.getenv(k)]
if _missing:
    raise SystemExit(f"Missing required .env values: {', '.join(_missing)}")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")


def staff_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("staff"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthenticated"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == os.getenv("STAFF_PASSWORD"):
            session["staff"] = True
            return redirect(url_for("index"))
        error = "Wrong password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@staff_required
def index():
    return render_template("index.html")


@app.route("/api/clients")
@staff_required
def api_clients():
    return jsonify(load_clients())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
```

- [ ] **Step 5: Create templates and stylesheet**

`templates/login.html`:
```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Log in — Client SharePoint Search</title>
<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<main class="narrow">
  <h1>Log in</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post">
    <input type="password" name="password" placeholder="Staff password"
           autofocus required>
    <button type="submit">Log in</button>
  </form>
</main>
</body>
</html>
```

`templates/index.html` (search page shell; `search.js` and `fuse.min.js` arrive in Task 4 — the page still renders, scripts just 404 until then):
```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Client SharePoint Search</title>
<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<main>
  <header>
    <h1>Client SharePoint Search</h1>
    <nav>
      <a href="/admin">Admin</a>
      <a href="{{ url_for('logout') }}">Log out</a>
    </nav>
  </header>
  <input id="search" type="search" placeholder="Type a client name or ID…"
         autocomplete="off" disabled>
  <ul id="results"></ul>
</main>
<script src="{{ url_for('static', filename='fuse.min.js') }}"></script>
<script src="{{ url_for('static', filename='search.js') }}"></script>
</body>
</html>
```

`static/style.css`:
```css
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif;
  background: #f5f6f8; color: #1a1d24; }
main { max-width: 640px; margin: 3rem auto; padding: 0 1rem; }
main.narrow { max-width: 400px; }
header { display: flex; justify-content: space-between; align-items: baseline; }
h1 { font-size: 1.4rem; }
nav a { margin-left: 1rem; font-size: .9rem; color: #4b5563; }
input[type=search], input[type=password], input[type=file] {
  width: 100%; padding: .7rem .9rem; font-size: 1.05rem;
  border: 1px solid #d1d5db; border-radius: 8px;
  margin-bottom: .8rem; background: #fff; }
button { padding: .6rem 1.2rem; font-size: 1rem; border: 0;
  border-radius: 8px; background: #4f46e5; color: #fff; cursor: pointer; }
#results { list-style: none; padding: 0; margin: 1rem 0; }
#results li { display: flex; justify-content: space-between;
  align-items: center; background: #fff; border: 1px solid #e5e7eb;
  border-radius: 8px; padding: .7rem .9rem; margin-bottom: .5rem; }
#results .name { font-weight: 600; display: block; }
#results .cid { color: #6b7280; font-size: .85rem; }
a.open { background: #0d9488; color: #fff; padding: .4rem .8rem;
  border-radius: 6px; text-decoration: none; font-size: .9rem;
  white-space: nowrap; }
.nolink { color: #b45309; background: #fef3c7; padding: .3rem .6rem;
  border-radius: 6px; font-size: .85rem; }
.empty { color: #6b7280; }
.error { color: #b91c1c; }
.ok { color: #15803d; }
.hint { color: #6b7280; font-size: .85rem; }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: 6 passed

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest tests/ -v`
Expected: 15 passed (5 parser + 4 storage + 6 auth)

- [ ] **Step 8: Commit**

```bash
git add app.py templates/ static/ tests/
git commit -m "feat: Flask app with staff login and clients API"
```

---

### Task 4: Search UI — vendored Fuse.js + fuzzy search page

**Files:**
- Create: `static/fuse.min.js` (vendored download), `static/search.js`

**Interfaces:**
- Consumes: `GET /api/clients` JSON (Task 3), DOM ids `search` and `results` from `templates/index.html` (Task 3), CSS classes `info/name/cid/open/nolink/empty` from `static/style.css` (Task 3).
- Produces: working fuzzy search in the browser. No Python surface.

- [ ] **Step 1: Vendor Fuse.js**

```bash
curl -L -o static/fuse.min.js https://cdn.jsdelivr.net/npm/fuse.js@7.0.0/dist/fuse.min.js
```

Verify: `head -c 200 static/fuse.min.js` shows minified JS (not an HTML error page), and the file mentions `Fuse`.

- [ ] **Step 2: Write the search script**

`static/search.js`:
```javascript
let fuse = null;

async function init() {
  const res = await fetch("/api/clients");
  if (res.status === 401) { window.location = "/login"; return; }
  const clients = await res.json();
  fuse = new Fuse(clients, {
    keys: [{ name: "name", weight: 0.7 }, { name: "id", weight: 0.3 }],
    threshold: 0.4,
    ignoreLocation: true,
  });
  const box = document.getElementById("search");
  box.disabled = false;
  box.focus();
}

function render(results) {
  const list = document.getElementById("results");
  list.innerHTML = "";
  if (!results.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No client found";
    list.appendChild(li);
    return;
  }
  for (const { item } of results.slice(0, 8)) {
    const li = document.createElement("li");
    const info = document.createElement("div");
    info.className = "info";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = item.name;
    const id = document.createElement("span");
    id.className = "cid";
    id.textContent = item.id;
    info.append(name, id);
    li.appendChild(info);
    if (item.link) {
      const a = document.createElement("a");
      a.href = item.link;
      a.target = "_blank";
      a.rel = "noopener";
      a.className = "open";
      a.textContent = "Open folder";
      li.appendChild(a);
    } else {
      const badge = document.createElement("span");
      badge.className = "nolink";
      badge.textContent = "No link on file";
      li.appendChild(badge);
    }
    list.appendChild(li);
  }
}

document.getElementById("search").addEventListener("input", (e) => {
  const q = e.target.value.trim();
  if (q.length < 2 || !fuse) {
    document.getElementById("results").innerHTML = "";
    return;
  }
  render(fuse.search(q));
});

init();
```

- [ ] **Step 3: Manual browser verification**

Requires `data/clients.json` (created by Task 2 Step 6) and a `.env` (copy `.env.example` to `.env`, set any values — e.g. `STAFF_PASSWORD=staffpw`).

Start: `python app.py` (background). Open `http://127.0.0.1:5001`, log in, then verify:
1. Typing `Afsana Rehman` (misspelled) suggests **Afsana Rahman**.
2. Typing `Adnan Hlayil` suggests **Adnan Enaiyid Hlaiyil**.
3. Typing surname-first `Rahman Afsana` still finds **Afsana Rahman**.
4. Typing `NAS313` finds **Abbas Hassan Nasser**.
5. Typing `Aizaz Ahmed` shows the **No link on file** badge.
6. Typing gibberish `zzqqxx` shows **No client found**.
7. One char (`a`) shows nothing.
8. "Open folder" opens the SharePoint URL in a new tab.

If misspellings miss, loosen `threshold` to 0.45 max; if noise floods in, tighten toward 0.35. Stop the server after (Windows: use `Stop-Process` on the python PID, then confirm port free with `netstat -ano | findstr :5001` — Bash `kill $!` leaves zombies holding the port).

- [ ] **Step 4: Commit**

```bash
git add static/fuse.min.js static/search.js
git commit -m "feat: client-side fuzzy search with vendored Fuse.js"
```

---

### Task 5: Admin upload page

**Files:**
- Create: `templates/admin.html`
- Modify: `app.py` (add imports + `/admin` route)
- Test: `tests/test_admin.py`

**Interfaces:**
- Consumes: `xlsx_parser.parse_xlsx` / `ParseError` (Task 1), `storage.save_clients` / `load_clients` (Task 2), `staff_required` + fixtures (Task 3), `make_xlsx` fixture (Task 1).
- Produces: `GET/POST /admin` — staff session required; POST needs form fields `admin_password` (must equal env `ADMIN_PASSWORD`) and `file` (xlsx). Success replaces the data atomically and renders `"N clients imported, M missing links."` plus linkless names; any failure leaves existing data untouched.

- [ ] **Step 1: Write the failing admin tests**

`tests/test_admin.py`:
```python
from storage import load_clients, save_clients


def upload(client, path, password="adminpw"):
    with open(path, "rb") as f:
        return client.post(
            "/admin",
            data={"admin_password": password, "file": (f, "upload.xlsx")},
            content_type="multipart/form-data",
        )


def test_admin_requires_staff_login(client):
    resp = client.get("/admin")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_wrong_admin_password_rejected(logged_in, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("N1", "New Client", "https://x")])
    resp = upload(logged_in, p, password="wrong")
    assert b"Wrong admin password" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_valid_upload_replaces_data_and_reports(logged_in, data_path,
                                                make_xlsx, tmp_path):
    p = make_xlsx(tmp_path / "new.xlsx", [
        ("N1", "New Client", "https://x"),
        ("N2", "Linkless Client", None),
    ])
    resp = upload(logged_in, p)
    assert b"2 clients imported, 1 missing links." in resp.data
    assert b"Linkless Client" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == \
        ["New Client", "Linkless Client"]


def test_bad_file_keeps_existing_data(logged_in, data_path, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not really an xlsx")
    resp = upload(logged_in, bad)
    assert b"Not a valid .xlsx" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_no_file_selected(logged_in):
    resp = logged_in.post("/admin", data={"admin_password": "adminpw"},
                          content_type="multipart/form-data")
    assert b"No file selected" in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin.py -v`
Expected: 5 failures — `/admin` returns 404

- [ ] **Step 3: Add the admin route**

In `app.py`, extend the two import lines:
```python
from storage import load_clients, save_clients
from xlsx_parser import ParseError, parse_xlsx
```

Add after the `api_clients` route (before the `if __name__` block):
```python
@app.route("/admin", methods=["GET", "POST"])
@staff_required
def admin():
    result = None
    error = None
    if request.method == "POST":
        if request.form.get("admin_password") != os.getenv("ADMIN_PASSWORD"):
            error = "Wrong admin password."
        else:
            file = request.files.get("file")
            if file is None or not file.filename:
                error = "No file selected."
            else:
                try:
                    clients = parse_xlsx(file)
                    save_clients(clients)
                    missing = [c["name"] for c in clients if not c["link"]]
                    result = {"count": len(clients), "missing": missing}
                except ParseError as exc:
                    error = str(exc)
    return render_template("admin.html", result=result, error=error)
```

- [ ] **Step 4: Create the admin template**

`templates/admin.html`:
```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin — upload client list</title>
<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<main class="narrow">
  <header>
    <h1>Upload client list</h1>
    <nav>
      <a href="{{ url_for('index') }}">Search</a>
      <a href="{{ url_for('logout') }}">Log out</a>
    </nav>
  </header>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  {% if result %}
    <p class="ok">{{ result.count }} clients imported,
      {{ result.missing|length }} missing links.</p>
    {% if result.missing %}
      <details open>
        <summary>Clients missing a SharePoint link</summary>
        <ul>{% for name in result.missing %}<li>{{ name }}</li>{% endfor %}</ul>
      </details>
    {% endif %}
  {% endif %}
  <form method="post" enctype="multipart/form-data">
    <input type="password" name="admin_password" placeholder="Admin password"
           required>
    <input type="file" name="file" accept=".xlsx" required>
    <button type="submit">Upload &amp; replace data</button>
  </form>
  <p class="hint">Expected layout: first sheet — column A Client ID,
    column B client name, column C cell whose hyperlink is the SharePoint
    folder. Header row is ignored.</p>
</main>
</body>
</html>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin.py -v`
Expected: 5 passed

- [ ] **Step 6: Run the whole suite**

Run: `python -m pytest tests/ -v`
Expected: 20 passed

- [ ] **Step 7: Commit**

```bash
git add app.py templates/admin.html tests/test_admin.py
git commit -m "feat: admin xlsx upload with separate admin password"
```

---

### Task 6: Production setup — .env, real import, README, end-to-end check

**Files:**
- Create: `README.md`, `.env` (NOT committed — gitignored)
- Uses: `import_xlsx.py` (Task 2)

**Interfaces:**
- Consumes: everything above.
- Produces: running site with real data; docs for future maintainers.

- [ ] **Step 1: Create the real .env**

Copy `.env.example` to `.env`. Set a random `SECRET_KEY` (e.g. output of `python -c "import secrets; print(secrets.token_hex(32))"`). Ask the user what `STAFF_PASSWORD` and `ADMIN_PASSWORD` should be — do not invent production passwords silently; if the user is unavailable, set clearly-temporary values and flag them in the final report.

- [ ] **Step 2: Import the real spreadsheet (if not already done in Task 2)**

Run: `python import_xlsx.py "../SharePoint Links for Clients S.A.xlsx"`
Expected: `219 clients imported, 36 missing links.`

- [ ] **Step 3: Write the README**

`README.md`:
```markdown
# SharePoint Client Search

Internal staff site: type a client name (typos fine) or Client ID, get
fuzzy-matched suggestions with a button to the client's SharePoint folder.

## Run

    python app.py

Serves on http://127.0.0.1:5001 (benison-chatbot uses 5000).
Needs `.env` (copy `.env.example`): `SECRET_KEY`, `STAFF_PASSWORD`
(login for the search page), `ADMIN_PASSWORD` (extra password for
uploading a new spreadsheet on /admin).

## Update the client list

Either upload the new xlsx on **/admin** (staff login, then admin
password), or from the command line:

    python import_xlsx.py "../SharePoint Links for Clients S.A.xlsx"

Expected spreadsheet layout: first sheet, header row, then
column A = Client ID, column B = client name, column C = cell whose
**hyperlink** is the SharePoint folder URL. Rows without a name are
skipped; rows without a hyperlink show a "No link on file" badge.

## Tests

    python -m pytest tests/ -v

## Notes

- Data lives in `data/clients.json` (gitignored — client data never
  committed). Uploads replace it atomically; a bad upload leaves the
  old data untouched.
- Fuse.js v7 is vendored at `static/fuse.min.js`; no CDN at runtime.
- Search: min 2 characters, top 8 results, threshold 0.4.
```

- [ ] **Step 4: Full test suite + end-to-end check**

Run: `python -m pytest tests/ -v` → Expected: 20 passed.

Start `python app.py` (background), then confirm with curl:
```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5001/          # 302 (to /login)
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5001/login     # 200
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5001/api/clients  # 401
```
Then the browser checks from Task 4 Step 3 against real data. Stop the server (Stop-Process, verify with `netstat -ano | findstr :5001`).

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: README with run, update, and test instructions"
```

Verify `git status` shows `.env` and `data/` untracked/ignored — they must never appear in a commit.
