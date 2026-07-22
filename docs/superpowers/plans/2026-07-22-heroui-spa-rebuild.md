# React + HeroUI v3 SPA Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the sharepoint-search frontend (search, login, admin) as a single-page React app using HeroUI v3, with Flask reduced to a JSON API + static server.

**Architecture:** A `frontend/` Vite app (React 19 + TypeScript + Tailwind v4 + HeroUI v3) builds to `frontend/dist/`, committed to git. Flask serves that build same-origin and exposes a `/api/*` JSON surface. Migration is phased: JSON endpoints land alongside the existing HTML routes (both work), the SPA is built page-by-page, then a final cutover deletes the Jinja templates and old vanilla JS.

**Tech Stack:** Python 3 / Flask / flask-limiter / openpyxl (backend, unchanged libs); Vite / React 19 / TypeScript / Tailwind CSS v4 / @heroui/react / @heroui/styles / react-router-dom / fuse.js / Vitest / @testing-library/react (frontend).

## Global Constraints

- **Same-origin only.** SPA is served by Flask from `frontend/dist/`. No CORS, no separate host, no CDN.
- **Auth = existing Flask session cookie.** `HTTPOnly`, `SameSite=Lax`, `Secure` (from `SESSION_COOKIE_SECURE`, default true). No tokens.
- **Admin safety flow unchanged.** xlsx parse → pending stash → session-bound token (constant-time compare, doubles as CSRF) → confirm/cancel. Reuse `parse_xlsx`, `storage.*`, `_client_key`, `_diff_clients` verbatim.
- **Client record shape:** `{"id": str, "name": str, "link": str|None}`. `missing` = records where `not link`.
- **CSRF on state-changing JSON endpoints:** require JSON body (`request.is_json`) on `/api/login`, `/api/logout`, `/api/admin/confirm`, `/api/admin/cancel`; `/api/admin/preview` stays `multipart/form-data`.
- **CSP:** keep `script-src 'self'`. Only `style-src` may gain `'unsafe-inline'` if the built app needs it — verify empirically in Task 12, never relax `script-src`.
- **Build locally, commit `frontend/dist/`.** Server (PythonAnywhere) has no Node; deploy stays `git pull` + Reload.
- **Rate limits preserved:** `10 per 15 minutes` on login POST and admin POST paths.
- **Backend Node commands** on this machine must use the WinGet node dir (PATH gotcha): prepend `C:\Users\Ansh 2\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.16.0-win-x64` to `$env:Path` and call `npm.cmd`/`node.exe` by name.
- **Local run:** backend `python app.py` (port 5001); frontend dev `npm run dev` in `frontend/` (port 5173, proxied to 5001 — see Task 5).
- **Tests must stay green** at each commit: `python -m pytest -q` (backend), `npm run test -- --run` (frontend, once it exists).

---

## File Structure

**Backend (modify):**
- `app.py` — add `/api/login`, `/api/logout`, `/api/me`, `/api/admin/preview`, `/api/admin/confirm`, `/api/admin/cancel`; later add SPA catch-all + asset serving; later finalize CSP.
- `tests/test_api_auth.py` (create), `tests/test_api_admin.py` (create) — JSON endpoint tests.
- `templates/*.html`, `static/*.js`, `static/style.css` — deleted at cutover (Task 12).

**Frontend (create) — under `frontend/`:**
- `package.json`, `vite.config.ts`, `tsconfig*.json`, `index.html`
- `src/main.tsx` — mount
- `src/App.tsx` — Router + theme + `<Toast.Provider/>`
- `src/lib/api.ts` — fetch wrapper
- `src/lib/auth.tsx` — auth context + `RequireStaff`
- `src/routes/Search.tsx`, `src/routes/Login.tsx`, `src/routes/Admin.tsx`
- `src/components/ThemeToggle.tsx`
- `src/index.css` — Tailwind + HeroUI imports + theme tokens
- `src/routes/Search.test.tsx`, `src/lib/auth.test.tsx`, `src/routes/Admin.test.tsx`
- `src/test/setup.ts` — Vitest DOM setup
- `dist/` — committed build output

---

## Phase 0 — Backend JSON API

### Task 1: Auth API — `/api/me`, `/api/login`, `/api/logout`

**Files:**
- Modify: `app.py` (add three routes near the existing `login`/`logout`)
- Test: `tests/test_api_auth.py` (create)

