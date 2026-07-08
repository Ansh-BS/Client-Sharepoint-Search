from storage import load_clients, save_clients


def test_load_missing_file_returns_empty(tmp_path):
    assert load_clients(tmp_path / "nope.json") == []


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "clients.json"
    data = [{"id": "A1", "name": "Test Client", "link": None}]
    save_clients(data, p)
    assert load_clients(p) == data


def test_save_replaces_existing(tmp_path):
    p = tmp_path / "clients.json"
    save_clients([{"id": "A", "name": "Old", "link": None}], p)
    save_clients([{"id": "B", "name": "New", "link": "https://x"}], p)
    assert [c["name"] for c in load_clients(p)] == ["New"]


def test_env_var_overrides_default_path(tmp_path, monkeypatch):
    p = tmp_path / "override.json"
    monkeypatch.setenv("CLIENTS_JSON", str(p))
    save_clients([{"id": "E1", "name": "Env Client", "link": None}])
    assert load_clients() == [{"id": "E1", "name": "Env Client", "link": None}]
