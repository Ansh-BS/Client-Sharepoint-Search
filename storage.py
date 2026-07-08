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
