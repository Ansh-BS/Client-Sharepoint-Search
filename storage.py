"""Atomic load/save of the client list as data/clients.json.

Uploads are two-step: a parsed spreadsheet is stashed as a *pending* file
(``save_pending``) so the admin can review the diff, then committed with
``save_clients`` only after they confirm. Pending files live in a ``pending/``
dir beside the clients JSON, are named by an unguessable token, and expire so
abandoned previews clean themselves up.
"""
import json
import os
import re
import tempfile
import time

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "clients.json")

# Abandoned previews (parsed but never confirmed) expire after this long.
PENDING_TTL = 1800  # 30 minutes
# token_urlsafe output only; anchors the filename against path traversal.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")


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


# --- pending uploads (the preview/confirm stash) ---------------------------

def _pending_dir(path=None):
    base = _resolve(path)
    return os.path.join(os.path.dirname(base) or ".", "pending")


def _pending_path(token, path=None):
    if not token or not _TOKEN_RE.fullmatch(token):
        return None
    return os.path.join(_pending_dir(path), token + ".json")


def save_pending(clients, token, path=None):
    """Stash a parsed-but-unconfirmed client list under ``token``."""
    dest = _pending_path(token, path)
    if dest is None:
        raise ValueError("invalid pending token")
    directory = _pending_dir(path)
    os.makedirs(directory, exist_ok=True)
    _sweep_pending(path)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(clients, f, ensure_ascii=False, indent=1)
        os.replace(tmp, dest)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_pending(token, path=None):
    """Return the stashed list for ``token``, or None if absent/expired."""
    src = _pending_path(token, path)
    if src is None or not os.path.exists(src):
        return None
    if time.time() - os.path.getmtime(src) > PENDING_TTL:
        os.remove(src)
        return None
    with open(src, encoding="utf-8") as f:
        return json.load(f)


def discard_pending(token, path=None):
    src = _pending_path(token, path)
    if src and os.path.exists(src):
        os.remove(src)


def _sweep_pending(path=None):
    """Best-effort cleanup of previews that were never confirmed."""
    directory = _pending_dir(path)
    try:
        now = time.time()
        for name in os.listdir(directory):
            fp = os.path.join(directory, name)
            try:
                if now - os.path.getmtime(fp) > PENDING_TTL:
                    os.remove(fp)
            except OSError:
                pass
    except FileNotFoundError:
        pass
