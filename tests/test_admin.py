import logging
import re
import time

import pytest

import app
from storage import load_clients, load_pending, save_clients


def preview(client, path):
    """Step 1: upload for review. Returns the response (data NOT yet saved)."""
    with open(path, "rb") as f:
        return client.post(
            "/admin",
            data={"file": (f, "upload.xlsx")},
            content_type="multipart/form-data",
        )


def _token(resp):
    m = re.search(rb'name="token" value="([^"]+)"', resp.data)
    return m.group(1).decode() if m else None


def confirm(client, token):
    """Step 2: commit the reviewed upload."""
    return client.post("/admin", data={"action": "confirm", "token": token})


def upload(client, path):
    """Full two-step replace: preview then confirm. Returns the confirm resp."""
    resp = preview(client, path)
    token = _token(resp)
    return confirm(client, token)


def test_admin_requires_staff_login(client):
    resp = client.get("/admin")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# --- admin-page unlock gate ------------------------------------------------

def test_admin_requires_unlock(logged_in, data_path):
    resp = logged_in.get("/admin")
    assert resp.status_code == 302
    assert "/admin/unlock" in resp.headers["Location"]


def test_unlock_page_shown_to_staff(logged_in):
    resp = logged_in.get("/admin/unlock")
    assert resp.status_code == 200
    assert b"Admin username" in resp.data
    assert b"Admin password" in resp.data


def test_unlock_correct_credentials_grant_access(logged_in, data_path):
    resp = logged_in.post("/admin/unlock",
                          data={"username": "adminuser", "password": "adminpw"})
    assert resp.status_code == 302
    assert "/admin" in resp.headers["Location"]
    assert logged_in.get("/admin").status_code == 200


def test_unlock_username_ignores_case_and_surrounding_space(logged_in, data_path):
    resp = logged_in.post("/admin/unlock",
                          data={"username": "  AdminUser ",
                                "password": "adminpw"})
    assert resp.status_code == 302
    assert logged_in.get("/admin").status_code == 200


def test_unlock_wrong_password_rejected(logged_in, data_path):
    resp = logged_in.post("/admin/unlock",
                          data={"username": "adminuser", "password": "nope"})
    assert b"Wrong admin username or password" in resp.data
    assert logged_in.get("/admin").status_code == 302  # still locked


def test_unlock_wrong_username_rejected(logged_in, data_path):
    resp = logged_in.post("/admin/unlock",
                          data={"username": "someoneelse",
                                "password": "adminpw"})
    assert b"Wrong admin username or password" in resp.data
    assert logged_in.get("/admin").status_code == 302


@pytest.mark.parametrize("name", ["adminuser", "secondadmin", "officemanager"])
def test_every_configured_username_unlocks_with_the_shared_password(
        logged_in, data_path, name):
    resp = logged_in.post("/admin/unlock",
                          data={"username": name, "password": "adminpw"})
    assert resp.status_code == 302
    assert logged_in.get("/admin").status_code == 200


def test_username_not_in_the_list_is_rejected(logged_in, data_path):
    resp = logged_in.post("/admin/unlock",
                          data={"username": "fourthperson",
                                "password": "adminpw"})
    assert b"Wrong admin username or password" in resp.data
    assert logged_in.get("/admin").status_code == 302


def test_unlock_stores_the_canonical_username_in_the_session(logged_in,
                                                             data_path):
    logged_in.post("/admin/unlock",
                   data={"username": " SECONDADMIN ", "password": "adminpw"})
    with logged_in.session_transaction() as sess:
        assert sess["admin_user"] == "secondadmin"


def test_admin_page_never_shows_the_username(admin, data_path):
    """The record is for the server log only — not for the page."""
    body = admin.get("/admin").data.lower()
    for name in (b"adminuser", b"secondadmin", b"officemanager"):
        assert name not in body


def test_unlock_missing_username_rejected(logged_in, data_path):
    resp = logged_in.post("/admin/unlock", data={"password": "adminpw"})
    assert b"Wrong admin username or password" in resp.data
    assert logged_in.get("/admin").status_code == 302


def test_unlock_error_does_not_say_which_field_was_wrong(logged_in, data_path):
    resp = logged_in.post("/admin/unlock",
                          data={"username": "adminuser", "password": "nope"})
    body = resp.data.lower()
    assert b"wrong admin password" not in body
    assert b"wrong admin username." not in body


