"""Parse the 'SharePoint Links for Clients' spreadsheet into client dicts."""
import openpyxl


class ParseError(Exception):
    """Raised when the uploaded file is not a usable client spreadsheet."""


def parse_xlsx(source):
    """Parse an xlsx (path or file-like) into a list of client dicts.

    Layout: first sheet, one header row, then A=Client ID, B=client name,
    C=cell whose hyperlink target is the SharePoint folder URL.
    Rows with an empty name are skipped; a missing hyperlink gives
    link=None. Raises ParseError for unreadable files or zero valid rows.
    NOTE: must not use read_only=True — that mode drops hyperlinks.
    """
    try:
        wb = openpyxl.load_workbook(source)
    except Exception as exc:
        raise ParseError(f"Not a valid .xlsx file: {exc}") from exc

    clients = []
    for row in wb.worksheets[0].iter_rows(min_row=2):
        if len(row) < 3:
            continue
        cid = str(row[0].value).strip() if row[0].value else ""
        name = str(row[1].value).strip() if row[1].value else ""
        if not name:
            continue
        link_cell = row[2]
        link = link_cell.hyperlink.target if link_cell.hyperlink else None
        clients.append({"id": cid, "name": name, "link": link})

    if not clients:
        raise ParseError(
            "No client rows found — wrong file or wrong sheet layout.")
    return clients
