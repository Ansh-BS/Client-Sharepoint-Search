from storage import load_clients, save_clients


def upload(client, path, password="adminpw"):
    with open(path, "rb") as f:
        return client.post(
            "/admin",
            data={"admin_password": password, "file": (f, "upload.xlsx")},
            content_type="multipart/form-data",
        )


def test_admin_requires_staff_login(client):
    resp = client.get("/admin")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_wrong_admin_password_rejected(logged_in, data_path, make_xlsx, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    p = make_xlsx(tmp_path / "new.xlsx", [("N1", "New Client", "https://x")])
    resp = upload(logged_in, p, password="wrong")
    assert b"Wrong admin password" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_valid_upload_replaces_data_and_reports(logged_in, data_path,
                                                make_xlsx, tmp_path):
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


def test_bad_file_keeps_existing_data(logged_in, data_path, tmp_path):
    save_clients([{"id": "OLD", "name": "Old Client", "link": None}], data_path)
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not really an xlsx")
    resp = upload(logged_in, bad)
    assert b"Not a valid .xlsx" in resp.data
    assert [c["name"] for c in load_clients(data_path)] == ["Old Client"]


def test_no_file_selected(logged_in):
    resp = logged_in.post("/admin", data={"admin_password": "adminpw"},
                          content_type="multipart/form-data")
    assert b"No file selected" in resp.data
