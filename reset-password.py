#!/usr/bin/env python3
"""
Falcon Fitness — reset an account password.

You do not need to remember the old password. Run this on the machine where the
app lives (your phone, or the server) while the app is stopped or running:

    cd /sdcard/falcon-fitness/falcon-fitness
    python3 reset-password.py

It lists every account, asks which one, asks for a new password, and writes it
to the same database the site uses. Nothing else is changed.
"""

import getpass
import os
import sqlite3
import sys

DB = os.environ.get("FALCON_DB_PATH",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "data", "falcon.db"))


def main():
    if not os.path.exists(DB):
        print(f"No database found at {DB}")
        print("Start the app once first (python app.py) so it can create one.")
        return 1

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    users = con.execute(
        "SELECT id, name, email, role, active, must_change_pw FROM users ORDER BY role, id"
    ).fetchall()

    if not users:
        print("There are no accounts in the database yet.")
        return 1

    print()
    print("Accounts in this database")
    print("-" * 62)
    for u in users:
        flag = "" if u["active"] else "  [disabled]"
        print(f"  {u['id']:>3}  {u['role']:<7} {u['name']:<22} {u['email']}{flag}")
    print("-" * 62)

    raw = input("Which account id? ").strip()
    try:
        uid = int(raw)
    except ValueError:
        print("That is not a number.")
        return 1

    match = next((u for u in users if u["id"] == uid), None)
    if not match:
        print("No account with that id.")
        return 1

    print(f"\nResetting password for {match['name']} <{match['email']}>")

    while True:
        pw = getpass.getpass("New password (8+ characters): ")
        if len(pw) < 8:
            print("Too short — use at least 8 characters.")
            continue
        if pw != getpass.getpass("Type it again: "):
            print("They did not match. Try again.")
            continue
        break

    from werkzeug.security import generate_password_hash

    con.execute(
        "UPDATE users SET password_hash=?, active=1, must_change_pw=0 WHERE id=?",
        (generate_password_hash(pw), uid))
    con.commit()
    con.close()

    print()
    print("=" * 62)
    print(f"  Done. {match['email']} can now sign in at /login")
    print("  The account was also re-enabled if it had been disabled.")
    print("=" * 62)
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(1)
