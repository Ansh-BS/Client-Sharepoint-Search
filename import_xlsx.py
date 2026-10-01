"""One-off CLI: import a client spreadsheet into data/clients.json."""
import sys

from storage import load_clients, save_clients
from temp_codes import merge_temp_clients
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
    # Same rule as the admin upload: a client added before their permanent code
    # existed is not in the spreadsheet yet, and a restore must not delete them.
    merged, kept = merge_temp_clients(clients, load_clients())
    save_clients(merged)
    missing = [c["name"] for c in merged if not c["link"]]
    print(f"{len(merged)} clients imported, {len(missing)} missing links, "
          f"{len(kept)} awaiting a real ID.")
    for name in missing:
        print(f"  no link: {name}")
    for c in kept:
        print(f"  kept, awaiting a real ID: {c['id']} {c['name']}")


if __name__ == "__main__":
    main()
