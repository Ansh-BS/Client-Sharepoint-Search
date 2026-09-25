"""Client SharePoint Search — Flask app (port 5001)."""
import hmac
import os
import secrets
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from storage import (discard_pending, load_clients, load_pending,
                     save_clients, save_pending)
from xlsx_parser import ParseError, parse_xlsx

load_dotenv()

_missing = [k for k in ("SECRET_KEY", "STAFF_PASSWORD", "ADMIN_USERNAME",
                        "ADMIN_PASSWORD")
            if not os.getenv(k)]
if _missing:
    raise SystemExit(f"Missing required .env values: {', '.join(_missing)}")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Default True (fail-safe). Set SESSION_COOKIE_SECURE=false in .env for
# non-HTTPS testing. http://127.0.0.1 is a secure context in browsers,
# so the default works for local dev.
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("SESSION_COOKIE_SECURE", "true").strip().lower() != "false")

limiter = Limiter(get_remote_address, app=app, default_limits=[],
                   storage_uri="memory://")

# Cache-busting tag for the CSS and JS under static/. Browsers reuse a cached
# copy of a URL they've seen before, so a deploy that changes those files
# leaves staff staring at the old ones. Bump this on every deploy that touches
# style.css, search.js, theme.js or any of the other static scripts; the
# changed URL forces a fresh fetch. Templates read it via asset_v().
ASSET_VERSION = "17"


@app.context_processor
def inject_asset_version():
    return {"asset_v": ASSET_VERSION}


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    # Only honoured over HTTPS; harmless on plain HTTP.
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains")
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def staff_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("staff"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthenticated"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("staff"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthenticated"}), 401
            return redirect(url_for("login"))
        if not session.get("admin"):
            return redirect(url_for("admin_unlock"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per 15 minutes", methods=["POST"])
def login():
    error = None
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""),
                               os.getenv("STAFF_PASSWORD")):
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


def _client_key(c):
    """Identity for diffing two client lists: Client ID when present,
    else the case-folded name. Two rows the office thinks of as the same
    client compare equal even if only one carries an ID."""
    cid = (c.get("id") or "").strip()
    if cid:
        return ("id", cid)
    return ("name", (c.get("name") or "").strip().casefold())


def _diff_clients(current, new):
    """Return (dropped, added) — clients present only in current, and only
    in new. `dropped` is the one that matters: those stop being findable."""
    cur = {_client_key(c): c for c in current}
    nxt = {_client_key(c): c for c in new}
    dropped = [c for k, c in cur.items() if k not in nxt]
    added = [c for k, c in nxt.items() if k not in cur]
    return dropped, added


def _find_by_key(clients, cid, name):
    key = _client_key({"id": cid, "name": name})
    return next((i for i, c in enumerate(clients) if _client_key(c) == key), None)


def _find_by_query(clients, query):
    idx = next((i for i, c in enumerate(clients)
               if (c.get("id") or "").strip() == query), None)
    if idx is None:
        idx = next((i for i, c in enumerate(clients)
                   if (c.get("name") or "").strip().casefold()
                   == query.casefold()), None)
    return idx


@app.route("/admin/unlock", methods=["GET", "POST"])
@limiter.limit("10 per 15 minutes", methods=["POST"])
@staff_required
def admin_unlock():
    error = None
    if request.method == "POST":
        # Both checks run before either is acted on, so a wrong username and a
        # wrong password cost the same work and the error below can't tell an
        # attacker which half they got right. The username is matched
        # case-insensitively and trimmed -- the password is the secret here.
        user_ok = hmac.compare_digest(
            request.form.get("username", "").strip().casefold(),
            os.getenv("ADMIN_USERNAME").strip().casefold())
        password_ok = hmac.compare_digest(request.form.get("password", ""),
                                          os.getenv("ADMIN_PASSWORD"))
        if user_ok and password_ok:
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Wrong admin username or password."
    return render_template("admin_unlock.html", error=error)


