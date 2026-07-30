from storage import load_clients, save_clients, load_report, save_report, report_path


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


def test_load_report_missing_returns_none(tmp_path):
    assert load_report(tmp_path / "clients.json") is None


def test_save_then_load_report_roundtrip(tmp_path):
    p = tmp_path / "clients.json"
    report = {"checked_at": "2026-07-30T11:00:00Z", "total": 1,
              "counts": {"ok": 1, "dead": 0, "suspect": 0, "nolink": 0, "error": 0},
              "flagged": []}
    save_report(report, p)
    assert load_report(p) == report


def test_report_sits_beside_clients(tmp_path):
    p = tmp_path / "clients.json"
    assert report_path(p) == str(tmp_path / "link_health.json")