**Interfaces:**
- Consumes: existing `session`, `staff_required`, `limiter`, `hmac`, `os.getenv("STAFF_PASSWORD")`.
- Produces:
  - `POST /api/login` — JSON `{"password": str}` → `200 {"staff": true}` on match (sets `session["staff"]=True`), `401 {"error": "Wrong password."}` on mismatch, `415 {"error": "expected json"}` if not JSON.
  - `POST /api/logout` — clears session → `204`.
  - `GET /api/me` — `200 {"staff": bool}` (public, reads `session.get("staff", False)`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_auth.py`:

```python
def test_me_anonymous(client):
    resp = client.get("/api/me")
    assert resp.status_code == 200
    assert resp.get_json() == {"staff": False}


def test_login_success_sets_session(client):
    resp = client.post("/api/login", json={"password": "staffpw"})
    assert resp.status_code == 200
    assert resp.get_json() == {"staff": True}
    assert client.get("/api/me").get_json() == {"staff": True}


def test_login_wrong_password(client):
    resp = client.post("/api/login", json={"password": "nope"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Wrong password."
    assert client.get("/api/me").get_json() == {"staff": False}


def test_login_requires_json(client):
    resp = client.post("/api/login", data={"password": "staffpw"})
    assert resp.status_code == 415


def test_logout_clears_session(logged_in):
    assert logged_in.get("/api/me").get_json() == {"staff": True}
    resp = logged_in.post("/api/logout", json={})
    assert resp.status_code == 204
    assert logged_in.get("/api/me").get_json() == {"staff": False}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api_auth.py -q`
Expected: FAIL (404 responses — routes not defined).

- [ ] **Step 3: Implement the three routes**

In `app.py`, after the existing `logout` view (around line 95), add:

```python
@app.route("/api/me")
def api_me():
    return jsonify({"staff": bool(session.get("staff"))})


@app.route("/api/login", methods=["POST"])
@limiter.limit("10 per 15 minutes")
def api_login():
    if not request.is_json:
        return jsonify({"error": "expected json"}), 415
    password = (request.get_json(silent=True) or {}).get("password", "")
    if hmac.compare_digest(password, os.getenv("STAFF_PASSWORD")):
        session["staff"] = True
        return jsonify({"staff": True})
    return jsonify({"error": "Wrong password."}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    if not request.is_json:
        return jsonify({"error": "expected json"}), 415
    session.clear()
    return "", 204
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_auth.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run: `python -m pytest -q`
Expected: all prior tests still pass plus the 5 new ones.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_api_auth.py
git commit -m "feat(api): JSON auth endpoints (/api/me, /api/login, /api/logout)"
```

---

### Task 2: Admin API — `/api/admin/preview`

**Files:**
- Modify: `app.py` (add route; reuse `_diff_clients`, `parse_xlsx`, `storage.*`)
- Test: `tests/test_api_admin.py` (create)

**Interfaces:**
- Consumes: `staff_required`, `limiter`, `parse_xlsx`, `ParseError`, `load_clients`, `save_pending`, `discard_pending`, `_diff_clients`, `secrets`, `hmac`, `os.getenv("ADMIN_PASSWORD")`, `session`.
- Produces: `POST /api/admin/preview` — `multipart/form-data` with `file` + `admin_password` →
  - `200 {"token": str, "count": int, "current_count": int, "added": [str], "dropped": [str], "missing": [str]}` on success (stashes pending, sets `session["pending_upload"]`).
  - `401 {"error": "Wrong admin password."}` on bad password.
  - `400 {"error": str}` on missing file or `ParseError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_admin.py`:

```python
from storage import load_clients, save_clients


def api_preview(client, path, password="adminpw"):
    with open(path, "rb") as f:
        return client.post(
            "/api/admin/preview",
            data={"admin_password": password, "file": (f, "upload.xlsx")},
            content_type="multipart/form-data",
        )


def test_preview_requires_staff(client, make_xlsx, tmp_path):
    p = make_xlsx(tmp_path / "n.xlsx", [("N1", "New", "https://x")])
    resp = api_preview(client, p)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthenticated"


def test_preview_wrong_password(logged_in, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old", "link": None}], data_path)
    p = make_xlsx(tmp_path / "n.xlsx", [("N1", "New", "https://x")])
    resp = api_preview(logged_in, p, password="wrong")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Wrong admin password."
    assert [c["name"] for c in load_clients(data_path)] == ["Old"]


def test_preview_reports_diff_without_saving(logged_in, data_path, make_xlsx,
                                             tmp_path):
    save_clients([{"id": "OLD", "name": "Old", "link": "https://o"}], data_path)
    p = make_xlsx(tmp_path / "n.xlsx",
                  [("N1", "New", "https://x"), ("N2", "NoLink", None)])
    resp = api_preview(logged_in, p)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == 2
    assert body["current_count"] == 1
    assert body["dropped"] == ["Old"]
    assert set(body["added"]) == {"New", "NoLink"}
    assert body["missing"] == ["NoLink"]
    assert body["token"]
    # Not committed yet.
    assert [c["name"] for c in load_clients(data_path)] == ["Old"]


def test_preview_missing_file(logged_in):
    resp = logged_in.post("/api/admin/preview",
                          data={"admin_password": "adminpw"},
                          content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "No file selected."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api_admin.py -q`
Expected: FAIL (404 — route not defined).

- [ ] **Step 3: Implement the route**

In `app.py`, after the existing `admin` view (around line 198), add:

```python
@app.route("/api/admin/preview", methods=["POST"])
@limiter.limit("10 per 15 minutes")
@staff_required
def api_admin_preview():
    if not hmac.compare_digest(request.form.get("admin_password", ""),
                               os.getenv("ADMIN_PASSWORD")):
        return jsonify({"error": "Wrong admin password."}), 401
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "No file selected."}), 400
    try:
        clients = parse_xlsx(file)
    except ParseError as exc:
        return jsonify({"error": str(exc)}), 400
    current = load_clients()
    dropped, added = _diff_clients(current, clients)
    token = secrets.token_urlsafe(24)
    old = session.get("pending_upload")
    if old and old != token:
        discard_pending(old)
    save_pending(clients, token)
    session["pending_upload"] = token
    return jsonify({
        "token": token,
        "count": len(clients),
        "current_count": len(current),
        "added": [c["name"] for c in added],
        "dropped": [c["name"] for c in dropped],
        "missing": [c["name"] for c in clients if not c["link"]],
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_admin.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_api_admin.py
git commit -m "feat(api): admin preview endpoint returning JSON diff"
```

---

### Task 3: Admin API — `/api/admin/confirm` and `/api/admin/cancel`

**Files:**
- Modify: `app.py` (add two routes)
- Test: `tests/test_api_admin.py` (append)

**Interfaces:**
- Consumes: everything from Task 2 plus `load_pending`, `save_clients`.
- Produces:
  - `POST /api/admin/confirm` — JSON `{"token": str}` → `200 {"count": int, "missing": [str]}` on valid token (commits, clears pending), `400 {"error": "That preview expired. Upload the spreadsheet again."}` on bad/expired token, `415` if not JSON.
  - `POST /api/admin/cancel` — JSON `{}` → `204` (discards pending if any), `415` if not JSON.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_admin.py`:

```python
def test_confirm_commits_and_reports(logged_in, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old", "link": "https://o"}], data_path)
    p = make_xlsx(tmp_path / "n.xlsx",
                  [("N1", "New", "https://x"), ("N2", "NoLink", None)])
    token = api_preview(logged_in, p).get_json()["token"]
    resp = logged_in.post("/api/admin/confirm", json={"token": token})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == 2
    assert body["missing"] == ["NoLink"]
    assert sorted(c["name"] for c in load_clients(data_path)) == ["NoLink", "New"]


def test_confirm_bad_token(logged_in, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old", "link": None}], data_path)
    p = make_xlsx(tmp_path / "n.xlsx", [("N1", "New", "https://x")])
    api_preview(logged_in, p)
    resp = logged_in.post("/api/admin/confirm", json={"token": "wrong"})
    assert resp.status_code == 400
    assert "expired" in resp.get_json()["error"]
    assert [c["name"] for c in load_clients(data_path)] == ["Old"]


def test_confirm_requires_json(logged_in):
    resp = logged_in.post("/api/admin/confirm", data={"token": "x"})
    assert resp.status_code == 415


def test_cancel_discards_pending(logged_in, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old", "link": None}], data_path)
    p = make_xlsx(tmp_path / "n.xlsx", [("N1", "New", "https://x")])
    token = api_preview(logged_in, p).get_json()["token"]
    resp = logged_in.post("/api/admin/cancel", json={})
    assert resp.status_code == 204
    # Token no longer valid after cancel.
    again = logged_in.post("/api/admin/confirm", json={"token": token})
    assert again.status_code == 400
    assert [c["name"] for c in load_clients(data_path)] == ["Old"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api_admin.py -q`
Expected: FAIL on the four new tests (404).

- [ ] **Step 3: Implement the routes**

In `app.py`, after `api_admin_preview`, add:

```python
@app.route("/api/admin/confirm", methods=["POST"])
@staff_required
def api_admin_confirm():
    if not request.is_json:
        return jsonify({"error": "expected json"}), 415
    submitted = (request.get_json(silent=True) or {}).get("token", "")
    token = session.get("pending_upload")
    expired = {"error": "That preview expired. Upload the spreadsheet again."}
    if not token or not hmac.compare_digest(submitted, token):
        return jsonify(expired), 400
    clients = load_pending(token)
    if clients is None:
        return jsonify(expired), 400
    save_clients(clients)
    discard_pending(token)
    session.pop("pending_upload", None)
    missing = [c["name"] for c in clients if not c["link"]]
    return jsonify({"count": len(clients), "missing": missing})


@app.route("/api/admin/cancel", methods=["POST"])
@staff_required
def api_admin_cancel():
    if not request.is_json:
        return jsonify({"error": "expected json"}), 415
    token = session.pop("pending_upload", None)
    if token:
        discard_pending(token)
    return "", 204
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_admin.py -q`
Expected: PASS (8 passed total in the file).

- [ ] **Step 5: Run the full backend suite**

Run: `python -m pytest -q`
Expected: all pass (old HTML tests + new API tests).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_api_admin.py
git commit -m "feat(api): admin confirm + cancel endpoints"
```

---

## Phase 1 — Frontend scaffold + Search page

### Task 4: Scaffold `frontend/` and wire HeroUI + Tailwind + Router

**Files:**
- Create: `frontend/` via Vite, then edit `frontend/vite.config.ts`, `frontend/src/index.css`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/package.json` (scripts)
- Test: manual (dev server renders); automated tests start in Task 6.

**Interfaces:**
- Produces: a running Vite dev app at `http://localhost:5173` proxying `/api` to `http://127.0.0.1:5001`; `<App/>` rendering a React Router with routes `/`, `/login`, `/admin` (placeholder text for now) and a mounted `<Toast.Provider/>`.

- [ ] **Step 1: Scaffold the Vite app**

From the repo root (PowerShell, using the WinGet node dir):

```powershell
$nodedir='C:\Users\Ansh 2\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.16.0-win-x64'
$env:Path = $nodedir + ';' + $env:Path
& "$nodedir\npm.cmd" create vite@latest frontend -- --template react-ts --yes
cd frontend
& "$nodedir\npm.cmd" install
& "$nodedir\npm.cmd" install @heroui/react @heroui/styles tailwindcss @tailwindcss/vite react-router-dom fuse.js
& "$nodedir\npm.cmd" install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 2: Configure Vite (Tailwind plugin + API proxy + test env)**

Overwrite `frontend/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:5001" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
  },
});
```

Because `vite.config.ts` now has a `test` block, add the Vitest types. Overwrite the top of `frontend/tsconfig.node.json`'s `compilerOptions.types` is not required; instead create `frontend/src/vite-env.d.ts` already exists — leave it. Add a triple-slash ref at the top of `vite.config.ts` if TS complains: `/// <reference types="vitest/config" />`.

- [ ] **Step 3: Wire Tailwind v4 + HeroUI styles**

Overwrite `frontend/src/index.css`:

```css
@import "tailwindcss";
@import "@heroui/styles";

/* App tokens layered on HeroUI's defaults. HeroUI already ships full
   light + dark oklch token sets; we only add app-level niceties here. */
:root { color-scheme: light dark; }
html, body, #root { height: 100%; }
body { margin: 0; }
```

- [ ] **Step 4: Create the Vitest setup file**

Create `frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom";
```

- [ ] **Step 5: Write the router shell**

Overwrite `frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toast } from "@heroui/react";

export default function App() {
  return (
    <BrowserRouter>
      <Toast.Provider />
      <Routes>
        <Route path="/" element={<div>search</div>} />
        <Route path="/login" element={<div>login</div>} />
        <Route path="/admin" element={<div>admin</div>} />
      </Routes>
    </BrowserRouter>
  );
}
```

Overwrite `frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Delete the scaffold's `frontend/src/App.css` import if present (already removed by overwriting App.tsx). Remove `frontend/src/assets/react.svg` usage (gone with the overwrite).

- [ ] **Step 6: Add a test script to package.json**

In `frontend/package.json`, ensure the `scripts` block contains:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview",
  "test": "vitest"
}
```

- [ ] **Step 7: Manual verification**

Terminal A: `python app.py` (repo root).
Terminal B: in `frontend/`, `npm run dev`. Open `http://localhost:5173/` → shows "search"; `/login` → "login"; `/admin` → "admin". No console errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/ .gitignore
git commit -m "chore(frontend): scaffold Vite + React + Tailwind v4 + HeroUI + Router"
```

Note: keep Vite's generated `frontend/.gitignore` (it ignores `node_modules`, but NOT `dist` — remove the `dist` line from `frontend/.gitignore` so the committed build in Task 13 is tracked).

---

### Task 5: API + auth client (`lib/api.ts`, `lib/auth.tsx`)

**Files:**
- Create: `frontend/src/lib/api.ts`, `frontend/src/lib/auth.tsx`
- Test: `frontend/src/lib/auth.test.tsx`

**Interfaces:**
- Produces:
  - `api.ts`: `apiGet<T>(path): Promise<T>`; `apiJson<T>(path, body): Promise<T>` (POST JSON, `credentials: "same-origin"`, throws `ApiError {status, message}` on non-2xx); `apiForm<T>(path, formData): Promise<T>` (POST multipart). `class ApiError extends Error { status: number }`.
  - `auth.tsx`: `AuthProvider` (fetches `/api/me` once, exposes `{staff, loading, setStaff}` via `useAuth()`); `RequireStaff` component that renders children when `staff`, `<Navigate to="/login"/>` otherwise, and `null` while `loading`.

- [ ] **Step 1: Write `lib/api.ts`**

Create `frontend/src/lib/api.ts`:

```ts
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parse(resp: Response) {
  if (resp.status === 204) return null;
  const text = await resp.text();
  return text ? JSON.parse(text) : null;
}

async function handle<T>(resp: Response): Promise<T> {
  const data = await parse(resp);
  if (!resp.ok) {
    const message = (data && data.error) || `Request failed (${resp.status})`;
    throw new ApiError(resp.status, message);
  }
  return data as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return fetch(path, { credentials: "same-origin" }).then(handle<T>);
}

export function apiJson<T>(path: string, body: unknown): Promise<T> {
  return fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

export function apiForm<T>(path: string, form: FormData): Promise<T> {
  return fetch(path, {
    method: "POST",
    credentials: "same-origin",
    body: form,
  }).then(handle<T>);
}
```

- [ ] **Step 2: Write the failing auth test**

Create `frontend/src/lib/auth.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { AuthProvider, RequireStaff } from "./auth";

function mockMe(staff: boolean) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200, text: async () => JSON.stringify({ staff }),
  }));
}

