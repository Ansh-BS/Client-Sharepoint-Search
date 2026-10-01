"""CLI: list the clients still carrying a temporary Client ID.

The same list the /admin page shows, for anyone who would rather run it from a
terminal or a scheduled task. Read-only — it never edits the client list.

    python check_temp_codes.py [--clients path.json]
"""
import argparse

from storage import load_clients
from temp_codes import pending_temp


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="List clients awaiting a real Client ID.")
    ap.add_argument("--clients", default=None,
                    help="clients.json path (default: CLIENTS_JSON env or data/)")
    args = ap.parse_args(argv)

    waiting = pending_temp(load_clients(args.clients))
    if not waiting:
        print("No clients are awaiting a real ID.")
        return waiting

    print(f"{len(waiting)} client{'' if len(waiting) == 1 else 's'} "
          "awaiting a real ID")
    for c in waiting:
        print(f"  {c['id']}  {c['name']}")
    return waiting


if __name__ == "__main__":
    main()
