import check_links
import link_health
from storage import load_report, save_clients


def test_cli_writes_report_beside_clients(tmp_path, monkeypatch, capsys):
    p = tmp_path / "clients.json"
    save_clients([{"id": "A1", "name": "Alive", "link": "http://ok"},
                  {"id": "D1", "name": "Dead", "link": "http://dead"}], p)
    monkeypatch.setattr(link_health, "check_link", lambda url, timeout=15:
                        ("ok", 401) if url == "http://ok" else ("dead", 404))

    report = check_links.main(["--clients", str(p), "--workers", "2"])

    on_disk = load_report(p)
    assert on_disk == report
    assert on_disk["counts"]["dead"] == 1
    assert [f["id"] for f in on_disk["flagged"]] == ["D1"]
    assert "1 dead" in capsys.readouterr().out