beforeEach(() => vi.unstubAllGlobals());

test("RequireStaff renders children when staff", async () => {
  mockMe(true);
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<RequireStaff><div>secret</div></RequireStaff>} />
          <Route path="/login" element={<div>login page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
  await waitFor(() => expect(screen.getByText("secret")).toBeInTheDocument());
});

test("RequireStaff redirects to /login when not staff", async () => {
  mockMe(false);
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<RequireStaff><div>secret</div></RequireStaff>} />
          <Route path="/login" element={<div>login page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
  await waitFor(() => expect(screen.getByText("login page")).toBeInTheDocument());
});
```

- [ ] **Step 3: Run test to verify it fails**

Run (in `frontend/`): `npm run test -- --run src/lib/auth.test.tsx`
Expected: FAIL (cannot import `./auth`).

- [ ] **Step 4: Write `lib/auth.tsx`**

Create `frontend/src/lib/auth.tsx`:

```tsx
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { apiGet } from "./api";

type Auth = { staff: boolean; loading: boolean; setStaff: (v: boolean) => void };
const AuthContext = createContext<Auth>({ staff: false, loading: true, setStaff: () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [staff, setStaff] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    apiGet<{ staff: boolean }>("/api/me")
      .then((d) => setStaff(d.staff))
      .catch(() => setStaff(false))
      .finally(() => setLoading(false));
  }, []);
  return (
    <AuthContext.Provider value={{ staff, loading, setStaff }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export function RequireStaff({ children }: { children: ReactNode }) {
  const { staff, loading } = useAuth();
  if (loading) return null;
  if (!staff) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm run test -- --run src/lib/auth.test.tsx`
Expected: PASS (2 passed).

- [ ] **Step 6: Wrap App in AuthProvider + guard routes**

Overwrite `frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toast } from "@heroui/react";
import { AuthProvider, RequireStaff } from "./lib/auth";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toast.Provider />
        <Routes>
          <Route path="/" element={<RequireStaff><div>search</div></RequireStaff>} />
          <Route path="/login" element={<div>login</div>} />
          <Route path="/admin" element={<RequireStaff><div>admin</div></RequireStaff>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib frontend/src/App.tsx
git commit -m "feat(frontend): api client + auth context + RequireStaff guard"
```

---

### Task 6: Search page (Fuse.js over `/api/clients`)

**Files:**
- Create: `frontend/src/routes/Search.tsx`, `frontend/src/components/ThemeToggle.tsx`
- Modify: `frontend/src/App.tsx` (use `<Search/>` at `/`)
- Test: `frontend/src/routes/Search.test.tsx`

**Interfaces:**
- Consumes: `apiGet` (Task 5), `useAuth` (for logout button optional).
- Produces: `Search` default export. On mount, `apiGet<Client[]>("/api/clients")`; builds a Fuse index over `name`; input filters live; each result links to `client.link` (new tab) or shows "No link on file" when `!client.link`. `type Client = { id: string; name: string; link: string | null }` (exported from `Search.tsx`).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/routes/Search.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import Search from "./Search";

const CLIENTS = [
  { id: "1", name: "Acme Holdings", link: "https://sp/acme" },
  { id: "2", name: "Beta Corp", link: null },
];

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200, text: async () => JSON.stringify(CLIENTS),
  }));
});

test("lists all clients on load and links to SharePoint", async () => {
  render(<Search />);
  await waitFor(() => expect(screen.getByText("Acme Holdings")).toBeInTheDocument());
  const link = screen.getByRole("link", { name: /Acme Holdings/ });
  expect(link).toHaveAttribute("href", "https://sp/acme");
  expect(screen.getByText("No link on file")).toBeInTheDocument();
});

test("filters as the user types", async () => {
  render(<Search />);
  await waitFor(() => screen.getByText("Acme Holdings"));
  await userEvent.type(screen.getByRole("searchbox"), "beta");
  await waitFor(() => {
    expect(screen.queryByText("Acme Holdings")).not.toBeInTheDocument();
    expect(screen.getByText("Beta Corp")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- --run src/routes/Search.test.tsx`
Expected: FAIL (cannot import `./Search`).

- [ ] **Step 3: Write `components/ThemeToggle.tsx`**

Create `frontend/src/components/ThemeToggle.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Switch } from "@heroui/react";

// HeroUI reads `.dark` on <html> for dark mode. Persist the choice.
export default function ThemeToggle() {
  const [dark, setDark] = useState(
    () => localStorage.getItem("theme") === "dark",
  );
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);
  return (
    <Switch isSelected={dark} onChange={setDark} aria-label="Dark mode">
      Dark
    </Switch>
  );
}
```

- [ ] **Step 4: Write `routes/Search.tsx`**

Create `frontend/src/routes/Search.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import Fuse from "fuse.js";
import { SearchField, Input, Card, Link, Spinner } from "@heroui/react";
import { apiGet } from "../lib/api";
import ThemeToggle from "../components/ThemeToggle";

export type Client = { id: string; name: string; link: string | null };

export default function Search() {
  const [clients, setClients] = useState<Client[] | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    apiGet<Client[]>("/api/clients").then(setClients).catch(() => setClients([]));
  }, []);

  const fuse = useMemo(
    () => new Fuse(clients ?? [], { keys: ["name"], threshold: 0.4 }),
    [clients],
  );

  const results = useMemo(() => {
    if (!clients) return [];
    if (!query.trim()) return clients;
    return fuse.search(query).map((r) => r.item);
  }, [clients, query, fuse]);

  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      <div className="mx-auto max-w-2xl flex flex-col gap-6">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Client SharePoint search</h1>
          <ThemeToggle />
        </header>

        <SearchField aria-label="Search clients" value={query} onChange={setQuery}>
          <Input placeholder="Search by client name…" variant="secondary" />
        </SearchField>

        {clients === null ? (
          <Spinner aria-label="Loading clients" />
        ) : (
          <ul className="flex flex-col gap-2">
            {results.map((c) => (
              <li key={c.id || c.name}>
                <Card variant="secondary">
                  <Card.Content className="flex items-center justify-between gap-4">
                    {c.link ? (
                      <Link href={c.link} target="_blank" rel="noopener noreferrer">
                        {c.name}
                      </Link>
                    ) : (
                      <>
                        <span>{c.name}</span>
                        <span className="text-sm text-muted">No link on file</span>
                      </>
                    )}
                  </Card.Content>
                </Card>
              </li>
            ))}
            {results.length === 0 && (
              <li className="text-muted">No matching clients.</li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm run test -- --run src/routes/Search.test.tsx`
Expected: PASS (2 passed). If the HeroUI `SearchField` does not expose `role="searchbox"`, change the test selector to `screen.getByLabelText("Search clients")` and re-run.

- [ ] **Step 6: Wire the route**

In `frontend/src/App.tsx`, replace the `/` element:

```tsx
import Search from "./routes/Search";
// ...
<Route path="/" element={<RequireStaff><Search /></RequireStaff>} />
```

- [ ] **Step 7: Manual verification**

With backend on 5001 and `npm run dev`: log in via the old `/login` first (in a separate tab at `http://127.0.0.1:5001/login`) so the session cookie exists, then open `http://localhost:5173/` — clients load, typing filters, links open SharePoint, dark toggle flips theme.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/Search.tsx frontend/src/components/ThemeToggle.tsx frontend/src/App.tsx frontend/src/routes/Search.test.tsx
git commit -m "feat(frontend): search page with Fuse.js + theme toggle"
```

---

## Phase 2 — Login page

### Task 7: Login page + post-login redirect

**Files:**
- Create: `frontend/src/routes/Login.tsx`
- Modify: `frontend/src/App.tsx` (use `<Login/>` at `/login`)
- Test: `frontend/src/routes/Login.test.tsx`

**Interfaces:**
- Consumes: `apiJson` (Task 5), `useAuth().setStaff`, `useNavigate`.
- Produces: `Login` default export. Submits `{password}` to `/api/login`; on success sets `staff=true` and navigates to `/`; on `ApiError` shows the message inline (`role="alert"`).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/routes/Login.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { AuthProvider } from "../lib/auth";
import Login from "./Login";

function renderLogin() {
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<div>home</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

beforeEach(() => vi.unstubAllGlobals());

test("wrong password shows an error", async () => {
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce({ ok: true, status: 200, text: async () => JSON.stringify({ staff: false }) }) // /api/me
    .mockResolvedValueOnce({ ok: false, status: 401, text: async () => JSON.stringify({ error: "Wrong password." }) }));
  renderLogin();
  await userEvent.type(screen.getByLabelText(/password/i), "nope");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Wrong password."));
});

test("correct password navigates home", async () => {
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce({ ok: true, status: 200, text: async () => JSON.stringify({ staff: false }) }) // /api/me
    .mockResolvedValueOnce({ ok: true, status: 200, text: async () => JSON.stringify({ staff: true }) })); // /api/login
  renderLogin();
  await userEvent.type(screen.getByLabelText(/password/i), "staffpw");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
  await waitFor(() => expect(screen.getByText("home")).toBeInTheDocument());
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- --run src/routes/Login.test.tsx`
Expected: FAIL (cannot import `./Login`).

- [ ] **Step 3: Write `routes/Login.tsx`**

Create `frontend/src/routes/Login.tsx`:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, TextField, Label, Input, Button } from "@heroui/react";
import { apiJson, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function Login() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { setStaff } = useAuth();
  const navigate = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiJson<{ staff: boolean }>("/api/login", { password });
      setStaff(true);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground grid place-items-center p-6">
      <Card className="w-full max-w-sm">
        <Card.Header>
          <Card.Title>Staff sign in</Card.Title>
          <Card.Description>Enter the staff password to search clients.</Card.Description>
        </Card.Header>
        <form onSubmit={submit}>
          <Card.Content className="flex flex-col gap-4">
            {error && <p role="alert" className="text-danger text-sm">{error}</p>}
            <TextField type="password">
              <Label>Password</Label>
              <Input value={password} onChange={setPassword} placeholder="••••••••"
                     variant="secondary" autoComplete="current-password" />
            </TextField>
          </Card.Content>
          <Card.Footer>
            <Button type="submit" variant="primary" className="w-full" isDisabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </Card.Footer>
        </form>
      </Card>
    </div>
  );
}
```

Note: HeroUI `Input`'s `onChange` yields the string value directly (React Aria convention). If in manual testing it yields an event instead, change to `onChange={(e) => setPassword(typeof e === "string" ? e : e.target.value)}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- --run src/routes/Login.test.tsx`
Expected: PASS (2 passed).

- [ ] **Step 5: Wire the route**

In `frontend/src/App.tsx`, replace the `/login` element:

```tsx
import Login from "./routes/Login";
// ...
<Route path="/login" element={<Login />} />
```

- [ ] **Step 6: Manual verification**

`npm run dev` + backend running. Visit `http://localhost:5173/` while logged out → redirected to `/login`. Wrong password → inline error. Correct staff password → lands on search with clients loaded.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/Login.tsx frontend/src/routes/Login.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): login page wired to /api/login"
```

---

## Phase 3 — Admin page

### Task 8: Admin upload + preview modal + confirm/cancel + toasts

**Files:**
- Create: `frontend/src/routes/Admin.tsx`
- Modify: `frontend/src/App.tsx` (use `<Admin/>` at `/admin`)
- Test: `frontend/src/routes/Admin.test.tsx`

**Interfaces:**
- Consumes: `apiForm`, `apiJson`, `ApiError` (Task 5); `toast` from `@heroui/react`.
- Produces: `Admin` default export. Dropzone (drag-drop + click) with client-side `.xlsx`/size validation; "Review changes" → `POST /api/admin/preview` (multipart) → opens a `Modal` with the diff; "Replace list" → `POST /api/admin/confirm` → success toast + result summary; "Cancel" → `POST /api/admin/cancel` → info toast; errors render inline (not toasts). Preview response type `type Preview = { token: string; count: number; current_count: number; added: string[]; dropped: string[]; missing: string[] }`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/routes/Admin.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import Admin from "./Admin";

const PREVIEW = {
  token: "tok123", count: 2, current_count: 1,
  added: ["New"], dropped: ["Old"], missing: ["NoLink"],
};

beforeEach(() => vi.unstubAllGlobals());

function file(name: string) {
  return new File([new Uint8Array([1, 2, 3])], name, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

test("rejects a non-xlsx file client-side", async () => {
  render(<Admin />);
  await userEvent.upload(screen.getByLabelText(/spreadsheet/i), file("data.csv"));
  expect(screen.getByText(/not an \.xlsx file/i)).toBeInTheDocument();
});

test("preview then confirm shows a success toast summary", async () => {
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce({ ok: true, status: 200, text: async () => JSON.stringify(PREVIEW) }) // preview
    .mockResolvedValueOnce({ ok: true, status: 200, text: async () => JSON.stringify({ count: 2, missing: ["NoLink"] }) })); // confirm
  render(<Admin />);
  await userEvent.upload(screen.getByLabelText(/spreadsheet/i), file("good.xlsx"));
  await userEvent.type(screen.getByLabelText(/admin password/i), "adminpw");
  await userEvent.click(screen.getByRole("button", { name: /review changes/i }));
  await waitFor(() => expect(screen.getByText(/review before replacing/i)).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: /replace list/i }));
  await waitFor(() => expect(screen.getByText(/2 clients imported/i)).toBeInTheDocument());
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- --run src/routes/Admin.test.tsx`
Expected: FAIL (cannot import `./Admin`).

- [ ] **Step 3: Write `routes/Admin.tsx`**

Create `frontend/src/routes/Admin.tsx`:

```tsx
import { useRef, useState } from "react";
import {
  Card, Button, Modal, toast, Input, Label, TextField,
} from "@heroui/react";
import { apiForm, apiJson, ApiError } from "../lib/api";

type Preview = {
  token: string; count: number; current_count: number;
  added: string[]; dropped: string[]; missing: string[];
};
type Result = { count: number; missing: string[] };

const MAX_BYTES = 10 * 1024 * 1024;

function humanSize(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${Math.round(b / 1024)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Admin() {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function pick(f: File | null) {
    setFileError(null);
    if (!f) { setFile(null); return; }
    if (!/\.xlsx$/i.test(f.name)) { setFile(null); setFileError(`Not an .xlsx file: ${f.name}`); return; }
    if (f.size > MAX_BYTES) { setFile(null); setFileError(`Too large (${humanSize(f.size)}, max 10 MB)`); return; }
    setFile(f);
  }

  async function doPreview(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setFileError("No file selected."); return; }
    setBusy(true); setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("admin_password", password);
      setPreview(await apiForm<Preview>("/api/admin/preview", form));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally { setBusy(false); }
  }

  async function confirm() {
    if (!preview) return;
    setBusy(true);
    try {
      const res = await apiJson<Result>("/api/admin/confirm", { token: preview.token });
      setResult(res);
      setPreview(null);
      setFile(null);
      setPassword("");
      toast.success(`Client list replaced — ${res.count} client${res.count === 1 ? "" : "s"} now live.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Confirm failed.");
      setPreview(null);
    } finally { setBusy(false); }
  }

  async function cancel() {
    setPreview(null);
    try { await apiJson("/api/admin/cancel", {}); } catch { /* ignore */ }
    toast.info("Upload cancelled — nothing was changed.");
  }

  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      <div className="mx-auto max-w-xl flex flex-col gap-6">
        <h1 className="text-2xl font-semibold">Replace the client list</h1>

        {result ? (
          <Card>
            <Card.Header><Card.Title>Client list replaced</Card.Title></Card.Header>
            <Card.Content className="flex flex-col gap-2">
              <p>{result.count} clients imported. The search box is live with the new list.</p>
              {result.missing.length > 0 && (
                <details open>
                  <summary>{result.missing.length} with no SharePoint link</summary>
                  <ul>{result.missing.map((n) => <li key={n}>{n}</li>)}</ul>
                </details>
              )}
              <Button variant="secondary" className="w-fit" onPress={() => setResult(null)}>
                Upload another spreadsheet
              </Button>
            </Card.Content>
          </Card>
        ) : (
          <Card>
            <form onSubmit={doPreview}>
              <Card.Content className="flex flex-col gap-4">
                {error && <p role="alert" className="text-danger text-sm">{error}</p>}
                <label
                  className="block cursor-pointer text-center p-6 rounded-2xl border border-dashed border-border bg-surface-secondary"
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files?.[0] ?? null); }}
                >
                  <span className="block font-medium">Spreadsheet (.xlsx)</span>
                  <span className="block text-sm text-muted">Drag the file here, or click to choose</span>
                  <input
                    ref={inputRef}
                    type="file"
                    accept=".xlsx"
                    aria-label="Spreadsheet (.xlsx)"
                    className="mt-3 w-full"
                    onChange={(e) => pick(e.target.files?.[0] ?? null)}
                  />
                </label>
                {fileError && <p className="text-danger text-sm">✗ {fileError}</p>}
                {file && <p className="text-success text-sm">✓ Ready: {file.name} ({humanSize(file.size)})</p>}

                <TextField type="password">
                  <Label>Admin password</Label>
                  <Input value={password} onChange={setPassword} placeholder="••••••••"
                         variant="secondary" autoComplete="current-password" />
                </TextField>
              </Card.Content>
              <Card.Footer>
                <Button type="submit" variant="primary" isDisabled={busy}>
                  {busy ? "Working…" : "Review changes"}
                </Button>
              </Card.Footer>
            </form>
          </Card>
        )}
      </div>

      {preview && (
        <Modal isOpen onOpenChange={(open) => { if (!open) cancel(); }}>
          <Modal.Backdrop>
            <Modal.Container>
              <Modal.Dialog className="sm:max-w-[440px]">
                <Modal.Header><Modal.Heading>Review before replacing</Modal.Heading></Modal.Header>
                <Modal.Body className="flex flex-col gap-3">
                  <p><strong>Nothing has changed yet.</strong> Replaces the current {preview.current_count}{" "}
                    client{preview.current_count === 1 ? "" : "s"} with {preview.count} from the new file
                    {preview.added.length ? `, ${preview.added.length} new` : ""}.</p>
                  {preview.dropped.length > 0 && (
                    <details open>
                      <summary>{preview.dropped.length} will stop being findable</summary>
                      <ul>{preview.dropped.map((n) => <li key={n}>{n}</li>)}</ul>
                    </details>
                  )}
                  {preview.missing.length > 0 && (
                    <details>
                      <summary>{preview.missing.length} with no SharePoint link</summary>
                      <ul>{preview.missing.map((n) => <li key={n}>{n}</li>)}</ul>
                    </details>
                  )}
                </Modal.Body>
                <Modal.Footer className="flex gap-2 justify-end">
                  <Button variant="tertiary" onPress={cancel} isDisabled={busy}>Cancel</Button>
                  <Button variant="primary" onPress={confirm} isDisabled={busy}>
                    Replace list with {preview.count} client{preview.count === 1 ? "" : "s"}
                  </Button>
                </Modal.Footer>
              </Modal.Dialog>
            </Modal.Container>
          </Modal.Backdrop>
        </Modal>
      )}
    </div>
  );
}
```

Note: the `Modal` here is used in controlled form (`isOpen` + `onOpenChange`) because open state is driven by the async preview, not a trigger button. If the installed HeroUI build requires the trigger/uncontrolled pattern, wrap the dialog so `preview` conditionally renders `<Modal defaultOpen>` and drive close via the buttons' `onPress` only — verify against `get_component_docs(["Modal"])` during implementation.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- --run src/routes/Admin.test.tsx`
Expected: PASS (2 passed). If HeroUI `toast` needs `<Toast.Provider/>` mounted for the assertion, wrap the render: `render(<><Toast.Provider/><Admin/></>)` and import `Toast`.

