import urllib.error

import link_health


def _fake_opener(mapping):
    """mapping: url -> int status, or url -> Exception to raise."""
    class _Resp:
        def __init__(self, status):
            self.status = status
        def close(self):
            pass
    class _Opener:
        def open(self, req, timeout=None):
            outcome = mapping[req.full_url]
            if isinstance(outcome, Exception):
                raise outcome
            if 400 <= outcome:
                raise urllib.error.HTTPError(req.full_url, outcome, "e", {}, None)
            return _Resp(outcome)
    return _Opener()


def test_classify_alive_401(monkeypatch):
    monkeypatch.setattr(link_health, "_opener",
                        _fake_opener({"http://x": 401}))
    assert link_health.check_link("http://x") == ("ok", 401)


def test_classify_dead_404(monkeypatch):
    monkeypatch.setattr(link_health, "_opener",
                        _fake_opener({"http://x": 404}))
    assert link_health.check_link("http://x") == ("dead", 404)


def test_classify_suspect_200(monkeypatch):
    monkeypatch.setattr(link_health, "_opener",
                        _fake_opener({"http://x": 200}))
    assert link_health.check_link("http://x") == ("suspect", 200)


def test_classify_error_on_timeout(monkeypatch):
    monkeypatch.setattr(link_health, "_opener",
                        _fake_opener({"http://x": TimeoutError()}))
    assert link_health.check_link("http://x") == ("error", None)


def test_empty_link_is_nolink():
    assert link_health.check_link("") == ("nolink", None)
    assert link_health.check_link(None) == ("nolink", None)


def test_check_all_report_shape(monkeypatch):
    clients = [
        {"id": "A1", "name": "Alive", "link": "http://ok"},
        {"id": "D1", "name": "Dead", "link": "http://dead"},
        {"id": "S1", "name": "Suspect", "link": "http://susp"},
        {"id": "N1", "name": "NoLink", "link": ""},
    ]
    monkeypatch.setattr(link_health, "check_link", lambda url, timeout=15: {
        "http://ok": ("ok", 401),
        "http://dead": ("dead", 404),
        "http://susp": ("suspect", 200),
        "": ("nolink", None),
    }[url])
    report = link_health.check_all(clients, workers=2)
    assert report["total"] == 4
    assert report["counts"] == {"ok": 1, "dead": 1, "suspect": 1,
                                "nolink": 1, "error": 0}
    flagged_ids = {f["id"] for f in report["flagged"]}
    assert flagged_ids == {"D1", "S1", "N1"}   # every non-ok, ok excluded
    assert report["checked_at"].endswith("Z")


def test_malformed_url_is_error():
    """Malformed URLs (no scheme, typo) degrade to error, not crash."""
    assert link_health.check_link("not-a-real-url-no-scheme") == ("error", None)
    assert link_health.check_link("htp://x") == ("error", None)


def test_check_all_tolerates_malformed_link():
    """One malformed link in batch doesn't abort; completes with error count."""
    clients = [
        {"id": "B1", "name": "Bad", "link": "malformed-no-scheme"},
    ]
    report = link_health.check_all(clients, workers=1)
    assert report["total"] == 1
    assert report["counts"]["error"] == 1
    assert len(report["flagged"]) == 1
    assert report["flagged"][0]["id"] == "B1"
    assert report["flagged"][0]["category"] == "error"


def test_redirect_not_followed():
    """Verify _NoRedirect prevents following 3xx redirects - uses real HTTP server."""
    import http.server
    import socketserver
    import threading

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self):
            # Respond with 302 redirect; if followed, would get different response
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:0/other")
            self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress logging

    # Use dynamic port selection
    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    host, port = server.server_address
    url = f"http://{host}:{port}/original"

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        # Make real request through real _opener (with _NoRedirect)
        result = link_health.check_link(url, timeout=5)
        # Should classify 302 as "suspect" without following to the redirect location
        assert result == ("suspect", 302), f"Expected ('suspect', 302), got {result}"
    finally:
        server.shutdown()
