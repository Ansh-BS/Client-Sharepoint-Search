"""CLI: give a temp code to every client whose Client ID is blank or their name.

Clients loaded before temp codes existed often had their name typed into the
Client ID column as a stand-in. That reads as a real ID, so they never show as
awaiting one. This finds them and gives each a TEMPnn code, exactly as the
admin upload now does for such rows.

Dry run by default — prints what would change and writes nothing. With
--apply it WRITES the client list, after copying it to
clients.json.bak-YYYYMMDD-HHMMSS beside it. Run it when nobody is editing in
/admin; the app reads the file on every request, so no reload is needed.

    python backfill_temp_codes.py [--clients path.json] [--apply]
"""
import argparse
import os
import shutil
import time

from storage import _resolve, load_clients, save_clients
from temp_codes import fill_temp_codes


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Give temp codes to clients with no real Client ID.")
    ap.add_argument("--clients", default=None,
                    help="clients.json path (default: CLIENTS_JSON env or data/)")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default: dry run)")
    args = ap.parse_args(argv)

    path = _resolve(args.clients)
    clients = load_clients(path)
    filled, minted = fill_temp_codes(clients)
    if not minted:
        print("Every client already has a real or temporary ID.")
        return minted

    verb = "Gave" if args.apply else "Would give"
    print(f"{verb} {len(minted)} client{'' if len(minted) == 1 else 's'} "
          "a temporary ID")
    for c in minted:
        print(f'  "{c["name"]}" (id "{c["was"]}") -> {c["id"]}')

    # A converted row that shares its name with another client is most likely
    # the same client entered twice (e.g. once from the spreadsheet, once via
    # quick add). Merging is a judgement call, so flag it rather than guess.
    names = {}
    for c in filled:
        names.setdefault((c.get("name") or "").strip().casefold(), []).append(c)
    keys = dict.fromkeys((c["name"] or "").strip().casefold() for c in minted)
    dupes = [names[k] for k in keys if len(names[k]) > 1]
    if dupes:
        print("Possible duplicates — check these in /admin:")
        for rows in dupes:
            print("  " + ", ".join(f'{r["id"]} "{r["name"]}"' for r in rows))

    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply to save.")
        return minted

    backup = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    if os.path.exists(path):
        shutil.copy2(path, backup)
        print(f"Backed up to {backup}")
    save_clients(filled, path)
    for c in minted:
        print(f'backfill temp={c["id"]} was="{c["was"]}" name="{c["name"]}"')
    return minted


if __name__ == "__main__":
    main()
