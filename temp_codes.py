"""Temporary client codes for clients who have no permanent code yet.

A client can start work before the practice has assigned them a code. Rather
than block the add — or let staff invent a dummy nobody can tell from a real
code — the app mints TEMP01, TEMP02, ... and shows the client as awaiting a
real ID until one is assigned.

"Awaiting a code" is derived from the id, never stored as a separate field: the
client record stays {"id", "name", "link"}, so the spreadsheet (which is the
restore path, and has no column for extra state) round-trips without losing
anything.
"""
import re

# TEMP + a bare number. Case-insensitive so a hand-typed temp01 still reads as
# temporary; the app itself always writes upper case, matching every real ID.
TEMP_RE = re.compile(r"TEMP(\d+)", re.IGNORECASE)


def _num(cid):
    """The number in a temporary ID, or None if this isn't one."""
    m = TEMP_RE.fullmatch((cid or "").strip())
    return int(m.group(1)) if m else None


def is_temp(cid):
    """True when this Client ID is one the app minted, not a real ID."""
    return _num(cid) is not None


def next_temp_code(clients):
    """The lowest temp number not currently in use, as TEMP01, TEMP02, ...

    Lowest-free rather than highest-plus-one so the numbers left behind by
    assignments get reused and the list stays short. Zero-padded to two digits
    to line up with the real IDs; past 99 it simply gets longer.
    """
    taken = {n for n in (_num(c.get("id")) for c in clients) if n is not None}
    nxt = 1
    while nxt in taken:
        nxt += 1
    return "TEMP%02d" % nxt


def pending_temp(clients):
    """The clients still waiting for a real ID, sorted by name."""
    return sorted((c for c in clients if is_temp(c.get("id"))),
                  key=lambda c: (c.get("name") or "").casefold())


def merge_temp_clients(new_clients, current):
    """Carry temp-code clients across a spreadsheet replace.

    The upload is a restore/bulk-load path, not the daily source of truth, so a
    client added through /admin this morning must not vanish because this
    afternoon's backup predates them. Returns (merged, kept).

    A temp client whose name IS in the file is dropped in favour of the file's
    row — that is how a backup carrying the real ID retires the temp one.
    Clients with real IDs are untouched: missing from the file still means
    gone, which is what replacing the list is for.
    """
    names = {(c.get("name") or "").strip().casefold() for c in new_clients}
    kept = [c for c in current
            if is_temp(c.get("id"))
            and (c.get("name") or "").strip().casefold() not in names]
    return list(new_clients) + kept, kept
