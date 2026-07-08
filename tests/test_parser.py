import pytest

from xlsx_parser import parse_xlsx, ParseError


def test_parses_clients_with_links(tmp_path, make_xlsx):
    p = make_xlsx(tmp_path / "ok.xlsx", [
        ("NAS313", "Abbas Hassan Nasser", "https://example.sharepoint.com/a"),
        ("RAO026", "Abdul Ammar Amin Rao", "https://example.sharepoint.com/b"),
    ])
    assert parse_xlsx(p) == [
        {"id": "NAS313", "name": "Abbas Hassan Nasser",
         "link": "https://example.sharepoint.com/a"},
        {"id": "RAO026", "name": "Abdul Ammar Amin Rao",
         "link": "https://example.sharepoint.com/b"},
    ]


def test_missing_hyperlink_gives_none(tmp_path, make_xlsx):
    p = make_xlsx(tmp_path / "nolink.xlsx", [("AHM407", "Aizaz Ahmed", None)])
    assert parse_xlsx(p) == [{"id": "AHM407", "name": "Aizaz Ahmed", "link": None}]


def test_rows_without_name_skipped(tmp_path, make_xlsx):
    p = make_xlsx(tmp_path / "gap.xlsx", [
        ("X1", "Real Client", "https://example.com/x"),
        ("X2", "", None),
    ])
    assert [c["name"] for c in parse_xlsx(p)] == ["Real Client"]


def test_not_an_xlsx_raises(tmp_path):
    p = tmp_path / "fake.xlsx"
    p.write_bytes(b"this is not a zip")
    with pytest.raises(ParseError):
        parse_xlsx(p)


def test_header_only_raises(tmp_path, make_xlsx):
    p = make_xlsx(tmp_path / "empty.xlsx", [])
    with pytest.raises(ParseError):
        parse_xlsx(p)