@app.route("/admin", methods=["GET", "POST"])
# Not a password check (unlike login/unlock) — just abuse mitigation on an
# already-gated route. Preview+confirm makes every add/remove/replace two
# requests, so this needs headroom the stricter auth limits don't.
@limiter.limit("40 per 15 minutes", methods=["POST"])
@admin_required
def admin():
    result = None
    error = None
    preview = None
    if request.method == "POST":
        action = request.form.get("action", "preview")

        if action == "cancel":
            # Throw away whichever unconfirmed preview is pending and return
            # to a clean form.
            token = session.pop("pending_upload", None)
            if token:
                discard_pending(token)
            session.pop("pending_action", None)
            return redirect(url_for("admin"))

        elif action == "confirm":
            # The token was minted only after a correct password on the
            # preview step, is session-bound, and is compared in constant
            # time — so it doubles as the CSRF guard for this commit.
            token = session.get("pending_upload")
            submitted = request.form.get("token", "")
            if not token or not hmac.compare_digest(submitted, token):
                error = "That preview expired. Upload the spreadsheet again."
            else:
                clients = load_pending(token)
                if clients is None:
                    error = "That preview expired. Upload the spreadsheet again."
                else:
                    save_clients(clients)
                    discard_pending(token)
                    session.pop("pending_upload", None)
                    missing = [c["name"] for c in clients if not c["link"]]
                    result = {"kind": "replace", "count": len(clients),
                              "missing": missing}

        elif action == "add_client":
            name = request.form.get("client_name", "").strip()
            cid = request.form.get("client_id", "").strip()
            link = request.form.get("client_link", "").strip() or None
            if not name or not cid:
                error = "Client name and Client ID required."
            else:
                clients = load_clients()
                idx = _find_by_key(clients, cid, name)
                verb = "Added" if idx is None else "Updated"
                old_link = clients[idx]["link"] if idx is not None else None
                pending = {"kind": "add", "name": name, "id": cid,
                          "link": link, "verb": verb, "old_link": old_link}
                session["pending_action"] = pending
                preview = pending

        elif action == "confirm_add_client":
            pending = session.get("pending_action")
            if not pending or pending.get("kind") != "add":
                error = "That preview expired. Add the client again."
            else:
                clients = load_clients()
                idx = _find_by_key(clients, pending["id"], pending["name"])
                entry = {"id": pending["id"], "name": pending["name"],
                         "link": pending["link"]}
                if idx is None:
                    clients.append(entry)
                else:
                    clients[idx] = entry
                save_clients(clients)
                session.pop("pending_action", None)
                result = {"kind": "add", "verb": pending["verb"],
                          "name": pending["name"]}

        elif action == "delete_client":
            query = request.form.get("client_query", "").strip()
            if not query:
                error = "Enter a client name or ID to remove."
            else:
                clients = load_clients()
                idx = _find_by_query(clients, query)
                if idx is None:
                    error = f'No client matches "{query}".'
                else:
                    found = clients[idx]
                    pending = {"kind": "delete", "query": query,
                              "id": found.get("id"), "name": found["name"],
                              "link": found.get("link")}
                    session["pending_action"] = pending
                    preview = pending

        elif action == "confirm_delete_client":
            pending = session.get("pending_action")
            if not pending or pending.get("kind") != "delete":
                error = "That preview expired. Remove the client again."
            else:
                clients = load_clients()
                idx = _find_by_query(clients, pending["query"])
                if idx is None:
                    error = f'No client matches "{pending["query"]}".'
                else:
                    removed = clients.pop(idx)
                    save_clients(clients)
                    result = {"kind": "delete", "name": removed["name"]}
                session.pop("pending_action", None)

        else:  # preview: parse and stash, but change nothing yet
            file = request.files.get("file")
            if file is None or not file.filename:
                error = "No file selected."
            else:
                try:
                    clients = parse_xlsx(file)
                except ParseError as exc:
                    error = str(exc)
                else:
                    current = load_clients()
                    dropped, added = _diff_clients(current, clients)
                    token = secrets.token_urlsafe(24)
                    old = session.get("pending_upload")
                    if old and old != token:
                        discard_pending(old)
                    save_pending(clients, token)
                    session["pending_upload"] = token
                    preview = {
                        "kind": "replace",
                        "token": token,
                        "count": len(clients),
                        "current_count": len(current),
                        "added": [c["name"] for c in added],
                        "dropped": [c["name"] for c in dropped],
                        "missing": [c["name"] for c in clients
                                    if not c["link"]],
                        }
    return render_template("admin.html", result=result, error=error,
                           preview=preview)


if __name__ == "__main__":
    # Local dev: re-read templates when they change on disk. Without this, Jinja
    # caches compiled templates for the whole process, so HTML edits only appear
    # after a full restart while static/ files (style.css) refresh on their own —
    # which looks like edits silently doing nothing. Production runs under WSGI,
    # not this block, so it is unaffected.
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.run(host="127.0.0.1", port=5001, debug=False)
