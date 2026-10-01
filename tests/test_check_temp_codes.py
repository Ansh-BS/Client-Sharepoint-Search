import check_temp_codes
from storage import save_clients


def test_cli_lists_clients_awaiting_a_real_code(tmp_path, capsys):
    p = tmp_path / "clients.json"
    save_clients([{"id": "TEMP02", "name": "Oakfield", "link": None},
                  {"id": "RED341", "name": "Redwood", "link": None},
                  {"id": "TEMP01", "name": "Ashby", "link": None}], p)

    waiting = check_temp_codes.main(["--clients", str(p)])

    assert [c["name"] for c in waiting] == ["Ashby", "Oakfield"]
    out = capsys.readouterr().out
    assert "2 clients awaiting a real ID" in out
    assert "TEMP01" in out and "Ashby" in out
    assert "Redwood" not in out


def test_cli_says_so_when_nothing_is_waiting(tmp_path, capsys):
    p = tmp_path / "clients.json"
    save_clients([{"id": "RED341", "name": "Redwood", "link": None}], p)

    assert check_temp_codes.main(["--clients", str(p)]) == []
    assert "No clients" in capsys.readouterr().out
