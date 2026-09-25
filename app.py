"""Client SharePoint Search — Flask app (port 5001)."""
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import time
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

_missing = [k for k in ("SECRET_KEY", "STAFF_PASSWORD", "ADMIN_USERNAMES",
                        "ADMIN_PASSWORD")
            if not os.getenv(k)]
if _missing:
    raise SystemExit(f"Missing required .env values: {', '.join(_missing)}")

# Several people share one ADMIN_PASSWORD but sign in under their own name, so
# the log can say who made a change. Order and spelling here are the canonical
# ones; what someone types is matched case-insensitively.
ADMIN_USERNAMES = tuple(n.strip() for n in os.getenv("ADMIN_USERNAMES").split(",")
                        if n.strip())

# How long /admin stays unlocked with nothing happening. Idle, not absolute:
# every admin request pushes the clock forward, so real work is never cut off
# — but a machine left at a desk locks itself. Staff login is unaffected.
ADMIN_IDLE_SECONDS = 15 * 60
if not ADMIN_USERNAMES:
    raise SystemExit("ADMIN_USERNAMES must list at least one username, "
                     "comma-separated.")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# The admin audit lines below are INFO; without this they'd be dropped, since
# a non-debug logger inherits the root level (WARNING). They go to stderr —
# your terminal in dev, the server error log on PythonAnywhere.
app.logger.setLevel(logging.INFO)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Default True (fail-safe). Set SESSION_COOKIE_SECURE=false in .env for
# non-HTTPS testing. http://127.0.0.1 is a secure context in browsers,
# so the default works for local dev.
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("SESSION_COOKIE_SECURE", "true").strip().lower() != "false")

# Whether to believe the forwarding headers that say who the caller really is.
#   "auto" (default) — decide per request from the peer address, see below
#   1/true/yes/on     — always believe them
#   0/false/no/off    — never believe them
# Set this to 0 for any deployment where the app is reachable directly by the
# people using it (an office LAN box with no proxy): there their peer address is
# private, auto would believe them, and anyone could mint a fresh address per
# request and walk past the rate limiter.
def _trust_mode(raw):
    """Normalise the TRUST_PROXY setting; absent or blank means "auto"."""
    return (raw or "").strip().lower() or "auto"


TRUST_PROXY = _trust_mode(os.getenv("TRUST_PROXY"))

# Longest a real address can be written out: an IPv4-mapped IPv6 address with a
# zone id. The value below becomes a rate-limit key kept in memory and a field
# in every audit line, and it is attacker-chosen, so it gets a ceiling.
_MAX_ADDR_LEN = 45


def _proxy_in_front():
    """Whether this request reached us through a proxy we believe."""
    if TRUST_PROXY in ("1", "true", "yes", "on"):
        return True
    if TRUST_PROXY in ("0", "false", "no", "off"):
        return False
    # "auto". Nothing on the public internet can present a private or loopback
    # peer address — that is a property of routing, not a claim in a header — so
    # a private peer means something local handed us the request. On
    # PythonAnywhere that is always true: the load balancer presents as 10.x.
    # A caller arriving straight off the internet has a public peer address, and
    # their headers are ignored.
    peer = request.remote_addr
    if not peer:
        return False
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    # is_global is the exact question: could this address have been the source
    # of a packet routed to us across the public internet? Private, loopback and
    # reserved ranges all answer no, and only those can mean a local hop.
    return not addr.is_global


def _last_hop(value):
    """The rightmost non-empty comma-separated segment of a header, clipped.

    WSGI merges repeated headers into one comma-joined value, and an appending
    proxy adds what it actually saw at the end. So whether the caller sent their
    own copy of the header or the proxy appended to theirs, the last segment is
    the only one a proxy vouched for. Reading the first would read whatever the
    caller chose to write.
    """
    for hop in reversed(value.split(",")):
        hop = hop.strip()
        if hop:
            return hop[:_MAX_ADDR_LEN]
    return ""


