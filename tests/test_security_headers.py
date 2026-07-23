def _csp(client):
    return client.get("/login").headers["Content-Security-Policy"]


def test_styles_are_locked_to_self(client):
    """The React build needed style-src 'unsafe-inline' because React Aria
    writes inline style attributes at runtime. Vanilla does not, so the strict
    policy is back — and stays."""
    csp = _csp(client)
    assert "style-src 'self';" in csp
    assert "unsafe-inline" not in csp


def test_scripts_are_locked_to_self(client):
    csp = _csp(client)
    assert "script-src 'self';" in csp
    assert "unsafe-eval" not in csp


def test_framing_and_base_uri_locked(client):
    csp = _csp(client)
    assert "default-src 'self';" in csp
    assert "frame-ancestors 'none';" in csp
    assert "base-uri 'self';" in csp


def test_other_hardening_headers_present(client):
    headers = client.get("/login").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
