"""SharePoint client search — Flask app (port 5001)."""
import hmac
import os
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for)

from storage import load_clients, save_clients
from xlsx_parser import ParseError, parse_xlsx

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


@app.route("/admin", methods=["GET", "POST"])
@staff_required
def admin():
    result = None
    error = None
    if request.method == "POST":
        if not hmac.compare_digest(request.form.get("admin_password", ""),
                                   os.getenv("ADMIN_PASSWORD")):
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


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