def client_ip():
    """The caller's address, as well as this deployment can know it.

    PythonAnywhere load-balances web apps, so ``request.remote_addr`` is the
    balancer: one constant value for every visitor. Used as a rate-limit key it
    puts the whole firm in a single bucket, so one person mistyping a password
    locks out the office; written to the audit log it says nothing at all. The
    balancer puts the real caller in ``X-Real-IP``.

    Assumes exactly one trusted hop. If a second proxy is ever put in front
    (Cloudflare ahead of PythonAnywhere, say), the last hop becomes the inner
    balancer and this returns a constant again — the original bug, silently.
    """
    if _proxy_in_front():
        real = _last_hop(request.headers.get("X-Real-IP", ""))
        if real:
            return real
        # For a proxy that sets only X-Forwarded-For.
        fwd = _last_hop(request.headers.get("X-Forwarded-For", ""))
        if fwd:
            return fwd
    # Never empty: an empty key would pool every caller into one bucket again.
    return get_remote_address()[:_MAX_ADDR_LEN]


limiter = Limiter(client_ip, app=app, default_limits=[],
                   storage_uri="memory://")

# Cache-busting tag for the CSS and JS under static/. Browsers reuse a cached
# copy of a URL they've seen before, so a deploy that changes those files
# leaves staff staring at the old ones. Bump this on every deploy that touches
# style.css, search.js, theme.js or any of the other static scripts; the
# changed URL forces a fresh fetch. Templates read it via asset_v().
ASSET_VERSION = "18"


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


def _match_admin_username(submitted):
    """The configured spelling of a submitted admin username, else None.

    Every configured name is compared and the loop always runs to the end, so
    the time taken doesn't betray which entry matched — or that any did.
    """
    candidate = submitted.strip().casefold()
    matched = None
    for name in ADMIN_USERNAMES:
        if hmac.compare_digest(candidate, name.casefold()):
            matched = name
    return matched


def _loggable(value):
    """Quote and clip a value so a typed newline can't forge a log line."""
    return repr(str(value)[:60])


def _audit(message, *args):
    app.logger.info("ADMIN " + message + " user=%s ip=%s", *args,
                    _loggable(session.get("admin_user", "?")),
                    client_ip())


