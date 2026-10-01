"""The CLI import must keep temp-code clients, exactly as the web upload does.

Two import paths that disagree about this would mean a restore run from the
terminal silently deletes clients the admin page would have kept.
"""
import import_xlsx
from storage import load_clients, save_clients


def test_cli_import_keeps_a_temp_client_absent_from_the_file(
        data_path, make_xlsx, tmp_path, monkeypatch, capsys):
    save_clients([{"id": "TEMP01", "name": "Oakfield", "link": "https://oak"}],
                 data_path)
    path = make_xlsx(tmp_path / "u.xlsx", [("RED341", "Redwood", "https://red")])
    monkeypatch.setattr("sys.argv", ["import_xlsx.py", str(path)])
    import_xlsx.main()
    clients = load_clients(data_path)
    assert sorted(c["name"] for c in clients) == ["Oakfield", "Redwood"]
    assert "1 awaiting a real ID" in capsys.readouterr().out


def test_cli_import_lets_the_file_retire_a_temp_row(
        data_path, make_xlsx, tmp_path, monkeypatch, capsys):
    save_clients([{"id": "TEMP01", "name": "Oakfield", "link": None}],
                 data_path)
    path = make_xlsx(tmp_path / "u.xlsx", [("OAK118", "Oakfield", "https://oak")])
    monkeypatch.setattr("sys.argv", ["import_xlsx.py", str(path)])
    import_xlsx.main()
    clients = load_clients(data_path)
    assert len(clients) == 1
    assert clients[0]["id"] == "OAK118"
