"""CLI: check every client's SharePoint link and write a health report.

Runs the same engine the admin button uses. Safe to run on a PC/office
machine or on the server; it writes link_health.json beside clients.json and
never edits the client list.

    python check_links.py [--workers 8] [--timeout 15] [--clients path.json]
"""
import argparse

from link_health import check_all
from storage import load_clients, save_report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check client SharePoint links.")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--clients", default=None,
                    help="clients.json path (default: CLIENTS_JSON env or data/)")
    args = ap.parse_args(argv)

    clients = load_clients(args.clients)
    report = check_all(clients, workers=args.workers, timeout=args.timeout)
    save_report(report, args.clients)
    c = report["counts"]
    print(f'{c["ok"]} ok, {c["dead"]} dead, {c["suspect"]} suspect, '
          f'{c["nolink"]} no-link, {c["error"]} error')
    return report


if __name__ == "__main__":
    main()