def test_unlock_requires_staff_login(client):
    resp = client.get("/admin/unlock")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_logout_clears_admin(admin, data_path):
    assert admin.get("/admin").status_code == 200
    admin.get("/logout")
    resp = admin.get("/admin")
    assert resp.status_code == 302  # session cleared -> gate redirects


# --- upload flow (now behind the unlock gate, no upload password) ----------

def test_admin_page_has_no_password_field(admin, data_path):
    resp = admin.get("/admin")
    assert b'name="admin_password"' not in resp.data


def test_upload_needs_no_admin_password(admin, data_path, make_xlsx, tmp_path):
    p = make_xlsx(tmp_path / "new.xlsx", [("N1", "New Client", "https://x")])
    resp = upload(admin, p)
    assert b"Client list replaced" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == ["New Client"]


def test_preview_does_not_modify_data(admin, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("N1", "New Client", "https://x")])
    resp = preview(admin, p)
    assert b"Review before replacing" in resp.data
    assert _token(resp) is not None
    # Nothing committed until confirm.
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_confirm_replaces_data_and_reports(admin, data_path, make_xlsx,
                                           tmp_path):
    p = make_xlsx(tmp_path / "new.xlsx", [
        ("N1", "New Client", "https://x"),
        ("N2", "Linkless Client", None),
    ])
    resp = upload(admin, p)
    assert b"2 clients imported" in resp.data
    assert b"1 client with no SharePoint link" in resp.data
    assert b"Linkless Client" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == \
        ["New Client", "Linkless Client"]


def test_preview_warns_about_dropped_clients(admin, data_path, make_xlsx,
                                             tmp_path):
    save_clients([
        {"id": "OLD1", "name": "Vanishing Client", "link": "https://a"},
        {"id": "KEEP", "name": "Kept Client", "link": "https://b"},
    ], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("KEEP", "Kept Client", "https://b")])
    resp = preview(admin, p)
    assert b"will stop being findable" in resp.data
    assert b"Vanishing Client" in resp.data


def test_a_list_that_moves_under_the_preview_is_re_shown_not_committed(
        admin, data_path, make_xlsx, tmp_path):
    """The preview's promise is about consequences, not just about data.

    The file that gets written is pinned by token, so the *data* is never a
    surprise. The diff is not: it is computed against the live list at preview
    time, so if the list moves before confirm, the admin agreed to a set of
    consequences that no longer holds.
    """
    save_clients([{"id": "A1", "name": "Acme Ltd", "link": None}], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("B1", "Beta Ltd", "https://b")])
    resp = preview(admin, p)
    assert b"Acme Ltd" in resp.data          # the one drop they were shown
    token = _token(resp)

    # A second admin adds a client while the preview sits on screen. Replacing
    # now would drop it too, and nobody has been told.
    save_clients([{"id": "A1", "name": "Acme Ltd", "link": None},
                  {"id": "C1", "name": "Gamma Ltd", "link": None}], data_path)

    resp = confirm(admin, token)

    assert [c["id"] for c in load_clients(data_path)] == ["A1", "C1"], (
        "committed a replace whose consequences the admin was never shown")
    assert b"changed while you were reviewing" in resp.data
    assert b"Gamma Ltd" in resp.data          # the newly-exposed drop


def test_re_confirming_the_refreshed_preview_commits_without_re_uploading(
        admin, data_path, make_xlsx, tmp_path):
    """The parsed file is still stashed, so only the diff needed refreshing."""
    save_clients([{"id": "A1", "name": "Acme Ltd", "link": None}], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("B1", "Beta Ltd", "https://b")])
    token = _token(preview(admin, p))
    save_clients([{"id": "A1", "name": "Acme Ltd", "link": None},
                  {"id": "C1", "name": "Gamma Ltd", "link": None}], data_path)

    refreshed = confirm(admin, token)
    assert _token(refreshed) == token

    confirm(admin, token)
    assert [c["id"] for c in load_clients(data_path)] == ["B1"]


def test_an_unrelated_edit_to_a_link_does_not_force_a_re_confirm(
        admin, data_path, make_xlsx, tmp_path):
    """Only a change that alters the diff should interrupt. A link edit
    changes the live list but not who is about to stop being findable."""
    save_clients([{"id": "A1", "name": "Acme Ltd", "link": None}], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("B1", "Beta Ltd", "https://b")])
    token = _token(preview(admin, p))
    save_clients([{"id": "A1", "name": "Acme Ltd", "link": "https://new"}],
                 data_path)

    confirm(admin, token)
    assert [c["id"] for c in load_clients(data_path)] == ["B1"]