- [ ] **Step 5: Wire the route**

In `frontend/src/App.tsx`, replace the `/admin` element:

```tsx
import Admin from "./routes/Admin";
// ...
<Route path="/admin" element={<RequireStaff><Admin /></RequireStaff>} />
```

- [ ] **Step 6: Manual verification**

`npm run dev` + backend. Log in, visit `http://localhost:5173/admin`. Drag a real `.xlsx` → "✓ Ready"; wrong extension → "✗ Not an .xlsx"; enter admin password → "Review changes" opens the modal with the diff; Cancel → info toast, no change; re-do and Replace → success toast + "N clients imported" summary; verify the search page reflects the new list.

- [ ] **Step 7: Run the full frontend suite**

Run: `npm run test -- --run`
Expected: all frontend tests pass (auth, Search, Login, Admin).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/Admin.tsx frontend/src/routes/Admin.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): admin upload/preview/confirm with modal + toasts"
```

---

## Phase 4 — Cutover

### Task 9: Flask serves the SPA build (catch-all + assets)

**Files:**
- Modify: `app.py` (static folder config + catch-all route)
- Test: `tests/test_spa.py` (create)

**Interfaces:**
- Consumes: Flask `send_from_directory`, existing routes (API routes must still win over the catch-all).
- Produces: `GET /` and any non-`/api`, non-asset path → `frontend/dist/index.html`; `GET /assets/<file>` → the hashed built asset. API routes are registered before the catch-all and keep their behavior.

- [ ] **Step 1: Produce a build to serve**

In `frontend/` (WinGet node dir on PATH): `npm run build`. Confirm `frontend/dist/index.html` and `frontend/dist/assets/` exist.

- [ ] **Step 2: Write the failing test**

Create `tests/test_spa.py`:

```python
def test_root_serves_spa_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<div id=\"root\">" in resp.data


