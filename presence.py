"""Who has the search page open right now.

A count, not a record. There is no per-user identity in this app — the staff
password is shared and the login form has no username — so this counts browser
sessions, anonymously, and nothing else. What anyone searched for is not
recorded here or anywhere.

State is a flat JSON object of {device_id: last_seen} written through
storage's atomic writer, so a reader never sees a torn file. It is deliberately
not a database: every entry is rewritten on each heartbeat and expires on its
own, so a write lost to two workers racing costs one device one beat, which
that device repairs on its next one.
"""
import json
import os
import time

# Private by name, shared by intent: the atomic writer and the path resolution
# are exactly what this needs, and a second copy of either would be the bug.
from storage import _atomic_write_json, _resolve

# A device counts for this long after its last heartbeat. Three beats' grace, so
# one dropped request does not blink someone out of the count.
WINDOW_SECONDS = 180
# What the browser uses. It lives here so the two cannot drift apart.
HEARTBEAT_SECONDS = 60
# Ids are never reused — a new browser session or a cleared cookie mints another
# — so the file needs a ceiling that does not depend on clients behaving.
MAX_ENTRIES = 200


def presence_path(path=None):
    """Path to presence.json beside the resolved clients path."""
    base = _resolve(path)
    return os.path.join(os.path.dirname(base) or ".", "presence.json")


def _load(path):
    """The stored entries, or {} if the file is missing, unreadable or junk.

    Never raises. This sits on the search page's request path, and a bad file
    must cost the count, not the page.
    """
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(entries, dict):
        return {}
    return {k: v for k, v in entries.items()
            if isinstance(k, str) and isinstance(v, (int, float))
            and not isinstance(v, bool)}


def _prune(entries, now):
    """Drop what has expired, then cap what is left.

    Expiry is on distance from now, not elapsed time: a backward clock step, or
    the app being paused and revived, leaves entries stamped in the future that
    elapsed-time expiry would keep for ever.
    """
    live = {k: v for k, v in entries.items()
            if abs(now - v) <= WINDOW_SECONDS}
    if len(live) <= MAX_ENTRIES:
        return live
    newest = sorted(live.items(), key=lambda kv: kv[1], reverse=True)
    return dict(newest[:MAX_ENTRIES])


def touch(device_id, path=None, now=None):
    """Record that `device_id` is still here, and return how many are.

    Pruning happens here because there is nowhere else: the deploy has no
    scheduler, so the write path is the only thing that runs regularly.
    """
    now = time.time() if now is None else now
    dest = presence_path(path)
    entries = _load(dest)
    if device_id:
        entries[device_id] = now
    # Prune after inserting, not before: capping first and then adding would
    # leave MAX_ENTRIES + 1 on disk. This device was just stamped `now`, so it
    # is the newest and always survives the cap.
    entries = _prune(entries, now)
    try:
        _atomic_write_json(entries, dest)
    except OSError:
        # The count is still true for this request; the next beat will retry.
        pass
    return len(entries)


def count(path=None, now=None):
    """How many devices are currently present. Reads, never writes."""
    now = time.time() if now is None else now
    return len(_prune(_load(presence_path(path)), now))
