"""The address the app treats as the caller's.

On the deployed host every request arrives via a load balancer, so
``request.remote_addr`` is that balancer and is identical for everyone. The
real caller is in the forwarding headers — but only a real proxy makes those
headers trustworthy, so reading them is opt-in.
"""
import pytest

import app as app_module
from app import app


@pytest.fixture
def trusted_proxy(monkeypatch):
    """Force the trusted-proxy branch on regardless of the peer address."""
    monkeypatch.setattr(app_module, "TRUST_PROXY", "1")


@pytest.fixture
def no_proxy(monkeypatch):
    monkeypatch.setattr(app_module, "TRUST_PROXY", "0")


def ip_for(headers=None, peer="10.0.0.9"):
    with app.test_request_context(headers=headers or {},
                                  environ_base={"REMOTE_ADDR": peer}):
        return app_module.client_ip()


SPOOFED = {"X-Real-IP": "203.0.113.7",
           "X-Forwarded-For": "198.51.100.1, 203.0.113.7"}


def test_forwarding_headers_are_ignored_when_explicitly_switched_off(no_proxy):
    assert ip_for(SPOOFED, peer="10.0.0.9") == "10.0.0.9"


def test_a_public_peer_cannot_talk_its_way_into_a_different_address():
    """Default (auto). A caller reaching us straight off the internet has a
    public peer address by construction, so its headers are its own invention."""
    # 8.8.8.8 rather than a 198.51.100.x documentation address: Python counts
    # the documentation ranges as non-global, so one would take the proxy branch.
    assert ip_for(SPOOFED, peer="8.8.8.8") == "8.8.8.8"


def test_a_private_peer_is_a_proxy_and_is_believed():
    """Default (auto). Nothing on the public internet can present a private
    peer address, so a private one means something local passed the request on
    — on PythonAnywhere, the load balancer, which presents as 10.x."""
    assert ip_for({"X-Real-IP": "203.0.113.7"}, peer="10.87.38.59") == "203.0.113.7"


def test_a_peer_that_is_not_an_address_at_all_is_not_trusted():
    assert ip_for(SPOOFED, peer="not-an-address") == "not-an-address"


def test_trusted_proxy_reveals_the_caller_via_x_real_ip(trusted_proxy):
    assert ip_for({"X-Real-IP": "203.0.113.7"}) == "203.0.113.7"


def test_forwarded_for_falls_back_to_the_rightmost_hop(trusted_proxy):
    # A caller can put anything at the front of X-Forwarded-For; an appending
    # proxy adds the address it actually saw at the end. Only that last hop is
    # vouched for, so reading the leftmost entry would read attacker input.
    assert ip_for({"X-Forwarded-For": "198.51.100.1, 203.0.113.7"}) == "203.0.113.7"


def test_trusted_proxy_without_headers_falls_back_to_the_peer(trusted_proxy):
    assert ip_for({}) == "10.0.0.9"


# --- what the corrected address is actually for ---------------------------

LOGIN_BUDGET = 30


@pytest.fixture
def limited(data_path, trusted_proxy):
    """A client with the rate limiter live, behind a trusted proxy.

    The shared conftest client disables the limiter; these tests are about it.
    """
    from app import limiter
    app.config["TESTING"] = True
    was_enabled = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        with app.test_client() as c:
            yield c
    finally:
        limiter.enabled = was_enabled
        limiter.reset()


def wrong_login(c, ip):
    return c.post("/login", data={"password": "nope"},
                  headers={"X-Real-IP": ip})


def test_one_address_exhausting_its_login_budget_leaves_another_free(limited):
    """The defect this whole change exists for.

    Keyed on the balancer's address, every visitor shares one budget, so one
    person mistyping their password locks out everyone else.
    """
    for _ in range(LOGIN_BUDGET + 1):
        wrong_login(limited, "203.0.113.7")
    assert wrong_login(limited, "203.0.113.7").status_code == 429

    assert wrong_login(limited, "198.51.100.4").status_code != 429


def test_login_allows_a_whole_office_worth_of_attempts_before_refusing(limited):
    """Staff share one public address, so the budget covers a whole office."""
    for attempt in range(LOGIN_BUDGET):
        assert wrong_login(limited, "203.0.113.7").status_code != 429, (
            f"refused on attempt {attempt + 1} of {LOGIN_BUDGET}")
    assert wrong_login(limited, "203.0.113.7").status_code == 429


