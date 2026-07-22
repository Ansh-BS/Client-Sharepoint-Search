# Client SharePoint Search — in plain English

## What it does

It's a small internal search page for staff. You type a client's name
(typos are fine) or their Client ID, and it instantly suggests matching
clients with a button that takes you straight to that client's SharePoint
folder. No more scrolling through spreadsheets to find the right link.

To update the client list, an admin uploads the latest spreadsheet on the
admin page — the site reads the names, IDs, and folder links from it.

## How your data stays safe

- **Locked behind a login.** You can't see anything without the staff
  password first. Uploading a new spreadsheet needs a second, separate
  admin password on top of that.
- **The client data never leaves our own systems.** It lives only on our
  own server and is never uploaded to the public internet or shared with
  any outside company or service.
- **Nothing runs from outside sources.** The page loads only its own
  files — no third-party code, adverts, or trackers that could leak data.
- **Brute-force protection.** If someone tries to guess the password
  over and over, the site locks them out after a handful of attempts.
- **Secure sessions.** Once you log in, your session is protected so it
  can't be hijacked or read by other software on your machine.
- **Safe updates.** When a new spreadsheet is uploaded, the old list is
  only replaced once the new one is confirmed good — a bad file can't
  wipe out or corrupt the existing data.

In short: it's a staff-only tool, the data stays in-house, and it's built
with the standard protections you'd expect from a proper internal system.
