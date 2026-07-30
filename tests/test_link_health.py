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