def test_admin_unlock_budget_is_per_address_too(limited):
    limited.post("/login", data={"password": "staffpw"},
                 headers={"X-Real-IP": "203.0.113.7"})

    def bad_unlock(ip):
        return limited.post("/admin/unlock",
                            data={"username": "adminuser", "password": "nope"},
                            headers={"X-Real-IP": ip})

    for _ in range(LOGIN_BUDGET + 1):
        bad_unlock("203.0.113.7")
    assert bad_unlock("203.0.113.7").status_code == 429
    assert bad_unlock("198.51.100.4").status_code != 429


def test_audit_log_records_the_forwarded_address(logged_in, trusted_proxy,
                                                 caplog):
    """An audit line naming the balancer answers 'from where' with nothing."""
    import logging
    with caplog.at_level(logging.INFO):
        logged_in.post("/admin/unlock",
                       data={"username": "adminuser", "password": "adminpw"},
                       headers={"X-Real-IP": "203.0.113.7"})
    assert "ADMIN unlock ok" in caplog.text
    assert "ip=203.0.113.7" in caplog.text


# --- header hardening -----------------------------------------------------

def test_a_second_x_real_ip_header_cannot_forge_the_key(trusted_proxy):
    """WSGI merges repeated headers into one comma-joined value.

    If any proxy in the chain appends an X-Real-IP instead of replacing one the
    caller sent, the naive read returns the whole joined string — an
    attacker-controlled, per-request-unique rate-limit key, i.e. no limit at
    all. Only the last segment is the one a proxy actually vouched for.
    """
    with app.test_request_context(headers=[("X-Real-IP", "9.9.9.9"),
                                           ("X-Real-IP", "203.0.113.7")],
                                  environ_base={"REMOTE_ADDR": "10.0.0.9"}):
        assert app_module.client_ip() == "203.0.113.7"


def test_an_absurdly_long_header_cannot_bloat_the_log_or_the_key(trusted_proxy):
    """The value becomes a rate-limit key held in memory and a line in the
    audit log, on every request. It is attacker-chosen, so it needs a ceiling.
    45 characters is the longest a real address can be."""
    assert len(ip_for({"X-Real-IP": "9" * 4000})) <= 45


# --- what the budget is actually for --------------------------------------

def test_a_successful_login_does_not_spend_the_brute_force_budget(limited):
    """The allowance exists to slow password guessing.

    Charging it for correct logins recreates the defect in miniature: ten staff
    signing in at nine o'clock would spend a third of the office's allowance
    before anyone has mistyped anything.
    """
    for attempt in range(LOGIN_BUDGET):
        resp = limited.post("/login", data={"password": "staffpw"},
                            headers={"X-Real-IP": "203.0.113.7"})
        assert resp.status_code != 429, f"refused a correct password on attempt {attempt + 1}"

    assert wrong_login(limited, "203.0.113.7").status_code != 429


def test_the_change_log_records_the_forwarded_address(logged_in, trusted_proxy,
                                                      caplog):
    """`_audit` is the who-changed-the-client-list-and-from-where record."""
    import logging
    via = {"X-Real-IP": "203.0.113.7"}
    logged_in.post("/admin/unlock",
                   data={"username": "adminuser", "password": "adminpw"},
                   headers=via)
    logged_in.post("/admin", data={"action": "add_client",
                                   "client_name": "Acme Ltd",
                                   "client_id": "A1"}, headers=via)
    with caplog.at_level(logging.INFO):
        logged_in.post("/admin", data={"action": "confirm_add_client"},
                       headers=via)
    assert "ADMIN add" in caplog.text
    assert "ip=203.0.113.7" in caplog.text


# --- the one line between a working server and a broken one ---------------

def test_the_env_setting_is_normalised():
    assert app_module._trust_mode("  TRUE  ") == "true"
    assert app_module._trust_mode("1") == "1"


def test_an_absent_or_blank_env_setting_means_auto():
    assert app_module._trust_mode(None) == "auto"
    assert app_module._trust_mode("   ") == "auto"
