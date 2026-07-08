"""One-off CLI: import a client spreadsheet into data/clients.json."""
import sys

from storage import save_clients
from xlsx_parser import ParseError, parse_xlsx


def main():
    if len(sys.argv) != 2:
        print("Usage: python import_xlsx.py <path-to-xlsx>")
        sys.exit(1)
    try:
        clients = parse_xlsx(sys.argv[1])
    except ParseError as exc:
        print(f"Import failed: {exc}")
        sys.exit(1)
    save_clients(clients)
    missing = [c["name"] for c in clients if not c["link"]]
    print(f"{len(clients)} clients imported, {len(missing)} missing links.")
    for name in missing:
        print(f"  no link: {name}")


if __name__ == "__main__":
    main()