def test_unknown_path_serves_spa_index(client):
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert b"<div id=\"root\">" in resp.data


def test_api_still_json_not_spa(client):
    resp = client.get("/api/me")
    assert resp.status_code == 200
    assert resp.get_json() == {"staff": False}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_spa.py -q`
Expected: FAIL (`/` currently 302→/login or renders Jinja; `/admin` 302).

- [ ] **Step 4: Point Flask at the build and add the catch-all**

In `app.py`, change the app construction (line 24) to serve the built assets and add a catch-all at the very end (after all `/api` and page routes, before `if __name__`):

```python
DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")
app = Flask(__name__, static_folder=os.path.join(DIST, "assets"),
            static_url_path="/assets")
```

Then add near the end of the module (after `api_admin_cancel`, before `if __name__ == "__main__":`):

```python
from flask import send_from_directory


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path):
    # API routes are matched first by Flask's router; anything else is the SPA.
    # The SPA itself calls /api/me to decide whether to show login, so this
    # route is intentionally public.
    return send_from_directory(DIST, "index.html")
```

Note: remove the old `index()` view's `@staff_required` HTML route only in Task 10 (kept now so existing HTML tests keep passing until they are replaced). To avoid a route collision on `/`, temporarily rename the old HTML `index` route path — but simpler: this task's `test_spa.py` asserts the SPA at `/`, which conflicts with the old `index` view. Resolve by deleting the old `index`, `login` (GET/POST HTML), and `admin` HTML views and their template tests in **this** task if they collide. See Step 5.

- [ ] **Step 5: Remove the colliding HTML page routes now**

Delete from `app.py`: the `index()` view (lines ~98-101), the HTML `login()` view (keep POST? no — the SPA uses `/api/login`), the HTML `logout()` view, and the `admin()` HTML view (lines ~130-198). Delete the now-obsolete template tests: `tests/test_admin.py` (HTML-form based) and any HTML assertions in `tests/test_auth.py` that hit `/login`/`/admin` HTML. Keep parser/storage tests and the new API tests.

Also delete the now-unused `inject_asset_version` context processor and `ASSET_VERSION` (Vite hashes replace cache-busting), and drop `render_template`, `redirect`, `url_for` from the imports if no longer used.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest -q`
Expected: PASS — `test_spa.py`, `test_api_auth.py`, `test_api_admin.py`, `test_parser.py`, `test_storage.py` all green; no references to deleted views remain.

