#!/usr/bin/env python3
"""
Create (or update) a login user for the JWT auth API.

Credentials come from environment variables so that no password is stored
in the repository:

    ADMIN_USERNAME=admin ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD='<strong password>' \
        python scripts/create_user.py --roles admin

Requires migrations/004_create_users_table.sql to be applied first.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt  # noqa: E402

from app.core.mysql_client import get_mysql_client  # noqa: E402

VALID_ROLES = {"admin", "analyst", "viewer"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update a user from environment variables")
    parser.add_argument("--roles", default="viewer", help="Comma-separated roles (admin, analyst, viewer)")
    args = parser.parse_args()

    username = os.environ.get("ADMIN_USERNAME", "").strip()
    email = os.environ.get("ADMIN_EMAIL", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")

    if not username or not email or not password:
        print("ADMIN_USERNAME, ADMIN_EMAIL and ADMIN_PASSWORD must be set", file=sys.stderr)
        return 1
    if len(password) < 12:
        print("ADMIN_PASSWORD must be at least 12 characters", file=sys.stderr)
        return 1

    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    unknown = set(roles) - VALID_ROLES
    if not roles or unknown:
        print(f"Invalid roles: {sorted(unknown) or roles}. Allowed: {sorted(VALID_ROLES)}", file=sys.stderr)
        return 1

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    mysql = get_mysql_client()
    mysql.execute(
        """
        INSERT INTO users (username, email, password_hash, roles)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE email = VALUES(email),
                                password_hash = VALUES(password_hash),
                                roles = VALUES(roles)
        """,
        (username, email, password_hash, json.dumps(roles)),
    )
    print(f"User '{username}' saved with roles {roles}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
