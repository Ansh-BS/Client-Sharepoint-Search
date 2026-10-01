import json

import pytest

import presence
from presence import MAX_ENTRIES, WINDOW_SECONDS


def test_two_devices_count_as_two(data_path):
    presence.touch("aaa", data_path)
    assert presence.touch("bbb", data_path) == 2


def test_the_same_device_twice_counts_as_one(data_path):
    presence.touch("aaa", data_path)
    assert presence.touch("aaa", data_path) == 1


def test_a_device_that_stopped_beating_drops_out(data_path):
    presence.touch("gone", data_path, now=1000)
    assert presence.touch("here", data_path, now=1000 + WINDOW_SECONDS + 1) == 1


def test_an_expired_device_is_removed_from_the_file(data_path):
    presence.touch("gone", data_path, now=1000)
    presence.touch("here", data_path, now=1000 + WINDOW_SECONDS + 1)
    on_disk = json.load(open(presence.presence_path(data_path), encoding="utf-8"))
    assert list(on_disk) == ["here"]


def test_an_entry_stamped_in_the_future_is_dropped(data_path):
    """A backward clock step, or the app being paused and revived, can leave a
    timestamp ahead of now. Expiring on elapsed time alone would keep it for
    ever."""
    presence.touch("skewed", data_path, now=1000 + 2 * WINDOW_SECONDS)
    assert presence.count(data_path, now=1000) == 0


def test_a_device_inside_the_window_still_counts(data_path):
    presence.touch("recent", data_path, now=1000)
    assert presence.count(data_path, now=1000 + WINDOW_SECONDS - 1) == 1


def test_count_is_zero_before_anyone_has_been_seen(data_path):
    assert presence.count(data_path) == 0


def test_a_corrupt_file_does_not_break_the_count(data_path):
    open(presence.presence_path(data_path), "w", encoding="utf-8").write("{not json")
    assert presence.touch("aaa", data_path) == 1


def test_a_file_of_the_wrong_shape_does_not_break_the_count(data_path):
    json.dump(["not", "an", "object"],
              open(presence.presence_path(data_path), "w", encoding="utf-8"))
    assert presence.touch("aaa", data_path) == 1


def test_a_failed_write_still_returns_a_count(data_path, monkeypatch):
    """Presence must never be able to break the page it sits on."""
    def boom(obj, dest):
        raise OSError("disk full")
    monkeypatch.setattr(presence, "_atomic_write_json", boom)
    assert presence.touch("aaa", data_path) == 1


def test_the_file_is_capped_so_a_stuck_client_cannot_grow_it(data_path):
    # All inside the window, so the cap is what limits the file, not expiry.
    for n in range(MAX_ENTRIES + 50):
        presence.touch("dev%d" % n, data_path, now=1000 + n * 0.1)
    on_disk = json.load(open(presence.presence_path(data_path), encoding="utf-8"))
    assert len(on_disk) == MAX_ENTRIES
    # The cap keeps the most recent, not the first ones through the door.
    assert "dev%d" % (MAX_ENTRIES + 49) in on_disk
    assert "dev0" not in on_disk


def test_presence_lives_beside_the_client_list(data_path):
    assert presence.presence_path(data_path).endswith("presence.json")
    import os
    assert (os.path.dirname(presence.presence_path(data_path))
            == os.path.dirname(str(data_path)))


# --- the heartbeat endpoint -------------------------------------------------

def beat(client):
    return client.post("/api/presence")


def test_heartbeat_needs_a_staff_login(client, data_path):
    resp = beat(client)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthenticated"


def test_heartbeat_counts_the_caller(logged_in, data_path):
    resp = beat(logged_in)
    assert resp.status_code == 200
    assert resp.get_json()["count"] == 1


def test_two_beats_from_one_browser_are_one_person(logged_in, data_path):
    beat(logged_in)
    assert beat(logged_in).get_json()["count"] == 1


def test_two_browsers_are_two_people(logged_in, data_path):
    from app import app as flask_app
    other = flask_app.test_client()
    other.post("/login", data={"password": "staffpw"})
    beat(logged_in)
    assert beat(other).get_json()["count"] == 2


def test_a_session_from_before_this_feature_still_counts(logged_in, data_path):
    """Everyone already signed in on deploy day has a session with no device id.

    The id is minted lazily here rather than at login so their heartbeats have
    something to key on without making them log in again.
    """
    with logged_in.session_transaction() as sess:
        sess.pop("device", None)
    assert beat(logged_in).get_json()["count"] == 1


def test_heartbeat_refuses_GET(logged_in, data_path):
    """A mutating GET would be cacheable and prefetchable."""
    assert logged_in.get("/api/presence").status_code == 405
