"""
Bootstrap the first SYSTEM_ADMIN user.

/api/auth/register requires SYSTEM_ADMIN to call it (§2.4: only Admins
create users) — which means the very first admin can't come from the API
at all. Run this once per environment instead:

    python -m app.scripts.create_admin --email admin@piet.ac.in --name "Root Admin"

It prompts for a password interactively (never pass it as a CLI arg —
that leaks into shell history / process listings).
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.auth import User, UserRole


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first SYSTEM_ADMIN user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, dest="full_name")
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing is not None:
            print(f"A user with email {args.email} already exists.", file=sys.stderr)
            sys.exit(1)

        admin = User(
            email=args.email,
            hashed_password=hash_password(password),
            full_name=args.full_name,
            role=UserRole.SYSTEM_ADMIN,
            department_id=None,
        )
        db.add(admin)
        db.commit()
        print(f"Created SYSTEM_ADMIN user: {args.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