- [ ] **Step 7: Commit**

```bash
git add app.py tests/
git commit -m "feat: Flask serves the SPA build; remove Jinja page routes"
```

---

### Task 10: Delete old templates/static, finalize CSP, update docs

**Files:**
- Delete: `templates/index.html`, `templates/login.html`, `templates/admin.html`, `static/search.js`, `static/toast.js`, `static/modal.js`, `static/upload.js`, `static/password.js`, `static/style.css`, `static/fuse.min.js`
- Modify: `app.py` (finalize CSP), `docs/UPDATE_PYTHONANYWHERE.md`, `docs/DEPLOY_PYTHONANYWHERE.md`
- Test: `python -m pytest -q` + manual CSP check

**Interfaces:**
- Consumes: the working SPA + API from prior tasks.
- Produces: a repo with no Jinja/vanilla frontend, a finalized CSP, and deploy docs describing the `git pull` + Reload (build-committed) flow.

- [ ] **Step 1: Delete the obsolete frontend files**

```bash
git rm templates/index.html templates/login.html templates/admin.html \
  static/search.js static/toast.js static/modal.js static/upload.js \
  static/password.js static/style.css static/fuse.min.js
```

Keep `static/logo.png` and `static/fonts/` only if the SPA references them; otherwise `git rm` those too. (The SPA bundles its own assets, so most likely remove them — verify no `frontend/src` reference first with a search for `logo.png` / font filenames.)

