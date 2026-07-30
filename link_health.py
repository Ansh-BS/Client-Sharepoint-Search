"""Best-effort health check of client SharePoint links.

Unauthenticated HEAD requests distinguish alive from dead shares (verified
2026-07-30): a live share answers 401 (auth wall, resource exists), a
revoked/typo'd token answers 200 (generic login/error page), a missing site
answers 404. This cannot prove folder contents or permissions, so any non-ok
result is "needs review", never grounds to delete a client.
"""
import datetime
import socket
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

USER_AGENT = "benison-link-health-check/1.0"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Classify on the first response; a 3xx must not be followed to a login page.
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _classify(code):
    if code == 401:
        return "ok"
    if code == 404:
        return "dead"
    return "suspect"


def check_link(url, timeout=15):
    if not url:
        return ("nolink", None)
    req = urllib.request.Request(url, method="HEAD",
                                headers={"User-Agent": USER_AGENT})
    try:
        resp = _opener.open(req, timeout=timeout)
        code = getattr(resp, "status", None) or resp.getcode()
        resp.close()
    except urllib.error.HTTPError as exc:
        code = exc.code
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        return ("error", None)
    return (_classify(code), code)


def check_all(clients, workers=8, timeout=15):
    counts = {"ok": 0, "dead": 0, "suspect": 0, "nolink": 0, "error": 0}
    flagged = []

    def _one(c):
        cat, status = check_link(c.get("link"), timeout)
        return c, cat, status

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for c, cat, status in ex.map(_one, clients):
            counts[cat] += 1
            if cat != "ok":
                flagged.append({"id": c.get("id", ""), "name": c.get("name", ""),
                                "category": cat, "status": status})

    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return {
        "checked_at": now.isoformat().replace("+00:00", "Z"),
        "total": len(clients),
        "counts": counts,
        "flagged": flagged,
    }
