import os

import backfill_temp_codes
from storage import load_clients, save_clients


def rows():
    return [{"id": "Acme Ltd", "name": "Acme Ltd", "link": "https://a"},
            {"id": "", "name": "Beta", "link": None},
            {"id": "TEMP01", "name": "Oakfield", "link": None},
            {"id": "RED341", "name": "Redwood", "link": None}]


def test_dry_run_reports_and_writes_nothing(tmp_path, capsys):
    p = tmp_path / "clients.json"
    save_clients(rows(), p)
    before = p.read_bytes()

    minted = backfill_temp_codes.main(["--clients", str(p)])

    assert [m["id"] for m in minted] == ["TEMP02", "TEMP03"]
    assert p.read_bytes() == before
    assert list(tmp_path.iterdir()) == [p]
    out = capsys.readouterr().out
    assert 'Would give 2 clients' in out
    assert '"Acme Ltd" (id "Acme Ltd") -> TEMP02' in out
    assert "Dry run" in out


def test_apply_writes_codes_and_backs_up(tmp_path, capsys):
    p = tmp_path / "clients.json"
    save_clients(rows(), p)
    before = p.read_bytes()

    backfill_temp_codes.main(["--clients", str(p), "--apply"])

    clients = load_clients(p)
    assert [c["id"] for c in clients] == ["TEMP02", "TEMP03", "TEMP01", "RED341"]
    assert clients[0]["link"] == "https://a"
    backups = [f for f in os.listdir(tmp_path) if ".bak-" in f]
    assert len(backups) == 1
    assert (tmp_path / backups[0]).read_bytes() == before


def test_nothing_to_do(tmp_path, capsys):
    p = tmp_path / "clients.json"
    save_clients([{"id": "RED341", "name": "Redwood", "link": None}], p)
    assert backfill_temp_codes.main(["--clients", str(p), "--apply"]) == []
    assert "already has" in capsys.readouterr().out
    assert len(list(tmp_path.iterdir())) == 1


def test_warns_about_likely_duplicates(tmp_path, capsys):
    p = tmp_path / "clients.json"
    save_clients([{"id": "Oakfield", "name": "Oakfield", "link": None},
                  {"id": "TEMP01", "name": "oakfield", "link": None}], p)
    backfill_temp_codes.main(["--clients", str(p)])
    out = capsys.readouterr().out
    assert "Possible duplicates" in out
    assert 'TEMP02 "Oakfield", TEMP01 "oakfield"' in out
