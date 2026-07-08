from storage import save_clients


def test_index_redirects_when_logged_out(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_wrong_password_shows_error(client):
    resp = client.post("/login", data={"password": "nope"})
    assert b"Wrong password" in resp.data


def test_right_password_logs_in(client):
    resp = client.post("/login", data={"password": "staffpw"},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert b"search" in resp.data.lower()


def test_api_unauthenticated_gets_401_json(client):
    resp = client.get("/api/clients")
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "unauthenticated"}


def test_api_returns_clients_when_logged_in(logged_in, data_path):
    save_clients([{"id": "A1", "name": "Test Client", "link": None}], data_path)
    resp = logged_in.get("/api/clients")
    assert resp.status_code == 200
    assert resp.get_json() == [{"id": "A1", "name": "Test Client", "link": None}]


def test_logout_clears_session(logged_in):
    logged_in.get("/logout")
    assert logged_in.get("/").status_code == 302
