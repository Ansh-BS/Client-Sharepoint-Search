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
