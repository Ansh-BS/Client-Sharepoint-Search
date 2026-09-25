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
    monkeypatch.setattr(app_module, "TRUST_PROXY", True)


def ip_for(headers=None, peer="10.0.0.9"):
    with app.test_request_context(headers=headers or {},
                                  environ_base={"REMOTE_ADDR": peer}):
        return app_module.client_ip()


def test_forwarding_headers_are_ignored_when_no_proxy_is_trusted():
    # Default deployment posture: anyone could have set these themselves.
    assert ip_for({"X-Real-IP": "203.0.113.7",
                   "X-Forwarded-For": "198.51.100.1, 203.0.113.7"}) == "10.0.0.9"


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
    limiter.enabled = True
    limiter.reset()
    with app.test_client() as c:
        yield c
    limiter.enabled = False
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