def test_cancel_discards_preview(admin, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("N1", "New Client", "https://x")])
    resp = preview(admin, p)
    token = _token(resp)
    admin.post("/admin", data={"action": "cancel"})
    # The stashed preview is gone: confirming the old token now fails.
    resp2 = confirm(admin, token)
    assert b"expired" in resp2.data
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_confirm_without_preview_rejected(admin, data_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    resp = confirm(admin, "forged-token-aaaaaaaaaaaaaaaa")
    assert b"expired" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_bad_file_keeps_existing_data(admin, data_path, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not really an xlsx")
    resp = preview(admin, bad)
    assert b"Not a valid .xlsx" in resp.data
    assert _token(resp) is None
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_no_file_selected(admin):
    resp = admin.post("/admin", data={}, content_type="multipart/form-data")
    assert b"No file selected" in resp.data


# --- quick add / delete (no spreadsheet) — two-step preview/confirm --------

def preview_add(client, name, cid, link=""):
    return client.post("/admin", data={
        "action": "add_client", "client_name": name,
        "client_id": cid, "client_link": link})


def confirm_add(client):
    return client.post("/admin", data={"action": "confirm_add_client"})


def add_client(client, name, cid, link=""):
    """Full two-step add/update: preview then confirm."""
    preview_add(client, name, cid, link)
    return confirm_add(client)


def preview_delete(client, query):
    return client.post("/admin", data={"action": "delete_client",
                                       "client_query": query})


def confirm_delete(client):
    return client.post("/admin", data={"action": "confirm_delete_client"})


def delete_client(client, query):
    """Full two-step remove: preview then confirm."""
    preview_delete(client, query)
    return confirm_delete(client)


def test_add_client_preview_does_not_save(admin, data_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    resp = preview_add(admin, "New Client", "N1", "https://x")
    assert b"Review before saving" in resp.data
    assert b"Adds a new client" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_add_client_appends_new(admin, data_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    resp = add_client(admin, "New Client", "N1", "https://x")
    assert b"Added client: New Client" in resp.data
    names = [c["name"] for c in load_clients(data_path)]
    assert names == ["Old Client", "New Client"]


def test_add_client_updates_existing_by_id(admin, data_path):
    save_clients([{"id": "N1", "name": "New Client", "link": None}], data_path)
    resp = preview_add(admin, "New Client", "N1", "https://x")
    assert b"Updates existing client" in resp.data
    resp = confirm_add(admin)
    assert b"Updated client: New Client" in resp.data
    clients = load_clients(data_path)
    assert len(clients) == 1
    assert clients[0]["link"] == "https://x"


def test_add_client_requires_name(admin, data_path):
    resp = preview_add(admin, "", "N1")
    assert b"Client name and Client ID required" in resp.data
    assert load_clients(data_path) == []


def test_add_client_requires_id(admin, data_path):
    resp = preview_add(admin, "New Client", "")
    assert b"Client name and Client ID required" in resp.data
    assert load_clients(data_path) == []


def test_confirm_add_client_without_preview_rejected(admin, data_path):
    resp = confirm_add(admin)
    assert b"expired" in resp.data
    assert load_clients(data_path) == []


def test_delete_client_preview_does_not_remove(admin, data_path):
    save_clients([{"id": "N1", "name": "New Client", "link": None}], data_path)
    resp = preview_delete(admin, "N1")
    assert b"Review before removing" in resp.data
    assert b"New Client" in resp.data
    assert len(load_clients(data_path)) == 1


def test_delete_client_by_id(admin, data_path):
    save_clients([
        {"id": "N1", "name": "New Client", "link": None},
        {"id": "N2", "name": "Other Client", "link": None},
    ], data_path)
    resp = delete_client(admin, "N1")
    assert b"Removed client: New Client" in resp.data
    names = [c["name"] for c in load_clients(data_path)]
    assert names == ["Other Client"]


def test_delete_client_by_name(admin, data_path):
    save_clients([{"id": "", "name": "No Id Client", "link": None}], data_path)
    resp = delete_client(admin, "no id client")
    assert b"Removed client: No Id Client" in resp.data
    assert load_clients(data_path) == []


def test_confirming_a_removal_only_ever_removes_what_was_previewed(admin,
                                                                   data_path):
    """The preview promises "this client will stop being findable".

    Two clients can share a name — PRODUCT.md calls that out — so a query is
    not an identity. Re-running the query at confirm time means that if the
    list moves underneath the preview, the row that gets deleted is not the
    row the admin was shown and agreed to.
    """
    save_clients([{"id": "A1", "name": "Acme Ltd", "link": None},
                  {"id": "A2", "name": "Acme Ltd", "link": None}], data_path)
    preview_delete(admin, "Acme Ltd")          # resolves to A1, the first match

    # While the preview sits on screen, A1 goes — a second admin, or an upload.
    save_clients([{"id": "A2", "name": "Acme Ltd", "link": None}], data_path)

    resp = confirm_delete(admin)

    assert [c["id"] for c in load_clients(data_path)] == ["A2"], (
        "confirming a preview of A1 removed A2, which was never previewed")
    assert b"no longer in the list" in resp.data


def test_delete_client_not_found(admin, data_path):
    save_clients([{"id": "N1", "name": "New Client", "link": None}], data_path)
    resp = preview_delete(admin, "Nope")
    assert b"No client matches" in resp.data
    assert len(load_clients(data_path)) == 1


def test_delete_client_requires_query(admin, data_path):
    resp = preview_delete(admin, "")
    assert b"Enter a client name or ID" in resp.data


def test_confirm_delete_client_without_preview_rejected(admin, data_path):
    save_clients([{"id": "N1", "name": "New Client", "link": None}], data_path)
    resp = confirm_delete(admin)
    assert b"expired" in resp.data
    assert len(load_clients(data_path)) == 1


def test_cancel_discards_add_preview(admin, data_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    preview_add(admin, "New Client", "N1", "https://x")
    admin.post("/admin", data={"action": "cancel"})
    resp = confirm_add(admin)
    assert b"expired" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_cancel_discards_delete_preview(admin, data_path):
    save_clients([{"id": "N1", "name": "New Client", "link": None}], data_path)
    preview_delete(admin, "N1")
    admin.post("/admin", data={"action": "cancel"})
    resp = confirm_delete(admin)
    assert b"expired" in resp.data
    assert len(load_clients(data_path)) == 1


# --- terminal audit log ----------------------------------------------------

def test_unlock_logs_who_got_in(logged_in, data_path, caplog):
    with caplog.at_level(logging.INFO):
        logged_in.post("/admin/unlock",
                       data={"username": "secondadmin", "password": "adminpw"})
    assert "ADMIN unlock ok" in caplog.text
    assert "secondadmin" in caplog.text


def test_failed_unlock_logs_the_attempted_username(logged_in, data_path,
                                                   caplog):
    with caplog.at_level(logging.INFO):
        logged_in.post("/admin/unlock",
                       data={"username": "intruder", "password": "nope"})
    assert "ADMIN unlock FAILED" in caplog.text
    assert "intruder" in caplog.text


def test_log_line_cannot_be_forged_through_the_username(logged_in, data_path,
                                                        caplog):
    with caplog.at_level(logging.INFO):
        logged_in.post("/admin/unlock",
                       data={"username": "x\nADMIN unlock ok user=boss",
                             "password": "nope"})
    assert "\nADMIN unlock ok" not in caplog.text


def test_confirmed_add_is_logged_with_the_username(admin, data_path, caplog):
    admin.post("/admin", data={"action": "add_client",
                               "client_name": "Acme Ltd",
                               "client_id": "A1",
                               "client_link": "https://example.com/a"})
    with caplog.at_level(logging.INFO):
        admin.post("/admin", data={"action": "confirm_add_client"})
    assert "ADMIN add" in caplog.text
    assert "adminuser" in caplog.text
    assert "Acme Ltd" in caplog.text


def test_preview_alone_is_not_logged(admin, data_path, caplog):
    """A preview changes nothing, so it leaves no line in the log."""
    with caplog.at_level(logging.INFO):
        admin.post("/admin", data={"action": "add_client",
                                   "client_name": "Acme Ltd",
                                   "client_id": "A1"})
    assert "ADMIN add" not in caplog.text


def test_confirmed_remove_is_logged_with_the_username(admin, data_path,
                                                      caplog):
    save_clients([{"id": "A1", "name": "Acme Ltd", "link": None}], data_path)
    admin.post("/admin", data={"action": "delete_client",
                               "client_query": "Acme Ltd"})
    with caplog.at_level(logging.INFO):
        admin.post("/admin", data={"action": "confirm_delete_client"})
    assert "ADMIN remove" in caplog.text
    assert "adminuser" in caplog.text
    assert "Acme Ltd" in caplog.text


def test_confirmed_replace_is_logged_with_the_username(admin, data_path,
                                                       make_xlsx, tmp_path,
                                                       caplog):
    path = make_xlsx(tmp_path / "c.xlsx",
                     [("A1", "Acme Ltd", "https://example.com/a"),
                      ("A2", "Beta Ltd", "https://example.com/b")])
    with open(path, "rb") as fh:
        admin.post("/admin", data={"file": (fh, "c.xlsx")},
                   content_type="multipart/form-data")
    with admin.session_transaction() as sess:
        token = sess["pending_upload"]
    with caplog.at_level(logging.INFO):
        admin.post("/admin", data={"action": "confirm", "token": token})
    assert "ADMIN replace" in caplog.text
    assert "adminuser" in caplog.text
    assert "clients=2" in caplog.text


# --- admin idle re-lock ----------------------------------------------------

def _age_admin_session(client, seconds):
    """Backdate the admin session's last-seen stamp by `seconds`."""
    with client.session_transaction() as sess:
        sess["admin_at"] = time.time() - seconds


def test_admin_survives_a_short_gap(admin, data_path):
    _age_admin_session(admin, app.ADMIN_IDLE_SECONDS - 60)
    assert admin.get("/admin").status_code == 200


def test_admin_relocks_after_the_idle_window(admin, data_path):
    _age_admin_session(admin, app.ADMIN_IDLE_SECONDS + 1)
    resp = admin.get("/admin")
    assert resp.status_code == 302
    assert "/admin/unlock" in resp.headers["Location"]
    assert "timeout=1" in resp.headers["Location"]


def test_relock_clears_the_admin_half_of_the_session(admin, data_path):
    _age_admin_session(admin, app.ADMIN_IDLE_SECONDS + 1)
    admin.get("/admin")
    with admin.session_transaction() as sess:
        assert "admin" not in sess
        assert "admin_user" not in sess
        assert "admin_at" not in sess


def test_staff_login_survives_an_admin_relock(admin, data_path):
    _age_admin_session(admin, app.ADMIN_IDLE_SECONDS + 1)
    admin.get("/admin")
    assert admin.get("/").status_code == 200  # still signed in to search


def test_every_admin_request_pushes_the_clock_forward(admin, data_path):
    _age_admin_session(admin, app.ADMIN_IDLE_SECONDS - 60)
    admin.get("/admin")
    with admin.session_transaction() as sess:
        assert time.time() - sess["admin_at"] < 5


def test_relock_discards_a_staged_upload(admin, data_path, make_xlsx,
                                         tmp_path):
    path = make_xlsx(tmp_path / "c.xlsx", [("A1", "Acme Ltd", None)])
    with open(path, "rb") as fh:
        admin.post("/admin", data={"file": (fh, "c.xlsx")},
                   content_type="multipart/form-data")
    with admin.session_transaction() as sess:
        token = sess["pending_upload"]
    assert load_pending(token) is not None
    _age_admin_session(admin, app.ADMIN_IDLE_SECONDS + 1)
    admin.get("/admin")
    assert load_pending(token) is None
    with admin.session_transaction() as sess:
        assert "pending_upload" not in sess


def test_relock_discards_a_pending_add(admin, data_path):
    admin.post("/admin", data={"action": "add_client",
                               "client_name": "Acme Ltd", "client_id": "A1"})
    _age_admin_session(admin, app.ADMIN_IDLE_SECONDS + 1)
    admin.get("/admin")
    with admin.session_transaction() as sess:
        assert "pending_action" not in sess


def test_relock_is_logged(admin, data_path, caplog):
    _age_admin_session(admin, app.ADMIN_IDLE_SECONDS + 1)
    with caplog.at_level(logging.INFO):
        admin.get("/admin")
    assert "ADMIN auto-lock" in caplog.text
    assert "adminuser" in caplog.text


def test_unlock_page_explains_a_timeout(logged_in):
    resp = logged_in.get("/admin/unlock?timeout=1")
    assert b"inactivity" in resp.data
    # The wording follows the constant, so the two can't drift apart.
    assert f"{app.ADMIN_IDLE_SECONDS // 60} minutes".encode() in resp.data


def test_unlock_page_says_nothing_about_a_timeout_normally(logged_in):
    resp = logged_in.get("/admin/unlock")
    assert b"inactivity" not in resp.data

