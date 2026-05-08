#!/usr/bin/env python3
"""
One-shot migration: onboard Applecross as the first tenant and create Jack's super-admin account.

Usage:
    ADMIN_PASSWORD=<password> python scripts/migrate_applecross.py
    ADMIN_PASSWORD=<password> python scripts/migrate_applecross.py --dry-run

The script:
  1. Finds the Applecross organisation row (by name match).
  2. Sets slug='applecross', is_active=True on it.
  3. Creates a user with username='jack' (or ADMIN_USERNAME env override).
  4. Creates a club_memberships row linking jack → applecross with role='super_admin'.

Set DRY_RUN=1 or pass --dry-run to preview without committing.
"""

import os
import sys
import argparse
import uuid
from datetime import datetime, timezone

import psycopg2
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DB_URL = os.environ.get("DATABASE_URL", "postgresql://cricket:cricket@localhost/betterstats").replace("postgresql+asyncpg://", "postgresql://")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "jack")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_DISPLAY = os.environ.get("ADMIN_DISPLAY_NAME", "Jack")
CLUB_SLUG = os.environ.get("CLUB_SLUG", "applecross")
CLUB_NAME_MATCH = os.environ.get("CLUB_NAME_MATCH", "applecross")


def main(dry_run: bool):
    if not ADMIN_PASSWORD:
        print("ERROR: ADMIN_PASSWORD environment variable is required.")
        sys.exit(1)

    if len(ADMIN_PASSWORD) < 10:
        print("ERROR: Password must be at least 10 characters.")
        sys.exit(1)

    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            # Find Applecross org
            cur.execute(
                "SELECT id, name, slug FROM organisations WHERE LOWER(name) LIKE %s OR LOWER(short_name) LIKE %s",
                (f"%{CLUB_NAME_MATCH.lower()}%", f"%{CLUB_NAME_MATCH.lower()}%"),
            )
            orgs = cur.fetchall()
            if not orgs:
                print(f"ERROR: No organisation found matching '{CLUB_NAME_MATCH}'.")
                sys.exit(1)
            if len(orgs) > 1:
                print("Multiple matches found:")
                for o in orgs:
                    print(f"  {o[0]}  {o[1]}  slug={o[2]}")
                print("Set CLUB_NAME_MATCH to narrow down.")
                sys.exit(1)

            org_id, org_name, existing_slug = orgs[0]
            print(f"Found org: {org_name} (id={org_id}, current_slug={existing_slug})")

            # Check slug collision
            cur.execute("SELECT id FROM organisations WHERE slug = %s AND id != %s", (CLUB_SLUG, org_id))
            if cur.fetchone():
                print(f"ERROR: Slug '{CLUB_SLUG}' is already taken by another org.")
                sys.exit(1)

            print(f"  Will set slug='{CLUB_SLUG}', is_active=True")

            # Check if user already exists
            cur.execute("SELECT id FROM users WHERE username = %s", (ADMIN_USERNAME,))
            existing_user = cur.fetchone()
            if existing_user:
                print(f"  User '{ADMIN_USERNAME}' already exists (id={existing_user[0]})")
                user_id = existing_user[0]
                create_user = False
            else:
                user_id = str(uuid.uuid4())
                print(f"  Will create user '{ADMIN_USERNAME}' (id={user_id})")
                create_user = True

            # Check membership
            cur.execute(
                "SELECT id, role FROM club_memberships WHERE user_id = %s AND club_id = %s",
                (user_id, org_id),
            )
            existing_membership = cur.fetchone()
            if existing_membership:
                print(f"  Membership already exists: role={existing_membership[1]}")
                create_membership = False
            else:
                print(f"  Will create membership: {ADMIN_USERNAME} → {org_name} (super_admin)")
                create_membership = True

            if dry_run:
                print("\n[DRY RUN] No changes made.")
                return

            # Apply changes
            cur.execute(
                "UPDATE organisations SET slug = %s, is_active = TRUE, updated_at = NOW() WHERE id = %s",
                (CLUB_SLUG, org_id),
            )
            print(f"  ✓ Updated organisation: slug='{CLUB_SLUG}', is_active=True")

            if create_user:
                hashed = pwd_context.hash(ADMIN_PASSWORD)
                cur.execute(
                    """INSERT INTO users (id, username, password_hash, display_name, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, NOW(), NOW())""",
                    (user_id, ADMIN_USERNAME, hashed, ADMIN_DISPLAY),
                )
                print(f"  ✓ Created user '{ADMIN_USERNAME}'")
            else:
                # Update password for existing user
                hashed = pwd_context.hash(ADMIN_PASSWORD)
                cur.execute(
                    "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s",
                    (hashed, user_id),
                )
                print(f"  ✓ Updated password for existing user '{ADMIN_USERNAME}'")

            if create_membership:
                membership_id = str(uuid.uuid4())
                cur.execute(
                    """INSERT INTO club_memberships (id, club_id, user_id, role, created_at)
                       VALUES (%s, %s, %s, 'super_admin', NOW())""",
                    (membership_id, org_id, user_id),
                )
                print(f"  ✓ Created super_admin membership")

            conn.commit()
            print("\nMigration complete.")
            print(f"  Club:     {org_name} ({CLUB_SLUG})")
            print(f"  Username: {ADMIN_USERNAME}")
            print(f"  Login at: /login")

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboard Applecross as first tenant")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without committing")
    args = parser.parse_args()
    main(dry_run=args.dry_run or os.environ.get("DRY_RUN") == "1")