- [ ] **Step 2: Finalize CSP against the real build**

Run the app (`python app.py`) and load `http://127.0.0.1:5001/` with DevTools console open. If there are **no** CSP violations, keep `style-src 'self'`. If HeroUI/React inline styles are blocked, change only the `style-src` directive in `set_security_headers` (line ~55):

```python
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
```

Leave `script-src 'self'` untouched. Document in a code comment which case applied and why.

- [ ] **Step 3: Run the backend suite**

Run: `python -m pytest -q`
Expected: all pass (no template references remain).

- [ ] **Step 4: Update deploy docs**

In `docs/UPDATE_PYTHONANYWHERE.md` and `docs/DEPLOY_PYTHONANYWHERE.md`, replace the "bump ASSET_VERSION / templates cached" guidance with:

- Build locally: in `frontend/`, `npm ci && npm run build`, then `git add frontend/dist && git commit`.
- Deploy: `git pull` on the server + **Reload**. No Node on the server. Vite content-hashed filenames handle cache-busting (ASSET_VERSION retired).
- WSGI unchanged; Flask serves `frontend/dist` (`/assets` static + SPA catch-all).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove Jinja/vanilla frontend, finalize CSP, update deploy docs"
```

---

### Task 11: Build, commit `dist/`, and full regression

**Files:**
- Create/Modify: `frontend/dist/**` (committed build)
- Test: full backend + frontend suites + manual end-to-end

**Interfaces:**
- Consumes: everything.
- Produces: a committed production build and a green full regression.

- [ ] **Step 1: Clean production build**

In `frontend/` (WinGet node dir on PATH): `npm run build`. Confirm `frontend/dist/index.html` + `frontend/dist/assets/*` regenerated.

- [ ] **Step 2: Frontend tests**

Run: `npm run test -- --run`
Expected: all frontend tests pass.

- [ ] **Step 3: Backend tests**

Run (repo root): `python -m pytest -q`
Expected: all pass.

- [ ] **Step 4: Manual end-to-end against the built app (no dev server)**

Run only `python app.py`. In a browser at `http://127.0.0.1:5001/`:
- Logged out → SPA shows login. Wrong password → error; correct staff password → search page, clients load.
- Search filters; SharePoint links open; "No link on file" shows for linkless clients.
- Dark toggle persists across reload.
- `/admin`: dropzone validation, preview modal with correct diff, Cancel → info toast + no change, Replace → success toast + summary; search reflects the new list.
- No console errors; no CSP violations.

- [ ] **Step 5: Commit the build**

```bash
git add frontend/dist
git commit -m "build: commit production SPA bundle"
```

- [ ] **Step 6: Finish the branch**

Use superpowers:finishing-a-development-branch to merge to `main` locally (no push unless asked).

---

## Self-Review (completed by plan author)

- **Spec coverage:** Architecture (Task 9), API surface (Tasks 1-3), auth/CSRF (Tasks 1-3 JSON guards + preserved token flow), CSP (Tasks 9-10), frontend structure (Tasks 4-8), search client-side Fuse (Task 6), dark toggle (Task 6), testing backend+frontend (all tasks), deploy build-locally/commit-dist (Tasks 9-11), phasing (task order) — all mapped.
- **Placeholders:** none — every code step contains complete code; verification notes for HeroUI API variance point to `get_component_docs` rather than leaving logic unspecified.
- **Type consistency:** `Client {id,name,link}`, `Preview {token,count,current_count,added,dropped,missing}`, `Result {count,missing}`, `ApiError {status,message}`, `apiGet/apiJson/apiForm`, `useAuth/RequireStaff/AuthProvider` names used consistently across tasks.
- **Known API-variance risks flagged for the implementer:** HeroUI `Input` onChange signature (Tasks 7-8), `Modal` controlled vs trigger pattern (Task 8), `SearchField` role (Task 6), `toast` needing a provider in tests (Task 8). Each has a concrete fallback.
