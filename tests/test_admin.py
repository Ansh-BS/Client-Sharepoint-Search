import re

import app as app_module
from storage import load_clients, save_clients, save_report


def preview(client, path, password="adminpw"):
    """Step 1: upload for review. Returns the response (data NOT yet saved)."""
    with open(path, "rb") as f:
        return client.post(
            "/admin",
            data={"admin_password": password, "file": (f, "upload.xlsx")},
            content_type="multipart/form-data",
        )


def _token(resp):
    m = re.search(rb'name="token" value="([^"]+)"', resp.data)
    return m.group(1).decode() if m else None


def confirm(client, token):
    """Step 2: commit the reviewed upload."""
    return client.post("/admin", data={"action": "confirm", "token": token})


def upload(client, path, password="adminpw"):
    """Full two-step replace: preview then confirm. Returns the confirm resp."""
    resp = preview(client, path, password=password)
    token = _token(resp)
    return confirm(client, token)


def test_admin_requires_staff_login(client):
    resp = client.get("/admin")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_wrong_admin_password_rejected(logged_in, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("N1", "New Client", "https://x")])
    resp = preview(logged_in, p, password="wrong")
    assert b"Wrong admin password" in resp.data
    assert _token(resp) is None
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_preview_does_not_modify_data(logged_in, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("N1", "New Client", "https://x")])
    resp = preview(logged_in, p)
    assert b"Review before replacing" in resp.data
    assert _token(resp) is not None
    # Nothing committed until confirm.
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_confirm_replaces_data_and_reports(logged_in, data_path, make_xlsx,
                                           tmp_path):
    p = make_xlsx(tmp_path / "new.xlsx", [
        ("N1", "New Client", "https://x"),
        ("N2", "Linkless Client", None),
    ])
    resp = upload(logged_in, p)
    assert b"2 clients imported" in resp.data
    assert b"1 client with no SharePoint link" in resp.data
    assert b"Linkless Client" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == \
        ["New Client", "Linkless Client"]


def test_preview_warns_about_dropped_clients(logged_in, data_path, make_xlsx,
                                             tmp_path):
    save_clients([
        {"id": "OLD1", "name": "Vanishing Client", "link": "https://a"},
        {"id": "KEEP", "name": "Kept Client", "link": "https://b"},
    ], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("KEEP", "Kept Client", "https://b")])
    resp = preview(logged_in, p)
    assert b"will stop being findable" in resp.data
    assert b"Vanishing Client" in resp.data


def test_cancel_discards_preview(logged_in, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("N1", "New Client", "https://x")])
    resp = preview(logged_in, p)
    token = _token(resp)
    logged_in.post("/admin", data={"action": "cancel"})
    # The stashed preview is gone: confirming the old token now fails.
    resp2 = confirm(logged_in, token)
    assert b"expired" in resp2.data
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_confirm_without_preview_rejected(logged_in, data_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    resp = confirm(logged_in, "forged-token-aaaaaaaaaaaaaaaa")
    assert b"expired" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_bad_file_keeps_existing_data(logged_in, data_path, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not really an xlsx")
    resp = preview(logged_in, bad)
    assert b"Not a valid .xlsx" in resp.data
    assert _token(resp) is None
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_no_file_selected(logged_in):
    resp = logged_in.post("/admin", data={"admin_password": "adminpw"},
                          content_type="multipart/form-data")
    assert b"No file selected" in resp.data


def test_admin_shows_no_check_yet(logged_in, data_path):
    resp = logged_in.get("/admin")
    assert b"No link check has been run yet" in resp.data


def test_admin_shows_all_ok(logged_in, data_path):
    save_report({"checked_at": "2026-07-30T11:00:00Z", "total": 3,
                 "counts": {"ok": 3, "dead": 0, "suspect": 0, "nolink": 0,
                            "error": 0}, "flagged": []}, data_path)
    resp = logged_in.get("/admin")
    assert b"All 3 links OK" in resp.data


def test_admin_lists_flagged(logged_in, data_path):
    save_report({"checked_at": "2026-07-30T11:00:00Z", "total": 2,
                 "counts": {"ok": 0, "dead": 1, "suspect": 1, "nolink": 0,
                            "error": 0},
                 "flagged": [
                     {"id": "D1", "name": "Dead Client", "category": "dead",
                      "status": 404},
                     {"id": "S1", "name": "Suspect Client", "category": "suspect",
                      "status": 200}]}, data_path)
    resp = logged_in.get("/admin")
    assert b"Dead Client" in resp.data
    assert b"Suspect Client" in resp.data
    assert b"dead" in resp.data and b"suspect" in resp.data


def test_button_hidden_when_disabled(logged_in, data_path, monkeypatch):
    monkeypatch.setattr(app_module, "LINK_CHECK_ENABLED", False)
    resp = logged_in.get("/admin")
    assert b'value="check_links"' not in resp.data


def test_button_shown_when_enabled(logged_in, data_path, monkeypatch):
    monkeypatch.setattr(app_module, "LINK_CHECK_ENABLED", True)
    resp = logged_in.get("/admin")
    assert b'value="check_links"' in resp.data


def test_check_links_post_disabled_is_refused(logged_in, data_path, monkeypatch):
    monkeypatch.setattr(app_module, "LINK_CHECK_ENABLED", False)
    resp = logged_in.post("/admin", data={"action": "check_links"})
    assert b"not enabled" in resp.data


def test_check_links_post_enabled_runs(logged_in, data_path, monkeypatch):
    monkeypatch.setattr(app_module, "LINK_CHECK_ENABLED", True)
    ran = {}
    def fake_check_all(clients, **kw):
        ran["called"] = True
        return {"checked_at": "2026-07-30T11:00:00Z", "total": 0,
                "counts": {"ok": 0, "dead": 0, "suspect": 0, "nolink": 0,
                           "error": 0}, "flagged": []}
    monkeypatch.setattr(app_module, "check_all", fake_check_all)
    resp = logged_in.post("/admin", data={"action": "check_links"})
    assert b"Check running" in resp.data