def staff_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("staff"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthenticated"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def _lock_admin(reason_idle=None):
    """Drop the admin half of the session, leaving the staff login alone.

    Anything staged but unconfirmed goes too: a pending upload otherwise
    leaves its parsed copy sitting on disk with nobody coming back for it.
    """
    if reason_idle is not None:
        _audit("auto-lock idle=%ds", int(reason_idle))
    token = session.pop("pending_upload", None)
    if token:
        discard_pending(token)
    session.pop("pending_action", None)
    session.pop("pending_basis", None)
    for key in ("admin", "admin_user", "admin_at"):
        session.pop(key, None)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("staff"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthenticated"}), 401
            return redirect(url_for("login"))
        if not session.get("admin"):
            return redirect(url_for("admin_unlock"))
        idle = time.time() - session.get("admin_at", 0)
        if idle > ADMIN_IDLE_SECONDS:
            _lock_admin(reason_idle=idle)
            return redirect(url_for("admin_unlock", timeout=1))
        session["admin_at"] = time.time()
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
# Sized for a shared address, not for one person: staff reach this through a
# single office internet connection, so every failure any of them makes lands in
# the same bucket. Ten across ten people is an outage waiting for a typo.
#
# deduct_when charges only failures. A brute-force brake that also bills correct
# logins is the same defect in miniature — ten people signing in at nine o'clock
# would spend a third of the office's allowance before anyone mistyped anything.
# A redirect is this app's success response on both routes.
#
# Thirty failures per fifteen minutes is roughly 2,900 a day per address — but
# per worker process, and reset by any app reload, since the limiter stores its
# counters in memory. A brake on guessing, not a hard ceiling.
@limiter.limit("30 per 15 minutes", methods=["POST"],
               deduct_when=lambda response: response.status_code != 302)
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


def _list_fingerprint(clients):
    """Identify the live list by what the upload diff actually depends on.

    Only the set of ids and names matters: `dropped` and `added` are computed
    from client keys, and `missing` comes from the new file, not this one. So a
    link edit or a reordering leaves this unchanged and will not interrupt an
    admin mid-review, while an added or removed client will.
    """
    pairs = sorted([(c.get("id") or ""), (c.get("name") or "")]
                   for c in clients)
    return hashlib.sha256(
        json.dumps(pairs, ensure_ascii=False).encode("utf-8")).hexdigest()


def _replace_preview(new_clients, token, current):
    """What replacing the live list with `new_clients` would do to it."""
    dropped, added = _diff_clients(current, new_clients)
    return {
        "kind": "replace",
        "token": token,
        "count": len(new_clients),
        "current_count": len(current),
        "added": [c["name"] for c in added],
        "dropped": [c["name"] for c in dropped],
        "missing": [c["name"] for c in new_clients if not c["link"]],
        }


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
# Sized for a shared address, not for one person: staff reach this through a
# single office internet connection, so every failure any of them makes lands in
# the same bucket. Ten across ten people is an outage waiting for a typo.
#
# deduct_when charges only failures. A brute-force brake that also bills correct
# logins is the same defect in miniature — ten people signing in at nine o'clock
# would spend a third of the office's allowance before anyone mistyped anything.
# A redirect is this app's success response on both routes.
#
# Thirty failures per fifteen minutes is roughly 2,900 a day per address — but
# per worker process, and reset by any app reload, since the limiter stores its
# counters in memory. A brake on guessing, not a hard ceiling.
@limiter.limit("30 per 15 minutes", methods=["POST"],
               deduct_when=lambda response: response.status_code != 302)
@staff_required
def admin_unlock():
    error = None
    if request.method == "POST":
        # Both checks run before either is acted on, so a wrong username and a
        # wrong password cost the same work and the error below can't tell an
        # attacker which half they got right. The username is matched
        # case-insensitively and trimmed -- the password is the secret here.
        submitted = request.form.get("username", "")
        matched = _match_admin_username(submitted)
        password_ok = hmac.compare_digest(request.form.get("password", ""),
                                          os.getenv("ADMIN_PASSWORD"))
        if matched and password_ok:
            session["admin"] = True
            session["admin_user"] = matched
            session["admin_at"] = time.time()
            app.logger.info("ADMIN unlock ok user=%s ip=%s",
                            _loggable(matched), client_ip())
            return redirect(url_for("admin"))
        app.logger.info("ADMIN unlock FAILED user=%s ip=%s",
                        _loggable(submitted), client_ip())
        error = "Wrong admin username or password."
    return render_template("admin_unlock.html", error=error,
                           timed_out=request.args.get("timeout") == "1",
                           idle_minutes=ADMIN_IDLE_SECONDS // 60)


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
            session.pop("pending_basis", None)
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
                    current = load_clients()
                    basis = _list_fingerprint(current)
                    if basis != session.get("pending_basis"):
                        # The live list moved while this preview was on screen,
                        # so the consequences the admin agreed to no longer
                        # hold. The parsed file is still stashed and still what
                        # would be written — only the diff went stale, so show
                        # it again against the list as it is now. Nothing saved.
                        session["pending_basis"] = basis
                        preview = _replace_preview(clients, token, current)
                        preview["stale"] = True
                    else:
                        save_clients(clients)
                        discard_pending(token)
                        session.pop("pending_upload", None)
                        session.pop("pending_basis", None)
                        _audit("replace clients=%d", len(clients))
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
                _audit("add verb=%s id=%s name=%s", pending["verb"],
                       _loggable(pending["id"]), _loggable(pending["name"]))
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
                    # Pin the client itself, not the query that found it. The
                    # query is how the admin reached this row; what they are
                    # shown and agree to is the row.
                    pending = {"kind": "delete",
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
                # Resolve the pinned client, never the original query. Two
                # clients can share a name, so re-running the query here could
                # land on a different row if the list moved while the preview
                # was on screen — and delete something nobody was shown.
                idx = _find_by_key(clients, pending.get("id"), pending["name"])
                if idx is None:
                    error = (f'{pending["name"]} is no longer in the list — '
                             "nothing was removed.")
                else:
                    removed = clients.pop(idx)
                    save_clients(clients)
                    _audit("remove id=%s name=%s",
                           _loggable(removed.get("id")),
                           _loggable(removed["name"]))
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
                    token = secrets.token_urlsafe(24)
                    old = session.get("pending_upload")
                    if old and old != token:
                        discard_pending(old)
                    save_pending(clients, token)
                    session["pending_upload"] = token
                    session["pending_basis"] = _list_fingerprint(current)
                    preview = _replace_preview(clients, token, current)
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
