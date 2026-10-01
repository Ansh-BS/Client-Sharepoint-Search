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
    return _lowest_free(_taken(clients))


def _taken(clients):
    return {n for n in (_num(c.get("id")) for c in clients) if n is not None}


def _lowest_free(taken):
    nxt = 1
    while nxt in taken:
        nxt += 1
    return "TEMP%02d" % nxt


def _fold(s):
    return (s or "").strip().casefold()


def needs_temp(c):
    """True for a row with no real Client ID: blank, or the name typed in.

    Clients loaded before temp codes existed often had their name put in the
    Client ID column as a stand-in. That reads as a real ID everywhere, so they
    never show as awaiting one. Only an exact (trimmed, case-folded) match to
    the name counts — an odd-looking code that isn't the name is left alone.
    """
    cid = _fold(c.get("id"))
    return not cid or cid == _fold(c.get("name"))


def fill_temp_codes(clients, previous=()):
    """Give every row that `needs_temp` a temp code. Returns (filled, minted).

    A temp client in `previous` with the same name lends its code, so
    re-uploading a spreadsheet that still has the name in column A keeps the
    code staff have already seen instead of minting a new one each time. Each
    previous code is lent once, so two same-name rows never share an ID.

    New codes skip every temp number in both lists and each code minted so
    far, so a batch never hands out the same one twice. `minted` lists only
    the new codes ({"id", "name", "was"}), not the reused ones. Neither input
    is modified.
    """
    in_file = _taken(clients)
    lendable = {}
    for c in previous:
        # A code the file already uses for some row is not free to lend.
        if is_temp(c.get("id")) and _num(c.get("id")) not in in_file:
            lendable.setdefault(_fold(c.get("name")), []).append(
                c["id"].strip().upper())
    taken = in_file | _taken(previous)
    filled, minted = [], []
    for c in clients:
        if not needs_temp(c):
            filled.append(c)
            continue
        codes = lendable.get(_fold(c.get("name")))
        if codes:
            code = codes.pop(0)
        else:
            code = _lowest_free(taken)
            taken.add(_num(code))
            minted.append({"id": code, "name": c.get("name"),
                           "was": c.get("id") or ""})
        filled.append({**c, "id": code})
    return filled, minted


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


def merge_upload(new_clients, current):
    """What a spreadsheet replace writes: rows with no real ID get temp codes
    (reusing the live list's where the name matches), then temp clients
    absent from the file are carried across. Returns (merged, kept, minted)."""
    filled, minted = fill_temp_codes(new_clients, current)
    merged, kept = merge_temp_clients(filled, current)
    return merged, kept, minted
